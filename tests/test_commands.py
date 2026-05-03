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

import inspect
import os
import sys
from contextlib import nullcontext
from textwrap import dedent

import click
import cloup
import pytest

import click_extra
from click_extra import (
    ExtraVersionOption,
    HelpCommand,
    LazyGroup,
    command,
    echo,
    group,
    option,
    option_group,
    pass_context,
    version_option,
)
from click_extra.commands import default_extra_params
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

    click_members = {
        name
        for name, member in inspect.getmembers(click)
        if not name.startswith("_") and not inspect.ismodule(member)
    }
    assert click_members <= click_extra_members

    cloup_members = {m for m in cloup.__all__ if not m.startswith("_")}
    assert cloup_members <= click_extra_members


@pytest.fixture
def all_command_cli():
    """A CLI that is mixing all variations and flavors of subcommands."""

    def versioned_extra_params():
        params = default_extra_params()
        for p in params:
            if isinstance(p, ExtraVersionOption):
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
    """``ExtraCommand.parse_args`` improves error messages for single-dash
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
    result = invoke(all_command_cli, cmd_id, param)

    colored_help_header = (
        r"It works!\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mUsage:\x1b\[0m "
        rf"\x1b\[97mcommand-cli1 {cmd_id}\x1b\[0m"
        r" \x1b\[36m\x1b\[2m\[OPTIONS\]\x1b\[0m\n"
        r"\n"
        r"\x1b\[94m\x1b\[1m\x1b\[4mOptions:\x1b\[0m\n"
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
                r"  \x1b\[36m-h\x1b\[0m, \x1b\[36m--help\x1b\[0m"
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

    result = invoke(bare_cli, param)
    assert (
        "\n"
        "\x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m\n"
        "  \x1b[36m-h\x1b[0m, \x1b[36m--help\x1b[0m  Show this message and exit.\n"
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
    @version_option(version="0.1")
    def cli():
        pass

    result = invoke(cli, "--help", color=False)
    assert result.stdout.endswith(
        "  --verbosity LEVEL       Either CRITICAL, ERROR, WARNING, INFO, DEBUG.\n"
        "                          [default: WARNING]\n"
        "  -v, --verbose           Increase the default WARNING verbosity by one level\n"
        "                          for each additional repetition of the option.\n"
        "                          [default: 0]\n"
        "  --version               Show the version and exit.\n"
        "  --version               Show the version and exit.\n"
        "  -h, --help              Show this message and exit.\n"
    )
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
            "  --flag2                 [env var: "
            + ("CUSTOM2" if os.name == "nt" else "custom2")
            + ", CLI_FLAG2]\n"
            "  --flag3\n",
        ),
        # Click Extra allow bypassing its global show_envvar setting.
        (
            command,
            {"show_envvar": None},
            "  --flag1\n"
            "  --flag2                 [env var: "
            + ("CUSTOM2" if os.name == "nt" else "custom2")
            + ", CLI_FLAG2]\n"
            "  --flag3\n",
        ),
        # Click Extra force the show_envvar value on all options.
        (
            command,
            {"show_envvar": True},
            "  --flag1                 [env var: "
            + ("CUSTOM1" if os.name == "nt" else "custom1")
            + ", CLI_FLAG1]\n"
            "  --flag2                 [env var: "
            + ("CUSTOM2" if os.name == "nt" else "custom2")
            + ", CLI_FLAG2]\n"
            "  --flag3                 [env var: "
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
        (click_extra.Command, True),
        (click_extra.Group, True),
        (click_extra.ExtraCommand, False),
        (click_extra.ExtraGroup, False),
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


class TestHelpSubcommand:
    """Tests for the auto-injected ``help`` subcommand."""

    def test_help_shows_group_help(self, invoke):
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

    def test_help_shows_subcommand_help(self, invoke):
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

    def test_help_nested_group(self, invoke):
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

    def test_help_nonexistent_subcommand(self, invoke):
        """``mycli help nosuch`` reports an error."""

        @group
        def cli():
            pass

        result = invoke(cli, "help", "nosuch", color=False)
        assert result.exit_code == 2
        assert "No such command" in result.output

    def test_help_subcommand_of_non_group(self, invoke):
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

    def test_help_disabled(self, invoke):
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

    def test_help_user_override(self, invoke):
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

    def test_help_appears_in_listing(self, invoke):
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

    def test_help_search(self, invoke):
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

    def test_help_search_no_match(self, invoke):
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

    def test_help_in_all_command_cli(self, invoke, all_command_cli):
        """The help subcommand works on the fixture CLI."""
        result = invoke(all_command_cli, "help", color=False)
        assert result.exit_code == 0
        assert "command-cli1" in result.stdout

    def test_help_for_subcommand_in_all_command_cli(self, invoke, all_command_cli):
        """``help default-subcommand`` works on the fixture CLI."""
        result = invoke(all_command_cli, "help", "default-subcommand", color=False)
        assert result.exit_code == 0
        assert "default-subcommand" in result.stdout
