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
"""Options and primitives controlling how CLIs run.

Two altitudes live here. The higher one governs the CLI *being authored*: the
pre-configured {class}`~click_extra.parameters.ExtraOption` subclasses
({class}`JobsOption`, {class}`TimerOption`, {class}`ZeroExitOption`) publish
their resolved value on `ctx.meta`, and the fan-out primitives
({func}`run_jobs`, {func}`run_lanes`) parallelize work per the resolved
`--jobs` count.

The lower one runs *foreign* CLIs in subprocesses, for tools that wrap other
programs: {func}`run_cli` spawns one command, disclosing its invocation to the
logger and streaming its output live, while {func}`install_interrupt_handler`
and {func}`terminate_live_processes` make Ctrl+C abort in-flight children
cleanly. {func}`args_cleanup` and {func}`format_cli_prompt` are the shared
serialization and disclosure atoms both altitudes (and
{mod}`click_extra.testing`) build upon.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from gettext import gettext as _
from time import perf_counter
from typing import Final, TypeVar, cast

import click
from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from click import echo
from click.core import ParameterSource
from click.shell_completion import CompletionItem
from extra_platforms import is_windows

from . import context
from .envvar import env_copy
from .parameters import ExtraOption
from .theme import get_current_theme

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from pathlib import Path
    from types import FrameType
    from typing import IO, Any

    from .envvar import TEnvVars

    TArg = str | Path | None
    TNestedArgs = Iterable[TArg | Iterable["TNestedArgs"]]
    """Type for arbitrary nested CLI arguments.

    Arguments can be `str`, :py:class:`pathlib.Path` objects or `None` values.
    """

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")

CPU_COUNT = os.cpu_count()
"""Number of **logical** CPUs available, or `None` if undetermined.

This is {func}`os.cpu_count`, which counts *logical* processors (hardware
threads). On a CPU with simultaneous multi-threading (Intel Hyper-Threading,
AMD SMT) a 4-physical-core chip reports `8`. It is therefore **not** a count
of *physical* cores, and is usually larger than what physical-core tools
report, such as `psutil.cpu_count(logical=False)` or pytest-xdist's
`-n auto` (which counts physical cores). Parallelism here is keyed on the
logical count on purpose: subprocess- and I/O-bound work overlaps well across
hardware threads.
"""

DEFAULT_JOBS = max(1, CPU_COUNT - 1) if CPU_COUNT else 1
"""Default number of parallel jobs: one fewer than {data}`CPU_COUNT` (logical CPUs).

Leaves one logical CPU free for the main process and system tasks. Falls back
to `1` (sequential) when the count cannot be determined.

```{caution}
This resolves to `1` not only on single-core hosts but also on **two-core
hosts**, since it reserves one core. There, the default silently runs
sequentially. {meth}`JobCount.convert` logs whenever a parallel-intent
keyword collapses to a single job this way: as a warning for an explicit
request, at info level for the option's own default.
```
"""


class JobCount(click.ParamType):
    """Parse a `--jobs` value: an integer or the `auto`/`max` keyword.

    Resolves the symbolic keywords against the host's logical CPU count
    ({data}`CPU_COUNT`), counting hardware threads, not physical cores:

    - `auto` resolves to {data}`DEFAULT_JOBS` (one fewer than the available
      logical CPUs), the same heuristic used as the option's default.
    - `max` resolves to {data}`CPU_COUNT` (every available logical CPU).

    Any other token is parsed as an integer and left to
    {meth}`JobsOption.validate_jobs` for clamping and range-checking. Resolving
    the keywords here keeps the value handed downstream a plain {class}`int`,
    so consumers never have to know about the keywords.
    """

    name = "jobs"

    #: Symbolic keywords accepted besides an integer count, in render order.
    #:
    #: Exposed as `choices` so the help colorizer highlights them like
    #: `click.Choice` values: the keyword collector duck-types on this
    #: attribute (see the `getattr(param.type, "choices", ...)` branch in
    #: `_HelpColorsMixin._collect_params`). It is
    #: also the single source of truth reused by {meth}`get_metavar` and
    #: {meth}`convert`, so the metavar and the parser never drift apart.
    choices = ("auto", "max")

    def get_metavar(self, param, ctx=None):
        """Render `[auto|max|INTEGER]` (brackets included, as `Choice` does)."""
        return f"[{'|'.join(self.choices)}|INTEGER]"

    def convert(
        self,
        value: Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> int:
        """Resolve a keyword to a logical-core count, else parse as an integer.

        An already-resolved integer is returned untouched, so option defaults
        and re-validation can flow back through conversion unharmed. When a
        parallel-intent keyword (`auto`/`max`) resolves to a single job,
        the collapse is logged: the request reads as "use several cores", but
        the host has too few logical CPUs, so execution is silently sequential.
        An explicit request (command line, environment variable, config file)
        logs a warning; the option's own default only logs at info level, else
        every bare invocation on a 1-CPU host would emit a warning the user
        never asked for, polluting captured runner streams and the CLI output
        rendered in Sphinx docs.
        """
        if isinstance(value, int):
            return value

        normalized = str(value).strip().lower()
        if normalized in self.choices:
            resolved = DEFAULT_JOBS if normalized == "auto" else (CPU_COUNT or 1)
            # A parallel-intent keyword that collapses to a single job runs
            # sequentially: surface it so it is not mistaken for parallel
            # execution. See the docstring for the warning-vs-info split.
            if resolved <= 1 and not (ctx is not None and ctx.resilient_parsing):
                if CPU_COUNT is None:
                    cpu_desc = "the number of logical CPUs could not be determined"
                elif CPU_COUNT == 1:
                    cpu_desc = "only 1 logical CPU is available"
                else:
                    cpu_desc = f"only {CPU_COUNT} logical CPUs are available"
                implicit_default = (
                    ctx is not None
                    and param is not None
                    and param.name is not None
                    and ctx.get_parameter_source(param.name) is ParameterSource.DEFAULT
                )
                log = logger.info if implicit_default else logger.warning
                log(
                    "'--jobs %s' resolved to a single job: %s, so execution "
                    "will be sequential, not parallel.",
                    normalized,
                    cpu_desc,
                )
            return resolved

        try:
            return int(normalized)
        except ValueError:
            self.fail(
                f"{value!r} is not a valid job count: use an integer, 'auto' or 'max'.",
                param,
                ctx,
            )

    def shell_complete(
        self,
        ctx: click.Context,
        param: click.Parameter,
        incomplete: str,
    ) -> list[CompletionItem]:
        """Suggest the `auto`/`max` keywords; an integer count is free-form.

        Completion proposes only the symbolic keywords, matched
        case-insensitively to mirror how {meth}`convert` lower-cases its input.
        An integer has no finite set to enumerate, so none is offered, yet
        {meth}`convert` still accepts one.
        """
        prefix = incomplete.lower()
        return [
            CompletionItem(keyword)
            for keyword in self.choices
            if keyword.startswith(prefix)
        ]


class JobsOption(ExtraOption):
    """A pre-configured `--jobs` option to control parallel execution.

    Accepts an integer or one of two keywords resolved by
    {class}`~click_extra.execution.JobCount`: `auto` (the default: one fewer
    than the available logical CPU cores, leaving a core free for the main
    process and system tasks) and `max` (every available logical CPU core). A
    value of `0` disables parallelism and runs sequentially.

    The core count is the number of *logical* CPUs (hardware threads) reported
    by {func}`os.cpu_count`, not physical cores: see
    {data}`~click_extra.execution.CPU_COUNT`. On a host with too few logical
    CPUs, `auto`/`max` resolve to a single job and
    {class}`~click_extra.execution.JobCount` logs that execution will be
    sequential: as a warning when the keyword was requested explicitly, at info
    level when it came from the option's own default.

    The resolved value is stored as an {class}`int` in
    `ctx.meta[click_extra.context.JOBS]`.

    ```{warning}
    `JobsOption` only resolves and publishes the job count: it does not
    drive any concurrency by itself. Pass it to {func}`run_jobs` (which
    reads the resolved `ctx.meta[click_extra.context.JOBS]` count), or
    read that value yourself and act on it.
    ```
    """

    def validate_jobs(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: int,
    ) -> None:
        """Validate the resolved job count and store it in context metadata.

        {class}`~click_extra.execution.JobCount` has already resolved any
        `auto`/`max` keyword to an integer by the time this runs. A value of
        `0` disables parallelism: it is rounded up to `1` (sequential
        execution) with a warning. Negative values are likewise clamped to
        `1`, and a count above the available cores is honored but warned
        about. The resolved count is then logged at info level next to the
        host's logical CPU count ({data}`~click_extra.execution.CPU_COUNT`), so a
        CLI's parallelism is visible under `--verbosity INFO`.
        """
        if ctx.resilient_parsing:
            return

        effective = value

        if value == 0:
            effective = 1
            logger.warning(
                "Requested 0 jobs: parallelism disabled, running sequentially.",
            )
        elif value < 0:
            effective = 1
            logger.warning(
                "Requested %d jobs, clamping to minimum of 1.",
                value,
            )
        elif CPU_COUNT and value > CPU_COUNT:
            logger.warning(
                "Requested %d jobs exceeds available CPU cores (%d).",
                value,
                CPU_COUNT,
            )

        context.set(ctx, context.JOBS, effective)

        # Surface the resolved worker count so any CLI using --jobs can show its
        # parallelism (and how it maps to the logical CPU count) under -v/INFO.
        logger.info(
            "Resolved --jobs to %d (os.cpu_count()=%s logical CPUs).",
            effective,
            CPU_COUNT if CPU_COUNT is not None else "unknown",
        )

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default="auto",
        expose_value=False,
        show_default=True,
        type=JobCount(),
        help=_(
            "Number of parallel jobs. Accepts an integer, 'auto' (one fewer "
            "than the host's logical CPUs) or 'max' (all logical CPUs). 0 runs "
            "sequentially."
        ),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--jobs",)

        kwargs.setdefault("callback", self.validate_jobs)

        super().__init__(
            param_decls=param_decls,
            default=default,
            expose_value=expose_value,
            show_default=show_default,
            type=type,
            help=help,
            **kwargs,
        )


def resolve_jobs(
    ctx: click.Context | None,
    count: int,
    *,
    serial_at_debug: bool = False,
) -> int:
    """Resolve how many worker threads to use for a batch of `count` items.

    Returns the number of items to process in parallel; `1` means run
    sequentially in the calling thread. This is the policy shared by
    {func}`run_jobs` and {func}`run_lanes`, exposed on its own for callers that
    must know the resolved count *before* they fan out (for example to pick a
    progress-rendering mode). It collapses to sequential when:

    - there is no active CLI context (programmatic or test use),
    - a single item leaves nothing to parallelize, or
    - the resolved {class}`JobsOption` count
      (`ctx.meta[click_extra.context.JOBS]`) is `1` or less.

    Otherwise that count wins, capped at `count`: there is no point spinning up
    more workers than there are items.

    :param ctx: the active Click context, read for the resolved `--jobs` count
        (and, with `serial_at_debug`, the verbosity). `None` forces sequential.
    :param count: how many items are about to be scheduled.
    :param serial_at_debug: when set, also collapse to sequential at `DEBUG`
        verbosity, where coherent per-worker log narration matters more than the
        speed-up (interleaved threads would scramble it). Off by default.
    """
    if count <= 1 or ctx is None:
        return 1
    # Compared against the stdlib level rather than click_extra.logging.LogLevel
    # (which mirrors it) to keep this module free of a logging-module import cycle.
    if serial_at_debug and context.get(ctx, context.VERBOSITY_LEVEL) == logging.DEBUG:
        return 1
    jobs = context.get(ctx, context.JOBS, 1)
    return min(jobs, count) if jobs > 1 else 1


@contextmanager
def _interruptible_pool(max_workers: int) -> Iterator[ThreadPoolExecutor]:
    """Yield a thread pool whose teardown honors a prompt interrupt.

    Wraps a {class}`~concurrent.futures.ThreadPoolExecutor` for a `with` body
    that submits and drains work. On a normal exit, or when a task raises, the
    pool shuts down with `wait=True`, keeping the drain-then-propagate
    semantics of a plain `with ThreadPoolExecutor(...)` block. But on a prompt
    abort (a {class}`KeyboardInterrupt` from Ctrl+C, or a {class}`GeneratorExit`
    from a caller closing the generator early) it shuts down with
    `wait=False, cancel_futures=True`: queued items are dropped and control
    returns at once, without blocking on the tasks already in flight.

    A running thread cannot be cancelled, so those in-flight tasks keep going
    until they return; a caller that needs them to stop sooner (killing a
    subprocess, say) must arrange that itself. This is why a plain `with` block
    is not used: its `shutdown(wait=True)` teardown would block until every
    in-flight task finished, defeating the interrupt.

    Shared by {func}`run_jobs` and {func}`run_lanes`, the two parallel drivers.
    """
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        yield executor
    except (KeyboardInterrupt, GeneratorExit):
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    except BaseException:
        # A task raised: keep the drain-then-propagate semantics of `with`.
        executor.shutdown(wait=True)
        raise
    else:
        executor.shutdown(wait=True)


def run_jobs(
    func: Callable[[T], R],
    items: Iterable[T],
    *,
    jobs: int | None = None,
    serial_at_debug: bool = False,
) -> Iterator[R]:
    """Run `func` over `items`, parallelized per the resolved `--jobs` count.

    The worker count is taken from `jobs` when given, else resolved from the
    active command's {class}`JobsOption` value by {func}`resolve_jobs`, else `1`.
    With a single worker (or at most one item) the items run **sequentially and
    lazily**, so a caller can stop early on the first result (for example to abort
    on the first failure); otherwise they run in a thread pool. Either way results
    are yielded in submission order, like {func}`map`.

    This is the single-task-per-item special case of {func}`run_lanes` (every item
    is its own lane). Reach for {func}`run_lanes` when some items must run serially
    relative to one another while others run concurrently.

    The pool is thread-based, which suits the I/O- and subprocess-bound work CLI
    tools usually parallelize (each child releases the GIL). The count is a
    number of logical CPUs: see {data}`~click_extra.execution.CPU_COUNT`.

    :param func: Called once per item; its return value is yielded.
    :param items: The work items. Materialized up front to size the pool.
    :param jobs: Override the worker count instead of reading it from the
        context. `1` or fewer forces sequential execution.
    :param serial_at_debug: forwarded to {func}`resolve_jobs` when `jobs` is not
        given: collapse to sequential at `DEBUG` verbosity.
    :return: An iterator over `func`'s results, in the order of `items`.
    """
    work = list(items)
    if jobs is None:
        ctx = click.get_current_context(silent=True)
        jobs = resolve_jobs(ctx, len(work), serial_at_debug=serial_at_debug)

    if jobs <= 1 or len(work) <= 1:
        # Sequential and lazy: the caller can break early (for example on the
        # first failure) and the remaining items never run.
        for item in work:
            yield func(item)
    else:
        # Parallel: every item is submitted up front and results are yielded in
        # submission order. The pool teardown drops queued work on a prompt
        # interrupt instead of blocking on it (see {func}`_interruptible_pool`).
        with _interruptible_pool(min(jobs, len(work))) as executor:
            yield from executor.map(func, work)


def run_lanes(
    func: Callable[[T], R],
    lanes: Iterable[Iterable[T]],
    *,
    jobs: int | None = None,
    serial_at_debug: bool = False,
) -> Iterator[R]:
    """Run `func` over grouped items: serial within a lane, concurrent across.

    Each *lane* is an iterable of items. `func` is mapped over every item, but a
    lane's own items run **serially and in order** on a single worker, while distinct
    lanes run **concurrently** up to the resolved `--jobs` count. This is the right
    primitive when some work must be serialized relative to itself (a shared lock, a
    rate limit, one mailbox file, one package-manager backend) yet still overlap with
    unrelated work.

    {func}`run_jobs` is the degenerate case where every lane holds a single item.
    Concurrency is sized by the *number of lanes* (one worker per lane), since a
    lane never splits across workers.

    Results are yielded in lane-submission order, a lane's items in order, like
    {func}`map`. With a single worker the run stays lazy (the caller can break
    early); otherwise every lane is submitted up front. A lane runs entirely on one
    worker, so a stateful resource bound to the lane (a per-lane cache, a connection)
    is touched by only that one thread and needs no lock.

    :param func: Called once per item; its return value is yielded.
    :param lanes: The lanes, each an iterable of items. Materialized up front.
    :param jobs: Override the worker count instead of reading it from the context.
        `1` or fewer forces fully sequential execution.
    :param serial_at_debug: forwarded to {func}`resolve_jobs` when `jobs` is not
        given: collapse to sequential at `DEBUG` verbosity.
    :return: An iterator over `func`'s results, lane by lane in submission order.
    """
    lane_list = [list(lane) for lane in lanes]
    if not lane_list:
        return
    if jobs is None:
        ctx = click.get_current_context(silent=True)
        jobs = resolve_jobs(ctx, len(lane_list), serial_at_debug=serial_at_debug)
    elif jobs > 1:
        jobs = min(jobs, len(lane_list))

    if jobs <= 1:
        # Sequential and lazy across every lane and item: the caller can break early.
        for lane in lane_list:
            for item in lane:
                yield func(item)
    else:
        # Each lane is a serial chain run on one worker; chains run concurrently and
        # their results are yielded in submission order.
        def run_chain(lane: list[T]) -> list[R]:
            return [func(item) for item in lane]

        # The pool teardown drops queued lanes on a prompt interrupt instead of
        # blocking on the in-flight ones (see {func}`_interruptible_pool`).
        with _interruptible_pool(jobs) as executor:
            for chain_results in executor.map(run_chain, lane_list):
                yield from chain_results


class TimerOption(ExtraOption):
    """A pre-configured option that is adding a `--time`/`--no-time` flag to print
    elapsed time at the end of CLI execution.

    The start time is made available in the context in
    `ctx.meta[click_extra.context.START_TIME]`.
    """

    def print_timer(self) -> None:
        """Compute and print elapsed execution time.

        Always prints, even when a sibling eager option (`--version`,
        `--params`, `--show-config`…) short-circuited the command
        body via `ctx.exit()`. That makes `--time` a usable probe for
        the cost of Click Extra's own machinery (option parsing, config
        loading, eager callbacks), not just user command bodies.
        """
        echo(f"Execution time: {perf_counter() - self.start_time:0.3f} seconds.")

    def init_timer(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Set up the execution-timer machinery for the current invocation.

        Captures {func}`time.perf_counter` as the start time, stores it on
        `ctx.meta` under {data}`click_extra.context.START_TIME`, and queues
        :py:meth:`print_timer` as a context-close callback so the elapsed
        duration is printed even when a sibling eager option (`--version`,
        `--params`…) short-circuits the command body.

        Renamed from `register_timer_on_close` to align with the
        `init_<system>` convention shared with
        {class}`~click_extra.table.TableFormatOption.init_formatter` and
        {class}`~click_extra.table.SortByOption.init_sort`.
        """
        if not value or ctx.resilient_parsing:
            return

        # Only capture the start time when the user requested timing.
        self.start_time = perf_counter()
        context.set(ctx, context.START_TIME, self.start_time)

        # Register printing at the end of execution.
        ctx.call_on_close(self.print_timer)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default=False,
        expose_value=False,
        is_eager=True,
        help=_("Measure and print elapsed execution time."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--time/--no-time",)

        kwargs.setdefault("callback", self.init_timer)

        super().__init__(
            param_decls=param_decls,
            default=default,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )


class ZeroExitOption(ExtraOption):
    """A pre-configured `-0`/`--zero-exit` option flag.

    Follows the convention popularized by linters and static analysers, which
    exit with a non-zero code whenever they report findings so that automation
    can gate on it. Setting this flag flips that behavior: the CLI returns `0`
    as long as it ran to completion, reserving non-zero codes for actual
    execution failures.

    The resolved value is stored in
    {data}`ctx.meta[click_extra.context.ZERO_EXIT] <click_extra.context.ZERO_EXIT>`,
    aligning with every other Click Extra option's per-invocation context-meta
    storage pattern.

    ```{warning}
    This option is a placeholder: it does not alter the CLI's exit code by
    itself. Downstream code must read
    {data}`ctx.meta[click_extra.context.ZERO_EXIT] <click_extra.context.ZERO_EXIT>`
    and act on it.
    ```
    """

    def set_zero_exit(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Store the resolved zero-exit flag on the context's `meta` dict.

        Read via {func}`click_extra.context.get(ctx, click_extra.context.ZERO_EXIT)
        <click_extra.context.get>`.
        """
        context.set(ctx, context.ZERO_EXIT, value)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default=False,
        expose_value=False,
        is_flag=True,
        help=_("Always exit with a status code of 0, even when problems are found."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("-0", "--zero-exit")

        kwargs.setdefault("callback", self.set_zero_exit)

        super().__init__(
            param_decls=param_decls,
            default=default,
            expose_value=expose_value,
            is_flag=is_flag,
            help=help,
            **kwargs,
        )


# Subprocess execution.
#
# Everything below runs *foreign* CLIs in subprocesses, for tools that wrap other
# programs (package managers, mail utilities, binaries under test). run_cli() is the
# spawn/stream/timeout engine; args_cleanup() and format_cli_prompt() serialize and
# disclose an invocation; the live-process registry and install_interrupt_handler()
# make Ctrl+C abort in-flight children instead of hanging a concurrent fan-out.


PROMPT = (">" if is_windows() else "$") + " "
"""Prompt used to simulate the CLI execution.

```{hint}
Use ASCII characters to avoid issues with Windows terminals.
```
"""


INDENT = " " * len(PROMPT)
"""Constants for rendering of CLI execution."""


def args_cleanup(*args: TArg | TNestedArgs) -> tuple[str, ...]:
    """Flatten recursive iterables, remove all `None`, and cast each element to
    strings.

    Helps serialize :py:class:`pathlib.Path` and other objects.

    It also allows for nested iterables and `None` values as CLI arguments for
    convenience. We just need to flatten and filters them out.
    """
    return tuple(str(arg) for arg in flatten(args) if arg is not None)


def highlight_bin_name(program: str) -> str:
    """Style the binary's own name inside `program`, leaving its directory plain.

    `/opt/homebrew/bin/mas` renders with only `mas` in the active theme's
    `invoked_command` style, so the part of the path the eye scans for stands
    out from the noise of its location. A bare name (no separator) is styled
    whole. Both POSIX and Windows separators are recognized, whichever comes
    last.
    """
    split_at = max(program.rfind("/"), program.rfind("\\")) + 1
    return program[:split_at] + get_current_theme().invoked_command(
        program[split_at:],
    )


def format_cli_prompt(
    cmd_args: Iterable[str],
    extra_env: TEnvVars | None = None,
) -> str:
    """Render the shell prompt simulating a CLI invocation, for logs and dry-runs.

    Prefixes {data}`~click_extra.execution.PROMPT` to any `extra_env` assignments
    and the command line. Each token family is styled with the theme slot
    ({func}`~click_extra.theme.get_current_theme`) it holds elsewhere in a CLI's
    output, so the line reads like the help screens do:

    - the prompt sigil with `bracket`, the structural-token style;
    - each environment assignment as `envvar` name, plain `=`, `default`
      value;
    - the program's binary name with `invoked_command`, its directory plain
      (see {func}`highlight_bin_name`);
    - the `-`/`--` flags with `option`; other arguments stay plain.

    Useful to print a copy-pasteable command trace in debug logs, dry-runs and
    test output.
    """
    active_theme = get_current_theme()
    extra_env_string = ""
    if extra_env:
        extra_env_string = "".join(
            f"{active_theme.envvar(name)}={active_theme.default(str(value))} "
            for name, value in extra_env.items()
        )

    cmd_parts = tuple(cmd_args)
    styled_parts = []
    if cmd_parts:
        styled_parts.append(highlight_bin_name(cmd_parts[0]))
        for part in cmd_parts[1:]:
            styled_parts.append(
                active_theme.option(part) if part.startswith("-") else part,
            )

    sigil, _, spacing = PROMPT.partition(" ")
    return (
        active_theme.bracket(sigil)
        + f" {spacing}"
        + extra_env_string
        + " ".join(styled_parts)
    )


_LIVE_PROCESSES: Final[set[subprocess.Popen[str]]] = set()
"""Registry of the subprocesses currently running through {func}`run_cli`.

Populated by {func}`run_cli` for the lifetime of each child (added right after
spawn, discarded in its `finally`). Read by {func}`terminate_live_processes` to
interrupt them all at once. Guarded by {data}`_LIVE_PROCESSES_LOCK`, since a
concurrent fan-out ({func}`run_jobs`, {func}`run_lanes`) calls {func}`run_cli`
from several worker threads at once.
"""


_LIVE_PROCESSES_LOCK: Final = threading.Lock()
"""Guards {data}`_LIVE_PROCESSES` and {data}`_GROUP_LEADERS` against concurrent
mutation by worker threads."""


_GROUP_LEADERS: Final[set[subprocess.Popen[str]]] = set()
"""Subset of {data}`_LIVE_PROCESSES` spawned with `start_new_session`.

Each of these children leads its own POSIX session and process group, so the
kill paths signal the whole group (reaping its descendants along with it)
instead of the direct child alone. Maintained by {func}`run_cli` in lockstep
with {data}`_LIVE_PROCESSES`, under the same lock.
"""


def _kill_posix_process_group(
    process: subprocess.Popen[str],
    signum: signal.Signals,
) -> bool:
    """Signal the whole POSIX process group led by `process`.

    Only meaningful for a child spawned with `start_new_session`, whose group
    ID equals its PID. Returns `True` when the signal was delivered to the
    group, `False` when it could not be (no `killpg` on this platform, or
    the group is already gone), leaving the caller to fall back on signalling
    the direct child.
    """
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return False
    try:
        # A start_new_session child is its own session and group leader, so its
        # PID doubles as the group ID: no getpgid() lookup (which could race
        # with the reaping of the child) is needed.
        killpg(process.pid, signum)
    except OSError:
        # The whole group is already gone: nothing left to signal.
        return False
    return True


def terminate_live_processes() -> None:
    """Send `SIGTERM` to every subprocess currently running through {func}`run_cli`.

    Called from the main thread's `SIGINT` handler (see
    {func}`install_interrupt_handler`) so a concurrent fan-out aborts promptly:
    terminating the children unblocks the worker threads parked in
    {func}`run_cli`, letting the thread pool drain instead of hanging on a child
    that ignored the terminal's process-group `SIGINT`.

    A child spawned with `start_new_session` never receives the terminal's
    `SIGINT` at all (it left the foreground process group), so its whole group
    is signalled here, descendants included.

    Uses `SIGTERM` rather than `SIGKILL` so a child still gets to clean up,
    notably to restore terminal state a `sudo` password prompt may have altered.
    The registry is snapshotted under the lock, then signalled outside it, because
    {func}`run_cli` may be discarding its own entries from other threads at the
    same time.
    """
    with _LIVE_PROCESSES_LOCK:
        live = tuple(_LIVE_PROCESSES)
        leaders = set(_GROUP_LEADERS)
    for process in live:
        if process in leaders and _kill_posix_process_group(
            process,
            signal.SIGTERM,
        ):
            continue
        try:
            process.terminate()
        except OSError:
            # Reaped between the snapshot and the signal: nothing left to stop.
            pass


def install_interrupt_handler(ctx: click.Context) -> None:
    """Make the first Ctrl+C terminate in-flight subprocesses, then abort as usual.

    Installs a `SIGINT` handler for the duration of the CLI run that calls
    {func}`terminate_live_processes` before re-raising {class}`KeyboardInterrupt`
    (exactly what Python's default handler raises). The abort then proceeds
    normally, but a concurrent fan-out no longer hangs on surviving children. The
    previous handler is restored when `ctx` closes.

    Must run in the main thread: {func}`signal.signal` refuses to install a handler
    from any other, so a non-main-thread caller (embedded use, some tests) is a
    no-op that keeps the default Ctrl+C behavior.

    A signal handler is required here rather than a `try`/``except
    KeyboardInterrupt`` around the fan-out: Python delivers Ctrl+C only to the main
    thread, so worker threads never see the interrupt, and the exception unwinds
    through the executor's blocking `shutdown(wait=True)` teardown *before* any
    `except` in the caller could run. The children must be killed at
    signal-delivery time, ahead of that teardown.
    """
    if threading.current_thread() is not threading.main_thread():
        return

    def handler(signum: int, frame: FrameType | None) -> None:
        terminate_live_processes()
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGINT, handler)
    ctx.call_on_close(lambda: signal.signal(signal.SIGINT, previous))


_KILL_DRAIN_GRACE: Final = 3.0
"""Seconds {func}`run_cli` waits for its stream readers after killing the child.

Once the child is killed its pipes normally hit `EOF` at once, so the readers
finish within milliseconds. The exception is an orphaned grandchild holding an
inherited pipe handle open: the grace period bounds the wait instead of blocking
forever, and the daemon reader threads are then abandoned with whatever output
they collected. A `start_new_session` child never leaves such orphans behind
(its whole group is killed), so its drain always completes promptly.
"""


def _kill_windows_process_tree(pid: int) -> None:
    """Forcibly terminate `pid` and its whole process tree. No-op off Windows.

    Grandchild processes (installer EXEs spawned by a package manager's COM
    server, say) inherit the pipe write handles and keep them open past a plain
    `kill()` of the direct child, which would leave the output drain blocked
    until every grandchild exits. `taskkill /F /T` kills the entire tree,
    closing all inherited handles so the readers hit `EOF` promptly.
    """
    if not is_windows():
        return
    subprocess.run(
        ("taskkill", "/F", "/T", "/PID", str(pid)),
        capture_output=True,
        timeout=10,
        check=False,
    )


def _pump_stream(
    pipe: IO[str],
    sink: list[str],
    log: logging.Logger,
    level: int,
    label: str | None,
) -> None:
    """Reader-thread body: accumulate `pipe`'s lines and forward each to `log`.

    Each line is appended raw to `sink` (so the caller reassembles the exact
    capture `communicate()` would have produced), then echoed to the logger
    stripped of ANSI codes and trailing whitespace. Blank lines are accumulated
    but not logged. The loop ends at `EOF`, when every writer of the pipe has
    closed it.

    `label` rides each record as its `label` attribute, which
    {class}`click_extra.logging.Formatter` renders glued to the level name
    (`debug:mas: ...`) rather than polluting the message text itself.
    """
    extra = {"label": label} if label else None
    for line in pipe:
        sink.append(line)
        text = strip_ansi(line).rstrip()
        if text:
            log.log(level, text, extra=extra)


def _drain_readers(readers: Iterable[threading.Thread], timeout: float | None) -> bool:
    """Join the reader threads, bounded by `timeout` seconds shared among them.

    Returns `True` when every reader finished, `False` when the deadline
    passed with at least one still alive (an orphaned grandchild keeping a pipe
    open). `None` waits forever, like {meth}`subprocess.Popen.communicate`
    without a timeout.
    """
    readers = tuple(readers)
    deadline = time.monotonic() + timeout if timeout is not None else None
    for reader in readers:
        reader.join(
            None if deadline is None else max(0.0, deadline - time.monotonic()),
        )
    return not any(reader.is_alive() for reader in readers)


def run_cli(
    args: TArg | TNestedArgs,
    *,
    extra_env: TEnvVars | None = None,
    timeout: float | None = None,
    label: str | None = None,
    merge_streams: bool = False,
    errors: str = "replace",
    windows_creation_flags: int = 0,
    start_new_session: bool = False,
    command_level: int = logging.INFO,
    output_level: int = logging.DEBUG,
    log: logging.Logger | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a CLI in a subprocess, disclosing the call and streaming its output live.

    A {func}`subprocess.run` work-alike for CLI-wrapping tools, with observability
    built in:

    - the invocation is logged before the spawn, as the copy-pasteable
      `$ ENV=value command args` line of {func}`format_cli_prompt`, so a user
      can reproduce by hand what the tool runs on their system;
    - each line of the child's output is forwarded to the logger *as it is
      produced* (ANSI-stripped, tagged with `label`), instead of being held
      back until the child exits, so a long-running command narrates its progress
      live;
    - the child is registered in the live-process registry for the duration of the
      call, so {func}`terminate_live_processes` (wired to Ctrl+C by
      {func}`install_interrupt_handler`) can abort it.

    Contract mirrored from {func}`subprocess.run`:

    - returns a {class}`subprocess.CompletedProcess` with the full captured
      `stdout` and `stderr` decoded as UTF-8;
    - raises {exc}`subprocess.TimeoutExpired` (with the partial capture attached)
      when the child, or the draining of its output, outlives `timeout`. The
      child is killed first — its whole process tree on Windows (see
      {func}`_kill_windows_process_tree`), its whole POSIX process group when
      spawned with `start_new_session`, the direct child alone otherwise;
    - a {exc}`KeyboardInterrupt` mid-run kills the child (with the same tree,
      group or direct scope), then propagates.

    The child reads from {data}`subprocess.DEVNULL` so it can never block on
    `stdin`, and never opens a console window on Windows.

    ```{note}
    The pipes are opened in universal-newlines text mode, so a bare `\\r`
    (a child redrawing a progress bar in place) terminates a line just like
    `\\n`: each redraw is streamed as its own log line, and the captured
    text normalizes both to `\\n`, exactly as
    {meth}`subprocess.Popen.communicate` does.
    ```

    :param args: the command line. Nested iterables are flattened, `None`
        values dropped, and every element ({class}`~pathlib.Path`, versions, ...)
        cast to a string; see {func}`args_cleanup`.
    :param extra_env: environment variables forced over the inherited environment
        for this call (see {func}`~click_extra.envvar.env_copy`). They are part of
        the disclosed prompt line, since reproducing the call requires them.
    :param timeout: seconds before the child is killed. `None` waits forever.
    :param label: tag identifying this call on each streamed output line, for
        when several children interleave in one log. Carried as the record's
        `label` attribute, which {class}`click_extra.logging.Formatter` renders
        glued to the level name and styled like an invoked command
        (`debug:mas: Warning: ...`); a foreign formatter can read
        `record.label` itself. Applied to the output lines only, never the
        prompt line.
    :param merge_streams: route the child's `stderr` into `stdout` so the OS
        interleaves both in write order. The result's `stderr` is then `None`,
        like a {func}`subprocess.run` call with `stderr=STDOUT`.
    :param errors: decoding error handler for the child's output. The default
        `"replace"` swaps undecodable bytes for `�`; pass
        `"backslashreplace"` to keep them inspectable as escapes.
    :param windows_creation_flags: extra Windows process-creation flags, OR-ed
        with the always-on `CREATE_NO_WINDOW`. No-op off Windows.
    :param start_new_session: make the child lead its own POSIX session and
        process group ({class}`subprocess.Popen`'s parameter of the same name).
        Every kill path — the `timeout` overrun, a mid-run
        {exc}`KeyboardInterrupt`, and {func}`terminate_live_processes` — then
        signals the whole group, so a grandchild spawned by the child (a shim
        re-executing the real binary, an installer helper) is reaped along with
        it instead of surviving as an orphan holding the output pipes open.
        Off by default, and to be left off when a descendant must keep the
        controlling terminal: a new session detaches from it, so an interactive
        prompt raised from inside the child (`sudo` reading `/dev/tty`)
        would fail, and `sudo`'s tty-keyed credential cache would no longer
        match. No-op on Windows, where the timeout path already kills the full
        tree.
    :param command_level: logging level of the invocation-disclosure line.
        Defaults to {data}`logging.INFO`; lower it to {data}`logging.DEBUG` for
        internal probes not worth narrating.
    :param output_level: logging level of the streamed output lines. Defaults to
        {data}`logging.DEBUG`.
    :param log: destination logger. Defaults to the root logger, whose level the
        {class}`~click_extra.logging.VerbosityOption` family manages.
    """
    if log is None:
        log = logging.getLogger()
    clean_args = args_cleanup(args)
    assert clean_args, "No CLI to run."

    log.log(command_level, format_cli_prompt(clean_args, extra_env))

    # On Windows, CREATE_NO_WINDOW suppresses any console window the child might
    # open, while still capturing output via the explicit PIPE handles. SW_HIDE is
    # a belt-and-suspenders suppression of console windows. STARTUPINFO must be
    # created per call because subprocess overwrites its hStd* fields. On POSIX,
    # both creationflags=0 and startupinfo=None are no-ops.
    startupinfo = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo is not None:
        startupinfo = startupinfo()
        startupinfo.dwFlags = getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = 0  # SW_HIDE
    # Session isolation is a POSIX concept: force it off on Windows, whose kill
    # path already covers the whole tree through taskkill.
    start_new_session = start_new_session and not is_windows()
    process = subprocess.Popen(
        clean_args,
        # Prevents the child from blocking on stdin reads.
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_streams else subprocess.PIPE,
        encoding="utf-8",
        errors=errors,
        env=cast("subprocess._ENV", env_copy(extra_env)),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | windows_creation_flags,
        startupinfo=startupinfo,
        start_new_session=start_new_session,
    )
    log.debug(f"Spawned PID {process.pid}: {highlight_bin_name(clean_args[0])}.")

    # Track the live child so the main thread's SIGINT handler can terminate it on
    # Ctrl+C (see terminate_live_processes): a worker thread never receives the
    # interrupt itself. A session-isolated child is also flagged as the leader of
    # its own process group, so every kill path signals the group as a whole.
    with _LIVE_PROCESSES_LOCK:
        _LIVE_PROCESSES.add(process)
        if start_new_session:
            _GROUP_LEADERS.add(process)

    # One reader thread per captured pipe streams the output live while the
    # calling thread blocks in wait(). Daemon threads, so an abandoned reader (an
    # orphaned grandchild holding the pipe open past the kill grace) never blocks
    # interpreter shutdown.
    out_lines: list[str] = []
    err_lines: list[str] = []
    readers = []
    for pipe, sink in ((process.stdout, out_lines), (process.stderr, err_lines)):
        if pipe is None:
            continue
        reader = threading.Thread(
            target=_pump_stream,
            args=(pipe, sink, log, output_level, label),
            daemon=True,
        )
        reader.start()
        readers.append(reader)

    def timeout_expired() -> subprocess.TimeoutExpired:
        """Build the exception with the partial capture attached, as run() does."""
        assert timeout is not None
        return subprocess.TimeoutExpired(
            clean_args,
            timeout,
            output="".join(out_lines),
            stderr=None if merge_streams else "".join(err_lines),
        )

    def kill_child() -> None:
        """Forcibly stop the child: its tree on Windows, its whole POSIX process
        group when session-isolated, the direct child otherwise."""
        _kill_windows_process_tree(process.pid)
        if not (
            start_new_session and _kill_posix_process_group(process, signal.SIGKILL)
        ):
            process.kill()

    deadline = time.monotonic() + timeout if timeout is not None else None
    timeout_desc = "none" if timeout is None else f"{timeout}s"
    try:
        try:
            log.debug(f"Waiting for PID {process.pid} (timeout={timeout_desc}).")
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log.debug(f"PID {process.pid} timed out; sending kill.")
            kill_child()
            process.wait()
            _drain_readers(readers, _KILL_DRAIN_GRACE)
            log.debug(f"PID {process.pid} killed; exit {process.returncode}.")
            raise timeout_expired() from None
        except KeyboardInterrupt:
            log.debug(f"PID {process.pid} interrupted; sending kill.")
            kill_child()
            process.wait()
            _drain_readers(readers, _KILL_DRAIN_GRACE)
            raise
    finally:
        # The child is no longer live: drop it so a later Ctrl+C does not try to
        # signal an already-reaped process.
        with _LIVE_PROCESSES_LOCK:
            _LIVE_PROCESSES.discard(process)
            _GROUP_LEADERS.discard(process)

    # The child exited: drain the readers within what remains of the deadline. A
    # reader can outlive the child when a grandchild inherited the pipe and keeps
    # writing; communicate() times out on that same shape, so mirror it.
    remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
    if not _drain_readers(readers, remaining):
        log.debug(f"PID {process.pid} exited but its output drain timed out.")
        raise timeout_expired() from None

    stdout = "".join(out_lines)
    stderr = "".join(err_lines)
    log.debug(
        f"PID {process.pid} exited {process.returncode}; "
        f"stdout {len(stdout)} chars, stderr {len(stderr)} chars.",
    )
    return subprocess.CompletedProcess(
        clean_args,
        process.returncode,
        stdout=stdout,
        stderr=None if merge_streams else stderr,
    )
