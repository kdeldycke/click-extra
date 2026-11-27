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
"""Tests for the `sphinx.ext.viewcode` pages a build publishes."""

from __future__ import annotations

import re
import subprocess
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from sphinx.application import Sphinx
from sphinx.domains.python import ObjectEntry, PythonDomain
from sphinx.util.docutils import docutils_namespace
from sphinx.util.parallel import parallel_available

from click_extra.sphinx.viewcode import (
    forget_merged_definitions,
    keep_definitions_over_aliases,
)

FRUITS_MODULE = '''\
import re

SEED = re.compile(r"\\d+")
"""Pattern of a seed count."""

BASKET = dict
"""Container the fruits are counted in."""


def ripen(fruit):
    """Ripen a fruit."""
'''
"""A module documenting two constants that viewcode cannot link to.

viewcode looks for `SEED` in the module of its class, `re`, and finds nothing to
link to there. It looks for `BASKET`, a builtin class, in `builtins`, whose
source it cannot read at all.
"""

PUBLISHED_PAGES = ["_modules/fruits.html", "_modules/index.html"]
"""The module page of `fruits`, and the index linking to it."""


def write_project(srcdir: Path) -> None:
    """Write a project whose last document read documents `fruits`.

    No later document purges the unused `re` entry, so a serial read keeps it
    too.
    """
    srcdir.mkdir()
    (srcdir / "fruits.py").write_text(FRUITS_MODULE, encoding="UTF-8")
    extensions = ["sphinx.ext.autodoc", "sphinx.ext.viewcode", "click_extra.sphinx"]
    (srcdir / "conf.py").write_text(f"extensions = {extensions!r}", encoding="UTF-8")
    (srcdir / "index.rst").write_text(
        "Orchard\n=======\n\n.. toctree::\n\n   pears\n   plums\n", encoding="UTF-8"
    )
    (srcdir / "pears.rst").write_text("Pears\n=====\n\nPears.\n", encoding="UTF-8")
    (srcdir / "plums.rst").write_text(
        "Plums\n=====\n\n.. automodule:: fruits\n   :members:\n", encoding="UTF-8"
    )


def module_pages(outdir: Path) -> list[str]:
    """List the viewcode pages of a build, relative to its output directory."""
    return sorted(
        path.relative_to(outdir).as_posix()
        for path in (outdir / "_modules").rglob("*.html")
    )


def index_links(outdir: Path) -> list[str]:
    """List the module pages the viewcode index links to.

    The paths are relative to the output directory. Links of the page template,
    which lead out of `_modules/`, are left out.
    """
    index = outdir / "_modules" / "index.html"
    targets = {
        (index.parent / href).resolve().relative_to(outdir.resolve()).as_posix()
        for href in re.findall(r'href="([^"#:]+)"', index.read_text(encoding="UTF-8"))
    }
    return sorted(
        target
        for target in targets
        if target.startswith("_modules/") and target != "_modules/index.html"
    )


def broken_backlinks(outdir: Path) -> list[str]:
    """List the `[docs]` links of the viewcode pages that reach no anchor."""
    broken = []
    for page in sorted((outdir / "_modules").rglob("*.html")):
        for href in re.findall(
            r'class="viewcode-back" href="([^"]+)"', page.read_text(encoding="UTF-8")
        ):
            target, _, anchor = href.partition("#")
            if f'id="{anchor}"' not in (page.parent / target).read_text(
                encoding="UTF-8"
            ):
                broken.append(f"{page.relative_to(outdir).as_posix()}: {href}")
    return broken


def build_serial(srcdir: Path, outdir: Path) -> None:
    """Build the HTML pages of `srcdir` in this process, one document at a time."""
    with docutils_namespace():
        app = Sphinx(
            str(srcdir),
            str(srcdir),
            str(outdir),
            str(outdir / ".doctrees"),
            "html",
            status=StringIO(),
            warning=StringIO(),
        )
        app.build()


def build_parallel(srcdir: Path, outdir: Path) -> None:
    """Build the HTML pages of `srcdir` with two workers, in a process of its own.

    Forking the test process, which runs other threads, can deadlock the
    workers. `python -m` puts the working directory first on `sys.path`, which
    makes the modules of `srcdir` importable to autodoc.
    """
    subprocess.run(
        [
            sys.executable,
            "-m",
            "sphinx",
            "--builder",
            "html",
            "--jobs",
            "2",
            "--quiet",
            str(srcdir),
            str(outdir),
        ],
        check=True,
        cwd=srcdir,
    )


def test_serial_read_publishes_linked_modules_only(tmp_path, monkeypatch):
    """A serial read publishes no page for the module it read for nothing."""
    srcdir = tmp_path / "source"
    write_project(srcdir)
    monkeypatch.syspath_prepend(str(srcdir))
    monkeypatch.delitem(sys.modules, "fruits", raising=False)

    outdir = tmp_path / "build"
    build_serial(srcdir, outdir)

    assert module_pages(outdir) == PUBLISHED_PAGES
    assert "viewcode-back" in (outdir / "_modules" / "fruits.html").read_text(
        encoding="UTF-8"
    )


def test_module_index_links_only_published_pages(tmp_path, monkeypatch):
    """The viewcode index links no page for a module viewcode could not read.

    viewcode keeps `builtins`, where it looked for `BASKET`, as an entry set to
    `False`. It writes no page for that entry, but its index lists every entry.
    """
    srcdir = tmp_path / "source"
    write_project(srcdir)
    monkeypatch.syspath_prepend(str(srcdir))
    monkeypatch.delitem(sys.modules, "fruits", raising=False)

    outdir = tmp_path / "build"
    build_serial(srcdir, outdir)

    assert index_links(outdir) == ["_modules/fruits.html"]


@pytest.mark.skipif(not parallel_available, reason="Sphinx reads in parallel on POSIX")
def test_parallel_read_publishes_the_pages_of_a_serial_one(tmp_path):
    """A parallel read publishes the same pages as a serial one.

    Its workers merge their entries after every purge has run, which is the
    case of [sphinx-doc/sphinx#14675](https://github.com/sphinx-doc/sphinx/issues/14675).
    """
    srcdir = tmp_path / "source"
    write_project(srcdir)
    outdir = tmp_path / "build"
    build_parallel(srcdir, outdir)
    assert module_pages(outdir) == PUBLISHED_PAGES


VINEYARD_MODULES = {
    "__init__.py": "",
    "grape.py": 'class Grape:\n    """A grape of the vineyard."""\n',
    "harvest.py": (
        "from vineyard.grape import Grape\n\n"
        'MERLOT = Grape()\n"""A grape of the harvest."""\n'
    ),
}
"""A package whose `harvest` module documents an instance of a `grape` class.

viewcode reads `MERLOT` in the module of its class, `vineyard.grape`, and finds
no definition of it there.
"""


def test_backlinks_point_at_the_anchor_of_their_object(tmp_path, monkeypatch):
    """A `[docs]` link leads to its object, whatever signature viewcode read first.

    The page documents the instance before the class, so the instance creates
    the viewcode entry of `vineyard.grape` under the module path
    `vineyard.harvest`
    ([sphinx-doc/sphinx#14815](https://github.com/sphinx-doc/sphinx/pull/14815)).
    One page is enough: a serial read purges an entry only between two pages.
    """
    srcdir = tmp_path / "source"
    package = srcdir / "vineyard"
    package.mkdir(parents=True)
    for name, source in VINEYARD_MODULES.items():
        (package / name).write_text(source, encoding="UTF-8")
    extensions = ["sphinx.ext.autodoc", "sphinx.ext.viewcode", "click_extra.sphinx"]
    (srcdir / "conf.py").write_text(f"extensions = {extensions!r}", encoding="UTF-8")
    (srcdir / "index.rst").write_text(
        "Vineyard\n========\n\n"
        ".. automodule:: vineyard.harvest\n   :members:\n\n"
        ".. automodule:: vineyard.grape\n   :members:\n",
        encoding="UTF-8",
    )
    monkeypatch.syspath_prepend(str(srcdir))

    outdir = tmp_path / "build"
    try:
        build_serial(srcdir, outdir)
    finally:
        # autodoc imported the package into this process: forget it, so no other
        # test finds it there.
        for module in [
            name for name in sys.modules if name.split(".")[0] == "vineyard"
        ]:
            del sys.modules[module]

    page = (outdir / "_modules" / "vineyard" / "grape.html").read_text(encoding="UTF-8")
    assert 'href="../../index.html#vineyard.grape.Grape"' in page
    assert 'id="vineyard.grape.Grape"' in (outdir / "index.html").read_text(
        encoding="UTF-8"
    )


GRAPE = "vineyard.grape.Grape"
"""The name of a class under the path of the module that defines it."""

GRAPE_DEFINITION = ObjectEntry("grape", GRAPE, "class", False)
"""The entry that the page of the module registers for the class."""

GRAPE_ALIAS = ObjectEntry("vineyard", "vineyard.Grape", "class", True)
"""The entry that a page re-exporting the class registers through `:canonical:`."""


def merge_worker(
    env: SimpleNamespace, docnames: set[str], objects: dict[str, ObjectEntry]
) -> None:
    """Merge a worker that read `docnames` and holds `objects`, as Sphinx does.

    Runs the merge of `PythonDomain`, then the hook, which is the order
    `BuildEnvironment.merge_info_from` follows for each worker of a parallel
    read.
    """
    other = SimpleNamespace(domaindata={"py": {"objects": objects, "modules": {}}})
    domain = SimpleNamespace(objects=env.domaindata["py"]["objects"], modules={})
    PythonDomain.merge_domaindata(domain, docnames, other.domaindata["py"])
    keep_definitions_over_aliases(None, env, docnames, other)


@pytest.mark.parametrize(
    "definition_first", (True, False), ids=("definition-first", "alias-first")
)
def test_parallel_merge_keeps_the_definition_over_an_alias(definition_first):
    """A definition stays indexed, whichever worker merges first.

    `PythonDomain.merge_domaindata` copies the entries of each worker over the
    ones in place, so an alias merged after the definition replaces it. A serial
    read keeps the definition.
    """
    env = SimpleNamespace(domaindata={"py": {"objects": {}}})
    forget_merged_definitions(None, env, [])
    workers = [
        ({"grape"}, {GRAPE: GRAPE_DEFINITION}),
        ({"vineyard"}, {GRAPE: GRAPE_ALIAS}),
    ]
    if not definition_first:
        workers.reverse()
    for docnames, objects in workers:
        merge_worker(env, docnames, objects)
    assert env.domaindata["py"]["objects"][GRAPE] == GRAPE_DEFINITION


def test_a_read_forgets_the_definitions_of_the_last_one():
    """A definition merged in one build never comes back in the next one."""
    env = SimpleNamespace(domaindata={"py": {"objects": {}}})
    forget_merged_definitions(None, env, [])
    merge_worker(env, {"grape"}, {GRAPE: GRAPE_DEFINITION})

    later = SimpleNamespace(domaindata={"py": {"objects": {}}})
    forget_merged_definitions(None, later, [])
    merge_worker(later, {"vineyard"}, {GRAPE: GRAPE_ALIAS})
    assert later.domaindata["py"]["objects"][GRAPE] == GRAPE_ALIAS


TERROIR_MODULES = {
    "__init__.py": (
        'from terroir.grape import Grape, Vine\n\n__all__ = ["Grape", "Vine"]\n'
    ),
    "grape.py": (
        'class Grape:\n    """A grape of the terroir."""\n\n\n'
        'class Vine:\n    """A vine of the terroir."""\n\n\n'
        'def press():\n    """Press the grapes."""\n'
    ),
    "cellar.py": '"""Wine that takes its time."""\n\nimport time\n\ntime.sleep(1)\n',
}
"""A package re-exporting both classes of its `grape` module, but not `press`.

The page of the package also documents `cellar`, whose import takes a second, so
the worker that reads that page merges after the worker that reads `grape`.
"""


@pytest.mark.skipif(not parallel_available, reason="Sphinx reads in parallel on POSIX")
def test_parallel_read_keeps_the_backlinks_of_a_serial_one(tmp_path):
    """A parallel read points each `[docs]` link at an anchor, as a serial read does.

    The page of the package documents `Grape` and `Vine` with a `:canonical:`
    alias to `terroir.grape`. Merged after the page of `grape`, those aliases
    replace its definitions, unless the extension puts them back. The root path
    then indexes more objects of `grape` than its own path does, and the link
    of `press`, which the package does not re-export, leads under the root path.
    """
    srcdir = tmp_path / "source"
    package = srcdir / "terroir"
    package.mkdir(parents=True)
    for name, source in TERROIR_MODULES.items():
        (package / name).write_text(source, encoding="UTF-8")
    extensions = ["sphinx.ext.autodoc", "sphinx.ext.viewcode", "click_extra.sphinx"]
    (srcdir / "conf.py").write_text(f"extensions = {extensions!r}", encoding="UTF-8")
    (srcdir / "index.rst").write_text(
        "Terroir\n=======\n\n.. toctree::\n\n   grape\n   vineyard\n",
        encoding="UTF-8",
    )
    (srcdir / "grape.rst").write_text(
        "Grape\n=====\n\n.. automodule:: terroir.grape\n   :members:\n",
        encoding="UTF-8",
    )
    (srcdir / "vineyard.rst").write_text(
        "Vineyard\n========\n\n"
        ".. automodule:: terroir\n   :members:\n\n"
        ".. automodule:: terroir.cellar\n",
        encoding="UTF-8",
    )

    outdir = tmp_path / "build"
    build_parallel(srcdir, outdir)

    page = (outdir / "_modules" / "terroir" / "grape.html").read_text(encoding="UTF-8")
    assert 'href="../../grape.html#terroir.grape.press"' in page
    assert broken_backlinks(outdir) == []
