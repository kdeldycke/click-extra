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
import cloup
import pytest
from boltons.strutils import strip_ansi
from click import echo, secho, style
from cloup import HelpTheme, Style, command, option, option_group
from pytest_cases import fixture, parametrize

from ..colorize import (
    HelpExtraFormatter,
    HelpExtraTheme,
    color_option,
    highlight,
    theme,
    version_option,
)
from ..commands import extra_command, extra_group
from ..logging import LOG_LEVELS, logger, verbosity_option
from .conftest import (
    command_decorators,
    default_debug_colored_log,
    default_debug_uncolored_log,
    default_options_colored_help,
    skip_windows_colors,
)


def test_theme_definition():
    """Ensure we do not leave any property we would have inherited from cloup and
    logging primitives."""
    assert set(HelpTheme._fields).issubset(HelpExtraTheme._fields)

    log_levels = {l.lower() for l in LOG_LEVELS}
    assert log_levels.issubset(HelpExtraTheme._fields)
    assert log_levels.isdisjoint(HelpTheme._fields)


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
    @extra_group()
    @option_group(
        "Group 1",
        option("-a", "--o1"),
        option("-b", "--o2"),
    )
    @cloup.option_group(
        "Group 2",
        option("--o3"),
        option("--o4"),
    )
    @option("--test")
    def color_cli1(o1, o2, o3, o4, test):
        echo("It works!")

    @extra_command(params=None)
    def command1():
        echo("Run click-extra command #1...")

    @cloup.command()
    def command2():
        echo("Run cloup command #2...")

    @click.command
    def command3():
        echo("Run click command #3...")

    @command(deprecated=True)
    def command4():
        echo("Run click-extra command #4...")

    color_cli1.section("Subcommand group 1", command1, command2)
    color_cli1.section("Extra commands", command3, command4)

    help_screen = (
        r"\x1b\[94m\x1b\[1mUsage: \x1b\[0m\x1b\[97mcolor-cli1\x1b\[0m "
        r"\x1b\[90m\[OPTIONS\]\x1b\[0m \x1b\[90mCOMMAND \[ARGS\]...\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1mGroup 1:\x1b\[0m\n"
        r"  \x1b\[36m-a\x1b\[0m, \x1b\[36m--o1\x1b\[0m \x1b\[90mTEXT\x1b\[0m\n"
        r"  \x1b\[36m-b\x1b\[0m, \x1b\[36m--o2\x1b\[0m \x1b\[90mTEXT\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1mGroup 2:\x1b\[0m\n"
        r"  \x1b\[36m--o3\x1b\[0m \x1b\[90mTEXT\x1b\[0m\n"
        r"  \x1b\[36m--o4\x1b\[0m \x1b\[90mTEXT\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1mOther options:\x1b\[0m\n"
        r"  \x1b\[36m--test\x1b\[0m \x1b\[90mTEXT\x1b\[0m\n"
        rf"{default_options_colored_help}"
        r"\n"
        r"\x1b\[94m\x1b\[1mSubcommand group 1:\x1b\[0m\n"
        r"  \x1b\[36mcommand1\x1b\[0m\n"
        r"  \x1b\[36mcommand2\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1mExtra commands:\x1b\[0m\n"
        r"  \x1b\[36mcommand3\x1b\[0m\n"
        r"  \x1b\[36mcommand4\x1b\[0m  \x1b\[33m\(Deprecated\)\x1b\[0m\n"
    )

    result = invoke(color_cli1, "--help", color=True)
    assert result.exit_code == 0
    assert re.fullmatch(help_screen, result.output)
    assert not result.stderr

    result = invoke(color_cli1, "-h", color=True)
    assert result.exit_code == 0
    assert re.fullmatch(help_screen, result.output)
    assert not result.stderr

    # CLI main group is invoked before sub-command.
    result = invoke(color_cli1, "command1", "--help", color=True)
    assert result.exit_code == 0
    assert result.output == dedent(
        f"""\
        It works!
        \x1b[94m\x1b[1mUsage: \x1b[0m\x1b[97mcolor-cli1 command1\x1b[0m \x1b[90m[OPTIONS]\x1b[0m

        \x1b[94m\x1b[1mOptions:\x1b[0m
          \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m  Show this message and exit.
        """
    )
    assert not result.stderr

    # Standalone call to command: CLI main group is skipped.
    result = invoke(command1, "--help", color=True)
    assert result.exit_code == 0
    assert result.output == dedent(
        f"""\
        \x1b[94m\x1b[1mUsage: \x1b[0m\x1b[97mcommand1\x1b[0m \x1b[90m[OPTIONS]\x1b[0m

        \x1b[94m\x1b[1mOptions:\x1b[0m
          \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m  Show this message and exit.
        """
    )
    assert not result.stderr

    # Non-click-extra commands are not colorized nor have extra options.
    for cmd_id in ("command2", "command3"):
        result = invoke(color_cli1, cmd_id, "--help", color=True)
        assert result.exit_code == 0
        assert result.stdout == dedent(
            f"""\
            It works!
            Usage: color-cli1 {cmd_id} [OPTIONS]

            Options:
              -h, --help  Show this message and exit.
            """
        )
        assert not result.stderr


@skip_windows_colors
def test_standalone_version_option_with_env_info(invoke):
    @click.group
    @version_option(version="1.2.3.4", print_env_info=True)
    def color_cli2():
        echo("It works!")

    # Test default colouring.
    result = invoke(color_cli2, "--version", color=True)
    assert result.exit_code == 0

    regex_output = r"\x1b\[97mcolor-cli2\x1b\[0m, version \x1b\[32m1.2.3.4"
    # XXX Temporarily skip displaying environment details for Python >= 3.10 while we wait for
    # https://github.com/mahmoud/boltons/issues/294 to be released upstream.
    if sys.version_info[:2] < (3, 10):
        regex_output += r"\x1b\[0m\x1b\[90m\n{'.+'}"
    regex_output += r"\x1b\[0m\n"
    assert re.fullmatch(regex_output, result.output)

    assert not result.stderr


@pytest.mark.xfail(
    strict=False, reason="version_option always displays click-extra version. See #176."
)
@skip_windows_colors
@parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_standalone_version_option_without_env_info(invoke, cmd_decorator):
    @cmd_decorator
    @version_option(version="1.2.3.4", print_env_info=False)
    def color_cli3():
        echo("It works!")

    # Test default colouring.
    result = invoke(color_cli3, "--version", color=True)
    assert result.exit_code == 0
    assert (
        result.output == "\x1b[97mcolor-cli3\x1b[0m, version \x1b[32m1.2.3.4\x1b[0m\n"
    )
    assert not result.stderr


@skip_windows_colors
@pytest.mark.parametrize(
    "params", (None, "--help", "blah", ("--config", "random.toml"))
)
def test_integrated_version_option_precedence(invoke, params):
    @extra_group(version="1.2.3.4")
    def color_cli4():
        echo("It works!")

    result = invoke(color_cli4, "--version", params, color=True)
    assert result.exit_code == 0

    regex_output = r"\x1b\[97mcolor-cli4\x1b\[0m, version \x1b\[32m1.2.3.4"
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

    @click.command
    @verbosity_option()
    @color_option()
    def color_cli5():
        echo(Style(fg="yellow")("It works!"))
        echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")
        echo(style("Run command.", fg="magenta"))
        logger.warning("Processing...")
        print(style("print() bypass Click.", fg="blue"))
        secho("Done.", fg="green")

    result = invoke(color_cli5, param, "--verbosity", "DEBUG", color=True)
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

    @click.command
    @color_option()
    @version_option(version="2.1.9")
    def color_cli6():
        echo(Style(fg="yellow")("It works!"))

    result = invoke(color_cli6, "--no-color", "--version", "command1", color=True)
    assert result.exit_code == 0
    assert result.output == "color-cli6, version 2.1.9\n"
    assert not result.stderr

    result = invoke(color_cli6, "--version", "--no-color", "command1", color=True)
    assert result.exit_code == 0
    assert result.output == "\x1b[97mcolor-cli6\x1b[0m, version \x1b[32m2.1.9\x1b[0m\n"
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
    @click.command
    @color_option()
    def color_cli7():
        echo(Style(fg="yellow")("It works!"))

    result = invoke(color_cli7, param, color=True, env=env)
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
    @extra_group()
    def color_cli8():
        echo(Style(fg="yellow")("It works!"))
        echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")

    @color_cli8.command()
    def command1():
        echo(style("Run command #1.", fg="magenta"))
        logger.warning("Processing...")
        print(style("print() bypass Click.", fg="blue"))
        secho("Done.", fg="green")

    result = invoke(color_cli8, param, "--verbosity", "DEBUG", "command1", color=True)

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
