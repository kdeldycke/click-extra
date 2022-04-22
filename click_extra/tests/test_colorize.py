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

from .. import __version__, command, echo, group, option, option_group
from ..colorize import (
    HelpExtraFormatter,
    color_option,
    highlight,
    theme,
    version_option,
)
from ..logging import logger, verbosity_option
from .conftest import (
    default_debug_colored_log,
    default_debug_uncolored_log,
    default_options_colored_help,
    skip_windows_colors,
)


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
        echo("It works!")

    @command()
    def command1():
        echo("Run click-extra command #1...")

    @cloup_command()
    def command2():
        echo("Run cloup command #2...")

    @click.command()
    def command3():
        echo("Run click command #3...")

    @command()
    def command4():
        echo("Run click-extra command #4...")

    mycli.section("Subcommand group 1", command1, command2)
    mycli.section("Extra commands", command3, command4)

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
        rf"{default_options_colored_help}"
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
            rf"{default_options_colored_help}"
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
            rf"{default_options_colored_help}"
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
              -h, --help  Show this message and exit.
            """
        )
        assert not result.stderr


@skip_windows_colors
def test_standalone_version_option_with_env_info(invoke):
    @click.group()
    @version_option(version="1.2.3.4", print_env_info=True)
    def dummy_cli():
        echo("It works!")

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
        echo("It works!")

    # Test default colouring.
    result = invoke(dummy_cli, "--version", color=True)
    assert result.exit_code == 0
    assert result.output == "\x1b[97mdummy-cli\x1b[0m, version \x1b[32m1.2.3.4\x1b[0m\n"
    assert not result.stderr


@skip_windows_colors
@pytest.mark.parametrize(
    "params", (None, "--help", "blah", ("--config", "random.toml"))
)
def test_integrated_version_option_precedence(invoke, params):
    @group(version="1.2.3.4")
    def dummy_cli():
        echo("It works!")

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
    """Check color option values, defaults and effects on all things colored, including
    verbosity option."""

    @click.command()
    @verbosity_option()
    @color_option()
    def dummy_cli():
        echo(Style(fg="yellow")("It works!"))
        echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")
        echo(click.style("Run command.", fg="magenta"))
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
def test_color_option_precedence(invoke):
    """--no-color has an effect on --version, if placed in the right order.

    Eager parameters are evaluated in the order as they were provided on the command
    line by the user as expleined in:
    https://click.palletsprojects.com/en/8.0.x/advanced/#callback-evaluation-order

    ..todo:

        Maybe have the possibility to tweak CLI callback evaluation order so we can
        let the user to have the NO_COLOR env set to allow for color-less --version output.
    """

    @click.command()
    @color_option()
    @version_option(version="2.1.9")
    def dummy_cli():
        echo(Style(fg="yellow")("It works!"))

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
    "env,env_expect_colors",
    (
        ({"COLOR": "true"}, True),
        ({"COLOR": ""}, True),
        ({"COLOR": "false"}, False),
        ({"NO_COLOR": "true"}, False),
        ({"NO_COLOR": ""}, False),
        ({"NO_COLOR": "false"}, True),
        (None, True),
    ),
)
@pytest.mark.parametrize(
    "param,param_expect_colors",
    (
        ("--color", True),
        ("--no-color", False),
        ("--ansi", True),
        ("--no-ansi", False),
        (None, True),
    ),
)
def test_no_color_env_convention(
    invoke, env, env_expect_colors, param, param_expect_colors
):
    @click.command()
    @color_option()
    def dummy_cli():
        echo(Style(fg="yellow")("It works!"))

    result = invoke(dummy_cli, param, color=True, env=env)
    assert result.exit_code == 0
    assert not result.stderr

    # Params always overrides env's expectations.
    expecting_colors = env_expect_colors
    if param:
        expecting_colors = param_expect_colors

    if expecting_colors:
        assert result.output == "\x1b[33mIt works!\x1b[0m\n"
    else:
        assert result.output == "It works!\n"


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
        echo(Style(fg="yellow")("It works!"))
        echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")

    @dummy_cli.command()
    def command1():
        echo(click.style("Run command #1.", fg="magenta"))
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
        assert re.fullmatch(
            (
                rf"{default_debug_colored_log}"
                r"\x1b\[33mwarning: \x1b\[0mProcessing...\n"
            ),
            result.stderr,
        )

    else:
        assert result.output == (
            "It works!\n"
            "Art\n"
            "Run command #1.\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "Done.\n"
        )
        assert re.fullmatch(
            (rf"{default_debug_uncolored_log}" r"warning: Processing...\n"),
            result.stderr,
        )


@pytest.mark.parametrize(
    "substrings,expected,ignore_case",
    (
        # Function input types.
        (["hey"], "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m", False),
        (("hey",), "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m", False),
        ({"hey"}, "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m", False),
        (
            "hey",
            "H\x1b[32mey\x1b[0m-xx-xxx-\x1b[32mhe\x1b[0mY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        # Duplicate substrings.
        (["hey", "hey"], "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m", False),
        (("hey", "hey"), "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m", False),
        ({"hey", "hey"}, "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m", False),
        (
            "heyhey",
            "H\x1b[32mey\x1b[0m-xx-xxx-\x1b[32mhe\x1b[0mY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        # Case-sensivity and multiple matches.
        (["hey"], "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m", False),
        (
            ["Hey"],
            "\x1b[32mHey\x1b[0m-xx-xxx-\x1b[32mheY\x1b[0m-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            True,
        ),
        (
            "x",
            "Hey-\x1b[32mxx\x1b[0m-\x1b[32mxxx\x1b[0m-heY-\x1b[32mx\x1b[0mX\x1b[32mx\x1b[0mX\x1b[32mxxxxx\x1b[0m-hey",
            False,
        ),
        (
            "x",
            "Hey-\x1b[32mxx\x1b[0m-\x1b[32mxxx\x1b[0m-heY-\x1b[32mxXxXxxxxx\x1b[0m-hey",
            True,
        ),
        # Overlaps.
        (
            ["xx"],
            "Hey-\x1b[32mxx\x1b[0m-\x1b[32mxxx\x1b[0m-heY-\x1b[32mxXxXxxxxx\x1b[0m-hey",
            True,
        ),
        (
            ["xx"],
            "Hey-\x1b[32mxx\x1b[0m-\x1b[32mxxx\x1b[0m-heY-xXxX\x1b[32mxxxxx\x1b[0m-hey",
            False,
        ),
        # No match.
        ("z", "Hey-xx-xxx-heY-xXxXxxxxx-hey", False),
        (["XX"], "Hey-xx-xxx-heY-xXxXxxxxx-hey", False),
    ),
)
def test_substring_highlighting(substrings, expected, ignore_case):
    result = highlight(
        "Hey-xx-xxx-heY-xXxXxxxxx-hey",
        substrings,
        styling_method=theme.success,
        ignore_case=ignore_case,
    )
    assert result == expected
