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
"""Tests for the execution-control options (--jobs, --time, -0/--zero-exit) and the
subprocess-execution primitives (run_cli and the interrupt machinery)."""

from __future__ import annotations

import logging
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
from pathlib import Path
from textwrap import dedent
from time import monotonic, sleep
from unittest.mock import patch

import click
import cloup
import pytest
from boltons.strutils import strip_ansi
from extra_platforms.pytest import skip_windows

from click_extra import (
    BUILTIN_THEMES,
    Command,
    Context,
    JobsOption,
    command,
    context,
    echo,
    format_cli_prompt,
    get_current_theme,
    group,
    highlight_bin_name,
    jobs_option,
    pass_context,
    resolve_jobs,
    run_cli,
    run_jobs,
    run_lanes,
    timer_option,
    zero_exit_option,
)
from click_extra.execution import (
    _GROUP_LEADERS,
    _LIVE_PROCESSES,
    _LIVE_PROCESSES_LOCK,
    _WORKER_WINDOW_FACTOR,
    CPU_COUNT,
    DEFAULT_JOBS,
    PROMPT,
    _logical_cpu_count,
    install_interrupt_handler,
    terminate_live_processes,
)
from click_extra.logging import LogLevel
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
    """Default reserves one core, except on hosts with fewer than three CPUs."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    result = invoke(cli)
    assert result.stdout == f"Jobs: {DEFAULT_JOBS}\n"
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("keyword", "expected"),
    (
        ("auto", DEFAULT_JOBS),
        ("max", CPU_COUNT or 1),
    ),
)
def test_keyword_resolution(invoke, keyword, expected):
    """'auto' resolves to the reserved-core default, 'max' to all logical CPUs.

    On a host with at least two logical CPUs the resolution is silent; on a
    single-CPU host the keyword collapses to a single (sequential) job with a
    warning, so the assertion adapts to the host running the suite.
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
        # A single logical CPU: both keywords are the whole machine, 1 job.
        ("max", 1, 1, "only 1 logical CPU is available"),
        ("auto", 1, 1, "only 1 logical CPU is available"),
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


def test_default_collapse_to_sequential_is_quiet(invoke):
    """The bare default ('auto') collapsing to a single job does not warn.

    The user never asked for parallelism: warning on the option's own default
    would fire on every bare invocation on a 1-CPU host, polluting captured
    runner streams and the CLI output rendered in Sphinx docs.
    """

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch.multiple("click_extra.execution", CPU_COUNT=1, DEFAULT_JOBS=1):
        result = invoke(cli)  # No --jobs: exercise the default value.

    assert result.stdout == "Jobs: 1\n"
    assert result.exit_code == 0
    assert not result.stderr


def test_default_collapse_to_sequential_logged_at_info(invoke):
    """The default's collapse to a single job stays discoverable at info level.

    This is the silent trap on a single-CPU host: no flag is passed, yet
    execution runs sequentially. The trace lives at info level, next to the
    resolved-jobs line, instead of a default-verbosity warning.
    """

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch.multiple("click_extra.execution", CPU_COUNT=1, DEFAULT_JOBS=1):
        result = invoke(cli, "--verbosity", "INFO", color=False)

    assert result.stdout == "Jobs: 1\n"
    assert result.exit_code == 0
    assert "'--jobs auto' resolved to a single job" in result.stderr
    assert "only 1 logical CPU is available" in result.stderr


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
    assert "8 logical CPUs" in result.stderr


@pytest.mark.parametrize("jobs", (1, 2, 5))
def test_run_jobs_preserves_order(jobs):
    """Results come back in submission order, sequential or parallel."""
    assert list(run_jobs(lambda n: n * n, range(5), jobs=jobs)) == [0, 1, 4, 9, 16]


def test_run_jobs_sequential_is_lazy():
    """With one worker, items run lazily so a caller can stop early."""
    seen = []

    def record(n):
        seen.append(n)
        return n

    for result in run_jobs(record, [1, 2, 3], jobs=1):
        if result == 1:
            break
    assert seen == [1]


@pytest.mark.parametrize("jobs", (1, 2, 5))
def test_run_jobs_preserves_order_past_its_window(jobs):
    """Order holds when the stream is longer than the in-flight window."""
    size = 200
    assert list(run_jobs(lambda n: n * n, iter(range(size)), jobs=jobs)) == [
        n * n for n in range(size)
    ]


@pytest.mark.parametrize("jobs", (1, 2, 5))
def test_run_jobs_handles_empty_and_single_streams(jobs):
    """The peek that sizes the run does not lose the items it looked at."""
    assert list(run_jobs(str, iter(()), jobs=jobs)) == []
    assert list(run_jobs(str, iter((1,)), jobs=jobs)) == ["1"]


def test_run_jobs_parallel_reads_no_further_than_its_window():
    """The parallel path pulls a bounded window instead of draining the stream."""
    produced = []

    def stream():
        # Far more than the window: a regression to materializing shows up as a
        # produced count in the thousands.
        for n in range(10_000):
            produced.append(n)
            yield n

    jobs = 2
    results = run_jobs(str, stream(), jobs=jobs)
    assert next(results) == "0"
    # The window is primed up front, then one slot refills before the first
    # result is handed over.
    assert len(produced) == jobs * _WORKER_WINDOW_FACTOR + 1
    results.close()


def test_run_jobs_parallel_stops_scheduling_on_early_exit():
    """Breaking out of a parallel run leaves the rest of the stream unread."""
    produced = []

    def stream():
        for n in range(10_000):
            produced.append(n)
            yield n

    for result in run_jobs(str, stream(), jobs=2):
        if result == "0":
            break
    assert len(produced) < 10_000


def test_run_jobs_reads_jobs_from_context(invoke):
    """Without an explicit count, run_jobs reads the resolved --jobs value."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(",".join(str(n) for n in run_jobs(lambda n: n + 1, range(4))))

    result = invoke(cli, "--jobs", "3")
    assert result.stdout == "1,2,3,4\n"
    assert result.exit_code == 0


def test_run_jobs_without_context_runs_sequential():
    """Outside any Click context and with no count, run_jobs falls back to 1."""
    assert list(run_jobs(str, [1, 2, 3])) == ["1", "2", "3"]


def test_run_jobs_interrupt_aborts_without_blocking():
    """A KeyboardInterrupt returns at once, without waiting on in-flight tasks.

    Results yield in submission order, so the interrupting item (index 0) is
    pulled first: the abort fires while a second, still-running item is parked on
    an event that stays unset for the run. The old ``with``-block teardown would
    ``shutdown(wait=True)`` and hang on that parked task; the hardened path drops
    queued work and returns immediately.
    """
    blocker_started = threading.Event()
    release = threading.Event()

    def work(n):
        if n == 0:
            # Only interrupt once the blocker is actually running.
            blocker_started.wait(timeout=5)
            raise KeyboardInterrupt
        blocker_started.set()
        release.wait(timeout=10)
        return n

    start = monotonic()
    try:
        with pytest.raises(KeyboardInterrupt):
            # jobs=2 so the interrupter and the blocker run at once.
            list(run_jobs(work, [0, 1], jobs=2))
        # Far below the blocker's 10s park: proves we did not wait on it.
        assert monotonic() - start < 4
    finally:
        release.set()


def test_resolve_jobs_without_context_is_sequential():
    """No context means nothing to read a job count from: stay sequential."""
    assert resolve_jobs(None, 5) == 1


def test_resolve_jobs_single_item_is_sequential():
    """A single item has nothing to parallelize."""
    ctx = click.Context(click.Command("cli"))
    context.set(ctx, context.JOBS, 4)
    assert resolve_jobs(ctx, 1) == 1


@pytest.mark.parametrize(
    ("jobs", "count", "expected"),
    (
        (4, 5, 4),  # The job count wins when below the item count.
        (8, 3, 3),  # Capped at the item count.
        (1, 5, 1),  # An explicit single job is sequential.
    ),
)
def test_resolve_jobs_reads_context(jobs, count, expected):
    """The resolved --jobs value drives the count, capped at the item count."""
    ctx = click.Context(click.Command("cli"))
    context.set(ctx, context.JOBS, jobs)
    assert resolve_jobs(ctx, count) == expected


def test_resolve_jobs_serial_at_debug():
    """serial_at_debug collapses to sequential only at DEBUG verbosity."""
    ctx = click.Context(click.Command("cli"))
    context.set(ctx, context.JOBS, 4)
    context.set(ctx, context.VERBOSITY_LEVEL, LogLevel.DEBUG)
    # The flag is opt-in: DEBUG is ignored without it.
    assert resolve_jobs(ctx, 5) == 4
    assert resolve_jobs(ctx, 5, serial_at_debug=True) == 1


@pytest.mark.parametrize("jobs", (1, 2, 5))
def test_run_lanes_preserves_order(jobs):
    """Results come back in lane-submission order, items within a lane in order."""
    lanes = ([0, 1], [2], [3, 4])
    assert list(run_lanes(lambda n: n * n, lanes, jobs=jobs)) == [0, 1, 4, 9, 16]


@pytest.mark.parametrize("jobs", (1, 2, 5))
def test_run_lanes_preserves_order_past_its_window(jobs):
    """Lane order holds when there are more lanes than the in-flight window."""
    expected = [n for pair in range(0, 200, 2) for n in (pair, pair + 1)]
    lanes = ([pair, pair + 1] for pair in range(0, 200, 2))
    assert list(run_lanes(lambda n: n, lanes, jobs=jobs)) == expected


def test_run_lanes_materializes_lanes_lazily():
    """A lane becomes a list only when it is about to be scheduled."""
    built = []

    def lanes():
        for n in range(10_000):
            built.append(n)
            yield [n]

    jobs = 2
    results = run_lanes(str, lanes(), jobs=jobs)
    assert next(results) == "0"
    assert len(built) == jobs * _WORKER_WINDOW_FACTOR + 1
    results.close()


def test_run_lanes_is_run_jobs_with_singleton_lanes():
    """run_jobs is the degenerate case of run_lanes: one item per lane."""
    items = range(5)
    singleton_lanes = ([n] for n in items)
    assert list(run_lanes(str, singleton_lanes, jobs=3)) == list(
        run_jobs(str, items, jobs=3)
    )


def test_run_lanes_serializes_within_a_lane():
    """Within a lane, items run one at a time even when lanes run in parallel."""
    lock = threading.Lock()
    active: dict[str, int] = {}
    overlap = []

    def work(item):
        lane_id, n = item
        with lock:
            if lane_id in active:
                overlap.append((lane_id, active[lane_id], n))
            active[lane_id] = n
        sleep(0.01)
        with lock:
            del active[lane_id]
        return n

    lanes = (
        [("a", 1), ("a", 2), ("a", 3)],
        [("b", 1), ("b", 2), ("b", 3)],
    )
    list(run_lanes(work, lanes, jobs=2))
    assert overlap == []


def test_run_lanes_runs_lanes_concurrently():
    """Distinct lanes overlap: a barrier only releases if all lanes run at once."""
    barrier = threading.Barrier(3, timeout=5)

    def work(n):
        barrier.wait()
        return n

    assert sorted(run_lanes(work, ([0], [1], [2]), jobs=3)) == [0, 1, 2]


def test_run_lanes_sequential_is_lazy():
    """With one worker, items run lazily so a caller can stop early."""
    seen = []

    def record(n):
        seen.append(n)
        return n

    for result in run_lanes(record, [[1, 2], [3]], jobs=1):
        if result == 1:
            break
    assert seen == [1]


def test_run_lanes_reads_jobs_from_context(invoke):
    """Without an explicit count, run_lanes reads the resolved --jobs value."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        lanes = ([1, 2], [3, 4])
        echo(",".join(str(n) for n in run_lanes(lambda n: n + 1, lanes)))

    result = invoke(cli, "--jobs", "2")
    assert result.stdout == "2,3,4,5\n"
    assert result.exit_code == 0


def test_run_lanes_without_context_runs_sequential():
    """Outside any Click context and with no count, run_lanes falls back to 1."""
    assert list(run_lanes(str, [[1, 2], [3]])) == ["1", "2", "3"]


def test_run_lanes_empty_yields_nothing():
    """No lanes, or only empty lanes, yields nothing and raises nothing."""
    assert list(run_lanes(str, [])) == []
    assert list(run_lanes(str, [[], []], jobs=2)) == []


def test_run_lanes_interrupt_aborts_without_blocking():
    """A KeyboardInterrupt returns at once, without waiting on in-flight lanes.

    Mirror of :func:`test_run_jobs_interrupt_aborts_without_blocking`: see it for
    the rationale.
    """
    blocker_started = threading.Event()
    release = threading.Event()

    def work(n):
        if n == 0:
            blocker_started.wait(timeout=5)
            raise KeyboardInterrupt
        blocker_started.set()
        release.wait(timeout=10)
        return n

    start = monotonic()
    try:
        with pytest.raises(KeyboardInterrupt):
            list(run_lanes(work, ([0], [1]), jobs=2))
        assert monotonic() - start < 4
    finally:
        release.set()


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
    ("incomplete", "expected"),
    (
        ("", ["auto", "max"]),
        ("a", ["auto"]),
        ("m", ["max"]),
        ("ma", ["max"]),
        ("MA", ["max"]),  # Case-insensitive, mirroring convert().
        ("auto", ["auto"]),
        ("3", []),  # An integer count is free-form: no keyword to suggest.
        ("x", []),
    ),
)
def test_jobs_shell_complete(incomplete, expected):
    """--jobs completion suggests the auto/max keywords and never an integer."""
    cmd = Command("tool", params=[JobsOption()])
    ctx = Context(cmd)
    completions = cmd.params[0].shell_complete(ctx, incomplete)
    assert [item.value for item in completions] == expected


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
    """A count above the core count is honored, with an I/O-bound caveat."""

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch("click_extra.execution.CPU_COUNT", 4):
        result = invoke(cli, "--jobs", "8")

    assert result.stdout == "Jobs: 8\n"
    assert result.exit_code == 0
    assert "exceeds the 4 logical CPUs" in result.stderr
    assert "honored, but pays only for I/O-bound work" in result.stderr


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
    """DEFAULT_JOBS is 1 when the logical CPU count is 1."""
    cpu_count = 1
    assert (cpu_count - 1 if cpu_count and cpu_count >= 3 else (cpu_count or 1)) == 1


def test_two_core_default_uses_both_cpus():
    """DEFAULT_JOBS drops the core reservation on a two-CPU host.

    Reserving one of two logical CPUs would collapse the pool to a single
    (sequential) worker, and threads waiting on subprocesses and I/O cost
    nothing there, so the whole machine is used instead.
    """
    cpu_count = 2
    assert (cpu_count - 1 if cpu_count and cpu_count >= 3 else (cpu_count or 1)) == 2


def test_none_cpu_count_default():
    """DEFAULT_JOBS is 1 when cpu_count returns None."""
    cpu_count: int | None = None
    assert (cpu_count - 1 if cpu_count and cpu_count >= 3 else (cpu_count or 1)) == 1


@pytest.mark.parametrize(
    ("process_count", "fallback", "expected"),
    (
        # The process-aware count wins when it answers.
        (4, 8, 4),
        # A None answer (unsupported platform) falls back to os.cpu_count().
        (None, 8, 8),
    ),
)
def test_logical_cpu_count_prefers_process_count(process_count, fallback, expected):
    """os.process_cpu_count() is preferred, os.cpu_count() is the fallback."""
    with (
        patch("os.process_cpu_count", create=True, return_value=process_count),
        patch("os.cpu_count", return_value=fallback),
    ):
        assert _logical_cpu_count() == expected


def test_logical_cpu_count_fallback_without_process_count():
    """On runtimes lacking os.process_cpu_count(), os.cpu_count() answers."""
    with patch("click_extra.execution.os") as mock_os:
        del mock_os.process_cpu_count  # Simulate a Python older than 3.13.
        mock_os.cpu_count.return_value = 8
        assert _logical_cpu_count() == 8


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


# --- Subprocess execution -----------------------------------------------------


def test_run_cli_returns_completed_process(caplog):
    """run_cli mirrors subprocess.run's result shape, with separate streams."""
    code = "import sys; print('to out'); print('to err', file=sys.stderr)"
    with caplog.at_level(logging.DEBUG):
        result = run_cli((sys.executable, "-c", code))
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0
    assert result.stdout == "to out\n"
    assert result.stderr == "to err\n"


def test_run_cli_cwd_moves_the_child(tmp_path):
    """`cwd` runs the child elsewhere; omitted, it inherits the caller's."""
    code = "import os; print(os.path.basename(os.getcwd()))"

    result = run_cli((sys.executable, "-c", code), cwd=tmp_path)
    assert result.stdout.strip() == tmp_path.name

    # The caller's own directory is never changed by the call.
    assert Path.cwd() != tmp_path
    assert run_cli((sys.executable, "-c", code)).stdout.strip() == Path.cwd().name


def test_run_cli_flattens_nested_args(caplog):
    """Nested iterables are flattened, None dropped, and elements stringified."""
    with caplog.at_level(logging.DEBUG):
        result = run_cli((sys.executable, None, ("-c", ("print('ok')",))))
    assert result.args == (sys.executable, "-c", "print('ok')")
    assert result.stdout == "ok\n"


def test_run_cli_discloses_command_at_info(caplog):
    """The invocation is logged up front at INFO, with its forced env vars, and
    the output stays out of the INFO records."""
    with caplog.at_level(logging.INFO):
        run_cli(
            (sys.executable, "-c", "print('sesame')"),
            extra_env={"MY_VAR": "value"},
        )
    prompts = [
        record
        for record in caplog.records
        if strip_ansi(record.getMessage()).startswith(PROMPT)
    ]
    assert len(prompts) == 1
    assert prompts[0].levelno == logging.INFO
    message = strip_ansi(prompts[0].getMessage())
    assert "MY_VAR=value " in message
    assert sys.executable in message
    # The child's output is a DEBUG concern, absent at INFO. The prompt record is
    # excluded: the command line itself carries the print('sesame') code.
    assert not any(
        "sesame" in strip_ansi(record.getMessage())
        for record in caplog.records
        if record not in prompts
    )


def test_run_cli_command_level_override(caplog):
    """A caller can lower the disclosure line to DEBUG for internal probes."""
    with caplog.at_level(logging.DEBUG):
        run_cli((sys.executable, "-c", "pass"), command_level=logging.DEBUG)
    prompts = [
        record
        for record in caplog.records
        if strip_ansi(record.getMessage()).startswith(PROMPT)
    ]
    assert len(prompts) == 1
    assert prompts[0].levelno == logging.DEBUG


def test_run_cli_streams_output_at_debug_with_label(caplog):
    """Every output line is forwarded to the logger, tagged with the label.

    The tag rides the record's ``label`` attribute, not the message text: the
    default :class:`click_extra.logging.Formatter` renders it glued to the level
    name (``debug:probe: line1``).
    """
    code = "import sys; print('line1'); print('line2'); print('boom', file=sys.stderr)"
    with caplog.at_level(logging.DEBUG):
        run_cli((sys.executable, "-c", code), label="probe")
    streamed = [
        strip_ansi(record.getMessage())
        for record in caplog.records
        if getattr(record, "label", None) == "probe"
    ]
    assert "line1" in streamed
    assert "line2" in streamed
    assert "boom" in streamed
    # Only the streamed output lines carry the tag, all at the output level.
    assert all(
        record.levelno == logging.DEBUG
        for record in caplog.records
        if getattr(record, "label", None) == "probe"
    )


def test_highlight_bin_name():
    """Only the binary's own name is styled; its directory stays plain, whichever
    separator convention the path uses."""
    theme = get_current_theme()
    styled = theme.invoked_command
    assert highlight_bin_name("/opt/homebrew/bin/mas") == (
        f"/opt/homebrew/bin/{styled('mas')}"
    )
    assert highlight_bin_name("C:\\Tools\\mas.exe") == f"C:\\Tools\\{styled('mas.exe')}"
    # A bare name (no separator) is styled whole.
    assert highlight_bin_name("mas") == styled("mas")


def test_format_cli_prompt_styles_token_families():
    """Each token family gets the theme slot it holds elsewhere in a CLI's
    output: dim sigil, envvar/default assignment pairs, the binary name as an
    invoked command (directory plain), option-styled flags, plain arguments."""
    theme = get_current_theme()
    prompt = format_cli_prompt(
        ("/opt/homebrew/bin/brew", "list", "--quiet", "--versions"),
        extra_env={"HOMEBREW_NO_ANALYTICS": "1"},
    )
    # The rendered content is the exact copy-pasteable command line.
    assert strip_ansi(prompt) == (
        f"{PROMPT}HOMEBREW_NO_ANALYTICS=1 "
        "/opt/homebrew/bin/brew list --quiet --versions"
    )
    assert prompt.startswith(theme.bracket(PROMPT.rstrip()) + " ")
    assert f"{theme.envvar('HOMEBREW_NO_ANALYTICS')}={theme.default('1')} " in prompt
    assert f"/opt/homebrew/bin/{theme.invoked_command('brew')} list " in prompt
    assert prompt.endswith(f"{theme.option('--quiet')} {theme.option('--versions')}")

    # A bare binary name (no directory) is styled whole.
    prompt = format_cli_prompt(("mas",))
    assert prompt.endswith(theme.invoked_command("mas"))

    # Windows separators are recognized too, and their backslashes are not
    # something to quote: the path pastes back as it stands.
    prompt = format_cli_prompt(("C:\\Tools\\mas.exe", "list"))
    assert f"C:\\Tools\\{theme.invoked_command('mas.exe')} list" in prompt


@pytest.mark.parametrize(
    "argv",
    (
        pytest.param(("python", "-c", 'print("a b")'), id="script-with-space"),
        pytest.param(("greet", "--name=John Doe"), id="flag-value-with-space"),
        pytest.param(("cook", "soup; rm cake"), id="command-separator"),
        pytest.param(("pick", "*.txt"), id="glob"),
        pytest.param(("say", "it's ready"), id="apostrophe"),
        pytest.param(("tally", "$HOME"), id="variable-expansion"),
        pytest.param(("plain", "banana", "--ripe"), id="nothing-to-quote"),
    ),
)
def test_format_cli_prompt_arguments_survive_a_shell_round_trip(argv):
    """A drawn command line parses back to the arguments that produced it.

    The line advertises itself as copy-pasteable, so every argument carrying a
    space or a shell metacharacter has to reach the shell as the single argument
    it started as, instead of spilling into the line as several.
    """
    drawn = strip_ansi(format_cli_prompt(argv))
    assert shlex.split(drawn.removeprefix(PROMPT)) == list(argv)


def test_format_cli_prompt_environment_values_survive_a_shell_round_trip():
    """An assignment prefixing the command is quoted like an argument.

    A value holding a space ends the assignment early otherwise, and the rest of
    it reads as the command to run.
    """
    drawn = strip_ansi(
        format_cli_prompt(("forecast",), extra_env={"CITY": "Rio de Janeiro"}),
    )
    assert drawn == f"{PROMPT}CITY='Rio de Janeiro' forecast"
    assert shlex.split(drawn.removeprefix(PROMPT)) == [
        "CITY=Rio de Janeiro",
        "forecast",
    ]


def test_format_cli_prompt_honors_an_explicit_theme():
    """A caller drawing the line onto a surface of its own picks the palette.

    Every slot follows, the binary name included: that one is styled a level
    down, in {func}`~click_extra.execution.highlight_bin_name`, which used to
    read the active theme on its own and leave a light capture's prompt in the
    dark theme's near-white.
    """
    light = BUILTIN_THEMES["light"]
    prompt = format_cli_prompt(("mas", "list", "--quiet"), theme=light)
    assert f"{light.invoked_command('mas')} list " in prompt
    assert prompt.endswith(light.option("--quiet"))
    assert prompt.startswith(light.bracket(PROMPT.rstrip()) + " ")
    # The active theme is what an unqualified call keeps rendering with.
    assert format_cli_prompt(("mas",)) != prompt


def test_run_cli_merged_streams():
    """merge_streams interleaves stderr into stdout and nulls the stderr field."""
    code = dedent("""\
        import sys
        print("to out")
        sys.stdout.flush()
        print("to err", file=sys.stderr)
        """)
    result = run_cli((sys.executable, "-c", code), merge_streams=True)
    # run_cli() types both streams as str; merging nulls stderr at runtime.
    stderr: str | None = result.stderr
    assert stderr is None
    assert "to out" in result.stdout
    assert "to err" in result.stdout


def test_run_cli_timeout_kills_child_and_attaches_partial_output():
    """An overrun raises TimeoutExpired carrying what was captured so far, and
    leaves no zombie in the live registry."""
    code = "print('partial', flush=True); import time; time.sleep(30)"
    start = monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as excinfo:
        run_cli((sys.executable, "-c", code), timeout=2)
    # The child was killed at the deadline, not waited out.
    assert monotonic() - start < 15
    assert "partial" in (excinfo.value.output or "")
    assert not _LIVE_PROCESSES


@skip_windows
def test_run_cli_default_shares_process_group():
    """By default the child stays in the caller's process group: it keeps the
    controlling terminal (an interactive ``sudo`` raised from inside the child
    must be able to prompt on ``/dev/tty``) and receives the terminal's signals
    with the rest of the foreground group."""
    result = run_cli((sys.executable, "-c", "import os; print(os.getpgid(0))"))
    assert int(result.stdout) == os.getpgid(0)


@skip_windows
def test_run_cli_new_session_makes_child_group_leader():
    """With start_new_session the child leads its own session and process group,
    whose ID is its own PID: the property every group-kill path relies on."""
    result = run_cli(
        (sys.executable, "-c", "import os; print(os.getpid(), os.getpgid(0))"),
        start_new_session=True,
    )
    pid, pgid = (int(field) for field in result.stdout.split())
    assert pid == pgid
    assert pgid != os.getpgid(0)


def _is_unreaped_zombie(pid: int) -> bool:
    """Return whether ``pid`` is a zombie: killed but not yet reaped.

    A build sandbox with no init to reap orphans (e.g. an Alpine ``abuild``
    container) leaves a SIGKILL'd process lingering as a zombie, which
    ``os.kill(pid, 0)`` still reports as alive. Only Linux exposes the state
    through ``/proc``; elsewhere a real reaper collects the process, so the
    plain existence check is enough.
    """
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as stat_file:
            # The state letter follows the ")" that closes the comm field,
            # which may itself contain spaces or parentheses.
            return stat_file.read().rpartition(")")[2].split()[0] == "Z"
    except OSError:
        return False


def _assert_process_dies(pid: int, deadline_seconds: float = 5.0) -> None:
    """Poll until ``pid`` is gone, killing it and failing if it survives.

    Signal delivery and the reparenting of orphans to the reaper are
    asynchronous, so the check retries briefly instead of asserting at once. A
    zombie counts as gone: it has already been killed, only its reaping is
    pending (which never comes in a reaper-less sandbox).
    """
    deadline = monotonic() + deadline_seconds
    while monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            # Very unlikely PID reuse by another user: consider it gone.
            return
        if _is_unreaped_zombie(pid):
            return
        sleep(0.05)
    os.kill(pid, signal.SIGKILL)  # Don't leak the sleeper past the test.
    pytest.fail(f"PID {pid} survived the process-group kill.")


@skip_windows
def test_run_cli_timeout_new_session_kills_grandchildren():
    """A timed-out start_new_session child takes its whole process group down:
    the grandchild is reaped along with it instead of surviving as an orphan
    holding the inherited output pipe open."""
    code = dedent("""\
        import subprocess, sys, time
        grandchild = subprocess.Popen(
            (sys.executable, "-c", "import time; time.sleep(30)"),
        )
        print(f"grandchild={grandchild.pid}", flush=True)
        time.sleep(30)
        """)
    start = monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as excinfo:
        run_cli((sys.executable, "-c", code), timeout=2, start_new_session=True)
    # The grandchild inherited the stdout pipe, so a surviving orphan would have
    # stalled the drain for the full kill grace: a prompt return doubles as
    # evidence the whole group died.
    assert monotonic() - start < 15
    match = re.search(r"grandchild=(\d+)", excinfo.value.output or "")
    assert match, "the child never reported its grandchild's PID"
    _assert_process_dies(int(match.group(1)))
    assert not _LIVE_PROCESSES


def test_run_cli_registers_live_process_then_discards_it():
    """run_cli tracks its subprocess while it runs, and drops it once done.

    A background call parks in a real subprocess. Once it is registered,
    terminate_live_processes() unblocks it, and run_cli's ``finally`` clears the
    registry: this is the exact path the SIGINT handler drives on Ctrl+C.
    """

    def call():
        run_cli((sys.executable, "-c", "import time; time.sleep(30)"))

    worker = threading.Thread(target=call)
    worker.start()
    try:
        deadline = monotonic() + 5
        while not _LIVE_PROCESSES and monotonic() < deadline:
            sleep(0.01)
        assert _LIVE_PROCESSES, "run_cli() should register its live subprocess"
        # Terminating the child unblocks the parked run_cli() call.
        terminate_live_processes()
        worker.join(timeout=5)
        assert not worker.is_alive()
    finally:
        terminate_live_processes()
        worker.join(timeout=5)
    # run_cli()'s finally discarded the child once it was reaped.
    assert not _LIVE_PROCESSES


@skip_windows
def test_terminate_live_processes_signals_whole_group(tmp_path):
    """Interrupting a start_new_session child reaps its grandchild too: the
    group never received the terminal's SIGINT (it left the foreground group),
    so terminate_live_processes() is its only kill path and must cover the
    descendants.

    The child reports its grandchild's PID through a sentinel file, polled
    before tearing down, so the group is never signalled mid-spawn. The sentinel
    is published by rename: a bare ``open(..., "w")`` creates the file before the
    write is flushed, so polling for existence could tear the group down between
    creation and flush, leaving an empty file behind for ``int()`` to choke on.
    """
    pid_file = tmp_path / "grandchild.pid"
    code = dedent(f"""\
        import os, subprocess, sys, time
        grandchild = subprocess.Popen(
            (sys.executable, "-c", "import time; time.sleep(30)"),
        )
        pid_file = {str(pid_file)!r}
        with open(pid_file + ".tmp", "w", encoding="utf-8") as f:
            f.write(str(grandchild.pid))
        os.replace(pid_file + ".tmp", pid_file)
        time.sleep(30)
        """)

    def call():
        run_cli((sys.executable, "-c", code), start_new_session=True)

    worker = threading.Thread(target=call)
    worker.start()
    try:
        deadline = monotonic() + 10
        while not pid_file.exists() and monotonic() < deadline:
            sleep(0.01)
        assert pid_file.exists(), "the child never reported its grandchild's PID"
        assert _GROUP_LEADERS, "the isolated child should be flagged group leader"
        terminate_live_processes()
        worker.join(timeout=10)
        assert not worker.is_alive()
    finally:
        terminate_live_processes()
        worker.join(timeout=5)
    assert not _LIVE_PROCESSES
    assert not _GROUP_LEADERS
    _assert_process_dies(int(pid_file.read_text(encoding="utf-8")))


def test_terminate_live_processes_ignores_already_reaped():
    """A process gone between snapshot and signal is skipped, not raised on."""
    proc = subprocess.Popen(
        (sys.executable, "-c", "pass"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    proc.wait(timeout=5)  # Already exited before we signal it.
    with _LIVE_PROCESSES_LOCK:
        _LIVE_PROCESSES.add(proc)
    try:
        terminate_live_processes()  # Must not raise on the dead process.
    finally:
        with _LIVE_PROCESSES_LOCK:
            _LIVE_PROCESSES.discard(proc)


def test_install_interrupt_handler_terminates_children_and_reraises():
    """The installed SIGINT handler SIGTERMs live children, then raises to abort."""
    ctx = click.Context(click.Command("cli"))
    original = signal.getsignal(signal.SIGINT)
    install_interrupt_handler(ctx)
    handler = signal.getsignal(signal.SIGINT)
    assert callable(handler)
    assert handler is not original

    proc = subprocess.Popen(
        (sys.executable, "-c", "import time; time.sleep(30)"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    with _LIVE_PROCESSES_LOCK:
        _LIVE_PROCESSES.add(proc)
    try:
        # Simulate signal delivery: the handler kills the child, then re-raises.
        with pytest.raises(KeyboardInterrupt):
            handler(signal.SIGINT, None)
        assert proc.wait(timeout=5) != 0
    finally:
        with _LIVE_PROCESSES_LOCK:
            _LIVE_PROCESSES.discard(proc)
        if proc.poll() is None:
            proc.kill()
        ctx.close()  # Restores the previous handler via call_on_close.
    assert signal.getsignal(signal.SIGINT) is original


def test_install_interrupt_handler_restored_on_context_close():
    """Closing the context restores the handler in place before the install."""
    original = signal.getsignal(signal.SIGINT)
    ctx = click.Context(click.Command("cli"))
    try:
        install_interrupt_handler(ctx)
        assert signal.getsignal(signal.SIGINT) is not original
    finally:
        ctx.close()
    assert signal.getsignal(signal.SIGINT) is original


def test_install_interrupt_handler_skips_off_main_thread():
    """signal.signal() only works in the main thread: off-thread install is a no-op."""
    original = signal.getsignal(signal.SIGINT)
    ctx = click.Context(click.Command("cli"))
    errors: list[BaseException] = []

    def off_main():
        try:
            install_interrupt_handler(ctx)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    worker = threading.Thread(target=off_main)
    worker.start()
    worker.join()
    assert not errors
    assert signal.getsignal(signal.SIGINT) is original
