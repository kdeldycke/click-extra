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
"""Tests for the `autoclasstree` override that keeps d3 zoom off class diagrams."""

from __future__ import annotations

import re
import sys
from io import StringIO
from types import ModuleType
from typing import Any

import pytest
from docutils import nodes
from docutils.parsers.rst import Directive
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace, is_directive_registered

from click_extra.sphinx.mermaid import (
    AUTOCLASSTREE_CLASS,
    MERMAID_EXTENSION,
    NO_ZOOM_CSS,
    STYLESHEET,
)

DIAGRAM = "Class diagram of orchard.Pear."
"""Text the stand-in `autoclasstree` renders for each diagram."""


class StubClassDiagram(Directive):
    """Stand-in for the `autoclasstree` directive of sphinxcontrib-mermaid."""

    required_arguments = 1

    def run(self, **kwargs: Any) -> list[nodes.Node]:
        return [nodes.paragraph(DIAGRAM, DIAGRAM)]


def stub_setup(app: Sphinx) -> dict[str, bool]:
    """Register what the override reads of sphinxcontrib-mermaid."""
    app.add_config_value("mermaid_d3_zoom", False, "html")
    app.add_directive("autoclasstree", StubClassDiagram)
    return {"parallel_read_safe": True, "parallel_write_safe": True}


@pytest.fixture
def mermaid_stub(monkeypatch) -> None:
    """Serve a stand-in for sphinxcontrib-mermaid, which the test group lacks.

    The stand-in only holds the directive and the config value the override
    reads.
    """
    module = ModuleType(MERMAID_EXTENSION)
    module.__dict__.update(MermaidClassDiagram=StubClassDiagram, setup=stub_setup)
    monkeypatch.setitem(sys.modules, MERMAID_EXTENSION, module)


def build(tmp_path, *, loaded: bool, d3_zoom: bool | None) -> tuple[str, bool]:
    """Build a page, with an `autoclasstree` diagram when the stand-in is loaded.

    `click_extra.sphinx` comes first in `extensions`, before the directive it
    overrides is registered. `d3_zoom` sets `mermaid_d3_zoom`, left to its
    default when `None`.

    :return: the HTML of the page, and whether `autoclasstree` is registered.
    """
    srcdir = tmp_path / "source"
    srcdir.mkdir()
    extensions = ["click_extra.sphinx", *([MERMAID_EXTENSION] if loaded else [])]
    conf = [f"extensions = {extensions!r}"]
    if d3_zoom is not None:
        conf.append(f"mermaid_d3_zoom = {d3_zoom!r}")
    (srcdir / "conf.py").write_text("\n".join(conf), encoding="UTF-8")
    page = "Orchard\n=======\n"
    if loaded:
        page += "\n.. autoclasstree:: orchard.Pear\n"
    (srcdir / "index.rst").write_text(page, encoding="UTF-8")
    outdir = tmp_path / "build"
    with docutils_namespace():
        app = Sphinx(
            str(srcdir),
            str(srcdir),
            str(outdir),
            str(outdir / ".doctrees"),
            "html",
            status=None,
            warning=StringIO(),
        )
        app.build()
        registered = is_directive_registered("autoclasstree")
    return (outdir / "index.html").read_text(encoding="UTF-8"), registered


@pytest.mark.usefixtures("mermaid_stub")
@pytest.mark.parametrize(
    ("loaded", "d3_zoom", "overridden"),
    [
        pytest.param(True, True, True, id="zoom-on"),
        pytest.param(True, False, False, id="zoom-off"),
        pytest.param(True, None, False, id="zoom-default"),
        pytest.param(False, True, False, id="no-mermaid"),
    ],
)
def test_class_diagrams_skip_the_zoom(
    tmp_path, loaded: bool, d3_zoom: bool | None, overridden: bool
) -> None:
    """The override wraps each diagram only with sphinxcontrib-mermaid and zoom on.

    The page then links the stylesheet the wrapper hooks into. Otherwise the
    directive renders as sphinxcontrib-mermaid draws it, or not at all.
    """
    html, registered = build(tmp_path, loaded=loaded, d3_zoom=d3_zoom)
    assert registered is loaded
    assert (DIAGRAM in html) is loaded
    wrapper = re.compile(
        rf'<div class="[^"]*\b{AUTOCLASSTREE_CLASS}\b[^"]*">\s*<p>{re.escape(DIAGRAM)}'
    )
    assert bool(wrapper.search(html)) is overridden
    assert (f"_static/{STYLESHEET}" in html) is overridden
    stylesheet = tmp_path / "build" / "_static" / STYLESHEET
    assert stylesheet.exists() is overridden
    if overridden:
        assert stylesheet.read_text(encoding="UTF-8") == NO_ZOOM_CSS
