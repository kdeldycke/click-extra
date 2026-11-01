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
import re
import threading
import time

import click
import pytest

import click_extra
from click_extra import SPINNERS, Style
from click_extra.cli import _TRAIL_BATCH, demo
from click_extra.spinner import SHOW_CURSOR, _active_line, active_spinner
from click_extra.theme import KO_GLYPH, OK_GLYPH
from click_extra.trail import (
    OperationTrail,
    _BarIndicator,
    _SpinnerIndicator,
    trail_line,
)

from .conftest import StallingTTY, TTYStringIO, wait_until


def test_bar_stop_leaves_a_stalled_ticker_behind(monkeypatch):
    """The progress bar's elapsed-clock ticker gets the same bounded stop."""
    monkeypatch.setattr("click_extra.spinner._STOP_GRACE", 0.2)
    stream = StallingTTY()
    indicator = _BarIndicator(
        label="Fetching feeds",
        unit="feeds",
        total=3,
        delay=0,
        live="always",
        stream=stream,
        timer=True,
    )
    releaser = threading.Timer(3, stream.release.set)
    # stop() is idempotent: the exit of the block finds the bar already stopped.
    with indicator:
        assert indicator._ticker is not None
        stream.stall.set()
        assert stream.blocked.wait(3)
        releaser.start()
        try:
            start = time.monotonic()
            indicator.stop()
            assert time.monotonic() - start < 2
        finally:
            stream.release.set()
            releaser.cancel()


def test_bar_teardown_after_a_stall_returns_at_once(monkeypatch):
    """A second teardown of a bar whose ticker stalled does not wait on it.

    The stalled ticker holds the draw lock while it blocks in its write. A Ctrl+C
    inside a trail runs `finish()`, then `stop()`, and the second one must not
    take that lock and wait for the terminal to drain.
    """
    monkeypatch.setattr("click_extra.spinner._STOP_GRACE", 0.2)
    stream = StallingTTY()
    indicator = _BarIndicator(
        label="Fetching feeds",
        unit="feeds",
        total=3,
        delay=0,
        live="always",
        stream=stream,
        timer=True,
    )
    releaser = threading.Timer(3, stream.release.set)
    with indicator:
        stream.stall.set()
        assert stream.blocked.wait(3)
        releaser.start()
        try:
            start = time.monotonic()
            indicator.finish(False, "Interrupted after 0/3 feeds")
            indicator.stop()
            assert time.monotonic() - start < 2
        finally:
            stream.release.set()
            releaser.cancel()


@pytest.mark.parametrize(
    ("progress_bar", "jobs", "stream_factory"),
    (
        pytest.param(True, 1, TTYStringIO, id="bar"),
        pytest.param(False, 2, TTYStringIO, id="concurrent-spinner"),
        pytest.param(False, 1, io.StringIO, id="sequential"),
    ),
)
def test_interrupted_trail_closes_with_a_finisher(progress_bar, jobs, stream_factory):
    """A Ctrl+C inside the trail still ends it on a `✘` line saying how far it
    got, and an outcome landing afterwards prints below that line."""
    stream = stream_factory()
    trail = OperationTrail(
        label="Fetching",
        unit="feeds",
        total=5,
        jobs=jobs,
        progress_bar=progress_bar,
        live="always",
        stream=stream,
        timer=False,
        delay=0,
    )

    def interrupted_batch():
        with trail:
            trail.mark(True, "feed-a fetched")
            trail.mark(True, "feed-b fetched")
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        interrupted_batch()
    # A task the CLI waited on after the Ctrl+C finishes now.
    trail.mark(True, "feed-c fetched")

    plain = click.unstyle(stream.getvalue())
    assert "feed-a fetched" in plain
    finisher = f"{KO_GLYPH} Interrupted after 2/5 feeds"
    assert finisher in plain
    assert plain.index("feed-c fetched") > plain.index(finisher)


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
    "args",
    (
        pytest.param(("trail",), id="concurrent-spinner"),
        pytest.param(("trail", "--jobs", "1"), id="sequential"),
        pytest.param(("trail", "--progress-bar"), id="progress-bar"),
        pytest.param(("trail", "--progress-bar", "--eta"), id="progress-bar-eta"),
        # A group option, so it goes before the subcommand.
        pytest.param(("--no-progress", "trail"), id="no-progress"),
    ),
)
def test_demo_trail_prints_plain_lines_off_tty(invoke, monkeypatch, args):
    """Every rendering runs the batch to completion and, off a TTY, prints each
    outcome and the finisher as plain lines, with no indicator drawn."""
    # Skip the real per-vegetable pauses so the batch completes instantly.
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    result = invoke(demo, *args)
    assert result.exit_code == 0
    # No spinner or bar drew: either one writes a carriage return to redraw.
    assert "\r" not in result.output
    # Drop the timing suffix that --eta turns on, then compare the text alone.
    lines = [
        re.sub(r" \([^)]*\)$", "", line)
        for line in click.unstyle(result.output).splitlines()
    ]
    # Concurrent workers land in any order, but the finisher always closes.
    assert sorted(lines[:-1]) == sorted(
        f"{OK_GLYPH} {name} roasted" if roasted else f"{KO_GLYPH} {name} scorched"
        for name, _seconds, roasted in _TRAIL_BATCH
    )
    assert lines[-1] == f"{KO_GLYPH} Roasted 5/6 vegetables"


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


def test_sequential_trail_echoes_off_tty():
    """A non-interactive stream gets the trail lines and finisher by default."""
    stream = io.StringIO()
    trail = OperationTrail(label="Fetching", unit="feeds", total=1, stream=stream)
    trail.mark(True, "feed-a fetched")
    trail.finish(True, "Fetched 1/1 feeds")
    assert click.unstyle(stream.getvalue()).splitlines() == [
        f"{OK_GLYPH} feed-a fetched",
        f"{OK_GLYPH} Fetched 1/1 feeds",
    ]
    assert trail.ok_count == 1


def test_sequential_trail_invisible_stays_silent_off_tty():
    """`visible=False` silences the trail on a non-interactive stream too."""
    stream = io.StringIO()
    trail = OperationTrail(total=1, visible=False, stream=stream)
    trail.mark(True, "feed-a fetched")
    trail.finish(True, "Fetched 1/1 feeds")
    assert stream.getvalue() == ""
    # The tally is kept regardless of rendering.
    assert trail.ok_count == 1


def test_trail_forced_spinner_draws_on_pipe():
    """`live="always"` animates the aggregate spinner on a non-interactive stream."""
    stream = io.StringIO()
    with OperationTrail(
        label="Syncing", unit="repos", total=2, jobs=2, live="always", stream=stream
    ) as trail:
        assert wait_until(
            lambda: trail._indicator is not None and trail._indicator.shown
        )
        assert "Syncing 0/2 repos" in click.unstyle(stream.getvalue())


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


def test_concurrent_trail_invisible_stays_silent():
    """`visible=False` keeps the concurrent spinner and its buffer off screen."""
    stream = TTYStringIO()
    with OperationTrail(total=1, jobs=4, visible=False, stream=stream) as trail:
        trail.mark(False, "repo-a failed")
        trail.finish(False, "Synced 0/1 repos")
    assert stream.getvalue() == ""
    assert trail.ok_count == 0


@pytest.mark.parametrize(
    "rendering",
    (
        pytest.param({"jobs": 2}, id="concurrent-spinner"),
        pytest.param({"progress_bar": True}, id="progress-bar"),
    ),
)
@pytest.mark.parametrize("finished", (True, False), ids=("finished", "left-early"))
def test_trail_echoes_a_batch_its_indicator_never_drew(rendering, finished):
    """A batch finishing inside `delay` still leaves its whole record on screen.

    Its indicator never drew, so the lines it buffered never reached the
    stream. A sequential batch of the same outcomes prints them, and so must
    this one, in order: before the finisher, or on its own when the batch is
    left without one.
    """
    stream = TTYStringIO()
    with OperationTrail(
        label="Syncing", unit="repos", total=2, delay=30.0, stream=stream, **rendering
    ) as trail:
        trail.mark(True, "repo-a synced")
        trail.mark(False, "repo-b failed")
        if finished:
            trail.finish(False, "Synced 1/2 repos")
    assert trail._indicator is None
    expected = [trail_line(True, "repo-a synced"), trail_line(False, "repo-b failed")]
    if finished:
        expected.append(trail_line(False, "Synced 1/2 repos"))
    assert stream.getvalue().splitlines() == expected


@pytest.mark.parametrize(
    ("options", "stream_class"),
    (
        pytest.param({"echo_sequential": False}, TTYStringIO, id="echo-opt-out"),
        pytest.param(
            {"echo_sequential": False}, io.StringIO, id="echo-opt-out-off-tty"
        ),
        pytest.param({"visible": False}, TTYStringIO, id="invisible"),
    ),
)
@pytest.mark.parametrize("finished", (True, False), ids=("finished", "left-early"))
def test_trail_leaves_nothing_for_an_undrawn_batch_without_echo(
    options, stream_class, finished
):
    """The echo of an undrawn batch obeys the same gates as a sequential one."""
    stream = stream_class()
    with OperationTrail(total=1, jobs=2, delay=30.0, stream=stream, **options) as trail:
        trail.mark(True, "repo-a synced")
        if finished:
            trail.finish(True, "Synced 1/1 repos")
    assert stream.getvalue() == ""
    assert trail.ok_count == 1


@pytest.mark.parametrize(
    "rendering",
    (
        pytest.param({"jobs": 2}, id="concurrent-spinner"),
        pytest.param({"progress_bar": True}, id="progress-bar"),
    ),
)
def test_trail_stays_plain_above_a_drawn_indicator_without_color(
    monkeypatch, rendering
):
    """With color off, a drawn indicator's trail lines and finisher carry no SGR.

    Those lines reach the stream through a raw write rather than
    `click.echo`, so the glyph's paint and any escape embedded in the message
    have to be stripped before the write.
    """
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("click_extra.color._invocation_color", False)
    stream = TTYStringIO()
    with OperationTrail(
        label="Syncing", unit="repos", total=2, stream=stream, **rendering
    ) as trail:
        assert wait_until(
            lambda: trail._indicator is not None and trail._indicator.shown
        )
        trail.mark(True, f"{Style(fg='red')('repo-a')} synced")
        trail.mark(False, "repo-b failed")
        trail.finish(False, "Synced 1/2 repos")
    output = stream.getvalue()
    assert re.search(r"\x1b\[[0-9;]*m", output) is None
    assert f"{OK_GLYPH} repo-a synced" in output
    assert f"{KO_GLYPH} repo-b failed" in output
    assert f"{KO_GLYPH} Synced 1/2 repos" in output


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
        live="always",
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
        total=2, jobs=1, live="always", stream=stream, timer=True
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
        total=1, jobs=1, live="always", stream=stream, timer=True
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
        total=1, jobs=1, live="always", stream=stream, timer=False
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
        live="always",
        stream=stream,
        timer=lambda seconds: f"{seconds * 1000:.0f}ms",
    ) as trail:
        trail.mark(True, "carrots roasted", seconds=2.4)
        trail.finish(True, "Roasted 1/1 vegetables")
    assert "carrots roasted (2400ms)" in stream.getvalue()


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
        total=3, progress_bar=True, live="always", stream=stream, timer=True
    ) as trail:
        indicator = trail._indicator
        assert isinstance(indicator, _BarIndicator)
        assert indicator._bar is not None
        assert indicator._bar.show_eta is False  # No Click ETA.
        assert indicator._ticker is not None  # A ticker drives the clock.
        # The elapsed clock is on screen from the start, before any outcome.
        plain = click.unstyle(stream.getvalue())
        assert re.search(r"0/3\s+\d\.\ds", plain)


def test_progress_bar_clock_eta_uses_click_eta():
    """clock='eta' keeps Click's estimated-time display and runs no ticker."""
    stream = TTYStringIO()
    with OperationTrail(
        total=3,
        progress_bar=True,
        live="always",
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
        total=3, progress_bar=True, live="always", stream=stream, timer=True
    ):
        # No mark is made: only the ticker moves the clock past 0.0s.
        assert wait_until(
            lambda: bool(
                re.search(
                    r"0/3\s+0\.[1-9]s",
                    click.unstyle(stream.getvalue()),
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


def test_operation_trail_rejects_invalid_live():
    """`live` must be 'auto', 'always' or 'never'."""
    with pytest.raises(ValueError, match='"auto", "always" or "never"'):
        OperationTrail(live="sometimes")  # type: ignore[arg-type]


def test_invisible_trail_draws_nothing_even_when_live_always():
    """`visible=False` wins over `live="always"`: no indicator, no line."""
    stream = TTYStringIO()
    with OperationTrail(
        total=2, jobs=2, visible=False, live="always", stream=stream
    ) as trail:
        trail.mark(True, "repo-a synced")
        trail.finish(True, "Synced 1/2 repos")
    assert stream.getvalue() == ""
    assert trail.ok_count == 1


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


@pytest.mark.parametrize(
    "rendering",
    (
        pytest.param({"jobs": 2}, id="concurrent-spinner"),
        pytest.param({"progress_bar": True}, id="progress-bar"),
    ),
)
@pytest.mark.parametrize(
    ("stream_class", "term", "options"),
    (
        pytest.param(io.StringIO, None, {}, id="off-tty"),
        pytest.param(TTYStringIO, "dumb", {}, id="dumb-terminal"),
        pytest.param(TTYStringIO, None, {"live": "never"}, id="live-never"),
    ),
)
def test_trail_echoes_live_where_no_indicator_draws(
    monkeypatch, rendering, stream_class, term, options
):
    """Where no indicator draws, each outcome prints as soon as it is marked.

    Nothing owns the live line there, so no line waits for a first frame that
    never comes, and no cursor control reaches the stream.
    """
    if term:
        monkeypatch.setenv("TERM", term)
    stream = stream_class()
    with OperationTrail(
        label="Syncing", unit="repos", total=2, stream=stream, **rendering, **options
    ) as trail:
        trail.mark(True, "repo-a synced")
        assert click.unstyle(stream.getvalue()) == f"{OK_GLYPH} repo-a synced\n"
        trail.mark(False, "repo-b failed")
        trail.finish(False, "Synced 1/2 repos")
    output = stream.getvalue()
    assert click.unstyle(output).splitlines() == [
        f"{OK_GLYPH} repo-a synced",
        f"{KO_GLYPH} repo-b failed",
        f"{KO_GLYPH} Synced 1/2 repos",
    ]
    assert "\r" not in output
    assert "\x1b[K" not in output
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
