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
"""Deprecated import shim for the renamed {mod}`click_extra.test_suite` module.

`click_extra.test_plan` was renamed to `click_extra.test_suite`, and its
`TestPlanConfig` / `parse_test_plan` / `run_test_plan` / `DEFAULT_TEST_PLAN`
API to the `TestSuite` equivalents. Importing this module keeps the historical
path working for a deprecation cycle, re-exporting the renamed symbols under
their old names and warning once on import. See {mod}`click_extra._deprecated`.
"""

from __future__ import annotations

import warnings

from ._deprecated import deprecation_message
from .test_suite import (
    DEFAULT_TEST_SUITE as DEFAULT_TEST_PLAN,
    CLITestCase,
    SkippedTest,
    parse_test_suite as parse_test_plan,
    run_test_suite as run_test_plan,
)

warnings.warn(
    deprecation_message("click_extra.test_plan", "click_extra.test_suite"),
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "DEFAULT_TEST_PLAN",
    "CLITestCase",
    "SkippedTest",
    "parse_test_plan",
    "run_test_plan",
]
