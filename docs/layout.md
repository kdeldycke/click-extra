# {octicon}`rows` Layout

A terminal is a grid of cells. Anything a CLI draws to a stated width has to agree with the terminal on how many cells a string takes, and that number is not the string's length.

## Measuring a line

`cell_width` answers in cells. An ideograph takes two of them, and a combining mark none:

```{click:source}
from click_extra import command, echo
from click_extra.layout import cell_width


@command
def measure():
    """Compare a string's length with the cells it occupies."""
    for text in ("apricot", "杏", "e\u0301"):
        echo(f"{len(text):2} characters, {cell_width(text):2} cells")
```

```{click:run}
result = invoke(measure)
assert result.exit_code == 0
assert result.stdout.splitlines() == [
    " 7 characters,  7 cells",
    " 1 characters,  2 cells",
    " 2 characters,  1 cells",
]
```

Reach for it over `len` wherever a column has to line up: a table gutter, a padded label, a rule.

An escape sequence is the one thing it cannot account for. A string carrying one holds a control character, `wcswidth` refuses to measure any such string, and `cell_width` falls back to the character count:

```{click:run}
from click_extra.layout import cell_width

assert cell_width("\x1b[31mapricot\x1b[0m") == 16
```

Sixteen, where the terminal draws seven. Strip the styling before measuring text that already carries it, the way `center_in_rule` does below.

## Ruling a line

`center_in_rule` composes a line of a stated width with a label centered in it. It is what `click-extra themes` heads each palette with, and what a capture writes in place of the lines `--head` cut away:

```{click:source}
from click_extra import command, echo, option
from click_extra.layout import center_in_rule


@command
@option("--columns", type=int, default=60, help="Width of the rule.")
def harvest(columns):
    """Separate two baskets with a named rule."""
    echo(center_in_rule("apricots", columns))
    echo("  Alberge, Moorpark, Tilton")
    echo(center_in_rule("plums", columns))
    echo("  Damson, Greengage, Mirabelle")
```

```{click:run}
result = invoke(harvest, args=["--columns", "44"])
assert result.exit_code == 0
from click_extra import unstyle

# The rule is painted to recede, so read it back unstyled.
plain = unstyle(result.stdout)
assert plain.startswith("────────────────[ apricots ]────────────────\n")
assert "─────────────────[ plums ]──────────────────" in plain
```

Every part of the line is a parameter: the character the rule repeats, the two brackets around the label, and the color the rule and brackets are painted.

```{click:run}
from click_extra.layout import center_in_rule

assert center_in_rule("plums", 30) == (
    "\x1b[90m──────────[ \x1b[0mplums\x1b[90m ]───────────\x1b[0m"
)
assert center_in_rule("plums", 30, rule="·", opening=" ", closing=" ", color=None) == (
    "··········· plums ············"
)
```

## A rule with nothing to name

Pass no label and the brackets go too, leaving one unbroken line. A divider naming nothing should not look like a frame around nothing:

```{click:run}
from click_extra.layout import center_in_rule

assert center_in_rule(None, 30, color=None) == "─" * 30
assert center_in_rule("", 30, color=None) == "─" * 30
```

The same happens when the width cannot hold the brackets, and a width too narrow for the label leaves the label alone rather than drawing a rule that cannot close.

## A label you styled yourself

The label is measured with its escape sequences stripped, so a caller paints it whichever way it likes and hands the whole thing over. `color` reaches only the rule and the brackets, which is the half a caller cannot pre-style without knowing where they fall:

```{click:source}
from click_extra import command, echo
from click_extra.layout import center_in_rule
from click_extra.styling import Style


@command
def basket():
    """Rule a line around a label the caller colored itself."""
    echo(center_in_rule(Style(fg="green", bold=True)("ripe"), 40))
```

```{click:run}
result = invoke(basket)
assert result.exit_code == 0
assert "\x1b[32m\x1b[1mripe\x1b[0m" in result.output
```

That label is 4 cells of text carrying 17 characters, so a rule built on `len` would come out 13 columns short of the width asked for.

```{tip}
A rule drawn with a Box Drawing dash (`┄`, `┈`, `╌`) carries two or three strokes inside a single cell. In a [capture](screenshots.md) each stroke is a pixel or two wide and a cell advances a fractional number of device pixels, so neighbouring dashes merge on some cells and separate on others, and the rule shimmers. An unbroken `─` has nothing to merge, and `·` puts one mark per cell with room around it. Both stay even at any scale.
```

## `click_extra.layout` API

```{eval-rst}
.. automodule:: click_extra.layout
   :members:
   :undoc-members:
   :show-inheritance:
```
