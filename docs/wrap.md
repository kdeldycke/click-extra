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

The group-level `--theme` option selects a color preset for help screens. The flag is part of click-extra's default options, so it works on every click-extra command:

```shell-session
$ click-extra --theme light flask --help
```

Custom themes can be registered with `register_theme()` before the CLI is parsed *or* declared inside the `--config` file (see [Custom themes via config](#custom-themes-via-config) below). Either way the new name becomes a valid value for `--theme` for the duration of the invocation.

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

The `[tool.click-extra.wrap.<script>]`{l=toml} section sets persistent defaults for a specific target CLI. All keys are converted to CLI arguments and prepended to the target's invocation:

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

### Custom themes via config

The `--config` flag also accepts theme overrides and brand-new theme definitions. Drop a `[tool.click-extra.themes.<name>]` table into the same `pyproject.toml` and the new palette is loaded before `--theme` is validated, so it can be selected on the command line or pinned via `theme = "..."`:

```toml
[tool.click-extra]
theme = "midnight"

# Override one slot of the built-in `dark` theme:
[tool.click-extra.themes.dark]
option = { fg = "bright_cyan" }

# Define a fresh palette named "midnight":
[tool.click-extra.themes.midnight]
option = { fg = "blue", bold = true }
heading = { fg = "magenta" }
choice = { fg = "yellow" }
```

```shell-session
$ click-extra --help
# --theme [dark|dracula|light|manpage|midnight|monokai|nord|solarized_dark]
$ click-extra flask --help     # rendered with the "midnight" palette
```

Themes loaded this way live on `ctx.meta` for the current invocation only. The module-level `theme_registry` is never mutated, so back-to-back wraps in the same process don't cross-contaminate. See [Themes from your `--config` file](theme.md#themes-from-your-config-file) for the full schema and the validation behavior.

## Script resolution

`SCRIPT` is accepted in four forms, tried in this order:

1. A `console_scripts` entry point exposed by an installed package, the most common case:

   ```{code-block} shell-session
   $ click-extra wrap flask --help
   ```

2. `module:function` notation pointing straight at a Click command object. Useful when the entry point is a wrapper rather than the command itself, or when the command isn't exposed as a console script at all:

   ```{code-block} shell-session
   $ click-extra wrap flask.cli:cli --help
   ```

3. A `.py` file path. The file is imported in place, with no install step required:

   ```{code-block} shell-session
   $ click-extra wrap path/to/my_cli.py --help
   ```

4. A bare Python module name invocable via `python -m`. The resolver imports the module and picks up the Click command from its top-level attributes:

   ```{code-block} shell-session
   $ click-extra wrap my_package.cli --help
   ```

The same resolver is shared with `show-params` and [`man`](man-page.md#target-resolution).

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
from click_extra.cli import demo
```

```{click:run}
result = invoke(demo, args=["show-params", "--help"])
assert result.exit_code == 0
assert "Show parameters of an external Click CLI" in result.stdout
```

Here is an example introspecting Flask's `run` subcommand with the vertical table format:

```{click:run}
result = invoke(demo, args=["--table-format", "vertical", "show-params", "flask", "run"])
assert result.exit_code == 0
assert "run.host" in result.output
assert "run.port" in result.output
assert "-p, --port INTEGER" in result.output
```

All `--table-format` renderings are supported. JSON output is useful for programmatic consumption:

```{click:run}
result = invoke(demo, args=["--table-format", "json", "show-params", "flask", "run"])
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

Target resolution follows [the same order as `wrap`](#script-resolution): a `console_scripts` entry point, `module:function` notation, a `.py` file path, or a bare Python module name.

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
