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
on a character grid by {func}`~click_extra.capture.svg.render_svg`, HTML is
inline-styled markup from {func}`~click_extra.capture.html.render_html`.

The two are not interchangeable, and neither is a fallback for the other:

- **SVG** goes where you do not own the page. GitHub and PyPI render an image
  and strip inline HTML, so a README has no other option. It is a picture: the
  text is not selectable, and not searchable.
- **HTML** goes where you do own the page. The text stays selectable,
  searchable and copy-pasteable, and reflows with the container.
"""

from __future__ import annotations

import shlex
import subprocess
from enum import Enum

from click import style

from .._utils import AUTO
from ..ansi import ANSI_SGR_RE, RESET, hex_to_rgb
from ..color import TerminalBackground, forced_color
from ..execution import args_cleanup, format_cli_prompt, run_cli
from ..layout import (
    RULE_COLOR,
    cell_width,
    center_in_rule,
    fit_columns,
    number_lines,
)
from ..output import is_stdout
from ..styling import Style, split_ansi
from ..theme import BUILTIN_THEMES
from .html import render_html
from .presets import (
    Chrome,
    Cursor,
    TerminalPalette,
    TerminalPreset,
    resolve_palette,
)
from .svg import cursor_cell, emphasis_paint, render_svg

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import Any, Literal, TypeAlias

    from ..execution import TArg, TNestedArgs
    from ..theme import HelpTheme
    from .svg import THold

    TColumns: TypeAlias = int | Literal["auto"]
    """Width a capture is taken and rendered at, see {data}`AUTO_COLUMNS`."""


AUTO_COLUMNS: Literal["auto"] = AUTO
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

AUTO_CURSOR: Literal["auto"] = AUTO
"""Cursor shape asking for the one the terminal preset decides.

The same bargain as {data}`AUTO_COLUMNS` and
{data}`~click_extra.capture.svg.AUTO_HOLD`: the caller says a cursor is wanted
and leaves what it looks like to whatever knows the terminal. It is what
{attr}`~click_extra.capture.presets.Cursor.shape` of `None` spells on a command
line, which cannot pass `None`.
"""

AUTO_TRUNCATION: Literal["auto"] = AUTO
"""Marker asking for a rule across the width of the picture.

{data}`TRUNCATION_LABEL` centered in a run of {data}`TRUNCATION_RULE`, spanning
the text column of the window. A bare label sits in the left margin and reads
as one more line of output; a rule crosses the picture and reads as a seam,
which is what a cut is. It carries no brackets, unlike a rule naming a section:
there is nothing to name here, and the label is the cut itself.

Never wider than what decides the image width, so the marker cannot widen the
picture it cuts: the pinned `columns`, or the widest line under
{data}`AUTO_COLUMNS`. See {func}`_rule_marker`.
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

AUTO_WRAP_MARKER: Literal["auto"] = AUTO
"""Marker asking for {data}`WRAP_MARKER_LABEL` at every fold.

A terminal folds a line wider than itself silently, so a reader of a picture
cannot tell a line that wrapped from one the command printed in pieces, and a
break landing mid-word reads as a typo. The marker says which it is. It costs a
cell of the row it closes, see {func}`~click_extra.layout.grid`.
"""

WRAP_MARKER_LABEL = "\N{DOWNWARDS ARROW WITH CORNER LEFTWARDS}"
"""What {data}`~click_extra.capture.screenshot.AUTO_WRAP_MARKER` writes at the fold.

`↵` rather than a right-pointing arrow: the line turns back to the left margin
and continues on the row below, which is what the glyph draws. It is also the
one convention with a precedent in another pager: `delta` ships it as its own
`--wrap-left-symbol`, and paints it in a color of its own for the same reason
this one is drawn in {data}`~click_extra.layout.RULE_COLOR`.
"""

DEFAULT_WRAP_MARKER: str = ""
"""What closes a folded row when nothing asks for a marker.

Empty, so a capture folds the way a terminal does. A reader drawing a terminal
window is not owed a mark for something the terminal itself would not show.
"""

PROMPT_THEMES: dict[TerminalBackground, HelpTheme | None] = {
    TerminalBackground.DARK: None,
    TerminalBackground.LIGHT: BUILTIN_THEMES["light"],
}
"""Theme the prompt line is drawn with, per chrome.

The captured output arrives already colored by the CLI that produced it, under
whatever theme *that* run was told to use. The prompt is the one line this
process draws itself, so it is the one that would otherwise land on white
chrome in the dark default's near-white `invoked_command` style, invisible.

`None` keeps whatever theme the invocation already runs under.
"""

CAPTURE_TERMINAL_HINTS: dict[TerminalBackground, dict[str, str]] = {
    TerminalBackground.DARK: {"CLITHEME": "dark", "COLORFGBG": "15;0"},
    TerminalBackground.LIGHT: {"CLITHEME": "light", "COLORFGBG": "0;15"},
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


class CaptureFormat(Enum):
    """Document formats a capture can be rendered to.

    The value doubles as the file extension {meth}`from_path` matches on.
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

    Laid out on a character grid by {func}`~click_extra.capture.svg.render_svg`.
    """

    @classmethod
    def from_path(cls, path: Path) -> CaptureFormat:
        """Pick the capture format a file name asks for.

        A bare {data}`~click_extra.output.STDOUT_SENTINEL` names the terminal,
        whose format is the escape sequences themselves, see
        {func}`~click_extra.output.is_stdout`. A file *named* `-` in some
        directory is a file like any other, and answers by its extension, which
        it has none of. It is answered here rather than at the call site so the
        one question "what does this destination want?" has one answer.

        :param path: where the capture is to be written.
        :return: the {class}`CaptureFormat` its extension names.
        :raises ValueError: when the extension names no format.
        """
        if is_stdout(path):
            return cls.ANSI
        suffix = path.suffix.lower().lstrip(".")
        # `.htm` is the same document under the older extension.
        if suffix == "htm":
            suffix = cls.HTML.value
        try:
            return cls(suffix)
        except ValueError:
            known = ", ".join(sorted(f".{member.value}" for member in cls))
            raise ValueError(
                f"Cannot tell the capture format of {path.name!r}: name it {known}."
            ) from None


def capture_environment(
    background: TerminalBackground,
    columns: TColumns,
) -> dict[str, str | None]:
    """The environment a capture states to the command it runs.

    The overrides {func}`~click_extra.envvar.env_copy` lays over the inherited
    environment, which is how {func}`~click_extra.execution.run_cli` takes them:
    the chrome's {data}`CAPTURE_TERMINAL_HINTS`, every
    {data}`CAPTURE_HIDDEN_TERMINAL_VARS` entry mapped to `None` so it is removed
    rather than set, and the width the command wraps to.

    :param background: chrome the capture is headed for.
    :param columns: terminal width, in characters, pinned through `COLUMNS`.
        {data}`AUTO_COLUMNS` pins nothing.
    :return: the overrides, by variable name.
    """
    overrides: dict[str, str | None] = dict(CAPTURE_TERMINAL_HINTS[background])
    overrides.update(dict.fromkeys(CAPTURE_HIDDEN_TERMINAL_VARS))
    if columns != AUTO_COLUMNS:
        overrides["COLUMNS"] = str(columns)
    return overrides


def resolve_wrap_marker(marker: str) -> str:
    """Read a `wrap_marker` option into the characters written at a fold.

    The one reading of the option every entry point shares: the `--wrap-marker`
    of the capture commands, and the API those commands call.

    :param marker: the text,
        {data}`~click_extra.capture.screenshot.AUTO_WRAP_MARKER`, or an empty
        string for no marker at all.
    :return: the characters to write at a fold, empty for none.
    """
    return WRAP_MARKER_LABEL if marker == AUTO_WRAP_MARKER else marker


def parse_columns(value: str) -> TColumns:
    """Read a width written as text into a number, or into {data}`AUTO_COLUMNS`.

    The one reading of a `columns` option every entry point shares: the
    `--columns` of the capture commands and the `:screenshot-columns:` of the
    documentation directive. Each wraps the error in the exception its framework
    reports.

    :param value: the text, an integer or the word {data}`AUTO_COLUMNS`.
    :return: the width, in characters, or {data}`AUTO_COLUMNS`.
    :raises ValueError: when the text is neither, or names a width under
        {data}`MIN_COLUMNS`.
    """
    if value.strip().lower() == AUTO_COLUMNS:
        return AUTO_COLUMNS
    try:
        width = int(value)
    except ValueError:
        raise ValueError(
            f"{value!r} is neither an integer nor {AUTO_COLUMNS!r}."
        ) from None
    if width < MIN_COLUMNS:
        raise ValueError(f"{width} is narrower than the {MIN_COLUMNS}-column floor.")
    return width


def auto_columns(pictures: Sequence[str], cursor: Cursor | None = None) -> int:
    """Width, in characters, an auto-sized capture of `pictures` asks for.

    The longest line any of them holds, which is what keeps a command's own
    wrapping from folding again inside the picture. Frames are stacked in one
    window, so the widest is what has to fit.

    A cursor standing past the end of its row needs a cell of its own on top of
    that. At exactly the text's width it would otherwise wrap onto the row
    below, see {func}`~click_extra.capture.svg.cursor_cell`, and an auto-sized
    capture would show a row holding nothing but a cursor: the width is derived
    from the text, so the text always ends on the last column.

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
    return max([width, *(at[1] + 1 for at in standing if at is not None)])


def _styled_prompt(
    displayed: Sequence[str],
    background: TerminalBackground,
    preset: TerminalPreset | None,
) -> str:
    """Draw a prompt line the way a capture of `background` shows it.

    Colors forced, since the line is headed for a picture rather than for the
    terminal running this; the theme picked for the chrome, see
    {data}`PROMPT_THEMES`; and the sigil the pictured terminal's shell draws.

    :param displayed: the command line after the sigil. Empty draws the sigil
        alone, which is the shell waiting.
    :param background: chrome the capture is headed for.
    :param preset: terminal being pictured, or `None` for this platform's.
    :return: the styled line.
    """
    with forced_color():
        return format_cli_prompt(
            displayed,
            theme=PROMPT_THEMES[background],
            prompt=None if preset is None else preset.prompt,
        )


def prompt_line(
    args: TArg | TNestedArgs,
    *,
    prompt: str | None = None,
    background: TerminalBackground = TerminalBackground.DARK,
    preset: TerminalPreset | None = None,
) -> str:
    """Compose the invocation a capture draws above its output.

    The one place three pipelines agree on what a prompt looks like: a still
    capture, a recording, and a documentation block that records one. Drawing
    it three times would be three chances for the sigil, the theme or the
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
    return _styled_prompt(displayed, background, preset)


def append_prompt(
    text: str,
    *,
    background: TerminalBackground = TerminalBackground.DARK,
    preset: TerminalPreset | None = None,
) -> str:
    """Put the shell's prompt back on the row under a finished command.

    What a terminal actually shows once a command exits: the shell comes back
    and waits, so the row under the output holds its sigil rather than nothing.
    Paired with a cursor it costs no height at all, the cursor having already
    claimed that row, see {func}`~click_extra.capture.svg.cursor_cell`. It also
    puts the cursor somewhere that reads: after a prompt, instead of alone on an
    empty line.

    ```{caution}
    Only for a screen the command has finished drawing. Mid-animation the shell
    has not come back, and a sigil there says the command exited when it did
    not. {func}`~click_extra.capture.recording.record_and_render` therefore closes its
    last frame alone.
    ```

    :param text: the captured text to close.
    :param background: chrome the capture is headed for, which picks the theme
        the sigil is styled with.
    :param preset: terminal being pictured, which names the sigil its shell
        draws. `None` keeps this platform's.
    :return: the same text, closed by a prompt.
    """
    sigil = _styled_prompt((), background, preset)
    # A screen closing on a newline already carries the empty row the prompt
    # belongs on: filling it costs nothing, where appending would leave a blank
    # row between the output and the shell.
    return f"{text}{sigil}" if text.endswith("\n") else f"{text}\n{sigil}"


def capture_output(
    args: TArg | TNestedArgs,
    *,
    columns: TColumns = DEFAULT_COLUMNS,
    background: TerminalBackground = TerminalBackground.DARK,
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
    with forced_color():
        return run_cli(
            args,
            extra_env=capture_environment(background, columns),
            timeout=timeout,
            merge_stderr=merge_stderr,
        )


def _leaves_style_open(lines: Sequence[str]) -> bool:
    """Whether `lines` end with a style still in effect.

    A cut drops whatever closes a style opened above it. A heading printed as
    `style("\\n● Step")` puts its opening escapes on the line before the text and
    its reset on the text's own line, so cutting between the two leaves the style
    open. The marker would inherit it, and so would every line `tail` keeps: a
    rule whose first segment only sets a color came out underlined.

    :param lines: the lines kept above the marker.
    :return: `True` when anything but the default style is still in effect.
    """
    if not lines:
        return False
    # A sentinel character makes the style in effect at the end visible:
    # `split_ansi` drops empty runs, so escapes closing the text would yield
    # nothing to read the state off.
    *_, (state, _sentinel) = split_ansi("\n".join(lines) + "\x00")
    return state != Style()


def _rule_marker(
    lines: Sequence[str],
    columns: TColumns = DEFAULT_COLUMNS,
    wrap_marker: str = DEFAULT_WRAP_MARKER,
    width_floor: int = 0,
    gutter: int = 0,
) -> str:
    """Center {data}`TRUNCATION_LABEL` in a rule across the picture's text column.

    A cut crosses the whole picture, so the rule spans the width the text is
    drawn at: `columns`, less the cell a wrap marker takes and the `gutter` the
    line numbers take. Under {data}`AUTO_COLUMNS` the picture is as wide as its
    widest line, so the rule spans the widest of `lines`, or `width_floor` when
    a line drawn besides them, like the prompt, is wider still.

    ```{note}
    Never past the width the text is drawn at. {func}`~click_extra.layout.grid`
    folds any line reaching past it, and a rule folded on its last dots puts them
    alone on a row of their own, outside the text column. A wrap marker takes a
    cell of every row, so a rule as wide as `columns` would also fold, and close
    its row on the marker as if the rule continued below. A line-number gutter
    is drawn in front of every row, the rule's included, and pushes it past the
    width the same way.
    ```

    :param lines: the lines the marker is drawn between.
    :param columns: width the capture is drawn at, or {data}`AUTO_COLUMNS` when
        nothing folds.
    :param wrap_marker: what closes a folded row,
        {data}`~click_extra.capture.screenshot.AUTO_WRAP_MARKER` included.
    :param width_floor: under {data}`AUTO_COLUMNS`, the width of the widest line
        drawn besides `lines`.
    :param gutter: cells the line numbers take in front of every row.
    :return: the marker to write in their place.
    """
    if columns == AUTO_COLUMNS:
        # The gutter widens every row alike, the rule's included.
        width = fit_columns("\n".join(lines), floor=width_floor)
    else:
        width = columns - cell_width(resolve_wrap_marker(wrap_marker)) - gutter
    return center_in_rule(
        style(TRUNCATION_LABEL, fg=RULE_COLOR),
        width,
        rule=TRUNCATION_RULE,
        opening=" ",
        closing=" ",
    )


def trim_lines(
    text: str,
    *,
    head: int | None = None,
    tail: int | None = None,
    truncation: str = DEFAULT_TRUNCATION,
    columns: TColumns = DEFAULT_COLUMNS,
    wrap_marker: str = DEFAULT_WRAP_MARKER,
    width_floor: int = 0,
    gutter: int = 0,
) -> str:
    """Keep only the first `head` and last `tail` lines of `text`.

    Whatever is dropped is replaced by a single `truncation` line, so the image
    admits that it was cut rather than pretending to be the whole output. Text
    short enough to survive both bounds comes back untouched, with no marker.

    A cut leaving a style open above it closes that style before the marker, see
    {func}`_leaves_style_open`.

    :param text: the captured output.
    :param head: number of leading lines to keep, or `None` for no head bound.
    :param tail: number of trailing lines to keep, or `None` for no tail bound.
    :param truncation: line standing in for what was cut.
    :param columns: width the text is drawn at, which bounds the rule
        {data}`AUTO_TRUNCATION` draws, see {func}`_rule_marker`.
    :param wrap_marker: what closes a folded row, see {func}`render`. It takes a
        cell of every row, so it narrows the rule by as much.
    :param width_floor: under {data}`AUTO_COLUMNS`, the width of a line the
        picture draws besides `text`, like the prompt, which the rule spans too.
    :param gutter: cells the line numbers drawn after the cut take in front of
        every row, see {func}`~click_extra.layout.number_lines`. It narrows the
        rule by as much.
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
        marker = _rule_marker(
            [*head_lines, *tail_lines], columns, wrap_marker, width_floor, gutter
        )
    if _leaves_style_open(head_lines):
        marker = RESET + marker
    return "\n".join([*head_lines, marker, *tail_lines])


def _gutter_width(text: str) -> int:
    """Cells {func}`~click_extra.layout.number_lines` draws in front of each row.

    Measured on a numbered copy of `text` rather than restated, so the two
    cannot drift. The gutter widens by a digit when the row count does, so it
    is measured on the whole text the numbers are drawn on.

    :param text: the text to be numbered.
    :return: the gutter's width, in cells. Zero for a text with no row.
    """
    rows = text.splitlines()
    if not rows:
        return 0
    return cell_width(number_lines(text).partition("\n")[0]) - cell_width(rows[0])


def emphasize_ansi(
    text: str,
    lines: Sequence[int],
    paint: str,
) -> str:
    r"""Band the named lines of ANSI text, the way a terminal can.

    The picture's band is a rectangle drawn behind a row. A terminal has no
    behind, so the band is the row's own background color, set for the whole
    row and padded out to the longest line so the marked rows still square up
    into a block rather than ending ragged.

    ```{caution}
    The band is restated after every escape sequence in the row, not just at
    its start. Pygments closes a colored run with a full reset (`\x1b[39;00m`),
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
    # Escapes occupy no cell, so a styled row measures as its glyphs do.
    widths = [cell_width(row) for row in rows]
    width = max(widths, default=0)
    red, green, blue = hex_to_rgb(paint)
    band = f"\x1b[48;2;{red};{green};{blue}m"
    painted = []
    for number, (row, measured) in enumerate(zip(rows, widths, strict=True), 1):
        if number not in wanted:
            painted.append(row)
            continue
        filled = row + " " * (width - measured)
        restated = ANSI_SGR_RE.sub(lambda match: f"{match.group(0)}{band}", filled)
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
    wrap_marker: str = DEFAULT_WRAP_MARKER,
    full: bool = True,
    background: TerminalBackground = TerminalBackground.DARK,
    preset: TerminalPreset | None = None,
    palette: TerminalPalette | None = None,
    chrome: Chrome = Chrome(),
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
        {func}`~click_extra.capture.svg.render_svg`.
    :param interval: SVG only. How long each of them is shown, see
        {func}`~click_extra.capture.svg.render_svg`.
    :param hold: SVG only. Extra seconds the last frame stays up, or
        {data}`~click_extra.capture.svg.AUTO_HOLD` to scale them to that frame's line
        count, see {func}`~click_extra.capture.svg.render_svg`.
    :param blank: SVG only. Seconds of empty screen closing the cycle, see
        {func}`~click_extra.capture.svg.render_svg`.
    :param speed: SVG only. How much faster to play than recorded, see
        {func}`~click_extra.capture.svg.render_svg`.
    :param emphasize: SVG and ANSI. Lines to draw a band behind, see
        {func}`~click_extra.capture.svg.render_svg` and {func}`emphasize_ansi`.
    :param cursor: SVG only. The terminal cursor to draw, see
        {class}`~click_extra.capture.presets.Cursor`. `None` draws none. A
        cursor naming no shape takes the one the `preset` says that terminal
        draws, so `--preset windows` gets its bar without stating it.
    :param wrap_marker: SVG only. What closes each row a fold cut short,
        {data}`~click_extra.capture.screenshot.AUTO_WRAP_MARKER` for
        {data}`WRAP_MARKER_LABEL`, or empty to fold silently, see
        {func}`~click_extra.layout.grid`. HTML reflows with the page embedding
        it, and a terminal reading ANSI folds on its own, so neither has a fold
        of the capture's to mark.
    :param full: HTML only. See {func}`~click_extra.capture.html.render_html`.
    :param background: chrome to draw on, see
        {class}`~click_extra.color.TerminalBackground`.
    :param preset: terminal to draw the capture as, see
        {class}`~click_extra.capture.presets.TerminalPreset`. `None` keeps
        the renderer's own neutral window.
    :param palette: colors the text resolves against. `None` takes the ones the
        preset and chrome name, which is what a terminal capture wants. The
        window's decorations keep answering to the chrome either way: a stated
        palette repaints the terminal's body, not the desktop's frame around it.
    :param chrome: how the window around the text is drawn, see
        {class}`~click_extra.capture.presets.Chrome`.
    :return: the rendered document.
    :raises ValueError: asking an ANSI or HTML capture to animate.
    """
    if frames is not None and format is not CaptureFormat.SVG:
        # Only the SVG draws a picture that can hold several frames: an HTML
        # capture is a `<pre>` of selectable text, and an ANSI one is the stream
        # a terminal paints as it arrives.
        raise ValueError(f"{format.name} captures do not animate.")
    # What the chrome would paint on its own, kept apart from the `palette` the
    # text is drawn with: the two differ for a capture whose colors come from
    # elsewhere, and the decorations below stay the chrome's in that case.
    chrome_palette = resolve_palette(preset, background)
    if palette is None:
        palette = chrome_palette
    if format is CaptureFormat.ANSI:
        # The text already is the document, so there is nothing to render: what
        # a terminal reads is the stream a capture was carried in all along.
        # Only the emphasis survives, being the one mark that lives in the rows
        # rather than around them.
        return emphasize_ansi(text, emphasize, emphasis_paint(palette))

    frame: dict[str, Any] = {"chrome": chrome.resolve(background, preset)}
    if preset is not None:
        frame["font_stack"] = preset.font_stack
    if format is CaptureFormat.HTML:
        # The title bar and its decorations are drawn by the SVG alone: HTML
        # reflows with the page embedding it.
        return render_html(text, title=title, full=full, palette=palette, **frame)

    if preset is not None:
        frame["buttons"] = preset.buttons
        frame["buttons_color"] = chrome_palette.foreground
        frame["titlebar"] = chrome_palette.titlebar
        # A window wearing neither decoration nor caption has nothing to seat in
        # its title bar, so it closes over the first line of output instead.
        frame["collapse_titlebar"] = not any(
            (preset.buttons.circles, preset.buttons.glyphs, title),
        )
        if cursor is not None and cursor.shape is None:
            cursor = cursor._replace(shape=preset.cursor)
    return render_svg(
        text,
        columns=(
            auto_columns(frames or (text,), cursor)
            if columns == AUTO_COLUMNS
            else columns
        ),
        wrap_marker=resolve_wrap_marker(wrap_marker),
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
    wrap_marker: str = DEFAULT_WRAP_MARKER,
    closing_prompt: bool = False,
    title: str = "",
    unique_id: str | None = None,
    full: bool = True,
    background: TerminalBackground = TerminalBackground.DARK,
    preset: TerminalPreset | None = None,
    chrome: Chrome = Chrome(),
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
        {func}`~click_extra.capture.svg.render_svg`. The prompt is line 1 here too,
        and a gutter does not shift the count.
    :param cursor: see {func}`render`. A still capture leaves its cursor after
        the last thing the command printed, which is where the shell finds it.
    :param wrap_marker: see {func}`render`.
    :param closing_prompt: draw the shell's prompt on the row under the output,
        which is where it comes back once the command exits, see
        {func}`append_prompt`.
    :param title: see {func}`render`.
    :param unique_id: see {func}`render`.
    :param full: see {func}`render`.
    :param background: see {func}`render`.
    :param preset: see {func}`render`.
    :param chrome: see {func}`render`.
    :return: the rendered document, and the command's exit code.
    :raises OSError: when the command cannot start. {class}`subprocess.Popen`
        raises a `FileNotFoundError` for a program it cannot find, and a
        `PermissionError` for a file it cannot run.
    """
    process = capture_output(
        args,
        columns=columns,
        background=background,
        merge_stderr=merge_stderr,
        timeout=timeout,
    )
    invocation = prompt_line(args, prompt=prompt, background=background, preset=preset)

    def picture(gutter: int = 0) -> str:
        """The rows the capture draws, from the invocation to the shell's return."""
        text = trim_lines(
            process.stdout,
            head=head,
            tail=tail,
            truncation=truncation,
            columns=columns,
            wrap_marker=wrap_marker,
            # The prompt joins the picture below, and widens it under `auto`.
            width_floor=fit_columns(invocation),
            gutter=gutter,
        )
        if invocation:
            text = f"{invocation}\n{text}"
        if closing_prompt:
            text = append_prompt(text, background=background, preset=preset)
        return text

    text = picture()
    # Numbered after both prompts join it, so line 1 is the invocation that
    # produced everything under it and the last is the shell coming back. The
    # rows are drawn again first, for the rule to leave room for the gutter.
    if line_numbers:
        text = number_lines(picture(gutter=_gutter_width(text)))
    return (
        render(
            text,
            format=format,
            columns=columns,
            emphasize=emphasize,
            cursor=cursor,
            wrap_marker=wrap_marker,
            title=title,
            unique_id=unique_id,
            full=full,
            background=background,
            preset=preset,
            chrome=chrome,
        ),
        process.returncode,
    )
