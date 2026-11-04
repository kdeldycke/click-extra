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
"""Tests for the crosshair of two-axis tables."""

from __future__ import annotations

from pathlib import Path

from click_extra.sphinx.crosshair import CROSSHAIR_CSS, CROSSHAIR_JS, SCRIPT, STYLESHEET
from click_extra.sphinx.tables import CORNER_TABLE_CLASS, STATIC_DIR


def test_crosshair_ships_with_every_page(sphinx_app_myst) -> None:
    """Every page links the stylesheet and the script, written from their sources.

    The static folder they share with the table stylesheet is listed once.
    """
    html = sphinx_app_myst.build_document("# Orchard\n\nApples ripen in autumn.\n")
    assert html is not None
    assert f'href="_static/{STYLESHEET}' in html
    assert f'src="_static/{SCRIPT}' in html

    static = Path(sphinx_app_myst.outdir) / "_static"
    assert (static / STYLESHEET).read_text(encoding="UTF-8") == CROSSHAIR_CSS
    assert (static / SCRIPT).read_text(encoding="UTF-8") == CROSSHAIR_JS

    static_dir = str(Path(sphinx_app_myst.outdir) / STATIC_DIR)
    assert sphinx_app_myst.config.html_static_path.count(static_dir) == 1


def test_script_targets_corner_tables_only() -> None:
    """The script selects the tables {mod}`click_extra.sphinx.tables` marks."""
    assert CROSSHAIR_JS.endswith(f'("table.{CORNER_TABLE_CLASS}");\n')
    assert "querySelectorAll(selector)" in CROSSHAIR_JS
