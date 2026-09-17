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

"""Render captured terminal text as self-contained HTML.

{mod}`click_extra.screenshot` decides what a capture shows, then hands the text,
its palette and the resolved {class}`~click_extra.screenshot.Chrome` to
{func}`render_html`, which writes them as an inline-styled `<pre>`: selectable,
searchable text that needs no stylesheet and reflows with the page. The window
around it is drawn with the geometry {mod}`click_extra.screenshot_svg` publishes,
so the two documents look like the same terminal.
"""

from __future__ import annotations

from html import escape

from .screenshot_presets import (
    CAPTURE_FONT_STACK,
    CAPTURE_FOREGROUND,
    CaptureBackground,
    resolve_palette,
)
from .screenshot_svg import (
    DEFAULT_BORDER_WIDTH,
    DEFAULT_RADIUS,
    NO_PAINT,
    OPAQUE,
    SHADOW_BLUR,
    SHADOW_OFFSET,
    WATERMARK_INK,
    WATERMARK_INSET,
    WATERMARK_SIZE,
    WATERMARK_URL,
    credit_segments,
)
from .styling import ansi_to_html

TYPE_CHECKING = False
if TYPE_CHECKING:
    from .screenshot_presets import TerminalPalette, TerminalPreset, WindowButtons


def render_html(
    text: str,
    *,
    title: str = "",
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
    preset: TerminalPreset | None = None,
    palette: TerminalPalette | None = None,
    border: str = NO_PAINT,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int = DEFAULT_RADIUS,
    backdrop: str = NO_PAINT,
    shadow: str = NO_PAINT,
    margin: int = 0,
    padding: int = 0,
    buttons: WindowButtons | None = None,
    buttons_color: str = CAPTURE_FOREGROUND,
    font_stack: str = CAPTURE_FONT_STACK,
    titlebar: str = NO_PAINT,
    collapse_titlebar: bool = False,
    opacity: float = OPAQUE,
    watermark: str = "",
    watermark_color: str = WATERMARK_INK,
    watermark_url: str = WATERMARK_URL,
) -> str:
    """Render captured terminal text to HTML.

    The `<pre>` carries its own inline styling, so a fragment pasted into an
    existing page needs no stylesheet and cannot be restyled out of legibility
    by the host. Nothing else is needed either: a `<pre>` preserves the
    capture's own spacing, which is what spares HTML the column arithmetic
    {func}`~click_extra.screenshot_svg.render_svg` performs for a picture.

    ```{caution}
    The text is escaped before its ANSI is translated, the order
    {mod}`click_extra.table` uses for its `html` format. Skip it and any `<` a
    CLI prints opens a tag: click-extra's own `--export-config` help says it
    writes `to <stdout>`.
    ```

    ```{note}
    An OSC 8 hyperlink loses its URL and keeps its visible text: the escape is
    dropped rather than turned into an `<a>`.
    ```

    :param text: captured output, ANSI escape sequences included.
    :param title: `<title>` of the document. Ignored for a fragment.
    :param full: wrap the `<pre>` in a standalone document. `False` returns the
        `<pre>` alone, to paste into a page that has its own.
    :param background: chrome to draw on, see
        {class}`~click_extra.screenshot_presets.CaptureBackground`.
    :param palette: colors the text resolves against. `None` takes the ones the
        preset and chrome name, which is what a terminal capture wants. Stated
        by a capture whose colors come from somewhere else, as a
        {mod}`~click_extra.snippet` one takes them from a syntax style.
    :param border: color of the block's frame, see
        {func}`~click_extra.screenshot_svg.render_svg`.
    :param border_width: thickness of that frame, in pixels.
    :param radius: how round the block's corners are, in pixels.
    :param backdrop: paint filling the page behind the block.
    :param shadow: color of the block's drop shadow, see
        {func}`~click_extra.screenshot_svg.render_svg`.
    :param margin: pixels left around the block, on all four sides.
    :param padding: pixels added inside the block, on top of its own.
    :param buttons: ignored. HTML reflows with the page embedding it, so it
        carries the text and its colors, not a window drawn around them.
    :param buttons_color: ignored, see `buttons`.
    :param titlebar: ignored, see `buttons`.
    :param collapse_titlebar: ignored, see `buttons`.
    :param opacity: how solid the block's background is, from
        {data}`~click_extra.screenshot_svg.OPAQUE` down to `0.0`, where the page shows
        straight through the text.
    :param watermark: credit line drawn under the block, against its right edge,
        where an SVG draws it in the margin. Empty draws none.
    :param watermark_color: color that line is drawn in, alpha included.
    :param watermark_url: where the package name points. Empty links nothing.
    :return: the rendered markup.
    """
    if palette is None:
        palette = resolve_palette(preset, background)
    chrome, ink = palette.background, palette.foreground
    if opacity != OPAQUE:
        # CSS carries no background-opacity, and the `opacity` property would
        # take the text down with it, so the color itself is thinned instead.
        chrome = f"color-mix(in srgb, {chrome} {opacity:.0%}, transparent)"
    frame = "" if border == NO_PAINT else f"border: {border_width}px solid {border}; "
    if shadow != NO_PAINT:
        frame += f"box-shadow: 0 {SHADOW_OFFSET}px {SHADOW_BLUR * 2}px {shadow}; "
    # A credit line takes the block's bottom margin over, so the two read as one
    # figure: the same place an SVG draws its mark, which is the margin rather
    # than the page below it.
    block_margin = f"{margin}px"
    if watermark:
        block_margin = (
            f"{margin}px {margin}px {max(margin // 4, WATERMARK_INSET // 2)}px"
        )
    body = (
        f'<pre style="background: {chrome}; color: {ink}; '
        f"font-family: {font_stack}; line-height: 1.25; "
        f"margin: {block_margin}; padding: calc(1em + {padding}px); "
        f"{frame}border-radius: {radius}px; "
        f'overflow-x: auto">{ansi_to_html(escape(text, quote=False))}</pre>'
    )
    if watermark:
        credit = escape(watermark, quote=False)
        segments = credit_segments(watermark) if watermark_url else None
        if segments:
            before, name, after = segments
            # The anchor inherits the credit's own gray rather than taking the
            # page's link color, which would make the mark the loudest thing in
            # a capture whose point is the terminal above it.
            credit = (
                f"{escape(before, quote=False)}"
                f'<a href="{escape(watermark_url)}" style="color: inherit">'
                f"{escape(name, quote=False)}</a>{escape(after, quote=False)}"
            )
        body += (
            f'\n<div style="margin: 0 {margin}px {margin}px; text-align: right; '
            f"color: {watermark_color}; font-family: {font_stack}; "
            f'font-size: {WATERMARK_SIZE}px">{credit}</div>'
        )
    page = "" if backdrop == NO_PAINT else f"background: {backdrop}; "
    if not full:
        # A fragment carries no page of its own, so a backdrop needs one. A
        # credit line needs nothing: a fragment is a run of markup, and the mark
        # is the second element of it.
        return f'<div style="{page}">{body}</div>' if page else body
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{escape(title, quote=False)}</title>\n"
        "</head>\n"
        f'<body style="{page}margin: 0">\n{body}\n</body>\n'
        "</html>\n"
    )
