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

import logging
import os
import re
from textwrap import dedent

import click
import cloup
import pytest
from boltons.strutils import strip_ansi
from pytest_cases import parametrize

from click_extra import (
    Color,
    ExtraCommand,
    ExtraContext,
    ExtraOption,
    HelpTheme,
    IntRange,
    Style,
    argument,
    echo,
    option,
    option_group,
    pass_context,
    secho,
    style,
)
from click_extra.colorize import (
    HelpExtraFormatter,
    HelpExtraTheme,
    highlight,
)
from click_extra.colorize import (
    default_theme as theme,
)
from click_extra.decorators import (
    color_option,
    command,
    extra_command,
    extra_group,
    help_option,
    verbosity_option,
)
from click_extra.logging import LOG_LEVELS
from click_extra.pytest import (
    command_decorators,
    default_debug_colored_log_end,
    default_debug_colored_log_start,
    default_debug_colored_logging,
    default_debug_uncolored_log_end,
    default_debug_uncolored_log_start,
    default_debug_uncolored_logging,
    default_options_colored_help,
)

from .conftest import skip_windows_colors


def test_theme_definition():
    """Ensure we do not leave any property we would have inherited from cloup and
    logging primitives."""
    assert (
        set(HelpTheme.__dataclass_fields__)
        <= HelpExtraTheme.__dataclass_fields__.keys()
    )

    log_levels = {level.lower() for level in LOG_LEVELS}
    assert log_levels <= HelpExtraTheme.__dataclass_fields__.keys()
    assert log_levels.isdisjoint(HelpTheme.__dataclass_fields__)


def test_extra_theme():
    theme = HelpExtraTheme()

    # Check the same instance is returned when no attribute is set.
    assert theme.with_() == theme
    assert theme.with_() is theme

    # Check that we can't set a non-existing attribute.
    with pytest.raises(TypeError):
        theme.with_(random_arg=Style())

    # Create a new theme with a different color.
    assert theme.choice != Style(fg=Color.magenta)
    new_theme = theme.with_(choice=Style(fg=Color.magenta))
    assert new_theme != theme
    assert new_theme is not theme
    assert new_theme.choice == Style(fg=Color.magenta)

    # Derives a second theme from the first one.
    second_theme = new_theme.with_(choice=Style(fg=Color.magenta))
    assert second_theme == new_theme
    assert second_theme is new_theme


@pytest.mark.parametrize(
    ("opt", "expected_outputs"),
    (
        # Short option.
        (
            # Short option name is highlighted in both the synopsis and the description.
            ExtraOption(["-e"], help="Option -e (-e), not -ee or --e."),
            (
                f" {theme.option('-e')} {theme.metavar('TEXT')} ",
                f" Option {theme.option('-e')} ({theme.option('-e')}), not -ee or --e.",
            ),
        ),
        # Long option.
        (
            # Long option name is highlighted in both the synopsis and the description.
            ExtraOption(["--exclude"], help="Option named --exclude."),
            (
                f" {theme.option('--exclude')} {theme.metavar('TEXT')} ",
                f" Option named {theme.option('--exclude')}.",
            ),
        ),
        # Default value.
        (
            ExtraOption(["--n"], default=1, show_default=True),
            (
                f" {theme.option('--n')} {theme.metavar('INTEGER')} ",
                f" {theme.bracket('[')}"
                f"{theme.bracket('default: ')}"
                f"{theme.default('1')}"
                f"{theme.bracket(']')}",
            ),
        ),
        # Dynamic default.
        (
            ExtraOption(
                ["--username"],
                prompt=True,
                default=lambda: os.environ.get("USER", ""),
                show_default="current user",
            ),
            (
                f" {theme.option('--username')} {theme.metavar('TEXT')} ",
                f" {theme.bracket('[')}"
                f"{theme.bracket('default: ')}"
                f"{theme.default('(current user)')}"
                f"{theme.bracket(']')}",
            ),
        ),
        # Required option.
        (
            ExtraOption(["--x"], required=True, type=int),
            (
                f" {theme.option('--x')} {theme.metavar('INTEGER')} ",
                f" {theme.bracket('[')}"
                f"{theme.bracket('required')}"
                f"{theme.bracket(']')}",
            ),
        ),
        # Required and default value.
        (
            ExtraOption(["--y"], default=1, required=True, show_default=True),
            (
                f" {theme.option('--y')} {theme.metavar('INTEGER')} ",
                f" {theme.bracket('[')}"
                f"{theme.bracket('default: ')}"
                f"{theme.default('1')}"
                f"{theme.bracket('; ')}"
                f"{theme.bracket('required')}"
                f"{theme.bracket(']')}",
            ),
        ),
        # Range option.
        (
            ExtraOption(["--digit"], type=IntRange(0, 9)),
            (
                f" {theme.option('--digit')} {theme.metavar('INTEGER RANGE')} ",
                f" {theme.bracket('[')}"
                f"{theme.bracket('0<=x<=9')}"
                f"{theme.bracket(']')}",
            ),
        ),
        # Boolean flags.
        (
            # Option flag and its opposite names are highlighted, including in the
            # description.
            ExtraOption(
                ["--flag/--no-flag"],
                default=False,
                help="Auto --no-flag and --flag options.",
            ),
            (
                f" {theme.option('--flag')} / {theme.option('--no-flag')} ",
                f" Auto {theme.option('--no-flag')}"
                f" and {theme.option('--flag')} options.",
            ),
        ),
        (
            # Option with single flag is highlighted, but not its negative.
            ExtraOption(
                ["--shout"],
                is_flag=True,
                help="Auto --shout but no --no-shout.",
            ),
            (
                f" {theme.option('--shout')} ",
                f" Auto {theme.option('--shout')} but no --no-shout.",
            ),
        ),
        (
            # Option flag with alternative leading symbol.
            ExtraOption(
                ["/debug;/no-debug"],
                help="Auto /no-debug and /debug options.",
            ),
            (
                f" {theme.option('/debug')}; {theme.option('/no-debug')} ",
                f" Auto {theme.option('/no-debug')}"
                f" and {theme.option('/debug')} options.",
            ),
        ),
        (
            # Option flag with alternative leading symbol.
            ExtraOption(["+w/-w"], help="Auto +w, and -w. Not ++w or -woo."),
            (
                f" {theme.option('+w')} / {theme.option('-w')} ",
                f" Auto {theme.option('+w')}, and {theme.option('-w')}."
                " Not ++w or -woo.",
            ),
        ),
        (
            # Option flag, and its short and negative name are highlighted.
            ExtraOption(
                ["--shout/--no-shout", " /-S"],
                default=False,
                help="Auto --shout, --no-shout and -S.",
            ),
            (
                f" {theme.option('--shout')} / {theme.option('-S')},"
                f" {theme.option('--no-shout')} ",
                f" Auto {theme.option('--shout')}, {theme.option('--no-shout')}"
                f" and {theme.option('-S')}.",
            ),
        ),
        # Choices.
        (
            # Choices after the option name are highlighted. Case is respected.
            ExtraOption(
                ["--manager"],
                type=click.Choice(["apm", "apt", "brew"]),
                help="apt, APT (not aptitude or apt_mint) and brew.",
            ),
            (
                f" {theme.option('--manager')} "
                f"[{theme.choice('apm')}|{theme.choice('apt')}"
                f"|{theme.choice('brew')}] ",
                f" {theme.choice('apt')}, APT (not aptitude or apt_mint) and"
                f" {theme.choice('brew')}.",
            ),
        ),
        # Tuple option.
        (
            ExtraOption(["--item"], type=(str, int), help="Option with tuple type."),
            (f" {theme.option('--item')} {theme.metavar('<TEXT INTEGER>...')} ",),
        ),
        # Metavar.
        (
            # Metavar after the option name is highlighted.
            ExtraOption(
                ["--special"],
                metavar="SPECIAL",
                help="Option with SPECIAL metavar.",
            ),
            (
                f" {theme.option('--special')} {theme.metavar('SPECIAL')} ",
                f" Option with {theme.metavar('SPECIAL')} metavar.",
            ),
        ),
        # Envvars.
        (
            # All envvars in square brackets are highlighted.
            ExtraOption(
                ["--flag1"],
                is_flag=True,
                envvar=["custom1", "FLAG1"],
                show_envvar=True,
            ),
            (
                f" {theme.option('--flag1')} ",
                f" {theme.bracket('[')}"
                f"{theme.bracket('env var: ')}"
                f"{theme.envvar('custom1, FLAG1, TEST_FLAG1')}"
                f"{theme.bracket(']')}",
            ),
        ),
        (
            # Envvars and default.
            ExtraOption(
                ["--flag1"],
                default=1,
                envvar="custom1",
                show_envvar=True,
                show_default=True,
            ),
            (
                f" {theme.option('--flag1')} ",
                f" {theme.bracket('[')}"
                f"{theme.bracket('env var: ')}"
                f"{theme.envvar('custom1, TEST_FLAG1')}"
                f"{theme.bracket('; ')}"
                f"{theme.bracket('default: ')}"
                f"{theme.default('1')}"
                f"{theme.bracket(']')}",
            ),
        ),
    ),
)
def test_option_highlight(opt, expected_outputs):
    """Test highlighting of all option's variations."""
    # Add option to a dummy command.
    cli = ExtraCommand("test", params=[opt])
    ctx = ExtraContext(cli)

    # Render full CLI help.
    help = cli.get_help(ctx)

    # TODO: check extra elements of the option once
    # https://github.com/pallets/click/pull/2517 is released.
    # opt.get_help_extra()

    # Check that the option is highlighted.
    for expected in expected_outputs:
        assert expected in help


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
        r"\x1b\[94m\x1b\[1m\x1b\[4mUsage:\x1b\[0m \x1b\[97mcolor-cli1\x1b\[0m "
        r"\x1b\[36m\x1b\[2m\[OPTIONS\]\x1b\[0m"
        r" \x1b\[36m\x1b\[2mCOMMAND \[ARGS\]...\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mGroup 1:\x1b\[0m\n"
        r"  \x1b\[36m-a\x1b\[0m, \x1b\[36m--o1\x1b\[0m \x1b\[36m\x1b\[2mTEXT\x1b\[0m\n"
        r"  \x1b\[36m-b\x1b\[0m, \x1b\[36m--o2\x1b\[0m \x1b\[36m\x1b\[2mTEXT\x1b\[0m\n"
        r"\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mGroup 2:\x1b\[0m\n"
        r"  \x1b\[36m--o3\x1b\[0m \x1b\[36m\x1b\[2mMY_VAR\x1b\[0m\n"
        r"  \x1b\[36m--o4\x1b\[0m \x1b\[36m\x1b\[2mTEXT\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mOther options:\x1b\[0m\n"
        r"  \x1b\[36m--test\x1b\[0m \x1b\[36m\x1b\[2mTEXT\x1b\[0m\n"
        r"  \x1b\[36m-b\x1b\[0m, \x1b\[36m--boolean\x1b\[0m / \x1b\[36m\+B\x1b\[0m,"
        r" \x1b\[36m--no-boolean\x1b\[0m\n"
        r"                            "
        r"\x1b\[2m\[\x1b\[0m\x1b\[2mdefault: "
        r"\x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mno-boolean\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
        r"  \x1b\[36m/debug\x1b\[0m; \x1b\[36m/no-debug\x1b\[0m"
        r"         \x1b\[2m\[\x1b\[0m\x1b\[2mdefault:"
        r" \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mno-debug\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
        r"  \x1b\[36m--shout\x1b\[0m / \x1b\[36m-S\x1b\[0m, \x1b\[36m--no-shout\x1b\[0m"
        r"  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: "
        r"\x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mno-shout\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
        rf"{default_options_colored_help}"
        r"\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mSubcommand group 1:\x1b\[0m\n"
        r"  \x1b\[36mcommand1\x1b\[0m  CLI description with extra"
        r" \x1b\[36m\x1b\[2mMY_VAR\x1b\[0m reference.\n"
        r"  \x1b\[36mcommand2\x1b\[0m\n\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mExtra commands:\x1b\[0m\n"
        r"  \x1b\[36mcommand3\x1b\[0m\n"
        r"  \x1b\[36mcommand4\x1b\[0m  \x1b\[93m\x1b\[1m\(Deprecated\)\x1b\[0m\n"
    )

    result = invoke(color_cli1, "--help", color=True)
    assert result.exit_code == 0
    assert re.fullmatch(help_screen, result.stdout)
    assert not result.stderr

    result = invoke(color_cli1, "-h", color=True)
    assert result.exit_code == 0
    assert re.fullmatch(help_screen, result.stdout)
    assert not result.stderr

    # CLI main group is invoked before sub-command.
    result = invoke(color_cli1, "command1", "--help", color=True)
    assert result.exit_code == 0
    assert result.stdout == (
        "It works!\n"
        "\x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mcolor-cli1 command1\x1b[0m"
        " \x1b[36m\x1b[2m[OPTIONS]\x1b[0m [\x1b[36mMY_ARG\x1b[0m]...\n"
        "\n"
        "  CLI description with extra MY_VAR reference.\n"
        "\n"
        "\x1b[94m\x1b[1m\x1b[4mPositional arguments:\x1b[0m\n"
        "  [\x1b[36mMY_ARG\x1b[0m]...  Argument supports help.\n"
        "\n"
        "\x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m\n"
        "  \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m  Show this message and exit.\n"
    )
    assert not result.stderr

    # Standalone call to command: CLI main group is skipped.
    result = invoke(command1, "--help", color=True)
    assert result.exit_code == 0
    assert result.stdout == (
        "\x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mcommand1\x1b[0m"
        " \x1b[36m\x1b[2m[OPTIONS]\x1b[0m [\x1b[36mMY_ARG\x1b[0m]...\n"
        "\n"
        "  CLI description with extra MY_VAR reference.\n"
        "\n"
        "\x1b[94m\x1b[1m\x1b[4mPositional arguments:\x1b[0m\n"
        "  [\x1b[36mMY_ARG\x1b[0m]...  Argument supports help.\n"
        "\n"
        "\x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m\n"
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
            """,
        )
        assert not result.stderr


@skip_windows_colors
@parametrize("option_decorator", (color_option, color_option()))
@pytest.mark.parametrize(
    ("param", "expecting_colors"),
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
        assert re.fullmatch(
            (
                rf"{default_debug_colored_logging}"
                r"\x1b\[33mwarning\x1b\[0m: Processing...\n"
                rf"{default_debug_colored_log_end}"
            ),
            result.stderr,
        )
    else:
        assert result.stdout == (
            "It works!\n"
            "Art\n"
            "Run command.\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "Done.\n"
        )
        assert re.fullmatch(
            (
                rf"{default_debug_uncolored_logging}"
                rf"warning: Processing\.\.\.\n"
                rf"{default_debug_uncolored_log_end}"
            ),
            result.stderr,
        )


@skip_windows_colors
@pytest.mark.parametrize(
    ("env", "env_expect_colors"),
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
    ("param", "param_expect_colors"),
    (
        ("--color", True),
        ("--no-color", False),
        ("--ansi", True),
        ("--no-ansi", False),
        (None, True),
    ),
)
def test_no_color_env_convention(
    invoke,
    env,
    env_expect_colors,
    param,
    param_expect_colors,
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
        assert result.stdout == "\x1b[33mIt works!\x1b[0m\n"
    else:
        assert result.stdout == "It works!\n"


# TODO: test with  configuration file


@skip_windows_colors
@pytest.mark.parametrize(
    ("param", "expecting_colors"),
    (
        ("--color", True),
        ("--no-color", False),
        ("--ansi", True),
        ("--no-ansi", False),
        (None, True),
    ),
)
def test_integrated_color_option(invoke, param, expecting_colors):
    """Check effect of color option on all things colored, including verbosity option.

    Also checks the color option in subcommands is inherited from parent context.
    """

    @extra_group
    @pass_context
    def color_cli8(ctx):
        echo(f"ctx.color={ctx.color}")
        echo(Style(fg="yellow")("It works!"))
        echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")

    @color_cli8.command()
    @pass_context
    def command1(ctx):
        echo(f"ctx.color={ctx.color}")
        echo(style("Run command #1.", fg="magenta"))
        logging.getLogger("click_extra").warning("Processing...")
        print(style("print() bypass Click.", fg="blue"))
        secho("Done.", fg="green")

    result = invoke(color_cli8, param, "--verbosity", "DEBUG", "command1", color=True)

    assert result.exit_code == 0
    if expecting_colors:
        assert result.stdout == (
            "ctx.color=True\n"
            "\x1b[33mIt works!\x1b[0m\n"
            "\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m\n"
            "ctx.color=True\n"
            "\x1b[35mRun command #1.\x1b[0m\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "\x1b[32mDone.\x1b[0m\n"
        )
        assert re.fullmatch(
            (
                rf"{default_debug_colored_log_start}"
                r"\x1b\[33mwarning\x1b\[0m: Processing...\n"
                rf"{default_debug_colored_log_end}"
            ),
            result.stderr,
        )

    else:
        assert result.stdout == (
            "ctx.color=False\n"
            "It works!\n"
            "Art\n"
            "ctx.color=False\n"
            "Run command #1.\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "Done.\n"
        )
        assert re.fullmatch(
            (
                rf"{default_debug_uncolored_log_start}"
                rf"warning: Processing\.\.\.\n"
                rf"{default_debug_uncolored_log_end}"
            ),
            result.stderr,
        )


@pytest.mark.parametrize(
    ("original", "substrings", "expected", "ignore_case"),
    (
        # Function input types.
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            ["hey"],
            "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            ("hey",),
            "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            {"hey"},
            "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            "hey",
            "H\x1b[32mey\x1b[0m-xx-xxx-\x1b[32mhe\x1b[0mY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        # Duplicate substrings.
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            ["hey", "hey"],
            "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            ("hey", "hey"),
            "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            {"hey", "hey"},
            "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            "heyhey",
            "H\x1b[32mey\x1b[0m-xx-xxx-\x1b[32mhe\x1b[0mY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        # Case-sensitivity and multiple matches.
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            ["hey"],
            "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            ["Hey"],
            "\x1b[32mHey\x1b[0m-xx-xxx-\x1b[32mheY\x1b[0m-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            True,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            "x",
            "Hey-\x1b[32mxx\x1b[0m-\x1b[32mxxx\x1b[0m-heY-\x1b[32mx\x1b[0mX\x1b[32mx\x1b[0mX\x1b[32mxxxxx\x1b[0m-hey",
            False,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            "x",
            "Hey-\x1b[32mxx\x1b[0m-\x1b[32mxxx\x1b[0m-heY-\x1b[32mxXxXxxxxx\x1b[0m-hey",
            True,
        ),
        # Overlaps.
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            ["xx"],
            "Hey-\x1b[32mxx\x1b[0m-\x1b[32mxxx\x1b[0m-heY-\x1b[32mxXxXxxxxx\x1b[0m-hey",
            True,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            ["xx"],
            "Hey-\x1b[32mxx\x1b[0m-\x1b[32mxxx\x1b[0m-heY-xXxX\x1b[32mxxxxx\x1b[0m-hey",
            False,
        ),
        # No match.
        ("Hey-xx-xxx-heY-xXxXxxxxx-hey", "z", "Hey-xx-xxx-heY-xXxXxxxxx-hey", False),
        ("Hey-xx-xxx-heY-xXxXxxxxx-hey", ["XX"], "Hey-xx-xxx-heY-xXxXxxxxx-hey", False),
        # Special characters.
        (
            "(?P<quote>[']).*?(?P=quote)",
            "[",
            "(?P<quote>\x1b[32m[\x1b[0m']).*?(?P=quote)",
            False,
        ),
        # Unicode normalization.
        ("Straße", "ß", "Stra\x1b[32mß\x1b[0me", False),
        # ("Straße", ["SS"], "Stra\x1b[32mß\x1b[0me", True),
    ),
)
def test_substring_highlighting(original, substrings, expected, ignore_case):
    assert (
        highlight(
            original,
            substrings,
            styling_method=theme.success,
            ignore_case=ignore_case,
        )
        == expected
    )


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
            """,
        )
    else:
        assert result.stdout == dedent(
            """\
            Usage: standalone-help [OPTIONS]

            Options:
              -h, --help  Show this message and exit.
            """,
        )
