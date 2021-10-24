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

from ..commands import group, timer_option


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
    @group()
    def dummy_cli():
        click.echo("It works!")

    @dummy_cli.command()
    def command1():
        click.echo("Run command #1...")

    result = invoke(dummy_cli, "--time", "command1")
    assert result.exit_code == 0
    assert result.output.startswith("It works!\nRun command #1...\nExecution time: ")
    assert result.output.endswith(" seconds.\n")
    assert not result.stderr

    result = invoke(dummy_cli, "--no-time", "command1")
    assert result.exit_code == 0
    assert result.output == "It works!\nRun command #1...\n"
    assert not result.stderr
