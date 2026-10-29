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

import os
from pathlib import Path

import pytest

from click_extra._utils import (
    exception_chain,
    flatten,
    generator_tag,
    missing_extra_message,
    patch_attr,
    shrinkuser,
)


def test_exception_chain_ends_on_a_loop():
    """Two exceptions naming each other are each yielded once."""
    spill = ValueError("spill")
    alarm = RuntimeError("alarm")
    alarm.__context__ = spill
    spill.__context__ = alarm
    assert list(exception_chain(alarm)) == [alarm, spill]


def test_exception_chain_follows_the_context_without_a_cause():
    spill = ValueError("spill")
    alarm = RuntimeError("alarm")
    alarm.__context__ = spill
    assert list(exception_chain(alarm)) == [alarm, spill]


def test_exception_chain_of_nothing_is_empty():
    assert list(exception_chain(None)) == []


def test_exception_chain_prefers_the_cause():
    """The cause an exception was raised from wins over the one it replaced."""
    spill = ValueError("spill")
    burn = KeyError("burn")
    alarm = RuntimeError("alarm")
    alarm.__context__ = burn
    alarm.__cause__ = spill
    assert list(exception_chain(alarm)) == [alarm, spill]


def test_generator_tag():
    assert generator_tag() == "Click Extra"


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


def test_flatten_collapses_nested_iterables():
    """Every nesting level is walked, strings and bytes staying whole."""
    nested = [1, (2, [3, {4}]), "ab", b"cd", [[]], ()]
    assert list(flatten(nested)) == [1, 2, 3, 4, "ab", b"cd"]


def test_flatten_of_nothing_is_empty():
    assert list(flatten(())) == []


def test_shrinkuser_spells_the_home_directory_as_a_tilde():
    home = Path.home()
    assert shrinkuser(home) == "~"
    assert shrinkuser(home / "notes" / "todo.txt") == str(
        Path("~", "notes", "todo.txt")
    )
    # A sibling whose name merely starts with the home directory's is left alone.
    assert shrinkuser(f"{home}1") == f"{home}1"
    assert shrinkuser(Path("srv", "www")) == os.path.join("srv", "www")


def test_shrinkuser_takes_another_home_spelling():
    home = Path.home()
    assert shrinkuser(home, home="$HOME") == "$HOME"
    assert shrinkuser(home / "notes", home="$HOME") == os.path.join("$HOME", "notes")
