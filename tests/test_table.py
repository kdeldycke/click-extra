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

from __future__ import annotations

import csv

import pytest
import tabulate
from extra_platforms import is_windows

from boltons.strutils import strip_ansi

from click_extra import (
    Color,
    TableFormat,
    echo,
    pass_context,
    style,
    table_format_option,
)
from click_extra.pytest import command_decorators
from click_extra.table import MARKUP_FORMATS


@pytest.mark.once
def test_table_formats_definition():
    """Check all table formats are accounted for and properly named."""
    # Formats from tabulate.
    tabulate_formats = [
        (f.upper(), f.replace("_", "-")) for f in tabulate._table_formats
    ]

    # Formats derived from CSV dialects.
    csv_dialects = [
        (f"CSV_{d.replace('-', '_').upper()}", f"csv-{d}") for d in csv.list_dialects()
    ]

    # Formats inherited from previous legacy cli-helpers dependency.
    cli_helpers_formats = [("CSV", "csv"), ("VERTICAL", "vertical")]

    table_formats = set((f.name, f.value) for f in TableFormat)

    # All tabulate formats are listed in our TableFormat enum.
    assert set(tabulate_formats) <= table_formats

    # All CSV variants are listed in our TableFormat enum.
    assert set(csv_dialects) <= table_formats

    # All legacy cli-helpers formats are listed in our TableFormat enum.
    assert set(cli_helpers_formats) <= table_formats

    # No duplicates.
    assert len(tabulate_formats) + len(csv_dialects) + len(cli_helpers_formats) == len(
        table_formats
    )
    assert (
        set(tabulate_formats) | set(csv_dialects) | set(cli_helpers_formats)
        == table_formats
    )

    # Sorted alphabetically by format name.
    assert list(f.name for f in TableFormat) == sorted(f.name for f in TableFormat)


@pytest.mark.parametrize(
    ("cmd_decorator", "cmd_type"),
    command_decorators(with_types=True),
)
def test_unrecognized_format(invoke, cmd_decorator, cmd_type):
    @cmd_decorator
    @table_format_option
    def table_cli():
        echo("It works!")

    result = invoke(table_cli, "--table-format", "random", color=False)
    assert not result.stdout

    group_help = " COMMAND [ARGS]..." if "group" in cmd_type else ""
    assert result.stderr == (
        f"Usage: table-cli [OPTIONS]{group_help}\n"
        "Try 'table-cli --help' for help.\n\n"
        "Error: Invalid value for '--table-format': 'random' is not one of "
        "'aligned', 'asciidoc', 'colon-grid', 'csv', 'csv-excel', 'csv-excel-tab', "
        "'csv-unix', 'double-grid', 'double-outline', 'fancy-grid', 'fancy-outline', 'github', "
        "'grid', 'heavy-grid', 'heavy-outline', 'html', 'jira', 'latex', "
        "'latex-booktabs', 'latex-longtable', 'latex-raw', 'mediawiki', 'mixed-grid', "
        "'mixed-outline', 'moinmoin', 'orgtbl', 'outline', 'pipe', 'plain', 'presto', "
        "'pretty', 'psql', 'rounded-grid', 'rounded-outline', 'rst', 'simple', "
        "'simple-grid', 'simple-outline', 'textile', 'tsv', 'unsafehtml', 'vertical', "
        "'youtrack'.\n"
    )

    assert result.exit_code == 2


aligned_table = """\
Day    Temperature
1      42.9
2
Friday Hot 🥵
"""

asciidoc_table = (
    '[cols="<8,<13",options="header"]\n'
    "|====\n"
    "| Day    | Temperature \n"
    "| 1      | 42.9        \n"
    "| 2      |             \n"
    "| Friday | Hot 🥵      \n"
    "|====\n"
)

colon_grid_table = """\
+--------+-------------+
| Day    | Temperature |
+:=======+:============+
| 1      | 42.9        |
+--------+-------------+
| 2      |             |
+--------+-------------+
| Friday | Hot 🥵      |
+--------+-------------+
"""

csv_table = """\
Day,Temperature\r
1,42.9\r
2,\r
Friday,Hot 🥵\r
"""

csv_excel_table = csv_table

csv_excel_tab_table = """\
Day\tTemperature\r
1\t42.9\r
2\t\r
Friday\tHot 🥵\r
"""

csv_unix_table = """\
"Day","Temperature"
"1","42.9"
"2",""
"Friday","Hot 🥵"
"""

double_grid_table = """\
╔════════╦═════════════╗
║ Day    ║ Temperature ║
╠════════╬═════════════╣
║ 1      ║ 42.9        ║
╠════════╬═════════════╣
║ 2      ║             ║
╠════════╬═════════════╣
║ Friday ║ Hot 🥵      ║
╚════════╩═════════════╝
"""

double_outline_table = """\
╔════════╦═════════════╗
║ Day    ║ Temperature ║
╠════════╬═════════════╣
║ 1      ║ 42.9        ║
║ 2      ║             ║
║ Friday ║ Hot 🥵      ║
╚════════╩═════════════╝
"""

fancy_grid_table = """\
╒════════╤═════════════╕
│ Day    │ Temperature │
╞════════╪═════════════╡
│ 1      │ 42.9        │
├────────┼─────────────┤
│ 2      │             │
├────────┼─────────────┤
│ Friday │ Hot 🥵      │
╘════════╧═════════════╛
"""

fancy_outline_table = """\
╒════════╤═════════════╕
│ Day    │ Temperature │
╞════════╪═════════════╡
│ 1      │ 42.9        │
│ 2      │             │
│ Friday │ Hot 🥵      │
╘════════╧═════════════╛
"""

github_table = """\
| Day    | Temperature |
|:-------|:------------|
| 1      | 42.9        |
| 2      |             |
| Friday | Hot 🥵      |
"""

grid_table = """\
+--------+-------------+
| Day    | Temperature |
+========+=============+
| 1      | 42.9        |
+--------+-------------+
| 2      |             |
+--------+-------------+
| Friday | Hot 🥵      |
+--------+-------------+
"""

heavy_grid_table = """\
┏━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Day    ┃ Temperature ┃
┣━━━━━━━━╋━━━━━━━━━━━━━┫
┃ 1      ┃ 42.9        ┃
┣━━━━━━━━╋━━━━━━━━━━━━━┫
┃ 2      ┃             ┃
┣━━━━━━━━╋━━━━━━━━━━━━━┫
┃ Friday ┃ Hot 🥵      ┃
┗━━━━━━━━┻━━━━━━━━━━━━━┛
"""

heavy_outline_table = """\
┏━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Day    ┃ Temperature ┃
┣━━━━━━━━╋━━━━━━━━━━━━━┫
┃ 1      ┃ 42.9        ┃
┃ 2      ┃             ┃
┃ Friday ┃ Hot 🥵      ┃
┗━━━━━━━━┻━━━━━━━━━━━━━┛
"""

html_table = """\
<table>
<thead>
<tr><th>Day   </th><th>Temperature</th></tr>
</thead>
<tbody>
<tr><td>1     </td><td>42.9       </td></tr>
<tr><td>2     </td><td>           </td></tr>
<tr><td>Friday</td><td>Hot 🥵     </td></tr>
</tbody>
</table>
"""

jira_table = """\
|| Day    || Temperature ||
| 1      | 42.9        |
| 2      |             |
| Friday | Hot 🥵      |
"""

latex_table = """\
\\begin{tabular}{ll}
\\hline
 Day    & Temperature \\\\
\\hline
 1      & 42.9        \\\\
 2      &             \\\\
 Friday & Hot 🥵      \\\\
\\hline
\\end{tabular}
"""

latex_booktabs_table = """\
\\begin{tabular}{ll}
\\toprule
 Day    & Temperature \\\\
\\midrule
 1      & 42.9        \\\\
 2      &             \\\\
 Friday & Hot 🥵      \\\\
\\bottomrule
\\end{tabular}
"""

latex_longtable_table = """\
\\begin{longtable}{ll}
\\hline
 Day    & Temperature \\\\
\\hline
\\endhead
 1      & 42.9        \\\\
 2      &             \\\\
 Friday & Hot 🥵      \\\\
\\hline
\\end{longtable}
"""

latex_raw_table = """\
\\begin{tabular}{ll}
\\hline
 Day    & Temperature \\\\
\\hline
 1      & 42.9        \\\\
 2      &             \\\\
 Friday & Hot 🥵      \\\\
\\hline
\\end{tabular}
"""

mediawiki_table = """\
{| class="wikitable" style="text-align: left;"
|+ <!-- caption -->
|-
! Day    !! Temperature
|-
| 1      || 42.9
|-
| 2      ||
|-
| Friday || Hot 🥵
|}
"""

mixed_grid_table = """\
┍━━━━━━━━┯━━━━━━━━━━━━━┑
│ Day    │ Temperature │
┝━━━━━━━━┿━━━━━━━━━━━━━┥
│ 1      │ 42.9        │
├────────┼─────────────┤
│ 2      │             │
├────────┼─────────────┤
│ Friday │ Hot 🥵      │
┕━━━━━━━━┷━━━━━━━━━━━━━┙
"""

mixed_outline_table = """\
┍━━━━━━━━┯━━━━━━━━━━━━━┑
│ Day    │ Temperature │
┝━━━━━━━━┿━━━━━━━━━━━━━┥
│ 1      │ 42.9        │
│ 2      │             │
│ Friday │ Hot 🥵      │
┕━━━━━━━━┷━━━━━━━━━━━━━┙
"""

moinmoin_table = """\
|| ''' Day    ''' || ''' Temperature ''' ||
||  1       ||  42.9         ||
||  2       ||               ||
||  Friday  ||  Hot 🥵       ||
"""

orgtbl_table = """\
| Day    | Temperature |
|--------+-------------|
| 1      | 42.9        |
| 2      |             |
| Friday | Hot 🥵      |
"""

outline_table = """\
+--------+-------------+
| Day    | Temperature |
+========+=============+
| 1      | 42.9        |
| 2      |             |
| Friday | Hot 🥵      |
+--------+-------------+
"""

pipe_table = """\
| Day    | Temperature |
|:-------|:------------|
| 1      | 42.9        |
| 2      |             |
| Friday | Hot 🥵      |
"""

plain_table = """\
Day     Temperature
1       42.9
2
Friday  Hot 🥵
"""

presto_table = """\
 Day    | Temperature
--------+-------------
 1      | 42.9
 2      |
 Friday | Hot 🥵
"""

pretty_table = """\
+--------+-------------+
|  Day   | Temperature |
+--------+-------------+
|   1    |    42.9     |
|   2    |             |
| Friday |   Hot 🥵    |
+--------+-------------+
"""

psql_table = """\
+--------+-------------+
| Day    | Temperature |
|--------+-------------|
| 1      | 42.9        |
| 2      |             |
| Friday | Hot 🥵      |
+--------+-------------+
"""

rounded_grid_table = """\
╭────────┬─────────────╮
│ Day    │ Temperature │
├────────┼─────────────┤
│ 1      │ 42.9        │
├────────┼─────────────┤
│ 2      │             │
├────────┼─────────────┤
│ Friday │ Hot 🥵      │
╰────────┴─────────────╯
"""

rounded_outline_table = """\
╭────────┬─────────────╮
│ Day    │ Temperature │
├────────┼─────────────┤
│ 1      │ 42.9        │
│ 2      │             │
│ Friday │ Hot 🥵      │
╰────────┴─────────────╯
"""

rst_table = """\
======  ===========
Day     Temperature
======  ===========
1       42.9
2
Friday  Hot 🥵
======  ===========
"""

simple_table = """\
Day     Temperature
------  -----------
1       42.9
2
Friday  Hot 🥵
"""

simple_grid_table = """\
┌────────┬─────────────┐
│ Day    │ Temperature │
├────────┼─────────────┤
│ 1      │ 42.9        │
├────────┼─────────────┤
│ 2      │             │
├────────┼─────────────┤
│ Friday │ Hot 🥵      │
└────────┴─────────────┘
"""

simple_outline_table = """\
┌────────┬─────────────┐
│ Day    │ Temperature │
├────────┼─────────────┤
│ 1      │ 42.9        │
│ 2      │             │
│ Friday │ Hot 🥵      │
└────────┴─────────────┘
"""

textile_table = """\
|_.  Day    |_. Temperature |
|<. 1       |<. 42.9        |
|<. 2       |<.             |
|<. Friday  |<. Hot 🥵      |
"""

tsv_table = "Day   \tTemperature\n1     \t42.9\n2\nFriday\tHot 🥵\n"

unsafehtml_table = """\
<table>
<thead>
<tr><th>Day   </th><th>Temperature</th></tr>
</thead>
<tbody>
<tr><td>1     </td><td>42.9       </td></tr>
<tr><td>2     </td><td>           </td></tr>
<tr><td>Friday</td><td>Hot 🥵     </td></tr>
</tbody>
</table>
"""

vertical_table = (
    "***************************[ 1. row ]***************************\n"
    "Day         | 1\n"
    "Temperature | 42.9\n"
    "***************************[ 2. row ]***************************\n"
    "Day         | 2\n"
    "Temperature | \n"
    "***************************[ 3. row ]***************************\n"
    "Day         | Friday\n"
    "Temperature | Hot 🥵\n"
)

youtrack_table = """\
||  Day     ||  Temperature  ||
|  1       |  42.9         |
|  2       |               |
|  Friday  |  Hot 🥵       |
"""

expected_renderings = {
    TableFormat.ALIGNED: aligned_table,
    TableFormat.ASCIIDOC: asciidoc_table,
    TableFormat.COLON_GRID: colon_grid_table,
    TableFormat.CSV: csv_table,
    TableFormat.CSV_EXCEL: csv_excel_table,
    TableFormat.CSV_EXCEL_TAB: csv_excel_tab_table,
    TableFormat.CSV_UNIX: csv_unix_table,
    TableFormat.DOUBLE_GRID: double_grid_table,
    TableFormat.DOUBLE_OUTLINE: double_outline_table,
    TableFormat.FANCY_GRID: fancy_grid_table,
    TableFormat.FANCY_OUTLINE: fancy_outline_table,
    TableFormat.GITHUB: github_table,
    TableFormat.GRID: grid_table,
    TableFormat.HEAVY_GRID: heavy_grid_table,
    TableFormat.HEAVY_OUTLINE: heavy_outline_table,
    TableFormat.HTML: html_table,
    TableFormat.JIRA: jira_table,
    TableFormat.LATEX: latex_table,
    TableFormat.LATEX_BOOKTABS: latex_booktabs_table,
    TableFormat.LATEX_LONGTABLE: latex_longtable_table,
    TableFormat.LATEX_RAW: latex_raw_table,
    TableFormat.MEDIAWIKI: mediawiki_table,
    TableFormat.MIXED_GRID: mixed_grid_table,
    TableFormat.MIXED_OUTLINE: mixed_outline_table,
    TableFormat.MOINMOIN: moinmoin_table,
    TableFormat.ORGTBL: orgtbl_table,
    TableFormat.OUTLINE: outline_table,
    TableFormat.PIPE: pipe_table,
    TableFormat.PLAIN: plain_table,
    TableFormat.PRESTO: presto_table,
    TableFormat.PRETTY: pretty_table,
    TableFormat.PSQL: psql_table,
    TableFormat.ROUNDED_GRID: rounded_grid_table,
    TableFormat.ROUNDED_OUTLINE: rounded_outline_table,
    TableFormat.RST: rst_table,
    TableFormat.SIMPLE: simple_table,
    TableFormat.SIMPLE_GRID: simple_grid_table,
    TableFormat.SIMPLE_OUTLINE: simple_outline_table,
    TableFormat.TEXTILE: textile_table,
    TableFormat.TSV: tsv_table,
    TableFormat.UNSAFEHTML: unsafehtml_table,
    TableFormat.VERTICAL: vertical_table,
    TableFormat.YOUTRACK: youtrack_table,
}


def test_all_table_formats_have_test_rendering():
    """Check all table formats have a rendering test fixture defined."""
    # Nothing missing or extra.
    assert len(TableFormat) == len(expected_renderings.keys())
    # Same order.
    assert list(TableFormat) == list(expected_renderings.keys())
    # Same content.
    assert set(TableFormat) == set(expected_renderings.keys())


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
@pytest.mark.parametrize(
    "option_decorator", (table_format_option, table_format_option())
)
@pytest.mark.parametrize(
    ("format_name", "expected"),
    (pytest.param(k, v, id=str(k)) for k, v in expected_renderings.items()),
)
def test_all_table_rendering(
    invoke, cmd_decorator, option_decorator, format_name, expected
):
    @cmd_decorator
    @option_decorator
    @pass_context
    def table_cli(ctx):
        format_id = ctx.meta["click_extra.table_format"]
        echo(f"Table format: {format_id}")

        headers = ("Day", "Temperature")
        data = (
            (1, 42.9),
            (2, None),
            (style("Friday", fg=Color.blue), style("Hot 🥵", fg=Color.red, bold=True)),
        )

        ctx.print_table(data, headers)

    result = invoke(table_cli, "--table-format", format_name, color=False)
    if not is_windows():
        expected = expected.replace("\r\n", "\n")
    assert result.stdout == f"Table format: {format_name}\n{expected}"
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "format_id",
    (pytest.param(f, id=str(f)) for f in MARKUP_FORMATS),
)
def test_markup_strips_ansi_by_default(invoke, format_id):
    """Markup formats strip ANSI codes when ``--color`` is not forced."""
    from click_extra import command

    @command
    @table_format_option
    @pass_context
    def table_cli(ctx):
        data = ((style("hello", fg=Color.red),),)
        ctx.print_table(data, headers=("greeting",))

    # color=True tells the CliRunner to preserve ANSI in captured output so we
    # can inspect what print_table actually wrote.
    result = invoke(table_cli, "--table-format", format_id, color=True)
    assert result.exit_code == 0
    assert result.stdout == strip_ansi(result.stdout)


@pytest.mark.parametrize(
    "format_id",
    (pytest.param(f, id=str(f)) for f in MARKUP_FORMATS),
)
def test_markup_preserves_ansi_with_color_flag(invoke, format_id):
    """``--color`` overrides ANSI stripping for markup formats."""
    from click_extra import command

    @command
    @table_format_option
    @pass_context
    def table_cli(ctx):
        data = ((style("hello", fg=Color.red),),)
        ctx.print_table(data, headers=("greeting",))

    result = invoke(
        table_cli, "--color", "--table-format", format_id, color=True
    )
    assert result.exit_code == 0
    assert result.stdout != strip_ansi(result.stdout)
