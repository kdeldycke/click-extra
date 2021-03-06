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

"""Test defaults of our custom commands, as well as their customizations and attached
options, and how they interact with each others."""

import re
import sys
from textwrap import dedent

import click
import cloup
import pytest

from .. import (
    command,
    echo,
    extra_command,
    extra_group,
    option,
    option_group,
    timer_option,
)
from .conftest import default_options_uncolored_help


class TestSubcommands:
    @extra_group(version="2021.10.08")
    def cli_group():
        echo("It works!")

    @cli_group.command()
    def default_subcommand():
        echo("Run default subcommand...")

    @extra_command()
    def click_extra_subcommand():
        echo("Run click-extra subcommand...")

    @cloup.command()
    def cloup_subcommand():
        echo("Run cloup subcommand...")

    @click.command
    def click_subcommand():
        echo("Run click subcommand...")

    cli_group.section(
        "Subcommand group",
        click_extra_subcommand,
        cloup_subcommand,
        click_subcommand,
    )

    help_screen = (
        r"Usage: cli-group \[OPTIONS\] COMMAND \[ARGS\]...\n"
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

    def test_unknown_option(self, invoke):
        result = invoke(self.cli_group, "--blah")
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: No such option: --blah" in result.stderr

    def test_unknown_command(self, invoke):
        result = invoke(self.cli_group, "blah")
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: No such command 'blah'." in result.stderr

    def test_required_command(self, invoke):
        result = invoke(self.cli_group, "--verbosity", "DEBUG", color=False)
        assert result.exit_code == 2
        # In debug mode, the version is always printed.
        assert not result.stdout

        # XXX Temporarily skip displaying environment details for Python >= 3.10 while we wait for
        # https://github.com/mahmoud/boltons/issues/294 to be released upstream.
        system_details_regex = ""
        if sys.version_info[:2] < (3, 10):
            system_details_regex = r"debug: {'.+'}\n"
        assert re.fullmatch(
            (
                r"debug: Verbosity set to DEBUG.\n"
                r"debug: Search for configuration in default location...\n"
                r"debug: No default configuration found.\n"
                r"debug: No configuration provided.\n"
                r"debug: cli-group, version 2021.10.08\n"
                rf"{system_details_regex}"
                r"Usage: cli-group \[OPTIONS\] COMMAND \[ARGS\]...\n"
                r"\n"
                r"Error: Missing command.\n"
            ),
            result.stderr,
        )

    @pytest.mark.parametrize("param", (None, "-h", "--help"))
    def test_group_help(self, invoke, param):
        result = invoke(self.cli_group, param, color=False)
        assert result.exit_code == 0
        assert re.fullmatch(self.help_screen, result.stdout)
        assert "It works!" not in result.stdout
        assert not result.stderr

    @pytest.mark.parametrize(
        "params",
        ("--version", "blah", ("--verbosity", "DEBUG"), ("--config", "random.toml")),
    )
    def test_help_eagerness(self, invoke, params):
        """
        See: https://click.palletsprojects.com/en/8.0.x/advanced/#callback-evaluation-order
        """
        result = invoke(self.cli_group, "--help", params, color=False)
        assert result.exit_code == 0
        assert re.fullmatch(self.help_screen, result.stdout)
        assert "It works!" not in result.stdout
        assert not result.stderr

    # XXX default and click-extra should have the same results, i.e. includes extra options.
    # @pytest.mark.parametrize("cmd_id", ("default", "click-extra"))
    @pytest.mark.parametrize("cmd_id", ("click-extra",))
    @pytest.mark.parametrize("param", ("-h", "--help"))
    def test_click_extra_subcommand_help(self, invoke, cmd_id, param):
        result = invoke(self.cli_group, f"{cmd_id}-subcommand", param, color=False)
        assert result.exit_code == 0
        assert re.fullmatch(
            (
                r"It works!\n"
                rf"Usage: cli-group {cmd_id}-subcommand \[OPTIONS\]\n"
                r"\n"
                r"Options:\n"
                rf"{default_options_uncolored_help}"
            ),
            result.stdout,
        )
        assert not result.stderr

    @pytest.mark.parametrize("cmd_id", ("default", "cloup", "click"))
    @pytest.mark.parametrize("param", ("-h", "--help"))
    def test_subcommand_help(self, invoke, cmd_id, param):
        result = invoke(self.cli_group, f"{cmd_id}-subcommand", param, color=False)
        assert result.exit_code == 0
        assert result.stdout == dedent(
            f"""\
            It works!
            Usage: cli-group {cmd_id}-subcommand [OPTIONS]

            Options:
              -h, --help  Show this message and exit.
            """
        )
        assert not result.stderr

    @pytest.mark.parametrize("cmd_id", ("default", "click-extra", "cloup", "click"))
    def test_subcommand_execution(self, invoke, cmd_id):
        result = invoke(self.cli_group, f"{cmd_id}-subcommand", color=False)
        assert result.exit_code == 0
        assert result.stdout == dedent(
            f"""\
            It works!
            Run {cmd_id} subcommand...
            """
        )
        assert not result.stderr

    def test_integrated_time_option(self, invoke):
        result = invoke(self.cli_group, "--time", "default-subcommand")
        assert result.exit_code == 0
        assert re.fullmatch(
            r"It works!\nRun default subcommand...\nExecution time: [0-9.]+ seconds.\n",
            result.output,
        )
        assert not result.stderr

    def test_integrated_notime_option(self, invoke):
        result = invoke(self.cli_group, "--no-time", "default-subcommand")
        assert result.exit_code == 0
        assert result.output == "It works!\nRun default subcommand...\n"
        assert not result.stderr

    def test_integrated_version_value(self, invoke):
        result = invoke(self.cli_group, "--version", color=False)
        assert result.exit_code == 0

        regex_output = r"cli-group, version 2021.10.08\n"
        # XXX Temporarily skip displaying environment details for Python >= 3.10 while we wait for
        # https://github.com/mahmoud/boltons/issues/294 to be released upstream.
        if sys.version_info[:2] < (3, 10):
            regex_output += r"{'.+'}\n"
        assert re.fullmatch(regex_output, result.output)

        assert not result.stderr


def test_standalone_time_option(invoke):
    @command()
    @timer_option()
    def standalone_time():
        echo("It works!")

    result = invoke(standalone_time, "--help")
    assert result.exit_code == 0
    assert result.stdout == dedent(
        f"""\
        Usage: standalone-time [OPTIONS]

        Options:
          --time / --no-time  Measure and print elapsed execution time.
          --help              Show this message and exit.
        """
    )
    assert not result.stderr

    result = invoke(standalone_time, "--time")
    assert result.exit_code == 0
    assert re.fullmatch(
        r"It works!\nExecution time: [0-9.]+ seconds.\n",
        result.output,
    )
    assert not result.stderr

    result = invoke(standalone_time, "--no-time")
    assert result.exit_code == 0
    assert result.output == "It works!\n"
    assert not result.stderr


def test_option_group_integration(invoke):
    # Mix regular and grouped options
    @extra_group()
    @option_group(
        "Group 1",
        click.option("-a", "--opt1"),
        option("-b", "--opt2"),
    )
    @click.option("-c", "--opt3")
    @option("-d", "--opt4")
    def default_group(opt1, opt2, opt3, opt4):
        echo("It works!")

    @default_group.command()
    def default_command():
        echo("Run command...")

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
            rf"{default_options_uncolored_help}"
            r"\n"
            r"Commands:\n"
            r"  default-command\n"
        ),
        result.stdout,
    )
    assert "It works!" not in result.stdout
    assert not result.stderr
