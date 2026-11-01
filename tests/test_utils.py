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

import copy
import os
from configparser import ConfigParser
from pathlib import Path

import pytest

from click_extra._utils import (
    BOOLEAN_STATES,
    GENERATOR_TAG,
    deep_merge,
    exception_chain,
    flatten,
    missing_extra_message,
    parse_bool,
    patch_attr,
    remove_blanks,
    set_nested,
    shrinkuser,
    walk_up,
)
from click_extra.param_tools import ParamStructure


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
    assert GENERATOR_TAG == "Click Extra"


def test_missing_extra_message():
    msg = missing_extra_message("mkdocs", subject="This module")
    assert msg == (
        "This module requires an optional dependency. "
        "Install it with: uv pip install 'click-extra[mkdocs]'"
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


def test_deep_merge_merges_dicts_and_takes_every_other_value_from_the_overlay():
    base = {"a": {"b": 1, "c": [1, 2], "d": {"e": 1}}, "f": "base", "g": {"h": 1}}
    overlay = {"a": {"b": 2, "c": [3]}, "f": {"i": 1}, "j": None}
    assert deep_merge(base, overlay) == {
        "a": {"b": 2, "c": [3], "d": {"e": 1}},
        "f": {"i": 1},
        "g": {"h": 1},
        "j": None,
    }


def test_deep_merge_leaves_both_arguments_alone():
    base = {"a": {"b": 1}}
    overlay = {"a": {"c": 2}}
    merged = deep_merge(base, overlay)
    merged["a"]["d"] = 3
    assert base == {"a": {"b": 1}}
    assert overlay == {"a": {"c": 2}}


SET_NESTED_PATHS: tuple[tuple[tuple[str, ...], object], ...] = (
    (("orchard", "apple", "count"), 3),
    (("orchard", "apple", "color"), "red"),
    (("orchard", "pear"), {"count": 1}),
    (("orchard", "pear"), {"color": "green"}),
    (("orchard", "pear", "count"), 2),
    (("garden",), "tomato"),
    (("garden", "basil"), True),
    (("orchard", "apple"), ["fuji", "gala"]),
    (("orchard", "apple", "count"), 4),
    (("barn",), {"hay": {"bales": 10}}),
    (("barn", "hay"), {"straw": 2}),
)
"""Paths and values covering every case of a merge: a fresh path, a shared prefix,
two dictionaries merging, a dictionary replacing a value, and the reverse."""


def test_set_nested_matches_merging_one_path_trees():
    """Setting each path in place builds the tree the one-path merges built."""
    merged: dict = {}
    nested: dict = {}
    # Copies, since set_nested changes in place a dictionary it stored as a value.
    for keys, value in copy.deepcopy(SET_NESTED_PATHS):
        merged = deep_merge(
            merged, ParamStructure.init_tree_dict(*keys, leaf=copy.deepcopy(value))
        )
        set_nested(nested, keys, value)
        assert nested == merged
    assert nested == {
        "orchard": {
            "apple": {"count": 4},
            "pear": {"count": 2, "color": "green"},
        },
        "garden": {"basil": True},
        "barn": {"hay": {"bales": 10, "straw": 2}},
    }


def test_set_nested_rejects_an_empty_path():
    with pytest.raises(ValueError):
        set_nested({}, (), "apple")


def test_walk_up_starts_at_the_start_and_ends_at_the_root(tmp_path):
    start = tmp_path / "orchard" / "row"
    walked = list(walk_up(start))
    assert walked[:3] == [start, start.parent, tmp_path]
    assert walked[-1] == Path(start.anchor)
    assert len(walked) == len(start.parents) + 1


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        *((spelling, state) for spelling, state in BOOLEAN_STATES.items()),
        ("TRUE", True),
        ("Off", False),
        (" yes ", True),
        ("\t0\n", False),
        ("", None),
        ("2", None),
        ("maybe", None),
    ),
)
def test_parse_bool(text, expected):
    """The spellings read the same whatever their case and surrounding blanks."""
    assert parse_bool(text) is expected


def test_boolean_states_match_configparser():
    """The copy holds the spellings the standard library reads, no more."""
    assert BOOLEAN_STATES == ConfigParser.BOOLEAN_STATES


BLANK_TREE: dict[str, object] = {
    "city": "Lyon",
    "river": "",
    "lake": None,
    "forecast": {"rain": None, "wind": {}, "sky": ""},
    "harbor": {"boats": 0, "docks": [], "flags": False},
    "orchard": {},
}
"""A tree holding a blank value of each kind, at the top and one level down."""


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    (
        pytest.param(
            {},
            {"city": "Lyon", "harbor": {"boats": 0, "docks": [], "flags": False}},
            id="every-blank",
        ),
        pytest.param(
            {"remove_none": False},
            {
                "city": "Lyon",
                "lake": None,
                "forecast": {"rain": None},
                "harbor": {"boats": 0, "docks": [], "flags": False},
            },
            id="keep-none",
        ),
        pytest.param(
            {"remove_dicts": False},
            {
                "city": "Lyon",
                "forecast": {"wind": {}},
                "harbor": {"boats": 0, "docks": [], "flags": False},
                "orchard": {},
            },
            id="keep-dicts",
        ),
        pytest.param(
            {"remove_str": False},
            {
                "city": "Lyon",
                "river": "",
                "forecast": {"sky": ""},
                "harbor": {"boats": 0, "docks": [], "flags": False},
            },
            id="keep-strings",
        ),
        pytest.param(
            {"remove_none": False, "remove_dicts": False, "remove_str": False},
            BLANK_TREE,
            id="keep-everything",
        ),
    ),
)
def test_remove_blanks(kwargs, expected):
    """Each kind of blank value goes, unless its `remove_*` argument keeps it.

    A falsy value that is not blank, like `0`, `False` or an empty list, stays.
    """
    assert remove_blanks(BLANK_TREE, **kwargs) == expected


def test_remove_blanks_drops_a_dict_emptied_by_the_cleaning():
    tree = {"garden": {"shed": {"tools": None}}, "fence": "wood"}
    assert remove_blanks(tree) == {"fence": "wood"}
    assert remove_blanks(tree, remove_dicts=False) == {
        "garden": {"shed": {}},
        "fence": "wood",
    }


def test_remove_blanks_leaves_the_tree_alone():
    tree = {"garden": {"shed": None, "pond": "koi"}}
    cleaned = remove_blanks(tree)
    cleaned["garden"]["bench"] = "oak"
    assert tree == {"garden": {"shed": None, "pond": "koi"}}
