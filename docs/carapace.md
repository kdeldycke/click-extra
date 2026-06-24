# {octicon}`terminal` Carapace completion

## Generating a spec

[Carapace](https://carapace.sh) is a multi-shell completion engine: one spec file drives identical completions across Bash, Zsh, Fish, Nushell, PowerShell, Elvish, Xonsh and more. `click_extra.carapace` walks a Click command tree and serializes it to the [carapace-spec](https://github.com/carapace-sh/carapace-spec) YAML format, so a CLI gets completion everywhere Carapace runs. This is Click Extra's answer to [`click#3188`](https://github.com/pallets/click/issues/3188), the request for native Carapace support that fell outside the scope of core Click.

The spec is produced mechanically from the command itself, on any Click command *object* (no `console_scripts` entry point required). Take a small CLI:

```{click:source}
import click

@click.group()
def weather():
    """Show the weather."""

@weather.command()
@click.option("--unit", type=click.Choice(["celsius", "fahrenheit"]), help="Scale.")
@click.option("--report", type=click.Path(exists=True), help="Read a saved report.")
@click.argument("city")
def forecast(unit, report, city):
    """Forecast for a CITY."""
```

`dump_carapace_spec` renders its spec. Choices are inlined, a path operand becomes the `$files` action, and the subcommand tree is reproduced verbatim:

```{click:run}
@click.command()
def emit():
    from click_extra.carapace import dump_carapace_spec

    click.echo(dump_carapace_spec(weather, prog_name="weather"))

result = invoke(emit)
assert result.exit_code == 0
assert "name: weather" in result.stdout
assert "celsius" in result.stdout
assert result.stdout.count("$files") == 1
```

## The wrap `--carapace` mode

`click-extra wrap --carapace SCRIPT` resolves a target, loads its Click command, and prints the whole tree's spec to stdout without running it. SCRIPT is [resolved the same way](wrap.md#script-resolution) as for `--man`, so nothing needs to be installed up front with uvx:

```{code-block} shell-session
$ uvx --from "click-extra[carapace]" --with flask click-extra wrap --carapace flask > flask.yaml
```

`--carapace` must appear *before* SCRIPT, since arguments after SCRIPT navigate into nested subcommands. It is mutually exclusive with `--man` and `--show-params`.

Pass `--install` to write the spec straight into Carapace's user spec directory (`$XDG_CONFIG_HOME/carapace/specs/`, which Carapace loads on startup) instead of printing it:

```{code-block} shell-session
$ uvx --from "click-extra[carapace]" --with flask click-extra wrap --carapace --install flask
/home/me/.config/carapace/specs/flask.yaml
```

## Commands discovered from external state

The spec is a point-in-time snapshot of the command tree. Most groups expose a fixed set of subcommands, but some compute theirs from external state: a loaded application, installed plugins, or a scanned directory. The exporter walks the tree through the group's own `list_commands` and `get_command`, so the spec captures exactly what those return at generation time. Anything the group cannot see at that moment is left out.

A group that registers an extra command only when an optional integration is configured shows the effect. Here that integration is stood in for by the `GARDEN_PLOTS` environment variable:

```{click:source}
import os
import click

@click.command()
def water():
    """Water the garden."""

@click.command()
def harvest():
    """Pick ripe produce."""

class GardenGroup(click.Group):
    """A garden that grows an extra command once its plots are configured."""

    def list_commands(self, ctx):
        names = ["water"]
        if os.environ.get("GARDEN_PLOTS"):
            names.append("harvest")
        return names

    def get_command(self, ctx, name):
        return {"water": water, "harvest": harvest}.get(name)

garden = GardenGroup(name="garden", help="Tend a garden.")
```

With nothing configured, only the built-in `water` reaches the spec; configuring `GARDEN_PLOTS` brings `harvest` in:

```{click:run}
@click.command()
def emit():
    import os

    from click_extra.carapace import dump_carapace_spec

    os.environ.pop("GARDEN_PLOTS", None)
    click.echo(dump_carapace_spec(garden, prog_name="garden"))

    os.environ["GARDEN_PLOTS"] = "1"
    try:
        full = dump_carapace_spec(garden, prog_name="garden")
    finally:
        os.environ.pop("GARDEN_PLOTS", None)
    click.echo(f"harvest available once configured: {'name: harvest' in full}")

result = invoke(emit)
assert result.exit_code == 0
assert "name: water" in result.stdout
assert "name: harvest" not in result.stdout
assert "harvest available once configured: True" in result.stdout
```

[Flask](https://flask.palletsprojects.com) hits this in practice. Its `flask` command lists the built-in `routes`, `run` and `shell`, then adds whatever commands the loaded application registered, so it needs to find an application to enumerate the full set. Wrap it with none in reach and the spec carries only the three built-ins, alongside the red `Could not locate a Flask application` error Flask prints to stderr. That error is Flask's own and is not fatal: Flask catches it, falls back to the built-ins and carries on, so the YAML on stdout stays valid, only incomplete. Point Flask at an application through the `FLASK_APP` environment variable (or a `wsgi.py` or `app.py` in the working directory) and the error clears and the application's own commands join the spec:

```{code-block} shell-session
$ FLASK_APP=myapp uvx --from "click-extra[carapace]" --with flask click-extra wrap --carapace flask > flask.yaml
```

The `flask --app` option cannot stand in here: the spec is built without running Flask's own argument parsing, so the application must be discoverable from the environment or the working directory.

## Static and dynamic completion

Two strategies cooperate, and the generator picks per parameter:

- **Static.** Choices, file and directory operands, and the command hierarchy are frozen into the spec. They complete with no process launch and work in every shell Carapace supports: this is what a spec buys over Carapace's bridge to a single shell's native Click completion.

- **Dynamic.** A parameter with a custom `shell_complete` (a callback, or a [`ParamType`](https://click.palletsprojects.com/en/stable/api/#click.ParamType) that overrides `shell_complete`) cannot be frozen, so its spec action calls back into the CLI. The callback reuses Click's own completion machinery through the `carapace` completion class, registered on `import click_extra`.

Dynamic completion therefore needs that class registered in the target process, which a CLI built with Click Extra gets automatically. A plain Click CLI would have to `import click_extra` for the callback to resolve. Static completion has no such requirement.

A click-extra command also carries its [default options](commands.md) (`--version`, `--verbosity`, `--color`, and the rest). On the root command these are emitted as Carapace `persistentflags`, so every subcommand inherits them without the spec repeating them.

## Programmatic API

Three entry points cover the Python side, from a string to an installed file:

1. `to_carapace_spec(cli, prog_name=...)` returns the spec as a plain dict, ready for `yaml.safe_dump` or further processing. It needs no optional dependency.

2. `dump_carapace_spec(cli, prog_name=...)` serializes that dict to a YAML string with a provenance header.

3. `write_carapace_spec(cli, target, prog_name=...)` writes the YAML to a path, and `install_carapace_spec(cli, prog_name=...)` writes it to Carapace's user spec directory and returns the path.

## Installation

YAML serialization (`dump_carapace_spec`, `write_carapace_spec`, `install_carapace_spec`, and `wrap --carapace`) needs PyYAML, pulled by the `carapace` extra:

```{code-block} shell-session
$ pip install "click-extra[carapace]"
```

`to_carapace_spec` and the `carapace` completion class work without it.

## Known limitations

- Cloup constraints beyond mutual exclusion (`RequireAtLeast`, `RequireExactly`, `If`) have no carapace-spec equivalent and are dropped: only `@option_group(..., constraint=mutually_exclusive)` becomes `exclusiveflags`.
- The dynamic callback hands the already-typed words to Carapace and lets it filter, so a parameter whose `shell_complete` does its own non-prefix filtering completes more broadly through the spec than it would natively.

## `click_extra.carapace` API

```{eval-rst}
.. autoclasstree:: click_extra.carapace
   :strict:

.. automodule:: click_extra.carapace
   :members:
   :undoc-members:
   :show-inheritance:
```
