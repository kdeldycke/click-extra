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

import os
import re
from pathlib import Path

import click
import pytest

from click_extra import command, echo, option, strip_ansi, style
from click_extra.color import COLOR_ENVVARS
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
from click_extra.testing import REGEX_NEWLINE, unescape_regex


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


def test_isolated_app_dir(invoke, isolated_app_dir):
    """Config discovery is repointed at the isolated directory.

    A CLI invoked in-process must not see the host's real configuration
    folder, and a configuration file planted in the isolated directory must be
    picked up by the default ``--config`` search pattern.
    """
    # Every application name resolves to the same isolated directory.
    assert Path(click.get_app_dir("any-app")) == isolated_app_dir
    assert Path(click.get_app_dir("other-app", roaming=False)) == isolated_app_dir

    @command
    @option("--dummy-flag/--no-flag")
    def my_cli(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    # The isolated directory starts empty: no configuration is discovered.
    result = invoke(my_cli)
    assert result.exit_code == 0
    assert result.stdout == "dummy_flag = False\n"

    # A file planted in the isolated directory is discovered by default.
    (isolated_app_dir / "config.toml").write_text(
        "[my-cli]\ndummy_flag = true\n",
        encoding="utf-8",
    )
    result = invoke(my_cli)
    assert result.exit_code == 0
    assert result.stdout == "dummy_flag = True\n"


@pytest.fixture(params=sorted(COLOR_ENVVARS))
def ambient_color_var(request, monkeypatch):
    """One color variable set in the caller's shell, before `runner` starts.

    Requested ahead of `runner` in a signature, so the variable is in place by the
    time the fixture isolates the environment.
    """
    monkeypatch.setenv(request.param, "1")
    return request.param


def test_runner_ignores_ambient_color_vars(ambient_color_var, runner):
    """A color variable of the caller's shell does not reach the invoked CLI.

    Each one can switch the colors of the output a test matches as plain text.
    """
    assert ambient_color_var not in os.environ

    @command
    def my_cli():
        echo(style("Apricot", fg="green"))

    result = runner.invoke(my_cli)
    assert result.exit_code == 0
    assert result.stdout == "Apricot\n"


def test_runner_lets_a_test_ask_for_color(runner):
    """A variable passed to one invocation still turns its colors on."""

    @command
    def my_cli():
        echo(style("Apricot", fg="green"))

    result = runner.invoke(my_cli, env={"FORCE_COLOR": "1"})
    assert result.exit_code == 0
    assert result.stdout != "Apricot\n"
    assert strip_ansi(result.stdout) == "Apricot\n"
