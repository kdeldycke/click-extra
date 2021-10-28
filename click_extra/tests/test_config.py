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

from .. import __version__
from ..commands import group
from ..config import DEFAULT_CONF_NAME

DUMMY_CONF_FILE = """
    # Comment

    top_level_param = "to_ignore"

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
    assert re.fullmatch(
        r"debug: Verbosity set to DEBUG.\n"
        r"debug: Load configuration at \S+config.toml\n"
        r"debug: Configuration not found at \S+config.toml\n"
        r"debug: Ignore configuration file.\n"
        r"debug: Loaded configuration: {}\n",
        result.stderr,
    )


def test_conf_not_exist(invoke):
    conf_path = Path("dummy.toml")
    result = invoke(
        default_group, "--config", str(conf_path), "default-command", color=False
    )
    assert result.exit_code == 2
    assert not result.output
    assert result.stderr == (
        f"Load configuration at {conf_path.resolve()}\n"
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
        f"Load configuration at {conf_path.resolve()}\n"
        f"critical: Configuration {conf_path.resolve()} is not a file.\n"
    )


def test_conf_file_overrides_defaults(invoke, create_toml):
    conf_path = create_toml("configuration.extension", DUMMY_CONF_FILE)
    result = invoke(
        default_group, "--config", str(conf_path), "default-command", color=False
    )
    assert result.exit_code == 0
    assert result.output == (
        "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
    )
    # Debug level has been activated by configuration file.
    assert result.stderr == (
        f"Load configuration at {conf_path.resolve()}\n"
        "debug: Verbosity set to DEBUG.\n"
    )


def test_auto_env_var_conf(invoke, create_toml):
    conf_path = create_toml("conf.ext", DUMMY_CONF_FILE)
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
        f"Load configuration at {conf_path.resolve()}\n"
        "debug: Verbosity set to DEBUG.\n"
    )


def test_conf_file_overrided_by_cli_param(invoke, create_toml):
    conf_path = create_toml("configuration.extension", DUMMY_CONF_FILE)
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
    assert re.fullmatch(
        r"Load configuration at \S+configuration.extension\n",
        result.stderr,
    )
