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

{mod}`click_extra.screenshot` decides what a capture shows, then hands the text,
its palette and the resolved {class}`~click_extra.screenshot.Chrome` to
{func}`render_svg`, which lays the text out on a character grid and paints the
window around it: frame, title bar, shadow, backdrop, cursor, emphasis bands,
credit line and animation.

The window's geometry and paint vocabulary live here too, since every pixel size
below is the picture's: {data}`NO_PAINT` and {data}`OPAQUE`, the default frame,
radius and shadow, the credit line's ink, size and text, and the cell metrics
the grid is measured in. The HTML renderer of {mod}`click_extra.screenshot`
draws the same window and borrows them, so the two documents look like the same
terminal.
"""

from __future__ import annotations

import re
import zlib
from collections import Counter
from hashlib import sha256
from html import escape
from importlib import metadata
from math import ceil, cos, hypot, pi, sin

from boltons.strutils import strip_ansi

from ._utils import generator_tag
from .layout import PADDING, cell_width, grid, is_bidirectional
from .screenshot_presets import (
    CAPTURE_FONT_STACK,
    DEFAULT_PRESET,
    MACOS_BUTTONS,
    Cursor,
    CursorShape,
    TerminalPalette,
    WindowButtons,
)
from .styling import _ANSI_INDEX, _ATTR_CSS, _hex_to_rgb, _palette_to_rgb, _rgb_to_hex

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from typing import Literal, TypeAlias

    from .styling import Style

    THold: TypeAlias = float | Literal["auto"]
    """Pause an animation takes on its last frame, see {data}`AUTO_HOLD`."""


NO_PAINT = "none"
"""Border or shadow value asking for none to be drawn.

SVG's own keyword for an absent paint, so it reaches the `stroke` attribute
unchanged, and CSS's for an absent shadow.
"""


OPAQUE = 1.0
"""Opacity of a window showing nothing of what sits behind it.

Anything under it is what a terminal calls transparency: the backdrop, or the
page embedding the capture, comes through the window's body while its text,
frame and title bar stay as they are. `0.0` leaves the text alone on the page.
"""


WATERMARK_INK = "rgba(128,128,128,0.85)"
"""Color the credit line is drawn in.

The one paint in a capture that answers to neither chrome, because it is the one
thing drawn outside the window: the margin is transparent, so the mark sits on
whatever page embeds the image, which the capture never gets to see. A white
mark suits the dark chrome it was picked for and disappears on a README; a
neutral gray reads on both, and dims into a backdrop when one is painted.
"""


DEFAULT_BORDER_WIDTH = 1
"""Thickness, in pixels, of the frame drawn around the window."""


TITLEBAR_HEIGHT = 40
"""Height, in pixels, of the strip a title and its buttons sit in.

The padding a renderer leaves above the text, which is what a window's chrome
occupies. Restated here because a capture wearing neither decoration nor caption
drops the strip, and one drawn as a real terminal paints it.
"""


DEFAULT_RADIUS = 8
"""How round the window's corners are, in pixels.

The radius a renderer draws on its own, which is what a terminal on a desktop
looks like. Zero squares them, for a capture meant to read as a plain block.
"""


SHADOW_BLUR = 6
"""Standard deviation, in pixels, of the drop shadow's blur."""


SHADOW_OFFSET = 3
"""Downward offset, in pixels, of the drop shadow."""


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


PACKAGE_NAME = "click-extra"
"""Name this package is distributed and credited under."""


def _package_release() -> str:
    """The release this build of the package belongs to.

    Read from the installed distribution rather than the package's own
    `__version__`, the way {mod}`click_extra.version` reads its dependencies'.
    The segment naming the build is dropped: a capture shot from a checkout of
    the `1.2.3` cycle is showing what `1.2.3` draws, and stamping `1.2.3.dev4`
    on it would date every committed image as unreleased, then rewrite it on the
    day the release makes it true.

    :return: the release, or an empty string when the package is not installed.
    """
    try:
        release = metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return ""
    return release.split(".dev")[0].split("+")[0]


DEFAULT_WATERMARK = f"generated with {PACKAGE_NAME} {_package_release()}".rstrip()
"""Credit line every capture carries unless another one, or none, is asked for.

A capture travels: it lands on a slide, in a README, on a social card, far from
the page that explains where it came from. The mark is what still says so, and
names the release that drew it, so a reader can tell an image shot two years ago
from one shot today.

```{note}
This is a default, not a fixture. `--watermark ""` draws none, and any other
text replaces it: a project crediting itself rather than its tooling is the
expected case, not an exception.
```
"""


WATERMARK_URL = f"https://kdeldycke.github.io/{PACKAGE_NAME}/screenshots.html"
"""Page the credit line points at, for a reader holding only the image.

A capture travels away from whatever explained it, so the mark carries the way
back. Only {data}`PACKAGE_NAME` is linked, and only where the line still names
it: a project crediting itself instead has no click-extra left to point at, and
gets no link rather than one pointing somewhere it did not ask for.

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

Fira Code's, the first family {data}`~click_extra.screenshot_presets.CAPTURE_FONT_STACK`
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

Both {attr}`~click_extra.screenshot_presets.CursorShape.BAR` and
{attr}`~click_extra.screenshot_presets.CursorShape.UNDERLINE` are the same line
turned a quarter, so one number states both. Thin enough to read as a cursor
beside a glyph, thick enough to survive a renderer rounding it to whole pixels.
"""


DEFAULT_CURSOR_SHAPE = CursorShape.BLOCK
"""Shape a cursor takes when nothing names one.

What every terminal here but Windows draws, and the shape a reader recognizes
as a terminal cursor rather than as a text caret. A capture given a preset takes
that terminal's own shape instead, see
{attr}`~click_extra.screenshot_presets.TerminalPreset.cursor`.
"""


TILE_RUN = 8
"""Cells of tiling characters drawn before their offset is restated.

Small enough that a font whose tiles are a fraction of a pixel off the grid
cannot drift a visible amount before the next offset resets it, and large enough
that a table's rule stays a handful of elements rather than one per cell. See
{func}`tile_runs`.
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
Neither property is redundant, and the split was found the hard way. `visibility`
alone was tried first and satisfies a browser, `librsvg` and macOS Quick Look's
*thumbnailer*. Two other readers ignored it and drew every frame on top of the
last: a git client's SVG diff view, and macOS Finder's *preview pane*, which is
a different code path from the thumbnailer that was already working. Adding
`opacity` fixed both, so each property covers a reader the other misses and
dropping either takes a class of reader with it.
```
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


AUTO_HOLD: Literal["auto"] = "auto"
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


_NON_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_-]+")
"""Characters a CSS class name cannot carry, as written into `unique_id`."""


_TILING_RE = re.compile(r"[─-▟]")
"""A Box Drawing or Block Elements character.

These are not letters, they are tiles: a table's rule, a tree's elbow and a
gradient's bar are drawn by butting them edge to edge, and a fraction of a pixel
of drift between two of them shows as a seam or a kink. They also never ligate,
which is what makes it free to place each one on its own cell rather than
letting the renderer space them, see {func}`glyph_offsets`.
"""


_COLUMN_GAP_RE = re.compile(f"[{PADDING}]{{2,}}")
"""The run of blanks separating one column of output from the next.

Two, because one space is a word break inside a phrase and two is a gutter. A
terminal has no other way to say "new column", which is what makes this the
boundary {func}`column_segments` cuts on.
"""


_GRADIENT_RE = re.compile(
    r"^(?P<kind>linear|radial)-gradient\((?P<args>.+)\)$", re.DOTALL
)
"""A CSS gradient, as a backdrop may be spelled."""


_ANGLE_RE = re.compile(r"^(?P<degrees>-?[\d.]+)deg$")
"""The angle a CSS linear gradient may open with."""


_STOP_RE = re.compile(r"^(?P<color>.+?)(?:\s+(?P<position>[\d.]+)%)?$", re.DOTALL)
"""One color stop of a gradient, with the position it may pin itself at."""


def cursor_cell(picture: str, columns: int) -> tuple[int, int] | None:
    """Where a terminal left its cursor on the screen a capture pictures.

    A {class}`~click_extra.recording.TerminalScreen` joins its rows with
    newlines and appends what a command writes to the last of them, so the
    cursor stands at the end of that row. A picture closing on a newline
    therefore carries an empty last row, and the cursor lands on it at column
    zero, which is where a terminal puts it.

    ```{note}
    Derived rather than recorded, and exactly rather than nearly: the position
    is a property of the text a screen holds, so it survives a frame travelling
    as a bare string and costs the recorder no second channel to carry it on.
    Checked against the screen's own column across a spinner's writes.
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
    if isinstance(color, str):
        if color.startswith("#"):
            return color
        if color.startswith("bright_"):
            index = _ANSI_INDEX.get(color.removeprefix("bright_"))
            if index is not None:
                return palette.ansi[index + 8]
        elif color in _ANSI_INDEX:
            return palette.ansi[_ANSI_INDEX[color]]
    # `bool` is an `int`, and neither `True` nor `False` is a palette index.
    elif isinstance(color, int) and not isinstance(color, bool):
        if 0 <= color < 16:
            return palette.ansi[color]
        return _rgb_to_hex(_palette_to_rgb(color))
    elif isinstance(color, tuple) and len(color) == 3:
        return _rgb_to_hex(color)
    elif hasattr(color, "name") and not isinstance(color, type):
        return palette_color(color.name, palette)
    raise ValueError(f"Cannot resolve color: {color!r}")


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
    start, end = _hex_to_rgb(color), _hex_to_rgb(into)
    return _rgb_to_hex(
        tuple(round(a + (b - a) * ratio) for a, b in zip(start, end)),  # type: ignore[arg-type]
    )


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
    gradient = _GRADIENT_RE.match(value.strip())
    if not gradient:
        return None
    arguments = _split_arguments(gradient["args"])

    angle = CSS_SIDE_ANGLES["to bottom"]
    if arguments:
        opening = arguments[0].strip().lower()
        degrees = _ANGLE_RE.match(opening)
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
        stop = _STOP_RE.match(argument)
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


def credit_segments(text: str) -> tuple[str, str, str] | None:
    """Split a credit line around the package name it credits.

    The one part of the line worth pointing anywhere is the name, so both
    formats link that and leave the rest as prose. Splitting is what keeps a
    custom credit out of it: a line not naming the package has nothing to link.

    :param text: the credit line.
    :return: what precedes the name, the name, and what follows it, or `None`
        when the line does not name the package.
    """
    before, name, after = text.partition(PACKAGE_NAME)
    return (before, name, after) if name else None


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

    The package name is wrapped in a link, see {data}`WATERMARK_URL`. Written as
    a plain `href` rather than the `xlink:href` of SVG 1.1, which every current
    browser reads and which needs no second namespace on the root element.

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
    body = _xml_escape(text)
    segments = credit_segments(text) if url else None
    if segments:
        before, name, after = segments
        body = (
            f"{_xml_escape(before)}"
            f'<a href="{escape(url)}" class="watermark-link">'
            f'<tspan text-decoration="underline">{_xml_escape(name)}</tspan>'
            f"</a>{_xml_escape(after)}"
        )
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
        {class}`~click_extra.screenshot_presets.Cursor`.
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
    return (
        f'<rect{blinking} fill="{paint}" '
        f'x="{_svg_number(left)}" y="{_svg_number(top)}" '
        f'width="{_svg_number(width)}" height="{_svg_number(height)}" '
        'shape-rendering="crispEdges"/>'
    )


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
        chunk = text[position : gap.start() if gap else len(text)]
        glyphs = chunk.strip(PADDING)
        if glyphs:
            indent = cell_width(chunk) - cell_width(chunk.lstrip(PADDING))
            yield glyphs, column + cell_width(text[:position]) + indent
        if gap is None:
            break
        position = gap.end()


def tile_runs(text: str, column: int) -> Iterator[tuple[str, int]]:
    """Break a column's text into the pieces drawn as one element each.

    Ordinary text is one piece: the renderer lays it out and `textLength` holds
    the result to the width it occupies.

    Text carrying a tile ({data}`_TILING_RE`) is cut into groups of at most
    {data}`TILE_RUN` cells, each landing on a stated offset. A `<text>` element
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
    if not _TILING_RE.search(text):
        yield text, column
        return
    cell = column
    start = 0
    while start < len(text):
        end = min(start + TILE_RUN, len(text))
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


def style_rules(style: Style, palette: TerminalPalette) -> str:
    """Compile a style to the CSS an SVG text run is drawn with.

    :param style: the run's style, as {func}`~click_extra.styling.split_ansi`
        yields it.
    :param palette: the terminal colors to resolve names against.
    :return: the CSS declarations, semicolon-separated.
    """
    ink = palette.foreground if style.fg is None else palette_color(style.fg, palette)
    paper = palette.background if style.bg is None else palette_color(style.bg, palette)
    if style.reverse:
        ink, paper = paper, ink
    if style.dim:
        ink = blend(ink, paper, DIM_RATIO)
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
    return ";".join(rules)


def run_paint(style: Style, palette: TerminalPalette) -> str | None:
    """The color painted behind a run, or `None` where it shows the terminal's own.

    :param style: the run's style.
    :param palette: the terminal colors to resolve names against.
    :return: the background color, as `#rrggbb`, or `None` to paint nothing.
    """
    if style.reverse:
        return (
            palette.foreground if style.fg is None else palette_color(style.fg, palette)
        )
    return None if style.bg is None else palette_color(style.bg, palette)


def _css_number(value: float) -> str:
    """Render a CSS percentage or duration compactly, and the same every time."""
    return f"{value:g}"


def _frame_visibility(state: str) -> str:
    """Declare a frame shown or hidden, in both of the ways a renderer reads."""
    return f"visibility: {state}; opacity: {1 if state == 'visible' else 0};"


def _row_group(
    rows: Sequence[tuple[str, str]],
    wanted: Sequence[int],
    matrix: str,
) -> str:
    """Draw the named rows: their backgrounds first, then their glyphs.

    The glyphs share one matrix group, which is what carries the font and color
    a renderer ignoring the stylesheet falls back to. Rows carrying nothing draw
    nothing rather than an empty group.
    """
    cells = "".join(rows[row][0] for row in wanted)
    glyphs = "".join(rows[row][1] for row in wanted)
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
    hides anything: the frames a still is not made of carry `visibility="hidden"`
    as a presentation attribute instead. A CSS animation outranks a presentation
    attribute, so the two never argue, and putting the hiding outside CSS
    altogether is what keeps a renderer reading no stylesheet from drawing every
    frame on top of the last.

    :param unique_id: prefix namespacing this document's classes and keyframes.
    :param durations: seconds each frame is shown, in order.
    :return: the stylesheet fragment, indented to sit in a `<style>` block.
    :raises ValueError: when a frame is given a duration that is not positive.
    """
    if any(duration <= 0 for duration in durations):
        raise ValueError("An animated capture's frames each last a positive time.")
    total = sum(durations)
    boundaries = []
    running = 0.0
    for duration in durations:
        running += duration
        boundaries.append(_css_number(running / total * 100))
    # Float addition is not associative, so the running total need not land back
    # on the sum it was accumulated from. The cycle ends at its end regardless.
    boundaries[-1] = "100"

    # Two properties, not one. A frame is hidden by presentation attributes so a
    # renderer reading no stylesheet still shows one picture, and a renderer
    # honoring only one of the two is common enough to be worth answering: file
    # managers and git clients have both been seen drawing every frame at once.
    # The animation therefore has to restore whichever attribute was honored.
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
    palette: TerminalPalette = DEFAULT_PRESET.dark,
    font_stack: str = CAPTURE_FONT_STACK,
    border: str = NO_PAINT,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int = DEFAULT_RADIUS,
    backdrop: str = NO_PAINT,
    shadow: str = NO_PAINT,
    margin: int = 0,
    padding: int = 0,
    buttons: WindowButtons = MACOS_BUTTONS,
    buttons_color: str | None = None,
    titlebar: str = NO_PAINT,
    collapse_titlebar: bool = False,
    opacity: float = OPAQUE,
    watermark: str = "",
    watermark_color: str = WATERMARK_INK,
) -> str:
    """Draw captured terminal text as a picture of a terminal window.

    A terminal is a fixed grid of identically-sized cells, which is what makes
    this arithmetic rather than typesetting: {func}`~click_extra.layout.grid`
    says which cell each run of same-styled characters starts on, and every
    coordinate below is that column times {data}`CELL_WIDTH`.

    Two primitives draw everything. A `<rect>` fills the cells behind a run that
    carries a background, and a `<text>` draws its glyphs, pinned to its columns
    with `textLength` so the layout survives a reader who does not have the font.

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
    {func}`frame_animation_css` in turn, leaving the first one visible wherever
    the animation does not run.

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
        IDs, see {func}`~click_extra.screenshot.render`. Derived from the content when
        not given.
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
        {class}`~click_extra.screenshot_presets.Cursor`. `None` draws none,
        which is what every capture taken before this option existed shows.
        Where it stands is read off each frame's own text, see
        {func}`cursor_cell`, so an animation carries it from screen to screen
        on its own. A cursor landing under the last line of output grows the
        window by that line, the way a terminal's does.
    :param palette: terminal colors the capture's ANSI codes resolve against.
    :param font_stack: fonts the text is set in, best first.
    :param border: paint for the window's frame. {data}`NO_PAINT` draws none.
    :param border_width: thickness of that frame, in pixels.
    :param radius: how round the window's corners are, in pixels.
    :param backdrop: paint filling the whole image, margin included, or a CSS
        gradient, see {func}`gradient_svg`. {data}`NO_PAINT` leaves it
        transparent.
    :param shadow: color the window's drop shadow floods with.
    :param margin: transparent pixels left around the window, on all four sides.
    :param padding: pixels added inside the window, around the text.
    :param buttons: decorations drawn in the title bar.
    :param buttons_color: paint for the glyph decorations. Circles carry their
        own colors. `None` takes the palette's foreground.
    :param titlebar: paint for the strip the title and buttons sit in.
        {data}`NO_PAINT` leaves it the terminal's own color.
    :param collapse_titlebar: drop that strip, closing the window over the first
        line of text. For a capture wearing neither decoration nor caption.
    :param opacity: how solid the window's body is, from {data}`OPAQUE` down to
        `0.0`. Only the body thins out: the frame, the title bar and the text
        keep their own paint.
    :param watermark: credit line drawn in the image's bottom-right corner.
    :param watermark_color: color that line is drawn in, alpha included.
    :return: the SVG source.
    :raises ValueError: when `frames` is given without an `interval`, when the
        two disagree on how many frames there are, when no frame is given, when
        `emphasize` names a line the capture does not have, or when a `cursor`
        is given a negative blink.
    """
    animated = frames is not None
    pictures = tuple(frames) if frames is not None else (text,)
    if not pictures:
        raise ValueError("An animated capture draws at least one frame.")
    durations: tuple[float, ...] = ()
    if animated:
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
        # The annotation admits one word only, so a checker rules this branch
        # out. It catches the caller that never ran one: a Sphinx directive
        # option, a CLI argument, anything read from text.
        elif isinstance(hold, str):  # type: ignore[unreachable]
            raise ValueError(f"{hold!r} is not a hold, which is seconds or 'auto'.")
        if hold:
            # Spent on the last frame rather than on a pause of its own, so the
            # frame a still falls back to is the one that was held.
            durations = (*durations[:-1], durations[-1] + hold)
        if blank:
            if blank < 0:
                raise ValueError(f"{blank} is not a pause, which is not negative.")
            # An empty picture, which draws nothing and reads as the cycle
            # turning over. It also leaves no row identical across every frame,
            # so a blank costs the saving a still row would otherwise make.
            pictures = (*pictures, "")
            durations = (*durations, blank)
    if unique_id is None:
        seed = "".join(pictures) + title
        unique_id = f"terminal-{zlib.adler32(seed.encode()):d}"
    unique_id = _NON_IDENTIFIER_RE.sub("-", unique_id)
    if buttons_color is None:
        buttons_color = palette.foreground
    cursor_paint = palette.foreground
    if cursor is not None:
        if cursor.blink < 0:
            raise ValueError(f"{cursor.blink} is not a blink, which is not negative.")
        if cursor.color is not None:
            cursor_paint = cursor.color

    # One dictionary across every frame, so a color two frames share is written
    # as a single rule and no frame can name a class the stylesheet omits.
    classes: dict[str, int] = {}
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
        rows = grid(picture.rstrip("\n"), columns)
        text_rows = max(text_rows, len(rows))
        rendered_rows: list[tuple[str, str]] = []
        for row, runs in enumerate(rows):
            baseline = row * LINE_HEIGHT + CELL_HEIGHT
            cells: list[str] = []
            glyphs: list[str] = []
            for run_style, run, column in runs:
                # The paint spans the whole run, padding included: a styled
                # column keeps its background across the spaces trailing it.
                paint = run_paint(run_style, palette)
                if paint is not None:
                    cells.append(
                        f'<rect fill="{paint}" '
                        f'x="{_svg_number(column * CELL_WIDTH)}" '
                        f'y="{_svg_number(row * LINE_HEIGHT + CELL_TOP_INSET)}" '
                        f'width="{_svg_number(cell_width(run) * CELL_WIDTH)}" '
                        f'height="{_svg_number(LINE_HEIGHT + CELL_BLEED)}" '
                        'shape-rendering="crispEdges"/>'
                    )
                # The glyphs do not, see this function's note.
                if not run.strip(PADDING):
                    continue
                rule = classes.setdefault(
                    style_rules(run_style, palette), len(classes) + 1
                )
                for column_text, start in column_segments(run, column):
                    for drawn, at in tile_runs(column_text, start):
                        glyphs.append(
                            f'<text class="{unique_id}-r{rule}" '
                            f"{glyph_offsets(drawn, at)} "
                            f'y="{_svg_number(baseline)}">'
                            f"{_xml_escape(drawn, preserve_spaces=True)}</text>"
                        )
            rendered_rows.append(("".join(cells), "".join(glyphs)))
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

    # A collapsed title bar is negative padding applied to the top alone, which
    # is why both travel together through every measurement below.
    dropped = TITLEBAR_HEIGHT if collapse_titlebar else 0
    text_width = columns * CELL_WIDTH
    text_height = row_count * LINE_HEIGHT
    beyond = sorted(line for line in emphasize if not 1 <= line <= text_rows)
    if beyond:
        raise ValueError(
            f"Cannot emphasize line {', '.join(map(str, beyond))} of a capture "
            f"{text_rows} lines long."
        )
    window_width = ceil(text_width + 2 * (WINDOW_PADDING + padding))
    window_height = (
        text_height + TITLEBAR_HEIGHT + WINDOW_PADDING - dropped + 2 * padding
    )
    width = window_width + 2 * (margin + WINDOW_INSET)
    height = window_height + 2 * (margin + WINDOW_INSET)
    origin_x = margin + WINDOW_INSET + WINDOW_PADDING + padding
    origin_y = margin + WINDOW_INSET + TITLEBAR_HEIGHT + padding - dropped

    # Stated where the image itself measures, rather than at the origin of the
    # group it clips. A `clipPath` in `userSpaceOnUse` (the default) resolves
    # against "the user coordinate system in place when it is referenced", and
    # renderers disagree over whether the referencing element's own `transform`
    # is part of that. Hung on a translated group, the readings differ by the
    # translation, and the one that ignores it crops the text partway down: what
    # macOS Finder's thumbnailer does. Absolute coordinates on an untranslated
    # wrapper read the same either way.
    defs = [
        (
            f'<clipPath id="{unique_id}-clip">'
            f'<rect x="{_svg_number(origin_x)}" y="{_svg_number(origin_y)}" '
            f'width="{_svg_number(text_width)}" '
            f'height="{_svg_number(text_height)}"/></clipPath>'
        )
    ]
    body = []

    paint = backdrop
    if backdrop != NO_PAINT:
        ramp = gradient_svg(backdrop, f"{unique_id}-backdrop", width, height)
        if ramp:
            defs.append(ramp[0])
            paint = ramp[1]
        body.append(
            f'<rect fill="{paint}" x="0" y="0" '
            f'width="{_svg_number(width)}" height="{_svg_number(height)}"/>'
        )

    if shadow != NO_PAINT:
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
        defs.append(
            f'<filter id="{unique_id}-shadow" x="-50%" y="-50%" '
            'width="200%" height="200%">'
            f'<feGaussianBlur in="SourceAlpha" stdDeviation="{SHADOW_BLUR}"/>'
            f'<feOffset dx="0" dy="{SHADOW_OFFSET}" result="cast"/>'
            f'<feFlood flood-color="{shadow}"/>'
            '<feComposite in2="cast" operator="in" result="shadow"/>'
            # Cut the window's own footprint back out, leaving the halo alone.
            # A window is drawn over its shadow and hides it, so the part
            # underneath only ever shows through one asking for `opacity`, where
            # it reads as a slab of dirty glass instead of the page behind.
            '<feComposite in="shadow" in2="SourceAlpha" operator="out"/>'
            "</filter>"
        )
        body.append(
            f'<rect filter="url(#{unique_id}-shadow)" '
            f'x="{_svg_number(margin + WINDOW_INSET)}" '
            f'y="{_svg_number(margin + WINDOW_INSET)}" '
            f'width="{_svg_number(window_width)}" '
            f'height="{_svg_number(window_height)}" rx="{radius}"/>'
        )

    window = (
        f'<rect fill="{palette.background}" stroke="{border}" '
        f'stroke-width="{border_width}" x="{_svg_number(margin + WINDOW_INSET)}" '
        f'y="{_svg_number(margin + WINDOW_INSET)}" '
        f'width="{_svg_number(window_width)}" height="{_svg_number(window_height)}" '
        f'rx="{radius}"'
    )
    if opacity != OPAQUE:
        # Set on the fill alone, so the frame drawn by the same rect's stroke
        # keeps stating where the window ends.
        window += f' fill-opacity="{opacity}"'
    body.append(f"{window}/>")

    if not collapse_titlebar:
        if titlebar != NO_PAINT:
            body.append(
                titlebar_strip(
                    margin + WINDOW_INSET,
                    margin + WINDOW_INSET,
                    window_width,
                    paint=titlebar,
                    radius=radius,
                )
            )
        body.append(
            f'<g transform="translate({_svg_number(margin + WINDOW_INSET)}, '
            f'{_svg_number(margin + WINDOW_INSET)})">'
            f"{window_buttons(buttons, width=window_width, color=buttons_color, font_stack=font_stack)}"
            "</g>"
        )
        if title:
            body.append(
                f'<text class="{unique_id}-title" fill="{palette.foreground}" '
                f'font-family="monospace" font-size="{TITLE_SIZE}" '
                f'font-weight="bold" text-anchor="middle" '
                f'x="{_svg_number(margin + WINDOW_INSET + window_width / 2)}" '
                f'y="{_svg_number(margin + WINDOW_INSET + CELL_HEIGHT + 6)}">'
                f"{_xml_escape(title)}</text>"
            )

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
    if animated:
        # Padded so a row index means the same thing in every frame.
        padded = [
            frame_rows + [("", "")] * (row_count - len(frame_rows))
            for frame_rows in painted
        ]
        # A row drawn the same in every frame is drawn once, outside them. On a
        # recording where one line moves under twenty that do not, that is the
        # difference between one copy of those twenty and one copy per frame.
        still = [
            row
            for row in range(row_count)
            if len({frame_rows[row] for frame_rows in padded}) == 1
        ]
        moving = [row for row in range(row_count) if row not in set(still)]
        # Each frame carries its own matrix, so the attribute fallback above
        # reaches the frames a renderer shows after the first one too.
        # The frame a renderer showing no animation is left with. The last one
        # that draws something, because an animation that accumulates (a trail
        # filling up, a bar advancing, an outcome landing) says most once it has
        # finished, and a `blank` closing the cycle says nothing at all. A
        # spinner cycling in place reads the same whichever frame is picked.
        pictured = [
            index
            for index, frame_rows in enumerate(padded)
            if any(cells or glyphs for cells, glyphs in frame_rows)
        ]
        poster = pictured[-1] if pictured else len(padded) - 1
        stack = _row_group(padded[0], still, matrix)
        for index, frame_rows in enumerate(padded):
            # Stated as an attribute, not a rule: a renderer free to ignore the
            # stylesheet would otherwise stack every frame on top of the poster.
            hidden = "" if index == poster else HIDDEN_FRAME_ATTRIBUTES
            stack += (
                f'<g class="{unique_id}-f{index}"{hidden}>'
                f"{_row_group(frame_rows, moving, matrix)}</g>"
            )
    else:
        still_cells = "".join(row_cells for row_cells, _ in painted[0])
        still_glyphs = "".join(row_glyphs for _, row_glyphs in painted[0])
        stack = f"{still_cells}{matrix}{still_glyphs}</g>"
    # Behind the text and behind every frame, because an emphasized line marks a
    # row of the screen rather than anything a particular frame drew there.
    #
    # Drawn in the window's coordinates rather than the text's, so a band runs
    # from one edge to the other instead of stopping where the padding does: the
    # row is emphasized, not the column of text sitting in it. That puts it
    # outside the clip holding the text, so it takes the window's own rounded
    # clip instead, or a band on the last row would square off the corners it
    # runs into.
    if emphasize:
        # A stroke straddles the path it outlines, so half the window's frame is
        # drawn inside the window. A band running the frame's full width would
        # paint over that half and eat the border on the rows it marks. Both the
        # band and the clip rounding it therefore stop on the frame's inner
        # edge, which is where the window actually begins.
        inner = border_width / 2 if border != NO_PAINT else 0
        band_x = margin + WINDOW_INSET + inner
        band_width = window_width - 2 * inner
        defs.append(
            f'<clipPath id="{unique_id}-window">'
            f'<rect x="{_svg_number(band_x)}" '
            f'y="{_svg_number(margin + WINDOW_INSET + inner)}" '
            f'width="{_svg_number(band_width)}" '
            f'height="{_svg_number(window_height - 2 * inner)}" '
            f'rx="{_svg_number(max(radius - inner, 0))}"/></clipPath>'
        )

        def bands(lines: Iterable[int]) -> str:
            """Draw a band across the window on each of the lines given."""
            return "".join(
                f'<rect fill="'
                f'{blend(palette.background, palette.foreground, EMPHASIS_RATIO)}"'
                f' x="{_svg_number(band_x)}"'
                f' y="'
                f'{_svg_number(origin_y + (line - 1) * LINE_HEIGHT + CELL_TOP_INSET)}"'
                f' width="{_svg_number(band_width)}"'
                f' height="{_svg_number(LINE_HEIGHT + CELL_BLEED)}"'
                ' shape-rendering="crispEdges"/>'
                for line in lines
            )

        wanted = sorted(set(emphasize))
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
                body.append(
                    f'<g class="{unique_id}-f{index}"{hidden}'
                    f' clip-path="url(#{unique_id}-window)">{bands(marked)}</g>'
                )
        else:
            body.append(f'<g clip-path="url(#{unique_id}-window)">{bands(wanted)}</g>')

    # The clip and the offset are the window's, not a frame's, so they wrap the
    # whole stack rather than being repeated inside it.
    body.append(
        f'<g clip-path="url(#{unique_id}-clip)">'
        f'<g transform="translate({_svg_number(origin_x)}, {_svg_number(origin_y)})">'
        f"{stack}"
        "</g></g>"
    )
    body.append(
        watermark_svg(
            watermark,
            width=width,
            height=height,
            paint=watermark_color,
            font_stack=font_stack,
        )
    )

    # An animation states what it is, so a rebuild can leave an unchanged
    # one alone instead of rewriting bytes its own clock jitter moved.
    recording_line = ""
    if animated:
        recording_line = (
            f"<!-- @recording frames={len(pictures)} "
            f"period={_css_number(sum(durations))}s "
            f"digest={animation_digest(pictures, durations)} -->\n"
        )

    styles = "\n".join(
        f"    .{unique_id}-r{rule} {{ {css} }}" for css, rule in classes.items()
    )
    if animated:
        styles += f"\n{frame_animation_css(unique_id, durations)}"
    if cursor is not None and cursor.blink > 0:
        styles += f"\n{blink_css(unique_id, cursor.blink)}"
    return (
        # A standalone SVG carries no HTTP header to state its encoding, and a
        # reader that assumes the platform's instead renders every multi-byte
        # character as mojibake: a full block becomes `â`, and a capture of
        # colored output becomes a wall of accented letters. XML defaults to
        # UTF-8 in the absence of a declaration, but WebKit (and therefore
        # macOS Quick Look) applies its HTML fallback to the document encoding.
        # Saying so outright costs one line and settles it everywhere.
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg viewBox="0 0 {_svg_number(width)} {_svg_number(height)}" '
        'xmlns="http://www.w3.org/2000/svg">\n'
        f"<!-- @generated by {generator_tag()} -->\n"
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


def _svg_number(value: float) -> str:
    """Render a coordinate the way a renderer does, to a tenth of a pixel.

    A value rounding to a negative zero is folded into a plain one: trigonometry
    lands a hair below it for every gradient running straight down, and `-0` in
    a committed file reads as a bug rather than as the zero it is.
    """
    rounded = round(value, 1)
    return f"{rounded or 0.0:.1f}".removesuffix(".0")


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
    escaped = escape(text, quote=False).replace("\N{NO-BREAK SPACE}", "&#160;")
    return escaped.replace(" ", "&#160;") if preserve_spaces else escaped
