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
"""Options to pick a table's format, sort its rows and select its columns.

`--table-format`, `--sort-by` and `--columns` publish their choice on the
context, where the renderers of {mod}`click_extra.table` read it.
"""

from __future__ import annotations

from functools import partial
from gettext import gettext as _

import click

# The commands module imports this one: its `Context` is read through the module
# object, once the callbacks run.
from . import commands, context
from .parameters import ExtraOption
from .table import (
    DEFAULT_FORMAT,
    TableFormat,
    _defs_sort_key,
    _normalize_column_def,
    _row_sort_key,
    print_table,
    render_table,
)
from .types import EnumChoice, MultiChoice

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    from .columns import ColumnSpec
    from .table import TColumnDef


class TableFormatOption(ExtraOption):
    """A pre-configured option that is adding a `--table-format` flag to select
    the rendering style of a table.

    The selected table format ID is made available in the context in
    `ctx.meta[click_extra.context.TABLE_FORMAT]`, where the
    {meth}`~click_extra.commands.Context.render_table` and
    {meth}`~click_extra.commands.Context.print_table` context methods pick it
    up as their default format. `ctx.meta` is shared along the context
    chain, so declaring this option on a group makes the selected format reach
    every subcommand:

    - `ctx.render_table(table_data, headers, **kwargs)`: renders and returns
      the table as a string,
    - `ctx.print_table(table_data, headers, **kwargs)`: renders and prints
      the table to the console.

    Where:

    - `table_data` is a 2-dimensional iterable of iterables for rows and cells values,
    - `headers` is a list of string to be used as column headers,
    - `**kwargs` are any extra keyword arguments supported by the underlying table
      formatting function.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
        type: click.ParamType | Any = EnumChoice(TableFormat),
        metavar: str = "FORMAT",
        default: TableFormat = DEFAULT_FORMAT,
        expose_value: bool = False,
        is_eager: bool = True,
        help: str = _("Rendering style of tables."),
        **kwargs: Any,
    ) -> None:
        if not param_decls:
            param_decls = ("--table-format",)

        kwargs.setdefault("callback", self.init_formatter)

        super().__init__(
            param_decls=param_decls,
            type=type,
            metavar=metavar,
            default=default,
            expose_value=expose_value,
            help=help,
            is_eager=is_eager,
            **kwargs,
        )

    def init_formatter(
        self,
        ctx: click.Context,
        param: click.Parameter,
        table_format: TableFormat | None,
    ) -> None:
        """Save the resolved `table_format` in the context's shared `meta`.

        The {meth}`~click_extra.commands.Context.render_table` and
        {meth}`~click_extra.commands.Context.print_table` context methods read
        it back at call time.
        """
        if ctx.resilient_parsing:
            return

        context.set(ctx, context.TABLE_FORMAT, table_format)

        # Foreign click/cloup commands run with a plain click.Context, which
        # lacks the enhanced Context.render_table/print_table methods: give
        # them bound equivalents as instance attributes so this option stays a
        # drop-in on any Click CLI.
        if not isinstance(ctx, commands.Context):
            ctx.render_table = partial(  # type: ignore[attr-defined]
                render_table,
                table_format=table_format,
            )
            ctx.print_table = partial(  # type: ignore[attr-defined]
                print_table,
                table_format=table_format,
            )


def column_sort_key(
    header_defs: Sequence[TColumnDef],
    sort_columns: Sequence[str] | None = None,
    cell_key: Callable[[str | None], Any] | None = None,
) -> Callable[[Sequence[str | None]], tuple] | None:
    """Build a row sort key from the `sort_columns` a table actually carries.

    `header_defs` describes the rendered columns:
    {class}`~click_extra.columns.ColumnSpec` instances, with `sortable=False` for
    columns that cannot be sorted on. The requested `sort_columns` the table carries
    drive the comparison first, de-duplicated and in request order; the remaining
    columns follow in their natural left-to-right order for tie-breaking.

    Returns `None` when the table carries none of the requested columns,
    signalling that rows should keep their original order. This is what lets
    one `--sort-by` selection apply across subcommands rendering
    heterogeneous tables: each table sorts by the requested fields it knows,
    and a table knowing none of them is left untouched.
    """
    return _defs_sort_key(
        tuple(_normalize_column_def(c) for c in header_defs), sort_columns, cell_key
    )


def _column_sort_key(
    header_defs: Sequence[tuple[str | None, str | None]],
    sort_columns: Sequence[str] | None = None,
    cell_key: Callable[[str | None], Any] | None = None,
) -> Callable[[Sequence[str | None]], tuple]:
    """Like {func}`column_sort_key`, but always sorts.

    When none of the `sort_columns` is carried by `header_defs` (or none
    is requested), rows still sort, comparing every column in natural
    left-to-right order. This is the key {class}`SortByOption` publishes on
    the context (`click_extra.context.TABLE_SORT_KEY`) when its column
    definitions are known at declaration time.
    """
    key = _defs_sort_key(header_defs, sort_columns, cell_key)
    if key is None:
        key = _row_sort_key(range(len(header_defs)), cell_key)
    return key


class ColumnsType(MultiChoice):
    """{class}`~click_extra.types.MultiChoice` over the IDs of table columns.

    Pins the comma separator and case-sensitive matching (column IDs are
    snake_case identifiers, not free-form strings), and renames the metavar
    fallback to `COLUMNS` instead of the generic `MULTI`.
    """

    name = "columns"

    def __init__(self, choices: Sequence[str] = ()) -> None:
        super().__init__(choices=choices, separator=",", case_sensitive=True)


class ColumnsOption(ExtraOption):
    """A `--columns` option that lets users restrict and reorder table columns.

    Accepts a comma-separated list of column IDs, SQL-`SELECT`-style:

    ```{code-block} shell-session

    $ my-cli --columns id,spec,value --params
    ```

    The selection is stored in
    {data}`ctx.meta[click_extra.context.COLUMNS] <click_extra.context.COLUMNS>` and
    consumed by table-rendering callbacks (like
    {class}`click_extra.show_params.ShowParamsOption`) to project rows + headers
    before rendering.

    Pass `columns=` at construction time with the column registry the option
    should advertise: the help text then lists the accepted IDs and the default
    selection, and the callback validates the user input against that registry
    so unknown IDs fail fast with a {class}`click.UsageError`. Without
    `columns=`, the option stays generic: it parses any IDs and leaves
    validation to the downstream consumer.

    Empty / unset means *render every column in canonical order*: the default
    behavior, indistinguishable from not passing `--columns` at all.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
        columns: Sequence[ColumnSpec] | None = None,
        type: click.ParamType | Any | None = None,
        metavar: str = "COLUMNS",
        default: Sequence[str] | None = (),
        expose_value: bool = False,
        is_eager: bool = True,
        help: str = _(
            "Restrict and reorder table columns, SQL SELECT-style. "
            "Comma-separated list of column IDs. Default: all columns in "
            "canonical order.",
        ),
        **kwargs: Any,
    ) -> None:
        if not param_decls:
            param_decls = ("--columns",)

        self.columns: tuple[ColumnSpec, ...] = tuple(columns or ())
        """Column registry this option advertises and validates against (may be empty)."""

        # The registry still reaches the type, which validates against it and
        # reports the IDs to every doc render. The help screen shows the
        # `COLUMNS` placeholder instead of the enumeration: a table wide enough
        # to be worth projecting carries more IDs than a metavar can hold, and
        # the unwrappable line pushes the description off the column and past
        # the terminal's width. The `man`, `markdown` and `json` renders list
        # them, see `DocOptionItem.unlisted_choices`.
        if type is None:
            type = ColumnsType(choices=tuple(c.id for c in self.columns))

        kwargs.setdefault("callback", self.init_columns)

        super().__init__(
            param_decls=param_decls,
            type=type,
            metavar=metavar,
            default=default,
            expose_value=expose_value,
            help=help,
            is_eager=is_eager,
            **kwargs,
        )

    def init_columns(
        self,
        ctx: click.Context,
        param: click.Parameter,
        columns: tuple[str, ...],
    ) -> None:
        """Store the selected column IDs on the context for later projection.

        {meth}`~click_extra.types.MultiChoice.convert` validates the IDs against
        the registry before this callback runs, so this only threads the parsed
        selection onto the context.
        """
        if ctx.resilient_parsing:
            return
        context.set(ctx, context.COLUMNS, tuple(columns or ()))


class SortByOption(ExtraOption):
    """A `--sort-by` option whose choices are derived from column definitions.

    Stores the selected column IDs in `ctx.meta[click_extra.context.SORT_BY]`
    and publishes the derived row sort key in
    `ctx.meta[click_extra.context.TABLE_SORT_KEY]`, which `ctx.print_table`
    picks up so that table output is automatically sorted, without changing its
    `(table_data, headers)` call contract. The option accepts
    `multiple=True`, so users can repeat `--sort-by` to define a
    multi-column sort priority.

    Column definitions are `ColumnSpec` instances, passed positionally or via
    the `columns=` keyword. A column marked `sortable=False` keeps its place in
    the layout without being offered as a choice. Passing a `ColumnSpec`
    registry via `columns=` lets the same tuple drive both `ColumnsOption`
    (`--columns`) and `--sort-by`, so the two options stay in sync from a
    single source of truth.

    ```{code-block} python

    COLUMNS = (
        ColumnSpec("package_id", "Package ID"),
        ColumnSpec("package_name", "Name"),
        ColumnSpec("manager_id", "Manager"),
    )


    @command
    @table_format_option
    @columns_option(columns=COLUMNS)
    @sort_by_option(columns=COLUMNS)
    @pass_context
    def my_cmd(ctx):
        ctx.print_table(rows, [col.label for col in COLUMNS])
    ```

    Definitions may instead be bare column ID strings, declaring a
    **field vocabulary** untied to any single table layout. This fits a
    `--sort-by` declared once on a group whose subcommands render
    heterogeneous tables: no sort key is published since no layout is known up
    front. The selection is resolved per table by
    {func}`~click_extra.table.print_table`, from
    the column IDs its headers carry: each table sorts by the selected fields
    it knows (remaining columns breaking ties left to right) and keeps its
    original row order when it knows none.

    ```{code-block} python

    @group
    @sort_by_option("package_id", "package_name", "manager_id")
    def my_cli():
        pass


    @my_cli.command
    def installed():
        print_table(
            rows,
            [
                ColumnSpec("package_id", "Package ID"),
                ColumnSpec("manager_id", "Manager"),
            ],
        )


    @my_cli.command
    def managers():
        print_table(rows, [ColumnSpec("manager_id", "Manager"), "Path"])
    ```
    """

    def __init__(
        self,
        *header_defs: TColumnDef,
        param_decls: Sequence[str] | None = None,
        columns: Sequence[TColumnDef] | None = None,
        default: str | Sequence[str] | None = None,
        expose_value: bool = False,
        cell_key: Callable[[str | None], Any] | None = None,
        help: str = _("Sort table by this column. Repeat to set priority."),
        **kwargs: Any,
    ) -> None:
        if not param_decls:
            param_decls = ("--sort-by",)

        # Accept a shared `columns=` registry (the same `ColumnSpec` tuple
        # passed to `--columns`) or positional definitions. Each entry is a
        # `ColumnSpec` or a bare column ID string.
        if columns is not None and header_defs:
            msg = "Pass column definitions positionally or via columns=, not both."
            raise TypeError(msg)
        raw_defs = columns if columns is not None else header_defs
        self.header_defs = tuple(_normalize_column_def(c) for c in raw_defs)
        self.cell_key = cell_key

        # Bare column IDs declare a table-less field vocabulary; labeled
        # definitions describe one table's layout. Mixing both would leave the
        # labeled part baking a sort over a layout the vocabulary part denies.
        labeled = [d for d in self.header_defs if d[0] is not None]
        if labeled and len(labeled) != len(self.header_defs):
            msg = "Pass either bare column IDs or labeled column definitions, not both."
            raise TypeError(msg)

        self.field_vocabulary = bool(self.header_defs) and not labeled
        """Whether definitions are bare column IDs, untied to any table layout.

        In this mode {meth}`init_sort` only publishes the selection on the
        context: the sort is resolved per table at
        {func}`~click_extra.table.print_table` time.
        """

        sortable_ids = [col_id for _, col_id in self.header_defs if col_id]

        # Normalize default to a tuple for multiple mode. `None` derives the
        # first sortable ID; an explicit empty sequence declares no default
        # sort, so bare invocations keep the original row order.
        if default is None:
            default = (sortable_ids[0],) if sortable_ids else ()
        elif isinstance(default, str):
            default = (default,)
        else:
            default = tuple(default)

        kwargs.setdefault("callback", self.init_sort)

        super().__init__(
            param_decls=param_decls,
            type=click.Choice(sortable_ids, case_sensitive=False),
            default=default,
            expose_value=expose_value,
            help=help,
            multiple=True,
            **kwargs,
        )

    def init_sort(
        self,
        ctx: click.Context,
        param: click.Parameter,
        sort_columns: tuple[str, ...],
    ) -> None:
        """Publish the row sort key on the context's shared `meta`.

        Builds the sort key from this option's column definitions and the
        selected `sort_columns`, then stores it under
        `ctx.meta[click_extra.context.TABLE_SORT_KEY]`, where
        `ctx.print_table` picks it up. The call contract is the same sorted
        or not: `ctx.print_table(table_data, headers)`.

        In field-vocabulary mode no table layout is known at declaration time,
        so no key is published: only the selection lands on the context
        (`ctx.meta` is shared with every subcommand), resolved per table by
        {func}`~click_extra.table.print_table` from the column IDs its headers carry.
        """
        if ctx.resilient_parsing:
            return

        context.set(ctx, context.SORT_BY, sort_columns)

        if self.field_vocabulary:
            return

        sort_key = _column_sort_key(self.header_defs, sort_columns, self.cell_key)
        context.set(ctx, context.TABLE_SORT_KEY, sort_key)

        # Same foreign-command escape hatch as TableFormatOption.init_formatter:
        # rebind the instance attribute with the sort baked in, since a plain
        # click.Context has no meta-reading print_table method.
        if not isinstance(ctx, commands.Context):
            ctx.print_table = partial(  # type: ignore[attr-defined]
                print_table,
                table_format=context.get(ctx, context.TABLE_FORMAT),
                sort_key=sort_key,
            )
