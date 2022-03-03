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
import sys
from textwrap import dedent

import click
import pytest
from click import option as click_option
from cloup import command as cloup_command
from cloup import option as cloup_option
from cloup import option_group

from ..commands import command as click_extra_command
from ..commands import group, timer_option


@group(version="2021.10.08")
def default_group():
    click.echo("It works!")


@default_group.command()
def default_subcommand():
    click.echo("Run default subcommand...")


@click_extra_command()
def click_extra_subcommand():
    click.echo("Run click-extra subcommand...")


@cloup_command()
def cloup_subcommand():
    click.echo("Run cloup subcommand...")


@click.command()
def click_subcommand():
    click.echo("Run click subcommand...")


default_group.section(
    "Subcommand group", click_extra_subcommand, cloup_subcommand, click_subcommand
)


default_options_help_screen = (
    r"  --time / --no-time        Measure and print elapsed execution time.  \[default:\n"
    r"                            no-time\]\n"
    r"  --color, --ansi / --no-color, --no-ansi\n"
    r"                            Strip out all colors and all ANSI codes from output.\n"
    r"                            \[default: color\]\n"
    r"  -C, --config CONFIG_PATH  Location of the configuration file. Supports both\n"
    r"                            local path and remote URL.  \[default:( \S+)?\n"
    r"(                            \S+\n)*"
    r"                            \S+config.{toml,yaml,yml,json}\]\n"
    r"  -v, --verbosity LEVEL     Either CRITICAL, ERROR, WARNING, INFO, DEBUG.\n"
    r"                            \[default: INFO\]\n"
    r"  --version                 Show the version and exit.  \[default: False\]\n"
    r"  -h, --help                Show this message and exit.  \[default: False\]\n"
)

help_screen = (
    r"Usage: default-group \[OPTIONS\] COMMAND \[ARGS\]...\n"
    r"\n"
    r"Options:\n"
    rf"{default_options_help_screen}"
    r"\n"
    r"Subcommand group:\n"
    r"  click-extra-subcommand\n"
    r"  cloup-subcommand\n"
    r"  click-subcommand\n"
    r"\n"
    r"Other commands:\n"
    r"  default-subcommand\n"
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
    assert re.fullmatch(help_screen, result.stdout)
    assert "It works!" not in result.stdout
    assert not result.stderr


@pytest.mark.parametrize(
    "params",
    ("--version", "blah", ("--verbosity", "DEBUG"), ("--config", "random.toml")),
)
def test_help_eagerness(invoke, params):
    # See: https://click.palletsprojects.com/en/8.0.x/advanced/#callback-evaluation-order
    result = invoke(default_group, "--help", params, color=False)
    assert result.exit_code == 0
    assert re.fullmatch(help_screen, result.stdout)
    assert "It works!" not in result.stdout
    assert not result.stderr


# XXX default and click-extra should have the same results, i.e. includes extra options.
# @pytest.mark.parametrize("cmd_id", ("default", "click-extra"))
@pytest.mark.parametrize("cmd_id", ("click-extra",))
@pytest.mark.parametrize("param", ("-h", "--help"))
def test_click_extra_subcommand_help(invoke, cmd_id, param):
    result = invoke(default_group, f"{cmd_id}-subcommand", param, color=False)
    assert result.exit_code == 0
    assert re.fullmatch(
        (
            r"It works!\n"
            rf"Usage: default-group {cmd_id}-subcommand \[OPTIONS\]\n"
            r"\n"
            r"Options:\n"
            rf"{default_options_help_screen}"
        ),
        result.stdout,
    )
    assert not result.stderr


@pytest.mark.parametrize("cmd_id", ("default", "cloup", "click"))
@pytest.mark.parametrize("param", ("-h", "--help"))
def test_subcommand_help(invoke, cmd_id, param):
    result = invoke(default_group, f"{cmd_id}-subcommand", param, color=False)
    assert result.exit_code == 0
    assert result.stdout == dedent(
        f"""\
        It works!
        Usage: default-group {cmd_id}-subcommand [OPTIONS]

        Options:
          -h, --help  Show this message and exit.  [default: False]
        """
    )
    assert not result.stderr


@pytest.mark.parametrize("cmd_id", ("default", "click-extra", "cloup", "click"))
def test_subcommand_execution(invoke, cmd_id):
    result = invoke(default_group, f"{cmd_id}-subcommand", color=False)
    assert result.exit_code == 0
    assert result.stdout == dedent(
        f"""\
        It works!
        Run {cmd_id} subcommand...
        """
    )
    assert not result.stderr


def test_integrated_version_value(invoke):
    result = invoke(default_group, "--version", color=False)
    assert result.exit_code == 0

    regex_output = r"default-group, version 2021.10.08\n"
    # XXX Temporarily skip displaying environment details for Python >= 3.10 while we wait for
    # https://github.com/mahmoud/boltons/issues/294 to be released upstream.
    if sys.version_info[:2] < (3, 10):
        regex_output += r"{'.+'}\n"
    assert re.fullmatch(regex_output, result.output)

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

    result = invoke(default_group, "--time", "default-subcommand")
    assert result.exit_code == 0
    assert re.fullmatch(
        r"It works!\nRun default subcommand...\nExecution time: [0-9.]+ seconds.\n",
        result.output,
    )
    assert not result.stderr

    result = invoke(default_group, "--no-time", "default-subcommand")
    assert result.exit_code == 0
    assert result.output == "It works!\nRun default subcommand...\n"
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
    assert re.fullmatch(
        (
            r"Usage: default-group \[OPTIONS\] COMMAND \[ARGS\]...\n"
            r"\n"
            r"Group 1:\n"
            r"  -a, --opt1 TEXT\n"
            r"  -b, --opt2 TEXT\n"
            r"\n"
            r"Other options:\n"
            r"  -c, --opt3 TEXT\n"
            r"  -d, --opt4 TEXT\n"
            r"  --time / --no-time        Measure and print elapsed execution time.  \[default:\n"
            r"                            no-time\]\n"
            r"  --color, --ansi / --no-color, --no-ansi\n"
            r"                            Strip out all colors and all ANSI codes from output.\n"
            r"                            \[default: color\]\n"
            r"  -C, --config CONFIG_PATH  Location of the configuration file. Supports both\n"
            r"                            local path and remote URL.  \[default:( \S+)?\n"
            r"(                            \S+\n)*"
            r"                            \S+config.{toml,yaml,yml,json}\]\n"
            r"  -v, --verbosity LEVEL     Either CRITICAL, ERROR, WARNING, INFO, DEBUG.\n"
            r"                            \[default: INFO\]\n"
            r"  --version                 Show the version and exit.  \[default: False\]\n"
            r"  -h, --help                Show this message and exit.  \[default: False\]\n"
            r"\n"
            r"Commands:\n"
            r"  default-command\n"
        ),
        result.stdout,
    )
    assert "It works!" not in result.stdout
    assert not result.stderr
