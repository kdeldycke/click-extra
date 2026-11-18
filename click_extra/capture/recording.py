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
"""Record the screens a terminal shows while a command writes at it.

A command that animates does not print its frames one after another: it prints
one, returns the cursor to the start of the line, and prints the next over it. A
full-screen program goes further and redraws any cell it likes. The stream
therefore says what *changed*, and the frames only exist once something replays
those changes against a screen. {class}`~click_extra.capture.terminal.TerminalScreen`
is that screen, and this module notes what it shows over time.
"""

from __future__ import annotations

import codecs
import io
import os
import re
import select
import struct
import subprocess
import time
import warnings
from itertools import pairwise
from typing import Any, NamedTuple, cast

from ..ansi import CSI_PATTERN, CSI_PREFIX_PATTERN, RESET
from ..color import TerminalBackground, forced_color
from ..envvar import env_copy
from ..execution import _stop_process, _track, _untrack, args_cleanup
from ..layout import number_frames
from . import terminal as _terminal
from .presets import Chrome
from .screenshot import (
    DEFAULT_COLUMNS,
    append_prompt,
    capture_environment,
    prompt_line,
    render,
)
from .svg import AUTO_HOLD

# A pseudo-terminal is what makes a CLI checking `isatty` animate for a
# recorder, and `pty` reaches for `termios`, which Windows does not ship. The
# import is attempted rather than buried in the function needing it, so the
# platform this module is narrower on stays readable from its head, and it is
# the import itself that is asked rather than a platform probe, which would
# charge every CLI the whole platform detection on startup.
try:
    import fcntl
    import pty
    import termios
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]
    pty = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from ..execution import TArg, TNestedArgs
    from .presets import Cursor, TerminalPalette, TerminalPreset
    from .svg import THold

CSI_RE = re.compile(CSI_PATTERN)
"""One control sequence, from the escape that opens it to the final byte ending it.

Broad on purpose: a typed prompt is cut between two characters, never inside an
escape, so every sequence has to be *recognized* whole, see {func}`ansi_prefix`.
The grammar is the one {data}`~click_extra.ansi.CSI_PATTERN` states, so a
sequence with an intermediate byte, like the `ESC [ 2 SP q` setting the
cursor's shape, counts as one too.
"""

DEFAULT_QUANTUM = 0.01
"""Grid a recording's frame durations are rounded onto, in seconds.

Ten milliseconds is coarser than the jitter two runs of one unchanged command
differ by, and finer than any frame worth picturing: the fastest bundled spinner
holds one for eighty. See {func}`quantize`.
"""

DEFAULT_RECORDING_HOLD: THold = AUTO_HOLD
"""How long a recorded animation holds its last frame before starting over.

A recording ends somewhere, and the end is usually its point: the trail filled
in, the bar run out, the outcome landed. Looping straight back gives a reader no
time to read any of it, and how much time reading takes depends on how much the
ending shows, so the default scales with it: see
{func}`~click_extra.capture.svg.auto_hold`. A declared animation cycles in place
and ends nowhere, so it holds for nothing unless a page asks.
"""

DEFAULT_RECORDING_BLANK = 0.6
"""Seconds of empty screen closing a recorded animation's cycle.

Long enough to read as the loop turning over, short enough not to read as the
image going blank.
"""

DEFAULT_ROWS = 24
"""Height of the terminal a recording runs its command in, in characters.

A width is what a CLI wraps to and therefore what a capture pictures, so it is
stated per recording. A height only has to be tall enough that nothing scrolls
away before the screen is read, which this is.
"""

DEFAULT_SUBMIT = 0.4
"""Seconds a finished command line waits before its output starts, by default.

The beat between the last character and the return key. Long enough that the
two read as separate acts, short enough that the animation does not appear to
have stalled. See {func}`type_line`.
"""

DEFAULT_TYPING = 0.05
"""Seconds one character of a typed command line takes to appear, by default.

A brisk but readable rate: a reader follows what is being typed rather than
watching a line materialize. Slower than any real typist, which is the point,
since the line is there to be read and not to be raced. See {func}`type_line`.
"""

READ_POLL = 0.02
"""Seconds a recording waits on the terminal before checking the command again.

Short enough to time a frame of the fastest bundled spinner, whose interval is
80 milliseconds, and long enough that waiting costs no measurable spin.
"""

READ_SIZE = 65536
"""Bytes read from the terminal at once.

Well past any single frame, but a pseudo-terminal still hands a large redraw
back in several reads, see {data}`REDRAW_GAP`. The screen holds a sequence split
across two reads until its tail arrives.
"""

RECORDING_TERM = "xterm-256color"
"""Terminal a recording names to its command, through `TERM`.

A full-screen program looks its terminal up in the terminfo database and writes
the sequences that entry lists, so the name decides the vocabulary
{class}`~click_extra.capture.terminal.TerminalScreen` has to read. Stating it
keeps a recording from inheriting whatever terminal it runs from, and gives a
program run where `TERM` is unset, like a CI runner, an entry to find at all.
"""

REDRAW_GAP = 0.01
"""Seconds of quiet that close a redraw, in a recording read off a terminal.

A program draws a screen in one write, which a pseudo-terminal hands back in as
many reads as its buffer takes. A screen noted between two of them would picture
a half-drawn frame. The reads of one redraw follow each other within a fraction
of a millisecond, while a program redrawing ten times a second leaves 100
milliseconds between two redraws, so this gap tells them apart.
"""

TERMINATE_GRACE = 2.0
"""Seconds a recording waits for the command to exit after `SIGTERM`.

A command still running when the recording ends, by its `duration` or by a
Ctrl+C, gets `SIGTERM` first, to clean up after itself. One that ignores it is
killed with its descendants once this grace runs out, so the recording never
waits forever: see `click_extra.execution._stop_process`.
"""


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

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        columns: int | None = None,
        rows: int | None = None,
        onlcr: bool = True,
    ) -> None:
        """Start on a blank screen, with nothing recorded.

        :param clock: what the recorder reads the time off. Stated so a test can
            hand it a clock that does not depend on how busy the machine is.
        :param columns: width of the terminal, see
            {class}`~click_extra.capture.terminal.TerminalScreen`.
        :param rows: height of the terminal, see
            {class}`~click_extra.capture.terminal.TerminalScreen`.
        :param onlcr: whether a newline returns the cursor to the start of its
            row, see {class}`~click_extra.capture.terminal.TerminalScreen`.
        """
        self._screen = _terminal.TerminalScreen(columns, rows, onlcr=onlcr)
        self._clock = clock
        self._samples: list[tuple[float, str]] = []
        self._redraw: float | None = None
        self._preface_display = ""

    def isatty(self) -> bool:
        """Claim to be a terminal, which is what makes a CLI animate at all."""
        return True

    def writable(self) -> bool:
        """Claim to be writable, as a terminal is."""
        return True

    def write(self, text: str) -> int:
        """Replay what was written and note the screen it leaves behind.

        A write changing nothing on screen is not noted: a cursor hidden or a
        style opened leaves the picture as it was, and the screen it did not
        change keeps the time it first appeared. What is kept is one sample per
        distinct screen, so a long animation costs as much memory as it has
        screens rather than as many as it has writes.

        :param text: the stream, control sequences and all.
        :return: how much was written, as a stream is expected to report.
        """
        self._screen.feed(text)
        display = self._screen.display
        if not self._samples or self._samples[-1][1] != display:
            self._samples.append((self._clock(), display))
        return len(text)

    def _preface(self, text: str) -> None:
        """Draw what stands on the screen before the command writes anything.

        A recording drawing its invocation as a shell prompt writes it here, so
        the command's output lands under it and a full-screen program covers
        it, as on a terminal. A screen showing nothing more is no frame, see
        {meth}`frames`.

        :param text: what the screen shows first, control sequences and all.
        """
        self._screen.feed(text)
        self._preface_display = self._screen.display

    def _receive(self, text: str, at: float) -> None:
        """Replay one read off a terminal, noting the screen each redraw leaves.

        A screen is noted once the stream has been quiet for
        {data}`REDRAW_GAP`, which no read inside a single redraw ever is, and
        never in the middle of a synchronized update. A half-drawn screen is
        therefore never a frame.

        :param text: what the read held, decoded.
        :param at: when it arrived.
        """
        if not text:
            return
        if self._redraw is not None and at - self._redraw >= REDRAW_GAP:
            self._settle()
        self._screen.feed(text)
        self._redraw = at

    def _settle(self, *, final: bool = False) -> None:
        """Note the screen the last redraw left, timed from its last read.

        :param final: note it even mid-update, the stream having ended.
        """
        if self._redraw is None or (self._screen.synchronized and not final):
            return
        display = self._screen.display
        if not self._samples or self._samples[-1][1] != display:
            self._samples.append((self._redraw, display))
        self._redraw = None

    def _idle(self, now: float) -> None:
        """Note the screen a finished redraw left, the stream having gone quiet.

        {meth}`_receive` notes it when the next read arrives, which a command
        drawing one screen and then waiting for a key never sends. Noting it on
        a quiet poll changes nothing about its timing, which stays that of its
        last read.

        :param now: when the stream was found quiet.
        """
        if self._redraw is not None and now - self._redraw >= REDRAW_GAP:
            self._settle()

    def _opened_at(self) -> float | None:
        """When the first screen {meth}`frames` keeps was drawn.

        :return: that time, or `None` while no such screen was noted.
        """
        for at, display in self._samples:
            if display.strip() and display != self._preface_display:
                return at
        return None

    def frames(self, *, end: float | None = None) -> tuple[Frame, ...]:
        """Coalesce what was recorded into the frames the screen held.

        A write changing nothing on screen is not a frame, see {meth}`write`,
        and neither is a screen holding nothing but blanks: an animation erases
        its line before printing the result underneath, and neither that erasure
        nor the newline ending it is a picture. Neither is a screen holding
        nothing but the prompt a recording drew before its command started.
        What is left is one frame per distinct screen, each lasting until the
        next replaced it.

        ```{caution}
        The durations are wall-clock, so they answer to how busy the machine was
        and differ a little between two runs of the same command. Quantize them
        before committing what they time.
        ```

        :param end: when the recording stopped, which is how long the last frame
            lasted. Defaults to now.
        :return: the frames, in the order they were drawn.
        """
        # A redraw still waiting for its quiet gap is the last screen.
        self._settle(final=True)
        finish = self._clock() if end is None else end
        # A blank sample at the stop time closes the last screen's span.
        samples = [*self._samples, (finish, "")]
        return tuple(
            Frame(display, until - at)
            for (at, display), (until, _) in pairwise(samples)
            if display.strip() and display != self._preface_display and until > at
        )


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
    background: TerminalBackground = TerminalBackground.DARK,
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
    this process *hosts* needs none of that: hand a
    {class}`~click_extra.capture.recording.ScreenRecorder` to its `stream` and
    it animates on any platform.
    ```

    The terminal this runs *from* is hidden from the command, see
    {data}`~click_extra.capture.screenshot.CAPTURE_HIDDEN_TERMINAL_VARS`, so one
    machine's recording matches another's.

    Both the command's output and its errors are read, the spinner drawing on
    the latter. What comes back is timed by the wall clock and therefore differs
    a little between two runs: quantize the durations before committing them.

    :param args: the command line, in the nested form
        {func}`~click_extra.execution.run_cli` accepts.
    :param columns: width of the terminal it is run in, in characters.
    :param rows: height of that terminal, in characters.
    :param background: chrome the recording is headed for, stated to the command
        the way a terminal would, see
        {data}`~click_extra.capture.screenshot.CAPTURE_TERMINAL_HINTS`.
    :param duration: seconds to record before stopping the command. `None`
        records until it exits on its own.
    :param clock: what the recorder reads the time off.
    :return: the frames the terminal held, in order.
    :raises NotImplementedError: on a platform with no pseudo-terminal.
    :raises OSError: when the command cannot start. {class}`subprocess.Popen`
        raises a `FileNotFoundError` for a program it cannot find, and a
        `PermissionError` for a file it cannot run.
    """
    return _record_process(
        args,
        columns=columns,
        rows=rows,
        background=background,
        duration=duration,
        clock=clock,
    )[0]


def _record_process(
    args: TArg | TNestedArgs,
    *,
    columns: int = DEFAULT_COLUMNS,
    rows: int = DEFAULT_ROWS,
    background: TerminalBackground = TerminalBackground.DARK,
    duration: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    preface: str = "",
    end: float | None = None,
) -> tuple[tuple[Frame, ...], int, bool]:
    """{func}`record_command`, reporting how the command ended beside the frames.

    The private form {func}`record_and_render` builds on: a caller writing a
    file wants to relay the command's exit code, and to know whether it left
    the alternate screen up, while the public frame recorder keeps its
    single-value return.

    :param preface: what stands on the screen before the command starts, like
        the shell prompt it was typed at. Empty draws nothing.
    :param end: seconds after the first screen to stop the command at, on the
        clock of {func}`end_at`. `None` leaves the stop to `duration` or to the
        command.
    :return: the frames, the command's exit code, and whether the alternate
        screen was still up when the recording ended.
    """
    # Deferred import: keeps extra_platforms off the startup path of every CLI.
    from extra_platforms import is_unix

    if not is_unix():
        raise NotImplementedError(
            "Recording a command needs a pseudo-terminal, which this platform "
            "does not provide. A spinner running in this process records "
            "anywhere through a ScreenRecorder stream."
        )

    # The height is stated beside the width: a pseudo-terminal has one, where
    # a capture through a pipe only ever pins the width.
    with forced_color():
        environment = env_copy({
            **capture_environment(background, columns),
            "LINES": str(rows),
            "TERM": RECORDING_TERM,
        })

    # The pseudo-terminal already turns each newline into the return and
    # newline the command meant, so a bare one moves the cursor straight down.
    recorder = ScreenRecorder(clock=clock, columns=columns, rows=rows, onlcr=False)
    if preface:
        recorder._preface(f"{preface}\r\n")
    # Decoded incrementally rather than chunk by chunk: a pseudo-terminal
    # hands the stream back in kernel-buffer-sized reads, so a multi-byte
    # glyph regularly straddles two of them, and a per-chunk decode would
    # mangle each straddling glyph into U+FFFD. The incremental decoder holds
    # the partial byte sequence until its tail arrives.
    decoder = codecs.getincrementaldecoder("UTF-8")(errors="replace")
    parent, child = pty.openpty()
    try:
        _pin_window_size(child, rows, columns)
        started = clock()
        process = subprocess.Popen(
            args_cleanup(args),
            stdin=child,
            stdout=child,
            stderr=child,
            env=cast("subprocess._ENV", environment),
            close_fds=True,
        )
    except BaseException:
        # A command that never started leaves nothing to read, so the reading
        # end closes with the other one.
        os.close(parent)
        raise
    finally:
        # The parent holds the only reading end from here on: leaving the
        # child's open would keep the read blocking forever after the command
        # exits.
        os.close(child)
    # Registered like a child of run_cli, so the Ctrl+C handlers stop it even
    # while another thread records it: see terminate_live_processes.
    _track(process)
    try:
        while True:
            now = clock()
            if duration is not None and now - started >= duration:
                break
            if end is not None:
                opened = recorder._opened_at()
                # One quiet gap past the end: a redraw still under way then has
                # a read after the end, so the cut drops it instead of keeping
                # a half-drawn screen.
                if opened is not None and now - opened >= end + REDRAW_GAP:
                    break
            readable, _, _ = select.select([parent], [], [], READ_POLL)
            if not readable:
                recorder._idle(clock())
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
            recorder._receive(decoder.decode(written), clock())
    finally:
        tail = decoder.decode(b"", final=True)
        if tail:
            recorder._receive(tail, clock())
        os.close(parent)
        try:
            returncode = _stop_process(process, TERMINATE_GRACE)
        finally:
            _untrack(process)

    return recorder.frames(end=clock()), returncode, recorder._screen.alternate


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
    {func}`~click_extra.capture.svg.animation_digest`, which fingerprints the
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


def start_at(frames: Sequence[Frame], start: float) -> tuple[Frame, ...]:
    """Drop what a recording showed before `start` seconds into it.

    The animation then opens on the screen that stood at that moment, as a
    player told where to start does: mpv's `--start` and the `startAt` option of
    [asciinema's player](https://docs.asciinema.org/manual/player/options/#startat)
    name the same move. It cuts the seconds a command spends warming up, like
    a profiler's tables filling in from nothing.

    The time counts from the first frame, which is where the animation starts
    too, and not from the moment the command was launched. The frame on screen
    at `start` keeps what remains of its duration.

    :param frames: what was recorded.
    :param start: seconds to drop. Zero keeps every frame.
    :return: the frames from `start` on.
    :raises ValueError: when `start` is negative, or when it reaches past the
        last frame, which would leave nothing to draw.
    """
    if start < 0:
        raise ValueError(f"{start} is not a start time, which is zero or more.")
    if not start:
        return tuple(frames)
    elapsed = 0.0
    for index, frame in enumerate(frames):
        if elapsed + frame.duration > start:
            return (
                Frame(frame.text, elapsed + frame.duration - start),
                *frames[index + 1 :],
            )
        elapsed += frame.duration
    raise ValueError(
        f"Starting {start:g} seconds in drops the whole recording, which lasted "
        f"{elapsed:.2f} seconds."
    )


def end_at(frames: Sequence[Frame], end: float) -> tuple[Frame, ...]:
    """Drop what a recording showed after `end` seconds into it.

    The mirror of {func}`start_at`, on the same clock: mpv pairs `--start`
    with an `--end` that stops at a time counted from the beginning, not from
    the start. `start_at(end_at(frames, 10), 6)` therefore keeps the four
    seconds between 6 and 10.

    The frame on screen at `end` keeps the part of its duration before it. A
    recording ending sooner is kept whole.

    :param frames: what was recorded.
    :param end: seconds after the first frame to stop at.
    :return: the frames up to `end`.
    :raises ValueError: when `end` is not positive.
    """
    if end <= 0:
        raise ValueError(f"{end} is not an end time, which is positive.")
    kept = []
    elapsed = 0.0
    for frame in frames:
        if elapsed >= end:
            break
        kept.append(Frame(frame.text, min(frame.duration, end - elapsed)))
        elapsed += frame.duration
    return tuple(kept)


def ansi_prefix(text: str, count: int) -> str:
    """The first `count` printable characters of `text`, its styling kept.

    Slicing a styled line by index cuts an escape sequence in half, and the
    remains land on the screen as the digits and brackets they are made of.
    Counting the printable characters alone and keeping every escape passed on
    the way is what avoids that, and it is also correct rather than merely safe:
    an escape is drawn nowhere, so the ones before a character are exactly the
    styling in force at it.

    :param text: the line to cut, ANSI escape sequences included.
    :param count: how many printable characters to keep. Counted as characters
        rather than as cells, a keystroke producing one of either.
    :return: the prefix, closed by a reset so the styling it opened ends with
        it.
    """
    kept: list[str] = []
    printed = 0
    index = 0
    while index < len(text) and printed < count:
        sequence = CSI_RE.match(text, index)
        if sequence:
            kept.append(sequence.group())
            index = sequence.end()
            continue
        kept.append(text[index])
        printed += 1
        index += 1
    return "".join(kept) + RESET


def type_line(
    line: str,
    *,
    typing: float = DEFAULT_TYPING,
    submit: float = DEFAULT_SUBMIT,
) -> tuple[Frame, ...]:
    """Frames of a command line appearing one keystroke at a time.

    The opening act a terminal recording is usually missing. A command records
    what it drew and never the invocation that drew it, so an animation starts
    on output arriving from nowhere. Typing the line first says where it came
    from, and reads as a session rather than as a clip.

    ```{note}
    Ordinary frames, carrying no mechanism of their own: they prepend to a
    recording's and travel through
    {func}`~click_extra.capture.svg.render_svg` like any others. Everything the
    picture does for a frame therefore reaches these too, the gutter numbering
    them and the cursor following the text along, see
    {func}`~click_extra.capture.svg.cursor_cell`.
    ```

    The last frame holds the finished line for `submit`, which is the beat
    before the return key. A recording's own frames follow it.

    :param line: the command line to type, already styled as a prompt draws it,
        see {func}`~click_extra.execution.format_cli_prompt`.
    :param typing: seconds each character takes to appear.
    :param submit: seconds the finished line waits before whatever follows.
    :return: one frame per character, in the order they are typed. Empty for an
        empty line, there being nothing to type.
    :raises ValueError: when either duration is not positive.
    """
    if typing <= 0:
        raise ValueError(f"{typing} is not a typing speed, which is positive.")
    if submit <= 0:
        raise ValueError(f"{submit} is not a pause, which is positive.")
    length = len(CSI_RE.sub("", line))
    if not length:
        return ()
    return tuple(
        Frame(
            ansi_prefix(line, typed),
            # The finished line waits out the beat before the return key, and
            # every character before it lasts one keystroke.
            submit if typed == length else typing,
        )
        for typed in range(1, length + 1)
    )


def record_and_render(
    args: TArg | TNestedArgs,
    *,
    columns: int = DEFAULT_COLUMNS,
    rows: int = DEFAULT_ROWS,
    background: TerminalBackground = TerminalBackground.DARK,
    prompt: str | None = None,
    duration: float | None = None,
    start: float = 0.0,
    end: float | None = None,
    quantum: float = DEFAULT_QUANTUM,
    hold: THold = DEFAULT_RECORDING_HOLD,
    blank: float = DEFAULT_RECORDING_BLANK,
    speed: float = 1.0,
    typing: float = 0.0,
    submit: float = DEFAULT_SUBMIT,
    line_numbers: bool = False,
    emphasize: Sequence[int] = (),
    cursor: Cursor | None = None,
    closing_prompt: bool = False,
    title: str = "",
    unique_id: str | None = None,
    preset: TerminalPreset | None = None,
    palette: TerminalPalette | None = None,
    font_stack: str | None = None,
    chrome: Chrome = Chrome(),
) -> tuple[str, int]:
    """Record a command under a pseudo-terminal and render it as an animated SVG.

    Chains {func}`record_command`, {func}`end_at`, {func}`start_at`,
    {func}`quantize` and
    {func}`~click_extra.capture.screenshot.render`, the way
    {func}`~click_extra.capture.screenshot.capture` chains the still pipeline. The
    invocation stands on the screen as a shell prompt before the command starts,
    styled by the active theme through
    {func}`~click_extra.execution.format_cli_prompt`, so the recording shows
    what to type to reproduce it. The command's output lands under it, and a
    full-screen program's alternate screen covers it, as on a terminal.

    :param args: the command line to record.
    :param columns: width of the terminal it runs in, in characters. A
        recording pins its width up front, so there is no `auto` here: the
        pseudo-terminal must exist before the command draws its first line.
    :param rows: height of that terminal, in characters.
    :param background: chrome the recording is headed for, stated to the
        command the way a terminal would.
    :param prompt: command line to *display*, when it differs from the one
        run. An empty string draws no prompt at all.
    :param duration: seconds to record before stopping the command. `None`
        records until it exits on its own.
    :param start: seconds of the recording to drop, counted from the first
        screen the command drew, see {func}`start_at`. Zero keeps them all.
    :param end: seconds after that first screen to stop the recording and the
        command at, see {func}`end_at`. `None` records until `duration` runs
        out or the command exits.
    :param quantum: grid the frame durations are rounded onto, see
        {func}`quantize`.
    :param hold: extra seconds the last frame stays up, or
        {data}`~click_extra.capture.svg.AUTO_HOLD` (the default here) to scale
        them to that frame's line count.
    :param blank: seconds of empty screen closing the cycle.
    :param speed: how much faster to play than recorded. The typed opening is
        replayed at the same rate as everything else, being part of what the
        animation shows rather than a pause laid over it.
    :param typing: seconds each character of the prompt takes to appear,
        opening the animation by typing the command out. Zero draws the prompt
        whole from the first frame, which is what a recording carrying no
        opening shows. See {func}`type_line`.
    :param submit: seconds the finished command line waits before its output
        starts. Unused when nothing is typed.
    :param line_numbers: draw each line's number in a gutter, the prompt
        counting as the first of them. Every frame takes the gutter of the
        tallest, see {func}`~click_extra.layout.number_frames`.
    :param emphasize: lines to draw a band behind, see
        {func}`~click_extra.capture.svg.render_svg`.
    :param cursor: the terminal cursor to draw, see
        {class}`~click_extra.capture.presets.Cursor`. It follows the text
        from screen to screen on its own, so a typed opening gets its caret
        from this and nothing else.
    :param closing_prompt: draw the shell's prompt under the last frame, which
        is where it comes back once the command exits, see
        {func}`~click_extra.capture.screenshot.append_prompt`. Only that frame carries
        it: the shell has not returned while the command is still drawing. A
        command stopped with the alternate screen still up gets none, as its
        screen is no shell's.
    :param title: see {func}`~click_extra.capture.screenshot.render`.
    :param unique_id: see {func}`~click_extra.capture.screenshot.render`.
    :param preset: see {func}`~click_extra.capture.screenshot.render`.
    :param palette: see {func}`~click_extra.capture.screenshot.render`.
    :param font_stack: see {func}`~click_extra.capture.screenshot.render`.
    :param chrome: see {func}`~click_extra.capture.screenshot.render`.
    :return: the rendered SVG document, and the command's exit code.
    :raises NotImplementedError: on a platform with no pseudo-terminal.
    :raises OSError: when the command cannot start, see {func}`record_command`.
    :raises ValueError: when the command drew nothing to record, when `end`
        is not after `start`, when `start` reaches past the last screen, or
        when a stated `typing` or `submit` is not positive.
    """
    # Refused before anything runs: a recording this would cut to nothing is
    # not worth waiting for.
    if end is not None and end <= start:
        raise ValueError(
            f"Ending {end:g} seconds in leaves nothing after a start at {start:g}."
        )
    invocation = prompt_line(args, prompt=prompt, background=background, preset=preset)
    frames, returncode, alternate = _record_process(
        args,
        columns=columns,
        rows=rows,
        background=background,
        duration=duration,
        preface=invocation,
        end=end,
    )
    if not frames:
        raise ValueError("Recorded nothing: the command drew no screen.")
    if end is not None:
        frames = end_at(frames, end)
    timed = quantize(start_at(frames, start), quantum)

    texts = tuple(frame.text for frame in timed)
    if closing_prompt and not alternate:
        # The last frame alone: it is the only screen the command has finished
        # drawing, and the shell comes back on no other.
        texts = (
            *texts[:-1],
            append_prompt(texts[-1], background=background, preset=preset),
        )
    intervals = tuple(frame.duration for frame in timed)
    if invocation and typing:
        # Prepended rather than merged: the opening is the same kind of thing
        # the recording is, one screen per moment, so it rides the same ladder.
        opening = type_line(invocation, typing=typing, submit=submit)
        texts = tuple(frame.text for frame in opening) + texts
        intervals = tuple(frame.duration for frame in opening) + intervals
    if line_numbers:
        texts = number_frames(texts)

    return (
        render(
            texts[-1],
            columns=columns,
            frames=texts,
            interval=intervals,
            hold=hold,
            blank=blank,
            speed=speed,
            emphasize=emphasize,
            cursor=cursor,
            title=title,
            unique_id=unique_id,
            background=background,
            preset=preset,
            palette=palette,
            font_stack=font_stack,
            chrome=chrome,
        ),
        returncode,
    )


_DEPRECATED_NAMES: dict[str, Any] = {
    "ERASE_IN_LINE": "K",
    "PARTIAL_CSI_RE": re.compile(rf"(?:{CSI_PREFIX_PATTERN}|\x1b)$"),
    "SELECT_GRAPHIC_RENDITION": "m",
}
"""Names of the line screen this module kept, each with the value it held.

{class}`~click_extra.capture.terminal.TerminalScreen` reads every sequence
itself, which leaves these with no reader. `__getattr__` serves each until
{data}`_REMOVAL_VERSION`.
"""


_MOVED_NAMES = frozenset({"TerminalScreen"})
"""Names this module defined in `10.2.0`, which {mod}`click_extra.capture.terminal`
defines now.

`__getattr__` serves each from there until {data}`_REMOVAL_VERSION`.
"""


_REMOVAL_VERSION = "11.0.0"
"""The release in which the names of {data}`_DEPRECATED_NAMES` and
{data}`_MOVED_NAMES` stop resolving."""


def __getattr__(name: str) -> Any:
    """Serve a name of {data}`_DEPRECATED_NAMES` or {data}`_MOVED_NAMES`, with a
    warning.

    The value is never cached here, so every access warns. Any other name raises
    {exc}`AttributeError` without a warning.
    """
    if name in _MOVED_NAMES:
        value = getattr(_terminal, name)
        reason = f"import it from {_terminal.__name__}"
    elif name in _DEPRECATED_NAMES:
        value = _DEPRECATED_NAMES[name]
        reason = f"{_terminal.__name__} reads every sequence"
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        f"{__name__}.{name} is deprecated and will be removed in click-extra "
        f"{_REMOVAL_VERSION}: {reason}.",
        DeprecationWarning,
        stacklevel=2,
    )
    return value
