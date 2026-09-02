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
"""Test defaults of our custom commands, as well as their customizations and attached
options, and how they interact with each others."""

from __future__ import annotations

import importlib.metadata
import inspect
import json
import os
import re
import sys
from contextlib import nullcontext
from subprocess import run
from textwrap import dedent

import click
import cloup
import pytest

import click_extra
from click_extra import (
    ExtraOptionGroup,
    HelpCommand,
    LazyGroup,
    LazySubcommand,
    VersionOption,
    argument,
    command,
    echo,
    group,
    option,
    option_group,
    pass_context,
    version_option,
)
from click_extra.commands import (
    DEFAULT_OPTION_GROUPS,
    DEFAULT_PRIORITY,
    default_params,
)
from click_extra.parameters import (
    full_short_help,
    iter_params_for_display,
    iter_subcommands,
    make_resilient_context,
)
from click_extra.pytest import (
    command_decorators,
    default_debug_uncolored_log_end,
    default_debug_uncolored_log_start,
    default_options_colored_help,
    default_options_uncolored_help,
)


@pytest.mark.once
def test_module_root_declarations():
    """Verify ``click_extra.__all__`` is a superset of click and cloup.

    Sort order is enforced by ``ruff`` (RUF022).
    """
    click_extra_members = set(click_extra.__all__)

    # Namespace artifacts that are not real API: ``annotations`` is the
    # ``from __future__ import annotations`` binding upstream modules leave
    # behind, and cloup's ``__all__`` leaks the stdlib ``warnings`` module.
    artifacts = {"annotations", "warnings"}

    click_members = {
        name
        for name, member in inspect.getmembers(click)
        if not name.startswith("_")
        and not inspect.ismodule(member)
        and name not in artifacts
    }
    assert click_members <= click_extra_members

    cloup_members = {
        m for m in cloup.__all__ if not m.startswith("_") and m not in artifacts
    }
    assert cloup_members <= click_extra_members


@pytest.mark.once
def test_public_namespace_integrity():
    """The package namespace and ``__all__`` agree: nothing missing or extra.

    click ships no ``__all__``, so its star import would otherwise leak every
    submodule bound by click's ``__init__`` (``click.core``, ``click.globals``,
    ...) into the package namespace, handing out click's un-enhanced classes
    and shadowing the ``globals`` builtin. Those bindings are scrubbed at the
    end of ``click_extra/__init__.py``: verify the scrub held, that every
    public binding is declared in ``__all__``, and that every declared name
    resolves (eagerly, lazily, or as one of our own submodules).
    """
    foreign_modules = {
        name
        for name, value in vars(click_extra).items()
        if inspect.ismodule(value) and not value.__name__.startswith("click_extra.")
    }
    assert not foreign_modules

    # TYPE_CHECKING is the module's own typing idiom, not API. Lazy test
    # tooling cached by an earlier access is fine: those names are declared.
    public = {
        name
        for name, value in vars(click_extra).items()
        if not name.startswith("_")
        and not inspect.ismodule(value)
        and name != "TYPE_CHECKING"
    }
    assert public <= set(click_extra.__all__)

    for name in click_extra.__all__:
        getattr(click_extra, name)


@pytest.mark.once
def test_no_debugger_ballast_on_import():
    """Importing the package must not load the test tooling nor the debugger stack.

    ``click_extra.testing`` imports ``click.testing``, whose module-level
    ``import pdb`` cascades into asyncio and the ``_pyrepl`` machinery on
    Python 3.13+. That chain used to load eagerly with ``import click_extra``,
    and ended up bundled into every Nuitka-compiled CLI binary. The test
    tooling is exported lazily now: check from a pristine interpreter that
    none of it leaks at import time.
    """
    ballast = (
        "click.testing",
        "click_extra.test_suite",
        "click_extra.testing",
        "pdb",
        "bdb",
        "asyncio",
        "_pyrepl",
    )
    probe = (
        "import sys; import click_extra; "
        f"leaked = [m for m in {ballast!r} if m in sys.modules]; "
        "assert not leaked, f'leaked at import time: {leaked}'"
    )
    process = run(
        (sys.executable, "-c", probe), capture_output=True, text=True, check=False
    )
    assert process.returncode == 0, process.stderr


@pytest.mark.once
def test_lazy_test_tooling_exports():
    """The lazy test-tooling names resolve, cache, and show up in ``dir()``."""
    assert "CliRunner" in dir(click_extra)
    assert "run_test_suite" in dir(click_extra)

    from click_extra import CliRunner, testing

    assert CliRunner is testing.CliRunner
    # First access caches the symbol in the module namespace, bypassing the
    # PEP 562 hook for later lookups.
    assert "CliRunner" in vars(click_extra)
    assert click_extra.run_test_suite is click_extra.test_suite.run_test_suite


@pytest.fixture
def all_command_cli():
    """A CLI that is mixing all variations and flavors of subcommands."""

    def versioned_extra_params():
        params = default_params()
        for p in params:
            if isinstance(p, VersionOption):
                p.version = "2021.10.08"
        return params

    @group(params=versioned_extra_params)
    def command_cli1():
        echo("It works!")

    @command_cli1.command()
    def default_subcommand():
        echo("Run default subcommand...")

    @command
    def click_extra_subcommand():
        echo("Run click-extra subcommand...")

    @cloup.command()
    def cloup_subcommand():
        echo("Run cloup subcommand...")

    @click.command
    def click_subcommand():
        echo("Run click subcommand...")

    command_cli1.section(  # type: ignore[attr-defined]
        "Subcommand group",
        click_extra_subcommand,
        cloup_subcommand,
        click_subcommand,
    )

    return command_cli1


help_screen = (
    r"Usage: command-cli1 \[OPTIONS\] COMMAND \[ARGS\]\.\.\.\n"
    r"\n"
    r"Options:\n"
    rf"{default_options_uncolored_help}"
    r"\n"
    r"Subcommand group:\n"
    r"  click-extra-subcommand\n"
    r"  cloup-subcommand\n"
    r"  click-subcommand\n"
    r"\n"
    r"Other commands:\n"
    r"  default-subcommand\n"
    r"  help +Show help for a command\.\n"
)


def test_unknown_option(invoke, all_command_cli):
    result = invoke(all_command_cli, "--blah")
    assert not result.stdout
    assert "No such option" in result.stderr
    assert result.exit_code == 2


@pytest.mark.parametrize(
    ("cli_options", "args", "exit_code", "expected_fragment"),
    [
        pytest.param(
            {"--alpha/-a": True},
            ["-dbgwrong"],
            2,
            "-dbgwrong",
            id="full_token_no_match",
        ),
        pytest.param(
            {"--debug/-d": True},
            ["--deubg"],
            2,
            "--deubg",
            id="long_option_typo_suggest",
        ),
        pytest.param(
            {"-a": True, "-b": True, "-c": True},
            ["-abc"],
            0,
            "a=True b=True c=True",
            id="combining_still_works",
        ),
        pytest.param(
            {"-a": True, "-b": True},
            ["-abZ"],
            2,
            "-Z",
            id="combining_error_on_later_char",
        ),
    ],
)
def test_short_option_error_enhancement(
    invoke,
    cli_options,
    args,
    exit_code,
    expected_fragment,
):
    """``Command.parse_args`` improves error messages for single-dash
    multi-character tokens whose first character is not a registered short
    option.  Vanilla Click would split ``-dbgwrong`` character by character and
    report "No such option: -d"; we re-raise with the full token and close-match
    suggestions instead.

    The enhancement must not interfere with valid ``-abc``-style combining or
    with the per-character diagnostic when a *later* character is unknown.

    Upstream context: https://github.com/pallets/click/issues/2779
    """
    # Build a minimal CLI from the option spec.
    params = []
    param_names = []
    for spec, is_flag in cli_options.items():
        opts = spec.split("/")
        # Derive the Python parameter name from the longest option.
        name = max(opts, key=len).lstrip("-").replace("-", "_")
        param_names.append(name)
        params.append(click_extra.option(*opts, is_flag=is_flag))

    def callback(**kwargs):
        parts = " ".join(f"{k}={v}" for k, v in kwargs.items())
        click_extra.echo(parts)

    # Apply option decorators, then the command decorator.
    decorated = callback
    for param in reversed(params):
        decorated = param(decorated)
    cli = click_extra.command()(decorated)

    result = invoke(cli, *args)
    assert result.exit_code == exit_code
    output = result.output if exit_code == 0 else result.stderr
    assert expected_fragment in output


def test_unknown_command(invoke, all_command_cli):
    result = invoke(all_command_cli, "blah")
    assert not result.stdout
    assert "Error: No such command 'blah'." in result.stderr
    assert result.exit_code == 2


def test_required_command(invoke, all_command_cli, assert_output_regex):
    result = invoke(all_command_cli, "--verbosity", "DEBUG", color=False)
    # In debug mode, the version is always printed.
    assert not result.stdout
    assert_output_regex(
        result.stderr,
        (
            rf"{default_debug_uncolored_log_start}"
            rf"{default_debug_uncolored_log_end}"
            r"Usage: command-cli1 \[OPTIONS\] COMMAND \[ARGS\]\.\.\.\n"
            r"Try 'command-cli1 --help' for help\.\n"
            r"\n"
            r"Error: Missing command\.\n"
        ),
    )
    assert result.exit_code == 2


@pytest.mark.parametrize(("param", "exit_code"), ((None, 2), ("-h", 0), ("--help", 0)))
def test_group_help(invoke, all_command_cli, param, exit_code, assert_output_regex):
    result = invoke(all_command_cli, param, color=False)
    assert "It works!" not in result.stdout
    if exit_code == 2:
        assert_output_regex(result.stderr, help_screen)
    else:
        assert_output_regex(result.stdout, help_screen)
        assert not result.stderr
    assert result.exit_code == exit_code


@pytest.mark.parametrize(
    ("params", "exit_code", "expect_help", "expect_empty_stderr"),
    (
        (("--help", "--version"), 0, True, True),
        # --version takes precedence over --help.
        (("--version", "--help"), 0, False, True),
        (("--help", "blah"), 0, True, True),
        (("--help", "--verbosity", "DEBUG"), 0, True, True),
        # stderr will contain DEBUG log messages.
        (("--verbosity", "DEBUG", "--help"), 0, True, False),
        (("--help", "--config", "random.toml"), 0, True, True),
        # Config file does not exist and stderr will contain the error message.
        (("--config", "random.toml", "--help"), 2, False, False),
    ),
)
def test_help_eagerness(
    invoke,
    all_command_cli,
    params,
    exit_code,
    expect_help,
    expect_empty_stderr,
    assert_output_regex,
):
    """See:
    https://click.palletsprojects.com/en/stable/click-concepts/#callback-evaluation-order
    """
    result = invoke(all_command_cli, params, color=False)
    assert "It works!" not in result.stdout
    if expect_help:
        assert_output_regex(result.stdout, help_screen)
    elif result.stdout:
        with pytest.raises(AssertionError):
            assert_output_regex(result.stdout, help_screen)
    if expect_empty_stderr:
        assert not result.stderr
    else:
        assert result.stderr
    assert result.exit_code == exit_code


def test_help_custom_name(invoke):
    """Removes the ``-h`` short option as we reserve it for a custom ``-h/--header`` option.

    See: https://github.com/kdeldycke/mail-deduplicate/issues/762
    """

    @command(context_settings={"help_option_names": ("--help",)})
    @option("-h", "--header", is_flag=True)
    def cli(header):
        echo(f"--header is {header}")

    result = invoke(cli, "--help", color=False)
    assert "-h, --header" in result.stdout
    assert "-h, --help" not in result.stdout
    assert "--help" in result.stdout
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "cmd_id",
    (
        "default-subcommand",
        "click-extra-subcommand",
        "cloup-subcommand",
        "click-subcommand",
    ),
)
@pytest.mark.parametrize("param", ("-h", "--help"))
def test_subcommand_help(invoke, all_command_cli, cmd_id, param, assert_output_regex):
    # Force color: under the GNU auto default, piped output (like this runner) is
    # left uncolored, but here we exercise the colored rendering of extra commands.
    result = invoke(all_command_cli, cmd_id, param, color="forced")

    colored_help_header = (
        r"It works!\n"
        r"\x1b\[94m\x1b\[4mUsage:\x1b\[0m "
        rf"\x1b\[97m\x1b\[1mcommand-cli1 {cmd_id}\x1b\[0m"
        r" \x1b\[36m\x1b\[2m\x1b\[3m\[OPTIONS\]\x1b\[0m\n"
        r"\n"
        r"\x1b\[94m\x1b\[4mOptions:\x1b\[0m\n"
    )
    # Extra sucommands are colored and include all extra options.
    if cmd_id == "click-extra-subcommand":
        assert_output_regex(
            result.stdout,
            rf"{colored_help_header}{default_options_colored_help}",
        )

    # Default subcommand inherits from extra family and is colored, but does not include
    # extra options.
    elif cmd_id == "default-subcommand":
        assert_output_regex(
            result.stdout,
            (
                rf"{colored_help_header}"
                r"  \x1b\[36m\x1b\[1m-h\x1b\[0m, \x1b\[36m\x1b\[1m--help\x1b\[0m"
                r"  Show this message and exit\.\n"
            ),
        )

    # Non-extra subcommands are not colored.
    else:
        assert result.stdout == dedent(
            f"""\
            It works!
            Usage: command-cli1 {cmd_id} [OPTIONS]

            Options:
              -h, --help  Show this message and exit.
            """,
        )

    assert result.exit_code == 0
    assert not result.stderr


@pytest.mark.parametrize("cmd_id", ("default", "click-extra", "cloup", "click"))
def test_subcommand_execution(invoke, all_command_cli, cmd_id):
    result = invoke(all_command_cli, f"{cmd_id}-subcommand", color=False)
    assert result.stdout == dedent(
        f"""\
        It works!
        Run {cmd_id} subcommand...
        """,
    )
    assert not result.stderr
    assert result.exit_code == 0


def test_integrated_version_value(invoke, all_command_cli):
    result = invoke(all_command_cli, "--version", color=False)
    assert result.stdout == "command-cli1, version 2021.10.08\n"
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "cmd_decorator",
    command_decorators(no_click=True, no_cloup=True, with_parenthesis=False),
)
@pytest.mark.parametrize("param", ("-h", "--help"))
def test_colored_bare_help(invoke, cmd_decorator, param):
    """Extra decorators are always colored.

    Even when stripped of their default parameters, as reported in:
    https://github.com/kdeldycke/click-extra/issues/534
    https://github.com/kdeldycke/click-extra/pull/543
    """

    @cmd_decorator(params=None)
    def bare_cli():
        pass

    # Force color: with the GNU auto default, piped output is uncolored, but this
    # test asserts the extra formatter still colorizes even a bare command.
    result = invoke(bare_cli, param, color="forced")
    assert (
        "\n"
        "\x1b[94m\x1b[4mOptions:\x1b[0m\n"
        "  \x1b[36m\x1b[1m-h\x1b[0m, \x1b[36m\x1b[1m--help\x1b[0m  Show this message and exit.\n"
    ) in result.stdout
    assert not result.stderr
    assert result.exit_code == 0


def test_duplicate_option(invoke):
    """
    See:
    - https://kdeldycke.github.io/click-extra/commands.html#change-default-options
    - https://github.com/kdeldycke/click-extra/issues/232
    """

    @command
    @version_option(fields={"version": "0.1"})
    def cli():
        pass

    result = invoke(cli, "--help", color=False)
    version_line = "  --version                    Show the version and exit.\n"
    # The CLI's own --version opens its section, ungrouped alongside --help. The
    # injected duplicate closes the introspection section at the far end.
    assert result.stdout.startswith(
        "Usage: cli [OPTIONS]\n"
        "\n"
        "Options:\n"
        f"{version_line}"
        "  -h, --help                   Show this message and exit.\n"
    )
    assert result.stdout.endswith(version_line)
    assert result.stdout.count(version_line) == 2
    assert not result.stderr
    assert result.exit_code == 0


def test_no_option_leaks_between_subcommands(invoke, assert_output_regex):
    """As reported in https://github.com/kdeldycke/click-extra/issues/489."""

    @click.group
    def cli():
        echo("Run cli...")

    @command
    @click.option("--one")
    def foo():
        echo("Run foo...")

    @command(short_help="Bar subcommand.")
    @click.option("--two")
    def bar():
        echo("Run bar...")

    cli.add_command(foo)
    cli.add_command(bar)

    result = invoke(cli, "--help", color=False)
    assert result.stdout == dedent(
        """\
        Usage: cli [OPTIONS] COMMAND [ARGS]...

        Options:
          --help  Show this message and exit.

        Commands:
          bar  Bar subcommand.
          foo
        """,
    )
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(cli, "foo", "--help", color=False)
    assert_output_regex(
        result.stdout,
        (
            r"Run cli\.\.\.\n"
            r"Usage: cli foo \[OPTIONS\]\n"
            r"\n"
            r"Options:\n"
            r"  --one TEXT\n"
            rf"{default_options_uncolored_help}"
        ),
    )
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(cli, "bar", "--help", color=False)
    assert_output_regex(
        result.stdout,
        (
            r"Run cli\.\.\.\n"
            r"Usage: cli bar \[OPTIONS\]\n"
            r"\n"
            r"Options:\n"
            r"  --two TEXT\n"
            rf"{default_options_uncolored_help}"
        ),
    )
    assert not result.stderr
    assert result.exit_code == 0


def test_option_group_integration(invoke, assert_output_regex):
    # Mix regular and grouped options
    @group
    @option_group(
        "Group 1",
        click.option("-a", "--opt1"),
        option("-b", "--opt2"),
    )
    @click.option("-c", "--opt3")
    @option("-d", "--opt4")
    def command_cli2(opt1, opt2, opt3, opt4):
        echo("It works!")

    @command_cli2.command()
    def default_command():
        echo("Run command...")

    # Remove colors to simplify output comparison.
    result = invoke(command_cli2, "--help", color=False)
    assert_output_regex(
        result.stdout,
        (
            r"Usage: command-cli2 \[OPTIONS\] COMMAND \[ARGS\]\.\.\.\n"
            r"\n"
            r"Group 1:\n"
            r"  -a, --opt1 TEXT\n"
            r"  -b, --opt2 TEXT\n"
            r"\n"
            r"Other options:\n"
            r"  -c, --opt3 TEXT\n"
            r"  -d, --opt4 TEXT\n"
            rf"{default_options_uncolored_help}"
            r"\n"
            r"Commands:\n"
            r"  default\n"
            r"  help +Show help for a command\.\n"
        ),
    )
    assert "It works!" not in result.stdout
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("cmd_decorator", "ctx_settings", "expected_help"),
    (
        # Click does not show all envvar in the help screen by default, unless
        # specifficaly set on an option.
        (
            click.command,
            {},
            "  --flag1\n  --flag2  [env var: custom2]\n  --flag3\n",
        ),
        # Click Extra defaults to let each option choose its own show_envvar value.
        (
            command,
            {},
            "  --flag1\n"
            "  --flag2                      [env var: "
            + ("CUSTOM2" if os.name == "nt" else "custom2")
            + ", CLI_FLAG2]\n"
            "  --flag3\n",
        ),
        # Click Extra allow bypassing its global show_envvar setting.
        (
            command,
            {"show_envvar": None},
            "  --flag1\n"
            "  --flag2                      [env var: "
            + ("CUSTOM2" if os.name == "nt" else "custom2")
            + ", CLI_FLAG2]\n"
            "  --flag3\n",
        ),
        # Click Extra force the show_envvar value on all options.
        (
            command,
            {"show_envvar": True},
            "  --flag1                      [env var: "
            + ("CUSTOM1" if os.name == "nt" else "custom1")
            + ", CLI_FLAG1]\n"
            "  --flag2                      [env var: "
            + ("CUSTOM2" if os.name == "nt" else "custom2")
            + ", CLI_FLAG2]\n"
            "  --flag3                      [env var: "
            + ("CUSTOM3" if os.name == "nt" else "custom3")
            + ", CLI_FLAG3]\n",
        ),
        (
            command,
            {"show_envvar": False},
            "  --flag1\n  --flag2\n  --flag3\n",
        ),
    ),
)
def test_show_envvar_parameter(invoke, cmd_decorator, ctx_settings, expected_help):
    @cmd_decorator(context_settings=ctx_settings)
    @option("--flag1", is_flag=True, envvar=["custom1"])
    @option("--flag2", is_flag=True, envvar=["custom2"], show_envvar=True)
    @option("--flag3", is_flag=True, envvar=["custom3"], show_envvar=False)
    def cli():
        pass

    # Remove colors to simplify output comparison.
    result = invoke(cli, "--help", color=False)
    assert expected_help in result.stdout
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("ctx_settings", "expected"),
    (
        # Click Extra leaves each option's show_choices untouched by default.
        ({}, (True, True, False)),
        ({"show_choices": None}, (True, True, False)),
        # Click Extra forces the show_choices value on all options when set.
        ({"show_choices": True}, (True, True, True)),
        ({"show_choices": False}, (False, False, False)),
    ),
)
def test_show_choices_parameter(ctx_settings, expected):
    """The show_choices context setting is forced on every option when set."""

    @command(context_settings=ctx_settings)
    @option("--opt1", prompt=True, type=click.Choice(["a", "b"]))
    @option("--opt2", prompt=True, type=click.Choice(["a", "b"]), show_choices=True)
    @option("--opt3", prompt=True, type=click.Choice(["a", "b"]), show_choices=False)
    def cli():
        pass

    resolved = {
        param.name: param.show_choices
        for param in cli.params
        if isinstance(param, click.Option)
    }
    assert (resolved["opt1"], resolved["opt2"], resolved["opt3"]) == expected


def test_raw_args(invoke):
    """Raw args are expected to be scoped in subcommands."""

    @group
    @option("--dummy-flag/--no-flag")
    @pass_context
    def my_cli(ctx, dummy_flag):
        echo("-- Group output --")
        echo(f"dummy_flag is {dummy_flag!r}")
        echo(f"Raw parameters: {ctx.meta.get('click_extra.raw_args', [])}")

    @my_cli.command()
    @pass_context
    @option("--int-param", type=int, default=10)
    def subcommand(ctx, int_param):
        echo("-- Subcommand output --")
        echo(f"int_parameter is {int_param!r}")
        echo(f"Raw parameters: {ctx.meta.get('click_extra.raw_args', [])}")

    result = invoke(my_cli, "--dummy-flag", "subcommand", "--int-param", "33")
    assert result.stdout == dedent(
        """\
        -- Group output --
        dummy_flag is True
        Raw parameters: ['--dummy-flag', 'subcommand', '--int-param', '33']
        -- Subcommand output --
        int_parameter is 33
        Raw parameters: ['--int-param', '33']
        """,
    )
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "lazy_cmd_decorator",
    (
        "@click.command",
        "@click_extra.command",
        "@cloup.command()",
    ),
)
@pytest.mark.parametrize(
    "lazy_group_decorator",
    (
        "@click.group(cls=LazyGroup,",
        "@cloup.group(cls=LazyGroup,",
        "@click_extra.group(cls=LazyGroup,",
    ),
)
def test_lazy_group(invoke, tmp_path, lazy_cmd_decorator, lazy_group_decorator):
    """Test extends the `snippet from Click documentation
    <https://click.palletsprojects.com/en/stable/complex/#using-lazygroup-to-define-a-cli>`_.
    """

    (tmp_path / "foo_cmd.py").write_text(
        dedent(
            f"""
            import click
            import cloup
            import click_extra

            from click import echo, option


            print("<foo_cmd module loaded>")

            {lazy_cmd_decorator}
            @option("--foo-param", default=5)
            def foo_cli(foo_param):
                echo(f"foo_param = {{foo_param}}")
            """
        )
    )

    (tmp_path / "fur_cmd.py").write_text(
        dedent(
            f"""
            import click
            import cloup
            import click_extra

            from click import echo, option


            print("<fur_cmd module loaded>")

            {lazy_cmd_decorator}
            @option("--fur-param", default=7)
            def fur_cli(fur_param):
                echo(f"fur_param = {{fur_param}}")
            """
        )
    )

    (tmp_path / "bar_cmd.py").write_text(
        dedent(
            f"""
            import click
            import cloup
            import click_extra

            from click import echo, option
            from click_extra import LazyGroup


            print("<bar_cmd module loaded>")

            {lazy_group_decorator}
                lazy_subcommands={{"baz_cmd": "baz_cmd.baz_cli"}},
                help="bar command for lazy example.",
            )
            @option("--bar-param", default=11)
            def bar_cli(bar_param):
                echo(f"bar_param = {{bar_param}}")
            """
        )
    )

    (tmp_path / "baz_cmd.py").write_text(
        dedent(
            f"""
            import click
            import cloup
            import click_extra

            from click import echo, option


            print("<baz_cmd module loaded>")

            {lazy_cmd_decorator}
            @option("--baz-param", default=13)
            def baz_cli(baz_param):
                echo(f"baz_param = {{baz_param}}")
            """
        )
    )

    def reset_main_cli():
        """Create the main CLI command with lazy subcommands.

        Also forces a reset of the lazy-loaded module. Else we'll have an issue
        with ``invoke()`` reusing the same CLI instance, and modules attached to it
        not getting reloaded because ``LazyGroup`` caches the resolved commands.
        """
        # Remove lazy-loaded modules from sys.modules to force reloading.
        for module_name in ["foo_cmd", "fur_cmd", "bar_cmd", "baz_cmd"]:
            sys.modules.pop(module_name, None)

        @click.group(
            cls=LazyGroup,
            lazy_subcommands={
                "foo_cmd": "foo_cmd.foo_cli",
                "fur_cmd": "fur_cmd.fur_cli",
                "bar_cmd": "bar_cmd.bar_cli",
            },
            help="main CLI command for lazy example.",
        )
        @click.option("--main-param", default=3)
        def main_cli(main_param):
            echo(f"main_param = {main_param}")

        return main_cli

    help_screen = dedent(
        """\
        Usage: main-cli [OPTIONS] COMMAND [ARGS]...

          main CLI command for lazy example.

        Options:
          --main-param INTEGER  [default: 3]
          -h, --help            Show this message and exit.

        Commands:
          bar_cmd  bar command for lazy example.
          foo_cmd
          fur_cmd
          help     Show help for a command.
        """
    )

    # Allow discoverability of the modules implementing the lazy subcommands.
    sys.path.insert(0, str(tmp_path))

    try:
        main_cli = reset_main_cli()

        # Calling --help load the modules in a stable order. Also check that the
        # subcommands are featured in the help screen. But not the nested baz_cmd.
        result = invoke(main_cli, "--help", color=False)
        assert result.stdout == (
            dedent(
                """\
                <bar_cmd module loaded>
                <foo_cmd module loaded>
                <fur_cmd module loaded>
                """
            )
            + help_screen
        )
        assert not result.stderr
        assert result.exit_code == 0

        # A second help invocation should not reload already loaded modules.
        result = invoke(main_cli, "--help", color=False)
        assert result.stdout == help_screen

        # Recreate the CLI to reset the lazy-loaded commands cache.
        main_cli = reset_main_cli()

        # Check modules are reloaded.
        result = invoke(main_cli, "--help", color=False)
        assert result.stdout == (
            dedent(
                """\
                <bar_cmd module loaded>
                <foo_cmd module loaded>
                <fur_cmd module loaded>
                """
            )
            + help_screen
        )
        assert not result.stderr
        assert result.exit_code == 0

        # Execute a lazy subcommand: no module gets loaded because it was already done
        # in the previous --help invocation.
        result = invoke(main_cli, "foo_cmd")
        assert result.stdout == dedent(
            """\
            main_param = 3
            foo_param = 5
            """
        )
        assert not result.stderr
        assert result.exit_code == 0

        # Reset the CLI.
        main_cli = reset_main_cli()

        # Execute a lazy subcommand: only the invoked module gets lazy loaded.
        result = invoke(main_cli, "--main-param", "30", "foo_cmd", "--foo-param", "50")
        assert result.stdout == dedent(
            """\
            <foo_cmd module loaded>
            main_param = 30
            foo_param = 50
            """
        )
        assert not result.stderr
        assert result.exit_code == 0

        # Execute a nested lazy subcommand.
        result = invoke(main_cli, "bar_cmd", "baz_cmd", "--baz-param", "17")
        assert result.stdout == dedent(
            """\
            <bar_cmd module loaded>
            main_param = 3
            <baz_cmd module loaded>
            bar_param = 11
            baz_param = 17
            """
        )
        assert not result.stderr
        assert result.exit_code == 0

    finally:
        sys.path.remove(str(tmp_path))


def write_produce_modules(tmp_path):
    """Write the command modules the sectioned lazy-group tests import."""
    (tmp_path / "apple_cmd.py").write_text(
        dedent(
            """
            from click_extra import command, echo


            @command
            def apple_cli():
                "Count the apples."
                echo("apples = 3")
            """
        )
    )

    (tmp_path / "banana_cmd.py").write_text(
        dedent(
            """
            from click_extra import command, echo


            @command
            def banana_cli():
                "Count the bananas."
                echo("bananas = 5")
            """
        )
    )

    (tmp_path / "carrot_cmd.py").write_text(
        dedent(
            """
            from click_extra import command, echo


            @command
            def carrot_cli():
                "Count the carrots."
                echo("carrots = 7")
            """
        )
    )


def test_lazy_group_sections(invoke, tmp_path):
    """A `LazySubcommand` files its command under the section it declares."""
    write_produce_modules(tmp_path)

    fruits = cloup.Section("Fruits")
    vegetables = cloup.Section("Vegetables")

    # Sections are declared out of alphabetical order, and interleaved, to prove the
    # help screen follows declaration order instead of import order.
    @click.group(
        cls=LazyGroup,
        lazy_subcommands={
            "carrot": LazySubcommand("carrot_cmd.carrot_cli", section=vegetables),
            "apple": LazySubcommand("apple_cmd.apple_cli", section=fruits),
            "banana": LazySubcommand("banana_cmd.banana_cli", section=fruits),
        },
        help="Count the produce.",
    )
    def basket():
        pass

    sys.path.insert(0, str(tmp_path))
    try:
        result = invoke(basket, "--help", color=False)
        assert result.stdout == dedent(
            """\
            Usage: basket [OPTIONS] COMMAND [ARGS]...

              Count the produce.

            Options:
              -h, --help  Show this message and exit.

            Vegetables:
              carrot  Count the carrots.

            Fruits:
              apple   Count the apples.
              banana  Count the bananas.

            Other commands:
              help    Show help for a command.
            """
        )
        assert not result.stderr
        assert result.exit_code == 0

        # A sectioned subcommand is still invocable.
        result = invoke(basket, "banana", color=False)
        assert result.stdout == "bananas = 5\n"
        assert not result.stderr
        assert result.exit_code == 0

    finally:
        sys.path.remove(str(tmp_path))


def test_lazy_group_section_shared_with_eager_subcommand(invoke, tmp_path):
    """A `Section` can hold both eagerly and lazily registered subcommands."""
    write_produce_modules(tmp_path)

    @click_extra.command
    def cherry():
        """Count the cherries."""
        echo("cherries = 11")

    fruits = cloup.Section("Fruits", [cherry])

    @click.group(
        cls=LazyGroup,
        sections=[fruits],
        lazy_subcommands={"apple": LazySubcommand("apple_cmd.apple_cli", fruits)},
        help="Count the produce.",
    )
    def basket():
        pass

    sys.path.insert(0, str(tmp_path))
    try:
        result = invoke(basket, "--help", color=False)
        assert result.stdout == dedent(
            """\
            Usage: basket [OPTIONS] COMMAND [ARGS]...

              Count the produce.

            Options:
              -h, --help  Show this message and exit.

            Fruits:
              cherry  Count the cherries.
              apple   Count the apples.

            Other commands:
              help    Show help for a command.
            """
        )
        assert not result.stderr
        assert result.exit_code == 0

    finally:
        sys.path.remove(str(tmp_path))


def test_lazy_group_no_default_section(invoke, tmp_path):
    """`fallback_to_default_section=False` hides a subcommand but keeps it invocable."""
    write_produce_modules(tmp_path)

    @click.group(
        cls=LazyGroup,
        lazy_subcommands={
            "apple": "apple_cmd.apple_cli",
            "carrot": LazySubcommand(
                "carrot_cmd.carrot_cli",
                fallback_to_default_section=False,
            ),
        },
        help="Count the produce.",
    )
    def basket():
        pass

    sys.path.insert(0, str(tmp_path))
    try:
        result = invoke(basket, "--help", color=False)
        assert result.stdout == dedent(
            """\
            Usage: basket [OPTIONS] COMMAND [ARGS]...

              Count the produce.

            Options:
              -h, --help  Show this message and exit.

            Commands:
              apple  Count the apples.
              help   Show help for a command.
            """
        )
        assert not result.stderr
        assert result.exit_code == 0

        result = invoke(basket, "carrot", color=False)
        assert result.stdout == "carrots = 7\n"
        assert not result.stderr
        assert result.exit_code == 0

    finally:
        sys.path.remove(str(tmp_path))


def test_lazy_subcommand_normalizes_bare_import_paths(tmp_path):
    """A bare import path is normalized into a `LazySubcommand`."""

    @click.group(
        cls=LazyGroup,
        lazy_subcommands={"apple": "apple_cmd.apple_cli"},
    )
    def basket():
        pass

    assert basket.lazy_subcommands == {
        "apple": LazySubcommand(
            "apple_cmd.apple_cli",
            section=None,
            fallback_to_default_section=True,
        ),
    }


def test_decorator_overrides():
    """Ensure our decorators are not just alias of Click and Cloup ones."""

    assert click_extra.command not in (click.command, cloup.command)
    assert click_extra.group not in (click.group, cloup.group)

    assert click_extra.Option not in (click.Option, cloup.Option)
    assert issubclass(click_extra.Option, click.Option)
    assert issubclass(click_extra.Option, cloup.Option)

    assert click_extra.Argument not in (click.Argument, cloup.Argument)
    assert issubclass(click_extra.Argument, click.Argument)
    assert issubclass(click_extra.Argument, cloup.Argument)

    assert click_extra.option not in (click.option, cloup.option)
    assert click_extra.argument not in (click.argument, cloup.argument)

    assert click_extra.version_option not in (
        click.version_option,
        cloup.version_option,
    )


@pytest.mark.parametrize(
    ("klass", "should_raise"),
    (
        (click.Command, True),
        (click.Group, True),
        (cloup.Command, True),
        (cloup.Group, True),
        (click_extra.Command, False),
        (click_extra.Group, False),
        (str, True),
        (int, True),
    ),
)
def test_decorator_cls_parameter(klass, should_raise):
    """Decorators accept custom cls parameters."""

    class Custom(klass):  # type: ignore[valid-type, misc]
        pass

    context = pytest.raises(TypeError) if should_raise else nullcontext()

    with context:
        command(cls=Custom)


def test_help_shows_group_help(invoke):
    """``mycli help`` produces the same output as ``mycli --help``."""

    @group
    def cli():
        """My CLI."""

    @cli.command()
    @option("--name", help="Who to greet.")
    def greet(name):
        """Greet someone."""

    result_help = invoke(cli, "help", color=False)
    result_flag = invoke(cli, "--help", color=False)

    assert result_help.exit_code == 0
    assert result_flag.exit_code == 0
    assert result_help.stdout == result_flag.stdout


def test_help_shows_subcommand_help(invoke):
    """``mycli help greet`` matches ``mycli greet --help``."""

    @group
    def cli():
        pass

    @cli.command()
    @option("--name", help="Who to greet.")
    def greet(name):
        """Greet someone."""

    result_help = invoke(cli, "help", "greet", color=False)
    result_flag = invoke(cli, "greet", "--help", color=False)

    assert result_help.exit_code == 0
    assert result_flag.exit_code == 0
    assert result_help.stdout == result_flag.stdout


def test_help_nested_group(invoke):
    """``mycli help sub leaf`` resolves through nested groups."""

    @group
    def cli():
        pass

    @cli.group()
    def sub():
        """A sub-group."""

    @sub.command()
    @option("--count", type=int, help="Number of items.")
    def leaf(count):
        """A leaf command."""

    result = invoke(cli, "help", "sub", "leaf", color=False)
    assert result.exit_code == 0
    assert "A leaf command." in result.stdout
    assert "--count" in result.stdout


def test_help_nonexistent_subcommand(invoke):
    """``mycli help nosuch`` reports an error."""

    @group
    def cli():
        pass

    result = invoke(cli, "help", "nosuch", color=False)
    assert result.exit_code == 2
    assert "No such command" in result.output


def test_help_subcommand_of_non_group(invoke):
    """``mycli help leaf deeper`` errors when leaf is not a group."""

    @group
    def cli():
        pass

    @cli.command()
    def leaf():
        pass

    result = invoke(cli, "help", "leaf", "deeper", color=False)
    assert result.exit_code == 2
    assert "has no subcommands" in result.output


def test_help_disabled(invoke):
    """``help_command=False`` suppresses auto-injection."""

    @group(help_command=False)
    def cli():
        pass

    @cli.command()
    def sub():
        pass

    assert "help" not in cli.commands
    result = invoke(cli, "help", color=False)
    assert result.exit_code == 2


def test_help_user_override(invoke):
    """User-defined ``help`` subcommand replaces the auto-injected one."""

    @group
    def cli():
        pass

    @cli.command(name="help")
    def custom_help():
        """Custom help."""
        echo("Custom help output")

    assert not isinstance(cli.commands["help"], HelpCommand)
    result = invoke(cli, "help", color=False)
    assert "Custom help output" in result.stdout


def test_help_appears_in_listing(invoke):
    """The ``help`` subcommand is visible in the group's command list."""

    @group
    def cli():
        pass

    @cli.command()
    def greet():
        pass

    result = invoke(cli, "--help", color=False)
    assert "help" in result.stdout
    assert "Show help for a command." in result.stdout


def test_help_search(invoke):
    """``mycli help --search term`` finds matching subcommands."""

    @group
    def cli():
        pass

    @cli.command()
    @option("--output", help="Output file path.")
    def export(output):
        """Export data to a file."""

    @cli.command()
    @option("--format")
    def render(format):
        """Render the visualization."""

    result = invoke(cli, "help", "--search", "file", color=False)
    assert result.exit_code == 0
    assert "export" in result.stdout
    assert "render" not in result.stdout


def test_help_search_no_match(invoke):
    """``mycli help --search term`` with no matches."""

    @group
    def cli():
        pass

    @cli.command()
    def sub():
        pass

    result = invoke(cli, "help", "--search", "zzzzz", color=False)
    assert result.exit_code == 0
    assert "No commands matching" in result.stdout


def test_help_in_all_command_cli(invoke, all_command_cli):
    """The help subcommand works on the fixture CLI."""
    result = invoke(all_command_cli, "help", color=False)
    assert result.exit_code == 0
    assert "command-cli1" in result.stdout


def test_help_for_subcommand_in_all_command_cli(invoke, all_command_cli):
    """``help default-subcommand`` works on the fixture CLI."""
    result = invoke(all_command_cli, "help", "default-subcommand", color=False)
    assert result.exit_code == 0
    assert "default-subcommand" in result.stdout


def kitchen_group(**kwargs):
    """A group whose subcommands are declared out of alphabetical order."""

    @group(**kwargs)
    def kitchen():
        """Kitchen pipeline."""

    @kitchen.command()
    def prep():
        """Prep the ingredients."""

    @kitchen.command()
    def cook():
        """Cook the dish."""

    @kitchen.command()
    def plate():
        """Plate the dish."""

    return kitchen


def listed_subcommands(help_screen):
    """Names listed under the ``Commands:`` heading of a help screen."""
    _, _, tail = help_screen.partition("\nCommands:\n")
    return [line.split()[0] for line in tail.splitlines() if line.startswith("  ")]


subcommand_orders = pytest.mark.parametrize(
    ("group_kwargs", "expected"),
    (
        pytest.param({}, ["cook", "help", "plate", "prep"], id="default"),
        pytest.param(
            {"sort_subcommands": True},
            ["cook", "help", "plate", "prep"],
            id="alphabetical",
        ),
        pytest.param(
            {"sort_subcommands": False},
            ["prep", "cook", "plate", "help"],
            id="declaration",
        ),
        pytest.param(
            {"context_settings": {"sort_subcommands": False}},
            ["prep", "cook", "plate", "help"],
            id="declaration-from-context",
        ),
        pytest.param(
            {"subcommand_priorities": {"prep": 1, "cook": 2, "plate": 3}},
            ["prep", "cook", "plate", "help"],
            id="priorities",
        ),
        pytest.param(
            {"subcommand_priorities": {"prep": 1, "plate": 3, "cook": 1.5}},
            ["prep", "cook", "plate", "help"],
            id="fractional-wedge",
        ),
        pytest.param(
            {"subcommand_priorities": {"help": 1}},
            ["help", "cook", "plate", "prep"],
            id="promotion-leaves-the-rest-alphabetical",
        ),
        pytest.param(
            {"subcommand_priorities": {"prep": 200}},
            ["cook", "help", "plate", "prep"],
            id="demotion-past-the-default-line",
        ),
        pytest.param(
            {"sort_subcommands": False, "subcommand_priorities": {"plate": 1}},
            ["plate", "prep", "cook", "help"],
            id="priority-outranks-declaration",
        ),
    ),
)


@subcommand_orders
def test_subcommand_order_in_help_screen(invoke, group_kwargs, expected):
    """Cloup renders the help screen from sections, never from ``list_commands()``."""
    result = invoke(kitchen_group(**group_kwargs), "--help", color=False)
    assert result.exit_code == 0
    assert listed_subcommands(result.stdout) == expected


@subcommand_orders
def test_subcommand_order_in_list_commands(group_kwargs, expected):
    """The flat listing feeding ``--tree``, man pages, specs and completion."""
    cli = kitchen_group(**group_kwargs)
    ctx = make_resilient_context(cli, cli.name)
    assert cli.list_commands(ctx) == expected


def test_subcommand_order_agrees_across_renderers(invoke):
    """Every rendering of a command tree lists subcommands in the same order.

    Each renderer used to reach for its own accessor, so a group that ordered its
    subcommands could have its help screen disagree with its man page or its
    completion spec. They all go through ``list_commands()`` now, and this pins
    that down for the whole population rather than one renderer at a time.
    """
    yaml = pytest.importorskip("yaml")

    cli = kitchen_group(sort_subcommands=False)
    expected = ["prep", "cook", "plate", "help"]

    ctx = make_resilient_context(cli, cli.name)
    renderings = {"iter_subcommands": [name for name, _ in iter_subcommands(cli, ctx)]}

    result = invoke(cli, "--help", color=False)
    renderings["--help"] = listed_subcommands(result.stdout)

    result = invoke(cli, "--tree", color=False)
    renderings["--tree"] = [
        line.split()[1]
        for line in result.stdout.splitlines()
        if line.startswith(("├", "└"))
    ]

    result = invoke(cli, "--help-format", "markdown", color=False)
    section = result.stdout.partition("\n## Commands\n")[2].partition("\n## ")[0]
    renderings["markdown"] = [
        line.split("`")[1] for line in section.splitlines() if line.startswith("- `")
    ]

    result = invoke(cli, "--help-format", "carapace", color=False)
    renderings["carapace"] = [
        sub["name"] for sub in yaml.safe_load(result.stdout)["commands"]
    ]

    diverging = {name: order for name, order in renderings.items() if order != expected}
    assert not diverging, f"renderers out of order: {diverging}"


def test_option_order_agrees_across_renderers(invoke):
    """Every rendering of a command lists options in the same order.

    Cloup draws the ungrouped section last, and Click Extra sends its own groups
    past it, so a renderer reaching for its own accessor would let a help screen
    disagree with its man page or its completion spec. They all resolve the
    section order through ``split_option_groups()`` now.

    Pins the taxonomy too: each rendering is filtered down to the flags
    ``DEFAULT_OPTION_GROUPS`` declares, so the order they are declared in is the
    order a reader sees.
    """
    yaml = pytest.importorskip("yaml")

    @command
    @option("--city", help="City to forecast.")
    def forecast(city):
        """Show the weather forecast."""

    expected = ["--city", "--help"]
    for _, flags in DEFAULT_OPTION_GROUPS:
        expected.extend(flags)

    ctx = make_resilient_context(forecast, forecast.name)
    renderings = {
        "iter_params_for_display": [
            next(opt for opt in param.opts if opt.startswith("--"))
            for param in iter_params_for_display(forecast, ctx)
        ],
        "--help": re.findall(
            r"^  (?:-\w, )?(--[\w-]+)",
            invoke(forecast, "--help", color=False).stdout,
            re.MULTILINE,
        ),
        # Read as the long spelling, like the renderings above: Click 8.4
        # collects `--help`'s names through a set, so which of `-h` and
        # `--help` lands first there varies with the interpreter's hash seed.
        # Click 8.5.0 keeps their declaration order.
        "json": [
            next(name for name in opt["names"] if name.startswith("--"))
            for group in json.loads(
                invoke(forecast, "--help-format", "json", color=False).stdout
            )["option_groups"]
            for opt in group["options"]
        ],
    }

    # Carapace splits a CLI's own flags from the inherited ones, and gives each
    # spelling of a boolean pair its own entry.
    spec = yaml.safe_load(
        invoke(forecast, "--help-format", "carapace", color=False).stdout
    )
    renderings["carapace"] = [
        flag.split(", ")[-1].rstrip("=?*")
        for section in ("flags", "persistentflags")
        for flag in spec.get(section, {})
    ]

    diverging = {
        name: kept
        for name, order in renderings.items()
        if (kept := [flag for flag in order if flag in set(expected)]) != expected
    }
    assert not diverging, f"renderers out of order: {diverging}"


ARGUMENT_HELP_CLICK_VERSION = (8, 5)
"""Click release that gave `click.Argument` a `help` parameter of its own.

Below it a plain `click.argument` rejects the keyword outright, so the matrix
cells pinning an older Click inside the supported range have nothing to render.
Cloup and Click Extra carry their own `Argument`, which accepted a description
all along and is checked on every cell.
"""


@pytest.mark.parametrize(
    "argument_decorator",
    (
        pytest.param(
            click.argument,
            id="click",
            marks=pytest.mark.skipif(
                tuple(
                    int(p) for p in importlib.metadata.version("click").split(".")[:2]
                )
                < ARGUMENT_HELP_CLICK_VERSION,
                reason="`click.Argument` takes a `help` since Click 8.5.",
            ),
        ),
        pytest.param(cloup.argument, id="cloup"),
        pytest.param(argument, id="click_extra"),
    ),
)
def test_argument_help_agrees_across_renderers(invoke, argument_decorator):
    """An argument's help reaches every rendering, whatever its `Argument` class.

    Click 8.5.0 gave `click.Argument` a `help` parameter of its own. Cloup reads a
    description off a `cloup.Argument` alone, so a plain `click.argument` drew a
    blank `Positional arguments` entry while the man page and the JSON export
    carried its text. See https://github.com/janluke/cloup/issues/210.
    """

    @command
    @argument_decorator("city", help="City to forecast.")
    def forecast(city):
        """Show the weather forecast."""

    help_screen = invoke(forecast, "--help", color=False).stdout
    assert re.search(r"^  CITY +City to forecast\.$", help_screen, re.MULTILINE)

    doc = json.loads(invoke(forecast, "--help-format", "json", color=False).stdout)
    assert doc["arguments"] == [{"metavar": "CITY", "help": "City to forecast."}]


@pytest.mark.parametrize(
    ("deprecated", "label"),
    (
        pytest.param(True, "(DEPRECATED)", id="bool"),
        pytest.param(
            "use `forecast` instead",
            "(DEPRECATED: use `forecast` instead)",
            id="reason",
        ),
    ),
)
def test_deprecated_command_label_matches_click(invoke, deprecated, label):
    """A deprecated command carries Click's own marker, reason string included.

    Cloup prefixes `(Deprecated) ` to the description, a form Click left behind in
    8.2.0 and which has nowhere to put the reason a `deprecated` string carries.
    See https://github.com/janluke/cloup/issues/211.

    The marker is checked on the help screen and on
    {func}`~click_extra.parameters.full_short_help`, which feeds `--tree`, the man
    page, the JSON export and the completion specs.
    """

    @command(params=[], deprecated=deprecated)
    def legacy():
        """Show the weather forecast."""

    @click.command(deprecated=deprecated)
    def reference():
        """Show the weather forecast."""

    expected = f"Show the weather forecast. {label}"
    assert expected in invoke(legacy, "--help", color=False).stdout
    assert expected in invoke(reference, "--help", color=False).stdout
    assert full_short_help(legacy) == expected


def test_every_default_option_lands_in_a_section():
    """No option `default_params()` returns escapes `DEFAULT_OPTION_GROUPS`.

    An option no section claims stays ungrouped, which draws it in the command's
    own `Options` block where it reads as one the CLI author declared. Nothing
    else reports that: the help screen renders, and every cross-renderer check
    still agrees, because they all read the same wrong layout.
    """
    ungrouped = [
        param.opts
        for param in default_params()
        if not isinstance(getattr(param, "group", None), ExtraOptionGroup)
    ]
    assert not ungrouped, f"default options claimed by no section: {ungrouped}"


def test_default_option_groups_name_no_stale_flag():
    """Every flag `DEFAULT_OPTION_GROUPS` declares is one `default_params()` returns.

    A renamed or dropped option otherwise leaves a dead entry behind. And a flag
    landing in two sections is silently taken by the later one, since
    `_assign_option_groups` writes them in order.
    """
    declared = [flag for _, flags in DEFAULT_OPTION_GROUPS for flag in flags]
    available = {
        opt
        for param in default_params()
        for opt in (*param.opts, *param.secondary_opts)
    }
    assert not set(declared) - available, (
        f"sections name unknown flags: {sorted(set(declared) - available)}"
    )

    duplicated = sorted({flag for flag in declared if declared.count(flag) > 1})
    assert not duplicated, f"flags claimed by more than one section: {duplicated}"


def test_lazy_group_subcommand_order_is_stable_across_loading(tmp_path, monkeypatch):
    """A lazy subcommand holds its slot before and after it is imported.

    Importing appends the command to ``self.commands``, so registration order read
    off that dictionary alone would reshuffle mid-run.
    """
    for name in ("simmer", "chop", "roast"):
        (tmp_path / f"{name}_cmd.py").write_text(
            dedent(
                f"""\
                from click_extra import command

                @command
                def {name}_cli():
                    pass
                """
            ),
            encoding="utf-8",
        )
    monkeypatch.syspath_prepend(str(tmp_path))

    cli = LazyGroup(
        name="kitchen",
        sort_subcommands=False,
        lazy_subcommands={
            "simmer": "simmer_cmd.simmer_cli",
            "chop": "chop_cmd.chop_cli",
            "roast": "roast_cmd.roast_cli",
        },
    )
    ctx = make_resilient_context(cli, cli.name)
    expected = ["simmer", "chop", "roast", "help"]

    assert cli.list_commands(ctx) == expected
    # Import one of them out of order, then ask again.
    assert cli.get_command(ctx, "roast") is not None
    assert cli.list_commands(ctx) == expected


def test_lazy_group_defaults_to_alphabetical_order():
    """Sorting moved from ``__init__`` to listing time, with the same result."""
    cli = LazyGroup(
        name="kitchen",
        lazy_subcommands={
            "simmer": "simmer_cmd.simmer_cli",
            "chop": "chop_cmd.chop_cli",
            "roast": "roast_cmd.roast_cli",
        },
    )
    ctx = make_resilient_context(cli, cli.name)
    assert cli.list_commands(ctx) == ["chop", "help", "roast", "simmer"]


def test_option_priorities_leave_processing_order_alone(invoke):
    """The help screen reorders while ``params`` and the callbacks do not.

    ``click.core.iter_params_for_processing`` breaks eager-option ties on
    declaration order, which is why ``--time`` measures everything and
    ``--accessible`` lowers the ``--color`` default before it resolves. Reordering
    the help screen must not disturb any of that.
    """
    fired = []

    def record(ctx, param, value):
        fired.append(param.name)

    @command(
        params=[],
        option_priorities={"--zest": 1, "--simmer": 2, "--chop": 3},
    )
    @option("--chop", is_eager=True, expose_value=False, callback=record)
    @option("--simmer", is_eager=True, expose_value=False, callback=record)
    @option("--zest", is_eager=True, expose_value=False, callback=record)
    def cli():
        """Kitchen."""

    declared = ["chop", "simmer", "zest"]
    assert [p.name for p in cli.params] == declared
    assert [
        p.name
        for p in cli.ungrouped_options  # type: ignore[attr-defined]
    ] == ["zest", "simmer", "chop"]

    result = invoke(cli, "--help", color=False)
    assert result.exit_code == 0
    options = result.stdout.partition("\nOptions:\n")[2]
    assert options.index("--zest") < options.index("--simmer") < options.index("--chop")

    fired.clear()
    result = invoke(cli, color=False)
    assert result.exit_code == 0
    assert fired == declared


def test_option_priorities_match_flags_then_destination():
    """A flag pair sharing one destination stays addressable one flag at a time."""

    @command(params=[])
    @option("--sweet/--savory", default=True)
    @option("--plate")
    def cli(sweet, plate):
        """Kitchen."""

    priority = cli.param_priority  # type: ignore[attr-defined]
    assert priority(cli.params[0]) == DEFAULT_PRIORITY

    @command(params=[], option_priorities={"--savory": 1, "plate": 2})
    @option("--sweet/--savory", default=True)
    @option("--plate")
    def keyed(sweet, plate):
        """Kitchen."""

    # `--savory` is the secondary flag of the `sweet` destination, and `plate` is
    # matched by destination name rather than by flag.
    priority = keyed.param_priority  # type: ignore[attr-defined]
    assert [
        p.name
        for p in keyed.ungrouped_options  # type: ignore[attr-defined]
    ] == ["sweet", "plate"]
    assert priority(keyed.params[0]) == 1
    assert priority(keyed.params[1]) == 2


def test_option_priorities_never_reorder_positional_arguments():
    """Argument order is part of the command's grammar, not of its presentation."""

    @command(params=[], option_priorities={"first": 9, "second": 1})
    @argument("first")
    @argument("second")
    def cli(first, second):
        """Kitchen."""

    arguments = cli.arguments  # type: ignore[attr-defined]
    priority = cli.param_priority  # type: ignore[attr-defined]
    assert [p.name for p in arguments] == ["first", "second"]
    assert all(priority(p) == DEFAULT_PRIORITY for p in arguments)
