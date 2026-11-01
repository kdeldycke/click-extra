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
"""A determinate progress bar that honors `--progress` and `--time`.

{func}`progressbar` is a drop-in for {func}`click.progressbar`, the determinate
counterpart of the indeterminate {class}`~click_extra.spinner.Spinner`. Its bar
joins the spinner's registry of live lines while it draws, so a log record
prints on a line of its own above it.
"""

from __future__ import annotations

import functools
import math
import sys
import time

import click

from .spinner import (
    CLEAR_LINE,
    DEFAULT_INTERVAL,
    _deregister_line,
    _progress_enabled,
    _register_line,
    _time_flag_active,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from typing import IO, Any, Self, TypeVar

    from click._termui_impl import ProgressBar

    V = TypeVar("V")


@functools.cache
def _live_progressbar_class() -> type[ProgressBar[Any]]:
    """The Click progress bar class that other output can print above.

    Its bars register as a live line while they draw, so
    {class}`~click_extra.logging.StreamHandler` routes each log record through
    their `echo`: the bar line is erased, the record printed, and the bar drawn
    again below it. Left to itself, a record lands on the bar's row, right after
    its position, because Click draws the bar with a carriage return and no line
    feed until it finishes.

    Its bars also draw at most once every {data}`DEFAULT_INTERVAL`, the cadence
    of a spinner's frames, unless the caller passed `update_min_steps`. Click
    redraws a bar on every step otherwise, which is once per item: 20,000 writes
    for a bar over 20,000 items, and as many frames for a recording of it. A gate
    on time bounds the writes whatever the items do, where a gate on a count of
    items would freeze a bar over slow items for as long as each count takes to
    fill. The position itself moves on every step, so a redraw forced in
    between, like the one after a log record, shows where the bar really is.

    ```{note}
    {func}`progressbar` builds the bar through {func}`click.progressbar` and then
    switches its class to this one. `click.progressbar` passes defaults of its own
    (a bracketed template, a dash for the empty part, a width of 36) that
    {class}`~click._termui_impl.ProgressBar` does not have, so building this
    class directly would draw a different bar.
    ```
    """
    # Deferred import: keeps click._termui_impl off the startup path of every CLI.
    from click._termui_impl import ProgressBar as ClickProgressBar

    class LiveProgressBar(ClickProgressBar):
        time_gated = False
        """Whether redraws wait {data}`DEFAULT_INTERVAL` from one to the next."""

        clock: Callable[[], float] = staticmethod(time.monotonic)
        """What the time gate reads the time off."""

        _last_render = -math.inf

        def _resolve_stream(self) -> IO[str]:
            return self.file

        def render_progress(self) -> None:
            """Draw the bar, unless it was drawn less than an interval ago.

            Click's iterator redraws before every item on its own, outside
            {meth}`update`, so the gate sits here, where every redraw passes. The
            first and the last positions always draw. A time-gated bar keeps
            Click's default `update_min_steps` of one, so {meth}`update` moves
            its position on every step.
            """
            if self.time_gated and not self.finished:
                now = self.clock()
                if now - self._last_render < DEFAULT_INTERVAL:
                    return
                self._last_render = now
            super().render_progress()

        def _draws(self) -> bool:
            """Whether this bar writes to its stream, rather than staying silent."""
            return not self.hidden and self._is_atty

        def __enter__(self) -> Self:
            if self._draws():
                _register_line(self)
            super().__enter__()
            return self

        def render_finish(self) -> None:
            _deregister_line(self)
            super().render_finish()

        def echo(self, message: str) -> None:
            """Print `message` as a persistent line above the bar, then redraw it."""
            stream = self.file
            drawn = self.entered and self._draws()
            if drawn:
                stream.write(f"\r{CLEAR_LINE}")
            stream.write(f"{message}\n")
            if drawn:
                # Click skips a redraw whose line did not change, which is the
                # case here: the bar moved down a row, not forward. Drawn past
                # the time gate, which would leave the bar erased until the next
                # interval.
                self._last_line = None
                ClickProgressBar.render_progress(self)
            stream.flush()

    return LiveProgressBar


def progressbar(
    iterable: Iterable[V] | None = None,
    length: int | None = None,
    label: str | None = None,
    hidden: bool | None = None,
    show_eta: bool | None = None,
    **kwargs: Any,
) -> ProgressBar[V]:
    """Drop-in for {func}`click.progressbar` honoring `--progress` and `--time`.

    Click's own progress bar is *determinate*, the counterpart to the
    indeterminate {class}`~click_extra.spinner.Spinner`. This thin wrapper gates
    its visibility on the same {data}`~click_extra.context.PROGRESS` flag the
    spinner uses, so a single `--no-progress` (or `--accessible`, which lowers
    the `progress` default) silences both, and gates its estimated-time display
    on `--time`.

    :param hidden: tri-state. Left at its default `None`, the bar follows the
        resolved `--progress` flag: hidden when the user (or `--accessible`)
        turned progress off, shown otherwise. An explicit `True` or `False`
        forces the bar regardless, mirroring how an explicit `color=` argument
        overrides `ctx.color` on {func}`click.echo`. With no active context (the
        bar used outside a Click command) it defaults to shown.
    :param show_eta: tri-state, like `hidden`. Left at its default `None`, the
        estimated-time-remaining display follows the `--time` / `--no-time`
        flag: shown under `--time`, hidden otherwise (its default, or outside a
        command). An explicit `True` or `False` forces it, keeping a bare bar's
        timing in step with an {class}`~click_extra.trail.OperationTrail`'s
        `timer`. Click's own default is `True`.

    Unlike {func}`click.progressbar`, the bar draws on {data}`sys.stderr` unless
    `file` says otherwise, like {class}`~click_extra.spinner.Spinner` and
    {class}`~click_extra.trail.OperationTrail`. That keeps stdout free for the
    data a command prints, and puts the bar on the stream log records go to. A
    record logged while the bar draws then prints on a line of its own above the
    bar, which draws again below it. The bar is also redrawn at most once every
    {data}`~click_extra.spinner.DEFAULT_INTERVAL`, the cadence of a spinner's
    frames, unless `update_min_steps` says otherwise. Its position still moves on
    every step.

    ```{note}
    The `--progress` flag gates visibility and `--time` the ETA. Color is
    already handled upstream: Click renders the bar through {func}`click.echo`,
    whose `color=None` resolves against `ctx.color`, so `--no-color` /
    `NO_COLOR` strip the bar's ANSI without any work from this wrapper.
    ```
    """
    if hidden is None:
        hidden = not _progress_enabled()
    if show_eta is None:
        # The ETA follows --time / --no-time, like a trail's timer, so a bare
        # bar and a trail agree on when to show timing.
        show_eta = _time_flag_active()
    if kwargs.get("file") is None:
        kwargs["file"] = sys.stderr
    bar = click.progressbar(
        iterable,
        length=length,
        label=label,
        hidden=hidden,
        show_eta=show_eta,
        **kwargs,
    )
    bar.__class__ = _live_progressbar_class()
    # A caller stating `update_min_steps` keeps Click's own gate on a count.
    bar.time_gated = "update_min_steps" not in kwargs  # type: ignore[attr-defined]
    return bar
