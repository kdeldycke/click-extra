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

import inspect
import re
import sys

import click
import pytest
from boltons.strutils import strip_ansi

from click_extra import (
    ExtraVersionOption,
    Style,
    __version__,
    color_option,
    command,
    echo,
    group,
    pass_context,
    verbosity_option,
    version_option,
)
from click_extra.commands import default_extra_params
from click_extra.pytest import (
    command_decorators,
    default_debug_colored_log_end,
    default_debug_colored_logging,
    default_debug_colored_version_details,
)

from .conftest import skip_windows_colors

# Regex matching the version with optional PEP 440 local version suffix for dev
# versions (e.g., "7.6.0.dev0+abc1234").
_ver = re.escape(__version__) + r"(\+[a-f0-9]{4,40})?"


@skip_windows_colors
@pytest.mark.parametrize("cmd_decorator", command_decorators())
@pytest.mark.parametrize("option_decorator", (version_option, version_option()))
def test_standalone_version_option(invoke, cmd_decorator, option_decorator):
    @cmd_decorator
    @option_decorator
    def standalone_option():
        echo("It works!")

    result = invoke(standalone_option, "--version", color=True)
    assert re.fullmatch(
        rf"\x1b\[97mstandalone-option\x1b\[0m, version \x1b\[32m{_ver}\x1b\[0m\n",
        result.output,
    )
    assert result.exit_code == 0


@skip_windows_colors
@pytest.mark.parametrize("cmd_decorator", command_decorators())
@pytest.mark.parametrize("option_decorator", (version_option, version_option()))
def test_debug_output(invoke, cmd_decorator, option_decorator, assert_output_regex):
    @cmd_decorator
    @verbosity_option
    @option_decorator
    def debug_output():
        echo("It works!")

    result = invoke(debug_output, "--verbosity", "DEBUG", "--version", color=True)

    assert_output_regex(
        result.output,
        (
            default_debug_colored_logging
            + default_debug_colored_version_details
            + r"\x1b\[97mdebug-output\x1b\[0m, "
            rf"version \x1b\[32m{_ver}\x1b\[0m\n" + default_debug_colored_log_end
        ),
    )


@skip_windows_colors
def test_set_version(invoke):
    @click.group
    @version_option(version="1.2.3.4")
    def color_cli2():
        echo("It works!")

    # Test default coloring.
    result = invoke(color_cli2, "--version", color=True)
    assert result.stdout == (
        "\x1b[97mcolor-cli2\x1b[0m, version \x1b[32m1.2.3.4\x1b[0m\n"
    )
    assert not result.stderr
    assert result.exit_code == 0


@skip_windows_colors
@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
@pytest.mark.parametrize(
    "message, regex_stdout",
    (
        (
            "{prog_name}, version {version}",
            r"\x1b\[97mcolor-cli3\x1b\[0m, "
            rf"version \x1b\[32m{_ver}"
            r"\x1b\[0m\n",
        ),
        (
            "{prog_name}, version {version}\n{env_info}",
            r"\x1b\[97mcolor-cli3\x1b\[0m, "
            rf"version \x1b\[32m{_ver}"
            r"\x1b\[0m\n"
            r"\x1b\[90m{'.+'}"
            r"\x1b\[0m\n",
        ),
        (
            "{prog_name} v{version} - {package_name}",
            r"\x1b\[97mcolor-cli3\x1b\[0m "
            rf"v\x1b\[32m{_ver}"
            r"\x1b\[0m - "
            r"\x1b\[97mclick_extra"
            r"\x1b\[0m\n",
        ),
        (
            "{prog_name}, version {version} (Python {env_info[python][version]})",
            r"\x1b\[97mcolor-cli3\x1b\[0m, "
            rf"version \x1b\[32m{_ver}\x1b\[0m "
            r"\(Python \x1b\[90m3\.\d+\.\d+.+\x1b\[0m\)\n",
        ),
    ),
)
def test_custom_message(
    invoke, cmd_decorator, message, regex_stdout, assert_output_regex
):
    @cmd_decorator
    @version_option(message=message)
    def color_cli3():
        echo("It works!")

    result = invoke(color_cli3, "--version", color=True)
    assert_output_regex(result.output, regex_stdout)
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_style_reset(invoke, cmd_decorator):
    @cmd_decorator
    @version_option(
        message_style=None,
        version_style=None,
        prog_name_style=None,
    )
    def color_reset():
        pass

    result = invoke(color_reset, "--version", color=True)
    assert result.output == strip_ansi(result.output)
    assert not result.stderr
    assert result.exit_code == 0


@skip_windows_colors
@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_custom_message_style(invoke, cmd_decorator):
    @cmd_decorator
    @version_option(
        message="{prog_name} v{version} - {package_name} (latest)",
        message_style=Style(fg="cyan"),
        prog_name_style=Style(fg="green", bold=True),
        version_style=Style(fg="bright_yellow", bg="red"),
        package_name_style=Style(fg="bright_blue", italic=True),
    )
    def custom_style():
        pass

    result = invoke(custom_style, "--version", color=True)
    assert re.fullmatch(
        r"\x1b\[32m\x1b\[1mcustom-style\x1b\[0m\x1b\[36m "
        rf"v\x1b\[0m\x1b\[93m\x1b\[41m{_ver}\x1b\[0m\x1b\[36m - "
        r"\x1b\[0m\x1b\[94m\x1b\[3mclick_extra\x1b\[0m\x1b\[36m \(latest\)\x1b\[0m\n",
        result.output,
    )
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_context_meta(invoke, cmd_decorator, assert_output_regex):
    @cmd_decorator
    @version_option
    @pass_context
    def version_metadata(ctx):
        for field in ExtraVersionOption.template_fields:
            value = ctx.meta[f"click_extra.{field}"]
            echo(f"{field} = {value}")

    result = invoke(version_metadata, color=True)

    assert_output_regex(
        result.output,
        (
            r"module = <module 'click_extra\.testing' from '.+testing\.py'>\n"
            r"module_name = click_extra\.testing\n"
            r"module_file = .+testing\.py\n"
            r"module_version = None\n"
            r"package_name = click_extra\n"
            r"package_version = \S+\n"
            r"exec_name = click_extra\.testing\n"
            r"version = \S+\n"
            r"git_repo_path = .+\n"
            r"git_branch = .+\n"
            r"git_long_hash = [a-f0-9]{40}\n"
            r"git_short_hash = [a-f0-9]{4,40}\n"
            r"git_date = \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}\n"
            r"prog_name = version-metadata\n"
            r"env_info = {'.+'}\n"
        ),
    )
    assert result.output == strip_ansi(result.output)

    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_context_meta_laziness(invoke, cmd_decorator):
    """Accessing a single field from ``ctx.meta`` must not evaluate unrelated fields.

    Ensures that the ``_LazyVersionDict`` defers property evaluation: reading
    ``click_extra.version`` should not trigger expensive properties like
    ``env_info`` or git fields.
    """

    @cmd_decorator
    @version_option(version="1.0.0")
    @pass_context
    def lazy_cli(ctx):
        # Access only the version field.
        echo(f"version = {ctx.meta['click_extra.version']}")

    result = invoke(lazy_cli)
    assert result.exit_code == 0
    assert "version = 1.0.0" in result.output

    # Retrieve the ExtraVersionOption instance from the command.
    version_param = next(
        p for p in lazy_cli.params if isinstance(p, ExtraVersionOption)
    )
    # Fields that were never accessed should NOT have been cached.
    assert "env_info" not in version_param.__dict__
    assert "git_date" not in version_param.__dict__
    assert "git_long_hash" not in version_param.__dict__


def test_module_version_parent_package_fallback(monkeypatch):
    """``module_version`` falls back to parent package's ``__version__``.

    Simulates the Nuitka use-case: a CLI whose module is ``myapp.__main__``
    (no ``__version__``), with the parent package ``myapp`` providing it.
    """
    import types

    # Create a fake parent package with __version__.
    fake_parent = types.ModuleType("myapp")
    fake_parent.__version__ = "1.2.3"
    fake_parent.__package__ = "myapp"

    # Create a fake __main__ submodule without __version__.
    fake_main = types.ModuleType("myapp.__main__")
    fake_main.__package__ = "myapp"

    monkeypatch.setitem(sys.modules, "myapp", fake_parent)
    monkeypatch.setitem(sys.modules, "myapp.__main__", fake_main)

    opt = ExtraVersionOption(["--version"])
    # Bypass cli_frame resolution by setting the module directly.
    monkeypatch.setattr(
        type(opt),
        "module",
        property(lambda self: fake_main),
    )

    assert opt.module_version == "1.2.3"


def test_cli_frame_fallback(monkeypatch):
    """``cli_frame()`` falls back to the outermost frame when all frames are
    from the Click ecosystem."""
    original_stack = inspect.stack

    def patched_stack():
        """Make every frame look like it belongs to click_extra."""
        frames = original_stack()
        for frame_info in frames:
            frame_info.frame.f_globals.setdefault("__name__", "")
            # Temporarily override __name__ so the heuristic skips all frames.
            frame_info.frame.f_globals["__name__"] = (
                "click_extra." + frame_info.function
            )
        return frames

    monkeypatch.setattr(inspect, "stack", patched_stack)

    # Should not raise RuntimeError; instead falls back to outermost frame.
    frame = ExtraVersionOption.cli_frame()
    assert frame is not None


@pytest.mark.parametrize(
    "params",
    (None, "--help", "blah", ("--config", "random.toml")),
)
def test_integrated_version_option_precedence(invoke, params):
    def versioned_extra_params():
        params = default_extra_params()
        for p in params:
            if isinstance(p, ExtraVersionOption):
                p.version = "1.2.3.4"
        return params

    @group(params=versioned_extra_params)
    def color_cli4():
        echo("It works!")

    result = invoke(color_cli4, "--version", params, color=True)
    assert result.stdout == (
        "\x1b[97mcolor-cli4\x1b[0m, version \x1b[32m1.2.3.4\x1b[0m\n"
    )
    assert not result.stderr
    assert result.exit_code == 0


@skip_windows_colors
def test_prog_name_forwarded_to_version_option(invoke):
    """``prog_name`` on ``@command``/``@group`` is forwarded to ``ExtraVersionOption``."""

    @command(name="my-tool", prog_name="My Tool")
    def prog_name_cli():
        echo("It works!")

    # prog_name controls --version output.
    result = invoke(prog_name_cli, "--version", color=True)
    assert "\x1b[97mMy Tool\x1b[0m, version" in result.output
    assert result.exit_code == 0

    # name controls the usage line.
    result = invoke(prog_name_cli, "--help", color=True)
    assert "\x1b[97mmy-tool\x1b[0m" in result.output
    assert result.exit_code == 0

    # All default extra options are preserved.
    result = invoke(prog_name_cli, "--help", color=False)
    assert "--time" in result.output
    assert "--color" in result.output
    assert "--config" in result.output
    assert "--version" in result.output


@skip_windows_colors
def test_prog_name_forwarded_on_group(invoke):
    """``prog_name`` works on ``@group`` too."""

    @group(name="my-grp", prog_name="My Group")
    def prog_name_grp():
        pass

    result = invoke(prog_name_grp, "--version", color=True)
    assert "\x1b[97mMy Group\x1b[0m, version" in result.output
    assert result.exit_code == 0

    result = invoke(prog_name_grp, "--help", color=True)
    assert "\x1b[97mmy-grp\x1b[0m" in result.output
    assert result.exit_code == 0


@skip_windows_colors
def test_color_option_precedence(invoke):
    """--no-color has an effect on --version, if placed in the right order.

    Eager parameters are evaluated in the order as they were provided on the command
    line by the user as expleined in:
    https://click.palletsprojects.com/en/stable/click-concepts/#callback-evaluation-order

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
    assert result.stdout == "color-cli6, version 2.1.9\n"
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(color_cli6, "--version", "--no-color", "command1", color=True)
    assert result.stdout == (
        "\x1b[97mcolor-cli6\x1b[0m, version \x1b[32m2.1.9\x1b[0m\n"
    )
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_dev_version_appends_git_hash(invoke, cmd_decorator):
    """A ``.dev`` version gets a ``+hash`` suffix appended (or not, if git is
    unavailable)."""

    @cmd_decorator
    @version_option(module_version="1.0.0.dev1")
    def dev_cli():
        echo("It works!")

    result = invoke(dev_cli, "--version", color=False)
    ver = strip_ansi(result.output).split("version ")[-1].strip()
    # Either plain dev version (no git) or with +hash suffix.
    assert re.fullmatch(r"1\.0\.0\.dev1(\+[a-f0-9]{4,40})?", ver)
    assert result.exit_code == 0


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_prebaked_dev_version_not_double_suffixed(invoke, cmd_decorator):
    """A version with an existing ``+`` is returned as-is — no second hash appended."""

    @cmd_decorator
    @version_option(module_version="1.0.0.dev1+abc1234")
    def prebaked_cli():
        echo("It works!")

    result = invoke(prebaked_cli, "--version", color=False)
    ver = strip_ansi(result.output).split("version ")[-1].strip()
    assert ver == "1.0.0.dev1+abc1234"
    assert result.exit_code == 0


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_release_version_unchanged(invoke, cmd_decorator):
    """A non-dev version is never modified."""

    @cmd_decorator
    @version_option(module_version="2.5.0")
    def release_cli():
        echo("It works!")

    result = invoke(release_cli, "--version", color=False)
    ver = strip_ansi(result.output).split("version ")[-1].strip()
    assert ver == "2.5.0"
    assert result.exit_code == 0


# --- prebake_version tests ---


@pytest.fixture
def init_file(tmp_path):
    """Helper that creates a temporary __init__.py with the given content."""

    def _make(content: str):
        p = tmp_path / "__init__.py"
        p.write_text(content, encoding="utf-8")
        return p

    return _make


def test_prebake_dev_version(init_file):
    """A ``.dev`` version gets ``+hash`` appended in the file."""
    p = init_file('__version__ = "1.0.0.dev0"\n')
    result = ExtraVersionOption.prebake_version(p, local_version="abc1234")
    assert result == "1.0.0.dev0+abc1234"
    assert '__version__ = "1.0.0.dev0+abc1234"' in p.read_text()


def test_prebake_single_quotes(init_file):
    """Single-quoted ``__version__`` is also handled."""
    p = init_file("__version__ = '2.0.0.dev5'\n")
    result = ExtraVersionOption.prebake_version(p, local_version="f00baa")
    assert result == "2.0.0.dev5+f00baa"
    assert "__version__ = '2.0.0.dev5+f00baa'" in p.read_text()


def test_prebake_already_baked_skipped(init_file):
    """A version with existing ``+`` is left untouched."""
    p = init_file('__version__ = "1.0.0.dev0+existing"\n')
    result = ExtraVersionOption.prebake_version(p, local_version="abc1234")
    assert result is None
    assert '__version__ = "1.0.0.dev0+existing"' in p.read_text()


def test_prebake_release_skipped(init_file):
    """A release version (no ``.dev``) is not modified."""
    p = init_file('__version__ = "3.2.1"\n')
    result = ExtraVersionOption.prebake_version(p, local_version="abc1234")
    assert result is None
    assert '__version__ = "3.2.1"' in p.read_text()


def test_prebake_no_version_in_file(init_file):
    """A file without ``__version__`` returns ``None``."""
    p = init_file('"""Just a docstring."""\n')
    result = ExtraVersionOption.prebake_version(p, local_version="abc1234")
    assert result is None


def test_prebake_missing_local_version_raises(init_file):
    """Calling without ``local_version`` raises ``TypeError``."""
    p = init_file('__version__ = "1.0.0.dev0"\n')
    with pytest.raises(TypeError):
        ExtraVersionOption.prebake_version(p)


def test_prebake_idempotent(init_file):
    """Running prebake twice does not double-suffix."""
    p = init_file('__version__ = "1.0.0.dev0"\n')
    first = ExtraVersionOption.prebake_version(p, local_version="abc1234")
    assert first == "1.0.0.dev0+abc1234"
    second = ExtraVersionOption.prebake_version(p, local_version="def5678")
    assert second is None
    assert '__version__ = "1.0.0.dev0+abc1234"' in p.read_text()


def test_prebake_preserves_surrounding_content(init_file):
    """Content around ``__version__`` is not disturbed."""
    content = (
        '"""My package."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        '__version__ = "4.0.0.dev0"\n'
        "\n"
        "API_URL = 'https://example.com'\n"
    )
    p = init_file(content)
    ExtraVersionOption.prebake_version(p, local_version="cafe123")
    result = p.read_text()
    assert '__version__ = "4.0.0.dev0+cafe123"' in result
    assert "from __future__ import annotations" in result
    assert "API_URL = 'https://example.com'" in result


def __test_inplace_context():
    @click.command
    @version_option
    def cli():
        pass

    with cli.make_context("foo", []) as ctx:
        for field in ExtraVersionOption.template_fields:
            value = ctx.meta[f"click_extra.{field}"]
            assert value is not None
