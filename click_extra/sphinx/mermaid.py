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
"""Let the page scroll over the class diagrams of `autoclasstree`.

With `mermaid_d3_zoom = True`, sphinxcontrib-mermaid attaches d3's wheel and drag
handlers to the `<svg>` of every diagram on a page. It has no per-diagram
opt-out, and the zoom of its fullscreen viewer needs the same option. A class
inheritance tree is often taller than the screen, and the wheel then zooms the
diagram where the reader wants to scroll the page.

This module overrides the `autoclasstree` directive of sphinxcontrib-mermaid
with a subclass that wraps each diagram in a container of the
{data}`AUTOCLASSTREE_CLASS` class. {data}`NO_ZOOM_CSS` turns off the pointer
events of the inline `<svg>` in that container: the events never reach it,
d3's handlers never fire, and the wheel scrolls the page. The fullscreen viewer
clones the diagram outside the container, so its button and its zoom still
work. The stylesheet is written into the build rather than packaged as a data
file.

The module is inert on a project that does not load `sphinxcontrib.mermaid`, or
that leaves `mermaid_d3_zoom` off.
"""

from __future__ import annotations

from docutils import nodes

from .tables import _write_static_file

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

    from docutils.parsers.rst import Directive
    from sphinx.application import Sphinx


MERMAID_EXTENSION = "sphinxcontrib.mermaid"
"""Module name of the extension whose `autoclasstree` directive is overridden."""

AUTOCLASSTREE_CLASS = "autoclasstree"
"""HTML class of the container wrapping each `autoclasstree` diagram."""

NO_ZOOM_CSS = f"""\
/* With pointer events off, the inline <svg> never becomes an event target, so
 * d3's wheel and drag handlers never fire, and the wheel scrolls the page. The
 * fullscreen viewer clones the diagram outside the container, so its button
 * and its zoom keep working. */
.{AUTOCLASSTREE_CLASS} pre.mermaid svg {{
  pointer-events: none;
}}
"""
"""Stylesheet keeping the pointer off the inline diagram of each container."""

STYLESHEET = "click-extra-mermaid.css"
"""File name of the stylesheet, served from the `_static` folder."""


def _no_zoom_class_diagram() -> type[Directive]:
    """Subclass the `autoclasstree` directive of sphinxcontrib-mermaid.

    The subclass wraps the nodes of each diagram in a container of the
    {data}`AUTOCLASSTREE_CLASS` class, which {data}`NO_ZOOM_CSS` targets.
    """
    # Deferred import: sphinxcontrib.mermaid is an optional extension, and
    # click_extra.sphinx must import without it.
    from sphinxcontrib.mermaid import MermaidClassDiagram

    class NoZoomClassDiagram(MermaidClassDiagram):
        """`autoclasstree`, with its diagram wrapped in a marked container."""

        def run(self, **kwargs: Any) -> list[nodes.Node]:
            return [
                nodes.container(
                    "", *super().run(**kwargs), classes=[AUTOCLASSTREE_CLASS]
                )
            ]

    return NoZoomClassDiagram


def override_class_diagrams(app: Sphinx) -> None:
    """Register the zoom-free `autoclasstree` and its stylesheet on `app`.

    Connected to `builder-inited`, which fires once every extension is set up,
    whatever their order in `extensions`: the directive to override is then
    registered, and `mermaid_d3_zoom` holds the value of `conf.py`. Inert
    without `sphinxcontrib.mermaid`, or with `mermaid_d3_zoom` off. Only an HTML
    builder serves the stylesheet, so other builders get the directive alone.
    """
    if MERMAID_EXTENSION not in app.extensions or not app.config.mermaid_d3_zoom:
        return
    app.add_directive("autoclasstree", _no_zoom_class_diagram(), override=True)
    if app.builder.format == "html":
        _write_static_file(app, STYLESHEET, NO_ZOOM_CSS)
        app.add_css_file(STYLESHEET)


def setup(app: Sphinx) -> None:
    """Register the class diagram override on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`.
    """
    app.connect("builder-inited", override_class_diagrams)
