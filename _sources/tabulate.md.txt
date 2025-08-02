# Table

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
assert "-t, --table-format" in result.stdout
```

So you can use the `--table-format` option to change the table format:

```{click:run}
from textwrap import dedent

result = invoke(table_command, args=["--table-format", "fancy_outline"])
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

Available table [formats are inherited from `python-tabulate`](https://github.com/astanin/python-tabulate#table-format).

This list is augmented with extra formats:

- `csv`
- `csv-excel`
- `csv-excel-tab`
- `csv-unix`
- `vertical`

```{todo}
Explicitly list all formats IDs and render an example of each format.
```

```{todo}
Explain extra parameters supported by `print_table()` for each category of formats.
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
result = invoke(vanilla_command, args=["--table-format", "fancy_outline"])
assert "Table format: fancy_outline" in result.stdout
```

## `click_extra.tabulate` API

```{eval-rst}
.. autoclasstree:: click_extra.tabulate
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.tabulate
   :members:
   :undoc-members:
   :show-inheritance:
```
