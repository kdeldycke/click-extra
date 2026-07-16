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

import inspect
import json
import re
from collections.abc import Sequence
from itertools import permutations
from os.path import sep
from pathlib import Path
from textwrap import dedent

import click
import pytest
from boltons.iterutils import flatten, unique
from boltons.strutils import strip_ansi
from extra_platforms import is_windows

from click_extra import (
    BOOL,
    FLOAT,
    INT,
    STRING,
    UNPROCESSED,
    UUID,
    Choice,
    ConfigFormat,
    DateTime,
    File,
    FloatRange,
    IntRange,
    ParamType,
    ShowParamsOption,
    Style,
    TableFormat,
    Tuple,
    argument,
    color_option,
    columns_option,
    command,
    echo,
    get_app_dir,
    group,
    option,
    render_table,
    search_params,
    show_params_option,
    table_format_option,
)
from click_extra.config import NO_CONFIG
from click_extra.parameters import (
    iter_subcommands,
    make_resilient_context,
    missing_extra_message,
    option_value_kind,
)
from click_extra.pytest import command_decorators
from click_extra.table import SERIALIZATION_FORMATS, STYLED_FORMATS
from click_extra.theme import get_current_theme

from .test_highlight import HashType


def _detect_click_help_param_name() -> str:
    """Probe Click's internal parameter name for its built-in help option."""
    probe_cmd = click.Command("probe")
    probe_ctx = probe_cmd.make_context("probe", [])
    help_option = probe_cmd.get_help_option(probe_ctx)
    assert help_option is not None
    assert help_option.name is not None
    return help_option.name


CLICK_HELP_PARAM_NAME = _detect_click_help_param_name()
"""Click's internal ``.name`` for its built-in ``--help`` option.

Detected at runtime instead of hardcoded as ``"help"``: Click's development branch
renamed it to ``"_click_default_help"``, an internal identifier click-extra does not
control and a version comparison alone cannot reliably predict.
"""


class Custom(ParamType):
    """A dummy custom type."""

    name = "Custom"

    def convert(self, value, param, ctx):
        return value


def test_factory_decorators_expose_option_signature():
    """Factory-built option decorators expose their option class's real signature.

    Guards the signature propagation in
    :func:`click_extra.decorators.decorator_factory`, which lets editors,
    ``help()`` and Sphinx see the actual parameters instead of an opaque
    ``(*args, **kwargs)``.
    """
    table_params = inspect.signature(table_format_option).parameters
    assert "param_decls" in table_params
    assert "default" in table_params
    assert set(table_params) != {"args", "kwargs"}

    # The columns registry argument is surfaced too.
    assert "columns" in inspect.signature(columns_option).parameters

    # Command/group are not parameter decorators, so they stay generic.
    assert set(inspect.signature(command).parameters) == {"args", "kwargs"}


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

    assert result.stdout != "Works!\n"
    assert result.exit_code == 0

    show_param_option = search_params(params_introspection.params, ShowParamsOption)
    assert isinstance(show_param_option, ShowParamsOption)
    # ``params_template`` walks the command tree from the active context, so
    # build it inside a (resilient, callback-free) context rather than relying
    # on a leftover cache from the invocation above.
    with params_introspection.make_context(
        "params-introspection",
        ["random_file1", "random_file2"],
        resilient_parsing=True,
    ):
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
                CLICK_HELP_PARAM_NAME: None,
            },
        }


def _sort_params_table(table: Sequence[Sequence]) -> list[Sequence]:
    """Sort rows like render_params_table() does: depth first, then alphabetically
    by path. Lets tests declare and mutate rows in any convenient order while still
    matching the CLI's actual output order, which shifts whenever a row's
    alphabetical position changes, like Click's help option gaining a leading
    underscore on its development branch.
    """
    return sorted(table, key=lambda row: (len(str(row[0]).split(".")), row[0]))


def assert_table_content(
    output: str,
    expected_table: Sequence[Sequence],
    table_format: TableFormat | None = None,
) -> None:
    """Helper to assert the content of a rendered table in the output."""
    expected_table = _sort_params_table(expected_table)

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
        headers=ShowParamsOption.column_labels(),
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

    expected_table: list = [
        (
            f"show-params.{CLICK_HELP_PARAM_NAME}",
            "--help",
            "click.core.Option",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
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
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            "None",
            "COMMANDLINE",
        ),
    ]

    assert_table_content(result.stdout, expected_table)

    if result.stderr:
        assert_output_regex(
            result.stderr,
            r"warning: Cannot extract parameters values: "
            r"<(Group|Command) show-params> does not inherits from Command\.\n",
        )

    assert result.exit_code == 0


def test_integrated_show_params_option(invoke, create_config):
    @command
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

    expected_table: list = [
        (
            "show-params-cli.accessible",
            "--accessible",
            "click_extra.accessibility.AccessibleOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_ACCESSIBLE",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            False,
            "DEFAULT",
        ),
        (
            "show-params-cli.color",
            "--color [auto|always|never]",
            "click_extra.color.ColorOption",
            "click_extra.color.ColorWhenChoice",
            "str",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_COLOR",
            "'auto'",
            "✘",
            "'always'",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "'auto'",
            "DEFAULT",
        ),
        (
            "show-params-cli.config",
            "--config CONFIG_PATH",
            "click_extra.config.option.ConfigOption",
            "click.types.UnprocessedParamType",
            "str",
            "✘",
            "✘",
            "✘",
            "SHOW_PARAMS_CLI_CONFIG",
            # On Windows, backslashes are double-escaped in Path string repr.
            (
                f"'{Path(get_app_dir('show-params-cli')).resolve()}{sep}"
                f"{{{','.join(unique(flatten(f.patterns for f in ConfigFormat if f.enabled)))}}}'"
            ).replace("\\", "\\\\")
            if is_windows
            else (
                f"'{Path(get_app_dir('show-params-cli')).resolve()}{sep}"
                f"{{{','.join(unique(flatten(f.patterns for f in ConfigFormat if f.enabled)))}}}'"
            ),
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            repr(str(conf_path)),
            "COMMANDLINE",
        ),
        (
            "show-params-cli.config",
            "--no-config",
            "click_extra.config.option.NoConfigOption",
            "click.types.UnprocessedParamType",
            "str",
            "✘",
            "✘",
            "✘",
            "SHOW_PARAMS_CLI_CONFIG",
            "None",
            "✓",
            NO_CONFIG,
            "✘",
            "✘",
            1,
            "",
            "✘",
            repr(str(conf_path)),
            "COMMANDLINE",
        ),
        (
            "show-params-cli.custom_param",
            "--custom-param CUSTOM",
            "click_extra.parameters.Option",
            "tests.test_parameters.Custom",
            "str",
            "✘",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_CUSTOM_PARAM",
            "None",
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "None",
            "DEFAULT",
        ),
        (
            "show-params-cli.export_config",
            "--export-config FORMAT",
            "click_extra.config.option.ExportConfigOption",
            "click.types.Choice",
            "str",
            "✘",
            "✘",
            "✘",
            "SHOW_PARAMS_CLI_EXPORT_CONFIG",
            "None",
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "None",
            "DEFAULT",
        ),
        (
            f"show-params-cli.{CLICK_HELP_PARAM_NAME}",
            "-h, --help",
            "click.core.Option",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✘",
            f"SHOW_PARAMS_CLI_{CLICK_HELP_PARAM_NAME.upper()}",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            True,
            "COMMANDLINE",
        ),
        (
            "show-params-cli.hidden_param",
            "--hidden-param TEXT",
            "click_extra.parameters.Option",
            "click.types.StringParamType",
            "str",
            "✓",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_HIDDEN_PARAM",
            "None",
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "None",
            "DEFAULT",
        ),
        (
            "show-params-cli.int_param1",
            "--int-param1 INTEGER",
            "click_extra.parameters.Option",
            "click.types.IntParamType",
            "int",
            "✘",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_INT_PARAM1",
            3,
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "'9999'",
            "COMMANDLINE",
        ),
        (
            "show-params-cli.int_param2",
            "--int-param2 INTEGER",
            "click_extra.parameters.Option",
            "click.types.IntParamType",
            "int",
            "✘",
            "✓",
            "✓",
            "SHOW_PARAMS_CLI_INT_PARAM2",
            555,
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            555,
            "DEFAULT",
        ),
        (
            "show-params-cli.man",
            "--man",
            "click_extra.man_page.ManOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_MAN",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            False,
            "DEFAULT",
        ),
        (
            "show-params-cli.no_color",
            "--no-color",
            "click_extra.color.NoColorOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_NO_COLOR",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            False,
            "DEFAULT",
        ),
        (
            "show-params-cli.progress",
            "--progress / --no-progress",
            "click_extra.spinner.ProgressOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_PROGRESS",
            True,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            True,
            "DEFAULT",
        ),
        (
            "show-params-cli.quiet",
            "-q, --quiet",
            "click_extra.logging.QuietOption",
            "click.types.IntRange",
            "int",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_QUIET",
            0,
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            0,
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
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            True,
            "COMMANDLINE",
        ),
        (
            "show-params-cli.table_format",
            "--table-format [aligned|asciidoc|colon-grid|csv|csv-excel|csv-excel-tab|csv-unix|double-grid|double-outline|fancy-grid|fancy-outline|github|grid|heavy-grid|heavy-outline|hjson|html|jira|json|json5|jsonc|latex|latex-booktabs|latex-longtable|latex-raw|mediawiki|mixed-grid|mixed-outline|moinmoin|orgtbl|outline|pipe|plain|presto|pretty|psql|rounded-grid|rounded-outline|rst|simple|simple-grid|simple-outline|textile|toml|tsv|unsafehtml|vertical|xml|yaml|youtrack]",
            "click_extra.table.TableFormatOption",
            "click_extra.types.EnumChoice",
            "str",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_TABLE_FORMAT",
            "'rounded-outline'",
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "'rounded-outline'",
            "DEFAULT",
        ),
        (
            "show-params-cli.theme",
            "--theme [dark|dracula|light|manpage|monokai|nord|solarized_dark]",
            "click_extra.theme.ThemeOption",
            "click_extra.theme.ThemeChoice",
            "str",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_THEME",
            "'dark'",
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "'dark'",
            "DEFAULT",
        ),
        (
            "show-params-cli.time",
            "--time / --no-time",
            "click_extra.execution.TimerOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_TIME",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            False,
            "DEFAULT",
        ),
        (
            "show-params-cli.tree",
            "--tree",
            "click_extra.tree.TreeOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_TREE",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            False,
            "DEFAULT",
        ),
        (
            "show-params-cli.validate_config",
            "--validate-config FILE",
            "click_extra.config.option.ValidateConfigOption",
            "click.types.Path",
            "str",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_VALIDATE_CONFIG",
            "None",
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "None",
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
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            0,
            "DEFAULT",
        ),
        (
            "show-params-cli.verbosity",
            "--verbosity LEVEL",
            "click_extra.logging.VerbosityOption",
            "click_extra.types.EnumChoice",
            "str",
            "✘",
            "✘",
            "✓",
            "SHOW_PARAMS_CLI_VERBOSITY",
            "'WARNING'",
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "'DeBuG'",
            "COMMANDLINE",
        ),
        (
            "show-params-cli.version",
            "--version",
            "click_extra.version.VersionOption",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "✘",
            "SHOW_PARAMS_CLI_VERSION",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            False,
            "DEFAULT",
        ),
    ]

    assert_table_content(result.stdout, expected_table)

    assert f"debug: click_extra.raw_args: {raw_args!r}\n" in result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "args_order",
    permutations(("--show-params", "--table-format=csv", "--no-color")),
    ids=lambda p: " ".join(p),
)
def test_show_params_table_format_ordering(invoke, args_order):
    """``--show-params`` respects ``--table-format`` regardless of CLI order."""

    @command
    @option("--name", default="world")
    def ordering_cli(name):
        echo(f"Hello, {name}!")

    result = invoke(ordering_cli, *args_order, color=False)

    assert result.exit_code == 0
    # CSV format: first line is the header row, comma-separated.
    lines = result.stdout.strip().splitlines()
    assert lines[0] == ",".join(ShowParamsOption.column_labels())
    # All data rows must have the same number of columns as the header.
    for line in lines[1:]:
        assert line.count(",") >= len(ShowParamsOption.TABLE_HEADERS) - 1


@pytest.mark.parametrize(
    "table_format",
    ("json", "yaml", "toml", "hjson"),
)
def test_show_params_native_types(invoke, table_format):
    """Serialization formats emit native types instead of styled glyphs."""

    @command
    @option("--flag/--no-flag", default=True)
    def typed_cli(flag):
        echo(f"flag is {flag!r}")

    result = invoke(
        typed_cli,
        "--show-params",
        f"--table-format={table_format}",
        color=False,
    )

    assert result.exit_code == 0
    output = result.stdout

    # Glyphs must not appear in structured output.
    assert "✓" not in output
    assert "✘" not in output

    # Boolean values must be native, not stringified repr().
    assert "'True'" not in output
    assert "'False'" not in output

    # Check format-specific native boolean representations.
    if table_format == "json":
        assert '"Hidden": false' in output
        assert '"Exposed": false' in output
    elif table_format in ("yaml", "hjson"):
        assert "Hidden: false" in output
        assert "Exposed: false" in output
    elif table_format == "toml":
        assert "Hidden = false" in output
        assert "Exposed = false" in output


def test_show_params_no_default_renders_none(invoke):
    """A parameter with no default renders as None, not the UNSET sentinel.

    Regression guard for Click 8.4's ``UNSET`` sentinel leaking into the value
    and default columns through the ``--show-params`` re-parse path. See the
    RAW_ARGS dossier in ``click_extra.context``.
    """

    @command
    @option("--fruit")  # No default.
    @argument("baskets", nargs=-1)  # No default.
    def grocery_cli(fruit, baskets):
        echo(f"fruit is {fruit!r}")

    result = invoke(grocery_cli, "--show-params", "--table-format=json", color=False)

    assert result.exit_code == 0
    output = result.stdout

    # The UNSET sentinel must never reach the rendered table. (Sentinel.NO_CONFIG
    # legitimately appears as the --no-config flag value, so guard the exact one.)
    assert "Sentinel.UNSET" not in output

    rows = {row["ID"]: row for row in json.loads(output)}
    for param_id in ("grocery-cli.fruit", "grocery-cli.baskets"):
        assert rows[param_id]["Default"] is None
        assert rows[param_id]["Value"] is None
        assert rows[param_id]["Source"] == "DEFAULT"


def test_column_registry_is_consistent():
    """TABLE_HEADERS exposes parallel ``column_labels()`` / ``column_ids()``."""
    headers = ShowParamsOption.TABLE_HEADERS
    labels = ShowParamsOption.column_labels()
    ids = ShowParamsOption.column_ids()

    # All three views agree in length and order.
    assert len(headers) == len(labels) == len(ids)
    assert tuple(c.label for c in headers) == labels
    assert tuple(c.id for c in headers) == ids

    # Column IDs are unique and snake_case-style identifiers.
    assert len(set(ids)) == len(ids)
    for col_id in ids:
        assert col_id.replace("_", "").isalnum()
        assert col_id.islower()

    # Every column carries a non-empty description for doc auto-gen.
    for col in headers:
        assert col.description


def test_find_column_known_and_unknown():
    spec = ShowParamsOption.find_column("is_flag")
    assert spec.id == "is_flag"
    assert spec.label == "Is flag"

    with pytest.raises(KeyError, match="Unknown column ID 'made_up'"):
        ShowParamsOption.find_column("made_up")


def test_render_doc_table_emits_markdown():
    """``render_doc_table`` returns a 2-column Markdown table covering every column."""
    md = ShowParamsOption.render_doc_table()
    lines = md.splitlines()
    # Header + separator + one row per column.
    assert lines[0] == "| Column | Description |"
    assert lines[1] == "| :--- | :--- |"
    assert len(lines) == 2 + len(ShowParamsOption.TABLE_HEADERS)

    # Every label appears exactly once, in canonical order.
    for col, line in zip(ShowParamsOption.TABLE_HEADERS, lines[2:], strict=True):
        assert line.startswith(f"| `{col.label}` | ")


def test_columns_option_projects_and_orders(invoke):
    """`--columns` keeps only selected columns and preserves the user order."""

    @command
    @columns_option
    @option("--int-param", type=int, default=42)
    def project_cli(int_param):
        echo(f"int_param is {int_param!r}")

    # Selection order id, value, is_flag is preserved (different from canonical).
    result = invoke(
        project_cli,
        "--no-color",
        "--columns",
        "id,value,is_flag",
        "--show-params",
    )
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    # First non-border line is the header row.
    header_line = next(ln for ln in lines if "ID" in ln and "Value" in ln)
    id_pos = header_line.index("ID")
    val_pos = header_line.index("Value")
    flag_pos = header_line.index("Is flag")
    # Headers appear in the order requested.
    assert id_pos < val_pos < flag_pos
    # Unselected headers do not appear.
    assert "Spec." not in header_line
    assert "Hidden" not in header_line


def test_columns_option_rejects_unknown_id(invoke):
    """An unknown column ID raises a UsageError with available IDs listed."""

    @command
    @columns_option
    def reject_cli():
        echo("ok")

    result = invoke(
        reject_cli,
        "--no-color",
        "--columns",
        "id,nope,spec",
        "--show-params",
    )
    assert result.exit_code != 0
    assert "Unknown --columns ID(s): 'nope'" in result.stderr
    assert "Accepted:" in result.stderr


def test_recurse_subcommands(invoke):
    # ``help_command=False``: the auto-injected ``help`` subcommand is unrelated to
    # what this test covers (recursive parameter introspection) and is tested on its
    # own in test_commands.py. Keeping it out avoids coupling this fixture's row
    # count to Click's internal naming of its own ``--help`` option, which collides
    # with the ``help`` subcommand's name on some Click versions but not others.
    @group(params=[ShowParamsOption()], help_command=False)
    def show_params_cli_main():
        echo("main cmd")

    @show_params_cli_main.group(params=[], help_command=False)
    def show_params_sub_cmd():
        echo("subcommand")

    @show_params_sub_cmd.command()
    @option("--int-param", type=int, default=10)
    def show_params_sub_sub_cmd(int_param):
        echo(f"subsubcommand int_param is {int_param!r}")

    result = invoke(show_params_cli_main, "--show-params", color=False)

    expected_table: list[list] = [
        [
            f"show-params-cli-main.{CLICK_HELP_PARAM_NAME}",
            "-h, --help",
            "click.core.Option",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            f"SHOW_PARAMS_CLI_MAIN_{CLICK_HELP_PARAM_NAME.upper()}",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            False,
            "DEFAULT",
        ],
        [
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
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            True,
            "COMMANDLINE",
        ],
        [
            f"show-params-cli-main.show-params-sub.{CLICK_HELP_PARAM_NAME}",
            "-h, --help",
            "click.core.Option",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            f"SHOW_PARAMS_CLI_MAIN_SHOW_PARAMS_SUB_{CLICK_HELP_PARAM_NAME.upper()}",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            False,
            "DEFAULT",
        ],
        [
            f"show-params-cli-main.show-params-sub.show-params-sub-sub.{CLICK_HELP_PARAM_NAME}",
            "-h, --help",
            "click.core.Option",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            f"SHOW_PARAMS_CLI_MAIN_SHOW_PARAMS_SUB_SHOW_PARAMS_SUB_SUB_{CLICK_HELP_PARAM_NAME.upper()}",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            False,
            "DEFAULT",
        ],
        [
            "show-params-cli-main.show-params-sub.show-params-sub-sub.int_param",
            "--int-param INTEGER",
            "click_extra.parameters.Option",
            "click.types.IntParamType",
            "int",
            "✘",
            "✓",
            "",
            "SHOW_PARAMS_SUB_SUB_INT_PARAM, "
            "SHOW_PARAMS_CLI_MAIN_SHOW_PARAMS_SUB_SHOW_PARAMS_SUB_SUB_INT_PARAM",
            10,
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            10,
            "DEFAULT",
        ],
    ]

    assert_table_content(result.stdout, expected_table)

    assert result.exit_code == 0


def test_subcommand_conflicts_with_parent_param(invoke):
    """A subcommand whose name matches its direct parent's param is skipped in the
    parameter tree (the config key would be ambiguous), but does not crash the CLI.

    .. code-block:: toml

        [root.alpha]
        # "foo" is ambiguous: is it the --foo param or the [root.alpha.foo] subcommand?
        foo = ???

    See: https://github.com/kdeldycke/click-extra/pull/1286
    """

    @click.group(params=[ShowParamsOption()])
    def root():
        pass

    @root.group()
    @option("--foo")
    def alpha(foo):
        pass

    @alpha.command("foo")
    def alpha_foo_cmd():
        """Subcommand named 'foo', same as alpha's --foo param."""

    result = invoke(root, "--show-params", color=False)
    # The CLI succeeds; the conflicting subcommand is excluded from the tree.
    assert result.exit_code == 0
    # The --foo option of alpha IS in the tree.
    assert "root.alpha.foo" in result.stdout
    # The foo subcommand's own --help param is NOT in the tree.
    assert "root.alpha.foo.help" not in result.stdout


def test_nested_subcommand_no_false_conflict_with_root_param(invoke):
    """A nested subcommand can share a name with a root-level param without conflict.

    The config paths are distinct (``root.verbose`` vs ``root.alpha.verbose``), so there
    is no ambiguity.

    See: https://github.com/kdeldycke/click-extra/pull/1286
    """

    @click.group(params=[ShowParamsOption()])
    @option("--verbose", is_flag=True)
    def root(verbose):
        pass

    @root.group()
    def alpha():
        pass

    @alpha.command("verbose")
    def alpha_verbose_cmd():
        """Subcommand named 'verbose', same as root's --verbose param."""

    result = invoke(root, "--show-params", color=False)
    assert result.exit_code == 0


# Shuffle the order of declaration to ensure behavior stability.
@pytest.mark.parametrize(
    ("opt1", "opt2"),
    permutations((show_params_option, table_format_option)),
)
@pytest.mark.parametrize("table_format", TableFormat)
def test_standalone_table_rendering(invoke, opt1, opt2, table_format):
    """Check all rendering styles of the table with standalone ``--show-params`` and
    ``--table-format`` option.
    """

    @click.command
    @opt1
    @opt2
    def show_params():
        echo("It works!")

    expected_table: list[list] = [
        [
            f"show-params.{CLICK_HELP_PARAM_NAME}",
            "--help",
            "click.core.Option",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
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
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            "None",
            "COMMANDLINE",
        ],
        [
            "show-params.table_format",
            "--table-format [aligned|asciidoc|colon-grid|csv|csv-excel|csv-excel-tab|csv-unix|double-grid|double-outline|fancy-grid|fancy-outline|github|grid|heavy-grid|heavy-outline|hjson|html|jira|json|json5|jsonc|latex|latex-booktabs|latex-longtable|latex-raw|mediawiki|mixed-grid|mixed-outline|moinmoin|orgtbl|outline|pipe|plain|presto|pretty|psql|rounded-grid|rounded-outline|rst|simple|simple-grid|simple-outline|textile|toml|tsv|unsafehtml|vertical|xml|yaml|youtrack]",
            "click_extra.table.TableFormatOption",
            "click_extra.types.EnumChoice",
            "str",
            "✘",
            "✘",
            "",
            "",
            "'rounded-outline'",
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
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
        assert_table_content(result.stdout, expected_table)
        assert result.exit_code == 0

    # --table-format is explicitly set from now on, so its source is COMMANDLINE.
    expected_table[2][18] = "COMMANDLINE"

    # Serialization formats emit native types instead of styled glyphs.
    if table_format in SERIALIZATION_FORMATS:
        for row in expected_table:
            for i, cell in enumerate(row):
                if cell == "✘":
                    row[i] = False
                elif cell == "✓":
                    row[i] = True
            if row[5] == "":
                row[5] = None
            if row[7] == "":
                row[7] = None
            row[8] = [row[8]] if row[8] else []
            if (
                isinstance(row[9], str)
                and row[9].startswith("'")
                and row[9].endswith("'")
            ):
                row[9] = row[9][1:-1]
            # Flag value: empty cell means the attribute is absent (None); a quoted
            # string flag value (like --color's 'always') renders as a native string.
            if row[11] == "":
                row[11] = None
            elif (
                isinstance(row[11], str)
                and row[11].startswith("'")
                and row[11].endswith("'")
            ):
                row[11] = row[11][1:-1]
            # Prompt: empty cell means no prompt configured (None).
            if row[15] == "":
                row[15] = None
            if row[17] == "None":
                row[17] = None
            if row[18] == "":
                row[18] = None

    # Check the explicit rendering style of the table. Ignore colors, they'll be
    # checked in the next test.
    result = invoke(
        show_params, "--table-format", table_format, "--show-params", color=False
    )

    styler = STYLED_FORMATS.get(table_format)
    if styler is None:
        render_data = expected_table
        headers: tuple[str, ...] = ShowParamsOption.column_labels()
    else:
        # Styled formats translate the theme styling of cells and headers to
        # native markup instead of stripping it: reproduce the styling applied
        # by format_param_row() and render_params_table() on the expected data.
        theme = get_current_theme()
        glyphs = {"✓": theme.success("✓"), "✘": theme.error("✘")}
        column_styles = {
            0: theme.invoked_command,  # ID.
            1: theme.option,  # Spec.
            4: theme.metavar,  # Python type.
            9: theme.default,  # Default.
            11: theme.default,  # Flag value.
        }
        render_data = []
        for row in expected_table:
            styled_row = []
            for i, cell in enumerate(row):
                text = str(cell)
                if text in glyphs:
                    styled_row.append(glyphs[text])
                elif text and i in column_styles:
                    styled_row.append(column_styles[i](text))
                else:
                    styled_row.append(cell)
            render_data.append(styled_row)
        bold = Style(bold=True)
        headers = tuple(bold(label) for label in ShowParamsOption.column_labels())

    rendered = render_table(
        _sort_params_table(render_data),
        headers=headers,
        table_format=table_format,
    )
    if styler is not None:
        rendered = styler(rendered)
    rendered_table = rendered if rendered.endswith("\n") else rendered + "\n"

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

    assert result.exit_code == 0


# Shuffle the order of declaration to ensure behavior stability.
@pytest.mark.parametrize(
    ("opt1", "opt2", "opt3"),
    permutations((show_params_option, table_format_option, color_option)),
)
@pytest.mark.parametrize("table_format", TableFormat)
def test_standalone_no_color_rendering(invoke, opt1, opt2, opt3, table_format):
    """Check that all rendering styles are responding to the ``--color`` option."""

    @click.command
    @opt1
    @opt2
    @opt3
    def show_params():
        echo("It works!")

    expected_table: list[list] = [
        [
            "show-params.color",
            "--color [auto|always|never]",
            "click_extra.color.ColorOption",
            "click_extra.color.ColorWhenChoice",
            "str",
            "✘",
            "✘",
            "",
            "",
            "'auto'",
            "✘",
            "'always'",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "None",
            "",
        ],
        [
            f"show-params.{CLICK_HELP_PARAM_NAME}",
            "--help",
            "click.core.Option",
            "click.types.BoolParamType",
            "bool",
            "✘",
            "✘",
            "",
            "",
            False,
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
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
            "✓",
            True,
            "✓",
            "✘",
            1,
            "",
            "✘",
            "None",
            "COMMANDLINE",
        ],
        [
            "show-params.table_format",
            "--table-format [aligned|asciidoc|colon-grid|csv|csv-excel|csv-excel-tab|csv-unix|double-grid|double-outline|fancy-grid|fancy-outline|github|grid|heavy-grid|heavy-outline|hjson|html|jira|json|json5|jsonc|latex|latex-booktabs|latex-longtable|latex-raw|mediawiki|mixed-grid|mixed-outline|moinmoin|orgtbl|outline|pipe|plain|presto|pretty|psql|rounded-grid|rounded-outline|rst|simple|simple-grid|simple-outline|textile|toml|tsv|unsafehtml|vertical|xml|yaml|youtrack]",
            "click_extra.table.TableFormatOption",
            "click_extra.types.EnumChoice",
            "str",
            "✘",
            "✘",
            "",
            "",
            "'rounded-outline'",
            "✘",
            "",
            "✘",
            "✘",
            1,
            "",
            "✘",
            "None",
            "",
        ],
    ]

    # Check the default rendering style.
    for args in (
        # There is no impact with just the presence of @color_option decorator.
        ("--show-params",),
        # Both options are eager, so passing --color after --show-params makes it too
        # late to have an effect.
        ("--show-params", "--color"),
        ("--show-params", "--color=never"),
    ):
        result = invoke(show_params, args)
        assert_table_content(result.stdout, expected_table)
        assert result.exit_code == 0

    # --color/--no-color is explicitly set from now on, so its source is COMMANDLINE.
    expected_table[0][18] = "COMMANDLINE"

    # Force --color.
    result = invoke(show_params, "--color", "--show-params")
    # --color is forced, so the table is colorized and doesn't match expected_table, unless we
    # strip all ANSI escape sequences.
    with pytest.raises(AssertionError):
        assert_table_content(result.stdout, expected_table)
    assert_table_content(strip_ansi(result.stdout), expected_table)
    assert result.exit_code == 0

    # Force --color=never.
    result = invoke(show_params, "--color=never", "--show-params")
    assert_table_content(result.stdout, expected_table)
    assert result.exit_code == 0

    # --table-format is explicitly set from now on, so its source is COMMANDLINE.
    expected_table[3][18] = "COMMANDLINE"

    # Serialization formats emit native types instead of styled glyphs.
    from click_extra.table import SERIALIZATION_FORMATS

    if table_format in SERIALIZATION_FORMATS:
        for row in expected_table:
            # Replace glyph strings with native booleans.
            for i, cell in enumerate(row):
                if cell == "✘":
                    row[i] = False
                elif cell == "✓":
                    row[i] = True
            # Hidden: empty string means None (Arguments have no hidden attr).
            if row[5] == "":
                row[5] = None
            # Allowed in conf?: empty string means no config option (None).
            if row[7] == "":
                row[7] = None
            # Env. vars. become a list (index 8).
            row[8] = [row[8]] if row[8] else []
            # Default value: strip repr quotes (index 9).
            if (
                isinstance(row[9], str)
                and row[9].startswith("'")
                and row[9].endswith("'")
            ):
                row[9] = row[9][1:-1]
            # Flag value: empty cell means the attribute is absent (None); a quoted
            # string flag value (like --color's 'always') renders as a native string.
            if row[11] == "":
                row[11] = None
            elif (
                isinstance(row[11], str)
                and row[11].startswith("'")
                and row[11].endswith("'")
            ):
                row[11] = row[11][1:-1]
            # Prompt: empty cell means no prompt configured (None).
            if row[15] == "":
                row[15] = None
            # Value: "None" string becomes None (index 17).
            if row[17] == "None":
                row[17] = None
            # Source: empty string means None (index 18).
            if row[18] == "":
                row[18] = None

    # Check the explicit rendering style of the table.
    result = invoke(
        show_params, "--color=never", "--table-format", table_format, "--show-params"
    )

    rendered = render_table(
        _sort_params_table(expected_table),
        headers=ShowParamsOption.column_labels(),
        table_format=table_format,
    )
    # Tabulate-based formats don't end with a newline; echo() adds one.
    # Serialization/CSV/vertical formats already include a trailing newline.
    rendered_table = rendered if rendered.endswith("\n") else rendered + "\n"

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
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("opt", "expected"),
    [
        (click.Option(["--foo"]), "required"),
        (click.Option(["--inc"], multiple=True), "required"),
        (click.Option(["--flag"], is_flag=True), "flag"),
        (click.Option(["--shout/--no-shout"]), "flag"),
        (click.Option(["-v", "--verbose"], count=True), "flag"),
        # A flag with a non-bool flag_value (like NoConfigOption) reports
        # is_bool_flag=False yet still takes no value: it must stay "flag". This is
        # why the classifier keys off is_flag rather than is_bool_flag.
        (
            click.Option(["--no-cfg"], is_flag=True, flag_value="x", default=None),
            "flag",
        ),
        # is_flag=False carrying a flag_value is Click's optional-value option.
        (
            click.Option(["--color"], is_flag=False, flag_value="always", default=None),
            "optional",
        ),
    ],
)
def test_option_value_kind(opt, expected):
    assert option_value_kind(opt) == expected


def test_iter_subcommands_hidden_handling():
    cli = click.Group("cli")
    cli.add_command(click.Command("visible"))
    cli.add_command(click.Command("secret", hidden=True))
    ctx = make_resilient_context(cli, "cli")
    # Hidden subcommands are skipped by default, kept when asked.
    assert [name for name, _ in iter_subcommands(cli, ctx)] == ["visible"]
    assert [name for name, _ in iter_subcommands(cli, ctx, skip_hidden=False)] == [
        "secret",
        "visible",
    ]


def test_iter_subcommands_empty_for_non_group():
    leaf = click.Command("leaf")
    ctx = make_resilient_context(leaf, "leaf")
    assert list(iter_subcommands(leaf, ctx)) == []


def test_missing_extra_message():
    msg = missing_extra_message("mkdocs", subject="This module")
    assert msg == (
        "This module requires an optional dependency. "
        "Install it with: pip install click-extra[mkdocs]"
    )
    # The canonical hyphenated distribution name, not the underscore form.
    assert "click_extra[" not in msg
