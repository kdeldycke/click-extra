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
"""Rebuild a terminal's screen from the stream a command writes at it.

A command that animates does not print its frames one after another: it prints
one, returns the cursor to the start of the line, and prints the next over it.
The stream therefore says what *changed*, and the frames only exist once
something replays those changes against a screen. That replay is what this
module does.

```{note}
The vocabulary is deliberately small. A spinner and a progress bar move the
cursor with a carriage return, clear what they are about to redraw with an
erase-in-line, and end a kept line with a newline. Following those, plus the
color codes that travel with the text, is enough to recover their frames, and it
costs no dependency. Anything addressing the cursor by coordinate, clearing the
screen or switching to the alternate buffer is out of scope: a full-screen
program is not what a capture pictures.
```

```{todo}
Read a full-screen program through [pyte](https://github.com/selectel/pyte)
behind an optional extra, should picturing one ever be asked for. The screen
below would stay the default, so the common case keeps costing no dependency.
```
"""

from __future__ import annotations

import re

from wcwidth import wcswidth

CSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
"""One control sequence, from the escape that opens it to the letter ending it.

Broad on purpose: the sequences this screen ignores have to be *recognized* to
be dropped, or their parameter digits would land on the screen as text.
"""

PARTIAL_CSI_RE = re.compile(r"\x1b(\[[0-9;?]*)?$")
"""The opening of a control sequence the rest of which has not arrived yet.

A recorder reads whatever the terminal hands it, on boundaries that answer to
the pipe rather than to the stream: a sequence routinely straddles two reads.
Recognizing the half that arrived first is what keeps its bracket and digits off
the screen, where they would otherwise read as text a command never printed.
"""

ERASE_IN_LINE = "K"
"""Final letter of the sequence clearing a line from the cursor onward."""

SELECT_GRAPHIC_RENDITION = "m"
"""Final letter of the sequence setting colors and attributes.

The one class of sequence kept in the screen's text rather than acted on: it
carries no cursor movement, and a capture renders it as the color it names.
"""


class TerminalScreen:
    """The text a terminal shows, rebuilt from what was written at it.

    Rows accumulate as a command writes. A carriage return moves the cursor back
    to the start of the row it is on, so what follows lands over what is already
    there, which is how an animation redraws itself in place.

    ```{caution}
    Overwriting is whole-row rather than per-cell: a write landing on column
    zero replaces the row instead of covering its first few cells. Every
    animation this screen exists for redraws its row in full and ends with an
    erase-in-line, so the two agree there. They part on a command that overwrites
    a *prefix* and leaves a longer tail behind, where a terminal keeps the tail
    and this screen drops it. Tracking that faithfully means holding a style per
    cell, which is a full emulator and the dependency this one avoids.
    ```
    """

    def __init__(self) -> None:
        """Start on a single empty row, with the cursor at its start."""
        self.rows: list[str] = [""]
        self._column = 0
        self._partial = ""

    @property
    def display(self) -> str:
        """The screen as it stands, rows joined by newlines."""
        return "\n".join(self.rows)

    def feed(self, text: str) -> None:
        """Replay what a command wrote, moving the screen to what it now shows.

        Safe to call with the stream cut anywhere: a control sequence straddling
        two calls is held until the rest of it arrives. A sequence still
        unfinished when the stream ends never reaches the screen, having named
        nothing to draw.

        :param text: the stream, control sequences and all.
        """
        text = self._partial + text
        self._partial = ""
        position = 0
        for sequence in CSI_RE.finditer(text):
            self._write(text[position : sequence.start()])
            self._control(sequence.group())
            position = sequence.end()

        tail = text[position:]
        opening = PARTIAL_CSI_RE.search(tail)
        if opening:
            self._partial = tail[opening.start() :]
            tail = tail[: opening.start()]
        self._write(tail)

    def _control(self, sequence: str) -> None:
        """Act on one control sequence, or drop it when it is out of scope."""
        final = sequence[-1]
        if final == SELECT_GRAPHIC_RENDITION:
            # Styling travels with the text it wraps: kept, never acted on.
            self.rows[-1] += sequence
        elif final == ERASE_IN_LINE and not self._column:
            # Cleared from the start of the row, which empties the whole of it.
            # Past the start, the row already holds only what was written since
            # the cursor came back, so there is nothing left to erase.
            self.rows[-1] = ""

    def _write(self, text: str) -> None:
        """Lay printable text on the screen, one row per newline it carries."""
        for line_index, line in enumerate(text.split("\n")):
            if line_index:
                self.rows.append("")
                self._column = 0
            for chunk_index, chunk in enumerate(line.split("\r")):
                if chunk_index:
                    # The cursor goes back to the start of the row, which this
                    # screen redraws whole: see the class's caution. Clearing
                    # here rather than when the next text lands is what keeps a
                    # color set between the return and the text it wraps.
                    self.rows[-1] = ""
                    self._column = 0
                if not chunk:
                    continue
                self.rows[-1] += chunk
                # A wide glyph covers the two cells it is drawn with. Text
                # carrying something unmeasurable reads as zero rather than as
                # the -1 wcswidth answers with.
                self._column += max(wcswidth(chunk), 0)
