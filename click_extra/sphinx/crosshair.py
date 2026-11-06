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
"""Highlight the row and the column under the pointer in a two-axis table.

A reader of a two-axis table traces each cell back to its row label and its
column header. On a wide grid, like a feature comparison across a dozen
projects, that means counting columns. This module ships a script that
highlights the row and the column of the cell under the pointer, headers
included, and the cell itself more strongly.

The script also makes a cell whose whole content is one link clickable over its
full area, like a cell holding only a check mark that links to its evidence.

Both apply to the tables {mod}`click_extra.sphinx.tables` marks with
{data}`~click_extra.sphinx.tables.CORNER_TABLE_CLASS`: the ones whose top-left
cell names both axes. Other tables are left as they are. The stylesheet and the
script are written into the build rather than packaged as data files.
"""

from __future__ import annotations

from .tables import CORNER_TABLE_CLASS, _write_static_file

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx


CROSSHAIR_CSS = """\
/* Hovered row and column. The row rule matches the `tr` the script marks, and
 * keeps the specificity of the column rule: one notch higher, it would outrank
 * the rule of the hovered cell below. */
table td.crosshair-col,
table th.crosshair-col,
tr.crosshair-row > td,
tr.crosshair-row > th {
  background-color: var(--color-background-hover, rgba(128, 128, 128, 0.12));
}

/* The hovered cell, outlined to mark the intersection. */
table td.crosshair-cell,
table th.crosshair-cell {
  background-color: var(--color-highlight-on-target, rgba(255, 209, 0, 0.4));
  outline: 2px solid var(--color-brand-primary, #336790);
  outline-offset: -2px;
}

/* A cell whose whole content is one link: the link's hit area covers the
 * cell. The link itself is untouched, so keyboard focus and middle-click keep
 * working, and the overlay is transparent, so the highlight shows through. */
table td.linked-cell,
table th.linked-cell {
  position: relative;
  cursor: pointer;
}
table td.linked-cell a[href]::after,
table th.linked-cell a[href]::after {
  content: "";
  position: absolute;
  inset: 0;
}
"""
"""Stylesheet of the classes the crosshair script sets.

The colors come from Furo's CSS variables, so the highlight follows Furo's light
and dark modes. Each variable carries a fallback for other themes.
"""

CROSSHAIR_JS = (
    """\
(function (selector) {
  function ready(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else {
      document.addEventListener("DOMContentLoaded", fn);
    }
  }

  ready(function () {
    Array.prototype.forEach.call(document.querySelectorAll(selector), function (table) {
      // Mark each cell whose whole content is one link. A cell mixing a link
      // with other text, like a header with a footnote marker, is left alone.
      Array.prototype.forEach.call(table.querySelectorAll("td, th"), function (cell) {
        var links = cell.querySelectorAll("a[href]");
        if (
          links.length === 1 &&
          cell.textContent.trim() === links[0].textContent.trim()
        ) {
          cell.classList.add("linked-cell");
        }
      });

      // A merged cell shifts the cells after it in its row, so a cell index no
      // longer names a visual column.
      if (table.querySelector("[colspan], [rowspan]")) {
        return;
      }

      function clear() {
        var marked = table.querySelectorAll(
          ".crosshair-col, .crosshair-row, .crosshair-cell"
        );
        Array.prototype.forEach.call(marked, function (element) {
          element.classList.remove("crosshair-col", "crosshair-row", "crosshair-cell");
        });
      }

      table.addEventListener("mouseover", function (event) {
        var cell = event.target.closest("td, th");
        if (!cell || !table.contains(cell)) {
          return;
        }
        var column = cell.cellIndex;
        clear();
        // The column: the cell at the same index in every row, header included.
        Array.prototype.forEach.call(table.rows, function (row) {
          var columnCell = row.cells[column];
          if (columnCell) {
            columnCell.classList.add("crosshair-col");
          }
        });
        cell.parentElement.classList.add("crosshair-row");
        cell.classList.add("crosshair-cell");
      });

      table.addEventListener("mouseleave", clear);
    });
  });
})"""
    + f'("table.{CORNER_TABLE_CLASS}");\n'
)
"""Script setting the crosshair and full-cell link classes on two-axis tables.

The selector of the tables is the argument of the outer function, so the class
{mod}`click_extra.sphinx.tables` sets is named in one place.
"""

STYLESHEET = "click-extra-crosshair.css"
"""File name of the stylesheet, served from the `_static` folder."""

SCRIPT = "click-extra-crosshair.js"
"""File name of the script, served from the `_static` folder."""


def add_crosshair(app: Sphinx) -> None:
    """Write {data}`CROSSHAIR_CSS` and {data}`CROSSHAIR_JS` into the build.

    Both files go to the static folder of the extension (see
    `click_extra.sphinx.tables._write_static_file`), and every page links them.
    Only an HTML builder serves them, so other builders skip it.
    """
    if app.builder.format != "html":
        return
    _write_static_file(app, STYLESHEET, CROSSHAIR_CSS)
    _write_static_file(app, SCRIPT, CROSSHAIR_JS)
    app.add_css_file(STYLESHEET)
    app.add_js_file(SCRIPT)


def setup(app: Sphinx) -> None:
    """Register the crosshair stylesheet and script on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. The tables it applies to are
    marked by {func}`click_extra.sphinx.tables.mark_corner_tables`.
    """
    app.connect("builder-inited", add_crosshair)
