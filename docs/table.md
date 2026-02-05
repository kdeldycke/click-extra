# {octicon}`table` Table

Click Extra provides a way to render tables in the terminal.

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
    '[cols="8<,13<",options="header"]\n'
    '|====\n'
    '| Day    | Temperature \n'
    '| 1      | 42.9        \n'
    '| 2      |             \n'
    '| \x1b[34mFriday\x1b[0m | \x1b[31m\x1b[1mHot 🥵\x1b[0m      \n'
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

Table formats are aggregated from 3 sources:
- [`python-tabulate`](https://github.com/astanin/python-tabulate)
- [`cli-helpers`](https://github.com/dbcli/cli_helpers)
- Python's [`csv` module](https://docs.python.org/3/library/csv.html) from the standard library

They're divided in 2 categories:
- Formats that produce **plain text** output (like ASCII tables, grid tables, etc.) and are often composed of Unicode box-drawing characters, to be displayed in a terminal.
- Formats that produce **markup language** output (like HTML, Markdown, LaTeX, etc.) and are expected to be rendered by a supporting viewer. This category also includes CSV and TSV formats, which are plain text but meant to be processed by other tools.

| Format ID | Description | Implementation | Markup |
|--------|-------------|--------|----------------|
| `aligned` | Compact table with single-space column separators and no borders | Click Extra | ❌ |
| `asciidoc` | [AsciiDoc table](https://docs.asciidoctor.org/asciidoc/latest/tables/build-a-basic-table/) | `python-tabulate` | ✅ |
| `csv` | [Comma-separated values](https://en.wikipedia.org/wiki/Comma-separated_values) | `csv`| ✅ |
| `csv-excel` | CSV with [Excel dialect](https://docs.python.org/3/library/csv.html#csv.excel) | `csv`| ✅ |
| `csv-excel-tab` | CSV with [Excel tab dialect](https://docs.python.org/3/library/csv.html#csv.excel_tab) | `csv`| ✅ |
| `csv-unix` | CSV with [Unix dialect](https://docs.python.org/3/library/csv.html#csv.unix_dialect) | `csv`| ✅ |
| `double-grid` | Double-line grid table | `python-tabulate` | ❌ |
| `double-outline` | Double-line outline table | `python-tabulate` | ❌ |
| `fancy-grid` | Grid with Unicode box-drawing characters | `python-tabulate` | ❌ |
| `fancy-outline` | Outline with Unicode box-drawing characters | `python-tabulate` | ❌ |
| `github` | [GitHub-flavored Markdown table](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/organizing-information-with-tables) | `python-tabulate` | ✅ |
| `grid` | Grid table with ASCII characters, also supported by [Pandoc](https://pandoc.org/MANUAL.html#extension-grid_tables) and [reStructuredText](https://docutils.sourceforge.io/docs/ref/rst/restructuredtext.html#grid-tables) | `python-tabulate` | ❌ |
| `heavy-grid` | Heavy-line grid table | `python-tabulate` | ❌ |
| `heavy-outline` | Heavy-line outline table | `python-tabulate` | ❌ |
| `html` | [HTML table](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/table) | `python-tabulate` | ✅ |
| `jira` | [Jira-style markup](https://confluence.atlassian.com/doc/confluence-wiki-markup-251003035.html#ConfluenceWikiMarkup-Tables) | `python-tabulate` | ✅ |
| `latex` | [LaTeX table](https://en.wikibooks.org/wiki/LaTeX/Tables) | `python-tabulate` | ✅ |
| `latex-booktabs` | [LaTeX table with booktabs package](https://ctan.org/pkg/booktabs) | `python-tabulate` | ✅ |
| `latex-longtable` | [LaTeX longtable environment](https://ctan.org/pkg/longtable) | `python-tabulate` | ✅ |
| `latex-raw` | [LaTeX table](https://en.wikibooks.org/wiki/LaTeX/Tables) without escaping | `python-tabulate` | ✅ |
| `mediawiki` | [MediaWiki markup](https://en.wikipedia.org/wiki/Help:Table) | `python-tabulate` | ✅ |
| `mixed-grid` | Mixed-line grid table | `python-tabulate` | ❌ |
| `mixed-outline` | Mixed-line outline table | `python-tabulate` | ❌ |
| `moinmoin` | [MoinMoin wiki markup](https://moinmo.in/HelpOnTables) | `python-tabulate` | ✅ |
| `orgtbl` | [Emacs org-mode table](https://orgmode.org/manual/Tables.html) | `python-tabulate` | ✅ |
| `outline` | Simple outline table | `python-tabulate` | ❌ |
| `pipe` | [PHP Markdown Extra pipes](https://michelf.ca/projects/php-markdown/extra/#table), also [supported by Pandoc](https://pandoc.org/MANUAL.html#extension-pipe_tables) | `python-tabulate` | ✅ |
| `plain` | Plain text, no formatting | `python-tabulate` | ❌ |
| `presto` | Presto SQL output style | `python-tabulate` | ❌ |
| `pretty` | Pretty ASCII table | `python-tabulate` | ❌ |
| `psql` | PostgreSQL output style | `python-tabulate` | ❌ |
| `rounded-grid` | Rounded grid table | `python-tabulate` | ❌ |
| `rounded-outline` | Rounded outline table | `python-tabulate` | ❌ |
| `rst` | [reStructuredText simple table](https://docutils.sourceforge.io/docs/ref/rst/restructuredtext.html#simple-tables) | `python-tabulate` | ✅ |
| `simple` | Simple table with spaces, also [supported by Pandoc](https://pandoc.org/MANUAL.html#extension-simple_tables) | `python-tabulate` | ❌ |
| `simple-grid` | Simple grid table | `python-tabulate` | ❌ |
| `simple-outline` | Simple outline table | `python-tabulate` | ❌ |
| `textile` | [Textile markup](https://textile-lang.com/doc/tables) | `python-tabulate` | ✅ |
| `tsv` | [Tab-separated values](https://en.wikipedia.org/wiki/Tab-separated_values) | `python-tabulate` | ✅ |
| `unsafehtml` | [HTML table](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/table) without escaping | `python-tabulate` | ✅ |
| `vertical` | Vertical table layout | `cli-helpers` | ❌ |
| `youtrack` | [YouTrack markup](https://www.jetbrains.com/help/youtrack/server/youtrack-markdown-syntax-issues.html#tables) | `python-tabulate` | ✅ |

```{todo}
Explain extra parameters supported by `print_table()` for each category of formats.
```

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
invoke(table_command, args=["--table-format", "html"])
```

```{click:run}
:emphasize-lines: 1
invoke(table_command, args=["--table-format", "jira"])
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

## `click_extra.table` API

```{eval-rst}
.. autoclasstree:: click_extra.table
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.table
   :members:
   :undoc-members:
   :show-inheritance:
```