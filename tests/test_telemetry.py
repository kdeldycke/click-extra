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

import os

import click
import cloup
import pytest

from click_extra import command, echo, pass_context, telemetry_option


@pytest.mark.parametrize(
    ("cmd_decorator", "telemetry_help"),
    (
        # Click and Cloup do not show the auto-generated envvar in the help screen.
        (
            click.command,
            "  --telemetry / --no-telemetry  Collect telemetry and usage data.  [env var:\n"
            "                                DO_NOT_TRACK]\n",
        ),
        (
            click.command(),
            "  --telemetry / --no-telemetry  Collect telemetry and usage data.  [env var:\n"
            "                                DO_NOT_TRACK]\n",
        ),
        (
            cloup.command(),
            "  --telemetry / --no-telemetry  Collect telemetry and usage data.  [env var:\n"
            "                                DO_NOT_TRACK]\n",
        ),
        # Click Extra always adds the auto-generated envvar to the help screen
        # (and show the defaults).
        (
            command,
            "  --telemetry / --no-telemetry  Collect telemetry and usage data.  [env var:\n"
            "                                DO_NOT_TRACK, CLI_TELEMETRY; default: no-\n"
            "                                telemetry]\n",
        ),
    ),
)
@pytest.mark.parametrize("option_decorator", (telemetry_option, telemetry_option()))
def test_standalone_telemetry_option(
    invoke, cmd_decorator, telemetry_help, option_decorator
):
    @cmd_decorator
    @option_decorator
    @pass_context
    def cli(ctx):
        echo("It works!")
        echo(f"Telemetry value: {ctx.telemetry}")

    result = invoke(cli, "--help", color=False)
    assert telemetry_help in result.stdout
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(cli, "--telemetry")
    assert result.stdout == "It works!\nTelemetry value: True\n"
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(cli, "--no-telemetry")
    assert result.stdout == "It works!\nTelemetry value: False\n"
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("cmd_decorator", "telemetry_help"),
    (
        # Click and Cloup do not show the auto-generated envvar in the help screen.
        (
            click.command,
            "  --telemetry / --no-telemetry  Collect telemetry and usage data.  [env var:\n"
            "                                DO_NOT_TRACK; default: no-telemetry]\n",
        ),
        (
            cloup.command,
            "  --telemetry / --no-telemetry  Collect telemetry and usage data.  [env var:\n"
            "                                DO_NOT_TRACK; default: no-telemetry]\n",
        ),
        # Click Extra always adds the auto-generated envvar to the help screen
        # (and show the defaults).
        (
            command,
            "  --telemetry / --no-telemetry  Collect telemetry and usage data.  [env var:\n"
            "                                DO_NOT_TRACK, "
            + ("YO_TELEMETRY" if os.name == "nt" else "yo_TELEMETRY")
            + "; default: no-\n"
            "                                telemetry]\n",
        ),
    ),
)
def test_multiple_envvars(invoke, cmd_decorator, telemetry_help):
    @cmd_decorator(context_settings={"auto_envvar_prefix": "yo", "show_default": True})
    @telemetry_option
    @pass_context
    def standalone_telemetry(ctx):
        echo("It works!")
        echo(f"Telemetry value: {ctx.telemetry}")

    result = invoke(standalone_telemetry, "--help", color=False)
    assert telemetry_help in result.stdout
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(standalone_telemetry, env={"DO_NOT_TRACK": "1"})
    assert result.stdout == "It works!\nTelemetry value: True\n"
    assert not result.stderr
    assert result.exit_code == 0
