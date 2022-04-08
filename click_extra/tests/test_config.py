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
from pathlib import Path

import click
import pytest

from .. import __version__
from ..commands import group
from ..platform import is_windows

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


all_config_formats = pytest.mark.parametrize(
    "conf_name,conf_content",
    (
        pytest.param(f"configuration.{ext}", content, id=ext)
        for ext, content in [
            ("toml", DUMMY_TOML_FILE),
            ("yaml", DUMMY_YAML_FILE),
            ("json", DUMMY_JSON_FILE),
            ("ini", DUMMY_INI_FILE),
        ]
    ),
)


@group()
@click.option("--dummy-flag/--no-flag")
@click.option("--my-list", multiple=True)
def default_group(dummy_flag, my_list):
    click.echo(f"dummy_flag = {dummy_flag!r}")
    click.echo(f"my_list = {my_list!r}")


@default_group.command()
@click.option("--int-param", type=int, default=10)
def default_command(int_param):
    click.echo(f"int_parameter = {int_param!r}")


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
    assert result.stderr == (
        "debug: Verbosity set to DEBUG.\n"
        "debug: Search for configuration in default location...\n"
        "debug: No default configuration found.\n"
        "debug: No configuration provided.\n"
    )


def test_conf_default_path(invoke):
    result = invoke(default_group, "--help", color=False)
    assert result.exit_code == 0

    # OS-specific part of the path.
    folder = Path(".default-group")
    home = "~"
    if is_windows():
        folder = Path("AppData") / "Roaming" / "default-group"
        home = Path.home()

    default_path = home / folder / "config.{toml,yaml,yml,json,ini}"

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
        # Debug level has been activated by configuration file.
        assert result.stderr == (
            f"Load configuration from {conf_path}\n" "debug: Verbosity set to DEBUG.\n"
        )


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
