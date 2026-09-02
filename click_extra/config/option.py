# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""Utilities to load parameters and options from a configuration file.

```{hint}
Why `config`?

That whole namespace is using the common `config` short-name to designate
configuration files.

Not `conf`, not `cfg`, not `configuration`, not `settings`. Just `config`.

A quick survey of existing practices, and poll to my friends informed me that
`config` is more explicit and less likely to be misunderstood.

After all, is there a chance for it to be misunderstood, in the context of a CLI,
for something else? *Confirm*? *Conference*? *Conflict* *Confuse*?...

So yes, `config` is good enough.
```

Dotted keys in configuration files (like `"subcommand.option": value`) are
automatically expanded into nested dicts before merging, so users can freely mix
flat dot-notation and nested structures in any supported format.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import plistlib
import shlex
from collections import ChainMap
from collections.abc import Iterable
from configparser import ConfigParser, ExtendedInterpolation
from enum import Enum
from functools import cached_property, partial
from gettext import gettext as _
from pathlib import Path, PurePosixPath

from boltons.iterutils import flatten, unique
from boltons.pathutils import shrinkuser
from boltons.urlutils import URL
from click import (
    UNPROCESSED,
    Choice,
    echo,
    get_app_dir,
    get_current_context,
)
from click._utils import UNSET
from click.core import ParameterSource
from click.parser import _split_opt
from deepmerge import always_merger
from extra_platforms import is_windows
from extra_platforms._utils import _remove_blanks
from wcmatch import fnmatch, glob

from .. import context
from ..parameters import (
    PARAM_PATH_SEP,
    ExtraOption,
    ParamStructure,
    canonical_param_name,
    replay_raw_args,
    require_sibling_param,
    resolve_flag_value,
    search_params,
)
from ..types import EnumChoice
from .builtin import THEMES_CONFIG_KEY, _builtin_config_validators
from .formats import (
    SERIALIZABLE_FORMATS,
    SQLITE_CONFIG_TABLE,
    ConfigFormat,
    disabled_format_message,
    format_from_mime,
    format_from_path,
    parse_content,
    serialize_content,
)
from .schema import (
    ConfigValidator,
    _merge_into_template,
    _normalize_conf,
    _opaque_paths,
    _scope_app_sections,
    _select_app_section,
    _strip_opaque_subtrees,
    make_schema_callable,
    run_config_validation,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any, Literal

    import click

logger = logging.getLogger(__name__)


VCS_DIRS = (".git", ".hg", ".svn", ".bzr", "CVS", ".darcs")
"""VCS directory names used to identify version control system roots.

Includes:
- `.git`: Git
- `.hg`: Mercurial
- `.svn`: Subversion
- `.bzr`: Bazaar
- `CVS`: CVS (note: uppercase, no leading dot)
- `.darcs`: Darcs
"""


CONFIG_OPTION_NAME = "config"
"""Hardcoded name of the configuration option.

This name is going to be shared by both the `--config` and `--no-config` options
below, so they can compete with each other to either set a path pattern or disable the
use of any configuration file at all.
"""


DEFAULT_EXCLUDED_PARAMS = (
    CONFIG_OPTION_NAME,
    "export_config",
    "params",
    "validate_config",
    "version",
)
"""Default parameter IDs to exclude from the configuration file.

Defaults to:

- `--config` option, which cannot be used to recursively load another configuration
  file.
- `--export-config` flag, which like `--params` introspects the CLI and exits,
  so it has no place in the configuration it would export.
- `--params` flag, which is like `--help` and stops the CLI execution.
- `--validate-config` option, which belongs to the same self-referential
  config machinery as `--config` and `--export-config`.
- `--version`, which is not a configurable option *per-se*.

`--help` is excluded too (it makes no sense to have a configuration file always
force a CLI to show the help and exit), but is deliberately absent from this tuple:
unlike the entries above, click-extra does not control that option's internal name.
It is resolved at runtime instead, in {attr}`ConfigOption.excluded_params`, so a
rename on Click's own side does not silently stop excluding it.
"""


class Sentinel(Enum):
    """Enum used to define sentinel values.

    ```{note}
    This reuse the same pattern as `Click._utils.Sentinel`.
    ```

    ```{seealso}
    [PEP 661 - Sentinel Values](https://peps.python.org/pep-0661/).
    ```
    """

    NO_CONFIG = object()
    VCS = object()  # noqa: PIE796

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"


NO_CONFIG = Sentinel.NO_CONFIG
"""Sentinel used to indicate that no configuration file must be used at all."""

VCS = Sentinel.VCS
"""Sentinel used to stop parent directory walking at the nearest VCS root."""


def _join_format_labels(formats: Iterable[ConfigFormat]) -> str:
    """Enumerate format labels in the `A, B or C` form used by error messages.

    A single format is returned bare: the generic
    `", ".join(labels[:-1]) + " or " + labels[-1]` shape leaves a dangling
    conjunction on a one-item list, which is what an option restricted to one
    format always produces.
    """
    labels = [str(fmt) for fmt in formats]
    if len(labels) < 2:
        return "".join(labels)
    return f"{', '.join(labels[:-1])} or {labels[-1]}"


class ConfigOption(ExtraOption, ParamStructure):
    """A pre-configured option adding `--config LOCATION`."""

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        metavar="LOCATION",
        type=UNPROCESSED,
        help=_(
            "Location of the configuration file. Supports local path with glob patterns "
            "or remote URL.",
        ),
        is_eager: bool = True,
        expose_value: bool = False,
        file_format_patterns: dict[ConfigFormat, Sequence[str] | str]
        | Iterable[ConfigFormat]
        | ConfigFormat
        | None = None,
        file_pattern_flags: int = fnmatch.NEGATE | fnmatch.SPLIT,
        show_file_patterns: bool | None = None,
        roaming: bool = True,
        force_posix: bool = False,
        search_pattern_flags: int = (
            glob.GLOBSTAR
            | glob.FOLLOW
            | glob.DOTGLOB
            | glob.BRACE
            | glob.SPLIT
            | glob.GLOBTILDE
            | glob.NODIR
        ),
        search_parents: bool = False,
        stop_at: Path | str | Literal[Sentinel.VCS] | None = Sentinel.VCS,
        cascade: bool = False,
        excluded_params: Iterable[str] | None = None,
        included_params: Iterable[str] | None = None,
        strict: bool = False,
        config_schema: type | Callable[[dict[str, Any]], Any] | None = None,
        schema_strict: bool = False,
        fallback_sections: Sequence[str] = (),
        config_validators: Sequence[ConfigValidator] = (),
        **kwargs,
    ) -> None:
        """Takes as input a path to a file or folder, a glob pattern, or an URL.

        - `is_eager` is active by default so the `callback` gets the opportunity to
          set the `default_map` of the CLI before any other parameter is processed.

        - `default` is set to the value returned by `self.default_pattern()`, which
          is a pattern combining the default configuration folder for the CLI (as
          returned by `click.get_app_dir()`) and all supported file formats.

          ```{attention}
          Default search pattern must follow the syntax of [wcmatch.glob](https://facelessuser.github.io/wcmatch/glob/#syntax).
          ```

        - `excluded_params` are parameters which, if present in the configuration
          file, will be ignored and not applied to the CLI. Items are expected to be the
          fully-qualified ID of the parameter, as produced in the output of
          `--params`. Will default to the value of `DEFAULT_EXCLUDED_PARAMS`,
          plus the CLI's `--help` option, resolved at runtime.

        - `included_params` is the inverse of `excluded_params`: only the listed
          parameters will be loaded from the configuration file. Cannot be used together
          with `excluded_params`.
        """

        if not param_decls:
            param_decls = ("--config", CONFIG_OPTION_NAME)

        # Setup supported file format patterns.
        self.file_format_patterns: dict[ConfigFormat, tuple[str, ...]]
        """Mapping of `ConfigFormat` to their associated file patterns.

        Can be a string or a sequence of strings. This defines which configuration file
        formats are supported, and which file patterns are used to search for them.

        ```{note}
        All formats depending on third-party dependencies that are not installed
        will be ignored.
        ```

        ```{attention}
        File patterns must follow the syntax of [wcmatch.fnmatch](https://facelessuser.github.io/wcmatch/fnmatch/#syntax).
        ```
        """

        if isinstance(file_format_patterns, ConfigFormat):
            self.file_format_patterns = {
                file_format_patterns: file_format_patterns.patterns
            }
        elif isinstance(file_format_patterns, dict):
            self.file_format_patterns = {
                fmt: (patterns,) if isinstance(patterns, str) else tuple(patterns)
                for fmt, patterns in file_format_patterns.items()
            }
        elif isinstance(file_format_patterns, Iterable):
            self.file_format_patterns = {
                fmt: fmt.patterns for fmt in file_format_patterns
            }
        else:
            self.file_format_patterns = {fmt: fmt.patterns for fmt in ConfigFormat}

        self.auto_file_formats = file_format_patterns is None
        """Whether the format set was inherited instead of chosen by the developer.

        `True` when no `file_format_patterns` was provided, so the set is whatever the
        installed [extra dependencies](install.md#extra-dependencies) enable. It ranges
        from 3 patterns on a bare install to 14 with every extra, which is an artifact
        of the environment rather than a decision the CLI made.

        Only `collapse_default()` reads it, and only when `show_file_patterns` is
        left at `None`.
        """

        # Check mapping of file formats to their patterns.
        for fmt, patterns in self.file_format_patterns.items():
            assert fmt in ConfigFormat
            assert isinstance(patterns, tuple)
            assert patterns, f"No pattern defined for {fmt}"
            assert all(isinstance(pat, str) and pat for pat in patterns)
            assert len(set(patterns)) == len(patterns), f"Duplicate patterns for {fmt}"

        # Filter out disabled formats.
        disabled = {fmt for fmt in self.file_format_patterns if not fmt.enabled}
        if disabled:
            logger.debug(f"Skip disabled {', '.join(map(str, disabled))}.")
            for fmt in disabled:
                del self.file_format_patterns[fmt]

        if not self.file_format_patterns:
            raise ValueError("No configuration format is enabled.")

        # Validate file pattern flags.
        if not file_pattern_flags & glob.SPLIT:
            logger.warning("Forcing SPLIT flag for file patterns.")
            file_pattern_flags |= glob.SPLIT

        self.file_pattern_flags = file_pattern_flags
        """Flags provided to all calls of `wcmatch.fnmatch`.

        Applies to the matching of file names against supported format patterns
        specified in `file_format_patterns`.

        ```{important}
        The `SPLIT` flag is always forced, as our multi-pattern design relies on
        it.
        ```
        """

        self.show_file_patterns = show_file_patterns
        """Whether the help screen prints the file patterns of the default.

        Follows the tri-state convention of Click Extra's other display settings:

        - `None` prints them when the developer chose the format set, and hides them
          when it was inherited from the install.
        - `True` always prints them, which is how a CLI advertises the formats its
          own dependencies enable.
        - `False` always hides them.

        See `collapse_default()` for what each state renders.
        """

        # Setup the configuration for default folder search.
        self.roaming = roaming
        self.force_posix = force_posix
        """Configuration for default folder search.

        `roaming` and `force_posix` are [fed to click.get_app_dir()](https://click.palletsprojects.com/en/stable/api/#click.get_app_dir) to
        determine the location of the default configuration folder.
        """

        kwargs.setdefault("default", self.default_pattern)

        # Force BRACE to ensure multi-format default patterns expand correctly.
        if not search_pattern_flags & glob.BRACE:
            logger.warning("Forcing BRACE flag for search patterns.")
            search_pattern_flags |= glob.BRACE

        # Force NODIR to optimize search for files only.
        if not search_pattern_flags & glob.NODIR:
            logger.warning("Forcing NODIR flag for search patterns.")
            search_pattern_flags |= glob.NODIR

        self.search_pattern_flags = search_pattern_flags
        """Flags provided to all calls of `wcmatch.glob`.

        Applies to both the default pattern and any user-provided pattern.

        ```{important}
        The `BRACE` flag is always forced, so that multi-format default
        patterns using ``{pat1,pat2,...}`` syntax expand correctly.

        The `NODIR` flag is always forced, to optimize the search for files only.
        ```
        """

        self.search_parents = search_parents
        """Indicates whether to walk back the tree of parent folders when searching for
        configuration files.
        """

        self.stop_at = stop_at
        """Boundary for parent directory walking.

        - `None`: walk up to filesystem root.
        - `VCS`: stop at the nearest VCS root, whichever system marks it (see
          {data}`~click_extra.config.option.VCS_DIRS`) (default).
        - A `Path` or `str`: stop at that directory.
        """

        self.cascade = cascade
        """Merge every discovered configuration file instead of stopping at the
        first parseable one.

        When `True`, all files found by auto-discovery (the app-dir search,
        including the parent walk when `search_parents=True`, plus the
        `pyproject.toml` CWD search when enabled) are loaded and layered into
        the context's `default_map` via a `~collections.ChainMap`. The most
        local file wins on key lookup: a `pyproject.toml` found near the CWD
        overrides the app-dir config, which overrides files found higher up
        the parent walk.

        An explicit `--config` value never cascades: it pins a single source,
        whatever the pattern matches.

        Defaults to `False`, which preserves the historical behavior of the
        first successfully parsed file winning.
        """

        if excluded_params is not None and included_params is not None:
            msg = "excluded_params and included_params are mutually exclusive."
            raise ValueError(msg)

        self.extra_excluded_params: frozenset[str] = frozenset()
        """Additional exclusions merged into the dynamic `excluded_params` default.

        Populated by `Command`'s `excluded_params` forwarding, which is
        additive: the default blocklist (`--config`, `--version`, `--help`,
        ...) is preserved and the forwarded IDs are unioned into it when the
        property resolves. Ignored when an explicit `excluded_params` was
        frozen on the instance, as the property is then never consulted.
        """

        # If the user provided its own excluded params, freeze them now and store it
        # to prevent the dynamic default property to be called.
        if excluded_params is not None:
            self.excluded_params = frozenset(excluded_params)

        # Freeze and store included_params. The resolution into
        # excluded_params happens in params_objects.
        self.included_params: frozenset[str] | None = (
            frozenset(included_params) if included_params is not None else None
        )

        self.strict = strict
        """Defines the strictness of the configuration loading.

        - If `True`, raise an error if the configuration file contain parameters not
          recognized by the CLI.
        - If `False`, silently ignore unrecognized parameters.
        """

        self.config_schema = config_schema
        """Optional schema for structured access to configuration values.

        When set, the app's configuration section is extracted from the parsed
        config file, normalized (hyphens replaced with underscores), flattened
        (nested dicts joined with `_`), and passed to this callable to produce
        a typed configuration object.

        Supports:

        - **Dataclass types**: detected via `__dataclass_fields__`. Keys
          are normalized, nested dicts are flattened, and the result is filtered
          to known fields before instantiation. This allows nested config
          sections (like `[tool.myapp.sub-section]`) to map directly to flat
          dataclass fields (like `sub_section_key`).
        - **Any callable** `dict → T`: called directly with the raw
          dict. Works with Pydantic's `Model.model_validate`, attrs, or
          custom factory functions. The caller is responsible for key
          normalization and flattening.

        The resulting object is stored in
        `ctx.meta[click_extra.context.TOOL_CONFIG]` and can be retrieved
        via `get_tool_config`.
        """

        self.schema_strict = schema_strict
        """Strictness for schema validation (separate from `strict`).

        - If `True`, raise `ValueError` when the config section contains keys
          that do not match any dataclass field (after normalization and
          flattening). Only applies when `config_schema` is a dataclass.
        - If `False`, ignore unrecognized keys. When the section is
          schema-only (`included_params=()`), a warning still names them:
          see `warn_unknown` in
          {func}`~click_extra.config.schema.make_schema_callable`.

        ```{note}
        This is distinct from `strict`, which controls whether
        `merge_default_map` rejects config keys not matching CLI
        parameters.  `schema_strict` validates against dataclass fields
        instead.
        ```
        """

        self.fallback_sections: Sequence[str] = tuple(fallback_sections)
        """Legacy section names to try when the app's own section is empty.

        Useful when a CLI tool has been renamed: old configuration files that
        still use `[tool.old-name]` (TOML), `old-name:` (YAML), or
        ``{"old-name": …}`` (JSON) are recognized with a deprecation warning.
        Works with all configuration formats.
        """

        self.schema_warn_unknown: bool = (
            self.included_params is not None and not self.included_params
        )
        """Warn on config keys unknown to the schema, in lax mode.

        Inferred, not user-supplied: an explicitly empty `included_params`
        means no CLI parameter is merged from the app's config section, so the
        section is schema-only and any key the schema does not know is a typo
        worth a warning. Forwarded to
        {func}`~click_extra.config.schema.make_schema_callable` and the
        validation pipeline as `warn_unknown`.
        """

        self._config_schema_callable = make_schema_callable(
            config_schema,
            strict=schema_strict,
            warn_unknown=self.schema_warn_unknown,
        )

        self.config_validators: tuple[ConfigValidator, ...] = (
            _builtin_config_validators() + tuple(config_validators)
        )
        """Extension validators for sub-trees of the configuration file.

        Each {class}`~click_extra.config.schema.ConfigValidator` targets a dotted `extension_path` relative
        to the app section. Validators run after click-extra's built-in
        CLI-parameter strict check (during `--validate-config`) and after the
        schema callable produces the typed configuration object (during normal
        config loading).

        The list is seeded with click-extra's built-in validators (currently the
        one for `[tool.<cli>.themes.<name>]` tables, see
        {func}`click_extra.theme.validate_themes_config`); user-supplied
        validators are appended after them. App code that registers its own
        validator on the same `extension_path` simply runs alongside the
        built-in: both validators are called, both sets of errors surface.
        """

        # Pre-compute the unified opaque-path set: every dotted path that
        # click-extra must skip during its CLI-parameter strict check. See
        # :py:func:`_opaque_paths` for how the schema and validator sources merge.
        self._opaque_paths: frozenset[str] = _opaque_paths(
            config_schema, self.config_validators
        )
        """Dotted paths, relative to the app section, that strict CLI-parameter
        validation must skip.

        Union of schema-inferred extension fields and explicit
        {class}`~click_extra.config.schema.ConfigValidator` registrations. Used by
        :py:meth:`merge_default_map` and
        :py:meth:`ValidateConfigOption.validate_config`.
        """

        kwargs.setdefault("callback", self.load_conf)

        super().__init__(
            param_decls=param_decls,
            metavar=metavar,
            type=type,
            help=help,
            is_eager=is_eager,
            expose_value=expose_value,
            **kwargs,
        )

        self._check_pattern_sanity()

    def _check_pattern_sanity(self) -> None:
        """Emit DEBUG-level logs for common `ConfigOption` misconfigurations.

        The checks help developers catch suboptimal patterns early when running
        with debug logging enabled. Four categories are covered:

        1. Broad glob + narrow (all-literal) format patterns.
        2. Literal default whose filename doesn't match any format pattern.
        3. Format/extension mismatch (unconditional).
        4. Dotfile referenced without `DOTGLOB` in `search_pattern_flags`.
        """

        # --- Check 3 (unconditional): format/extension mismatch ---
        # Build a reverse map: extension → canonical ConfigFormats.
        ext_to_formats: dict[str, set[ConfigFormat]] = {}
        for fmt in ConfigFormat:
            for pat in fmt.patterns:
                ext = PurePosixPath(pat).suffix
                if ext:
                    ext_to_formats.setdefault(ext, set()).add(fmt)

        for fmt, patterns in self.file_format_patterns.items():
            for pat in patterns:
                ext = PurePosixPath(pat).suffix
                if ext and ext in ext_to_formats:
                    canonical = ext_to_formats[ext]
                    if fmt not in canonical:
                        canonical_names = ", ".join(sorted(f.name for f in canonical))
                        logger.debug(
                            f"Format pattern {pat!r} mapped to {fmt.name} but "
                            f"extension {ext!r} is canonically associated with "
                            f"{canonical_names}."
                        )

        # --- Checks 1, 2, 4 require an explicit default ---
        if not isinstance(self.default, str):
            return

        file_part = PurePosixPath(self.default).name
        default_is_magic = glob.is_magic(
            self.default.replace("\\", "/"), flags=self.search_pattern_flags
        )
        all_format_patterns = tuple(flatten(self.file_format_patterns.values()))

        # Check 1: broad glob + all-literal format patterns.
        if default_is_magic:
            all_literal = all(
                not glob.is_magic(p.replace("\\", "/"), flags=self.search_pattern_flags)
                for p in all_format_patterns
            )
            if all_literal:
                logger.debug(
                    f"Broad search pattern {self.default!r} with literal format "
                    f"patterns {all_format_patterns!r}. The glob may scan many "
                    f"files only to discard most of them."
                )

        # Check 2: literal default that never matches any format pattern.
        if not default_is_magic:
            pattern_str = "|".join(all_format_patterns)
            if not fnmatch.fnmatch(
                file_part, pattern_str, flags=self.file_pattern_flags
            ):
                logger.debug(
                    f"Literal search pattern {self.default!r} does not match "
                    f"any format pattern ({pattern_str!r}). No config will ever "
                    f"be found."
                )

        # Check 4: dotfile without DOTGLOB.
        if not (self.search_pattern_flags & glob.DOTGLOB):
            dotfiles: list[str] = []
            if file_part.startswith("."):
                dotfiles.append(self.default)
            dotfiles.extend(
                pat
                for pat in all_format_patterns
                if PurePosixPath(pat).name.startswith(".")
            )
            if dotfiles:
                logger.debug(
                    f"Dotfile(s) {dotfiles!r} referenced but DOTGLOB is not set "
                    f"in search_pattern_flags. Hidden files may be skipped by "
                    f"glob."
                )

    @cached_property
    def excluded_params(self) -> frozenset[str]:  # type: ignore[override]
        """Generates the default list of fully-qualified IDs to exclude.

        ```{danger}
        It is only called once to produce the default exclusion list if the user did
        not provided its own.

        It was not implemented in the constructor but made as a property, to allow
        for a just-in-time call within the current context. Without this trick we could
        not have fetched the CLI name.
        ```
        """
        ctx = get_current_context()
        cli = ctx.find_root().command
        excluded_ids = list(DEFAULT_EXCLUDED_PARAMS)
        # Resolve the help option's ID from Click itself instead of assuming it is
        # named "help": Click's development branch renamed it to
        # "_click_default_help", and click-extra does not control that name.
        help_option = cli.get_help_option(ctx)
        if help_option is not None and help_option.name is not None:
            excluded_ids.append(help_option.name)
        return (
            frozenset(f"{cli.name}{PARAM_PATH_SEP}{p}" for p in excluded_ids)
            | self.extra_excluded_params
        )

    @cached_property
    def file_pattern(self) -> str:
        """Compile all file patterns from the supported formats.

        Uses `,` (comma) notation to combine multiple patterns, suitable for
        `wcmatch` brace expansion (``{pat1,pat2,...}``).

        Returns a single pattern string.
        """
        patterns = unique(flatten(self.file_format_patterns.values()))
        return ",".join(patterns)

    def default_pattern(self) -> str:
        """Returns the default pattern used to search for the configuration file.

        Defaults to ``<app_dir>/{*.toml,*.json,*.ini}``. Where `<app_dir>` is
        produced by the [click.get_app_dir() method](https://click.palletsprojects.com/en/stable/api/#click.get_app_dir).
        The result depends on OS and is influenced by the `roaming` and
        `force_posix` properties.

        Multiple file format patterns are wrapped with ``{…}`` brace-expansion
        syntax so that `wcmatch.glob` correctly applies the directory prefix
        to every sub-pattern.

        ```{note}
        A CLI wanting another folder layout, like the one
        [platformdirs](https://github.com/tox-dev/platformdirs) computes,
        passes its own pattern to `default` instead. That keeps the layout a
        choice of the CLI rather than a dependency of this package: see
        [the documentation](config-discovery.md#use-platformdirs-instead).
        ```
        """
        ctx = get_current_context()
        cli_name = ctx.find_root().info_name
        if not cli_name:
            raise ValueError
        app_dir = Path(
            get_app_dir(cli_name, roaming=self.roaming, force_posix=self.force_posix),
        ).resolve()
        fp = self.file_pattern
        # Wrap multi-pattern with braces for BRACE expansion.
        suffix = f"{{{fp}}}" if "," in fp else fp
        return f"{app_dir}{os.path.sep}{suffix}"

    def get_help_extra(self, ctx: click.Context) -> click.types.OptionHelpExtra:
        """Replaces the default value of the configuration option.

        Display a pretty path that is relative to the user's home directory:

        ```{code-block} text

        ~/folder/my_cli/{*.toml,*.json,*.ini}
        ```

        Instead of the full absolute path:

        ```{code-block} text

        /home/user/folder/my_cli/{*.toml,*.json,*.ini}
        ```

        ```{caution}
        This only applies when the `GLOBTILDE` flag is set in `search_pattern_flags`.
        ```

        An inherited format set is then reduced to the folder it searches, as
        described in `collapse_default()`.
        """
        extra = super().get_help_extra(ctx)
        extra["default"] = self.collapse_default(self.render_default(ctx))
        return extra

    def render_default(self, ctx: click.Context) -> str:
        """The default search pattern, as a portable home-relative path.

        Keeps the whole pattern, file patterns included. The help screen collapses
        an inherited set on top of this with `collapse_default()`, but a consumer
        with room for the files (the `FILES` section of a man page) calls this
        method instead.
        """
        default = self.get_default(ctx)
        if default is NO_CONFIG:
            return "disabled"
        if self.search_pattern_flags & glob.GLOBTILDE:
            # When the default already starts with `~` (user-supplied tilde
            # pattern), use it as-is. Passing through `Path()` would
            # normalize forward slashes to backslashes on Windows.
            default_str = str(default)
            if default_str.startswith("~"):
                return default_str
            return str(shrinkuser(Path(default)))
        return str(default)

    def collapse_default(self, default: str) -> str:
        """Reduce an inherited default pattern to the folder it searches.

        A CLI installed with every extra searches 15 file patterns, so its default
        renders as a 136-character glob. The help screen has no space for it and no
        place to break it, so Click splits it mid-word:

        ```{code-block} text

        [default: ~/.config/hello/{*.
        toml,*.yaml,*.yml,*.json,*.json5,*.jwcc,*.jsonc,
        *.hjson,*.ini,*.xml,*.plist,*.sqlite,*.sqlite3,*
        .conf,pyproject.toml}]
        ```

        Rendering the folder alone answers the question a reader opens `--help` for,
        on one line, and keeps the answer the same on every install:

        ```{code-block} text

        [default: ~/.config/hello/]
        ```

        A developer who passed `file_format_patterns` chose that set, so it is
        displayed in full: the pattern is short enough to read, and the help screen
        is where the choice shows up. `show_file_patterns` overrides that reading in
        either direction, and `True` is what a CLI advertising its formats wants: the
        set is computed from the installed dependencies at each invocation, so the
        help screen reports what that install can really parse. The complete pattern
        of any CLI stays available in the output of `--params`.

        The trailing separator marks the value as a folder, since it is a search base
        and not a location the option accepts back.
        """
        show = self.show_file_patterns
        if show is None:
            show = not self.auto_file_formats
        if show:
            return default
        fp = self.file_pattern
        suffix = f"{{{fp}}}" if "," in fp else fp
        folder, sep, tail = default.rpartition(os.path.sep)
        # Leave a custom default alone: only the pattern this option built for
        # itself ends with its own file patterns.
        if not sep or tail != suffix:
            return default
        return folder + sep

    @staticmethod
    def _find_vcs_root(start: Path) -> Path | None:
        """Walk up from `start` looking for a VCS root directory.

        Returns the directory containing one of the VCS directories defined in
        `VCS_DIRS`, or `None` if no VCS root is found before reaching the
        filesystem root.
        """
        current = start if start.is_dir() else start.parent
        for directory in (current, *current.parents):
            if any((directory / vcs_dir).exists() for vcs_dir in VCS_DIRS):
                return directory
        return None

    def _resolve_stop_at(self, start_dir: Path) -> Path | None:
        """Resolve the `stop_at` value to an absolute `Path` or `None`.

        - `None` → `None` (no boundary).
        - `VCS` → calls `_find_vcs_root(start_dir)`.
        - `Path` or other `str` → resolves to absolute.
        """
        if self.stop_at is None:
            return None
        if self.stop_at is VCS:
            return self._find_vcs_root(start_dir)
        # Mypy cannot narrow `Literal[Sentinel.VCS]` via the `is` check above.
        assert isinstance(self.stop_at, (str, Path))
        return Path(self.stop_at).resolve()

    @staticmethod
    def _should_stop_walking(directory: Path, stop_at: Path | None) -> bool:
        """Return `True` if the parent-directory walk should stop.

        Stops when:
        - `stop_at` is set and `directory` is not equal to or a child of it.
        - The directory exists but is not readable.
        """
        if stop_at is not None:
            try:
                directory.relative_to(stop_at)
            except ValueError:
                return True
        return bool(directory.exists() and not os.access(directory, os.R_OK))

    def parent_patterns(self, pattern: str) -> Iterable[tuple[str | None, str]]:
        """Generate `(root_dir, file_pattern)` pairs for searching.

        Each yielded pair can be passed directly to
        `glob.iglob(file_pattern, root_dir=root_dir)` so that every
        sub-pattern (whether from `BRACE` or `SPLIT` expansion) is
        correctly scoped to the same directory.

        `root_dir` is `None` for entirely magic patterns that will be
        evaluated relative to the current working directory.

        Stops when reaching the root folder, the `stop_at` boundary, or an
        inaccessible directory.
        """

        # Normalize path separators for magic detection: on Windows, backslashes
        # in paths are mistaken for glob escape characters by wcmatch.
        def is_magic(p: str) -> bool:
            return glob.is_magic(p.replace("\\", "/"), flags=self.search_pattern_flags)

        # Split pattern into non-magic directory prefix (root_dir) and magic
        # file suffix (file_pattern).
        root_dir: Path | None
        if not is_magic(pattern):
            resolved = Path(pattern).resolve()
            if resolved.is_file():
                root_dir = resolved.parent
                file_pattern = resolved.name
            else:
                root_dir = resolved
                file_pattern = ""
        else:
            parts = Path(pattern).parts
            magic_idx = next(i for i, part in enumerate(parts) if is_magic(part))
            if magic_idx == 0:
                # Entirely magic (like "{*.toml,*.yaml}").
                root_dir = None
                file_pattern = pattern
            else:
                root_dir = Path(*parts[:magic_idx]).resolve()
                file_pattern = str(Path(*parts[magic_idx:]))

        # Yield the original location.
        root_str = str(root_dir) if root_dir is not None else None
        yield root_str, file_pattern

        if not self.search_parents:
            return

        if root_dir is None:
            logger.debug("Entirely magic pattern, skipping parent search.")
            return

        logger.debug("Parent search enabled.")
        stop_at = self._resolve_stop_at(root_dir)

        for parent in root_dir.parents:
            if self._should_stop_walking(parent, stop_at):
                logger.debug(f"Stopped walking at {parent}")
                return
            yield str(parent), file_pattern

    def search_and_read_file(
        self,
        pattern: str,
    ) -> Iterable[tuple[Path | URL, str, str | None]]:
        """Search filesystem or URL for files matching the `pattern`.

        If `pattern` is an URL, download its content. A pattern is considered an URL
        only if it validates as one and starts with `http://` or `https://`. All
        other patterns are considered glob patterns for local filesystem search.

        Returns an iterator of `(location, content, media_type)` triples, for each
        one matching the pattern. `location` is normalized and `content` raw.
        `media_type` is the bare `type/subtype` the server advertised in its
        `Content-Type` header, and is `None` for a local file, whose format is
        derived from its name. Only files are returned, directories are silently
        skipped.

        This method returns the raw content of all matching patterns, without trying to
        parse them. If the content is empty, it is still returned as-is.

        Also includes lookups into parents directories if `self.search_parents` is
        `True`.

        Raises `FileNotFoundError` if no file was found after searching all locations.
        """
        files_found = 0

        # Check if the pattern is an URL.
        location = URL(pattern)
        location.normalize()
        if location and location.scheme in ("http", "https"):
            # It's an URL, try to download it.
            logger.debug(f"Download file from URL: {location}")
            # Fetch the remote config with the standard library rather than
            # `requests`: downloading a file is the only HTTP call Click Extra
            # makes, and `urllib` handles it (TLS, redirects, and the
            # `*_proxy` environment variables) without forcing `requests`
            # and its urllib3 / charset-normalizer / idna stack onto every
            # install. It is still imported lazily, on this rare path only, so
            # `http.client` / `ssl` stay off every CLI's startup. Do not
            # hoist these back to module scope.
            from urllib.error import HTTPError
            from urllib.request import urlopen

            try:
                with urlopen(str(location)) as response:
                    files_found += 1
                    # Decode using the charset advertised in the Content-Type
                    # header, defaulting to UTF-8: the near-universal encoding
                    # for configuration files.
                    charset = response.headers.get_content_charset() or "utf-8"
                    # The same header types the payload. A server sending no
                    # Content-Type at all reads as `text/plain`, which no format
                    # claims, so the URL's file name still decides.
                    media_type = response.headers.get_content_type()
                    yield location, response.read().decode(charset), media_type
            # A 4xx/5xx leaves files_found at 0, so the search falls through to
            # the FileNotFoundError below, like a missing local file. Lower-level
            # URLError failures (DNS, refused connection, TLS) still propagate.
            except HTTPError as error:
                logger.warning(f"Can't download {location}: {error.reason}")

        # Not an URL, search local file system.
        else:
            logger.debug(f"Search filesystem for {pattern}")
            # wcmatch expect patterns to be written with Unix-like syntax by default,
            # even on Windows. See more details at:
            # https://facelessuser.github.io/wcmatch/glob/#windows-separators
            # https://github.com/facelessuser/wcmatch/issues/194
            if is_windows():
                win_path = Path(pattern)
                pattern = str(win_path.as_posix())
                logger.debug(f"Windows pattern converted from {win_path} to {pattern}")

            for root_dir, file_pattern in self.parent_patterns(pattern):
                # Sort matches within each directory: iglob yields in filesystem
                # order, so without this the winner among sibling files (and
                # the layering order of a cascade) would be arbitrary.
                for file in sorted(
                    glob.iglob(
                        file_pattern,
                        root_dir=root_dir,
                        flags=self.search_pattern_flags,
                    )
                ):
                    base = Path(root_dir) if root_dir else Path()
                    file_path = (base / file).resolve()
                    logger.debug(f"Found candidate: {file_path}")
                    if not file_path.is_file():
                        logger.debug(f"Skipping non-file {file_path}")
                        continue
                    files_found += 1
                    if format_from_path(
                        file_path, (ConfigFormat.SQLITE, ConfigFormat.PLIST)
                    ):
                        # SQLite databases and binary plists are read from
                        # their path, not from a text payload: see
                        # load_sqlite_config() and load_plist_config().
                        yield file_path, "", None
                    else:
                        yield file_path, file_path.read_text(encoding="utf-8"), None

        if not files_found:
            raise FileNotFoundError(f"No file found matching {pattern}")

    def parse_conf(
        self,
        content: str,
        formats: Sequence[ConfigFormat],
        location: Path | URL | None = None,
    ) -> Iterable[dict[str, Any] | None]:
        """Parse the `content` with the given `formats`.

        Tries to parse the given raw `content` string with each of the given
        `formats`, in order. Yields the resulting data structure for each
        successful parse.

        `location` is the path the `content` was read from. It is only needed
        by formats that cannot be parsed from a text payload, like `SQLITE`,
        which is read straight from its file, and the binary variant of
        `PLIST`, which only exists on disk. Such formats are skipped when
        `location` is missing or is not a local file.

        ```{attention}
        Formats whose parsing raises an exception or does not return a `dict`
        are considered a failure and are skipped.

        This follows the *parse, don't validate* principle.
        ```
        """

        conf = None
        for fmt in formats:
            try:
                if fmt is ConfigFormat.INI:
                    conf = self.load_ini_config(content)
                elif fmt is ConfigFormat.ARGFILE:
                    conf = self.load_argfile_config(content)
                elif fmt is ConfigFormat.SQLITE:
                    if not isinstance(location, Path):
                        raise ValueError(
                            "SQLite configurations can only be read from a local file."
                        )
                    conf = self.load_sqlite_config(location)
                elif fmt is ConfigFormat.PLIST and isinstance(location, Path):
                    # Local files are read as raw bytes so the binary plist
                    # variant parses too; text payloads (URL downloads) fall
                    # through to parse_content(), which handles the XML one.
                    conf = self.load_plist_config(location)
                else:
                    conf = parse_content(fmt, content)

            except Exception as ex:  # noqa: BLE001
                logger.debug(f"{fmt} parsing failed: {ex}")
                continue

            # A parseable but empty configuration is expected to return an empty dict.
            if not isinstance(conf, dict) or conf is None:
                logger.debug(
                    f"{fmt} parsing failed: expecting a dict, got {conf!r} instead."
                )
                continue

            logger.debug(f"{fmt} parsing successful, got {conf!r}.")
            yield conf

    def _search_pyproject_cwd_all(
        self,
    ) -> Iterable[tuple[Path, dict[str, Any]]]:
        """Yield every `pyproject.toml` from CWD upward, deepest first.

        Mimics the discovery behavior of uv, ruff, and mypy: start in the
        current working directory and walk up to the VCS root (or filesystem
        root), yielding each `pyproject.toml` containing a
        `[tool.<cli_name>]` section as a `(path, parsed_document)` pair.

        A `pyproject.toml` without a `[tool.<cli_name>]` section is
        skipped so unrelated project configs (like a dotfiles repo's
        `[tool.ruff]`) do not shadow the user's app-dir config.

        Only runs when `ConfigFormat.PYPROJECT_TOML` is in
        `file_format_patterns`. Yields nothing when no valid
        `pyproject.toml` is found.
        """
        cwd = Path.cwd()
        stop_at = self._resolve_stop_at(cwd)

        cli_name = get_current_context().find_root().info_name

        for directory in (cwd, *cwd.parents):
            if self._should_stop_walking(directory, stop_at):
                logger.debug(f"pyproject.toml CWD search stopped at {directory}.")
                break

            candidate = directory / "pyproject.toml"
            if not candidate.is_file():
                continue

            logger.debug(f"Found {candidate}, parsing as pyproject.toml.")
            try:
                content = candidate.read_text(encoding="utf-8")
            except OSError as ex:
                logger.debug(f"Cannot read {candidate}: {ex}")
                continue

            for conf in self.parse_conf(
                content, formats=(ConfigFormat.PYPROJECT_TOML,)
            ):
                if conf and cli_name in conf:
                    yield candidate, conf
                    break
            else:
                logger.debug(f"{candidate} has no [tool.{cli_name}] section; skipping.")

    def _search_pyproject_cwd(
        self,
    ) -> tuple[Path, dict[str, Any]] | tuple[None, None]:
        """Return the nearest `pyproject.toml` from CWD upward, if any.

        Thin wrapper over {meth}`_search_pyproject_cwd_all` keeping the
        single-file discovery contract: the deepest `pyproject.toml` with a
        `[tool.<cli_name>]` section wins, matching the behavior of uv, ruff
        and mypy. Returns `(None, None)` when no valid `pyproject.toml` is
        found.
        """
        for location, conf in self._search_pyproject_cwd_all():
            return location, conf
        return None, None

    def read_and_parse_all_conf(
        self,
        pattern: str,
    ) -> Iterable[tuple[Path | URL, dict[str, Any]]]:
        """Search for every parseable configuration file matching `pattern`.

        Yields `(location, parsed_conf)` pairs in discovery order, which is
        the most local first: the original search location, then each parent
        directory when parent search is enabled. Files already yielded (as
        matched by their resolved location) are skipped, as are files that
        parse to an empty configuration.

        Raises `FileNotFoundError` if no file at all matched the pattern.
        """
        seen: set[str] = set()

        for location, content, media_type in self.search_and_read_file(pattern):
            if str(location) in seen:
                logger.debug(f"Skipping duplicate {location}.")
                continue
            seen.add(str(location))

            conf = self._parse_one_conf(location, content, media_type)
            if conf is None:
                logger.debug(f"No parseable configuration in {location}.")
                continue

            yield location, conf

    def _parse_one_conf(
        self,
        location: Path | URL,
        content: str,
        media_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Parse a single file's `content` into a configuration dict.

        Candidate formats come from two sources, and are tried in order until
        one returns a non-empty structure:

        1. `media_type`, the `Content-Type` a server advertised for a downloaded
           configuration. It leads, because a URL is free to carry no file
           extension at all, or one that says nothing about the payload.
        2. The file name, matched against `file_format_patterns`.

        The two are layered rather than exclusive, so a server advertising a
        generic or plain wrong type costs nothing: the name-derived formats are
        still tried behind it. A media type never widens the format set either,
        as it is resolved against `file_format_patterns` alone.

        Returns `None` when the file matches no format or no parse attempt
        produces a non-empty structure.
        """
        if isinstance(location, URL):
            filename = location.path_parts[-1]
        else:
            filename = location.name

        # Match file with formats.
        matching_formats = tuple(
            fmt
            for fmt, patterns in self.file_format_patterns.items()
            if fnmatch.fnmatch(filename, patterns, flags=self.file_pattern_flags)
        )

        # Type a download from the media type its server advertised, and try
        # that format first. Iterating the mapping yields the formats the option
        # accepts, in their declared priority order.
        if media_type:
            mime_format = format_from_mime(media_type, self.file_format_patterns)
            if mime_format:
                logger.debug(f"{media_type} advertised by {location} is {mime_format}.")
                matching_formats = (
                    mime_format,
                    *(fmt for fmt in matching_formats if fmt is not mime_format),
                )

        # PYPROJECT_TOML is a specialization of TOML that unwraps [tool].
        # When both match, drop generic TOML so [tool] unwrapping takes effect.
        if (
            ConfigFormat.PYPROJECT_TOML in matching_formats
            and ConfigFormat.TOML in matching_formats
        ):
            matching_formats = tuple(
                f for f in matching_formats if f is not ConfigFormat.TOML
            )

        if not matching_formats:
            logger.debug(f"{location} does not match {self.file_pattern}.")
            return None

        logger.debug(f"Parsing {location} with {','.join(map(str, matching_formats))}")
        for conf in self.parse_conf(
            content, formats=matching_formats, location=location
        ):
            if conf:
                return conf
            logger.debug("Empty configuration, try next format.")

        return None

    def read_and_parse_conf(
        self,
        pattern: str,
    ) -> tuple[Path | URL, dict[str, Any]] | tuple[None, None]:
        """Search for a parseable configuration file.

        Returns the location and data structure of the first configuration matching the
        `pattern`.

        Only return the first match that:

        - exists,
        - is a file,
        - is not empty,
        - match file format patterns,
        - can be parsed successfully, and
        - produce a non-empty data structure.

        Raises `FileNotFoundError` if no configuration file was found matching the
        criteria above.

        Returns `(None, None)` if files were found but none could be parsed.
        """
        for location, conf in self.read_and_parse_all_conf(pattern):
            return location, conf
        return None, None

    def load_ini_config(self, content: str) -> dict[str, Any]:
        """Utility method to parse INI configuration file.

        Internal convention is to use a dot (`.`, as set by
        {data}`~click_extra.parameters.PARAM_PATH_SEP`) in section IDs as a
        separator between levels. This is a workaround the limitation of `INI`
        format which doesn't allow for sub-sections.

        Returns a ready-to-use data structure.
        """
        ini_config = ConfigParser(interpolation=ExtendedInterpolation())
        ini_config.read_string(content)

        conf: dict[str, Any] = {}
        for section_id in ini_config.sections():
            # Extract all options of the section.
            sub_conf = {}
            for option_id in ini_config.options(section_id):
                # Fetch the expected type of the CLI parameter.
                try:
                    target_params = self.get_tree_value(
                        self.params_objects, section_id, option_id
                    )
                # The item in the INI config file does not correspond to any existing
                # parameter in the CLI structure.
                except KeyError:
                    target_type = None
                # The item in the INI config file corresponds to a single parameter
                # in the CLI structure.
                else:
                    # Because one variable name can be shared by multiple options, we
                    # need to fetch all of those we detected in the CLI structure.
                    assert isinstance(target_params, list)
                    # We deduplicate them to simplify the next steps. If we are lucky,
                    # all options sharing the same name also share the same type.
                    target_types = [self.get_param_type(p) for p in target_params]
                    dedup_types = set(target_types)

                    # XXX This case is tricky and not even covered in Click unittests.
                    if len(dedup_types) > 1:
                        raise ValueError(
                            f"Cannot handle the {target_types!r} types defined by the "
                            "multiple options associated to the "
                            f"[{section_id}]:{option_id} INI config item."
                        )
                    target_type = dedup_types.pop()

                value: Any

                if target_type in (None, str):
                    value = ini_config.get(section_id, option_id)

                elif target_type is int:
                    value = ini_config.getint(section_id, option_id)

                elif target_type is float:
                    value = ini_config.getfloat(section_id, option_id)

                elif target_type is bool:
                    value = ini_config.getboolean(section_id, option_id)

                # Types not natively supported by INI format are loaded as
                # JSON-serialized strings.
                elif target_type in (list, tuple, set, frozenset, dict):
                    value = json.loads(ini_config.get(section_id, option_id))

                else:
                    raise ValueError(
                        f"Cannot handle the conversion of [{section_id}]:{option_id} "
                        f"INI config item to {target_type} type."
                    )

                sub_conf[option_id] = value

            # Place collected options at the right level of the dict tree.
            conf = always_merger.merge(
                conf,
                self.init_tree_dict(*section_id.split(PARAM_PATH_SEP), leaf=sub_conf),
            )

        return conf

    def load_argfile_config(self, content: str) -> dict[str, Any]:
        """Utility method to parse a plain-text argfile configuration file.

        The file holds command-line tokens, one option per line, in the style of
        `mpv`'s and `yt-dlp`'s configuration files:

        ```{code-block} text
        # Comments start with a hash sign.
        --option-name some value
        --flag
        ```

        Tokens are split with {func}`shlex.split`, so shell quoting rules apply
        and a `#` starts a comment. Each option is matched against the CLI's
        root-level parameter declarations, and its value is converted to the
        parameter's Python type, like {meth}`load_ini_config` does. A boolean
        flag needs no value: its primary declaration sets it to `True`, its
        secondary one (`--no-*`) to `False`. An option flagged `multiple`
        accumulates one list item per occurrence. Unknown options are kept
        under a normalized key so the strict check can reject them like any
        other unrecognized configuration key, while positional tokens are
        skipped; subcommand options cannot be addressed from an argfile.

        Returns a ready-to-use data structure, wrapped in the app's section
        name like the `[my-cli]` section of the other formats.

        :raises ValueError: the content cannot be tokenized, or an option is
            missing its value.
        """
        tokens = shlex.split(content, comments=True)

        # Map each option declaration, primary and secondary, to its parameter.
        # Only root-level options are reachable from an argfile: subcommand
        # subtrees of the parameter structure are skipped.
        app_name = self._app_section_name(get_current_context())
        root_params = self.params_objects.get(app_name, {})
        primary_decls: dict[str, click.Parameter] = {}
        secondary_decls: dict[str, click.Parameter] = {}
        for leaf in root_params.values():
            if not isinstance(leaf, list):
                continue
            for param in leaf:
                for decl in getattr(param, "opts", ()):
                    primary_decls[decl] = param
                for decl in getattr(param, "secondary_opts", ()):
                    secondary_decls[decl] = param

        def store(param: click.Parameter, value: Any) -> None:
            assert param.name is not None
            if param.multiple:
                conf.setdefault(param.name, []).append(value)
            else:
                conf[param.name] = value

        def convert(param: click.Parameter, decl: str, raw_value: str) -> Any:
            target_type = (
                ParamStructure.map_click_type(param.type)
                if param.multiple
                else self.get_param_type(param)
            )
            try:
                if target_type is bool:
                    # Mirror configparser's getboolean() accepted spellings.
                    lowered = raw_value.strip().lower()
                    if lowered in ("1", "yes", "true", "on"):
                        return True
                    if lowered in ("0", "no", "false", "off"):
                        return False
                    raise ValueError(f"not a boolean: {raw_value!r}")
                if target_type is int:
                    return int(raw_value)
                if target_type is float:
                    return float(raw_value)
                if target_type in (list, tuple, set, frozenset, dict):
                    return json.loads(raw_value)
                if target_type in (None, str):
                    return raw_value
            except (ValueError, json.JSONDecodeError) as ex:
                raise ValueError(
                    f"Cannot convert {decl} value {raw_value!r} to {target_type} type."
                ) from ex
            raise ValueError(
                f"Cannot handle the conversion of {decl} value {raw_value!r} "
                f"to {target_type} type."
            )

        conf: dict[str, Any] = {}
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1

            # Positional arguments and subcommand names have no place in an
            # argfile: the structureless format cannot address them.
            if not token.startswith("-"):
                logger.debug(f"Skip positional token {token!r}: not supported.")
                continue

            decl, _, inline_value = token.partition("=")

            # A secondary declaration (--no-*) unambiguously sets its boolean
            # flag to False and never consumes a value.
            param = secondary_decls.get(decl)
            if param is not None:
                store(param, False)
                continue

            param = primary_decls.get(decl)
            if param is None:
                # Keep the unknown entry under its normalized key so the strict
                # check rejects it with the standard error message, instead of
                # failing the whole parse. Splitting the prefix and folding are
                # exactly what Click does to name a parameter from a
                # declaration, so `--Foo-Bar` is reported as `foo_bar`.
                key = canonical_param_name(_split_opt(decl)[1])
                value: Any = True
                if index < len(tokens) and not tokens[index].startswith("-"):
                    value = tokens[index]
                    index += 1
                conf[key] = value
                logger.debug(f"Unknown option {decl!r} kept as {key!r}.")
                continue

            # Flags carry their value in the declaration itself, which
            # {func}`~click_extra.parameters.resolve_flag_value` reads the same
            # way on every Click line. Reading `flag_value` directly stores the
            # UNSET sentinel under Click's development branch, and a boolean
            # flag set from an argfile then comes back off.
            if getattr(param, "is_flag", False):
                flag_value = resolve_flag_value(param)
                store(param, True if flag_value is None else flag_value)
                continue

            if "=" in token:
                raw_value = inline_value
            elif index < len(tokens):
                raw_value = tokens[index]
                index += 1
            else:
                raise ValueError(f"Option {decl} is missing its value.")
            store(param, convert(param, decl, raw_value))

        if not conf:
            return conf
        return {app_name: conf} if app_name else conf

    def load_sqlite_config(self, path: Path) -> dict[str, Any]:
        """Utility method to parse a SQLite configuration database.

        The database holds a single {data}`~click_extra.config.formats.SQLITE_CONFIG_TABLE`
        table of `key`/`value` rows. Keys are parameter paths, with a dot
        (`.`, as set by {data}`~click_extra.parameters.PARAM_PATH_SEP`)
        separating each level, like `my-cli.default.int_param`. Values are
        JSON-encoded, which carries every type the other formats do:
        booleans, numbers, strings, lists and nested objects alike.

        Returns a ready-to-use data structure.

        ```{note}
        {mod}`sqlite3` is imported here and not at the top of the module, like
        the optional parsers of
        {func}`~click_extra.config.formats.parse_content`. A distribution can
        ship a Python without the SQLite bindings, and an unconditional import
        would then break every CLI at import time.
        {data}`~click_extra.config.formats.SQLITE_SUPPORT` reports whether they
        are there, and disables the format if they are not.
        ```
        """
        import sqlite3

        connection = sqlite3.connect(str(path))
        try:
            rows = connection.execute(
                f"SELECT key, value FROM {SQLITE_CONFIG_TABLE}"
            ).fetchall()
        finally:
            connection.close()

        conf: dict[str, Any] = {}
        for key, raw_value in rows:
            conf = always_merger.merge(
                conf,
                self.init_tree_dict(
                    *key.split(PARAM_PATH_SEP), leaf=json.loads(raw_value)
                ),
            )

        return conf

    def load_plist_config(self, path: Path) -> dict[str, Any]:
        """Utility method to parse a `plist` configuration file.

        The file is read as raw bytes and handed to the standard library's
        {mod}`plistlib`, which transparently decodes both the XML and the
        binary variants of the format. The XML variant also parses from a
        text payload through
        {func}`~click_extra.config.formats.parse_content`, which is how a
        `plist` fetched over `http://` or `https://` is loaded.

        Returns a ready-to-use data structure.
        """
        conf: dict[str, Any] = plistlib.loads(path.read_bytes())
        return conf

    def _app_section_name(self, ctx: click.Context) -> str:
        """Return the app section name used for both schema processing and opaque
        path resolution.

        Matches the name resolution logic in :py:meth:`_apply_config_schema`:
        prefers the root command's name, falls back to `ctx.info_name`, and
        defaults to empty string for fully-defensive callers.
        """
        return ctx.find_root().command.name or ctx.info_name or ""

    def _app_section(
        self,
        ctx: click.Context,
        user_conf: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Return `(app_name, app_section)` for the current context.

        Convenience pair that bundles :py:meth:`_app_section_name` and
        :py:meth:`_resolve_app_section`. Used by every callback that operates
        on the app's slice of the parsed config (schema processing, validator
        dispatch, theme-override extraction).
        """
        app_name = self._app_section_name(ctx)
        return app_name, self._resolve_app_section(user_conf, app_name)

    def _strip_opaque_from_conf(
        self,
        ctx: click.Context,
        normalized_conf: dict[str, Any],
    ) -> dict[str, Any]:
        """Remove opaque sub-trees from a normalized config before strict-check.

        Opaque paths are relative to the app's section, so they are prefixed with
        the app name when stripping. Returns `normalized_conf` unchanged if no
        opaque paths are declared, so the helper is safe to call unconditionally.
        """
        if not self._opaque_paths:
            return normalized_conf
        app_name = self._app_section_name(ctx)
        prefixed_paths = (
            f"{app_name}.{path}" if app_name else path for path in self._opaque_paths
        )
        return _strip_opaque_subtrees(normalized_conf, prefixed_paths)

    def _resolve_app_section(
        self,
        conf: dict[str, Any],
        app_name: str,
    ) -> dict[str, Any]:
        """Extract the app's configuration section from the parsed config.

        Thin instance-bound wrapper around :py:func:`_select_app_section` that
        supplies this option's :py:attr:`fallback_sections`.
        """
        return _select_app_section(conf, app_name, self.fallback_sections)

    def _apply_config_schema(
        self,
        ctx: click.Context,
        user_conf: dict[str, Any],
    ) -> None:
        """Apply the config schema to the app's section and store the result.

        Extracts the app-specific section from the full parsed config, passes
        it through the schema callable, and stores the result in
        `ctx.meta[click_extra.context.TOOL_CONFIG]`.
        """
        if self._config_schema_callable is None:
            return
        _, app_section = self._app_section(ctx, user_conf)
        context.set(ctx, context.TOOL_CONFIG, self._config_schema_callable(app_section))

    def _apply_theme_overrides(
        self,
        ctx: click.Context,
        user_conf: dict[str, Any],
    ) -> None:
        """Build per-invocation theme overrides from the config and stash on `ctx.meta`.

        Reads the `[tool.<cli>.themes.<name>]` sub-tree, builds each entry into
        a {class}`HelpTheme <click_extra.theme.HelpTheme>` (cascading
        on top of an existing built-in theme when *name* matches one already in
        {data}`~click_extra.theme.theme_registry`), and writes the result to
        `ctx.meta[click_extra.context.THEME_OVERRIDES]`. The module-level
        registry is never mutated, so themes defined here apply to the current
        invocation only.

        Validation already happened via the built-in
        {func}`~click_extra.theme.validate_themes_config` validator, so failures
        below this point would be a click-extra bug rather than user error.
        """
        # Lazy-imported to avoid the load-time config-theme cycle, like
        # _builtin_config_validators in click_extra.config.builtin.
        from ..theme import themes_from_config

        _, app_section = self._app_section(ctx, user_conf)
        themes_subtree = app_section.get(THEMES_CONFIG_KEY)
        if not isinstance(themes_subtree, dict) or not themes_subtree:
            return
        overrides = themes_from_config(themes_subtree)
        if overrides:
            context.set(ctx, context.THEME_OVERRIDES, overrides)

    def merge_default_map(self, ctx: click.Context, user_conf: dict) -> None:
        """Save the user configuration into the context's `default_map`.

        Merge the user configuration into the pre-computed template structure, which
        filters out all unrecognized options not supported by the command, then hand
        the result to :py:meth:`_install_default_map`.

        Opaque sub-trees declared by the schema or by registered
        {class}`~click_extra.config.schema.ConfigValidator` instances are stripped from the conf before the
        CLI-parameter strict check, so user-controlled keys (like mappings whose
        keys are data, not flag names) don't trip `strict=True`.

        ```{note}
        This recomputes the filtered config that
        :py:func:`~click_extra.config.schema.run_config_validation` already
        produces as
        :py:attr:`~click_extra.config.schema.ValidationReport.merged_conf`.
        :py:meth:`load_conf` installs that result directly and skips this
        method; it stays as the standalone entry point for external callers.
        ```
        """
        normalized_conf = _normalize_conf(user_conf, strict=self.strict)
        normalized_conf = self._strip_opaque_from_conf(ctx, normalized_conf)
        # Scope the merge (and its strict check) to the app's own section, so
        # foreign sections in a shared file are ignored and legacy fallback
        # sections are honored.
        app_name = self._app_section_name(ctx)
        scoped_conf = (
            _scope_app_sections(normalized_conf, app_name, self.fallback_sections)
            if app_name
            else normalized_conf
        )
        filtered_conf = _merge_into_template(
            copy.deepcopy(self.params_template),
            scoped_conf,
            self.strict,
            blocked=self.excluded_params,
        )
        self._install_default_map(ctx, filtered_conf)

    def _apply_cascaded_conf(
        self,
        ctx: click.Context,
        layers: Sequence[tuple[Path | URL, dict[str, Any]]],
    ) -> dict[str, Any]:
        """Validate and install multiple config layers into `default_map`.

        *layers* holds `(location, parsed_conf)` pairs in precedence order,
        highest first. Each file is strict-checked individually so any error
        names the file it comes from, then installed as its own
        `~collections.ChainMap` layer, lowest precedence first so the
        highest-precedence file ends up in front.

        The dataclass schema and extension validators run once on the
        deep-merged view of all layers, where they see one coherent document.
        That merged view is returned, for publication in
        `ctx.meta[click_extra.context.CONF_FULL]`.
        """
        app_name = self._app_section_name(ctx)

        # Strict-check each file against the CLI-parameter template.
        per_file_conf = []
        for location, conf in layers:
            report = run_config_validation(
                conf,
                app_name=app_name,
                params_template=self.params_template,
                fallback_sections=self.fallback_sections,
                strict=self.strict,
                blocked_params=self.excluded_params,
                collect_all=False,
            )
            if not report.ok:
                logger.critical(
                    f"Configuration validation error in {location}: {report.errors[0]}"
                )
                ctx.exit(1)
            assert report.merged_conf is not None  # params_template is always set.
            per_file_conf.append(report.merged_conf)

        # Deep-merge the raw documents, highest-precedence layer winning, for
        # the schema and the extension validators. Merging starts from the
        # lowest-precedence file so each later merge overwrites it.
        merged_view: dict[str, Any] = {}
        for _location, conf in reversed(layers):
            merged_view = always_merger.merge(merged_view, copy.deepcopy(conf))

        report = run_config_validation(
            merged_view,
            app_name=app_name,
            params_template=None,
            config_schema=self.config_schema,
            config_validators=self.config_validators,
            fallback_sections=self.fallback_sections,
            schema_strict=self.schema_strict,
            schema_warn_unknown=self.schema_warn_unknown,
            strict=self.strict,
            collect_all=False,
        )
        if not report.ok:
            logger.critical(f"Configuration validation error: {report.errors[0]}")
            ctx.exit(1)

        # Install one default_map layer per file, lowest precedence first.
        for merged_conf in reversed(per_file_conf):
            self._install_default_map(ctx, merged_conf)
        logger.debug(f"New defaults: {ctx.default_map}")

        if self._config_schema_callable is not None:
            context.set(ctx, context.TOOL_CONFIG, report.schema_instance)
        self._apply_theme_overrides(ctx, merged_view)
        return merged_view

    def _install_default_map(
        self, ctx: click.Context, filtered_conf: dict[str, Any]
    ) -> None:
        """Layer a template-filtered config onto the context's `default_map`.

        Cleans up the blank values left over by the template structure, then layers
        the app's section on top of any existing `default_map` via a
        `~collections.ChainMap` so each config source keeps its own layer. The first
        layer wins on key lookup, which makes parameter-source precedence explicit
        and future-proofs for multi-file config loading.
        """
        # Clean-up the conf by removing all blank values left-over by the template
        # structure.
        clean_conf = _remove_blanks(filtered_conf, remove_str=False)

        # Layer the config values on top of any existing default_map via ChainMap.
        # Click only calls .get() on default_map, which ChainMap supports with
        # first-match-wins semantics.
        local_conf = clean_conf.get(ctx.find_root().command.name, {})
        ctx.default_map = ChainMap(local_conf, ctx.default_map or {})

    def load_conf(
        self,
        ctx: click.Context,
        param: click.Parameter,
        path_pattern: str | Path | Literal[Sentinel.NO_CONFIG],
    ) -> None:
        """Fetch parameter values from a configuration file and set them as defaults.

        User configuration is merged to the [context's default_map](https://click.palletsprojects.com/en/stable/commands/#overriding-defaults),
        [like Click does](https://click.palletsprojects.com/en/stable/commands/#context-defaults).

        By relying on Click's `default_map`, we make sure that precedence is
        respected. Direct CLI parameters, environment variables or interactive prompts
        take precedence over any values from the config file.

        ```{hint}
        Once loading is complete, the resolved file path and its full parsed content
        are stored in `ctx.meta[click_extra.context.CONF_SOURCE]` and
        `ctx.meta[click_extra.context.CONF_FULL]` respectively. This is the
        recommended way to identify which configuration file was loaded.

        We intentionally do not
        add a custom `ParameterSource.CONFIG_FILE` enum member: `ParameterSource`
        is a closed enum in Click, and monkeypatching it would be fragile. Besides,
        config values end up in `default_map`, so Click already reports them as
        `ParameterSource.DEFAULT_MAP`, which is accurate.
        ```
        """
        # Skip file I/O and ctx.meta writes during help rendering, shell
        # completion, and any `make_context(resilient_parsing=True)` path.
        if ctx.resilient_parsing:
            return

        # In this function we would like to inform the user of what we're doing.
        # In theory we could use logger.info() for that, but the logger is stuck to its
        # default WARNING level at this point, because the defaults have not been
        # loaded yet. So we use echo() to print messages to stderr instead.
        info_msg = partial(echo, err=True)

        assert self.name is not None  # Always set for Option subclasses.

        # Listed explicitly: the ParameterSource IntEnum ordering does not
        # cleanly split explicit from non-explicit sources, since DEFAULT and
        # DEFAULT_MAP fall between the user-set members.
        explicit_sources = {
            ParameterSource.COMMANDLINE,
            ParameterSource.ENVIRONMENT,
            ParameterSource.PROMPT,
        }

        if path_pattern is NO_CONFIG:
            logger.debug(f"{NO_CONFIG} received.")
            source = ctx.get_parameter_source(self.name)
            explicit = source is not None and source in explicit_sources
            if explicit:
                info_msg("Skip configuration file loading altogether.")
            else:
                logger.debug("Configuration file autodiscovery disabled by default.")
            return

        conf_source = ctx.get_parameter_source(self.name)
        explicit_conf = conf_source is not None and conf_source in explicit_sources

        # Print configuration location to the user if it was explicitly set.
        # Normalize to string to both allow parsing as a glob pattern or URL.
        if isinstance(path_pattern, Path):
            # Normalize the path without checking for its existence.
            path_pattern = str(path_pattern.resolve(strict=False))
        # NO_CONFIG was handled above with an early return. Help mypy see that.
        assert isinstance(path_pattern, str)
        message = f"Load configuration matching {path_pattern}"
        if explicit_conf:
            info_msg(message)
        else:
            logger.debug(message)

        # Discover configuration layers, in precedence order (highest first).
        # A pyproject.toml found near the CWD beats the app-dir search, which
        # itself yields the most local file first.
        conf_path: Path | URL | None = None
        user_conf: dict[str, Any] | None = None
        layers: list[tuple[Path | URL, dict[str, Any]]] = []
        if (
            not explicit_conf
            and ConfigFormat.PYPROJECT_TOML in self.file_format_patterns
        ):
            if self.cascade:
                layers.extend(self._search_pyproject_cwd_all())
            else:
                pyproject_result = self._search_pyproject_cwd()
                if pyproject_result[0] is not None:
                    layers.append(pyproject_result)
            if layers:
                logger.debug(f"Using {layers[0][0]} from CWD search.")

        # Extend the cascade with the app-dir search layers, or fall back
        # to it entirely when the CWD search found nothing. An explicit
        # --config never cascades: it pins a single source.
        try:
            if self.cascade and not explicit_conf:
                found = {str(location) for location, _ in layers}
                layers.extend(
                    layer
                    for layer in self.read_and_parse_all_conf(path_pattern)
                    if str(layer[0]) not in found
                )
            elif not layers:
                result = self.read_and_parse_conf(path_pattern)
                if result[0] is not None:
                    layers.append(result)
        # Exit the CLI if no user-provided config file was found. Else, it
        # means we were just trying to automatically discover a config file
        # with the default pattern, so we can just log it and continue.
        except FileNotFoundError:
            if not layers:
                message = "No configuration file found."
                if explicit_conf:
                    logger.critical(message)
                    ctx.exit(2)
                else:
                    logger.debug(message)
        else:
            if not layers:
                formats = _join_format_labels(self.file_format_patterns)
                message = f"Error parsing file as {formats}."
                if explicit_conf:
                    logger.critical(message)
                    ctx.exit(2)
                else:
                    logger.debug(message)

        # Apply the loaded configuration (from CWD and/or app-dir search).
        if layers:
            # The winning source, and the document `ctx.meta` exposes. The
            # cascade replaces the latter with the deep-merged view below.
            conf_path, user_conf = layers[0]
            if len(layers) > 1:
                assert self.cascade
                user_conf = self._apply_cascaded_conf(ctx, layers)
            else:
                logger.debug(f"Parsed user configuration: {user_conf}")
                logger.debug(f"Initial defaults: {ctx.default_map}")

                # Run every check through the unified pipeline. collect_all=False
                # fails fast: the first error is surfaced as a clean critical-level
                # log and the context exits 1, before any subcommand callback fires,
                # rather than letting an exception bubble up as a traceback. Exit
                # code 1 matches `--validate-config` for the same failure mode.
                report = run_config_validation(
                    user_conf,
                    app_name=self._app_section_name(ctx),
                    params_template=self.params_template,
                    config_schema=self.config_schema,
                    config_validators=self.config_validators,
                    fallback_sections=self.fallback_sections,
                    schema_strict=self.schema_strict,
                    schema_warn_unknown=self.schema_warn_unknown,
                    strict=self.strict,
                    blocked_params=self.excluded_params,
                    collect_all=False,
                )
                if not report.ok:
                    logger.critical(
                        f"Configuration validation error: {report.errors[0]}"
                    )
                    ctx.exit(1)

                # Validation passed. Install the recognized values into default_map,
                # publish the typed schema instance built by the pipeline, then apply
                # theme overrides (the [tool.<cli>.themes.<name>] table was already
                # validated above, so building it here cannot surface user error).
                # The pipeline already filtered user_conf against the template, so the
                # merged result is installed directly instead of recomputing it via
                # merge_default_map.
                assert report.merged_conf is not None  # params_template is always set.
                self._install_default_map(ctx, report.merged_conf)
                logger.debug(f"New defaults: {ctx.default_map}")
                if self._config_schema_callable is not None:
                    context.set(ctx, context.TOOL_CONFIG, report.schema_instance)
                self._apply_theme_overrides(ctx, user_conf)

        # When a schema is configured but no config file was found, still
        # produce the default instance so get_tool_config() never returns None.
        elif self._config_schema_callable is not None:
            logger.debug("No config file found; instantiating schema defaults.")
            self._apply_config_schema(ctx, {})

        # Expose the resolved config file path and its full parsed content via
        # ctx.meta, so downstream CLI code can inspect what was loaded and from where.
        # See the load_conf docstring for why we use ctx.meta instead of a custom
        # ParameterSource enum member.
        context.set(ctx, context.CONF_SOURCE, conf_path)
        context.set(ctx, context.CONF_FULL, user_conf)
        context.set(ctx, context.CONF_SOURCES, tuple(layers))


class NoConfigOption(ExtraOption):
    """A pre-configured option adding `--no-config`.

    This option is supposed to be used alongside the `--config` option
    (`ConfigOption`) to allow users to explicitly disable the use of any
    configuration file.

    This is especially useful to debug side-effects caused by autodetection of
    configuration files.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        help=_(
            "Ignore all configuration files and only use command line parameters and "
            "environment variables.",
        ),
        is_flag=True,
        flag_value=NO_CONFIG,
        is_eager=True,
        expose_value=False,
        **kwargs,
    ) -> None:
        """`flag_value=NO_CONFIG` is the `Sentinel` enum member that
        signals "skip configuration loading" to {class}`ConfigOption`. Click
        `8.4.0` (PR [pallets/click#3363](https://github.com/pallets/click/pull/3363)) auto-detects
        `type=UNPROCESSED` for non-basic `flag_value` types, so the sentinel
        passes through `Option` unchanged without an explicit `type` override.

        ```{seealso}
        An alternative implementation of this class would be to create a custom
        [click.ParamType](https://click.palletsprojects.com/en/stable/api/#click.ParamType)
        instead of a custom `Option` subclass. [Here is for example](https://github.com/pallets/click/issues/3024#issuecomment-3146511356).
        ```
        """
        if not param_decls:
            param_decls = ("--no-config", CONFIG_OPTION_NAME)

        kwargs.setdefault("callback", self.check_sibling_config_option)

        super().__init__(
            param_decls=param_decls,
            help=help,
            is_flag=is_flag,
            flag_value=flag_value,
            is_eager=is_eager,
            expose_value=expose_value,
            **kwargs,
        )

    def check_sibling_config_option(
        self, ctx: click.Context, param: click.Parameter, value: int
    ) -> None:
        """Ensure that this option is used alongside a `ConfigOption` instance."""
        require_sibling_param(ctx.command.params, param, ConfigOption)


class ValidateConfigOption(ExtraOption):
    """A pre-configured option adding `--validate-config LOCATION`.

    Loads the config file at the given location, validates it against the CLI's
    parameter structure in strict mode, reports results, and exits.

    ```{note}
    The value is left `UNPROCESSED` so it accepts everything
    {class}`ConfigOption` accepts: a file, a folder, a glob pattern, or an
    `http://` or `https://` URL. Both options hand their value to the same
    {meth}`ConfigOption.read_and_parse_conf`, so a configuration a CLI can
    load is a configuration it can also validate.
    ```
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        type: click.ParamType | Any = UNPROCESSED,
        metavar: str = "LOCATION",
        is_eager: bool = True,
        expose_value: bool = False,
        help: str = _("Validate the configuration file and exit."),
        **kwargs: Any,
    ) -> None:
        if not param_decls:
            param_decls = ("--validate-config",)

        kwargs.setdefault("callback", self.validate_config)

        super().__init__(
            param_decls=param_decls,
            type=type,
            metavar=metavar,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )

    def validate_config(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: str | None,
    ) -> None:
        """Load, parse, and validate the configuration file, then exit.

        Validation runs three checks in order, every one of them under the same
        {class}`~click_extra.config.schema.ValidationError` shape so the reported path is always rooted at
        the configuration file:

        1. CLI-parameter strict check on the non-opaque part of the document.
        2. Schema processing, if a `config_schema` is configured: catches
           type errors and unknown keys inside the dataclass-described section.
        3. Each registered {class}`~click_extra.config.schema.ConfigValidator` runs against its declared
           opaque sub-tree.

        Every detected error is emitted before exiting, so a single
        `--validate-config` run surfaces the full list of fixes the user
        needs to apply.
        """
        if not value:
            return

        info_msg: Callable[..., None] = partial(echo, err=True)

        # Find the sibling ConfigOption to reuse its parsing machinery.
        config_option = require_sibling_param(ctx.command.params, param, ConfigOption)

        # Read and parse the config file.
        try:
            _conf_path, user_conf = config_option.read_and_parse_conf(value)
        except FileNotFoundError:
            info_msg(f"Configuration file not found: {value}")
            ctx.exit(2)

        if user_conf is None:
            formats = _join_format_labels(config_option.file_format_patterns)
            info_msg(f"Error parsing {value} as {formats}.")
            ctx.exit(2)

        # Delegate every check to the unified pipeline in collect-all mode so a
        # single run surfaces the full punch list. `--validate-config` always
        # runs the CLI-parameter check in strict mode regardless of the sibling
        # option's `strict` setting; schema strictness honors the option's
        # configured `schema_strict`.
        report = run_config_validation(
            user_conf,
            app_name=config_option._app_section_name(ctx),
            params_template=config_option.params_template,
            config_schema=config_option.config_schema,
            config_validators=config_option.config_validators,
            fallback_sections=config_option.fallback_sections,
            schema_strict=config_option.schema_strict,
            strict=True,
            blocked_params=config_option.excluded_params,
            collect_all=True,
        )

        if not report.ok:
            for error in report.errors:
                info_msg(f"Configuration validation error: {error}")
            ctx.exit(1)

        info_msg(f"Configuration file {value} is valid.")
        ctx.exit(0)


_EXPORT_FORMAT_BY_TOKEN: dict[str, ConfigFormat] = {
    fmt.label.lower(): fmt for fmt in SERIALIZABLE_FORMATS
}
"""Mapping of `--export-config` choice tokens to their {class}`ConfigFormat`.

Built from {data}`~click_extra.config.formats.SERIALIZABLE_FORMATS`, so the
accepted tokens are exactly the formats
{func}`~click_extra.config.formats.serialize_content` can write: `toml`,
`yaml`, `json`, `json5`, `jsonc`, `hjson`, `xml` and `plist`.
"""


def ensure_config_loaded(ctx: click.Context) -> None:
    """Run the sibling {class}`ConfigOption`'s resolution if it has not run yet.

    Click processes eager parameters given on the command line before eager
    parameters left at their defaults, so an explicitly-passed introspection
    flag (`--params`, `--export-config`) fires before the `--config`
    option had a chance to discover and load the configuration file. The views
    those flags render would then miss the configuration layer entirely,
    showing defaults where the user's config applies.

    Idempotent: does nothing when the config option already resolved (its
    callback stamps {data}`~click_extra.context.CONF_SOURCE` on the context
    even when no file was found), when the command has no config option, or
    when the option carries no callback.
    """
    if context.get(ctx, context.CONF_SOURCE, UNSET) is not UNSET:
        return
    config_option = search_params(ctx.command.params, ConfigOption)
    if config_option is None:
        return
    assert isinstance(config_option, ConfigOption)
    if config_option.callback is None:
        return
    opts = replay_raw_args(ctx)
    value, source = config_option.consume_value(ctx, opts)
    if value is UNSET:
        return
    # Record the provenance so the callback's explicit-vs-discovery logic sees
    # the same source as it would under normal parameter processing.
    if config_option.name is not None and source is not None:
        ctx.set_parameter_source(config_option.name, source)
    config_option.callback(ctx, config_option, value)


def _serialize_toml_with_unset(tree: dict[str, Any]) -> str:
    """Render *tree* as TOML, emitting `None` leaves as commented-out keys.

    TOML has no null type, so parameters without a value cannot round-trip as
    real entries. Instead of dropping them from the export, each one is
    rendered as a `# key =` comment line: the generated file documents every
    key that can be set, while leaving the unset ones inert.

    Relies on `tomlkit` (the `[toml]` extra), like
    {func}`~click_extra.config.formats.serialize_content` does for TOML.

    :raises ImportError: when `tomlkit` is not installed.
    """
    import tomlkit

    def fill(container: Any, mapping: dict[str, Any]) -> None:
        for key, value in mapping.items():
            if isinstance(value, dict):
                table = tomlkit.table()
                fill(table, value)
                container[key] = table
            elif value is None:
                container.add(tomlkit.comment(f"{key} ="))
            else:
                container[key] = value

    doc = tomlkit.document()
    fill(doc, tree)
    return str(tomlkit.dumps(doc))


def _config_dump_value(param: click.Parameter, value: Any) -> Any:
    """Coerce a resolved parameter value into a config-serializable form.

    Produces what a user would write in a configuration file, so the dump
    round-trips back through `--config`:

    - native scalars (`str`, `int`, `float`, `bool`) and `None` pass
      through unchanged;
    - sequences are coerced element-wise into a `list`;
    - an {class}`~enum.Enum` member becomes its
      {class}`~click_extra.types.EnumChoice` token (or its value/name otherwise);
    - a scalar string whose parameter resolves to a numeric Python type is
      converted to that type, so `--count 7` dumps as `count = 7` rather than
      `count = "7"` (Click hands back raw strings for command-line and
      environment values, ahead of its own type conversion);
    - anything else (a {class}`~pathlib.Path`, a custom object) is stringified.
    """
    if value is None:
        # An unset multi-value parameter reads naturally as an empty list,
        # which also survives serialization in null-less formats like TOML.
        if ParamStructure.get_param_type(param) is list:
            return []
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_config_dump_value(param, item) for item in value]
    # bool is an int subclass: handle it before the numeric coercion below.
    if isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        param_type = getattr(param, "type", None)
        if isinstance(param_type, EnumChoice):
            return param_type.get_choice_string(value)
        member_value = value.value
        if isinstance(member_value, (str, int, float, bool)):
            return member_value
        return value.name
    if isinstance(value, str):
        python_type = ParamStructure.get_param_type(param)
        if python_type is int:
            try:
                return int(value)
            except ValueError:
                return value
        if python_type is float:
            try:
                return float(value)
            except ValueError:
                return value
        return value
    if isinstance(value, (int, float)):
        return value
    return str(value)


class ExportConfigOption(ExtraOption):
    """A pre-configured option adding `--export-config FORMAT`.

    Resolves the CLI's current parameter values following Click's precedence
    chain (command line, then environment variables, then configuration file,
    then defaults), renders them as a configuration file in the requested format
    on `<stdout>`, and exits.

    ```{hint}
    Combine the flag with other options or environment variables to capture
    them in the generated configuration. For example, ``mycli --verbosity
    DEBUG --export-config toml` emits a configuration whose `verbosity`` is
    already set to `DEBUG`.
    ```

    Like {class}`ValidateConfigOption`, it relies on a sibling
    {class}`ConfigOption` to provide the parameter structure and the
    `excluded_params` / `included_params` filter, so the export contains
    exactly the parameters that can be loaded back from a configuration file.

    ```{note}
    The accepted formats are those
    {func}`~click_extra.config.formats.serialize_content` can write
    ({data}`~click_extra.config.formats.SERIALIZABLE_FORMATS`). `INI`,
    `Argfile` and `pyproject.toml` have no serializer and cannot be dumped.
    ```
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        type: click.ParamType | Any = None,
        metavar: str = "FORMAT",
        is_eager: bool = True,
        expose_value: bool = False,
        help: str = _(
            "Export the configuration in the selected format to <stdout>, then exit.",
        ),
        **kwargs: Any,
    ) -> None:
        if not param_decls:
            param_decls = ("--export-config",)

        # Restrict the choice to the writable formats, addressed by their
        # lower-case token (`toml`, `json`, ...). A short `FORMAT` metavar
        # keeps the token list out of the one-line help while the full set still
        # surfaces in the Choice error message.
        if type is None:
            type = Choice(tuple(_EXPORT_FORMAT_BY_TOKEN), case_sensitive=False)

        kwargs.setdefault("callback", self.export_config)

        super().__init__(
            param_decls=param_decls,
            type=type,
            metavar=metavar,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )

    def build_config(
        self,
        ctx: click.Context,
        config_option: ConfigOption,
    ) -> dict[str, Any]:
        """Resolve every config-eligible parameter into a dumpable tree.

        Walks the sibling {class}`ConfigOption`'s parameter structure, resolves
        each parameter's effective value by replaying
        {data}`~click_extra.context.RAW_ARGS` (falling back to defaults when the
        command did not capture them), drops the
        {attr}`~click_extra.parameters.ParamStructure.excluded_params`, and
        layers the coerced values into the ``{cli-name: {param: value, ...}}``
        shape a configuration file uses. Parameter keys are rendered in their
        kebab-case spelling, the canonical presentation for configuration
        files; either spelling loads back to the same parameter.

        Parameters without a default are kept as `None` leaves so the export
        names every key a configuration file can set: serializers render them
        as `null`, except TOML which comments them out (see
        :py:func:`_serialize_toml_with_unset`). Loading `null` back is
        harmless: {meth}`ConfigOption._install_default_map` cleans blank
        values out of the merged result.
        """
        # Force the included_params -> excluded_params resolution that happens
        # the first time the parameter tree is built.
        config_option.params_objects  # noqa: B018
        excluded = config_option.excluded_params

        opts = replay_raw_args(ctx)
        has_raw_args = context.get(ctx, context.RAW_ARGS) is not None
        if not has_raw_args:
            logger.warning(
                f"Cannot resolve parameter values: {ctx.command} does not "
                "inherit from Command; dumping defaults.",
            )

        tree: dict[str, Any] = {}
        for keys, target in config_option.walk_params():
            if PARAM_PATH_SEP.join(keys) in excluded:
                continue
            if has_raw_args:
                raw, _source = target.consume_value(ctx, opts)
                resolved = None if raw is UNSET else raw
            else:
                resolved = target.get_default(ctx)
            leaf = _config_dump_value(target, resolved)
            # Render the option under its kebab-case spelling, the canonical
            # presentation for configuration files (matching the CLI flags and
            # the TOML/YAML convention). Loading normalizes either spelling
            # back to the parameter ID. Section keys (the CLI and subcommand
            # names) are kept verbatim: the app-section lookup matches the
            # root exactly, and command names are displayed as invoked.
            file_keys = (*keys[:-1], keys[-1].replace("_", "-"))
            tree = always_merger.merge(
                tree, ParamStructure.init_tree_dict(*file_keys, leaf=leaf)
            )

        return _remove_blanks(tree, remove_none=False, remove_str=False)

    def export_config(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: str | None,
    ) -> None:
        """Render the resolved configuration to `<stdout>` and exit."""
        # Stay dormant during help rendering and shell completion, like Click's
        # own eager callbacks, so a typed `--export-config FORMAT` does not
        # export and exit mid-completion.
        if not value or ctx.resilient_parsing:
            return

        # Load the configuration file first, so the export reflects the full
        # precedence chain the docstring promises (config file included) even
        # when this flag was processed ahead of the --config option.
        ensure_config_loaded(ctx)

        fmt = _EXPORT_FORMAT_BY_TOKEN[value.lower()]
        config_option = require_sibling_param(ctx.command.params, param, ConfigOption)
        tree = self.build_config(ctx, config_option)

        try:
            # TOML cannot hold nulls: unset parameters are commented out.
            if fmt is ConfigFormat.TOML:
                output = _serialize_toml_with_unset(tree)
            elif fmt is ConfigFormat.PLIST:
                # plist has no null type either, and plistlib raises on None
                # values: unset parameters are dropped from the export.
                output = serialize_content(fmt, _remove_blanks(tree, remove_str=False))
            else:
                output = serialize_content(fmt, tree)
        except ImportError:
            echo(disabled_format_message(fmt), err=True)
            ctx.exit(1)

        echo(output.rstrip("\n"))
        ctx.exit()
