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
"""Test defaults of our custom commands, as well as their customizations and attached
options, and how they interact with each others."""

from __future__ import annotations

import re
from textwrap import dedent
from time import sleep

from pytest_cases import parametrize

from click_extra import echo
from click_extra.decorators import extra_group, timer_option
from click_extra.pytest import command_decorators


@extra_group
def integrated_timer():
    echo("Start of CLI")


@integrated_timer.command()
def fast_subcommand():
    sleep(0.02)
    echo("End of fast subcommand")


@integrated_timer.command()
def slow_subcommand():
    sleep(0.2)
    echo("End of slow subcommand")


@parametrize(
    "subcommand_id, time_min, time_max",
    (
        ("fast", 0.01, 0.2),
        ("slow", 0.1, 1),
    ),
)
def test_integrated_time_option(invoke, subcommand_id, time_min, time_max):
    result = invoke(integrated_timer, "--time", f"{subcommand_id}-subcommand")
    assert result.exit_code == 0
    assert not result.stderr
    group = re.fullmatch(
        rf"Start of CLI\nEnd of {subcommand_id} subcommand\n"
        r"Execution time: (?P<time>[0-9.]+) seconds.\n",
        result.stdout,
    )
    assert group
    assert time_min < float(group.groupdict()["time"]) < time_max


@parametrize("subcommand_id", ("fast", "slow"))
def test_integrated_notime_option(invoke, subcommand_id):
    result = invoke(integrated_timer, "--no-time", f"{subcommand_id}-subcommand")
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == f"Start of CLI\nEnd of {subcommand_id} subcommand\n"


@parametrize(
    "cmd_decorator",
    # Skip click extra's commands, as timer option is already part of the default.
    command_decorators(no_groups=True, no_extra=True),
)
@parametrize("option_decorator", (timer_option, timer_option()))
def test_standalone_timer_option(invoke, cmd_decorator, option_decorator):
    @cmd_decorator
    @option_decorator
    def standalone_timer():
        echo("It works!")

    result = invoke(standalone_timer, "--help")
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == dedent(
        """\
        Usage: standalone-timer [OPTIONS]

        Options:
          --time / --no-time  Measure and print elapsed execution time.
          --help              Show this message and exit.
        """,
    )

    result = invoke(standalone_timer, "--time")
    assert result.exit_code == 0
    assert not result.stderr
    assert re.fullmatch(
        r"It works!\nExecution time: [0-9.]+ seconds.\n",
        result.stdout,
    )

    result = invoke(standalone_timer, "--no-time")
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == "It works!\n"
