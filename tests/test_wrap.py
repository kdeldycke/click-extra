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

from pathlib import Path

import click
import pytest

from click_extra.cli import demo
from click_extra.colorize import ExtraHelpColorsMixin
from click_extra.commands import ColorizedCommand, ColorizedGroup, ExtraContext
from click_extra.testing import ExtraCliRunner
from click_extra.wrap import (
    _config_args_for_target,
    resolve_target,
    unpatch_click,
    wrap,
)

GREET_SCRIPT = (
    "import click\n"
    "\n"
    "@click.command()\n"
    '@click.option("--name", default="World", help="Name to greet.")\n'
    "def hello(name):\n"
    '    """Greet someone."""\n'
    '    click.echo(f"Hello, {name}")\n'
    "\n"
    'if __name__ == "__main__":\n'
    "    hello()\n"
)
"""Plain ``@click.command()`` script: patched via decorator defaults."""

CUSTOM_CLS_SCRIPT = (
    "import click\n"
    "\n"
    "class RecipeGroup(click.Group):\n"
    '    """Custom group like Flask\'s FlaskGroup."""\n'
    "\n"
    "@click.command(cls=RecipeGroup)\n"
    "def kitchen():\n"
    '    """Manage recipes and ingredients."""\n'
    "\n"
    "@kitchen.command()\n"
    '@click.option("--servings", default=4, help="Number of servings.")\n'
    "def bake(servings):\n"
    '    """Bake a cake."""\n'
    '    click.echo(f"Baking for {servings}")\n'
    "\n"
    'if __name__ == "__main__":\n'
    "    kitchen()\n"
)
"""Script with explicit ``cls=RecipeGroup``: patched via method patching."""

MULTI_OPTION_SCRIPT = (
    "import click\n"
    "\n"
    "@click.command()\n"
    '@click.option("--city", default="Paris", help="City name.")\n'
    '@click.option("--unit", default="celsius", help="Temperature unit.")\n'
    '@click.option("--verbose", is_flag=True, help="Show details.")\n'
    "def weather(city, unit, verbose):\n"
    '    """Check the weather."""\n'
    '    msg = f"{city}: 22 {unit}"\n'
    "    if verbose:\n"
    '        msg += " (detailed)"\n'
    "    click.echo(msg)\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    weather()\n"
)
"""Script with multiple options for config passthrough tests."""


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


@pytest.fixture
def custom_cls_script(tmp_path):
    """A Click CLI with explicit ``cls=CustomGroup`` (like Flask's FlaskGroup)."""
    script = tmp_path / "kitchen.py"
    script.write_text(CUSTOM_CLS_SCRIPT)
    return str(script)


@pytest.fixture
def weather_script(tmp_path):
    """A Click CLI with multiple options for config tests."""
    script = tmp_path / "weather.py"
    script.write_text(MULTI_OPTION_SCRIPT)
    return str(script)


@pytest.fixture
def create_config(tmp_path):
    """Produce a temporary configuration file."""

    def _create_config(filename, content):
        config_path = tmp_path / filename
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(content, encoding="utf-8")
        return config_path

    return _create_config


# -- Patched classes -----------------------------------------------------------


@pytest.mark.parametrize(
    "cls, base",
    [
        (ColorizedCommand, click.Command),
        (ColorizedGroup, click.Group),
    ],
)
def test_patched_class_inherits_click(cls, base):
    assert issubclass(cls, base)


@pytest.mark.parametrize("cls", [ColorizedCommand, ColorizedGroup])
def test_patched_class_has_mixin(cls):
    assert issubclass(cls, ExtraHelpColorsMixin)


@pytest.mark.parametrize("cls", [ColorizedCommand, ColorizedGroup])
def test_patched_class_context(cls):
    assert cls.context_class is ExtraContext


def test_patched_command_no_extra_params():
    """Patched commands carry no default_extra_params."""
    cmd = ColorizedCommand(name="test", callback=lambda: None)
    option_names = {
        opt for p in cmd.params if isinstance(p, click.Option) for opt in p.opts
    }
    for forbidden in ("--config", "--verbose", "--verbosity", "--timer"):
        assert forbidden not in option_names


# -- Target resolution ---------------------------------------------------------


@pytest.mark.parametrize(
    "script, expected_module, expected_func",
    [
        ("click-extra", "click_extra.__main__", "main"),
        ("json:tool", "json", "tool"),
        ("os.path:join", "os.path", "join"),
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


def test_resolve_py_file_missing(tmp_path):
    """A .py path that doesn't exist falls through to module resolution."""
    with pytest.raises(click.ClickException, match="Cannot resolve"):
        resolve_target(str(tmp_path / "nonexistent.py"))


@pytest.mark.parametrize(
    "script",
    [
        "nonexistent_package_xyz_12345",
        "no-such-entry-point-xyz",
        "",
    ],
)
def test_resolve_not_found(script):
    if not script:
        # Empty string: find_spec raises ValueError.
        with pytest.raises((click.ClickException, ValueError)):
            resolve_target(script)
    else:
        with pytest.raises(click.ClickException, match="Cannot resolve"):
            resolve_target(script)


# -- wrap subcommand -----------------------------------------------------------


@pytest.mark.parametrize(
    "args, expected",
    [
        (["--help"], "Apply Click Extra help colorization"),
        ([], "Apply Click Extra help colorization"),
    ],
)
def test_wrap_self(runner, args, expected):
    result = runner.invoke(wrap, args)
    assert result.exit_code == 0
    assert expected in result.output


@pytest.mark.parametrize(
    "script_fixture, target_args, expected_text",
    [
        ("greet_script", ["--help"], "Greet someone."),
        ("greet_script", ["--name", "Alice"], "Hello, Alice"),
        ("custom_cls_script", ["--help"], "Manage recipes and ingredients."),
        ("custom_cls_script", ["bake", "--help"], "Bake a cake."),
        ("custom_cls_script", ["bake", "--servings", "8"], "Baking for 8"),
    ],
)
def test_run_invokes_target(
    runner,
    script_fixture,
    target_args,
    expected_text,
    request,
):
    """The run subcommand forwards arguments to the target CLI."""
    script = request.getfixturevalue(script_fixture)
    result = runner.invoke(wrap, [script, *target_args])
    assert result.exit_code == 0
    assert expected_text in result.output


@pytest.mark.parametrize(
    "script_fixture, target_args",
    [
        ("greet_script", ["--help"]),
        ("custom_cls_script", ["--help"]),
        ("custom_cls_script", ["bake", "--help"]),
    ],
)
def test_run_colorizes(runner, script_fixture, target_args, request):
    """Help output contains ANSI escape codes."""
    script = request.getfixturevalue(script_fixture)
    result = runner.invoke(wrap, [script, *target_args], color=True)
    assert result.exit_code == 0
    assert "\x1b[" in result.output


def test_run_highlights_keywords_with_custom_cls(runner, custom_cls_script):
    """Options and subcommands are individually styled, not just headings."""
    result = runner.invoke(wrap, [custom_cls_script, "--help"], color=True)
    assert result.exit_code == 0
    assert "\x1b[36m--help\x1b[0m" in result.output
    assert "\x1b[36mbake\x1b[0m" in result.output


def test_run_unresolvable_target(runner):
    result = runner.invoke(wrap, ["nonexistent_xyz_12345"])
    assert result.exit_code != 0
    assert "Cannot resolve" in result.output


# -- WrapperGroup default-to-run -----------------------------------------------


@pytest.mark.parametrize(
    "args, expected",
    [
        # Unknown name falls through to wrap.
        pytest.param(
            ["--help"],
            "Greet someone.",
            id="implicit-wrap",
        ),
        # Explicit wrap subcommand.
        pytest.param(
            ["wrap", "--help"],
            "Greet someone.",
            id="explicit-wrap",
        ),
        # run alias.
        pytest.param(
            ["run", "--help"],
            "Greet someone.",
            id="run-alias",
        ),
    ],
)
def test_group_dispatches_to_wrap(runner, greet_script, args, expected):
    """All invocation forms reach the target CLI."""
    full_args = [args[0]]
    if args[0] in ("run", "wrap"):
        full_args.append(greet_script)
        full_args.extend(args[1:])
    else:
        full_args = [greet_script, *args]
    result = runner.invoke(demo, full_args, color=True)
    assert result.exit_code == 0
    assert expected in result.output


@pytest.mark.parametrize(
    "group_opts",
    [
        ["--time"],
        ["--verbosity", "DEBUG"],
        ["--no-color"],
        ["--color"],
    ],
)
def test_group_options_work_with_wrap(runner, greet_script, group_opts):
    """Default ExtraGroup options are accepted alongside the wrap subcommand."""
    result = runner.invoke(
        demo,
        [*group_opts, "wrap", greet_script, "--help"],
    )
    assert result.exit_code == 0
    assert "Greet someone." in result.output


@pytest.mark.parametrize(
    "subcommand",
    ["gradient", "palette", "8color", "colors", "styles"],
)
def test_group_known_subcommands_not_wrapped(runner, subcommand):
    """Known demo subcommands are dispatched directly, not to wrap."""
    result = runner.invoke(demo, [subcommand, "--help"])
    assert result.exit_code == 0


# -- Config integration --------------------------------------------------------


def test_config_verbosity(runner, greet_script, create_config):
    """``verbosity = "DEBUG"`` in pyproject.toml activates debug logging."""
    conf = create_config(
        "pyproject.toml",
        '[tool.click-extra]\nverbosity = "DEBUG"\n',
    )
    result = runner.invoke(
        demo,
        ["--config", str(conf), "wrap", greet_script, "--help"],
    )
    assert result.exit_code == 0
    assert "Greet someone." in result.output
    assert "DEBUG" in (result.output + (result.stderr or ""))


def test_config_group_theme(runner, greet_script, create_config):
    """A ``[tool.click-extra]`` ``theme`` key sets the help-screen theme."""
    conf = create_config(
        "pyproject.toml",
        '[tool.click-extra]\ntheme = "light"\n',
    )
    result = runner.invoke(
        demo,
        ["--config", str(conf), "wrap", greet_script, "--help"],
        color=True,
    )
    assert result.exit_code == 0
    assert "Greet someone." in result.output


# -- Config passthrough to target ----------------------------------------------


def test_config_target_string(runner, greet_script, create_config):
    """A string config value is forwarded as ``--key value``."""
    conf = create_config(
        "pyproject.toml",
        f'[tool.click-extra.wrap."{Path(greet_script).as_posix()}"]\nname = "Alice"\n',
    )
    result = runner.invoke(
        demo,
        ["--config", str(conf), "wrap", greet_script],
    )
    assert result.exit_code == 0
    assert "Hello, Alice" in result.output


def test_config_target_bool_true(runner, weather_script, create_config):
    """A ``true`` config value is forwarded as ``--flag``."""
    conf = create_config(
        "pyproject.toml",
        f'[tool.click-extra.wrap."{Path(weather_script).as_posix()}"]\nverbose = true\n',
    )
    result = runner.invoke(
        demo,
        ["--config", str(conf), "wrap", weather_script],
    )
    assert result.exit_code == 0
    assert "(detailed)" in result.output


def test_config_target_bool_false_is_noop(runner, weather_script, create_config):
    """A ``false`` config value is skipped: the flag is simply not passed."""
    conf = create_config(
        "pyproject.toml",
        f'[tool.click-extra.wrap."{Path(weather_script).as_posix()}"]\nverbose = false\n',
    )
    result = runner.invoke(
        demo,
        ["--config", str(conf), "wrap", weather_script],
    )
    assert result.exit_code == 0
    # verbose defaults to false anyway, so output has no "(detailed)".
    assert "(detailed)" not in result.output


def test_config_target_multiple_keys(runner, weather_script, create_config):
    """Multiple config keys are all forwarded."""
    conf = create_config(
        "pyproject.toml",
        f'[tool.click-extra.wrap."{Path(weather_script).as_posix()}"]\n'
        f'city = "Tokyo"\n'
        f'unit = "fahrenheit"\n',
    )
    result = runner.invoke(
        demo,
        ["--config", str(conf), "wrap", weather_script],
    )
    assert result.exit_code == 0
    assert "Tokyo" in result.output
    assert "fahrenheit" in result.output


def test_config_target_cli_overrides(runner, greet_script, create_config):
    """Explicit CLI args override config target defaults."""
    conf = create_config(
        "pyproject.toml",
        f'[tool.click-extra.wrap."{Path(greet_script).as_posix()}"]\nname = "Alice"\n',
    )
    result = runner.invoke(
        demo,
        ["--config", str(conf), "wrap", greet_script, "--name", "Bob"],
    )
    assert result.exit_code == 0
    assert "Hello, Bob" in result.output


def test_config_target_wrong_section_ignored(
    runner,
    greet_script,
    create_config,
):
    """Config for a different script name has no effect."""
    conf = create_config(
        "pyproject.toml",
        '[tool.click-extra.wrap.other-cli]\nname = "Alice"\n',
    )
    result = runner.invoke(
        demo,
        ["--config", str(conf), "wrap", greet_script],
    )
    assert result.exit_code == 0
    assert "Hello, World" in result.output


def test_config_target_empty_section(runner, greet_script, create_config):
    """An empty target section produces no extra args."""
    conf = create_config(
        "pyproject.toml",
        f'[tool.click-extra.wrap."{Path(greet_script).as_posix()}"]\n',
    )
    result = runner.invoke(
        demo,
        ["--config", str(conf), "wrap", greet_script],
    )
    assert result.exit_code == 0
    assert "Hello, World" in result.output


def test_config_target_no_config(runner, greet_script):
    """No config file at all: target runs with its own defaults."""
    result = runner.invoke(
        demo,
        ["--no-config", "wrap", greet_script],
    )
    assert result.exit_code == 0
    assert "Hello, World" in result.output


def test_config_target_invalid_option(runner, greet_script, create_config):
    """An invalid config key is caught by the target CLI."""
    conf = create_config(
        "pyproject.toml",
        f'[tool.click-extra.wrap."{Path(greet_script).as_posix()}"]\nnonexistent_option = "bad"\n',
    )
    result = runner.invoke(
        demo,
        ["--config", str(conf), "wrap", greet_script],
    )
    assert result.exit_code != 0
    assert "No such option" in result.output


# -- _config_args_for_target unit tests ----------------------------------------


def _make_wrap_ctx(full_conf):
    """Create a minimal context chain for _config_args_for_target."""
    group_ctx = click.Context(demo, info_name="click-extra")
    group_ctx.meta["click_extra.conf_full"] = full_conf
    return click.Context(wrap, info_name="wrap", parent=group_ctx)


@pytest.mark.parametrize(
    "section, script, expected",
    [
        # String value.
        ({"name": "Alice"}, "greet", ("--name", "Alice")),
        # Boolean true.
        ({"verbose": True}, "greet", ("--verbose",)),
        # Boolean false: skipped (don't pass the flag).
        ({"verbose": False}, "greet", ()),
        # Integer value.
        ({"count": 3}, "greet", ("--count", "3")),
        # List value.
        ({"tag": ["a", "b"]}, "greet", ("--tag", "a", "--tag", "b")),
        # Underscore to dash.
        ({"dry_run": True}, "greet", ("--dry-run",)),
        # Empty section.
        ({}, "greet", ()),
        # Wrong script name.
        ({"name": "Alice"}, "other", ()),
    ],
)
def test_config_args_for_target(section, script, expected):
    ctx = _make_wrap_ctx({"click-extra": {"wrap": {"greet": section}}})
    assert _config_args_for_target(ctx, script) == expected


def test_config_args_no_config():
    """No config loaded: returns empty tuple."""
    ctx = _make_wrap_ctx({})
    assert _config_args_for_target(ctx, "greet") == ()


def test_config_args_no_wrap_section():
    """Config exists but has no wrap section."""
    ctx = _make_wrap_ctx({"click-extra": {"verbosity": "DEBUG"}})
    assert _config_args_for_target(ctx, "greet") == ()
