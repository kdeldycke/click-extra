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
"""Our own flavor of ``Option``, ``Argument`` and ``parameters``.

Also implements environment variable utilities.
"""

from __future__ import annotations

import inspect
import logging
import re
from collections.abc import MutableMapping
from functools import cached_property, reduce
from gettext import gettext as _
from operator import getitem, methodcaller
from typing import Any, Dict, Iterable, Sequence

import click
from boltons.iterutils import unique
from mergedeep import merge
from tabulate import tabulate

from . import (
    BOOL,
    FLOAT,
    INT,
    STRING,
    UNPROCESSED,
    UUID,
    Choice,
    DateTime,
    File,
    FloatRange,
    IntRange,
    Option,
    Style,
    Tuple,
    echo,
    get_current_context,
)


def auto_envvar(
    param: click.Parameter, ctx: click.Context | Dict[str, Any]
) -> str | None:
    """Compute the auto-generated environment variable of an option or argument.

    Returns the auto envvar as it is exacly computed within Click's internals, i.e.
    ``click.core.Parameter.resolve_envvar_value()`` and
    ``click.core.Option.resolve_envvar_value()``.
    """
    # Skip parameters that have their auto-envvar explicitly disabled.
    if not getattr(param, "allow_from_autoenv", None):
        return None

    if isinstance(ctx, click.Context):
        prefix = ctx.auto_envvar_prefix
    else:
        prefix = ctx.get("auto_envvar_prefix")
    if not prefix or not param.name:
        return None

    # Mimicks Click's internals.
    return f"{prefix}_{param.name.upper()}"


def extend_envvars(
    envvars_1: str | Sequence[str] | None, envvars_2: str | Sequence[str] | None
) -> tuple[str, ...]:
    """Utility to build environment variables value to be fed to options.

    Variable names are deduplicated while preserving their initial order.

    Returns a tuple of environment variable strings. The result is ready to be used as
    the ``envvar`` parameter for options or arguments.
    """
    # Make the fist argument into a list of string.
    envvars = []
    if envvars_1:
        if isinstance(envvars_1, str):
            envvars = [envvars_1]
        else:
            envvars = list(envvars_1)

    # Merge the second argument into the list.
    if envvars_2:
        if isinstance(envvars_2, str):
            envvars.append(envvars_2)
        else:
            envvars.extend(envvars_2)

    # Deduplicate the list and cast it into an immutable tuple.
    return tuple(unique(envvars))


def normalize_envvar(envvar: str) -> str:
    """Utility to normalize an environment variable name.

    The normalization process separates all contiguous alphanumeric string segments,
    eliminate empty strings, join them with an underscore and uppercase the result.
    """
    return "_".join((p for p in re.split(r"[^a-zA-Z0-9]+", envvar) if p)).upper()


def all_envvars(
    param: click.Parameter, ctx: click.Context | Dict[str, Any], normalize: bool = False
) -> tuple[str, ...]:
    """Returns the deduplicated, ordered list of environment variables for an option or
    argument, including the auto-generated one.

    The auto-generated environment variable is added at the end of the list, so that
    user-defined envvars takes precedence. This respects the current implementation
    of ``click.core.Option.resolve_envvar_value()``.

    If ``normalize`` is `True`, the returned value is normalized. By default it is
    `False` to perfectly reproduce the
    `current behavior of Click, which is subject to discussions <https://github.com/pallets/click/issues/2483>`_.
    """
    auto_envvar_id = auto_envvar(param, ctx)
    envvars = extend_envvars(param.envvar, auto_envvar_id)

    if normalize:
        envvars = tuple(normalize_envvar(var) for var in envvars)

    return envvars


def search_params(
    params: Iterable[click.Parameter],
    klass: type[click.Parameter],
    unique: bool = True,
) -> list[click.Parameter] | click.Parameter | None:
    """Search a particular class of parameter in a list and return them.

    :param params: list of parameter instances to search in.
    :param klass: the class of the parameters to look for.
    :param unique: if ``True``, raise an error if more than one parameter of the
        provided ``klass`` is found.
    """
    param_list = [p for p in params if isinstance(p, klass)]
    if not param_list:
        return None
    if unique:
        if len(param_list) != 1:
            raise RuntimeError(
                f"More than one {klass.__name__} parameters found "
                f"on command: {param_list}"
            )
        return param_list.pop()
    return param_list


class ExtraOption(Option):
    """All new options implemented by ``click-extra`` inherits this class.

    Does nothing in particular for now but provides a way to identify Click Extra's own
    options with certainty.

    Also contains Option-specific code that should be contributed upstream to Click.
    """

    @staticmethod
    def get_help_default(option: click.Option, ctx: click.Context) -> str | None:
        """Produce the string to be displayed in the help as option's default.

        .. caution::
            This is a `copy of Click's default value rendering of the default
            <https://github.com/pallets/click/blob/b0538df/src/click/core.py#L2754-L2792>`_

            This code **should be keep in sync with Click's implementation**.

        .. attention::
            This doens't work with our own ``--config`` option because we are also
            monkey-patching `ConfigOption.get_help_record()
            <https://kdeldycke.github.io/click-extra/config.html#click_extra.config.ConfigOption.get_help_record>`_
            to display the dynamic default value.

            So the results of this method call is:

                .. code-block:: text

                    <bound method ConfigOption.default_pattern of <ConfigOption config>>

            instead of the expected:

                .. code-block:: text

                    ~/(...)/multiple_envvars.py/*.{toml,yaml,yml,json,ini,xml}

        .. todo::
            A better solution has been proposed upstream to Click:
            - https://github.com/pallets/click/issues/2516
            - https://github.com/pallets/click/pull/2517
        """
        # Temporarily enable resilient parsing to avoid type casting
        # failing for the default. Might be possible to extend this to
        # help formatting in general.
        resilient = ctx.resilient_parsing
        ctx.resilient_parsing = True

        try:
            default_value = option.get_default(ctx, call=False)
        finally:
            ctx.resilient_parsing = resilient

        show_default = False
        show_default_is_str = False

        if option.show_default is not None:
            if isinstance(option.show_default, str):
                show_default_is_str = show_default = True
            else:
                show_default = option.show_default
        elif ctx.show_default is not None:
            show_default = ctx.show_default

        if show_default_is_str or (show_default and (default_value is not None)):
            if show_default_is_str:
                default_string = f"({option.show_default})"
            elif isinstance(default_value, (list, tuple)):
                default_string = ", ".join(str(d) for d in default_value)
            elif inspect.isfunction(default_value):
                default_string = _("(dynamic)")
            elif option.is_bool_flag and option.secondary_opts:
                # For boolean flags that have distinct True/False opts,
                # use the opt without prefix instead of the value.
                default_string = click.parser.split_opt(
                    (option.opts if option.default else option.secondary_opts)[0]
                )[1]
            elif (
                option.is_bool_flag and not option.secondary_opts and not default_value
            ):
                default_string = ""
            else:
                default_string = str(default_value)

            if default_string:
                return default_string

        return None


class ParamStructure:
    """Utilities to introspect CLI options and commands structure.

    Structures are represented by a tree-like ``dict``.

    Access to a node is available using a serialized path string composed of the keys to
    descend to that node, separated by a dot ``.``.
    """

    SEP: str = "."
    """Use a dot ``.`` as a separator between levels of the tree-like parameter
    structure."""

    DEFAULT_EXCLUDE_PARAMS: Iterable[str] = (
        "config",
        "help",
        "show_params",
        "version",
    )
    """List of root parameters to exclude from configuration by default:

    - ``-C``/``--config`` option, which cannot be used to recursively load another
      configuration file.
    - ``--help``, as it makes no sense to have the configurable file always
      forces a CLI to show the help and exit.
    - ``--show-params`` flag, which is like ``--help`` and stops the CLI execution.
    - ``--version``, which is not a configurable option *per-se*.
    """

    def __init__(self, *args, exclude_params: Iterable[str] | None = None, **kwargs):
        """Force the blocklist with paramerers provided by the user.

        Else, let the cached ``self.exclude_params`` property compute it.
        """
        if exclude_params is not None:
            self.exclude_params = exclude_params

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
    def get_tree_value(tree_dict: dict[str, Any], *path: str) -> Any | None:
        """Get in the ``tree_dict`` the value located at the ``path``."""
        try:
            return reduce(getitem, path, tree_dict)
        except KeyError:
            return None

    def _flatten_tree_dict_gen(self, tree_dict, parent_key):
        """
        `Source of this snippet
        <https://www.freecodecamp.org/news/how-to-flatten-a-dictionary-in-python-in-4-different-ways/>`_.
        """
        for k, v in tree_dict.items():
            new_key = f"{parent_key}{self.SEP}{k}" if parent_key else k
            if isinstance(v, MutableMapping):
                yield from self.flatten_tree_dict(v, new_key).items()
            else:
                yield new_key, v

    def flatten_tree_dict(
        self, tree_dict: MutableMapping, parent_key: str | None = None
    ):
        """Recursively traverse the tree-like ``dict`` and produce a flat ``dict`` whose
        keys are path and values are the leaf's content."""
        return dict(self._flatten_tree_dict_gen(tree_dict, parent_key))

    def walk_params(self):
        """Generates an unfiltered list of all CLI parameters.

        Everything is included, from top-level to subcommands, from options to
        arguments.

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
                    yield (cli.name, cmd_id, p.name), p

    def get_param_type(self, param):
        """Get the Python type of a Click parameter.

        See the list of
        `custom types provided by Click <https://click.palletsprojects.com/en/8.1.x/api/?highlight=intrange#types>`_.
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
            click.Path: str,
            Choice: str,
            IntRange: int,
            FloatRange: float,
            DateTime: str,
            Tuple: list,
        }

        for click_type, py_type in instance_map.items():
            if isinstance(param.type, click_type):
                return py_type

        raise ValueError(
            f"Can't guess the appropriate Python type of {param!r} parameter."
        )

    @cached_property
    def exclude_params(self) -> Iterable[str]:
        """List of parameter IDs to exclude from the parameter structure.

        Elements of this list are expected to be the fully-qualified ID of the
        parameter, i.e. the dot-separated ID that is prefixed by the CLI name.

        It's been made into a property to allow for a last-minute call to the current
        context to fetch the CLI name.
        """
        ctx = get_current_context()
        cli = ctx.find_root().command
        return [f"{cli.name}{self.SEP}{p}" for p in self.DEFAULT_EXCLUDE_PARAMS]

    def build_param_trees(self) -> None:
        """Build all parameters tree structure in one go and cache them.

        This removes parameters whose fully-qualified IDs are in the ``exclude_params``
        blocklist.
        """
        template: dict[str, Any] = {}
        types: dict[str, Any] = {}
        objects: dict[str, Any] = {}

        for keys, param in self.walk_params():
            if self.SEP.join(keys) in self.exclude_params:
                continue
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


class ShowParamsOption(ExtraOption, ParamStructure):
    """A pre-configured option adding a ``--show-params`` option.

    Between configuration files, default values and environment variables, it might be
    hard to guess under which set of parameters the CLI will be executed. This option
    print information about the parameters that will be fed to the CLI.
    """

    TABLE_HEADERS = (
        "ID",
        "Class",
        "Spec.",
        "Type",
        "Allowed in conf?",
        "Exposed",
        "Env. vars.",
        "Default",
        "Value",
        "Source",
    )
    """Hard-coded list of table headers."""

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=True,
        expose_value=False,
        is_eager=True,
        help=_(
            "Show all CLI parameters, their provenance, defaults and value, then exit."
        ),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--show-params",)

        kwargs.setdefault("callback", self.print_params)

        # Deactivate blocking of any parameter.
        self.exclude_params = ()

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )

    def print_params(self, ctx, param, value):
        """Introspects current CLI and list its parameters and metadata.

        .. important::
            Click doesn't keep a list of all parsed arguments and their origin.
            So we need to emulate here what's happening during CLI invokation.

            Unfortunately we cannot even do that because the raw, pre-parsed arguments
            are not available anywhere within Click's internals.

            Our workaround consist in leveraging our custom
            ``ExtraCommand``/``ExtraGroup`` classes, in which we are attaching
            a ``click_extra.raw_args`` metadata entry to the context.
        """
        # imported here to avoid circular imports.
        from .colorize import KO, OK, default_theme
        from .config import ConfigOption

        # Exit early if the callback was processed but the option wasn't set.
        if not value:
            return

        logger = logging.getLogger("click_extra")

        if "click_extra.raw_args" in ctx.meta:
            raw_args = ctx.meta.get("click_extra.raw_args", [])
            logger.debug(f"click_extra.raw_args: {raw_args}")

            # Mimics click.core.Command.parse_args() so we can produce the list of
            # parsed options values.
            parser = ctx.command.make_parser(ctx)
            opts, _, _ = parser.parse_args(args=raw_args)

            # We call directly consume_value() instead of handle_parse_result() to
            # prevent an embedded call to process_value(), as the later triggers the
            # callback (and might terminate CLI execution).
            param_value, source = param.consume_value(ctx, opts)

            get_param_value = methodcaller("consume_value", ctx, opts)

        else:
            logger.debug(f"click_extra.raw_args not in {ctx.meta}")
            logger.warning(
                f"Cannot extract parameters values: "
                f"{ctx.command} does not inherits from ExtraCommand."
            )

            def vanilla_getter(param):
                param_value = None
                source = ctx.get_parameter_source(param.name)
                return param_value, source

            get_param_value = vanilla_getter

        # Inspect the CLI to search for any --config option.
        config_option = search_params(ctx.command.params, ConfigOption)

        table = []
        for path, param_type in self.flatten_tree_dict(self.params_types).items():
            # Get the parameter instance.
            tree_keys = path.split(self.SEP)
            param = self.get_tree_value(self.params_objects, *tree_keys)
            assert param.name == tree_keys[-1]

            param_value, source = get_param_value(param)
            param_class = self.get_tree_value(self.params_objects, *tree_keys).__class__
            param_spec = param.get_help_record(ctx)[0]

            # Check if the parameter is allowed in the configuration file.
            allowed_in_conf = None
            if config_option:
                if path in config_option.exclude_params:
                    allowed_in_conf = KO
                else:
                    allowed_in_conf = OK

            line = (
                default_theme.invoked_command(path),
                f"{param_class.__module__}.{param_class.__qualname__}",
                param_spec,
                param_type.__name__,
                allowed_in_conf,
                OK if param.expose_value is True else KO,
                ", ".join(map(default_theme.envvar, all_envvars(param, ctx))),
                default_theme.default(param.get_default(ctx)),
                param_value,
                source._name_ if source else None,
            )
            table.append(line)

        def sort_by_depth(line):
            """Sort parameters by depth first, then IDs, so that top-level parameters
            are kept to the top."""
            param_path = line[0]
            tree_keys = param_path.split(self.SEP)
            return len(tree_keys), param_path

        header_style = Style(bold=True)
        header_labels = map(header_style, self.TABLE_HEADERS)

        output = tabulate(
            sorted(table, key=sort_by_depth),
            headers=header_labels,
            tablefmt="rounded_outline",
            disable_numparse=True,
        )
        echo(output, color=ctx.color)

        # Do not just ctx.exit() as it will prevent callbacks defined on options
        # to be called.
        ctx.close()
        ctx.exit()