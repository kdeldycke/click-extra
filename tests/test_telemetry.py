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

from textwrap import dedent

from pytest_cases import parametrize

from click_extra import command, echo, pass_context, telemetry_option
from click_extra.pytest import command_decorators


@parametrize("cmd_decorator", command_decorators(no_groups=True, no_extra=True))
@parametrize("option_decorator", (telemetry_option, telemetry_option()))
def test_standalone_telemetry_option(invoke, cmd_decorator, option_decorator):
    @cmd_decorator
    @option_decorator
    @pass_context
    def standalone_telemetry(ctx):
        echo("It works!")
        echo(f"Telemetry value: {ctx.telemetry}")

    result = invoke(standalone_telemetry, "--help")
    assert result.exit_code == 0
    assert not result.stderr

    assert result.stdout == dedent(
        """\
        Usage: standalone-telemetry [OPTIONS]

        Options:
          --telemetry / --no-telemetry  Collect telemetry and usage data.  [env var:
                                        DO_NOT_TRACK]
          --help                        Show this message and exit.
        """,
    )

    result = invoke(standalone_telemetry, "--telemetry")
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == "It works!\nTelemetry value: True\n"

    result = invoke(standalone_telemetry, "--no-telemetry")
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == "It works!\nTelemetry value: False\n"


def test_multiple_envvars(invoke):
    @command(context_settings={"auto_envvar_prefix": "yo", "show_default": True})
    @telemetry_option
    @pass_context
    def standalone_telemetry(ctx):
        echo("It works!")
        echo(f"Telemetry value: {ctx.telemetry}")

    result = invoke(standalone_telemetry, "--help")
    assert result.exit_code == 0
    assert not result.stderr

    assert result.stdout == dedent(
        """\
        Usage: standalone-telemetry [OPTIONS]

        Options:
          --telemetry / --no-telemetry  Collect telemetry and usage data.  [env var:
                                        DO_NOT_TRACK; default: no-telemetry]
          --help                        Show this message and exit.
        """,
    )

    result = invoke(standalone_telemetry, env={"DO_NOT_TRACK": "1"})
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == "It works!\nTelemetry value: True\n"
