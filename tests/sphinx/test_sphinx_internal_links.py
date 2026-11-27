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
"""Tests for the warning about each internal link of the built HTML that leads nowhere."""

from __future__ import annotations

import pytest

from click_extra.sphinx.internal_links import DEAD_LINK_WARNING, dead_links

from .conftest import build_serial

ORCHARD_PAGES = {
    "index.html": (
        '<p id="top"><a name="old"></a>'
        '<a href="fruits.html">fruits</a>'
        '<a href="fruits.html#pears">pears</a>'
        '<a href="fruits.html#plums">plums</a>'
        '<a href="missing.html">missing</a>'
        '<a href="missing.html">missing again</a>'
        '<a href="#top">top</a><a href="#old">old</a><a href="#">empty</a>'
        '<a href="cellar/">cellar</a>'
        '<a href="https://example.com/orchard.html#nowhere">external</a>'
        '<a href="mailto:grower@example.com">mail</a>'
        '<a href="/fruits.html#nowhere">root-relative</a>'
        '<a href="../outside.html">outside</a>'
        '<code>&lt;a href="missing.html"&gt;</code>'
        '<span>href="text.html"</span></p>'
    ),
    "fruits.html": '<h2 id="pears">Pears</h2>',
    "cellar/index.html": '<a href="../index.html#top">back</a>',
}
"""Pages that hold two dead links among links of every kind the check skips.

The text that only looks like a link, inside `<code>` or as a bare string, is no
`<a>` element, so it leads nowhere and gets no warning.
"""


def test_dead_links_finds_each_dead_target_once(tmp_path):
    """Each `href` that leads to no page or no anchor is reported once per page."""
    for name, body in ORCHARD_PAGES.items():
        page = tmp_path / name
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(f"<html><body>{body}</body></html>", encoding="UTF-8")

    assert dead_links(tmp_path) == [
        ("index.html", "fruits.html#plums", "anchor"),
        ("index.html", "missing.html", "page"),
    ]


def write_project(srcdir, conf=""):
    """Write a project whose only page holds a raw HTML block of dead links."""
    srcdir.mkdir()
    (srcdir / "conf.py").write_text(
        f'extensions = ["click_extra.sphinx"]\n{conf}', encoding="UTF-8"
    )
    (srcdir / "index.rst").write_text(
        "Orchard\n=======\n\n.. raw:: html\n\n"
        '   <a href="pears.html">pears</a> <a href="pears.html">pears again</a>\n'
        '   <a href="index.html#plums">plums</a>\n',
        encoding="UTF-8",
    )


def test_build_warns_once_per_dead_link(tmp_path):
    """A build warns once about each dead link of a page, with the warning type."""
    srcdir = tmp_path / "source"
    write_project(srcdir)

    warnings = build_serial(srcdir, tmp_path / "build")

    assert warnings.count(f"[{DEAD_LINK_WARNING}]") == 2
    assert "index.html links pears.html, which leads to no page." in warnings
    assert "index.html links index.html#plums, which leads to no anchor." in warnings


@pytest.mark.parametrize("suppressed", ("click_extra", DEAD_LINK_WARNING))
def test_suppressed_warning_turns_the_check_off(tmp_path, suppressed):
    """Listing the type in `suppress_warnings`, or its parent, silences the check."""
    srcdir = tmp_path / "source"
    write_project(srcdir, conf=f"suppress_warnings = [{suppressed!r}]\n")

    warnings = build_serial(srcdir, tmp_path / "build")

    assert DEAD_LINK_WARNING not in warnings
