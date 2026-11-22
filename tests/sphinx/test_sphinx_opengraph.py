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
"""Tests for the title hooks that keep the space of a title icon out of `og:title`."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from click_extra.sphinx.opengraph import (
    OPENGRAPH_EXTENSION,
    TITLE_STASH_KEY,
    restore_title,
    strip_title_icon_gap,
)

ICON = '<svg version="1.1" class="sd-octicon"><path d="M2 0h12"></path></svg>'
"""A stand-in for the SVG that sphinx-design renders for an octicon."""


def render(extensions: dict, title: str) -> tuple[str, str]:
    """Run both hooks around the point where sphinxext-opengraph reads the title.

    :return: The title the extension reads, and the title left for the theme.
    """
    app = SimpleNamespace(extensions=extensions)
    context = {"title": title}
    strip_title_icon_gap(app, "index", "page.html", context, None)
    read = context["title"]
    restore_title(app, "index", "page.html", context, None)
    assert TITLE_STASH_KEY not in context
    return read, context["title"]


@pytest.mark.parametrize(
    ("title", "read"),
    (
        pytest.param(f"{ICON} Pears", f"{ICON}Pears", id="leading-icon"),
        pytest.param(f"{ICON}\n  Pears", f"{ICON}Pears", id="line-break"),
        pytest.param("Pears", "Pears", id="no-icon"),
        pytest.param(f"Pears {ICON} plums", f"Pears {ICON} plums", id="inner-icon"),
        pytest.param("", "", id="empty"),
    ),
)
def test_extension_reads_the_title_without_the_icon_gap(title, read):
    """The extension reads the title without the gap, and the theme gets it back."""
    assert render({OPENGRAPH_EXTENSION: object()}, title) == (read, title)


def test_title_untouched_without_the_extension():
    """Without sphinxext-opengraph, no hook changes the title."""
    title = f"{ICON} Pears"
    assert render({}, title) == (title, title)
