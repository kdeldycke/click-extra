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

The same build shows what the `click_extra.sphinx` extension changes in its
output: each changelog release anchored on its version, no viewcode page that
nothing links to, and no pickled page holding a node of another document.

The docs are built in a subprocess through `uv run --group docs`, and so are
the pickled pages read back, so this module needs no Sphinx dependency of its
own and runs in the plain test environment.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# The docs dependency group requires Python >= 3.14 (see pyproject.toml
# [tool.uv] dependency-groups.docs). Only build under the same conditions the
# docs workflow uses: Linux, that Python floor, and uv available to provision
# the docs environment. The full build is expensive and platform-independent,
# so it is a run-once test, filtered out of the cross-platform matrix. `uv`
# downloads the docs environment and Sphinx reads the intersphinx inventories,
# so the module is a network test too, which a packager deselects.
pytestmark = [
    pytest.mark.network,
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

UV_RUN_DOCS = ("uv", "run", "--group", "docs")
"""Prefix of a command run in the docs environment."""

CHANGELOG_RELEASE = re.compile(
    r"^## \[`(?P<version>\d+\.\d+\.\d+)(?:\.\w+)?` \(", re.MULTILINE
)
"""Heading of a release in `changelog.md`, the `.devN` suffix left out."""

FOREIGN_NODES_SCRIPT = """\
import json
import pickle
import sys
from pathlib import Path

doctrees = Path(sys.argv[1])
foreign = {}
for path in sorted(doctrees.rglob("*.doctree")):
    doctree = pickle.loads(path.read_bytes())
    count = sum(1 for node in doctree.findall() if node.document is not doctree)
    if count:
        foreign[path.relative_to(doctrees).as_posix()] = count
print(json.dumps(foreign))
"""
"""Count, for each pickled page, the nodes that belong to another document.

Runs in the docs environment, which holds every class the pages pickle.
"""


@pytest.fixture(scope="module")
def built_docs(
    tmp_path_factory: pytest.TempPathFactory,
    captures_before_build: dict[Path, bytes],
) -> Path:
    """Build the HTML documentation once and return its output directory.

    Builds into a throwaway directory (rather than ``docs/_build``) so the run
    is hermetic and never clobbers a developer's local build. Reads in parallel,
    as `docs.yaml` does: a serial read hides most of the viewcode pages a
    parallel one publishes.

    Requests {func}`captures_before_build` so the snapshot is taken before the
    build whichever test triggers it: every test of this module shares the one
    build, and `pytest-randomly` decides which of them runs first.
    """
    out_dir = tmp_path_factory.mktemp("sphinx-html")
    subprocess.run(
        [
            *UV_RUN_DOCS,
            "sphinx-build",
            "--builder",
            "html",
            "--jobs",
            "auto",
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

    {func}`built_docs` requests it, so the bytes are read while the tree is
    still as committed, whichever test of the module builds first.
    """
    return {
        path: path.read_bytes()
        for path in sorted((PROJECT_ROOT / "docs" / "assets").glob("*.svg"))
    }


def test_committed_captures_survive_a_build(captures_before_build, built_docs):
    """A build leaves every committed capture byte-identical.

    A `click:run` block carrying `:screenshot:` rewrites its image from the CLI's
    live output on every build. So an image that no longer matches the code
    surfaces here, instead of sitting stale in a readme nobody re-checked.

    The bytes compare raw: the `@generated` stamp and the default watermark
    name no release, so a version bump moves neither. Regenerating is still the
    fix for a real difference: build and commit it.
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
    return html_path.read_text(encoding="UTF-8")


def test_install_page_internal_anchor(built_docs):
    """The install page's in-page binaries link resolves to its section."""
    html = read_html(built_docs, "install.html")
    assert 'id="binaries"' in html, "missing binaries section anchor"
    assert 'href="#binaries"' in html, "no in-page link to binaries"


def test_changelog_releases_are_anchored_on_their_version(built_docs):
    """Each release of the changelog has an anchor made from its version.

    docutils reduces a release heading to nothing and numbers its section from
    a per-page counter, so `#id40` names another release after each new one.
    `click_extra_release_anchors` in `docs/conf.py` gives each section an anchor
    like `#v1-4-2` instead. See {mod}`click_extra.sphinx.changelog`.
    """
    changelog = (PROJECT_ROOT / "changelog.md").read_text(encoding="UTF-8")
    versions = CHANGELOG_RELEASE.findall(changelog)
    assert versions, "no release heading found in changelog.md"
    html = read_html(built_docs, "changelog.html")
    missing = [
        version
        for version in versions
        if f'<section id="v{version.replace(".", "-")}">' not in html
    ]
    assert not missing, f"releases with no version anchor: {missing}"


def test_viewcode_pages_link_back_to_their_objects(built_docs):
    """Each published module page links back to an object it documents.

    `sphinx.ext.viewcode` keeps a module it read even when no documented object
    links to it, and a parallel read publishes a page for each such module,
    reachable from the `_modules` index alone. See
    {mod}`click_extra.sphinx.viewcode`.
    """
    index = built_docs / "_modules" / "index.html"
    pages = [
        page
        for page in sorted((built_docs / "_modules").rglob("*.html"))
        if page != index
    ]
    assert pages, "no viewcode page was built"
    orphans = [
        page.relative_to(built_docs).as_posix()
        for page in pages
        if 'class="viewcode-back"' not in page.read_text(encoding="UTF-8")
    ]
    assert not orphans, f"viewcode pages no documented object links to: {orphans}"


def test_pickled_pages_hold_no_node_of_another_document(built_docs):
    """Every node of each pickled page belongs to that page.

    A node that keeps a throwaway document pickles that document's settings
    with the page, build environment included. Counting such nodes catches a
    leak of any size, where a ceiling on file sizes lets through a leak that
    only some of the pages carry. See {mod}`click_extra.sphinx.doctrees`.
    """
    result = subprocess.run(
        [
            *UV_RUN_DOCS,
            "python",
            "-c",
            FOREIGN_NODES_SCRIPT,
            str(built_docs / ".doctrees"),
        ],
        capture_output=True,
        check=True,
        cwd=PROJECT_ROOT,
        encoding="UTF-8",
        text=True,
    )
    foreign = json.loads(result.stdout)
    assert not foreign, f"pages holding nodes of another document: {foreign}"


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
            "config-formats.html#yaml",
            "config-formats.html",
            "yaml",
        ),
        (
            "install.html",
            "table.html#table-formats",
            "table.html",
            "table-formats",
        ),
        (
            "install.html",
            "python-directives.html#the-support-envelope",
            "python-directives.html",
            "the-support-envelope",
        ),
        (
            "click_extra.config.html",
            "install.html#extra-dependencies",
            "install.html",
            "extra-dependencies",
        ),
        (
            "click_extra.config.html",
            "config-discovery.html#use-platformdirs-instead",
            "config-discovery.html",
            "use-platformdirs-instead",
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
