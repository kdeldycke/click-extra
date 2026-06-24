# {octicon}`terminal` CLI wrapper

Click Extra's `wrap` subcommand runs any installed Click CLI through Click Extra, without modifying the target's source code. By default it applies help colorization, useful for previewing how a third-party CLI would look with Click Extra's keyword highlighting and themed styling. With `--show-params` or `--man`, it instead loads the target and [describes it](#introspecting-external-clis) without running it.

## Usage

The `wrap` subcommand is the default when no known subcommand is given, so both forms work:

```shell-session
$ click-extra wrap -- flask --help
$ click-extra -- flask --help
```

```{click:source}
:hide-source:
from click_extra.cli_wrapper import wrap
```

```{click:run}
result = invoke(wrap, args=["--help"])
assert result.exit_code == 0
assert "Run, or introspect, any Click CLI" in result.stdout
```

````{tip}
`run` is an alias for `wrap`, so you can also use:

```shell-session
$ click-extra run -- flask --help
```
````

## Wrapping a Click CLI

Pass the target CLI name (or path) as the first argument. Everything after it is forwarded to the target:

```shell-session
$ click-extra -- flask --help
$ click-extra -- black --help
$ click-extra -- ./my_script.py --help
$ click-extra -- ../my-project --help
$ click-extra -- my_package.cli:main --help
```

````{tip}
Every example on this page uses the `--` separator to visually split Click Extra's own options from the target CLI and its arguments. It is optional (Click Extra stops parsing its own options at the first token it does not recognize), but using it consistently keeps the two sides of the invocation unambiguous:

```shell-session
$ click-extra --no-color -- flask --help
```
````

## Execution timing

The group-level `--time` flag measures the total execution time of the wrapped CLI, including import and patching overhead:

```shell-session
$ click-extra --time -- flask routes
Execution time: 0.342 seconds.
```

## Color control

`--color` / `--no-color` controls whether ANSI codes are emitted. The flag also respects environment variables like `NO_COLOR`, `CLICOLOR`, and `FORCE_COLOR`:

```shell-session
$ click-extra --no-color -- flask --help
$ NO_COLOR=1 click-extra -- flask --help
```

The group-level `--theme` option selects a color preset for help screens. The flag is part of click-extra's default options, so it works on every click-extra command:

```shell-session
$ click-extra --theme light -- flask --help
```

Custom themes can be registered with `register_theme()` before the CLI is parsed *or* declared inside the `--config` file (see [Custom themes via config](#custom-themes-via-config) below). Either way the new name becomes a valid value for `--theme` for the duration of the invocation.

## Configuration

Click Extra's [configuration file](config.md) support works alongside the wrapper. Group-level options like `verbosity` can be set in `pyproject.toml`:

```toml
[tool.click-extra]
verbosity = "DEBUG"
```

```shell-session
$ click-extra -- flask --help
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
$ click-extra -- flask routes
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
$ click-extra -- flask --app otherapp routes
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
$ click-extra -- flask --help     # rendered with the "midnight" palette
```

Themes loaded this way live on `ctx.meta` for the current invocation only. The module-level `theme_registry` is never mutated, so back-to-back wraps in the same process don't cross-contaminate. See [Themes from your `--config` file](theme.md#themes-from-your-config-file) for the full schema and the validation behavior.

## Script resolution

`SCRIPT` is accepted in five forms, tried in this order:

1. A `console_scripts` entry point exposed by an installed package, the most common case:

   ```{code-block} shell-session
   $ click-extra wrap -- flask --help
   ```

2. A local project directory. Its console-script entry point is read from `pyproject.toml` (`[project.scripts]`) or `setup.cfg` (`console_scripts`), and the directory holding its top-level package is added to `sys.path` so it imports without an install step. This is handy for a checked-out project sitting next to your own:

   ```{code-block} shell-session
   $ click-extra wrap -- ../my-project --help
   ```

   Both the flat layout (the package at the project root) and the src layout (under `src/`) are detected. When several scripts point at *different* targets, pass the right one with `module:function` notation; the error lists the candidates. Adding the directory to `sys.path` makes its package importable, but it does *not* install the project's dependencies, so see [Dependencies of the wrapped CLI](#dependencies-of-the-wrapped-cli) below.

3. A `.py` file path. The file is imported in place, with no install step required:

   ```{code-block} shell-session
   $ click-extra wrap -- path/to/my_cli.py --help
   ```

4. `module:function` notation pointing straight at a Click command object. Useful when the entry point is a wrapper rather than the command itself, or when the command isn't exposed as a console script at all:

   ```{code-block} shell-session
   $ click-extra wrap -- flask.cli:cli --help
   ```

5. A bare Python module name invocable via `python -m`. The resolver imports the module and picks up the Click command from its top-level attributes:

   ```{code-block} shell-session
   $ click-extra wrap -- my_package.cli --help
   ```

The same resolver backs every `wrap` mode, including [`--show-params`](#introspecting-external-clis) and [`--man`](man-page.md#target-resolution).

## Dependencies of the wrapped CLI

`wrap` runs the target inside Click Extra's own interpreter: it imports the resolved module and calls it in-process (see [How it works](#how-it-works)). The target is never installed into a separate environment, so **every third-party package the target imports must already be importable where `wrap` runs**, exactly as if you had launched the target directly.

This bites hardest when [wrapping a project directory](#script-resolution). Pointing `wrap` at a checked-out project makes its package importable by putting it on `sys.path`, but it does *not* install that project's declared dependencies. If the target's CLI imports a package that is absent, the failure surfaces from the target's own code:

```{code-block} shell-session
$ click-extra wrap -- ../weather-cli --help
...
ModuleNotFoundError: No module named 'httpx'
```

A traceback like this means resolution already succeeded and the target started running: the missing module is a dependency of the target, not of Click Extra. It is the same error a direct `python -m weather_cli` would raise.

The lightest fix is to layer the missing packages onto an ephemeral run with [`uv`](https://docs.astral.sh/uv/), one `--with` per dependency:

```{code-block} shell-session
$ uv run --with httpx click-extra wrap -- ../weather-cli --help
```

Alternatively, run `wrap` from an environment that already has the target and its dependencies installed (the target's own virtualenv, for example).

## Ephemeral wrapping with `uvx`

The wrapper pairs well with [`uvx`](https://docs.astral.sh/uv/guides/tools/#running-tools) for one-shot colorization of any Click CLI without permanently installing Click Extra. The ephemeral environment holds only Click Extra, so the target and anything it imports have to be pulled in with `--with` (see [Dependencies of the wrapped CLI](#dependencies-of-the-wrapped-cli) above):

```shell-session
$ uvx --with flask click-extra -- flask --help
$ uvx --with black click-extra -- black --help
```

## How it works

The wrapper monkey-patches Click at two levels before importing the target module:

1. **Decorator defaults**: `@click.command()` and `@click.group()` produce colorized commands when no explicit `cls=` is given.
2. **Method patching**: `click.Command.get_help` and `click.Command.format_help` are patched to inject the colorized formatter and keyword collection on all commands, including those with custom classes (like Flask's `FlaskGroup`).

CLIs already built with Click Extra or Cloup are unaffected by the patching (they already have their own help formatting) but still run correctly through the wrapper.

## Introspecting external CLIs

The `--show-params` flag turns `wrap` into a read-only inspector: it loads any Click CLI without running it and prints a table of every parameter, with its ID, spec, class, type, hidden status, environment variables, and default value. This is the same table the [`--show-params` option](parameters.md#show-params-option) produces for a Click Extra CLI, pointed at a foreign target instead.

```{click:source}
:hide-source:
from click_extra.cli_wrapper import wrap
```

```{click:run}
result = invoke(wrap, args=["--help"])
assert result.exit_code == 0
assert "Show the parameters of the target CLI" in result.stdout
```

Here is Flask's `run` subcommand rendered with the vertical table format:

```{click:run}
result = invoke(wrap, args=["--show-params", "--table-format", "vertical", "--", "flask", "run"])
assert result.exit_code == 0
assert "run.host" in result.output
assert "run.port" in result.output
assert "-p, --port INTEGER" in result.output
```

Because `wrap` resolves the target's own context, the auto-generated environment variables resolve too (Flask sets the `FLASK_` prefix, so `--port` reads `FLASK_RUN_PORT`):

```{click:run}
result = invoke(wrap, args=["--show-params", "--table-format", "vertical", "--columns", "id,envvars", "--", "flask", "run"])
assert result.exit_code == 0
assert "FLASK_RUN_PORT" in result.output
```

### Restricting columns

Pass `--columns` a comma-separated list of column IDs to restrict and reorder the table, SQL `SELECT`-style:

```{click:run}
result = invoke(wrap, args=["--show-params", "--columns", "id,spec,default", "--", "flask", "run"])
assert result.exit_code == 0
assert "run.port" in result.output
```

### Reading values and their source

Any options after `SCRIPT` (and its subcommand path) are replayed against the resolved command, so the `value` and `source` columns report what each parameter would resolve to under those arguments:

```{click:run}
result = invoke(wrap, args=["--show-params", "--columns", "id,value,source", "--", "flask", "run", "--port", "8080"])
assert result.exit_code == 0
assert "8080" in result.output
assert "COMMANDLINE" in result.output
```

### Machine-readable output

All [`--table-format`](table.md#table-formats) renderings are supported. JSON is handy for programmatic consumption:

```{click:run}
result = invoke(wrap, args=["--show-params", "--table-format", "json", "--", "flask", "run"])
assert result.exit_code == 0
assert '"run.port"' in result.output
assert '"Default": 5000' in result.output
```

### Subcommand drilling

Extra arguments after `SCRIPT` navigate into nested command groups; the table then scopes to the resolved node:

```shell-session
$ click-extra wrap --show-params -- flask run
$ click-extra wrap --show-params -- flask routes
```

### Target resolution

Target resolution follows [the same order as the default mode](#script-resolution): a `console_scripts` entry point, a local project directory, a `.py` file path, `module:function` notation, or a bare Python module name.

When the resolved entry point is a wrapper function (not a Click command), the module is scanned for Click command instances. If a single command group is found, it is used automatically. If multiple candidates exist, the error message lists them so you can use explicit `module:name` notation:

```shell-session
$ click-extra wrap --show-params -- flask.cli:cli
```

Some CLIs import their Click command *lazily*: a `__main__:main` wrapper that runs `from my_package.cli import cli` only when called, for instance. The module scan then finds nothing at the top level and `wrap` reports `No Click command found in my_package.__main__`. Introspection cannot recover the command from such an entry point, nor from the project directory that resolves to it, because running the wrapper is the only thing that would import the command. Point it instead at the module that *defines* the command with `module:function` notation, making the package importable if it is not installed:

```shell-session
$ PYTHONPATH=../my-project click-extra wrap --man -- my_package.cli:cli
```

## `click_extra.cli_wrapper` API

```{eval-rst}
.. autoclasstree:: click_extra.cli_wrapper
   :strict:

.. automodule:: click_extra.cli_wrapper
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
