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

import logging
import os
import re
import sys
from pathlib import Path
from textwrap import dedent

import click
import pytest
from boltons.pathutils import shrinkuser
from extra_platforms import (
    is_macos,
    is_unix_not_macos,  # type: ignore[attr-defined]
    is_windows,
)

from click_extra import (
    NO_CONFIG,
    ConfigFormat,
    ConfigOption,
    LazyGroup,
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


@pytest.mark.parametrize(
    "conf_path",
    [
        pytest.param(Path("dummy.toml"), id="not-exist"),
        pytest.param(Path().parent, id="not-file"),
    ],
)
def test_conf_not_found(invoke, simple_config_cli, conf_path):
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


def test_conf_unparseable(invoke, simple_config_cli, create_config):
    """Explicit --config pointing to a file with garbage content."""
    conf_path = create_config("garbage.toml", "{{{{ not valid anything >>>")
    result = invoke(
        simple_config_cli,
        "--config",
        str(conf_path),
        "default",
        color=False,
    )
    assert not result.stdout
    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert "critical: Error parsing file as" in result.stderr
    assert result.exit_code == 2


def test_conf_empty_file(invoke, simple_config_cli, create_config):
    """Explicit --config pointing to an empty file."""
    conf_path = create_config("empty.toml", "")
    result = invoke(
        simple_config_cli,
        "--config",
        str(conf_path),
        "default",
        color=False,
    )
    assert not result.stdout
    assert f"Load configuration matching {conf_path}\n" in result.stderr
    assert "critical: Error parsing file as" in result.stderr
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


@pytest.mark.parametrize(
    ("conf_text", "expect_error"),
    [
        pytest.param(
            dedent("""\
                [config-cli3]
                dummy_flag = true
                my_list = ["item 1", "item #2", "Very Last Item!"]

                [config-cli3.subcommand]
                int_param = 3
                random_stuff = "will be ignored"
            """),
            True,
            id="unknown-param-rejected",
        ),
        pytest.param(
            dedent("""\
                [config-cli3]
                dummy_flag = true
                my_list = ["item 1", "item #2"]

                [config-cli3.subcommand]
                int_param = 3
            """),
            False,
            id="clean-config-accepted",
        ),
    ],
)
def test_strict_conf(invoke, create_config, conf_text, expect_error):
    """Strict mode rejects unknown params but accepts clean configs."""

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

    conf_path = create_config("strict.toml", conf_text)

    result = invoke(config_cli3, "--config", str(conf_path), "subcommand", color=False)

    if expect_error:
        assert result.exception
        assert type(result.exception) is ValueError
        assert (
            str(result.exception)
            == "Parameter 'random_stuff' found in second dict but not in first."
        )
        assert not result.stdout
        assert result.exit_code == 1
    else:
        assert result.exit_code == 0
        assert "dummy_flag    is True" in result.stdout
        assert "int_parameter is 3" in result.stdout

    assert f"Load configuration matching {conf_path}\n" in result.stderr


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


def test_conf_metadata_no_config(invoke):
    """ctx.meta entries are not set when --no-config skips loading."""

    @click.command
    @config_option
    @no_config_option
    @pass_context
    def config_metadata_noconf(ctx):
        echo(f"conf_source={ctx.meta.get('click_extra.conf_source', 'MISSING')}")
        echo(f"conf_full={ctx.meta.get('click_extra.conf_full', 'MISSING')}")

    result = invoke(config_metadata_noconf, "--no-config", color=False)
    assert result.exit_code == 0
    assert "conf_source=MISSING" in result.stdout
    assert "conf_full=MISSING" in result.stdout


def test_default_map_populated(invoke, create_config):
    """Verify default_map structure when config values match CLI parameters.

    Complements test_conf_metadata which only checks the empty default_map case
    (where no config values match the CLI's parameter structure).
    """
    conf_file = dedent(
        """
        [default-map-cli]
        flag_a = true

        [default-map-cli.sub]
        int_param = 7
        """
    )
    conf_path = create_config("map.toml", conf_file)

    @click.group
    @option("--flag-a/--no-flag-a")
    @config_option
    @pass_context
    def default_map_cli(ctx, flag_a):
        echo(f"flag_a={flag_a!r}")
        # After config loading, the group's default_map has group-level values
        # consumed by Click, plus the subcommand's nested section.
        echo(f"default_map={ctx.default_map}")

    @default_map_cli.command()
    @option("--int-param", type=int, default=10)
    @pass_context
    def sub(ctx, int_param):
        echo(f"int_param={int_param!r}")
        echo(f"sub_default_map={ctx.default_map}")

    result = invoke(
        default_map_cli,
        "--config",
        str(conf_path),
        "sub",
        color=False,
    )
    assert result.exit_code == 0
    assert "flag_a=True" in result.stdout
    assert "int_param=7" in result.stdout
    # Group's default_map retains the subcommand section after param resolution.
    assert "default_map={'flag_a': True, 'sub': {'int_param': 7}}" in result.stdout
    # Click passes default_map["sub"] to the subcommand's context.
    assert "sub_default_map={'int_param': 7}" in result.stdout


def test_default_map_none_without_config(invoke):
    """Verify default_map is left alone when --no-config is used."""

    @click.group
    @option("--flag/--no-flag")
    @config_option
    @no_config_option
    @pass_context
    def noconfig_map_cli(ctx, flag):
        echo(f"default_map={ctx.default_map}")

    @noconfig_map_cli.command()
    def sub():
        echo("ok")

    result = invoke(noconfig_map_cli, "--no-config", "sub", color=False)
    assert result.exit_code == 0
    assert "default_map=None" in result.stdout


def test_nested_subcommand_config(invoke, create_config):
    """Config propagates through group -> subgroup -> leaf command."""
    conf_file = dedent(
        """
        [nested-cli]
        top_param = "from_config"

        [nested-cli.mid]
        mid_param = "from_config"

        [nested-cli.mid.leaf]
        leaf_param = 42
        """
    )
    conf_path = create_config("nested.toml", conf_file)

    @group()
    @option("--top-param", default="default")
    def nested_cli(top_param):
        echo(f"top_param={top_param!r}")

    @nested_cli.group()
    @option("--mid-param", default="default")
    def mid(mid_param):
        echo(f"mid_param={mid_param!r}")

    @mid.command()
    @option("--leaf-param", type=int, default=0)
    def leaf(leaf_param):
        echo(f"leaf_param={leaf_param!r}")

    for cli_args, expected in (
        (
            ("--config", str(conf_path), "mid", "leaf"),
            ("top_param='from_config'", "mid_param='from_config'", "leaf_param=42"),
        ),
        (
            (
                "--config",
                str(conf_path),
                "--top-param",
                "override",
                "mid",
                "--mid-param",
                "override",
                "leaf",
                "--leaf-param",
                "99",
            ),
            ("top_param='override'", "mid_param='override'", "leaf_param=99"),
        ),
        (
            ("--no-config", "mid", "leaf"),
            ("top_param='default'", "mid_param='default'", "leaf_param=0"),
        ),
    ):
        result = invoke(nested_cli, *cli_args, color=False)
        assert result.exit_code == 0
        for exp in expected:
            assert exp in result.stdout


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

    for cli, args, expected_stdout, expected_stderr in (
        (first_cli, (), "int = 7\n", ""),
        (second_cli, (), "int = 11\n", ""),
        (
            first_cli,
            ("--no-config",),
            "int = 3\n",
            "Skip configuration file loading altogether.\n",
        ),
        (
            second_cli,
            ("--no-config",),
            "int = 5\n",
            "Skip configuration file loading altogether.\n",
        ),
    ):
        result = invoke(cli, *args, color=False)
        assert result.stdout == expected_stdout
        assert result.stderr == expected_stderr
        assert result.exit_code == 0


def test_lazy_group_config(invoke, create_config, tmp_path):
    """Test that lazy groups work with config files.

    Refs: https://github.com/kdeldycke/click-extra/issues/1332
    """
    conf_file = dedent(
        """
        [lazy-config-cli]
        dummy_flag = true

        [lazy-config-cli.foo_cmd]
        foo_param = "from_config"

        [lazy-config-cli.bar_cmd]
        bar_flag = true
        """
    )
    conf_path = create_config("lazy_config.toml", conf_file)

    (tmp_path / "lazy_cfg_foo.py").write_text(
        dedent("""\
            import click

            @click.command()
            @click.option("--foo-param", default="default_foo")
            def foo_cli(foo_param):
                click.echo(f"foo_param = {foo_param!r}")
        """)
    )

    (tmp_path / "lazy_cfg_bar.py").write_text(
        dedent("""\
            import click

            @click.command()
            @click.option("--bar-flag/--no-bar-flag", default=False)
            def bar_cli(bar_flag):
                click.echo(f"bar_flag = {bar_flag!r}")
        """)
    )

    module_names = ("lazy_cfg_foo", "lazy_cfg_bar")

    def make_cli():
        """Create a fresh CLI instance.

        .. caution::
            Each invocation needs its own CLI because LazyGroup caches resolved
            commands and the ConfigOption caches its params_template. A stale
            cache would prevent config values from reaching lazy subcommands on
            subsequent invocations.
        """
        for name in module_names:
            sys.modules.pop(name, None)

        @group(
            cls=LazyGroup,
            lazy_subcommands={
                "foo_cmd": "lazy_cfg_foo.foo_cli",
                "bar_cmd": "lazy_cfg_bar.bar_cli",
            },
        )
        @option("--dummy-flag/--no-flag")
        def lazy_config_cli(dummy_flag):
            echo(f"dummy_flag = {dummy_flag!r}")

        return lazy_config_cli

    sys.path.insert(0, str(tmp_path))
    try:
        for cli_args, expected in (
            (
                ("--config", str(conf_path), "foo_cmd"),
                ("dummy_flag = True", "foo_param = 'from_config'"),
            ),
            (
                ("--config", str(conf_path), "bar_cmd"),
                ("dummy_flag = True", "bar_flag = True"),
            ),
            (
                (
                    "--config",
                    str(conf_path),
                    "--no-flag",
                    "foo_cmd",
                    "--foo-param",
                    "override",
                ),
                ("dummy_flag = False", "foo_param = 'override'"),
            ),
        ):
            cli = make_cli()
            result = invoke(cli, *cli_args, color=False)
            assert result.exit_code == 0
            for exp in expected:
                assert exp in result.stdout

    finally:
        sys.path.remove(str(tmp_path))
        for name in module_names:
            sys.modules.pop(name, None)


def test_lazy_group_config_no_config_flag(invoke, create_config, tmp_path):
    """Test that --no-config works with lazy groups."""
    conf_file = dedent(
        """
        [lazy-noconfig-cli]
        param_value = "from_config"

        [lazy-noconfig-cli.sub_cmd]
        sub_param = "sub_from_config"
        """
    )
    conf_path = create_config("lazy_noconfig.toml", conf_file)

    (tmp_path / "lazy_nocfg_sub.py").write_text(
        dedent("""\
            import click

            @click.command()
            @click.option("--sub-param", default="sub_default")
            def sub_cli(sub_param):
                click.echo(f"sub_param = {sub_param!r}")
        """)
    )

    module_names = ("lazy_nocfg_sub",)

    def make_cli():
        for name in module_names:
            sys.modules.pop(name, None)

        @group(
            cls=LazyGroup,
            lazy_subcommands={"sub_cmd": "lazy_nocfg_sub.sub_cli"},
        )
        @option("--param-value", default="default_value")
        def lazy_noconfig_cli(param_value):
            echo(f"param_value = {param_value!r}")

        return lazy_noconfig_cli

    sys.path.insert(0, str(tmp_path))
    try:
        for cli_args, expected_stdout, skip_msg in (
            (
                ("--config", str(conf_path), "sub_cmd"),
                ("param_value = 'from_config'", "sub_param = 'sub_from_config'"),
                False,
            ),
            (
                ("--no-config", "sub_cmd"),
                ("param_value = 'default_value'", "sub_param = 'sub_default'"),
                True,
            ),
            (
                ("--config", str(conf_path), "--no-config", "sub_cmd"),
                ("param_value = 'default_value'", "sub_param = 'sub_default'"),
                True,
            ),
        ):
            cli = make_cli()
            result = invoke(cli, *cli_args, color=False)
            assert result.exit_code == 0
            for exp in expected_stdout:
                assert exp in result.stdout
            if skip_msg:
                assert "Skip configuration file loading altogether." in result.stderr

    finally:
        sys.path.remove(str(tmp_path))
        for name in module_names:
            sys.modules.pop(name, None)


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


@pytest.mark.parametrize(
    ("search_parents", "subdirs", "create_file", "expected_start"),
    [
        pytest.param(
            False,
            ("subdir",),
            True,
            lambda p: [str(p / "subdir" / "config.toml")],
            id="no-search",
        ),
        pytest.param(
            True,
            ("level1", "level2", "level3"),
            True,
            lambda p: [
                str(p / "level1" / "level2" / "level3" / "config.toml"),
                str(p / "level1" / "level2" / "level3"),
                str(p / "level1" / "level2"),
                str(p / "level1"),
                str(p),
            ],
            id="file-path",
        ),
        pytest.param(
            True,
            ("level1", "level2", "level3"),
            False,
            lambda p: [
                str(p / "level1" / "level2" / "level3"),
                str(p / "level1" / "level2"),
                str(p / "level1"),
                str(p),
            ],
            id="directory-path",
        ),
        pytest.param(
            True,
            (),
            True,
            lambda p: [str(p / "config.toml"), str(p)],
            id="shallow-reaches-root",
        ),
        pytest.param(
            True,
            ("a", "b", "c"),
            True,
            lambda p: [
                str(p / "a" / "b" / "c" / "config.toml"),
                str(p / "a" / "b" / "c"),
                str(p / "a" / "b"),
                str(p / "a"),
                str(p),
            ],
            id="deep-order",
        ),
    ],
)
def test_parent_patterns(
    tmp_path, search_parents, subdirs, create_file, expected_start
):
    deep_path = tmp_path
    for subdir in subdirs:
        deep_path = deep_path / subdir
    deep_path.mkdir(parents=True, exist_ok=True)

    if create_file:
        config_file = deep_path / "config.toml"
        config_file.write_text("[test]\nvalue = 1")
        input_path = str(config_file)
    else:
        input_path = str(deep_path)

    @click.command
    @config_option(search_parents=search_parents)
    def test_cli():
        pass

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        patterns = list(config_opt.parent_patterns(input_path))

    expected = expected_start(tmp_path)
    for i, exp in enumerate(expected):
        assert patterns[i] == exp, f"Pattern {i} mismatch"

    assert all(isinstance(p, str) for p in patterns)

    if search_parents:
        assert all(Path(p).is_absolute() for p in patterns)
        root_path = Path("/") if not is_windows() else Path(tmp_path.drive + "\\")
        assert Path(patterns[-1]) == root_path


def test_parent_patterns_with_magic_pattern():
    """Test parent_patterns with a glob pattern containing magic characters."""

    @click.command
    @config_option(search_parents=True)
    def test_cli():
        pass

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)

        with pytest.raises(
            NotImplementedError,
            match="Parent search for magic patterns not implemented",
        ):
            list(config_opt.parent_patterns("/some/path/*.toml"))


def test_parent_patterns_relative_path(tmp_path):
    """Test parent_patterns resolves relative paths to absolute."""
    deep_path = tmp_path / "level1" / "level2"
    deep_path.mkdir(parents=True)
    config_file = deep_path / "config.toml"
    config_file.write_text("[test]\nvalue = 1")

    @click.command
    @config_option(search_parents=True)
    def test_cli():
        pass

    # Change to the parent directory to create a relative path
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path / "level1")
        relative_path = "level2/config.toml"

        with click.Context(test_cli, info_name="test-cli"):
            config_opt = search_params(test_cli.params, ConfigOption)

            patterns = list(config_opt.parent_patterns(relative_path))

            # All patterns should be absolute
            assert all(Path(p).is_absolute() for p in patterns)

            # First pattern should resolve to the config file
            assert Path(patterns[0]) == config_file
    finally:
        os.chdir(old_cwd)


def test_config_option_default_no_config(invoke, create_config):
    """ConfigOption with default=NO_CONFIG disables autodiscovery."""

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option(default=NO_CONFIG)
    def no_autodiscovery_cli(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    @no_autodiscovery_cli.command()
    @option("--int-param", type=int, default=10)
    def default_command(int_param):
        echo(f"int_parameter = {int_param!r}")

    # --help shows "disabled" as default.
    result = invoke(no_autodiscovery_cli, "--help", color=False)
    assert result.exit_code == 0
    assert "disabled" in result.stdout

    # Running without --config produces no stderr.
    result = invoke(no_autodiscovery_cli, "default")
    assert result.exit_code == 0
    assert result.stdout == "dummy_flag = False\nint_parameter = 10\n"
    assert not result.stderr

    # Explicit --config still loads the file.
    conf_path = create_config(
        "custom.toml",
        dedent("""\
            [no-autodiscovery-cli]
            dummy_flag = true
        """),
    )
    result = invoke(no_autodiscovery_cli, "--config", str(conf_path), "default")
    assert result.exit_code == 0
    assert "dummy_flag = True" in result.stdout


def test_no_config_explicit_with_default_no_config(invoke):
    """--no-config still prints the skip message even when NO_CONFIG is the default."""

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option(default=NO_CONFIG)
    @no_config_option
    def no_autodiscovery_cli2(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    @no_autodiscovery_cli2.command()
    def default_command():
        echo("ok")

    # Explicit --no-config should print the skip message.
    result = invoke(no_autodiscovery_cli2, "--no-config", "default")
    assert result.exit_code == 0
    assert result.stderr == "Skip configuration file loading altogether.\n"


def test_excluded_params(invoke, create_config):
    """Custom excluded_params prevents config values from being applied."""
    conf_file = dedent(
        """\
        [excluded-cli]
        flag_a = true
        flag_b = true
        """
    )
    conf_path = create_config("excluded.toml", conf_file)

    @click.command
    @option("--flag-a/--no-flag-a")
    @option("--flag-b/--no-flag-b")
    @config_option(excluded_params=("excluded-cli.flag_b",))
    def excluded_cli(flag_a, flag_b):
        echo(f"flag_a={flag_a!r}")
        echo(f"flag_b={flag_b!r}")

    result = invoke(excluded_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 0
    # flag_a is loaded from config.
    assert "flag_a=True" in result.stdout
    # flag_b is excluded, so it keeps its default.
    assert "flag_b=False" in result.stdout


def test_multiple_files_matching_glob(invoke, create_config, tmp_path):
    """When multiple files match a glob, only the first parseable one is used."""
    # Create two config files with different values in the same directory.
    # One sets param_a, the other sets param_b. Only one file should be loaded.
    (tmp_path / "first.toml").write_text(
        dedent("""\
            [glob-cli]
            param_a = "from_first"
            param_b = "from_first"
        """)
    )
    (tmp_path / "second.toml").write_text(
        dedent("""\
            [glob-cli]
            param_a = "from_second"
            param_b = "from_second"
        """)
    )

    search_path = tmp_path / "*.toml"

    @click.command
    @option("--param-a", default="default_a")
    @option("--param-b", default="default_b")
    @config_option(default=search_path)
    def glob_cli(param_a, param_b):
        echo(f"param_a={param_a!r}")
        echo(f"param_b={param_b!r}")

    result = invoke(glob_cli, color=False)
    assert result.exit_code == 0
    # Both params come from the same file — values are not merged across files.
    assert (
        "param_a='from_first'" in result.stdout
        and "param_b='from_first'" in result.stdout
    ) or (
        "param_a='from_second'" in result.stdout
        and "param_b='from_second'" in result.stdout
    )


def test_forced_flags_warnings(caplog):
    """Warnings fire when SPLIT or NODIR flags are missing."""
    from wcmatch import fnmatch, glob

    with caplog.at_level(logging.WARNING, logger="click_extra"):
        ConfigOption(
            file_pattern_flags=fnmatch.NEGATE,  # missing SPLIT
            search_pattern_flags=glob.GLOBSTAR | glob.FOLLOW,  # missing NODIR
        )

    assert "Forcing SPLIT flag" in caplog.text
    assert "Forcing NODIR flag" in caplog.text


def test_no_enabled_formats_raises():
    """ValueError raised when all formats are disabled."""
    import unittest.mock

    with unittest.mock.patch.object(
        ConfigFormat, "enabled", new_callable=lambda: property(lambda self: False)
    ):
        with pytest.raises(ValueError, match="No configuration format is enabled"):
            ConfigOption(file_format_patterns=ConfigFormat.TOML)
