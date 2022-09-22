# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

import re
import sys
from os.path import sep
from pathlib import Path

import click
import pytest
from click import (
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
)
from click import Path as ClickPath
from click import Tuple, echo, get_app_dir
from cloup import argument, option
from tabulate import tabulate

from ..commands import extra_command, extra_group
from ..config import ConfigOption, ShowParamsOption, config_option
from .conftest import default_debug_uncolored_log

DUMMY_TOML_FILE = """
    # Comment

    top_level_param             = "to_ignore"

    [config-cli1]
    verbosity = "DEBUG"
    blahblah = 234
    dummy_flag = true
    my_list = ["pip", "npm", "gem"]

    [garbage]
    # An empty random section that will be skipped

    [config-cli1.default-command]
    int_param = 3
    random_stuff = "will be ignored"
    """

DUMMY_YAML_FILE = """
    # Comment

    top_level_param: to_ignore

    config-cli1:
        verbosity : DEBUG
        blahblah: 234
        dummy_flag: True
        my_list:
          - pip
          - "npm"
          - gem
        default-command:
            int_param: 3
            random_stuff : will be ignored

    garbage:
        # An empty random section that will be skipped

    """

DUMMY_JSON_FILE = """
    {
        "top_level_param": "to_ignore",
        "config-cli1": {
            "blahblah": 234,
            "dummy_flag": true,
            "my_list": [
                "pip",
                "npm",
                "gem"
            ],
            "verbosity": "DEBUG",   // log level

            # Subcommand config
            "default-command": {
                "int_param": 3,
                "random_stuff": "will be ignored"
            }
        },

        // Section to ignore
        "garbage": {}
    }
    """

DUMMY_INI_FILE = """
    ; Comment
    # Another kind of comment

    [to_ignore]
    key=value
    spaces in keys=allowed
    spaces in values=allowed as well
    spaces around the delimiter = obviously
    you can also use : to delimit keys from values

    [config-cli1.default-command]
    int_param = 3
    random_stuff = will be ignored

    [garbage]
    # An empty random section that will be skipped

    [config-cli1]
    verbosity : DEBUG
    blahblah: 234
    dummy_flag = true
    my_list = ["pip", "npm", "gem"]
    """

DUMMY_XML_FILE = """
    <!-- Comment -->

    <config-cli1 has="an attribute">

        <to_ignore>
            <key>value</key>
            <spaces >    </spaces>
            <text_as_value>
                Ratione omnis sit rerum dolor.
                Quas omnis dolores quod sint aspernatur.
                Veniam deleniti est totam pariatur temporibus qui
                        accusantium eaque.
            </text_as_value>

        </to_ignore>

        <verbosity>debug</verbosity>
        <blahblah>234</blahblah>
        <dummy_flag>true</dummy_flag>

        <my_list>pip</my_list>
        <my_list>npm</my_list>
        <my_list>gem</my_list>

        <garbage>
            <!-- An empty random section that will be skipped -->
        </garbage>

        <default-command>
            <int_param>3</int_param>
            <random_stuff>will be ignored</random_stuff>
        </default-command>

    </config-cli1>
    """


all_config_formats = pytest.mark.parametrize(
    "conf_name,conf_content",
    (
        pytest.param(f"configuration.{ext}", content, id=ext)
        for ext, content in (
            ("toml", DUMMY_TOML_FILE),
            ("yaml", DUMMY_YAML_FILE),
            ("json", DUMMY_JSON_FILE),
            ("ini", DUMMY_INI_FILE),
            ("xml", DUMMY_XML_FILE),
        )
    ),
)


@extra_group()
@option("--dummy-flag/--no-flag")
@option("--my-list", multiple=True)
def config_cli1(dummy_flag, my_list):
    echo(f"dummy_flag = {dummy_flag!r}")
    echo(f"my_list = {my_list!r}")


@config_cli1.command()
@option("--int-param", type=int, default=10)
def default_command(int_param):
    echo(f"int_parameter = {int_param!r}")


def test_unset_conf_no_message(invoke):
    result = invoke(config_cli1, "default-command")
    assert result.exit_code == 0
    assert result.output == "dummy_flag = False\nmy_list = ()\nint_parameter = 10\n"
    assert not result.stderr


def test_unset_conf_debug_message(invoke):
    result = invoke(config_cli1, "--verbosity", "DEBUG", "default-command", color=False)
    assert result.exit_code == 0
    assert result.output == "dummy_flag = False\nmy_list = ()\nint_parameter = 10\n"
    assert re.fullmatch(default_debug_uncolored_log, result.stderr)


def test_conf_default_path(invoke):
    result = invoke(config_cli1, "--help", color=False)
    assert result.exit_code == 0

    # OS-specific path.
    default_path = ConfigOption.compress_path(
        Path(get_app_dir("config-cli1")) / "*.{toml,yaml,yml,json,ini,xml}"
    )

    # Make path string compatible with regexp.
    path_regexp = (
        str(default_path)
        .replace("\\", "\\\\")
        .replace("*", r"\*")
        .replace("-", r"-\s*")
    )
    assert re.search(rf"\[default:\s+{path_regexp}\]", result.output)


def test_conf_not_exist(invoke):
    conf_path = Path("dummy.toml")
    result = invoke(
        config_cli1, "--config", str(conf_path), "default-command", color=False
    )
    assert result.exit_code == 2
    assert not result.output
    assert result.stderr == (
        f"Load configuration matching {conf_path}\n"
        f"critical: No configuration file found.\n"
    )


def test_conf_not_file(invoke):
    conf_path = Path().parent
    result = invoke(
        config_cli1, "--config", str(conf_path), "default-command", color=False
    )
    assert result.exit_code == 2
    assert not result.output
    assert result.stderr == (
        f"Load configuration matching {conf_path}\n"
        f"critical: No configuration file found.\n"
    )


def test_conf_auto_types(invoke, create_config):
    """Check the conf type and structure is properly derived from CLI options."""

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
    @option("--path-param", type=ClickPath())
    @option("--choice-param", type=Choice(("a", "b", "c")))
    @option("--int-range-param", type=IntRange())
    @option("--count-param", count=True)  # See issue #170.
    @option("--float-range-param", type=FloatRange())
    @option("--datetime-param", type=DateTime())
    @option("--tuple1", nargs=2, type=Tuple([str, int]))
    @option("--list1", multiple=True)
    @argument("file_arg1", type=File("w"))
    @argument("file_arg2", type=File("w"), nargs=-1)
    @config_option()
    def config_cli2(
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
        int_range_param,
        count_param,
        float_range_param,
        datetime_param,
        tuple1,
        list1,
        file_arg1,
        file_arg2,
    ):
        echo("Works!")

    conf_path = create_config("dummy.toml", DUMMY_TOML_FILE)
    result = invoke(
        config_cli2,
        "--config",
        str(conf_path),
        "random_file1",
        "random_file2",
        color=False,
    )

    assert result.exit_code == 0
    assert result.output == "Works!\n"

    cli_config_option = [
        p for p in config_cli2.params if isinstance(p, ConfigOption)
    ].pop()
    assert cli_config_option.params_template == {
        "config-cli2": {
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
            "choice_param": None,
            "int_range_param": None,
            "count_param": None,
            "float_range_param": None,
            "datetime_param": None,
            "tuple1": None,
            "list1": None,
            "file_arg1": None,
            "file_arg2": None,
        }
    }
    assert cli_config_option.params_types == {
        "config-cli2": {
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
            "choice_param": str,
            "int_range_param": int,
            "count_param": int,
            "float_range_param": float,
            "datetime_param": str,
            "tuple1": list,
            "list1": list,
            "file_arg1": str,
            "file_arg2": list,
        }
    }


def test_strict_conf(invoke, create_config):
    """Same test as the one shown in the readme, but in strict validation mode."""

    @click.group(context_settings={"show_default": True})
    @option("--dummy-flag/--no-flag")
    @option("--my-list", multiple=True)
    @config_option(strict=True)
    def config_cli3(dummy_flag, my_list):
        echo(f"dummy_flag    is {dummy_flag!r}")
        echo(f"my_list       is {my_list!r}")

    @config_cli3.command
    @option("--int-param", type=int, default=10)
    def subcommand(int_param):
        echo(f"int_parameter is {int_param!r}")

    conf_file = """
        # My default configuration file.

        [config-cli3]
        dummy_flag = true   # New boolean default.
        my_list = ["item 1", "item #2", "Very Last Item!"]

        [config-cli3.subcommand]
        int_param = 3
        random_stuff = "will be ignored"
        """

    conf_path = create_config("messy.toml", conf_file)

    result = invoke(config_cli3, "--config", str(conf_path), "subcommand", color=False)

    assert result.exception
    assert type(result.exception) == ValueError
    assert (
        str(result.exception)
        == "Parameter 'random_stuff' is not allowed in configuration file."
    )

    assert result.exit_code == 1
    assert result.stderr == f"Load configuration matching {conf_path}\n"
    assert not result.stdout


@all_config_formats
def test_conf_file_overrides_defaults(
    invoke, create_config, httpserver, conf_name, conf_content
):
    # Create a local file and remote config.
    conf_filepath = create_config(conf_name, conf_content)
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_content)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path in conf_filepath, conf_url:

        result = invoke(
            config_cli1, "--config", str(conf_path), "default-command", color=False
        )
        assert result.exit_code == 0
        assert result.stdout == (
            "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
        )

        # Make path string compatible with regexp on Windows.
        conf_path = str(conf_path).replace("\\", "\\\\")
        # Debug level has been activated by configuration file.
        debug_log = (
            rf"Load configuration matching {conf_path}\n"
            r"debug: Verbosity set to DEBUG.\n"
            r"debug: \S+, version \S+\n"
        )
        # XXX Temporarily expect extra-env info for Python < 3.10 while we wait for
        # https://github.com/mahmoud/boltons/issues/294 to be released upstream.
        if sys.version_info[:2] < (3, 10):
            debug_log += r"debug: {.*}\n"
        assert re.fullmatch(debug_log, result.stderr)


@all_config_formats
def test_auto_env_var_conf(invoke, create_config, httpserver, conf_name, conf_content):
    # Create a local config.
    conf_filepath = create_config(conf_name, conf_content)

    # Create a remote config.
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_content)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path in conf_filepath, conf_url:

        conf_path = create_config(conf_name, conf_content)
        result = invoke(
            config_cli1,
            "default-command",
            color=False,
            env={"CONFIG_TEST_CLI_CONFIG": str(conf_path)},
        )
        assert result.exit_code == 0
        assert result.output == (
            "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
        )
        # Debug level has been activated by configuration file.
        assert result.stderr == (
            f"Load configuration matching {conf_path.resolve()}\n"
            "debug: Verbosity set to DEBUG.\n"
        )


@all_config_formats
def test_conf_file_overrided_by_cli_param(
    invoke, create_config, httpserver, conf_name, conf_content
):
    # Create a local file and remote config.
    conf_filepath = create_config(conf_name, conf_content)
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_content)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path in conf_filepath, conf_url:

        conf_path = create_config(conf_name, conf_content)
        result = invoke(
            config_cli1,
            "--my-list",
            "super",
            "--config",
            str(conf_path),
            "--verbosity",
            "CRITICAL",
            "--no-flag",
            "--my-list",
            "wow",
            "default-command",
            "--int-param",
            "15",
        )
        assert result.exit_code == 0
        assert result.output == (
            "dummy_flag = False\nmy_list = ('super', 'wow')\nint_parameter = 15\n"
        )
        assert result.stderr == f"Load configuration matching {conf_path.resolve()}\n"


def test_show_params_option(invoke, create_config):
    @extra_command()
    @option("--int-param1", type=int, default=10)
    @option("--int-param2", type=int, default=555)
    def show_params_cli(int_param1, int_param2):
        echo(f"int_param1 is {int_param1!r}")
        echo(f"int_param2 is {int_param2!r}")

    conf_file = """
        [show-params-cli]
        int_param1 = 3
        extra_value = "unallowed"
        """
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

    cli_config_option = [
        p for p in show_params_cli.params if isinstance(p, ConfigOption)
    ].pop()
    table = [
        (
            "<ColorOption color>",
            "show-params-cli.color",
            "bool",
            "SHOW_PARAMS_CLI_COLOR",
            True,
            True,
            "DEFAULT",
        ),
        (
            "<ConfigOption config>",
            "show-params-cli.config",
            "str",
            "SHOW_PARAMS_CLI_CONFIG",
            f"{Path(get_app_dir('show-params-cli')).resolve()}{sep}*.{{toml,yaml,yml,json,ini,xml}}",
            str(conf_path),
            "COMMANDLINE",
        ),
        (
            "<HelpOption help>",
            "show-params-cli.help",
            "bool",
            "SHOW_PARAMS_CLI_HELP",
            False,
            True,
            "COMMANDLINE",
        ),
        (
            "<Option int_param1>",
            "show-params-cli.int_param1",
            "int",
            "SHOW_PARAMS_CLI_INT_PARAM1",
            3,
            9999,
            "COMMANDLINE",
        ),
        (
            "<Option int_param2>",
            "show-params-cli.int_param2",
            "int",
            "SHOW_PARAMS_CLI_INT_PARAM2",
            555,
            555,
            "DEFAULT",
        ),
        (
            "<ShowParamsOption show_params>",
            "show-params-cli.show_params",
            "bool",
            "SHOW_PARAMS_CLI_SHOW_PARAMS",
            False,
            True,
            "COMMANDLINE",
        ),
        (
            "<TimerOption time>",
            "show-params-cli.time",
            "bool",
            "SHOW_PARAMS_CLI_TIME",
            False,
            False,
            "DEFAULT",
        ),
        (
            "<VerbosityOption verbosity>",
            "show-params-cli.verbosity",
            "str",
            "SHOW_PARAMS_CLI_VERBOSITY",
            "INFO",
            "DeBuG",
            "COMMANDLINE",
        ),
        (
            "<VersionOption version>",
            "show-params-cli.version",
            "bool",
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
    assert result.output == f"{output}\n"

    assert f"debug: click_extra.raw_args: {raw_args}" in result.stderr
