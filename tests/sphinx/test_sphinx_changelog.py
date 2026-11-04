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
"""Tests for the anchors of changelog releases."""

from __future__ import annotations

from io import StringIO

import pytest
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from click_extra.sphinx.changelog import RELEASE_ANCHORS_CONFIG, RELEASE_HEADING

MYST_CHANGELOG = """\
# Changelog

See the [next release](#v1-5-0).

## [`1.5.0.dev0` (unreleased)](https://example.com/compare/v1.4.2...main)

- Plant a pear tree.

## [`1.4.2` (2026-03-15)](https://example.com/compare/v1.4.1...v1.4.2)

- Prune the apple trees.

## `1.4.1` (2026-02-01)

- Water the plums.
"""
"""A MyST changelog, one release titled as a link, one as plain text."""

RST_CHANGELOG = """\
Changelog
=========

1.5.0.dev0 (unreleased)
-----------------------

- Plant a pear tree.

1.4.2 (2026-03-15)
------------------

- Prune the apple trees.

1.4.1 (2026-02-01)
------------------

- Water the plums.
"""
"""The same changelog in reStructuredText."""

ORCHARD_PAGE = "# Orchard\n\nThe trees were [last pruned](changelog.md#v1-4-2).\n"
"""A MyST page linking to a release of the changelog page."""


def build(tmp_path, pages, *, anchors=None):
    """Build `pages`, a map of file names to sources, and return the output.

    `anchors` sets {data}`~click_extra.sphinx.changelog.RELEASE_ANCHORS_CONFIG`,
    left to its default when `None`. Returns the output directory and the
    warning stream.
    """
    srcdir = tmp_path / "source"
    srcdir.mkdir()
    conf = [
        'root_doc = "index"',
        "extensions = ['myst_parser', 'click_extra.sphinx']",
        "myst_heading_anchors = 6",
        'myst_heading_slug_func = "docutils.nodes.make_id"',
    ]
    if anchors is not None:
        conf.append(f"{RELEASE_ANCHORS_CONFIG} = {anchors!r}")
    (srcdir / "conf.py").write_text("\n".join(conf), encoding="UTF-8")
    toctree = "\n".join(name.rpartition(".")[0] for name in pages)
    (srcdir / "index.md").write_text(
        f"# Index\n\n```{{toctree}}\n{toctree}\n```\n", encoding="UTF-8"
    )
    for name, source in pages.items():
        (srcdir / name).write_text(source, encoding="UTF-8")

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
    return outdir, warnings.getvalue()


@pytest.mark.parametrize(
    ("title", "version"),
    (
        ("1.4.2 (2026-03-15)", "1.4.2"),
        ("1.5.0.dev0 (unreleased)", "1.5.0"),
        ("10.12.0 (2027-01-04)", "10.12.0"),
        ("1.4 (2026-03-15)", None),
        ("1.4.2", None),
        ("Version 1.4.2 (2026-03-15)", None),
        ("1.4.2 (2026-03-15) and more", None),
    ),
)
def test_release_heading(title, version):
    """Only a title made of a full version and a parenthesized label matches."""
    match = RELEASE_HEADING.fullmatch(title)
    assert (match["version"] if match else None) == version


@pytest.mark.parametrize(
    "page",
    (
        pytest.param({"changelog.md": MYST_CHANGELOG}, id="myst"),
        pytest.param({"changelog.rst": RST_CHANGELOG}, id="rst"),
    ),
)
def test_releases_are_anchored_on_their_version(tmp_path, page):
    """Each release section takes its version as ID, the one in preparation too."""
    outdir, _ = build(tmp_path, page, anchors=True)
    html = (outdir / "changelog.html").read_text(encoding="UTF-8")
    for anchor in ("v1-5-0", "v1-4-2", "v1-4-1"):
        assert f'<section id="{anchor}">' in html


def test_links_resolve_to_version_anchors(tmp_path):
    """A link to a version anchor resolves, from the changelog and from another page."""
    outdir, warnings = build(
        tmp_path,
        {"changelog.md": MYST_CHANGELOG, "orchard.md": ORCHARD_PAGE},
        anchors=True,
    )
    assert "myst.xref_missing" not in warnings
    changelog = (outdir / "changelog.html").read_text(encoding="UTF-8")
    assert 'href="#v1-5-0"' in changelog
    orchard = (outdir / "orchard.html").read_text(encoding="UTF-8")
    assert 'href="changelog.html#v1-4-2"' in orchard


def test_release_anchors_are_off_by_default(tmp_path):
    """Without the opt-in, each release keeps the ID docutils gave it."""
    outdir, _ = build(tmp_path, {"changelog.md": MYST_CHANGELOG})
    html = (outdir / "changelog.html").read_text(encoding="UTF-8")
    assert '<section id="v1-4-2">' not in html
    assert '<section id="id1">' in html
