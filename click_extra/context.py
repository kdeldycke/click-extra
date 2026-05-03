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
"""Click context plumbing: the :class:`ExtraContext` subclass plus the central
registry of every ``ctx.meta`` key Click Extra writes or reads.

Click's :attr:`click.Context.meta` is a per-invocation dict that Click shares
across the parent/child context hierarchy. Click Extra uses it to pass
per-invocation state (the picked theme, the resolved table format, the loaded
configuration, etc.) between eager callbacks and the rest of the CLI without
mutating module-level globals. Per-invocation context storage is what keeps
back-to-back invocations of the same CLI (Sphinx builds, test runners, REPLs)
from leaking state into each other.

This module is part of Click Extra's **public API**. Inside any
``@command``- or ``@group``-decorated function, request the active context
with :func:`click.pass_context` (or call :func:`click.get_current_context`)
and read the entries you need:

.. code-block:: python

    from click_extra import command, context, echo, pass_context


    @command
    @pass_context
    def cli(ctx):
        echo(f"Theme: {ctx.meta[context.THEME]}")
        echo(f"Jobs:  {ctx.meta[context.JOBS]}")

Each constant below documents who writes the entry, when, and what shape the
value takes. The raw string values are stable and downstream code may also
read ``ctx.meta["click_extra.<field>"]`` directly: the constants exist so
internal call sites and downstream code can converge on a single spelling.
"""

from __future__ import annotations

from typing import Any

import click
import cloup

from .colorize import HelpExtraFormatter

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Final


class ExtraContext(cloup.Context):
    """Like ``cloup._context.Context``, but with the ability to populate the context's
    ``meta`` property at instantiation.

    Also defaults ``color`` to ``True`` for root contexts (i.e. without a parent), so
    help screens are always colorized — even when piped. Click's own default is ``None``
    (auto-detect via TTY), which strips colors in non-interactive contexts.

    Parent-to-child color inheritance is handled by Click itself at ``Context.__init__``
    time, so no property override is needed.

    .. todo::
        Propose addition of ``meta`` keyword upstream to Click.
    """

    formatter_class = HelpExtraFormatter
    """Use our own formatter to colorize the help screen."""

    def __init__(self, *args, meta: dict[str, Any] | None = None, **kwargs) -> None:
        """Like parent's context but with an extra ``meta`` keyword-argument.

        Also force ``color`` default to ``True`` if not provided by user and this
        context has no parent.
        """
        super().__init__(*args, **kwargs)

        # Click defaults root ``ctx.color`` to ``None`` (auto-detect via TTY), which
        # strips colors when piped. Override to ``True`` for parentless contexts so
        # help screens are always colorized by default. The ``ColorOption`` callback
        # will set the final value later, respecting ``--no-color`` and env vars.
        if not self.parent and self.color is None:
            self.color = True

        # Update the context's meta property with the one provided by user.
        if meta:
            self._meta.update(meta)


META_NAMESPACE: Final[str] = "click_extra."
"""Prefix shared by every ``ctx.meta`` key Click Extra writes.

Reserved for entries the framework owns. Downstream consumers picking their
own ``ctx.meta`` keys are encouraged to use a different prefix to avoid
colliding with current or future Click Extra entries.
"""


class _LazyMetaDict(dict):
    """Dict subclass that lazily resolves fields on first access.

    Installed as ``ctx._meta`` so that ``ctx.meta["click_extra.<field>"]``
    transparently evaluates the corresponding ``@cached_property`` on the
    source object only when the key is actually read.
    """

    def __init__(
        self,
        base: dict[str, Any],
        source: object,
        fields: tuple[str, ...],
    ) -> None:
        super().__init__(base)
        self._source = source
        self._lazy_keys = {f"{META_NAMESPACE}{f}": f for f in fields}

    def _resolve(self, key: str) -> Any:
        """Resolve a lazy key, cache the result, and return it."""
        value = getattr(self._source, self._lazy_keys[key])
        # Store as a regular entry so subsequent reads are plain dict lookups.
        dict.__setitem__(self, key, value)
        return value

    def __getitem__(self, key: str) -> Any:
        if key in self._lazy_keys and not dict.__contains__(self, key):
            return self._resolve(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        return key in self._lazy_keys or super().__contains__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._lazy_keys:
            if dict.__contains__(self, key):
                return super().__getitem__(key)
            return self._resolve(key)
        return super().get(key, default)


# --- Argument capture ---------------------------------------------------------

RAW_ARGS: Final[str] = "click_extra.raw_args"
"""The pre-parsed ``argv`` slice fed to the current command.

Written by :class:`click_extra.commands.ExtraCommand.make_context` so that
:class:`click_extra.parameters.ShowParamsOption` can re-parse the original
arguments for the ``--show-params`` table without re-running the callbacks.
"""


# --- Configuration loading ----------------------------------------------------

CONF_SOURCE: Final[str] = "click_extra.conf_source"
"""Resolved path or URL of the configuration file that was loaded.

Written by :class:`click_extra.config.ConfigOption.load_conf` after a
configuration file is found and parsed. ``None`` if no file matched.
"""

CONF_FULL: Final[str] = "click_extra.conf_full"
"""Full parsed configuration document (the whole file, every section).

Written by :class:`click_extra.config.ConfigOption.load_conf`. Read by
:class:`click_extra.commands.ExtraGroup` (for subcommand inheritance) and by
:func:`click_extra.wrap.run` (to forward the loaded config to wrapped CLIs).
"""

TOOL_CONFIG: Final[str] = "click_extra.tool_config"
"""The app-specific config section, deserialised through ``config_schema``.

Written by :class:`click_extra.config.ConfigOption._apply_config_schema` only
when a schema callable is configured. Read via
:func:`click_extra.config.get_tool_config`.
"""


# --- Verbosity / logging ------------------------------------------------------

VERBOSITY_LEVEL: Final[str] = "click_extra.verbosity_level"
"""The reconciled :class:`~click_extra.logging.LogLevel` chosen for the run.

Written by :meth:`click_extra.logging.ExtraVerbosity.set_level`, which
arbitrates between every verbosity-related option (``--verbosity``,
``--verbose``/``-v``) and keeps the highest pick. Read by the same callback
to detect prior writes from sibling options.
"""

VERBOSITY: Final[str] = "click_extra.verbosity"
"""Raw value of ``--verbosity LEVEL`` as the user passed it.

Written by :meth:`click_extra.logging.VerbosityOption.set_level`. Stored
alongside :data:`VERBOSITY_LEVEL` so downstream code can tell whether the
final level came from ``--verbosity`` or from ``-v`` repetitions.
"""

VERBOSE: Final[str] = "click_extra.verbose"
"""Raw repetition count of ``--verbose``/``-v``.

Written by :meth:`click_extra.logging.VerboseOption.set_level`. Same role
as :data:`VERBOSITY` for the ``-v`` family of flags.
"""


# --- Timing -------------------------------------------------------------------

START_TIME: Final[str] = "click_extra.start_time"
"""``time.perf_counter()`` snapshot taken when ``--time`` is enabled.

Written by :class:`click_extra.timer.TimerOption.register_timer_on_close`.
"""


# --- Parallelism --------------------------------------------------------------

JOBS: Final[str] = "click_extra.jobs"
"""Effective parallel job count after clamping (always >= 1).

Written by :class:`click_extra.jobs.JobsOption.validate_jobs`. Click Extra
itself does not act on this value: it is a contract for downstream commands
that drive their own concurrency.
"""


# --- Table rendering ----------------------------------------------------------

TABLE_FORMAT: Final[str] = "click_extra.table_format"
"""The :class:`~click_extra.table.TableFormat` chosen via ``--table-format``.

Written by :class:`click_extra.table.TableFormatOption.init_formatter`. Read
by :class:`click_extra.table.SortByOption` to thread the same format through
``ctx.print_table``.
"""

SORT_BY: Final[str] = "click_extra.sort_by"
"""Tuple of column IDs picked via ``--sort-by`` (in priority order).

Written by :class:`click_extra.table.SortByOption.init_sort`.
"""


# --- Theming ------------------------------------------------------------------

THEME: Final[str] = "click_extra.theme.active"
"""The :class:`~click_extra.theme.HelpExtraTheme` active for this invocation.

Written by :class:`click_extra.theme.ThemeOption.set_theme`. Read via
:func:`click_extra.theme.get_current_theme`, which falls back to
``click_extra.theme.default_theme`` when no key is set.
"""


# --- Helpers ------------------------------------------------------------------


def get(ctx: click.Context, key: str, default: Any = None) -> Any:
    """Read ``key`` from the current context's shared ``meta`` dict.

    Equivalent to ``ctx.meta.get(key, default)``. Click's ``meta`` is shared
    across the parent/child hierarchy, so reading from the local context is
    sufficient: there is no need to walk up to the root manually.
    """
    return ctx.meta.get(key, default)


def set(
    ctx: click.Context,
    key: str,
    value: Any,
) -> None:
    """Write ``value`` under ``key`` in the current context's shared ``meta`` dict.

    Equivalent to ``ctx.meta[key] = value``. Provided as the symmetric writer
    for :func:`get` so that callers can route both sides of a ``meta`` access
    through this module.
    """
    ctx.meta[key] = value
