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
import re
import time
from itertools import pairwise
from typing import cast

import pytest
from extra_platforms.pytest import skip_windows

from click_extra import SPINNERS, Spinner, Style, unstyle
from click_extra.recording import (
    DEFAULT_SUBMIT,
    Frame,
    ScreenRecorder,
    TerminalScreen,
    ansi_prefix,
    quantize,
    record_and_render,
    record_command,
    type_line,
)
from click_extra.screenshot import (
    CELL_HEIGHT,
    CELL_WIDTH,
    LINE_HEIGHT,
    animation_digest,
    render_svg,
)
from click_extra.screenshot_presets import Cursor

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
        pytest.param("one\r\ntwo", "one\ntwo", id="return-newline-keeps-the-row"),
        pytest.param(
            f"spin{CLEAR_LINE}\r{CLEAR_LINE}done\r\n\rnext{CLEAR_LINE}",
            "done\nnext",
            id="trail-choreography",
        ),
    ),
)
def test_screen_replays_a_stream(stream, expected):
    """The screen shows what a terminal would, for the vocabulary it follows."""
    screen = TerminalScreen()
    screen.feed(stream)
    assert screen.display == expected


def test_screen_keeps_a_color_set_between_a_return_and_its_text():
    """A color opened after the cursor comes back still wraps what follows.

    An animation writes the return, then its color, then the text. The redraw
    is deferred until something lands on the row, and the color is the first
    thing to land: it must trigger the clear and survive it, or the frame
    draws in the terminal's default ink.
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
        ("python", "-c", SPLIT_GLYPH_SCRIPT),
        columns=40,
        duration=5.0,
    )

    assert frames, "the command drew nothing"
    assert frames[-1].text == "\u2570 ripe"
    assert all("\ufffd" not in frame.text for frame in frames)


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_and_render_draws_the_prompt_on_every_frame():
    """The stated invocation leads each frame, styled as a shell prompt."""
    svg, returncode = record_and_render(
        ("python", "-c", BAR_SCRIPT),
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
        ("python", "-c", BAR_SCRIPT),
        columns=40,
        prompt="",
        unique_id="bare-run",
    )
    assert "python" not in svg


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_and_render_reports_the_exit_code():
    """The command's own verdict travels beside the picture of it."""
    _svg, returncode = record_and_render(
        ("python", "-c", "import sys; print('rotten'); sys.exit(3)"),
        columns=40,
        prompt="",
    )
    assert returncode == 3


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_record_and_render_refuses_an_empty_recording():
    """A command that drew nothing leaves nothing to animate."""
    with pytest.raises(ValueError, match="drew no screen"):
        record_and_render(("python", "-c", "pass"), columns=40)


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
    assert typed[-1].duration == 0.4


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
        ("python", "-c", BAR_SCRIPT),
        columns=40,
        prompt="basket ripen --all",
        unique_id="orchard",
    )
    typed, _ = record_and_render(
        ("python", "-c", BAR_SCRIPT),
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
    """The default opens on the finished prompt, as every recording so far does."""
    svg, _ = record_and_render(
        ("python", "-c", BAR_SCRIPT),
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
        ("python", "-c", script),
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
