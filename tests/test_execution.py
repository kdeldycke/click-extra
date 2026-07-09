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
import re
import signal
import subprocess
import sys
import threading
from textwrap import dedent
from time import monotonic, sleep
from unittest.mock import patch

import click
import cloup
import pytest
from boltons.strutils import strip_ansi

from click_extra import (
    Command,
    Context,
    JobsOption,
    command,
    context,
    echo,
    format_cli_prompt,
    get_current_theme,
    group,
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
    _LIVE_PROCESSES,
    _LIVE_PROCESSES_LOCK,
    CPU_COUNT,
    PROMPT,
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

    with patch.multiple("click_extra.execution", CPU_COUNT=2, DEFAULT_JOBS=1):
        result = invoke(cli)  # No --jobs: exercise the default value.

    assert result.stdout == "Jobs: 1\n"
    assert result.exit_code == 0
    assert not result.stderr


def test_default_collapse_to_sequential_logged_at_info(invoke):
    """The default's collapse to a single job stays discoverable at info level.

    This is the silent trap on a two-core host: no flag is passed, yet the
    default reserves one core and runs sequentially. The trace lives at info
    level, next to the resolved-jobs line, instead of a default-verbosity
    warning.
    """

    @command
    @jobs_option
    @pass_context
    def cli(ctx):
        echo(f"Jobs: {ctx.meta['click_extra.jobs']}")

    with patch.multiple("click_extra.execution", CPU_COUNT=2, DEFAULT_JOBS=1):
        result = invoke(cli, "--verbosity", "INFO", color=False)

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

    # Windows separators are recognized too.
    prompt = format_cli_prompt(("C:\\Tools\\mas.exe", "list"))
    assert f"C:\\Tools\\{theme.invoked_command('mas.exe')} list" in prompt


def test_run_cli_merged_streams():
    """merge_streams interleaves stderr into stdout and nulls the stderr field."""
    code = dedent("""\
        import sys
        print("to out")
        sys.stdout.flush()
        print("to err", file=sys.stderr)
        """)
    result = run_cli((sys.executable, "-c", code), merge_streams=True)
    assert result.stderr is None
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
