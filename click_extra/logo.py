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
"""Terminal rendition of the Click Extra brand mark.

The mark of `docs/assets/logo-square.svg` is six wireframe cubes stacked three-two-one.
Here each cube is redrawn as {data}`CUBE`, the smallest arrangement of `/`, `\\`, `_`
and `|` that still reads as an isometric solid, and the six are laid out on the same
lattice the artwork uses.

Line art rather than half-blocks, and plain ASCII rather than any of the block or
geometric ranges, because both choices buy the same thing: the mark keeps its shape
when something goes missing. A half-block rendition carries its structure in its
colors and collapses into one silhouette the moment they are stripped, and every
Unicode candidate that reads as a cube on its own — the quadrant blocks, `◤◥`, the
hexagons — is missing from at least one of the monospace faces this project's own
users run. Four ASCII characters survive every terminal, every codepage and the loss
of color.

Only the artwork lives here. Measuring it, seating the facts beside it and deciding
whether to draw it at all belong to {class}`~click_extra.version.VersionScreen`,
which knows nothing of cubes: this module is one worked example of feeding it, and a
CLI of your own would write its own such module.
"""

from __future__ import annotations

from click import style

from .version import VersionScreen, default_facts, dependency_versions

DOCS_URL = "https://kdeldycke.github.io/click-extra"
"""Canonical documentation host, advertised on the version screen."""

TAGLINE = "Drop-in replacement for Click and Cloup"
"""What the project is, spelled out under the program name."""

CUBE: tuple[str, ...] = (
    " __ ",
    "/\\_\\",
    "\\/_/",
)
"""One cube of the mark, in four columns and three lines.

The floor for an isometric solid in line art: the lid needs two columns to slope
across, and each of the two walls one more. Taking a column away collapses the lid
into a single character and the cube reads as a plus sign; taking a line away leaves
no room for a wall at all.
"""

CUBE_FACES: tuple[str, ...] = (
    ".tt.",
    "lttr",
    "llrr",
)
"""Which face each character of {data}`CUBE` belongs to, for coloring.

`t` is the lid, `l` and `r` the two walls, `.` the cells the cube does not paint. A
character on a silhouette edge is assigned to the face it bounds, so the wireframe
picks up the same three colors per cube the artwork gives its ribbons.
"""

COLUMN_STEP = 4
"""Columns between two cubes of the same row: the cube's own width, so they touch."""

ROW_STEP = 3
"""Lines between two rows of cubes: the cube's own height, so none overlaps another.

Overlapping rows by a line does buy back two lines of screen, and was tried. It
merges each cube's floor into the lid of the one below and the six stop reading as
six, which is the whole point of the mark.
"""

LEVEL_OFFSET = 2
"""Columns a row is shifted right of the one below it, seating it between two cubes."""

LEVELS: tuple[int, ...] = (3, 2, 1)
"""Cubes per row, bottom to top."""

FACE_COLORS: tuple[dict[str, tuple[int, int, int]], ...] = (
    {"t": (0xE9, 0xB3, 0x3D), "l": (0x49, 0xF9, 0x57), "r": (0x71, 0x83, 0x41)},
    {"t": (0xE5, 0xFD, 0xD3), "l": (0x9B, 0x51, 0x07), "r": (0x69, 0x39, 0x99)},
    {"t": (0x9F, 0x73, 0x9B), "l": (0x5F, 0xF3, 0xE1), "r": (0x53, 0x8B, 0x4B)},
    {"t": (0xA1, 0x09, 0xF1), "l": (0x97, 0x11, 0xC3), "r": (0xBF, 0x79, 0xAF)},
    {"t": (0x2F, 0x75, 0xBB), "l": (0xF5, 0x4B, 0x01), "r": (0x97, 0xC1, 0x83)},
    {"t": (0x3B, 0xFD, 0xAF), "l": (0xC7, 0x33, 0x8D), "r": (0x43, 0x21, 0x8D)},
)
"""Each cube's three face colors, in the order {func}`render_logo` lays them out.

Read off the ribbons of `docs/assets/logo-square.svg`, and repeated here because
runtime code cannot open that file: the artwork ships in the sdist but not in the
wheel. `test_logo_palette_tracks_the_artwork` fails if the two ever disagree.

Emitted as 24-bit color rather than mapped onto the 256-color cube. The cube cannot
separate them — `#718341` and `#538B4B` belong to different faces of different cubes
and land on the same index — and the usual reason to prefer it does not apply here: a
terminal that does not understand a 24-bit sequence drops the color and still draws
six legible cubes.
"""

LOGO_WIDTH = max(
    LEVEL_OFFSET * level + COLUMN_STEP * (count - 1) + len(CUBE[0])
    for level, count in enumerate(LEVELS)
)
"""Columns the mark occupies, every rendered line being padded to it.

Taken over every row rather than assuming the widest one is also the least indented.
It happens to be, the pyramid narrowing as it rises faster than it shifts right, but
that is a property of {data}`LEVELS` and not something the layout enforces.
"""

LOGO_LINES = ROW_STEP * (len(LEVELS) - 1) + len(CUBE)
"""Terminal lines the mark renders to."""


def _placements() -> list[tuple[int, int, int]]:
    """Where each cube sits, as (column, line, index), back row first.

    Back to front, so a cube nearer the viewer paints over the one behind it.
    """
    spots = []
    index = 0
    for level, count in enumerate(LEVELS):
        for column in range(count):
            spots.append((
                LEVEL_OFFSET * level + COLUMN_STEP * column,
                LOGO_LINES - len(CUBE) - ROW_STEP * level,
                index,
            ))
            index += 1
    return list(reversed(spots))


def render_logo() -> tuple[str, ...]:
    """Paint the six cubes into styled lines, each exactly {data}`LOGO_WIDTH` wide.

    Runs of characters sharing a color are styled together rather than one escape
    sequence per character, keeping the mark from tripling in size.

    Trailing blanks are deliberately kept. They are what squares the mark off into a
    block the metadata column can be seated against, and re-padding afterwards is not
    an option a caller has: `str.ljust` counts the escape sequences it cannot see, so
    on a styled line it silently does nothing.
    """
    chars = [[" "] * LOGO_WIDTH for _ in range(LOGO_LINES)]
    colors: list[list[tuple[int, int, int] | None]] = [
        [None] * LOGO_WIDTH for _ in range(LOGO_LINES)
    ]
    for left, top, index in _placements():
        for row, (art, faces) in enumerate(zip(CUBE, CUBE_FACES)):
            for offset, (char, face) in enumerate(zip(art, faces)):
                if char == " ":
                    continue
                chars[top + row][left + offset] = char
                colors[top + row][left + offset] = FACE_COLORS[index][face]

    lines = []
    for char_row, color_row in zip(chars, colors):
        line = ""
        run = ""
        current: tuple[int, int, int] | None = None
        for char, color in zip(char_row, color_row):
            if color != current:
                line += _paint(run, current)
                run, current = "", color
            run += char
        lines.append(line + _paint(run, current))
    return tuple(lines)


def _paint(run: str, color: tuple[int, int, int] | None) -> str:
    """Style a run of characters, leaving uncolored ones as bare text.

    Uncolored runs must not go through `style()`: it would wrap them in a reset
    sequence, which costs bytes and, worse, cancels nothing while looking like it
    might.
    """
    if not run or color is None:
        return run
    return style(run, fg=color)


def brand_facts() -> dict[str, str]:
    """The interpreter and platform every screen reports, plus this project's own."""
    return default_facts() | {
        "Built on": dependency_versions(),
        "Docs": DOCS_URL,
    }


BRAND_SCREEN = VersionScreen(
    logo=render_logo(),
    tagline=TAGLINE,
    facts=brand_facts,
)
"""Click Extra's own `--version` screen.

Mounted on the `click-extra` CLI, and the shape a CLI of your own would copy:

```{code-block} python
from functools import partial
from click_extra import group
from click_extra.commands import default_params

@group(params=partial(default_params, screen=BRAND_SCREEN))
def cli():
    pass
```

The mark is rendered once, here, since it never changes. {func}`brand_facts` is
passed uncalled so its values are read when `--version` is, not when this module is
imported — the habit that keeps a costlier fact from being charged to every
invocation.
"""
