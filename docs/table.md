# {octicon}`table` Table

Click Extra provides a way to render tables in the terminal.

```{tip}
The selected `--table-format` value and the `--sort-by` priority list are published on `ctx.meta` as `TABLE_FORMAT` and `SORT_BY`. See the [available keys](context.md#available-keys) table to read them from your own callbacks.
```

Here how to use the standalone table rendering option decorator:

```{click:source}
:emphasize-lines: 5,14
import click
from click_extra import pass_context, table_format_option, style, Color

@click.command
@table_format_option
@pass_context
def table_command(ctx):
    headers = ("Day", "Temperature")
    data = (
        (1, 42.9),
        ("2", None),
        (style("Friday", fg=Color.blue), style("Hot 🥵", fg=Color.red, bold=True)),
    )
    ctx.print_table(data, headers)
```

As you can see above, this option registers a ready-to-use `print_table()` method to the context object.

The default help message for this option list all available table formats:

```{click:run}
:emphasize-lines: 5-6
result = invoke(table_command, args=["--help"])
assert "--table-format" in result.stdout
```

So you can use the `--table-format` option to change the table format:

```{click:run}
from textwrap import dedent

result = invoke(table_command, args=["--table-format", "fancy-outline"])
assert result.stdout == dedent("""\
    ╒════════╤═════════════╕
    │ Day    │ Temperature │
    ╞════════╪═════════════╡
    │ 1      │ 42.9        │
    │ 2      │             │
    │ \x1b[34mFriday\x1b[0m │ \x1b[31m\x1b[1mHot 🥵\x1b[0m      │
    ╘════════╧═════════════╛
    """)
```

```{click:run}
from textwrap import dedent

result = invoke(table_command, args=["--table-format", "asciidoc"])
assert result.stdout == (
    '[cols="<8,<13",options="header"]\n'
    '|====\n'
    '| Day    | Temperature \n'
    '| 1      | 42.9        \n'
    '| 2      |             \n'
    '| Friday | Hot 🥵      \n'
    '|====\n'
)
```

```{tip}
This example has been selected so you can see how `print_table()` handles:
- Mixed data types (integers, floats, `None`, strings)
- ANSI color codes (added with the `click_extra.style()` function)
- Unicode characters (like the emojis)
```

```{hint}
There's another method called `render_table()` that is registered in the context alongside `print_table()`.

It works the same way, but instead of printing the table to the console, it returns the rendered table as a string.
```

### Table formats

Table formats are aggregated from these sources:

- [`python-tabulate`](https://github.com/astanin/python-tabulate)
- [`cli-helpers`](https://github.com/dbcli/cli_helpers)
- Python's [`csv` module](https://docs.python.org/3/library/csv.html) from the standard library
- Python's [`json` module](https://docs.python.org/3/library/json.html) from the standard library
- [`hjson`](https://hjson.github.io) (requires the [`[hjson]` extra](install.md#extra-dependencies))
- [`tomlkit`](https://github.com/sdispater/tomlkit) (requires the [`[toml]` extra](install.md#extra-dependencies))
- [`xmltodict`](https://github.com/martinblech/xmltodict) (requires the [`[xml]` extra](install.md#extra-dependencies))
- [`PyYAML`](https://pyyaml.org) (requires the [`[yaml]` extra](install.md#extra-dependencies))

They're divided in 2 categories:

- Formats that produce **plain text** output (like ASCII tables, grid tables, etc.) and are often composed of Unicode box-drawing characters, to be displayed in a terminal.
- Formats that produce **markup language** output (like HTML, Markdown, LaTeX, etc.) and are expected to be rendered by a supporting viewer. This category also includes CSV, TSV, and structured serialization formats (HJSON, JSON, JSON5, JSONC, TOML, XML, YAML), which are plain text but meant to be processed by other tools.

| Format ID         | Description                                                                                                                                                                                                               | Implementation                               | Markup |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- | ------ |
| `aligned`         | Compact table with single-space column separators and no borders                                                                                                                                                          | Click Extra                                  | ❌     |
| `asciidoc`        | [AsciiDoc table](https://docs.asciidoctor.org/asciidoc/latest/tables/build-a-basic-table/)                                                                                                                                | `python-tabulate`                            | ✅     |
| `csv`             | [Comma-separated values](https://en.wikipedia.org/wiki/Comma-separated_values)                                                                                                                                            | `csv`                                        | ✅     |
| `csv-excel`       | CSV with [Excel dialect](https://docs.python.org/3/library/csv.html#csv.excel)                                                                                                                                            | `csv`                                        | ✅     |
| `csv-excel-tab`   | CSV with [Excel tab dialect](https://docs.python.org/3/library/csv.html#csv.excel_tab)                                                                                                                                    | `csv`                                        | ✅     |
| `csv-unix`        | CSV with [Unix dialect](https://docs.python.org/3/library/csv.html#csv.unix_dialect)                                                                                                                                      | `csv`                                        | ✅     |
| `double-grid`     | Double-line grid table                                                                                                                                                                                                    | `python-tabulate`                            | ❌     |
| `double-outline`  | Double-line outline table                                                                                                                                                                                                 | `python-tabulate`                            | ❌     |
| `fancy-grid`      | Grid with Unicode box-drawing characters                                                                                                                                                                                  | `python-tabulate`                            | ❌     |
| `fancy-outline`   | Outline with Unicode box-drawing characters                                                                                                                                                                               | `python-tabulate`                            | ❌     |
| `github`          | [GitHub-flavored Markdown table](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/organizing-information-with-tables)                                                            | `python-tabulate`                            | ✅     |
| `grid`            | Grid table with ASCII characters, also supported by [Pandoc](https://pandoc.org/MANUAL.html#extension-grid_tables) and [reStructuredText](https://docutils.sourceforge.io/docs/ref/rst/restructuredtext.html#grid-tables) | `python-tabulate`                            | ❌     |
| `heavy-grid`      | Heavy-line grid table                                                                                                                                                                                                     | `python-tabulate`                            | ❌     |
| `heavy-outline`   | Heavy-line outline table                                                                                                                                                                                                  | `python-tabulate`                            | ❌     |
| `hjson`           | [HJSON](https://hjson.github.io) array of objects                                                                                                                                                                         | [`hjson`](install.md#extra-dependencies)     | ✅     |
| `html`            | [HTML table](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/table)                                                                                                                                             | `python-tabulate`                            | ✅     |
| `jira`            | [Jira-style markup](https://confluence.atlassian.com/doc/confluence-wiki-markup-251003035.html#ConfluenceWikiMarkup-Tables)                                                                                               | `python-tabulate`                            | ✅     |
| `json`            | [JSON](https://www.json.org) array of objects                                                                                                                                                                             | `json`                                       | ✅     |
| `json5`           | Alias for `json` ([JSON5](https://json5.org) is a superset of JSON)                                                                                                                                                       | `json`                                       | ✅     |
| `jsonc`           | Alias for `json` ([JSONC](https://code.visualstudio.com/docs/languages/json#_json-with-comments) is JSON with comments)                                                                                                   | `json`                                       | ✅     |
| `latex`           | [LaTeX table](https://en.wikibooks.org/wiki/LaTeX/Tables)                                                                                                                                                                 | `python-tabulate`                            | ✅     |
| `latex-booktabs`  | [LaTeX table with booktabs package](https://ctan.org/pkg/booktabs)                                                                                                                                                        | `python-tabulate`                            | ✅     |
| `latex-longtable` | [LaTeX longtable environment](https://ctan.org/pkg/longtable)                                                                                                                                                             | `python-tabulate`                            | ✅     |
| `latex-raw`       | [LaTeX table](https://en.wikibooks.org/wiki/LaTeX/Tables) without escaping                                                                                                                                                | `python-tabulate`                            | ✅     |
| `mediawiki`       | [MediaWiki markup](https://en.wikipedia.org/wiki/Help:Table)                                                                                                                                                              | `python-tabulate`                            | ✅     |
| `mixed-grid`      | Mixed-line grid table                                                                                                                                                                                                     | `python-tabulate`                            | ❌     |
| `mixed-outline`   | Mixed-line outline table                                                                                                                                                                                                  | `python-tabulate`                            | ❌     |
| `moinmoin`        | [MoinMoin wiki markup](https://moinmo.in/HelpOnTables)                                                                                                                                                                    | `python-tabulate`                            | ✅     |
| `orgtbl`          | [Emacs org-mode table](https://orgmode.org/manual/Tables.html)                                                                                                                                                            | `python-tabulate`                            | ✅     |
| `outline`         | Simple outline table                                                                                                                                                                                                      | `python-tabulate`                            | ❌     |
| `pipe`            | [PHP Markdown Extra pipes](https://michelf.ca/projects/php-markdown/extra/#table), also [supported by Pandoc](https://pandoc.org/MANUAL.html#extension-pipe_tables)                                                       | `python-tabulate`                            | ✅     |
| `plain`           | Plain text, no formatting                                                                                                                                                                                                 | `python-tabulate`                            | ❌     |
| `presto`          | Presto SQL output style                                                                                                                                                                                                   | `python-tabulate`                            | ❌     |
| `pretty`          | Pretty ASCII table                                                                                                                                                                                                        | `python-tabulate`                            | ❌     |
| `psql`            | PostgreSQL output style                                                                                                                                                                                                   | `python-tabulate`                            | ❌     |
| `rounded-grid`    | Rounded grid table                                                                                                                                                                                                        | `python-tabulate`                            | ❌     |
| `rounded-outline` | Rounded outline table                                                                                                                                                                                                     | `python-tabulate`                            | ❌     |
| `rst`             | [reStructuredText simple table](https://docutils.sourceforge.io/docs/ref/rst/restructuredtext.html#simple-tables)                                                                                                         | `python-tabulate`                            | ✅     |
| `simple`          | Simple table with spaces, also [supported by Pandoc](https://pandoc.org/MANUAL.html#extension-simple_tables)                                                                                                              | `python-tabulate`                            | ❌     |
| `simple-grid`     | Simple grid table                                                                                                                                                                                                         | `python-tabulate`                            | ❌     |
| `simple-outline`  | Simple outline table                                                                                                                                                                                                      | `python-tabulate`                            | ❌     |
| `textile`         | [Textile markup](https://textile-lang.com/doc/tables)                                                                                                                                                                     | `python-tabulate`                            | ✅     |
| `toml`            | [TOML](https://toml.io) array of tables                                                                                                                                                                                   | [`tomlkit`](install.md#extra-dependencies)   | ✅     |
| `tsv`             | [Tab-separated values](https://en.wikipedia.org/wiki/Tab-separated_values)                                                                                                                                                | `python-tabulate`                            | ✅     |
| `unsafehtml`      | [HTML table](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/table) without escaping                                                                                                                            | `python-tabulate`                            | ✅     |
| `vertical`        | Vertical table layout                                                                                                                                                                                                     | `cli-helpers`                                | ❌     |
| `xml`             | [XML](https://www.w3.org/XML/) document                                                                                                                                                                                   | [`xmltodict`](install.md#extra-dependencies) | ✅     |
| `yaml`            | [YAML](https://yaml.org) sequence of mappings                                                                                                                                                                             | [`PyYAML`](install.md#extra-dependencies)    | ✅     |
| `youtrack`        | [YouTrack markup](https://www.jetbrains.com/help/youtrack/server/youtrack-markdown-syntax-issues.html#tables)                                                                                                             | `python-tabulate`                            | ✅     |

```{attention}
By default, markup formats strip ANSI color codes from the output, to avoid injecting escape sequences into structured content like HTML, LaTeX, or CSV.

If you want to keep them, force the `--color` option when invoking the command.
```

````{tip}
Use the built-in demo subcommands to verify how ANSI codes are handled by each format:

```shell-session
$ uvx click-extra --table-format github styles
$ uvx click-extra --table-format json colors
```

Plain-text formats preserve ANSI styling. Markup formats strip it unless `--color` is passed explicitly.
````

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "aligned"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "asciidoc"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "csv"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "csv-excel"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "csv-excel-tab"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "csv-unix"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "double-grid"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "double-outline"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "fancy-grid"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "fancy-outline"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "github"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "grid"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "heavy-grid"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "heavy-outline"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "hjson"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "html"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "jira"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "json"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "json5"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "jsonc"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "latex"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "latex-booktabs"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "latex-longtable"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "latex-raw"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "mediawiki"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "mixed-grid"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "mixed-outline"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "moinmoin"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "orgtbl"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "outline"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "pipe"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "plain"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "presto"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "pretty"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "psql"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "rounded-grid"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "rounded-outline"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "rst"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "simple"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "simple-grid"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "simple-outline"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "textile"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "toml"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "tsv"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "unsafehtml"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "vertical"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "xml"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "yaml"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "youtrack"])
```

### Get table format

You can get the ID of the current table format from the context:

```{click:source}
:emphasize-lines: 8-9
import click
from click_extra import echo, pass_context, table_format_option

@click.command
@table_format_option
@pass_context
def vanilla_command(ctx):
    format_id = ctx.meta["click_extra.table_format"]
    echo(f"Table format: {format_id}")

    data = ((1, 87), (2, 80), (3, 79))
    headers = ("day", "temperature")
    ctx.print_table(data, headers)
```

```{click:run}
:emphasize-lines: 2
result = invoke(vanilla_command, args=["--table-format", "fancy-outline"])
assert "Table format: fancy-outline" in result.stdout
```

### Data serialization

`print_data()` and `serialize_data()` handle arbitrary data structures (nested dicts, lists, scalars), unlike `print_table()` which expects tabular rows and headers. They support the structured serialization formats: JSON, HJSON, YAML, TOML, and XML.

```{click:source}
from click_extra import command, pass_context, table_format_option
from click_extra.table import print_data

@command
@table_format_option
@pass_context
def data_command(ctx):
    """Serialize nested data."""
    data = {
        "city": "Paris",
        "population": 2161000,
        "landmarks": ["Eiffel Tower", "Louvre", "Notre-Dame"],
    }
    table_format = ctx.meta["click_extra.table_format"]
    print_data(data, table_format)
```

```{click:run}
result = invoke(data_command, args=["--table-format", "json"])
assert result.exit_code == 0
assert '"city": "Paris"' in result.stdout
```

```{click:run}
result = invoke(data_command, args=["--table-format", "yaml"])
assert result.exit_code == 0
assert "city: Paris" in result.stdout
```

`serialize_data()` returns the serialized string instead of printing it:

```{click:run}
from click_extra.table import serialize_data, TableFormat

output = serialize_data({"city": "Paris", "population": 2161000}, TableFormat.JSON)
assert '"city": "Paris"' in output
print(output, end="")
```

### Sorted tables

`SortByOption` adds a `--sort-by` CLI option whose choices are derived from column definitions. Column definitions are `(label, column_id)` tuples. Columns with `column_id=None` are displayed but not offered as sort choices.

The option can be repeated to define a multi-column sort priority: `--sort-by name --sort-by age` sorts by name first, then breaks ties by age.

When active, `SortByOption` replaces `ctx.print_table` with a sorted variant, so the command body doesn't need any sorting logic.

```{click:source}
from click_extra import command, pass_context, table_format_option
from click_extra.table import SortByOption

sort_opt = SortByOption(
    ("Fruit", "fruit"),
    ("Count", "count"),
    ("Notes", None),
)

@command(params=[sort_opt])
@table_format_option
@pass_context
def inventory(ctx):
    """Sortable fruit inventory."""
    header_defs = (("Fruit", "fruit"), ("Count", "count"), ("Notes", None))
    data = [
        ["Cherry", "50", "seasonal"],
        ["Apple", "120", ""],
        ["Banana", "80", "organic"],
    ]
    ctx.print_table(header_defs, data)
```

```{click:run}
result = invoke(inventory, args=["--help"])
assert "--sort-by" in result.stdout
assert "fruit" in result.stdout
assert result.exit_code == 0
```

```{click:run}
result = invoke(inventory, args=["--table-format", "rounded-outline", "--sort-by", "fruit"])
assert result.exit_code == 0
assert result.stdout.index("Apple") < result.stdout.index("Banana")
```

```{click:run}
result = invoke(inventory, args=["--table-format", "rounded-outline", "--sort-by", "count"])
assert result.exit_code == 0
assert result.stdout.index("Apple") < result.stdout.index("Cherry")
```

Repeating `--sort-by` sets multi-column priority. Here, rows are sorted by count first, then ties broken by fruit name:

```{click:run}
result = invoke(inventory, args=["--table-format", "rounded-outline", "--sort-by", "count", "--sort-by", "fruit"])
assert result.exit_code == 0
assert result.stdout.index("Apple") < result.stdout.index("Cherry")
```

For programmatic use without a CLI option, `render_table()` accepts a `sort_key` callable:

```{click:source}
from click_extra import command, echo
from click_extra.table import render_table, TableFormat

@command
def sorted_demo():
    """Render a table sorted alphabetically."""
    data = [["Cherry", "50"], ["Apple", "120"], ["Banana", "80"]]
    output = render_table(
        data,
        headers=["Fruit", "Count"],
        table_format=TableFormat.ROUNDED_OUTLINE,
        sort_key=lambda row: row[0],
    )
    echo(output)
```

```{click:run}
result = invoke(sorted_demo)
assert result.exit_code == 0
assert result.stdout.index("Apple") < result.stdout.index("Cherry")
```

## `click_extra.table` API

```{eval-rst}
.. autoclasstree:: click_extra.table
   :strict:

.. automodule:: click_extra.table
   :members:
   :undoc-members:
   :show-inheritance:
```
