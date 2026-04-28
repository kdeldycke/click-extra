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
import json
from pathlib import PurePosixPath

import hjson
import pytest
import tabulate
import tomlkit
import xmltodict
import yaml
from boltons.strutils import strip_ansi
from extra_platforms import is_windows
from tabulate import tabulate_formats

# tabulate 0.10 introduced the ``colon_grid`` format and changed the asciidoc
# cell-alignment marker from ``8<`` to ``<8``. Older releases (still shipped
# by some distributions) need a different fixture.
TABULATE_HAS_COLON_GRID = "colon_grid" in tabulate_formats

from click_extra import (
    Color,
    command,
    echo,
    pass_context,
    style,
    table_format_option,
)
from click_extra.pytest import command_decorators
from click_extra.table import (
    SERIALIZATION_FORMATS,
    SortByOption,
    TableFormat,
    _apply_default,
    _column_sort_key,
    _strip_none,
    print_data,
    print_sorted_table,
    print_table,
    render_table,
    serialize_data,
)


@pytest.mark.once
def test_table_formats_definition():
    """Check all table formats are accounted for and properly named."""
    # Formats from tabulate.
    tabulate_formats = [
        (f.upper(), f.replace("_", "-"))
        for f in tabulate._table_formats  # type: ignore[attr-defined]
    ]

    # Formats derived from CSV dialects.
    csv_dialects = [
        (f"CSV_{d.replace('-', '_').upper()}", f"csv-{d}") for d in csv.list_dialects()
    ]

    # Formats inherited from previous legacy cli-helpers dependency.
    cli_helpers_formats = [("CSV", "csv"), ("VERTICAL", "vertical")]

    # Structured data serialization formats.
    serialization_formats = [
        ("HJSON", "hjson"),
        ("JSON", "json"),
        ("JSON5", "json5"),
        ("JSONC", "jsonc"),
        ("TOML", "toml"),
        ("XML", "xml"),
        ("YAML", "yaml"),
    ]

    table_formats = {(f.name, f.value) for f in TableFormat}

    # All tabulate formats are listed in our TableFormat enum.
    assert set(tabulate_formats) <= table_formats

    # All CSV variants are listed in our TableFormat enum.
    assert set(csv_dialects) <= table_formats

    # All legacy cli-helpers formats are listed in our TableFormat enum.
    assert set(cli_helpers_formats) <= table_formats

    # All serialization formats are listed in our TableFormat enum.
    assert set(serialization_formats) <= table_formats

    # No duplicates.
    all_formats = (
        set(tabulate_formats)
        | set(csv_dialects)
        | set(cli_helpers_formats)
        | set(serialization_formats)
    )
    assert len(all_formats) == len(table_formats)
    assert all_formats == table_formats

    # Sorted alphabetically by format name.
    assert [f.name for f in TableFormat] == sorted(f.name for f in TableFormat)


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
        "'grid', 'heavy-grid', 'heavy-outline', 'hjson', 'html', 'jira', 'json', 'json5', 'jsonc', 'latex', "
        "'latex-booktabs', 'latex-longtable', 'latex-raw', 'mediawiki', 'mixed-grid', "
        "'mixed-outline', 'moinmoin', 'orgtbl', 'outline', 'pipe', 'plain', 'presto', "
        "'pretty', 'psql', 'rounded-grid', 'rounded-outline', 'rst', 'simple', "
        "'simple-grid', 'simple-outline', 'textile', 'toml', 'tsv', 'unsafehtml', 'vertical', 'xml', 'yaml', "
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
    f'[cols="{"<8,<13" if TABULATE_HAS_COLON_GRID else "8<,13<"}",options="header"]\n'
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
| :----- | :---------- |
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

hjson_table = """\
[
  {
    Day: 1
    Temperature: 42.9
  }
  {
    Day: 2
    Temperature: null
  }
  {
    Day: Friday
    Temperature: Hot 🥵
  }
]
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

json_table = """\
[
  {
    "Day": 1,
    "Temperature": 42.9
  },
  {
    "Day": 2,
    "Temperature": null
  },
  {
    "Day": "Friday",
    "Temperature": "Hot 🥵"
  }
]
"""

json5_table = json_table

jsonc_table = json_table

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
| :----- | :---------- |
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

toml_table = """\
[[record]]
Day = 1
Temperature = 42.9

[[record]]
Day = 2

[[record]]
Day = "Friday"
Temperature = "Hot 🥵"
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

xml_table = """\
<records>
\t<record>
\t\t<Day>1</Day>
\t\t<Temperature>42.9</Temperature>
\t</record>
\t<record>
\t\t<Day>2</Day>
\t</record>
\t<record>
\t\t<Day>Friday</Day>
\t\t<Temperature>Hot 🥵</Temperature>
\t</record>
</records>
"""

yaml_table = """\
- Day: 1
  Temperature: 42.9
- Day: 2
  Temperature: null
- Day: Friday
  Temperature: Hot 🥵
"""

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
    TableFormat.HJSON: hjson_table,
    TableFormat.HTML: html_table,
    TableFormat.JIRA: jira_table,
    TableFormat.JSON: json_table,
    TableFormat.JSON5: json5_table,
    TableFormat.JSONC: jsonc_table,
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
    TableFormat.TOML: toml_table,
    TableFormat.TSV: tsv_table,
    TableFormat.UNSAFEHTML: unsafehtml_table,
    TableFormat.VERTICAL: vertical_table,
    TableFormat.XML: xml_table,
    TableFormat.YAML: yaml_table,
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


def _table_format_marks(format_name):
    """Skip ``colon_grid`` when tabulate <0.10 aliases it to ``grid``."""
    if format_name is TableFormat.COLON_GRID and not TABULATE_HAS_COLON_GRID:
        return (
            pytest.mark.skip(reason="colon_grid is aliased to grid on tabulate <0.10"),
        )
    return ()


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
@pytest.mark.parametrize(
    "option_decorator", (table_format_option, table_format_option())
)
@pytest.mark.parametrize(
    ("format_name", "expected"),
    (
        pytest.param(k, v, id=str(k), marks=_table_format_marks(k))
        for k, v in expected_renderings.items()
    ),
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
    (pytest.param(f, id=str(f)) for f in TableFormat if f.is_markup),
)
def test_markup_strips_ansi_by_default(invoke, format_id):
    """Markup formats strip ANSI codes when ``--color`` is not forced."""

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
    (
        pytest.param(f, id=str(f))
        for f in TableFormat
        if f.is_markup and f not in SERIALIZATION_FORMATS
    ),
)
def test_markup_preserves_ansi_with_color_flag(invoke, format_id):
    """``--color`` overrides ANSI stripping for markup formats."""

    @command
    @table_format_option
    @pass_context
    def table_cli(ctx):
        data = ((style("hello", fg=Color.red),),)
        ctx.print_table(data, headers=("greeting",))

    result = invoke(table_cli, "--color", "--table-format", format_id, color=True)
    assert result.exit_code == 0
    assert result.stdout != strip_ansi(result.stdout)


@pytest.mark.parametrize(
    ("table_format", "data"),
    (
        pytest.param(TableFormat.JSON, {"a": {"b": [1, 2, 3]}}, id="json"),
        pytest.param(TableFormat.JSON5, {"key": "value"}, id="json5"),
        pytest.param(TableFormat.JSONC, [1, 2, 3], id="jsonc"),
    ),
)
def test_serialize_json_compatible(table_format, data):
    result = serialize_data(data, table_format)
    assert json.loads(result) == data


@pytest.mark.parametrize(
    ("table_format", "data", "loader"),
    (
        pytest.param(
            TableFormat.HJSON,
            {"name": "test", "count": 42},
            hjson.loads,
            id="hjson",
        ),
        pytest.param(
            TableFormat.TOML,
            {"section": {"key": "value"}},
            tomlkit.loads,
            id="toml",
        ),
        pytest.param(
            TableFormat.YAML,
            {"managers": {"brew": {"version": "4.0"}}},
            yaml.safe_load,
            id="yaml",
        ),
    ),
)
def test_serialize_roundtrip(table_format, data, loader):
    result = serialize_data(data, table_format)
    assert loader(result) == data


def test_serialize_toml_list_wrapping():
    """Top-level lists are wrapped under a ``record`` key for TOML."""
    data = [{"id": "a"}, {"id": "b"}]
    result = serialize_data(data, TableFormat.TOML)
    parsed = tomlkit.loads(result)
    assert parsed == {"record": data}


@pytest.mark.parametrize(
    "table_format",
    (
        pytest.param(TableFormat.TOML, id="toml"),
        pytest.param(TableFormat.XML, id="xml"),
    ),
)
def test_serialize_strips_none(table_format):
    """TOML and XML have no null type. ``None`` values are omitted."""
    data = {"present": "yes", "absent": None}
    result = serialize_data(data, table_format)
    assert "absent" not in result


def test_serialize_xml():
    data = {"item": {"name": "test"}}
    result = serialize_data(data, TableFormat.XML)
    parsed = xmltodict.parse(f"<root>{result}</root>")
    assert parsed["root"]["records"]["item"]["name"] == "test"


def test_serialize_xml_list_wrapping():
    """Top-level lists are wrapped under a ``record`` key for XML."""
    data = [{"id": "a"}, {"id": "b"}]
    result = serialize_data(data, TableFormat.XML)
    parsed = xmltodict.parse(f"<root>{result}</root>")
    records = parsed["root"]["records"]["record"]
    assert len(records) == 2
    assert records[0]["id"] == "a"


def test_serialize_xml_custom_root_element():
    data = {"key": "value"}
    result = serialize_data(data, TableFormat.XML, root_element="mpm")
    assert "<mpm>" in result


def test_serialize_default_callback():
    """Custom types are converted via the ``default`` callback."""
    data = {"path": PurePosixPath("/usr/bin"), "name": "test"}
    result = serialize_data(
        data,
        TableFormat.JSON,
        default=lambda obj: str(obj) if isinstance(obj, PurePosixPath) else obj,
    )
    parsed = json.loads(result)
    assert parsed == {"path": "/usr/bin", "name": "test"}


def test_serialize_unsupported_format_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        serialize_data({"a": 1}, TableFormat.PLAIN)


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        pytest.param({"a": 1, "b": None}, {"a": 1}, id="flat-dict"),
        pytest.param(
            {"a": {"b": None, "c": 2}, "d": [{"e": None, "f": 3}]},
            {"a": {"c": 2}, "d": [{"f": 3}]},
            id="nested",
        ),
        pytest.param("hello", "hello", id="passthrough-string"),
        pytest.param(42, 42, id="passthrough-int"),
    ),
)
def test_strip_none(data, expected):
    assert _strip_none(data) == expected


def test_apply_default_native_types_unchanged():
    data = {"s": "a", "i": 1, "f": 1.5, "b": True, "n": None}
    assert _apply_default(data, lambda x: x) == data


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        pytest.param({"p": PurePosixPath("/tmp")}, {"p": "/tmp"}, id="dict"),
        pytest.param(
            [PurePosixPath("/a"), [PurePosixPath("/b")]],
            ["/a", ["/b"]],
            id="nested-lists",
        ),
    ),
)
def test_apply_default_custom_type_converted(data, expected):
    result = _apply_default(data, lambda obj: str(obj))
    assert result == expected


@pytest.mark.parametrize(
    ("func", "args", "kwargs", "match"),
    (
        pytest.param(
            print_data,
            ({"a": 1}, TableFormat.YAML),
            {},
            "pip install click-extra",
            id="print-data-default-package",
        ),
        pytest.param(
            print_data,
            ({"a": 1}, TableFormat.YAML),
            {"package": "my-project"},
            "pip install my-project",
            id="print-data-custom-package",
        ),
        pytest.param(
            print_table,
            ([["a"]], ["col"], TableFormat.YAML),
            {},
            "pip install click-extra",
            id="print-table",
        ),
    ),
)
def test_missing_dependency_clean_error(monkeypatch, func, args, kwargs, match):
    """Missing optional dependency produces a clean error, no traceback."""
    monkeypatch.setitem(__import__("sys").modules, "yaml", None)
    with pytest.raises(SystemExit, match=match):
        func(*args, **kwargs)


@pytest.mark.parametrize(
    ("data", "headers", "sort_key", "expected_fruits"),
    (
        pytest.param(
            [["banana", "3"], ["apple", "1"], ["cherry", "2"]],
            ["Fruit", "Count"],
            lambda row: row[0],
            ["apple", "banana", "cherry"],
            id="with-sort-key",
        ),
        pytest.param(
            [["banana"], ["apple"]],
            ["Fruit"],
            None,
            ["banana", "apple"],
            id="preserves-original-order",
        ),
    ),
)
def test_render_table_sort(data, headers, sort_key, expected_fruits):
    result = render_table(
        data,
        headers=headers,
        table_format=TableFormat.JSON,
        sort_key=sort_key,
    )
    parsed = json.loads(result)
    assert [r["Fruit"] for r in parsed] == expected_fruits


@pytest.mark.parametrize(
    ("headers", "data", "expected"),
    (
        pytest.param(
            ["Name", "Name"],
            [["Alice", "Bob"]],
            [{"Name": "Bob"}],
            id="duplicate-header-names-last-wins",
        ),
        pytest.param(
            ["", "Value"],
            [["key", "val"]],
            [{"": "key", "Value": "val"}],
            id="empty-header-name",
        ),
        pytest.param(
            ["\x1b[31mRed\x1b[0m", "Plain"],
            [["\x1b[32mgreen\x1b[0m", "text"]],
            [{"\x1b[31mRed\x1b[0m": "\x1b[32mgreen\x1b[0m", "Plain": "text"}],
            id="ansi-in-headers-and-cells",
        ),
        pytest.param(
            ["🎯 Target", "📊 Score"],
            [["alpha", "100"]],
            [{"🎯 Target": "alpha", "📊 Score": "100"}],
            id="emoji-in-headers",
        ),
    ),
)
def test_render_table_header_edge_cases(headers, data, expected):
    """Edge cases for header handling in structured format rendering."""
    result = render_table(data, headers=headers, table_format=TableFormat.JSON)
    assert json.loads(result) == expected


@pytest.mark.parametrize(
    ("header_defs", "rows", "sort_columns", "cell_key", "expected_first_col"),
    (
        pytest.param(
            [("Name", "name"), ("Age", "age"), ("City", None)],
            [["Bob", "30", "NYC"], ["Alice", "25", "LA"], ["Charlie", "25", "SF"]],
            ("age",),
            None,
            ["Alice", "Charlie", "Bob"],
            id="primary-sort",
        ),
        pytest.param(
            [("Name", "name"), ("Age", "age")],
            [["Bob", "25"], ["Alice", "30"]],
            None,
            None,
            ["Alice", "Bob"],
            id="default-order",
        ),
        pytest.param(
            [("Name", "name"), ("Count", "count")],
            [["a", "10"], ["b", "2"], ["c", "1"]],
            ("count",),
            lambda v: (0, int(v)) if v and v.isdigit() else (1, v or ""),
            ["c", "b", "a"],
            id="custom-cell-key",
        ),
        pytest.param(
            [("First", "name"), ("Last", "name")],
            [["Bob", "Smith"], ["Alice", "Jones"]],
            ("name",),
            None,
            ["Alice", "Bob"],
            id="duplicate-keys-last-index-wins",
        ),
        pytest.param(
            [("Name", ""), ("Age", "age")],
            [["Bob", "25"], ["Alice", "30"]],
            ("",),
            None,
            ["Alice", "Bob"],
            id="empty-key-falls-back-to-default",
        ),
        pytest.param(
            [("Name", "name")],
            [["\x1b[31mBob\x1b[0m"], ["\x1b[32mAlice\x1b[0m"]],
            ("name",),
            None,
            ["\x1b[32mAlice\x1b[0m", "\x1b[31mBob\x1b[0m"],
            id="ansi-stripped-for-sort",
        ),
        pytest.param(
            [("Fruit", "fruit")],
            [["🍒 cherry"], ["🍌 banana"], ["🍎 apple"]],
            ("fruit",),
            None,
            ["🍌 banana", "🍎 apple", "🍒 cherry"],
            id="emoji-in-cells",
        ),
        pytest.param(
            [("City", "city"), ("Name", "name"), ("Age", "age")],
            [
                ["NYC", "Alice", "30"],
                ["LA", "Bob", "25"],
                ["SF", "Alice", "25"],
            ],
            ("name", "age"),
            None,
            ["SF", "NYC", "LA"],
            id="multi-column-priority",
        ),
    ),
)
def test_column_sort_key(header_defs, rows, sort_columns, cell_key, expected_first_col):
    key = _column_sort_key(header_defs, sort_columns, cell_key)
    result = sorted(rows, key=key)
    assert [r[0] for r in result] == expected_first_col


def test_print_sorted_table_empty_rows(capsys):
    """Empty table produces no output."""
    print_sorted_table(
        header_defs=[("Name", "name")],
        table_data=[],
        sort_columns=("name",),
        table_format=TableFormat.PLAIN,
    )
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("header_defs", "expected_choices", "expected_default"),
    (
        pytest.param(
            (("Name", "name"), ("Age", "age"), ("Notes", None)),
            ["name", "age"],
            ("name",),
            id="none-key-excluded",
        ),
        pytest.param(
            (("ID", "id"), ("Label", "label")),
            ["id", "label"],
            ("id",),
            id="first-sortable-as-default",
        ),
        pytest.param(
            (("First", "name"), ("Last", "name"), ("Age", "age")),
            ["name", "name", "age"],
            ("name",),
            id="duplicate-keys",
        ),
        pytest.param(
            (("Notes", ""), ("Name", "name")),
            ["name"],
            ("name",),
            id="empty-key-excluded",
        ),
    ),
)
def test_sort_by_option_choices_and_default(
    header_defs, expected_choices, expected_default
):
    """SortByOption choices and default are derived from column definitions."""
    opt = SortByOption(*header_defs)
    assert list(opt.type.choices) == expected_choices  # type: ignore[attr-defined]
    assert opt.default == expected_default


def test_sort_by_option_wires_context(invoke):
    """SortByOption replaces ctx.print_table with the sorted variant."""
    sort_opt = SortByOption(("Fruit", "fruit"), ("Count", "count"))

    @command(params=[sort_opt])
    @table_format_option
    @pass_context
    def cli(ctx):
        header_defs = (("Fruit", "fruit"), ("Count", "count"))
        data = [["banana", "3"], ["apple", "1"], ["cherry", "2"]]
        ctx.print_table(header_defs, data)

    result = invoke(cli, "--table-format", "json", "--sort-by", "fruit", color=False)
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert [r["Fruit"] for r in parsed] == ["apple", "banana", "cherry"]


def test_sort_by_option_multi_column(invoke):
    """Multiple --sort-by options define sort priority."""
    sort_opt = SortByOption(
        ("City", "city"),
        ("Name", "name"),
        ("Age", "age"),
    )

    @command(params=[sort_opt])
    @table_format_option
    @pass_context
    def cli(ctx):
        header_defs = (("City", "city"), ("Name", "name"), ("Age", "age"))
        data = [
            ["NYC", "Alice", "30"],
            ["LA", "Bob", "25"],
            ["SF", "Alice", "25"],
        ]
        ctx.print_table(header_defs, data)

    result = invoke(
        cli,
        "--table-format",
        "json",
        "--sort-by",
        "name",
        "--sort-by",
        "age",
        color=False,
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert [r["City"] for r in parsed] == ["SF", "NYC", "LA"]
