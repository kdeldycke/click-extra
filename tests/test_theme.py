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

from __future__ import annotations

import dataclasses

from click.testing import CliRunner

from click_extra import command, context, echo, option, theme as _theme


@command
@option("--name", default="world", help="Who to greet.")
def greet(name):
    """Greet a recipient."""
    echo(f"Hello, {name}!")


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
    a real :class:`HelpExtraTheme` field, the two roles must not overlap, and
    the representative slots must keep their expected role.
    """
    theme_fields = {f.name for f in dataclasses.fields(_theme.HelpExtraTheme)}

    assert _theme.LITERAL_STYLES <= theme_fields
    assert _theme.REPLACEABLE_STYLES <= theme_fields
    assert _theme.LITERAL_STYLES.isdisjoint(_theme.REPLACEABLE_STYLES)

    assert "option" in _theme.LITERAL_STYLES
    assert "metavar" in _theme.REPLACEABLE_STYLES
