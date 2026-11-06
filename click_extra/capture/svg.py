# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

"""Draw captured terminal text as an SVG picture of a terminal window.

{mod}`click_extra.capture.screenshot` decides what a capture shows, then hands
the text, its palette and the resolved {class}`~click_extra.capture.presets.Chrome`
to {func}`render_svg`, which lays the text out on a character grid and paints the
window around it, one layer at a time: backdrop, shadow, frame, title bar,
emphasis bands, text, cursor, credit line and animation.

The window's geometry lives here too, since every pixel size below is the
picture's: the title bar, the shadow's blur and offset, the credit line's size
and place, and the cell metrics the grid is measured in.
{mod}`click_extra.capture.html` draws the same window and borrows them, so the
two documents look like the same terminal. The paints and sizes a
{class}`~click_extra.capture.presets.Chrome` defaults to, like
{data}`~click_extra.capture.presets.NO_PAINT` and
{data}`~click_extra.capture.presets.OPAQUE`, live beside it in
{mod}`click_extra.capture.presets`.
"""

from __future__ import annotations

import re
import warnings
import zlib
from collections import Counter
from functools import cache, lru_cache
from itertools import accumulate, groupby
from math import ceil, cos, hypot, pi, sin
from typing import NamedTuple, cast

from .._utils import AUTO, DOCS_URL, GENERATOR_TAG
from ..ansi import ANSI_INDEX, hex_to_rgb, resolve_rgb, rgb_to_hex, strip_ansi
from ..layout import PADDING, cell_width, grid, is_bidirectional
from ..styling import _ATTR_CSS
from .presets import (
    BARE_CHROME,
    CAPTURE_FONT_STACK,
    DEFAULT_PRESET,
    MACOS_BUTTONS,
    NO_PAINT,
    OPAQUE,
    PACKAGE_NAME,
    Cursor,
    CursorShape,
    TerminalPalette,
    WindowButtons,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from typing import Any, Literal, TypeAlias, TypeVar

    from ..styling import Style
    from .presets import Chrome

    THold: TypeAlias = float | Literal["auto"]
    """Pause an animation takes on its last frame, see {data}`AUTO_HOLD`."""

    _Edge = TypeVar("_Edge", int, float)
    """Where a span starts or ends, see {func}`_extend_spans`."""


TITLEBAR_HEIGHT = 40
"""Height, in pixels, of the strip a title and its buttons sit in.

The padding a renderer leaves above the text, which is what a window's chrome
occupies. Restated here because a capture wearing neither decoration nor caption
drops the strip, and one drawn as a real terminal paints it.
"""


SHADOW_BLUR = 6
"""Standard deviation, in pixels, of the drop shadow's blur."""


SHADOW_OFFSET = 3
"""Downward offset, in pixels, of the drop shadow."""


WINDOW_PADDING = 8
"""Pixels every window keeps between its frame and its text, on three sides.

The fourth is the top, where {data}`TITLEBAR_HEIGHT` answers instead. This is the
window's own breathing room, before the `padding` a capture may ask for on top.
"""


WINDOW_INSET = 1
"""Pixels between the image's edge and the window's frame.

A stroke straddles the shape it outlines, so a frame drawn flush with the
viewBox loses its outer half to the crop. Inset by more than that half and the
whole line shows.
"""


CSS_SIDE_ANGLES = {
    "to top": 0.0,
    "to top right": 45.0,
    "to right top": 45.0,
    "to right": 90.0,
    "to bottom right": 135.0,
    "to right bottom": 135.0,
    "to bottom": 180.0,
    "to bottom left": 225.0,
    "to left bottom": 225.0,
    "to left": 270.0,
    "to top left": 315.0,
    "to left top": 315.0,
}
"""Angle each CSS side keyword names, in degrees clockwise from `to top`.

`to bottom` is what a gradient opening with no direction at all means, which is
why it doubles as the default. See {func}`gradient_svg`.
"""


TITLE_SIZE = 18
"""Height, in pixels, of the caption drawn in a window's title bar."""


WATERMARK_SIZE = 13
"""Height, in pixels, of the credit line's glyphs.

Below the terminal's own text, since a mark competing with the screen it credits
is a mark in the way.
"""


WATERMARK_INSET = 12
"""Pixels between the credit line and the image's bottom-right corner.

It is drawn in the margin, the one band of a capture that carries nothing else.
A capture shot with `margin=0` has no such band, and the line lands on the
window's own corner instead of beside it.
"""


WATERMARK_URL = f"{DOCS_URL}/screenshots.html"
"""Page the credit line points at, for a reader holding only the image.

A capture travels away from whatever explained it, so the mark carries the way
back. Only {data}`~click_extra.capture.presets.PACKAGE_NAME` is linked, and only
where the line still names it: a project crediting itself instead has no
click-extra left to point at, and gets no link rather than one pointing
somewhere it did not ask for.

```{note}
The link answers where the file is interactive: opened on its own, inlined into
a page, or embedded through `<object>`. An `<img>` draws an SVG as a picture and
no click reaches inside one, which is how this documentation embeds its own
captures.
```
"""


CELL_HEIGHT = 20.0
"""Height of one glyph cell, in pixels, which is also the text's font size."""


FONT_ASPECT_RATIO = 0.61
"""Width-to-height ratio of the font a capture is laid out for.

Fira Code's, the first family {data}`~click_extra.capture.presets.CAPTURE_FONT_STACK`
asks for. Every monospaced fallback behind it is close enough that the grid holds, and
`textLength` pins each run to its columns for the ones that are not.
"""


CELL_WIDTH = CELL_HEIGHT * FONT_ASPECT_RATIO
"""Width of one glyph cell, in pixels. One character of a monospaced terminal."""


LINE_HEIGHT = CELL_HEIGHT * 1.22
"""Vertical distance between two consecutive text baselines, in pixels."""


CELL_BLEED = 0.25
"""Pixels a cell's background is grown by, past the line it belongs to.

Two rectangles meeting on an exact boundary leave a hairline of page showing
through when a renderer rounds their edges to different pixels. Overlapping them
slightly is what closes that seam, and is invisible because the color painted
twice is the same color.
"""


CELL_TOP_INSET = 1.5
"""Pixels between a line's top edge and the cell backgrounds drawn on it.

A glyph does not fill its line box: the leading sits above the tallest letter.
Starting the paint just under that keeps a highlighted run reading as one block
of color rather than as a band taller than the text it marks.
"""


CURSOR_THICKNESS = 2.0
"""Pixels a cursor is drawn thick, when it is a line rather than a cell.

Both {attr}`~click_extra.capture.presets.CursorShape.BAR` and
{attr}`~click_extra.capture.presets.CursorShape.UNDERLINE` are the same line
turned a quarter, so one number states both. Thin enough to read as a cursor
beside a glyph, thick enough to survive a renderer rounding it to whole pixels.
"""


DEFAULT_CURSOR_SHAPE = CursorShape.BLOCK
"""Shape a cursor takes when nothing names one.

What every terminal here but Windows draws, and the shape a reader recognizes
as a terminal cursor rather than as a text caret. A capture given a preset takes
that terminal's own shape instead, see
{attr}`~click_extra.capture.presets.TerminalPreset.cursor`.
"""


_TILE_RUN = 8
"""Cells of tiling characters {func}`_tile_runs` groups before restating an offset.

Small enough that a font whose tiles are a fraction of a pixel off the grid
cannot drift a visible amount before the next offset resets it, and large enough
that a table's rule stays a handful of elements rather than one per cell.
"""


BLOCK_ELEMENTS = {
    "▀": ((0, 0, 8, 4),),
    "▁": ((0, 7, 8, 8),),
    "▂": ((0, 6, 8, 8),),
    "▃": ((0, 5, 8, 8),),
    "▄": ((0, 4, 8, 8),),
    "▅": ((0, 3, 8, 8),),
    "▆": ((0, 2, 8, 8),),
    "▇": ((0, 1, 8, 8),),
    "█": ((0, 0, 8, 8),),
    "▉": ((0, 0, 7, 8),),
    "▊": ((0, 0, 6, 8),),
    "▋": ((0, 0, 5, 8),),
    "▌": ((0, 0, 4, 8),),
    "▍": ((0, 0, 3, 8),),
    "▎": ((0, 0, 2, 8),),
    "▏": ((0, 0, 1, 8),),
    "▐": ((4, 0, 8, 8),),
    "░": ((0, 0, 8, 8),),
    "▒": ((0, 0, 8, 8),),
    "▓": ((0, 0, 8, 8),),
    "▔": ((0, 0, 8, 1),),
    "▕": ((7, 0, 8, 8),),
    "▖": ((0, 4, 4, 8),),
    "▗": ((4, 4, 8, 8),),
    "▘": ((0, 0, 4, 4),),
    "▙": ((0, 0, 4, 8), (4, 4, 8, 8)),
    "▚": ((0, 0, 4, 4), (4, 4, 8, 8)),
    "▛": ((0, 0, 8, 4), (0, 4, 4, 8)),
    "▜": ((0, 0, 8, 4), (4, 4, 8, 8)),
    "▝": ((4, 0, 8, 4),),
    "▞": ((4, 0, 8, 4), (0, 4, 4, 8)),
    "▟": ((4, 0, 8, 4), (0, 4, 8, 8)),
}
"""Rectangles each Block Elements character fills on its cell.

Each rectangle is `(left, top, right, bottom)`, counted in eighths of the cell
from its top-left corner: `▁`, the lower one eighth, is the finest step these
characters take. {func}`block_svg` draws the rectangles in place of the glyphs,
and {func}`~click_extra.capture.html.block_css` does in an HTML capture.

A font draws these characters to its own height, not to the row's. SF Mono
`15.0d5e1` draws `█` exactly one em tall and Menlo `22.0d2e1` 1.02 em, while a
capture's rows are {data}`LINE_HEIGHT` apart, 1.22 em. Set as glyphs, two
stacked rows of block art leave a band of 4.0 to 4.4 pixels between them, and
stretching the glyphs would take a factor and an offset per font, which a
capture cannot know. A rectangle fills its share of the cell in every renderer,
whatever font the reader has.

Terminals draw these characters themselves rather than take them from the font,
for the same result: WezTerm with
[`custom_block_glyphs`](https://wezterm.org/config/lua/config/custom_block_glyphs.html)
and Alacritty with
[`builtin_box_drawing`](https://alacritty.org/config-alacritty.html), both on by
default, and VS Code with
[`terminal.integrated.customGlyphs`](https://code.visualstudio.com/docs/terminal/appearance)
under GPU acceleration.

The characters stay in the text, unpainted, see
{data}`HIDDEN_GLYPH_ATTRIBUTES`. A decoration on one, like an underline, is
hidden with it.
"""


SHADE_DENSITY = {"░": 0.25, "▒": 0.5, "▓": 0.75}
"""How much of a shade character's cell is ink.

{data}`BLOCK_ELEMENTS` gives each shade the full cell. Its ink is mixed with the
color behind it up front rather than thinned with opacity, for the reason
{func}`blend` gives, so a shade draws as one flat color.
"""


BRAILLE_DOTS = ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3))
"""Where each Braille dot sits on its cell, as `(column, row)` on a 2 by 4 grid.

Listed in bit order: bit `n` of a pattern's offset from U+2800 raises dot
`n + 1`. The dots number down the left column, then down the right, and the
bottom row, dots 7 and 8, comes last: 8-dot Braille extends the 6-dot cell with
that row. {func}`braille_svg` draws them.

The rows split the line into four and the columns split the cell into two, so
the dots keep one pitch across cells, and stacked rows of Braille plot one even
grid.

Menlo, where a stock macOS falls through
{data}`~click_extra.capture.presets.CAPTURE_FONT_STACK`, has no Braille. Its
stand-in, Apple Symbols `22.0d3e1`, draws every pattern 0.684 em wide, 1.5
pixels wider than its column at a capture's size. Drawn as dots, a pattern
fits its cell whatever font the reader has. Terminals draw Braille themselves
too: WezTerm with
[`custom_block_glyphs`](https://wezterm.org/config/lua/config/custom_block_glyphs.html)
and VS Code with
[`terminal.integrated.customGlyphs`](https://code.visualstudio.com/docs/terminal/appearance).
"""


BRAILLE_DOT_RADIUS = 0.25
"""Radius of a Braille dot, as a share of the pitch between two dots.

A quarter, so a dot is half as wide as the pitch: the proportion Apple Braille
`22.0d3e1` draws, a dot 248 units across on a pitch of 488.
"""


BOX_ARMS = {
    "─": (0, 1, 0, 1),
    "━": (0, 2, 0, 2),
    "│": (1, 0, 1, 0),
    "┃": (2, 0, 2, 0),
    "┌": (0, 1, 1, 0),
    "┍": (0, 2, 1, 0),
    "┎": (0, 1, 2, 0),
    "┏": (0, 2, 2, 0),
    "┐": (0, 0, 1, 1),
    "┑": (0, 0, 1, 2),
    "┒": (0, 0, 2, 1),
    "┓": (0, 0, 2, 2),
    "└": (1, 1, 0, 0),
    "┕": (1, 2, 0, 0),
    "┖": (2, 1, 0, 0),
    "┗": (2, 2, 0, 0),
    "┘": (1, 0, 0, 1),
    "┙": (1, 0, 0, 2),
    "┚": (2, 0, 0, 1),
    "┛": (2, 0, 0, 2),
    "├": (1, 1, 1, 0),
    "┝": (1, 2, 1, 0),
    "┞": (2, 1, 1, 0),
    "┟": (1, 1, 2, 0),
    "┠": (2, 1, 2, 0),
    "┡": (2, 2, 1, 0),
    "┢": (1, 2, 2, 0),
    "┣": (2, 2, 2, 0),
    "┤": (1, 0, 1, 1),
    "┥": (1, 0, 1, 2),
    "┦": (2, 0, 1, 1),
    "┧": (1, 0, 2, 1),
    "┨": (2, 0, 2, 1),
    "┩": (2, 0, 1, 2),
    "┪": (1, 0, 2, 2),
    "┫": (2, 0, 2, 2),
    "┬": (0, 1, 1, 1),
    "┭": (0, 1, 1, 2),
    "┮": (0, 2, 1, 1),
    "┯": (0, 2, 1, 2),
    "┰": (0, 1, 2, 1),
    "┱": (0, 1, 2, 2),
    "┲": (0, 2, 2, 1),
    "┳": (0, 2, 2, 2),
    "┴": (1, 1, 0, 1),
    "┵": (1, 1, 0, 2),
    "┶": (1, 2, 0, 1),
    "┷": (1, 2, 0, 2),
    "┸": (2, 1, 0, 1),
    "┹": (2, 1, 0, 2),
    "┺": (2, 2, 0, 1),
    "┻": (2, 2, 0, 2),
    "┼": (1, 1, 1, 1),
    "┽": (1, 1, 1, 2),
    "┾": (1, 2, 1, 1),
    "┿": (1, 2, 1, 2),
    "╀": (2, 1, 1, 1),
    "╁": (1, 1, 2, 1),
    "╂": (2, 1, 2, 1),
    "╃": (2, 1, 1, 2),
    "╄": (2, 2, 1, 1),
    "╅": (1, 1, 2, 2),
    "╆": (1, 2, 2, 1),
    "╇": (2, 2, 1, 2),
    "╈": (1, 2, 2, 2),
    "╉": (2, 1, 2, 2),
    "╊": (2, 2, 2, 1),
    "╋": (2, 2, 2, 2),
    "═": (0, 3, 0, 3),
    "║": (3, 0, 3, 0),
    "╒": (0, 3, 1, 0),
    "╓": (0, 1, 3, 0),
    "╔": (0, 3, 3, 0),
    "╕": (0, 0, 1, 3),
    "╖": (0, 0, 3, 1),
    "╗": (0, 0, 3, 3),
    "╘": (1, 3, 0, 0),
    "╙": (3, 1, 0, 0),
    "╚": (3, 3, 0, 0),
    "╛": (1, 0, 0, 3),
    "╜": (3, 0, 0, 1),
    "╝": (3, 0, 0, 3),
    "╞": (1, 3, 1, 0),
    "╟": (3, 1, 3, 0),
    "╠": (3, 3, 3, 0),
    "╡": (1, 0, 1, 3),
    "╢": (3, 0, 3, 1),
    "╣": (3, 0, 3, 3),
    "╤": (0, 3, 1, 3),
    "╥": (0, 1, 3, 1),
    "╦": (0, 3, 3, 3),
    "╧": (1, 3, 0, 3),
    "╨": (3, 1, 0, 1),
    "╩": (3, 3, 0, 3),
    "╪": (1, 3, 1, 3),
    "╫": (3, 1, 3, 1),
    "╬": (3, 3, 3, 3),
    "╴": (0, 0, 0, 1),
    "╵": (1, 0, 0, 0),
    "╶": (0, 1, 0, 0),
    "╷": (0, 0, 1, 0),
    "╸": (0, 0, 0, 2),
    "╹": (2, 0, 0, 0),
    "╺": (0, 2, 0, 0),
    "╻": (0, 0, 2, 0),
    "╼": (0, 2, 0, 1),
    "╽": (1, 0, 2, 0),
    "╾": (0, 1, 0, 2),
    "╿": (2, 0, 1, 0),
}
"""Arms of each Box Drawing line, as their `(up, right, down, left)` weights.

`0` draws no arm, `1` a light one, `2` a heavy one and `3` a double one: the
weights the character's Unicode name lists. {func}`box_svg` draws each arm from
its cell's edge toward the middle, and works out where two arms' strokes meet.

As glyphs, two of these meet wherever the font and the renderer place them, a
fraction of a pixel off the grid, and a table's rule shows a seam or a kink at
every join: [`rich#2536`](https://github.com/Textualize/rich/issues/2536), which
its maintainer answers takes drawn shapes. Terminals draw these characters
themselves: WezTerm with
[`custom_block_glyphs`](https://wezterm.org/config/lua/config/custom_block_glyphs.html),
Alacritty with
[`builtin_box_drawing`](https://alacritty.org/config-alacritty.html) and VS Code
with
[`terminal.integrated.customGlyphs`](https://code.visualstudio.com/docs/terminal/appearance).
"""


BOX_STROKES = {1: ((-1, 1),), 2: ((-2, 2),), 3: ((-3, -1), (1, 3))}
"""Where the strokes of a light, heavy and double arm sit across it.

Counted from the cell's middle line, in sixteenths of its width or thirty-seconds
of its height: one unit on both axes, a row being twice as tall as a column is
wide. A light stroke is two units thick, 0.076 em, close to Menlo `22.0d2e1`'s
0.078 em. A heavy one is twice that, and a double one is two light strokes a
light stroke apart, as Menlo draws them.
"""


BOX_DASHES = {
    "┄": (False, 1, 3),
    "┅": (False, 2, 3),
    "┆": (True, 1, 3),
    "┇": (True, 2, 3),
    "┈": (False, 1, 4),
    "┉": (False, 2, 4),
    "┊": (True, 1, 4),
    "┋": (True, 2, 4),
    "╌": (False, 1, 2),
    "╍": (False, 2, 2),
    "╎": (True, 1, 2),
    "╏": (True, 2, 2),
}
"""Dashed Box Drawing lines, as whether each runs down, its weight and its dashes.

A dash covers two thirds of its share of the cell and leaves the rest as a gap
split between its two ends, so dashes keep one pitch across cells.
"""


BOX_CURVES = {
    "╭": "M16,16 A8,8 0 0,0 8,24 L8,32",
    "╮": "M0,16 A8,8 0 0,1 8,24 L8,32",
    "╯": "M8,0 L8,8 A8,8 0 0,1 0,16",
    "╰": "M8,0 L8,8 A8,8 0 0,0 16,16",
    "╱": "M16,0 L0,32",
    "╲": "M0,0 L16,32",
    "╳": "M16,0 L0,32 M0,0 L16,32",
}
"""Arcs and diagonals of Box Drawing, as SVG path data on a 16 by 32 cell.

Drawn as a light stroke, see {data}`BOX_STROKES`. An arc turns on a radius of
half the cell's width, so it meets the straight arms of its neighbors.
"""


DIM_RATIO = 0.4
"""How far a `dim` run's ink is mixed toward the background, see {func}`blend`."""


EMPHASIS_RATIO = 0.16
"""How far an emphasized line's band is mixed from the background toward the ink.

Mixed rather than stated outright, so one number answers for every chrome: a
band a shade lighter than a dark terminal is a shade darker than a light one,
and both read as the same emphasis. Far enough to find the line at a glance,
near enough to leave its text the thing being read.
"""


HIDDEN_FRAME_ATTRIBUTES = ' visibility="hidden" opacity="0"'
"""How an animated capture hides the frames its still is not made of.

Presentation attributes rather than a stylesheet rule, so a renderer reading no
CSS still shows one picture instead of every frame at once. A CSS animation
outranks a presentation attribute, so {func}`frame_animation_css` restores both
together and the two mechanisms never disagree.

```{caution}
Neither property is redundant. `visibility` alone satisfies a browser, `librsvg`
and macOS Quick Look's *thumbnailer*, but two other readers ignore it and draw
every frame on top of the last: a git client's SVG diff view, and macOS Finder's
*preview pane*, a different code path from the thumbnailer. Both honor
`opacity`, so each property covers a reader the other misses, and dropping
either takes a class of reader with it.
```
"""


HIDDEN_GLYPH_ATTRIBUTES = ' opacity="0"'
"""How a run drawn as shapes keeps its characters without painting them.

Kept as text, the characters still reach a reader copying the capture's text,
and whatever rebuilds the terminal's lines from it.

`opacity`, because every reader honors it, see {data}`HIDDEN_FRAME_ATTRIBUTES`.
`fill` would lose to the run's class, which sets it in the stylesheet, and
AppKit's `NSImage` ignores `fill-opacity` on text: macOS Finder's preview pane
and a git client's SVG diff view then draw each glyph over its own shapes.
"""


ANIMATION_METADATA_RE = re.compile(r"<!-- @recording (?P<fields>[^>]*?) -->")
"""The line an animated capture states its own identity on.

Written beside the `@generated` line, and read back by whatever has to decide
whether a freshly drawn animation is the one already on disk. Holding the answer
in the file is what spares that decision from parsing an SVG back into frames.
"""


FRAME_TIMING_FUNCTION = "step-end"
"""How an animated capture moves between two frames: it does not.

A terminal repaints a whole cell at once, so a capture of one has nothing to
interpolate. `step-end` holds each keyframe's value until the next one is
reached, which turns a percentage ladder into discrete frames and lets every
frame state its own window. That is what carries a recording, whose frames each
last as long as the terminal held them, on the same machinery as a spinner,
whose frames are all the same length.
"""


REDUCED_MOTION_QUERY = "@media (prefers-reduced-motion: no-preference)"
"""Guard every animation rule an animated capture emits sits behind.

{mod}`click_extra.accessibility` counts an endlessly repeating spinner among the
things `--accessible` exists to lower, and an image looping forever on a
documentation page is the same imposition on a reader who asked their system for
less motion. Outside the guard the first frame stays visible and the rest stay
hidden, which is the picture a renderer that reads no CSS animation already
gets, so honoring the preference costs a media query and no second code path.
"""


AUTO_HOLD: Literal["auto"] = AUTO
"""Hold asking for the pause the final screen's own density decides.

Resolved by {func}`auto_hold`: the busier the closing screen, the longer the
loop pauses on it before starting over. A fixed number serves an animation
whose ending the author has seen; this serves one whose ending changes with
every retake, like a recorded command whose closing report grows with what
there is to report.
"""


AUTO_HOLD_SECONDS_PER_LINE = 0.25
"""Seconds {func}`auto_hold` grants per populated line of the final screen.

A scanning rate rather than a reading one: terminal output is tables and
listings, which a reader sweeps at a few lines a second rather than reads
word by word.
"""


AUTO_HOLD_MIN = 2.0
"""Shortest pause {func}`auto_hold` answers.

Even a one-line outcome deserves a beat before the loop swallows it.
"""


AUTO_HOLD_MAX = 30.0
"""Longest pause {func}`auto_hold` answers.

Past this, a looping animation reads as a still that never moves: whoever
needs longer than half a minute on one screen wants the still, not the loop.
"""


_NON_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_-]+")
"""Characters a CSS class name cannot carry, as written into `unique_id`."""


_TILE_RE = re.compile(r"[─-▟]")
"""A Box Drawing or Block Elements character, which {func}`_tile_runs` cuts text at.

These are not letters, they are tiles: a table's rule, a tree's elbow and a
gradient's bar are drawn by butting them edge to edge, and a fraction of a pixel
of drift between two of them shows as a seam or a kink. A capture draws them as
shapes, see {data}`BOX_ARMS` and {data}`BLOCK_ELEMENTS`.
"""


_BRAILLE_BASE = 0x2800
"""Code point of the blank Braille pattern, which every other one is offset from.

Kept as a number: the blank pattern prints as nothing, so a literal one in the
source would read as a space.
"""


_SHAPED_RE = re.compile(
    r"(?<!\N{ZERO WIDTH JOINER})"
    f"[─-▟{chr(_BRAILLE_BASE)}-{chr(_BRAILLE_BASE + 0xFF)}]+"
)
"""A run of characters drawn as shapes: Box Drawing, Block Elements and Braille.

The first two blocks are contiguous, from U+2500 to U+259F. {func}`shape_svg`
draws them.

A run never opens on the character after a zero width joiner, which
{func}`~click_extra.layout.cell_width` counts in the cluster before it. Cut out
as a shape, it would push the text after it a cell past its column, so it stays
in the cluster's text.
"""


_COLUMN_GAP_RE = re.compile(f"[{PADDING}]{{2,}}")
"""The run of blanks separating one column of output from the next.

Two, because one space is a word break inside a phrase and two is a gutter. A
terminal has no other way to say "new column", which is what makes this the
boundary {func}`column_segments` cuts on.
"""


_GRADIENT_PATTERN = r"(?s)^(?P<kind>linear|radial)-gradient\((?P<args>.+)\)$"
"""A CSS gradient, as a backdrop may be spelled.

Left uncompiled, like the two patterns below: a gradient backdrop is the rare
capture, and {mod}`re` compiles a pattern on its first use and caches it.
"""


_ANGLE_PATTERN = r"^(?P<degrees>-?[\d.]+)deg$"
"""The angle a CSS linear gradient may open with."""


_STOP_PATTERN = r"(?s)^(?P<color>.+?)(?:\s+(?P<position>[\d.]+)%)?$"
"""One color stop of a gradient, with the position it may pin itself at."""


@lru_cache(maxsize=4096)
def _svg_number(value: float) -> str:
    """Render a coordinate the way a renderer does, to a tenth of a pixel.

    A value rounding to a negative zero is folded into a plain one: trigonometry
    lands a hair below it for every gradient running straight down, and `-0` in
    a committed file reads as a bug rather than as the zero it is.

    Cached: a capture states the same few coordinates thousands of times, one
    per column and one per row, and formatting a float costs more than finding
    it again.
    """
    rounded = round(value, 1)
    return f"{rounded or 0.0:.1f}".removesuffix(".0")


def _css_number(value: float) -> str:
    """Render a CSS percentage or duration compactly, and the same every time."""
    return f"{value:g}"


def _escape_markup(text: str, *, quote: bool = False) -> str:
    """Escape the characters markup reads, as {func}`html.escape` does.

    Spelled out rather than imported: {mod}`html` loads its whole entity table
    on import, which the `screenshot` and `snippet` commands of the
    `click-extra` CLI would pay for on every run.

    :param text: the text to escape.
    :param quote: escape both quote characters too, for an attribute value.
    :return: the escaped text.
    """
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if quote:
        text = text.replace('"', "&quot;").replace("'", "&#x27;")
    return text


def _xml_escape(text: str, *, preserve_spaces: bool = False) -> str:
    """Escape text for an XML element, spelling padding as a character reference.

    A literal non-breaking space is valid XML but invisible in a diff, and easily
    mangled by an editor stripping trailing whitespace, so it is always written
    as `&#160;`.

    `preserve_spaces` promotes the ordinary ones too, for text whose spacing is
    load-bearing: an XML parser is free to collapse a run of them into one, and
    the default `xml:space` says it may. Two spaces of a monospaced grid are two
    columns, and losing one shifts the rest of the line. Prose drawn outside that
    grid (a caption, a credit line) is left to wrap as prose does.
    """
    escaped = _escape_markup(text).replace("\N{NO-BREAK SPACE}", "&#160;")
    return escaped.replace(" ", "&#160;") if preserve_spaces else escaped


def auto_hold(text: str) -> float:
    """Seconds a reader needs on a closing screen, from how much it shows.

    Counts the populated lines of *text* (ANSI escapes stripped, blank rows
    ignored) and grants {data}`AUTO_HOLD_SECONDS_PER_LINE` for each, clamped
    between {data}`AUTO_HOLD_MIN` and {data}`AUTO_HOLD_MAX`. Lines rather than
    words, because terminal output is mostly tables whose box-drawing rows
    would drown a word count without adding anything to read.

    :param text: the final frame's captured text, ANSI escapes included.
    :return: the pause, in seconds.
    """
    lines = sum(1 for line in strip_ansi(text).splitlines() if line.strip())
    return min(AUTO_HOLD_MAX, max(AUTO_HOLD_MIN, lines * AUTO_HOLD_SECONDS_PER_LINE))


def _check_pause(seconds: float) -> float:
    """Pass a pause through, rejecting a negative one.

    The one message every pause an animation takes (a hold, a blank, a blink)
    is refused with, so the renderer, the command line and a directive agree
    on it.

    :param seconds: the pause, in seconds. Zero is a pause of no length.
    :return: `seconds`, unchanged.
    :raises ValueError: when `seconds` is negative.
    """
    if seconds < 0:
        raise ValueError(f"{seconds} is not a pause, which is never negative.")
    return seconds


def _not_a_hold(value: object) -> str:
    """The one message a hold that is neither seconds nor `auto` is refused with.

    Shared by {func}`render_svg` and {func}`parse_hold`, so the renderer and the
    command line agree on it.
    """
    return f"{value!r} is not a hold, which is seconds or 'auto'."


def parse_pause(value: str) -> float:
    """Read a pause written as text into seconds, zero included.

    :param value: the text.
    :return: the pause, in seconds.
    :raises ValueError: when the text is not a number, or is negative.
    """
    return _check_pause(float(value))


def parse_hold(value: str) -> THold:
    """Read a hold written as text into seconds, or into `auto`.

    {data}`AUTO_HOLD` scales the pause to the final frame's own line count, see
    {func}`auto_hold`.

    :param value: the text, a number of seconds or the word `auto`.
    :return: the hold.
    :raises ValueError: when the text is neither, or names a negative pause.
    """
    if value.strip().lower() == AUTO_HOLD:
        return AUTO_HOLD
    try:
        hold = float(value)
    except ValueError:
        raise ValueError(_not_a_hold(value)) from None
    return _check_pause(hold)


def blend(color: str, into: str, ratio: float) -> str:
    """Mix `color` toward `into`, the way a terminal fades dim text.

    SVG has no dim, and thinning the glyphs with `opacity` would let whatever
    sits behind the capture show through them. Mixing the two colors up front
    keeps the text opaque and lands the same shade.

    :param color: the color to fade, as `#rrggbb`.
    :param into: the color to fade it toward, usually the background.
    :param ratio: how far to go, from `0.0` (unchanged) to `1.0` (`into`).
    :return: the blended color, as `#rrggbb`.
    """
    red, green, blue = (
        round(start + (end - start) * ratio)
        for start, end in zip(hex_to_rgb(color), hex_to_rgb(into))
    )
    return rgb_to_hex((red, green, blue))


def emphasis_paint(palette: TerminalPalette) -> str:
    """The color an emphasized line's band is painted, on `palette`.

    {data}`EMPHASIS_RATIO` of the way from the terminal's background toward its
    ink, see {func}`blend`.

    :param palette: the terminal colors the capture is drawn with.
    :return: the band's color, as `#rrggbb`.
    """
    return blend(palette.background, palette.foreground, EMPHASIS_RATIO)


def _palette_slot(color: object) -> int | None:
    """The one of the sixteen terminal slots `color` names, or `None`.

    A base name (`red`) or its `bright_` form, a palette index under 16, or an
    object naming either through its `name` attribute, the way an enum member
    does. Anything else states its own color and names no slot: a `bool` is an
    `int`, and names none for all that.
    """
    if isinstance(color, int) and not isinstance(color, bool):
        return color if 0 <= color < 16 else None
    if isinstance(color, str):
        name = color.removeprefix("bright_")
        index = ANSI_INDEX.get(name)
        if index is None:
            return None
        return index if name == color else index + 8
    if hasattr(color, "name") and not isinstance(color, type):
        return _palette_slot(color.name)
    return None


def palette_color(color: object, palette: TerminalPalette) -> str:
    """Resolve any color a {class}`~click_extra.styling.Style` carries to a hex string.

    The 16 named and indexed ANSI slots are not colors, they are *names*: a
    terminal decides what its `red` looks like, and a capture has no terminal,
    so they answer to `palette`. Every other form a style can carry (a 24-bit
    triplet, a 256-cube index, a hex string) already states its own color and
    passes through.

    :param color: the value to resolve, as {class}`~click_extra.styling.Style`
        holds it.
    :param palette: the terminal colors to resolve names against.
    :return: the color, as `#rrggbb`.
    :raises ValueError: when the value names no color.
    """
    slot = _palette_slot(color)
    if slot is not None:
        return palette.ansi[slot]
    # `bool` is an `int`, and neither `True` nor `False` is a palette index.
    if not isinstance(color, bool):
        return rgb_to_hex(resolve_rgb(color))
    raise ValueError(f"Cannot resolve color: {color!r}")


def _compile_style(
    style: Style, palette: TerminalPalette
) -> tuple[str, str | None, str]:
    """Compile a style to the CSS its glyphs are drawn with, and its two paints.

    A run naming no foreground takes the terminal's, and one naming no
    background paints none, showing the terminal's own. `reverse` swaps the
    two, so the ink moves behind the glyphs and whatever was behind them, the
    terminal's background when nothing was named, becomes the ink.

    :param style: the run's style, as {func}`~click_extra.styling.split_ansi`
        yields it.
    :param palette: the terminal colors to resolve names against.
    :return: the CSS declarations, semicolon-separated; the color painted behind
        the run as `#rrggbb`, or `None` where it shows the terminal's own; and
        the ink, as `#rrggbb`, which a run drawn as shapes is painted in.
    """
    ink = palette.foreground if style.fg is None else palette_color(style.fg, palette)
    paper = None if style.bg is None else palette_color(style.bg, palette)
    if style.reverse:
        ink, paper = (palette.background if paper is None else paper), ink
    if style.dim:
        ink = blend(ink, palette.background if paper is None else paper, DIM_RATIO)
    rules = [f"fill: {ink}"]
    if style.bold:
        rules.append("font-weight: bold")
    if style.italic:
        rules.append("font-style: italic")
    # The three decorations share one property, so they are written as one
    # declaration: CSS keeps the last of a repeated property, and a run that is
    # both underlined and struck through would otherwise lose the underline.
    decorations = [
        _ATTR_CSS[attribute][1]
        for attribute in ("underline", "overline", "strikethrough")
        if getattr(style, attribute)
    ]
    if decorations:
        rules.append(f"text-decoration: {' '.join(decorations)}")
    return ";".join(rules), paper, ink


def style_rules(style: Style, palette: TerminalPalette) -> str:
    """Compile a style to the CSS an SVG text run is drawn with.

    :param style: the run's style, as {func}`~click_extra.styling.split_ansi`
        yields it.
    :param palette: the terminal colors to resolve names against.
    :return: the CSS declarations, semicolon-separated.
    """
    return _compile_style(style, palette)[0]


def cursor_cell(picture: str, columns: int) -> tuple[int, int] | None:
    """Where a terminal left its cursor on the screen a capture pictures.

    A {class}`~click_extra.capture.recording.TerminalScreen` joins its rows with
    newlines and appends what a command writes to the last of them, so the
    cursor stands at the end of that row. A picture closing on a newline
    therefore carries an empty last row, and the cursor lands on it at column
    zero, which is where a terminal puts it.

    ```{note}
    Derived rather than recorded, and exactly rather than nearly: the position
    is a property of the text a screen holds, so it survives a frame travelling
    as a bare string and costs the recorder no second channel to carry it on.
    ```

    :param picture: the captured text, ANSI escape sequences included.
    :param columns: width of the terminal, in characters.
    :return: the cursor's row and column, both counted from zero, or `None` for
        a screen showing nothing. The blank beat closing an animation's cycle is
        the one such screen, and an empty terminal shows no cursor.
    """
    if not picture.strip():
        return None
    rows = picture.split("\n")
    row, column = len(rows) - 1, cell_width(rows[-1])
    if column >= columns:
        # A terminal carries a cursor past its last column onto the next row.
        row, column = row + 1, 0
    return (row, column)


def _split_arguments(text: str) -> list[str]:
    """Split a CSS function's arguments on the commas that separate them.

    A color is a function of its own (`rgba(0, 0, 0, 0.5)`), so a plain
    {meth}`str.split` on commas would tear one apart. Only the commas outside
    every parenthesis separate arguments.
    """
    arguments: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and not depth:
            arguments.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    arguments.append("".join(current).strip())
    return [argument for argument in arguments if argument]


def gradient_svg(
    value: str,
    unique_id: str,
    width: float,
    height: float,
) -> tuple[str, str] | None:
    """Translate a CSS gradient into the paint server SVG draws it with.

    An SVG `fill` takes a paint: a color, or a reference to a gradient declared
    as an element of its own. The syntax a page's CSS carries,
    `linear-gradient(135deg, #ff9a9e, #fad0c4)`, means nothing to it, and a
    capture handed one would come out unpainted. So the CSS is read here and
    re-emitted as the element SVG does understand, which is what lets the same
    `--backdrop` value serve both formats.

    Understood: `linear-gradient` opening with an optional angle (`135deg`) or
    side keyword (`to bottom right`, see {data}`CSS_SIDE_ANGLES`), and
    `radial-gradient`, both followed by two or more color stops, each pinnable
    at a percentage. Anything else returns `None` and is left alone, being a
    plain color as far as this is concerned.

    The gradient is placed in user space, which is what makes it exact rather
    than approximated: the CSS line runs through the image's center at the given
    angle, and is as long as the box measures along it (`|W·sinθ| + |H·cosθ|`),
    while a radial one reaches the farthest corner.

    :param value: the `--backdrop` value, gradient or not.
    :param unique_id: identifier the paint server is declared under.
    :param width: width of the image the gradient fills, in pixels.
    :param height: its height.
    :return: the `<defs>` markup and the `fill` value referencing it, or `None`
        when the value is not a gradient this understands.
    """
    gradient = re.match(_GRADIENT_PATTERN, value.strip())
    if not gradient:
        return None
    arguments = _split_arguments(gradient["args"])

    angle = CSS_SIDE_ANGLES["to bottom"]
    if arguments:
        opening = arguments[0].lower()
        degrees = re.match(_ANGLE_PATTERN, opening)
        if degrees:
            angle = float(degrees["degrees"])
            arguments = arguments[1:]
        elif opening in CSS_SIDE_ANGLES:
            angle = CSS_SIDE_ANGLES[opening]
            arguments = arguments[1:]
    if len(arguments) < 2:
        return None

    stops = []
    for index, argument in enumerate(arguments):
        stop = re.match(_STOP_PATTERN, argument)
        if not stop:
            return None
        offset = (
            float(stop["position"])
            if stop["position"] is not None
            else index / (len(arguments) - 1) * 100
        )
        stops.append(
            f'<stop offset="{_svg_number(offset)}%" '
            f'stop-color="{stop["color"].strip()}"/>'
        )

    center_x, center_y = width / 2, height / 2
    if gradient["kind"] == "radial":
        geometry = (
            f'<radialGradient id="{unique_id}" gradientUnits="userSpaceOnUse" '
            f'cx="{_svg_number(center_x)}" cy="{_svg_number(center_y)}" '
            f'r="{_svg_number(hypot(width, height) / 2)}">'
        )
        closing = "</radialGradient>"
    else:
        radians = angle * pi / 180
        # CSS measures clockwise from `to top`, on a y-axis pointing down here.
        step_x, step_y = sin(radians), -cos(radians)
        length = abs(width * sin(radians)) + abs(height * cos(radians))
        geometry = (
            f'<linearGradient id="{unique_id}" gradientUnits="userSpaceOnUse" '
            f'x1="{_svg_number(center_x - step_x * length / 2)}" '
            f'y1="{_svg_number(center_y - step_y * length / 2)}" '
            f'x2="{_svg_number(center_x + step_x * length / 2)}" '
            f'y2="{_svg_number(center_y + step_y * length / 2)}">'
        )
        closing = "</linearGradient>"

    markup = f"\n{geometry}\n{''.join(stops)}\n{closing}\n"
    return (markup, f"url(#{unique_id})")


def titlebar_strip(
    left: float,
    top: float,
    width: float,
    *,
    paint: str,
    radius: int,
) -> str:
    """Paint the strip a terminal seats its title and buttons in.

    A capture leaves that strip the color of the terminal itself, where a real
    window carries a chrome of its own: the strip is what a reader's eye reads
    as the top of a window rather than as the first line of output.

    Drawn as a path rather than a rectangle because only its top corners follow
    the window's own rounding; the bottom two meet the text and stay square.

    :param left: where the window starts, in pixels.
    :param top: where the window starts vertically, in pixels.
    :param width: how wide the window is, in pixels.
    :param paint: color to fill the strip with.
    :param radius: the window's corner radius, in pixels.
    :return: the SVG markup.
    """
    right, bottom = left + width, top + TITLEBAR_HEIGHT
    corner = min(radius, TITLEBAR_HEIGHT)
    if not corner:
        return (
            f'<rect fill="{paint}" x="{_svg_number(left)}" y="{_svg_number(top)}" '
            f'width="{_svg_number(width)}" height="{TITLEBAR_HEIGHT}"/>'
        )
    return (
        f'<path fill="{paint}" d="'
        f"M{_svg_number(left + corner)},{_svg_number(top)} "
        f"H{_svg_number(right - corner)} "
        f"A{corner},{corner} 0 0 1 {_svg_number(right)},{_svg_number(top + corner)} "
        f"V{_svg_number(bottom)} H{_svg_number(left)} "
        f"V{_svg_number(top + corner)} "
        f"A{corner},{corner} 0 0 1 {_svg_number(left + corner)},{_svg_number(top)} Z"
        '"/>'
    )


def credit_markup(
    text: str,
    url: str,
    link: Callable[[str, str], str],
    *,
    escape: Callable[[str], str],
) -> str:
    """Write a credit line as markup, the package name it credits linked.

    The one part of the line worth pointing anywhere is the name, so both
    documents link that and leave the rest as prose. A line naming no package,
    or given no URL, is the escaped text and nothing more: a custom credit has
    nothing to link.

    :param text: the credit line.
    :param url: where the package name points. Empty links nothing.
    :param link: draws the anchor around the name, from the URL and the raw
        name. It escapes both for the document it writes.
    :param escape: how the rest of the line is escaped for that document.
    :return: the markup.
    """
    before, name, after = text.partition(PACKAGE_NAME)
    if not (url and name):
        return escape(text)
    return f"{escape(before)}{link(url, name)}{escape(after)}"


def _watermark_link(url: str, name: str) -> str:
    """Wrap the credit line's package name in an SVG link.

    Written as a plain `href` rather than the `xlink:href` of SVG 1.1, which
    every current browser reads and which needs no second namespace on the root
    element.
    """
    return (
        f'<a href="{_escape_markup(url, quote=True)}" class="watermark-link">'
        f'<tspan text-decoration="underline">{_xml_escape(name)}</tspan></a>'
    )


def watermark_svg(
    text: str,
    *,
    width: float,
    height: float,
    paint: str,
    font_stack: str = CAPTURE_FONT_STACK,
    url: str = WATERMARK_URL,
) -> str:
    """Draw the credit line in the image's bottom-right corner.

    Placed in the margin rather than over the terminal, which is what keeps it
    from covering a line of output: a capture is a picture of text, and a mark
    crossing that text costs the reader the thing being shown.

    Carries a `watermark` class, so a reader taking a capture apart can tell the
    one run the renderer never captured from the ones it did.

    The package name is wrapped in a link, see {data}`WATERMARK_URL` and
    {func}`credit_markup`.

    :param text: the credit to draw. Empty draws nothing.
    :param width: width of the whole image, in pixels.
    :param height: its height, in pixels.
    :param paint: color to draw the text in, alpha included.
    :param font_stack: fonts it is set in, the capture's own.
    :param url: where the package name points. Empty links nothing.
    :return: the SVG markup, empty when there is nothing to draw.
    """
    if not text:
        return ""
    body = credit_markup(text, url, _watermark_link, escape=_xml_escape)
    return (
        f'<text class="watermark" x="{_svg_number(width - WATERMARK_INSET)}" '
        f'y="{_svg_number(height - WATERMARK_INSET)}" text-anchor="end" '
        f'fill="{paint}" font-family="{font_stack}" '
        f'font-size="{WATERMARK_SIZE}">{body}</text>'
    )


def window_buttons(
    buttons: WindowButtons,
    *,
    width: float,
    color: str,
    font_stack: str = CAPTURE_FONT_STACK,
) -> str:
    """Draw a title bar's decorations, as the terminal being mimicked draws them.

    Two conventions, and a window carries one or the other: macOS fills round
    buttons on the left, Windows and GNOME set glyphs against the right edge.
    Both are placed in the window's own coordinates, so they follow it wherever
    the frame moves it.

    :param buttons: which decorations to draw.
    :param width: width of the window they are drawn in, in pixels.
    :param color: paint for the glyphs. Circles carry their own.
    :param font_stack: fonts the glyphs are set in, the window's own.
    :return: the SVG markup, empty when the window wears none.
    """
    drawn = [
        f'<circle cx="{index * 22}" cy="0" r="7" fill="{paint}"/>'
        for index, paint in enumerate(buttons.circles)
    ]
    if drawn:
        return f'<g transform="translate(26,22)">{"".join(drawn)}</g>'
    if not buttons.glyphs:
        return ""
    return (
        f'<text x="{_svg_number(width - 14)}" y="27" text-anchor="end" '
        f'fill="{color}" font-family="{font_stack}" font-size="15">'
        f"{_xml_escape('  '.join(buttons.glyphs), preserve_spaces=True)}</text>"
    )


def _row_rect(
    fill: str,
    x: float,
    top: float,
    width: float,
    *,
    height: float = LINE_HEIGHT + CELL_BLEED,
    attributes: str = "",
) -> str:
    """Draw a crisp rectangle on the text grid.

    The one shape behind a run's background, a cursor and an emphasis band,
    which all paint a row's cells and nothing else. Pixel-snapped, so two
    rectangles meeting on a boundary share it instead of leaving a hairline.

    :param fill: the paint.
    :param x: where it starts, in pixels.
    :param top: where the row's cells start, see {data}`CELL_TOP_INSET`.
    :param width: how wide it is, in pixels.
    :param height: how tall, a row's cells plus their bleed unless stated.
    :param attributes: extra attributes, each opening on a space.
    :return: the SVG markup.
    """
    return (
        f'<rect{attributes} fill="{fill}" '
        f'x="{_svg_number(x)}" y="{_svg_number(top)}" '
        f'width="{_svg_number(width)}" height="{_svg_number(height)}" '
        'shape-rendering="crispEdges"/>'
    )


def cursor_svg(
    cursor: Cursor,
    row: int,
    column: int,
    paint: str,
    unique_id: str,
) -> str:
    """Draw a terminal's cursor on the cell it stands on.

    Emitted as part of that row's cell backgrounds rather than as a layer of its
    own, which is what puts it under the glyphs and hands it to the machinery
    already deciding which rows move between frames. A row whose cursor never
    stirs is then drawn once for the whole animation, and a row that moves
    carries its cursor along at no charge. It is also why an animation typing a
    command line needs no caret of its own: the cursor follows the text.

    ```{note}
    The cursor is never drawn over a glyph, so a block shape covering one is not
    a case to answer. {func}`cursor_cell` puts it at the end of a row, which is
    past everything written on it.
    ```

    :param cursor: what the cursor looks like, see
        {class}`~click_extra.capture.presets.Cursor`.
    :param row: the row it stands on, counted from zero.
    :param column: the column it stands on, counted from zero.
    :param paint: color it is drawn in.
    :param unique_id: prefix namespacing this document's classes.
    :return: the SVG source for the cursor.
    """
    left = column * CELL_WIDTH
    top = row * LINE_HEIGHT + CELL_TOP_INSET
    height = LINE_HEIGHT + CELL_BLEED
    width = CELL_WIDTH
    shape = cursor.shape or DEFAULT_CURSOR_SHAPE
    if shape is CursorShape.BAR:
        width = CURSOR_THICKNESS
    elif shape is CursorShape.UNDERLINE:
        top += height - CURSOR_THICKNESS
        height = CURSOR_THICKNESS
    # Only a blinking cursor wears a class: a steady one needs no rule, and
    # naming a class the stylesheet does not define is what breaks a renderer.
    blinking = f' class="{unique_id}-blink"' if cursor.blink > 0 else ""
    return _row_rect(paint, left, top, width, height=height, attributes=blinking)


def column_segments(text: str, column: int) -> Iterator[tuple[str, int]]:
    """Cut a run of text into the columns it actually occupies.

    A run carries its own padding: a help screen's `--count INTEGER  Number of
    greetings.` is one styled run holding two columns and the gutter between
    them. Drawn as a single element, the second column only lands where it
    belongs if the renderer honors `textLength` and resolves the font, because
    the gutter's width is being paid for in glyphs. `librsvg` does neither, and
    the columns collapse onto each other.

    Cutting the run at its gutters and giving each piece its own offset asks
    nothing of the renderer but to draw glyphs at coordinates.

    :param text: the run's text, padding included.
    :param column: the terminal column the run starts on.
    :return: each column's text, with the column it starts on.
    """
    position = 0
    for gap in (*_COLUMN_GAP_RE.finditer(text), None):
        end = len(text) if gap is None else gap.start()
        glyphs = text[position:end].lstrip(PADDING)
        # Padding is one cell per character, so the indent is a plain count.
        start = column + end - position - len(glyphs)
        glyphs = glyphs.rstrip(PADDING)
        if glyphs:
            yield glyphs, start
        if gap is None:
            return
        column += cell_width(text[position : gap.end()])
        position = gap.end()


def _tile_runs(text: str, column: int) -> Iterator[tuple[str, int]]:
    """Break a column's text into pieces, each to be drawn as one element.

    Served as the deprecated `tile_runs` until `11.0.0`, see
    {data}`_DEPRECATED_NAMES`: a capture draws Box Drawing and Block Elements as
    shapes, which leaves no tile among its glyphs.

    Ordinary text is one piece: the renderer lays it out and `textLength` holds
    the result to the width it occupies.

    Text carrying a tile ({data}`_TILE_RE`) is cut into groups of at most
    {data}`_TILE_RUN` cells, each landing on a stated offset. A `<text>` element
    is the smallest thing some renderers position at all: `librsvg` (and through
    it `rsvg-convert` and ImageMagick) honors the first `x` of an element and
    then lays every following glyph out at the font's own advance, ignoring both
    `textLength` and any further `x`. A rule of 75 tiles drawn a tenth of a pixel
    narrow therefore ends a whole cell short of the `│` below it, and the table's
    corners miss. Restating the offset every few cells bounds that error to well
    under a pixel, whatever the font, and costs a tile nothing since none of them
    ligate.

    :param text: the column's text.
    :param column: the terminal column it starts on.
    :return: each piece, with the column it starts on.
    """
    if not _TILE_RE.search(text):
        yield text, column
        return
    cell = column
    start = 0
    while start < len(text):
        end = min(start + _TILE_RUN, len(text))
        # A piece is placed by its first glyph, so one opening on a blank draws
        # every tile behind it a cell late. Carry the blank into the piece
        # before it instead, which is the one already holding its own offset.
        while end < len(text) and text[end] in PADDING:
            end += 1
        piece = text[start:end]
        yield piece, cell
        cell += cell_width(piece)
        start = end


def glyph_offsets(text: str, column: int) -> str:
    """Place a piece of text on the grid, as the attributes SVG reads.

    A right-to-left piece is pinned by its offset alone: it is reordered and
    shaped by whoever draws it, and holding it to a width fights that.

    :param text: the piece's glyphs.
    :param column: the terminal column it starts on.
    :return: the `x` attribute, and a `textLength` where one applies.
    """
    start = f'x="{_svg_number(column * CELL_WIDTH)}"'
    if is_bidirectional(text):
        return start
    return f'{start} textLength="{_svg_number(cell_width(text) * CELL_WIDTH)}"'


def shape_runs(text: str, column: int) -> Iterator[tuple[str, int, bool]]:
    """Cut a column's text into its runs of shapes and the text between.

    A run of Box Drawing, Block Elements and Braille patterns is drawn as shapes
    by {func}`shape_svg`, and the text between as glyphs. That text is trimmed
    of the blanks at either end, which its offset pays for instead, as
    {func}`column_segments` does for a column.

    :param text: the column's text.
    :param column: the terminal column it starts on.
    :return: each piece, with the column it starts on and whether it is drawn as
        shapes.
    """
    position = 0
    for found in (*_SHAPED_RE.finditer(text), None):
        end = len(text) if found is None else found.start()
        glyphs = text[position:end].lstrip(PADDING)
        # Padding is one cell per character, so the indent is a plain count.
        indent = end - position - len(glyphs)
        glyphs = glyphs.rstrip(PADDING)
        if glyphs:
            yield glyphs, column + indent, False
        if found is None:
            return
        column += cell_width(text[position:end])
        yield found.group(), column, True
        column += cell_width(found.group())
        position = found.end()


def _extend_spans(spans: list[list[_Edge]], start: _Edge, end: _Edge) -> None:
    """Add the span from `start` to `end` to `spans`, which arrive sorted by start.

    A span reaching the last one, or overlapping it, merges into it, so a line
    running on across cells is one shape.
    """
    if spans and spans[-1][1] >= start:
        spans[-1][1] = max(spans[-1][1], end)
    else:
        spans.append([start, end])


def block_svg(text: str, column: int, top: float, ink: str, paper: str) -> str:
    """Draw a run of Block Elements as the rectangles they name.

    Each character fills its share of its cell, see {data}`BLOCK_ELEMENTS`.
    Neighbors sharing a band and a paint merge into one rectangle, so a bar of
    `█` is one shape rather than one per cell. A rectangle reaching the bottom
    of its cell takes the {data}`CELL_BLEED` a background takes, which closes
    the seam with the row below.

    :param text: the run, Block Elements only.
    :param column: the terminal column it starts on.
    :param top: where the row's cells start, see {data}`CELL_TOP_INSET`.
    :param ink: color the shapes are drawn in, as `#rrggbb`.
    :param paper: color behind them, as `#rrggbb`, which a shade mixes its ink
        with, see {data}`SHADE_DENSITY`.
    :return: the SVG markup.
    """
    # Edges are counted in eighths of a cell, as integers, so two neighbors
    # compare exactly when deciding whether they merge.
    bands: dict[tuple[int, int, str], list[list[int]]] = {}
    for offset, char in enumerate(text):
        density = SHADE_DENSITY.get(char)
        paint = ink if density is None else blend(ink, paper, 1 - density)
        origin = (column + offset) * 8
        for left, upper, right, lower in BLOCK_ELEMENTS[char]:
            _extend_spans(
                bands.setdefault((upper, lower, paint), []),
                origin + left,
                origin + right,
            )
    shapes: list[str] = []
    for (upper, lower, paint), spans in bands.items():
        height = (lower - upper) * LINE_HEIGHT / 8
        if lower == 8:
            height += CELL_BLEED
        shapes.extend(
            _row_rect(
                paint,
                left * CELL_WIDTH / 8,
                top + upper * LINE_HEIGHT / 8,
                (right - left) * CELL_WIDTH / 8,
                height=height,
            )
            for left, right in spans
        )
    return "".join(shapes)


def _shape_kind(char: str) -> str:
    """The drawer of a {data}`_SHAPED_RE` character: `box`, `block` or `braille`."""
    if ord(char) >= _BRAILLE_BASE:
        return "braille"
    return "block" if char in BLOCK_ELEMENTS else "box"


def braille_dots(char: str) -> tuple[tuple[int, int], ...]:
    """Where the dots a Braille pattern raises sit on its cell.

    :param char: a Braille pattern, from U+2800 to U+28FF.
    :return: each raised dot's `(column, row)`, see {data}`BRAILLE_DOTS`.
    """
    bits = ord(char) - _BRAILLE_BASE
    return tuple(dot for index, dot in enumerate(BRAILLE_DOTS) if bits >> index & 1)


def _braille_centers(char: str) -> tuple[tuple[float, float], ...]:
    """Where the dots a Braille pattern raises are centered on its cell.

    Each dot sits in the middle of its place on the grid of {data}`BRAILLE_DOTS`.
    {func}`braille_svg` and {func}`~click_extra.capture.html.braille_css` both
    draw them there.

    :param char: a Braille pattern, from U+2800 to U+28FF.
    :return: each raised dot's center, as shares of the cell's width and height.
    """
    return tuple(((2 * x + 1) / 4, (2 * y + 1) / 8) for x, y in braille_dots(char))


def braille_svg(text: str, column: int, top: float, ink: str) -> str:
    """Draw a run of Braille patterns as the dots they raise.

    :param text: the run, Braille patterns only.
    :param column: the terminal column it starts on.
    :param top: where the row's cells start, see {data}`CELL_TOP_INSET`.
    :param ink: color the dots are drawn in, as `#rrggbb`.
    :return: the SVG markup, empty when no pattern raises a dot.
    """
    radius = _svg_number(BRAILLE_DOT_RADIUS * CELL_WIDTH / 2)
    dots = "".join(
        f'<circle cx="{_svg_number((column + offset + across) * CELL_WIDTH)}" '
        f'cy="{_svg_number(top + down * LINE_HEIGHT)}" r="{radius}"/>'
        for offset, char in enumerate(text)
        for across, down in _braille_centers(char)
    )
    return f'<g fill="{ink}">{dots}</g>' if dots else ""


def _box_reach(spans: Sequence[tuple[int, int]], from_end: bool) -> int:
    """How far toward its middle a stroke runs to meet the nearest of `spans`."""
    if from_end:
        return max(low for low, _ in spans)
    return min(high for _, high in spans)


def _box_far(spans: Sequence[tuple[int, int]], from_end: bool, middle: int) -> int:
    """How far a stroke runs to cross all of `spans`, or to its middle without any."""
    if not spans:
        return middle
    if from_end:
        return min(low for low, _ in spans)
    return max(high for _, high in spans)


@cache
def box_strokes(char: str) -> tuple[tuple[bool, float, float, float, float], ...]:
    """The rectangles a Box Drawing line or dash fills on its cell.

    Each is `(vertical, low, high, start, end)`: whether the stroke runs down,
    then its span across and its span along, in the units of
    {data}`BOX_STROKES`, on a cell 16 wide and 32 tall. Strokes on one line are
    merged, so a straight line is one rectangle.

    A stroke runs from its cell's edge toward the middle, and stops where its
    arm meets the arms across it, the way Menlo `22.0d2e1` draws each join:

    - A line passing straight through runs on into its other half, across the
      gap of a double line if it meets one, as in `╪`.
    - A single line ending on a double line that passes through stops at its
      nearer stroke, as in `╤`.
    - A stroke of a double line stops at the nearer stroke of the arm on its
      side, as the inner corner of `╔` does.
    - Any other stroke runs to the far edge of the arms across it, which fills
      the corner it turns, as the outer corner of `╔` does.

    :param char: a Box Drawing line or dash, see {data}`BOX_ARMS` and
        {data}`BOX_DASHES`.
    :return: the rectangles.
    """
    dashed = BOX_DASHES.get(char)
    if dashed is not None:
        vertical, weight, dashes = dashed
        ((low, high),) = BOX_STROKES[weight]
        middle, length = (8, 32) if vertical else (16, 16)
        pitch = length / dashes
        return tuple(
            (
                vertical,
                middle + low,
                middle + high,
                (n + 1 / 6) * pitch,
                (n + 5 / 6) * pitch,
            )
            for n in range(dashes)
        )
    weights = dict(zip(("up", "right", "down", "left"), BOX_ARMS[char]))

    def spans(arm: str) -> list[tuple[int, int]]:
        """Where an arm's strokes sit across it, on the axis along the others."""
        middle = 8 if arm in ("up", "down") else 16
        return [
            (middle + low, middle + high)
            for low, high in BOX_STROKES.get(weights[arm], ())
        ]

    lines: dict[tuple[bool, int, int], list[list[int]]] = {}
    for arm, weight in weights.items():
        if not weight:
            continue
        vertical = arm in ("up", "down")
        from_end = arm in ("right", "down")
        middle, length = (16, 32) if vertical else (8, 16)
        lower, upper = ("left", "right") if vertical else ("up", "down")
        opposite = {"up": "down", "down": "up", "left": "right", "right": "left"}[arm]
        across = spans(lower) + spans(upper)
        lanes = spans(arm)
        for lane, (low, high) in enumerate(lanes):
            if len(lanes) == 1:
                if weights[opposite] or not across:
                    reach = middle
                elif weights[lower] == weights[upper] == 3:
                    reach = _box_reach(across, from_end)
                else:
                    reach = _box_far(across, from_end, middle)
            else:
                side = (lower, upper)[lane]
                if weights[side]:
                    reach = _box_reach(spans(side), from_end)
                else:
                    reach = _box_far(across, from_end, middle)
            lines.setdefault((vertical, low, high), []).append(
                [reach, length] if from_end else [0, reach]
            )
    merged: list[tuple[bool, float, float, float, float]] = []
    for (vertical, low, high), extents in lines.items():
        joined: list[list[int]] = []
        for start, end in sorted(extents):
            _extend_spans(joined, start, end)
        merged.extend((vertical, low, high, start, end) for start, end in joined)
    return tuple(sorted(merged))


def box_svg(text: str, column: int, top: float, ink: str) -> str:
    """Draw a run of Box Drawing as the lines it names.

    Lines and dashes are rectangles, see {func}`box_strokes`, and a stroke
    running on into the next cell merges with it, so a table's rule is one
    shape. Arcs and diagonals are paths, see {data}`BOX_CURVES`. A vertical
    stroke reaching the bottom of its cell takes the {data}`CELL_BLEED` a
    background takes, which closes the seam with the row below.

    :param text: the run, Box Drawing only.
    :param column: the terminal column it starts on.
    :param top: where the row's cells start, see {data}`CELL_TOP_INSET`.
    :param ink: color the lines are drawn in.
    :return: the SVG markup.
    """
    across = CELL_WIDTH / 16
    down = LINE_HEIGHT / 32
    # A curve is drawn as thick as a light stroke.
    (light,) = BOX_STROKES[1]
    shapes: list[str] = []
    rules: dict[tuple[float, float], list[list[float]]] = {}
    for offset, char in enumerate(text):
        origin = (column + offset) * 16
        curve = BOX_CURVES.get(char)
        if curve is not None:
            shapes.append(
                f'<path transform="translate('
                f"{_svg_number((column + offset) * CELL_WIDTH)},{_svg_number(top)}) "
                f'scale({across:g},{down:g})" d="{curve}" fill="none" '
                f'stroke="{ink}" stroke-width="{light[1] - light[0]}" '
                'stroke-linecap="square"/>'
            )
            continue
        for vertical, low, high, start, end in box_strokes(char):
            if vertical:
                height = (end - start) * down
                if end == 32:
                    height += CELL_BLEED
                shapes.append(
                    _row_rect(
                        ink,
                        (origin + low) * across,
                        top + start * down,
                        (high - low) * across,
                        height=height,
                    )
                )
                continue
            _extend_spans(
                rules.setdefault((low, high), []), origin + start, origin + end
            )
    shapes.extend(
        _row_rect(
            ink,
            start * across,
            top + low * down,
            (end - start) * across,
            height=(high - low) * down,
        )
        for (low, high), spans in rules.items()
        for start, end in spans
    )
    return "".join(shapes)


def shape_svg(text: str, column: int, top: float, ink: str, paper: str) -> str:
    """Draw a run of shapes: lines, rectangles and dots.

    Box Drawing is drawn by {func}`box_svg`, Block Elements by
    {func}`block_svg` and Braille patterns by {func}`braille_svg`.

    :param text: the run, see {func}`shape_runs`.
    :param column: the terminal column it starts on.
    :param top: where the row's cells start, see {data}`CELL_TOP_INSET`.
    :param ink: color the shapes are drawn in, as `#rrggbb`.
    :param paper: color behind them, as `#rrggbb`, see {func}`block_svg`.
    :return: the SVG markup.
    """
    drawn = []
    for kind, chars in groupby(text, key=_shape_kind):
        run = "".join(chars)
        if kind == "braille":
            drawn.append(braille_svg(run, column, top, ink))
        elif kind == "block":
            drawn.append(block_svg(run, column, top, ink, paper))
        else:
            drawn.append(box_svg(run, column, top, ink))
        column += len(run)
    return "".join(drawn)


def _frame_visibility(state: str) -> str:
    """Declare a frame shown or hidden, in both of the ways a renderer reads."""
    return f"visibility: {state}; opacity: {1 if state == 'visible' else 0};"


def _row_group(
    rows: Sequence[tuple[str, str]],
    wanted: Iterable[int],
    matrix: str,
) -> str:
    """Draw the named rows: their backgrounds first, then their glyphs.

    The glyphs share one matrix group, which is what carries the font and color
    a renderer ignoring the stylesheet falls back to. Rows carrying nothing draw
    nothing rather than an empty group.
    """
    picked = [rows[row] for row in wanted]
    cells = "".join(row_cells for row_cells, _ in picked)
    glyphs = "".join(row_glyphs for _, row_glyphs in picked)
    if not cells and not glyphs:
        return ""
    return f"{cells}{matrix}{glyphs}</g>"


def animation_digest(frames: Sequence[str], durations: Sequence[float]) -> str:
    """Fingerprint what an animation *is*, rather than how it happened to run.

    Two recordings of one unchanged command are never byte-identical: the
    durations are wall-clock, so they answer to how busy the machine was.
    Quantizing settles the ordinary jitter and cannot settle a frame the
    scheduler dropped, which leaves a shorter sequence of the same frames.

    So the fingerprint covers the frames a cycle *holds* and the beat it holds
    them on, not the order or the count. A dropped frame changes neither, and a
    command whose output actually changed changes the first.

    ```{note}
    This is what lets a rebuild leave an unchanged asset alone instead of
    rewriting it, see {data}`ANIMATION_METADATA_RE`. It is a freshness check and
    never a security one: a digest saying two animations match is a statement
    about the pixels, made by the same process that drew them.
    ```

    :param frames: each frame's captured text.
    :param durations: how long each is shown, in the same order.
    :return: the fingerprint, as hexadecimal.
    """
    # Deferred import: hashlib loads OpenSSL, which the `click-extra` CLI would
    # otherwise pay for on every start, and only an animation needs it.
    from hashlib import sha256

    beat = Counter(durations).most_common(1)[0][0] if durations else 0.0
    payload = "\n".join(sorted(set(frames))) + f"\n{beat:g}"
    return sha256(payload.encode()).hexdigest()[:16]


def animation_metadata(svg: str) -> dict[str, str]:
    """Read back what an animated capture states about itself.

    :param svg: source of a rendered capture.
    :return: the `@recording` line's fields, empty for a capture carrying none.
    """
    stated = ANIMATION_METADATA_RE.search(svg)
    if not stated:
        return {}
    return dict(
        field.split("=", 1) for field in stated.group("fields").split() if "=" in field
    )


def frame_animation_css(unique_id: str, durations: Sequence[float]) -> str:
    """Time an animated capture's frames into CSS animation rules.

    Every frame is shown for its own slice of one cycle, so a recording whose
    frames each lasted as long as the terminal held them rides the same
    machinery as a spinner whose frames are all one interval.

    ```{note}
    Each boundary is computed once and handed to both the frame that ends on it
    and the frame that starts there. Rounding the two sides of one instant
    separately is what opens a gap, which the animation shows as a blank flash,
    or an overlap, which it shows as two frames drawn at once.
    ```

    Every rule sits behind {data}`REDUCED_MOTION_QUERY`, and nothing else here
    hides anything: the frames a still is not made of carry
    {data}`HIDDEN_FRAME_ATTRIBUTES` as presentation attributes instead. A CSS
    animation outranks a presentation attribute, so the two never argue, and
    putting the hiding outside CSS altogether is what keeps a renderer reading
    no stylesheet from drawing every frame on top of the last. The keyframes
    restore both properties those attributes set, for the same reason.

    :param unique_id: prefix namespacing this document's classes and keyframes.
    :param durations: seconds each frame is shown, in order.
    :return: the stylesheet fragment, indented to sit in a `<style>` block.
    :raises ValueError: when a frame is given a duration that is not positive.
    """
    if any(duration <= 0 for duration in durations):
        raise ValueError("An animated capture's frames each last a positive time.")
    total = sum(durations)
    boundaries = [
        _css_number(running / total * 100) for running in accumulate(durations)
    ]
    # Float addition is not associative, so the running total need not land back
    # on the sum it was accumulated from. The cycle ends at its end regardless.
    boundaries[-1] = "100"

    rules = []
    for index, end in enumerate(boundaries):
        opening = "visible" if index == 0 else "hidden"
        steps = [f"0% {{ {_frame_visibility(opening)} }}"]
        if index:
            steps.append(
                f"{boundaries[index - 1]}% {{ {_frame_visibility('visible')} }}"
            )
        steps.append(f"{end}% {{ {_frame_visibility('hidden')} }}")
        rules.append(
            f"    @keyframes {unique_id}-f{index} {{ {' '.join(steps)} }}\n"
            f"    .{unique_id}-f{index} {{ animation: {unique_id}-f{index} "
            f"{_css_number(total)}s {FRAME_TIMING_FUNCTION} infinite; }}"
        )
    animation = "\n".join(rules)
    return f"    {REDUCED_MOTION_QUERY} {{\n{animation}\n    }}"


def blink_css(unique_id: str, period: float) -> str:
    """Time a cursor's blink into a CSS animation rule.

    One keyframe set and one rule for the whole document, however many frames
    it holds: a terminal has one cursor, and every frame's copy of it therefore
    lights and darkens together. It steps like a frame does, being lit or dark
    with nothing in between, see {data}`FRAME_TIMING_FUNCTION`.

    ```{note}
    The blink dims `opacity` and never touches `visibility`. A cursor sits
    inside the group of the frame it belongs to, and that group is hidden by
    both properties at once, see {data}`HIDDEN_FRAME_ATTRIBUTES`. Opacity
    multiplies down into the group, so a hidden frame's cursor stays hidden;
    a rule restoring `visibility` would instead override the inherited value
    and show every frame's cursor at once.
    ```

    The rule sits behind {data}`REDUCED_MOTION_QUERY`, which leaves the cursor
    lit and still for a reader who asked their system for less motion.

    :param unique_id: prefix namespacing this document's classes and keyframes.
    :param period: seconds one blink takes, half of it lit.
    :return: the stylesheet fragment, indented to sit in a `<style>` block.
    :raises ValueError: when the period is not positive.
    """
    if period <= 0:
        raise ValueError("A blinking cursor takes a positive time to blink.")
    return (
        f"    {REDUCED_MOTION_QUERY} {{\n"
        f"    @keyframes {unique_id}-blink "
        "{ 0% { opacity: 1; } 50% { opacity: 0; } }\n"
        f"    .{unique_id}-blink {{ animation: {unique_id}-blink "
        f"{_css_number(period)}s {FRAME_TIMING_FUNCTION} infinite; }}\n"
        "    }"
    )


def _frame_durations(
    frames: Sequence[str],
    interval: float | Sequence[float] | None,
    *,
    hold: THold,
    blank: float,
    speed: float,
) -> tuple[tuple[str, ...], tuple[float, ...]]:
    """Validate an animation's timing, and settle how long each frame lasts.

    The pacing {func}`render_svg` documents, applied in its order: `speed`
    scales the recorded durations, `hold` lengthens the last frame, and
    `blank` closes the cycle on an empty frame of its own.

    :return: the frames to draw, `blank`'s empty one included, and their
        durations, in seconds.
    :raises ValueError: on any timing {func}`render_svg` refuses.
    """
    pictures = tuple(frames)
    if not pictures:
        raise ValueError("An animated capture draws at least one frame.")
    if interval is None:
        raise ValueError("An animated capture states how long a frame lasts.")
    if isinstance(interval, int | float):
        durations = (float(interval),) * len(pictures)
    else:
        durations = tuple(float(each) for each in interval)
        if len(durations) != len(pictures):
            raise ValueError(
                f"{len(pictures)} frames carry {len(durations)} durations."
            )
    if speed <= 0:
        raise ValueError(f"{speed} is not a speed, which is positive.")
    if speed != 1:
        durations = tuple(each / speed for each in durations)
    if hold == AUTO_HOLD:
        hold = auto_hold(pictures[-1])
    # The annotation admits one word only, so a checker rules this branch out.
    # It catches the caller that never ran one: a Sphinx directive option, a CLI
    # argument, anything read from text.
    elif isinstance(hold, str):  # type: ignore[unreachable]
        raise ValueError(_not_a_hold(hold))
    if _check_pause(hold):
        # Spent on the last frame rather than on a pause of its own, so the
        # frame a still falls back to is the one that was held.
        durations = (*durations[:-1], durations[-1] + hold)
    if _check_pause(blank):
        # An empty picture, which draws nothing and reads as the cycle turning
        # over. It also leaves no row identical across every frame, so a blank
        # costs the saving a still row would otherwise make.
        pictures = (*pictures, "")
        durations = (*durations, blank)
    return pictures, durations


class _Canvas(NamedTuple):
    """Where a capture's window and text sit in the picture, in pixels."""

    width: int
    """Width of the whole image, margin included."""

    height: float
    """Height of the whole image, margin included."""

    window_width: int
    """Width of the window, rounded up to a whole pixel."""

    window_height: float
    """Height of the window."""

    edge: int
    """Distance from the image's top-left corner to the window's, on both axes."""

    origin_x: int
    """Where the text starts, from the image's left edge."""

    origin_y: int
    """Where the text starts, from the image's top edge."""

    text_width: float
    """Width of the text's columns."""

    text_height: float
    """Height of the text's rows."""


class _Screens(NamedTuple):
    """Every frame of a capture, drawn row by row."""

    painted: list[list[tuple[str, str]]]
    """Each frame's rows, as their cell backgrounds and their glyphs."""

    classes: dict[str, int]
    """The rule number of each style's CSS, shared by every frame."""

    filled: list[int]
    """How many rows each frame drew, zero for a frame holding only blanks."""

    row_count: int
    """Rows of the tallest frame, the one a cursor stands on included."""

    text_rows: int
    """Rows of the tallest frame, before a cursor is added."""


def _document_id(unique_id: str | None, pictures: Sequence[str], title: str) -> str:
    """The prefix namespacing a document's CSS classes and element IDs.

    :param unique_id: the prefix asked for, or `None` to derive one from the
        content.
    :param pictures: the captured texts the document draws.
    :param title: the caption it draws.
    :return: the prefix, folded to the characters a CSS class name can carry.
    """
    if unique_id is None:
        seed = "".join(pictures) + title
        unique_id = f"terminal-{zlib.adler32(seed.encode()):d}"
    return _NON_IDENTIFIER_RE.sub("-", unique_id)


def _draw_screens(
    pictures: Sequence[str],
    columns: int,
    *,
    wrap_marker: str,
    palette: TerminalPalette,
    unique_id: str,
    cursor: Cursor | None,
    cursor_paint: str,
    recall: bool,
) -> _Screens:
    """Lay each picture out on the grid, and draw its rows.

    :param pictures: the captured texts, one per frame.
    :param columns: width of the terminal, in characters.
    :param wrap_marker: characters closing each row a fold cut short.
    :param palette: terminal colors the ANSI codes resolve against.
    :param unique_id: prefix namespacing this document's classes.
    :param cursor: the terminal cursor to draw, or `None`.
    :param cursor_paint: color the cursor is drawn in.
    :param recall: draw a row once per distinct content and read it back
        wherever it recurs, which only an animation gains from.
    :return: the drawn frames.
    """
    # One dictionary across every frame, so a color two frames share is written
    # as a single rule and no frame can name a class the stylesheet omits.
    classes: dict[str, int] = {}
    # Each style is compiled against the palette once, however many runs wear
    # it: a help screen repeats a handful of styles across hundreds of runs.
    compiled: dict[Style, tuple[str, str | None, str]] = {}

    def draw_row(row: int, runs: Sequence[tuple[Style, str, int]]) -> tuple[str, str]:
        """Draw one row's cell backgrounds and glyphs, as two markup strings."""
        baseline = _svg_number(row * LINE_HEIGHT + CELL_HEIGHT)
        top = row * LINE_HEIGHT + CELL_TOP_INSET
        cells: list[str] = []
        glyphs: list[str] = []
        for run_style, run, column in runs:
            resolved = compiled.get(run_style)
            if resolved is None:
                resolved = compiled[run_style] = _compile_style(run_style, palette)
            css, paint, ink = resolved
            # The paint spans the whole run, padding included: a styled
            # column keeps its background across the spaces trailing it.
            if paint is not None:
                cells.append(
                    _row_rect(
                        paint, column * CELL_WIDTH, top, cell_width(run) * CELL_WIDTH
                    )
                )
            # The glyphs do not, see the note of `render_svg`.
            if not run.strip(PADDING):
                continue
            rule = classes.setdefault(css, len(classes) + 1)
            opening = f'<text class="{unique_id}-r{rule}" '
            behind = palette.background if paint is None else paint
            for column_text, start in column_segments(run, column):
                for piece, at, shaped in shape_runs(column_text, start):
                    if shaped:
                        hidden = (
                            f'{opening}{glyph_offsets(piece, at)} y="{baseline}"'
                            f"{HIDDEN_GLYPH_ATTRIBUTES}>{_xml_escape(piece)}</text>"
                        )
                        # Drawn after every row's backgrounds, like a glyph.
                        glyphs.extend((shape_svg(piece, at, top, ink, behind), hidden))
                        continue
                    glyphs.append(
                        f'{opening}{glyph_offsets(piece, at)} y="{baseline}">'
                        f"{_xml_escape(piece, preserve_spaces=True)}</text>"
                    )
        return "".join(cells), "".join(glyphs)

    # A row is drawn once per distinct content and read back wherever it recurs.
    # Most rows of a recording stand still from one frame to the next, and the
    # drawing is the costly part: measuring, cutting and escaping every run.
    # Keyed on the row index too, since the markup carries the row's vertical
    # position. A still draws each row once, so only an animation pays for it.
    drawn_rows: dict[tuple[int, tuple[tuple[Style, str, int], ...]], tuple[str, str]]
    drawn_rows = {}

    def recall_row(row: int, runs: Sequence[tuple[Style, str, int]]) -> tuple[str, str]:
        """Draw a row, or read it back when an earlier frame already drew it."""
        key = (row, tuple(runs))
        drawn = drawn_rows.get(key)
        if drawn is None:
            drawn = drawn_rows[key] = draw_row(row, runs)
        return drawn

    draw = recall_row if recall else draw_row
    painted: list[list[tuple[str, str]]] = []
    # How many rows each frame drew, which is what says whether an
    # emphasized line exists yet in it. A frame holding only blanks (the one
    # a `blank` closes the cycle with) drew none.
    filled: list[int] = []
    # Frames are stacked in one window, so the tallest is what has to fit.
    row_count = 0
    # The same count before a cursor is added, which is what `emphasize` marks:
    # a band picks out a line of output, and a cursor draws no line.
    text_rows = 0
    for picture in pictures:
        rows = grid(picture.rstrip("\n"), columns, wrap_marker=wrap_marker)
        text_rows = max(text_rows, len(rows))
        rendered_rows = [draw(row, runs) for row, runs in enumerate(rows)]
        if cursor is not None:
            standing = cursor_cell(picture, columns)
            if standing is not None:
                cursor_row, cursor_column = standing
                # A command whose last line closed on a newline leaves the
                # cursor on the row under its output, and the window grows a
                # line to hold it, exactly as the terminal's would.
                while len(rendered_rows) <= cursor_row:
                    rendered_rows.append(("", ""))
                row_cells, row_glyphs = rendered_rows[cursor_row]
                rendered_rows[cursor_row] = (
                    row_cells
                    + cursor_svg(
                        cursor, cursor_row, cursor_column, cursor_paint, unique_id
                    ),
                    row_glyphs,
                )
        painted.append(rendered_rows)
        row_count = max(row_count, len(rendered_rows))
        filled.append(len(rows) if picture.strip() else 0)
    return _Screens(painted, classes, filled, row_count, text_rows)


def _measure(
    columns: int,
    rows: int,
    chrome: Chrome,
    *,
    collapse_titlebar: bool,
) -> _Canvas:
    """Lay the window and its text out on the picture.

    :param columns: width of the terminal, in characters.
    :param rows: rows the window holds.
    :param chrome: the resolved chrome around the text.
    :param collapse_titlebar: close the window over the first row of text,
        instead of seating a title bar above it.
    :return: where everything sits.
    """
    # A collapsed title bar is negative padding applied to the top alone, which
    # is why both travel together through every measurement below.
    dropped = TITLEBAR_HEIGHT if collapse_titlebar else 0
    text_width = columns * CELL_WIDTH
    text_height = rows * LINE_HEIGHT
    window_width = ceil(text_width + 2 * (WINDOW_PADDING + chrome.padding))
    window_height = (
        text_height + TITLEBAR_HEIGHT + WINDOW_PADDING - dropped + 2 * chrome.padding
    )
    edge = chrome.margin + WINDOW_INSET
    return _Canvas(
        width=window_width + 2 * edge,
        height=window_height + 2 * edge,
        window_width=window_width,
        window_height=window_height,
        edge=edge,
        origin_x=edge + WINDOW_PADDING + chrome.padding,
        origin_y=edge + TITLEBAR_HEIGHT + chrome.padding - dropped,
        text_width=text_width,
        text_height=text_height,
    )


def _stack_frames(
    screens: _Screens,
    palette: TerminalPalette,
    unique_id: str,
    *,
    animated: bool,
) -> tuple[str, int]:
    """Stack the rows of every frame into the markup the text's clip holds.

    :param screens: the drawn frames.
    :param palette: terminal colors the text falls back to.
    :param unique_id: prefix namespacing this document's classes.
    :param animated: hide every frame but one, for the stylesheet to animate.
    :return: the markup, and the index of the frame left visible wherever the
        animation does not run.
    """
    # The stylesheet says all of this too, and says it once. It is repeated here
    # as presentation attributes because a renderer is free to ignore a `<style>`
    # block, and several do: the text then falls back to a proportional face at a
    # default size in default black, which is a terminal capture with neither its
    # grid nor its colors. A presentation attribute loses to any stylesheet rule,
    # so this changes nothing for a renderer that reads both.
    #
    # The face is named as the bare generic keyword rather than as the stack,
    # deliberately: a renderer poor enough to skip the stylesheet is one to hand
    # the single most parseable value CSS has, instead of a comma-separated list
    # of quoted family names it may take for one exotic family and fail to
    # resolve. The stack still reaches everything that reads the stylesheet,
    # which is what picks the nice face. This only decides what the rest fall
    # back to, and to a picture of a terminal any monospace is worth more than
    # the right one.
    matrix = (
        f'<g class="{unique_id}-matrix" font-family="monospace" '
        f'font-size="{_svg_number(CELL_HEIGHT)}" fill="{palette.foreground}">'
    )
    painted = screens.painted
    # The frame a renderer showing no animation is left with. The last one that
    # draws something, because an animation that accumulates (a trail filling
    # up, a bar advancing, an outcome landing) says most once it has finished,
    # and a `blank` closing the cycle says nothing at all. A spinner cycling in
    # place reads the same whichever frame is picked.
    poster = 0
    if animated:
        # Padded so a row index means the same thing in every frame.
        padded = [
            frame_rows + [("", "")] * (screens.row_count - len(frame_rows))
            for frame_rows in painted
        ]
        # A row drawn the same in every frame is drawn once, outside them. On a
        # recording where one line moves under twenty that do not, that is the
        # difference between one copy of those twenty and one copy per frame.
        still: list[int] = []
        moving: list[int] = []
        for row in range(screens.row_count):
            same = len({frame_rows[row] for frame_rows in padded}) == 1
            (still if same else moving).append(row)
        pictured = [
            index
            for index, frame_rows in enumerate(padded)
            if any(cells or glyphs for cells, glyphs in frame_rows)
        ]
        poster = pictured[-1] if pictured else len(padded) - 1
        # Each frame carries its own matrix, so the attribute fallback above
        # reaches the frames a renderer shows after the first one too. The
        # hiding is an attribute, not a rule: a renderer free to ignore the
        # stylesheet would otherwise stack every frame on top of the poster.
        layers = [_row_group(padded[0], still, matrix)]
        layers.extend(
            f'<g class="{unique_id}-f{index}"'
            f"{'' if index == poster else HIDDEN_FRAME_ATTRIBUTES}>"
            f"{_row_group(frame_rows, moving, matrix)}</g>"
            for index, frame_rows in enumerate(padded)
        )
        stack = "".join(layers)
    else:
        still_cells = "".join(row_cells for row_cells, _ in painted[0])
        still_glyphs = "".join(row_glyphs for _, row_glyphs in painted[0])
        stack = f"{still_cells}{matrix}{still_glyphs}</g>"
    return stack, poster


def _text_layer(stack: str, unique_id: str, canvas: _Canvas) -> tuple[str, str]:
    """Clip the stacked frames to the text's box, and move them onto it.

    :param stack: the markup of every frame, see {func}`_stack_frames`.
    :param unique_id: prefix namespacing this document's element IDs.
    :param canvas: where the text sits.
    :return: the clip path, and the group drawing the text through it.
    """
    # Stated where the image itself measures, rather than at the origin of the
    # group it clips. A `clipPath` in `userSpaceOnUse` (the default) resolves
    # against "the user coordinate system in place when it is referenced", and
    # renderers disagree over whether the referencing element's own `transform`
    # is part of that. Hung on a translated group, the readings differ by the
    # translation, and the one that ignores it crops the text partway down: what
    # macOS Finder's thumbnailer does. Absolute coordinates on an untranslated
    # wrapper read the same either way.
    clip = (
        f'<clipPath id="{unique_id}-clip">'
        f'<rect x="{_svg_number(canvas.origin_x)}" y="{_svg_number(canvas.origin_y)}" '
        f'width="{_svg_number(canvas.text_width)}" '
        f'height="{_svg_number(canvas.text_height)}"/></clipPath>'
    )
    # The clip and the offset are the window's, not a frame's, so they wrap the
    # whole stack rather than being repeated inside it.
    origin = (
        f"translate({_svg_number(canvas.origin_x)}, {_svg_number(canvas.origin_y)})"
    )
    return clip, (
        f'<g clip-path="url(#{unique_id}-clip)"><g transform="{origin}">{stack}</g></g>'
    )


def _backdrop_layer(backdrop: str, unique_id: str, canvas: _Canvas) -> tuple[str, str]:
    """Paint the whole image, margin included.

    :param backdrop: the paint, or a CSS gradient, see {func}`gradient_svg`.
    :param unique_id: prefix namespacing this document's element IDs.
    :param canvas: where everything sits.
    :return: the gradient the paint references, empty for a plain color, and the
        rectangle painting the image.
    """
    paint = backdrop
    ramp = ""
    gradient = gradient_svg(
        backdrop, f"{unique_id}-backdrop", canvas.width, canvas.height
    )
    if gradient:
        ramp, paint = gradient
    return ramp, (
        f'<rect fill="{paint}" x="0" y="0" '
        f'width="{_svg_number(canvas.width)}" height="{_svg_number(canvas.height)}"/>'
    )


def _shadow_layer(chrome: Chrome, unique_id: str, canvas: _Canvas) -> tuple[str, str]:
    """Cast the window's drop shadow.

    :param chrome: the resolved chrome, which names the shadow's color.
    :param unique_id: prefix namespacing this document's element IDs.
    :param canvas: where the window sits.
    :return: the filter casting the shadow, and the rectangle it is cast by.
    """
    window_edge = _svg_number(canvas.edge)
    # The shadow is cast by a rectangle of its own, laid under the window
    # rather than by a filter on the window itself. An element whose filter
    # a renderer cannot resolve is an element *in error*, which the spec
    # answers by not rendering it at all: hung on the window, a filter it
    # dislikes takes the background, the frame and the shadow down together
    # and leaves the text floating on the page. On a rectangle of its own,
    # the worst it costs is the shadow.
    #
    # The primitives are spelled out rather than left to `feDropShadow`,
    # whose result includes its source: this one keeps the blurred, offset
    # flood alone, so a window asking for `opacity` still shows the page
    # through itself instead of the slab that casts its shadow.
    return (
        f'<filter id="{unique_id}-shadow" x="-50%" y="-50%" '
        'width="200%" height="200%">'
        f'<feGaussianBlur in="SourceAlpha" stdDeviation="{SHADOW_BLUR}"/>'
        f'<feOffset dx="0" dy="{SHADOW_OFFSET}" result="cast"/>'
        f'<feFlood flood-color="{chrome.shadow}"/>'
        '<feComposite in2="cast" operator="in" result="shadow"/>'
        # Cut the window's own footprint back out, leaving the halo alone.
        # A window is drawn over its shadow and hides it, so the part
        # underneath only ever shows through one asking for `opacity`, where
        # it reads as a slab of dirty glass instead of the page behind.
        '<feComposite in="shadow" in2="SourceAlpha" operator="out"/>'
        "</filter>"
    ), (
        f'<rect filter="url(#{unique_id}-shadow)" '
        f'x="{window_edge}" y="{window_edge}" '
        f'width="{_svg_number(canvas.window_width)}" '
        f'height="{_svg_number(canvas.window_height)}" rx="{chrome.radius}"/>'
    )


def _window_layer(chrome: Chrome, palette: TerminalPalette, canvas: _Canvas) -> str:
    """Draw the window's body and its frame.

    :param chrome: the resolved chrome, which names the frame and the opacity.
    :param palette: terminal colors, whose background fills the body.
    :param canvas: where the window sits.
    :return: the SVG markup.
    """
    window_edge = _svg_number(canvas.edge)
    window = (
        f'<rect fill="{palette.background}" stroke="{chrome.border}" '
        f'stroke-width="{chrome.border_width}" x="{window_edge}" y="{window_edge}" '
        f'width="{_svg_number(canvas.window_width)}" '
        f'height="{_svg_number(canvas.window_height)}" '
        f'rx="{chrome.radius}"'
    )
    if chrome.opacity != OPAQUE:
        # Set on the fill alone, so the frame drawn by the same rect's stroke
        # keeps stating where the window ends.
        window += f' fill-opacity="{chrome.opacity}"'
    return f"{window}/>"


def _titlebar_layers(
    title: str,
    *,
    unique_id: str,
    canvas: _Canvas,
    radius: int,
    palette: TerminalPalette,
    font_stack: str,
    buttons: WindowButtons,
    buttons_color: str,
    titlebar: str,
) -> list[str]:
    """Draw the title bar: its strip, its decorations and its caption.

    :param title: caption drawn in the title bar. Empty draws none.
    :param unique_id: prefix namespacing this document's classes.
    :param canvas: where the window sits.
    :param radius: the window's corner radius, in pixels.
    :param palette: terminal colors, whose foreground draws the caption.
    :param font_stack: fonts the decorations are set in.
    :param buttons: decorations drawn in the title bar.
    :param buttons_color: paint for the glyph decorations.
    :param titlebar: paint for the strip.
        {data}`~click_extra.capture.presets.NO_PAINT` leaves it the terminal's own
        color.
    :return: the SVG markup of each layer, in drawing order.
    """
    layers = []
    if titlebar != NO_PAINT:
        layers.append(
            titlebar_strip(
                canvas.edge,
                canvas.edge,
                canvas.window_width,
                paint=titlebar,
                radius=radius,
            )
        )
    buttons_markup = window_buttons(
        buttons, width=canvas.window_width, color=buttons_color, font_stack=font_stack
    )
    window_edge = _svg_number(canvas.edge)
    layers.append(
        f'<g transform="translate({window_edge}, {window_edge})">{buttons_markup}</g>'
    )
    if title:
        layers.append(
            f'<text class="{unique_id}-title" fill="{palette.foreground}" '
            f'font-family="monospace" font-size="{TITLE_SIZE}" '
            f'font-weight="bold" text-anchor="middle" '
            f'x="{_svg_number(canvas.edge + canvas.window_width / 2)}" '
            f'y="{_svg_number(canvas.edge + CELL_HEIGHT + 6)}">'
            f"{_xml_escape(title)}</text>"
        )
    return layers


def _emphasis_layers(
    emphasize: Sequence[int],
    *,
    unique_id: str,
    canvas: _Canvas,
    chrome: Chrome,
    radius: int,
    palette: TerminalPalette,
    filled: Sequence[int],
    poster: int,
    animated: bool,
) -> tuple[str, list[str]]:
    """Draw a band across the window behind each emphasized line.

    Behind the text and behind every frame, because an emphasized line marks a
    row of the screen rather than anything a particular frame drew there.

    Drawn in the window's coordinates rather than the text's, so a band runs
    from one edge to the other instead of stopping where the padding does: the
    row is emphasized, not the column of text sitting in it. That puts it
    outside the clip holding the text, so it takes the window's own rounded
    clip instead, or a band on the last row would square off the corners it
    runs into.

    :param emphasize: lines to draw a band behind, counted from `1`.
    :param unique_id: prefix namespacing this document's classes and IDs.
    :param canvas: where the window and its text sit.
    :param chrome: the resolved chrome, whose frame the bands stop at.
    :param radius: the window's corner radius, in pixels.
    :param palette: terminal colors the band's paint is mixed from.
    :param filled: how many rows each frame drew.
    :param poster: the frame left visible where the animation does not run.
    :param animated: give each frame bands of its own.
    :return: the clip path rounding the bands to the window, and the groups
        drawing them.
    """
    # A stroke straddles the path it outlines, so half the window's frame is
    # drawn inside the window. A band running the frame's full width would
    # paint over that half and eat the border on the rows it marks. Both the
    # band and the clip rounding it therefore stop on the frame's inner
    # edge, which is where the window actually begins.
    inner = chrome.border_width / 2 if chrome.border != NO_PAINT else 0
    band_x = canvas.edge + inner
    band_width = canvas.window_width - 2 * inner
    clip = (
        f'<clipPath id="{unique_id}-window">'
        f'<rect x="{_svg_number(band_x)}" '
        f'y="{_svg_number(canvas.edge + inner)}" '
        f'width="{_svg_number(band_width)}" '
        f'height="{_svg_number(canvas.window_height - 2 * inner)}" '
        f'rx="{_svg_number(max(radius - inner, 0))}"/></clipPath>'
    )

    band_paint = emphasis_paint(palette)

    def bands(lines: Iterable[int]) -> str:
        """Draw a band across the window on each of the lines given."""
        return "".join(
            _row_rect(
                band_paint,
                band_x,
                canvas.origin_y + (line - 1) * LINE_HEIGHT + CELL_TOP_INSET,
                band_width,
            )
            for line in lines
        )

    wanted = sorted(set(emphasize))
    groups = []
    if animated:
        # One band group per frame, wearing that frame's own class so the
        # animation shows and hides the two together. A band therefore
        # arrives with the row it marks rather than waiting in empty space
        # for the animation to reach it, which is also when a gutter would
        # first number that row.
        for index, rows_drawn in enumerate(filled):
            marked = [line for line in wanted if line <= rows_drawn]
            if not marked:
                continue
            hidden = "" if index == poster else HIDDEN_FRAME_ATTRIBUTES
            groups.append(
                f'<g class="{unique_id}-f{index}"{hidden}'
                f' clip-path="url(#{unique_id}-window)">{bands(marked)}</g>'
            )
    else:
        groups.append(f'<g clip-path="url(#{unique_id}-window)">{bands(wanted)}</g>')
    return clip, groups


def _stylesheet(
    unique_id: str,
    classes: dict[str, int],
    durations: Sequence[float],
    cursor: Cursor | None,
    *,
    animated: bool,
) -> str:
    """Write the rules of a capture's stylesheet beyond the two it always has.

    :param unique_id: prefix namespacing this document's classes and keyframes.
    :param classes: the rule number of each style's CSS.
    :param durations: seconds each frame is shown, in order.
    :param cursor: the terminal cursor drawn, or `None`.
    :param animated: time the frames into an animation.
    :return: the rules, one per line.
    """
    styles = "\n".join(
        f"    .{unique_id}-r{rule} {{ {css} }}" for css, rule in classes.items()
    )
    if animated:
        styles += f"\n{frame_animation_css(unique_id, durations)}"
    if cursor is not None and cursor.blink > 0:
        styles += f"\n{blink_css(unique_id, cursor.blink)}"
    return styles


def _svg_document(
    canvas: _Canvas,
    *,
    unique_id: str,
    font_stack: str,
    recording_line: str,
    styles: str,
    defs: Sequence[str],
    body: Sequence[str],
) -> str:
    """Assemble the SVG source from its stylesheet, definitions and layers.

    :param canvas: where everything sits.
    :param unique_id: prefix namespacing this document's classes.
    :param font_stack: fonts the text is set in, best first.
    :param recording_line: the comment an animation states itself on, or empty.
    :param styles: the rules {func}`_stylesheet` writes.
    :param defs: the clip paths, gradients and filters the layers reference.
    :param body: the layers, in drawing order. Empty ones are left out.
    :return: the SVG source.
    """
    return (
        # A standalone SVG carries no HTTP header to state its encoding, and a
        # reader that assumes the platform's instead renders every multi-byte
        # character as mojibake: a full block becomes `â`, and a capture of
        # colored output becomes a wall of accented letters. XML defaults to
        # UTF-8 in the absence of a declaration, but WebKit (and therefore
        # macOS Quick Look) applies its HTML fallback to the document encoding.
        # Saying so outright costs one line and settles it everywhere.
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg viewBox="0 0 {_svg_number(canvas.width)} {_svg_number(canvas.height)}" '
        'xmlns="http://www.w3.org/2000/svg">\n'
        f"<!-- @generated by {GENERATOR_TAG} -->\n"
        f"{recording_line}"
        "<style>\n"
        f"    .{unique_id}-matrix {{\n"
        f"        font-family: {font_stack};\n"
        f"        font-size: {_svg_number(CELL_HEIGHT)}px;\n"
        f"        line-height: {_svg_number(LINE_HEIGHT)}px;\n"
        "        font-variant-east-asian: full-width;\n"
        "    }\n"
        f"    .{unique_id}-title {{\n"
        f"        font-size: {TITLE_SIZE}px;\n"
        "        font-weight: bold;\n"
        f"        font-family: {font_stack};\n"
        "    }\n"
        f"{styles}\n"
        "</style>\n"
        f"<defs>{''.join(defs)}</defs>\n"
        f"{chr(10).join(part for part in body if part)}\n"
        "</svg>\n"
    )


def render_svg(
    text: str = "",
    *,
    columns: int,
    title: str = "",
    unique_id: str | None = None,
    frames: Sequence[str] | None = None,
    interval: float | Sequence[float] | None = None,
    hold: THold = 0.0,
    blank: float = 0.0,
    speed: float = 1.0,
    emphasize: Sequence[int] = (),
    cursor: Cursor | None = None,
    wrap_marker: str = "",
    palette: TerminalPalette = DEFAULT_PRESET.dark,
    font_stack: str = CAPTURE_FONT_STACK,
    chrome: Chrome = BARE_CHROME,
    buttons: WindowButtons = MACOS_BUTTONS,
    buttons_color: str | None = None,
    titlebar: str = NO_PAINT,
    collapse_titlebar: bool = False,
) -> str:
    """Draw captured terminal text as a picture of a terminal window.

    A terminal is a fixed grid of identically-sized cells, which is what makes
    this arithmetic rather than typesetting: {func}`~click_extra.layout.grid`
    says which cell each run of same-styled characters starts on, and every
    coordinate below is that column times {data}`CELL_WIDTH`.

    Two primitives draw everything. A `<rect>` fills the cells behind a run that
    carries a background, and a `<text>` draws its glyphs, pinned to its columns
    with `textLength` so the layout survives a reader who does not have the font.
    Box Drawing, Block Elements and Braille patterns are the exception: drawn
    as shapes by {func}`shape_svg`, and kept, unpainted, as text.

    ```{note}
    A run's padding is left out of its `<text>` and paid for in the `x` offset
    instead. Written the other way, a column only lands where it belongs if the
    glyphs are exactly the width assumed here, which asks the renderer to both
    honor `textLength` and resolve the font. A web browser does both. `librsvg`
    (and through it `rsvg-convert` and ImageMagick) ignores `textLength`, and a
    file manager, a git client or a thumbnailer commonly falls back to a
    proportional font. Starting each run on its own column asks neither.
    ```

    Passing `frames` draws an animation instead of a still. The window, its
    caption and its clip path are drawn once and every frame is stacked inside
    them, so the frames differ in nothing but their text, and one stylesheet
    covers the lot: a color two frames share is one rule, and a frame cannot
    name a class the document never defines. Frames are hidden by
    {func}`frame_animation_css` in turn, leaving the last one that draws
    anything visible wherever the animation does not run.

    ```{note}
    Everything a frame carries is namespaced by `unique_id`, keyframes
    included, so two animations inlined into one HTML page keep their own
    timing. Sharing a selector between them is what makes the shorter one run
    on the longer one's clock and blank out for the frames it does not have.
    ```

    :param text: captured output, ANSI escape sequences included. The whole
        picture when `frames` is left out, and unused when it is given.
    :param columns: width of the terminal, in characters.
    :param title: caption drawn in the window's title bar. Empty draws none.
    :param unique_id: prefix namespacing this document's CSS classes and element
        IDs, see {func}`~click_extra.capture.screenshot.render`. Derived from the
        content when not given.
    :param frames: the animation's frames, each captured text, in order. A
        single frame draws the same still `text` would.
    :param interval: seconds each frame is shown. One number times every frame
        alike, which is what a spinner asks for; a sequence gives each frame its
        own, which is what a recording asks for. Required alongside `frames`.
    :param hold: extra seconds the last frame stays up before the animation
        starts over. An animation that ends somewhere (a trail filled in, a bar
        run out, an outcome landed) is worth reading, and a loop that restarts
        the instant it arrives never lets anyone. A spinner turning in place
        ends nowhere, so it wants none of this and defaults to none.
        {data}`AUTO_HOLD` scales the pause to the final frame's own line
        count, see {func}`auto_hold`.
    :param blank: seconds of empty screen closing the cycle, after `hold`. A
        loop that jumps from its last frame back to its first reads as one long
        animation doing something odd; an empty beat says plainly that this is
        where it starts over. Never the frame a still falls back to.
    :param speed: how much faster to play than it was recorded, so `2` halves
        every frame's time and `0.5` doubles it. `hold` and `blank` are stated
        in real seconds and are not scaled: they are how long a reader is given,
        not part of what is being replayed.
    :param emphasize: lines to draw a band behind, counted from `1` the way
        `:emphasize-lines:` counts them. A band runs the full width of the
        window rather than of the text, the row being what is emphasized. In an
        animation it appears with the frame that first draws the row it marks,
        which is also when a gutter would first number that row, and it is gone
        again wherever the row is.
    :param cursor: the terminal cursor to draw, see
        {class}`~click_extra.capture.presets.Cursor`. `None` draws none.
        Where it stands is read off each frame's own text, see
        {func}`cursor_cell`, so an animation carries it from screen to screen
        on its own. A cursor landing under the last line of output grows the
        window by that line, the way a terminal's does.
    :param wrap_marker: characters closing each row a fold cut short, see
        {func}`~click_extra.layout.grid`. Empty folds silently, the way a
        terminal does.
    :param palette: terminal colors the capture's ANSI codes resolve against.
    :param font_stack: fonts the text is set in, best first.
    :param chrome: the window around the text, resolved, see
        {meth}`~click_extra.capture.presets.Chrome.resolve`: its frame, corners,
        backdrop, shadow, margin, padding, opacity and credit line. Its
        `backdrop` takes a CSS gradient too, see {func}`gradient_svg`. Its
        `opacity` thins the window's body alone: the frame, the title bar and
        the text keep their own paint. Defaults to
        {data}`~click_extra.capture.presets.BARE_CHROME`.
    :param buttons: decorations drawn in the title bar.
    :param buttons_color: paint for the glyph decorations. Circles carry their
        own colors. `None` takes the palette's foreground.
    :param titlebar: paint for the strip the title and buttons sit in.
        {data}`~click_extra.capture.presets.NO_PAINT` leaves it the terminal's
        own color.
    :param collapse_titlebar: drop that strip, closing the window over the first
        line of text. For a capture wearing neither decoration nor caption.
    :return: the SVG source.
    :raises ValueError: when `chrome` is not resolved, when `frames` is given
        without an `interval`, when the two disagree on how many frames there
        are, when no frame is given, when `hold` or `blank` is negative, when
        `emphasize` names a line the capture does not have, or when a `cursor`
        is given a negative blink.
    """
    chrome.check_resolved()
    # A resolved chrome carries no `None`, as checked just above.
    radius = cast("int", chrome.radius)
    watermark_color = cast("str", chrome.watermark_color)
    animated = frames is not None
    if frames is None:
        pictures: tuple[str, ...] = (text,)
        durations: tuple[float, ...] = ()
    else:
        pictures, durations = _frame_durations(
            frames, interval, hold=hold, blank=blank, speed=speed
        )
    unique_id = _document_id(unique_id, pictures, title)
    if buttons_color is None:
        buttons_color = palette.foreground
    cursor_paint = palette.foreground
    if cursor is not None:
        if cursor.blink < 0:
            raise ValueError(f"{cursor.blink} is not a blink, which is not negative.")
        if cursor.color is not None:
            cursor_paint = cursor.color

    screens = _draw_screens(
        pictures,
        columns,
        wrap_marker=wrap_marker,
        palette=palette,
        unique_id=unique_id,
        cursor=cursor,
        cursor_paint=cursor_paint,
        recall=animated,
    )
    beyond = sorted(line for line in emphasize if not 1 <= line <= screens.text_rows)
    if beyond:
        raise ValueError(
            f"Cannot emphasize line {', '.join(map(str, beyond))} of a capture "
            f"{screens.text_rows} lines long."
        )
    canvas = _measure(
        columns, screens.row_count, chrome, collapse_titlebar=collapse_titlebar
    )
    stack, poster = _stack_frames(screens, palette, unique_id, animated=animated)
    clip, text_layer = _text_layer(stack, unique_id, canvas)

    defs = [clip]
    body = []
    if chrome.backdrop != NO_PAINT:
        ramp, backdrop = _backdrop_layer(chrome.backdrop, unique_id, canvas)
        if ramp:
            defs.append(ramp)
        body.append(backdrop)
    if chrome.shadow != NO_PAINT:
        shadow_filter, shadow = _shadow_layer(chrome, unique_id, canvas)
        defs.append(shadow_filter)
        body.append(shadow)
    body.append(_window_layer(chrome, palette, canvas))
    if not collapse_titlebar:
        body.extend(
            _titlebar_layers(
                title,
                unique_id=unique_id,
                canvas=canvas,
                radius=radius,
                palette=palette,
                font_stack=font_stack,
                buttons=buttons,
                buttons_color=buttons_color,
                titlebar=titlebar,
            )
        )
    if emphasize:
        window_clip, bands = _emphasis_layers(
            emphasize,
            unique_id=unique_id,
            canvas=canvas,
            chrome=chrome,
            radius=radius,
            palette=palette,
            filled=screens.filled,
            poster=poster,
            animated=animated,
        )
        defs.append(window_clip)
        body.extend(bands)
    body.extend((
        text_layer,
        watermark_svg(
            chrome.watermark,
            width=canvas.width,
            height=canvas.height,
            paint=watermark_color,
            font_stack=font_stack,
        ),
    ))

    # An animation states what it is, so a rebuild can leave an unchanged
    # one alone instead of rewriting bytes its own clock jitter moved.
    recording_line = ""
    if animated:
        recording_line = (
            f"<!-- @recording frames={len(pictures)} "
            f"period={_css_number(sum(durations))}s "
            f"digest={animation_digest(pictures, durations)} -->\n"
        )

    return _svg_document(
        canvas,
        unique_id=unique_id,
        font_stack=font_stack,
        recording_line=recording_line,
        styles=_stylesheet(
            unique_id, screens.classes, durations, cursor, animated=animated
        ),
        defs=defs,
        body=body,
    )


_DEPRECATED_NAMES = {
    "TILE_RUN": "_TILE_RUN",
    "_TILING_RE": "_TILE_RE",
    "tile_runs": "_tile_runs",
}
"""Names a capture no longer uses, each with the private one holding its value.

{func}`shape_svg` draws Box Drawing and Block Elements as shapes, which leaves no
tile among a capture's glyphs for {func}`_tile_runs` to cut. `__getattr__` serves
each old name until {data}`_REMOVAL_VERSION`.
"""


_REMOVAL_VERSION = "11.0.0"
"""The release in which the names of {data}`_DEPRECATED_NAMES` stop resolving."""


def __getattr__(name: str) -> Any:
    """Serve a name of {data}`_DEPRECATED_NAMES`, with a warning.

    The value is never cached here, so every access warns. Any other name raises
    {exc}`AttributeError` without a warning.
    """
    private = _DEPRECATED_NAMES.get(name)
    if private is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        f"{__name__}.{name} is deprecated and will be removed in click-extra "
        f"{_REMOVAL_VERSION}: a capture draws Box Drawing as shapes.",
        DeprecationWarning,
        stacklevel=2,
    )
    return globals()[private]
