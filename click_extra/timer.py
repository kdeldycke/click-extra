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
"""Command execution time measurement."""

from __future__ import annotations

from gettext import gettext as _
from time import perf_counter
from typing import Sequence

from . import Context, Parameter, echo
from .parameters import ExtraOption


class TimerOption(ExtraOption):
    """A pre-configured option that is adding a ``--time``/``--no-time`` flag to print
    elapsed time at the end of CLI execution.

    The start time is made available in the context in
    ``ctx.meta["click_extra.start_time"]``.
    """

    def print_timer(self):
        """Compute and print elapsed execution time."""
        echo(f"Execution time: {perf_counter() - self.start_time:0.3f} seconds.")

    def register_timer_on_close(
        self,
        ctx: Context,
        param: Parameter,
        value: bool,
    ) -> None:
        """Callback setting up all timer's machinery.

        Computes and print the execution time at the end of the CLI, if option has been
        activated.
        """
        # Take timestamp snapshot.
        self.start_time = perf_counter()

        ctx.meta["click_extra.start_time"] = self.start_time

        # Skip timekeeping if option is not active.
        if value:
            # Register printing at the end of execution.
            ctx.call_on_close(self.print_timer)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default=False,
        expose_value=False,
        help=_("Measure and print elapsed execution time."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--time/--no-time",)

        kwargs.setdefault("callback", self.register_timer_on_close)

        super().__init__(
            param_decls=param_decls,
            default=default,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )
