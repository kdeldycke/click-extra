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

"""Render tests for Sphinx cross-references in the built documentation.

Build the docs once and assert against the real HTML that in-page and
cross-page anchors resolve to the sections they name, and that intersphinx
references to Click resolve to the upstream site. This catches drift the
moment a heading rename shifts a `make_id` slug, a page link goes stale, or
the `intersphinx_mapping` URL breaks, none of which a mock-based test would
notice.

The docs are built in a subprocess through `uv run --group docs`, so this
module needs no Sphinx dependency of its own and runs in the plain test
environment.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# The docs dependency group requires Python >= 3.14 (see pyproject.toml
# [tool.uv] dependency-groups.docs). Only build under the same conditions the
# docs workflow uses: Linux, that Python floor, and uv available to provision
# the docs environment. The full build is expensive and platform-independent,
# so it is a run-once test, filtered out of the cross-platform matrix.
pytestmark = [
    pytest.mark.once,
    pytest.mark.skipif(
        not sys.platform.startswith("linux"),
        reason="docs are built on Linux in CI",
    ),
    pytest.mark.skipif(
        sys.version_info < (3, 14),
        reason="docs dependency group requires Python >= 3.14",
    ),
    pytest.mark.skipif(
        shutil.which("uv") is None,
        reason="needs uv to build the docs",
    ),
]

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def built_docs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the HTML documentation once and return its output directory.

    Builds into a throwaway directory (rather than ``docs/_build``) so the run
    is hermetic and never clobbers a developer's local build.
    """
    out_dir = tmp_path_factory.mktemp("sphinx-html")
    subprocess.run(
        [
            "uv",
            "run",
            "--group",
            "docs",
            "sphinx-build",
            "--builder",
            "html",
            str(PROJECT_ROOT / "docs"),
            str(out_dir),
        ],
        check=True,
        cwd=PROJECT_ROOT,
    )
    return out_dir


@pytest.fixture(scope="module")
def captures_before_build() -> dict[Path, bytes]:
    """Snapshot every committed capture before a build gets a chance to rewrite one.

    Requested ahead of {func}`built_docs` by the freshness check below, so the
    bytes are read while the tree is still as committed.
    """
    return {
        path: path.read_bytes()
        for path in sorted((PROJECT_ROOT / "docs" / "assets").glob("*.svg"))
    }


def test_committed_captures_survive_a_build(captures_before_build, built_docs):
    """Building the documentation leaves every committed capture byte-identical.

    A `click:run` block carrying `:screenshot:` rewrites its image from the CLI's
    live output on every build. So an image that no longer matches the code
    surfaces here, instead of sitting stale in a readme nobody re-checked.

    Regenerating is the fix: build the docs and commit what changed.
    """
    assert captures_before_build, "no committed capture found to check"
    stale = [
        path.name
        for path, before in captures_before_build.items()
        if path.read_bytes() != before
    ]
    assert not stale, f"the build refreshed committed captures: {', '.join(stale)}"


def read_html(built_docs: Path, filename: str) -> str:
    """Read a built HTML page."""
    html_path = built_docs / filename
    assert html_path.exists(), f"HTML file not found: {html_path}"
    return html_path.read_text(encoding="utf-8")


def test_install_page_internal_anchor(built_docs):
    """The install page's in-page executables link resolves to its section."""
    html = read_html(built_docs, "install.html")
    assert 'id="executables"' in html, "missing executables section anchor"
    assert 'href="#executables"' in html, "no in-page link to executables"


@pytest.mark.parametrize("anchor", ("click-extra-wrap", "test-suite-file"))
def test_cli_reference_anchors(built_docs, anchor):
    """The CLI page's tree and config summary tables deep-link their sections.

    One anchor per directive: `click-extra-wrap` comes from `{click:tree}`,
    `test-suite-file` from `{click:config}`. Their presence is also the canary
    for the directives themselves staying on the page.
    """
    html = read_html(built_docs, "cli.html")
    assert f'id="{anchor}"' in html, f"missing section anchor for {anchor}"
    assert f'href="#{anchor}"' in html, f"summary table does not link to {anchor}"


@pytest.mark.parametrize(
    ("source_page", "href", "target_page", "anchor"),
    (
        (
            "install.html",
            "config-formats.html#toml",
            "config-formats.html",
            "toml",
        ),
        (
            "install.html",
            "table.html#table-formats",
            "table.html",
            "table-formats",
        ),
        (
            "install.html",
            "python-directives.html#matrix-directives",
            "python-directives.html",
            "matrix-directives",
        ),
    ),
)
def test_cross_page_links_resolve(built_docs, source_page, href, target_page, anchor):
    """Cross-page links point at anchors that exist on the target page.

    Every case names a page, so splitting one moves the anchor and leaves the
    case behind. Repoint them in the same commit that splits the page: this
    module is skipped off Linux, so the break surfaces only in CI, and a local
    `pytest -m once` reports a clean pass while skipping all of it.
    """
    source_html = read_html(built_docs, source_page)
    assert f'href="{href}"' in source_html, f"{source_page} does not link to {href}"
    target_html = read_html(built_docs, target_page)
    assert f'id="{anchor}"' in target_html, (
        f"{target_page} lost its {anchor} section anchor"
    )


def test_intersphinx_click_resolves(built_docs):
    """Click cross-references resolve to the upstream documentation site."""
    html = read_html(built_docs, "click_extra.html")
    assert "https://click.palletsprojects.com" in html, (
        "no intersphinx link to Click found; the mapping may be broken"
    )
