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
"""Click context plumbing: the central registry of every `ctx.meta` key Click
Extra writes or reads.

The {class}`~click_extra.commands.Context` subclass lives in
{mod}`click_extra.commands`, beside the commands that create it.

Click's {attr}`click.Context.meta` is a per-invocation dict that Click shares
across the parent/child context hierarchy. Click Extra uses it to pass
per-invocation state (the picked theme, the resolved table format, the loaded
configuration, etc.) between eager callbacks and the rest of the CLI without
mutating module-level globals. Per-invocation context storage is what keeps
back-to-back invocations of the same CLI (Sphinx builds, test runners, REPLs)
from leaking state into each other.

This module is part of Click Extra's **public API**. Inside any
`@command`- or `@group`-decorated function, request the active context
with {func}`click.pass_context` (or call {func}`click.get_current_context`)
and read the entries you need:

```{code-block} python

from click_extra import command, context, echo, pass_context


@command
@pass_context
def cli(ctx):
    echo(f"Theme: {ctx.meta[context.THEME]}")
    echo(f"Jobs:  {ctx.meta[context.JOBS]}")
```

Each constant below documents who writes the entry, when, and what shape the
value takes. The raw string values are stable and downstream code may also
read `ctx.meta["click_extra.<field>"]` directly: the constants exist so
internal call sites and downstream code can converge on a single spelling.
"""

from __future__ import annotations

import weakref
from collections.abc import ItemsView, KeysView, ValuesView
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import cast

import click

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator
    from typing import Any, Concatenate, Final, ParamSpec, TypeVar

    from .commands import Context

    P = ParamSpec("P")
    R = TypeVar("R")


_RUN_CLEANUPS: ContextVar[list[Callable[[], None]] | None] = ContextVar(
    "_RUN_CLEANUPS", default=None
)
"""What the runs started within the `_scoped_run` block in progress may leave.

One callable for each piece of process-wide state a run took: its hold on the
handler of the `root` logger, the log levels it set, the color it published.
`None` outside such a block. Written by `_queue_run_cleanup`.
"""


def _queue_run_cleanup(ctx: click.Context, cleanup: Callable[[], None]) -> None:
    """Have `cleanup` called for the run of `ctx`, even when Click never closes it.

    A run that fails while parsing leaves its context never entered, and therefore
    never closed: its close callbacks do not run. Two mechanisms cover that path:

    - A finalizer, called when Python collects the context. That may be late, and
      in the middle of a later run.
    - The `_scoped_run` block {meth}`click_extra.commands.Command.main` runs
      within, which does not wait for a collection.

    Both also call `cleanup` for a context that did close. It so has to do nothing
    when called again, and to leave alone what a later run took over. The options
    taking process-wide state queue their cleanup here beside the close callback
    they register for the normal path: see `click_extra.logging` and
    {func}`click_extra.color.publish_invocation_color`.
    """
    weakref.finalize(ctx, cleanup)
    cleanups = _RUN_CLEANUPS.get()
    if cleanups is not None:
        cleanups.append(cleanup)


@contextmanager
def _scoped_run() -> Generator[None, None, None]:
    """Give back on exit the process-wide state of the runs started within the block.

    {meth}`click_extra.commands.Command.main` runs within it. A run that fails
    while parsing so gives back the handler of the `root` logger, resets the
    levels of its loggers and clears the color it published, without waiting for
    a garbage collection. What the run around the block took stays: that run
    gives it back when it ends.
    """
    cleanups: list[Callable[[], None]] = []
    reset_token = _RUN_CLEANUPS.set(cleanups)
    try:
        yield
    finally:
        _RUN_CLEANUPS.reset(reset_token)
        for cleanup in cleanups:
            cleanup()


META_NAMESPACE: Final[str] = "click_extra."
"""Prefix shared by every `ctx.meta` key Click Extra writes.

Reserved for entries the framework owns. Downstream consumers picking their
own `ctx.meta` keys are encouraged to use a different prefix to avoid
colliding with current or future Click Extra entries.
"""


# A real dict, not a UserDict: Click types `ctx._meta` as one and reads it directly.
class _LazyMetaDict(dict):  # noqa: FURB189
    """Dict subclass that lazily resolves fields on first access.

    Installed as `ctx._meta` so that `ctx.meta["click_extra.<field>"]`
    transparently evaluates the corresponding `@cached_property` on the
    source object only when the key is actually read.

    A lazy key belongs to the mapping before it resolves: `in`, `len()`,
    iteration and `keys()` count it without resolving it. What reads its value
    resolves it: indexing, `get()`, `items()`, `values()`, `pop()`,
    `setdefault()` and equality. A deleted lazy key stays deleted.
    """

    def __init__(
        self,
        base: dict[str, Any],
        source: object,
        fields: tuple[str, ...],
    ) -> None:
        # Copy only the entries `base` stores, so a lazy `base` keeps its pending
        # keys unresolved: each `--version` option of a command tree wraps
        # `ctx.meta` again.
        super().__init__(dict.items(base))
        self._source = source
        self._lazy_keys = {f"{META_NAMESPACE}{f}": f for f in fields}

    def _pending(self) -> list[str]:
        """The lazy keys not resolved yet, in the order they were declared."""
        stored = dict.keys(self)
        return [key for key in self._lazy_keys if key not in stored]

    def _resolve(self, key: str) -> Any:
        """Resolve a lazy key, cache the result, and return it."""
        value = getattr(self._source, self._lazy_keys[key])
        # Store as a regular entry so subsequent reads are plain dict lookups.
        self[key] = value
        return value

    def __getitem__(self, key: str) -> Any:
        # The dict's own test, since `__contains__` below claims every lazy key.
        if key in self._lazy_keys and not super().__contains__(key):
            return self._resolve(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        return key in self._lazy_keys or super().__contains__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._lazy_keys:
            return self[key]
        return super().get(key, default)

    def __iter__(self) -> Iterator[str]:
        """Iterate the stored keys, then the pending ones."""
        yield from super().__iter__()
        yield from self._pending()

    def __reversed__(self) -> Iterator[str]:
        yield from reversed(self._pending())
        yield from super().__reversed__()

    def __len__(self) -> int:
        return super().__len__() + len(self._pending())

    # Views over the mapping itself rather than over the stored entries, so they
    # list the pending keys too.
    def keys(self) -> KeysView[str]:  # type: ignore[override]
        return KeysView(self)

    def values(self) -> ValuesView[Any]:  # type: ignore[override]
        return ValuesView(self)

    def items(self) -> ItemsView[str, Any]:  # type: ignore[override]
        return ItemsView(self)

    def __eq__(self, other: object) -> bool:
        return dict(self.items()) == other

    def __ne__(self, other: object) -> bool:
        return not self == other

    def __delitem__(self, key: str) -> None:
        # A pending key has no stored entry: forgetting it is enough.
        if self._lazy_keys.pop(key, None) is None or super().__contains__(key):
            super().__delitem__(key)

    def pop(self, key: str, *default: Any) -> Any:
        if key in self._lazy_keys:
            value = self[key]
            del self[key]
            return value
        return super().pop(key, *default)

    def popitem(self) -> tuple[str, Any]:
        """Remove and return the last pair, in the order of iteration."""
        pending = self._pending()
        if pending:
            return pending[-1], self.pop(pending[-1])
        key, value = super().popitem()
        self._lazy_keys.pop(key, None)
        return key, value

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key in self._lazy_keys:
            return self[key]
        return super().setdefault(key, default)

    def clear(self) -> None:
        self._lazy_keys.clear()
        super().clear()

    def copy(self) -> _LazyMetaDict:
        """A shallow copy, whose pending keys stay pending."""
        return _LazyMetaDict(self, self._source, tuple(self._lazy_keys.values()))


# --- Argument capture ---------------------------------------------------------

RAW_ARGS: Final[str] = "click_extra.raw_args"
"""The raw, pre-parsed `argv` slice fed to the current command.

Written by {class}`click_extra.commands.Command.make_context` so that
{class}`click_extra.show_params.ShowParamsOption` can re-parse the original
arguments for the `--params` table without re-running the callbacks.
Consumers normalize the parser's `UNSET` sentinel back to `None` on read,
matching what `click.Command.parse_args` does for `ctx.params`.

```{todo}
Open a narrowly-scoped Click issue and PR for a public
{class}`click.Context` accessor returning a parameter's resolved
`(value, ParameterSource)` after parsing, without re-firing eager callbacks.
That is the forward resolution a live CLI needs: landing it retires the replay
behind the `--params` table and the configuration dump. The
`click-extra wrap --params` path keeps this constant and its replay, because
Click never parses the foreign CLI it renders.

Reference [`pallets/click#1279`](https://github.com/pallets/click/issues/1279)
as related, not as home: it asks for the inverse direction (reconstructing a
normalized argv from a Context), was scoped with about a dozen normalization
rules, flagged underdefined, and has stalled since 2023. Tracked in
`docs/upstream.md` under "Normalized arguments"; the developer note below
records why the cheaper alternatives do not work.
```
"""

# Developer note: why RAW_ARGS exists, and what to actually propose upstream.
#
# What --params needs is the *forward* resolution: for every parameter, the
# value it resolves to and its provenance (ParameterSource), computable at an
# arbitrary moment. Click does not expose this:
#   - The parsed command-line values (`opts`) are a local in
#     `click.Command.parse_args`, discarded when it returns. They are never
#     stored on the Context, despite the convenience of pretending otherwise.
#   - --params is eager, so its callback fires mid-processing, before the
#     non-eager parameters land in `ctx.params`. Reading `ctx.params` there would
#     see a partial picture.
#
# Workaround: Command.make_context stashes a copy of the raw argv under
# RAW_ARGS; show_params.render_params_table rebuilds the parser, re-parses those
# args to recover `opts`, and calls `consume_value()` (not
# `handle_parse_result()`) per parameter so eager callbacks are not re-fired.
# The same re-parse backs `click-extra wrap --params`, which introspects a
# foreign CLI that is never actually executed (no live parse to borrow from).
#
# Fragilities to keep in mind:
#   - The re-parse replays the parser but skips Click's post-parse cleanup, so it
#     drifts whenever that cleanup changes. `parse_args` rewrites the UNSET
#     sentinel of a parameter with no default to None and the re-parse does not,
#     so the consumer sites (render_params_table and _format_param_row) normalize
#     it back to None.
#   - It depends on `Command.make_parser()` handing back the private
#     `click.parser._OptionParser`.
#
# Upstream proposal (the actionable half is the `{todo}` on RAW_ARGS above).
# Three different features get muddled under the "raw_args" label:
#   1. Preserve the raw input argv on the Context. Trivial; what RAW_ARGS does.
#   2. Expose the parsed `opts`, or better, a per-parameter resolved
#      (value, ParameterSource), on the Context. Modest; this is what
#      --params actually consumes.
#   3. Reconstruct a *normalized* argv from a Context (the inverse direction).
#      Hard and underdefined; this is click#1279.
#
# Reusing the `opts` lying around does not work: `opts` is not on the Context,
# capturing it means reimplementing parse_args or wrapping make_parser, it would
# still need the UNSET normalization above, and it would not help the
# foreign-CLI wrap path, which has no live parse to capture from.


# --- Invocation name ----------------------------------------------------------

INVOCATION_NAME: Final[str] = "click_extra.invocation_name"
"""The name the CLI was invoked under, as resolved on the root context.

Written by {class}`click_extra.commands.Command.make_context` on the root
context only (`ctx.meta` is shared down the whole hierarchy, so a subcommand
must not overwrite it). Equals Click's root `info_name`: the entry-point
script name, the symlink name in {mod}`~click_extra.multicall` personality
mode, or an explicit `prog_name` override passed to `main()`. Read it with
{func}`click.pass_context` to implement invocation-name-aware behavior
without the full multicall machinery:

```{code-block} python
if ctx.meta[context.INVOCATION_NAME] == "bunzip2":
    ...
```
"""


# --- Configuration loading ----------------------------------------------------

CONF_SOURCE: Final[str] = "click_extra.conf_source"
"""Resolved path or URL of the configuration file that was loaded.

Written by {class}`click_extra.config.option.ConfigOption.load_conf` after a
configuration file is found and parsed. `None` if no file matched.
"""

CONF_FULL: Final[str] = "click_extra.conf_full"
"""Full parsed configuration document (the whole file, every section).

Written by {class}`click_extra.config.option.ConfigOption.load_conf`. Read by
{class}`click_extra.commands.Group` (for subcommand inheritance) and by
{func}`click_extra.cli_wrapper.invoke_target` (to forward the loaded config to
wrapped CLIs).

With `cascade=True` this holds the deep-merged view of every loaded file,
which is the configuration as it was actually applied.
"""

CONF_SOURCES: Final[str] = "click_extra.conf_sources"
"""Every configuration file loaded, in precedence order (highest first).

Written by {class}`click_extra.config.option.ConfigOption.load_conf` as a
(possibly empty) tuple of `(location, parsed_conf)` pairs. Holds a single
entry in the default first-file-wins mode, and one entry per loaded file
when `cascade=True`.
"""

TOOL_CONFIG: Final[str] = "click_extra.tool_config"
"""The app-specific config section, deserialized through `config_schema`.

Written by {meth}`~click_extra.config.option.ConfigOption.load_conf` when a
`config_schema` is set. Read via
{func}`click_extra.config.schema.get_tool_config`.
"""

SUBCOMMANDS_APPLIED: Final[str] = "click_extra.subcommands_applied"
"""Command paths whose reserved subcommand keys were already spliced in.

Written by {func}`click_extra.config.subcommands.inject_reserved_subcommands` as a
growing set of `ctx.command_path` strings. This `meta` dict is shared by the whole
context tree, so the set is what tells one group's injection from another's, and
what keeps a second pass over the same group from prepending its
`_prepend_subcommands` twice.
"""


# --- Verbosity / logging ------------------------------------------------------

VERBOSITY_LEVEL: Final[str] = "click_extra.verbosity_level"
"""The reconciled {class}`~click_extra.logging.LogLevel` chosen for the run.

Written by `_VerbosityOption.apply_verbosity`, which
reconciles every verbosity-related option (`--verbosity`, `--verbose`/`-v`
and `--quiet`/`-q`) into a single level. Read by the same method to detect
whether the reconciled level changed since a sibling option last fired.
"""

VERBOSITY: Final[str] = "click_extra.verbosity"
"""Raw value of `--verbosity LEVEL` as the user passed it.

Written by {meth}`click_extra.logging.VerbosityOption.set_level`. Stored
alongside {data}`VERBOSITY_LEVEL` so downstream code can tell whether the
final level came from `--verbosity` or from `-v`/`-q` repetitions.
"""

DEBUG: Final[str] = "click_extra.debug"
"""Whether `--debug` was passed.

Written by the `set_level` callback of {class}`click_extra.logging.DebugOption`.
Read by `_VerbosityOption.resolve_level`, which answers it before anything else:
`--debug` names the loudest level there is, so nothing another option asks for
can outrank it.
"""

VERBOSE: Final[str] = "click_extra.verbose"
"""Raw repetition count of `--verbose`/`-v`.

Written by the `set_level` callback of {class}`click_extra.logging.VerboseOption`.
Combined with {data}`QUIET` into the signed `verbose - quiet` counter that
`_VerbosityOption.resolve_level` shifts the base level by.
"""

QUIET: Final[str] = "click_extra.quiet"
"""Raw repetition count of `--quiet`/`-q`.

Written by the `set_level` callback of {class}`click_extra.logging.QuietOption`.
The quiet counterpart of {data}`VERBOSE`: each `-q` subtracts one step from the
`verbose - quiet` net applied on top of the base verbosity level.
"""


# --- Timing -------------------------------------------------------------------

START_TIME: Final[str] = "click_extra.start_time"
"""`time.perf_counter()` snapshot taken when `--time` is enabled.

Written by {class}`click_extra.execution.TimerOption.init_timer`.
"""


# --- Parallelism --------------------------------------------------------------

JOBS: Final[str] = "click_extra.jobs"
"""Effective parallel job count after clamping (always >= 1).

Written by {class}`click_extra.jobs.JobsOption.validate_jobs`. Click Extra
itself does not act on this value: it is a contract for downstream commands
that drive their own concurrency.
"""


# --- Table rendering ----------------------------------------------------------

TABLE_FORMAT: Final[str] = "click_extra.table_format"
"""The {class}`~click_extra.table.TableFormat` chosen via `--table-format`.

Written by {class}`click_extra.table_options.TableFormatOption.init_formatter`.
Read by {meth}`~click_extra.commands.Context.render_table` and
{meth}`~click_extra.commands.Context.print_table` as their default format.
"""

SORT_BY: Final[str] = "click_extra.sort_by"
"""Tuple of column IDs picked via `--sort-by` (in priority order).

Written by {class}`click_extra.table_options.SortByOption.init_sort`.
"""

TABLE_SORT_KEY: Final[str] = "click_extra.table_sort_key"
"""Row sort key derived from the `--sort-by` selection.

Written by {class}`click_extra.table_options.SortByOption.init_sort` when its
column definitions are known at declaration time (labeled mode). Read by
{meth}`~click_extra.commands.Context.render_table` and
{meth}`~click_extra.commands.Context.print_table` as their default `sort_key`.
Absent in field-vocabulary mode, where the sort is resolved per table by
{func}`click_extra.table.print_table` from the column IDs its headers carry.
"""

COLUMNS: Final[str] = "click_extra.columns"
"""Tuple of column IDs selected via `--columns` (in display order).

Written by {class}`click_extra.table_options.ColumnsOption.init_columns`. Read by
table-rendering consumers (like {class}`click_extra.show_params.ShowParamsOption`)
to project and reorder columns before emitting the table. Empty / unset means
no projection: render every column in its canonical order.
"""


# --- Theming ------------------------------------------------------------------

THEME: Final[str] = "click_extra.theme.active"
"""The {class}`~click_extra.theme.HelpTheme` active for this invocation.

Written by {class}`click_extra.theme.ThemeOption.set_theme`. Read via
{func}`click_extra.theme.get_current_theme`, which falls back to
`click_extra.theme.default_theme` when no key is set.
"""

THEME_OVERRIDES: Final[str] = "click_extra.theme.overrides"
"""Per-invocation theme registry overlay loaded from the user's config file.

Written by {class}`click_extra.config.option.ConfigOption` when it sees
`[tool.<cli>.themes.<name>]` tables: each table is built into a
{class}`~click_extra.theme.HelpTheme` (cascading on top of an existing
theme when *name* matches one already in {data}`~click_extra.theme.theme_registry`).
Read by {func}`click_extra.theme.get_theme_registry` so `--theme` can pick
the new themes without leaking them into sibling invocations sharing the
same process.
"""


# --- Telemetry ----------------------------------------------------------------

TELEMETRY: Final[str] = "click_extra.telemetry"
"""`True` if the user opted into telemetry, `False` otherwise.

Written by {class}`click_extra.telemetry.TelemetryOption.set_telemetry` after
reconciling `--telemetry` / `--no-telemetry` with the standard
`DO_NOT_TRACK` environment variable. Downstream code reads this to decide
whether to emit usage data.
"""


# --- Progress -----------------------------------------------------------------

PROGRESS: Final[str] = "click_extra.progress"
"""`True` when the CLI may display progress spinners, `False` otherwise.

Written by {class}`click_extra.spinner.ProgressOption.set_progress` from the
`--progress` / `--no-progress` flag (which `--accessible` lowers to
`False`). {class}`~click_extra.spinner.Spinner`,
{class}`~click_extra.trail.OperationTrail` and
{func}`~click_extra.progress.progressbar` read it on their own when left at
their automatic default.

Deliberately independent of color: a spinner is an interactivity concern, so it is
gated on the terminal (TTY / `TERM=dumb`, handled by the spinner) and on explicit
intent (`--no-progress` / `--accessible`), never on `--no-color` /
`NO_COLOR`. See {class}`~click_extra.spinner.ProgressOption` for the rationale.
"""


# --- Accessibility ------------------------------------------------------------

ACCESSIBLE: Final[str] = "click_extra.accessible"
"""`True` when the user requested screen-reader-friendly output.

Written by {meth}`~click_extra.AccessibleOption.set_accessible`
after reconciling the `--accessible` flag with the `ACCESSIBLE` environment
variable. Read by output helpers that must degrade a cursor-driven element to a
linear stream: {func}`~click_extra.clear` becomes a no-op and
{func}`~click_extra.echo_via_pager` writes its text straight to
stdout instead of spawning a pager.

This is the *readable* counterpart to the `--color` / `--progress` /
`--table-format` defaults that `--accessible` also lowers: those are consumed
through their own resolved values (`ctx.color`, {data}`PROGRESS`, the table
format), while this flag exposes the accessibility intent itself.
"""


# --- Exit code ----------------------------------------------------------------

ZERO_EXIT: Final[str] = "click_extra.zero_exit"
"""`True` when the user asked the CLI to always return a zero exit code.

Written by {class}`click_extra.execution.ZeroExitOption.set_zero_exit`. Click
Extra itself does not act on this value: it is a contract for downstream
commands that suppress their non-zero "problems found" exit code and return
`0` as long as the run itself succeeded.
"""


# --- Internal keys ------------------------------------------------------------
# Not part of the public API: one module writes and reads each of them. They live
# here, under the `click_extra._` prefix, so that this module spells every key
# Click Extra puts in `ctx.meta`.

_COLOR_CLI_OVERRIDE: Final[str] = "click_extra._color_cli_override"
"""Set when `--no-color` is passed on the command line.

Written by {meth}`click_extra.color.NoColorOption.set_no_color` and read by
{meth}`click_extra.color.ColorOption.set_color`, so the explicit negative alias
outranks the color environment variables, which may only override the built-in
default.
"""

_COLOR_PUBLISHED: Final[str] = "click_extra._color_published"
"""Set once the reset of the process-wide color mirror is queued.

Written by {func}`click_extra.color.publish_invocation_color`, which so registers
its reset callbacks at most once per invocation, however many color callbacks
fire.
"""

_CONFIG_PRELOADED: Final[str] = "click_extra._config_preloaded"
"""The command paths whose configuration was loaded ahead of time.

Filled by `ConfigOption._resolve_subcommands_eagerly`, which processes the option
before Click's parameter loop does. That loop then calls
{meth}`click_extra.config.option.ConfigOption.load_conf` again with the same value:
the call removes its entry and returns, in place of loading the document a second
time.
"""

_CONFIG_STATUS_SILENCED: Final[str] = "click_extra._config_status_silenced"
"""Whether the command line asks for less than `WARNING` output.

Set by {meth}`click_extra.config.option.ConfigOption.handle_parse_result` before
the configuration loads, and read by
{meth}`click_extra.config.option.ConfigOption.load_conf` to keep its status lines
quiet.
"""

_LOG_HANDLER_TOKEN: Final[str] = "click_extra._log_handler_token"
"""The token a run holds the log handler with.

`ctx.meta` is shared down the context hierarchy, so the options of a command and
of its subcommands find the same token there, and a run takes one hold however
many of them it carries. See `click_extra.logging._hold_invocation_handler`.
"""

_LOG_LEVEL_TOKEN: Final[str] = "click_extra._log_level_token"
"""The token a run owns its log levels with.

Set by the first verbosity option that applies a level, which also queues the
reset of the loggers. It lives in `ctx.meta` so the verbosity options queue that
reset at most once per invocation, even when several of them are passed. See
`click_extra.logging._level_owner`.
"""

_VERBOSITY_COUNTER_SCANNED: Final[str] = "click_extra._verbosity_counter_scanned"
"""Set once the `-v`/`-q` counter is resolved ahead of the verbosity options.

The first verbosity option reaching `_VerbosityOption.handle_parse_result` reads
the raw `--verbose`/`--quiet` repetition counts from the parsed `opts` and
stashes them on the context before any option applies a level. This way the
option that fires first already reconciles the full counter and never applies an
intermediate, louder level that a later `-q` would have to lower, which would
leak its `Set ... DEBUG` debug trace.
"""


# --- Helpers ------------------------------------------------------------------


def pass_context(func: Callable[Concatenate[Context, P], R]) -> Callable[P, R]:
    """Mark a callback as wanting the active {class}`~click_extra.commands.Context`
    as its first argument.

    Click's own {func}`click.pass_context` is typed for the base
    {class}`click.Context`. A handler annotated with click-extra's enhanced
    {class}`~click_extra.commands.Context` (to reach its extra helpers like
    `ctx.print_table`) therefore fails static type checking: function parameters
    are contravariant, so `Callable[[Context], R]` is not assignable where a
    `Callable[[click.Context], R]` is expected.

    This drop-in is typed for the enhanced {class}`~click_extra.commands.Context`
    and still accepts handlers typed for the base `click.Context` (a wider first
    parameter is allowed), so both type-check. At runtime it forwards the active
    context unchanged, exactly like {func}`click.pass_context`.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(cast("Context", click.get_current_context()), *args, **kwargs)

    return wrapper


def get(ctx: click.Context, key: str, default: Any = None) -> Any:
    """Read `key` from the current context's shared `meta` dict.

    Equivalent to `ctx.meta.get(key, default)`. Click's `meta` is shared
    across the parent/child hierarchy, so reading from the local context is
    sufficient: there is no need to walk up to the root manually.
    """
    return ctx.meta.get(key, default)


def set(
    ctx: click.Context,
    key: str,
    value: Any,
) -> None:
    """Write `value` under `key` in the current context's shared `meta` dict.

    Equivalent to `ctx.meta[key] = value`. Provided as the symmetric writer
    for {func}`get` so that callers can route both sides of a `meta` access
    through this module.
    """
    ctx.meta[key] = value


def setdefault(ctx: click.Context, key: str, factory: Callable[[], Any]) -> Any:
    """Read `key` from the shared `meta` dict, first storing `factory()` if missing.

    `factory` runs for a missing key only, so each invocation gets a mutable value
    of its own, like the set of command paths a run marks.
    """
    if key not in ctx.meta:
        ctx.meta[key] = factory()
    return ctx.meta[key]
