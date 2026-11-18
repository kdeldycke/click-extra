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

"""Tests for `click_extra.capture.recording`, which records a terminal's screens."""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import threading
import time
import warnings
from html import unescape
from itertools import pairwise
from pathlib import Path
from typing import cast

import pytest
from extra_platforms.pytest import skip_windows

from click_extra import SPINNERS, Spinner, Style, unstyle
from click_extra.capture import recording as capture_recording
from click_extra.capture.presets import Cursor
from click_extra.capture.recording import (
    DEFAULT_SUBMIT,
    Frame,
    ScreenRecorder,
    ansi_prefix,
    end_at,
    quantize,
    record_and_render,
    record_command,
    start_at,
    type_line,
)
from click_extra.capture.svg import (
    CELL_HEIGHT,
    CELL_WIDTH,
    LINE_HEIGHT,
    animation_digest,
    render_svg,
)
from click_extra.capture.terminal import TerminalScreen
from click_extra.execution import _LIVE_PROCESSES, terminate_live_processes
from click_extra.spinner import CLEAR_LINE, HIDE_CURSOR

from .test_screenshots import played_frames, svg_to_lines

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import IO


class StepClock:
    """A clock advancing a fixed step per reading, so a test can time frames."""

    def __init__(self, step: float = 1.0) -> None:
        self.step = step
        self.now = 0.0

    def __call__(self) -> float:
        reading = self.now
        self.now += self.step
        return reading


def test_recorder_claims_to_be_a_terminal():
    """A spinner animates for a recorder without being told to.

    The whole question a spinner asks before drawing is whether its stream is a
    terminal. Answering it is what makes the in-process path need no
    pseudo-terminal, and therefore work on every platform.
    """
    assert ScreenRecorder().isatty()


def test_recorder_frames_carry_what_the_screen_held():
    """Each frame lasts until the next screen replaced it."""
    clock = StepClock(1.0)
    recorder = ScreenRecorder(clock=clock)
    recorder.write("apricot")
    recorder.write(f"\r{CLEAR_LINE}fig")
    recorder.write(f"\r{CLEAR_LINE}plum")

    frames = recorder.frames(end=10.0)
    assert [frame.text for frame in frames] == ["apricot", "fig", "plum"]
    # Written at 0, 1 and 2 on the step clock; the last runs out the record.
    assert [frame.duration for frame in frames] == [1.0, 1.0, 8.0]


def test_recorder_drops_a_write_that_changed_nothing():
    """A write leaving the screen as it was is not a frame of its own."""
    recorder = ScreenRecorder(clock=StepClock(1.0))
    recorder.write("fig")
    recorder.write(f"\r{CLEAR_LINE}fig")
    recorder.write(HIDE_CURSOR)

    assert [frame.text for frame in recorder.frames(end=9.0)] == ["fig"]


def test_recorder_drops_a_cursor_shape_change():
    """A sequence the screen does not act on adds no frame, whatever its bytes.

    `ESC [ 2 SP q` sets the cursor's shape and carries an intermediate byte. A
    grammar stopping at the first letter missed it, so the sequence landed on
    the screen as text and split one picture into two identical frames.
    """
    recorder = ScreenRecorder(clock=StepClock(1.0))
    recorder.write("fig")
    recorder.write("\x1b[2 q")

    assert [frame.text for frame in recorder.frames(end=9.0)] == ["fig"]


def test_recorder_stores_one_sample_per_distinct_screen():
    """A write changing nothing stores nothing, so memory follows the screens.

    A spinner redraws the same frame for as long as its label holds, and a long
    recording would otherwise keep a copy of the whole screen per redraw.
    """
    recorder = ScreenRecorder(clock=StepClock(1.0))
    for _ in range(50):
        recorder.write(f"\r{CLEAR_LINE}fig")
    recorder.write(f"\r{CLEAR_LINE}plum")

    assert len(recorder._samples) == 2
    frames = recorder.frames(end=60.0)
    assert [frame.text for frame in frames] == ["fig", "plum"]
    # The clock is read once per kept screen, so the step clock stamps the two
    # at 0 and 1: each screen is timed from its first appearance.
    assert [frame.duration for frame in frames] == [1.0, 59.0]


def test_recorder_drops_a_screen_holding_only_blanks():
    """An erasure, and the newline ending it, picture nothing."""
    recorder = ScreenRecorder(clock=StepClock(1.0))
    recorder.write("fig")
    recorder.write(f"\r{CLEAR_LINE}")
    recorder.write("\n")

    assert [frame.text for frame in recorder.frames(end=9.0)] == ["fig"]


def test_recorder_records_a_spinner_without_a_terminal(monkeypatch):
    """A spinner handed a recorder animates into it, on any platform.

    No pseudo-terminal is involved, which is what a documentation build on
    Windows depends on.
    """
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    recorder = ScreenRecorder()
    spinner = Spinner(
        "Steeping",
        spinner=SPINNERS["moon"],
        style=Style(fg="green"),
        # A recorder stands in for a terminal, but `io.TextIOBase` does not
        # satisfy the nominal `IO[str]` the signature asks for.
        stream=cast("IO[str]", recorder),
        interval=0.02,
    )
    spinner.start()
    time.sleep(0.4)
    spinner.stop()

    assert spinner.shown, "the recorder did not read as a terminal"
    frames = recorder.frames()
    assert frames
    drawn = {frame.text for frame in frames}
    assert drawn <= set(spinner.frame_lines())
    assert all(frame.duration > 0 for frame in frames)


def test_recorder_notes_a_redraw_once_its_reads_settle():
    """Reads arriving within one redraw make one frame, never a half-drawn one.

    A pseudo-terminal hands a large redraw back in several reads, a fraction of
    a millisecond apart. A screen noted after each of them would picture the
    program halfway through drawing.
    """
    recorder = ScreenRecorder(columns=20, rows=3, onlcr=False)
    recorder._receive("\x1b[2;1Happle", 0.0)
    recorder._receive(" pie", 0.0002)
    recorder._receive("\x1b[2;1Hplum tart", 0.1)

    frames = recorder.frames(end=0.3)
    assert [frame.text for frame in frames] == ["\napple pie", "\nplum tart"]
    assert [round(frame.duration, 4) for frame in frames] == [0.0998, 0.2]


def test_recorder_holds_a_synchronized_update_until_it_closes():
    """A program asking its terminal to wait gets no frame of what it drew meanwhile."""
    recorder = ScreenRecorder(columns=20, rows=3, onlcr=False)
    recorder._receive("\x1b[?2026happle", 0.0)
    recorder._receive(" pie\x1b[?2026l", 0.05)

    assert [frame.text for frame in recorder.frames(end=0.2)] == ["apple pie"]


def test_recorder_takes_no_frame_of_its_preface_alone():
    """A screen showing only what stood before the command started is no frame.

    The command erasing its own output leaves the prompt it was typed at, which
    is where the recording started, not a picture of the command.
    """
    recorder = ScreenRecorder(columns=20, rows=3, onlcr=False)
    recorder._preface("$ bake\r\n")
    recorder._receive("bread", 0.0)
    recorder._receive("\r\x1b[K", 0.1)
    recorder._receive("rolls", 0.2)

    frames = recorder.frames(end=0.3)
    assert [frame.text for frame in frames] == ["$ bake\nbread", "$ bake\nrolls"]


BAR_SCRIPT = """\
import sys, time
for filled in range(4):
    sys.stderr.write('\\r[' + '#' * filled + ']\\x1b[K')
    sys.stderr.flush()
    time.sleep(0.05)
"""
"""A progress bar drawn to `stderr`, redrawn in place, as a real one is."""


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_command_recovers_a_foreign_animation():
    """A command this process does not host still animates, under a terminal.

    The case a pipe cannot reach: the program asks whether it is talking to a
    terminal, and only a pseudo-terminal makes it draw. Its frames go to
    `stderr`, where a spinner and a progress bar both write.
    """
    frames = record_command(
        (sys.executable, "-c", BAR_SCRIPT),
        columns=40,
        duration=5.0,
    )

    assert [frame.text for frame in frames] == ["[]", "[#]", "[##]", "[###]"]
    assert all(frame.duration > 0 for frame in frames)


STUBBORN_SCRIPT = """
import signal, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
sys.stdout.write("ripe")
sys.stdout.flush()
time.sleep(6)
"""
"""A command that ignores `SIGTERM` and outlives the recording."""


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_command_kills_a_command_ignoring_sigterm(monkeypatch):
    """A command ignoring `SIGTERM` is killed once the grace runs out, so the
    recording returns instead of waiting for the command to exit on its own."""
    monkeypatch.setattr("click_extra.capture.recording.TERMINATE_GRACE", 0.2)
    start = time.monotonic()
    frames = record_command((sys.executable, "-c", STUBBORN_SCRIPT), duration=0.5)
    assert time.monotonic() - start < 4
    assert any("ripe" in frame.text for frame in frames)


SLEEPER_SCRIPT = """
import pathlib, sys, time
sys.stdout.write("ripe")
sys.stdout.flush()
pathlib.Path(sys.argv[1]).touch()
time.sleep(30)
"""
"""A command that draws once, touches the file it is given, then waits for a
signal to end it."""


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_command_registers_its_command_for_ctrl_c(tmp_path):
    """A recording registers its command where the Ctrl+C handlers find it.

    A worker thread records while the main thread calls
    `terminate_live_processes`, which is what a Ctrl+C runs: the command ends,
    and so does the recording, long before its `duration`. The interrupt waits
    for the command to draw, which a slow runner can delay past registration.
    """
    recorded: list[tuple[Frame, ...]] = []
    drawn = tmp_path / "drawn"

    def record():
        recorded.append(
            record_command(
                (sys.executable, "-c", SLEEPER_SCRIPT, str(drawn)), duration=8
            )
        )

    worker = threading.Thread(target=record, daemon=True)
    start = time.monotonic()
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not drawn.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert _LIVE_PROCESSES, "the recording did not register its command"
        assert drawn.exists(), "the command did not draw"
        terminate_live_processes()
        worker.join(timeout=5)
        assert not worker.is_alive()
    finally:
        worker.join(timeout=10)
    assert time.monotonic() - start < 7
    assert not _LIVE_PROCESSES
    assert recorded
    assert any("ripe" in frame.text for frame in recorded[0])


STUBBORN_PARENT_SCRIPT = """
import signal, subprocess, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
seed = subprocess.Popen((sys.executable, "-c", "import time; time.sleep(30)"))
sys.stdout.write(f"seed={seed.pid}")
sys.stdout.flush()
time.sleep(30)
"""
"""A command ignoring `SIGTERM` that starts a child of its own, which does too."""


def _wait_until_gone(pid: int, timeout: float = 5.0) -> bool:
    """Whether `pid` ends within `timeout` seconds. A zombie counts as gone."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        try:
            with open(f"/proc/{pid}/stat", encoding="ascii") as stat_file:
                if stat_file.read().rpartition(")")[2].split()[0] == "Z":
                    return True
        except OSError:
            pass
        time.sleep(0.05)
    return False


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
@pytest.mark.usefixtures("requires_process_table")
def test_record_command_kills_what_its_command_started(monkeypatch):
    """A command killed at the end of its recording takes its descendants along.

    They would otherwise outlive the recording, holding the terminal it drew on.
    """
    monkeypatch.setattr("click_extra.capture.recording.TERMINATE_GRACE", 0.2)
    frames = record_command((sys.executable, "-c", STUBBORN_PARENT_SCRIPT), duration=1)
    match = re.search(r"seed=(\d+)", "".join(frame.text for frame in frames))
    assert match, "the command never reported its child"
    pid = int(match.group(1))
    try:
        assert _wait_until_gone(pid), f"PID {pid} outlived the recording"
    finally:
        # Do not leak the sleeper past the test.
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


SPLIT_GLYPH_SCRIPT = """
import sys, time
raw = sys.stdout.buffer
glyph = "\u2570".encode("UTF-8")
raw.write(glyph[:1])
raw.flush()
time.sleep(0.2)
raw.write(glyph[1:] + b" ripe")
raw.flush()
"""
"""A box-drawing corner flushed one byte at a time, as a busy pty read splits it."""


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_command_reassembles_a_glyph_split_across_reads():
    """A multi-byte glyph straddling two pty reads decodes whole.

    A pseudo-terminal hands the stream back in kernel-buffer-sized chunks, so
    a heavy redraw regularly splits a box-drawing glyph or an emoji across two
    reads. Decoding each chunk on its own mangles both halves into `U+FFFD`;
    the recorder must hold the partial sequence until its tail arrives.
    """
    frames = record_command(
        (sys.executable, "-c", SPLIT_GLYPH_SCRIPT),
        columns=40,
        duration=5.0,
    )

    assert frames, "the command drew nothing"
    assert frames[-1].text == "\u2570 ripe"
    assert all("\ufffd" not in frame.text for frame in frames)


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_command_closes_its_terminal_when_the_command_cannot_start(tmp_path):
    """A command that never started leaves no end of its terminal open.

    The pseudo-terminal is opened before the command is spawned, so a spawn
    refused by the system is the one exit that has both ends to close.
    """
    opened = set(os.listdir("/dev/fd"))
    with pytest.raises(FileNotFoundError):
        record_command((str(tmp_path / "juicer"),))
    leaked = set(os.listdir("/dev/fd")) - opened
    assert not leaked, f"descriptors left open: {sorted(leaked)}"


FULL_SCREEN_SCRIPT = """\
import curses, time

def fill(screen):
    curses.curs_set(0)
    # Draw on the terminal's own background, not on curses' default black.
    curses.use_default_colors()
    for count in (1, 2, 3):
        screen.erase()
        screen.addstr(1, 4, f"apples: {count}")
        screen.refresh()
        time.sleep(0.15)

curses.wrapper(fill)
"""
"""A full-screen program counting apples on the alternate screen, with curses."""


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_command_follows_a_full_screen_program():
    """Each redraw of a curses program is a frame of the screen it addresses.

    The recording names `xterm-256color` to the program, so curses finds an
    entry even where `TERM` is unset. Every frame holds the alternate screen at
    its full height, and the first screen coming back at exit, blank, is none.
    """
    frames = record_command(
        (sys.executable, "-c", FULL_SCREEN_SCRIPT), columns=24, rows=4, duration=10.0
    )
    assert [unstyle(frame.text) for frame in frames] == [
        f"\n    apples: {count}\n\n" for count in (1, 2, 3)
    ]


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_and_render_draws_the_prompt_on_every_frame():
    """The stated invocation leads each frame, styled as a shell prompt."""
    svg, returncode = record_and_render(
        (sys.executable, "-c", BAR_SCRIPT),
        columns=40,
        prompt="basket ripen --all",
        unique_id="pantry-run",
    )
    assert returncode == 0
    assert "basket" in svg
    assert "ripen" in svg
    # Four bar frames recorded, plus the blank frame closing the cycle.
    assert svg.count('"pantry-run-clip"') == 1
    assert "pantry-run-f4" in svg


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_and_render_hides_an_empty_prompt():
    """An empty --prompt draws no invocation at all."""
    svg, _returncode = record_and_render(
        (sys.executable, "-c", BAR_SCRIPT),
        columns=40,
        prompt="",
        unique_id="bare-run",
    )
    assert Path(sys.executable).name not in svg


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_and_render_reports_the_exit_code():
    """The command's own verdict travels beside the picture of it."""
    _svg, returncode = record_and_render(
        (sys.executable, "-c", "import sys; print('rotten'); sys.exit(3)"),
        columns=40,
        prompt="",
    )
    assert returncode == 3


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_and_render_refuses_an_empty_recording():
    """A command that drew nothing leaves nothing to animate."""
    with pytest.raises(ValueError, match="drew no screen"):
        record_and_render((sys.executable, "-c", "pass"), columns=40)


def text_columns(svg: str, text: str) -> set[int]:
    """Every column a capture starts a run reading `text` on, in any frame."""
    return {
        round(float(offset) / CELL_WIDTH)
        for offset, content in re.findall(
            r'<text [^>]*\bx="([\d.]+)"[^>]*>([^<]*)</text>', svg
        )
        if unescape(content).replace("\N{NO-BREAK SPACE}", " ") == text
    }


def test_record_and_render_numbers_every_frame_in_one_gutter(monkeypatch):
    """A screen reaching ten rows does not push its text a cell to the right.

    Each frame counts its own rows, from one. Numbered on its own, a nine-row
    screen aligns its numbers on one digit and the ten-row screen after it on
    two, so every row moves between the two frames. The recording is stated
    rather than timed, so both screens are sure to be in it.
    """
    screens = tuple(
        Frame("\n".join(f"crate {crate}" for crate in range(rows)), 0.1)
        for rows in (9, 10)
    )
    monkeypatch.setattr(
        "click_extra.capture.recording._record_process",
        lambda *args, **kwargs: (screens, 0, False),
    )
    svg, _returncode = record_and_render(
        ("stack",), columns=40, prompt="", unique_id="pantry", line_numbers=True
    )
    # Two digits and the rule, ` 1 │ `, in front of the first row of both.
    assert text_columns(svg, "crate 0") == {5}


@pytest.mark.parametrize(
    ("recorded", "expected"),
    (
        pytest.param(0.0794, 0.08, id="under"),
        pytest.param(0.0812, 0.08, id="over"),
        pytest.param(0.0801, 0.08, id="barely-over"),
        pytest.param(0.08, 0.08, id="exact"),
        pytest.param(0.0001, 0.01, id="a-drawn-frame-keeps-a-whole-step"),
    ),
)
def test_quantize_lands_jitter_on_one_grid(recorded, expected):
    """Two runs of one unchanged command time their frames the same."""
    (frame,) = quantize((Frame("fig", recorded),))
    assert frame.duration == expected


def test_quantize_keeps_the_frames_it_times():
    """Rounding a duration never rewrites the screen it belongs to."""
    frames = (Frame("apricot", 0.079), Frame("fig", 0.082))
    assert [frame.text for frame in quantize(frames)] == ["apricot", "fig"]


def test_quantize_rejects_a_grid_going_nowhere():
    with pytest.raises(ValueError, match="positive"):
        quantize((Frame("fig", 0.08),), quantum=0)


@pytest.mark.parametrize(
    ("start", "expected"),
    (
        pytest.param(0, [("apricot", 1.0), ("fig", 2.0)], id="zero-keeps-all"),
        pytest.param(0.25, [("apricot", 0.75), ("fig", 2.0)], id="inside-the-first"),
        pytest.param(1.0, [("fig", 2.0)], id="on-a-boundary"),
        pytest.param(2.5, [("fig", 0.5)], id="inside-the-last"),
    ),
)
def test_start_at_opens_on_the_screen_standing_then(start, expected):
    """The frame on screen at `start` stays, with what remains of its time."""
    frames = (Frame("apricot", 1.0), Frame("fig", 2.0))
    cut = start_at(frames, start)
    assert [(frame.text, frame.duration) for frame in cut] == expected


@pytest.mark.parametrize(
    ("start", "message"),
    (
        pytest.param(-1, "zero or more", id="negative"),
        pytest.param(3, "drops the whole recording", id="at-the-end"),
        pytest.param(9, "drops the whole recording", id="past-the-end"),
    ),
)
def test_start_at_refuses_a_start_leaving_nothing(start, message):
    with pytest.raises(ValueError, match=message):
        start_at((Frame("apricot", 1.0), Frame("fig", 2.0)), start)


@pytest.mark.parametrize(
    ("end", "expected"),
    (
        pytest.param(0.25, [("apricot", 0.25)], id="inside-the-first"),
        pytest.param(1.0, [("apricot", 1.0)], id="on-a-boundary"),
        pytest.param(2.5, [("apricot", 1.0), ("fig", 1.5)], id="inside-the-last"),
        pytest.param(9, [("apricot", 1.0), ("fig", 2.0)], id="past-the-end"),
    ),
)
def test_end_at_stops_on_the_screen_standing_then(end, expected):
    """The frame on screen at `end` keeps what came before it, the rest goes."""
    frames = (Frame("apricot", 1.0), Frame("fig", 2.0))
    cut = end_at(frames, end)
    assert [(frame.text, frame.duration) for frame in cut] == expected


@pytest.mark.parametrize("end", (0, -1))
def test_end_at_refuses_an_end_before_anything(end):
    with pytest.raises(ValueError, match="positive"):
        end_at((Frame("apricot", 1.0),), end)


def test_record_and_render_ends_where_asked(monkeypatch):
    """`start` and `end` keep the slice between them, on one clock."""
    screens = (Frame("apricot", 1.0), Frame("quince", 1.0), Frame("plum", 1.0))
    monkeypatch.setattr(
        "click_extra.capture.recording._record_process",
        lambda *args, **kwargs: (screens, 0, False),
    )
    svg, _returncode = record_and_render(
        ("ripen",), columns=40, prompt="", unique_id="orchard", start=0.5, end=1.5
    )
    assert "apricot" in svg
    assert "quince" in svg
    assert "plum" not in svg
    # Half a second of each screen around the boundary, then the two second
    # hold a one-line screen gets and the closing blank beat.
    assert "period=3.6s" in svg


def test_record_and_render_refuses_an_end_before_the_start(monkeypatch):
    """A slice that holds nothing is refused before the command runs."""

    def never(*args, **kwargs):
        raise AssertionError("the command ran")

    monkeypatch.setattr("click_extra.capture.recording._record_process", never)
    with pytest.raises(ValueError, match="leaves nothing"):
        record_and_render(("ripen",), columns=40, start=2, end=2)


def test_record_and_render_starts_where_asked(monkeypatch):
    """`start` drops the screens shown before it, and keeps the one standing then.

    The recording is stated rather than timed, so the cut lands inside the
    second screen whatever the machine's load.
    """
    screens = (Frame("apricot", 1.0), Frame("quince", 1.0), Frame("plum", 1.0))
    monkeypatch.setattr(
        "click_extra.capture.recording._record_process",
        lambda *args, **kwargs: (screens, 0, False),
    )
    svg, _returncode = record_and_render(
        ("ripen",), columns=40, prompt="", unique_id="orchard", start=1.5
    )
    assert "apricot" not in svg
    assert "quince" in svg
    assert "plum" in svg
    # Half a second left of the cut screen, the whole last one, then the two
    # second hold a one-line screen gets and the closing blank beat.
    assert "period=4.1s" in svg


def test_quantized_recordings_of_one_command_render_the_same_bytes():
    """The point of the exercise: a rerun rewrites the asset byte for byte.

    Two recordings of one unchanged command, timed a few milliseconds apart the
    way two runs on a differently loaded machine are.
    """
    texts = ["[", "[#", "[##"]
    quiet = quantize(
        tuple(Frame(text, beat) for text, beat in zip(texts, (0.0794, 0.0801, 0.0812)))
    )
    loaded = quantize(
        tuple(Frame(text, beat) for text, beat in zip(texts, (0.0823, 0.0779, 0.0795)))
    )

    def draw(frames):
        return render_svg(
            columns=20,
            unique_id="bar",
            frames=[frame.text for frame in frames],
            interval=[frame.duration for frame in frames],
        )

    assert draw(quiet) == draw(loaded)


def test_a_dropped_frame_does_not_move_the_recording():
    """A frame the scheduler lost leaves the animation's identity alone.

    Quantizing cannot recover it, so the fingerprint is written not to care: it
    covers the frames a cycle holds and the beat, not how many were caught.
    """
    cycle = ["[", "[#", "[##", "[###"]
    beats = (0.08,) * len(cycle)
    quiet = animation_digest(cycle * 2, beats * 2)
    # One frame missing from the first turn, the second turn complete.
    loaded = animation_digest(cycle[:-1] + cycle, beats * 2)
    assert quiet == loaded


def test_a_changed_command_moves_the_recording():
    """What the fingerprint is for: real drift is still reported."""
    cycle = ["[", "[#", "[##"]
    beats = (0.08,) * len(cycle)
    assert animation_digest(cycle, beats) != animation_digest(["(", "(#", "(##"], beats)


TYPED_PROMPT = "\x1b[90m$\x1b[0m \x1b[97mbasket\x1b[0m ripen --all"
"""A styled prompt line, as `format_cli_prompt` composes one."""


@pytest.mark.parametrize(
    ("count", "expected"),
    (
        pytest.param(0, "\x1b[0m", id="nothing-typed-yet"),
        pytest.param(1, "\x1b[90m$\x1b[0m", id="one-character"),
        pytest.param(3, "\x1b[90m$\x1b[0m \x1b[97mb\x1b[0m", id="into-the-next-style"),
        pytest.param(
            99,
            "\x1b[90m$\x1b[0m \x1b[97mbasket\x1b[0m ripen --all\x1b[0m",
            id="past-the-end",
        ),
    ),
)
def test_ansi_prefix_keeps_the_styling_in_force(count, expected):
    """An escape is drawn nowhere, so every one before the cut still applies."""
    assert ansi_prefix(TYPED_PROMPT, count) == expected


@pytest.mark.parametrize("count", range(len("$ basket ripen --all") + 1))
def test_ansi_prefix_never_cuts_an_escape(count):
    """A half-written escape lands on the screen as the digits it is made of."""
    prefix = ansi_prefix(TYPED_PROMPT, count)
    assert "\x1b" not in re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", prefix)
    assert unstyle(prefix) == unstyle(TYPED_PROMPT)[:count]


def test_type_line_makes_one_frame_per_character():
    """A keystroke is a screen, so a character is a frame."""
    typed = type_line(TYPED_PROMPT, typing=0.05)
    assert len(typed) == len(unstyle(TYPED_PROMPT))
    assert [unstyle(frame.text) for frame in typed[:3]] == ["$", "$ ", "$ b"]
    assert unstyle(typed[-1].text) == unstyle(TYPED_PROMPT)


def test_type_line_holds_the_finished_line_for_the_submit_beat():
    """The pause before the return key, and only on the frame that waits it."""
    typed = type_line(TYPED_PROMPT, typing=0.05, submit=0.4)
    assert {frame.duration for frame in typed[:-1]} == {0.05}
    assert typed[-1].duration == pytest.approx(0.4)


def test_type_line_types_nothing_for_an_empty_line():
    """A recording carrying no prompt has no opening to play."""
    assert type_line("") == ()
    assert type_line("\x1b[90m\x1b[0m") == ()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        pytest.param({"typing": 0}, "not a typing speed", id="typing-zero"),
        pytest.param({"typing": -1}, "not a typing speed", id="typing-backwards"),
        pytest.param({"submit": 0}, "not a pause", id="submit-zero"),
        pytest.param({"submit": -1}, "not a pause", id="submit-backwards"),
    ),
)
def test_type_line_rejects_a_beat_going_nowhere(kwargs, message):
    """Seconds run forwards, and a frame lasting none is never shown."""
    with pytest.raises(ValueError, match=message):
        type_line(TYPED_PROMPT, **kwargs)


def test_a_typed_opening_walks_its_cursor_one_cell_at_a_time():
    """The caret is the cursor, and it follows the text with no code of its own.

    What the design rests on: a cursor is drawn as part of the row it stands on,
    read off that row's text, so an animation typing a line gets its caret for
    nothing.
    """
    typed = type_line(TYPED_PROMPT, typing=0.05)
    svg = render_svg(
        columns=40,
        unique_id="basket",
        frames=[frame.text for frame in typed],
        interval=[frame.duration for frame in typed],
        cursor=Cursor(),
    )
    lefts = [
        float(left)
        for left in re.findall(
            r'<rect class="basket-blink" fill="[^"]*" x="([\d.]+)"', svg
        )
    ]
    assert len(lefts) == len(typed)
    steps = {round(after - before, 1) for before, after in pairwise(lefts)}
    assert steps == {round(CELL_WIDTH, 1)}


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_a_recording_types_its_prompt_when_asked():
    """The typed opening leads the recorded frames, under the prompt it types."""
    plain, _ = record_and_render(
        (sys.executable, "-c", BAR_SCRIPT),
        columns=40,
        prompt="basket ripen --all",
        unique_id="orchard",
    )
    typed, _ = record_and_render(
        (sys.executable, "-c", BAR_SCRIPT),
        columns=40,
        prompt="basket ripen --all",
        unique_id="orchard",
        typing=0.05,
        submit=DEFAULT_SUBMIT,
    )

    def frame_count(svg: str) -> int:
        found = re.search(r"frames=(\d+)", svg)
        assert found, svg
        return int(found.group(1))

    assert frame_count(typed) - frame_count(plain) == len("$ basket ripen --all")


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_a_recording_types_nothing_unless_asked():
    """By default, a recording opens on the finished prompt."""
    svg, _ = record_and_render(
        (sys.executable, "-c", BAR_SCRIPT),
        columns=40,
        prompt="basket ripen --all",
        unique_id="orchard",
    )
    assert "orchard-blink" not in svg


RIPENED_SCRIPT = """\
import sys, time
for filled in range(4):
    sys.stderr.write('\\r[' + '#' * filled + ']\\x1b[K')
    sys.stderr.flush()
    time.sleep(0.05)
sys.stderr.write('\\r\\x1b[Kripe\\n')
"""
"""The same bar, ending on a newline the way a finished command does."""


def last_drawn_row(svg: str) -> int:
    """Index of the lowest row a capture draws a glyph on, counted from zero.

    Matched on the styled runs alone: the caption and the credit line are
    `<text>` too, and both sit outside the grid this measures.
    """
    baselines = [
        float(y) for y in re.findall(r'<text class="[\w-]+-r\d+"[^>]*y="([\d.]+)"', svg)
    ]
    assert baselines, svg
    return round((max(baselines) - CELL_HEIGHT) / LINE_HEIGHT)


def window_height(svg: str) -> float:
    """How tall the capture is, in pixels."""
    found = re.search(r'viewBox="0 0 [\d.]+ ([\d.]+)"', svg)
    assert found, svg
    return float(found.group(1))


def recorded(script: str, **kwargs: object) -> str:
    """Record one script, however the capture is asked to close."""
    svg, _returncode = record_and_render(
        (sys.executable, "-c", script),
        columns=40,
        prompt="basket ripen --all",
        unique_id="orchard",
        cursor=Cursor(),
        **kwargs,  # type: ignore[arg-type]
    )
    return svg


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_a_closing_prompt_fills_the_row_the_cursor_waited_on():
    """A command closing on a newline already left the row the shell wants.

    Which is what makes the pair free: the window is the same height either
    way, and the row holding nothing but a cursor holds a prompt instead.
    """
    plain = recorded(RIPENED_SCRIPT)
    closed = recorded(RIPENED_SCRIPT, closing_prompt=True)
    assert window_height(closed) == window_height(plain)
    # Unclosed, that bottom row carries the cursor and no glyph at all.
    assert last_drawn_row(closed) == last_drawn_row(plain) + 1


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_a_closing_prompt_opens_a_row_under_a_screen_left_mid_line():
    """A command that never ended its line is given one, as a shell gives it.

    The free case above is the common one and not the only one: a progress bar
    redrawing in place leaves the cursor mid-line, so the shell coming back
    costs the row it prints its own newline onto.
    """
    plain = recorded(BAR_SCRIPT)
    closed = recorded(BAR_SCRIPT, closing_prompt=True)
    assert window_height(closed) - window_height(plain) == pytest.approx(LINE_HEIGHT)


def test_a_closing_prompt_stays_off_a_full_screen_program(monkeypatch):
    """A command stopped on the alternate screen gets no shell prompt drawn.

    Stopped by the recording, a full-screen program leaves its own screen up,
    where the shell coming back would print over the program.
    """
    screens = (Frame("\n  oven", 0.1),)

    def height(*, alternate: bool, closing_prompt: bool) -> float:
        monkeypatch.setattr(
            "click_extra.capture.recording._record_process",
            lambda *args, **kwargs: (screens, 0, alternate),
        )
        svg, _returncode = record_and_render(
            ("bake",), columns=20, rows=4, prompt="", closing_prompt=closing_prompt
        )
        return window_height(svg)

    assert height(alternate=False, closing_prompt=True) > height(
        alternate=False, closing_prompt=False
    )
    assert height(alternate=True, closing_prompt=True) == height(
        alternate=True, closing_prompt=False
    )


TACHYON_CAST = Path(__file__).with_name("tachyon-live.cast")
"""Tachyon's live mode as a terminal received it, see `tests/tachyon_cast.py`."""


def test_tachyon_live_mode_replays_screen_by_screen(monkeypatch):
    """Python's live profiler records into an animation of every screen it drew.

    Closes the loop on the screenshot the Python documentation shows as a GIF:
    the curses interface of `python -m profiling.sampling run --live`, as
    `ncurses` wrote it at an `xterm-256color` terminal of the same size, is read
    back through the recorder with the timing each chunk arrived with, and
    rendered the way the `screenshot --record` command renders it.
    """
    header, *events = (
        json.loads(line)
        for line in TACHYON_CAST.read_text(encoding="UTF-8").splitlines()
    )

    def replay(*args, columns, rows, preface="", **kwargs):
        recorder = ScreenRecorder(columns=columns, rows=rows, onlcr=False)
        if preface:
            recorder._preface(f"{preface}\r\n")
        for at, _kind, text in events:
            recorder._receive(text, at)
        return recorder.frames(end=events[-1][0]), 0, recorder._screen.alternate

    frames, _returncode, alternate = replay(
        columns=header["width"], rows=header["height"]
    )
    # Every frame is the profiler's whole screen, and the last one its verdict.
    assert not alternate
    assert {frame.text.count("\n") + 1 for frame in frames} == {header["height"]}
    assert "PROFILING COMPLETE" in frames[-1].text

    monkeypatch.setattr("click_extra.capture.recording._record_process", replay)
    svg, _returncode = record_and_render(
        ("python", "-m", "profiling.sampling", "run", "--live", "--opcodes", "bake.py"),
        columns=header["width"],
        rows=header["height"],
        hold=2.0,
        unique_id="tachyon-live",
    )
    # Played back, every moment shows the screen that was up, then the blank.
    played = [svg_to_lines(still) for still in played_frames(svg, "tachyon-live")]
    expected = [
        svg_to_lines(render_svg(frame.text, columns=header["width"]))
        for frame in frames
    ]
    assert played == [*expected, []]


@pytest.mark.parametrize(
    ("name", "released"),
    (
        ("ERASE_IN_LINE", "K"),
        ("PARTIAL_CSI_RE", re.compile(r"(?:\x1b\[[0-?]*[ -/]*|\x1b)$")),
        ("SELECT_GRAPHIC_RENDITION", "m"),
        ("TerminalScreen", TerminalScreen),
    ),
)
def test_line_screen_names_warn_until_their_removal(name, released):
    """The names of the `10.2.0` line screen still resolve, with a warning.

    `TerminalScreen` resolves to the class of its new module.
    """
    with pytest.warns(
        DeprecationWarning,
        match=(
            rf"^click_extra\.capture\.recording\.{name} is deprecated and will be "
            r"removed in click-extra 11\.0\.0: "
        ),
    ):
        value = getattr(capture_recording, name)
    assert value == released


def test_recording_module_serves_no_other_missing_name():
    """A name the module never had stays missing, and sets off no warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert not hasattr(capture_recording, "TerminalScreens")
