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
"""Tests for failing a Sphinx build on the warning types a project lists."""

from __future__ import annotations

from io import StringIO

import pytest
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from click_extra.sphinx.fail_on_warnings import FAIL_ON_WARNINGS_CONFIG

DEAD_LABEL_PAGE = "Orchard\n=======\n\nSee :ref:`the-walled-garden`.\n"
"""A reStructuredText page whose one defect is an undefined label: `ref.ref`."""

CLEAN_PAGE = "Orchard\n=======\n\nApples ripen in autumn.\n"
"""The same page, without the defect."""

DEAD_FRAGMENT_PAGE = "# Orchard\n\nSee [the walled garden](#the-walled-garden).\n"
"""A MyST page whose one defect is a link to no anchor: `myst.xref_missing`."""


def build(tmp_path, page, *, listed=None, suppressed=None, suffix=".rst"):
    """Build a one-page project, and return its exit status and warning stream."""
    srcdir = tmp_path / "source"
    srcdir.mkdir(parents=True)
    extensions = ["click_extra.sphinx"]
    if suffix == ".md":
        extensions.insert(0, "myst_parser")
    conf = ['root_doc = "index"', f"extensions = {extensions!r}"]
    if listed is not None:
        conf.append(f"{FAIL_ON_WARNINGS_CONFIG} = {listed!r}")
    if suppressed is not None:
        conf.append(f"suppress_warnings = {suppressed!r}")
    (srcdir / "conf.py").write_text("\n".join(conf), encoding="utf-8")
    (srcdir / f"index{suffix}").write_text(page, encoding="utf-8")

    outdir = tmp_path / "build"
    warnings = StringIO()
    with docutils_namespace():
        app = Sphinx(
            str(srcdir),
            str(srcdir),
            str(outdir),
            str(outdir / ".doctrees"),
            "html",
            status=None,
            warning=warnings,
        )
        app.build()
    return app.statuscode, warnings.getvalue()


@pytest.mark.parametrize(
    ("listed", "suppressed", "status"),
    (
        pytest.param(None, None, 0, id="unset"),
        pytest.param(["ref.ref"], None, 1, id="type-and-subtype"),
        pytest.param(["ref"], None, 1, id="type-alone"),
        pytest.param(["ref.*"], None, 1, id="type-wildcard"),
        pytest.param(["myst.xref_missing"], None, 0, id="other-type"),
        pytest.param(["ref.ref"], ["ref.ref"], 0, id="suppressed-wins"),
        pytest.param(["ref"], ["ref.ref"], 0, id="suppressed-subtype-wins"),
    ),
)
def test_listed_types_decide_the_exit_status(tmp_path, listed, suppressed, status):
    """A warning fails the build only when its type is listed and not suppressed."""
    result, _ = build(tmp_path, DEAD_LABEL_PAGE, listed=listed, suppressed=suppressed)
    assert result == status


def test_clean_build_passes(tmp_path):
    """A listed type fails nothing while no warning of that type is logged."""
    status, _ = build(tmp_path, CLEAN_PAGE, listed=["ref.ref"])
    assert status == 0


def test_error_counts_each_warning_once(tmp_path):
    """The error names the matched type, and counts a replayed warning once."""
    status, warnings = build(tmp_path, DEAD_LABEL_PAGE, listed=["ref"])
    assert status == 1
    assert "undefined label" in warnings
    assert (
        f"1 warning of a type listed in {FAIL_ON_WARNINGS_CONFIG} (ref.ref)."
        in warnings
    )


def test_dead_myst_fragment_fails_the_build(tmp_path):
    """The case the hook was written for: a `[text](#anchor)` link to nothing."""
    status, warnings = build(
        tmp_path, DEAD_FRAGMENT_PAGE, listed=["myst.xref_missing"], suffix=".md"
    )
    assert status == 1
    assert "[myst.xref_missing]" in warnings


def test_collector_does_not_outlive_its_build(tmp_path):
    """A second build in the same process starts with nothing collected."""
    first, _ = build(tmp_path / "first", DEAD_LABEL_PAGE, listed=["ref.ref"])
    second, _ = build(tmp_path / "second", CLEAN_PAGE, listed=["ref.ref"])
    assert (first, second) == (1, 0)
