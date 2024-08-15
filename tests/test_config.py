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
from textwrap import dedent

import click
import pytest
from boltons.pathutils import shrinkuser
from pytest_cases import fixture, parametrize

from click_extra import (
    command,
    echo,
    get_app_dir,
    option,
    pass_context,
)
from click_extra.colorize import escape_for_help_screen
from click_extra.decorators import config_option, extra_group
from click_extra.pytest import (
    default_debug_uncolored_log_end,
    default_debug_uncolored_log_start,
    default_debug_uncolored_logging,
    default_debug_uncolored_version_details,
)

DUMMY_TOML_FILE, DUMMY_TOML_DATA = (
    dedent(
        """
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
        """,
    ),
    {
        "top_level_param": "to_ignore",
        "config-cli1": {
            "verbosity": "DEBUG",
            "blahblah": 234,
            "dummy_flag": True,
            "my_list": ["pip", "npm", "gem"],
            "default-command": {
                "int_param": 3,
                "random_stuff": "will be ignored",
            },
        },
        "garbage": {},
    },
)

DUMMY_YAML_FILE, DUMMY_YAML_DATA = (
    dedent(
        """
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

        """,
    ),
    {
        "top_level_param": "to_ignore",
        "config-cli1": {
            "verbosity": "DEBUG",
            "blahblah": 234,
            "dummy_flag": True,
            "my_list": ["pip", "npm", "gem"],
            "default-command": {
                "int_param": 3,
                "random_stuff": "will be ignored",
            },
        },
        "garbage": None,
    },
)

DUMMY_JSON_FILE, DUMMY_JSON_DATA = (
    dedent(
        """
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
        """,
    ),
    {
        "top_level_param": "to_ignore",
        "config-cli1": {
            "blahblah": 234,
            "dummy_flag": True,
            "my_list": ["pip", "npm", "gem"],
            "verbosity": "DEBUG",
            "default-command": {
                "int_param": 3,
                "random_stuff": "will be ignored",
            },
        },
        "garbage": {},
    },
)

DUMMY_INI_FILE, DUMMY_INI_DATA = (
    dedent(
        """
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
        """,
    ),
    {
        "to_ignore": {
            "key": "value",
            "spaces in keys": "allowed",
            "spaces in values": "allowed as well",
            "spaces around the delimiter": "obviously",
            "you can also use": "to delimit keys from values",
        },
        "config-cli1": {
            "default-command": {
                "int_param": "3",
                "random_stuff": "will be ignored",
            },
            "verbosity": "DEBUG",
            "blahblah": "234",
            "dummy_flag": "true",
            "my_list": '["pip", "npm", "gem"]',
        },
        "garbage": {},
    },
)

DUMMY_XML_FILE, DUMMY_XML_DATA = (
    dedent(
        """
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
    """,
    ),
    {
        "config-cli1": {
            "@has": "an attribute",
            "to_ignore": {
                "key": "value",
                "spaces": None,
                "text_as_value": (
                    "Ratione omnis sit rerum dolor.\n"
                    "            "
                    "Quas omnis dolores quod sint aspernatur.\n"
                    "            "
                    "Veniam deleniti est totam pariatur temporibus qui\n"
                    "                    "
                    "accusantium eaque."
                ),
            },
            "verbosity": "debug",
            "blahblah": "234",
            "dummy_flag": "true",
            "my_list": ["pip", "npm", "gem"],
            "garbage": None,
            "default-command": {
                "int_param": "3",
                "random_stuff": "will be ignored",
            },
        },
    },
)

all_config_formats = parametrize(
    ("conf_name, conf_text, conf_data"),
    (
        pytest.param(f"configuration.{ext}", content, data, id=ext)
        for ext, content, data in (
            ("toml", DUMMY_TOML_FILE, DUMMY_TOML_DATA),
            ("yaml", DUMMY_YAML_FILE, DUMMY_YAML_DATA),
            ("json", DUMMY_JSON_FILE, DUMMY_JSON_DATA),
            ("ini", DUMMY_INI_FILE, DUMMY_INI_DATA),
            ("xml", DUMMY_XML_FILE, DUMMY_XML_DATA),
        )
    ),
)


@fixture
def simple_config_cli():
    @extra_group(context_settings={"show_envvar": True})
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


def test_unset_conf_no_message(invoke, simple_config_cli):
    result = invoke(simple_config_cli, "default-command")
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == "dummy_flag = False\nmy_list = ()\nint_parameter = 10\n"


def test_unset_conf_debug_message(invoke, simple_config_cli):
    result = invoke(
        simple_config_cli,
        "--verbosity",
        "DEBUG",
        "default-command",
        color=False,
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
        Path(get_app_dir("config-cli1")) / "*.{toml,yaml,yml,json,ini,xml}",
    )

    # Make path string compatible with regexp.
    assert re.search(
        r"\s+\[env\s+var:\s+CONFIG_CLI1_CONFIG;\s+"
        rf"default:\s+{escape_for_help_screen(str(default_path))}\]\s+",
        result.stdout,
    )


def test_conf_not_exist(invoke, simple_config_cli):
    conf_path = Path("dummy.toml")
    result = invoke(
        simple_config_cli,
        "--config",
        str(conf_path),
        "default-command",
        color=False,
    )
    assert result.exit_code == 2
    assert not result.stdout
    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert "critical: No configuration file found.\n" in result.stderr


def test_conf_not_file(invoke, simple_config_cli):
    conf_path = Path().parent
    result = invoke(
        simple_config_cli,
        "--config",
        str(conf_path),
        "default-command",
        color=False,
    )
    assert result.exit_code == 2
    assert not result.stdout

    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert "critical: No configuration file found.\n" in result.stderr


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

    conf_file = dedent(
        """
        # My default configuration file.

        [config-cli3]
        dummy_flag = true   # New boolean default.
        my_list = ["item 1", "item #2", "Very Last Item!"]

        [config-cli3.subcommand]
        int_param = 3
        random_stuff = "will be ignored"
        """,
    )

    conf_path = create_config("messy.toml", conf_file)

    result = invoke(config_cli3, "--config", str(conf_path), "subcommand", color=False)

    assert result.exception
    assert type(result.exception) is ValueError
    assert (
        str(result.exception)
        == "Parameter 'random_stuff' found in second dict but not in first."
    )

    assert result.exit_code == 1
    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert not result.stdout


@all_config_formats
def test_conf_file_overrides_defaults(
    invoke,
    simple_config_cli,
    create_config,
    httpserver,
    conf_name,
    conf_text,
    conf_data,
):
    # Create a local file and remote config.
    conf_filepath = create_config(conf_name, conf_text)
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_text)
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
            default_debug_uncolored_logging
            + default_debug_uncolored_version_details
            + default_debug_uncolored_log_end
        )
        assert re.fullmatch(debug_log, result.stderr)


@all_config_formats
def test_auto_env_var_conf(
    invoke,
    simple_config_cli,
    create_config,
    httpserver,
    conf_name,
    conf_text,
    conf_data,
):
    # Check the --config option properly documents its environment variable.
    result = invoke(simple_config_cli, "--help")
    assert result.exit_code == 0
    assert not result.stderr
    assert "CONFIG_CLI1_CONFIG" in result.stdout

    # Create a local config.
    conf_filepath = create_config(conf_name, conf_text)

    # Create a remote config.
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_text)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path in conf_filepath, conf_url:
        conf_path = create_config(conf_name, conf_text)
        result = invoke(
            simple_config_cli,
            "default-command",
            color=False,
            env={"CONFIG_CLI1_CONFIG": str(conf_path)},
        )
        assert result.exit_code == 0
        assert result.stdout == (
            "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
        )
        # Debug level has been activated by configuration file.
        assert result.stderr.startswith(
            f"Load configuration matching {conf_path}\n"
            "debug: Set <Logger click_extra (DEBUG)> to DEBUG.\n"
            "debug: Set <RootLogger root (DEBUG)> to DEBUG.\n",
        )


@all_config_formats
def test_conf_file_overridden_by_cli_param(
    invoke,
    simple_config_cli,
    create_config,
    httpserver,
    conf_name,
    conf_text,
    conf_data,
):
    # Create a local file and remote config.
    conf_filepath = create_config(conf_name, conf_text)
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_text)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path in conf_filepath, conf_url:
        conf_path = create_config(conf_name, conf_text)
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
        assert result.stderr == f"Load configuration matching {conf_path}\n"


@all_config_formats
def test_conf_metadata(
    invoke,
    create_config,
    httpserver,
    conf_name,
    conf_text,
    conf_data,
):
    @command
    @config_option
    @pass_context
    def config_metadata(ctx):
        echo(f"conf_source={ctx.meta['click_extra.conf_source']}")
        echo(f"conf_full={ctx.meta['click_extra.conf_full']}")
        echo(f"default_map={ctx.default_map}")

    # Create a local file and remote config.
    conf_filepath = create_config(conf_name, conf_text)
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_text)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path in conf_filepath, conf_url:
        conf_path = create_config(conf_name, conf_text)
        result = invoke(config_metadata, "--config", str(conf_path))
        assert result.exit_code == 0
        assert result.stdout == (
            f"conf_source={conf_path}\n"
            f"conf_full={conf_data}\n"
            # No configuration values match the CLI's parameter structure, so default
            # map is left untouched.
            "default_map={}\n"
        )
        assert result.stderr == f"Load configuration matching {conf_path}\n"
