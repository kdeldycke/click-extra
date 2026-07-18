# {octicon}`workflow` Command tree

The `--tree` flag prints the whole hierarchy of nested subcommands at once, with their one-line descriptions. It is a constant-cost overview of a CLI's shape: without it, mapping an unfamiliar command set means walking `--help` screens one level at a time, or generating a full [man page](man-page.md) or [completion spec](carapace.md) dump.

It is also the hierarchical companion of [`--params`](parameters.md#params-option): where the parameter table flattens the command tree into dotted IDs (`cli.subcommand.param`), `--tree` renders the skeleton those IDs hang off, without the parameter noise.

## `--tree` flag

The flag is part of the [default options](tutorial.md#available-options), so every CLI built with `@command` or `@group` exposes it:

```{click:source}
from click_extra import argument, group

@group
def observatory():
    """Weather observatory control center."""

@observatory.group(aliases=["st"])
def station():
    """Manage remote weather stations."""

@station.command()
def calibrate():
    """Recalibrate the sensors."""

@station.command(deprecated=True)
def reboot():
    """Power-cycle the station."""

@observatory.command()
@argument("city")
def report(city):
    """Print the forecast for a city."""

@observatory.command()
def status():
    """Report the current conditions."""

@observatory.command(hidden=True)
def diagnose():
    """Internal diagnostics."""
```

```{click:run}
result = invoke(observatory, args=["--tree"])
assert result.exit_code == 0
assert "station" in result.stdout
assert "calibrate" in result.stdout
assert "CITY" in result.stdout
assert "(Deprecated)" in result.stdout
assert "├── " in result.stdout
assert "└── " in result.stdout
assert "diagnose" not in result.stdout
```

The rendering mirrors help screens: subcommands are discovered dynamically (so lazily-registered commands are included), listed in the same order, hidden ones are skipped, aliases are parenthesized, operand metavars follow each name like on the usage line (`report CITY`), and deprecated commands carry their `(Deprecated)` marker. Descriptions are column-aligned and wrap at the terminal width, with the tree rail running through the wrapped lines. Everything is styled with the same [theme slots](theme.md) as help screens (`invoked_command` for the root, `subcommand` and `alias` below, `metavar` for operands), so the tree follows `--theme` and `--color` like every other output.

Options are deliberately absent from the tree: their exhaustive inventory is [`--params`](parameters.md#params-option)' job.

Like the [completion spec](carapace.md#commands-discovered-from-external-state), the tree is a point-in-time snapshot: a group that computes its subcommands from external state (a loaded application, installed plugins, a scanned directory) renders exactly what its `list_commands` returns at that moment.

## Accessibility

Box-drawing characters are hostile to screen readers, which either skip them or spell out their Unicode names. Under [accessibility mode](colorize.md#accessible-flag), the rail degrades to the pure-ASCII set `tree(1)` uses with `--charset=ascii`:

```{click:run}
result = invoke(observatory, args=["--accessible", "--tree"])
assert result.exit_code == 0
assert "├── " not in result.stdout
assert "|-- " in result.stdout
assert "`-- " in result.stdout
```

## Foreign CLIs

`click-extra wrap --tree -- SCRIPT` resolves a target, loads its Click command, and prints its tree without running it. SCRIPT is [resolved the same way](wrap.md#script-resolution) as for the other [introspection modes](wrap.md#introspecting-external-clis), so with uvx nothing needs to be installed up front:

```{code-block} shell-session
$ uvx --from click-extra --with flask click-extra wrap --tree -- flask
```

```{click:run}
:hide-source:
from click_extra.cli_wrapper import wrap
result = invoke(wrap, args=["--tree", "--", "flask"])
assert result.exit_code == 0
assert "routes" in result.stdout
assert "run" in result.stdout
assert "shell" in result.stdout
```

The error line above is Flask itself: its group computes part of its command list from the application, and without one only the static commands render. That is the point-in-time snapshot caveat made visible.

Extra arguments after SCRIPT navigate into nested command groups and re-root the tree at the resolved node, exactly like [subcommand drilling](wrap.md#subcommand-drilling) for `--params`:

```{code-block} shell-session
$ click-extra wrap --tree -- flask run
```

## Structure vs. inventory

`--tree` and `--params` are two projections of the same walk, and answer different questions:

- `--tree` is **command-level, hierarchical, static**: which subcommands exist and how they nest. No values, no options.
- [`--params`](parameters.md#params-option) is **parameter-level, flat, runtime**: one row per parameter with its type, environment variable, default, current value and provenance.

The tree is a human rendering only. Machine-readable hierarchies are already covered: `--params --table-format json` serializes every parameter with its dotted path, and [`--carapace`](carapace.md) serializes the whole command-and-flag tree as YAML.

## Standalone option

Use the `@tree_option` decorator to add the flag to a plain Click CLI, outside of Click Extra's `@command` and `@group`:

```{click:source}
import click

from click_extra import tree_option

@click.group
@tree_option
def produce():
    """Manage a produce stand."""

@produce.command()
def restock():
    """Restock the shelves."""
```

```{click:run}
result = invoke(produce, args=["--tree"])
assert result.exit_code == 0
assert "restock" in result.stdout
```

## `click_extra.tree` API

```{eval-rst}
.. autoclasstree:: click_extra.tree
   :strict:

.. automodule:: click_extra.tree
   :members:
   :undoc-members:
   :show-inheritance:
```
