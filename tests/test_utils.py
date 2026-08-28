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
"""Test the generic helpers of the private utility module."""

from __future__ import annotations

import re
from enum import Enum

import pytest

from click_extra._utils import (
    generator_tag,
    memoize_enums,
    missing_extra_message,
    patch_attr,
)


def test_generator_tag():
    assert re.fullmatch(r"Click Extra \d+\.\d+\.\d+(\.\w+)?", generator_tag())


def test_memoize_enums_seeds_every_member_of_a_held_class():
    """A held member seeds its siblings too, not only itself."""

    class Ripeness(Enum):
        GREEN = "green"
        RIPE = "ripe"

    class Basket:
        def __init__(self):
            self.apple = Ripeness.GREEN
            self.crate = "wooden"

    memo: dict[int, object] = {}
    memoize_enums(Basket(), memo)
    assert memo == {
        id(Ripeness.GREEN): Ripeness.GREEN,
        id(Ripeness.RIPE): Ripeness.RIPE,
    }


def test_memoize_enums_leaves_an_enum_free_object_alone():
    class Basket:
        def __init__(self):
            self.crate = "wooden"

    memo: dict[int, object] = {}
    memoize_enums(Basket(), memo)
    assert memo == {}


def test_missing_extra_message():
    msg = missing_extra_message("mkdocs", subject="This module")
    assert msg == (
        "This module requires an optional dependency. "
        "Install it with: pip install click-extra[mkdocs]"
    )
    # The canonical hyphenated distribution name, not the underscore form.
    assert "click_extra[" not in msg


def test_patch_attr_restores_on_exit():
    class Kettle:
        temperature = "cold"

    kettle = Kettle()
    with patch_attr(kettle, "temperature", "boiling"):
        assert kettle.temperature == "boiling"
    assert kettle.temperature == "cold"


def test_patch_attr_restores_on_error():
    class Kettle:
        temperature = "cold"

    kettle = Kettle()
    with pytest.raises(RuntimeError):  # noqa: SIM117
        with patch_attr(kettle, "temperature", "boiling"):
            raise RuntimeError("burner failure")
    assert kettle.temperature == "cold"


def test_patch_attr_requires_existing_attribute():
    class Kettle:
        pass

    with pytest.raises(AttributeError), patch_attr(Kettle(), "temperature", "boiling"):
        pass
