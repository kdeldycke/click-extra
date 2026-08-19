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
"""Tests for the `todolist` deduplication hook."""

from __future__ import annotations

import re
import sys
from textwrap import dedent

import pytest
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from click_extra.sphinx.todos import is_reexport, todo_identity

TODO_SOURCE_RE = re.compile(
    r'<p class="todo-source">\(The <a class="reference internal" '
    r'href="([^"]+)">.*?located in (.*?), line (\d+)\.\)</p>',
    re.DOTALL,
)
"""Captures the page, the origin and the line of every rendered todo entry.

`sphinx.ext.todo` emits one such paragraph per entry it puts on a
`todolist`, so counting them counts the entries.
"""

PACKAGE_INIT = dedent("""\
    \"\"\"An orchard.\"\"\"

    from .harvest import pick

    __all__ = ["pick"]
    """)

PACKAGE_MODULE = dedent("""\
    \"\"\"Fruit picking.\"\"\"


    def pick(basket):
        \"\"\"Fill ``basket`` with ripe fruit.

        .. todo::
           Weigh the basket before handing it over.
        \"\"\"
        return basket


    def prune(tree):
        \"\"\"Cut the dead wood out of ``tree``.

        .. todo::
           Skip the cut when the tree is still in blossom.
        \"\"\"
        return tree
    """)


def build_orchard(tmp_path, package, pages, *, dedupe=None, todo_extension=True):
    """Build a throwaway project documenting `package`, and return its todo entries.

    `pages` maps a docname to its reStructuredText body. A `todos` page
    carrying the `todolist` is always appended, and every page is wired into
    the root toctree.

    `package` names the generated package, and must differ between tests: the
    modules are imported by autodoc into the running interpreter, where
    `sys.modules` would otherwise serve the first test's copy to every later
    one.

    Returns the `(page, origin, line)` triples the `todolist` page rendered,
    in document order.
    """
    srcdir = tmp_path / "source"
    (srcdir / package).mkdir(parents=True)
    (srcdir / package / "__init__.py").write_text(PACKAGE_INIT, encoding="utf-8")
    (srcdir / package / "harvest.py").write_text(PACKAGE_MODULE, encoding="utf-8")

    extensions = ["sphinx.ext.autodoc", "click_extra.sphinx"]
    if todo_extension:
        extensions.insert(1, "sphinx.ext.todo")
    conf = [
        "import sys",
        "from pathlib import Path",
        "sys.path.insert(0, str(Path(__file__).parent))",
        'master_doc = "index"',
        f"extensions = {extensions!r}",
        "todo_include_todos = True",
    ]
    if dedupe is not None:
        conf.append(f"click_extra_dedupe_todos = {dedupe!r}")
    (srcdir / "conf.py").write_text("\n".join(conf), encoding="utf-8")

    pages = {**pages, "todos": ".. todolist::\n"}
    for docname, body in pages.items():
        (srcdir / f"{docname}.rst").write_text(body, encoding="utf-8")
    toctree = "\n".join(f"   {docname}" for docname in pages)
    (srcdir / "index.rst").write_text(
        f"Orchard\n=======\n\n.. toctree::\n\n{toctree}\n", encoding="utf-8"
    )

    outdir = tmp_path / "build"
    try:
        with docutils_namespace():
            app = Sphinx(
                str(srcdir),
                str(srcdir),
                str(outdir),
                str(outdir / ".doctrees"),
                "html",
                verbosity=0,
                warning=None,
            )
            app.build()
    finally:
        sys.path[:] = [p for p in sys.path if p != str(srcdir)]
        for name in [
            m for m in sys.modules if m == package or m.startswith(f"{package}.")
        ]:
            del sys.modules[name]

    return TODO_SOURCE_RE.findall((outdir / "todos.html").read_text(encoding="utf-8"))


def automodule(target, no_index=False):
    """Render an `automodule` block for `target`."""
    body = f".. automodule:: {target}\n   :members:\n"
    if no_index:
        body += "   :no-index:\n"
    return f"{target}\n{'=' * len(target)}\n\n{body}"


def test_todo_identity_ignores_the_import_path_of_a_docstring():
    """Two renderings of one docstring share an identity whatever reached it."""

    class FakeNode:
        def __init__(self, source, line):
            self.source, self.line = source, line

    through_module = FakeNode("/src/orchard/harvest.py:docstring of orchard.pick", 4)
    through_package = FakeNode("/src/orchard/__init__.py:docstring of orchard.pick", 4)
    assert todo_identity(through_module) == todo_identity(through_package)
    assert todo_identity(through_module) == ("orchard.pick", 4)

    # A plain document keeps its path: two files may hold a todo on one line.
    assert todo_identity(FakeNode("/src/guide.rst", 4)) == ("/src/guide.rst", 4)
    assert todo_identity(FakeNode("/src/guide.rst", 4)) != todo_identity(
        FakeNode("/src/other.rst", 4)
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("/src/orchard/__init__.py:docstring of orchard.pick", True),
        ("/src/orchard/harvest.py:docstring of orchard.harvest.pick", False),
        # A document is never a re-export, whatever it is named.
        ("/src/__init__.py", False),
        ("", False),
    ),
)
def test_is_reexport(source, expected):
    """Only a docstring reached through a package `__init__` ranks as re-exported."""

    class FakeNode:
        source = None
        line = 1

    node = FakeNode()
    node.source = source
    assert is_reexport(node) is expected


def test_full_api_page_and_feature_page_yield_one_entry_each(tmp_path):
    """A module documented twice across pages lists each todo once."""
    entries = build_orchard(
        tmp_path,
        "orchard_pages",
        {
            "api": automodule("orchard_pages.harvest"),
            "feature": automodule("orchard_pages.harvest", no_index=True),
        },
    )
    assert len(entries) == 2
    assert {origin.rsplit(" ", 1)[-1] for _, origin, _ in entries} == {
        "orchard_pages.harvest.pick",
        "orchard_pages.harvest.prune",
    }


def test_reexported_members_yield_one_entry_each(tmp_path):
    """A member documented under both its package and its module lists once."""
    entries = build_orchard(
        tmp_path,
        "orchard_reexport",
        {
            "api": (
                automodule("orchard_reexport")
                + "\n"
                + automodule("orchard_reexport.harvest")
            ),
        },
    )
    # `pick` is re-exported and rendered twice, `prune` only once.
    assert len(entries) == 2


def test_surviving_entry_attributes_to_the_defining_module(tmp_path):
    """The kept rendering names the module defining the object, not the package."""
    entries = build_orchard(
        tmp_path,
        "orchard_attribution",
        {
            "api": (
                automodule("orchard_attribution")
                + "\n"
                + automodule("orchard_attribution.harvest")
            ),
        },
    )
    origins = [origin for _, origin, _ in entries]
    assert any("harvest.py:docstring of" in origin for origin in origins)
    assert not any("__init__.py:docstring of" in origin for origin in origins)


def test_dedupe_switched_off_restores_every_rendering(tmp_path):
    """`click_extra_dedupe_todos = False` gives Sphinx's raw output back."""
    pages = {
        "api": automodule("orchard_off.harvest"),
        "feature": automodule("orchard_off.harvest", no_index=True),
    }
    entries = build_orchard(tmp_path, "orchard_off", pages, dedupe=False)
    assert len(entries) == 4


def test_distinct_todos_all_survive(tmp_path):
    """Deduplication collapses repeats, never two different directives."""
    entries = build_orchard(
        tmp_path,
        "orchard_distinct",
        {"api": automodule("orchard_distinct.harvest")},
    )
    identities = {(origin, line) for _, origin, line in entries}
    assert len(identities) == 2


def test_build_succeeds_without_the_todo_extension(tmp_path):
    """The hook is inert on a project that never registered the todo domain."""
    entries = build_orchard(
        tmp_path,
        "orchard_no_ext",
        {"api": automodule("orchard_no_ext.harvest")},
        todo_extension=False,
    )
    assert entries == []
