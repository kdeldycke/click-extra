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
import threading
import time
from collections.abc import Callable

import click
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
from click_extra.cli import demo
from click_extra.context import PROGRESS, START_TIME
from click_extra.spinner import (
    _TOUR_CAP,
    _TOUR_CYCLES,
    _TOUR_MIN,
    OperationTrail,
    _active_line,
    _BarIndicator,
    _resolve_timer,
    _SpinnerIndicator,
    _tour_duration,
    active_spinner,
    trail_line,
)
from click_extra.spinner_presets import ASCII_SPINNER_FRAMES, SPINNER_FRAMES
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
    ("args", "expected_hidden"),
    (
        # Shown by default.
        ((), False),
        # --no-progress hides the determinate bar, just like the spinner.
        (("--no-progress",), True),
        # Color is decoupled: --no-color keeps the bar, only stripping its color.
        (("--no-color",), False),
        # --accessible hides it: a screen reader wants no animated bar.
        (("--accessible",), True),
    ),
)
def test_progressbar_follows_progress_flag(invoke, args, expected_hidden):
    """click_extra.progressbar gates ``hidden`` on the resolved --progress flag."""

    @command
    def cli():
        bar = click_extra.progressbar([1, 2, 3], label="Brewing tea")
        echo(f"hidden={bar.hidden}")

    result = invoke(cli, *args)
    assert f"hidden={expected_hidden}" in result.stdout


@pytest.mark.parametrize("forced", (True, False))
def test_progressbar_explicit_hidden_overrides_flag(invoke, forced):
    """An explicit ``hidden=`` wins over --no-progress, like echo(color=...)."""

    @command
    def cli():
        bar = click_extra.progressbar([1, 2, 3], hidden=forced)
        echo(f"hidden={bar.hidden}")

    # --no-progress would otherwise force hidden=True; the explicit value stands.
    result = invoke(cli, "--no-progress")
    assert f"hidden={forced}" in result.stdout


def test_progressbar_shown_without_active_context():
    """Outside a Click command the bar defaults to shown, like click.progressbar."""
    bar = click_extra.progressbar([1, 2, 3])
    assert bar.hidden is False


@pytest.mark.parametrize(
    ("args", "label_shown"),
    (
        ((), True),
        (("--no-progress",), False),
    ),
)
def test_progressbar_label_emission_off_tty(invoke, args, label_shown):
    """Off a TTY a shown bar still emits its label once; a hidden one emits nothing."""

    @command
    def cli():
        with click_extra.progressbar([1, 2, 3], label="Brewing tea") as bar:
            for _ in bar:
                pass

    result = invoke(cli, *args)
    assert ("Brewing tea" in result.output) is label_shown


def test_progressbar_shows_final_position_with_update_min_steps():
    """Work around pallets/click#3571: with show_pos and an update_min_steps that
    does not divide the length, the bar must still land on total/total instead of
    freezing at the last multiple (14/20 for length 20, update_min_steps 7)."""
    stream = TTYStringIO()
    with click_extra.progressbar(
        range(20), show_pos=True, update_min_steps=7, file=stream
    ) as bar:
        for _ in bar:
            pass
    output = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", stream.getvalue())
    assert "20/20" in output


def test_progressbar_show_eta_follows_time_flag():
    """The bar's ETA follows --time by default; an explicit show_eta wins."""
    # No command context: ETA off.
    assert click_extra.progressbar([1, 2, 3]).show_eta is False
    with click.Context(click.Command("noop")) as ctx:
        # --no-time / default: no marker → off.
        assert click_extra.progressbar([1, 2, 3]).show_eta is False
        ctx.meta[START_TIME] = 1.0  # --time sets the marker.
        assert click_extra.progressbar([1, 2, 3]).show_eta is True
    # An explicit value overrides the flag.
    assert click_extra.progressbar([1, 2, 3], show_eta=False).show_eta is False


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
    Spinner._enable_windows_ansi(io.StringIO())  # No real fileno.
    Spinner._enable_windows_ansi(sys.stderr)


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


def _catalog_row_count(output: str) -> int:
    """Count data rows in a rendered spinner catalog table.

    Each row carries two time cells (Interval and Tour), so the count of
    ``X.Ys`` values is halved.
    """
    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    return len(re.findall(r"\d\.\d+s", plain)) // 2


def test_demo_spinner_table_lists_selection(invoke):
    """`--table` prints the catalog table; the tour stays TTY-only."""
    result = invoke(demo, "spinner", "--table")
    assert result.exit_code == 0
    # The table lists its column headers and a spread of curated spinner names.
    for token in ("Name", "Frames", "Interval", "Tour", "dots", "moon", "bouncingBar"):
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
    assert _catalog_row_count(result.output) == len(SPINNERS)  # All 90 rows.
    assert "dots8Bit" in result.output  # Present in --all, absent from default.


def test_demo_spinner_select_filters_by_name(invoke):
    result = invoke(demo, "spinner", "--select", "mindblown,pong,shark", "--table")
    assert result.exit_code == 0
    assert _catalog_row_count(result.output) == 3  # Exactly the three named.
    for name in ("mindblown", "pong", "shark"):
        assert name in result.output
    assert "dots8Bit" not in result.output


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


def test_demo_trail_help_lists_renderings(invoke):
    """`trail --help` documents its purpose and the rendering-selecting options."""
    result = invoke(demo, "trail", "--help")
    assert result.exit_code == 0
    assert "Trace a simulated batch of operations" in result.stdout
    for token in ("--progress-bar", "--eta", "--elapsed", "--spinner", "--jobs"):
        assert token in result.stdout


def test_demo_trail_rejects_unknown_spinner(invoke):
    """An unknown --spinner name is rejected by the Choice type before any work."""
    result = invoke(demo, "trail", "--spinner", "nope")
    assert result.exit_code != 0
    assert "'nope' is not one of" in result.output
    assert "moon" in result.output  # The valid names are listed.


@pytest.mark.parametrize(
    "extra_args",
    (
        pytest.param((), id="concurrent-spinner"),
        pytest.param(("--jobs", "1"), id="sequential"),
        pytest.param(("--progress-bar",), id="progress-bar"),
        pytest.param(("--progress-bar", "--eta"), id="progress-bar-eta"),
    ),
)
def test_demo_trail_runs_silently_off_tty(invoke, monkeypatch, extra_args):
    """Every rendering runs the batch to completion and, off a TTY, stays silent."""
    # Skip the real per-vegetable pauses so the batch completes instantly.
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    result = invoke(demo, "trail", *extra_args)
    assert result.exit_code == 0
    # Off a TTY the trail draws no indicator and echoes no lines.
    assert result.output == ""


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

    # dots8Bit: even one cycle exceeds the cap → exactly one full cycle.
    big = SPINNERS["dots8Bit"]
    one_big_cycle = len(big.frames) * big.interval
    assert one_big_cycle > _TOUR_CAP
    assert _tour_duration(big) == one_big_cycle


def test_active_spinner_registry_lifecycle():
    """A started spinner advertises itself, keyed by stream, until stopped."""
    assert active_spinner() is None

    # A huge delay keeps the animation registered without ever drawing a frame,
    # making the test timing-free.
    spinner = Spinner("work", enabled=True, delay=3600)
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
    spinner = Spinner("silent", enabled=False)
    spinner.start()
    try:
        assert active_spinner() is None
    finally:
        spinner.stop()


def test_operation_trail_exported_from_root():
    assert click_extra.OperationTrail is OperationTrail


def test_trail_line_carries_themed_glyphs():
    assert OK_GLYPH in trail_line(True, "backup saved")
    assert "backup saved" in trail_line(True, "backup saved")
    assert KO_GLYPH in trail_line(False, "backup failed")


def test_sequential_trail_echoes_lines_and_finisher():
    """A sequential batch on a TTY echoes each outcome, then a timed finisher."""
    stream = TTYStringIO()
    trail = OperationTrail(
        label="Fetching", unit="feeds", total=2, stream=stream, timer=True
    )
    trail.mark(True, "feed-a fetched")
    trail.mark(False, "feed-b failed")
    trail.finish(False, "Fetched 1/2 feeds")
    lines = stream.getvalue().splitlines()
    assert len(lines) == 3
    assert "feed-a fetched" in lines[0] and OK_GLYPH in lines[0]
    assert "feed-b failed" in lines[1] and KO_GLYPH in lines[1]
    assert re.search(r"Fetched 1/2 feeds \(\d+\.\ds\)", lines[2])
    assert trail.ok_count == 1


def test_sequential_trail_silent_off_tty():
    """A non-interactive stream gets no trail at all by default."""
    stream = io.StringIO()
    trail = OperationTrail(label="Fetching", unit="feeds", total=1, stream=stream)
    trail.mark(True, "feed-a fetched")
    trail.finish(True, "Fetched 1/1 feeds")
    assert stream.getvalue() == ""
    # The tally is kept regardless of rendering.
    assert trail.ok_count == 1


def test_sequential_trail_forced_on_pipe():
    """`enabled=True` forces the sequential echo onto a non-interactive stream."""
    stream = io.StringIO()
    trail = OperationTrail(total=1, enabled=True, stream=stream)
    trail.mark(True, "done")
    assert "done" in stream.getvalue()


def test_sequential_trail_echo_opt_out():
    """`echo_sequential=False` silences a sequential batch, even on a TTY."""
    stream = TTYStringIO()
    trail = OperationTrail(total=1, echo_sequential=False, stream=stream)
    trail.mark(True, "done")
    trail.finish(True, "Done 1/1")
    assert stream.getvalue() == ""
    assert trail.ok_count == 1


def test_concurrent_trail_buffers_until_spinner_draws():
    """Outcomes marked before the aggregate spinner first draws are buffered,
    then flushed above it; the finisher becomes the spinner's kept line.

    The draw delay guarantees the first mark lands before the first frame, making
    the buffering deterministic instead of racing the animation thread.
    """
    stream = TTYStringIO()
    with OperationTrail(
        label="Syncing",
        unit="repos",
        total=2,
        jobs=2,
        delay=0.2,
        stream=stream,
    ) as trail:
        # Marked before the first frame: buffered, nothing rendered yet beyond
        # at most a frame of the spinner itself.
        trail.mark(True, "repo-a synced")
        assert "repo-a synced" not in stream.getvalue()
        assert wait_until(
            lambda: trail._indicator is not None and trail._indicator.shown
        )
        trail.mark(True, "repo-b synced")
        trail.finish(True, "Synced 2/2 repos")
    output = stream.getvalue()
    assert "repo-a synced" in output
    assert "repo-b synced" in output
    assert "Synced 2/2 repos" in output
    assert OK_GLYPH in output
    assert trail.ok_count == 2


def test_concurrent_trail_disabled_stays_silent():
    """`enabled=False` keeps the concurrent spinner and its buffer off screen."""
    stream = TTYStringIO()
    with OperationTrail(total=1, jobs=4, enabled=False, stream=stream) as trail:
        trail.mark(False, "repo-a failed")
        trail.finish(False, "Synced 0/1 repos")
    assert stream.getvalue() == ""
    assert trail.ok_count == 0


def test_concurrent_trail_marks_are_thread_safe():
    """Concurrent mark() calls from worker threads all land in the tally."""
    stream = TTYStringIO()
    with OperationTrail(label="Crunching", total=32, jobs=8, stream=stream) as trail:
        workers = [
            threading.Thread(target=trail.mark, args=(True, f"item-{i} done"))
            for i in range(32)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        trail.finish(True, "Crunched 32/32 items")
    assert trail.ok_count == 32


def test_concurrent_trail_uses_chosen_spinner_preset():
    """`spinner=` picks the concurrent aggregate spinner's animation."""
    stream = TTYStringIO()
    preset = SPINNERS["moon"]
    with OperationTrail(total=2, jobs=2, spinner=preset, stream=stream) as trail:
        assert isinstance(trail._indicator, _SpinnerIndicator)
        assert trail._indicator._spinner.frames == preset.frames
        assert trail._indicator._spinner.interval == preset.interval


def test_concurrent_spinner_eta_mode():
    """clock='eta' drives the concurrent spinner's estimate from a hidden Click
    bar (stepped per outcome), and the finisher still shows the elapsed total."""
    stream = TTYStringIO()
    with OperationTrail(
        label="Fetching",
        unit="feeds",
        total=4,
        jobs=4,
        enabled=True,
        stream=stream,
        timer=True,
        clock="eta",
    ) as trail:
        indicator = trail._indicator
        assert isinstance(indicator, _SpinnerIndicator)
        assert indicator._eta_bar is not None  # A hidden bar drives the estimate.
        assert indicator._spinner.timer is False  # No elapsed clock while running.
        trail.mark(True, "feed-a fetched", seconds=0.1)
        assert indicator._eta_bar.pos == 1  # advance() steps the hidden bar.
        # Wait for the spinner's first frame: finish() drops its kept line when
        # the spinner has not drawn yet (matching the delay semantics), so
        # without this the summary races the render thread. The GIL usually
        # serializes that race; free-threaded parallelism exposes it.
        assert wait_until(
            lambda: trail._indicator is not None and trail._indicator.shown
        )
        trail.finish(True, "Fetched 4/4 feeds")
    # A finished batch has no ETA: the finisher carries the elapsed total.
    assert re.search(r"Fetched 4/4 feeds \(\d", stream.getvalue())


def test_operation_trail_appends_per_operation_timing():
    """With timer on (the default), a `seconds` value appends each operation's
    own duration to its trail line, independent of the others."""
    stream = TTYStringIO()
    with OperationTrail(
        total=2, jobs=1, enabled=True, stream=stream, timer=True
    ) as trail:
        trail.mark(True, "carrots roasted", seconds=2.4)
        trail.mark(False, "leeks scorched", seconds=0.7)
        trail.finish(trail.ok_count == 2, "Roasted 1/2 vegetables")
    output = stream.getvalue()
    assert "carrots roasted (2.4s)" in output
    assert "leeks scorched (0.7s)" in output


def test_operation_handle_times_from_its_creation():
    """An operation() handle marks its outcome with the elapsed since it began."""
    stream = TTYStringIO()
    with OperationTrail(
        total=1, jobs=1, enabled=True, stream=stream, timer=True
    ) as trail:
        op = trail.operation()
        op.mark(True, "carrots roasted")
        trail.finish(True, "Roasted 1/1 vegetables")
    # The value is wall-clock, so match the appended-clock shape, not a number.
    assert re.search(r"carrots roasted \(\d+\.\ds\)", stream.getvalue())


def test_operation_trail_timer_false_drops_all_timing():
    """timer=False silences both the per-item and the finisher clock."""
    stream = TTYStringIO()
    with OperationTrail(
        total=1, jobs=1, enabled=True, stream=stream, timer=False
    ) as trail:
        trail.mark(True, "carrots roasted", seconds=2.4)
        trail.finish(True, "Roasted 1/1 vegetables")
    output = stream.getvalue()
    assert "carrots roasted" in output and "(2.4s)" not in output
    assert not re.search(r"vegetables \(\d", output)  # No finisher clock.


def test_operation_trail_timer_callable_formats_durations():
    """A callable timer formats the per-item durations it is handed."""
    stream = TTYStringIO()
    with OperationTrail(
        total=1,
        jobs=1,
        enabled=True,
        stream=stream,
        timer=lambda seconds: f"{seconds * 1000:.0f}ms",
    ) as trail:
        trail.mark(True, "carrots roasted", seconds=2.4)
        trail.finish(True, "Roasted 1/1 vegetables")
    assert "carrots roasted (2400ms)" in stream.getvalue()


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


def test_progress_bar_trail_renders_bar_and_finisher():
    """`progress_bar=True` drives a determinate bar with outcomes above it."""
    stream = TTYStringIO()
    with OperationTrail(
        label="Fetching",
        unit="feeds",
        total=3,
        progress_bar=True,
        stream=stream,
        timer=True,
    ) as trail:
        trail.mark(True, "feed-a fetched")
        trail.mark(False, "feed-b failed")
        trail.mark(True, "feed-c fetched")
        trail.finish(trail.ok_count == 3, f"Fetched {trail.ok_count}/3 feeds")
    output = stream.getvalue()
    # Each outcome leaves its persistent trail line.
    assert "feed-a fetched" in output and OK_GLYPH in output
    assert "feed-b failed" in output and KO_GLYPH in output
    # The determinate bar renders its fill and the running tally.
    assert "###" in output  # Click's default fill_char.
    assert "2/3" in output
    # The finisher replaces the bar with a kept, timed summary and shows the
    # cursor Click hid while drawing.
    assert re.search(r"Fetched 2/3 feeds \(\d+\.\ds\)", output)
    assert SHOW_CURSOR in output
    assert trail.ok_count == 2


def test_progress_bar_trail_shows_empty_bar_on_entry():
    """The bar's 0/total state draws on entry, not only once the first outcome
    advances it, matching the spinner indicator that animates its tally at once."""
    stream = TTYStringIO()
    with OperationTrail(
        label="Fetching", unit="feeds", total=4, progress_bar=True, stream=stream
    ) as trail:
        # No outcome marked yet, but the empty bar is already drawn.
        assert trail._indicator is not None and trail._indicator.shown
        assert "0/4" in stream.getvalue()
        trail.mark(True, "feed-a fetched")
    assert "1/4" in stream.getvalue()


def test_progress_bar_clock_defaults_to_elapsed():
    """clock='elapsed' (the default) draws a stopwatch from the start via
    item_show_func, with Click's ETA off and a ticker to keep it moving."""
    stream = TTYStringIO()
    with OperationTrail(
        total=3, progress_bar=True, enabled=True, stream=stream, timer=True
    ) as trail:
        indicator = trail._indicator
        assert isinstance(indicator, _BarIndicator)
        assert indicator._bar is not None
        assert indicator._bar.show_eta is False  # No Click ETA.
        assert indicator._ticker is not None  # A ticker drives the clock.
        # The elapsed clock is on screen from the start, before any outcome.
        plain = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", stream.getvalue())
        assert re.search(r"0/3\s+\d\.\ds", plain)


def test_progress_bar_clock_eta_uses_click_eta():
    """clock='eta' keeps Click's estimated-time display and runs no ticker."""
    stream = TTYStringIO()
    with OperationTrail(
        total=3,
        progress_bar=True,
        enabled=True,
        stream=stream,
        timer=True,
        clock="eta",
    ) as trail:
        indicator = trail._indicator
        assert isinstance(indicator, _BarIndicator)
        assert indicator._bar is not None
        assert indicator._bar.show_eta is True
        assert indicator._ticker is None


def test_progress_bar_elapsed_clock_ticks_between_marks():
    """The elapsed clock advances on its own between outcomes, with no mark."""
    stream = TTYStringIO()
    with OperationTrail(
        total=3, progress_bar=True, enabled=True, stream=stream, timer=True
    ):
        # No mark is made: only the ticker moves the clock past 0.0s.
        assert wait_until(
            lambda: bool(
                re.search(
                    r"0/3\s+0\.[1-9]s",
                    re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", stream.getvalue()),
                )
            )
        )


def test_operation_trail_rejects_invalid_clock():
    """`clock` must be 'elapsed' or 'eta'."""
    with pytest.raises(ValueError, match='"elapsed" or "eta"'):
        OperationTrail(
            total=1,
            progress_bar=True,
            clock="nope",  # type: ignore[arg-type]
        )


def test_progress_bar_trail_works_concurrently():
    """`progress_bar=True` also drives a concurrent batch from worker threads."""
    stream = TTYStringIO()
    with OperationTrail(
        label="Crunching",
        unit="items",
        total=16,
        jobs=8,
        progress_bar=True,
        stream=stream,
    ) as trail:
        workers = [
            threading.Thread(target=trail.mark, args=(True, f"item-{i} done"))
            for i in range(16)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        trail.finish(True, "Crunched 16/16 items")
    assert trail.ok_count == 16
    assert "Crunched 16/16 items" in stream.getvalue()


def test_progress_bar_trail_disabled_stays_silent():
    """Off a TTY, the progress-bar trail renders nothing but keeps its tally."""
    stream = io.StringIO()
    with OperationTrail(total=2, progress_bar=True, stream=stream) as trail:
        trail.mark(True, "a done")
        trail.finish(True, "Done 1/2")
    assert stream.getvalue() == ""
    assert trail.ok_count == 1


def test_progress_bar_requires_positive_total():
    """A determinate bar needs a length, so `total` must be positive."""
    with pytest.raises(ValueError, match="positive total"):
        OperationTrail(progress_bar=True, total=0)


def test_progress_bar_and_spinner_are_mutually_exclusive():
    """`progress_bar` and `spinner` select different indicators; only one may win."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        OperationTrail(progress_bar=True, total=3, spinner=SPINNERS["moon"])


def test_progress_bar_registers_as_active_line_not_spinner():
    """A drawing bar owns the active line (so logs cooperate), but is no spinner."""
    stream = TTYStringIO()
    with OperationTrail(total=3, progress_bar=True, stream=stream) as trail:
        assert _active_line(stream) is trail._indicator
        # active_spinner() skips a bar indicator: it is not a Spinner.
        assert active_spinner(stream) is None
    # The trail deregisters its indicator on exit.
    assert _active_line(stream) is None
