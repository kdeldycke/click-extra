# Tutorial

This tutorial details how we transformed the [canonical `click` example](https://github.com/pallets/click#a-simple-example):

![click CLI help screen](https://github.com/kdeldycke/click-extra/raw/main/docs/images/click-help-screen.png)

Into this:

![click-extra CLI help screen](https://github.com/kdeldycke/click-extra/raw/main/docs/images/click-extra-screen.png)

## All bells and whistles

The [canonical `click` example](https://github.com/pallets/click#a-simple-example) is implemented that way:

```{eval-rst}
.. click:example::
    from click import command, echo, option

    @command()
    @option("--count", default=1, help="Number of greetings.")
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello(count, name):
        """Simple program that greets NAME for a total of COUNT times."""
        for _ in range(count):
            echo(f"Hello, {name}!")

Whose help screen renders as:

.. click:run::
   invoke(hello, args=["--help"])
```

To augment the simple example above with [all the bells and whistles](index#features) `click-extra` has in store, you just need to replace the base command decorator with its `extra_`-prefixed variant:

```{eval-rst}
.. click:example::
    from click_extra import extra_command, echo, option

    @extra_command()
    @option("--count", default=1, help="Number of greetings.")
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello(count, name):
        """Simple program that greets NAME for a total of COUNT times."""
        for _ in range(count):
            echo(f"Hello, {name}!")

And now you get:

.. click:run::
   invoke(hello, args=["--help"])
```

That's it!

Here is a highlight of the only changes between the two versions:

```diff
-from click import command, echo, option
+from click_extra import extra_command, echo, option

-@command()
+@extra_command()
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

If you do not like the opiniated way the `@extra_command()` decorator is built with all its defaults options, you are still free to pick them up independently.

If, for example, you're only interested in using the `--config` option, nothing prevents you to use it with a standard `click` CLI:

```{eval-rst}
.. click:example::
    from click import command, echo, option
    from click_extra import config_option

    @command()
    @option("--count", default=1, help="Number of greetings.")
    @option("--name", prompt="Your name", help="The person to greet.")
    @config_option()
    def hello(count, name):
        """Simple program that greets NAME for a total of COUNT times."""
        for _ in range(count):
            echo(f"Hello, {name}!")

Which now renders to:

.. click:run::
   invoke(hello, args=["--help"])
```

This option itself behave like any Click option and can be customized easely:

```{eval-rst}
.. click:example::
    from click import command, echo, option
    from click_extra import config_option

    @command()
    @option("--count", default=1, help="Number of greetings.")
    @option("--name", prompt="Your name", help="The person to greet.")
    @config_option("--hello-conf", metavar="CONF_FILE", help="Loads CLI config.")
    def hello(count, name):
        """Simple program that greets NAME for a total of COUNT times."""
        for _ in range(count):
            echo(f"Hello, {name}!")

.. click:run::
   invoke(hello, args=["--help"])
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
   invoke(hello, args=["--help"])
```

```{seealso}
Click Extra provides these additional options:

- [`color_option`](colorize.md#color-option)
- [`config_option`](config.md)
- [`help_option`](colorize.md#help-option)
- [`show_params_option`](config.md#show-params-option)
- [`table_format_option`](tabulate.md)
- [`timer_option`](commands.md#timer-option)
- [`verbosity_option`](logging.md)
- [`version_option`](colorize.md#version-option)
```
