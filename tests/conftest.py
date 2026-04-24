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
"""Fixtures, configuration and helpers for tests."""

from __future__ import annotations

import os

import pytest
from extra_platforms.pytest import skip_windows

from click_extra.colorize import color_envvars
from click_extra.pytest import (  # noqa: F401
    assert_output_regex,
    create_config,
    extra_runner,
    invoke,
)


@pytest.fixture(autouse=True)
def _isolate_color_envvars():
    """Remove color-affecting environment variables so tests are deterministic.

    Variables like ``NO_COLOR`` and ``LLM`` are commonly set by shells, editors,
    and AI tooling. Their presence overrides ``ColorOption``'s default, making
    color-dependent tests fail in developer environments.
    """
    saved = {var: os.environ.pop(var) for var in color_envvars if var in os.environ}
    yield
    os.environ.update(saved)


skip_windows_colors = skip_windows(reason="Click overstrip colors on Windows")
"""Skips color tests on Windows as ``click.testing.invoke`` overzealously strips colors.

See:
- https://github.com/pallets/click/issues/2111
- https://github.com/pallets/click/issues/2110
"""
