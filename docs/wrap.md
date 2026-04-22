# {octicon}`terminal` CLI wrapper

Click Extra's `run` subcommand applies its help colorization to any installed Click CLI, without modifying the target's source code. This is useful for previewing how a third-party CLI would look with Click Extra's keyword highlighting and themed styling.

## Usage

The `run` subcommand is the default when no known subcommand is given, so both forms work:

```shell-session
$ click-extra run flask --help
$ click-extra flask --help
```

```{click:source}
:hide-source:
from click_extra.wrap import run
```

```{click:run}
result = invoke(run, args=["--help"])
assert result.exit_code == 0
assert "Apply Click Extra help colorization" in result.stdout
assert "--theme" in result.stdout
```

## Wrapping a Click CLI

Pass the target CLI name (or path) as the first argument. Everything after it is forwarded to the target:

```shell-session
$ click-extra flask --help
$ click-extra black --help
$ click-extra ./my_script.py --help
$ click-extra my_package.cli:main --help
```

A `--` separator is optional but supported:

```shell-session
$ click-extra --no-color -- flask --help
```

## Options

The group-level `--color` / `--no-color` (`--ansi` / `--no-ansi`) flag controls whether ANSI codes are emitted. It also respects environment variables like `NO_COLOR`, `CLICOLOR`, and `FORCE_COLOR`:

```shell-session
$ click-extra --no-color flask --help
$ NO_COLOR=1 click-extra flask --help
```

The `--theme` option on `run` selects a color preset:

```shell-session
$ click-extra run --theme light flask --help
```

## Script resolution

The `SCRIPT` argument is resolved in this order:

1. **Console scripts entry point**: any package installed with `pip install` or `uv add` that registers a `console_scripts` entry point. This covers most CLI tools.
2. **`module:function` notation**: explicit import path like `my_app.cli:main`.
3. **`.py` file path**: a local Python script.
4. **Python module name**: a bare module or package name invokable via `python -m`.

## Ephemeral wrapping with `uvx`

The wrapper is particularly useful with [`uvx`](https://docs.astral.sh/uv/reference/cli/#uvx) for one-shot colorization of any Click CLI without permanently installing Click Extra:

```shell-session
$ uvx click-extra flask --help
$ uvx click-extra black --help
```

## How it works

The wrapper monkey-patches Click at two levels before importing the target module:

1. **Decorator defaults**: `@click.command()` and `@click.group()` produce colorized commands when no explicit `cls=` is given.
2. **Method patching**: `click.Command.get_help` and `click.Command.format_help` are patched to inject the colorized formatter and keyword collection on all commands, including those with custom classes (like Flask's `FlaskGroup`).

CLIs already built with Click Extra or Cloup are unaffected by the patching (they already have their own help formatting) but still run correctly through the wrapper.
