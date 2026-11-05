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
"""Tests for the vertical layout of sphinx-design tab-sets."""

from __future__ import annotations

import re
from pathlib import Path

from click_extra.sphinx.tabs import STYLESHEET, VERTICAL_TABS_CLASS, VERTICAL_TABS_CSS


def test_vertical_tabs_stylesheet_is_linked(sphinx_app_myst) -> None:
    """Every page links the stylesheet, which the build writes."""
    html = sphinx_app_myst.build_document("Apples and pears.\n")
    assert html is not None
    assert f"_static/{STYLESHEET}" in html
    stylesheet = Path(sphinx_app_myst.outdir) / "_static" / STYLESHEET
    assert stylesheet.read_text(encoding="UTF-8") == VERTICAL_TABS_CSS


def test_vertical_tabs_rules_stay_on_their_tab_set() -> None:
    """Every rule targets a tab-set marked with the class, or a direct child of it.

    Other tab-sets keep their layout, and so does a tab-set nested inside a pane
    of a vertical one.
    """
    rules = re.sub(r"/\*.*?\*/", "", VERTICAL_TABS_CSS, flags=re.DOTALL)
    selectors = [
        selector.strip()
        for block in re.findall(r"([^{}]+)\{[^{}]*\}", rules)
        for selector in block.split(",")
    ]
    assert selectors
    scoped = re.compile(rf"\.sd-tab-set\.{VERTICAL_TABS_CLASS}( > .+)?")
    assert [s for s in selectors if not scoped.fullmatch(s)] == []
