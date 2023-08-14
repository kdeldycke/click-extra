# Parameters

Click Extra provides a set of tools to help you manage parameters in your CLI.

Like the magical `--show-params` option, which is a X-ray scanner for your CLI's parameters.

## Parameter structure

```{todo}
Write example and tutorial.
```

## Introspecting parameters

If for any reason you need to dive into parameters and their values, there is a lot of intermediate and metadata available in the context. Here are some pointers:

```{code-block} python
from click import option, echo, pass_context

from click_extra import config_option, extra_group

@extra_group
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

```{caution}
The `click_extra.raw_args` metadata field in the context referenced above is not a standard feature from Click, but a helper introduced by Click Extra. It is only available with `@extra_group` and `@extra_command` decorators.

In the mean time, it is [being discussed in the Click community at `click#1279`](https://github.com/pallets/click/issues/1279#issuecomment-1493348208).
```

```{todo}
Propose the `raw_args` feature upstream to Click.
```

Now if we feed the following `~/configuration.toml` configuration file:

```toml
[my-cli]
verbosity = "DEBUG"
dummy_flag = true
my_list = [ "item 1", "item #2", "Very Last Item!",]

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

## `--show-params` option

Click Extra provides a ready-to-use `--show-params` option, which is enabled by default.

It produces a comprehensive table of your CLI parameters, normalized IDs, types and corresponding environment variables. And because it dynamiccaly print their default value, actual value and its source, it is a practical tool for users to introspect and debug the parameters of a CLI.

See how the default `@extra_command` decorator come with the default `--show-params` option and the result of its use:

```{eval-rst}
.. click:example::
    from click_extra import extra_command, option, echo

    @extra_command
    @option("--int-param1", type=int, default=10)
    @option("--int-param2", type=int, default=555)
    def cli(int_param1, int_param2):
        echo(f"int_param1 is {int_param1!r}")
        echo(f"int_param2 is {int_param2!r}")

.. click:run::
    result = invoke(cli, args=["--verbosity", "Debug", "--int-param1", "3", "--show-params"])
    assert "click_extra.raw_args: ['--verbosity', 'Debug', '--int-param1', '3', '--show-params']" in result.stderr
    assert "│ \x1b[33m\x1b[2mCLI_INT_PARAM1\x1b[0m  │ \x1b[32m\x1b[2m\x1b[3m10\x1b[0m " in result.stdout
    assert "│ \x1b[33m\x1b[2mCLI_INT_PARAM2\x1b[0m  │ \x1b[32m\x1b[2m\x1b[3m555\x1b[0m " in result.stdout
```

```{note}
Notice how `--show-params` is showing all parameters, even those provided to the `exclude_params` argument. You can still see the `--help`, `--version`, `-C`/`--config` and `--show-params` options in the table.
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
