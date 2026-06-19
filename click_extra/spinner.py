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

Click ships :func:`click.progressbar`, but it is *determinate*: it needs a known
length or an iterable to advance through. Some work has no measurable progress:
a blocking subprocess, a network round-trip, a query whose duration is unknown.
For those, the only honest feedback is "something is happening".

:class:`Spinner` fills that gap. It animates a small frame sequence on a daemon
thread, so the caller can stay blocked in a single call (``communicate()``,
``urlopen()``, ...) while the spinner keeps turning:

.. code-block:: python

    from time import sleep

    from click_extra import Spinner

    with Spinner("Brewing tea"):
        sleep(5)  # A blocking call with no measurable progress.

.. caution::
    The spinner draws with carriage returns and ANSI control codes, so it is a
    no-op whenever its output stream is not a TTY (a pipe, a file, a captured
    test buffer, a CI log), unless ``enabled`` is forced. This keeps redirected
    output and machine-readable formats clean.
"""

from __future__ import annotations

import sys
import threading

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType
    from typing import IO, Final

    from typing_extensions import Self


ASCII_SPINNER_FRAMES: Final = ("-", "\\", "|", "/")
"""Plain ASCII animation frames, for terminals or fonts lacking Unicode glyphs."""

SPINNER_FRAMES: Final = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
"""Default animation frames: the ubiquitous Braille-dots spinner.

Ten frames give a smooth rotation in any UTF-8 terminal. Fall back to
:data:`ASCII_SPINNER_FRAMES` where Braille glyphs are unavailable.
"""


class Spinner:
    """A thread-animated, indeterminate progress spinner usable as a context
    manager.

    The animation runs on a background daemon thread, leaving the calling thread
    free to block on the actual work. Entering the context (or calling
    :meth:`start`) begins the animation; leaving it (or calling :meth:`stop`)
    halts the thread and erases the spinner line so it never lingers above the
    next output.

    .. note::
        A single :class:`Spinner` instance drives one animation at a time. mpm
        and similar tools run their subprocesses sequentially, so one shared
        instance whose :attr:`label` is reassigned between steps is enough; for
        concurrent work, use one instance per thread.
    """

    label: str
    """Text drawn after the spinner glyph.

    Reassign it at any time while the spinner runs to reflect the current step;
    the animation thread reads it afresh on every frame.
    """

    def __init__(
        self,
        label: str = "",
        *,
        frames: Sequence[str] = SPINNER_FRAMES,
        reverse: bool = False,
        interval: float = 0.1,
        delay: float = 0.0,
        stream: IO[str] | None = None,
        enabled: bool | None = None,
        hide_cursor: bool = True,
        beep: bool = False,
    ) -> None:
        """Configure (but do not start) the spinner.

        :param label: text shown after the spinner glyph.
        :param frames: the animation frames, cycled in order.
        :param reverse: cycle the frames backwards, spinning the animation the
            other way. Set it when the rotation runs counter to what you expect;
            it composes with any custom ``frames``.
        :param interval: seconds between two frames.
        :param delay: seconds to wait before drawing the first frame. A non-zero
            delay keeps the spinner silent for calls that finish quickly, so it
            only surfaces once an operation is genuinely slow.
        :param stream: where to draw; defaults to :data:`sys.stderr` so the
            spinner never mixes into ``stdout`` data.
        :param enabled: force the spinner on or off. ``None`` (the default)
            auto-detects, animating only when ``stream`` is a TTY.
        :param hide_cursor: hide the text cursor while spinning and restore it on
            stop.
        :param beep: ring the terminal bell once when the spinner stops. It
            fires only when the spinner was active, so a disabled or redirected
            spinner stays silent.
        """
        self.label = label
        self.frames = frames
        self.reverse = reverse
        self.interval = interval
        self.delay = delay
        self.stream = stream
        self.enabled = enabled
        self.hide_cursor = hide_cursor
        self.beep = beep

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._drawn = False
        self._cursor_hidden = False

    def _resolve_stream(self) -> IO[str]:
        """Return the explicit ``stream``, or default to :data:`sys.stderr`.

        Resolved lazily so a stream swapped in after construction (as test
        harnesses do) is honored.
        """
        return self.stream if self.stream is not None else sys.stderr

    def _resolve_enabled(self, stream: IO[str]) -> bool:
        """Decide whether to animate, honoring an explicit ``enabled`` override.

        Falls back to TTY detection: a non-interactive stream (pipe, file,
        captured buffer) yields a silent no-op spinner.
        """
        if self.enabled is not None:
            return self.enabled
        isatty = getattr(stream, "isatty", None)
        return bool(isatty and isatty())

    def start(self) -> None:
        """Begin animating on a background thread, unless the spinner is disabled.

        A disabled spinner (non-TTY stream, or ``enabled=False``) returns at once
        without spawning a thread or emitting anything.
        """
        stream = self._resolve_stream()
        if not self._resolve_enabled(stream):
            return
        self._stop.clear()
        self._drawn = False
        self._cursor_hidden = False
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
        """Print ``message`` on its own line above the running spinner.

        Click's :func:`click.progressbar` and a bare ``print`` both fight the
        animation: a frame drawn between the cursor returns and the text mangles
        the line. :meth:`echo` takes the same draw lock as the animation thread,
        erases the in-progress frame, writes ``message`` followed by a newline,
        and lets the next tick redraw the spinner underneath. It is safe to call
        from another thread while the spinner runs.

        Output goes to the spinner's own ``stream`` (``stderr`` by default), so
        results written to ``stdout`` never need it. When the spinner is not
        animating (disabled, or a non-TTY stream), it degrades to a plain write
        of ``message`` with no control codes.
        """
        stream = self._resolve_stream()
        with self._lock:
            # Erase the in-progress frame so the message starts at column 0.
            if self._drawn:
                stream.write("\r\x1b[K")
            stream.write(f"{message}\n")
            stream.flush()

    def _animate(self, stream: IO[str]) -> None:
        """Frame loop run on the background thread.

        Waits ``delay`` before the first frame, then writes one frame every
        ``interval`` until :meth:`stop` is called. Every wait goes through the
        stop :class:`~threading.Event`, so the spinner reacts to ``stop()``
        immediately instead of sleeping out the current interval. Stream errors
        (a closed terminal) end the loop quietly rather than surfacing a
        traceback from the background thread.
        """
        # A call that finishes within `delay` never draws anything.
        if self._stop.wait(self.delay):
            return
        # Resolve the rotation direction once: `reverse` flips the frame order.
        frames = tuple(reversed(self.frames)) if self.reverse else self.frames
        try:
            if self.hide_cursor:
                stream.write("\x1b[?25l")
                self._cursor_hidden = True
                stream.flush()
            index = 0
            while not self._stop.is_set():
                frame = frames[index % len(frames)]
                suffix = f" {self.label}" if self.label else ""
                # Hold the draw lock so a concurrent `echo()` cannot interleave
                # with a half-written frame. Return to the line start, then
                # clear to end-of-line so a shrinking label leaves no stale
                # characters behind.
                with self._lock:
                    stream.write(f"\r{frame}{suffix}\x1b[K")
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
