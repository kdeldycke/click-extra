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
"""Lay out a sphinx-design tab-set vertically, its labels down a left rail.

A tab-set with many tabs, like the install channels of a project, wraps its
labels into a strip that is hard to read. This module ships a stylesheet that
lays out a tab-set marked with {data}`VERTICAL_TABS_CLASS` in two columns: the
labels stack down the left, and the selected pane fills the right. On a screen
narrower than {data}`NARROW_SCREEN`, the tab-set falls back to the stock
horizontal layout.

sphinx-design keeps the radio inputs, their labels and the panes of a tab-set
as flat siblings of one flex container, so a two-column grid on that container
is enough: grid placement decouples the visual position of each sibling from
its source order. The rules use the child combinator, so a tab-set nested
inside a pane keeps the horizontal layout. The stylesheet is written into the
build rather than packaged as a data file, and is inert on a project that does
not load sphinx-design.

The class is deprecated: sphinx-design `0.8.0` lays out a tab-set the same way
with the `:orientation: vertical` option of `tab-set`, from
[executablebooks/sphinx-design#304](https://github.com/executablebooks/sphinx-design/pull/304).
Each tab-set that carries the class gets a {data}`VERTICAL_TABS_WARNING`, and
the class stops working in `11.0.0`.
"""

from __future__ import annotations

from docutils import nodes
from sphinx.util import logging

from .tables import _write_static_file

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx


logger = logging.getLogger(__name__)

VERTICAL_TABS_CLASS = "tabs-vertical"
"""The class a `tab-set` takes in its `:class:` option to lay out vertically."""

VERTICAL_TABS_WARNING = "click_extra.tabs_vertical"
"""Type and subtype of the warning about a {data}`VERTICAL_TABS_CLASS` tab-set.

List it in `suppress_warnings` to silence the warning.
"""

_REMOVAL_VERSION = "11.0.0"
"""The release in which {data}`VERTICAL_TABS_CLASS` stops working."""

NARROW_SCREEN = "50em"
"""The screen width under which a vertical tab-set falls back to horizontal tabs."""

VERTICAL_TABS_CSS = f"""\
.sd-tab-set.{VERTICAL_TABS_CLASS} {{
  display: grid;
  /* The pane's track is floored at zero: a bare `1fr` means `minmax(auto, 1fr)`,
   * whose floor grows to the widest line the pane cannot break, like a long URL
   * in a code block, and pushes the pane under the sidebar. */
  grid-template-columns: minmax(7rem, max-content) minmax(0, 1fr);
  align-items: start;
}}

/* No column gap: the marker of the active label then sits on the rule of the
 * pane, the way horizontal tabs merge an underline into an overline. */
.sd-tab-set.{VERTICAL_TABS_CLASS} > label {{
  grid-column: 1;
  text-align: left;
  padding-right: 1rem;
  border-bottom: none;
  border-right: 0.125rem solid transparent;
}}
.sd-tab-set.{VERTICAL_TABS_CLASS} > input:checked + label {{
  border-right-color: var(--sd-color-tabs-underline-active);
}}
.sd-tab-set.{VERTICAL_TABS_CLASS} > .sd-tab-content {{
  grid-column: 2;
  /* Span every row, or the height of the pane inflates the first row and
   * pushes the labels down the rail. `1 / -1` counts from the last explicit
   * row, and the grid declares none, so the span overshoots any tab count. */
  grid-row: 1 / span 99;
  align-self: stretch;
  padding: 0 0 0 1.5rem;
  /* sphinx-design rules a pane with two shadows, one above and one below. A
   * single hairline down the left edge replaces them. */
  box-shadow: -0.0625rem 0 var(--sd-color-tabs-overline);
}}

/* Too narrow for two columns: restate the values of sphinx-design, since a
 * shorthand cannot fall back to the value of another stylesheet. */
@media (max-width: {NARROW_SCREEN}) {{
  .sd-tab-set.{VERTICAL_TABS_CLASS} {{
    display: flex;
    flex-wrap: wrap;
  }}
  .sd-tab-set.{VERTICAL_TABS_CLASS} > label {{
    padding: 1em 1.25em 0.5em;
    border-right: none;
    border-bottom: 0.125rem solid transparent;
  }}
  .sd-tab-set.{VERTICAL_TABS_CLASS} > input:checked + label {{
    border-bottom-color: var(--sd-color-tabs-underline-active);
  }}
  .sd-tab-set.{VERTICAL_TABS_CLASS} > .sd-tab-content {{
    align-self: auto;
    padding: 0.75rem 0;
    box-shadow:
      0 -0.0625rem var(--sd-color-tabs-overline),
      0 0.0625rem var(--sd-color-tabs-underline);
  }}
}}
"""
"""Stylesheet laying out a tab-set marked with {data}`VERTICAL_TABS_CLASS`."""

STYLESHEET = "click-extra-tabs.css"
"""File name of the stylesheet, served from the `_static` folder."""


def add_vertical_tabs(app: Sphinx) -> None:
    """Write {data}`VERTICAL_TABS_CSS` into the build and link it from each page.

    The file goes to the static folder of the extension (see
    `click_extra.sphinx.tables._write_static_file`). Only an HTML builder serves
    it, so other builders skip it.
    """
    if app.builder.format != "html":
        return
    _write_static_file(app, STYLESHEET, VERTICAL_TABS_CSS)
    app.add_css_file(STYLESHEET)


def warn_vertical_tabs_class(app: Sphinx, doctree: nodes.document) -> None:
    """Warn about each tab-set of `doctree` marked with {data}`VERTICAL_TABS_CLASS`.

    sphinx-design gives the node of each `tab-set` and `tab-set-code` the
    `sd-tab-set` class, beside the classes of its `:class:` option.
    """
    warning_type, _, subtype = VERTICAL_TABS_WARNING.partition(".")
    for node in doctree.findall(nodes.Element):
        if "sd-tab-set" in node["classes"] and VERTICAL_TABS_CLASS in node["classes"]:
            logger.warning(
                "click_extra.sphinx: the `%s` class is deprecated and stops working "
                "in click-extra %s. Set `:orientation: vertical` on the tab-set "
                "instead, which needs sphinx-design 0.8.0.",
                VERTICAL_TABS_CLASS,
                _REMOVAL_VERSION,
                type=warning_type,
                subtype=subtype,
                location=node,
            )


def setup(app: Sphinx) -> None:
    """Register the vertical tab stylesheet and the deprecation warning on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`.
    """
    app.connect("builder-inited", add_vertical_tabs)
    app.connect("doctree-read", warn_vertical_tabs_class)
