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
"""Pygments lexers, filters, and formatters for ANSI escape sequences.

Parses ANSI SGR escape sequences (ECMA-48 / ISO 6429) from terminal output and renders
them as colored HTML with CSS classes. Supports the standard 8/16 named colors, the
256-color indexed palette, and 24-bit RGB.

SGR text attributes: bold, faint, italic, underline, blink, reverse video, strikethrough,
and overline.

OSC 8 hyperlinks are rendered as HTML ``<a>`` tags. Other OSC sequences are silently
stripped.

.. note::
    24-bit RGB colors (``SGR 38;2;r;g;b`` and ``48;2;r;g;b``) are preserved by default
    and rendered by ``AnsiHtmlFormatter`` as inline ``style="color: #rrggbb"`` /
    ``style="background-color: #rrggbb"`` spans (CSS classes cannot enumerate 16.7M
    colors). Other token components (bold, named colors, palette indices) keep their
    CSS-class rendering. Pass ``true_color=False`` to ``AnsiColorLexer``, ``AnsiFilter``,
    or any session lexer (via ``get_lexer_by_name(..., true_color=False)``) to opt into
    quantization to the nearest entry in the 256-color palette instead.
"""

from __future__ import annotations

import itertools
import re
from io import StringIO

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
    232 + i: f"#{10 * i + 8:02x}{10 * i + 8:02x}{10 * i + 8:02x}" for i in range(24)
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
    code + 10: name for code, name in _SGR_FG_COLORS.items()
}
"""SGR background color codes (40-47, 100-107) to named color strings.

Derived from ``_SGR_FG_COLORS`` by offsetting each code by +10.
"""

_SGR_ATTR_ON: dict[int, str] = {
    1: "Bold",
    2: "Faint",
    3: "Italic",
    4: "Underline",
    5: "Blink",
    7: "Reverse",
    9: "Strikethrough",
    53: "Overline",
}
"""SGR codes that activate text attributes, mapped to ``Token.Ansi`` component names.

This mapping is the single source of truth for supported text attributes. The attribute
names appear in ``EXTRA_ANSI_CSS``, the Pygments token hierarchy, and CSS class names.
"""

_SGR_ATTR_OFF: dict[int, tuple[str, ...]] = {
    22: ("Bold", "Faint"),
    23: ("Italic",),
    24: ("Underline",),
    25: ("Blink",),
    27: ("Reverse",),
    29: ("Strikethrough",),
    55: ("Overline",),
}
"""SGR codes that deactivate text attributes.

Each code maps to one or more attribute names to reset. SGR 22 (normal intensity) resets
both bold and faint simultaneously.
"""


# --- Token construction ---

Ansi = Token.Ansi
"""Unified token namespace for ANSI styling.

Compound tokens from the lexer (like ``Token.Ansi.Bold.Red``) and individual style
components (like ``Token.Ansi.Red``) share this single namespace. The formatter
decomposes compound tokens into individual CSS classes at render time.
"""

_AnsiLinkStart = Token.AnsiLinkStart
"""Structural token emitted at the start of an OSC 8 hyperlink.

The token value carries the raw URL. ``AnsiHtmlFormatter`` converts these into HTML
``<a>`` tags.
"""

_AnsiLinkEnd = Token.AnsiLinkEnd
"""Structural token emitted at the end of an OSC 8 hyperlink."""

_SAFE_URL_SCHEMES = frozenset(("ftp", "ftps", "http", "https", "mailto"))
"""Allowed URL schemes for OSC 8 hyperlinks.

Only URLs with one of these schemes are emitted as link tokens. All other URLs are
silently stripped to prevent ``javascript:`` and other injection vectors.
"""


def _has_safe_scheme(url: str) -> bool:
    """Return ``True`` if ``url`` starts with a scheme in ``_SAFE_URL_SCHEMES``."""
    colon = url.find(":")
    return colon > 0 and url[:colon].lower() in _SAFE_URL_SCHEMES


# --- Style generation ---


def _build_ansi_styles() -> dict[_TokenType, str]:
    """Build the Pygments style dict mapping ``Token.Ansi.*`` to CSS property strings.

    Registers text attributes, 16 named colors (foreground and background), and the full
    256-color indexed palette.
    """
    styles: dict[_TokenType, str] = {}

    # All SGR text attributes are intentionally absent from this style dict.
    # Furo's dark-mode CSS generator adds a `color: #D0D0D0` fallback to every token
    # in the style dict. For attribute tokens (like Underline or Strikethrough), this
    # fallback overrides actual foreground colors on compound tokens when the attribute
    # rule appears later in the CSS cascade than the color rule.
    # Attribute styling is handled separately by EXTRA_ANSI_CSS, injected via
    # AnsiHtmlFormatter.get_token_style_defs.

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
    r"|\x1b\]8;[^;]*;(?P<osc8_uri>[^\x07\x1b]*)(?:\x07|\x1b\\)"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[()][A-B012]"
    r"|\x1b.?"
    r"|(?P<text>[^\x1b]+)",
)
"""Single-pass regex for ANSI escape sequence parsing.

Alternatives in priority order:

1. CSI SGR sequence (``ESC [`` + params + ``m``): captured for SGR processing.
2. Other CSI sequences (``ESC [`` + params + final byte): consumed and stripped.
3. OSC 8 hyperlink (``ESC ] 8 ; params ; URI ST``): URI captured for link rendering.
4. Other OSC sequences (``ESC ]`` + payload + ``BEL`` or ``ST``): consumed and stripped.
5. VT100 charset selection (``ESC (`` or ``ESC )`` + designator): consumed and stripped.
6. Any other escape sequence: consumed and stripped.
7. Plain text: captured and emitted with the current styling token.
"""


class AnsiColorLexer(Lexer):
    """Lexer for text containing ANSI escape sequences.

    Parses Select Graphic Rendition (SGR) codes and emits compound ``Token.Ansi.*``
    tokens representing the active styling state. OSC 8 hyperlinks emit
    ``Token.AnsiLinkStart`` / ``Token.AnsiLinkEnd`` structural tokens. All other escape
    sequences are silently stripped.

    Supported SGR codes:

    - Text attributes: bold (1), faint (2), italic (3), underline (4), blink (5),
      reverse video (7), strikethrough (9), overline (53), and their resets.
    - Named colors: standard (30-37, 40-47) and bright (90-97, 100-107).
    - 256-color indexed palette (38;5;n, 48;5;n).
    - 24-bit RGB (38;2;r;g;b, 48;2;r;g;b), quantized to the nearest 256-color entry.

    Supported OSC sequences:

    - OSC 8 hyperlinks: rendered as ``<a>`` tags by ``AnsiHtmlFormatter``. Only URLs with
      safe schemes (http, https, mailto, ftp, ftps) are emitted; others are stripped.
    """

    name = "ANSI Color"
    aliases = ("ansi-color", "ansi", "ansi-terminal")

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the lexer.

        :param true_color: Default ``True``. 24-bit RGB sequences are preserved as
            ``Token.Ansi.FG_{rrggbb}`` / ``Token.Ansi.BG_{rrggbb}`` tokens, which
            ``AnsiHtmlFormatter`` renders as inline ``style="color: #rrggbb"`` /
            ``style="background-color: #rrggbb"`` attributes (CSS classes cannot
            enumerate 16.7M colors). Pass ``False`` to quantize 24-bit RGB to the
            nearest entry in the 256-color palette and emit ``Token.Ansi.C{n}`` /
            ``Token.Ansi.BGC{n}`` tokens that map to CSS classes via the style dict.
        """
        self.true_color = bool(kwargs.pop("true_color", True))
        super().__init__(*args, **kwargs)
        self._cached_token: _TokenType = Text
        self._reset_state()

    def _reset_state(self) -> None:
        """Reset all SGR and link state to defaults."""
        self._attrs = dict.fromkeys(_SGR_ATTR_ON.values(), False)
        self.fg_color: str | None = None
        self.bg_color: str | None = None
        self._token_dirty = True
        self._link_active = False

    @property
    def _current_token(self) -> _TokenType:
        """Return the compound token for the current SGR state.

        Each active attribute and color becomes a component of the token path. For
        example, bold red text on a green background produces
        ``Token.Ansi.Bold.Red.BGGreen``.

        Uses a dirty flag to avoid recomputation when the state hasn't changed since the
        last access (common with stripped non-SGR escapes between text fragments).
        """
        if not self._token_dirty:
            return self._cached_token
        components = [name for name, active in self._attrs.items() if active]
        if self.fg_color:
            components.append(self.fg_color)
        if self.bg_color:
            # ``BG_rrggbb`` true-color values are already prefixed; named and
            # palette-indexed values use the conventional ``BG`` prefix.
            components.append(
                self.bg_color
                if self.bg_color.startswith("BG_")
                else "BG" + self.bg_color
            )
        if not components:
            self._cached_token = Text
        else:
            token = Ansi
            for c in components:
                token = getattr(token, c)
            self._cached_token = token
        self._token_dirty = False
        return self._cached_token

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

        self._token_dirty = True
        while values:
            code = values.pop(0)

            # SGR 0: reset all attributes.
            if code == 0:
                self._reset_state()

            # Text attributes: set (SGR 1-9, 53) or reset (SGR 22-29, 55).
            elif code in _SGR_ATTR_ON:
                self._attrs[_SGR_ATTR_ON[code]] = True
            elif code in _SGR_ATTR_OFF:
                for attr in _SGR_ATTR_OFF[code]:
                    self._attrs[attr] = False

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
                    # Quantized to the nearest 256-color entry by default; preserved
                    # as FG_/BG_ hex token components when ``true_color`` is enabled.
                    if len(values) < 3:
                        continue
                    r, g, b = values.pop(0), values.pop(0), values.pop(0)
                    if all(0 <= v <= 255 for v in (r, g, b)):
                        if self.true_color:
                            hex_value = f"{r:02x}{g:02x}{b:02x}"
                            if code == 38:
                                self.fg_color = f"FG_{hex_value}"
                            else:
                                self.bg_color = f"BG_{hex_value}"
                        else:
                            nearest = _nearest_256(r, g, b)
                            if code == 38:
                                self.fg_color = f"C{nearest}"
                            else:
                                self.bg_color = f"C{nearest}"

    def get_tokens_unprocessed(
        self, text: str
    ) -> Iterator[tuple[int, _TokenType, str]]:
        """Parse ANSI escape sequences from ``text`` and yield styled tokens.

        SGR sequences update the styling state. OSC 8 hyperlinks emit structural
        ``Token.AnsiLinkStart`` / ``Token.AnsiLinkEnd`` tokens. All other escape
        sequences are consumed and stripped.
        """
        self._reset_state()
        for match in _ANSI_ESCAPE_RE.finditer(text):
            sgr_params = match.group("sgr_params")
            osc8_uri = match.group("osc8_uri")
            plain = match.group("text")

            if sgr_params is not None:
                self._process_sgr(sgr_params)
            elif osc8_uri is not None:
                pos = match.start()
                if osc8_uri:
                    # OSC 8 open: validate scheme and emit link start.
                    if _has_safe_scheme(osc8_uri):
                        if self._link_active:
                            yield pos, _AnsiLinkEnd, ""
                        yield pos, _AnsiLinkStart, osc8_uri
                        self._link_active = True
                elif self._link_active:
                    # OSC 8 close: emit link end.
                    yield pos, _AnsiLinkEnd, ""
                    self._link_active = False
            elif plain is not None:
                yield match.start(), self._current_token, plain
        # Close any unclosed link at end of input.
        if self._link_active:
            yield len(text), _AnsiLinkEnd, ""
            self._link_active = False


# --- Filter ---


class AnsiFilter(Filter):
    """Custom filter transforming a particular kind of token (``Generic.Output`` by
    default) into ANSI tokens."""

    def __init__(self, **options) -> None:
        """Initialize an ``AnsiColorLexer`` and configure the ``token_type`` to be
        colorized.

        :param true_color: Forwarded to the inner ``AnsiColorLexer`` to control whether
            24-bit RGB sequences are preserved as ``FG_/BG_`` hex tokens for inline-style
            rendering (default ``True``) or quantized to the 256-color palette. See
            :class:`AnsiColorLexer` for details.

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
        true_color = bool(options.pop("true_color", True))
        super().__init__(**options)
        self.ansi_lexer = AnsiColorLexer(true_color=true_color)
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

        :param true_color: Forwarded to ``AnsiFilter``. Default ``True``: 24-bit RGB
            renders via inline styles. Pass ``False`` to quantize to the 256-color palette.
        """
        true_color = bool(kwargs.pop("true_color", True))
        super().__init__(*args, **kwargs)
        self.filters.append(TokenMergeFilter())
        self.filters.append(AnsiFilter(true_color=true_color))


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
    _new_lexer = _AnsiSessionMeta(_new_name, (_AnsiFilterMixin, _original_lexer), {})
    locals()[_new_name] = _new_lexer
    LEXER_MAP[_original_lexer] = _new_lexer  # type: ignore[assignment]


# --- Formatter ---


EXTRA_ANSI_CSS: dict[str, str] = {
    "Bold": "font-weight: bold",
    "Faint": "opacity: 0.5",
    "Italic": "font-style: italic",
    "Underline": "text-decoration: underline",
    "Blink": "animation: ansi-blink 1s step-end infinite",
    "Reverse": "filter: invert(1)",
    "Strikethrough": "text-decoration: line-through",
    "Overline": "text-decoration: overline",
}
"""All SGR text attribute CSS declarations.

Maps ``Token.Ansi`` component names to CSS declarations. These are kept out of the
Pygments style dict (``_ANSI_STYLES``) to prevent Furo's dark-mode CSS generator from
injecting ``color: #D0D0D0`` fallbacks that conflict with foreground color tokens.

Used by ``AnsiHtmlFormatter.get_token_style_defs`` to inject CSS rules that both
standalone ``pygmentize`` and Furo's dark-mode CSS generator pick up.
"""

_LINK_OPEN = "\ue000"
"""Private Use Area marker injected before the hyperlink URL."""

_LINK_SEP = "\ue001"
"""Private Use Area marker injected after the hyperlink URL."""

_LINK_CLOSE = "\ue002"
"""Private Use Area marker injected at the end of a hyperlink."""

_LINK_MARKER_RE = re.compile(f"{_LINK_OPEN}([^{_LINK_SEP}]*){_LINK_SEP}")
"""Regex matching link-open markers in post-processed HTML.

Captures the HTML-escaped URL between ``_LINK_OPEN`` and ``_LINK_SEP`` for replacement
with an ``<a href="...">`` tag.
"""

_RGB_FG_OPEN = "\ue010"
"""Private Use Area marker injected before a 24-bit foreground hex value."""

_RGB_BG_OPEN = "\ue011"
"""Private Use Area marker injected before a 24-bit background hex value."""

_RGB_SEP = "\ue012"
"""Private Use Area marker separating the hex value from the styled text."""

_RGB_CLOSE = "\ue013"
"""Private Use Area marker closing a 24-bit color span."""

_RGB_MARKER_RE = re.compile(
    f"(?P<kind>[{_RGB_FG_OPEN}{_RGB_BG_OPEN}])(?P<hex>[0-9a-f]{{6}}){_RGB_SEP}"
)
"""Regex matching 24-bit color open markers in post-processed HTML.

Captures the marker kind (foreground or background) and the 6-character hex value for
replacement with a ``<span style="...">`` tag.
"""


class AnsiHtmlFormatter(HtmlFormatter):
    """HTML formatter with ANSI color and hyperlink support.

    Extends Pygments' ``HtmlFormatter`` to handle compound ``Token.Ansi.*`` tokens by
    decomposing them into individual CSS classes, augments the base style with ANSI color
    definitions for the 256-color indexed palette, and renders OSC 8 hyperlinks as HTML
    ``<a>`` tags.
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
        self._ansi_css_cache: dict[_TokenType, str] = {}

    def format_unencoded(self, tokensource, outfile) -> None:
        """Render tokens to HTML, converting OSC 8 link and 24-bit RGB markers to tags.

        Replaces ``Token.AnsiLinkStart`` / ``Token.AnsiLinkEnd`` with Unicode Private
        Use Area markers, strips ``FG_/BG_`` 24-bit RGB components from compound tokens
        and replaces them with PUA markers carrying the hex value, delegates to Pygments'
        HTML rendering, then post-processes the output to swap markers for ``<a>`` and
        inline-styled ``<span>`` tags.
        """
        buffer = StringIO()
        super().format_unencoded(
            self._inject_link_markers(self._inject_rgb_markers(tokensource)),
            buffer,
        )
        html = buffer.getvalue()
        html = _LINK_MARKER_RE.sub(lambda m: f'<a href="{m.group(1)}">', html)
        html = html.replace(_LINK_CLOSE, "</a>")
        html = _RGB_MARKER_RE.sub(self._rgb_marker_to_span, html)
        html = html.replace(_RGB_CLOSE, "</span>")
        outfile.write(html)

    @staticmethod
    def _rgb_marker_to_span(match: re.Match) -> str:
        """Replace a 24-bit RGB open marker with a ``<span>`` tag carrying inline style.

        ``_RGB_FG_OPEN`` produces a ``color`` declaration; ``_RGB_BG_OPEN`` produces a
        ``background-color`` declaration.
        """
        prop = "color" if match.group("kind") == _RGB_FG_OPEN else "background-color"
        return f'<span style="{prop}: #{match.group("hex")}">'

    @staticmethod
    def _inject_rgb_markers(
        tokensource: Iterable[tuple[_TokenType, str]],
    ) -> Iterator[tuple[_TokenType, str]]:
        """Strip ``FG_/BG_`` components from Ansi tokens and wrap text in PUA markers.

        24-bit RGB colors cannot be expressed as a finite set of CSS classes, so they
        bypass the style dict entirely. The hex value travels with the text via PUA
        markers and gets converted to inline ``style="..."`` attributes during HTML
        post-processing. Non-RGB token components (Bold, named colors, palette indices)
        survive on the rebuilt token and continue to render through the standard CSS
        class mechanism.
        """
        for ttype, value in tokensource:
            # Only Ansi compound tokens may carry FG_/BG_ components.
            if len(ttype) <= 1 or ttype[0] != "Ansi":
                yield ttype, value
                continue

            fg_hex: str | None = None
            bg_hex: str | None = None
            kept: list[str] = []
            for component in ttype[1:]:
                if component.startswith("FG_") and len(component) == 9:
                    fg_hex = component[3:]
                elif component.startswith("BG_") and len(component) == 9:
                    bg_hex = component[3:]
                else:
                    kept.append(component)

            if fg_hex is None and bg_hex is None:
                yield ttype, value
                continue

            # Rebuild the token without the RGB components. An empty result collapses
            # to ``Text`` so Pygments emits no surrounding span: the inline-style span
            # produced by the marker post-processing is the only wrapper needed.
            new_ttype: _TokenType = Text
            if kept:
                new_ttype = Ansi
                for component in kept:
                    new_ttype = getattr(new_ttype, component)

            prefix = ""
            suffix = ""
            if fg_hex is not None:
                prefix += f"{_RGB_FG_OPEN}{fg_hex}{_RGB_SEP}"
                suffix = _RGB_CLOSE + suffix
            if bg_hex is not None:
                prefix += f"{_RGB_BG_OPEN}{bg_hex}{_RGB_SEP}"
                suffix = _RGB_CLOSE + suffix

            yield new_ttype, prefix + value + suffix

    @staticmethod
    def _inject_link_markers(
        tokensource: Iterable[tuple[_TokenType, str]],
    ) -> Iterator[tuple[_TokenType, str]]:
        """Replace link tokens with PUA-marked text for post-processing.

        ``Token.AnsiLinkStart`` becomes the URL wrapped in ``_LINK_OPEN`` /
        ``_LINK_SEP``. ``Token.AnsiLinkEnd`` becomes ``_LINK_CLOSE``. All other tokens
        pass through unchanged.
        """
        for ttype, value in tokensource:
            if ttype is _AnsiLinkStart:
                yield ttype, f"{_LINK_OPEN}{value}{_LINK_SEP}"
            elif ttype is _AnsiLinkEnd:
                yield ttype, _LINK_CLOSE
            else:
                yield ttype, value

    def get_token_style_defs(self, arg=None):
        """Extend Pygments' token CSS with rules for SGR attributes it cannot express.

        Pygments' style strings support ``bold``, ``italic``, and ``underline``, but
        have no keywords for faint, blink, reverse, strikethrough, or overline. This
        override appends dedicated CSS rules from ``EXTRA_ANSI_CSS`` after the standard
        Pygments token CSS output.

        Overriding ``get_token_style_defs`` (rather than ``get_style_defs``) ensures
        that Furo's dark-mode CSS generator, which calls this method directly, also
        picks up the extra rules.
        """
        lines = super().get_token_style_defs(arg)
        prefix = self.get_css_prefix(arg)
        for attr, declaration in EXTRA_ANSI_CSS.items():
            cls = self._get_css_class(  # type: ignore[attr-defined]
                getattr(Ansi, attr),
            )
            lines.append(f"{prefix(cls)} {{ {declaration} }}")
        lines.append("@keyframes ansi-blink { 50% { opacity: 0 } }")
        # OSC 8 hyperlink styling: inherit text color from ANSI tokens.
        container = f".{self.cssclass} " if self.cssclass else ""
        lines.append(f"{container}a {{ color: inherit; text-decoration: underline }}")
        return lines

    def _get_css_classes(self, ttype: _TokenType) -> str:
        """Decompose compound ``Token.Ansi.*`` tokens into individual CSS classes.

        For a token like ``Token.Ansi.Bold.Red``, Pygments' default behavior produces a
        single concatenated class (``-Ansi-Bold-Red``). This override adds individual
        component classes (``-Ansi-Bold``, ``-Ansi-Red``) so that each maps to its own
        CSS rule from the style dict.

        Results are cached per token type since the same compound tokens recur frequently
        in typical terminal output.
        """
        cached = self._ansi_css_cache.get(ttype)
        if cached is not None:
            return cached
        classes: str = super()._get_css_classes(ttype)  # type: ignore[misc]
        if ttype[0] == "Ansi":
            classes += (
                " "
                + " ".join(
                    self._get_css_class(  # type: ignore[attr-defined]
                        getattr(Ansi, part),
                    )
                    for part in ttype[1:]
                )
            )
        self._ansi_css_cache[ttype] = classes
        return classes
