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
"""Warn about each internal link of the built HTML that leads nowhere.

Sphinx warns about a cross-reference it cannot resolve. A link it does not
resolve itself, it writes as it is: the `href` of a raw HTML block, a fragment
that names an anchor its page lost, or a link an extension builds from data,
like the `[docs]` link of a `sphinx.ext.viewcode` page. Nothing tells when such
a link leads to no page, or to no anchor of its page.

This module reads the HTML pages once the build is over, and logs a
{data}`DEAD_LINK_WARNING` for each `<a href>` that leads to no file, or to a
fragment that the page it leads to does not define. A link that names a scheme
or a host leaves the build, and a link that opens on `/` depends on where the
site is served, so the check skips both. A page that holds the same dead link
several times gets one warning for it. `--fail-on-warning` then fails the build.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sphinx.util import logging
from sphinx.util.logging import is_suppressed_warning

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx


logger = logging.getLogger(__name__)


DEAD_LINK_WARNING = "click_extra.dead_link"
"""Type of the warning logged for each internal link that leads nowhere.

Listed in `suppress_warnings`, it turns the check off. Listed in
{data}`~click_extra.sphinx.fail_on_warnings.FAIL_ON_WARNINGS_CONFIG`, it fails a
build on a dead link without `--fail-on-warning`.
"""


class _PageParser(HTMLParser):
    """Collect the anchors a page defines and the `href` of each of its links.

    An anchor is the `id` of any element, or the `name` of an `<a>`, which are
    the two targets a browser scrolls a fragment to.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: set[str] = set()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value is None:
                continue
            if name == "id" or (name == "name" and tag == "a"):
                self.anchors.add(value)
            elif name == "href" and tag == "a":
                self.links.append(value)


def _parse(page: Path) -> _PageParser:
    """Read the anchors and the links of the HTML `page`."""
    parser = _PageParser()
    parser.feed(page.read_text(encoding="UTF-8"))
    parser.close()
    return parser


def dead_links(outdir: Path) -> list[tuple[str, str, str]]:
    """Return each internal link of the HTML pages under `outdir` that leads nowhere.

    A link to a folder leads to its `index.html`. A fragment is checked on an
    HTML target only. A link that leaves `outdir` through `..` is skipped, like
    an external one.

    :return: the path of the page relative to `outdir`, the `href` as the page
        writes it, and `"page"` or `"anchor"` for what it misses. One entry per
        page and `href`, sorted.
    """
    root = outdir.resolve()
    pages = {page: _parse(page) for page in sorted(root.rglob("*.html"))}
    dead: set[tuple[str, str, str]] = set()
    for page, parser in pages.items():
        name = page.relative_to(root).as_posix()
        for href in parser.links:
            parts = urlsplit(href)
            if parts.scheme or parts.netloc or href.startswith("/"):
                continue
            target = page
            if parts.path:
                target = (page.parent / unquote(parts.path)).resolve()
                if root != target and root not in target.parents:
                    continue
                if target.is_dir():
                    target /= "index.html"
                if not target.is_file():
                    dead.add((name, href, "page"))
                    continue
            fragment = unquote(parts.fragment)
            if not fragment or target.suffix != ".html":
                continue
            if target not in pages:
                pages[target] = _parse(target)
            if fragment not in pages[target].anchors:
                dead.add((name, href, "anchor"))
    return sorted(dead)


def report_dead_links(app: Sphinx, exception: Exception | None) -> None:
    """Warn once about each dead internal link of the pages the build wrote.

    Connected to `build-finished`, which fires once every page is on disk. The
    warning has the {data}`DEAD_LINK_WARNING` type, names the page that holds
    the link, and points at the source of that page when the page has one: a
    page that an extension writes, like a `sphinx.ext.viewcode` page, has none.
    Inert after a failed build, with a builder that writes no HTML, and when
    `suppress_warnings` lists the type, which then also spares the reading of
    every page.
    """
    if exception is not None or app.builder.format != "html":
        return
    warning_type, _, subtype = DEAD_LINK_WARNING.partition(".")
    if is_suppressed_warning(warning_type, subtype, app.config.suppress_warnings):
        return
    for page, href, missing in dead_links(Path(app.outdir)):
        docname = page.removesuffix(".html")
        logger.warning(
            "click_extra.sphinx: %s links %s, which leads to no %s.",
            page,
            href,
            missing,
            type=warning_type,
            subtype=subtype,
            location=docname if docname in app.env.all_docs else None,
        )


def setup(app: Sphinx) -> None:
    """Register the dead-link check on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. The default priority runs the
    check before {mod}`click_extra.sphinx.fail_on_warnings` counts the warnings
    of the build, at priority 900.
    """
    app.connect("build-finished", report_dead_links)
