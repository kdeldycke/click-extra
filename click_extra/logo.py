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

The mark of `docs/assets/logo-square.svg` is six cubes stacked three-two-one. Here
they are rebuilt as flat shaded solids — one color per face, no outline anywhere —
and painted with half blocks, two sub-pixels to a terminal line.

Flat faces are what let one palette serve a light terminal and a dark one. An
outlined mark carries its shape in the outline, so every stroke has to out-contrast
whatever sits behind it, and the artwork's own palette spans too wide a range for
that: six of its colors vanish on white, two more on black. A flat mark carries its
shape in the *difference between its three planes*, which no background can touch,
leaving only the silhouette to keep its distance. That fits comfortably in the middle
of the range, which is where {data}`FACE_COLORS` sits.

```{caution}
The mark's structure is carried by *color*: strip the ANSI codes and it collapses
into one silhouette. {class}`~click_extra.version.VersionScreen` therefore only draws
it where color reaches the output, falling back to the plain `--version` line
everywhere else — which is also the form machine readers parse.
```
"""

from __future__ import annotations

from click import style

from .version import VersionScreen, default_facts, dependency_versions

DOCS_URL = "https://kdeldycke.github.io/click-extra"
"""Canonical documentation host, advertised on the version screen."""

TAGLINE = "Drop-in replacement for Click and Cloup"
"""What the project is, spelled out under the program name."""

UNIT = 2
"""Scale of the whole mark, in sub-pixels.

Every dimension is a multiple of it, so the mark is `12 * UNIT` columns wide and
`5 * UNIT` lines tall. Two is the largest that still seats the mark beside the
version screen's facts inside eighty columns: 24 columns of mark, three of gutter and
fifty of facts comes to 77. Three would need 89, and the screen would decline to draw
itself on any standard terminal.
"""

LEVELS: tuple[tuple[int, int], ...] = (
    (0, 0),
    (0, 1),
    (0, 2),
    (1, 0),
    (1, 1),
    (2, 0),
)
"""Each cube's (row, column) up the pyramid, bottom row first.

Also the order {data}`FACE_COLORS` is written in, and the order the mark is painted
in: a cube resting on two others has to be laid down after them.
"""

BRAND_HUES: tuple[int, ...] = (41, 94, 306, 279, 210, 156)
"""Each cube's hue in degrees, in {data}`LEVELS` order.

Read off the ribbon that outlines each cube's top face in the artwork. The mark has
no per-cube hue of its own — cube one alone carries gold, green and olive across its
six ribbons — so this is a reading of the artwork rather than a recovery of it. It
keeps the terminal mark recognizably the same six colors people already associate
with the logo, which an evenly spaced spectrum would not.
"""

SATURATION = 0.62
"""HLS saturation shared by every face. Vivid enough to tell six hues apart."""

PLANE_LUMINANCE: dict[str, float] = {"t": 0.36, "r": 0.22, "l": 0.13}
"""WCAG relative luminance per plane: the lid, then the two walls.

Chosen as a band rather than per color, so every hue is equally far from both
backgrounds. The floor of the band is what the mark shows against white and the
ceiling what it shows against black, which is why it sits in the middle: the widest
band tried reads beautifully on black and falls to 1.74:1 on white.

The 2.25:1 it leaves between a cube's lid and its dark wall is well past what an eye
needs to see a facet, and it survives every dichromacy, planes differing in luminance
alone.
"""

FACE_COLORS: tuple[dict[str, str], ...] = (
    {"t": "#CB9A30", "r": "#A37B26", "l": "#7F611E"},
    {"t": "#66B52A", "r": "#519122", "l": "#40721B"},
    {"t": "#E17FD8", "r": "#D344C6", "l": "#AD28A1"},
    {"t": "#C58CE4", "r": "#AE5ED9", "l": "#9730CC"},
    {"t": "#70A7DD", "r": "#3985D0", "l": "#2767A8"},
    {"t": "#2BB87F", "r": "#229265", "l": "#1B724F"},
)
"""Each cube's three face colors, in {data}`LEVELS` order.

Derived, not picked: every entry is its cube's {data}`BRAND_HUES` hue at
{data}`SATURATION`, taken to the luminance its plane declares in
{data}`PLANE_LUMINANCE`. Written out rather than computed at import so the palette
stays greppable and a designer can hand-tune one value;
`test_palette_follows_its_derivation` fails if a tuned value drifts off the system.

Emitted as 24-bit color. The 256-color cube cannot separate all eighteen, and the
usual reason to prefer it does not apply: no touching pair of faces collides there,
so a terminal that downsamples still shows six distinct cubes.
"""

Point = tuple[int, int]
Face = list[Point]
RGB = tuple[int, int, int]

_UPPER = "▀"
_LOWER = "▄"
_FULL = "█"


def geometry() -> dict[str, int]:
    """One cube's dimensions, in sub-pixels.

    A lid four units wide and two tall is 2:1 dimetric, and the smallest such rhombus
    whose half-height is a whole number — which the row pitch needs. The body matches
    the lid's width over two, making every box a true cube.
    """
    return {
        "width": 4 * UNIT,
        "lid": 2 * UNIT,
        "half_lid": UNIT,
        "body": 2 * UNIT,
        # A cube resting on two others meets them where their lids meet, which puts
        # its floor exactly half a lid below their rims. Any other pitch would show
        # the background between the rows.
        "pitch": 3 * UNIT,
    }


def size() -> tuple[int, int]:
    """The mark's footprint in sub-pixels, columns by rows."""
    box = geometry()
    return 3 * box["width"], box["lid"] + box["body"] + 2 * box["pitch"]


LOGO_WIDTH = size()[0]
"""Columns the mark occupies."""

LOGO_LINES = size()[1] // 2
"""Terminal lines the mark renders to, two sub-pixel rows making one."""


def faces() -> list[tuple[int, str, Face]]:
    """Every visible face, bottom row first, as whole-sub-pixel polygons.

    2:1 dimetric rather than the artwork's 30 degrees, and integer vertices rather
    than a sampled rendering, for the same reason: a 30-degree edge advances 1.732
    sub-pixels per row, which no grid can hold, so it comes out as a stair of uneven
    treads that the eye reads as fraying. Two across for every one down tiles a
    square grid exactly, and every tread is then the same.
    """
    box = geometry()
    _, height = size()
    out: list[tuple[int, str, Face]] = []
    for slot, (level, column) in enumerate(LEVELS):
        centre = box["width"] * column + 2 * UNIT * level + 2 * UNIT
        near_y = height - box["body"] - box["pitch"] * level

        far = (centre, near_y - box["lid"])
        left = (centre - 2 * UNIT, near_y - box["half_lid"])
        right = (centre + 2 * UNIT, near_y - box["half_lid"])
        near = (centre, near_y)
        floor = box["body"]

        out.append((slot, "t", [far, right, near, left]))
        out.append((
            slot,
            "r",
            [near, right, (right[0], right[1] + floor), (near[0], near[1] + floor)],
        ))
        out.append((
            slot,
            "l",
            [left, near, (near[0], near[1] + floor), (left[0], left[1] + floor)],
        ))
    return out


def _inside(point: tuple[float, float], polygon: Face) -> bool:
    """Ray-casting point-in-polygon, counting crossings to the right of `point`."""
    x, y = point
    hit = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            hit = not hit
    return hit


def sub_pixels() -> list[list[RGB | None]]:
    """The mark as a grid of flat colors, hit-tested against the face polygons.

    Rasterizing the mark and reading pixels back would hand the antialiaser a say in
    the palette: every boundary it smooths mints a color belonging to neither face,
    and a rendition this size comes back carrying over a hundred of them. Testing
    each sub-pixel's centre against the polygons keeps it to the eighteen declared,
    three per cube, which is what makes the edges read as steps rather than smudge.
    """
    width, height = size()
    # Nearest face first, so the paint order becomes the hit-test order and a cube
    # resting on another wins over the lid it covers.
    ordered = list(reversed(faces()))
    palette = {
        (slot, plane): tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
        for slot, planes in enumerate(FACE_COLORS)
        for plane, value in planes.items()
    }

    grid: list[list[RGB | None]] = []
    for row in range(height):
        line: list[RGB | None] = []
        for column in range(width):
            centre = (column + 0.5, row + 0.5)
            for slot, plane, polygon in ordered:
                if _inside(centre, polygon):
                    line.append(palette[(slot, plane)])  # type: ignore[arg-type]
                    break
            else:
                line.append(None)
        grid.append(line)
    return grid


def render_logo() -> tuple[str, ...]:
    """Paint the mark into styled lines, each exactly {data}`LOGO_WIDTH` wide.

    A cell whose two sub-pixels carry different colors paints the top one as
    foreground over the bottom one as background, which is what fits two independent
    colors on one line. Runs of cells sharing a color pair are styled together rather
    than one escape sequence per character, keeping the mark from tripling in size.

    Trailing blanks are kept: {class}`~click_extra.version.VersionScreen` pads a
    ragged logo for us, but a mark that arrives square costs it nothing to measure.
    """
    grid = sub_pixels()
    lines = []
    for top in range(0, len(grid) - 1, 2):
        line = ""
        run = ""
        current: tuple[RGB | None, RGB | None] = (None, None)
        for over, under in zip(grid[top], grid[top + 1]):
            pair: tuple[RGB | None, RGB | None]
            if over is None and under is None:
                char, pair = " ", (None, None)
            elif under is None:
                char, pair = _UPPER, (over, None)
            elif over is None:
                char, pair = _LOWER, (under, None)
            elif over == under:
                char, pair = _FULL, (over, None)
            else:
                char, pair = _UPPER, (over, under)
            if pair != current:
                line += _paint(run, current)
                run, current = "", pair
            run += char
        lines.append(line + _paint(run, current))
    return tuple(lines)


def _paint(run: str, colors: tuple[RGB | None, RGB | None]) -> str:
    """Style a run of cells, leaving fully transparent ones as bare spaces.

    Transparent runs must not go through `style()`: it would wrap them in a reset
    sequence, which costs bytes and, worse, cancels nothing while looking like it
    might.
    """
    if not run or colors == (None, None):
        return run
    return style(run, fg=colors[0], bg=colors[1])


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

The mark is painted once, here, since it never changes. {func}`brand_facts` is passed
uncalled so its values are read when `--version` is, not when this module is imported
— the habit that keeps a costlier fact from being charged to every invocation.
"""
