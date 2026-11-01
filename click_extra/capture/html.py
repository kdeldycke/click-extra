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

{mod}`click_extra.capture.screenshot` decides what a capture shows, then hands
the text, its palette and the resolved {class}`~click_extra.capture.presets.Chrome`
to {func}`render_html`, which writes them as an inline-styled `<pre>`: selectable,
searchable text that needs no stylesheet and reflows with the page. The window
around it is drawn with the geometry {mod}`click_extra.capture.svg` publishes, so
the two documents look like the same terminal.
"""

from __future__ import annotations

from ..styling import ansi_to_html
from .presets import BARE_CHROME, CAPTURE_FONT_STACK, DEFAULT_PRESET, NO_PAINT, OPAQUE
from .svg import (
    SHADOW_BLUR,
    SHADOW_OFFSET,
    WATERMARK_INSET,
    WATERMARK_SIZE,
    WATERMARK_URL,
    _escape_markup,
    credit_markup,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from .presets import Chrome, TerminalPalette


def _credit_link(url: str, name: str) -> str:
    """Wrap the credit line's package name in an HTML link.

    The anchor inherits the credit's own gray rather than taking the page's link
    color, which would make the mark the loudest thing in a capture whose point
    is the terminal above it.
    """
    return (
        f'<a href="{_escape_markup(url, quote=True)}" style="color: inherit">'
        f"{_escape_markup(name)}</a>"
    )


def render_html(
    text: str,
    *,
    title: str = "",
    full: bool = True,
    palette: TerminalPalette = DEFAULT_PRESET.dark,
    chrome: Chrome = BARE_CHROME,
    font_stack: str = CAPTURE_FONT_STACK,
) -> str:
    """Render captured terminal text to HTML.

    The `<pre>` carries its own inline styling, so a fragment pasted into an
    existing page needs no stylesheet and cannot be restyled out of legibility
    by the host. Nothing else is needed either: a `<pre>` preserves the
    capture's own spacing, which is what spares HTML the column arithmetic
    {func}`~click_extra.capture.svg.render_svg` performs for a picture.

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
        `<pre>` and its credit line alone, to paste into a page that has its own.
    :param palette: terminal colors the text resolves against, see
        {func}`~click_extra.capture.presets.resolve_palette`.
    :param chrome: the block around the text, resolved, see
        {meth}`~click_extra.capture.presets.Chrome.resolve`. Its `margin` is left
        around the block, its `padding` added inside the block on top of its
        own, its `backdrop` fills the page behind it, and its `opacity` thins the
        block's background alone, down to `0.0` where the page shows straight
        through the text. The credit line sits under the block, against its
        right edge, where an SVG draws it in the margin. Defaults to
        {data}`~click_extra.capture.presets.BARE_CHROME`.
    :param font_stack: fonts the text is set in, best first.
    :return: the rendered markup.
    :raises ValueError: when `chrome` is not resolved.
    """
    chrome.check_resolved()
    margin = chrome.margin
    background, ink = palette.background, palette.foreground
    if chrome.opacity != OPAQUE:
        # CSS carries no background-opacity, and the `opacity` property would
        # take the text down with it, so the color itself is thinned instead.
        background = (
            f"color-mix(in srgb, {background} {chrome.opacity:.0%}, transparent)"
        )
    frame = (
        ""
        if chrome.border == NO_PAINT
        else f"border: {chrome.border_width}px solid {chrome.border}; "
    )
    if chrome.shadow != NO_PAINT:
        frame += (
            f"box-shadow: 0 {SHADOW_OFFSET}px {SHADOW_BLUR * 2}px {chrome.shadow}; "
        )
    # A credit line takes the block's bottom margin over, so the two read as one
    # figure: the same place an SVG draws its mark, which is the margin rather
    # than the page below it.
    block_margin = f"{margin}px"
    if chrome.watermark:
        block_margin = (
            f"{margin}px {margin}px {max(margin // 4, WATERMARK_INSET // 2)}px"
        )
    body = (
        f'<pre style="background: {background}; color: {ink}; '
        f"font-family: {font_stack}; line-height: 1.25; "
        f"margin: {block_margin}; padding: calc(1em + {chrome.padding}px); "
        f"{frame}border-radius: {chrome.radius}px; "
        f'overflow-x: auto">{ansi_to_html(_escape_markup(text))}</pre>'
    )
    if chrome.watermark:
        credit = credit_markup(
            chrome.watermark, WATERMARK_URL, _credit_link, escape=_escape_markup
        )
        body += (
            f'\n<div style="margin: 0 {margin}px {margin}px; text-align: right; '
            f"color: {chrome.watermark_color}; font-family: {font_stack}; "
            f'font-size: {WATERMARK_SIZE}px">{credit}</div>'
        )
    page = "" if chrome.backdrop == NO_PAINT else f"background: {chrome.backdrop}; "
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
        f"<title>{_escape_markup(title)}</title>\n"
        "</head>\n"
        f'<body style="{page}margin: 0">\n{body}\n</body>\n'
        "</html>\n"
    )
