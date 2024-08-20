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
from pytest_cases import fixture, parametrize

# We use vanilla click primitives here to demonstrate the full-compatibility.
from click_extra import echo, pass_context
from click_extra.decorators import table_format_option
from click_extra.pytest import command_decorators
from click_extra.tabulate import output_formats


@pytest.mark.parametrize(
    ("cmd_decorator", "cmd_type"),
    command_decorators(with_types=True),
)
def test_unrecognized_format(invoke, cmd_decorator, cmd_type):
    @cmd_decorator
    @table_format_option
    def tabulate_cli1():
        echo("It works!")

    result = invoke(tabulate_cli1, "--table-format", "random", color=False)
    assert result.exit_code == 2
    assert not result.stdout

    group_help = " COMMAND [ARGS]..." if "group" in cmd_type else ""
    extra_suggest = (
        "Try 'tabulate-cli1 --help' for help.\n" if "extra" not in cmd_type else ""
    )
    assert result.stderr == (
        f"Usage: tabulate-cli1 [OPTIONS]{group_help}\n"
        f"{extra_suggest}\n"
        "Error: Invalid value for '-t' / '--table-format': 'random' is not one of "
        "'asciidoc', 'csv', 'csv-excel', 'csv-excel-tab', 'csv-unix', 'double_grid', "
        "'double_outline', 'fancy_grid', 'fancy_outline', 'github', 'grid', "
        "'heavy_grid', 'heavy_outline', 'html', 'jira', 'latex', 'latex_booktabs', "
        "'latex_longtable', 'latex_raw', 'mediawiki', 'mixed_grid', 'mixed_outline', "
        "'moinmoin', 'orgtbl', 'outline', 'pipe', 'plain', 'presto', 'pretty', "
        "'psql', 'rounded_grid', 'rounded_outline', 'rst', 'simple', 'simple_grid', "
        "'simple_outline', 'textile', 'tsv', 'unsafehtml', 'vertical', 'youtrack'.\n"
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
    "asciidoc": asciidoc_table,
    "csv": csv_table,
    "csv-excel": csv_excel_table,
    "csv-excel-tab": csv_excel_tab_table,
    "csv-unix": csv_unix_table,
    "double_grid": double_grid_table,
    "double_outline": double_outline_table,
    "fancy_grid": fancy_grid_table,
    "fancy_outline": fancy_outline_table,
    "github": github_table,
    "grid": grid_table,
    "heavy_grid": heavy_grid_table,
    "heavy_outline": heavy_outline_table,
    "html": html_table,
    "jira": jira_table,
    "latex": latex_table,
    "latex_booktabs": latex_booktabs_table,
    "latex_longtable": latex_longtable_table,
    "latex_raw": latex_raw_table,
    "mediawiki": mediawiki_table,
    "mixed_grid": mixed_grid_table,
    "mixed_outline": mixed_outline_table,
    "moinmoin": moinmoin_table,
    "orgtbl": orgtbl_table,
    "outline": outline_table,
    "pipe": pipe_table,
    "plain": plain_table,
    "presto": presto_table,
    "pretty": pretty_table,
    "psql": psql_table,
    "rounded_grid": rounded_grid_table,
    "rounded_outline": rounded_outline_table,
    "rst": rst_table,
    "simple": simple_table,
    "simple_grid": simple_grid_table,
    "simple_outline": simple_outline_table,
    "textile": textile_table,
    "tsv": tsv_table,
    "unsafehtml": unsafehtml_table,
    "youtrack": youtrack_table,
    "vertical": vertical_table,
}


def test_recognized_modes():
    """Check all rendering modes proposed by the table module are accounted for and
    there is no duplicates."""
    assert set(tabulate._table_formats) <= expected_renderings.keys()
    assert set(tabulate._table_formats) <= set(output_formats)

    assert len(output_formats) == len(expected_renderings.keys())
    assert set(output_formats) == set(expected_renderings.keys())


@fixture
@parametrize("cmd_decorator", command_decorators(no_groups=True))
@parametrize("option_decorator", (table_format_option, table_format_option()))
def table_cli(cmd_decorator, option_decorator):
    @cmd_decorator
    @option_decorator
    @pass_context
    def tabulate_cli2(ctx):
        format_id = ctx.meta["click_extra.table_format"]
        echo(f"Table format: {format_id}")

        data = ((1, 87), (2, 80), (3, 79))
        headers = ("day", "temperature")
        ctx.print_table(data, headers)

    return tabulate_cli2


@pytest.mark.parametrize(
    ("format_name", "expected"),
    (pytest.param(k, v, id=k) for k, v in expected_renderings.items()),
)
def test_all_table_rendering(invoke, table_cli, format_name, expected):
    result = invoke(table_cli, "--table-format", format_name)
    assert result.exit_code == 0
    if not is_windows():
        expected = expected.replace("\r\n", "\n")
    assert result.stdout == f"Table format: {format_name}\n{expected}"
    assert not result.stderr
