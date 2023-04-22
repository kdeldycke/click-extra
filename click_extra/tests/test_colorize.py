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

from __future__ import annotations

import re
from textwrap import dedent

import click
import cloup
import pytest
from boltons.strutils import strip_ansi
from pytest_cases import parametrize
import logging
from .. import HelpTheme, Style, argument, echo, option, option_group, secho, style
from ..colorize import (
    HelpExtraFormatter,
    HelpExtraTheme,
    default_theme,
    highlight,
)
from ..decorators import (
    color_option,
    command,
    extra_command,
    extra_group,
    help_option,
    verbosity_option,
)
from ..logging import LOG_LEVELS
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

    log_levels = {level.lower() for level in LOG_LEVELS}
    assert log_levels.issubset(HelpExtraTheme._fields)
    assert log_levels.isdisjoint(HelpTheme._fields)


def test_options_highlight():
    formatter = HelpExtraFormatter()
    formatter.write("applies filtering by --manager and --exclude options")

    formatter.long_options = {"--manager", "--exclude"}

    output = formatter.getvalue()
    assert default_theme.option("--manager") in output
    assert default_theme.option("--exclude") in output


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
    assert default_theme.choice("apm") in output
    assert default_theme.choice("apt") in output
    assert default_theme.choice("apt-mint") in output
    assert default_theme.choice("brew") in output


def test_metavars_highlight():
    formatter = HelpExtraFormatter()
    formatter.write("-v, --verbosity LEVEL   Either CRITICAL, ERROR or DEBUG.")

    formatter.metavars = {"LEVEL"}

    output = formatter.getvalue()
    assert default_theme.metavar("LEVEL") in output


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
    @extra_group
    @option_group(
        "Group 1",
        option("-a", "--o1"),
        option("-b", "--o2"),
    )
    @cloup.option_group(
        "Group 2",
        option("--o3", metavar="MY_VAR"),
        option("--o4"),
    )
    @option("--test")
    # Windows-style parameters.
    @option("--boolean/--no-boolean", "-b/+B", is_flag=True)
    @option("/debug;/no-debug")
    # First option without an alias.
    @option("--shout/--no-shout", " /-S", default=False)
    def color_cli1(o1, o2, o3, o4, test, boolean, debug, shout):
        echo("It works!")

    @extra_command(params=None)
    @argument("MY_ARG", nargs=-1, help="Argument supports help.")
    def command1(my_arg):
        """CLI description with extra MY_VAR reference."""
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
        r"  \x1b\[36m--o3\x1b\[0m \x1b\[90mMY_VAR\x1b\[0m\n"
        r"  \x1b\[36m--o4\x1b\[0m \x1b\[90mTEXT\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1mOther options:\x1b\[0m\n"
        r"  \x1b\[36m--test\x1b\[0m \x1b\[90mTEXT\x1b\[0m\n"
        r"  \x1b\[36m-b\x1b\[0m, \x1b\[36m--boolean\x1b\[0m / \x1b\[36m\+B\x1b\[0m,"
        r" \x1b\[36m--no-boolean\x1b\[0m\n"
        r"                            "
        r"\x1b\[90m\[default: \x1b\[0m\x1b\[35mno-boolean\x1b\[0m\x1b\[90m\]\x1b\[0m\n"
        r"  \x1b\[36m/debug\x1b\[0m; \x1b\[36m/no-debug\x1b\[0m"
        r"         \x1b\[90m\[default:"
        r" \x1b\[0m\x1b\[35mno-debug\x1b\[0m\x1b\[90m\]\x1b\[0m\n"
        r"  \x1b\[36m--shout\x1b\[0m / \x1b\[36m-S\x1b\[0m, \x1b\[36m--no-shout\x1b\[0m"
        r"  \x1b\[90m\[default: \x1b\[0m\x1b\[35mno-shout\x1b\[0m\x1b\[90m\]\x1b\[0m\n"
        rf"{default_options_colored_help}"
        r"\n"
        r"\x1b\[94m\x1b\[1mSubcommand group 1:\x1b\[0m\n"
        r"  \x1b\[36mcommand1\x1b\[0m  CLI description with extra"
        r" \x1b\[90mMY_VAR\x1b\[0m reference.\n"
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
    assert result.output == (
        "It works!\n"
        "\x1b[94m\x1b[1mUsage: \x1b[0m\x1b[97mcolor-cli1 command1\x1b[0m"
        " \x1b[90m[OPTIONS]\x1b[0m [\x1b[36mMY_ARG\x1b[0m]...\n"
        "\n"
        "  CLI description with extra MY_VAR reference.\n"
        "\n"
        "\x1b[94m\x1b[1mPositional arguments:\x1b[0m\n"
        "  [\x1b[36mMY_ARG\x1b[0m]...  Argument supports help.\n"
        "\n"
        "\x1b[94m\x1b[1mOptions:\x1b[0m\n"
        "  \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m  Show this message and exit.\n"
    )
    assert not result.stderr

    # Standalone call to command: CLI main group is skipped.
    result = invoke(command1, "--help", color=True)
    assert result.exit_code == 0
    assert result.output == (
        "\x1b[94m\x1b[1mUsage: \x1b[0m\x1b[97mcommand1\x1b[0m"
        " \x1b[90m[OPTIONS]\x1b[0m [\x1b[36mMY_ARG\x1b[0m]...\n"
        "\n"
        "  CLI description with extra MY_VAR reference.\n"
        "\n"
        "\x1b[94m\x1b[1mPositional arguments:\x1b[0m\n"
        "  [\x1b[36mMY_ARG\x1b[0m]...  Argument supports help.\n"
        "\n"
        "\x1b[94m\x1b[1mOptions:\x1b[0m\n"
        "  \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m  Show this message and exit.\n"
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
@parametrize("option_decorator", (color_option, color_option()))
@pytest.mark.parametrize(
    "param, expecting_colors",
    (
        ("--color", True),
        ("--no-color", False),
        ("--ansi", True),
        ("--no-ansi", False),
        (None, True),
    ),
)
def test_standalone_color_option(invoke, option_decorator, param, expecting_colors):
    """Check color option values, defaults and effects on all things colored, including
    verbosity option."""

    @click.command
    @verbosity_option
    @option_decorator
    def standalone_color():
        echo(Style(fg="yellow")("It works!"))
        echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")
        echo(style("Run command.", fg="magenta"))
        logging.getLogger("click_extra").warning("Processing...")
        print(style("print() bypass Click.", fg="blue"))
        secho("Done.", fg="green")

    result = invoke(standalone_color, param, "--verbosity", "DEBUG", color=True)
    assert result.exit_code == 0

    if expecting_colors:
        assert result.stdout == (
            "\x1b[33mIt works!\x1b[0m\n"
            "\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m\n"
            "\x1b[35mRun command.\x1b[0m\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "\x1b[32mDone.\x1b[0m\n"
        )
        assert result.stderr == (
            "\x1b[34mdebug\x1b[0m: Verbosity set to DEBUG.\n"
            "\x1b[33mwarning\x1b[0m: Processing...\n"
        )
    else:
        assert result.stdout == (
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
@pytest.mark.parametrize(
    "env, env_expect_colors",
    (
        ({"COLOR": "True"}, True),
        ({"COLOR": "true"}, True),
        ({"COLOR": "1"}, True),
        ({"COLOR": ""}, True),
        ({"COLOR": "False"}, False),
        ({"COLOR": "false"}, False),
        ({"COLOR": "0"}, False),
        ({"NO_COLOR": "True"}, False),
        ({"NO_COLOR": "true"}, False),
        ({"NO_COLOR": "1"}, False),
        ({"NO_COLOR": ""}, False),
        ({"NO_COLOR": "False"}, True),
        ({"NO_COLOR": "false"}, True),
        ({"NO_COLOR": "0"}, True),
        (None, True),
    ),
)
@pytest.mark.parametrize(
    "param, param_expect_colors",
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
    @color_option
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
    "param, expecting_colors",
    (
        ("--color", True),
        ("--no-color", False),
        ("--ansi", True),
        ("--no-ansi", False),
        (None, True),
    ),
)
def test_integrated_color_option(invoke, param, expecting_colors):
    @extra_group
    def color_cli8():
        echo(Style(fg="yellow")("It works!"))
        echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")

    @color_cli8.command()
    def command1():
        echo(style("Run command #1.", fg="magenta"))
        logging.getLogger("click_extra").warning("Processing...")
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
                r"\x1b\[33mwarning\x1b\[0m: Processing...\n"
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
            rf"{default_debug_uncolored_log}warning: Processing\.\.\.\n",
            result.stderr,
        )


@pytest.mark.parametrize(
    "substrings, expected, ignore_case",
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
        styling_method=default_theme.success,
        ignore_case=ignore_case,
    )
    assert result == expected


@parametrize(
    "cmd_decorator, cmd_type",
    # Skip click extra's commands, as help option is already part of the default.
    command_decorators(no_extra=True, with_types=True),
)
@parametrize("option_decorator", (help_option, help_option()))
def test_standalone_help_option(invoke, cmd_decorator, cmd_type, option_decorator):
    @cmd_decorator
    @option_decorator
    def standalone_help():
        echo("It works!")

    result = invoke(standalone_help, "--help")
    assert result.exit_code == 0
    assert not result.stderr

    if "group" in cmd_type:
        assert result.stdout == dedent(
            """\
            Usage: standalone-help [OPTIONS] COMMAND [ARGS]...

            Options:
              -h, --help  Show this message and exit.
            """
        )
    else:
        assert result.stdout == dedent(
            """\
            Usage: standalone-help [OPTIONS]

            Options:
              -h, --help  Show this message and exit.
            """
        )
