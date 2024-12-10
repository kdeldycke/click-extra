# Logging

## Colored verbosity option

Click Extra provides a pre-configured option which adds a `--verbosity`/`-v` flag to your CLI. It allow users of your CLI to set the log level of a [`logging.Logger` instance](https://docs.python.org/3/library/logging.html#logger-objects).

### Integrated extra option

This option is by default part of `@extra_command` and `@extra_group`:

```{eval-rst}
.. click:example::
    from click_extra import extra_command, echo

    @extra_command
    def my_cli():
        echo("It works!")

See how ``--verbosity``/``-v`` option in featured in the help screen:

.. click:run::
   result = invoke(my_cli, args=["--help"])
   assert "--verbosity" in result.stdout, "missing --verbosity option"

This option can be invoked to display all the gory details of your CLI with the ``DEBUG`` level:

.. click:run::
   result = invoke(my_cli, args=["--verbosity", "DEBUG"])
   assert "Set <Logger click_extra (DEBUG)> to DEBUG." in result.stderr, "missing DEBUG message"
   assert "Set <RootLogger root (DEBUG)> to DEBUG." in result.stderr, "missing DEBUG message"
```

### Standalone option

The verbosity option can be used independently of `@extra_command`, and you can attach it to a vanilla Click commands:

```{eval-rst}
.. click:example::
    import logging
    from click import command, echo
    from click_extra import verbosity_option

    @command
    @verbosity_option
    def vanilla_command():
        echo("It works!")
        logging.debug("We're printing stuff.")

.. click:run::
   result = invoke(vanilla_command, args=["--help"])
   assert "-v, --verbosity LEVEL  Either CRITICAL, ERROR, WARNING, INFO, DEBUG." in result.stdout, "missing --verbosity option"

.. click:run::
   result = invoke(vanilla_command)
   assert result.stdout == "It works!\n"
   assert not result.stderr

.. click:run::
   result = invoke(vanilla_command, args=["--verbosity", "DEBUG"])
   assert result.stdout == "It works!\n"
   assert "We're printing stuff." in result.stderr
```

```{hint}
Notice how, in the output above, the verbosity option is automatticcaly printing its own log level as a debug message.
```

### Default logger

The `--verbosity` option force its value to the [Python's global `root` logger](https://github.com/python/cpython/blob/a59dc1fb4324589427c5c84229eb2c0872f29ca0/Lib/logging/__init__.py#L1945).

This is a quality-of-life behavior that allows you to use module-level helpers like [`logging.debug`](https://docs.python.org/3/library/logging.html?highlight=logging#logging.Logger.debug). That way you don't have to worry about setting up your own logger. And logging messages can be easily produced with minimal code:

```{eval-rst}
.. click:example::
    import logging
    from click import command
    from click_extra import verbosity_option

    @command
    @verbosity_option
    def my_cli():
        # Print a message for each level.
        logging.debug("We're printing stuff.")
        logging.info("This is a message.")
        logging.warning("Mad scientist at work!")
        logging.error("Does not compute.")
        logging.critical("Complete meltdown!")

By default the ``--verbosity`` option print all ``WARNING`` messages and levels above:

.. click:run::
   from textwrap import dedent
   result = invoke(my_cli)
   assert result.stderr == dedent("""\
      \x1b[33mwarning\x1b[0m: Mad scientist at work!
      \x1b[31merror\x1b[0m: Does not compute.
      \x1b[31m\x1b[1mcritical\x1b[0m: Complete meltdown!
      """
   )

And now see how each level selectively print messages and renders them with colors:

.. click:run::
   from textwrap import dedent
   result = invoke(my_cli, args=["--verbosity", "CRITICAL"])
   assert result.stderr == "\x1b[31m\x1b[1mcritical\x1b[0m: Complete meltdown!\n"

.. click:run::
   from textwrap import dedent
   result = invoke(my_cli, args=["--verbosity", "ERROR"])
   assert result.stderr == dedent("""\
      \x1b[31merror\x1b[0m: Does not compute.
      \x1b[31m\x1b[1mcritical\x1b[0m: Complete meltdown!
      """
   )

.. click:run::
   from textwrap import dedent
   result = invoke(my_cli, args=["--verbosity", "WARNING"])
   assert result.stderr == dedent("""\
      \x1b[33mwarning\x1b[0m: Mad scientist at work!
      \x1b[31merror\x1b[0m: Does not compute.
      \x1b[31m\x1b[1mcritical\x1b[0m: Complete meltdown!
      """
   )

.. click:run::
   from textwrap import dedent
   result = invoke(my_cli, args=["--verbosity", "INFO"])
   assert result.stderr == dedent("""\
      info: This is a message.
      \x1b[33mwarning\x1b[0m: Mad scientist at work!
      \x1b[31merror\x1b[0m: Does not compute.
      \x1b[31m\x1b[1mcritical\x1b[0m: Complete meltdown!
      """
   )

.. click:run::
   from textwrap import dedent
   result = invoke(my_cli, args=["--verbosity", "DEBUG"])
   assert result.stderr == dedent("""\
      \x1b[34mdebug\x1b[0m: Set <Logger click_extra (DEBUG)> to DEBUG.
      \x1b[34mdebug\x1b[0m: Set <RootLogger root (DEBUG)> to DEBUG.
      \x1b[34mdebug\x1b[0m: We're printing stuff.
      info: This is a message.
      \x1b[33mwarning\x1b[0m: Mad scientist at work!
      \x1b[31merror\x1b[0m: Does not compute.
      \x1b[31m\x1b[1mcritical\x1b[0m: Complete meltdown!
      \x1b[34mdebug\x1b[0m: Reset <RootLogger root (DEBUG)> to WARNING.
      \x1b[34mdebug\x1b[0m: Reset <Logger click_extra (DEBUG)> to WARNING.
      """
   )
```

```{hint}
`--verbosity` default behavior is to:

- output to `<stderr>`,
- send messages via the `root` logger,
- show `WARNING`-level messages and above,
- render logs with the `%(levelname)s: %(message)s` format,
- color the log's level name in the `%(levelname)s` variable,
```

```{eval-rst}
.. attention:: Level propagation

   Because the default logger associated to the ``--verbosity`` option is ``root``, its level is propagated to all other loggers, including those you may have created yourself:

   .. click:example::
      import logging
      from click import command, echo
      from click_extra import verbosity_option

      @command
      @verbosity_option
      def multiple_loggers():
         # Use the root default logger.
         root_logger = logging.getLogger()
         root_logger.warning("Default informative message")
         root_logger.debug("Default debug message")

         # Use my custom standalone logger.
         my_logger = logging.getLogger("my_logger")
         my_logger.warning("Random informative message")
         my_logger.debug("Random debug message")

         echo("It works!")

   A normal invocation will only print the default ``WARNING`` messages:

   .. click:run::
      from textwrap import dedent
      result = invoke(multiple_loggers)
      assert result.stdout == "It works!\n"
      assert result.stderr == dedent("""\
         \x1b[33mwarning\x1b[0m: Default informative message
         \x1b[33mwarning\x1b[0m: Random informative message
         """
      )

   And setting verbosity to ``DEBUG`` will print debug messages both from ``root`` and ``my_logger``:

   .. click:run::
      from textwrap import dedent
      result = invoke(multiple_loggers, args=["--verbosity", "DEBUG"])
      assert result.stdout == "It works!\n"
      assert result.stderr == dedent("""\
         \x1b[34mdebug\x1b[0m: Set <Logger click_extra (DEBUG)> to DEBUG.
         \x1b[34mdebug\x1b[0m: Set <RootLogger root (DEBUG)> to DEBUG.
         \x1b[33mwarning\x1b[0m: Default informative message
         \x1b[34mdebug\x1b[0m: Default debug message
         \x1b[33mwarning\x1b[0m: Random informative message
         \x1b[34mdebug\x1b[0m: Random debug message
         \x1b[34mdebug\x1b[0m: Reset <RootLogger root (DEBUG)> to WARNING.
         \x1b[34mdebug\x1b[0m: Reset <Logger click_extra (DEBUG)> to WARNING.
         """
      )

   To prevent this behavior, you can setup the verbosity option to target a custom logger, other than the default ``root`` logger. This is explained in the next section.
```

### Customize default logger

You can generate a new `root` logger in the style of Click Extra with the [`extra_basic_config()` helper](#click_extra.logging.extra_basic_config).

So if you want to change the default logger's configuration, you can create a custom logger and pass it to the verbosity option:

```{eval-rst}
.. click:example::
    import logging
    from click import command
    from click_extra import extra_basic_config, verbosity_option

    custom_root_logger = extra_basic_config(
        format="{levelname} | {name} | {message}",
    )

    @command
    @verbosity_option(default_logger=custom_root_logger)
    def custom_root_logger_cli():
        # Call the root logger directly.
        logging.warning("Root logger warning")
        logging.debug("Root logger debug")
        logging.info("Root logger info")
        # Use our custom logger object.
        custom_root_logger.warning("Logger object warning")
        custom_root_logger.debug("Logger object debug")
        custom_root_logger.info("Logger object info")

And see how logs messages are rendered with the custom format, whichever calling method you use:

.. click:run::
   from textwrap import dedent
   result = invoke(custom_root_logger_cli)
   assert dedent("""\
      \x1b[33mwarning\x1b[0m | root | Root logger warning
      \x1b[33mwarning\x1b[0m | root | Logger object warning
      """
   ) in result.output

.. click:run::
   from textwrap import dedent
   result = invoke(custom_root_logger_cli, args=["--verbosity", "DEBUG"])
   assert dedent("""\
      \x1b[33mwarning\x1b[0m | root | Root logger warning
      \x1b[34mdebug\x1b[0m | root | Root logger debug
      info | root | Root logger info
      \x1b[33mwarning\x1b[0m | root | Logger object warning
      \x1b[34mdebug\x1b[0m | root | Logger object debug
      info | root | Logger object info
      """
   ) in result.output
```

````{todo}
Make the passing of the logger object to the verbosity option optional if it targets the root logger, so we can do:

```python
extra_basic_config(...)


@command
@verbosity_option
def custom_logger(): ...
```
````

### Custom logger

If you'd like to target another logger than the default `root` logger, you can pass [your own logger](https://docs.python.org/3/library/logging.html?#logging.getLogger)'s ID to the option parameter:

```{eval-rst}
.. click:example::
    import logging
    from click import command, echo
    from click_extra import extra_basic_config, verbosity_option

    # Create a custom logger in the style of Click Extra, with our own format message.
    extra_basic_config(
        logger_name="app_logger",
        format="{levelname} | {name} | {message}",
    )

    @command
    @verbosity_option(default_logger="app_logger")
    def awesome_app():
        echo("Awesome App started")
        logger = logging.getLogger("app_logger")
        logger.debug("Awesome App has started.")

You can now check that the ``--verbosity`` option influence the log level of your own ``app_logger`` global logger:

.. click:run::
   invoke(awesome_app)

.. click:run::
   from textwrap import dedent
   result = invoke(awesome_app, args=["--verbosity", "DEBUG"])
   assert dedent("""\
      Awesome App started
      \x1b[34mdebug\x1b[0m | app_logger | Awesome App has started.
      \x1b[34mdebug\x1b[0m: Awesome App has started.
      """
      ) in result.output
```

You can also pass the default logger object to the option:

```{eval-rst}
.. click:example::
    import logging
    from click import command, echo
    from click_extra import verbosity_option

    my_app_logger = logging.getLogger("app_logger")

    @command
    @verbosity_option(default_logger=my_app_logger)
    def awesome_app():
        echo("Awesome App started")
        logger = logging.getLogger("app_logger")
        logger.debug("Awesome App has started.")

.. click:run::
   from textwrap import dedent
   result = invoke(awesome_app, args=["--verbosity", "DEBUG"])
   assert dedent("""\
      Awesome App started
      \x1b[34mdebug\x1b[0m | app_logger | Awesome App has started.
      \x1b[34mdebug\x1b[0m: Awesome App has started.
      """
      ) in result.output
```

### Custom configuration

The Python standard library provides the [`logging.basicConfig`](https://docs.python.org/3/library/logging.html?#logging.basicConfig) function, which is a helper to simplify the configuration of loggers and covers most use cases.

Click Extra provides a similar helper, [`click_extra.logging.extra_basic_config`](#click_extra.logging.extra_basic_config).

```{todo}
Write detailed documentation of `extra_basic_config()`.
```

### Get verbosity level

You can get the name of the current verbosity level from the context or the logger itself:

```{eval-rst}
.. click:example::
    import logging
    from click_extra import command, echo, pass_context, verbosity_option

    @command
    @verbosity_option
    @pass_context
    def vanilla_command(ctx):
        level_from_context = ctx.meta["click_extra.verbosity"]
        echo(f"Level from context: {level_from_context}")

        level_from_logger = logging._levelToName[logging.getLogger().getEffectiveLevel()]
        echo(f"Level from logger: {level_from_logger}")

.. click:run::
   result = invoke(vanilla_command, args=["--verbosity", "DEBUG"])
```

## Internal `click_extra` logger

```{todo}
Write docs!
```

## `click_extra.logging` API

```{eval-rst}
.. autoclasstree:: click_extra.logging
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.logging
   :members:
   :undoc-members:
   :show-inheritance:
```
