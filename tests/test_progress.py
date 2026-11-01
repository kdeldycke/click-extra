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

import logging
import re
import sys

import click
import pytest
from extra_platforms.pytest import skip_windows

import click_extra
from click_extra import command, echo
from click_extra.capture.recording import TerminalScreen, record_command
from click_extra.context import START_TIME
from click_extra.logging import StreamHandler as ExtraStreamHandler
from click_extra.spinner import _active_line

from .conftest import TTYStringIO


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
    """With an `update_min_steps` that does not divide the length, the bar still
    lands on total/total instead of the last multiple (14/20 for a length of 20
    and an `update_min_steps` of 7)."""
    stream = TTYStringIO()
    with click_extra.progressbar(
        range(20), show_pos=True, update_min_steps=7, file=stream
    ) as bar:
        for _ in bar:
            pass
    output = click.unstyle(stream.getvalue())
    assert "20/20" in output


def test_progressbar_prints_a_log_record_above_itself(monkeypatch):
    """A record logged while a bar draws lands on a line of its own, above it.

    Click draws a bar with a carriage return and no line feed until it finishes,
    so a record written in between continued the bar's row, after its position.
    """
    terminal = TTYStringIO()
    monkeypatch.setattr(sys, "stderr", terminal)
    handler = ExtraStreamHandler()
    handler.stream = sys.stderr
    logger = logging.getLogger("click_extra.test.progressbar")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        with click_extra.progressbar(range(3), label="Sorting plums") as bar:
            # Compared by identity: the registry types its entries as live lines.
            assert id(_active_line(terminal)) == id(bar)
            for _ in bar:
                logger.warning("Opening the fruit basket")
    finally:
        logger.removeHandler(handler)
    assert _active_line(terminal) is None

    screen = TerminalScreen()
    screen.feed(terminal.getvalue())
    rows = [click.unstyle(row) for row in screen.rows]
    records = [row for row in rows if "Opening the fruit basket" in row]
    assert len(records) == 3
    assert not [row for row in records if "Sorting plums" in row], rows
    # The bar keeps drawing below the records, and ends there.
    assert [row for row in rows if row.strip()][-1].startswith("Sorting plums")


LOGGING_UNDER_A_BAR_SCRIPT = """
import logging
import time

from click_extra import command, progressbar


@command
def sort_plums():
    with progressbar(range(3), label="Sorting plums") as bar:
        for _ in bar:
            logging.warning("Opening the fruit basket")
            time.sleep(0.05)


sort_plums()
"""
"""A CLI logging from inside an open progress bar."""


@skip_windows(reason="A pseudo-terminal needs termios, which Windows lacks")
def test_progressbar_logging_on_a_pseudo_terminal():
    """On a real terminal, each record a CLI logs under a bar gets its own row."""
    frames = record_command(
        (sys.executable, "-c", LOGGING_UNDER_A_BAR_SCRIPT), columns=80, rows=12
    )
    rows = [click.unstyle(row).rstrip() for row in frames[-1].text.splitlines()]
    records = [row for row in rows if "Opening the fruit basket" in row]
    assert records == ["warning: Opening the fruit basket"] * 3, rows
    assert [row for row in rows if row][-1].startswith("Sorting plums"), rows


def test_progressbar_draws_on_stderr_by_default():
    """The bar draws where log records and the other live lines go."""
    assert click_extra.progressbar([1, 2, 3]).file is sys.stderr
    assert click_extra.progressbar([1, 2, 3], file=sys.stdout).file is sys.stdout


def _drawn_positions(stream: TTYStringIO) -> list[str]:
    """The `done/total` tallies a bar drew on `stream`, in order."""
    plain = click.unstyle(stream.getvalue())
    return re.findall(r"(\d+/\d+)", plain)


def test_progressbar_draws_fast_items_once_per_interval():
    """Items faster than the interval draw nothing between the first and the last
    position, however many there are."""
    stream = TTYStringIO()
    bar = click_extra.progressbar(range(1000), show_pos=True, file=stream)
    bar.clock = lambda: 0.0  # type: ignore[attr-defined]
    with bar:
        for index, _ in enumerate(bar, 1):
            # The position moves on every step, drawn or not.
            assert bar.pos == index - 1
    assert _drawn_positions(stream) == ["0/1000", "1000/1000"]


def test_progressbar_draws_every_slow_item():
    """Items slower than the interval each draw their position, so a bar over slow
    items never looks frozen."""
    stream = TTYStringIO()
    now = [0.0]

    def clock() -> float:
        now[0] += 1.0
        return now[0]

    bar = click_extra.progressbar(range(300), show_pos=True, file=stream)
    bar.clock = clock  # type: ignore[attr-defined]
    with bar:
        for _ in bar:
            pass
    assert _drawn_positions(stream) == [f"{done}/300" for done in range(301)]


def test_progressbar_keeps_an_explicit_update_min_steps():
    """A caller stating `update_min_steps` keeps Click's gate on a count of items."""
    assert click_extra.progressbar(range(10)).time_gated is True  # type: ignore[attr-defined]
    bar = click_extra.progressbar(range(10), update_min_steps=4)
    assert bar.time_gated is False  # type: ignore[attr-defined]
    assert bar.update_min_steps == 4


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
