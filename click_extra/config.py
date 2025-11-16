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

.. todo::
    Add a ``ParameterSource.CONFIG_FILE`` entry to the ``ParameterSource`` enum?
    Also see: https://github.com/pallets/click/issues/2879
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Iterable
from configparser import ConfigParser, ExtendedInterpolation
from enum import Enum
from functools import cached_property, partial
from gettext import gettext as _
from pathlib import Path

import requests
from boltons.iterutils import flatten, unique
from boltons.pathutils import shrinkuser
from boltons.urlutils import URL
from deepmerge import always_merger
from extra_platforms import is_windows
from extra_platforms.platform import _recursive_update, _remove_blanks
from wcmatch import fnmatch, glob

from . import (
    UNPROCESSED,
    ParameterSource,
    echo,
    get_app_dir,
    get_current_context,
)
from .parameters import ExtraOption, ParamStructure, search_params

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]


TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any, Literal

    import click


yaml_support = True
try:
    import yaml  # noqa: F401
except ImportError:
    yaml_support = False
    logging.getLogger("click_extra").debug(
        "YAML support disabled: install click-extra[yaml] to enable it."
    )


json5_support = True
try:
    import json5  # noqa: F401
except ImportError:
    json5_support = False
    logging.getLogger("click_extra").debug(
        "JSON5 support disabled: install click-extra[json5] to enable it."
    )


jsonc_support = True
try:
    import jsonc  # noqa: F401
except ImportError:
    jsonc_support = False
    logging.getLogger("click_extra").debug(
        "JSONC support disabled: install click-extra[jsonc] to enable it."
    )


hjson_support = True
try:
    import hjson  # noqa: F401
except ImportError:
    hjson_support = False
    logging.getLogger("click_extra").debug(
        "HJSON support disabled: install click-extra[hjson] to enable it."
    )


xml_support = True
try:
    import xmltodict  # noqa: F401
except ImportError:
    xml_support = False
    logging.getLogger("click_extra").debug(
        "XML support disabled: install click-extra[xml] to enable it."
    )


class ConfigFormat(Enum):
    """All configuration formats, associated to their support status.

    The first element of the tuple is a sequence of file extensions associated to the
    format. Patterns are fed to ``wcmatch.glob`` for matching, and are influenced by the
    flags set on the ``ConfigOption`` instance.

    The second element indicates whether the format is supported or not, depending on
    the availability of the required third-party packages. This evaluation is performed
    at runtime when this module is imported.

    .. caution::
        The order is important for both format members and file patterns. It defines the
        priority order in which formats are tried when multiple candidate files are found.

    .. todo::
        Add support for `JWCC
        <https://nigeltao.github.io/blog/2021/json-with-commas-comments.html>`_
        / `hujson <https://github.com/tailscale/hujson>`_ format?
    """

    TOML = (("*.toml",), True)
    YAML = (("*.yaml", "*.yml"), yaml_support)
    JSON = (("*.json",), True)
    JSON5 = (("*.json5",), json5_support)
    JSONC = (("*.jsonc",), jsonc_support)
    HJSON = (("*.hjson",), hjson_support)
    INI = (("*.ini",), True)
    XML = (("*.xml",), xml_support)

    def __str__(self) -> str:
        return self.name.lower()

    @property
    def enabled(self) -> bool:
        """Returns ``True`` if the format is supported, ``False`` otherwise."""
        return self.value[1]  # type: ignore[no-any-return]

    @property
    def patterns(self) -> tuple[str]:
        """Returns the default file patterns associated to the format."""
        return self.value[0]  # type: ignore[no-any-return]


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

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"


NO_CONFIG = Sentinel.NO_CONFIG
"""Sentinel used to indicate that no configuration file must be used at all."""


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
            | glob.SPLIT
            | glob.GLOBTILDE
            | glob.NODIR
        ),
        search_parents: bool = False,
        excluded_params: Iterable[str] | None = None,
        strict: bool = False,
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
        """
        logger = logging.getLogger("click_extra")

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

        # Force NODIR to optimize search for files only.
        if not search_pattern_flags & glob.NODIR:
            logger.warning("Forcing NODIR flag for search patterns.")
            search_pattern_flags |= glob.NODIR

        self.search_pattern_flags = search_pattern_flags
        """Flags provided to all calls of ``wcmatch.glob``.

        Applies to both the default pattern and any user-provided pattern.

        .. important::
            The ``NODIR`` flag is always forced, to optimize the search for files only.
        """

        self.search_parents = search_parents
        """Indicates whether to walk back the tree of parent folders when searching for
        configuration files.
        """

        # If the user provided its own excluded params, freeze them now and store it
        # to prevent the dynamic default property to be called.
        if excluded_params is not None:
            self.excluded_params = frozenset(excluded_params)

        self.strict = strict
        """Defines the strictness of the configuration loading.

        - If ``True``, raise an error if the configuration file contain parameters not
          recognized by the CLI.
        - If ``False``, silently ignore unrecognized parameters.
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
            f"{cli.name}{ParamStructure.SEP}{p}" for p in DEFAULT_EXCLUDED_PARAMS
        )

    @cached_property
    def file_pattern(self) -> str:
        """Compile all file patterns from the supported formats.

        Use ``|`` split notation to combine multiple patterns.

        Returns a single pattern string.
        """
        patterns = unique(flatten(self.file_format_patterns.values()))
        return "|".join(patterns)

    def default_pattern(self) -> str:
        """Returns the default pattern used to search for the configuration file.

        Defaults to ``<app_dir>/*.toml|*.json|*.ini``. Where ``<app_dir>`` is produced by
        the `clickget_app_dir() method
        <https://click.palletsprojects.com/en/stable/api/#click.get_app_dir>`_.
        The result depends on OS and is influenced by the ``roaming`` and
        ``force_posix`` properties.

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
        return f"{app_dir}{os.path.sep}{self.file_pattern}"

    def get_help_extra(self, ctx: click.Context) -> click.types.OptionHelpExtra:
        """Replaces the default value of the configuration option.

        Display a pretty path that is relative to the user's home directory:

        .. code-block:: text

            ~/folder/my_cli/*.toml|*.json|*.ini

        Instead of the full absolute path:

        .. code-block:: text

            /home/user/folder/my_cli/*.toml|*.json|*.ini

        .. caution::
            This only applies when the ``GLOBTILDE`` flag is set in ``search_pattern_flags``.
        """
        extra = super().get_help_extra(ctx)
        if self.search_pattern_flags & glob.GLOBTILDE:
            default = shrinkuser(Path(self.get_default(ctx)))
        extra["default"] = default
        return extra

    def parent_patterns(self, pattern: str) -> Iterable[str]:
        """Generate patterns for parent directories lookup.

        Yields patterns for each parent directory of the given ``pattern``.

        The first yielded pattern is the original one.

        Stops when reaching the root folder.
        """
        # Return the original pattern as-is.
        yield pattern

        # No parent search requested, stop here.
        if not self.search_parents:
            return

        logger = logging.getLogger("click_extra")
        logger.debug("Parent search enabled.")

        # The pattern is a regular path: no magic is involved. Simply walk up.
        if not glob.is_magic(pattern, flags=self.search_pattern_flags):
            search_path = Path(pattern).resolve()
            if search_path.is_file():
                search_path = search_path.parent

            yield from map(str, (search_path, *search_path.parents))
            return

        # Magic patterns needs special handling for parent search.
        raise NotImplementedError("Parent search for magic patterns not implemented.")

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
        logger = logging.getLogger("click_extra")
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

            for search_pattern in self.parent_patterns(pattern):
                for file in glob.iglob(search_pattern, flags=self.search_pattern_flags):
                    logger.debug(f"Found candidate: {file}")
                    file_path = Path(file).resolve()
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
        logger = logging.getLogger("click_extra")

        conf = None
        for fmt in formats:
            try:
                match fmt:
                    case ConfigFormat.TOML:
                        conf = tomllib.loads(content)
                    case ConfigFormat.YAML:
                        conf = yaml.full_load(content)
                    case ConfigFormat.JSON:
                        conf = json.loads(content)
                    case ConfigFormat.JSON5:
                        conf = json5.loads(content)
                    case ConfigFormat.JSONC:
                        conf = jsonc.loads(content)
                    case ConfigFormat.HJSON:
                        conf = hjson.loads(content)
                    case ConfigFormat.INI:
                        conf = self.load_ini_config(content)
                    case ConfigFormat.XML:
                        conf = xmltodict.parse(content)

            except Exception as ex:
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
        logger = logging.getLogger("click_extra")

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

        Internal convention is to use a dot (``.``, as set by ``self.SEP``) in
        section IDs as a separator between levels. This is a workaround
        the limitation of ``INI`` format which doesn't allow for sub-sections.

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
                    target_types = self.get_tree_value(
                        self.params_types, section_id, option_id
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
                    assert isinstance(target_types, list)
                    # We deduplicate them to simplify the next steps. If we are lucky,
                    # all options sharing the same name also share the same type.
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
                conf, self.init_tree_dict(*section_id.split(self.SEP), leaf=sub_conf)
            )

        return conf

    def merge_default_map(self, ctx: click.Context, user_conf: dict) -> None:
        """Save the user configuration into the context's ``default_map``.

        Merge the user configuration into the pre-computed template structure, which
        will filter out all unrecognized options not supported by the command. Then
        cleans up blank values and update the context's ``default_map``.
        """
        filtered_conf = _recursive_update(self.params_template, user_conf, self.strict)

        # Clean-up the conf by removing all blank values left-over by the template
        # structure.
        clean_conf = _remove_blanks(filtered_conf, remove_str=False)

        # Update the default_map.
        if ctx.default_map is None:
            ctx.default_map = {}
        ctx.default_map.update(clean_conf.get(ctx.find_root().command.name, {}))

    def load_conf(
        self,
        ctx: click.Context,
        param: click.Parameter,
        path_pattern: str | Path | Literal[Sentinel.NO_CONFIG],
    ) -> None:
        """Fetch parameters values from configuration file and sets them as defaults.

        User configuration is merged to the `context's default_map
        <https://click.palletsprojects.com/en/stable/commands/#overriding-defaults>`_,
        `like Click does
        <https://click.palletsprojects.com/en/stable/commands/#context-defaults>`_.

        By relying on Click's ``default_map``, we make sure that precedence is
        respected. And direct CLI parameters, environment variables or interactive
        prompts takes precedence over any values from the config file.
        """
        logger = logging.getLogger("click_extra")

        # In this function we would like to inform the user of what we're doing.
        # In theory we could use logger.info() for that, but the logger is stuck to its
        # default WARNING level at this point, because the defaults have not been
        # loaded yet. So we use echo() to print messages to stderr instead.
        info_msg = partial(echo, err=True)

        if path_pattern is NO_CONFIG:
            logger.debug(f"{NO_CONFIG} received.")
            info_msg("Skip configuration file loading altogether.")
            return

        explicit_conf = ctx.get_parameter_source(self.name) in (  # type: ignore[arg-type]
            ParameterSource.COMMANDLINE,
            ParameterSource.ENVIRONMENT,
            ParameterSource.PROMPT,
        )  # type: ignore[operator]

        # Print configuration location to the user if it was explicitly set.
        # Normalize to string to both allow parsing as a glob pattern or URL.
        if isinstance(path_pattern, Path):
            # Normalize the path without checking for its existence.
            path_pattern = str(path_pattern.resolve(strict=False))
        message = f"Load configuration matching {path_pattern}"
        if explicit_conf:
            info_msg(message)
        else:
            logger.debug(message)

        # Read configuration file.
        conf_path, user_conf = None, None
        try:
            conf_path, user_conf = self.read_and_parse_conf(path_pattern)
        # Exit the CLI if no user-provided config file was found. Else, it means we
        # were just trying to automaticcaly discover a config file with the default
        # pattern, so we can just log it and continue.
        except FileNotFoundError:
            message = "No configuration file found."
            if explicit_conf:
                logger.critical(message)
                ctx.exit(2)
            else:
                logger.debug(message)

        # Exit the CLI if a user-provided config file was found but could not be
        # parsed. Else, it means we automaticcaly discovered a config file, but it
        # couldn't be parsed, so we can just log it and continue.
        else:
            if user_conf is None:
                message = (
                    "Error parsing file as "
                    f"{', '.join(map(str, self.file_format_patterns))}."
                )
                if explicit_conf:
                    logger.critical(message)
                    ctx.exit(2)
                else:
                    logger.debug(message)
            else:
                logger.debug(f"Parsed user configuration: {user_conf}")
                logger.debug(f"Initial defaults: {ctx.default_map}")
                self.merge_default_map(ctx, user_conf)
                logger.debug(f"New defaults: {ctx.default_map}")

        # Save the location and content of the configuration file into the context's
        # meta dict, for the convenience of CLI developers.
        ctx.meta["click_extra.conf_source"] = conf_path
        ctx.meta["click_extra.conf_full"] = user_conf


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
        """
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
        config_option = search_params(ctx.command.params, ConfigOption)
        if config_option is None:
            raise RuntimeError(
                f"{'/'.join(param.opts)} {self.__class__.__name__} must be used "
                f"alongside {ConfigOption.__name__}."
            )
