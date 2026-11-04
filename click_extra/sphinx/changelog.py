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
"""Anchor each release of a changelog on its version, like `#v1-4-2`.

docutils builds the ID of a section from its title, minus the leading digits and
hyphens. That leaves nothing of a release title like `1.4.2 (2026-03-15)`, so
the section takes the next value of a per-page counter: `#id1` for the newest
release. The next release then moves every older one down the counter, and a
saved `#id40` link lands on another release.

With {data}`RELEASE_ANCHORS_CONFIG` set, {class}`ReleaseAnchors` gives each
section titled like a release an ID made from its version instead. The
transform applies to every page, so it covers a changelog split over several
pages, like an archive of old releases.
"""

from __future__ import annotations

import re

from docutils import nodes
from docutils.transforms.references import PropagateTargets
from sphinx.transforms import SphinxTransform

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx


RELEASE_ANCHORS_CONFIG = "click_extra_release_anchors"
"""Name of the `conf.py` value that anchors releases on their version.

`False` by default: the version IDs replace the ones a published changelog
already carries, so each `#idN` link to a release stops working once.
"""

RELEASE_HEADING = re.compile(r"(?P<version>\d+\.\d+\.\d+)(?:\.\w+)? \([^)]+\)")
"""Rendered title of a release: `1.4.2 (2026-03-15)`.

The release in preparation carries a `.devN` suffix, and the `unreleased` label
in place of a date: `1.5.0.dev0 (unreleased)`.
"""


class ReleaseAnchors(SphinxTransform):
    """Replace the ID docutils gave each release section with its version.

    The version ID replaces the old one on the section, in the ID and name
    tables of the document, and in the table myst-parser resolves a
    `[text](changelog.md#v1-4-2)` link against. The `.devN` suffix of the
    release in preparation is left out, so its anchor does not change the day
    it ships.

    Runs right before `PropagateTargets`: the section then holds only the ID
    docutils gave it, and nothing has read that ID yet.
    """

    default_priority = PropagateTargets.default_priority - 1

    def apply(self, **kwargs: object) -> None:
        """Rename the section of each release, if the project opted in."""
        if not getattr(self.config, RELEASE_ANCHORS_CONFIG, False):
            return
        renamed: dict[str, str] = {}
        for release in self.document.findall(nodes.section):
            title = release.children[0] if release.children else None
            if not isinstance(title, nodes.title) or not release["ids"]:
                continue
            match = RELEASE_HEADING.fullmatch(title.astext())
            if not match:
                continue
            anchor = "v" + match["version"].replace(".", "-")
            # Makes a second pass, or a second heading of that version, a no-op.
            if anchor in self.document.ids:
                continue
            docutils_id = release["ids"][0]
            release["ids"][0] = anchor
            self.document.ids.pop(docutils_id, None)
            self.document.ids[anchor] = release
            for name in release["names"]:
                self.document.nameids[name] = anchor
            renamed[docutils_id] = anchor

        # The same object as `env.metadata[docname]["myst_slugs"]`, which is why
        # it is updated in place.
        slugs = getattr(self.document, "myst_slugs", {})
        for slug, (line, section_id, title_text) in list(slugs.items()):
            if section_id in renamed:
                del slugs[slug]
                anchor = renamed[section_id]
                slugs[anchor] = (line, anchor, title_text)


def setup(app: Sphinx) -> None:
    """Register the config value and the release transform on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. The value rebuilds the
    environment, since the IDs are set while a page is read.
    """
    app.add_config_value(
        RELEASE_ANCHORS_CONFIG, default=False, rebuild="env", types=[bool]
    )
    app.add_transform(ReleaseAnchors)
