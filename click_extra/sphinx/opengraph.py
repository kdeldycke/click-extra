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
"""Keep the space a title icon leaves out of the `og:title` of a page.

A page title that opens on an icon, like `` # {octicon}`flame` Recipes `` with
sphinx-design, renders as the SVG of the icon, a space, and the text.
sphinxext-opengraph sets `og:title` to the text of that title without stripping
it, so the social card of the page reads `" Recipes"`
([sphinx-doc/sphinxext-opengraph#150](https://github.com/sphinx-doc/sphinxext-opengraph/pull/150)).
This module removes the space from the page title just before
sphinxext-opengraph reads it, and puts the title back just after, so the theme
renders the title it always did.

```{todo}
Delete this module once
[sphinx-doc/sphinxext-opengraph#150](https://github.com/sphinx-doc/sphinxext-opengraph/pull/150)
ships in a sphinxext-opengraph release.
```
"""

from __future__ import annotations

import re

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

    from sphinx.application import Sphinx


OPENGRAPH_EXTENSION = "sphinxext.opengraph"
"""Module name of the extension whose `og:title` this module fixes."""

TITLE_ICON_GAP = re.compile(r"^(\s*<svg\b.*?</svg>)\s+", re.DOTALL)
"""A leading SVG icon of a page title, and the space that follows it."""

TITLE_STASH_KEY = "click_extra_title_with_icon_gap"
"""Page context key holding the title as Sphinx rendered it, until it goes back."""


def strip_title_icon_gap(
    app: Sphinx, pagename: str, templatename: str, context: dict, doctree: Any
) -> None:
    """Drop the space after a leading icon of the page title, for the extension.

    Connected to `html-page-context` at priority 400, ahead of the default 500
    sphinxext-opengraph reads the title at. Inert without sphinxext-opengraph,
    and on a title that opens on no icon.
    """
    if OPENGRAPH_EXTENSION not in app.extensions:
        return
    title = context.get("title")
    if not title:
        return
    stripped = TITLE_ICON_GAP.sub(r"\1", title)
    if stripped != title:
        context[TITLE_STASH_KEY] = title
        context["title"] = stripped


def restore_title(
    app: Sphinx, pagename: str, templatename: str, context: dict, doctree: Any
) -> None:
    """Put back the title {func}`strip_title_icon_gap` changed.

    Connected to `html-page-context` at priority 600, after sphinxext-opengraph
    has read the title, so the templates of the theme get it unchanged.
    """
    if TITLE_STASH_KEY in context:
        context["title"] = context.pop(TITLE_STASH_KEY)


def setup(app: Sphinx) -> None:
    """Register the two title hooks on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`.
    """
    app.connect("html-page-context", strip_title_icon_gap, priority=400)
    app.connect("html-page-context", restore_title, priority=600)
