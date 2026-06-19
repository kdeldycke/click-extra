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

from __future__ import annotations

import io
import sys
import time
from collections.abc import Callable

import pytest

import click_extra
from click_extra import Spinner
from click_extra.spinner import ASCII_SPINNER_FRAMES, SPINNER_FRAMES

# Cursor and line control codes the spinner emits, named for readable asserts.
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR_LINE = "\x1b[K"


class TTYStringIO(io.StringIO):
    """An in-memory text buffer that claims to be an interactive terminal."""

    def isatty(self) -> bool:
        return True


def wait_until(predicate: Callable[[], bool], timeout: float = 3.0) -> bool:
    """Poll ``predicate`` until it is true or ``timeout`` seconds elapse.

    Lets thread-driven assertions wait for an outcome instead of sleeping a fixed
    (and racy) amount.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_spinner_exported_from_root():
    assert click_extra.Spinner is Spinner


def test_default_stream_is_stderr():
    assert Spinner()._resolve_stream() is sys.stderr


def test_explicit_stream_is_honored():
    stream = io.StringIO()
    assert Spinner(stream=stream)._resolve_stream() is stream


@pytest.mark.parametrize(
    ("enabled", "stream", "expected"),
    (
        (None, io.StringIO(), False),
        (None, TTYStringIO(), True),
        (True, io.StringIO(), True),
        (False, TTYStringIO(), False),
    ),
)
def test_resolve_enabled(enabled, stream, expected):
    spinner = Spinner(stream=stream, enabled=enabled)
    assert spinner._resolve_enabled(stream) is expected


def test_noop_on_non_tty_stream():
    """A non-interactive stream produces no output and spawns no thread."""
    stream = io.StringIO()
    with Spinner("Brewing tea", stream=stream) as spinner:
        assert spinner._thread is None
        time.sleep(0.05)
    assert stream.getvalue() == ""


def test_delay_suppresses_quick_calls():
    """A call shorter than the delay never draws anything."""
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, delay=10)
    spinner.start()
    # Stop before the delay elapses: the thread aborts without drawing.
    spinner.stop()
    assert stream.getvalue() == ""
    assert spinner._drawn is False
    assert spinner._cursor_hidden is False


def test_draws_and_cleans_up_when_enabled():
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()

    output = stream.getvalue()
    # A frame glyph and the label were drawn.
    assert any(frame in output for frame in SPINNER_FRAMES)
    assert "Brewing tea" in output
    # The cursor was hidden during the spin and restored at the very end.
    assert HIDE_CURSOR in output
    assert output.endswith(SHOW_CURSOR)
    # The line was cleared so the spinner does not linger.
    assert CLEAR_LINE in output
    assert spinner._thread is None


def test_label_can_change_mid_spin():
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.label = "Roasting coffee"
    assert wait_until(lambda: "Roasting coffee" in stream.getvalue())
    spinner.stop()


def test_hide_cursor_disabled():
    stream = TTYStringIO()
    spinner = Spinner(
        "Brewing tea",
        stream=stream,
        interval=0.02,
        hide_cursor=False,
    )
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()

    output = stream.getvalue()
    assert HIDE_CURSOR not in output
    assert SHOW_CURSOR not in output


def test_ascii_frames():
    stream = TTYStringIO()
    spinner = Spinner(stream=stream, frames=ASCII_SPINNER_FRAMES, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()
    assert any(frame in stream.getvalue() for frame in ASCII_SPINNER_FRAMES)


def test_stop_is_idempotent_and_safe_before_start():
    spinner = Spinner("Brewing tea", stream=TTYStringIO())
    # Never started: stop is a harmless no-op.
    spinner.stop()
    spinner.start()
    spinner.stop()
    # A second stop after a real run stays a no-op.
    spinner.stop()
    assert spinner._thread is None


def test_suspend_and_resume():
    """A spinner restarts cleanly after a stop, without re-using a dead thread."""
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()
    assert spinner._thread is None

    # Resuming spins up a fresh thread and draws again, no exception raised.
    spinner.start()
    assert wait_until(lambda: spinner._thread is not None and spinner._drawn)
    spinner.stop()
    assert spinner._thread is None


@pytest.mark.parametrize("reverse", (False, True))
def test_rotation_direction(reverse):
    """Frames cycle forwards by default and backwards when ``reverse=True``."""
    stream = TTYStringIO()
    frames = ("A", "B", "C", "D")
    spinner = Spinner(stream=stream, frames=frames, reverse=reverse, interval=0.01)
    spinner.start()
    # Wait for at least two full cycles so wrap-around is observable.
    assert wait_until(lambda: stream.getvalue().count("\r") >= 2 * len(frames))
    spinner.stop()

    # Each tick writes exactly one frame glyph; extract them in drawn order.
    drawn = [char for char in stream.getvalue() if char in frames]
    step = -1 if reverse else 1
    for previous, current in zip(drawn, drawn[1:]):
        assert frames.index(current) == (frames.index(previous) + step) % len(frames)


def test_beep_rings_bell_on_stop_when_enabled():
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02, beep=True)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()
    assert "\a" in stream.getvalue()


def test_beep_silent_when_disabled():
    """A disabled spinner never beeps, even with ``beep=True``."""
    stream = io.StringIO()  # Non-TTY: the spinner is a no-op.
    with Spinner("Brewing tea", stream=stream, beep=True):
        time.sleep(0.05)
    assert stream.getvalue() == ""


def test_echo_prints_above_running_spinner():
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.echo("Kettle filled")
    spinner.stop()

    output = stream.getvalue()
    # The message appears exactly once, on its own line.
    assert output.count("Kettle filled") == 1
    # The in-progress frame is erased right before the message, so no glyph
    # shares its line.
    assert "\r" + CLEAR_LINE + "Kettle filled\n" in output


def test_echo_degrades_to_plain_write_when_disabled():
    """Off a TTY the message is still emitted, just without control codes."""
    stream = io.StringIO()  # Non-TTY: nothing is animating.
    spinner = Spinner("Brewing tea", stream=stream)
    spinner.start()  # No-op.
    spinner.echo("Kettle filled")
    spinner.stop()
    assert stream.getvalue() == "Kettle filled\n"
