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

from . import UNSET, EnumChoice, ParamType, Style, context, get_current_context
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


class ExtraOption(Option):
    """Dedicated to option implemented by ``click-extra`` itself.

    Provides a way to identify Click Extra's own options with certainty, and
    restores the pre-Click-8.4.0 contract that eager callbacks can introspect
    their own parameter source from within their own callback.

    .. note::
        Bracket fields (envvar, default, range, required) cannot be pre-styled in
        ``get_help_record()`` because Click's text wrapper splits lines *after* the
        record is returned, which would break ANSI codes that span wrapped boundaries.
        Styling is instead applied post-wrapping in
        ``HelpExtraFormatter._style_bracket_fields()``, which uses the structured data
        from ``Option.get_help_extra()`` to identify each field by its label.
    """

    def handle_parse_result(self, ctx, opts, args):
        """Record the parameter source before delegating to the base implementation.

        .. warning::
            Click ``8.4.0`` (PR `pallets/click#3404
            <https://github.com/pallets/click/pull/3404>`_) reordered
            ``Parameter.handle_parse_result`` so ``ctx.set_parameter_source`` runs
            *after* ``process_value``. Eager callbacks that introspect their own
            provenance via ``ctx.get_parameter_source(self.name)`` therefore read
            ``None`` instead of the actual source. ``ColorOption``, ``ConfigOption``,
            and ``ShowParamsOption`` all rely on this introspection to decide whether
            an env var should override the default (``--color``), whether the
            ``--config`` path was user-supplied, and what to render in the ``Source``
            column of ``--show-params``.

            Click ``8.4.1`` restored the pre-``8.4.0`` contract upstream (PR
            `pallets/click#3484 <https://github.com/pallets/click/pull/3484>`_), so
            this override only matters for Click ``8.4.0`` itself, which sits inside
            click-extra's supported ``>= 8.3.1`` range. Pre-recording the source here
            for eager options keeps that contract on every supported Click.
            ``super().handle_parse_result`` re-records the same value at the canonical
            time, so the slot arbitration logic introduced by #3404 is unaffected:
            ``slot_empty`` is computed from ``ctx.params``, not from
            ``_parameter_source``.

            ``consume_value`` runs twice as a side effect: once here and once in
            ``super``. Both calls are pure for click-extra's existing eager
            flag-style options (no env var side effects, no prompt). Should a future
            eager subclass need prompt behavior, this override would need to cache
            the result instead.

            The pre-record is skipped when the slot already carries a source from
            an earlier option sharing the same ``name`` (Click's feature-switch
            pattern), so the arbitration logic in ``super`` still sees the original
            ``existing_source`` rather than a stale rewrite from this option.
        """
        if self.is_eager and ctx.get_parameter_source(self.name) is None:
            _value, source = self.consume_value(ctx, opts)
            ctx.set_parameter_source(self.name, source)
        return super().handle_parse_result(ctx, opts, args)


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
) -> dict[str, Any]:
    """Compute the *structural* table cells for a Click parameter.

    Returns a ``dict[column_id, cell]`` covering every column that can be
    derived from the parameter object alone (no runtime invocation state or
    config-file context). Specifically: ``id``, ``spec``, ``class``,
    ``param_type``, ``python_type``, ``hidden``, ``exposed``, ``envvars``,
    ``default``, ``is_flag``, ``flag_value``, ``is_bool_flag``, ``multiple``,
    ``nargs``, ``prompt``, and ``confirmation_prompt``.

    Attributes only defined on ``click.Option`` (``hidden``, ``is_flag``,
    ``flag_value``, ``is_bool_flag``, ``prompt``, ``confirmation_prompt``)
    yield ``None`` for ``click.Argument`` parameters: empty cell in visual
    formats, ``null`` in structured ones.

    For structured formats (JSON, YAML, etc.), values are native Python types.
    For visual formats, values are themed strings matching help-screen styling.

    The remaining table columns (``allowed_in_conf``, ``value``, ``source``)
    require live context and are filled in by :func:`render_params_table`.
    """
    param_spec = get_param_spec(param, ctx)
    param_class = param.__class__
    class_str = f"{param_class.__module__}.{param_class.__qualname__}"
    type_str = f"{param.type.__module__}.{param.type.__class__.__name__}"
    python_type_name = ParamStructure.get_param_type(param).__name__

    hidden = getattr(param, "hidden", None)
    is_flag = getattr(param, "is_flag", None)
    flag_value = getattr(param, "flag_value", None)
    is_bool_flag = getattr(param, "is_bool_flag", None)
    prompt = getattr(param, "prompt", None)
    confirmation_prompt = getattr(param, "confirmation_prompt", None)

    if is_structured:
        default_val = param.get_default(ctx)
        if not isinstance(default_val, (str, int, float, bool, list, type(None))):
            default_val = repr(default_val)
        if not isinstance(flag_value, (str, int, float, bool, list, type(None))):
            flag_value = repr(flag_value)
        return {
            "id": path,
            "spec": param_spec,
            "class": class_str,
            "param_type": type_str,
            "python_type": python_type_name,
            "hidden": hidden,
            "exposed": param.expose_value,
            "envvars": list(param_envvar_ids(param, ctx)),
            "default": default_val,
            "is_flag": is_flag,
            "flag_value": flag_value,
            "is_bool_flag": is_bool_flag,
            "multiple": param.multiple,
            "nargs": param.nargs,
            "prompt": prompt,
            "confirmation_prompt": confirmation_prompt,
        }

    # Lazy import to avoid circular dependency with theme.
    from .theme import KO_GLYPH, OK_GLYPH, get_current_theme

    active_theme = get_current_theme()

    def styled_bool(value):
        """Render a boolean attribute as a themed glyph, or ``None`` if absent."""
        if value is None:
            return None
        return (
            active_theme.success(OK_GLYPH)
            if value is True
            else active_theme.error(KO_GLYPH)
        )

    return {
        "id": active_theme.invoked_command(path),
        "spec": active_theme.option(param_spec) if param_spec else param_spec,
        "class": class_str,
        "param_type": type_str,
        "python_type": active_theme.metavar(python_type_name),
        "hidden": styled_bool(hidden),
        "exposed": styled_bool(param.expose_value),
        "envvars": ", ".join(map(active_theme.envvar, param_envvar_ids(param, ctx))),
        "default": active_theme.default(repr(param.get_default(ctx))),
        "is_flag": styled_bool(is_flag),
        "flag_value": (
            active_theme.default(repr(flag_value)) if flag_value is not None else None
        ),
        "is_bool_flag": styled_bool(is_bool_flag),
        "multiple": styled_bool(param.multiple),
        "nargs": str(param.nargs),
        "prompt": prompt,
        "confirmation_prompt": styled_bool(confirmation_prompt),
    }


#: Separator joining the keys of a parameter's fully-qualified path
#: (``cli.subcommand.param``).
PARAM_PATH_SEP = "."


def walk_command_params(
    cmd: click.Command,
    ctx: click.Context,
    parent_keys: tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], click.Parameter, click.Context]]:
    """Walk the parameter tree of a Click command and all its subcommands.

    Yields ``(path_keys, param, owning_ctx)`` for every parameter found on
    *cmd* and, recursively, on each subcommand. Each subcommand is walked under
    its own freshly-built child context, so context-sensitive metadata (notably
    the auto-generated environment variable, which derives from
    ``Context.auto_envvar_prefix``) is computed at the correct nesting level
    rather than inherited from the root.

    A subcommand whose name collides with a sibling parameter at the same level
    is skipped: a single fully-qualified path cannot address both an option and
    a subcommand at once.
    """
    level_param_names = set()
    for param in cmd.get_params(ctx):
        if param.name is not None:
            level_param_names.add(param.name)
            yield (*parent_keys, param.name), param, ctx

    if isinstance(cmd, click.Group):
        for subcmd_name in sorted(cmd.list_commands(ctx)):
            if subcmd_name in level_param_names:
                logging.getLogger("click_extra").debug(
                    f"{cmd.name}{PARAM_PATH_SEP}{subcmd_name} subcommand shadows a "
                    f"top-level parameter; excluded from parameter tree.",
                )
                continue
            subcmd = cmd.get_command(ctx, subcmd_name)
            if subcmd is None:
                continue
            subcmd_ctx = click.Context(subcmd, parent=ctx, info_name=subcmd_name)
            yield from walk_command_params(
                subcmd, subcmd_ctx, (*parent_keys, subcmd_name)
            )


def render_params_table(
    subject_ctx: click.Context,
    *,
    default_columns: Sequence[str] | None = None,
) -> None:
    """Introspect ``subject_ctx.command`` and print its parameter metadata table.

    Walks the command and any nested subcommands, emitting one row per
    parameter. The table format and column selection are read from
    ``subject_ctx.meta`` (see :data:`~click_extra.context.TABLE_FORMAT` and
    :data:`~click_extra.context.COLUMNS`); when neither is set, a sibling
    ``--table-format`` / ``--columns`` option on the command is consulted, then
    the *default_columns* fallback, then the canonical order.

    When ``subject_ctx.meta`` carries pre-parsed
    :data:`~click_extra.context.RAW_ARGS`, the ``value`` and ``source`` columns
    are resolved by replaying those arguments against the command parser;
    otherwise they fall back to the parameter defaults.

    This is the shared rendering core behind both
    :meth:`ShowParamsOption.print_params` (introspecting the live CLI) and the
    ``click-extra wrap --show-params`` path (introspecting a foreign target).
    The caller is responsible for exiting the context afterwards.

    .. important::
        Click does not keep the raw, pre-parsed arguments around, so values and
        their provenance cannot be read back directly. The workaround replays
        :data:`~click_extra.context.RAW_ARGS` (captured on the context by
        ``ExtraCommand``/``ExtraGroup``) through the command parser, calling
        ``consume_value()`` rather than ``handle_parse_result()`` so eager
        callbacks are not re-triggered.
    """
    # Imported here to avoid circular imports with the table module.
    from .config import ConfigOption
    from .table import (
        DEFAULT_FORMAT,
        SERIALIZATION_FORMATS,
        ColumnsOption,
        TableFormatOption,
        print_table,
        select_columns,
        select_row,
    )
    from .theme import KO_GLYPH, OK_GLYPH, get_current_theme

    active_theme = get_current_theme()
    ok_styled = active_theme.success(OK_GLYPH)
    ko_styled = active_theme.error(KO_GLYPH)

    cmd = subject_ctx.command
    logger = logging.getLogger("click_extra")

    # Resolve the value getter. When the original arguments are available we
    # replay them through the command parser to recover each value and its
    # provenance; otherwise we only know the parameter defaults.
    opts: dict = {}
    raw_args = context.get(subject_ctx, context.RAW_ARGS)
    if raw_args is not None:
        logger.debug(f"{context.RAW_ARGS}: {raw_args}")
        parser = cmd.make_parser(subject_ctx)
        opts, _, _ = parser.parse_args(args=list(raw_args))
        get_param_value: Callable[[click.Parameter], tuple[Any, Any]] = methodcaller(
            "consume_value", subject_ctx, opts
        )
    else:

        def get_param_value(param):
            return None, subject_ctx.get_parameter_source(param.name)

    # Locate a --config option to fill the "allowed in conf?" column.
    config_option = search_params(cmd.get_params(subject_ctx), ConfigOption)
    assert config_option is None or isinstance(config_option, ConfigOption)

    # Resolve the table format: an explicit context entry wins, else a sibling
    # --table-format option, else the default.
    if context.get(subject_ctx, context.TABLE_FORMAT) is None:
        table_option = search_params(cmd.get_params(subject_ctx), TableFormatOption)
        if table_option and isinstance(table_option, TableFormatOption):
            table_fmt, _ = table_option.consume_value(subject_ctx, opts)
            table_option.init_formatter(
                subject_ctx,
                table_option,
                table_option.type.convert(table_fmt, table_option, subject_ctx)
                if table_fmt
                else table_option.get_default(subject_ctx),
            )
    table_format = context.get(subject_ctx, context.TABLE_FORMAT) or DEFAULT_FORMAT
    is_structured = table_format in SERIALIZATION_FORMATS

    # Resolve the column selection: an explicit context entry wins, else a
    # sibling --columns option, else the provided default.
    if context.get(subject_ctx, context.COLUMNS) is None:
        cols_option = search_params(cmd.get_params(subject_ctx), ColumnsOption)
        if cols_option and isinstance(cols_option, ColumnsOption):
            cols_value, _ = cols_option.consume_value(subject_ctx, opts)
            cols_option.init_columns(
                subject_ctx,
                cols_option,
                cols_option.type.convert(cols_value, cols_option, subject_ctx)
                if cols_value
                else (),
            )
    selected_ids: tuple[str, ...] = context.get(subject_ctx, context.COLUMNS) or ()
    if not selected_ids and default_columns:
        selected_ids = tuple(default_columns)

    # Validate the requested IDs against the column registry so unknown IDs
    # become a clear, actionable UsageError.
    canonical_ids = ShowParamsOption.column_ids()
    known_ids = set(canonical_ids)
    unknown = [col_id for col_id in selected_ids if col_id not in known_ids]
    if unknown:
        joined = ", ".join(repr(c) for c in unknown)
        accepted = ", ".join(canonical_ids)
        raise click.UsageError(
            f"Unknown --columns ID(s): {joined}. Accepted: {accepted}.",
            ctx=subject_ctx,
        )

    table: list[tuple[Any, ...]] = []
    for keys, param, owning_ctx in walk_command_params(
        cmd, subject_ctx, (cmd.name or "",)
    ):
        path = PARAM_PATH_SEP.join(keys)
        param_value, source = get_param_value(param)

        # Whether the parameter is reachable from a configuration file.
        allowed_in_conf_bool = None
        if config_option:
            config_option.params_template  # noqa: B018
            allowed_in_conf_bool = path not in config_option.excluded_params

        row = format_param_row(param, owning_ctx, path, is_structured)

        if is_structured:
            if not isinstance(param_value, (str, int, float, bool, list, type(None))):
                param_value = repr(param_value)
            row["allowed_in_conf"] = allowed_in_conf_bool
            row["value"] = param_value
            row["source"] = source.name if source else None
        else:
            allowed_in_conf = None
            if allowed_in_conf_bool is not None:
                allowed_in_conf = ok_styled if allowed_in_conf_bool else ko_styled
            row["allowed_in_conf"] = allowed_in_conf
            row["value"] = repr(param_value)
            row["source"] = source.name if source else None

        table.append(select_row(row, selected_ids, canonical_ids))

    def sort_by_depth(line: Sequence[Any]) -> tuple[int, Any]:
        """Sort by depth first, then path, keeping top-level params on top."""
        param_path = line[0]
        return len(param_path.split(PARAM_PATH_SEP)), param_path

    selected_columns = select_columns(ShowParamsOption.TABLE_HEADERS, selected_ids)
    labels = tuple(col.label for col in selected_columns)
    header_labels: tuple[Any, ...]
    if is_structured:
        header_labels = labels
    else:
        header_style = Style(bold=True)
        header_labels = tuple(map(header_style, labels))

    print_table(
        sorted(table, key=sort_by_depth),
        headers=header_labels,
        table_format=table_format,
    )


class ShowParamsOption(ExtraOption, ParamStructure):
    """A pre-configured option adding a ``--show-params`` option.

    Between configuration files, default values and environment variables, it might be
    hard to guess under which set of parameters the CLI will be executed. This option
    print information about the parameters that will be fed to the CLI.
    """

    from .table import ColumnSpec as _ColumnSpec

    TABLE_HEADERS: ClassVar[tuple[_ColumnSpec, ...]] = (
        _ColumnSpec(
            id="id",
            label="ID",
            description=(
                "Fully-qualified parameter path (`cli.subcommand.param-name`) "
                "derived from the [`click.Command`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Command) "
                "tree. Doubles as the key used to address the parameter from a "
                "configuration file."
            ),
        ),
        _ColumnSpec(
            id="spec",
            label="Spec.",
            description=(
                "Option/argument specification string (like `-v, --verbose`) "
                "extracted from [`click.Parameter.get_help_record()`]"
                "(https://click.palletsprojects.com/en/stable/api/"
                "#click.Parameter.get_help_record)."
            ),
        ),
        _ColumnSpec(
            id="class",
            label="Class",
            description=(
                "Fully-qualified class of the parameter: a subclass of "
                "[`click.Option`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option), "
                "[`click.Argument`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Argument), "
                "[`cloup.Option`]"
                "(https://cloup.readthedocs.io/en/stable/autoapi/cloup/"
                "index.html#cloup.Option), "
                "or one of Click Extra's own wrappers "
                "([`click_extra.parameters.Option`](#click_extra.parameters.Option), "
                "[`click_extra.parameters.Argument`]"
                "(#click_extra.parameters.Argument), "
                "[`click_extra.parameters.ExtraOption`]"
                "(#click_extra.parameters.ExtraOption))."
            ),
        ),
        _ColumnSpec(
            id="param_type",
            label="Param type",
            description=(
                "Click value converter class: a subclass of [`click.ParamType`]"
                "(https://click.palletsprojects.com/en/stable/api/"
                "#click.ParamType) like [`click.IntRange`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.IntRange), "
                "[`click.Choice`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Choice), "
                "or a Click Extra type."
            ),
        ),
        _ColumnSpec(
            id="python_type",
            label="Python type",
            description=(
                "Python built-in type the parsed value resolves to: "
                "[`str`](https://docs.python.org/3/library/stdtypes.html"
                "#text-sequence-type-str), "
                "[`int`](https://docs.python.org/3/library/functions.html#int), "
                "[`float`](https://docs.python.org/3/library/functions.html#float), "
                "[`bool`](https://docs.python.org/3/library/functions.html#bool), "
                "or [`list`](https://docs.python.org/3/library/stdtypes.html#list). "
                "Computed by [`ParamStructure.get_param_type()`]"
                "(#click_extra.parameters.ParamStructure.get_param_type) from "
                "the Click `Param type`."
            ),
        ),
        _ColumnSpec(
            id="hidden",
            label="Hidden",
            description=(
                "Reflects [`click.Option`'s `hidden`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option) "
                "constructor argument: the option is omitted from `--help` output. "
                "Empty for [`click.Argument`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Argument), "
                "which does not support hiding."
            ),
        ),
        _ColumnSpec(
            id="exposed",
            label="Exposed",
            description=(
                "Reflects [`click.Parameter`'s `expose_value`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Parameter) "
                "constructor argument: whether the parsed value is forwarded to "
                "the command callback. Eager options like `--show-params` and "
                "`--help` typically run a callback and exit, so they are not "
                "exposed."
            ),
        ),
        _ColumnSpec(
            id="allowed_in_conf",
            label="Allowed in conf?",
            description=(
                "Click Extra-specific: whether the parameter is reachable from a "
                "configuration file. Controlled by [`ParamStructure.excluded_params`]"
                "(#click_extra.parameters.ParamStructure.excluded_params) and "
                "[`included_params`]"
                "(#click_extra.parameters.ParamStructure.included_params). Empty "
                "when the CLI has no [`--config` option](config.md)."
            ),
        ),
        _ColumnSpec(
            id="envvars",
            label="Env. vars.",
            description=(
                "Environment variables read for this parameter: the explicit "
                "[`click.Parameter`'s `envvar`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Parameter) "
                "plus the auto-resolved IDs documented in "
                "[Environment variables](envvar.md)."
            ),
        ),
        _ColumnSpec(
            id="default",
            label="Default",
            description=(
                "Default value returned by [`click.Parameter.get_default()`]"
                "(https://click.palletsprojects.com/en/stable/api/"
                "#click.Parameter.get_default), rendered as its Python `repr()`."
            ),
        ),
        _ColumnSpec(
            id="is_flag",
            label="Is flag",
            description=(
                "Reflects [`click.Option`'s `is_flag`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option): "
                "whether the option behaves as a flag (no value taken from the "
                "command line). Empty for [`click.Argument`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Argument)."
            ),
        ),
        _ColumnSpec(
            id="flag_value",
            label="Flag value",
            description=(
                "Reflects [`click.Option`'s `flag_value`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option): "
                "the Python value substituted for the option when its flag is "
                "used. Defaults to `True` for boolean flags, can be any value "
                "for flag-value style options "
                "(like `@option('--upper', 'transform', flag_value='upper')`)."
            ),
        ),
        _ColumnSpec(
            id="is_bool_flag",
            label="Is bool flag",
            description=(
                "Reflects `click.Option.is_bool_flag` (set internally by Click "
                "when `flag_value` is `True` or `False`): the option is a *true* "
                "boolean flag, as opposed to a flag-value style option."
            ),
        ),
        _ColumnSpec(
            id="multiple",
            label="Multiple",
            description=(
                "Reflects [`click.Parameter`'s `multiple`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Parameter): "
                "the parameter can be repeated on the command line, collecting "
                "values into a tuple."
            ),
        ),
        _ColumnSpec(
            id="nargs",
            label="Nargs",
            description=(
                "Reflects [`click.Parameter`'s `nargs`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Parameter): "
                "the number of CLI tokens the parameter consumes. `1` is the "
                "default; `-1` denotes a variadic argument."
            ),
        ),
        _ColumnSpec(
            id="prompt",
            label="Prompt",
            description=(
                "Reflects [`click.Option`'s `prompt`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option): "
                "the text shown to the user when the option is not provided on "
                "the command line. Empty when no prompt is configured."
            ),
        ),
        _ColumnSpec(
            id="confirmation_prompt",
            label="Confirmation prompt",
            description=(
                "Reflects [`click.Option`'s `confirmation_prompt`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option): "
                "whether the user is asked to enter the value twice for "
                "confirmation."
            ),
        ),
        _ColumnSpec(
            id="value",
            label="Value",
            description=(
                "Current value of the parameter at invocation time, computed by "
                "[`click.Parameter.consume_value()`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Parameter) "
                "from the merged sources (CLI, environment, config file, default)."
            ),
        ),
        _ColumnSpec(
            id="source",
            label="Source",
            description=(
                "Provenance of the resolved value: a [`click.core.ParameterSource`]"
                "(https://click.palletsprojects.com/en/stable/api/"
                "#click.core.ParameterSource) enum member such as `COMMANDLINE`, "
                "`ENVIRONMENT`, `DEFAULT_MAP`, or `DEFAULT`."
            ),
        ),
    )
    """Rich column registry for the ``--show-params`` table.

    Each entry is a :class:`click_extra.table.ColumnSpec` carrying the column's
    stable ``id`` (used by ``--columns`` and as structured-format key), its
    display ``label``, and a MyST/Markdown ``description`` consumed by the
    documentation's auto-generated *Available columns* section. Iteration
    yields columns in canonical display order.
    """

    @classmethod
    def column_labels(cls) -> tuple[str, ...]:
        """Return just the display labels of :data:`TABLE_HEADERS` (in order)."""
        return tuple(col.label for col in cls.TABLE_HEADERS)

    @classmethod
    def column_ids(cls) -> tuple[str, ...]:
        """Return just the stable IDs of :data:`TABLE_HEADERS` (in order)."""
        return tuple(col.id for col in cls.TABLE_HEADERS)

    @classmethod
    def find_column(cls, column_id: str):
        """Return the :class:`ColumnSpec` matching ``column_id``.

        Raises ``KeyError`` if no column has this ID; callers should convert
        the error into a :class:`click.UsageError` when surfaced to a user.
        """
        for col in cls.TABLE_HEADERS:
            if col.id == column_id:
                return col
        msg = f"Unknown column ID {column_id!r}"
        raise KeyError(msg)

    @classmethod
    def render_doc_table(cls) -> str:
        """Render :data:`TABLE_HEADERS` as a Markdown table for documentation.

        Used by the ``show_params_columns_table`` MyST substitution in
        ``docs/conf.py`` to feed the *Available columns* section of
        ``docs/parameters.md``: editing a description here automatically
        rebuilds the docs table on the next ``sphinx-build``.
        """
        from .table import render_columns_markdown_table

        return render_columns_markdown_table(cls.TABLE_HEADERS)

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
        """Introspect the current CLI and print its parameter metadata table.

        Thin wrapper over :func:`render_params_table`, the shared rendering core
        also driving ``click-extra wrap --show-params`` for foreign CLIs. The
        live invocation context carries everything the core needs: the captured
        :data:`~click_extra.context.RAW_ARGS` (attached by
        ``ExtraCommand``/``ExtraGroup``) for value and source resolution, plus
        any sibling ``--table-format`` / ``--columns`` options.
        """
        # Exit early if the callback was processed but the option wasn't set.
        if not value:
            return

        # Warn when the live command is not an ExtraCommand: without the captured
        # raw arguments, the value/source columns fall back to defaults.
        if context.get(ctx, context.RAW_ARGS) is None:
            logging.getLogger("click_extra").warning(
                f"Cannot extract parameters values: "
                f"{ctx.command} does not inherits from ExtraCommand.",
            )

        render_params_table(ctx)
        ctx.exit()
