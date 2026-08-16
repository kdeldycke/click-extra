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
"""Test the terminal rendition of the Click Extra brand mark.

The layout it is drawn into belongs to {class}`~click_extra.version.VersionScreen`
and is tested in `test_version.py`. What is left here is the artwork: its geometry,
its palette, and that it survives losing its color.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from boltons.strutils import strip_ansi

from click_extra.logo import (
    BRAND_SCREEN,
    CUBE,
    CUBE_FACES,
    FACE_COLORS,
    LOGO_LINES,
    LOGO_WIDTH,
    render_logo,
)

ARTWORK = Path(__file__).parent.parent / "docs" / "assets" / "logo-square.svg"
"""The SVG the terminal rendition's palette is copied from.

Present in a source checkout and in the sdist, absent from the wheel, which is the
whole reason `click_extra.logo` repeats the colors instead of reading them.
"""


def test_cube_and_faces_line_up():
    assert len(CUBE) == len(CUBE_FACES)
    assert len({len(row) for row in CUBE} | {len(row) for row in CUBE_FACES}) == 1
    for art_row, face_row in zip(CUBE, CUBE_FACES):
        for char, face in zip(art_row, face_row):
            assert face in ".tlr"
            # Every painted character names a face, and every named face paints.
            assert (char == " ") == (face == ".")


def test_every_cube_declares_three_faces():
    assert len(FACE_COLORS) == sum((3, 2, 1))
    for faces in FACE_COLORS:
        assert set(faces) == {"t", "l", "r"}
        for channels in faces.values():
            assert len(channels) == 3
            assert all(0 <= channel <= 255 for channel in channels)


def test_rendered_logo_fits_its_declared_box():
    """Every line is exactly as wide as declared, trailing blanks included.

    {class}`~click_extra.version.VersionScreen` pads a ragged mark for us, so this
    is not what keeps the screen aligned. It is what keeps the two declarations
    honest: {data}`~click_extra.logo.LOGO_WIDTH` and
    {data}`~click_extra.logo.LOGO_LINES` are computed from the lattice rather than
    from the render, and nothing else would notice the two drifting apart.
    """
    lines = render_logo()
    assert len(lines) == LOGO_LINES
    ragged = {
        index: len(strip_ansi(line))
        for index, line in enumerate(lines)
        if len(strip_ansi(line)) != LOGO_WIDTH
    }
    assert not ragged, f"lines not {LOGO_WIDTH} columns wide: {ragged}"
    assert BRAND_SCREEN.width == LOGO_WIDTH


def test_logo_reads_without_color():
    """The mark's structure is in its characters, not its colors.

    Strip every escape sequence and the six cubes are still there, which a
    half-block rendition of the same mark could not promise. That is what makes the
    screen's color gate a courtesy to machine readers rather than a legibility
    requirement.
    """
    plain = [strip_ansi(line) for line in render_logo()]
    assert set("".join(plain)) <= set(" /\\_")
    # Six lids, one per cube, each drawn as its own run of underscores.
    lids = sum(len(re.findall(r"__", line)) for line in plain[:: len(CUBE)])
    assert lids == len(FACE_COLORS)


def artwork_ribbons() -> list[tuple[str, str]]:
    """Every ribbon of the SVG, as (color, the isometric plane it outlines).

    A ribbon tracing a cube's top rhombus has only diagonal segments. One tracing a
    side face has a vertical segment too, and the sign of its diagonal says which
    side: descending to the right is the left-hand face, rising to the right the
    right-hand one.
    """
    svg = ARTWORK.read_text(encoding="utf-8")
    fills = dict(re.findall(r"\.(st\d+)\{fill:#([0-9A-Fa-f]{6});\}", svg))
    out = []
    for element in re.finditer(r"<polygon\b(?P<attrs>[^>]*?)/>", svg, re.DOTALL):
        attrs = element.group("attrs")
        css_class = re.search(r'class="(st\d+)"', attrs)
        coordinates = re.search(r'points="([^"]+)"', attrs)
        assert css_class and coordinates, f"unparsable ribbon: {attrs}"
        numbers = [float(n) for n in re.findall(r"-?[\d.]+", coordinates.group(1))]
        points = list(zip(numbers[0::2], numbers[1::2]))

        slopes = []
        upright = False
        for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
            if abs(bx - ax) < 1e-6:
                upright = upright or abs(by - ay) > 1.0
            elif abs(by - ay) > 1e-6:
                slopes.append((by - ay) / (bx - ax))
        if not upright:
            plane = "t"
        else:
            plane = "l" if max(slopes, key=abs) > 0 else "r"
        out.append((fills[css_class.group(1)].upper(), plane))
    return out


@pytest.mark.skipif(not ARTWORK.exists(), reason="artwork not shipped in the wheel")
def test_logo_palette_tracks_the_artwork():
    """Every color the rendition uses is a ribbon of the SVG, on the same plane.

    Guards the copy in `click_extra.logo`: runtime code cannot open the SVG, so
    nothing but this test notices when the artwork is recolored and the terminal mark
    keeps painting the old palette. The artwork outlines each face with two ribbons
    and the rendition keeps one of them, so this checks containment rather than
    equality — and checks the plane too, which is what catches a lid color
    transcribed onto a wall.
    """
    ribbons = artwork_ribbons()
    assert len(ribbons) == len(FACE_COLORS) * 3 * 2

    planes_by_color: dict[str, set[str]] = {}
    for color, plane in ribbons:
        planes_by_color.setdefault(color, set()).add(plane)

    declared = [
        (f"{r:02X}{g:02X}{b:02X}", face)
        for faces in FACE_COLORS
        for face, (r, g, b) in faces.items()
    ]
    assert len({color for color, _ in declared}) == len(declared)
    for color, face in declared:
        assert color in planes_by_color, f"{color} is not a ribbon of the artwork"
        assert face in planes_by_color[color], (
            f"{color} outlines the {planes_by_color[color]} plane, "
            f"not {face!r} as declared"
        )
