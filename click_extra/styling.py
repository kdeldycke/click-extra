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
"""Drop-in replacement for :class:`cloup.Style` with extra features.

The module name mirrors :mod:`cloup.styling`, the upstream module that hosts
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
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields

import cloup

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any


# --- Color conversion utilities ----------------------------------------------

# 16 standard ANSI colors as approximate sRGB values. Used by :meth:`to_css`
# (where ``bright_*`` named colors aren't valid CSS keywords) and by
# :meth:`contrast_ratio` (which needs RGB to compute luminance).
_ANSI_16_RGB: tuple[tuple[int, int, int], ...] = (
    (0, 0, 0),         # 0: black
    (170, 0, 0),       # 1: red
    (0, 170, 0),       # 2: green
    (170, 85, 0),      # 3: yellow
    (0, 0, 170),       # 4: blue
    (170, 0, 170),     # 5: magenta
    (0, 170, 170),     # 6: cyan
    (170, 170, 170),   # 7: white
    (85, 85, 85),      # 8: bright_black
    (255, 85, 85),     # 9: bright_red
    (85, 255, 85),     # 10: bright_green
    (255, 255, 85),    # 11: bright_yellow
    (85, 85, 255),     # 12: bright_blue
    (255, 85, 255),    # 13: bright_magenta
    (85, 255, 255),    # 14: bright_cyan
    (255, 255, 255),   # 15: bright_white
)

_ANSI_NAMES: tuple[str, ...] = (
    "black", "red", "green", "yellow",
    "blue", "magenta", "cyan", "white",
)

# Channel values for the 6×6×6 color cube (palette indices 16–231).
_CUBE_VALUES: tuple[int, ...] = (0, 95, 135, 175, 215, 255)

# Boolean style attributes processed in repr/css/from_ansi.
_BOOL_ATTRS: tuple[str, ...] = (
    "bold", "dim", "italic", "underline", "overline",
    "blink", "reverse", "strikethrough",
)

# Match a single ANSI SGR escape: ``\x1b[...m``.
_ANSI_SGR_RE: re.Pattern[str] = re.compile(r"\x1b\[(\d+(?:;\d+)*)m")


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


def _palette_to_rgb(idx: int) -> tuple[int, int, int]:
    """Convert a 256-color palette index to an approximate sRGB tuple."""
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


def _resolve_rgb(color: object) -> tuple[int, int, int]:
    """Best-effort conversion of any color value to an ``(r, g, b)`` tuple.

    Accepts hex strings, named ANSI strings (``"red"``, ``"bright_blue"``),
    palette indices (``int``), and ``Color``-enum-like objects with a
    ``.name`` attribute.
    """
    if isinstance(color, tuple) and len(color) == 3:
        return color  # type: ignore[return-value]
    if isinstance(color, str):
        if color.startswith("#"):
            return _hex_to_rgb(color)
        if color.startswith("bright_"):
            return _ANSI_16_RGB[_ANSI_NAMES.index(color[7:]) + 8]
        return _ANSI_16_RGB[_ANSI_NAMES.index(color)]
    if isinstance(color, int):
        return _palette_to_rgb(color)
    if hasattr(color, "name") and not isinstance(color, type):
        return _resolve_rgb(color.name)  # type: ignore[union-attr]
    raise ValueError(f"Cannot resolve color: {color!r}")


def _color_repr(value: object) -> str:
    """Compact human-readable form of a color value for ``__repr__``."""
    if isinstance(value, tuple) and len(value) == 3:
        return f"#{value[0]:02x}{value[1]:02x}{value[2]:02x}"
    if hasattr(value, "name") and not isinstance(value, str):
        return value.name  # type: ignore[no-any-return,union-attr]
    return repr(value)


def _color_to_css(color: object) -> str:
    """Render a color value as a CSS color string."""
    if isinstance(color, tuple) and len(color) == 3:
        return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
    if isinstance(color, str):
        if color.startswith("#"):
            return color
        if color.startswith("bright_"):
            r, g, b = _resolve_rgb(color)
            return f"#{r:02x}{g:02x}{b:02x}"
        return color  # plain CSS keyword: 'red', 'blue', etc.
    if isinstance(color, int):
        r, g, b = _palette_to_rgb(color)
        return f"#{r:02x}{g:02x}{b:02x}"
    if hasattr(color, "name") and not isinstance(color, type):
        return _color_to_css(color.name)  # type: ignore[union-attr]
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


# --- Style ------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class Style(cloup.Style):
    """:class:`cloup.Style` with extra ergonomics.

    See the module docstring for the full list of additions. The runtime
    contract (calling the instance to apply styling, equality, hashing,
    ``with_()``) is otherwise identical to :class:`cloup.Style`.
    """

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

    def __repr__(self) -> str:
        """Compact repr that lists only the attributes actually set."""
        parts: list[str] = []
        if self.fg is not None:
            parts.append(f"fg={_color_repr(self.fg)}")
        if self.bg is not None:
            parts.append(f"bg={_color_repr(self.bg)}")
        for attr in _BOOL_ATTRS:
            if getattr(self, attr, None):
                parts.append(attr)
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
                getattr(self, f.name)
                for f in fields(self)
                if f.name != "_style_kwargs"
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
            return NotImplemented  # type: ignore[return-value]
        return self._merge(self, other)

    def __ror__(self, other: object) -> Style:
        """Reflected ``|``: ``other | self`` where ``self``'s fields win."""
        if not isinstance(other, cloup.Style):
            return NotImplemented  # type: ignore[return-value]
        return self._merge(other, self)

    def cascade(self, base: cloup.Style) -> Style:
        """Return a copy with ``None`` fields filled in from *base*.

        The instance's own non-``None`` values always win: ``cascade`` only
        fills gaps. Useful for theme inheritance: ``derived.cascade(parent)``
        keeps ``derived``'s overrides and inherits the rest from ``parent``.
        """
        if not isinstance(base, cloup.Style):
            raise TypeError(
                f"Cannot cascade onto {type(base).__name__}: not a Style."
            )
        return self._merge(base, self)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict with only the set fields.

        RGB tuples are emitted as ``#rrggbb`` strings so the result
        round-trips through TOML/JSON/YAML untouched. Pair with
        :meth:`from_dict` to rebuild a :class:`Style`.
        """
        out: dict[str, Any] = {}
        for f in fields(self):
            if f.name == "_style_kwargs":
                continue
            val = getattr(self, f.name)
            if val is None:
                continue
            if isinstance(val, tuple) and len(val) == 3:
                out[f.name] = f"#{val[0]:02x}{val[1]:02x}{val[2]:02x}"
            elif hasattr(val, "name") and not isinstance(val, str):
                out[f.name] = val.name
            else:
                out[f.name] = val
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Style:
        """Build a :class:`Style` from the plain dict produced by :meth:`to_dict`."""
        return cls(**data)

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
        if self.bold:
            parts.append("font-weight: bold")
        if self.italic:
            parts.append("font-style: italic")
        decorations: list[str] = []
        if self.underline:
            decorations.append("underline")
        if self.overline:
            decorations.append("overline")
        if self.strikethrough:
            decorations.append("line-through")
        if decorations:
            parts.append(f"text-decoration: {' '.join(decorations)}")
        if self.dim:
            parts.append("opacity: 0.6")
        if self.reverse:
            parts.append("filter: invert(1)")
        return "; ".join(parts)

    @classmethod
    def from_ansi(cls, escape: str) -> Style:
        """Parse one or more consecutive ANSI SGR escapes into a :class:`Style`.

        Supports the standard 8/16-color codes (30–37, 40–47, 90–97,
        100–107), the ``38;5;n`` / ``48;5;n`` 256-color extension, and the
        ``38;2;r;g;b`` / ``48;2;r;g;b`` 24-bit extension. Reset codes (``0``)
        are ignored. Multiple back-to-back escapes (as click emits when
        combining colors with attributes: ``\\x1b[31m\\x1b[1m``) are merged
        into a single :class:`Style`.
        """
        matches = list(_ANSI_SGR_RE.finditer(escape))
        if not matches:
            raise ValueError(f"Not an ANSI SGR escape: {escape!r}")
        codes: list[int] = []
        for m in matches:
            codes.extend(int(c) for c in m.group(1).split(";"))
        kwargs: dict[str, Any] = {}
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                pass  # reset, skip.
            elif c == 1:
                kwargs["bold"] = True
            elif c == 2:
                kwargs["dim"] = True
            elif c == 3:
                kwargs["italic"] = True
            elif c == 4:
                kwargs["underline"] = True
            elif c == 5:
                kwargs["blink"] = True
            elif c == 7:
                kwargs["reverse"] = True
            elif c == 9:
                kwargs["strikethrough"] = True
            elif c == 53:
                kwargs["overline"] = True
            elif 30 <= c <= 37:
                kwargs["fg"] = _ANSI_NAMES[c - 30]
            elif 40 <= c <= 47:
                kwargs["bg"] = _ANSI_NAMES[c - 40]
            elif 90 <= c <= 97:
                kwargs["fg"] = "bright_" + _ANSI_NAMES[c - 90]
            elif 100 <= c <= 107:
                kwargs["bg"] = "bright_" + _ANSI_NAMES[c - 100]
            elif c in (38, 48):
                key = "fg" if c == 38 else "bg"
                if i + 2 < len(codes) and codes[i + 1] == 5:
                    kwargs[key] = codes[i + 2]
                    i += 2
                elif i + 4 < len(codes) and codes[i + 1] == 2:
                    kwargs[key] = (codes[i + 2], codes[i + 3], codes[i + 4])
                    i += 4
            i += 1
        return cls(**kwargs)

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
