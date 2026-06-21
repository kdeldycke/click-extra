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

.. hint::
    Why ``config``?

    That whole namespace is using the common ``config`` short-name to designate
    configuration files.

    Not ``conf``, not ``cfg``, not ``configuration``, not ``settings``. Just ``config``.

    A quick survey of existing practices, and poll to my friends informed me that
    ``config`` is more explicit and less likely to be misunderstood.

    After all, is there a chance for it to be misunderstood, in the context of a CLI,
    for something else? *Confirm*? *Conference*? *Conflict* *Confuse*?...

    So yes, ``config`` is good enough.

.. todo::
    Add a ``--dump-config`` or ``--export-config`` option to write down the current
    configuration (or a template) into a file or ``<stdout>``.

    Help message would be: *you can use this option with other options or environment
    variables to have them set in the generated configuration*.

Dotted keys in configuration files (like ``"subcommand.option": value``) are
automatically expanded into nested dicts before merging, so users can freely mix
flat dot-notation and nested structures in any supported format.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from collections import ChainMap
from collections.abc import Iterable
from configparser import ConfigParser, ExtendedInterpolation
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property, partial
from gettext import gettext as _
from pathlib import Path, PurePosixPath

import requests
from boltons.iterutils import flatten, unique
from boltons.pathutils import shrinkuser
from boltons.urlutils import URL
from deepmerge import always_merger
from extra_platforms import is_windows
from extra_platforms._utils import _recursive_update, _remove_blanks
from wcmatch import fnmatch, glob

from .. import (
    UNPROCESSED,
    ParameterSource,
    Path as ClickPath,
    context,
    echo,
    get_app_dir,
    get_current_context,
)
from ..parameters import (
    PARAM_PATH_SEP,
    ExtraOption,
    ParamStructure,
    search_params,
)
from .formats import ConfigFormat, parse_content
from .schema import (
    THEMES_CONFIG_KEY,
    ConfigValidator,
    _builtin_config_validators,
    _expand_dotted_keys,
    _opaque_paths,
    _select_app_section,
    _strip_opaque_subtrees,
    _strip_reserved_keys,
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
- ``.git``: Git
- ``.hg``: Mercurial
- ``.svn``: Subversion
- ``.bzr``: Bazaar
- ``CVS``: CVS (note: uppercase, no leading dot)
- ``.darcs``: Darcs
"""


CONFIG_OPTION_NAME = "config"
"""Hardcoded name of the configuration option.

This name is going to be shared by both the ``--config`` and ``--no-config`` options
below, so they can compete with each other to either set a path pattern or disable the
use of any configuration file at all.
"""


DEFAULT_EXCLUDED_PARAMS = (
    CONFIG_OPTION_NAME,
    "help",
    "show_params",
    "version",
)
"""Default parameter IDs to exclude from the configuration file.

Defaults to:

- ``--config`` option, which cannot be used to recursively load another configuration
  file.
- ``--help``, as it makes no sense to have the configurable file always forces a CLI to
  show the help and exit.
- ``--show-params`` flag, which is like ``--help`` and stops the CLI execution.
- ``--version``, which is not a configurable option *per-se*.
"""


class Sentinel(Enum):
    """Enum used to define sentinel values.

    .. note::
        This reuse the same pattern as ``Click._utils.Sentinel``.

    .. seealso::
        `PEP 661 - Sentinel Values <https://peps.python.org/pep-0661/>`_.
    """

    NO_CONFIG = object()
    VCS = object()  # noqa: PIE796

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"


NO_CONFIG = Sentinel.NO_CONFIG
"""Sentinel used to indicate that no configuration file must be used at all."""

VCS = Sentinel.VCS
"""Sentinel used to stop parent directory walking at the nearest VCS root."""


class ConfigOption(ExtraOption, ParamStructure):
    """A pre-configured option adding ``--config CONFIG_PATH``."""

    # excluded_params: frozenset[str]

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        metavar="CONFIG_PATH",
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

        - ``is_eager`` is active by default so the ``callback`` gets the opportunity to
          set the ``default_map`` of the CLI before any other parameter is processed.

        - ``default`` is set to the value returned by ``self.default_pattern()``, which
          is a pattern combining the default configuration folder for the CLI (as
          returned by ``click.get_app_dir()``) and all supported file formats.

          .. attention::
            Default search pattern must follow the syntax of `wcmatch.glob
            <https://facelessuser.github.io/wcmatch/glob/#syntax>`_.

        - ``excluded_params`` are parameters which, if present in the configuration
          file, will be ignored and not applied to the CLI. Items are expected to be the
          fully-qualified ID of the parameter, as produced in the output of
          ``--show-params``. Will default to the value of ``DEFAULT_EXCLUDED_PARAMS``.

        - ``included_params`` is the inverse of ``excluded_params``: only the listed
          parameters will be loaded from the configuration file. Cannot be used together
          with ``excluded_params``.
        """

        if not param_decls:
            param_decls = ("--config", CONFIG_OPTION_NAME)

        # Setup supported file format patterns.
        self.file_format_patterns: dict[ConfigFormat, tuple[str, ...]]
        """Mapping of ``ConfigFormat`` to their associated file patterns.

        Can be a string or a sequence of strings. This defines which configuration file
        formats are supported, and which file patterns are used to search for them.

        .. note::
            All formats depending on third-party dependencies that are not installed
            will be ignored.

        .. attention::
            File patterns must follow the syntax of `wcmatch.fnmatch
            <https://facelessuser.github.io/wcmatch/fnmatch/#syntax>`_.
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
        """Flags provided to all calls of ``wcmatch.fnmatch``.

        Applies to the matching of file names against supported format patterns
        specified in ``file_format_patterns``.

        .. important::
            The ``SPLIT`` flag is always forced, as our multi-pattern design relies on
            it.
        """

        # Setup the configuration for default folder search.
        self.roaming = roaming
        self.force_posix = force_posix
        """Configuration for default folder search.

        ``roaming`` and ``force_posix`` are `fed to click.get_app_dir()
        <https://click.palletsprojects.com/en/stable/api/#click.get_app_dir>`_ to
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
        """Flags provided to all calls of ``wcmatch.glob``.

        Applies to both the default pattern and any user-provided pattern.

        .. important::
            The ``BRACE`` flag is always forced, so that multi-format default
            patterns using ``{pat1,pat2,...}`` syntax expand correctly.

            The ``NODIR`` flag is always forced, to optimize the search for files only.
        """

        self.search_parents = search_parents
        """Indicates whether to walk back the tree of parent folders when searching for
        configuration files.
        """

        self.stop_at = stop_at
        """Boundary for parent directory walking.

        - ``None``: walk up to filesystem root.
        - ``VCS``: stop at the nearest VCS root (``.git`` or ``.hg``) (default).
        - A ``Path`` or ``str``: stop at that directory.
        """

        if excluded_params is not None and included_params is not None:
            msg = "excluded_params and included_params are mutually exclusive."
            raise ValueError(msg)

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

        - If ``True``, raise an error if the configuration file contain parameters not
          recognized by the CLI.
        - If ``False``, silently ignore unrecognized parameters.
        """

        self.config_schema = config_schema
        """Optional schema for structured access to configuration values.

        When set, the app's configuration section is extracted from the parsed
        config file, normalized (hyphens replaced with underscores), flattened
        (nested dicts joined with ``_``), and passed to this callable to produce
        a typed configuration object.

        Supports:

        - **Dataclass types**: detected via ``__dataclass_fields__``. Keys
          are normalized, nested dicts are flattened, and the result is filtered
          to known fields before instantiation. This allows nested config
          sections (like ``[tool.myapp.sub-section]``) to map directly to flat
          dataclass fields (like ``sub_section_key``).
        - **Any callable** ``dict → T``: called directly with the raw
          dict. Works with Pydantic's ``Model.model_validate``, attrs, or
          custom factory functions. The caller is responsible for key
          normalization and flattening.

        The resulting object is stored in
        ``ctx.meta[click_extra.context.TOOL_CONFIG]`` and can be retrieved
        via `get_tool_config`.
        """

        self.schema_strict = schema_strict
        """Strictness for schema validation (separate from ``strict``).

        - If ``True``, raise ``ValueError`` when the config section contains keys
          that do not match any dataclass field (after normalization and
          flattening). Only applies when ``config_schema`` is a dataclass.
        - If ``False``, silently ignore unrecognized keys.

        .. note::
            This is distinct from ``strict``, which controls whether
            ``merge_default_map`` rejects config keys not matching CLI
            parameters.  ``schema_strict`` validates against dataclass fields
            instead.
        """

        self.fallback_sections: Sequence[str] = tuple(fallback_sections)
        """Legacy section names to try when the app's own section is empty.

        Useful when a CLI tool has been renamed: old configuration files that
        still use ``[tool.old-name]`` (TOML), ``old-name:`` (YAML), or
        ``{"old-name": …}`` (JSON) are recognized with a deprecation warning.
        Works with all configuration formats.
        """

        self._config_schema_callable = make_schema_callable(
            config_schema,
            strict=schema_strict,
        )

        self.config_validators: tuple[ConfigValidator, ...] = (
            _builtin_config_validators() + tuple(config_validators)
        )
        """Extension validators for sub-trees of the configuration file.

        Each :class:`~click_extra.config.schema.ConfigValidator` targets a dotted ``extension_path`` relative
        to the app section. Validators run after click-extra's built-in
        CLI-parameter strict check (during ``--validate-config``) and after the
        schema callable produces the typed configuration object (during normal
        config loading).

        The list is seeded with click-extra's built-in validators (currently the
        one for ``[tool.<cli>.themes.<name>]`` tables, see
        :func:`click_extra.theme.validate_themes_config`); user-supplied
        validators are appended after them. App code that registers its own
        validator on the same ``extension_path`` simply runs alongside the
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
        :class:`~click_extra.config.schema.ConfigValidator` registrations. Used by
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
        """Emit DEBUG-level logs for common ``ConfigOption`` misconfigurations.

        The checks help developers catch suboptimal patterns early when running
        with debug logging enabled. Four categories are covered:

        1. Broad glob + narrow (all-literal) format patterns.
        2. Literal default whose filename doesn't match any format pattern.
        3. Format/extension mismatch (unconditional).
        4. Dotfile referenced without ``DOTGLOB`` in ``search_pattern_flags``.
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

        .. danger::
            It is only called once to produce the default exclusion list if the user did
            not provided its own.

            It was not implemented in the constructor but made as a property, to allow
            for a just-in-time call within the current context. Without this trick we could
            not have fetched the CLI name.
        """
        cli = get_current_context().find_root().command
        return frozenset(
            f"{cli.name}{PARAM_PATH_SEP}{p}" for p in DEFAULT_EXCLUDED_PARAMS
        )

    @cached_property
    def file_pattern(self) -> str:
        """Compile all file patterns from the supported formats.

        Uses ``,`` (comma) notation to combine multiple patterns, suitable for
        ``wcmatch`` brace expansion (``{pat1,pat2,...}``).

        Returns a single pattern string.
        """
        patterns = unique(flatten(self.file_format_patterns.values()))
        return ",".join(patterns)

    def default_pattern(self) -> str:
        """Returns the default pattern used to search for the configuration file.

        Defaults to ``<app_dir>/{*.toml,*.json,*.ini}``. Where ``<app_dir>`` is
        produced by the `click.get_app_dir() method
        <https://click.palletsprojects.com/en/stable/api/#click.get_app_dir>`_.
        The result depends on OS and is influenced by the ``roaming`` and
        ``force_posix`` properties.

        Multiple file format patterns are wrapped with ``{…}`` brace-expansion
        syntax so that ``wcmatch.glob`` correctly applies the directory prefix
        to every sub-pattern.

        .. todo::
            Use `platformdirs <https://github.com/tox-dev/platformdirs>`_ for more
            advanced configuration folder detection?
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

        .. code-block:: text

            ~/folder/my_cli/{*.toml,*.json,*.ini}

        Instead of the full absolute path:

        .. code-block:: text

            /home/user/folder/my_cli/{*.toml,*.json,*.ini}

        .. caution::
            This only applies when the ``GLOBTILDE`` flag is set in ``search_pattern_flags``.
        """
        extra = super().get_help_extra(ctx)
        default = self.get_default(ctx)
        if default is NO_CONFIG:
            extra["default"] = "disabled"
        elif self.search_pattern_flags & glob.GLOBTILDE:
            # When the default already starts with ``~`` (user-supplied tilde
            # pattern), use it as-is. Passing through ``Path()`` would
            # normalize forward slashes to backslashes on Windows.
            default_str = str(default)
            extra["default"] = (
                default_str
                if default_str.startswith("~")
                else shrinkuser(Path(default))
            )
        else:
            extra["default"] = str(default)
        return extra

    @staticmethod
    def _find_vcs_root(start: Path) -> Path | None:
        """Walk up from ``start`` looking for a VCS root directory.

        Returns the directory containing one of the VCS directories defined in
        ``VCS_DIRS``, or ``None`` if no VCS root is found before reaching the
        filesystem root.
        """
        current = start if start.is_dir() else start.parent
        for directory in (current, *current.parents):
            if any((directory / vcs_dir).exists() for vcs_dir in VCS_DIRS):
                return directory
        return None

    def _resolve_stop_at(self, start_dir: Path) -> Path | None:
        """Resolve the ``stop_at`` value to an absolute ``Path`` or ``None``.

        - ``None`` → ``None`` (no boundary).
        - ``VCS`` → calls ``_find_vcs_root(start_dir)``.
        - ``Path`` or other ``str`` → resolves to absolute.
        """
        if self.stop_at is None:
            return None
        if self.stop_at is VCS:
            return self._find_vcs_root(start_dir)
        # Mypy cannot narrow ``Literal[Sentinel.VCS]`` via the ``is`` check above.
        assert isinstance(self.stop_at, (str, Path))
        return Path(self.stop_at).resolve()

    @staticmethod
    def _should_stop_walking(directory: Path, stop_at: Path | None) -> bool:
        """Return ``True`` if the parent-directory walk should stop.

        Stops when:
        - ``stop_at`` is set and ``directory`` is not equal to or a child of it.
        - The directory exists but is not readable.
        """
        if stop_at is not None:
            try:
                directory.relative_to(stop_at)
            except ValueError:
                return True
        return bool(directory.exists() and not os.access(directory, os.R_OK))

    def parent_patterns(self, pattern: str) -> Iterable[tuple[str | None, str]]:
        """Generate ``(root_dir, file_pattern)`` pairs for searching.

        Each yielded pair can be passed directly to
        ``glob.iglob(file_pattern, root_dir=root_dir)`` so that every
        sub-pattern (whether from ``BRACE`` or ``SPLIT`` expansion) is
        correctly scoped to the same directory.

        ``root_dir`` is ``None`` for entirely magic patterns that will be
        evaluated relative to the current working directory.

        Stops when reaching the root folder, the ``stop_at`` boundary, or an
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

    def search_and_read_file(self, pattern: str) -> Iterable[tuple[Path | URL, str]]:
        """Search filesystem or URL for files matching the ``pattern``.

        If ``pattern`` is an URL, download its content. A pattern is considered an URL
        only if it validates as one and starts with ``http://`` or ``https://``. All
        other patterns are considered glob patterns for local filesystem search.

        Returns an iterator of the normalized location and its raw content, for each
        one matching the pattern. Only files are returned, directories are silently
        skipped.

        This method returns the raw content of all matching patterns, without trying to
        parse them. If the content is empty, it is still returned as-is.

        Also includes lookups into parents directories if ``self.search_parents`` is
        ``True``.

        Raises ``FileNotFoundError`` if no file was found after searching all locations.
        """
        files_found = 0

        # Check if the pattern is an URL.
        location = URL(pattern)
        location.normalize()
        if location and location.scheme in ("http", "https"):
            # It's an URL, try to download it.
            logger.debug(f"Download file from URL: {location}")
            with requests.get(str(location)) as response:
                if response.ok:
                    files_found += 1
                    # TODO: use mime-type to guess file format?
                    yield location, response.text
                else:
                    logger.warning(f"Can't download {location}: {response.reason}")

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
                for file in glob.iglob(
                    file_pattern,
                    root_dir=root_dir,
                    flags=self.search_pattern_flags,
                ):
                    base = Path(root_dir) if root_dir else Path()
                    file_path = (base / file).resolve()
                    logger.debug(f"Found candidate: {file_path}")
                    if not file_path.is_file():
                        logger.debug(f"Skipping non-file {file_path}")
                        continue
                    files_found += 1
                    yield file_path, file_path.read_text(encoding="utf-8")

        if not files_found:
            raise FileNotFoundError(f"No file found matching {pattern}")

    def parse_conf(
        self,
        content: str,
        formats: Sequence[ConfigFormat],
    ) -> Iterable[dict[str, Any] | None]:
        """Parse the ``content`` with the given ``formats``.

        Tries to parse the given raw ``content`` string with each of the given
        ``formats``, in order. Yields the resulting data structure for each
        successful parse.

        .. attention::
            Formats whose parsing raises an exception or does not return a ``dict``
            are considered a failure and are skipped.

            This follows the *parse, don't validate* principle.
        """

        conf = None
        for fmt in formats:
            try:
                conf = (
                    self.load_ini_config(content)
                    if fmt is ConfigFormat.INI
                    else parse_content(fmt, content)
                )

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

    def _search_pyproject_cwd(
        self,
    ) -> tuple[Path, dict[str, Any]] | tuple[None, None]:
        """Search for ``pyproject.toml`` from CWD upward to the VCS root.

        Mimics the discovery behavior of uv, ruff, and mypy: start in the
        current working directory and walk up until a ``pyproject.toml``
        containing a ``[tool.<cli_name>]`` section is found, or the VCS root
        (or filesystem root) is reached.

        A ``pyproject.toml`` without a ``[tool.<cli_name>]`` section is
        skipped so unrelated project configs (like a dotfiles repo's
        ``[tool.ruff]``) do not shadow the user's app-dir config; the
        caller falls back to the standard app-dir search instead.

        Only runs when ``ConfigFormat.PYPROJECT_TOML`` is in
        ``file_format_patterns``. Returns ``(path, parsed_tool_section)`` on
        success, or ``(None, None)`` if no valid ``pyproject.toml`` was found.
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
                content = candidate.read_text(encoding="UTF-8")
            except OSError as ex:
                logger.debug(f"Cannot read {candidate}: {ex}")
                continue

            for conf in self.parse_conf(
                content, formats=(ConfigFormat.PYPROJECT_TOML,)
            ):
                if conf and cli_name in conf:
                    return candidate, conf
            logger.debug(
                f"{candidate} has no [tool.{cli_name}] section; "
                "falling back to app-dir search."
            )

        return None, None

    def read_and_parse_conf(
        self,
        pattern: str,
    ) -> tuple[Path | URL, dict[str, Any]] | tuple[None, None]:
        """Search for a parseable configuration file.

        Returns the location and data structure of the first configuration matching the
        ``pattern``.

        Only return the first match that:

        - exists,
        - is a file,
        - is not empty,
        - match file format patterns,
        - can be parsed successfully, and
        - produce a non-empty data structure.

        Raises ``FileNotFoundError`` if no configuration file was found matching the
        criteria above.

        Returns ``(None, None)`` if files were found but none could be parsed.
        """

        for location, content in self.search_and_read_file(pattern):
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
                continue

            logger.debug(
                f"Parsing {location} with {','.join(map(str, matching_formats))}"
            )
            for conf in self.parse_conf(content, formats=matching_formats):
                if conf:
                    return location, conf
                logger.debug("Empty configuration, try next file.")

        return None, None

    def load_ini_config(self, content: str) -> dict[str, Any]:
        """Utility method to parse INI configuration file.

        Internal convention is to use a dot (``.``, as set by
        :data:`~click_extra.parameters.PARAM_PATH_SEP`) in section IDs as a
        separator between levels. This is a workaround the limitation of ``INI``
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

    def _app_section_name(self, ctx: click.Context) -> str:
        """Return the app section name used for both schema processing and opaque
        path resolution.

        Matches the name resolution logic in :py:meth:`_apply_config_schema`:
        prefers the root command's name, falls back to ``ctx.info_name``, and
        defaults to empty string for fully-defensive callers.
        """
        return ctx.find_root().command.name or ctx.info_name or ""

    def _app_section(
        self,
        ctx: click.Context,
        user_conf: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Return ``(app_name, app_section)`` for the current context.

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
        the app name when stripping. Returns ``normalized_conf`` unchanged if no
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
        ``ctx.meta[click_extra.context.TOOL_CONFIG]``.
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
        """Build per-invocation theme overrides from the config and stash on ``ctx.meta``.

        Reads the ``[tool.<cli>.themes.<name>]`` sub-tree, builds each entry into
        a :class:`HelpTheme <click_extra.theme.HelpTheme>` (cascading
        on top of an existing built-in theme when *name* matches one already in
        :data:`~click_extra.theme.theme_registry`), and writes the result to
        ``ctx.meta[click_extra.context.THEME_OVERRIDES]``. The module-level
        registry is never mutated, so themes defined here apply to the current
        invocation only.

        Validation already happened via the built-in
        :func:`~click_extra.theme.validate_themes_config` validator, so failures
        below this point would be a click-extra bug rather than user error.
        """
        from ..theme import themes_from_config

        _, app_section = self._app_section(ctx, user_conf)
        themes_subtree = app_section.get(THEMES_CONFIG_KEY)
        if not isinstance(themes_subtree, dict) or not themes_subtree:
            return
        overrides = themes_from_config(themes_subtree)
        if overrides:
            context.set(ctx, context.THEME_OVERRIDES, overrides)

    def merge_default_map(self, ctx: click.Context, user_conf: dict) -> None:
        """Save the user configuration into the context's ``default_map``.

        Merge the user configuration into the pre-computed template structure, which
        will filter out all unrecognized options not supported by the command. Then
        cleans up blank values and update the context's ``default_map``.

        Uses a `~collections.ChainMap` so each config source keeps its own layer.
        The first layer wins on key lookup, which makes parameter-source precedence
        explicit and future-proofs for multi-file config loading.

        Opaque sub-trees declared by the schema or by registered
        :class:`~click_extra.config.schema.ConfigValidator` instances are stripped from the conf before the
        CLI-parameter strict check, so user-controlled keys (like mappings whose
        keys are data, not flag names) don't trip ``strict=True``.
        """
        normalized_conf = _expand_dotted_keys(
            _strip_reserved_keys(user_conf), strict=self.strict
        )
        normalized_conf = self._strip_opaque_from_conf(ctx, normalized_conf)
        filtered_conf = _recursive_update(
            copy.deepcopy(self.params_template), normalized_conf, self.strict
        )

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

        User configuration is merged to the `context's default_map
        <https://click.palletsprojects.com/en/stable/commands/#overriding-defaults>`_,
        `like Click does
        <https://click.palletsprojects.com/en/stable/commands/#context-defaults>`_.

        By relying on Click's ``default_map``, we make sure that precedence is
        respected. Direct CLI parameters, environment variables or interactive prompts
        take precedence over any values from the config file.

        ..hint::
            Once loading is complete, the resolved file path and its full parsed content
            are stored in ``ctx.meta[click_extra.context.CONF_SOURCE]`` and
            ``ctx.meta[click_extra.context.CONF_FULL]`` respectively. This is the
            recommended way to identify which configuration file was loaded.

            We intentionally do not
            add a custom ``ParameterSource.CONFIG_FILE`` enum member: ``ParameterSource``
            is a closed enum in Click, and monkeypatching it would be fragile. Besides,
            config values end up in ``default_map``, so Click already reports them as
            ``ParameterSource.DEFAULT_MAP``, which is accurate.
        """
        # Skip file I/O and ctx.meta writes during help rendering, shell
        # completion, and any ``make_context(resilient_parsing=True)`` path.
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

        # Search for pyproject.toml from CWD upward before the standard
        # app-dir search. This matches the discovery behavior of uv, ruff,
        # and mypy. Only runs on auto-discovery (not explicit --config).
        conf_path: Path | URL | None = None
        user_conf = None
        if (
            not explicit_conf
            and ConfigFormat.PYPROJECT_TOML in self.file_format_patterns
        ):
            conf_path, user_conf = self._search_pyproject_cwd()
            if conf_path is not None:
                logger.debug(f"Using {conf_path} from CWD search.")

        # Fall back to the standard app-dir search if CWD search found nothing.
        if user_conf is None:
            try:
                conf_path, user_conf = self.read_and_parse_conf(path_pattern)
            # Exit the CLI if no user-provided config file was found. Else, it
            # means we were just trying to automatically discover a config file
            # with the default pattern, so we can just log it and continue.
            except FileNotFoundError:
                message = "No configuration file found."
                if explicit_conf:
                    logger.critical(message)
                    ctx.exit(2)
                else:
                    logger.debug(message)
            else:
                if user_conf is None:
                    formats = list(map(str, self.file_format_patterns))
                    message = (
                        f"Error parsing file as "
                        f"{', '.join(formats[:-1])} or {formats[-1]}."
                    )
                    if explicit_conf:
                        logger.critical(message)
                        ctx.exit(2)
                    else:
                        logger.debug(message)

        # Apply the loaded configuration (from CWD or app-dir search).
        if user_conf is not None:
            logger.debug(f"Parsed user configuration: {user_conf}")
            logger.debug(f"Initial defaults: {ctx.default_map}")

            # Run every check through the unified pipeline. collect_all=False
            # fails fast: the first error is surfaced as a clean critical-level
            # log and the context exits 1, before any subcommand callback fires,
            # rather than letting an exception bubble up as a traceback. Exit
            # code 1 matches ``--validate-config`` for the same failure mode.
            report = run_config_validation(
                user_conf,
                app_name=self._app_section_name(ctx),
                params_template=self.params_template,
                config_schema=self.config_schema,
                config_validators=self.config_validators,
                fallback_sections=self.fallback_sections,
                schema_strict=self.schema_strict,
                strict=self.strict,
                collect_all=False,
            )
            if not report.ok:
                logger.critical(f"Configuration validation error: {report.errors[0]}")
                ctx.exit(1)

            # Validation passed. Merge the recognized values into default_map,
            # publish the typed schema instance built by the pipeline, then apply
            # theme overrides (the [tool.<cli>.themes.<name>] table was already
            # validated above, so building it here cannot surface user error).
            self.merge_default_map(ctx, user_conf)
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


def _require_sibling_config_option(
    params: Sequence[click.Parameter],
    requester: click.Parameter,
) -> ConfigOption:
    """Return the sibling :class:`ConfigOption` declared on the same command.

    Both ``--no-config`` and ``--validate-config`` are inert on their own: they
    drive the parsing machinery owned by ``--config``. This helper centralizes
    the lookup so both raise the same ``RuntimeError`` (rather than the historic
    mix of ``RuntimeError`` and ``TypeError``) when no ``ConfigOption`` is found
    on the command, naming the offending flag in the message.

    :param params: The command's parameter list to scan.
    :param requester: The option requiring the sibling, used to build the error
        message from its flag names and class.
    """
    config_option = search_params(params, ConfigOption)
    if not isinstance(config_option, ConfigOption):
        # RuntimeError (not the type-implied TypeError) is intentional: it keeps
        # the historical --no-config contract and unifies both call sites on one
        # exception type for a missing-or-wrong-type sibling.
        raise RuntimeError(  # noqa: TRY004
            f"{'/'.join(requester.opts)} {type(requester).__name__} must be used "
            f"alongside {ConfigOption.__name__}."
        )
    return config_option


class NoConfigOption(ExtraOption):
    """A pre-configured option adding ``--no-config``.

    This option is supposed to be used alongside the ``--config`` option
    (``ConfigOption``) to allow users to explicitly disable the use of any
    configuration file.

    This is especially useful to debug side-effects caused by autodetection of
    configuration files.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        type=UNPROCESSED,
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
        """``flag_value=NO_CONFIG`` is the ``Sentinel`` enum member that
        signals "skip configuration loading" to :class:`ConfigOption`. Click
        ``8.4.0`` (PR `pallets/click#3363
        <https://github.com/pallets/click/pull/3363>`_) auto-detects
        ``type=UNPROCESSED`` for non-basic ``flag_value`` types, but click-extra
        still supports Click ``8.3.x`` where that auto-detection is absent, so the
        ``type=UNPROCESSED`` override is kept explicit to let the sentinel pass
        through ``Option`` unchanged on every supported Click.

        .. seealso::
            An alternative implementation of this class would be to create a custom
            `click.ParamType
            <https://click.palletsprojects.com/en/stable/api/#click.ParamType>`_
            instead of a custom ``Option`` subclass. `Here is for example
            <https://github.com/pallets/click/issues/3024#issuecomment-3146511356>`_.
        """
        if not param_decls:
            param_decls = ("--no-config", CONFIG_OPTION_NAME)

        kwargs.setdefault("callback", self.check_sibling_config_option)

        super().__init__(
            param_decls=param_decls,
            type=type,
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
        """Ensure that this option is used alongside a ``ConfigOption`` instance."""
        _require_sibling_config_option(ctx.command.params, param)


class ValidateConfigOption(ExtraOption):
    """A pre-configured option adding ``--validate-config CONFIG_PATH``.

    Loads the config file at the given path, validates it against the CLI's
    parameter structure in strict mode, reports results, and exits.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        type: click.ParamType | Any = ClickPath(
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
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
        :class:`~click_extra.config.schema.ValidationError` shape so the reported path is always rooted at
        the configuration file:

        1. CLI-parameter strict check on the non-opaque part of the document.
        2. Schema processing, if a ``config_schema`` is configured: catches
           type errors and unknown keys inside the dataclass-described section.
        3. Each registered :class:`~click_extra.config.schema.ConfigValidator` runs against its declared
           opaque sub-tree.

        Every detected error is emitted before exiting, so a single
        ``--validate-config`` run surfaces the full list of fixes the user
        needs to apply.
        """
        if not value:
            return

        info_msg: Callable[..., None] = partial(echo, err=True)

        # Find the sibling ConfigOption to reuse its parsing machinery.
        config_option = _require_sibling_config_option(ctx.command.params, param)

        # Read and parse the config file.
        try:
            _conf_path, user_conf = config_option.read_and_parse_conf(value)
        except FileNotFoundError:
            info_msg(f"Configuration file not found: {value}")
            ctx.exit(2)

        if user_conf is None:
            formats = list(map(str, config_option.file_format_patterns))
            info_msg(
                f"Error parsing {value} as {', '.join(formats[:-1])} or {formats[-1]}."
            )
            ctx.exit(2)

        # Delegate every check to the unified pipeline in collect-all mode so a
        # single run surfaces the full punch list. ``--validate-config`` always
        # runs the CLI-parameter check in strict mode regardless of the sibling
        # option's ``strict`` setting; schema strictness honors the option's
        # configured ``schema_strict``.
        report = run_config_validation(
            user_conf,
            app_name=config_option._app_section_name(ctx),
            params_template=config_option.params_template,
            config_schema=config_option.config_schema,
            config_validators=config_option.config_validators,
            fallback_sections=config_option.fallback_sections,
            schema_strict=config_option.schema_strict,
            strict=True,
            collect_all=True,
        )

        if not report.ok:
            for error in report.errors:
                info_msg(f"Configuration validation error: {error}")
            ctx.exit(1)

        info_msg(f"Configuration file {value} is valid.")
        ctx.exit(0)


# --- Click Extra's own configuration schema -----------------------------------


@dataclass
class TestPlanConfig:
    """Config schema for a project's test plan, read from ``[tool.<cli>.test-plan]``.

    The ``test-plan`` CLI command resolves its cases from this config when no
    plan is given on the command line. Map it onto an app's config section with
    a field carrying ``metadata={"click_extra.config_path": "test-plan"}``.
    """

    file: str = "./tests/cli-test-plan.yaml"
    """Path to a YAML test plan file, resolved relative to the project root."""

    inline: str | None = None
    """Inline YAML test plan, an alternative to :attr:`file`. Takes precedence."""

    timeout: int | None = None
    """Default timeout (seconds) for each case that does not set its own.

    ``None`` leaves cases unbounded unless ``--timeout`` is passed.
    """


@dataclass
class PrebakeConfig:
    """Config schema for the prebake commands, read from ``[tool.<cli>.prebake]``.

    Lets a project pin the target ``__init__.py`` once for its build pipeline,
    instead of passing ``--module`` to every ``click-extra prebake`` command.
    """

    module: str | None = None
    """Path to the ``__init__.py`` to pre-bake, resolved relative to the project
    root. Overrides the ``[project.scripts]`` auto-discovery; leave unset to keep
    it."""


@dataclass
class ClickExtraConfig:
    """Schema for the ``[tool.click-extra]`` configuration section.

    Wired as the ``config_schema`` of the top-level ``click-extra`` group, so
    every subcommand reads the same section and pulls its own sub-table through
    :func:`~click_extra.config.schema.get_tool_config`.
    """

    test_plan: TestPlanConfig = field(
        default_factory=TestPlanConfig,
        metadata={"click_extra.config_path": "test-plan"},
    )
    """The ``[tool.click-extra.test-plan]`` sub-table (file/inline/timeout)."""

    prebake: PrebakeConfig = field(
        default_factory=PrebakeConfig,
        metadata={"click_extra.config_path": "prebake"},
    )
    """The ``[tool.click-extra.prebake]`` sub-table (target module)."""
