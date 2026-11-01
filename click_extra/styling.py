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
"""Drop-in replacement for `cloup.Style` with extra features.

The module name mirrors `cloup.styling`, the upstream module that hosts
the original `Style` class. Click Extra's {class}`Style` is a subclass that
keeps cloup's runtime contract (calling the instance to apply the style, equality,
hashing) intact and adds:

- An equality and a hash shared with `cloup.Style`, so a {class}`Style` equals
  the `cloup.Style` carrying the same fields.
- A compact, single-line `__repr__` that hides `None` and falsy
  attributes and renders RGB tuples as `#rrggbb` hex.
- Hex-string color shorthand: `Style(fg="#f1fa8c")` works alongside
  `Style(fg=(241, 250, 140))`.
- A `__str__` that returns the styled word `"sample"` so REPL prints and
  debuggers visualize what the style does, not just its fields.
- A composition operator `a | b` that merges two styles, with the right
  operand winning on conflicts.
- A {meth}`Style.cascade` method that fills the style's `None` fields from
  a base style without overriding any value already set.
- {meth}`Style.to_dict` / {meth}`Style.from_dict` for round-tripping styles
  through TOML/JSON/YAML.
- {meth}`Style.to_css` for emitting CSS-equivalent declarations: useful for
  HTML renderings of help screens.
- {meth}`Style.from_ansi` for parsing an ANSI SGR escape sequence back into
  a `Style` instance.
- {meth}`Style.contrast_ratio` returning the WCAG contrast ratio between
  two foreground colors. Useful for theme designers checking accessibility.
- {func}`split_ansi` and {func}`render_ansi` for tokenizing a string mixing
  text and ANSI escapes into styled runs, then re-rendering those runs through
  a markup emitter. Wrapping them to a width lives in
  {func}`~click_extra.layout.wrap_ansi`, with the rest of the terminal-grid
  measures.
- The {func}`ansi_to_html`, {func}`ansi_to_jira`, {func}`ansi_to_latex` and
  {func}`ansi_to_textile` converters, translating ANSI styling to markup
  languages with native styling support.

The escape grammar, the SGR decoder and the color conversions all of this reads
through live in {mod}`click_extra.ansi`, with
{func}`~click_extra.ansi.strip_ansi` and {func}`~click_extra.ansi.open_ansi`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields, replace
from functools import cache
from operator import attrgetter

import cloup

from .ansi import (
    ANSI_SGR_RE,
    apply_sgr_codes,
    hex_to_rgb,
    is_rgb,
    nearest_256,
    palette_to_rgb,
    resolve_rgb,
    rgb_to_hex,
    sgr_params,
    strip_ansi,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from dataclasses import Field
    from typing import Any


# --- Style attributes --------------------------------------------------------

# Single source of truth mapping each boolean style attribute to its CSS
# `(property, value)` equivalent. Consumed by {meth}`Style.to_css` (which
# groups the three `text-decoration` attributes into one declaration) and,
# in its declaration-string form, by `click_extra.sphinx.theme_docs._PALETTE_ATTR_CSS`
# to render the documentation palette's attribute pills.
#
# `blink` maps to an empty pair on purpose: there is no standard CSS for it
# (the legacy `text-decoration: blink` keyword is non-functional in modern
# browsers). It is therefore omitted from the rendered CSS. Animated blink is
# handled separately by `click_extra.pygments` via a `@keyframes` rule.
_ATTR_CSS: dict[str, tuple[str, str]] = {
    "bold": ("font-weight", "bold"),
    "dim": ("opacity", "0.6"),
    "italic": ("font-style", "italic"),
    "underline": ("text-decoration", "underline"),
    "overline": ("text-decoration", "overline"),
    "blink": ("", ""),
    "reverse": ("filter", "invert(1)"),
    "strikethrough": ("text-decoration", "line-through"),
}

# Boolean style attributes processed in repr/css/from_ansi, in palette order.
_BOOL_ATTRS: tuple[str, ...] = tuple(_ATTR_CSS)


# --- Shared dict round-trip helpers ------------------------------------------
#
# `Style` (per-attribute) and `HelpTheme` (per-slot) both serialize
# their dataclass fields to plain dicts for TOML/JSON/YAML round-tripping.
# These helpers codify the shared rules: walk the dataclass fields, skip
# values that match the field default, and raise on unknown keys with a
# clear message.


@cache
def _fields_by_name(cls: type) -> dict[str, Field[Any]]:
    """The dataclass fields of `cls`, keyed by name.

    Cached per class: {func}`dataclasses.fields` rebuilds its tuple on every
    call, and loading the built-in themes decodes one mapping per slot.
    """
    return {f.name: f for f in fields(cls)}


def fields_to_dict(
    instance: Any,
    *,
    encode: Callable[[Any, Any], Any] = lambda field, value: value,
    keep: Callable[[Any, Any], bool] = lambda field, value: True,
) -> dict[str, Any]:
    """Serialize a dataclass instance to a dict of its non-default fields.

    Skips every field still holding its declared default, then applies *keep*
    to decide which of the remaining fields are written, and passes their
    values through *encode*.

    :param instance: the dataclass to serialize.
    :param encode: callable `(field, value) -> encoded_value` applied to
        every kept value. Use to convert RGB tuples to `#rrggbb` strings,
        nested dataclasses to dicts, etc. Defaults to the identity.
    :param keep: callable `(field, value) -> bool` deciding whether a
        non-default field is emitted. Defaults to keeping all of them.
    """
    cls: type = type(instance)
    out: dict[str, Any] = {}
    for name, f in _fields_by_name(cls).items():
        value = getattr(instance, name)
        if value != f.default and keep(f, value):
            out[name] = encode(f, value)
    return out


def dict_to_fields(
    cls: type,
    data: dict[str, Any],
    *,
    decode: Callable[[Any, Any], Any] = lambda field, raw: raw,
) -> dict[str, Any]:
    """Validate *data*'s keys against *cls*'s dataclass fields and decode them.

    Returns a kwargs dict ready to splat into `cls(**kwargs)`.

    :param cls: the dataclass type whose fields define the legal keys.
    :param data: mapping from field name to a serialized value.
    :param decode: callable `(field, raw) -> decoded_value` invoked for
        every recognized key. Default returns the raw value unchanged.
    :raises TypeError: listing every key that names no field of *cls*, so
        callers can build a constructor call without validating first.
    """
    fields_by_name = _fields_by_name(cls)
    unknown = data.keys() - fields_by_name.keys()
    if unknown:
        raise TypeError(
            f"Unknown {cls.__name__} field(s): {', '.join(sorted(unknown))}"
        )
    return {name: decode(fields_by_name[name], raw) for name, raw in data.items()}


# --- Color rendering ---------------------------------------------------------


def _color_repr(value: object) -> str:
    """Compact human-readable form of a color value for `__repr__`."""
    return rgb_to_hex(value) if is_rgb(value) else repr(value)


def _color_to_css(color: object) -> str:
    """Render a color value as a CSS color string.

    The 8 base ANSI names and hex strings pass through: both are valid CSS. A
    `bright_*` name, a palette index and an RGB tuple resolve to `#rrggbb`.
    """
    if is_rgb(color):
        return rgb_to_hex(color)
    if isinstance(color, int):
        return rgb_to_hex(palette_to_rgb(color))
    if isinstance(color, str) and color.startswith("bright_"):
        return rgb_to_hex(resolve_rgb(color))
    return str(color)


def _linear_channel(value: int) -> float:
    """Linearize one sRGB channel for {func}`_relative_luminance`."""
    ratio = value / 255
    return ratio / 12.92 if ratio <= 0.03928 else ((ratio + 0.055) / 1.055) ** 2.4


def _relative_luminance(color: object) -> float:
    """WCAG relative luminance for a color value, in `[0, 1]`.

    See: https://www.w3.org/TR/WCAG22/#dfn-relative-luminance
    """
    r, g, b = resolve_rgb(color)
    return (
        0.2126 * _linear_channel(r)
        + 0.7152 * _linear_channel(g)
        + 0.0722 * _linear_channel(b)
    )


# --- Terminal color-depth detection -----------------------------------------

_TRUECOLOR_COLORTERMS = frozenset({"truecolor", "24bit"})
"""`COLORTERM` values that advertise 24-bit (truecolor) support.

The two tokens [Rich](https://github.com/Textualize/rich/blob/master/rich/console.py) and the wider
terminal ecosystem agree on. Any other non-empty `COLORTERM` is read as a
deliberate *non*-truecolor advertisement.
"""


def supports_truecolor() -> bool:
    """Whether the terminal is assumed to render 24-bit (truecolor) ANSI.

    Drives `Style.__call__`'s choice between emitting a 24-bit
    `38;2;r;g;b` sequence and quantizing it to the nearest `38;5;n` 256-color
    index, so a branded theme's RGB colors degrade gracefully on a terminal that
    cannot display them.

    The policy is optimistic: assume truecolor unless the environment positively
    says otherwise. Precedence, highest first:

    #. `COLORTERM` of `truecolor` / `24bit` (see
       `_TRUECOLOR_COLORTERMS`) keeps 24-bit.
    #. Any other non-empty `COLORTERM` quantizes: an explicit lower
       advertisement.
    #. A `TERM` ending in `-16color` quantizes: an unambiguous sub-256
       terminal. `*-256color` is deliberately *not* treated as a downgrade,
       since truecolor terminals routinely report it while advertising their
       24-bit support through `COLORTERM` instead. Honoring it would strip
       truecolor from the very terminals this optimistic default protects.
    #. Otherwise keeps 24-bit.

    A `dumb` / `unknown` `TERM` never reaches this decision for CLI output:
    it has already disabled color upstream through
    {func}`~click_extra.color.resolve_color_env`.
    """
    colorterm = os.environ.get("COLORTERM", "").strip().lower()
    if colorterm:
        return colorterm in _TRUECOLOR_COLORTERMS
    return not os.environ.get("TERM", "").strip().lower().endswith("-16color")


_Color = str | tuple[int, int, int] | int | None
"""A color `click.style` takes: ANSI name, RGB tuple, palette index or `None`."""


def _quantize_color(color: _Color) -> _Color:
    """Map a 24-bit RGB `(r, g, b)` color to its nearest 256-palette index.

    Any non-tuple color (a named ANSI string, an existing palette `int`, or
    `None`) is returned untouched: only true-color values need quantizing.
    """
    if is_rgb(color):
        return nearest_256(*color)
    return color


# --- Style ------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class Style(cloup.Style):
    """`cloup.Style` with extra ergonomics.

    See the module docstring for the full list of additions. The runtime
    contract (calling the instance to apply the style, equality, hashing) is
    otherwise identical to `cloup.Style`.
    """

    fg: _Color = None
    """Foreground color: named ANSI string, `#rrggbb` hex, RGB tuple, or palette index."""

    bg: _Color = None
    """Background color: named ANSI string, `#rrggbb` hex, RGB tuple, or palette index."""

    def __post_init__(self) -> None:
        """Convert `#rrggbb` shorthand strings on `fg`/`bg` to RGB tuples.

        Frozen dataclass: must use {func}`object.__setattr__` to bypass the
        frozen guard.
        """
        if isinstance(self.fg, str) and self.fg.startswith("#"):
            object.__setattr__(self, "fg", hex_to_rgb(self.fg))
        if isinstance(self.bg, str) and self.bg.startswith("#"):
            object.__setattr__(self, "bg", hex_to_rgb(self.bg))

    def __call__(self, text: str) -> str:
        """Apply the style, quantizing 24-bit colors when truecolor is unavailable.

        On a truecolor terminal (see {func}`supports_truecolor`) this is cloup's
        unchanged behavior: RGB `fg` / `bg` emit `38;2;r;g;b` sequences. When
        the terminal does not advertise truecolor, RGB colors are downsampled to the
        nearest `38;5;n` 256-color index so a branded theme degrades instead of
        relying on the terminal to convert. Named and palette-index colors are
        unaffected either way, and a style carrying no RGB color never reads the
        environment: this method runs for every styled token of a help screen.
        """
        if (is_rgb(self.fg) or is_rgb(self.bg)) and not supports_truecolor():
            # Quantize on a transient copy: the theme styles are shared, and the
            # next call may land on a truecolor terminal.
            return replace(
                self, fg=_quantize_color(self.fg), bg=_quantize_color(self.bg)
            )(text)
        return super().__call__(text)

    def __repr__(self) -> str:
        """Compact repr that lists only the attributes actually set."""
        parts: list[str] = []
        if self.fg is not None:
            parts.append(f"fg={_color_repr(self.fg)}")
        if self.bg is not None:
            parts.append(f"bg={_color_repr(self.bg)}")
        parts.extend(attr for attr in _BOOL_ATTRS if getattr(self, attr))
        if self.text_transform is not None:
            parts.append(f"text_transform={self.text_transform!r}")
        return f"Style({', '.join(parts)})"

    def __str__(self) -> str:
        """Return the word `"sample"` styled with this Style.

        Lets `print(style)` and debuggers visualize the style instead of
        dumping its fields.
        """
        return self("sample")

    def __eq__(self, other: object) -> bool:
        """Equality on the style fields, against `cloup.Style` too.

        The generated dataclass equality only compares instances of the very
        same class, so a {class}`Style` would never equal the `cloup.Style`
        carrying the same fields.
        """
        if not isinstance(other, cloup.Style):
            return NotImplemented
        return _style_values(self) == _style_values(other)

    def __hash__(self) -> int:
        """Hash mirroring {meth}`__eq__`, and the hash of `cloup.Style`."""
        return hash(_style_values(self))

    @staticmethod
    def _merge(base: cloup.Style, top: cloup.Style) -> Style:
        """Return a {class}`Style` where *top*'s set fields override *base*'s.

        Walks the shared {data}`_STYLE_FIELDS` names, which cover cloup's
        {class}`~cloup.Style` too (this subclass adds no field of its own), so
        cloup's class works fine as either operand of `|`.
        """
        merged: dict[str, Any] = {}
        for name in _STYLE_FIELDS:
            value = getattr(top, name)
            merged[name] = getattr(base, name) if value is None else value
        # Pick the most specific class present so `my_style | cloup_style`
        # still returns a `Style` (this subclass).
        if isinstance(top, Style):
            return type(top)(**merged)
        if isinstance(base, Style):
            return type(base)(**merged)
        return Style(**merged)

    def __or__(self, other: object) -> Style:
        """`a | b` merges two styles. `b`'s set fields win on conflicts."""
        if not isinstance(other, cloup.Style):
            return NotImplemented
        return self._merge(self, other)

    def __ror__(self, other: object) -> Style:
        """Reflected `|`: `other | self` where `self`'s fields win."""
        if not isinstance(other, cloup.Style):
            return NotImplemented
        return self._merge(other, self)

    def cascade(self, base: cloup.Style) -> Style:
        """Return a copy with `None` fields filled in from *base*.

        The instance's own non-`None` values always win: `cascade` only
        fills gaps. Useful for theme inheritance: `derived.cascade(parent)`
        keeps `derived`'s overrides and inherits the rest from `parent`.
        """
        if not isinstance(base, cloup.Style):
            raise TypeError(f"Cannot cascade onto {type(base).__name__}: not a Style.")
        return self._merge(base, self)

    @staticmethod
    def _encode_field(_field: Any, value: Any) -> Any:
        """Encode a field value for {meth}`to_dict`.

        RGB tuples become `#rrggbb` strings; everything else passes through.
        """
        return rgb_to_hex(value) if is_rgb(value) else value

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict with only the set fields.

        RGB tuples are emitted as `#rrggbb` strings so the result
        round-trips through TOML/JSON/YAML untouched. Pair with
        {meth}`from_dict` to rebuild a {class}`Style`.
        """
        return fields_to_dict(self, encode=self._encode_field)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Style:
        """Build a {class}`Style` from the plain dict produced by {meth}`to_dict`.

        Validates that every key in *data* names a known {class}`Style` field
        and raises {class}`TypeError` otherwise. Pair with {meth}`to_dict`
        to round-trip through TOML/JSON/YAML.
        """
        return cls(**dict_to_fields(cls, data))

    def to_css(self) -> str:
        """Render the style as a semicolon-separated CSS declaration list.

        `Style(fg="#f1fa8c", bold=True).to_css()` returns
        `"color: #f1fa8c; font-weight: bold"`. Suitable for inline
        `style="..."` attributes on HTML spans.
        """
        parts: list[str] = []
        if self.fg is not None:
            parts.append(f"color: {_color_to_css(self.fg)}")
        if self.bg is not None:
            parts.append(f"background-color: {_color_to_css(self.bg)}")
        # Per-attribute CSS comes from the shared `_ATTR_CSS` source of
        # truth. The three `text-decoration` attributes are grouped into a
        # single declaration; `blink` (empty pair) is skipped.
        if self.bold:
            prop, value = _ATTR_CSS["bold"]
            parts.append(f"{prop}: {value}")
        if self.italic:
            prop, value = _ATTR_CSS["italic"]
            parts.append(f"{prop}: {value}")
        decorations = [
            _ATTR_CSS[attr][1]
            for attr in ("underline", "overline", "strikethrough")
            if getattr(self, attr)
        ]
        if decorations:
            parts.append(f"text-decoration: {' '.join(decorations)}")
        if self.dim:
            prop, value = _ATTR_CSS["dim"]
            parts.append(f"{prop}: {value}")
        if self.reverse:
            prop, value = _ATTR_CSS["reverse"]
            parts.append(f"{prop}: {value}")
        return "; ".join(parts)

    @classmethod
    def from_ansi(cls, escape: str) -> Style:
        r"""Parse one or more consecutive ANSI SGR escapes into a {class}`Style`.

        Supports the standard 8/16-color codes (30–37, 40–47, 90–97,
        100–107), the `38;5;n` / `48;5;n` 256-color extension, and the
        `38;2;r;g;b` / `48;2;r;g;b` 24-bit extension. Reset codes (the
        full `0` reset, its parameter-less `\x1b[m` form included, and
        selective resets like `22`, `39` or `49`) are ignored, so
        parsing the full output of a style call (trailing reset included)
        recovers that style. Multiple back-to-back escapes (as click emits
        when combining colors with attributes: `\x1b[31m\x1b[1m`) are
        merged into a single {class}`Style`.

        To tokenize a string mixing text and escapes, with resets honored,
        see {func}`split_ansi`.
        """
        matches = list(ANSI_SGR_RE.finditer(escape))
        if not matches:
            raise ValueError(f"Not an ANSI SGR escape: {escape!r}")
        state: dict[str, Any] = {}
        for m in matches:
            apply_sgr_codes(sgr_params(m.group(1)), state, resets=False)
        return cls(**state)

    def contrast_ratio(self, other: cloup.Style) -> float:
        """Return the WCAG 2.x contrast ratio between this fg and *other*'s fg.

        Result is in `[1, 21]`: 1 = identical colors (no contrast),
        21 = maximum contrast (black on white). WCAG AA requires 4.5+ for
        normal text, 3.0+ for large text; AAA wants 7.0+ and 4.5+ respectively.
        """
        if self.fg is None or other.fg is None:
            raise ValueError(
                "contrast_ratio requires both styles to have a foreground color."
            )
        a = _relative_luminance(self.fg)
        b = _relative_luminance(other.fg)
        if a < b:
            a, b = b, a
        return (a + 0.05) / (b + 0.05)


_STYLE_FIELDS: tuple[str, ...] = tuple(_fields_by_name(Style))
"""Names of {class}`Style`'s fields, in declaration order.

The names also cover the parent `cloup.Style` (this subclass only re-types
`fg` / `bg`), which is what lets {meth}`Style._merge` and {meth}`Style.__eq__`
accept either class."""

_style_values = attrgetter(*_STYLE_FIELDS)
"""Read the {data}`_STYLE_FIELDS` of a style as one tuple.

What {meth}`Style.__eq__` and {meth}`Style.__hash__` compare: a single C call,
where walking the fields in Python costs several times more for every styled
run {func}`render_ansi` compares."""


# --- ANSI stream parsing and markup rendering ---------------------------------


def split_ansi(text: str) -> Iterator[tuple[Style, str]]:
    """Split *text* into `(style, text)` runs at ANSI SGR escape boundaries.

    A stateful SGR stream parser: each escape updates the current style state
    (with full and selective resets honored, unlike {meth}`Style.from_ansi`),
    and every maximal run of text sharing the same state is yielded with its
    {class}`Style`. Unstyled text is yielded with an empty {class}`Style`.
    Consecutive runs with equal styles are merged and empty runs are dropped,
    so wrapping each yielded run produces minimal markup.

    Every other escape carries no style information and is removed from the
    yielded text by {func}`~click_extra.ansi.strip_ansi`, so a terminal hyperlink
    keeps its display text and loses its URI.
    """
    state: dict[str, Any] = {}
    current = Style()
    # Snapshot of the state `current` was built from. The SGR appliers keep the
    # state dict canonical (attributes are popped on reset, never set falsy, and
    # values arrive in one spelling each), so two runs share a style exactly
    # when their state dicts are equal: comparing dicts is what lets the hot
    # loop skip a Style construction, and its field-walking equality, for every
    # escape that lands back on the same state (a reset closing an unstyled
    # run, a style re-opened identically).
    current_state: dict[str, Any] = {}
    buffer: list[str] = []
    pos = 0
    for match in ANSI_SGR_RE.finditer(text):
        segment = _strip_segment(text[pos : match.start()])
        pos = match.end()
        if segment:
            buffer.append(segment)
        apply_sgr_codes(sgr_params(match.group(1)), state)
        if state != current_state:
            if buffer:
                yield current, "".join(buffer)
                buffer = []
            current = Style(**state)
            current_state = dict(state)
    tail = _strip_segment(text[pos:])
    if tail:
        buffer.append(tail)
    if buffer:
        yield current, "".join(buffer)


def _strip_segment(segment: str) -> str:
    """Strip the non-SGR escapes from the text between two SGR escapes.

    Each segment of {func}`split_ansi` is stripped on its own, so a sequence left
    open ends at the SGR escape that follows it, as on a terminal. The regex pass
    is skipped for the common segment that carries no escape at all.
    """
    return strip_ansi(segment) if "\x1b" in segment else segment


def render_ansi(text: str, emitter: Callable[[Style, str], str]) -> str:
    """Rebuild *text*, replacing each ANSI-styled run by *emitter*'s markup.

    Unstyled runs pass through verbatim, so any markup surrounding the styled
    runs (table borders, tags produced by another renderer) is preserved byte
    for byte. Styled runs are handed to *emitter* one line at a time: runs are
    split on newlines so no markup wrapper ever crosses a line boundary, which
    keeps line-oriented markup (LaTeX rows, wiki tables) well-formed even when
    a style spans multiple lines.
    """
    plain = Style()
    chunks: list[str] = []
    for style, run in split_ansi(text):
        if style == plain:
            chunks.append(run)
            continue
        for index, line in enumerate(run.split("\n")):
            if index:
                chunks.append("\n")
            if line:
                chunks.append(emitter(style, line))
    return "".join(chunks)


def _html_emitter(style: Style, text: str) -> str:
    """Wrap *text* in an HTML `<span>` carrying the style as inline CSS.

    Relies on {meth}`Style.to_css` for the declarations. A style with no CSS
    equivalent (like a bare `blink`) leaves the text unwrapped.
    """
    css = style.to_css()
    if not css:
        return text
    return f'<span style="{css}">{text}</span>'


def ansi_to_html(text: str) -> str:
    r"""Translate ANSI styling in *text* to inline-styled HTML `<span>` tags.

    `\x1b[34mSummer\x1b[0m` becomes
    `<span style="color: blue">Summer</span>`. The spans are self-contained
    (no stylesheet needed) and also valid in markups accepting inline HTML,
    like MediaWiki.
    """
    return render_ansi(text, _html_emitter)


_JIRA_ATTR_MARKUP: dict[str, str] = {
    "bold": "*",
    "italic": "_",
    "underline": "+",
    "strikethrough": "-",
}
"""Jira wiki markup markers for the text attributes it can express."""


def _jira_emitter(style: Style, text: str) -> str:
    """Wrap *text* in Jira wiki markup.

    Foreground colors render as ``{color:...}`` macros: named for the 8 base
    ANSI colors, `#rrggbb` hex otherwise. Text attributes use the markers
    from {data}`_JIRA_ATTR_MARKUP`. Jira markup has no equivalent for
    background colors, dim, overline, reverse or blink: those are dropped.
    """
    prefix = ""
    suffix = ""
    for attr, marker in _JIRA_ATTR_MARKUP.items():
        if getattr(style, attr):
            prefix = prefix + marker
            suffix = marker + suffix
    if style.fg is not None:
        prefix = f"{{color:{_color_to_css(style.fg)}}}{prefix}"
        suffix = f"{suffix}{{color}}"
    return f"{prefix}{text}{suffix}"


def ansi_to_jira(text: str) -> str:
    r"""Translate ANSI styling in *text* to Jira wiki markup.

    `\x1b[34;1mSummer\x1b[0m` becomes ``{color:blue}*Summer*{color}``.
    """
    return render_ansi(text, _jira_emitter)


def _latex_color(color: object) -> str:
    r"""Render a color as `\textcolor` / `\colorbox` arguments.

    The 8 base ANSI color names are [predefined by xcolor](https://ctan.org/pkg/xcolor) and pass through as ``{name}``. Everything
    else (bright variants, 256-color indices, 24-bit values) resolves to an
    ``[HTML]{RRGGBB}`` model specification.
    """
    css = _color_to_css(color)
    if css.startswith("#"):
        return f"[HTML]{{{css[1:].upper()}}}"
    return f"{{{css}}}"


def _latex_emitter(style: Style, text: str) -> str:
    r"""Wrap *text* in LaTeX styling macros.

    Colors require the [xcolor package](https://ctan.org/pkg/xcolor) in the
    document preamble (``\usepackage{xcolor}``); bold, italic and underline
    use core LaTeX macros. Dim, overline, reverse, blink and strikethrough
    have no core-LaTeX equivalent and are dropped (strikethrough alone would
    pull in the `ulem` package).
    """
    result = text
    if style.bold:
        result = f"\\textbf{{{result}}}"
    if style.italic:
        result = f"\\textit{{{result}}}"
    if style.underline:
        result = f"\\underline{{{result}}}"
    if style.fg is not None:
        result = f"\\textcolor{_latex_color(style.fg)}{{{result}}}"
    if style.bg is not None:
        result = f"\\colorbox{_latex_color(style.bg)}{{{result}}}"
    return result


def ansi_to_latex(text: str) -> str:
    r"""Translate ANSI styling in *text* to LaTeX macros.

    `\x1b[34;1mSummer\x1b[0m` becomes
    ``\textcolor{blue}{\textbf{Summer}}``. The colored macros require
    ``\usepackage{xcolor}`` in the document preamble.
    """
    return render_ansi(text, _latex_emitter)


def _textile_emitter(style: Style, text: str) -> str:
    """Wrap *text* in a Textile span carrying the style as inline CSS.

    Textile accepts arbitrary CSS declarations in curly braces:
    ``%{color:red}text%``. Relies on {meth}`Style.to_css` for the
    declarations, like the HTML emitter.
    """
    css = style.to_css()
    if not css:
        return text
    return f"%{{{css}}}{text}%"


def ansi_to_textile(text: str) -> str:
    r"""Translate ANSI styling in *text* to Textile spans.

    `\x1b[34;1mSummer\x1b[0m` becomes
    ``%{color: blue; font-weight: bold}Summer%``.
    """
    return render_ansi(text, _textile_emitter)
