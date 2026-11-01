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
"""A `✓`/`✘` progress trail that reports a batch of operations.

{class}`OperationTrail` leaves a persistent {func}`trail_line` for each completed
operation, keeps a running `done/total` tally on an aggregate indicator while the
batch runs, and closes the batch with a kept summary line. The indicator is a
{class}`~click_extra.spinner.Spinner` or a determinate {func}`click.progressbar`.
"""

from __future__ import annotations

import threading
import time
from gettext import gettext as _

import click

from ._utils import AUTO
from .spinner import (
    CLEAR_LINE,
    DEFAULT_INTERVAL,
    SHOW_CURSOR,
    Spinner,
    _can_draw,
    _check_live,
    _color_enabled,
    _deregister_line,
    _enable_windows_ansi,
    _format_timer,
    _halt,
    _plain_unless,
    _register_line,
    _resolve_timer,
    _stream_or_stderr,
    _timer_suffix,
    trail_glyph,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType
    from typing import IO, Literal, Protocol, Self

    from click._termui_impl import ProgressBar

    from .color import TWhen
    from .spinner_presets import SpinnerPreset

    class _AggregateIndicator(Protocol):
        """The live aggregate indicator an {class}`OperationTrail` drives.

        Both the spinner-backed and bar-backed indicators expose this surface,
        so the trail drives either one the same way: enter it, {meth}`advance`
        the tally as outcomes land, {meth}`echo` a persistent line per outcome,
        then {meth}`finish` with a kept summary.
        """

        @property
        def shown(self) -> bool: ...
        def __enter__(self) -> Self: ...
        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> None: ...
        def advance(self, done: int) -> None: ...
        def echo(self, message: str) -> None: ...
        def finish(self, ok: bool, summary: str) -> None: ...
        def stop(self) -> None: ...


def trail_line(ok: bool, message: str) -> str:
    """Format one `✓`/`✘` trail line: a glyph followed by `message`.

    The glyph is the one {func}`~click_extra.spinner.trail_glyph` paints.
    """
    return f"{trail_glyph(ok)} {message}"


class _SpinnerIndicator:
    """An {class}`OperationTrail` aggregate indicator backed by a {class}`Spinner`.

    Carries the running ``{label} {done}/{total} {unit}`` tally on one animated
    line while completed outcomes stream above it, and closes on the spinner's
    kept {meth}`~Spinner.ok` / {meth}`~Spinner.fail` line. Used for a concurrent
    batch, where per-call spinners would collide on the shared stream.
    """

    def __init__(
        self,
        *,
        label: str,
        unit: str,
        total: int,
        delay: float,
        live: TWhen,
        stream: IO[str] | None,
        spinner: SpinnerPreset | None = None,
        timer: bool | Callable[[float], str] = True,
        clock: Literal["elapsed", "eta"] = "elapsed",
    ) -> None:
        self._label = label
        self._unit = unit
        self._total = total
        self._timer = timer
        # In eta mode a hidden Click bar supplies the rolling-average estimate,
        # shown in the spinner's label; the spinner's own elapsed timer is then
        # off, and finish() appends the total elapsed itself (a done batch has no
        # ETA). Reuses Click's make_step/format_eta rather than reimplementing it.
        self._eta_bar: ProgressBar[int] | None = None
        if timer and clock == "eta" and total > 0:
            self._eta_bar = click.progressbar(range(total))
        self._spinner = Spinner(
            self._tally(0),
            spinner=spinner,
            delay=delay,
            live=live,
            timer=False if self._eta_bar is not None else timer,
            stream=stream,
        )

    @property
    def shown(self) -> bool:
        return self._spinner.shown

    def __enter__(self) -> Self:
        self._spinner.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()

    def _tally(self, done: int) -> str:
        """The ``{label} {done}/{total} {unit}`` count the spinner carries."""
        return f"{self._label} {done}/{self._total} {self._unit}"

    def advance(self, done: int) -> None:
        """Re-label the spinner with the tally, adding the ETA in eta mode."""
        label = self._tally(done)
        if self._eta_bar is not None:
            self._eta_bar.make_step(done - self._eta_bar.pos)
            eta = self._eta_bar.format_eta()  # "" until a step lets it estimate.
            if eta:
                label = f"{label}  {eta}"
        self._spinner.label = label

    def echo(self, message: str) -> None:
        self._spinner.echo(message)

    def stop(self) -> None:
        """Halt the spinner and erase its line, with no kept line. Idempotent."""
        self._spinner.stop()

    def finish(self, ok: bool, summary: str) -> None:
        """Leave the spinner's kept `✓`/`✘` ``summary`` line, elapsed included."""
        if not self._spinner.shown:
            return
        if self._eta_bar is not None:
            # eta mode runs the spinner's own timer off, so append the batch's
            # total elapsed here (a finished batch has no time remaining).
            summary += _timer_suffix(self._timer, self._spinner.elapsed_time)
        self._spinner.label = summary
        (self._spinner.ok if ok else self._spinner.fail)()


class _BarIndicator:
    """An {class}`OperationTrail` aggregate indicator backed by a determinate
    {func}`click.progressbar`.

    Where {class}`_SpinnerIndicator` narrates an *indeterminate* pulse, this
    carries a real ``{label} [####----] {done}/{total}`` bar (the trail knows
    its `total`), with completed outcomes streaming above it exactly as they
    do over a spinner. It drives Click's bar directly rather than iterating it:
    {meth}`advance` steps and redraws it, {meth}`echo` erases it to slip a
    persistent line above, then redraws it below.

    ```{note}
    Click's {meth}`~click._termui_impl.ProgressBar.render_progress` skips a
    redraw whose line is unchanged, so {meth}`_draw` clears the bar's
    `_last_line` cache to force the post-`echo` redraw. Cursor hiding is left
    to Click (its `BEFORE_BAR` / `AFTER_BAR`); this only restores the cursor
    when it tears the bar down early.
    ```
    """

    def __init__(
        self,
        *,
        label: str,
        unit: str,
        total: int,
        delay: float,
        live: TWhen,
        stream: IO[str] | None,
        timer: bool | Callable[[float], str] = True,
        clock: Literal["elapsed", "eta"] = "elapsed",
    ) -> None:
        self._label = label
        self._unit = unit
        self._total = total
        self._delay = delay
        self._live = live
        self._stream = stream
        self._timer = timer
        self._clock = clock
        self._lock = threading.Lock()
        self._on = False
        self._drawn = False
        self._finished = False
        self._start = 0.0
        self._bar: ProgressBar[int] | None = None
        self._stop_tick = threading.Event()
        self._ticker: threading.Thread | None = None

    def _resolve_stream(self) -> IO[str]:
        return _stream_or_stderr(self._stream)

    def __enter__(self) -> Self:
        stream = self._resolve_stream()
        self._on = _can_draw(self._live, stream)
        self._start = time.monotonic()
        # show_pos renders the `{done}/{total}` tally; item_show_func appends the
        # counted unit after it (and, in elapsed mode, a running clock), echoing
        # the spinner's `3/5 feeds` phrasing. The `range(total)` iterable is never
        # consumed (advance() drives the bar directly); it just fixes the length
        # and satisfies the typed overload that carries item_show_func. Click
        # types `file` as `TextIO`, narrower than the `IO[str]` taken here.
        self._bar = click.progressbar(  # type: ignore[call-overload]
            range(self._total),
            label=self._label,
            show_pos=True,
            # Click's ETA (remaining time) is shown only in `clock="eta"` mode;
            # `clock="elapsed"` renders a running elapsed clock through
            # item_show_func instead, and a `timer`-off bar shows no time at all.
            show_eta=bool(self._timer) and self._clock == "eta",
            item_show_func=self._render_info,
            file=stream,
            hidden=not self._on,
        )
        if self._on:
            # The bar emits ANSI control codes: make a legacy Windows console
            # interpret rather than echo them, as Spinner.start does.
            _enable_windows_ansi(stream)
            _register_line(self)
            # Draw the empty bar right away (unless a delay defers the first
            # render), so its `0/total` state is visible from the start, like the
            # spinner indicator's animated tally: without this the bar appears
            # only when the first outcome advances it, leaving the screen blank
            # while the batch is already running.
            if self._delay <= 0:
                with self._lock:
                    self._draw()
            # An elapsed clock must keep ticking between outcomes; the bar has no
            # animation thread, so drive periodic redraws from a daemon ticker.
            if self._elapsed_clock():
                self._ticker = threading.Thread(target=self._tick, daemon=True)
                self._ticker.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()

    @property
    def shown(self) -> bool:
        return self._drawn

    def _draw(self) -> None:
        """Force a bar redraw, defeating Click's unchanged-line dedup."""
        assert self._bar is not None
        self._bar._last_line = None
        self._bar.render_progress()
        self._drawn = True

    def _elapsed_clock(self) -> bool:
        """Whether a running elapsed clock is drawn (timing on, `clock="elapsed"`)."""
        return bool(self._timer) and self._clock == "elapsed"

    def _render_info(self, item: int | None) -> str | None:
        """The `item_show_func`: a running elapsed clock plus the unit, or the unit.

        In `clock="elapsed"` mode with timing on, the elapsed time since the bar
        started is prepended to the counted unit (`5.0s  feeds`); an ETA bar or a
        timer-off bar shows just the unit (Click renders any ETA itself).
        """
        if self._elapsed_clock():
            clock = _format_timer(self._timer, time.monotonic() - self._start)
            return f"{clock}  {self._unit}" if self._unit else clock
        return self._unit or None

    def _tick(self) -> None:
        """Redraw periodically so the running elapsed clock keeps ticking.

        The bar, unlike the spinner, has no animation thread; without this the
        elapsed clock would freeze between outcomes. Runs only in elapsed mode:
        an ETA needs no ticking, since Click recomputes it on each step. The
        cadence is the spinner's, see {data}`~click_extra.spinner.DEFAULT_INTERVAL`.
        """
        while not self._stop_tick.wait(DEFAULT_INTERVAL):
            with self._lock:
                if self._drawn and not self._finished:
                    self._draw()

    def _stop_ticker(self) -> bool:
        """Stop and join the elapsed-clock ticker. Idempotent.

        :return: `False` when the ticker is still blocked in a write after
            {data}`~click_extra.spinner._STOP_GRACE`, so the caller skips its own
            clean-up writes.
        """
        if self._ticker is None:
            return True
        halted = _halt(self._ticker, self._stop_tick)
        self._ticker = None
        return halted

    def advance(self, done: int) -> None:
        """Step the bar to `done` and redraw it, once past the initial delay."""
        if not self._on:
            return
        assert self._bar is not None
        with self._lock:
            # A batch that finishes within `delay` never draws: remember the
            # position and stay silent, as the spinner does for a quick batch.
            if (time.monotonic() - self._start) < self._delay:
                self._bar.pos = done
                return
            self._bar.make_step(done - self._bar.pos)
            self._draw()

    def echo(self, message: str) -> None:
        """Print `message` as a persistent line above the bar, then redraw it."""
        stream = self._resolve_stream()
        with self._lock:
            if self._drawn:
                stream.write(f"\r{CLEAR_LINE}")  # Erase the bar line.
            stream.write(f"{message}\n")  # Persistent line above.
            if self._drawn:
                self._draw()  # Redraw the bar below.
            stream.flush()

    def finish(self, ok: bool, summary: str) -> None:
        """Replace the bar with a kept `✓`/`✘` ``summary`` line, elapsed included."""
        self._close((ok, summary))

    def stop(self) -> None:
        """Erase the bar and restore the cursor with no kept line. Idempotent.

        The teardown path for an abnormal exit (an exception inside the trail's
        `with` block, where {meth}`finish` never ran).
        """
        self._close(None)

    def _close(self, outcome: tuple[bool, str] | None) -> None:
        """Tear the bar down, leaving the `outcome` finisher in its place.

        Runs once: a later call returns at once. The first call either erased the
        bar, or left the ticker behind, blocked in a write with the draw lock
        held, which a second teardown would wait on until the stream drains.

        :param outcome: whether the batch succeeded and its summary, or `None`
            to erase the bar and keep no line.
        """
        if self._finished:
            return
        self._finished = True
        _deregister_line(self)
        if not self._stop_ticker():
            # See spinner._STOP_GRACE: the stream does not drain, so skip the
            # clean-up.
            return
        with self._lock:
            if not self._drawn:
                return
            stream = self._resolve_stream()
            kept = ""
            if outcome is not None:
                ok, summary = outcome
                clock = _timer_suffix(self._timer, time.monotonic() - self._start)
                line = f"{trail_line(ok, summary)}{clock}"
                kept = f"{_plain_unless(line, _color_enabled(stream))}\n"
            # Erase the bar, keep the finisher in its place, and show the cursor
            # Click hid through `BEFORE_BAR`.
            stream.write(f"\r{CLEAR_LINE}{kept}{SHOW_CURSOR}")
            stream.flush()
            self._drawn = False


class OperationTrail:
    """A `✓`/`✘` progress trail and finisher for a batch of operations.

    Where {class}`~click_extra.spinner.Spinner` narrates *one* long-running
    call, `OperationTrail` reports a *batch* of them: each completed operation
    leaves a persistent {func}`~click_extra.trail.trail_line` on screen, a
    running `done/total` tally keeps the batch's pulse visible, and
    {meth}`finish` closes with a persistent summary line. The natural
    reporting companion of the concurrency primitives
    {func}`~click_extra.jobs.run_jobs` and {func}`~click_extra.jobs.run_lanes`,
    rendered one of three ways:

    - **sequential** (`jobs <= 1`): echo each outcome as it lands, with no
      aggregate indicator (each operation is free to keep its own per-call
      {class}`~click_extra.spinner.Spinner`). {meth}`finish` appends the
      elapsed time.
    - **concurrent** (`jobs > 1`): drive one aggregate
      {class}`~click_extra.spinner.Spinner` (per-call spinners would collide on
      the shared stream), buffering outcomes until it first draws, then
      streaming the rest live above it.
      Pick the animation from the
      {data}`~click_extra.spinner_presets.SPINNERS` catalog with `spinner=`.
    - **progress bar** (`progress_bar=True`): drive one aggregate *determinate*
      bar carrying the `{done}/{total}` tally, with outcomes streaming above
      it. Serves sequential and concurrent batches alike, and needs a known
      `total`.

    The aggregate indicators redraw in place, which a pipe or a CI log cannot
    do, so by default they draw only on an interactive terminal, and `live`
    changes where they draw. The `✓`/`✘` lines and the finisher only append, so
    they print on any stream, in plain text where color is off. Where no
    indicator draws, every rendering echoes each outcome as it lands, as the
    sequential one does. `visible=False` silences all of it. The running `✓`
    tally is kept as outcomes land ({attr}`ok_count`), so a caller computes no
    counts of its own.

    Thread-safe: {meth}`mark` may be called from worker threads. Use it as a
    context manager whenever it may run concurrently, to bound the aggregate
    spinner's life; a purely sequential caller may construct it bare.

    ```{code-block} python

    from click_extra.jobs import run_jobs
    from click_extra.trail import OperationTrail

    with OperationTrail(label="Fetching", unit="feeds", total=len(feeds),
                        jobs=jobs) as trail:
        def fetch(feed):
            trail.mark(*pull(feed))  # pull() returns (ok, message).

        list(run_jobs(fetch, feeds, jobs=jobs))
        trail.finish(
            trail.ok_count == len(feeds),
            f"Fetched {trail.ok_count}/{len(feeds)} feeds",
        )
    ```
    """

    def __init__(
        self,
        *,
        label: str = "",
        unit: str = "",
        total: int = 0,
        jobs: int = 1,
        spinner: SpinnerPreset | None = None,
        progress_bar: bool = False,
        timer: bool | Callable[[float], str] | None = None,
        clock: Literal["elapsed", "eta"] = "elapsed",
        visible: bool = True,
        live: TWhen = AUTO,
        echo_sequential: bool = True,
        delay: float = 0.0,
        stream: IO[str] | None = None,
    ) -> None:
        """Configure (but do not start) the trail.

        :param label: present-tense verb for the running aggregate indicator
            (`"Fetching"`), composed into its ``{label} {done}/{total} {unit}``
            tally.
        :param unit: the noun counted in the tally (`"files"`, `"feeds"`).
        :param total: how many outcomes are expected, for the `done/total`
            count.
        :param jobs: the batch's worker count; `> 1` selects the concurrent
            rendering (one aggregate spinner), `<= 1` the sequential one
            (plain echoed lines).
        :param spinner: a {class}`~click_extra.spinner_presets.SpinnerPreset`
            from the {data}`~click_extra.spinner_presets.SPINNERS` catalog
            (`spinner=SPINNERS["moon"]`) for the concurrent aggregate spinner.
            Ignored by the sequential and progress-bar renderings, and mutually
            exclusive with `progress_bar`.
        :param progress_bar: render the aggregate indicator as a determinate
            {func}`click.progressbar` instead of a spinner, for a sequential or
            concurrent batch alike. Requires a positive `total` (a bar needs a
            length) and is mutually exclusive with `spinner`.
        :param timer: append each operation's and the batch's elapsed time to
            the trail lines and the finisher. `None` (the default) follows the
            CLI's `--time` / `--no-time` flag; `True` forces timing on with
            {func}`~click_extra.humanize.format_duration`'s compact clock, a
            callable `(seconds: float) -> str` forces it on with a custom
            format, and `False` forces it off. Per-operation times come from a
            `seconds` argument to {meth}`mark`, filled in automatically by an
            {meth}`operation` handle.
        :param clock: whether a running aggregate indicator shows *elapsed* time
            (`"elapsed"`, the default: a stopwatch counting up, visible from the
            start) or *remaining* time (`"eta"`: an estimate from the batch's
            rate, appearing only once an outcome lets it be computed). Both the
            progress bar and the concurrent spinner honor `"eta"` (the spinner
            reuses Click's progress-bar estimate, since the trail knows its
            `total`). Per-operation and finisher times are always elapsed.
        :param visible: whether the trail shows anything. `False` silences the
            lines, the finisher and the aggregate indicator, while
            {attr}`ok_count` keeps counting.
        :param live: where the aggregate indicator may draw: `"auto"` (the
            default) on an interactive terminal only, unless `--no-progress`
            turns it off, `"always"` on any stream, `"never"` nowhere. Where it
            does not draw, each outcome line prints as it lands.
        :param echo_sequential: whether the batch echoes its outcome lines and
            finisher as plain lines at all: in a sequential batch, in a batch
            whose aggregate indicator cannot draw on the stream, and in one that
            finishes before its indicator first draws. Turn it off when the
            batch has another output that is the real product (a result table)
            and the trail would be noise. An indicator that did draw is
            unaffected.
        :param delay: seconds before the aggregate indicator first draws: a
            fast batch then completes without ever flashing one, its lines
            echoed plainly at {meth}`finish` instead (see `echo_sequential`).
        :param stream: where to render; defaults to {data}`sys.stderr` so the
            trail never mixes into `stdout` data.
        :raises ValueError: if `progress_bar` is set without a positive
            `total`, or together with `spinner`, if `clock` is neither
            `"elapsed"` nor `"eta"`, or if `live` is not one of
            {data}`~click_extra.color.WHEN`.
        """
        if progress_bar and total <= 0:
            raise ValueError("progress_bar=True requires a positive total.")
        if progress_bar and spinner is not None:
            raise ValueError("progress_bar= and spinner= are mutually exclusive.")
        if clock not in ("elapsed", "eta"):
            raise ValueError('clock must be "elapsed" or "eta".')
        _check_live(live)
        self.label = label
        self.unit = unit
        self.total = total
        self.concurrent = jobs > 1
        self.progress_bar = progress_bar
        # None auto-detects the --time flag; a bool or callable forces it.
        self.timer = _resolve_timer(timer)
        self.clock = clock
        self.spinner_preset = spinner
        self.visible = visible
        self.live = live
        self.stream = stream
        self._delay = delay
        self._lock = threading.Lock()
        self._done = 0
        self._ok = 0
        self._finished = False
        self._start = time.monotonic()
        self._indicator: _AggregateIndicator | None = None
        self._buffer: list[str] = []
        # Whether outcome lines may reach the stream as plain text: the trail is
        # the batch's output and is visible. A plain line needs no cursor
        # control, so this holds for a pipe or a file as for a terminal.
        self._echo_plain = echo_sequential and visible
        # The mode the aggregate indicator gets: a hidden trail draws nothing,
        # whatever `live` says.
        self._indicator_live: TWhen = live if visible else "never"
        # An aggregate indicator (a progress bar, or a spinner for a concurrent
        # batch) owns the live line only on a stream it can draw on, under the
        # same resolution the indicator applies. There, lines wait for its first
        # frame, and finish() echoes them for a batch it never drew. Elsewhere
        # no indicator ever draws, so lines echo as they are marked.
        self._indicator_draws = (self.concurrent or progress_bar) and _can_draw(
            self._indicator_live, _stream_or_stderr(stream)
        )
        self._echo = self._echo_plain and not self._indicator_draws

    def __enter__(self) -> Self:
        if self.progress_bar:
            self._indicator = _BarIndicator(
                label=self.label,
                unit=self.unit,
                total=self.total,
                delay=self._delay,
                live=self._indicator_live,
                stream=self.stream,
                timer=self.timer,
                clock=self.clock,
            )
        elif self.concurrent:
            self._indicator = _SpinnerIndicator(
                label=self.label,
                unit=self.unit,
                total=self.total,
                delay=self._delay,
                live=self._indicator_live,
                stream=self.stream,
                spinner=self.spinner_preset,
                timer=self.timer,
                clock=self.clock,
            )
        if self._indicator is not None:
            self._indicator.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if (
            exc_type is not None
            and issubclass(exc_type, KeyboardInterrupt)
            and not self._finished
        ):
            # An interrupted batch still closes with a finisher, so the record
            # of what completed ends on a line saying it stopped short.
            self.finish(False, self._interrupted_summary())
        indicator = self._indicator
        if indicator is None:
            return
        # Leaving without a finisher keeps every outcome line, as finish() does.
        # Lines the indicator drew are already on screen, past any still buffered
        # behind a first frame that fell due after the last mark. Lines of a batch
        # it never drew echo plainly, on the same terms as in finish().
        with self._lock:
            if indicator.shown:
                self._flush()
            replay = self._buffer if self._echo_plain else []
            self._buffer = []
        indicator.__exit__(exc_type, exc_val, exc_tb)
        self._indicator = None
        for text in replay:
            self._echo_line(text)

    @property
    def ok_count(self) -> int:
        """How many marked outcomes have succeeded so far."""
        return self._ok

    def _interrupted_summary(self) -> str:
        """The finisher of a batch a Ctrl+C stopped: how far it got."""
        count = f"{self._done}/{self.total}" if self.total else str(self._done)
        summary = _("Interrupted after {count}").format(count=count)
        return f"{summary} {self.unit}" if self.unit else summary

    def _render_line(self, ok: bool, message: str) -> str:
        """Format one `✓`/`✘` line for the trail's stream, plain when color is off.

        The glyph is painted unconditionally by {func}`trail_line`, and a line
        flushed above a drawn indicator reaches the stream through a raw write,
        not through {func}`click.echo`'s strip. So the strip happens here, and
        takes any escape embedded in `message` along with the glyph's.
        """
        stream = _stream_or_stderr(self.stream)
        return _plain_unless(trail_line(ok, message), _color_enabled(stream))

    def _echo_line(self, message: str) -> None:
        """Print one rendered line to the trail's stream."""
        if self.stream is not None:
            click.echo(message, file=self.stream)
        else:
            click.echo(message, err=True)

    def mark(self, ok: bool, message: str, seconds: float | None = None) -> None:
        """Record one `✓`/`✘` outcome: tally it and render its trail line.

        :param seconds: the operation's own elapsed time. When `timer` is on it
            is formatted and appended to `message` as ` (2.3s)`. An
            {meth}`operation` handle fills this in from when it was created;
            pass it yourself when you already hold a duration.
        """
        if seconds is not None:
            message += _timer_suffix(self.timer, seconds)
        with self._lock:
            self._done += 1
            if ok:
                self._ok += 1
            if self._finished:
                # An outcome landing after the finisher, from a task the batch
                # waited on after a Ctrl+C: print it plainly, below the finisher,
                # so the record of what completed stays whole.
                if self._echo_plain:
                    self._echo_line(self._render_line(ok, message))
            elif self._echo:
                self._echo_line(self._render_line(ok, message))
            elif self._indicator is not None:
                self._buffer.append(self._render_line(ok, message))
                self._indicator.advance(self._done)
                self._flush()

    def _flush(self) -> None:
        """Print the buffered lines above the indicator, once it draws.

        The caller holds the trail's lock. Before the first frame, writing would
        leak into a stream the delayed (or disabled) indicator may never touch.
        """
        if self._indicator is None or not self._indicator.shown:
            return
        for text in self._buffer:
            self._indicator.echo(text)
        self._buffer.clear()

    def finish(self, ok: bool, summary: str) -> None:
        """Render the persistent `✓`/`✘` ``{summary}`` finisher.

        With an aggregate indicator that drew, it becomes the indicator's kept
        line (a spinner's {meth}`~click_extra.spinner.Spinner.ok` /
        {meth}`~click_extra.spinner.Spinner.fail` line, or the bar's replacement
        line); otherwise, a plain echoed line. The batch's elapsed time since
        construction is appended when `timer` is on.

        A batch finishing inside `delay` never draws its indicator, so none of
        its buffered lines reached the stream. When the trail is the batch's
        output (`echo_sequential` and `visible`), they are echoed plainly along
        with the finisher, the way a sequential batch prints them: how fast a
        batch ran must not decide whether its record exists.
        """
        self._finished = True
        indicator = self._indicator
        if indicator is not None:
            with self._lock:
                drew = indicator.shown
                if drew:
                    self._flush()
                replay, self._buffer = self._buffer, []
            if drew or not self._echo_plain:
                indicator.finish(ok, summary)
                return
            # Tear the indicator down first, so a first frame falling due right
            # now cannot draw over the replayed lines.
            indicator.stop()
            for text in replay:
                self._echo_line(text)
        elif not self._echo:
            return
        summary += _timer_suffix(self.timer, time.monotonic() - self._start)
        self._echo_line(self._render_line(ok, summary))

    def operation(self) -> _Operation:
        """Start a timed operation, returning a handle to record its outcome.

        The handle captures the current time; call {meth}`_Operation.mark` when
        the work finishes to record its `✓`/`✘` outcome with the elapsed time
        appended (when `timer` is on). This is how a batch reports
        per-operation timings under concurrency, where the trail itself never
        sees when an operation began:

        ```{code-block} python

        def fetch(feed):
            op = trail.operation()
            ok, message = pull(feed)
            op.mark(ok, message)
        ```
        """
        return _Operation(self)


class _Operation:
    """A single timed operation issued by {meth}`OperationTrail.operation`.

    Captures its start time on creation; {meth}`mark` reports the outcome to the
    parent trail with the elapsed time, so per-operation timings work under
    concurrency where the trail cannot know when each operation began.
    """

    def __init__(self, trail: OperationTrail) -> None:
        self._trail = trail
        self._start = time.monotonic()

    def mark(self, ok: bool, message: str) -> None:
        """Record this operation's `✓`/`✘` outcome, timed from its start."""
        self._trail.mark(ok, message, seconds=time.monotonic() - self._start)
