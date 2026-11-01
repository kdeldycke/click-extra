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
"""The `--jobs` option, and the fan-out primitives that honor its count.

{class}`JobsOption` resolves the count, its `auto` and `max` keywords included,
and publishes it on `ctx.meta`. {func}`run_jobs` and {func}`run_lanes` spread
work over a thread pool of that size, and {func}`resolve_jobs` holds the policy
both apply.

```{todo}
Stop turning a {exc}`RuntimeError` of the wait in `_wait_result()` back into the
{exc}`KeyboardInterrupt` it replaced, once
[python/cpython#118433](https://github.com/python/cpython/issues/118433) is fixed
in every free-threaded Python Click Extra supports.
```
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections import deque
from contextlib import contextmanager
from gettext import gettext as _
from itertools import chain, islice
from typing import Final, TypeVar

import click
from click.core import ParameterSource
from click.shell_completion import CompletionItem

from . import context
from ._utils import AUTO
from .execution import _JOIN_POLL
from .parameters import ExtraOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Sequence
    from concurrent.futures import Future, ThreadPoolExecutor
    from typing import Any

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


def _logical_cpu_count() -> int | None:
    """The logical CPU count this process can actually use, if determinable.

    {func}`os.process_cpu_count` (Python 3.13+) is preferred: it honors the
    process's CPU affinity mask and, on Linux, the cgroup quota, so a
    container limited to two CPUs reports `2` instead of the host's full
    core count. {func}`os.cpu_count` is cgroup-blind, which is exactly what
    lets a quota-limited container oversubscribe its allocation, so it only
    serves as the fallback for older runtimes and platforms where the
    process-aware count is unavailable.
    """
    if hasattr(os, "process_cpu_count"):
        count: int | None = os.process_cpu_count()
        if count is not None:
            return count
    return os.cpu_count()


def _default_jobs(cpu_count: int | None) -> int:
    """The default number of parallel jobs on a host with `cpu_count` logical CPUs.

    See {data}`DEFAULT_JOBS` for the rule.
    """
    if not cpu_count:
        return 1
    return cpu_count - 1 if cpu_count >= 3 else cpu_count


CPU_COUNT = _logical_cpu_count()
"""Number of **logical** CPUs available to this process, or `None` if undetermined.

A count of *logical* processors (hardware threads), resolved by
{func}`_logical_cpu_count`: {func}`os.process_cpu_count` on Python 3.13+,
falling back to {func}`os.cpu_count` on older runtimes. On a CPU with
simultaneous multi-threading (Intel Hyper-Threading, AMD SMT) a
4-physical-core chip reports `8`. It is therefore **not** a count of
*physical* cores, and is usually larger than what physical-core tools report,
such as `psutil.cpu_count(logical=False)` or pytest-xdist's `-n auto` (which
counts physical cores). Parallelism here is keyed on the logical count on
purpose: subprocess- and I/O-bound work overlaps well across hardware
threads.
"""

DEFAULT_JOBS = _default_jobs(CPU_COUNT)
"""Default number of parallel jobs: {data}`CPU_COUNT` minus one reserved core.

Leaves one logical CPU free for the main process and system tasks, but only
on hosts with three logical CPUs or more: on smaller hosts the reservation
would collapse the pool to a single (sequential) worker, and threads waiting
on subprocesses and I/O cost nothing there, so the whole machine is used
instead. Falls back to `1` (sequential) when the count cannot be determined.

```{caution}
On a **single-CPU host** this still resolves to `1` and the default silently
runs sequentially. {meth}`JobCount.convert` logs whenever a parallel-intent
keyword collapses to a single job this way: as a warning for an explicit
request, at info level for the option's own default.
```
"""


class JobCount(click.ParamType):
    """Parse a `--jobs` value: an integer or the `auto`/`max` keyword.

    Resolves the symbolic keywords against the host's logical CPU count
    ({data}`CPU_COUNT`), counting hardware threads, not physical cores:

    - `auto` resolves to {data}`DEFAULT_JOBS` (one fewer than the available
      logical CPUs, except on hosts with fewer than three, where reserving a
      core would leave a single worker), the same heuristic used as the
      option's default.
    - `max` resolves to {data}`CPU_COUNT` (every available logical CPU).

    Any other token is parsed as an integer and left to
    {meth}`JobsOption.validate_jobs` for clamping and range-checking. Resolving
    the keywords here keeps the value handed downstream a plain {class}`int`,
    so consumers never have to know about the keywords.
    """

    name = "jobs"

    choices = (AUTO, "max")
    """Symbolic keywords accepted besides an integer count, in render order.

    Exposed as `choices` so the help colorizer highlights them like
    `click.Choice` values: the keyword collector duck-types on this attribute
    (see the `getattr(param.type, "choices", ...)` branch in
    `_HelpColorsMixin._collect_params`). It is also the single source of truth
    reused by {meth}`get_metavar` and {meth}`convert`, so the metavar and the
    parser never drift apart.
    """

    def get_metavar(self, param: click.Parameter, ctx: click.Context) -> str:
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
            resolved = DEFAULT_JOBS if normalized == AUTO else (CPU_COUNT or 1)
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
    {class}`~click_extra.jobs.JobCount`: `auto` (the default: one fewer
    than the available logical CPU cores, leaving a core free for the main
    process and system tasks, except on hosts with fewer than three logical
    CPUs, where reserving one would leave a single worker) and `max` (every
    available logical CPU core). A value of `0` disables parallelism and runs
    sequentially.

    The core count is the number of *logical* CPUs (hardware threads)
    available to the process, not physical cores: see
    {data}`~click_extra.jobs.CPU_COUNT`. On a host with a single logical
    CPU, `auto`/`max` resolve to a single job and
    {class}`~click_extra.jobs.JobCount` logs that execution will be
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

        {class}`~click_extra.jobs.JobCount` has already resolved any
        `auto`/`max` keyword to an integer by the time this runs. A value of
        `0` disables parallelism: it is rounded up to `1` (sequential
        execution) with a warning. Negative values are likewise clamped to
        `1`. A count above the available cores is honored: the pool is a
        {class}`~concurrent.futures.ThreadPoolExecutor`, and oversubscription
        is how I/O- and subprocess-bound work overlaps, so the warning only
        flags the CPU-bound case where extra threads just contend for the
        GIL. The resolved count is then logged at info level next to the
        host's logical CPU count ({data}`~click_extra.jobs.CPU_COUNT`),
        so a CLI's parallelism is visible under `--verbosity INFO`.
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
                "Requested %d jobs exceeds the %d logical CPUs: honored, "
                "but pays only for I/O-bound work.",
                value,
                CPU_COUNT,
            )

        context.set(ctx, context.JOBS, effective)

        # Surface the resolved worker count so any CLI using --jobs can show its
        # parallelism (and how it maps to the logical CPU count) under -v/INFO.
        logger.info(
            "Resolved --jobs to %d (%s logical CPUs).",
            effective,
            CPU_COUNT if CPU_COUNT is not None else "unknown",
        )

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
        default: int | str = AUTO,
        expose_value: bool = False,
        show_default: bool | str = True,
        type: click.ParamType | Any = JobCount(),
        help: str = _(
            "Number of parallel jobs. Accepts an integer, auto (the host's "
            "logical CPUs, minus one when there are three or more) or max (all "
            "logical CPUs). --jobs 0 runs sequentially."
        ),
        **kwargs: Any,
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


def _wait_result(future: Future[R]) -> R:
    """The result of `future`, waited for in slices of {data}`_JOIN_POLL` seconds.

    A Ctrl+C that lands as the main thread enters the wait is then handled within
    one slice. An unbounded wait would hand it to the handler only once the task
    returns, however long it runs: see {data}`_JOIN_POLL`.

    The future is read once it is done, never with a timeout of its own. A timed
    read that runs out raises the {exc}`TimeoutError` a task may raise itself,
    like a {exc}`socket.timeout`, and the two could not be told apart.

    A free-threaded CPython can raise the Ctrl+C after the wait releases its lock
    and before it takes the lock back, then fail to release a lock it no longer
    holds: the {exc}`KeyboardInterrupt` comes out as a {exc}`RuntimeError`
    ([python/cpython#118433](https://github.com/python/cpython/issues/118433)).
    The interrupt is raised again in its place.
    """
    # Deferred import: keeps concurrent.futures off the startup path of every CLI.
    from concurrent.futures import wait

    while not future.done():
        try:
            wait((future,), timeout=_JOIN_POLL)
        except RuntimeError as exc:
            if isinstance(exc.__context__, KeyboardInterrupt):
                raise exc.__context__ from None
            raise
    return future.result()


@contextmanager
def _interruptible_pool(
    max_workers: int,
    stop: threading.Event,
) -> Generator[ThreadPoolExecutor, None, None]:
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
    in-flight task finished, defeating the interrupt. The `stop` event, set on
    that same abort, lets a task made of several steps quit between two of them.

    The pool of {func}`run_lanes`, and so of {func}`run_jobs`.
    """
    # Deferred import: keeps concurrent.futures off the startup path of every CLI.
    from concurrent.futures import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        yield executor
    except (KeyboardInterrupt, GeneratorExit):
        stop.set()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    except BaseException:
        # A task raised: keep the drain-then-propagate semantics of `with`.
        executor.shutdown(wait=True)
        raise
    else:
        executor.shutdown(wait=True)


_WORKER_WINDOW_FACTOR: Final = 4
"""How many tasks {func}`run_jobs` and {func}`run_lanes` keep in flight per worker.

One task per worker would leave it idle between finishing its own and the caller
pulling the next result. A few queued behind each keeps them fed, while staying a
multiple of the worker count rather than growing with the stream.
"""


def _windowed_map(
    executor: ThreadPoolExecutor,
    func: Callable[[T], R],
    items: Iterable[T],
    window: int,
) -> Generator[R, None, None]:
    """Map `func` over `items`, keeping at most `window` tasks in flight.

    The lazy counterpart of {meth}`~concurrent.futures.Executor.map`, which
    submits every item up front and so drains whatever iterable it is handed.
    Here the stream is pulled one item at a time as a slot frees, keeping both
    the queue and the unread tail of `items` bounded however long the stream is.
    Results still come out in submission order.

    A caller that stops early therefore leaves the rest of the stream unread and
    unscheduled, matching what the sequential path already promised.
    """
    stream = iter(items)
    pending: deque[Future[R]] = deque(
        executor.submit(func, item) for item in islice(stream, window)
    )
    while pending:
        result = _wait_result(pending.popleft())
        # Refill the freed slot before handing the result over, so a worker does
        # not sit idle while the caller processes what it just got.
        for item in islice(stream, 1):
            pending.append(executor.submit(func, item))
        yield result


def run_jobs(
    func: Callable[[T], R],
    items: Iterable[T],
    *,
    jobs: int | None = None,
    serial_at_debug: bool = False,
) -> Generator[R, None, None]:
    """Run `func` over `items`, parallelized per the resolved `--jobs` count.

    The worker count is taken from `jobs` when given, else resolved from the
    active command's {class}`JobsOption` value by {func}`resolve_jobs`, else `1`.
    With a single worker (or at most one item) the items run **sequentially and
    lazily**, so a caller can stop early on the first result (for example to abort
    on the first failure); otherwise they run in a thread pool. Either way results
    are yielded in submission order, like {func}`map`.

    This is the single-task-per-item special case of {func}`run_lanes`, which runs
    every item as a lane of its own. Reach for {func}`run_lanes` when some items
    must run serially relative to one another while others run concurrently.

    The pool is thread-based, which suits the I/O- and subprocess-bound work CLI
    tools usually parallelize (each child releases the GIL). The count is a
    number of logical CPUs: see {data}`~click_extra.jobs.CPU_COUNT`.

    `items` is never materialized: only a bounded window of tasks is queued at a
    time, so an unbounded or expensive-to-produce stream stays memory-flat and is
    read no further than the caller consumes.

    :param func: Called once per item; its return value is yielded.
    :param items: The work items. Read lazily, a window at a time.
    :param jobs: Override the worker count instead of reading it from the
        context. `1` or fewer forces sequential execution.
    :param serial_at_debug: forwarded to {func}`resolve_jobs` when `jobs` is not
        given: collapse to sequential at `DEBUG` verbosity.
    :return: An iterator over `func`'s results, in the order of `items`.
    """
    yield from run_lanes(
        func,
        ([item] for item in items),
        jobs=jobs,
        serial_at_debug=serial_at_debug,
    )


def run_lanes(
    func: Callable[[T], R],
    lanes: Iterable[Iterable[T]],
    *,
    jobs: int | None = None,
    serial_at_debug: bool = False,
) -> Generator[R, None, None]:
    """Run `func` over grouped items: serial within a lane, concurrent across.

    Each *lane* is an iterable of items. `func` is mapped over every item, but a
    lane's own items run **serially and in order** on a single worker, while distinct
    lanes run **concurrently** up to the resolved `--jobs` count. This is the right
    primitive when some work must be serialized relative to itself (a shared lock, a
    rate limit, one mailbox file, one package-manager backend) yet still overlap with
    unrelated work.

    {func}`run_jobs` is the degenerate case where every lane holds a single item.
    Concurrency is sized by the *number of lanes* (one worker per lane), since a
    lane never splits across workers. A single lane runs in the calling thread,
    whatever the worker count.

    Results are yielded in lane-submission order, a lane's items in order, like
    {func}`map`. The run stays lazy at any worker count: a lane is materialized
    only when it is about to be scheduled, and only a bounded window of lanes is
    in flight, so a caller can break early and the lanes behind it are never read.
    A lane runs entirely on one worker, so a stateful resource bound to the lane
    (a per-lane cache, a connection) is touched by only that one thread and needs
    no lock.

    :param func: Called once per item; its return value is yielded.
    :param lanes: The lanes, each an iterable of items. Read lazily, a window of
        lanes at a time; a lane's own items are materialized when it is scheduled.
    :param jobs: Override the worker count instead of reading it from the context.
        `1` or fewer forces fully sequential execution.
    :param serial_at_debug: forwarded to {func}`resolve_jobs` when `jobs` is not
        given: collapse to sequential at `DEBUG` verbosity.
    :return: An iterator over `func`'s results, lane by lane in submission order.
    """
    # Each lane is materialized only as it is pulled, never all of them at once.
    lane_stream = (list(lane) for lane in lanes)
    # Two lanes are all it takes to tell a run with nothing to overlap, which stays
    # sequential, from a real batch. The rest of the stream is left unread.
    head = list(islice(lane_stream, 2))
    if len(head) > 1 and jobs is None:
        # No cap at the number of lanes, which a lazy stream cannot report without
        # being drained: the rest of the policy applies, and the pool spawns its
        # threads on demand, so a ceiling above the number of lanes costs nothing.
        jobs = resolve_jobs(
            click.get_current_context(silent=True),
            sys.maxsize,
            serial_at_debug=serial_at_debug,
        )

    if len(head) <= 1 or jobs is None or jobs <= 1:
        # Sequential and lazy across every lane and item: the caller can break
        # early (for example on the first failure) and the rest never runs.
        for lane in chain(head, lane_stream):
            for item in lane:
                yield func(item)
    else:
        # Each lane is a serial chain run on one worker; chains run concurrently and
        # their results are yielded in submission order.
        stop = threading.Event()

        def run_chain(lane: list[T]) -> list[R]:
            results = []
            for item in lane:
                # An interrupted or abandoned run stops each running lane after
                # its current item, instead of running the lane to its end.
                if stop.is_set():
                    break
                results.append(func(item))
            return results

        # The pool teardown drops queued lanes on a prompt interrupt instead of
        # blocking on the in-flight ones (see {func}`_interruptible_pool`).
        with _interruptible_pool(jobs, stop=stop) as executor:
            for chain_results in _windowed_map(
                executor,
                run_chain,
                chain(head, lane_stream),
                jobs * _WORKER_WINDOW_FACTOR,
            ):
                yield from chain_results
