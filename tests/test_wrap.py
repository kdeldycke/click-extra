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
"""Tests for the CLI wrapper feature."""

from __future__ import annotations

import click
import pytest

from click_extra.cli import demo
from click_extra.colorize import ExtraHelpColorsMixin
from click_extra.commands import ExtraContext
from click_extra.testing import ExtraCliRunner
from click_extra.wrap import (
    _PatchedCommand,
    _PatchedGroup,
    resolve_target,
    run,
    unpatch_click,
)

GREET_SCRIPT = (
    'import click\n'
    '\n'
    '@click.command()\n'
    '@click.option("--name", default="World", help="Name to greet.")\n'
    'def hello(name):\n'
    '    """Greet someone."""\n'
    '    click.echo(f"Hello, {name}")\n'
    '\n'
    'if __name__ == "__main__":\n'
    '    hello()\n'
)


@pytest.fixture(autouse=True)
def _restore_click():
    """Undo any monkey-patching after each test to prevent cross-contamination."""
    yield
    unpatch_click()


@pytest.fixture
def runner():
    """CLI runner for wrapper tests."""
    return ExtraCliRunner()


@pytest.fixture
def greet_script(tmp_path):
    """A minimal Click CLI script for wrapping tests."""
    script = tmp_path / "greet.py"
    script.write_text(GREET_SCRIPT)
    return str(script)


# -- Patched classes -----------------------------------------------------------


@pytest.mark.parametrize(
    "cls, base",
    [
        (_PatchedCommand, click.Command),
        (_PatchedGroup, click.Group),
    ],
)
def test_patched_class_inherits_click(cls, base):
    assert issubclass(cls, base)


@pytest.mark.parametrize("cls", [_PatchedCommand, _PatchedGroup])
def test_patched_class_has_mixin(cls):
    assert issubclass(cls, ExtraHelpColorsMixin)


@pytest.mark.parametrize("cls", [_PatchedCommand, _PatchedGroup])
def test_patched_class_context(cls):
    assert cls.context_class is ExtraContext


def test_patched_command_no_extra_params():
    """Patched commands carry no default_extra_params."""
    cmd = _PatchedCommand(name="test", callback=lambda: None)
    option_names = {
        opt
        for p in cmd.params
        if isinstance(p, click.Option)
        for opt in p.opts
    }
    for forbidden in ("--config", "--verbose", "--verbosity", "--timer"):
        assert forbidden not in option_names


# -- Target resolution ---------------------------------------------------------


@pytest.mark.parametrize(
    "script, expected_module, expected_func",
    [
        ("click-extra", "click_extra.__main__", "main"),
        ("json:tool", "json", "tool"),
        ("json", "json", ""),
    ],
)
def test_resolve_target(script, expected_module, expected_func):
    module_path, function_name = resolve_target(script)
    assert module_path == expected_module
    assert function_name == expected_func


def test_resolve_py_file(tmp_path):
    script = tmp_path / "hello.py"
    script.write_text("print('hello')")
    module_path, function_name = resolve_target(str(script))
    assert module_path == str(script)
    assert function_name == ""


def test_resolve_not_found():
    with pytest.raises(click.ClickException, match="Cannot resolve"):
        resolve_target("nonexistent_package_xyz_12345")


# -- run subcommand ------------------------------------------------------------


def test_run_help(runner):
    result = runner.invoke(run, ["--help"])
    assert result.exit_code == 0
    assert "Apply Click Extra help colorization" in result.output


def test_run_no_args_shows_help(runner):
    result = runner.invoke(run, [])
    assert result.exit_code == 0
    assert "Apply Click Extra help colorization" in result.output


def test_run_colorizes_target(runner, greet_script):
    """A plain Click CLI wrapped by the run subcommand gets colorized help."""
    result = runner.invoke(run, [greet_script, "--help"], color=True)
    assert result.exit_code == 0
    assert "Greet someone." in result.output
    # ANSI escape codes should be present.
    assert "\x1b[" in result.output


def test_run_no_color(runner, greet_script):
    """Parent --no-color propagates through ctx.color to disable ANSI."""
    result = runner.invoke(run, ["--theme", "dark", greet_script, "--help"])
    assert result.exit_code == 0
    assert "Greet someone." in result.output


def test_run_passes_args_through(runner, greet_script):
    """Arguments after the script name are forwarded to the target CLI."""
    result = runner.invoke(run, [greet_script, "--name", "Alice"])
    assert result.exit_code == 0
    assert "Hello, Alice" in result.output


def test_run_unresolvable_target(runner):
    result = runner.invoke(run, ["nonexistent_xyz_12345"])
    assert result.exit_code != 0
    assert "Cannot resolve" in result.output


# -- WrapperGroup default-to-run -----------------------------------------------


def test_group_defaults_to_run(runner, greet_script):
    """Unknown subcommand names fall through to the run subcommand."""
    result = runner.invoke(demo, [greet_script, "--help"], color=True)
    assert result.exit_code == 0
    assert "Greet someone." in result.output


def test_group_known_subcommands_still_work(runner):
    """Explicit subcommands like render-matrix are not affected."""
    result = runner.invoke(demo, ["render-matrix", "--help"])
    assert result.exit_code == 0
    assert "Render a color or style matrix" in result.output
