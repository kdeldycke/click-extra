# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

import sys
from configparser import ConfigParser, ExtendedInterpolation
from enum import Enum, auto
from functools import partial, reduce
from gettext import gettext as _
from operator import getitem
from os.path import sep
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Union
from unittest.mock import patch

if sys.version_info >= (3, 8):
    from functools import cached_property
else:
    from boltons.cacheutils import cachedproperty as cached_property

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import commentjson as json
import requests
import xmltodict
import yaml
from boltons.iterutils import remap
from boltons.urlutils import URL
from click import BOOL, FLOAT, INT, STRING, UNPROCESSED, UUID
from click import Path as ClickPath
from click import echo, get_app_dir, get_current_context
from click.core import ParameterSource
from cloup import Choice, DateTime, File, FloatRange, IntRange
from cloup import Tuple as CloupTuple
from cloup import option
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

from .logging import logger
from .parameters import ExtraOption
from .platform import is_windows


class Formats(Enum):
    """Supported configuration formats.

    The default order set the priority by which each format is searched for the default configuration file.
    """

    TOML = auto()
    YAML = auto()
    JSON = auto()
    INI = auto()
    XML = auto()


class ConfigOption(ExtraOption):
    """A pre-configured option adding ``--config``/``-C`` option."""

    formats: Sequence[Formats]

    roaming: bool
    force_posix: bool

    ignore_options: Iterable[str]

    strict: bool

    conf_template: Dict[str, Any] = {}
    conf_types: Dict[str, Any] = {}

    def __init__(
        self,
        param_decls=None,
        metavar="CONFIG_PATH",
        type=STRING,
        help=_(
            "Location of the configuration file. Supports glob pattern of local path and remote URL."
        ),
        is_eager=True,
        expose_value=False,
        formats=tuple(Formats),
        roaming=True,
        force_posix=False,
        ignored_options=(
            "help",
            "version",
            "config",
        ),
        strict=False,
        **kwargs,
    ):
        """

        A [``wcmatch.glob`` pattern](https://facelessuser.github.io/wcmatch/glob/#syntax).

        - ``is_eager`` is active by default so the config option's ``callback`` gets the opportunity to set the
            ``default_map`` values before the other options use them.

        - ``formats`` is the ordered list of formats that the configuration file will be tried to be read with. Can be a single one.

        - ``roaming`` and ``force_posix`` are [fed to ``click.get_app_dir()``](https://click.palletsprojects.com/en/8.1.x/api/#click.get_app_dir) to setup the default configuration
            folder.

        - ``ignored_options`` is a list of options to ignore by the configuration parser. Defaults to:
            - ``--help``, as it makes no sense to have the configurable file always forces a CLI to show the help and exit.
            - ``--version``, which is not a configurable option *per-se*.
            - ``-C``/``--config`` option, which cannot be used to recursively load another configuration file (yet?).

        - ``strict``
            - If ``True``, raise an error if the configuration file contain unrecognized content.
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

        self.ignored_options = ignored_options

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

        Defaults to ``/<app_dir>/*.{toml,yaml,json,ini,xml}``.

        ``<app_dir>`` is produced by [`clickget_app_dir()` method](https://click.palletsprojects.com/en/8.1.x/api/#click.get_app_dir).
        The result depends on OS and is influenced by the ``roaming`` and ``force_posix`` properties of this instance.

        In that folder, we're looking for any file matching the extensions derived from the ``self.formats`` property:
        - a simple ``*.ext`` pattern if only one format is set
        - an expanded ``*.{ext1,ext2,...}`` pattern if multiple formats are set
        """
        ctx = get_current_context()
        cli_name = ctx.find_root().info_name
        if not cli_name:
            raise ValueError
        app_dir = Path(
            get_app_dir(cli_name, roaming=self.roaming, force_posix=self.force_posix)
        ).resolve()
        # Build the extension matching pattern.
        ext_pattern = ",".join(f.name.lower() for f in self.formats)
        if len(self.formats) > 1:
            ext_pattern = f"{{{ext_pattern}}}"
        return f"{app_dir}{sep}*.{ext_pattern}"

    @staticmethod
    def compress_path(path: Path) -> Path:
        """Reduces a path length by prefixing it with the `~` user's home prefix if possible."""
        if not is_windows():
            try:
                path = "~" / path.relative_to(Path.home())
            except (RuntimeError, ValueError):
                pass
        return path

    def get_help_record(self, ctx):
        """Replaces the default value by the pretty version of the configuration matching pattern."""
        # Pre-compute pretty_path to bypass infinite recursive loop on get_default.
        default_path = Path(self.get_default(ctx))
        pretty_path = self.compress_path(default_path)
        with patch.object(ConfigOption, "get_default") as mock_method:
            mock_method.return_value = pretty_path
            return super().get_help_record(ctx)

    def search_and_read_conf(self, pattern: str) -> Iterable[str]:
        """Search on local file system or remote URL files matching the provided pattern.

        Returns an iterator of raw content for each file/URL matching the pattern.
        """
        # Check if the pattern is an URL.
        location = URL(pattern)
        if location and location.scheme.lower() in ("http", "https"):
            logger.debug(f"Fetch configuration from remote URL.")
            with requests.get(location) as response:
                if response.ok:
                    yield from (response.text,)
                    return
                logger.warning(f"Can't download {location}: {response.reason}")
        else:
            logger.debug(f"Pattern is not an URL.")

        logger.debug(f"Search local file system.")
        # wcmatch expect patterns to be written with unix-like syntax by default, even on Windows. See more details at:
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

    def parse_conf(self, conf_content: str) -> Optional[dict]:
        """Try to parse the provided content with each format in the order provided by the user.

        A successful parsing in any format is supposed to return a dict. Any other result, including any raised exception,
        is considered a failure and the next format is tried.
        """
        user_conf = None
        for conf_format in self.formats:
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

    def read_and_parse_conf(self, pattern: str) -> Optional[dict]:
        for conf_content in self.search_and_read_conf(pattern):
            user_conf = self.parse_conf(conf_content)
            if user_conf is not None:
                return user_conf
        return None

    @staticmethod
    def init_deep_dict(path, leaf=None):
        """Utility method to recursively create a nested dict structure whose keys are
        provided by ``levels`` list and at the end is populated by ``leaf``."""

        def dive(levels):
            if levels:
                return {levels[0]: dive(levels[1:])}
            return leaf

        # Use dot separator in section names as a separator between levels.
        return dive(path.split("."))

    @staticmethod
    def get_deep_value(deep_dict, path):
        try:
            return reduce(getitem, path.split("."), deep_dict)
        except KeyError:
            return None

    def load_ini_config(self, content):
        """Utility method to parse INI configuration file.

        Returns a ready-to-use data structure.
        """
        ini_config = ConfigParser(interpolation=ExtendedInterpolation())
        ini_config.read_string(content)

        conf = {}
        for section_id in ini_config.sections():

            # Extract all options of the section.
            sub_conf = {}
            for option_id in ini_config.options(section_id):
                target_type = self.get_deep_value(
                    self.conf_types, f"{section_id}.{option_id}"
                )

                if target_type in (None, str):
                    value = ini_config.get(section_id, option_id)

                elif target_type == int:
                    value = ini_config.getint(section_id, option_id)

                elif target_type == float:
                    value = ini_config.getfloat(section_id, option_id)

                elif target_type == bool:
                    value = ini_config.getboolean(section_id, option_id)

                # Types not natively supported by INI format are loaded as JSON-serialized
                # strings.
                elif target_type in (list, tuple, set, frozenset, dict):
                    value = json.loads(ini_config.get(section_id, option_id))

                else:
                    raise ValueError(
                        f"Conversion of {target_type} type for [{section_id}]:{option_id} INI config option."
                    )

                sub_conf[option_id] = value

            # Place collected options at the right level of the dict tree.
            merge(conf, self.init_deep_dict(section_id, leaf=sub_conf))

        return conf

    def map_option_type(self, param):
        """Translate Click parameter type to Python type.

        See the list of `custom types provided by Click
        <https://click.palletsprojects.com/en/8.1.x/api/?highlight=intrange#types>`_.
        """

        if param.multiple or param.nargs != 1:
            return list

        if hasattr(param, "is_bool_flag") and getattr(param, "is_bool_flag"):
            return bool

        direct_map = {
            STRING: str,
            INT: int,
            FLOAT: float,
            BOOL: bool,
            UUID: str,
            UNPROCESSED: str,
        }

        for click_type, py_type in direct_map.items():
            if param.type == click_type:
                return py_type

        instance_map = {
            File: str,
            ClickPath: str,
            Choice: str,
            IntRange: int,
            FloatRange: float,
            DateTime: str,
            CloupTuple: list,
        }

        for click_type, py_type in instance_map.items():
            if isinstance(param.type, click_type):
                return py_type

        raise ValueError(
            f"Can't guess the target configuration data type of {param!r} parameter."
        )

    def build_conf_structure(self, ctx):
        """Returns two data structures shadowing the CLI options and subcommands.

        2 tree-like dictionnaries are returned:

        - One with only keys, all values being set to None, to serve as a template for configuration
        - A copy of the former, with values set to their expected type
        """
        cli = ctx.find_root().command

        # The whole config is placed under the cli name's section.
        conf_template = {cli.name: {}}
        conf_types = {cli.name: {}}

        # Global, top-level options shared by all subcommands.
        for p in cli.params:
            if p.name not in self.ignored_options:
                conf_template[cli.name][p.name] = None
                conf_types[cli.name][p.name] = self.map_option_type(p)

        # Subcommand-specific options.
        if hasattr(cli, "commands"):
            for cmd_id, cmd in cli.commands.items():
                if cmd_id in conf_template[cli.name]:
                    raise ValueError(
                        f"{cli.name}.{cmd_id} subcommand conflicts with {conf_template[cli.name]} top-level parameters"
                    )

                for p in cmd.params:
                    if p.name not in self.ignored_options:
                        conf_template[cli.name].setdefault(cmd_id, {})[p.name] = None
                        conf_types[cli.name].setdefault(cmd_id, {})[
                            p.name
                        ] = self.map_option_type(p)

        self.conf_template = conf_template
        self.conf_types = conf_types

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
                raise ValueError(
                    f"Parameter {k!r} is not allowed in configuration file."
                )
        return a

    def merge_conf(self, user_conf):
        """Try-out configuration formats againts file's content and returns a ``dict``.

        The returned ``dict`` will only contain options and parameters defined on the CLI.
        All others will be filtered out.
        """
        # Merge configuration file's content into the template structure, but
        # ignore all unrecognized options.
        valid_conf = self.recursive_update(self.conf_template, user_conf)

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
        """Fetch parameters values from configuration file and merge them with the defaults.

        User configuration is merged to the context ``default_map``, as in:
        https://click.palletsprojects.com/en/8.1.x/commands/#context-defaults

        This allow user's config to only overrides defaults. Values sets from direct
        command line parameters, environment variables or interactive prompts, takes precedence
        over any values from the config file.
        """
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
        self.build_conf_structure(ctx)
        user_conf = self.read_and_parse_conf(path_pattern)
        # Exit the CLI if the user-provided config file is bad.
        if user_conf is None:
            message = "No configuration file found."
            if explicit_conf:
                logger.fatal(message)
                ctx.exit(2)
            else:
                logger.debug(f"{message} Ignore it.")

        else:
            conf = self.merge_conf(user_conf)
            logger.debug(f"Loaded configuration: {conf}")

            # Merge config to the default_map.
            if ctx.default_map is None:
                ctx.default_map = dict()
            ctx.default_map.update(conf.get(ctx.find_root().command.name, {}))
            logger.debug(f"New defaults: {ctx.default_map}")

        return path_pattern


config_option = partial(option, cls=ConfigOption)
"""Decorator for ``ConfigOption``."""
