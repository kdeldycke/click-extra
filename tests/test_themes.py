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
"""Tests for built-in themes loaded from ``click_extra/themes.toml``."""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path

import pytest
from cloup._util import identity

from click_extra import Style
from click_extra.theme import (
    BUILTIN_THEMES,
    LITERAL_STYLES,
    REPLACEABLE_STYLES,
    HelpExtraTheme,
)

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

# Each theme's assumed background. Branded themes use the canonical hex
# from each scheme's spec; ANSI themes assume the conventional terminal
# default (black on dark, white on light) since their actual rendering
# tracks whatever palette the user's terminal is configured with.
_THEME_BACKGROUNDS: dict[str, str] = {
    "dark": "#000000",
    "dracula": "#282a36",
    "light": "#ffffff",
    # `manpage` is colorless, so its background is never used for a contrast
    # check; any value satisfies the dict lookup in the legibility test.
    "manpage": "#000000",
    "monokai": "#272822",
    "nord": "#2e3440",
    "solarized_dark": "#002b36",
}

# Branded themes are 24-bit RGB and ship with deliberate palettes, so we
# can hold them to a real WCAG threshold. ANSI themes inherit terminal
# rendering and only get the legibility floor below.
_BRANDED_THEMES: tuple[str, ...] = (
    "dracula",
    "monokai",
    "nord",
    "solarized_dark",
)

# Slots that carry primary readable text. These should clear WCAG AA Large
# (3.0): readable enough for headings and dense developer-facing output.
# Strict AA (4.5) is unattainable for some themes (Solarized's #268bd2 on
# #002b36 famously sits at 4.08), so AA Large is the realistic floor.
_READABLE_SLOTS: tuple[str, ...] = (
    "option",
    "error",
    "warning",
    "success",
)

# Absolute legibility floor: anything below this is essentially invisible
# against the assumed background. Catches palette tweaks that would render
# a slot unusable, while still letting subdued slots stay subdued.
_LEGIBILITY_FLOOR: float = 1.5

# WCAG 2.x AA Large threshold for normal text in heading-sized contexts.
# https://www.w3.org/TR/WCAG22/#contrast-minimum
_WCAG_AA_LARGE: float = 3.0

_THEMES_TOML = Path(__file__).parent.parent / "click_extra" / "themes.toml"


def _toml_table_order() -> list[str]:
    """Return the top-level table names in the order they appear in ``themes.toml``."""
    text = _THEMES_TOML.read_text(encoding="utf-8")
    return re.findall(r"^\[([A-Za-z_][\w]*)\]\s*$", text, flags=re.MULTILINE)


def _parsed_themes_toml() -> dict[str, dict]:
    """Load ``themes.toml`` raw (without going through ``HelpExtraTheme.from_dict``)."""
    result: dict[str, dict] = tomllib.loads(_THEMES_TOML.read_text(encoding="utf-8"))
    return result


# --- Source-of-truth checks -------------------------------------------------


def test_themes_toml_tables_alphabetical():
    """Top-level tables in ``themes.toml`` are declared alphabetically."""
    declared = _toml_table_order()
    assert declared == sorted(declared), (
        f"Theme tables in click_extra/themes.toml must be alphabetical. "
        f"Got: {declared}\nExpected: {sorted(declared)}"
    )


def test_builtin_themes_alphabetical():
    """``BUILTIN_THEMES`` keys are alphabetical (matters for ``--theme`` choices)."""
    keys = list(BUILTIN_THEMES)
    assert keys == sorted(keys), (
        f"BUILTIN_THEMES keys must be alphabetical. "
        f"Got: {keys}\nExpected: {sorted(keys)}"
    )


def test_builtin_themes_match_toml():
    """Every TOML table maps to a ``BUILTIN_THEMES`` entry, and vice versa."""
    parsed = _parsed_themes_toml()
    assert set(parsed) == set(BUILTIN_THEMES), (
        f"Mismatch between themes.toml tables and BUILTIN_THEMES.\n"
        f"In TOML only: {set(parsed) - set(BUILTIN_THEMES)}\n"
        f"In BUILTIN_THEMES only: {set(BUILTIN_THEMES) - set(parsed)}"
    )


def test_builtin_themes_are_helpextratheme_instances():
    """Every ``BUILTIN_THEMES`` entry is a :class:`HelpExtraTheme` instance."""
    for name, theme in BUILTIN_THEMES.items():
        assert isinstance(theme, HelpExtraTheme), (
            f"BUILTIN_THEMES[{name!r}] is {type(theme).__name__}, "
            f"expected HelpExtraTheme."
        )


@pytest.mark.parametrize("theme_name", sorted(BUILTIN_THEMES))
def test_builtin_themes_follow_manpage_font_convention(theme_name):
    """Every built-in theme bolds literal slots and italicizes replaceable ones.

    Encodes the man-pages(7) typographic convention (``LITERAL_STYLES`` bold,
    ``REPLACEABLE_STYLES`` italic) as an invariant across all palettes, so
    adding a theme or tweaking a slot can't silently drop the
    literal/replaceable distinction. The ``manpage`` theme renders it with no
    color at all.
    """
    theme = BUILTIN_THEMES[theme_name]
    for slot in sorted(LITERAL_STYLES):
        assert getattr(getattr(theme, slot), "bold", None) is True, (
            f"{theme_name}.{slot} must be bold (literal token)."
        )
    for slot in sorted(REPLACEABLE_STYLES):
        assert getattr(getattr(theme, slot), "italic", None) is True, (
            f"{theme_name}.{slot} must be italic (replaceable token)."
        )


# --- Round-trip serialization -----------------------------------------------


@pytest.mark.parametrize("theme_name", sorted(BUILTIN_THEMES))
def test_theme_round_trips_through_dict(theme_name):
    """``HelpExtraTheme.to_dict``/``from_dict`` round-trips every built-in theme."""
    theme = BUILTIN_THEMES[theme_name]
    rebuilt = HelpExtraTheme.from_dict(theme.to_dict())
    assert rebuilt == theme


@pytest.mark.parametrize("theme_name", sorted(BUILTIN_THEMES))
def test_themes_toml_payload_matches_to_dict(theme_name):
    """The TOML payload for each theme equals what ``to_dict`` would emit."""
    parsed = _parsed_themes_toml()
    assert parsed[theme_name] == BUILTIN_THEMES[theme_name].to_dict()


def test_to_dict_omits_identity_slots():
    """Slots left at the ``identity`` default do not appear in ``to_dict`` output."""
    blank = HelpExtraTheme()
    assert blank.to_dict() == {}


def test_to_dict_emits_cross_ref_highlight_only_when_overridden():
    """``cross_ref_highlight`` is emitted only when it differs from the default."""
    default = HelpExtraTheme()
    assert "cross_ref_highlight" not in default.to_dict()

    flipped = HelpExtraTheme(cross_ref_highlight=False)
    assert flipped.to_dict() == {"cross_ref_highlight": False}


def test_from_dict_rejects_unknown_keys():
    """Typos like ``optoin`` raise ``TypeError`` instead of being silently dropped."""
    with pytest.raises(TypeError, match="optoin"):
        HelpExtraTheme.from_dict({"optoin": {"fg": "cyan"}})


# --- Cascade ----------------------------------------------------------------


def test_cascade_overrides_only_set_slots():
    """``cascade`` keeps base's slots wherever the overlay leaves them at default."""
    dark = BUILTIN_THEMES["dark"]
    overlay = HelpExtraTheme.from_dict({"option": {"fg": "magenta"}})
    merged = overlay.cascade(dark)

    # Overlay slot wins.
    assert isinstance(merged.option, Style)
    assert merged.option.fg == "magenta"
    # All other slots come from the base.
    assert merged.heading == dark.heading
    assert merged.critical == dark.critical
    assert merged.deprecated == dark.deprecated


def test_cascade_returns_new_instance_when_overlay_changes_anything():
    """Even a single-slot overlay produces a distinct theme instance."""
    dark = BUILTIN_THEMES["dark"]
    overlay = HelpExtraTheme.from_dict({"option": {"fg": "magenta"}})
    merged = overlay.cascade(dark)

    assert merged is not dark
    assert isinstance(merged.option, Style)
    assert isinstance(dark.option, Style)
    assert merged.option.fg != dark.option.fg


def test_cascade_round_trips_through_dict():
    """``self.to_dict()`` wins over ``base.to_dict()`` slot-by-slot."""
    light = BUILTIN_THEMES["light"]
    merged = light.cascade(BUILTIN_THEMES["dark"])
    # Every slot light sets wins over dark.
    for slot, value in light.to_dict().items():
        assert merged.to_dict()[slot] == value


def test_cascade_rejects_non_theme_base():
    """``cascade`` rejects anything that is not a :class:`HelpExtraTheme`."""
    overlay = HelpExtraTheme()
    with pytest.raises(TypeError, match="not a HelpExtraTheme"):
        overlay.cascade(object())  # type: ignore[arg-type]


# --- ThemeChoice ------------------------------------------------------------


def test_themechoice_choices_track_global_registry():
    """Outside any context, ``choices`` reflects the module-level registry."""
    from click_extra.theme import ThemeChoice, theme_registry

    tc = ThemeChoice()
    assert set(tc.choices) == set(theme_registry)


def test_themechoice_choices_pick_up_context_overrides():
    """A theme stashed under ``THEME_OVERRIDES`` shows up in ``choices``."""
    import click

    from click_extra import context as cx
    from click_extra.theme import ThemeChoice

    @click.command
    def noop() -> None:
        pass

    tc = ThemeChoice()
    with click.Context(noop) as ctx:
        cx.set(ctx, cx.THEME_OVERRIDES, {"midnight": BUILTIN_THEMES["dark"]})
        assert "midnight" in tc.choices


# --- WCAG contrast quality gates --------------------------------------------


@pytest.mark.parametrize(
    ("theme_name", "slot"),
    [(theme, slot) for theme in _BRANDED_THEMES for slot in _READABLE_SLOTS],
)
def test_branded_themes_meet_wcag_aa_large(theme_name, slot):
    """Branded themes' readable-text slots clear WCAG AA Large (3.0+).

    Branded palettes are deliberate 24-bit RGB choices, so we can hold them
    to a real WCAG threshold. AA Large is the realistic floor: full AA
    (4.5+) is unattainable for some published themes (e.g. Solarized's
    accent blue on its base03 background sits at ~4.08).

    A regression that drops one of these slots below 3.0 means the theme is
    less readable than what currently ships and warrants a deliberate
    palette tweak rather than a silent slip.
    """
    theme = BUILTIN_THEMES[theme_name]
    fg_style = getattr(theme, slot)
    bg_style = Style(fg=_THEME_BACKGROUNDS[theme_name])
    ratio = fg_style.contrast_ratio(bg_style)
    assert ratio >= _WCAG_AA_LARGE, (
        f"{theme_name}.{slot} (fg={fg_style.fg!r}) on {_THEME_BACKGROUNDS[theme_name]} "
        f"has contrast {ratio:.2f}, below WCAG AA Large ({_WCAG_AA_LARGE})."
    )


@pytest.mark.parametrize("theme_name", sorted(BUILTIN_THEMES))
def test_themes_meet_legibility_floor(theme_name):
    """Every styled slot in every theme stays above the legibility floor.

    Subdued slots (``debug``, ``bracket``, ``default``, ...) are allowed to
    fall below WCAG AA Large by design, but no slot should be effectively
    invisible against the theme's assumed background. Catches accidental
    palette tweaks like setting an attribute to nearly the background color.
    """
    theme = BUILTIN_THEMES[theme_name]
    bg_style = Style(fg=_THEME_BACKGROUNDS[theme_name])
    failures: list[str] = []
    for f in dataclasses.fields(theme):
        slot_value = getattr(theme, f.name)
        if slot_value is identity:
            continue
        fg = getattr(slot_value, "fg", None)
        if fg is None:
            continue
        ratio = slot_value.contrast_ratio(bg_style)
        if ratio < _LEGIBILITY_FLOOR:
            failures.append(f"{theme_name}.{f.name} (fg={fg!r}) ratio={ratio:.2f}")
    assert not failures, (
        f"Slots below the legibility floor ({_LEGIBILITY_FLOOR}) on "
        f"{_THEME_BACKGROUNDS[theme_name]}: " + ", ".join(failures)
    )
