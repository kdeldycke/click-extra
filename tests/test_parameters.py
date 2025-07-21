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

import re
from os.path import sep
from pathlib import Path
from textwrap import dedent

import click
import pytest
from tabulate import tabulate

from click_extra import (
    BOOL,
    FLOAT,
    INT,
    STRING,
    UNPROCESSED,
    UUID,
    Choice,
    DateTime,
    File,
    FloatRange,
    IntRange,
    ParamType,
    Tuple,
    argument,
    echo,
    get_app_dir,
    option,
    search_params,
)
from click_extra.decorators import extra_command, extra_group, show_params_option
from click_extra.parameters import ShowParamsOption
from click_extra.pytest import command_decorators

from .test_colorize import HashType


class Custom(ParamType):
    """A dummy custom type."""

    name = "Custom"

    def convert(self, value, param, ctx):
        if value is not None:
            assert isinstance(value, str)
        return value


@pytest.mark.parametrize("option_decorator", (show_params_option, show_params_option()))
def test_params_auto_types(invoke, option_decorator):
    """Check parameters types and structure are properly derived from CLI."""

    @click.command
    @option("--flag1/--no-flag1")
    @option("--flag2", is_flag=True)
    @option("--str-param1", type=str)
    @option("--str-param2", type=STRING)
    @option("--int-param1", type=int)
    @option("--int-param2", type=INT)
    @option("--float-param1", type=float)
    @option("--float-param2", type=FLOAT)
    @option("--bool-param1", type=bool)
    @option("--bool-param2", type=BOOL)
    @option("--uuid-param", type=UUID)
    @option("--unprocessed-param", type=UNPROCESSED)
    @option("--file-param", type=File())
    @option("--path-param", type=click.Path())
    @option("--choice-param", type=Choice(("a", "b", "c")))
    @option("--number-choice", type=Choice([1, 2, 3]))
    @option("--hash-type", type=Choice(HashType))
    @option("--int-range-param", type=IntRange())
    @option("--count-param", count=True)  # See issue #170.
    @option("--float-range-param", type=FloatRange())
    @option("--datetime-param", type=DateTime())
    @option("--custom-param", type=Custom())  # See issue #721.
    @option("--tuple1", nargs=2, type=Tuple([str, int]))
    @option("--list1", multiple=True)
    @option("--hidden-param", hidden=True)  # See issue #689.
    @argument("file_arg1", type=File("w"))
    @argument("file_arg2", type=File("w"), nargs=-1)
    @option_decorator
    def params_introspection(
        flag1,
        flag2,
        str_param1,
        str_param2,
        int_param1,
        int_param2,
        float_param1,
        float_param2,
        bool_param1,
        bool_param2,
        uuid_param,
        unprocessed_param,
        file_param,
        path_param,
        choice_param,
        number_choice,
        hash_type,
        int_range_param,
        count_param,
        float_range_param,
        datetime_param,
        custom_param,
        tuple1,
        list1,
        hidden_param,
        file_arg1,
        file_arg2,
    ):
        echo("Works!")

    # Invoke the --show-params option to trigger the introspection.
    result = invoke(
        params_introspection,
        "--show-params",
        "random_file1",
        "random_file2",
        color=False,
    )

    assert result.exit_code == 0
    assert result.stdout != "Works!\n"

    show_param_option = search_params(params_introspection.params, ShowParamsOption)
    assert show_param_option.params_template == {
        "params-introspection": {
            "flag1": None,
            "flag2": None,
            "str_param1": None,
            "str_param2": None,
            "int_param1": None,
            "int_param2": None,
            "float_param1": None,
            "float_param2": None,
            "bool_param1": None,
            "bool_param2": None,
            "uuid_param": None,
            "unprocessed_param": None,
            "file_param": None,
            "path_param": None,
            "show_params": None,
            "choice_param": None,
            "number_choice": None,
            "hash_type": None,
            "int_range_param": None,
            "count_param": None,
            "float_range_param": None,
            "datetime_param": None,
            "custom_param": None,
            "tuple1": None,
            "list1": None,
            "hidden_param": None,
            "file_arg1": None,
            "file_arg2": None,
            "help": None,
        },
    }
    assert show_param_option.params_types == {
        "params-introspection": {
            "flag1": bool,
            "flag2": bool,
            "str_param1": str,
            "str_param2": str,
            "int_param1": int,
            "int_param2": int,
            "float_param1": float,
            "float_param2": float,
            "bool_param1": bool,
            "bool_param2": bool,
            "uuid_param": str,
            "unprocessed_param": str,
            "file_param": str,
            "path_param": str,
            "show_params": bool,
            "choice_param": str,
            "number_choice": str,
            "hash_type": str,
            "int_range_param": int,
            "count_param": int,
            "float_range_param": float,
            "datetime_param": str,
            "custom_param": str,
            "tuple1": list,
            "list1": list,
            "hidden_param": str,
            "file_arg1": str,
            "file_arg2": list,
            "help": bool,
        },
    }


# Skip click extra's commands, as show_params option is already part of the default.
@pytest.mark.parametrize("cmd_decorator", command_decorators(no_extra=True))
@pytest.mark.parametrize("option_decorator", (show_params_option, show_params_option()))
def test_standalone_show_params_option(invoke, cmd_decorator, option_decorator):
    @cmd_decorator
    @option_decorator
    def show_params():
        echo("It works!")

    result = invoke(show_params, "--show-params")
    assert result.exit_code == 0

    table = [
        (
            "show-params.help",
            "click.core.Option",
            "--help",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "",
            "",
        ),
        (
            "show-params.show_params",
            "click_extra.parameters.ShowParamsOption",
            "--show-params",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "",
            "COMMANDLINE",
        ),
    ]
    output = tabulate(
        table,
        headers=ShowParamsOption.TABLE_HEADERS,
        tablefmt="rounded_outline",
        disable_numparse=True,
    )
    assert result.stdout == f"{output}\n"

    assert re.fullmatch(
        r"warning: Cannot extract parameters values: "
        r"<(Group|Command) show-params> does not inherits from ExtraCommand\.\n",
        result.stderr,
    )


def test_integrated_show_params_option(invoke, create_config):
    @extra_command
    @option("--int-param1", type=int, default=10)
    @option("--int-param2", type=int, default=555)
    @option("--hidden-param", hidden=True)  # See issue #689.
    @option("--custom-param", type=Custom())  # See issue #721.
    def show_params_cli(int_param1, int_param2, hidden_param, custom_param):
        echo(f"int_param1 is {int_param1!r}")
        echo(f"int_param2 is {int_param2!r}")
        echo(f"hidden_param is {hidden_param!r}")
        echo(f"custom_param is {custom_param!r}")

    conf_file = dedent(
        """
        [show-params-cli]
        int_param1 = 3
        extra_value = "unallowed"
        """,
    )
    conf_path = create_config("show-params-cli.toml", conf_file)

    raw_args = [
        "--verbosity",
        "DeBuG",
        "--config",
        str(conf_path),
        "--int-param1",
        "9999",
        "--show-params",
        "--help",
    ]
    result = invoke(show_params_cli, *raw_args, color=False)

    assert result.exit_code == 0
    assert f"debug: click_extra.raw_args: {raw_args!r}\n" in result.stderr

    table = [
        (
            "show-params-cli.color",
            "click_extra.colorize.ColorOption",
            "--color, --ansi / --no-color, --no-ansi",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_COLOR",
            True,
            True,
            "DEFAULT",
        ),
        (
            "show-params-cli.config",
            "click_extra.config.ConfigOption",
            "-C, --config CONFIG_PATH",
            "click.types.StringParamType",
            "str",
            "✘",
            "✘",
            "✘",
            "SHOW_PARAMS_CLI_CONFIG",
            (
                f"'{Path(get_app_dir('show-params-cli')).resolve()}{sep}"
                "*.{toml,yaml,yml,json,ini,xml}'"
            ),
            str(conf_path),
            "COMMANDLINE",
        ),
        (
            "show-params-cli.custom_param",
            "cloup._params.Option",
            "--custom-param CUSTOM",
            "tests.test_parameters.Custom",
            "str",
            "✘",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_CUSTOM_PARAM",
            "None",
            None,
            "DEFAULT",
        ),
        (
            "show-params-cli.help",
            "click.core.Option",
            "-h, --help",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✘",
            "SHOW_PARAMS_CLI_HELP",
            False,
            True,
            "COMMANDLINE",
        ),
        (
            "show-params-cli.hidden_param",
            "cloup._params.Option",
            "--hidden-param TEXT",
            "click.types.StringParamType",
            "str",
            "✓",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_HIDDEN_PARAM",
            "None",
            None,
            "DEFAULT",
        ),
        (
            "show-params-cli.int_param1",
            "cloup._params.Option",
            "--int-param1 INTEGER",
            "click.types.IntParamType",
            "int",
            "✘",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_INT_PARAM1",
            3,
            9999,
            "COMMANDLINE",
        ),
        (
            "show-params-cli.int_param2",
            "cloup._params.Option",
            "--int-param2 INTEGER",
            "click.types.IntParamType",
            "int",
            "✘",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_INT_PARAM2",
            555,
            555,
            "DEFAULT",
        ),
        (
            "show-params-cli.show_params",
            "click_extra.parameters.ShowParamsOption",
            "--show-params",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✘",
            "SHOW_PARAMS_CLI_SHOW_PARAMS",
            False,
            True,
            "COMMANDLINE",
        ),
        (
            "show-params-cli.time",
            "click_extra.timer.TimerOption",
            "--time / --no-time",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_TIME",
            False,
            False,
            "DEFAULT",
        ),
        (
            "show-params-cli.verbose",
            "click_extra.logging.VerboseOption",
            "-v, --verbose",
            "click.types.IntRange",
            "int",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_VERBOSE",
            "0",
            "0",
            "DEFAULT",
        ),
        (
            "show-params-cli.verbosity",
            "click_extra.logging.VerbosityOption",
            "--verbosity LEVEL",
            "click.types.Choice",
            "str",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_VERBOSITY",
            "<LogLevel.WARNING: 30>",
            "DeBuG",
            "COMMANDLINE",
        ),
        (
            "show-params-cli.version",
            "click_extra.version.ExtraVersionOption",
            "--version",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✘",
            "SHOW_PARAMS_CLI_VERSION",
            False,
            False,
            "DEFAULT",
        ),
    ]
    output = tabulate(
        table,
        headers=ShowParamsOption.TABLE_HEADERS,
        tablefmt="rounded_outline",
        disable_numparse=True,
    )
    assert result.stdout == f"{output}\n"


def test_recurse_subcommands(invoke):
    @extra_group(params=[ShowParamsOption()])
    def show_params_cli_main():
        echo("main cmd")

    @show_params_cli_main.group(params=[])
    def show_params_sub_cmd():
        echo("subcommand")

    @show_params_sub_cmd.command()
    @option("--int-param", type=int, default=10)
    def show_params_sub_sub_cmd(int_param):
        echo(f"subsubcommand int_param is {int_param!r}")

    result = invoke(show_params_cli_main, "--show-params", color=False)

    table = [
        (
            "show-params-cli-main.help",
            "click.core.Option",
            "-h, --help",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "SHOW_PARAMS_CLI_MAIN_HELP",
            False,
            False,
            "DEFAULT",
        ),
        (
            "show-params-cli-main.show_params",
            "click_extra.parameters.ShowParamsOption",
            "--show-params",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "SHOW_PARAMS_CLI_MAIN_SHOW_PARAMS",
            False,
            True,
            "COMMANDLINE",
        ),
        (
            "show-params-cli-main.show-params-sub.help",
            "click.core.Option",
            "-h, --help",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "SHOW_PARAMS_CLI_MAIN_HELP",  # XXX Should be SHOW_PARAMS_SUB_HELP
            False,
            False,
            "DEFAULT",
        ),
        (
            "show-params-cli-main.show-params-sub.show-params-sub-sub.help",
            "click.core.Option",
            "-h, --help",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "SHOW_PARAMS_CLI_MAIN_HELP",  # XXX Should be SHOW_PARAMS_SUB_SUB_HELP
            False,
            False,
            "DEFAULT",
        ),
        (
            "show-params-cli-main.show-params-sub.show-params-sub-sub.int_param",
            "cloup._params.Option",
            "--int-param INTEGER",
            "click.types.IntParamType",
            "int",
            "✘",
            "✓",
            "",
            "SHOW_PARAMS_SUB_SUB_INT_PARAM, SHOW_PARAMS_CLI_MAIN_INT_PARAM",
            10,
            10,
            "DEFAULT",
        ),
    ]
    output = tabulate(
        table,
        headers=ShowParamsOption.TABLE_HEADERS,
        tablefmt="rounded_outline",
        disable_numparse=True,
    )
    assert result.stdout == f"{output}\n"
