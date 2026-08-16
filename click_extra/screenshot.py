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

"""Run a CLI, capture its colors, and render the result as a static document.

In Sphinx the {mod}`click:run <click_extra.sphinx.click>` directive executes each
CLI and renders its real output at build time, so a documentation page never
needs a screenshot. A README on GitHub or PyPI, a slide, or a social post cannot
run code, and those surfaces need a capture instead.

The pipeline is two steps, each replaceable on its own:

1. {func}`capture_output` runs the command through
   {func}`~click_extra.execution.run_cli`, under
   {func}`~click_extra.color.forced_color` and a pinned terminal width, and hands
   back its raw ANSI text.
2. {func}`render` turns that text into a document, in one of the
   {class}`CaptureFormat` members.

{func}`capture` chains both, and is what the `click-extra screenshot` command
calls.

Both formats read the same {func}`~click_extra.styling.split_ansi` stream, and
neither needs a dependency the package does not already carry: SVG is laid out
on a character grid by {func}`render_svg`, HTML is inline-styled markup from
{func}`~click_extra.styling.ansi_to_html`.

The two are not interchangeable, and neither is a fallback for the other:

- **SVG** goes where you do not own the page. GitHub and PyPI render an image
  and strip inline HTML, so a README has no other option. It is a picture: the
  text is not selectable, and not searchable.
- **HTML** goes where you do own the page. The text stays selectable,
  searchable and copy-pasteable, and reflows with the container.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import zlib
from enum import Enum
from html import escape
from importlib import metadata
from math import ceil, cos, hypot, pi, sin
from unicodedata import bidirectional

from click import style, unstyle
from wcwidth import wcswidth

from .color import forced_color
from .execution import args_cleanup, format_cli_prompt, run_cli
from .parameters import generator_tag
from .screenshot_presets import (
    MACOS_BUTTONS,
    PRESETS,
    TerminalPalette,
    TerminalPreset,
    WindowButtons,
)
from .styling import (
    _ANSI_NAMES,
    _hex_to_rgb,
    _palette_to_rgb,
    _rgb_to_hex,
    ansi_to_html,
    split_ansi,
)
from .theme import BUILTIN_THEMES

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from typing import Any, Literal, TypeAlias

    from .execution import TArg, TNestedArgs
    from .styling import Style
    from .theme import HelpTheme

    TColumns: TypeAlias = int | Literal["auto"]
    """Width a capture is taken and rendered at, see {data}`AUTO_COLUMNS`."""


class CaptureFormat(Enum):
    """Document formats a capture can be rendered to.

    The value doubles as the file extension {func}`format_from_path` matches on.
    """

    HTML = "html"
    """Selectable, searchable text in a self-contained `<pre>`.

    Built on {func}`~click_extra.styling.ansi_to_html`, so it needs no extra.
    """

    SVG = "svg"
    """A picture of a terminal window, for a surface that strips inline HTML.

    Laid out on a character grid by {func}`render_svg`.
    """


class CaptureBackground(Enum):
    """Terminal chrome a capture is drawn on.

    A capture freezes the colors of the run it pictures, so the chrome has to
    answer to the palette that run was colored for. Neither direction survives
    the other: a screen colored for a dark terminal is unreadable on white, and
    click-extra's own `light` and `manpage` themes wash out on the dark chrome
    a renderer defaults to.

    The value doubles as the `--background` choice the CLI offers.
    """

    DARK = "dark"
    """What a terminal, and this package's default theme, usually look like."""

    LIGHT = "light"
    """For a CLI rendered with a light-background theme."""

    def __str__(self):
        return self.name.lower()


DEFAULT_PRESET = PRESETS["plain"]
"""Terminal a capture with no `--preset` is drawn as.

`plain` mimics no desktop, which is what a capture wearing no decoration should
resolve its colors against. Naming it here is what keeps the two formats looking
like the same terminal, and keeps one catalog answering for every palette a
capture can use: without it the default colors would be a second set of literals
free to drift from the one the presets publish.
"""

CAPTURE_PALETTES: dict[CaptureBackground, TerminalPalette] = {
    CaptureBackground.DARK: DEFAULT_PRESET.dark,
    CaptureBackground.LIGHT: DEFAULT_PRESET.light,
}
"""Colors each chrome resolves a capture's ANSI codes against.

A palette carries the 16 ANSI colors alongside the background and foreground,
which is the other half of the job: a CLI naming `blue` leaves the shade to
whoever draws it, and the one that reads on white is not the one that reads on
`#292929`.
"""

CAPTURE_BACKGROUND = CAPTURE_PALETTES[CaptureBackground.DARK].background
"""Background a dark capture is drawn on.

Stating it is not optional: a help screen colored for a dark terminal is
unreadable on a page that defaults to white.
"""

CAPTURE_FOREGROUND = CAPTURE_PALETTES[CaptureBackground.DARK].foreground
"""Color of the text a dark capture leaves unstyled. See {data}`CAPTURE_BACKGROUND`."""

LIGHT_CAPTURE_BACKGROUND = CAPTURE_PALETTES[CaptureBackground.LIGHT].background
"""Background a light capture is drawn on.

See {data}`CAPTURE_BACKGROUND`: an SVG and an HTML capture of the same run have
to look like the same terminal.
"""

LIGHT_CAPTURE_FOREGROUND = CAPTURE_PALETTES[CaptureBackground.LIGHT].foreground
"""Color of the text a light capture leaves unstyled.

See {data}`LIGHT_CAPTURE_BACKGROUND`.
"""

PROMPT_THEMES: dict[CaptureBackground, HelpTheme | None] = {
    CaptureBackground.DARK: None,
    CaptureBackground.LIGHT: BUILTIN_THEMES.get("light"),
}
"""Theme the prompt line is drawn with, per chrome.

The captured output arrives already colored by the CLI that produced it, under
whatever theme *that* run was told to use. The prompt is the one line this
process draws itself, so it is the one that would otherwise land on white
chrome in the dark default's near-white `invoked_command` style, invisible.

`None` keeps whatever theme the invocation already runs under. So does a
missing entry: the mapping is read through {meth}`dict.get`, and
{data}`~click_extra.theme.BUILTIN_THEMES` is empty when a trimmed install drops
`themes.toml`.
"""

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

CAPTURE_BORDERS: dict[CaptureBackground, str] = {
    CaptureBackground.DARK: "rgba(255,255,255,0.35)",
    CaptureBackground.LIGHT: "rgba(0,0,0,0.25)",
}
"""Color the window frame is drawn in, per chrome.

The dark entry is a translucent white that reads against `#292929` and against
nothing else: a light capture framed with it is a white window on a white page,
the shape of the terminal only guessable from its text. Each chrome names a
frame its own background can show.
"""

CAPTURE_SHADOWS: dict[CaptureBackground, str] = {
    CaptureBackground.DARK: "rgba(0,0,0,0.5)",
    CaptureBackground.LIGHT: "rgba(0,0,0,0.25)",
}
"""Color the window's drop shadow floods with, per chrome.

Where the frame states the window's edge, the shadow lifts it off whatever page
embeds the capture, which is the other half of not dissolving into it. A reader
whose renderer drops the filter still gets the frame.
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

DEFAULT_MARGIN = 48
"""Transparent pixels left around the window, on all four sides.

Room for the shadow to fall into, first of all: a filter draws outside the shape
it is applied to, and anything past the image's own box is cut. It is also what
a backdrop has to show through, and what keeps the window from touching the text
of the page embedding it.
"""

DEFAULT_PADDING = 8
"""Pixels added inside the window, around the captured text.

On top of the few a renderer adds on its own (8, and 40 above for the title
bar), which leaves a help screen's first column tight against the frame.
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
        release = metadata.version("click-extra")
    except metadata.PackageNotFoundError:
        return ""
    return release.split(".dev")[0].split("+")[0]


DEFAULT_WATERMARK = f"generated with click-extra {_package_release()}".rstrip()
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

CAPTURE_TERMINAL_HINTS: dict[CaptureBackground, dict[str, str]] = {
    CaptureBackground.DARK: {"CLITHEME": "dark", "COLORFGBG": "15;0"},
    CaptureBackground.LIGHT: {"CLITHEME": "light", "COLORFGBG": "0;15"},
}
"""Environment a terminal of each chrome would carry, handed to the command.

A capture is a terminal simulated for a command that cannot see one: its width
is pinned and its colors forced, because a pipe would have it wrap to a guess
and print none. Its background is the third thing a terminal states and a pipe
does not, through the two variables
{func}`~click_extra.color.resolve_background` reads: the
[cli-theme](https://wiki.tau.garden/cli-theme) `CLITHEME`, and `COLORFGBG`
carrying `foreground;background` palette indices.

So a CLI asking for [`--theme auto`](theme.md#automatic-background-detection)
renders for the chrome its picture is drawn on, instead of falling back to dark
inside a light window. A CLI that never asks is unaffected: the variables only
answer a question it does not put.
"""

CAPTURE_FONT_STACK = DEFAULT_PRESET.font_stack
"""Monospaced fonts a capture asks for, best first.

Nothing is embedded and nothing is fetched, so both formats set the text in the
first family the reader already has, and a capture renders the same offline, on
a page forbidding third-party requests, and in a viewer that speaks no CSS
`@font-face`.

Family names are single-quoted on purpose: this lands in a double-quoted
`style` attribute, which a double quote here would terminate early.
"""

CELL_HEIGHT = 20.0
"""Height of one glyph cell, in pixels, which is also the text's font size."""

FONT_ASPECT_RATIO = 0.61
"""Width-to-height ratio of the font a capture is laid out for.

Fira Code's, the first family {data}`CAPTURE_FONT_STACK` asks for. Every
monospaced fallback behind it is close enough that the grid holds, and
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

DIM_RATIO = 0.4
"""How far a `dim` run's ink is mixed toward the background, see {func}`blend`."""

RTL_BIDI_CLASSES = frozenset({"R", "AL", "AN"})
"""Unicode bidirectional classes written right to left.

Right-to-left letters, Arabic letters and Arabic-Indic numbers, as
{func}`unicodedata.bidirectional` names them. See {func}`is_bidirectional`.
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

AUTO_COLUMNS: Literal["auto"] = "auto"
"""Width asking for the one the captured text itself decides.

Neither end of the pipeline is pinned: the command wraps to whatever terminal it
finds (Click's own 80 when that is a pipe, or a documentation build), and the
image is laid out at the longest line that came back, see {func}`fit_columns`.
Nothing the command printed folds inside the picture then, which is what a line
the command does not wrap on its own needs: a prompt, a wide table, a
machine-readable dump.

The cost is that the picture stops being a fixed-width terminal, so a capture
meant to sit beside others at the same width should name that width instead.
"""

DEFAULT_COLUMNS = 80
"""Terminal width a capture is taken at, in characters.

Both ends of the pipeline have to agree on it: the command wraps its output to
this width, and the renderer lays the image out at the same one. Let them
disagree and the rendered lines overrun the image. 80 is the width Click itself
falls back to off a terminal, which makes it the value a capture lands on by
accident anyway.
"""

MIN_COLUMNS = 20
"""Narrowest width a capture is rendered at.

A floor on {data}`AUTO_COLUMNS` as much as on an explicit width: a command
printing nothing but blank lines would otherwise ask for an image no glyph fits
in.
"""

LINE_NUMBER_SEPARATOR = " │ "
"""Rule drawn between a line's number and the line itself.

A vertical bar rather than a bare space, so the gutter reads as a column of its
own even where the output is itself indented.
"""

DEFAULT_TRUNCATION = "[...]"
"""Marker standing in for the lines {func}`trim_lines` cut away."""

PADDING = " \N{NO-BREAK SPACE}"
"""Characters separating one column of a capture from the next.

{func}`render_svg` emits every space as a non-breaking one, so the padding
survives an XML round-trip and no renderer collapses a run of them.
"""

_NON_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_-]+")
"""Characters a CSS class name cannot carry, as written into `unique_id`."""

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


def number_lines(text: str, start: int = 1) -> str:
    """Prefix each line of `text` with its number, in a dim gutter.

    The numbers are drawn into the terminal text rather than into a column of
    the image, which is the same trade Pygments makes with its inline line
    numbers: every renderer places them for free, and every reader copying the
    capture copies them too.

    Right-aligned on the widest number, so the gutter is one column whatever the
    output's length, and separated by {data}`LINE_NUMBER_SEPARATOR`.

    :param text: captured output, ANSI escape sequences included.
    :param start: number given to the first line.
    :return: the numbered text.
    """
    lines = text.splitlines()
    if not lines:
        return text
    width = len(str(start + len(lines) - 1))
    gutter = (
        f"{style(str(number).rjust(width), dim=True)}"
        f"{style(LINE_NUMBER_SEPARATOR, dim=True)}"
        for number in range(start, start + len(lines))
    )
    return "\n".join(f"{prefix}{line}" for prefix, line in zip(gutter, lines))


def preset_palette(
    preset: TerminalPreset,
    background: CaptureBackground,
) -> TerminalPalette:
    """The colors a preset shows on the given chrome."""
    return preset.dark if background is CaptureBackground.DARK else preset.light


def is_bidirectional(text: str) -> bool:
    """Whether `text` carries a character written right to left.

    Arabic, Hebrew and their neighbours are reordered by whoever draws them, and
    the cursive ones are shaped: a letter's form depends on what it joins. A
    terminal grid describes neither, which is why {func}`render_svg` stops
    pinning such a run to an exact width.

    :param text: the text to inspect.
    :return: `True` when at least one character is right-to-left.
    """
    return any(bidirectional(char) in RTL_BIDI_CLASSES for char in text)


def cell_width(text: str) -> int:
    """Columns `text` occupies on a terminal's character grid.

    Not its length: a CJK ideograph is drawn two cells wide, a combining mark
    none at all. {func}`wcwidth.wcswidth` answers for both, and returns `-1` for
    a string carrying a control character, where the count of characters is the
    closest thing to an answer left.

    :param text: the text to measure.
    :return: the number of cells it occupies.
    """
    width = wcswidth(text)
    return width if width >= 0 else len(text)


def fit_columns(text: str) -> int:
    """Width, in characters, of the longest line in `text`.

    ANSI escapes are stripped first: they style the glyphs around them and
    occupy no cell of their own. Measured in terminal cells, so a line of CJK
    asks for the two columns per glyph it is drawn with. Floored at
    {data}`MIN_COLUMNS`.

    :param text: captured output, ANSI escape sequences included.
    :return: the width laying every line out without folding any.
    """
    return max(
        [MIN_COLUMNS, *(cell_width(unstyle(line)) for line in text.splitlines())],
    )


def capture_output(
    args: TArg | TNestedArgs,
    *,
    columns: TColumns = DEFAULT_COLUMNS,
    background: CaptureBackground = CaptureBackground.DARK,
    merge_stderr: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and capture its output, ANSI escape sequences and all.

    A command whose output is a pipe rather than a terminal strips its own
    colors, and wraps to whatever width it can guess. Both are pinned here:
    {func}`~click_extra.color.forced_color` sets the `FORCE_COLOR` lever every
    mainstream color system obeys and clears any opt-out the environment
    carries, while `COLUMNS` fixes the width the command wraps to.

    Only `stdout` is captured by default. That is what keeps a capture free of
    the progress lines and build chatter a wrapper like `uv` writes to `stderr`,
    with no shell redirection to remember.

    :param args: the command line, in the nested form
        {func}`~click_extra.execution.run_cli` accepts.
    :param columns: terminal width, in characters, the command wraps its output
        to. {data}`AUTO_COLUMNS` pins nothing and lets the command find its own.
    :param background: chrome the capture is headed for, stated to the command
        the way a terminal would, see {data}`CAPTURE_TERMINAL_HINTS`.
    :param merge_stderr: fold `stderr` into the captured output, for a command
        printing its help there.
    :param timeout: seconds before the command is killed. `None` waits forever.
    :return: the completed process, whose `stdout` holds the captured text.
    """
    extra_env: dict[str, str | None] = dict(CAPTURE_TERMINAL_HINTS[background])
    if columns != AUTO_COLUMNS:
        extra_env["COLUMNS"] = str(columns)
    with forced_color():
        return run_cli(
            args,
            extra_env=extra_env,
            timeout=timeout,
            merge_streams=merge_stderr,
        )


def trim_lines(
    text: str,
    *,
    head: int | None = None,
    tail: int | None = None,
    truncation: str = DEFAULT_TRUNCATION,
) -> str:
    """Keep only the first `head` and last `tail` lines of `text`.

    Whatever is dropped is replaced by a single `truncation` line, so the image
    admits that it was cut rather than pretending to be the whole output. Text
    short enough to survive both bounds comes back untouched, with no marker.

    :param text: the captured output.
    :param head: number of leading lines to keep, or `None` for no head bound.
    :param tail: number of trailing lines to keep, or `None` for no tail bound.
    :param truncation: line standing in for what was cut.
    :return: the trimmed text.
    """
    if head is None and tail is None:
        return text
    lines = text.splitlines()
    kept = (head or 0) + (tail or 0)
    if kept >= len(lines):
        return text
    return "\n".join([
        *(lines[:head] if head else []),
        truncation,
        *(lines[-tail:] if tail else []),
    ])


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
            return palette.ansi[_ANSI_NAMES.index(color.removeprefix("bright_")) + 8]
        if color in _ANSI_NAMES:
            return palette.ansi[_ANSI_NAMES.index(color)]
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


def grid(text: str, columns: int) -> list[list[tuple[Style, str, int]]]:
    """Lay ANSI text out on a terminal's character grid.

    The one place a capture stops being a stream and becomes a picture. Each
    styled run of {func}`~click_extra.styling.split_ansi` is split at newlines
    into rows, then placed on the column it starts at, measured in cells rather
    than characters so a wide glyph takes the two it is drawn with.

    A line reaching past `columns` soft-wraps onto the next row, the way it would
    on a terminal that narrow, rather than being cropped: a command is free to
    print a line it never wraps itself (a long URL, a wide table, a
    machine-readable dump), and a picture that silently swallowed the overflow
    would be lying about what ran. A glyph straddling the edge moves down whole.

    Returning the column with each run is what lets {func}`render_svg` place a
    run without measuring anything back out of its own output.

    :param text: captured output, ANSI escape sequences included.
    :param columns: width of the grid, in cells.
    :return: one list of `(style, text, column)` runs per row.
    """
    rows: list[list[tuple[Style, str, int]]] = [[]]
    column = 0
    for run_style, run in split_ansi(text):
        for index, line in enumerate(run.split("\n")):
            if index:
                rows.append([])
                column = 0
            if not line:
                continue
            kept: list[str] = []
            start = column
            for char in line:
                size = cell_width(char)
                # `and column` keeps a glyph wider than the whole grid on the
                # row it started, instead of wrapping forever onto empty ones.
                if column + size > columns and column:
                    if kept:
                        rows[-1].append((run_style, "".join(kept), start))
                        kept = []
                    rows.append([])
                    column = start = 0
                kept.append(char)
                column += size
            if kept:
                rows[-1].append((run_style, "".join(kept), start))
    return rows


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


def watermark_svg(
    text: str,
    *,
    width: float,
    height: float,
    paint: str,
    font_stack: str = CAPTURE_FONT_STACK,
) -> str:
    """Draw the credit line in the image's bottom-right corner.

    Placed in the margin rather than over the terminal, which is what keeps it
    from covering a line of output: a capture is a picture of text, and a mark
    crossing that text costs the reader the thing being shown.

    Carries a `watermark` class, so a reader taking a capture apart can tell the
    one run the renderer never captured from the ones it did.

    :param text: the credit to draw. Empty draws nothing.
    :param width: width of the whole image, in pixels.
    :param height: its height, in pixels.
    :param paint: color to draw the text in, alpha included.
    :param font_stack: fonts it is set in, the capture's own.
    :return: the SVG markup, empty when there is nothing to draw.
    """
    if not text:
        return ""
    return (
        f'<text class="watermark" x="{_svg_number(width - WATERMARK_INSET)}" '
        f'y="{_svg_number(height - WATERMARK_INSET)}" text-anchor="end" '
        f'fill="{paint}" font-family="{font_stack}" '
        f'font-size="{WATERMARK_SIZE}">{_xml_escape(text)}</text>'
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
    if style.underline:
        rules.append("text-decoration: underline")
    if style.strikethrough:
        rules.append("text-decoration: line-through")
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


def render_svg(
    text: str,
    *,
    columns: int,
    title: str = "",
    unique_id: str | None = None,
    palette: TerminalPalette = CAPTURE_PALETTES[CaptureBackground.DARK],
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
    this arithmetic rather than typesetting: {func}`grid` says which cell each
    run of same-styled characters starts on, and every coordinate below is that
    column times {data}`CELL_WIDTH`.

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

    :param text: captured output, ANSI escape sequences included.
    :param columns: width of the terminal, in characters.
    :param title: caption drawn in the window's title bar. Empty draws none.
    :param unique_id: prefix namespacing this document's CSS classes and element
        IDs, see {func}`render`. Derived from the content when not given.
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
    """
    rows = grid(text.rstrip("\n"), columns)
    if unique_id is None:
        unique_id = f"terminal-{zlib.adler32((text + title).encode()):d}"
    unique_id = _NON_IDENTIFIER_RE.sub("-", unique_id)
    if buttons_color is None:
        buttons_color = palette.foreground

    classes: dict[str, int] = {}
    cells: list[str] = []
    glyphs: list[str] = []
    for row, runs in enumerate(rows):
        baseline = row * LINE_HEIGHT + CELL_HEIGHT
        for run_style, run, column in runs:
            # The paint spans the whole run, padding included: a styled column
            # keeps its background across the spaces trailing it.
            paint = run_paint(run_style, palette)
            if paint is not None:
                cells.append(
                    f'<rect fill="{paint}" x="{_svg_number(column * CELL_WIDTH)}" '
                    f'y="{_svg_number(row * LINE_HEIGHT + CELL_TOP_INSET)}" '
                    f'width="{_svg_number(cell_width(run) * CELL_WIDTH)}" '
                    f'height="{_svg_number(LINE_HEIGHT + CELL_BLEED)}" '
                    'shape-rendering="crispEdges"/>'
                )
            # The glyphs do not, see this function's note.
            if not run.strip(PADDING):
                continue
            rule = classes.setdefault(style_rules(run_style, palette), len(classes) + 1)
            for drawn, at in column_segments(run, column):
                # A right-to-left segment is reordered and shaped by whoever
                # draws it, and `textLength` pays for any difference in letter
                # spacing, which pulls a cursive word apart at its joins. Such a
                # segment keeps its own width. Only that width floats: every one
                # is placed by its own `x`, so the columns around it hold.
                length = (
                    ""
                    if is_bidirectional(drawn)
                    else f' textLength="{_svg_number(cell_width(drawn) * CELL_WIDTH)}"'
                )
                glyphs.append(
                    f'<text class="{unique_id}-r{rule}" '
                    f'x="{_svg_number(at * CELL_WIDTH)}" '
                    f'y="{_svg_number(baseline)}"{length}>'
                    f"{_xml_escape(drawn, preserve_spaces=True)}</text>"
                )

    # A collapsed title bar is negative padding applied to the top alone, which
    # is why both travel together through every measurement below.
    dropped = TITLEBAR_HEIGHT if collapse_titlebar else 0
    text_width = columns * CELL_WIDTH
    text_height = len(rows) * LINE_HEIGHT
    window_width = ceil(text_width + 2 * (WINDOW_PADDING + padding))
    window_height = (
        text_height + TITLEBAR_HEIGHT + WINDOW_PADDING - dropped + 2 * padding
    )
    width = window_width + 2 * (margin + WINDOW_INSET)
    height = window_height + 2 * (margin + WINDOW_INSET)
    origin_x = margin + WINDOW_INSET + WINDOW_PADDING + padding
    origin_y = margin + WINDOW_INSET + TITLEBAR_HEIGHT + padding - dropped

    defs = [
        (
            f'<clipPath id="{unique_id}-clip">'
            f'<rect x="0" y="0" width="{_svg_number(text_width)}" '
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
            '<feComposite in2="cast" operator="in"/>'
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
                f'font-family="{font_stack}" font-size="{TITLE_SIZE}" '
                f'font-weight="bold" text-anchor="middle" '
                f'x="{_svg_number(margin + WINDOW_INSET + window_width / 2)}" '
                f'y="{_svg_number(margin + WINDOW_INSET + CELL_HEIGHT + 6)}">'
                f"{_xml_escape(title)}</text>"
            )

    body.append(
        f'<g transform="translate({_svg_number(origin_x)}, {_svg_number(origin_y)})" '
        f'clip-path="url(#{unique_id}-clip)">'
        f"{''.join(cells)}"
        # The stylesheet says all of this too, and says it once. It is repeated
        # here as presentation attributes because a renderer is free to ignore a
        # `<style>` block, and several do: the text then falls back to a
        # proportional face at a default size in default black, which is a
        # terminal capture with neither its grid nor its colors. An attribute
        # loses to a stylesheet wherever one is read, so this changes nothing
        # for a renderer that reads both.
        f'<g class="{unique_id}-matrix" font-family="{font_stack}" '
        f'font-size="{_svg_number(CELL_HEIGHT)}" fill="{palette.foreground}">'
        f"{''.join(glyphs)}</g>"
        "</g>"
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

    styles = "\n".join(
        f"    .{unique_id}-r{rule} {{ {css} }}" for css, rule in classes.items()
    )
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


def render_html(
    text: str,
    *,
    title: str = "",
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
    preset: TerminalPreset | None = None,
    border: str = NO_PAINT,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int = DEFAULT_RADIUS,
    backdrop: str = NO_PAINT,
    shadow: str = NO_PAINT,
    margin: int = 0,
    padding: int = 0,
    buttons: WindowButtons | None = None,
    buttons_color: str = CAPTURE_FOREGROUND,
    font_stack: str = CAPTURE_FONT_STACK,
    titlebar: str = NO_PAINT,
    collapse_titlebar: bool = False,
    opacity: float = OPAQUE,
    watermark: str = "",
    watermark_color: str = WATERMARK_INK,
) -> str:
    """Render captured terminal text to HTML.

    The `<pre>` carries its own inline styling, so a fragment pasted into an
    existing page needs no stylesheet and cannot be restyled out of legibility
    by the host. Nothing else is needed either: a `<pre>` preserves the
    capture's own spacing, which is what spares HTML the column arithmetic
    {func}`render_svg` performs for a picture.

    ```{caution}
    The text is escaped before its ANSI is translated, the order
    {mod}`click_extra.table` uses for its `html` format. Skip it and any `<` a
    CLI prints opens a tag: click-extra's own `--export-config` help says it
    writes `to <stdout>`.
    ```

    ```{note}
    An OSC 8 hyperlink loses its URL and keeps its visible text: the escape is
    dropped rather than turned into an `<a>`.
    ```

    :param text: captured output, ANSI escape sequences included.
    :param title: `<title>` of the document. Ignored for a fragment.
    :param full: wrap the `<pre>` in a standalone document. `False` returns the
        `<pre>` alone, to paste into a page that has its own.
    :param background: chrome to draw on, see {class}`CaptureBackground`.
    :param border: color of the block's frame, see {func}`render_svg`.
    :param border_width: thickness of that frame, in pixels.
    :param radius: how round the block's corners are, in pixels.
    :param backdrop: paint filling the page behind the block.
    :param shadow: color of the block's drop shadow, see {func}`render_svg`.
    :param margin: pixels left around the block, on all four sides.
    :param padding: pixels added inside the block, on top of its own.
    :param buttons: ignored. HTML reflows with the page embedding it, so it
        carries the text and its colors, not a window drawn around them.
    :param buttons_color: ignored, see `buttons`.
    :param titlebar: ignored, see `buttons`.
    :param collapse_titlebar: ignored, see `buttons`.
    :param opacity: how solid the block's background is, from {data}`OPAQUE`
        down to `0.0`, where the page shows straight through the text.
    :param watermark: credit line drawn under the block, against its right edge,
        where an SVG draws it in the margin. Empty draws none.
    :param watermark_color: color that line is drawn in, alpha included.
    :return: the rendered markup.
    """
    palette = (
        CAPTURE_PALETTES[background]
        if preset is None
        else preset_palette(preset, background)
    )
    chrome, ink = palette.background, palette.foreground
    if opacity != OPAQUE:
        # CSS carries no background-opacity, and the `opacity` property would
        # take the text down with it, so the color itself is thinned instead.
        chrome = f"color-mix(in srgb, {chrome} {opacity:.0%}, transparent)"
    frame = "" if border == NO_PAINT else f"border: {border_width}px solid {border}; "
    if shadow != NO_PAINT:
        frame += f"box-shadow: 0 {SHADOW_OFFSET}px {SHADOW_BLUR * 2}px {shadow}; "
    # A credit line takes the block's bottom margin over, so the two read as one
    # figure: the same place an SVG draws its mark, which is the margin rather
    # than the page below it.
    block_margin = f"{margin}px"
    if watermark:
        block_margin = (
            f"{margin}px {margin}px {max(margin // 4, WATERMARK_INSET // 2)}px"
        )
    body = (
        f'<pre style="background: {chrome}; color: {ink}; '
        f"font-family: {font_stack}; line-height: 1.25; "
        f"margin: {block_margin}; padding: calc(1em + {padding}px); "
        f"{frame}border-radius: {radius}px; "
        f'overflow-x: auto">{ansi_to_html(escape(text, quote=False))}</pre>'
    )
    if watermark:
        body += (
            f'\n<div style="margin: 0 {margin}px {margin}px; text-align: right; '
            f"color: {watermark_color}; font-family: {font_stack}; "
            f'font-size: {WATERMARK_SIZE}px">{escape(watermark, quote=False)}</div>'
        )
    page = "" if backdrop == NO_PAINT else f"background: {backdrop}; "
    if not full:
        # A fragment carries no page of its own, so a backdrop needs one. A
        # credit line needs nothing: a fragment is a run of markup, and the mark
        # is the second element of it.
        return f'<div style="{page}">{body}</div>' if page else body
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{escape(title, quote=False)}</title>\n"
        "</head>\n"
        f'<body style="{page}margin: 0">\n{body}\n</body>\n'
        "</html>\n"
    )


def render(
    text: str,
    *,
    format: CaptureFormat = CaptureFormat.SVG,
    columns: TColumns = DEFAULT_COLUMNS,
    title: str = "",
    unique_id: str | None = None,
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
    preset: TerminalPreset | None = None,
    border: str | None = None,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int | None = None,
    backdrop: str = NO_PAINT,
    shadow: str | None = None,
    margin: int = DEFAULT_MARGIN,
    padding: int = DEFAULT_PADDING,
    opacity: float = OPAQUE,
    watermark: str = DEFAULT_WATERMARK,
    watermark_color: str | None = None,
) -> str:
    """Render captured terminal text to the document `format` names.

    :param text: captured output, ANSI escape sequences included.
    :param format: which document to produce.
    :param columns: terminal width, in characters, an SVG is laid out at, or
        {data}`AUTO_COLUMNS` for the width its own longest line asks for. HTML
        reflows, so it ignores this.
    :param title: caption drawn in an SVG's window chrome, or an HTML document's
        `<title>`.
    :param unique_id: SVG only. Prefix namespacing the source's CSS classes and
        element IDs. Pinning it to something stable (the output file's name, say)
        keeps a regenerated capture diffing line by line, instead of renaming
        every class as soon as a single character of output changes. Characters
        a CSS class name cannot carry are folded to a dash.
    :param full: HTML only. See {func}`render_html`.
    :param background: chrome to draw on, see {class}`CaptureBackground`.
    :param border: color of the window's frame. `None` takes the one the chrome
        can show, see {data}`CAPTURE_BORDERS`; {data}`NO_PAINT` draws none.
    :param border_width: thickness of that frame, in pixels.
    :param radius: how round the window's corners are, in pixels. Zero squares
        them.
    :param backdrop: paint filling the image behind the window, margin included.
        {data}`NO_PAINT` leaves it transparent.
    :param shadow: color of the window's drop shadow. `None` takes the chrome's
        own, see {data}`CAPTURE_SHADOWS`; {data}`NO_PAINT` draws none.
    :param margin: transparent pixels left around the window, on all four sides.
    :param padding: pixels added inside the window, around the text.
    :param opacity: how solid the window's body is, from {data}`OPAQUE` down to
        `0.0`. Below it, whatever the capture is laid over shows through.
    :param watermark: credit line drawn in the image's bottom-right corner, see
        {data}`DEFAULT_WATERMARK`. An empty string draws none.
    :param watermark_color: color that line is drawn in. `None` takes
        {data}`WATERMARK_INK`, which reads on a page of either color.
    :return: the rendered document.
    :raises ImportError: rendering SVG without the `screenshot` extra installed.
    """
    if border is None:
        border = CAPTURE_BORDERS[background]
    if shadow is None:
        shadow = CAPTURE_SHADOWS[background]
    if watermark_color is None:
        watermark_color = WATERMARK_INK
    if radius is None:
        radius = DEFAULT_RADIUS if preset is None else preset.radius
    frame: dict[str, Any] = {
        "border": border,
        "border_width": border_width,
        "radius": radius,
        "backdrop": backdrop,
        "shadow": shadow,
        "margin": margin,
        "padding": padding,
        "opacity": opacity,
        "watermark": watermark,
        "watermark_color": watermark_color,
    }
    if preset is not None:
        palette = preset_palette(preset, background)
        frame["buttons"] = preset.buttons
        frame["buttons_color"] = palette.foreground
        frame["font_stack"] = preset.font_stack
        frame["titlebar"] = palette.titlebar
        # A window wearing neither decoration nor caption has nothing to seat in
        # its title bar, so it closes over the first line of output instead.
        frame["collapse_titlebar"] = not any(
            (preset.buttons.circles, preset.buttons.glyphs, title),
        )
    if format is CaptureFormat.HTML:
        return render_html(
            text,
            title=title,
            full=full,
            background=background,
            preset=preset,
            **frame,
        )
    return render_svg(
        text,
        columns=fit_columns(text) if columns == AUTO_COLUMNS else columns,
        title=title,
        unique_id=unique_id,
        palette=(
            CAPTURE_PALETTES[background]
            if preset is None
            else preset_palette(preset, background)
        ),
        **frame,
    )


def capture(
    args: TArg | TNestedArgs,
    *,
    format: CaptureFormat = CaptureFormat.SVG,
    columns: TColumns = DEFAULT_COLUMNS,
    prompt: str | None = None,
    head: int | None = None,
    tail: int | None = None,
    truncation: str = DEFAULT_TRUNCATION,
    merge_stderr: bool = False,
    timeout: float | None = None,
    line_numbers: bool = False,
    title: str = "",
    unique_id: str | None = None,
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
    preset: TerminalPreset | None = None,
    border: str | None = None,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int | None = None,
    backdrop: str = NO_PAINT,
    shadow: str | None = None,
    margin: int = DEFAULT_MARGIN,
    padding: int = DEFAULT_PADDING,
    opacity: float = OPAQUE,
    watermark: str = DEFAULT_WATERMARK,
    watermark_color: str | None = None,
) -> tuple[str, int]:
    """Run a command and render its output as a document.

    Chains {func}`capture_output`, {func}`trim_lines` and {func}`render`. The
    invocation is drawn above the output as a shell prompt, styled by the active
    theme through {func}`~click_extra.execution.format_cli_prompt`, so the
    capture shows what to type to reproduce it.

    :param args: the command line to run.
    :param format: which document to produce.
    :param columns: terminal width, in characters, or {data}`AUTO_COLUMNS` to
        pin none and lay the image out at what the command printed.
    :param prompt: command line to *display*, when it differs from the one run.
        `uv run --frozen -- my-cli` reproduces a capture from a checkout, but
        `my-cli` is what a reader types. An empty string draws no prompt at all.
    :param head: number of leading output lines to keep.
    :param tail: number of trailing output lines to keep.
    :param truncation: line standing in for the lines cut by `head` or `tail`.
    :param merge_stderr: fold `stderr` into the captured output.
    :param timeout: seconds before the command is killed.
    :param line_numbers: draw each line's number in a gutter, see
        {func}`number_lines`. The prompt counts as the first of them, being the
        invocation everything under it came from.
    :param title: see {func}`render`.
    :param unique_id: see {func}`render`.
    :param full: see {func}`render`.
    :param background: see {func}`render`.
    :param border: see {func}`render`.
    :param border_width: see {func}`render`.
    :param radius: see {func}`render`.
    :param backdrop: see {func}`render`.
    :param shadow: see {func}`render`.
    :param margin: see {func}`render`.
    :param padding: see {func}`render`.
    :param opacity: see {func}`render`.
    :param watermark: see {func}`render`.
    :param watermark_color: see {func}`render`.
    :return: the rendered document, and the command's exit code.
    """
    process = capture_output(
        args,
        columns=columns,
        background=background,
        merge_stderr=merge_stderr,
        timeout=timeout,
    )
    text = trim_lines(
        process.stdout,
        head=head,
        tail=tail,
        truncation=truncation,
    )
    displayed = args_cleanup(args) if prompt is None else tuple(shlex.split(prompt))
    if displayed:
        with forced_color():
            prompt_line = format_cli_prompt(
                displayed,
                theme=PROMPT_THEMES[background],
                prompt=None if preset is None else preset.prompt,
            )
            text = f"{prompt_line}\n{text}"
    # Numbered after the prompt joins it, so line 1 is the invocation that
    # produced everything under it.
    if line_numbers:
        text = number_lines(text)
    return (
        render(
            text,
            format=format,
            columns=columns,
            title=title,
            unique_id=unique_id,
            full=full,
            background=background,
            preset=preset,
            border=border,
            border_width=border_width,
            radius=radius,
            backdrop=backdrop,
            shadow=shadow,
            margin=margin,
            padding=padding,
            opacity=opacity,
            watermark=watermark,
            watermark_color=watermark_color,
        ),
        process.returncode,
    )


def format_from_path(path: Path) -> CaptureFormat:
    """Pick the capture format a file name asks for.

    :param path: where the capture is to be written.
    :return: the {class}`CaptureFormat` its extension names.
    :raises ValueError: when the extension names no format.
    """
    suffix = path.suffix.lower().lstrip(".")
    # `.htm` is the same document under the older extension.
    if suffix == "htm":
        suffix = CaptureFormat.HTML.value
    try:
        return CaptureFormat(suffix)
    except ValueError:
        known = ", ".join(sorted(f".{member.value}" for member in CaptureFormat))
        raise ValueError(
            f"Cannot tell the capture format of {path.name!r}: name it {known}."
        ) from None


def _svg_number(value: float) -> str:
    """Render a coordinate the way a renderer does, to a tenth of a pixel.

    A value rounding to a negative zero is folded into a plain one: trigonometry
    lands a hair below it for every gradient running straight down, and `-0` in
    a committed file reads as a bug rather than as the zero it is.
    """
    rounded = round(value, 1)
    return f"{rounded if rounded else 0.0:.1f}".removesuffix(".0")


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
