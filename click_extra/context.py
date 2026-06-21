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
"""Click context plumbing: the :class:`Context` subclass plus the central
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

import functools
import os
from typing import Any, ParamSpec, TypeVar, cast

import click
import cloup

from .colorize import resolve_color_env
from .highlight import HelpFormatter

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Concatenate, Final

P = ParamSpec("P")
R = TypeVar("R")


POSIXLY_CORRECT_ENVVAR: Final[str] = "POSIXLY_CORRECT"
"""Environment variable that requests strict POSIX argument parsing.

When this variable is present in the environment (regardless of its value,
matching GNU ``getopt`` semantics), :class:`Context` forces
``allow_interspersed_args`` to ``False`` so option parsing stops at the first
positional argument.
"""


class Context(cloup.Context):
    """Like ``cloup._context.Context``, but with the ability to populate the context's
    ``meta`` property at instantiation.

    Also defaults ``color`` to ``True`` for root contexts (i.e. without a parent), so
    help screens are always colorized — even when piped. Click's own default is ``None``
    (auto-detect via TTY), which strips colors in non-interactive contexts.

    Parent-to-child color inheritance is handled by Click itself at ``Context.__init__``
    time, so no property override is needed.

    When the ``POSIXLY_CORRECT`` environment variable is set, this context forces
    ``allow_interspersed_args`` to ``False`` so option parsing stops at the first
    positional argument, as GNU getopt-based tools do. See
    :data:`POSIXLY_CORRECT_ENVVAR`.

    .. todo::
        Propose addition of ``meta`` keyword upstream to Click.
    """

    formatter_class = HelpFormatter
    """Use our own formatter to colorize the help screen."""

    def __init__(self, *args, meta: dict[str, Any] | None = None, **kwargs) -> None:
        """Like parent's context but with an extra ``meta`` keyword-argument.

        Also pre-seed ``color`` from the color environment variables for a parentless
        context when the user did not provide it, and force
        ``allow_interspersed_args`` to ``False`` when ``POSIXLY_CORRECT`` is set in the
        environment.
        """
        super().__init__(*args, **kwargs)

        # Click defaults root ``ctx.color`` to ``None`` (GNU ``auto``: keep ANSI on a
        # TTY, strip it when piped). For a parentless context, pre-seed it from the
        # color environment variables so the eager help and version screens — which
        # can render before ``--color`` resolves — still honor ``FORCE_COLOR`` /
        # ``NO_COLOR``. With no recognized variable the value stays ``None`` (auto),
        # and the ``ColorOption`` callback later layers the command line, configuration
        # and ``--accessible`` on top.
        if not self.parent and self.color is None:
            self.color = resolve_color_env()

        # Honor the POSIX conformance switch: when POSIXLY_CORRECT is present in the
        # environment, stop parsing options at the first positional argument, the way
        # GNU getopt-based tools do. Presence alone is enough, regardless of value.
        # This can only tighten parsing (True -> False), never loosen it.
        if POSIXLY_CORRECT_ENVVAR in os.environ:
            self.allow_interspersed_args = False

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
"""The raw, pre-parsed ``argv`` slice fed to the current command.

Written by :class:`click_extra.commands.Command.make_context` so that
:class:`click_extra.parameters.ShowParamsOption` can re-parse the original
arguments for the ``--show-params`` table without re-running the callbacks.
Consumers normalize the parser's ``UNSET`` sentinel back to ``None`` on read,
matching what ``click.Command.parse_args`` does for ``ctx.params``.
"""

# Developer note: why RAW_ARGS exists, and what to actually propose upstream.
#
# What --show-params needs is the *forward* resolution: for every parameter, the
# value it resolves to and its provenance (ParameterSource), computable at an
# arbitrary moment. Click does not expose this:
#   - The parsed command-line values (`opts`) are a local in
#     `click.Command.parse_args`, discarded when it returns. They are never
#     stored on the Context, despite the convenience of pretending otherwise.
#   - --show-params is eager, so its callback fires mid-processing, before the
#     non-eager parameters land in `ctx.params`. Reading `ctx.params` there would
#     see a partial picture.
#
# Workaround: Command/Group.make_context stashes a copy of the raw
# argv under RAW_ARGS; parameters.render_params_table rebuilds the parser,
# re-parses those args to recover `opts`, and calls `consume_value()` (not
# `handle_parse_result()`) per parameter so eager callbacks are not re-fired.
# The same re-parse backs `click-extra wrap --show-params`, which introspects a
# foreign CLI that is never actually executed (no live parse to borrow from).
#
# Fragilities to keep in mind:
#   - The re-parse replays the parser but skips Click's post-parse cleanup, so it
#     drifts whenever that cleanup changes. Click 8.4 introduced the UNSET
#     sentinel (returned for parameters with no default); parse_args rewrites it
#     to None, the re-parse did not, and the sentinel leaked into the value and
#     default columns. It is now normalized back to None at the consumer sites
#     (render_params_table and format_param_row).
#   - It depends on `Command.make_parser()` handing back
#     `click.parser._OptionParser`, private since the Click 8.2 parser rework.
#
# Upstream proposal (revisit later: tracked in docs/upstream.md under
# "Normalized arguments", linked to click#1279). Three different features get
# muddled under the "raw_args" label:
#   1. Preserve the raw input argv on the Context. Trivial; what we do here.
#   2. Expose the parsed `opts`, or better, a per-parameter resolved
#      (value, ParameterSource), on the Context. Modest; this is what
#      --show-params actually consumes.
#   3. Reconstruct a *normalized* argv from a Context (the inverse direction).
#      Hard and underdefined; this is click#1279.
# click#1279 was filed for pip-tools and is feature 3: davidism scoped it with
# ~a dozen normalization rules (option ordering, prompt/env inclusion, default
# exclusion, ambiguous file paths) and flagged it underdefined; it has stalled
# since 2023. click-extra needs feature 2, the easier forward direction, so the
# right move is a new, narrowly-scoped issue/PR for a public Context accessor
# returning a parameter's resolved (value, ParameterSource) after parsing
# without re-firing eager callbacks, referencing click#1279 as related, not home.
#
# Note: "just reuse the `opts` lying around" does not work as stated. `opts` is
# not on the Context; capturing it means reimplementing parse_args or wrapping
# make_parser, it would still need the UNSET normalization above, and it would
# not help the foreign-CLI wrap path, which has no live parse to capture from.


# --- Configuration loading ----------------------------------------------------

CONF_SOURCE: Final[str] = "click_extra.conf_source"
"""Resolved path or URL of the configuration file that was loaded.

Written by :class:`click_extra.config.option.ConfigOption.load_conf` after a
configuration file is found and parsed. ``None`` if no file matched.
"""

CONF_FULL: Final[str] = "click_extra.conf_full"
"""Full parsed configuration document (the whole file, every section).

Written by :class:`click_extra.config.option.ConfigOption.load_conf`. Read by
:class:`click_extra.commands.Group` (for subcommand inheritance) and by
:func:`click_extra.cli_wrapper.invoke_target` (to forward the loaded config to
wrapped CLIs).
"""

TOOL_CONFIG: Final[str] = "click_extra.tool_config"
"""The app-specific config section, deserialised through ``config_schema``.

Written by :class:`~click_extra.config.option.ConfigOption`'s
``_apply_config_schema`` method only when a schema callable is configured. Read via
:func:`click_extra.config.schema.get_tool_config`.
"""


# --- Verbosity / logging ------------------------------------------------------

VERBOSITY_LEVEL: Final[str] = "click_extra.verbosity_level"
"""The reconciled :class:`~click_extra.logging.LogLevel` chosen for the run.

Written by :meth:`click_extra.logging._VerbosityOption.apply_verbosity`, which
reconciles every verbosity-related option (``--verbosity``, ``--verbose``/``-v``
and ``--quiet``/``-q``) into a single level. Read by the same method to detect
whether the reconciled level changed since a sibling option last fired.
"""

VERBOSITY: Final[str] = "click_extra.verbosity"
"""Raw value of ``--verbosity LEVEL`` as the user passed it.

Written by :meth:`click_extra.logging.VerbosityOption.set_level`. Stored
alongside :data:`VERBOSITY_LEVEL` so downstream code can tell whether the
final level came from ``--verbosity`` or from ``-v``/``-q`` repetitions.
"""

VERBOSE: Final[str] = "click_extra.verbose"
"""Raw repetition count of ``--verbose``/``-v``.

Written by :meth:`click_extra.logging.VerboseOption.set_level`. Combined with
:data:`QUIET` into the signed ``verbose - quiet`` counter that
:meth:`click_extra.logging._VerbosityOption.resolve_level` shifts the base level by.
"""

QUIET: Final[str] = "click_extra.quiet"
"""Raw repetition count of ``--quiet``/``-q``.

Written by :meth:`click_extra.logging.QuietOption.set_level`. The quiet
counterpart of :data:`VERBOSE`: each ``-q`` subtracts one step from the
``verbose - quiet`` net applied on top of the base verbosity level.
"""


# --- Timing -------------------------------------------------------------------

START_TIME: Final[str] = "click_extra.start_time"
"""``time.perf_counter()`` snapshot taken when ``--time`` is enabled.

Written by :class:`click_extra.execution.TimerOption.init_timer`.
"""


# --- Parallelism --------------------------------------------------------------

JOBS: Final[str] = "click_extra.jobs"
"""Effective parallel job count after clamping (always >= 1).

Written by :class:`click_extra.execution.JobsOption.validate_jobs`. Click Extra
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

COLUMNS: Final[str] = "click_extra.columns"
"""Tuple of column IDs selected via ``--columns`` (in display order).

Written by :class:`click_extra.table.ColumnsOption.init_columns`. Read by
table-rendering consumers (like :class:`click_extra.parameters.ShowParamsOption`)
to project and reorder columns before emitting the table. Empty / unset means
no projection: render every column in its canonical order.
"""


# --- Theming ------------------------------------------------------------------

THEME: Final[str] = "click_extra.theme.active"
"""The :class:`~click_extra.theme.HelpTheme` active for this invocation.

Written by :class:`click_extra.theme.ThemeOption.set_theme`. Read via
:func:`click_extra.theme.get_current_theme`, which falls back to
``click_extra.theme.default_theme`` when no key is set.
"""

THEME_OVERRIDES: Final[str] = "click_extra.theme.overrides"
"""Per-invocation theme registry overlay loaded from the user's config file.

Written by :class:`click_extra.config.option.ConfigOption` when it sees
``[tool.<cli>.themes.<name>]`` tables: each table is built into a
:class:`~click_extra.theme.HelpTheme` (cascading on top of an existing
theme when *name* matches one already in :data:`~click_extra.theme.theme_registry`).
Read by :func:`click_extra.theme.get_theme_registry` so ``--theme`` can pick
the new themes without leaking them into sibling invocations sharing the
same process.
"""


# --- Telemetry ----------------------------------------------------------------

TELEMETRY: Final[str] = "click_extra.telemetry"
"""``True`` if the user opted into telemetry, ``False`` otherwise.

Written by :class:`click_extra.telemetry.TelemetryOption.set_telemetry` after
reconciling ``--telemetry`` / ``--no-telemetry`` with the standard
``DO_NOT_TRACK`` environment variable. Downstream code reads this to decide
whether to emit usage data.
"""


# --- Progress -----------------------------------------------------------------

PROGRESS: Final[str] = "click_extra.progress"
"""``True`` when the CLI may display progress spinners, ``False`` otherwise.

Written by :class:`click_extra.spinner.ProgressOption.set_progress` from the
``--progress`` / ``--no-progress`` flag (which ``--accessible`` lowers to
``False``). Downstream code reads it to decide whether to start a
:class:`~click_extra.spinner.Spinner`.

Deliberately independent of color: a spinner is an interactivity concern, so it is
gated on the terminal (TTY / ``TERM=dumb``, handled by the spinner) and on explicit
intent (``--no-progress`` / ``--accessible``), never on ``--no-color`` /
``NO_COLOR``. See :class:`~click_extra.spinner.ProgressOption` for the rationale.
"""


# --- Accessibility ------------------------------------------------------------

ACCESSIBLE: Final[str] = "click_extra.accessible"
"""``True`` when the user requested screen-reader-friendly output.

Written by :class:`click_extra.accessibility.AccessibleOption.set_accessible`
after reconciling the ``--accessible`` flag with the ``ACCESSIBLE`` environment
variable. Read by output helpers that must degrade a cursor-driven element to a
linear stream: :func:`click_extra.accessibility.clear` becomes a no-op and
:func:`click_extra.accessibility.echo_via_pager` writes its text straight to
stdout instead of spawning a pager.

This is the *readable* counterpart to the ``--color`` / ``--progress`` /
``--table-format`` defaults that ``--accessible`` also lowers: those are consumed
through their own resolved values (``ctx.color``, :data:`PROGRESS`, the table
format), while this flag exposes the accessibility intent itself.
"""


# --- Exit code ----------------------------------------------------------------

ZERO_EXIT: Final[str] = "click_extra.zero_exit"
"""``True`` when the user asked the CLI to always return a zero exit code.

Written by :class:`click_extra.execution.ZeroExitOption.set_zero_exit`. Click
Extra itself does not act on this value: it is a contract for downstream
commands that suppress their non-zero "problems found" exit code and return
``0`` as long as the run itself succeeded.
"""


# --- Helpers ------------------------------------------------------------------


def pass_context(func: Callable[Concatenate[Context, P], R]) -> Callable[P, R]:
    """Mark a callback as wanting the active :class:`Context` as its first argument.

    Click's own :func:`click.pass_context` is typed for the base
    :class:`click.Context`. A handler annotated with click-extra's enhanced
    :class:`Context` (to reach its extra helpers like ``ctx.print_table``)
    therefore fails static type checking: function parameters are contravariant,
    so ``Callable[[Context], R]`` is not assignable where a
    ``Callable[[click.Context], R]`` is expected.

    This drop-in is typed for the enhanced :class:`Context` and still accepts
    handlers typed for the base ``click.Context`` (a wider first parameter is
    allowed), so both type-check. At runtime it forwards the active context
    unchanged, exactly like :func:`click.pass_context`.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(cast(Context, click.get_current_context()), *args, **kwargs)

    return wrapper


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
