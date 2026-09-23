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
import types
from importlib import import_module

import pytest

from click_extra._deprecated import (
    DEPRECATED_ALIASES,
    REMOVAL_VERSION,
    warn_deprecated_argument,
)


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


def test_warn_deprecated_argument_blames_the_caller():
    """The warning names the argument and its replacement, at the call site."""

    def steep(**kwargs):
        warn_deprecated_argument("steep", "minutes", "duration=")

    with pytest.deprecated_call(
        match=re.escape(
            "steep(minutes=...) is deprecated and will be removed in "
            f"click-extra {REMOVAL_VERSION}, use duration= instead."
        ),
    ) as record:
        steep(minutes=4)
    assert record[0].filename == __file__


def test_warn_deprecated_argument_skips_ecosystem_frames():
    """A warning behind a Click ecosystem frame still blames the code to change.

    The real shape is a parameter construction warning: the user's module
    calls a `click` decorator, whose frame sits between the code to change and
    the warning. The funnel below reproduces that frame, in a namespace whose
    `__name__` classifies it the same way.
    """
    fake_click = types.ModuleType("click.decorators")
    # The funnel resolves the helper out of the module's own globals, so seed
    # them with it. ModuleType declares no __setattr__, so a plain attribute
    # assignment would be a type error: write through the namespace the exec
    # below already targets.
    fake_click.__dict__["warn_deprecated_argument"] = warn_deprecated_argument
    exec(
        "def funnel(**kwargs):\n"
        "    warn_deprecated_argument('steep', 'minutes', 'duration=')\n",
        fake_click.__dict__,
    )

    with pytest.deprecated_call() as record:
        fake_click.funnel(minutes=4)
    assert record[0].filename == __file__
