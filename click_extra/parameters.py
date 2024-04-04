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
from collections.abc import Iterable, MutableMapping, Sequence
from contextlib import nullcontext
from functools import cached_property, reduce
from gettext import gettext as _
from operator import getitem, methodcaller
from typing import (
    Any,
    Callable,
    ContextManager,
    Iterator,
    cast,
)
from unittest.mock import patch

import click
from boltons.iterutils import unique
from mergedeep import merge
from tabulate import tabulate

from . import (
    Command,
    Option,
    Parameter,
    ParamType,
    Style,
    echo,
    get_current_context,
)


def auto_envvar(
    param: click.Parameter,
    ctx: click.Context | dict[str, Any],
) -> str | None:
    """Compute the auto-generated environment variable of an option or argument.

    Returns the auto envvar as it is exactly computed within Click's internals, i.e.
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

    # Mimics Click's internals.
    return f"{prefix}_{param.name.upper()}"


def extend_envvars(
    envvars_1: str | Sequence[str] | None,
    envvars_2: str | Sequence[str] | None,
) -> tuple[str, ...]:
    """Utility to build environment variables value to be fed to options.

    Variable names are deduplicated while preserving their initial order.

    Returns a tuple of environment variable strings. The result is ready to be used as
    the ``envvar`` parameter for options or arguments.
    """
    # Make the fist argument into a list of string.
    envvars = []
    if envvars_1:
        envvars = [envvars_1] if isinstance(envvars_1, str) else list(envvars_1)

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
    return "_".join(p for p in re.split(r"[^a-zA-Z0-9]+", envvar) if p).upper()


def all_envvars(
    param: click.Parameter,
    ctx: click.Context | dict[str, Any],
    normalize: bool = False,
) -> tuple[str, ...]:
    """Returns the deduplicated, ordered list of environment variables for an option or
    argument, including the auto-generated one.

    The auto-generated environment variable is added at the end of the list, so that
    user-defined envvars takes precedence. This respects the current implementation
    of ``click.core.Option.resolve_envvar_value()``.

    If ``normalize`` is `True`, the returned value is normalized. By default it is
    `False` to perfectly reproduce the `current behavior of Click, which is subject to
    discussions <https://github.com/pallets/click/issues/2483>`_.
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
            msg = (
                f"More than one {klass.__name__} parameters found on command: "
                f"{param_list}"
            )
            raise RuntimeError(msg)
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
            This doesn't work with our own ``--config`` option because we are also
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
                    (option.opts if option.default else option.secondary_opts)[0],
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

    .. todo::
        Evaluates the possibility of replacing all key-based access to the tree-like
        structure by a `Box <https://github.com/cdgriffith/Box>`_ object, as it
        provides lots of utilities to merge its content.
    """

    SEP: str = "."
    """Use a dot ``.`` as a separator between levels of the tree-like parameter
    structure."""

    DEFAULT_EXCLUDED_PARAMS: Iterable[str] = (
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

    def __init__(
        self,
        *args,
        excluded_params: Iterable[str] | None = None,
        **kwargs,
    ) -> None:
        """Allow a list of paramerers to be blocked from the parameter structure.

        If ``excluded_params`` is not provided, let the dynamic and cached
        ``self.excluded_params`` property to compute the default value on first use.
        """
        if excluded_params is not None:
            self.excluded_params = excluded_params

        super().__init__(*args, **kwargs)

    @staticmethod
    def init_tree_dict(*path: str, leaf: Any = None) -> Any:
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

    def _flatten_tree_dict_gen(
        self, tree_dict: MutableMapping, parent_key: str | None = None
    ) -> Iterable[tuple[str, Any]]:
        """`Source of this snippet
        <https://www.freecodecamp.org/news/how-to-flatten-a-dictionary-in-python-in-4-different-ways/>`_.
        """
        for k, v in tree_dict.items():
            new_key = f"{parent_key}{self.SEP}{k}" if parent_key else k
            if isinstance(v, MutableMapping):
                yield from self.flatten_tree_dict(v, new_key).items()
            else:
                yield new_key, v

    def flatten_tree_dict(
        self,
        tree_dict: MutableMapping,
        parent_key: str | None = None,
    ) -> dict[str, Any]:
        """Recursively traverse the tree-like ``dict`` and produce a flat ``dict`` whose
        keys are path and values are the leaf's content."""
        return dict(self._flatten_tree_dict_gen(tree_dict, parent_key))

    def _recurse_cmd(
        self,
        cmd: Command,
        top_level_params: Iterable[str],
        parent_keys: tuple[str, ...],
    ) -> Iterator[tuple[tuple[str, ...], Parameter]]:
        """Recursive generator to walk through all subcommands and their parameters."""
        if hasattr(cmd, "commands"):
            for subcmd_id, subcmd in cmd.commands.items():
                if subcmd_id in top_level_params:
                    msg = (
                        f"{cmd.name}{self.SEP}{subcmd_id} subcommand conflicts with "
                        f"{top_level_params} top-level parameters"
                    )
                    raise ValueError(msg)

                for p in subcmd.params:
                    yield ((*parent_keys, subcmd_id, p.name)), p

                yield from self._recurse_cmd(
                    subcmd,
                    top_level_params,
                    ((*parent_keys, subcmd.name)),
                )

    def walk_params(self) -> Iterator[tuple[tuple[str, ...], Parameter]]:
        """Generates an unfiltered list of all CLI parameters.

        Everything is included, from top-level groups to subcommands, and from options
        to arguments.

        Returns a 2-elements tuple:
            - the first being a tuple of keys leading to the parameter
            - the second being the parameter object itself
        """
        ctx = get_current_context()
        cli = ctx.find_root().command
        assert cli.name is not None

        # Keep track of top-level CLI parameter IDs to check conflict with command
        # IDs later.
        top_level_params = set()

        # Global, top-level options shared by all subcommands.
        for p in cli.params:
            assert p.name is not None
            top_level_params.add(p.name)
            yield (cli.name, p.name), p

        # Subcommand-specific options.
        yield from self._recurse_cmd(cli, top_level_params, (cli.name,))

    TYPE_MAP: dict[type[ParamType], type[str | int | float | bool | list]] = {
        click.types.StringParamType: str,
        click.types.IntParamType: int,
        click.types.FloatParamType: float,
        click.types.BoolParamType: bool,
        click.types.UUIDParameterType: str,
        click.types.UnprocessedParamType: str,
        click.types.File: str,
        click.types.Path: str,
        click.types.Choice: str,
        click.types.IntRange: int,
        click.types.FloatRange: float,
        click.types.DateTime: str,
        click.types.Tuple: list,
    }
    """Map Click types to their Python equivalent.

    Keys are subclasses of ``click.types.ParamType``. Values are expected to be simple
    builtins Python types.

    This mapping can be seen as a reverse of the ``click.types.convert_type()`` method.
    """

    def get_param_type(self, param: Parameter) -> type[str | int | float | bool | list]:
        """Get the Python type of a Click parameter.

        See the list of
        `custom types provided by Click <https://click.palletsprojects.com/en/8.1.x/api/#types>`_.
        """
        if param.multiple or param.nargs != 1:
            return list

        if hasattr(param, "is_bool_flag") and param.is_bool_flag:
            return bool

        # Try to directly map the Click type to a Python type.
        py_type = self.TYPE_MAP.get(param.type.__class__)
        if py_type is not None:
            return py_type

        # Try to indirectly map the type by looking at inheritance.
        for click_type, py_type in self.TYPE_MAP.items():
            matching = set()
            if isinstance(param.type, click_type):
                matching.add(py_type)
            if matching:
                if len(matching) > 1:
                    msg = (
                        f"Multiple Python types found for {param.type!r} parameter: "
                        f"{matching}"
                    )
                    raise ValueError(msg)
                return matching.pop()

        # Custom parameters are expected to convert from strings, as that's the default
        # type of command lines.
        # See: https://click.palletsprojects.com/en/8.1.x/api/#click.ParamType
        if isinstance(param.type, ParamType):
            return str

        msg = f"Can't guess the appropriate Python type of {param!r} parameter."  # type:ignore[unreachable]
        raise ValueError(msg)

    @cached_property
    def excluded_params(self) -> Iterable[str]:
        """List of parameter IDs to exclude from the parameter structure.

        Elements of this list are expected to be the fully-qualified ID of the
        parameter, i.e. the dot-separated ID that is prefixed by the CLI name.

        .. caution::
            It is only called once to produce the list of default parameters to
            exclude, if the user did not provided its own list to the constructor.

            It was not implemented in the constructor but made as a property, to allow
            for a just-in-time call to the current context. Without this trick we could
            not have fetched the CLI name.
        """
        ctx = get_current_context()
        cli = ctx.find_root().command
        return [f"{cli.name}{self.SEP}{p}" for p in self.DEFAULT_EXCLUDED_PARAMS]

    def build_param_trees(self) -> None:
        """Build all parameters tree structure in one go and cache them.

        This removes parameters whose fully-qualified IDs are in the ``excluded_params``
        blocklist.
        """
        template: dict[str, Any] = {}
        types: dict[str, Any] = {}
        objects: dict[str, Any] = {}

        for keys, param in self.walk_params():
            if self.SEP.join(keys) in self.excluded_params:
                continue
            merge(template, self.init_tree_dict(*keys))
            merge(types, self.init_tree_dict(*keys, leaf=self.get_param_type(param)))
            merge(objects, self.init_tree_dict(*keys, leaf=param))

        self.params_template = template
        self.params_types = types
        self.params_objects = objects

    @cached_property
    def params_template(self) -> dict[str, Any]:
        """Returns a tree-like dictionary whose keys shadows the CLI options and
        subcommands and values are ``None``.

        Perfect to serve as a template for configuration files.
        """
        self.build_param_trees()
        return self.params_template

    @cached_property
    def params_types(self) -> dict[str, Any]:
        """Returns a tree-like dictionary whose keys shadows the CLI options and
        subcommands and values are their expected Python type.

        Perfect to parse configuration files and user-provided parameters.
        """
        self.build_param_trees()
        return self.params_types

    @cached_property
    def params_objects(self) -> dict[str, Any]:
        """Returns a tree-like dictionary whose keys shadows the CLI options and
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
        "Param type",
        "Python type",
        "Hidden",
        "Exposed",
        "Allowed in conf?",
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
            "Show all CLI parameters, their provenance, defaults and value, then exit.",
        ),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--show-params",)

        kwargs.setdefault("callback", self.print_params)

        self.excluded_params = ()
        """Deactivates the blocking of any parameter."""

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )

    def print_params(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Introspects current CLI and list its parameters and metadata.

        .. important::
            Click doesn't keep a list of all parsed arguments and their origin.
            So we need to emulate here what's happening during CLI invocation.

            Unfortunately we cannot even do that because the raw, pre-parsed arguments
            are not available anywhere within Click's internals.

            Our workaround consist in leveraging our custom
            ``ExtraCommand``/``ExtraGroup`` classes, in which we are attaching
            a ``click_extra.raw_args`` metadata entry to the context.
        """
        # Imported here to avoid circular imports.
        from .colorize import KO, OK, default_theme
        from .config import ConfigOption

        # Exit early if the callback was processed but the option wasn't set.
        if not value:
            return

        logger = logging.getLogger("click_extra")

        get_param_value: Callable[[Any], Any]

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
                f"{ctx.command} does not inherits from ExtraCommand.",
            )

            def vanilla_getter(p):
                param_value = None
                source = ctx.get_parameter_source(p.name)
                return param_value, source

            get_param_value = vanilla_getter

        # Inspect the CLI to search for any --config option.
        config_option = cast(
            "ConfigOption",
            search_params(ctx.command.params, ConfigOption),
        )

        table: list[
            tuple[
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
            ]
        ] = []
        for path, python_type in self.flatten_tree_dict(self.params_types).items():
            # Get the parameter instance.
            tree_keys = path.split(self.SEP)
            instance = cast(
                "click.Parameter",
                self.get_tree_value(self.params_objects, *tree_keys),
            )
            assert instance.name == tree_keys[-1]

            param_value, source = get_param_value(instance)
            param_class = instance.__class__

            # Collect param's spec and hidden status.
            hidden = None
            param_spec = None
            # Hidden property is only supported by Option, not Argument.
            # TODO: Allow arguments to produce their spec.
            if hasattr(instance, "hidden"):
                hidden = OK if instance.hidden is True else KO

                # No-op context manager without any effects.
                hidden_param_bypass: ContextManager = nullcontext()
                # If the parameter is hidden, we need to temporarily disable this flag
                # to let Click produce a help record.
                # See: https://github.com/kdeldycke/click-extra/issues/689
                # TODO: Submit a PR to Click to separate production of param spec and
                # help record. That way we can always produce the param spec even if
                # the parameter is hidden.
                if instance.hidden:
                    hidden_param_bypass = patch.object(instance, "hidden", False)
                with hidden_param_bypass:
                    help_record = instance.get_help_record(ctx)
                    if help_record:
                        param_spec = help_record[0]

            # Check if the parameter is allowed in the configuration file.
            allowed_in_conf = None
            if config_option:
                allowed_in_conf = KO if path in config_option.excluded_params else OK

            line = (
                default_theme.invoked_command(path),
                f"{param_class.__module__}.{param_class.__qualname__}",
                param_spec,
                f"{instance.type.__module__}.{instance.type.__class__.__name__}",
                python_type.__name__,
                hidden,
                OK if instance.expose_value is True else KO,
                allowed_in_conf,
                ", ".join(map(default_theme.envvar, all_envvars(instance, ctx))),
                default_theme.default(str(instance.get_default(ctx))),
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
        header_labels = tuple(map(header_style, self.TABLE_HEADERS))

        output = tabulate(
            sorted(table, key=sort_by_depth),
            headers=header_labels,
            tablefmt="rounded_outline",
            disable_numparse=True,
        )
        echo(output, color=ctx.color)

        ctx.exit()
