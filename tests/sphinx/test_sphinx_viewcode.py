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
import sys
from pathlib import Path

import pytest
from sphinx.util.parallel import parallel_available

from .conftest import build_parallel, build_serial

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
