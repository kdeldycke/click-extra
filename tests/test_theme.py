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
    theme uses ``\\x1b[34m`` (regular blue). If the second invocation picks up
    the first's choice via process-wide state, it leaks the light palette and
    the assertion below fails.
    """
    runner = CliRunner()

    light_result = runner.invoke(greet, ["--theme", "light", "--help"], color=True)
    assert light_result.exit_code == 0
    assert "\x1b[34m\x1b[1m\x1b[4mUsage:" in light_result.output

    dark_result = runner.invoke(greet, ["--help"], color=True)
    assert dark_result.exit_code == 0
    assert "\x1b[94m\x1b[1m\x1b[4mUsage:" in dark_result.output


def test_theme_default_unchanged_after_invocation():
    """An invocation with ``--theme light`` must not mutate the module default."""
    original = _theme.default_theme
    runner = CliRunner()
    runner.invoke(greet, ["--theme", "light", "--help"], color=True)
    assert _theme.default_theme is original


def test_theme_meta_key_matches_registry():
    """:func:`get_current_theme` reads from the same key :class:`ThemeOption` writes."""
    assert context.THEME == "click_extra.theme.active"
