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
"""Telemetry utilities."""

from __future__ import annotations

from gettext import gettext as _
from typing import TYPE_CHECKING, Sequence

from .parameters import ExtraOption, extend_envvars

if TYPE_CHECKING:
    from . import Context, Parameter


class TelemetryOption(ExtraOption):
    """A pre-configured ``--telemetry``/``--no-telemetry`` option flag.

    Respects the
    `proposed DO_NOT_TRACK environment variable <https://consoledonottrack.com>`_ as a
    unified standard to opt-out of telemetry for TUI/console apps.

    The ``DO_NOT_TRACK`` convention takes precedence over the user-defined environment
    variables and the auto-generated values.

    .. seealso::

        - A `knowledge base of telemetry disabling configuration options
          <https://github.com/beatcracker/toptout>`_.

        - And another `list of environment variable to disable telemetry in desktop apps
          <https://telemetry.timseverien.com/opt-out/>`_.
    """

    def save_telemetry(
        self,
        ctx: Context,
        param: Parameter,
        value: bool,
    ) -> None:
        """Save the option value in the context, in ``ctx.telemetry``."""
        ctx.telemetry = value  # type: ignore[attr-defined]

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default=False,
        expose_value=False,
        envvar=None,
        show_envvar=True,
        help=_("Collect telemetry and usage data."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--telemetry/--no-telemetry",)

        envvar = extend_envvars(["DO_NOT_TRACK"], envvar)

        kwargs.setdefault("callback", self.save_telemetry)

        super().__init__(
            param_decls=param_decls,
            default=default,
            expose_value=expose_value,
            envvar=envvar,
            show_envvar=show_envvar,
            help=help,
            **kwargs,
        )
