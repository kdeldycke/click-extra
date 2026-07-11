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
"""Tests for the command-tree rendering feature."""

from __future__ import annotations

import pytest

from click_extra import argument, command, group, unstyle
from click_extra.cli import demo
from click_extra.testing import CliRunner
from click_extra.theme import get_current_theme
from click_extra.tree import render_command_tree


@command
def forecast():
    """Report the forecast."""


@group
def observatory():
    """Weather observatory control center."""


@observatory.group(aliases=["st"])
def station():
    """Manage remote weather stations."""


@station.command()
def calibrate():
    """Recalibrate the sensors."""


@station.command(deprecated=True)
def reboot():
    """Power-cycle the station."""


@observatory.command()
@argument("city")
def report(city):
    """Print the forecast for a city."""


@observatory.command()
def status():
    """Report the current conditions."""


@observatory.command(hidden=True)
def diagnose():
    """Internal diagnostics."""


OBSERVATORY_TREE = (
    "observatory                     Weather observatory control center.\n"
    "├── help [COMMAND_PATH]...      Show help for a command.\n"
    "├── report CITY                 Print the forecast for a city.\n"
    "├── station (st)                Manage remote weather stations.\n"
    "│   ├── calibrate               Recalibrate the sensors.\n"
    "│   ├── help [COMMAND_PATH]...  Show help for a command.\n"
    "│   └── reboot                  (Deprecated) Power-cycle the station.\n"
    "└── status                      Report the current conditions."
)
"""Expected unstyled tree of the ``observatory`` fixture CLI.

Descriptions are column-aligned on the longest rail-plus-label row, hidden
commands are skipped, aliases are parenthesized, operand metavars follow the
command name and deprecated commands carry their marker. The ``help`` entries
are the implicit subcommand every click-extra group registers.
"""


@group
def harbor():
    """Harbor master control."""


@harbor.group()
def docks():
    """Manage the loading docks and their assignment to incoming cargo ships."""


@docks.command()
def assign():
    """Assign a dock."""


@harbor.command()
def tides():
    """Print the tide table for the next seven days, with high and low water."""


@pytest.fixture
def runner():
    return CliRunner()


# -- render_command_tree core ---------------------------------------------------


def test_render_tree_structure():
    assert unstyle(render_command_tree(observatory)) == OBSERVATORY_TREE


def test_render_tree_non_group():
    assert unstyle(render_command_tree(forecast)) == "forecast  Report the forecast."


def test_render_tree_hidden_skipped():
    assert "diagnose" not in render_command_tree(observatory)


def test_render_tree_prog_name_override():
    tree = unstyle(render_command_tree(observatory, prog_name="obs"))
    first_line = tree.splitlines()[0]
    assert first_line.startswith("obs ")
    assert first_line.endswith("Weather observatory control center.")


def test_render_tree_theme_styling():
    """Nodes reuse the same theme slots and styling as help screens."""
    theme = get_current_theme()
    tree = render_command_tree(observatory)
    assert tree.startswith(theme.invoked_command("observatory"))
    assert theme.subcommand("status") in tree
    assert theme.subcommand("calibrate") in tree
    assert theme.metavar("CITY") in tree
    # Aliases render through Cloup's canonical formatter, like help screens:
    # the word takes the alias slot, the punctuation the alias_secondary slot.
    assert (
        theme.alias_secondary("(") + theme.alias("st") + theme.alias_secondary(")")
    ) in tree


def test_render_tree_wraps_descriptions():
    """Long descriptions wrap in the aligned column, rail running through."""
    tree = unstyle(render_command_tree(harbor, width=60))
    lines = tree.splitlines()
    # 5 nodes (root, docks, assign, help, tides), plus wrapped continuations.
    assert len(lines) > 5
    # No line overflows the requested width.
    assert all(len(line) <= 60 for line in lines)
    # A wrapped line under a non-last node keeps the rail running through.
    assert any(line.startswith("│") and "── " not in line for line in lines)
    # A wrapped line under a node with children also carries the bar dropping
    # to its first child, so the child connector below stays attached.
    assert any(line.startswith("│   │") and "── " not in line for line in lines)
    # The last node's wrapped lines are rail-free indentation.
    assert lines[-1].startswith("    ")
    assert "── " not in lines[-1]


# -- TreeOption flag (self-introspection) ---------------------------------------


def test_tree_option_prints_and_exits(runner):
    result = runner.invoke(observatory, ["--tree"], color=False)
    assert result.exit_code == 0
    assert result.stdout == OBSERVATORY_TREE + "\n"
    assert not result.stderr


def test_tree_option_colored(runner):
    result = runner.invoke(observatory, ["--tree"], color=True)
    assert result.exit_code == 0
    assert "\x1b[" in result.stdout


def test_tree_option_accessible_ascii_rail(runner):
    """Accessibility mode degrades the box-drawing rail to pure ASCII."""
    result = runner.invoke(observatory, ["--accessible", "--tree"], color=False)
    assert result.exit_code == 0
    assert "├──" not in result.stdout
    assert "|-- station (st)" in result.stdout
    assert "`-- status" in result.stdout


def test_tree_option_in_help(runner):
    result = runner.invoke(observatory, ["--help"], color=False)
    assert result.exit_code == 0
    assert "--tree" in result.stdout
    assert "Show the tree of nested subcommands and exit." in result.stdout


# -- CLI surface (wrap --tree) ---------------------------------------------------


KITCHEN_SCRIPT = """
import click

@click.group()
def kitchen():
    "Manage recipes and ingredients."

@kitchen.group()
def pantry():
    "Inspect the pantry."

@pantry.command()
def restock():
    "Restock the shelves."

@kitchen.command()
def bake():
    "Bake a cake."

# Keep a single group at module level: the wrap module scanner refuses to pick
# between multiple group candidates.
del pantry
"""


@pytest.fixture
def kitchen_script(tmp_path):
    script = tmp_path / "kitchen.py"
    script.write_text(KITCHEN_SCRIPT)
    return str(script)


def test_wrap_tree_renders_tree(runner, kitchen_script):
    result = runner.invoke(demo, ["wrap", "--tree", kitchen_script], color=False)
    assert result.exit_code == 0
    # The root line is labeled with the script exactly as the user typed it.
    assert result.stdout.startswith(kitchen_script)
    assert "Manage recipes and ingredients." in result.stdout
    assert "├── bake" in result.stdout
    assert "└── pantry" in result.stdout
    assert "    └── restock" in result.stdout


def test_wrap_tree_drills_into_subcommand(runner, kitchen_script):
    """Extra arguments after SCRIPT re-root the tree at the nested subcommand."""
    result = runner.invoke(
        demo, ["wrap", "--tree", kitchen_script, "pantry"], color=False
    )
    assert result.exit_code == 0
    assert result.stdout.startswith(f"{kitchen_script} pantry")
    assert "└── restock" in result.stdout
    assert "bake" not in result.stdout


def test_wrap_tree_accessible_ascii_rail(runner, kitchen_script):
    """Accessibility mode carries over from the wrapping context."""
    result = runner.invoke(
        demo, ["--accessible", "wrap", "--tree", kitchen_script], color=False
    )
    assert result.exit_code == 0
    assert "├──" not in result.stdout
    assert "|-- bake" in result.stdout
    assert "`-- pantry" in result.stdout


@pytest.mark.parametrize("conflicting", ["--show-params", "--man", "--carapace"])
def test_wrap_tree_mutually_exclusive(runner, kitchen_script, conflicting):
    result = runner.invoke(
        demo, ["wrap", "--tree", conflicting, kitchen_script], color=False
    )
    assert result.exit_code != 0
    assert "--show-params, --man, --carapace and --tree are mutually exclusive." in (
        result.output
    )


def test_wrap_tree_unresolvable_target(runner):
    result = runner.invoke(demo, ["wrap", "--tree", "nonexistent_xyz_12345"])
    assert result.exit_code != 0
    assert "Cannot resolve" in result.output
