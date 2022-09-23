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
from gettext import gettext as _

import tabulate
from cli_helpers.tabular_output import TabularOutputFormatter, tabulate_adapter
from cli_helpers.tabular_output.output_formatter import MAX_FIELD_WIDTH
from click import Choice, echo, get_current_context
from cloup import option
from tabulate import DataRow, Line, TableFormat

from .parameters import ExtraOption
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


# Fix rendering of `None` values. We want an empty column instead of `<null>`.
for format_id in TabularOutputFormatter._output_formats:
    TabularOutputFormatter._output_formats[format_id].formatter_args[
        "missing_value"
    ] = ""


# Register all our new formats to cli-helper.
for tabulate_format in new_formats:
    TabularOutputFormatter.register_new_formatter(
        tabulate_format,
        tabulate_adapter.adapter,
        tabulate_adapter.get_preprocessors(tabulate_format),
        {
            "table_format": tabulate_format,
            "missing_value": "",
            "max_field_width": MAX_FIELD_WIDTH,
        },
    )


class TableFormatOption(ExtraOption):
    """A pre-configured option that is adding a ``-t``/``--table-format`` flag to select
    the rendering style of a table."""

    def cleanup_formatter(self):
        """Clean-up formatter attached to context."""
        ctx = get_current_context()
        if hasattr(ctx, "table_formatter"):
            delattr(ctx, "table_formatter")

    def print_table(self, table_formatter, *args, **kwargs):
        """Print table via echo."""
        for line in table_formatter.format_output(*args, **kwargs):
            if is_windows():
                line = line.encode("utf-8")
            echo(line)

    def init_formatter(self, ctx, param, value):
        """Initialize the table formatter and attach it to the context."""
        ctx.table_formatter = TabularOutputFormatter(format_name=value)
        ctx.print_table = partial(self.print_table, ctx.table_formatter)
        ctx.call_on_close(self.cleanup_formatter)

    def __init__(
        self,
        param_decls=None,
        type=Choice(
            sorted(TabularOutputFormatter._output_formats), case_sensitive=False
        ),
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
