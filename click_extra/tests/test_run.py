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

"""Test all runner utilities as well as all the test and pytest helpers."""

from pathlib import Path

import click
from cloup import Style

from ..commands import command
from ..logging import logger
from ..platform import is_windows


def test_real_fs():
    """Check a simple test is not caught into the CLI runner fixture which is
    encapsulating all filesystem access into temporary directory structure."""
    assert str(Path(__file__)).startswith(str(Path.cwd()))


def test_temporary_fs(runner):
    """Check the CLI runner fixture properly encapsulated the filesystem in
    temporary directory."""
    assert not str(Path(__file__)).startswith(str(Path.cwd()))


def test_invoke_color_stripping(invoke):
    """On windows Click ends up deciding it is not running un an interactive terminal
    and forces the stripping of all colors.
    """

    @command()
    @click.pass_context
    def dummy_cli(ctx):
        click.echo(Style(fg="green")("It works!"))
        logger.warning("Is the logger colored?")
        print(click.style("print() bypass Click.", fg="blue"))
        click.echo(f"Context.color = {ctx.color!r}")

    def check_colored_rendering(result):
        assert result.exit_code == 0
        assert result.output.startswith(
            "\x1b[32mIt works!\x1b[0m\n\x1b[34mprint() bypass Click.\x1b[0m\n"
        )
        assert result.stderr == "\x1b[33mwarning: \x1b[0mIs the logger colored?\n"

    def check_uncolored_rendering(result):
        assert result.exit_code == 0
        assert result.output.startswith(
            "It works!\n\x1b[34mprint() bypass Click.\x1b[0m\n"
        )
        assert result.stderr == "warning: Is the logger colored?\n"

    # Test invoker color stripping.
    result = invoke(dummy_cli, color=False)
    check_uncolored_rendering(result)
    assert result.output.endswith("Context.color = None\n")

    # Test colours are preserved while invoking, but not on Windows where
    # Click applies striping.
    result = invoke(dummy_cli, color=True)
    if is_windows():
        check_uncolored_rendering(result)
    else:
        check_colored_rendering(result)
    assert result.output.endswith("Context.color = None\n")

    # Test colours are preserved while invoking, and forced to be rendered
    # on Windows.
    result = invoke(dummy_cli, color="forced")
    check_colored_rendering(result)
    assert result.output.endswith("Context.color = True\n")
