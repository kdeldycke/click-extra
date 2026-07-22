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

from . import context
from .envvar import merge_envvar_ids
from .parameters import ExtraOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence

    import click


class TelemetryOption(ExtraOption):
    """A pre-configured `--telemetry`/`--no-telemetry` option flag.

    Respects the
    [proposed DO_NOT_TRACK environment variable](https://consoledonottrack.com) as a
    unified standard to opt-out of telemetry for TUI/console apps.

    The `DO_NOT_TRACK` convention takes precedence over the user-defined environment
    variables and the auto-generated values.

    The resolved value is stored in
    {data}`ctx.meta[click_extra.context.TELEMETRY] <click_extra.context.TELEMETRY>`,
    aligning with every other Click Extra option's per-invocation context-meta
    storage pattern.

    ```{seealso}

    - A [knowledge base of telemetry disabling configuration options](https://github.com/beatcracker/toptout).

    - And another [list of environment variable to disable telemetry in desktop apps](https://telemetry.timseverien.com/opt-out/).
    ```
    """

    def set_telemetry(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Store the resolved telemetry opt-in flag on the context's `meta` dict.

        Reads via {func}`click_extra.context.get(ctx, click_extra.context.TELEMETRY)
        <click_extra.context.get>`. Renamed from `save_telemetry` to align
        with the `set_<key>` convention used by every other ctx.meta-writing
        callback.
        """
        context.set(ctx, context.TELEMETRY, value)

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

        envvar = merge_envvar_ids("DO_NOT_TRACK", envvar)

        kwargs.setdefault("callback", self.set_telemetry)

        super().__init__(
            param_decls=param_decls,
            default=default,
            expose_value=expose_value,
            envvar=envvar,
            show_envvar=show_envvar,
            help=help,
            **kwargs,
        )
