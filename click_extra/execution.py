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
"""Options and primitives controlling how CLIs run.

Two altitudes live here. The higher one governs the CLI *being authored*: the
pre-configured {class}`~click_extra.parameters.ExtraOption` subclasses
{class}`TimerOption` and {class}`ZeroExitOption` publish their resolved value on
`ctx.meta`. The `--jobs` option, and the fan-out primitives that parallelize
work per its count, are in {mod}`click_extra.jobs`.

The lower one runs *foreign* CLIs in subprocesses, for tools that wrap other
programs: {func}`run_cli` spawns one command, disclosing its invocation to the
logger and streaming its output live, while {func}`install_interrupt_handler`
and {func}`terminate_live_processes` make Ctrl+C abort in-flight children
cleanly. {func}`args_cleanup` and {func}`format_cli_prompt` are the shared
serialization and disclosure atoms both altitudes (and
{mod}`click_extra.testing`) build upon.
"""

from __future__ import annotations

import logging
import os
import shlex
import signal
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial
from gettext import gettext as _, ngettext
from time import perf_counter
from typing import Final, NoReturn

import click
from click import echo

from . import context
from ._utils import IS_WINDOWS, exception_chain, flatten
from .ansi import strip_ansi
from .envvar import env_copy
from .parameters import ExtraOption
from .theme import get_current_theme

TYPE_CHECKING = False
if TYPE_CHECKING:
    import subprocess
    from collections.abc import Generator, Iterable, Sequence
    from pathlib import Path
    from types import FrameType
    from typing import IO, Any

    from .envvar import TEnvVars
    from .theme import HelpTheme

    TArg = str | Path | None
    TNestedArgs = Iterable[TArg | Iterable["TNestedArgs"]]
    """Type for arbitrary nested CLI arguments.

    Arguments can be `str`, {class}`pathlib.Path` objects or `None` values.
    """


def is_windows() -> bool:
    """Whether the running platform is Windows, per `extra_platforms`.

    A thin wrapper around `extra_platforms.is_windows()` with a deferred
    import, which keeps extra_platforms off the startup path of every CLI.
    Kept under the same name so the POSIX-only signal reads below stay under a
    guard `tests/test_execution.py` recognizes.
    """
    # Deferred import: keeps extra_platforms off the startup path of every CLI.
    from extra_platforms import is_windows as platform_is_windows

    return platform_is_windows()


_JOIN_POLL: Final = 0.1
"""Seconds between two checks while the main thread waits on another thread.

A bounded wait returns to the interpreter that often, which is when a pending
Ctrl+C is handled. Two cases need it. On Windows, no signal interrupts a wait on
a lock or on a process. On every platform, a signal that lands after the
interpreter last checked for one and before the thread blocked in the C library
interrupts nothing: its handler runs only when the wait returns.
{func}`_exit_interrupted` joins the running threads in such slices,
{func}`~click_extra.jobs._wait_result` waits on each task of
{func}`~click_extra.jobs.run_jobs` and {func}`~click_extra.jobs.run_lanes` the
same way, and {func}`run_cli` waits so on its child and on the threads reading
its output.
"""


def _poll_slice(deadline: float | None) -> float:
    """Seconds the next slice of a wait lasts, to stop at `deadline`.

    {data}`_JOIN_POLL`, or what remains before the {func}`time.monotonic`
    `deadline` when that is less: `0` once it passed. `None` sets no deadline.
    """
    if deadline is None:
        return _JOIN_POLL
    return min(_JOIN_POLL, max(0.0, deadline - time.monotonic()))


class TimerOption(ExtraOption):
    """A pre-configured option that is adding a `--time`/`--no-time` flag to print
    elapsed time at the end of CLI execution.

    The start time is made available in the context in
    `ctx.meta[click_extra.context.START_TIME]`.
    """

    def print_timer(self, start_time: float) -> None:
        """Print the time elapsed since `start_time`.

        Always prints, even when a sibling eager option (`--version`,
        `--params`, `--show-config`…) short-circuited the command
        body via `ctx.exit()`. That makes `--time` a usable probe for
        the cost of Click Extra's own machinery (option parsing, config
        loading, eager callbacks), not just user command bodies.

        :param start_time: the {func}`time.perf_counter` reading the run started
            at.
        """
        echo(f"Execution time: {perf_counter() - start_time:0.3f} seconds.")

    def init_timer(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Set up the execution-timer machinery for the current invocation.

        Captures {func}`time.perf_counter` as the start time, stores it on
        `ctx.meta` under {data}`click_extra.context.START_TIME`, and queues
        {meth}`print_timer` as a context-close callback so the elapsed
        duration is printed even when a sibling eager option (`--version`,
        `--params`…) short-circuits the command body.

        The start time belongs to the run, not to the option: a run started from
        within another run of the same command times itself, and leaves the outer
        one its own start.
        """
        if not value or ctx.resilient_parsing:
            return

        # Only capture the start time when the user requested timing.
        start_time = perf_counter()
        context.set(ctx, context.START_TIME, start_time)

        # Register printing at the end of execution.
        ctx.call_on_close(partial(self.print_timer, start_time))

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
        default: bool = False,
        expose_value: bool = False,
        is_eager: bool = True,
        help: str = _("Measure and print elapsed execution time."),
        **kwargs: Any,
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
    """A pre-configured `-0`/`--zero-exit` option flag.

    Follows the convention popularized by linters and static analysers, which
    exit with a non-zero code whenever they report findings so that automation
    can gate on it. Setting this flag flips that behavior: the CLI returns `0`
    as long as it ran to completion, reserving non-zero codes for actual
    execution failures.

    The resolved value is stored in
    {data}`ctx.meta[click_extra.context.ZERO_EXIT] <click_extra.context.ZERO_EXIT>`.

    ```{warning}
    This option is a placeholder: it does not alter the CLI's exit code by
    itself. Downstream code must read
    {data}`ctx.meta[click_extra.context.ZERO_EXIT] <click_extra.context.ZERO_EXIT>`
    and act on it.
    ```
    """

    def set_zero_exit(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Store the resolved zero-exit flag on the context's `meta` dict.

        Read via {func}`click_extra.context.get(ctx, click_extra.context.ZERO_EXIT)
        <click_extra.context.get>`.
        """
        context.set(ctx, context.ZERO_EXIT, value)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
        default: bool = False,
        expose_value: bool = False,
        is_flag: bool = True,
        help: str = _(
            "Always exit with a status code of 0, even when problems are found."
        ),
        **kwargs: Any,
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


# Subprocess execution.
#
# Everything below runs *foreign* CLIs in subprocesses, for tools that wrap other
# programs (package managers, mail utilities, binaries under test). run_cli() is the
# spawn/stream/timeout engine; args_cleanup() and format_cli_prompt() serialize and
# disclose an invocation; the live-process registry and install_interrupt_handler()
# make Ctrl+C abort in-flight children instead of hanging a concurrent fan-out.


PROMPT = (">" if IS_WINDOWS else "$") + " "
"""Prompt used to simulate the CLI execution.

```{hint}
Use ASCII characters to avoid issues with Windows terminals.
```
"""


INDENT = " " * len(PROMPT)
"""Blank prefix as wide as {data}`PROMPT`, to indent what a run prints under the
line of its command."""


def args_cleanup(*args: TArg | TNestedArgs) -> tuple[str, ...]:
    """Flatten recursive iterables, remove all `None`, and cast each element to
    strings.

    Serializes {class}`pathlib.Path` and other objects. Nested iterables and
    `None` values are accepted as CLI arguments for convenience: they are
    flattened and filtered out.
    """
    return tuple(str(arg) for arg in flatten(args) if arg is not None)


def highlight_bin_name(program: str, theme: HelpTheme | None = None) -> str:
    """Style the binary's own name inside `program`, leaving its directory plain.

    `/opt/homebrew/bin/mas` renders with only `mas` in the active theme's
    `invoked_command` style, so the part of the path the eye scans for stands
    out from the noise of its location. A bare name (no separator) is styled
    whole. Both POSIX and Windows separators are recognized, whichever comes
    last.

    :param program: the command, path and all.
    :param theme: palette to style with. Defaults to the theme the current
        invocation runs under, see {func}`format_cli_prompt`.
    :return: the styled command.
    """
    active_theme = get_current_theme() if theme is None else theme
    split_at = max(program.rfind("/"), program.rfind("\\")) + 1
    return program[:split_at] + active_theme.invoked_command(program[split_at:])


def format_cli_prompt(
    cmd_args: Iterable[str],
    extra_env: TEnvVars | None = None,
    theme: HelpTheme | None = None,
    prompt: str | None = None,
) -> str:
    r"""Render the shell prompt simulating a CLI invocation, for logs and dry-runs.

    Prefixes {data}`~click_extra.execution.PROMPT` to any `extra_env` assignments
    and the command line. Each token family is styled with the theme slot
    ({func}`~click_extra.theme.get_current_theme`) it holds elsewhere in a CLI's
    output, so the line reads like the help screens do:

    - the prompt sigil with `bracket`, the structural-token style;
    - each environment assignment as `envvar` name, plain `=`, `default`
      value;
    - the program's binary name with `invoked_command`, its directory plain
      (see {func}`highlight_bin_name`);
    - the `-`/`--` flags with `option`; other arguments stay plain.

    Useful to print a copy-pasteable command trace in debug logs, dry-runs and
    test output. Each argument and environment value is quoted for the shell, so
    one carrying a space or a metacharacter reads back as the single token it
    was: a `-c` script keeps the quotes that made it one argument, instead of
    spilling into the line as several. Quote nothing before calling this, or the
    quotes are themselves quoted. Styling reads the raw argument, since a quoted
    `--name=John Doe` no longer opens on a dash.

    ```{note}
    The program is left as it stands. Quoting has to wrap the whole token, which
    would put the closing quote inside the name {func}`highlight_bin_name` styles,
    and a Windows path is quoted whole for its separators alone: `C:\Tools\mas.exe`
    needs none of it to paste back.
    ```

    :param cmd_args: the command line to render.
    :param extra_env: environment assignments to prefix it with.
    :param theme: palette to style the line with. Defaults to the theme the
        current invocation runs under, which is what a CLI printing its own
        trace wants. A caller drawing the line onto a surface of its own choosing
        (a light {doc}`capture </screenshots>`, say) passes the one that surface can
        show.
    :param prompt: sigil to draw before the command, when the shell being
        pictured is not the one running. A capture mimicking a Windows terminal
        passes `PS C:\>`; `None` keeps {data}`~click_extra.execution.PROMPT`,
        which is this platform's.
    :return: the styled prompt line.
    """
    active_theme = get_current_theme() if theme is None else theme
    extra_env_string = ""
    if extra_env:
        extra_env_string = "".join(
            f"{active_theme.envvar(name)}"
            f"={active_theme.default(shlex.quote(str(value)))} "
            for name, value in extra_env.items()
        )

    cmd_parts = tuple(cmd_args)
    styled_parts = []
    if cmd_parts:
        styled_parts.append(highlight_bin_name(cmd_parts[0], active_theme))
        for part in cmd_parts[1:]:
            quoted = shlex.quote(part)
            styled_parts.append(
                active_theme.option(quoted) if part.startswith("-") else quoted,
            )

    sigil, _, spacing = (PROMPT if prompt is None else f"{prompt} ").partition(" ")
    return (
        active_theme.bracket(sigil)
        + f" {spacing}"
        + extra_env_string
        + " ".join(styled_parts)
    )


_LIVE_PROCESSES: Final[set[subprocess.Popen[str]]] = set()
"""Registry of the subprocesses currently running through {func}`run_cli`.

Populated by {func}`run_cli` for the lifetime of each child (added right after
spawn, discarded in its `finally`). Read by {func}`terminate_live_processes` to
interrupt them all at once. Guarded by {data}`_LIVE_PROCESSES_LOCK`, since a
concurrent fan-out ({func}`~click_extra.jobs.run_jobs`,
{func}`~click_extra.jobs.run_lanes`) calls {func}`run_cli` from several worker
threads at once.
"""


_LIVE_PROCESSES_LOCK: Final = threading.RLock()
"""Guards {data}`_LIVE_PROCESSES`, {data}`_GROUP_LEADERS` and
{data}`_STRAY_DESCENDANTS` against concurrent mutation by worker threads.

Reentrant, because the Ctrl+C handlers call {func}`terminate_live_processes` in
the main thread, which can hold the lock at that moment: an interrupted run takes
it when its grace period ends. A plain lock would block the handler for good.
"""


_GROUP_LEADERS: Final[set[subprocess.Popen[str]]] = set()
"""Subset of {data}`_LIVE_PROCESSES` spawned with `start_new_session`.

Each of these children leads its own POSIX session and process group, so the
kill paths signal the whole group, plus every group a descendant moved to (see
{func}`_kill_posix_process_group`), instead of the direct child alone.
Maintained by {func}`run_cli` in lockstep with {data}`_LIVE_PROCESSES`, under
the same lock.
"""


_STRAY_DESCENDANTS: Final[dict[int, int]] = {}
"""Descendants the children of {func}`run_cli` may leave behind: each PID, with
the process group it was last seen in.

A child that exits on `SIGTERM` takes with it the only link to what it started
(see {func}`_descendant_pids`). So {func}`terminate_live_processes` writes down
the descendants of each child it asks to stop, and reads them back when it is
told to kill. A descendant leading a group of its own is left out: its group
alone cannot tell it from an unrelated process that took its PID. Guarded by
{data}`_LIVE_PROCESSES_LOCK`.
"""


_KILL_SIGNAL: Final = getattr(signal, "SIGKILL", signal.SIGTERM)
"""The signal that ends the children of {func}`run_cli` at once.

Windows has no `SIGKILL`: {func}`terminate_live_processes` uses its single
forced termination there, whatever the signal.
"""


def _parse_proc_stat(stat: str) -> tuple[int, int] | None:
    """Read the parent PID and process group ID off a Linux `/proc/<pid>/stat` line.

    The command name sits in parentheses and may itself hold spaces or
    parentheses, so the fields are counted from the last `)`: the state, the
    parent PID, then the process group. Returns `None` for a line that does not
    parse.
    """
    fields = stat.rpartition(")")[2].split()
    try:
        return int(fields[1]), int(fields[2])
    except (IndexError, ValueError):
        return None


def _posix_process_table() -> dict[int, tuple[int, int]]:
    """Map every visible process ID to its parent PID and process group ID.

    Reads `/proc` where it holds Linux `stat` files, which needs no subprocess and
    works in a container that ships no `ps`. Runs `ps` everywhere else, whose
    `-A` and `-o` options are POSIX. A process that exits while the table is read
    is left out, and the table is empty when neither source answers.
    """
    table: dict[int, tuple[int, int]] = {}
    if os.path.exists("/proc/self/stat"):
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                with open(
                    f"/proc/{name}/stat", encoding="UTF-8", errors="replace"
                ) as stat_file:
                    parsed = _parse_proc_stat(stat_file.read())
            except OSError:
                continue
            if parsed is not None:
                table[int(name)] = parsed
        return table

    # Deferred import: keeps subprocess off the startup path of every CLI.
    import subprocess

    try:
        listing = subprocess.run(
            ("ps", "-A", "-o", "pid=", "-o", "ppid=", "-o", "pgid="),
            capture_output=True,
            encoding="UTF-8",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return table
    for line in listing.stdout.splitlines():
        try:
            pid, ppid, pgid = (int(field) for field in line.split())
        except ValueError:
            continue
        table[pid] = (ppid, pgid)
    return table


def _descendant_pids(leader: int, table: dict[int, tuple[int, int]]) -> list[int]:
    """List every descendant of `leader`, deepest first.

    Descendants are found through their parent PIDs, so `table` must be read
    while `leader` is alive: once it dies, its children are reparented on to
    `init` and nothing links them back to it. `leader` itself is left out.

    The deepest-first order lets a caller signal a tree from its leaves up, so a
    supervisor never outlives the worker it would respawn.
    """
    children: dict[int, list[int]] = {}
    for pid, (ppid, _group) in table.items():
        children.setdefault(ppid, []).append(pid)
    found: list[int] = []
    seen = {leader}
    pending = [leader]
    while pending:
        for child in children.get(pending.pop(), ()):
            if child in seen:
                continue
            seen.add(child)
            pending.append(child)
            found.append(child)
    found.reverse()
    return found


def _kill_descendants(
    leader: int,
    table: dict[int, tuple[int, int]],
    signum: signal.Signals,
) -> None:
    """Signal each descendant of `leader`, one PID at a time.

    What a child sharing the caller's own process group gets instead of
    {func}`_kill_posix_process_group`, which cannot signal that group without
    hitting the caller too. Killing such a child leaves its own descendants
    running: `sudo` runs the command under a monitor process whenever `use_pty`
    is on, the upstream default since `1.9.14`, so a killed `sudo` leaves the
    escalated command alive and holding whatever lock it took.

    A PID that is already gone, or owned by another user, is skipped.
    """
    for pid in _descendant_pids(leader, table):
        try:
            os.kill(pid, signum)
        except OSError:
            pass


def _escaped_process_groups(
    leader: int,
    table: dict[int, tuple[int, int]],
) -> set[int]:
    """Find the process groups holding descendants of `leader` outside its group.

    A descendant that calls `setsid()` or `setpgid()` leaves the group `leader`
    heads, so signalling that group misses it and everything it starts. CPAN.pm
    does this for every `make test` run: it forks, and the fork detaches with
    `setsid()`.

    The group of the calling process is never returned, nor a group ID below `2`,
    which {func}`os.killpg` does not read as a plain group.
    """
    own_group = os.getpgid(0)
    groups: set[int] = set()
    for child in _descendant_pids(leader, table):
        group = table[child][1]
        if group not in (leader, own_group) and group > 1:
            groups.add(group)
    return groups


def _kill_posix_process_group(
    process: subprocess.Popen[str],
    signum: signal.Signals,
    table: dict[int, tuple[int, int]],
) -> bool:
    """Signal the POSIX process group led by `process`, and each group its
    descendants moved to.

    Only meaningful for a child spawned with `start_new_session`, whose group
    ID equals its PID. A descendant that left that group (see
    {func}`_escaped_process_groups`) is signalled through its own group, so it dies
    with the child instead of surviving as an orphan that holds the output pipes
    open. `table` is the caller's {func}`_posix_process_table` read, so one read
    serves several children and is always taken before the first signal.

    Returns `True` when the signal was delivered to the child's group, `False`
    when it could not be (no `killpg` on this platform, or the group is already
    gone), leaving the caller to fall back on signalling the direct child.
    """
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return False
    escaped = _escaped_process_groups(process.pid, table)
    try:
        # A start_new_session child is its own session and group leader, so its
        # PID doubles as the group ID: no getpgid() lookup (which could race
        # with the reaping of the child) is needed.
        killpg(process.pid, signum)
    except OSError:
        # The whole group is already gone: nothing left to signal.
        delivered = False
    else:
        delivered = True
    for group in escaped:
        try:
            killpg(group, signum)
        except OSError:
            # Gone already, or owned by another user: nothing to signal.
            pass
    return delivered


def _signal_posix_child(
    process: subprocess.Popen[str],
    signum: signal.Signals,
    table: dict[int, tuple[int, int]],
    *,
    leader: bool,
) -> None:
    """Send `signum` to a child of {func}`run_cli`, on POSIX.

    A `leader` child, spawned with `start_new_session`, gets it through its
    process groups: see {func}`_kill_posix_process_group`. Any other child, or a
    leader whose group is gone, gets it directly. When the signal is
    {data}`_KILL_SIGNAL`, the descendants of that child get it too, one PID at a
    time: a killed child cannot stop what it started. See
    {func}`_kill_descendants`.
    """
    if leader and _kill_posix_process_group(process, signum, table):
        return
    try:
        process.send_signal(signum)
    except OSError:
        # Reaped since the table was read: nothing left to stop.
        pass
    if signum == _KILL_SIGNAL:
        _kill_descendants(process.pid, table, signum)


def terminate_live_processes(signum: signal.Signals = signal.SIGTERM) -> None:
    """Send `signum` to every subprocess currently running through {func}`run_cli`.

    Called from the main thread's `SIGINT` handler (see
    {func}`install_interrupt_handler`) so a concurrent fan-out aborts promptly:
    terminating the children unblocks the worker threads parked in
    {func}`run_cli`, letting the thread pool drain instead of hanging on a child
    that ignored the terminal's process-group `SIGINT`.

    A child spawned with `start_new_session` never receives the terminal's
    `SIGINT` at all (it left the foreground process group), so its whole group
    is signalled here, with the groups its descendants moved to.

    Defaults to `SIGTERM` rather than `SIGKILL` so a child still gets to clean
    up, notably to restore terminal state a `sudo` password prompt may have
    altered. An aborting Click Extra command follows up with `SIGKILL` for a
    child still running after a grace period.

    `SIGTERM` goes to a child sharing the caller's process group alone: stopping
    what it started is part of its own clean-up. `SIGKILL` cannot be handled, so
    it also goes to each descendant of that child, one PID at a time (see
    {func}`_kill_descendants`), and to the descendants an earlier call wrote
    down (see {data}`_STRAY_DESCENDANTS`), which a child that exited on
    `SIGTERM` left running. Windows has a single forced termination, which ends
    the whole process tree of each child whatever `signum` asks for.

    The registry is snapshotted under the lock, then signalled outside it, because
    {func}`run_cli` may be discarding its own entries from other threads at the
    same time.
    """
    with _LIVE_PROCESSES_LOCK:
        live = tuple(_LIVE_PROCESSES)
        leaders = set(_GROUP_LEADERS)
        strays = dict(_STRAY_DESCENDANTS)
    if is_windows():
        for process in live:
            _kill_windows_process_tree(process.pid)
            try:
                process.terminate()
            except OSError:
                # Ended with its tree, or reaped since the snapshot.
                pass
        return
    kill = signum == _KILL_SIGNAL
    # One read of the process table, taken before any signal, serves every child.
    table = _posix_process_table() if live or strays else {}
    # A descendant still in the group it was seen in is the one written down.
    strays = {
        pid: group
        for pid, group in strays.items()
        if table.get(pid, (0, 0))[1] == group
    }
    for process in live:
        for pid in _descendant_pids(process.pid, table):
            if table[pid][1] != pid:
                strays[pid] = table[pid][1]
        _signal_posix_child(process, signum, table, leader=process in leaders)
    if kill:
        for pid in strays:
            try:
                os.kill(pid, signum)
            except OSError:
                # Gone since the table was read: nothing left to stop.
                pass
        strays = {}
    with _LIVE_PROCESSES_LOCK:
        _STRAY_DESCENDANTS.clear()
        _STRAY_DESCENDANTS.update(strays)


_STATUS_CONTROL_C_EXIT: Final = 0xC000013A - (1 << 32)
"""The exit code Windows reports for a process ended by Ctrl+C.

`STATUS_CONTROL_C_EXIT` (`0xC000013A`), written as the signed 32-bit integer
{func}`os._exit` takes: a parent process reads it back as `0xC000013A`. Python
ends with it on an unhandled Ctrl+C, where POSIX dies by `SIGINT`.
"""


_INTERRUPTED = threading.Event()
"""Set when a Ctrl+C reached the handler {func}`_interrupt_handling` installs.

Tells a `SIGINT` the terminal sent apart from a {exc}`KeyboardInterrupt` raised
by code, which a test runner does to simulate one. Only the former ends the
process by `SIGINT`.
"""


_RUN_END: ContextVar[list[BaseException] | None] = ContextVar("_RUN_END", default=None)
"""The exceptions that ended the CLI run in progress, or `None` outside a run.

Written by {func}`_run_end_watch`, read by {func}`_interrupted`.
"""


def _record_interrupt(signum: int, frame: FrameType | None) -> None:
    """Record a real Ctrl+C, then raise {exc}`KeyboardInterrupt` as Python does."""
    _INTERRUPTED.set()
    raise KeyboardInterrupt


@contextmanager
def _interrupt_handling() -> Generator[None, None, None]:
    """Track Ctrl+C, and what the run ends on, for the duration of a CLI run.

    Installs a `SIGINT` handler that behaves like Python's default one, but
    records that a real interrupt arrived, so {func}`_exit_interrupted` can end
    the process the way an unhandled Ctrl+C would. Only replaces Python's own
    default handler, in the main thread: a handler the program installed itself,
    or a call from another thread, leaves Ctrl+C alone.
    """
    token = _RUN_END.set([])
    try:
        if (
            threading.current_thread() is not threading.main_thread()
            or signal.getsignal(signal.SIGINT) is not signal.default_int_handler
        ):
            yield
            return
        _INTERRUPTED.clear()
        signal.signal(signal.SIGINT, _record_interrupt)
        try:
            yield
        finally:
            signal.signal(signal.SIGINT, signal.default_int_handler)
    finally:
        _RUN_END.reset(token)


@contextmanager
def _run_end_watch() -> Generator[None, None, None]:
    """Record the exception the block raises, as one the run in progress ends on.

    A Click Extra command wraps the two ways out of its run in it: building the
    root context, and closing it. Click's `main()` handles the exception past
    that point, then exits with a status that need not carry its cause: from
    Click `8.5.1` on ([pallets/click#3818](https://github.com/pallets/click/pull/3818)),
    the exit happens outside the handler, so it does not chain to what was
    handled.
    """
    try:
        yield
    except BaseException as exc:
        ended_on = _RUN_END.get()
        if ended_on is not None:
            ended_on.append(exc)
        raise


def _interrupted() -> bool:
    """Whether a real Ctrl+C ended the run in progress.

    True when {func}`_interrupt_handling` saw a `SIGINT`, and
    {func}`_run_end_watch` saw the run end on a {exc}`KeyboardInterrupt` or on
    an exception one led to, like the {exc}`click.exceptions.Abort` of an
    interrupted prompt. A program that caught the interrupt and exited on its
    own terms does not count.
    """
    if not _INTERRUPTED.is_set():
        return False
    return any(
        isinstance(link, KeyboardInterrupt)
        for exc in _RUN_END.get() or ()
        for link in exception_chain(exc)
    )


def _die_by_sigint() -> NoReturn:
    """End the process at once, the way an unhandled Ctrl+C does.

    Dies by `SIGINT` on POSIX, so a calling shell sees the signal and stops its
    own loop: a process exiting with a status, even `130`, tells the shell it
    handled the interrupt itself, and the loop goes on. On Windows, exits with
    {data}`_STATUS_CONTROL_C_EXIT`. Skips every clean-up but flushing the
    standard streams.

    Called from the handler of a second Ctrl+C, it can run while the interrupted
    code is writing to one of those streams: Python then refuses the flush as a
    reentrant call, with a {exc}`RuntimeError`, and the stream is left as is.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, RuntimeError, ValueError):
            # A closed or broken stream has nothing left to flush, and one the
            # interrupted code is writing to refuses a reentrant flush.
            pass
    if not is_windows():
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGINT)
    os._exit(_STATUS_CONTROL_C_EXIT if is_windows() else 128 + signal.SIGINT)


def _second_interrupt(signum: int, frame: FrameType | None) -> None:
    """Handle a Ctrl+C pressed while an interrupted run waits: exit at once.

    Kills the children of {func}`run_cli` first, with their descendants, which
    would otherwise outlive the process.
    """
    terminate_live_processes(_KILL_SIGNAL)
    _die_by_sigint()


_TERMINATE_GRACE: Final = 3.0
"""Seconds an interrupted CLI gives the children of {func}`run_cli` to exit.

They get `SIGTERM` as the run aborts, so they can clean up, and
{data}`_KILL_SIGNAL` once this grace runs out.
"""


def _exit_interrupted() -> NoReturn:
    """End an interrupted run once its running threads finish.

    Asks the children of {func}`run_cli` to stop first, so the threads waiting
    on them return: `SIGTERM` at once, {data}`_KILL_SIGNAL` after
    {data}`_TERMINATE_GRACE`, to them and to their descendants. Waits for the
    threads, as the interpreter would at exit, but says so, and says what a
    second Ctrl+C does: it stops the wait and exits at once. Then ends the
    process by {func}`_die_by_sigint`.
    """
    terminate_live_processes()
    current = threading.current_thread()
    running = [
        thread
        for thread in threading.enumerate()
        if thread is not current and not thread.daemon and thread.is_alive()
    ]
    if running and current is threading.main_thread():
        signal.signal(signal.SIGINT, _second_interrupt)
        echo(
            ngettext(
                "Waiting for {count} running task to finish. "
                "Press Ctrl+C again to quit now.",
                "Waiting for {count} running tasks to finish. "
                "Press Ctrl+C again to quit now.",
                len(running),
            ).format(count=len(running)),
            err=True,
        )
        deadline = time.monotonic() + _TERMINATE_GRACE
        killed = False
        for thread in running:
            while thread.is_alive():
                thread.join(timeout=_JOIN_POLL)
                if not killed and time.monotonic() >= deadline:
                    terminate_live_processes(_KILL_SIGNAL)
                    killed = True
    _die_by_sigint()


@contextmanager
def _deferred_interrupt() -> Generator[None, None, None]:
    """Hold back a Ctrl+C for the duration of the block, then deliver it.

    Shields a short critical section that must run whole: the kill in
    {func}`run_cli` reads the process table, then signals what it found, and an
    interrupt landing in between would skip the signals and orphan the child.
    The interrupt is delivered again at the end of the block, to whichever
    handler was in place, so it is postponed, never lost.

    Only the main thread receives `SIGINT`, so elsewhere the block runs as is.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    received: list[int] = []

    def hold(signum: int, frame: FrameType | None) -> None:
        received.append(signum)

    previous = signal.signal(signal.SIGINT, hold)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)
        if received:
            signal.raise_signal(signal.SIGINT)


def install_interrupt_handler(ctx: click.Context) -> None:
    """Make the first Ctrl+C terminate in-flight subprocesses, then abort as usual.

    Installs a `SIGINT` handler for the duration of the CLI run that calls
    {func}`terminate_live_processes` before re-raising {class}`KeyboardInterrupt`
    (exactly what Python's default handler raises). The abort then proceeds
    normally, and a concurrent fan-out does not hang on surviving children. The
    previous handler is restored when `ctx` closes.

    Must run in the main thread: {func}`signal.signal` refuses to install a handler
    from any other, so a non-main-thread caller (embedded use, some tests) is a
    no-op that keeps the default Ctrl+C behavior.

    A Click Extra command already asks the children to stop as the run aborts,
    once its context has closed. This handler does it at the moment of the
    Ctrl+C, which matters when a close callback waits on one of them, and serves
    a plain Click command, which has no such abort path.
    """
    if threading.current_thread() is not threading.main_thread():
        return

    def handler(signum: int, frame: FrameType | None) -> None:
        _INTERRUPTED.set()
        terminate_live_processes()
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGINT, handler)
    ctx.call_on_close(lambda: signal.signal(signal.SIGINT, previous))


_KILL_DRAIN_GRACE: Final = 3.0
"""Seconds {func}`run_cli` waits for its stream readers after killing the child.

Once the child is killed its pipes normally hit `EOF` at once, so the readers
finish within milliseconds. The exception is an orphaned grandchild holding an
inherited pipe handle open: the grace period bounds the wait instead of blocking
forever, and the daemon reader threads are then abandoned with whatever output
they collected. A killed child normally leaves no such orphan behind, since
its descendants are killed with it, so its drain completes promptly.
"""


def _kill_windows_process_tree(pid: int) -> None:
    """Forcibly terminate `pid` and its whole process tree. No-op off Windows.

    Grandchild processes (installer EXEs spawned by a package manager's COM
    server, say) inherit the pipe write handles and keep them open past a plain
    `kill()` of the direct child, which would leave the output drain blocked
    until every grandchild exits. `taskkill /F /T` kills the entire tree,
    closing all inherited handles so the readers hit `EOF` promptly.
    """
    if not is_windows():
        return

    # Deferred import: keeps subprocess off the startup path of every CLI.
    import subprocess

    subprocess.run(
        ("taskkill", "/F", "/T", "/PID", str(pid)),
        capture_output=True,
        timeout=10,
        check=False,
    )


def _pump_stream(
    pipe: IO[str],
    sink: list[str],
    log: logging.Logger,
    level: int,
    label: str | None,
) -> None:
    """Reader-thread body: accumulate `pipe`'s lines and forward each to `log`.

    Each line is appended raw to `sink` (so the caller reassembles the exact
    capture `communicate()` would have produced), then echoed to the logger
    stripped of ANSI codes and trailing whitespace. Blank lines are accumulated
    but not logged. The loop ends at `EOF`, when every writer of the pipe has
    closed it.

    `label` rides each record as its `label` attribute, which
    {class}`click_extra.logging.Formatter` renders glued to the level name
    (`debug:mas: ...`) rather than polluting the message text itself.
    """
    extra = {"label": label} if label else None
    for line in pipe:
        sink.append(line)
        text = strip_ansi(line).rstrip()
        if text:
            log.log(level, text, extra=extra)


def _wait_process(process: subprocess.Popen[str], deadline: float | None) -> None:
    """Wait for `process` to exit, by the {func}`time.monotonic` `deadline`.

    Waits in slices of {data}`_JOIN_POLL` seconds, so a Ctrl+C reaching the main
    thread is handled within one slice. `None` waits for as long as the process
    runs.

    :raises subprocess.TimeoutExpired: when the deadline passes first.
    """
    # Deferred import: keeps subprocess off the startup path of every CLI.
    import subprocess

    while True:
        try:
            process.wait(timeout=_poll_slice(deadline))
        except subprocess.TimeoutExpired:
            if deadline is not None and time.monotonic() >= deadline:
                raise
        else:
            return


def _track(process: subprocess.Popen[Any], *, leader: bool = False) -> None:
    """Add `process` to the live-process registry, so Ctrl+C reaches it.

    {func}`terminate_live_processes` signals every process in the registry, which
    is how a Ctrl+C reaching the main thread stops a child that another thread
    waits on. A `leader`, spawned with `start_new_session`, is signalled through
    its process group. Pair each call with {func}`_untrack`.
    """
    with _LIVE_PROCESSES_LOCK:
        _LIVE_PROCESSES.add(process)
        if leader:
            _GROUP_LEADERS.add(process)


def _untrack(process: subprocess.Popen[Any]) -> None:
    """Remove `process` from the live-process registry, once it is reaped.

    A later Ctrl+C then does not try to signal a process that is gone.
    """
    with _LIVE_PROCESSES_LOCK:
        _LIVE_PROCESSES.discard(process)
        _GROUP_LEADERS.discard(process)


def _kill_process(process: subprocess.Popen[Any], *, leader: bool = False) -> None:
    """Kill `process` and the descendants it started, then reap it.

    Kills its whole tree on Windows. On POSIX it kills the process group it
    leads plus the groups its descendants moved to when `leader`, and the child
    followed by each of its descendants otherwise: the process table is read
    first, because {func}`_descendant_pids` needs the child alive to find them.
    A second Ctrl+C waits for the kill to land: see {func}`_deferred_interrupt`.
    """
    with _deferred_interrupt():
        if is_windows():
            # `taskkill /F /T` covers the whole tree and `process.kill()` backs it
            # up. Windows has no process group to signal.
            _kill_windows_process_tree(process.pid)
            process.kill()
        else:
            _signal_posix_child(
                process, _KILL_SIGNAL, _posix_process_table(), leader=leader
            )
    process.wait()


def _stop_process(process: subprocess.Popen[Any], grace: float) -> int:
    """Ask `process` to stop, kill it once `grace` seconds run out, and reap it.

    `SIGTERM` comes first, so the child gets to clean up after itself. A child
    still running when `grace` runs out is killed with its descendants, see
    {func}`_kill_process`, and so is one whose wait a Ctrl+C interrupts. The wait
    is sliced like the one of {func}`run_cli`, so a Ctrl+C reaching the main
    thread is handled within one slice.

    :return: the exit status of `process`.
    """
    # Deferred import: keeps subprocess off the startup path of every CLI.
    import subprocess

    if process.poll() is None:
        process.terminate()
        try:
            _wait_process(process, time.monotonic() + grace)
        except subprocess.TimeoutExpired:
            _kill_process(process)
        except KeyboardInterrupt:
            _kill_process(process)
            raise
    return process.wait()


def _drain_readers(readers: Iterable[threading.Thread], deadline: float | None) -> bool:
    """Join the reader threads, by the {func}`time.monotonic` `deadline`.

    Returns `True` when every reader finished, `False` when the deadline
    passed with at least one still alive (an orphaned grandchild keeping a pipe
    open). `None` waits forever, like {meth}`subprocess.Popen.communicate`
    without a timeout. Each join waits in slices of {data}`_JOIN_POLL` seconds,
    like {func}`_wait_process`.
    """
    for reader in readers:
        while reader.is_alive():
            wait = _poll_slice(deadline)
            if not wait:
                return False
            reader.join(wait)
    return True


def run_cli(
    args: TArg | TNestedArgs,
    *,
    extra_env: TEnvVars | None = None,
    cwd: Path | str | None = None,
    timeout: float | None = None,
    label: str | None = None,
    merge_stderr: bool = False,
    errors: str = "replace",
    windows_creation_flags: int = 0,
    start_new_session: bool = False,
    command_level: int = logging.INFO,
    output_level: int = logging.DEBUG,
    log: logging.Logger | None = None,
) -> subprocess.CompletedProcess[str]:
    r"""Run a CLI in a subprocess, disclosing the call and streaming its output live.

    A {func}`subprocess.run` work-alike for CLI-wrapping tools, with observability
    built in:

    - the invocation is logged before the spawn, as the copy-pasteable
      `$ ENV=value command args` line of {func}`format_cli_prompt`, so a user
      can reproduce by hand what the tool runs on their system;
    - each line of the child's output is forwarded to the logger *as it is
      produced* (ANSI-stripped, tagged with `label`), instead of being held
      back until the child exits, so a long-running command narrates its progress
      live;
    - the child is registered in the live-process registry for the duration of the
      call, so {func}`terminate_live_processes` (wired to Ctrl+C by
      {func}`install_interrupt_handler`) can abort it.

    Contract mirrored from {func}`subprocess.run`:

    - returns a {class}`subprocess.CompletedProcess` with the full captured
      `stdout` and `stderr` decoded as UTF-8;
    - raises {exc}`subprocess.TimeoutExpired` (with the partial capture attached)
      when the child, or the draining of its output, outlives `timeout`. The
      child is killed first, and so is every descendant it left behind: the
      whole process tree on Windows (see {func}`_kill_windows_process_tree`),
      the POSIX process group and every group its descendants moved to when
      spawned with `start_new_session`, the child plus each descendant PID
      otherwise;
    - a {exc}`KeyboardInterrupt` mid-run kills the child (with the same tree,
      group or per-PID scope), then propagates.

    The child reads from {data}`subprocess.DEVNULL` so it can never block on
    `stdin`, and never opens a console window on Windows.

    ```{note}
    The pipes are opened in universal-newlines text mode, so a bare `\r`
    (a child redrawing a progress bar in place) terminates a line just like
    `\n`: each redraw is streamed as its own log line, and the captured
    text normalizes both to `\n`, exactly as
    {meth}`subprocess.Popen.communicate` does.
    ```

    :param args: the command line. Nested iterables are flattened, `None`
        values dropped, and every element ({class}`~pathlib.Path`, versions, ...)
        cast to a string; see {func}`args_cleanup`.
    :param extra_env: environment variables forced over the inherited environment
        for this call (see {func}`~click_extra.envvar.env_copy`). They are part of
        the disclosed prompt line, since reproducing the call requires them.
    :param cwd: directory to run the child in. `None` inherits the caller's, which
        is {func}`subprocess.run`'s own default. A relative `args[0]` is resolved
        by the OS against this directory, not the caller's, so pass an absolute
        path (or a name on the `PATH`) when moving the child elsewhere.
    :param timeout: seconds before the child is killed. `None` waits forever.
    :param label: tag identifying this call on each streamed output line, for
        when several children interleave in one log. Carried as the record's
        `label` attribute, which {class}`click_extra.logging.Formatter` renders
        glued to the level name and styled like an invoked command
        (`debug:mas: Warning: ...`); a foreign formatter can read
        `record.label` itself. Applied to the prompt line and to every output
        line, so an interleaved log attributes each command as well as what it
        printed.
    :param merge_stderr: route the child's `stderr` into `stdout` so the OS
        interleaves both in write order. The result's `stderr` is then `None`,
        like a {func}`subprocess.run` call with `stderr=STDOUT`.
    :param errors: decoding error handler for the child's output. The default
        `"replace"` swaps undecodable bytes for `�`; pass
        `"backslashreplace"` to keep them inspectable as escapes.
    :param windows_creation_flags: extra Windows process-creation flags, OR-ed
        with the always-on `CREATE_NO_WINDOW`. No-op off Windows.
    :param start_new_session: make the child lead its own POSIX session and
        process group ({class}`subprocess.Popen`'s parameter of the same name).
        Every kill path then signals the whole group in one call: the
        `timeout` overrun, a mid-run {exc}`KeyboardInterrupt`, and
        {func}`terminate_live_processes`. A grandchild spawned by the child (a
        shim re-executing the real binary, an installer helper) is reaped along
        with it instead of surviving as an orphan holding the output pipes
        open. A descendant that left the group with `setsid()`, like the
        `make test` run CPAN.pm forks, is signalled through its own group.
        Off by default, and to be left off when a descendant must keep the
        controlling terminal: a new session detaches from it, so an interactive
        prompt raised from inside the child (`sudo` reading `/dev/tty`)
        would fail, and `sudo`'s tty-keyed credential cache would no longer
        match. That costs the atomicity of a single group signal, not the
        reaping: the `timeout` and {exc}`KeyboardInterrupt` paths then kill the
        child and walk the tree it led, signalling each descendant by PID (see
        {func}`_kill_descendants`). {func}`terminate_live_processes` signals
        the direct child alone when it sends `SIGTERM`, for a clean exit, and
        walks the same tree when it sends `SIGKILL`. No-op on Windows, where
        each of these paths already kills the full tree. Only the reaping half of
        this flag has that Windows equivalent, and the other half has none: a
        POSIX session also detaches the child from the controlling terminal,
        where a Windows child keeps sharing the parent's console and can still
        reach back into it: a console control event the child raises, as a
        package manager's own teardown can, lands in the parent as a
        {exc}`KeyboardInterrupt`. The lever there is `windows_creation_flags`
        (`CREATE_NEW_PROCESS_GROUP`), left to the caller because it also
        changes how a real Ctrl-C reaches the child.
    :param command_level: logging level of the invocation-disclosure line.
        Defaults to {data}`logging.INFO`; lower it to {data}`logging.DEBUG` for
        internal probes not worth narrating.
    :param output_level: logging level of the streamed output lines. Defaults to
        {data}`logging.DEBUG`.
    :param log: destination logger. Defaults to the root logger, whose level the
        {class}`~click_extra.logging.VerbosityOption` family manages.
    """
    # Deferred import: keeps subprocess off the startup path of every CLI.
    import subprocess

    if log is None:
        log = logging.getLogger()
    clean_args = args_cleanup(args)
    assert clean_args, "No CLI to run."

    log.log(
        command_level,
        format_cli_prompt(clean_args, extra_env),
        extra={"label": label} if label else None,
    )

    # On Windows, CREATE_NO_WINDOW suppresses any console window the child might
    # open, while still capturing output via the explicit PIPE handles. SW_HIDE is
    # a belt-and-suspenders suppression of console windows. STARTUPINFO must be
    # created per call because subprocess overwrites its hStd* fields. On POSIX,
    # both creationflags=0 and startupinfo=None are no-ops.
    startupinfo = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo is not None:
        startupinfo = startupinfo()
        startupinfo.dwFlags = getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = 0  # SW_HIDE
    # Session isolation is a POSIX concept: force it off on Windows, whose kill
    # path already covers the whole tree through taskkill.
    start_new_session = start_new_session and not is_windows()
    process = subprocess.Popen(
        clean_args,
        # Prevents the child from blocking on stdin reads.
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        encoding="UTF-8",
        errors=errors,
        env=env_copy(extra_env),
        cwd=cwd,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | windows_creation_flags,
        startupinfo=startupinfo,
        start_new_session=start_new_session,
    )
    log.debug(f"Spawned PID {process.pid}: {highlight_bin_name(clean_args[0])}.")

    # Track the live child so the main thread's SIGINT handler can terminate it on
    # Ctrl+C (see terminate_live_processes): a worker thread never receives the
    # interrupt itself. A session-isolated child is also flagged as the leader of
    # its own process group, so every kill path signals the group as a whole.
    _track(process, leader=start_new_session)

    # One reader thread per captured pipe streams the output live while the
    # calling thread blocks in wait(). Daemon threads, so an abandoned reader (an
    # orphaned grandchild holding the pipe open past the kill grace) never blocks
    # interpreter shutdown.
    out_lines: list[str] = []
    err_lines: list[str] = []
    readers = []
    for pipe, sink in ((process.stdout, out_lines), (process.stderr, err_lines)):
        if pipe is None:
            continue
        reader = threading.Thread(
            target=_pump_stream,
            args=(pipe, sink, log, output_level, label),
            daemon=True,
        )
        reader.start()
        readers.append(reader)

    def timeout_expired() -> subprocess.TimeoutExpired:
        """Build the exception with the partial capture attached, as run() does."""
        assert timeout is not None
        return subprocess.TimeoutExpired(
            clean_args,
            timeout,
            output="".join(out_lines),
            stderr=None if merge_stderr else "".join(err_lines),
        )

    def abort(reason: str) -> None:
        """Forcibly stop the child and its descendants, reap it and collect what
        its pipes still hold.

        See {func}`_kill_process` for what the kill reaches.
        """
        log.debug(f"PID {process.pid} {reason}; sending kill.")
        _kill_process(process, leader=start_new_session)
        _drain_readers(readers, time.monotonic() + _KILL_DRAIN_GRACE)

    deadline = time.monotonic() + timeout if timeout is not None else None
    timeout_desc = "none" if timeout is None else f"{timeout}s"
    try:
        try:
            log.debug(f"Waiting for PID {process.pid} (timeout={timeout_desc}).")
            _wait_process(process, deadline)
        except subprocess.TimeoutExpired:
            abort("timed out")
            log.debug(f"PID {process.pid} killed; exit {process.returncode}.")
            raise timeout_expired() from None
        except KeyboardInterrupt:
            abort("interrupted")
            raise
    finally:
        # The child is no longer live: drop it so a later Ctrl+C does not try to
        # signal an already-reaped process.
        _untrack(process)

    # The child exited: drain the readers within what remains of the deadline. A
    # reader can outlive the child when a grandchild inherited the pipe and keeps
    # writing; communicate() times out on that same shape, so mirror it.
    if not _drain_readers(readers, deadline):
        log.debug(f"PID {process.pid} exited but its output drain timed out.")
        raise timeout_expired() from None

    stdout = "".join(out_lines)
    stderr = "".join(err_lines)
    log.debug(
        f"PID {process.pid} exited {process.returncode}; "
        f"stdout {len(stdout)} chars, stderr {len(stderr)} chars.",
    )
    return subprocess.CompletedProcess(
        clean_args,
        process.returncode,
        stdout=stdout,
        stderr=None if merge_stderr else stderr,
    )
