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

from ..commands import group
from ..logging import LOG_LEVELS


# Create a dummy Click CLI.
@group()
def mycli():
    click.echo("It works!")


@mycli.command()
def command1():
    click.echo("Run command #1...")


def test_unrecognized_verbosity(invoke):
    result = invoke(mycli, "--verbosity", "random")
    assert result.exit_code == 2
    assert not result.stdout
    assert "Error: Invalid value for '--verbosity' / '-v'" in result.stderr


@pytest.mark.parametrize("level", LOG_LEVELS.keys())
def test_verbosity(invoke, level):
    result = invoke(mycli, "--verbosity", level, "command1")
    assert result.exit_code == 0
    assert "It works!" in result.stdout
    if level == "DEBUG":
        assert "debug: " in result.stderr
    else:
        assert "debug: " not in result.stderr
