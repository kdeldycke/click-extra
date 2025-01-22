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
- color the log's level name in the `{levelname}` variable,
```

```{eval-rst}
.. caution::

   Because ``root`` is the default logger associated with ``--verbosity``, its **level is propagated to all other loggers**. Including those you may have created yourself:

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

         # Use my custom logger.
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

If you'd like to target another logger than the default `root`, you can pass [your own logger](https://docs.python.org/3/library/logging.html?#logging.getLogger)'s ID to the option parameter:

```{eval-rst}
.. click:example::
    import logging
    from click import command
    from click_extra import verbosity_option

    @command
    @verbosity_option(default_logger="app_logger")
    def custom_logger():
        # Default root logger.
        logging.warning("Root warning message")
        logging.info("Root info message")

        # My custom logger.
        my_logger = logging.getLogger("app_logger")
        my_logger.warning("My warning message")
        my_logger.info("My info message")

You can now check that ``--verbosity`` only influence the level of ``app_logger``. See how the ``root`` logger is only printing at its default ``WARNING`` level, while ``app_logger``'s level is set to ``INFO``:

.. click:run::
   from textwrap import dedent
   result = invoke(custom_logger)
   assert dedent("""\
      \x1b[33mwarning\x1b[0m: Root warning message
      \x1b[33mwarning\x1b[0m: My warning message
      \x1b[33mwarning\x1b[0m: My warning message
      """
      ) in result.output

.. click:run::
   from textwrap import dedent
   result = invoke(custom_logger, args=["--verbosity", "INFO"])
   assert dedent("""\
      \x1b[33mwarning\x1b[0m: Root warning message
      \x1b[33mwarning\x1b[0m: My warning message
      \x1b[33mwarning\x1b[0m: My warning message
      info: My info message
      info: My info message
      """
      ) in result.output
```

```{eval-rst}
.. danger::

   In the example above, you can right away notice an issue: ``app_logger``'s **messages are displayed twice**.

   That's because `new logger are always created as a sub-logger <https://github.com/python/cpython/blob/a3797492179c249417a06d2499a7d535d453ac2c/Doc/library/logging.rst?plain=1#L70-L71>`_ of ``root``. And as such, their messages are propagated to it.

   To fix this issue, you have to explicitely `disable the propagation of messages <https://docs.python.org/3/library/logging.html#logging.Logger.propagate>`_:

   .. click:example::
      import logging
      from click import command
      from click_extra import verbosity_option

      @command
      @verbosity_option(default_logger="app_logger")
      def custom_logger():
         # Default root logger.
         logging.warning("Root warning message")
         logging.info("Root info message")

         # My custom logger.
         my_logger = logging.getLogger("app_logger")
         my_logger.propagate = False
         my_logger.warning("My warning message")
         my_logger.info("My info message")

   Which get rids of the duplicate messages:

   .. click:run::
      from textwrap import dedent
      result = invoke(custom_logger, args=["--verbosity", "INFO"])
      assert dedent("""\
         \x1b[33mwarning\x1b[0m: Root warning message
         \x1b[33mwarning\x1b[0m: My warning message
         info: My info message
         """
         ) in result.output
```

```{eval-rst}
.. tip::
   As an alternative, you can pass the logger object directly to the option:

   .. click:example::
      import logging
      from click import command
      from click_extra import verbosity_option

      my_logger = logging.getLogger("app_logger")
      my_logger.propagate = False

      @command
      @verbosity_option(default_logger=my_logger)
      def custom_logger():
         # Default root logger.
         logging.warning("Root warning message")
         logging.info("Root info message")

         # My custom logger.
         my_logger.warning("My warning message")
         my_logger.info("My info message")

   .. click:run::
      from textwrap import dedent
      result = invoke(custom_logger, args=["--verbosity", "INFO"])
      assert dedent("""\
         \x1b[33mwarning\x1b[0m: Root warning message
         \x1b[33mwarning\x1b[0m: My warning message
         info: My info message
         """
         ) in result.output
```

### Logger configuration

The Python standard library provides the [`logging.basicConfig`](https://docs.python.org/3/library/logging.html?#logging.basicConfig) function, which is a helper to simplify the configuration of loggers and covers most use cases.

Click Extra has a similar helper: [`click_extra.logging.extra_basic_config`](#click_extra.logging.extra_basic_config).

This will allow you to change the default logger's configuration, like the message format. All you have to do is to pass it to the verbosity option:

```{eval-rst}
.. click:example::
    import logging
    from click import command
    from click_extra import extra_basic_config, verbosity_option

    custom_logger = extra_basic_config(format="{levelname} | {name} | {message}")

    @command
    @verbosity_option(default_logger=custom_logger)
    def custom_root_logger_cli():
        # Call the root logger directly.
        logging.warning("Root logger warning")
        logging.info("Root logger info")

        # Use our custom logger.
        custom_logger.warning("Custom warning")
        custom_logger.info("Custom info")

And see how logs messages are rendered with the new format:

.. click:run::
   from textwrap import dedent
   result = invoke(custom_root_logger_cli)
   assert dedent("""\
      \x1b[33mwarning\x1b[0m | root | Root logger warning
      \x1b[33mwarning\x1b[0m | root | Custom warning
      """
   ) in result.output

.. click:run::
   from textwrap import dedent
   result = invoke(custom_root_logger_cli, args=["--verbosity", "INFO"])
   assert dedent("""\
      \x1b[33mwarning\x1b[0m | root | Root logger warning
      info | root | Root logger info
      \x1b[33mwarning\x1b[0m | root | Custom warning
      info | root | Custom info
      """
   ) in result.output

   # XXX Reset root logger because "click:run" directives are not isolated and custom config polute the next examples.
   extra_basic_config()
```

Now the reason all messages are rendered with the new format is that `extra_basic_config` is a global configuration. It affects the default `root` logger by default, and all loggers that inherit from it.

```{eval-rst}
.. hint::
   You can creatively configure loggers to produce any kind of messages, like this JSON-like format:

   .. click:example::
      import logging
      from click import command
      from click_extra import extra_basic_config, verbosity_option

      json_logger = extra_basic_config(
         format='{{"time": "{asctime}", "name": "{name}", "level": "{levelname}", "msg": "{message}"}}',
      )

      @command
      @verbosity_option(default_logger=json_logger)
      def json_logs():
         logging.info("This is an info message from the root logger.")

   .. click:run::
      from textwrap import dedent
      result = invoke(json_logs, args=["--verbosity", "INFO"])
      assert result.output.endswith(
         '", "name": "root", "level": "info", "msg": "This is an info message from the root logger."}\n'
      )

      # XXX Reset root logger because "click:run" directives are not isolated and custom config polute the next examples.
      extra_basic_config()
```

````{todo}
Make the passing of the logger object to the verbosity option optional if it targets the `root` logger, so we can do:

```python
extra_basic_config(...)

@command
@verbosity_option
def custom_logger(): ...
```
````

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