# {octicon}`terminal` CLI wrapper

Click Extra's `wrap` subcommand applies its help colorization to any installed Click CLI, without modifying the target's source code. This is useful for previewing how a third-party CLI would look with Click Extra's keyword highlighting and themed styling.

## Usage

The `wrap` subcommand is the default when no known subcommand is given, so both forms work:

```shell-session
$ click-extra wrap flask --help
$ click-extra flask --help
```

```{click:source}
:hide-source:
from click_extra.wrap import wrap
```

```{click:run}
result = invoke(wrap, args=["--help"])
assert result.exit_code == 0
assert "Apply Click Extra help colorization" in result.stdout
assert "--theme" in result.stdout
```

````{tip}
`run` is an alias for `wrap`, so you can also use:

```shell-session
$ click-extra run flask --help
```
````

## Wrapping a Click CLI

Pass the target CLI name (or path) as the first argument. Everything after it is forwarded to the target:

```shell-session
$ click-extra flask --help
$ click-extra black --help
$ click-extra ./my_script.py --help
$ click-extra my_package.cli:main --help
```

````{tip}
An optional `--` separator is available which you can use for visually separating Click Extra from the target CLI:

```shell-session
$ click-extra --no-color -- flask --help
```
````

## Execution timing

The group-level `--time` flag measures the total execution time of the wrapped CLI, including import and patching overhead:

```shell-session
$ click-extra --time flask routes
Execution time: 0.342 seconds.
```

## Color control

`--color` / `--no-color` (`--ansi` / `--no-ansi`) controls whether ANSI codes are emitted. The flag also respects environment variables like `NO_COLOR`, `CLICOLOR`, and `FORCE_COLOR`:

```shell-session
$ click-extra --no-color flask --help
$ NO_COLOR=1 click-extra flask --help
```

The `--theme` option on `wrap` selects a color preset:

```shell-session
$ click-extra wrap --theme light flask --help
```

## Configuration

Click Extra's [configuration file](config.md) support works alongside the wrapper. Group-level options like `verbosity` can be set in `pyproject.toml`:

```toml
[tool.click-extra]
verbosity = "DEBUG"
```

```shell-session
$ click-extra flask --help
debug: Set <Logger click_extra (DEBUG)> to DEBUG.
...
```

### Defaults for the wrapped CLI

The `[tool.click-extra.wrap.<script>]` section sets persistent defaults for a specific target CLI. All keys are converted to CLI arguments and prepended to the target's invocation:

```toml
[tool.click-extra.wrap.flask]
app = "myapp:create_app"
debug = true
```

```shell-session
$ click-extra flask routes
# Equivalent to: flask --app myapp:create_app --debug routes
```

The section name must match the script name you pass on the command line. Multiple targets can each have their own section:

```toml
[tool.click-extra.wrap.flask]
app = "myapp:create_app"

[tool.click-extra.wrap.quart]
app = "otherapp:create_app"
```

Explicit CLI arguments always override config values:

```shell-session
$ click-extra flask --app otherapp routes
# CLI --app wins over config
```

Invalid option names are caught by the target CLI itself with standard Click error messages, so typos are surfaced immediately.

## Script resolution

The `SCRIPT` argument is resolved in this order:

1. **Console scripts entry point**: any package installed with `pip install` or `uv add` that registers a `console_scripts` entry point. This covers most CLI tools.
2. **`module:function` notation**: explicit import path like `my_app.cli:main`.
3. **`.py` file path**: a local Python script.
4. **Python module name**: a bare module or package name invocable via `python -m`.

## Ephemeral wrapping with `uvx`

The wrapper is particularly useful with [`uvx`](https://docs.astral.sh/uv/guides/tools/#running-tools) for one-shot colorization of any Click CLI without permanently installing Click Extra:

```shell-session
$ uvx click-extra -- flask --help
$ uvx click-extra -- black --help
```

## How it works

The wrapper monkey-patches Click at two levels before importing the target module:

1. **Decorator defaults**: `@click.command()` and `@click.group()` produce colorized commands when no explicit `cls=` is given.
2. **Method patching**: `click.Command.get_help` and `click.Command.format_help` are patched to inject the colorized formatter and keyword collection on all commands, including those with custom classes (like Flask's `FlaskGroup`).

CLIs already built with Click Extra or Cloup are unaffected by the patching (they already have their own help formatting) but still run correctly through the wrapper.

## Introspecting external CLIs

The `show-params` subcommand inspects the parameters of any Click CLI without running it. It displays a table with each parameter's ID, spec, class, type, hidden status, environment variables, and default value.

```{click:source}
:hide-source:
from click_extra.cli import show_params_cmd
```

```{click:run}
result = invoke(show_params_cmd, prog_name="click-extra show-params", args=["--help"])
assert result.exit_code == 0
assert "Show parameters of an external Click CLI" in result.stdout
assert "--table-format" in result.stdout
```

Here is an example introspecting Flask's `run` subcommand with the vertical table format:

```{click:run}
result = invoke(show_params_cmd, prog_name="click-extra show-params", args=["--table-format", "vertical", "flask", "run"])
assert result.exit_code == 0
assert "run.host" in result.output
assert "run.port" in result.output
assert "-p, --port INTEGER" in result.output
```

All `--table-format` renderings are supported. JSON output is useful for programmatic consumption:

```{click:run}
result = invoke(show_params_cmd, prog_name="click-extra show-params", args=["--table-format", "json", "flask", "run"])
assert result.exit_code == 0
assert '"run.port"' in result.output
assert '"Default": 5000' in result.output
```

### Subcommand drilling

Extra arguments after `SCRIPT` navigate into nested command groups:

```shell-session
$ click-extra show-params -- flask run
$ click-extra show-params -- flask routes
```

### Target resolution

Target resolution follows the same order as `wrap`: console_scripts entry points, `module:function` notation, `.py` file paths, and Python module names.

When the resolved entry point is a wrapper function (not a Click command), the module is scanned for Click command instances. If a single command group is found, it is used automatically. If multiple candidates exist, the error message lists them so you can use explicit `module:name` notation:

```shell-session
$ click-extra show-params -- flask.cli:cli
```

### `click_extra.wrap` API

```{eval-rst}
.. autoclasstree:: click_extra.wrap
   :strict:

.. automodule:: click_extra.wrap
   :members:
   :undoc-members:
   :show-inheritance:
```
