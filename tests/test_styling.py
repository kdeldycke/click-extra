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
"""Tests for click_extra.styling.Style extras."""

from __future__ import annotations

import cloup
import pytest

from click_extra import Style


# --- 1. Hex string color shorthand ------------------------------------------


@pytest.mark.parametrize(
    ("hex_str", "expected_rgb"),
    [
        ("#ff0000", (0xFF, 0x00, 0x00)),
        ("#f1fa8c", (0xF1, 0xFA, 0x8C)),
        ("#FFFFFF", (0xFF, 0xFF, 0xFF)),  # uppercase
        ("#000", (0x00, 0x00, 0x00)),  # 3-digit shorthand expands
        ("#abc", (0xAA, 0xBB, 0xCC)),
    ],
)
def test_hex_fg_converts_to_rgb_tuple(hex_str, expected_rgb):
    s = Style(fg=hex_str)
    assert s.fg == expected_rgb


def test_hex_bg_converts_to_rgb_tuple():
    s = Style(bg="#282a36")
    assert s.bg == (0x28, 0x2A, 0x36)


def test_hex_invalid_raises():
    with pytest.raises(ValueError, match="Not a valid hex color"):
        Style(fg="#xyz")
    with pytest.raises(ValueError, match="Not a valid hex color"):
        Style(fg="#1234")  # 4 chars: not a recognized form


def test_named_color_string_passes_through():
    """Plain named-color strings must not be touched by the hex shorthand."""
    s = Style(fg="cyan")
    assert s.fg == "cyan"


# --- 2. Composition operator ------------------------------------------------


def test_or_right_operand_wins_on_conflicts():
    a = Style(fg="red", bold=True)
    b = Style(fg="blue", italic=True)
    merged = a | b
    assert merged.fg == "blue"  # b wins
    assert merged.bold is True  # only a sets it
    assert merged.italic is True  # only b sets it


def test_or_returns_subclass_instance():
    merged = Style(fg="red") | Style(bold=True)
    assert isinstance(merged, Style)
    assert type(merged) is Style


def test_or_with_cloup_style_promotes_to_subclass():
    merged = Style(fg="red") | cloup.Style(bold=True)
    assert isinstance(merged, Style)
    assert merged.fg == "red"
    assert merged.bold is True


def test_ror_with_cloup_left_operand():
    """``cloup_style | my_style`` is reached via ``__ror__``."""
    merged = cloup.Style(fg="red") | Style(bold=True)
    assert isinstance(merged, Style)
    assert merged.fg == "red"
    assert merged.bold is True


def test_or_with_non_style_returns_notimplemented():
    """Style | int falls through to ``int.__ror__`` and raises ``TypeError``."""
    with pytest.raises(TypeError):
        Style(fg="red") | 42


# --- 3. cascade() -----------------------------------------------------------


def test_cascade_fills_unset_fields_from_base():
    base = Style(fg="cyan", bold=True, italic=True)
    derived = Style(fg="red")
    merged = derived.cascade(base)
    assert merged.fg == "red"  # derived wins
    assert merged.bold is True  # filled from base
    assert merged.italic is True  # filled from base


def test_cascade_keeps_subclass_identity():
    merged = Style(fg="red").cascade(Style(bold=True))
    assert isinstance(merged, Style)


def test_cascade_with_non_style_raises():
    with pytest.raises(TypeError, match="not a Style"):
        Style(fg="red").cascade("not a style")


# --- 4. to_dict() / from_dict() ---------------------------------------------


def test_to_dict_omits_unset_fields():
    s = Style(fg="#f1fa8c", bold=True)
    d = s.to_dict()
    assert d == {"fg": "#f1fa8c", "bold": True}


def test_to_dict_serializes_rgb_as_hex():
    s = Style(fg=(0xF1, 0xFA, 0x8C))
    assert s.to_dict() == {"fg": "#f1fa8c"}


def test_to_dict_omits_none_only():
    """``False`` boolean attributes are kept; only ``None`` is filtered out."""
    # Actually our to_dict treats only None as "unset". False is preserved.
    s = Style(fg="red", bold=False)
    d = s.to_dict()
    assert d == {"fg": "red", "bold": False}


def test_from_dict_round_trip():
    original = Style(fg="#bd93f9", bold=True, underline=True)
    restored = Style.from_dict(original.to_dict())
    assert restored == original


def test_from_dict_accepts_hex_or_rgb():
    """Both hex strings and RGB tuples work as input."""
    via_hex = Style.from_dict({"fg": "#ff5555"})
    via_rgb = Style.from_dict({"fg": (0xFF, 0x55, 0x55)})
    assert via_hex == via_rgb


# --- 5. __str__ -------------------------------------------------------------


def test_str_returns_styled_sample():
    s = Style(fg="red", bold=True)
    rendered = str(s)
    assert rendered.endswith("sample\x1b[0m")
    assert "\x1b[" in rendered  # ANSI code present


def test_str_no_styling_has_no_color_codes():
    """Style with no fields set produces only click's bare reset suffix."""
    rendered = str(Style())
    # click.style always appends ``\x1b[0m`` even when no SGR codes precede it.
    assert "sample" in rendered
    assert "\x1b[31" not in rendered  # no actual color escape


# --- 6. __repr__ ------------------------------------------------------------


def test_repr_compact_named_color():
    assert repr(Style(fg="cyan", dim=True)) == "Style(fg='cyan', dim)"


def test_repr_compact_rgb_to_hex():
    assert repr(Style(fg=(0xF1, 0xFA, 0x8C), bold=True)) == "Style(fg=#f1fa8c, bold)"


def test_repr_empty_style():
    assert repr(Style()) == "Style()"


def test_repr_multiple_attrs():
    rendered = repr(
        Style(fg="red", bg="black", bold=True, underline=True, italic=True),
    )
    assert rendered == "Style(fg='red', bg='black', bold, italic, underline)"


# --- 7. to_css() ------------------------------------------------------------


def test_to_css_basic():
    css = Style(fg="#f1fa8c", bold=True).to_css()
    assert css == "color: #f1fa8c; font-weight: bold"


def test_to_css_named_color_passes_through():
    css = Style(fg="red").to_css()
    assert css == "color: red"


def test_to_css_bright_named_color_resolves_to_rgb():
    """Bright ANSI colors aren't valid CSS keywords: convert to RGB."""
    css = Style(fg="bright_red").to_css()
    assert css.startswith("color: #")


def test_to_css_text_decorations_combine():
    css = Style(underline=True, strikethrough=True).to_css()
    assert "text-decoration: underline line-through" in css


def test_to_css_dim_emits_opacity():
    assert "opacity: 0.6" in Style(dim=True).to_css()


def test_to_css_empty_style_returns_empty_string():
    assert Style().to_css() == ""


# --- 8. from_ansi() ---------------------------------------------------------


@pytest.mark.parametrize(
    ("escape", "expected"),
    [
        ("\x1b[31m", Style(fg="red")),
        ("\x1b[1m", Style(bold=True)),
        ("\x1b[31;1m", Style(fg="red", bold=True)),
        ("\x1b[91m", Style(fg="bright_red")),
        ("\x1b[42m", Style(bg="green")),
        ("\x1b[102m", Style(bg="bright_green")),
        ("\x1b[3;4m", Style(italic=True, underline=True)),
        ("\x1b[2m", Style(dim=True)),
        ("\x1b[7m", Style(reverse=True)),
        ("\x1b[9m", Style(strikethrough=True)),
        # 256-color extension.
        ("\x1b[38;5;42m", Style(fg=42)),
        ("\x1b[48;5;200m", Style(bg=200)),
        # 24-bit RGB extension.
        ("\x1b[38;2;241;250;140m", Style(fg=(241, 250, 140))),
        ("\x1b[38;2;241;250;140;1m", Style(fg=(241, 250, 140), bold=True)),
        # Reset code is ignored.
        ("\x1b[0;31m", Style(fg="red")),
    ],
)
def test_from_ansi_parses_codes(escape, expected):
    assert Style.from_ansi(escape) == expected


def test_from_ansi_round_trip_through_call():
    """A Style can be parsed back from its own ANSI output."""
    original = Style(fg="red", bold=True)
    rendered = original("text")
    # Extract just the leading SGR escape (before the text).
    leading = rendered.split("text", 1)[0]
    parsed = Style.from_ansi(leading)
    assert parsed == original


def test_from_ansi_invalid_raises():
    with pytest.raises(ValueError, match="Not an ANSI SGR escape"):
        Style.from_ansi("not an escape")


# --- 9. contrast_ratio() ----------------------------------------------------


def test_contrast_ratio_white_on_black_is_max():
    ratio = Style(fg="#ffffff").contrast_ratio(Style(fg="#000000"))
    assert ratio == pytest.approx(21.0, abs=0.01)


def test_contrast_ratio_identical_colors_is_one():
    ratio = Style(fg="#aaaaaa").contrast_ratio(Style(fg="#aaaaaa"))
    assert ratio == pytest.approx(1.0, abs=0.001)


def test_contrast_ratio_is_symmetric():
    a = Style(fg="#ff5555")
    b = Style(fg="#282a36")
    assert a.contrast_ratio(b) == b.contrast_ratio(a)


def test_contrast_ratio_meets_wcag_aa_for_dracula_default():
    """Dracula's default fg/bg pair clears WCAG AA (4.5)."""
    fg = Style(fg="#f8f8f2")
    bg = Style(fg="#282a36")
    assert fg.contrast_ratio(bg) >= 4.5


def test_contrast_ratio_requires_both_fgs():
    with pytest.raises(ValueError, match="foreground color"):
        Style().contrast_ratio(Style(fg="red"))


# --- 10. __eq__ / __hash__ --------------------------------------------------


def test_eq_ignores_style_kwargs_cache():
    """Equality must not depend on cloup's lazy ``_style_kwargs`` cache."""
    a = Style(fg="red")
    b = Style(fg="red")
    a("trigger")  # primes a's _style_kwargs
    assert b._style_kwargs is None
    assert a._style_kwargs is not None
    assert a == b
    assert hash(a) == hash(b)


def test_eq_with_cloup_style():
    """A click-extra Style equals an equivalent cloup.Style."""
    assert Style(fg="red") == cloup.Style(fg="red")
