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
from textwrap import dedent

import click
import pytest

from click_extra import echo
from click_extra.decorators import extra_command, verbose_option, verbosity_option
from click_extra.logging import (
    DEFAULT_LEVEL,
    ExtraFormatter,
    ExtraStreamHandler,
    LogLevel,
    new_extra_logger,
)
from click_extra.pytest import (
    command_decorators,
    default_debug_colored_config,
    default_debug_colored_log_end,
    default_debug_colored_logging,
    default_debug_colored_verbose_log,
    default_debug_colored_version_details,
    default_debug_uncolored_log_end,
    default_debug_uncolored_logging,
    default_debug_uncolored_verbose_log,
)

from .conftest import skip_windows_colors


def test_level_default_order():
    assert tuple((level.name, level.value) for level in LogLevel) == (
        ("CRITICAL", 50),
        ("ERROR", 40),
        ("WARNING", 30),
        ("INFO", 20),
        ("DEBUG", 10),
    )


def test_root_logger_defaults():
    """Check our internal default is aligned to Python's root logger."""
    # Check the root logger is the default logger.
    assert logging.getLogger() is logging.getLogger("root")
    assert logging.getLogger() is logging.root

    # Check root logger's level.
    assert logging.root.getEffectiveLevel() == logging.WARNING
    assert logging.root.level == logging.WARNING
    assert logging.root.level == DEFAULT_LEVEL.value
    assert logging._levelToName[logging.root.level] == "WARNING"
    assert logging._levelToName[logging.root.level] == DEFAULT_LEVEL.name


@pytest.mark.parametrize(
    ("args", "expected_level"),
    (
        # Default level when no option is provided.
        (None, "WARNING"),
        # Test all --verbosity levels.
        (("--verbosity", "CRITICAL"), "CRITICAL"),
        (("--verbosity", "ERROR"), "ERROR"),
        (("--verbosity", "WARNING"), "WARNING"),
        (("--verbosity", "INFO"), "INFO"),
        (("--verbosity", "DEBUG"), "DEBUG"),
        # Repeating -v options increases the default level.
        (("-v",), "INFO"),
        (("--verbose",), "INFO"),
        (("-vv",), "DEBUG"),
        (("-v", "-v"), "DEBUG"),
        (("--verbose", "--verbose"), "DEBUG"),
        (("-vvv",), "DEBUG"),
        (("-v", "-v", "-v"), "DEBUG"),
        (("--verbose", "--verbose", "--verbose"), "DEBUG"),
        (("-vvvvvvvvvvvvvv",), "DEBUG"),
        (("-vv", "-v", "-vvvvvvvvvvv"), "DEBUG"),
        (("-vv", "-v", "--verbose", "-vvvvvvvvvvv"), "DEBUG"),
        # Equivalent levels don't conflicts.
        (("--verbosity", "INFO", "-v"), "INFO"),
        (("--verbosity", "DEBUG", "-vv"), "DEBUG"),
        # -v is higher level and takes precedence.
        (("--verbosity", "CRITICAL", "-v"), "INFO"),
        (("--verbosity", "CRITICAL", "-vv"), "DEBUG"),
        # --verbosity is higher level and takes precedence.
        (("--verbosity", "DEBUG", "-v"), "DEBUG"),
    ),
)
# TODO: test extra_group
def test_integrated_verbosity_options(invoke, args, expected_level):
    @extra_command
    def logging_cli3():
        echo("It works!")

    result = invoke(logging_cli3, args, color=True)
    assert result.exit_code == 0
    assert result.stdout == "It works!\n"
    if expected_level == "DEBUG":
        debug_log = default_debug_colored_logging
        if any(a for a in args if a.startswith("-v") or a == "--verbose"):
            debug_log += default_debug_colored_verbose_log
        debug_log += (
            default_debug_colored_config
            + default_debug_colored_version_details
            + default_debug_colored_log_end
        )
        assert re.fullmatch(debug_log, result.stderr)
    else:
        assert not result.stderr


@pytest.mark.parametrize(
    "args",
    (
        # Long option.
        ("--blah", "DEBUG"),
        # Short option.
        ("-B", "DEBUG"),
        # Duplicate options.
        ("--blah", "DEBUG", "--blah", "DEBUG"),
        ("-B", "DEBUG", "-B", "DEBUG"),
        ("--blah", "DEBUG", "-B", "DEBUG"),
        ("-B", "DEBUG", "--blah", "DEBUG"),
        # Duplicate options with different levels: the last always win.
        ("--blah", "INFO", "-B", "DEBUG"),
        ("-B", "INFO", "--blah", "DEBUG"),
        # Click's argument parser deduplicate options before invoking the
        # callback, so the following cases fails.
        pytest.param(
            ("--blah", "DEBUG", "-B", "INFO"),
            marks=pytest.mark.xfail(reason="Last value of the same option wins"),
        ),
        pytest.param(
            ("-B", "DEBUG", "--blah", "INFO"),
            marks=pytest.mark.xfail(reason="Last value of the same option wins"),
        ),
    ),
)
def test_custom_verbosity_option_name(invoke, args):
    param_names = ("--blah", "-B")

    @click.command
    @verbosity_option(*param_names)
    def awesome_app():
        root_logger = logging.getLogger()
        root_logger.debug("my debug message.")

    result = invoke(awesome_app, args, color=False)
    assert result.exit_code == 0
    assert not result.stdout
    assert re.fullmatch(
        default_debug_uncolored_logging
        + r"debug: my debug message\.\n"
        + default_debug_uncolored_log_end,
        result.stderr,
    )


@pytest.mark.parametrize(
    "args",
    (
        # Short option.
        ("-BB",),
        ("-B", "-B"),
        # Long option.
        ("--blah", "--blah"),
        # Duplicate options.
        ("--blah", "-B"),
        ("-B", "--blah"),
    ),
)
def test_custom_verbose_option_name(invoke, args):
    param_names = ("--blah", "-B")

    @click.command
    @verbose_option(*param_names)
    def awesome_app():
        root_logger = logging.getLogger()
        root_logger.debug("my debug message.")

    result = invoke(awesome_app, args, color=False)
    assert result.exit_code == 0
    assert not result.stdout
    assert re.fullmatch(
        default_debug_uncolored_logging
        + default_debug_uncolored_verbose_log
        + r"debug: my debug message\.\n"
        + default_debug_uncolored_log_end,
        result.stderr,
    )


@pytest.mark.parametrize(
    ("cmd_decorator", "cmd_type"),
    command_decorators(with_types=True),
)
def test_unrecognized_verbosity_level(invoke, cmd_decorator, cmd_type):
    @cmd_decorator
    @verbosity_option
    def logging_cli1():
        echo("It works!")

    # Remove colors to simplify output comparison.
    result = invoke(logging_cli1, "--verbosity", "random", color=False)
    assert result.exit_code == 2
    assert not result.stdout

    group_help = " COMMAND [ARGS]..." if "group" in cmd_type else ""
    assert result.stderr == (
        f"Usage: logging-cli1 [OPTIONS]{group_help}\n"
        "Try 'logging-cli1 --help' for help.\n\n"
        "Error: Invalid value for '--verbosity': "
        "'random' is not one of 'critical', 'error', 'warning', 'info', 'debug'.\n"
    )


@skip_windows_colors
@pytest.mark.parametrize(
    "cmd_decorator",
    # Skip click extra's commands, as verbosity option is already part of the default.
    command_decorators(no_groups=True, no_extra=True),
)
@pytest.mark.parametrize(
    "option_decorator",
    (
        verbosity_option,
        verbosity_option(),
        verbose_option,
        verbose_option(),
    ),
)
@pytest.mark.parametrize(
    ("args", "expected_level"),
    (
        (None, LogLevel.WARNING),
        (("--verbosity", "CRITICAL"), LogLevel.CRITICAL),
        (("--verbosity", "ERROR"), LogLevel.ERROR),
        (("--verbosity", "WARNING"), LogLevel.WARNING),
        (("--verbosity", "INFO"), LogLevel.INFO),
        (("--verbosity", "DEBUG"), LogLevel.DEBUG),
        (("-v",), LogLevel.INFO),
        (("-v", "-v"), LogLevel.DEBUG),
        (("-v", "-v", "-v"), LogLevel.DEBUG),
        (("-v", "-v", "-v", "-v", "-v", "-v"), LogLevel.DEBUG),
    ),
)
def test_standalone_option_default_logger(
    invoke, cmd_decorator, option_decorator, args, expected_level
):
    """Checks:
    - option affect log level
    - the default logger is ``root``
    - the default logger message format
    - level names are colored
    - log level is propagated to all other loggers
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

    logging_option = logging_cli2.params[0]
    if args and not set(logging_option.opts).intersection(args):
        pytest.skip(
            reason=f"Test case for {' '.join(args)!r} "
            f"does not apply to {logging_option}"
        )

    result = invoke(logging_cli2, args, color=True)
    assert result.exit_code == 0
    assert result.stdout == "It works!\n"

    root_logger = logging.getLogger()

    assert root_logger is logging.getLogger("root")
    assert root_logger is logging.root

    assert root_logger.getEffectiveLevel() == logging.WARNING
    assert root_logger.level == DEFAULT_LEVEL

    assert root_logger.parent is None
    assert root_logger.propagate is True

    assert len(root_logger.handlers) == 1
    assert isinstance(root_logger.handlers[0], ExtraStreamHandler)
    assert isinstance(root_logger.handlers[0].formatter, ExtraFormatter)

    messages = {
        LogLevel.DEBUG: (
            r"\x1b\[34mdebug\x1b\[0m: my random message.\n"
            r"\x1b\[34mdebug\x1b\[0m: my debug message.\n"
        ),
        LogLevel.INFO: r"info: my info message.\n",
        LogLevel.WARNING: r"\x1b\[33mwarning\x1b\[0m: my warning message.\n",
        LogLevel.ERROR: r"\x1b\[31merror\x1b\[0m: my error message.\n",
        LogLevel.CRITICAL: r"\x1b\[31m\x1b\[1mcritical\x1b\[0m: my critical message.\n",
    }

    log_records = r"".join([
        line for level, line in messages.items() if level >= expected_level
    ])

    if expected_level == LogLevel.DEBUG:
        log_start = default_debug_colored_logging
        if "-v" in args:
            log_start += default_debug_colored_verbose_log
        log_records = log_start + log_records + default_debug_colored_log_end
    assert re.fullmatch(log_records, result.stderr)


@pytest.mark.parametrize(
    "logger_param",
    (
        logging.getLogger("awesome_app"),
        "awesome_app",
        new_extra_logger("awesome_app"),
    ),
)
@pytest.mark.parametrize("params", (("--verbosity", "DEBUG"), None))
def test_default_logger_param(invoke, logger_param, params):
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
        assert result.stderr == dedent("""\
            debug: Set <Logger click_extra (DEBUG)> to DEBUG.
            debug: Set <Logger awesome_app (DEBUG)> to DEBUG.
            debug: Awesome App has started.
            debug: Reset <Logger awesome_app (DEBUG)> to WARNING.
            debug: Reset <Logger click_extra (DEBUG)> to WARNING.
            """)
    else:
        assert not result.stderr


def test_new_extra_logger_name_passing(invoke):
    """Test extra logger with custom format, passed to the option by its name."""
    new_extra_logger(
        name="my_logger",
        format="{levelname} | {name} | {message}",
    )

    @click.command
    @verbosity_option(default_logger="my_logger")
    def logger_as_name():
        # Call the root logger directly.
        logging.warning("Root logger warning")
        logging.debug("Root logger debug")
        logging.info("Root logger info")
        # Fetch our custom logger object.
        my_logger = logging.getLogger("my_logger")
        my_logger.warning("My logger warning")
        my_logger.debug("My logger debug")
        my_logger.info("My logger info")

    result = invoke(logger_as_name, color=False)
    assert result.exit_code == 0
    assert result.output == dedent("""\
        warning: Root logger warning
        warning | my_logger | My logger warning
        """)

    result = invoke(logger_as_name, ("--verbosity", "DEBUG"), color=False)
    assert result.exit_code == 0
    # The --verbosity option only affects the logger it is attached to.
    assert result.output == dedent("""\
        debug: Set <Logger click_extra (DEBUG)> to DEBUG.
        debug: Set <Logger my_logger (DEBUG)> to DEBUG.
        warning: Root logger warning
        warning | my_logger | My logger warning
        debug | my_logger | My logger debug
        info | my_logger | My logger info
        debug: Reset <Logger my_logger (DEBUG)> to WARNING.
        debug: Reset <Logger click_extra (DEBUG)> to WARNING.
        """)


def test_new_extra_logger_object_passing(invoke):
    """Test extra logger with custom format, passed as an object to the option."""
    custom_logger = new_extra_logger(
        name="my_logger",
        format="{levelname} | {name} | {message}",
    )

    @click.command
    @verbosity_option(default_logger=custom_logger)
    def logger_as_object():
        # Call the root logger directly.
        logging.warning("Root logger warning")
        logging.debug("Root logger debug")
        logging.info("Root logger info")
        # Use our custom logger object.
        custom_logger.warning("Logger object warning")
        custom_logger.debug("Logger object debug")
        custom_logger.info("Logger object info")

    result = invoke(logger_as_object, color=False)
    assert result.exit_code == 0
    assert result.output == dedent("""\
        warning: Root logger warning
        warning | my_logger | Logger object warning
        """)

    result = invoke(logger_as_object, ("--verbosity", "DEBUG"), color=False)
    assert result.exit_code == 0
    assert result.output == dedent("""\
        debug: Set <Logger click_extra (DEBUG)> to DEBUG.
        debug: Set <Logger my_logger (DEBUG)> to DEBUG.
        warning: Root logger warning
        warning | my_logger | Logger object warning
        debug | my_logger | Logger object debug
        info | my_logger | Logger object info
        debug: Reset <Logger my_logger (DEBUG)> to WARNING.
        debug: Reset <Logger click_extra (DEBUG)> to WARNING.
        """)


@pytest.mark.skip(reason="Test is flacky because of the logger's propagation.")
def test_new_extra_logger_root_config(invoke):
    """Modify the root logger via ``new_extra_logger()``"""

    root_logger = new_extra_logger(format="{levelname} | {name} | {message}")

    @click.command
    @verbosity_option(default_logger=root_logger)
    def custom_root_logger_cli():
        # Call the root logger directly.
        logging.warning("Root logger warning")
        logging.debug("Root logger debug")
        logging.info("Root logger info")
        # Create a new custom logger object.
        my_logger = logging.getLogger("my_logger")
        my_logger.warning("My logger warning")
        my_logger.debug("My logger debug")
        my_logger.info("My logger info")

    result = invoke(custom_root_logger_cli, color=False)
    assert result.exit_code == 0
    assert result.output == dedent("""\
        warning | root | Root logger warning
        warning | my_logger | My logger warning
        """)

    result = invoke(custom_root_logger_cli, ("--verbosity", "DEBUG"), color=False)
    assert result.exit_code == 0
    assert result.output == dedent("""\
        debug | click_extra | Set <Logger click_extra (DEBUG)> to DEBUG.
        debug | click_extra | Set <RootLogger root (DEBUG)> to DEBUG.
        warning | root | Root logger warning
        debug | root | Root logger debug
        info | root | Root logger info
        warning | my_logger | My logger warning
        debug | click_extra | Reset <RootLogger root (DEBUG)> to WARNING.
        debug | click_extra | Reset <Logger click_extra (DEBUG)> to WARNING.
        """)


def test_logger_propagation(invoke):
    new_extra_logger(
        name="my_logger",
        propagate=True,
        format="{levelname} | {name} | {message}",
    )

    @click.command
    @verbosity_option(default_logger="my_logger")
    def logger_as_name():
        # Call the root logger directly.
        logging.warning("Root logger warning")
        logging.debug("Root logger debug")
        logging.info("Root logger info")
        # Fetch our custom logger object.
        my_logger = logging.getLogger("my_logger")
        my_logger.warning("My logger warning")
        my_logger.debug("My logger debug")
        my_logger.info("My logger info")

    result = invoke(logger_as_name, color=False)
    assert result.exit_code == 0
    # my_logger is now breaking its inheritance from the root logger.
    assert result.output == dedent("""\
        warning: Root logger warning
        warning | my_logger | My logger warning
        warning: My logger warning
        """)

    result = invoke(logger_as_name, ("--verbosity", "DEBUG"), color=False)
    assert result.exit_code == 0
    # The root logger is unaffected by the --verbosity option.
    assert result.output == dedent("""\
        debug: Set <Logger click_extra (DEBUG)> to DEBUG.
        debug: Set <Logger my_logger (DEBUG)> to DEBUG.
        warning: Root logger warning
        warning | my_logger | My logger warning
        warning: My logger warning
        debug | my_logger | My logger debug
        debug: My logger debug
        info | my_logger | My logger info
        info: My logger info
        debug: Reset <Logger my_logger (DEBUG)> to WARNING.
        debug: Reset <Logger click_extra (DEBUG)> to WARNING.
        """)
