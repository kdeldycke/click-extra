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
"""Tests for the styling of corner-labeled tables."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from click_extra.sphinx.matrix import FORBIDDEN_CELL, SUPPORTED_CELL, UNDECLARED_CELL
from click_extra.sphinx.tables import (
    CORNER_TABLE_CLASS,
    CORNER_TABLE_CSS,
    FORBIDDEN_CELL_CLASS,
    STATE_CELL_CLASSES,
    STYLESHEET,
    SUPPORTED_CELL_CLASS,
    UNDECLARED_CELL_CLASS,
)
from click_extra.table import corner_header


def test_corner_tables_keep_their_first_column_whole(sphinx_app_myst) -> None:
    """Only a table whose first header cell holds the corner label is marked.

    The glyph in any other header cell marks nothing, and every page links the
    stylesheet the mark hooks into.
    """
    # Doubled backslash: the form mdformat writes in a Markdown source.
    corner = corner_header("City", "Month").replace("\\", "\\\\")
    html = sphinx_app_myst.build_document(
        f"| {corner} | Jan | Jul |\n"
        "| :-- | :-: | :-: |\n"
        "| Paris | 7 | 25 |\n"
        "\n"
        "| City | Country |\n"
        "| :-- | :-- |\n"
        "| Oslo | Norway |\n"
        "\n"
        f"| City | {corner} |\n"
        "| :-- | :-- |\n"
        "| Lima | 22 |\n"
    )
    assert html is not None
    tables = re.findall(r"<table[^>]*>", html)
    assert len(tables) == 3
    assert [CORNER_TABLE_CLASS in table for table in tables] == [True, False, False]

    assert f"_static/{STYLESHEET}" in html
    stylesheet = Path(sphinx_app_myst.outdir) / "_static" / STYLESHEET
    assert stylesheet.read_text(encoding="UTF-8") == CORNER_TABLE_CSS


def test_matrix_cells_are_tinted_by_state(sphinx_app_myst) -> None:
    """A state glyph alone in a body cell of a corner table marks that cell.

    A glyph next to other text marks nothing, and nor does a glyph in a table
    without a corner label.
    """
    corner = corner_header("Fruit", "Month").replace("\\", "\\\\")
    html = sphinx_app_myst.build_document(
        f"| {corner} | Jan | Jul | Oct |\n"
        "| :-- | :-: | :-: | :-: |\n"
        f"| Apple | {SUPPORTED_CELL} | {FORBIDDEN_CELL} | {UNDECLARED_CELL} |\n"
        f"| Pear | {SUPPORTED_CELL} ripe | 4 | 7 |\n"
        "\n"
        "| Fruit | Jan |\n"
        "| :-- | :-: |\n"
        f"| Plum | {SUPPORTED_CELL} |\n"
    )
    assert html is not None
    corner_table, plain_table = re.findall(r"<table.*?</table>", html, re.DOTALL)
    marked = re.findall(r'<td class="[^"]*\b(matrix-\w+)\b', corner_table)
    assert marked == [SUPPORTED_CELL_CLASS, FORBIDDEN_CELL_CLASS, UNDECLARED_CELL_CLASS]
    assert "matrix-" not in plain_table


@pytest.mark.parametrize("glyph", [SUPPORTED_CELL, FORBIDDEN_CELL, UNDECLARED_CELL])
def test_every_state_has_a_tint(glyph: str) -> None:
    """Each cell state of a matrix maps to a class the stylesheet tints."""
    assert f"td.{STATE_CELL_CLASSES[glyph]} {{\n  --matrix-tint:" in CORNER_TABLE_CSS
