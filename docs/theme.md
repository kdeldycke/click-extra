# {octicon}`sun` Themes

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
result = invoke(weather, args=["--theme", "light", "--help"])
assert result.exit_code == 0
assert "--theme" in result.stdout
```

The flag is eager, so it is processed before any other option and before help is rendered. The picked theme is stored on the active Click context's `meta` dict under `click_extra.context.THEME` and inherits down to subcommands, so a parent group's `--theme` applies to every child. See the [available keys](context.md#available-keys) table for the full inventory you can read from your own callbacks.

## Configuration file

Like every other [default option](config.md), `--theme` reads its value from `pyproject.toml`:

```toml
[tool.weather]
theme = "light"
```

Now invocations of the `weather` CLI pick up the light theme without passing `--theme` on the command line.

## Built-in themes

| Name                                | Color model          | Notes                                                                |
| :---------------------------------- | :------------------- | :------------------------------------------------------------------- |
| [`dark`](#dark)                     | 16 named ANSI colors | Process-wide default. Follows the user's terminal palette.           |
| [`light`](#light)                   | 16 named ANSI colors | Tuned for white backgrounds: no bright variants, blue replaces cyan. |
| [`solarized_dark`](#solarized-dark) | 24-bit RGB           | Warm-toned dark theme with selective accent contrast.                |
| [`dracula`](#dracula)               | 24-bit RGB           | High-contrast dark theme with vivid neon accents.                    |
| [`nord`](#nord)                     | 24-bit RGB           | Cool-toned dark theme built around frost-blue and aurora accents.    |
| [`monokai`](#monokai)               | 24-bit RGB           | Classic dark theme with high-saturation magenta and lime accents.    |
| [`manpage`](#manpage)               | None (monochrome)    | Bold literals, italic replaceable, no color. Shadows a man page.     |

Each row is keyed by the `--theme` choice value; access the instance via `BUILTIN_THEMES["<name>"]` (e.g. `BUILTIN_THEMES["dark"]`). Click any name to jump to that theme's [palette listing](#palettes) below.

Click each tab below for a live render of the theme applied to the same `weather` CLI's `--help` output. Colors are produced at Sphinx build time, not screenshots.

``````{tab-set}

`````{tab-item} dark
```{click:run}
result = invoke(weather, args=["--theme", "dark", "--help"])
assert result.exit_code == 0
```
`````

`````{tab-item} light
```{click:run}
result = invoke(weather, args=["--theme", "light", "--help"])
assert result.exit_code == 0
```
`````

`````{tab-item} solarized_dark
```{click:run}
result = invoke(weather, args=["--theme", "solarized_dark", "--help"])
assert result.exit_code == 0
```
`````

`````{tab-item} dracula
```{click:run}
result = invoke(weather, args=["--theme", "dracula", "--help"])
assert result.exit_code == 0
```
`````

`````{tab-item} nord
```{click:run}
result = invoke(weather, args=["--theme", "nord", "--help"])
assert result.exit_code == 0
```
`````

`````{tab-item} monokai
```{click:run}
result = invoke(weather, args=["--theme", "monokai", "--help"])
assert result.exit_code == 0
```
`````

`````{tab-item} manpage
```{click:run}
result = invoke(weather, args=["--theme", "manpage", "--help"])
assert result.exit_code == 0
```
`````

``````

Three flavors ship in `click_extra/themes.toml`:

- **ANSI themes** (`dark`, `light`) use the 16 named ANSI colors via `cloup.styling.Color`, so the rendered colors track whatever palette the user's terminal is configured with. Pick these when you want to blend in with the user's terminal theme.
- **Branded themes** (`solarized_dark`, `dracula`, `nord`, `monokai`) emit 24-bit RGB triplets from each theme's canonical palette. Pick these when the theme name implies specific colors (`solarized_dark` should look like Solarized, not "whatever the terminal calls cyan"). Terminals without 24-bit support fall back to the nearest 256-color cell automatically. Each theme's slot mapping is hand-curated: there's no automated translation from generic colour-scheme formats, because none of them expose the same semantic roles we care about (option, metavar, choice, deprecated, envvar, ...).
- **Monochrome theme** (`manpage`) uses no color at all: it renders literal tokens bold and replaceable tokens italic, the way `man-pages(7)` typesets a command. Pick it for low-color terminals, screenshots, or output meant to read like a man page. The bold/italic split is the one in [literal and replaceable slots](#literal-and-replaceable-slots).

`click_extra.theme.BUILTIN_THEMES` is a `dict[str, HelpExtraTheme]` mapping the names above to their instances; it is built by parsing `click_extra/themes.toml` at import time and is seeded into `theme_registry` immediately afterwards. Read the TOML file directly for the exact palette mapping, or call `theme.to_dict()` at runtime to get a TOML/JSON-friendly dict.

### Palettes

Every styled slot of each built-in theme, with the swatch and attribute decorations rendered live from the shipped `themes.toml` at Sphinx build time. The block below iterates `BUILTIN_THEMES` and calls `palette_html()` for each: downstream projects with their own custom themes can drop the same loop into their own docs to get matching swatch listings.

```{python:render}
from click_extra.theme import BUILTIN_THEMES, palette_html

for name, theme in BUILTIN_THEMES.items():
    print(f"#### `{name}`")
    print()
    print(palette_html(theme))
    print()
```

### Module exports

`click_extra.theme` exposes two themes and a pair of accessor helpers:

- `nocolor_theme`: an all-`identity` theme used when ANSI rendering is suppressed.
- `get_default_theme()` / `set_default_theme(theme)`: read or override the process-wide fallback. The default is the built-in `dark` palette. `ThemeOption` does *not* call `set_default_theme`: per-invocation choices live on `ctx.meta` instead. `click_extra.wrap.patch_click()` calls `set_default_theme()` to override the fallback for the entire patched session.

Use `click_extra.theme.get_current_theme()` to read the theme that applies to the current invocation: it consults the active Click context first and falls back to `get_default_theme()`.

### Adding a new built-in theme

A built-in theme is a single TOML table in `click_extra/themes.toml`: declare a `[<name>]` table with one inline-table per styled slot. The file is parsed at import time via `HelpExtraTheme.from_dict`, so adding a theme requires no Python — only the data:

```toml
# click_extra/themes.toml

[zenburn]
# Zenburn by Jani Nurminen.
# Palette: https://kippura.org/zenburnpage/
invoked_command = { fg = "#dcdccc", bold = true }
heading = { fg = "#8cd0d3", bold = true, underline = true }
option = { fg = "#8cd0d3" }
# ... fill in the rest of the slots
```

Tables are kept in alphabetical order; `tests/test_themes.py` enforces this. The slot mapping is the work: generic colour-scheme catalogs (base16, pygments, iTerm palettes) don't expose the semantic roles Click Extra needs (option, metavar, choice, deprecated, envvar, ...), so each theme is hand-curated. Use the existing `solarized_dark`, `dracula`, `nord`, and `monokai` tables as templates.

## Registering a custom theme

The list of valid `--theme` choices is pulled from `click_extra.theme.theme_registry` (plus per-invocation overrides from `--config`) at parse time. To add your own theme from a downstream package, call `register_theme()` *before* declaring your commands:

```python
from click_extra import (
    BUILTIN_THEMES,
    Color,
    Style,
    command,
    echo,
    register_theme,
)

NEON = BUILTIN_THEMES["dark"].with_(
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

After this runs, `cocktail --theme neon` becomes a valid invocation, and `cocktail --help` lists `neon` alongside the built-in choices.

```{tip}
For themes that depend on runtime state (terminal-background detection, environment variables, user settings), compute the `HelpExtraTheme` once at startup and pass it to `register_theme`. The registry holds plain instances only — if you need lazy or per-invocation resolution, load the theme from `[tool.<cli>.themes.<name>]` (see [Themes from your `--config` file](#themes-from-your-config-file) below) so it lands on `ctx.meta` rather than the process-wide dict.
```

## Anatomy of a theme

`HelpExtraTheme` is a frozen dataclass that extends [`cloup.HelpTheme`](https://cloup.readthedocs.io/en/stable/pages/formatting.html#help-formatting-and-themes) with extra styling slots for log levels and Click Extra's own categories.

Use `with_()` to derive a new theme that only overrides a few styles:

```python
from click_extra import BUILTIN_THEMES, Style, Color

minimal = BUILTIN_THEMES["dark"].with_(
    option=Style(fg=Color.white),
    choice=Style(fg=Color.white, dim=True),
)
```

`with_()` returns the same instance when no styles change and validates that all keyword arguments match a known field, so typos like `optoin=...` raise immediately.

### Literal and replaceable slots

The styling slots carry a second, coarser classification borrowed from [man-pages(7)](https://man7.org/linux/man-pages/man7/man-pages.7.html): *literal* tokens the user types verbatim versus *replaceable* tokens the user substitutes with a real value. Man pages render the former in **bold** and the latter in *italic*, "even in the SYNOPSIS section". `click_extra.theme` records that mapping as two frozensets of slot names:

- `LITERAL_STYLES`: `invoked_command`, `subcommand`, `alias`, `alias_secondary`, `option`, `choice`.
- `REPLACEABLE_STYLES`: `metavar`, `argument`.

Every remaining slot (log levels, the `[default: ...]` and `[env var: ...]` bracket fields, headings, …) sits outside the dichotomy. Every built-in theme applies this split: literal slots render bold and replaceable slots italic, even inside the color palettes, and the [`manpage`](#manpage) theme renders it with nothing else. A future [man-page generator](man-page.md) can reuse the same two sets to map each styled token to roff's `\fB` / `\fI`.

### Cross-reference highlighting

The `cross_ref_highlight` flag (default `True`) controls whether option names, choices, arguments, metavars, and CLI names are highlighted wherever they appear in free-form prose. Disable it for a calmer help screen:

```python
calm = BUILTIN_THEMES["dark"].with_(cross_ref_highlight=False)
```

See [Cross-reference highlighting](colorize.md#cross-reference-highlighting) for the details on what stays styled when the flag is off.

### Manual loading from a mapping

`HelpExtraTheme.to_dict()` and `HelpExtraTheme.from_dict()` round-trip a theme through plain mappings, so a theme can live in a TOML, JSON, or YAML file alongside the rest of an application's configuration:

```toml
[my_theme]
option = { fg = "cyan" }
heading = { fg = "bright_blue", bold = true, underline = true }
choice = { fg = "magenta" }
```

```python
import tomllib
from pathlib import Path

from click_extra import HelpExtraTheme, register_theme

raw = tomllib.loads(Path("config.toml").read_text())
register_theme("my_theme", HelpExtraTheme.from_dict(raw["my_theme"]))
```

`to_dict()` only emits slots that diverge from the default (`identity` / `None`), and `from_dict()` raises `TypeError` on unknown keys, so configuration typos surface at load time rather than silently producing a half-styled theme.

For the much more common case where the theme should live in the same `--config` file the CLI already reads, see the [next section](#themes-from-your-config-file) — click-extra wires the loader for you.

## Themes from your config file

`ConfigOption` recognizes a `themes` sub-table inside the app's section. Every `[<cli>.themes.<name>]` entry is parsed via `HelpExtraTheme.from_dict` and made available to `--theme` for the duration of the invocation, with two distinct behaviors depending on whether `<name>` matches a built-in:

- **Override an existing palette.** Re-declare a built-in name (`dark`, `dracula`, `light`, …) and the slots you set are overlaid on top of the built-in palette via `HelpExtraTheme.cascade`. Unset slots inherit from the built-in, so a one-line override like `option = { fg = "bright_cyan" }` is enough.
- **Define a new palette.** Use any other name and `--theme <name>` becomes a valid choice for that invocation. Unset slots default to *no styling* (`identity`), so you typically declare a slot for every category you care about.

In both cases the theme registry mutation is **per-invocation**: it lives on `ctx.meta` under `click_extra.context.THEME_OVERRIDES` and never touches the module-level `theme_registry`. Sphinx builds, test runners, and any other host process running multiple CLI invocations back-to-back never leak themes between them.

### Override an existing built-in

```{click:source}
from click_extra import command, echo

@command
def weather():
    """Show the local weather forecast."""
    echo("Sunny, 22°C.")
```

Drop the override under `[<cli>.themes.dark]` in your `weather.toml`:

```toml
[weather.themes.dark]
option = { fg = "bright_cyan" }
choice = { fg = "yellow", bold = true }
```

Then ask for `--help` with the override applied (the rest of the dark palette stays put):

```{click:run}
import tempfile, textwrap
from pathlib import Path

config = Path(tempfile.mkdtemp()) / "weather.toml"
config.write_text(textwrap.dedent("""
    [weather.themes.dark]
    option = { fg = "bright_cyan" }
    choice = { fg = "yellow", bold = true }
"""))
result = invoke(weather, args=["--config", str(config), "--help"])
assert result.exit_code == 0
assert "--theme" in result.stdout
```

### Define a brand-new theme

```toml
[weather.themes.midnight]
option = { fg = "blue", bold = true }
heading = { fg = "magenta" }
choice = { fg = "yellow" }
default = { fg = "green", italic = true }
```

The new name immediately shows up in `--help`'s `--theme` metavar and is selectable on the command line:

```{click:run}
import tempfile, textwrap
from pathlib import Path

config = Path(tempfile.mkdtemp()) / "weather.toml"
config.write_text(textwrap.dedent("""
    [weather]
    theme = "midnight"

    [weather.themes.midnight]
    option = { fg = "blue", bold = true }
    heading = { fg = "magenta" }
    choice = { fg = "yellow" }
    default = { fg = "green", italic = true }
"""))
result = invoke(weather, args=["--config", str(config), "--help"])
assert result.exit_code == 0
assert "midnight" in result.stdout
```

The same `[weather] theme = "midnight"` selector you'd use for a built-in works here: pre-pick the new theme as the default for invocations of this CLI.

### Validation

Malformed entries surface as `ValidationError` with a path rooted at the configuration file root, both during `--validate-config` and at normal load time:

```toml
[weather.themes.midnight]
optoin = { fg = "blue" } # typo
```

```{click:run}
import tempfile, textwrap
from pathlib import Path

config = Path(tempfile.mkdtemp()) / "weather.toml"
config.write_text(textwrap.dedent("""
    [weather.themes.midnight]
    optoin = { fg = "blue" }
"""))
result = invoke(weather, args=["--validate-config", str(config)])
assert result.exit_code != 0
assert "midnight" in result.stderr
assert "optoin" in result.stderr
```

The built-in `ConfigValidator` for the `themes` sub-tree is auto-registered on every `ConfigOption`, so app authors don't have to opt in. Apps that ship their own `ConfigValidator` continue to work alongside it.

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
