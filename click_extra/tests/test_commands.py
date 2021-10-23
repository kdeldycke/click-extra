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
from boltons.strutils import strip_ansi
from cloup import option

from .. import __version__
from ..commands import command, group


# Create a dummy Click CLI.
@group()
@option("-a", "--opt1")
@option("-b", "--opt2")
@click.pass_context
def mycli(ctx, opt1, opt2):
    print("It works!")


@mycli.command()
@click.pass_context
def command1(ctx):
    print("Run command #1...")


@mycli.command()
@click.pass_context
def command2(ctx):
    print("Run command #2...")


def test_simple_call(invoke):
    result = invoke(mycli, "command2", color=True)
    assert "It works!" in result.output
    assert "Run command #1..." not in result.output
    assert "Run command #2..." in result.output


def test_timer(invoke):
    result = invoke(mycli, "--time", "command2", color=True)
    assert "It works!" in result.output
    assert "Run command #2..." in result.output
    assert "Execution time: " in result.output

    result = invoke(mycli, "--no-time", "command2", color=True)
    assert "It works!" in result.output
    assert "Run command #2..." in result.output
    assert "Execution time: " not in result.output
