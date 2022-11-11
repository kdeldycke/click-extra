# Logging

Here is an example on how to [use your own logger](https://docs.python.org/3/library/logging.html?#logging.getLogger), in this case Python's default `root` logger:

```{eval-rst}
.. click:example::
   import logging

   import click_extra
   from click_extra import extra_command, VerbosityOption, echo

   @extra_command(
      params=[
         VerbosityOption(logging.getLogger(), default="DEBUG"),
      ]
   )
   def cli():
      echo("--- Defaults ---")
      logging.warning("logging at warning level")
      logging.info("logging at info level")
      logging.debug("logging at debug level")

      echo("\n--- Click Extra's logger object ---")
      echo(click_extra.logging.logger)
      echo(click_extra.logging.logger.level)

      echo("\n--- Python's root logger ---")
      echo(logging.getLogger())
      echo(logging.getLogger().level)

      echo("\n--- Manual settings ---")
      logging.getLogger().setLevel("INFO")
      logging.warning("logging at warning level")
      logging.info("logging at info level")
      logging.debug("logging at debug level")

Which produces:

.. click:run::
   invoke(cli)
```

## `click_extra.logging` API

```{eval-rst}
.. automodule:: click_extra.logging
   :members:
   :undoc-members:
   :show-inheritance:
```
