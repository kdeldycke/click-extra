# {octicon}`mortar-board` Tutorial

This tutorial details how we transformed the [canonical `click` example](https://github.com/pallets/click?tab=readme-ov-file#a-simple-example):

![click CLI help screen](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/click-help-screen.png)

Into this:

![click-extra CLI help screen](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/click-extra-screen.png)

## All bells and whistles

The [canonical `click` example](https://github.com/pallets/click?tab=readme-ov-file#a-simple-example) is implemented that way:

```{click:example}
import click

@click.command
@click.option("--count", default=1, help="Number of greetings.")
@click.option("--name", prompt="Your name", help="The person to greet.")
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        click.echo(f"Hello, {name}!")
```

Whose help screen renders as:

```{click:run}
from textwrap import dedent
result = invoke(hello, args=["--help"])
assert result.output == dedent(
    """\
    Usage: hello [OPTIONS]

      Simple program that greets NAME for a total of COUNT times.

    Options:
      --count INTEGER  Number of greetings.
      --name TEXT      The person to greet.
      --help           Show this message and exit.
    """
)
```

To augment the example above with [all the bells and whistles](index.md#features) `click-extra` has in store, you just need to import from its namespace:

```{click:example}
:emphasize-lines: 1,3-5,9
import click_extra

@click_extra.command
@click_extra.option("--count", default=1, help="Number of greetings.")
@click_extra.option("--name", prompt="Your name", help="The person to greet.")
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        click_extra.echo(f"Hello, {name}!")
```

And now you get:

```{click:run}
from textwrap import dedent
result = invoke(hello, args=["--help"])
assert result.output.startswith(dedent("""\
    \x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mhello\x1b[0m \x1b[36m\x1b[2m[OPTIONS]\x1b[0m

      Simple program that greets NAME for a total of COUNT times.

    \x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m
      \x1b[36m--count\x1b[0m \x1b[36m\x1b[2mINTEGER\x1b[0m       Number of greetings.  \x1b[2m[\x1b[0m\x1b[2mdefault: \x1b[0m\x1b[32m\x1b[2m\x1b[3m1\x1b[0m\x1b[2m]\x1b[0m
      \x1b[36m--name\x1b[0m \x1b[36m\x1b[2mTEXT\x1b[0m           The person to greet.
    """
))
```

That's it!

```{tip}
`click_extra` is proxy-ing the whole `click` and `cloud` namespace, so you can use it as a [drop-in replacement](tutorial.md#drop-in-replacement).
```

## Mix and match

If you do not like the opiniated way the `@click_extra.command` decorator is built with all its defaults options, you are still free to pick them up independently.

If, for example, you're only interested in using [the `--config` option](config.md), nothing prevents you to use it with a standard `click` CLI:

```{click:example}
:emphasize-lines: 2, 7
import click
import click_extra

@click.command
@click.option("--count", default=1, help="Number of greetings.")
@click.option("--name", prompt="Your name", help="The person to greet.")
@click_extra.config_option
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        click.echo(f"Hello, {name}!")
```

Which now renders to:

```{click:run}
:emphasize-lines: 9-12
result = invoke(hello, args=["--help"])
assert "--config CONFIG_PATH" in result.output
```

This option itself behave like any Click option and can be customized easily:

```{click:example}
:emphasize-lines: 7
from click import command, echo, option
from click_extra import config_option

@command
@option("--count", default=1, help="Number of greetings.")
@option("--name", prompt="Your name", help="The person to greet.")
@config_option("--hello-conf", metavar="CONF_FILE", help="Loads CLI config.")
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        echo(f"Hello, {name}!")
```

```{click:run}
:emphasize-lines: 9-10
result = invoke(hello, args=["--help"])
assert "--hello-conf CONF_FILE  Loads CLI config." in result.output
```

## Cloup integration

All Click Extra primitives are sub-classes of Cloup's and supports all its features.

Like [option groups](https://cloup.readthedocs.io/en/stable/pages/option-groups.html):

```{click:example}
:emphasize-lines: 2-3, 9-15
import click
import cloup
import click_extra

@cloup.command()
@click.option("--count", default=1, help="Number of greetings.")
@click.option("--name", prompt="Your name", help="The person to greet.")
@cloup.option_group(
    "Cool options",
    cloup.option("--foo", help="The option that starts it all."),
    cloup.option("--bar", help="Another important option."),
    click_extra.config_option("--hello-conf", metavar="CONF_FILE", help="Loads CLI config."),
    constraint=cloup.constraints.RequireAtLeast(1),
)
def hello(count, name, foo, bar, hello_conf):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        click.echo(f"Hello, {name}!")
```

See how the configuration option is grouped with others:

```{click:run}
:emphasize-lines: 6-10
from textwrap import dedent
result = invoke(hello, args=["--help"])
assert dedent(
    """\
    Cool options: [at least 1 required]
      --foo TEXT              The option that starts it all.
      --bar TEXT              Another important option.
      --hello-conf CONF_FILE  Loads CLI config."""
) in result.output
```

```{caution}
Notice in the example above how the `@command()` decorator from Cloup is used with parenthesis. Contrary to Click and Click Extra, [Cloup requires parenthesis on its decorators](https://github.com/janluke/cloup/issues/127).
```

## Available options

Click Extra provides these additional, pre-configured options decorators you can use standalone. Some of them are [included by default in the `@extra_command` and `@extra_group`](commands.md#click_extra.commands.default_extra_params) decorators (see the last column):

| Decorator |  Specification | Default |
|-----------|----------------| ----|
| [`@timer_option`](timer.md) | `--time / --no-time` | ✅ |
| [`@color_option`](colorize.md#color-option)   | `--color, --ansi / --no-color, --no-ansi` | ✅ |
| [`@config_option`](config.md#standalone-option) | `--config CONFIG_PATH` | ✅ |
| [`@no_config_option`](config.md#) | `--no-config` | ✅ |
| [`@show_params_option`](parameters.md#show-params-option) | `--show-params` | ✅ |
| [`@table_format_option`](table.md) | `--table-format FORMAT` | ✅ |
| [`@verbosity_option`](logging.md#colored-verbosity) | `--verbosity LEVEL` | ✅ |
| [`@verbose_option`](logging.md#click_extra.logging.VerboseOption) | `-v, --verbose` | ✅ |
| [`@version_option`](version.md)| `--version` | ✅ |
| [`@help_option`](colorize.md#click_extra.colorize.HelpExtraFormatter) | `-h, --help` | ✅ |
| [`@telemetry_option`](click_extra.md#module-click_extra.telemetry) | `--telemetry / --no-telemetry` |❌|

```{note}
Because single-letter options are a scarce resource, Click Extra does not impose them on you. All the options above are specified with their long names only. You can always customize them to add a short name if you wish.

That's a general rule, unless some short names follow a widely-accepted convention or an overwhelmingly-followed tradition. Which is the case for `-v, --verbose` and `-h, --help`.
```

````{tip}
If you find the `click_extra` namespace too long to type, you can always alias it to something shorter.

A popular choice is `clickx`:

```{code-block} python
:emphasize-lines: 2,7
import click
import click_extra as clickx


@click.command
@click.option("--foo")
@clickx.config_option
def first(foo): ...
```
````