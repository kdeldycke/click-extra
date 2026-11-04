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
"""Tests for the document each node of a pickled page belongs to."""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "block",
    (
        pytest.param("```{eval-rst}\n- Apples\n- Pears\n```", id="eval-rst"),
        pytest.param(
            "```{python:render-rst}\nprint('- Apples')\nprint('- Pears')\n```",
            id="python-render-rst",
        ),
        pytest.param(
            "```{python:render-myst}\nprint('- Apples')\nprint('- Pears')\n```",
            id="python-render-myst",
        ),
    ),
)
def test_pickled_nodes_belong_to_their_page(sphinx_app_myst, block):
    """Every node of a pickled page belongs to the page's document.

    Each block parses a list in a document of its own, then moves it into the
    page. docutils points the list at the page, and leaves each item below it
    pointing at the document it was parsed in.
    """
    html = sphinx_app_myst.build_document(f"# Orchard\n\n{block}\n")
    assert html is not None
    assert "<li><p>Pears</p></li>" in html

    doctree_path = Path(sphinx_app_myst.doctreedir) / "index.doctree"
    doctree = pickle.loads(doctree_path.read_bytes())
    foreign = [
        node.tagname for node in doctree.findall() if node.document is not doctree
    ]
    assert not foreign
