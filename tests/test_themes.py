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
"""Tests for built-in themes."""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest
from cloup._util import identity

from click_extra import Style, themes
from click_extra.theme import HelpExtraTheme

# Each theme's assumed background. Branded themes use the canonical hex
# from each scheme's spec; ANSI themes assume the conventional terminal
# default (black on dark, white on light) since their actual rendering
# tracks whatever palette the user's terminal is configured with.
_THEME_BACKGROUNDS: dict[str, str] = {
    "dark": "#000000",
    "dracula": "#282a36",
    "light": "#ffffff",
    "monokai": "#272822",
    "nord": "#2e3440",
    "solarized_dark": "#002b36",
}

# Branded themes are 24-bit RGB and ship with deliberate palettes, so we
# can hold them to a real WCAG threshold. ANSI themes inherit terminal
# rendering and only get the legibility floor below.
_BRANDED_THEMES: tuple[str, ...] = (
    "dracula", "monokai", "nord", "solarized_dark",
)

# Slots that carry primary readable text. These should clear WCAG AA Large
# (3.0): readable enough for headings and dense developer-facing output.
# Strict AA (4.5) is unattainable for some themes (Solarized's #268bd2 on
# #002b36 famously sits at 4.08), so AA Large is the realistic floor.
_READABLE_SLOTS: tuple[str, ...] = (
    "option", "error", "warning", "success",
)

# Slots intentionally rendered as low-contrast/subdued (comment-style).
# Excluded from the AA Large gate; only checked against the legibility floor.
_SUBDUED_SLOTS: frozenset[str] = frozenset({
    "debug", "bracket", "envvar", "range_label", "required",
    "metavar", "alias_secondary", "default",
})

# Absolute legibility floor: anything below this is essentially invisible
# against the assumed background. Catches palette tweaks that would render
# a slot unusable, while still letting subdued slots stay subdued.
_LEGIBILITY_FLOOR: float = 1.5

# WCAG 2.x AA Large threshold for normal text in heading-sized contexts.
# https://www.w3.org/TR/WCAG22/#contrast-minimum
_WCAG_AA_LARGE: float = 3.0


def _theme_subclass_names(tree: ast.Module) -> list[str]:
    """Extract names of top-level ``HelpExtraTheme`` subclass definitions."""
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            isinstance(base, ast.Name) and base.id == "HelpExtraTheme"
            for base in node.bases
        )
    ]


def _theme_singleton_names(tree: ast.Module) -> list[str]:
    """Extract names of top-level UPPER_CASE assignments whose RHS is a theme call."""
    theme_class_names = set(_theme_subclass_names(tree))
    names: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target = node.targets[0].id
        if not target.isupper():
            continue
        # RHS must be a call to one of the theme classes (e.g. ``Dark()``).
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id in theme_class_names
        ):
            names.append(target)
    return names


def test_theme_classes_alphabetical():
    """``HelpExtraTheme`` subclasses in ``themes.py`` are declared alphabetically."""
    source = Path(inspect.getsourcefile(themes)).read_text(encoding="utf-8")
    declared = _theme_subclass_names(ast.parse(source))
    assert declared == sorted(declared), (
        f"Theme classes in click_extra/themes.py must be declared alphabetically. "
        f"Got: {declared}\nExpected: {sorted(declared)}"
    )


def test_theme_singletons_alphabetical():
    """UPPER_CASE theme singletons in ``themes.py`` are declared alphabetically."""
    source = Path(inspect.getsourcefile(themes)).read_text(encoding="utf-8")
    declared = _theme_singleton_names(ast.parse(source))
    assert declared == sorted(declared), (
        f"Theme singletons in click_extra/themes.py must be declared alphabetically. "
        f"Got: {declared}\nExpected: {sorted(declared)}"
    )


def test_builtin_themes_alphabetical():
    """``BUILTIN_THEMES`` keys are kept alphabetical (matters for ``--theme`` choices)."""
    keys = list(themes.BUILTIN_THEMES)
    assert keys == sorted(keys), (
        f"BUILTIN_THEMES keys must be alphabetical. "
        f"Got: {keys}\nExpected: {sorted(keys)}"
    )


def test_singletons_match_builtin_themes():
    """Every UPPER_CASE singleton has a matching ``BUILTIN_THEMES`` entry, and vice versa."""
    source = Path(inspect.getsourcefile(themes)).read_text(encoding="utf-8")
    declared = set(_theme_singleton_names(ast.parse(source)))
    registered = {name.upper() for name in themes.BUILTIN_THEMES}
    assert declared == registered, (
        f"Mismatch between theme singletons declared in themes.py and "
        f"BUILTIN_THEMES entries.\nDeclared only: {declared - registered}\n"
        f"Registered only: {registered - declared}"
    )


def test_theme_classes_subclass_helpextratheme():
    """Every theme class declared in ``themes.py`` actually subclasses ``HelpExtraTheme``."""
    source = Path(inspect.getsourcefile(themes)).read_text(encoding="utf-8")
    for name in _theme_subclass_names(ast.parse(source)):
        cls = getattr(themes, name)
        assert isinstance(cls, type), f"{name} is not a class"
        assert issubclass(cls, HelpExtraTheme), (
            f"{name} declares HelpExtraTheme as a base in source but does not "
            f"actually subclass it at runtime."
        )


# --- WCAG contrast quality gates --------------------------------------------


@pytest.mark.parametrize(
    ("theme_name", "slot"),
    [
        (theme, slot)
        for theme in _BRANDED_THEMES
        for slot in _READABLE_SLOTS
    ],
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
    theme = themes.BUILTIN_THEMES[theme_name]
    fg_style = getattr(theme, slot)
    bg_style = Style(fg=_THEME_BACKGROUNDS[theme_name])
    ratio = fg_style.contrast_ratio(bg_style)
    assert ratio >= _WCAG_AA_LARGE, (
        f"{theme_name}.{slot} (fg={fg_style.fg!r}) on {_THEME_BACKGROUNDS[theme_name]} "
        f"has contrast {ratio:.2f}, below WCAG AA Large ({_WCAG_AA_LARGE})."
    )


@pytest.mark.parametrize("theme_name", sorted(themes.BUILTIN_THEMES))
def test_themes_meet_legibility_floor(theme_name):
    """Every styled slot in every theme stays above the legibility floor.

    Subdued slots (``debug``, ``bracket``, ``default``, ...) are allowed to
    fall below WCAG AA Large by design, but no slot should be effectively
    invisible against the theme's assumed background. Catches accidental
    palette tweaks like setting an attribute to nearly the background color.
    """
    theme = themes.BUILTIN_THEMES[theme_name]
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
            failures.append(
                f"{theme_name}.{f.name} (fg={fg!r}) ratio={ratio:.2f}"
            )
    assert not failures, (
        f"Slots below the legibility floor ({_LEGIBILITY_FLOOR}) on "
        f"{_THEME_BACKGROUNDS[theme_name]}: " + ", ".join(failures)
    )
