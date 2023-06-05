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
"""Utilities to load parameters and options from a configuration file."""

from __future__ import annotations

import logging
import os
import sys
from configparser import ConfigParser, ExtendedInterpolation
from enum import Enum
from gettext import gettext as _
from pathlib import Path
from typing import Iterable, Sequence
from unittest.mock import patch

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import]

import commentjson as json
import requests
import xmltodict
import yaml
from boltons.iterutils import flatten, remap
from boltons.pathutils import shrinkuser
from boltons.urlutils import URL
from mergedeep import merge
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
    STRING,
    ParameterSource,
    echo,
    get_app_dir,
    get_current_context,
)
from .parameters import ExtraOption, ParamStructure
from .platforms import is_windows


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


class ConfigOption(ExtraOption, ParamStructure):
    """A pre-configured option adding ``--config``/``-C`` option."""

    formats: Sequence[Formats]

    roaming: bool
    force_posix: bool

    strict: bool

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        metavar="CONFIG_PATH",
        type=STRING,
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
          <https://click.palletsprojects.com/en/8.1.x/api/#click.get_app_dir>`_
          to setup the default configuration folder.

        - ``excluded_params`` is a list of options to ignore by the
          configuration parser. Defaults to
          ``ParamStructure.DEFAULT_EXCLUDED_PARAMS``.

        - ``strict``
            - If ``True``, raise an error if the configuration file contain
              unrecognized content.
            - If ``False``, silently ignore unsupported configuration option.
        """
        if not param_decls:
            param_decls = ("--config", "-C")

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
        <https://click.palletsprojects.com/en/8.1.x/api/#click.get_app_dir>`_.
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

    def get_help_record(self, ctx):
        """Replaces the default value by the pretty version of the configuration
        matching pattern."""
        # Pre-compute pretty_path to bypass infinite recursive loop on get_default.
        pretty_path = shrinkuser(Path(self.get_default(ctx)))
        with patch.object(ConfigOption, "get_default") as mock_method:
            mock_method.return_value = pretty_path
            return super().get_help_record(ctx)

    def search_and_read_conf(self, pattern: str) -> Iterable[str]:
        """Search on local file system or remote URL files matching the provided
        pattern.

        ``pattern`` is considered as an URL only if it is parseable as such and starts
        with ``http://`` or ``https://``.

        Returns an iterator of raw content for each file/URL matching the
        pattern.
        """
        logger = logging.getLogger("click_extra")

        # Check if the pattern is an URL.
        location = URL(pattern)
        if location and location.scheme.lower() in ("http", "https"):
            logger.debug("Fetch configuration from remote URL.")
            with requests.get(location) as response:
                if response.ok:
                    yield from (response.text,)
                    return
                logger.warning(f"Can't download {location}: {response.reason}")
        else:
            logger.debug("Pattern is not an URL.")

        logger.debug("Search local file system.")
        # wcmatch expect patterns to be written with Unix-like syntax by default, even
        # on Windows. See more details at:
        # https://facelessuser.github.io/wcmatch/glob/#windows-separators
        # https://github.com/facelessuser/wcmatch/issues/194
        if is_windows():
            pattern = pattern.replace("\\", "/")
        for file in iglob(
            pattern,
            flags=NODIR | GLOBSTAR | DOTGLOB | GLOBTILDE | BRACE | FOLLOW | IGNORECASE,
        ):
            file_path = Path(file)
            logger.debug(f"Configuration file found at {file_path}")
            yield file_path.read_text()

    def parse_conf(self, conf_content: str) -> dict | None:
        """Try to parse the provided content with each format in the order provided by
        the user.

        A successful parsing in any format is supposed to return a ``dict``. Any other
        result, including any raised exception, is considered a failure and the next
        format is tried.
        """
        user_conf = None
        for conf_format in self.formats:
            logger = logging.getLogger("click_extra")
            logger.debug(f"Parse configuration as {conf_format.name}...")

            try:
                if conf_format == Formats.TOML:
                    user_conf = tomllib.loads(conf_content)

                elif conf_format == Formats.YAML:
                    user_conf = yaml.full_load(conf_content)

                elif conf_format == Formats.JSON:
                    user_conf = json.loads(conf_content)

                elif conf_format == Formats.INI:
                    user_conf = self.load_ini_config(conf_content)

                elif conf_format == Formats.XML:
                    user_conf = xmltodict.parse(conf_content)

            except Exception as ex:
                logger.debug(ex)
                continue

            if isinstance(user_conf, dict):
                return user_conf
            else:
                logger.debug(f"{conf_format.name} parsing failed.")

        return None

    def read_and_parse_conf(self, pattern: str) -> dict | None:
        for conf_content in self.search_and_read_conf(pattern):
            user_conf = self.parse_conf(conf_content)
            if user_conf is not None:
                return user_conf
        return None

    def load_ini_config(self, content):
        """Utility method to parse INI configuration file.

        Internal convention is to use a dot (``.``, as set by ``self.SEP``) in
        section IDs as a separator between levels. This is a workaround
        the limitation of ``INI`` format which doesn't allow for sub-sections.

        Returns a ready-to-use data structure.
        """
        ini_config = ConfigParser(interpolation=ExtendedInterpolation())
        ini_config.read_string(content)

        conf = {}
        for section_id in ini_config.sections():
            # Extract all options of the section.
            sub_conf = {}
            for option_id in ini_config.options(section_id):
                target_type = self.get_tree_value(
                    self.params_types,
                    section_id,
                    option_id,
                )

                if target_type in (None, str):
                    value = ini_config.get(section_id, option_id)

                elif target_type == int:
                    value = ini_config.getint(section_id, option_id)

                elif target_type == float:
                    value = ini_config.getfloat(section_id, option_id)

                elif target_type == bool:
                    value = ini_config.getboolean(section_id, option_id)

                # Types not natively supported by INI format are loaded as
                # JSON-serialized strings.
                elif target_type in (list, tuple, set, frozenset, dict):
                    value = json.loads(ini_config.get(section_id, option_id))

                else:
                    msg = (
                        f"Conversion of {target_type} type for "
                        f"[{section_id}]:{option_id} INI config option."
                    )
                    raise ValueError(msg)

                sub_conf[option_id] = value

            # Place collected options at the right level of the dict tree.
            merge(conf, self.init_tree_dict(*section_id.split(self.SEP), leaf=sub_conf))

        return conf

    def recursive_update(self, a, b):
        """Like standard ``dict.update()``, but recursive so sub-dict gets updated.

        Ignore elements present in ``b`` but not in ``a``.
        """
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                a[k] = self.recursive_update(a[k], v)
            # Ignore elements unregistered in the template structure.
            elif k in a:
                a[k] = b[k]
            elif self.strict:
                msg = f"Parameter {k!r} is not allowed in configuration file."
                raise ValueError(
                    msg,
                )
        return a

    def merge_conf(self, user_conf):
        """Try-out configuration formats againts file's content and returns a ``dict``.

        The returned ``dict`` will only contain options and parameters defined on the
        CLI. All others will be filtered out.
        """
        # Merge configuration file's content into the template structure, but
        # ignore all unrecognized options.
        valid_conf = self.recursive_update(self.params_template, user_conf)

        # Clean-up blank values left-over by the template structure.

        def visit(path, key, value):
            """Skip None values and empty dicts."""
            if value is None:
                return False
            if isinstance(value, dict) and not len(value):
                return False
            return True

        clean_conf = remap(valid_conf, visit=visit)
        return clean_conf

    def load_conf(self, ctx, param, path_pattern):
        """Fetch parameters values from configuration file and merge them with the
        defaults.

        User configuration is
        `merged to the context default_map as Click does <https://click.palletsprojects.com/en/8.1.x/commands/#context-defaults>`_.

        This allow user's config to only overrides defaults. Values sets from direct
        command line parameters, environment variables or interactive prompts, takes
        precedence over any values from the config file.
        """
        logger = logging.getLogger("click_extra")

        explicit_conf = ctx.get_parameter_source("config") in (
            ParameterSource.COMMANDLINE,
            ParameterSource.ENVIRONMENT,
            ParameterSource.PROMPT,
        )
        # Always print a message if the user explicitly set the configuration location.
        # We can't use logger.info because the default have not been loaded yet
        # and the logger is stuck to its default WARNING level.
        message = f"Load configuration matching {path_pattern}"
        if explicit_conf:
            echo(message, err=True)
        # Fallback on default configuration file location.
        else:
            logger.debug(message)

        # Read configuration file.
        conf = {}
        user_conf = self.read_and_parse_conf(path_pattern)
        # Exit the CLI if the user-provided config file is bad.
        if user_conf is None:
            message = "No configuration file found."
            if explicit_conf:
                logger.critical(message)

                # Do not just ctx.exit() as it will prevent callbacks defined on options
                # to be called.
                ctx.close()
                ctx.exit(2)
            else:
                logger.debug(message)

        else:
            conf = self.merge_conf(user_conf)
            logger.debug(f"Loaded configuration: {conf}")

            # Merge config to the default_map.
            if ctx.default_map is None:
                ctx.default_map = {}
            ctx.default_map.update(conf.get(ctx.find_root().command.name, {}))
            logger.debug(f"New defaults: {ctx.default_map}")

        return path_pattern
