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
import random
import re

import click
import pytest
from pytest_cases import parametrize

from click_extra import echo
from click_extra.decorators import extra_command, verbosity_option
from click_extra.logging import DEFAULT_LEVEL, LOG_LEVELS
from click_extra.pytest import (
    command_decorators,
    default_debug_colored_log_end,
    default_debug_colored_log_start,
    default_debug_colored_logging,
    default_debug_uncolored_log_end,
    default_debug_uncolored_logging,
)

from .conftest import skip_windows_colors


def test_level_default_order():
    assert tuple(LOG_LEVELS) == ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")


def test_root_logger_defaults():
    """Check our internal default is aligned to Python's root logger."""
    # Check the root logger is the default logger, and that getLogger is
    # properly patched on Python 3.8.
    assert logging.getLogger() is logging.getLogger("root")
    assert logging.getLogger() is logging.root

    # Check root logger's level.
    assert logging.root.getEffectiveLevel() == logging.WARNING
    assert logging._levelToName[logging.root.level] == "WARNING"
    assert logging.root.level == DEFAULT_LEVEL


@pytest.mark.parametrize(
    ("cmd_decorator", "cmd_type"),
    command_decorators(with_types=True),
)
def test_unrecognized_verbosity(invoke, cmd_decorator, cmd_type):
    @cmd_decorator
    @verbosity_option
    def logging_cli1():
        echo("It works!")

    # Remove colors to simplify output comparison.
    result = invoke(logging_cli1, "--verbosity", "random", color=False)
    assert result.exit_code == 2
    assert not result.stdout

    group_help = " COMMAND [ARGS]..." if "group" in cmd_type else ""
    extra_suggest = (
        "Try 'logging-cli1 --help' for help.\n" if "extra" not in cmd_type else ""
    )
    assert result.stderr == (
        f"Usage: logging-cli1 [OPTIONS]{group_help}\n"
        f"{extra_suggest}\n"
        "Error: Invalid value for '--verbosity' / '-v': "
        "'random' is not one of 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'.\n"
    )


@skip_windows_colors
@pytest.mark.parametrize(
    "cmd_decorator",
    # Skip click extra's commands, as verbosity option is already part of the default.
    command_decorators(no_groups=True, no_extra=True),
)
@parametrize("option_decorator", (verbosity_option, verbosity_option()))
@pytest.mark.parametrize("level", LOG_LEVELS.keys())
def test_default_root_logger(invoke, cmd_decorator, option_decorator, level):
    """Checks:
    - the default logger is ``<root>``
    - the default logger message format
    - level names are colored
    - log level is propagated to all other loggers.
    """

    @cmd_decorator
    @option_decorator
    def logging_cli2():
        echo("It works!")

        random_logger = logging.getLogger(
            f"random_logger_{random.randrange(10000, 99999)}",
        )
        random_logger.debug("my random message.")

        logging.debug("my debug message.")
        logging.info("my info message.")
        logging.warning("my warning message.")
        logging.error("my error message.")
        logging.critical("my critical message.")

    result = invoke(logging_cli2, "--verbosity", level, color=True)
    assert result.exit_code == 0
    assert result.stdout == "It works!\n"

    messages = (
        (
            rf"{default_debug_colored_logging}"
            r"\x1b\[34mdebug\x1b\[0m: my random message.\n"
            r"\x1b\[34mdebug\x1b\[0m: my debug message.\n"
        ),
        r"info: my info message.\n",
        r"\x1b\[33mwarning\x1b\[0m: my warning message.\n",
        r"\x1b\[31merror\x1b\[0m: my error message.\n",
        r"\x1b\[31m\x1b\[1mcritical\x1b\[0m: my critical message.\n",
    )
    level_index = {index: level for level, index in enumerate(LOG_LEVELS)}[level]
    log_records = r"".join(messages[-level_index - 1 :])

    if level == "DEBUG":
        log_records += default_debug_colored_log_end
    assert re.fullmatch(log_records, result.stderr)


@skip_windows_colors
@pytest.mark.parametrize("level", LOG_LEVELS.keys())
# TODO: test extra_group
def test_integrated_verbosity_option(invoke, level):
    @extra_command
    def logging_cli3():
        echo("It works!")

    result = invoke(logging_cli3, "--verbosity", level, color=True)
    assert result.exit_code == 0
    assert result.stdout == "It works!\n"
    if level == "DEBUG":
        assert re.fullmatch(
            default_debug_colored_log_start + default_debug_colored_log_end,
            result.stderr,
        )
    else:
        assert not result.stderr


@pytest.mark.parametrize(
    "logger_param",
    (logging.getLogger("awesome_app"), "awesome_app"),
)
@pytest.mark.parametrize("params", (("--verbosity", "DEBUG"), None))
def test_custom_logger_param(invoke, logger_param, params):
    """Passing a logger instance or name to the ``default_logger`` parameter works."""

    @click.command
    @verbosity_option(default_logger=logger_param)
    def awesome_app():
        echo("Starting Awesome App...")
        logging.getLogger("awesome_app").debug("Awesome App has started.")

    result = invoke(awesome_app, params, color=False)
    assert result.exit_code == 0
    assert result.stdout == "Starting Awesome App...\n"
    if params:
        assert re.fullmatch(
            (
                r"debug: Set <Logger click_extra \(DEBUG\)> to DEBUG.\n"
                r"debug: Set <Logger awesome_app \(DEBUG\)> to DEBUG.\n"
                r"debug: Awesome App has started\.\n"
                r"debug: Reset <Logger awesome_app \(DEBUG\)> to WARNING.\n"
                r"debug: Reset <Logger click_extra \(DEBUG\)> to WARNING.\n"
            ),
            result.stderr,
        )
    else:
        assert not result.stderr


def test_custom_option_name(invoke):
    param_names = ("--blah", "-B")

    @click.command
    @verbosity_option(*param_names)
    def awesome_app():
        root_logger = logging.getLogger()
        root_logger.debug("my debug message.")

    for name in param_names:
        result = invoke(awesome_app, name, "DEBUG", color=False)
        assert result.exit_code == 0
        assert not result.stdout
        assert re.fullmatch(
            (
                rf"{default_debug_uncolored_logging}"
                r"debug: my debug message\.\n"
                rf"{default_debug_uncolored_log_end}"
            ),
            result.stderr,
        )
