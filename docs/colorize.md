# {octicon}`paintbrush` Colored help

Click Extra extends [Cloup's help formatter and theme](https://cloup.readthedocs.io/en/stable/pages/formatting.html#help-formatting-and-themes) to automatically colorize every element of the help screen: options, choices, metavars, arguments, CLI and subcommand names, aliases, environment variables, defaults, ranges, and required labels.

## Cross-reference highlighting

Option names are highlighted wherever they appear in the help screen, not only in the synopsis column. If an option name shows up in another option's description or in the command's docstring, it gets the same styling. This turns plain-text references into visual links, making it easier to scan for related options.

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

The same applies to choices (highlighted in the metavar list and in any description that references them), arguments, and subcommand names.

### Disabling cross-reference highlighting

If the free-text matching produces false positives (option names or choices that coincide with common words), disable it via the theme:

```python
from click_extra import HelpExtraTheme, group

safe_theme = HelpExtraTheme.dark().with_(cross_ref_highlight=False)

@group(context_settings={"formatter_settings": {"theme": safe_theme}})
def cli():
    ...
```

With `cross_ref_highlight=False`, only structural elements are styled: bracket fields (`[default: ...]`, `[env var: ...]`, ranges, `[required]`), deprecated messages, and subcommand names in definition lists. Option names, choices, arguments, metavars, and CLI names in descriptions and docstrings are left unstyled.

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

## `color_option`

```{todo}
Write examples and tutorial.
```

## `help_option`

```{todo}
Write examples and tutorial.
```

## Colors and styles

Here is a little CLI to demonstrate the rendering of colors and styles, based on [`cloup.styling.Style`](https://cloup.readthedocs.io/en/stable/autoapi/cloup/styling/index.html#cloup.styling.Style):

```{click:source}
from click import command
from click_extra import Color, style, Choice, option, print_table

all_styles = [
    "bold",
    "dim",
    "underline",
    "overline",
    "italic",
    "blink",
    "reverse",
    "strikethrough",
]

all_colors = sorted(Color._dict.values())

@command
@option("--matrix", type=Choice(["colors", "styles"]))
def render_matrix(matrix):
    table = []

    if matrix == "colors":
        table_headers = ["Foreground ↴ \\ Background →"] + all_colors
        for fg_color in all_colors:
            line = [
                style(fg_color, fg=fg_color)
            ]
            for bg_color in all_colors:
                line.append(
                    style(fg_color, fg=fg_color, bg=bg_color)
                )
            table.append(line)

    elif matrix == "styles":
        table_headers = ["Color ↴ \\ Style →"] + all_styles
        for color_name in all_colors:
            line = [
                style(color_name, fg=color_name)
            ]
            for prop in all_styles:
                line.append(
                    style(color_name, fg=color_name, **{prop: True})
                )
            table.append(line)

    print_table(table, headers=table_headers)
```

```{click:run}
result = invoke(render_matrix, ["--matrix=colors"])
assert "\x1b[95mbright_magenta\x1b[0m" in result.stdout
assert "\x1b[95m\x1b[101mbright_magenta\x1b[0m" in result.stdout
```

```{click:run}
result = invoke(render_matrix, ["--matrix=styles"])
assert "\x1b[97mbright_white\x1b[0m" in result.stdout
assert "\x1b[97m\x1b[1mbright_white\x1b[0m" in result.stdout
assert "\x1b[97m\x1b[2mbright_white\x1b[0m" in result.stdout
assert "\x1b[97m\x1b[4mbright_white\x1b[0m" in result.stdout
```

```{caution}
The current rendering of colors and styles in this HTML documentation is not complete, and does not reflect the real output in a terminal.

That is because [`pygments-ansi-color`](https://github.com/chriskuehl/pygments-ansi-color), the component we rely on to render ANSI code in Sphinx via Pygments, [only supports a subset of the ANSI codes](https://github.com/chriskuehl/pygments-ansi-color/issues/31) we use.
```

```{tip}
The code above is presented as a CLI, so you can copy and run it yourself in your environment, and see the output in your terminal. That way you can evaluate the real effect of these styles and colors for your end users.
```

## `click_extra.colorize` API

```{eval-rst}
.. autoclasstree:: click_extra.colorize
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.colorize
   :members:
   :undoc-members:
   :show-inheritance:
```
