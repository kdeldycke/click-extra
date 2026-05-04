# {octicon}`paintbrush` Themes

Click Extra exposes a small theming system that controls every color used in help screens: options, choices, metavars, arguments, CLI names, defaults, environment variables, log levels, and more. Two themes ship by default (`dark` and `light`), and downstream projects can register their own.

## The `--theme` option

Every command and group built with `@click_extra.command` / `@click_extra.group` automatically gets a `--theme` flag, alongside the other [default options](commands.md#default-options).

```{click:source}
from click_extra import command, echo

@command
def weather():
    """Show the local weather forecast."""
    echo("Sunny, 22°C.")
```

```{click:run}
result = invoke(weather, args=["--theme", "dark", "--help"])
assert result.exit_code == 0
assert "--theme" in result.stdout
```

```{click:run}
result = invoke(weather, args=["--theme", "light", "--help"])
assert result.exit_code == 0
```

The flag is eager, so it is processed before any other option and before help is rendered. The picked theme is stored on the active Click context's `meta` dict under `click_extra.context.THEME`, so it applies for the duration of the current invocation only: subcommands inherit it (Click shares `meta` across the parent/child hierarchy), but a sibling invocation of the same CLI in the same process starts from the default again. See the [available keys](context.md#available-keys) table for the full inventory you can read from your own callbacks.

## Configuration file

Like every other [default option](config.md), `--theme` reads its value from `pyproject.toml`:

```toml
[tool.weather]
theme = "light"
```

Now invocations of the `weather` CLI pick up the light theme without passing `--theme` on the command line.

## Built-in themes

| Name    | Intended terminal background |
| ------- | ---------------------------- |
| `dark`  | Dark background              |
| `light` | Light background             |

Both themes live as plain `HelpExtraTheme` instances in `click_extra.themes`:

- `click_extra.themes.DARK`: tuned for dark backgrounds and used as the process-wide default.
- `click_extra.themes.LIGHT`: swaps the dark palette's bright variants and cyan accents for plain colors that stay legible on a white background.
- `click_extra.themes.BUILTIN_THEMES`: a `dict[str, HelpExtraTheme]` mapping the names above to their instance. Seeded into `theme_registry` at module load.

The two module-level instances exported by `click_extra.theme` are:

- `default_theme`: the process-wide fallback. `ThemeOption` does *not* reassign it: per-invocation choices live on `ctx.meta` instead. `click_extra.wrap.patch_click()` does reassign it to override the fallback for the entire patched session.
- `nocolor_theme`: an all-`identity` theme used when ANSI rendering is suppressed.

Use `click_extra.theme.get_current_theme()` to read the theme that applies to the current invocation: it consults the active Click context first and falls back to `default_theme`.

### Adding a new built-in theme

A built-in theme is a single constant in `click_extra/themes.py`: declare a `HelpExtraTheme(...)` instance and add it to `BUILTIN_THEMES`. No subclass, no factory method on `HelpExtraTheme`.

```python
# click_extra/themes.py

SOLARIZED = HelpExtraTheme(
    invoked_command=Style(fg=Color.cyan),
    heading=Style(fg=Color.yellow, bold=True, underline=True),
    option=Style(fg=Color.cyan),
    # ... fill in the rest of the slots
)

BUILTIN_THEMES = {
    "dark": DARK,
    "light": LIGHT,
    "solarized": SOLARIZED,
}
```

## Registering a custom theme

The list of valid `--theme` choices is pulled from `click_extra.theme.theme_registry` at option-instantiation time. To add your own theme from a downstream package, call `register_theme()` *before* declaring your commands. The simplest case is registering a static `HelpExtraTheme` instance:

```python
from click_extra import (
    DARK,
    Color,
    Style,
    command,
    echo,
    register_theme,
)

NEON = DARK.with_(
    heading=Style(fg=Color.bright_magenta, bold=True, underline=True),
    option=Style(fg=Color.bright_cyan),
    choice=Style(fg=Color.bright_yellow),
)
register_theme("neon", NEON)


@command
def cocktail():
    """Mix a cocktail."""
    echo("Cheers!")
```

After this runs, `cocktail --theme neon` becomes a valid invocation, and `cocktail --help` lists `[dark|light|neon]` as the choices.

For themes whose styling depends on runtime state (terminal capabilities, environment variables, user settings), `register_theme()` also accepts a zero-argument callable that returns a `HelpExtraTheme`. The callable is resolved when `--theme` is parsed, not at registration time:

```python
def detect_theme():
    """Pick a palette based on terminal background detection."""
    return DARK if terminal_is_dark() else LIGHT

register_theme("auto", detect_theme)
```

```{caution}
`register_theme()` mutates a module-level dict. Call it once at import time, before your `@command` / `@group` decorators run. `ThemeOption` builds its `click.Choice` from `theme_registry` at instantiation, so themes registered after the option is constructed will not appear in the choices.
```

## Anatomy of a theme

`HelpExtraTheme` is a frozen dataclass that extends [`cloup.HelpTheme`](https://cloup.readthedocs.io/en/stable/pages/formatting.html#help-formatting-and-themes) with extra styling slots for log levels and Click Extra's own categories.

Use `with_()` to derive a new theme that only overrides a few styles:

```python
from click_extra import DARK, Style, Color

minimal = DARK.with_(
    option=Style(fg=Color.white),
    choice=Style(fg=Color.white, dim=True),
)
```

`with_()` returns the same instance when no styles change and validates that all keyword arguments match a known field, so typos like `optoin=...` raise immediately.

### Cross-reference highlighting

The `cross_ref_highlight` flag (default `True`) controls whether option names, choices, arguments, metavars, and CLI names are highlighted wherever they appear in free-form prose. Disable it for a calmer help screen:

```python
calm = DARK.with_(cross_ref_highlight=False)
```

See [Cross-reference highlighting](colorize.md#cross-reference-highlighting) for the details on what stays styled when the flag is off.

## Interaction with `--color` / `--no-color`

`--theme` controls *which* colors are used. `--color` / `--no-color` controls *whether* colors are emitted at all. The two are independent:

- `--theme light` with `--no-color` emits no ANSI codes.
- `--theme dark` with `--color` (the default) emits the dark theme's ANSI codes.
- `NO_COLOR=1` in the environment overrides any `--theme` choice by silencing all ANSI output.

The `--color` callback inspects the standard set of color environment variables (`NO_COLOR`, `CLICOLOR`, `FORCE_COLOR`, `LLM`, etc.) before the theme is applied: see [`color_envvars`](colorize.md) for the full list.

## `click_extra.theme` API

```{eval-rst}
.. autoclasstree:: click_extra.theme
   :strict:

.. automodule:: click_extra.theme
   :members:
   :undoc-members:
   :show-inheritance:
```

## `click_extra.themes` API

```{eval-rst}
.. automodule:: click_extra.themes
   :members:
   :undoc-members:
```
