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
from cloup import option

from .. import __version__
from ..commands import group


# Create a dummy Click CLI.
@group()
@option("-a", "--opt1")
@option("-b", "--opt2")
@click.pass_context
def mycli(ctx, opt1, opt2):
    click.echo("It works!")


@mycli.command()
@click.pass_context
def command1(ctx):
    click.echo("Run command #1...")


@mycli.command()
@click.pass_context
def command2(ctx):
    click.echo("Run command #2...")


def test_simple_call(invoke):
    result = invoke(mycli, "command2")
    assert result.exit_code == 0
    assert "It works!" in result.output
    assert "Run command #1..." not in result.output
    assert "Run command #2..." in result.output
    assert not result.stderr


def test_timer(invoke):
    result = invoke(mycli, "--time", "command2")
    assert result.exit_code == 0
    assert result.output.startswith("It works!\nRun command #2...\nExecution time: ")
    assert result.output.endswith(" seconds.\n")
    assert not result.stderr

    result = invoke(mycli, "--no-time", "command2")
    assert result.exit_code == 0
    assert result.output == "It works!\nRun command #2...\n"
    assert not result.stderr
