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
from enum import Enum, IntEnum, auto
from textwrap import dedent

import click
import cloup
import pytest
from boltons.strutils import strip_ansi

from click_extra import (
    Color,
    ExtraCommand,
    ExtraContext,
    ExtraOption,
    HelpExtraFormatter,
    HelpExtraTheme,
    HelpTheme,
    IntRange,
    LogLevel,
    Style,
    argument,
    color_option,
    command,
    echo,
    group,
    help_option,
    option,
    option_group,
    pass_context,
    secho,
    style,
    verbosity_option,
)
from click_extra.colorize import color_envvars, default_theme as theme, highlight
from click_extra.types import ChoiceSource, EnumChoice
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


@pytest.mark.once
def test_theme_definition():
    """Ensure we do not leave any property we would have inherited from cloup and
    logging primitives."""
    assert (
        set(HelpTheme.__dataclass_fields__)
        <= HelpExtraTheme.__dataclass_fields__.keys()
    )

    log_levels = {level.name.lower() for level in LogLevel}
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


class HashType(Enum):
    MD5 = auto()
    SHA1 = auto()
    BCRYPT = auto()


class Priority(Enum):
    LOW = "low-priority"
    HIGH = "high-priority"


class Port(IntEnum):
    HTTP = 80
    HTTPS = 443


@pytest.mark.parametrize(
    ("opt", "expected_outputs"),
    (
        # Short option.
        (
            ExtraOption(["-e"], help="Option -e (-e), not -ee or --e."),
            (
                " " + theme.option("-e") + " " + theme.metavar("TEXT") + " ",
                " Option "
                + theme.option("-e")
                + " ("
                + theme.option("-e")
                + "), not -ee or --e.",
            ),
        ),
        # Long option.
        (
            ExtraOption(["--exclude"], help="Option named --exclude."),
            (
                " " + theme.option("--exclude") + " " + theme.metavar("TEXT") + " ",
                " Option named " + theme.option("--exclude") + ".",
            ),
        ),
        # Default value.
        (
            ExtraOption(["--n"], default=1, show_default=True),
            (
                " " + theme.option("--n") + " " + theme.metavar("INTEGER") + " ",
                " "
                + theme.bracket("[")
                + theme.bracket("default: ")
                + theme.default("1")
                + theme.bracket("]"),
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
                " " + theme.option("--username") + " " + theme.metavar("TEXT") + " ",
                " "
                + theme.bracket("[")
                + theme.bracket("default: ")
                + theme.default("(current user)")
                + theme.bracket("]"),
            ),
        ),
        # Default value is an empty string.
        (
            ExtraOption(["--prefix"], default="", show_default=True, help="Prefix."),
            (
                " "
                + theme.bracket("[")
                + theme.bracket("default: ")
                + theme.default('""')
                + theme.bracket("]"),
            ),
        ),
        # Default value of None (no bracket rendered).
        (
            ExtraOption(["--optional"], default=None, help="An optional value."),
            (" An optional value.",),
        ),
        # Required option.
        (
            ExtraOption(["--x"], required=True, type=int),
            (
                " " + theme.option("--x") + " " + theme.metavar("INTEGER") + " ",
                " "
                + theme.bracket("[")
                + theme.required("required")
                + theme.bracket("]"),
            ),
        ),
        # Required and default value.
        (
            ExtraOption(["--y"], default=1, required=True, show_default=True),
            (
                " " + theme.option("--y") + " " + theme.metavar("INTEGER") + " ",
                " "
                + theme.bracket("[")
                + theme.bracket("default: ")
                + theme.default("1")
                + theme.bracket("; ")
                + theme.required("required")
                + theme.bracket("]"),
            ),
        ),
        # Range option (closed bounds).
        (
            ExtraOption(["--digit"], type=IntRange(0, 9)),
            (
                " "
                + theme.option("--digit")
                + " "
                + theme.metavar("INTEGER RANGE")
                + " ",
                " "
                + theme.bracket("[")
                + theme.range_label("0<=x<=9")
                + theme.bracket("]"),
            ),
        ),
        # Range with open upper bound.
        (
            ExtraOption(["--ratio"], type=IntRange(min=0, max_open=True, max=100)),
            (
                " "
                + theme.bracket("[")
                + theme.range_label("0<=x<100")
                + theme.bracket("]"),
            ),
        ),
        # Range with only a minimum.
        (
            ExtraOption(["--port"], type=IntRange(min=1024)),
            (
                " "
                + theme.bracket("[")
                + theme.range_label("x>=1024")
                + theme.bracket("]"),
            ),
        ),
        # Range + default + required combined.
        (
            ExtraOption(
                ["--pct"],
                type=IntRange(0, 100),
                default=50,
                required=True,
                show_default=True,
            ),
            (
                " "
                + theme.bracket("[")
                + theme.bracket("default: ")
                + theme.default("50")
                + theme.bracket("; ")
                + theme.range_label("0<=x<=100")
                + theme.bracket("; ")
                + theme.required("required")
                + theme.bracket("]"),
            ),
        ),
        # Envvar + default + range + required (all four bracket fields).
        (
            # All four bracket fields combined. Checked individually because
            # Click's text wrapper may break the line inside the bracket.
            ExtraOption(
                ["--threshold"],
                type=IntRange(1, 10),
                default=5,
                required=True,
                show_default=True,
                envvar="THRESHOLD",
                show_envvar=True,
            ),
            (
                theme.bracket("env var: ")
                + theme.envvar("THRESHOLD, TEST_THRESHOLD"),
                theme.bracket("default: ") + theme.default("5"),
                theme.range_label("1<=x<=10"),
                theme.required("required") + theme.bracket("]"),
            ),
        ),
        # Boolean flags.
        (
            ExtraOption(
                ["--flag/--no-flag"],
                default=False,
                help="Auto --no-flag and --flag options.",
            ),
            (
                " " + theme.option("--flag") + " / " + theme.option("--no-flag") + " ",
                " Auto "
                + theme.option("--no-flag")
                + " and "
                + theme.option("--flag")
                + " options.",
            ),
        ),
        (
            # Single flag: its name is highlighted, but --no-shout is not.
            ExtraOption(
                ["--shout"],
                is_flag=True,
                help="Auto --shout but no --no-shout.",
            ),
            (
                " " + theme.option("--shout") + " ",
                " Auto " + theme.option("--shout") + " but no --no-shout.",
            ),
        ),
        (
            # Boolean flag with show_default.
            ExtraOption(
                ["--color/--no-color"],
                default=True,
                show_default=True,
                help="Enable color output.",
            ),
            (
                " " + theme.option("--color") + " / " + theme.option("--no-color") + " ",
                " "
                + theme.bracket("[")
                + theme.bracket("default: ")
                + theme.default("color")
                + theme.bracket("]"),
            ),
        ),
        (
            # Slash-style flag.
            ExtraOption(
                ["/debug;/no-debug"],
                help="Auto /no-debug and /debug options.",
            ),
            (
                " " + theme.option("/debug") + "; " + theme.option("/no-debug") + " ",
                " Auto "
                + theme.option("/no-debug")
                + " and "
                + theme.option("/debug")
                + " options.",
            ),
        ),
        (
            # Plus/minus flag.
            ExtraOption(["+w/-w"], help="Auto +w, and -w. Not ++w or -woo."),
            (
                " " + theme.option("+w") + " / " + theme.option("-w") + " ",
                " Auto "
                + theme.option("+w")
                + ", and "
                + theme.option("-w")
                + ". Not ++w or -woo.",
            ),
        ),
        (
            # Flag with short alias and negative name.
            ExtraOption(
                ["--shout/--no-shout", " /-S"],
                default=False,
                help="Auto --shout, --no-shout and -S.",
            ),
            (
                " "
                + theme.option("--shout")
                + " / "
                + theme.option("-S")
                + ", "
                + theme.option("--no-shout")
                + " ",
                " Auto "
                + theme.option("--shout")
                + ", "
                + theme.option("--no-shout")
                + " and "
                + theme.option("-S")
                + ".",
            ),
        ),
        # Choices.
        (
            ExtraOption(
                ["--manager"],
                type=click.Choice(["apm", "apt", "brew"]),
                help="apt, APT (not aptitude or apt_mint) and brew.",
            ),
            (
                " "
                + theme.option("--manager")
                + " "
                + "["
                + theme.choice("apm")
                + "|"
                + theme.choice("apt")
                + "|"
                + theme.choice("brew")
                + "] ",
                " "
                + theme.choice("apt")
                + ", APT (not aptitude or apt_mint) and"
                + " "
                + theme.choice("brew")
                + ".",
            ),
        ),
        (
            # Integer choices.
            ExtraOption(
                ["--number-choice"],
                type=click.Choice([1, 2, 3]),
                help="1, 2 (not 10, 01, 222 or 3333) and 3.",
            ),
            (
                " "
                + theme.option("--number-choice")
                + " "
                + "["
                + theme.choice("1")
                + "|"
                + theme.choice("2")
                + "|"
                + theme.choice("3")
                + "] ",
                " "
                + theme.choice("1")
                + ", "
                + theme.choice("2")
                + " (not 10, 01, 222 or 3333) and "
                + theme.choice("3")
                + ".",
            ),
        ),
        (
            # Enum choices (auto values): names are displayed and highlighted.
            ExtraOption(
                ["--hash-type"],
                type=click.Choice(HashType),
                help="MD5, SHA1 (not SHA128 or SHA1024) and BCRYPT.",
            ),
            (
                " "
                + theme.option("--hash-type")
                + " "
                + "["
                + theme.choice("MD5")
                + "|"
                + theme.choice("SHA1")
                + "|"
                + theme.choice("BCRYPT")
                + "] ",
                " "
                + theme.choice("MD5")
                + ", "
                + theme.choice("SHA1")
                + " (not SHA128 or SHA1024) and "
                + theme.choice("BCRYPT")
                + ".",
            ),
        ),
        (
            # Enum with string values: Click displays member names, not values.
            ExtraOption(
                ["--priority"],
                type=click.Choice(Priority),
                help="Set priority to LOW or HIGH.",
            ),
            (
                "["
                + theme.choice("LOW")
                + "|"
                + theme.choice("HIGH")
                + "]",
                " Set priority to "
                + theme.choice("LOW")
                + " or "
                + theme.choice("HIGH")
                + ".",
            ),
        ),
        (
            # IntEnum: Click displays member names, not integer values.
            ExtraOption(
                ["--port"],
                type=click.Choice(Port),
            ),
            (
                "["
                + theme.choice("HTTP")
                + "|"
                + theme.choice("HTTPS")
                + "]",
            ),
        ),
        (
            # EnumChoice with NAME source: case-folded names are displayed and
            # highlighted (case_sensitive defaults to False in EnumChoice).
            ExtraOption(
                ["--priority"],
                type=EnumChoice(Priority, choice_source=ChoiceSource.NAME),
            ),
            (
                "["
                + theme.choice("low")
                + "|"
                + theme.choice("high")
                + "]",
            ),
        ),
        (
            # EnumChoice with VALUE source: values are displayed and highlighted.
            ExtraOption(
                ["--priority"],
                type=EnumChoice(Priority, choice_source=ChoiceSource.VALUE),
            ),
            (
                "["
                + theme.choice("low-priority")
                + "|"
                + theme.choice("high-priority")
                + "]",
            ),
        ),
        (
            # Choice with default and envvar.
            ExtraOption(
                ["--render-mode"],
                type=click.Choice(["auto", "always", "never"]),
                default="auto",
                show_default=True,
                envvar="RENDER_MODE",
                show_envvar=True,
            ),
            (
                "["
                + theme.choice("auto")
                + "|"
                + theme.choice("always")
                + "|"
                + theme.choice("never")
                + "]",
                " "
                + theme.bracket("[")
                + theme.bracket("env var: ")
                + theme.envvar("RENDER_MODE, TEST_RENDER_MODE")
                + theme.bracket("; ")
                + theme.bracket("default: ")
                + theme.default("auto")
                + theme.bracket("]"),
            ),
        ),
        # DateTime formats highlighted as choices.
        (
            ExtraOption(
                ["--date"],
                type=click.DateTime(["%Y-%m-%d"]),
                help="A date in %Y-%m-%d format.",
            ),
            (
                " "
                + theme.option("--date")
                + " "
                + "["
                + theme.choice("%Y-%m-%d")
                + "] ",
                " A date in " + theme.choice("%Y-%m-%d") + " format.",
            ),
        ),
        (
            # Multiple DateTime formats.
            ExtraOption(
                ["--timestamp"],
                type=click.DateTime(["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]),
            ),
            (
                "["
                + theme.choice("%Y-%m-%d")
                + "|"
                + theme.choice("%Y-%m-%dT%H:%M:%S")
                + "]",
            ),
        ),
        # Custom metavar on a Choice type is highlighted as metavar.
        (
            ExtraOption(
                ["--level"],
                type=click.Choice(["low", "mid", "high"]),
                metavar="LEVEL",
                help="Set LEVEL priority.",
            ),
            (
                " " + theme.option("--level") + " " + theme.metavar("LEVEL") + " ",
                " Set " + theme.metavar("LEVEL") + " priority.",
            ),
        ),
        # Tuple option.
        (
            ExtraOption(["--item"], type=(str, int), help="Option with tuple type."),
            (
                " "
                + theme.option("--item")
                + " "
                + theme.metavar("<TEXT INTEGER>...")
                + " ",
            ),
        ),
        # Metavar.
        (
            ExtraOption(
                ["--special"],
                metavar="SPECIAL",
                help="Option with SPECIAL metavar.",
            ),
            (
                " " + theme.option("--special") + " " + theme.metavar("SPECIAL") + " ",
                " Option with " + theme.metavar("SPECIAL") + " metavar.",
            ),
        ),
        # Path type.
        (
            ExtraOption(
                ["--config"],
                type=click.Path(exists=True),
                help="Path to config file.",
            ),
            (
                " " + theme.option("--config") + " " + theme.metavar("PATH") + " ",
                " Path to config file.",
            ),
        ),
        # File type.
        (
            ExtraOption(["--log"], type=click.File("w"), help="Log file."),
            (" " + theme.option("--log") + " " + theme.metavar("FILENAME") + " ",),
        ),
        # Multiple option (accepts repeated values).
        (
            ExtraOption(["--tag"], multiple=True, help="Add tags."),
            (
                " " + theme.option("--tag") + " " + theme.metavar("TEXT") + " ",
                " Add tags.",
            ),
        ),
        # Count option.
        (
            ExtraOption(["-v", "--verbose"], count=True, help="Increase verbosity."),
            (
                " "
                + theme.option("-v")
                + ", "
                + theme.option("--verbose")
                + " ",
                " Increase verbosity.",
            ),
        ),
        # Two options sharing the same metavar.
        (
            ExtraOption(["--input"], metavar="FILE", help="Input FILE path."),
            (
                " " + theme.option("--input") + " " + theme.metavar("FILE") + " ",
                " Input " + theme.metavar("FILE") + " path.",
            ),
        ),
        # Envvars.
        (
            ExtraOption(
                ["--flag1"],
                is_flag=True,
                envvar=["custom1", "FLAG1"],
                show_envvar=True,
            ),
            (
                " " + theme.option("--flag1") + " ",
                " "
                + theme.bracket("[")
                + theme.bracket("env var: ")
                + theme.envvar(
                    ("CUSTOM1" if os.name == "nt" else "custom1")
                    + ", FLAG1, TEST_FLAG1"
                )
                + theme.bracket("]"),
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
                " " + theme.option("--flag1") + " ",
                " "
                + theme.bracket("[")
                + theme.bracket("env var: ")
                + theme.envvar(
                    ("CUSTOM1" if os.name == "nt" else "custom1") + ", TEST_FLAG1"
                )
                + theme.bracket("; ")
                + theme.bracket("default: ")
                + theme.default("1")
                + theme.bracket("]"),
            ),
        ),
        # Deprecated (boolean).
        (
            ExtraOption(
                ["-X"],
                help="An old option that you should not use anymore.",
                deprecated=True,
            ),
            (
                " " + theme.option("-X") + " " + theme.metavar("TEXT") + " ",
                " An old option that you should not use anymore."
                + theme.deprecated("(DEPRECATED)"),
            ),
        ),
        (
            click.Option(
                ["-X"],
                help="An old option that you should not use anymore.",
                deprecated=True,
            ),
            (
                " " + theme.option("-X") + " " + theme.metavar("TEXT") + " ",
                " An old option that you should not use anymore."
                + theme.deprecated("(DEPRECATED)"),
            ),
        ),
        (
            cloup.Option(
                ["-X"],
                help="An old option that you should not use anymore.",
                deprecated=True,
            ),
            (
                " " + theme.option("-X") + " " + theme.metavar("TEXT") + " ",
                " An old option that you should not use anymore."
                + theme.deprecated("(DEPRECATED)"),
            ),
        ),
        # Deprecated with custom message.
        (
            ExtraOption(
                ["--old-api"],
                deprecated="use --new-api instead",
                help="Legacy endpoint.",
            ),
            (
                " Legacy endpoint."
                + theme.deprecated("(DEPRECATED: use --new-api instead)"),
            ),
        ),
        # Long option that is prefix of text in help.
        (
            ExtraOption(["--output"], help="Use --output-dir for directories."),
            (
                " " + theme.option("--output") + " " + theme.metavar("TEXT") + " ",
                " Use --output-dir for directories.",
            ),
        ),
    ),
)
def test_option_highlight(opt, expected_outputs):
    """Test highlighting of all option variations: types, defaults, ranges,
    envvars, choices, flags, metavars, deprecated messages."""
    cli = ExtraCommand("test", params=[opt])
    ctx = ExtraContext(cli)
    help = cli.get_help(ctx)

    for expected in expected_outputs:
        assert expected in help


def test_skip_hidden_option():
    """Ensure hidden options are not highlighted."""
    opt1 = ExtraOption(["--hidden"], hidden=True, help="Invisible --hidden option.")
    opt2 = ExtraOption(
        ["--visible"], help="Visible option referencing --hidden option."
    )
    cli = ExtraCommand("test", params=[opt1, opt2])
    ctx = ExtraContext(cli)

    help = cli.get_help(ctx)

    assert "Invisible --hidden option." not in help
    # Check that the option is not highlighted.
    assert "Visible option referencing --hidden option." in help


def test_cross_ref_highlight_disabled():
    """When ``cross_ref_highlight`` is ``False``, only structural elements are
    styled (bracket fields, deprecated messages, subcommands). Options, choices,
    metavars, arguments, and CLI names in free-form text are left plain."""
    no_xref_theme = HelpExtraTheme.dark().with_(cross_ref_highlight=False)

    cli = ExtraCommand(
        "test",
        params=[
            ExtraOption(
                ["--output"],
                default="out.csv",
                show_default=True,
                help="Write to --output path.",
            ),
            ExtraOption(
                ["--format"],
                type=click.Choice(["json", "csv"]),
                help="Output format.",
            ),
        ],
    )
    ctx = ExtraContext(cli, formatter_settings={"theme": no_xref_theme})
    help_text = cli.get_help(ctx)

    # Bracket fields ARE still styled (structural).
    assert theme.bracket("[") in help_text
    assert theme.default("out.csv") in help_text

    # Options, choices and metavars in free text are NOT styled.
    assert theme.option("--output") not in help_text
    assert theme.option("--format") not in help_text
    assert theme.choice("json") not in help_text
    assert theme.choice("csv") not in help_text
    assert theme.metavar("TEXT") not in help_text


@pytest.mark.parametrize(
    ("params", "expected", "forbidden"),
    (
        # Argument names in Usage and description.
        pytest.param(
            [
                click.Argument(["src"], type=click.Path()),
                click.Argument(["dst"], type=click.Path()),
            ],
            [theme.argument("SRC"), theme.argument("DST")],
            [],
            id="basic-arguments",
        ),
        # Optional and variadic arguments.
        pytest.param(
            [
                click.Argument(["files"], nargs=-1),
                click.Argument(["output"], required=False),
            ],
            [theme.argument("[FILES]..."), theme.argument("[OUTPUT]")],
            [],
            id="optional-variadic",
        ),
        # Argument gets argument style, not generic metavar style.
        pytest.param(
            [
                click.Argument(["my_file"]),
                ExtraOption(["--out"], metavar="OUTFILE"),
            ],
            [theme.argument("MY_FILE"), theme.metavar("OUTFILE")],
            [theme.metavar("MY_FILE")],
            id="argument-not-metavar",
        ),
    ),
)
def test_argument_highlight(params, expected, forbidden):
    """Argument metavars get the ``argument`` style, distinct from option
    metavars."""
    cli = ExtraCommand("test", params=params, help="Copy SRC to DST.")
    ctx = ExtraContext(cli)
    help_text = cli.get_help(ctx)

    for fragment in expected:
        assert fragment in help_text
    for fragment in forbidden:
        assert fragment not in help_text


@pytest.mark.parametrize(
    ("params", "help_text", "expected_present", "expected_absent"),
    (
        # Partial word must not be highlighted.
        pytest.param(
            [],
            None,
            [],
            [],
            id="partial-word-snap",
        ),
        # Argument name must not shadow an option with the same suffix.
        pytest.param(
            [
                ExtraOption(["--list-keys"], is_flag=True, help="List all keys."),
                click.Argument(["keys"], nargs=-1),
            ],
            None,
            [" " + theme.option("--list-keys") + " "],
            [],
            id="argument-does-not-shadow-option",
        ),
        # --table must not match inside --table-format in help prose.
        pytest.param(
            [ExtraOption(["--table/--no-table"], is_flag=True, default=True)],
            "Use --table-format to pick a format.",
            [],
            [theme.option("--table") + "-format"],
            id="option-prefix-in-prose",
        ),
        # Choice must not match in dotted names, URLs, hyphens, or alerts.
        pytest.param(
            [
                ExtraOption(
                    ["--format"],
                    type=click.Choice(["toml", "json", "github", "WARNING"]),
                ),
            ],
            (
                "Reads pyproject.toml for config."
                ' Remove the "[!WARNING]" block.'
                " Issues by github-actions[bot]."
                " See https://github.com/owner/repo."
                " Use github or json format."
            ),
            ["|" + theme.choice("github") + "|", "|" + theme.choice("json") + "|"],
            [
                "pyproject." + theme.choice("toml"),
                theme.choice("github") + "-actions",
                "/" + theme.choice("github"),
                "!" + theme.choice("WARNING"),
            ],
            id="choice-false-positives",
        ),
        # Default value must not be double-styled by the choice pass.
        pytest.param(
            [
                ExtraOption(
                    ["--table-format"],
                    type=click.Choice(["github", "outline", "rounded-outline"]),
                    default="rounded-outline",
                    show_default=True,
                    help="Rendering style of tables.",
                ),
            ],
            None,
            [theme.default("rounded-outline")],
            [],
            id="default-not-double-styled",
        ),
        # Choice values that look like option names.
        pytest.param(
            [
                ExtraOption(
                    ["--mode"],
                    type=click.Choice(["--fast", "--slow", "normal"]),
                ),
            ],
            None,
            [
                theme.choice("--fast"),
                theme.choice("--slow"),
                theme.choice("normal"),
            ],
            [],
            id="choice-looks-like-option",
        ),
    ),
)
def test_no_false_positive_highlight(params, help_text, expected_present, expected_absent):
    """Verify that highlighting does not leak into compound words, URLs, dotted
    names, already-styled regions, or partial-word matches."""
    cli = ExtraCommand("test", params=params, help=help_text)
    ctx = ExtraContext(cli)
    rendered = cli.get_help(ctx)

    # Special case: the partial-word test uses the formatter directly.
    if not params:
        formatter = HelpExtraFormatter()
        formatter.write("package snapshot")
        formatter.choices.add("snap")
        rendered = formatter.getvalue()
        assert strip_ansi(rendered) == rendered
        return

    for fragment in expected_present:
        assert fragment in rendered
    for fragment in expected_absent:
        assert fragment not in rendered


def test_parent_keywords_highlighted_in_subcommand_help():
    """Parent group names, options, and choices must be highlighted in
    subcommand help text."""
    from click_extra.commands import ExtraGroup

    grp = ExtraGroup(
        "myapp",
        params=[
            ExtraOption(
                ["--table-format"],
                type=click.Choice(["github", "json", "csv"]),
            ),
        ],
    )

    sub = ExtraCommand(
        "sub",
        help="Example: myapp --table-format github sub",
    )
    grp.add_command(sub)

    parent_ctx = ExtraContext(grp, info_name="myapp")
    ctx = ExtraContext(sub, parent=parent_ctx, info_name="sub")
    help_text = sub.get_help(ctx)

    assert " " + theme.invoked_command("myapp") + " " in help_text
    assert " " + theme.option("--table-format") + " " in help_text
    assert theme.choice("github") + " " in help_text


def test_command_aliases_collected():
    """Command aliases are collected as keywords for highlighting."""
    from click_extra.commands import ExtraGroup

    grp = ExtraGroup("cli")

    @command(params=None, aliases=["ci"])
    def commit():
        """Record changes."""

    grp.add_command(commit)

    ctx = ExtraContext(grp, info_name="cli")
    keywords = grp._collect_keywords(ctx)
    # command_aliases is the 3rd element in the returned tuple.
    command_aliases = keywords[2]
    assert "ci" in command_aliases


def test_keyword_collection(invoke, assert_output_regex):
    # Create a dummy Click CLI.
    @group
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
    @option("--long-shout/--no-long-shout", " /-S", default=False)
    def color_cli1(o1, o2, o3, o4, test, boolean, debug, long_shout):
        echo("It works!")

    @command(params=None)
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

    @click.command(deprecated=True)
    def command4():
        echo("Run click-extra command #4...")

    color_cli1.section("Subcommand group 1", command1, command2)
    color_cli1.section("Extra commands", command3, command4)

    help_screen = (
        r"\x1b\[94m\x1b\[1m\x1b\[4mUsage:\x1b\[0m \x1b\[97mcolor-cli1\x1b\[0m \x1b\[36m\x1b\[2m\[OPTIONS\]\x1b\[0m \x1b\[36m\x1b\[2mCOMMAND \[ARGS\]\.\.\.\x1b\[0m\n"
        r"\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mGroup 1:\x1b\[0m\n"
        r"  \x1b\[36m-a\x1b\[0m, \x1b\[36m--o1\x1b\[0m \x1b\[36m\x1b\[2mTEXT\x1b\[0m\n"
        r"  \x1b\[36m-b\x1b\[0m, \x1b\[36m--o2\x1b\[0m \x1b\[36m\x1b\[2mTEXT\x1b\[0m\n"
        r"\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mGroup 2:\x1b\[0m\n"
        r"  \x1b\[36m--o3\x1b\[0m \x1b\[36m\x1b\[2mMY_VAR\x1b\[0m\n"
        r"  \x1b\[36m--o4\x1b\[0m \x1b\[36m\x1b\[2mTEXT\x1b\[0m\n"
        r"\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mOther options:\x1b\[0m\n"
        r"  \x1b\[36m--test\x1b\[0m \x1b\[36m\x1b\[2mTEXT\x1b\[0m\n"
        r"  \x1b\[36m-b\x1b\[0m, \x1b\[36m--boolean\x1b\[0m / \x1b\[36m\+B\x1b\[0m, \x1b\[36m--no-boolean\x1b\[0m\n"
        r"                          \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mno-boolean\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
        r"  \x1b\[36m/debug\x1b\[0m; \x1b\[36m/no-debug\x1b\[0m       \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mno-debug\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
        r"  \x1b\[36m--long-shout\x1b\[0m / \x1b\[36m-S\x1b\[0m, \x1b\[36m--no-long-shout\x1b\[0m\n"
        r"                          \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mno-long-shout\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
        rf"{default_options_colored_help}\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mSubcommand group 1:\x1b\[0m\n"
        r"  \x1b\[36mcommand1\x1b\[0m  CLI description with extra \x1b\[36m\x1b\[2mMY_VAR\x1b\[0m reference\.\n"
        r"  \x1b\[36mcommand2\x1b\[0m\n"
        r"\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mExtra commands:\x1b\[0m\n"
        r"  \x1b\[36mcommand3\x1b\[0m\n"
        r"  \x1b\[36mcommand4\x1b\[0m  \x1b\[93m\x1b\[1m\(DEPRECATED\)\x1b\[0m\n"
    )

    result = invoke(color_cli1, "--help", color=True)
    assert_output_regex(result.stdout, help_screen)
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(color_cli1, "-h", color=True)
    assert_output_regex(result.stdout, help_screen)
    assert not result.stderr
    assert result.exit_code == 0

    # CLI main group is invoked before sub-command.
    result = invoke(color_cli1, "command1", "--help", color=True)
    assert result.stdout == (
        "It works!\n"
        "\x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mcolor-cli1 command1\x1b[0m"
        " \x1b[36m\x1b[2m[OPTIONS]\x1b[0m \x1b[36m[MY_ARG]...\x1b[0m\n"
        "\n"
        "  CLI description with extra MY_VAR reference.\n"
        "\n"
        "\x1b[94m\x1b[1m\x1b[4mPositional arguments:\x1b[0m\n"
        "  \x1b[36m[MY_ARG]...\x1b[0m  Argument supports help.\n"
        "\n"
        "\x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m\n"
        "  \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m  Show this message and exit.\n"
    )
    assert not result.stderr
    assert result.exit_code == 0

    # Standalone call to command: CLI main group is skipped.
    result = invoke(command1, "--help", color=True)
    assert result.stdout == (
        "\x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mcommand1\x1b[0m"
        " \x1b[36m\x1b[2m[OPTIONS]\x1b[0m \x1b[36m[MY_ARG]...\x1b[0m\n"
        "\n"
        "  CLI description with extra MY_VAR reference.\n"
        "\n"
        "\x1b[94m\x1b[1m\x1b[4mPositional arguments:\x1b[0m\n"
        "  \x1b[36m[MY_ARG]...\x1b[0m  Argument supports help.\n"
        "\n"
        "\x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m\n"
        "  \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m  Show this message and exit.\n"
    )
    assert not result.stderr
    assert result.exit_code == 0

    # Make sure other subcommands do not interfere with each other.
    for cmd_id in ("command2", "command3", "command4"):
        result = invoke(color_cli1, cmd_id, "--help", color=True)
        assert result.exit_code == 0


@skip_windows_colors
@pytest.mark.parametrize("option_decorator", (color_option, color_option()))
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
def test_standalone_color_option(
    invoke, option_decorator, param, expecting_colors, assert_output_regex
):
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
    if expecting_colors:
        assert result.stdout == (
            "\x1b[33mIt works!\x1b[0m\n"
            "\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m\n"
            "\x1b[35mRun command.\x1b[0m\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "\x1b[32mDone.\x1b[0m\n"
        )
        assert_output_regex(
            result.stderr,
            (
                rf"{default_debug_colored_logging}"
                r"\x1b\[33mwarning\x1b\[0m: Processing\.\.\.\n"
                rf"{default_debug_colored_log_end}"
            ),
        )
    else:
        assert result.stdout == (
            "It works!\n"
            "Art\n"
            "Run command.\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "Done.\n"
        )
        assert_output_regex(
            result.stderr,
            (
                rf"{default_debug_uncolored_logging}"
                r"warning: Processing\.\.\.\n"
                rf"{default_debug_uncolored_log_end}"
            ),
        )
    assert result.exit_code == 0


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
        ({"LLM": "True"}, False),
        ({"LLM": "true"}, False),
        ({"LLM": "1"}, False),
        ({"LLM": ""}, False),
        ({"LLM": "False"}, True),
        ({"LLM": "false"}, True),
        ({"LLM": "0"}, True),
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

    # Unset all recognized color env vars so the outer environment (e.g.
    # LLM=1 set by AI agents) doesn't leak into the baseline case.
    if env is None:
        env = {var: None for var in color_envvars if var in os.environ}

    result = invoke(color_cli7, param, color=True, env=env)

    # Params always overrides env's expectations.
    expecting_colors = env_expect_colors
    if param:
        expecting_colors = param_expect_colors
    if expecting_colors:
        assert result.stdout == "\x1b[33mIt works!\x1b[0m\n"
    else:
        assert result.stdout == "It works!\n"

    assert result.exit_code == 0
    assert not result.stderr


# TODO: test with  configuration file


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
def test_integrated_color_option(invoke, param, expecting_colors, assert_output_regex):
    """Check effect of color option on all things colored, including verbosity option.

    Also checks the color option in subcommands is inherited from parent context.
    """

    @group
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
        assert_output_regex(
            result.stderr,
            (
                rf"{default_debug_colored_log_start}"
                r"\x1b\[33mwarning\x1b\[0m: Processing\.\.\.\n"
                rf"{default_debug_colored_log_end}"
            ),
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
        assert_output_regex(
            result.stderr,
            (
                rf"{default_debug_uncolored_log_start}"
                r"warning: Processing\.\.\.\n"
                rf"{default_debug_uncolored_log_end}"
            ),
        )
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("content", "patterns", "expected", "ignore_case"),
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
            "Hey-xx-xxx-heY-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            ["h", "e", "y"],
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
            "heyhey",
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            False,
        ),
        # Case-sensitivity and multiple matches.
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
        (
            "[double-grid|double-outline|fancy-grid|fancy-outline|github|grid"
            "|heavy-grid|heavy-outline|mixed-grid|mixed-outline|moinmoin|outline"
            "|rounded-grid|rounded-outline|rst|simple|simple-grid|simple-outline]",
            [
                "double-grid",
                "double-outline",
                "fancy-grid",
                "fancy-outline",
                "github",
                "grid",
                "heavy-grid",
                "heavy-outline",
                "mixed-grid",
                "mixed-outline",
                "moinmoin",
                "outline",
                "rounded-grid",
                "rounded-outline",
                "rst",
                "simple",
                "simple-grid",
                "simple-outline",
            ],
            "[\x1b[32mdouble-grid\x1b[0m|\x1b[32mdouble-outline\x1b[0m"
            "|\x1b[32mfancy-grid\x1b[0m|\x1b[32mfancy-outline\x1b[0m"
            "|\x1b[32mgithub\x1b[0m|\x1b[32mgrid\x1b[0m|\x1b[32mheavy-grid\x1b[0m"
            "|\x1b[32mheavy-outline\x1b[0m|\x1b[32mmixed-grid\x1b[0m"
            "|\x1b[32mmixed-outline\x1b[0m|\x1b[32mmoinmoin\x1b[0m"
            "|\x1b[32moutline\x1b[0m|\x1b[32mrounded-grid\x1b[0m"
            "|\x1b[32mrounded-outline\x1b[0m|\x1b[32mrst\x1b[0m|\x1b[32msimple\x1b[0m"
            "|\x1b[32msimple-grid\x1b[0m|\x1b[32msimple-outline\x1b[0m]",
            False,
        ),
        # Regex patterns - basic patterns
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            re.compile(r"h\w+"),
            "Hey-xx-xxx-\x1b[32mheY\x1b[0m-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            False,
        ),
        (
            "Hey-xx-xxx-heY-xXxXxxxxx-hey",
            re.compile(r"h\w+"),
            "\x1b[32mHey\x1b[0m-xx-xxx-\x1b[32mheY\x1b[0m-xXxXxxxxx-\x1b[32mhey\x1b[0m",
            True,
        ),
        # Regex patterns - character classes
        (
            "test123-abc456-xyz789",
            re.compile(r"\d+"),
            "test\x1b[32m123\x1b[0m-abc\x1b[32m456\x1b[0m-xyz\x1b[32m789\x1b[0m",
            False,
        ),
        (
            "file.txt config.json data.csv",
            re.compile(r"\w+\.\w+"),
            "\x1b[32mfile.txt\x1b[0m \x1b[32mconfig.json\x1b[0m \x1b[32mdata.csv\x1b[0m",
            False,
        ),
        # Regex patterns - word boundaries
        (
            "testing test tested",
            re.compile(r"\btest\b"),
            "testing \x1b[32mtest\x1b[0m tested",
            False,
        ),
        # Regex patterns - alternation
        (
            "apple banana cherry",
            re.compile(r"apple|cherry"),
            "\x1b[32mapple\x1b[0m banana \x1b[32mcherry\x1b[0m",
            False,
        ),
        # Regex patterns - quantifiers
        (
            "a aa aaa aaaa aaaaa",
            re.compile(r"a{2,3}"),
            "a \x1b[32maa\x1b[0m \x1b[32maaa\x1b[0m \x1b[32maaaa\x1b[0m \x1b[32maaaaa\x1b[0m",
            False,
        ),
        # Compiled regex patterns
        (
            "test@example.com admin@site.org",
            re.compile(r"\w+@\w+\.\w+"),
            "\x1b[32mtest@example.com\x1b[0m \x1b[32madmin@site.org\x1b[0m",
            False,
        ),
        # Mixed literal and regex patterns
        (
            "--verbose --debug --help -v -d -h",
            ["--help", re.compile(r"--\w+"), re.compile(r"-[a-z]")],
            "\x1b[32m--verbose\x1b[0m \x1b[32m--debug\x1b[0m \x1b[32m--help\x1b[0m \x1b[32m-v\x1b[0m \x1b[32m-d\x1b[0m \x1b[32m-h\x1b[0m",
            False,
        ),
        # Overlapping regex matches
        (
            "aaabbb",
            [re.compile(r"aa"), re.compile(r"aaa")],
            "\x1b[32maaa\x1b[0mbbb",
            False,
        ),
        # Regex with special characters (already escaped in literal)
        (
            "Price: $10.99 and $5.50",
            re.compile(r"\$\d+\.\d+"),
            "Price: \x1b[32m$10.99\x1b[0m and \x1b[32m$5.50\x1b[0m",
            False,
        ),
        # Empty regex match (should not highlight)
        (
            "test string",
            re.compile(r"xyz"),
            "test string",
            False,
        ),
        # Case-insensitive regex
        (
            "HTML CSS JavaScript",
            re.compile(r"html|css"),
            "\x1b[32mHTML\x1b[0m \x1b[32mCSS\x1b[0m JavaScript",
            True,
        ),
        # Pre-compiled regex with flags
        (
            "HTML CSS JavaScript",
            re.compile(r"html|css", re.IGNORECASE),
            "\x1b[32mHTML\x1b[0m \x1b[32mCSS\x1b[0m JavaScript",
            False,
        ),
        # Complex regex patterns
        (
            "IP: 192.168.1.1 and 10.0.0.1",
            re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
            "IP: \x1b[32m192.168.1.1\x1b[0m and \x1b[32m10.0.0.1\x1b[0m",
            False,
        ),
        # Regex matching start/end anchors (should work within content)
        (
            "start middle end",
            re.compile(r"start|end"),
            "\x1b[32mstart\x1b[0m middle \x1b[32mend\x1b[0m",
            False,
        ),
    ),
)
def test_substring_highlighting(content, patterns, expected, ignore_case):
    assert (
        highlight(
            content,
            patterns,
            styling_func=theme.success,
            ignore_case=ignore_case,
        )
        == expected
    )


@pytest.mark.parametrize(
    "cmd_decorator, cmd_type",
    # Skip click extra's commands, as help option is already part of the default.
    command_decorators(no_extra=True, with_types=True),
)
@pytest.mark.parametrize("option_decorator", (help_option, help_option()))
def test_standalone_help_option(invoke, cmd_decorator, cmd_type, option_decorator):
    @cmd_decorator
    @option_decorator
    def standalone_help():
        echo("It works!")

    result = invoke(standalone_help, "--help")
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
    assert result.exit_code == 0
    assert not result.stderr
