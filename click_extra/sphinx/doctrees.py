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
"""Keep the build environment out of each pickled page.

Sphinx pickles the doctree of every page it reads. Before it does, it removes
the build environment from a copy of the page's settings. A node that belongs to
another document escapes that copy: it pickles its own document, whose settings
still hold the whole environment. On a project with an API reference, each page
holding such nodes then weighs megabytes, and a build writes hundreds of them.

Two parsers leave such nodes. myst-parser parses an ``{eval-rst}`` block into a
throwaway document that shares the page's settings, then moves the parsed nodes
into the page. docutils points each moved node at the page, but not its
descendants, which keep the throwaway document as theirs. The `python:render-rst`
and `python:render-myst` directives of {mod}`click_extra.sphinx.python` parse
their output into a throwaway document the same way.

This module points every node of a page at the page's own document, once Sphinx
has read the page and before it pickles it.

```{todo}
Re-scope this module once myst-parser parses an ``{eval-rst}`` block into the
page's own document, which
[executablebooks/MyST-Parser#1212](https://github.com/executablebooks/MyST-Parser/issues/1212)
asks for in its item 3, and the `sphinx` extra's myst-parser floor passes that
release. The hook then only serves the `python:render-*` directives, which can
point their nodes at the page where they parse them, and the module can go.
```
"""

from __future__ import annotations

TYPE_CHECKING = False
if TYPE_CHECKING:
    from docutils import nodes
    from sphinx.application import Sphinx


def rehome_moved_nodes(app: Sphinx, doctree: nodes.document) -> None:
    """Point every node of `doctree` at `doctree` itself.

    A node moved in from a throwaway document keeps that document, and with it
    a reference to the build environment, through its settings. Pointing the
    node at the page lets it pickle without them.
    """
    for node in doctree.findall():
        if node.document is not doctree:
            node.document = doctree


def setup(app: Sphinx) -> None:
    """Register the rehoming hook on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. `doctree-read` is the last
    event before Sphinx pickles a page, and priority 900 runs the hook after
    the handlers at the default 500, which can add nodes to the page too.
    """
    app.connect("doctree-read", rehome_moved_nodes, priority=900)
