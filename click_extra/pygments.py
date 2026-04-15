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
"""Pygments lexers, filters, and formatters for ANSI Select Graphic Rendition codes.

Parses ANSI SGR escape sequences (ECMA-48 / ISO 6429) from terminal output and renders
them as colored HTML with CSS classes. Supports the standard 8/16 named colors, the
256-color indexed palette, and 24-bit RGB.

SGR text attributes: bold, faint, italic, underline, blink, reverse video, strikethrough,
and overline.

.. warning::
    24-bit RGB colors (``SGR 38;2;r;g;b`` and ``48;2;r;g;b``) are quantized to the
    nearest entry in the 256-color indexed palette. This is a deliberate trade-off:
    true RGB rendering would require per-color inline styles, breaking the CSS-class
    architecture that Pygments and Sphinx rely on. The quantization produces a close
    visual approximation for most colors.
"""

from __future__ import annotations

import itertools
import re

try:
    import pygments  # noqa: F401
except ImportError:
    raise ImportError(
        "You need to install click_extra[pygments] extra dependencies to use this "
        "module."
    )

from pygments import lexers
from pygments.filter import Filter
from pygments.filters import TokenMergeFilter
from pygments.formatter import _lookup_style  # type: ignore[attr-defined]
from pygments.formatters import HtmlFormatter
from pygments.lexer import Lexer, LexerMeta
from pygments.lexers.algebra import GAPConsoleLexer
from pygments.lexers.dylan import DylanConsoleLexer
from pygments.lexers.erlang import ElixirConsoleLexer, ErlangShellLexer
from pygments.lexers.julia import JuliaConsoleLexer
from pygments.lexers.matlab import MatlabSessionLexer
from pygments.lexers.php import PsyshConsoleLexer
from pygments.lexers.python import PythonConsoleLexer
from pygments.lexers.r import RConsoleLexer
from pygments.lexers.ruby import RubyConsoleLexer
from pygments.lexers.shell import ShellSessionBaseLexer
from pygments.lexers.special import OutputLexer
from pygments.lexers.sql import PostgresConsoleLexer, SqliteConsoleLexer
from pygments.style import StyleMeta
from pygments.token import Generic, Text, Token, string_to_tokentype

from .colorize import _CUBE_VALUES, _nearest_256

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from typing import ClassVar

    from pygments.token import _TokenType


# --- Color palettes ---

_NAMED_COLORS: dict[str, str] = {
    "Black": "#000000",
    "Red": "#ef2929",
    "Green": "#8ae234",
    "Yellow": "#fce94f",
    "Blue": "#3465a4",
    "Magenta": "#c509c5",
    "Cyan": "#34e2e2",
    "White": "#f5f5f5",
    "BrightBlack": "#676767",
    "BrightRed": "#ff6d67",
    "BrightGreen": "#5ff967",
    "BrightYellow": "#fefb67",
    "BrightBlue": "#6871ff",
    "BrightMagenta": "#ff76ff",
    "BrightCyan": "#5ffdff",
    "BrightWhite": "#feffff",
}
"""Standard 8 colors and their bright variants, mapped to hex values."""

_PALETTE_256: dict[int, str] = {
    0: "#000000",
    1: "#800000",
    2: "#008000",
    3: "#808000",
    4: "#000080",
    5: "#800080",
    6: "#008080",
    7: "#c0c0c0",
    8: "#808080",
    9: "#ff0000",
    10: "#00ff00",
    11: "#ffff00",
    12: "#0000ff",
    13: "#ff00ff",
    14: "#00ffff",
    15: "#ffffff",
}
"""256-color indexed palette mapped to hex values.

Indices 0-7 are the standard colors, 8-15 are bright variants, 16-231 are the 6x6x6
color cube, and 232-255 are the grayscale ramp.
"""

# 6x6x6 color cube (indices 16-231).
_PALETTE_256.update({
    16 + i: "#{:02x}{:02x}{:02x}".format(*rgb)
    for i, rgb in enumerate(itertools.product(_CUBE_VALUES, _CUBE_VALUES, _CUBE_VALUES))
})
# Grayscale ramp (indices 232-255).
_PALETTE_256.update({
    232 + i: "#{0:02x}{0:02x}{0:02x}".format(10 * i + 8) for i in range(24)
})


_SGR_FG_COLORS: dict[int, str] = {
    30: "Black",
    31: "Red",
    32: "Green",
    33: "Yellow",
    34: "Blue",
    35: "Magenta",
    36: "Cyan",
    37: "White",
    90: "BrightBlack",
    91: "BrightRed",
    92: "BrightGreen",
    93: "BrightYellow",
    94: "BrightBlue",
    95: "BrightMagenta",
    96: "BrightCyan",
    97: "BrightWhite",
}
"""SGR foreground color codes (30-37, 90-97) to named color strings."""

_SGR_BG_COLORS: dict[int, str] = {
    40: "Black",
    41: "Red",
    42: "Green",
    43: "Yellow",
    44: "Blue",
    45: "Magenta",
    46: "Cyan",
    47: "White",
    100: "BrightBlack",
    101: "BrightRed",
    102: "BrightGreen",
    103: "BrightYellow",
    104: "BrightBlue",
    105: "BrightMagenta",
    106: "BrightCyan",
    107: "BrightWhite",
}
"""SGR background color codes (40-47, 100-107) to named color strings."""


# --- Token construction ---

Ansi = Token.Ansi
"""Unified token namespace for ANSI styling.

Compound tokens from the lexer (like ``Token.Ansi.Bold.Red``) and individual style
components (like ``Token.Ansi.Red``) share this single namespace. The formatter
decomposes compound tokens into individual CSS classes at render time.
"""


def _token_from_state(
    bold: bool,
    faint: bool,
    italic: bool,
    underline: bool,
    blink: bool,
    reverse: bool,
    strikethrough: bool,
    overline: bool,
    fg_color: str | None,
    bg_color: str | None,
) -> _TokenType:
    """Construct a compound ``Token.Ansi.*`` token from the current SGR state.

    Each active attribute and color becomes a component of the token path. For example,
    bold red text on a green background produces ``Token.Ansi.Bold.Red.BGGreen``.
    """
    components: list[str] = []
    if bold:
        components.append("Bold")
    if faint:
        components.append("Faint")
    if italic:
        components.append("Italic")
    if underline:
        components.append("Underline")
    if blink:
        components.append("Blink")
    if reverse:
        components.append("Reverse")
    if strikethrough:
        components.append("Strikethrough")
    if overline:
        components.append("Overline")
    if fg_color:
        components.append(fg_color)
    if bg_color:
        components.append("BG" + bg_color)
    if not components:
        return Text
    token = Ansi
    for c in components:
        token = getattr(token, c)
    return token


# --- Style generation ---


def _build_ansi_styles() -> dict[_TokenType, str]:
    """Build the Pygments style dict mapping ``Token.Ansi.*`` to CSS property strings.

    Registers text attributes, 16 named colors (foreground and background), and the full
    256-color indexed palette.
    """
    styles: dict[_TokenType, str] = {}

    # SGR text attributes.
    styles[Ansi.Bold] = "bold"
    styles[Ansi.Faint] = ""
    styles[Ansi.Italic] = "italic"
    styles[Ansi.Underline] = "underline"
    styles[Ansi.Blink] = ""
    styles[Ansi.Reverse] = ""
    styles[Ansi.Strikethrough] = ""
    styles[Ansi.Overline] = ""

    # Named colors (16 foreground + 16 background).
    for name, hex_value in _NAMED_COLORS.items():
        styles[getattr(Ansi, name)] = hex_value
        styles[getattr(Ansi, f"BG{name}")] = f"bg:{hex_value}"

    # 256-color indexed palette (256 foreground + 256 background).
    for i, hex_value in _PALETTE_256.items():
        styles[getattr(Ansi, f"C{i}")] = hex_value
        styles[getattr(Ansi, f"BGC{i}")] = f"bg:{hex_value}"

    return styles


_ANSI_STYLES: dict[_TokenType, str] = _build_ansi_styles()
"""Pre-built Pygments style dict for all ANSI color tokens.

Computed once at import time. Used by ``AnsiHtmlFormatter`` to augment the base Pygments
style with ANSI color support.
"""


# --- Lexer ---

DEFAULT_TOKEN_TYPE = Generic.Output
"""Default Pygments token type to render with ANSI support.

Defaults to ``Generic.Output`` tokens, as this is the token type used by all REPL-like
and terminal session lexers.
"""

_ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[(?P<sgr_params>[0-9;]*)m"
    r"|\x1b\[[^a-zA-Z]*[a-zA-Z]"
    r"|\x1b[()][A-B012]"
    r"|\x1b.?"
    r"|(?P<text>[^\x1b]+)",
)
"""Single-pass regex for ANSI escape sequence parsing.

Alternatives in priority order:

1. CSI SGR sequence (``ESC [`` + params + ``m``): captured for SGR processing.
2. Other CSI sequences (``ESC [`` + params + final byte): consumed and stripped.
3. VT100 charset selection (``ESC (`` or ``ESC )`` + designator): consumed and stripped.
4. Any other escape sequence: consumed and stripped.
5. Plain text: captured and emitted with the current styling token.
"""


class AnsiColorLexer(Lexer):
    """Lexer for text containing ANSI SGR escape sequences.

    Parses Select Graphic Rendition (SGR) codes and emits compound ``Token.Ansi.*``
    tokens representing the active styling state. Non-SGR escape sequences are silently
    stripped.

    Supported SGR codes:

    - Text attributes: bold (1), faint (2), italic (3), underline (4), blink (5),
      reverse video (7), strikethrough (9), overline (53), and their resets.
    - Named colors: standard (30-37, 40-47) and bright (90-97, 100-107).
    - 256-color indexed palette (38;5;n, 48;5;n).
    - 24-bit RGB (38;2;r;g;b, 48;2;r;g;b), quantized to the nearest 256-color entry.
    """

    name = "ANSI Color"
    aliases = ("ansi-color", "ansi", "ansi-terminal")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._reset_state()

    def _reset_state(self) -> None:
        """Reset all SGR state to defaults."""
        self.bold = False
        self.faint = False
        self.italic = False
        self.underline = False
        self.blink = False
        self.reverse = False
        self.strikethrough = False
        self.overline = False
        self.fg_color: str | None = None
        self.bg_color: str | None = None

    @property
    def _current_token(self) -> _TokenType:
        """Return the compound token for the current SGR state."""
        return _token_from_state(
            self.bold,
            self.faint,
            self.italic,
            self.underline,
            self.blink,
            self.reverse,
            self.strikethrough,
            self.overline,
            self.fg_color,
            self.bg_color,
        )

    def _process_sgr(self, params: str) -> None:
        """Update SGR state from a semicolon-separated parameter string.

        An empty parameter string is equivalent to SGR 0 (reset all).
        """
        if not params:
            self._reset_state()
            return

        try:
            values = [int(v) for v in params.split(";")]
        except ValueError:
            return

        while values:
            code = values.pop(0)

            # SGR 0: reset all attributes.
            if code == 0:
                self._reset_state()

            # SGR 1: bold (increased intensity).
            elif code == 1:
                self.bold = True
            # SGR 2: faint (decreased intensity).
            elif code == 2:
                self.faint = True
            # SGR 3: italic.
            elif code == 3:
                self.italic = True
            # SGR 4: underline.
            elif code == 4:
                self.underline = True
            # SGR 5: blink.
            elif code == 5:
                self.blink = True
            # SGR 7: reverse video.
            elif code == 7:
                self.reverse = True
            # SGR 9: strikethrough (crossed-out).
            elif code == 9:
                self.strikethrough = True

            # SGR 22: normal intensity (resets both bold and faint).
            elif code == 22:
                self.bold = False
                self.faint = False
            # SGR 23: not italic.
            elif code == 23:
                self.italic = False
            # SGR 24: not underlined.
            elif code == 24:
                self.underline = False
            # SGR 25: not blinking.
            elif code == 25:
                self.blink = False
            # SGR 27: not reversed.
            elif code == 27:
                self.reverse = False
            # SGR 29: not crossed-out.
            elif code == 29:
                self.strikethrough = False

            # SGR 53: overline.
            elif code == 53:
                self.overline = True
            # SGR 55: not overlined.
            elif code == 55:
                self.overline = False

            # SGR 39: default foreground color.
            elif code == 39:
                self.fg_color = None
            # SGR 49: default background color.
            elif code == 49:
                self.bg_color = None

            # SGR 30-37, 90-97: named foreground colors.
            elif code in _SGR_FG_COLORS:
                self.fg_color = _SGR_FG_COLORS[code]
            # SGR 40-47, 100-107: named background colors.
            elif code in _SGR_BG_COLORS:
                self.bg_color = _SGR_BG_COLORS[code]

            # SGR 38/48: extended color (256-color indexed or 24-bit RGB).
            elif code in (38, 48):
                if len(values) < 2:
                    continue
                mode = values.pop(0)
                if mode == 5:
                    # 256-color indexed: 38;5;n or 48;5;n.
                    color_idx = values.pop(0)
                    if 0 <= color_idx <= 255:
                        if code == 38:
                            self.fg_color = f"C{color_idx}"
                        else:
                            self.bg_color = f"C{color_idx}"
                elif mode == 2:
                    # 24-bit RGB: 38;2;r;g;b or 48;2;r;g;b.
                    # Quantized to the nearest 256-color entry.
                    if len(values) < 3:
                        continue
                    r, g, b = values.pop(0), values.pop(0), values.pop(0)
                    if all(0 <= v <= 255 for v in (r, g, b)):
                        nearest = _nearest_256(r, g, b)
                        if code == 38:
                            self.fg_color = f"C{nearest}"
                        else:
                            self.bg_color = f"C{nearest}"

    def get_tokens_unprocessed(
        self, text: str
    ) -> Iterator[tuple[int, _TokenType, str]]:
        """Parse ANSI escape sequences from ``text`` and yield styled tokens.

        Only SGR sequences (CSI + ``m``) update the styling state. All other escape
        sequences are consumed and stripped from the output.
        """
        self._reset_state()
        for match in _ANSI_ESCAPE_RE.finditer(text):
            sgr_params = match.group("sgr_params")
            plain = match.group("text")

            if sgr_params is not None:
                self._process_sgr(sgr_params)
            elif plain is not None:
                yield match.start(), self._current_token, plain


# --- Filter ---


class AnsiFilter(Filter):
    """Custom filter transforming a particular kind of token (``Generic.Output`` by
    default) into ANSI tokens."""

    def __init__(self, **options) -> None:
        """Initialize an ``AnsiColorLexer`` and configure the ``token_type`` to be
        colorized.

        .. note::
            Only one ``token_type`` is supported. All Pygments session lexers
            (``ShellSessionBaseLexer`` and the manually-maintained list in
            ``collect_session_lexers``) emit terminal output exclusively as
            ``Generic.Output``. No upstream issue or PR proposes splitting output into
            additional token types (like ``Generic.Error`` for stderr). If that changes,
            this filter would need to accept a set of token types instead of a single
            one. See `pygments#1148
            <https://github.com/pygments/pygments/issues/1148>`_ and `pygments#2499
            <https://github.com/pygments/pygments/issues/2499>`_ for the closest
            related discussions.
        """
        super().__init__(**options)
        self.ansi_lexer = AnsiColorLexer()
        self.token_type = string_to_tokentype(
            options.get("token_type", DEFAULT_TOKEN_TYPE),
        )

    def filter(
        self, lexer: Lexer | None, stream: Iterable[tuple[_TokenType, str]]
    ) -> Iterator[tuple[_TokenType, str]]:
        """Transform each token of ``token_type`` type into a stream of ANSI tokens."""
        for ttype, value in stream:
            if ttype == self.token_type:
                yield from self.ansi_lexer.get_tokens(value)
            else:
                yield ttype, value


# --- Session lexer factory ---


class _AnsiSessionMeta(LexerMeta):
    """Metaclass that creates ANSI-capable variants of session lexers."""

    def __new__(cls, name, bases, dct):
        """Set up class properties for new ANSI-capable lexers.

        - Adds an ``ANSI`` prefix to the lexer's name.
        - Replaces all ``aliases`` IDs from the parent lexer with variants prefixed with
            ``ansi-``.
        """
        new_cls = super().__new__(cls, name, bases, dct)
        new_cls.name = f"ANSI {new_cls.name}"
        new_cls.aliases = tuple(f"ansi-{alias}" for alias in new_cls.aliases)
        return new_cls


class _AnsiFilterMixin(Lexer):
    def __init__(self, *args, **kwargs) -> None:
        """Add ``TokenMergeFilter`` and ``AnsiFilter`` to the filter chain.

        Session lexers parse code blocks line by line to differentiate inputs and outputs.
        Each output line ends up encapsulated into a ``Generic.Output`` token. The
        ``TokenMergeFilter`` consolidates contiguous output lines into a single token,
        then ``AnsiFilter`` transforms the merged output into ANSI-styled tokens.
        """
        super().__init__(*args, **kwargs)
        self.filters.append(TokenMergeFilter())
        self.filters.append(AnsiFilter())


def collect_session_lexers() -> Iterator[type[Lexer]]:
    """Retrieve all lexers producing shell-like sessions in Pygments.

    This function contains a manually-maintained list of lexers, to which we dynamically
    add lexers inheriting from ``ShellSessionBaseLexer``.

    .. hint::

        To help maintain this list, there is `a test that will fail
        <https://github.com/kdeldycke/click-extra/blob/main/tests/test_pygments.py>`_
        if a new REPL/terminal-like lexer is added to Pygments but not referenced here.
    """
    yield from [
        DylanConsoleLexer,
        ElixirConsoleLexer,
        ErlangShellLexer,
        GAPConsoleLexer,
        JuliaConsoleLexer,
        MatlabSessionLexer,
        OutputLexer,
        PostgresConsoleLexer,
        PsyshConsoleLexer,
        PythonConsoleLexer,
        RConsoleLexer,
        RubyConsoleLexer,
        SqliteConsoleLexer,
    ]

    for lexer in lexers._iter_lexerclasses():
        if ShellSessionBaseLexer in lexer.__bases__:
            yield lexer


LEXER_MAP: dict[type[Lexer], type[Lexer]] = {}
"""Map original session lexers to their ANSI-capable variants."""


# Auto-generate the ANSI variant of all session lexers.
for _original_lexer in collect_session_lexers():
    _new_name = f"Ansi{_original_lexer.__name__}"
    _new_lexer = _AnsiSessionMeta(
        _new_name, (_AnsiFilterMixin, _original_lexer), {}
    )
    locals()[_new_name] = _new_lexer
    LEXER_MAP[_original_lexer] = _new_lexer


# --- Formatter ---


EXTRA_ANSI_CSS: dict[str, str] = {
    "Faint": "opacity: 0.5",
    "Blink": "animation: ansi-blink 1s step-end infinite",
    "Reverse": "filter: invert(1)",
    "Strikethrough": "text-decoration: line-through",
    "Overline": "text-decoration: overline",
}
"""SGR attributes that Pygments' style system cannot express.

Maps ``Token.Ansi`` component names to CSS declarations. Used by
``AnsiHtmlFormatter.get_style_defs`` for standalone rendering and by the Sphinx
extension to inject a dedicated stylesheet.
"""


class AnsiHtmlFormatter(HtmlFormatter):
    """HTML formatter with ANSI color support.

    Extends Pygments' ``HtmlFormatter`` to handle compound ``Token.Ansi.*`` tokens by
    decomposing them into individual CSS classes, and augments the base style with ANSI
    color definitions for the 256-color indexed palette.
    """

    name = "ANSI HTML"
    aliases: ClassVar[list[str]] = ["ansi-html"]

    def __init__(self, **kwargs) -> None:
        """Intercept the ``style`` argument to augment it with ANSI color support.

        Creates a new style instance that inherits from the one provided by the user, but
        updates its ``styles`` attribute with ANSI token definitions from
        ``_ANSI_STYLES``.
        """
        # Same default style as Pygments' HtmlFormatter: ``default``.
        base_style_id = kwargs.setdefault("style", "default")
        base_style = _lookup_style(base_style_id)

        augmented_styles = dict(base_style.styles)
        augmented_styles.update(_ANSI_STYLES)

        new_name = f"Ansi{base_style.__name__}"
        ansi_style = StyleMeta(new_name, (base_style,), {"styles": augmented_styles})
        kwargs["style"] = ansi_style

        super().__init__(**kwargs)

    def get_style_defs(self, arg: str = "") -> str:
        """Extend Pygments' CSS with rules for SGR attributes it cannot express.

        Pygments' style strings support ``bold``, ``italic``, and ``underline``, but
        have no keywords for faint, blink, reverse, strikethrough, or overline. This
        override appends dedicated CSS rules from ``EXTRA_ANSI_CSS`` after the standard
        Pygments CSS output.
        """
        css = super().get_style_defs(arg)
        prefix = arg or ".highlight"
        extra_lines = []
        for attr, declaration in EXTRA_ANSI_CSS.items():
            cls = self._get_css_class(getattr(Ansi, attr))
            extra_lines.append(f"{prefix} .{cls} {{ {declaration} }}")
        extra_lines.append("@keyframes ansi-blink { 50% { opacity: 0 } }")
        return css + "\n" + "\n".join(extra_lines)

    def _get_css_classes(self, ttype: _TokenType) -> str:
        """Decompose compound ``Token.Ansi.*`` tokens into individual CSS classes.

        For a token like ``Token.Ansi.Bold.Red``, Pygments' default behavior produces a
        single concatenated class (``-Ansi-Bold-Red``). This override adds individual
        component classes (``-Ansi-Bold``, ``-Ansi-Red``) so that each maps to its own
        CSS rule from the style dict.
        """
        classes: str = super()._get_css_classes(ttype)
        if ttype[0] == "Ansi":
            classes += " " + " ".join(
                self._get_css_class(getattr(Ansi, part)) for part in ttype[1:]
            )
        return classes
