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
and is tested in `test_version.py`. What is checked here is the mark itself: that its
geometry lands on the grid, that its palette follows the system it claims to, and
that both survive the terminal.
"""

from __future__ import annotations

import colorsys
import importlib.metadata
import re
from pathlib import Path

import pytest
from boltons.strutils import strip_ansi

from click_extra.logo import (
    BRAND_HUES,
    BRAND_SCREEN,
    FACE_COLORS,
    LEVELS,
    LOGO_LINES,
    LOGO_WIDTH,
    PLANE_LUMINANCE,
    SATURATION,
    UNIT,
    faces,
    geometry,
    render_logo,
    size,
    sub_pixels,
)
from click_extra.styling import _nearest_256, _relative_luminance

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

SILHOUETTE_FLOOR = 2.0
"""Contrast a face must keep against either background to hold its silhouette.

Below the 3:1 WCAG asks of non-text graphics, deliberately: that threshold assumes a
shape whose only cue is its edge against the page, and this one also has two
neighbouring planes to be read against. What it rules out is a face disappearing.
"""


def contrast(a, b) -> float:
    high, low = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def rgb(value: str) -> tuple[int, int, int]:
    channels = (int(value[i : i + 2], 16) for i in (1, 3, 5))
    return tuple(channels)  # type: ignore[return-value]


ARTWORK = Path(__file__).parent.parent / "docs" / "assets" / "logo-square.svg"
"""The SVG the terminal rendition shares its palette with.

Present in a source checkout and in the sdist, absent from the wheel, which is the
whole reason `click_extra.logo` repeats the colors instead of reading them.
"""

PLANE_NAMES = {"top": "t", "left": "l", "right": "r"}
"""How the artwork's CSS spells the planes `click_extra.logo` keys by initial."""


@pytest.mark.skipif(not ARTWORK.exists(), reason="artwork not shipped in the wheel")
def test_palette_matches_the_artwork():
    """The terminal mark and the artwork paint the same eighteen colors.

    They were separate palettes while the artwork was outlined and the terminal had
    to compensate for it. Both being flat-shaded, there is no longer any reason for
    them to differ — and nothing but this notices when one is recolored alone.
    """
    rules = re.findall(
        r"\.cube(\d)-(top|left|right)\{fill:(#[0-9A-Fa-f]{6});\}",
        ARTWORK.read_text(encoding="utf-8"),
    )
    assert len(rules) == len(LEVELS) * 3, f"artwork declares {len(rules)} faces"

    artwork = {
        (int(slot) - 1, PLANE_NAMES[plane]): value.upper()
        for slot, plane, value in rules
    }
    declared = {
        (slot, plane): value.upper()
        for slot, planes in enumerate(FACE_COLORS)
        for plane, value in planes.items()
    }
    assert artwork == declared


def test_geometry_lands_on_whole_sub_pixels():
    """Every vertex is an integer, so the fill has nothing to round.

    A polygon landing between sub-pixels is what turns a straight edge into an
    irregular stair, and no amount of resolution fixes it.
    """
    for slot, plane, polygon in faces():
        for x, y in polygon:
            assert x == int(x) and y == int(y), f"cube {slot} {plane} is off-grid"


def test_edges_advance_two_sub_pixels_per_row():
    """The lid edges are 2:1, which is the whole reason for the projection.

    The artwork is a true 30-degree isometric, whose edges advance 1.732 sub-pixels
    per row. No grid holds that, so it comes out as a stair of alternating two- and
    four-wide treads that reads as fraying. Two across per one down tiles exactly.
    """
    box = geometry()
    for slot, plane, polygon in faces():
        if plane != "t":
            continue
        far, right, _near, left = polygon
        for corner in (right, left):
            across = abs(corner[0] - far[0])
            down = abs(corner[1] - far[1])
            assert across == 2 * down, f"cube {slot} lid edge is {across}:{down}"
        assert right[0] - left[0] == box["width"]


def test_rows_are_seated_not_floating():
    """A cube rests on the two below it, rather than hovering over them.

    The artwork's own row pitch is wider than a stack allows, which shows the
    background between the rows. A cube meets the pair beneath it where their lids
    meet, exactly half a lid below their rims.
    """
    box = geometry()
    assert box["pitch"] == box["body"] + box["half_lid"]


def test_mark_fits_its_declared_box():
    """Every line is exactly as wide as declared, trailing blanks included."""
    width, height = size()
    assert (width, height // 2) == (LOGO_WIDTH, LOGO_LINES)
    assert height % 2 == 0, "half blocks pair two rows, so the count must be even"

    lines = render_logo()
    assert len(lines) == LOGO_LINES
    ragged = {
        index: len(strip_ansi(line))
        for index, line in enumerate(lines)
        if len(strip_ansi(line)) != LOGO_WIDTH
    }
    assert not ragged, f"lines not {LOGO_WIDTH} columns wide: {ragged}"


def test_palette_follows_its_derivation():
    """Every face sits at its cube's hue and its plane's luminance.

    The palette is written out rather than computed, so it stays greppable and a
    designer can tune one value. Nothing but this notices a tuned value drifting off
    the system it claims to belong to.
    """
    for slot, planes in enumerate(FACE_COLORS):
        assert set(planes) == set(PLANE_LUMINANCE)
        for plane, value in planes.items():
            color = rgb(value)
            hue, _light, sat = colorsys.rgb_to_hls(*(c / 255 for c in color))
            assert round(hue * 360) == pytest.approx(BRAND_HUES[slot], abs=1), (
                f"cube {slot} {plane} is hue {round(hue * 360)}, not {BRAND_HUES[slot]}"
            )
            assert sat == pytest.approx(SATURATION, abs=0.02)
            assert _relative_luminance(color) == pytest.approx(
                PLANE_LUMINANCE[plane], abs=0.01
            ), f"cube {slot} {plane} is off its plane's luminance"


def test_every_cube_shows_exactly_its_three_faces():
    """The grid carries the eighteen declared colors and nothing between them.

    Rasterizing the mark and reading pixels back would let the antialiaser mint
    colors belonging to no face — over a hundred of them at this size. Hit-testing
    the polygons is what keeps the count to what the palette declares.
    """
    used = {cell for row in sub_pixels() for cell in row if cell is not None}
    declared = {rgb(value) for planes in FACE_COLORS for value in planes.values()}
    assert used == declared
    assert len(declared) == len(LEVELS) * 3

    for slot, planes in enumerate(FACE_COLORS):
        present = {rgb(value) for value in planes.values()} & used
        assert len(present) == 3, f"cube {slot} shows {len(present)} of its 3 faces"


@pytest.mark.parametrize("background", (WHITE, BLACK), ids=("white", "black"))
def test_mark_keeps_its_distance_from_both_backgrounds(background):
    """One palette has to serve a light terminal and a dark one.

    Flat faces are what make that possible: the shape lives in the difference between
    a cube's three planes, so only the silhouette has to clear the background, and
    that fits in the middle of the range.
    """
    faint = {
        value: round(contrast(rgb(value), background), 2)
        for planes in FACE_COLORS
        for value in planes.values()
        if contrast(rgb(value), background) < SILHOUETTE_FLOOR
    }
    assert not faint, f"below {SILHOUETTE_FLOOR}:1 on this background: {faint}"


def test_neighbouring_faces_survive_a_256_color_terminal():
    """No two faces that touch collapse onto the same palette index.

    The mark is emitted in 24-bit color, so a terminal that downsamples is the
    degraded case rather than the target. It still has to show six cubes.
    """
    grid = sub_pixels()
    touching = set()
    for row, line in enumerate(grid):
        for column, here in enumerate(line):
            if here is None:
                continue
            for down, across in ((0, 1), (1, 0)):
                y, x = row + down, column + across
                if y >= len(grid) or x >= len(line):
                    continue
                there = grid[y][x]
                if there is not None and there != here:
                    touching.add(tuple(sorted((here, there))))

    merged = [
        pair for pair in touching if _nearest_256(*pair[0]) == _nearest_256(*pair[1])
    ]
    assert not merged, f"pairs that collide once downsampled: {merged}"


def _is_released(distribution: str) -> bool:
    """Is *distribution* an installed release rather than a branch build?

    A dependency installed from a Git branch reports a PEP 440 development
    release (`.devN`) or carries a local version identifier (`+<hash>`), either
    of which is longer than the release string it stands in for.
    """
    version = importlib.metadata.version(distribution)
    return ".dev" not in version and "+" not in version


SCREEN_DEPENDENCIES_ARE_RELEASES = all(map(_is_released, ("click", "cloup")))
"""Whether the dependencies the version screen names are installed releases.

The screen's `Built on` row prints the installed Click and Cloup versions, so a
branch build widens it past the docs URL that is otherwise the longest row. The
width below is a design constraint on the configuration this project *ships*,
and the screen already falls back to the plain message when it does not fit, so
asserting it against a dev string measures upstream's version scheme rather than
this package.
"""


@pytest.mark.skipif(
    not SCREEN_DEPENDENCIES_ARE_RELEASES,
    reason="A branch-built Click or Cloup widens the screen's `Built on` row.",
)
def test_screen_fits_an_eighty_column_terminal():
    """The mark is sized so the screen it decorates can actually be drawn.

    A wider mark is not a bigger logo, it is no logo: the screen measures itself
    against the terminal and falls back to the plain message when it does not fit.
    """
    rows = BRAND_SCREEN.rows("click-extra", "8.10.0", {})
    needed = (
        BRAND_SCREEN.width
        + len(BRAND_SCREEN.gutter)
        + max(len(plain) for plain, _ in rows)
    )
    assert needed <= 80, f"the screen wants {needed} columns"
    assert BRAND_SCREEN.width == 12 * UNIT
