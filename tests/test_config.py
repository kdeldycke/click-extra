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
from boltons.iterutils import flatten, unique
from boltons.pathutils import shrinkuser
from extra_platforms import (  # type: ignore[attr-defined]
    is_macos,
    is_unix_not_macos,
    is_windows,
)
from extra_platforms.pytest import unless_unix_not_macos  # type: ignore[attr-defined]

from click_extra import (
    NO_CONFIG,
    VCS,
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
    validate_config_option,
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

PYPROJECT_TOML_FILE, PYPROJECT_TOML_DATA = (
    dedent("""\
        [build-system]
        requires = ["setuptools"]

        [tool.config-cli1]
        verbosity = "DEBUG"
        blahblah = 234
        dummy_flag = true
        my_list = ["pip", "npm", "gem"]

        [tool.config-cli1.default]
        int_param = 3
        random_stuff = "will be ignored"
        """),
    {
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
    fp = ",".join(unique(flatten(f.patterns for f in ConfigFormat if f.enabled)))
    assert f"{{{fp}}}]" in help_screen

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


def test_conf_unparsable(invoke, simple_config_cli, create_config):
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
    assert (
        "default_map=ChainMap({'flag_a': True, 'sub': {'int_param': 7}}, {})"
        in result.stdout
    )
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
            ",".join(
                unique(flatten(fmt.patterns for fmt in ConfigFormat if fmt.enabled))
            ),
            id="default_all_formats",
        ),
        pytest.param(ConfigFormat.TOML, "*.toml", id="single_format"),
        pytest.param(ConfigFormat.YAML, "*.yaml,*.yml", id="yaml_multiple_patterns"),
        pytest.param(
            [ConfigFormat.TOML, ConfigFormat.JSON],
            "*.toml,*.json",
            id="multiple_formats_iterable",
        ),
        pytest.param(
            {
                ConfigFormat.TOML: ("*.toml", "*.tml"),
                ConfigFormat.JSON: "*.json",
            },
            "*.toml,*.tml,*.json",
            id="custom_patterns_dict",
        ),
        pytest.param(
            {
                ConfigFormat.TOML: ("*.toml", "*.config"),
                ConfigFormat.JSON: ("*.json", "*.config"),
            },
            "*.toml,*.config,*.json",
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
    roaming, force_posix, current_platform, expected_path, monkeypatch
):
    """Test that roaming and force_posix affect the default pattern generation."""
    if not current_platform:
        pytest.skip("Platform-specific test.")

    # Ensure XDG_CONFIG_HOME doesn't override the default config directory.
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    @click.command
    @config_option(roaming=roaming, force_posix=force_posix)
    def test_cli():
        pass

    # Create a context and call default_pattern directly.
    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)

        fp = config_opt.file_pattern
        suffix = f"{{{fp}}}" if "," in fp else fp
        assert config_opt.default_pattern() == (
            str(Path(expected_path).expanduser()) + os.path.sep + suffix
        )


@unless_unix_not_macos
@pytest.mark.parametrize("force_posix", [True, False])
def test_default_pattern_xdg_config_home(force_posix, tmp_path, monkeypatch):
    """Test that default_pattern respects XDG_CONFIG_HOME on Linux."""
    custom_config = tmp_path / "custom-config"
    custom_config.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom_config))

    @click.command
    @config_option(force_posix=force_posix)
    def test_cli():
        pass

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        pattern = config_opt.default_pattern()

        if force_posix:
            # force_posix ignores XDG_CONFIG_HOME and uses ~/.test-cli/.
            assert pattern.startswith(str(Path("~/.test-cli").expanduser().resolve()))
        else:
            # XDG_CONFIG_HOME is resolved into the pattern.
            assert pattern.startswith(str(custom_config.resolve() / "test-cli"))


@pytest.mark.parametrize(
    ("search_parents", "subdirs", "create_file", "expected_start"),
    [
        pytest.param(
            False,
            ("subdir",),
            True,
            lambda p: [(str(p / "subdir"), "config.toml")],
            id="no-search",
        ),
        pytest.param(
            True,
            ("level1", "level2", "level3"),
            True,
            lambda p: [
                (str(p / "level1" / "level2" / "level3"), "config.toml"),
                (str(p / "level1" / "level2"), "config.toml"),
                (str(p / "level1"), "config.toml"),
                (str(p), "config.toml"),
            ],
            id="file-path",
        ),
        pytest.param(
            True,
            ("level1", "level2", "level3"),
            False,
            lambda p: [
                (str(p / "level1" / "level2" / "level3"), ""),
                (str(p / "level1" / "level2"), ""),
                (str(p / "level1"), ""),
                (str(p), ""),
            ],
            id="directory-path",
        ),
        pytest.param(
            True,
            (),
            True,
            lambda p: [(str(p), "config.toml")],
            id="shallow-reaches-root",
        ),
        pytest.param(
            True,
            ("a", "b", "c"),
            True,
            lambda p: [
                (str(p / "a" / "b" / "c"), "config.toml"),
                (str(p / "a" / "b"), "config.toml"),
                (str(p / "a"), "config.toml"),
                (str(p), "config.toml"),
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

    assert all(isinstance(p, tuple) and len(p) == 2 for p in patterns)

    if search_parents:
        assert all(Path(root_dir).is_absolute() for root_dir, _ in patterns)
        root_path = Path("/") if not is_windows() else Path(tmp_path.drive + "\\")
        assert Path(patterns[-1][0]) == root_path


@pytest.mark.parametrize(
    ("pattern_factory", "expected_factory"),
    [
        pytest.param(
            lambda p: str(p / "a" / "b" / "*.toml"),
            lambda p: [
                (str(p / "a" / "b"), "*.toml"),
                (str(p / "a"), "*.toml"),
                (str(p), "*.toml"),
                *((str(parent), "*.toml") for parent in p.parents),
            ],
            id="file-glob-at-leaf",
        ),
        pytest.param(
            lambda p: "*.toml",
            lambda p: [(None, "*.toml")],
            id="entirely-magic",
        ),
        pytest.param(
            lambda p: str(p / "proj*" / "config.toml"),
            lambda p: [
                (str(p), str(Path("proj*") / "config.toml")),
                *(
                    (str(parent), str(Path("proj*") / "config.toml"))
                    for parent in p.parents
                ),
            ],
            id="magic-in-directory",
        ),
        pytest.param(
            lambda p: str(p / "a" / "*.toml|*.yaml|*.yml"),
            lambda p: [
                (str(p / "a"), "*.toml|*.yaml|*.yml"),
                (str(p), "*.toml|*.yaml|*.yml"),
                *((str(parent), "*.toml|*.yaml|*.yml") for parent in p.parents),
            ],
            id="pipe-separated-multi-glob",
        ),
        pytest.param(
            lambda p: str(p / "proj*" / "*.toml"),
            lambda p: [
                (str(p), str(Path("proj*", "*.toml"))),
                *((str(parent), str(Path("proj*", "*.toml"))) for parent in p.parents),
            ],
            id="multiple-magic-parts-in-suffix",
        ),
        pytest.param(
            lambda p: str(p / "*.toml"),
            lambda p: [
                (str(p), "*.toml"),
                *((str(parent), "*.toml") for parent in p.parents),
            ],
            id="single-depth-magic",
        ),
        pytest.param(
            lambda p: "~/a/b/*.toml",
            lambda p: [(None, "~/a/b/*.toml")],
            id="tilde-is-magic",
        ),
        pytest.param(
            lambda p: str(Path("**", "config.toml")),
            lambda p: [(None, str(Path("**", "config.toml")))],
            id="globstar-entirely-magic",
        ),
    ],
)
def test_parent_patterns_with_magic_pattern(
    tmp_path, pattern_factory, expected_factory
):
    """Test parent_patterns with glob patterns containing magic characters."""

    @click.command
    @config_option(search_parents=True)
    def test_cli():
        pass

    pattern = pattern_factory(tmp_path)
    expected = expected_factory(tmp_path)

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        patterns = list(config_opt.parent_patterns(pattern))

    assert patterns == expected


def test_parent_patterns_magic_no_search(tmp_path):
    """Magic pattern with search_parents=False yields only the original."""

    @click.command
    @config_option(search_parents=False)
    def test_cli():
        pass

    pattern = str(tmp_path / "a" / "*.toml|*.yaml")

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        patterns = list(config_opt.parent_patterns(pattern))

    assert patterns == [(str(tmp_path / "a"), "*.toml|*.yaml")]


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

            # All root_dirs should be absolute
            assert all(Path(root_dir).is_absolute() for root_dir, _ in patterns)

            # First pattern should resolve to the config file's parent
            root_dir, file_pattern = patterns[0]
            assert Path(root_dir) == config_file.parent
            assert file_pattern == config_file.name
    finally:
        os.chdir(old_cwd)


def test_parent_patterns_stop_at_path(tmp_path):
    """stop_at as a path limits the parent directory walk."""
    deep_path = tmp_path / "a" / "b" / "c"
    deep_path.mkdir(parents=True)
    config_file = deep_path / "config.toml"
    config_file.write_text("[test]\nvalue = 1")

    boundary = tmp_path / "a"

    @click.command
    @config_option(search_parents=True, stop_at=boundary)
    def test_cli():
        pass

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        patterns = list(config_opt.parent_patterns(str(config_file)))

    # First yield should be (parent_of_file, filename).
    root_dir, file_pattern = patterns[0]
    assert Path(root_dir) == config_file.parent
    assert file_pattern == config_file.name
    # Every root_dir should be inside or equal to the boundary.
    for root_dir, _ in patterns:
        assert Path(root_dir).is_relative_to(boundary), (
            f"{root_dir} is outside boundary {boundary}"
        )


@pytest.mark.parametrize(
    ("has_vcs", "expected_bounded"),
    [
        pytest.param(True, True, id="with-vcs-root"),
        pytest.param(False, False, id="no-vcs-root"),
    ],
)
def test_parent_patterns_stop_at_vcs(tmp_path, has_vcs, expected_bounded):
    """stop_at=VCS stops at VCS root, or walks to filesystem root if none."""
    vcs_root = tmp_path / "repo"
    vcs_root.mkdir()
    if has_vcs:
        (vcs_root / ".git").mkdir()

    deep_path = vcs_root / "src" / "pkg"
    deep_path.mkdir(parents=True)

    @click.command
    @config_option(search_parents=True, stop_at=VCS)
    def test_cli():
        pass

    pattern = str(deep_path / "*.toml")

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        patterns = list(config_opt.parent_patterns(pattern))

    assert patterns[0] == (str(deep_path), "*.toml")

    if expected_bounded:
        for root_dir, _ in patterns:
            assert Path(root_dir).is_relative_to(vcs_root), (
                f"{root_dir} is outside VCS root {vcs_root}"
            )
    else:
        root_path = Path("/") if not is_windows() else Path(tmp_path.drive + "\\")
        assert Path(patterns[-1][0]) == root_path


def test_parent_patterns_inaccessible_directory(tmp_path):
    """Walk stops at an inaccessible directory."""
    deep_path = tmp_path / "a" / "b" / "c"
    deep_path.mkdir(parents=True)
    config_file = deep_path / "config.toml"
    config_file.write_text("[test]\nvalue = 1")

    @click.command
    @config_option(search_parents=True)
    def test_cli():
        pass

    from unittest.mock import patch

    original_access = os.access

    def fake_access(path, mode, **kwargs):
        if Path(path).resolve() == (tmp_path / "a").resolve():
            return False
        return original_access(path, mode, **kwargs)

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        with patch("click_extra.config.os.access", side_effect=fake_access):
            patterns = list(config_opt.parent_patterns(str(config_file)))

    # First yield: (parent_of_file, filename).
    root_dir, file_pattern = patterns[0]
    assert Path(root_dir) == config_file.parent
    assert file_pattern == config_file.name
    # Should stop before tmp_path/a (inaccessible).
    for root_dir, _ in patterns:
        assert Path(root_dir) != tmp_path / "a"
        assert Path(root_dir) != tmp_path


@pytest.mark.parametrize(
    ("vcs_dir", "expected"),
    [
        pytest.param(".git", "found", id="git"),
        pytest.param(".hg", "found", id="hg"),
        pytest.param(None, None, id="no-vcs"),
    ],
)
def test_find_vcs_root(tmp_path, vcs_dir, expected):
    """Test _find_vcs_root with .git, .hg, and no VCS markers."""
    repo = tmp_path / "repo"
    repo.mkdir()
    if vcs_dir:
        (repo / vcs_dir).mkdir()

    deep = repo / "a" / "b"
    deep.mkdir(parents=True)

    result = ConfigOption._find_vcs_root(deep)
    if expected:
        assert result == repo
    else:
        assert result is None


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


def test_included_params(invoke, create_config):
    """Only parameters in included_params are loaded from config."""
    conf_file = dedent(
        """\
        [included-cli]
        flag_a = true
        flag_b = true
        """
    )
    conf_path = create_config("included.toml", conf_file)

    @click.command
    @option("--flag-a/--no-flag-a")
    @option("--flag-b/--no-flag-b")
    @config_option(included_params=("included-cli.flag_a",))
    def included_cli(flag_a, flag_b):
        echo(f"flag_a={flag_a!r}")
        echo(f"flag_b={flag_b!r}")

    result = invoke(included_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 0
    # flag_a is in the allowlist, so it's loaded from config.
    assert "flag_a=True" in result.stdout
    # flag_b is not in the allowlist, so it keeps its default.
    assert "flag_b=False" in result.stdout


def test_included_params_empty(invoke, create_config):
    """An empty included_params excludes all params from config."""
    conf_file = dedent(
        """\
        [empty-included-cli]
        flag_a = true
        flag_b = true
        """
    )
    conf_path = create_config("empty_included.toml", conf_file)

    @click.command
    @option("--flag-a/--no-flag-a")
    @option("--flag-b/--no-flag-b")
    @config_option(included_params=())
    def empty_included_cli(flag_a, flag_b):
        echo(f"flag_a={flag_a!r}")
        echo(f"flag_b={flag_b!r}")

    result = invoke(empty_included_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 0
    # Both flags keep their defaults since nothing is included.
    assert "flag_a=False" in result.stdout
    assert "flag_b=False" in result.stdout


def test_included_and_excluded_params_conflict():
    """Providing both included_params and excluded_params raises ValueError."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        ConfigOption(
            excluded_params=("foo.bar",),
            included_params=("foo.baz",),
        )


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
    """Warnings fire when SPLIT, BRACE or NODIR flags are missing."""
    from wcmatch import fnmatch, glob

    with caplog.at_level(logging.WARNING, logger="click_extra"):
        ConfigOption(
            file_pattern_flags=fnmatch.NEGATE,  # missing SPLIT
            search_pattern_flags=glob.GLOBSTAR | glob.FOLLOW,  # missing BRACE and NODIR
        )

    assert "Forcing SPLIT flag" in caplog.text
    assert "Forcing BRACE flag" in caplog.text
    assert "Forcing NODIR flag" in caplog.text


@pytest.mark.parametrize(
    "ext",
    [
        pytest.param("toml", id="toml"),
        pytest.param("yaml", id="yaml"),
        pytest.param("json", id="json"),
        pytest.param("ini", id="ini"),
    ],
)
def test_brace_multi_format_search(invoke, tmp_path, ext):
    """All format extensions are found in the search directory.

    Regression test: before BRACE expansion, only the first format in the
    default pattern got the directory prefix — others were searched in CWD.
    """
    conf_texts = {
        "toml": "[brace-cli]\nint_param = 42\n",
        "yaml": "brace-cli:\n  int_param: 42\n",
        "json": '{"brace-cli": {"int_param": 42}}\n',
        "ini": "[brace-cli]\nint_param = 42\n",
    }
    config_file = tmp_path / f"config.{ext}"
    config_file.write_text(conf_texts[ext])

    # Build a brace-expansion search pattern covering all test formats.
    search_pattern = str(tmp_path / "{*.toml,*.yaml,*.json,*.ini}")

    @click.command
    @option("--int-param", type=int, default=0)
    @config_option(default=search_pattern)
    def brace_cli(int_param):
        echo(f"int_param={int_param!r}")

    result = invoke(brace_cli, color=False)
    assert result.exit_code == 0
    assert "int_param=42" in result.stdout


def test_root_dir_parent_search_finds_non_toml(invoke, tmp_path):
    """Parent search with root_dir correctly finds non-TOML config in parents.

    Before the root_dir refactoring, SPLIT patterns like ``*.toml|*.yaml``
    only applied the directory prefix to the first sub-pattern. Now with
    root_dir, all sub-patterns are scoped to the correct directory.
    """
    parent_dir = tmp_path / "project"
    parent_dir.mkdir()
    child_dir = parent_dir / "src"
    child_dir.mkdir()

    # Place a YAML config only in the parent, not the child.
    yaml_config = parent_dir / "config.yaml"
    yaml_config.write_text("parent-cli:\n  int_param: 99\n")

    search_pattern = str(child_dir / "*.toml|*.yaml")

    @click.command
    @option("--int-param", type=int, default=0)
    @config_option(default=search_pattern, search_parents=True, stop_at=tmp_path)
    def parent_cli(int_param):
        echo(f"int_param={int_param!r}")

    result = invoke(parent_cli, color=False)
    assert result.exit_code == 0
    assert "int_param=99" in result.stdout


def test_no_enabled_formats_raises():
    """ValueError raised when all formats are disabled."""
    import unittest.mock

    with unittest.mock.patch.object(
        ConfigFormat, "enabled", new_callable=lambda: property(lambda self: False)
    ):
        with pytest.raises(ValueError, match="No configuration format is enabled"):
            ConfigOption(file_format_patterns=ConfigFormat.TOML)


def test_pyproject_toml_in_defaults():
    """ConfigOption() with default file_format_patterns includes PYPROJECT_TOML."""
    opt = ConfigOption()
    assert ConfigFormat.PYPROJECT_TOML in opt.file_format_patterns


def test_pyproject_toml_tool_extraction(simple_config_cli):
    """parse_conf with PYPROJECT_TOML returns the [tool] subsection."""
    opt = ConfigOption(
        file_format_patterns={ConfigFormat.PYPROJECT_TOML: ("pyproject.toml",)},
    )
    results = list(
        opt.parse_conf(PYPROJECT_TOML_FILE, formats=[ConfigFormat.PYPROJECT_TOML])
    )
    assert len(results) == 1
    assert results[0] == PYPROJECT_TOML_DATA


def test_pyproject_toml_no_tool_section(simple_config_cli):
    """pyproject.toml without [tool] returns empty dict."""
    content = dedent("""\
        [build-system]
        requires = ["setuptools"]
        """)
    opt = ConfigOption(
        file_format_patterns={ConfigFormat.PYPROJECT_TOML: ("pyproject.toml",)},
    )
    results = list(opt.parse_conf(content, formats=[ConfigFormat.PYPROJECT_TOML]))
    # parse_conf yields the empty dict; downstream read_and_parse_conf skips it.
    assert len(results) == 1
    assert results[0] == {}


def test_file_pattern_with_pyproject_toml():
    """Explicit file_format_patterns with PYPROJECT_TOML works."""
    opt = ConfigOption(
        file_format_patterns={ConfigFormat.PYPROJECT_TOML: ("pyproject.toml",)},
    )
    assert ConfigFormat.PYPROJECT_TOML in opt.file_format_patterns
    assert opt.file_pattern == "pyproject.toml"


def test_pyproject_toml_overrides_defaults(
    invoke,
    create_config,
):
    """End-to-end: a CLI with default formats reads from pyproject.toml."""
    conf_path = create_config("pyproject.toml", PYPROJECT_TOML_FILE)

    @click.group
    @option("--dummy-flag/--no-flag")
    @option("--my-list", multiple=True)
    @config_option
    def config_cli1(dummy_flag, my_list):
        echo(f"dummy_flag = {dummy_flag!r}")
        echo(f"my_list = {my_list!r}")

    @config_cli1.command()
    @option("--int-param", type=int, default=10)
    def default_command(int_param):
        echo(f"int_parameter = {int_param!r}")

    result = invoke(
        config_cli1,
        "--config",
        str(conf_path),
        "default",
        color=False,
    )
    assert result.exit_code == 0
    assert result.stdout == (
        "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
    )


def test_validate_config_valid(invoke, create_config):
    """--validate-config with a valid config file exits 0."""
    conf_text = dedent("""\
        [validate-cli]
        dummy_flag = true
        my_list = ["pip", "npm"]

        [validate-cli.sub]
        int_param = 3
        """)
    conf_path = create_config("valid.toml", conf_text)

    @click.group
    @option("--dummy-flag/--no-flag")
    @option("--my-list", multiple=True)
    @config_option
    @validate_config_option
    def validate_cli(dummy_flag, my_list):
        echo(f"dummy_flag = {dummy_flag!r}")

    @validate_cli.command
    @option("--int-param", type=int, default=10)
    def sub(int_param):
        echo(f"int_parameter = {int_param!r}")

    result = invoke(validate_cli, "--validate-config", str(conf_path), color=False)
    assert result.exit_code == 0
    assert "is valid" in result.stderr


def test_validate_config_invalid_keys(invoke, create_config):
    """--validate-config with unrecognized keys exits 1."""
    conf_text = dedent("""\
        [validate-cli]
        dummy_flag = true
        unknown_key = "bad"

        [validate-cli.sub]
        int_param = 3
        random_stuff = "will be rejected"
        """)
    conf_path = create_config("invalid.toml", conf_text)

    @click.group
    @option("--dummy-flag/--no-flag")
    @option("--my-list", multiple=True)
    @config_option
    @validate_config_option
    def validate_cli(dummy_flag, my_list):
        echo(f"dummy_flag = {dummy_flag!r}")

    @validate_cli.command
    @option("--int-param", type=int, default=10)
    def sub(int_param):
        echo(f"int_parameter = {int_param!r}")

    result = invoke(validate_cli, "--validate-config", str(conf_path), color=False)
    assert result.exit_code == 1
    assert "validation error" in result.stderr.lower()


@pytest.mark.parametrize(
    ("default_pattern", "expected_help_default"),
    [
        pytest.param("~/*", "~/*", id="broad_glob"),
        pytest.param("~/.commandrc", "~/.commandrc", id="exact_path"),
    ],
)
def test_extensionless_config(
    invoke, create_config, default_pattern, expected_help_default
):
    """Both broad and exact default patterns resolve the same .commandrc file.

    The ``default`` parameter is printed as-is on the help screen, so an exact
    path is more informative than a broad glob, but both locate the same file.
    """
    conf_text = dedent("""\
        extensionless-cli:
            dummy_flag: true
        """)
    conf_path = create_config(".commandrc", conf_text)

    @click.command(context_settings={"show_default": True})
    @option("--dummy-flag/--no-flag")
    @config_option(
        default=default_pattern,
        file_format_patterns={ConfigFormat.YAML: ".commandrc"},
    )
    def extensionless_cli(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    # Help screen shows the raw default pattern as-is.
    result = invoke(extensionless_cli, "--help", color=False)
    assert result.exit_code == 0
    # Join wrapped lines to match the default value regardless of terminal width.
    help_screen = " ".join(result.stdout.split())
    assert f"[default: {expected_help_default}]" in help_screen

    # Both patterns resolve the same config file.
    result = invoke(
        extensionless_cli,
        "--config",
        str(conf_path),
        color=False,
    )
    assert result.exit_code == 0
    assert result.stdout == "dummy_flag = True\n"


def test_validate_config_unparsable(invoke, create_config):
    """--validate-config with garbage content exits 2."""
    conf_path = create_config("garbage.toml", "{{{{ not valid anything >>>")

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option
    @validate_config_option
    def validate_cli(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    @validate_cli.command
    def sub():
        pass

    result = invoke(validate_cli, "--validate-config", str(conf_path), color=False)
    assert result.exit_code == 2
    assert "Error parsing" in result.stderr


def test_validate_config_missing_file(invoke, tmp_path):
    """--validate-config with a nonexistent file is caught by Click's Path(exists=True)."""

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option
    @validate_config_option
    def validate_cli(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    @validate_cli.command
    def sub():
        pass

    missing = str(tmp_path / "nonexistent.toml")
    result = invoke(validate_cli, "--validate-config", missing, color=False)
    assert result.exit_code == 2


def test_validate_config_requires_config_option(invoke, tmp_path):
    """--validate-config without @config_option raises RuntimeError."""
    dummy = tmp_path / "dummy.toml"
    dummy.touch()

    @click.command
    @validate_config_option
    def missing_config():
        echo("Hello, World!")

    result = invoke(missing_config, "--validate-config", str(dummy))

    assert result.exception
    assert type(result.exception) is RuntimeError
    assert "ValidateConfigOption must be used alongside ConfigOption" in str(
        result.exception
    )
    assert not result.output
    assert result.exit_code == 1


def test_validate_config_pyproject_toml(invoke, create_config):
    """--validate-config works with pyproject.toml [tool.*] sections."""
    conf_text = dedent("""\
        [build-system]
        requires = ["setuptools"]

        [tool.validate-cli]
        dummy_flag = true

        [tool.validate-cli.sub]
        int_param = 3
        """)
    conf_path = create_config("pyproject.toml", conf_text)

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option
    @validate_config_option
    def validate_cli(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    @validate_cli.command
    @option("--int-param", type=int, default=10)
    def sub(int_param):
        echo(f"int_parameter = {int_param!r}")

    result = invoke(validate_cli, "--validate-config", str(conf_path), color=False)
    assert result.exit_code == 0
    assert "is valid" in result.stderr


# --- _default_subcommands tests ---


@pytest.mark.parametrize(
    ("cli_subcmd", "expected", "unexpected"),
    [
        pytest.param(None, "backup ran", "sync ran", id="config-default"),
        pytest.param("sync", "sync ran", "backup ran", id="cli-override"),
    ],
)
def test_default_subcommand_selection(
    invoke, create_config, cli_subcmd, expected, unexpected
):
    """Config default is used when no subcommand given; CLI wins otherwise."""
    conf_text = dedent("""\
        [ds-cli]
        _default_subcommands = ["backup"]
        """)
    conf_path = create_config("ds-cli.toml", conf_text)

    @group
    def ds_cli():
        pass

    @ds_cli.command()
    def backup():
        echo("backup ran")

    @ds_cli.command()
    def sync():
        echo("sync ran")

    args = ["--config", str(conf_path)]
    if cli_subcmd is not None:
        args.append(cli_subcmd)

    result = invoke(ds_cli, *args, color=False)
    assert result.exit_code == 0
    assert expected in result.output
    assert unexpected not in result.output


def test_default_subcommand_chained(invoke, create_config):
    """chain=True group runs multiple config-listed subcommands in order."""
    conf_text = dedent("""\
        [chained-cli]
        _default_subcommands = ["backup", "sync"]
        """)
    conf_path = create_config("chained-cli.toml", conf_text)

    @group(chain=True)
    def chained_cli():
        pass

    @chained_cli.command()
    def backup():
        echo("backup ran")

    @chained_cli.command()
    def sync():
        echo("sync ran")

    result = invoke(chained_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 0
    assert "backup ran" in result.output
    assert "sync ran" in result.output
    # Verify order: backup before sync.
    assert result.output.index("backup ran") < result.output.index("sync ran")


@pytest.mark.parametrize(
    ("conf_value", "error_fragment"),
    [
        pytest.param('["backup", "sync"]', "at most 1", id="non-chained-multi"),
        pytest.param('["nonexistent"]', "not found", id="unknown-subcommand"),
        pytest.param('"not-a-list"', "must be a list", id="invalid-type"),
    ],
)
def test_default_subcommand_config_errors(
    invoke, create_config, conf_value, error_fragment
):
    """Bad _default_subcommands values produce clear errors."""
    conf_text = dedent(f"""\
        [err-cli]
        _default_subcommands = {conf_value}
        """)
    conf_path = create_config("err-cli.toml", conf_text)

    @group
    def err_cli():
        pass

    @err_cli.command()
    def backup():
        echo("backup ran")

    @err_cli.command()
    def sync():
        echo("sync ran")

    result = invoke(err_cli, "--config", str(conf_path), color=False)
    assert result.exit_code != 0
    combined = result.output + result.stderr
    assert error_fragment in combined


def test_default_subcommand_strict_mode_tolerance(invoke, create_config):
    """strict=True config with _default_subcommands doesn't raise."""
    conf_text = dedent("""\
        [strict-cli]
        _default_subcommands = ["backup"]
        """)
    conf_path = create_config("strict-cli.toml", conf_text)

    @click.group
    @config_option(strict=True)
    def strict_cli():
        pass

    @strict_cli.command()
    def backup():
        echo("backup ran")

    result = invoke(strict_cli, "--config", str(conf_path), "backup", color=False)
    assert result.exit_code == 0
    assert "backup ran" in result.output


def test_default_subcommand_validate_config_tolerance(invoke, create_config):
    """--validate-config with _default_subcommands reports valid."""
    conf_text = dedent("""\
        [validate-ds-cli]
        _default_subcommands = ["sub"]
        dummy_flag = true

        [validate-ds-cli.sub]
        int_param = 3
        """)
    conf_path = create_config("validate-ds-cli.toml", conf_text)

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option
    @validate_config_option
    def validate_ds_cli(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    @validate_ds_cli.command()
    @option("--int-param", type=int, default=10)
    def sub(int_param):
        echo(f"int_parameter = {int_param!r}")

    result = invoke(validate_ds_cli, "--validate-config", str(conf_path), color=False)
    assert result.exit_code == 0
    assert "is valid" in result.stderr


def test_default_subcommand_with_options(invoke, create_config):
    """Default subcommand receives its config-provided options."""
    conf_text = dedent("""\
        [opts-cli]
        _default_subcommands = ["backup"]

        [opts-cli.backup]
        path = "/home"
        """)
    conf_path = create_config("opts-cli.toml", conf_text)

    @group
    def opts_cli():
        pass

    @opts_cli.command()
    @option("--path", default="/tmp")
    def backup(path):
        echo(f"path={path}")

    result = invoke(opts_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 0
    assert "path=/home" in result.output


def test_default_subcommand_no_config(invoke):
    """Normal behavior when no config file is loaded."""

    @group
    def no_conf_cli():
        pass

    @no_conf_cli.command()
    def backup():
        echo("backup ran")

    # Without a subcommand and no config, the group should not run any subcommand.
    result = invoke(no_conf_cli, "--no-config", color=False)
    assert "backup ran" not in result.output


def test_default_subcommand_duplicates_warning(invoke, create_config):
    """Duplicate entries in _default_subcommands are deduplicated with a warning."""
    conf_text = dedent("""\
        [dup-cli]
        _default_subcommands = ["backup", "sync", "backup"]
        """)
    conf_path = create_config("dup-cli.toml", conf_text)

    @group(chain=True)
    def dup_cli():
        pass

    @dup_cli.command()
    def backup():
        echo("backup ran")

    @dup_cli.command()
    def sync():
        echo("sync ran")

    result = invoke(
        dup_cli, "--config", str(conf_path), "--verbosity", "WARNING", color=False
    )
    assert result.exit_code == 0
    assert "backup ran" in result.output
    assert "sync ran" in result.output
    # backup should only run once despite being listed twice.
    assert result.output.count("backup ran") == 1
    assert "Duplicate entries" in result.stderr


def test_default_subcommand_cli_override_debug_log(invoke, create_config):
    """Debug log emitted when CLI subcommands override config defaults."""
    conf_text = dedent("""\
        [log-cli]
        _default_subcommands = ["backup"]
        """)
    conf_path = create_config("log-cli.toml", conf_text)

    @group
    def log_cli():
        pass

    @log_cli.command()
    def backup():
        echo("backup ran")

    @log_cli.command()
    def sync():
        echo("sync ran")

    result = invoke(
        log_cli,
        "--config",
        str(conf_path),
        "--verbosity",
        "DEBUG",
        "sync",
        color=False,
    )
    assert result.exit_code == 0
    assert "sync ran" in result.output
    assert "backup ran" not in result.output
    assert "ignoring _default_subcommands" in result.stderr.lower()


# --- _prepend_subcommands tests ---


@pytest.mark.parametrize(
    ("cli_subcmd", "expected", "unexpected"),
    [
        pytest.param("sync", "sync ran", "", id="with-cli-arg"),
        pytest.param(None, "", "sync ran", id="no-cli-args"),
    ],
)
def test_prepend_subcommand_selection(
    invoke, create_config, cli_subcmd, expected, unexpected
):
    """Prepend fires regardless of whether a CLI subcommand is given."""
    conf_text = dedent("""\
        [prepend-cli]
        _prepend_subcommands = ["debug"]
        """)
    conf_path = create_config("prepend-cli.toml", conf_text)

    @group(chain=True)
    def prepend_cli():
        pass

    @prepend_cli.command()
    def debug():
        echo("debug ran")

    @prepend_cli.command()
    def sync():
        echo("sync ran")

    args = ["--config", str(conf_path)]
    if cli_subcmd is not None:
        args.append(cli_subcmd)

    result = invoke(prepend_cli, *args, color=False)
    assert result.exit_code == 0
    assert "debug ran" in result.output
    if expected:
        assert expected in result.output
        # debug must come before the CLI subcommand.
        assert result.output.index("debug ran") < result.output.index(expected)
    if unexpected:
        assert unexpected not in result.output


@pytest.mark.parametrize(
    ("cli_subcmd", "expect_backup"),
    [
        pytest.param(None, False, id="no-cli-defaults-apply"),
        pytest.param("sync", False, id="cli-overrides-defaults"),
    ],
)
def test_prepend_subcommand_with_defaults(
    invoke, create_config, cli_subcmd, expect_backup
):
    """Prepend always applies; defaults only fire when no CLI subcommand given."""
    conf_text = dedent("""\
        [pd-cli]
        _default_subcommands = ["sync"]
        _prepend_subcommands = ["debug"]
        """)
    conf_path = create_config("pd-cli.toml", conf_text)

    @group(chain=True)
    def pd_cli():
        pass

    @pd_cli.command()
    def debug():
        echo("debug ran")

    @pd_cli.command()
    def backup():
        echo("backup ran")

    @pd_cli.command()
    def sync():
        echo("sync ran")

    args = ["--config", str(conf_path)]
    if cli_subcmd is not None:
        args.append(cli_subcmd)

    result = invoke(pd_cli, *args, color=False)
    assert result.exit_code == 0
    assert "debug ran" in result.output
    assert "sync ran" in result.output
    assert result.output.index("debug ran") < result.output.index("sync ran")
    if expect_backup:
        assert "backup ran" in result.output
    else:
        assert "backup ran" not in result.output


def test_prepend_subcommand_non_chained_error(invoke, create_config):
    """Error on non-chained group."""
    conf_text = dedent("""\
        [nc-cli]
        _prepend_subcommands = ["debug"]
        """)
    conf_path = create_config("nc-cli.toml", conf_text)

    @group
    def nc_cli():
        pass

    @nc_cli.command()
    def debug():
        echo("debug ran")

    @nc_cli.command()
    def sync():
        echo("sync ran")

    result = invoke(nc_cli, "--config", str(conf_path), "sync", color=False)
    assert result.exit_code != 0
    combined = result.output + result.stderr
    assert "chain=True" in combined


@pytest.mark.parametrize(
    ("conf_value", "error_fragment"),
    [
        pytest.param('"not-a-list"', "must be a list", id="invalid-type"),
        pytest.param('["nonexistent"]', "not found", id="unknown-subcommand"),
    ],
)
def test_prepend_subcommand_config_errors(
    invoke, create_config, conf_value, error_fragment
):
    """Bad _prepend_subcommands values produce clear errors."""
    conf_text = dedent(f"""\
        [perr-cli]
        _prepend_subcommands = {conf_value}
        """)
    conf_path = create_config("perr-cli.toml", conf_text)

    @group(chain=True)
    def perr_cli():
        pass

    @perr_cli.command()
    def backup():
        echo("backup ran")

    result = invoke(perr_cli, "--config", str(conf_path), color=False)
    assert result.exit_code != 0
    combined = result.output + result.stderr
    assert error_fragment in combined


def test_prepend_subcommand_strict_mode_tolerance(invoke, create_config):
    """strict=True config with _prepend_subcommands doesn't raise."""
    conf_text = dedent("""\
        [strict-p-cli]
        _prepend_subcommands = ["backup"]
        """)
    conf_path = create_config("strict-p-cli.toml", conf_text)

    @click.group(chain=True)
    @config_option(strict=True)
    def strict_p_cli():
        pass

    @strict_p_cli.command()
    def backup():
        echo("backup ran")

    result = invoke(strict_p_cli, "--config", str(conf_path), "backup", color=False)
    assert result.exit_code == 0
    assert "backup ran" in result.output


def test_prepend_subcommand_validate_config_tolerance(invoke, create_config):
    """--validate-config with _prepend_subcommands reports valid."""
    conf_text = dedent("""\
        [validate-ps-cli]
        _prepend_subcommands = ["sub"]
        dummy_flag = true

        [validate-ps-cli.sub]
        int_param = 3
        """)
    conf_path = create_config("validate-ps-cli.toml", conf_text)

    @click.group(chain=True)
    @option("--dummy-flag/--no-flag")
    @config_option
    @validate_config_option
    def validate_ps_cli(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    @validate_ps_cli.command()
    @option("--int-param", type=int, default=10)
    def sub(int_param):
        echo(f"int_parameter = {int_param!r}")

    result = invoke(validate_ps_cli, "--validate-config", str(conf_path), color=False)
    assert result.exit_code == 0
    assert "is valid" in result.stderr


def test_prepend_subcommand_duplicates_warning(invoke, create_config):
    """Duplicate entries in _prepend_subcommands are deduplicated with a warning."""
    conf_text = dedent("""\
        [pdup-cli]
        _prepend_subcommands = ["debug", "debug"]
        """)
    conf_path = create_config("pdup-cli.toml", conf_text)

    @group(chain=True)
    def pdup_cli():
        pass

    @pdup_cli.command()
    def debug():
        echo("debug ran")

    @pdup_cli.command()
    def sync():
        echo("sync ran")

    result = invoke(
        pdup_cli,
        "--config",
        str(conf_path),
        "--verbosity",
        "WARNING",
        "sync",
        color=False,
    )
    assert result.exit_code == 0
    assert "debug ran" in result.output
    assert "sync ran" in result.output
    # debug should only run once despite being listed twice.
    assert result.output.count("debug ran") == 1
    assert "Duplicate entries" in result.stderr


def test_prepend_subcommand_info_log(invoke, create_config):
    """INFO log emitted when _prepend_subcommands are injected."""
    conf_text = dedent("""\
        [plog-cli]
        _prepend_subcommands = ["debug"]
        """)
    conf_path = create_config("plog-cli.toml", conf_text)

    @group(chain=True)
    def plog_cli():
        pass

    @plog_cli.command()
    def debug():
        echo("debug ran")

    @plog_cli.command()
    def sync():
        echo("sync ran")

    result = invoke(
        plog_cli,
        "--config",
        str(conf_path),
        "--verbosity",
        "INFO",
        "sync",
        color=False,
    )
    assert result.exit_code == 0
    assert "debug ran" in result.output
    assert "sync ran" in result.output
    assert "prepending _prepend_subcommands" in result.stderr.lower()


def test_prepend_subcommand_multiple(invoke, create_config):
    """Multiple prepend subcommands run in order."""
    conf_text = dedent("""\
        [pmulti-cli]
        _prepend_subcommands = ["init", "debug"]
        """)
    conf_path = create_config("pmulti-cli.toml", conf_text)

    @group(chain=True)
    def pmulti_cli():
        pass

    @pmulti_cli.command()
    def init():
        echo("init ran")

    @pmulti_cli.command()
    def debug():
        echo("debug ran")

    @pmulti_cli.command()
    def sync():
        echo("sync ran")

    result = invoke(pmulti_cli, "--config", str(conf_path), "sync", color=False)
    assert result.exit_code == 0
    assert "init ran" in result.output
    assert "debug ran" in result.output
    assert "sync ran" in result.output
    # Verify order: init, debug, sync.
    assert result.output.index("init ran") < result.output.index("debug ran")
    assert result.output.index("debug ran") < result.output.index("sync ran")


# --- _check_pattern_sanity tests ---


def test_sanity_broad_glob_narrow_format(caplog):
    """Broad glob + all-literal format patterns triggers a debug log."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            default="~/*",
            file_format_patterns={ConfigFormat.YAML: ".commandrc"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.DOTGLOB
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "Broad search pattern" in caplog.text
    assert "literal format patterns" in caplog.text


def test_sanity_broad_glob_wildcard_format(caplog):
    """Broad glob + wildcard format patterns does NOT trigger the warning."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            default="~/*",
            file_format_patterns={ConfigFormat.YAML: "*.yaml"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.DOTGLOB
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "Broad search pattern" not in caplog.text


def test_sanity_disjoint_patterns(caplog):
    """Literal default not matching any format pattern triggers a debug log."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            default="/etc/myapp/config.conf",
            file_format_patterns={ConfigFormat.TOML: "*.toml"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.DOTGLOB
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "does not match any format pattern" in caplog.text


def test_sanity_disjoint_matching_literal(caplog):
    """Literal default matching a format pattern does NOT trigger the warning."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            default="/etc/myapp/config.toml",
            file_format_patterns={ConfigFormat.TOML: "*.toml"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.DOTGLOB
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "does not match any format pattern" not in caplog.text


def test_sanity_format_extension_mismatch(caplog):
    """Format pattern extension mismatching its format triggers a debug log."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            file_format_patterns={ConfigFormat.YAML: "*.toml"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.DOTGLOB
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "canonically associated" in caplog.text


def test_sanity_format_extension_correct(caplog):
    """Correctly-matched format extension does NOT trigger the warning."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            file_format_patterns={ConfigFormat.YAML: "*.yaml"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.DOTGLOB
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "canonically associated" not in caplog.text


def test_sanity_dotfile_without_dotglob(caplog):
    """Dotfile in default without DOTGLOB triggers a debug log."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            default="~/.myapprc",
            file_format_patterns={ConfigFormat.YAML: "*.yaml"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "DOTGLOB is not set" in caplog.text


def test_sanity_dotfile_format_without_dotglob(caplog):
    """Dotfile in format patterns without DOTGLOB triggers a debug log."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            default="~/configs/*",
            file_format_patterns={ConfigFormat.YAML: ".myapprc"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "DOTGLOB is not set" in caplog.text


def test_sanity_dotfile_with_dotglob(caplog):
    """Dotfile with DOTGLOB does NOT trigger the warning."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            default="~/.myapprc",
            file_format_patterns={ConfigFormat.YAML: "*.yaml"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.DOTGLOB
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "DOTGLOB is not set" not in caplog.text


def test_sanity_no_explicit_default(caplog):
    """Without an explicit string default, checks 1/2/4 are skipped."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            file_format_patterns={ConfigFormat.YAML: "*.yaml"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.DOTGLOB
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "Broad search pattern" not in caplog.text
    assert "does not match" not in caplog.text


def test_sanity_format_mismatch_without_explicit_default(caplog):
    """Check 3 (format mismatch) runs even without explicit default."""
    from wcmatch import glob

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(
            file_format_patterns={ConfigFormat.YAML: "*.toml"},
            search_pattern_flags=(
                glob.GLOBSTAR
                | glob.FOLLOW
                | glob.DOTGLOB
                | glob.BRACE
                | glob.SPLIT
                | glob.GLOBTILDE
                | glob.NODIR
            ),
        )

    assert "canonically associated" in caplog.text
