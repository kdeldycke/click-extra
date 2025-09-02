# {octicon}`table` Table

Click Extra provides a way to render tables in the terminal.

Here how to use the standalone table rendering option decorator:

```{click:example}
:emphasize-lines: 4
from click_extra import command, echo, pass_context, table_format_option

@command
@table_format_option
@pass_context
def table_command(ctx):
    data = ((1, 87), (2, 80), (3, 79))
    headers = ("day", "temperature")
    ctx.print_table(data, headers)
```

As you can see above, this option adds a ready-to-use `print_table()` method to the context object.

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
    ╒═════╤═════════════╕
    │ day │ temperature │
    ╞═════╪═════════════╡
    │ 1   │ 87          │
    │ 2   │ 80          │
    │ 3   │ 79          │
    ╘═════╧═════════════╛
    """)
```

```{click:run}
from textwrap import dedent

result = invoke(table_command, args=["--table-format", "jira"])
assert result.stdout == dedent("""\
    || day || temperature ||
    | 1   | 87          |
    | 2   | 80          |
    | 3   | 79          |
    """)
```

### Table formats

Table formats are aggregated from three sources:
- [`python-tabulate`](https://github.com/astanin/python-tabulate)
- [`cli-helpers`](https://github.com/dbcli/cli_helpers)
- Python's [`csv` module](https://docs.python.org/3/library/csv.html) from the standard library

| Format | Description | Source |
|--------|-------------|--------|
| `asciidoc` | AsciiDoc table | `python-tabulate` |
| `csv` | Comma-separated values | `csv`|
| `csv-excel` | CSV with Excel dialect | `csv`|
| `csv-excel-tab` | CSV with Excel tab dialect | `csv`|
| `csv-unix` | CSV with Unix dialect | `csv`|
| `double-grid` | Double-line grid table | `python-tabulate` |
| `double-outline` | Double-line outline table | `python-tabulate` |
| `fancy-grid` | Grid with Unicode box-drawing characters | `python-tabulate` |
| `fancy-outline` | Outline with Unicode box-drawing characters | `python-tabulate` |
| `github` | GitHub-flavored Markdown table | `python-tabulate` |
| `grid` | Grid table with ASCII characters | `python-tabulate` |
| `heavy-grid` | Heavy-line grid table | `python-tabulate` |
| `heavy-outline` | Heavy-line outline table | `python-tabulate` |
| `html` | HTML table | `python-tabulate` |
| `jira` | Jira-style markup | `python-tabulate` |
| `latex` | LaTeX table | `python-tabulate` |
| `latex-booktabs` | LaTeX table with booktabs package | `python-tabulate` |
| `latex-longtable` | LaTeX longtable environment | `python-tabulate` |
| `latex-raw` | LaTeX table without escaping | `python-tabulate` |
| `mediawiki` | MediaWiki markup | `python-tabulate` |
| `mixed-grid` | Mixed-line grid table | `python-tabulate` |
| `mixed-outline` | Mixed-line outline table | `python-tabulate` |
| `moinmoin` | MoinMoin wiki markup | `python-tabulate` |
| `orgtbl` | Emacs org-mode table | `python-tabulate` |
| `outline` | Simple outline table | `python-tabulate` |
| `pipe` | Markdown-style pipes | `python-tabulate` |
| `plain` | Plain text, no formatting | `python-tabulate` |
| `presto` | Presto SQL output style | `python-tabulate` |
| `pretty` | Pretty ASCII table | `python-tabulate` |
| `psql` | PostgreSQL output style | `python-tabulate` |
| `rounded-grid` | Rounded grid table | `python-tabulate` |
| `rounded-outline` | Rounded outline table | `python-tabulate` |
| `rst` | reStructuredText grid table | `python-tabulate` |
| `simple` | Simple table with spaces | `python-tabulate` |
| `simple-grid` | Simple grid table | `python-tabulate` |
| `simple-outline` | Simple outline table | `python-tabulate` |
| `textile` | Textile markup | `python-tabulate` |
| `tsv` | Tab-separated values | `python-tabulate` |
| `unsafehtml` | HTML table without escaping | `python-tabulate` |
| `vertical` | Vertical table layout | `cli-helpers` |
| `youtrack` | YouTrack markup | `python-tabulate` |

```{todo}
Explain extra parameters supported by `print_table()` for each category of formats.
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

```{click:example}
:emphasize-lines: 7-8
from click_extra import command, echo, pass_context, table_format_option

@command
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