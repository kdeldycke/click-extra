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
"""Our own flavor of ``Option``, ``Argument`` and ``parameters``."""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from contextlib import nullcontext
from functools import cached_property, reduce
from gettext import gettext as _
from operator import getitem, methodcaller
from unittest.mock import patch

import click
import cloup
from deepmerge import always_merger

from . import UNSET, EnumChoice, ParamType, Style, get_current_context
from . import ctx_meta
from .envvar import param_envvar_ids

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from typing import Any, ClassVar


def search_params(
    params: Iterable[click.Parameter],
    klass: type[click.Parameter],
    include_subclasses: bool = True,
    unique: bool = True,
) -> list[click.Parameter] | click.Parameter | None:
    """Search a particular class of parameter in a list and return them.

    :param params: list of parameter instances to search in.
    :param klass: the class of the parameters to look for.
    :param include_subclasses: if ``True``, includes in the results all parameters subclassing
        the provided ``klass``. If ``False``, only matches parameters which are strictly instances of ``klass``.
        Defaults to ``True``.
    :param unique: if ``True``, raise an error if more than one parameter of the
        provided ``klass`` is found. Defaults to ``True``.
    """
    param_list = [
        p
        for p in params
        if (include_subclasses and isinstance(p, klass))
        or (not include_subclasses and p.__class__ is klass)
    ]
    if not param_list:
        return None
    if unique:
        if len(param_list) != 1:
            raise RuntimeError(
                f"More than one {klass.__name__} parameters found on command: "
                f"{param_list}"
            )
        return param_list.pop()
    return param_list


class _ParameterMixin:
    """Mixin providing shared functionality for Click Extra parameters.

    .. warning::
        If we want to override any method from Click's ``Parameter`` class, we have to
        use that mixin and have it inherited first in the ``Option`` and ``Argument``
        classes below.

        Because:
        - Cloup does not provide its own ``Parameter`` class.
        - Multiple inheritance cannot be used because of MRO issues.
    """

    def get_default(self, ctx: click.Context, call: bool = True):
        """Override ``click.Parameter.get_default()`` to support ``EnumChoice`` types.

        Reuse the ``EnumChoice.get_choice_string()`` method to convert an ``Enum``
        default value to its string representation, to bypass `Click's default behavior
        of returning the Enum.name <https://github.com/pallets/click/pull/3004>`_.
        """
        default_value = super().get_default(ctx, call)  # type: ignore[misc]

        if (
            hasattr(self, "type")
            and isinstance(self.type, EnumChoice)
            # Turns out UNSET is also an Enum member, so we need to ignore it.
            and default_value is not UNSET
        ):
            default_value = self.type.get_choice_string(default_value)

        return default_value


class Argument(_ParameterMixin, cloup.Argument):
    """Wrap ``cloup.Argument``, itself inheriting from ``click.Argument``.

    Inherits first from ``_ParameterMixin`` to allow future overrides of Click's
    ``Parameter`` methods.
    """


class Option(_ParameterMixin, cloup.Option):
    """Wrap ``cloup.Option``, itself inheriting from ``click.Option``.

    Inherits first from ``_ParameterMixin`` to allow future overrides of Click's
    ``Parameter`` methods.
    """


class _LazyMetaDict(dict):
    """Dict subclass that lazily resolves fields on first access.

    Installed as ``ctx._meta`` so that ``ctx.meta["click_extra.<field>"]``
    transparently evaluates the corresponding ``@cached_property`` on the
    source object only when the key is actually read.
    """

    def __init__(
        self,
        base: dict[str, Any],
        source: object,
        fields: tuple[str, ...],
    ) -> None:
        super().__init__(base)
        self._source = source
        self._lazy_keys = {f"click_extra.{f}": f for f in fields}

    def _resolve(self, key: str) -> Any:
        """Resolve a lazy key, cache the result, and return it."""
        value = getattr(self._source, self._lazy_keys[key])
        # Store as a regular entry so subsequent reads are plain dict lookups.
        dict.__setitem__(self, key, value)
        return value

    def __getitem__(self, key: str) -> Any:
        if key in self._lazy_keys and not dict.__contains__(self, key):
            return self._resolve(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        return key in self._lazy_keys or super().__contains__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._lazy_keys:
            if dict.__contains__(self, key):
                return super().__getitem__(key)
            return self._resolve(key)
        return super().get(key, default)


class ExtraOption(Option):
    """Dedicated to option implemented by ``click-extra`` itself.

    Does nothing in particular for now but provides a way to identify Click Extra's own
    options with certainty.

    .. note::
        Bracket fields (envvar, default, range, required) cannot be pre-styled in
        ``get_help_record()`` because Click's text wrapper splits lines *after* the
        record is returned, which would break ANSI codes that span wrapped boundaries.
        Styling is instead applied post-wrapping in
        ``HelpExtraFormatter._style_bracket_fields()``, which uses the structured data
        from ``Option.get_help_extra()`` to identify each field by its label.
    """


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

    def __init__(
        self,
        *args,
        excluded_params: Iterable[str] | None = None,
        included_params: Iterable[str] | None = None,
        **kwargs,
    ) -> None:
        """Allow a list of paramerers to be blocked from the parameter structure.

        Items of ``excluded_params`` are expected to be the fully-qualified ID of the
        parameter. Which is the dot-separated ID that is prefixed by the CLI name,
        featured in the first column of the table.

        ``included_params`` is the inverse: only the listed parameters will be allowed.
        Cannot be used together with ``excluded_params``.
        """
        if excluded_params and included_params:
            msg = "excluded_params and included_params are mutually exclusive."
            raise ValueError(msg)

        self.excluded_params: frozenset[str] = (
            frozenset(excluded_params) if excluded_params else frozenset()
        )

        self.included_params: frozenset[str] | None = (
            frozenset(included_params) if included_params is not None else None
        )

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
    def get_tree_value(tree_dict: dict[str, Any], *path: str) -> Any:
        """Get in the ``tree_dict`` the value located at the ``path``.

        Raises ``KeyError`` if no item is found at the provided ``path``.
        """
        return reduce(getitem, path, tree_dict)

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
        cmd: click.Command,
        top_level_params: Iterable[str],
        parent_keys: tuple[str, ...],
    ) -> Iterator[tuple[tuple[str, ...], click.Parameter]]:
        """Recursive generator to walk through all subcommands and their parameters."""
        if hasattr(cmd, "commands"):
            ctx = get_current_context()

            for subcmd_id, subcmd in cmd.commands.items():
                if subcmd_id in top_level_params:
                    # Subcommand name shadows a top-level parameter (e.g. the
                    # auto-injected ``help`` subcommand vs Click's ``--help``
                    # option).  Skip it: the config tree cannot represent both.
                    logging.getLogger("click_extra").debug(
                        f"{cmd.name}{self.SEP}{subcmd_id} subcommand shadows a "
                        f"top-level parameter; excluded from parameter tree."
                    )
                    continue

                _top_level_params = set()

                for p in subcmd.get_params(ctx):
                    _top_level_params.add(p.name)
                    yield ((*parent_keys, subcmd_id, p.name)), p

                yield from self._recurse_cmd(
                    subcmd,
                    _top_level_params,
                    ((*parent_keys, subcmd.name)),
                )

    def walk_params(self) -> Iterator[tuple[tuple[str, ...], click.Parameter]]:
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
        for p in cli.get_params(ctx):
            assert p.name is not None
            top_level_params.add(p.name)
            yield (cli.name, p.name), p

        # Subcommand-specific options.
        yield from self._recurse_cmd(cli, top_level_params, (cli.name,))

    TYPE_MAP: ClassVar[dict[type[ParamType], type[str | int | float | bool | list]]] = {
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

    @staticmethod
    def get_param_type(
        param: click.Parameter,
    ) -> type[str | int | float | bool | list]:
        """Get the Python type of a Click parameter.

        Returns ``str`` for unrecognised custom types, since command-line
        parameters are strings by default.

        See the list of
        `custom types provided by Click <https://click.palletsprojects.com/en/stable/api/#types>`_.
        """
        if param.multiple or param.nargs != 1:
            return list

        if hasattr(param, "is_bool_flag") and param.is_bool_flag:
            return bool

        # Try to directly map the Click type to a Python type.
        py_type = ParamStructure.TYPE_MAP.get(param.type.__class__)
        if py_type is not None:
            return py_type

        # Try to indirectly map the type by looking at inheritance.
        for click_type, py_type in ParamStructure.TYPE_MAP.items():
            if isinstance(param.type, click_type):
                return py_type

        # Custom parameters are expected to convert from strings, as that's
        # the default type of command lines.
        # See: https://click.palletsprojects.com/en/stable/api/#click.ParamType
        return str

    def build_param_trees(self) -> None:
        """Build the parameters tree structure and cache it.

        This removes parameters whose fully-qualified IDs are in the ``excluded_params``
        blocklist.

        If ``included_params`` was provided, it is resolved into ``excluded_params``
        here, where all parameter IDs are available.
        """
        # Resolve included_params into excluded_params before filtering.
        if self.included_params is not None:
            all_param_ids = frozenset(
                self.SEP.join(keys) for keys, _ in self.walk_params()
            )
            self.excluded_params = all_param_ids - self.included_params

        objects: dict[str, Any] = {}

        for keys, param in self.walk_params():
            if self.SEP.join(keys) in self.excluded_params:
                continue

            objects = always_merger.merge(
                objects, self.init_tree_dict(*keys, leaf=[param])
            )

        self.params_objects = objects

    @staticmethod
    def _nullify_leaves(tree: dict[str, Any]) -> dict[str, Any]:
        """Derive a template shape from a tree by replacing all leaves with ``None``."""
        return {
            k: ParamStructure._nullify_leaves(v) if isinstance(v, dict) else None
            for k, v in tree.items()
        }

    @cached_property
    def params_template(self) -> dict[str, Any]:
        """Returns a tree-like dictionary whose keys shadows the CLI options and
        subcommands and values are ``None``.

        Perfect to serve as a template for configuration files.
        """
        return self._nullify_leaves(self.params_objects)

    @cached_property
    def params_objects(self) -> dict[str, Any]:
        """Returns a tree-like dictionary whose keys shadows the CLI options and
        subcommands and values are parameter objects.

        Perfect to parse configuration files and user-provided parameters.
        """
        self.build_param_trees()
        return self.params_objects


def get_param_spec(param: click.Parameter, ctx: click.Context) -> str | None:
    """Extract the option-spec string (like ``-v, --verbose``) from a parameter.

    Temporarily unhides hidden options so their help record can be produced.

    .. note::
        The ``hidden`` property is only supported by ``Option``, not ``Argument``.

    .. todo::
        Submit a PR to Click to separate production of param spec and help
        record. That way we can always produce the param spec even if the
        parameter is hidden.
        See: https://github.com/kdeldycke/click-extra/issues/689
    """
    if not hasattr(param, "hidden"):
        return None
    with patch.object(param, "hidden", False) if param.hidden else nullcontext():
        help_record = param.get_help_record(ctx)
        return help_record[0] if help_record else None


def format_param_row(
    param: click.Parameter,
    ctx: click.Context,
    path: str,
    is_structured: bool,
) -> tuple:
    """Format the common parameter table cells.

    Returns a tuple of 8 cells in column order: ID, Spec., Class, Param type,
    Python type, Hidden, Env. vars., Default.

    For structured formats (JSON, YAML, etc.), cells are native Python values.
    For visual formats, cells are themed strings matching help-screen styling.
    """
    param_spec = get_param_spec(param, ctx)
    param_class = param.__class__
    class_str = f"{param_class.__module__}.{param_class.__qualname__}"
    type_str = f"{param.type.__module__}.{param.type.__class__.__name__}"
    python_type_name = ParamStructure.get_param_type(param).__name__

    if is_structured:
        default_val = param.get_default(ctx)
        if not isinstance(default_val, (str, int, float, bool, list, type(None))):
            default_val = repr(default_val)
        return (
            path,
            param_spec,
            class_str,
            type_str,
            python_type_name,
            getattr(param, "hidden", None),
            list(param_envvar_ids(param, ctx)),
            default_val,
        )

    # Lazy import to avoid circular dependency with theme.
    from .theme import KO, OK, get_current_theme

    active_theme = get_current_theme()
    hidden = None
    if hasattr(param, "hidden"):
        hidden = OK if param.hidden is True else KO
    return (
        active_theme.invoked_command(path),
        active_theme.option(param_spec) if param_spec else param_spec,
        class_str,
        type_str,
        active_theme.metavar(python_type_name),
        hidden,
        ", ".join(map(active_theme.envvar, param_envvar_ids(param, ctx))),
        active_theme.default(repr(param.get_default(ctx))),
    )


class ShowParamsOption(ExtraOption, ParamStructure):
    """A pre-configured option adding a ``--show-params`` option.

    Between configuration files, default values and environment variables, it might be
    hard to guess under which set of parameters the CLI will be executed. This option
    print information about the parameters that will be fed to the CLI.
    """

    TABLE_HEADERS = (
        "ID",
        "Spec.",
        "Class",
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

        self.excluded_params = frozenset()
        """Deactivates the blocking of any parameter."""

        self.included_params = None
        """No allowlist filter; show all parameters."""

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
        from .config import ConfigOption
        from .table import SERIALIZATION_FORMATS, print_table
        from .theme import KO, OK

        # Exit early if the callback was processed but the option wasn't set.
        if not value:
            return

        logger = logging.getLogger("click_extra")

        get_param_value: Callable[[Any], Any]
        opts: dict = {}

        if ctx_meta.RAW_ARGS in ctx.meta:
            raw_args = ctx.meta.get(ctx_meta.RAW_ARGS, [])
            logger.debug(f"{ctx_meta.RAW_ARGS}: {raw_args}")

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
            logger.debug(f"{ctx_meta.RAW_ARGS} not in {ctx.meta}")
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
        config_option = search_params(ctx.command.get_params(ctx), ConfigOption)
        # This is just a check to please the type checker.
        assert config_option is None or isinstance(config_option, ConfigOption)

        # Resolve the table format early so we know whether to emit typed values.
        if not hasattr(ctx, "print_table"):
            from .table import TableFormatOption

            table_option = search_params(ctx.command.get_params(ctx), TableFormatOption)
            if table_option and isinstance(table_option, TableFormatOption):
                table_fmt, _ = table_option.consume_value(ctx, opts)
                table_option.init_formatter(
                    ctx,
                    table_option,
                    table_option.type.convert(table_fmt, table_option, ctx)
                    if table_fmt
                    else table_option.get_default(ctx),
                )
        print_func = getattr(ctx, "print_table", print_table)

        # Check if the resolved format is a structured serialization format.
        table_format = None
        if hasattr(print_func, "keywords"):
            table_format = print_func.keywords.get("table_format")
        is_structured = table_format in SERIALIZATION_FORMATS

        table: list[tuple[Any, ...]] = []

        # Walk through the the tree of parameters and get their fully-qualified path.
        for path, instances in self.flatten_tree_dict(self.params_objects).items():
            tree_keys = path.split(self.SEP)

            # Multiple parameters can share the same path, if for instance they are
            # sharing the same variable name.
            for instance in instances:
                assert instance.name == tree_keys[-1]

                param_value, source = get_param_value(instance)

                # Check if the parameter is allowed in the configuration file.
                # Access params_objects first to ensure included_params has been
                # resolved into excluded_params via build_param_trees().
                allowed_in_conf_bool = None
                if config_option:
                    config_option.params_template  # noqa: B018
                    allowed_in_conf_bool = path not in config_option.excluded_params

                # Common 8 cells: ID .. Hidden ([:6]) and Env. vars. .. Default ([6:]).
                common = format_param_row(instance, ctx, path, is_structured)

                if is_structured:
                    if not isinstance(
                        param_value, (str, int, float, bool, list, type(None))
                    ):
                        param_value = repr(param_value)
                    line: tuple[Any, ...] = (
                        *common[:6],
                        instance.expose_value,
                        allowed_in_conf_bool,
                        *common[6:],
                        param_value,
                        source.name if source else None,
                    )
                else:
                    allowed_in_conf = None
                    if allowed_in_conf_bool is not None:
                        allowed_in_conf = OK if allowed_in_conf_bool else KO
                    line = (
                        *common[:6],
                        OK if instance.expose_value is True else KO,
                        allowed_in_conf,
                        *common[6:],
                        repr(param_value),
                        source.name if source else None,
                    )
                table.append(line)

        def sort_by_depth(line):
            """Sort parameters by depth first, then IDs, so that top-level parameters
            are kept to the top."""
            param_path = line[0]
            tree_keys = param_path.split(self.SEP)
            return len(tree_keys), param_path

        header_labels: tuple[Any, ...]
        if is_structured:
            header_labels = self.TABLE_HEADERS
        else:
            header_style = Style(bold=True)
            header_labels = tuple(map(header_style, self.TABLE_HEADERS))

        print_func(sorted(table, key=sort_by_depth), headers=header_labels)

        ctx.exit()
