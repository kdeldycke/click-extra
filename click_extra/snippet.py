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

"""Draw a snippet of source code as a static document.

{mod}`click_extra.screenshot` pictures what a command *printed*. This module
pictures what a file *says*, and hands the result to the same renderer: a
README, a slide or a social post that cannot run code equally cannot syntax
highlight it, so both need a picture.

The pipeline is the screenshot module's, with its first step swapped:

1. {func}`highlight_code` colors the source with Pygments, which writes the same
   ANSI escape sequences a terminal would.
2. {func}`~click_extra.screenshot.render` turns that text into a document.

That leaves nothing to reimplement. Pygments' terminal formatter speaks the
interchange format {func}`~click_extra.styling.split_ansi` already parses, so a
snippet inherits the window, the presets, the light and dark chromes, the line
numbers, the emphasis bands and the HTML export from the captures beside it.

{func}`render_snippet` chains both, and is what the `click-extra snippet`
command calls.

```{note}
A snippet answers to a Pygments *style*, where a capture answers to a terminal
*palette*. The two name colors differently: a style states every color it uses,
while a terminal names sixteen and leaves their shades to whoever draws them.
{func}`style_palette` is where the first becomes the second.
```
"""

from __future__ import annotations

from ._utils import missing_extra_message

try:
    import pygments  # noqa: F401
except ImportError as err:
    raise ImportError(missing_extra_message("pygments", subject="This module")) from err

from pygments import highlight as pygments_highlight
from pygments.formatters import TerminalTrueColorFormatter
from pygments.lexers import get_lexer_by_name, get_lexer_for_filename, guess_lexer
from pygments.styles import get_all_styles, get_style_by_name
from pygments.token import Token
from pygments.util import ClassNotFound

from .screenshot import (
    AUTO_COLUMNS,
    DEFAULT_BORDER_WIDTH,
    DEFAULT_MARGIN,
    DEFAULT_PADDING,
    DEFAULT_TRUNCATION,
    DEFAULT_WATERMARK,
    NO_PAINT,
    OPAQUE,
    CaptureBackground,
    CaptureFormat,
    number_lines,
    render,
    resolve_palette,
    trim_lines,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence

    from pygments.lexer import Lexer

    from .screenshot import TColumns
    from .screenshot_presets import TerminalPalette, TerminalPreset


DEFAULT_SYNTAX_STYLES: dict[CaptureBackground, str] = {
    CaptureBackground.DARK: "monokai",
    CaptureBackground.LIGHT: "default",
}
"""Pygments style a snippet is colored with, per chrome.

Both are picked to sit beside a terminal capture without a seam showing.
`monokai` paints `#272822`, two shades off the `#292929` a dark capture is drawn
on, and Pygments' own `default` paints `#f8f8f8` against a light capture's
white. A darker style renders perfectly well on its own and steps visibly when
the two images share a page, which is the case this default is chosen for.
"""

TAB_WIDTH = 4
"""Spaces a tab is expanded to before the snippet is laid out.

A terminal expands tabs as it prints, so captured output never carries one and
the renderer never had to answer for it. A file does carry them, and a tab has
no width on a character grid: {func}`~click_extra.screenshot.cell_width` reads
`wcwidth.wcswidth`, which answers `-1` for a control character and takes the
whole line's measurement down with it. Expanding up front is what keeps the grid
arithmetic true.
"""

FALLBACK_LEXER = "text"
"""Lexer a snippet is colored with when nothing identifies its language.

Emits one unstyled token per line, so an unrecognized file is drawn as the plain
text it could not be proven to be, rather than miscolored as a guess.
"""


def known_styles() -> tuple[str, ...]:
    """Every Pygments style a snippet can be colored with, sorted.

    :return: the style names.
    """
    return tuple(sorted(get_all_styles()))


def resolve_lexer(
    code: str,
    *,
    language: str | None = None,
    filename: str | None = None,
) -> Lexer:
    """Pick the lexer a snippet is colored with.

    Three sources answer, in falling order of how much they know: the language
    stated outright, the file name it was read from, and the code itself. A
    stated language that names no lexer is an error rather than a fallback,
    since silently drawing `pythn` as plain text hides the typo in a picture
    nobody re-reads.

    :param code: the source, used to break a tie between lexers sharing an
        extension and to guess when nothing else identifies it.
    :param language: the language, as [Pygments names it](https://pygments.org/languages/).
    :param filename: name the code was read from, extension included.
    :return: the lexer.
    :raises ValueError: when `language` names no lexer Pygments knows.
    """
    if language:
        try:
            return get_lexer_by_name(language)
        except ClassNotFound:
            raise ValueError(
                f"{language!r} is not a language Pygments knows. See "
                "https://pygments.org/languages/ for the ones it does."
            ) from None
    if filename:
        try:
            return get_lexer_for_filename(filename, code)
        except ClassNotFound:
            pass
    try:
        return guess_lexer(code)
    except ClassNotFound:
        return get_lexer_by_name(FALLBACK_LEXER)


def resolve_style(
    style: str | None,
    background: CaptureBackground,
) -> str:
    """The Pygments style a snippet is colored with.

    :param style: the style asked for, or `None` for the chrome's default.
    :param background: chrome the snippet is drawn on.
    :return: the style's name.
    :raises ValueError: when `style` names no style Pygments knows.
    """
    if style is None:
        return DEFAULT_SYNTAX_STYLES[background]
    try:
        get_style_by_name(style)
    except ClassNotFound:
        raise ValueError(
            f"{style!r} is not a style Pygments knows: it is not one of "
            f"{', '.join(known_styles())}."
        ) from None
    return style


def style_palette(
    style: str,
    background: CaptureBackground,
    *,
    preset: TerminalPreset | None = None,
) -> TerminalPalette:
    """The colors a snippet's window is drawn with, taken from a syntax style.

    A style states the background it was designed against, and a snippet drawn
    on any other one is a picture of that style in a window it was never meant
    for: `monokai`'s comment gray reads on `#272822` and disappears on white.

    The chrome's own palette is where the rest comes from. Its sixteen ANSI
    slots are carried through untouched, being what a preset publishes and what
    a run captured in the same document resolves against; a snippet consults
    none of them, since Pygments states every color outright.

    ```{note}
    A style naming no color for plain text keeps the chrome's foreground, which
    is what the twenty-five light styles shipping no `Token.Text` color need:
    their code is black on near-white, and black is what a light chrome already
    names.
    ```

    :param style: name of the Pygments style.
    :param background: chrome the snippet is drawn on.
    :param preset: terminal the window is dressed as, whose palette the
        decorations keep answering to.
    :return: the palette.
    """
    chrome = resolve_palette(preset, background)
    paper = get_style_by_name(style).background_color
    ink = get_style_by_name(style).style_for_token(Token.Text)["color"]
    return chrome._replace(
        background=paper,
        foreground=f"#{ink}" if ink else chrome.foreground,
        # A window wearing no preset paints no title bar, so this only reaches a
        # reader taking the palette apart. It still answers to the same surface
        # the background does, rather than to a chrome the snippet replaced.
        titlebar=chrome.titlebar if preset is not None else paper,
    )


def highlight_code(
    code: str,
    *,
    language: str | None = None,
    filename: str | None = None,
    style: str = DEFAULT_SYNTAX_STYLES[CaptureBackground.DARK],
) -> str:
    """Color source code the way a terminal would print it.

    Pygments' true-color terminal formatter writes `38;2;r;g;b` sequences, which
    is the one interchange format both capture renderers already read. So the
    output of this drops straight into
    {func}`~click_extra.screenshot.render`, with nothing in between.

    :param code: the source to color.
    :param language: the language, as Pygments names it. See
        {func}`resolve_lexer` for what answers when it is left out.
    :param filename: name the code was read from, extension included.
    :param style: name of the Pygments style to color with.
    :return: the source, ANSI escape sequences included.
    :raises ValueError: when `language` names no lexer Pygments knows.
    """
    lexer = resolve_lexer(code, language=language, filename=filename)
    # Expanded before coloring, not after: an escape sequence occupies no column
    # of its own, so a tab measured across one would be expanded to the wrong
    # stop. See TAB_WIDTH for why they cannot be left alone.
    return pygments_highlight(
        code.expandtabs(TAB_WIDTH),
        lexer,
        TerminalTrueColorFormatter(style=style),
    )


def render_snippet(
    code: str,
    *,
    format: CaptureFormat = CaptureFormat.SVG,
    language: str | None = None,
    filename: str | None = None,
    style: str | None = None,
    columns: TColumns = AUTO_COLUMNS,
    head: int | None = None,
    tail: int | None = None,
    truncation: str = DEFAULT_TRUNCATION,
    line_numbers: bool = False,
    emphasize: Sequence[int] = (),
    title: str = "",
    unique_id: str | None = None,
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
    preset: TerminalPreset | None = None,
    border: str | None = None,
    border_width: int = DEFAULT_BORDER_WIDTH,
    radius: int | None = None,
    backdrop: str = NO_PAINT,
    shadow: str | None = None,
    margin: int = DEFAULT_MARGIN,
    padding: int = DEFAULT_PADDING,
    opacity: float = OPAQUE,
    watermark: str = DEFAULT_WATERMARK,
    watermark_color: str | None = None,
) -> str:
    """Color source code and render it as a document.

    Chains {func}`highlight_code`, {func}`~click_extra.screenshot.trim_lines`
    and {func}`~click_extra.screenshot.render`.

    ```{note}
    The width defaults to {data}`~click_extra.screenshot.AUTO_COLUMNS`, where a
    terminal capture pins eighty. A command wraps its own output to the width it
    was told about, so a capture at that width folds nothing; nobody wrapped a
    source file to any width, and a picture that soft-wrapped its code would
    break indentation the reader is meant to be reading.
    ```

    :param code: the source to draw.
    :param format: which document to produce.
    :param language: the language, as Pygments names it. See
        {func}`resolve_lexer` for what answers when it is left out.
    :param filename: name the code was read from, extension included.
    :param style: name of the Pygments style to color with. `None` takes the
        chrome's own, see {data}`DEFAULT_SYNTAX_STYLES`.
    :param columns: width, in characters, an SVG is laid out at.
    :param head: number of leading lines to keep.
    :param tail: number of trailing lines to keep.
    :param truncation: line standing in for the lines cut by `head` or `tail`.
    :param line_numbers: draw each line's number in a gutter, see
        {func}`~click_extra.screenshot.number_lines`.
    :param emphasize: lines to draw a band behind, counted from `1`.
    :param title: see {func}`~click_extra.screenshot.render`.
    :param unique_id: see {func}`~click_extra.screenshot.render`.
    :param full: see {func}`~click_extra.screenshot.render`.
    :param background: see {func}`~click_extra.screenshot.render`.
    :param preset: see {func}`~click_extra.screenshot.render`.
    :param border: see {func}`~click_extra.screenshot.render`.
    :param border_width: see {func}`~click_extra.screenshot.render`.
    :param radius: see {func}`~click_extra.screenshot.render`.
    :param backdrop: see {func}`~click_extra.screenshot.render`.
    :param shadow: see {func}`~click_extra.screenshot.render`.
    :param margin: see {func}`~click_extra.screenshot.render`.
    :param padding: see {func}`~click_extra.screenshot.render`.
    :param opacity: see {func}`~click_extra.screenshot.render`.
    :param watermark: see {func}`~click_extra.screenshot.render`.
    :param watermark_color: see {func}`~click_extra.screenshot.render`.
    :return: the rendered document.
    :raises ValueError: when `language` or `style` names nothing Pygments knows.
    """
    resolved_style = resolve_style(style, background)
    text = highlight_code(
        code,
        language=language,
        filename=filename,
        style=resolved_style,
    )
    text = trim_lines(text, head=head, tail=tail, truncation=truncation)
    if line_numbers:
        text = number_lines(text)
    return render(
        text,
        format=format,
        columns=columns,
        title=title,
        unique_id=unique_id,
        emphasize=emphasize,
        full=full,
        background=background,
        preset=preset,
        palette=style_palette(resolved_style, background, preset=preset),
        border=border,
        border_width=border_width,
        radius=radius,
        backdrop=backdrop,
        shadow=shadow,
        margin=margin,
        padding=padding,
        opacity=opacity,
        watermark=watermark,
        watermark_color=watermark_color,
    )
