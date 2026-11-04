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

import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace
from sphinx.util.parallel import parallel_available

FRUITS_MODULE = '''\
import re

SEED = re.compile(r"\\d+")
"""Pattern of a seed count."""


def ripen(fruit):
    """Ripen a fruit."""
'''
"""A module documenting a constant whose value is an instance of `re.Pattern`.

viewcode looks for `SEED` in the module of that class, `re`, and finds nothing
to link to there.
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


def test_serial_read_publishes_linked_modules_only(tmp_path, monkeypatch):
    """A serial read publishes no page for the module it read for nothing."""
    srcdir = tmp_path / "source"
    write_project(srcdir)
    monkeypatch.syspath_prepend(str(srcdir))
    monkeypatch.delitem(sys.modules, "fruits", raising=False)

    outdir = tmp_path / "build"
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

    assert module_pages(outdir) == PUBLISHED_PAGES
    assert "viewcode-back" in (outdir / "_modules" / "fruits.html").read_text(
        encoding="UTF-8"
    )


@pytest.mark.skipif(not parallel_available, reason="Sphinx reads in parallel on POSIX")
def test_parallel_read_publishes_the_pages_of_a_serial_one(tmp_path):
    """A parallel read publishes the same pages as a serial one.

    Its workers merge their entries after every purge has run, which is the
    case of [sphinx-doc/sphinx#14675](https://github.com/sphinx-doc/sphinx/issues/14675).
    The build runs in a process of its own: forking the test process, which
    runs other threads, can deadlock the workers.
    """
    srcdir = tmp_path / "source"
    write_project(srcdir)
    outdir = tmp_path / "build"
    # `python -m` puts the working directory first on `sys.path`, which makes
    # `fruits` importable to autodoc.
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
    assert module_pages(outdir) == PUBLISHED_PAGES
