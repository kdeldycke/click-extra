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
"""Tests for ``click_extra.theme``: in-process isolation, built-in TOML themes
and ``[tool.<cli>.themes.<name>]`` config integration."""

from __future__ import annotations

import dataclasses
import logging
import re
import sys
from pathlib import Path
from textwrap import dedent

import click
import pytest
from click.testing import CliRunner
from cloup._util import identity

import click_extra
from click_extra import (
    Style,
    command,
    context,
    echo,
    option,
    theme as _theme,
)
from click_extra.theme import (
    BUILTIN_THEMES,
    LITERAL_STYLES,
    REPLACEABLE_STYLES,
    HelpTheme,
    ThemeChoice,
    get_theme_registry,
    theme_registry,
    themes_from_config,
)

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

# Alias kept for the built-in-themes section, which reaches module-private
# helpers (``_load_builtin_themes``, ``resources``) and patches module-level
# state on the same object as ``_theme``.
theme_mod = _theme


@command
@option("--name", default="world", help="Who to greet.")
def greet(name):
    """Greet a recipient."""
    echo(f"Hello, {name}!")


# --- In-process isolation and font-role slots -------------------------------


def test_theme_does_not_leak_across_invocations():
    """A `--theme light` invocation must not bleed into a later `--help` render.

    Two back-to-back invocations of the same CLI in the same process:

    1. ``--theme light --help`` -- selects the light palette for this call only.
    2. ``--help`` -- no ``--theme`` argument, must fall back to the dark default.

    The dark theme renders headings with ``\\x1b[94m`` (bright blue); the light
    theme uses ``\\x1b[35m`` (magenta, chosen to stay distinct from its blue
    options). If the second invocation picks up the first's choice via
    process-wide state, it leaks the light palette and the assertion below fails.
    """
    runner = CliRunner()

    light_result = runner.invoke(greet, ["--theme", "light", "--help"], color=True)
    assert light_result.exit_code == 0
    assert "\x1b[35m\x1b[4mUsage:" in light_result.output

    dark_result = runner.invoke(greet, ["--help"], color=True)
    assert dark_result.exit_code == 0
    assert "\x1b[94m\x1b[4mUsage:" in dark_result.output


def test_theme_default_unchanged_after_invocation():
    """An invocation with ``--theme light`` must not mutate the process-wide default."""
    original = _theme.get_default_theme()
    runner = CliRunner()
    runner.invoke(greet, ["--theme", "light", "--help"], color=True)
    assert _theme.get_default_theme() is original


def test_theme_meta_key_matches_registry():
    """:func:`get_current_theme` reads from the same key :class:`ThemeOption` writes."""
    assert context.THEME == "click_extra.theme.active"


def test_font_role_slots_are_known_and_disjoint():
    """``LITERAL_STYLES`` / ``REPLACEABLE_STYLES`` must classify real, distinct slots.

    The two frozensets encode the man-pages(7) bold/italic font roles by slot
    name and are maintained by hand, so guard against drift: every name must be
    a real :class:`HelpTheme` field, the two roles must not overlap, and
    the representative slots must keep their expected role.
    """
    theme_fields = {f.name for f in dataclasses.fields(_theme.HelpTheme)}

    assert _theme.LITERAL_STYLES <= theme_fields
    assert _theme.REPLACEABLE_STYLES <= theme_fields
    assert _theme.LITERAL_STYLES.isdisjoint(_theme.REPLACEABLE_STYLES)

    assert "option" in _theme.LITERAL_STYLES
    assert "metavar" in _theme.REPLACEABLE_STYLES


# --- Built-in themes loaded from ``click_extra/themes.toml`` ----------------

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
    """Load ``themes.toml`` raw (without going through ``HelpTheme.from_dict``)."""
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
    """Every ``BUILTIN_THEMES`` entry is a :class:`HelpTheme` instance."""
    for name, theme in BUILTIN_THEMES.items():
        assert isinstance(theme, HelpTheme), (
            f"BUILTIN_THEMES[{name!r}] is {type(theme).__name__}, expected HelpTheme."
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
    """``HelpTheme.to_dict``/``from_dict`` round-trips every built-in theme."""
    theme = BUILTIN_THEMES[theme_name]
    rebuilt = HelpTheme.from_dict(theme.to_dict())
    assert rebuilt == theme


@pytest.mark.parametrize("theme_name", sorted(BUILTIN_THEMES))
def test_themes_toml_payload_matches_to_dict(theme_name):
    """The TOML payload for each theme equals what ``to_dict`` would emit."""
    parsed = _parsed_themes_toml()
    assert parsed[theme_name] == BUILTIN_THEMES[theme_name].to_dict()


def test_to_dict_omits_identity_slots():
    """Slots left at the ``identity`` default do not appear in ``to_dict`` output."""
    blank = HelpTheme()
    assert blank.to_dict() == {}


def test_to_dict_emits_cross_ref_highlight_only_when_overridden():
    """``cross_ref_highlight`` is emitted only when it differs from the default."""
    default = HelpTheme()
    assert "cross_ref_highlight" not in default.to_dict()

    flipped = HelpTheme(cross_ref_highlight=False)
    assert flipped.to_dict() == {"cross_ref_highlight": False}


def test_from_dict_rejects_unknown_keys():
    """Typos like ``optoin`` raise ``TypeError`` instead of being silently dropped."""
    with pytest.raises(TypeError, match="optoin"):
        HelpTheme.from_dict({"optoin": {"fg": "cyan"}})


# --- Cascade ----------------------------------------------------------------


def test_cascade_overrides_only_set_slots():
    """``cascade`` keeps base's slots wherever the overlay leaves them at default."""
    dark = BUILTIN_THEMES["dark"]
    overlay = HelpTheme.from_dict({"option": {"fg": "magenta"}})
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
    overlay = HelpTheme.from_dict({"option": {"fg": "magenta"}})
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
    """``cascade`` rejects anything that is not a :class:`HelpTheme`."""
    overlay = HelpTheme()
    with pytest.raises(TypeError, match="not a HelpTheme"):
        overlay.cascade(object())  # type: ignore[arg-type]


# --- ThemeChoice ------------------------------------------------------------


def test_themechoice_choices_track_global_registry():
    """Outside any context, ``choices`` reflects the module-level registry."""
    tc = ThemeChoice()
    assert set(tc.choices) == set(theme_registry)


def test_themechoice_choices_pick_up_context_overrides():
    """A theme stashed under ``THEME_OVERRIDES`` shows up in ``choices``."""

    @click.command
    def noop() -> None:
        pass

    tc = ThemeChoice()
    with click.Context(noop) as ctx:
        context.set(ctx, context.THEME_OVERRIDES, {"midnight": BUILTIN_THEMES["dark"]})
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


# --- Missing data file tolerance --------------------------------------------


class _MissingResource:
    """Stand-in for a Traversable whose ``themes.toml`` was dropped.

    Some packaging and distribution setups (Nuitka onefile without
    ``--include-package-data``, trimmed downstream rebuilds) omit the package
    data file, so ``read_text`` raises as if the file never shipped.
    """

    def joinpath(self, *args: str) -> _MissingResource:
        return self

    def read_text(self, *args: object, **kwargs: object) -> str:
        raise FileNotFoundError("simulated missing themes.toml")


def test_load_builtin_themes_tolerates_missing_file(caplog, monkeypatch):
    """A dropped themes.toml degrades to an empty mapping plus a warning."""
    monkeypatch.setattr(
        theme_mod.resources, "files", lambda package: _MissingResource()
    )

    with caplog.at_level(logging.WARNING, logger="click_extra"):
        result = theme_mod._load_builtin_themes()

    assert result == {}
    assert "themes.toml" in caplog.text
    assert "no-color theme" in caplog.text
    # The warning points users at the config-file fallback for custom themes.
    assert "[tool.<cli>.themes.<name>]" in caplog.text


def test_themechoice_inert_when_registry_empty(monkeypatch):
    """With no themes available, ThemeChoice ignores any value instead of failing.

    Mirrors the runtime state once themes.toml is dropped: an empty registry
    means even the built-in ``dark`` default cannot resolve, so ``convert``
    returns None rather than aborting the invocation.
    """
    monkeypatch.setattr(theme_mod, "theme_registry", {})
    choice = theme_mod.ThemeChoice()
    assert choice.convert("dark", None, None) is None
    assert choice.convert("light", None, None) is None


def test_cli_runs_with_empty_theme_registry(invoke, monkeypatch):
    """A CLI still runs when no themes are available (themes.toml dropped).

    The built-in --theme option defaults to ``dark``; with an empty registry
    that default must stay inert instead of crashing the whole command.
    """
    monkeypatch.setattr(theme_mod, "theme_registry", {})

    @command
    @option("--fruit", default="apple")
    def greet(fruit):
        echo(f"Picked {fruit}")

    result = invoke(greet, ["--fruit", "banana"])
    assert result.exit_code == 0
    assert result.output == "Picked banana\n"

    result = invoke(greet, ["--theme", "dark", "--fruit", "kiwi"])
    assert result.exit_code == 0
    assert result.output == "Picked kiwi\n"


# --- [tool.<cli>.themes.<name>] config integration --------------------------

DARK = BUILTIN_THEMES["dark"]


def _palette_cli(captured: dict):
    """Build a minimal CLI that records the active theme on invocation."""

    @click_extra.command
    def palette() -> None:
        ctx = click_extra.get_current_context()
        captured["theme"] = ctx.meta.get(context.THEME)
        captured["overrides"] = ctx.meta.get(context.THEME_OVERRIDES)

    return palette


# --- Sub-tree construction --------------------------------------------------


def test_themes_from_config_overrides_existing_theme():
    """Known theme names cascade on top of the matching built-in palette."""
    built = themes_from_config({"dark": {"option": {"fg": "magenta"}}})
    assert isinstance(built["dark"].option, Style)
    assert built["dark"].option.fg == "magenta"
    # All other slots are inherited from the built-in `dark` palette.
    assert built["dark"].heading == DARK.heading
    assert built["dark"].critical == DARK.critical


def test_themes_from_config_creates_standalone_theme():
    """Unknown theme names build a stand-alone theme with unset slots at default."""
    built = themes_from_config({"midnight": {"option": {"fg": "magenta"}}})
    assert isinstance(built["midnight"].option, Style)
    assert built["midnight"].option.fg == "magenta"
    # Slots not declared in the config stay at their identity default.
    assert built["midnight"].heading is not DARK.heading


def test_themes_from_config_does_not_mutate_global_registry():
    """``themes_from_config`` is pure: the module-level registry is untouched."""
    before = dict(theme_registry)
    themes_from_config({"midnight": {"option": {"fg": "magenta"}}})
    assert dict(theme_registry) == before


# --- Live registry view -----------------------------------------------------


def test_get_theme_registry_falls_back_to_global_without_ctx():
    """``get_theme_registry(None)`` returns a copy of the module-level registry."""
    snapshot = get_theme_registry()
    assert set(snapshot) == set(theme_registry)
    snapshot["leaked"] = DARK
    assert "leaked" not in theme_registry


# --- ConfigOption integration ----------------------------------------------


def test_config_loads_new_theme(invoke, create_config):
    """A ``[tool.<cli>.themes.<name>]`` table registers a new theme for the invocation."""
    captured: dict = {}
    cli = _palette_cli(captured)

    config_path = create_config(
        "palette.toml",
        dedent("""\
            [palette.themes.midnight]
            option = { fg = "blue", bold = true }
            heading = { fg = "magenta" }
            choice = { fg = "yellow" }
            """),
    )

    result = invoke(cli, "--config", str(config_path), "--theme", "midnight")
    assert result.exit_code == 0, result.stderr
    assert isinstance(captured["theme"], HelpTheme)
    option = captured["theme"].option
    assert isinstance(option, Style)
    assert option.fg == "blue"
    assert option.bold is True
    heading = captured["theme"].heading
    assert isinstance(heading, Style)
    assert heading.fg == "magenta"
    assert "midnight" in (captured["overrides"] or {})


def test_config_overrides_existing_theme_palette(invoke, create_config):
    """A ``[tool.<cli>.themes.dark]`` table cascades onto the built-in dark palette."""
    captured: dict = {}
    cli = _palette_cli(captured)

    config_path = create_config(
        "palette.toml",
        dedent("""\
            [palette.themes.dark]
            option = { fg = "bright_cyan" }
            """),
    )

    result = invoke(cli, "--config", str(config_path), "--theme", "dark")
    assert result.exit_code == 0, result.stderr
    # Overridden slot picks up the config value.
    assert captured["theme"].option.fg == "bright_cyan"
    # Untouched slots inherit from the built-in `dark` palette.
    assert captured["theme"].heading == DARK.heading
    assert captured["theme"].critical == DARK.critical


def test_config_theme_appears_in_help_metavar(invoke, create_config):
    """``--help`` lists config-defined themes alongside the built-ins."""
    captured: dict = {}
    cli = _palette_cli(captured)

    config_path = create_config(
        "palette.toml",
        dedent("""\
            [palette.themes.midnight]
            option = { fg = "blue" }
            """),
    )

    result = invoke(cli, "--config", str(config_path), "--help", color=False)
    assert result.exit_code == 0, result.stderr
    # The bracket-style metavar must include "midnight" in alphabetical order.
    assert (
        "[dark|dracula|light|manpage|midnight|monokai|nord|solarized_dark]"
        in result.stdout
    )


def test_config_theme_validation_error(invoke, create_config):
    """A malformed ``[tool.<cli>.themes.<name>]`` table is rejected with a rooted path."""
    captured: dict = {}
    cli = _palette_cli(captured)

    config_path = create_config(
        "palette.toml",
        dedent("""\
            [palette.themes.midnight]
            optoin = { fg = "blue" }
            """),
    )

    result = invoke(cli, "--config", str(config_path))
    assert result.exit_code == 1
    assert "midnight" in result.stderr
    assert "optoin" in result.stderr


def test_config_theme_does_not_leak_across_invocations(invoke, create_config):
    """Themes defined in invocation N are not visible in invocation N+1."""
    captured: dict = {}
    cli = _palette_cli(captured)

    config_path = create_config(
        "palette.toml",
        dedent("""\
            [palette.themes.midnight]
            option = { fg = "blue" }
            """),
    )

    result1 = invoke(cli, "--config", str(config_path), "--theme", "midnight")
    assert result1.exit_code == 0, result1.stderr
    assert captured["theme"].option.fg == "blue"

    # Second invocation without --config: the global registry never grew, so
    # "midnight" is unknown and the theme picker rejects it.
    captured.clear()
    result2 = invoke(cli, "--no-config", "--theme", "midnight")
    assert result2.exit_code == 2
    assert "midnight" in result2.stderr


def test_validate_config_catches_bad_theme(invoke, create_config):
    """``--validate-config`` surfaces the same ValidationError as the runtime path."""
    captured: dict = {}
    cli = _palette_cli(captured)

    config_path = create_config(
        "palette.toml",
        dedent("""\
            [palette.themes.midnight]
            option = "not a table"
            """),
    )

    result = invoke(cli, "--validate-config", str(config_path))
    assert result.exit_code != 0
    assert "midnight" in result.stderr
