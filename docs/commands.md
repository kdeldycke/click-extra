# {octicon}`apps` Commands & groups

## Drop-in replacement

The whole namespace of `click_extra` is a superset of both `click` and `cloup` namespaces. Click Extra's main decorators, functions and classes extends and enhance Click and Cloup ones. Those left untouched by Click Extra are directly proxied to Cloup or Click.

This means if you want to [upgrade an existing CLI to Click Extra](tutorial.md), you can often replace imports of the `click` namespace by `click_extra` and it will work as expected.

## Click and Cloup inheritance

At the module level, `click_extra` imports all elements from `click.*`, then all elements from the `cloup.*` namespace.

Which means all elements not redefined by Click Extra fallback to Cloup. And if Cloup itself does not redefine them, they fallback to Click.

For the types Click Extra does re-implement, each subclasses its Cloup counterpart, which in turn subclasses Click's (arrows point from a child to the parent it inherits from):

```mermaid
:align: center

flowchart TB
    subgraph CE["click_extra (extends and overrides)"]
        direction LR
        XCmd["Command"]
        XGrp["Group"]
        XOpt["Option"]
        XArg["Argument"]
        XCtx["Context"]
        XSty["Style"]
    end
    subgraph CL["cloup (first fallback)"]
        direction LR
        CCmd["cloup.Command"]
        CGrp["cloup.Group"]
        COpt["cloup.Option"]
        CArg["cloup.Argument"]
        CCtx["cloup.Context"]
        CSty["cloup.Style"]
    end
    subgraph CK["click (base)"]
        direction LR
        KCmd["click.Command"]
        KGrp["click.Group"]
        KOpt["click.Option"]
        KArg["click.Argument"]
        KCtx["click.Context"]
        KSty["click.style()"]
    end
    XCmd --> CCmd --> KCmd
    XGrp --> CGrp --> KGrp
    XOpt --> COpt --> KOpt
    XArg --> CArg --> KArg
    XCtx --> CCtx --> KCtx
    XSty --> CSty -.->|wraps| KSty
```

For example:

- `click_extra.echo` is a direct alias to `click.echo` because neither Click Extra or Cloup re-implements an `echo` helper.
- [`@cloup.option_group` is a specific feature of Cloup](https://cloup.readthedocs.io/en/stable/pages/option-groups.html) that is only implemented by it. It is not modified by Click Extra, and Click does not implement it. Still, `@click_extra.option_group` is a direct alias to Cloup's one.
- `@click_extra.timer_option` is a new decorator only implemented by Click Extra. So it is not a proxy of anything.
- As for `@click_extra.version_option`, it is a re-implementation of `@click.version_option`, and so overrides it. If you want to use its original version, import it directly from `click` namespace.

Here is some of the main decorators of Click Extra and how they wraps and extends Cloup and Click ones:

| Decorators from `click_extra` | Wrapped decorator     | Base class                      |
| :---------------------------- | :-------------------- | :------------------------------ |
| `@command`                    | `@cloup.command`      | `click_extra.Command`           |
| `@group`                      | `@cloup.group`        | `click_extra.Group`             |
| `@lazy_group`                 | `@click_extra.group`  | `click_extra.LazyGroup`         |
| `@option`                     | `@cloup.option`       | `click_extra.Option`            |
| `@argument`                   | `@cloup.argument`     | `click_extra.Argument`          |
| `@version_option`             | `@click_extra.option` | `click_extra.VersionOption`     |
| `@color_option`               | `@click_extra.option` | `click_extra.ColorOption`       |
| `@config_option`              | `@click_extra.option` | `click_extra.ConfigOption`      |
| `@no_config_option`           | `@click_extra.option` | `click_extra.NoConfigOption`    |
| `@show_params_option`         | `@click_extra.option` | `click_extra.ShowParamsOption`  |
| `@table_format_option`        | `@click_extra.option` | `click_extra.TableFormatOption` |
| `@telemetry_option`           | `@click_extra.option` | `click_extra.TelemetryOption`   |
| `@timer_option`               | `@click_extra.option` | `click_extra.TimerOption`       |
| `@verbose_option`             | `@click_extra.option` | `click_extra.VerboseOption`     |
| `@verbosity_option`           | `@click_extra.option` | `click_extra.VerbosityOption`   |
| `@option_group`               | `@cloup.option_group` | `cloup.OptionGroup`             |
| `@pass_context`               | `@click.pass_context` | -                               |
| `@help_option`                | `@click.help_option`  | -                               |
| …                             | …                     | …                               |

Same for the main classes and functions, where some are re-implemented by Click Extra, and others are direct aliases to Cloup or Click ones:

| Classes from `click_extra` | Alias to                     | Parent class              |
| :------------------------- | :--------------------------- | :------------------------ |
| `Command`                  | -                            | `cloup.Command`           |
| `Group`                    | -                            | `cloup.Group`             |
| `LazyGroup`                | -                            | `click_extra.Group`       |
| `Option`                   | -                            | `cloup.Option`            |
| `Argument`                 | -                            | `cloup.Argument`          |
| `Context`                  | -                            | `cloup.Context`           |
| `HelpFormatter`            | -                            | `cloup.HelpFormatter`     |
| `HelpTheme`                | -                            | `cloup.HelpTheme`         |
| `CliRunner`                | -                            | `click.testing.CliRunner` |
| `Result`                   | -                            | `click.testing.Result`    |
| `VersionOption`            | -                            | `click_extra.ExtraOption` |
| `Style`                    | -                            | `cloup.Style`             |
| `echo`                     | `click.echo`                 |                           |
| `ParameterSource`          | `click.core.ParameterSource` |                           |
| `UNSET`                    | `click._utils.UNSET`         |                           |
| `Choice`                   | `click.Choice`               |                           |
| `EnumChoice`               | -                            | `click.Choice`            |
| …                          | …                            | …                         |

```{hint}
You can inspect the implementation details in:

- [`click_extra.__init__`](https://github.com/kdeldycke/click-extra/blob/main/click_extra/__init__.py)
- [`cloup.__init__`](https://github.com/janluke/cloup/blob/master/cloup/__init__.py)
- [`click.__init__`](https://github.com/pallets/click/blob/main/src/click/__init__.py)
```

## Default options

The `@command` and `@group` decorators are pre-configured with a set of {py:func}`default options <click_extra.commands.default_params>`. The `--help`/`-h` option is added separately through `help_option_names`, which is why it survives even when `default_params()` is reset:

```{tip}
Each default option publishes its resolved value on `ctx.meta` so you can pick it up from anywhere in your CLI. See the [available keys](context.md#available-keys) table for the full inventory and worked examples.
```

### Remove default options

You can remove all default options by resetting the `params` argument to `None`:

```{click:source}
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
    \x1b[94m\x1b[4mUsage:\x1b[0m \x1b[97m\x1b[1mbare-cli\x1b[0m \x1b[36m\x1b[2m\x1b[3m[OPTIONS]\x1b[0m

    \x1b[94m\x1b[4mOptions:\x1b[0m
      \x1b[36m\x1b[1m-h\x1b[0m, \x1b[36m\x1b[1m--help\x1b[0m  Show this message and exit.
    """
)
```

As you can see, all options are stripped out, but the coloring and formatting of the help message is preserved.

### Change default options

To override the default options, you can provide the `params=` argument to the command. But note how we use classes instead of option decorators:

```{click:source}
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
:emphasize-result-lines: 5-9
from textwrap import dedent
result = invoke(cli, args=["--help"])
assert result.stdout.startswith(dedent(
    """\
    \x1b[94m\x1b[4mUsage:\x1b[0m \x1b[97m\x1b[1mcli\x1b[0m \x1b[36m\x1b[2m\x1b[3m[OPTIONS]\x1b[0m

    \x1b[94m\x1b[4mOptions:\x1b[0m
      \x1b[36m\x1b[1m--config\x1b[0m \x1b[36m\x1b[2m\x1b[3mLOCATION\x1b[0m"""
))
```

This let you replace the preset options by your own set, tweak their order and fine-tune their defaults.

````{admonition} Duplicate options
:class: caution
If you try to add option decorators to a command which already have them by default, you will end up with duplicate entries ([as seen in issue #232](https://github.com/kdeldycke/click-extra/issues/232)):

```{click:source}
:emphasize-lines: 4
from click_extra import command, version_option

@command
@version_option(fields={"version": "0.1"})
def cli():
    pass
```

See how the `--version` option shows up twice: once in the command's own section, and once more where Click Extra lists its own.

```{click:run}
:emphasize-result-lines: 4,58
result = invoke(cli, args=["--help"])
version_line = (
    "  \x1b[36m\x1b[1m--version\x1b[0m                    Show the version and exit.\n"
)
assert result.stdout.count(version_line) == 2
assert result.stdout.endswith(version_line)
```

This is by design: decorators are cumulative, to allow you to add your own options to the preset of `@command` and `@group`.

But notice the `UserWarning` log messages: `The parameter --version is used more than once. Remove its duplicate as parameters should be unique.`. As it is not a good practice to have duplicate options and you must avoid it. There's also a non-zero chance for this situation to result in complete failure in a future Click release.

Finally, if the second `--version` option is placed right before the `--help` option, it is because Click is adding its own generated `--help` option at the end of the {py:func}`~click_extra.commands.default_params` list.
````

### Option order

Options are listed in the order they were declared: first whatever the `params=` argument of the decorator holds, then the option decorators stacked below `@command`, read bottom-up as Python applies them.

```{click:source}
from click_extra import command, option

@command(params=[])
@option("--sugar", help="Grams of sugar.")
@option("--butter", help="Grams of butter.")
@option("--flour", help="Grams of flour.")
def bake(sugar, butter, flour):
    """Bake a cake."""
```

```{click:run}
result = invoke(bake, args=["--help"])
assert result.exit_code == 0
options = result.stdout
assert options.index("--sugar") < options.index("--butter") < options.index("--flour")
```

On top of that, {py:class}`~click_extra.commands.Command` moves every {py:class}`~click_extra.parameters.ExtraOption` to the end of the list, so the options you wrote yourself come first and Click Extra's own trail behind them. That is the `extra_option_at_end` argument, `True` by default:

```{click:source}
from click_extra import VersionOption, command, option

@command(params=[VersionOption()], extra_option_at_end=False)
@option("--sugar", help="Grams of sugar.")
def keep_declared_order(sugar):
    """Bake a cake."""
```

```{click:run}
result = invoke(keep_declared_order, args=["--help"])
assert result.exit_code == 0
assert result.stdout.index("--version") < result.stdout.index("--sugar")
```

#### Option priorities

The order above is the *processing* order: it decides when each option's callback fires, which is why `--time` sits ahead of everything it measures and `--config` ahead of the defaults it seeds. Reshuffling the help screen by hand would drag those callbacks along with it.

`option_priorities` moves an option on the screen alone. It maps a flag, or an option's destination name, to a number: lowest is shown first, and anything left out sits on the {py:data}`~click_extra.commands.DEFAULT_PRIORITY` line at `100`. So a number below `100` promotes, and one above demotes:

```{click:source}
from click_extra import command, option

@command(params=[], option_priorities={"--flour": 1, "--sugar": 2, "--butter": 3})
@option("--sugar", help="Grams of sugar.")
@option("--butter", help="Grams of butter.")
@option("--flour", help="Grams of flour.")
def measured(sugar, butter, flour):
    """Bake a cake."""
```

```{click:run}
result = invoke(measured, args=["--help"])
assert result.exit_code == 0
options = result.stdout
assert options.index("--flour") < options.index("--sugar") < options.index("--butter")
```

The declaration order is untouched underneath:

```{click:run}
:show-source:
print([param.name for param in measured.params])
```

Priorities are floats rather than integers, so a new option can be wedged between two existing ones without renumbering the rest: `1.5` lands between `1` and `2`. See {py:data}`~click_extra.commands.DEFAULT_PRIORITY` for where that convention comes from.

A priority can also be written against that constant instead of against the literal `100`, which reads well when a single option has to clear the crowd it was declared in:

```{click:source}
from click_extra import command, option
from click_extra.commands import DEFAULT_PRIORITY

@command(
    params=[],
    option_priorities={
        "--flour": DEFAULT_PRIORITY - 1,
        "--sugar": DEFAULT_PRIORITY + 1,
    },
)
@option("--sugar", help="Grams of sugar.")
@option("--butter", help="Grams of butter.")
@option("--flour", help="Grams of flour.")
def relative(sugar, butter, flour):
    """Bake a cake."""
```

Mind the sign, as it runs against the screen: the lowest priority is listed first, so subtracting from `DEFAULT_PRIORITY` raises an option and adding to it lowers one. `--butter` was left out of the mapping and holds the default line between the two. `--help` is appended by Click after the sort, so it closes the command's own section whatever the mapping says:

```{click:run}
result = invoke(relative, args=["--help"])
assert result.exit_code == 0
options = result.stdout
assert options.index("--flour") < options.index("--butter") < options.index("--sugar")
assert options.index("--sugar") < options.index("--help")
```

Positional arguments are never reordered: their sequence is part of the command's grammar, not a matter of presentation.

### Option sections

Click Extra sorts its own options into four sections, drawn after the ones a command declares:

| Section                 | Options                                                                            |
| ----------------------- | ---------------------------------------------------------------------------------- |
| `Configuration options` | `--config`, `--no-config`, `--validate-config`, `--export-config`                  |
| `Output options`        | `--accessible`, `--color`, `--no-color`, `--progress`, `--theme`, `--table-format` |
| `Logging options`       | `--verbosity`, `--verbose`, `--quiet`, `--debug`                                   |
| `Introspection options` | `--time`, `--params`, `--tree`, `--man`, `--help-format`, `--version`              |

The last one gathers the options that replace the run instead of configuring it: each prints something and exits. `--time` sits there because it reports on the run rather than changing what it does.

A command's own options keep the plain `Options` heading, closed by `-h` / `--help`:

```{click:source}
from click_extra import command, option

@command
@option("--city", help="City to report on.")
def forecast(city):
    """Report a multi-day forecast."""
```

```{click:run}
from boltons.strutils import strip_ansi

result = invoke(forecast, args=["--help"])
assert result.exit_code == 0
plain = strip_ansi(result.stdout)
assert plain.startswith(
    "Usage: forecast [OPTIONS]\n"
    "\n"
    "  Report a multi-day forecast.\n"
    "\n"
    "Options:\n"
    "  --city TEXT                  City to report on.\n"
    "  -h, --help                   Show this message and exit.\n"
    "\n"
    "Configuration options:\n"
)
assert plain.rstrip().endswith("--version                    Show the version and exit.")
```

Groups declared with `@option_group` come first, ahead of both. The options left ungrouped gather between them and Click Extra's, under Cloup's `Other options` heading.

To place a group of your own *after* Click Extra's instead, build it with {py:class}`~click_extra.commands.ExtraOptionGroup` and give it a `priority` above the last section:

```{click:source}
from click_extra import ExtraOptionGroup, command, option

@command
@option("--city", help="City to report on.")
@option(
    "--sensor",
    group=ExtraOptionGroup("Hardware options", priority=200),
    help="Identifier of the weather station.",
)
def station(city, sensor):
    """Report from a weather station."""
```

```{click:run}
from boltons.strutils import strip_ansi

result = invoke(station, args=["--help"])
assert result.exit_code == 0
plain = strip_ansi(result.stdout)
assert plain.index("Introspection options:") < plain.index("Hardware options:")
assert plain.rstrip().endswith(
    "--sensor TEXT                Identifier of the weather station."
)
```

The man page and every [machine-readable format](machine-readable.md) read the same sections, so a CLI never lists its options one way on `--help` and another way elsewhere.

### Option defaults

Click Extra inherits from Click, so [the same override mechanisms apply](https://click.palletsprojects.com/en/stable/commands/#context-defaults).

For example, the `--verbosity` option defaults to the {py:data}`WARNING level <click_extra.logging.DEFAULT_LEVEL>`. Now we'd like to change this default to `INFO`.

If you manage your own `--verbosity` option, you can [pass the `default` argument to its decorator like we did above](#change-default-options):

```{click:source}
:emphasize-lines: 2,5
import click
from click_extra import verbosity_option

@click.command
@verbosity_option(default="INFO")
def cli():
    pass
```

This also works in its class form:

```{click:source}
:emphasize-lines: 2,4
import click
from click_extra import VerbosityOption

@click.command(params=[VerbosityOption(default="INFO")])
def cli():
    pass
```

With a `@click_extra.command` instead of `@click.command`, it is the same, you also have the alternative to pass a `default_map` via the `context_settings`:

```{click:source}
:emphasize-lines: 1,3
import click_extra

@click_extra.command(context_settings={"default_map": {"verbosity": "INFO"}})
def cli():
    pass
```

Which results in `[default: INFO]` being featured in the help message:

```{click:run}
:emphasize-result-lines: 36
result = invoke(cli, args=["--help"])
assert (
    "                          \x1b[2m[\x1b[0m\x1b[2mdefault: \x1b[0m\x1b[32m\x1b[2m\x1b[3mINFO\x1b[0m\x1b[2m]\x1b[0m\n"
) in result.stdout
```

```{tip}
The advantage of the `context_settings` method we demonstrated above, is that it let you change the default of the `--verbosity` option provided by Click Extra, [without having to touch the `params` argument](#change-default-options).
```

### Version fields

Click's `@version_option(prog_name=...)` lets you customize the name displayed by `--version`. But with Click Extra's default options, the `VersionOption` is created for you: so there's no decorator call to pass `prog_name` to.

The `version_fields` parameter on `@command` and `@group` solves this. It forwards values to the `VersionOption` in the default params list, without replacing it. It accepts any field from `VersionOption.template_fields`:

```{click:source}
:emphasize-lines: 3
from click_extra import command

@command(name="my-tool", version_fields={"prog_name": "My Tool"})
def my_tool():
    """My Tool CLI."""
```

The `name` controls the usage line, while `prog_name` controls the `--version` output:

```{click:run}
result = invoke(my_tool, args=["--help"])
assert result.exit_code == 0
assert "\x1b[97m\x1b[1mmy-tool\x1b[0m" in result.stdout
```

```{click:run}
result = invoke(my_tool, args=["--version"])
assert result.exit_code == 0
assert "\x1b[97m\x1b[1mMy Tool\x1b[0m" in result.output
```

```{hint}
When `prog_name` is not set, `--version` falls back to the command `name`, which is Click's standard behavior.
```

Multiple fields can be overridden at once, including the version message template:

```{click:source}
from click_extra import command

@command(
    version_fields={
        "prog_name": "Acme CLI",
        "version": "42.0",
        "git_branch": "release/42",
    },
)
def acme():
    pass
```

```{click:run}
result = invoke(acme, args=["--version"])
assert result.exit_code == 0
assert "Acme CLI" in result.output
assert "42.0" in result.output
```

## Examples

A command can carry usage examples, as `(description, command)` pairs. They render in an `Examples:` section of the help screen, in the [man page](man-page.md)'s `EXAMPLES` section, and in every [machine-readable rendering](machine-readable.md):

```{click:source}
from click_extra import command, echo, option


@command(
    examples=[
        ("Report the temperature in Fahrenheit", "forecast --units fahrenheit Oslo"),
        ("Report tomorrow's forecast", "forecast --day tomorrow Oslo"),
    ]
)
@option("--units", default="celsius", help="Temperature scale to display.")
def forecast(units):
    """Report the forecast for a city."""
    echo(f"Sunny, in {units}.")
```

```{click:run}
from boltons.strutils import strip_ansi

result = invoke(forecast, args=["--help"])
assert result.exit_code == 0
plain = strip_ansi(result.output)
assert "Examples:" in plain
assert "$ forecast --units fahrenheit Oslo" in plain
```

The command lines are emitted verbatim rather than wrapped: an example exists to be copied. Option names, subcommands and CLI names inside them are highlighted by the same pass that highlights them everywhere else on the screen, which is why the assertion above strips the styling before matching.

They reach the machine-readable renderings as structured entries, not as prose to be parsed back out:

```{click:run}
import json

result = invoke(forecast, args=["--help-format", "json"])
assert result.exit_code == 0
assert json.loads(result.output)["examples"][0] == {
    "description": "Report the temperature in Fahrenheit",
    "command": "forecast --units fahrenheit Oslo",
}
```

A malformed pair raises `TypeError` at command construction, so a typo surfaces on import rather than on the first `--help` a user runs.

## Subcommand order

A group lists its subcommands alphabetically, as Click does:

```{click:source}
from click_extra import group

@group
def kitchen():
    """Run the kitchen."""

@kitchen.command()
def prep():
    """Prep the ingredients."""

@kitchen.command()
def cook():
    """Cook the dish."""

@kitchen.command()
def plate():
    """Plate the dish."""
```

```{click:run}
result = invoke(kitchen, args=["--help"])
assert result.exit_code == 0
listing = result.stdout
assert listing.index("cook") < listing.index("plate") < listing.index("prep")
```

Which reads well for a set of siblings, and poorly for a sequence: a kitchen preps before it cooks and cooks before it plates, and the alphabet says nothing about that.

### Declaration order

`sort_subcommands=False` lists subcommands in the order they were registered instead:

```{click:source}
from click_extra import group

@group(sort_subcommands=False)
def pipeline():
    """Run the kitchen."""

@pipeline.command()
def prep():
    """Prep the ingredients."""

@pipeline.command()
def cook():
    """Cook the dish."""

@pipeline.command()
def plate():
    """Plate the dish."""
```

```{click:run}
result = invoke(pipeline, args=["--help"])
assert result.exit_code == 0
listing = result.stdout
assert listing.index("prep") < listing.index("cook") < listing.index("plate")
```

The auto-generated [`help` subcommand](#help-subcommand) is listed last, wherever it happens to sit in the registration order, mirroring what `extra_option_at_end` does to options.

### Subcommand priorities

Registration order ties the listing to the shape of your source file, which is awkward when subcommands come from several modules or from a plugin scan. `subcommand_priorities` numbers them instead. Lowest is listed first, and any subcommand left out of the mapping sits on the {py:data}`~click_extra.commands.DEFAULT_PRIORITY` line at `100`, so a number below `100` promotes and one above demotes:

```{click:source}
from click_extra import group

@group(subcommand_priorities={"prep": 1, "plate": 2})
def numbered():
    """Run the kitchen."""

@numbered.command()
def plate():
    """Plate the dish."""

@numbered.command()
def prep():
    """Prep the ingredients."""
```

```{click:run}
result = invoke(numbered, args=["--help"])
assert result.exit_code == 0
assert result.stdout.index("prep") < result.stdout.index("plate")
```

Priorities are floats, so a subcommand added later slots between two existing ones without renumbering anything:

```{click:source}
from click_extra import group

@group(subcommand_priorities={"prep": 1, "plate": 2, "cook": 1.5})
def wedged():
    """Run the kitchen."""

@wedged.command()
def plate():
    """Plate the dish."""

@wedged.command()
def prep():
    """Prep the ingredients."""

@wedged.command()
def cook():
    """Cook the dish."""
```

```{click:run}
result = invoke(wedged, args=["--help"])
assert result.exit_code == 0
listing = result.stdout
assert listing.index("prep") < listing.index("cook") < listing.index("plate")
```

See {py:data}`~click_extra.commands.DEFAULT_PRIORITY` for where that convention comes from.

As with options, a priority can be written against that constant rather than against the literal `100`, which is enough to bookend a listing you are otherwise happy to leave alphabetical:

```{click:source}
from click_extra import group
from click_extra.commands import DEFAULT_PRIORITY

@group(
    subcommand_priorities={
        "prep": DEFAULT_PRIORITY - 1,
        "plate": DEFAULT_PRIORITY + 1,
    },
)
def bookended():
    """Run the kitchen."""

@bookended.command()
def plate():
    """Plate the dish."""

@bookended.command()
def prep():
    """Prep the ingredients."""

@bookended.command()
def brine():
    """Brine overnight."""

@bookended.command()
def cook():
    """Cook the dish."""
```

The same inversion applies: subtracting lifts `prep` above the pack and adding drops `plate` below it, while `brine` and `cook` stay on the default line and keep the alphabetical tie-break between them. The `help` subcommand takes a priority like any other, and ties on that same line here:

```{click:run}
result = invoke(bookended, args=["--help"])
assert result.exit_code == 0
listing = result.stdout.split("Commands:")[1]
assert listing.index("prep") < listing.index("brine") < listing.index("cook")
assert listing.index("cook") < listing.index("help") < listing.index("plate")
```

### One setting for a whole tree

Both knobs are per-group, which means repeating them on every subgroup. `sort_subcommands` is also a context setting, and a context setting is inherited: declare it once on the root group and every group below it follows, unless one says otherwise.

```{click:source}
from click_extra import group

@group(context_settings={"sort_subcommands": False})
def restaurant():
    """Run the restaurant."""

@restaurant.group()
def service():
    """Run the dining room."""

@service.command()
def seat():
    """Seat the guests."""

@service.command()
def pour():
    """Pour the wine."""
```

```{click:run}
result = invoke(restaurant, args=["service", "--help"])
assert result.exit_code == 0
assert result.stdout.index("seat") < result.stdout.index("pour")
```

### Every rendering agrees

The order settles the help screen and every other rendering of the command tree: [`--tree`](tree.md), [`--help-format`](machine-readable.md#the-help-format-option) in all its flavors, the [Carapace completion spec](carapace.md) and shell completion all read the same listing.

```{click:run}
result = invoke(pipeline, args=["--tree"])
assert result.exit_code == 0
listing = result.stdout
assert listing.index("prep") < listing.index("cook") < listing.index("plate")
```

```{admonition} Explicit sections
:class: tip
Cloup's own {py:class}`~cloup.Section` splits a long listing into titled blocks, and carries its own `is_sorted` flag. Priorities and `sort_subcommands` address the default section and the flat listings above; a section you declared yourself is left to Cloup.
```

## `help` subcommand

Every `Group` automatically includes a `help` subcommand. It is the standard way to get help in most major CLIs (git, docker, cargo, npm, kubectl, gh).

`mycli help` shows the group's own help, and `mycli help <subcommand>` shows a specific subcommand's help:

```{click:source}
from click_extra import echo, group, option

@group
def restaurant():
    """Restaurant management CLI."""

@restaurant.command()
@option("--city", help="City to search in.")
def find(city):
    """Find nearby restaurants."""
    echo(f"Searching in {city}...")

@restaurant.command()
@option("--stars", type=int, help="Minimum star rating.")
def rate(stars):
    """Rate a restaurant."""
    echo(f"Minimum stars: {stars}")
```

```{click:run}
result = invoke(restaurant, args=["help"])
assert result.exit_code == 0
assert "find" in result.stdout
assert "rate" in result.stdout
```

```{click:run}
result = invoke(restaurant, args=["help", "find"])
assert result.exit_code == 0
assert "--city" in result.stdout
```

The `help` subcommand also supports nested groups. If `mycli` has a subgroup `admin` with a command `reset`, then `mycli help admin reset` shows the help for `reset`.

### Searching help

The `--search` option searches all subcommands for matching options or descriptions:

```{click:run}
result = invoke(restaurant, args=["help", "--search", "star"])
assert result.exit_code == 0
assert "rate" in result.stdout
```

### Disabling the help subcommand

Pass `help_command=False` to suppress the auto-injected `help` subcommand:

```{click:source}
from click_extra import group

@group(help_command=False)
def bare_cli():
    """A CLI without the help subcommand."""
```

```{click:run}
result = invoke(bare_cli, args=["help"])
assert result.exit_code == 2
```

If you register your own `help` subcommand, it replaces the auto-injected one.

## Lazily loading subcommands

Click Extra provides a `LazyGroup` class and `@lazy_group` decorator to create command groups that only load their subcommands when they are invoked.

This implementation is based on the one provided in Click's documentation, so refer to the [*Lazily loading subcommands*](https://click.palletsprojects.com/en/stable/complex/#defining-the-lazy-group) section for more details.

Each entry of `lazy_subcommands` maps a subcommand name to the import path of its command object, written as `"<module-name>.<command-object-name>"`:

```{click:source}
:hide-source:
import sys
from types import ModuleType

from click_extra import command, echo

# Stands in for a module the project would ship on disk.
produce_module = ModuleType("produce")

@command
def apple_cli():
    """Count the apples."""
    echo("apples = 3")

@command
def banana_cli():
    """Count the bananas."""
    echo("bananas = 5")

@command
def carrot_cli():
    """Count the carrots."""
    echo("carrots = 7")

produce_module.apple_cli = apple_cli
produce_module.banana_cli = banana_cli
produce_module.carrot_cli = carrot_cli
sys.modules["produce"] = produce_module
```

```{click:source}
from click_extra import lazy_group

@lazy_group(lazy_subcommands={
    "apple": "produce.apple_cli",
    "banana": "produce.banana_cli",
    "carrot": "produce.carrot_cli",
})
def basket():
    """Count the produce."""
```

Invoking `apple` imports the module holding it, and leaves the other subcommands alone:

```{click:run}
result = invoke(basket, args=["apple"])
assert result.exit_code == 0
assert result.stdout == "apples = 3\n"
```

### Registration settings

A bare import path registers its subcommand with Cloup's defaults, which files it under the default help section. Wrap the path in a `LazySubcommand` to carry the settings [`Group.add_command()`](https://cloup.readthedocs.io/en/stable/autoapi/cloup/index.html#cloup.Group.add_command) accepts:

```{click:source}
from click_extra import LazySubcommand, Section, lazy_group

fruits = Section("Fruits")
vegetables = Section("Vegetables")

@lazy_group(lazy_subcommands={
    "carrot": LazySubcommand("produce.carrot_cli", section=vegetables),
    "apple": LazySubcommand("produce.apple_cli", section=fruits),
    "banana": LazySubcommand("produce.banana_cli", section=fruits),
})
def sectioned_basket():
    """Count the produce."""
```

Sections show up in the order they are declared, not in the order their subcommands happen to be imported. `LazyGroup` registers every section as soon as it reads the declaration, so the ordering holds whatever a run imports:

```{click:run}
result = invoke(sectioned_basket, args=["--help"])
assert result.exit_code == 0
listing = result.stdout
assert listing.index("Vegetables:") < listing.index("Fruits:")
assert listing.index("carrot") < listing.index("apple") < listing.index("banana")
```

Set `fallback_to_default_section=False` to keep a subcommand out of every section. It disappears from the help screen, and stays invocable:

```{click:source}
from click_extra import LazySubcommand, lazy_group

@lazy_group(lazy_subcommands={
    "apple": "produce.apple_cli",
    "carrot": LazySubcommand(
        "produce.carrot_cli", fallback_to_default_section=False
    ),
})
def stealth_basket():
    """Count the produce."""
```

```{click:run}
result = invoke(stealth_basket, args=["--help"])
assert result.exit_code == 0
assert "apple" in result.stdout
assert "carrot" not in result.stdout
```

```{click:run}
result = invoke(stealth_basket, args=["carrot"])
assert result.exit_code == 0
assert result.stdout == "carrots = 7\n"
```

```{admonition} Lazy loading and the help screen
:class: note
A help screen prints the short help of every subcommand, so `--help` imports them all. Lazy loading pays off on a plain `mycli apple`, which imports the one module carrying `apple`.
```

## Third-party commands composition

Click Extra is capable of composing with existing Click CLI in various situation.

### Wrap other commands

Click builds hierarchies of commands and subcommands, and Click Extra inherits this. Third-party subcommands can be assembled into a top-level command.

Take an operation team relying daily on a couple of CLIs: [`dbt`](https://github.com/dbt-labs/dbt-core) to manage data workflows, and [`aws-sam-cli`](https://github.com/aws/aws-sam-cli) to deploy them in the cloud.

To wrap all these commands into a single one:

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


@click_extra.group(name="wrap.py")
def main():
    pass


main.add_command(cmd=sam_cli, name="aws_sam")
main.add_command(cmd=dbt_cli, name="dbt")


if __name__ == "__main__":
    main()
```

And this simple script gets rendered into:

```{code-block} shell-session
:emphasize-lines: 49-51
$ uv run -- python ./wrap.py
Usage: wrap.py [OPTIONS] COMMAND [ARGS]...

Options:
  --time / --no-time           Measure and print elapsed execution time.
                               [default: no-time]
  --config LOCATION            Location of the configuration file. Supports
                               local path with glob patterns or remote URL.
                               [default: ~/Library/Application Support/wrap.py/]
  --no-config                  Ignore all configuration files and only use
                               command line parameters and environment
                               variables.
  --validate-config LOCATION   Validate the configuration file and exit.
  --export-config FORMAT       Export the configuration in the selected format
                               to <stdout>, then exit.
  --accessible                 Accessibility mode: disable colors and render
                               tables in a borderless, screen-reader-friendly
                               format.
  --color [auto|always|never]  Colorize the output. A bare --color is the same
                               as --color=always.  [default: auto]
  --no-color                   Disable colorization (alias of --color=never).
  --progress / --no-progress   Show progress indicators during long operations.
                               Disabled for non-interactive output (pipes, dumb
                               terminals, CI) and by --accessible.  [default:
                               progress]
  --theme [auto|dark|dracula|light|manpage|monokai|nord|solarized-dark]
                               Color theme used for help screens.  [default:
                               dark]
  --params                     Show all CLI parameters, their provenance,
                               defaults and value, then exit.
  --table-format FORMAT        Rendering style of tables.  [default: rounded-
                               outline]
  --verbosity LEVEL            Either CRITICAL, ERROR, WARNING, INFO, DEBUG.
                               [default: WARNING]
  -v, --verbose                Increase the default WARNING verbosity by one
                               level for each additional repetition of the
                               option.  [default: 0]
  -q, --quiet                  Decrease the default WARNING verbosity by one
                               level for each additional repetition of the
                               option.  [default: 0]
  --tree                       Show the tree of nested subcommands and exit.
  --man                        Read the command's manual page and exit.
  --help-format [carapace|json|json-full|man|markdown|markdown-full]
                               Render the command in the given format and exit.
  --version                    Show the version and exit.
  -h, --help                   Show this message and exit.

Commands:
  aws_sam  AWS Serverless Application Model (SAM) CLI
  dbt      An ELT tool for managing your SQL transformations and data models.
  help     Show help for a command.
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
    docs NEW! Launch the AWS SAM CLI documentation in a browser.

  Create an App:
    init                Initialize an AWS SAM application.

  Develop your App:
    build               Build your AWS serverless function code.
    local               Run your AWS serverless function locally.
    validate            Validate an AWS SAM template.
    sync NEW! Sync an AWS SAM project to AWS.
    remote NEW! Invoke or send an event to cloud resources in your AWS
                        Cloudformation stack.

  Deploy your App:
    package             Package an AWS SAM application.
    deploy              Deploy an AWS SAM application.

  Monitor your App:
    logs                Fetch AWS Cloudwatch logs for AWS Lambda Functions or
                        Cloudwatch Log groups.
    traces              Fetch AWS X-Ray traces.

  And More:
    list NEW! Fetch the state of your AWS serverless application.
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
    docs NEW! Launch the AWS SAM CLI documentation in a browser.

  Create an App:
    init                Initialize an AWS SAM application.

  Develop your App:
    build               Build your AWS serverless function code.
    local               Run your AWS serverless function locally.
    validate            Validate an AWS SAM template.
    sync NEW! Sync an AWS SAM project to AWS.
    remote NEW! Invoke or send an event to cloud resources in your AWS
                        Cloudformation stack.

  Deploy your App:
    package             Package an AWS SAM application.
    deploy              Deploy an AWS SAM application.

  Monitor your App:
    logs                Fetch AWS Cloudwatch logs for AWS Lambda Functions or
                        Cloudwatch Log groups.
    traces              Fetch AWS X-Ray traces.

  And More:
    list NEW! Fetch the state of your AWS serverless application.
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

The composition can carry custom glue code, simplify redistributing these CLIs on production machines, control their common dependencies, freeze their versions, hard-code parameters, apply monkey-patches, or chain commands into new automation.

If you have other examples in the same vein, share them in an issue or a PR: I'd love to complement this documentation with creative use cases.
```

## `click_extra.commands` API

```{eval-rst}
.. autoclasstree:: click_extra.commands
   :strict:

.. automodule:: click_extra.commands
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
