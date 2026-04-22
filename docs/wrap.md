# {octicon}`terminal` CLI wrapper

Click Extra ships a `click-extra` command that applies its help colorization to any installed Click CLI, without modifying the target's source code. This is useful for previewing how a third-party CLI would look with Click Extra's keyword highlighting and themed styling.

## Usage

```{click:source}
:hide-source:
from click_extra.wrap import wrapper
```

```{click:run}
result = invoke(wrapper, args=["--help"])
assert result.exit_code == 0
assert "Apply Click Extra help colorization" in result.stdout
assert "--color" in result.stdout
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

`--color` / `--no-color` (`--ansi` / `--no-ansi`)
: Enable or disable ANSI colors in the wrapped CLI output.

`--theme` `dark` | `light`
: Color theme preset for help screen styling.

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

## Limitations

The wrapper monkey-patches Click's `@click.command()` and `@click.group()` decorator functions before importing the target module. This covers CLIs built with standard Click decorators. CLIs that create commands programmatically (like `click.Command(...)`) or use custom command classes with explicit `cls=` arguments are not affected by the patching.

CLIs already built with Click Extra or Cloup are unaffected by the patching (they already have their own help formatting) but still run correctly through the wrapper.
