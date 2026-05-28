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
from gettext import gettext as _
from time import perf_counter

from . import context, echo
from .parameters import ExtraOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence

    import click

logger = logging.getLogger(__name__)

CPU_COUNT = os.cpu_count()
"""Number of available CPU cores, or ``None`` if undetermined."""

DEFAULT_JOBS = max(1, CPU_COUNT - 1) if CPU_COUNT else 1
"""Default number of parallel jobs: one fewer than available cores.

Falls back to ``1`` on single-core machines or when the core count cannot be
determined.
"""


class JobsOption(ExtraOption):
    """A pre-configured ``--jobs`` option to control parallel execution.

    Defaults to one fewer than the number of available CPU cores, leaving one
    core free for the main process and system tasks.

    The resolved value is stored in ``ctx.meta[click_extra.context.JOBS]``.

    .. warning::
        This option is a placeholder for future parallel execution utilities.
        It does not drive any concurrency by itself: downstream code must read
        ``ctx.meta[click_extra.context.JOBS]`` and act on it.
    """

    def validate_jobs(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: int,
    ) -> None:
        """Validate job count and store the effective value in context metadata.

        Clamps values below 1 to 1 and warns when the requested count exceeds
        available CPU cores.
        """
        if ctx.resilient_parsing:
            return

        effective = value

        if value < 1:
            effective = 1
            logger.warning(
                "Requested %d jobs, clamping to minimum of 1.",
                value,
            )

        if CPU_COUNT and value > CPU_COUNT:
            logger.warning(
                "Requested %d jobs exceeds available CPU cores (%d).",
                value,
                CPU_COUNT,
            )

        context.set(ctx, context.JOBS, effective)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default=DEFAULT_JOBS,
        expose_value=False,
        show_default=True,
        type=int,
        help=_("Number of parallel jobs. Defaults to one less than available CPUs."),
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
