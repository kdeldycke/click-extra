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

from __future__ import annotations

import re
import sys

import click
import pytest
from click import echo
from cloup import Style
from pytest_cases import parametrize

from ..colorize import color_option
from ..commands import extra_group
from ..version import version_option
from .conftest import command_decorators, skip_windows_colors


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
