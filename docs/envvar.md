# {octicon}`pin` Environment variables

Click's environment-variable handling spreads across several internal methods on `Parameter`, `Option`, and `Context`. This module centralizes that logic into a small set of pure helpers that downstream code can call to introspect what Click *would* read for a given parameter, plus a couple of subprocess-friendly conveniences.

The helpers underpin click-extra's [`show_envvar` defaults](commands.md#default-options) on every option's help screen, the [`--params` table](parameters.md#params-option), and the auto-envvar reconciliation in [`TelemetryOption`](telemetry.md), [`ColorOption`](colorize.md), and others, but they're equally useful for any downstream code that needs to surface the env-var contract of its CLI.

```{seealso}
[Environment variables are a legacy mess: Let's dive deep into them](https://allvpv.org/haotic-journey-through-envvars/) is the best survey of the wider problem space these helpers paper over.
```

## `merge_envvar_ids(*envvar_ids)`

Merge and deduplicate environment-variable names from any combination of strings and arbitrarily-nested iterables. `None` values are filtered out. Order is preserved (first occurrence wins), and on Windows every name is upper-cased to match the [platform's case-insensitive `os.environ` semantics](https://docs.python.org/3/library/os.html#os.environ): the same normalization the standard library applies internally.

```{python:run}
from click_extra.envvar import merge_envvar_ids

print(merge_envvar_ids("MYAPP_DEBUG"))

# Strings, lists, and None values all flatten correctly.
print(merge_envvar_ids("MYAPP_DEBUG", ["MYAPP_VERBOSE", None], "MYAPP_DEBUG"))

# Deduplication preserves the first occurrence's position.
print(merge_envvar_ids("A", "B", "A", "C", "B"))
```

The result is a `tuple[str, ...]` ready to feed Click's `envvar=` parameter on options and arguments. Click Extra uses it internally to combine user-supplied envvar names with conventions like `NO_COLOR`, `DO_NOT_TRACK`, and `FORCE_COLOR`:

```python
# click_extra/telemetry.py
envvar = merge_envvar_ids("DO_NOT_TRACK", envvar)
```

## `clean_envvar_id(name)`

Normalize an arbitrary string into a canonical environment-variable name: split on non-alphanumeric runs, drop empties, join with underscores, uppercase the result.

```{python:run}
from click_extra.envvar import clean_envvar_id

print(clean_envvar_id("my-cli"))
print(clean_envvar_id("My CLI debug-mode"))
print(clean_envvar_id("v2.0+beta"))
```

```{attention}
This helper does not exactly replicate Click's own auto-envvar derivation: [Click's case-handling of environment variables is inconsistent across versions](https://github.com/pallets/click/issues/2483). Use `clean_envvar_id` when *you* control the naming, and `param_auto_envvar_id` (below) when you need to know exactly what Click itself would produce for a given parameter.
```

## `param_auto_envvar_id(param, ctx)`

Compute the auto-generated environment variable Click would read for an option or argument, given a parameter instance and either an active `click.Context` or a plain settings dict (like `context_settings`). Returns `None` when the parameter has `allow_from_autoenv=False`, or when no `auto_envvar_prefix` is configured. The output exactly mirrors what `click.core.Parameter.resolve_envvar_value()` and `click.core.Option.resolve_envvar_value()` produce internally:

```{python:run}
import click

from click_extra.envvar import param_auto_envvar_id


@click.command()
@click.option("--debug")
@click.pass_context
def show(ctx, debug):
    pass


with click.Context(show, auto_envvar_prefix="MYAPP") as ctx:
    debug_opt = next(p for p in show.params if p.name == "debug")
    print(param_auto_envvar_id(debug_opt, ctx))

# Without an auto_envvar_prefix, the auto-envvar is None.
with click.Context(show) as ctx:
    print(param_auto_envvar_id(debug_opt, ctx))
```

## `param_envvar_ids(param, ctx)`: the main entry point

Returns the deduplicated, ordered tuple of environment variables Click would consider for an option or argument: the user-declared `envvar=` value (single string or iterable) followed by the auto-generated one. Click reads them in this order and stops at the first one set, which means **user-declared envvars take precedence over the auto-generated one**: `param_envvar_ids` preserves that ordering.

```mermaid
:align: center

flowchart LR
    decl["param.envvar<br/>user-declared:<br/>string or nested iterable"] --> merge
    auto["param_auto_envvar_id()<br/>PREFIX_NAME,<br/>if auto-envvar enabled"] --> merge
    merge["merge_envvar_ids()<br/>flatten, drop empty,<br/>dedupe, upper-case on Windows"] --> tup["ordered tuple<br/>user-declared first,<br/>auto-generated last"]
    tup --> reader["Click reads in order,<br/>stops at first set<br/>so user-declared wins"]
```

```{python:run}
import click

from click_extra.envvar import param_envvar_ids


@click.command()
@click.option("--debug", envvar=["DEBUG", "MYAPP_DEBUG"])
@click.option("--verbose")
def show(debug, verbose):
    pass


with click.Context(show, auto_envvar_prefix="MYAPP") as ctx:
    debug_opt = next(p for p in show.params if p.name == "debug")
    verbose_opt = next(p for p in show.params if p.name == "verbose")
    print(f"--debug:   {param_envvar_ids(debug_opt, ctx)}")
    print(f"--verbose: {param_envvar_ids(verbose_opt, ctx)}")
```

This is what powers click-extra's `--params` table: each row's *Env. vars.* column comes from `param_envvar_ids(param, ctx)`, joined with `, ` and styled with the active theme's `envvar` slot.

## `env_copy(extend=None)`

Returns a shallow copy of `os.environ` with optional extra keys layered on top, or `None` when `extend` is empty. Mirrors Python's own subprocess-handling pattern: `subprocess.Popen(env=None)` inherits the current environment, so returning `None` for the no-extension case is a useful contract:

```{python:run}
import os
from click_extra.envvar import env_copy

# No extension → returns None (subprocess inherits unchanged).
print(env_copy())
print(env_copy({}))

# Extension → returns a copy with the extras layered on top.
copy = env_copy({"MYAPP_DEBUG": "1"})
print(copy is os.environ)  # False — it's a copy.
print(copy["MYAPP_DEBUG"])

# Original environment stays unchanged.
print("MYAPP_DEBUG" in os.environ)
```

Pair it with `subprocess.run(..., env=env_copy({"MYAPP_TOKEN": secret}))` when you need to add a few variables for a child process without leaking them into the parent's `os.environ`.

## `click_extra.envvar` API

```{eval-rst}
.. automodule:: click_extra.envvar
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
