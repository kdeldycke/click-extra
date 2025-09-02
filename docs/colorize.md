# Colored help

Extend
[Cloup's own help formatter and theme](https://cloup.readthedocs.io/en/stable/pages/formatting.html#help-formatting-and-themes)
to add colorization of:

- Options

- Choices

- Metavars

- Cli name

- Sub-commands

- Command aliases

- Long and short options

- Choices

- Metavars

- Environment variables

- Defaults

```{todo}
Write examples and tutorial.
```

## Why not use `rich-click`?

[`rich-click`](https://github.com/ewels/rich-click) is a good project that aims to integrate [Rich](https://github.com/Textualize/rich) with Click. Like Click Extra, it provides a ready-to-use help formatter for Click.

But contrary to Click Extra, the [help screen is rendered within a table](https://github.com/ewels/rich-click#styling), which takes the whole width of the terminal. This is not ideal if you try to print the output of a command somewhere else.

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

```{click:example}
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
        table_headers = ["Foreground ↴ \ Background →"] + all_colors
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
        table_headers = ["Color ↴ \ Style →"] + all_styles
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
