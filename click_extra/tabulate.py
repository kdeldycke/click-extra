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

"""Extend cli_helpers.tabulate utilities with new formats."""

from __future__ import annotations

import csv
from functools import partial
from gettext import gettext as _
from io import StringIO

import tabulate
from click import Choice, echo
from cloup import option

from .parameters import ExtraOption

tabulate.MIN_PADDING = 0
"""Neutralize spurious double-spacing in table rendering."""


output_formats: list[str] = sorted(
    # Formats from tabulate.
    list(tabulate._table_formats)  # type: ignore[attr-defined]
    # Formats inherited from previous legacy cli-helpers dependency.
    + ["csv", "vertical"]
    # Formats derived from CSV dialects.
    + [f"csv-{d}" for d in csv.list_dialects()]
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


def render_csv(tabular_data, headers=(), **kwargs):
    with StringIO(newline="") as output:
        writer = csv.writer(output, **kwargs)
        writer.writerow(headers)
        writer.writerows(tabular_data)
        # Use print instead of echo to conserve CSV dialect's line termination,
        # avoid extra line returns and ANSI coloring.
        print(output.getvalue(), end="")


def render_vertical(tabular_data, headers=(), **kwargs):
    """Re-implements cli-helpers' vertical table layout.

    Source: https://github.com/dbcli/cli_helpers/blob/v2.3.0/cli_helpers/tabular_output/vertical_table_adapter.py
    """
    header_len = max(len(h) for h in headers)
    padded_headers = [h.ljust(header_len) for h in headers]

    for index, row in enumerate(tabular_data):
        # 27 has been hardcoded in cli-helpers:
        # https://github.com/dbcli/cli_helpers/blob/4e2c417f68bc07c72b508e107431569b0783c4ef/cli_helpers/tabular_output/vertical_table_adapter.py#L34
        echo(f"{'*' * 27}[ {index + 1}. row ]{'*' * 27}")
        for cell_label, cell_value in zip(padded_headers, row):
            echo(f"{cell_label} | {cell_value}")


def render_table(tabular_data, headers=(), **kwargs):
    """Render a table with tabulate and output it via echo."""
    defaults = {
        "disable_numparse": True,
        "numalign": None,
    }
    defaults.update(kwargs)
    echo(tabulate.tabulate(tabular_data, headers, **defaults))


class TableFormatOption(ExtraOption):
    """A pre-configured option that is adding a ``-t``/``--table-format`` flag to select
    the rendering style of a table."""

    def init_formatter(self, ctx, param, value):
        """Save table format ID in the context, and attach ``print_table()`` method to
        it.

        ``print_table(tabular_data, headers)`` is a ready-to-use method that takes a
        2-dimentional ``tabular_data`` iterable of iterables and a list of headers.
        """
        ctx.table_format = value

        render_func = None
        if value.startswith("csv"):
            render_func = partial(render_csv, dialect=get_csv_dialect(value))
        elif value == "vertical":
            render_func = render_vertical
        else:
            render_func = partial(render_table, tablefmt=value)
        ctx.print_table = render_func

    def __init__(
        self,
        param_decls=None,
        type=Choice(output_formats, case_sensitive=False),
        default="rounded_outline",
        expose_value=False,
        help=_("Rendering style of tables."),
        **kwargs,
    ):
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


table_format_option = partial(option, cls=TableFormatOption)
"""Decorator for ``TableFormatOption``."""
