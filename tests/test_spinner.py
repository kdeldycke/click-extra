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
import itertools
import re
import sys
import time
from collections.abc import Callable

import pytest

import click_extra
from click_extra import (
    SPINNERS,
    ProgressOption,
    Spinner,
    SpinnerPreset,
    Style,
    command,
    echo,
    pass_context,
)
from click_extra.context import PROGRESS
from click_extra.spinner import ASCII_SPINNER_FRAMES, SPINNER_FRAMES
from click_extra.theme import KO_GLYPH, OK_GLYPH

# Cursor and line control codes the spinner emits, named for readable asserts.
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR_LINE = "\x1b[K"

# ANSI styling codes click.style emits, named for readable color asserts.
GREEN = "\x1b[32m"
RED = "\x1b[31m"
BOLD = "\x1b[1m"
BG_RED = "\x1b[41m"


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
    for previous, current in itertools.pairwise(drawn):
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


def test_progress_option_is_a_default_option():
    """ProgressOption ships in the default option set of every extra command."""

    @command
    def cli():
        echo("hi")

    assert any(isinstance(p, ProgressOption) for p in cli.params)


@pytest.mark.parametrize(
    ("args", "expected"),
    (
        # Progress is on by default.
        ((), True),
        # Explicit opt-out wins.
        (("--no-progress",), False),
        # Color is decoupled: --no-color strips color but keeps the spinner,
        # like cargo, npm, pip, Rich, indicatif and ora.
        (("--no-color",), True),
        # --accessible disables it: a screen reader wants no spinning glyph.
        (("--accessible",), False),
    ),
)
def test_progress_option_resolution(invoke, args, expected):
    """``ctx.meta[PROGRESS]`` follows --progress and --accessible, never color."""

    @command
    @pass_context
    def cli(ctx):
        echo(f"progress={ctx.meta[PROGRESS]}")

    result = invoke(cli, *args)
    assert f"progress={expected}" in result.stdout


@pytest.mark.parametrize("term", ("dumb", "unknown"))
def test_dumb_terminal_disables_spinner(monkeypatch, term):
    """A cursor-less terminal self-disables the spinner even on a TTY."""
    monkeypatch.setenv("TERM", term)
    spinner = Spinner(stream=TTYStringIO())
    assert spinner._resolve_enabled(spinner._resolve_stream()) is False


def test_explicit_enabled_overrides_dumb_terminal(monkeypatch):
    """An explicit ``enabled=True`` wins over the ``TERM=dumb`` auto-detection."""
    monkeypatch.setenv("TERM", "dumb")
    spinner = Spinner(stream=TTYStringIO(), enabled=True)
    assert spinner._resolve_enabled(spinner._resolve_stream()) is True


def test_decorator_runs_function_inside_spinner():
    """``@spinner`` animates while the wrapped function runs and returns its result."""
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02)

    @spinner
    def brew(cups):
        # The spinner is animating while this body runs.
        assert wait_until(lambda: spinner._drawn)
        return cups * 2

    assert brew(3) == 6
    # The context exited, so the spinner cleaned up after the call.
    assert spinner._thread is None
    assert SHOW_CURSOR in stream.getvalue()


def test_bare_decorator_without_parentheses():
    """``@Spinner`` with no parentheses wraps the function with default settings."""

    @Spinner
    def double(value):
        return value * 2

    # The spinner is a no-op on the captured (non-TTY) default stream, but the
    # wrapped function still runs and returns its value through the decorator.
    assert double(21) == 42
    # The instance masquerades as the function (functools.update_wrapper).
    assert double.__name__ == "double"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("env", "stream_factory", "expected"),
    (
        ({}, TTYStringIO, True),
        ({}, io.StringIO, False),
        ({"NO_COLOR": "1"}, TTYStringIO, False),
        ({"FORCE_COLOR": "1"}, io.StringIO, True),
    ),
)
def test_resolve_color_enabled(monkeypatch, env, stream_factory, expected):
    """Color follows NO_COLOR / FORCE_COLOR then TTY, with no command context."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    stream = stream_factory()
    assert Spinner(stream=stream)._resolve_color_enabled(stream) is expected


def test_color_applied_on_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    stream = TTYStringIO()
    spinner = Spinner(
        "Brewing tea", stream=stream, style=Style(fg="green"), interval=0.02
    )
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()
    assert GREEN in stream.getvalue()


def test_color_stripped_but_spinner_still_spins_when_disabled(monkeypatch):
    """NO_COLOR strips the spinner's color but never stops it spinning."""
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    stream = TTYStringIO()
    spinner = Spinner(
        "Brewing tea", stream=stream, style=Style(fg="green"), interval=0.02
    )
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()

    output = stream.getvalue()
    assert GREEN not in output  # Color stripped.
    assert any(frame in output for frame in SPINNER_FRAMES)  # Still spinning.


def test_style_applied_to_spinner(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    stream = TTYStringIO()
    spinner = Spinner(
        "Brewing tea",
        stream=stream,
        style=Style(bg="red", bold=True),
        interval=0.02,
    )
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()

    output = stream.getvalue()
    assert BOLD in output
    assert BG_RED in output


def test_invalid_style_raises():
    with pytest.raises(ValueError, match="Invalid spinner style"):
        Spinner(style=Style(fg="notacolor"))


def test_ok_leaves_persistent_success_line(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.ok()

    output = stream.getvalue()
    # The success line is kept (not erased) with the themed success glyph.
    assert output.endswith(" Brewing tea\n")
    assert OK_GLYPH in output
    assert GREEN in output  # Default theme paints the success glyph green.
    assert spinner._thread is None


def test_fail_leaves_persistent_failure_line(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.fail()

    output = stream.getvalue()
    assert output.endswith(" Brewing tea\n")
    assert KO_GLYPH in output
    assert RED in output  # Default theme paints the error glyph red.


def test_ok_degrades_to_plain_line_when_disabled(monkeypatch):
    """Off a TTY the outcome is still recorded, without symbol color."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    stream = io.StringIO()  # Non-TTY: nothing animates.
    spinner = Spinner("Brewing tea", stream=stream)
    spinner.start()  # No-op.
    spinner.ok()
    assert stream.getvalue() == f"{OK_GLYPH} Brewing tea\n"


def test_timer_appended_to_frames_and_final_line():
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, timer=True, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.ok()

    output = stream.getvalue()
    # Elapsed time shows on the live spinner and on the kept final line.
    assert re.search(r"\(\d+\.\ds\)", output)


def test_elapsed_time_freezes_after_stop():
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02)
    spinner.start()
    time.sleep(0.05)
    spinner.stop()
    frozen = spinner.elapsed_time
    assert frozen > 0
    # Once stopped, the clock no longer advances.
    time.sleep(0.05)
    assert spinner.elapsed_time == frozen


def test_catalog_is_complete():
    """The cli-spinners / ora catalog is present and well-formed."""
    assert len(SPINNERS) == 90
    assert all(isinstance(p, SpinnerPreset) for p in SPINNERS.values())
    # Every preset has at least one frame and a positive interval.
    assert all(p.frames and p.interval > 0 for p in SPINNERS.values())
    # A few well-known names are present.
    for name in ("dots", "line", "moon", "clock", "bouncingBar", "dots8Bit"):
        assert name in SPINNERS
    # dots / line reuse the module's existing frame constants.
    assert SPINNERS["dots"].frames == SPINNER_FRAMES
    assert SPINNERS["line"].frames == ASCII_SPINNER_FRAMES
    # The 256-frame 8-bit animation round-tripped through its packed form.
    assert len(SPINNERS["dots8Bit"].frames) == 256


def test_spinner_preset_supplies_frames_and_interval():
    preset = SPINNERS["dots2"]
    spinner = Spinner(spinner=preset)
    assert spinner.frames == preset.frames
    assert spinner.interval == preset.interval


def test_explicit_frames_and_interval_override_preset():
    spinner = Spinner(
        spinner=SPINNERS["moon"], frames=ASCII_SPINNER_FRAMES, interval=0.5
    )
    assert spinner.frames == ASCII_SPINNER_FRAMES  # Explicit frames win.
    assert spinner.interval == 0.5  # Explicit interval wins.


def test_defaults_without_frames_or_preset():
    spinner = Spinner()
    assert spinner.frames == SPINNER_FRAMES
    assert spinner.interval == 0.1


def test_multichar_preset_renders():
    """A multi-character animation (which upstream `\\b` renderers drop) draws."""
    preset = SPINNERS["bouncingBar"]
    assert any(len(frame) > 1 for frame in preset.frames)  # Multi-char frames.
    stream = TTYStringIO()
    spinner = Spinner(stream=stream, spinner=preset, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()
    assert any(frame in stream.getvalue() for frame in preset.frames)
