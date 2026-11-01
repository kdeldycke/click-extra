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
"""Read and write ANSI escape sequences, and convert terminal colors.

A terminal styles its text with escape sequences mixed into the text. Every
module of this package that reads or writes such text uses the grammar and the
color arithmetic of this module:

- {data}`ANSI_ESCAPE_PATTERN` matches one escape sequence of any kind, in
  ECMA-48 syntax. {func}`strip_ansi` removes all of them from a string.
- {data}`ANSI_SGR_RE` matches the SGR escapes that set colors and text
  attributes. {func}`sgr_params` and {func}`apply_sgr_codes` decode them, and
  {func}`open_ansi` returns the ones a string leaves in effect.
- {func}`hex_to_rgb`, {func}`rgb_to_hex`, {func}`palette_to_rgb`,
  {func}`nearest_256` and {func}`resolve_rgb` convert a color between the forms
  a terminal knows: a hex string, a 24-bit RGB triplet, an index of the
  256-color palette and a name of the 16 colors of {data}`ANSI_16_RGB`.

{class}`~click_extra.styling.Style`, the stream parser
{func}`~click_extra.styling.split_ansi` and the markup converters are built on
this module, in {mod}`click_extra.styling`.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import overload

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any, TypeGuard


RESET = "\x1b[0m"
"""Escape closing every style a line left open, written before any padding."""


# --- Color conversion utilities ----------------------------------------------

ANSI_16_RGB: tuple[tuple[int, int, int], ...] = (
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
{meth}`~click_extra.styling.Style.to_css` (`bright_*` names are not valid CSS
keywords), {meth}`~click_extra.styling.Style.contrast_ratio` (luminance needs
RGB), {func}`palette_to_rgb` (indices 0-15), and the palettes rendering terminal
sessions in the documentation (`click_extra.pygments._NAMED_COLORS` and
`_PALETTE_256`).

Values are the ones the documentation always rendered: Tango-flavored normal
colors and iTerm2's default brights, picked for legibility on both light and
dark backgrounds.

```{note}
The 8 base *named* colors keep bypassing this table in markup output:
{func}`~click_extra.styling._color_to_css` emits them as plain CSS keywords (and
the Jira and LaTeX emitters as macro/xcolor names), delegating the exact shade to
the renderer. This table only answers when a concrete value is unavoidable.
```
"""

ANSI_NAMES: tuple[str, ...] = (
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
)
"""Names of the 8 base ANSI colors, in palette order.

A bright variant takes the `bright_` prefix and the slot 8 places further on.
"""

ANSI_INDEX: dict[str, int] = {name: index for index, name in enumerate(ANSI_NAMES)}
"""Palette index of each base ANSI color name, the O(1) mirror of
{data}`ANSI_NAMES` for the name-to-slot lookups color resolution performs."""

# Channel values for the 6×6×6 color cube (palette indices 16–231).
_CUBE_VALUES: tuple[int, ...] = (0, 95, 135, 175, 215, 255)

ANSI_SGR_RE: re.Pattern[str] = re.compile(r"\x1b\[(?P<sgr_params>[0-9;]*)m")
r"""Match a single ANSI SGR escape: `\x1b[...m`.

The parameter substring may be empty: `\x1b[m` is a valid, parameter-less full
reset. It is captured as `sgr_params`: the lexer of `click_extra.pygments`
composes this pattern into its own tokenizer and reads the parameters by that
name.
"""

SGR_ATTRIBUTES: dict[int, str] = {
    1: "bold",
    2: "dim",
    3: "italic",
    4: "underline",
    5: "blink",
    7: "reverse",
    9: "strikethrough",
    53: "overline",
}
"""The SGR code switching each boolean style attribute on."""

_SGR_RESETS: dict[int, tuple[str, ...]] = {
    22: ("bold", "dim"),
    23: ("italic",),
    24: ("underline",),
    25: ("blink",),
    27: ("reverse",),
    29: ("strikethrough",),
    39: ("fg",),
    49: ("bg",),
    55: ("overline",),
}
"""The style fields each selective SGR reset code switches off.

`22` ends both the bold and the faint intensity, as ECMA-48 defines it. The full
reset, `0`, clears every field and is handled apart.
"""

_SGR_COLOR_RANGES: tuple[tuple[int, int, str, str], ...] = (
    (30, 37, "fg", ""),
    (40, 47, "bg", ""),
    (90, 97, "fg", "bright_"),
    (100, 107, "bg", "bright_"),
)
"""The SGR code ranges naming one of the 16 ANSI colors.

Each entry gives the first and last code of the range, the field it sets and the
prefix of the color name: the standard colors are named after
{data}`ANSI_NAMES`, the bright ones take a `bright_` prefix.
"""


def is_rgb(color: object) -> TypeGuard[tuple[int, int, int]]:
    """Whether `color` is a 24-bit `(r, g, b)` triplet.

    The one shape of color this module computes on: a named ANSI color, a palette
    index or a hex string is resolved to it first.
    """
    return isinstance(color, tuple) and len(color) == 3


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Parse a hex color (`#rrggbb` or shorthand `#rgb`) to an RGB tuple.

    :raises ValueError: when `value` holds anything but 3 or 6 hex digits after
        its `#`. {class}`int` alone would take a sign, an underscore or a
        non-ASCII digit, and turn `#-1-1-1` into negative channels.
    """
    digits = value.removeprefix("#")
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    if len(digits) != 6 or not (digits.isascii() and digits.isalnum()):
        raise ValueError(f"Not a valid hex color: {value!r}")
    try:
        rgb = int(digits, 16)
    except ValueError as exc:
        raise ValueError(f"Not a valid hex color: {value!r}") from exc
    return rgb >> 16, (rgb >> 8) & 0xFF, rgb & 0xFF


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Format an `(r, g, b)` tuple as a `#rrggbb` hex string.

    The inverse of {func}`hex_to_rgb`. The single source of truth for the
    RGB-to-hex rendering shared by `__repr__`, `to_css`, `to_dict`, and
    the documentation palette.
    """
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def palette_to_rgb(idx: int) -> tuple[int, int, int]:
    """Convert a 256-color palette index to its sRGB tuple.

    Indices 0-15 are the terminal's *system colors*: terminals render them with
    their theme's palette, so they resolve through the canonical
    {data}`ANSI_16_RGB` table. Indices 16-231 (the 6x6x6 color cube) and
    232-255 (the grayscale ramp) are fixed by the xterm 256-color layout.
    """
    if 0 <= idx < 16:
        return ANSI_16_RGB[idx]
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
def nearest_256(r: int, g: int, b: int) -> int:
    """Map a 24-bit RGB triplet to the nearest index in the 256-color palette.

    The inverse of {func}`palette_to_rgb`. Compares the Euclidean distance in RGB
    space against both the 6x6x6 color cube (indices 16-231) and the grayscale ramp
    (indices 232-255), returning whichever is closer.

    Used by `Style.__call__` to downsample branded-theme colors when the
    terminal lacks truecolor (see {func}`~click_extra.styling.supports_truecolor`),
    and by `click_extra.pygments` and `click_extra.cli` for the same
    24-bit-to-8-bit quantization.

    ```{seealso}
    [Previous implementation](https://github.com/kdeldycke/dotfiles/blob/64d29369/starship-ansi-colors.py)
    of full-color to 8-bit quantization.
    ```
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


def resolve_rgb(color: object) -> tuple[int, int, int]:
    """Convert a color value to an `(r, g, b)` tuple.

    Accepts RGB tuples, hex strings, named ANSI colors (`"red"`,
    `"bright_blue"`) and palette indices.

    :raises ValueError: for any other value.
    """
    if is_rgb(color):
        return color
    if isinstance(color, str):
        if color.startswith("#"):
            return hex_to_rgb(color)
        name = color.removeprefix("bright_")
        index = ANSI_INDEX.get(name)
        if index is not None:
            return ANSI_16_RGB[index if name == color else index + 8]
    elif isinstance(color, int):
        return palette_to_rgb(color)
    raise ValueError(f"Cannot resolve color: {color!r}")


# --- Escape sequence grammar -------------------------------------------------

CSI_PREFIX_PATTERN = r"\x1b\[[0-?]*[ -/]*"
"""A CSI sequence short of its final byte, in ECMA-48 syntax.

`ESC [`, then the parameter bytes and the intermediate bytes. A stream read in
chunks can end on one, the rest of the sequence still to arrive.
"""

CSI_PATTERN = rf"{CSI_PREFIX_PATTERN}[@-~]"
"""One CSI sequence, SGR styles included.

{data}`CSI_PREFIX_PATTERN`, then a final byte, like the `m` closing an SGR
escape or the `~` closing `ESC [ 200 ~`.
"""

ANSI_ESCAPE_PATTERN = (
    r"(?:"
    # An OSC command, like the boundary markers of a terminal hyperlink: `ESC ]`,
    # a payload, then the BEL or `ESC \` closing it. A payload left open runs to
    # the end of the text.
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?"
    # A CSI sequence, SGR styles included: `ESC [`, parameter bytes, intermediate
    # bytes and a final byte.
    rf"|{CSI_PATTERN}"
    # Any other escape sequence: intermediate bytes, then a final byte of the
    # `0` to `~` range, like the `ESC 7` saving the cursor or the `ESC ( B`
    # selecting a character set. The `[` and `]` that open the two forms above
    # are not final bytes here.
    r"|\x1b[ -/]*[0-Z\\^-~]"
    r")"
)
"""One ANSI escape sequence of any kind, SGR styles included, in ECMA-48 syntax."""

_ANSI_ESCAPE_RE: re.Pattern[str] = re.compile(ANSI_ESCAPE_PATTERN)
"""Match one ANSI escape sequence, see {data}`ANSI_ESCAPE_PATTERN`."""

_ANSI_ESCAPE_BYTES_PATTERN = ANSI_ESCAPE_PATTERN.encode("ascii")
"""{data}`ANSI_ESCAPE_PATTERN` over bytes.

Left uncompiled: few callers strip bytes, so {func}`strip_ansi` lets `re`
compile and cache it on first use instead of every import paying for it."""


@overload
def strip_ansi(text: str) -> str: ...
@overload
def strip_ansi(text: bytes) -> bytes: ...
def strip_ansi(text: str | bytes) -> str | bytes:
    """Remove every ANSI escape sequence from `text`, leaving its plain text.

    Styles, cursor movements, screen clearing and OSC commands all go. A terminal
    hyperlink keeps its display text and loses its URI, which lived in the markers
    around it. Bytes come back as bytes.
    """
    if isinstance(text, bytes):
        return re.sub(_ANSI_ESCAPE_BYTES_PATTERN, b"", text)
    return _ANSI_ESCAPE_RE.sub("", text)


# --- SGR decoding ------------------------------------------------------------


def sgr_params(params: str) -> tuple[int, ...]:
    r"""Decode an SGR parameter substring into a sequence of integer codes.

    Per ECMA-48, an empty parameter defaults to `0`: `\x1b[m` is a full
    reset, and `\x1b[;31m` carries a reset followed by a red foreground.
    """
    return tuple(int(code) if code else 0 for code in params.split(";"))


def apply_sgr_codes(
    codes: Sequence[int],
    state: dict[str, Any],
    *,
    resets: bool = True,
) -> None:
    """Apply SGR parameter *codes* to the mutable style *state*, in place.

    The single source of truth for SGR semantics, shared by
    {func}`~click_extra.styling.split_ansi` (with the default `resets=True`) and
    {meth}`~click_extra.styling.Style.from_ansi` (with `resets=False`).

    Style-setting codes add entries to *state*, keyed by
    {class}`~click_extra.styling.Style` field names. When *resets* is true, the
    full `0` reset clears the state, and selective resets drop their attribute:
    `22` (bold and dim), `23` (italic), `24` (underline), `25` (blink), `27`
    (reverse), `29` (strikethrough), `39` (foreground), `49` (background) and
    `55` (overline). When *resets* is false all of them are ignored, letting
    {meth}`~click_extra.styling.Style.from_ansi` merge escapes without wiping
    already-parsed codes.

    Unknown codes are silently skipped, like terminals do.
    """
    i = 0
    total = len(codes)
    while i < total:
        code = codes[i]
        if code in SGR_ATTRIBUTES:
            state[SGR_ATTRIBUTES[code]] = True
        elif code in (38, 48):
            key = "fg" if code == 38 else "bg"
            if i + 2 < total and codes[i + 1] == 5:
                state[key] = codes[i + 2]
                i += 2
            elif i + 4 < total and codes[i + 1] == 2:
                state[key] = (codes[i + 2], codes[i + 3], codes[i + 4])
                i += 4
        elif resets and code == 0:
            state.clear()
        elif resets and code in _SGR_RESETS:
            for field_name in _SGR_RESETS[code]:
                state.pop(field_name, None)
        else:
            for first, last, key, prefix in _SGR_COLOR_RANGES:
                if first <= code <= last:
                    state[key] = prefix + ANSI_NAMES[code - first]
                    break
        i += 1


def open_ansi(text: str, opened: str = "") -> str:
    r"""Return the ANSI SGR escapes still in effect at the end of *text*.

    Escapes accumulate in the order they were read. A full `0` reset (its
    parameter-less `\x1b[m` form included) empties the accumulator, so the
    result re-opens what *text* left dangling and nothing else. Escapes come
    back verbatim rather than folded into a {class}`~click_extra.styling.Style`,
    which keeps a code this module does not model.

    Use it to splice a styled fragment into styled text: the fragment closes
    with a reset of its own, which would otherwise strip the surrounding
    styling from everything after it. See
    {func}`~click_extra.highlight.highlight`.

    :param text: the string to read the escapes from.
    :param opened: escapes already in effect before *text*, as returned by an
        earlier call. Feeding a string one chunk at a time then costs one pass
        over it, where re-reading the whole prefix per chunk costs one per
        chunk. A chunk must not start or end in the middle of an escape: the
        two halves match nothing, and the escape is lost.
    """
    if "\x1b" not in text:
        return opened
    active: list[str] = [opened] if opened else []
    for match in ANSI_SGR_RE.finditer(text):
        codes = sgr_params(match.group(1))
        if 0 in codes:
            active.clear()
        # A bare reset opens nothing, so it is dropped rather than accumulated.
        # One carrying more parameters still sets them: `\x1b[0;31m` reopens red.
        if any(codes):
            active.append(match.group(0))
    return "".join(active)
