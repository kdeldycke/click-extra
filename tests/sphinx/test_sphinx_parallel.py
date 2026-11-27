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
"""Tests for the fixes that make a parallel read index what a serial read indexes."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sphinx.domains.python import ObjectEntry, PythonDomain
from sphinx.util.parallel import parallel_available

from click_extra.sphinx.parallel import (
    forget_merged_definitions,
    keep_definitions_over_aliases,
)

from .conftest import build_parallel, build_serial


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


BASKET_MODULE = '''\
from __future__ import annotations

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import TypeAlias

    Fruits: TypeAlias = "tuple[str, ...]"
    """Fruits a basket holds."""


class Basket:
    """A basket of fruits."""

    def __init__(self, *fruits: str) -> None:
        """Fill the basket."""
        self.fruits: tuple[str, ...] = fruits
'''
"""A module annotating two names that only its source holds.

`Fruits` sits in a `TYPE_CHECKING` block, and `Basket.fruits` in `__init__`.
"""


def test_a_page_read_first_lists_its_annotated_members(tmp_path, monkeypatch):
    """A page lists the names its module annotates, whatever autodoc read before.

    autodoc copies the annotations of the source into the module and its classes
    only when it documents an attribute of the module, then lists each annotated
    name as a member. Without the copy made in advance, a page read before any
    such attribute, like the first page of a parallel worker, lists neither name.
    """
    srcdir = tmp_path / "source"
    srcdir.mkdir()
    (srcdir / "basket.py").write_text(BASKET_MODULE, encoding="UTF-8")
    extensions = ["sphinx.ext.autodoc", "click_extra.sphinx"]
    (srcdir / "conf.py").write_text(f"extensions = {extensions!r}", encoding="UTF-8")
    (srcdir / "index.rst").write_text(
        "Basket\n======\n\n.. automodule:: basket\n   :members:\n   :undoc-members:\n",
        encoding="UTF-8",
    )
    monkeypatch.syspath_prepend(str(srcdir))
    # A module imported by an earlier build may hold the annotations already.
    monkeypatch.delitem(sys.modules, "basket", raising=False)

    outdir = tmp_path / "build"
    try:
        build_serial(srcdir, outdir)
    finally:
        sys.modules.pop("basket", None)

    page = (outdir / "index.html").read_text(encoding="UTF-8")
    assert 'id="basket.Fruits"' in page
    assert 'id="basket.Basket.fruits"' in page


CRATE_MODULE = '''\
from typing import TypedDict


class _Fields(TypedDict, total=False):
    weight: int
    """How heavy the crate is."""


class Crate(_Fields, total=False):
    """A crate of fruits."""

    color: str
    """The color of the crate."""
'''
"""A module whose `TypedDict` takes a field from a private base.

Without `from __future__ import annotations`, Python 3.14 and later evaluate the
annotations of a class lazily, through its `__annotate__`.
"""


def test_copied_annotations_keep_the_fields_of_a_typeddict_base(tmp_path, monkeypatch):
    """A `TypedDict` still lists the fields of its base once its module is annotated.

    Assigning a new `__annotations__` to the base, rather than filling the one in
    place, clears its `__annotate__` from Python 3.14 on, and `Crate` then reads
    its own field alone.
    """
    srcdir = tmp_path / "source"
    srcdir.mkdir()
    (srcdir / "crate.py").write_text(CRATE_MODULE, encoding="UTF-8")
    extensions = ["sphinx.ext.autodoc", "click_extra.sphinx"]
    (srcdir / "conf.py").write_text(f"extensions = {extensions!r}", encoding="UTF-8")
    (srcdir / "index.rst").write_text(
        "Crate\n=====\n\n.. automodule:: crate\n   :members:\n   :undoc-members:\n",
        encoding="UTF-8",
    )
    monkeypatch.syspath_prepend(str(srcdir))
    monkeypatch.delitem(sys.modules, "crate", raising=False)

    outdir = tmp_path / "build"
    try:
        build_serial(srcdir, outdir)
    finally:
        sys.modules.pop("crate", None)

    page = (outdir / "index.html").read_text(encoding="UTF-8")
    assert 'id="crate.Crate.color"' in page
    assert 'id="crate.Crate.weight"' in page
