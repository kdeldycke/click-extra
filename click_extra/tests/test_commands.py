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

"""Test defaults of our custom commands, as well as their customizations and attached options, and how they interact with each others."""

import re
from textwrap import dedent

import click
import pytest
from click import option as click_option
from cloup import option as cloup_option
from cloup import option_group

from ..commands import group, timer_option


@group(version="2021.10.08")
def default_group():
    click.echo("It works!")


@default_group.command()
def default_command():
    click.echo("Run command...")


help_screen = dedent(
    """\
    Usage: default-group [OPTIONS] COMMAND [ARGS]...

    Options:
      --time / --no-time        Measure and print elapsed execution time.  [default:
                                no-time]
      --color, --ansi / --no-color, --no-ansi
                                Strip out all colors and all ANSI codes from output.
                                [default: color]
      -C, --config CONFIG_PATH  Location of the configuration file.  [default:
                                (dynamic)]
      -v, --verbosity LEVEL     Either CRITICAL, ERROR, WARNING, INFO, DEBUG.
                                [default: INFO]
      --version                 Show the version and exit.  [default: False]
      -h, --help                Show this message and exit.  [default: False]

    Commands:
      default-command
    """
)


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


@pytest.mark.parametrize("param", (None, "-h", "--help"))
def test_group_help(invoke, param):
    result = invoke(default_group, param, color=False)
    assert result.exit_code == 0
    assert result.stdout == help_screen
    assert "It works!" not in result.stdout
    assert not result.stderr


# TODO: let subcommands inherits "-h" short parameter?
def test_subcommand_help(invoke):
    result = invoke(default_group, "default-command", "--help", color=False)
    assert result.exit_code == 0
    assert result.stdout == dedent(
        """\
        It works!
        Usage: default-group default-command [OPTIONS]

        Options:
          -h, --help  Show this message and exit.  [default: False]
        """
    )
    assert not result.stderr


@pytest.mark.parametrize(
    "params",
    ("--version", "blah", ("--verbosity", "DEBUG"), ("--config", "random.toml")),
)
def test_help_eagerness(invoke, params):
    # See: https://click.palletsprojects.com/en/8.0.x/advanced/#callback-evaluation-order
    result = invoke(default_group, "--help", params, color=False)
    assert result.exit_code == 0
    assert result.stdout == help_screen
    assert "It works!" not in result.stdout
    assert not result.stderr


def test_integrated_version_value(invoke):
    result = invoke(default_group, "--version", color=False)
    assert result.exit_code == 0
    assert re.fullmatch(
        r"default-group, version 2021.10.08\n{'.+'}\n",
        result.output,
    )
    assert not result.stderr


def test_standalone_timer_option(invoke):
    @click.command()
    @timer_option()
    def dummy_cli():
        click.echo("It works!")

    result = invoke(dummy_cli, "--time")
    assert result.exit_code == 0
    assert re.fullmatch(
        r"It works!\nExecution time: [0-9.]+ seconds.\n",
        result.output,
    )
    assert not result.stderr

    result = invoke(dummy_cli, "--no-time")
    assert result.exit_code == 0
    assert result.output == "It works!\n"
    assert not result.stderr


def test_integrated_timer_option(invoke):

    result = invoke(default_group, "--time", "default-command")
    assert result.exit_code == 0
    assert re.fullmatch(
        r"It works!\nRun command...\nExecution time: [0-9.]+ seconds.\n",
        result.output,
    )
    assert not result.stderr

    result = invoke(default_group, "--no-time", "default-command")
    assert result.exit_code == 0
    assert result.output == "It works!\nRun command...\n"
    assert not result.stderr


def test_option_group_integration(invoke):
    # Mix regular and grouped options
    @group()
    @option_group(
        "Group 1",
        click_option("-a", "--opt1"),
        cloup_option("-b", "--opt2"),
    )
    @click_option("-c", "--opt3")
    @cloup_option("-d", "--opt4")
    def default_group(opt1, opt2, opt3, opt4):
        click.echo("It works!")

    @default_group.command()
    def default_command():
        click.echo("Run command...")

    result = invoke(default_group, "--help", color=False)
    assert result.exit_code == 0
    assert result.stdout == dedent(
        """\
        Usage: default-group [OPTIONS] COMMAND [ARGS]...

        Group 1:
          -a, --opt1 TEXT
          -b, --opt2 TEXT

        Other options:
          -c, --opt3 TEXT
          -d, --opt4 TEXT
          --time / --no-time        Measure and print elapsed execution time.  [default:
                                    no-time]
          --color, --ansi / --no-color, --no-ansi
                                    Strip out all colors and all ANSI codes from output.
                                    [default: color]
          -C, --config CONFIG_PATH  Location of the configuration file.  [default:
                                    (dynamic)]
          -v, --verbosity LEVEL     Either CRITICAL, ERROR, WARNING, INFO, DEBUG.
                                    [default: INFO]
          --version                 Show the version and exit.  [default: False]
          -h, --help                Show this message and exit.  [default: False]

        Commands:
          default-command
        """
    )
    assert "It works!" not in result.stdout
    assert not result.stderr
