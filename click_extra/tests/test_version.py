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

import click
import pytest
from boltons.strutils import strip_ansi
from pytest_cases import parametrize

from click_extra import Style, __version__, echo, pass_context
from click_extra.decorators import color_option, extra_group, version_option

from .conftest import command_decorators, skip_windows_colors


@skip_windows_colors
@parametrize("cmd_decorator", command_decorators())
@parametrize("option_decorator", (version_option, version_option()))
def test_standalone_version_option(invoke, cmd_decorator, option_decorator):
    @cmd_decorator
    @option_decorator
    def standalone_option():
        echo("It works!")

    result = invoke(standalone_option, "--version", color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.output == (
        "\x1b[97mstandalone-option\x1b[0m, "
        f"version \x1b[32m{__version__}"
        "\x1b[0m\n"
    )


@skip_windows_colors
def test_set_version(invoke):
    @click.group
    @version_option(version="1.2.3.4")
    def color_cli2():
        echo("It works!")

    # Test default coloring.
    result = invoke(color_cli2, "--version", color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == (
        "\x1b[97mcolor-cli2\x1b[0m, version \x1b[32m1.2.3.4\x1b[0m\n"
    )


@skip_windows_colors
@parametrize("cmd_decorator", command_decorators(no_groups=True))
@parametrize(
    "message, regex_stdout",
    (
        (
            "%(prog_name)s, version %(version)s",
            r"\x1b\[97mcolor-cli3\x1b\[0m, "
            rf"version \x1b\[32m{re.escape(__version__)}"
            r"\x1b\[0m\n",
        ),
        (
            "%(prog_name)s, version %(version)s\n%(env_info)s",
            r"\x1b\[97mcolor-cli3\x1b\[0m, "
            rf"version \x1b\[32m{re.escape(__version__)}"
            r"\x1b\[0m\n"
            r"\x1b\[90m{'.+'}"
            r"\x1b\[0m\n",
        ),
        (
            "%(prog_name)s v%(version)s - %(package_name)s",
            r"\x1b\[97mcolor-cli3\x1b\[0m "
            rf"v\x1b\[32m{re.escape(__version__)}"
            r"\x1b\[0m - "
            r"\x1b\[97mclick_extra"
            r"\x1b\[0m\n",
        ),
    ),
)
def test_custom_message(invoke, cmd_decorator, message, regex_stdout):
    @cmd_decorator
    @version_option(message=message)
    def color_cli3():
        echo("It works!")

    result = invoke(color_cli3, "--version", color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert re.fullmatch(regex_stdout, result.output)


@parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_style_reset(invoke, cmd_decorator):
    @cmd_decorator
    @version_option(
        version_style=None,
        package_name_style=None,
        prog_name_style=None,
        env_info_style=None,
        message_style=None,
    )
    def color_reset():
        pass

    result = invoke(color_reset, "--version", color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.output == strip_ansi(result.output)


@parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_context_meta(invoke, cmd_decorator):
    @cmd_decorator
    @version_option
    @pass_context
    def version_metadata(ctx):
        for var in ("version", "package_name", "prog_name", "env_info"):
            value = ctx.meta[f"click_extra.{var}"]
            echo(f"{var} = {value}")

    result = invoke(version_metadata, color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert re.fullmatch(
        (
            rf"version = {__version__}\n"
            r"package_name = click_extra\n"
            r"prog_name = version-metadata\n"
            r"env_info = {'.+'}\n"
        ),
        result.output,
    )
    assert result.output == strip_ansi(result.output)


@skip_windows_colors
@pytest.mark.parametrize(
    "params",
    (None, "--help", "blah", ("--config", "random.toml")),
)
def test_integrated_version_option_precedence(invoke, params):
    @extra_group(version="1.2.3.4")
    def color_cli4():
        echo("It works!")

    result = invoke(color_cli4, "--version", params, color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == (
        "\x1b[97mcolor-cli4\x1b[0m, version \x1b[32m1.2.3.4\x1b[0m\n"
    )


@skip_windows_colors
def test_color_option_precedence(invoke):
    """--no-color has an effect on --version, if placed in the right order.

    Eager parameters are evaluated in the order as they were provided on the command
    line by the user as expleined in:
    https://click.palletsprojects.com/en/8.0.x/advanced/#callback-evaluation-order

    .. todo::

        Maybe have the possibility to tweak CLI callback evaluation order so we can
        let the user to have the NO_COLOR env set to allow for color-less ``--version``
        output.
    """

    @click.command
    @color_option
    @version_option(version="2.1.9")
    def color_cli6():
        echo(Style(fg="yellow")("It works!"))

    result = invoke(color_cli6, "--no-color", "--version", "command1", color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == "color-cli6, version 2.1.9\n"

    result = invoke(color_cli6, "--version", "--no-color", "command1", color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == (
        "\x1b[97mcolor-cli6\x1b[0m, version \x1b[32m2.1.9\x1b[0m\n"
    )
