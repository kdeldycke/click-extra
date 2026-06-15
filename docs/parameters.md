# {octicon}`tasklist` Parameters

Click Extra implements tools to manipulate your CLI's parameters, options and arguments.

The cornerstone of these tools is the magical `--show-params` option, which is a X-ray scanner for your CLI's parameters.

<a name="show-params-option"></a>

## `--show-params` option

Click Extra adds a `--show-params` flag to every `@command` and `@group`. It dumps a colorized table of every parameter, its current value, where that value came from, the resolved environment variable, and the default:

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
:emphasize-lines: 1
result = invoke(cli, args=["--int-param1", "3", "--show-params"])
assert "│ \x1b[33m\x1b[2mCLI_INT_PARAM1\x1b[0m      │ \x1b[32m\x1b[2m\x1b[3m10\x1b[0m " in result.stdout
assert "│ \x1b[33m\x1b[2mCLI_INT_PARAM2\x1b[0m      │ \x1b[32m\x1b[2m\x1b[3m555\x1b[0m " in result.stdout
```

`--int-param1` shows `3` because it was passed on the command line. `--int-param2` falls back to its `555` default. The `--show-params` option produces this table dynamically: every value is re-evaluated at invocation time from the current `argv`, environment, and config files.

```{tip}
Every command built with `@command` or `@group` captures the pre-parsed `argv` slice on `ctx.meta` as `RAW_ARGS`, which `--show-params` itself relies on to re-parse the original arguments. See the [available keys](context.md#available-keys) table to read it from your own callbacks.
```

```{hint}
`--show-params` always displays all parameters, even those marked as not *allowed in conf*. In effect bypassing [its own `excluded_params` argument](#click_extra.parameters.ParamStructure.excluded_params). So you can still see the `--help`, `--version`, `-C`/`--config` and `--show-params` options in the table.
```

### Available columns

Each row in the table mirrors a single [`click.Parameter`](https://click.palletsprojects.com/en/stable/api/#click.Parameter) instance. The columns map to its public attributes (plus a handful of Click Extra-specific fields):

| Column                | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| :-------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ID`                  | Fully-qualified parameter path (`cli.subcommand.param-name`) derived from the [`click.Command`](https://click.palletsprojects.com/en/stable/api/#click.Command) tree. Doubles as the key used to address the parameter from a configuration file.                                                                                                                                                                                                                                                                                                                                         |
| `Spec.`               | Option/argument specification string (like `-v, --verbose`) extracted from [`click.Parameter.get_help_record()`](https://click.palletsprojects.com/en/stable/api/#click.Parameter.get_help_record).                                                                                                                                                                                                                                                                                                                                                                                       |
| `Class`               | Fully-qualified class of the parameter: a subclass of [`click.Option`](https://click.palletsprojects.com/en/stable/api/#click.Option), [`click.Argument`](https://click.palletsprojects.com/en/stable/api/#click.Argument), [`cloup.Option`](https://cloup.readthedocs.io/en/stable/autoapi/cloup/index.html#cloup.Option), or one of Click Extra's own wrappers ([`click_extra.parameters.Option`](#click_extra.parameters.Option), [`click_extra.parameters.Argument`](#click_extra.parameters.Argument), [`click_extra.parameters.ExtraOption`](#click_extra.parameters.ExtraOption)). |
| `Param type`          | Click value converter class: a subclass of [`click.ParamType`](https://click.palletsprojects.com/en/stable/api/#click.ParamType) like [`click.IntRange`](https://click.palletsprojects.com/en/stable/api/#click.IntRange), [`click.Choice`](https://click.palletsprojects.com/en/stable/api/#click.Choice), or a Click Extra type.                                                                                                                                                                                                                                                        |
| `Python type`         | Python built-in type the parsed value resolves to: [`str`](https://docs.python.org/3/library/stdtypes.html#text-sequence-type-str), [`int`](https://docs.python.org/3/library/functions.html#int), [`float`](https://docs.python.org/3/library/functions.html#float), [`bool`](https://docs.python.org/3/library/functions.html#bool), or [`list`](https://docs.python.org/3/library/stdtypes.html#list). Computed by [`ParamStructure.get_param_type()`](#click_extra.parameters.ParamStructure.get_param_type) from the Click `Param type`.                                             |
| `Hidden`              | Reflects [`click.Option`'s `hidden`](https://click.palletsprojects.com/en/stable/api/#click.Option) constructor argument: the option is omitted from `--help` output. Empty for [`click.Argument`](https://click.palletsprojects.com/en/stable/api/#click.Argument), which does not support hiding.                                                                                                                                                                                                                                                                                       |
| `Exposed`             | Reflects [`click.Parameter`'s `expose_value`](https://click.palletsprojects.com/en/stable/api/#click.Parameter) constructor argument: whether the parsed value is forwarded to the command callback. Eager options like `--show-params` and `--help` typically run a callback and exit, so they are not exposed.                                                                                                                                                                                                                                                                          |
| `Allowed in conf?`    | Click Extra-specific: whether the parameter is reachable from a configuration file. Controlled by [`ParamStructure.excluded_params`](#click_extra.parameters.ParamStructure.excluded_params) and [`included_params`](#click_extra.parameters.ParamStructure.included_params). Empty when the CLI has no [`--config` option](config.md).                                                                                                                                                                                                                                                   |
| `Env. vars.`          | Environment variables read for this parameter: the explicit [`click.Parameter`'s `envvar`](https://click.palletsprojects.com/en/stable/api/#click.Parameter) plus the auto-resolved IDs documented in [Environment variables](envvar.md).                                                                                                                                                                                                                                                                                                                                                 |
| `Default`             | Default value returned by [`click.Parameter.get_default()`](https://click.palletsprojects.com/en/stable/api/#click.Parameter.get_default), rendered as its Python `repr()`.                                                                                                                                                                                                                                                                                                                                                                                                               |
| `Is flag`             | Reflects [`click.Option`'s `is_flag`](https://click.palletsprojects.com/en/stable/api/#click.Option): whether the option behaves as a flag (no value taken from the command line). Empty for [`click.Argument`](https://click.palletsprojects.com/en/stable/api/#click.Argument).                                                                                                                                                                                                                                                                                                         |
| `Flag value`          | Reflects [`click.Option`'s `flag_value`](https://click.palletsprojects.com/en/stable/api/#click.Option): the Python value substituted for the option when its flag is used. Defaults to `True` for boolean flags, can be any value for flag-value style options (like `@option("--upper", "transform", flag_value="upper")`).                                                                                                                                                                                                                                                             |
| `Is bool flag`        | Reflects `click.Option.is_bool_flag` (set internally by Click when `flag_value` is `True` or `False`): the option is a *true* boolean flag, as opposed to a flag-value style option.                                                                                                                                                                                                                                                                                                                                                                                                      |
| `Multiple`            | Reflects [`click.Parameter`'s `multiple`](https://click.palletsprojects.com/en/stable/api/#click.Parameter): the parameter can be repeated on the command line, collecting values into a tuple.                                                                                                                                                                                                                                                                                                                                                                                           |
| `Nargs`               | Reflects [`click.Parameter`'s `nargs`](https://click.palletsprojects.com/en/stable/api/#click.Parameter): the number of CLI tokens the parameter consumes. `1` is the default; `-1` denotes a variadic argument.                                                                                                                                                                                                                                                                                                                                                                          |
| `Prompt`              | Reflects [`click.Option`'s `prompt`](https://click.palletsprojects.com/en/stable/api/#click.Option): the text shown to the user when the option is not provided on the command line. Empty when no prompt is configured.                                                                                                                                                                                                                                                                                                                                                                  |
| `Confirmation prompt` | Reflects [`click.Option`'s `confirmation_prompt`](https://click.palletsprojects.com/en/stable/api/#click.Option): whether the user is asked to enter the value twice for confirmation.                                                                                                                                                                                                                                                                                                                                                                                                    |
| `Value`               | Current value of the parameter at invocation time, computed by [`click.Parameter.consume_value()`](https://click.palletsprojects.com/en/stable/api/#click.Parameter) from the merged sources (CLI, environment, config file, default).                                                                                                                                                                                                                                                                                                                                                    |
| `Source`              | Provenance of the resolved value: a [`click.core.ParameterSource`](https://click.palletsprojects.com/en/stable/api/#click.core.ParameterSource) enum member such as `COMMANDLINE`, `ENVIRONMENT`, `DEFAULT_MAP`, or `DEFAULT`.                                                                                                                                                                                                                                                                                                                                                            |

The full list is exposed as [`ShowParamsOption.TABLE_HEADERS`](#click_extra.parameters.ShowParamsOption.TABLE_HEADERS).

### Table format

The default table produced by `--show-params` can be a bit overwhelming, so you can change its rendering with the [`--table-format` option](table.md#table-formats):

```{click:run}
:emphasize-lines: 1
result = invoke(cli, args=["--table-format", "vertical", "--show-params"])
assert "***************************[ 1. row ]***************************\n" in result.stdout
assert "\x1b[1mEnv. vars.\x1b[0m          | \x1b[33m\x1b[2mCLI_INT_PARAM1\x1b[0m\n" in result.stdout
assert "\x1b[1mDefault\x1b[0m             | \x1b[32m\x1b[2m\x1b[3m10\x1b[0m\n" in result.stdout
```

```{caution}
Because both options are eager, the order in which they are passed matters. `--table-format` must be passed before `--show-params`, otherwise it will have no effect.
```

### Color highlighting

By default, the table produced by `--show-params` is colorized to highlight important bits. If you do not like colors, you can disable them with the [`--no-color` option](colorize.md#color-no-color-flag):

```{click:run}
:emphasize-lines: 1
result = invoke(cli, args=["--no-color", "--show-params"])
assert "│ CLI_INT_PARAM1      │ 10 " in result.stdout
assert "│ CLI_INT_PARAM2      │ 555 " in result.stdout
```

```{caution}
Because both options are eager, the order in which they are passed matters. `--no-color` must be passed before `--show-params`, otherwise it will have no effect.
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

In the mean time, it is [being discussed in the Click community at `click#1279`](https://github.com/pallets/click/issues/1279#issuecomment-1493348208).
```

```{todo}
Propose the `raw_args` feature upstream to Click.
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

The `--show-params` option works on your own Click Extra CLIs. To inspect a third-party CLI that doesn't use Click Extra, use the [`show-params` subcommand](wrap.md#introspecting-external-clis):

```{click:source}
:hide-source:
from click_extra.cli import show_params_cmd
```

```{click:run}
result = invoke(show_params_cmd, prog_name="click-extra show-params", args=["--table-format", "vertical", "flask", "run"])
assert result.exit_code == 0
assert "run.host" in result.output
assert "-p, --port INTEGER" in result.output
```

## Parameter structure

```{todo}
Write example and tutorial.
```

## `click_extra.parameters` API

```{eval-rst}
.. autoclasstree:: click_extra.parameters
   :strict:

.. automodule:: click_extra.parameters
   :members:
   :undoc-members:
   :show-inheritance:
```
