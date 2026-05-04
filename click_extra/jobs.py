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
"""Parallel job control utilities."""

from __future__ import annotations

import logging
import os
from gettext import gettext as _

from . import context
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
