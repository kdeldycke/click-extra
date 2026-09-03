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

import codecs
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
from .screenshot import (
    AUTO_HOLD,
    CAPTURE_HIDDEN_TERMINAL_VARS,
    CAPTURE_TERMINAL_HINTS,
    DEFAULT_BORDER_WIDTH,
    DEFAULT_COLUMNS,
    DEFAULT_MARGIN,
    DEFAULT_PADDING,
    DEFAULT_WATERMARK,
    NO_PAINT,
    OPAQUE,
    CaptureBackground,
    append_prompt,
    number_lines,
    prompt_line,
    render,
)

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
    from .screenshot import THold
    from .screenshot_presets import Cursor, TerminalPreset

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

DEFAULT_RECORDING_HOLD: THold = AUTO_HOLD
"""How long a recorded animation holds its last frame before starting over.

A recording ends somewhere, and the end is usually its point: the trail filled
in, the bar run out, the outcome landed. Looping straight back gives a reader no
time to read any of it, and how much time reading takes depends on how much the
ending shows, so the default scales with it: see
{func}`~click_extra.screenshot.auto_hold`. A declared animation cycles in place
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
        self._pending_return = False

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

    def _land(self) -> None:
        """Apply a deferred carriage return, just before something lands.

        A return only *moves* the cursor: whether the row survives depends on
        what comes next. Text or styling landing on the row redraws it, so the
        row is cleared here, at landing time; a newline instead leaves for the
        next row and the one the cursor came back over survives, which is what
        a real terminal shows for the `\r\n` a pseudo-terminal substitutes
        for every newline.
        """
        if self._pending_return:
            self.rows[-1] = ""
            self._pending_return = False

    def _control(self, sequence: str) -> None:
        """Act on one control sequence, or drop it when it is out of scope."""
        final = sequence[-1]
        if final == SELECT_GRAPHIC_RENDITION:
            # Styling travels with the text it wraps: kept, never acted on. It
            # lands like text does, so a color opened between a return and its
            # redraw survives the deferred clear instead of being wiped by it.
            self._land()
            self.rows[-1] += sequence
        elif final == ERASE_IN_LINE and not self._column:
            # Cleared from the start of the row, which empties the whole of it.
            # Past the start, the row already holds only what was written since
            # the cursor came back, so there is nothing left to erase. The
            # erase is the redraw a pending return was waiting for.
            self.rows[-1] = ""
            self._pending_return = False

    def _write(self, text: str) -> None:
        """Lay printable text on the screen, one row per newline it carries."""
        for line_index, line in enumerate(text.split("\n")):
            if line_index:
                # A newline settles any return before it without a redraw: the
                # row it came back over survives, so the `\r\n` a
                # pseudo-terminal substitutes for every newline keeps the line
                # a real terminal keeps.
                self.rows.append("")
                self._column = 0
                self._pending_return = False
            for chunk_index, chunk in enumerate(line.split("\r")):
                if chunk_index:
                    # The cursor goes back to the start of the row. The redraw
                    # is deferred to {meth}`_land`, which is what tells an
                    # animation redrawing its row apart from a line merely
                    # ending in a return.
                    self._column = 0
                    self._pending_return = True
                if not chunk:
                    continue
                self._land()
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

    The terminal this runs *from* is hidden from the command, see
    {data}`~click_extra.screenshot.CAPTURE_HIDDEN_TERMINAL_VARS`, so one
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
        {data}`~click_extra.screenshot.CAPTURE_TERMINAL_HINTS`.
    :param duration: seconds to record before stopping the command. `None`
        records until it exits on its own.
    :param clock: what the recorder reads the time off.
    :return: the frames the terminal held, in order.
    :raises NotImplementedError: on a platform with no pseudo-terminal.
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
    background: CaptureBackground = CaptureBackground.DARK,
    duration: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[tuple[Frame, ...], int]:
    """{func}`record_command`, reporting the command's exit code beside the frames.

    The private form {func}`record_and_render` builds on: a caller writing a
    file wants to relay how the command it pictured ended, while the public
    frame recorder keeps its single-value return.
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
    for hidden in CAPTURE_HIDDEN_TERMINAL_VARS:
        environment.pop(hidden, None)
    environment["COLUMNS"] = str(columns)
    environment["LINES"] = str(rows)

    recorder = ScreenRecorder(clock=clock)
    # Decoded incrementally rather than chunk by chunk: a pseudo-terminal
    # hands the stream back in kernel-buffer-sized reads, so a multi-byte
    # glyph regularly straddles two of them, and a per-chunk decode would
    # mangle each straddling glyph into U+FFFD. The incremental decoder holds
    # the partial byte sequence until its tail arrives.
    decoder = codecs.getincrementaldecoder("UTF-8")(errors="replace")
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
            recorder.write(decoder.decode(written))
    finally:
        tail = decoder.decode(b"", final=True)
        if tail:
            recorder.write(tail)
        os.close(parent)
        if process.poll() is None:
            process.terminate()
        returncode = process.wait()

    return recorder.frames(end=clock()), returncode


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
    return "".join(kept) + "\x1b[0m"


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
    {func}`~click_extra.screenshot.render_svg` like any others. Everything the
    picture does for a frame therefore reaches these too, the gutter numbering
    them and the cursor following the text along, see
    {func}`~click_extra.screenshot.cursor_cell`.
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
    background: CaptureBackground = CaptureBackground.DARK,
    prompt: str | None = None,
    duration: float | None = None,
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
    border: str | None = None,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int | None = None,
    backdrop: str = NO_PAINT,
    shadow: str | None = None,
    margin: int = DEFAULT_MARGIN,
    padding: int = DEFAULT_PADDING,
    opacity: float = OPAQUE,
    watermark: str = DEFAULT_WATERMARK,
    watermark_color: str | None = None,
) -> tuple[str, int]:
    """Record a command under a pseudo-terminal and render it as an animated SVG.

    Chains {func}`record_command`, {func}`quantize` and
    {func}`~click_extra.screenshot.render`, the way
    {func}`~click_extra.screenshot.capture` chains the still pipeline. The
    invocation is drawn above every frame as a shell prompt, styled by the
    active theme through {func}`~click_extra.execution.format_cli_prompt`, so
    the recording shows what to type to reproduce it.

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
    :param quantum: grid the frame durations are rounded onto, see
        {func}`quantize`.
    :param hold: extra seconds the last frame stays up, or
        {data}`~click_extra.screenshot.AUTO_HOLD` (the default here) to scale
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
        counting as the first of them.
    :param emphasize: lines to draw a band behind, see
        {func}`~click_extra.screenshot.render_svg`.
    :param cursor: the terminal cursor to draw, see
        {class}`~click_extra.screenshot_presets.Cursor`. It follows the text
        from screen to screen on its own, so a typed opening gets its caret
        from this and nothing else.
    :param closing_prompt: draw the shell's prompt under the last frame, which
        is where it comes back once the command exits, see
        {func}`~click_extra.screenshot.append_prompt`. Only that frame carries
        it: the shell has not returned while the command is still drawing.
    :param title: see {func}`~click_extra.screenshot.render`.
    :param unique_id: see {func}`~click_extra.screenshot.render`.
    :param preset: see {func}`~click_extra.screenshot.render`.
    :param border: see {func}`~click_extra.screenshot.render`.
    :param border_width: see {func}`~click_extra.screenshot.render`.
    :param radius: see {func}`~click_extra.screenshot.render`.
    :param backdrop: see {func}`~click_extra.screenshot.render`.
    :param shadow: see {func}`~click_extra.screenshot.render`.
    :param margin: see {func}`~click_extra.screenshot.render`.
    :param padding: see {func}`~click_extra.screenshot.render`.
    :param opacity: see {func}`~click_extra.screenshot.render`.
    :param watermark: see {func}`~click_extra.screenshot.render`.
    :param watermark_color: see {func}`~click_extra.screenshot.render`.
    :return: the rendered SVG document, and the command's exit code.
    :raises NotImplementedError: on a platform with no pseudo-terminal.
    :raises ValueError: when the command drew nothing to record, or when a
        stated `typing` or `submit` is not positive.
    """
    frames, returncode = _record_process(
        args,
        columns=columns,
        rows=rows,
        background=background,
        duration=duration,
    )
    timed = quantize(frames, quantum)
    if not timed:
        raise ValueError("Recorded nothing: the command drew no screen.")

    texts = tuple(frame.text for frame in timed)
    invocation = prompt_line(args, prompt=prompt, background=background, preset=preset)
    if invocation:
        texts = tuple(f"{invocation}\n{text}" for text in texts)
    if closing_prompt:
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
        texts = tuple(number_lines(text) for text in texts)

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
            border=border,
            border_width=border_width,
            radius=radius,
            backdrop=backdrop,
            shadow=shadow,
            margin=margin,
            padding=padding,
            opacity=opacity,
            watermark=watermark,
            watermark_color=watermark_color,
        ),
        returncode,
    )
