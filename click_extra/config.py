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

""" Utilities to load parameters and options from a configuration file. """

import sys
from configparser import ConfigParser, ExtendedInterpolation
from functools import reduce
from operator import getitem
from pathlib import Path

import click
import commentjson as json
import requests
import yaml
from boltons.iterutils import flatten, remap
from boltons.urlutils import URL
from click.core import ParameterSource
from cloup import GroupedOption
from mergedeep import merge

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .logging import logger
from .platform import is_windows

# List of unsupported options we're going to ignore.
IGNORED_OPTIONS = (
    # --help is not a configurable option.
    "help",
    # --version is not a configurable option.
    "version",
    # -C/--config option cannot be used to recursively load another file.
    "config",
)


# Maps configuration formats, their file extension, and parsing function,
# The order encode the priority by which each format is searched for default configuration file.
# TODO: add XML?
CONFIGURATION_FORMATS = {
    "TOML": (".toml",),
    "YAML": (".yaml", ".yml"),
    "JSON": (".json",),
    "INI": (".ini",),
}
# List of all supported configuration file extensions.
ALL_EXTENSIONS = tuple(flatten(CONFIGURATION_FORMATS.values()))


class ConfigurationFileError(Exception):
    """Base class for all exceptions related to configuration file."""

    pass


class DefaultConfPath:
    """Returns default location of the configuration file.

    Location depends on OS (see `Click documentation
    <https://click.palletsprojects.com/en/8.0.x/api/#click.get_app_dir>`_):

        * macOS & Linux: ``~/.my_cli/config.{toml,yaml,yml,json,ini}``

        * Windows: ``C:\\Users\\<user>\\AppData\\Roaming\\my_cli\\config.{toml,yaml,yml,json,ini}``
    """

    default_conf_name = "config"

    @property
    def conf_path(self):
        ctx = click.get_current_context()
        cli_name = ctx.find_root().info_name
        return Path(
            click.get_app_dir(cli_name, force_posix=True), self.default_conf_name
        ).resolve()

    def __call__(self):
        """Search for all recognized file extensions in default location."""
        logger.debug("Search for configuration in default location...")
        conf_path = self.conf_path
        for conf_ext in ALL_EXTENSIONS:
            conf_file = conf_path.with_suffix(conf_ext)
            if conf_file.exists():
                logger.debug(f"File found in default location {conf_file}.")
                return conf_file
        logger.debug("No default configuration found.")

    def __str__(self):
        """Default location represented with all supported extensions for help screens."""
        # Reduce leading path with the `~` user's home construct for tersness.
        conf_path = self.conf_path
        if not is_windows():
            try:
                conf_path = "~" / conf_path.relative_to(Path.home())
            except (RuntimeError, ValueError):
                pass
        return f"{conf_path}.{{{','.join(ext.lstrip('.') for ext in ALL_EXTENSIONS)}}}"


def init_deep_dict(path, leaf=None):
    """Utility method to recursively create a nested dict structure whose keys are provided by ``levels`` list
    and at the end is populated by ``leaf``.
    """

    def dive(levels):
        if levels:
            return {levels[0]: dive(levels[1:])}
        return leaf

    # Use dot separator in section names as a separator between levels.
    return dive(path.split("."))


def get_deep_value(deep_dict, path):
    try:
        return reduce(getitem, path.split("."), deep_dict)
    except KeyError:
        return None


def load_ini_config(content, conf_types):
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

            target_type = get_deep_value(conf_types, f"{section_id}.{option_id}")
            if target_type in (None, str):
                value = ini_config.get(section_id, option_id)

            elif target_type == int:
                value = ini_config.getint(section_id, option_id)

            elif target_type == float:
                value = ini_config.getfloat(section_id, option_id)

            elif target_type == bool:
                value = ini_config.getboolean(section_id, option_id)

            # Types not natively supported by INI format are loaded as JSON-serialized strings.
            elif target_type in (list, tuple, set, frozenset, dict):
                value = json.loads(ini_config.get(section_id, option_id))

            else:
                raise ValueError(
                    f"Conversion of {target_type} type for [{section_id}]:{option_id} INI config option."
                )

            sub_conf[option_id] = value

        # Place collected options at the right level of the dict tree.
        merge(conf, init_deep_dict(section_id, leaf=sub_conf))

    return conf


def map_option_type(param):
    """Translate Click parameter type to Python type."""

    if param.multiple:
        return list

    if param.is_bool_flag:
        return bool

    if isinstance(param.type, click.Choice):
        return str

    direct_map = {
        click.INT: int,
        click.FLOAT: float,
        click.BOOL: bool,
        click.STRING: str,
    }

    if param.type in direct_map:
        return direct_map[param.type]

    raise ValueError(
        f"Can't guess the target configuration data type of {param!r} prameter."
    )


def conf_structure(ctx):
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
        if p.name not in IGNORED_OPTIONS:
            conf_template[cli.name][p.name] = None
            conf_types[cli.name][p.name] = map_option_type(p)

    # Subcommand-specific options.
    for cmd_id, cmd in cli.commands.items():
        if cmd_id in conf_template[cli.name]:
            raise ValueError(
                f"{cli.name}.{cmd_id} subcommand conflicts with {conf_template[cli.name]} top-level parameters"
            )

        for p in cmd.params:
            if p.name not in IGNORED_OPTIONS:
                conf_template[cli.name].setdefault(cmd_id, {})[p.name] = None
                conf_types[cli.name].setdefault(cmd_id, {})[p.name] = map_option_type(p)

    return conf_template, conf_types


def parse_and_merge_conf(ctx, conf_content, conf_extension):
    """Detect configuration format, parse its content and returns a ``dict``.

    The returned ``dict`` will only contain options and parameters defined on the CLI. All others will be filtered out.
    """
    # Select configuration format based on extension and parse its content.
    user_conf = None
    for conf_format, conf_exts in CONFIGURATION_FORMATS.items():
        logger.debug(f"Evaluate configuration as {conf_format}...")
        if conf_extension in conf_exts:
            logger.debug(f"Configuration format is {conf_format}.")
            break
    else:
        raise ConfigurationFileError("Configuration format not recognized.")

    # Merge configuration file's content into the template structure, but
    # ignore all unrecognized options.

    def recursive_update(a, b):
        """Like standard ``dict.update()``, but recursive so sub-dict gets updated.

        Ignore elements present in ``b`` but not in ``a``.
        """
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                a[k] = recursive_update(a[k], v)
            # Ignore elements unregistered in the template structure.
            elif k in a:
                a[k] = b[k]
        return a

    conf_template, conf_types = conf_structure(ctx)

    if conf_format == "TOML":
        user_conf = tomllib.loads(conf_content)

    elif conf_format == "YAML":
        user_conf = yaml.full_load(conf_content)

    elif conf_format == "JSON":
        user_conf = json.loads(conf_content)

    elif conf_format == "INI":
        user_conf = load_ini_config(conf_content, conf_types)

    valid_conf = recursive_update(conf_template, user_conf)

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


def read_conf(conf_path):
    """Read conf from remote URL or local file system."""

    # Check if the path is an URL.
    location = URL(conf_path)
    if location and location.scheme.lower() in ("http", "https"):
        with requests.get(location) as response:
            if not response.ok:
                raise ConfigurationFileError(
                    f"Can't download {location}: {response.reason}"
                )
            return response.text, "." + location.path.split(".")[-1]

    # Load configuration from local file.
    conf_path = Path(conf_path).resolve()
    if not conf_path.exists():
        raise ConfigurationFileError(f"Configuration not found at {conf_path}")
    if not conf_path.is_file():
        raise ConfigurationFileError(f"Configuration {conf_path} is not a file.")
    return conf_path.read_text(), conf_path.suffix.lower()


def load_conf(ctx, param, conf_path):
    """Fetch parameters values from configuration file and merge them to the defaults.

    User configuration is merged to the context ``default_map``, as in:
    https://click.palletsprojects.com/en/8.0.x/commands/#context-defaults

    This allow user's config to only overrides defaults. Values sets from direct
    command line parameters, environment variables or interactive prompts takes precedence
    over any values from the config file.
    """
    if not conf_path:
        logger.debug(f"No configuration provided.")
        return

    explicit_conf = ctx.get_parameter_source("config") in (
        ParameterSource.COMMANDLINE,
        ParameterSource.ENVIRONMENT,
        ParameterSource.PROMPT,
    )
    # Always print a message if the user explicitly set the configuration location.
    # We can't use logger.info because the default have not been loaded yet and the logger is stuck to its default WARNING level.
    if explicit_conf:
        click.echo(f"Load configuration from {conf_path}", err=True)
    # Fallback on default configuration file location.
    else:
        logger.debug(f"Load configuration from {conf_path}")

    # Read configuration file.
    conf = {}
    try:
        conf_content, conf_extension = read_conf(conf_path)
        conf = parse_and_merge_conf(ctx, conf_content, conf_extension)
    except ConfigurationFileError as excpt:
        # Exit the CLI if the user-provided config file is bad.
        if explicit_conf:
            logger.fatal(excpt)
            ctx.exit(2)
        else:
            logger.debug(excpt)
            logger.debug("Ignore configuration file.")

    logger.debug(f"Loaded configuration: {conf}")

    # Merge config to the default_map.
    if ctx.default_map is None:
        ctx.default_map = dict()
    ctx.default_map.update(conf.get(ctx.find_root().command.name, {}))

    return conf_path


def config_option(
    *names,
    metavar="CONFIG_PATH",
    type=click.STRING,
    default=DefaultConfPath(),
    help="Location of the configuration file. Supports both local path and remote URL.",
    # Force eagerness so the config option's callback gets the oportunity to set the
    # default_map values before the other options use them.
    is_eager=True,
    callback=load_conf,
    expose_value=False,
    cls=GroupedOption,
    **kwargs,
):
    """Adds a ``--config``/``-C`` option."""
    if not names:
        names = ("--config", "-C")
    return click.option(
        *names,
        metavar=metavar,
        type=type,
        default=default,
        help=help,
        is_eager=is_eager,
        callback=callback,
        expose_value=expose_value,
        cls=cls,
        **kwargs,
    )
