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
r"""The bundled catalog of terminal presets a capture can be drawn as.

A capture is a picture of a terminal, and terminals do not look alike. A preset
carries the five things that make one recognizable, so a reader placing the
image knows which desktop it came from:

- the **window decorations**, three round buttons on the left for macOS, three
  glyphs on the right for Windows, a single one for GNOME;
- the **palette** its colors resolve against, which is what turns a bright blue
  into Campbell's `#3B78FF` or Tango's `#729FCF`;
- the **font** the terminal ships with;
- the **prompt** its shell draws, `$` against `PS C:\>`;
- the **cursor** it draws, a block everywhere but Windows Terminal, which
  opens on a bar.

None of it is applied unless asked for: a capture with no preset keeps the
renderer's own neutral window. That window is described here too:
{data}`DEFAULT_PRESET` is the terminal it resolves its colors against,
{class}`~click_extra.color.TerminalBackground` names the dark or light chrome a
capture is drawn on, and {func}`resolve_palette` answers the palette any preset
shows on either.
{class}`Chrome` draws the rest of the window: its frame, shadow, margins and
credit line.

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

from dataclasses import dataclass, fields, replace
from enum import Enum
from typing import NamedTuple

from ..color import TerminalBackground

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Final, TypedDict

    class ChromeArguments(TypedDict, total=False):
        """The {class}`Chrome` fields, taken one by one as keyword arguments."""

        border: str | None
        border_width: int
        radius: int | None
        backdrop: str
        shadow: str | None
        margin: int
        padding: int
        opacity: float
        watermark: str
        watermark_color: str | None


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
    Windows and GNOME draw glyphs on the right. An empty field leaves that half
    undrawn, which is what a bare window asks for.
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

    Passed to {func}`~click_extra.capture.svg.render_svg` to draw one at all: a
    capture shows no cursor unless asked.

    ```{note}
    Where the cursor *is* is never stated here. A frame's text already says so,
    see {func}`~click_extra.capture.svg.cursor_cell`, so a caller states what the
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
    {data}`~click_extra.capture.svg.REDUCED_MOTION_QUERY` like every other
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


DEFAULT_PRESET: Final = PRESETS["plain"]
"""Terminal a capture with no `--preset` is drawn as.

`plain` mimics no desktop, which is what a capture wearing no decoration should
resolve its colors against. Naming it here is what keeps the two formats looking
like the same terminal, and keeps one catalog answering for every palette a
capture can use: without it the default colors would be a second set of literals
free to drift from the one the presets publish.
"""

CAPTURE_FONT_STACK: Final = DEFAULT_PRESET.font_stack
"""Monospaced fonts a capture asks for, best first.

Nothing is embedded and nothing is fetched, so both formats set the text in the
first family the reader already has, and a capture renders the same offline, on
a page forbidding third-party requests, and in a viewer that speaks no CSS
`@font-face`.

Family names are single-quoted on purpose: this lands in a double-quoted
`style` attribute, which a double quote here would terminate early.

```{note}
Not embedding is a decision, not an omission: a subsetted font would ship inside
this package, and redistribute someone else's font under its own license. The
bytes are small; the license management is not worth a terminal picture. The
JuliaMono subset under `docs/_static/` does not change this: it sets the
documentation's own HTML, where a stylesheet reaches the text, and reusing it in
a capture would be that same redistribution.

The fallback has a cost. A stock macOS falls through to Menlo, which carries
no Braille and none of the Mathematical Operators the spinner catalog draws, so
those resolve to the proportional Apple Symbols: nearly a third of the spinner
tiles draw wider than their column, and the window's clip cuts the overflow. A
reader with either of the first two families sees none of it, and emoji stay out
of reach of every monospaced font.

Fitting each run to its columns instead (`lengthAdjust="spacingAndGlyphs"`) is
no cure: it stretches a narrow glyph as readily as it squeezes a wide one, and
distorts nearly a third of the runs in the committed captures by more than 6%.

{data}`~click_extra.capture.svg.WATERMARK_URL` documents the other half of
this: a capture embedded with `<img>` never sees the page's own `@font-face`
either, so a stylesheet cannot fix this from the outside.
```
"""


CAPTURE_PALETTES: dict[TerminalBackground, TerminalPalette] = {
    TerminalBackground.DARK: DEFAULT_PRESET.dark,
    TerminalBackground.LIGHT: DEFAULT_PRESET.light,
}
"""Colors each chrome resolves a capture's ANSI codes against.

A palette carries the 16 ANSI colors alongside the background and foreground,
which is the other half of the job: a CLI naming `blue` leaves the shade to
whoever draws it, and the one that reads on white is not the one that reads on
`#292929`.
"""


def resolve_palette(
    preset: TerminalPreset | None,
    background: TerminalBackground,
) -> TerminalPalette:
    """The colors a capture resolves its ANSI codes against.

    The preset's palette on the given chrome, or the default terminal's
    ({data}`CAPTURE_PALETTES`) when no preset dresses the capture. The one
    resolution rule {func}`~click_extra.capture.screenshot.render` and
    {func}`~click_extra.capture.snippet.style_palette` share, so the SVG and HTML
    formats cannot disagree on what a chrome looks like.

    :param preset: terminal being pictured, or `None` for the default one.
    :param background: chrome the capture is drawn on.
    :return: the palette.
    """
    preset = preset or DEFAULT_PRESET
    return preset.dark if background is TerminalBackground.DARK else preset.light


NO_PAINT = "none"
"""Border or shadow value asking for none to be drawn.

SVG's own keyword for an absent paint, so it reaches the `stroke` attribute
unchanged, and CSS's for an absent shadow.
"""

OPAQUE = 1.0
"""Opacity of a window showing nothing of what sits behind it.

Anything under it is what a terminal calls transparency: the backdrop, or the
page embedding the capture, comes through the window's body while its text,
frame and title bar stay as they are. `0.0` leaves the text alone on the page.
"""

WATERMARK_INK = "rgba(128,128,128,0.85)"
"""Color the credit line is drawn in.

The one paint in a capture that answers to neither chrome, because it is the one
thing drawn outside the window: the margin is transparent, so the mark sits on
whatever page embeds the image, which the capture never gets to see. A white
mark suits the dark chrome it was picked for and disappears on a README; a
neutral gray reads on both, and dims into a backdrop when one is painted.
"""

DEFAULT_BORDER_WIDTH = 1
"""Thickness, in pixels, of the frame drawn around the window."""

DEFAULT_RADIUS = 8
"""How round the window's corners are, in pixels.

The radius a renderer draws on its own, which is what a terminal on a desktop
looks like. Zero squares them, for a capture meant to read as a plain block.
"""

PACKAGE_NAME = "click-extra"
"""Name this package is distributed and credited under."""

DEFAULT_WATERMARK = f"generated with {PACKAGE_NAME}"
"""Credit line every capture carries unless another one, or none, is asked for.

A capture travels: it lands on a slide, in a README, on a social card, far from
the page that explains where it came from. The mark is what still says so, and
carries the link back.

The line names the tool, never its release. A capture is committed beside the
project that drew it and regenerated at every release, and a release number
would rewrite every asset on release day for nothing but the bump.

```{note}
This is a default, not a fixture. `--watermark ""` draws none, and any other
text replaces it: a project crediting itself rather than its tooling is the
expected case, not an exception.
```
"""

DEFAULT_MARGIN = 48
"""Transparent pixels left around the window, on all four sides.

Room for the shadow to fall into, first of all: a filter draws outside the shape
it is applied to, and anything past the image's own box is cut. It is also what
a backdrop has to show through, and what keeps the window from touching the text
of the page embedding it.
"""

DEFAULT_PADDING = 8
"""Pixels added inside the window, around the captured text.

On top of the few a renderer adds on its own (8, and 40 above for the title
bar), which leaves a help screen's first column tight against the frame.
"""

CAPTURE_BORDERS: dict[TerminalBackground, str] = {
    TerminalBackground.DARK: "rgba(255,255,255,0.35)",
    TerminalBackground.LIGHT: "rgba(0,0,0,0.25)",
}
"""Color the window frame is drawn in, per chrome.

The dark entry is a translucent white that reads against `#292929` and against
nothing else: a light capture framed with it is a white window on a white page,
the shape of the terminal only guessable from its text. Each chrome names a
frame its own background can show.
"""

CAPTURE_SHADOWS: dict[TerminalBackground, str] = {
    TerminalBackground.DARK: "rgba(0,0,0,0.5)",
    TerminalBackground.LIGHT: "rgba(0,0,0,0.25)",
}
"""Color the window's drop shadow floods with, per chrome.

Where the frame states the window's edge, the shadow lifts it off whatever page
embeds the capture, which is the other half of not dissolving into it. A reader
whose renderer drops the filter still gets the frame.
"""


@dataclass(frozen=True)
class Chrome:
    """How the window around a capture's text is drawn.

    One value for the decoration {func}`~click_extra.capture.screenshot.render`,
    {func}`~click_extra.capture.screenshot.capture`,
    {func}`~click_extra.capture.recording.record_and_render` and
    {func}`~click_extra.capture.snippet.render_snippet` all take, so its defaults
    live in one place. A field left at `None` takes what the capture's background
    and preset draw, which {meth}`resolve` fills in.

    ```{code-block} python

    from click_extra.capture.presets import Chrome
    from click_extra.capture.screenshot import render

    svg = render(text, chrome=Chrome(margin=0, watermark=""))
    ```
    """

    border: str | None = None
    """Color of the window's frame.

    `None` takes the one the background can show, see {data}`CAPTURE_BORDERS`;
    {data}`NO_PAINT` draws none.
    """

    border_width: int = DEFAULT_BORDER_WIDTH
    """Thickness of that frame, in pixels."""

    radius: int | None = None
    """How round the window's corners are, in pixels. Zero squares them.

    `None` takes the preset's own, or {data}`DEFAULT_RADIUS` without one.
    """

    backdrop: str = NO_PAINT
    """Paint filling the image behind the window, margin included.

    {data}`NO_PAINT` leaves it transparent.
    """

    shadow: str | None = None
    """Color of the window's drop shadow.

    `None` takes the background's own, see {data}`CAPTURE_SHADOWS`;
    {data}`NO_PAINT` draws none.
    """

    margin: int = DEFAULT_MARGIN
    """Transparent pixels left around the window, on all four sides."""

    padding: int = DEFAULT_PADDING
    """Pixels added inside the window, around the text."""

    opacity: float = OPAQUE
    """How solid the window's body is, from {data}`OPAQUE` down to `0.0`.

    Below it, whatever the capture is laid over shows through.
    """

    watermark: str = DEFAULT_WATERMARK
    """Credit line drawn in the image's bottom-right corner.

    See {data}`DEFAULT_WATERMARK`. An empty string draws none.
    """

    watermark_color: str | None = None
    """Color that line is drawn in.

    `None` takes {data}`WATERMARK_INK`, which reads on a page of either color.
    """

    def resolve(
        self, background: TerminalBackground, preset: TerminalPreset | None
    ) -> Chrome:
        """This chrome, with every `None` replaced by what the capture draws.

        {func}`~click_extra.capture.svg.render_svg` and
        {func}`~click_extra.capture.html.render_html` take a resolved chrome,
        which makes this the one step between the two layers.

        :param background: chrome the capture is headed for.
        :param preset: terminal being pictured, or `None`.
        :return: a chrome carrying no `None`.
        """
        return replace(
            self,
            border=CAPTURE_BORDERS[background] if self.border is None else self.border,
            radius=(
                (DEFAULT_RADIUS if preset is None else preset.radius)
                if self.radius is None
                else self.radius
            ),
            shadow=CAPTURE_SHADOWS[background] if self.shadow is None else self.shadow,
            watermark_color=(
                WATERMARK_INK if self.watermark_color is None else self.watermark_color
            ),
        )

    def check_resolved(self) -> None:
        """Refuse a chrome that still carries a `None`.

        A renderer draws the values it is given, and a `None` names no paint and
        no size: only {meth}`resolve` knows what it stands for.

        :raises ValueError: naming each field still set to `None`.
        """
        unset = [each.name for each in fields(self) if getattr(self, each.name) is None]
        if unset:
            raise ValueError(
                "Resolve the chrome before drawing it, see Chrome.resolve(): "
                f"{', '.join(unset)} left at None."
            )


BARE_CHROME = Chrome(
    border=NO_PAINT,
    radius=DEFAULT_RADIUS,
    shadow=NO_PAINT,
    margin=0,
    padding=0,
    watermark="",
    watermark_color=WATERMARK_INK,
)
"""A resolved chrome that draws the window alone.

No frame, no shadow, no margin, no padding and no credit line: what
{func}`~click_extra.capture.svg.render_svg` and
{func}`~click_extra.capture.html.render_html` draw when they get no chrome. A
capture taken through {func}`~click_extra.capture.screenshot.render` resolves a
{class}`Chrome` instead, which frames the window and credits the package.
"""
