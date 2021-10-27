# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

import click
import pytest

from ..commands import group, timer_option


@group()
def default_group():
    click.echo("It works!")


@default_group.command()
def default_command():
    click.echo("Run command...")


@pytest.mark.parametrize("param", (None, "-h", "--help"))
def test_group_help(invoke, param):
    result = invoke(default_group, param)
    assert result.exit_code == 0
    assert "Usage: " in result.stdout
    assert not result.stderr


# TODO: let subcommands inherits "-h" short parameter?
def test_subcommand_help(invoke):
    result = invoke(default_group, "default-command", "--help")
    assert result.exit_code == 0
    assert "Usage: " in result.stdout
    assert not result.stderr


def test_unknown_option(invoke):
    result = invoke(default_group, "--blah")
    assert result.exit_code == 2
    assert not result.stdout
    assert "Error: No such option: --blah" in result.stderr


def test_unknown_command(invoke):
    result = invoke(default_group, "blah")
    assert result.exit_code == 2
    assert not result.stdout
    assert "Error: No such command 'blah'." in result.stderr


def test_required_command(invoke):
    result = invoke(default_group, "--verbosity", "DEBUG")
    assert result.exit_code == 2
    assert not result.stdout
    assert "Error: Missing command." in result.stderr


def test_standalone_timer_option(invoke):
    @click.command()
    @timer_option()
    def dummy_cli():
        click.echo("It works!")

    result = invoke(dummy_cli, "--time")
    assert result.exit_code == 0
    assert result.output.startswith("It works!\nExecution time: ")
    assert result.output.endswith(" seconds.\n")
    assert not result.stderr

    result = invoke(dummy_cli, "--no-time")
    assert result.exit_code == 0
    assert result.output == "It works!\n"
    assert not result.stderr


def test_integrated_timer_option(invoke):

    result = invoke(default_group, "--time", "default-command")
    assert result.exit_code == 0
    assert result.output.startswith("It works!\nRun command...\nExecution time: ")
    assert result.output.endswith(" seconds.\n")
    assert not result.stderr

    result = invoke(default_group, "--no-time", "default-command")
    assert result.exit_code == 0
    assert result.output == "It works!\nRun command...\n"
    assert not result.stderr
