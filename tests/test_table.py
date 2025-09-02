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

import pytest
import tabulate
from extra_platforms import is_windows

# We use vanilla click primitives here to demonstrate the full-compatibility.
from click_extra import echo, pass_context
from click_extra.decorators import table_format_option
from click_extra.pytest import command_decorators
from click_extra.table import TableFormat


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
    assert result.exit_code == 2
    assert not result.stdout

    group_help = " COMMAND [ARGS]..." if "group" in cmd_type else ""
    assert result.stderr == (
        f"Usage: table-cli [OPTIONS]{group_help}\n"
        "Try 'table-cli --help' for help.\n\n"
        "Error: Invalid value for '--table-format': 'random' is not one of "
        "'asciidoc', 'csv', 'csv-excel', 'csv-excel-tab', 'csv-unix', 'double-grid', "
        "'double-outline', 'fancy-grid', 'fancy-outline', 'github', 'grid', "
        "'heavy-grid', 'heavy-outline', 'html', 'jira', 'latex', 'latex-booktabs', "
        "'latex-longtable', 'latex-raw', 'mediawiki', 'mixed-grid', 'mixed-outline', "
        "'moinmoin', 'orgtbl', 'outline', 'pipe', 'plain', 'presto', 'pretty', "
        "'psql', 'rounded-grid', 'rounded-outline', 'rst', 'simple', 'simple-grid', "
        "'simple-outline', 'textile', 'tsv', 'unsafehtml', 'vertical', 'youtrack'.\n"
    )


asciidoc_table = (
    '[cols="5<,13<",options="header"]\n'
    "|====\n"
    "| day | temperature \n"
    "| 1   | 87          \n"
    "| 2   | 80          \n"
    "| 3   | 79          \n"
    "|====\n"
)

csv_table = """\
day,temperature\r
1,87\r
2,80\r
3,79\r
"""

csv_excel_table = csv_table

csv_excel_tab_table = """\
day\ttemperature\r
1\t87\r
2\t80\r
3\t79\r
"""

csv_unix_table = """\
"day","temperature"
"1","87"
"2","80"
"3","79"
"""

double_grid_table = """\
╔═════╦═════════════╗
║ day ║ temperature ║
╠═════╬═════════════╣
║ 1   ║ 87          ║
╠═════╬═════════════╣
║ 2   ║ 80          ║
╠═════╬═════════════╣
║ 3   ║ 79          ║
╚═════╩═════════════╝
"""

double_outline_table = """\
╔═════╦═════════════╗
║ day ║ temperature ║
╠═════╬═════════════╣
║ 1   ║ 87          ║
║ 2   ║ 80          ║
║ 3   ║ 79          ║
╚═════╩═════════════╝
"""

fancy_grid_table = """\
╒═════╤═════════════╕
│ day │ temperature │
╞═════╪═════════════╡
│ 1   │ 87          │
├─────┼─────────────┤
│ 2   │ 80          │
├─────┼─────────────┤
│ 3   │ 79          │
╘═════╧═════════════╛
"""

fancy_outline_table = """\
╒═════╤═════════════╕
│ day │ temperature │
╞═════╪═════════════╡
│ 1   │ 87          │
│ 2   │ 80          │
│ 3   │ 79          │
╘═════╧═════════════╛
"""

github_table = """\
| day | temperature |
| --- | ----------- |
| 1   | 87          |
| 2   | 80          |
| 3   | 79          |
"""

grid_table = """\
+-----+-------------+
| day | temperature |
+=====+=============+
| 1   | 87          |
+-----+-------------+
| 2   | 80          |
+-----+-------------+
| 3   | 79          |
+-----+-------------+
"""

heavy_grid_table = """\
┏━━━━━┳━━━━━━━━━━━━━┓
┃ day ┃ temperature ┃
┣━━━━━╋━━━━━━━━━━━━━┫
┃ 1   ┃ 87          ┃
┣━━━━━╋━━━━━━━━━━━━━┫
┃ 2   ┃ 80          ┃
┣━━━━━╋━━━━━━━━━━━━━┫
┃ 3   ┃ 79          ┃
┗━━━━━┻━━━━━━━━━━━━━┛
"""

heavy_outline_table = """\
┏━━━━━┳━━━━━━━━━━━━━┓
┃ day ┃ temperature ┃
┣━━━━━╋━━━━━━━━━━━━━┫
┃ 1   ┃ 87          ┃
┃ 2   ┃ 80          ┃
┃ 3   ┃ 79          ┃
┗━━━━━┻━━━━━━━━━━━━━┛
"""

html_table = """\
<table>
<thead>
<tr><th>day</th><th>temperature</th></tr>
</thead>
<tbody>
<tr><td>1  </td><td>87         </td></tr>
<tr><td>2  </td><td>80         </td></tr>
<tr><td>3  </td><td>79         </td></tr>
</tbody>
</table>
"""

jira_table = """\
|| day || temperature ||
| 1   | 87          |
| 2   | 80          |
| 3   | 79          |
"""

latex_table = """\
\\begin{tabular}{ll}
\\hline
 day & temperature \\\\
\\hline
 1   & 87          \\\\
 2   & 80          \\\\
 3   & 79          \\\\
\\hline
\\end{tabular}
"""

latex_booktabs_table = """\
\\begin{tabular}{ll}
\\toprule
 day & temperature \\\\
\\midrule
 1   & 87          \\\\
 2   & 80          \\\\
 3   & 79          \\\\
\\bottomrule
\\end{tabular}
"""

latex_longtable_table = """\
\\begin{longtable}{ll}
\\hline
 day & temperature \\\\
\\hline
\\endhead
 1   & 87          \\\\
 2   & 80          \\\\
 3   & 79          \\\\
\\hline
\\end{longtable}
"""

latex_raw_table = """\
\\begin{tabular}{ll}
\\hline
 day & temperature \\\\
\\hline
 1   & 87          \\\\
 2   & 80          \\\\
 3   & 79          \\\\
\\hline
\\end{tabular}
"""

mediawiki_table = """\
{| class="wikitable" style="text-align: left;"
|+ <!-- caption -->
|-
! day !! temperature
|-
| 1   || 87
|-
| 2   || 80
|-
| 3   || 79
|}
"""

mixed_grid_table = """\
┍━━━━━┯━━━━━━━━━━━━━┑
│ day │ temperature │
┝━━━━━┿━━━━━━━━━━━━━┥
│ 1   │ 87          │
├─────┼─────────────┤
│ 2   │ 80          │
├─────┼─────────────┤
│ 3   │ 79          │
┕━━━━━┷━━━━━━━━━━━━━┙
"""

mixed_outline_table = """\
┍━━━━━┯━━━━━━━━━━━━━┑
│ day │ temperature │
┝━━━━━┿━━━━━━━━━━━━━┥
│ 1   │ 87          │
│ 2   │ 80          │
│ 3   │ 79          │
┕━━━━━┷━━━━━━━━━━━━━┙
"""

moinmoin_table = """\
|| ''' day ''' || ''' temperature ''' ||
||  1    ||  87           ||
||  2    ||  80           ||
||  3    ||  79           ||
"""

orgtbl_table = """\
| day | temperature |
|-----+-------------|
| 1   | 87          |
| 2   | 80          |
| 3   | 79          |
"""

outline_table = """\
+-----+-------------+
| day | temperature |
+=====+=============+
| 1   | 87          |
| 2   | 80          |
| 3   | 79          |
+-----+-------------+
"""

pipe_table = """\
| day | temperature |
|:----|:------------|
| 1   | 87          |
| 2   | 80          |
| 3   | 79          |
"""

plain_table = """\
day  temperature
1    87
2    80
3    79
"""

presto_table = """\
 day | temperature
-----+-------------
 1   | 87
 2   | 80
 3   | 79
"""

pretty_table = """\
+-----+-------------+
| day | temperature |
+-----+-------------+
|  1  |     87      |
|  2  |     80      |
|  3  |     79      |
+-----+-------------+
"""

psql_table = """\
+-----+-------------+
| day | temperature |
|-----+-------------|
| 1   | 87          |
| 2   | 80          |
| 3   | 79          |
+-----+-------------+
"""

rounded_grid_table = """\
╭─────┬─────────────╮
│ day │ temperature │
├─────┼─────────────┤
│ 1   │ 87          │
├─────┼─────────────┤
│ 2   │ 80          │
├─────┼─────────────┤
│ 3   │ 79          │
╰─────┴─────────────╯
"""

rounded_outline_table = """\
╭─────┬─────────────╮
│ day │ temperature │
├─────┼─────────────┤
│ 1   │ 87          │
│ 2   │ 80          │
│ 3   │ 79          │
╰─────┴─────────────╯
"""

rst_table = """\
===  ===========
day  temperature
===  ===========
1    87
2    80
3    79
===  ===========
"""

simple_table = """\
day  temperature
---  -----------
1    87
2    80
3    79
"""

simple_grid_table = """\
┌─────┬─────────────┐
│ day │ temperature │
├─────┼─────────────┤
│ 1   │ 87          │
├─────┼─────────────┤
│ 2   │ 80          │
├─────┼─────────────┤
│ 3   │ 79          │
└─────┴─────────────┘
"""

simple_outline_table = """\
┌─────┬─────────────┐
│ day │ temperature │
├─────┼─────────────┤
│ 1   │ 87          │
│ 2   │ 80          │
│ 3   │ 79          │
└─────┴─────────────┘
"""

textile_table = """\
|_.  day |_. temperature |
|<. 1    |<. 87          |
|<. 2    |<. 80          |
|<. 3    |<. 79          |
"""

tsv_table = """\
day\ttemperature
1  \t87
2  \t80
3  \t79
"""

unsafehtml_table = """\
<table>
<thead>
<tr><th>day</th><th>temperature</th></tr>
</thead>
<tbody>
<tr><td>1  </td><td>87         </td></tr>
<tr><td>2  </td><td>80         </td></tr>
<tr><td>3  </td><td>79         </td></tr>
</tbody>
</table>
"""

youtrack_table = """\
||  day  ||  temperature  ||
|  1    |  87           |
|  2    |  80           |
|  3    |  79           |
"""

vertical_table = """\
***************************[ 1. row ]***************************
day         | 1
temperature | 87
***************************[ 2. row ]***************************
day         | 2
temperature | 80
***************************[ 3. row ]***************************
day         | 3
temperature | 79
"""


expected_renderings = {
    TableFormat.ASCIIDOC: asciidoc_table,
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
    TableFormat.YOUTRACK: youtrack_table,
    TableFormat.VERTICAL: vertical_table,
}


def test_recognized_modes():
    """Check all rendering modes proposed by the table module are accounted for and
    there is no duplicates."""
    assert set(tabulate._table_formats) <= set(
        i.value.replace("-", "_") for i in expected_renderings
    )
    assert set(tabulate._table_formats) <= set(
        i.value.replace("-", "_") for i in TableFormat
    )

    assert len(TableFormat) == len(expected_renderings.keys())
    assert set(TableFormat) == set(expected_renderings.keys())


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
@pytest.mark.parametrize(
    "option_decorator", (table_format_option, table_format_option())
)
@pytest.mark.parametrize(
    ("format_name", "expected"),
    (pytest.param(k, v, id=k) for k, v in expected_renderings.items()),
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

        data = ((1, 87), (2, 80), (3, 79))
        headers = ("day", "temperature")
        ctx.print_table(data, headers)

    result = invoke(table_cli, "--table-format", format_name)
    assert result.exit_code == 0
    if not is_windows():
        expected = expected.replace("\r\n", "\n")
    assert result.stdout == f"Table format: {format_name}\n{expected}"
    assert not result.stderr
