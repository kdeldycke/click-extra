# {octicon}`database` Context state

Click Extra's option callbacks publish their resolved values on [Click's `Context.meta` dict](https://click.palletsprojects.com/en/stable/api/#click.Context.meta). That dict is **shared across the parent/child context hierarchy** and lives for the duration of a single CLI invocation, so it doubles as a per-request shared bus between Click Extra's eager callbacks and your own command body.

If you are writing a `@command`- or `@group`-decorated function, you can read any of the entries below at any point: in the function body, in a parameter callback, in a `@pass_context` consumer, or in a subcommand of a group that declared one of the options. Click Extra's default options (`--verbosity`, `--theme`, `--config`, `--time`, etc.) are wired in automatically by `@command` / `@group`, so the corresponding entries are populated without you having to opt in.

## Picking values up from your own callbacks

Every key Click Extra owns lives under the `click_extra.` namespace and is exposed as a constant in the `click_extra.context` module:

```{click:source}
from click_extra import command, context, echo, pass_context

@command
@pass_context
def status(ctx):
    """Print a status line tagged with the current verbosity."""
    level = ctx.meta[context.VERBOSITY_LEVEL]
    echo(f"[{level}] all systems nominal.")
```

```{click:run}
result = invoke(status, args=["--verbosity", "INFO"])
assert result.exit_code == 0
assert "[INFO] all systems nominal." in result.stdout
```

You may also reach the same entry through the literal string (`ctx.meta["click_extra.verbosity_level"]`): the constants only fix the spelling in one place and document who owns each entry.

(available-keys)=
## Available keys

The table below lists every entry Click Extra writes, the option that triggers it, and the value's shape. Entries marked *write-only* are not read back internally: they exist so your code can inspect what the user picked.

| Constant                   | String key                       | Set by                                                     | Value                                                                  |
| -------------------------- | -------------------------------- | ---------------------------------------------------------- | ---------------------------------------------------------------------- |
| `context.RAW_ARGS`        | `click_extra.raw_args`           | `ExtraCommand.make_context` (always, on `@command` group)  | `list[str]` — pre-parsed `argv` slice fed to the current command       |
| `context.CONF_SOURCE`     | `click_extra.conf_source`        | `ConfigOption.load_conf` (`@config_option`)                | `pathlib.Path \| URL \| None` — file the configuration was loaded from |
| `context.CONF_FULL`       | `click_extra.conf_full`          | `ConfigOption.load_conf` (`@config_option`)                | `dict \| None` — full parsed configuration document                    |
| `context.TOOL_CONFIG`     | `click_extra.tool_config`        | `ConfigOption._apply_config_schema` (with `config_schema`) | The deserialised app section (also reachable via `get_tool_config()`)  |
| `context.VERBOSITY_LEVEL` | `click_extra.verbosity_level`    | `--verbosity` / `--verbose` callbacks (reconciled)         | `LogLevel` — the highest level any verbosity option picked             |
| `context.VERBOSITY`       | `click_extra.verbosity`          | `--verbosity` callback                                     | `LogLevel` — raw value of `--verbosity LEVEL` *(write-only)*           |
| `context.VERBOSE`         | `click_extra.verbose`            | `--verbose` / `-v` callback                                | `int` — repetition count *(write-only)*                                |
| `context.START_TIME`      | `click_extra.start_time`         | `--time` callback (`@timer_option`)                        | `float` — `time.perf_counter()` snapshot                               |
| `context.JOBS`            | `click_extra.jobs`               | `--jobs` callback (`@jobs_option`)                         | `int` — effective parallel job count (clamped to >= 1)                 |
| `context.TABLE_FORMAT`    | `click_extra.table_format`       | `--table-format` callback (`@table_format_option`)         | `TableFormat`                                                          |
| `context.SORT_BY`         | `click_extra.sort_by`            | `--sort-by` callback (`@sort_by_option`)                   | `tuple[str, ...]` — column IDs in priority order                       |
| `context.THEME`           | `click_extra.theme.active`       | `--theme` callback (always present on `@command`)          | `HelpExtraTheme` — palette picked for this invocation                  |

## Worked examples

### Switching behaviour on the active theme

```{click:source}
from click_extra import command, context, echo, pass_context

@command
@pass_context
def report(ctx):
    """Render a status line in the active theme's success colour."""
    theme = ctx.meta[context.THEME]
    echo(theme.success("OK"))
```

```{click:run}
result = invoke(report, args=["--theme", "dark"])
assert result.exit_code == 0
assert "OK" in result.stdout
```

### Driving parallelism off `--jobs`

`--jobs` is not part of the default options, so it has to be added explicitly via `@jobs_option`:

```{click:source}
from click_extra import command, context, echo, jobs_option, pass_context

@command
@jobs_option
@pass_context
def crunch(ctx):
    """Demonstrate reading the resolved `--jobs` value."""
    echo(f"Working with {ctx.meta[context.JOBS]} workers.")
```

```{click:run}
result = invoke(crunch, args=["--jobs", "4"])
assert result.exit_code == 0
assert "Working with 4 workers." in result.stdout
```

### Inspecting the loaded configuration

`--config` is part of the default options. The block below uses `--no-config` to skip discovery, then reads `CONF_SOURCE` to confirm no file was loaded:

```{click:source}
from click_extra import command, context, echo, pass_context

@command
@pass_context
def show_conf(ctx):
    """Print which configuration file (if any) was loaded."""
    source = ctx.meta.get(context.CONF_SOURCE)
    echo(f"config: {source or 'none'}")
```

```{click:run}
result = invoke(show_conf, args=["--no-config"])
assert result.exit_code == 0
assert "config: none" in result.stdout
```

## Reaching the context outside the command body

Inside a `@command`-decorated function, you can either accept `ctx` via [`@pass_context`](https://click.palletsprojects.com/en/stable/commands/#nested-handling-and-contexts) or call [`click.get_current_context()`](https://click.palletsprojects.com/en/stable/api/#click.get_current_context) from any helper that runs while the CLI is being invoked. Both give you the same context, and both expose the same `.meta` dict.

```{caution}
Outside an active CLI invocation (e.g. at import time, in unit tests that build options directly without invoking a CLI, or in a REPL) there is no context, and these keys are not available. Helpers that need to work in both modes should fall through to a sane default. The [theming layer](theme.md) does this with `get_current_theme()`, which returns the module-level `default_theme` when no context is in flight.
```

## `click_extra.context` API

```{eval-rst}
.. automodule:: click_extra.context
   :members:
   :undoc-members:
```
