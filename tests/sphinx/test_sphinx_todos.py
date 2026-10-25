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
"""Tests for the `todolist` deduplication hook and the unrendered-todo check."""

from __future__ import annotations

import re
import sys
from io import StringIO
from pathlib import Path
from textwrap import dedent

import pytest
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from click_extra.sphinx.todos import (
    UNRENDERED_TODO_WARNING,
    _package_modules,
    docstring_todos,
    is_reexport,
    todo_identity,
)

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

COMPOST_MODULE = dedent("""\
    \"\"\"Turn fallen fruit into compost.

    .. todo::
       Turn the heap once a week.
    \"\"\"
    """)
"""A module docstring with a todo on its third line."""

GRAFTING_MODULE = dedent("""\
    \"\"\"Fruit grafting.\"\"\"


    def _graft(branch):
        \"\"\"Join ``branch`` to a rootstock.

        .. todo::
           Seal the cut with wax.
        \"\"\"
        return branch
    """)
"""A module whose only todo sits in a private function, which `:members:` skips."""

UNRENDERED_RE = re.compile(
    r"(\S+):(\d+): WARNING: click_extra\.sphinx: no page renders the docstring "
    r"of (\S+), so no todolist can list this todo\."
)
"""Captures the file, the line and the owner of every unrendered-todo warning."""


def build_project(
    tmp_path,
    package,
    pages,
    *,
    files=None,
    conf=(),
    dedupe=None,
    todo_extension=True,
):
    """Build a throwaway project documenting `package`, and return the build.

    `pages` maps a docname to its reStructuredText body. A `todos` page
    carrying the `todolist` is always appended, and every page is wired into
    the root toctree.

    `package` names the generated package, and must differ between tests: the
    modules are imported by autodoc into the running interpreter, where
    `sys.modules` would otherwise serve the first test's copy to every later
    one.

    `files` maps a path inside the package to its source, written over the
    orchard's own `__init__.py` and `harvest.py`. `conf` appends lines to the
    generated `conf.py`.

    Returns the output directory, the warning stream and the exit status.
    """
    srcdir = tmp_path / "source"
    sources = {"__init__.py": PACKAGE_INIT, "harvest.py": PACKAGE_MODULE}
    sources.update(files or {})
    for relative, source in sources.items():
        path = srcdir / package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    extensions = ["sphinx.ext.autodoc", "click_extra.sphinx"]
    if todo_extension:
        extensions.insert(1, "sphinx.ext.todo")
    conf_lines = [
        "import sys",
        "from pathlib import Path",
        "sys.path.insert(0, str(Path(__file__).parent))",
        'master_doc = "index"',
        f"extensions = {extensions!r}",
        "todo_include_todos = True",
    ]
    if dedupe is not None:
        conf_lines.append(f"click_extra_dedupe_todos = {dedupe!r}")
    conf_lines.extend(conf)
    (srcdir / "conf.py").write_text("\n".join(conf_lines), encoding="utf-8")

    pages = {**pages, "todos": ".. todolist::\n"}
    for docname, body in pages.items():
        (srcdir / f"{docname}.rst").write_text(body, encoding="utf-8")
    toctree = "\n".join(f"   {docname}" for docname in pages)
    (srcdir / "index.rst").write_text(
        f"Orchard\n=======\n\n.. toctree::\n\n{toctree}\n", encoding="utf-8"
    )

    outdir = tmp_path / "build"
    warnings = StringIO()
    try:
        with docutils_namespace():
            app = Sphinx(
                str(srcdir),
                str(srcdir),
                str(outdir),
                str(outdir / ".doctrees"),
                "html",
                verbosity=0,
                warning=warnings,
            )
            app.build()
    finally:
        sys.path[:] = [p for p in sys.path if p != str(srcdir)]
        for name in [
            m for m in sys.modules if m == package or m.startswith(f"{package}.")
        ]:
            del sys.modules[name]

    return outdir, warnings.getvalue(), app.statuscode


def build_orchard(tmp_path, package, pages, **options):
    """Build a project with `build_project`, and return its todo entries.

    Returns the `(page, origin, line)` triples the `todolist` page rendered,
    in document order.
    """
    outdir, _, _ = build_project(tmp_path, package, pages, **options)
    return TODO_SOURCE_RE.findall((outdir / "todos.html").read_text(encoding="utf-8"))


def unrendered_todos(warnings):
    """Return the `(file name, line, owner)` of each unrendered-todo warning."""
    return {
        (Path(path).name, int(line), owner)
        for path, line, owner in UNRENDERED_RE.findall(warnings)
    }


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


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        pytest.param(
            """\
            \"\"\"Orchard tools.

            .. todo::
               Sharpen the shears.
            \"\"\"
            """,
            [("orchard", 3)],
            id="module-docstring",
        ),
        pytest.param(
            """\
            class Ladder:
                \"\"\"A ladder.

                ```{todo}
                Add a rung.
                ```
                \"\"\"

                def climb(self):
                    \"\"\"Climb it.

                    ```{todo}
                    Hold the rail.
                    ```
                    \"\"\"
            """,
            [("orchard.Ladder", 4), ("orchard.Ladder.climb", 12)],
            id="class-and-method",
        ),
        pytest.param(
            """\
            def plant(seed):
                \"\"\"Plant a seed.\"\"\"

                def water():
                    \"\"\"Water it.

                    :::{todo}
                    Check the forecast.
                    :::
                    \"\"\"
            """,
            [("orchard.plant.<locals>.water", 7)],
            id="nested-function-colon-fence",
        ),
        pytest.param(
            """\
            SEASON = "autumn"
            \"\"\"The harvest season.

            .. todo::
               Allow spring.
            \"\"\"

            APPLES, PEARS = 3, 4
            \"\"\"Fruit counts.

            .. todo::
               Count the plums too.
            \"\"\"


            class Basket:
                \"\"\"A basket.\"\"\"

                size: int = 10
                \"\"\"Its size.

                .. todo::
                   Measure in liters.
                \"\"\"
            """,
            [
                ("orchard.SEASON", 4),
                ("orchard.APPLES", 11),
                ("orchard.PEARS", 11),
                ("orchard.Basket.size", 22),
            ],
            id="attribute-docstrings",
        ),
        pytest.param(
            """\
            \"\"\"Orchard tools.

            ````{note}
            A note.

            ```{todo}
            Nested in the note.
            ```
            ````
            \"\"\"
            """,
            [("orchard", 6)],
            id="nested-in-directive",
        ),
        pytest.param(
            """\
            \"\"\"Orchard tools.

            ````markdown
            ```{todo}
            Quoted as an example.
            ```
            ````

            ```text
            .. todo::
               Quoted as an example.
            ```

            .. todo::
               A real one.
            \"\"\"
            """,
            [("orchard", 14)],
            id="quoted-in-code-block",
        ),
        pytest.param(
            """\
            \"\"\"Name the `{todo}` directive and ``.. todo::`` inline.\"\"\"

            # .. todo:: a comment is not a docstring.

            print(\"\"\"
            .. todo::
               An argument is not a docstring.
            \"\"\")

            \"\"\"
            .. todo::
               A string after a call is not a docstring.
            \"\"\"
            """,
            [],
            id="not-a-docstring",
        ),
        pytest.param(
            """\
            try:
                import shears
            except ImportError:

                def cut():
                    \"\"\"Cut by hand.

                    .. todo::
                       Buy shears.
                    \"\"\"
            """,
            [("orchard.cut", 8)],
            id="compound-statement",
        ),
    ),
)
def test_docstring_todos(source, expected):
    """Each todo is found at its line, under the path autodoc labels it with."""
    assert list(docstring_todos(dedent(source), "orchard")) == expected


def test_docstring_todos_rejects_invalid_source():
    """A module that does not parse raises, for the caller to skip it."""
    with pytest.raises(SyntaxError):
        list(docstring_todos("def plant(:\n", "orchard"))


def test_package_modules_walks_without_importing(tmp_path, monkeypatch):
    """Every module of a package is found, private ones included, none imported."""
    package = tmp_path / "grove"
    for relative in (
        "__init__.py",
        "trees.py",
        "_soil.py",
        "_shed/__init__.py",
        "_shed/tools.py",
        # A directory without `__init__.py` is not a package.
        "seeds/apple.py",
    ):
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""A grove."""\n', encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    found = [
        (name, path.relative_to(package)) for name, path in _package_modules("grove")
    ]
    assert found == [
        ("grove", Path("__init__.py")),
        ("grove._shed", Path("_shed/__init__.py")),
        ("grove._shed.tools", Path("_shed/tools.py")),
        ("grove._soil", Path("_soil.py")),
        ("grove.trees", Path("trees.py")),
    ]
    assert not [name for name in sys.modules if name.split(".")[0] == "grove"]


def test_unrendered_todos_warn_at_their_line(tmp_path):
    """A todo in a docstring no page renders is reported at its own line."""
    package = "orchard_unrendered"
    _, warnings, status = build_project(
        tmp_path,
        package,
        {
            "api": (
                automodule(f"{package}.harvest")
                + "\n"
                + automodule(f"{package}.grafting")
            ),
        },
        files={
            "_compost.py": COMPOST_MODULE,
            "_cellar/__init__.py": COMPOST_MODULE,
            "grafting.py": GRAFTING_MODULE,
            # A module that does not parse is skipped, not fatal.
            "_draft.py": "def draft(:\n",
        },
    )
    assert unrendered_todos(warnings) == {
        ("__init__.py", 3, f"{package}._cellar"),
        ("_compost.py", 3, f"{package}._compost"),
        ("grafting.py", 7, f"{package}.grafting._graft"),
    }
    assert f"[{UNRENDERED_TODO_WARNING}]" in warnings
    assert status == 0


def test_rendered_todos_do_not_warn(tmp_path):
    """No todo a page renders is reported, a re-exported one included."""
    package = "orchard_rendered"
    _, warnings, _ = build_project(
        tmp_path,
        package,
        {"api": automodule(package) + "\n" + automodule(f"{package}.harvest")},
    )
    assert UNRENDERED_TODO_WARNING not in warnings


def test_todo_rendered_under_another_path_does_not_warn(tmp_path):
    """A docstring autodoc labels with another path still counts as rendered.

    With its `__module__` overridden, `pick` is labeled with the path of the
    package, not with the path of the module that defines it.
    """
    package = "orchard_relabeled"
    _, warnings, _ = build_project(
        tmp_path,
        package,
        {"api": automodule(package)},
        files={"harvest.py": f'{PACKAGE_MODULE}\n\npick.__module__ = "{package}"\n'},
    )
    # `prune` is neither exported nor documented: its todo alone is reported.
    assert unrendered_todos(warnings) == {
        ("harvest.py", 16, f"{package}.harvest.prune"),
    }


@pytest.mark.parametrize(
    ("package", "options"),
    (
        pytest.param(
            "orchard_excluded",
            {"conf": ["todo_include_todos = False"]},
            id="todos-excluded",
        ),
        pytest.param("orchard_bare", {"todo_extension": False}, id="no-extension"),
        pytest.param(
            "orchard_suppressed",
            {"conf": [f"suppress_warnings = [{UNRENDERED_TODO_WARNING!r}]"]},
            id="suppressed",
        ),
    ),
)
def test_unrendered_todo_check_stays_silent(tmp_path, package, options):
    """The check is inert when no todo renders, and `suppress_warnings` hides it."""
    _, warnings, _ = build_project(
        tmp_path,
        package,
        {"api": automodule(f"{package}.harvest")},
        files={"_compost.py": COMPOST_MODULE},
        **options,
    )
    assert UNRENDERED_TODO_WARNING not in warnings


def test_listed_unrendered_todo_fails_the_build(tmp_path):
    """Listing the warning in `click_extra_fail_on_warnings` fails the build."""
    package = "orchard_fatal"
    _, warnings, status = build_project(
        tmp_path,
        package,
        {"api": automodule(f"{package}.harvest")},
        files={"_compost.py": COMPOST_MODULE},
        conf=[f"click_extra_fail_on_warnings = [{UNRENDERED_TODO_WARNING!r}]"],
    )
    assert status == 1
    assert f"({UNRENDERED_TODO_WARNING})." in warnings
