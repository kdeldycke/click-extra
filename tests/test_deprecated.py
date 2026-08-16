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

import inspect
import re
from importlib import import_module, reload

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


def test_test_plan_module_shim():
    """Importing the renamed test_plan module warns and re-exports the old names."""
    test_plan = import_module("click_extra.test_plan")
    with pytest.deprecated_call(
        match=re.escape(
            "click_extra.test_plan is deprecated and will be removed in "
            f"click-extra {REMOVAL_VERSION}, use click_extra.test_suite instead.",
        ),
    ):
        reload(test_plan)

    test_suite = import_module("click_extra.test_suite")
    assert test_plan.CLITestCase is test_suite.CLITestCase
    assert test_plan.SkippedTest is test_suite.SkippedTest
    assert test_plan.DEFAULT_TEST_PLAN is test_suite.DEFAULT_TEST_SUITE
    assert test_plan.parse_test_plan is test_suite.parse_test_suite
    assert test_plan.run_test_plan is test_suite.run_test_suite


def test_man_page_module_shim():
    """Importing the renamed man_page module warns and re-exports the old names."""
    man_page = import_module("click_extra.man_page")
    with pytest.deprecated_call(
        match=re.escape(
            "click_extra.man_page is deprecated and will be removed in "
            f"click-extra {REMOVAL_VERSION}, use click_extra.command_doc instead.",
        ),
    ):
        reload(man_page)

    command_doc = import_module("click_extra.command_doc")
    # The model shed its Man prefix when roff stopped being its only backend.
    assert man_page.ManPage is command_doc.CommandDoc
    assert man_page.ManOptionItem is command_doc.DocOptionItem
    assert man_page.ManOptionGroup is command_doc.DocOptionGroup
    assert man_page.extract_manpage is command_doc.extract_command_doc
    # The names that never changed stay reachable from the old path too.
    assert man_page.ManOption is command_doc.ManOption
    assert man_page.render_help is command_doc.render_help
    assert man_page.HELP_FORMATS is command_doc.HELP_FORMATS


def test_man_page_shim_covers_the_whole_surface():
    """Nothing public is lost on the way through the shim.

    A symbol added to `command_doc` and forgotten here would be an import error
    for anyone still on the old path, which is exactly what the shim exists to
    prevent.
    """
    man_page = import_module("click_extra.man_page")
    command_doc = import_module("click_extra.command_doc")

    public = {
        name
        for name in vars(command_doc)
        if not name.startswith("_") and name not in {"annotations", "TYPE_CHECKING"}
    }
    # Only the module's own symbols, not the modules and helpers it imported
    # to build them.
    own = {
        name
        for name in public
        if not inspect.ismodule(vars(command_doc)[name])
        and getattr(vars(command_doc)[name], "__module__", command_doc.__name__)
        == command_doc.__name__
    }
    assert own <= set(man_page.__all__)
