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

import importlib.metadata

import click
import cloup
import pytest
from boltons.strutils import strip_ansi

from click_extra import Style
from click_extra.styling import (
    _nearest_256,
    ansi_to_html,
    ansi_to_jira,
    ansi_to_latex,
    ansi_to_textile,
    render_ansi,
    split_ansi,
    supports_truecolor,
)

CLICK_VERSION = tuple(
    int(part) for part in importlib.metadata.version("click").split(".")[:2]
)
"""Major and minor version of the installed Click package.

Click ``8.5.0`` started validating ``fg`` / ``bg`` color arguments: the 256-color
index ``0`` is no longer dropped, and falsy non-``None`` values raise ``TypeError``
instead of being silently ignored. See `pallets/click#3666
<https://github.com/pallets/click/pull/3666>`_.
"""

CLICK_HAS_PALETTE_ZERO_FIX = "\x1b[38;5;0m" in click.style("X", fg=0)
"""True when Click emits the 256-color escape sequence for palette index ``0``.

Click ``8.5.0`` fixed a bug where ``fg=0`` / ``bg=0`` were silently dropped
because the integer ``0`` is falsy. Development snapshots with version numbers
>= ``8.5`` may not yet carry this fix, so a version comparison alone is
unreliable.
"""

try:
    click.style("X", fg="")
    CLICK_REJECTS_EMPTY_COLOR = False
except TypeError:
    CLICK_REJECTS_EMPTY_COLOR = True
"""True when Click raises ``TypeError`` for empty-string ``fg`` / ``bg`` arguments.

Click ``8.5.0`` started rejecting falsy non-``None`` color values.  Development
snapshots with version numbers >= ``8.5`` may not yet enforce this validation.
"""

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
        Style(fg="red").cascade("not a style")  # type: ignore[arg-type]


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


def test_repr_palette_index_zero():
    """Index ``0`` is falsy but set: it must survive the ``is not None`` guards."""
    assert repr(Style(fg=0)) == "Style(fg=0)"


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


def test_to_css_palette_index_zero():
    """Palette index ``0`` is falsy but set, and resolves to ANSI black."""
    assert Style(fg=0).to_css() == "color: #000000"


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
        # Index 0 is falsy but a valid color (black).
        ("\x1b[38;5;0m", Style(fg=0)),
        ("\x1b[48;5;0m", Style(bg=0)),
        # 24-bit RGB extension.
        ("\x1b[38;2;241;250;140m", Style(fg=(241, 250, 140))),
        ("\x1b[38;2;241;250;140;1m", Style(fg=(241, 250, 140), bold=True)),
        # Overline is carried by SGR 53.
        ("\x1b[53m", Style(overline=True)),
        # Reset codes are ignored, wherever they sit.
        ("\x1b[0;31m", Style(fg="red")),
        ("\x1b[31m\x1b[0m", Style(fg="red")),
        ("\x1b[31;39m", Style(fg="red")),
        ("\x1b[1m\x1b[22m", Style(bold=True)),
        # The parameter-less escape is a bare reset, so it parses to no style.
        ("\x1b[m", Style()),
    ],
)
def test_from_ansi_parses_codes(escape, expected):
    assert Style.from_ansi(escape) == expected


def test_from_ansi_full_styled_string_round_trip():
    """Parsing a style's complete output (trailing reset included) recovers it."""
    original = Style(fg="red", bold=True)
    assert Style.from_ansi(original("text")) == original


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


# --- 11. Truecolor detection and quantization -------------------------------


@pytest.mark.parametrize(
    ("colorterm", "term", "expected"),
    (
        # Unset: optimistic default keeps 24-bit.
        (None, None, True),
        # COLORTERM positively advertises truecolor (case-insensitive, stripped).
        ("truecolor", None, True),
        ("24bit", None, True),
        ("TrueColor", None, True),
        (" truecolor ", None, True),
        # COLORTERM set to any other value is a deliberate non-truecolor advert.
        ("256", None, False),
        ("8bit", None, False),
        # A 256color TERM is NOT a downgrade: truecolor terminals report it too.
        (None, "xterm-256color", True),
        # A 16color TERM is an unambiguous sub-256 terminal.
        (None, "xterm-16color", False),
        # COLORTERM outranks TERM.
        ("truecolor", "xterm-16color", True),
    ),
)
def test_supports_truecolor(monkeypatch, colorterm, term, expected):
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    if colorterm is not None:
        monkeypatch.setenv("COLORTERM", colorterm)
    if term is not None:
        monkeypatch.setenv("TERM", term)
    assert supports_truecolor() is expected


def test_style_call_keeps_24bit_on_truecolor(monkeypatch):
    """An RGB color emits a 24-bit sequence when the terminal supports truecolor."""
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert Style(fg="#ff0000")("X") == "\x1b[38;2;255;0;0mX\x1b[0m"


def test_style_call_quantizes_without_truecolor(monkeypatch):
    """An RGB color downsamples to the nearest 256-index without truecolor."""
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.setenv("TERM", "xterm-16color")
    index = _nearest_256(255, 0, 0)  # 196
    assert Style(fg="#ff0000")("X") == f"\x1b[38;5;{index}mX\x1b[0m"


@pytest.mark.parametrize("colorterm", ("truecolor", "256"))
def test_style_call_leaves_named_and_indexed_colors(monkeypatch, colorterm):
    """Named and palette-index colors never quantize, regardless of depth."""
    monkeypatch.setenv("COLORTERM", colorterm)
    assert Style(fg="red")("X") == "\x1b[31mX\x1b[0m"
    assert Style(fg=200)("X") == "\x1b[38;5;200mX\x1b[0m"


def test_style_call_cache_survives_depth_flip(monkeypatch):
    """The same style renders correctly when truecolor flips between calls.

    Quantizing on a transient copy must not poison cloup's lazy
    ``_style_kwargs`` cache on the shared (often singleton) style instance.
    """
    style = Style(fg="#ff0000")
    index = _nearest_256(255, 0, 0)

    monkeypatch.setenv("COLORTERM", "truecolor")
    assert style("X") == "\x1b[38;2;255;0;0mX\x1b[0m"

    monkeypatch.setenv("COLORTERM", "256")
    assert style("X") == f"\x1b[38;5;{index}mX\x1b[0m"

    monkeypatch.setenv("COLORTERM", "truecolor")
    assert style("X") == "\x1b[38;2;255;0;0mX\x1b[0m"


# --- 12. Upstream Click color handling ---------------------------------------


@pytest.mark.xfail(
    not CLICK_HAS_PALETTE_ZERO_FIX,
    reason="This Click build drops the 256-color index 0: pallets/click#3666.",
    strict=True,
)
@pytest.mark.parametrize(
    ("style", "expected"),
    [
        (Style(fg=0), "\x1b[38;5;0mX\x1b[0m"),
        (Style(bg=0), "\x1b[48;5;0mX\x1b[0m"),
    ],
)
def test_style_call_palette_index_zero(style, expected):
    """Rendering palette index ``0`` must emit its escape code, not drop it."""
    assert style("X") == expected


@pytest.mark.skipif(
    CLICK_REJECTS_EMPTY_COLOR,
    reason="This Click build rejects empty-string colors.",
)
@pytest.mark.parametrize("style", [Style(fg=""), Style(bg="")])
def test_style_call_empty_string_color_ignored(style):
    """Click < 8.5 silently ignores falsy colors at render time."""
    assert style("X") == "X\x1b[0m"


@pytest.mark.skipif(
    not CLICK_REJECTS_EMPTY_COLOR,
    reason="This Click build silently ignores empty-string colors.",
)
@pytest.mark.parametrize("style", [Style(fg=""), Style(bg="")])
def test_style_call_empty_string_color_rejected(style):
    """Click >= 8.5 validates colors at render time and rejects empty strings."""
    with pytest.raises(TypeError, match="Unknown color"):
        style("X")


# --- 13. split_ansi() --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("plain text", [(Style(), "plain text")], id="no-escapes"),
        pytest.param(
            "\x1b[31mred\x1b[0m",
            [(Style(fg="red"), "red")],
            id="single-styled-run",
        ),
        pytest.param(
            "\x1b[34mFriday\x1b[0m and \x1b[31m\x1b[1mHot\x1b[0m",
            [
                (Style(fg="blue"), "Friday"),
                (Style(), " and "),
                (Style(fg="red", bold=True), "Hot"),
            ],
            id="interleaved-runs",
        ),
        pytest.param(
            "\x1b[31mred\x1b[1mred bold\x1b[0mplain",
            [
                (Style(fg="red"), "red"),
                (Style(fg="red", bold=True), "red bold"),
                (Style(), "plain"),
            ],
            id="state-accumulates",
        ),
        pytest.param(
            "\x1b[31;1mX\x1b[22mY\x1b[39mZ",
            [
                (Style(fg="red", bold=True), "X"),
                (Style(fg="red"), "Y"),
                (Style(), "Z"),
            ],
            id="selective-resets",
        ),
        pytest.param("\x1b[mplain", [(Style(), "plain")], id="empty-reset"),
        pytest.param(
            "\x1b[31ma\x1b[31mb",
            [(Style(fg="red"), "ab")],
            id="identical-styles-merge",
        ),
        pytest.param("a\x1b[0mb", [(Style(), "ab")], id="noop-reset-merges"),
        pytest.param(
            "\x1b[38;5;196mflame\x1b[0m",
            [(Style(fg=196), "flame")],
            id="256-color",
        ),
        pytest.param(
            "\x1b[38;2;241;250;140mlemon\x1b[0m",
            [(Style(fg=(241, 250, 140)), "lemon")],
            id="24bit-color",
        ),
        pytest.param(
            "\x1b[41mtomato\x1b[49m plain",
            [(Style(bg="red"), "tomato"), (Style(), " plain")],
            id="background",
        ),
        pytest.param(
            "\x1b[31munterminated",
            [(Style(fg="red"), "unterminated")],
            id="unterminated-style",
        ),
        pytest.param("ab\x1b[2Kcd", [(Style(), "abcd")], id="non-sgr-csi-dropped"),
        pytest.param(
            "\x1b]8;;https://example.com\x1b\\Berlin\x1b]8;;\x1b\\",
            [(Style(), "Berlin")],
            id="osc8-hyperlink-keeps-text",
        ),
    ],
)
def test_split_ansi(text, expected):
    assert list(split_ansi(text)) == expected


def test_split_ansi_empty_string():
    assert list(split_ansi("")) == []


def test_split_ansi_preserves_text():
    """Concatenated run texts equal the ANSI-stripped input."""
    text = (
        "plain \x1b[31mred\x1b[0m mid \x1b[1;4mbold+underline\x1b[0m"
        " \x1b[38;5;42mgreenish\x1b[m end"
    )
    assert "".join(run for _, run in split_ansi(text)) == strip_ansi(text)


# --- 14. render_ansi() -------------------------------------------------------


def test_render_ansi_passthrough_unstyled():
    text = "no escapes | at all"
    assert render_ansi(text, lambda style, run: f"<{run}>") == text


def test_render_ansi_wraps_styled_runs():
    result = render_ansi("a \x1b[31mred\x1b[0m z", lambda style, run: f"<{run}>")
    assert result == "a <red> z"


def test_render_ansi_splits_runs_at_newlines():
    """No markup wrapper ever crosses a line boundary."""
    result = render_ansi("\x1b[31mtwo\nlines\x1b[0m", lambda style, run: f"<{run}>")
    assert result == "<two>\n<lines>"


# --- 15. ANSI-to-markup converters -------------------------------------------

BLUE = "\x1b[34mSummer\x1b[0m"
BLUE_BOLD = "\x1b[34m\x1b[1mSummer\x1b[0m"


@pytest.mark.parametrize(
    ("converter", "text", "expected"),
    [
        # HTML: inline-CSS spans, straight from Style.to_css().
        pytest.param(
            ansi_to_html,
            BLUE,
            '<span style="color: blue">Summer</span>',
            id="html-named-color",
        ),
        pytest.param(
            ansi_to_html,
            BLUE_BOLD,
            '<span style="color: blue; font-weight: bold">Summer</span>',
            id="html-bold",
        ),
        pytest.param(
            ansi_to_html,
            "\x1b[94mSummer\x1b[0m",
            '<span style="color: #5555ff">Summer</span>',
            id="html-bright-color-resolves-to-hex",
        ),
        pytest.param(
            ansi_to_html,
            "\x1b[38;5;196mSummer\x1b[0m",
            '<span style="color: #ff0000">Summer</span>',
            id="html-256-color",
        ),
        pytest.param(
            ansi_to_html,
            "\x1b[38;2;241;250;140mSummer\x1b[0m",
            '<span style="color: #f1fa8c">Summer</span>',
            id="html-24bit-color",
        ),
        pytest.param(
            ansi_to_html,
            "\x1b[41mSummer\x1b[0m",
            '<span style="background-color: red">Summer</span>',
            id="html-background",
        ),
        pytest.param(
            ansi_to_html,
            "\x1b[2mSummer\x1b[0m",
            '<span style="opacity: 0.6">Summer</span>',
            id="html-dim",
        ),
        pytest.param(
            ansi_to_html,
            "\x1b[9mSummer\x1b[0m",
            '<span style="text-decoration: line-through">Summer</span>',
            id="html-strikethrough",
        ),
        # Blink has no CSS equivalent: the run is left unwrapped.
        pytest.param(ansi_to_html, "\x1b[5mSummer\x1b[0m", "Summer", id="html-blink"),
        pytest.param(ansi_to_html, "Summer", "Summer", id="html-plain-text"),
        # Jira: {color} macros and wiki emphasis markers.
        pytest.param(
            ansi_to_jira,
            BLUE,
            "{color:blue}Summer{color}",
            id="jira-named-color",
        ),
        pytest.param(
            ansi_to_jira,
            BLUE_BOLD,
            "{color:blue}*Summer*{color}",
            id="jira-bold",
        ),
        pytest.param(
            ansi_to_jira,
            "\x1b[94mSummer\x1b[0m",
            "{color:#5555ff}Summer{color}",
            id="jira-bright-color-resolves-to-hex",
        ),
        pytest.param(
            ansi_to_jira,
            "\x1b[3;4;9mSummer\x1b[0m",
            "_+-Summer-+_",
            id="jira-attribute-markers",
        ),
        # Jira has no equivalent for backgrounds or dim: dropped.
        pytest.param(
            ansi_to_jira, "\x1b[41;2mSummer\x1b[0m", "Summer", id="jira-drops"
        ),
        # LaTeX: xcolor macros for colors, core macros for attributes.
        pytest.param(
            ansi_to_latex,
            BLUE,
            "\\textcolor{blue}{Summer}",
            id="latex-named-color",
        ),
        pytest.param(
            ansi_to_latex,
            BLUE_BOLD,
            "\\textcolor{blue}{\\textbf{Summer}}",
            id="latex-bold",
        ),
        pytest.param(
            ansi_to_latex,
            "\x1b[94mSummer\x1b[0m",
            "\\textcolor[HTML]{5555FF}{Summer}",
            id="latex-bright-color-resolves-to-hex",
        ),
        pytest.param(
            ansi_to_latex,
            "\x1b[41mSummer\x1b[0m",
            "\\colorbox{red}{Summer}",
            id="latex-background",
        ),
        pytest.param(
            ansi_to_latex,
            "\x1b[34;1;3;4mSummer\x1b[0m",
            "\\textcolor{blue}{\\underline{\\textit{\\textbf{Summer}}}}",
            id="latex-nested-macros",
        ),
        # LaTeX has no core equivalent for dim: dropped.
        pytest.param(ansi_to_latex, "\x1b[2mSummer\x1b[0m", "Summer", id="latex-drops"),
        # Textile: CSS spans, straight from Style.to_css().
        pytest.param(
            ansi_to_textile,
            BLUE,
            "%{color: blue}Summer%",
            id="textile-named-color",
        ),
        pytest.param(
            ansi_to_textile,
            BLUE_BOLD,
            "%{color: blue; font-weight: bold}Summer%",
            id="textile-bold",
        ),
    ],
)
def test_ansi_converters(converter, text, expected):
    assert converter(text) == expected
