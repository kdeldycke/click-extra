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
"""Drop-in replacement for ``cloup.Style`` with extra features.

The module name mirrors ``cloup.styling``, the upstream module that hosts
the original ``Style`` class. Click Extra's :class:`Style` is a subclass that
keeps cloup's runtime contract (calling, equality, hashing, ``with_()``)
intact and adds:

- A compact, single-line ``__repr__`` that hides ``None`` and falsy
  attributes and renders RGB tuples as ``#rrggbb`` hex.
- Hex-string color shorthand: ``Style(fg="#f1fa8c")`` works alongside
  ``Style(fg=(241, 250, 140))``.
- A ``__str__`` that returns the styled word ``"sample"`` so REPL prints and
  debuggers visualize what the style does, not just its fields.
- A composition operator ``a | b`` that merges two styles, with the right
  operand winning on conflicts.
- A :meth:`Style.cascade` method that fills the style's ``None`` fields from
  a base style without overriding any value already set.
- :meth:`Style.to_dict` / :meth:`Style.from_dict` for round-tripping styles
  through TOML/JSON/YAML.
- :meth:`Style.to_css` for emitting CSS-equivalent declarations: useful for
  HTML renderings of help screens.
- :meth:`Style.from_ansi` for parsing an ANSI SGR escape sequence back into
  a ``Style`` instance.
- :meth:`Style.contrast_ratio` returning the WCAG contrast ratio between
  two foreground colors. Useful for theme designers checking accessibility.
- :func:`split_ansi` and :func:`render_ansi` for tokenizing a string mixing
  text and ANSI escapes into styled runs, and re-rendering those runs through
  a markup emitter.
- The :func:`ansi_to_html`, :func:`ansi_to_jira`, :func:`ansi_to_latex` and
  :func:`ansi_to_textile` converters, translating ANSI styling to markup
  languages with native styling support.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, fields, replace
from functools import lru_cache

import cloup
from boltons.strutils import strip_ansi

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from typing import Any


# --- Color conversion utilities ----------------------------------------------

_ANSI_16_RGB: tuple[tuple[int, int, int], ...] = (
    (0, 0, 0),  # 0: black
    (239, 41, 41),  # 1: red
    (138, 226, 52),  # 2: green
    (252, 233, 79),  # 3: yellow
    (52, 101, 164),  # 4: blue
    (197, 9, 197),  # 5: magenta
    (52, 226, 226),  # 6: cyan
    (245, 245, 245),  # 7: white
    (103, 103, 103),  # 8: bright_black
    (255, 109, 103),  # 9: bright_red
    (95, 249, 103),  # 10: bright_green
    (254, 251, 103),  # 11: bright_yellow
    (104, 113, 255),  # 12: bright_blue
    (255, 118, 255),  # 13: bright_magenta
    (95, 253, 255),  # 14: bright_cyan
    (254, 255, 255),  # 15: bright_white
)
"""Canonical sRGB values for the 16 ANSI colors.

The single source of truth wherever a named ANSI color, or one of the first 16
slots of the 256-color palette, must materialize as a concrete RGB value:
:meth:`Style.to_css` (``bright_*`` names are not valid CSS keywords),
:meth:`Style.contrast_ratio` (luminance needs RGB), :func:`_palette_to_rgb`
(indices 0-15), and the palettes rendering terminal sessions in the
documentation (``click_extra.pygments._NAMED_COLORS`` and ``_PALETTE_256``).

Values are the ones the documentation always rendered: Tango-flavored normal
colors and iTerm2's default brights, picked for legibility on both light and
dark backgrounds.

.. note::
    The 8 base *named* colors keep bypassing this table in markup output:
    :func:`_color_to_css` emits them as plain CSS keywords (and the Jira and
    LaTeX emitters as macro/xcolor names), delegating the exact shade to the
    renderer. This table only answers when a concrete value is unavoidable.
"""

_ANSI_NAMES: tuple[str, ...] = (
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
)

# Channel values for the 6×6×6 color cube (palette indices 16–231).
_CUBE_VALUES: tuple[int, ...] = (0, 95, 135, 175, 215, 255)

# Single source of truth mapping each boolean style attribute to its CSS
# ``(property, value)`` equivalent. Consumed by :meth:`Style.to_css` (which
# groups the three ``text-decoration`` attributes into one declaration) and,
# in its declaration-string form, by ``click_extra.theme_docs._PALETTE_ATTR_CSS``
# to render the documentation palette's attribute pills.
#
# ``blink`` maps to an empty pair on purpose: there is no standard CSS for it
# (the legacy ``text-decoration: blink`` keyword is non-functional in modern
# browsers). It is therefore omitted from the rendered CSS. Animated blink is
# handled separately by ``click_extra.pygments`` via a ``@keyframes`` rule.
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

# Match a single ANSI SGR escape: ``\x1b[...m``. The parameter substring may be
# empty: ``\x1b[m`` is a valid, parameter-less full reset.
_ANSI_SGR_RE: re.Pattern[str] = re.compile(r"\x1b\[([0-9;]*)m")


# --- Shared dict round-trip helpers ------------------------------------------
#
# ``Style`` (per-attribute) and ``HelpTheme`` (per-slot) both serialize
# their dataclass fields to plain dicts for TOML/JSON/YAML round-tripping.
# These helpers codify the shared rules: walk ``dataclasses.fields``, skip
# cloup's lazy ``_style_kwargs`` cache, skip values that match the field
# default, and raise on unknown keys with a clear message.


def fields_to_dict(
    instance: Any,
    *,
    encode: Callable[[Any, Any], Any] = lambda field, value: value,
    keep: Callable[[Any, Any], bool] = lambda field, value: True,
) -> dict[str, Any]:
    """Serialize a dataclass instance to a dict of set fields.

    Walks every field via :func:`dataclasses.fields`, skips the internal
    ``_style_kwargs`` cache, applies *keep* to decide which fields are
    written (default: every non-default field), and passes the surviving
    values through *encode* (default: identity).

    :param instance: the dataclass to serialize.
    :param encode: callable ``(field, value) -> encoded_value`` applied to
        every kept value. Use to convert RGB tuples to ``#rrggbb`` strings,
        nested dataclasses to dicts, etc.
    :param keep: callable ``(field, value) -> bool`` deciding whether the
        field is emitted. Default keeps everything that differs from the
        field's declared default.
    """
    out: dict[str, Any] = {}
    for f in fields(instance):
        if f.name == "_style_kwargs":
            continue
        value = getattr(instance, f.name)
        if value == f.default:
            continue
        if not keep(f, value):
            continue
        out[f.name] = encode(f, value)
    return out


def dict_to_fields(
    cls: type,
    data: dict[str, Any],
    *,
    decode: Callable[[Any, Any], Any] = lambda field, raw: raw,
) -> dict[str, Any]:
    """Validate *data*'s keys against *cls*'s dataclass fields and decode them.

    Returns a kwargs dict ready to splat into ``cls(**kwargs)``. Raises
    :class:`TypeError` listing every unknown key, so callers can build
    a constructor call without an extra pre-validation pass.

    :param cls: the dataclass type whose fields define the legal keys.
    :param data: mapping from field name to a serialized value.
    :param decode: callable ``(field, raw) -> decoded_value`` invoked for
        every recognized key. Default returns the raw value unchanged.
    """
    fields_by_name = {f.name: f for f in fields(cls)}
    unknown = set(data).difference(fields_by_name)
    if unknown:
        raise TypeError(
            f"Unknown {cls.__name__} field(s): {', '.join(sorted(unknown))}"
        )
    kwargs: dict[str, Any] = {}
    for name, raw in data.items():
        kwargs[name] = decode(fields_by_name[name], raw)
    return kwargs


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Parse a hex color (``#rrggbb`` or shorthand ``#rgb``) to an RGB tuple."""
    s = value.lstrip("#").lower()
    if len(s) not in (3, 6):
        raise ValueError(f"Not a valid hex color: {value!r}")
    try:
        if len(s) == 3:
            return int(s[0] * 2, 16), int(s[1] * 2, 16), int(s[2] * 2, 16)
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"Not a valid hex color: {value!r}") from exc


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Format an ``(r, g, b)`` tuple as a ``#rrggbb`` hex string.

    The inverse of :func:`_hex_to_rgb`. The single source of truth for the
    RGB-to-hex rendering shared by ``__repr__``, ``to_css``, ``to_dict``, and
    the documentation palette.
    """
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def _palette_to_rgb(idx: int) -> tuple[int, int, int]:
    """Convert a 256-color palette index to its sRGB tuple.

    Indices 0-15 are the terminal's *system colors*: terminals render them with
    their theme's palette, so they resolve through the canonical
    :data:`_ANSI_16_RGB` table. Indices 16-231 (the 6x6x6 color cube) and
    232-255 (the grayscale ramp) are fixed by the xterm 256-color layout.
    """
    if 0 <= idx < 16:
        return _ANSI_16_RGB[idx]
    if 16 <= idx < 232:
        idx -= 16
        return (
            _CUBE_VALUES[idx // 36],
            _CUBE_VALUES[(idx // 6) % 6],
            _CUBE_VALUES[idx % 6],
        )
    if 232 <= idx < 256:
        v = (idx - 232) * 10 + 8
        return v, v, v
    raise ValueError(f"Palette index out of range: {idx}")


@lru_cache(maxsize=512)
def _nearest_256(r: int, g: int, b: int) -> int:
    """Map a 24-bit RGB triplet to the nearest index in the 256-color palette.

    The inverse of :func:`_palette_to_rgb`. Compares the Euclidean distance in RGB
    space against both the 6x6x6 color cube (indices 16-231) and the grayscale ramp
    (indices 232-255), returning whichever is closer.

    Used by ``Style.__call__`` to downsample branded-theme colors when the
    terminal lacks truecolor (see :func:`supports_truecolor`), and by
    ``click_extra.pygments`` and ``click_extra.cli`` for the same 24-bit-to-8-bit
    quantization.

    .. seealso::
        `Previous implementation
        <https://github.com/kdeldycke/dotfiles/blob/64d29369/starship-ansi-colors.py>`_
        of full-color to 8-bit quantization.
    """
    # Color cube (indices 16-231).
    ci = [
        min(
            range(6),
            key=lambda i, v=v: abs(v - _CUBE_VALUES[i]),  # type: ignore[misc]
        )
        for v in (r, g, b)
    ]
    cube_idx = 16 + 36 * ci[0] + 6 * ci[1] + ci[2]
    cube_dist = sum((v - _CUBE_VALUES[i]) ** 2 for v, i in zip((r, g, b), ci))

    # Grayscale ramp (indices 232-255).
    gray = round((r + g + b) / 3)
    gi = min(range(24), key=lambda i: abs(gray - (10 * i + 8)))
    gray_idx = 232 + gi
    gray_val = 10 * gi + 8
    gray_dist = sum((v - gray_val) ** 2 for v in (r, g, b))

    return gray_idx if gray_dist < cube_dist else cube_idx


def _resolve_rgb(color: object) -> tuple[int, int, int]:
    """Best-effort conversion of any color value to an ``(r, g, b)`` tuple.

    Accepts hex strings, named ANSI strings (``"red"``, ``"bright_blue"``),
    palette indices (``int``), and ``Color``-enum-like objects with a
    ``.name`` attribute.
    """
    if isinstance(color, tuple) and len(color) == 3:
        return color
    if isinstance(color, str):
        if color.startswith("#"):
            return _hex_to_rgb(color)
        if color.startswith("bright_"):
            return _ANSI_16_RGB[_ANSI_NAMES.index(color[7:]) + 8]
        return _ANSI_16_RGB[_ANSI_NAMES.index(color)]
    if isinstance(color, int):
        return _palette_to_rgb(color)
    if hasattr(color, "name") and not isinstance(color, type):
        return _resolve_rgb(color.name)
    raise ValueError(f"Cannot resolve color: {color!r}")


def _color_repr(value: object) -> str:
    """Compact human-readable form of a color value for ``__repr__``."""
    if isinstance(value, tuple) and len(value) == 3:
        return _rgb_to_hex(value)
    if hasattr(value, "name") and not isinstance(value, str):
        return value.name  # type: ignore[no-any-return]
    return repr(value)


def _color_to_css(color: object) -> str:
    """Render a color value as a CSS color string."""
    if isinstance(color, tuple) and len(color) == 3:
        return _rgb_to_hex(color)
    if isinstance(color, str):
        if color.startswith("#"):
            return color
        if color.startswith("bright_"):
            return _rgb_to_hex(_resolve_rgb(color))
        return color  # plain CSS keyword: 'red', 'blue', etc.
    if isinstance(color, int):
        return _rgb_to_hex(_palette_to_rgb(color))
    if hasattr(color, "name") and not isinstance(color, type):
        return _color_to_css(color.name)
    return str(color)


def _relative_luminance(color: object) -> float:
    """WCAG relative luminance for a color value, in ``[0, 1]``.

    See: https://www.w3.org/TR/WCAG22/#dfn-relative-luminance
    """
    r, g, b = _resolve_rgb(color)

    def _channel(c: int) -> float:
        c01 = c / 255
        return c01 / 12.92 if c01 <= 0.03928 else ((c01 + 0.055) / 1.055) ** 2.4

    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


# --- Terminal color-depth detection -----------------------------------------

_TRUECOLOR_COLORTERMS = frozenset({"truecolor", "24bit"})
"""``COLORTERM`` values that advertise 24-bit (truecolor) support.

The two tokens `Rich
<https://github.com/Textualize/rich/blob/master/rich/console.py>`_ and the wider
terminal ecosystem agree on. Any other non-empty ``COLORTERM`` is read as a
deliberate *non*-truecolor advertisement.
"""


def supports_truecolor() -> bool:
    """Whether the terminal is assumed to render 24-bit (truecolor) ANSI.

    Drives ``Style.__call__``'s choice between emitting a 24-bit
    ``38;2;r;g;b`` sequence and quantizing it to the nearest ``38;5;n`` 256-color
    index, so a branded theme's RGB colors degrade gracefully on a terminal that
    cannot display them.

    The policy is optimistic: assume truecolor unless the environment positively
    says otherwise. Precedence, highest first:

    #. ``COLORTERM`` of ``truecolor`` / ``24bit`` (see
       ``_TRUECOLOR_COLORTERMS``) keeps 24-bit.
    #. Any other non-empty ``COLORTERM`` quantizes: an explicit lower
       advertisement.
    #. A ``TERM`` ending in ``-16color`` quantizes: an unambiguous sub-256
       terminal. ``*-256color`` is deliberately *not* treated as a downgrade,
       since truecolor terminals routinely report it while advertising their
       24-bit support through ``COLORTERM`` instead. Honoring it would strip
       truecolor from the very terminals this optimistic default protects.
    #. Otherwise keeps 24-bit.

    A ``dumb`` / ``unknown`` ``TERM`` never reaches this decision for CLI output:
    it has already disabled color upstream through
    :func:`~click_extra.color.resolve_color_env`.
    """
    colorterm = os.environ.get("COLORTERM", "").strip().lower()
    if colorterm:
        return colorterm in _TRUECOLOR_COLORTERMS
    return not os.environ.get("TERM", "").strip().lower().endswith("-16color")


def _quantize_color(
    color: str | tuple[int, int, int] | int | None,
) -> str | tuple[int, int, int] | int | None:
    """Map a 24-bit RGB ``(r, g, b)`` color to its nearest 256-palette index.

    Any non-tuple color (a named ANSI string, an existing palette ``int``, or
    ``None``) is returned untouched: only true-color values need quantizing.
    """
    if isinstance(color, tuple) and len(color) == 3:
        return _nearest_256(*color)
    return color


# --- Style ------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class Style(cloup.Style):
    """``cloup.Style`` with extra ergonomics.

    See the module docstring for the full list of additions. The runtime
    contract (calling the instance to apply styling, equality, hashing,
    ``with_()``) is otherwise identical to ``cloup.Style``.
    """

    fg: str | tuple[int, int, int] | int | None = None  # type: ignore[assignment]
    """Foreground color: named ANSI string, ``#rrggbb`` hex, RGB tuple, or palette index."""

    bg: str | tuple[int, int, int] | int | None = None  # type: ignore[assignment]
    """Background color: named ANSI string, ``#rrggbb`` hex, RGB tuple, or palette index."""

    def __post_init__(self) -> None:
        """Convert ``#rrggbb`` shorthand strings on ``fg``/``bg`` to RGB tuples.

        Frozen dataclass: must use :func:`object.__setattr__` to bypass the
        frozen guard. Runs once at construction; cloup's lazy
        ``_style_kwargs`` cache (built on first ``__call__``) picks up the
        converted values.
        """
        if isinstance(self.fg, str) and self.fg.startswith("#"):
            object.__setattr__(self, "fg", _hex_to_rgb(self.fg))
        if isinstance(self.bg, str) and self.bg.startswith("#"):
            object.__setattr__(self, "bg", _hex_to_rgb(self.bg))

    def __call__(self, text: str) -> str:
        """Apply the style, quantizing 24-bit colors when truecolor is unavailable.

        On a truecolor terminal (see :func:`supports_truecolor`) this is cloup's
        unchanged behavior: RGB ``fg`` / ``bg`` emit ``38;2;r;g;b`` sequences. When
        the terminal does not advertise truecolor, RGB colors are downsampled to the
        nearest ``38;5;n`` 256-color index so a branded theme degrades instead of
        relying on the terminal to convert. Named and palette-index colors are
        unaffected either way.
        """
        if supports_truecolor():
            return super().__call__(text)
        fg = _quantize_color(self.fg)
        bg = _quantize_color(self.bg)
        if fg is self.fg and bg is self.bg:
            return super().__call__(text)
        # Quantize on a transient copy. ``replace`` resets cloup's lazy
        # ``_style_kwargs`` cache (the field is ``init=False``), so the singleton
        # theme styles keep their truecolor cache intact for the next call.
        return replace(self, fg=fg, bg=bg)(text)

    def __repr__(self) -> str:
        """Compact repr that lists only the attributes actually set."""
        parts: list[str] = []
        if self.fg is not None:
            parts.append(f"fg={_color_repr(self.fg)}")
        if self.bg is not None:
            parts.append(f"bg={_color_repr(self.bg)}")
        parts.extend(attr for attr in _BOOL_ATTRS if getattr(self, attr, None))
        text_transform = getattr(self, "text_transform", None)
        if text_transform is not None:
            parts.append(f"text_transform={text_transform!r}")
        return f"Style({', '.join(parts)})"

    def __str__(self) -> str:
        """Return the word ``"sample"`` styled with this Style.

        Lets ``print(style)`` and debuggers visualize the style instead of
        dumping its fields.
        """
        return self("sample")

    def __eq__(self, other: object) -> bool:
        """Equality on the publicly-set fields.

        Excludes cloup's lazily-populated ``_style_kwargs`` cache so two
        otherwise-identical styles compare equal whether or not either has
        been called yet.
        """
        if not isinstance(other, cloup.Style):
            return NotImplemented
        for f in fields(self):
            if f.name == "_style_kwargs":
                continue
            if getattr(self, f.name) != getattr(other, f.name):
                return False
        return True

    def __hash__(self) -> int:
        """Hash mirroring :meth:`__eq__`: skip the lazy ``_style_kwargs`` cache."""
        return hash(
            tuple(
                getattr(self, f.name) for f in fields(self) if f.name != "_style_kwargs"
            )
        )

    @staticmethod
    def _merge(base: cloup.Style, top: cloup.Style) -> Style:
        """Return a :class:`Style` where *top*'s set fields override *base*'s.

        Field walked from *base* so we don't depend on *top* being our own
        subclass: cloup's :class:`~cloup.Style` works fine as the right
        operand of ``|``.
        """
        merged: dict[str, Any] = {}
        for f in fields(base):
            if f.name == "_style_kwargs":
                continue
            top_val = getattr(top, f.name)
            merged[f.name] = top_val if top_val is not None else getattr(base, f.name)
        # Pick the most specific class present so ``my_style | cloup_style``
        # still returns a ``Style`` (this subclass).
        cls = type(top) if isinstance(top, Style) else type(base)
        if not isinstance(cls, type) or not issubclass(cls, Style):
            cls = Style
        return cls(**merged)

    def __or__(self, other: object) -> Style:
        """``a | b`` merges two styles. ``b``'s set fields win on conflicts."""
        if not isinstance(other, cloup.Style):
            return NotImplemented
        return self._merge(self, other)

    def __ror__(self, other: object) -> Style:
        """Reflected ``|``: ``other | self`` where ``self``'s fields win."""
        if not isinstance(other, cloup.Style):
            return NotImplemented
        return self._merge(other, self)

    def cascade(self, base: cloup.Style) -> Style:
        """Return a copy with ``None`` fields filled in from *base*.

        The instance's own non-``None`` values always win: ``cascade`` only
        fills gaps. Useful for theme inheritance: ``derived.cascade(parent)``
        keeps ``derived``'s overrides and inherits the rest from ``parent``.
        """
        if not isinstance(base, cloup.Style):
            raise TypeError(f"Cannot cascade onto {type(base).__name__}: not a Style.")
        return self._merge(base, self)

    @staticmethod
    def _encode_field(_field: Any, value: Any) -> Any:
        """Encode a field value for :meth:`to_dict`.

        RGB tuples become ``#rrggbb`` strings; enum-shaped objects with a
        ``.name`` are serialized by name; everything else passes through.
        """
        if isinstance(value, tuple) and len(value) == 3:
            return _rgb_to_hex(value)
        if hasattr(value, "name") and not isinstance(value, str):
            return value.name
        return value

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict with only the set fields.

        RGB tuples are emitted as ``#rrggbb`` strings so the result
        round-trips through TOML/JSON/YAML untouched. Pair with
        :meth:`from_dict` to rebuild a :class:`Style`.
        """
        return fields_to_dict(self, encode=self._encode_field)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Style:
        """Build a :class:`Style` from the plain dict produced by :meth:`to_dict`.

        Validates that every key in *data* names a known :class:`Style` field
        and raises :class:`TypeError` otherwise. Pair with :meth:`to_dict`
        to round-trip through TOML/JSON/YAML.
        """
        return cls(**dict_to_fields(cls, data))

    def to_css(self) -> str:
        """Render the style as a semicolon-separated CSS declaration list.

        ``Style(fg="#f1fa8c", bold=True).to_css()`` returns
        ``"color: #f1fa8c; font-weight: bold"``. Suitable for inline
        ``style="..."`` attributes on HTML spans.
        """
        parts: list[str] = []
        if self.fg is not None:
            parts.append(f"color: {_color_to_css(self.fg)}")
        if self.bg is not None:
            parts.append(f"background-color: {_color_to_css(self.bg)}")
        # Per-attribute CSS comes from the shared ``_ATTR_CSS`` source of
        # truth. The three ``text-decoration`` attributes are grouped into a
        # single declaration; ``blink`` (empty pair) is skipped.
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
        """Parse one or more consecutive ANSI SGR escapes into a :class:`Style`.

        Supports the standard 8/16-color codes (30–37, 40–47, 90–97,
        100–107), the ``38;5;n`` / ``48;5;n`` 256-color extension, and the
        ``38;2;r;g;b`` / ``48;2;r;g;b`` 24-bit extension. Reset codes (the
        full ``0`` reset, its parameter-less ``\\x1b[m`` form included, and
        selective resets like ``22``, ``39`` or ``49``) are ignored, so
        parsing the full output of a style call (trailing reset included)
        recovers that style. Multiple back-to-back escapes (as click emits
        when combining colors with attributes: ``\\x1b[31m\\x1b[1m``) are
        merged into a single :class:`Style`.

        To tokenize a string mixing text and escapes, with resets honored,
        see :func:`split_ansi`.
        """
        matches = list(_ANSI_SGR_RE.finditer(escape))
        if not matches:
            raise ValueError(f"Not an ANSI SGR escape: {escape!r}")
        state: dict[str, Any] = {}
        for m in matches:
            _apply_sgr_codes(_sgr_params(m.group(1)), state, resets=False)
        return cls(**state)

    def contrast_ratio(self, other: cloup.Style) -> float:
        """Return the WCAG 2.x contrast ratio between this fg and *other*'s fg.

        Result is in ``[1, 21]``: 1 = identical colors (no contrast),
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


# --- ANSI stream parsing and markup rendering ---------------------------------

_OSC_HYPERLINK_RE: re.Pattern[str] = re.compile(r"\x1b\]8;[^\x1b\x07]*(?:\x07|\x1b\\)")
"""Match one boundary marker of an OSC 8 terminal hyperlink.

Both the opening marker (which carries the URI) and the closing one (empty URI)
match, leaving the display text between them untouched. Consumed by
:func:`_strip_unsupported_ansi` so hyperlinked text survives with its link
dropped, instead of leaking the URI as visible garbage.
"""

_JIRA_ATTR_MARKUP: dict[str, str] = {
    "bold": "*",
    "italic": "_",
    "underline": "+",
    "strikethrough": "-",
}
"""Jira wiki markup markers for the text attributes it can express."""


def _sgr_params(params: str) -> tuple[int, ...]:
    """Decode an SGR parameter substring into a sequence of integer codes.

    Per ECMA-48, an empty parameter defaults to ``0``: ``\\x1b[m`` is a full
    reset, and ``\\x1b[;31m`` carries a reset followed by a red foreground.
    """
    return tuple(int(code) if code else 0 for code in params.split(";"))


def _apply_sgr_codes(
    codes: Sequence[int],
    state: dict[str, Any],
    *,
    resets: bool = True,
) -> None:
    """Apply SGR parameter *codes* to the mutable style *state*, in place.

    The single source of truth for SGR semantics, shared by :func:`split_ansi`
    (with the default ``resets=True``) and :meth:`Style.from_ansi` (with
    ``resets=False``).

    Style-setting codes add entries to *state*, keyed by :class:`Style` field
    names. When *resets* is true, the full ``0`` reset clears the state, and
    selective resets drop their attribute: ``22`` (bold and dim), ``23``
    (italic), ``24`` (underline), ``25`` (blink), ``27`` (reverse), ``29``
    (strikethrough), ``39`` (foreground), ``49`` (background) and ``55``
    (overline). When *resets* is false all of them are ignored, letting
    :meth:`Style.from_ansi` merge escapes without wiping already-parsed codes.

    Unknown codes are silently skipped, like terminals do.
    """
    i = 0
    total = len(codes)
    while i < total:
        code = codes[i]
        if code == 1:
            state["bold"] = True
        elif code == 2:
            state["dim"] = True
        elif code == 3:
            state["italic"] = True
        elif code == 4:
            state["underline"] = True
        elif code == 5:
            state["blink"] = True
        elif code == 7:
            state["reverse"] = True
        elif code == 9:
            state["strikethrough"] = True
        elif code == 53:
            state["overline"] = True
        elif 30 <= code <= 37:
            state["fg"] = _ANSI_NAMES[code - 30]
        elif 40 <= code <= 47:
            state["bg"] = _ANSI_NAMES[code - 40]
        elif 90 <= code <= 97:
            state["fg"] = "bright_" + _ANSI_NAMES[code - 90]
        elif 100 <= code <= 107:
            state["bg"] = "bright_" + _ANSI_NAMES[code - 100]
        elif code in (38, 48):
            key = "fg" if code == 38 else "bg"
            if i + 2 < total and codes[i + 1] == 5:
                state[key] = codes[i + 2]
                i += 2
            elif i + 4 < total and codes[i + 1] == 2:
                state[key] = (codes[i + 2], codes[i + 3], codes[i + 4])
                i += 4
        elif resets:
            if code == 0:
                state.clear()
            elif code == 22:
                state.pop("bold", None)
                state.pop("dim", None)
            elif code == 23:
                state.pop("italic", None)
            elif code == 24:
                state.pop("underline", None)
            elif code == 25:
                state.pop("blink", None)
            elif code == 27:
                state.pop("reverse", None)
            elif code == 29:
                state.pop("strikethrough", None)
            elif code == 39:
                state.pop("fg", None)
            elif code == 49:
                state.pop("bg", None)
            elif code == 55:
                state.pop("overline", None)
        i += 1


def _strip_unsupported_ansi(text: str) -> str:
    """Remove non-SGR ANSI escapes, keeping OSC 8 hyperlinks' display text.

    OSC 8 boundary markers are removed first, so the display text between them
    survives the broader :func:`boltons.strutils.strip_ansi` pass (whose CSI
    pattern would otherwise leave the URI behind as visible garbage). Every
    other escape (cursor movements, screen clearing, other OSC commands) has
    no markup equivalent and is dropped.
    """
    return strip_ansi(_OSC_HYPERLINK_RE.sub("", text))


def split_ansi(text: str) -> Iterator[tuple[Style, str]]:
    """Split *text* into ``(style, text)`` runs at ANSI SGR escape boundaries.

    A stateful SGR stream parser: each escape updates the current style state
    (with full and selective resets honored, unlike :meth:`Style.from_ansi`),
    and every maximal run of text sharing the same state is yielded with its
    :class:`Style`. Unstyled text is yielded with an empty :class:`Style`.
    Consecutive runs with equal styles are merged and empty runs are dropped,
    so wrapping each yielded run produces minimal markup.

    Non-SGR escapes carry no style information and are removed from the
    yielded text, per :func:`_strip_unsupported_ansi`.
    """
    state: dict[str, Any] = {}
    current = Style()
    buffer: list[str] = []
    pos = 0
    for match in _ANSI_SGR_RE.finditer(text):
        segment = _strip_unsupported_ansi(text[pos : match.start()])
        pos = match.end()
        if segment:
            buffer.append(segment)
        _apply_sgr_codes(_sgr_params(match.group(1)), state)
        new_style = Style(**state)
        if new_style != current:
            if buffer:
                yield current, "".join(buffer)
                buffer = []
            current = new_style
    tail = _strip_unsupported_ansi(text[pos:])
    if tail:
        buffer.append(tail)
    if buffer:
        yield current, "".join(buffer)


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
    """Wrap *text* in an HTML ``<span>`` carrying the style as inline CSS.

    Relies on :meth:`Style.to_css` for the declarations. A style with no CSS
    equivalent (like a bare ``blink``) leaves the text unwrapped.
    """
    css = style.to_css()
    if not css:
        return text
    return f'<span style="{css}">{text}</span>'


def ansi_to_html(text: str) -> str:
    """Translate ANSI styling in *text* to inline-styled HTML ``<span>`` tags.

    ``\\x1b[34mSummer\\x1b[0m`` becomes
    ``<span style="color: blue">Summer</span>``. The spans are self-contained
    (no stylesheet needed) and also valid in markups accepting inline HTML,
    like MediaWiki.
    """
    return render_ansi(text, _html_emitter)


def _jira_emitter(style: Style, text: str) -> str:
    """Wrap *text* in Jira wiki markup.

    Foreground colors render as ``{color:...}`` macros: named for the 8 base
    ANSI colors, ``#rrggbb`` hex otherwise. Text attributes use the markers
    from :data:`_JIRA_ATTR_MARKUP`. Jira markup has no equivalent for
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
    """Translate ANSI styling in *text* to Jira wiki markup.

    ``\\x1b[34;1mSummer\\x1b[0m`` becomes ``{color:blue}*Summer*{color}``.
    """
    return render_ansi(text, _jira_emitter)


def _latex_color(color: object) -> str:
    """Render a color as ``\\textcolor`` / ``\\colorbox`` arguments.

    The 8 base ANSI color names are `predefined by xcolor
    <https://ctan.org/pkg/xcolor>`_ and pass through as ``{name}``. Everything
    else (bright variants, 256-color indices, 24-bit values) resolves to an
    ``[HTML]{RRGGBB}`` model specification.
    """
    css = _color_to_css(color)
    if css.startswith("#"):
        return f"[HTML]{{{css[1:].upper()}}}"
    return f"{{{css}}}"


def _latex_emitter(style: Style, text: str) -> str:
    """Wrap *text* in LaTeX styling macros.

    Colors require the `xcolor package <https://ctan.org/pkg/xcolor>`_ in the
    document preamble (``\\usepackage{xcolor}``); bold, italic and underline
    use core LaTeX macros. Dim, overline, reverse, blink and strikethrough
    have no core-LaTeX equivalent and are dropped (strikethrough alone would
    pull in the ``ulem`` package).
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
    """Translate ANSI styling in *text* to LaTeX macros.

    ``\\x1b[34;1mSummer\\x1b[0m`` becomes
    ``\\textcolor{blue}{\\textbf{Summer}}``. The colored macros require
    ``\\usepackage{xcolor}`` in the document preamble.
    """
    return render_ansi(text, _latex_emitter)


def _textile_emitter(style: Style, text: str) -> str:
    """Wrap *text* in a Textile span carrying the style as inline CSS.

    Textile accepts arbitrary CSS declarations in curly braces:
    ``%{color:red}text%``. Relies on :meth:`Style.to_css` for the
    declarations, like the HTML emitter.
    """
    css = style.to_css()
    if not css:
        return text
    return f"%{{{css}}}{text}%"


def ansi_to_textile(text: str) -> str:
    """Translate ANSI styling in *text* to Textile spans.

    ``\\x1b[34;1mSummer\\x1b[0m`` becomes
    ``%{color: blue; font-weight: bold}Summer%``.
    """
    return render_ansi(text, _textile_emitter)
