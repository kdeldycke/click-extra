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
from collections.abc import MutableMapping
from configparser import ConfigParser, ExtendedInterpolation
from enum import Enum
from functools import partial, reduce
from gettext import gettext as _
from operator import getitem, methodcaller
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
from boltons.iterutils import flatten, remap
from boltons.urlutils import URL
from click import BOOL, FLOAT, INT, STRING, UNPROCESSED, UUID, Option, Parameter
from click import Path as ClickPath
from click import echo, get_app_dir, get_current_context
from click.core import ParameterSource
from cloup import Choice, DateTime, File, FloatRange, IntRange
from cloup import Tuple as CloupTuple
from cloup import option
from mergedeep import merge
from tabulate import tabulate
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
    """Supported configuration formats and the list of their default extensions.

    The default order set the priority by which each format is searched for the default
    configuration file.
    """

    TOML = ("toml",)
    YAML = ("yaml", "yml")
    JSON = ("json",)
    INI = ("ini",)
    XML = ("xml",)


class ParamStructure:
    """Utilities to introspect CLI options and commands structure.

    Structures are represented by a tree-like ``dict``.

    Access to a node is available using a serialized path string composed of the keys to descend to that node,
    separated by a dot ``.``.
    """

    ignored_params: Iterable[str] = tuple()

    SEP: str = "."
    """Use a dot ``.`` as a separator between levels of the tree-like parameter structure."""

    def __init__(self, *args, ignored_params: Optional[Iterable[str]] = None, **kwargs):
        if ignored_params:
            self.ignored_params = ignored_params

        super().__init__(*args, **kwargs)

    @staticmethod
    def init_tree_dict(*path: str, leaf: Any = None):
        """Utility method to recursively create a nested dict structure whose keys are
        provided by ``path`` list and at the end is populated by a copy of ``leaf``."""

        def dive(levels):
            if levels:
                return {levels[0]: dive(levels[1:])}
            return leaf

        return dive(path)

    @staticmethod
    def get_tree_value(tree_dict: Dict[str, Any], *path: str) -> Optional[Any]:
        """Get in the ``tree_dict`` the value located at the ``path``."""
        try:
            return reduce(getitem, path, tree_dict)
        except KeyError:
            return None

    def _flatten_tree_dict_gen(self, tree_dict, parent_key):
        """
        Source: https://www.freecodecamp.org/news/how-to-flatten-a-dictionary-in-python-in-4-different-ways/
        """
        for k, v in tree_dict.items():
            new_key = f"{parent_key}{self.SEP}{k}" if parent_key else k
            if isinstance(v, MutableMapping):
                yield from self.flatten_tree_dict(v, new_key).items()
            else:
                yield new_key, v

    def flatten_tree_dict(
        self, tree_dict: MutableMapping, parent_key: Optional[str] = None
    ):
        """Recursively traverse the tree-like ``dict`` and produce a flat ``dict`` whose
        keys are path and values are the leaf's content."""
        return dict(self._flatten_tree_dict_gen(tree_dict, parent_key))

    def walk_params(self):
        """Generator yielding all CLI parameters from top-level to subcommands.

        Returns a 2-elements tuple:
        - the first being a tuple of keys leading to the parameter
        - the second being the parameter object itself
        """
        ctx = get_current_context()
        cli = ctx.find_root().command

        # Keep track of top-level CLI parameter IDs to check conflict with command
        # IDs later.
        top_level_params = set()

        # Global, top-level options shared by all subcommands.
        for p in cli.params:
            if p.name not in self.ignored_params:
                top_level_params.add(p.name)
                yield (cli.name, p.name), p

        # Subcommand-specific options.
        if hasattr(cli, "commands"):
            for cmd_id, cmd in cli.commands.items():
                if cmd_id in top_level_params:
                    raise ValueError(
                        f"{cli.name}{self.SEP}{cmd_id} subcommand conflicts with "
                        f"{top_level_params} top-level parameters"
                    )

                for p in cmd.params:
                    if p.name not in self.ignored_params:
                        yield (cli.name, cmd_id, p.name), p

    def get_param_type(self, param):
        """Get the Python type of a Click parameter.

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
            f"Can't guess the appropriate Python type of {param!r} parameter."
        )

    def build_param_trees(self) -> None:
        """Build all parameters tree structure in one go and cache them."""
        template: Dict[str, Any] = {}
        types: Dict[str, Any] = {}
        objects: Dict[str, Any] = {}

        for keys, param in self.walk_params():
            merge(template, self.init_tree_dict(*keys))
            merge(types, self.init_tree_dict(*keys, leaf=self.get_param_type(param)))
            merge(objects, self.init_tree_dict(*keys, leaf=param))

        self.params_template = template
        self.params_types = types
        self.params_objects = objects

    @cached_property
    def params_template(self):
        """Returns a tree-like dictionnary whose keys shadows the CLI options and
        subcommands and values are ``None``.

        Perfect to serve as a template for configuration files.
        """
        self.build_param_trees()
        return self.params_template

    @cached_property
    def params_types(self):
        """Returns a tree-like dictionnary whose keys shadows the CLI options and
        subcommands and values are their expected Python type.

        Perfect to parse configuration files and user-provided parameters.
        """
        self.build_param_trees()
        return self.params_types

    @cached_property
    def params_objects(self):
        """Returns a tree-like dictionnary whose keys shadows the CLI options and
        subcommands and values are parameter objects.

        Perfect to parse configuration files and user-provided parameters.
        """
        self.build_param_trees()
        return self.params_objects


class ConfigOption(ExtraOption, ParamStructure):
    """A pre-configured option adding ``--config``/``-C`` option."""

    formats: Sequence[Formats]

    roaming: bool
    force_posix: bool

    strict: bool

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
        ignored_params=(
            "help",
            "version",
            "config",
            "show_params",
        ),
        strict=False,
        **kwargs,
    ):
        """A [``wcmatch.glob``
        pattern](https://facelessuser.github.io/wcmatch/glob/#syntax).

        - ``is_eager`` is active by default so the config option's ``callback`` gets the opportunity to set the
            ``default_map`` values before the other options use them.

        - ``formats`` is the ordered list of formats that the configuration file will be tried to be read with. Can be a single one.

        - ``roaming`` and ``force_posix`` are [fed to ``click.get_app_dir()``](https://click.palletsprojects.com/en/8.1.x/api/#click.get_app_dir) to setup the default configuration
            folder.

        - ``ignored_params`` is a list of options to ignore by the configuration parser. Defaults to:
            - ``--help``, as it makes no sense to have the configurable file always forces a CLI to show the help and exit.
            - ``--version``, which is not a configurable option *per-se*.
            - ``-C``/``--config`` option, which cannot be used to recursively load another configuration file (yet?).
            - ``--show-params`` flag, which is like ``--help`` and stops the CLI execution.

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

        self.ignored_params = ignored_params

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

        Defaults to ``/<app_dir>/*.{toml,yaml,yml,json,ini,xml}``.

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
        extensions = flatten(f.value for f in self.formats)
        if len(extensions) == 1:
            ext_pattern = extensions[0]
        else:
            # Use brace notation for multiple extension matching.
            ext_pattern = f"{{{','.join(extensions)}}}"
        return f"{app_dir}{sep}*.{ext_pattern}"

    @staticmethod
    def compress_path(path: Path) -> Path:
        """Reduces a path length by prefixing it with the `~` user's home prefix if
        possible."""
        if not is_windows():
            try:
                path = "~" / path.relative_to(Path.home())
            except (RuntimeError, ValueError):
                pass
        return path

    def get_help_record(self, ctx):
        """Replaces the default value by the pretty version of the configuration
        matching pattern."""
        # Pre-compute pretty_path to bypass infinite recursive loop on get_default.
        default_path = Path(self.get_default(ctx))
        pretty_path = self.compress_path(default_path)
        with patch.object(ConfigOption, "get_default") as mock_method:
            mock_method.return_value = pretty_path
            return super().get_help_record(ctx)

    def search_and_read_conf(self, pattern: str) -> Iterable[str]:
        """Search on local file system or remote URL files matching the provided
        pattern.

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
        """Try to parse the provided content with each format in the order provided by
        the user.

        A successful parsing in any format is supposed to return a dict. Any other
        result, including any raised exception, is considered a failure and the next
        format is tried.
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

    def load_ini_config(self, content):
        """Utility method to parse INI configuration file.

        Internal convention is to use a dot (``.``, as set by ``self.SEP``) in section IDs as a separator between levels. This is a workaround
        the limitation of INI format which doesn't allow for sub-sections.

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
                    self.params_types, section_id, option_id
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
                raise ValueError(
                    f"Parameter {k!r} is not allowed in configuration file."
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


class ShowParamsOption(ExtraOption, ParamStructure):
    """A pre-configured option adding a ``--show-params`` option.

    Between configuration files, default values and environment variables, it might be
    hard to guess under which set of parameters the CLI will be executed. This option
    print information about the parameters that will be fed to the CLI.
    """

    TABLE_HEADERS = [
        "Parameter",
        "ID",
        "Type",
        "Env. var.",
        "Default",
        "Value",
        "Source",
    ]

    def __init__(
        self,
        param_decls=None,
        is_flag=True,
        expose_value=False,
        is_eager=True,
        help=_(
            "Show all CLI parameters, their provenance, defaults, value, then exit."
        ),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--show-params",)

        kwargs.setdefault("callback", self.print_params)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )

    @staticmethod
    def get_envvar(ctx, param: Union[Parameter, Option]):
        """Emulates the retrieval or dynamic generation of a parameter's environment
        variable.

        This code is a copy of what happens in ``click.core.Parameter.resolve_envvar_value()`` and
        ``click.core.Option.resolve_envvar_value()`` as the logic is deeply embedded in Click's internals
        and can't be independently used.

        ..todo:: Contribute this to Click as slight refactor to DRY?
        """
        if param.envvar:
            return param.envvar
        else:
            if (
                getattr(param, "allow_from_autoenv")
                and ctx.auto_envvar_prefix is not None
                and param.name is not None
            ):
                return f"{ctx.auto_envvar_prefix}_{param.name.upper()}"
        return None

    def print_params(self, ctx, param, value):
        """Introspects current CLI ans list its parameters and metadata."""
        # Exit early if the callback was processed but the option wasn't set.
        if not value:
            return

        # Click doen't keep a list of all parsed arguments and their origin. We need to emulate what's happening
        # during CLI invokation. The problem is even the raw arguments are now available somewhere. Our workaround
        # consist in leveraging our ExtraCommand/ExtraGroup for this.
        if "click_extra.raw_args" in ctx.meta:
            raw_args = ctx.meta.get("click_extra.raw_args", [])
            logger.debug(f"click_extra.raw_args: {raw_args}")

            # Mimics click.core.Command.parse_args() so we can produce the list of
            # parsed options values.
            parser = ctx.command.make_parser(ctx)
            opts, _, _ = parser.parse_args(args=raw_args)

            # We call directly consume_value() instead of handle_parse_result() to prevent an
            # embedded call to process_value(), as the later triggers the callback
            # (and might terminate CLI execution).
            param_value, source = param.consume_value(ctx, opts)

            get_param_value = methodcaller("consume_value", ctx, opts)

        else:
            logger.debug(f"click_extra.raw_args not in {ctx.meta}")
            logger.warning(
                f"Cannot extract parameters values: {ctx.command} does not inherits from ExtraCommand."
            )

            def vanilla_getter(param):
                param_value = None
                source = ctx.get_parameter_source(param.name)
                return param_value, source

            get_param_value = vanilla_getter

        table = []
        for path, param_type in self.flatten_tree_dict(self.params_types).items():
            # Get the parameter instance.
            tree_keys = path.split(self.SEP)
            param = self.get_tree_value(self.params_objects, *tree_keys)
            assert param.name == tree_keys[-1]

            param_value, source = get_param_value(param)

            line = (
                self.get_tree_value(self.params_objects, *tree_keys),
                path,
                param_type.__name__,
                self.get_envvar(ctx, param),
                param.get_default(ctx),
                param_value,
                source._name_ if source else None,
            )
            table.append(line)

        def sort_by_depth(line):
            """Sort parameters by depth first, then IDs, so that top-level parameters
            are kept to the top."""
            param_path = line[1]
            tree_keys = param_path.split(self.SEP)
            return len(tree_keys), param_path

        output = tabulate(
            sorted(table, key=sort_by_depth),
            headers=self.TABLE_HEADERS,
            tablefmt="rounded_outline",
            disable_numparse=True,
        )
        echo(output, color=ctx.color)
        ctx.exit()


show_params_option = partial(option, cls=ShowParamsOption)
"""Decorator for ``ShowParamsOption``."""


config_option = partial(option, cls=ConfigOption)
"""Decorator for ``ConfigOption``."""
