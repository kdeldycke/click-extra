# Logging

The Python's standard library logging module is a bit tricky to use. Click Extra provides pre-configured helpers with sane defaults to simplify the logging configuration.

## Colored `--verbosity` option

Click Extra provides a pre-configured option which adds a `--verbosity`/`-v` flag to your CLI. It allow users of your CLI to set the log level of a [`logging.Logger` instance](https://docs.python.org/3/library/logging.html#logger-objects).

### Integrated option

This option is part of `@extra_command` and `@extra_group` by default:

```{eval-rst}
.. click:example::
    from click_extra import extra_command, echo

    @extra_command
    def my_cli():
        echo("It works!")

See how ``--verbosity``/``-v`` option is featured in the help screen:

.. click:run::
   result = invoke(my_cli, args=["--help"])
   assert "--verbosity" in result.stdout, "missing --verbosity option"

This option can be invoked to display all the gory details of your CLI with the ``DEBUG`` level:

.. click:run::
   result = invoke(my_cli, args=["--verbosity", "DEBUG"])
   assert "Set <Logger click_extra (DEBUG)> to DEBUG." in result.stderr, "missing DEBUG message"
   assert "Set <RootLogger root (DEBUG)> to DEBUG." in result.stderr, "missing DEBUG message"
```

```{hint}
Notice how, in the output above, the verbosity option is printing the levels of loggers as a debug messages.
```

### Standalone option

The verbosity option can be used independently of `@extra_command`, and you can attach it to a vanilla Click command:

```{eval-rst}
.. click:example::
    import logging
    from click import command, echo
    from click_extra import verbosity_option

    @command
    @verbosity_option
    def vanilla_command():
        echo("It works!")
        logging.info("We're printing stuff.")

.. click:run::
   result = invoke(vanilla_command, args=["--help"])
   assert "-v, --verbosity LEVEL  Either CRITICAL, ERROR, WARNING, INFO, DEBUG." in result.stdout, "missing --verbosity option"

.. click:run::
   result = invoke(vanilla_command)
   assert result.stdout == "It works!\n"
   assert not result.stderr

.. click:run::
   result = invoke(vanilla_command, args=["--verbosity", "INFO"])
   assert result.stdout == "It works!\n"
   assert "We're printing stuff." in result.stderr
```

### Default logger

The `--verbosity` option is by default attached to the [global `root` logger](https://github.com/python/cpython/blob/a59dc1fb4324589427c5c84229eb2c0872f29ca0/Lib/logging/__init__.py#L1945).

This allows you to use module-level helpers like [`logging.debug`](https://docs.python.org/3/library/logging.html?highlight=logging#logging.Logger.debug). That way you don't have to worry about setting up your own logger. And logging messages can be easily produced with minimal code:

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

The ``--verbosity`` option print by default all messages at the ``WARNING`` level and above:

.. click:run::
   from textwrap import dedent
   result = invoke(my_cli)
   assert result.stderr == dedent("""\
      \x1b[33mwarning\x1b[0m: Mad scientist at work!
      \x1b[31merror\x1b[0m: Does not compute.
      \x1b[31m\x1b[1mcritical\x1b[0m: Complete meltdown!
      """
   )

But each level can be selected with the option:

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
- use `{`-style (curly braces) for format strings,
- render logs with the `{levelname}: {message}` format,
- color the log's level name in the `{levelname}` variable.
```

```{eval-rst}
.. caution::

   Because ``root`` is the default logger associated with ``--verbosity``, its **display level is inherited by other loggers**. Including those you may have independently created yourself:

   .. click:example::
      import logging
      from click import command
      from click_extra import verbosity_option

      @command
      @verbosity_option
      def multiple_loggers():
         # Use the default root logger.
         root_logger = logging.getLogger()
         root_logger.warning("Root warning message")
         root_logger.info("Root info message")

         # Create a custom logger and use it.
         my_logger = logging.getLogger("my_logger")
         my_logger.warning("My warning message")
         my_logger.info("My info message")

   A normal invocation will only print the default ``WARNING`` messages:

   .. click:run::
      from textwrap import dedent
      result = invoke(multiple_loggers)
      assert result.stderr == dedent("""\
         \x1b[33mwarning\x1b[0m: Root warning message
         \x1b[33mwarning\x1b[0m: My warning message
         """
      )

   But calling ``--verbosity INFO`` will print both ``root`` and ``my_logger`` messages of that level:

   .. click:run::
      from textwrap import dedent
      result = invoke(multiple_loggers, args=["--verbosity", "INFO"])
      assert result.stderr == dedent("""\
         \x1b[33mwarning\x1b[0m: Root warning message
         info: Root info message
         \x1b[33mwarning\x1b[0m: My warning message
         info: My info message
         """
      )

   To prevent this behavior, you can associate the ``--verbosity`` option with your own custom logger. This is explained in the next section.
```

### Custom logger

The preferred way to customize log messages is to create your own logger and attach the `--verbosity` option to it.

This can be done with [`click_extra.logging.new_extra_logger`](#click_extra.logging.new_extra_logger). Here is how we can for example change the format of the log messages:

```{eval-rst}
.. click:example::
    import logging
    from click import command
    from click_extra import new_extra_logger, verbosity_option

    new_extra_logger(
      name="app_logger",
      format="{levelname} | {name} | {message}"
    )

    @command
    @verbosity_option(default_logger="app_logger")
    def custom_logger_cli():
        # Call the root logger directly.
        logging.warning("Root logger warning")
        logging.info("Root logger info")

        # Use our custom logger.
        my_logger = logging.getLogger("app_logger")
        my_logger.warning("Custom warning")
        my_logger.info("Custom info")

And so by default, the ``root`` logger keeps its default format, while the custom logger uses the new one:

.. click:run::
   from textwrap import dedent
   result = invoke(custom_logger_cli)
   assert dedent("""\
      \x1b[33mwarning\x1b[0m: Root logger warning
      \x1b[33mwarning\x1b[0m | app_logger | Custom warning
      """
   ) in result.output

And changing the verbosity level will only affect the custom logger:

.. click:run::
   from textwrap import dedent
   result = invoke(custom_logger_cli, args=["--verbosity", "INFO"])
   assert dedent("""\
      \x1b[33mwarning\x1b[0m: Root logger warning
      \x1b[33mwarning\x1b[0m | app_logger | Custom warning
      info | app_logger | Custom info
      """
   ) in result.output
```

This is because we explicitely passed the custom logger to the `--verbosity` option. If we didn't passed it, the default `root` logger would have been tied to the `--verbosity` option:

```{eval-rst}
.. click:example::
    import logging
    from click import command
    from click_extra import new_extra_logger, verbosity_option

    new_extra_logger(
      name="app_logger",
      format="{levelname} | {name} | {message}"
    )

    @command
    @verbosity_option
    def root_logger_verbosity():
        # Call the root logger directly.
        logging.warning("Root logger warning")
        logging.info("Root logger info")

        # Use our custom logger.
        my_logger = logging.getLogger("app_logger")
        my_logger.warning("Custom warning")
        my_logger.info("Custom info")

In that case the default behavior doesn't change and messages are rendered in their own logger's format, at the default ``WARNING`` level:

.. click:run::
   from textwrap import dedent
   result = invoke(root_logger_verbosity)
   assert dedent("""\
      \x1b[33mwarning\x1b[0m: Root logger warning
      \x1b[33mwarning\x1b[0m | app_logger | Custom warning
      """
   ) in result.output

And changing the verbosity level only affects the logger attached to ``--verbosity`` (i.e. ``root``), in the opposite of the previous example:

.. click:run::
   from textwrap import dedent
   result = invoke(root_logger_verbosity, args=["--verbosity", "INFO"])
   assert dedent("""\
      \x1b[33mwarning\x1b[0m: Root logger warning
      info: Root logger info
      \x1b[33mwarning\x1b[0m | app_logger | Custom warning
      """
   ) in result.output
```

```{eval-rst}
.. hint::
   You can creatively configure loggers to produce any kind of messages, like this JSON-like format:

   .. click:example::
      import logging
      from click import command
      from click_extra import new_extra_logger, verbosity_option

      new_extra_logger(
         name="json_logger",
         format='{{"time": "{asctime}", "name": "{name}", "level": "{levelname}", "msg": "{message}"}}',
      )

      @command
      @verbosity_option(default_logger="json_logger")
      def json_logs():
         my_logger = logging.getLogger("json_logger")
         my_logger.info("This is an info message.")

   .. click:run::
      from textwrap import dedent
      result = invoke(json_logs, args=["--verbosity", "INFO"])
      assert result.output.endswith(
         '", "name": "json_logger", "level": "info", "msg": "This is an info message."}\n'
      )
```

```{eval-rst}
.. important::

   By design, `new loggers are always created as sub-loggers <https://github.com/python/cpython/blob/a3797492179c249417a06d2499a7d535d453ac2c/Doc/library/logging.rst?plain=1#L70-L71>`_ of ``root``. And as such, their messages are propagated back to it.

   But [`new_extra_logger`](#click_extra.logging.new_extra_logger) is creating new loggers by setting their ``propagate`` attribute to ``False``. This means that messages of new loggers won't be propagated to their parents.

   This is the reason why, in the example above, the ``root`` and ``app_logger`` loggers are independent.

   Let's experiment with that property and set the ``propagate`` attribute to ``True``:

   .. click:example::
      import logging
      from click import command
      from click_extra import new_extra_logger, verbosity_option

      new_extra_logger(
         name="app_logger",
         propagate=True,
         format="{levelname} | {name} | {message}"
      )

      @command
      @verbosity_option
      def custom_logger_propagation():
         # Call the root logger directly.
         logging.warning("Root logger warning")
         logging.info("Root logger info")

         # Use our custom logger.
         my_logger = logging.getLogger("app_logger")
         my_logger.warning("Custom warning")
         my_logger.info("Custom info")

   Here you can immediatly spot the issue with propagation: ``app_logger``'s **messages are displayed twice**. Once in their custom format, and once in the format of the ``root`` logger:

   .. click:run::
      from textwrap import dedent
      result = invoke(custom_logger_propagation)
      assert dedent("""\
         \x1b[33mwarning\x1b[0m: Root logger warning
         \x1b[33mwarning\x1b[0m | app_logger | Custom warning
         \x1b[33mwarning\x1b[0m: Custom warning
         """
      ) in result.output

   .. seealso::

      The reason for that hierarchycal design is to allow for `dot-separated logger names <https://docs.python.org/3/library/logging.html#logger-objects>`_, like ``foo.bar.baz``. Which allows for even more `granular control of loggers by filtering <https://docs.python.org/3/library/logging.html#filter-objects>`_.
```

```{eval-rst}
.. tip::

   Becasue loggers are registered in a global registry, you can set them up in one place and use them in another. The idiomatic approach is to `always refer to them by name <https://docs.python.org/3/library/logging.html#logging.getLogger>`_, like in all examples above.

   But for convenience, you can pass the logger object directly to the option:

   .. click:example::
      import logging
      from click import command
      from click_extra import new_extra_logger, verbosity_option

      my_logger = new_extra_logger(name="app_logger")

      @command
      @verbosity_option(default_logger=my_logger)
      def logger_object():
         # Default root logger.
         logging.warning("Root warning message")
         logging.info("Root info message")

         # My custom logger.
         my_logger.warning("My warning message")
         my_logger.info("My info message")

   .. click:run::
      from textwrap import dedent
      result = invoke(logger_object, args=["--verbosity", "INFO"])
      assert dedent("""\
         \x1b[33mwarning\x1b[0m: Root warning message
         \x1b[33mwarning\x1b[0m: My warning message
         info: My info message
         """
         ) in result.output
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

        level_from_logger = logging._levelToName[logging.getLogger().getEffectiveLevel()]

        echo(f"Level from context: {level_from_context}")
        echo(f"Level from logger: {level_from_logger}")

.. click:run::
   from textwrap import dedent
   result = invoke(vanilla_command, args=["--verbosity", "INFO"])
   assert dedent("""\
      Level from context: INFO
      Level from logger: INFO
      """
   ) in result.output
```

## Internal `click_extra` logger

Click Extra has its own logger, named `click_extra`, which is used to print debug messages to inspect its own internal behavior.

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