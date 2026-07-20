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

import sys
from pathlib import Path

import click
import pytest

from click_extra.cli import demo
from click_extra.cli_wrapper import (
    _config_args_for_target,
    resolve_target,
    resolve_target_command,
    unpatch_click,
    wrap,
)
from click_extra.commands import ColorizedCommand, ColorizedGroup
from click_extra.context import Context
from click_extra.highlight import _HelpColorsMixin
from click_extra.testing import CliRunner

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

PACKAGE_GROUP_SRC = (
    "import click\n"
    "\n"
    "@click.group()\n"
    "def cli():\n"
    '    """Manage a produce stand."""\n'
    "\n"
    "@cli.command()\n"
    "def restock():\n"
    '    """Restock the shelves."""\n'
    '    click.echo("Restocked")\n'
)
"""Module-level Click group, exposed by a package inside a project directory."""


@pytest.fixture(autouse=True)
def _restore_click():
    """Undo any monkey-patching after each test to prevent cross-contamination."""
    yield
    unpatch_click()


@pytest.fixture
def runner():
    """CLI runner for wrapper tests."""
    return CliRunner()


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
def make_project(tmp_path):
    """Build a local project directory exposing a Click group at module level.

    The returned factory writes packaging metadata (``pyproject.toml`` or
    ``setup.cfg``) plus a package, in either the flat or src layout. On teardown
    it undoes the ``sys.path`` and ``sys.modules`` mutations that resolving a
    project directory triggers, keeping the tests isolated.
    """
    original_path = list(sys.path)
    original_modules = set(sys.modules)

    def _make(package, *, layout="flat", metadata="pyproject", scripts=None):
        project = tmp_path / f"{package}-project"
        root = project / "src" if layout == "src" else project
        pkg_dir = root / package
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "cli.py").write_text(PACKAGE_GROUP_SRC)

        scripts = scripts or {package: f"{package}.cli:cli"}
        if metadata == "pyproject":
            lines = [f'[project]\nname = "{package}"\n', "[project.scripts]"]
            lines += [f'{name} = "{target}"' for name, target in scripts.items()]
            (project / "pyproject.toml").write_text("\n".join(lines) + "\n")
        else:
            entries = "\n".join(
                f"    {name} = {target}" for name, target in scripts.items()
            )
            (project / "setup.cfg").write_text(
                f"[options.entry_points]\nconsole_scripts =\n{entries}\n"
            )
        return project

    yield _make

    sys.path[:] = original_path
    for name in set(sys.modules) - original_modules:
        del sys.modules[name]


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
    assert issubclass(cls, _HelpColorsMixin)


@pytest.mark.parametrize("cls", [ColorizedCommand, ColorizedGroup])
def test_patched_class_context(cls):
    assert cls.context_class is Context


def test_patched_command_no_extra_params():
    """Patched commands carry no default_params."""
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


# -- Local project directory resolution ----------------------------------------


def test_resolve_directory_flat_layout(make_project):
    """A project directory resolves via its pyproject.toml entry point."""
    project = make_project("orchard")
    assert resolve_target(str(project)) == ("orchard.cli", "cli")
    # The package root is prepended to sys.path so the import can succeed.
    assert str(project.resolve()) in sys.path


def test_resolve_directory_src_layout(make_project):
    """A src-layout project puts its src/ directory on sys.path."""
    project = make_project("vineyard", layout="src")
    assert resolve_target(str(project)) == ("vineyard.cli", "cli")
    assert str((project / "src").resolve()) in sys.path


def test_resolve_directory_setup_cfg(make_project):
    """console_scripts in setup.cfg resolve when no pyproject.toml is present."""
    project = make_project("bakery", metadata="setup_cfg")
    assert resolve_target(str(project)) == ("bakery.cli", "cli")


def test_resolve_directory_duplicate_scripts(make_project):
    """Multiple script names pointing to one target resolve unambiguously."""
    project = make_project(
        "cellar",
        scripts={"cellar": "cellar.cli:cli", "cl": "cellar.cli:cli"},
    )
    assert resolve_target(str(project)) == ("cellar.cli", "cli")


def test_resolve_directory_run(runner, make_project):
    """The default run mode imports and executes a project directory's CLI."""
    project = make_project("pantry")
    result = runner.invoke(wrap, [str(project), "restock"])
    assert result.exit_code == 0
    assert "Restocked" in result.output


def test_resolve_directory_introspect(make_project):
    """Introspection discovers the command tree of a project directory."""
    project = make_project("greenhouse")
    cmd, _ = resolve_target_command(str(project))
    assert isinstance(cmd, click.Group)
    assert cmd.name == "cli"
    assert "restock" in cmd.commands


def test_resolve_directory_no_scripts(tmp_path):
    """A project without console scripts raises an actionable error."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "empty"\n')
    with pytest.raises(click.ClickException, match="No console-script entry point"):
        resolve_target(str(tmp_path))


def test_resolve_directory_multiple_scripts(make_project):
    """Distinct entry-point targets cannot be disambiguated and raise."""
    project = make_project(
        "market",
        scripts={"sell": "stall_a.cli:sell", "buy": "stall_b.cli:buy"},
    )
    with pytest.raises(click.ClickException, match="Multiple console scripts"):
        resolve_target(str(project))


def test_resolve_directory_package_not_found(tmp_path):
    """An entry point whose package is absent on disk raises."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "ghost"\n[project.scripts]\nghost = "ghost.cli:main"\n'
    )
    with pytest.raises(click.ClickException, match="is not under"):
        resolve_target(str(tmp_path))


# -- wrap subcommand -----------------------------------------------------------


@pytest.mark.parametrize(
    "args, expected",
    [
        (["--help"], "Run, or introspect, any Click CLI"),
        ([], "Run, or introspect, any Click CLI"),
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
    assert "\x1b[36m\x1b[1m--help\x1b[0m" in result.output
    assert "\x1b[36m\x1b[1mbake\x1b[0m" in result.output


def test_run_unresolvable_target(runner):
    result = runner.invoke(wrap, ["nonexistent_xyz_12345"])
    assert result.exit_code != 0
    assert "Cannot resolve" in result.output


# -- shared external-CLI command resolution -----------------------------------


def test_resolve_target_command_returns_command_and_context(greet_script):
    """The shared resolver returns the target's command object and a context."""
    cmd, cmd_ctx = resolve_target_command(greet_script)
    assert isinstance(cmd, click.Command)
    assert isinstance(cmd_ctx, click.Context)


def test_resolve_target_command_drills_subcommand(custom_cls_script):
    """Extra subcommands navigate into nested groups."""
    cmd, _ = resolve_target_command(custom_cls_script, ("bake",))
    assert cmd.name == "bake"


# -- wrap --man: man page generation for an external CLI ----------------------


def test_wrap_man_renders_manpage(runner, greet_script):
    """``click-extra wrap --man SCRIPT`` prints the target's roff page and exits."""
    result = runner.invoke(demo, ["wrap", "--man", greet_script], color=False)
    assert result.exit_code == 0
    assert '.TH "' in result.stdout
    assert "Greet someone." in result.stdout
    assert "Name to greet." in result.stdout


def test_wrap_man_custom_class_group(runner, custom_cls_script):
    """``--man`` resolves a custom-class group target via the shared scanner."""
    result = runner.invoke(demo, ["wrap", "--man", custom_cls_script], color=False)
    assert result.exit_code == 0
    assert "Manage recipes and ingredients." in result.stdout


def test_wrap_man_drills_into_subcommand(runner, custom_cls_script):
    """Extra arguments after SCRIPT render the nested subcommand's page."""
    result = runner.invoke(
        demo, ["wrap", "--man", custom_cls_script, "bake"], color=False
    )
    assert result.exit_code == 0
    assert "Bake a cake." in result.stdout


def test_wrap_man_unresolvable_target(runner):
    result = runner.invoke(demo, ["wrap", "--man", "nonexistent_xyz_12345"])
    assert result.exit_code != 0
    assert "Cannot resolve" in result.output


def test_wrap_man_output_dir_writes_tree(runner, custom_cls_script, tmp_path):
    """``wrap --man --output-dir`` writes one .1 per (sub)command into the dir.

    ``--output-dir`` must appear before SCRIPT, because wrap runs with
    ``allow_interspersed_args=False`` so that anything after SCRIPT is
    treated as a sub-command path rather than a click-extra flag.
    """
    target = tmp_path / "man"
    result = runner.invoke(
        demo,
        ["wrap", "--man", "--output-dir", str(target), custom_cls_script],
        color=False,
    )
    assert result.exit_code == 0
    names = {path.name for path in target.iterdir()}
    assert any(name.endswith(".1") for name in names)
    # The root page is named after the resolved script (file-path target uses
    # the file stem, which is the temp script's basename).
    root_pages = {name for name in names if "-" not in name}
    assert root_pages, f"expected a root .1 page among {names!r}"
    # Subcommand 'bake' must surface as a hyphenated child page.
    assert any(name.endswith("-bake.1") for name in names), names
    # Each generated file is a valid roff document.
    for path in target.iterdir():
        assert path.read_text(encoding="utf-8").startswith('.\\" Generated')


def test_wrap_man_output_dir_creates_missing_directory(runner, greet_script, tmp_path):
    """``--output-dir`` creates the target dir when it does not exist yet."""
    target = tmp_path / "nested" / "man"
    assert not target.exists()
    result = runner.invoke(
        demo,
        ["wrap", "--man", "--output-dir", str(target), greet_script],
        color=False,
    )
    assert result.exit_code == 0
    assert target.is_dir()
    assert list(target.iterdir())


def test_wrap_man_output_dir_rejects_subcommand(runner, custom_cls_script, tmp_path):
    """``--output-dir`` always emits the full tree; mixing in a SUBCOMMAND arg
    is rejected so the user cannot accidentally produce a tree of pages named
    after a partial path."""
    target = tmp_path / "man"
    result = runner.invoke(
        demo,
        ["wrap", "--man", "--output-dir", str(target), custom_cls_script, "bake"],
        color=False,
    )
    assert result.exit_code != 0
    assert "--output-dir" in result.output
    assert not target.exists() or not any(target.iterdir())


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
    """Default Group options are accepted alongside the wrap subcommand."""
    result = runner.invoke(
        demo,
        [*group_opts, "wrap", greet_script, "--help"],
    )
    assert result.exit_code == 0
    assert "Greet someone." in result.output


@pytest.mark.parametrize(
    ("theme", "styled_heading"),
    [
        # The styled ``Usage:`` heading uses each theme's 24-bit ``heading`` slot,
        # which no other built-in emits; re-pin if the palette changes.
        ("dracula", "\x1b[38;2;255;121;198m\x1b[4mUsage:"),
        ("nord", "\x1b[38;2;94;129;172m\x1b[4mUsage:"),
    ],
)
def test_wrap_honors_group_theme(runner, greet_script, theme, styled_heading):
    """A group-level ``--theme`` reaches the wrapped CLI's help screen.

    ThemeOption records the pick on the shared context meta, but the wrapped
    target runs under its own fresh context; wrap must bridge the pick to the
    process default (through patch_click) for the target's help to pick it up.
    """
    result = runner.invoke(
        demo,
        ["--theme", theme, "wrap", greet_script, "--help"],
        color=True,
    )
    assert result.exit_code == 0
    assert styled_heading in result.output
    # Not the 16-color bright-blue heading of the dark default it used to leak.
    assert "\x1b[94m\x1b[4mUsage:" not in result.output


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
