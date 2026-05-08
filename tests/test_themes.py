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
import inspect
from pathlib import Path

from click_extra import themes
from click_extra.theme import HelpExtraTheme


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
