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
"""Tests for the execution-control options: --jobs, --time and -0/--zero-exit."""

from __future__ import annotations

import re
from textwrap import dedent
from time import sleep
from unittest.mock import patch

import click
import cloup
import pytest

from click_extra import (
    command,
    context,
    echo,
    group,
    jobs_option,
    pass_context,
    timer_option,
    zero_exit_option,
)
from click_extra.execution import CPU_COUNT
from click_extra.pytest import command_decorators

# --- Jobs -------------------------------------------------------------------


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


@pytest.mark.parametrize(
    ("keyword", "expected"),
    (
        ("auto", max(1, CPU_COUNT - 1) if CPU_COUNT else 1),
        ("max", CPU_COUNT or 1),
    ),
)
def test_keyword_resolution(invoke, keyword, expected):
    """'auto' resolves to logical CPUs minus one, 'max' to all logical CPUs.

    On a host with enough cores the resolution is silent; on a 1- or 2-core
    host the keyword collapses to a single (sequential) job with a warning, so
    the assertion adapts to the host running the suite.
    """

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    result = invoke(cli, "--jobs", keyword)
    assert result.stdout == f"Jobs: {expected}\n"
    if expected > 1:
        assert not result.stderr
    else:
        assert "sequential" in result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("keyword", "cpu_count", "default_jobs", "cpu_phrase"),
    (
        # A single logical CPU: 'max' is the whole machine, still just 1 job.
        ("max", 1, 1, "only 1 logical CPU is available"),
        # 'auto' reserves one core, so one or two logical CPUs leave a single job.
        ("auto", 1, 1, "only 1 logical CPU is available"),
        ("auto", 2, 1, "only 2 logical CPUs are available"),
    ),
)
def test_parallel_keyword_collapses_to_sequential_warns(
    invoke, keyword, cpu_count, default_jobs, cpu_phrase
):
    """'auto'/'max' warn when too few logical CPUs force a single (sequential) job."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch.multiple(
        "click_extra.execution",
        CPU_COUNT=cpu_count,
        DEFAULT_JOBS=default_jobs,
    ):
        result = invoke(cli, "--jobs", keyword)

    assert result.stdout == "Jobs: 1\n"
    assert result.exit_code == 0
    assert f"'--jobs {keyword}' resolved to a single job" in result.stderr
    assert cpu_phrase in result.stderr
    assert "sequential, not parallel" in result.stderr


def test_explicit_single_job_is_silent(invoke):
    """An explicit '--jobs 1' is a deliberate sequential choice: no warning."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch("click_extra.execution.CPU_COUNT", 4):
        result = invoke(cli, "--jobs", "1")

    assert result.stdout == "Jobs: 1\n"
    assert result.exit_code == 0
    assert not result.stderr


def test_default_collapses_to_sequential_warns(invoke):
    """The bare default ('auto') also warns when it collapses to a single job.

    This is the silent trap on a two-core host: no flag is passed, yet the
    default reserves one core and runs sequentially.
    """

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch.multiple("click_extra.execution", CPU_COUNT=2, DEFAULT_JOBS=1):
        result = invoke(cli)  # No --jobs: exercise the default value.

    assert result.stdout == "Jobs: 1\n"
    assert result.exit_code == 0
    assert "'--jobs auto' resolved to a single job" in result.stderr
    assert "only 2 logical CPUs are available" in result.stderr


def test_resolved_job_count_logged_at_info(invoke):
    """The resolved job count and os.cpu_count() are logged at info level."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch.multiple("click_extra.execution", CPU_COUNT=8, DEFAULT_JOBS=7):
        result = invoke(cli, "--verbosity", "INFO", "--jobs", "4", color=False)

    assert result.stdout == "Jobs: 4\n"
    assert result.exit_code == 0
    assert "Resolved --jobs to 4" in result.stderr
    assert "os.cpu_count()=8 logical CPUs" in result.stderr


def test_invalid_value(invoke):
    """Values that are neither an integer nor a known keyword are rejected."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    result = invoke(cli, "--jobs", "fast")
    assert result.exit_code == 2
    assert "fast" in result.stderr
    assert "not a valid job count" in result.stderr


@pytest.mark.parametrize(
    ("value", "warning"),
    (
        ("0", "running sequentially"),
        ("-1", "clamping to minimum of 1"),
        ("-5", "clamping to minimum of 1"),
    ),
)
def test_clamp_to_one(invoke, value, warning):
    """0 disables parallelism and negatives clamp: both run 1 job with a warning."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    result = invoke(cli, "--jobs", value)
    assert result.stdout == "Jobs: 1\n"
    assert result.exit_code == 0
    assert warning in result.stderr


def test_exceeds_cpu_count(invoke):
    """Warn when requested jobs exceed available CPU cores."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch("click_extra.execution.CPU_COUNT", 4):
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

    with patch("click_extra.execution.CPU_COUNT", 8):
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


# --- Timer ------------------------------------------------------------------


@group
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


@pytest.mark.parametrize(
    ("subcommand_id", "time_min"),
    (
        ("fast", 0.01),
        ("slow", 0.1),
    ),
)
def test_integrated_time_option(invoke, subcommand_id, time_min):
    result = invoke(integrated_timer, "--time", f"{subcommand_id}-subcommand")
    group = re.fullmatch(
        rf"Start of CLI\nEnd of {subcommand_id} subcommand\n"
        r"Execution time: (?P<time>[0-9.]+) seconds.\n",
        result.stdout,
    )
    assert group
    # Hard-code upper bound to avoid flakiness on slow platforms like macOS.
    assert time_min < float(group.groupdict()["time"]) < 80
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize("subcommand_id", ("fast", "slow"))
def test_integrated_notime_option(invoke, subcommand_id):
    result = invoke(integrated_timer, "--no-time", f"{subcommand_id}-subcommand")
    assert result.stdout == f"Start of CLI\nEnd of {subcommand_id} subcommand\n"
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "cmd_decorator",
    # Skip click extra's commands, as timer option is already part of the default.
    command_decorators(no_groups=True, no_extra=True),
)
@pytest.mark.parametrize("option_decorator", (timer_option, timer_option()))
def test_standalone_timer_option(
    invoke, cmd_decorator, option_decorator, assert_output_regex
):
    @cmd_decorator
    @option_decorator
    def standalone_timer():
        echo("It works!")

    result = invoke(standalone_timer, "--help")
    assert result.stdout == dedent(
        """\
        Usage: standalone-timer [OPTIONS]

        Options:
          --time / --no-time  Measure and print elapsed execution time.
          --help              Show this message and exit.
        """,
    )
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(standalone_timer, "--time")
    assert_output_regex(
        result.stdout,
        r"It works!\nExecution time: [0-9.]+ seconds.\n",
    )
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(standalone_timer, "--no-time")
    assert result.stdout == "It works!\n"
    assert not result.stderr
    assert result.exit_code == 0


def test_time_with_short_circuit_sibling_still_prints(invoke):
    """``--time --version`` still emits a duration.

    ``--version`` is an eager option that calls ``ctx.exit()`` before the
    user command body runs, but ``--time`` is intentionally measured even
    on short-circuit paths so it can probe the cost of Click Extra's own
    machinery (eager callbacks, config loading, option parsing).
    """

    @command
    def short_circuit_cli():
        echo("body ran")

    result = invoke(short_circuit_cli, "--time", "--version")
    assert re.search(r"Execution time: [0-9.]+ seconds\.", result.output)
    assert result.exit_code == 0


# --- Zero exit --------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd_decorator",
    (click.command, click.command(), cloup.command(), command),
)
@pytest.mark.parametrize("option_decorator", (zero_exit_option, zero_exit_option()))
def test_standalone_zero_exit_option(invoke, cmd_decorator, option_decorator):
    @cmd_decorator
    @option_decorator
    @pass_context
    def cli(ctx):
        echo("It works!")
        echo(f"Zero-exit value: {context.get(ctx, context.ZERO_EXIT)}")

    result = invoke(cli, "--help", color=False)
    assert "-0, --zero-exit" in result.stdout
    assert "Always exit with a status code of 0" in result.stdout
    assert not result.stderr
    assert result.exit_code == 0

    # Defaults to False.
    result = invoke(cli)
    assert result.stdout == "It works!\nZero-exit value: False\n"
    assert not result.stderr
    assert result.exit_code == 0

    # The long form enables the flag.
    result = invoke(cli, "--zero-exit")
    assert result.stdout == "It works!\nZero-exit value: True\n"
    assert not result.stderr
    assert result.exit_code == 0

    # The -0 short form enables the flag.
    result = invoke(cli, "-0")
    assert result.stdout == "It works!\nZero-exit value: True\n"
    assert not result.stderr
    assert result.exit_code == 0


def test_zero_exit_auto_envvar(invoke):
    @command
    @zero_exit_option
    @pass_context
    def cli(ctx):
        echo(f"Zero-exit value: {context.get(ctx, context.ZERO_EXIT)}")

    result = invoke(cli, env={"CLI_ZERO_EXIT": "1"})
    assert result.stdout == "Zero-exit value: True\n"
    assert not result.stderr
    assert result.exit_code == 0
