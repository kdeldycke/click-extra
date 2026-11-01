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
"""Tests for the --jobs option and the run_jobs and run_lanes fan-out primitives."""

from __future__ import annotations

import _thread
import threading
from concurrent.futures import Future
from time import monotonic, sleep
from unittest.mock import patch

import click
import cloup
import pytest

from click_extra import (
    Command,
    Context,
    JobsOption,
    command,
    context,
    echo,
    jobs_option,
    pass_context,
    resolve_jobs,
    run_jobs,
    run_lanes,
)
from click_extra.jobs import (
    _WORKER_WINDOW_FACTOR,
    CPU_COUNT,
    DEFAULT_JOBS,
    _default_jobs,
    _logical_cpu_count,
    _wait_result,
)
from click_extra.logging import LogLevel


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
        "click_extra.jobs",
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

    with patch("click_extra.jobs.CPU_COUNT", 4):
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

    with patch.multiple("click_extra.jobs", CPU_COUNT=1, DEFAULT_JOBS=1):
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

    with patch.multiple("click_extra.jobs", CPU_COUNT=1, DEFAULT_JOBS=1):
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

    with patch.multiple("click_extra.jobs", CPU_COUNT=8, DEFAULT_JOBS=7):
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
    an event that stays unset for the run. A plain ``with``-block teardown would
    ``shutdown(wait=True)`` and hang on that parked task; the run drops queued
    work and returns at once.
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


@pytest.mark.parametrize(
    "run",
    (
        pytest.param(lambda work: run_jobs(work, [0], jobs=4), id="run_jobs"),
        pytest.param(lambda work: run_lanes(work, ([0, 1],), jobs=4), id="run_lanes"),
    ),
)
def test_lone_item_or_lane_runs_in_the_calling_thread(run):
    """With nothing to overlap, the work runs in the calling thread, whatever the
    worker count."""
    threads = list(run(lambda n: threading.current_thread()))
    assert threads
    assert all(thread is threading.current_thread() for thread in threads)


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


def test_run_lanes_interrupt_stops_each_lane_after_its_current_item():
    """An interrupt lets each running lane finish its current item, then stop."""
    started = threading.Event()
    release = threading.Event()
    ran: list[int] = []
    lock = threading.Lock()

    def work(n):
        with lock:
            ran.append(n)
        if n == 0:
            started.wait(timeout=5)
            raise KeyboardInterrupt
        if n == 1:
            started.set()
            release.wait(timeout=5)
        return n

    with pytest.raises(KeyboardInterrupt):
        list(run_lanes(work, ([0], [1, 2, 3]), jobs=2))
    release.set()
    # Leaves the lane worker time to run on, which it must not.
    sleep(0.3)
    assert sorted(ran) == [0, 1]


@pytest.mark.parametrize(
    "run",
    (
        pytest.param(lambda work: run_jobs(work, [0, 1], jobs=2), id="run_jobs"),
        pytest.param(lambda work: run_lanes(work, ([0], [1]), jobs=2), id="run_lanes"),
    ),
)
def test_interrupt_tripped_as_the_wait_began_is_handled_promptly(run):
    """A Ctrl+C the interpreter noted as the main thread blocked on a task is
    handled within the poll period, not when the task ends.

    `interrupt_main()` leaves the interrupt pending without waking the main
    thread: the state a `SIGINT` leaves when it lands after the interpreter last
    checked for one and before the thread blocked in the C library. An unbounded
    wait on the task would run the handler only when the task returns.
    """
    release = threading.Event()

    def work(n):
        if n == 0:
            # Leaves the main thread time to block on this task's result.
            sleep(0.3)
            _thread.interrupt_main()
        release.wait(timeout=5)
        return n

    start = monotonic()
    try:
        with pytest.raises(KeyboardInterrupt):
            list(run(work))
        assert monotonic() - start < 2
    finally:
        release.set()


@pytest.mark.parametrize(
    ("context", "expected"),
    (
        pytest.param(KeyboardInterrupt(), KeyboardInterrupt, id="interrupted"),
        pytest.param(None, RuntimeError, id="unrelated"),
    ),
)
def test_wait_result_raises_the_interrupt_a_lock_error_replaced(
    monkeypatch, context, expected
):
    """A `RuntimeError` the wait raises in place of a Ctrl+C becomes the Ctrl+C again.

    A free-threaded CPython can raise the interrupt between the wait and the lock it
    takes back, then fail to release it, as python/cpython#118433 reports. Any other
    `RuntimeError` of the wait stays as it is.
    """

    def failing_wait(*args, **kwargs):
        error = RuntimeError("release unlocked lock")
        error.__context__ = context
        raise error

    monkeypatch.setattr("concurrent.futures.wait", failing_wait)
    with pytest.raises(expected):
        _wait_result(Future())


def test_run_jobs_reports_a_task_timeout_error():
    """A task raising `TimeoutError` ends the run on it, within the poll period.

    `concurrent.futures.TimeoutError` is the builtin `TimeoutError` from Python
    3.11 on, which a task raises itself when a socket times out: a wait reading
    the result with a timeout of its own could not tell the two apart.
    """

    def work(n):
        if n == 0:
            raise TimeoutError("oven door left open")
        return n

    start = monotonic()
    with pytest.raises(TimeoutError, match="oven door left open"):
        list(run_jobs(work, [0, 1], jobs=2))
    assert monotonic() - start < 2


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

    with patch("click_extra.jobs.CPU_COUNT", 4):
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

    with patch("click_extra.jobs.CPU_COUNT", 8):
        result = invoke(cli, "--jobs", "4")

    assert result.stdout == "Jobs: 4\n"
    assert result.exit_code == 0
    assert not result.stderr


@pytest.mark.parametrize(
    ("cpu_count", "expected"),
    (
        # An undetermined count runs sequentially.
        (None, 1),
        (1, 1),
        # Reserving one of two logical CPUs would collapse the pool to a single
        # (sequential) worker, and threads waiting on subprocesses and I/O cost
        # nothing there, so the whole machine is used instead.
        (2, 2),
        (3, 2),
        (4, 3),
        (16, 15),
    ),
)
def test_default_jobs(cpu_count, expected):
    """The default reserves one logical CPU, from three CPUs up."""
    assert _default_jobs(cpu_count) == expected


def test_default_jobs_of_this_host():
    """The published default follows the rule for the CPUs of this host."""
    assert _default_jobs(CPU_COUNT) == DEFAULT_JOBS


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
    with patch("click_extra.jobs.os") as mock_os:
        del mock_os.process_cpu_count  # Simulate a Python older than 3.13.
        mock_os.cpu_count.return_value = 8
        assert _logical_cpu_count() == 8
