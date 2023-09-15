# Commands & groups

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

```{note} Click and Cloup inheritance

At the module level, `click_extra` imports all elements from `click.*`, then all elements from the `cloup.*` namespace.

Which means all elements not redefined by Click Extra fallback to Cloup. And if Cloup itself does not redefine them, they fallback to Click.

For example:
- `click_extra.echo` is a direct proxy to `click.echo` because Cloup does not re-implement an `echo` helper.
- On the other hand, `@click_extra.option` is a proxy of `@cloup.option`, because Cloup adds the [possibility for options to be grouped](https://cloup.readthedocs.io/en/stable/pages/option-groups.html).
- `@click_extra.timer` is not a proxy of anything, because it is a new decorator implemented by Click Extra.
- As for `@click_extra.extra_version_option`, it is a re-implementation of `@click.version_option`. Because it adds new features and breaks the original API, it was prefixed with `extra_` to become its own thing. And `@click_extra.version_option` still proxy the original from Click.

Here are few other examples on how Click Extra proxies the main elements from Click and Cloup:

| Click Extra element           | Target                | [Click's original](https://click.palletsprojects.com/en/8.1.x/api/) |
| ----------------------------- | --------------------- | ----------------------------------------------------------- |
| `@click_extra.command`        | `@cloup.command`      | `@click.command`                                            |
| `@click_extra.group`          | `@cloup.group`        | `@click.group`                                              |
| `@click_extra.argument`       | `@cloup.argument`     | `@click.argument`                                           |
| `@click_extra.option`         | `@cloup.option`       | `@click.option`                                             |
| `@click_extra.option_group`   | `@cloup.option_group` | *Not implemented*                                           |
| `@click_extra.pass_context`   | `@click.pass_context` | `@click.pass_context`                                       |
| `@click_extra.version_option`   | `@click.version_option` | `@click.version_option`                                       |
| `@click_extra.extra_version_option` | *Itself*              | `@click.version_option`                                     |
| `@click_extra.help_option`    | *Itself*              | `@click.help_option`                                        |
| `@click_extra.timer_option`   | *Itself*              | *Not implemented*                                           |
| …                             | …                            | …                                                    |
| `click_extra.Argument`        | `cloup.Argument`      | `click.Argument`                                            |
| `click_extra.Command`         | `cloup.Command`       | `click.Command`                                             |
| `click_extra.Group`           | `cloup.Group`         | `click.Group`                                               |
| `click_extra.HelpFormatter`   | `cloup.HelpFormatter` | `click.HelpFormatter`                                       |
| `click_extra.HelpTheme`       | `cloup.HelpThene`     | *Not implemented*                                           |
| `click_extra.Option`          | `cloup.Option`        | `click.Option`                                              |
| `click_extra.ExtraVersionOption`          |  *Itself*        |  *Not implemented*                     |
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

Now if you want to benefit from all the [wonderful features of Click Extra](index.md#features), you have to use the `extra`-prefixed variants:

| [Original](https://click.palletsprojects.com/en/8.1.x/api/) | Extra variant                       |
| ----------------------------------------------------------- | ----------------------------------- |
| `@click.command`                                            | `@click_extra.extra_command`        |
| `@click.group`                                              | `@click_extra.extra_group`          |
| `click.Command`                                             | `click_extra.ExtraCommand`          |
| `click.Group`                                               | `click_extra.ExtraGroup`            |
| `click.Context`                                             | `click_extra.ExtraContext`          |
| `click.Option`                                              | `click_extra.ExtraOption`           |
| `@click.version_option`                                     | `@click_extra.extra_version_option` |
| `click.testing.CliRunner`                                   | `click_extra.ExtraCliRunner`        |

You can see how to use some of these `extra` variants in the [tutorial](tutorial.md).

## Default options

The `@extra_command` and `@extra_group` decorators are [pre-configured with a set of default options](commands.md#click_extra.commands.default_extra_params).

### Remove default options

You can remove all default options by resetting the `params` argument to `None`:

```{eval-rst}
.. click:example::
   from click_extra import extra_command

   @extra_command(params=None)
   def bare_cli():
      pass

Which results in:

.. click:run::
   from textwrap import dedent
   result = invoke(bare_cli, args=["--help"])
   assert result.output == dedent(
      """\
      \x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mbare-cli\x1b[0m \x1b[36m\x1b[2m[OPTIONS]\x1b[0m

      \x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m
        \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m  Show this message and exit.
      """
   )
```

As you can see, all options are stripped out, but the colouring and formatting of the help message is preserved.

### Change default options

To override the default options, you can provide the `params=` argument to the command. But note how we use classes instead of option decorators:

```{eval-rst}
.. click:example::
   from click_extra import extra_command, ConfigOption, VerbosityOption

   @extra_command(
      params=[
         ConfigOption(default="ex.yml"),
         VerbosityOption(default="DEBUG"),
      ]
   )
   def cli():
      pass

And now you get:

.. click:run::
   from textwrap import dedent
   result = invoke(cli, args=["--help"])
   assert result.stdout.startswith(dedent(
      """\
      \x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mcli\x1b[0m \x1b[36m\x1b[2m[OPTIONS]\x1b[0m

      \x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m
        \x1b[36m-C\x1b[0m, \x1b[36m--config\x1b[0m \x1b[36m\x1b[2mCONFIG_PATH\x1b[0m"""
   ))
```

This let you replace the preset options by your own set, tweak their order and fine-tune their defaults.

```{eval-rst}
.. caution:: Duplicate options

   If you try to add option decorators to a command which already have them by default, you will end up with duplicate entries (as seen in issue {issue}`232`):

   .. click:example::
      from click_extra import extra_command, extra_version_option

      @extra_command
      @extra_version_option(version="0.1")
      def cli():
         pass

   See how the ``--version`` option gets duplicated at the end:

   .. click:run::
      from textwrap import dedent
      result = invoke(cli, args=["--help"])
      assert (
         "  \x1b[36m--version\x1b[0m                 Show the version and exit.\n"
         "  \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m                Show this message and exit.\n"
         "  \x1b[36m--version\x1b[0m                 Show the version and exit.\n"
      ) in result.output

   This is by design: decorators are cumulative, to allow you to add your own options to the preset of `@extra_command` and `@extra_group`.
```

### Option order

Notice how the options above are ordered in the help message.

The default behavior of `@extra_command` (and its derivates decorators) is to order options in the way they are provided to the `params=` argument of the decorator. Then adds to that list the additional option decorators positioned after the `@extra_command` decorator.

After that, there is a final [sorting step applied to options](https://kdeldycke.github.io/click-extra/commands.html#click_extra.commands.ExtraCommand). This is done by the `extra_option_at_end` option, which is `True` by default.

### Option's defaults

Because Click Extra commands and groups inherits from Click, you can [override the defaults the way Click allows you to](https://click.palletsprojects.com/en/8.1.x/commands/#context-defaults). Here is a reminder on how to do it.

For example, the [`--verbosity` option defaults to the `WARNING` level](logging.md#click_extra.logging.DEFAULT_LEVEL_NAME). Now we'd like to change this default to `INFO`.

If you manage your own `--verbosity` option, you can [pass the `default` argument to its decorator like we did above](#change-default-options):

```python
from click_extra import command, verbosity_option


@command
@verbosity_option(default="INFO")
def cli():
    pass
```

This also works in its class form:

```python
from click_extra import command, VerbosityOption


@command(params=[VerbosityOption(default="INFO")])
def cli():
    pass
```

But you also have the alternative to pass a `default_map` via the `context_settings`:

```{eval-rst}
.. click:example::
   from click_extra import extra_command

   @extra_command(context_settings={"default_map": {"verbosity": "INFO"}})
   def cli():
      pass

Which results in ``[default: INFO]`` being featured in the help message:

.. click:run::
   result = invoke(cli, args=["--help"])
   assert "\x1b[2m[\x1b[0m\x1b[2mdefault: \x1b[0m\x1b[32m\x1b[2m\x1b[3mINFO\x1b[0m\x1b[2m]\x1b[0m\n" in result.stdout
```

```{tip}
The advantage of the `context_settings` method we demonstrated last, is that it let you change the default of the `--verbosity` option provided by Click Extra, without having to [re-list the whole set of default options](#change-default-options).
```

## Third-party commands composition

Click Extra is capable of composing with existing Click CLI in various situation.

### Wrap other commands

Click allows you to build up a hierarchy of command and subcommands. Click Extra inherits this behavior, which means we are free to assemble multiple third-party subcommands into a top-level one.

For this example, let's imagine you are working for an operation team that is relying daily on a couple of CLIs. Like [`dbt`](https://github.com/dbt-labs/dbt-core) to manage your data workflows, and [`aws-sam-cli`](https://github.com/aws/aws-sam-cli) to deploy them in the cloud.

For some practical reasons, you'd like to wrap all these commands into a big one. This is how to do it.

````{note}
Here is how I initialized this example on my machine:

```shell-session
$ git clone https://github.com/kdeldycke/click-extra
(...)

$ cd click-extra
(...)

$ poetry install
(...)

$ poetry run python -m pip install dbt-core
(...)

$ poetry run python -m pip install aws-sam-cli
(...)
```

That way I had the latest Click Extra, `dbt` and `aws-sam-cli` installed in the same virtual environment:

```shell-session
$ poetry run dbt --version
Core:
  - installed: 1.6.1
  - latest:    1.6.2 - Update available!

  Your version of dbt-core is out of date!
  You can find instructions for upgrading here:
  https://docs.getdbt.com/docs/installation

Plugins:


```

```shell-session
$ poetry run sam --version
SAM CLI, version 1.97.0
```
````

Once you identified the entry points of each commands, you can easely wrap them into a top-level Click Extra CLI. Here is for instance the content of a `wrap.py` script:

```python
from click_extra import extra_group

from samcli.cli.main import cli as sam_cli
from dbt.cli.main import cli as dbt_cli


@extra_group
def main():
    pass


main.add_command(cmd=sam_cli, name='aws_sam')
main.add_command(cmd=dbt_cli, name='dbt')


if __name__ == '__main__':
    main()
```

And this simple script gets rendered into:

```shell-session
$ poetry run python ./wrap.py
Usage: wrap.py [OPTIONS] COMMAND [ARGS]...

Options:
  --time / --no-time        Measure and print elapsed execution time.  [default:
                            no-time]
  --color, --ansi / --no-color, --no-ansi
                            Strip out all colors and all ANSI codes from output.
                            [default: color]
  -C, --config CONFIG_PATH  Location of the configuration file. Supports glob
                            pattern of local path and remote URL.  [default:
                            ~/Library/Application
                            Support/wrap.py/*.{toml,yaml,yml,json,ini,xml}]
  --show-params             Show all CLI parameters, their provenance, defaults
                            and value, then exit.
  -v, --verbosity LEVEL     Either CRITICAL, ERROR, WARNING, INFO, DEBUG.
                            [default: WARNING]
  --version                 Show the version and exit.
  -h, --help                Show this message and exit.

Commands:
  aws_sam  AWS Serverless Application Model (SAM) CLI
  dbt      An ELT tool for managing your SQL transformations and data models.
```

Here you can see that the top-level CLI gets [all the default options and behavior (including coloring)](tutorial.md#all-bells-and-whistles) of `@extra_group`. But it also made available the standalone `aws_sam` and `dbt` CLI as standard subcommands.

And they are perfectly functional as-is.

You can compare the output of the `aws_sam` subcommand with its original one:

`````{tab-set}
````{tab-item} aws_sam subcommand in wrap.py
```shell-session
$ poetry run python ./wrap.py aws_sam --help
Usage: wrap.py aws_sam [OPTIONS] COMMAND [ARGS]...

  AWS Serverless Application Model (SAM) CLI

  The AWS Serverless Application Model Command Line Interface (AWS SAM CLI) is
  a command line tool that you can use with AWS SAM templates and supported
  third-party integrations to build and run your serverless applications.

  Learn more: https://docs.aws.amazon.com/serverless-application-model/

Commands:

  Learn:
    docs NEW!           Launch the AWS SAM CLI documentation in a browser.

  Create an App:
    init                Initialize an AWS SAM application.

  Develop your App:
    build               Build your AWS serverless function code.
    local               Run your AWS serverless function locally.
    validate            Validate an AWS SAM template.
    sync NEW!           Sync an AWS SAM project to AWS.
    remote NEW!         Invoke or send an event to cloud resources in your AWS
                        Cloudformation stack.

  Deploy your App:
    package             Package an AWS SAM application.
    deploy              Deploy an AWS SAM application.

  Monitor your App:
    logs                Fetch AWS Cloudwatch logs for AWS Lambda Functions or
                        Cloudwatch Log groups.
    traces              Fetch AWS X-Ray traces.

  And More:
    list NEW!           Fetch the state of your AWS serverless application.
    delete              Delete an AWS SAM application and the artifacts created
                        by sam deploy.
    pipeline            Manage the continuous delivery of your AWS serverless
                        application.
    publish             Publish a packaged AWS SAM template to AWS Serverless
                        Application Repository for easy sharing.

Options:

    --beta-features / --no-beta-features
                                    Enable/Disable beta features.
    --debug                         Turn on debug logging to print debug message
                                    generated by AWS SAM CLI and display
                                    timestamps.
    --version                       Show the version and exit.
    --info                          Show system and dependencies information.
    -h, --help                      Show this message and exit.

Examples:

    Get Started:        $wrap.py aws_sam init
```
````

````{tab-item} Vanilla sam CLI
```shell-session
$ poetry run sam --help
Usage: sam [OPTIONS] COMMAND [ARGS]...

  AWS Serverless Application Model (SAM) CLI

  The AWS Serverless Application Model Command Line Interface (AWS SAM CLI) is
  a command line tool that you can use with AWS SAM templates and supported
  third-party integrations to build and run your serverless applications.

  Learn more: https://docs.aws.amazon.com/serverless-application-model/

Commands:

  Learn:
    docs NEW!           Launch the AWS SAM CLI documentation in a browser.

  Create an App:
    init                Initialize an AWS SAM application.

  Develop your App:
    build               Build your AWS serverless function code.
    local               Run your AWS serverless function locally.
    validate            Validate an AWS SAM template.
    sync NEW!           Sync an AWS SAM project to AWS.
    remote NEW!         Invoke or send an event to cloud resources in your AWS
                        Cloudformation stack.

  Deploy your App:
    package             Package an AWS SAM application.
    deploy              Deploy an AWS SAM application.

  Monitor your App:
    logs                Fetch AWS Cloudwatch logs for AWS Lambda Functions or
                        Cloudwatch Log groups.
    traces              Fetch AWS X-Ray traces.

  And More:
    list NEW!           Fetch the state of your AWS serverless application.
    delete              Delete an AWS SAM application and the artifacts created
                        by sam deploy.
    pipeline            Manage the continuous delivery of your AWS serverless
                        application.
    publish             Publish a packaged AWS SAM template to AWS Serverless
                        Application Repository for easy sharing.

Options:

    --beta-features / --no-beta-features
                                    Enable/Disable beta features.
    --debug                         Turn on debug logging to print debug message
                                    generated by AWS SAM CLI and display
                                    timestamps.
    --version                       Show the version and exit.
    --info                          Show system and dependencies information.
    -h, --help                      Show this message and exit.

Examples:

    Get Started:        $sam init
```
````
`````

Here is the highlighted differences to make them even more obvious:

```diff
@@ -1,5 +1,5 @@
-$ poetry run python ./wrap.py aws_sam --help
-Usage: wrap.py aws_sam [OPTIONS] COMMAND [ARGS]...
+$ poetry run sam --help
+Usage: sam [OPTIONS] COMMAND [ARGS]...

   AWS Serverless Application Model (SAM) CLI

@@ -56,4 +56,4 @@

 Examples:

-    Get Started:        $wrap.py aws_sam init
+    Get Started:        $sam init
```

Now that all commands are under the same umbrella, there is no limit to your imagination!

```{important}
This might looks janky, but this franken-CLI might be a great way to solve practical problems in your situation.

You can augment them with your custom glue code. Or maybe mashing them up will simplify the re-distribution of these CLIs on your production machines. Or control their common dependencies. Or freeze their versions. Or hard-code some parameters. Or apply monkey-patches. Or chain these commands to create new kind of automation...

There is a miriad of possibilities. If you have some other examples in the same vein, please share them in an issue or even directly via a PR. I'd love to complement this documentation with creative use-cases.
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
