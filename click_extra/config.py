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

.. todo::
    Add a ``--dump-config`` or ``--export-config`` option to write down the current
    configuration (or a template) into a file or ``<stdout>``.

    Help message would be: *you can use this option with other options or environment
    variables to have them set in the generated configuration*.

.. todo::
    Allow the ``--config`` option to walk-up the filesystem (up until the filesystem
    root) to discover configuration files.
    See: https://github.com/kdeldycke/click-extra/issues/651

.. todo::
    Add a ``ParameterSource.CONFIG_FILE`` entry to the ``ParameterSource`` enum?
    Also see: https://github.com/pallets/click/issues/2879
"""

from __future__ import annotations

import enum
import json
import logging
import os
import tomllib
from configparser import ConfigParser, ExtendedInterpolation
from enum import Enum
from functools import partial
from gettext import gettext as _
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

import click
import requests
import xmltodict
import yaml
from boltons.iterutils import flatten
from boltons.pathutils import shrinkuser
from boltons.urlutils import URL
from deepmerge import always_merger
from extra_platforms import is_windows
from extra_platforms.platform import _recursive_update, _remove_blanks
from wcmatch.glob import (
    BRACE,
    DOTGLOB,
    FOLLOW,
    GLOBSTAR,
    GLOBTILDE,
    IGNORECASE,
    NODIR,
    iglob,
)

from . import (
    UNPROCESSED,
    Context,
    Parameter,
    ParameterSource,
    echo,
    get_app_dir,
    get_current_context,
)
from .parameters import ExtraOption, ParamStructure, search_params


class Formats(Enum):
    """Supported configuration formats and the list of their default extensions.

    The default order set the priority by which each format is searched for the default
    configuration file.
    """

    TOML = ("toml",)
    YAML = ("yaml", "yml")
    JSON = ("json",)
    INI = ("ini",)
    XML = ("xml",)


CONFIG_OPTION_NAME = "config"
"""Hardcoded name of the configuration option.

This name is going to be shared by both the ``--config`` and ``--no-config`` options
below, so they can compete with each other to either set a path pattern or disable the
use of any configuration file at all.
"""


class Sentinel(enum.Enum):
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

T_NO_CONFIG = Literal[NO_CONFIG]  # type: ignore[valid-type]
"""Type hint for the :data:`NO_CONFIG` sentinel value."""


class ConfigOption(ExtraOption, ParamStructure):
    """A pre-configured option adding ``--config CONFIG_PATH``."""

    formats: Sequence[Formats]

    roaming: bool
    force_posix: bool

    strict: bool

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        metavar="CONFIG_PATH",
        type=UNPROCESSED,
        help=_(
            "Location of the configuration file. Supports glob pattern of local "
            "path and remote URL.",
        ),
        is_eager=True,
        expose_value=False,
        formats=tuple(Formats),
        roaming=True,
        force_posix=False,
        excluded_params=None,
        strict=False,
        **kwargs,
    ) -> None:
        """Takes as input a glob pattern or an URL.

        Glob patterns must follow the syntax of `wcmatch.glob
        <https://facelessuser.github.io/wcmatch/glob/#syntax>`_.

        - ``is_eager`` is active by default so the config option's ``callback``
          gets the opportunity to set the ``default_map`` values before the
          other options use them.

        - ``formats`` is the ordered list of formats that the configuration
          file will be tried to be read with. Can be a single one.

        - ``roaming`` and ``force_posix`` are `fed to click.get_app_dir()
          <https://click.palletsprojects.com/en/stable/api/#click.get_app_dir>`_
          to setup the default configuration folder.

        - ``excluded_params`` is a list of options to ignore by the configuration
          parser. See ``ParamStructure.excluded_params`` for the default values.

        - ``strict``
            - If ``True``, raise an error if the configuration file contain
              unrecognized content.
            - If ``False``, silently ignore unsupported configuration option.
        """
        if not param_decls:
            param_decls = ("--config", CONFIG_OPTION_NAME)

        # Make sure formats ends up as an iterable.
        if isinstance(formats, Formats):
            formats = (formats,)
        self.formats = formats

        # Setup the configuration default folder.
        self.roaming = roaming
        self.force_posix = force_posix
        kwargs.setdefault("default", self.default_pattern)

        if excluded_params is not None:
            self.excluded_params = excluded_params

        self.strict = strict

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

    def default_pattern(self) -> str:
        """Returns the default pattern used to search for the configuration file.

        Defaults to ``/<app_dir>/*.{toml,yaml,yml,json,ini,xml}``. Where
        ``<app_dir>`` is produced by the `clickget_app_dir() method
        <https://click.palletsprojects.com/en/stable/api/#click.get_app_dir>`_.
        The result depends on OS and is influenced by the ``roaming`` and
        ``force_posix`` properties of this instance.

        In that folder, we're looking for any file matching the extensions
        derived from the ``self.formats`` property:

        - a simple ``*.ext`` pattern if only one format is set
        - an expanded ``*.{ext1,ext2,...}`` pattern if multiple formats are set
        """
        ctx = get_current_context()
        cli_name = ctx.find_root().info_name
        if not cli_name:
            raise ValueError
        app_dir = Path(
            get_app_dir(cli_name, roaming=self.roaming, force_posix=self.force_posix),
        ).resolve()
        # Build the extension matching pattern.
        extensions = flatten(f.value for f in self.formats)
        if len(extensions) == 1:
            ext_pattern = extensions[0]
        else:
            # Use brace notation for multiple extension matching.
            ext_pattern = f"{{{','.join(extensions)}}}"
        return f"{app_dir}{os.path.sep}*.{ext_pattern}"

    def get_help_extra(self, ctx: Context) -> click.types.OptionHelpExtra:
        """Replaces the default value of the configuration option.

        Display a pretty path that is relative to the user's home directory:

        .. code-block:: text

            ~/(...)/multiple_envvars.py/*.{toml,yaml,yml,json,ini,xml}
        """
        extra = super().get_help_extra(ctx)
        extra["default"] = shrinkuser(Path(self.get_default(ctx)))  # type: ignore[arg-type]
        return extra

    def search_and_read_conf(self, pattern: str) -> Iterable[tuple[Path | URL, str]]:
        """Search on local file system or remote URL files matching the provided
        pattern.

        ``pattern`` is considered an URL only if it is parseable as such and starts
        with ``http://`` or ``https://``.

        Returns an iterator of the normalized configuration location and its textual
        content, for each file/URL matching the pattern.

        Raises ``FileNotFoundError`` if no file was found matching the pattern.
        """
        logger = logging.getLogger("click_extra")
        files_found = 0

        # Check if the pattern is an URL.
        location = URL(pattern)
        location.normalize()
        if location and location.scheme in ("http", "https"):
            logger.debug(f"Download configuration from URL: {location}")
            with requests.get(str(location)) as response:
                if response.ok:
                    files_found += 1
                    yield location, response.text
                else:
                    logger.warning(f"Can't download {location}: {response.reason}")

        # Not an URL, search local file system with glob pattern.
        else:
            logger.debug("Pattern is not an URL: search local file system.")
            # wcmatch expect patterns to be written with Unix-like syntax by default,
            # even on Windows. See more details at:
            # https://facelessuser.github.io/wcmatch/glob/#windows-separators
            # https://github.com/facelessuser/wcmatch/issues/194
            if is_windows():
                pattern = pattern.replace("\\", "/")
            for file in iglob(
                pattern,
                flags=NODIR
                | GLOBSTAR
                | DOTGLOB
                | GLOBTILDE
                | BRACE
                | FOLLOW
                | IGNORECASE,
            ):
                file_path = Path(file).resolve()
                logger.debug(f"Configuration file found at {file_path}")
                files_found += 1
                yield file_path, file_path.read_text(encoding="utf-8")

        if not files_found:
            msg = f"No configuration file found matching {pattern}"
            raise FileNotFoundError(msg)

    def parse_conf(self, conf_text: str) -> dict[str, Any] | None:
        """Try to parse the provided content with each format in the order provided by
        the user.

        A successful parsing in any format is supposed to return a ``dict``. Any other
        result, including any raised exception, is considered a failure and the next
        format is tried.
        """
        logger = logging.getLogger("click_extra")

        user_conf = None
        for conf_format in self.formats:
            try:
                match conf_format:
                    case Formats.TOML:
                        user_conf = tomllib.loads(conf_text)
                    case Formats.YAML:
                        user_conf = yaml.full_load(conf_text)
                    case Formats.JSON:
                        user_conf = json.loads(conf_text)
                    case Formats.INI:
                        user_conf = self.load_ini_config(conf_text)
                    case Formats.XML:
                        user_conf = xmltodict.parse(conf_text)

            except Exception as ex:
                logger.debug(f"{conf_format.name} parsing failed: {ex}")
                continue

            if not isinstance(user_conf, dict) or user_conf is None:
                logger.debug(
                    f"{conf_format.name} parsing failed: "
                    f"expecting a dict, got {user_conf!r} instead."
                )
                continue

            logger.debug(f"{conf_format.name} parsing successful, got {user_conf!r}.")
            return user_conf

        # All parsing attempts failed
        return None

    def read_and_parse_conf(
        self,
        pattern: str,
    ) -> tuple[Path | URL, dict[str, Any]] | tuple[None, None]:
        """Search for a configuration file matching the provided pattern.

        Returns the location and parsed content of the first valid configuration file
        that is not blank, or `(None, None)` if no file was found.

        Raises ``FileNotFoundError`` if no file was found matching the pattern.
        """
        logger = logging.getLogger("click_extra")

        for conf_path, conf_text in self.search_and_read_conf(pattern):
            logger.debug(f"Parsing: {conf_text!r}")
            user_conf = self.parse_conf(conf_text)
            if user_conf is not None:
                return conf_path, user_conf
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
                        msg = (
                            f"Cannot handle the {target_types!r} types defined by the "
                            "multiple options associated to the "
                            f"[{section_id}]:{option_id} INI config item."
                        )
                        raise ValueError(msg)
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
                    msg = (
                        f"Cannot handle the conversion of [{section_id}]:{option_id} "
                        f"INI config item to {target_type} type."
                    )
                    raise ValueError(msg)

                sub_conf[option_id] = value

            # Place collected options at the right level of the dict tree.
            conf = always_merger.merge(
                conf, self.init_tree_dict(*section_id.split(self.SEP), leaf=sub_conf)
            )

        return conf

    def merge_default_map(self, ctx: Context, user_conf: dict) -> None:
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
        self, ctx: Context, param: Parameter, path_pattern: str | Path
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
            logger.debug(f"{NO_CONFIG} received.")  # type: ignore[unreachable]
            info_msg("Skip configuration file loading altogether.")
            return

        explicit_conf = ctx.get_parameter_source(self.name) in (  # type: ignore[arg-type]
            ParameterSource.COMMANDLINE,
            ParameterSource.ENVIRONMENT,
            ParameterSource.PROMPT,
        )  # type: ignore[operator]

        # Print configuration location to the user if it was explicitly set.
        if isinstance(path_pattern, Path):
            path_pattern = str(path_pattern)
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
                    f"Error while parsing the configuration file in any of the "
                    f"{', '.join(e.name for e in self.formats)} formats."
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
        self, ctx: Context, param: Parameter, value: int
    ) -> None:
        """Ensure that this option is used alongside a ``ConfigOption`` instance."""
        config_option = search_params(ctx.command.params, ConfigOption)
        if config_option is None:
            raise RuntimeError(
                f"{'/'.join(param.opts)} {self.__class__.__name__} must be used "
                f"alongside {ConfigOption.__name__}."
            )
