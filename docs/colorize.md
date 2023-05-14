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

```{eval-rst}
.. click:example::
   from click import command
   from click_extra import Color, Style, Choice, option
   from click_extra.tabulate import render_table

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
            props = {"fg": Color[fg_color]}
            table.append(
               [
                  Style(**props)(fg_color)
               ] + [
                  Style(**props, **{"bg": bg_color})(fg_color)
                  for bg_color in all_colors
               ]
            )

      elif matrix == "styles":
         table_headers = ["Color ↴ \ Style →"] + all_styles
         for color_name in all_colors:
            props = {"fg": Color[color_name]}
            table.append(
               [
                  Style(**props)(color_name)
               ] + [
                  Style(**props, **{p: True})(color_name)
                  for p in all_styles
               ]
            )

      render_table(table, headers=table_headers)

.. click:run::
   invoke(render_matrix, ["--matrix=colors"])

.. click:run::
   invoke(render_matrix, ["--matrix=styles"])
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
