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
"""Style the two-axis tables of a Sphinx build.

A table whose top-left cell names both of its axes, as
{func}`~click_extra.table.corner_header` spells them, is read down its first
column and across its headers. On a narrow screen, a browser wraps that first
column wherever it can, including after the hyphen of `click-extra` or of a
date, which splits every label over several lines. The labels of such a table
are short, so this module keeps each one whole: the table scrolls sideways
instead, inside the `table-wrapper` Furo puts around every table.

A compatibility matrix is such a table, and each of its cells holds the glyph of
a state (see {mod}`click_extra.sphinx.matrix`). This module tints those cells
green, red or grey by state, so the shape of the support reads at a glance.

The extension marks every table whose first header cell holds
{data}`~click_extra.table.CORNER_GLYPH`, and each of its body cells holding a
state glyph alone, then ships the stylesheet the marks hook into. The
stylesheet is written into the build rather than packaged as a data file.
"""

from __future__ import annotations

from pathlib import Path

from docutils import nodes

from ..table import CORNER_GLYPH
from .matrix import FORBIDDEN_CELL, SUPPORTED_CELL, UNDECLARED_CELL

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx


CORNER_TABLE_CLASS = "corner-table"
"""HTML class of a table whose top-left cell names both of its axes."""

SUPPORTED_CELL_CLASS = "matrix-supported"
"""HTML class of a cell holding {data}`~click_extra.sphinx.matrix.SUPPORTED_CELL`."""

FORBIDDEN_CELL_CLASS = "matrix-forbidden"
"""HTML class of a cell holding {data}`~click_extra.sphinx.matrix.FORBIDDEN_CELL`."""

UNDECLARED_CELL_CLASS = "matrix-undeclared"
"""HTML class of a cell holding {data}`~click_extra.sphinx.matrix.UNDECLARED_CELL`."""

STATE_CELL_CLASSES: dict[str, str] = {
    SUPPORTED_CELL: SUPPORTED_CELL_CLASS,
    FORBIDDEN_CELL: FORBIDDEN_CELL_CLASS,
    UNDECLARED_CELL: UNDECLARED_CELL_CLASS,
}
"""The HTML class of each state glyph, for a body cell holding that glyph alone."""

CORNER_TABLE_CSS = f"""\
table.{CORNER_TABLE_CLASS} th:first-child,
table.{CORNER_TABLE_CLASS} td:first-child {{
  white-space: nowrap;
}}

/* State tints are translucent, so they read on light and dark themes alike.
 * Each is drawn as a background image, which layers over the background color
 * the crosshair sets on hover instead of hiding it. */
table.{CORNER_TABLE_CLASS} td.{SUPPORTED_CELL_CLASS} {{
  --matrix-tint: rgba(46, 160, 67, 0.15);
}}
table.{CORNER_TABLE_CLASS} td.{FORBIDDEN_CELL_CLASS} {{
  --matrix-tint: rgba(248, 81, 73, 0.15);
}}
table.{CORNER_TABLE_CLASS} td.{UNDECLARED_CELL_CLASS} {{
  --matrix-tint: rgba(128, 128, 128, 0.1);
}}
table.{CORNER_TABLE_CLASS} td.{SUPPORTED_CELL_CLASS},
table.{CORNER_TABLE_CLASS} td.{FORBIDDEN_CELL_CLASS},
table.{CORNER_TABLE_CLASS} td.{UNDECLARED_CELL_CLASS} {{
  background-image: linear-gradient(var(--matrix-tint), var(--matrix-tint));
}}
"""
"""Stylesheet of corner-labeled tables.

Keeps their first column on one line, and tints the state cells of a matrix.
"""

STATIC_DIR = "_click_extra_static"
"""Output folder of the stylesheets and scripts the extension writes.

Sphinx copies it into `_static` with the other static files, as it does for
every folder listed in `html_static_path`. See `_write_static_file`.
"""

STYLESHEET = "click-extra.css"
"""File name of the stylesheet, served from the `_static` folder."""


def mark_corner_tables(app: Sphinx, doctree: nodes.document) -> None:
    """Add {data}`CORNER_TABLE_CLASS` to every table with a corner label.

    Each body cell of such a table holding a state glyph alone also gets the
    class of that state (see {data}`STATE_CELL_CLASSES`).
    """
    for table in doctree.findall(nodes.table):
        header = next(table.findall(nodes.thead), None)
        if header is None:
            continue
        corner = next(header.findall(nodes.entry), None)
        if corner is None or CORNER_GLYPH not in corner.astext():
            continue
        table["classes"].append(CORNER_TABLE_CLASS)
        for body in table.findall(nodes.tbody):
            for entry in body.findall(nodes.entry):
                state = STATE_CELL_CLASSES.get(entry.astext().strip())
                if state:
                    entry["classes"].append(state)


def _write_static_file(app: Sphinx, name: str, content: str) -> None:
    """Write `content` to the file `name` of {data}`STATIC_DIR` in the build.

    The folder joins `html_static_path` with its first file, whichever module
    writes it, so Sphinx serves every file of the folder from `_static`.
    """
    static_dir = Path(app.outdir) / STATIC_DIR
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / name).write_text(content, encoding="UTF-8")
    if str(static_dir) not in app.config.html_static_path:
        app.config.html_static_path.append(str(static_dir))


def add_stylesheet(app: Sphinx) -> None:
    """Write {data}`CORNER_TABLE_CSS` into the build and link it from each page.

    Only an HTML builder serves stylesheets, so other builders skip it.
    """
    if app.builder.format != "html":
        return
    _write_static_file(app, STYLESHEET, CORNER_TABLE_CSS)
    app.add_css_file(STYLESHEET)


def setup(app: Sphinx) -> None:
    """Register the table marker and its stylesheet on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`.
    """
    app.connect("doctree-read", mark_corner_tables)
    app.connect("builder-inited", add_stylesheet)
