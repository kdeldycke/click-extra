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
result = invoke(weather, args=["--help"])
assert result.exit_code == 0
assert "--theme" in result.stdout
```

```{click:run}
result = invoke(weather, args=["--theme", "light", "--help"])
assert result.exit_code == 0
```

The flag is eager, so it is processed before any other option and before help is rendered. Setting `--theme` mutates the module-level `click_extra.theme.default_theme` for the rest of the process: any help screen rendered afterward (including subcommand help) picks up the new colors.

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

Both themes are defined in `click_extra.theme.HelpExtraTheme.dark()` / `.light()`. The `light` factory is currently a placeholder that returns the same styles as `dark`: see the docstring for the open task.

The two module-level instances live in `click_extra.theme`:

- `default_theme`: the active theme. Reassigned at parse time by `ThemeOption`. Read it through the module reference (`from click_extra import theme; theme.default_theme`) when you need late binding.
- `nocolor_theme`: an all-`identity` theme used when ANSI rendering is suppressed.

## Registering a custom theme

The list of valid `--theme` choices is pulled from `click_extra.theme.theme_registry` at option-instantiation time. To add your own theme, call `register_theme()` *before* declaring your commands:

```python
from click_extra import (
    HelpExtraTheme,
    Style,
    Color,
    command,
    echo,
    register_theme,
)


def neon():
    """A high-contrast theme inspired by neon signage."""
    return HelpExtraTheme.dark().with_(
        heading=Style(fg=Color.bright_magenta, bold=True, underline=True),
        option=Style(fg=Color.bright_cyan),
        choice=Style(fg=Color.bright_yellow),
    )


register_theme("neon", neon)


@command
def cocktail():
    """Mix a cocktail."""
    echo("Cheers!")
```

After this runs, ``cocktail --theme neon`` becomes a valid invocation, and ``cocktail --help`` lists ``[dark|light|neon]`` as the choices.

The registry stores **factories**, not pre-built instances, so themes that depend on runtime state (terminal capabilities, environment variables, user settings) compute their styles lazily.

```{caution}
`register_theme()` mutates a module-level dict. Call it once at import time, before your `@command` / `@group` decorators run. `ThemeOption` builds its `click.Choice` from `theme_registry` at instantiation, so themes registered after the option is constructed will not appear in the choices.
```

## Anatomy of a theme

`HelpExtraTheme` is a frozen dataclass that extends [`cloup.HelpTheme`](https://cloup.readthedocs.io/en/stable/pages/formatting.html#help-formatting-and-themes) with extra styling slots for log levels and Click Extra's own categories.

Use `with_()` to derive a new theme that only overrides a few styles:

```python
from click_extra import HelpExtraTheme, Style, Color

minimal = HelpExtraTheme.dark().with_(
    option=Style(fg=Color.white),
    choice=Style(fg=Color.white, dim=True),
)
```

`with_()` returns the same instance when no styles change and validates that all keyword arguments match a known field, so typos like `optoin=...` raise immediately.

### Cross-reference highlighting

The `cross_ref_highlight` flag (default `True`) controls whether option names, choices, arguments, metavars, and CLI names are highlighted wherever they appear in free-form prose. Disable it for a calmer help screen:

```python
calm = HelpExtraTheme.dark().with_(cross_ref_highlight=False)
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
