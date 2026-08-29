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
"""The bundled catalog of terminal presets a capture can be drawn as.

A capture is a picture of a terminal, and terminals do not look alike. A preset
carries the five things that make one recognizable, so a reader placing the
image knows which desktop it came from:

- the **window decorations**, three round buttons on the left for macOS, three
  glyphs on the right for Windows, a single one for GNOME;
- the **palette** its colors resolve against, which is what turns a bright blue
  into Campbell's `#3B78FF` or Tango's `#729FCF`;
- the **font** the terminal ships with;
- the **prompt** its shell draws, `$` against `PS C:\\>`;
- the **cursor** it draws, a block everywhere but Windows Terminal, which
  opens on a bar.

None of it is applied unless asked for: a capture with no preset keeps the
renderer's own neutral window, which is what every image in this project's
documentation is drawn as.

```{caution}
A palette here is a *published default*, transcribed from the scheme each
terminal ships (Campbell and One Half Light for Windows Terminal, Basic and Pro
for Apple's Terminal, Tango for GNOME), and cross-checked against
[iTerm2-Color-Schemes](https://github.com/mbadolato/iTerm2-Color-Schemes). It is
what the terminal looks like out of the box, not what any given reader has
configured theirs to.
```
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Final


class TerminalPalette(NamedTuple):
    """The colors a terminal resolves a capture's ANSI codes against.

    The 16 `ansi` entries are the standard palette in the canonical order:
    black, red, green, yellow, blue, magenta, cyan, white, then the same eight
    in their bright variants.
    """

    background: str
    """Color behind the text, as CSS spells it."""

    foreground: str
    """Color of the text a CLI leaves unstyled."""

    ansi: tuple[str, ...]
    """The 16 palette entries, normal eight first."""

    titlebar: str
    """Color of the strip the window's title and buttons sit in.

    A window's chrome, which the desktop paints rather than the terminal: a
    shade off the background, so the top of the window reads as a window rather
    than as the first line of output.
    """


class WindowButtons(NamedTuple):
    """The decorations a terminal draws in its title bar.

    Two shapes cover the desktops: macOS draws filled circles on the left,
    Windows and GNOME draw glyphs on the right. `None` in either field leaves
    that half undrawn, which is what a bare window asks for.
    """

    circles: tuple[str, ...] = ()
    """Colors of the round buttons drawn from the left, in order."""

    glyphs: str = ""
    """Characters drawn from the right, closing button last."""


MACOS_BUTTONS: Final = WindowButtons(circles=("#ff5f57", "#febc2e", "#28c840"))
"""Close, minimize and zoom, the three round buttons of an Aqua title bar."""

WINDOWS_BUTTONS: Final = WindowButtons(glyphs="\uff0d\u25a1\u2715")
"""Minimize, maximize and close, the three glyphs of a Windows title bar."""

GNOME_BUTTONS: Final = WindowButtons(glyphs="\u2715")
"""The single close button a GNOME window carries by default."""


class CursorShape(Enum):
    """The shape a terminal draws its cursor as.

    The three every terminal offers, under the names they are configured by.
    Which one a terminal picks out of the box is part of what makes it
    recognizable, so a preset states it alongside the buttons and the font.
    """

    BLOCK = "block"
    """A filled cell, the shape a terminal draws unless told otherwise."""

    BAR = "bar"
    """A thin upright line on the cell's leading edge."""

    UNDERLINE = "underline"
    """A thin line along the cell's bottom edge."""


class Cursor(NamedTuple):
    """The cursor a capture draws, and how it behaves.

    Passed to {func}`~click_extra.screenshot.render_svg` to draw one at all: a
    capture shows no cursor unless asked, which is what keeps an image taken
    before this existed byte-identical to the one taken after.

    ```{note}
    Where the cursor *is* is never stated here. A frame's text already says so,
    see {func}`~click_extra.screenshot.cursor_cell`, so a caller states what the
    cursor looks like and the picture answers for the rest.
    ```
    """

    shape: CursorShape | None = None
    """How it is drawn. `None` takes the shape the terminal preset names."""

    blink: float = 1.0
    """Seconds one blink takes, half of it lit. Zero draws a steady cursor.

    A second is what the desktops settle around, and it is deliberately no
    factor of any frame interval: the two clocks drift against each other
    across a loop, which is what a terminal showing a cursor over a running
    command looks like.

    ```{caution}
    Blinking is motion, and a reader may have asked their system for less of
    it. The rule sits behind
    {data}`~click_extra.screenshot.REDUCED_MOTION_QUERY` like every other
    animation this package emits, which leaves the cursor lit and still. That
    guard is also what answers [WCAG 2.2.2](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide),
    which asks that anything blinking past five seconds can be stopped.
    ```
    """

    color: str | None = None
    """Paint it is drawn with. `None` takes the terminal's foreground."""


APPLE_ANSI: Final = (
    "#000000",
    "#c23621",
    "#25bc24",
    "#adad27",
    "#492ee1",
    "#d338d3",
    "#33bbc8",
    "#cbcccd",
    "#818383",
    "#fc391f",
    "#31e722",
    "#eaec23",
    "#5833ff",
    "#f935f8",
    "#14f0f0",
    "#e9ebeb",
)
"""Palette shared by Apple Terminal's `Basic` and `Pro` schemes."""

CAMPBELL_ANSI: Final = (
    "#0c0c0c",
    "#c50f1f",
    "#13a10e",
    "#c19c00",
    "#0037da",
    "#881798",
    "#3a96dd",
    "#cccccc",
    "#767676",
    "#e74856",
    "#16c60c",
    "#f9f1a5",
    "#3b78ff",
    "#b4009e",
    "#61d6d6",
    "#f2f2f2",
)
"""Palette of `Campbell`, the scheme Windows Terminal opens with."""

ONE_HALF_LIGHT_ANSI: Final = (
    "#383a42",
    "#e45649",
    "#50a14f",
    "#c18301",
    "#0184bc",
    "#a626a4",
    "#0997b3",
    "#fafafa",
    "#4f525d",
    "#df6c75",
    "#98c379",
    "#e4c07a",
    "#61afef",
    "#c577dd",
    "#56b5c1",
    "#ffffff",
)
"""Palette of `One Half Light`, the light scheme Windows Terminal ships."""

TANGO_ANSI: Final = (
    "#2e3436",
    "#cc0000",
    "#4e9a06",
    "#c4a000",
    "#3465a4",
    "#75507b",
    "#06989a",
    "#d3d7cf",
    "#555753",
    "#ef2929",
    "#8ae234",
    "#fce94f",
    "#729fcf",
    "#ad7fa8",
    "#34e2e2",
    "#eeeeec",
)
"""Palette of Tango, which GNOME Terminal ships in a dark and a light dress."""


class TerminalPreset(NamedTuple):
    """A terminal a capture can be drawn as.

    Pass one to `click-extra screenshot --preset`, or to a `click:run` block as
    `:screenshot-preset:`. Anything stated alongside it wins: a preset picks the
    defaults, it does not lock them.
    """

    label: str
    """Human name of the terminal, for the documentation and the help screen."""

    buttons: WindowButtons
    """Decorations drawn in the title bar, see {class}`WindowButtons`."""

    radius: int
    """How round the window's corners are, in pixels."""

    prompt: str
    """Sigil the terminal's usual shell draws before a command."""

    cursor: CursorShape
    """Shape it draws its cursor as, see {class}`CursorShape`.

    Only consulted by a capture that asked for a cursor: a preset picks the
    shape, it never turns one on.
    """

    font_stack: str
    """Fonts the capture asks for, the terminal's own first.

    Nothing is embedded, so a reader without the family falls back down the
    list. Which is why each ends with the same generic `monospace` a browser
    always resolves.
    """

    dark: TerminalPalette
    """Colors the terminal shows on its dark scheme."""

    light: TerminalPalette
    """Colors it shows on its light one."""


PRESETS: Final[dict[str, TerminalPreset]] = {
    "linux": TerminalPreset(
        label="GNOME Terminal",
        buttons=GNOME_BUTTONS,
        radius=6,
        prompt="$",
        cursor=CursorShape.BLOCK,
        font_stack="'Ubuntu Mono', 'DejaVu Sans Mono', monospace",
        dark=TerminalPalette("#2e3436", "#d3d7cf", TANGO_ANSI, "#303030"),
        light=TerminalPalette("#ffffff", "#2e3436", TANGO_ANSI, "#ebebeb"),
    ),
    "macos": TerminalPreset(
        label="Apple Terminal",
        buttons=MACOS_BUTTONS,
        radius=10,
        prompt="$",
        cursor=CursorShape.BLOCK,
        font_stack="'SF Mono', Menlo, Monaco, monospace",
        dark=TerminalPalette("#000000", "#f2f2f2", APPLE_ANSI, "#3a3a3a"),
        light=TerminalPalette("#ffffff", "#000000", APPLE_ANSI, "#e9e9e9"),
    ),
    "plain": TerminalPreset(
        label="No terminal at all",
        buttons=WindowButtons(),
        radius=0,
        prompt="$",
        cursor=CursorShape.BLOCK,
        font_stack="'Fira Code', 'Cascadia Code', Menlo, Consolas, monospace",
        dark=TerminalPalette("#292929", "#c5c8c6", TANGO_ANSI, "#292929"),
        light=TerminalPalette("#ffffff", "#000000", TANGO_ANSI, "#ffffff"),
    ),
    "windows": TerminalPreset(
        label="Windows Terminal",
        buttons=WINDOWS_BUTTONS,
        radius=0,
        prompt="PS C:\\>",
        cursor=CursorShape.BAR,
        font_stack="'Cascadia Code', 'Cascadia Mono', Consolas, monospace",
        dark=TerminalPalette("#0c0c0c", "#cccccc", CAMPBELL_ANSI, "#202020"),
        light=TerminalPalette("#fafafa", "#383a42", ONE_HALF_LIGHT_ANSI, "#f3f3f3"),
    ),
}
"""Every terminal a capture can be drawn as, alphabetically.

`plain` is the odd one out: it mimics no desktop, dropping the buttons and the
rounded corners for a capture that has to read as a block of output rather than
as a window, on a slide or in a paper.
"""
