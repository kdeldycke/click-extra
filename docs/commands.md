# Commands and groups

## Drop-in replacement

Click Extra aims to be a drop-in replacement for Click, in which some elements are proxy of either Click or Cloup:

| [Original](https://click.palletsprojects.com/en/8.1.x/api/) | Proxy                        | Target                       |
| ----------------------------------------------------------- | ---------------------------- | ---------------------------- |
| `click.command`                                             | `click_extra.command`        | `cloup.command`              |
| `click.group`                                               | `click_extra.group`          | `cloup.group`                |
| `click.argument`                                            | `click_extra.argument`       | `cloup.argument`             |
| `click.option`                                              | `click_extra.option`         | `cloup.option`               |
| `click.version_option`                                      | `click_extra.version_option` | `click_extra.version_option` |
| `click.help_option`                                         | `click_extra.help_option`    | `click_extra.help_option`    |
| `click.Command`                                             | `click_extra.Command`        | `cloup.Command`              |
| `click.Group`                                               | `click_extra.Group`          | `cloup.Group`                |
| `click.Option`                                              | `click_extra.Option`         | `cloup.Option`               |
| `click.HelpFormatter`                                       | `click_extra.HelpFormatter`  | `cloup.HelpFormatter`        |

All others not in the table above are direct imports from `click.*`. You can inspect how this is implemented in [`click_extra.__init__`](https://github.com/kdeldycke/click-extra/blob/main/click_extra/__init__.py). That way, if you replace the namespace, nothing is supposed to happens.

Here is the [canonical `click` example](https://github.com/pallets/click#a-simple-example) with all elements imported from  `click_extra`:

```{eval-rst}
.. click:example::
    from click_extra import command, echo, option

    @command()
    @option("--count", default=1, help="Number of greetings.")
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello(count, name):
        """Simple program that greets NAME for a total of COUNT times."""
        for _ in range(count):
            echo(f"Hello, {name}!")

As you can see the result does not deviates from the original `click`-based output:

.. click:run::
   invoke(hello, args=["--help"])
```

## Extra variants

Now if you want to benefits from the [features of Click Extra](index#features), you have to use the `extra`-prefixed variants:

| [Original](https://click.palletsprojects.com/en/8.1.x/api/) | Extra variant               |
| ----------------------------------------------------------- | --------------------------- |
| `click.command`                                             | `click_extra.extra_command` |
| `click.group`                                               | `click_extra.extra_group`   |
| `click.Command`                                             | `click_extra.ExtraCommand`  |
| `click.Group`                                               | `click_extra.ExtraGroup`    |
| `click.Option`                                              | `click_extra.ExtraOption`   |

Go to the [example in the tutorial](tutorial) to see how these `extra`-variants are used in place of their originals.

## Default options

The `extra_command` and `extra_group` decorators are [pre-configured with a set of options](click_extra.commands.default_extra_params).

Adding to these decorators the same options it defaults to will end up with duplicate entries (as seen in issue {issue}`232`):

```{eval-rst}
.. click:example::
   from click_extra import extra_command, version_option, config_option, verbosity_option

   @extra_command()
   @version_option(version="0.1")
   @config_option(default="ex.yml")
   @verbosity_option(default="DEBUG")
   def cli():
      pass

See how options are duplicated at the end:

.. click:run::
   invoke(cli, args=["--help"])
```

This is an expected behavior: it allows you to add your own options to the preset of `extra_command` and `extra_group`.

To ovveride this, you can directly provide the base decorator with options via the `params=` argument:

```{eval-rst}
.. click:example::
   from click_extra import extra_command, VersionOption, ConfigOption, VerbosityOption

   @extra_command(params=[
      VersionOption(version="0.1"),
      ConfigOption(default="ex.yml"),
      VerbosityOption(default="DEBUG"),
   ])
   def cli():
      pass

And now you get:

.. click:run::
   invoke(cli, args=["--help"])
```

This let you replace the preset options by your own set, tweak their order and fine-tune their defaults.

## Timer option

```{todo}
Write example and tutorial.
```

## `click_extra.commands` API

```{eval-rst}
.. automodule:: click_extra.commands
   :members:
   :undoc-members:
   :show-inheritance:
```
