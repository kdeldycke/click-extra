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

import re
import sys
from textwrap import dedent

import click
import pytest
from boltons.strutils import strip_ansi
from cloup import Style
from cloup import command as cloup_command
from cloup import option, option_group

from .. import __version__
from ..colorize import HelpExtraFormatter, color_option, theme, version_option
from ..commands import command, group
from ..logging import logger, verbosity_option
from .conftest import skip_windows_colors


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


@skip_windows_colors
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
    @option("--test")
    def mycli(opt1, opt2, opt3, opt4, test):
        click.echo("It works!")

    @command()
    def command1():
        click.echo("Run click-extra command #1...")

    @cloup_command()
    def command2():
        click.echo("Run cloup command #2...")

    @click.command()
    def command3():
        click.echo("Run click command #3...")

    @command()
    def command4():
        click.echo("Run click-extra command #4...")

    mycli.section("Subcommand group 1", command1, command2)
    mycli.section("Extra commands", command3, command4)

    default_options_help_screen = (
        r"  \x1b\[36m--time / --no-time\x1b\[0m        Measure and print elapsed execution time.  \[default:\x1b\[0m\n"
        r"                            no-time\]\x1b\[0m\n"
        r"  \x1b\[36m--color, \x1b\[36m--ansi\x1b\[0m / --no-color, --no-ansi\x1b\[0m\n"
        r"                            Strip out all colors and all ANSI codes from output.\x1b\[0m\n"
        r"                            \[default: color\]\x1b\[0m\n"
        r"  \x1b\[36m-C, \x1b\[36m--config\x1b\[0m \x1b\[90mCONFIG_PATH\x1b\[0m\x1b\[0m  Location of the configuration file. Supports both\x1b\[0m\n"
        r"                            local path and remote URL.  \[default:\x1b\[0m\n"
        r"(                            \S+\n)*"
        r"                            \S+config.{toml,yaml,yml,json}\]\x1b\[0m\n"
        r"  \x1b\[36m-v, \x1b\[36m--verbosity\x1b\[0m \x1b\[90mLEVEL\x1b\[0m\x1b\[0m     Either \x1b\[35mCRITICAL\x1b\[0m, \x1b\[35mERROR\x1b\[0m, \x1b\[35mWARNING\x1b\[0m, \x1b\[35mINFO\x1b\[0m, \x1b\[35mDEBUG\x1b\[0m.\x1b\[0m\n"
        r"                            \[default: \x1b\[35mINFO\x1b\[0m\]\x1b\[0m\n"
        r"  \x1b\[36m--version\x1b\[0m                 Show the version and exit.  \[default: False\]\x1b\[0m\n"
        r"  \x1b\[36m-h, \x1b\[36m--help\x1b\[0m\x1b\[0m                Show this message and exit.  \[default: False\]\x1b\[0m\n"
    )

    help_screen = (
        r"\x1b\[94m\x1b\[1m\x1b\[94m\x1b\[1mUsage\x1b\[0m: "
        r"\x1b\[0m\x1b\[97mmycli\x1b\[0m \[OPTIONS\] COMMAND \[ARGS\]...\n\n"
        r"\x1b\[94m\x1b\[1m\x1b\[94m\x1b\[1mGroup \x1b\[35m1\x1b\[0m\x1b\[0m:\x1b\[0m\n"
        r"  \x1b\[36m-a, \x1b\[36m--opt1\x1b\[0m TEXT\x1b\[0m\n"
        r"  \x1b\[36m-b, \x1b\[36m--opt2\x1b\[0m TEXT\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1m\x1b\[94m\x1b\[1mGroup \x1b\[35m2\x1b\[0m\x1b\[0m:\x1b\[0m\n"
        r"  \x1b\[36m--opt3 TEXT\x1b\[0m\n"
        r"  \x1b\[36m--opt4 TEXT\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1m\x1b\[94m\x1b\[1mOther options\x1b\[0m:\x1b\[0m\n"
        r"  \x1b\[36m--test TEXT\x1b\[0m\n"
        rf"{default_options_help_screen}"
        r"\n"
        r"\x1b\[94m\x1b\[1m\x1b\[94m\x1b\[1mSubcommand group \x1b\[35m1\x1b\[0m\x1b\[0m:\x1b\[0m\n"
        r"  \x1b\[36mcommand1\x1b\[0m\n"
        r"  \x1b\[36mcommand2\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1m\x1b\[94m\x1b\[1mExtra commands\x1b\[0m:\x1b\[0m\n"
        r"  \x1b\[36mcommand3\x1b\[0m\n"
        r"  \x1b\[36mcommand4\x1b\[0m\n"
    )

    result = invoke(mycli, "--help", color=True)
    assert result.exit_code == 0
    assert re.fullmatch(help_screen, result.output)
    assert not result.stderr

    result = invoke(mycli, "-h", color=True)
    assert result.exit_code == 0
    assert re.fullmatch(help_screen, result.output)
    assert not result.stderr

    # CLI main group is invoked before sub-command.
    result = invoke(mycli, "command1", "--help", color=True)
    assert result.exit_code == 0
    assert re.fullmatch(
        (
            r"It works!\n"
            r"\x1b\[94m\x1b\[1m\x1b\[94m\x1b\[1mUsage\x1b\[0m: \x1b\[0m\x1b\[97mmycli command1\x1b\[0m \[OPTIONS\]\n\n"
            r"\x1b\[94m\x1b\[1m\x1b\[94m\x1b\[1mOptions\x1b\[0m:\x1b\[0m\n"
            rf"{default_options_help_screen}"
        ),
        result.output,
    )
    assert not result.stderr

    # Standalone call to command: CLI main group is skipped.
    result = invoke(command1, "--help", color=True)
    assert result.exit_code == 0
    assert re.fullmatch(
        (
            r"\x1b\[94m\x1b\[1m\x1b\[94m\x1b\[1mUsage\x1b\[0m: \x1b\[0m\x1b\[97mcommand1\x1b\[0m \[OPTIONS\]\n\n"
            r"\x1b\[94m\x1b\[1m\x1b\[94m\x1b\[1mOptions\x1b\[0m:\x1b\[0m\n"
            rf"{default_options_help_screen}"
        ),
        result.output,
    )
    assert not result.stderr

    # Non-click-extra commands are not colorized nor have extra options.
    for cmd_id in ("command2", "command3"):
        result = invoke(mycli, cmd_id, "--help", color=True)
        assert result.exit_code == 0
        assert result.stdout == dedent(
            f"""\
            It works!
            Usage: mycli {cmd_id} [OPTIONS]

            Options:
              -h, --help  Show this message and exit.  [default: False]
            """
        )
        assert not result.stderr


@skip_windows_colors
def test_standalone_version_option_with_env_info(invoke):
    @click.group()
    @version_option(version="1.2.3.4", print_env_info=True)
    def dummy_cli():
        click.echo("It works!")

    # Test default colouring.
    result = invoke(dummy_cli, "--version", color=True)
    assert result.exit_code == 0

    regex_output = r"\x1b\[97mdummy-cli\x1b\[0m, version \x1b\[32m1.2.3.4"
    # XXX Temporarily skip displaying environment details for Python >= 3.10 while we wait for
    # https://github.com/mahmoud/boltons/issues/294 to be released upstream.
    if sys.version_info[:2] < (3, 10):
        regex_output += r"\x1b\[0m\x1b\[90m\n{'.+'}"
    regex_output += r"\x1b\[0m\n"
    assert re.fullmatch(regex_output, result.output)

    assert not result.stderr


@skip_windows_colors
def test_standalone_version_option_without_env_info(invoke):
    @click.group()
    @version_option(version="1.2.3.4", print_env_info=False)
    def dummy_cli():
        click.echo("It works!")

    # Test default colouring.
    result = invoke(dummy_cli, "--version", color=True)
    assert result.exit_code == 0
    assert result.output == "\x1b[97mdummy-cli\x1b[0m, version \x1b[32m1.2.3.4\x1b[0m\n"
    assert not result.stderr


@skip_windows_colors
@pytest.mark.parametrize(
    "params", (None, "--help", "blah", ("--config", "random.toml"))
)
def test_integrated_version_option_eagerness(invoke, params):
    @group(version="1.2.3.4")
    def dummy_cli():
        click.echo("It works!")

    result = invoke(dummy_cli, "--version", params, color=True)
    assert result.exit_code == 0

    regex_output = r"\x1b\[97mdummy-cli\x1b\[0m, version \x1b\[32m1.2.3.4"
    # XXX Temporarily skip displaying environment details for Python >= 3.10 while we wait for
    # https://github.com/mahmoud/boltons/issues/294 to be released upstream.
    if sys.version_info[:2] < (3, 10):
        regex_output += r"\x1b\[0m\x1b\[90m\n{'.+'}"
    regex_output += r"\x1b\[0m\n"
    assert re.fullmatch(regex_output, result.output)

    assert not result.stderr


@skip_windows_colors
@pytest.mark.parametrize(
    "param,expecting_colors",
    (
        ("--color", True),
        ("--no-color", False),
        ("--ansi", True),
        ("--no-ansi", False),
        (None, True),
    ),
)
def test_standalone_color_option(invoke, param, expecting_colors):
    """Check color option values, defaults and effects on all things colored,
    including verbosity option."""

    @click.command()
    @verbosity_option()
    @color_option()
    def dummy_cli():
        click.echo(Style(fg="yellow")("It works!"))
        click.echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")
        click.echo(click.style("Run command.", fg="magenta"))
        logger.warning("Processing...")
        print(click.style("print() bypass Click.", fg="blue"))
        click.secho("Done.", fg="green")

    result = invoke(dummy_cli, param, "--verbosity", "DEBUG", color=True)
    assert result.exit_code == 0

    if expecting_colors:
        assert result.output == (
            "\x1b[33mIt works!\x1b[0m\n"
            "\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m\n"
            "\x1b[35mRun command.\x1b[0m\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "\x1b[32mDone.\x1b[0m\n"
        )
        assert result.stderr == (
            "\x1b[34mdebug: \x1b[0mVerbosity set to DEBUG.\n"
            "\x1b[33mwarning: \x1b[0mProcessing...\n"
        )
    else:
        assert result.output == (
            "It works!\n"
            "Art\n"
            "Run command.\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "Done.\n"
        )
        assert result.stderr == (
            "debug: Verbosity set to DEBUG.\nwarning: Processing...\n"
        )


@skip_windows_colors
def test_color_option_eagerness(invoke):
    """--no-color has an effect on --version, if placed in the right order.

    Eager parameters are evaluated in the order as they were provided on the command
    line by the user as expleined in:
    https://click.palletsprojects.com/en/8.0.x/advanced/#callback-evaluation-order
    """

    @click.command()
    @color_option()
    @version_option(version="2.1.9")
    def dummy_cli():
        click.echo(Style(fg="yellow")("It works!"))

    result = invoke(dummy_cli, "--no-color", "--version", "command1", color=True)
    assert result.exit_code == 0
    assert result.output == "dummy-cli, version 2.1.9\n"
    assert not result.stderr

    result = invoke(dummy_cli, "--version", "--no-color", "command1", color=True)
    assert result.exit_code == 0
    assert result.output == "\x1b[97mdummy-cli\x1b[0m, version \x1b[32m2.1.9\x1b[0m\n"
    assert not result.stderr


@skip_windows_colors
@pytest.mark.parametrize(
    "param,expecting_colors",
    (
        ("--color", True),
        ("--no-color", False),
        ("--ansi", True),
        ("--no-ansi", False),
        (None, True),
    ),
)
def test_integrated_color_option(invoke, param, expecting_colors):
    @group()
    def dummy_cli():
        click.echo(Style(fg="yellow")("It works!"))
        click.echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")

    @dummy_cli.command()
    def command1():
        click.echo(click.style("Run command #1.", fg="magenta"))
        logger.warning("Processing...")
        print(click.style("print() bypass Click.", fg="blue"))
        click.secho("Done.", fg="green")

    result = invoke(dummy_cli, param, "--verbosity", "DEBUG", "command1", color=True)

    assert result.exit_code == 0
    if expecting_colors:
        assert result.output == (
            "\x1b[33mIt works!\x1b[0m\n"
            "\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m\n"
            "\x1b[35mRun command #1.\x1b[0m\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "\x1b[32mDone.\x1b[0m\n"
        )
        assert result.stderr == (
            "\x1b[34mdebug: \x1b[0mVerbosity set to DEBUG.\n"
            "\x1b[34mdebug: \x1b[0mSearch for configuration in default location...\n"
            "\x1b[34mdebug: \x1b[0mNo default configuration found.\n"
            "\x1b[34mdebug: \x1b[0mNo configuration provided.\n"
            "\x1b[33mwarning: \x1b[0mProcessing...\n"
        )

    else:
        assert result.output == (
            "It works!\n"
            "Art\n"
            "Run command #1.\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "Done.\n"
        )
        assert result.stderr == (
            "debug: Verbosity set to DEBUG.\n"
            "debug: Search for configuration in default location...\n"
            "debug: No default configuration found.\n"
            "debug: No configuration provided.\n"
            "warning: Processing...\n"
        )
