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
The whole namespace designates configuration files by the short name `config`:
not `conf`, `cfg`, `configuration` or `settings`. In the context of a CLI,
`config` reads as nothing else.
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
import shlex
from collections import ChainMap
from enum import Enum
from functools import cache, cached_property, partial
from gettext import gettext as _
from itertools import islice
from pathlib import Path, PurePosixPath

import click
from click import (
    UNPROCESSED,
    echo,
    get_app_dir,
    get_current_context,
)
from click.core import ParameterSource
from click.parser import _split_opt

from .. import context
from .._utils import (
    deep_merge,
    flatten,
    parse_bool,
    remove_blanks,
    set_nested,
    shrinkuser,
)
from ..logging import LogLevel, requested_level
from ..param_tools import (
    PARAM_PATH_SEP,
    ParamStructure,
    canonical_param_name,
    require_sibling_param,
    resolve_flag_value,
)
from ..parameters import ExtraOption
from .discovery import _PATH_READ_FORMATS, ConfigDiscovery
from .formats import (
    SQLITE_CONFIG_TABLE,
    ConfigFormat,
    format_from_mime,
    format_from_path,
    parse_content,
)
from .schema import (
    ConfigValidator,
    ValidationError,
    ValidationReport,
    _build_merged_conf,
    _collect_opaque_paths,
    make_schema_callable,
    run_config_validation,
)
from .subcommands import _patch_group_parse_args, inject_reserved_subcommands

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from typing import Any, Literal, NoReturn

logger = logging.getLogger(__name__)


CONFIG_OPTION_NAME = "config"
"""Hardcoded name of the configuration option.

The `--config` and `--no-config` options share this name, so they compete with
each other to either set a path pattern or disable the use of any configuration file
at all.
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


THEMES_CONFIG_KEY: str = "themes"
"""Sub-key under `[tool.<cli>]` where user-defined themes live in config.

Used by {class}`~click_extra.config.option.ConfigOption` to find `[tool.<cli>.themes.<name>]` tables,
build them via {meth}`HelpTheme.from_dict
<click_extra.theme.HelpTheme.from_dict>`, and stash the result on
`ctx.meta[click_extra.context.THEME_OVERRIDES]`. The constant is the
single source of truth shared by `_builtin_config_validators`,
`ConfigOption._apply_theme_overrides`, and
{func}`click_extra.theme.themes_from_config`.
"""


_EXPLICIT_SOURCES = frozenset({
    ParameterSource.COMMANDLINE,
    ParameterSource.ENVIRONMENT,
    ParameterSource.PROMPT,
})
"""The parameter sources a user sets on purpose.

Listed outright: the {class}`~click.core.ParameterSource` ordering does not
split the explicit members from the rest, since `DEFAULT` and `DEFAULT_MAP`
fall between them.
"""

_JSON_ENCODED_TYPES = frozenset({list, tuple, set, frozenset, dict})
"""Parameter types a typeless format carries as JSON-serialized strings."""


class Sentinel(Enum):
    """Enum used to define sentinel values.

    ```{note}
    This reuses the pattern of `click._utils.Sentinel`.
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


class _EmptyConfigError(ValueError):
    """A file the user names parses, but holds no configuration.

    Like a TOML file of comments only, or an argfile naming no option. The message
    names the formats that parse it, which says how the file was read: a file of
    `key = value` lines named `*.conf` is read as an argfile, not as INI.
    """

    def __init__(self, location: Path | str, formats: Iterable[ConfigFormat]) -> None:
        super().__init__(
            f"{location} parses as {_join_format_labels(formats)} "
            "but holds no configuration."
        )


def _coerce_scalar(target_type: type | None, raw_value: str, subject: str) -> Any:
    """Convert text read from a typeless format to a parameter's Python type.

    An INI file and an argfile hold text only, so the parameter each entry
    feeds decides how its text is read: a `bool` takes the spellings
    {attr}`~configparser.ConfigParser.BOOLEAN_STATES` accepts (see
    {func}`~click_extra._utils.parse_bool`), a container is JSON-decoded, and an
    entry matching no parameter keeps its text.

    :param target_type: the parameter's Python type, or `None` when the entry
        matches no parameter.
    :param raw_value: the text to convert.
    :param subject: how an error message names the entry.
    :return: the converted value.
    :raises ValueError: when `target_type` has no conversion, or `raw_value`
        does not read as one.
    """
    if target_type is bool:
        state = parse_bool(raw_value)
        if state is None:
            raise ValueError(f"Cannot convert {subject} to {target_type} type.")
        return state
    try:
        if target_type in (None, str):
            return raw_value
        if target_type is int:
            return int(raw_value)
        if target_type is float:
            return float(raw_value)
        if target_type in _JSON_ENCODED_TYPES:
            return json.loads(raw_value)
    # A JSONDecodeError is a ValueError.
    except ValueError as ex:
        raise ValueError(f"Cannot convert {subject} to {target_type} type.") from ex
    raise ValueError(
        f"Cannot handle the conversion of {subject} to {target_type} type."
    )


def _exit_on_validation_error(
    ctx: click.Context,
    error: ValidationError,
    location: Path | str | None = None,
) -> NoReturn:
    """Log a validation error and exit the CLI with code `1`.

    The exit fires before any subcommand callback does, so the user reads one
    critical line rather than a traceback, and code `1` matches what
    `--validate-config` answers for the same failure.

    :param location: the file the error is about, named in the message when
        several were validated.
    """
    where = f" in {location}" if location is not None else ""
    logger.critical(f"Configuration validation error{where}: {error}")
    ctx.exit(1)


@cache
def _builtin_config_validators() -> tuple[ConfigValidator, ...]:
    """Return the validators click-extra registers on every {class}`~click_extra.config.option.ConfigOption`.

    A single validator, for `[tool.<cli>.themes.<name>]` tables. Built on the
    first call and shared by every option, as a validator is immutable.
    """
    # Deferred import: click_extra.theme and this package import each other.
    from ..theme import validate_themes_config

    return (
        ConfigValidator(
            extension_path=THEMES_CONFIG_KEY,
            validator=validate_themes_config,
            description=(
                "Validate user-defined and override themes declared under "
                "[tool.<cli>.themes.<name>]."
            ),
        ),
    )


class _DeepChainMap(ChainMap):
    """A `ChainMap` that also resolves the sections of its layers key by key.

    A plain `ChainMap` gives the value of the first layer holding a key. For a
    parameter of the root command, that is the most local value. For a subcommand
    section, Click then reads the whole section from that one layer, and the keys
    that a layer behind it sets in the same section are lost.

    Here, a key that several layers hold as a dictionary resolves to another
    `_DeepChainMap` over these dictionaries, front layer first, so the lookup
    goes on key by key at every depth. A value of another type, like a list,
    comes whole from one layer and hides the layers behind it: it is the result
    when it comes first, and ends the chain of sections otherwise. The values
    match what {func}`~click_extra._utils.deep_merge` builds from the same
    layers, merged back to front.
    """

    def __getitem__(self, key: str) -> Any:
        sections: list[dict[str, Any]] = []
        for mapping in self.maps:
            if key not in mapping:
                continue
            value = mapping[key]
            if not isinstance(value, dict):
                if sections:
                    break
                return value
            sections.append(value)
        if not sections:
            return self.__missing__(key)
        # A section held by one layer is that layer's own dictionary, as with a
        # plain ChainMap.
        if len(sections) == 1:
            return sections[0]
        return self.__class__(*sections)


class ConfigOption(ConfigDiscovery, ExtraOption, ParamStructure):
    """A pre-configured option adding `--config LOCATION`.

    ```{caution}
    The first `ConfigOption` a process builds replaces `click.Group.parse_args` for
    all of it. The replacement is how the subcommands the configuration names still
    run in the two cases the option never sees, on a group class click-extra does
    not own. One is a bare invocation, for which Click prints its `no_args_is_help`
    screen before it runs any parameter. The other is a subgroup, which holds no
    option of its own. Every other call goes to Click unchanged, as does each group
    of a CLI carrying no `ConfigOption`.
    ```
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
        metavar: str = "LOCATION",
        type: click.ParamType | Any = UNPROCESSED,
        help: str = _(
            "Location of the configuration file. Supports local path with glob patterns "
            "or remote URL.",
        ),
        is_eager: bool = True,
        expose_value: bool = False,
        file_format_patterns: dict[ConfigFormat, Sequence[str] | str]
        | Iterable[ConfigFormat]
        | ConfigFormat
        | None = None,
        file_pattern_flags: int | None = None,
        show_file_patterns: bool | None = None,
        roaming: bool = True,
        force_posix: bool = False,
        search_pattern_flags: int | None = None,
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
        **kwargs: Any,
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

        match file_format_patterns:
            case None:
                self.file_format_patterns = {fmt: fmt.patterns for fmt in ConfigFormat}
            case ConfigFormat():
                self.file_format_patterns = {
                    file_format_patterns: file_format_patterns.patterns
                }
            case dict():
                self.file_format_patterns = {
                    fmt: (patterns,) if isinstance(patterns, str) else tuple(patterns)
                    for fmt, patterns in file_format_patterns.items()
                }
            case _:
                self.file_format_patterns = {
                    fmt: fmt.patterns for fmt in file_format_patterns
                }

        self.auto_file_formats = file_format_patterns is None
        """Whether the format set was inherited instead of chosen by the developer.

        `True` when no `file_format_patterns` was provided, so the set is whatever the
        installed {ref}`extra dependencies <extra-dependencies>` enable. It ranges
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

        # Validated and defaulted on first use by the `file_pattern_flags`
        # property, which is what keeps wcmatch out of every CLI's startup.
        self._file_pattern_flags = file_pattern_flags

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

        # Validated and defaulted on first use by the `search_pattern_flags`
        # property, for the same reason as the file pattern flags above.
        self._search_pattern_flags = search_pattern_flags

        self.search_parents = search_parents
        """Indicates whether to walk back the tree of parent folders when searching for
        configuration files.
        """

        self.stop_at = stop_at
        """Boundary for parent directory walking.

        - `None`: walk up to filesystem root.
        - `VCS`: stop at the nearest VCS root, whichever system marks it (see
          {data}`~click_extra.config.discovery.VCS_DIRS`) (default).
        - A `Path` or `str`: stop at that directory.
        """

        self.cascade = cascade
        """Merge every discovered configuration file instead of stopping at the
        first parseable one.

        When `True`, all files found by auto-discovery (the app-dir search,
        including the parent walk when `search_parents=True`, plus the
        `pyproject.toml` CWD search when enabled) are loaded and layered into
        the context's `default_map`. The most local file wins each key, in the
        sections of subcommands too: a `pyproject.toml` found near the CWD
        overrides the app-dir config, which overrides files found higher up
        the parent walk. A list comes whole from the most local file setting it.

        An explicit `--config` value never cascades: it pins a single source,
        whatever the pattern matches.

        Defaults to `False`: the first successfully parsed file wins.
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
        This is distinct from `strict`, which controls whether config keys not
        matching CLI parameters are rejected. `schema_strict` validates against
        dataclass fields instead.
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

        self.config_validators: tuple[ConfigValidator, ...] = (
            _builtin_config_validators() + tuple(config_validators)
        )
        """Extension validators for sub-trees of the configuration file.

        Each {class}`~click_extra.config.schema.ConfigValidator` targets a dotted
        `extension_path` relative to the app section. Validators run after
        click-extra's built-in CLI-parameter strict check (during
        `--validate-config`) and after the schema callable produces the typed
        configuration object (during normal config loading).

        The list is seeded with click-extra's built-in validators (the one for
        `[tool.<cli>.themes.<name>]` tables, see
        {func}`click_extra.theme.validate_themes_config`); user-supplied
        validators are appended after them. App code that registers its own
        validator on the same `extension_path` runs alongside the built-in: both
        validators are called, both sets of errors surface.
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

        # Run by the first `load_conf` call logging at DEBUG level rather than here:
        # its checks need wcmatch, which stays off the startup path of every CLI.
        self._pattern_sanity_checked = False

        # The group this option lands on is not built yet, and may be of a class
        # click-extra does not own.
        _patch_group_parse_args(ConfigOption)

    def apply_command_settings(
        self,
        *,
        config_schema: type | Callable[[dict[str, Any]], Any] | None = None,
        config_strict: bool = False,
        schema_strict: bool = False,
        fallback_sections: Sequence[str] = (),
        config_validators: Sequence[ConfigValidator] = (),
        included_params: Iterable[str] | None = None,
        excluded_params: Iterable[str] | None = None,
        cascade: bool = False,
    ) -> None:
        """Take over the configuration settings a command was built with.

        {class}`~click_extra.commands.Command` accepts the settings of its default
        `--config` option as keyword arguments of its own, so a CLI tunes that
        option without replacing the whole default parameter list, and hands them
        over here once its parameters are known. Each argument defaults to the
        value meaning "leave the option as it is".

        `excluded_params` is additive, where the option's own argument replaces
        the default blocklist: the forwarded IDs join it, through
        {attr}`extra_excluded_params` while the blocklist is still the dynamic
        default, and straight into the frozen value otherwise. The
        `config_validators` join click-extra's built-in ones the same way, as they
        do when passed to the option itself.

        :raises ValueError: when `excluded_params` is forwarded to an option
            carrying its own `included_params`, the two filters being mutually
            exclusive.
        """
        if included_params is not None:
            self.included_params = frozenset(included_params)
            # Schema-only section: see the same inference in `__init__`.
            self.schema_warn_unknown = not self.included_params
        if excluded_params is not None:
            if self.included_params is not None:
                msg = (
                    "excluded_params conflicts with the config option's own "
                    "included_params."
                )
                raise ValueError(msg)
            if "excluded_params" in self.__dict__:
                # The option carries an explicit blocklist: extend the frozen
                # instance value directly.
                self.excluded_params = self.excluded_params | frozenset(excluded_params)
            else:
                # Stash the additions for the dynamic default property to merge
                # at resolution time, when the runtime context is available.
                self.extra_excluded_params = frozenset(excluded_params)
        if config_strict:
            self.strict = config_strict
        if schema_strict:
            self.schema_strict = schema_strict
        if config_schema is not None:
            self.config_schema = config_schema
        if fallback_sections:
            self.fallback_sections = tuple(fallback_sections)
        if cascade:
            self.cascade = cascade
        if config_validators:
            self.config_validators = _builtin_config_validators() + tuple(
                config_validators
            )
        # A new schema or new validators change the opaque paths: drop the cached
        # set, so the next read derives it from them.
        if config_schema is not None or config_validators:
            self.__dict__.pop("_opaque_paths", None)

    @cached_property
    def _opaque_paths(self) -> frozenset[str]:
        """Dotted paths, relative to the app section, that strict CLI-parameter
        validation must skip.

        Union of schema-inferred extension fields and explicit
        {class}`~click_extra.config.schema.ConfigValidator` registrations, see
        `click_extra.config.schema._collect_opaque_paths`. Derived on first use
        rather than at decoration: walking a large schema costs startup time.
        """
        return _collect_opaque_paths(self.config_schema, self.config_validators)

    @cached_property
    def file_pattern_flags(self) -> int:
        """Flags provided to all calls of `wcmatch.fnmatch`.

        Applies to the matching of file names against supported format patterns
        specified in `file_format_patterns`. `None` at construction picks
        `NEGATE | SPLIT`.

        ```{important}
        The `SPLIT` flag is always forced, as our multi-pattern design relies on
        it.
        ```

        Resolved on first use rather than in `__init__`, so building the option
        imports nothing from wcmatch.
        """
        # Deferred import: keeps wcmatch off the startup path of every CLI.
        from wcmatch import fnmatch

        flags = self._file_pattern_flags
        if flags is None:
            return fnmatch.NEGATE | fnmatch.SPLIT
        if not flags & fnmatch.SPLIT:
            logger.warning("Forcing SPLIT flag for file patterns.")
            flags |= fnmatch.SPLIT
        return flags

    @cached_property
    def search_pattern_flags(self) -> int:
        """Flags provided to all calls of `wcmatch.glob`.

        Applies to both the default pattern and any user-provided pattern. `None`
        at construction picks `GLOBSTAR | FOLLOW | DOTGLOB | BRACE | SPLIT |
        GLOBTILDE | NODIR`.

        ```{important}
        The `BRACE` flag is always forced, so that multi-format default
        patterns using ``{pat1,pat2,...}`` syntax expand correctly.

        The `NODIR` flag is always forced, to optimize the search for files only.
        ```

        Resolved on first use rather than in `__init__`, so building the option
        imports nothing from wcmatch.
        """
        # Deferred import: keeps wcmatch off the startup path of every CLI.
        from wcmatch import glob

        flags = self._search_pattern_flags
        if flags is None:
            return (
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.DOTGLOB
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            )
        if not flags & glob.BRACE:
            logger.warning("Forcing BRACE flag for search patterns.")
            flags |= glob.BRACE
        if not flags & glob.NODIR:
            logger.warning("Forcing NODIR flag for search patterns.")
            flags |= glob.NODIR
        return flags

    def _tilde_in_search_flags(self) -> bool:
        """Whether the search flags carry `GLOBTILDE`.

        The default set does, which the help screen can know without resolving
        the flags: that keeps wcmatch off the `--help` path of every CLI.
        """
        if self._search_pattern_flags is None:
            return True
        # Deferred import: keeps wcmatch off the startup path of every CLI.
        from wcmatch import glob

        return bool(self.search_pattern_flags & glob.GLOBTILDE)

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

        # Deferred import: keeps wcmatch off the startup path of every CLI.
        from wcmatch import fnmatch, glob

        # --- Checks 1, 2, 4 require an explicit default ---
        if not isinstance(self.default, str):
            return

        file_part = PurePosixPath(self.default).name
        default_is_magic = self._is_magic(self.default)
        all_format_patterns = tuple(flatten(self.file_format_patterns.values()))

        # Check 1: broad glob + all-literal format patterns.
        if default_is_magic:
            all_literal = all(not self._is_magic(p) for p in all_format_patterns)
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
        Resolved once, on first read, and only when the user did not provide a
        list of their own.

        The IDs are rooted at the CLI name, which only the running context
        knows: hence a property, read within that context, rather than a value
        set by the constructor.
        ```
        """
        ctx = get_current_context()
        cli = ctx.find_root().command
        excluded_ids = list(DEFAULT_EXCLUDED_PARAMS)
        # Read the help option's ID from Click instead of assuming it is named
        # "help": Click's development branch names it "_click_default_help", and
        # click-extra does not control that name.
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
        patterns = dict.fromkeys(flatten(self.file_format_patterns.values()))
        return ",".join(patterns)

    @cached_property
    def _file_pattern_glob(self) -> str:
        """The `file_pattern` as the last segment of a search pattern.

        Several patterns are wrapped in ``{…}`` braces, so that `BRACE` expansion
        applies the directory prefix to every one of them.
        """
        fp = self.file_pattern
        return f"{{{fp}}}" if "," in fp else fp

    def default_pattern(self) -> str:
        """Returns the default pattern used to search for the configuration file.

        Defaults to the patterns of every format in `file_format_patterns`, under
        `<app_dir>`: ``<app_dir>/{*.toml,*.json,*.ini,…}``. Where `<app_dir>` is
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
        {ref}`the documentation <use-platformdirs-instead>`.
        ```
        """
        ctx = get_current_context()
        cli_name = ctx.find_root().info_name
        if not cli_name:
            raise ValueError("No CLI name to locate the configuration folder from.")
        app_dir = Path(
            get_app_dir(cli_name, roaming=self.roaming, force_posix=self.force_posix),
        ).resolve()
        return f"{app_dir}{os.path.sep}{self._file_pattern_glob}"

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
        method instead. A URL is returned as given.
        """
        default = self.get_default(ctx)
        if default is NO_CONFIG:
            return "disabled"
        default_str = str(default)
        # A URL is not a path to shorten: `Path()` would collapse the double
        # slash after its scheme.
        if "://" in default_str:
            return default_str
        if self._tilde_in_search_flags():
            # When the default already starts with `~` (user-supplied tilde
            # pattern), use it as-is. Passing through `Path()` would
            # normalize forward slashes to backslashes on Windows.
            if default_str.startswith("~"):
                return default_str
            return str(shrinkuser(Path(default)))
        return default_str

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
        folder, sep, tail = default.rpartition(os.path.sep)
        # Leave a custom default alone: only the pattern this option built for
        # itself ends with its own file patterns.
        if not sep or tail != self._file_pattern_glob:
            return default
        return folder + sep

    def parse_conf(
        self,
        content: str,
        formats: Sequence[ConfigFormat],
        location: Path | str | None = None,
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
        are considered a failure and are skipped. A format parsing the content
        to `None`, as YAML does for a document of comments only, yields an empty
        `dict` instead.

        This follows the *parse, don't validate* principle.
        ```
        """

        conf = None
        for fmt in formats:
            try:
                match fmt:
                    case ConfigFormat.INI:
                        conf = self.load_ini_config(content)
                    case ConfigFormat.ARGFILE:
                        conf = self.load_argfile_config(content)
                    case ConfigFormat.SQLITE:
                        if not isinstance(location, Path):
                            raise TypeError(
                                "SQLite configurations can only be read from a "
                                "local file."
                            )
                        conf = self.load_sqlite_config(location)
                    case ConfigFormat.PLIST if isinstance(location, Path):
                        # Local files are read as raw bytes so the binary plist
                        # variant parses too. Text payloads (URL downloads) fall
                        # through to parse_content(), which handles the XML one.
                        conf = self.load_plist_config(location)
                    case _:
                        conf = parse_content(fmt, content)

            except Exception as ex:  # noqa: BLE001
                logger.debug(f"{fmt} parsing failed: {ex}")
                continue

            # A parseable but empty configuration is expected to return an empty dict.
            if conf is None:
                conf = {}
            elif not isinstance(conf, dict):
                logger.debug(
                    f"{fmt} parsing failed: expecting a dict, got {conf!r} instead."
                )
                continue

            logger.debug(f"{fmt} parsing successful, got {conf!r}.")
            yield conf

    def _parse_matches(
        self,
        pattern: str,
    ) -> Iterable[tuple[Path | str, dict[str, Any] | None, tuple[ConfigFormat, ...]]]:
        """Parse every file matching `pattern`, in discovery order.

        Yields a `(location, conf, empty_formats)` triple per file, as
        {meth}`_parse_one_conf` returns them. A file found again, as matched by its
        resolved location, is skipped.

        Raises `FileNotFoundError` if no file at all matched the pattern.
        """
        seen: set[str] = set()

        for location, content, media_type in self.search_and_read_file(pattern):
            if str(location) in seen:
                logger.debug(f"Skipping duplicate {location}.")
                continue
            seen.add(str(location))

            conf, empty_formats = self._parse_one_conf(location, content, media_type)
            yield location, conf, empty_formats

    def read_and_parse_all_conf(
        self,
        pattern: str,
    ) -> Iterable[tuple[Path | str, dict[str, Any]]]:
        """Search for every parseable configuration file matching `pattern`.

        Yields `(location, parsed_conf)` pairs in discovery order, which is
        the most local first: the original search location, then each parent
        directory when parent search is enabled. Files already yielded (as
        matched by their resolved location) are skipped, as are files that
        parse to an empty configuration.

        Raises `FileNotFoundError` if no file at all matched the pattern.
        """
        for location, conf, _empty_formats in self._parse_matches(pattern):
            if not conf:
                logger.debug(f"Nothing to load from {location}.")
                continue

            yield location, conf

    def _parse_one_conf(
        self,
        location: Path | str,
        content: str,
        media_type: str | None = None,
    ) -> tuple[dict[str, Any] | None, tuple[ConfigFormat, ...]]:
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

        Returns a `(conf, empty_formats)` pair. `conf` is the first non-empty
        structure a format produces, or an empty dict for a blank source, one
        holding nothing but whitespace. A blank source is caught before any format
        is tried: there is nothing to parse, so a source no format matches, like
        `/dev/null`, is blank too. `conf` is `None` when the file matches no
        format, or no parse attempt produces a non-empty structure:
        `empty_formats` then names the formats that parse it to an empty one.
        """
        # Deferred imports: keep urllib and wcmatch off the startup path of every
        # CLI.
        from urllib.parse import urlsplit

        from wcmatch import fnmatch

        # A file parsed from its path carries an empty placeholder as content,
        # which says nothing about the file itself: its size decides.
        if isinstance(location, Path) and format_from_path(
            location, _PATH_READ_FORMATS
        ):
            blank = location.stat().st_size == 0
        else:
            blank = not content.strip()
        if blank:
            logger.debug(f"{location} is blank.")
            return {}, ()

        if isinstance(location, Path):
            filename = location.name
        else:
            filename = PurePosixPath(urlsplit(location).path).name

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
            return None, ()

        logger.debug(f"Parsing {location} with {','.join(map(str, matching_formats))}")
        empty_formats = []
        for fmt in matching_formats:
            for conf in self.parse_conf(content, formats=(fmt,), location=location):
                if conf:
                    return conf, ()
                logger.debug("Empty configuration, try next format.")
                empty_formats.append(fmt)

        return None, tuple(empty_formats)

    def read_and_parse_conf(
        self,
        pattern: str,
    ) -> tuple[Path | str, dict[str, Any]] | tuple[None, None]:
        """Search for a parseable configuration file.

        Returns the location and data structure of the first configuration matching the
        `pattern`.

        Only return the first match that:

        - exists,
        - is a file, or a character device or a named pipe that `pattern` names,
        - is not empty,
        - match file format patterns,
        - can be parsed successfully, and
        - produce a non-empty data structure.

        Raises `FileNotFoundError` if no configuration file was found matching the
        criteria above.

        Returns `(None, None)` if files were found but none could be parsed.
        """
        return next(iter(self.read_and_parse_all_conf(pattern)), (None, None))

    def _read_explicit_conf(
        self,
        pattern: str,
    ) -> tuple[Path | str, dict[str, Any]] | tuple[None, None]:
        """Read the configuration at a location the user names on purpose.

        Works like {meth}`read_and_parse_conf`, for `--config` and
        `--validate-config`, with two differences when no match holds a
        configuration:

        - The first blank match loads an empty configuration. This is how
          `--config /dev/null` runs the CLI on its defaults.
        - Failing that, the first match that a format parses to nothing raises
          {class}`_EmptyConfigError`, which names that format.

        Raises `FileNotFoundError` if no file at all matched the pattern.

        Returns `(None, None)` if files were found but no format could parse them.
        """
        first_blank: tuple[Path | str, dict[str, Any]] | None = None
        first_empty: tuple[Path | str, tuple[ConfigFormat, ...]] | None = None
        for location, conf, empty_formats in self._parse_matches(pattern):
            if conf:
                return location, conf
            if conf is not None:
                first_blank = first_blank or (location, conf)
            elif empty_formats:
                first_empty = first_empty or (location, empty_formats)

        if first_blank:
            return first_blank
        if first_empty:
            raise _EmptyConfigError(*first_empty)
        return None, None

    def load_ini_config(self, content: str) -> dict[str, Any]:
        """Utility method to parse INI configuration file.

        Internal convention is to use a dot (`.`, as set by
        {data}`~click_extra.param_tools.PARAM_PATH_SEP`) in section IDs as a
        separator between levels. This is a workaround the limitation of `INI`
        format which doesn't allow for sub-sections.

        Each value is converted to the type of the parameter its section and key
        address, like `[my-cli.subcommand]` for the options of `subcommand`.

        Returns a ready-to-use data structure.
        """
        # Deferred import: keeps configparser off the startup path of every CLI.
        from configparser import ConfigParser, ExtendedInterpolation

        ini_config = ConfigParser(interpolation=ExtendedInterpolation())
        ini_config.read_string(content)

        conf: dict[str, Any] = {}
        for section_id in ini_config.sections():
            section_path = section_id.split(PARAM_PATH_SEP)
            sub_conf = {}
            for option_id in ini_config.options(section_id):
                # An item matching no parameter keeps its text.
                try:
                    target_params = self.get_tree_value(
                        self.params_objects, *section_path, option_id
                    )
                except (KeyError, TypeError):
                    target_params = None
                target_type = None
                if isinstance(target_params, list):
                    # One name can be shared by several options, which must then
                    # share a type for the item to be read as it.
                    target_types = [self.get_param_type(p) for p in target_params]
                    if len(set(target_types)) > 1:
                        raise ValueError(
                            f"Cannot handle the {target_types!r} types defined by the "
                            "multiple options associated to the "
                            f"[{section_id}]:{option_id} INI config item."
                        )
                    target_type = target_types[0]

                sub_conf[option_id] = _coerce_scalar(
                    target_type,
                    ini_config.get(section_id, option_id),
                    f"[{section_id}]:{option_id} INI config item",
                )

            # Place collected options at the right level of the dict tree.
            set_nested(conf, section_path, sub_conf)

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
            return _coerce_scalar(target_type, raw_value, f"{decl} value {raw_value!r}")

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
            # {func}`~click_extra.param_tools.resolve_flag_value` reads the same
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
        (`.`, as set by {data}`~click_extra.param_tools.PARAM_PATH_SEP`)
        separating each level, like `my-cli.default.int_param`. Values are
        JSON-encoded, which carries every type the other formats do:
        booleans, numbers, strings, lists and nested objects alike.

        Returns a ready-to-use data structure.

        ```{note}
        {mod}`sqlite3` is imported here and not at the top of the module, like
        the optional parsers of
        {func}`~click_extra.config.formats.parse_content`. A distribution can
        ship a Python without the SQLite bindings, and an unconditional import
        would then break every CLI at import time. `ConfigFormat.SQLITE.enabled`
        reports whether they are there, and the format is disabled if they are
        not.
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
            set_nested(conf, key.split(PARAM_PATH_SEP), json.loads(raw_value))

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
        # Deferred import: keeps plistlib off the startup path of every CLI.
        import plistlib

        conf: dict[str, Any] = plistlib.loads(path.read_bytes())
        return conf

    def _app_section_name(self, ctx: click.Context) -> str:
        """Return the name of the app's section in a configuration document.

        Prefers the root command's name, falls back to `ctx.info_name`, and
        defaults to an empty string, which makes the whole document the section.
        """
        return ctx.find_root().command.name or ctx.info_name or ""

    def _merged_conf(self, ctx: click.Context, conf: dict[str, Any]) -> dict[str, Any]:
        """Merge the app's section of `conf` onto this option's parameter template.

        Runs the strict check alone, with this option's settings: the opaque
        sub-trees and the reserved keys are left out, so neither a key of an
        extension point nor a dot inside one trips `strict=True`, and neither does
        a key the schema reads.

        :raises ~click_extra.config.schema.ValidationError: in strict mode, on an
            invalid dotted key or a key matching no parameter.
        """
        return _build_merged_conf(
            conf,
            app_name=self._app_section_name(ctx),
            params_template=self.params_template,
            opaque_paths=self._opaque_paths,
            fallback_sections=self.fallback_sections,
            strict=self.strict,
            blocked=self.excluded_params,
            config_schema=self.config_schema,
        )

    def _validate_conf(
        self,
        ctx: click.Context,
        conf: dict[str, Any],
        *,
        params_template: dict[str, Any] | None,
        strict: bool,
        collect_all: bool = False,
    ) -> ValidationReport:
        """Run {func}`~click_extra.config.schema.run_config_validation` on `conf`.

        The schema, the validators and the section settings are this option's.
        `collect_all` defaults to `False`: a configuration being loaded stops at
        its first error.
        """
        return run_config_validation(
            conf,
            app_name=self._app_section_name(ctx),
            params_template=params_template,
            config_schema=self.config_schema,
            config_validators=self.config_validators,
            fallback_sections=self.fallback_sections,
            schema_strict=self.schema_strict,
            schema_warn_unknown=self.schema_warn_unknown,
            strict=strict,
            blocked_params=self.excluded_params,
            collect_all=collect_all,
        )

    def _apply_theme_overrides(
        self,
        ctx: click.Context,
        report: ValidationReport,
    ) -> None:
        """Build per-invocation theme overrides from the config and stash on `ctx.meta`.

        Reads the `[tool.<cli>.themes.<name>]` sub-tree the validation extracted,
        builds each entry into a {class}`HelpTheme <click_extra.theme.HelpTheme>`
        (cascading on top of an existing built-in theme when *name* matches one
        already in {data}`~click_extra.theme.theme_registry`), and writes the result
        to `ctx.meta[click_extra.context.THEME_OVERRIDES]`. The module-level
        registry is never mutated, so themes defined here apply to the current
        invocation only.

        Validation already happened via the built-in
        {func}`~click_extra.theme.validate_themes_config` validator, so failures
        below this point would be a click-extra bug rather than user error.
        """
        themes_subtree = report.opaque_subtrees.get(THEMES_CONFIG_KEY)
        if not themes_subtree:
            return
        # Deferred import: click_extra.theme and this package import each other.
        from ..theme import themes_from_config

        overrides = themes_from_config(themes_subtree)
        if overrides:
            context.set(ctx, context.THEME_OVERRIDES, overrides)

    def _publish_report(self, ctx: click.Context, report: ValidationReport) -> None:
        """Publish on `ctx.meta` what a passing validation produced.

        The typed instance the schema callable built, under
        {data}`~click_extra.context.TOOL_CONFIG`, when a schema is configured, and
        the themes the document defines, under
        {data}`~click_extra.context.THEME_OVERRIDES`. The pipeline validated the
        themes table already, so building it here cannot surface a user error.
        """
        if self.config_schema is not None:
            context.set(ctx, context.TOOL_CONFIG, report.schema_instance)
        self._apply_theme_overrides(ctx, report)

    def merge_default_map(self, ctx: click.Context, user_conf: dict) -> None:
        """Save the user configuration into the context's `default_map`.

        Merge the user configuration into the pre-computed template structure, which
        filters out all unrecognized options not supported by the command, then hand
        the result to {meth}`_install_default_map`.

        Opaque sub-trees declared by the schema or by registered
        {class}`~click_extra.config.schema.ConfigValidator` instances are stripped
        from the conf before dotted-key expansion and the CLI-parameter strict
        check, so user-controlled keys (like mappings whose keys are data, not flag
        names) neither split on a dot nor trip `strict=True`.

        ```{note}
        {meth}`load_conf` installs the same merged configuration, as part of the
        validation it runs: it does not call this method.
        ```

        :raises ~click_extra.config.schema.ValidationError: in strict mode, on an
            invalid dotted key or a key matching no parameter.
        """
        self._install_default_map(ctx, self._merged_conf(ctx, user_conf))

    def _apply_cascaded_conf(
        self,
        ctx: click.Context,
        layers: Sequence[tuple[Path | str, dict[str, Any]]],
    ) -> dict[str, Any]:
        """Validate and install multiple config layers into `default_map`.

        *layers* holds `(location, parsed_conf)` pairs in precedence order,
        highest first. Each file is strict-checked individually so any error
        names the file it comes from, then installed as its own `default_map`
        layer, lowest precedence first so the highest-precedence file ends up in
        front. The layers resolve each key of a subcommand section the same way
        as a key of the root command, so the values match the merged view below.

        The dataclass schema and extension validators run once on the
        deep-merged view of all layers, where they see one coherent document.
        That merged view is returned, for publication in
        `ctx.meta[click_extra.context.CONF_FULL]`.
        """
        # Strict-check each file against the CLI-parameter template.
        per_file_conf = []
        for location, conf in layers:
            try:
                per_file_conf.append(self._merged_conf(ctx, conf))
            except ValidationError as error:
                _exit_on_validation_error(ctx, error, location)

        # Deep-merge the raw documents, highest-precedence layer winning, for
        # the schema and the extension validators. Merging starts from the
        # lowest-precedence file so each later merge overwrites it.
        merged_view: dict[str, Any] = {}
        for _location, conf in reversed(layers):
            merged_view = deep_merge(merged_view, copy.deepcopy(conf))

        report = self._validate_conf(
            ctx, merged_view, params_template=None, strict=self.strict
        )
        if not report.ok:
            _exit_on_validation_error(ctx, report.errors[0])

        # Install one default_map layer per file, lowest precedence first.
        for merged_conf in reversed(per_file_conf):
            self._install_default_map(ctx, merged_conf)
        logger.debug(f"New defaults: {ctx.default_map}")

        self._publish_report(ctx, report)
        return merged_view

    def _install_default_map(
        self, ctx: click.Context, filtered_conf: dict[str, Any]
    ) -> None:
        """Layer a template-filtered config onto the context's `default_map`.

        Cleans up the blank values left over by the template structure, then puts
        the app's section in front of any existing `default_map`, in a
        `_DeepChainMap` where each config source keeps its own layer. The front
        layer wins each key, in the sections of subcommands too.

        The layers stay flat in one chain, front layer first: the layers of a
        cascade then hold the same positions as their files in
        `ctx.meta[click_extra.context.CONF_SOURCES]`, which is how
        {func}`~click_extra.show_params.param_config_source` names the file a
        value comes from.
        """
        # Clean-up the conf by removing all blank values left-over by the template
        # structure.
        clean_conf = remove_blanks(filtered_conf, remove_str=False)

        local_conf = clean_conf.get(ctx.find_root().command.name, {})
        existing = ctx.default_map
        if isinstance(existing, _DeepChainMap):
            behind = existing.maps
        elif existing is None:
            behind = []
        else:
            behind = [existing]
        ctx.default_map = _DeepChainMap(local_conf, *behind)

    def load_conf(
        self,
        ctx: click.Context,
        param: click.Parameter,
        path_pattern: str | Path | Literal[Sentinel.NO_CONFIG],
    ) -> None:
        """Fetch parameter values from a configuration file and set them as defaults.

        User configuration is merged to the [context's default_map](https://click.palletsprojects.com/en/stable/commands/#overriding-defaults),
        [like Click does](https://click.palletsprojects.com/en/stable/commands/#context-defaults).

        Relying on Click's `default_map` keeps the precedence: direct CLI
        parameters, environment variables or interactive prompts take precedence
        over any values from the config file.

        ```{hint}
        Once loading is complete, the resolved file path and its full parsed content
        are stored in `ctx.meta[click_extra.context.CONF_SOURCE]` and
        `ctx.meta[click_extra.context.CONF_FULL]` respectively. This is the
        recommended way to identify which configuration file was loaded.

        There is no `ParameterSource.CONFIG_FILE` enum member: `ParameterSource`
        is a closed enum in Click, and monkeypatching it would be fragile. Config
        values end up in `default_map`, so Click reports them as
        `ParameterSource.DEFAULT_MAP`, which is accurate.
        ```
        """
        # Skip file I/O and ctx.meta writes during help rendering, shell
        # completion, and any `make_context(resilient_parsing=True)` path.
        if ctx.resilient_parsing:
            return

        # The checks only log at DEBUG level: below it, they would cost the import
        # of wcmatch for nothing.
        if not self._pattern_sanity_checked and logger.isEnabledFor(logging.DEBUG):
            self._pattern_sanity_checked = True
            self._check_pattern_sanity()

        # A bare invocation already loaded this document ahead of the no-args help
        # screen: skip the visit Click's parameter loop makes next.
        preloaded = context.get(ctx, context._CONFIG_PRELOADED)
        if preloaded and ctx.command_path in preloaded:
            preloaded.remove(ctx.command_path)
            return

        # The status lines below go to stderr through echo(), not the logger: the
        # logger still sits at its default level here, because the verbosity options
        # run after this one. handle_parse_result() reads the level they will settle
        # on ahead of time, so -q and a quieter --verbosity still silence the lines.
        silenced = context.get(ctx, context._CONFIG_STATUS_SILENCED, False)

        assert self.name is not None  # Always set for Option subclasses.

        explicit_conf = ctx.get_parameter_source(self.name) in _EXPLICIT_SOURCES

        if path_pattern is NO_CONFIG:
            logger.debug(f"{NO_CONFIG} received.")
            if explicit_conf:
                if not silenced:
                    echo("Skip configuration file loading altogether.", err=True)
            else:
                logger.debug("Configuration file autodiscovery disabled by default.")
            return

        # Print configuration location to the user if it was explicitly set.
        # Normalize to string to both allow parsing as a glob pattern or URL.
        if isinstance(path_pattern, Path):
            # Normalize the path without checking for its existence.
            path_pattern = str(path_pattern.resolve(strict=False))
        # NO_CONFIG was handled above with an early return. Help mypy see that.
        assert isinstance(path_pattern, str)
        message = f"Load configuration matching {path_pattern}"
        if explicit_conf and not silenced:
            echo(message, err=True)
        else:
            logger.debug(message)

        # Discover configuration layers, in precedence order (highest first).
        # A pyproject.toml found near the CWD beats the app-dir search, which
        # itself yields the most local file first.
        conf_path: Path | str | None = None
        user_conf: dict[str, Any] | None = None
        layers: list[tuple[Path | str, dict[str, Any]]] = []
        if (
            not explicit_conf
            and ConfigFormat.PYPROJECT_TOML in self.file_format_patterns
        ):
            # Without a cascade, the deepest pyproject.toml wins, as with uv, ruff
            # and mypy.
            pyprojects = self._search_pyproject_cwd()
            layers.extend(pyprojects if self.cascade else islice(pyprojects, 1))
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
                # A source the user points at with nothing in it, like `/dev/null`,
                # loads an empty configuration. Autodiscovery skips it.
                if explicit_conf:
                    result = self._read_explicit_conf(path_pattern)
                else:
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
        except _EmptyConfigError as ex:
            logger.critical(str(ex))
            ctx.exit(2)
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

                # Run every check through the unified pipeline, which stops at
                # the first error.
                report = self._validate_conf(
                    ctx,
                    user_conf,
                    params_template=self.params_template,
                    strict=self.strict,
                )
                if not report.ok:
                    _exit_on_validation_error(ctx, report.errors[0])

                # Validation passed. Install the recognized values the pipeline
                # merged onto the template into default_map, then publish what
                # it built.
                assert report.merged_conf is not None  # params_template is always set.
                self._install_default_map(ctx, report.merged_conf)
                logger.debug(f"New defaults: {ctx.default_map}")
                self._publish_report(ctx, report)

        # When a schema is configured but no config file was found, still
        # produce the default instance so get_tool_config() never returns None.
        elif self.config_schema is not None:
            logger.debug("No config file found; instantiating schema defaults.")
            schema_callable = make_schema_callable(self.config_schema)
            assert schema_callable is not None  # The schema is set.
            context.set(ctx, context.TOOL_CONFIG, schema_callable({}))

        # Expose the resolved config file path and its full parsed content via
        # ctx.meta, so downstream CLI code can inspect what was loaded and from where.
        # See the load_conf docstring for why ctx.meta stands in for a custom
        # ParameterSource enum member.
        context.set(ctx, context.CONF_SOURCE, conf_path)
        context.set(ctx, context.CONF_FULL, user_conf)
        context.set(ctx, context.CONF_SOURCES, tuple(layers))

    def handle_parse_result(
        self,
        ctx: click.Context,
        opts: Mapping[str, Any],
        args: list[str],
    ) -> tuple[Any, list[str]]:
        """Apply the reserved subcommand keys, once the configuration is loaded.

        {meth}`load_conf` runs as this option's callback, from inside the `super()`
        call below, so the parsed document is already in `ctx.meta` when
        {func}`~click_extra.config.subcommands.inject_reserved_subcommands` reads it.

        Returning a rewritten `args` is what makes `_default_subcommands` and
        `_prepend_subcommands` work on any group class: Click threads the residual
        arguments through each parameter in turn, then hands the final list to
        `Group.parse_args`, which splits it into the subcommands to dispatch. The
        group can be of a class click-extra does not own, so the option carries the
        feature instead of the group.

        Two cases never come here. On a bare invocation, Click raises the
        `no_args_is_help` screen before it runs any parameter. A subgroup reached
        through this option holds no option of its own. The `click.Group.parse_args`
        this class installs covers both.

        Before loading, it reads the verbosity the command line asks for (see
        {func}`~click_extra.logging.requested_level`), so {meth}`load_conf` can keep
        its status lines quiet under `-q` or a `--verbosity` above `WARNING`.
        """
        if not ctx.resilient_parsing:
            level = requested_level(ctx, opts)
            context.set(
                ctx,
                context._CONFIG_STATUS_SILENCED,
                level is not None and level > LogLevel.WARNING,
            )
        value, args = super().handle_parse_result(ctx, opts, args)
        if not ctx.resilient_parsing:
            args = inject_reserved_subcommands(ctx, args)
        return value, args

    def _resolve_subcommands_eagerly(self, ctx: click.Context) -> list[str]:
        """Settle the reserved subcommand keys ahead of the no-args help screen.

        Processes this option on its own, which loads the document and returns the
        names to dispatch. {func}`~click_extra.config.subcommands._group_parse_args`
        is the only caller, and the command line is empty by the time it reaches
        here, so the option is handed no parsed value and falls back to its own
        auto-discovery.

        Returns an empty list when the configuration names nothing, which leaves
        Click's help screen in place. A usage error does the same, like a reserved
        key naming an unknown subcommand: the regular parameter loop reports it on
        the next invocation naming a subcommand. A document failing validation still
        ends the CLI from here, as it does on every other invocation.

        Names to dispatch mean Click's parameter loop runs next, and processes this
        option again with the same value. The context is marked so that
        {meth}`load_conf` skips that second visit.
        """
        try:
            _, injected = self.handle_parse_result(ctx, {}, [])
        except click.ClickException:
            return []
        if injected:
            context.setdefault(ctx, context._CONFIG_PRELOADED, set).add(
                ctx.command_path
            )
        return injected


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
        *,
        help: str = _(
            "Ignore all configuration files and only use command line parameters and "
            "environment variables.",
        ),
        is_flag: bool = True,
        flag_value: Any = NO_CONFIG,
        is_eager: bool = True,
        expose_value: bool = False,
        **kwargs: Any,
    ) -> None:
        """`flag_value=NO_CONFIG` is the `Sentinel` enum member that
        signals "skip configuration loading" to {class}`ConfigOption`. Click
        picks `type=UNPROCESSED` for a `flag_value` of a non-basic type, so the
        sentinel passes through `Option` unchanged.

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
    `http://` or `https://` URL. Both options read their value the same way,
    so a configuration a CLI can load is a configuration it can also validate.
    ```
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
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
            _conf_path, user_conf = config_option._read_explicit_conf(value)
        except FileNotFoundError:
            info_msg(f"Configuration file not found: {value}")
            ctx.exit(2)
        except _EmptyConfigError as ex:
            info_msg(str(ex))
            ctx.exit(2)

        if user_conf is None:
            formats = _join_format_labels(config_option.file_format_patterns)
            info_msg(f"Error parsing {value} as {formats}.")
            ctx.exit(2)

        # Delegate every check to the unified pipeline in collect-all mode so a
        # single run surfaces the full punch list. `--validate-config` always
        # runs the CLI-parameter check in strict mode regardless of the sibling
        # option's `strict` setting. The schema checks follow the option's own
        # settings, as when it loads the file.
        report = config_option._validate_conf(
            ctx,
            user_conf,
            params_template=config_option.params_template,
            strict=True,
            collect_all=True,
        )

        if not report.ok:
            for error in report.errors:
                info_msg(f"Configuration validation error: {error}")
            ctx.exit(1)

        info_msg(f"Configuration file {value} is valid.")
        ctx.exit(0)
