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
   invoke(my_cli, args=["--help"])

Which can be invoked to display all the gory details of your CLI with the ``DEBUG`` level:

.. click:run::
   invoke(my_cli, args=["--verbosity", "DEBUG"])
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
   invoke(vanilla_command, args=["--help"])

.. click:run::
   invoke(vanilla_command)

.. click:run::
   invoke(vanilla_command, args=["--verbosity", "DEBUG"])
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

By default, the ``root`` logger is preconfigured to:

* output to ``<stderr>``,
* render log records with the ``%(levelname)s: %(message)s`` format,
* color the log level name in the ``%(levelname)s`` variable,
* default to the ``INFO`` level.

You can check these defaults by running the CLI without the ``--verbosity`` option:

.. click:run::
   invoke(my_cli)

And then see how each level selectively print messages and renders with colors:

.. click:run::
   invoke(my_cli, args=["--verbosity", "CRITICAL"])

.. click:run::
   invoke(my_cli, args=["--verbosity", "ERROR"])

.. click:run::
   invoke(my_cli, args=["--verbosity", "WARNING"])

.. click:run::
   invoke(my_cli, args=["--verbosity", "INFO"])

.. click:run::
   invoke(my_cli, args=["--verbosity", "DEBUG"])
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
   invoke(awesome_app, args=["--verbosity", "DEBUG"])
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
   invoke(awesome_app, args=["--verbosity", "DEBUG"])
```

```{todo}
Write more documentation about `extra_basic_config()`.
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
