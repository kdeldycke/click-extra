# {octicon}`paintbrush` Colored help

Click Extra extends [Cloup's help formatter and theme](https://cloup.readthedocs.io/en/stable/pages/formatting.html#help-formatting-and-themes) to automatically colorize every element of the help screen: options, choices, metavars, arguments, CLI and subcommand names, aliases, environment variables, defaults, ranges, and required labels.

## Cross-reference highlighting

Notice how `--format`, `--output`, and `--dry-run` light up not only in the synopsis column but also inside other options' descriptions and the command's docstring:

```{click:source}
from click_extra import Choice, command, option, echo

@command
@option("--format", type=Choice(["json", "csv"]), help="Output format.")
@option("--output", help="Write to file instead of stdout.")
@option(
    "--dry-run",
    is_flag=True,
    help="Preview what would be written to --output without --format validation.",
)
def export(format, output, dry_run):
    """Export data.

    Combine --format and --output to write directly to a file.
    Use --dry-run to preview without side effects.
    """
    echo("Exporting...")
```

```{click:run}
result = invoke(export, args=["--help"])
assert result.exit_code == 0
# --format, --output and --dry-run are highlighted in the synopsis column.
assert "\x1b[36m--format\x1b[0m" in result.output
assert "\x1b[36m--output\x1b[0m" in result.output
assert "\x1b[36m--dry-run\x1b[0m" in result.output
# They are ALSO highlighted when referenced in other options' help text
# and in the command docstring. Each occurrence of "--output" and "--format"
# in the rendered help carries the option style (cyan).
assert result.output.count("\x1b[36m--format\x1b[0m") >= 3
assert result.output.count("\x1b[36m--output\x1b[0m") >= 3
```

Every option name in the help screen carries the same style, regardless of where it appears: synopsis column, another option's description, the command's docstring. This turns plain-text references into visual links, making it easier to scan for related options. The same applies to choices (highlighted in the metavar list and anywhere the description mentions them), arguments, and subcommand names.

### Disabling cross-reference highlighting

If the free-text matching produces false positives (option names or choices that coincide with common words), disable it via the theme:

```python
from click_extra import HelpExtraTheme, group

safe_theme = HelpExtraTheme.dark().with_(cross_ref_highlight=False)


@group(context_settings={"formatter_settings": {"theme": safe_theme}})
def cli(): ...
```

With `cross_ref_highlight=False`, only structural elements are styled: bracket fields (`[default: ...]`, `[env var: ...]`, ranges, `[required]`), deprecated messages, subcommand names in definition lists, and choice metavars (`[json|csv|xml]`). Option names, choices in free-form text, arguments, metavars, and CLI names in descriptions and docstrings are left unstyled.

### Custom keyword injection

Use `extra_keywords` to inject additional strings for highlighting. Strings are grouped by category in a `HelpKeywords` dataclass, so each gets the appropriate style:

```{click:source}
from click_extra import HelpKeywords, command, echo, option

@command(
    extra_keywords=HelpKeywords(long_options={"--profile"}),
)
@option("--output", help="Write to file. See --profile for timing.")
def build(output):
    """Build the project."""
    echo("Building...")
```

```{click:run}
result = invoke(build, args=["--help"])
assert result.exit_code == 0
# --profile is not a real parameter, but it is highlighted as an option
# because it was injected via extra_keywords.
assert "\x1b[36m--profile\x1b[0m" in result.output
```

### Suppressing keyword highlighting

The mirror of `extra_keywords`: use `excluded_keywords` to prevent specific strings from being highlighted, even when they are auto-collected from the Click context:

```{click:source}
from click_extra import Choice, HelpKeywords, command, echo, option

@command(
    excluded_keywords=HelpKeywords(choices={"text"}),
)
@option("--format", type=Choice(["json", "text"]), help="Use json or text.")
def export(format):
    """Export data."""
    echo("Exporting...")
```

```{click:run}
from boltons.strutils import strip_ansi
result = invoke(export, args=["--help"])
assert result.exit_code == 0
# "json" is highlighted as a choice everywhere.
assert "\x1b[35mjson\x1b[0m" in result.output
# "text" is still styled inside its own choice metavar [json|text] (structural).
assert "[\x1b[35mjson\x1b[0m|\x1b[35mtext\x1b[0m]" in result.output
# But "text" is NOT highlighted in the description prose.
# Check "or text" context, which only appears in the description.
assert "or \x1b[35mtext\x1b[0m" not in result.output
assert "or text." in strip_ansi(result.output)
```

Excluded keywords are only suppressed in free-text descriptions and docstrings. They remain styled inside their own choice metavar, which is a structural element (like bracket fields).

Exclusions propagate from parent groups to subcommands. If a group excludes a choice, that exclusion applies to all nested subcommand help screens too. Parent and child exclusions are merged, so you can exclude additional keywords at any level:

```{click:source}
from click_extra import Choice, HelpKeywords, echo, group, option

@group(excluded_keywords=HelpKeywords(choices={"version"}))
@option("--sort-by", type=Choice(["name", "version"]))
def cli(sort_by):
    """Sort items."""

@cli.command()
def show():
    """Show the version of each item."""
    echo("Showing...")
```

```{click:run}
result = invoke(cli, args=["show", "--help"])
assert result.exit_code == 0
# "version" is a parent choice but excluded: not styled in the description.
assert "\x1b[35mversion\x1b[0m" not in result.output
from boltons.strutils import strip_ansi
assert "version" in strip_ansi(result.output)
```

Both `extra_keywords` and `excluded_keywords` accept a `HelpKeywords` instance. The available category fields are: `cli_names`, `subcommands`, `command_aliases`, `arguments`, `long_options`, `short_options`, `choices`, `choice_metavars`, `metavars`, `envvars`, and `defaults`. The `choice_metavars` field is auto-populated from `click.Choice` parameters and rarely needs manual specification.

For advanced customization, override `collect_keywords()` on your command class. Call `super()` and mutate the returned `HelpKeywords` to add or remove entries:

```python
from click_extra import ExtraCommand, HelpKeywords


class MyCommand(ExtraCommand):
    def collect_keywords(self, ctx):
        kw = super().collect_keywords(ctx)
        kw.choices.discard("internal")
        kw.long_options.add("--undocumented-flag")
        return kw
```

## Bracket fields

Trailing metadata brackets (`[default: ...]`, `[env var: ...]`, `[required]`, and range expressions) each get their own style. All four fields can appear together:

```{click:source}
from click_extra import command, option, IntRange

@command
@option(
    "--threshold",
    type=IntRange(1, 100),
    default=50,
    required=True,
    show_default=True,
    envvar="THRESHOLD",
    show_envvar=True,
    help="Sensitivity level.",
)
def analyze(threshold):
    """Run analysis."""
```

```{click:run}
result = invoke(analyze, args=["--help"])
assert result.exit_code == 0
# Each bracket field uses a distinct style.
# Default value (green, dim, italic):
assert "\x1b[32m\x1b[2m\x1b[3m50\x1b[0m" in result.output
# Range (cyan, dim):
assert "\x1b[36m\x1b[2m" in result.output
# Required (red, dim):
assert "\x1b[31m\x1b[2mrequired\x1b[0m" in result.output
```

```{note}
When choices are `Enum` members, Click Extra colorizes their `name` attribute (not their `value`), matching [Click's own behavior](types.md#limits-of-click-choice). Use [`EnumChoice`](types.md#enumchoice) if you need user-friendly choice strings based on values or custom representations.
```

## Why not use `rich-click`?

[`rich-click`](https://github.com/ewels/rich-click) is a good project that aims to integrate [Rich](https://github.com/Textualize/rich) with Click. Like Click Extra, it provides a ready-to-use help formatter for Click.

But contrary to Click Extra, the [help screen is rendered within a table](https://github.com/ewels/rich-click), which takes the whole width of the terminal. This is not ideal if you try to print the output of a command somewhere else.

The typical use-case is users reporting issues on GitHub, and pasting the output of a command in the issue description. If the output is too wide, it will be akwardly wrapped, or [adds a horizontal scrollbar](https://github.com/callowayproject/bump-my-version/pull/23#issuecomment-1602007874) to the page.

Without a table imposing a maximal width, the help screens from Click Extra will be rendered with the minimal width of the text, and will be more readable.

```{hint}
This is just a matter of preference, as nothing prevents you to use both `rich-click` and Click Extra in the same project, and get the best from both.
```

<a name="color-no-color-flag"></a>

## `--color`/`--no-color` flag

Click Extra adds a `--color`/`--no-color` flag (aliased as `--ansi`/`--no-ansi`) that controls whether ANSI codes are emitted. It is eager, so it takes effect before other eager options like `--version`.

The option respects the [`NO_COLOR`](https://no-color.org), `CLICOLOR`, and `CLICOLOR_FORCE` environment variables. When any of these signals "no color", the environment takes precedence over the default value (but an explicit `--color` or `--no-color` on the command line always wins).

All Click Extra commands and groups include this option by default. Use `color_option` as a standalone decorator when building CLIs with plain `click.command`:

```{click:source}
import click
from click_extra import echo, color_option

@click.command
@color_option
def greet():
    """Say hello with optional color."""
    ctx = click.get_current_context()
    if ctx.color:
        echo("\x1b[32mHello in green!\x1b[0m")
    else:
        echo("Hello without color.")
```

```{click:run}
result = invoke(greet, args=["--color"])
assert result.exit_code == 0
assert "\x1b[32mHello in green!\x1b[0m" in result.output
```

```{click:run}
result = invoke(greet, args=["--no-color"])
assert result.exit_code == 0
assert "Hello without color." in result.output
```

## `--help`, `-h` aliases

Click Extra defaults `help_option_names` to `("--help", "-h")`, adding the short `-h` alias that Click does not provide out of the box. This applies to all commands and groups created with Click Extra decorators:

```{click:source}
from click_extra import command, echo

@command
def hello():
    """Greet the user."""
    echo("Hello!")
```

```{click:run}
from boltons.strutils import strip_ansi
result = invoke(hello, args=["-h"])
assert result.exit_code == 0
plain = strip_ansi(result.output)
assert "Greet the user." in plain
assert "-h, --help" in plain
```

## Colors and styles

The `click-extra` demo subcommands render matrices of all colors, styles, and palettes, useful for testing terminal capabilities. Based on [`cloup.styling.Style`](https://cloup.readthedocs.io/en/stable/autoapi/cloup/styling/index.html#cloup.styling.Style):

### Style matrix

```{click:source}
:hide-source:
from click_extra.cli import demo
```

```{click:run}
result = invoke(demo, args=["--color", "styles"])
assert result.exit_code == 0

# Each style header renders with its own SGR attribute.
assert "\x1b[1mbold\x1b[0m" in result.output
assert "\x1b[2mdim\x1b[0m" in result.output
assert "\x1b[4munderline\x1b[0m" in result.output
assert "\x1b[53moverline\x1b[0m" in result.output
assert "\x1b[3mitalic\x1b[0m" in result.output
assert "\x1b[5mblink\x1b[0m" in result.output
assert "\x1b[7mreverse\x1b[0m" in result.output
assert "\x1b[9mstrikethrough\x1b[0m" in result.output

# Cells combine foreground color with style attribute.
# Bold red.
assert "\x1b[31m\x1b[1mred\x1b[0m" in result.output
# Italic bright_blue.
assert "\x1b[94m\x1b[3mbright_blue\x1b[0m" in result.output
# Strikethrough green.
assert "\x1b[32m\x1b[9mgreen\x1b[0m" in result.output
```

### Color matrix

```{click:run}
result = invoke(demo, args=["--color", "colors"])
assert result.exit_code == 0

# Each background header renders with its own background color.
assert "\x1b[41mred\x1b[0m" in result.output
assert "\x1b[44mblue\x1b[0m" in result.output

# Cells combine foreground and background.
# Red text on blue background.
assert "\x1b[31m\x1b[44mred\x1b[0m" in result.output
# Bright green text on yellow background.
assert "\x1b[92m\x1b[43mbright_green\x1b[0m" in result.output
```

### 256-color indexed palette

```{click:run}
result = invoke(demo, args=["--color", "palette"])
assert result.exit_code == 0

# System colors (indices 0-15).
assert "\x1b[38;5;0;48;5;0m" in result.output
assert "\x1b[38;5;15;48;5;15m" in result.output

# Color cube entry.
assert "\x1b[38;5;196;48;5;196m" in result.output

# Grayscale ramp.
assert "\x1b[38;5;232;48;5;232m" in result.output
assert "\x1b[38;5;255;48;5;255m" in result.output
```

### 8-color foreground/background combinations

```{click:run}
result = invoke(demo, args=["--color", "8color"])
assert result.exit_code == 0

# Plain foreground (no background).
assert "\x1b[31m gYw \x1b[m" in result.output

# Bold foreground.
assert "\x1b[1;31m gYw \x1b[m" in result.output

# Foreground + background combination.
assert "\x1b[31;42m gYw \x1b[m" in result.output
```

### 24-bit RGB vs. 256-color quantization

```{click:run}
result = invoke(demo, args=["--color", "gradient"])
assert result.exit_code == 0

# 24-bit row uses SGR 38;2;r;g;b.
assert "\x1b[38;2;" in result.output

# 8-bit row uses SGR 38;5;n.
assert "\x1b[38;5;" in result.output

# All four gradients are present.
assert "Rainbow:" in result.output
assert "Grayscale:" in result.output
assert "Red:" in result.output
assert "Cyan:" in result.output
```

```{caution}
The rendering of colors and styles in this HTML documentation is not complete, and does not reflect the real output in a terminal. Some SGR attributes (like reverse video) have no direct CSS equivalent and are not rendered. Some terminal emulators also lack support for overline (SGR 53), blink (SGR 5), and strikethrough (SGR 9).
```

```{tip}
Run `uvx click-extra styles` in your terminal to see the real rendering with your color scheme.
```

## `click_extra.colorize` API

```{eval-rst}
.. autoclasstree:: click_extra.colorize
   :strict:

.. automodule:: click_extra.colorize
   :members:
   :undoc-members:
   :show-inheritance:
```
