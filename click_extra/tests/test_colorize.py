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
from boltons.strutils import strip_ansi
from cloup import Style, option, option_group

from .. import __version__
from ..colorize import HelpExtraFormatter, nocolor_option, theme, version_option
from ..commands import command, group
from ..logging import logger


def test_options_highlight():
    formatter = HelpExtraFormatter()
    formatter.write("applies filtering by --manager and --exclude options")

    formatter.long_options = {"--manager", "--exclude"}

    output = formatter.getvalue()
    assert theme.option("--manager") in output
    assert theme.option("--exclude") in output


def test_choices_highlight():
    formatter = HelpExtraFormatter()
    formatter.write(
        """
        -e, --apt [apm|apt|apt-mint|brew]
                        Exclude a package manager.
                        Repeat to exclude multiple
                        managers.
        """
    )

    formatter.choices = {"apm", "apt", "apt-mint", "brew"}

    output = formatter.getvalue()
    assert theme.choice("apm") in output
    assert theme.choice("apt") in output
    assert theme.choice("apt-mint") in output
    assert theme.choice("brew") in output


def test_metavars_highlight():
    formatter = HelpExtraFormatter()
    formatter.write("-v, --verbosity LEVEL   Either CRITICAL, ERROR or DEBUG.")

    formatter.metavars = {"LEVEL"}

    output = formatter.getvalue()
    assert theme.metavar("LEVEL") in output


def test_only_full_word_highlight():
    formatter = HelpExtraFormatter()
    formatter.write("package snapshot")

    formatter.choices.add("snap")

    output = formatter.getvalue()
    # Make sure no highlighting occurred
    assert strip_ansi(output) == output


def test_keyword_collection(invoke):

    # Create a dummy Click CLI.
    @group()
    @option_group(
        "Group 1",
        option("-a", "--opt1"),
        option("-b", "--opt2"),
    )
    @option_group(
        "Group 2",
        option("--opt3"),
        option("--opt4"),
    )
    @option("--config")
    def mycli(opt1, opt2, opt3, opt4, config):
        click.echo("It works!")

    @command()
    def command1():
        click.echo("Run command #1...")

    @command()
    def command2():
        click.echo("Run command #2...")

    @command()
    def command3():
        click.echo("Run command #3...")

    @command()
    def command4():
        click.echo("Run command #4...")

    mycli.section("Subcommand group #1", command1, command2)
    mycli.section("Extra commands", command3, command4)

    help_screen = (
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mUsage\x1b[0m: "
        "\x1b[0m\x1b[97mmycli\x1b[0m [OPTIONS] COMMAND [ARGS]...\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mGroup \x1b[35m1\x1b[0m\x1b[0m:\x1b[0m\n"
        "  \x1b[36m-a, \x1b[36m--opt1\x1b[0m TEXT\x1b[0m\n"
        "  \x1b[36m-b, \x1b[36m--opt2\x1b[0m TEXT\x1b[0m\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mGroup \x1b[35m2\x1b[0m\x1b[0m:\x1b[0m\n"
        "  \x1b[36m--opt3 TEXT\x1b[0m\n"
        "  \x1b[36m--opt4 TEXT\x1b[0m\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mOther options\x1b[0m:\x1b[0m\n"
        "  \x1b[36m--config TEXT\x1b[0m\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mSubcommand group #1\x1b[0m:\x1b[0m\n"
        "  \x1b[36mcommand1\x1b[0m\n"
        "  \x1b[36mcommand2\x1b[0m\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mExtra commands\x1b[0m:\x1b[0m\n"
        "  \x1b[36mcommand3\x1b[0m\n"
        "  \x1b[36mcommand4\x1b[0m\n"
    )

    result = invoke(mycli, "--help", color=True)
    assert result.exit_code == 0
    assert result.output == help_screen
    assert not result.stderr

    result = invoke(mycli, "-h", color=True)
    assert result.exit_code == 0
    assert result.output == help_screen
    assert not result.stderr

    # CLI main group is invoked before sub-command.
    result = invoke(mycli, "command4", "--help", color=True)
    assert result.exit_code == 0
    assert result.output == (
        "It works!\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mUsage\x1b[0m: \x1b[0m\x1b[97mmycli command4\x1b[0m [OPTIONS]\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mOptions\x1b[0m:\x1b[0m\n"
        "  \x1b[36m--help\x1b[0m  Show this message and exit.  [default: False]\x1b[0m\n"
    )
    assert not result.stderr

    # Check CLI main group is skipped.
    result = invoke(command4, "--help", color=True)
    assert result.exit_code == 0
    assert result.output == (
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mUsage\x1b[0m: \x1b[0m\x1b[97mcommand4\x1b[0m [OPTIONS]\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mOptions\x1b[0m:\x1b[0m\n"
        "  \x1b[36m--help\x1b[0m  Show this message and exit.\x1b[0m\n"
    )
    assert not result.stderr


def test_standalone_version_option_with_env_info(invoke):
    @click.group()
    @version_option(version="1.2.3.4", print_env_info=True)
    def dummy_cli():
        click.echo("It works!")

    # Test default colouring.
    result = invoke(dummy_cli, "--version", color=True)
    assert result.exit_code == 0
    assert result.output.startswith(
        "\x1b[97mdummy-cli\x1b[0m, version \x1b[32m1.2.3.4\x1b[0m\x1b[90m\n{'"
    )
    assert result.output.endswith("'}\x1b[0m\n")
    assert not result.stderr


def test_standalone_version_option_no_env_info(invoke):
    @click.group()
    @version_option(version="1.2.3.4", print_env_info=False)
    def dummy_cli():
        click.echo("It works!")

    # Test default colouring.
    result = invoke(dummy_cli, "--version", color=True)
    assert result.exit_code == 0
    assert result.output == "\x1b[97mdummy-cli\x1b[0m, version \x1b[32m1.2.3.4\x1b[0m\n"
    assert not result.stderr


@pytest.mark.parametrize("param", ("--no-color", "--no-ansi", None))
def test_standalone_nocolor_option(invoke, param):
    @click.command()
    @nocolor_option()
    def dummy_cli():
        click.echo(Style(fg="yellow")("It works!"))
        click.echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")
        click.echo(click.style("Run command.", fg="magenta"))
        logger.warning("Processing...")
        click.secho("Done.", fg="green")

    result = invoke(dummy_cli, color=True)
    assert result.exit_code == 0

    # XXX Standalone nocolor option doesn't seems to be effective at stripping
    # colors yet. Use the integrated way as shown below.
    #
    # if not param:
    #     assert result.output == (
    #         "\x1b[33mIt works!\x1b[0m\n"
    #         "\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m\n"
    #         "\x1b[35mRun command.\x1b[0m\n"
    #         "\x1b[32mDone.\x1b[0m\n"
    #     )
    #     assert result.stderr == "\x1b[33mwarning: \x1b[0mProcessing...\n"
    # else:
    #     assert result.output == "It works!\nArt\nRun command.\nDone.\n"
    #     assert result.stderr == "warning: Processing...\n"


@pytest.mark.parametrize("param", ("--no-color", "--no-ansi", None))
def test_integrated_nocolor_option(invoke, param):
    @group()
    def dummy_cli():
        click.echo(Style(fg="yellow")("It works!"))
        click.echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")

    @dummy_cli.command()
    def command1():
        click.echo(click.style("Run command #1.", fg="magenta"))
        logger.warning("Processing...")
        click.secho("Done.", fg="green")

    # Test default colouring.
    result = invoke(dummy_cli, "--verbosity", "DEBUG", param, "command1", color=True)

    assert result.exit_code == 0
    if not param:
        assert result.output == (
            "\x1b[33mIt works!\x1b[0m\n"
            "\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m\n"
            "\x1b[35mRun command #1.\x1b[0m\n"
            "\x1b[32mDone.\x1b[0m\n"
        )
        assert result.stderr == (
            "\x1b[34mdebug: \x1b[0mVerbosity set to DEBUG.\n"
            "\x1b[33mwarning: \x1b[0mProcessing...\n"
        )
    else:
        assert result.output == "It works!\nArt\nRun command #1.\nDone.\n"
        assert result.stderr == (
            "debug: Verbosity set to DEBUG.\nwarning: Processing...\n"
        )
