# {octicon}`tasklist` Parameters

Click Extra implements tools to manipulate your CLI's parameters, options and arguments.

The cornerstone of these tools is the magical `--show-params` option, which is a X-ray scanner for your CLI's parameters.

## `--show-params` option

Click Extra provides a ready-to-use `--show-params` option, which is enabled by default.

It produces a comprehensive table of all the metadata about each of your CLI parameters, including: their normalized IDs, types, defaults and environment variables. And because it is dynamic, actual values and their sources are evaluated at runtime.

The default `@command` decorator come with the `--show-params` option, so you can call it right away:

```{click:source}
---
emphasize-lines: 3
---
from click_extra import command, option, echo

@command
@option("--int-param1", type=int, default=10)
@option("--int-param2", type=int, default=555)
def cli(int_param1, int_param2):
    echo(f"int_param1 is {int_param1!r}")
    echo(f"int_param2 is {int_param2!r}")
```

```{click:run}
---
emphasize-lines: 1
---
result = invoke(cli, args=["--int-param1", "3", "--show-params"])
assert "│ \x1b[33m\x1b[2mCLI_INT_PARAM1\x1b[0m   │ \x1b[32m\x1b[2m\x1b[3m10\x1b[0m " in result.stdout
assert "│ \x1b[33m\x1b[2mCLI_INT_PARAM2\x1b[0m   │ \x1b[32m\x1b[2m\x1b[3m555\x1b[0m " in result.stdout
```

See in the rendered table above how `--int-param1` is set to `3`, because it was explicitly set on the command line. While `--int-param2` still gets its value from its `555` default.

```{hint}
`--show-params` always displays all parameters, even those marked as not *allowed in conf*. In effect bypassing [its own `excluded_params` argument](#click_extra.parameters.ParamStructure.excluded_params). So you can still see the `--help`, `--version`, `-C`/`--config` and `--show-params` options in the table.
```

### Table format

The default table produced by `--show-params` can be a bit overwhelming, so you can change its rendering with the [`--table-format` option](table.md#table-formats):

```{click:run}
---
emphasize-lines: 1
---
result = invoke(cli, args=["--table-format", "vertical", "--show-params"])
assert "***************************[ 1. row ]***************************\n" in result.stdout
assert "\x1b[1mEnv. vars.\x1b[0m       | \x1b[33m\x1b[2mCLI_INT_PARAM1\x1b[0m\n" in result.stdout
assert "\x1b[1mDefault\x1b[0m          | \x1b[32m\x1b[2m\x1b[3m10\x1b[0m\n" in result.stdout
```

```{caution}
Because both options are eager, the order in which they are passed matters. `--table-format` must be passed before `--show-params`, otherwise it will have no effect.
```

### Color highlighting

By default, the table produced by `--show-params` is colorized to highlight important bits. If you do not like colors, you can disable them with the [`--no-color` option](colorize.md#color-option):

```{click:run}
---
emphasize-lines: 1
---
result = invoke(cli, args=["--no-color", "--show-params"])
assert "│ CLI_INT_PARAM1   │ 10 " in result.stdout
assert "│ CLI_INT_PARAM2   │ 555 " in result.stdout
```

```{caution}
Because both options are eager, the order in which they are passed matters. `--no-color` must be passed before `--show-params`, otherwise it will have no effect.
```

## Introspecting parameters

If you need to dive deeper into parameters and their values, there is a lot of metadata available in the context. Here are some pointers:

```{code-block} python
---
emphasize-lines: 13-15
---
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

## Parameter structure

```{todo}
Write example and tutorial.
```

## `click_extra.parameters` API

```{eval-rst}
.. autoclasstree:: click_extra.parameters
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.parameters
   :members:
   :undoc-members:
   :show-inheritance:
```
