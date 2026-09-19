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
"""Tests for the one-line first column of corner-labeled tables."""

from __future__ import annotations

import re
from pathlib import Path

from click_extra.sphinx.tables import (
    CORNER_TABLE_CLASS,
    CORNER_TABLE_CSS,
    STYLESHEET,
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
