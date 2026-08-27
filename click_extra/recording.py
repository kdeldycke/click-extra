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
"""Rebuild a terminal's screen from the stream a command writes at it.

A command that animates does not print its frames one after another: it prints
one, returns the cursor to the start of the line, and prints the next over it.
The stream therefore says what *changed*, and the frames only exist once
something replays those changes against a screen. That replay is what this
module does.

```{note}
The vocabulary is deliberately small. A spinner and a progress bar move the
cursor with a carriage return, clear what they are about to redraw with an
erase-in-line, and end a kept line with a newline. Following those, plus the
color codes that travel with the text, is enough to recover their frames, and it
costs no dependency. Anything addressing the cursor by coordinate, clearing the
screen or switching to the alternate buffer is out of scope: a full-screen
program is not what a capture pictures.
```

```{todo}
Read a full-screen program through [pyte](https://github.com/selectel/pyte)
behind an optional extra, should picturing one ever be asked for. The screen
below would stay the default, so the common case keeps costing no dependency.
```
"""

from __future__ import annotations

import io
import os
import re
import select
import subprocess
import time
from typing import NamedTuple

from extra_platforms import is_unix
from wcwidth import wcswidth

from .color import forced_color
from .execution import args_cleanup
from .screenshot import CAPTURE_TERMINAL_HINTS, DEFAULT_COLUMNS, CaptureBackground

# A pseudo-terminal is what makes a CLI checking `isatty` animate for a
# recorder, and `pty` reaches for `termios`, which Windows does not ship. The
# import is conditional rather than buried in the function needing it, so the
# platform this module is narrower on stays readable from its head.
if is_unix():
    import fcntl
    import pty
    import struct
    import termios

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from .execution import TArg, TNestedArgs

CSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
"""One control sequence, from the escape that opens it to the letter ending it.

Broad on purpose: the sequences this screen ignores have to be *recognized* to
be dropped, or their parameter digits would land on the screen as text.
"""

PARTIAL_CSI_RE = re.compile(r"\x1b(\[[0-9;?]*)?$")
"""The opening of a control sequence the rest of which has not arrived yet.

A recorder reads whatever the terminal hands it, on boundaries that answer to
the pipe rather than to the stream: a sequence routinely straddles two reads.
Recognizing the half that arrived first is what keeps its bracket and digits off
the screen, where they would otherwise read as text a command never printed.
"""

DEFAULT_QUANTUM = 0.01
"""Grid a recording's frame durations are rounded onto, in seconds.

Ten milliseconds is coarser than the jitter two runs of one unchanged command
differ by, and finer than any frame worth picturing: the fastest bundled spinner
holds one for eighty. See {func}`quantize`.
"""

DEFAULT_ROWS = 24
"""Height of the terminal a recording runs its command in, in characters.

A width is what a CLI wraps to and therefore what a capture pictures, so it is
stated per recording. A height only has to be tall enough that nothing scrolls
away before the screen is read, which this is.
"""

READ_POLL = 0.02
"""Seconds a recording waits on the terminal before checking the command again.

Short enough to time a frame of the fastest bundled spinner, whose interval is
80 milliseconds, and long enough that waiting costs no measurable spin.
"""

READ_SIZE = 65536
"""Bytes read from the terminal at once.

Well past any single frame, so a frame arrives whole in the ordinary case. The
screen handles a sequence split across two reads regardless, see
{data}`PARTIAL_CSI_RE`.
"""

ERASE_IN_LINE = "K"
"""Final letter of the sequence clearing a line from the cursor onward."""

SELECT_GRAPHIC_RENDITION = "m"
"""Final letter of the sequence setting colors and attributes.

The one class of sequence kept in the screen's text rather than acted on: it
carries no cursor movement, and a capture renders it as the color it names.
"""


class TerminalScreen:
    """The text a terminal shows, rebuilt from what was written at it.

    Rows accumulate as a command writes. A carriage return moves the cursor back
    to the start of the row it is on, so what follows lands over what is already
    there, which is how an animation redraws itself in place.

    ```{caution}
    Overwriting is whole-row rather than per-cell: a write landing on column
    zero replaces the row instead of covering its first few cells. Every
    animation this screen exists for redraws its row in full and ends with an
    erase-in-line, so the two agree there. They part on a command that overwrites
    a *prefix* and leaves a longer tail behind, where a terminal keeps the tail
    and this screen drops it. Tracking that faithfully means holding a style per
    cell, which is a full emulator and the dependency this one avoids.
    ```
    """

    def __init__(self) -> None:
        """Start on a single empty row, with the cursor at its start."""
        self.rows: list[str] = [""]
        self._column = 0
        self._partial = ""

    @property
    def display(self) -> str:
        """The screen as it stands, rows joined by newlines."""
        return "\n".join(self.rows)

    def feed(self, text: str) -> None:
        """Replay what a command wrote, moving the screen to what it now shows.

        Safe to call with the stream cut anywhere: a control sequence straddling
        two calls is held until the rest of it arrives. A sequence still
        unfinished when the stream ends never reaches the screen, having named
        nothing to draw.

        :param text: the stream, control sequences and all.
        """
        text = self._partial + text
        self._partial = ""
        position = 0
        for sequence in CSI_RE.finditer(text):
            self._write(text[position : sequence.start()])
            self._control(sequence.group())
            position = sequence.end()

        tail = text[position:]
        opening = PARTIAL_CSI_RE.search(tail)
        if opening:
            self._partial = tail[opening.start() :]
            tail = tail[: opening.start()]
        self._write(tail)

    def _control(self, sequence: str) -> None:
        """Act on one control sequence, or drop it when it is out of scope."""
        final = sequence[-1]
        if final == SELECT_GRAPHIC_RENDITION:
            # Styling travels with the text it wraps: kept, never acted on.
            self.rows[-1] += sequence
        elif final == ERASE_IN_LINE and not self._column:
            # Cleared from the start of the row, which empties the whole of it.
            # Past the start, the row already holds only what was written since
            # the cursor came back, so there is nothing left to erase.
            self.rows[-1] = ""

    def _write(self, text: str) -> None:
        """Lay printable text on the screen, one row per newline it carries."""
        for line_index, line in enumerate(text.split("\n")):
            if line_index:
                self.rows.append("")
                self._column = 0
            for chunk_index, chunk in enumerate(line.split("\r")):
                if chunk_index:
                    # The cursor goes back to the start of the row, which this
                    # screen redraws whole: see the class's caution. Clearing
                    # here rather than when the next text lands is what keeps a
                    # color set between the return and the text it wraps.
                    self.rows[-1] = ""
                    self._column = 0
                if not chunk:
                    continue
                self.rows[-1] += chunk
                # A wide glyph covers the two cells it is drawn with. Text
                # carrying something unmeasurable reads as zero rather than as
                # the -1 wcswidth answers with.
                self._column += max(wcswidth(chunk), 0)


class Frame(NamedTuple):
    """One screen a recording held, and how long it held it."""

    text: str
    """What the terminal showed, ANSI escape sequences included."""

    duration: float
    """Seconds the screen stayed that way before the next frame replaced it."""


class ScreenRecorder(io.TextIOBase):
    """A stream that keeps every screen written at it, and when.

    Stands in for a terminal without being one. It answers {meth}`isatty` in the
    affirmative, which is the whole question a spinner or a progress bar asks
    before deciding to animate, so handing one to a `stream` argument records an
    animation in-process: no pseudo-terminal, and therefore every platform.

    ```{note}
    This is the path a documentation build takes. {func}`record_command` is for
    a command this process does not host, which has no such stream to be handed
    and needs a pseudo-terminal instead.
    ```
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """Start on a blank screen, with nothing recorded.

        :param clock: what the recorder reads the time off. Stated so a test can
            hand it a clock that does not depend on how busy the machine is.
        """
        self._screen = TerminalScreen()
        self._clock = clock
        self._samples: list[tuple[float, str]] = []

    def isatty(self) -> bool:
        """Claim to be a terminal, which is what makes a CLI animate at all."""
        return True

    def writable(self) -> bool:
        """Claim to be writable, as a terminal is."""
        return True

    def write(self, text: str) -> int:
        """Replay what was written and note the screen it leaves behind.

        :param text: the stream, control sequences and all.
        :return: how much was written, as a stream is expected to report.
        """
        self._screen.feed(text)
        self._samples.append((self._clock(), self._screen.display))
        return len(text)

    def frames(self, *, end: float | None = None) -> tuple[Frame, ...]:
        """Coalesce what was recorded into the frames the screen held.

        A write changing nothing on screen is not a frame, and neither is a
        screen holding nothing but blanks: an animation erases its line before
        printing the result underneath, and neither that erasure nor the newline
        ending it is a picture. What is left is one frame per distinct screen,
        each lasting until the next replaced it.

        ```{caution}
        The durations are wall-clock, so they answer to how busy the machine was
        and differ a little between two runs of the same command. Quantize them
        before committing what they time.
        ```

        :param end: when the recording stopped, which is how long the last frame
            lasted. Defaults to now.
        :return: the frames, in the order they were drawn.
        """
        kept: list[tuple[float, str]] = []
        for at, display in self._samples:
            if kept and kept[-1][1] == display:
                continue
            kept.append((at, display))

        finish = self._clock() if end is None else end
        frames = []
        for index, (at, display) in enumerate(kept):
            following = kept[index + 1][0] if index + 1 < len(kept) else finish
            span = following - at
            if display.strip() and span > 0:
                frames.append(Frame(display, span))
        return tuple(frames)


def _pin_window_size(descriptor: int, rows: int, columns: int) -> None:
    """Tell a pseudo-terminal how big it is, so a CLI wraps to that width.

    A terminal that never states its size answers the usual query with zeros,
    and a CLI reading that falls back to whatever width it assumes. The capture
    would then picture a screen laid out for a terminal nobody chose.

    :param descriptor: the pseudo-terminal's child end.
    :param rows: height, in character cells.
    :param columns: width, in character cells.
    """
    fcntl.ioctl(
        descriptor, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0)
    )


def record_command(
    args: TArg | TNestedArgs,
    *,
    columns: int = DEFAULT_COLUMNS,
    rows: int = DEFAULT_ROWS,
    background: CaptureBackground = CaptureBackground.DARK,
    duration: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[Frame, ...]:
    """Run a command under a pseudo-terminal and record the screens it draws.

    An animation is the one thing a pipe cannot capture. A spinner asks whether
    its stream is a terminal and stays silent when it is not, so a command run
    the ordinary way prints its result and none of the frames leading to it.
    Forcing color through the environment does not help: that answers a
    different question. Only a pseudo-terminal answers this one.

    ```{caution}
    Unix only. A pseudo-terminal is `termios` and `pty`, neither of which
    Windows ships, and reaching ConPTY means a dependency. Recording a spinner
    this process *hosts* needs none of that: hand a {class}`ScreenRecorder` to
    its `stream` and it animates on any platform.
    ```

    Both the command's output and its errors are read, the spinner drawing on
    the latter. What comes back is timed by the wall clock and therefore differs
    a little between two runs: quantize the durations before committing them.

    :param args: the command line, in the nested form
        {func}`~click_extra.execution.run_cli` accepts.
    :param columns: width of the terminal it is run in, in characters.
    :param rows: height of that terminal, in characters.
    :param background: chrome the recording is headed for, stated to the command
        the way a terminal would, see
        {data}`~click_extra.screenshot.CAPTURE_TERMINAL_HINTS`.
    :param duration: seconds to record before stopping the command. `None`
        records until it exits on its own.
    :param clock: what the recorder reads the time off.
    :return: the frames the terminal held, in order.
    :raises NotImplementedError: on a platform with no pseudo-terminal.
    """
    if not is_unix():
        raise NotImplementedError(
            "Recording a command needs a pseudo-terminal, which this platform "
            "does not provide. A spinner running in this process records "
            "anywhere through a ScreenRecorder stream."
        )

    with forced_color():
        environment = dict(os.environ)
    environment.update(CAPTURE_TERMINAL_HINTS[background])
    environment["COLUMNS"] = str(columns)
    environment["LINES"] = str(rows)

    recorder = ScreenRecorder(clock=clock)
    parent, child = pty.openpty()
    _pin_window_size(child, rows, columns)
    started = clock()
    process = subprocess.Popen(
        args_cleanup(args),
        stdin=child,
        stdout=child,
        stderr=child,
        env=environment,
        close_fds=True,
    )
    # The parent holds the only reading end from here on: leaving the child's
    # open would keep the read blocking forever after the command exits.
    os.close(child)
    try:
        while True:
            if duration is not None and clock() - started >= duration:
                break
            readable, _, _ = select.select([parent], [], [], READ_POLL)
            if not readable:
                if process.poll() is not None:
                    break
                continue
            try:
                written = os.read(parent, READ_SIZE)
            except OSError:
                # The child closed its end, which a pseudo-terminal reports as
                # an error rather than as the end of a file.
                break
            if not written:
                break
            recorder.write(written.decode("UTF-8", errors="replace"))
    finally:
        os.close(parent)
        if process.poll() is None:
            process.terminate()
        process.wait()

    return recorder.frames(end=clock())


def quantize(
    frames: Sequence[Frame],
    quantum: float = DEFAULT_QUANTUM,
) -> tuple[Frame, ...]:
    """Round each frame's duration onto a grid, so a rerun times it the same.

    A recording is timed by the wall clock, so two runs of one unchanged command
    differ by a few milliseconds a frame. Rounding onto a grid coarser than that
    jitter lands both on the same numbers, which is what an asset rewritten on
    every build needs to stay byte-identical.

    ```{caution}
    This settles jitter and nothing else. A frame the scheduler dropped leaves a
    shorter recording of the same frames, which no rounding recovers. That case
    is answered a layer up, by
    {func}`~click_extra.screenshot.animation_digest`, which fingerprints the
    frames a cycle holds rather than how many of them were caught.
    ```

    :param frames: what was recorded.
    :param quantum: seconds per grid step.
    :return: the same frames, timed on the grid.
    :raises ValueError: when the grid step is not positive.
    """
    if quantum <= 0:
        raise ValueError(f"{quantum} is not a grid step, which is positive.")
    return tuple(
        # A frame shorter than half a step still keeps a whole one: it was
        # drawn, so rounding it away would picture less than what ran.
        Frame(frame.text, round(max(round(frame.duration / quantum), 1) * quantum, 9))
        for frame in frames
    )
