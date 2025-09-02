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
"""Collection of table rendering utilities."""

from __future__ import annotations

import csv
import logging
from enum import StrEnum
from functools import partial
from gettext import gettext as _
from io import StringIO
from typing import Sequence

import tabulate
from tabulate import DataRow, Line, TableFormat

from . import Choice, Context, Parameter, echo
from .parameters import ExtraOption

tabulate.MIN_PADDING = 0
"""Neutralize spurious double-spacing in table rendering."""


tabulate._table_formats.update(  # type: ignore[attr-defined]
    {
        "github": TableFormat(
            lineabove=Line("| ", "-", " | ", " |"),
            linebelowheader=Line("| ", "-", " | ", " |"),
            linebetweenrows=None,
            linebelow=None,
            headerrow=DataRow("| ", " | ", " |"),
            datarow=DataRow("| ", " | ", " |"),
            padding=0,
            with_header_hide=["lineabove"],
        ),
    },
)
"""Tweak table separators to match MyST and GFM syntax.

I.e. add a space between the column separator and the dashes filling a cell:

``|---|---|---|`` → ``| --- | --- | --- |``

That way we produce a table that doesn't need any supplement linting.

This has been proposed upstream at `python-tabulate#261
<https://github.com/astanin/python-tabulate/pull/261>`_.
"""

_output_formats: frozenset[str] = frozenset(
    # Formats from tabulate.
    list(tabulate._table_formats)  # type: ignore[attr-defined]
    # Formats inherited from previous legacy cli-helpers dependency.
    + ["csv", "vertical"]
    # Formats derived from CSV dialects.
    + [f"csv-{d}" for d in csv.list_dialects()]
)
"""Collection of raw IDs for supported table formats."""


TableFormat = StrEnum(
    "TableFormat",
    {
        fmt.replace("-", "_").upper(): fmt.replace("_", "-").lower()
        for fmt in sorted(_output_formats)
    },
)
"""Enumeration of supported table formats."""


def _get_csv_dialect(table_format: TableFormat | None = None) -> str:
    """Extract, validate and normalize CSV dialect ID from format.

    Defaults to ``excel`` rendering, like in Python's csv module.
    """
    dialect = "excel"

    # Extract dialect ID from table format, if any.
    if table_format:
        format_id = table_format.value
        assert format_id.startswith("csv")
        parts = format_id.split("-", 1)
        assert parts[0] == "csv"
        if len(parts) > 1:
            dialect = parts[1]

    csv.get_dialect(dialect)  # Validate dialect.
    return dialect


def _render_csv(
    table_data: Sequence[Sequence[str]],
    headers: Sequence[str] | None = None,
    table_format: TableFormat | None = None,
    **kwargs,
) -> str:
    """Render a table in CSV format.

    .. note::
        StringIO is used to capture CSV output in memory. `Hard-coded to default to
        UTF-8 <https://github.com/python/cpython/blob/9291095/Lib/_pyio.py#L2652>`_.
    """
    defaults = {"dialect": _get_csv_dialect(table_format)}
    defaults.update(kwargs)

    with StringIO(newline="") as output:
        writer = csv.writer(output, **defaults)
        if headers:
            writer.writerow(headers)
        writer.writerows(table_data)
        return output.getvalue()


def _render_vertical(
    table_data: Sequence[Sequence[str]],
    headers: Sequence[str] | None = None,
    sep_character: str = "*",
    sep_length: int = 27,
    **kwargs,
) -> str:
    """Re-implements ``cli-helpers``'s vertical table layout.

    .. note::
        See `cli-helpers source code for reference
        <https://github.com/dbcli/cli_helpers/blob/v2.7.0/cli_helpers/tabular_output/vertical_table_adapter.py>`_.

    .. caution::
        This layout is `hard-coded to 27 asterisks to separate rows
        <https://github.com/dbcli/cli_helpers/blob/c34ae9f/cli_helpers/tabular_output/vertical_table_adapter.py#L34>`_,
        as in the original implementation.
    """
    if not headers:
        headers = []
    header_len = max(len(h) for h in headers)
    padded_headers = [h.ljust(header_len) for h in headers]

    table_lines = []
    sep = sep_character * sep_length
    for index, row in enumerate(table_data):
        table_lines.append(f"{sep}[ {index + 1}. row ]{sep}")
        for cell_label, cell_value in zip(padded_headers, row):
            table_lines.append(f"{cell_label} | {cell_value}")
    return "\n".join(table_lines)


def _render_tabulate(
    table_data: Sequence[Sequence[str]],
    headers: Sequence[str] | None = None,
    table_format: TableFormat | None = None,
    **kwargs,
) -> str:
    """Render a table with ``tabulate``.

    Default format is ``TableFormat.ROUNDED_OUTLINE``.
    """
    if not headers:
        headers = ()
    if not table_format:
        table_format = TableFormat.ROUNDED_OUTLINE
    defaults = {
        "disable_numparse": True,
        "numalign": None,
        # tabulate()'s  format ID uses underscores instead of dashes.
        "tablefmt": table_format.value.replace("-", "_"),
    }
    defaults.update(kwargs)
    return tabulate.tabulate(table_data, headers, **defaults)  # type: ignore[arg-type]


def _select_table_funcs(
    table_format: TableFormat | None = None,
) -> tuple[callable, callable]:
    """Returns the rendering and print functions for the given ``table_format``."""
    print_func = echo
    match table_format:
        case (
            TableFormat.CSV
            | TableFormat.CSV_EXCEL
            | TableFormat.CSV_EXCEL_TAB
            | TableFormat.CSV_UNIX
        ):
            # Use print instead of echo to conserve CSV dialect's line termination,
            # avoid extra line returns and keep ANSI coloring.
            print_func = partial(print, end="")
            return partial(_render_csv, table_format=table_format), print_func  # type: ignore[assignment]
        case TableFormat.VERTICAL:
            return _render_vertical, print_func  # type: ignore[assignment]
        case _:
            return partial(_render_tabulate, table_format=table_format), print_func


def render_table(
    table_data: Sequence[Sequence[str]],
    headers: Sequence[str] | None = None,
    table_format: TableFormat | None = None,
    **kwargs,
) -> str:
    """Render a table and return it as a string."""
    render_func, _ = _select_table_funcs(table_format)
    return render_func(table_data, headers, **kwargs)


def print_table(
    table_data: Sequence[Sequence[str]],
    headers: Sequence[str] | None = None,
    table_format: TableFormat | None = None,
    **kwargs,
) -> None:
    """Render a table and print it to the console."""
    render_func, print_func = _select_table_funcs(table_format)
    return print_func(render_func(table_data, headers, **kwargs))


class TableFormatOption(ExtraOption):
    """A pre-configured option that is adding a ``--table-format`` flag to select
    the rendering style of a table.

    The selected table format ID is made available in the context in
    ``ctx.meta["click_extra.table_format"]``.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        # Click choices do not use the enum member values, but their names.
        type=Choice(tuple(i.value for i in TableFormat), case_sensitive=False),
        default=TableFormat.ROUNDED_OUTLINE.value,
        expose_value=False,
        help=_("Rendering style of tables."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--table-format",)

        kwargs.setdefault("callback", self.init_formatter)

        super().__init__(
            param_decls=param_decls,
            type=type,
            default=default,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )

    def init_formatter(
        self,
        ctx: Context,
        param: Parameter,
        value: str | TableFormat | None,
    ) -> None:
        """Save table format in the context, and adds ``print_table()`` to it.

        The ``print_table(table_data, headers, **kwargs)`` method added to the context
        is a ready-to-use helper that takes for parameters:

        - ``table_data``: a 2-dimensional iterable of iterables for rows and cells
          values,
        - ``headers``: a list of string to be used as column headers,
        - ``**kwargs``: any extra keyword argument supported by the underlying
          table rendering function.

        The rendering style of the table is normalized to one of the supported
        ``TableFormat`` enum.
        """
        table_format = None
        if isinstance(value, TableFormat):
            table_format = value
        elif value:
            format_id = value.lower().replace("_", "-")
            if value != format_id:
                logging.warning(
                    f"Table format ID normalized from {value!r} to {format_id!r}. "
                    f"Please update your CLI usage before {value!r} is deprecated.",
                )
            for fmt in TableFormat:
                if fmt.value == format_id:
                    table_format = fmt
                    break

        ctx.meta["click_extra.table_format"] = table_format
        ctx.print_table = partial(print_table, table_format=table_format)  # type: ignore[attr-defined]
