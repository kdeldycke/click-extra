# Tutorial

This tutorial details how we transformed the [canonical `click` example](https://github.com/pallets/click#a-simple-example):

![click CLI help screen](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/click-help-screen.png)

Into this:

![click-extra CLI help screen](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/click-extra-screen.png)

## All bells and whistles

The [canonical `click` example](https://github.com/pallets/click#a-simple-example) is implemented that way:

```{eval-rst}
.. click:example::
    from click import command, echo, option

    @command
    @option("--count", default=1, help="Number of greetings.")
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello(count, name):
        """Simple program that greets NAME for a total of COUNT times."""
        for _ in range(count):
            echo(f"Hello, {name}!")

Whose help screen renders as:

.. click:run::
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

To augment the simple example above with [all the bells and whistles](index.md#features) `click-extra` has in store, you just need to replace the base command decorator with its `extra_`-prefixed variant:

```{eval-rst}
.. click:example::
    from click_extra import extra_command, echo, option

    @extra_command
    @option("--count", default=1, help="Number of greetings.")
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello(count, name):
        """Simple program that greets NAME for a total of COUNT times."""
        for _ in range(count):
            echo(f"Hello, {name}!")

And now you get:

.. click:run::
    from textwrap import dedent
    result = invoke(hello, args=["--help"])
    assert result.output.startswith(dedent("""\
        \x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mhello\x1b[0m \x1b[36m\x1b[2m[OPTIONS]\x1b[0m

          Simple program that greets NAME for a total of COUNT times.

        \x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m
          \x1b[36m--count\x1b[0m \x1b[36m\x1b[2mINTEGER\x1b[0m           Number of greetings.  \x1b[2m[\x1b[0m\x1b[2mdefault: \x1b[0m\x1b[32m\x1b[2m\x1b[3m1\x1b[0m\x1b[2m]\x1b[0m
          \x1b[36m--name\x1b[0m \x1b[36m\x1b[2mTEXT\x1b[0m               The person to greet.
        """
    ))
```

That's it!

Here is a highlight of the only changes between the two versions:

```diff
-from click import command, echo, option
+from click_extra import extra_command, echo, option

-@command
+@extra_command
 @option("--count", default=1, help="Number of greetings.")
 @option("--name", prompt="Your name", help="The person to greet.")
 def hello(count, name):
     """Simple program that greets NAME for a total of COUNT times."""
     for _ in range(count):
         echo(f"Hello, {name}!")
```

```{tip}
As you can see above, `click_extra` is proxy-ing the whole `click` namespace, so you can use it as a [drop-in replacement](tutorial.md#drop-in-replacement).
```

## Standalone options

If you do not like the opiniated way the `@extra_command` decorator is built with all its defaults options, you are still free to pick them up independently.

If, for example, you're only interested in using the `--config` option, nothing prevents you to use it with a standard `click` CLI:

```{eval-rst}
.. click:example::
    from click import command, echo, option
    from click_extra import config_option

    @command
    @option("--count", default=1, help="Number of greetings.")
    @option("--name", prompt="Your name", help="The person to greet.")
    @config_option
    def hello(count, name):
        """Simple program that greets NAME for a total of COUNT times."""
        for _ in range(count):
            echo(f"Hello, {name}!")

Which now renders to:

.. click:run::
    result = invoke(hello, args=["--help"])
    assert "-C, --config CONFIG_PATH" in result.output
```

This option itself behave like any Click option and can be customized easily:

```{eval-rst}
.. click:example::
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

.. click:run::
    result = invoke(hello, args=["--help"])
    assert "--hello-conf CONF_FILE  Loads CLI config." in result.output
```

Click Extra's options are sub-classes of Cloup's and supports all its features, like [option groups](https://cloup.readthedocs.io/en/stable/pages/option-groups.html):

```{eval-rst}
.. click:example::
    from click import echo
    from cloup import command, option, option_group
    from cloup.constraints import RequireAtLeast
    from click_extra import config_option

    @command()
    @option("--count", default=1, help="Number of greetings.")
    @option("--name", prompt="Your name", help="The person to greet.")
    @option_group(
        "Cool options",
        option("--foo", help="The option that starts it all."),
        option("--bar", help="Another important option."),
        config_option("--hello-conf", metavar="CONF_FILE", help="Loads CLI config."),
        constraint=RequireAtLeast(1),
    )
    def hello(count, name, foo, bar, hello_conf):
        """Simple program that greets NAME for a total of COUNT times."""
        for _ in range(count):
            echo(f"Hello, {name}!")

See how the configuration option is grouped with others:

.. click:run::
    from textwrap import dedent
    result = invoke(hello, args=["--help"])
    assert dedent(
        """\
        Cool options: [at least 1 required]
          --foo TEXT              The option that starts it all.
          --bar TEXT              Another important option.
          --hello-conf CONF_FILE  Loads CLI config.
        """
    ) in result.output
```

```{caution}
Notice in the example above how the `@command()` decorator from Cloup is used with parenthesis. Contrary to Click and Click Extra, [Cloup requires parenthesis on its decorators](https://github.com/janluke/cloup/issues/127).
```

```{seealso}
Click Extra provides these additional options:

- [`color_option`](colorize.md#color-option)
- [`config_option`](config.md)
- [`help_option`](colorize.md#help-option)
- [`show_params_option`](config.md#show-params-option)
- [`table_format_option`](tabulate.md)
- [`timer_option`](timer.md)
- [`verbosity_option`](logging.md)
- [`version_option`](colorize.md#version-option)
```
