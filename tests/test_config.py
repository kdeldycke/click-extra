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

import ast
import json
import logging
import os
import plistlib
import re
import subprocess
import sys
import unittest.mock
from pathlib import Path
from textwrap import dedent

import click
import pytest
from boltons.iterutils import flatten, unique
from boltons.pathutils import shrinkuser
from extra_platforms import (
    is_macos,
    is_unix_not_macos,
    is_windows,
)
from extra_platforms.pytest import unless_unix_not_macos
from wcmatch import fnmatch, glob

from click_extra import (
    NO_CONFIG,
    VCS,
    ConfigFormat,
    ConfigOption,
    LazyGroup,
    command,
    config_option,
    echo,
    export_config_option,
    format_from_mime,
    format_from_path,
    get_app_dir,
    group,
    no_config_option,
    option,
    pass_context,
    search_params,
    validate_config_option,
)
from click_extra.config import SQLITE_CONFIG_TABLE
from click_extra.config.formats import SQLITE_SUPPORT, disabled_format_message
from click_extra.config.schema import (
    _expand_dotted_keys,
)
from click_extra.pytest import (
    default_debug_uncolored_log_end,
    default_debug_uncolored_log_start,
    default_debug_uncolored_logging,
    default_debug_uncolored_version_details,
)

DOCS_CONFIG_PAGE = Path(__file__).parent.parent / "docs" / "config-discovery.md"
"""The documentation page transcribing part of ``ConfigFormat``."""

# The complete set of glob search flags ``ConfigOption`` enforces by default.
FULL_SEARCH_FLAGS = (
    glob.GLOBSTAR
    | glob.FOLLOW
    | glob.DOTGLOB
    | glob.BRACE
    | glob.SPLIT
    | glob.GLOBTILDE
    | glob.NODIR
)
"""All search flags ``ConfigOption`` forces on, used as the baseline in tests."""

NO_DOTGLOB_FLAGS = FULL_SEARCH_FLAGS & ~glob.DOTGLOB
"""``FULL_SEARCH_FLAGS`` minus ``DOTGLOB``, to exercise the dotfile warnings."""

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

PLIST_FILE, PLIST_DATA = (
    dedent(
        """\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
            "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <!-- Comment -->
        <dict>
            <key>top_level_param</key>
            <string>to_ignore</string>

            <key>config-cli1</key>
            <dict>
                <key>verbosity</key>
                <string>DEBUG</string>
                <key>blahblah</key>
                <integer>234</integer>
                <key>dummy_flag</key>
                <true/>
                <key>my_list</key>
                <array>
                    <string>pip</string>
                    <string>npm</string>
                    <string>gem</string>
                </array>

                <key>default</key>
                <dict>
                    <key>int_param</key>
                    <integer>3</integer>
                    <key>random_stuff</key>
                    <string>will be ignored</string>
                </dict>
            </dict>

            <key>garbage</key>
            <dict/>
        </dict>
        </plist>
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

ARGFILE_FILE, ARGFILE_DATA = (
    dedent(
        """\
        # Comment

        --dummy-flag
        --my-list pip
        --my-list npm --my-list gem
        --verbosity DEBUG
        """,
    ),
    {
        "config-cli1": {
            "dummy_flag": True,
            "my_list": ["pip", "npm", "gem"],
            "verbosity": "DEBUG",
        },
    },
)

SQLITE_DATA = {
    "config-cli1": {
        "dummy_flag": True,
        "my_list": ["pip", "npm", "gem"],
        "default": {
            "int_param": 3,
            "random_stuff": "will be ignored",
        },
    },
}
"""The shared reference configuration, as `SQLITE_CONFIG_TABLE` rows.

Keys are dotted parameter paths, values are JSON-encoded. This mirrors
`TOML_DATA`, minus the verbosity bump and the sections the other formats
use to exercise their own quirks."""


def flatten_sqlite_keys(data: dict, prefix: str = "") -> dict:
    """Flatten a nested mapping into dotted keys, the SQLite config layout."""
    flat: dict = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten_sqlite_keys(value, full_key))
        else:
            flat[full_key] = value
    return flat


def make_sqlite_config(
    path: Path,
    data: dict | None = None,
    *,
    create_table: bool = True,
) -> Path:
    """Write a nested mapping into a SQLite configuration database.

    Skips the calling test on a Python whose SQLite bindings are missing, the
    same interpreter on which `ConfigFormat.SQLITE` reports itself disabled.
    """
    sqlite3 = pytest.importorskip(
        "sqlite3", reason="SQLITE is gated on the standard library's sqlite3"
    )
    connection = sqlite3.connect(path)
    if create_table:
        connection.execute(
            f"CREATE TABLE {SQLITE_CONFIG_TABLE} (key TEXT PRIMARY KEY, value TEXT)"
        )
    if data:
        for key, value in flatten_sqlite_keys(data).items():
            connection.execute(
                f"INSERT INTO {SQLITE_CONFIG_TABLE} VALUES (?, ?)",
                (key, json.dumps(value)),
            )
    connection.commit()
    connection.close()
    return path


all_config_formats = pytest.mark.parametrize(
    ("conf_name, conf_text, conf_data"),
    [
        pytest.param(f"configuration.{ext}", content, data, id=ext)
        for ext, content, data in (
            ("toml", TOML_FILE, TOML_DATA),
            ("yaml", YAML_FILE, YAML_DATA),
            ("json", JSON_FILE, JSON_DATA),
            ("ini", INI_FILE, INI_DATA),
            ("xml", XML_FILE, XML_DATA),
            ("plist", PLIST_FILE, PLIST_DATA),
        )
    ],
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

    # Cloup wraps the --config default at unpredictable columns, sometimes mid-token
    # (e.g. "~/config-c" then "li1"), so we cannot guess the wrap points with a
    # regex. De-wrap the option's help block by dropping all whitespace, then match
    # the folder against it.
    help_screen = re.sub(r"\s+", "", result.stdout.split("--config LOCATION")[1])

    # Mirror the CLI's own path display: default_pattern() resolves the app dir
    # before shrinkuser() collapses the home prefix to "~". The resolve() matters
    # on Windows, where the pinned HOME is an unresolved temp path: resolving it
    # to its canonical form defeats shrinkuser (the prefix no longer matches
    # expanduser), so the CLI prints the full path and the test must expect it.
    default_path = re.sub(
        r"\s+", "", str(shrinkuser(Path(get_app_dir("config-cli1")).resolve()))
    )
    assert f"default:{default_path}{os.path.sep}]" in help_screen

    # An inherited format set is collapsed away, so the folder is the whole default.
    # See ConfigOption.collapse_default().
    fp = ",".join(unique(flatten(f.patterns for f in ConfigFormat if f.enabled)))
    assert f"{{{fp}}}" not in help_screen

    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("file_format_patterns", "expected_pattern"),
    [
        pytest.param(ConfigFormat.TOML, "*.toml", id="single_format"),
        pytest.param(
            {ConfigFormat.TOML: ["*.toml", "my_app.conf"]},
            "{*.toml,my_app.conf}",
            id="custom_patterns",
        ),
    ],
)
def test_conf_chosen_formats_displayed(invoke, file_format_patterns, expected_pattern):
    """A format set chosen by the developer is displayed in full.

    Only an inherited set collapses to its folder, so the help screen keeps showing
    the effect of `file_format_patterns`, which is what `docs/config-discovery.md`
    demonstrates.
    """

    @click.command
    @config_option(file_format_patterns=file_format_patterns)
    def config_cli1():
        pass

    result = invoke(config_cli1, "--help", color=False)

    help_screen = re.sub(r"\s+", "", result.stdout.split("--config LOCATION")[1])
    assert f"{expected_pattern}]" in help_screen

    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("kwargs", "shows_patterns"),
    [
        pytest.param({"show_file_patterns": True}, True, id="inherited_forced_on"),
        pytest.param({"show_file_patterns": False}, False, id="inherited_forced_off"),
        pytest.param(
            {"file_format_patterns": ConfigFormat.TOML, "show_file_patterns": False},
            False,
            id="chosen_forced_off",
        ),
    ],
)
def test_conf_show_file_patterns(invoke, kwargs, shows_patterns):
    """`show_file_patterns` overrides the display in both directions."""

    @click.command
    @config_option(**kwargs)
    def config_cli1():
        pass

    result = invoke(config_cli1, "--help", color=False)

    config_opt = search_params(config_cli1.params, ConfigOption)
    assert isinstance(config_opt, ConfigOption)
    fp = config_opt.file_pattern
    suffix = f"{{{fp}}}" if "," in fp else fp
    help_screen = re.sub(r"\s+", "", result.stdout.split("--config LOCATION")[1])
    assert (f"{suffix}]" in help_screen) is shows_patterns

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
        for line in result.stdout.split("--config LOCATION")[1].splitlines()
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
        # Unknown keys surface as a clean critical-level log and exit 1, before
        # the subcommand runs, not as a raw ValueError traceback.
        assert result.exit_code == 1
        assert not result.stdout
        assert (
            "Configuration validation error: "
            "Unknown configuration key 'random_stuff'." in result.stderr
        )
    else:
        assert result.exit_code == 0
        assert "dummy_flag    is True" in result.stdout
        assert "int_parameter is 3" in result.stdout

    assert f"Load configuration matching {conf_path}\n" in result.stderr


def test_kebab_case_keys(invoke, create_config):
    """Kebab-case config keys reach the snake_case-named CLI parameters."""

    @command
    @option("--dummy-flag/--no-flag")
    @option("--int-param", type=int, default=10)
    def kebab_cli(dummy_flag, int_param):
        echo(f"dummy_flag = {dummy_flag!r}")
        echo(f"int_param = {int_param!r}")

    conf_path = create_config(
        "kebab.toml",
        dedent("""\
            [kebab-cli]
            dummy-flag = true
            int-param = 3
        """),
    )
    result = invoke(kebab_cli, "--config", str(conf_path), color=False)

    assert result.exit_code == 0
    assert "dummy_flag = True" in result.stdout
    assert "int_param = 3" in result.stdout


def test_kebab_case_spelling_collision(invoke, create_config):
    """Both spellings of the same key: last one wins, a warning names both."""

    @command
    @option("--int-param", type=int, default=10)
    def collision_cli(int_param):
        echo(f"int_param = {int_param!r}")

    conf_path = create_config(
        "collision.toml",
        dedent("""\
            [collision-cli]
            int_param = 3
            int-param = 7
        """),
    )
    result = invoke(collision_cli, "--config", str(conf_path), color=False)

    assert result.exit_code == 0
    assert "int_param = 7" in result.stdout
    assert "both resolve to 'int_param'. Last value wins." in result.stderr


def test_strict_conf_ignores_foreign_sections(invoke, create_config):
    """Other tools' sections in a shared config file do not trip strict mode."""

    @click.command
    @config_option(strict=True)
    @option("--int-param", type=int, default=10)
    def scoped_cli(int_param):
        echo(f"int_param = {int_param!r}")

    conf_path = create_config(
        "shared.toml",
        dedent("""\
            [scoped-cli]
            int_param = 3

            [other-tool]
            unknown_stuff = true
        """),
    )
    result = invoke(scoped_cli, "--config", str(conf_path), color=False)

    assert result.exit_code == 0
    assert "int_param = 3" in result.stdout


def test_command_forwards_config_strict(invoke, create_config):
    """@command(config_strict=True) activates strict mode on the default option."""

    @command(config_strict=True)
    @option("--int-param", type=int, default=10)
    def strict_forward_cli(int_param):
        echo(f"int_param = {int_param!r}")

    conf_path = create_config(
        "typo.toml",
        dedent("""\
            [strict-forward-cli]
            int_pram = 3
        """),
    )
    result = invoke(strict_forward_cli, "--config", str(conf_path), color=False)

    assert result.exit_code == 1
    assert (
        "Configuration validation error: "
        "Unknown configuration key 'int_pram'." in result.stderr
    )


def test_command_excluded_params_additive(invoke, create_config):
    """@command(excluded_params=...) extends the default blocklist.

    The forwarded exclusion applies on top of the built-in ones, and a blocked
    parameter found in a config file is reported as blocked, not unknown.
    """

    @command(
        config_strict=True,
        excluded_params=["excluded-cli.secret"],
    )
    @option("--secret")
    @option("--int-param", type=int, default=10)
    def excluded_cli(secret, int_param):
        echo(f"int_param = {int_param!r}")

    config_opt = search_params(excluded_cli.params, ConfigOption)
    assert isinstance(config_opt, ConfigOption)
    assert config_opt.extra_excluded_params == frozenset({"excluded-cli.secret"})

    # The blocked parameter is refused with a dedicated message.
    conf_path = create_config(
        "blocked.toml",
        dedent("""\
            [excluded-cli]
            secret = "hunter2"
        """),
    )
    result = invoke(excluded_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 1
    assert (
        "Configuration validation error: Configuration key 'secret' "
        "is not allowed in configuration files." in result.stderr
    )

    # The default exclusions survive the addition: a config key targeting
    # --version is still blocked.
    conf_path = create_config(
        "version.toml",
        dedent("""\
            [excluded-cli]
            version = true
        """),
    )
    result = invoke(excluded_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 1
    assert (
        "Configuration validation error: Configuration key 'version' "
        "is not allowed in configuration files." in result.stderr
    )


def test_export_config_includes_unset_params(invoke):
    """Parameters without a default are exported instead of silently dropped.

    TOML has no null type so unset parameters are commented out; multi-value
    parameters read as empty lists; JSON renders unset parameters as null.
    """

    @command
    @option("--tag", multiple=True)
    @option("--regexp")
    def unset_cli(tag, regexp):
        echo("run")

    result = invoke(unset_cli, "--export-config", "toml", color=False)
    assert result.exit_code == 0
    assert "[unset-cli]" in result.stdout
    assert "tag = []" in result.stdout
    assert "# regexp =" in result.stdout

    result = invoke(unset_cli, "--export-config", "json", color=False)
    assert result.exit_code == 0
    assert '"tag": []' in result.stdout
    assert '"regexp": null' in result.stdout

    result = invoke(unset_cli, "--export-config", "plist", color=False)
    assert result.exit_code == 0
    assert "<key>tag</key>" in result.stdout
    # plist has no null type: the unset parameter is dropped from the export.
    assert "regexp" not in result.stdout


def test_export_config_kebab_case_keys(invoke, tmp_path):
    """Exported keys use the kebab-case spelling, the canonical form for files.

    Either spelling loads back to the same parameter, so the kebab-cased
    export still round-trips through --config.
    """

    @command
    @option("--dry-run", is_flag=True)
    @option("--int-param", type=int, default=10)
    def kebab_dump_cli(dry_run, int_param):
        echo(f"int_param = {int_param!r}")

    result = invoke(kebab_dump_cli, "--export-config", "toml", color=False)
    assert result.exit_code == 0
    assert "dry-run = false" in result.stdout
    assert "int-param = 10" in result.stdout
    assert "dry_run" not in result.stdout
    assert "int_param" not in result.stdout

    conf_path = tmp_path / "kebab_dump.toml"
    conf_path.write_text(result.stdout, encoding="utf-8")
    reloaded = invoke(kebab_dump_cli, "--config", str(conf_path), color=False)
    assert reloaded.exit_code == 0
    assert "int_param = 10" in reloaded.stdout


def test_introspection_flags_load_config_first(invoke, create_config):
    """--params and --export-config reflect the config file regardless of the
    order in which Click processes the eager options.

    Click processes eager parameters given on the command line ahead of eager
    parameters left at their defaults, so these flags used to render before
    the configuration file was discovered and loaded.
    """

    @command
    @option("--int-param", type=int, default=10)
    def ordering_cli(int_param):
        echo(f"int_param = {int_param!r}")

    conf_path = create_config(
        "ordering.toml",
        dedent("""\
            [ordering-cli]
            int_param = 42
        """),
    )

    # The --params flag comes first on the command line, so it is processed
    # before --config: the table must still show the config-sourced value.
    result = invoke(
        ordering_cli,
        "--params",
        "--table-format",
        "csv",
        "--config",
        str(conf_path),
        color=False,
    )
    assert result.exit_code == 0
    param_row = [
        line
        for line in result.stdout.splitlines()
        if line.startswith("ordering-cli.int_param,")
    ]
    assert len(param_row) == 1
    assert ",42,DEFAULT_MAP" in param_row[0]

    # Same ordering trap for --export-config.
    result = invoke(
        ordering_cli,
        "--export-config",
        "toml",
        "--config",
        str(conf_path),
        color=False,
    )
    assert result.exit_code == 0
    assert "int-param = 42" in result.stdout


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
            # No configuration values match the CLI's parameter structure, so the
            # ChainMap layered onto the existing default_map holds two empty maps.
            "default_map=ChainMap({}, {})\n"
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


@pytest.mark.parametrize(
    ("media_type", "expected"),
    (
        # Media types each format is served as.
        ("application/toml", ConfigFormat.TOML),
        ("text/x-toml", ConfigFormat.TOML),
        ("application/yaml", ConfigFormat.YAML),
        ("text/yaml", ConfigFormat.YAML),
        ("application/x-yaml", ConfigFormat.YAML),
        ("text/x-yaml", ConfigFormat.YAML),
        ("application/json", ConfigFormat.JSON),
        ("text/json", ConfigFormat.JSON),
        ("application/json5", ConfigFormat.JSON5),
        ("application/jsonc", ConfigFormat.JSONC),
        ("application/hjson", ConfigFormat.HJSON),
        ("application/xml", ConfigFormat.XML),
        ("text/xml", ConfigFormat.XML),
        ("application/x-plist", ConfigFormat.PLIST),
        ("application/vnd.sqlite3", ConfigFormat.SQLITE),
        ("application/x-sqlite3", ConfigFormat.SQLITE),
        # Parameters are stripped and case is ignored.
        ("application/toml; charset=utf-8", ConfigFormat.TOML),
        ("  Application/TOML  ", ConfigFormat.TOML),
        # RFC 6839 structured syntax suffixes.
        ("application/vnd.acme.settings+json", ConfigFormat.JSON),
        ("application/atom+xml", ConfigFormat.XML),
        # Types no format claims.
        ("text/plain", None),
        ("application/octet-stream", None),
        ("application/unknown", None),
        ("", None),
        ("   ", None),
    ),
)
def test_format_from_mime(media_type, expected):
    assert format_from_mime(media_type) == expected


def test_format_from_mime_restricted_to_candidates():
    """`formats` narrows the resolution, like `format_from_path` does."""
    assert format_from_mime("application/json") is ConfigFormat.JSON
    assert format_from_mime("application/json", [ConfigFormat.TOML]) is None


def test_jwcc_resolves_to_the_json5_parser(tmp_path):
    """A `*.jwcc` file is read by the `JSON5` parser, which is a superset of it."""
    assert format_from_path(tmp_path / "settings.jwcc") is ConfigFormat.JSON5


def test_jwcc_conf(invoke, simple_config_cli, tmp_path):
    """A JWCC document loads: JSON plus comments and trailing commas."""
    pytest.importorskip("json5", reason="JWCC is parsed by the json5 extra")

    conf_file = tmp_path / "configuration.jwcc"
    conf_file.write_text(
        dedent(
            """
            {
                // A comment, which plain JSON refuses.
                "config-cli1": {
                    "dummy_flag": true,
                    "my_list": ["pip", "npm", "gem",],
                    "default": {"int_param": 3,},
                },
            }
            """,
        ),
        encoding="utf-8",
    )

    result = invoke(
        simple_config_cli, "--config", str(conf_file), "default", color=False
    )
    assert result.exit_code == 0
    assert result.stdout == (
        "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
    )


def test_conf_key_reaches_a_case_preserving_param_name(invoke, create_config):
    """A parameter whose name kept its case is still addressed by that case.

    Click takes an identifier declaration verbatim, so this parameter is named
    `Explicit_Name`. No fold produces that spelling, so the template has to
    stay the authority on it.
    """

    @click.command
    @config_option
    @option("--explicit", "Explicit_Name", default="untouched")
    def case_cli(**kwargs):
        echo(f"value = {kwargs['Explicit_Name']!r}")

    for spelling in ("Explicit_Name", "Explicit-Name"):
        conf_path = create_config(
            "case.toml", f'[case-cli]\n"{spelling}" = "from-conf"\n'
        )
        result = invoke(case_cli, "--config", str(conf_path), color=False)
        assert result.exit_code == 0
        assert result.stdout == "value = 'from-conf'\n", spelling


@pytest.mark.parametrize(
    "spelling",
    ("foo_bar", "foo-bar", "Foo-Bar", "FOO_BAR", "foo-BAR"),
)
def test_conf_key_case_folds_onto_the_param_name(invoke, create_config, spelling):
    """Every spelling Click could have derived `foo_bar` from reaches it."""

    @click.command
    @config_option
    @option("--Foo-Bar", default="untouched")
    def fold_cli(foo_bar):
        echo(f"value = {foo_bar!r}")

    conf_path = create_config("fold.toml", f'[fold-cli]\n"{spelling}" = "from-conf"\n')
    result = invoke(fold_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 0
    assert result.stdout == "value = 'from-conf'\n"


def test_conf_key_folding_onto_two_params_is_skipped(invoke, create_config, caplog):
    """A key folding onto two parameter names picks neither, and warns.

    Click allows `foo_bar` and `Foo_Bar` on one command, and nothing in the
    folded spelling says which was meant.
    """

    @click.command
    @config_option
    @option("--foo-bar", default="untouched")
    @option("--other", "Foo_Bar", default="untouched")
    def ambiguous_cli(**kwargs):
        echo(f"values = {sorted(kwargs.items())!r}")

    conf_path = create_config(
        "ambiguous.toml", '[ambiguous-cli]\n"FOO_BAR" = "from-conf"\n'
    )
    with caplog.at_level(logging.WARNING, logger="click_extra"):
        result = invoke(ambiguous_cli, "--config", str(conf_path), color=False)

    assert result.exit_code == 0
    assert "'from-conf'" not in result.stdout
    assert "matches" in caplog.text
    assert "no spelling tells them apart" in caplog.text


def test_strict_conf_accepts_a_folded_key(invoke, create_config):
    """Strict mode no longer rejects a spelling the fold resolves."""

    @click.command
    @config_option(strict=True)
    @option("--Foo-Bar", default="untouched")
    def strict_fold_cli(foo_bar):
        echo(f"value = {foo_bar!r}")

    conf_path = create_config("strict.toml", '[strict-fold-cli]\n"Foo-Bar" = "ok"\n')
    result = invoke(strict_fold_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 0
    assert result.stdout == "value = 'ok'\n"


def test_mime_types_are_unambiguous():
    """No media type is claimed by two formats.

    A duplicate would leave `format_from_mime` resolving on `ConfigFormat`
    declaration order alone, silently handing the media type to whichever
    format happens to be declared first.
    """
    owners: dict[str, str] = {}
    for fmt in ConfigFormat:
        for media_type in fmt.mime_types:
            assert media_type == media_type.strip().lower(), (
                f"{fmt.name} declares {media_type!r}, which is not normalized."
            )
            assert media_type.count("/") == 1, (
                f"{fmt.name} declares {media_type!r}, which is not a type/subtype."
            )
            assert media_type not in owners, (
                f"{media_type!r} is claimed by both {owners.get(media_type)} "
                f"and {fmt.name}."
            )
            owners[media_type] = fmt.name


def test_docs_media_types_table_matches_formats():
    """The media-type table in the docs is `ConfigFormat.mime_types`, transcribed.

    A format gaining or losing a media type otherwise leaves the table stale,
    and that table is the only place a user reads the mapping from.
    """
    page = DOCS_CONFIG_PAGE.read_text(encoding="utf-8")
    table = page.split("### Typing a download", 1)[1].split("```{warning}", 1)[0]

    # Each row links its format to the section documenting it, on a sibling
    # page, whose anchor is the member name kebab-cased.
    documented = {}
    for row in table.splitlines():
        match = re.match(
            r"\|\s*\[`[^`]+`\]\((?:[\w-]+\.md)?#([\w-]+)\)\s*\|([^|]+)\|", row
        )
        if not match:
            continue
        anchor, cell = match.groups()
        for media_type in re.findall(r"`([^`]+)`", cell):
            documented[media_type] = anchor

    declared = {
        media_type: fmt.name.lower().replace("_", "-")
        for fmt in ConfigFormat
        for media_type in fmt.mime_types
    }
    assert documented == declared


@pytest.mark.parametrize(
    ("media_type", "conf_text"),
    (
        pytest.param("application/toml", TOML_FILE, id="toml"),
        pytest.param("application/yaml", YAML_FILE, id="yaml"),
        pytest.param("application/json", JSON_FILE, id="json"),
        pytest.param("application/xml", XML_FILE, id="xml"),
        pytest.param("application/x-plist", PLIST_FILE, id="plist"),
        pytest.param(
            "application/vnd.acme.settings+json", JSON_FILE, id="vendor-suffix"
        ),
    ),
)
def test_remote_conf_typed_by_content_type(
    invoke,
    simple_config_cli,
    httpserver,
    media_type,
    conf_text,
):
    """An extension-less URL is typed by the media type its server advertises."""
    httpserver.expect_request("/settings").respond_with_data(
        conf_text, content_type=media_type
    )

    result = invoke(
        simple_config_cli,
        "--config",
        httpserver.url_for("/settings"),
        "default",
        color=False,
    )
    assert result.exit_code == 0
    assert result.stdout == (
        "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
    )


@pytest.mark.parametrize(
    "media_type",
    ("text/plain", "application/octet-stream", "application/json"),
)
def test_remote_conf_falls_back_to_the_url_name(
    invoke,
    simple_config_cli,
    httpserver,
    media_type,
):
    """A generic or plain wrong media type still leaves the URL name to match on."""
    httpserver.expect_request("/configuration.toml").respond_with_data(
        TOML_FILE, content_type=media_type
    )

    result = invoke(
        simple_config_cli,
        "--config",
        httpserver.url_for("/configuration.toml"),
        "default",
        color=False,
    )
    assert result.exit_code == 0
    assert result.stdout == (
        "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 3\n"
    )


@pytest.mark.parametrize(
    ("file_format_patterns", "exit_code", "stdout"),
    (
        pytest.param({}, 0, "dummy_flag = True\n", id="all-formats"),
        pytest.param(
            {"file_format_patterns": ConfigFormat.TOML}, 2, "", id="toml-only"
        ),
    ),
)
def test_remote_conf_content_type_never_widens_the_format_set(
    invoke,
    httpserver,
    file_format_patterns,
    exit_code,
    stdout,
):
    """A media type is resolved against `file_format_patterns` alone.

    The same `application/json` download feeds the CLI when `JSON` is accepted,
    and is rejected outright when the option only declares `TOML`.
    """

    @click.command
    @option("--dummy-flag/--no-flag")
    @config_option(**file_format_patterns)
    def config_cli1(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    httpserver.expect_request("/settings").respond_with_data(
        JSON_FILE, content_type="application/json"
    )

    result = invoke(
        config_cli1,
        "--config",
        httpserver.url_for("/settings"),
        color=False,
    )
    assert result.exit_code == exit_code
    assert result.stdout == stdout
    if exit_code:
        assert "Error parsing file as TOML." in result.stderr


@pytest.mark.parametrize(
    ("file_format_patterns", "expected"),
    (
        pytest.param(ConfigFormat.TOML, "TOML", id="single"),
        pytest.param([ConfigFormat.TOML, ConfigFormat.JSON], "TOML or JSON", id="pair"),
        pytest.param(
            [ConfigFormat.TOML, ConfigFormat.JSON, ConfigFormat.INI],
            "TOML, JSON or INI",
            id="triple",
        ),
    ),
)
def test_unparsable_conf_message_enumerates_formats(
    invoke,
    create_config,
    caplog,
    file_format_patterns,
    expected,
):
    """The "error parsing" message never dangles its conjunction."""
    conf_path = create_config("configuration.toml", "This is not a TOML file.")

    @click.command
    @option("--dummy-flag/--no-flag")
    @config_option(file_format_patterns=file_format_patterns)
    def config_cli1(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    with caplog.at_level(logging.CRITICAL, logger="click_extra"):
        result = invoke(config_cli1, "--config", str(conf_path), color=False)

    assert result.exit_code == 2
    assert f"Error parsing file as {expected}." in caplog.text


def test_argfile_conf_file_overrides_defaults(
    invoke,
    simple_config_cli,
    create_config,
    assert_output_regex,
):
    """An argfile feeds CLI tokens into the same default_map pipeline."""
    conf_path = create_config("configuration.conf", ARGFILE_FILE)

    result = invoke(
        simple_config_cli,
        "--config",
        str(conf_path),
        "default",
        color=False,
    )
    # Subcommand options cannot be addressed from an argfile, so int_param
    # keeps its default.
    assert result.stdout == (
        "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 10\n"
    )

    # Debug level has been activated by the configuration file.
    assert_output_regex(
        result.stderr,
        rf"Load configuration matching {re.escape(str(conf_path))}\n"
        + default_debug_uncolored_logging
        + default_debug_uncolored_version_details
        + default_debug_uncolored_log_end,
    )
    assert result.exit_code == 0


def test_argfile_conf_metadata(invoke, create_config):
    @click.command
    @config_option
    @pass_context
    def config_metadata(ctx):
        echo(f"conf_source={ctx.meta['click_extra.conf_source']}")
        echo(f"conf_full={ctx.meta['click_extra.conf_full']}")

    conf_path = create_config(
        "configuration.conf",
        "--verbosity DEBUG\n--unknown-token some value\n",
    )

    result = invoke(config_metadata, "--config", str(conf_path))
    assert result.stdout == (
        f"conf_source={conf_path}\n"
        "conf_full={'config-metadata': "
        "{'verbosity': 'DEBUG', 'unknown_token': 'some'}}\n"
    )
    assert result.stderr == f"Load configuration matching {conf_path}\n"
    assert result.exit_code == 0


def test_argfile_cli_overrides_conf(invoke, create_config):
    """Command-line parameters take precedence over argfile values."""

    @click.command
    @config_option
    @option("--dummy-flag/--no-flag", default=True)
    @option("--name", default="nobody")
    def argfile_cli(dummy_flag, name):
        echo(f"dummy_flag = {dummy_flag!r}")
        echo(f"name = {name!r}")

    conf_path = create_config(
        "override.conf",
        '--no-flag\n--name "from config"\n',
    )

    result = invoke(
        argfile_cli,
        "--config",
        str(conf_path),
        "--dummy-flag",
        "--name",
        "from CLI",
        color=False,
    )
    assert result.stdout == "dummy_flag = True\nname = 'from CLI'\n"
    assert result.exit_code == 0


def test_argfile_secondary_flag_and_inline_value(invoke, create_config):
    @click.command
    @config_option
    @option("--dummy-flag/--no-flag", default=True)
    @option("--name", default="nobody")
    @option("--ratio", type=float, default=1.0)
    def argfile_cli(dummy_flag, name, ratio):
        echo(f"dummy_flag = {dummy_flag!r}")
        echo(f"name = {name!r}")
        echo(f"ratio = {ratio!r}")

    conf_path = create_config(
        "secondary.conf",
        "# A comment.\n--no-flag\n--name='John #1 Doe'\n--ratio=0.5\n",
    )

    result = invoke(argfile_cli, "--config", str(conf_path), color=False)
    assert result.stdout == ("dummy_flag = False\nname = 'John #1 Doe'\nratio = 0.5\n")
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("conf_text", "expected_key"),
    [
        pytest.param(
            "--unknown-option some value\n--name ok\n",
            "unknown_option",
            id="unknown-option-rejected",
        ),
        pytest.param(
            "--Unknown-Option some value\n--name ok\n",
            "unknown_option",
            id="unknown-option-case-folded",
        ),
        pytest.param("--name ok\n", None, id="clean-config-accepted"),
    ],
)
def test_argfile_strict_conf(invoke, create_config, conf_text, expected_key):
    """Strict mode rejects unknown options with the standard error.

    An unmatched declaration is named the way Click names a parameter it
    derives from one, case fold included, so `--Unknown-Option` is reported
    as `unknown_option`.
    """

    @click.command
    @config_option(strict=True)
    @option("--name", default="nobody")
    def argfile_strict_cli(name):
        echo(f"name = {name!r}")

    conf_path = create_config("strict.conf", conf_text)
    result = invoke(argfile_strict_cli, "--config", str(conf_path), color=False)

    if expected_key:
        assert result.exit_code == 1
        assert not result.stdout
        assert (
            "Configuration validation error: "
            f"Unknown configuration key {expected_key!r}." in result.stderr
        )
    else:
        assert result.exit_code == 0
        assert result.stdout == "name = 'ok'\n"


def test_argfile_unknown_option_ignored_when_not_strict(invoke, create_config):
    @click.command
    @config_option
    @option("--name", default="nobody")
    def argfile_lax_cli(name):
        echo(f"name = {name!r}")

    conf_path = create_config("lax.conf", "--unknown-option some value\n--name ok\n")
    result = invoke(argfile_lax_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 0
    assert result.stdout == "name = 'ok'\n"


@pytest.mark.parametrize(
    "conf_text",
    [
        pytest.param("--name\n", id="missing-value"),
        pytest.param("# Only a comment.\n", id="comment-only"),
        pytest.param("key = value\n", id="foreign-ini-style"),
    ],
)
def test_argfile_unparsable_conf(invoke, create_config, conf_text):
    """An argfile that produces no option is skipped like any other format."""

    @command
    @option("--name", default="nobody")
    def argfile_cli(name):
        echo(f"name = {name!r}")

    conf_path = create_config("broken.conf", conf_text)
    result = invoke(argfile_cli, "--config", str(conf_path), color=False)
    assert not result.stdout
    assert "critical: Error parsing file as" in result.stderr
    assert result.exit_code == 2


def test_argfile_positional_tokens_skipped(invoke, create_config):
    @click.command
    @config_option
    @option("--name", default="nobody")
    def argfile_cli(name):
        echo(f"name = {name!r}")

    conf_path = create_config("positionals.conf", "subcommand\n--name ok\n")
    result = invoke(argfile_cli, "--config", str(conf_path), color=False)
    assert result.exit_code == 0
    assert result.stdout == "name = 'ok'\n"


def test_argfile_export_config_rejected(invoke):
    """Argfile has no serializer, so --export-config rejects it."""

    @command
    def dump_cli():
        echo("ran")

    result = invoke(dump_cli, "--export-config", "argfile", color=False)
    assert result.exit_code == 2
    assert "'argfile' is not one of" in result.stderr


@pytest.mark.parametrize("ext", ["sqlite", "sqlite3"])
def test_sqlite_conf_file_overrides_defaults(
    invoke,
    simple_config_cli,
    tmp_path,
    ext,
):
    conf_path = make_sqlite_config(tmp_path / f"configuration.{ext}", SQLITE_DATA)

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
    assert result.stderr == f"Load configuration matching {conf_path}\n"
    assert result.exit_code == 0


def test_sqlite_conf_metadata(invoke, tmp_path):
    conf_path = make_sqlite_config(tmp_path / "configuration.sqlite", SQLITE_DATA)

    @click.command
    @config_option
    @pass_context
    def config_metadata(ctx):
        echo(f"conf_source={ctx.meta['click_extra.conf_source']}")
        echo(f"conf_full={ctx.meta['click_extra.conf_full']}")
        echo(f"default_map={ctx.default_map}")

    result = invoke(config_metadata, "--config", str(conf_path))
    assert result.stdout == (
        f"conf_source={conf_path}\n"
        f"conf_full={SQLITE_DATA}\n"
        # No configuration values match the CLI's parameter structure, so the
        # ChainMap layered onto the existing default_map holds two empty maps.
        "default_map=ChainMap({}, {})\n"
    )
    assert result.stderr == f"Load configuration matching {conf_path}\n"
    assert result.exit_code == 0


def test_sqlite_read_and_parse_conf(tmp_path):
    """The default format patterns discover SQLite databases by extension."""
    conf_path = make_sqlite_config(tmp_path / "my-cli.sqlite", SQLITE_DATA)

    conf_option = ConfigOption()
    location, conf = conf_option.read_and_parse_conf(str(tmp_path / "*"))
    assert location == conf_path.resolve()
    assert conf == SQLITE_DATA


@pytest.mark.parametrize(
    "make_db",
    [
        pytest.param("garbage", id="garbage-content"),
        pytest.param("missing-table", id="missing-table"),
        pytest.param("empty-table", id="empty-table"),
    ],
)
def test_sqlite_conf_unparsable(invoke, simple_config_cli, tmp_path, make_db):
    """A SQLite file that cannot yield a configuration is rejected."""
    conf_path = tmp_path / "configuration.sqlite"
    if make_db == "garbage":
        conf_path.write_text("this is not a SQLite database", encoding="UTF-8")
    else:
        make_sqlite_config(conf_path, create_table=(make_db != "missing-table"))

    result = invoke(
        simple_config_cli,
        "--config",
        str(conf_path),
        "default",
        color=False,
    )
    assert result.exit_code == 2
    assert "critical: Error parsing file as" in result.stderr


SPLITTABLE_STDLIB_MODULES = frozenset((
    "curses",
    "dbm",
    "readline",
    "sqlite3",
    "tkinter",
))
"""Standard library modules a distribution can ship apart from its base Python.

Each wraps a system library, so a packager can leave it out of the interpreter:
FreeBSD serves `sqlite3` as a separate `pyXXX-sqlite3` package, and Debian
serves `tkinter` as `python3-tk`. A module-level import of any of them kills
every CLI built on `click_extra` at import time, on an interpreter that is
otherwise complete, so each one is probed and imported at its point of use."""


def eager_imports(tree: ast.Module) -> set[str]:
    """Top-level packages a module imports as soon as it is loaded.

    Skips function bodies, which import at call time, and `try` blocks, which
    guard against a missing module. Those are the two shapes that survive an
    interpreter without the module.
    """
    found: set[str] = set()

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Try)):
                continue
            if isinstance(child, ast.Import):
                found.update(alias.name.split(".")[0] for alias in child.names)
            elif isinstance(child, ast.ImportFrom) and not child.level and child.module:
                found.add(child.module.split(".")[0])
            visit(child)

    visit(tree)
    return found


def test_no_splittable_stdlib_module_imported_at_load_time():
    """No module of the package imports a splittable module unconditionally."""
    package_root = Path(__file__).parent.parent / "click_extra"
    offenders = {}
    for module_path in sorted(package_root.rglob("*.py")):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        culprits = eager_imports(tree) & SPLITTABLE_STDLIB_MODULES
        if culprits:
            offenders[str(module_path.relative_to(package_root))] = sorted(culprits)
    assert not offenders


@pytest.mark.once
def test_sqlite3_not_imported_by_the_package():
    """Importing the package leaves `sqlite3` out of `sys.modules`.

    Covers the whole import graph, dependencies included, where
    `test_no_splittable_stdlib_module_imported_at_load_time` only reads the
    package's own sources.
    """
    result = subprocess.run(
        (
            sys.executable,
            "-c",
            "import sys, click_extra; print('sqlite3' in sys.modules)",
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_sqlite_support_gates_the_format():
    """`SQLITE` is enabled exactly when the standard library ships its bindings."""
    assert ConfigFormat.SQLITE.enabled is SQLITE_SUPPORT

    message = disabled_format_message(ConfigFormat.SQLITE)
    # There is no `click-extra[sqlite]` to install: the bindings ship with Python.
    assert "click-extra[" not in message
    assert "sqlite3" in message


@pytest.mark.parametrize(
    "plist_variant",
    [
        pytest.param(plistlib.FMT_XML, id="xml"),
        pytest.param(plistlib.FMT_BINARY, id="binary"),
    ],
)
def test_plist_conf_file_overrides_defaults(
    invoke,
    simple_config_cli,
    assert_output_regex,
    tmp_path,
    plist_variant,
):
    """Both the XML and the binary plist variants load through --config."""
    conf_path = tmp_path / "configuration.plist"
    conf_path.write_bytes(plistlib.dumps(PLIST_DATA, fmt=plist_variant))

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

    # Debug level has been activated by the configuration file.
    assert_output_regex(
        result.stderr,
        rf"Load configuration matching {re.escape(str(conf_path))}\n"
        + default_debug_uncolored_logging
        + default_debug_uncolored_version_details
        + default_debug_uncolored_log_end,
    )
    assert result.exit_code == 0


def test_plist_read_and_parse_conf(tmp_path):
    """The default format patterns discover plist files by extension."""
    conf_path = tmp_path / "my-cli.plist"
    conf_path.write_bytes(plistlib.dumps(PLIST_DATA, fmt=plistlib.FMT_BINARY))

    conf_option = ConfigOption()
    location, conf = conf_option.read_and_parse_conf(str(tmp_path / "*"))
    assert location == conf_path.resolve()
    assert conf == PLIST_DATA


def test_validate_config_sqlite_valid(invoke, tmp_path):
    """--validate-config accepts a valid SQLite configuration database."""
    conf_path = make_sqlite_config(
        tmp_path / "valid.sqlite",
        {
            "validate-cli": {
                "dummy_flag": True,
                "my_list": ["pip", "npm"],
                "sub": {
                    "int_param": 3,
                },
            },
        },
    )

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


def test_merge_default_map_standalone(invoke):
    """merge_default_map filters a config into default_map on its own.

    load_conf bypasses this method by installing the merged config the validation
    pipeline already produced, so it is exercised here directly to cover the
    standalone entry point external callers rely on.
    """

    @click.command
    @option("--flag-a/--no-flag-a")
    @config_option
    @no_config_option
    @pass_context
    def merge_map_cli(ctx, flag_a):
        config_opt = next(p for p in ctx.command.params if isinstance(p, ConfigOption))
        config_opt.merge_default_map(
            ctx, {"merge-map-cli": {"flag_a": True, "unknown": "dropped"}}
        )
        echo(f"default_map={ctx.default_map}")

    result = invoke(merge_map_cli, "--no-config", color=False)
    assert result.exit_code == 0
    # Recognized flag is merged in; the unknown key is filtered out.
    assert "default_map=ChainMap({'flag_a': True}, {})" in result.stdout


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


def test_params_template_not_mutated_across_invocations(invoke, create_config):
    """Back-to-back invocations of the same CLI must not cross-contaminate via
    ``ConfigOption.params_template``.

    ``params_template`` is a ``@cached_property`` of the ``ConfigOption`` instance
    bound at decoration time, so it lives for the lifetime of the CLI object.
    ``_merge_into_template`` mutates its first argument in place; without a defensive
    copy, the cached template would accumulate values from earlier ``--config``
    loads and leak them into ``default_map`` on subsequent invocations.
    """
    conf_with_city = create_config(
        "city.toml",
        dedent("""\
            [pollution-cli]
            city = "Paris"
            """),
    )
    conf_with_weather = create_config(
        "weather.toml",
        dedent("""\
            [pollution-cli]
            weather = "rainy"
            """),
    )

    @click.command
    @option("--city", default="Atlantis")
    @option("--weather", default="sunny")
    @config_option
    def pollution_cli(city, weather):
        echo(f"city={city!r} weather={weather!r}")

    # First invocation: only `city` is set by the config file.
    result1 = invoke(pollution_cli, "--config", str(conf_with_city), color=False)
    assert result1.exit_code == 0
    assert result1.stdout == "city='Paris' weather='sunny'\n"

    # Second invocation: only `weather` is set by the config file. `city` must
    # fall back to its declared default, not carry over from the previous load.
    result2 = invoke(pollution_cli, "--config", str(conf_with_weather), color=False)
    assert result2.exit_code == 0
    assert result2.stdout == "city='Atlantis' weather='rainy'\n"


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
        assert isinstance(config_opt, ConfigOption)

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
        assert isinstance(config_opt, ConfigOption)
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
        assert isinstance(config_opt, ConfigOption)
        patterns = list(config_opt.parent_patterns(input_path))

    expected = expected_start(tmp_path)
    for i, exp in enumerate(expected):
        assert patterns[i] == exp, f"Pattern {i} mismatch"

    assert all(isinstance(p, tuple) and len(p) == 2 for p in patterns)

    if search_parents:
        assert all(
            root_dir is not None and Path(root_dir).is_absolute()
            for root_dir, _ in patterns
        )
        root_path = Path("/") if not is_windows() else Path(tmp_path.drive + "\\")
        last_root = patterns[-1][0]
        assert last_root is not None
        assert Path(last_root) == root_path


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
        assert isinstance(config_opt, ConfigOption)
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
        assert isinstance(config_opt, ConfigOption)
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

    # Change to the parent directory to create a relative path.
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path / "level1")
        relative_path = "level2/config.toml"

        with click.Context(test_cli, info_name="test-cli"):
            config_opt = search_params(test_cli.params, ConfigOption)
            assert isinstance(config_opt, ConfigOption)

            patterns = list(config_opt.parent_patterns(relative_path))

            # All root_dirs should be absolute.
            assert all(
                root_dir is not None and Path(root_dir).is_absolute()
                for root_dir, _ in patterns
            )

            # First pattern should resolve to the config file's parent.
            root_dir, file_pattern = patterns[0]
            assert root_dir is not None
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
        assert isinstance(config_opt, ConfigOption)
        patterns = list(config_opt.parent_patterns(str(config_file)))

    # First yield should be (parent_of_file, filename).
    root_dir, file_pattern = patterns[0]
    assert root_dir is not None
    assert Path(root_dir) == config_file.parent
    assert file_pattern == config_file.name
    # Every root_dir should be inside or equal to the boundary.
    for root_dir, _ in patterns:
        assert root_dir is not None
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
        assert isinstance(config_opt, ConfigOption)
        patterns = list(config_opt.parent_patterns(pattern))

    assert patterns[0] == (str(deep_path), "*.toml")

    if expected_bounded:
        for root_dir, _ in patterns:
            assert root_dir is not None
            assert Path(root_dir).is_relative_to(vcs_root), (
                f"{root_dir} is outside VCS root {vcs_root}"
            )
    else:
        root_path = Path("/") if not is_windows() else Path(tmp_path.drive + "\\")
        last_root = patterns[-1][0]
        assert last_root is not None
        assert Path(last_root) == root_path


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

    original_access = os.access

    def fake_access(path, mode, **kwargs):
        if Path(path).resolve() == (tmp_path / "a").resolve():
            return False
        return original_access(path, mode, **kwargs)

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        assert isinstance(config_opt, ConfigOption)
        with unittest.mock.patch(
            "click_extra.config.option.os.access", side_effect=fake_access
        ):
            patterns = list(config_opt.parent_patterns(str(config_file)))

    # First yield: (parent_of_file, filename).
    root_dir, file_pattern = patterns[0]
    assert root_dir is not None
    assert Path(root_dir) == config_file.parent
    assert file_pattern == config_file.name
    # Should stop before tmp_path/a (inaccessible).
    for root_dir, _ in patterns:
        assert root_dir is not None
        assert Path(root_dir) != tmp_path / "a"
        assert Path(root_dir) != tmp_path


# --- Cascading configuration files --------------------------------------------


@pytest.fixture
def cascade_tree(tmp_path, monkeypatch):
    """Point auto-discovery at a temporary app dir nested inside `tmp_path`.

    Returns `(tmp_path, app_dir)`: a config file dropped in `app_dir` is the
    most local source, one in `tmp_path` sits one level up the parent walk.
    """
    app_dir = tmp_path / "appdir"
    app_dir.mkdir()
    monkeypatch.setattr(
        "click_extra.config.option.get_app_dir", lambda *a, **k: str(app_dir)
    )
    return tmp_path, app_dir


LOCAL_CONF = dedent(
    """
    [cascade-cli]
    int_param = 1
    dummy_flag = true
    """,
)

PARENT_CONF = dedent(
    """
    [cascade-cli]
    int_param = 99
    other_param = "from_parent"
    """,
)


def _cascade_cli_factory(stop_at, cascade):
    """A CLI reading `--int-param`, `--dummy-flag` and `--other-param`.

    Built on plain `click.command` so the single `@config_option` below is
    not duplicated by click-extra's auto-injected default one.
    """

    @click.command
    @config_option(search_parents=True, stop_at=stop_at, cascade=cascade)
    @click.option("--int-param", type=int, default=10)
    @click.option("--dummy-flag/--no-flag")
    @click.option("--other-param", default="none")
    def cascade_cli(int_param, dummy_flag, other_param):
        echo(f"int_param = {int_param!r}")
        echo(f"dummy_flag = {dummy_flag!r}")
        echo(f"other_param = {other_param!r}")

    return cascade_cli


def test_cascade_merges_files_local_wins(invoke, cascade_tree):
    """With cascade=True, local values win and parent values fill the gaps."""
    tmp_path, app_dir = cascade_tree
    (app_dir / "config.toml").write_text(LOCAL_CONF, encoding="utf-8")
    (tmp_path / "config.toml").write_text(PARENT_CONF, encoding="utf-8")

    result = invoke(_cascade_cli_factory(tmp_path, cascade=True), color=False)
    assert result.stdout == (
        "int_param = 1\ndummy_flag = True\nother_param = 'from_parent'\n"
    )
    assert result.exit_code == 0


def test_no_cascade_first_file_wins(invoke, cascade_tree):
    """Without cascade, the first parseable file wins entirely."""
    tmp_path, app_dir = cascade_tree
    (app_dir / "config.toml").write_text(LOCAL_CONF, encoding="utf-8")
    (tmp_path / "config.toml").write_text(PARENT_CONF, encoding="utf-8")

    result = invoke(_cascade_cli_factory(tmp_path, cascade=False), color=False)
    assert result.stdout == ("int_param = 1\ndummy_flag = True\nother_param = 'none'\n")
    assert result.exit_code == 0


def test_cascade_single_layer_from_parent(invoke, cascade_tree):
    """A lone file found up the walk is applied as-is."""
    tmp_path, _app_dir = cascade_tree
    (tmp_path / "config.toml").write_text(PARENT_CONF, encoding="utf-8")

    result = invoke(_cascade_cli_factory(tmp_path, cascade=True), color=False)
    assert result.stdout == (
        "int_param = 99\ndummy_flag = False\nother_param = 'from_parent'\n"
    )
    assert result.exit_code == 0


def test_cascade_explicit_config_does_not_cascade(invoke, cascade_tree):
    """An explicit --config pins a single source, even with cascade=True."""
    tmp_path, app_dir = cascade_tree
    (app_dir / "config.toml").write_text(LOCAL_CONF, encoding="utf-8")
    parent_conf = tmp_path / "config.toml"
    parent_conf.write_text(PARENT_CONF, encoding="utf-8")

    result = invoke(
        _cascade_cli_factory(tmp_path, cascade=True),
        "--config",
        str(parent_conf),
        color=False,
    )
    assert result.stdout == (
        "int_param = 99\ndummy_flag = False\nother_param = 'from_parent'\n"
    )
    assert result.exit_code == 0


def test_cascade_conf_sources_metadata(invoke, cascade_tree):
    """ctx.meta[CONF_SOURCES] lists every loaded file, highest precedence first."""
    from click_extra import context

    tmp_path, app_dir = cascade_tree
    local_conf = app_dir / "config.toml"
    local_conf.write_text(LOCAL_CONF, encoding="utf-8")
    parent_conf = tmp_path / "config.toml"
    parent_conf.write_text(PARENT_CONF, encoding="utf-8")

    @click.command
    @config_option(search_parents=True, stop_at=tmp_path, cascade=True)
    @click.option("--int-param", type=int, default=10)
    @pass_context
    def cascade_cli(ctx, int_param):
        sources = context.get(ctx, context.CONF_SOURCES)
        for location, _conf in sources:
            echo(str(location))
        echo(f"conf_source = {context.get(ctx, context.CONF_SOURCE)}")

    result = invoke(cascade_cli, color=False)
    assert result.stdout == (
        f"{local_conf.resolve()}\n"
        f"{parent_conf.resolve()}\n"
        f"conf_source = {local_conf.resolve()}\n"
    )
    assert result.exit_code == 0


def test_cascade_conf_full_is_merged_view(invoke, cascade_tree):
    """ctx.meta[CONF_FULL] exposes the deep-merged document."""
    from click_extra import context

    tmp_path, app_dir = cascade_tree
    (app_dir / "config.toml").write_text(LOCAL_CONF, encoding="utf-8")
    (tmp_path / "config.toml").write_text(PARENT_CONF, encoding="utf-8")

    @click.command
    @config_option(search_parents=True, stop_at=tmp_path, cascade=True)
    @click.option("--int-param", type=int, default=10)
    @pass_context
    def cascade_cli(ctx, int_param):
        full = context.get(ctx, context.CONF_FULL)
        section = full["cascade-cli"]
        echo(f"int_param = {section['int_param']!r}")
        echo(f"other_param = {section['other_param']!r}")

    result = invoke(cascade_cli, color=False)
    assert result.stdout == "int_param = 1\nother_param = 'from_parent'\n"
    assert result.exit_code == 0


def test_cascade_validation_error_names_file(invoke, cascade_tree, caplog):
    """A strict-check failure in one layer names that file and exits 1."""
    tmp_path, app_dir = cascade_tree
    (app_dir / "config.toml").write_text(LOCAL_CONF, encoding="utf-8")
    bad_parent = tmp_path / "config.toml"
    bad_parent.write_text(
        dedent(
            """
            [cascade-cli]
            unknown_key = "boom"
            """,
        ),
        encoding="utf-8",
    )

    @click.command
    @config_option(search_parents=True, stop_at=tmp_path, cascade=True, strict=True)
    @click.option("--int-param", type=int, default=10)
    @click.option("--dummy-flag/--no-flag")
    @click.option("--other-param", default="none")
    def cascade_cli(int_param, dummy_flag, other_param):
        echo(f"int_param = {int_param!r}")

    result = invoke(cascade_cli, color=False)
    assert not result.stdout
    assert f"Configuration validation error in {bad_parent.resolve()}" in caplog.text
    assert "Unknown configuration key 'unknown_key'" in caplog.text
    assert result.exit_code == 1


def test_read_and_parse_all_conf_orders_local_first(tmp_path):
    """All parseable files are yielded, deepest first; unparsable ones skip."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    deep = tmp_path / "a" / "b" / "config.toml"
    deep.write_text("[test-cli]\nk = 2", encoding="utf-8")
    middle = tmp_path / "a" / "config.toml"
    middle.write_text("[test-cli]\nk = 1", encoding="utf-8")
    # Unparsable content: found, but not yielded.
    (tmp_path / "config.toml").write_text("not toml {{{", encoding="utf-8")

    @click.command
    @config_option(search_parents=True, stop_at=tmp_path)
    def test_cli():
        pass

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        assert isinstance(config_opt, ConfigOption)
        results = list(
            config_opt.read_and_parse_all_conf(str(tmp_path / "a" / "b" / "*.toml"))
        )

    assert [location for location, _ in results] == [
        deep.resolve(),
        middle.resolve(),
    ]
    assert [conf["test-cli"]["k"] for _, conf in results] == [2, 1]


def test_read_and_parse_conf_returns_first(tmp_path):
    """read_and_parse_conf keeps its first-match contract on top of the generator."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    deep = tmp_path / "a" / "b" / "config.toml"
    deep.write_text("[test-cli]\nk = 2", encoding="utf-8")
    (tmp_path / "a" / "config.toml").write_text("[test-cli]\nk = 1", encoding="utf-8")

    @click.command
    @config_option(search_parents=True, stop_at=tmp_path)
    def test_cli():
        pass

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        assert isinstance(config_opt, ConfigOption)
        location, conf = config_opt.read_and_parse_conf(
            str(tmp_path / "a" / "b" / "*.toml")
        )

    assert location == deep.resolve()
    assert conf == {"test-cli": {"k": 2}}


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
    # Both params come from the same file: values are not merged across files.
    assert (
        "param_a='from_first'" in result.stdout
        and "param_b='from_first'" in result.stdout
    ) or (
        "param_a='from_second'" in result.stdout
        and "param_b='from_second'" in result.stdout
    )


def test_forced_flags_warnings(caplog):
    """Warnings fire when SPLIT, BRACE or NODIR flags are missing."""
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
    default pattern got the directory prefix: others were searched in CWD.
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
    with (
        unittest.mock.patch.object(
            ConfigFormat, "enabled", new_callable=lambda: property(lambda self: False)
        ),
        pytest.raises(ValueError, match="No configuration format is enabled"),
    ):
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


def test_validate_config_accepts_a_glob(invoke, create_config):
    """--validate-config takes every location `--config` takes, glob included."""
    conf_text = dedent("""\
        [validate-cli]
        dummy_flag = true
        """)
    conf_path = create_config("valid.toml", conf_text)

    @click.command
    @option("--dummy-flag/--no-flag")
    @config_option
    @validate_config_option
    def validate_cli(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    pattern = str(conf_path.parent / "*.toml")
    result = invoke(validate_cli, "--validate-config", pattern, color=False)
    assert result.exit_code == 0
    assert "is valid" in result.stderr


def test_validate_config_accepts_a_url(invoke, httpserver):
    """A configuration a CLI can load from a URL is one it can also validate."""
    conf_text = dedent("""\
        [validate-cli]
        dummy_flag = true
        """)
    httpserver.expect_request("/settings.toml").respond_with_data(
        conf_text, content_type="application/toml"
    )

    @click.command
    @option("--dummy-flag/--no-flag")
    @config_option
    @validate_config_option
    def validate_cli(dummy_flag):
        echo(f"dummy_flag = {dummy_flag!r}")

    result = invoke(
        validate_cli,
        "--validate-config",
        httpserver.url_for("/settings.toml"),
        color=False,
    )
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
    """--validate-config reports a nonexistent location from its own callback."""

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
    assert f"Configuration file not found: {missing}" in result.stderr


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


def test_export_config_to_stdout(invoke):
    """--export-config writes the resolved configuration and exits 0."""

    @command
    @option("--name", default="Alice")
    def dump_cli(name):
        echo(f"name = {name!r}")

    result = invoke(dump_cli, "--export-config", "toml", color=False)
    assert result.exit_code == 0
    assert "[dump-cli]" in result.stdout
    assert 'name = "Alice"' in result.stdout
    # Action options and config plumbing are excluded from the dump.
    assert "export_config" not in result.stdout
    assert "params =" not in result.stdout
    assert "config =" not in result.stdout
    assert "version" not in result.stdout


def test_export_config_captures_overrides(invoke):
    """Command-line values are reflected in the dump."""

    @command
    @option("--name", default="Alice")
    @option("--tag", multiple=True)
    def dump_cli(name, tag):
        echo("ran")

    result = invoke(
        dump_cli,
        "--name",
        "Bob",
        "--tag",
        "x",
        "--tag",
        "y",
        "--export-config",
        "toml",
        color=False,
    )
    assert result.exit_code == 0
    assert 'name = "Bob"' in result.stdout
    assert 'tag = ["x", "y"]' in result.stdout


def test_export_config_captures_environment(invoke):
    """Values resolved from environment variables are reflected in the dump."""

    @command
    @option("--city", default="Lisbon")
    @option("--limit", type=int, default=5)
    def dump_cli(city, limit):
        echo("ran")

    result = invoke(
        dump_cli,
        "--city",
        "Berlin",
        "--export-config",
        "toml",
        color=False,
        env={"DUMP_CLI_CITY": "Tokyo", "DUMP_CLI_LIMIT": "30"},
    )
    assert result.exit_code == 0
    # The command line wins over the environment...
    assert 'city = "Berlin"' in result.stdout
    # ...but an environment-only value is still captured, keeping its type.
    assert "limit = 30" in result.stdout


def test_export_config_numeric_values_keep_their_type(invoke):
    """A command-line numeric scalar is dumped as a number, not a quoted string."""

    @command
    @option("--count", type=int, default=3)
    def dump_cli(count):
        echo("ran")

    result = invoke(dump_cli, "--count", "7", "--export-config", "toml", color=False)
    assert result.exit_code == 0
    assert "count = 7" in result.stdout
    assert 'count = "7"' not in result.stdout


@pytest.mark.parametrize("fmt", ["toml", "json", "yaml", "plist"])
def test_export_config_round_trip(invoke, tmp_path, fmt):
    """A dumped configuration reloads to the same values through --config."""

    @command
    @option("--name", default="Alice")
    @option("--count", type=int, default=3)
    def dump_cli(name, count):
        echo(f"name={name!r} count={count!r}")

    result = invoke(
        dump_cli,
        "--name",
        "Zoe",
        "--count",
        "42",
        "--export-config",
        fmt,
        color=False,
    )
    assert result.exit_code == 0

    conf_path = tmp_path / f"dumped.{fmt}"
    conf_path.write_text(result.stdout, encoding="utf-8")

    reloaded = invoke(dump_cli, "--config", str(conf_path), color=False)
    assert reloaded.exit_code == 0
    assert reloaded.stdout == "name='Zoe' count=42\n"


def test_export_config_invalid_format(invoke):
    """An unsupported format token is rejected by the Choice."""

    @command
    def dump_cli():
        echo("ran")

    result = invoke(dump_cli, "--export-config", "ini", color=False)
    assert result.exit_code == 2
    assert "'ini' is not one of" in result.stderr


def test_export_config_requires_config_option(invoke):
    """--export-config without @config_option raises RuntimeError."""

    @click.command
    @export_config_option
    def missing_config():
        echo("Hello, World!")

    result = invoke(missing_config, "--export-config", "toml")
    assert result.exception
    assert type(result.exception) is RuntimeError
    assert "ExportConfigOption must be used alongside ConfigOption" in str(
        result.exception
    )
    assert result.exit_code == 1


def test_export_config_standalone_falls_back_to_defaults(invoke):
    """Without a captured command line (vanilla Command), defaults are dumped."""

    @click.command
    @option("--name", default="Alice")
    @config_option
    @export_config_option
    def standalone_cli(name):
        echo("ran")

    result = invoke(standalone_cli, "--name", "Bob", "--export-config", "toml")
    assert result.exit_code == 0
    # No RAW_ARGS to replay: the --name Bob override cannot be recovered, so the
    # default value is dumped instead.
    assert 'name = "Alice"' in result.stdout


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

# Sentinel for sanity cases that omit the ``default`` keyword entirely, exercising
# the code paths that skip the default-dependent checks.
_NO_DEFAULT = object()


@pytest.mark.parametrize(
    ("default", "file_format_patterns", "flags", "present", "absent"),
    (
        pytest.param(
            "~/*",
            {ConfigFormat.YAML: ".commandrc"},
            FULL_SEARCH_FLAGS,
            ("Broad search pattern", "literal format patterns"),
            (),
            id="broad_glob_narrow_format",
        ),
        pytest.param(
            "~/*",
            {ConfigFormat.YAML: "*.yaml"},
            FULL_SEARCH_FLAGS,
            (),
            ("Broad search pattern",),
            id="broad_glob_wildcard_format",
        ),
        pytest.param(
            "/etc/myapp/config.conf",
            {ConfigFormat.TOML: "*.toml"},
            FULL_SEARCH_FLAGS,
            ("does not match any format pattern",),
            (),
            id="disjoint_patterns",
        ),
        pytest.param(
            "/etc/myapp/config.toml",
            {ConfigFormat.TOML: "*.toml"},
            FULL_SEARCH_FLAGS,
            (),
            ("does not match any format pattern",),
            id="disjoint_matching_literal",
        ),
        pytest.param(
            _NO_DEFAULT,
            {ConfigFormat.YAML: "*.toml"},
            FULL_SEARCH_FLAGS,
            ("canonically associated",),
            (),
            id="format_extension_mismatch",
        ),
        pytest.param(
            _NO_DEFAULT,
            {ConfigFormat.YAML: "*.yaml"},
            FULL_SEARCH_FLAGS,
            (),
            ("canonically associated",),
            id="format_extension_correct",
        ),
        pytest.param(
            "~/.myapprc",
            {ConfigFormat.YAML: "*.yaml"},
            NO_DOTGLOB_FLAGS,
            ("DOTGLOB is not set",),
            (),
            id="dotfile_without_dotglob",
        ),
        pytest.param(
            "~/configs/*",
            {ConfigFormat.YAML: ".myapprc"},
            NO_DOTGLOB_FLAGS,
            ("DOTGLOB is not set",),
            (),
            id="dotfile_format_without_dotglob",
        ),
        pytest.param(
            "~/.myapprc",
            {ConfigFormat.YAML: "*.yaml"},
            FULL_SEARCH_FLAGS,
            (),
            ("DOTGLOB is not set",),
            id="dotfile_with_dotglob",
        ),
        pytest.param(
            _NO_DEFAULT,
            {ConfigFormat.YAML: "*.yaml"},
            FULL_SEARCH_FLAGS,
            (),
            ("Broad search pattern", "does not match"),
            id="no_explicit_default",
        ),
        pytest.param(
            _NO_DEFAULT,
            {ConfigFormat.YAML: "*.toml"},
            FULL_SEARCH_FLAGS,
            ("canonically associated",),
            (),
            id="format_mismatch_without_explicit_default",
        ),
    ),
)
def test_sanity_checks(caplog, default, file_format_patterns, flags, present, absent):
    """``_check_pattern_sanity`` emits (or suppresses) debug logs per pattern config."""
    kwargs = {
        "file_format_patterns": file_format_patterns,
        "search_pattern_flags": flags,
    }
    if default is not _NO_DEFAULT:
        kwargs["default"] = default

    with caplog.at_level(logging.DEBUG, logger="click_extra"):
        ConfigOption(**kwargs)

    for fragment in present:
        assert fragment in caplog.text
    for fragment in absent:
        assert fragment not in caplog.text


@pytest.mark.parametrize(
    ("input_conf", "expected"),
    (
        pytest.param(
            {"a": 1, "b": 2},
            {"a": 1, "b": 2},
            id="no_dots",
        ),
        pytest.param(
            {"a.b": 1},
            {"a": {"b": 1}},
            id="single_dotted_key",
        ),
        pytest.param(
            {"a.b.c": 1},
            {"a": {"b": {"c": 1}}},
            id="multi_level_dotted_key",
        ),
        pytest.param(
            {"a.b": 1, "a": {"c": 2}},
            {"a": {"b": 1, "c": 2}},
            id="mixed_dotted_and_nested",
        ),
        pytest.param(
            {"a": {"b.c": 1, "d": 2}},
            {"a": {"b": {"c": 1}, "d": 2}},
            id="nested_dotted_key",
        ),
        pytest.param(
            {"a.b": 1, "a.c": 2},
            {"a": {"b": 1, "c": 2}},
            id="multiple_dotted_same_prefix",
        ),
        pytest.param(
            {"a.b": {"c": 3}, "a": {"d": 4}},
            {"a": {"b": {"c": 3}, "d": 4}},
            id="dotted_key_with_dict_value",
        ),
        pytest.param(
            {},
            {},
            id="empty",
        ),
    ),
)
def test_expand_dotted_keys(input_conf, expected):
    assert _expand_dotted_keys(input_conf) == expected


@pytest.mark.parametrize(
    ("conf_name", "conf_text"),
    (
        pytest.param(
            "dotted.toml",
            dedent("""\
                [config-cli1]
                "default.int_param" = 77
                dummy_flag = true
                my_list = ["pip", "npm", "gem"]
                verbosity = "DEBUG"
                """),
            id="toml",
        ),
        pytest.param(
            "dotted.json",
            dedent("""\
                {
                    "config-cli1": {
                        "default.int_param": 77,
                        "dummy_flag": true,
                        "my_list": ["pip", "npm", "gem"],
                        "verbosity": "DEBUG"
                    }
                }
                """),
            id="json",
        ),
        pytest.param(
            "dotted.yaml",
            dedent("""\
                config-cli1:
                    "default.int_param": 77
                    dummy_flag: true
                    my_list:
                      - pip
                      - npm
                      - gem
                    verbosity: DEBUG
                """),
            id="yaml",
        ),
    ),
)
def test_dotted_keys_in_config(
    invoke, simple_config_cli, create_config, conf_name, conf_text
):
    """Dotted keys in config files are expanded into nested structures."""
    conf_path = create_config(conf_name, conf_text)
    result = invoke(
        simple_config_cli,
        "--config",
        str(conf_path),
        "default",
        color=False,
    )
    assert result.exit_code == 0
    assert result.stdout == (
        "dummy_flag = True\nmy_list = ('pip', 'npm', 'gem')\nint_parameter = 77\n"
    )


@pytest.mark.parametrize(
    ("input_conf", "warning_fragment"),
    (
        pytest.param(
            {"a": 1, "a.b": 2},
            "Configuration key 'a.b' conflicts with 'a'",
            id="scalar_then_dotted",
        ),
        pytest.param(
            {"a.b": 2, "a": 1},
            "Configuration key 'a' conflicts with 'a'",
            id="dotted_then_scalar",
        ),
        pytest.param(
            {"a": None, "a.b": 2},
            "Configuration key 'a.b' conflicts with 'a'",
            id="none_then_dotted",
        ),
        pytest.param(
            {"a.b": 2, "a": None},
            "Configuration key 'a' conflicts with 'a'",
            id="dotted_then_none",
        ),
        pytest.param(
            {"a.b.c": 1, "a.b": 2},
            "Configuration key 'a.b' conflicts with 'a.b'",
            id="deep_conflict",
        ),
        pytest.param(
            {"a.b": 2, "a.b.c": 1},
            "Configuration key 'a.b.c' conflicts with 'a.b'",
            id="deep_conflict_reversed",
        ),
        pytest.param(
            {"a": False, "a.b": 2},
            "Configuration key 'a.b' conflicts with 'a'",
            id="false_then_dotted",
        ),
        pytest.param(
            {"a": 0, "a.b": 2},
            "Configuration key 'a.b' conflicts with 'a'",
            id="zero_then_dotted",
        ),
        pytest.param(
            {"a": "", "a.b": 2},
            "Configuration key 'a.b' conflicts with 'a'",
            id="empty_string_then_dotted",
        ),
        pytest.param(
            {"a": [], "a.b": 2},
            "Configuration key 'a.b' conflicts with 'a'",
            id="empty_list_then_dotted",
        ),
        pytest.param(
            {"a.b": 2, "a": False},
            "Configuration key 'a' conflicts with 'a'",
            id="dotted_then_false",
        ),
        pytest.param(
            {"a.b": 2, "a": 0},
            "Configuration key 'a' conflicts with 'a'",
            id="dotted_then_zero",
        ),
    ),
)
def test_expand_dotted_keys_conflict_warning(caplog, input_conf, warning_fragment):
    """Scalar/dict conflicts on the same key emit a warning."""
    with caplog.at_level(logging.WARNING, logger="click_extra"):
        _expand_dotted_keys(input_conf)
    assert warning_fragment in caplog.text


@pytest.mark.parametrize(
    "input_conf",
    (
        pytest.param({"...": 1}, id="only_dots"),
        pytest.param({".a": 1}, id="leading_dot"),
        pytest.param({"a.": 1}, id="trailing_dot"),
    ),
)
def test_expand_dotted_keys_empty_segments(caplog, input_conf):
    """Dotted keys with empty segments are skipped with a warning."""
    with caplog.at_level(logging.WARNING, logger="click_extra"):
        result = _expand_dotted_keys(input_conf)
    assert result == {}
    assert "contains empty segments" in caplog.text


@pytest.mark.parametrize(
    ("input_conf", "expected"),
    (
        pytest.param(
            {"a": {"b": 4}, "a.b": 2},
            {"a": {"b": 2}},
            id="dict_then_dotted_same_leaf",
        ),
        pytest.param(
            {"a.b": 2, "a": {"b": 4}},
            {"a": {"b": 4}},
            id="dotted_then_dict_same_leaf",
        ),
        pytest.param(
            {"a": {}, "a.b": 2},
            {"a": {"b": 2}},
            id="empty_dict_then_dotted",
        ),
        pytest.param(
            {"a.b": None},
            {"a": {"b": None}},
            id="dotted_with_none_value",
        ),
        pytest.param(
            {"a.b": [1, 2]},
            {"a": {"b": [1, 2]}},
            id="dotted_with_list_value",
        ),
        # Falsy values as leaves.
        pytest.param(
            {"a.b": False},
            {"a": {"b": False}},
            id="dotted_with_false",
        ),
        pytest.param(
            {"a.b": 0},
            {"a": {"b": 0}},
            id="dotted_with_zero",
        ),
        pytest.param(
            {"a.b": 0.0},
            {"a": {"b": 0.0}},
            id="dotted_with_zero_float",
        ),
        pytest.param(
            {"a.b": ""},
            {"a": {"b": ""}},
            id="dotted_with_empty_string",
        ),
        pytest.param(
            {"a.b": []},
            {"a": {"b": []}},
            id="dotted_with_empty_list",
        ),
        pytest.param(
            {"a.b": ()},
            {"a": {"b": ()}},
            id="dotted_with_empty_tuple",
        ),
        # Truthy values as leaves.
        pytest.param(
            {"a.b": True},
            {"a": {"b": True}},
            id="dotted_with_true",
        ),
        pytest.param(
            {"a.b": 1},
            {"a": {"b": 1}},
            id="dotted_with_one",
        ),
        pytest.param(
            {"a.b": " "},
            {"a": {"b": " "}},
            id="dotted_with_whitespace",
        ),
        # Falsy values at intermediate positions.
        pytest.param(
            {"a": False, "a.b": 2},
            {"a": {"b": 2}},
            id="false_then_dotted",
        ),
        pytest.param(
            {"a": 0, "a.b": 2},
            {"a": {"b": 2}},
            id="zero_then_dotted",
        ),
        pytest.param(
            {"a": "", "a.b": 2},
            {"a": {"b": 2}},
            id="empty_string_then_dotted",
        ),
        pytest.param(
            {"a": [], "a.b": 2},
            {"a": {"b": 2}},
            id="empty_list_then_dotted",
        ),
        # Dotted then falsy plain key.
        pytest.param(
            {"a.b": 2, "a": False},
            {"a": False},
            id="dotted_then_false",
        ),
        pytest.param(
            {"a.b": 2, "a": 0},
            {"a": 0},
            id="dotted_then_zero",
        ),
        # Empty dict merges cleanly (no data loss).
        pytest.param(
            {"a.b": 2, "a": {}},
            {"a": {"b": 2}},
            id="dotted_then_empty_dict",
        ),
    ),
)
def test_expand_dotted_keys_edge_cases(input_conf, expected):
    assert _expand_dotted_keys(input_conf) == expected


@pytest.mark.parametrize(
    ("input_conf", "error_fragment"),
    (
        pytest.param(
            {"a": 1, "a.b": 2},
            "Configuration key 'a.b' conflicts with 'a'",
            id="scalar_then_dotted",
        ),
        pytest.param(
            {"a.b": 2, "a": 1},
            "Configuration key 'a' conflicts with 'a'",
            id="dotted_then_scalar",
        ),
        pytest.param(
            {"a.b.c": 1, "a.b": 2},
            "Configuration key 'a.b' conflicts with 'a.b'",
            id="deep_conflict",
        ),
        pytest.param(
            {"a": None, "a.b": 2},
            "Configuration key 'a.b' conflicts with 'a'",
            id="none_then_dotted",
        ),
    ),
)
def test_expand_dotted_keys_strict_conflict(input_conf, error_fragment):
    """Strict mode raises ValueError on type conflicts."""
    with pytest.raises(ValueError, match=error_fragment):
        _expand_dotted_keys(input_conf, strict=True)


@pytest.mark.parametrize(
    "input_conf",
    (
        pytest.param({"...": 1}, id="only_dots"),
        pytest.param({".a": 1}, id="leading_dot"),
        pytest.param({"a.": 1}, id="trailing_dot"),
    ),
)
def test_expand_dotted_keys_strict_empty_segments(input_conf):
    """Strict mode raises ValueError on dotted keys with empty segments."""
    with pytest.raises(ValueError, match="contains empty segments"):
        _expand_dotted_keys(input_conf, strict=True)


def test_strict_conf_dotted_key_conflict(invoke, create_config):
    """Strict mode rejects configs with dotted-key type conflicts."""

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option(strict=True)
    def strict_cli(dummy_flag):
        echo(f"dummy_flag is {dummy_flag!r}")

    @strict_cli.command
    @option("--int-param", type=int, default=10)
    def subcommand(int_param):
        echo(f"int_parameter is {int_param!r}")

    conf_path = create_config(
        "conflict.json",
        dedent("""\
            {
                "strict-cli": {
                    "subcommand": "not_a_dict",
                    "subcommand.int_param": 3
                }
            }
            """),
    )

    result = invoke(strict_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exception
    assert type(result.exception) is ValueError
    assert "conflicts" in str(result.exception)
    assert result.exit_code == 1
