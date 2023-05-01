# Commands and groups

## Drop-in replacement

Click Extra aims to be a drop-in replacement for Click. The vast majority of Click Extra's decorators, functions and classes are direct proxies of their Click counterparts. This means that you can replace, in your code, imports of the `click` namespace by `click_extra` and it will work as expected.

Here is for instance the [canonical `click` example](https://github.com/pallets/click#a-simple-example) with all original imports replaced with `click_extra`:

```{eval-rst}
.. click:example::
    from click_extra import command, echo, option

    @command
    @option("--count", default=1, help="Number of greetings.")
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello(count, name):
        """Simple program that greets NAME for a total of COUNT times."""
        for _ in range(count):
            echo(f"Hello, {name}!")

As you can see the result does not deviates from the original Click-based output:

.. click:run::
   invoke(hello, args=["--help"])
```

```{note} Click and Cloup inheritance

At the module level, `click_extra` imports all elements from `click.*`, then all elements from the `cloup.*` namespace.

Which means all elements not redefined by Click Extra fallback to Cloup. And if Cloup itself does not redefine them, they fallback to Click.

For example:
- `click_extra.echo` is a direct proxy to `click.echo` because Cloup does not re-implement an `echo` helper.
- On the other hand, `@click_extra.option` is a proxy of `@cloup.option`, because Cloup adds the [possibility for options to be grouped](https://cloup.readthedocs.io/en/stable/pages/option-groups.html).
- `@click_extra.timer` is not a proxy of anything, because it is a new decorator implemented by Click Extra.
- As for `@click_extra.version_option`, it mimicks the original `@click.version_option`, but because it adds new features, it was fully reimplemented by Click Extra and is no longer a proxy of the original from Click.

Here are few other examples on how Click Extra proxies the main elements from Click and Cloup:

| Click Extra element           | Target                | [Click's original](https://click.palletsprojects.com/en/8.1.x/api/) |
| ----------------------------- | --------------------- | ----------------------------------------------------------- |
| `@click_extra.command`        | `@cloup.command`      | `@click.command`                                            |
| `@click_extra.group`          | `@cloup.group`        | `@click.group`                                              |
| `@click_extra.argument`       | `@cloup.argument`     | `@click.argument`                                           |
| `@click_extra.option`         | `@cloup.option`       | `@click.option`                                             |
| `@click_extra.option_group`   | `@cloup.option_group` | *Not implemented*                                           |
| `@click_extra.pass_context`   | `@click.pass_context` | `@click.pass_context`                                       |
| `@click_extra.version_option` | *Itself*              | `@click.version_option`                                     |
| `@click_extra.help_option`    | *Itself*              | `@click.help_option`                                        |
| `@click_extra.timer_option`   | *Itself*              | *Not implemented*                                           |
| …                             | …                            | …                                                    |
| `click_extra.Argument`        | `cloup.Argument`      | `click.Argument`                                            |
| `click_extra.Command`         | `cloup.Command`       | `click.Command`                                             |
| `click_extra.Group`           | `cloup.Group`         | `click.Group`                                               |
| `click_extra.HelpFormatter`   | `cloup.HelpFormatter` | `click.HelpFormatter`                                       |
| `click_extra.HelpTheme`       | `cloup.HelpThene`     | *Not implemented*                                           |
| `click_extra.Option`          | `cloup.Option`        | `click.Option`                                              |
| `click_extra.Style`           | `cloup.Style`         | *Not implemented*                                           |
| `click_extra.echo`            | `click.echo`          | `click.echo`                                                |
| `click_extra.ParameterSource` | `click.core.ParameterSource` | `click.core.ParameterSource`                         |
| …                             | …                            | …                                                    |

You can inspect the implementation details by looking at:

  * [`click_extra.__init__`](https://github.com/kdeldycke/click-extra/blob/main/click_extra/__init__.py)
  * [`cloup.__init__`](https://github.com/janluke/cloup/blob/master/cloup/__init__.py)
  * [`click.__init__`](https://github.com/pallets/click/blob/main/src/click/__init__.py)
```

## Extra variants

Now if you want to benefits from all the [wonderful features of Click Extra](index#features), you have to use the `extra`-prefixed variants:

| [Original](https://click.palletsprojects.com/en/8.1.x/api/) | Extra variant                |
| ----------------------------------------------------------- | ---------------------------- |
| `@click.command`                                            | `@click_extra.extra_command` |
| `@click.group`                                              | `@click_extra.extra_group`   |
| `click.Command`                                             | `click_extra.ExtraCommand`   |
| `click.Group`                                               | `click_extra.ExtraGroup`     |
| `click.Option`                                              | `click_extra.ExtraOption`    |

The best place to see how to use these `extra`-variants is the [tutorial](tutorial).

## Default options

The `@extra_command` and `@extra_group` decorators are [pre-configured with a set of default options](click_extra.commands.default_extra_params).

## Change default options

To override the default options, you can prvide the `params=` argument to the command. But note how we use classes instead of option decorators:

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

```{eval-rst}
.. caution:: Duplicate options

   If you try to add option decorators to a command which already have them by default, you will end up with duplicate entries (as seen in issue {issue}`232`):

   .. click:example::
      from click_extra import extra_command, version_option, config_option, verbosity_option

      @extra_command
      @version_option(version="0.1")
      @config_option(default="ex.yml")
      @verbosity_option(default="DEBUG")
      def cli():
         pass

   See how options are duplicated at the end:

   .. click:run::
      invoke(cli, args=["--help"])

   This is an expected behavior: decorators are cumulative to not prevent you to add your own options to the preset of `@extra_command` and `@extra_group`.
```

## Option order

Notice how the options above are ordered in the help message.

The default behavior of `@extra_command` (and its derivates decorators) is to order options in the way they are provided to the `params=` argument of the decorator. Then adds to that list the additional option decorators positionned after the `@extra_command` decorator.

After that, there is a final [sorting step applied to options](https://kdeldycke.github.io/click-extra/commands.html#click_extra.commands.ExtraCommand). This is done by the `extra_option_at_end` option, which is `True` by default.

## Timer option

```{todo}
Write example and tutorial.
```

## Introspecting parameters

If for any reason you need to dive into parameters and their values, there is a lot of intermediate and metadata available in the context. Here are some pointers:

```{code-block} python
from click import option, echo, pass_context

from click_extra import config_option, extra_group

@extra_group
@option("--dummy-flag/--no-flag")
@option("--my-list", multiple=True)
@config_option
@pass_context
def my_cli(ctx, dummy_flag, my_list):
    echo(f"dummy_flag    is {dummy_flag!r}")
    echo(f"my_list       is {my_list!r}")
    echo(f"Raw parameters:            {ctx.meta.get('click_extra.raw_args', [])}")
    echo(f"Loaded, default values:    {ctx.default_map}")
    echo(f"Values passed to function: {ctx.params}")

@my_cli.command()
@option("--int-param", type=int, default=10)
def subcommand(int_param):
    echo(f"int_parameter is {int_param!r}")
```

```{caution}
The `click_extra.raw_args` metadata field in the context referenced above is not a standard feature from Click, but a helper introduced by Click Extra. It is only available with `@extra_group` and `@extra_command` decorators.

In the mean time, it is [being discussed in the Click community at `click#1279`](https://github.com/pallets/click/issues/1279#issuecomment-1493348208).
```

```{todo}
Propose the `raw_args` feature upstream to Click.
```

Now if we feed the following `~/configuration.toml` configuration file:

```toml
[my-cli]
verbosity = "DEBUG"
dummy_flag = true
my_list = [ "item 1", "item #2", "Very Last Item!",]

[my-cli.subcommand]
int_param = 3
```

Here is what we get:

```{code-block} shell-session
$ cli --config ~/configuration.toml default-command
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
Raw parameters:            ['--config', '~/configuration.toml', 'default-command']
Loaded, default values:    {'dummy_flag': True, 'my_list': ['pip', 'npm', 'gem'], 'verbosity': 'DEBUG', 'default-command': {'int_param': 3}}
Values passed to function: {'dummy_flag': True, 'my_list': ('pip', 'npm', 'gem')}
```

## `click_extra.commands` API

```{eval-rst}
.. autoclasstree:: click_extra.commands
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.commands
   :members:
   :undoc-members:
   :show-inheritance:
```
