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
"""Keep the first column of a two-axis table on one line.

A table whose top-left cell names both of its axes, as
{func}`~click_extra.table.corner_header` spells them, is read down its first
column and across its headers. On a narrow screen, a browser wraps that first
column wherever it can, including after the hyphen of `click-extra` or of a
date, which splits every label over several lines. The labels of such a table
are short, so this module keeps each one whole: the table scrolls sideways
instead, inside the `table-wrapper` Furo puts around every table.

The extension marks every table whose first header cell holds
{data}`~click_extra.table.CORNER_GLYPH`, and ships the stylesheet the mark
hooks into. The stylesheet is written into the build rather than packaged as a
data file.
"""

from __future__ import annotations

from pathlib import Path

from docutils import nodes

from ..table import CORNER_GLYPH

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx


CORNER_TABLE_CLASS = "corner-table"
"""HTML class of a table whose top-left cell names both of its axes."""

CORNER_TABLE_CSS = f"""\
table.{CORNER_TABLE_CLASS} th:first-child,
table.{CORNER_TABLE_CLASS} td:first-child {{
  white-space: nowrap;
}}
"""
"""Stylesheet keeping the first column of a corner-labeled table on one line."""

STATIC_DIR = "_click_extra_static"
"""Folder of the output directory the stylesheet is written to.

Sphinx copies it into `_static` with the other static files, as it does for
every folder listed in `html_static_path`.
"""

STYLESHEET = "click-extra.css"
"""File name of the stylesheet, served from the `_static` folder."""


def mark_corner_tables(app: Sphinx, doctree: nodes.document) -> None:
    """Add {data}`CORNER_TABLE_CLASS` to every table with a corner label."""
    for table in doctree.findall(nodes.table):
        header = next(table.findall(nodes.thead), None)
        corner = next(header.findall(nodes.entry), None) if header else None
        if corner is not None and CORNER_GLYPH in corner.astext():
            table["classes"].append(CORNER_TABLE_CLASS)


def add_stylesheet(app: Sphinx) -> None:
    """Write {data}`CORNER_TABLE_CSS` into the build and link it from each page.

    Only an HTML builder serves stylesheets, so other builders skip it.
    """
    if app.builder.format != "html":
        return
    static_dir = Path(app.outdir) / STATIC_DIR
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / STYLESHEET).write_text(CORNER_TABLE_CSS, encoding="UTF-8")
    app.config.html_static_path.append(str(static_dir))
    app.add_css_file(STYLESHEET)


def setup(app: Sphinx) -> None:
    """Register the table marker and its stylesheet on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`.
    """
    app.connect("doctree-read", mark_corner_tables)
    app.connect("builder-inited", add_stylesheet)
