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


output_formats: list[str] = sorted(
    # Formats from tabulate.
    list(tabulate._table_formats)  # type: ignore[attr-defined]
    # Formats inherited from previous legacy cli-helpers dependency.
    + ["csv", "vertical"]
    # Formats derived from CSV dialects.
    + [f"csv-{d}" for d in csv.list_dialects()],
)
"""All output formats supported by click-extra."""


def get_csv_dialect(format_id: str) -> str | None:
    """Extract, validate and normalize CSV dialect ID from format."""
    assert format_id.startswith("csv")
    # Defaults to excel rendering, like in Python's csv module.
    dialect = "excel"
    parts = format_id.split("-", 1)
    assert parts[0] == "csv"
    if len(parts) > 1:
        dialect = parts[1]
    return dialect


def render_csv(
    tabular_data: Sequence[Sequence[str]],
    headers: Sequence[str] = (),
    **kwargs,
) -> None:
    with StringIO(newline="") as output:
        writer = csv.writer(output, **kwargs)
        writer.writerow(headers)
        writer.writerows(tabular_data)
        # Use print instead of echo to conserve CSV dialect's line termination,
        # avoid extra line returns and ANSI coloring.
        print(output.getvalue(), end="")


def render_vertical(
    tabular_data: Sequence[Sequence[str]],
    headers: Sequence[str] = (),
    **kwargs,
) -> None:
    """Re-implements ``cli-helpers``'s vertical table layout.

    See `cli-helpers source for reference
    <https://github.com/dbcli/cli_helpers/blob/v2.3.0/cli_helpers/tabular_output/vertical_table_adapter.py>`_.
    """
    header_len = max(len(h) for h in headers)
    padded_headers = [h.ljust(header_len) for h in headers]

    for index, row in enumerate(tabular_data):
        # 27 has been hardcoded in cli-helpers:
        # https://github.com/dbcli/cli_helpers/blob/4e2c417/cli_helpers/tabular_output/vertical_table_adapter.py#L34
        echo(f"{'*' * 27}[ {index + 1}. row ]{'*' * 27}")
        for cell_label, cell_value in zip(padded_headers, row):
            echo(f"{cell_label} | {cell_value}")


def render_table(
    tabular_data: Sequence[Sequence[str]],
    headers: Sequence[str] = (),
    **kwargs,
) -> None:
    """Render a table with tabulate and output it via echo."""
    defaults = {
        "disable_numparse": True,
        "numalign": None,
    }
    defaults.update(kwargs)
    echo(tabulate.tabulate(tabular_data, headers, **defaults))  # type: ignore[arg-type]


class TableFormatOption(ExtraOption):
    """A pre-configured option that is adding a ``-t``/``--table-format`` flag to select
    the rendering style of a table.

    The selected table format ID is made available in the context in
    ``ctx.meta["click_extra.table_format"]``.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        type=Choice(output_formats, case_sensitive=False),
        default="rounded_outline",
        expose_value=False,
        help=_("Rendering style of tables."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("-t", "--table-format")

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
        value: str,
    ) -> None:
        """Save table format ID in the context, and adds ``print_table()`` to it.

        The ``print_table(tabular_data, headers)`` method added to the context is a
        ready-to-use helper that takes for parameters:
        - ``tabular_data``, a 2-dimensional iterable of iterables for cell values,
        - ``headers``, a list of string to be used as headers.
        """
        ctx.meta["click_extra.table_format"] = value

        render_func = None
        if value.startswith("csv"):
            render_func = partial(render_csv, dialect=get_csv_dialect(value))
        elif value == "vertical":
            render_func = render_vertical  # type: ignore[assignment]
        else:
            render_func = partial(render_table, tablefmt=value)

        ctx.print_table = render_func  # type: ignore[attr-defined]
