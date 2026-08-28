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

"""Tests for `click_extra.recording`, which rebuilds a terminal's screen."""

from __future__ import annotations

import io
import time
from typing import cast

import pytest
from extra_platforms.pytest import skip_windows

from click_extra import SPINNERS, Spinner, Style
from click_extra.recording import (
    Frame,
    ScreenRecorder,
    TerminalScreen,
    quantize,
    record_command,
)
from click_extra.screenshot import animation_digest, render_svg

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import IO

CLEAR_LINE = "\x1b[K"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
GREEN = "\x1b[32m"
RESET = "\x1b[0m"


class TTYStringIO(io.StringIO):
    """An in-memory text buffer that claims to be an interactive terminal."""

    def isatty(self) -> bool:
        return True


def snapshots(stream: str) -> list[str]:
    """Replay a stream, keeping the screen each redraw leaves behind.

    Splitting on the erase-in-line is what a real sampler does with timestamps
    instead: every animation ends a frame with one.

    :param stream: what a command wrote, control sequences and all.
    :return: the distinct screens, in the order they were drawn.
    """
    seen: list[str] = []
    screen = TerminalScreen()
    for piece in stream.split(CLEAR_LINE):
        screen.feed(piece + CLEAR_LINE)
        if screen.display and (not seen or seen[-1] != screen.display):
            seen.append(screen.display)
    return seen


@pytest.mark.parametrize(
    ("stream", "expected"),
    (
        pytest.param("plain", "plain", id="text"),
        pytest.param("one\ntwo", "one\ntwo", id="newline-starts-a-row"),
        pytest.param("apricot\rfig", "fig", id="return-redraws-the-row"),
        pytest.param("apricot\rfig\rplum", "plum", id="two-returns"),
        pytest.param(f"apricot{CLEAR_LINE}", "apricot", id="erase-past-the-cursor"),
        pytest.param(f"apricot\r{CLEAR_LINE}", "", id="erase-from-the-start"),
        pytest.param(f"{HIDE_CURSOR}fig{SHOW_CURSOR}", "fig", id="cursor-visibility"),
        pytest.param("\x1b[2;5Hfig", "fig", id="an-unfollowed-sequence-is-dropped"),
        pytest.param("one\rtwo\nthree", "two\nthree", id="return-then-newline"),
    ),
)
def test_screen_replays_a_stream(stream, expected):
    """The screen shows what a terminal would, for the vocabulary it follows."""
    screen = TerminalScreen()
    screen.feed(stream)
    assert screen.display == expected


def test_screen_keeps_a_color_set_between_a_return_and_its_text():
    """A color opened after the cursor comes back still wraps what follows.

    An animation writes the return, then its color, then the text. Redrawing the
    row when the *text* lands rather than when the cursor comes back throws that
    color away, and the frame draws in the terminal's default ink.
    """
    screen = TerminalScreen()
    screen.feed(f"apricot\r{GREEN}fig{RESET}{CLEAR_LINE}")
    assert screen.display == f"{GREEN}fig{RESET}"


def test_screen_feeds_the_same_whether_split_or_whole():
    """A stream arriving in pieces lands where the whole of it would.

    A recorder reads whatever the terminal hands it, which is not aligned on
    anything: a frame routinely arrives across two reads.
    """
    stream = f"apricot\r{GREEN}fig{RESET}{CLEAR_LINE}\rplum{CLEAR_LINE}"
    whole = TerminalScreen()
    whole.feed(stream)

    piecewise = TerminalScreen()
    for index in range(len(stream)):
        piecewise.feed(stream[index : index + 1])
    assert piecewise.display == whole.display


def test_screen_counts_a_wide_glyph_by_its_cells():
    """A wide glyph covers the two cells it is drawn with.

    The count is what says whether the cursor sits at the start of a row, which
    is what an erase-in-line acts on.
    """
    screen = TerminalScreen()
    screen.feed("🌑")
    screen.feed(CLEAR_LINE)
    # Past the start of the row, so the erase leaves the glyph alone.
    assert screen.display == "🌑"


def test_screen_recovers_every_frame_a_spinner_draws(monkeypatch):
    """Replaying a real spinner's stream gives back its frames, and only those.

    The end of the loop this module exists to close: `frame_lines()` says what
    the spinner draws, the spinner writes it at a terminal, and the screen
    rebuilds those same lines out of the stream.
    """
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    stream = TTYStringIO()
    spinner = Spinner(
        "Steeping",
        spinner=SPINNERS["moon"],
        style=Style(fg="green"),
        stream=stream,
        interval=0.02,
        enabled=True,
    )
    spinner.start()
    # Long enough to draw every frame of an eight-frame preset at 20ms each.
    time.sleep(0.4)
    spinner.stop()

    recovered = set(snapshots(stream.getvalue()))
    assert recovered, "the spinner drew nothing to replay"
    assert recovered <= set(spinner.frame_lines()), (
        f"recovered a line the spinner never draws: "
        f"{sorted(recovered - set(spinner.frame_lines()))}"
    )


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
        ("python", "-c", BAR_SCRIPT),
        columns=40,
        duration=5.0,
    )

    assert [frame.text for frame in frames] == ["[]", "[#]", "[##]", "[###]"]
    assert all(frame.duration > 0 for frame in frames)


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
