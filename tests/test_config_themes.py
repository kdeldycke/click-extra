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
"""End-to-end tests for ``[tool.<cli>.themes.<name>]`` config integration."""

from __future__ import annotations

from textwrap import dedent

import click_extra
from click_extra import Style, context
from click_extra.theme import (
    BUILTIN_THEMES,
    HelpExtraTheme,
    get_theme_registry,
    theme_registry,
    themes_from_config,
)

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
    assert isinstance(captured["theme"], HelpExtraTheme)
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
