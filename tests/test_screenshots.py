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

"""Tests for `click_extra.capture` and the captures committed under `docs/`.

A screenshot is CLI output that stopped re-running, so it rots the moment the
command it pictures changes. A rendered capture is machine-readable, which is
what makes both halves of this module possible: every run of same-styled
characters is one `<text>` element carrying its column as an `x` offset and its
width as a `textLength`, so the terminal text can be rebuilt from the glyph
coordinates and compared to what a CLI prints today.

That comparison needs neither a network round-trip nor a capture tool, which
keeps this an ordinary unit test. When the drift check fails, re-run the command
documented alongside the image in `docs/screenshots.md`.
"""

from __future__ import annotations

import importlib.metadata
import inspect
import os
import re
import shutil
import sys
import unicodedata
import warnings
from dataclasses import fields, replace
from html import escape, unescape
from itertools import combinations, pairwise
from pathlib import Path
from typing import NamedTuple

import pytest
from extra_platforms.pytest import skip_windows

from click_extra import SPINNERS, Spinner, Style, style, unstyle
from click_extra.capture import svg as capture_svg
from click_extra.capture.html import (
    LINE_SPACING,
    block_css,
    braille_css,
    render_html,
)
from click_extra.capture.presets import (
    BARE_CHROME,
    CAPTURE_BORDERS,
    CAPTURE_PALETTES,
    CAPTURE_SHADOWS,
    DEFAULT_RADIUS,
    DEFAULT_WATERMARK,
    NO_PAINT,
    OPAQUE,
    PRESETS,
    WATERMARK_INK,
    Chrome,
    Cursor,
    CursorShape,
)
from click_extra.capture.recording import TerminalScreen, record_and_render
from click_extra.capture.screenshot import (
    AUTO_COLUMNS,
    AUTO_TRUNCATION,
    AUTO_WRAP_MARKER,
    CAPTURE_HIDDEN_TERMINAL_VARS,
    CAPTURE_TERMINAL_HINTS,
    DEFAULT_COLUMNS,
    MIN_COLUMNS,
    TRUNCATION_LABEL,
    TRUNCATION_RULE,
    WRAP_MARKER_LABEL,
    CaptureFormat,
    append_prompt,
    auto_columns,
    capture,
    capture_environment,
    capture_output,
    parse_columns,
    render,
    resolve_wrap_marker,
    trim_lines,
)
from click_extra.capture.snippet import render_snippet
from click_extra.capture.svg import (
    _COLUMN_GAP_RE,
    _SHAPED_RE,
    _TILE_RUN,
    AUTO_HOLD,
    AUTO_HOLD_MAX,
    AUTO_HOLD_MIN,
    AUTO_HOLD_SECONDS_PER_LINE,
    BLOCK_ELEMENTS,
    BOX_ARMS,
    BOX_CURVES,
    BOX_DASHES,
    CELL_BLEED,
    CELL_WIDTH,
    CURSOR_THICKNESS,
    HIDDEN_GLYPH_ATTRIBUTES,
    LINE_HEIGHT,
    REDUCED_MOTION_QUERY,
    SHADE_DENSITY,
    TITLEBAR_HEIGHT,
    WATERMARK_INSET,
    WATERMARK_URL,
    _split_arguments,
    _tile_runs,
    auto_hold,
    blend,
    blink_css,
    box_strokes,
    braille_dots,
    column_segments,
    cursor_cell,
    frame_animation_css,
    gradient_svg,
    palette_color,
    parse_hold,
    parse_pause,
    render_svg,
    shape_runs,
    style_rules,
    window_buttons,
)
from click_extra.cli_capture import deliver_capture, screenshot_cmd
from click_extra.color import TerminalBackground
from click_extra.execution import PROMPT
from click_extra.layout import PADDING, cell_width, fit_columns, grid, number_lines
from click_extra.output import STDOUT_SENTINEL
from click_extra.styling import split_ansi

_TEXT_ELEMENT_RE = re.compile(r"<text(?P<attrs>[^>]*)>(?P<content>[^<]*)</text>")
"""One run of same-styled characters in a rendered capture.

Test-side only: the renderer builds these rather than reading them back, so the
pattern belongs to whatever wants to inspect its output.
"""

ASSETS = Path(__file__).parent.parent / "docs" / "assets"
"""Directory the committed captures live in."""

COMMITTED_PROMPT = "$ "
"""Prompt sigil every committed capture was shot under.

{data}`~click_extra.execution.PROMPT` is the *running* platform's, and Windows
draws `> ` there, so a reshoot has to be normalized back to this one before the
two are compared. What the check is about is the command's output, not which
shell drew the line above it.
"""


class Capture(NamedTuple):
    """A terminal capture committed under `docs/assets` and embedded in the docs.

    Carries what it takes to reshoot it, which is what makes the drift check
    below able to state the command each image is supposed to picture.
    """

    filename: str
    """Name of the SVG under {data}`ASSETS`."""

    args: tuple[str, ...]
    """Arguments the `click-extra` CLI was invoked with."""

    columns: int = 80
    """Terminal width it was shot at.

    A CLI wraps its output to the ambient terminal size, so a check running
    under a different width would compare a differently wrapped screen and fail
    on the wrapping alone.
    """

    head: int | None = None
    """Number of leading lines kept, or `None` when nothing was trimmed."""

    background: TerminalBackground = TerminalBackground.DARK
    """Chrome it was drawn on, which is also the terminal it was told it ran in."""

    @property
    def prompt(self) -> str:
        """The {data}`COMMITTED_PROMPT` line the capture draws above its output."""
        return f"{COMMITTED_PROMPT}click-extra {' '.join(self.args)}"

    @property
    def command(self) -> tuple[str, ...]:
        """The command line reproducing this capture through this interpreter.

        `docs/screenshots.md` documents the same commands reached through
        `uv run`, which is what a human types from a checkout. Going straight at
        {data}`sys.executable` keeps the check independent of uv, and of whether
        the environment happens to be synced.
        """
        return (sys.executable, "-m", "click_extra", *self.args)


COMMITTED_CAPTURES = (
    Capture("auto-theme-dark-screen.svg", ("--theme", "auto", "themes", "--help")),
    Capture(
        "auto-theme-light-screen.svg",
        ("--theme", "auto", "themes", "--help"),
        background=TerminalBackground.LIGHT,
    ),
    Capture("color-gradient-screen.svg", ("gradient",)),
    Capture("text-styles-screen.svg", ("styles",), columns=160, head=14),
    Capture("theme-gallery-screen.svg", ("themes",), head=34),
)
"""Every capture shot by the `screenshot` command, in file-name order.

The `hello-click*` pair opening the readme is not here: those are written by
the tutorial's own `click:run` blocks at documentation-build time, and guarded
by `tests/test_sphinx_crossrefs.py` instead.
"""


DARK_PALETTE = CAPTURE_PALETTES[TerminalBackground.DARK]
LIGHT_PALETTE = CAPTURE_PALETTES[TerminalBackground.LIGHT]

SAMPLE_CAPTURE = (
    "\x1b[1mFruit\x1b[0m   Colour\nbanana  yellow\nkiwi    green\n\n2 fruits\n"
)
"""A small styled capture, with padded columns and a blank line to preserve.

The second column is deliberately left unstyled: sharing a style with the
padding that precedes it is what folds the two into a single run, which is the
case that would otherwise place a column by the width of the spaces before it.
Style the column and the padding becomes a run of its own.
"""


def svg_to_lines(svg: str) -> list[str]:
    """Rebuild the captured terminal lines from a rendered capture.

    Groups the `<text>` runs into lines by their shared `y` baseline, then lays
    each one back on its column: the capture is monospaced, so dividing a run's
    `x` offset by {data}`~click_extra.capture.svg.CELL_WIDTH` gives the character
    column it starts at.

    :param svg: source of a rendered capture.
    :return: the captured lines, top to bottom, with trailing whitespace removed.
    """
    lines: dict[float, str] = {}
    for element in _TEXT_ELEMENT_RE.finditer(svg):
        # The credit line is the one run no terminal printed, and the one that
        # moves on its own: it names the release that drew the image.
        if 'class="watermark"' in element["attrs"]:
            continue
        content = unescape(element["content"]).replace("\N{NO-BREAK SPACE}", " ")
        offset = re.search(r'\bx="(?P<value>-?[\d.]+)"', element["attrs"])
        baseline = re.search(r'\by="(?P<value>-?[\d.]+)"', element["attrs"])
        if not content or not offset or not baseline:
            continue
        y = float(baseline["value"])
        column = round(float(offset["value"]) / CELL_WIDTH)
        lines[y] = lines.get(y, "").ljust(column) + content
    return [line.rstrip() for line in lines.values()]


def svg_box(svg: str) -> tuple[float, float]:
    """The width and height of a rendered capture's own box."""
    match = re.search(r'viewBox="0 0 (?P<width>[\d.]+) (?P<height>[\d.]+)"', svg)
    assert match
    return (float(match["width"]), float(match["height"]))


def svg_window(svg: str) -> tuple[float, float]:
    """The width and height of the terminal window drawn in a capture."""
    match = re.search(
        r'<rect [^>]*width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)" rx=', svg
    )
    assert match
    return (float(match["w"]), float(match["h"]))


def html_to_text(markup: str) -> str:
    """Strip a capture's markup back off, leaving the terminal text."""
    body = markup[markup.index("<pre") : markup.index("</pre>")]
    return unescape(re.sub(r"<[^>]+>", "", body))


@pytest.mark.parametrize(
    ("head", "tail", "expected"),
    (
        (None, None, ["one", "two", "three", "four"]),
        (1, None, ["one", "<cut>"]),
        (None, 1, ["<cut>", "four"]),
        (1, 1, ["one", "<cut>", "four"]),
        # Bounds wide enough to cover the whole text leave it alone, marker
        # included: nothing was cut, so nothing should claim otherwise.
        (4, None, ["one", "two", "three", "four"]),
        (2, 2, ["one", "two", "three", "four"]),
    ),
)
def test_trim_lines(head, tail, expected):
    """`head` and `tail` keep their ends and account for what they dropped."""
    trimmed = trim_lines(
        "one\ntwo\nthree\nfour", head=head, tail=tail, truncation="<cut>"
    )
    assert trimmed.splitlines() == expected


def test_trim_lines_rules_the_default_marker_across_the_picture():
    """The default marker is a rule, spanning the width the picture is laid out
    at: the widest kept line when the width is left to the command."""
    text = "\n".join(f"line {index} of the captured output" for index in range(1, 9))
    trimmed = trim_lines(text, head=2, tail=1, columns=AUTO_COLUMNS).splitlines()

    marker = unstyle(trimmed[2])
    assert marker.startswith(TRUNCATION_RULE)
    assert marker.endswith(TRUNCATION_RULE)
    assert f" {TRUNCATION_LABEL} " in marker
    # No brackets: a cut names nothing, unlike a rule heading a section.
    assert "[" not in marker
    # Painted to recede, the way the theme gallery rules its own screens.
    assert trimmed[2] != marker
    # Never the widest line: the marker must not be what decides image width.
    assert cell_width(marker) == max(cell_width(unstyle(line)) for line in trimmed)


def test_trim_lines_caps_the_rule_at_the_terminal_width():
    """A kept line wider than the capture draws a rule as wide as the capture.

    The rule is measured on the kept lines, so a 150-cell log line among them
    asked for a 150-cell rule in an 80-column image. The renderer folds any line
    reaching past the width, so that rule came back as a row of dots plus its
    tail alone on a second row, started outside the text column.
    """
    text = "\n".join((
        "short first line",
        "x" * 150,
        "short last line",
        "short line cut away",
    ))
    trimmed = trim_lines(text, head=2, tail=1, columns=80).splitlines()

    assert len(trimmed) == 4, "the rule folded onto a row of its own"
    marker = unstyle(trimmed[2])
    assert f" {TRUNCATION_LABEL} " in marker
    assert cell_width(marker) == 80


@pytest.mark.parametrize(
    ("columns", "width_floor", "expected"),
    (
        # Nothing folds when the width is left to the command, so the rule spans
        # the widest line the picture draws: a kept one, or the prompt.
        (AUTO_COLUMNS, 0, 150),
        (AUTO_COLUMNS, 170, 170),
        (80, 0, 80),
        # A pinned width the kept lines all stop short of: the rule still crosses
        # the whole window, as the cut does.
        (200, 0, 200),
        (200, 170, 200),
    ),
)
def test_rule_marker_tracks_the_drawn_width(columns, width_floor, expected):
    """The `auto` rule spans the text column the picture is drawn at."""
    text = "\n".join((
        "short first line",
        "x" * 150,
        "short last line",
        "short line cut away",
    ))
    trimmed = trim_lines(
        text, head=2, tail=1, columns=columns, width_floor=width_floor
    ).splitlines()
    assert cell_width(unstyle(trimmed[2])) == expected


@pytest.mark.parametrize(
    ("wrap_marker", "expected"),
    (
        (AUTO_WRAP_MARKER, WRAP_MARKER_LABEL),
        (WRAP_MARKER_LABEL, WRAP_MARKER_LABEL),
        ("\N{NOT SIGN}", "\N{NOT SIGN}"),
        ("", ""),
    ),
)
def test_resolve_wrap_marker(wrap_marker, expected):
    """Only `auto` is replaced: any other marker, empty included, is taken as is."""
    assert resolve_wrap_marker(wrap_marker) == expected


def test_trim_lines_leaves_room_for_the_wrap_marker():
    """A rule capped to the width gives up the cell a wrap marker takes.

    Capped to `columns` alone, the rule filled the row the marker shortens, so it
    folded on its last dot and closed its row on the marker, reading as a rule
    that continues below.
    """
    text = "\n".join((
        "short first line",
        "x" * 150,
        "short last line",
        "short line cut away",
    ))
    trimmed = trim_lines(
        text, head=2, tail=1, columns=80, wrap_marker=AUTO_WRAP_MARKER
    ).splitlines()
    assert cell_width(unstyle(trimmed[2])) == 79

    lines = svg_to_lines(
        render("\n".join(trimmed), columns=80, wrap_marker=AUTO_WRAP_MARKER)
    )
    rule_rows = [line for line in lines if TRUNCATION_LABEL in line]
    assert len(rule_rows) == 1
    assert not rule_rows[0].endswith(WRAP_MARKER_LABEL)
    assert not any(set(line) <= {TRUNCATION_RULE} for line in lines if line)


@pytest.mark.parametrize(
    ("prompt", "head", "tail"),
    (
        # Five rows, one digit to number them with.
        pytest.param("", 2, 2, id="one-digit"),
        # Nine rows of output and the prompt above them: the tenth row is the
        # one that widens the gutter by a digit.
        pytest.param("basket", 4, 4, id="prompt-adds-a-digit"),
    ),
)
def test_capture_leaves_room_for_line_numbers_on_the_rule(prompt, head, tail):
    """A numbered capture rules its cut inside the text column the gutter leaves.

    The gutter takes cells in front of every row, the rule's included, so a rule
    as wide as `columns` would fold on its last dots and put them alone on a row
    of their own.
    """
    command = [
        sys.executable,
        "-c",
        "print('\\n'.join(f'kiwi {n}' for n in range(30)))",
    ]
    document, _ = capture(
        command,
        columns=40,
        prompt=prompt,
        head=head,
        tail=tail,
        line_numbers=True,
        chrome=Chrome(watermark=""),
    )
    lines = svg_to_lines(document)

    assert len(lines) == bool(prompt) + head + 1 + tail, "the rule folded"
    rule_rows = [line for line in lines if TRUNCATION_LABEL in line]
    assert len(rule_rows) == 1
    assert cell_width(rule_rows[0]) == 40


def test_render_draws_the_wrap_marker_at_each_fold():
    """An SVG capture closes each folded row on the marker, and only those rows."""
    text = "apple\n" + "kiwi " * 10
    lines = svg_to_lines(render(text, columns=20, wrap_marker=AUTO_WRAP_MARKER))
    folded = [line for line in lines if line.endswith(WRAP_MARKER_LABEL)]
    assert len(folded) == 2
    assert all(cell_width(line) <= 20 for line in lines)
    assert lines[0] == "apple"
    # The default leaves a fold the way a terminal leaves it.
    assert WRAP_MARKER_LABEL not in "".join(svg_to_lines(render(text, columns=20)))


@pytest.mark.parametrize("truncation", (AUTO_TRUNCATION, "<cut>"))
def test_trim_lines_closes_a_style_the_cut_left_open(truncation):
    """A cut between a style's opening and its reset does not style the marker.

    A heading printed as `style("\\n● Step")` opens its style on the line above
    the text and resets it on the text's own line. Cut between the two, the open
    underline ran into the marker, and into the lines `tail` kept after it.
    """
    heading = style("\n\N{BLACK CIRCLE} Step", fg="bright_blue", underline=True)
    text = f"apple\nbanana\n{heading}\ncherry\ndate"
    trimmed = trim_lines(text, head=3, tail=1, truncation=truncation)

    # Read whole, so the state the head leaves open reaches what follows it. The
    # head keeps no underlined glyph: the heading's text is the line cut away.
    underlined = [run for run_style, run in split_ansi(trimmed) if run_style.underline]
    assert not any(run.strip() for run in underlined), underlined
    assert unstyle(trimmed).splitlines()[-1] == "date"


def test_trim_lines_adds_no_reset_after_a_closed_style():
    """A head that closes every style it opens gets its marker untouched."""
    text = "\n".join((style("apple", fg="green"), "banana", "cherry"))
    assert trim_lines(text, head=1, truncation="<cut>").splitlines()[1] == "<cut>"


def test_trim_lines_keeps_a_marker_too_wide_for_its_rule_bare():
    """A capture narrower than the frame gets the label alone, not a broken rule."""
    marker = trim_lines("a\nb\nc", head=1, tail=1, columns=AUTO_COLUMNS).splitlines()[1]
    assert unstyle(marker) == TRUNCATION_LABEL


def test_trim_lines_leaves_an_explicit_marker_alone():
    """Naming a marker takes it verbatim: only `auto` asks for a rule."""
    assert trim_lines("a\nb\nc", head=1, tail=1, truncation="<cut>").splitlines() == [
        "a",
        "<cut>",
        "c",
    ]


def test_tile_runs_never_opens_a_piece_on_padding():
    """A tiled column cut at a blank carries it into the piece before it.

    A piece is placed by its first glyph, so one opening on a blank draws every
    tile behind it a cell late. The cut is made on character count, which lands
    on a blank whenever a label sits inside a rule.
    """
    text = "─" * (_TILE_RUN - 1) + "[ x ]"
    assert list(_tile_runs(text, 0)) == [("─" * 7 + "[ ", 0), ("x ]", 9)]


def test_tile_runs_keeps_every_piece_on_its_own_column():
    """Cutting a tiled column apart never moves a glyph off its cell.

    The cut counts characters and the offset counts cells, which part ways on a
    wide character.
    """
    text = f"{'─' * 9}[ 苹果 ]{'─' * 9}"
    assert list(_tile_runs(text, 0)) == [
        ("─" * 8, 0),
        ("─[ 苹果 ]─", 8),
        ("─" * 8, 18),
    ]


@pytest.mark.parametrize("tile", ("─", "▀"), ids=("box-drawing", "block"))
def test_tile_runs_cuts_every_tile_it_was_released_with(tile):
    """`tile_runs` cuts Block Elements as well as Box Drawing, as `10.1.1` did.

    A capture draws both as shapes, which leaves the deprecated helper no caller
    in the renderer: its answer stays the released one until it goes. The cut
    is spelled out, so `TILE_RUN` keeping its released 8 cells is checked too.
    """
    assert _TILE_RUN == 8
    assert list(_tile_runs(tile * 10, 0)) == [(tile * 8, 0), (tile * 2, 8)]


@pytest.mark.parametrize(
    ("name", "private"),
    (
        ("tile_runs", "_tile_runs"),
        ("TILE_RUN", "_TILE_RUN"),
        ("_TILING_RE", "_TILE_RE"),
    ),
)
def test_tile_helpers_warn_until_their_removal(name, private):
    """The tile helpers a capture no longer uses still resolve, with a warning."""
    with pytest.warns(
        DeprecationWarning,
        match=(
            rf"^click_extra\.capture\.svg\.{name} is deprecated and will be "
            r"removed in click-extra 11\.0\.0: "
        ),
    ):
        value = getattr(capture_svg, name)
    assert value is getattr(capture_svg, private)


def test_svg_module_serves_no_other_missing_name():
    """A name the module never had stays missing, and sets off no warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert not hasattr(capture_svg, "tile_rune")


_GRID_RECT_RE = re.compile(
    r'<rect fill="(?P<fill>#[0-9a-f]{6})" x="(?P<x>[\d.]+)" y="(?P<y>[\d.]+)" '
    r'width="(?P<width>[\d.]+)" height="(?P<height>[\d.]+)" '
    r'shape-rendering="crispEdges"/>'
)
"""A rectangle drawn on the text grid: a cell's background, a cursor or a block."""

_NAMED_EIGHTHS = {
    "ONE EIGHTH": 1,
    "ONE QUARTER": 2,
    "THREE EIGHTHS": 3,
    "HALF": 4,
    "FIVE EIGHTHS": 5,
    "THREE QUARTERS": 6,
    "SEVEN EIGHTHS": 7,
}
"""Eighths of a cell each fraction in a Block Elements name stands for."""

_NAMED_QUADRANTS = {
    "UPPER LEFT": (0, 0),
    "UPPER RIGHT": (4, 0),
    "LOWER LEFT": (0, 4),
    "LOWER RIGHT": (4, 4),
}
"""Top-left corner, in eighths of a cell, of each quadrant a name lists."""


def named_eighths(char: str) -> set[tuple[int, int]]:
    """The eighths of its cell a Block Elements character fills, read off its name.

    A Unicode name states the shape outright, like `LOWER THREE EIGHTHS BLOCK`
    or `QUADRANT UPPER LEFT AND LOWER RIGHT`, which makes it a second source to
    hold {data}`~click_extra.capture.svg.BLOCK_ELEMENTS` against.
    """
    name = unicodedata.name(char)
    if name == "FULL BLOCK" or name.endswith(" SHADE"):
        return {(x, y) for x in range(8) for y in range(8)}
    if name.startswith("QUADRANT "):
        filled: set[tuple[int, int]] = set()
        for quadrant in name.removeprefix("QUADRANT ").split(" AND "):
            left, top = _NAMED_QUADRANTS[quadrant]
            filled |= {
                (x, y) for x in range(left, left + 4) for y in range(top, top + 4)
            }
        return filled
    side, _, fraction = name.removesuffix(" BLOCK").partition(" ")
    size = _NAMED_EIGHTHS[fraction]
    columns, rows = range(8), range(8)
    match side:
        case "UPPER":
            rows = range(size)
        case "LOWER":
            rows = range(8 - size, 8)
        case "LEFT":
            columns = range(size)
        case "RIGHT":
            columns = range(8 - size, 8)
    return {(x, y) for x in columns for y in rows}


def test_block_elements_cover_their_whole_unicode_block():
    """Every Block Elements character has a shape, and is one cell wide."""
    block = "".join(chr(code) for code in range(0x2580, 0x25A0))
    assert "".join(BLOCK_ELEMENTS) == block
    assert all(cell_width(char) == 1 for char in block)
    assert list(shape_runs(block, 0)) == [(block, 0, True)]
    assert {unicodedata.name(char): ink for char, ink in SHADE_DENSITY.items()} == {
        "LIGHT SHADE": 0.25,
        "MEDIUM SHADE": 0.5,
        "DARK SHADE": 0.75,
    }


@pytest.mark.parametrize("char", tuple(BLOCK_ELEMENTS))
def test_block_element_fills_what_its_name_states(char):
    """Each Block Elements character fills the part of its cell its name states."""
    drawn = {
        (x, y)
        for left, top, right, bottom in BLOCK_ELEMENTS[char]
        for x in range(left, right)
        for y in range(top, bottom)
    }
    assert drawn == named_eighths(char)


_ZWJ = "\N{ZERO WIDTH JOINER}"
"""Joins the character after it to the cluster before it, see `_SHAPED_RE`."""


@pytest.mark.parametrize(
    ("text", "column", "expected"),
    (
        ("apple", 0, [("apple", 0, False)]),
        ("▀▄█ apple", 0, [("▀▄█", 0, True), ("apple", 4, False)]),
        ("kiwi ▒▒", 2, [("kiwi", 2, False), ("▒▒", 7, True)]),
        ("┌─▄▄─┐", 0, [("┌─▄▄─┐", 0, True)]),
        ("│ kiwi │", 0, [("│", 0, True), ("kiwi", 2, False), ("│", 7, True)]),
        ("苹果 ██", 0, [("苹果", 0, False), ("██", 5, True)]),
        ("⠋ Picking apples", 0, [("⠋", 0, True), ("Picking apples", 2, False)]),
        ("▀⣿▄ kiwi", 3, [("▀⣿▄", 3, True), ("kiwi", 7, False)]),
        (f"x{_ZWJ}█ab", 0, [(f"x{_ZWJ}█ab", 0, False)]),
        (
            f"x{_ZWJ}██ab",
            0,
            [(f"x{_ZWJ}█", 0, False), ("█", 1, True), ("ab", 2, False)],
        ),
    ),
)
def test_shape_runs_cut_shapes_from_the_text_between(text, column, expected):
    """Shapes are cut out on their own columns, and nothing else.

    Box Drawing, Block Elements and Braille patterns are drawn as shapes. One
    following a zero width joiner belongs to the cluster before it, and stays in
    its text.
    """
    assert list(shape_runs(text, column)) == expected


@pytest.mark.parametrize(
    "text",
    (
        "▀▄█ apple",
        "│ kiwi │",
        "苹果 ██",
        "⠋ Picking apples",
        f"x{_ZWJ}█ab",
        f"x{_ZWJ}⣿ kiwi",
        f"🍑{_ZWJ}─┐ pear",
        f"█{_ZWJ}█",
        f"plum {_ZWJ}▀▄",
    ),
)
def test_shape_runs_place_each_piece_where_cell_width_counts_it(text):
    """Each piece starts on the column `cell_width` counts up to it.

    `cell_width` counts the character after a zero width joiner in the cluster
    before it. A shape cut out of that cluster would push the text after it a
    cell past its column, onto the run the grid places next.
    """
    pieces = list(shape_runs(text, 0))
    position = 0
    for piece, column, _ in pieces:
        index = text.index(piece, position)
        assert column == cell_width(text[:index]), piece
        position = index + len(piece)
    last_piece, last_column, _ = pieces[-1]
    assert last_column + cell_width(last_piece) == cell_width(text)


_BRAILLE_DOT_PLACES = {
    1: (0, 0),
    2: (0, 1),
    3: (0, 2),
    4: (1, 0),
    5: (1, 1),
    6: (1, 2),
    7: (0, 3),
    8: (1, 3),
}
"""Where each numbered dot of a Braille cell sits, as the Unicode charts lay it out."""


@pytest.mark.parametrize(
    "code", range(0x2800, 0x2900), ids=lambda code: f"U+{code:04X}"
)
def test_braille_dots_match_their_unicode_names(code):
    """Each Braille pattern raises the dots its Unicode name lists."""
    char = chr(code)
    name = unicodedata.name(char)
    numbers = name.removeprefix("BRAILLE PATTERN DOTS-")
    if name == "BRAILLE PATTERN BLANK":
        numbers = ""
    assert set(braille_dots(char)) == {
        _BRAILLE_DOT_PLACES[int(number)] for number in numbers
    }
    assert list(shape_runs(char, 0)) == [(char, 0, True)]
    assert cell_width(char) == 1


def test_braille_dots_keep_one_pitch_across_cells():
    """Two stacked rows of full Braille cells plot one even grid of dots.

    The dot positions are rounded to a tenth of a pixel, the precision every
    coordinate of a capture is written at.
    """
    full = chr(0x28FF)
    # No title bar, whose window buttons are circles too.
    svg = render_svg(f"{full}{full}\n{full}{full}", columns=4, collapse_titlebar=True)
    dots = [
        (float(x), float(y))
        for x, y in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', svg)
    ]
    assert len(dots) == 32
    for axis, count in ((0, 4), (1, 8)):
        positions = sorted({dot[axis] for dot in dots})
        assert len(positions) == count
        for step in (after - before for before, after in pairwise(positions)):
            assert step == pytest.approx(CELL_WIDTH / 2, abs=0.11)


_BOX_WEIGHTS = {"LIGHT": 1, "SINGLE": 1, "HEAVY": 2, "DOUBLE": 3}
"""Weight each word of a Box Drawing name stands for, see `BOX_ARMS`."""

_BOX_DIRECTIONS = {
    "UP": ("up",),
    "RIGHT": ("right",),
    "DOWN": ("down",),
    "LEFT": ("left",),
    "VERTICAL": ("up", "down"),
    "HORIZONTAL": ("left", "right"),
}
"""Arms each direction word of a Box Drawing name stands for."""

_BOX_DASH_COUNTS = {"DOUBLE": 2, "TRIPLE": 3, "QUADRUPLE": 4}
"""Dashes each count word of a dashed Box Drawing name stands for."""


def named_arms(char: str) -> tuple[int, ...]:
    """The arms of a Box Drawing line, read off its Unicode name.

    A name states one weight for all its arms, as in `LIGHT DOWN AND RIGHT`, or
    one per group of arms, as in `DOWN LIGHT AND RIGHT HEAVY`.
    """
    name = unicodedata.name(char).removeprefix("BOX DRAWINGS ")
    groups = [group.split() for group in name.split(" AND ")]
    shared = next(
        _BOX_WEIGHTS[word] for group in groups for word in group if word in _BOX_WEIGHTS
    )
    arms = dict.fromkeys(("up", "right", "down", "left"), 0)
    for group in groups:
        weight = next(
            (_BOX_WEIGHTS[word] for word in group if word in _BOX_WEIGHTS), shared
        )
        for word in group:
            for arm in _BOX_DIRECTIONS.get(word, ()):
                arms[arm] = weight
    return tuple(arms.values())


def test_box_drawing_covers_its_whole_unicode_block():
    """Every Box Drawing character is a line, a dash or a curve, one cell wide."""
    block = "".join(chr(code) for code in range(0x2500, 0x2580))
    kinds = (BOX_ARMS, BOX_DASHES, BOX_CURVES)
    assert sorted(char for kind in kinds for char in kind) == list(block)
    assert all(cell_width(char) == 1 for char in block)
    assert list(shape_runs(block, 0)) == [(block, 0, True)]
    for char in BOX_CURVES:
        assert {"ARC", "DIAGONAL"} & set(unicodedata.name(char).split())


@pytest.mark.parametrize("char", tuple(BOX_ARMS))
def test_box_arms_match_their_unicode_names(char):
    """Each Box Drawing line has the arms and weights its Unicode name lists."""
    assert BOX_ARMS[char] == named_arms(char)


@pytest.mark.parametrize("char", tuple(BOX_DASHES))
def test_box_dashes_match_their_unicode_names(char):
    """Each dashed line runs the way, weighs and counts what its name says."""
    words = unicodedata.name(char).split()
    vertical, weight, dashes = BOX_DASHES[char]
    assert vertical == ("VERTICAL" in words)
    assert weight == _BOX_WEIGHTS[words[2]]
    assert dashes == _BOX_DASH_COUNTS[words[3]]


@pytest.mark.parametrize(
    ("char", "expected"),
    (
        pytest.param("─", {(False, 15, 17, 0, 16)}, id="light-horizontal"),
        pytest.param("┃", {(True, 6, 10, 0, 32)}, id="heavy-vertical"),
        pytest.param(
            "┼", {(False, 15, 17, 0, 16), (True, 7, 9, 0, 32)}, id="light-cross"
        ),
        pytest.param(
            "┌", {(False, 15, 17, 7, 16), (True, 7, 9, 15, 32)}, id="light-corner"
        ),
        pytest.param(
            "═", {(False, 13, 15, 0, 16), (False, 17, 19, 0, 16)}, id="double"
        ),
        # The outer stroke turns the outer corner, the inner one the inner corner.
        pytest.param(
            "╔",
            {
                (False, 13, 15, 5, 16),
                (False, 17, 19, 9, 16),
                (True, 5, 7, 13, 32),
                (True, 9, 11, 17, 32),
            },
            id="double-corner",
        ),
        # The top stroke runs on, the bottom one stops at the gap below it.
        pytest.param(
            "╦",
            {
                (False, 13, 15, 0, 16),
                (False, 17, 19, 0, 7),
                (False, 17, 19, 9, 16),
                (True, 5, 7, 17, 32),
                (True, 9, 11, 17, 32),
            },
            id="double-tee",
        ),
        # A single line ending on a double one stops at its nearer stroke.
        pytest.param(
            "╤",
            {(False, 13, 15, 0, 16), (False, 17, 19, 0, 16), (True, 7, 9, 17, 32)},
            id="single-on-double",
        ),
        # A single line passing through crosses the double line's gap.
        pytest.param(
            "╪",
            {(False, 13, 15, 0, 16), (False, 17, 19, 0, 16), (True, 7, 9, 0, 32)},
            id="single-through-double",
        ),
    ),
)
def test_box_strokes_join_as_menlo_draws_them(char, expected):
    """A line's strokes meet where Menlo `22.0d2e1` joins them."""
    assert set(box_strokes(char)) == expected


def test_double_cross_leaves_its_gaps_open():
    """No stroke of `╬` crosses into the gaps between its double lines."""
    for _, low, high, start, end in box_strokes("╬"):
        assert not (start < 16 < end and low < 8 < high)
        assert not (start < 8 < end and low < 16 < high)


def test_box_rule_is_one_shape_and_its_lines_meet_across_rows():
    """A rule merges across its cells, and a vertical line runs on into the next row."""
    svg = render_svg("──────\n│\n│", columns=8, collapse_titlebar=True)
    rects = sorted(
        (float(rect["y"]), float(rect["height"]), float(rect["width"]))
        for rect in _GRID_RECT_RE.finditer(svg)
    )
    assert len(rects) == 3
    (_, _, rule_width), (upper_y, upper_height, _), (lower_y, _, _) = rects
    assert rule_width == pytest.approx(6 * CELL_WIDTH, abs=0.05)
    assert upper_y + upper_height >= lower_y


def test_blank_braille_draws_nothing_and_keeps_its_text():
    """The blank pattern raises no dot, and still reads back as itself."""
    text = f"{chr(0x2800)}apple"
    svg = render_svg(text, columns=10, collapse_titlebar=True)
    assert "<circle" not in svg
    assert svg_to_lines(svg) == [text]


def test_stacked_blocks_leave_no_gap():
    """Two rows of full blocks paint one unbroken column, whatever the font.

    A font draws `█` shorter than a capture's row, so the same picture set as
    glyphs leaves a band of background between the two rows.
    """
    svg = render_svg("█\n█", columns=4)
    (upper_top, upper_bottom), (lower_top, lower_bottom) = sorted(
        (float(rect["y"]), float(rect["y"]) + float(rect["height"]))
        for rect in _GRID_RECT_RE.finditer(svg)
    )
    assert upper_bottom >= lower_top
    assert lower_bottom - upper_top >= 2 * LINE_HEIGHT


def test_half_block_splits_its_cell_in_the_middle():
    """`▀` inks the top half of its cell and leaves the bottom to the background."""
    svg = render_svg(style("▀", fg=(255, 255, 255), bg=(0, 0, 128)), columns=4)
    drawn = {rect["fill"]: rect for rect in _GRID_RECT_RE.finditer(svg)}
    ink, paper = drawn["#ffffff"], drawn["#000080"]
    assert ink["y"] == paper["y"]
    assert float(ink["height"]) == pytest.approx(LINE_HEIGHT / 2, abs=0.05)
    assert float(paper["height"]) == pytest.approx(LINE_HEIGHT + CELL_BLEED, abs=0.05)


def test_block_run_is_one_shape():
    """A bar of `█` is one rectangle, not one per cell."""
    svg = render_svg("████████", columns=10)
    (bar,) = _GRID_RECT_RE.finditer(svg)
    assert float(bar["width"]) == pytest.approx(8 * CELL_WIDTH, abs=0.05)


def test_shade_mixes_its_ink_with_the_paper():
    """`▒` is half ink, mixed into the color behind it."""
    svg = render_svg(style("▒", fg=(255, 255, 255), bg=(0, 0, 0)), columns=4)
    assert {rect["fill"] for rect in _GRID_RECT_RE.finditer(svg)} == {
        "#000000",
        "#808080",
    }


def test_shapes_stay_in_the_text():
    """A run drawn as shapes keeps its characters, as text that paints nothing."""
    text = "▀▄█ apple\n░▒▓  pear\n⠋ plum"
    svg = render_svg(text, columns=20)
    assert svg_to_lines(svg) == text.split("\n")
    for element in _TEXT_ELEMENT_RE.finditer(svg):
        shaped = bool(_SHAPED_RE.search(unescape(element["content"])))
        assert shaped == (HIDDEN_GLYPH_ATTRIBUTES in element["attrs"])


def test_no_committed_capture_draws_shapes_as_glyphs():
    """No committed capture draws Box Drawing, Block Elements or Braille as glyphs.

    A capture written before the renderer did still shows a seam at the joins of
    its box drawing, a band between its stacked rows of block art, or Braille
    wider than its column. Rewrite it the way its page documents: a recording, by
    deleting it and building again.
    """
    for path in sorted(ASSETS.glob("*.svg")):
        svg = path.read_text(encoding="UTF-8")
        if "@generated by" not in svg:
            continue
        for element in _TEXT_ELEMENT_RE.finditer(svg):
            content = unescape(element["content"])
            if _SHAPED_RE.search(content):
                assert HIDDEN_GLYPH_ATTRIBUTES in element["attrs"], (
                    f"{path.name}: {content!r} drawn as glyphs"
                )


@pytest.mark.parametrize(
    ("sgr", "expected"),
    (
        ("4", "text-decoration: underline"),
        ("53", "text-decoration: overline"),
        ("9", "text-decoration: line-through"),
        ("4;9", "text-decoration: underline line-through"),
        ("4;53;9", "text-decoration: underline overline line-through"),
    ),
)
def test_style_rules_writes_one_declaration_per_property(sgr, expected):
    """Every decoration reaches the CSS, and the three share one declaration.

    CSS keeps the last of a repeated property, so a run written as two
    `text-decoration` declarations loses all but one of them. `overline` had no
    branch at all, which left the column of `click-extra styles` naming it
    identical to the plain one in every viewer.
    """
    style = next(iter(split_ansi(f"\x1b[{sgr}mx\x1b[0m")))[0]
    rules = style_rules(style, next(iter(CAPTURE_PALETTES.values())))
    assert expected in rules
    assert rules.count("text-decoration") == 1


def test_render_folds_an_unusable_unique_id():
    """A file name that is not a CSS identifier cannot leak into a class name."""
    svg = render(SAMPLE_CAPTURE, unique_id="my shot (v2).final")
    assert "my-shot-v2-.final" not in svg
    assert 'class="my-shot-v2-final-r1"' in svg


def test_render_places_every_run_on_its_own_column():
    """Rebuilding the terminal text from a capture gives the text back.

    Each run is placed by its `x` offset alone, so laying the runs back on the
    columns that offset names has to reproduce what the terminal printed.
    """
    # A blank line draws no glyph, so it carries no baseline to group runs on.
    assert svg_to_lines(render_svg(SAMPLE_CAPTURE, columns=40)) == [
        line for line in unstyle(SAMPLE_CAPTURE).rstrip("\n").split("\n") if line
    ]


def test_no_run_starts_on_padding():
    """No visible run in a capture is positioned by the spaces preceding it.

    The invariant the column arithmetic exists for: a renderer that ignores
    `textLength` or cannot resolve the font still lands every run where it
    belongs. Checked against every committed capture as well as a fresh render,
    so a regression cannot hide in the assets or in the renderer alone.
    """
    pads = tuple(PADDING)
    captures = {
        committed.filename: (ASSETS / committed.filename).read_text(encoding="UTF-8")
        for committed in COMMITTED_CAPTURES
    }
    captures["<fresh>"] = render_svg(SAMPLE_CAPTURE, columns=40)
    for name, svg in captures.items():
        for element in _TEXT_ELEMENT_RE.finditer(svg):
            content = unescape(element["content"])
            assert content.strip(PADDING), f"{name}: run carrying no glyph"
            assert not content.startswith(pads), f"{name}: padded run {content!r}"


def test_capture_clip_holds_every_descender():
    """The terminal's clip is never shorter than the text it contains.

    A clip cropped to the text block's height minus a pixel cuts the descenders
    off the last line, turning an underscore into a blank. Checked against every
    committed capture, which is where such a crop would go unnoticed.
    """
    for committed in COMMITTED_CAPTURES:
        svg = (ASSETS / committed.filename).read_text(encoding="UTF-8")
        clip = re.search(
            r'<clipPath id="[^"]+-clip"><rect x="[\d.]+" y="[\d.]+" '
            r'width="[\d.]+" height="(?P<height>[\d.]+)"',
            svg,
        )
        assert clip, f"{committed.filename}: no terminal clip"
        # Only the terminal's own runs: the caption and the credit line are
        # drawn outside the clipped group, in the image's own coordinates.
        lowest = max(
            float(y)
            for y in re.findall(r'<text class="[^"]+-r\d+"[^>]*\by="([\d.]+)"', svg)
        )
        assert float(clip["height"]) >= lowest, (
            f"{committed.filename}: clip crops the last line"
        )


def test_no_capture_references_a_missing_clip():
    """Every `clip-path` a capture uses resolves to a `clipPath` it defines.

    A dangling reference is rendered inconsistently: a browser drops the clip, a
    strict SVG 1.1 renderer drops the whole element with it.
    """
    for committed in COMMITTED_CAPTURES:
        svg = (ASSETS / committed.filename).read_text(encoding="UTF-8")
        defined = set(re.findall(r'<clipPath id="([^"]+)">', svg))
        referenced = set(re.findall(r'clip-path="url\(#([^)]+)\)"', svg))
        assert not referenced - defined, (
            f"{committed.filename}: dangling {sorted(referenced - defined)}"
        )


ANIMATION_PRESETS = tuple(sorted(SPINNERS))
"""Every bundled spinner: the population an animated capture is checked over."""


def animated_capture(name: str) -> str:
    """Draw one bundled spinner as an animated capture."""
    preset = SPINNERS[name]
    spinner = Spinner("Steeping", spinner=preset, style=Style(fg="green"))
    return render_svg(
        columns=40,
        title=name,
        unique_id=f"spin-{name}",
        frames=spinner.frame_lines(),
        interval=preset.interval,
    )


def stylesheet_of(svg: str) -> str:
    """The `<style>` block of a rendered capture."""
    found = re.search(r"<style>(.*?)</style>", svg, re.DOTALL)
    assert found, "a capture always carries a stylesheet"
    return found.group(1)


def claimed_names(svg: str) -> set[str]:
    """Every name a capture's stylesheet claims in the scope of a whole page.

    Class selectors and keyframe names both: inlined into one HTML document,
    the stylesheets of two captures are global and share that scope.
    """
    stylesheet = stylesheet_of(svg)
    return set(re.findall(r"\.([\w-]+)\s*\{", stylesheet)) | set(
        re.findall(r"@keyframes ([\w-]+)", stylesheet)
    )


@pytest.mark.parametrize("name", ANIMATION_PRESETS)
def test_animated_capture_defines_every_class_it_uses(name):
    """No frame names a class its capture's stylesheet leaves undefined.

    An undefined class does not blank its frame: the text falls back to the
    presentation attributes and draws in a default face in the window's own ink.
    The animation then appears to reset its styling once a cycle, only the
    frames carrying a rule looking right.
    """
    svg = animated_capture(name)
    undefined = set(re.findall(r'class="([\w-]+)"', svg)) - claimed_names(svg)
    assert not undefined, f"{name}: undefined {sorted(undefined)}"


@pytest.mark.parametrize("name", ANIMATION_PRESETS)
def test_animated_capture_draws_its_chrome_once(name):
    """The window, its caption and its clip path are drawn once, not per frame."""
    svg = animated_capture(name)
    assert svg.count("<clipPath") == 1
    assert svg.count('-title"') == 1


@pytest.mark.parametrize("name", ANIMATION_PRESETS)
def test_animation_windows_tile_the_cycle(name):
    """Each frame's window abuts the next, covering the cycle exactly once.

    A gap leaves the picture blank for part of every turn; an overlap draws two
    frames on top of each other.
    """
    windows = []
    for keyframes in re.findall(
        r"@keyframes [\w-]+ \{ (.*?) \}\n", animated_capture(name)
    ):
        steps = [
            (float(at), state)
            for at, state in re.findall(r"([\d.]+)% \{ visibility: (\w+);", keyframes)
        ]
        opens = next(at for at, state in steps if state == "visible")
        closes = next(at for at, state in steps if state == "hidden" and at > opens)
        windows.append((opens, closes))

    windows.sort()
    assert windows[0][0] == pytest.approx(0.0), f"{name}: the cycle opens on no frame"
    assert windows[-1][1] == pytest.approx(100.0), f"{name}: the cycle ends on no frame"
    for (_, closes), (opens, _) in pairwise(windows):
        assert closes == opens, f"{name}: {closes}% to {opens}% is a gap or an overlap"


def test_animated_capture_draws_a_row_that_never_moves_once():
    """A row identical in every frame is drawn outside them, not once per frame.

    On a recording where one line moves under a screen of lines that do not,
    this is the difference between one copy of that screen and one per frame.
    """
    still = "\n".join(f"shelf {index} holds pears" for index in range(4))
    frames = [f"{still}\ncrate {index}" for index in range(5)]
    svg = render_svg(columns=40, unique_id="pantry", frames=frames, interval=0.1)

    assert len(re.findall(r'class="pantry-f\d+"', svg)) == 5
    # The rows that never move are drawn once, ahead of the first frame.
    assert svg.count("shelf") == 4
    head = svg[: svg.index('<g class="pantry-f0"')]
    assert head.count("shelf") == 4
    # Each frame carries the one row that does move, and nothing else.
    assert svg.count("crate") == 5


def test_animated_capture_keeps_a_row_that_moves_in_every_frame():
    """Nothing is shared when every row differs, which is the spinner's case."""
    frames = [f"pear {index}" for index in range(4)]
    svg = render_svg(columns=20, unique_id="one", frames=frames, interval=0.1)

    head = svg[: svg.index('<g class="one-f0"')]
    assert "pear" not in head, "a moving row was drawn outside the frames"
    assert svg.count("pear") == 4


BAND_GROUP_RE = re.compile(r'<g clip-path="url\(#[\w-]+-window\)">(.*?)</g>')
"""The group holding every band, clipped to the window rather than to the text."""


def bands_of(svg: str) -> list[tuple[str, float]]:
    """The paint and baseline of each band an emphasized capture draws."""
    group = BAND_GROUP_RE.search(svg)
    if not group:
        return []
    return [
        (fill, float(offset))
        for fill, offset in re.findall(
            r'<rect fill="(#[0-9a-f]+)"[^>]*\by="([\d.]+)"', group.group(1)
        )
    ]


def test_emphasized_lines_are_banded_where_they_sit():
    """A band lands on the row it names, counted from one, and spans the window.

    Edge to edge rather than stopping where the padding does: the row is what
    is emphasized, not the column of text sitting in it.
    """
    text = "\n".join(f"crate {index}" for index in range(1, 6))
    bands = bands_of(render_svg(text, columns=20, emphasize=(1, 3)))

    assert len(bands) == 2
    offsets = sorted(offset for _, offset in bands)
    # Two rows apart, so two line heights apart on the canvas.
    assert offsets[1] - offsets[0] == pytest.approx(2 * LINE_HEIGHT)

    svg = render_svg(
        text,
        columns=20,
        emphasize=(1,),
        chrome=replace(BARE_CHROME, margin=40, padding=12),
    )
    window = re.search(
        r'<rect fill="#[0-9a-f]+" stroke="[^"]*"[^>]*x="([\d.]+)"'
        r'[^>]*width="([\d.]+)"',
        svg,
    )
    band = re.search(r'-window\)">.*?<rect[^>]*x="([\d.]+)"[^>]*width="([\d.]+)"', svg)
    assert window and band
    assert band.groups() == window.groups(), "a band is as wide as the window"


def test_emphasis_is_mixed_from_the_chrome_it_is_drawn_on():
    """One ratio answers for both chromes: lighter on dark, darker on light."""
    text = "crate 1\ncrate 2"
    shades = {}
    for background in TerminalBackground:
        svg = render_svg(
            text,
            columns=20,
            emphasize=(1,),
            palette=CAPTURE_PALETTES[background],
        )
        ((fill, _),) = bands_of(svg)
        shades[background] = fill

    assert shades[TerminalBackground.DARK] != shades[TerminalBackground.LIGHT]
    # Neither band is the background it sits on, or it would not read as one.
    for background, fill in shades.items():
        assert fill != CAPTURE_PALETTES[background].background


def test_emphasis_rejects_a_line_the_capture_does_not_have():
    """Naming a line past the end is an authoring error, not a silent no-op."""
    with pytest.raises(ValueError, match="emphasize line 7 of a capture 2 lines"):
        render_svg("crate 1\ncrate 2", columns=20, emphasize=(7,))


def test_screenshot_reports_a_line_the_capture_does_not_have(invoke, tmp_path):
    """The command reports the authoring error as one, not as a traceback.

    The height of a capture is only known once its command has run, so the
    renderer is the one to refuse a band past its end, and the command turns that
    refusal into its own error message.
    """
    result = invoke(
        screenshot_cmd,
        [
            "--emphasize-lines",
            "99",
            "--prompt",
            "pantry",
            "--output",
            str(tmp_path / "shot.svg"),
            "--",
            sys.executable,
            "-c",
            "print('pear')",
        ],
    )
    assert result.exit_code == 1
    assert "Error: Cannot emphasize line 99 of a capture 2 lines long." in (
        result.output
    )
    assert not (tmp_path / "shot.svg").exists()


FRAME_BAND_RE = re.compile(
    r'<g class="([\w-]+)-f(\d+)"[^>]*clip-path="url\(#[\w-]+-window\)">(.*?)</g>'
)
"""A band group riding one frame of an animation."""


def banded_frames(svg: str) -> set[int]:
    """Which frames of an animated capture draw a band."""
    return {
        int(index) for _, index, drawn in FRAME_BAND_RE.findall(svg) if "<rect" in drawn
    }


def test_emphasis_arrives_with_the_row_it_marks():
    """A band shows in the frame that first draws its row, and not before.

    Waiting in empty space for the animation to reach it reads as a stray
    rectangle. Arriving with the row is also the moment a gutter would first
    number that row, so the two land together.
    """
    frames = (
        "one pear",
        "one pear\ntwo pears",
        "one pear\ntwo pears\nthree pears",
    )
    svg = render_svg(
        columns=20, unique_id="grow", frames=frames, interval=0.1, emphasize=(3,)
    )

    assert banded_frames(svg) == {2}, "only a frame holding a third row is banded"


def test_emphasis_leaves_a_closing_blank_alone():
    """The empty beat closing a cycle draws no band, having drawn no row."""
    svg = render_svg(
        columns=20,
        unique_id="beat",
        frames=("one pear", "two pears"),
        interval=0.1,
        blank=0.5,
        emphasize=(1,),
    )

    # Two frames of content are banded; the blank third is not.
    assert banded_frames(svg) == {0, 1}


def test_two_animations_share_no_selector():
    """Two animated captures inlined in one page keep their own timing.

    Both stylesheets are global there. A selector they share hands the shorter
    animation the longer one's clock, and the frames it does not have go blank
    for that part of every cycle.
    """
    names = ("dots", "moon", "bouncing-bar")
    claimed = {name: claimed_names(animated_capture(name)) for name in names}
    for first, second in combinations(names, 2):
        shared = claimed[first] & claimed[second]
        assert not shared, f"{first} and {second} share {sorted(shared)}"


def test_frame_animation_css_only_ever_animates():
    """Every rule the timing emits sits behind the reduced-motion guard.

    Nothing here hides a frame: that is the frames' own `visibility` attribute,
    which is what a renderer reading no stylesheet still honors. A reader asking
    their system for less motion therefore lands on the same still as one whose
    viewer speaks no CSS animation at all.
    """
    css = frame_animation_css("teapot", (0.1, 0.1, 0.1))
    assert css.lstrip().startswith(REDUCED_MOTION_QUERY)
    assert "@keyframes" in css
    assert "animation:" in css
    # No rule outlives the guard, which closes on the stylesheet's last brace.
    assert css.rstrip().endswith("}")
    assert "visibility: hidden;" not in css.split(REDUCED_MOTION_QUERY, 1)[0]


@pytest.mark.parametrize("name", ("bouncing-bar", "dots", "moon"))
def test_animated_capture_hides_its_frames_outside_the_stylesheet(name):
    """Every frame but the poster is hidden by an attribute, not by a rule.

    A renderer free to ignore `<style>` would otherwise draw all of them at
    once, stacked on top of each other. The poster is the last frame, which on
    an animation that accumulates is the one that says the most.
    """
    svg = animated_capture(name)
    frames = re.findall(r'<g class="spin-[\w-]+-f(\d+)"([^>]*)>', svg)
    assert frames
    shown = [index for index, attrs in frames if not attrs]
    assert shown == [str(len(frames) - 1)], "exactly the last frame is the poster"
    # Both properties, because renderers have been seen honoring one only.
    for index, attrs in frames:
        if index in shown:
            continue
        assert 'visibility="hidden"' in attrs, index
        assert 'opacity="0"' in attrs, index


@pytest.mark.parametrize("name", ("bouncing-bar", "dots", "moon"))
def test_animated_capture_renders_the_same_bytes_twice(name):
    """An unchanged animation rewrites byte-identical bytes.

    What lets a committed asset be regenerated on every build without dirtying
    the working tree.
    """
    assert animated_capture(name) == animated_capture(name)


def test_animated_capture_needs_an_interval():
    with pytest.raises(ValueError, match="how long a frame lasts"):
        render_svg(columns=20, frames=("one pear", "two pears"))


def test_animated_capture_counts_its_durations():
    with pytest.raises(ValueError, match="2 frames carry 1 durations"):
        render_svg(columns=20, frames=("one pear", "two pears"), interval=(0.1,))


def test_animated_capture_rejects_a_frame_lasting_no_time():
    with pytest.raises(ValueError, match="positive time"):
        render_svg(columns=20, frames=("one pear", "two pears"), interval=(0.1, 0))


@pytest.mark.parametrize(
    ("picture", "expected"),
    (
        pytest.param("apricot", (0, 7), id="after-the-last-glyph"),
        pytest.param("apricot\n", (1, 0), id="a-newline-starts-the-next-row"),
        pytest.param("apricot\nbiscuit", (1, 7), id="on-the-last-row"),
        pytest.param("\x1b[36mapricot\x1b[0m", (0, 7), id="escapes-occupy-no-cell"),
        pytest.param("\u6771\u4eac", (0, 4), id="a-wide-glyph-covers-two-cells"),
        pytest.param("a" * 20, (1, 0), id="past-the-last-column-it-wraps"),
        pytest.param("", None, id="an-empty-screen-shows-none"),
        pytest.param("   \n  ", None, id="a-blank-screen-shows-none"),
    ),
)
def test_cursor_cell_reads_the_screen_it_is_given(picture, expected):
    """A frame's text already says where the terminal left its cursor."""
    assert cursor_cell(picture, 20) == expected


def test_cursor_cell_matches_the_screen_that_wrote_it():
    """The derived column is the one the screen itself counted, not an estimate.

    Locks the claim {func}`~click_extra.capture.svg.cursor_cell` rests on: a
    recorded frame carries its cursor position implicitly, so nothing has to
    travel beside the text to say where the cursor was.
    """
    screen = TerminalScreen()
    for written in (
        "\x1b[36m\u280b Picking apples\x1b[0m",
        "\r\x1b[K",
        "Filled basket 0\r\n",
        "\x1b[36m\u2819 Picking apples\x1b[0m",
    ):
        screen.feed(written)
        standing = cursor_cell(screen.display, DEFAULT_COLUMNS)
        column = 0 if standing is None else standing[1]
        assert column == screen._column, f"after {written!r}"


def cursor_rect(svg: str) -> tuple[float, float, float, float]:
    """The cursor a capture drew, as its x, y, width and height.

    Found by its `crispEdges` rendering, which the text of these tests carries
    on nothing else: they draw unstyled words, so no run brings a background
    rectangle of its own. The count is asserted rather than assumed, so a test
    picture that grows a styled run fails here instead of measuring the wrong
    rectangle.
    """
    drawn = re.findall(
        r'<rect[^>]*x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"'
        r' shape-rendering="crispEdges"/>',
        svg,
    )
    assert len(drawn) == 1, f"expected one cursor, found {len(drawn)}"
    return tuple(float(number) for number in drawn[0])  # type: ignore[return-value]


def test_a_capture_draws_no_cursor_unless_asked():
    """The default is no cursor, which is what every committed asset shows."""
    svg = render_svg("apricot", columns=20, unique_id="basket")
    assert "basket-blink" not in svg
    assert 'shape-rendering="crispEdges"' not in svg


@pytest.mark.parametrize(
    ("shape", "width", "height"),
    (
        pytest.param(
            CursorShape.BLOCK, CELL_WIDTH, LINE_HEIGHT + CELL_BLEED, id="block"
        ),
        pytest.param(
            CursorShape.BAR, CURSOR_THICKNESS, LINE_HEIGHT + CELL_BLEED, id="bar"
        ),
        pytest.param(
            CursorShape.UNDERLINE, CELL_WIDTH, CURSOR_THICKNESS, id="underline"
        ),
    ),
)
def test_cursor_is_drawn_in_the_shape_it_names(shape, width, height):
    """Each shape covers the part of its cell that shape is."""
    left, _top, drawn_width, drawn_height = cursor_rect(
        render_svg(
            "apricot", columns=20, unique_id="basket", cursor=Cursor(shape, blink=0)
        )
    )
    # A capture writes its coordinates to a tenth of a pixel, see `_svg_number`.
    assert left == pytest.approx(7 * CELL_WIDTH, abs=0.05)
    assert drawn_width == pytest.approx(width, abs=0.05)
    assert drawn_height == pytest.approx(height, abs=0.05)


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_a_shapeless_cursor_takes_the_terminal_its_preset_names(name):
    """`--preset windows` draws Windows Terminal's bar without stating it."""
    _left, _top, drawn_width, _height = cursor_rect(
        render(
            text="apricot",
            columns=20,
            unique_id="basket",
            preset=PRESETS[name],
            cursor=Cursor(blink=0),
        )
    )
    expected = (
        CURSOR_THICKNESS if PRESETS[name].cursor is CursorShape.BAR else CELL_WIDTH
    )
    assert drawn_width == pytest.approx(expected, abs=0.05)


def test_a_cursor_under_the_output_grows_the_window_by_that_line():
    """Output closing on a newline leaves the cursor on the row underneath."""
    settled = render_svg("apricot", columns=20, unique_id="basket", cursor=Cursor())
    wrapped = render_svg("apricot\n", columns=20, unique_id="basket", cursor=Cursor())
    assert svg_box(wrapped)[1] - svg_box(settled)[1] == pytest.approx(LINE_HEIGHT)


def test_a_cursor_does_not_move_what_emphasize_may_mark():
    """A band picks out a line of output, and a cursor draws no line."""
    for cursor in (None, Cursor()):
        with pytest.raises(ValueError, match="1 lines long"):
            render_svg(
                "apricot\n",
                columns=20,
                unique_id="basket",
                emphasize=(2,),
                cursor=cursor,
            )


def test_an_animated_cursor_blinks_on_one_clock():
    """One rule and one keyframe set, however many frames carry a cursor.

    A terminal has one cursor. Namespacing the blink per frame would instead
    let each copy light on its own beat, which reads as several cursors.
    """
    svg = render_svg(
        columns=20,
        unique_id="basket",
        frames=("one", "two", "three"),
        interval=0.2,
        cursor=Cursor(),
    )
    assert svg.count("@keyframes basket-blink") == 1
    assert svg.count(".basket-blink { animation:") == 1
    assert svg.count('<rect class="basket-blink"') == 3


def test_the_blank_closing_a_cycle_shows_no_cursor():
    """An empty terminal has nothing to put a cursor on."""
    svg = render_svg(
        columns=20,
        unique_id="basket",
        frames=("one", "two"),
        interval=0.2,
        blank=0.5,
        cursor=Cursor(),
    )
    assert svg.count('<rect class="basket-blink"') == 2


def test_a_steady_cursor_names_no_class():
    """A class the stylesheet never defines is what breaks a renderer."""
    svg = render_svg("apricot", columns=20, unique_id="basket", cursor=Cursor(blink=0))
    assert "basket-blink" not in svg


def test_a_blinking_cursor_sits_behind_the_reduced_motion_guard():
    """Blinking is motion, and a reader may have asked for less of it."""
    svg = render_svg("apricot", columns=20, unique_id="basket", cursor=Cursor())
    assert svg.index(REDUCED_MOTION_QUERY) < svg.index("@keyframes basket-blink")


def test_a_blink_never_touches_visibility():
    """Opacity multiplies into a hidden frame's group; visibility would override it.

    A frame is hidden by `visibility` *and* `opacity` together, and `visibility`
    is inherited: a cursor restoring it would show through every frame at once,
    which is the whole reason the blink dims opacity alone.
    """
    assert "visibility" not in blink_css("basket", 1.0)


def test_blink_css_rejects_a_blink_going_nowhere():
    """A cursor blinking in no time is a cursor that never lights."""
    with pytest.raises(ValueError, match="positive time"):
        blink_css("basket", 0)


def test_a_capture_rejects_a_cursor_blinking_backwards():
    """Seconds run forwards, here as everywhere else."""
    with pytest.raises(ValueError, match="not a blink"):
        render_svg("apricot", columns=20, cursor=Cursor(blink=-1))


@pytest.mark.parametrize(
    ("arguments", "message"),
    (
        pytest.param(["--blink", "1"], "--blink requires --cursor.", id="blink"),
        pytest.param(["--typing", "0.05"], "--typing requires --record.", id="typing"),
        pytest.param(
            ["--record", "--columns", "40", "--submit", "0.4"],
            "--submit requires --typing.",
            id="submit",
        ),
    ),
)
def test_screenshot_cursor_options_need_their_partner(
    invoke, tmp_path, arguments, message
):
    """Each knob names the one it decorates, rather than passing unnoticed."""
    result = invoke(
        screenshot_cmd,
        [*arguments, "--output", str(tmp_path / "shot.svg"), "--", "echo"],
    )
    assert result.exit_code != 0
    assert message in result.output


def test_screenshot_draws_a_cursor_when_asked(invoke, tmp_path):
    """`--cursor` puts one on a still capture, blinking on one clock."""
    target = tmp_path / "shelf.svg"
    result = invoke(
        screenshot_cmd,
        [
            "--cursor",
            "--output",
            str(target),
            "--",
            sys.executable,
            "-c",
            "print('ok')",
        ],
    )
    assert result.exit_code == 0, result.output
    svg = target.read_text(encoding="UTF-8")
    assert svg.count("@keyframes shelf-blink") == 1
    assert svg.count('<rect class="shelf-blink"') == 1


def test_screenshot_draws_no_cursor_unless_asked(invoke, tmp_path):
    """The default is what every capture taken before the option showed."""
    target = tmp_path / "shelf.svg"
    result = invoke(
        screenshot_cmd,
        ["--output", str(target), "--", sys.executable, "-c", "print('ok')"],
    )
    assert result.exit_code == 0, result.output
    assert "shelf-blink" not in target.read_text(encoding="UTF-8")


@pytest.mark.parametrize(
    ("shape", "width"),
    (
        pytest.param("block", CELL_WIDTH, id="block"),
        pytest.param("bar", CURSOR_THICKNESS, id="bar"),
        pytest.param("underline", CELL_WIDTH, id="underline"),
    ),
)
def test_screenshot_cursor_takes_the_shape_it_names(invoke, tmp_path, shape, width):
    """A named shape overrides whatever the terminal preset would have drawn."""
    target = tmp_path / "shelf.svg"
    result = invoke(
        screenshot_cmd,
        [
            "--cursor",
            shape,
            "--blink",
            "0",
            "--preset",
            "windows",
            "--output",
            str(target),
            "--",
            sys.executable,
            "-c",
            "print('ok')",
        ],
    )
    assert result.exit_code == 0, result.output
    assert cursor_rect(target.read_text(encoding="UTF-8"))[2] == pytest.approx(
        width, abs=0.05
    )


def test_screenshot_bare_cursor_takes_the_preset_shape(invoke, tmp_path):
    """`--cursor` alone draws Windows Terminal's bar under `--preset windows`."""
    target = tmp_path / "shelf.svg"
    result = invoke(
        screenshot_cmd,
        [
            "--cursor",
            "--blink",
            "0",
            "--preset",
            "windows",
            "--output",
            str(target),
            "--",
            sys.executable,
            "-c",
            "print('ok')",
        ],
    )
    assert result.exit_code == 0, result.output
    assert cursor_rect(target.read_text(encoding="UTF-8"))[2] == pytest.approx(
        CURSOR_THICKNESS, abs=0.05
    )


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_screenshot_record_types_its_prompt(invoke, tmp_path):
    """`--typing` opens the recording on the command line being typed."""
    counts = {}
    for name, extra in (("plain", []), ("typed", ["--typing", "0.05"])):
        target = tmp_path / f"{name}.svg"
        result = invoke(
            screenshot_cmd,
            [
                "--record",
                "--columns",
                "40",
                *extra,
                "--prompt",
                "basket ripen",
                "--output",
                str(target),
                "--",
                sys.executable,
                "-c",
                "print('ripe')",
            ],
        )
        assert result.exit_code == 0, result.output
        found = re.search(r"frames=(\d+)", target.read_text(encoding="UTF-8"))
        assert found
        counts[name] = int(found.group(1))

    typed_length = len(f"{PROMPT}basket ripen")
    # Every typed character is a frame, so the opening cannot be shorter than
    # the line. The exact count belongs to type_line and is pinned there, by
    # test_type_line_makes_one_frame_per_character: what this covers is that a
    # real recording gets that opening prepended.
    assert counts["typed"] >= typed_length
    # Typing only ever adds frames to the front of a recording.
    assert counts["typed"] > counts["plain"]
    # The difference is deliberately not pinned. Only the typing frames are
    # deterministic: how many frames the wrapped command itself records depends
    # on when its output lands, and a loaded runner splits it one more time than
    # an idle one does.


def test_auto_columns_leaves_room_for_a_cursor():
    """An auto width derives from the text, which always ends on its last cell.

    Without the extra cell the cursor wraps onto a row of its own, which is a
    row holding nothing but a cursor.
    """
    # Longer than MIN_COLUMNS, which floors an auto width on its own.
    shelf = "apricots, biscuits and coffee"
    assert auto_columns((shelf,)) == len(shelf)
    assert auto_columns((shelf,), Cursor()) == len(shelf) + 1
    # A picture closing on a newline puts the cursor at column zero instead,
    # which the text's own width already covers.
    assert auto_columns((f"{shelf}\n",), Cursor()) == len(shelf)


@pytest.mark.parametrize("picture", ("", "\n\n"))
def test_auto_columns_with_a_cursor_on_a_blank_screen(picture):
    """A blank screen shows no cursor, and leaves the width to its floor.

    No frame placing a cursor left `max()` with the width alone to compare,
    which raised `TypeError: 'int' object is not iterable` for a command
    printing nothing under `--prompt ""`.
    """
    assert auto_columns((picture,), Cursor()) == MIN_COLUMNS
    svg = render(picture, columns=AUTO_COLUMNS, cursor=Cursor())
    assert svg.startswith("<?xml")


def test_a_closing_prompt_belongs_to_the_last_frame_alone():
    """Closing every frame would say the command exited before it had.

    Counted rather than located, the sigil landing on a different row in each
    frame of an animation that grows. A row drawn the same in every frame is
    drawn once, so an unclosed animation shows its opening sigil a single time
    and each closed frame adds one of its own: measured at 1, 2 and 5 here.
    """
    sigil = PROMPT.strip()
    opening = f"{Style(fg='bright_black')(sigil)} basket ripen"
    frames = tuple(f"{opening}\n{bar}" for bar in ("[", "[#", "[##", "[###\nripe\n"))
    # Windows draws `>` there, which the SVG spells as a character reference.
    drawn = f">{escape(sigil, quote=False)}</text>"

    def sigils(pictures):
        return render_svg(
            columns=30,
            unique_id="orchard",
            frames=pictures,
            interval=0.1,
            cursor=Cursor(),
        ).count(drawn)

    assert sigils(frames) == 1
    assert sigils((*frames[:-1], append_prompt(frames[-1]))) == 2
    assert sigils(tuple(append_prompt(frame) for frame in frames)) == 5


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        pytest.param(
            "shelved\n", f"shelved\n{PROMPT}", id="fills-the-row-the-newline-opened"
        ),
        pytest.param("shelved", f"shelved\n{PROMPT}", id="opens-a-row-when-mid-line"),
        pytest.param("", f"\n{PROMPT}", id="an-empty-screen-still-prompts"),
    ),
)
def test_append_prompt_closes_a_finished_screen(text, expected):
    """The shell comes back on the row under the output, and on no other."""
    assert unstyle(append_prompt(text)) == expected


def test_append_prompt_takes_the_sigil_its_preset_draws():
    """A capture of Windows Terminal closes on the shell that terminal runs."""
    closed = unstyle(append_prompt("shelved", preset=PRESETS["windows"]))
    assert closed == "shelved\nPS C:\\> "


def test_a_closing_prompt_costs_no_height_beside_a_cursor():
    """The cursor already claimed that row: the prompt only fills it.

    What makes the pair worth having. A cursor alone leaves a row holding
    nothing, and the sigil turns it into the shell waiting.
    """
    output = "shelved 4 crates\n"

    def height(text: str, cursor: Cursor | None) -> float:
        return svg_box(render_svg(text, columns=40, unique_id="shelf", cursor=cursor))[
            1
        ]

    bare = height(output, None)
    with_cursor = height(output, Cursor())
    assert with_cursor - bare == pytest.approx(LINE_HEIGHT)
    assert height(append_prompt(output), Cursor()) == pytest.approx(with_cursor)


def test_screenshot_closes_a_still_with_a_prompt(invoke, tmp_path):
    """`--closing-prompt` draws the shell coming back under the output."""
    target = tmp_path / "shelf.svg"
    result = invoke(
        screenshot_cmd,
        [
            "--closing-prompt",
            "--output",
            str(target),
            "--",
            sys.executable,
            "-c",
            "print('shelved')",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (
        svg_to_lines(target.read_text(encoding="UTF-8"))[-1].strip() == PROMPT.strip()
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        pytest.param("ripe", AUTO_HOLD_MIN, id="a-single-line-gets-the-floor"),
        pytest.param(
            "\n".join(f"row {index}" for index in range(40)),
            40 * AUTO_HOLD_SECONDS_PER_LINE,
            id="a-report-scales-by-its-lines",
        ),
        pytest.param("fig\n" * 500, AUTO_HOLD_MAX, id="a-dump-hits-the-ceiling"),
        pytest.param(
            "\x1b[32m\u2713\x1b[0m ripe\n\n   \n",
            AUTO_HOLD_MIN,
            id="escapes-and-blank-rows-are-not-lines",
        ),
    ),
)
def test_auto_hold_scales_with_the_final_screen(text, expected):
    """The pause follows the populated lines of the closing screen."""
    assert auto_hold(text) == expected


def test_animated_capture_resolves_an_auto_hold():
    """`hold="auto"` renders exactly as the resolved pause would."""
    frames = ("one pear", "one pear\ntwo pears")
    auto = render_svg(
        columns=20, unique_id="pause", frames=frames, interval=0.1, hold=AUTO_HOLD
    )
    fixed = render_svg(
        columns=20,
        unique_id="pause",
        frames=frames,
        interval=0.1,
        hold=auto_hold(frames[-1]),
    )
    assert auto == fixed


def test_animated_capture_rejects_an_unknown_hold_word():
    """A word the annotation forbids still has to fail loudly at runtime."""
    with pytest.raises(ValueError, match="not a hold"):
        render_svg(
            columns=20,
            frames=("one pear", "two pears"),
            interval=0.1,
            hold="forever",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "pause",
    (
        pytest.param({"hold": -0.05}, id="hold"),
        pytest.param({"blank": -1}, id="blank"),
    ),
)
def test_animated_capture_rejects_a_negative_pause(pause):
    """A pause runs forward or not at all, whichever end of the cycle it sits on."""
    with pytest.raises(ValueError, match="is not a pause, which is never negative"):
        render_svg(columns=20, frames=("one pear", "two pears"), interval=0.1, **pause)


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("auto", AUTO_HOLD),
        (" Auto ", AUTO_HOLD),
        ("2.5", 2.5),
        ("0", 0.0),
    ),
)
def test_parse_hold(value, expected):
    """A hold is seconds, or the one word asking the final screen to decide."""
    assert parse_hold(value) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    (
        ("forever", "'forever' is not a hold, which is seconds or 'auto'."),
        ("-1", "-1.0 is not a pause, which is never negative."),
    ),
)
def test_parse_hold_rejects(value, message):
    """A hold that is neither seconds nor `auto` says what it would take."""
    with pytest.raises(ValueError, match=re.escape(message)):
        parse_hold(value)


@pytest.mark.parametrize(("value", "expected"), (("0.5", 0.5), ("0", 0.0)))
def test_parse_pause(value, expected):
    """A pause is seconds, zero included."""
    assert parse_pause(value) == expected


def test_parse_pause_rejects_a_negative_one():
    with pytest.raises(ValueError, match="is not a pause, which is never negative"):
        parse_pause("-0.5")


def test_html_capture_does_not_animate():
    """An HTML capture is selectable text, which has no frame to hide.

    The refusal names the format the way a reader writes it, not as the
    `CaptureFormat.HTML` member it is held in.
    """
    with pytest.raises(ValueError, match=r"^HTML captures do not animate\.$"):
        render(
            format=CaptureFormat.HTML,
            frames=("one pear", "two pears"),
            interval=0.1,
        )


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        # A gutter of two blanks or more separates one column from the next.
        ("苹果        apple", [("苹果", 0), ("apple", 12)]),
        (
            "--count INTEGER  Number of greetings.",
            [
                ("--count INTEGER", 0),
                ("Number of greetings.", 17),
            ],
        ),
        # A single blank is a word break inside a phrase, and stays put.
        ("$ market", [("$ market", 0)]),
        ("± ≈ ∞ → ★", [("± ≈ ∞ → ★", 0)]),
        # Leading and trailing padding is an offset, never a glyph.
        ("   indented", [("indented", 3)]),
        ("trailing   ", [("trailing", 0)]),
        ("", []),
        ("      ", []),
        # Three columns, the middle one wide.
        ("a  水果  z", [("a", 0), ("水果", 3), ("z", 9)]),
    ),
)
def test_column_segments(text, expected):
    """A run is cut at its gutters, and each column carries the one it starts on."""
    assert list(column_segments(text, 0)) == expected


def test_no_capture_places_a_column_by_its_padding():
    """No column in a capture is positioned by the blanks in front of it.

    The invariant that lets a capture survive a renderer ignoring `textLength`:
    `librsvg` (and through it `rsvg-convert` and ImageMagick) lays every run out
    at the font's natural width, so a gutter paid for in glyphs collapses and
    the columns slide onto each other. Each column carrying its own `x` asks the
    renderer for nothing but coordinates.
    """
    captures = {
        committed.filename: (ASSETS / committed.filename).read_text(encoding="UTF-8")
        for committed in COMMITTED_CAPTURES
    }
    captures["<fresh>"] = render_svg(SAMPLE_CAPTURE, columns=40)
    for name, svg in captures.items():
        for element in _TEXT_ELEMENT_RE.finditer(svg):
            content = unescape(element["content"])
            assert not _COLUMN_GAP_RE.search(content), (
                f"{name}: run holds a gutter its glyphs pay for: {content!r}"
            )


def test_no_capture_clips_through_a_transform():
    """The element a capture's clip is hung on carries no transform of its own.

    A `clipPath` in `userSpaceOnUse` resolves against "the user coordinate
    system in place when it is referenced", and renderers disagree over whether
    the referencing element's own `transform` counts. Hung on a translated
    group, the two readings differ by the translation, and the one that ignores
    it crops the text partway down the window: what macOS Finder's thumbnailer
    does.
    """
    for committed in COMMITTED_CAPTURES:
        svg = (ASSETS / committed.filename).read_text(encoding="UTF-8")
        for element in re.finditer(r"<g [^>]*clip-path=[^>]*>", svg):
            assert "transform=" not in element[0], (
                f"{committed.filename}: clip resolved through a transform"
            )


def test_no_capture_hangs_a_filter_on_its_window():
    """The window's own rectangle carries no filter.

    An element whose filter a renderer cannot resolve is an element in error,
    which the spec answers by not rendering it at all. Hung on the window, a
    filter costs the background, the frame and the shadow together and leaves
    the text floating on the page: what macOS Finder's thumbnailer and
    ImageMagick both do with a capture built that way.
    """
    for committed in COMMITTED_CAPTURES:
        svg = (ASSETS / committed.filename).read_text(encoding="UTF-8")
        palette = CAPTURE_PALETTES[committed.background]
        for element in re.finditer(r"<rect [^>]*/>", svg):
            if f'fill="{palette.background}"' in element[0]:
                assert "filter=" not in element[0], (
                    f"{committed.filename}: the window would vanish with its filter"
                )


def test_capture_states_its_font_outside_the_stylesheet():
    """The terminal text names its face, size and color as attributes too.

    A renderer is free to ignore a `<style>` block, and several do. The text
    then falls back to a proportional face at a default size in default black,
    which is a terminal capture with neither its grid nor its colors.
    """
    for committed in COMMITTED_CAPTURES:
        svg = (ASSETS / committed.filename).read_text(encoding="UTF-8")
        matrix = re.search(r"<g class=\"[^\"]+-matrix\"[^>]*>", svg)
        assert matrix, f"{committed.filename}: no text group"
        for attribute in ("font-family", "font-size", "fill"):
            assert f"{attribute}=" in matrix[0], (
                f"{committed.filename}: text group leaves {attribute} to the stylesheet"
            )


def test_every_capture_declares_its_encoding():
    """A capture states UTF-8 outright rather than leaving it to be guessed.

    A standalone SVG carries no HTTP header to say so. XML defaults to UTF-8
    with no declaration, but WebKit applies its HTML fallback to the document
    encoding instead, which renders every multi-byte character as mojibake: a
    full block becomes `â`, and a capture of colored output becomes a wall of
    accented letters in macOS Quick Look.
    """
    for committed in COMMITTED_CAPTURES:
        raw = (ASSETS / committed.filename).read_bytes()
        assert raw.startswith(b'<?xml version="1.0" encoding="UTF-8"?>'), (
            f"{committed.filename}: no encoding declared"
        )


def test_no_capture_fetches_a_font():
    """A capture resolves its fonts locally, or falls back down its own stack.

    A committed image is read offline, on a page forbidding third-party
    requests, and by renderers that speak no `@font-face`.
    """
    for committed in COMMITTED_CAPTURES:
        svg = (ASSETS / committed.filename).read_text(encoding="UTF-8")
        assert "@font-face" not in svg, f"{committed.filename}: embeds a webfont"
        # The XML namespace is a URI, not a request: only a fetched resource
        # reaches the network, and every one of those is spelled `url(...)`.
        assert not re.search(r"url\(\s*[\"']?https?:", svg), (
            f"{committed.filename}: fetches over the network"
        )


@pytest.mark.parametrize(
    ("text", "characters", "cells"),
    (
        ("apples", 6, 6),
        ("水果", 2, 4),
        ("水果 apples", 9, 11),
        ("", 0, 0),
    ),
)
def test_wide_glyphs_are_sized_by_cell(text, characters, cells):
    """A run is drawn as wide as the cells it occupies, not its character count.

    A CJK ideograph takes two terminal cells, so sizing a run by `len()` squeezes
    it to half its width and stacks the glyphs on each other.
    """
    assert len(text) == characters
    assert cell_width(text) == cells
    if not text:
        return
    svg = render_svg(text, columns=40)
    run = re.search(r'<text[^>]*textLength="(?P<length>[\d.]+)"', svg)
    assert run
    assert float(run["length"]) == pytest.approx(cells * CELL_WIDTH)


def test_capture_output_forces_color_and_pins_width(monkeypatch):
    """A capture overrides the environment's color opt-out and terminal width."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "999")

    process = capture_output(
        [
            sys.executable,
            "-c",
            (
                "import os; print(os.environ['FORCE_COLOR'], os.environ['COLUMNS'], "
                "os.environ.get('NO_COLOR', 'cleared'))"
            ),
        ],
        columns=57,
    )

    assert process.returncode == 0
    assert process.stdout.split() == ["1", "57", "cleared"]
    # The override is scoped to the capture and restored on the way out.
    assert os.environ["NO_COLOR"] == "1"


@pytest.mark.parametrize("background", TerminalBackground)
def test_capture_output_states_the_terminal_it_simulates(background, monkeypatch):
    """The chrome reaches the command as the variables a terminal would set.

    Which is what lets a CLI asking for `--theme auto` render for the window its
    capture lands in, instead of falling back to dark inside a light one.
    """
    monkeypatch.delenv("CLITHEME", raising=False)
    monkeypatch.delenv("COLORFGBG", raising=False)

    process = capture_output(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ['CLITHEME'], os.environ['COLORFGBG'])",
        ],
        background=background,
    )
    hints = CAPTURE_TERMINAL_HINTS[background]
    assert process.stdout.split() == [hints["CLITHEME"], hints["COLORFGBG"]]


@pytest.mark.parametrize("variable", CAPTURE_HIDDEN_TERMINAL_VARS)
def test_capture_output_hides_the_terminal_it_runs_from(variable, monkeypatch):
    """The terminal taking the capture never reaches the command captured.

    Left through, a command tailoring its output to that terminal draws one
    picture on the machine that took the capture and another everywhere else,
    which no committed asset survives.
    """
    monkeypatch.setenv(variable, "Some_Terminal")

    process = capture_output(
        [
            sys.executable,
            "-c",
            f"import os; print(os.environ.get({variable!r}, '<unset>'))",
        ],
    )
    assert process.stdout.strip() == "<unset>"


def test_capture_output_keeps_stderr_out_unless_asked():
    """Only `stdout` is captured by default, so a wrapper's chatter stays out."""
    args = [
        sys.executable,
        "-c",
        "import sys; print('kept'); print('noise', file=sys.stderr)",
    ]
    assert capture_output(args).stdout.split() == ["kept"]
    assert sorted(capture_output(args, merge_stderr=True).stdout.split()) == [
        "kept",
        "noise",
    ]


CAPTURE_CLICK_VERSION = (8, 5)
"""Click release whose help layout the committed captures picture.

Click ``8.5.0`` gave positional arguments a section of their own, reshaping
every help screen it renders. A capture is a picture of one Click's output, so
the matrix cells pinning an older Click inside the supported range compare it
against a screen that never carried that section. The `Click released` cells
still check every committed capture, which is where the check belongs.
"""


@pytest.mark.parametrize(
    "committed",
    COMMITTED_CAPTURES,
    ids=tuple(committed.filename for committed in COMMITTED_CAPTURES),
)
@pytest.mark.skipif(
    tuple(int(p) for p in importlib.metadata.version("click").split(".")[:2])
    < CAPTURE_CLICK_VERSION,
    reason="Committed captures picture the Click 8.5 help layout.",
)
def test_committed_capture_matches_cli(committed):
    """Every committed capture still pictures what its command prints today.

    The capture is reshot through {func}`~click_extra.capture.screenshot.capture`,
    the very pipeline that produced the committed file, and the two are compared
    as terminal text. Going through the whole pipeline rather than against the
    command's raw output is what keeps the check honest on both counts the two
    differ:

    - a command wrapping to an 80-column terminal is handed
      `min(columns, max_width) - 2`, while Click's own `CliRunner` pins
      `FORCED_WIDTH` to 80, so an in-process render sits two columns wider;
    - the renderer folds a line longer than the terminal, exactly as a terminal
      does, so a help screen carrying an unwrappable option list (`--table-format`
      and its 463-character choice list) occupies more rows in the image than the
      command printed.

    Only the text is compared, so restyling a theme does not redden this.
    """
    source = (ASSETS / committed.filename).read_text(encoding="UTF-8")

    fresh, returncode = capture(
        list(committed.command),
        columns=committed.columns,
        prompt=committed.prompt.removeprefix(COMMITTED_PROMPT),
        head=committed.head,
        background=committed.background,
    )
    assert returncode == 0
    fresh_lines = svg_to_lines(fresh)
    if fresh_lines:
        fresh_lines[0] = COMMITTED_PROMPT + fresh_lines[0].removeprefix(PROMPT)
    assert svg_to_lines(source) == fresh_lines


@pytest.mark.parametrize(
    ("filename", "expected"),
    (
        ("shot.svg", CaptureFormat.SVG),
        ("shot.SVG", CaptureFormat.SVG),
        ("shot.html", CaptureFormat.HTML),
        # The older extension names the same document.
        ("shot.htm", CaptureFormat.HTML),
        ("shot.ansi", CaptureFormat.ANSI),
        # The one destination stating no extension: the terminal itself.
        (STDOUT_SENTINEL, CaptureFormat.ANSI),
    ),
)
def test_capture_format_from_path(filename, expected):
    """A capture's format is read off the file name it is written under."""
    assert CaptureFormat.from_path(Path(filename)) == expected


@pytest.mark.parametrize("filename", ("shot.png", "shot", "shot.svg.bak"))
def test_capture_format_from_path_rejects_an_unknown_extension(filename):
    """An extension naming no format says which ones do."""
    with pytest.raises(ValueError, match=r"\.ansi, \.html, \.svg"):
        CaptureFormat.from_path(Path(filename))


def test_capture_format_from_path_reads_a_file_named_dash_as_a_file(tmp_path):
    """Only a bare `-` is the terminal: a file called `-` has an extension to lack.

    `--output ./-` reaches here resolved to an absolute path, and the file it
    names is as nameable as any other.
    """
    with pytest.raises(ValueError, match="Cannot tell the capture format of '-'"):
        CaptureFormat.from_path(tmp_path / "-")


def test_deliver_capture_writes_a_file_named_dash(tmp_path, capsys):
    """A resolved `-` is a file to write, not the terminal to print on."""
    target = tmp_path / "-"
    deliver_capture("one pear\n", target)
    assert target.read_text(encoding="UTF-8") == "one pear\n"
    assert capsys.readouterr().out == f"Wrote {target}\n"


def test_screenshot_does_not_print_a_resolved_dash(invoke):
    """`--output ./-` is a file in the working directory, which names no format.

    Click resolves it to an absolute path whose last component is `-`, which is
    not the bare `-` naming the terminal.
    """
    result = invoke(screenshot_cmd, ["--output", "./-", "--", "echo", "pear"])
    assert result.exit_code != 0
    assert "Cannot tell the capture format of '-'" in result.output
    assert "pear" not in result.stdout


@pytest.mark.parametrize(
    ("background", "expected", "unwanted"),
    (
        (
            TerminalBackground.DARK,
            (DARK_PALETTE.background, DARK_PALETTE.foreground),
            (LIGHT_PALETTE.background,),
        ),
        (
            TerminalBackground.LIGHT,
            (LIGHT_PALETTE.background, LIGHT_PALETTE.foreground),
            (DARK_PALETTE.background,),
        ),
    ),
    ids=("dark", "light"),
)
@pytest.mark.parametrize("format", (CaptureFormat.HTML, CaptureFormat.SVG))
def test_render_draws_on_the_chrome_it_is_given(format, background, expected, unwanted):
    """Both renderers answer to the chrome, so a light capture stays readable.

    The colors are the contract: an SVG paints its window rect with them, and an
    HTML capture inlines them on its `<pre>`.
    """
    document = render("kiwi", format=format, background=background)
    for color in expected:
        assert color in document
    for color in unwanted:
        assert color not in document


@pytest.mark.parametrize("background", TerminalBackground)
def test_render_frames_with_a_border_its_chrome_can_show(background):
    """Each chrome frames its window in something its own background shows.

    The regression this guards is a light capture keeping the translucent white
    a dark renderer draws by default: a white window on a white page, whose
    shape is left for the reader to infer from the text inside it.
    """
    svg = render("kiwi", unique_id="fruit", background=background)
    assert f'stroke="{CAPTURE_BORDERS[background]}"' in svg
    assert f'flood-color="{CAPTURE_SHADOWS[background]}"' in svg


@pytest.mark.parametrize("background", tuple(TerminalBackground))
def test_chrome_resolves_what_the_capture_draws(background):
    """`None` fields take the background's and the preset's own; stated ones stay."""
    resolved = Chrome().resolve(background, None)
    assert resolved.border == CAPTURE_BORDERS[background]
    assert resolved.shadow == CAPTURE_SHADOWS[background]
    assert resolved.radius == DEFAULT_RADIUS
    assert resolved.watermark_color == WATERMARK_INK
    windows = PRESETS["windows"]
    assert Chrome().resolve(background, windows).radius == windows.radius
    stated = Chrome(border="red", radius=3, shadow=NO_PAINT, watermark_color="blue")
    assert stated.resolve(background, windows) == stated


@pytest.mark.parametrize(
    "function", (render, capture, record_and_render, render_snippet)
)
def test_capture_functions_take_one_chrome(function):
    """The window is one `chrome` argument everywhere, with one default."""
    parameters = inspect.signature(function).parameters
    assert parameters["chrome"].default == Chrome()
    assert not {field.name for field in fields(Chrome)} & set(parameters)


@pytest.mark.parametrize("renderer", (render_svg, render_html))
def test_renderers_take_one_resolved_chrome(renderer):
    """The two renderers take the window as one chrome, bare unless stated.

    A renderer draws the values it is given, so it refuses a chrome still
    carrying a `None` that only {meth}`~click_extra.capture.presets.Chrome.resolve`
    can fill.
    """
    parameters = inspect.signature(renderer).parameters
    assert parameters["chrome"].default == BARE_CHROME
    assert not {field.name for field in fields(Chrome)} & set(parameters)
    width = {"columns": 20} if renderer is render_svg else {}
    with pytest.raises(ValueError, match="border, radius, shadow, watermark_color"):
        renderer("kiwi", chrome=Chrome(), **width)


@pytest.mark.parametrize("background", tuple(TerminalBackground))
def test_bare_chrome_is_resolved(background):
    """The renderers' default draws as it stands: resolving it changes nothing."""
    BARE_CHROME.check_resolved()
    assert BARE_CHROME.resolve(background, None) == BARE_CHROME


def test_render_rejects_an_unknown_argument():
    """A typo is still refused, as a signature naming every argument would."""
    with pytest.raises(TypeError, match="unexpected keyword argument 'marign'"):
        render("kiwi", marign=0)  # type: ignore[call-arg]


def test_render_paints_what_it_is_given():
    """A caller's own frame and shadow reach the window."""
    svg = render("kiwi", unique_id="fruit", chrome=Chrome(border="red", shadow="blue"))
    assert 'stroke="red"' in svg
    assert 'flood-color="blue"' in svg
    assert 'filter="url(#fruit-shadow)"' in svg


def test_render_states_the_whole_window():
    """Corner radius, frame thickness, backdrop and title all reach the source."""
    svg = render(
        "kiwi",
        unique_id="fruit",
        title="caption",
        chrome=Chrome(border="red", border_width=3, radius=0, backdrop="#1f6feb"),
    )
    assert 'stroke-width="3"' in svg
    assert 'rx="0"' in svg
    assert '<rect fill="#1f6feb" x="0" y="0"' in svg
    # Drawn centered in the window's title bar, by the renderer itself.
    assert '<text class="fruit-title"' in svg
    assert 'text-anchor="middle"' in svg
    assert "caption" in svg
    # The backdrop covers the image, margin included, and sits under the window.
    assert svg.index('fill="#1f6feb"') < svg.index('stroke="red"')


@pytest.mark.parametrize(
    ("backdrop", "expected"),
    (
        # A plain color is left for the `fill` attribute to take verbatim.
        ("#1f6feb", None),
        ("rebeccapurple", None),
        ("rgba(0, 0, 0, 0.5)", None),
        # A gradient needs two stops to interpolate between.
        ("linear-gradient(#000)", None),
        ("linear-gradient(45deg)", None),
        # Both shapes, opening with an angle, a side, or nothing at all.
        ("linear-gradient(#000, #fff)", "linearGradient"),
        ("linear-gradient(135deg, #667eea, #764ba2)", "linearGradient"),
        ("linear-gradient(to bottom right, #000, #fff 30%, #888)", "linearGradient"),
        ("radial-gradient(rgba(0, 0, 0, 0.5), #fff)", "radialGradient"),
    ),
)
def test_gradient_svg(backdrop, expected):
    """A CSS gradient becomes a paint server; anything else stays a color."""
    translated = gradient_svg(backdrop, "fruit", 100, 50)
    if expected is None:
        assert translated is None
        return
    assert translated
    markup, paint = translated
    assert paint == "url(#fruit)"
    assert f'<{expected} id="fruit"' in markup
    # Every color the value named is carried over, in order.
    assert markup.count("<stop ") >= 2


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        # 90 degrees is `to right`: a horizontal line spanning the image's width.
        ("linear-gradient(90deg, #000, #fff)", 'x1="0" y1="25" x2="100" y2="25"'),
        # No direction at all means `to bottom`, spanning its height.
        ("linear-gradient(#000, #fff)", 'x1="50" y1="0" x2="50" y2="50"'),
        # A side keyword names the same angles.
        ("linear-gradient(to right, #000, #fff)", 'x1="0" y1="25" x2="100" y2="25"'),
    ),
)
def test_gradient_svg_places_the_line_in_user_space(value, expected):
    """The gradient line runs through the center, at the angle asked for."""
    translated = gradient_svg(value, "fruit", 100, 50)
    assert translated
    assert expected in translated[0]


def test_render_paints_a_gradient_backdrop():
    """A gradient backdrop reaches the capture as a declared paint server."""
    svg = render(
        "kiwi", unique_id="fruit", chrome=Chrome(backdrop="linear-gradient(#000, #fff)")
    )
    assert '<linearGradient id="fruit-backdrop"' in svg
    assert '<rect fill="url(#fruit-backdrop)"' in svg


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("", ""),
        ("kiwi", ["1 │ kiwi"]),
        ("kiwi\nbanana", ["1 │ kiwi", "2 │ banana"]),
        # The gutter is one column wide whatever the tally reaches.
        ("\n".join("fruit" for _ in range(10))[:], None),
    ),
)
def test_number_lines(text, expected):
    """Each line gets its number, right-aligned on the widest one."""
    numbered = unstyle(number_lines(text))
    if expected == "":
        assert numbered == ""
    elif expected is not None:
        assert numbered.splitlines() == expected
    else:
        lines = numbered.splitlines()
        assert lines[0].startswith(" 1 │ ")
        assert lines[-1].startswith("10 │ ")


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_preset_catalog(name):
    """Every preset carries a full palette on both of its dresses."""
    preset = PRESETS[name]
    assert preset.label
    for palette in (preset.dark, preset.light):
        assert len(palette.ansi) == 16
        for color in (
            palette.background,
            palette.foreground,
            palette.titlebar,
            *palette.ansi,
        ):
            assert re.fullmatch(r"#[0-9a-f]{6}", color), color
    # A stack always ends on the family every renderer resolves.
    assert preset.font_stack.endswith("monospace")


@pytest.mark.parametrize(
    ("color", "expected"),
    (
        # The 16 ANSI slots are names, and answer to the terminal's palette.
        ("blue", "#0037da"),
        ("bright_blue", "#3b78ff"),
        (4, "#0037da"),
        (12, "#3b78ff"),
        # Everything else already states its own color.
        ("#facade", "#facade"),
        ((250, 202, 222), "#facade"),
        # The 256-color cube and its grayscale ramp are fixed by xterm.
        (208, "#ff8700"),
        (232, "#080808"),
    ),
)
def test_palette_color(color, expected):
    """A style's color resolves against the palette only where it names a slot."""
    assert palette_color(color, PRESETS["windows"].dark) == expected


@pytest.mark.parametrize("color", (object(), True, False))
def test_palette_color_rejects_a_value_naming_no_color(color):
    """A value that is not a color cannot silently paint something.

    A `bool` is an `int`, and names no palette slot for all that.
    """
    with pytest.raises(ValueError, match="Cannot resolve color"):
        palette_color(color, PRESETS["windows"].dark)


@pytest.mark.parametrize(
    ("ratio", "expected"),
    ((0.0, "#ffffff"), (0.5, "#808080"), (1.0, "#000000")),
)
def test_blend(ratio, expected):
    """Dim text is mixed toward the background rather than made transparent."""
    assert blend("#ffffff", "#000000", ratio) == expected


def test_grid_wraps_at_the_terminal_edge():
    """A line reaching past the last column continues on the next row.

    Cropping it would drop text the command printed, and a capture is evidence
    of what ran.
    """
    rows = grid("fruit basket", 5)
    assert [[(run, column) for _, run, column in row] for row in rows] == [
        [("fruit", 0)],
        [(" bask", 0)],
        [("et", 0)],
    ]


def test_grid_marks_each_fold_with_its_wrap_marker():
    """A marked fold closes its row on the marker, painted as a mark of the layout.

    The marker takes the last cell of the row it closes, so each folded row holds
    one cell less of text, and the last row of the line carries none: nothing
    continues past it.
    """
    rows = grid("fruit basket", 6, wrap_marker=WRAP_MARKER_LABEL)
    assert [[(run, column) for _, run, column in row] for row in rows] == [
        [("fruit", 0), (WRAP_MARKER_LABEL, 5)],
        [(" bask", 0), (WRAP_MARKER_LABEL, 5)],
        [("et", 0)],
    ]
    marker_style = rows[0][1][0]
    assert marker_style != rows[0][0][0], "the marker reads as part of the output"
    assert all(cell_width(unstyle(run)) <= 6 for row in rows for _, run, _ in row)


def test_grid_without_a_wrap_marker_folds_a_full_row_silently():
    """No marker means the terminal's own fold: a line exactly as wide fits."""
    assert [[run for _, run, _ in row] for row in grid("banana", 6)] == [["banana"]]
    # Asking for a marker costs the cell, so the same line now folds.
    marked = grid("banana", 6, wrap_marker=WRAP_MARKER_LABEL)
    assert [[run for _, run, _ in row] for row in marked] == [
        ["banan", WRAP_MARKER_LABEL],
        ["a"],
    ]


def test_grid_never_splits_a_wide_glyph():
    """A wide glyph straddling the last column moves down whole."""
    # The ideograph needs two cells and only one is left on the first row.
    rows = grid("ab\u6c34", 3)
    assert [[run for _, run, _ in row] for row in rows] == [["ab"], ["\u6c34"]]


def test_grid_keeps_a_glyph_wider_than_the_grid():
    """A glyph too wide for the whole grid is drawn rather than wrapped forever."""
    assert [[run for _, run, _ in row] for row in grid("\u6c34", 1)] == [["\u6c34"]]


@pytest.mark.parametrize(
    ("name", "expected", "unwanted"),
    (
        # Round buttons on the left, the colors Aqua paints them.
        ("macos", "<circle", "<text"),
        # Glyphs against the right edge, close last.
        ("windows", 'text-anchor="end"', "<circle"),
        ("linux", 'text-anchor="end"', "<circle"),
        # A window wearing none of it.
        ("plain", "", "<circle"),
    ),
)
def test_window_buttons(name, expected, unwanted):
    """Each preset draws the decorations its desktop does, or none at all."""
    markup = window_buttons(PRESETS[name].buttons, width=500, color="#ffffff")
    if expected:
        assert expected in markup
    else:
        assert markup == ""
    assert unwanted not in markup


def test_render_draws_the_preset_it_is_given():
    """A preset reaches the capture: its palette, its font, its decorations."""
    svg = render("kiwi", unique_id="fruit", preset=PRESETS["windows"])
    assert 'fill="#0c0c0c"' in svg
    assert "Cascadia Code" in svg
    assert 'text-anchor="end"' in svg
    assert "Fira Code" not in svg
    # Its square corners come along, unless the caller states otherwise.
    assert 'rx="0"' in svg
    assert 'rx="8"' in render(
        "kiwi", unique_id="fruit", preset=PRESETS["windows"], chrome=Chrome(radius=8)
    )


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_preset_paints_its_own_titlebar(name):
    """A window drawn as a desktop's carries that desktop's chrome on top."""
    preset = PRESETS[name]
    svg = render("kiwi", unique_id="fruit", preset=preset, title="Pantry")
    assert f'fill="{preset.dark.titlebar}"' in svg
    # Every desktop paints the strip a shade off the terminal it frames. Only
    # the preset mimicking no desktop leaves the two the same color.
    wears_chrome = preset.dark.titlebar != preset.dark.background
    assert wears_chrome is (name != "plain")


def test_titlebar_collapses_on_a_window_wearing_nothing():
    """An empty strip is dropped, and comes back as soon as it holds something."""
    bare, titled, decorated = (
        render("kiwi", unique_id="fruit", preset=PRESETS[name], title=title)
        for name, title in (("plain", ""), ("plain", "Pantry"), ("macos", ""))
    )
    heights = [svg_box(svg)[1] for svg in (bare, titled, decorated)]
    assert heights[0] == heights[1] - TITLEBAR_HEIGHT
    assert heights[1] == heights[2]


@pytest.mark.parametrize(
    ("format", "expected"),
    (
        (CaptureFormat.SVG, 'fill-opacity="0.4"'),
        (CaptureFormat.HTML, "color-mix(in srgb, #292929 40%, transparent)"),
    ),
)
def test_render_thins_the_window_out(format, expected):
    """Opacity below one lets whatever the capture sits on through its body."""
    thinned = render(
        "kiwi", format=format, unique_id="fruit", chrome=Chrome(opacity=0.4)
    )
    assert expected in thinned
    # The text keeps its own paint whatever the body does.
    assert "kiwi" in thinned
    assert expected not in render(
        "kiwi", format=format, unique_id="fruit", chrome=Chrome(opacity=OPAQUE)
    )


DRAWN_FORMATS = tuple(
    format for format in CaptureFormat if format is not CaptureFormat.ANSI
)
"""The formats that draw a document around the captured text.

{attr}`~click_extra.capture.screenshot.CaptureFormat.ANSI` is the one that does not: it
hands a terminal the stream it was already carrying, so there is no margin to
credit in and nothing a window option could describe. Everything below asking
about a window therefore asks it of these two.
"""


@pytest.mark.parametrize("format", DRAWN_FORMATS)
def test_render_credits_what_drew_it(format):
    """Every capture carries the mark, in the space around the terminal."""
    marked = render("kiwi", format=format, unique_id="fruit")
    # The name is wrapped in a link, so the line reads whole only once the
    # markup between its parts is taken back out.
    assert DEFAULT_WATERMARK in re.sub(r"<[^>]+>", "", marked)
    assert WATERMARK_INK in marked
    # A capture that travels says what drew it, never which release: a
    # committed capture is regenerated at every release, and a release number
    # would rewrite every asset on release day.
    assert "click-extra" in DEFAULT_WATERMARK
    assert not re.search(r"\d", DEFAULT_WATERMARK)
    # And the mark is a default, not a fixture.
    assert DEFAULT_WATERMARK not in render(
        "kiwi", format=format, unique_id="fruit", chrome=Chrome(watermark="")
    )
    assert "pantry 1.4.2" in render(
        "kiwi",
        format=format,
        unique_id="fruit",
        chrome=Chrome(watermark="pantry 1.4.2"),
    )


@pytest.mark.parametrize("format", DRAWN_FORMATS)
def test_watermark_links_the_package_name(format):
    """The credit points a reader holding only the image back at the docs."""
    marked = render("kiwi", format=format, unique_id="fruit")
    assert f'href="{WATERMARK_URL}"' in marked
    # Only the name is linked: the words around it stay outside the anchor.
    linked = re.search(r"<a\b[^>]*>(.*?)</a>", marked, re.DOTALL)
    assert linked
    assert re.sub(r"<[^>]+>", "", linked[1]) == "click-extra"


@pytest.mark.parametrize("format", DRAWN_FORMATS)
def test_watermark_leaves_a_borrowed_credit_unlinked(format):
    """A project crediting itself has no click-extra to point anywhere."""
    marked = render(
        "kiwi",
        format=format,
        unique_id="fruit",
        chrome=Chrome(watermark="pantry 1.4.2"),
    )
    assert "pantry 1.4.2" in marked
    assert WATERMARK_URL not in marked
    assert "<a " not in marked


def test_watermark_is_not_terminal_text():
    """The mark is chrome, so reading a capture back does not collect it."""
    svg = render("kiwi", unique_id="fruit", chrome=Chrome(watermark="pantry 1.4.2"))
    assert "pantry 1.4.2" in svg
    assert svg_to_lines(svg) == ["kiwi"]


def test_watermark_sits_where_the_margin_is():
    """It is drawn against the image's own corner, wherever the margin puts it."""
    svg = render("kiwi", unique_id="fruit", chrome=Chrome(margin=60))
    width, height = svg_box(svg)
    mark = re.search(r'<text class="watermark" x="([\d.]+)" y="([\d.]+)"', svg)
    assert mark
    assert float(mark[1]) == pytest.approx(width - WATERMARK_INSET)
    assert float(mark[2]) == pytest.approx(height - WATERMARK_INSET)


def test_render_draws_neither_when_asked_for_neither():
    """`none` is the value that leaves the window bare."""
    svg = render(
        "kiwi", unique_id="fruit", chrome=Chrome(border=NO_PAINT, shadow=NO_PAINT)
    )
    assert 'stroke="none"' in svg
    assert "feDropShadow" not in svg
    assert "filter=" not in svg


@pytest.mark.parametrize(
    ("margin", "padding"),
    ((0, 0), (16, 0), (0, 12), (10, 10)),
)
def test_render_geometry(margin, padding):
    """Margin grows the image alone; padding grows the window inside it too.

    Neither moves a glyph relative to the others: the capture is repositioned as
    a whole, so its text still reads back line by line.
    """
    bare = render("kiwi", unique_id="fruit", chrome=Chrome(margin=0, padding=0))
    framed = render(
        "kiwi", unique_id="fruit", chrome=Chrome(margin=margin, padding=padding)
    )

    grown = 2 * (margin + padding)
    assert svg_box(framed) == tuple(side + grown for side in svg_box(bare))
    assert svg_window(framed) == tuple(side + 2 * padding for side in svg_window(bare))
    assert svg_to_lines(framed) == svg_to_lines(bare)


def test_render_html_escapes_the_captured_text():
    """Markup a CLI prints is escaped, not handed to the browser as markup.

    The load-bearing test of the HTML renderer: `ansi_to_html()` translates ANSI
    and copies everything else verbatim, so a caller skipping the escape turns
    click-extra's own `--export-config` help, which says it writes `to <stdout>`,
    into an unclosed tag.
    """
    html = render(
        "plain <stdout> & \x1b[31mstyled <b>bold</b>\x1b[0m",
        format=CaptureFormat.HTML,
    )
    assert "&lt;stdout&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html
    assert "&amp;" in html
    # The only tags are the ones the renderer emits itself.
    assert "<stdout>" not in html
    assert "<b>" not in html


def test_render_html_round_trips_the_terminal_text():
    """Stripping the markup back off returns exactly what the CLI printed.

    The HTML counterpart of {func}`svg_to_lines`: it catches a dropped
    character, a mangled escape and a stray tag in one assertion.
    """
    html = render(SAMPLE_CAPTURE, format=CaptureFormat.HTML)
    assert html_to_text(html) == unstyle(SAMPLE_CAPTURE)


def test_render_html_fragment_is_self_contained():
    """A fragment carries its own styling, and no document scaffolding."""
    fragment = render(
        SAMPLE_CAPTURE,
        format=CaptureFormat.HTML,
        full=False,
        chrome=Chrome(watermark=""),
    )
    assert fragment.startswith("<pre style=")
    assert fragment.endswith("</pre>")
    assert "<!doctype" not in fragment.lower()
    # Inline styling means a host page needs to supply no stylesheet.
    assert DARK_PALETTE.background in fragment
    assert DARK_PALETTE.foreground in fragment


def test_render_html_document_wraps_the_fragment():
    """A full document is the fragment plus scaffolding, nothing else."""
    fragment = render(SAMPLE_CAPTURE, format=CaptureFormat.HTML, full=False)
    document = render(SAMPLE_CAPTURE, format=CaptureFormat.HTML, title="Fruit <&> veg")
    assert document.lower().startswith("<!doctype html>")
    assert fragment in document
    # The title is escaped like any other text.
    assert "<title>Fruit &lt;&amp;&gt; veg</title>" in document


def test_render_html_quotes_survive_the_style_attribute():
    """The font stack cannot terminate the `style` attribute it sits in.

    A double-quoted family name would close the attribute early and spill CSS
    into the markup, so the stack is single-quoted.
    """
    fragment = render(SAMPLE_CAPTURE, format=CaptureFormat.HTML, full=False)
    opening = fragment[: fragment.index(">") + 1]
    assert opening.count('"') == 2, f"unbalanced quoting: {opening}"
    assert "monospace" in opening


_SPAN_RE = re.compile(r'<span style="(?P<css>[^"]*)">(?P<text>[^<]*)</span>')
"""One styled run of an HTML capture, with its inline declarations."""


def css_rects(declarations: str) -> set[tuple[int, int, int, int]]:
    """The rectangles a {func}`~click_extra.capture.html.block_css` box paints.

    Read back off its background layers, in eighths of a cell, the unit of
    {data}`~click_extra.capture.svg.BLOCK_ELEMENTS`.
    """
    css = dict(part.split(": ", 1) for part in declarations.split("; "))
    layers = zip(
        _split_arguments(css["background-image"]),
        _split_arguments(css["background-size"]),
        _split_arguments(css["background-position"]),
    )
    rects = set()
    for image, size, position in layers:
        stops = _split_arguments(image.removeprefix("linear-gradient(")[:-1])
        if stops[0] == "90deg":
            left = round(float(stops[1].rsplit(" ", 1)[1][:-1]) * 8 / 100)
            right = round(float(stops[3].rsplit(" ", 1)[1][:-1]) * 8 / 100)
        else:
            left, right = 0, 8
        height = float(size.split()[1].removesuffix("em"))
        top = float(position.split()[1].removesuffix("em"))
        upper = round(top / LINE_SPACING * 8)
        rects.add((left, upper, right, upper + round(height / LINE_SPACING * 8)))
    return rects


@pytest.mark.parametrize("char", tuple(BLOCK_ELEMENTS))
def test_block_css_paints_the_shape_of_its_character(char):
    """The CSS of a block element paints the rectangles its shape names."""
    declarations = block_css(char, 3)
    assert css_rects(declarations) == set(BLOCK_ELEMENTS[char])
    assert "width: 3ch" in declarations
    assert f"height: {LINE_SPACING:g}em" in declarations
    if char in SHADE_DENSITY:
        assert f"currentColor {SHADE_DENSITY[char]:.0%}" in declarations


def test_render_html_draws_each_box_run_as_one_svg():
    """A run of Box Drawing is one box holding the run's lines as an SVG.

    One SVG per run rather than a background per cell, so a rule merges into one
    line, and the characters stay in the text.
    """
    text = "┌─┐ kiwi\n└─┘"
    html = render(
        text, format=CaptureFormat.HTML, full=False, chrome=Chrome(watermark="")
    )
    assert html_to_text(html) == text
    assert html.count("<svg ") == 2
    assert html.count("position: relative") == 2
    assert 'fill="currentColor"' in html


@pytest.mark.parametrize("code", (0x2800, 0x2801, 0x280B, 0x28FF))
def test_braille_css_draws_one_disc_per_dot(code):
    """The CSS of a Braille pattern paints a disc for each dot it raises."""
    char = chr(code)
    declarations = braille_css(char, 2)
    assert declarations.count("radial-gradient(") == len(braille_dots(char))
    assert "width: 2ch" in declarations
    assert f"height: {LINE_SPACING:g}em" in declarations


def test_render_html_draws_shapes():
    """Every shape sits in a box drawing it, whatever its run's style.

    Its glyphs stay in the text, so the capture still reads back as the terminal
    text, and the run keeps the colors it came with.
    """
    text = (
        "▀▄█ apple\n"
        + style("▀▀", fg=(255, 255, 255), bg=(0, 0, 128))
        + style(" pear ░⠋", fg="green")
    )
    html = render(
        text, format=CaptureFormat.HTML, full=False, chrome=Chrome(watermark="")
    )
    assert html_to_text(html) == unstyle(text)
    assert f"line-height: {LINE_SPACING:g};" in html
    shaped = "".join(
        span["text"]
        for span in _SPAN_RE.finditer(html)
        if "display: inline-block" in span["css"]
        and "-webkit-text-fill-color: transparent" in span["css"]
    )
    assert shaped == "▀▄█▀▀░⠋"
    (two_tone,) = (span for span in _SPAN_RE.finditer(html) if span["text"] == "▀▀")
    assert "color: #ffffff; background-color: #000080; " in two_tone["css"]


def test_render_html_keeps_a_joined_shape_in_its_cluster():
    """A shape after a zero width joiner stays in the text, as in an SVG capture."""
    text = f"x{_ZWJ}█ab ▀"
    html = render(
        text, format=CaptureFormat.HTML, full=False, chrome=Chrome(watermark="")
    )
    assert html_to_text(html) == text
    shaped = [
        span["text"]
        for span in _SPAN_RE.finditer(html)
        if "display: inline-block" in span["css"]
    ]
    assert shaped == ["▀"]


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        # Nothing to measure still asks for a picture glyphs fit in.
        ("", MIN_COLUMNS),
        ("kiwi", MIN_COLUMNS),
        ("k" * 40, 40),
        ("kiwi\n" + "banana " * 10, 70),
        # An escape styles the glyphs around it and occupies no cell.
        ("\x1b[31m" + "cherry" * 6 + "\x1b[0m", 36),
    ),
)
def test_fit_columns(text, expected):
    """The width `auto` resolves to is the longest line, floored by the caller."""
    assert fit_columns(text, floor=MIN_COLUMNS) == expected


def test_render_auto_columns_folds_nothing():
    """`auto` lays the image out at what the text asks for.

    A line the command does not wrap on its own (a prompt, a wide table) is
    folded by a pinned width and kept whole by this one.
    """
    text = "banana " * 20
    assert svg_to_lines(render(text, columns=AUTO_COLUMNS)) == [text.rstrip()]
    assert len(svg_to_lines(render(text, columns=DEFAULT_COLUMNS))) > 1


@pytest.mark.parametrize(
    ("value", "message"),
    (
        ("wide", "neither an integer"),
        ("4", "narrower than"),
    ),
)
def test_screenshot_rejects_an_unusable_width(invoke, tmp_path, value, message):
    """`--columns` takes a width or the one word standing for none of them."""
    result = invoke(
        screenshot_cmd,
        ["--columns", value, "--output", str(tmp_path / "shot.svg"), "--", "echo"],
    )
    assert result.exit_code != 0
    assert "Invalid value for '--columns': " in result.output
    assert message in result.output


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("auto", AUTO_COLUMNS),
        (" Auto ", AUTO_COLUMNS),
        ("80", 80),
        (str(MIN_COLUMNS), MIN_COLUMNS),
    ),
)
def test_parse_columns(value, expected):
    """A width is an integer, or the one word leaving it to the text."""
    assert parse_columns(value) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    (
        ("wide", f"'wide' is neither an integer nor {AUTO_COLUMNS!r}."),
        ("4", f"4 is narrower than the {MIN_COLUMNS}-column floor."),
        (str(MIN_COLUMNS - 1), f"{MIN_COLUMNS - 1} is narrower than"),
    ),
)
def test_parse_columns_rejects(value, message):
    """A width that is neither says what it would take."""
    with pytest.raises(ValueError, match=re.escape(message)):
        parse_columns(value)


@pytest.mark.parametrize(
    ("value", "message"),
    (
        ("wide", "'wide' is not a hold, which is seconds or 'auto'."),
        ("-1", "is not a pause, which is never negative."),
    ),
)
def test_screenshot_rejects_an_unusable_hold(invoke, tmp_path, value, message):
    """A bad `--hold` is reported against the option, like a bad `--columns`.

    The prefix is what tells a reader which of a dozen options to fix.
    """
    result = invoke(
        screenshot_cmd,
        [f"--hold={value}", "--output", str(tmp_path / "shot.svg"), "--", "echo"],
    )
    assert result.exit_code != 0
    assert "Invalid value for '--hold': " in result.output
    assert message in result.output


@pytest.mark.parametrize(
    ("columns", "pinned"),
    (
        pytest.param(100, {"COLUMNS": "100"}, id="pinned-width"),
        pytest.param(AUTO_COLUMNS, {}, id="auto-pins-nothing"),
    ),
)
def test_capture_environment(columns, pinned):
    """The command is told the chrome, denied the terminal, and given its width."""
    assert capture_environment(TerminalBackground.LIGHT, columns) == {
        **CAPTURE_TERMINAL_HINTS[TerminalBackground.LIGHT],
        **dict.fromkeys(CAPTURE_HIDDEN_TERMINAL_VARS),
        **pinned,
    }


@pytest.mark.parametrize(
    ("arguments", "message"),
    (
        pytest.param(
            ["--rows", "30"], "--rows requires --record", id="rows-needs-record"
        ),
        pytest.param(
            ["--hold", "5"], "--hold requires --record", id="hold-needs-record"
        ),
        pytest.param(
            ["--blank", "1"], "--blank requires --record", id="blank-needs-record"
        ),
        pytest.param(
            ["--speed", "2"], "--speed requires --record", id="speed-needs-record"
        ),
    ),
)
def test_screenshot_pacing_needs_record(invoke, tmp_path, arguments, message):
    """The pacing knobs describe a recording, so a still refuses them."""
    result = invoke(
        screenshot_cmd,
        [*arguments, "--output", str(tmp_path / "shot.svg"), "--", "echo"],
    )
    assert result.exit_code != 0
    assert message in result.output


@pytest.mark.parametrize(
    ("arguments", "output_name", "message"),
    (
        pytest.param([], "shot.html", "point --output at an .svg file", id="svg-only"),
        pytest.param(
            ["--columns", "auto"],
            "shot.svg",
            "give --columns a number",
            id="width-pinned-up-front",
        ),
        pytest.param(
            ["--merge-stderr"],
            "shot.svg",
            "a pseudo-terminal has one",
            id="streams-already-folded",
        ),
        pytest.param(
            ["--head", "3"],
            "shot.svg",
            "keeps whole screens",
            id="no-trimming",
        ),
        pytest.param(
            ["--wrap-marker", "auto"],
            "shot.svg",
            "folds its own lines",
            id="no-wrap-marker",
        ),
    ),
)
def test_screenshot_record_rejects_still_only_arrangements(
    invoke, tmp_path, arguments, output_name, message
):
    """A recording is an animated SVG of whole screens at a pinned width."""
    result = invoke(
        screenshot_cmd,
        ["--record", *arguments, "--output", str(tmp_path / output_name), "--", "echo"],
    )
    assert result.exit_code != 0
    assert message in result.output


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_screenshot_record_writes_an_animation(invoke, tmp_path):
    """`--record` lands an animated SVG named after its output stem."""
    target = tmp_path / "pantry-trail.svg"
    result = invoke(
        screenshot_cmd,
        [
            "--record",
            "--output",
            str(target),
            "--prompt",
            "basket ripen",
            "--hold",
            "auto",
            "--",
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('\\r[##]\\x1b[K'); print('ripe')",
        ],
    )
    assert result.exit_code == 0, result.output
    svg = target.read_text(encoding="UTF-8")
    assert "pantry-trail-f0" in svg
    assert "basket" in svg
    assert "ripe" in svg


@pytest.mark.parametrize(
    "mode",
    (
        pytest.param((), id="still"),
        pytest.param(
            ("--record",),
            id="record",
            marks=skip_windows(
                reason="A pseudo-terminal needs termios, which Windows lacks"
            ),
        ),
    ),
)
@pytest.mark.parametrize(
    "program",
    (
        pytest.param("juicer", id="not-on-path"),
        pytest.param("{folder}/recipe.txt", id="not-executable"),
    ),
)
def test_screenshot_reports_a_command_that_cannot_start(
    invoke, monkeypatch, tmp_path, mode, program
):
    """A command the system refuses to start is an error line, not a traceback.

    Only the start of the line is pinned: the reason closing it is the system's
    own, and it differs between platforms.
    """
    monkeypatch.setenv("PATH", str(tmp_path))
    (tmp_path / "recipe.txt").write_text("Peel the mango.\n", encoding="UTF-8")
    program = program.format(folder=tmp_path)
    target = tmp_path / "shot.svg"
    result = invoke(screenshot_cmd, [*mode, "--output", str(target), "--", program])
    assert result.exit_code == 1, result.output
    assert f"Error: Cannot run {program!r}: " in result.output
    # The command line is not at fault, so no usage is printed.
    assert "Usage:" not in result.output
    assert not target.exists()


def test_screenshot_reports_a_command_outliving_its_timeout(invoke, tmp_path):
    """A command still running when `--timeout` ends is an error line.

    The command is killed, and nothing is written.
    """
    target = tmp_path / "shot.svg"
    result = invoke(
        screenshot_cmd,
        [
            "--timeout",
            "0.2",
            "--output",
            str(target),
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ],
    )
    assert result.exit_code == 1, result.output
    assert f"Error: --timeout 0.2 stopped {sys.executable!r} before it exited." in (
        result.output
    )
    assert not target.exists()


def test_screenshot_wrap_needs_the_console_script(invoke, monkeypatch, tmp_path):
    """`--wrap` refuses to re-enter through anything but the installed command.

    `python -m click_extra` resolves a target differently, so falling back to it
    would capture a different CLI than the composition it stands for. Better to
    say so than to quietly picture the wrong thing.
    """
    monkeypatch.setattr(shutil, "which", lambda _: None)
    result = invoke(
        screenshot_cmd,
        ["--wrap", "--output", str(tmp_path / "shot.svg"), "--", "mkdocs", "--help"],
    )
    assert result.exit_code != 0
    assert "click-extra wrap -- TARGET" in result.output


@pytest.mark.skipif(
    shutil.which("click-extra") is None,
    reason="--wrap re-enters through the installed console script",
)
def test_screenshot_wrap_matches_the_composition(invoke, tmp_path):
    """`--wrap` is the nested composition, spelled as a flag.

    Captured both ways, the terminal text has to match: the flag is a shortcut,
    not a second way of rendering.
    """
    target = ("click_extra.cli:demo_themes", "--help")
    shortcut = tmp_path / "shortcut.html"
    composed = tmp_path / "composed.html"

    assert (
        invoke(
            screenshot_cmd,
            [
                "--wrap",
                "--fragment",
                "--head",
                "3",
                "--output",
                str(shortcut),
                "--",
                *target,
            ],
        ).exit_code
        == 0
    )
    assert (
        invoke(
            screenshot_cmd,
            [
                "--fragment",
                "--head",
                "3",
                "--prompt",
                f"click-extra wrap -- {' '.join(target)}",
                "--output",
                str(composed),
                "--",
                shutil.which("click-extra"),
                "wrap",
                "--",
                *target,
            ],
        ).exit_code
        == 0
    )

    text = html_to_text(shortcut.read_text(encoding="UTF-8"))
    assert text == html_to_text(composed.read_text(encoding="UTF-8"))
    # The prompt shows what a reader types, not the plumbing that ran. Its sigil
    # is the running platform's, so both captures draw the same one.
    assert (
        text.splitlines()[0]
        == f"{PROMPT}click-extra wrap -- click_extra.cli:demo_themes --help"
    )


def test_ansi_capture_is_the_text_it_was_given():
    """The one format that renders nothing: a terminal reads the stream itself."""
    text = "\x1b[32mmango\x1b[0m\nripe\n"
    assert render(text, format=CaptureFormat.ANSI) == text


def test_ansi_capture_draws_no_window():
    """None of the window options reach a format that has no window."""
    drawn = render(
        "mango\n",
        format=CaptureFormat.ANSI,
        title="basket",
        preset=PRESETS["macos"],
        chrome=Chrome(watermark="credit me", backdrop="#ff0000", margin=48),
    )
    assert drawn == "mango\n"


def test_ansi_capture_bands_an_emphasized_row():
    """A terminal has no behind, so the band is the row's own background."""
    banded = render("mango\nripe\nplum\n", format=CaptureFormat.ANSI, emphasize=[2])
    rows = banded.split("\n")
    assert "\x1b[48;2;" not in rows[0]
    assert rows[1].startswith("\x1b[48;2;")
    assert rows[1].endswith("\x1b[49m")
    # Padded out to the longest row, so the marked rows square up into a block.
    assert unstyle(rows[1]) == "ripe "
    assert unstyle(banded) == "mango\nripe \nplum\n"


def test_ansi_band_survives_a_reset_inside_the_row():
    """Restated after every escape, or the band stops at the first keyword.

    Pygments closes a colored run with a full reset, which clears the background
    along with the ink it was closing.
    """
    row = "\x1b[38;2;1;2;3mdef\x1b[39;00m ripen"
    banded = render(row + "\n", format=CaptureFormat.ANSI, emphasize=[1])
    opening, _, after_reset = banded.partition("\x1b[39;00m")
    assert opening.startswith("\x1b[48;2;")
    assert after_reset.startswith("\x1b[48;2;"), "the band died at the reset"


def test_ansi_capture_does_not_animate():
    """There is no frame to hide in a stream a terminal paints as it arrives."""
    with pytest.raises(ValueError, match=r"^ANSI captures do not animate\.$"):
        render("mango", format=CaptureFormat.ANSI, frames=("a", "b"), interval=1)


def test_render_dresses_an_html_capture_in_the_preset_font_alone():
    """A preset's font reaches an HTML capture, and its title bar stays the SVG's.

    The buttons and the strip they sit in are drawn by the SVG alone: an HTML
    capture reflows with the page embedding it, and has no window to seat them.
    """
    html = render(SAMPLE_CAPTURE, format=CaptureFormat.HTML, preset=PRESETS["macos"])
    assert PRESETS["macos"].font_stack in html
    assert PRESETS["macos"].dark.titlebar not in html
    assert "<circle" not in html
