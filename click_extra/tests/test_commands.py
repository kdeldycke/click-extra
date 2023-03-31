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

"""Test defaults of our custom commands, as well as their customizations and attached
options, and how they interact with each others."""

from __future__ import annotations

import re
from textwrap import dedent

import click
import cloup
import pytest
from click import echo
from cloup import option, option_group
from pytest_cases import fixture, parametrize

from ..decorators import extra_command, extra_group, timer_option
from .conftest import (
    command_decorators,
    default_debug_uncolored_log,
    default_options_uncolored_help,
)


@fixture
def all_command_cli():
    """A CLI that used all variations and flavors of subcommands."""
    @extra_group(version="2021.10.08")
    def command_cli1():
        echo("It works!")

    @command_cli1.command()
    def default_subcommand():
        echo("Run default subcommand...")

    @extra_command
    def click_extra_subcommand():
        echo("Run click-extra subcommand...")

    @cloup.command()
    def cloup_subcommand():
        echo("Run cloup subcommand...")

    @click.command
    def click_subcommand():
        echo("Run click subcommand...")

    command_cli1.section(
        "Subcommand group",
        click_extra_subcommand,
        cloup_subcommand,
        click_subcommand,
    )

    return command_cli1


help_screen = (
    r"Usage: command-cli1 \[OPTIONS\] COMMAND \[ARGS\]...\n"
    r"\n"
    r"Options:\n"
    rf"{default_options_uncolored_help}"
    r"\n"
    r"Subcommand group:\n"
    r"  click-extra-subcommand\n"
    r"  cloup-subcommand\n"
    r"  click-subcommand\n"
    r"\n"
    r"Other commands:\n"
    r"  default-subcommand\n"
)


def test_unknown_option(invoke, all_command_cli):
    result = invoke(all_command_cli, "--blah")
    assert result.exit_code == 2
    assert not result.stdout
    assert "Error: No such option: --blah" in result.stderr


def test_unknown_command(invoke, all_command_cli):
    result = invoke(all_command_cli, "blah")
    assert result.exit_code == 2
    assert not result.stdout
    assert "Error: No such command 'blah'." in result.stderr


def test_required_command(invoke, all_command_cli):
    result = invoke(all_command_cli, "--verbosity", "DEBUG", color=False)
    assert result.exit_code == 2
    # In debug mode, the version is always printed.
    assert not result.stdout
    assert re.fullmatch(
        (
            rf"{default_debug_uncolored_log}"
            r"Usage: command-cli1 \[OPTIONS\] COMMAND \[ARGS\]...\n"
            r"\n"
            r"Error: Missing command.\n"
        ),
        result.stderr,
    )


@pytest.mark.parametrize("param", (None, "-h", "--help"))
def test_group_help(invoke, all_command_cli, param):
    result = invoke(all_command_cli, param, color=False)
    assert result.exit_code == 0
    assert re.fullmatch(help_screen, result.stdout)
    assert "It works!" not in result.stdout
    assert not result.stderr


@pytest.mark.parametrize(
    "params",
    ("--version", "blah", ("--verbosity", "DEBUG"), ("--config", "random.toml")),
)
def test_help_eagerness(invoke, all_command_cli, params):
    """
    See: https://click.palletsprojects.com/en/8.0.x/advanced/#callback-evaluation-order
    """
    result = invoke(all_command_cli, "--help", params, color=False)
    assert result.exit_code == 0
    assert re.fullmatch(help_screen, result.stdout)
    assert "It works!" not in result.stdout
    assert not result.stderr


# XXX default and click-extra should have the same results, i.e. includes extra options.
# @pytest.mark.parametrize("cmd_id", ("default", "click-extra"))
@pytest.mark.parametrize("cmd_id", ("click-extra",))
@pytest.mark.parametrize("param", ("-h", "--help"))
def test_click_extra_subcommand_help(invoke, all_command_cli, cmd_id, param):
    result = invoke(all_command_cli, f"{cmd_id}-subcommand", param, color=False)
    assert result.exit_code == 0
    assert re.fullmatch(
        (
            r"It works!\n"
            rf"Usage: command-cli1 {cmd_id}-subcommand \[OPTIONS\]\n"
            r"\n"
            r"Options:\n"
            rf"{default_options_uncolored_help}"
        ),
        result.stdout,
    )
    assert not result.stderr


@pytest.mark.parametrize("cmd_id", ("default", "cloup", "click"))
@pytest.mark.parametrize("param", ("-h", "--help"))
def test_subcommand_help(invoke, all_command_cli, cmd_id, param):
    result = invoke(all_command_cli, f"{cmd_id}-subcommand", param, color=False)
    assert result.exit_code == 0
    assert result.stdout == dedent(
        f"""\
            It works!
            Usage: command-cli1 {cmd_id}-subcommand [OPTIONS]

            Options:
              -h, --help  Show this message and exit.
            """
    )
    assert not result.stderr


@pytest.mark.parametrize("cmd_id", ("default", "click-extra", "cloup", "click"))
def test_subcommand_execution(invoke, all_command_cli, cmd_id):
    result = invoke(all_command_cli, f"{cmd_id}-subcommand", color=False)
    assert result.exit_code == 0
    assert result.stdout == dedent(
        f"""\
            It works!
            Run {cmd_id} subcommand...
            """
    )
    assert not result.stderr


def test_integrated_time_option(invoke, all_command_cli):
    result = invoke(all_command_cli, "--time", "default-subcommand")
    assert result.exit_code == 0
    assert re.fullmatch(
        r"It works!\nRun default subcommand...\nExecution time: [0-9.]+ seconds.\n",
        result.output,
    )
    assert not result.stderr


def test_integrated_notime_option(invoke, all_command_cli):
    result = invoke(all_command_cli, "--no-time", "default-subcommand")
    assert result.exit_code == 0
    assert result.output == "It works!\nRun default subcommand...\n"
    assert not result.stderr


def test_integrated_version_value(invoke, all_command_cli):
    result = invoke(all_command_cli, "--version", color=False)
    assert result.exit_code == 0

    regex_output = r"command-cli1, version 2021.10.08\n{'.+'}\n"
    assert re.fullmatch(regex_output, result.output)

    assert not result.stderr


@parametrize(
    "cmd_decorator",
    # Skip click extra's commands, as timer option is already part of the default.
    command_decorators(no_groups=True, no_extra=True),
)
@parametrize("option_decorator", (timer_option, timer_option()))
def test_standalone_timer_option(invoke, cmd_decorator, option_decorator):
    @cmd_decorator
    @option_decorator
    def standalone_timer():
        echo("It works!")

    result = invoke(standalone_timer, "--help")
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == dedent(
        """\
        Usage: standalone-timer [OPTIONS]

        Options:
          --time / --no-time  Measure and print elapsed execution time.
          --help              Show this message and exit.
        """
    )

    result = invoke(standalone_timer, "--time")
    assert result.exit_code == 0
    assert not result.stderr
    assert re.fullmatch(
        r"It works!\nExecution time: [0-9.]+ seconds.\n",
        result.output,
    )

    result = invoke(standalone_timer, "--no-time")
    assert result.exit_code == 0
    assert not result.stderr
    assert result.output == "It works!\n"


def test_no_option_leaks_between_subcommands(invoke):
    """As reported in https://github.com/kdeldycke/click-extra/issues/489."""
    @click.group
    def cli():
        echo("Run cli...")

    @extra_command
    @click.option("--one")
    def foo():
        echo("Run foo...")

    @extra_command(short_help="Bar subcommand.")
    @click.option("--two")
    def bar():
        echo("Run bar...")

    cli.add_command(foo)
    cli.add_command(bar)

    result = invoke(cli, "--help", color=False)
    assert result.exit_code == 0
    assert result.output == dedent(
        """\
        Usage: cli [OPTIONS] COMMAND [ARGS]...

        Options:
          --help  Show this message and exit.

        Commands:
          bar  Bar subcommand.
          foo
        """
    )
    assert not result.stderr

    result = invoke(cli, "foo", "--help", color=False)
    assert result.exit_code == 0
    assert re.fullmatch(
        (
            r"Run cli\.\.\.\n"
            r"Usage: cli foo \[OPTIONS\]\n"
            r"\n"
            r"Options:\n"
            r"  --one TEXT\n"
            rf"{default_options_uncolored_help}"
        ),
        result.stdout,
    )
    assert not result.stderr

    result = invoke(cli, "bar", "--help", color=False)
    assert result.exit_code == 0
    assert re.fullmatch(
        (
            r"Run cli\.\.\.\n"
            r"Usage: cli bar \[OPTIONS\]\n"
            r"\n"
            r"Options:\n"
            r"  --two TEXT\n"
            rf"{default_options_uncolored_help}"
        ),
        result.stdout,
    )
    assert not result.stderr


def test_option_group_integration(invoke):
    # Mix regular and grouped options
    @extra_group
    @option_group(
        "Group 1",
        click.option("-a", "--opt1"),
        option("-b", "--opt2"),
    )
    @click.option("-c", "--opt3")
    @option("-d", "--opt4")
    def command_cli2(opt1, opt2, opt3, opt4):
        echo("It works!")

    @command_cli2.command()
    def default_command():
        echo("Run command...")

    result = invoke(command_cli2, "--help", color=False)
    assert result.exit_code == 0
    assert re.fullmatch(
        (
            r"Usage: command-cli2 \[OPTIONS\] COMMAND \[ARGS\]...\n"
            r"\n"
            r"Group 1:\n"
            r"  -a, --opt1 TEXT\n"
            r"  -b, --opt2 TEXT\n"
            r"\n"
            r"Other options:\n"
            r"  -c, --opt3 TEXT\n"
            r"  -d, --opt4 TEXT\n"
            rf"{default_options_uncolored_help}"
            r"\n"
            r"Commands:\n"
            r"  default-command\n"
        ),
        result.stdout,
    )
    assert "It works!" not in result.stdout
    assert not result.stderr
