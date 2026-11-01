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
"""Tests for ``click_extra.theme``: in-process isolation, built-in themes and
``[tool.<cli>.themes.<name>]`` config integration."""

from __future__ import annotations

import dataclasses
import re
import sys
from subprocess import run
from textwrap import dedent

import click
import cloup
import pytest
from click.testing import CliRunner
from cloup._util import identity

import click_extra
from click_extra import (
    Style,
    color,
    command,
    context,
    echo,
    option,
    theme as _theme,
    unstyle,
)
from click_extra.cli import demo
from click_extra.theme import (
    AUTO_THEME,
    BUILTIN_THEMES,
    LITERAL_STYLES,
    REPLACEABLE_STYLES,
    THEME_ENVVAR,
    HelpTheme,
    ThemeChoice,
    ThemeOption,
    get_theme_registry,
    resolve_auto_theme,
    theme_registry,
    themes_from_config,
    validate_themes_config,
)


@command
@option("--name", default="world", help="Who to greet.")
def greet(name):
    """Greet a recipient."""
    echo(f"Hello, {name}!")


# --- In-process isolation and font-role slots -------------------------------


def test_theme_does_not_leak_across_invocations():
    r"""A `--theme light` invocation must not bleed into a later `--help` render.

    Two back-to-back invocations of the same CLI in the same process:

    1. ``--theme light --help`` -- selects the light palette for this call only.
    2. ``--help`` -- no ``--theme`` argument, must fall back to the dark default.

    The dark theme renders headings with ``\x1b[94m`` (bright blue); the light
    theme uses ``\x1b[35m`` (magenta, chosen to stay distinct from its blue
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


def test_demo_themes_renders_each_builtin_palette():
    """`click-extra themes` renders the sample help once per built-in theme, each
    in its own palette.

    Guards against the whole gallery collapsing onto the default palette: the
    ``themes`` command drives ``get_current_theme`` through the context ``THEME``
    meta, so a regression there would render all seven screens identically.
    """
    result = CliRunner().invoke(demo, ["themes"], color=True)
    assert result.exit_code == 0
    # Every built-in theme is labeled in the gallery.
    for name in BUILTIN_THEMES:
        assert name in result.output
    # Multiple 24-bit palettes actually reach the help screens: were every theme
    # to fall back to the 16-color default, no truecolor codes would appear.
    truecolor = set(re.findall(r"\x1b\[38;2;\d+;\d+;\d+m", result.output))
    assert len(truecolor) >= 10


def test_demo_themes_renders_only_the_named_palettes():
    """Named theme IDs narrow the gallery down, and keep the order they were given."""
    result = CliRunner().invoke(demo, ["themes", "nord", "dracula"], color=True)
    assert result.exit_code == 0
    labels = re.findall(r"\[ Theme: (\S+) \]", unstyle(result.output))
    assert labels == ["nord", "dracula"]


def test_demo_themes_resolves_auto_to_a_palette_name():
    """`auto` is a directive, so the gallery labels the palette it lands on.

    Which palette that is depends on the background detected from the
    environment, so the expectation is read back from the same resolver rather
    than pinned to ``dark``.
    """
    result = CliRunner().invoke(demo, ["themes", "auto"], color=True)
    assert result.exit_code == 0
    labels = re.findall(r"\[ Theme: (\S+) \]", unstyle(result.output))
    resolved = resolve_auto_theme()
    assert labels == [
        name for name, palette in BUILTIN_THEMES.items() if palette is resolved
    ]
    assert labels


def test_demo_themes_rejects_an_unknown_palette():
    """An unknown ID fails, and the error lists every name that would have worked."""
    result = CliRunner().invoke(demo, ["themes", "banana"])
    assert result.exit_code != 0
    for name in BUILTIN_THEMES:
        assert name in result.output


def test_theme_meta_key_matches_registry():
    """:func:`~click_extra.theme.get_current_theme` reads from the same key
    :class:`~click_extra.theme.ThemeOption` writes.
    """
    assert context.THEME == "click_extra.theme.active"


def test_font_role_slots_are_known_and_disjoint():
    """``LITERAL_STYLES`` / ``REPLACEABLE_STYLES`` must classify real, distinct slots.

    The two frozensets encode the man-pages(7) bold/italic font roles by slot
    name and are maintained by hand, so guard against drift: every name must be
    a real :class:`~click_extra.theme.HelpTheme` field, the two roles must not
    overlap, and the representative slots must keep their expected role.
    """
    theme_fields = {f.name for f in dataclasses.fields(_theme.HelpTheme)}

    assert _theme.LITERAL_STYLES <= theme_fields
    assert _theme.REPLACEABLE_STYLES <= theme_fields
    assert _theme.LITERAL_STYLES.isdisjoint(_theme.REPLACEABLE_STYLES)

    assert "option" in _theme.LITERAL_STYLES
    assert "metavar" in _theme.REPLACEABLE_STYLES


# --- Built-in themes ---------------------------------------------------------

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
    "solarized-dark": "#002b36",
}

# Branded themes are 24-bit RGB and ship with deliberate palettes, so we
# can hold them to a real WCAG threshold. ANSI themes inherit terminal
# rendering and only get the legibility floor below.
_BRANDED_THEMES: tuple[str, ...] = (
    "dracula",
    "monokai",
    "nord",
    "solarized-dark",
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


# --- Source-of-truth checks -------------------------------------------------


def test_builtin_themes_alphabetical():
    """Built-in themes are declared alphabetically (matters for ``--theme`` choices)."""
    keys = list(BUILTIN_THEMES)
    assert keys == sorted(keys), (
        f"Built-in themes in click_extra/theme.py must be alphabetical. "
        f"Got: {keys}\nExpected: {sorted(keys)}"
    )


@pytest.mark.once
def test_builtin_themes_build_on_first_lookup():
    """Importing the package builds no theme, and a ``--help`` builds ``dark`` only.

    Reading the theme names, which ``--theme`` does to list its choices, builds
    nothing either. Checked in a pristine interpreter, since the other tests have
    built every theme already.
    """
    probe = dedent("""\
        from click_extra import command, theme

        assert not theme._built_themes, list(theme._built_themes)
        assert "nord" in theme.BUILTIN_THEMES
        assert "nord" in theme.theme_registry
        assert "nord" in theme.ThemeChoice().choices
        assert len(theme.get_theme_registry()) >= len(theme.BUILTIN_THEMES)
        assert not theme._built_themes, list(theme._built_themes)

        @command
        def hello():
            pass

        hello.main(["--help"], prog_name="hello", standalone_mode=False)
        assert list(theme._built_themes) == ["dark"], list(theme._built_themes)
        assert theme.get_default_theme() is theme.BUILTIN_THEMES["dark"]
        """)
    process = run(
        (sys.executable, "-c", probe), capture_output=True, text=True, check=False
    )
    assert process.returncode == 0, process.stderr


def test_builtin_themes_resolve_to_one_instance():
    """A built-in theme is the same instance in every mapping that holds it."""
    registry = get_theme_registry()
    for name, theme in BUILTIN_THEMES.items():
        assert theme_registry[name] is theme
        assert registry[name] is theme


def test_theme_registry_takes_dict_mutations(monkeypatch):
    """Registering, replacing and removing entries work on built-in names too."""
    registry = _theme._LazyThemes()
    monkeypatch.setattr(_theme, "theme_registry", registry)
    custom = HelpTheme.from_dict({"option": {"fg": "magenta"}})

    _theme.register_theme("midnight", custom)
    registry["nord"] = custom
    del registry["manpage"]

    builtins = [name for name in BUILTIN_THEMES if name != "manpage"]
    assert list(registry) == [*builtins, "midnight"]
    assert registry["midnight"] is custom
    assert registry["nord"] is custom
    assert registry["dark"] is BUILTIN_THEMES["dark"]
    assert "manpage" not in get_theme_registry()

    registry.clear()
    assert not registry
    assert len(BUILTIN_THEMES) == len(builtins) + 1


def test_builtin_themes_are_helptheme_instances():
    """Every ``BUILTIN_THEMES`` entry is a :class:`~click_extra.theme.HelpTheme`
    instance.
    """
    for name, theme in BUILTIN_THEMES.items():
        assert isinstance(theme, HelpTheme), (
            f"BUILTIN_THEMES[{name!r}] is {type(theme).__name__}, expected HelpTheme."
        )


@pytest.mark.parametrize("palette", ("dark", "light"))
def test_cloup_constructors_keep_the_subclass(palette):
    """``dark()`` and ``light()`` return a click-extra theme carrying cloup's palette.

    Cloup builds both palettes from ``cloup.Style``, which ``to_dict`` and
    ``cascade`` reject, so each style is widened to click-extra's.
    """
    theme = getattr(HelpTheme, palette)()
    assert type(theme) is HelpTheme

    # The slots this subclass adds are there, at their default.
    assert theme.metavar is identity

    # Cloup's palette is carried over, widened to click-extra's Style so the
    # theme stays serializable.
    cloup_theme = getattr(cloup.HelpTheme, palette)()
    for field in dataclasses.fields(cloup.HelpTheme):
        value = getattr(theme, field.name)
        assert value == getattr(cloup_theme, field.name)
        if isinstance(value, cloup.Style):
            assert isinstance(value, Style)
    assert theme.to_dict()


def test_with_rejects_unknown_slots():
    """Every argument naming no slot is listed, in a stable order."""
    with pytest.raises(
        TypeError, match=r"^Unknown HelpTheme field\(s\): optoin, xoption$"
    ):
        HelpTheme().with_(xoption=Style(), optoin=Style(), option=Style())


def test_with_takes_none_as_a_value():
    """``None`` resets a slot, where cloup's version reads it as no change."""
    theme = BUILTIN_THEMES["dark"]
    assert theme.alias_secondary is not None
    assert theme.with_(alias_secondary=None).alias_secondary is None


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
def test_builtin_theme_definition_matches_to_dict(theme_name):
    """Each built-in definition equals what ``to_dict`` emits for its theme.

    So a definition sets no slot to its default value, which ``to_dict`` leaves
    out.
    """
    definition = _theme._BUILTIN_THEME_DEFINITIONS[theme_name]
    assert definition == BUILTIN_THEMES[theme_name].to_dict()


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
    """``cascade`` rejects anything that is not a
    :class:`~click_extra.theme.HelpTheme`.
    """
    overlay = HelpTheme()
    with pytest.raises(TypeError, match="not a HelpTheme"):
        overlay.cascade(object())  # type: ignore[arg-type]


# --- ThemeChoice ------------------------------------------------------------


def test_themechoice_choices_track_global_registry():
    """Outside any context, ``choices`` reflects the module-level registry.

    Plus the reserved ``auto`` directive, which every CLI takes and no registry
    holds.
    """
    tc = ThemeChoice()
    assert set(tc.choices) == {AUTO_THEME, *theme_registry}


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
    (4.5+) is unattainable for some published themes (like Solarized's
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


# --- Empty registry tolerance -----------------------------------------------


def test_themechoice_inert_when_registry_empty(monkeypatch):
    """With no themes available, ThemeChoice ignores any value instead of failing.

    A program can empty the registry: then even the built-in ``dark`` default
    cannot resolve, so ``convert`` returns None rather than aborting the
    invocation.
    """
    monkeypatch.setattr(_theme, "theme_registry", {})
    choice = _theme.ThemeChoice()
    assert choice.convert("dark", None, None) is None
    assert choice.convert("light", None, None) is None


def test_cli_runs_with_empty_theme_registry(invoke, monkeypatch):
    """A CLI still runs when no themes are available.

    The built-in --theme option defaults to ``dark``; with an empty registry
    that default must stay inert instead of crashing the whole command.
    """
    monkeypatch.setattr(_theme, "theme_registry", {})

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
        "[auto|dark|dracula|light|manpage|midnight|monokai|nord|solarized-dark]"
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


@pytest.mark.parametrize(
    ("themes", "code"),
    (
        pytest.param({"midnight": "blue"}, "invalid_theme_shape", id="not-a-table"),
        pytest.param(
            {"midnight": {"optoin": {"fg": "blue"}}}, "invalid_theme", id="no-such-slot"
        ),
    ),
)
def test_validate_themes_config_codes(themes, code):
    """A malformed themes table is reported under a snake-case code, like every
    other configuration error."""
    with pytest.raises(click_extra.ValidationError) as excinfo:
        validate_themes_config(themes)
    assert excinfo.value.code == code
    assert excinfo.value.path == "midnight"


def test_command_validators_keep_the_theme_validator(invoke, create_config):
    """Validators a command declares join the built-in themes validator.

    `@command(config_validators=...)` forwards them to the default `--config`
    option, which keeps the built-in validator beside them: a malformed
    `[tool.<cli>.themes.<name>]` table is reported as a configuration validation
    error, not a `TypeError`.
    """

    def check_orchard(tree: dict) -> None:
        if "pear" not in tree:
            raise click_extra.ValidationError("pear", "missing fruit", code="no_pear")

    @click_extra.command(
        config_validators=(click_extra.ConfigValidator("orchard", check_orchard),),
    )
    def palette() -> None:
        pass

    # The built-in validator still catches a malformed themes table.
    config_path = create_config(
        "palette.toml",
        dedent("""\
            [palette.orchard]
            pear = "conference"

            [palette.themes.midnight]
            optoin = { fg = "blue" }
            """),
    )
    result = invoke(palette, "--config", str(config_path))
    assert result.exit_code == 1
    assert "Configuration validation error: palette.themes.midnight" in result.stderr
    assert "optoin" in result.stderr

    # The command's own validator checks its sub-tree.
    config_path = create_config(
        "orchard.toml",
        dedent("""\
            [palette.orchard]
            apple = "fuji"
            """),
    )
    result = invoke(palette, "--config", str(config_path))
    assert result.exit_code == 1
    assert (
        "Configuration validation error: palette.orchard.pear: missing fruit"
        in result.stderr
    )


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


# --- Background auto-detection ----------------------------------------------


@pytest.mark.parametrize(
    ("env", "expected_name"),
    (
        ({"COLORFGBG": "0;15"}, "light"),
        ({"COLORFGBG": "15;0"}, "dark"),
        ({"CLITHEME": "light"}, "light"),
        ({"CLITHEME": "dark"}, "dark"),
        # No detectable signal falls back to the dark default.
        ({}, "dark"),
    ),
)
def test_theme_auto_resolves_to_detected_palette(
    invoke, monkeypatch, env, expected_name
):
    """``--theme=auto`` picks the built-in palette implied by the terminal background."""
    for var in ("CLITHEME", "COLORFGBG"):
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    captured: dict = {}
    cli = _palette_cli(captured)

    result = invoke(cli, "--theme", "auto")
    assert result.exit_code == 0, result.stderr
    assert captured["theme"] is BUILTIN_THEMES[expected_name]


def test_theme_auto_from_config(invoke, create_config, monkeypatch):
    """``theme = "auto"`` in the config file makes detection the effective default."""
    for var in ("CLITHEME", "COLORFGBG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CLITHEME", "light")
    captured: dict = {}
    cli = _palette_cli(captured)

    config_path = create_config("palette.toml", '[palette]\ntheme = "auto"\n')
    result = invoke(cli, "--config", str(config_path))
    assert result.exit_code == 0, result.stderr
    assert captured["theme"] is BUILTIN_THEMES["light"]


def test_theme_auto_advertised_in_help_metavar(invoke):
    """The reserved 'auto' directive is listed among the values --theme takes.

    It resolves to a palette rather than being one, but it works on every Click
    Extra CLI, and a value named nowhere is a value nobody finds.
    """
    result = invoke(greet, "--help", color=False)
    assert result.exit_code == 0
    assert (
        "[auto|dark|dracula|light|manpage|monokai|nord|solarized-dark]" in result.stdout
    )


def test_themechoice_accepts_auto_directive():
    """'auto' converts to itself though it is not a registered palette."""
    assert ThemeChoice().convert("auto", None, None) == AUTO_THEME
    assert ThemeChoice().convert("AUTO", None, None) == AUTO_THEME
    assert "auto" in ThemeChoice().choices


def test_theme_option_query_background_opt_in():
    """The live OSC 11 query is off unless a CLI explicitly opts in."""
    assert ThemeOption().query_background is False
    assert ThemeOption(query_background=True).query_background is True


def test_resolve_auto_theme_forwards_query_flag(monkeypatch):
    """``query_background`` gates the live query that env-var detection ignores."""
    for var in ("CLITHEME", "COLORFGBG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(color, "query_osc_background", lambda: (255, 255, 255))

    # With the query allowed, the live light background wins.
    assert resolve_auto_theme(query_background=True) is BUILTIN_THEMES["light"]
    # Without it, no signal resolves and the dark fallback applies.
    assert resolve_auto_theme(query_background=False) is BUILTIN_THEMES["dark"]


# --- Machine-wide CLICK_EXTRA_THEME variable --------------------------------


@pytest.mark.parametrize(
    ("env_value", "expected_name"),
    (
        ("monokai", "monokai"),
        ("nord", "nord"),
        # Matched against the registry case-insensitively, like the flag.
        ("NORD", "nord"),
        ("Solarized-Dark", "solarized-dark"),
    ),
)
def test_theme_envvar_picks_palette(invoke, monkeypatch, env_value, expected_name):
    """``CLICK_EXTRA_THEME`` themes a CLI invoked without ``--theme``."""
    monkeypatch.setenv(THEME_ENVVAR, env_value)
    captured: dict = {}

    result = invoke(_palette_cli(captured))
    assert result.exit_code == 0, result.stderr
    assert captured["theme"] is BUILTIN_THEMES[expected_name]


def test_theme_envvar_accepts_auto_directive(invoke, monkeypatch):
    """The reserved 'auto' directive resolves from the variable too."""
    monkeypatch.delenv("CLITHEME", raising=False)
    monkeypatch.setenv(THEME_ENVVAR, AUTO_THEME)
    monkeypatch.setenv("COLORFGBG", "0;15")
    captured: dict = {}

    result = invoke(_palette_cli(captured))
    assert result.exit_code == 0, result.stderr
    assert captured["theme"] is BUILTIN_THEMES["light"]


def test_theme_flag_outranks_envvar(invoke, monkeypatch):
    """An explicit ``--theme`` beats the machine-wide variable."""
    monkeypatch.setenv(THEME_ENVVAR, "nord")
    captured: dict = {}

    result = invoke(_palette_cli(captured), "--theme", "light")
    assert result.exit_code == 0, result.stderr
    assert captured["theme"] is BUILTIN_THEMES["light"]


def test_cli_envvar_outranks_theme_envvar(invoke, monkeypatch):
    """The ``<CLI>_THEME`` variable is more specific than the machine-wide one."""
    monkeypatch.setenv(THEME_ENVVAR, "nord")
    monkeypatch.setenv("PALETTE_THEME", "monokai")
    captured: dict = {}

    result = invoke(_palette_cli(captured))
    assert result.exit_code == 0, result.stderr
    assert captured["theme"] is BUILTIN_THEMES["monokai"]


def test_config_outranks_theme_envvar(invoke, create_config, monkeypatch):
    """A palette pinned in the CLI's own config file is more specific."""
    monkeypatch.setenv(THEME_ENVVAR, "nord")
    captured: dict = {}
    cli = _palette_cli(captured)

    config_path = create_config("palette.toml", '[palette]\ntheme = "monokai"\n')
    result = invoke(cli, "--config", str(config_path))
    assert result.exit_code == 0, result.stderr
    assert captured["theme"] is BUILTIN_THEMES["monokai"]


def test_unknown_theme_envvar_warns_and_keeps_default(invoke, monkeypatch):
    """A typo in a shell profile must not break every Click Extra CLI at once."""
    monkeypatch.setenv(THEME_ENVVAR, "zenburn")
    captured: dict = {}

    result = invoke(_palette_cli(captured))
    assert result.exit_code == 0
    assert THEME_ENVVAR in result.stderr
    assert "zenburn" in result.stderr
    # The warning lists every value the variable takes, like the flag's error.
    assert (
        "[auto|dark|dracula|light|manpage|monokai|nord|solarized-dark]" in result.stderr
    )
    assert captured["theme"] is DARK


@pytest.mark.parametrize("envvar", (THEME_ENVVAR, "GREET_THEME"))
def test_theme_from_env_reaches_the_help_screen(invoke, monkeypatch, envvar):
    """A palette named by the environment paints the screen it exists to paint.

    Click processes a typed ``--help`` before an untyped ``--theme``, so the
    palette only reaches the help screen through the pre-pass in
    ``Command._resolve_presentation_eagerly``.
    """
    plain = invoke(greet, "--help", color=True)
    flagged = invoke(greet, "--theme", "nord", "--help", color=True)
    monkeypatch.setenv(envvar, "nord")
    from_env = invoke(greet, "--help", color=True)

    assert from_env.stdout == flagged.stdout
    assert from_env.stdout != plain.stdout


def test_theme_flag_after_help_still_paints_it(invoke):
    """``--help --theme nord`` renders under nord, like the reverse order.

    Both are typed, so Click sorts ``--help`` first and would render before the
    palette settles: the same pre-pass covers it.
    """
    before = invoke(greet, "--theme", "nord", "--help", color=True)
    after = invoke(greet, "--help", "--theme", "nord", color=True)

    assert after.stdout == before.stdout
