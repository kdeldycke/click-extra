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

"""Tests for `click_extra.capture.terminal`, which rebuilds a terminal's screen."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time

import click
import pytest
from extra_platforms.pytest import skip_windows

from click_extra import SPINNERS, Spinner, Style
from click_extra.ansi import RESET, strip_ansi
from click_extra.capture.terminal import PENDING_LIMIT, TerminalScreen
from click_extra.spinner import CLEAR_LINE, HIDE_CURSOR, SHOW_CURSOR

from .conftest import TTYStringIO

GREEN = "\x1b[32m"


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


def replayed(stream: str, columns: int = 10, rows: int = 4) -> str:
    """The text a terminal of that size shows for a stream, unstyled.

    The stream is read the way a pseudo-terminal hands it back: a newline moves
    the cursor straight down, the driver having already added any return.
    """
    screen = TerminalScreen(columns, rows, onlcr=False)
    screen.feed(stream)
    return strip_ansi(screen.display)


@pytest.mark.parametrize(
    ("stream", "expected"),
    (
        pytest.param("plain", "plain", id="text"),
        pytest.param("one\ntwo", "one\ntwo", id="newline-starts-a-row"),
        pytest.param("apricot\rfig", "figicot", id="return-overwrites-the-start"),
        pytest.param("apricot\rfig\rplum", "plumcot", id="two-returns"),
        pytest.param(f"apricot{CLEAR_LINE}", "apricot", id="erase-past-the-cursor"),
        pytest.param(f"apricot\r{CLEAR_LINE}", "", id="erase-from-the-start"),
        pytest.param(f"{HIDE_CURSOR}fig{SHOW_CURSOR}", "fig", id="cursor-visibility"),
        pytest.param("\x1b[2;5Hfig", "\n    fig", id="cursor-position"),
        pytest.param("\x1b[2 qfig", "fig", id="an-intermediate-byte-is-dropped"),
        pytest.param("\x1b[200~fig\x1b[201~", "fig", id="a-symbol-final-byte-ends-it"),
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
    """The screen shows what a terminal would, for a stream written in-process."""
    screen = TerminalScreen()
    screen.feed(stream)
    assert screen.display == expected


def test_screen_keeps_a_color_set_between_a_return_and_its_text():
    """A color opened after the cursor comes back wraps the text written over.

    An animation writes the return, then its color, then the text, then an erase
    clearing what is left of the previous frame. The frame must come back in
    its color, not in the terminal's default ink.
    """
    screen = TerminalScreen()
    screen.feed(f"apricot\r{GREEN}fig{RESET}{CLEAR_LINE}")
    assert screen.display == f"{GREEN}fig{RESET}"


def test_screen_feeds_the_same_whether_split_or_whole():
    """A stream arriving in pieces lands where the whole of it would.

    A recorder reads whatever the terminal hands it, which is not aligned on
    anything: a frame routinely arrives across two reads.
    """
    stream = (
        f"apricot\r{GREEN}fig{RESET}{CLEAR_LINE}\rplum{CLEAR_LINE}"
        "\x1b]0;orchard\x07\x1b[2;3H\x1b(0lqk\x1b(B\x1bP1$r0m\x1b\\"
    )
    whole = TerminalScreen(20, 4)
    whole.feed(stream)

    piecewise = TerminalScreen(20, 4)
    for index in range(len(stream)):
        piecewise.feed(stream[index : index + 1])
    assert piecewise.display == whole.display
    assert strip_ansi(whole.display) == "plum\n  ┌─┐"


def test_screen_counts_a_wide_glyph_by_its_cells():
    """A wide glyph covers the two cells it is drawn with.

    The count is what says where the cursor stands after it, which is what an
    erase-in-line acts from.
    """
    screen = TerminalScreen()
    screen.feed("🌑")
    screen.feed(CLEAR_LINE)
    # Past the glyph, so the erase leaves it alone.
    assert screen.display == "🌑"
    assert screen.cursor == (0, 2)


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
        live="always",
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


@pytest.mark.parametrize(
    ("stream", "expected"),
    (
        pytest.param("\x1b[3;4Hfig", "\n\n   fig", id="cursor-position"),
        pytest.param("\x1b[3;4H\x1b[Hfig", "fig", id="cursor-home"),
        pytest.param("fig\x1b[2;7Hplum", "fig\n      plum", id="second-position"),
        pytest.param("fig\x1b[3Gx", "fix", id="column-absolute"),
        pytest.param("fig\x1b[3dx", "fig\n\n   x", id="row-absolute"),
        pytest.param("\x1b[3Bx\x1b[2Ay", "\n y\n\nx", id="cursor-down-and-up"),
        pytest.param("\x1b[4Cx\x1b[3Dy", "  y x", id="cursor-right-and-left"),
        pytest.param("ab\ncd", "ab\n  cd", id="newline-moves-straight-down"),
        pytest.param("apricotplum", "apricotplu\nm", id="autowrap"),
        pytest.param("0123456789\rX", "X123456789", id="return-cancels-the-wrap"),
        pytest.param("123456789🍎", "123456789\n🍎", id="wide-glyph-wraps-whole"),
        pytest.param("\x1b[?7lapricotplum", "apricotplm", id="no-autowrap"),
        pytest.param("fig\b\bX", "fXg", id="backspace"),
        pytest.param("a\tb", "a       b", id="tab"),
        pytest.param("\x1b[3gx\tb", "x        b", id="tab-stops-cleared"),
        pytest.param("apricot\x1b[4G\x1b[K", "apr", id="erase-to-end"),
        pytest.param("apricot\x1b[4G\x1b[1K", "    cot", id="erase-to-start"),
        pytest.param("apricot\x1b[2K", "", id="erase-row"),
        pytest.param("apricot\x1b[2G\x1b[3X", "a   cot", id="erase-cells"),
        pytest.param("apricot\x1b[2G\x1b[2@", "a  pricot", id="insert-cells"),
        pytest.param("apricot\x1b[2G\x1b[2P", "aicot", id="delete-cells"),
        pytest.param("\x1b[4hapricot\x1b[2Gxy", "axypricot", id="insert-mode"),
        pytest.param("a\x1b[3b", "aaaa", id="repeat"),
        pytest.param("one\r\ntwo\x1b[H\x1b[L", "\none\ntwo", id="insert-row"),
        pytest.param("one\r\ntwo\x1b[H\x1b[M", "two", id="delete-row"),
        pytest.param("one\r\ntwo\x1b[2J", "\n", id="erase-screen"),
        pytest.param("one\r\ntwo\x1b[H\x1b[J", "", id="erase-below"),
        pytest.param("one\r\ntwo\x1b[2;2H\x1b[1J", "\n  o", id="erase-above"),
        pytest.param("\x1b(0lqk\r\nx x\r\nmqj\x1b(B", "┌─┐\n│ │\n└─┘", id="lines"),
        pytest.param("\x1b)0\x0eq\x0fq", "─q", id="shift-out"),
        pytest.param("one\x1b7\r\ntwo\x1b8!", "one!\ntwo", id="save-restore"),
        pytest.param("one\x1b[s\r\ntwo\x1b[u!", "one!\ntwo", id="save-restore-csi"),
        pytest.param("\x1bMfig", "fig", id="reverse-index-at-the-top"),
        pytest.param("\x1b]0;orchard\x07fig", "fig", id="title-dropped"),
        pytest.param(
            "\x1b]8;;https://example.com\x1b\\fig\x1b]8;;\x1b\\",
            "fig",
            id="hyperlink-dropped",
        ),
        pytest.param("\x1bP1$r0m\x1b\\fig", "fig", id="device-string-dropped"),
        pytest.param("\x1b_Ga=q\x1b\\fig", "fig", id="application-string-dropped"),
        pytest.param("\x1b[>4;1mfig", "fig", id="private-modifier-dropped"),
        pytest.param("\x1b[?1h\x1b=fig\x1b[?1l\x1b>", "fig", id="keypad-dropped"),
        pytest.param("\x1b[6nfig\x1b[c", "fig", id="queries-dropped"),
        pytest.param("\x1b\x07fig", "fig", id="malformed-escape-dropped"),
        pytest.param("\x1b[?2026hfig\x1b[?2026l", "fig", id="synchronized-update"),
    ),
)
def test_screen_replays_a_sized_terminal(stream, expected):
    """A screen of known size follows cursor addressing, wrapping and editing.

    One case per control: what xterm shows for the same bytes on a 10 by 4
    terminal.
    """
    assert replayed(stream) == expected


def test_screen_keeps_the_history_a_full_screen_scrolls_away():
    """Rows leaving the top of the first screen stay in the picture."""
    screen = TerminalScreen(10, 2, onlcr=False)
    screen.feed("one\r\ntwo\r\nthree\r\nfour")
    assert screen.display == "one\ntwo\nthree\nfour"
    assert screen.cursor == (3, 4)


def test_screen_scrolls_only_its_region():
    """A newline on the last row of a scroll region moves that region alone."""
    stream = "top\x1b[4;1Hbottom\x1b[2;3r\x1b[2;1Hone\r\ntwo\r\nthree"
    assert replayed(stream) == "top\ntwo\nthree\nbottom"


@pytest.mark.parametrize(
    ("stream", "expected"),
    (
        pytest.param("\x1b[3;4r\x1b[3;1Ha\r\nb\x1b[1T", "\n\n\na", id="scroll-down"),
        pytest.param("\x1b[3;4r\x1b[3;1Ha\r\nb\x1b[1S", "\n\nb\n", id="scroll-up"),
        pytest.param("\x1b[2;3r\x1b[?6h\x1b[1;1Hx", "\nx", id="origin-mode"),
    ),
)
def test_screen_moves_the_region_it_is_given(stream, expected):
    """Scrolling and origin mode answer to the region, not to the whole screen."""
    assert replayed(stream) == expected


def test_screen_draws_a_full_screen_program_on_the_alternate_screen():
    """A full-screen program covers the first screen, which it leaves as it was."""
    screen = TerminalScreen(10, 4, onlcr=False)
    seen = []
    for stream in (
        "$ bake\r\n",
        "\x1b[?1049h\x1b[H\x1b[2J\x1b[2;3Hoven",
        "\x1b[?1049l",
    ):
        screen.feed(stream)
        seen.append((screen.alternate, screen.display, screen.cursor))
    assert seen == [
        (False, "$ bake\n", (1, 0)),
        # Exactly its height, blank rows included.
        (True, "\n  oven\n\n", (1, 6)),
        # The first screen as it was, cursor included.
        (False, "$ bake\n", (1, 0)),
    ]


def test_screen_erases_in_the_background_in_force():
    """An erase paints the cells it clears, which is how a bar is drawn.

    xterm calls this background color erase, `bce`, and its terminfo entry
    tells `ncurses` to rely on it.
    """
    screen = TerminalScreen(4, 2, onlcr=False)
    screen.feed("\x1b[44m\x1b[2K\x1b[0m")
    assert screen.display == click.style("    ", bg="blue")


def test_screen_blanks_the_half_a_write_leaves_of_a_wide_glyph():
    """Overwriting one cell of a wide glyph leaves a blank in the other."""
    assert replayed("🍎\x1b[2Gx") == " x"
    assert replayed("🍎\x1b[1Gx") == "x"


def test_screen_joins_a_combining_mark_to_its_base():
    """A combining accent arriving in its own read still lands on its letter."""
    screen = TerminalScreen()
    screen.feed("cafe")
    screen.feed("́!")
    assert screen.display == "café!"


def test_screen_reads_a_color_in_both_spellings():
    """A 24-bit color reads the same written with semicolons or with colons."""
    expected = click.style("fig", fg=(255, 128, 0))
    for stream in ("\x1b[38;2;255;128;0mfig", "\x1b[38:2::255:128:0mfig"):
        screen = TerminalScreen()
        screen.feed(stream)
        assert screen.display == expected


def test_screen_reports_the_modes_a_recording_reads():
    """Cursor visibility and synchronized updates are exposed, not drawn."""
    screen = TerminalScreen(10, 4)
    seen = []
    for stream in ("fig", "\x1b[?25l\x1b[?2026h", "\x1b[?25h\x1b[?2026l"):
        screen.feed(stream)
        seen.append((screen.cursor_visible, screen.synchronized, screen.display))
    assert seen == [(True, False, "fig"), (False, True, "fig"), (True, False, "fig")]


def test_screen_resets_to_its_starting_state():
    """A full reset clears the screen and every mode."""
    screen = TerminalScreen(10, 4, onlcr=False)
    screen.feed("\x1b[?1049h\x1b[31mfig\x1b[?25l\x1bc")
    assert not screen.alternate
    assert screen.cursor_visible
    screen.feed("plum")
    assert screen.display == "plum"


def test_screen_skips_a_runaway_string_to_its_terminator():
    """A string longer than the pending limit is skipped, never drawn."""
    screen = TerminalScreen()
    screen.feed("\x1b]0;" + "x" * (PENDING_LIMIT + 1))
    screen.feed("more of it\x1b")
    screen.feed("\\fig")
    assert screen.display == "fig"


def test_screen_skips_a_runaway_string_cut_inside_its_terminator():
    """The read that starts skipping a string can end on its terminator's escape."""
    screen = TerminalScreen()
    screen.feed("\x1b]0;" + "x" * (PENDING_LIMIT + 1) + "\x1b")
    screen.feed("\\fig")
    assert screen.display == "fig"


def test_screen_refuses_a_terminal_holding_no_cell():
    with pytest.raises(ValueError, match="holds nothing"):
        TerminalScreen(0, 4)


INFOCMP = shutil.which("infocmp")
"""The terminfo dumper `ncurses` ships, listing the capabilities of an entry."""

TERMINAL_REPLIES = frozenset(("rv", "u6", "u8", "xr"))
"""Capabilities describing what a terminal answers to a query.

`u6` and `u8` give the format of the cursor position and device attributes
replies, `rv` and `xr` the patterns of the version replies. `ncurses` matches
them against what comes back from the terminal, the way it matches a key
capability against what the keyboard sends: no program writes them.
"""

TERMINFO_PADDING_RE = re.compile(rb"\$<[\d.*/]+>")
"""A delay a terminfo capability asks for, which `tputs` waits out rather than
sending, like the `$<100/>` of xterm's visible bell."""


@skip_windows(reason="Windows ships neither curses nor a terminfo database")
@pytest.mark.skipif(INFOCMP is None, reason="infocmp is not installed")
def test_screen_reads_every_sequence_of_the_recording_terminal():
    """No capability of `xterm-256color` lands on the screen as text.

    The terminal a recording names to its command decides what the command
    writes, so every string capability of that entry is fed to the screen,
    parameters filled in, and followed by one letter: only that letter may show.
    A sequence the screen failed to recognize would leave its bytes behind, the
    way `ESC [ ? 1049 h` would print `[?1049h`.
    """
    # Imported here: Windows lacks the module, and the skip above covers it.
    import curses

    with open(os.devnull, "w", encoding="UTF-8") as null:
        curses.setupterm("xterm-256color", null.fileno())
    listing = subprocess.run(
        (str(INFOCMP), "-1", "-x", "xterm-256color"),
        capture_output=True,
        check=True,
        encoding="UTF-8",
    ).stdout
    names = re.findall(r"^\t([\w.]+)=", listing, re.MULTILINE)
    # Key capabilities describe what the keyboard sends, replies what the
    # terminal answers, and `acsc` maps the line-drawing glyphs: none of them is
    # ever written to a terminal.
    written = [
        name
        for name in names
        if not name.startswith("k") and name != "acsc" and name not in TERMINAL_REPLIES
    ]
    assert len(written) > 50, written

    leaks = {}
    for name in written:
        value = curses.tigetstr(name)
        # A string parameter (`%s`) crashes `tparm` handed numbers: these are
        # the capabilities setting a color or a selection by name.
        if value is None or b"%s" in value or b"%l" in value:
            continue
        if b"%" in value:
            value = curses.tparm(value, 1, 2, 3, 4, 5, 6, 7, 8, 9)
        screen = TerminalScreen(20, 5, onlcr=False)
        screen.feed(TERMINFO_PADDING_RE.sub(b"", value).decode("latin-1") + "X")
        shown = set(strip_ansi(screen.display)) - {"X", " ", "\n"}
        if shown:
            leaks[name] = (value, shown)
    assert not leaks
