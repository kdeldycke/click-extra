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
"""Tests for `readme.md`, which ships to PyPI as the long description."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

README = Path(__file__).parent.parent / "readme.md"

URL_RE = re.compile(
    r"\]\((?P<markdown>[^)\s]+)"
    r"""|\s(?:href|src)=["'](?P<html>[^"']+)["']"""
    r"|^\[[^\]]+\]:\s*(?P<definition>\S+)",
    re.MULTILINE,
)
"""Target of every link and image in a Markdown file.

Matches the inline Markdown forms, `[text](url)` and `![alt](url)`, the `href`
and `src` attributes of an HTML tag, and a reference definition,
`[label]: url`.
"""


@pytest.mark.once
def test_readme_links_and_images_are_absolute() -> None:
    """Every link and image of `readme.md` points at an absolute URL.

    `pyproject.toml` sets `readme = "readme.md"`, so this file ships verbatim as
    the PyPI long description. GitHub resolves a relative target against the
    repository. PyPI has no repository to resolve it against, so the image
    breaks or the link goes nowhere, on the published project page alone.
    """
    targets = [
        match["markdown"] or match["html"] or match["definition"]
        for match in URL_RE.finditer(README.read_text(encoding="UTF-8"))
    ]
    assert targets, "no link or image found in readme.md"
    relative = [target for target in targets if not urlsplit(target).scheme]
    assert not relative, f"readme.md has relative links or images: {relative}"
