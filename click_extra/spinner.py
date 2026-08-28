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
"""An indeterminate terminal spinner for long-running, blocking work.

Click ships {func}`click.progressbar`, but it is *determinate*: it needs a known
length or an iterable to advance through. Some work has no measurable progress:
a blocking subprocess, a network round-trip, a query whose duration is unknown.
For those, the only honest feedback is "something is happening".

{class}`Spinner` fills that gap. It animates a small frame sequence on a daemon
thread, so the caller can stay blocked in a single call (`communicate()`,
`urlopen()`, ...) while the spinner keeps turning:

```{code-block} python

from time import sleep

from click_extra import Spinner

with Spinner("Brewing tea"):
    sleep(5)  # A blocking call with no measurable progress.
```

```{caution}
The spinner draws with carriage returns and ANSI control codes, so it is a
no-op whenever its output stream is not a TTY (a pipe, a file, a captured
test buffer, a CI log), unless `enabled` is forced. This keeps redirected
output and machine-readable formats clean.
```

```{note}
On Windows, {meth}`Spinner.start` enables the console's virtual-terminal
processing so the ANSI control codes animate in place rather than print
literally (`⠋␛[0m … ␛[K`). Modern terminals (Windows Terminal, recent
conhost) already have it on; this just covers older consoles.
```
"""

from __future__ import annotations

import functools
import os
import sys
import threading
import time
from gettext import gettext as _
from typing import TypeVar, cast

import click
from wcwidth import wcswidth

from . import context
from .color import COLOR_DISABLING_TERMS, is_a_tty
from .humanize import format_duration
from .parameters import ExtraOption
from .spinner_presets import (
    SPINNER_FRAMES,
    SPINNERS,
    SpinnerPreset,
)
from .styling import Style

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from types import TracebackType
    from typing import IO, Any, Literal, Protocol, TextIO

    from click._termui_impl import ProgressBar
    from typing_extensions import Self

    class _LiveLine(Protocol):
        """A live terminal line other output must cooperate with.

        The shared surface {func}`_active_line` exposes so a concurrent writer
        (the logging bridge, a trail) can print above whichever live line owns
        the terminal right now, be it a {class}`Spinner` or an
        {class}`OperationTrail`'s progress-bar indicator.
        """

        def _resolve_stream(self) -> IO[str]: ...
        def echo(self, message: str) -> None: ...

    class _AggregateIndicator(Protocol):
        """The live aggregate indicator an {class}`OperationTrail` drives.

        Both the spinner-backed and bar-backed indicators expose this surface,
        so the trail drives either one the same way: enter it, {meth}`advance`
        the tally as outcomes land, {meth}`echo` a persistent line per outcome,
        then {meth}`finish` with a kept summary.
        """

        @property
        def shown(self) -> bool: ...
        def __enter__(self) -> Self: ...
        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> None: ...
        def advance(self, done: int) -> None: ...
        def echo(self, message: str) -> None: ...
        def finish(self, ok: bool, summary: str) -> None: ...


_ACTIVE_LINES: list[_LiveLine] = []
"""Stack of the live terminal lines currently drawing, innermost last.

A {class}`Spinner` or an {class}`OperationTrail` progress-bar indicator
registers itself when it actually begins drawing (a disabled one never
registers) and deregisters when it stops. Guarded by
{data}`_ACTIVE_LINES_LOCK`, since these are started and stopped from worker
threads too.
"""


_ACTIVE_LINES_LOCK = threading.Lock()
"""Guards {data}`_ACTIVE_LINES` against concurrent mutation."""


def _register_line(line: _LiveLine) -> None:
    """Advertise `line` as a live terminal line. Idempotent."""
    with _ACTIVE_LINES_LOCK:
        if line not in _ACTIVE_LINES:
            _ACTIVE_LINES.append(line)


def _deregister_line(line: _LiveLine) -> None:
    """Withdraw `line` from the live-line registry. Idempotent."""
    with _ACTIVE_LINES_LOCK:
        if line in _ACTIVE_LINES:
            _ACTIVE_LINES.remove(line)


def _active_line(stream: IO[str] | None = None) -> _LiveLine | None:
    """Return the innermost live terminal line drawing, or `None`.

    With `stream` given, only a line drawing on that very stream matches. This
    is how output producers cooperate with a running animation or progress bar
    instead of garbling it: {class}`click_extra.logging.StreamHandler` checks
    here and routes its records through the line's `echo`, which erases the
    in-progress render, prints the line, and redraws underneath.
    """
    with _ACTIVE_LINES_LOCK:
        for line in reversed(_ACTIVE_LINES):
            if stream is None or line._resolve_stream() is stream:
                return line
    return None


def active_spinner(stream: IO[str] | None = None) -> Spinner | None:
    """Return the innermost {class}`Spinner` currently animating, or `None`.

    A spinner-typed view of {func}`_active_line`, skipping any progress-bar
    indicator that may own the line instead. With `stream` given, only a
    spinner drawing on that very stream matches.
    """
    with _ACTIVE_LINES_LOCK:
        for line in reversed(_ACTIVE_LINES):
            if isinstance(line, Spinner) and (
                stream is None or line._resolve_stream() is stream
            ):
                return line
    return None


def _stream_enabled(enabled: bool | None, stream: IO[str]) -> bool:
    """Resolve whether a cursor-driven display may draw on `stream`.

    Honors an explicit `enabled` override; otherwise auto-detects, drawing only
    on an interactive terminal that can move the cursor. That rules out
    non-interactive streams (a pipe, file or captured buffer, which are not a
    TTY) and `TERM=dumb` / `TERM=unknown` terminals, whose lack of cursor
    control would smear the output instead of updating it in place. Shared by
    {class}`Spinner` and the {class}`OperationTrail` progress-bar indicator.
    """
    if enabled is not None:
        return enabled
    if os.environ.get("TERM", "").lower() in COLOR_DISABLING_TERMS:
        return False
    return is_a_tty(stream)


class Spinner:
    """A thread-animated, indeterminate progress spinner usable as a context
    manager.

    The animation runs on a background daemon thread, leaving the calling thread
    free to block on the actual work. Entering the context (or calling
    {meth}`start`) begins the animation; leaving it (or calling {meth}`stop`)
    halts the thread and erases the spinner line so it never lingers above the
    next output.

    ```{note}
    A single {class}`Spinner` instance drives one animation at a time. mpm
    and similar tools run their subprocesses sequentially, so one shared
    instance whose {attr}`label` is reassigned between steps is enough; for
    concurrent work, use one instance per thread.
    ```
    """

    label: str
    """Text drawn after the spinner glyph.

    Reassign it at any time while the spinner runs to reflect the current step;
    the animation thread reads it afresh on every frame.
    """

    def __init__(
        self,
        label: str | Callable[..., Any] = "",
        *,
        frames: Sequence[str] | None = None,
        spinner: SpinnerPreset | None = None,
        reverse: bool = False,
        interval: float | None = None,
        delay: float = 0.0,
        style: Style | None = None,
        timer: bool | Callable[[float], str] = False,
        stream: IO[str] | None = None,
        enabled: bool | None = None,
        hide_cursor: bool = True,
        beep: bool = False,
    ) -> None:
        """Configure (but do not start) the spinner.

        :param label: text shown after the spinner glyph. As a special case, a
            bare `@Spinner` decorator passes the wrapped function here instead;
            it is detected and the label defaults to empty.
        :param frames: the animation frames, cycled in order. Defaults to
            {data}`~click_extra.spinner_presets.SPINNER_FRAMES`, or the `spinner`
            preset's frames when given.
        :param spinner: a {class}`~click_extra.spinner_presets.SpinnerPreset` from
            the {data}`~click_extra.spinner_presets.SPINNERS` catalog
            (`spinner=SPINNERS["moon"]`), supplying both frames and a tuned
            interval. An explicit `frames` or `interval` still overrides it.
        :param reverse: cycle the frames backwards, spinning the animation the
            other way. Set it when the rotation runs counter to what you expect;
            it composes with any custom `frames`.
        :param interval: seconds between two frames. Defaults to `0.1`, or the
            `spinner` preset's interval when given.
        :param delay: seconds to wait before drawing the first frame. A non-zero
            delay keeps the spinner silent for calls that finish quickly, so it
            only surfaces once an operation is genuinely slow.
        :param style: a {class}`~click_extra.styling.Style` applied to the spinner
            glyph, label and timer (`Style(fg="cyan", bold=True)`). Color is
            decoupled from animation: `--no-color` / `NO_COLOR` strip it while
            the spinner keeps spinning (see {class}`ProgressOption`).
        :param timer: append the elapsed wall-clock time to the spinner, and to
            any final {meth}`ok` / {meth}`fail` line. `True` uses
            {func}`~click_extra.humanize.format_duration` for the default
            compact format (`2.3s`, `1:05`, then `1:02:03`). Pass a callable
            `(seconds: float) -> str` to format the duration yourself, like
            ``timer=lambda s: f"{s / 60:.0f}m"`` for whole minutes.
        :param stream: where to draw; defaults to {data}`sys.stderr` so the
            spinner never mixes into `stdout` data.
        :param enabled: force the spinner on or off. `None` (the default)
            auto-detects, animating only when `stream` is a TTY.
        :param hide_cursor: hide the text cursor while spinning and restore it on
            stop.
        :param beep: ring the terminal bell once when the spinner stops. It
            fires only when the spinner was active, so a disabled or redirected
            spinner stays silent.
        :raises ValueError: if `style` carries a color or attribute that
            cannot be rendered.
        """
        # Support a bare `@Spinner` decorator (no parentheses): the first
        # positional is then the wrapped function, not a text label. `@Spinner(…)`
        # and `with Spinner(…)` keep passing a string label as usual. A string is
        # never callable, so this never misfires on a real label.
        #
        # This is the same `callable(first_arg)` test as
        # `click_extra.decorators.allow_missing_parenthesis`, inlined here on
        # purpose: that helper wraps a decorator *factory function* and returns a
        # function, so it cannot wrap `Spinner` without replacing the class: and
        # `Spinner` must stay a class to double as a context manager and to support
        # `isinstance()` / subclassing. The bare-call hook therefore has to live
        # in `__init__`, the one place the parenthesis-less form reaches.
        self._decorated: Callable[..., Any] | None = None
        if callable(label):
            self._decorated = label
            # Make the instance masquerade as the function it stands in for,
            # without overwriting our own attributes (`updated=()`).
            functools.update_wrapper(self, label, updated=())
            label = ""

        self.label = label
        # `spinner=` supplies frames and interval together; an explicit `frames=`
        # or `interval=` overrides the preset, and both fall back to the defaults.
        if frames is not None:
            self.frames = frames
        elif spinner is not None:
            self.frames = spinner.frames
        else:
            self.frames = SPINNER_FRAMES
        if interval is not None:
            self.interval = interval
        elif spinner is not None:
            self.interval = spinner.interval
        else:
            self.interval = 0.1
        self.reverse = reverse
        self.delay = delay
        self.style = style
        self.timer = timer
        self.stream = stream
        self.enabled = enabled
        self.hide_cursor = hide_cursor
        self.beep = beep

        # Validate the style once, so a bad color or attribute fails loudly here
        # instead of silently killing the draw thread (cloup builds and applies
        # the style lazily on first call, where the error would surface off-thread).
        if style is not None:
            try:
                style("")
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid spinner style: {error}") from error

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._drawn = False
        self._cursor_hidden = False
        self._color_enabled = False
        self._start_time: float | None = None
        self._stop_time: float | None = None

    def _resolve_stream(self) -> IO[str]:
        """Return the explicit `stream`, or default to {data}`sys.stderr`.

        Resolved lazily so a stream swapped in after construction (as test
        harnesses do) is honored.
        """
        return self.stream if self.stream is not None else sys.stderr

    def _resolve_enabled(self, stream: IO[str]) -> bool:
        """Decide whether to animate, honoring an explicit `enabled` override.

        Auto-detection (`enabled=None`) animates only on an interactive terminal
        that can move the cursor. That rules out non-interactive streams (a pipe,
        file or captured buffer, which are not a TTY) and `TERM=dumb` /
        `TERM=unknown` terminals, whose lack of cursor control would smear a trail
        of frames down the screen instead of animating in place.
        """
        return _stream_enabled(self.enabled, stream)

    def _resolve_color_enabled(self, stream: IO[str]) -> bool:
        """Decide whether to apply ANSI color, orthogonally to whether it animates.

        Color follows Click Extra's reconciled {attr}`ctx.color
        <click.Context.color>` when a command context is active, so `--color` /
        `--no-color` and the `NO_COLOR` / `FORCE_COLOR` family have already
        been honored. Outside a CLI it falls back to those two environment variables
        and a dumb/unknown `TERM` (see
        {data}`~click_extra.color.COLOR_DISABLING_TERMS`), then to TTY detection.
        This is independent of {meth}`_resolve_enabled`: a spinner can spin in plain
        text (a TTY under `NO_COLOR`), which is exactly the decoupling
        {class}`ProgressOption` documents.
        """
        ctx = click.get_current_context(silent=True)
        if ctx is not None and ctx.color is not None:
            return ctx.color
        # Mirror resolve_color_env()'s enabling-wins reconciliation outside a command
        # context: FORCE_COLOR wins, then a dumb/unknown TERM or NO_COLOR forces plain
        # text, so this fallback agrees with the env path no context has resolved yet.
        if "FORCE_COLOR" in os.environ:
            return True
        if os.environ.get("TERM", "").lower() in COLOR_DISABLING_TERMS:
            return False
        if "NO_COLOR" in os.environ:
            return False
        return is_a_tty(stream)

    def _style(self, text: str, *, color: bool | None = None) -> str:
        """Apply the configured {class}`~click_extra.styling.Style`, or return bare.

        A no-op when no style was set or color is disabled, so the same call site
        produces colored output on a capable terminal and plain output under
        `NO_COLOR` / a pipe.

        :param text: what to style.
        :param color: override whether any color is applied. `None` follows what
            {meth}`start` resolved for the spinner's own stream, which is what
            the animation wants. A picture of the spinner overrides it, having
            its own answer to whether ANSI survives.
        :return: the text, styled or bare.
        """
        enabled = self._color_enabled if color is None else color
        if enabled and self.style is not None:
            return self.style(text)
        return text

    @property
    def elapsed_time(self) -> float:
        """Seconds elapsed since {meth}`start`, frozen once {meth}`stop` is called.

        Returns `0.0` before the spinner has started.
        """
        if self._start_time is None:
            return 0.0
        end = self._stop_time if self._stop_time is not None else time.monotonic()
        return end - self._start_time

    @property
    def shown(self) -> bool:
        """Whether the spinner has drawn at least one frame to its stream.

        `True` only once an animation frame was actually rendered. It stays
        `False` for a disabled spinner (off a TTY, on a `TERM=dumb` terminal,
        or with `enabled=False`) and for a call that finishes within `delay`,
        before the first frame. Reset by {meth}`start`.

        Use it to gate output that should mirror the spinner's visibility.
        {meth}`ok` and {meth}`fail` write their line unconditionally, so an
        outcome is still recorded in a pipe or log; guard them with `shown` when
        you only want the finisher on screen after a spinner the user actually
        saw::

            with Spinner("Baking bread") as spinner:
                bake()
                if spinner.shown:
                    spinner.ok()
        """
        return self._drawn

    def _clock(self) -> str:
        """The `( elapsed )` timer suffix, or empty when no timer is set.

        `timer=True` uses {func}`~click_extra.humanize.format_duration`; a
        callable `timer` formats {attr}`elapsed_time` itself. The result is
        always wrapped the same way.
        """
        if not self.timer:
            return ""
        return f" ({_format_timer(self.timer, self.elapsed_time)})"

    @property
    def _ordered_frames(self) -> tuple[str, ...]:
        """The frames in the order the animation cycles them, `reverse` applied."""
        return tuple(reversed(self.frames)) if self.reverse else tuple(self.frames)

    def _compose_frame(self, frame: str, *, color: bool | None = None) -> str:
        """Build the line one animation frame draws.

        The glyph, the label and the timer, in the order and the styling the
        animation writes them. Held in one place so a picture of a spinner shows
        what the spinner draws, instead of a second guess at it that drifts the
        first time this composition changes.

        :param frame: one of {attr}`frames`, the glyph the line opens with.
        :param color: see {meth}`_style`.
        :return: the line, ANSI escape sequences included.
        """
        label = f" {self.label}" if self.label else ""
        return self._style(f"{frame}{label}{self._clock()}", color=color)

    def frame_lines(self, *, color: bool = True) -> tuple[str, ...]:
        """Every line this spinner's animation draws, one per frame.

        One turn of the animation, held still. `reverse`, the label, the style
        and the timer all land the way {meth}`start` would draw them, which is
        what an animated capture stacks into a picture of this spinner.

        ```{note}
        The timer is read once, here, so every line carries the same elapsed
        time rather than a counting one: a still cannot show a clock running.
        A spinner that never started reads zero.
        ```

        :param color: style each line. On by default, because a capture renders
            ANSI whatever the terminal the spinner would have drawn on accepts.
        :return: the lines, in the order the animation cycles them.
        """
        return tuple(
            self._compose_frame(frame, color=color) for frame in self._ordered_frames
        )

    @staticmethod
    def _enable_windows_ansi(stream: IO[str]) -> None:
        """Best-effort: turn on virtual-terminal processing for a Windows console.

        Without it, legacy Windows consoles print the spinner's ANSI control codes
        literally (`⠋␛[0m … ␛[K`) instead of animating in place: the recurring
        complaint behind yaspin's Windows issues. Modern terminals (Windows
        Terminal, recent conhost) already enable it; this just covers the
        laggards. A no-op everywhere but Windows, and silent when the console (or
        a non-console stream) refuses the mode.
        """
        # Positive `sys.platform` guard so type checkers treat the body as
        # platform-conditional rather than dead code on a non-Windows host.
        if sys.platform == "win32":
            try:
                # Windows-only standard-library modules, imported lazily so the
                # spinner module still loads on every platform.
                import ctypes
                import msvcrt

                handle = msvcrt.get_osfhandle(stream.fileno())
                kernel32 = ctypes.windll.kernel32
                mode = ctypes.c_uint32()
                if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                    enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
                    kernel32.SetConsoleMode(handle, mode.value | enable_vt)
            except (OSError, ValueError, AttributeError):
                # Raised for a non-console stream (no/closed fileno) or a console
                # that refuses the mode; nothing actionable. On a modern terminal
                # the codes already render, on a truly legacy one they cannot.
                pass

    def start(self) -> None:
        """Begin animating on a background thread, unless the spinner is disabled.

        A disabled spinner (non-TTY stream, or `enabled=False`) returns at once
        without spawning a thread or emitting anything (but still records the
        start time, so a later {meth}`ok` / {meth}`fail` can report a duration).
        """
        # Time the operation even when the spinner is silenced, and resolve color
        # here on the calling thread: the animation thread never sees the Click
        # context that `_resolve_color_enabled` reads.
        self._start_time = time.monotonic()
        self._stop_time = None
        stream = self._resolve_stream()
        self._color_enabled = self._resolve_color_enabled(stream)
        if not self._resolve_enabled(stream):
            return
        # The spinner is about to emit ANSI control codes: make sure a Windows
        # console will interpret rather than echo them.
        self._enable_windows_ansi(stream)
        self._stop.clear()
        self._drawn = False
        self._cursor_hidden = False
        # Advertise the animation so concurrent writers (the logging bridge, see
        # _active_line()) print through echo() instead of over the frame.
        _register_line(self)
        self._thread = threading.Thread(
            target=self._animate,
            args=(stream,),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Halt the animation and erase the spinner line.

        Idempotent and safe to call when the spinner never started. Restores the
        cursor and clears the line only if the animation actually drew to the
        terminal.
        """
        # Freeze the timer first, before the early return, so even a never-drawn
        # spinner reports the operation's duration through `elapsed_time`.
        self._stop_time = time.monotonic()
        # Withdraw from the active registry first, so a concurrent log record
        # emitted during the teardown below goes through the plain path.
        _deregister_line(self)
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join()
        self._thread = None

        # The animation thread has joined, so the draw lock is now free: take it
        # so a concurrent `echo()` from another thread cannot interleave with the
        # final cleanup. Joining before acquiring avoids deadlocking against the
        # lock-holding frame write.
        with self._lock:
            # Undo only what was actually emitted: erase the line if a frame was
            # drawn, and restore the cursor if it was hidden. Reaching this point
            # means the spinner was active, so an opt-in bell rings here too: a
            # disabled or redirected spinner returns above and stays silent.
            cleanup = ""
            if self._drawn:
                cleanup += "\r\x1b[K"
            if self._cursor_hidden:
                cleanup += "\x1b[?25h"
            if self.beep:
                cleanup += "\a"
            if cleanup:
                stream = self._resolve_stream()
                stream.write(cleanup)
                stream.flush()
                self._cursor_hidden = False

    def echo(self, message: str = "") -> None:
        """Print `message` on its own line above the running spinner.

        Click's {func}`click.progressbar` and a bare `print` both fight the
        animation: a frame drawn between the cursor returns and the text mangles
        the line. {meth}`echo` takes the same draw lock as the animation thread,
        erases the in-progress frame, writes `message` followed by a newline,
        and lets the next tick redraw the spinner underneath. It is safe to call
        from another thread while the spinner runs.

        Output goes to the spinner's own `stream` (`stderr` by default), so
        results written to `stdout` never need it. When the spinner is not
        animating (disabled, or a non-TTY stream), it degrades to a plain write
        of `message` with no control codes.
        """
        stream = self._resolve_stream()
        with self._lock:
            # Erase the in-progress frame so the message starts at column 0.
            if self._drawn:
                stream.write("\r\x1b[K")
            stream.write(f"{message}\n")
            stream.flush()

    def ok(self, symbol: str | None = None, *, style: Style | None = None) -> None:
        """Stop the spinner and leave a persistent success line on screen.

        Where {meth}`stop` erases the spinner, {meth}`ok` replaces the final
        frame with `symbol` followed by the current label (and the elapsed time
        when `timer` is set), then keeps that line. `symbol` defaults to the
        themed success glyph {data}`~click_extra.theme.OK_GLYPH` (`✓`), painted
        with the active theme's `success` slot unless `style` overrides it.
        Color is stripped under `--no-color` / `NO_COLOR`; the glyph stays.
        """
        self._finalize(symbol, style, success=True)

    def fail(self, symbol: str | None = None, *, style: Style | None = None) -> None:
        """Stop the spinner and leave a persistent failure line on screen.

        The failure counterpart of {meth}`ok`, defaulting to
        {data}`~click_extra.theme.KO_GLYPH` (`✘`) painted with the active
        theme's `error` slot.
        """
        self._finalize(symbol, style, success=False)

    def _finalize(
        self,
        symbol: str | None,
        style: Style | None,
        *,
        success: bool,
    ) -> None:
        """Stop the animation and write a kept ``{symbol} {label}`` final line.

        Resolves color on the calling thread, stops the spinner (which erases the
        live frame and restores the cursor), then writes the final line in its
        place. The glyph and its paint default to the active theme's success /
        error slots, so a finished spinner matches the rest of a themed CLI.
        Degrades to a plain line when color is disabled or the spinner was never
        shown, so the outcome is still recorded off a TTY.
        """
        # Lazy import to avoid a circular dependency with theme (as parameters.py
        # does); the active theme is resolved here, not frozen at construction.
        from .theme import KO_GLYPH, OK_GLYPH, get_current_theme

        glyph = symbol if symbol is not None else (OK_GLYPH if success else KO_GLYPH)
        if style is None:
            theme = get_current_theme()
            paint = theme.success if success else theme.error
        else:
            paint = style

        stream = self._resolve_stream()
        color_enabled = self._resolve_color_enabled(stream)
        self.stop()
        label = f" {self.label}" if self.label else ""
        clock = self._clock()
        marker = paint(glyph) if color_enabled else glyph
        with self._lock:
            stream.write(f"{marker}{label}{clock}\n")
            stream.flush()

    def _animate(self, stream: IO[str]) -> None:
        """Frame loop run on the background thread.

        Waits `delay` before the first frame, then writes one frame every
        `interval` until {meth}`stop` is called. Every wait goes through the
        stop {class}`~threading.Event`, so the spinner reacts to `stop()`
        immediately instead of sleeping out the current interval. Stream errors
        (a closed terminal) end the loop quietly rather than surfacing a
        traceback from the background thread.
        """
        # A call that finishes within `delay` never draws anything.
        if self._stop.wait(self.delay):
            return
        # Resolve the rotation direction once: `reverse` flips the frame order.
        frames = self._ordered_frames
        try:
            if self.hide_cursor:
                stream.write("\x1b[?25l")
                self._cursor_hidden = True
                stream.flush()
            index = 0
            while not self._stop.is_set():
                content = self._compose_frame(frames[index % len(frames)])
                # Hold the draw lock so a concurrent `echo()` cannot interleave
                # with a half-written frame. Return to the line start, then
                # clear to end-of-line so a shrinking label leaves no stale
                # characters behind.
                with self._lock:
                    stream.write(f"\r{content}\x1b[K")
                    stream.flush()
                    self._drawn = True
                index += 1
                if self._stop.wait(self.interval):
                    break
        except (OSError, ValueError):
            # The stream was closed or detached mid-spin; nothing left to draw.
            return

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Use the spinner as a decorator, with or without parentheses.

        `@Spinner` wraps a function directly; `@Spinner("Loading", …)` first
        configures the spinner, then wraps. Either way the function spins for the
        duration of every call and returns its result untouched. The one instance
        is shared across calls, which is fine for sequential use; give concurrent
        callers their own spinner.
        """
        # Bare `@Spinner`: the instance stood in for the function (captured at
        # construction), so calling it runs that function inside the context.
        if self._decorated is not None:
            with self:
                return self._decorated(*args, **kwargs)

        # `@Spinner(…)`: wrap the single function argument so each call spins.
        (func,) = args

        @functools.wraps(func)
        def wrapper(*call_args: Any, **call_kwargs: Any) -> Any:
            with self:
                return func(*call_args, **call_kwargs)

        return wrapper


def trail_glyph(ok: bool) -> str:
    """Return the themed `✓` or `✘` glyph for a trail line or finisher.

    The success glyph {data}`~click_extra.theme.OK_GLYPH` painted with the active
    theme's `success` slot, or the failure glyph
    {data}`~click_extra.theme.KO_GLYPH` painted with its `error` slot.
    """
    # Lazy import to avoid a circular dependency with theme, as Spinner._finalize
    # does; the active theme is resolved at call time, not import time.
    from .theme import KO_GLYPH, OK_GLYPH, get_current_theme

    theme = get_current_theme()
    return theme.success(OK_GLYPH) if ok else theme.error(KO_GLYPH)


def trail_line(ok: bool, message: str) -> str:
    """Format one `✓`/`✘` trail line: a status glyph followed by `message`."""
    return f"{trail_glyph(ok)} {message}"


def _format_timer(timer: bool | Callable[[float], str], seconds: float) -> str:
    """Format `seconds` for a trail's timer suffix.

    Uses {func}`~click_extra.humanize.format_duration` for `True` (the default
    compact clock: `2.3s`, `1:05`, `1:02:03`), or the given callable for a
    custom format. Callers guard on a truthy `timer` before calling.
    """
    formatter = timer if callable(timer) else format_duration
    return formatter(seconds)


def _time_flag_active() -> bool:
    """Whether the active command's `--time` flag is on.

    `True` when a command context is active and carries the
    {data}`~click_extra.context.START_TIME` marker that
    {class}`~click_extra.execution.TimerOption` sets under `--time`; `False`
    under `--no-time` (its default) or outside any command. The shared signal
    behind `timer=None` on {class}`OperationTrail` and `show_eta=None` on
    {func}`progressbar`, so a trail and a bare bar agree on when to show timing.
    """
    ctx = click.get_current_context(silent=True)
    return ctx is not None and context.get(ctx, context.START_TIME) is not None


def _resolve_timer(
    timer: bool | Callable[[float], str] | None,
) -> bool | Callable[[float], str]:
    """Resolve a trail's `timer` setting, auto-detecting `--time` for `None`.

    An explicit `bool` or callable is returned unchanged; `None` (the trail
    default) follows the CLI's `--time` / `--no-time` flag via
    {func}`_time_flag_active`, mirroring how `enabled=None` auto-detects the
    terminal.
    """
    return _time_flag_active() if timer is None else timer


class _SpinnerIndicator:
    """An {class}`OperationTrail` aggregate indicator backed by a {class}`Spinner`.

    Carries the running ``{label} {done}/{total} {unit}`` tally on one animated
    line while completed outcomes stream above it, and closes on the spinner's
    kept {meth}`~Spinner.ok` / {meth}`~Spinner.fail` line. Used for a concurrent
    batch, where per-call spinners would collide on the shared stream.
    """

    def __init__(
        self,
        *,
        label: str,
        unit: str,
        total: int,
        delay: float,
        enabled: bool | None,
        stream: IO[str] | None,
        spinner: SpinnerPreset | None = None,
        timer: bool | Callable[[float], str] = True,
        clock: Literal["elapsed", "eta"] = "elapsed",
    ) -> None:
        self._label = label
        self._unit = unit
        self._total = total
        self._timer = timer
        # In eta mode a hidden Click bar supplies the rolling-average estimate,
        # shown in the spinner's label; the spinner's own elapsed timer is then
        # off, and finish() appends the total elapsed itself (a done batch has no
        # ETA). Reuses Click's make_step/format_eta rather than reimplementing it.
        self._eta_bar: ProgressBar[int] | None = None
        if timer and clock == "eta" and total > 0:
            self._eta_bar = click.progressbar(range(total))
        self._spinner = Spinner(
            f"{label} 0/{total} {unit}",
            spinner=spinner,
            delay=delay,
            enabled=enabled,
            timer=False if self._eta_bar is not None else timer,
            stream=stream,
        )

    @property
    def shown(self) -> bool:
        return self._spinner.shown

    def __enter__(self) -> Self:
        self._spinner.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._spinner.__exit__(exc_type, exc_val, exc_tb)

    def advance(self, done: int) -> None:
        """Re-label the spinner with the tally, adding the ETA in eta mode."""
        label = f"{self._label} {done}/{self._total} {self._unit}"
        if self._eta_bar is not None:
            self._eta_bar.make_step(done - self._eta_bar.pos)
            eta = self._eta_bar.format_eta()  # "" until a step lets it estimate.
            if eta:
                label = f"{label}  {eta}"
        self._spinner.label = label

    def echo(self, message: str) -> None:
        self._spinner.echo(message)

    def finish(self, ok: bool, summary: str) -> None:
        """Leave the spinner's kept `✓`/`✘` ``summary`` line, elapsed included."""
        if not self._spinner.shown:
            return
        if self._eta_bar is not None:
            # eta mode runs the spinner's own timer off, so append the batch's
            # total elapsed here (a finished batch has no time remaining).
            clock = _format_timer(self._timer, self._spinner.elapsed_time)
            summary = f"{summary} ({clock})"
        self._spinner.label = summary
        (self._spinner.ok if ok else self._spinner.fail)()


# How often the bar refreshes to keep its running elapsed clock ticking. The bar
# has no animation thread of its own (unlike the spinner), so a daemon ticker
# redraws it at this cadence in `clock="elapsed"` mode; matches the spinner's
# default frame interval.
_BAR_TICK_INTERVAL = 0.1


class _BarIndicator:
    """An {class}`OperationTrail` aggregate indicator backed by a determinate
    {func}`click.progressbar`.

    Where {class}`_SpinnerIndicator` narrates an *indeterminate* pulse, this
    carries a real ``{label} [####----] {done}/{total}`` bar (the trail knows
    its `total`), with completed outcomes streaming above it exactly as they
    do over a spinner. It drives Click's bar directly rather than iterating it:
    {meth}`advance` steps and redraws it, {meth}`echo` erases it to slip a
    persistent line above, then redraws it below.

    ```{note}
    Click's {meth}`~click._termui_impl.ProgressBar.render_progress` skips a
    redraw whose line is unchanged, so {meth}`_draw` clears the bar's
    `_last_line` cache to force the post-`echo` redraw. Cursor hiding is left
    to Click (its `BEFORE_BAR` / `AFTER_BAR`); this only restores the cursor
    when it tears the bar down early.
    ```
    """

    def __init__(
        self,
        *,
        label: str,
        unit: str,
        total: int,
        delay: float,
        enabled: bool | None,
        stream: IO[str] | None,
        timer: bool | Callable[[float], str] = True,
        clock: Literal["elapsed", "eta"] = "elapsed",
    ) -> None:
        self._label = label
        self._unit = unit
        self._total = total
        self._delay = delay
        self._enabled = enabled
        self._stream = stream
        self._timer = timer
        self._clock = clock
        self._lock = threading.Lock()
        self._on = False
        self._drawn = False
        self._finished = False
        self._start = 0.0
        self._bar: ProgressBar[int] | None = None
        self._stop_tick = threading.Event()
        self._ticker: threading.Thread | None = None

    def _resolve_stream(self) -> IO[str]:
        return self._stream if self._stream is not None else sys.stderr

    def __enter__(self) -> Self:
        stream = self._resolve_stream()
        self._on = _stream_enabled(self._enabled, stream)
        self._start = time.monotonic()
        # show_pos renders the `{done}/{total}` tally; item_show_func appends the
        # counted unit after it (and, in elapsed mode, a running clock), echoing
        # the spinner's `3/5 feeds` phrasing. The `range(total)` iterable is never
        # consumed (advance() drives the bar directly); it just fixes the length
        # and satisfies the typed overload that carries item_show_func.
        self._bar = click.progressbar(
            range(self._total),
            label=self._label,
            show_pos=True,
            # Click's ETA (remaining time) is shown only in `clock="eta"` mode;
            # `clock="elapsed"` renders a running elapsed clock through
            # item_show_func instead, and a `timer`-off bar shows no time at all.
            show_eta=bool(self._timer) and self._clock == "eta",
            item_show_func=self._render_info,
            file=cast("TextIO", stream),
            hidden=not self._on,
        )
        if self._on:
            # The bar emits ANSI control codes: make a legacy Windows console
            # interpret rather than echo them, as Spinner.start does.
            Spinner._enable_windows_ansi(stream)
            _register_line(self)
            # Draw the empty bar right away (unless a delay defers the first
            # render), so its `0/total` state is visible from the start, like the
            # spinner indicator's animated tally: without this the bar appears
            # only when the first outcome advances it, leaving the screen blank
            # while the batch is already running.
            if self._delay <= 0:
                with self._lock:
                    self._draw()
            # An elapsed clock must keep ticking between outcomes; the bar has no
            # animation thread, so drive periodic redraws from a daemon ticker.
            if self._elapsed_clock():
                self._ticker = threading.Thread(target=self._tick, daemon=True)
                self._ticker.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()

    @property
    def shown(self) -> bool:
        return self._drawn

    def _draw(self) -> None:
        """Force a bar redraw, defeating Click's unchanged-line dedup."""
        assert self._bar is not None
        self._bar._last_line = None
        self._bar.render_progress()
        self._drawn = True

    def _elapsed_clock(self) -> bool:
        """Whether a running elapsed clock is drawn (timing on, `clock="elapsed"`)."""
        return bool(self._timer) and self._clock == "elapsed"

    def _render_info(self, item: int | None) -> str | None:
        """The `item_show_func`: a running elapsed clock plus the unit, or the unit.

        In `clock="elapsed"` mode with timing on, the elapsed time since the bar
        started is prepended to the counted unit (`5.0s  feeds`); an ETA bar or a
        timer-off bar shows just the unit (Click renders any ETA itself).
        """
        if self._elapsed_clock():
            clock = _format_timer(self._timer, time.monotonic() - self._start)
            return f"{clock}  {self._unit}" if self._unit else clock
        return self._unit or None

    def _tick(self) -> None:
        """Redraw periodically so the running elapsed clock keeps ticking.

        The bar, unlike the spinner, has no animation thread; without this the
        elapsed clock would freeze between outcomes. Runs only in elapsed mode:
        an ETA needs no ticking, since Click recomputes it on each step.
        """
        while not self._stop_tick.wait(_BAR_TICK_INTERVAL):
            with self._lock:
                if self._drawn and not self._finished:
                    self._draw()

    def _stop_ticker(self) -> None:
        """Stop and join the elapsed-clock ticker. Idempotent."""
        if self._ticker is not None:
            self._stop_tick.set()
            self._ticker.join()
            self._ticker = None

    def advance(self, done: int) -> None:
        """Step the bar to `done` and redraw it, once past the initial delay."""
        if not self._on:
            return
        assert self._bar is not None
        with self._lock:
            # A batch that finishes within `delay` never draws: remember the
            # position and stay silent, as the spinner does for a quick batch.
            if (time.monotonic() - self._start) < self._delay:
                self._bar.pos = done
                return
            self._bar.make_step(done - self._bar.pos)
            self._draw()

    def echo(self, message: str) -> None:
        """Print `message` as a persistent line above the bar, then redraw it."""
        stream = self._resolve_stream()
        with self._lock:
            if self._drawn:
                stream.write("\r\x1b[K")  # Erase the bar line.
            stream.write(f"{message}\n")  # Persistent line above.
            if self._drawn:
                self._draw()  # Redraw the bar below.
            stream.flush()

    def finish(self, ok: bool, summary: str) -> None:
        """Replace the bar with a kept `✓`/`✘` ``summary`` line, elapsed included."""
        _deregister_line(self)
        self._stop_ticker()
        with self._lock:
            self._finished = True
            if not self._drawn:
                return
            stream = self._resolve_stream()
            clock = (
                f" ({_format_timer(self._timer, time.monotonic() - self._start)})"
                if self._timer
                else ""
            )
            # Erase the bar, keep the finisher in its place, restore the cursor
            # Click hid via BEFORE_BAR.
            stream.write(f"\r\x1b[K{trail_line(ok, summary)}{clock}\n\x1b[?25h")
            stream.flush()
            self._drawn = False

    def stop(self) -> None:
        """Erase the bar and restore the cursor with no kept line. Idempotent.

        The teardown path for an abnormal exit (an exception inside the trail's
        `with` block, where {meth}`finish` never ran).
        """
        _deregister_line(self)
        self._stop_ticker()
        with self._lock:
            if self._finished or not self._drawn:
                self._finished = True
                return
            stream = self._resolve_stream()
            stream.write("\r\x1b[K\x1b[?25h")
            stream.flush()
            self._drawn = False
            self._finished = True


class OperationTrail:
    """A `✓`/`✘` progress trail and finisher for a batch of operations.

    Where {class}`Spinner` narrates *one* long-running call,
    `OperationTrail` reports a *batch* of them: each completed operation
    leaves a persistent {func}`~click_extra.spinner.trail_line` on screen, a
    running `done/total` tally keeps the batch's pulse visible, and
    {meth}`finish` closes with a persistent summary line. The natural
    reporting companion of the concurrency primitives
    {func}`~click_extra.execution.run_jobs` and
    {func}`~click_extra.execution.run_lanes`, rendered one of three ways:

    - **sequential** (`jobs <= 1`): echo each outcome as it lands, with no
      aggregate indicator (each operation is free to keep its own per-call
      {class}`Spinner`). {meth}`finish` appends the elapsed time.
    - **concurrent** (`jobs > 1`): drive one aggregate {class}`Spinner`
      (per-call spinners would collide on the shared stream), buffering
      outcomes until it first draws, then streaming the rest live above it.
      Pick the animation from the
      {data}`~click_extra.spinner_presets.SPINNERS` catalog with `spinner=`.
    - **progress bar** (`progress_bar=True`): drive one aggregate *determinate*
      bar carrying the `{done}/{total}` tally, with outcomes streaming above
      it. Serves sequential and concurrent batches alike, and needs a known
      `total`.

    All render only on an interactive stream unless `enabled` forces the
    matter, so pipes, CI logs and captured test buffers stay clean. The running
    `✓` tally is kept as outcomes land ({attr}`ok_count`), so a caller computes
    no counts of its own.

    Thread-safe: {meth}`mark` may be called from worker threads. Use it as a
    context manager whenever it may run concurrently, to bound the aggregate
    spinner's life; a purely sequential caller may construct it bare.

    ```{code-block} python

    from click_extra.execution import run_jobs
    from click_extra.spinner import OperationTrail

    with OperationTrail(label="Fetching", unit="feeds", total=len(feeds),
                        jobs=jobs) as trail:
        def fetch(feed):
            trail.mark(*pull(feed))  # pull() returns (ok, message).

        list(run_jobs(fetch, feeds, jobs=jobs))
        trail.finish(
            trail.ok_count == len(feeds),
            f"Fetched {trail.ok_count}/{len(feeds)} feeds",
        )
    ```
    """

    def __init__(
        self,
        *,
        label: str = "",
        unit: str = "",
        total: int = 0,
        jobs: int = 1,
        spinner: SpinnerPreset | None = None,
        progress_bar: bool = False,
        timer: bool | Callable[[float], str] | None = None,
        clock: Literal["elapsed", "eta"] = "elapsed",
        enabled: bool | None = None,
        echo_sequential: bool = True,
        delay: float = 0.0,
        stream: IO[str] | None = None,
    ) -> None:
        """Configure (but do not start) the trail.

        :param label: present-tense verb for the running aggregate indicator
            (`"Fetching"`), composed into its ``{label} {done}/{total} {unit}``
            tally.
        :param unit: the noun counted in the tally (`"files"`, `"feeds"`).
        :param total: how many outcomes are expected, for the `done/total`
            count.
        :param jobs: the batch's worker count; `> 1` selects the concurrent
            rendering (one aggregate spinner), `<= 1` the sequential one
            (plain echoed lines).
        :param spinner: a {class}`~click_extra.spinner_presets.SpinnerPreset`
            from the {data}`~click_extra.spinner_presets.SPINNERS` catalog
            (`spinner=SPINNERS["moon"]`) for the concurrent aggregate spinner.
            Ignored by the sequential and progress-bar renderings, and mutually
            exclusive with `progress_bar`.
        :param progress_bar: render the aggregate indicator as a determinate
            {func}`click.progressbar` instead of a spinner, for a sequential or
            concurrent batch alike. Requires a positive `total` (a bar needs a
            length) and is mutually exclusive with `spinner`.
        :param timer: append each operation's and the batch's elapsed time to
            the trail lines and the finisher. `None` (the default) follows the
            CLI's `--time` / `--no-time` flag; `True` forces timing on with
            {func}`~click_extra.humanize.format_duration`'s compact clock, a
            callable `(seconds: float) -> str` forces it on with a custom
            format, and `False` forces it off. Per-operation times come from a
            `seconds` argument to {meth}`mark`, filled in automatically by an
            {meth}`operation` handle.
        :param clock: whether a running aggregate indicator shows *elapsed* time
            (`"elapsed"`, the default: a stopwatch counting up, visible from the
            start) or *remaining* time (`"eta"`: an estimate from the batch's
            rate, appearing only once an outcome lets it be computed). Both the
            progress bar and the concurrent spinner honor `"eta"` (the spinner
            reuses Click's progress-bar estimate, since the trail knows its
            `total`). Per-operation and finisher times are always elapsed.
        :param enabled: force the trail on or off. `None` (the default)
            auto-detects: the sequential echo renders only on an interactive
            stream, and the aggregate indicator applies its own TTY gate.
        :param echo_sequential: whether a sequential batch echoes its outcome
            lines and finisher at all. Turn it off when the batch has another
            output that is the real product (a result table) and the trail
            would be noise; an aggregate indicator is unaffected.
        :param delay: seconds before the aggregate indicator first draws: a
            fast batch then completes without ever flashing one.
        :param stream: where to render; defaults to {data}`sys.stderr` so the
            trail never mixes into `stdout` data.
        :raises ValueError: if `progress_bar` is set without a positive
            `total`, or together with `spinner`, or if `clock` is neither
            `"elapsed"` nor `"eta"`.
        """
        if progress_bar and total <= 0:
            raise ValueError("progress_bar=True requires a positive total.")
        if progress_bar and spinner is not None:
            raise ValueError("progress_bar= and spinner= are mutually exclusive.")
        if clock not in ("elapsed", "eta"):
            raise ValueError('clock must be "elapsed" or "eta".')
        self.label = label
        self.unit = unit
        self.total = total
        self.concurrent = jobs > 1
        self.progress_bar = progress_bar
        # None auto-detects the --time flag; a bool or callable forces it.
        self.timer = _resolve_timer(timer)
        self.clock = clock
        self.spinner_preset = spinner
        self.enabled = enabled
        self.stream = stream
        self._delay = delay
        self._lock = threading.Lock()
        self._done = 0
        self._ok = 0
        self._start = time.monotonic()
        self._indicator: _AggregateIndicator | None = None
        self._buffer: list[str] = []
        # An aggregate indicator (a progress bar, or a spinner for a concurrent
        # batch) owns the live line; the plain sequential echo runs only when
        # there is none. Gate it on an interactive stream unless `enabled`
        # forces the matter, mirroring the indicator's own TTY gate.
        if self.concurrent or progress_bar or not echo_sequential or enabled is False:
            self._echo = False
        elif enabled is True:
            self._echo = True
        else:
            self._echo = is_a_tty(stream if stream is not None else sys.stderr)

    def __enter__(self) -> Self:
        if self.progress_bar:
            self._indicator = _BarIndicator(
                label=self.label,
                unit=self.unit,
                total=self.total,
                delay=self._delay,
                enabled=self.enabled,
                stream=self.stream,
                timer=self.timer,
                clock=self.clock,
            )
        elif self.concurrent:
            self._indicator = _SpinnerIndicator(
                label=self.label,
                unit=self.unit,
                total=self.total,
                delay=self._delay,
                enabled=self.enabled,
                stream=self.stream,
                spinner=self.spinner_preset,
                timer=self.timer,
                clock=self.clock,
            )
        if self._indicator is not None:
            self._indicator.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._indicator is not None:
            self._indicator.__exit__(exc_type, exc_val, exc_tb)
            self._indicator = None

    @property
    def ok_count(self) -> int:
        """How many marked outcomes have succeeded so far."""
        return self._ok

    def _echo_line(self, message: str) -> None:
        """Print one rendered line to the trail's stream."""
        if self.stream is not None:
            click.echo(message, file=self.stream)
        else:
            click.echo(message, err=True)

    def mark(self, ok: bool, message: str, seconds: float | None = None) -> None:
        """Record one `✓`/`✘` outcome: tally it and render its trail line.

        :param seconds: the operation's own elapsed time. When `timer` is on it
            is formatted and appended to `message` as ` (2.3s)`. An
            {meth}`operation` handle fills this in from when it was created;
            pass it yourself when you already hold a duration.
        """
        if self.timer and seconds is not None:
            message = f"{message} ({_format_timer(self.timer, seconds)})"
        with self._lock:
            self._done += 1
            if ok:
                self._ok += 1
            if self._indicator is not None:
                self._buffer.append(trail_line(ok, message))
                self._indicator.advance(self._done)
                self._flush()
            elif self._echo:
                self._echo_line(trail_line(ok, message))

    def _flush(self) -> None:
        # Caller holds the lock. Drain buffered lines once the indicator is
        # drawing; before that, writing would leak into a stream the delayed
        # (or disabled) indicator may never touch.
        if self._indicator is None or not self._indicator.shown:
            return
        for text in self._buffer:
            self._indicator.echo(text)
        self._buffer.clear()

    def finish(self, ok: bool, summary: str) -> None:
        """Render the persistent `✓`/`✘` ``{summary}`` finisher.

        With an aggregate indicator, it becomes the indicator's kept line (a
        spinner's {meth}`Spinner.ok` / {meth}`Spinner.fail` line, or the bar's
        replacement line); sequential without one, a plain echoed line. The
        batch's elapsed time since construction is appended when `timer` is on
        (the default).
        """
        if self._indicator is not None:
            with self._lock:
                self._flush()
            self._indicator.finish(ok, summary)
        elif self._echo:
            if self.timer:
                elapsed = time.monotonic() - self._start
                summary = f"{summary} ({_format_timer(self.timer, elapsed)})"
            self._echo_line(trail_line(ok, summary))

    def operation(self) -> _Operation:
        """Start a timed operation, returning a handle to record its outcome.

        The handle captures the current time; call {meth}`_Operation.mark` when
        the work finishes to record its `✓`/`✘` outcome with the elapsed time
        appended (when `timer` is on). This is how a batch reports
        per-operation timings under concurrency, where the trail itself never
        sees when an operation began:

        ```{code-block} python

        def fetch(feed):
            op = trail.operation()
            ok, message = pull(feed)
            op.mark(ok, message)
        ```
        """
        return _Operation(self)


class _Operation:
    """A single timed operation issued by {meth}`OperationTrail.operation`.

    Captures its start time on creation; {meth}`mark` reports the outcome to the
    parent trail with the elapsed time, so per-operation timings work under
    concurrency where the trail cannot know when each operation began.
    """

    def __init__(self, trail: OperationTrail) -> None:
        self._trail = trail
        self._start = time.monotonic()

    def mark(self, ok: bool, message: str) -> None:
        """Record this operation's `✓`/`✘` outcome, timed from its start."""
        self._trail.mark(ok, message, seconds=time.monotonic() - self._start)


class ProgressOption(ExtraOption):
    """A pre-configured `--progress`/`--no-progress` flag gating spinner display.

    Resolves to a single boolean published at
    {data}`ctx.meta[click_extra.context.PROGRESS] <click_extra.context.PROGRESS>`,
    which a CLI reads to decide whether to start a {class}`Spinner`. The default is
    `True`; `--accessible` lowers it to `False` (via `default_map`) so a
    screen reader is never handed a spinning glyph.

    ```{note}
    Spinner display is intentionally **decoupled from color**, even though both
    emit ANSI. A spinner is an *interactivity* concern, not a color one: it is
    built from cursor-control codes (hide-cursor, carriage return, clear-line),
    which the [NO_COLOR standard](https://no-color.org) explicitly does not
    govern -- it "only signals the user's intention regarding adding ANSI color
    to text output". So `--no-color` / `NO_COLOR` strip the spinner's colors
    but never hide it.

    This matches how the wider ecosystem treats the two axes as orthogonal:
    cargo, npm, pip, Rich, indicatif and ora all gate progress on the terminal
    (and a dedicated `--progress`/`--quiet` knob), while `NO_COLOR` only
    affects color. Rich uses `TERM=dumb` -- not `NO_COLOR` -- as the signal
    to drop cursor-moving features like progress bars.

    The spinner is therefore silenced by two things only, neither of them color:

    - **non-interactive output** -- a pipe, file, CI log, or `TERM=dumb`
      terminal that cannot move the cursor (see `Spinner._resolve_enabled`);
    - **explicit intent** -- `--no-progress` or `--accessible`.
    ```

    This option is eager. It no longer reads `ctx.color`, so its position relative
    to {class}`~click_extra.color.ColorOption` is not load-bearing.
    """

    def set_progress(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Publish whether progress spinners may be shown.

        Stores the resolved `--progress` flag at
        {data}`~click_extra.context.PROGRESS`. Deliberately independent of color:
        see the {class}`ProgressOption` note for why a spinner is gated on
        interactivity (TTY / `TERM=dumb`) and `--accessible`, never on
        `--no-color` / `NO_COLOR`.
        """
        context.set(ctx, context.PROGRESS, value)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=True,
        default=True,
        is_eager=True,
        expose_value=False,
        help=_(
            "Show progress indicators during long operations. Disabled for "
            "non-interactive output (pipes, dumb terminals, CI) and by --accessible."
        ),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--progress/--no-progress",)

        kwargs.setdefault("callback", self.set_progress)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )


V = TypeVar("V")


def _flush_final_position(bar: ProgressBar[Any]) -> None:
    """Make the bar render its true final position on finish.

    Works around [pallets/click#3571](https://github.com/pallets/click/issues/3571):
    Click's {meth}`~click._termui_impl.ProgressBar.update` only applies and
    redraws accumulated steps once they reach `update_min_steps`, dropping the
    trailing sub-threshold batch. A bar whose `length` is not a multiple of
    `update_min_steps` (with `show_pos=True`) then freezes below completion:
    `14/20`, not `20/20`, for `length=20` and `update_min_steps=7`. Wrapping
    {meth}`render_finish` flushes those pending steps and redraws once more, so
    the kept line shows the real final position. A no-op for the default
    `update_min_steps=1`, where nothing is ever left pending.
    """
    inner_render_finish = bar.render_finish

    def render_finish() -> None:
        pending = bar._completed_intervals
        if pending:
            bar.make_step(pending)
            bar._completed_intervals = 0
            bar.render_progress()
        inner_render_finish()

    bar.render_finish = render_finish  # type: ignore[method-assign]


def progressbar(
    iterable: Iterable[V] | None = None,
    length: int | None = None,
    label: str | None = None,
    hidden: bool | None = None,
    show_eta: bool | None = None,
    **kwargs: Any,
) -> ProgressBar[V]:
    """Drop-in for {func}`click.progressbar` honoring `--progress` and `--time`.

    Click's own progress bar is *determinate*, the counterpart to the
    indeterminate {class}`Spinner`. This thin wrapper gates its visibility on the
    same {data}`~click_extra.context.PROGRESS` flag the spinner uses, so a single
    `--no-progress` (or `--accessible`, which lowers the `progress` default)
    silences both, and gates its estimated-time display on `--time`.

    :param hidden: tri-state. Left at its default `None`, the bar follows the
        resolved `--progress` flag: hidden when the user (or `--accessible`)
        turned progress off, shown otherwise. An explicit `True` or `False`
        forces the bar regardless, mirroring how an explicit `color=` argument
        overrides `ctx.color` on {func}`click.echo`. With no active context (the
        bar used outside a Click command) it defaults to shown.
    :param show_eta: tri-state, like `hidden`. Left at its default `None`, the
        estimated-time-remaining display follows the `--time` / `--no-time`
        flag: shown under `--time`, hidden otherwise (its default, or outside a
        command). An explicit `True` or `False` forces it, keeping a bare bar's
        timing in step with an {class}`OperationTrail`'s `timer`. Click's own
        default is `True`.

    ```{note}
    The `--progress` flag gates visibility and `--time` the ETA. Color is
    already handled upstream: Click renders the bar through {func}`click.echo`,
    whose `color=None` resolves against `ctx.color`, so `--no-color` /
    `NO_COLOR` strip the bar's ANSI without any work from this wrapper.
    ```
    """
    if hidden is None:
        ctx = click.get_current_context(silent=True)
        hidden = ctx is not None and not context.get(ctx, context.PROGRESS, True)
    if show_eta is None:
        # The ETA follows --time / --no-time, like a trail's timer, so a bare
        # bar and a trail agree on when to show timing.
        show_eta = _time_flag_active()
    bar = click.progressbar(
        iterable,
        length=length,
        label=label,
        hidden=hidden,
        show_eta=show_eta,
        **kwargs,
    )
    # Repair the final-position freeze of pallets/click#3571 (harmless otherwise).
    _flush_final_position(bar)
    return bar


# Max display width (terminal cells) of the frame preview column.
_SPINNER_PREVIEW_WIDTH = 56


def _spinner_preview(preset: SpinnerPreset) -> str:
    """Join leading frames into a preview within the display-width budget.

    Frames are measured by terminal cell width ({func}`wcwidth.wcswidth`), not by
    code points, so 1-cell glyphs and 2-cell emoji fill the column consistently
    rather than letting an emoji-heavy preview balloon it. Emoji variation
    selectors (`U+FE0F`) are dropped: `wcwidth` sizes the promoted emoji at
    two cells while many terminals render the bare symbol in one, and that
    disagreement misaligns the table. Wide animations (`shark`, `pong`,
    `dots-8bit`, …) stop at the budget with a `… (+N)` tail.
    """
    shown: list[str] = []
    width = 0
    for frame in preset.frames:
        glyph = frame.replace("\ufe0f", "")  # Drop emoji variation selectors.
        cost = max(wcswidth(glyph), 0) + (1 if shown else 0)  # +1 joining space.
        if width + cost > _SPINNER_PREVIEW_WIDTH:
            break
        shown.append(glyph)
        width += cost
    preview = " ".join(shown)
    remaining = len(preset.frames) - len(shown)
    if remaining:
        preview += f" … (+{remaining})"
    return preview


# A curated, visually-distinct default selection for the live tour.
_DEFAULT_SHOWCASE = (
    "dots",
    "line",
    "moon",
    "clock",
    "earth",
    "bouncing-bar",
    "arc",
    "pong",
    "shark",
    "mindblown",
)


# The live tour aims for _TOUR_CYCLES full cycles per spinner, then bounds the
# dwell to at least _TOUR_MIN seconds (so a snappy spinner stays watchable) and
# at most _TOUR_CAP seconds (so a long or slow one does not monopolize the tour).
_TOUR_CYCLES = 3
_TOUR_MIN = 2.0
_TOUR_CAP = 3.0


def _tour_duration(preset: SpinnerPreset) -> float:
    """Seconds the live tour dwells on a spinner.

    Aims for {data}`_TOUR_CYCLES` full cycles (one cycle is a pass through every
    frame), then clamps to `[_TOUR_MIN, _TOUR_CAP]` seconds: a snappy spinner is
    held at least {data}`_TOUR_MIN` seconds so it is watchable, while a long or
    slow one is capped at {data}`_TOUR_CAP`. The cap never trims below a single
    full cycle, so even a 256-frame spinner completes one loop.
    """
    one_cycle = len(preset.frames) * preset.interval
    capped = min(_TOUR_CYCLES * one_cycle, max(_TOUR_CAP, one_cycle))
    return max(_TOUR_MIN, capped)


def _animate_spinners(names: list[str]) -> None:
    """Spin each named catalog animation live, with its label and elapsed timer.

    Each spinner runs for its {func}`_tour_duration` (up to {data}`_TOUR_CYCLES`
    cycles, capped at {data}`_TOUR_CAP` seconds) before moving on, then leaves a
    `✓` success line behind. Interactive terminals only.
    """
    for name in names:
        preset = SPINNERS[name]
        with Spinner(name, spinner=preset, timer=True) as spinner:
            time.sleep(_tour_duration(preset))
            spinner.ok()
