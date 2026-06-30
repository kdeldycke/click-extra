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
"""Options controlling how a CLI runs: timing, parallelism and exit code.

These options share the same shape: each is a pre-configured
:class:`~click_extra.parameters.ExtraOption` that publishes its resolved value
on ``ctx.meta`` for downstream code to consume. Only :class:`TimerOption` acts
on its own (printing the elapsed time); :class:`JobsOption` and
:class:`ZeroExitOption` are contracts the framework records but does not enforce.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from gettext import gettext as _
from time import perf_counter
from typing import TypeVar

import click
from click.shell_completion import CompletionItem

from . import context, echo
from .parameters import ExtraOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from typing import Any

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")

CPU_COUNT = os.cpu_count()
"""Number of **logical** CPUs available, or ``None`` if undetermined.

This is :func:`os.cpu_count`, which counts *logical* processors (hardware
threads). On a CPU with simultaneous multi-threading (Intel Hyper-Threading,
AMD SMT) a 4-physical-core chip reports ``8``. It is therefore **not** a count
of *physical* cores, and is usually larger than what physical-core tools
report, such as ``psutil.cpu_count(logical=False)`` or pytest-xdist's
``-n auto`` (which counts physical cores). Parallelism here is keyed on the
logical count on purpose: subprocess- and I/O-bound work overlaps well across
hardware threads.
"""

DEFAULT_JOBS = max(1, CPU_COUNT - 1) if CPU_COUNT else 1
"""Default number of parallel jobs: one fewer than :data:`CPU_COUNT` (logical CPUs).

Leaves one logical CPU free for the main process and system tasks. Falls back
to ``1`` (sequential) when the count cannot be determined.

.. caution::
    This resolves to ``1`` not only on single-core hosts but also on **two-core
    hosts**, since it reserves one core. There, the default silently runs
    sequentially. :meth:`JobCount.convert` logs a warning whenever a
    parallel-intent keyword collapses to a single job this way.
"""


class JobCount(click.ParamType):
    """Parse a ``--jobs`` value: an integer or the ``auto``/``max`` keyword.

    Resolves the symbolic keywords against the host's logical CPU count
    (:data:`CPU_COUNT`), counting hardware threads, not physical cores:

    - ``auto`` resolves to :data:`DEFAULT_JOBS` (one fewer than the available
      logical CPUs), the same heuristic used as the option's default.
    - ``max`` resolves to :data:`CPU_COUNT` (every available logical CPU).

    Any other token is parsed as an integer and left to
    :meth:`JobsOption.validate_jobs` for clamping and range-checking. Resolving
    the keywords here keeps the value handed downstream a plain :class:`int`,
    so consumers never have to know about the keywords.
    """

    name = "jobs"

    #: Symbolic keywords accepted besides an integer count, in render order.
    #:
    #: Exposed as ``choices`` so the help colorizer highlights them like
    #: ``click.Choice`` values: the keyword collector duck-types on this
    #: attribute (see the ``getattr(param.type, "choices", ...)`` branch in
    #: ``_HelpColorsMixin._collect_params``). It is
    #: also the single source of truth reused by :meth:`get_metavar` and
    #: :meth:`convert`, so the metavar and the parser never drift apart.
    choices = ("auto", "max")

    def get_metavar(self, param, ctx=None):
        """Render ``[auto|max|INTEGER]`` (brackets included, as ``Choice`` does)."""
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
        parallel-intent keyword (``auto``/``max``) resolves to a single job, a
        warning is logged: the request reads as "use several cores", but the
        host has too few logical CPUs, so execution is silently sequential.
        """
        if isinstance(value, int):
            return value

        normalized = str(value).strip().lower()
        if normalized in self.choices:
            resolved = DEFAULT_JOBS if normalized == "auto" else (CPU_COUNT or 1)
            # A parallel-intent keyword that collapses to a single job runs
            # sequentially: warn so it is not mistaken for parallel execution.
            if resolved <= 1 and not (ctx is not None and ctx.resilient_parsing):
                if CPU_COUNT is None:
                    cpu_desc = "the number of logical CPUs could not be determined"
                elif CPU_COUNT == 1:
                    cpu_desc = "only 1 logical CPU is available"
                else:
                    cpu_desc = f"only {CPU_COUNT} logical CPUs are available"
                logger.warning(
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
        """Suggest the ``auto``/``max`` keywords; an integer count is free-form.

        Completion proposes only the symbolic keywords, matched
        case-insensitively to mirror how :meth:`convert` lower-cases its input.
        An integer has no finite set to enumerate, so none is offered, yet
        :meth:`convert` still accepts one.
        """
        prefix = incomplete.lower()
        return [
            CompletionItem(keyword)
            for keyword in self.choices
            if keyword.startswith(prefix)
        ]


class JobsOption(ExtraOption):
    """A pre-configured ``--jobs`` option to control parallel execution.

    Accepts an integer or one of two keywords resolved by
    :class:`~click_extra.execution.JobCount`: ``auto`` (the default: one fewer
    than the available logical CPU cores, leaving a core free for the main
    process and system tasks) and ``max`` (every available logical CPU core). A
    value of ``0`` disables parallelism and runs sequentially.

    The core count is the number of *logical* CPUs (hardware threads) reported
    by :func:`os.cpu_count`, not physical cores: see
    :data:`~click_extra.execution.CPU_COUNT`. On a host with too few logical
    CPUs, ``auto``/``max`` resolve to a single job and
    :class:`~click_extra.execution.JobCount` logs a warning that execution will
    be sequential.

    The resolved value is stored as an :class:`int` in
    ``ctx.meta[click_extra.context.JOBS]``.

    .. warning::
        ``JobsOption`` only resolves and publishes the job count: it does not
        drive any concurrency by itself. Pass it to :func:`run_jobs` (which
        reads the resolved ``ctx.meta[click_extra.context.JOBS]`` count), or
        read that value yourself and act on it.
    """

    def validate_jobs(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: int,
    ) -> None:
        """Validate the resolved job count and store it in context metadata.

        :class:`~click_extra.execution.JobCount` has already resolved any
        ``auto``/``max`` keyword to an integer by the time this runs. A value of
        ``0`` disables parallelism: it is rounded up to ``1`` (sequential
        execution) with a warning. Negative values are likewise clamped to
        ``1``, and a count above the available cores is honored but warned
        about. The resolved count is then logged at info level next to the
        host's logical CPU count (:data:`~click_extra.execution.CPU_COUNT`), so a
        CLI's parallelism is visible under ``--verbosity INFO``.
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
    """Resolve how many worker threads to use for a batch of ``count`` items.

    Returns the number of items to process in parallel; ``1`` means run
    sequentially in the calling thread. This is the policy shared by
    :func:`run_jobs` and :func:`run_lanes`, exposed on its own for callers that
    must know the resolved count *before* they fan out (for example to pick a
    progress-rendering mode). It collapses to sequential when:

    - there is no active CLI context (programmatic or test use),
    - a single item leaves nothing to parallelize, or
    - the resolved :class:`JobsOption` count
      (``ctx.meta[click_extra.context.JOBS]``) is ``1`` or less.

    Otherwise that count wins, capped at ``count``: there is no point spinning up
    more workers than there are items.

    :param ctx: the active Click context, read for the resolved ``--jobs`` count
        (and, with ``serial_at_debug``, the verbosity). ``None`` forces sequential.
    :param count: how many items are about to be scheduled.
    :param serial_at_debug: when set, also collapse to sequential at ``DEBUG``
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


def run_jobs(
    func: Callable[[T], R],
    items: Iterable[T],
    *,
    jobs: int | None = None,
    serial_at_debug: bool = False,
) -> Iterator[R]:
    """Run ``func`` over ``items``, parallelized per the resolved ``--jobs`` count.

    The worker count is taken from ``jobs`` when given, else resolved from the
    active command's :class:`JobsOption` value by :func:`resolve_jobs`, else ``1``.
    With a single worker (or at most one item) the items run **sequentially and
    lazily**, so a caller can stop early on the first result (for example to abort
    on the first failure); otherwise they run in a thread pool. Either way results
    are yielded in submission order, like :func:`map`.

    This is the single-task-per-item special case of :func:`run_lanes` (every item
    is its own lane). Reach for :func:`run_lanes` when some items must run serially
    relative to one another while others run concurrently.

    The pool is thread-based, which suits the I/O- and subprocess-bound work CLI
    tools usually parallelize (each child releases the GIL). The count is a
    number of logical CPUs: see :data:`~click_extra.execution.CPU_COUNT`.

    :param func: Called once per item; its return value is yielded.
    :param items: The work items. Materialized up front to size the pool.
    :param jobs: Override the worker count instead of reading it from the
        context. ``1`` or fewer forces sequential execution.
    :param serial_at_debug: forwarded to :func:`resolve_jobs` when ``jobs`` is not
        given: collapse to sequential at ``DEBUG`` verbosity.
    :return: An iterator over ``func``'s results, in the order of ``items``.
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
        # submission order. Breaking early does not cancel running work.
        with ThreadPoolExecutor(max_workers=min(jobs, len(work))) as executor:
            yield from executor.map(func, work)


def run_lanes(
    func: Callable[[T], R],
    lanes: Iterable[Iterable[T]],
    *,
    jobs: int | None = None,
    serial_at_debug: bool = False,
) -> Iterator[R]:
    """Run ``func`` over grouped items: serial within a lane, concurrent across.

    Each *lane* is an iterable of items. ``func`` is mapped over every item, but a
    lane's own items run **serially and in order** on a single worker, while distinct
    lanes run **concurrently** up to the resolved ``--jobs`` count. This is the right
    primitive when some work must be serialized relative to itself (a shared lock, a
    rate limit, one mailbox file, one package-manager backend) yet still overlap with
    unrelated work.

    :func:`run_jobs` is the degenerate case where every lane holds a single item.
    Concurrency is sized by the *number of lanes* (one worker per lane), since a
    lane never splits across workers.

    Results are yielded in lane-submission order, a lane's items in order, like
    :func:`map`. With a single worker the run stays lazy (the caller can break
    early); otherwise every lane is submitted up front. A lane runs entirely on one
    worker, so a stateful resource bound to the lane (a per-lane cache, a connection)
    is touched by only that one thread and needs no lock.

    :param func: Called once per item; its return value is yielded.
    :param lanes: The lanes, each an iterable of items. Materialized up front.
    :param jobs: Override the worker count instead of reading it from the context.
        ``1`` or fewer forces fully sequential execution.
    :param serial_at_debug: forwarded to :func:`resolve_jobs` when ``jobs`` is not
        given: collapse to sequential at ``DEBUG`` verbosity.
    :return: An iterator over ``func``'s results, lane by lane in submission order.
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

        with ThreadPoolExecutor(max_workers=jobs) as executor:
            for chain_results in executor.map(run_chain, lane_list):
                yield from chain_results


class TimerOption(ExtraOption):
    """A pre-configured option that is adding a ``--time``/``--no-time`` flag to print
    elapsed time at the end of CLI execution.

    The start time is made available in the context in
    ``ctx.meta[click_extra.context.START_TIME]``.
    """

    def print_timer(self) -> None:
        """Compute and print elapsed execution time.

        Always prints, even when a sibling eager option (``--version``,
        ``--show-params``, ``--show-config``…) short-circuited the command
        body via ``ctx.exit()``. That makes ``--time`` a usable probe for
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

        Captures :func:`time.perf_counter` as the start time, stores it on
        ``ctx.meta`` under :data:`click_extra.context.START_TIME`, and queues
        :py:meth:`print_timer` as a context-close callback so the elapsed
        duration is printed even when a sibling eager option (``--version``,
        ``--show-params``…) short-circuits the command body.

        Renamed from ``register_timer_on_close`` to align with the
        ``init_<system>`` convention shared with
        :class:`~click_extra.table.TableFormatOption.init_formatter` and
        :class:`~click_extra.table.SortByOption.init_sort`.
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
    """A pre-configured ``-0``/``--zero-exit`` option flag.

    Follows the convention popularized by linters and static analysers, which
    exit with a non-zero code whenever they report findings so that automation
    can gate on it. Setting this flag flips that behavior: the CLI returns ``0``
    as long as it ran to completion, reserving non-zero codes for actual
    execution failures.

    The resolved value is stored in
    :data:`ctx.meta[click_extra.context.ZERO_EXIT] <click_extra.context.ZERO_EXIT>`,
    aligning with every other Click Extra option's per-invocation context-meta
    storage pattern.

    .. warning::
        This option is a placeholder: it does not alter the CLI's exit code by
        itself. Downstream code must read
        :data:`ctx.meta[click_extra.context.ZERO_EXIT] <click_extra.context.ZERO_EXIT>`
        and act on it.
    """

    def set_zero_exit(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Store the resolved zero-exit flag on the context's ``meta`` dict.

        Read via :func:`click_extra.context.get(ctx, click_extra.context.ZERO_EXIT)
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
