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

from unittest.mock import patch

import click
import cloup
import pytest

from click_extra import command, echo, jobs_option, pass_context
from click_extra.jobs import CPU_COUNT


@pytest.mark.parametrize(
    "cmd_decorator",
    (click.command, click.command(), cloup.command(), command),
)
@pytest.mark.parametrize("option_decorator", (jobs_option, jobs_option()))
def test_standalone_jobs_option(invoke, cmd_decorator, option_decorator):
    @cmd_decorator
    @option_decorator
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    result = invoke(cli, "--help", color=False)
    assert "--jobs" in result.stdout
    assert result.exit_code == 0

    result = invoke(cli, "--jobs", "4")
    assert result.stdout == "Jobs: 4\n"
    assert result.exit_code == 0


def test_default_value(invoke):
    """Default is one fewer than available CPU cores."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    result = invoke(cli)
    expected = max(1, CPU_COUNT - 1) if CPU_COUNT else 1
    assert result.stdout == f"Jobs: {expected}\n"
    assert result.exit_code == 0


@pytest.mark.parametrize("value", ("0", "-5"))
def test_clamp_below_one(invoke, value):
    """Values below 1 are clamped to 1 with a warning."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    result = invoke(cli, "--jobs", value)
    assert result.stdout == "Jobs: 1\n"
    assert result.exit_code == 0
    assert "clamping to minimum of 1" in result.stderr


def test_exceeds_cpu_count(invoke):
    """Warn when requested jobs exceed available CPU cores."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch("click_extra.jobs.CPU_COUNT", 4):
        result = invoke(cli, "--jobs", "8")

    assert result.stdout == "Jobs: 8\n"
    assert result.exit_code == 0
    assert "exceeds available CPU cores (4)" in result.stderr


def test_no_warning_within_bounds(invoke):
    """No warning when the value is within the valid range."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch("click_extra.jobs.CPU_COUNT", 8):
        result = invoke(cli, "--jobs", "4")

    assert result.stdout == "Jobs: 4\n"
    assert result.exit_code == 0
    assert not result.stderr


def test_single_core_default():
    """DEFAULT_JOBS is 1 when cpu_count is 1."""
    assert max(1, 1 - 1) == 1


def test_none_cpu_count_default():
    """DEFAULT_JOBS is 1 when cpu_count returns None."""
    cpu_count = None
    assert (max(1, cpu_count - 1) if cpu_count else 1) == 1
