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

import pytest

from click_extra import SPINNERS, Spinner, Style
from click_extra.recording import TerminalScreen

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
