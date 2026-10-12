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

OSC 8 hyperlinks are rendered as HTML `<a>` tags. Other OSC sequences are silently
stripped.

```{note}
24-bit RGB colors (`SGR 38;2;r;g;b` and `48;2;r;g;b`) are preserved by default
and rendered by `AnsiHtmlFormatter` as inline `style="color: #rrggbb"` /
`style="background-color: #rrggbb"` spans (CSS classes cannot enumerate 16.7M
colors). Other token components (bold, named colors, palette indices) keep their
CSS-class rendering. Pass `true_color=False` to `AnsiColorLexer`, `AnsiFilter`,
or any session lexer (via `get_lexer_by_name(..., true_color=False)`) to opt into
quantization to the nearest entry in the 256-color palette instead.
```
"""

from __future__ import annotations

import re
from functools import cache
from io import StringIO
from typing import cast

from ._utils import missing_extra_message

try:
    import pygments  # noqa: F401
except ImportError as err:
    raise ImportError(missing_extra_message("pygments", subject="This module")) from err

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
from pygments.style import Style, StyleMeta
from pygments.token import Generic, Text, Token, string_to_tokentype

from .styling import (
    _ANSI_16_RGB,
    _ANSI_NAMES,
    _ATTR_CSS,
    _SGR_ATTRIBUTES,
    _apply_sgr_codes,
    _is_rgb,
    _nearest_256,
    _palette_to_rgb,
    _rgb_to_hex,
    _sgr_params,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from typing import Any, ClassVar

    from pygments.token import _TokenType


# --- Color palettes ---

_NAMED_COLORS: dict[str, str] = {
    prefix + name.capitalize(): _rgb_to_hex(_ANSI_16_RGB[offset + i])
    for prefix, offset in (("", 0), ("Bright", 8))
    for i, name in enumerate(_ANSI_NAMES)
}
"""Standard 8 colors and their bright variants, mapped to hex values.

Keyed by `Token.Ansi` component name (`Red`, `BrightRed`, ...) and derived
from the canonical {data}`click_extra.styling._ANSI_16_RGB` palette, so the
documentation renders named ANSI colors with the exact values `Style` uses
for CSS output and contrast math.
"""

_PALETTE_256: dict[int, str] = {
    idx: _rgb_to_hex(_palette_to_rgb(idx)) for idx in range(256)
}
"""256-color indexed palette mapped to hex values.

Derived index by index from {func}`click_extra.styling._palette_to_rgb`:
indices 0-15 are the system colors (the canonical named palette, like real
terminals which render those slots with their theme), 16-231 the 6x6x6 color
cube, and 232-255 the grayscale ramp.
"""


_ATTR_COMPONENTS: dict[str, str] = {
    attr: "Faint" if attr == "dim" else attr.capitalize()
    for attr in _SGR_ATTRIBUTES.values()
}
"""`Token.Ansi` component name of each boolean text attribute.

Keyed by the {class}`~click_extra.styling.Style` field names the SGR decoder of
{mod}`click_extra.styling` fills, in SGR code order, so the lexer and
{meth}`~click_extra.styling.Style.from_ansi` cannot disagree on which code
switches which attribute on. The component names appear in `EXTRA_ANSI_CSS`,
the Pygments token hierarchy, and CSS class names. `dim` is spelled `Faint`
there, the name ECMA-48 gives SGR 2.
"""


# --- Token construction ---

Ansi = Token.Ansi
"""Unified token namespace for ANSI styling.

Compound tokens from the lexer (like `Token.Ansi.Bold.Red`) and individual style
components (like `Token.Ansi.Red`) share this single namespace. The formatter
decomposes compound tokens into individual CSS classes at render time.
"""

_AnsiLinkStart = Token.AnsiLinkStart
"""Structural token emitted at the start of an OSC 8 hyperlink.

The token value carries the raw URL. `AnsiHtmlFormatter` converts these into HTML
`<a>` tags.
"""

_AnsiLinkEnd = Token.AnsiLinkEnd
"""Structural token emitted at the end of an OSC 8 hyperlink."""

_SAFE_URL_SCHEMES = frozenset(("ftp", "ftps", "http", "https", "mailto"))
"""Allowed URL schemes for OSC 8 hyperlinks.

Only URLs with one of these schemes are emitted as link tokens. All other URLs are
silently stripped to prevent `javascript:` and other injection vectors.
"""


def _has_safe_scheme(url: str) -> bool:
    """Return `True` if `url` starts with a scheme in `_SAFE_URL_SCHEMES`."""
    colon = url.find(":")
    return colon > 0 and url[:colon].lower() in _SAFE_URL_SCHEMES


def _ansi_token(components: Sequence[str]) -> _TokenType:
    """Build the compound `Token.Ansi.*` token holding `components`, in order.

    Pygments creates a token type on its first attribute access, so walking down
    from `Ansi` both looks the compound token up and defines it. No component at
    all collapses to `Text`, which Pygments renders without a surrounding span.
    """
    if not components:
        return Text
    token: _TokenType = Ansi
    for component in components:
        token = getattr(token, component)
    return token


def _color_component(color: object, ground: str, *, true_color: bool) -> str | None:
    """Name the token component of a color the SGR decoder parsed, or `None`.

    `ground` is `fg` or `bg`, the state key the color sits under. A named ANSI
    color becomes its capitalized component (`red` to `Red`, `bright_red` to
    `BrightRed`), a palette index `n` becomes `C{n}`, and an RGB triplet becomes
    a `FG_{rrggbb}` or `BG_{rrggbb}` hex component under `true_color`, or the
    `C{n}` of its nearest palette entry otherwise. A background component other
    than the hex one takes the `BG` prefix.

    A value no terminal would honor, like a palette index or a channel past
    255, names nothing: the text renders as if that color were never set.
    """
    if isinstance(color, str):
        name = "".join(part.capitalize() for part in color.split("_"))
    elif _is_rgb(color):
        if not all(0 <= channel <= 255 for channel in color):
            return None
        if true_color:
            return f"{ground.upper()}_{_rgb_to_hex(color)[1:]}"
        name = f"C{_nearest_256(*color)}"
    elif isinstance(color, int) and 0 <= color <= 255:
        name = f"C{color}"
    else:
        return None
    return name if ground == "fg" else f"BG{name}"


# --- Style generation ---


def _build_ansi_styles() -> dict[_TokenType, str]:
    """Build the Pygments style dict mapping `Token.Ansi.*` to CSS property strings.

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

Computed once at import time. Used by `AnsiHtmlFormatter` to augment the base Pygments
style with ANSI color support.
"""


# --- Lexer ---

DEFAULT_TOKEN_TYPE = Generic.Output
"""Default Pygments token type to render with ANSI support.

Defaults to `Generic.Output` tokens, as this is the token type used by all REPL-like
and terminal session lexers.
"""

DEFAULT_TRUE_COLOR = True
"""Whether 24-bit RGB colors are kept as such, rather than quantized.

The default of the `true_color` option every ANSI lexer and filter of this
module takes: {class}`AnsiColorLexer`, {class}`AnsiFilter`, and the session
lexers of {data}`LEXER_MAP`, which hand the option down to the lexers they wrap.
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

1. CSI SGR sequence (`ESC [` + params + `m`): captured for SGR processing.
2. Other CSI sequences (`ESC [` + params + final byte): consumed and stripped.
3. OSC 8 hyperlink (`ESC ] 8 ; params ; URI ST`): URI captured for link rendering.
4. Other OSC sequences (`ESC ]` + payload + `BEL` or `ST`): consumed and stripped.
5. VT100 charset selection (`ESC (` or `ESC )` + designator): consumed and stripped.
6. Any other escape sequence: consumed and stripped.
7. Plain text: captured and emitted with the current styling token.
"""


class AnsiColorLexer(Lexer):
    """Lexer for text containing ANSI escape sequences.

    Parses Select Graphic Rendition (SGR) codes and emits compound `Token.Ansi.*`
    tokens representing the active styling state. OSC 8 hyperlinks emit
    `Token.AnsiLinkStart` / `Token.AnsiLinkEnd` structural tokens. All other escape
    sequences are silently stripped.

    Supported SGR codes:

    - Text attributes: bold (1), faint (2), italic (3), underline (4), blink (5),
      reverse video (7), strikethrough (9), overline (53), and their resets.
    - Named colors: standard (30-37, 40-47) and bright (90-97, 100-107).
    - 256-color indexed palette (38;5;n, 48;5;n).
    - 24-bit RGB (38;2;r;g;b, 48;2;r;g;b), quantized to the nearest 256-color entry.

    Supported OSC sequences:

    - OSC 8 hyperlinks: rendered as `<a>` tags by `AnsiHtmlFormatter`. Only URLs with
      safe schemes (http, https, mailto, ftp, ftps) are emitted; others are stripped.
    """

    name = "ANSI Color"
    aliases = ("ansi-color", "ansi", "ansi-terminal")

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the lexer.

        :param true_color: Default {data}`DEFAULT_TRUE_COLOR`. 24-bit RGB sequences
            are preserved as ``Token.Ansi.FG_{rrggbb}`` / ``Token.Ansi.BG_{rrggbb}``
            tokens, which `AnsiHtmlFormatter` renders as inline
            `style="color: #rrggbb"` / `style="background-color: #rrggbb"`
            attributes (CSS classes cannot enumerate 16.7M colors). Pass `False` to
            quantize 24-bit RGB to the nearest entry in the 256-color palette and
            emit ``Token.Ansi.C{n}`` / ``Token.Ansi.BGC{n}`` tokens that map to CSS
            classes via the style dict.
        """
        self.true_color = bool(kwargs.pop("true_color", DEFAULT_TRUE_COLOR))
        super().__init__(*args, **kwargs)
        self._reset_state()

    def _reset_state(self) -> None:
        """Reset the SGR state, the token built from it and the link state."""
        self._state: dict[str, Any] = {}
        self._token_state: dict[str, Any] = {}
        self._cached_token: _TokenType = Text
        self._link_active = False

    def _components(self) -> list[str]:
        """Name the token components of the current SGR state, attributes first.

        Attributes come in SGR code order, then the foreground, then the
        background, each through `_color_component`.
        """
        components = [
            component
            for attr, component in _ATTR_COMPONENTS.items()
            if self._state.get(attr)
        ]
        for ground in ("fg", "bg"):
            color = self._state.get(ground)
            if color is None:
                continue
            component = _color_component(color, ground, true_color=self.true_color)
            if component is not None:
                components.append(component)
        return components

    @property
    def _current_token(self) -> _TokenType:
        """Return the compound token for the current SGR state.

        Each active attribute and color becomes a component of the token path. For
        example, bold red text on a green background produces
        `Token.Ansi.Bold.Red.BGGreen`.

        The token is rebuilt only when the state changed since the last access,
        which an escape landing back on the same state, or a stripped non-SGR
        escape between two text fragments, never does.
        """
        if self._state != self._token_state:
            self._cached_token = _ansi_token(self._components())
            self._token_state = dict(self._state)
        return self._cached_token

    def _process_sgr(self, params: str) -> None:
        """Update the SGR state from a semicolon-separated parameter string.

        The decoding is the one of {mod}`click_extra.styling`, so an escape reads
        the same here as in {func}`~click_extra.styling.split_ansi`: an empty
        parameter is `0`, a full reset, and `\x1b[;31m` is a reset followed by
        a red foreground. The state is keyed by
        {class}`~click_extra.styling.Style` field names, and `_components` maps
        it onto the token hierarchy.
        """
        _apply_sgr_codes(_sgr_params(params), self._state)

    def get_tokens_unprocessed(
        self, text: str
    ) -> Iterator[tuple[int, _TokenType, str]]:
        """Parse ANSI escape sequences from `text` and yield styled tokens.

        SGR sequences update the styling state. OSC 8 hyperlinks emit structural
        `Token.AnsiLinkStart` / `Token.AnsiLinkEnd` tokens. All other escape
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
    """Custom filter transforming a particular kind of token (`Generic.Output` by
    default) into ANSI tokens."""

    def __init__(self, **options) -> None:
        """Initialize an `AnsiColorLexer` and configure the `token_type` to be
        colorized.

        :param true_color: Forwarded to the inner `AnsiColorLexer` to control whether
            24-bit RGB sequences are preserved as `FG_/BG_` hex tokens for inline-style
            rendering (default {data}`DEFAULT_TRUE_COLOR`) or quantized to the
            256-color palette. See {class}`AnsiColorLexer` for details.

        ```{note}
        Only one `token_type` is supported. All Pygments session lexers
        (`ShellSessionBaseLexer` and the manually-maintained list in
        `collect_session_lexers`) emit terminal output exclusively as
        `Generic.Output`. No upstream issue or PR proposes splitting output into
        additional token types (like `Generic.Error` for stderr). If that changes,
        this filter would need to accept a set of token types instead of a single
        one. See [pygments#1148](https://github.com/pygments/pygments/issues/1148) and [pygments#2499](https://github.com/pygments/pygments/issues/2499) for the closest
        related discussions.
        ```
        """
        true_color = bool(options.pop("true_color", DEFAULT_TRUE_COLOR))
        super().__init__(**options)
        self.ansi_lexer = AnsiColorLexer(true_color=true_color)
        self.token_type = string_to_tokentype(
            options.get("token_type", DEFAULT_TOKEN_TYPE),
        )

    def filter(
        self, lexer: Lexer | None, stream: Iterable[tuple[_TokenType, str]]
    ) -> Iterator[tuple[_TokenType, str]]:
        """Transform each token of `token_type` type into a stream of ANSI tokens."""
        for ttype, value in stream:
            if ttype == self.token_type:
                yield from self.ansi_lexer.get_tokens(value)
            else:
                yield ttype, value


# --- Session lexer factory ---


def _ansi_input_lexer(inner_cls: type[Lexer]) -> type[Lexer]:
    r"""Wrap a session's inner lexer so an input line carrying ANSI keeps its colors.

    {class}`~pygments.lexers.shell.ShellSessionBaseLexer` splits a session into
    the commands a user typed and the output they produced, and only the output
    reaches {class}`AnsiFilter`. That split is drawn by matching a prompt, so a
    line the program *printed* is read as input whenever it opens on one: a
    `--help` epilog writing `$ my-cli pick --ripe` is the common case. Its escape
    sequences then reach the inner shell lexer, which has no idea what they are
    and tokenizes `\x1b[36m` as an operator between two runs of text, leaving the
    raw bytes in the rendered page.

    Input carrying no escape is handed to `inner_cls` untouched, so a
    hand-written session keeps its shell highlighting. Input carrying one is
    lexed by {class}`AnsiColorLexer` instead: the line arrived already styled,
    and drawing it the way the terminal does beats syntax-coloring it a second
    time.

    :param inner_cls: the lexer the session applies to its input lines.
    :return: a lexer class routing between `inner_cls` and `AnsiColorLexer`.
    """

    class _AnsiInputLexer(Lexer):
        name = f"ANSI-aware {inner_cls.name}"

        def __init__(self, **options) -> None:
            true_color = bool(options.pop("true_color", DEFAULT_TRUE_COLOR))
            super().__init__(**options)
            self.plain_lexer = inner_cls(**options)
            self.ansi_lexer = AnsiColorLexer(true_color=true_color)

        def get_tokens_unprocessed(
            self, text: str
        ) -> Iterator[tuple[int, _TokenType, str]]:
            if "\x1b" not in text:
                yield from self.plain_lexer.get_tokens_unprocessed(text)
                return
            # Re-indexed on what is emitted: AnsiColorLexer drops the escape
            # bytes but still counts their width in the positions it reports,
            # and `do_insertions` splits the first token when its index runs
            # ahead of the text consumed, dropping the prompt mid-word.
            position = 0
            for _, ttype, value in self.ansi_lexer.get_tokens_unprocessed(text):
                yield position, ttype, value
                position += len(value)

    return _AnsiInputLexer


class _AnsiSessionMeta(LexerMeta):
    """Metaclass that creates ANSI-capable variants of session lexers."""

    def __new__(cls, name, bases, dct):
        """Set up class properties for new ANSI-capable lexers.

        - Adds an `ANSI` prefix to the lexer's name.
        - Replaces all `aliases` IDs from the parent lexer with variants prefixed with
            `ansi-`.
        - Wraps the inner lexer of a shell session so ANSI survives an input line,
            see {func}`_ansi_input_lexer`. Only the shell-session family has one.
        """
        new_cls = super().__new__(cls, name, bases, dct)
        new_cls.name = f"ANSI {new_cls.name}"
        new_cls.aliases = tuple(f"ansi-{alias}" for alias in new_cls.aliases)
        inner_cls = getattr(new_cls, "_innerLexerCls", None)
        if inner_cls is not None:
            new_cls._innerLexerCls = _ansi_input_lexer(inner_cls)
        return new_cls


class _AnsiFilterMixin(Lexer):
    """Mixin appending `TokenMergeFilter` and `AnsiFilter` to a session
    lexer's filter chain so its terminal output renders ANSI colors."""

    def __init__(self, *args, **kwargs) -> None:
        """Add `TokenMergeFilter` and `AnsiFilter` to the filter chain.

        Session lexers parse code blocks line by line to differentiate inputs and outputs.
        Each output line ends up encapsulated into a `Generic.Output` token. The
        `TokenMergeFilter` consolidates contiguous output lines into a single token,
        then `AnsiFilter` transforms the merged output into ANSI-styled tokens.

        :param true_color: Forwarded to `AnsiFilter`. Default
            {data}`DEFAULT_TRUE_COLOR`: 24-bit RGB renders via inline styles. Pass
            `False` to quantize to the 256-color palette.
        """
        true_color = bool(kwargs.pop("true_color", DEFAULT_TRUE_COLOR))
        super().__init__(*args, **kwargs)
        # Put the option back where Pygments builds the inner lexer from, as
        # ShellSessionBaseLexer instantiates it with `**self.options`.
        self.options["true_color"] = true_color
        self.filters.append(TokenMergeFilter())
        self.filters.append(AnsiFilter(true_color=true_color))


def collect_session_lexers() -> Iterator[type[Lexer]]:
    """Retrieve all lexers producing shell-like sessions in Pygments.

    This function contains a manually-maintained list of lexers, to which we dynamically
    add lexers inheriting from `ShellSessionBaseLexer`.

    ```{hint}

    To help maintain this list, there is [a test that will fail](https://github.com/kdeldycke/click-extra/blob/main/tests/test_pygments.py)
    if a new REPL/terminal-like lexer is added to Pygments but not referenced here.
    ```
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


_BLINK_CSS = "animation: ansi-blink 1s step-end infinite"
"""The declaration animating a `Blink` span, through the `ansi-blink` keyframes.

CSS has no declaration for blinking text, which is why
{data}`click_extra.styling._ATTR_CSS` leaves the attribute empty. The keyframes
are emitted beside the token rules by `AnsiHtmlFormatter._extra_ansi_css_lines`.
"""

EXTRA_ANSI_CSS: dict[str, str] = {
    component: _BLINK_CSS if attr == "blink" else ": ".join(_ATTR_CSS[attr])
    for attr, component in _ATTR_COMPONENTS.items()
}
"""All SGR text attribute CSS declarations.

Maps `Token.Ansi` component names to CSS declarations, taken from
{data}`click_extra.styling._ATTR_CSS` so an attribute renders the same in a
documentation code block as in the HTML
{meth}`~click_extra.styling.Style.to_css` writes. `Blink` alone takes
`_BLINK_CSS`. The rules are kept out of the Pygments style dict (`_ANSI_STYLES`)
to prevent Furo's dark-mode CSS generator from injecting `color: #D0D0D0`
fallbacks that conflict with foreground color tokens.

Used by `AnsiHtmlFormatter.get_token_style_defs` to inject CSS rules that both
standalone `pygmentize` and Furo's dark-mode CSS generator pick up.
"""

_LINK_OPEN = "\ue000"
"""Private Use Area marker injected before the hyperlink URL."""

_LINK_SEP = "\ue001"
"""Private Use Area marker injected after the hyperlink URL."""

_LINK_CLOSE = "\ue002"
"""Private Use Area marker injected at the end of a hyperlink."""

_LINK_MARKER_RE = re.compile(f"{_LINK_OPEN}([^{_LINK_SEP}]*){_LINK_SEP}")
"""Regex matching link-open markers in post-processed HTML.

Captures the URL between `_LINK_OPEN` and `_LINK_SEP`, for replacement with an
`<a href="...">` tag by `AnsiHtmlFormatter._link_marker_to_anchor`.
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
replacement with a `<span style="...">` tag.
"""


@cache
def _ansi_style(base_style: type[Style]) -> type[Style]:
    """Subclass `base_style` with the ANSI color tokens of `_ANSI_STYLES` added.

    Cached per base style: Sphinx builds a formatter for every highlighted block,
    and a style class holding the same hundreds of token entries serves them all.
    """
    augmented_styles = dict(base_style.styles)
    augmented_styles.update(_ANSI_STYLES)
    return cast(
        "type[Style]",
        StyleMeta(
            f"Ansi{base_style.__name__}", (base_style,), {"styles": augmented_styles}
        ),
    )


class AnsiHtmlFormatter(HtmlFormatter):
    """HTML formatter with ANSI color and hyperlink support.

    Extends Pygments' `HtmlFormatter` to handle compound `Token.Ansi.*` tokens by
    decomposing them into individual CSS classes, augments the base style with ANSI color
    definitions for the 256-color indexed palette, and renders OSC 8 hyperlinks as HTML
    `<a>` tags.
    """

    name = "ANSI HTML"
    aliases: ClassVar[list[str]] = ["ansi-html"]

    _css_classes: ClassVar[dict[tuple[str, _TokenType], str]] = {}
    """CSS classes of each token already decomposed, keyed by class prefix.

    Shared by every instance: the classes a token maps to depend on nothing but
    the formatter's `classprefix` option and the token itself, and the same
    compound tokens recur in every terminal capture of a build.
    """

    def __init__(self, **kwargs) -> None:
        """Intercept the `style` argument to augment it with ANSI color support.

        The formatter runs on a subclass of the style provided by the user, whose
        `styles` attribute is extended with the ANSI token definitions of
        `_ANSI_STYLES`, see `_ansi_style`.
        """
        # Same default style as Pygments' HtmlFormatter: `default`.
        kwargs["style"] = _ansi_style(
            _lookup_style(kwargs.setdefault("style", "default"))
        )
        super().__init__(**kwargs)

    def format_unencoded(self, tokensource, outfile) -> None:
        """Render tokens to HTML, converting OSC 8 link and 24-bit RGB markers to tags.

        Replaces `Token.AnsiLinkStart` / `Token.AnsiLinkEnd` with Unicode Private
        Use Area markers, strips `FG_/BG_` 24-bit RGB components from compound tokens
        and replaces them with PUA markers carrying the hex value, delegates to Pygments'
        HTML rendering, then post-processes the output to swap markers for `<a>` and
        inline-styled `<span>` tags.
        """
        buffer = StringIO()
        super().format_unencoded(
            self._inject_link_markers(self._inject_rgb_markers(tokensource)),
            buffer,
        )
        html = buffer.getvalue()
        html = _LINK_MARKER_RE.sub(self._link_marker_to_anchor, html)
        html = html.replace(_LINK_CLOSE, "</a>")
        html = _RGB_MARKER_RE.sub(self._rgb_marker_to_span, html)
        html = html.replace(_RGB_CLOSE, "</span>")
        outfile.write(html)

    @staticmethod
    def _link_marker_to_anchor(match: re.Match) -> str:
        """Replace a link-open marker with an `<a>` tag pointing to the captured URL.

        Pygments escapes `&`, `<` and `>` in token text. It stopped escaping quotes in
        2.21.0, where `escape_html()` gave way to `html.escape(value, quote=False)`.
        Quotes are escaped here, at the point the URL enters an attribute value: a bare
        `"` closes `href` and lets the rest of the URL through as markup. The entities
        are the ones older Pygments produced, so the rendered link is the same on both
        sides of that release.
        """
        url = match.group(1).replace('"', "&quot;").replace("'", "&#39;")
        return f'<a href="{url}">'

    @staticmethod
    def _rgb_marker_to_span(match: re.Match) -> str:
        """Replace a 24-bit RGB open marker with a `<span>` tag carrying inline style.

        `_RGB_FG_OPEN` produces a `color` declaration; `_RGB_BG_OPEN` produces a
        `background-color` declaration.
        """
        prop = "color" if match.group("kind") == _RGB_FG_OPEN else "background-color"
        return f'<span style="{prop}: #{match.group("hex")}">'

    @staticmethod
    def _inject_rgb_markers(
        tokensource: Iterable[tuple[_TokenType, str]],
    ) -> Iterator[tuple[_TokenType, str]]:
        """Strip `FG_/BG_` components from Ansi tokens and wrap text in PUA markers.

        24-bit RGB colors cannot be expressed as a finite set of CSS classes, so they
        bypass the style dict entirely. The hex value travels with the text via PUA
        markers and gets converted to inline `style="..."` attributes during HTML
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
            # to `Text` so Pygments emits no surrounding span: the inline-style span
            # produced by the marker post-processing is the only wrapper needed.
            new_ttype = _ansi_token(kept)

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

        `Token.AnsiLinkStart` becomes the URL wrapped in `_LINK_OPEN` /
        `_LINK_SEP`. `Token.AnsiLinkEnd` becomes `_LINK_CLOSE`. All other tokens
        pass through unchanged.
        """
        for ttype, value in tokensource:
            if ttype is _AnsiLinkStart:
                yield ttype, f"{_LINK_OPEN}{value}{_LINK_SEP}"
            elif ttype is _AnsiLinkEnd:
                yield ttype, _LINK_CLOSE
            else:
                yield ttype, value

    def _extra_ansi_css_lines(self, arg=None) -> list[str]:
        """CSS for the SGR attributes Pygments cannot express, the blink keyframe
        and the OSC 8 hyperlink rule.

        Pygments' style strings support `bold`, `italic` and `underline` but
        have no keywords for faint, blink, reverse, strikethrough or overline, so
        those are emitted as dedicated declarations from `EXTRA_ANSI_CSS`.
        """
        prefix = self.get_css_prefix(arg)
        lines: list[str] = []
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

    def get_token_style_defs(self, arg=None):
        """Extend Pygments' token CSS with rules for SGR attributes it cannot express.

        Overriding `get_token_style_defs` (rather than `get_style_defs`) ensures
        that Furo's dark-mode CSS generator, which calls this method directly, also
        picks up the extra rules built by `_extra_ansi_css_lines`.
        """
        return super().get_token_style_defs(arg) + self._extra_ansi_css_lines(arg)

    def get_ansi_style_defs(self, arg=None) -> str:
        """Return only this formatter's ANSI CSS, dropping Pygments' base
        syntax-token rules.

        The MkDocs plugin layers these over a theme's own syntax highlighting, so
        it must not pull in the standard token rules (those would override the
        theme). Keeps the `-Ansi-*` token rules plus everything
        `_extra_ansi_css_lines` adds. Owning this selection here, next to
        the rules it returns, keeps the MkDocs plugin from hard-coding this
        formatter's class names and CSS internals.
        """
        ansi_token_rules = [
            line for line in super().get_token_style_defs(arg) if "-Ansi" in line
        ]
        return "\n".join(ansi_token_rules + self._extra_ansi_css_lines(arg))

    def _get_css_classes(self, ttype: _TokenType) -> str:
        """Map a token to its CSS classes, decomposing compound `Token.Ansi.*` tokens.

        For a token like `Token.Ansi.Bold.Cyan`, Pygments' default walks the token
        hierarchy and emits the concatenated compound class (`-Ansi-Bold-Cyan`)
        alongside each ancestor, repeating the intermediate `-Ansi-Bold`. No CSS rule
        targets the compound class (the style dict only holds single components), so it
        is dead weight. This override returns the base class plus exactly one class per
        component instead (`-Ansi -Ansi-Bold -Ansi-Cyan`): each maps to its own rule,
        with no dead or duplicated classes. Non-ANSI tokens keep Pygments' default
        behavior.

        ```{note}
        The decomposition is formatter-level, so it reaches every integration
        rather than a single renderer. Sphinx installs this formatter via
        `PygmentsBridge.html_formatter` in {func}`click_extra.sphinx.setup`;
        MkDocs reparents `pymdownx.highlight`'s formatters onto it in
        {class}`click_extra.mkdocs.AnsiColorPlugin`. Editing this method therefore
        re-pins both the Sphinx and the MkDocs HTML output (and their tests).
        ```

        Results are cached per class prefix and token type in `_css_classes`,
        since the same compound tokens recur frequently in typical terminal output.
        """
        key = (self.classprefix, ttype)
        cached = self._css_classes.get(key)
        if cached is not None:
            return cached
        if ttype and ttype[0] == "Ansi":
            tokens = [Ansi, *(getattr(Ansi, part) for part in ttype[1:])]
            classes = " ".join(
                self._get_css_class(token)  # type: ignore[attr-defined]
                for token in tokens
            )
        else:
            classes = super()._get_css_classes(ttype)  # type: ignore[misc]
        self._css_classes[key] = classes
        return classes
