# Logging

## Colored verbosity option

Click Extra provides a pre-configured option which adds a `--verbosity`/`-v` flag to your CLI. It allow users of your CLI to set the log level of a [`logging.Logger` instance](https://docs.python.org/3/library/logging.html#logger-objects).

### Integrated extra option

This option is added by default to `@extra_command` and `@extra_group`:

```{eval-rst}
.. click:example::
    from click_extra import extra_command, echo

    @extra_command
    def my_cli():
        echo("It works!")

See the default ``--verbosity``/``-v`` option in the help screen:

.. click:run::
   result = invoke(my_cli, args=["--help"])
   assert "--verbosity" in result.stdout, "missing --verbosity option"

Which can be invoked to display all the gory details of your CLI with the ``DEBUG`` level:

.. click:run::
   result = invoke(my_cli, args=["--verbosity", "DEBUG"])
   assert "Set <Logger click_extra (DEBUG)> to DEBUG." in result.stderr, "missing DEBUG message"
   assert "Set <RootLogger root (DEBUG)> to DEBUG." in result.stderr, "missing DEBUG message"
```

### Standalone option

The verbosity option can be used independently of `@extra_command`, and you can attach it to a vanilla commands:

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

```{tip}
Note in the output above how the verbosity option is automatticcaly printing its own log level as a debug message.
```

### Default logger

By default the `--verbosity` option is setting the log level of [Python's global `root` logger](https://github.com/python/cpython/blob/a59dc1fb4324589427c5c84229eb2c0872f29ca0/Lib/logging/__init__.py#L1945).

That way you can simply use the module helpers like [`logging.debug`](https://docs.python.org/3/library/logging.html?highlight=logging#logging.Logger.debug):

```{eval-rst}
.. click:example::
    import logging
    from click import command
    from click_extra import verbosity_option

    @command
    @verbosity_option
    def my_cli():
        # Print a messages for each level.
        logging.debug("We're printing stuff.")
        logging.info("This is a message.")
        logging.warning("Mad scientist at work!")
        logging.error("Does not compute.")
        logging.critical("Complete meltdown!")

.. hint::

   By default, the ``root`` logger is preconfigured to:

   - output to ``<stderr>``,
   - render log records with the ``%(levelname)s: %(message)s`` format,
   - color the log level name in the ``%(levelname)s`` variable,
   - default to the ``INFO`` level.

You can check these defaults by running the CLI without the ``--verbosity`` option:

.. click:run::
   from textwrap import dedent
   result = invoke(my_cli)
   assert result.stderr == dedent("""\
      \x1b[33mwarning\x1b[0m: Mad scientist at work!
      \x1b[31merror\x1b[0m: Does not compute.
      \x1b[31m\x1b[1mcritical\x1b[0m: Complete meltdown!
      """
   )

And then see how each level selectively print messages and renders with colors:

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

```{eval-rst}
.. attention:: Level propagation

   Because the default logger is ``root``, its level is by default propagated to all other loggers:

   .. click:example::
      import logging
      from click import command, echo
      from click_extra import verbosity_option

      @command
      @verbosity_option
      def multiple_loggers():
         # Print to default root logger.
         root_logger = logging.getLogger()
         root_logger.info("Default informative message")
         root_logger.debug("Default debug message")

         # Print to a random logger.
         random_logger = logging.getLogger("my_random_logger")
         random_logger.info("Random informative message")
         random_logger.debug("Random debug message")

         echo("It works!")

   .. click:run::
      invoke(multiple_loggers)

   .. click:run::
      invoke(multiple_loggers, args=["--verbosity", "DEBUG"])
```

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

Click Extra provides a similar helper, [`click_extra.logging.extra_basic_config`](https://click-extra.readthedocs.io/en/latest/api/logging.html#click_extra.logging.extra_basic_config).

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
