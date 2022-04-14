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
from pathlib import Path

import click
import pytest

from .. import __version__, argument
from .. import config as config_module
from .. import echo, group, option
from ..config import conf_structure, config_option
from ..platform import is_windows
from .conftest import default_debug_uncolored_log

DUMMY_TOML_FILE = """
    # Comment

    top_level_param             = "to_ignore"

    [default-group]
    verbosity = "DEBUG"
    blahblah = 234
    dummy_flag = true
    my_list = ["pip", "npm", "gem"]

    [garbage]
    # An empty random section that will be skipped

    [default-group.default-command]
    int_param = 3
    random_stuff = "will be ignored"
    """

DUMMY_YAML_FILE = """
    # Comment

    top_level_param: to_ignore

    default-group:
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
        "default-group": {
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
    # Another king of comment

    [to_ignore]
    key=value
    spaces in keys=allowed
    spaces in values=allowed as well
    spaces around the delimiter = obviously
    you can also use : to delimit keys from values

    [default-group.default-command]
    int_param = 3
    random_stuff = will be ignored

    [garbage]
    # An empty random section that will be skipped

    [default-group]
    verbosity : DEBUG
    blahblah: 234
    dummy_flag = true
    my_list = ["pip", "npm", "gem"]
    """

DUMMY_XML_FILE = """
    <!-- Comment -->

    <default-group has="an attribute">

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

    </default-group>
    """


all_config_formats = pytest.mark.parametrize(
    "conf_name,conf_content",
    (
        pytest.param(f"configuration.{ext}", content, id=ext)
        for ext, content in [
            ("toml", DUMMY_TOML_FILE),
            ("yaml", DUMMY_YAML_FILE),
            ("json", DUMMY_JSON_FILE),
            ("ini", DUMMY_INI_FILE),
            ("xml", DUMMY_XML_FILE),
        ]
    ),
)


@group()
@option("--dummy-flag/--no-flag")
@option("--my-list", multiple=True)
def default_group(dummy_flag, my_list):
    echo(f"dummy_flag = {dummy_flag!r}")
    echo(f"my_list = {my_list!r}")


@default_group.command()
@option("--int-param", type=int, default=10)
def default_command(int_param):
    echo(f"int_parameter = {int_param!r}")


def test_unset_conf_no_message(invoke):
    result = invoke(default_group, "default-command")
    assert result.exit_code == 0
    assert result.output == "dummy_flag = False\nmy_list = ()\nint_parameter = 10\n"
    assert not result.stderr


def test_unset_conf_debug_message(invoke):
    result = invoke(
        default_group, "--verbosity", "DEBUG", "default-command", color=False
    )
    assert result.exit_code == 0
    assert result.output == "dummy_flag = False\nmy_list = ()\nint_parameter = 10\n"
    assert re.fullmatch(default_debug_uncolored_log, result.stderr)


def test_conf_default_path(invoke):
    result = invoke(default_group, "--help", color=False)
    assert result.exit_code == 0

    # OS-specific part of the path.
    folder = Path(".default-group")
    home = "~"
    if is_windows():
        folder = Path("AppData") / "Roaming" / "default-group"
        home = Path.home()

    default_path = home / folder / "config.{toml,yaml,yml,json,ini,xml}"

    # Make path string compatible with regexp.
    default_path = str(default_path).replace("\\", "\\\\").replace("-", r"-\s*")
    assert re.search(rf"\[default:\s+{default_path}\]", result.output)


def test_conf_not_exist(invoke):
    conf_path = Path("dummy.toml")
    result = invoke(
        default_group, "--config", str(conf_path), "default-command", color=False
    )
    assert result.exit_code == 2
    assert not result.output
    assert result.stderr == (
        f"Load configuration from {conf_path}\n"
        f"critical: Configuration not found at {conf_path.resolve()}\n"
    )


def test_conf_not_file(invoke):
    conf_path = Path().parent
    result = invoke(
        default_group, "--config", str(conf_path), "default-command", color=False
    )
    assert result.exit_code == 2
    assert not result.output
    assert result.stderr == (
        f"Load configuration from {conf_path}\n"
        f"critical: Configuration {conf_path.resolve()} is not a file.\n"
    )


def test_conf_format_unknown(invoke, create_config):
    conf_path = create_config("file.unknown_extension", "")
    result = invoke(
        default_group, "--config", str(conf_path), "default-command", color=False
    )
    assert result.exit_code == 2
    assert not result.output
    assert result.stderr == (
        f"Load configuration from {conf_path.resolve()}\n"
        "critical: Configuration format not recognized.\n"
    )


def test_conf_auto_types(invoke, monkeypatch, create_config):
    """Check the conf type and structure is properly derived from CLI options."""

    def patched_conf_structure(ctx):
        conf_template, conf_types = conf_structure(ctx)
        assert conf_template == {
            "my-cli": {
                "flag1": None,
                "flag2": None,
                "int_param1": None,
                "int_param2": None,
                "float_param1": None,
                "float_param2": None,
                "bool_param1": None,
                "bool_param2": None,
                "str_param1": None,
                "str_param2": None,
                "choice_param": None,
                "list1": None,
                "file_arg1": None,
                "file_arg2": None,
            }
        }
        assert conf_types == {
            "my-cli": {
                "flag1": bool,
                "flag2": bool,
                "int_param1": int,
                "int_param2": int,
                "float_param1": float,
                "float_param2": float,
                "bool_param1": bool,
                "bool_param2": bool,
                "str_param1": str,
                "str_param2": str,
                "choice_param": str,
                "list1": list,
                "file_arg1": str,
                "file_arg2": list,
            }
        }
        return conf_template, conf_types

    monkeypatch.setattr(config_module, "conf_structure", patched_conf_structure)

    @click.command()
    @option("--flag1/--no-flag1")
    @option("--flag2", is_flag=True)
    @option("--int-param1", type=int)
    @option("--int-param2", type=click.INT)
    @option("--float-param1", type=float)
    @option("--float-param2", type=click.FLOAT)
    @option("--bool-param1", type=bool)
    @option("--bool-param2", type=click.BOOL)
    @option("--str-param1", type=str)
    @option("--str-param2", type=click.STRING)
    @option("--choice-param", type=click.Choice(("a", "b", "c")))
    @option("--list1", multiple=True)
    @argument("file_arg1", type=click.File("w"))
    @argument("file_arg2", type=click.File("w"), nargs=-1)
    @config_option()
    def my_cli(
        flag1,
        flag2,
        int_param1,
        int_param2,
        float_param1,
        float_param2,
        bool_param1,
        bool_param2,
        str_param1,
        str_param2,
        choice_param,
        list1,
        file_arg1,
        file_arg2,
    ):
        echo("Works!")

    conf_path = create_config("dummy.toml", DUMMY_TOML_FILE)
    result = invoke(
        my_cli, "--config", str(conf_path), "random_file1", "random_file2", color=False
    )

    assert result.exit_code == 0
    assert result.output == "Works!\n"


def test_strict_conf(invoke, create_config):
    """Same test as the one shown in the readme, but in strict validation mode."""

    @click.group(context_settings={"show_default": True})
    @option("--dummy-flag/--no-flag")
    @option("--my-list", multiple=True)
    @config_option(strict=True)
    def my_cli(dummy_flag, my_list):
        echo(f"dummy_flag    is {dummy_flag!r}")
        echo(f"my_list       is {my_list!r}")

    @my_cli.command
    @option("--int-param", type=int, default=10)
    def subcommand(int_param):
        echo(f"int_parameter is {int_param!r}")

    conf_file = """
        # My default configuration file.

        [my-cli]
        dummy_flag = true   # New boolean default.
        my_list = ["item 1", "item #2", "Very Last Item!"]

        [my-cli.subcommand]
        int_param = 3
        random_stuff = "will be ignored"
        """

    conf_path = create_config("messy.toml", conf_file)

    result = invoke(my_cli, "--config", str(conf_path), "subcommand", color=False)

    assert result.exception
    assert type(result.exception) == ValueError
    assert (
        str(result.exception)
        == "Parameter 'random_stuff' is not allowed in configuration file."
    )

    assert result.exit_code == 1
    assert result.stderr == f"Load configuration from {conf_path}\n"
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
            default_group, "--config", str(conf_path), "default-command", color=False
        )
        assert result.exit_code == 0
        assert result.output == (
            "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
        )

        # Make path string compatible with regexp on Windows.
        conf_path = str(conf_path).replace("\\", "\\\\")
        # Debug level has been activated by configuration file.
        debug_log = (
            rf"Load configuration from {conf_path}\n"
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
    # Create a local file and remote config.
    conf_filepath = create_config(conf_name, conf_content)
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_content)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path in conf_filepath, conf_url:

        conf_path = create_config(conf_name, conf_content)
        result = invoke(
            default_group,
            "default-command",
            color=False,
            env={"DEFAULT_GROUP_CONFIG": str(conf_path)},
        )
        assert result.exit_code == 0
        assert result.output == (
            "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
        )
        # Debug level has been activated by configuration file.
        assert result.stderr == (
            f"Load configuration from {conf_path.resolve()}\n"
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
            default_group,
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
        assert result.stderr == f"Load configuration from {conf_path.resolve()}\n"
