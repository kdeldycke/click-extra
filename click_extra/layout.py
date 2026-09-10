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

from boltons.strutils import strip_ansi
from click import style
from wcwidth import wcswidth

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
