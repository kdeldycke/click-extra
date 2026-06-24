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
