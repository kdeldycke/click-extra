# {octicon}`command-palette` Commands & groups

## Drop-in replacement

The whole namespace of `click_extra` is a superset of both `click` and `cloup` namespaces. So if Click Extra's main decorators, functions and classes extends and enhance Click and Cloup ones, all the rest are direct proxies.

This means if you want to [upgrade an existing Click-based CLI to Click Extra](tutorial.md), you can often replace imports of the `click` namespace by `click_extra` and it will work as expected.

## Click and Cloup inheritance

At the module level, `click_extra` imports all elements from `click.*`, then all elements from the `cloup.*` namespace.

Which means all elements not redefined by Click Extra fallback to Cloup. And if Cloup itself does not redefine them, they fallback to Click.

For example:
- `click_extra.echo` is a direct alias to `click.echo` because Cloup does not re-implement an `echo` helper.
- [`@cloup.option_group` is a specific feature of Cloup](https://cloup.readthedocs.io/en/stable/pages/option-groups.html) that is is not implemented by Click. Still, `@click_extra.option_group` is a direct proxy to it.
- `@click_extra.timer` is a new decorator implemented by Click Extra and not present in either Click or Cloup. So it is not a proxy of anything.
- As for `@click_extra.version_option`, it is a re-implementation of `@click.version_option`, and so overrides it. If you want to use its original version, import it directly from `click` namespace.

Here is how the main decorators of Click Extra wraps and extends Cloup and Click ones:

| Click Extra decorator              | Wrapped decorator        | Base class                           |
| ---------------------------------- | ------------------------ | ------------------------------------ |
| `@click_extra.command`             | `@cloup.command`         | `click_extra.ExtraCommand`           |
| `@click_extra.group`               | `@cloup.group`           | `click_extra.ExtraGroup`             |
| `@click_extra.option`              | `@cloup.option`          | `click_extra.Option`                 |
| `@click_extra.argument`            | `@cloup.argument`        | `click_extra.Argument`               |
| `@click_extra.version_option`      | `@click_extra.option`    | `click_extra.ExtraVersionOption`     |
| `@click_extra.lazy_group`          | `@click_extra.group`     | `click_extra.LazyGroup`              |
| `@click_extra.color_option`        | `@click_extra.option`    | `click_extra.ColorOption`            |
| `@click_extra.config_option`       | `@click_extra.option`    | `click_extra.ConfigOption`           |
| `@click_extra.no_config_option`    | `@click_extra.option`    | `click_extra.NoConfigOption`         |
| `@click_extra.show_params_option`  | `@click_extra.option`    | `click_extra.ShowParamsOption`       |
| `@click_extra.table_format_option` | `@click_extra.option`    | `click_extra.TableFormatOption`      |
| `@click_extra.telemetry_option`    | `@click_extra.option`    | `click_extra.TelemetryOption`        |
| `@click_extra.timer_option`        | `@click_extra.option`    | `click_extra.TimerOption`            |
| `@click_extra.verbose_option`      | `@click_extra.option`    | `click_extra.VerboseOption`          |
| `@click_extra.verbosity_option`    | `@click_extra.option`    | `click_extra.VerbosityOption`        |
| `@click_extra.option_group`        | `@cloup.option_group`    | `cloup.OptionGroup`                  |
| `@click_extra.pass_context`        | `@click.pass_context`    | *None*                               |
| `@click_extra.help_option`         | `@click.help_option`     | *None*                               |
| …                                  | …                        | …                                    |

Same for the main classes and functions, where some are re-implemented by Click Extra, and others are direct aliases to Cloup or Click ones:

| Click Extra class                | Alias to                        | Parent class                 |
| -------------------------------- | ------------------------------- | ---------------------------- |
| `click_extra.ExtraCommand`       | *Itself*                        | `cloup.Command`              |
| `click_extra.ExtraGroup`         | *Itself*                        | `cloup.Group`                |
| `click_extra.Option`             | *Itself*                        | `cloup.Option`               |
| `click_extra.Argument`           | *Itself*                        | `cloup.Argument`             |
| `click_extra.ExtraContext`       | *Itself*                        | `cloup.Context`              |
| `click_extra.HelpFormatter`      | `cloup.HelpFormatter`           |                              |
| `click_extra.HelpExtraFormatter` | *Itself*                        | `cloup.HelpFormatter`        |
| `click_extra.HelpTheme`          | `cloup.HelpThene`               |                              |
| `click_extra.HelpExtraTheme`     | *Itself*                        | `cloup.HelpThene`            |
| `click_extra.ExtraCliRunner`     | *Itself*                        | `click.testing.CliRunner`    |
| `click_extra.ExtraVersionOption` | *Itself*                        |                              |
| `click_extra.Style`              | `cloup.Style`                   |                              |
| `click_extra.echo`               | `click.echo`                    |                              |
| `click_extra.ParameterSource`    | `click.core.ParameterSource`    |                              |
| `click_extra.UNSET`              | `click._utils.UNSET`            |                              |
| `click_extra.EnumChoice`         | *Itself*                        | `click.Choice`               |
| `click_extra.Choice`             | `click.Choice`                  |                              |
| …                                | …                               | …                            |

```{hint}
You can inspect the implementation details in:

- [`click_extra.__init__`](https://github.com/kdeldycke/click-extra/blob/main/click_extra/__init__.py)
- [`cloup.__init__`](https://github.com/janluke/cloup/blob/master/cloup/__init__.py)
- [`click.__init__`](https://github.com/pallets/click/blob/main/src/click/__init__.py)
```

## Default options

The `@command` and `@group` decorators are [pre-configured with a set of default options](commands.md#click_extra.commands.default_extra_params).

### Remove default options

You can remove all default options by resetting the `params` argument to `None`:

```{click:example}
:emphasize-lines: 3
from click_extra import command

@command(params=None)
def bare_cli():
    pass
```

Which results in:

```{click:run}
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

```{click:example}
:emphasize-lines: 4-7
from click_extra import command, ConfigOption, VerbosityOption

@command(
    params=[
        ConfigOption(default="ex.yml"),
        VerbosityOption(default="DEBUG"),
    ]
)
def cli():
    pass
```

And now you get:

```{click:run}
:emphasize-lines: 5-9
from textwrap import dedent
result = invoke(cli, args=["--help"])
assert result.stdout.startswith(dedent(
    """\
    \x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mcli\x1b[0m \x1b[36m\x1b[2m[OPTIONS]\x1b[0m

    \x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m
      \x1b[36m--config\x1b[0m \x1b[36m\x1b[2mCONFIG_PATH\x1b[0m"""
))
```

This let you replace the preset options by your own set, tweak their order and fine-tune their defaults.

````{admonition} Duplicate options
:class: caution
If you try to add option decorators to a command which already have them by default, you will end up with duplicate entries ([as seen in issue #232](https://github.com/kdeldycke/click-extra/issues/232)):

```{click:example}
:emphasize-lines: 4
from click_extra import command, version_option

@command
@version_option(version="0.1")
def cli():
    pass
```

See how the `--version` option gets duplicated at the end:

```{click:run}
:emphasize-lines: 23,24
from textwrap import dedent
result = invoke(cli, args=["--help"])
assert (
    "  \x1b[36m--version\x1b[0m             Show the version and exit.\n"
    "  \x1b[36m--version\x1b[0m             Show the version and exit.\n"
    "  \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m            Show this message and exit.\n"
) in result.output
```

This is by design: decorators are cumulative, to allow you to add your own options to the preset of `@command` and `@group`.

But notice the `UserWarning` log messages: `The parameter --version is used more than once. Remove its duplicate as parameters should be unique.`. As it is not a good practice to have duplicate options and you must avoid it. There's also a non-zero chance for this situation to result in complete failure in a future Click release.

Finally, if the second `--version` option is placed right before the `--help` option, it is because [Click is adding its own generated `--help` option at the end of the list](https://kdeldycke.github.io/click-extra/commands.html#click_extra.commands.default_extra_params).
````

### Option order

Notice how the options above are ordered in the help message.

The default behavior of `@command` is to order options in the way they are provided to the `params=` argument of the decorator. Then adds to that list the additional option decorators positioned after the `@command` decorator.

After that, there is a final [sorting step applied to options](https://kdeldycke.github.io/click-extra/commands.html#click_extra.commands.ExtraCommand). This is done by the `extra_option_at_end` option, which is `True` by default.

### Option's defaults

Because Click Extra commands and groups inherits from Click, you can [override the defaults the way Click allows you to](https://click.palletsprojects.com/en/stable/commands/#context-defaults). Here is a reminder on how to do it.

For example, the [`--verbosity` option defaults to the `WARNING` level](logging.md#click_extra.logging.DEFAULT_LEVEL_NAME). Now we'd like to change this default to `INFO`.

If you manage your own `--verbosity` option, you can [pass the `default` argument to its decorator like we did above](#change-default-options):

```{click:example}
:emphasize-lines: 5
import click
import click_extra

@click.command
@click_extra.verbosity_option(default="INFO")
def cli():
    pass
```

This also works in its class form:

```{click:example}
:emphasize-lines: 4
import click
import click_extra

@click.command(params=[click_extra.VerbosityOption(default="INFO")])
def cli():
    pass
```

But you also have the alternative to pass a `default_map` via the `context_settings`:

```{click:example}
:emphasize-lines: 3
import click_extra

@click_extra.command(context_settings={"default_map": {"verbosity": "INFO"}})
def cli():
    pass
```

Which results in `[default: INFO]` being featured in the help message:

```{click:run}
:emphasize-lines: 20
result = invoke(cli, args=["--help"])
assert (
    "  \x1b[2m[\x1b[0m\x1b[2mdefault:\n"
    "                        \x1b[0m\x1b[32m\x1b[2m\x1b[3mINFO\x1b[0m\x1b[2m]\x1b[0m\n"
) in result.stdout
```

```{tip}
The advantage of the `context_settings` method we demonstrated above, is that it let you change the default of the `--verbosity` option provided by Click Extra, [without having to touch the `params` argument](#change-default-options).
```

## Lazily loading subcommands

Click Extra provides a `LazyGroup` class and `@lazy_group` decorator to create command groups that only load their subcommands when they are invoked.

This implementation is based on the one provided in Click's documentation, so refer to the [*Lazily loading subcommands*](https://click.palletsprojects.com/en/stable/complex/#defining-the-lazy-group) section for more details.

## Third-party commands composition

Click Extra is capable of composing with existing Click CLI in various situation.

### Wrap other commands

Click allows you to build up a hierarchy of command and subcommands. Click Extra inherits this behavior, which means we are free to assemble multiple third-party subcommands into a top-level one.

For this example, let's imagine you are working for an operation team that is relying daily on a couple of CLIs. Like [`dbt`](https://github.com/dbt-labs/dbt-core) to manage your data workflows, and [`aws-sam-cli`](https://github.com/aws/aws-sam-cli) to deploy them in the cloud.

For some practical reasons, you'd like to wrap all these commands into a big one. This is how to do it.

````{note}
Here is how I initialized this example on my machine:

```{code-block} shell-session
$ git clone https://github.com/kdeldycke/click-extra
(...)

$ cd click-extra
(...)

$ python -m pip install uv
(...)

$ uv venv
(...)

$ source .venv/bin/activate
(...)

$ uv sync --all-extras
(...)

$ uv pip install dbt-core
(...)

$ uv pip install aws-sam-cli
(...)
```

That way I had the latest Click Extra, `dbt` and `aws-sam-cli` installed in the same virtual environment:

```{code-block} shell-session
$ uv run -- dbt --version
Core:
  - installed: 1.6.1
  - latest:    1.6.2 - Update available!

  Your version of dbt-core is out of date!
  You can find instructions for upgrading here:
  https://docs.getdbt.com/docs/installation

Plugins:


```

```{code-block} shell-session
$ uv run -- sam --version
SAM CLI, version 1.97.0
```
````

Once you identified the entry points of each commands, you can easily wrap them into a top-level Click Extra CLI, here in a local script I called `wrap.py`:

```{code-block} python
:caption: `wrap.py`
:emphasize-lines: 3-4,12-13
import click_extra

from samcli.cli.main import cli as sam_cli
from dbt.cli.main import cli as dbt_cli


@click_extra.group
def main():
    pass


main.add_command(cmd=sam_cli, name="aws_sam")
main.add_command(cmd=dbt_cli, name="dbt")


if __name__ == "__main__":
    main()
```

And this simple script gets rendered into:

```{code-block} shell-session
:emphasize-lines: 27-29
$ uv run -- python ./wrap.py
Usage: wrap.py [OPTIONS] COMMAND [ARGS]...

Options:
  --time / --no-time    Measure and print elapsed execution time.  [default: no-
                        time]
  --color, --ansi / --no-color, --no-ansi
                        Strip out all colors and all ANSI codes from output.
                        [default: color]
  --config CONFIG_PATH  Location of the configuration file. Supports glob
                        pattern of local path and remote URL.  [default:
                        ~/Library/Application
                        Support/wrap.py/*.{toml,yaml,yml,json,ini,xml}]
  --no-config           Ignore all configuration files and only use command line
                        parameters and environment variables.
  --show-params         Show all CLI parameters, their provenance, defaults and
                        value, then exit.
  --table-format [asciidoc|csv|csv-excel|csv-excel-tab|csv-unix|double-grid|double-outline|fancy-grid|fancy-outline|github|grid|heavy-grid|heavy-outline|html|jira|latex|latex-booktabs|latex-longtable|latex-raw|mediawiki|mixed-grid|mixed-outline|moinmoin|orgtbl|outline|pipe|plain|presto|pretty|psql|rounded-grid|rounded-outline|rst|simple|simple-grid|simple-outline|textile|tsv|unsafehtml|vertical|youtrack]
                        Rendering style of tables.  [default: rounded-outline]
  --verbosity LEVEL     Either CRITICAL, ERROR, WARNING, INFO, DEBUG.  [default:
                        INFO]
  -v, --verbose         Increase the default WARNING verbosity by one level for
                        each additional repetition of the option.  [default: 0]
  --version             Show the version and exit.
  -h, --help            Show this message and exit.

Commands:
  aws_sam  AWS Serverless Application Model (SAM) CLI
  dbt      An ELT tool for managing your SQL transformations and data models.
```

Here you can see that the top-level CLI gets [all the default options and behavior (including coloring)](tutorial.md#all-bells-and-whistles) of `@group`. But it also made available the standalone `aws_sam` and `dbt` CLI as standard subcommands.

And they are perfectly functional as-is.

You can compare the output of the `aws_sam` subcommand with its original one:

`````{tab-set}
````{tab-item} aws_sam subcommand in wrap.py
```{code-block} shell-session
:emphasize-lines: 1-2,59
$ uv run -- python ./wrap.py aws_sam --help
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
```{code-block} shell-session
:emphasize-lines: 1-2,59
$ uv run -- sam --help
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

```{code-block} diff
:emphasize-lines: 2-5,13-14
@@ -1,5 +1,5 @@
-$ uv run -- python ./wrap.py aws_sam --help
-Usage: wrap.py aws_sam [OPTIONS] COMMAND [ARGS]...
+$ uv run -- sam --help
+Usage: sam [OPTIONS] COMMAND [ARGS]...

   AWS Serverless Application Model (SAM) CLI

@@ -56,4 +56,4 @@

 Examples:

-    Get Started:        $wrap.py aws_sam init
+    Get Started:        $sam init
```

Now that all commands are under the same umbrella, there is no limit to your imagination!

```{caution}
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
