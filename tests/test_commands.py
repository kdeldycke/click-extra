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

import ast
import inspect
import re
from pathlib import Path
from textwrap import dedent

import click
import cloup
import pytest
from pytest_cases import fixture, parametrize

import click_extra
from click_extra import echo, option, option_group, pass_context
from click_extra.decorators import extra_command, extra_group
from click_extra.pytest import (
    command_decorators,
    default_debug_uncolored_log_end,
    default_debug_uncolored_log_start,
    default_options_colored_help,
    default_options_uncolored_help,
)

from .conftest import skip_windows_colors


def test_module_root_declarations():
    def fetch_root_members(module):
        """Fetch all members exposed at the module root."""
        members = set()
        for name, member in inspect.getmembers(module):
            # Exclude private members.
            if name.startswith("_"):
                continue
            # Exclude automatic imports of submodules as we inspect __init__'s content
            # only.
            if inspect.ismodule(member):
                continue
            members.add(name)
        return members

    click_members = fetch_root_members(click)

    cloup_members = {m for m in cloup.__all__ if not m.startswith("_")}

    tree = ast.parse(Path(inspect.getfile(click_extra)).read_bytes())
    click_extra_members = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if target.id == "__all__":
                    for element in node.value.elts:
                        click_extra_members.append(element.s)

    assert click_members <= set(click_extra_members)
    assert cloup_members <= set(click_extra_members)

    expected_members = sorted(
        click_members.union(cloup_members).union(click_extra_members),
        key=lambda m: (m.lower(), m),
    )
    assert expected_members == click_extra_members


@fixture
def all_command_cli():
    """A CLI that is mixing all variations and flavors of subcommands."""

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
            rf"{default_debug_uncolored_log_start}"
            rf"{default_debug_uncolored_log_end}"
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
    """See: https://click.palletsprojects.com/en/8.0.x/advanced/#callback-evaluation-
    order.
    """
    result = invoke(all_command_cli, "--help", params, color=False)
    assert result.exit_code == 0
    assert re.fullmatch(help_screen, result.stdout)
    assert "It works!" not in result.stdout
    assert not result.stderr


@skip_windows_colors
@pytest.mark.parametrize("cmd_id", ("default", "click-extra", "cloup", "click"))
@pytest.mark.parametrize("param", ("-h", "--help"))
def test_subcommand_help(invoke, all_command_cli, cmd_id, param):
    result = invoke(all_command_cli, f"{cmd_id}-subcommand", param)
    assert result.exit_code == 0
    assert not result.stderr

    colored_help_header = (
        r"It works!\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mUsage:\x1b\[0m "
        rf"\x1b\[97mcommand-cli1 {cmd_id}-subcommand\x1b\[0m"
        r" \x1b\[36m\x1b\[2m\[OPTIONS\]\x1b\[0m\n"
        r"\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mOptions:\x1b\[0m\n"
    )

    # Extra sucommands are colored and include all extra options.
    if cmd_id == "click-extra":
        assert re.fullmatch(
            rf"{colored_help_header}{default_options_colored_help}",
            result.stdout,
        )

    # Default subcommand inherits from extra family and is colored, but does not include
    # extra options.
    elif cmd_id == "default":
        assert re.fullmatch(
            (
                rf"{colored_help_header}"
                r"  \x1b\[36m-h\x1b\[0m, \x1b\[36m--help\x1b\[0m"
                r"  Show this message and exit.\n"
            ),
            result.stdout,
        )

    # Non-extra subcommands are not colored.
    else:
        assert result.stdout == dedent(
            f"""\
            It works!
            Usage: command-cli1 {cmd_id}-subcommand [OPTIONS]

            Options:
              -h, --help  Show this message and exit.
            """,
        )


@pytest.mark.parametrize("cmd_id", ("default", "click-extra", "cloup", "click"))
def test_subcommand_execution(invoke, all_command_cli, cmd_id):
    result = invoke(all_command_cli, f"{cmd_id}-subcommand", color=False)
    assert result.exit_code == 0
    assert result.stdout == dedent(
        f"""\
        It works!
        Run {cmd_id} subcommand...
        """,
    )
    assert not result.stderr


def test_integrated_version_value(invoke, all_command_cli):
    result = invoke(all_command_cli, "--version", color=False)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == "command-cli1, version 2021.10.08\n"


@skip_windows_colors
@parametrize(
    "cmd_decorator",
    command_decorators(
        no_click=True,
        no_cloup=True,
        no_redefined=True,
        with_parenthesis=False,
    ),
)
@pytest.mark.parametrize("param", ("-h", "--help"))
def test_colored_bare_help(invoke, cmd_decorator, param):
    """Extra decorators are always colored.

    Even when stripped of their default parameters, as reported in:
    https://github.com/kdeldycke/click-extra/issues/534
    https://github.com/kdeldycke/click-extra/pull/543
    """

    @cmd_decorator(params=None)
    def bare_cli():
        pass

    result = invoke(bare_cli, param)
    assert result.exit_code == 0
    assert not result.stderr
    assert (
        "\n"
        "\x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m\n"
        "  \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m  Show this message and exit.\n"
    ) in result.stdout


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
    assert result.stdout == dedent(
        """\
        Usage: cli [OPTIONS] COMMAND [ARGS]...

        Options:
          --help  Show this message and exit.

        Commands:
          bar  Bar subcommand.
          foo
        """,
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

    # Remove colors to simplify output comparison.
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


@pytest.mark.parametrize(
    ("cmd_decorator", "ctx_settings", "expected_help"),
    (
        # Click does not show all envvar in the help screen by default, unless
        # specifficaly set on an option.
        (
            click.command,
            {},
            "  --flag1\n  --flag2  [env var: custom2]\n  --flag3\n",
        ),
        # Click Extra defaults to let each option choose its own show_envvar value.
        (
            extra_command,
            {},
            "  --flag1\n"
            "  --flag2                   [env var: custom2, CLI_FLAG2]\n"
            "  --flag3\n",
        ),
        # Click Extra allow bypassing its global show_envvar setting.
        (
            extra_command,
            {"show_envvar": None},
            "  --flag1\n"
            "  --flag2                   [env var: custom2, CLI_FLAG2]\n"
            "  --flag3\n",
        ),
        # Click Extra force the show_envvar value on all options.
        (
            extra_command,
            {"show_envvar": True},
            "  --flag1                   [env var: custom1, CLI_FLAG1]\n"
            "  --flag2                   [env var: custom2, CLI_FLAG2]\n"
            "  --flag3                   [env var: custom3, CLI_FLAG3]\n",
        ),
        (
            extra_command,
            {"show_envvar": False},
            "  --flag1\n  --flag2\n  --flag3\n",
        ),
    ),
)
def test_show_envvar_parameter(invoke, cmd_decorator, ctx_settings, expected_help):
    @cmd_decorator(context_settings=ctx_settings)
    @option("--flag1", is_flag=True, envvar=["custom1"])
    @option("--flag2", is_flag=True, envvar=["custom2"], show_envvar=True)
    @option("--flag3", is_flag=True, envvar=["custom3"], show_envvar=False)
    def cli():
        pass

    # Remove colors to simplify output comparison.
    result = invoke(cli, "--help", color=False)
    assert result.exit_code == 0
    assert not result.stderr
    assert expected_help in result.stdout


def test_raw_args(invoke):
    """Raw args are expected to be scoped in subcommands."""

    @extra_group
    @option("--dummy-flag/--no-flag")
    @pass_context
    def my_cli(ctx, dummy_flag):
        echo("-- Group output --")
        echo(f"dummy_flag is {dummy_flag!r}")
        echo(f"Raw parameters: {ctx.meta.get('click_extra.raw_args', [])}")

    @my_cli.command()
    @pass_context
    @option("--int-param", type=int, default=10)
    def subcommand(ctx, int_param):
        echo("-- Subcommand output --")
        echo(f"int_parameter is {int_param!r}")
        echo(f"Raw parameters: {ctx.meta.get('click_extra.raw_args', [])}")

    result = invoke(my_cli, "--dummy-flag", "subcommand", "--int-param", "33")
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == dedent(
        """\
        -- Group output --
        dummy_flag is True
        Raw parameters: ['--dummy-flag', 'subcommand', '--int-param', '33']
        -- Subcommand output --
        int_parameter is 33
        Raw parameters: ['--int-param', '33']
        """,
    )
