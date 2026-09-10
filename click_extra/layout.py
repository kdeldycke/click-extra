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

"""Measure a line of terminal text, and compose one of a stated width.

A terminal is a grid of cells, and everything a CLI draws on it has to agree on
how many cells a string occupies. That number is not the string's length: an
ideograph takes two cells and a combining mark none. {func}`cell_width` answers
it once, and every line this package composes is built on that answer.

The module holds the composition helpers built on it, starting with
{func}`center_in_rule`. They are terminal-text primitives, not capture
machinery: {mod}`click_extra.screenshot` consumes them to lay a picture out on
the same grid, and so can any CLI drawing a divider of its own.
"""

from __future__ import annotations

from unicodedata import bidirectional

from boltons.strutils import strip_ansi
from click import style, unstyle
from wcwidth import wcswidth, wrap as wcwidth_wrap

from .styling import Style, split_ansi

PADDING = " \N{NO-BREAK SPACE}"
"""Characters that separate one column of terminal text from the next.

Both are one cell wide and draw nothing.
{func}`~click_extra.screenshot.render_svg` emits every space as a non-breaking
one, so the padding survives an XML round-trip and no renderer collapses a run
of them.
"""

RULE_GLYPH = "\N{BOX DRAWINGS LIGHT HORIZONTAL}"
"""Character {func}`center_in_rule` draws a rule with, absent a better one.

An unbroken line, which is what a divider between two whole things is.
"""

RULE_COLOR = "bright_black"
"""Color {func}`center_in_rule` paints a rule and its brackets.

A rule is the one line of a screen nothing printed, so it is drawn to recede:
dimmer than the text it separates, in both the gallery of `click-extra themes`
and the marker standing in for what a capture cut. A rule a caller spells out
in full is written as given, color included, since a caller naming one has
already decided how it should look.
"""


def cell_width(text: str) -> int:
    """Columns `text` occupies on a terminal's character grid.

    Not its length: a CJK ideograph is drawn two cells wide, a combining mark
    none at all. `wcwidth.wcswidth` answers for both, and returns `-1` for
    a string carrying a control character, where the count of characters is the
    closest thing to an answer left.

    :param text: the text to measure.
    :return: the number of cells it occupies.
    """
    width = wcswidth(text)
    return width if width >= 0 else len(text)


def center_in_rule(
    label: str | None,
    width: int,
    rule: str = RULE_GLYPH,
    opening: str = "[ ",
    closing: str = " ]",
    color: str | None = RULE_COLOR,
) -> str:
    """One line of `width` cells: `label` centered in a rule drawn with `rule`.

    `label` may arrive already styled, and is measured with its escapes
    stripped, so a caller paints the label its own way and hands the whole
    thing over. `color` paints the rule and the two brackets, which is the half
    a caller cannot pre-style without knowing where they fall.

    A `None` or empty label draws no brackets and one contiguous rule: a
    divider naming nothing should not look like a frame around nothing. A width
    too narrow for the brackets drops them the same way, and one too narrow for
    the label leaves the label alone rather than drawing a rule that cannot
    close.

    Measured in cells, not characters: a label carrying a wide glyph shifts a
    rule built on `len` by one column per glyph.

    :param label: the text the rule is drawn around, styled or not, or `None`
        for an unbroken rule.
    :param width: columns the line occupies.
    :param rule: character the rule is drawn with.
    :param opening: bracket written between the rule and `label`.
    :param closing: bracket written between `label` and the rule.
    :param color: color the rule and brackets are painted, or `None` to leave
        them as they are. `label` is never repainted: a caller styles it
        itself, or leaves it in the terminal's own ink.
    :return: the whole line.
    """
    label = label or ""
    plain = strip_ansi(label)
    if not plain:
        opening = closing = ""
    if cell_width(f"{opening}{plain}{closing}") > width:
        opening = closing = ""
    padding = max(width - cell_width(f"{opening}{plain}{closing}"), 0)
    left = padding // 2

    def paint(text: str) -> str:
        return style(text, fg=color) if color and text else text

    return f"{paint(rule * left + opening)}{label}{paint(closing + rule * (padding - left))}"


LINE_NUMBER_SEPARATOR = " │ "
"""Rule drawn between a line's number and the line itself.

A vertical bar rather than a bare space, so the gutter reads as a column of its
own even where the output is itself indented.
"""

RTL_BIDI_CLASSES = frozenset({"R", "AL", "AN"})
"""Unicode bidirectional classes written right to left.

Right-to-left letters, Arabic letters and Arabic-Indic numbers, as
{func}`unicodedata.bidirectional` names them. See {func}`is_bidirectional`.
"""


def number_lines(text: str, start: int = 1) -> str:
    """Prefix each line of `text` with its number, in a dim gutter.

    The numbers are drawn into the terminal text rather than into a column
    beside it, which is the same trade Pygments makes with its inline line
    numbers: every renderer places them for free, and every reader copying the
    text copies them too.

    Right-aligned on the widest number, so the gutter is one column whatever the
    output's length, and separated by {data}`LINE_NUMBER_SEPARATOR`.

    :param text: the text to number, ANSI escape sequences included.
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


def is_bidirectional(text: str) -> bool:
    """Whether `text` carries a character written right to left.

    Arabic, Hebrew and their neighbours are reordered by whoever draws them, and
    the cursive ones are shaped: a letter's form depends on what it joins. A
    terminal grid describes neither, which is why
    {func}`~click_extra.screenshot.render_svg` stops pinning such a run to an
    exact width.

    :param text: the text to inspect.
    :return: `True` when at least one character is right-to-left.
    """
    return any(bidirectional(char) in RTL_BIDI_CLASSES for char in text)


def _char_width(char: str) -> int:
    """Cells one character occupies, cached.

    {func}`grid` measures every character one at a time, and terminal output
    draws from a small alphabet, so the cache turns the repeated width-table
    walks of {func}`cell_width` into dict hits.
    """
    return cell_width(char)


def fit_columns(text: str, floor: int = 0) -> int:
    """Width, in characters, of the longest line in `text`.

    ANSI escapes are stripped first: they style the glyphs around them and
    occupy no cell of their own. Measured in terminal cells, so a line of CJK
    asks for the two columns per glyph it is drawn with.

    :param text: the text to measure, ANSI escape sequences included.
    :param floor: width to return when every line is narrower than it. A caller
        laying the text out somewhere with a minimum of its own states that
        minimum here; the default floors at nothing.
    :return: the width laying every line out without folding any.
    """
    return max(
        [floor, *(cell_width(unstyle(line)) for line in text.splitlines())],
    )


def grid(text: str, columns: int) -> list[list[tuple[Style, str, int]]]:
    """Lay ANSI text out on a terminal's character grid.

    Where a stream of styled text stops being a stream and becomes a picture.
    Each styled run of {func}`~click_extra.styling.split_ansi` is split at
    newlines into rows, then placed on the column it starts at, measured in
    cells rather than characters so a wide glyph takes the two it is drawn
    with.

    A line reaching past `columns` soft-wraps onto the next row, the way it would
    on a terminal that narrow, rather than being cropped: a command is free to
    print a line it never wraps itself (a long URL, a wide table, a
    machine-readable dump), and a layout that silently swallowed the overflow
    would be lying about what ran. A glyph straddling the edge moves down whole.

    Returning the column with each run is what lets a renderer place a run
    without measuring anything back out of its own output.

    :param text: the text to lay out, ANSI escape sequences included.
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
                size = _char_width(char)
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


def wrap_ansi(text: str, width: int) -> list[str]:
    """Wrap *text* to *width* terminal cells, preserving its ANSI styling.

    {func}`textwrap.wrap` counts every byte of an ANSI escape toward the line
    length, so a styled string wraps far earlier than its visible width
    warrants. `wcwidth.wrap` measures an escape at no cells and every
    character between escapes at the width a terminal advances by. It reopens
    on each line the styling still in effect, so no escape sequence crosses a
    line boundary: each returned line carries the styling it needs, opened and
    closed within the line.

    Returns a list of lines, empty *text* yielding a single empty one.

    ```{note}
    Breaks land where {func}`textwrap.wrap` puts them on plain ASCII, so
    long-word breaking and whitespace handling match it exactly. The two
    measures part on a double-width character, which counts for the two cells
    it takes, and on an OSC 8 hyperlink, which counts for none.
    ```
    """
    # Tab expansion would change the visible width of the text. Disabled,
    # `replace_whitespace` still substitutes a single space for each whitespace
    # character, which preserves it.
    return wcwidth_wrap(text, width, expand_tabs=False) or [""]
