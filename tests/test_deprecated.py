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
"""Test the backward-compatible deprecated aliases and their warnings."""

from __future__ import annotations

import re
from importlib import import_module

import pytest

from click_extra._deprecated import DEPRECATED_ALIASES, REMOVAL_VERSION


def _resolve(target: str) -> object:
    """Resolve a registry target, which is relative to the ``click_extra`` package."""
    module_path, _, attr = f"click_extra.{target}".rpartition(".")
    return getattr(import_module(module_path), attr)


# Registry-derived: every alias in DEPRECATED_ALIASES is exercised, so a new
# entry cannot slip in without test coverage.
@pytest.mark.parametrize(
    ("module_id", "deprecated_id", "target"),
    sorted(
        (module_id, name, target)
        for module_id, aliases in DEPRECATED_ALIASES.items()
        for name, target in aliases.items()
    ),
)
def test_deprecated_alias(module_id, deprecated_id, target):
    """Each deprecated alias resolves to its replacement and emits a warning."""
    full_target = f"click_extra.{target}"
    with pytest.deprecated_call(
        match=re.escape(
            f"{module_id}.{deprecated_id} is deprecated and will be removed in "
            f"click-extra {REMOVAL_VERSION}, use {full_target} instead."
        ),
    ):
        resolved = getattr(import_module(module_id), deprecated_id)
    assert resolved is _resolve(target)


@pytest.mark.parametrize("module_id", sorted(DEPRECATED_ALIASES))
def test_unknown_attribute_raises(module_id):
    """A non-registered attribute still raises a standard AttributeError."""
    with pytest.raises(AttributeError, match="has no attribute 'DOES_NOT_EXIST'"):
        _ = import_module(module_id).DOES_NOT_EXIST
