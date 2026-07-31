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

from __future__ import annotations

import pytest

from click_extra import config_table_to_flags


@pytest.mark.parametrize(
    ("table", "expected"),
    (
        ({}, []),
        # A truthy flag maps to a bare --key; a falsy one is skipped.
        ({"verbose": True}, ["--verbose"]),
        ({"verbose": False}, []),
        # Scalars become --key=value.
        ({"name": "papaya"}, ["--name=papaya"]),
        ({"jobs": 4}, ["--jobs=4"]),
        ({"ratio": 1.5}, ["--ratio=1.5"]),
        # Sequences repeat the flag, one per item.
        ({"select": ["apple", "cherry"]}, ["--select=apple", "--select=cherry"]),
        ({"select": ("apple", "cherry")}, ["--select=apple", "--select=cherry"]),
        # Hyphenated keys map straight onto long options.
        ({"line-length": 88}, ["--line-length=88"]),
        # Iteration order is preserved.
        ({"quiet": True, "color": False, "jobs": 2}, ["--quiet", "--jobs=2"]),
    ),
)
def test_config_table_to_flags(table, expected) -> None:
    assert config_table_to_flags(table) == expected
