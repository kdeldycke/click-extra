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

from click_extra.color import color_envvars
from click_extra.pytest import (  # noqa: F401
    assert_output_regex,
    create_config,
    invoke,
    runner,
)


@pytest.fixture(scope="session")
def httpserver_listen_address():
    """Bind the local HTTP server to the loopback address, not to a name.

    Overrides ``pytest-httpserver``'s default of ``("localhost", 0)``. Resolving
    that name is the one thing the ``tests/test_config.py`` cases serving a
    configuration file over HTTP need from the host, and a build sandbox is
    exactly where it is unavailable: the Nix one on macOS denies the lookup, so
    every one of them errors out with ``socket.gaierror: [Errno 8] nodename nor
    servname provided, or not known``.

    Binding the literal address asks nothing of the resolver. Whether a sandbox
    additionally gates the loopback socket is its own policy, and a separate
    question: this only removes the lookup that failed first.
    """
    return ("127.0.0.1", 0)


@pytest.fixture(autouse=True)
def _isolate_color_envvars():
    """Remove output-affecting environment variables so tests are deterministic.

    Variables like ``NO_COLOR`` and ``LLM`` are commonly set by shells, editors,
    and AI tooling. Their presence overrides ``ColorOption``'s default, making
    color-dependent tests fail in developer environments. ``ACCESSIBLE`` is
    isolated for the same reason: it lowers the ``--color`` and ``--table-format``
    defaults.
    """
    isolated = (*color_envvars, "ACCESSIBLE")
    saved = {var: os.environ.pop(var) for var in isolated if var in os.environ}
    yield
    os.environ.update(saved)


skip_windows_colors = skip_windows(reason="Click overstrip colors on Windows")
"""Skips color tests on Windows as ``click.testing.invoke`` overzealously strips colors.

See:
- https://github.com/pallets/click/issues/2111
- https://github.com/pallets/click/issues/2110
"""
