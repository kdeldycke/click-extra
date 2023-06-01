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
from pathlib import Path

import click
import pytest
from boltons.pathutils import shrinkuser
from pytest_cases import fixture, parametrize

from .. import (
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
    Tuple,
    argument,
    echo,
    get_app_dir,
    option,
)
from ..colorize import escape_for_help_sceen
from ..config import ConfigOption
from ..decorators import config_option, extra_group
from ..parameters import search_params
from .conftest import (
    default_debug_uncolored_log_end,
    default_debug_uncolored_log_start,
)

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
    "conf_name, conf_content",
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


@fixture
def simple_config_cli():
    @extra_group
    @option("--dummy-flag/--no-flag")
    @option("--my-list", multiple=True)
    def config_cli1(dummy_flag, my_list):
        echo(f"dummy_flag = {dummy_flag!r}")
        echo(f"my_list = {my_list!r}")

    @config_cli1.command()
    @option("--int-param", type=int, default=10)
    def default_command(int_param):
        echo(f"int_parameter = {int_param!r}")

    return config_cli1


@pytest.mark.xfail(
    strict=False,
    reason=(
        "stderr is not supposed to be filled with debug logs, but it seems there is a "
        "leak somewhere in our logging system"
    ),
)
def test_unset_conf_no_message(invoke, simple_config_cli):
    result = invoke(simple_config_cli, "default-command")
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == "dummy_flag = False\nmy_list = ()\nint_parameter = 10\n"


def test_unset_conf_debug_message(invoke, simple_config_cli):
    result = invoke(
        simple_config_cli, "--verbosity", "DEBUG", "default-command", color=False
    )
    assert result.exit_code == 0
    assert result.stdout == "dummy_flag = False\nmy_list = ()\nint_parameter = 10\n"
    assert re.fullmatch(
        default_debug_uncolored_log_start + default_debug_uncolored_log_end,
        result.stderr,
    )


def test_conf_default_path(invoke, simple_config_cli):
    result = invoke(simple_config_cli, "--help", color=False)
    assert result.exit_code == 0
    assert not result.stderr

    # OS-specific path.
    default_path = shrinkuser(
        Path(get_app_dir("config-cli1")) / "*.{toml,yaml,yml,json,ini,xml}"
    )

    # Make path string compatible with regexp.
    assert re.search(
        rf"\[default:\s+{escape_for_help_sceen(str(default_path))}\]",
        result.stdout,
    )


def test_conf_not_exist(invoke, simple_config_cli):
    conf_path = Path("dummy.toml")
    result = invoke(
        simple_config_cli, "--config", str(conf_path), "default-command", color=False
    )
    assert result.exit_code == 2
    assert not result.stdout
    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert "critical: No configuration file found.\n" in result.stderr


def test_conf_not_file(invoke, simple_config_cli):
    conf_path = Path().parent
    result = invoke(
        simple_config_cli, "--config", str(conf_path), "default-command", color=False
    )
    assert result.exit_code == 2
    assert not result.stdout

    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert "critical: No configuration file found.\n" in result.stderr


@parametrize("option_decorator", (config_option, config_option()))
def test_conf_auto_types(invoke, create_config, option_decorator):
    """Check the conf type and structure is properly derived from CLI options.

    Also covers the tests of the standalone ``@config_option`` decorator in all its
    flavors.
    """

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
    @option("--int-range-param", type=IntRange())
    @option("--count-param", count=True)  # See issue #170.
    @option("--float-range-param", type=FloatRange())
    @option("--datetime-param", type=DateTime())
    @option("--tuple1", nargs=2, type=Tuple([str, int]))
    @option("--list1", multiple=True)
    @argument("file_arg1", type=File("w"))
    @argument("file_arg2", type=File("w"), nargs=-1)
    @option_decorator
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
    assert result.stdout == "Works!\n"

    cli_config_option = search_params(config_cli2.params, ConfigOption)
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

    @click.group
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
    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert not result.stdout


@all_config_formats
def test_conf_file_overrides_defaults(
    invoke, simple_config_cli, create_config, httpserver, conf_name, conf_content
):
    # Create a local file and remote config.
    conf_filepath = create_config(conf_name, conf_content)
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_content)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path, is_url in (conf_filepath, False), (conf_url, True):
        result = invoke(
            simple_config_cli,
            "--config",
            str(conf_path),
            "default-command",
            color=False,
        )
        assert result.exit_code == 0
        assert result.stdout == (
            "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
        )

        # Debug level has been activated by configuration file.
        debug_log = rf"Load configuration matching {re.escape(str(conf_path))}\n"
        if is_url:
            debug_log += (
                r"info: 127\.0\.0\.1 - - \[\S+ \S+\] "
                rf'"GET /{re.escape(conf_name)} HTTP/1\.1" 200 -\n'
            )
        debug_log += (
            r"debug: Set <Logger click_extra \(DEBUG\)> to DEBUG.\n"
            r"debug: Set <RootLogger root \(DEBUG\)> to DEBUG.\n"
            r"debug: \S+, version \S+\n"
            r"debug: {.*}\n"
            rf"{default_debug_uncolored_log_end}"
        )
        assert re.fullmatch(debug_log, result.stderr)


@all_config_formats
def test_auto_env_var_conf(
    invoke, simple_config_cli, create_config, httpserver, conf_name, conf_content
):
    # Create a local config.
    conf_filepath = create_config(conf_name, conf_content)

    # Create a remote config.
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_content)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path in conf_filepath, conf_url:
        conf_path = create_config(conf_name, conf_content)
        result = invoke(
            simple_config_cli,
            "default-command",
            color=False,
            env={"CONFIG_TEST_CLI_CONFIG": str(conf_path)},
        )
        assert result.exit_code == 0
        assert result.stdout == (
            "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
        )
        # Debug level has been activated by configuration file.
        assert result.stderr == (
            f"Load configuration matching {conf_path.resolve()}\n"
            "debug: Verbosity set to DEBUG.\n"
        )


@all_config_formats
def test_conf_file_overrided_by_cli_param(
    invoke, simple_config_cli, create_config, httpserver, conf_name, conf_content
):
    # Create a local file and remote config.
    conf_filepath = create_config(conf_name, conf_content)
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_content)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path in conf_filepath, conf_url:
        conf_path = create_config(conf_name, conf_content)
        result = invoke(
            simple_config_cli,
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
        assert result.stdout == (
            "dummy_flag = False\nmy_list = ('super', 'wow')\nint_parameter = 15\n"
        )
        assert result.stderr == f"Load configuration matching {conf_path.resolve()}\n"
