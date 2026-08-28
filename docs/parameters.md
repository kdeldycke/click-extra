# {octicon}`tasklist` Parameters

Click Extra implements tools to manipulate your CLI's parameters, options and arguments.

The cornerstone of these tools is the magical `--params` option, which is a X-ray scanner for your CLI's parameters.

## `--params` option

Click Extra adds a `--params` flag to every `@command` and `@group`. It dumps a colorized table of every parameter, its current value, where that value came from, the resolved environment variable, and the default:

```{click:source}
:emphasize-lines: 3
from click_extra import command, option, echo

@command
@option("--int-param1", type=int, default=10)
@option("--int-param2", type=int, default=555)
def cli(int_param1, int_param2):
    echo(f"int_param1 is {int_param1!r}")
    echo(f"int_param2 is {int_param2!r}")
```

```{click:run}
:emphasize-result-lines: 1
result = invoke(cli, args=["--int-param1", "3", "--params"])
assert "│ \x1b[33m\x1b[2mCLI_INT_PARAM1\x1b[0m          │ \x1b[32m\x1b[2m\x1b[3m10\x1b[0m " in result.stdout
assert "│ \x1b[33m\x1b[2mCLI_INT_PARAM2\x1b[0m          │ \x1b[32m\x1b[2m\x1b[3m555\x1b[0m " in result.stdout
```

`--int-param1` shows `3` because it was passed on the command line. `--int-param2` falls back to its `555` default. The `--params` option produces this table dynamically: every value is re-evaluated at invocation time from the current `argv`, environment, and config files.

```{tip}
Every command built with `@command` or `@group` captures the pre-parsed `argv` slice on `ctx.meta` as `RAW_ARGS`, which `--params` itself relies on to re-parse the original arguments. See the [available keys](context.md#available-keys) table to read it from your own callbacks.
```

```{hint}
`--params` always displays all parameters, even those marked as not *allowed in conf*. In effect bypassing the {py:attr}`excluded_params <click_extra.parameters.ParamStructure.excluded_params>` argument. So you can still see the `--help`, `--version`, `-C`/`--config` and `--params` options in the table.
```

### Available columns

Each row in the table mirrors a single [`click.Parameter`](https://click.palletsprojects.com/en/stable/api/#click.Parameter) instance. The columns map to its public attributes (plus a handful of Click Extra-specific fields). The table below is auto-generated at build time from {py:attr}`ShowParamsOption.TABLE_HEADERS <click_extra.parameters.ShowParamsOption.TABLE_HEADERS>`: edit the {py:attr}`ColumnSpec.description <click_extra.table.ColumnSpec.description>` entries in `click_extra/parameters.py` to update it.

{{ show_params_columns_table }}

### Columns selection

Add Click Extra's {py:func}`columns_option <click_extra.decorators.columns_option>` to your CLI so users can pick which columns `--params` emits, in the order they want, SQL `SELECT`-style:

```{click:source}
:hide-source:
from click_extra import columns_option, command, echo, option

@command
@columns_option
@option("--int-param1", type=int, default=10)
@option("--int-param2", type=int, default=555)
def cli_with_columns(int_param1, int_param2):
    echo(f"int_param1 is {int_param1!r}")
    echo(f"int_param2 is {int_param2!r}")
```

```{click:run}
:emphasize-result-lines: 1
result = invoke(cli_with_columns, args=["--no-color", "--columns", "id,is_flag,default,value", "--params"])
assert "ID" in result.stdout
assert "Is flag" in result.stdout
assert "Default" in result.stdout
assert "Value" in result.stdout
# Unselected columns are not in the output.
assert "Spec." not in result.stdout
assert "Confirmation prompt" not in result.stdout
```

Unknown IDs raise a `BadParameter` listing the valid ones (`--columns` is built on top of the generic [`MultiChoice`](types.md#multichoice) type, which does the validation at parse time). The standalone [`click-extra wrap --params`](#introspecting-external-clis) exposes the same option for inspecting third-party CLIs.

One column is opt-in: `Help` carries each parameter's own help text, the only free-form prose in the table, and would squeeze every other column out of shape if it showed up uninvited. Select it by ID to get it:

```{click:run}
result = invoke(cli_with_columns, args=["--no-color", "--columns", "id,spec,help", "--params"])
assert "Help" in result.stdout
assert "Show all CLI parameters" in result.stdout
```

### As structured data

`--params` speaks every [structured format](table.md#table-formats), which turns the table into a description of the CLI a tool can consume. It is what makes a Click Extra command introspectable by something other than a reader:

```{click:run}
import json

result = invoke(
    cli_with_columns,
    args=["--table-format", "json", "--columns", "id,spec,help,default,envvars", "--params"],
)
rows = {row["ID"]: row for row in json.loads(result.stdout)}
assert rows["cli-with-columns.int_param1"]["Default"] == 10
assert rows["cli-with-columns.int_param1"]["Env. vars."] == [
    "CLI_WITH_COLUMNS_INT_PARAM1"
]
```

Values come out as native types here (`10`, not `"10"`), and the `Help` column makes each row self-describing. This is the *state* of one invocation; for the command's own interface (its description, usage line, subcommands and examples), [`--help-format`](machine-readable.md) covers what a parameter table cannot. [Machine-readable help](machine-readable.md) sets the two side by side.

### Table format

The default table produced by `--params` can be a bit overwhelming, so you can change its rendering with the [`--table-format` option](table.md#table-formats):

```{click:run}
:emphasize-result-lines: 1
result = invoke(cli, args=["--table-format", "vertical", "--params"])
assert "***************************[ 1. row ]***************************\n" in result.stdout
assert "\x1b[1mEnv. vars.\x1b[0m          | \x1b[33m\x1b[2mCLI_INT_PARAM1\x1b[0m\n" in result.stdout
assert "\x1b[1mDefault\x1b[0m             | \x1b[32m\x1b[2m\x1b[3m10\x1b[0m\n" in result.stdout
```

```{caution}
Because both options are eager, the order in which they are passed matters. `--table-format` must be passed before `--params`, otherwise it will have no effect.
```

### Color highlighting

By default, the table produced by `--params` is colorized to highlight important bits. If you do not like colors, you can disable them with the [`--no-color` option](colorize.md#color-flag):

```{click:run}
:emphasize-result-lines: 1
result = invoke(cli, args=["--no-color", "--params"])
assert "│ CLI_INT_PARAM1          │ 10 " in result.stdout
assert "│ CLI_INT_PARAM2          │ 555 " in result.stdout
```

```{caution}
Because both options are eager, the order in which they are passed matters. `--no-color` must be passed before `--params`, otherwise it will have no effect.
```

## Introspecting parameters

If you need to dive deeper into parameters and their values, there is a lot of metadata available in the context. Here are some pointers:

```{code-block} python
:emphasize-lines: 13-15
from click import option, echo, pass_context

from click_extra import config_option, group

@group
@option("--dummy-flag/--no-flag")
@option("--my-list", multiple=True)
@config_option
@pass_context
def my_cli(ctx, dummy_flag, my_list):
    echo(f"dummy_flag    is {dummy_flag!r}")
    echo(f"my_list       is {my_list!r}")
    echo(f"Raw parameters:            {ctx.meta.get('click_extra.raw_args', [])}")
    echo(f"Loaded, default values:    {ctx.default_map}")
    echo(f"Values passed to function: {ctx.params}")

@my_cli.command()
@option("--int-param", type=int, default=10)
def subcommand(int_param):
    echo(f"int_parameter is {int_param!r}")
```

```{hint}
The `click_extra.raw_args` metadata field in the context referenced above is not a standard feature from Click, but a helper introduced by Click Extra. It is only available with `@group` and `@command` decorators.
```

Now if we feed the following `~/configuration.toml` configuration file:

```{code-block} toml
:caption: `~/configuration.toml`
[my-cli]
verbosity = "DEBUG"
dummy_flag = true
my_list = ["item 1", "item #2", "Very Last Item!"]

[my-cli.subcommand]
int_param = 3
```

Here is what we get:

```{code-block} shell-session
$ cli --config ~/configuration.toml default-command
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
Raw parameters:            ['--config', '~/configuration.toml', 'default-command']
Loaded, default values:    {'dummy_flag': True, 'my_list': ['pip', 'npm', 'gem'], 'verbosity': 'DEBUG', 'default-command': {'int_param': 3}}
Values passed to function: {'dummy_flag': True, 'my_list': ('pip', 'npm', 'gem')}
```

## Introspecting external CLIs

The `--params` option works on your own Click Extra CLIs. To inspect a third-party CLI that doesn't use Click Extra, use [`wrap --params`](wrap.md#introspecting-external-clis), which loads the target and prints the same table without running it:

```{click:source}
:hide-source:
from click_extra.cli import demo
```

```{click:run}
result = invoke(demo, args=["wrap", "--params", "--table-format", "vertical", "--", "flask", "run"])
assert result.exit_code == 0
assert "run.host" in result.output
assert "-p, --port INTEGER" in result.output
```

## Parameter structure

The table `--params` prints is the flattened view of a tree, and {py:class}`~click_extra.parameters.ParamStructure` is what builds it. The same tree is what [`--config`](config.md) maps a configuration file's sections onto: a node is a subcommand, a leaf is a parameter, and the path from the root spells the fully-qualified ID.

Take a group with two subcommands:

```{python:source}
import click


@click.group
@click.option("--unit", type=click.Choice(("celsius", "fahrenheit")), default="celsius")
def weather(unit):
    """Report the weather of a city."""


@weather.command
@click.option("--days", type=int, default=3)
@click.option("--tag", multiple=True)
@click.argument("city")
def forecast(days, tag, city):
    """Forecast the days to come."""


@weather.command
@click.option("--since", type=click.DateTime())
def history(since):
    """Look back at recorded weather."""
```

`ParamStructure` is a mixin: it expects the class using it to settle which parameters the tree covers. Freezing both filters open covers everything.

```{python:source}
from click_extra.parameters import ParamStructure


class Structure(ParamStructure):
    excluded_params = frozenset()
    included_params = None
```

{py:attr}`~click_extra.parameters.ParamStructure.params_template` then returns the command tree with every leaf nulled out, which is the skeleton a configuration file is expected to fill:

```{python:run}
:show-source:
:language: json
import json

with click.Context(weather):
    print(json.dumps(Structure().params_template, indent=2))
```

The walk resolves its root command from the active context, which a CLI callback already sits in. Outside of one, a bare {py:class}`click.Context` around the group is enough, as above.

{py:attr}`~click_extra.parameters.ParamStructure.params_objects` is the same tree with the parameter objects kept at the leaves, which is what a consumer needs to coerce a configuration value or report where one came from:

```{python:run}
:show-source:
with click.Context(weather):
    structure = Structure()
    print(structure.params_objects["weather"]["forecast"])
    print(ParamStructure.get_tree_value(structure.params_objects, "weather", "forecast", "days"))
```

{py:meth}`~click_extra.parameters.ParamStructure.get_tree_value` descends a path in one call, and raises a `KeyError` when the path leads nowhere. Its counterpart {py:meth}`~click_extra.parameters.ParamStructure.init_tree_dict` builds a nested dict from a path and a leaf, which is how the tree gets assembled one parameter at a time.

### Fully-qualified IDs

Joining a path with {py:data}`~click_extra.parameters.PARAM_PATH_SEP` produces the ID shown in the `ID` column of `--params`, and the same string [`excluded_params` and `included_params`](config.md#excluding-parameters) are matched against. {py:meth}`~click_extra.parameters.ParamStructure.walk_params` yields those paths directly, unfiltered and flat:

```{python:run}
:show-source:
from click_extra.parameters import PARAM_PATH_SEP

with click.Context(weather):
    for keys, param in Structure().walk_params():
        param_type = ParamStructure.get_param_type(param)
        print(f"{PARAM_PATH_SEP.join(keys):26} {param_type.__name__}")
```

The second column is {py:meth}`~click_extra.parameters.ParamStructure.get_param_type`, which reduces a Click type to the Python type a configuration file has to carry, through the {py:attr}`~click_extra.parameters.ParamStructure.TYPE_MAP` table. A repeatable parameter is a `list` whatever its items are, a boolean flag is a `bool`, and an unrecognized custom type falls back to `str`, since a command line carries nothing else.

`--help` sits in that tree like any other option, and a subcommand sharing its name with a parameter of the same level is left out of it, since a single path cannot address both. What a consumer does with the tree is its own decision: `--params` reports every node, while `--config` narrows it down through [`excluded_params`](config.md#excluding-parameters).

## `click_extra.parameters` API

```{eval-rst}
.. autoclasstree:: click_extra.parameters
   :strict:

.. automodule:: click_extra.parameters
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
