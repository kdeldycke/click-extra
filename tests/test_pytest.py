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
"""Test the Pytest helpers."""

from __future__ import annotations

import re

import pytest
from boltons.strutils import strip_ansi

from click_extra.pytest import (
    default_debug_colored_config,
    default_debug_colored_log_end,
    default_debug_colored_log_start,
    default_debug_colored_logging,
    default_debug_colored_verbose_log,
    default_debug_colored_version_details,
    default_debug_uncolored_config,
    default_debug_uncolored_log_end,
    default_debug_uncolored_log_start,
    default_debug_uncolored_logging,
    default_debug_uncolored_verbose_log,
    default_debug_uncolored_version_details,
    default_options_colored_help,
    default_options_uncolored_help,
)
from click_extra.testing import unescape_regex

REGEX_NEWLINE = "\\n"
"""Newline representation in the regexes above."""


@pytest.mark.parametrize(
    ("uncolored", "colored"),
    (
        (default_options_uncolored_help, default_options_colored_help),
        (default_debug_uncolored_logging, default_debug_colored_logging),
        (default_debug_uncolored_verbose_log, default_debug_colored_verbose_log),
        (default_debug_uncolored_config, default_debug_colored_config),
        (
            default_debug_uncolored_version_details,
            default_debug_colored_version_details,
        ),
        (default_debug_uncolored_log_start, default_debug_colored_log_start),
        (default_debug_uncolored_log_end, default_debug_colored_log_end),
    ),
)
def test_aligned_colored_fixtures(uncolored, colored):
    uncolored_lines = uncolored.split(REGEX_NEWLINE)
    colored_lines = colored.split(REGEX_NEWLINE)

    line_indexes = range(max(len(colored_lines), len(uncolored_lines)))
    for i in line_indexes:
        uncolored_line = uncolored_lines[i]
        colored_line = colored_lines[i]

        unescaped_uncolored_line = unescape_regex(uncolored_line)
        unescaped_colored_line = unescape_regex(colored_line)

        assert strip_ansi(unescaped_colored_line) == unescaped_uncolored_line

    # Check that all lines can be compiled as regexes.
    assert re.compile(uncolored)
    assert re.compile(colored)
