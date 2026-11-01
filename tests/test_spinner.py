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
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import click
import pytest
from extra_platforms.pytest import skip_windows

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
    progress_option,
)
from click_extra.cli import (
    _TOUR_CAP,
    _TOUR_CYCLES,
    _TOUR_MIN,
    _tour_duration,
    demo,
)
from click_extra.context import PROGRESS, START_TIME
from click_extra.layout import cell_width
from click_extra.pytest import command_decorators
from click_extra.spinner import (
    CLEAR_LINE,
    HIDE_CURSOR,
    SHOW_CURSOR,
    _can_draw,
    _color_enabled,
    _enable_windows_ansi,
    _resolve_timer,
    active_spinner,
    trail_glyph,
)
from click_extra.spinner_presets import ASCII_SPINNER_FRAMES, SPINNER_FRAMES
from click_extra.theme import KO_GLYPH, OK_GLYPH

from .conftest import StallingTTY, TTYStringIO, wait_until

# ANSI styling codes click.style emits, named for readable color asserts.
GREEN = "\x1b[32m"
RED = "\x1b[31m"
BOLD = "\x1b[1m"
BG_RED = "\x1b[41m"


def test_spinner_exported_from_root():
    assert click_extra.Spinner is Spinner


def test_default_stream_is_stderr():
    assert Spinner()._resolve_stream() is sys.stderr


def test_explicit_stream_is_honored():
    stream = io.StringIO()
    assert Spinner(stream=stream)._resolve_stream() is stream


@pytest.mark.parametrize(
    ("live", "stream", "expected"),
    (
        ("auto", io.StringIO(), False),
        ("auto", TTYStringIO(), True),
        ("always", io.StringIO(), True),
        ("never", TTYStringIO(), False),
    ),
)
def test_can_draw(live, stream, expected):
    assert _can_draw(live, stream) is expected


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


def test_shown_false_when_not_drawn():
    """``shown`` stays False whenever no frame reaches the terminal."""
    # Never started.
    assert Spinner("Brewing tea", stream=TTYStringIO()).shown is False
    # Disabled (non-TTY stream): the spinner is a silent no-op.
    disabled = Spinner("Brewing tea", stream=io.StringIO())
    disabled.start()
    disabled.stop()
    assert disabled.shown is False
    # Enabled but finishing within the delay, before the first frame.
    delayed = Spinner("Brewing tea", stream=TTYStringIO(), delay=10)
    delayed.start()
    delayed.stop()
    assert delayed.shown is False


def test_shown_true_after_drawing():
    """``shown`` flips to True once a frame is drawn, and stays True after stop."""
    spinner = Spinner("Brewing tea", stream=TTYStringIO(), interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner.shown)
    spinner.stop()
    assert spinner.shown is True


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


@pytest.mark.parametrize(
    "cmd_decorator",
    # Skip click extra's commands, as the progress option is already part of the
    # default.
    command_decorators(no_groups=True, no_extra=True),
)
@pytest.mark.parametrize("option_decorator", (progress_option, progress_option()))
def test_standalone_progress_option(invoke, cmd_decorator, option_decorator):
    @cmd_decorator
    @option_decorator
    @pass_context
    def standalone_progress(ctx):
        echo(f"progress={ctx.meta[PROGRESS]}")

    result = invoke(standalone_progress, "--help", color=False)
    assert "--progress / --no-progress" in result.stdout
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(standalone_progress)
    assert result.stdout == "progress=True\n"

    result = invoke(standalone_progress, "--no-progress")
    assert result.stdout == "progress=False\n"


@pytest.mark.parametrize(
    ("args", "draws"),
    (
        ((), True),
        # The spinner reads the flag on its own, as the progress bar does.
        (("--no-progress",), False),
        (("--accessible",), False),
        # Color stays decoupled from progress.
        (("--no-color",), True),
    ),
)
def test_auto_spinner_follows_progress_flag(invoke, args, draws):
    """A `live="auto"` spinner stays still under `--no-progress` and `--accessible`,
    even on a terminal, with no wiring in the command."""
    stream = TTYStringIO()

    @command
    def cli():
        spinner = Spinner("Brewing tea", stream=stream, interval=0.02)
        spinner.start()
        if draws:
            assert wait_until(lambda: spinner._drawn)
        else:
            assert not wait_until(lambda: spinner._drawn, timeout=0.2)
        spinner.stop()

    result = invoke(cli, *args)
    assert result.exit_code == 0
    assert ("Brewing tea" in stream.getvalue()) is draws


def test_spinner_stop_leaves_a_stalled_drawing_thread_behind(monkeypatch):
    """`stop()` gives up on a drawing thread stuck in a write after the grace,
    instead of hanging the Ctrl+C that asked for the stop."""
    monkeypatch.setattr("click_extra.spinner._STOP_GRACE", 0.2)
    stream = StallingTTY()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    stream.stall.set()
    assert stream.blocked.wait(3)
    # Frees an unbounded join after a while, so a regression fails, not hangs.
    releaser = threading.Timer(3, stream.release.set)
    releaser.start()
    try:
        start = time.monotonic()
        spinner.stop()
        assert time.monotonic() - start < 2
    finally:
        stream.release.set()
        releaser.cancel()


SPINNING_SCRIPT = """
import sys
import time

from click_extra import Spinner

Spinner("Brewing tea", stream=sys.stdout, live="always", interval=0.02).start()
time.sleep(30)
"""
"""A process spinning until something kills it."""


@skip_windows(reason="Windows terminates a process without running any handler")
def test_sigterm_shows_the_cursor_again(tmp_path):
    """A spinner killed by `SIGTERM` leaves its terminal with the cursor shown,
    and the process still dies by `SIGTERM`."""
    script = tmp_path / "spin.py"
    script.write_text(SPINNING_SCRIPT, encoding="UTF-8")
    process = subprocess.Popen((sys.executable, str(script)), stdout=subprocess.PIPE)
    try:
        assert process.stdout is not None
        output = b""
        deadline = time.monotonic() + 10
        while b"\x1b[?25l" not in output and time.monotonic() < deadline:
            output += os.read(process.stdout.fileno(), 4096)
        assert b"\x1b[?25l" in output
        process.terminate()
        rest, _ = process.communicate(timeout=10)
        output += rest
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    assert process.returncode == -signal.SIGTERM
    assert output.rfind(b"\x1b[?25h") > output.rfind(b"\x1b[?25l")


@pytest.mark.parametrize("term", ("dumb", "unknown"))
def test_dumb_terminal_disables_spinner(monkeypatch, term):
    """A cursor-less terminal self-disables the spinner even on a TTY."""
    monkeypatch.setenv("TERM", term)
    assert _can_draw("auto", TTYStringIO()) is False


def test_live_always_overrides_dumb_terminal(monkeypatch):
    """An explicit ``live="always"`` wins over the ``TERM=dumb`` auto-detection."""
    monkeypatch.setenv("TERM", "dumb")
    assert _can_draw("always", TTYStringIO()) is True


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
        # An empty value counts as unset, and LLM refuses color: the fallback reads
        # the variables exactly as resolve_color_env() does.
        ({"NO_COLOR": ""}, TTYStringIO, True),
        ({"FORCE_COLOR": ""}, io.StringIO, False),
        ({"LLM": "1"}, TTYStringIO, False),
        # A dumb terminal strips color even on a TTY, matching resolve_color_env().
        ({"TERM": "dumb"}, TTYStringIO, False),
        ({"TERM": "unknown"}, TTYStringIO, False),
        # FORCE_COLOR stays authoritative over a dumb terminal.
        ({"TERM": "dumb", "FORCE_COLOR": "1"}, io.StringIO, True),
    ),
)
def test_resolve_color_enabled(monkeypatch, env, stream_factory, expected):
    """Color follows FORCE_COLOR / dumb TERM / NO_COLOR then TTY, with no context."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert _color_enabled(stream_factory()) is expected


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


def test_style_alone_keeps_painting_the_line_as_one_run():
    """Without a part style, `style` still wraps the whole line, byte for byte."""
    style = Style(fg="green")
    spinner = Spinner("Brewing tea", frames=("*",), style=style, timer=True)
    assert spinner.frame_lines() == (style("* Brewing tea (0.0s)"),)


@pytest.mark.parametrize(
    ("options", "glyph", "label", "timer"),
    (
        pytest.param(
            {"label_style": Style(italic=True), "timer_style": Style(dim=True)},
            "*",
            Style(italic=True)(" Brewing tea"),
            Style(dim=True)(" (0.0s)"),
            id="each-part-its-own",
        ),
        pytest.param(
            {"style": Style(fg="green"), "timer_style": Style(dim=True)},
            Style(fg="green")("*"),
            Style(fg="green")(" Brewing tea"),
            Style(dim=True)(" (0.0s)"),
            id="label-falls-back-to-style",
        ),
        pytest.param(
            {"style": Style(fg="green"), "label_style": Style(bold=True)},
            Style(fg="green")("*"),
            Style(bold=True)(" Brewing tea"),
            Style(fg="green")(" (0.0s)"),
            id="timer-falls-back-to-style",
        ),
    ),
)
def test_part_styles_paint_their_own_part(options, glyph, label, timer):
    """Each part carries its leading space and takes its own style over `style`.

    The timer's parentheses belong to its part, which is what a `timer`
    callable formatting only the duration cannot reach.
    """
    spinner = Spinner("Brewing tea", frames=("*",), timer=True, **options)
    assert spinner.frame_lines() == (f"{glyph}{label}{timer}",)


@pytest.mark.parametrize(
    "options",
    (
        pytest.param({}, id="no-style"),
        pytest.param({"style": Style(fg="green")}, id="style"),
        pytest.param(
            {"label_style": Style(bold=True), "timer_style": Style(dim=True)},
            id="part-styles",
        ),
    ),
)
def test_color_off_strips_escapes_embedded_in_the_label(options):
    """A label styled by hand renders plain when color is off, like any other."""
    label = f"{Style(fg='red')('kettle')}: {Style(italic=True)('boiling water')}"
    spinner = Spinner(label, frames=("*",), timer=True, **options)
    assert spinner.frame_lines(color=False) == ("* kettle: boiling water (0.0s)",)


def test_kept_line_paints_label_and_timer_with_part_styles(monkeypatch):
    """`ok()` paints its label and timer with the part styles, when color is on."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    stream = TTYStringIO()
    spinner = Spinner(
        "Brewing tea",
        stream=stream,
        timer=True,
        label_style=Style(italic=True),
        timer_style=Style(dim=True),
        interval=0.02,
    )
    spinner.start()
    # Wait for a frame: `ok()` erases it with a clear-to-end-of-line, and that
    # erasure is what the kept line is isolated from below. A finisher landing
    # between the hide-cursor write and the first frame leaves no clear at all.
    assert wait_until(lambda: spinner._drawn)
    spinner.ok(symbol="*", style=Style(fg="green"))
    written = stream.getvalue().rpartition(CLEAR_LINE)[2]
    line = written.removeprefix(SHOW_CURSOR).removesuffix("\n")
    assert line.startswith(Style(fg="green")("*") + Style(italic=True)(" Brewing tea"))
    # The whole clock, parentheses included, sits inside the dim run.
    assert re.fullmatch(r".*\x1b\[2m \([^)]+\)\x1b\[0m", line)


def test_kept_line_strips_embedded_escapes_with_color_off():
    """Off a TTY, `ok()` writes the label plain, embedded escapes included."""
    stream = io.StringIO()
    spinner = Spinner(Style(fg="red")("Brewing tea"), stream=stream)
    spinner.ok(symbol="*")
    assert stream.getvalue() == "* Brewing tea\n"


@pytest.mark.parametrize(
    "options",
    (
        pytest.param({"label_style": Style(fg="notacolor")}, id="label_style"),
        pytest.param({"timer_style": Style(fg="notacolor")}, id="timer_style"),
    ),
)
def test_invalid_part_style_raises(options):
    with pytest.raises(ValueError, match="Invalid spinner style"):
        Spinner(**options)


def test_frame_lines_are_what_the_animation_draws(monkeypatch):
    """A picture of a spinner shows the lines the spinner really writes.

    Spins for real, recovers every frame written to the stream, and asserts each
    one is a line `frame_lines()` offers. Composing the picture separately from
    the animation is what lets the two drift the first time the glyph, the label
    or the timer change places; comparing them is what stops that.
    """
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    stream = TTYStringIO()
    spinner = Spinner(
        "Brewing tea",
        spinner=SPINNERS["moon"],
        style=Style(fg="green"),
        stream=stream,
        interval=0.02,
    )
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()

    # Every frame is written as a carriage return, the line, then a clear to
    # end-of-line. The last one is the erasure `stop()` leaves, carrying no line.
    drawn = set()
    for written in stream.getvalue().split("\r"):
        if not written.endswith(CLEAR_LINE):
            continue
        content = written.removesuffix(CLEAR_LINE)
        if content:
            drawn.add(content)

    assert drawn
    assert drawn <= set(spinner.frame_lines())


def test_frame_lines_honors_reverse():
    """A spinner cycling backwards is pictured spinning the way it animates."""
    preset = SPINNERS["moon"]
    forward = Spinner("Brewing tea", spinner=preset).frame_lines(color=False)
    backward = Spinner("Brewing tea", spinner=preset, reverse=True).frame_lines(
        color=False
    )
    assert backward == tuple(reversed(forward))


@pytest.mark.parametrize("color", (True, False))
def test_frame_lines_colors_on_request(color):
    """A capture asks for color whatever stream the spinner would have drawn on.

    A spinner that never started resolved no color for itself, so the picture
    has to state its own answer rather than inherit that one.
    """
    spinner = Spinner("Brewing tea", spinner=SPINNERS["moon"], style=Style(fg="green"))
    assert not spinner._color
    lines = spinner.frame_lines(color=color)
    assert lines
    assert all((GREEN in line) is color for line in lines)


@pytest.mark.parametrize(
    ("outcome", "glyph", "color"),
    (
        # Default theme paints the success glyph green, the error glyph red.
        ("ok", OK_GLYPH, GREEN),
        ("fail", KO_GLYPH, RED),
    ),
)
def test_outcome_leaves_persistent_line(monkeypatch, outcome, glyph, color):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    stream = TTYStringIO()
    spinner = Spinner("Brewing tea", stream=stream, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    getattr(spinner, outcome)()

    output = stream.getvalue()
    # The outcome line is kept (not erased) with the themed glyph and color.
    assert output.endswith(" Brewing tea\n")
    assert glyph in output
    assert color in output
    assert spinner._thread is None


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


def test_timer_accepts_custom_formatter():
    """A callable ``timer`` formats the elapsed seconds itself (yaspin #236)."""
    stream = TTYStringIO()
    spinner = Spinner(
        "Brewing tea", stream=stream, timer=lambda s: f"t{s:.0f}", interval=0.02
    )
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.ok()

    output = stream.getvalue()
    assert "(t0)" in output  # Custom format, on the spinner and the ok() line.
    assert "0.0s" not in output  # The default format is not used.


def test_enable_windows_ansi_is_a_safe_noop():
    """The Windows VT-enable never raises: off Windows, or on a stream with no
    usable console handle (the path the spinner exercises on every platform)."""
    _enable_windows_ansi(io.StringIO())  # No real fileno.
    _enable_windows_ansi(sys.stderr)


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
    assert len(SPINNERS) == 89
    assert all(isinstance(p, SpinnerPreset) for p in SPINNERS.values())
    # Every preset has at least one frame and a positive interval.
    assert all(p.frames and p.interval > 0 for p in SPINNERS.values())
    # A few well-known names are present.
    for name in ("dots", "line", "moon", "clock", "bouncing-bar", "dots-8bit"):
        assert name in SPINNERS
    # dots / line reuse the module's existing frame constants.
    assert SPINNERS["dots"].frames == SPINNER_FRAMES
    assert SPINNERS["line"].frames == ASCII_SPINNER_FRAMES
    # The 256-frame 8-bit animation round-tripped through its packed form.
    assert len(SPINNERS["dots-8bit"].frames) == 256


@pytest.mark.parametrize("name", sorted(SPINNERS))
def test_catalog_frames_share_one_width(name):
    """Every frame of a preset occupies the same number of terminal cells.

    A ragged preset moves its label a cell in and out as the animation turns,
    and a capture laid out on the frames reserves a column for the widest one.
    """
    widths = {cell_width(frame) for frame in SPINNERS[name].frames}
    assert len(widths) == 1, f"{name} mixes frame widths {sorted(widths)}"


@pytest.mark.parametrize("name", sorted(SPINNERS))
def test_catalog_frames_carry_no_upstream_padding(name):
    """No preset pads every one of its frames with a trailing space.

    Upstream writes its emoji frames that way. Kept, the space lands next to the
    one the spinner writes before its label and reads as a double gap.
    """
    frames = SPINNERS[name].frames
    assert not all(frame.endswith(" ") for frame in frames), (
        f"{name} pads every frame: {frames[0]!r}"
    )


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
    assert spinner.interval == pytest.approx(0.5)  # Explicit interval wins.


def test_defaults_without_frames_or_preset():
    spinner = Spinner()
    assert spinner.frames == SPINNER_FRAMES
    assert spinner.interval == pytest.approx(0.1)


def test_multichar_preset_renders():
    r"""A multi-character animation (which upstream `\b` renderers drop) draws."""
    preset = SPINNERS["bouncing-bar"]
    assert any(len(frame) > 1 for frame in preset.frames)  # Multi-char frames.
    stream = TTYStringIO()
    spinner = Spinner(stream=stream, spinner=preset, interval=0.02)
    spinner.start()
    assert wait_until(lambda: spinner._drawn)
    spinner.stop()
    assert any(frame in stream.getvalue() for frame in preset.frames)


def _catalog_row_count(output: str) -> int:
    """Count data rows in a rendered spinner catalog table.

    Each row carries two time cells (Interval and Tour), so the count of
    ``X.Ys`` values is halved.
    """
    plain = click.unstyle(output)
    return len(re.findall(r"\d\.\d+s", plain)) // 2


def test_demo_spinner_table_lists_selection(invoke):
    """`--table` prints the catalog table; the tour stays TTY-only."""
    result = invoke(demo, "spinner", "--table")
    assert result.exit_code == 0
    # The table lists its column headers and a spread of curated spinner names.
    for token in ("Name", "Frames", "Interval", "Tour", "dots", "moon", "bouncing-bar"):
        assert token in result.stdout


def test_demo_spinner_without_table_flag_shows_no_table(invoke):
    """Off a TTY and without --table, the command renders no table."""
    result = invoke(demo, "spinner")
    assert result.exit_code == 0
    assert _catalog_row_count(result.output) == 0
    assert "Interval" not in result.output


def test_demo_spinner_tour_column_shows_three_cycle_time(invoke):
    """The Tour column reports 3 × frames × interval (dots = 2.4s)."""
    result = invoke(demo, "spinner", "--select", "dots", "--table")
    assert result.exit_code == 0
    assert "Tour" in result.output
    assert "2.4s" in result.output  # dots: 10 frames × 0.08s × 3 cycles.


def test_demo_spinner_all_lists_full_catalog(invoke):
    result = invoke(demo, "spinner", "--all", "--table")
    assert result.exit_code == 0
    assert _catalog_row_count(result.output) == len(SPINNERS)  # Every preset.
    assert "dots-8bit" in result.output  # Present in --all, absent from default.


def test_demo_spinner_select_filters_by_name(invoke):
    result = invoke(demo, "spinner", "--select", "mindblown,pong,shark", "--table")
    assert result.exit_code == 0
    assert _catalog_row_count(result.output) == 3  # Exactly the three named.
    for name in ("mindblown", "pong", "shark"):
        assert name in result.output
    assert "dots-8bit" not in result.output


def test_demo_spinner_select_rejects_unknown(invoke):
    result = invoke(demo, "spinner", "--select", "pong,nope")
    assert result.exit_code != 0
    assert "Unknown spinner" in result.output
    assert "nope" in result.output


def test_demo_spinner_random_limits_count(invoke):
    result = invoke(demo, "spinner", "--random", "7", "--table")
    assert result.exit_code == 0
    assert _catalog_row_count(result.output) == 7


def test_demo_spinner_options_are_mutually_exclusive(invoke):
    result = invoke(demo, "spinner", "--all", "--select", "pong")
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_tour_duration_bounds_dwell():
    """The tour dwell aims for three cycles, clamped to [_TOUR_MIN, _TOUR_CAP],
    and never trims a huge spinner below one full cycle."""
    # dots: three cycles (2.4s) fall within the bounds, used as-is.
    dots = SPINNERS["dots"]
    one_cycle = len(dots.frames) * dots.interval
    assert _tour_duration(dots) == _TOUR_CYCLES * one_cycle
    assert _TOUR_MIN <= _tour_duration(dots) <= _TOUR_CAP

    # toggle11: three cycles (0.3s) fall below the floor → bumped to the minimum.
    assert _tour_duration(SPINNERS["toggle11"]) == _TOUR_MIN

    # pong: three cycles (7.2s) exceed the cap but one cycle (2.4s) fits → clamp.
    assert _tour_duration(SPINNERS["pong"]) == _TOUR_CAP

    # dots-8bit: even one cycle exceeds the cap → exactly one full cycle.
    big = SPINNERS["dots-8bit"]
    one_big_cycle = len(big.frames) * big.interval
    assert one_big_cycle > _TOUR_CAP
    assert _tour_duration(big) == one_big_cycle


def test_active_spinner_registry_lifecycle():
    """A started spinner advertises itself, keyed by stream, until stopped."""
    assert active_spinner() is None

    # A huge delay keeps the animation registered without ever drawing a frame,
    # making the test timing-free.
    spinner = Spinner("work", live="always", delay=3600)
    spinner.start()
    try:
        assert active_spinner() is spinner
        assert active_spinner(sys.stderr) is spinner
        # No spinner animates on stdout.
        assert active_spinner(sys.stdout) is None
    finally:
        spinner.stop()
    assert active_spinner() is None

    # stop() is idempotent, deregistering only once.
    spinner.stop()
    assert active_spinner() is None


def test_active_spinner_ignores_disabled_spinner():
    """A disabled spinner never animates, so it never registers either."""
    spinner = Spinner("silent", live="never")
    spinner.start()
    try:
        assert active_spinner() is None
    finally:
        spinner.stop()


@pytest.mark.parametrize(
    ("args", "kwargs", "expected"),
    (
        pytest.param((True,), {"color": False}, OK_GLYPH, id="success-bare"),
        pytest.param((False,), {"color": False}, KO_GLYPH, id="failure-bare"),
        pytest.param((True, "+"), {"color": False}, "+", id="symbol"),
        pytest.param(
            (False, None, Style(fg="cyan")),
            {},
            Style(fg="cyan")(KO_GLYPH),
            id="style",
        ),
    ),
)
def test_trail_glyph(args, kwargs, expected):
    """The glyph takes a symbol and a style in place of the theme's."""
    assert trail_glyph(*args, **kwargs) == expected


def test_color_resolution_reaches_worker_threads(monkeypatch):
    """A spinner started on a worker thread sees the invocation's `--no-color`.

    The thread-local command context is absent there, so the published
    invocation color is what carries the decision, and it outranks the
    environment it was reconciled from.
    """
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setattr("click_extra.color._invocation_color", False)
    stream = TTYStringIO()
    answers = []
    worker = threading.Thread(target=lambda: answers.append(_color_enabled(stream)))
    worker.start()
    worker.join()
    assert answers == [False]


def test_resolve_timer_follows_time_flag():
    """`timer=None` follows the --time flag; explicit settings pass through."""
    # Explicit settings are returned unchanged, in or out of a context.
    assert _resolve_timer(True) is True
    assert _resolve_timer(False) is False

    def custom(seconds):
        return f"{seconds}s"

    assert _resolve_timer(custom) is custom
    # None outside any command context: off.
    assert _resolve_timer(None) is False
    # None inside a command: off without the --time marker, on with it.
    with click.Context(click.Command("noop")) as ctx:
        assert _resolve_timer(None) is False
        ctx.meta[START_TIME] = 1.0  # Set by TimerOption under --time.
        assert _resolve_timer(None) is True


def test_spinner_rejects_invalid_live():
    """`live` must be one of `WHEN`."""
    with pytest.raises(ValueError, match='"auto", "always" or "never"'):
        Spinner(live="sometimes")  # type: ignore[arg-type]


def test_spinner_timer_follows_time_flag():
    """A spinner's default `timer` follows --time, as a trail's does."""
    assert Spinner().timer is False
    with click.Context(click.Command("noop")) as ctx:
        assert Spinner().timer is False
        ctx.meta[START_TIME] = 1.0  # Set by TimerOption under --time.
        assert Spinner().timer is True
        assert Spinner(timer=False).timer is False


CUSTOM_CSS = Path(__file__).parent.parent / "docs" / "_static" / "custom.css"
"""Stylesheet carrying the documentation's `unicode-range` declaration."""

GRIDLESS_BLOCKS = (
    (0x2500, 0x257F),  # Box drawing, which the catalog's own table borders use.
    (0x2580, 0x259F),  # Block elements.
    (0x25A0, 0x25FF),  # Geometric shapes.
    (0x2800, 0x28FF),  # Braille patterns.
)
"""Ranges no mainstream monospace font carries a glyph for.

A browser substitutes one that knows nothing of the character grid, so these
come out narrow or wide and a captured table's columns slide apart along the
row. `docs/_static/custom.css` binds a subset font to exactly these.
"""


def declared_unicode_ranges() -> list[tuple[int, int]]:
    """Read the codepoint spans the documentation's stylesheet claims."""
    css = CUSTOM_CSS.read_text(encoding="UTF-8")
    declaration = re.search(r"unicode-range:\s*([^;]+);", css)
    assert declaration, "the stylesheet declares no unicode-range"
    spans = []
    for entry in declaration.group(1).split(","):
        # A span is written `U+2500-257F`, with the `U+` stated once only.
        bounds = re.match(r"U\+([0-9A-Fa-f]+)(?:-([0-9A-Fa-f]+))?", entry.strip())
        assert bounds, f"{entry.strip()!r} is not a codepoint span"
        low = int(bounds.group(1), 16)
        spans.append((low, int(bounds.group(2), 16) if bounds.group(2) else low))
    return spans


@pytest.mark.once
def test_catalog_gridless_glyphs_are_covered_by_the_docs_font(invoke):
    """Every glyph a browser cannot size is one the documentation ships a font for.

    The catalog table is laid out on a character grid, and a browser only
    reproduces that if every glyph advances by one cell. `custom.css` binds a
    subset font to the ranges no ordinary monospace font carries; this checks
    the two have not drifted apart, which they would the moment the declaration
    is narrowed or a spinner starts drawing from a range it omits.

    ```{note}
    Narrower than the problem it guards: it checks the ranges already known to
    need a font, not that a *newly* used range has been noticed. A spinner
    drawn from some other gridless block would pass here and still misalign.
    ```
    """
    result = invoke(demo, args=["--no-color", "spinner", "--all", "--table"])
    assert result.exit_code == 0

    declared = declared_unicode_ranges()
    used = {
        ord(character)
        for character in result.stdout
        if any(low <= ord(character) <= high for low, high in GRIDLESS_BLOCKS)
    }
    assert used, "the catalog drew none of the glyphs this is about"

    uncovered = sorted(
        codepoint
        for codepoint in used
        if not any(low <= codepoint <= high for low, high in declared)
    )
    assert not uncovered, (
        "the documentation ships no font for "
        f"{', '.join(f'U+{codepoint:04X}' for codepoint in uncovered)}"
    )


SPINNER_ASSETS = Path(__file__).parent.parent / "docs" / "assets"
"""Directory the inventory gallery writes one animation per preset into."""


@pytest.mark.once
def test_every_spinner_has_a_committed_animation():
    """The inventory gallery covers the catalog exactly, one asset per preset.

    The gallery is generated from `SPINNERS` at build time, so a new preset
    grows an asset on the next build and this only fails on a *committed*
    tree that has fallen behind. The stray half matters more: a renamed or
    dropped preset leaves its old animation behind, where nothing references
    it and nothing would notice.
    """
    committed = {
        path.name.removeprefix("spinner-").removesuffix(".svg")
        for path in SPINNER_ASSETS.glob("spinner-*.svg")
    }
    assert not sorted(set(SPINNERS) - committed), "presets with no animation"
    assert not sorted(committed - set(SPINNERS)), "animations with no preset"
