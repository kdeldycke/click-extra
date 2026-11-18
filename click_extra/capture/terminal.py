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
"""Rebuild the screen a terminal shows from the stream a command writes at it.

A command prints text and control sequences, never a picture. The terminal makes
the picture: a carriage return sends the cursor back over its row, a cursor
position sends it anywhere on the screen, an erase blanks cells in the
background color in force, and a full-screen program draws on a second screen
that hides the first. {class}`TerminalScreen` is that terminal, held in memory,
so a recording can read every screen off it.

```{note}
The vocabulary is xterm's, as `ncurses` drives it for `TERM=xterm-256color`: the
terminal {data}`~click_extra.capture.recording.RECORDING_TERM` names to every
recorded command. A spinner or a progress bar uses a handful of it: a return, an
erase, a newline. A full-screen program uses much more: cursor addressing,
scroll regions, insertion and deletion of cells and rows, the line-drawing
character set and the alternate screen. Sequences that change nothing on screen
(keypad and mouse modes, window titles, hyperlinks, the queries a program sends
its terminal) are read whole and dropped, so their bytes never reach a cell.
```

```{todo}
Answer the cursor position report (`CSI 6 n`) and the device attributes query
(`CSI c`) once a recorded program blocks on either. No reply reaches the program
today, so one waiting for it waits until it gives up.
```
"""

from __future__ import annotations

import re
from typing import Any, Final

import click

from ..ansi import apply_sgr_codes
from ..layout import cell_width

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import TypeAlias

    _Style: TypeAlias = tuple[tuple[str, Any], ...]
    _Cell: TypeAlias = tuple[str | None, _Style]

DEC_SPECIAL_GRAPHICS: Final[dict[str, str]] = {
    "_": " ",
    "`": "◆",
    "a": "▒",
    "b": "␉",
    "c": "␌",
    "d": "␍",
    "e": "␊",
    "f": "°",
    "g": "±",
    "h": "␤",
    "i": "␋",
    "j": "┘",
    "k": "┐",
    "l": "┌",
    "m": "└",
    "n": "┼",
    "o": "⎺",
    "p": "⎻",
    "q": "─",
    "r": "⎼",
    "s": "⎽",
    "t": "├",
    "u": "┤",
    "v": "┴",
    "w": "┬",
    "x": "│",
    "y": "≤",
    "z": "≥",
    "{": "π",
    "|": "≠",
    "}": "£",
    "~": "·",
}
"""Glyphs the DEC Special Graphics character set draws in place of ASCII.

A program selects the set with `ESC ( 0` and then writes `q` for a horizontal
rule, `x` for a vertical one and `l` for a corner. `ncurses` does so for its
line-drawing routines, like `box()` and the `ACS_*` characters. The screen keeps
the Unicode glyph, which the renderers draw as the shape it names.
"""

PENDING_LIMIT: Final = 4096
"""Characters an unfinished escape sequence may hold while its tail is awaited.

A sequence split across two reads waits for its tail, and each read re-reads
what waits. A string longer than this is skipped as it arrives instead, up to
the terminator closing it.
"""

TAB_WIDTH: Final = 8
"""Columns between two tab stops, until a program sets its own."""

_BLANK: Final[_Cell] = (None, ())
"""A cell nothing was written to, or that an erase cleared on no background."""

_STRING_END_RE: Final = re.compile(r"\x07|\x1b\\")
"""What closes a string: BEL, or the string terminator `ESC \\`."""

_PARTIAL_RE: Final = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*|\][^\x07\x1b]*\x1b?|[PX^_][^\x1b]*\x1b?|[ -/]*)\Z"
)
"""The opening of an escape sequence whose tail has not arrived yet.

A recorder reads whatever the terminal hands it, on boundaries that answer to
the pipe rather than to the stream, so a sequence routinely straddles two reads.
"""

_TOKEN_RE: Final = re.compile(
    # Printable text: everything but the C0 and C1 controls and DEL.
    r"(?P<text>[^\x00-\x1f\x7f-\x9f]+)"
    # A control sequence: parameters, intermediates, then the final byte.
    r"|\x1b\[(?P<parameters>[0-?]*)(?P<intermediates>[ -/]*)(?P<final>[@-~])"
    # An operating system command, closed by BEL or by the string terminator.
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    # A device control string, and the three other strings no terminal draws.
    r"|\x1b[PX^_][^\x1b]*\x1b\\"
    # Any other escape: intermediates, then a final byte that opens no string.
    r"|\x1b(?P<escape>[ -/]*[0-OQ-WYZ\\`-~])"
    # One control character.
    r"|(?P<control>[\x00-\x1a\x1c-\x1f\x7f-\x9f])"
)
"""One unit of a terminal stream: a run of text, a control sequence, a string,
an escape or a control character."""


def _numbers(parameters: str) -> list[int]:
    """Read the numeric parameters of a control sequence.

    An omitted parameter reads as `0`, which each sequence then takes as its own
    default. A sub-parameter, after a colon, is ignored.

    :param parameters: the parameter bytes, private marker removed.
    :return: one number per parameter.
    """
    numbers = []
    for field in parameters.split(";"):
        head = field.split(":", 1)[0]
        numbers.append(int(head) if head.isdigit() else 0)
    return numbers


def _sgr_codes(parameters: str) -> list[int]:
    """Read the parameters of an SGR sequence, colon sub-parameters included.

    xterm reads a color in two spellings: `38;2;R;G;B`, and the one of ITU T.416,
    `38:2::R:G:B`, whose sub-parameters {func}`~click_extra.ansi.apply_sgr_codes`
    does not take. The second is rewritten into the first. So is a styled
    underline, `4:3` for a curly one, which a capture draws as a plain one.

    :param parameters: the parameter bytes of the sequence.
    :return: the codes, in the form {func}`~click_extra.ansi.apply_sgr_codes`
        reads.
    """
    codes: list[int] = []
    for field in parameters.split(";"):
        if ":" not in field:
            codes.append(int(field) if field.isdigit() else 0)
            continue
        parts = [int(part) if part.isdigit() else 0 for part in field.split(":")]
        head = parts[0]
        if head in (38, 48) and len(parts) > 4 and parts[1] == 2:
            codes.extend((head, 2, *parts[-3:]))
        elif head in (38, 48) and len(parts) > 2 and parts[1] == 5:
            codes.extend((head, 5, parts[2]))
        elif head == 4:
            codes.append(24 if parts[1] == 0 else 4)
        elif head not in (38, 48, 58):
            codes.append(head)
    return codes


class TerminalScreen:
    """The screen a terminal shows, rebuilt from what was written at it.

    The screen is a grid of cells, each holding one grapheme and the style it was
    written in. A write lands on the cells under the cursor and leaves the others
    alone, so a redraw shorter than the row it covers keeps the row's tail, the
    way a terminal does. An erase blanks cells in the background color in force,
    which is how a full-screen program paints a bar across the screen.

    Rows the cursor leaves through the top of a full screen stay above it, as a
    terminal's history does, and stay in the picture: {attr}`display` holds
    every row a command printed, not only the last screenful. A full-screen
    program draws on the alternate screen instead, which keeps no history and
    holds exactly the screen's height. Leaving it brings the first screen back as
    it was.

    ```{note}
    A screen of unknown size is boundless: a row never wraps, and a newline on
    the last row adds a row below it. That is the screen an in-process recording
    has, which nothing tells how big its terminal is. The renderers fold a long
    row at the capture's own width later.
    ```
    """

    def __init__(
        self,
        columns: int | None = None,
        rows: int | None = None,
        *,
        onlcr: bool = True,
    ) -> None:
        """Start on an empty screen, with the cursor in its top-left corner.

        :param columns: width of the terminal, in cells. `None` never wraps.
        :param rows: height of the terminal, in cells. `None` never scrolls.
        :param onlcr: return the cursor to the start of its row on every newline,
            as the `ONLCR` flag of a terminal driver does on the way to the
            screen. A pseudo-terminal applies the flag itself, so a stream read
            from one already carries a return before each newline that wants
            one, and a full-screen program clears the flag to move straight
            down. A stream written in-process went through no driver at all.
        :raises ValueError: when a stated size is not positive.
        """
        if (columns is not None and columns < 1) or (rows is not None and rows < 1):
            raise ValueError(f"A terminal of {columns}x{rows} cells holds nothing.")
        self.width = columns
        """Width of the terminal, in cells, or `None` when unbounded."""
        self.height = rows
        """Height of the terminal, in cells, or `None` when unbounded."""
        self._onlcr = onlcr
        self._spans: dict[_Style, tuple[str, str]] = {}
        self._reset()

    def _reset(self) -> None:
        """Put every state back to the one a terminal starts in."""
        self._main: list[list[_Cell]] = []
        self._alternate: list[list[_Cell]] | None = None
        self._lines = self._main
        self._main_top = 0
        self._row = 0
        self._column = 0
        self._wrap_pending = False
        self._state: dict[str, Any] = {}
        self._style: _Style = ()
        self._charsets = ["B", "B"]
        self._shift = 0
        self._autowrap = True
        self._insert = False
        self._origin = False
        self._newline_returns = self._onlcr
        self._margin_top = 0
        self._margin_bottom = None if self.height is None else self.height - 1
        self._tab_stops: set[int] | None = None
        self._saved: dict[bool, tuple[Any, ...]] = {}
        self._last = ""
        self._pending = ""
        self._skipping = False
        self._cursor_visible = True
        self._synchronized = False

    @property
    def alternate(self) -> bool:
        """Whether a full-screen program switched to the alternate screen."""
        return self._lines is self._alternate

    @property
    def cursor(self) -> tuple[int, int]:
        """Row and column the cursor stands on, both counted from zero.

        The row counts from the top of {attr}`rows`, history included.
        """
        return self._base() + self._row, self._column

    @property
    def cursor_visible(self) -> bool:
        """Whether the program shows its cursor, which a full-screen one hides."""
        return self._cursor_visible

    @property
    def display(self) -> str:
        """The screen as it stands, rows joined by newlines."""
        return "\n".join(self.rows)

    @property
    def rows(self) -> list[str]:
        """Every row of the picture, each as styled text.

        On the first screen, the history and every row down to the last one
        holding anything, or the cursor's when it stands lower: output closing
        on a newline leaves an empty last row, where the cursor waits. On the
        alternate screen, exactly its height.
        """
        return [self._render(cells) for cells in self._picture()]

    @property
    def synchronized(self) -> bool:
        """Whether the program is in the middle of a synchronized update.

        A program opens one with `CSI ? 2026 h` and closes it with `CSI ? 2026 l`,
        asking its terminal to show nothing it drew in between until the close.
        """
        return self._synchronized

    def feed(self, text: str) -> None:
        """Replay what a command wrote, moving the screen to what it now shows.

        Safe to call with the stream cut anywhere: an escape sequence straddling
        two calls is held until the rest of it arrives. A sequence still
        unfinished when the stream ends never reaches the screen, having named
        nothing to draw.

        :param text: the stream, control sequences and all.
        """
        text = self._pending + text
        self._pending = ""
        position, end = 0, len(text)
        if self._skipping:
            closing = _STRING_END_RE.search(text)
            if closing is None:
                # An escape ending the read may open the terminator.
                self._pending = "\x1b" if text.endswith("\x1b") else ""
                return
            position = closing.end()
            self._skipping = False
        while position < end:
            match = _TOKEN_RE.match(text, position)
            if match is None:
                # Only an escape sequence fails to match, either because its
                # tail is still on its way or because it is malformed. A
                # terminal drops the escape of a malformed one and reads on.
                if _PARTIAL_RE.match(text, position) is None:
                    position += 1
                elif end - position <= PENDING_LIMIT:
                    self._pending = text[position:]
                    return
                elif text[position + 1] in "]PX^_":
                    # A string this long is skipped up to its terminator, whose
                    # escape may end the read.
                    self._skipping = True
                    self._pending = "\x1b" if text.endswith("\x1b") else ""
                    return
                else:
                    position += 1
                continue
            position = match.end()
            kind = match.lastgroup
            if kind == "text":
                self._print(match["text"])
            elif kind == "final":
                self._sequence(
                    match["parameters"], match["intermediates"], match["final"]
                )
            elif kind == "escape":
                self._escape(match["escape"])
            elif kind == "control":
                self._control(match["control"])
            # What is left is a string, which draws nothing.

    def _base(self) -> int:
        """Index of the screen's top row in the lines of the buffer in use."""
        return 0 if self.alternate else self._main_top

    def _cells(self, row: int) -> list[_Cell]:
        """The cells of a row of the screen, created when nothing reached it yet.

        :param row: the row, counted from the top of the screen.
        :return: the row's cells, which the caller may change in place.
        """
        index = self._base() + row
        lines = self._lines
        while len(lines) <= index:
            lines.append([])
        return lines[index]

    def _erased(self) -> _Cell:
        """The cell an erase leaves: a blank in the background color in force."""
        background = self._state.get("bg")
        return _BLANK if background is None else (None, (("bg", background),))

    def _erased_row(self) -> list[_Cell]:
        """A row an erase or a scroll leaves, painted like {meth}`_erased`."""
        erased = self._erased()
        if erased == _BLANK or self.width is None:
            return []
        return [erased] * self.width

    def _pad_screen(self) -> None:
        """Create every row of a bounded screen, so rows can move as a block."""
        if self.height is not None:
            self._cells(self.height - 1)

    def _clamp_column(self, column: int) -> int:
        """Keep a column on the screen."""
        if self.width is not None:
            column = min(column, self.width - 1)
        return max(column, 0)

    def _clamp_row(self, row: int) -> int:
        """Keep a row on the screen."""
        if self.height is not None:
            row = min(row, self.height - 1)
        return max(row, 0)

    def _move(self, row: int, column: int) -> None:
        """Send the cursor to a cell, kept on the screen."""
        self._row = self._clamp_row(row)
        self._column = self._clamp_column(column)
        self._wrap_pending = False

    def _home(self) -> None:
        """Send the cursor to the top-left corner of the screen or its region."""
        self._move(self._margin_top if self._origin else 0, 0)

    def _print(self, text: str) -> None:
        """Lay printable text on the screen, one grapheme per cell or two.

        :param text: printable characters, with no control among them.
        """
        # Deferred import: keeps wcwidth off the startup path of every CLI.
        from wcwidth import iter_graphemes

        graphics = self._charsets[self._shift] == "0"
        for grapheme in iter_graphemes(text):
            if graphics:
                grapheme = DEC_SPECIAL_GRAPHICS.get(grapheme, grapheme)
            width = cell_width(grapheme)
            if width:
                self._put(grapheme, min(width, 2))
                self._last = grapheme
            else:
                self._combine(grapheme)

    def _put(self, grapheme: str, width: int) -> None:
        """Write one grapheme under the cursor and move the cursor past it.

        Writing the last column of a row leaves the cursor on it, with a wrap
        pending: the next grapheme starts the row below, while a return, a
        backspace or a cursor movement cancels the wrap. `ncurses` counts on
        this, which xterm calls the `xenl` glitch.

        :param grapheme: what to write.
        :param width: cells it covers, `1` or `2`.
        """
        if self._wrap_pending:
            self._wrap_pending = False
            if self._autowrap:
                self._column = 0
                self._index()
        if self.width is not None and self._column + width > self.width:
            if width > self.width:
                return
            if self._autowrap:
                # A wide glyph not fitting on the row moves down whole.
                self._column = 0
                self._index()
            else:
                self._column = self.width - width
        cells = self._cells(self._row)
        column = self._column
        if self._insert:
            self._open(cells, column, width)
        self._split_wide(cells, column, column + width)
        if len(cells) < column + width:
            cells.extend([_BLANK] * (column + width - len(cells)))
        cells[column] = (grapheme, self._style)
        if width == 2:
            cells[column + 1] = ("", self._style)
        self._column += width
        if self.width is not None and self._column >= self.width:
            self._column = self.width - 1
            self._wrap_pending = self._autowrap

    def _combine(self, mark: str) -> None:
        """Join a zero-width character to the grapheme before the cursor.

        A combining accent or a variation selector arriving in a later read
        than its base still lands on it.
        """
        column = self._column if self._wrap_pending else self._column - 1
        cells = self._cells(self._row)
        if column >= len(cells):
            return
        if column > 0 and cells[column][0] == "":
            column -= 1
        if column < 0:
            return
        glyph, style = cells[column]
        cells[column] = ((glyph or " ") + mark, style)

    @staticmethod
    def _split_wide(cells: list[_Cell], start: int, stop: int) -> None:
        """Blank the half a change between `start` and `stop` leaves of a wide glyph.

        A wide glyph spans two cells. Overwriting or erasing one of them leaves
        the other on its own, which a terminal shows as a blank.
        """
        if 0 < start < len(cells) and cells[start][0] == "":
            cells[start - 1] = (None, cells[start - 1][1])
        if stop < len(cells) and cells[stop][0] == "":
            cells[stop] = (None, cells[stop][1])

    def _open(self, cells: list[_Cell], column: int, count: int) -> None:
        """Insert blank cells at `column`, pushing the rest of the row right."""
        if len(cells) <= column:
            return
        self._split_wide(cells, column, column)
        cells[column:column] = [self._erased()] * count
        if self.width is not None and len(cells) > self.width:
            del cells[self.width :]
            # A wide glyph pushed half off the row loses its other half too.
            if cells and cells[-1][0] and cell_width(cells[-1][0]) == 2:
                cells[-1] = (None, cells[-1][1])

    def _control(self, char: str) -> None:
        """Act on one control character."""
        if char in "\n\x0b\x0c":
            if self._newline_returns:
                self._column = 0
            self._index()
        elif char == "\r":
            self._column = 0
            self._wrap_pending = False
        elif char == "\b":
            self._column = max(self._column - 1, 0)
            self._wrap_pending = False
        elif char == "\t":
            self._tab(1)
        elif char == "\x0e":
            self._shift = 1
        elif char == "\x0f":
            self._shift = 0
        # A bell and the remaining controls change nothing on screen.

    def _escape(self, sequence: str) -> None:
        """Act on an escape sequence that is not a control sequence.

        :param sequence: what follows the escape: intermediates and final byte.
        """
        if sequence == "7":
            self._save_cursor()
        elif sequence == "8":
            self._restore_cursor()
        elif sequence == "D":
            self._index()
        elif sequence == "E":
            self._column = 0
            self._index()
        elif sequence == "M":
            self._reverse_index()
        elif sequence == "H":
            self._set_tab_stop()
        elif sequence == "c":
            self._reset()
        elif len(sequence) == 2 and sequence[0] in "()":
            # Designates the character set G0, with `(`, or G1, with `)`. Only
            # line drawing reads differently from ASCII.
            self._charsets["()".index(sequence[0])] = sequence[1]
        # Keypad modes and the other character sets change nothing on screen.

    def _sequence(self, parameters: str, intermediates: str, final: str) -> None:
        """Act on one control sequence.

        :param parameters: the parameter bytes, private marker included.
        :param intermediates: the intermediate bytes, which most sequences lack.
        :param final: the final byte, naming the function.
        """
        private = parameters[0] if parameters and parameters[0] in "<=>?" else ""
        parameters = parameters[len(private) :]
        if intermediates:
            if intermediates == "!" and final == "p" and not private:
                self._soft_reset()
            # The cursor's shape and the rest change nothing the screen holds.
            return
        if private:
            if private == "?" and final in "hl":
                self._private_modes(_numbers(parameters), final == "h")
            return
        if final == "m":
            apply_sgr_codes(_sgr_codes(parameters), self._state)
            self._style = tuple(sorted(self._state.items()))
            return
        numbers = _numbers(parameters)
        count = numbers[0] or 1
        if final == "A":
            top = self._margin_top if self._row >= self._margin_top else 0
            self._move(max(self._row - count, top), self._column)
        elif final in "Be":
            bottom = self._margin_bottom
            if bottom is not None and self._row > bottom:
                bottom = None
            row = self._row + count
            self._move(row if bottom is None else min(row, bottom), self._column)
        elif final in "Ca":
            self._move(self._row, self._column + count)
        elif final == "D":
            self._move(self._row, self._column - count)
        elif final == "E":
            self._sequence(parameters, "", "B")
            self._column = 0
        elif final == "F":
            self._sequence(parameters, "", "A")
            self._column = 0
        elif final in "G`":
            self._move(self._row, count - 1)
        elif final in "Hf":
            row = (numbers[0] or 1) - 1
            column = (numbers[1] if len(numbers) > 1 else 0) or 1
            if self._origin:
                bottom = self._margin_bottom
                row = self._margin_top + row
                if bottom is not None:
                    row = min(row, bottom)
            self._move(row, column - 1)
        elif final == "I":
            self._tab(count)
        elif final == "Z":
            self._tab(-count)
        elif final == "J":
            self._erase_display(numbers[0])
        elif final == "K":
            self._erase_line(numbers[0])
        elif final == "L":
            self._insert_rows(count)
        elif final == "M":
            self._delete_rows(count)
        elif final == "P":
            self._delete_cells(count)
        elif final == "S":
            self._scroll_up(count)
        elif final == "T" and len(numbers) == 1:
            # With more parameters, this is xterm's mouse highlight tracking.
            self._scroll_down(count)
        elif final == "X":
            self._erase_cells(count)
        elif final == "@":
            self._open(self._cells(self._row), self._column, count)
        elif final == "b":
            if self._last:
                width = min(cell_width(self._last), 2)
                for _ in range(count):
                    self._put(self._last, width)
        elif final == "d":
            self._move(count - 1, self._column)
        elif final == "g":
            self._clear_tab_stops(numbers[0])
        elif final in "hl":
            for mode in numbers:
                if mode == 4:
                    self._insert = final == "h"
                elif mode == 20:
                    self._newline_returns = final == "h"
        elif final == "r":
            self._set_margins(numbers)
        elif final == "s" and not parameters:
            self._save_cursor()
        elif final == "u" and not parameters:
            self._restore_cursor()
        # Queries, window operations and the rest change nothing on screen.

    def _private_modes(self, modes: list[int], enable: bool) -> None:
        """Set or reset DEC private modes, the `CSI ? … h` and `CSI ? … l` family."""
        for mode in modes:
            if mode == 6:
                self._origin = enable
                self._home()
            elif mode == 7:
                self._autowrap = enable
                if not enable:
                    self._wrap_pending = False
            elif mode == 25:
                self._cursor_visible = enable
            elif mode in (47, 1047):
                self._switch_screen(enable)
                if not enable and mode == 1047:
                    # Left cleared, so coming back finds it blank.
                    self._alternate = None
            elif mode == 1048:
                if enable:
                    self._save_cursor()
                else:
                    self._restore_cursor()
            elif mode == 1049:
                if enable:
                    self._save_cursor()
                    self._alternate = None
                    self._switch_screen(True)
                else:
                    self._switch_screen(False)
                    self._restore_cursor()
            elif mode == 2026:
                self._synchronized = enable

    def _switch_screen(self, alternate: bool) -> None:
        """Draw on the alternate screen, or back on the first one."""
        if alternate == self.alternate:
            return
        if alternate:
            if self._alternate is None:
                self._alternate = [[] for _ in range(self.height or 0)]
            self._lines = self._alternate
        else:
            self._lines = self._main

    def _save_cursor(self) -> None:
        """Remember the cursor and its rendition, one memory per screen."""
        self._saved[self.alternate] = (
            self._row,
            self._column,
            self._wrap_pending,
            dict(self._state),
            list(self._charsets),
            self._shift,
            self._origin,
        )

    def _restore_cursor(self) -> None:
        """Bring back what {meth}`_save_cursor` remembered for this screen.

        With nothing remembered, the cursor goes home in the default rendition.
        """
        saved = self._saved.get(self.alternate)
        if saved is None:
            saved = (0, 0, False, {}, ["B", "B"], 0, False)
        row, column, wrap, state, charsets, shift, origin = saved
        self._move(row, column)
        self._wrap_pending = wrap
        self._state = dict(state)
        self._style = tuple(sorted(self._state.items()))
        self._charsets = list(charsets)
        self._shift = shift
        self._origin = origin

    def _soft_reset(self) -> None:
        """Reset the modes and the rendition, leaving the screen's cells alone."""
        self._state = {}
        self._style = ()
        self._charsets = ["B", "B"]
        self._shift = 0
        self._autowrap = True
        self._insert = False
        self._origin = False
        self._cursor_visible = True
        self._margin_top = 0
        self._margin_bottom = None if self.height is None else self.height - 1
        self._saved.pop(self.alternate, None)

    def _set_margins(self, numbers: list[int]) -> None:
        """Bound the rows a newline or a deletion scrolls, then go home."""
        if self.height is None:
            return
        top = (numbers[0] or 1) - 1
        bottom = min(
            ((numbers[1] if len(numbers) > 1 else 0) or self.height) - 1,
            self.height - 1,
        )
        if top < bottom:
            self._margin_top, self._margin_bottom = top, bottom
            self._home()

    def _index(self) -> None:
        """Move the cursor down a row, scrolling the region from its last row."""
        self._wrap_pending = False
        if self.height is None:
            self._row += 1
        elif self._row == self._margin_bottom:
            self._scroll_up(1)
        elif self._row < self.height - 1:
            self._row += 1

    def _reverse_index(self) -> None:
        """Move the cursor up a row, scrolling the region from its first row."""
        self._wrap_pending = False
        if self.height is not None and self._row == self._margin_top:
            self._scroll_down(1)
        elif self._row > 0:
            self._row -= 1

    def _scroll_up(self, count: int) -> None:
        """Move the rows of the scroll region up, blank rows entering below.

        Scrolling the whole first screen keeps the rows leaving its top as the
        history above it. A region or the alternate screen drops them.
        """
        if self.height is None or self._margin_bottom is None:
            return
        top, bottom = self._margin_top, self._margin_bottom
        count = min(count, bottom - top + 1)
        self._pad_screen()
        lines, base = self._lines, self._base()
        if not self.alternate and top == 0 and bottom == self.height - 1:
            lines.extend(self._erased_row() for _ in range(count))
            self._main_top += count
            return
        del lines[base + top : base + top + count]
        for _ in range(count):
            lines.insert(base + bottom - count + 1, self._erased_row())

    def _scroll_down(self, count: int) -> None:
        """Move the rows of the scroll region down, blank rows entering above."""
        if self.height is None or self._margin_bottom is None:
            return
        top, bottom = self._margin_top, self._margin_bottom
        count = min(count, bottom - top + 1)
        self._pad_screen()
        lines, base = self._lines, self._base()
        del lines[base + bottom - count + 1 : base + bottom + 1]
        for _ in range(count):
            lines.insert(base + top, self._erased_row())

    def _insert_rows(self, count: int) -> None:
        """Insert blank rows at the cursor, pushing the region below it down."""
        bottom = self._margin_bottom
        if self._row < self._margin_top or (bottom is not None and self._row > bottom):
            return
        lines, index = self._lines, self._base() + self._row
        if bottom is None:
            self._cells(self._row)
            lines[index:index] = [self._erased_row() for _ in range(count)]
        else:
            count = min(count, bottom - self._row + 1)
            self._pad_screen()
            del lines[self._base() + bottom - count + 1 : self._base() + bottom + 1]
            lines[index:index] = [self._erased_row() for _ in range(count)]
        self._column = 0
        self._wrap_pending = False

    def _delete_rows(self, count: int) -> None:
        """Delete rows at the cursor, pulling the region below it up."""
        bottom = self._margin_bottom
        if self._row < self._margin_top or (bottom is not None and self._row > bottom):
            return
        lines, index = self._lines, self._base() + self._row
        if bottom is None:
            del lines[index : index + count]
        else:
            count = min(count, bottom - self._row + 1)
            self._pad_screen()
            del lines[index : index + count]
            for _ in range(count):
                lines.insert(self._base() + bottom - count + 1, self._erased_row())
        self._column = 0
        self._wrap_pending = False

    def _delete_cells(self, count: int) -> None:
        """Delete cells at the cursor, pulling the rest of the row left."""
        cells = self._cells(self._row)
        column = self._column
        erased = self._erased()
        self._wrap_pending = False
        if self.width is None or erased == _BLANK:
            # The cells entering at the right edge are blank, which a row
            # ending early already shows.
            self._split_wide(cells, column, column + count)
            del cells[column : column + count]
            return
        count = min(count, self.width - column)
        cells.extend([_BLANK] * (self.width - len(cells)))
        self._split_wide(cells, column, column + count)
        del cells[column : column + count]
        cells.extend([erased] * count)

    def _erase_cells(self, count: int) -> None:
        """Blank cells from the cursor on, without moving the rest of the row."""
        cells = self._cells(self._row)
        start = self._column
        stop = start + count
        if self.width is not None:
            stop = min(stop, self.width)
        self._split_wide(cells, start, stop)
        if len(cells) < stop:
            cells.extend([_BLANK] * (stop - len(cells)))
        cells[start:stop] = [self._erased()] * (stop - start)
        self._wrap_pending = False

    def _erase_line(self, mode: int) -> None:
        """Blank part of the cursor's row: after it, before it, or all of it."""
        cells = self._cells(self._row)
        column = self._column
        erased = self._erased()
        if mode == 0:
            self._split_wide(cells, column, column)
            if erased == _BLANK or self.width is None:
                del cells[column:]
            else:
                if len(cells) < column:
                    cells.extend([_BLANK] * (column - len(cells)))
                cells[column:] = [erased] * (self.width - column)
        elif mode == 1:
            stop = column + 1
            self._split_wide(cells, stop, stop)
            if len(cells) < stop:
                cells.extend([_BLANK] * (stop - len(cells)))
            cells[:stop] = [erased] * stop
        elif mode == 2:
            self._lines[self._base() + self._row] = self._erased_row()
        self._wrap_pending = False

    def _erase_display(self, mode: int) -> None:
        """Blank part of the screen: after the cursor, before it, or all of it.

        Mode `3` drops the history above the first screen instead.
        """
        if self._erased() != _BLANK:
            # A painted erase reaches rows nothing was written to yet.
            self._pad_screen()
        lines, base = self._lines, self._base()
        end = base + self.height if self.height is not None else len(lines)
        cursor = base + self._row
        if mode == 0:
            self._erase_line(0)
            for index in range(cursor + 1, min(end, len(lines))):
                lines[index] = self._erased_row()
        elif mode == 1:
            for index in range(base, cursor):
                lines[index] = self._erased_row()
            self._erase_line(1)
        elif mode == 2:
            for index in range(base, min(end, len(lines))):
                lines[index] = self._erased_row()
        elif mode == 3 and not self.alternate:
            del lines[: self._main_top]
            self._main_top = 0
        self._wrap_pending = False

    def _tab(self, count: int) -> None:
        """Move the cursor to the next tab stop, or back to the previous one."""
        for _ in range(abs(count)):
            column = self._column
            if count > 0:
                if self._tab_stops is None:
                    column = (column // TAB_WIDTH + 1) * TAB_WIDTH
                else:
                    later = [stop for stop in self._tab_stops if stop > column]
                    if later:
                        column = min(later)
                    elif self.width is not None:
                        column = self.width - 1
            elif self._tab_stops is None:
                column = max((column - 1) // TAB_WIDTH * TAB_WIDTH, 0)
            else:
                earlier = [stop for stop in self._tab_stops if stop < column]
                column = max(earlier) if earlier else 0
            self._move(self._row, column)

    def _default_tab_stops(self) -> set[int]:
        """The stops a terminal starts with, every {data}`TAB_WIDTH` columns."""
        return set(range(0, self.width or 1024, TAB_WIDTH))

    def _set_tab_stop(self) -> None:
        """Add a tab stop at the cursor's column."""
        if self._tab_stops is None:
            self._tab_stops = self._default_tab_stops()
        self._tab_stops.add(self._column)

    def _clear_tab_stops(self, mode: int) -> None:
        """Remove the tab stop at the cursor's column, or every one of them."""
        if mode == 3:
            self._tab_stops = set()
        elif mode == 0:
            if self._tab_stops is None:
                self._tab_stops = self._default_tab_stops()
            self._tab_stops.discard(self._column)

    def _picture(self) -> list[list[_Cell]]:
        """The rows {attr}`rows` renders, each a list of cells."""
        lines = self._lines
        if self.alternate and self.height is not None:
            return lines
        last = self._base() + self._row
        for index in range(len(lines) - 1, last, -1):
            if any(cell != _BLANK for cell in lines[index]):
                last = index
                break
        return [lines[index] if index < len(lines) else [] for index in range(last + 1)]

    def _render(self, cells: list[_Cell]) -> str:
        """Write one row back as styled text, its trailing blanks left out.

        A blank painted with a background is kept: it is part of a bar.
        """
        end = len(cells)
        while end and cells[end - 1] == _BLANK:
            end -= 1
        parts: list[str] = []
        run: list[str] = []
        style: _Style = ()
        for glyph, cell_style in cells[:end]:
            if glyph == "":
                continue
            if cell_style != style:
                parts.append(self._wrap("".join(run), style))
                run, style = [], cell_style
            run.append(" " if glyph is None else glyph)
        parts.append(self._wrap("".join(run), style))
        return "".join(parts)

    def _wrap(self, text: str, style: _Style) -> str:
        """Wrap a run of text in the escapes of its style.

        Written by {func}`click.style`, the way a Click Extra CLI writes a styled
        run in the first place, so a recorded frame reads back exactly as the CLI
        printed it.
        """
        if not text or not style:
            return text
        span = self._spans.get(style)
        if span is None:
            opening, _, closing = click.style("\0", **dict(style)).partition("\0")
            span = self._spans[style] = (opening, closing)
        return f"{span[0]}{text}{span[1]}"
