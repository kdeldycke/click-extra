# {octicon}`git-compare` Typer compatibility

[Typer](https://typer.tiangolo.com) builds command-line interfaces from function type hints, on top of Click. Since click-extra also builds on Click, it is natural to expect the two to combine: a Typer app that picks up click-extra's configuration loading, logging and themed help. They do not combine, and this page explains why, and what to reach for instead.

## Why click-extra and Typer don't compose

click-extra extends the Click and [Cloup](https://cloup.readthedocs.io) classes installed in your environment: its commands, options and context all derive from them. Recent Typer bundles its own private copy of Click instead of using the one click-extra extends. A Typer command therefore subclasses Typer's bundled `Command`, a different class from the `click.Command` that click-extra subclasses, even though both descend from a common Click codebase.

Because the two come from separate class lineages, they cannot be merged. A hybrid such as `class MyCommand(click_extra.Command, TyperCommand)` is a valid class declaration, but it inherits two unrelated `Command` implementations at once and cannot be instantiated: Typer hands it arguments that click-extra's Click base does not accept. Construction aside, click-extra's options are `click.Parameter` objects that Typer's bundled parser does not recognize, so they would never be parsed. No `cls=` argument or runtime patch bridges this: the gap is between two copies of Click, not between two ways of using one.

## How this differs from rich-click

[rich-click](https://ewels.github.io/rich-click/) does integrate with Typer, through its [`patch_typer()`](https://ewels.github.io/rich-click/latest/documentation/typer_support/) helper, which can look like a counterexample. The difference is in what each library changes. rich-click only restyles the help *output*: it overrides how help is rendered and leaves Typer's own command construction and parsing untouched, so it never crosses the Click-lineage boundary.

click-extra's value is the opposite kind of work. Its features run *during parsing*: `--config` loads a file and feeds it into the command's defaults, `--verbosity` configures logging, `--color` and `--version` resolve ahead of the rest. That requires being a working Click command inside the same parser that runs it, which is exactly what Typer's bundled Click forecloses. Restyling output transfers to Typer; parse-time behavior does not.

## Using click-extra's features instead

If you want the options Typer lacks (configuration files, logging control, a metadata-aware `--version`, themed help), build the CLI with click-extra's own decorators. `@command` and `@group` are drop-in replacements for Click's, and they add the full set of extra options automatically:

```{click:source}
from click_extra import command, option

@command
@option("--unit", help="Temperature scale.")
def forecast(unit):
    """Show today's forecast."""
```

The extra options are there without declaring them:

```{click:run}
result = invoke(forecast, args=["--help"])
assert result.exit_code == 0
assert "--config" in result.output
assert "--verbosity" in result.output
assert "--version" in result.output
```

See the [tutorial](tutorial.md) and [commands](commands.md) pages for the full feature set. The trade-off is the authoring style: click-extra defines parameters with explicit `@option` and `@argument` decorators rather than from function type hints. If type-hint-driven definition matters more than the extra options, stay on Typer and reach for rich-click to prettify its help.
