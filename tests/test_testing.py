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
"""Test the testing utilities and the simulation of CLI execution."""

from __future__ import annotations

from pathlib import Path

import click

from click_extra import (
    ExtraCliRunner,
    Style,
    command,
    echo,
    pass_context,
    secho,
    style,
)


def test_real_fs():
    """Check a simple test is not caught into the CLI runner fixture which is
    encapsulating all filesystem access into temporary directory structure."""
    assert str(Path(__file__)).startswith(str(Path.cwd()))


def test_temporary_fs(extra_runner):
    """Check the CLI runner fixture properly encapsulated the filesystem in temporary
    directory."""
    assert not str(Path(__file__)).startswith(str(Path.cwd()))


def test_runner_output():
    @command
    def cli_output():
        echo("1 - stdout")
        echo("2 - stderr", err=True)
        echo("3 - stdout")
        echo("4 - stderr", err=True)

    runner_mix = ExtraCliRunner()
    result_mix = runner_mix.invoke(cli_output)

    assert result_mix.output == "1 - stdout\n2 - stderr\n3 - stdout\n4 - stderr\n"
    assert result_mix.stdout == "1 - stdout\n3 - stdout\n"
    assert result_mix.stderr == "2 - stderr\n4 - stderr\n"
    assert result_mix.exit_code == 0


@click.command
@pass_context
def run_cli1(ctx):
    """https://github.com/pallets/click/issues/2111."""
    echo(Style(fg="green")("echo()"))
    echo(Style(fg="green")("echo(color=None)"), color=None)
    echo(Style(fg="red")("echo(color=True) bypass invoke.color = False"), color=True)
    echo(Style(fg="green")("echo(color=False)"), color=False)

    secho("secho()", fg="green")
    secho("secho(color=None)", fg="green", color=None)
    secho("secho(color=True) bypass invoke.color = False", fg="red", color=True)
    secho("secho(color=False)", fg="green", color=False)

    print(style("print() bypass Click.", fg="blue"))

    echo(f"Context.color = {ctx.color!r}")
    echo(f"click.utils.should_strip_ansi = {click.utils.should_strip_ansi()!r}")


def check_default_colored_rendering(result):
    assert result.stdout.startswith(
        "\x1b[32mecho()\x1b[0m\n"
        "\x1b[32mecho(color=None)\x1b[0m\n"
        "\x1b[31mecho(color=True) bypass invoke.color = False\x1b[0m\n"
        "echo(color=False)\n"
        "\x1b[32msecho()\x1b[0m\n"
        "\x1b[32msecho(color=None)\x1b[0m\n"
        "\x1b[31msecho(color=True) bypass invoke.color = False\x1b[0m\n"
        "secho(color=False)\n"
        "\x1b[34mprint() bypass Click.\x1b[0m\n",
    )
    assert result.exit_code == 0


def check_default_uncolored_rendering(result):
    assert result.stdout.startswith(
        "echo()\n"
        "echo(color=None)\n"
        "\x1b[31mecho(color=True) bypass invoke.color = False\x1b[0m\n"
        "echo(color=False)\n"
        "secho()\n"
        "secho(color=None)\n"
        "\x1b[31msecho(color=True) bypass invoke.color = False\x1b[0m\n"
        "secho(color=False)\n"
        "\x1b[34mprint() bypass Click.\x1b[0m\n",
    )
    assert result.exit_code == 0


def check_forced_uncolored_rendering(result):
    assert result.stdout.startswith(
        "echo()\n"
        "echo(color=None)\n"
        "echo(color=True) bypass invoke.color = False\n"
        "echo(color=False)\n"
        "secho()\n"
        "secho(color=None)\n"
        "secho(color=True) bypass invoke.color = False\n"
        "secho(color=False)\n"
        "print() bypass Click.\n",
    )
    assert result.exit_code == 0


def test_invoke_optional_color(invoke):
    result = invoke(run_cli1, color=None)
    check_default_uncolored_rendering(result)
    assert result.stdout.endswith(
        "Context.color = None\nclick.utils.should_strip_ansi = True\n",
    )


def test_invoke_default_color(invoke):
    result = invoke(run_cli1)
    check_default_uncolored_rendering(result)
    assert result.stdout.endswith(
        "Context.color = None\nclick.utils.should_strip_ansi = True\n",
    )


def test_invoke_forced_color_stripping(invoke):
    result = invoke(run_cli1, color=False)
    check_forced_uncolored_rendering(result)
    assert result.stdout.endswith(
        "Context.color = None\nclick.utils.should_strip_ansi = True\n",
    )


def test_invoke_color_keep(invoke):
    result = invoke(run_cli1, color=True)
    check_default_colored_rendering(result)
    assert result.stdout.endswith(
        "Context.color = None\nclick.utils.should_strip_ansi = False\n",
    )


def test_invoke_color_forced(invoke):
    """Test colors are preserved while invoking, and forced to be rendered on
    Windows."""
    result = invoke(run_cli1, color="forced")
    check_default_colored_rendering(result)
    assert result.stdout.endswith(
        "Context.color = True\nclick.utils.should_strip_ansi = False\n",
    )


# --- Full-stack click-extra color tests ---


@command
@pass_context
def run_cli_extra(ctx):
    """CLI using click-extra's full decorator for color testing."""
    echo(Style(fg="green")("colored output"))
    echo(f"Context.color = {ctx.color!r}")


def test_extra_command_default_color():
    """With @command, ExtraContext defaults root color=True and ColorOption defaults
    True. Verify ctx.color=True and ANSI codes present in output."""
    runner = ExtraCliRunner()
    result = runner.invoke(run_cli_extra, color=True)
    assert result.exit_code == 0
    assert "\x1b[32mcolored output\x1b[0m" in result.stdout
    assert "Context.color = True" in result.stdout


def test_extra_command_no_color_flag():
    """Invoke with --no-color. Verify ctx.color=False and ANSI stripped from echo
    output."""
    runner = ExtraCliRunner()
    result = runner.invoke(run_cli_extra, "--no-color", color=True)
    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout
    assert "Context.color = False" in result.stdout


# --- force_color class attribute test ---


def test_force_color_attribute():
    """ExtraCliRunner.force_color=True overrides color parameter."""

    @click.command
    def simple_cli():
        echo(Style(fg="green")("styled"))

    runner = ExtraCliRunner()
    runner.force_color = True
    result = runner.invoke(simple_cli, color=None)
    assert result.exit_code == 0
    # force_color=True makes isolation_color=True, so ANSI codes are preserved.
    assert "\x1b[32mstyled\x1b[0m" in result.stdout


# --- NO_COLOR / FORCE_COLOR environment variable tests ---


def test_no_color_envvar():
    """NO_COLOR=1 env var causes ctx.color=False via ColorOption."""
    runner = ExtraCliRunner()
    result = runner.invoke(run_cli_extra, env={"NO_COLOR": "1"}, color=True)
    assert result.exit_code == 0
    assert "Context.color = False" in result.stdout


def test_force_color_envvar():
    """FORCE_COLOR=1 env var keeps ctx.color=True via ColorOption."""
    runner = ExtraCliRunner()
    result = runner.invoke(run_cli_extra, env={"FORCE_COLOR": "1"}, color=True)
    assert result.exit_code == 0
    assert "Context.color = True" in result.stdout


# --- should_strip_ansi / resolve_color_default tests ---


def test_should_strip_ansi_non_tty():
    """In a test runner (non-TTY), should_strip_ansi behaves based on color arg."""
    # No color arg: strips because stdin is not a TTY.
    assert click.utils.should_strip_ansi() is True
    # color=True: do not strip.
    assert click.utils.should_strip_ansi(color=True) is False
    # color=False: strip.
    assert click.utils.should_strip_ansi(color=False) is True


def test_resolve_color_default_no_context():
    """Outside any Click context, resolve_color_default returns None or passed value."""
    from click.globals import resolve_color_default

    assert resolve_color_default() is None
    assert resolve_color_default(True) is True
    assert resolve_color_default(False) is False
