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

The pipeline is three steps, each replaceable on its own:

1. {func}`capture_output` runs the command through
   {func}`~click_extra.execution.run_cli`, under
   {func}`~click_extra.color.forced_color` and a pinned terminal width, and hands
   back its raw ANSI text.
2. {func}`render` turns that text into a document, in one of the
   {class}`CaptureFormat` members.
3. For SVG, {func}`harden_svg` rewrites the rendered source so it survives
   renderers that are not a web browser. That function documents what goes wrong
   without it. HTML needs no such pass: a `<pre>` keeps its own spacing.

{func}`capture` chains all three, and is what the `click-extra screenshot`
command calls.

The two formats are not interchangeable, and neither is a fallback for the
other:

- **SVG** goes where you do not own the page. GitHub and PyPI render an image
  and strip inline HTML, so a README has no other option. It is a picture: the
  text is not selectable, and not searchable.
- **HTML** goes where you do own the page. The text stays selectable,
  searchable and copy-pasteable, and reflows with the container.

```{note}
Only SVG needs the `screenshot` extra, whose Rich dependency renders it. HTML
is built on {func}`~click_extra.styling.ansi_to_html`, which ships with the
package, so it is always available.
```
"""

from __future__ import annotations

import re
import shlex
import subprocess
from enum import Enum
from html import escape, unescape
from io import StringIO

from click import unstyle

from .color import forced_color
from .execution import args_cleanup, format_cli_prompt, run_cli
from .parameters import missing_extra_message
from .styling import ansi_to_html
from .theme import BUILTIN_THEMES

try:
    from rich.console import Console
    from rich.terminal_theme import DEFAULT_TERMINAL_THEME, SVG_EXPORT_THEME
    from rich.text import Text
except ImportError:
    # Rich ships behind the `screenshot` extra: importing this module stays cheap,
    # and only the rendering entry point raises (see _rich_svg).
    Console = None  # type: ignore[assignment,misc]
    Text = None  # type: ignore[assignment,misc]
    DEFAULT_TERMINAL_THEME = None  # type: ignore[assignment]
    SVG_EXPORT_THEME = None  # type: ignore[assignment]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any, Literal, TypeAlias

    from .execution import TArg, TEnvVars, TNestedArgs
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

    Rendered by Rich, behind the `screenshot` extra.
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


CAPTURE_BACKGROUND = "#292929"
"""Background a dark capture is drawn on.

Matches the palette Rich's SVG export uses, so the two formats look like the
same terminal. Stating it is not optional: a help screen colored for a dark
terminal is unreadable on a page that defaults to white.
"""

CAPTURE_FOREGROUND = "#c5c8c6"
"""Color of the text a dark capture leaves unstyled. See {data}`CAPTURE_BACKGROUND`."""

LIGHT_CAPTURE_BACKGROUND = "#ffffff"
"""Background a light capture is drawn on.

The white Rich's own light terminal theme names, for the same reason
{data}`CAPTURE_BACKGROUND` mirrors its dark one: an SVG and an HTML capture of
the same run have to look like the same terminal.
"""

LIGHT_CAPTURE_FOREGROUND = "#000000"
"""Color of the text a light capture leaves unstyled.

See {data}`LIGHT_CAPTURE_BACKGROUND`.
"""

CAPTURE_COLORS: dict[CaptureBackground, tuple[str, str]] = {
    CaptureBackground.DARK: (CAPTURE_BACKGROUND, CAPTURE_FOREGROUND),
    CaptureBackground.LIGHT: (LIGHT_CAPTURE_BACKGROUND, LIGHT_CAPTURE_FOREGROUND),
}
"""Background and unstyled-foreground pair each chrome draws HTML with."""

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

CAPTURE_BORDERS: dict[CaptureBackground, str] = {
    CaptureBackground.DARK: "rgba(255,255,255,0.35)",
    CaptureBackground.LIGHT: "rgba(0,0,0,0.25)",
}
"""Color the window frame is drawn in, per chrome.

The dark entry is the one Rich draws on its own, a translucent white that reads
against `#292929` and against nothing else: a light capture framed with it is a
white window on a white page, the shape of the terminal only guessable from its
text. Each chrome names a frame its own background can show.
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

DEFAULT_BORDER_WIDTH = 1
"""Thickness, in pixels, of the frame drawn around the window."""

DEFAULT_RADIUS = 8
"""How round the window's corners are, in pixels.

The radius a renderer draws on its own, which is what a terminal on a desktop
looks like. Zero squares them, for a capture meant to read as a plain block.
"""

SHADOW_BLUR = 6
"""Standard deviation, in pixels, of the drop shadow's blur."""

SHADOW_OFFSET = 3
"""Downward offset, in pixels, of the drop shadow."""

DEFAULT_MARGIN = 16
"""Transparent pixels left around the window, on all four sides.

Room for the shadow to fall into, first of all: a filter draws outside the shape
it is applied to, and anything past the image's own box is cut. It also keeps
the window from touching the text of the page embedding it.
"""

DEFAULT_PADDING = 0
"""Pixels added inside the window, around the captured text.

Zero because a renderer pads on its own already (8 pixels, and 40 above for the
title bar). This is what a capture wanting more room between its frame and its
first glyph asks for.
"""

CAPTURE_THEMES = {
    CaptureBackground.DARK: SVG_EXPORT_THEME,
    CaptureBackground.LIGHT: DEFAULT_TERMINAL_THEME,
}
"""Rich terminal theme each chrome renders SVG with.

A theme carries the 16 ANSI colors alongside the chrome, which is the other half
of the job: a CLI naming `blue` leaves the shade to whoever draws it, and the
one that reads on white is not the one that reads on `#292929`. Both entries are
`None` without the `screenshot` extra, where no SVG is rendered anyway.
"""

CAPTURE_FONT_STACK = "'Fira Code', 'Cascadia Code', Menlo, Consolas, monospace"
"""Monospaced fonts an HTML capture asks for, best first.

Opens with the family Rich's SVG export names, so a reader who has it sees both
formats set identically.

Family names are single-quoted on purpose: this lands in a double-quoted
`style` attribute, which a double quote here would terminate early.
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

DEFAULT_TRUNCATION = "[...]"
"""Marker standing in for the lines {func}`trim_lines` cut away."""

PADDING = " \N{NO-BREAK SPACE}"
"""Characters a renderer pads a text run with to place it on its column.

Rich emits every space as a non-breaking one, so the padding survives an XML
round-trip; a plain space is accepted too, for sources written by other tools.
"""

_TEXT_ELEMENT_RE = re.compile(r"<text(?P<attrs>[^>]*)>(?P<content>[^<]*)</text>")
"""One run of same-styled characters in a rendered capture."""

_X_ATTR_RE = re.compile(r'\bx="(?P<value>-?[\d.]+)"')
"""The horizontal offset a text run is drawn at, in pixels."""

_TEXT_LENGTH_ATTR_RE = re.compile(r'\btextLength="(?P<value>[\d.]+)"')
"""The width a text run is asked to occupy, in pixels."""

_NON_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_-]+")
"""Characters a CSS class name cannot carry, as written into `unique_id`."""

_CHROME_RECT_RE = re.compile(r"<rect (?P<attrs>[^>]*\brx=\"8\")\s*/>")
"""The rounded rectangle a renderer draws the terminal window as.

Keyed on the corner radius, the one attribute no other rectangle in a capture
carries: the rest are the opaque cells behind styled text, drawn square.
"""

_STROKE_ATTR_RE = re.compile(r'\bstroke="[^"]*"')
"""The paint an element's outline is drawn with."""

_STROKE_WIDTH_ATTR_RE = re.compile(r'\bstroke-width="[^"]*"')
"""The thickness an element's outline is drawn at, in pixels."""

_RADIUS_ATTR_RE = re.compile(r'\brx="[^"]*"')
"""The corner radius a rectangle is rounded by, in pixels."""

_VIEWBOX_RE = re.compile(r'\bviewBox="0 0 (?P<width>[\d.]+) (?P<height>[\d.]+)"')
"""The box a capture's own coordinates are read in."""

_BOX_SIZE_ATTR_RE = re.compile(r'(?<![-\w])(?P<name>width|height)="(?P<value>[\d.]+)"')
"""Either side of a rectangle, in pixels.

The lookbehind is what keeps `stroke-width` out: a hyphenated attribute ending
in `width` is a different measurement, and growing it by a window's padding
draws a 41-pixel frame.
"""

_CLIP_ID_RE = re.compile(r'\bid="(?P<id>[^"]+)-clip-terminal"')
"""The `unique_id` a capture namespaces its identifiers with, read back."""

_TERMINAL_GROUP_RE = re.compile(
    r'<g transform="translate\((?P<x>[\d.]+), (?P<y>[\d.]+)\)"'
    r'(?P<rest> clip-path="url\(#[^"]+-clip-terminal\)")>',
)
"""The group holding the captured text, and every cell drawn behind it."""

_TITLE_TEXT_RE = re.compile(
    r'(?P<head><text class="[^"]+-title"[^>]*?)x="(?P<x>[\d.]+)"'
)
"""The caption a capture draws in its window chrome, when it carries one."""


def fit_columns(text: str) -> int:
    """Width, in characters, of the longest line in `text`.

    ANSI escapes are stripped first: they style the glyphs around them and
    occupy no cell of their own. Floored at {data}`MIN_COLUMNS`.

    :param text: captured output, ANSI escape sequences included.
    :return: the width laying every line out without folding any.
    """
    return max(
        [MIN_COLUMNS, *(len(unstyle(line)) for line in text.splitlines())],
    )


def capture_output(
    args: TArg | TNestedArgs,
    *,
    columns: TColumns = DEFAULT_COLUMNS,
    merge_stderr: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and capture its output, ANSI escape sequences and all.

    A command whose output is a pipe rather than a terminal strips its own
    colors, and wraps to whatever width it can guess. Both are pinned here:
    {func}`~click_extra.color.forced_color` sets the `FORCE_COLOR` lever both
    Click's and Rich's color systems obey and clears any opt-out the environment
    carries, while `COLUMNS` fixes the width the command wraps to.

    Only `stdout` is captured by default. That is what keeps a capture free of
    the progress lines and build chatter a wrapper like `uv` writes to `stderr`,
    with no shell redirection to remember.

    :param args: the command line, in the nested form
        {func}`~click_extra.execution.run_cli` accepts.
    :param columns: terminal width, in characters, the command wraps its output
        to. {data}`AUTO_COLUMNS` pins nothing and lets the command find its own.
    :param merge_stderr: fold `stderr` into the captured output, for a command
        printing its help there.
    :param timeout: seconds before the command is killed. `None` waits forever.
    :return: the completed process, whose `stdout` holds the captured text.
    """
    extra_env: TEnvVars = {} if columns == AUTO_COLUMNS else {"COLUMNS": str(columns)}
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


def measure_cell_width(svg: str) -> float:
    """Measure the width of one glyph cell, in pixels, from a rendered capture.

    A capture is monospaced, so every run of characters is `textLength` pixels
    wide for exactly as many characters. The widest run gives that ratio with the
    least rounding error.

    :param svg: source of a rendered capture.
    :return: the width of a single character cell, in pixels.
    :raises ValueError: when the source carries no sized text run.
    """
    widest = 0
    cell_width = 0.0
    for element in _TEXT_ELEMENT_RE.finditer(svg):
        length = _TEXT_LENGTH_ATTR_RE.search(element["attrs"])
        content = unescape(element["content"])
        if length and len(content) > widest:
            widest = len(content)
            cell_width = float(length["value"]) / widest
    if not cell_width:
        raise ValueError("No sized text run found: not a rendered terminal capture.")
    return cell_width


def harden_svg(svg: str, cell_width: float | None = None) -> str:
    """Move each text run's leading padding out of its glyphs and into its offset.

    A renderer places a run of same-styled characters with an `x` offset, then
    leans on `textLength` to hold that run to an exact width. The padding that
    separates two columns lives *inside* the run, as spaces preceding the text.
    So a column only lands where it belongs if the glyphs are the exact width the
    renderer assumed, which asks two things of whoever displays the file: honor
    `textLength`, and resolve the font the source names.

    A web browser does both. Little else does. `librsvg` (and through it
    `rsvg-convert` and ImageMagick) ignores `textLength` outright, and a file
    manager, a git client or a thumbnailer commonly falls back to a proportional
    font. Either way every glyph sitting behind padding slides out of its column,
    and neighbouring words collide.

    Stripping that padding and advancing `x` by as many cells makes each run start
    on its own column, so a renderer only has to draw glyphs, not match metrics. A
    browser is unaffected: `textLength` is rewritten to the width of what is left.

    A run carrying no glyph is left alone. Rich ends every line with one holding
    just a newline, and that is what keeps a blank line present in the source; a
    run of pure padding (which Rich never emits, though another tool might) has
    nothing to reposition anyway.

    :param svg: source of a rendered capture.
    :param cell_width: width of a character cell, in pixels. Measured from the
        source when not given (see {func}`measure_cell_width`).
    :return: the hardened source.
    """
    measured = measure_cell_width(svg) if cell_width is None else cell_width

    def rewrite(element: re.Match[str]) -> str:
        attrs = element["attrs"]
        content = unescape(element["content"])
        stripped = content.strip(PADDING)
        offset = _X_ATTR_RE.search(attrs)
        if not stripped or not offset:
            return element[0]
        indent = len(content) - len(content.lstrip(PADDING))
        column = float(offset["value"]) + indent * measured
        attrs = _X_ATTR_RE.sub(lambda _: f'x="{_svg_number(column)}"', attrs, count=1)
        attrs = _TEXT_LENGTH_ATTR_RE.sub(
            lambda _: f'textLength="{_svg_number(len(stripped) * measured)}"',
            attrs,
            count=1,
        )
        return f"<text{attrs}>{_xml_escape(stripped)}</text>"

    return _TEXT_ELEMENT_RE.sub(rewrite, svg)


def frame_svg(
    svg: str,
    *,
    border: str = NO_PAINT,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int = DEFAULT_RADIUS,
    backdrop: str = NO_PAINT,
    shadow: str = NO_PAINT,
    margin: int = 0,
    padding: int = 0,
) -> str:
    """Restate the window a rendered capture is drawn in.

    A renderer draws the terminal as a rounded rectangle, and frames it with a
    translucent white that only a dark background can show. Everything about that
    window is decided before the capture knows which chrome it is headed for, so
    it is restated here rather than asked for up front:

    - `border` repaints the frame, so a light capture stops being a white window
      on a white page;
    - `shadow` lifts the window off the page under it, drawn as an SVG filter so
      a renderer that skips filters still gets the frame;
    - `margin` grows the image around the window, which is what gives the shadow
      somewhere to fall: a filter draws outside its shape, and the image's own
      box cuts whatever lands past it;
    - `padding` grows the window around the text.

    The geometry is rewritten rather than recomputed: the coordinates a renderer
    already resolved stay as they are, moved as a whole by wrapping them in one
    translation, which is what keeps this independent of how the source was laid
    out.

    :param svg: source of a rendered capture.
    :param border: SVG paint for the window's frame. {data}`NO_PAINT` draws none.
    :param border_width: thickness of that frame, in pixels.
    :param radius: how round the window's corners are, in pixels. Zero squares
        them.
    :param backdrop: paint filling the whole image, window and margin alike.
        {data}`NO_PAINT` leaves it transparent, showing the page through.
    :param shadow: color the drop shadow floods with. {data}`NO_PAINT` draws none.
    :param margin: transparent pixels to leave on each side of the window.
    :param padding: pixels to add inside the window, around the text.
    :return: the reframed source.
    """
    window = _CHROME_RECT_RE.search(svg)
    if not window:
        return svg
    unique_id = _CLIP_ID_RE.search(svg)
    shaded = shadow != NO_PAINT and unique_id is not None

    def grow(match: re.Match[str]) -> str:
        """Widen the window by the padding it gains on each side."""
        return f'{match["name"]}="{_svg_number(float(match["value"]) + 2 * padding)}"'

    attrs = window["attrs"]
    attrs = _STROKE_ATTR_RE.sub(f'stroke="{border}"', attrs, count=1)
    attrs = _STROKE_WIDTH_ATTR_RE.sub(f'stroke-width="{border_width}"', attrs, count=1)
    attrs = _RADIUS_ATTR_RE.sub(f'rx="{radius}"', attrs, count=1)
    if padding:
        attrs = _BOX_SIZE_ATTR_RE.sub(grow, attrs, count=2)
    if shaded:
        assert unique_id
        attrs = f'{attrs} filter="url(#{unique_id["id"]}-shadow)"'
    svg = svg.replace(window[0], f"<rect {attrs}/>", 1)

    if padding:
        svg = _TERMINAL_GROUP_RE.sub(
            lambda match: (
                f'<g transform="translate({_svg_number(float(match["x"]) + padding)}, '
                f'{_svg_number(float(match["y"]) + padding)})"{match["rest"]}>'
            ),
            svg,
            count=1,
        )
        svg = _TITLE_TEXT_RE.sub(
            lambda match: (
                f'{match["head"]}x="{_svg_number(float(match["x"]) + padding)}"'
            ),
            svg,
            count=1,
        )

    grown = 2 * (margin + padding)
    box = _VIEWBOX_RE.search(svg)
    if grown and box:
        svg = svg.replace(
            box[0],
            f'viewBox="0 0 {_svg_number(float(box["width"]) + grown)} '
            f'{_svg_number(float(box["height"]) + grown)}"',
            1,
        )

    if shaded:
        assert unique_id
        svg = svg.replace(
            "</defs>",
            f'<filter id="{unique_id["id"]}-shadow" x="-50%" y="-50%" '
            'width="200%" height="200%">\n'
            f'<feDropShadow dx="0" dy="{SHADOW_OFFSET}" '
            f'stdDeviation="{SHADOW_BLUR}" flood-color="{shadow}"/>\n'
            "</filter>\n</defs>",
            1,
        )

    if margin:
        head, defs, body = svg.partition("</defs>")
        drawing, close, tail = body.rpartition("</svg>")
        svg = (
            f'{head}{defs}\n<g transform="translate({margin}, {margin})">'
            f"{drawing}</g>\n{close}{tail}"
        )

    # Painted last so it can be inserted first, under everything already drawn,
    # and sized from the box the two growths above settled.
    if backdrop != NO_PAINT and box:
        head, defs, body = svg.partition("</defs>")
        svg = (
            f'{head}{defs}\n<rect fill="{backdrop}" x="0" y="0" '
            f'width="{_svg_number(float(box["width"]) + grown)}" '
            f'height="{_svg_number(float(box["height"]) + grown)}"/>{body}'
        )

    return svg


def render_html(
    text: str,
    *,
    title: str = "",
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
    border: str = NO_PAINT,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int = DEFAULT_RADIUS,
    backdrop: str = NO_PAINT,
    shadow: str = NO_PAINT,
    margin: int = 0,
    padding: int = 0,
) -> str:
    """Render captured terminal text to HTML.

    The `<pre>` carries its own inline styling, so a fragment pasted into an
    existing page needs no stylesheet and cannot be restyled out of legibility
    by the host. Nothing else is needed either: a `<pre>` preserves the
    capture's own spacing, which is what spares HTML the offset surgery
    {func}`harden_svg` performs on SVG.

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
    :param border: color of the block's frame, see {func}`frame_svg`.
    :param border_width: thickness of that frame, in pixels.
    :param radius: how round the block's corners are, in pixels.
    :param backdrop: paint filling the page behind the block.
    :param shadow: color of the block's drop shadow, see {func}`frame_svg`.
    :param margin: pixels left around the block, on all four sides.
    :param padding: pixels added inside the block, on top of its own.
    :return: the rendered markup.
    """
    chrome, ink = CAPTURE_COLORS[background]
    frame = "" if border == NO_PAINT else f"border: {border_width}px solid {border}; "
    if shadow != NO_PAINT:
        frame += f"box-shadow: 0 {SHADOW_OFFSET}px {SHADOW_BLUR * 2}px {shadow}; "
    body = (
        f'<pre style="background: {chrome}; color: {ink}; '
        f"font-family: {CAPTURE_FONT_STACK}; line-height: 1.25; "
        f"margin: {margin}px; padding: calc(1em + {padding}px); "
        f"{frame}border-radius: {radius}px; "
        f'overflow-x: auto">{ansi_to_html(escape(text, quote=False))}</pre>'
    )
    page = "" if backdrop == NO_PAINT else f"background: {backdrop}; "
    if not full:
        # A fragment carries no page of its own, so a backdrop needs one.
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
    border: str | None = None,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int = DEFAULT_RADIUS,
    backdrop: str = NO_PAINT,
    shadow: str | None = None,
    margin: int = DEFAULT_MARGIN,
    padding: int = DEFAULT_PADDING,
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
    :return: the rendered document.
    :raises ImportError: rendering SVG without the `screenshot` extra installed.
    """
    if border is None:
        border = CAPTURE_BORDERS[background]
    if shadow is None:
        shadow = CAPTURE_SHADOWS[background]
    frame: dict[str, Any] = {
        "border": border,
        "border_width": border_width,
        "radius": radius,
        "backdrop": backdrop,
        "shadow": shadow,
        "margin": margin,
        "padding": padding,
    }
    if format is CaptureFormat.HTML:
        return render_html(text, title=title, full=full, background=background, **frame)
    if unique_id:
        unique_id = _NON_IDENTIFIER_RE.sub("-", unique_id)
    return frame_svg(
        harden_svg(
            _rich_svg(
                text,
                columns=fit_columns(text) if columns == AUTO_COLUMNS else columns,
                title=title,
                unique_id=unique_id,
                background=background,
            ),
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
    title: str = "",
    unique_id: str | None = None,
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
    border: str | None = None,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int = DEFAULT_RADIUS,
    backdrop: str = NO_PAINT,
    shadow: str | None = None,
    margin: int = DEFAULT_MARGIN,
    padding: int = DEFAULT_PADDING,
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
    :return: the rendered document, and the command's exit code.
    """
    process = capture_output(
        args,
        columns=columns,
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
            prompt_line = format_cli_prompt(displayed, theme=PROMPT_THEMES[background])
            text = f"{prompt_line}\n{text}"
    return (
        render(
            text,
            format=format,
            columns=columns,
            title=title,
            unique_id=unique_id,
            full=full,
            background=background,
            border=border,
            border_width=border_width,
            radius=radius,
            backdrop=backdrop,
            shadow=shadow,
            margin=margin,
            padding=padding,
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
    """Render a coordinate the way a renderer does, to a tenth of a pixel."""
    return f"{value:.1f}".removesuffix(".0")


def _xml_escape(text: str) -> str:
    """Escape text for an XML element, spelling padding as a character reference.

    A literal non-breaking space is valid XML but invisible in a diff, and easily
    mangled by an editor stripping trailing whitespace.
    """
    return escape(text, quote=False).replace("\N{NO-BREAK SPACE}", "&#160;")


def _rich_svg(
    text: str,
    *,
    columns: int,
    title: str,
    unique_id: str | None,
    background: CaptureBackground = CaptureBackground.DARK,
) -> str:
    """Render terminal text to SVG source with Rich.

    The only place in Click Extra that talks to Rich. It takes ANSI text and
    returns SVG source, which is the whole contract {func}`render_svg` needs: a
    replacement backend has to satisfy that signature and emit `<text>` runs
    carrying `x` and `textLength`, and nothing else in the package changes.

    The console writes to a throwaway buffer because only the recording is
    wanted, and is forced into terminal mode at full color depth: it is fed text
    that already carries ANSI escapes, so nothing here should decide the output
    is not worth coloring.
    """
    if Console is None:
        raise ImportError(
            missing_extra_message("screenshot", subject="Screenshot rendering"),
        )
    console = Console(
        record=True,
        width=columns,
        file=StringIO(),
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
    )
    console.print(Text.from_ansi(text.rstrip("\n")))
    return console.export_svg(
        title=title,
        unique_id=unique_id,
        theme=CAPTURE_THEMES[background],
    )
