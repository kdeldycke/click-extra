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

import os
import re
from pathlib import Path
from textwrap import dedent

import click
import pytest
from boltons.pathutils import shrinkuser
from extra_platforms import is_macos, is_unix_not_macos, is_windows  # type: ignore[attr-defined]

from click_extra import (
    ConfigFormat,
    ConfigOption,
    config_option,
    echo,
    get_app_dir,
    group,
    no_config_option,
    option,
    pass_context,
    search_params,
)
from click_extra.colorize import _escape_for_help_screen
from click_extra.pytest import (
    default_debug_uncolored_log_end,
    default_debug_uncolored_log_start,
    default_debug_uncolored_logging,
    default_debug_uncolored_version_details,
)

TOML_FILE, TOML_DATA = (
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

        [config-cli1.default]
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
            "default": {
                "int_param": 3,
                "random_stuff": "will be ignored",
            },
        },
        "garbage": {},
    },
)

YAML_FILE, YAML_DATA = (
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
            default:
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
            "default": {
                "int_param": 3,
                "random_stuff": "will be ignored",
            },
        },
        "garbage": None,
    },
)

JSON_FILE, JSON_DATA = (
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
                "verbosity": "DEBUG",

                "default": {
                    "int_param": 3,
                    "random_stuff": "will be ignored"
                }
            },

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
            "default": {
                "int_param": 3,
                "random_stuff": "will be ignored",
            },
        },
        "garbage": {},
    },
)

INI_FILE, INI_DATA = (
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

        [config-cli1.default]
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
            "default": {
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

XML_FILE, XML_DATA = (
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

            <default>
                <int_param>3</int_param>
                <random_stuff>will be ignored</random_stuff>
            </default>

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
            "default": {
                "int_param": "3",
                "random_stuff": "will be ignored",
            },
        },
    },
)

all_config_formats = pytest.mark.parametrize(
    ("conf_name, conf_text, conf_data"),
    (
        pytest.param(f"configuration.{ext}", content, data, id=ext)
        for ext, content, data in (
            ("toml", TOML_FILE, TOML_DATA),
            ("yaml", YAML_FILE, YAML_DATA),
            ("json", JSON_FILE, JSON_DATA),
            ("ini", INI_FILE, INI_DATA),
            ("xml", XML_FILE, XML_DATA),
        )
    ),
)


@pytest.fixture
def simple_config_cli():
    @group(context_settings={"show_envvar": True})
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


def test_unset_conf(invoke, simple_config_cli):
    result = invoke(simple_config_cli, "default")
    assert result.stdout == "dummy_flag = False\nmy_list = ()\nint_parameter = 10\n"
    assert not result.stderr
    assert result.exit_code == 0


def test_unset_conf_debug_message(invoke, simple_config_cli, assert_output_regex):
    result = invoke(
        simple_config_cli,
        "--verbosity",
        "DEBUG",
        "default",
        color=False,
    )
    assert result.stdout == "dummy_flag = False\nmy_list = ()\nint_parameter = 10\n"
    assert_output_regex(
        result.stderr,
        default_debug_uncolored_log_start + default_debug_uncolored_log_end,
    )
    assert result.exit_code == 0


def test_conf_default_path(invoke, simple_config_cli):
    result = invoke(simple_config_cli, "--help", color=False)

    # Search for the OS-specific path without glob pattern.
    default_path = _escape_for_help_screen(str(shrinkuser(get_app_dir("config-cli1"))))

    assert re.search(
        rf"\s+\[env\s+var:\s+CONFIG_CLI1_CONFIG;\s+default:\s+{default_path}",
        result.stdout,
    )

    # Reconstruct and search for the glob pattern, as we cannot rely on regexp because
    # we cannot predict how Cloup will wrap the help screen lines.
    help_screen = "".join(
        line.strip()
        for line in result.stdout.split("--config CONFIG_PATH")[1].splitlines()
    )
    assert (
        "*.toml|*.yaml|*.yml|*.json|*.json5|*.jsonc|*.hjson|*.ini|*.xml]" in help_screen
    )

    assert not result.stderr
    assert result.exit_code == 0


def test_conf_default_pathlib_type(invoke, create_config):
    """Refs https://github.com/kdeldycke/click-extra/issues/1356"""

    conf_path = create_config("dummy.toml", TOML_FILE)
    assert isinstance(conf_path, Path)
    assert conf_path.is_file()

    @click.command
    @option("--dummy-flag/--no-flag")
    @config_option(default=conf_path)
    def config_cli1(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    result = invoke(config_cli1, "--help", color=False)

    # Reconstruct and search for the glob pattern, as we cannot rely on regexp because
    # we cannot predict how Cloup will wrap the help screen lines.
    help_screen = "".join(
        line.strip()
        for line in result.stdout.split("--config CONFIG_PATH")[1].splitlines()
    )
    assert str(shrinkuser(conf_path)) in help_screen

    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(config_cli1)
    assert result.stdout == "dummy_flag = True\n"
    assert not result.stderr
    assert result.exit_code == 0


def test_conf_not_exist(invoke, simple_config_cli):
    conf_path = Path("dummy.toml")
    result = invoke(
        simple_config_cli,
        "--config",
        str(conf_path),
        "default",
        color=False,
    )
    assert not result.stdout
    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert "critical: No configuration file found.\n" in result.stderr
    assert result.exit_code == 2


def test_conf_not_file(invoke, simple_config_cli):
    conf_path = Path().parent
    result = invoke(
        simple_config_cli,
        "--config",
        str(conf_path),
        "default",
        color=False,
    )
    assert not result.stdout
    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert "critical: No configuration file found.\n" in result.stderr
    assert result.exit_code == 2


def test_no_config_option(invoke, simple_config_cli, create_config):
    conf_path = create_config("dummy.toml", TOML_FILE)

    for args in (
        ("--no-config", "default"),
        ("--config", str(conf_path), "--no-config", "default"),
    ):
        result = invoke(simple_config_cli, args)
        assert result.stdout == "dummy_flag = False\nmy_list = ()\nint_parameter = 10\n"
        assert result.stderr == "Skip configuration file loading altogether.\n"
        assert result.exit_code == 0


def test_standalone_no_config_option(invoke):
    """@no_config_option cannot work without @config_option."""

    @click.command
    @no_config_option
    def missing_config_option():
        echo("Hello, World!")

    result = invoke(missing_config_option)

    assert result.exception
    assert type(result.exception) is RuntimeError
    assert str(result.exception) == (
        "--no-config NoConfigOption must be used alongside ConfigOption."
    )

    assert not result.output
    assert result.exit_code == 1


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

    assert not result.stdout
    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert result.exit_code == 1


@all_config_formats
def test_conf_file_overrides_defaults(
    invoke,
    simple_config_cli,
    create_config,
    httpserver,
    conf_name,
    conf_text,
    conf_data,
    assert_output_regex,
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
            "default",
            color=False,
        )
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
        assert_output_regex(result.stderr, debug_log)

        assert result.exit_code == 0


@all_config_formats
def test_auto_envvar_conf(
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
    assert "CONFIG_CLI1_CONFIG" in result.stdout
    assert not result.stderr
    assert result.exit_code == 0

    # Create a local config.
    conf_filepath = create_config(conf_name, conf_text)

    # Create a remote config.
    httpserver.expect_request(f"/{conf_name}").respond_with_data(conf_text)
    conf_url = httpserver.url_for(f"/{conf_name}")

    for conf_path in conf_filepath, conf_url:
        conf_path = create_config(conf_name, conf_text)
        result = invoke(
            simple_config_cli,
            "default",
            color=False,
            env={"CONFIG_CLI1_CONFIG": str(conf_path)},
        )
        assert result.stdout == (
            "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
        )
        # Debug level has been activated by configuration file.
        assert result.stderr.startswith(
            f"Load configuration matching {conf_path}\n"
            "debug: Set <Logger click_extra (DEBUG)> to DEBUG.\n"
            "debug: Set <RootLogger root (DEBUG)> to DEBUG.\n",
        )
        assert result.exit_code == 0


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
            "default",
            "--int-param",
            "15",
        )
        assert result.stdout == (
            "dummy_flag = False\nmy_list = ('super', 'wow')\nint_parameter = 15\n"
        )
        assert result.stderr == f"Load configuration matching {conf_path}\n"
        assert result.exit_code == 0


@all_config_formats
def test_conf_metadata(
    invoke,
    create_config,
    httpserver,
    conf_name,
    conf_text,
    conf_data,
):
    @click.command
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
        assert result.stdout == (
            f"conf_source={conf_path}\n"
            f"conf_full={conf_data}\n"
            # No configuration values match the CLI's parameter structure, so default
            # map is left untouched.
            "default_map={}\n"
        )
        assert result.stderr == f"Load configuration matching {conf_path}\n"
        assert result.exit_code == 0


def test_multiple_cli_shared_conf(invoke, create_config):
    """Two CLIs sharing the same configuration file.

    Refs: https://github.com/kdeldycke/click-extra/issues/1277
    """

    conf_file = dedent(
        """
        # My shared configuration file.

        int_param = 99   # Will be ignored.

        [first-cli]
        int_param = 7

        [second-cli]
        int_param = 11
        random_stuff = "will be ignored"
        """,
    )

    conf_path = create_config("shared.toml", conf_file)

    search_path = conf_path.parent / "*.toml|*.yaml|*.yml|*.json|*.ini|*.xml"

    @click.command
    @option("--int-param", type=int, default=3)
    @config_option(default=search_path)
    @no_config_option
    def first_cli(int_param):
        echo(f"int = {int_param!r}")

    @click.command
    @option("--int-param", type=int, default=5)
    @config_option(default=search_path)
    @no_config_option
    def second_cli(int_param):
        echo(f"int = {int_param!r}")

    result = invoke(first_cli, color=False)
    assert result.stdout == "int = 7\n"
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(second_cli, color=False)
    assert result.stdout == "int = 11\n"
    assert not result.stderr
    assert result.exit_code == 0

    result = invoke(first_cli, "--no-config", color=False)
    assert result.stdout == "int = 3\n"
    assert result.stderr == "Skip configuration file loading altogether.\n"
    assert result.exit_code == 0

    result = invoke(second_cli, "--no-config", color=False)
    assert result.stdout == "int = 5\n"
    assert result.stderr == "Skip configuration file loading altogether.\n"
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("file_format_patterns", "expected_pattern"),
    [
        pytest.param(
            None,
            "*.toml|*.yaml|*.yml|*.json|*.json5|*.jsonc|*.hjson|*.ini|*.xml",
            id="default_all_formats",
        ),
        pytest.param(ConfigFormat.TOML, "*.toml", id="single_format"),
        pytest.param(ConfigFormat.YAML, "*.yaml|*.yml", id="yaml_multiple_patterns"),
        pytest.param(
            [ConfigFormat.TOML, ConfigFormat.JSON],
            "*.toml|*.json",
            id="multiple_formats_iterable",
        ),
        pytest.param(
            {
                ConfigFormat.TOML: ("*.toml", "*.tml"),
                ConfigFormat.JSON: "*.json",
            },
            "*.toml|*.tml|*.json",
            id="custom_patterns_dict",
        ),
        pytest.param(
            {
                ConfigFormat.TOML: ("*.toml", "*.config"),
                ConfigFormat.JSON: ("*.json", "*.config"),
            },
            "*.toml|*.config|*.json",
            id="deduplicated_patterns",
        ),
    ],
)
def test_file_pattern(file_format_patterns, expected_pattern):
    """Test the file_pattern property with different file format configurations."""
    opt = ConfigOption(file_format_patterns=file_format_patterns)
    assert opt.file_pattern == expected_pattern


@pytest.mark.parametrize(
    ("roaming", "force_posix", "current_platform", "expected_path"),
    [
        (True, False, is_macos(), "~/Library/Application Support/test-cli/"),
        (False, False, is_macos(), "~/Library/Application Support/test-cli/"),
        (True, True, is_macos(), "~/.test-cli/"),
        (False, True, is_macos(), "~/.test-cli/"),
        (True, False, is_unix_not_macos(), "~/.config/test-cli/"),
        (False, False, is_unix_not_macos(), "~/.config/test-cli/"),
        (True, True, is_unix_not_macos(), "~/.test-cli/"),
        (False, True, is_unix_not_macos(), "~/.test-cli/"),
        (True, False, is_windows(), "~\\AppData\\Roaming\\test-cli\\"),
        (False, False, is_windows(), "~\\AppData\\Local\\test-cli\\"),
        (True, True, is_windows(), "~\\AppData\\Roaming\\test-cli\\"),
        (False, True, is_windows(), "~\\AppData\\Local\\test-cli\\"),
    ],
)
def test_default_pattern_roaming_force_posix(
    roaming, force_posix, current_platform, expected_path
):
    """Test that roaming and force_posix affect the default pattern generation."""
    if not current_platform:
        pytest.skip("Platform-specific test.")

    @click.command
    @config_option(roaming=roaming, force_posix=force_posix)
    def test_cli():
        pass

    # Create a context and call default_pattern directly.
    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)

        assert config_opt.default_pattern() == (
            str(Path(expected_path).expanduser())
            + os.path.sep
            + config_opt.file_pattern
        )
