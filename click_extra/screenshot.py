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
on a character grid by {func}`~click_extra.screenshot_svg.render_svg`, HTML is
inline-styled markup from {func}`~click_extra.styling.ansi_to_html`.

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
from dataclasses import asdict, dataclass, fields, replace
from enum import Enum

from click import style, unstyle

from ._deprecated import warn_deprecated_usage
from .color import forced_color
from .execution import args_cleanup, format_cli_prompt, run_cli

# These were this module's own until the terminal-grid primitives moved to
# click_extra.layout, and the body still calls every one. They are imports, not a
# compatibility surface: a name this module stops using goes with it, and importers
# follow it to its new home.
from .layout import RULE_COLOR, cell_width, center_in_rule, fit_columns, number_lines
from .screenshot_html import render_html
from .screenshot_presets import (
    CaptureBackground,
    Cursor,
    TerminalPalette,
    TerminalPreset,
    resolve_palette,
)
from .screenshot_svg import (
    DEFAULT_BORDER_WIDTH,
    DEFAULT_RADIUS,
    DEFAULT_WATERMARK,
    EMPHASIS_RATIO,
    NO_PAINT,
    OPAQUE,
    WATERMARK_INK,
    blend,
    cursor_cell,
    render_svg,
)
from .styling import _hex_to_rgb
from .theme import BUILTIN_THEMES

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path
    from typing import Any, Literal, TypeAlias, TypedDict

    from typing_extensions import Unpack

    from .execution import TArg, TNestedArgs
    from .screenshot_svg import THold
    from .theme import HelpTheme

    TColumns: TypeAlias = int | Literal["auto"]
    """Width a capture is taken and rendered at, see {data}`AUTO_COLUMNS`."""

    class ChromeArguments(TypedDict, total=False):
        """The window arguments taken one by one before {class}`Chrome`."""

        border: str | None
        border_width: int
        radius: int | None
        backdrop: str
        shadow: str | None
        margin: int
        padding: int
        opacity: float
        watermark: str
        watermark_color: str | None


class CaptureFormat(Enum):
    """Document formats a capture can be rendered to.

    The value doubles as the file extension {func}`format_from_path` matches on.
    """

    ANSI = "ansi"
    """The escape sequences themselves, for a terminal to paint.

    The one target that needs no rendering, a terminal reading the same stream
    the capture is carried in. So it is the whole picture minus the window:
    there is no frame, no chrome and no margin to draw, and every option
    describing one is ignored, see {func}`render`.
    """

    HTML = "html"
    """Selectable, searchable text in a self-contained `<pre>`.

    Built on {func}`~click_extra.styling.ansi_to_html`, so it needs no extra.
    """

    SVG = "svg"
    """A picture of a terminal window, for a surface that strips inline HTML.

    Laid out on a character grid by {func}`~click_extra.screenshot_svg.render_svg`.
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

STDOUT_PATH = "-"
"""Destination naming the terminal rather than a file.

The convention every command-line tool reading or writing a stream already
follows, and the one destination that states no extension, so it is what
{func}`format_from_path` reads as {attr}`CaptureFormat.ANSI`.
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


@dataclass(frozen=True)
class Chrome:
    """How the window around a capture's text is drawn.

    One value for the decoration {func}`render`, {func}`capture`,
    {func}`~click_extra.recording.record_and_render` and
    {func}`~click_extra.snippet.render_snippet` all take, so its defaults live in
    one place. A field left at `None` takes what the capture's background and
    preset draw, which {meth}`resolve` fills in.

    ```{code-block} python

    from click_extra.screenshot import Chrome, render

    svg = render(text, chrome=Chrome(margin=0, watermark=""))
    ```
    """

    border: str | None = None
    """Color of the window's frame.

    `None` takes the one the background can show, see {data}`CAPTURE_BORDERS`;
    {data}`~click_extra.screenshot_svg.NO_PAINT` draws none.
    """

    border_width: int = DEFAULT_BORDER_WIDTH
    """Thickness of that frame, in pixels."""

    radius: int | None = None
    """How round the window's corners are, in pixels. Zero squares them.

    `None` takes the preset's own, or {data}`~click_extra.screenshot_svg.DEFAULT_RADIUS`
    without one.
    """

    backdrop: str = NO_PAINT
    """Paint filling the image behind the window, margin included.

    {data}`~click_extra.screenshot_svg.NO_PAINT` leaves it transparent.
    """

    shadow: str | None = None
    """Color of the window's drop shadow.

    `None` takes the background's own, see {data}`CAPTURE_SHADOWS`;
    {data}`~click_extra.screenshot_svg.NO_PAINT` draws none.
    """

    margin: int = DEFAULT_MARGIN
    """Transparent pixels left around the window, on all four sides."""

    padding: int = DEFAULT_PADDING
    """Pixels added inside the window, around the text."""

    opacity: float = OPAQUE
    """How solid the window's body is, from {data}`~click_extra.screenshot_svg.OPAQUE`
    down to `0.0`.

    Below it, whatever the capture is laid over shows through.
    """

    watermark: str = DEFAULT_WATERMARK
    """Credit line drawn in the image's bottom-right corner.

    See {data}`~click_extra.screenshot_svg.DEFAULT_WATERMARK`. An empty string draws
    none.
    """

    watermark_color: str | None = None
    """Color that line is drawn in.

    `None` takes {data}`~click_extra.screenshot_svg.WATERMARK_INK`, which reads on a
    page of either color.
    """

    def resolve(
        self, background: CaptureBackground, preset: TerminalPreset | None
    ) -> Chrome:
        """This chrome, with every `None` replaced by what the capture draws.

        {func}`~click_extra.screenshot_svg.render_svg` and
        {func}`~click_extra.screenshot_html.render_html` take resolved values, which
        makes this the one step between the two layers.

        :param background: chrome the capture is headed for.
        :param preset: terminal being pictured, or `None`.
        :return: a chrome carrying no `None`.
        """
        return replace(
            self,
            border=CAPTURE_BORDERS[background] if self.border is None else self.border,
            radius=(
                (DEFAULT_RADIUS if preset is None else preset.radius)
                if self.radius is None
                else self.radius
            ),
            shadow=CAPTURE_SHADOWS[background] if self.shadow is None else self.shadow,
            watermark_color=(
                WATERMARK_INK if self.watermark_color is None else self.watermark_color
            ),
        )


CHROME_FIELDS: frozenset[str] = frozenset(field.name for field in fields(Chrome))
"""The {class}`Chrome` field names, which the capture functions once took one by one."""


def fold_chrome_arguments(
    function: str, chrome: Chrome, legacy: Mapping[str, Any]
) -> Chrome:
    """`chrome`, with the window arguments `function` used to take folded in.

    Those arguments still resolve for one deprecation cycle, and passing any of
    them warns.

    :param function: name of the capture function, for the messages.
    :param chrome: the chrome the call passed.
    :param legacy: the other keyword arguments the call passed.
    :return: `chrome` updated with `legacy`.
    :raises TypeError: on an argument `function` never took.
    """
    unknown = sorted(set(legacy) - CHROME_FIELDS)
    if unknown:
        msg = f"{function}() got an unexpected keyword argument {unknown[0]!r}"
        raise TypeError(msg)
    if not legacy:
        return chrome
    warn_deprecated_usage(
        f"Passing {', '.join(f'{name}=' for name in legacy)} to {function}()",
        f"chrome=Chrome({', '.join(f'{name}=...' for name in legacy)})",
    )
    return replace(chrome, **legacy)


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

So a CLI asking for {ref}`--theme auto <automatic-background-detection>`
renders for the chrome its picture is drawn on, instead of falling back to dark
inside a light window. A CLI that never asks is unaffected: the variables only
answer a question it does not put.
"""

CAPTURE_HIDDEN_TERMINAL_VARS: tuple[str, ...] = ("TERM_PROGRAM",)
"""Environment variables naming the terminal a capture is *taken* from.

A capture is drawn for a file, and read in a browser or an image viewer. The
terminal that happened to run it is therefore not the terminal it is drawn
for, and anything the command would tailor to that terminal has to be kept
away from it, or the same capture comes out differently on every machine.

`TERM_PROGRAM` is the one that bites, through
{func}`~click_extra.table._paints_wider_than_it_advances`: a table carrying an
emoji-presentation sequence is padded for the terminal named there, so a
capture taken under Apple Terminal is wider than the same capture taken under
Ghostty. Committed side by side, the two never stop rewriting each other.

Cleared rather than pinned to a value: no name is the honest answer, since a
capture is drawn for no terminal in particular.
"""


AUTO_CURSOR: Literal["auto"] = "auto"
"""Cursor shape asking for the one the terminal preset decides.

The third of this module's `auto` sentinels, and the same bargain as
{data}`AUTO_COLUMNS` and {data}`~click_extra.screenshot_svg.AUTO_HOLD`: the caller says
a cursor is wanted and leaves what it looks like to whatever knows the terminal. It is
what {attr}`~click_extra.screenshot_presets.Cursor.shape` of `None` spells on a command
line, which cannot pass `None`.
"""


AUTO_COLUMNS: Literal["auto"] = "auto"
"""Width asking for the one the captured text itself decides.

Neither end of the pipeline is pinned: the command wraps to whatever terminal it
finds (Click's own 80 when that is a pipe, or a documentation build), and the
image is laid out at the longest line that came back, see
{func}`~click_extra.layout.fit_columns`. Nothing the command printed folds
inside the picture then, which is what a line the command does not wrap on its
own needs: a prompt, a wide table, a machine-readable dump.

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


AUTO_TRUNCATION: Literal["auto"] = "auto"
"""Marker asking for a rule as wide as the lines it stands between.

{data}`TRUNCATION_LABEL` centered in a run of {data}`TRUNCATION_RULE`, spanning
the widest line the capture kept. A bare label sits in the left margin and reads
as one more line of output; a rule crosses the picture and reads as a seam,
which is what a cut is. It carries no brackets, unlike a rule naming a section:
there is nothing to name here, and the label is the cut itself.

Measured on the kept lines alone, so the marker can never be what decides the
image width. That also makes it track an explicit `columns` only as far as the
text does: a capture whose lines all stop short draws a rule that stops there
too.
"""

TRUNCATION_LABEL = "\N{BLACK SCISSORS}"
"""What {data}`AUTO_TRUNCATION` centers in its rule."""

TRUNCATION_RULE = "\N{MIDDLE DOT}"
"""Character {data}`AUTO_TRUNCATION` draws its rule with.

Broken rather than {data}`~click_extra.layout.RULE_GLYPH`: a dotted line reads as
text missing from that spot, where an unbroken one reads as a section ending.

A dot rather than one of the Box Drawing dashes, which carry two or three
strokes inside a single cell. Those strokes and the hairline gaps between them
are each a pixel or two wide at a normal capture scale, and a cell advances a
fractional number of device pixels, so the gaps land inside a pixel on some
cells and on a boundary on others: neighbouring dashes merge here and separate
there, and the rule shimmers. One dot per cell has nothing to merge with.
"""


DEFAULT_TRUNCATION: str = AUTO_TRUNCATION
"""Marker standing in for the lines {func}`trim_lines` cut away."""

_SGR_RE = re.compile(r"\x1b\[[0-9;]*m")
"""One SGR escape sequence, the kind that changes how the text after it looks.

Matched so {func}`emphasize_ansi` can restate a band after each one: a full
reset closes the band along with the ink it was closing.
"""


def auto_columns(pictures: Sequence[str], cursor: Cursor | None = None) -> int:
    """Width, in characters, an auto-sized capture of `pictures` asks for.

    The longest line any of them holds, which is what keeps a command's own
    wrapping from folding again inside the picture. Frames are stacked in one
    window, so the widest is what has to fit.

    A cursor standing past the end of its row needs a cell of its own on top of
    that. At exactly the text's width it would otherwise wrap onto the row
    below, see {func}`~click_extra.screenshot_svg.cursor_cell`, and an auto-sized
    capture would show a row holding nothing but a cursor: the width is derived from the
    text, so the text always ends on the last column.

    :param pictures: the captured texts, one per frame, or the one a still
        draws.
    :param cursor: the cursor the capture draws, if any.
    :return: the width, in characters.
    """
    width = max(fit_columns(picture, floor=MIN_COLUMNS) for picture in pictures)
    if cursor is None:
        return width
    # Probed one column wider than the text, so the reading is where the cursor
    # stands rather than where that width would already have wrapped it.
    standing = (cursor_cell(picture, width + 1) for picture in pictures)
    return max(width, *(at[1] + 1 for at in standing if at is not None))


def append_prompt(
    text: str,
    *,
    background: CaptureBackground = CaptureBackground.DARK,
    preset: TerminalPreset | None = None,
) -> str:
    """Put the shell's prompt back on the row under a finished command.

    What a terminal actually shows once a command exits: the shell comes back
    and waits, so the row under the output holds its sigil rather than nothing.
    Paired with a cursor it costs no height at all, the cursor having already
    claimed that row, see {func}`~click_extra.screenshot_svg.cursor_cell`. It also puts
    the cursor somewhere that reads: after a prompt, instead of alone on an empty line.

    ```{caution}
    Only for a screen the command has finished drawing. Mid-animation the shell
    has not come back, and a sigil there says the command exited when it did
    not. {func}`~click_extra.recording.record_and_render` therefore closes its
    last frame alone.
    ```

    :param text: the captured text to close.
    :param background: chrome the capture is headed for, which picks the theme
        the sigil is styled with.
    :param preset: terminal being pictured, which names the sigil its shell
        draws. `None` keeps this platform's.
    :return: the same text, closed by a prompt.
    """
    with forced_color():
        sigil = format_cli_prompt(
            (),
            theme=PROMPT_THEMES[background],
            prompt=None if preset is None else preset.prompt,
        )
    # A screen closing on a newline already carries the empty row the prompt
    # belongs on: filling it costs nothing, where appending would leave a blank
    # row between the output and the shell.
    return f"{text}{sigil}" if text.endswith("\n") else f"{text}\n{sigil}"


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

    The terminal this runs *from* is hidden from the command, see
    {data}`CAPTURE_HIDDEN_TERMINAL_VARS`, so one machine's capture matches
    another's.

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
    extra_env.update(dict.fromkeys(CAPTURE_HIDDEN_TERMINAL_VARS))
    if columns != AUTO_COLUMNS:
        extra_env["COLUMNS"] = str(columns)
    with forced_color():
        return run_cli(
            args,
            extra_env=extra_env,
            timeout=timeout,
            merge_stderr=merge_stderr,
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
    head_lines = lines[:head] if head else []
    tail_lines = lines[-tail:] if tail else []
    marker = truncation
    if truncation == AUTO_TRUNCATION:
        marker = _rule_marker([*head_lines, *tail_lines])
    return "\n".join([*head_lines, marker, *tail_lines])


def _rule_marker(lines: Sequence[str]) -> str:
    """Center {data}`TRUNCATION_LABEL` in a rule as wide as the widest of `lines`.

    :param lines: the lines the marker is drawn between.
    :return: the marker to write in their place.
    """
    return center_in_rule(
        style(TRUNCATION_LABEL, fg=RULE_COLOR),
        fit_columns("\n".join(lines)),
        rule=TRUNCATION_RULE,
        opening=" ",
        closing=" ",
    )


def emphasize_ansi(
    text: str,
    lines: Sequence[int],
    paint: str,
) -> str:
    """Band the named lines of ANSI text, the way a terminal can.

    The picture's band is a rectangle drawn behind a row. A terminal has no
    behind, so the band is the row's own background color, set for the whole
    row and padded out to the longest line so the marked rows still square up
    into a block rather than ending ragged.

    ```{caution}
    The band is restated after every escape sequence in the row, not just at
    its start. Pygments closes a colored run with a full reset (`\\x1b[39;00m`),
    which clears the background along with the ink: set once, a band would stop
    at the row's first keyword. Restating the same color costs nothing to look
    at, since the second declaration paints what the first already did.
    ```

    :param text: the text to band, ANSI escape sequences included.
    :param lines: rows to band, counted from `1`. Empty bands nothing.
    :param paint: the band's color, as `#rrggbb`.
    :return: the text, banded.
    """
    if not lines:
        return text
    wanted = set(lines)
    rows = text.split("\n")
    width = max((cell_width(unstyle(row)) for row in rows), default=0)
    red, green, blue = _hex_to_rgb(paint)
    band = f"\x1b[48;2;{red};{green};{blue}m"
    painted = []
    for number, row in enumerate(rows, 1):
        if number not in wanted:
            painted.append(row)
            continue
        filled = row + " " * max(0, width - cell_width(unstyle(row)))
        restated = _SGR_RE.sub(lambda match: f"{match.group(0)}{band}", filled)
        painted.append(f"{band}{restated}\x1b[49m")
    return "\n".join(painted)


def render(
    text: str = "",
    *,
    format: CaptureFormat = CaptureFormat.SVG,
    columns: TColumns = DEFAULT_COLUMNS,
    title: str = "",
    unique_id: str | None = None,
    frames: Sequence[str] | None = None,
    interval: float | Sequence[float] | None = None,
    hold: THold = 0.0,
    blank: float = 0.0,
    speed: float = 1.0,
    emphasize: Sequence[int] = (),
    cursor: Cursor | None = None,
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
    preset: TerminalPreset | None = None,
    palette: TerminalPalette | None = None,
    chrome: Chrome = Chrome(),
    **legacy: Unpack[ChromeArguments],
) -> str:
    """Render captured terminal text to the document `format` names.

    :param text: captured output, ANSI escape sequences included.
    :param format: which document to produce. {attr}`CaptureFormat.ANSI` draws
        no window, so it ignores everything describing one: the frame, the
        chrome, the caption, the margin, the credit line and the animation. What
        it keeps is `emphasize`, which marks rows rather than surrounding them,
        and whatever the caller already did to the text itself.
    :param columns: terminal width, in characters, an SVG is laid out at, or
        {data}`AUTO_COLUMNS` for the width its own longest line asks for. HTML
        reflows and ANSI is the text itself, so both ignore this.
    :param title: caption drawn in an SVG's window chrome, or an HTML document's
        `<title>`.
    :param unique_id: SVG only. Prefix namespacing the source's CSS classes and
        element IDs. Pinning it to something stable (the output file's name, say)
        keeps a regenerated capture diffing line by line, instead of renaming
        every class as soon as a single character of output changes. Characters
        a CSS class name cannot carry are folded to a dash.
    :param frames: SVG only. The animation's frames, see
        {func}`~click_extra.screenshot_svg.render_svg`.
    :param interval: SVG only. How long each of them is shown, see
        {func}`~click_extra.screenshot_svg.render_svg`.
    :param hold: SVG only. Extra seconds the last frame stays up, or
        {data}`~click_extra.screenshot_svg.AUTO_HOLD` to scale them to that frame's line
        count, see {func}`~click_extra.screenshot_svg.render_svg`.
    :param blank: SVG only. Seconds of empty screen closing the cycle, see
        {func}`~click_extra.screenshot_svg.render_svg`.
    :param speed: SVG only. How much faster to play than recorded, see
        {func}`~click_extra.screenshot_svg.render_svg`.
    :param emphasize: SVG only. Lines to draw a band behind, see
        {func}`~click_extra.screenshot_svg.render_svg`.
    :param cursor: SVG only. The terminal cursor to draw, see
        {class}`~click_extra.screenshot_presets.Cursor`. `None` draws none. A
        cursor naming no shape takes the one the `preset` says that terminal
        draws, so `--preset windows` gets its bar without stating it.
    :param full: HTML only. See {func}`~click_extra.screenshot_html.render_html`.
    :param background: chrome to draw on, see
        {class}`~click_extra.screenshot_presets.CaptureBackground`.
    :param palette: colors the text resolves against. `None` takes the ones the
        preset and chrome name, which is what a terminal capture wants. The
        window's decorations keep answering to the chrome either way: a stated
        palette repaints the terminal's body, not the desktop's frame around it.
    :param chrome: how the window around the text is drawn, see
        {class}`Chrome`.
    :param legacy: deprecated: the {class}`Chrome` fields, passed one by one.
    :return: the rendered document.
    :raises ValueError: asking an HTML capture to animate.
    """
    chrome = fold_chrome_arguments("render", chrome, legacy)
    frame: dict[str, Any] = asdict(chrome.resolve(background, preset))
    # What the chrome would paint on its own, kept apart from the `palette` the
    # text is drawn with: the two differ for a capture whose colors come from
    # elsewhere, and the decorations below stay the chrome's in that case.
    chrome_palette = resolve_palette(preset, background)
    if palette is None:
        palette = chrome_palette
    if preset is not None:
        frame["buttons"] = preset.buttons
        frame["buttons_color"] = chrome_palette.foreground
        frame["font_stack"] = preset.font_stack
        frame["titlebar"] = chrome_palette.titlebar
        # A window wearing neither decoration nor caption has nothing to seat in
        # its title bar, so it closes over the first line of output instead.
        frame["collapse_titlebar"] = not any(
            (preset.buttons.circles, preset.buttons.glyphs, title),
        )
        if cursor is not None and cursor.shape is None:
            cursor = cursor._replace(shape=preset.cursor)
    if format is CaptureFormat.ANSI:
        if frames is not None:
            raise ValueError(f"{CaptureFormat.ANSI} captures do not animate.")
        # The text already is the document, so there is nothing to render: what
        # a terminal reads is the stream a capture was carried in all along.
        # Only the emphasis survives, being the one mark that lives in the rows
        # rather than around them.
        return emphasize_ansi(
            text,
            emphasize,
            blend(palette.background, palette.foreground, EMPHASIS_RATIO),
        )
    if format is CaptureFormat.HTML:
        if frames is not None:
            # An HTML capture is a `<pre>` of selectable text, which has no
            # frame to hide: only the SVG draws a picture that can hold several.
            raise ValueError(f"{CaptureFormat.HTML} captures do not animate.")
        return render_html(
            text,
            title=title,
            full=full,
            background=background,
            preset=preset,
            palette=palette,
            **frame,
        )
    return render_svg(
        text,
        columns=(
            auto_columns(frames or (text,), cursor)
            if columns == AUTO_COLUMNS
            else columns
        ),
        title=title,
        unique_id=unique_id,
        frames=frames,
        interval=interval,
        hold=hold,
        blank=blank,
        speed=speed,
        emphasize=emphasize,
        cursor=cursor,
        palette=palette,
        **frame,
    )


def prompt_line(
    args: TArg | TNestedArgs,
    *,
    prompt: str | None = None,
    background: CaptureBackground = CaptureBackground.DARK,
    preset: TerminalPreset | None = None,
) -> str:
    """Compose the invocation a capture draws above its output.

    The one place three pipelines agree on what a prompt looks like: a still
    capture, a recording, and a documentation block that records one. Each drew
    its own before, which is three chances for the sigil, the theme or the
    preset to disagree between an image and the image beside it.

    :param args: the command line that was run, in the nested form
        {func}`~click_extra.execution.run_cli` accepts.
    :param prompt: command line to *display*, when it differs from the one run.
        An empty string draws no prompt at all; `None` shows what was run.
    :param background: chrome the capture is headed for, which picks the theme
        the line is styled with.
    :param preset: terminal being pictured, which names the sigil its shell
        draws. `None` keeps this platform's.
    :return: the styled line, or empty when nothing is to be drawn.
    """
    displayed = args_cleanup(args) if prompt is None else tuple(shlex.split(prompt))
    if not displayed:
        return ""
    with forced_color():
        return format_cli_prompt(
            displayed,
            theme=PROMPT_THEMES[background],
            prompt=None if preset is None else preset.prompt,
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
    emphasize: Sequence[int] = (),
    cursor: Cursor | None = None,
    closing_prompt: bool = False,
    title: str = "",
    unique_id: str | None = None,
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
    preset: TerminalPreset | None = None,
    chrome: Chrome = Chrome(),
    **legacy: Unpack[ChromeArguments],
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
        {func}`~click_extra.layout.number_lines`. The prompt counts as the first
        of them, being the invocation everything under it came from.
    :param emphasize: lines to draw a band behind, see
        {func}`~click_extra.screenshot_svg.render_svg`. The prompt is line 1 here too,
        and a gutter does not shift the count.
    :param cursor: see {func}`render`. A still capture leaves its cursor after
        the last thing the command printed, which is where the shell finds it.
    :param closing_prompt: draw the shell's prompt on the row under the output,
        which is where it comes back once the command exits, see
        {func}`append_prompt`.
    :param title: see {func}`render`.
    :param unique_id: see {func}`render`.
    :param full: see {func}`render`.
    :param background: see {func}`render`.
    :param preset: see {func}`render`.
    :param chrome: see {func}`render`.
    :param legacy: deprecated: the {class}`Chrome` fields, passed one by one.
    :return: the rendered document, and the command's exit code.
    """
    chrome = fold_chrome_arguments("capture", chrome, legacy)
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
    invocation = prompt_line(args, prompt=prompt, background=background, preset=preset)
    if invocation:
        text = f"{invocation}\n{text}"
    if closing_prompt:
        text = append_prompt(text, background=background, preset=preset)
    # Numbered after both prompts join it, so line 1 is the invocation that
    # produced everything under it and the last is the shell coming back.
    if line_numbers:
        text = number_lines(text)
    return (
        render(
            text,
            format=format,
            columns=columns,
            emphasize=emphasize,
            cursor=cursor,
            title=title,
            unique_id=unique_id,
            full=full,
            background=background,
            preset=preset,
            chrome=chrome,
        ),
        process.returncode,
    )


def format_from_path(path: Path) -> CaptureFormat:
    """Pick the capture format a file name asks for.

    {data}`STDOUT_PATH` names the terminal, whose format is the escape sequences
    themselves. It is answered here rather than at the call site so the one
    question "what does this destination want?" has one answer.

    :param path: where the capture is to be written.
    :return: the {class}`CaptureFormat` its extension names.
    :raises ValueError: when the extension names no format.
    """
    if path.name == STDOUT_PATH:
        return CaptureFormat.ANSI
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
