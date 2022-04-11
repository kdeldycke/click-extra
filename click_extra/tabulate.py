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

from functools import partial

import click
import tabulate
from cli_helpers.tabular_output import TabularOutputFormatter, tabulate_adapter
from cli_helpers.tabular_output.output_formatter import MAX_FIELD_WIDTH, MISSING_VALUE
from cloup import GroupedOption
from tabulate import DataRow, Line, TableFormat

from .platform import is_windows

new_formats = {
    "simple_grid": TableFormat(
        lineabove=Line("┌", "─", "┬", "┐"),
        linebelowheader=Line("├", "─", "┼", "┤"),
        linebetweenrows=Line("├", "─", "┼", "┤"),
        linebelow=Line("└", "─", "┴", "┘"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "rounded_grid": TableFormat(
        lineabove=Line("╭", "─", "┬", "╮"),
        linebelowheader=Line("├", "─", "┼", "┤"),
        linebetweenrows=Line("├", "─", "┼", "┤"),
        linebelow=Line("╰", "─", "┴", "╯"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "double_grid": TableFormat(
        lineabove=Line("╔", "═", "╦", "╗"),
        linebelowheader=Line("╠", "═", "╬", "╣"),
        linebetweenrows=Line("╠", "═", "╬", "╣"),
        linebelow=Line("╚", "═", "╩", "╝"),
        headerrow=DataRow("║", "║", "║"),
        datarow=DataRow("║", "║", "║"),
        padding=1,
        with_header_hide=None,
    ),
    "outline": TableFormat(
        lineabove=Line("+", "-", "+", "+"),
        linebelowheader=Line("+", "=", "+", "+"),
        linebetweenrows=None,
        linebelow=Line("+", "-", "+", "+"),
        headerrow=DataRow("|", "|", "|"),
        datarow=DataRow("|", "|", "|"),
        padding=1,
        with_header_hide=None,
    ),
    "simple_outline": TableFormat(
        lineabove=Line("┌", "─", "┬", "┐"),
        linebelowheader=Line("├", "─", "┼", "┤"),
        linebetweenrows=None,
        linebelow=Line("└", "─", "┴", "┘"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "rounded_outline": TableFormat(
        lineabove=Line("╭", "─", "┬", "╮"),
        linebelowheader=Line("├", "─", "┼", "┤"),
        linebetweenrows=None,
        linebelow=Line("╰", "─", "┴", "╯"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "double_outline": TableFormat(
        lineabove=Line("╔", "═", "╦", "╗"),
        linebelowheader=Line("╠", "═", "╬", "╣"),
        linebetweenrows=None,
        linebelow=Line("╚", "═", "╩", "╝"),
        headerrow=DataRow("║", "║", "║"),
        datarow=DataRow("║", "║", "║"),
        padding=1,
        with_header_hide=None,
    ),
}


# Update tabulate with our new formats, some supporting multi-line rendering.
tabulate._table_formats.update(new_formats)
tabulate.multiline_formats.update(
    {
        "simple_grid": "simple_grid",
        "rounded_grid": "rounded_grid",
        "double_grid": "double_grid",
    }
)


# Remove duplicate formats:
#   * `ascii ` => `outline`
#   * `double` => `double_outline`
#   * `psql_unicode` => `simple_outline`
# See: https://github.com/dbcli/cli_helpers/issues/79
for tabulate_format in ("ascii", "double", "psql_unicode"):
    del TabularOutputFormatter._output_formats[tabulate_format]


# Register all our new formats to cli-helper.
for tabulate_format in new_formats:
    TabularOutputFormatter.register_new_formatter(
        tabulate_format,
        tabulate_adapter.adapter,
        tabulate_adapter.get_preprocessors(tabulate_format),
        {
            "table_format": tabulate_format,
            "missing_value": MISSING_VALUE,
            "max_field_width": MAX_FIELD_WIDTH,
        },
    )


def cleanup_formatter():
    """Clean-up formatter attached to context."""
    ctx = click.get_current_context()
    del ctx.table_formatter


def print_table(table_formatter, *args, **kwargs):
    for line in table_formatter.format_output(*args, **kwargs):
        if is_windows():
            line = line.encode("utf-8")
        click.echo(line)


def init_formatter(ctx, param, value):
    """Initialize the table formatter and attach it to the context."""
    ctx.table_formatter = TabularOutputFormatter(format_name=value)
    ctx.print_table = partial(print_table, ctx.table_formatter)
    ctx.call_on_close(cleanup_formatter)


def table_format_option(
    *names,
    type=click.Choice(
        sorted(TabularOutputFormatter._output_formats), case_sensitive=False
    ),
    default="rounded_outline",
    expose_value=False,
    callback=init_formatter,
    help="Rendering style of tables.",
    cls=GroupedOption,
    **kwargs,
):
    """A ready to use option decorator that is adding a ``-t/--table-format``
    option flag to select the rendering style of a table."""
    if not names:
        names = ("-t", "--table-format")
    return click.option(
        *names,
        type=type,
        default=default,
        expose_value=expose_value,
        callback=callback,
        help=help,
        cls=cls,
        **kwargs,
    )
