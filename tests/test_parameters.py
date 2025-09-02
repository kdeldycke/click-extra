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
from itertools import permutations
from os.path import sep
from pathlib import Path
from textwrap import dedent
from typing import Sequence

import click
import pytest
from boltons.strutils import strip_ansi
from extra_platforms import is_windows

from click_extra import (
    BOOL,
    FLOAT,
    INT,
    STRING,
    UNPROCESSED,
    UNSET,
    UUID,
    Choice,
    DateTime,
    File,
    FloatRange,
    IntRange,
    ParamType,
    ShowParamsOption,
    TableFormat,
    Tuple,
    argument,
    color_option,
    echo,
    extra_command,
    extra_group,
    get_app_dir,
    option,
    render_table,
    search_params,
    show_params_option,
    table_format_option,
)
from click_extra.pytest import command_decorators

from .test_colorize import HashType


class Custom(ParamType):
    """A dummy custom type."""

    name = "Custom"

    def convert(self, value, param, ctx):
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
            "flag1": [bool],
            "flag2": [bool],
            "str_param1": [str],
            "str_param2": [str],
            "int_param1": [int],
            "int_param2": [int],
            "float_param1": [float],
            "float_param2": [float],
            "bool_param1": [bool],
            "bool_param2": [bool],
            "uuid_param": [str],
            "unprocessed_param": [str],
            "file_param": [str],
            "path_param": [str],
            "show_params": [bool],
            "choice_param": [str],
            "number_choice": [str],
            "hash_type": [str],
            "int_range_param": [int],
            "count_param": [int],
            "float_range_param": [float],
            "datetime_param": [str],
            "custom_param": [str],
            "tuple1": [list],
            "list1": [list],
            "hidden_param": [str],
            "file_arg1": [str],
            "file_arg2": [list],
            "help": [bool],
        },
    }


def assert_table_content(
    output: str,
    expected_table: Sequence[Sequence[str]],
    table_format: TableFormat | None = None,
) -> None:
    """Helper to assert the content of a rendered table in the output."""
    # Crudly parse the rendered table from the output, as if produced with the
    # default style.
    extracted_table = []
    for line in output.strip().splitlines()[3:-1]:
        columns = [col.strip() for col in re.split(r"\s*\│\s*", line[1:-1])]
        assert len(columns) == len(ShowParamsOption.TABLE_HEADERS)
        extracted_table.append(tuple(columns))

    # Compare tables row by row to get cleaner assertion errors.
    for index in range(len(expected_table)):
        expected_strings = tuple(map(str, expected_table[index]))
        assert len(expected_strings) == len(ShowParamsOption.TABLE_HEADERS)
        assert extracted_table[index] == expected_strings

    # Check the rendering style of the table.
    rendered_table = render_table(
        expected_table,
        headers=ShowParamsOption.TABLE_HEADERS,
        table_format=table_format,
    )
    assert output == f"{rendered_table}\n"


# Skip click extra's commands, as show_params option is already part of the default.
@pytest.mark.parametrize("cmd_decorator", command_decorators(no_extra=True))
@pytest.mark.parametrize("option_decorator", (show_params_option, show_params_option()))
def test_standalone_show_params_option(
    invoke, cmd_decorator, option_decorator, assert_output_regex
):
    @cmd_decorator
    @option_decorator
    def show_params():
        echo("It works!")

    result = invoke(show_params, "--show-params")
    assert result.exit_code == 0

    expected_table = [
        (
            "show-params.help",
            "--help",
            "click.core.Option",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "None",
            "",
        ),
        (
            "show-params.show_params",
            "--show-params",
            "click_extra.parameters.ShowParamsOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "None",
            "COMMANDLINE",
        ),
    ]

    assert_table_content(result.stdout, expected_table)

    if result.stderr:
        assert_output_regex(
            result.stderr,
            r"warning: Cannot extract parameters values: "
            r"<(Group|Command) show-params> does not inherits from ExtraCommand\.\n",
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

    expected_table = [
        (
            "show-params-cli.color",
            "--color, --ansi / --no-color, --no-ansi",
            "click_extra.colorize.ColorOption",
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
            "--config CONFIG_PATH",
            "click_extra.config.ConfigOption",
            "click.types.UnprocessedParamType",
            "str",
            "✘",
            "✘",
            "✘",
            "SHOW_PARAMS_CLI_CONFIG",
            # On Windows, backslashes are double-escaped in Path string repr.
            (
                f"'{Path(get_app_dir('show-params-cli')).resolve()}{sep}"
                "*.{toml,yaml,yml,json,ini,xml}'"
            ).replace("\\", "\\\\")
            if is_windows
            else (
                f"'{Path(get_app_dir('show-params-cli')).resolve()}{sep}"
                "*.{toml,yaml,yml,json,ini,xml}'"
            ),
            repr(str(conf_path)),
            "COMMANDLINE",
        ),
        (
            "show-params-cli.config",
            "--no-config",
            "click_extra.config.NoConfigOption",
            "click.types.UnprocessedParamType",
            "str",
            "✘",
            "✘",
            "✘",
            "SHOW_PARAMS_CLI_CONFIG",
            UNSET,
            repr(str(conf_path)),
            "COMMANDLINE",
        ),
        (
            "show-params-cli.custom_param",
            "--custom-param CUSTOM",
            "cloup._params.Option",
            "tests.test_parameters.Custom",
            "str",
            "✘",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_CUSTOM_PARAM",
            UNSET,
            UNSET,
            "DEFAULT",
        ),
        (
            "show-params-cli.help",
            "-h, --help",
            "click.core.Option",
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
            "--hidden-param TEXT",
            "cloup._params.Option",
            "click.types.StringParamType",
            "str",
            "✓",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_HIDDEN_PARAM",
            UNSET,
            UNSET,
            "DEFAULT",
        ),
        (
            "show-params-cli.int_param1",
            "--int-param1 INTEGER",
            "cloup._params.Option",
            "click.types.IntParamType",
            "int",
            "✘",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_INT_PARAM1",
            3,
            "'9999'",
            "COMMANDLINE",
        ),
        (
            "show-params-cli.int_param2",
            "--int-param2 INTEGER",
            "cloup._params.Option",
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
            "--show-params",
            "click_extra.parameters.ShowParamsOption",
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
            "show-params-cli.table_format",
            "--table-format [asciidoc|csv|csv-excel|csv-excel-tab|csv-unix|double-grid|double-outline|fancy-grid|fancy-outline|github|grid|heavy-grid|heavy-outline|html|jira|latex|latex-booktabs|latex-longtable|latex-raw|mediawiki|mixed-grid|mixed-outline|moinmoin|orgtbl|outline|pipe|plain|presto|pretty|psql|rounded-grid|rounded-outline|rst|simple|simple-grid|simple-outline|textile|tsv|unsafehtml|vertical|youtrack]",
            "click_extra.table.TableFormatOption",
            "click.types.Choice",
            "str",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_TABLE_FORMAT",
            "'rounded-outline'",
            "'rounded-outline'",
            "DEFAULT",
        ),
        (
            "show-params-cli.time",
            "--time / --no-time",
            "click_extra.timer.TimerOption",
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
            "-v, --verbose",
            "click_extra.logging.VerboseOption",
            "click.types.IntRange",
            "int",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_VERBOSE",
            0,
            0,
            "DEFAULT",
        ),
        (
            "show-params-cli.verbosity",
            "--verbosity LEVEL",
            "click_extra.logging.VerbosityOption",
            "click.types.Choice",
            "str",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_VERBOSITY",
            "<LogLevel.WARNING: 30>",
            "'DeBuG'",
            "COMMANDLINE",
        ),
        (
            "show-params-cli.version",
            "--version",
            "click_extra.version.ExtraVersionOption",
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

    assert_table_content(result.stdout, expected_table)


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

    expected_table = [
        (
            "show-params-cli-main.help",
            "-h, --help",
            "click.core.Option",
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
            "--show-params",
            "click_extra.parameters.ShowParamsOption",
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
            "-h, --help",
            "click.core.Option",
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
            "-h, --help",
            "click.core.Option",
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
            "--int-param INTEGER",
            "cloup._params.Option",
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

    assert_table_content(result.stdout, expected_table)


# Shuffle the order of declaration to ensure behavior stability.
@pytest.mark.parametrize(
    ("opt1", "opt2"),
    permutations((show_params_option, table_format_option)),
)
@pytest.mark.parametrize("table_format", TableFormat)
def test_standalone_table_rendering(
    invoke, opt1, opt2, table_format, assert_output_regex
):
    """Check all rendering styles of the table with standalone ``--show-params`` and
    ``--table-format`` option.
    """

    @click.command
    @opt1
    @opt2
    def show_params():
        echo("It works!")

    expected_table = [
        [
            "show-params.help",
            "--help",
            "click.core.Option",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "None",
            "",
        ],
        [
            "show-params.show_params",
            "--show-params",
            "click_extra.parameters.ShowParamsOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "None",
            "COMMANDLINE",
        ],
        [
            "show-params.table_format",
            "--table-format [asciidoc|csv|csv-excel|csv-excel-tab|csv-unix|double-grid|double-outline|fancy-grid|fancy-outline|github|grid|heavy-grid|heavy-outline|html|jira|latex|latex-booktabs|latex-longtable|latex-raw|mediawiki|mixed-grid|mixed-outline|moinmoin|orgtbl|outline|pipe|plain|presto|pretty|psql|rounded-grid|rounded-outline|rst|simple|simple-grid|simple-outline|textile|tsv|unsafehtml|vertical|youtrack]",
            "click_extra.table.TableFormatOption",
            "click.types.Choice",
            "str",
            "✘",
            "✘",
            "",
            "",
            "'rounded-outline'",
            "None",
            "",
        ],
    ]

    # Check the default rendering style.
    for args in (
        # There is no impact with just the presence of @table_format_option decorator.
        ("--show-params",),
        # Both options are eager, so passing --table-format after --show-params makes
        # it too late to have an effect.
        ("--show-params", "--table-format", table_format),
    ):
        result = invoke(show_params, args)
        assert result.exit_code == 0
        assert_table_content(result.stdout, expected_table)

    # --table-format is explicitly set from now on, so its source is COMMANDLINE.
    expected_table[2][11] = "COMMANDLINE"

    # Check the explicit rendering style of the table. Ignore colors, they'll be
    # checked in the next test.
    result = invoke(
        show_params, "--table-format", table_format, "--show-params", color=False
    )
    assert result.exit_code == 0

    rendered_table = (
        render_table(
            expected_table,
            headers=ShowParamsOption.TABLE_HEADERS,
            table_format=table_format,
        )
        + "\n"
    )

    # Compare content line by line to simplify reporting of differences.
    output_lines = result.stdout.strip().splitlines()
    expected_lines = rendered_table.strip().splitlines()
    assert len(output_lines) == len(expected_lines)
    for index in range(len(expected_lines)):
        assert output_lines[index] == expected_lines[index]

    # XXX Click.testing.Result always uses \n line endings, even on Windows.
    # "\r\n" are replaced by "\n" since the beginning of time:
    # https://github.com/pallets/click/commit/7360097ec25e89730f46b840aa050467c5a80e9e#diff-e52e4ddd58b7ef887ab03c04116e676f6280b824ab7469d5d3080e5cba4f2128R120
    # So we can't test the CSV dialects properly.
    if table_format not in (
        TableFormat.CSV,
        TableFormat.CSV_EXCEL,
        TableFormat.CSV_EXCEL_TAB,
        TableFormat.CSV_UNIX,
    ):
        assert result.stdout == rendered_table


# Shuffle the order of declaration to ensure behavior stability.
@pytest.mark.parametrize(
    ("opt1", "opt2", "opt3"),
    permutations((show_params_option, table_format_option, color_option)),
)
@pytest.mark.parametrize("table_format", TableFormat)
def test_standalone_no_color_rendering(
    invoke, opt1, opt2, opt3, table_format, assert_output_regex
):
    """Check that all rendering styles are responding to the
    ``--color``/``--no-color`` option.
    """

    @click.command
    @opt1
    @opt2
    @opt3
    def show_params():
        echo("It works!")

    expected_table = [
        [
            "show-params.color",
            "--color, --ansi / --no-color, --no-ansi",
            "click_extra.colorize.ColorOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            True,
            "None",
            "",
        ],
        [
            "show-params.help",
            "--help",
            "click.core.Option",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "None",
            "",
        ],
        [
            "show-params.show_params",
            "--show-params",
            "click_extra.parameters.ShowParamsOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "None",
            "COMMANDLINE",
        ],
        [
            "show-params.table_format",
            "--table-format [asciidoc|csv|csv-excel|csv-excel-tab|csv-unix|double-grid|double-outline|fancy-grid|fancy-outline|github|grid|heavy-grid|heavy-outline|html|jira|latex|latex-booktabs|latex-longtable|latex-raw|mediawiki|mixed-grid|mixed-outline|moinmoin|orgtbl|outline|pipe|plain|presto|pretty|psql|rounded-grid|rounded-outline|rst|simple|simple-grid|simple-outline|textile|tsv|unsafehtml|vertical|youtrack]",
            "click_extra.table.TableFormatOption",
            "click.types.Choice",
            "str",
            "✘",
            "✘",
            "",
            "",
            "'rounded-outline'",
            "None",
            "",
        ],
    ]

    # Check the default rendering style.
    for args in (
        # There is no impact with just the presence of @color_option decorator.
        ("--show-params",),
        # Both options are eager, so passing --color/--no-color after --show-params
        # makes it too late to have an effect.
        ("--show-params", "--color"),
        ("--show-params", "--no-color"),
    ):
        result = invoke(show_params, args)
        assert result.exit_code == 0
        assert_table_content(result.stdout, expected_table)

    # --color/--no-color is explicitly set from now on, so its source is COMMANDLINE.
    expected_table[0][11] = "COMMANDLINE"

    # Force --color.
    result = invoke(show_params, "--color", "--show-params")
    assert result.exit_code == 0
    # --color is forced, so the table is colorized and doesn't match expected_table, unless we
    # strip all ANSI escape sequences.
    with pytest.raises(AssertionError):
        assert_table_content(result.stdout, expected_table)
    assert_table_content(strip_ansi(result.stdout), expected_table)

    # Force --no-color.
    result = invoke(show_params, "--no-color", "--show-params")
    assert result.exit_code == 0
    assert_table_content(result.stdout, expected_table)

    # --table-format is explicitly set from now on, so its source is COMMANDLINE.
    expected_table[3][11] = "COMMANDLINE"

    # Check the explicit rendering style of the table.
    result = invoke(
        show_params, "--no-color", "--table-format", table_format, "--show-params"
    )
    assert result.exit_code == 0

    rendered_table = (
        render_table(
            expected_table,
            headers=ShowParamsOption.TABLE_HEADERS,
            table_format=table_format,
        )
        + "\n"
    )

    # Compare content line by line to simplify reporting of differences.
    output_lines = result.stdout.strip().splitlines()
    expected_lines = rendered_table.strip().splitlines()
    assert len(output_lines) == len(expected_lines)
    for index in range(len(expected_lines)):
        line = output_lines[index]
        # XXX CSV dialects are not rendered with echo but with print and are not
        # sensitive to Click colorization settings.
        if table_format in (
            TableFormat.CSV,
            TableFormat.CSV_EXCEL,
            TableFormat.CSV_EXCEL_TAB,
            TableFormat.CSV_UNIX,
        ):
            line = strip_ansi(line)
        assert line == expected_lines[index]

    # XXX Click.testing.Result always uses \n line endings, even on Windows.
    # "\r\n" are replaced by "\n" since the beginning of time:
    # https://github.com/pallets/click/commit/7360097ec25e89730f46b840aa050467c5a80e9e#diff-e52e4ddd58b7ef887ab03c04116e676f6280b824ab7469d5d3080e5cba4f2128R120
    # So we can't test the CSV dialects properly.
    if table_format not in (
        TableFormat.CSV,
        TableFormat.CSV_EXCEL,
        TableFormat.CSV_EXCEL_TAB,
        TableFormat.CSV_UNIX,
    ):
        assert result.stdout == rendered_table
