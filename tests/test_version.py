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
"""Test the ``--version`` option.

.. todo::
    Test standalone scripts setting package name to filename and version to
    `None`.

.. todo::
    Test standalone script fetching version from ``__version__`` variable.
"""

from __future__ import annotations

import re

import click
import pytest
from boltons.strutils import strip_ansi
from pytest_cases import parametrize

from click_extra import ExtraVersionOption, Style, __version__, echo, pass_context
from click_extra.decorators import (
    color_option,
    extra_group,
    extra_version_option,
    verbosity_option,
)
from click_extra.pytest import (
    command_decorators,
    default_debug_colored_log_end,
    default_debug_colored_logging,
    default_debug_colored_version_details,
)

from .conftest import skip_windows_colors


@skip_windows_colors
@parametrize("cmd_decorator", command_decorators())
@parametrize("option_decorator", (extra_version_option, extra_version_option()))
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
@parametrize("cmd_decorator", command_decorators())
@parametrize("option_decorator", (extra_version_option, extra_version_option()))
def test_debug_output(invoke, cmd_decorator, option_decorator):
    @cmd_decorator
    @verbosity_option
    @option_decorator
    def debug_output():
        echo("It works!")

    result = invoke(debug_output, "--verbosity", "DEBUG", "--version", color=True)
    assert result.exit_code == 0

    assert re.fullmatch(
        (
            default_debug_colored_logging
            + default_debug_colored_version_details
            + r"\x1b\[97mdebug-output\x1b\[0m, "
            rf"version \x1b\[32m{re.escape(__version__)}\x1b\[0m\n"
            + default_debug_colored_log_end
        ),
        result.output,
    )


@skip_windows_colors
def test_set_version(invoke):
    @click.group
    @extra_version_option(version="1.2.3.4")
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
            "{prog_name}, version {version}",
            r"\x1b\[97mcolor-cli3\x1b\[0m, "
            rf"version \x1b\[32m{re.escape(__version__)}"
            r"\x1b\[0m\n",
        ),
        (
            "{prog_name}, version {version}\n{env_info}",
            r"\x1b\[97mcolor-cli3\x1b\[0m, "
            rf"version \x1b\[32m{re.escape(__version__)}"
            r"\x1b\[0m\n"
            r"\x1b\[90m{'.+'}"
            r"\x1b\[0m\n",
        ),
        (
            "{prog_name} v{version} - {package_name}",
            r"\x1b\[97mcolor-cli3\x1b\[0m "
            rf"v\x1b\[32m{re.escape(__version__)}"
            r"\x1b\[0m - "
            r"\x1b\[97mclick_extra"
            r"\x1b\[0m\n",
        ),
        (
            "{prog_name}, version {version} (Python {env_info[python][version]})",
            r"\x1b\[97mcolor-cli3\x1b\[0m, "
            rf"version \x1b\[32m{re.escape(__version__)}\x1b\[0m "
            r"\(Python \x1b\[90m3\.\d+\.\d+.+\x1b\[0m\)\n",
        ),
    ),
)
def test_custom_message(invoke, cmd_decorator, message, regex_stdout):
    @cmd_decorator
    @extra_version_option(message=message)
    def color_cli3():
        echo("It works!")

    result = invoke(color_cli3, "--version", color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert re.fullmatch(regex_stdout, result.output)


@parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_style_reset(invoke, cmd_decorator):
    @cmd_decorator
    @extra_version_option(
        message_style=None,
        version_style=None,
        prog_name_style=None,
    )
    def color_reset():
        pass

    result = invoke(color_reset, "--version", color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.output == strip_ansi(result.output)


@skip_windows_colors
@parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_custom_message_style(invoke, cmd_decorator):
    @cmd_decorator
    @extra_version_option(
        message="{prog_name} v{version} - {package_name} (latest)",
        message_style=Style(fg="cyan"),
        prog_name_style=Style(fg="green", bold=True),
        version_style=Style(fg="bright_yellow", bg="red"),
        package_name_style=Style(fg="bright_blue", italic=True),
    )
    def custom_style():
        pass

    result = invoke(custom_style, "--version", color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.output == (
        "\x1b[32m\x1b[1mcustom-style\x1b[0m\x1b[36m "
        f"v\x1b[0m\x1b[93m\x1b[41m{__version__}\x1b[0m\x1b[36m - "
        "\x1b[0m\x1b[94m\x1b[3mclick_extra\x1b[0m\x1b[36m (latest)\x1b[0m\n"
    )


@parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_context_meta(invoke, cmd_decorator):
    @cmd_decorator
    @extra_version_option
    @pass_context
    def version_metadata(ctx):
        for field in ExtraVersionOption.template_fields:
            value = ctx.meta[f"click_extra.{field}"]
            echo(f"{field} = {value}")

    result = invoke(version_metadata, color=True)
    assert result.exit_code == 0
    assert not result.stderr
    assert re.fullmatch(
        (
            r"module = <module 'click_extra\.testing' from '.+testing\.py'>\n"
            r"module_name = click_extra\.testing\n"
            r"module_file = .+testing\.py\n"
            rf"module_version = None\n"
            r"package_name = click_extra\n"
            rf"package_version = {__version__}\n"
            r"exec_name = click_extra\.testing\n"
            rf"version = {__version__}\n"
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
    @extra_version_option(version="2.1.9")
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
