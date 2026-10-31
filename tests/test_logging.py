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

import gc
import logging
import random
import sys
from subprocess import run
from textwrap import dedent

import click
import pytest

from click_extra import (
    LogLevel,
    Spinner,
    VerbosityOption,
    command,
    echo,
    group,
    quiet_option,
    strip_ansi,
    timer_option,
    verbose_option,
    verbosity_option,
)
from click_extra.logging import (
    _INVOCATION_HOLDERS,
    DEFAULT_LEVEL,
    Formatter,
    StreamHandler,
    basicConfig,
    new_logger,
)
from click_extra.pytest import (
    command_decorators,
    default_debug_colored_config,
    default_debug_colored_log_end,
    default_debug_colored_logging,
    default_debug_colored_quiet_log,
    default_debug_colored_verbose_log,
    default_debug_colored_version_details,
    default_debug_uncolored_log_end,
    default_debug_uncolored_logging,
    default_debug_uncolored_verbose_log,
)

from .conftest import skip_windows_colors

CUSTOM_FORMAT = "{levelname} | {name} | {message}"
"""A format to tell a logger set up on purpose from the default of Click Extra."""


def run_handlers():
    """The handlers of Click Extra attached to the root logger right now."""
    return [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, StreamHandler)
    ]


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
        # -q decreases the level, mirroring -v.
        (("-q",), "ERROR"),
        (("--quiet",), "ERROR"),
        (("-qq",), "CRITICAL"),
        (("-q", "-q"), "CRITICAL"),
        (("--quiet", "--quiet"), "CRITICAL"),
        (("-qqq",), "CRITICAL"),
        (("-qqqqqqqqqqqqqq",), "CRITICAL"),
        # -v and -q form a signed counter and cancel out.
        (("-v", "-q"), "WARNING"),
        (("-q", "-v"), "WARNING"),
        (("-vv", "-q"), "INFO"),
        (("-v", "-qq"), "ERROR"),
        (("-vvv", "-q"), "DEBUG"),
        # -q reconciles with --verbosity: the quietest of the two wins, and the
        # counter still starts from the default WARNING.
        (("--verbosity", "DEBUG", "-q"), "ERROR"),
        (("--verbosity", "CRITICAL", "-q"), "CRITICAL"),
        (("--verbosity", "INFO", "-qq"), "CRITICAL"),
        (("--verbosity", "WARNING", "-q"), "ERROR"),
        (("--verbosity", "ERROR", "-q"), "ERROR"),
        # Cancelling counter falls back to the explicit --verbosity value.
        (("--verbosity", "DEBUG", "-v", "-q"), "DEBUG"),
    ),
)
@pytest.mark.parametrize(
    ("cmd_decorator", "cmd_type"),
    # Only Click Extra's own decorators carry the verbosity options by default,
    # which is what this test drives.
    command_decorators(no_click=True, no_cloup=True, with_types=True),
)
def test_integrated_verbosity_options(
    invoke, cmd_decorator, cmd_type, args, expected_level, assert_output_regex
):
    if "group" in cmd_type:

        @cmd_decorator
        def logging_cli3():
            pass

        # Parenthesized: the group is Cloup-based, which rejects the naked form.
        @logging_cli3.command()
        def worker():
            echo("It works!")

        # The group's own options are parsed before the subcommand name, which
        # is where a reader would type them too.
        cli_args = (*(args or ()), "worker")

    else:

        @cmd_decorator
        def logging_cli3():
            echo("It works!")

        cli_args = args

    result = invoke(logging_cli3, cli_args, color=True)
    assert result.stdout == "It works!\n"
    if expected_level == "DEBUG":
        debug_log = default_debug_colored_logging
        if any(a for a in args if a.startswith("-v") or a == "--verbose"):
            debug_log += default_debug_colored_verbose_log
        if any(a for a in args if a.startswith("-q") or a == "--quiet"):
            debug_log += default_debug_colored_quiet_log
        debug_log += (
            default_debug_colored_config
            + default_debug_colored_version_details
            + default_debug_colored_log_end
        )
        assert_output_regex(result.stderr, debug_log)
    else:
        assert not result.stderr
    assert result.exit_code == 0


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
def test_custom_verbosity_option_name(invoke, args, assert_output_regex):
    param_names = ("--blah", "-B")

    @click.command
    @verbosity_option(*param_names)
    def awesome_app():
        root_logger = logging.getLogger()
        root_logger.debug("my debug message.")

    result = invoke(awesome_app, args, color=False)
    assert not result.stdout
    assert_output_regex(
        result.stderr,
        default_debug_uncolored_logging
        + r"debug: my debug message\.\n"
        + default_debug_uncolored_log_end,
    )
    assert result.exit_code == 0


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
def test_custom_verbose_option_name(invoke, args, assert_output_regex):
    param_names = ("--blah", "-B")

    @click.command
    @verbose_option(*param_names)
    def awesome_app():
        root_logger = logging.getLogger()
        root_logger.debug("my debug message.")

    result = invoke(awesome_app, args, color=False)
    assert not result.stdout
    assert_output_regex(
        result.stderr,
        default_debug_uncolored_logging
        + default_debug_uncolored_verbose_log
        + r"debug: my debug message\.\n"
        + default_debug_uncolored_log_end,
    )
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "args",
    (
        # Short option.
        ("-B",),
        # Long option.
        ("--blah",),
    ),
)
def test_custom_quiet_option_name(invoke, args):
    param_names = ("--blah", "-B")

    @click.command
    @quiet_option(*param_names)
    def awesome_app():
        root_logger = logging.getLogger()
        root_logger.warning("my warning message.")
        root_logger.error("my error message.")

    result = invoke(awesome_app, args, color=False)
    assert not result.stdout
    # A single -q lowers the level one step, from WARNING to ERROR, so the warning
    # is suppressed while the error is still shown.
    assert result.stderr == "error: my error message.\n"
    assert result.exit_code == 0


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
    assert not result.stdout

    group_help = " COMMAND [ARGS]..." if "group" in cmd_type else ""
    assert result.stderr == (
        f"Usage: logging-cli1 [OPTIONS]{group_help}\n"
        "Try 'logging-cli1 --help' for help.\n\n"
        "Error: Invalid value for '--verbosity': "
        "'random' is not one of 'critical', 'error', 'warning', 'info', 'debug'.\n"
    )

    assert result.exit_code == 2


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
        quiet_option,
        quiet_option(),
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
        (("-q",), LogLevel.ERROR),
        (("-q", "-q"), LogLevel.CRITICAL),
        (("-q", "-q", "-q"), LogLevel.CRITICAL),
    ),
)
def test_standalone_option_default_logger(
    invoke, cmd_decorator, option_decorator, args, expected_level, assert_output_regex
):
    """Checks:
    - option affect log level
    - the default logger is ``root``
    - the default logger message format
    - level names are colored
    - log level is propagated to all other loggers
    """
    seen_handlers = []

    @cmd_decorator
    @option_decorator
    def logging_cli2():
        echo("It works!")
        seen_handlers.extend(run_handlers())

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
    assert result.stdout == "It works!\n"

    root_logger = logging.getLogger()

    assert root_logger is logging.getLogger("root")
    assert root_logger is logging.root

    assert root_logger.getEffectiveLevel() == logging.WARNING
    assert root_logger.level == DEFAULT_LEVEL

    assert root_logger.parent is None
    assert root_logger.propagate is True

    # The run printed its records through one handler of Click Extra.
    assert len(seen_handlers) == 1
    assert isinstance(seen_handlers[0].formatter, Formatter)

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
    assert_output_regex(result.stderr, log_records)

    assert result.exit_code == 0


@pytest.mark.parametrize(
    "logger_param",
    (
        logging.getLogger("awesome_app"),
        "awesome_app",
        new_logger("awesome_app"),
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
    assert result.exit_code == 0


def test_new_logger_name_passing(invoke):
    """Test extra logger with custom format, passed to the option by its name."""
    new_logger(
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
    assert result.output == dedent("""\
        warning: Root logger warning
        warning | my_logger | My logger warning
        """)
    assert result.exit_code == 0

    result = invoke(logger_as_name, ("--verbosity", "DEBUG"), color=False)
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
    assert result.exit_code == 0


def test_new_logger_object_passing(invoke):
    """Test extra logger with custom format, passed as an object to the option."""
    custom_logger = new_logger(
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
    assert result.output == dedent("""\
        warning: Root logger warning
        warning | my_logger | Logger object warning
        """)
    assert result.exit_code == 0

    result = invoke(logger_as_object, ("--verbosity", "DEBUG"), color=False)
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
    assert result.exit_code == 0


@pytest.fixture
def restored_root_logger():
    """Put the root logger back the way the test found it.

    ``new_logger()`` naming no logger reconfigures the process-wide root one
    through ``basicConfig(force=True)``, which drops whatever handlers were
    already attached. Nothing in ``logging`` undoes that, so a test doing it
    once decides how every later test in the same worker renders: leaving the
    handler behind is what made ``test_logger_propagation`` fail whenever this
    module's root-logger test ran before it.

    A run of a plain Click command that failed while parsing keeps its hold on
    the handler of Click Extra until its context is collected. Collecting first
    keeps that handler out of the saved list, which would otherwise attach it
    again once the test is over.
    """
    gc.collect()
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        yield root
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


class RecordingHandler(logging.Handler):
    """Stand-in for the handler of an application: keeps the messages it receives."""

    def __init__(self):
        super().__init__()
        self.messages = []
        self.closed = False

    def emit(self, record):
        self.messages.append(record.getMessage())

    def close(self):
        self.closed = True
        super().close()


@pytest.fixture
def app_handler(restored_root_logger):
    """A handler attached to the root logger before any command is defined.

    This is the state an application leaves the root logger in before it imports
    a CLI, and the one pytest leaves it in with its own capture handlers.
    """
    handler = RecordingHandler()
    restored_root_logger.addHandler(handler)
    return handler


def test_new_logger_root_config(invoke, restored_root_logger):
    """Modify the root logger via ``new_logger()``"""

    root_logger = new_logger(format="{levelname} | {name} | {message}")

    @click.command
    @verbosity_option(default_logger=root_logger)
    def custom_root_logger_cli():
        # Call the root logger directly.
        logging.warning("Root logger warning")
        logging.debug("Root logger debug")
        logging.info("Root logger info")
        # A logger this module configures nowhere else, so it is always the
        # bare child the assertions below describe: one with no handler and no
        # level of its own, inheriting both from the root logger just
        # reconfigured. Reusing a name a sibling test passed to `new_logger()`
        # would instead fetch that logger, carrying its handler and its
        # `propagate=False`, and the output would depend on test order.
        inherited_logger = logging.getLogger("inherited_logger")
        inherited_logger.warning("Inherited logger warning")
        inherited_logger.debug("Inherited logger debug")
        inherited_logger.info("Inherited logger info")

    result = invoke(custom_root_logger_cli, color=False)
    assert result.output == dedent("""\
        warning | root | Root logger warning
        warning | inherited_logger | Inherited logger warning
        """)
    assert result.exit_code == 0

    result = invoke(custom_root_logger_cli, ("--verbosity", "DEBUG"), color=False)
    # The internal messages are emitted by `click_extra.logging` and reach the
    # root handler this test installed, so they are rendered with its format,
    # under the name of the module that logged them.
    assert result.output == dedent("""\
        debug | click_extra.logging | Set <Logger click_extra (DEBUG)> to DEBUG.
        debug | click_extra.logging | Set <RootLogger root (DEBUG)> to DEBUG.
        warning | root | Root logger warning
        debug | root | Root logger debug
        info | root | Root logger info
        warning | inherited_logger | Inherited logger warning
        debug | inherited_logger | Inherited logger debug
        info | inherited_logger | Inherited logger info
        debug | click_extra.logging | Reset <RootLogger root (DEBUG)> to WARNING.
        debug | click_extra.logging | Reset <Logger click_extra (DEBUG)> to WARNING.
        """)
    assert result.exit_code == 0


def test_logger_propagation(invoke):
    new_logger(
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
    # my_logger is now breaking its inheritance from the root logger.
    assert result.output == dedent("""\
        warning: Root logger warning
        warning | my_logger | My logger warning
        warning: My logger warning
        """)
    assert result.exit_code == 0

    result = invoke(logger_as_name, ("--verbosity", "DEBUG"), color=False)
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
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "cmd_decorator",
    # Only Click Extra's own decorators carry the verbosity options by default.
    command_decorators(no_click=True, no_cloup=True),
)
def test_decorating_a_command_leaves_the_root_logger_alone(cmd_decorator, app_handler):
    """Defining a command changes neither the handlers nor the level of ``root``.

    A command is defined when its module is imported: the handlers found there
    belong to whoever imports it.
    """
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level

    @cmd_decorator
    def orchard():
        pass

    assert root.handlers == handlers
    assert root.level == level
    assert not app_handler.closed


def test_unregistered_logger_name_is_set_up_without_the_root_logger(app_handler):
    """A name unknown to ``logging`` gets a logger of its own when the option is
    built. The root logger stays out of it."""
    root = logging.getLogger()
    handlers = root.handlers[:]
    assert "vineyard" not in logging.Logger.manager.loggerDict

    @click.command
    @verbosity_option(default_logger="vineyard")
    def orchard():
        pass

    assert root.handlers == handlers
    vineyard = logging.getLogger("vineyard")
    assert vineyard.propagate is False
    (handler,) = vineyard.handlers
    assert isinstance(handler, StreamHandler)
    assert isinstance(handler.formatter, Formatter)


def extra_command(body):
    """A Click Extra command, which carries the verbosity options by default."""

    @command
    def orchard():
        body()

    return orchard, ()


def extra_group(body):
    """A Click Extra group: its subcommand carries the verbosity options too."""

    @group
    def farm():
        pass

    # Parenthesized: the group is Cloup-based, which rejects the naked form.
    @farm.command()
    def orchard():
        body()

    return farm, ("orchard",)


def click_command(body):
    """A plain Click command borrowing the verbosity option."""

    @click.command
    @verbosity_option
    def orchard():
        body()

    return orchard, ()


def click_command_with_its_own_logger(body):
    """A plain Click command whose verbosity option sets a logger of its own."""

    @click.command
    @verbosity_option(default_logger=logging.getLogger("greenhouse"))
    def orchard():
        body()

    return orchard, ()


def click_command_without_verbosity(body):
    """A plain Click command borrowing an option other than the verbosity ones."""

    @click.command
    @timer_option
    def orchard():
        body()

    return orchard, ()


@pytest.mark.parametrize(
    "build",
    (
        extra_command,
        extra_group,
        click_command,
        click_command_with_its_own_logger,
        click_command_without_verbosity,
    ),
)
def test_run_adds_one_handler_beside_the_others(invoke, app_handler, build):
    """A run prints through one handler of Click Extra, added beside the handlers
    already on the root logger, and gone once the run is over.

    The handler of the application stays attached all along, and receives the
    record too: a console handler there prints it a second time.
    """
    root = logging.getLogger()
    handlers = root.handlers[:]
    during = []

    def body():
        during.append(root.handlers[:])
        logging.getLogger("orchard").warning("apples are ripe")

    cli, args = build(body)
    assert root.handlers == handlers

    result = invoke(cli, *args, color=False)
    assert result.exit_code == 0
    assert result.stderr == "warning: apples are ripe\n"

    (run_time_handlers,) = during
    (lent,) = [h for h in run_time_handlers if h not in handlers]
    assert isinstance(lent, StreamHandler)
    assert isinstance(lent.formatter, Formatter)
    # Every other handler stayed in place, in the same order.
    assert [h for h in run_time_handlers if h is not lent] == handlers

    assert app_handler.messages == ["apples are ripe"]
    assert not app_handler.closed
    assert root.handlers == handlers


def test_each_run_gets_the_handler(invoke, app_handler):
    """The handler leaves with a run, and the next run gets one again."""
    root = logging.getLogger()
    handlers = root.handlers[:]

    @command
    def orchard():
        logging.getLogger("orchard").warning("pears are ripe")

    for _ in range(2):
        result = invoke(orchard, color=False)
        assert result.exit_code == 0
        assert result.stderr == "warning: pears are ripe\n"
        assert root.handlers == handlers

    assert app_handler.messages == ["pears are ripe", "pears are ripe"]


def test_record_of_an_earlier_option_is_printed(invoke, app_handler):
    """The handler is attached before Click processes any option, so a record
    emitted by an option processed ahead of the verbosity ones is printed."""

    def announce(ctx, param, value):
        if value:
            logging.getLogger("orchard").warning("plums are ripe")

    @click.command
    @click.option(
        "--announce",
        is_flag=True,
        is_eager=True,
        expose_value=False,
        callback=announce,
    )
    @verbosity_option
    def orchard():
        pass

    # An eager option typed on the command line is processed before the eager
    # options left out of it.
    result = invoke(orchard, "--announce", color=False)
    assert result.exit_code == 0
    assert result.stderr == "warning: plums are ripe\n"


def test_record_after_a_run_is_not_printed(invoke, app_handler, capsys):
    """Once a run is over, Click Extra prints nothing of what the process logs."""

    @command
    def orchard():
        pass

    result = invoke(orchard, color=False)
    assert result.exit_code == 0
    capsys.readouterr()

    logging.getLogger("orchard").warning("quinces are ripe")
    assert not capsys.readouterr().err
    assert app_handler.messages == ["quinces are ripe"]


def test_caplog_captures_the_records_of_a_command_defined_in_a_test(invoke, caplog):
    """pytest attaches its capture handlers to the root logger before the test
    body runs: a command defined in that body must leave them in place."""

    @command
    def orchard():
        logging.getLogger("orchard").warning("melons are ripe")

    result = invoke(orchard, color=False)
    assert result.exit_code == 0
    assert result.stderr == "warning: melons are ripe\n"
    assert "melons are ripe" in caplog.text


def test_file_handler_of_the_root_logger_keeps_writing(
    invoke, restored_root_logger, tmp_path
):
    """No handler of the root logger is closed, at any point.

    A file handler opened in ``w`` mode never opens its file again once closed,
    which is the mode of the one behind pytest's ``--log-file``.
    """
    log_file = tmp_path / "harvest.log"
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    restored_root_logger.addHandler(file_handler)
    orchard_logger = logging.getLogger("orchard")
    try:
        orchard_logger.warning("before the command")

        @command
        def orchard():
            orchard_logger.warning("during the run")

        result = invoke(orchard, color=False)
        assert result.exit_code == 0
        orchard_logger.warning("after the run")
    finally:
        file_handler.close()

    assert log_file.read_text(encoding="utf-8").splitlines() == [
        "before the command",
        "during the run",
        "after the run",
    ]


@pytest.mark.parametrize(
    ("args", "exit_code"),
    (
        pytest.param((), 0, id="return"),
        pytest.param(("--help",), 0, id="help"),
        pytest.param(("--version",), 0, id="version"),
        # The two runs below fail while parsing: Click never closes their context.
        pytest.param(("--no-such-option",), 2, id="unknown-option"),
        pytest.param(("--baskets", "many"), 2, id="invalid-value"),
        pytest.param(("--end", "raise"), 1, id="exception"),
        pytest.param(("--end", "exit"), 3, id="exit"),
        pytest.param(("--end", "abort"), 1, id="abort"),
    ),
)
def test_handler_leaves_however_the_run_ends(invoke, app_handler, args, exit_code):
    """A Click Extra command gives the handler back the moment its run ends,
    whatever the run ends on."""
    root = logging.getLogger()
    handlers = root.handlers[:]

    @command
    @click.option("--baskets", type=int)
    @click.option("--end", default="return")
    @click.pass_context
    def orchard(ctx, baskets, end):
        if end == "raise":
            raise RuntimeError("frost")
        if end == "exit":
            ctx.exit(3)
        if end == "abort":
            raise click.Abort

    result = invoke(orchard, *args, color=False)
    assert result.exit_code == exit_code
    assert root.handlers == handlers


def test_failed_run_of_a_click_command_gives_the_handler_back_when_collected(
    invoke, app_handler
):
    """A plain Click command has no hook on a run that fails while parsing: the
    handler leaves once Python collects the context of that run."""
    root = logging.getLogger()
    handlers = root.handlers[:]

    @click.command
    @verbosity_option
    @click.option("--baskets", type=int)
    def orchard(baskets):
        pass

    result = invoke(orchard, "--baskets", "many", color=False)
    assert result.exit_code == 2

    del result
    gc.collect()
    assert root.handlers == handlers


def test_run_keeps_its_handler_when_a_failed_run_is_collected(invoke, app_handler):
    """The context of a failed run may be collected in the middle of a later run,
    which then still needs the handler they share."""
    root = logging.getLogger()
    handlers = root.handlers[:]
    contexts = []
    holders = []

    def keep_context(ctx, param, value):
        contexts.append(ctx)

    @click.command
    @verbosity_option
    @click.option(
        "--keep",
        is_flag=True,
        is_eager=True,
        expose_value=False,
        callback=keep_context,
    )
    @click.option("--baskets", type=int, expose_value=False)
    def orchard():
        holders.append(len(_INVOCATION_HOLDERS))
        contexts.clear()
        gc.collect()
        holders.append(len(_INVOCATION_HOLDERS))
        logging.getLogger("orchard").warning("figs are ripe")

    # The eager option keeps the context of the run, which then fails on the
    # value of the other one.
    failed = invoke(orchard, "--baskets", "many", color=False)
    assert failed.exit_code == 2
    del failed

    result = invoke(orchard, color=False)
    assert result.exit_code == 0
    # The failed run let go of the handler in the middle of this run.
    assert holders[0] - holders[1] == 1
    assert result.stderr == "warning: figs are ripe\n"
    assert root.handlers == handlers


def test_failed_run_collected_while_a_record_is_handled(invoke, restored_root_logger):
    """The context of a failed run may be collected while the `root` logger hands
    a record to its handlers: the handlers after the one of that run still get it.
    """
    contexts = []

    def keep_context(ctx, param, value):
        contexts.append(ctx)

    @click.command
    @verbosity_option
    @click.option(
        "--keep",
        is_flag=True,
        is_eager=True,
        expose_value=False,
        callback=keep_context,
    )
    @click.option("--baskets", type=int, expose_value=False)
    def orchard():
        pass

    # The failed run keeps its handler on the root logger, as long as its
    # context lives.
    failed = invoke(orchard, "--baskets", "many", color=False)
    assert failed.exit_code == 2
    del failed
    held = len(_INVOCATION_HOLDERS)

    class CollectingHandler(logging.Handler):
        """Lets the context of the failed run go, and collects it."""

        def emit(self, record):
            contexts.clear()
            gc.collect()

    late = RecordingHandler()
    restored_root_logger.addHandler(CollectingHandler())
    restored_root_logger.addHandler(late)

    logging.getLogger("orchard").warning("figs are ripe")

    # The failed run let go of its handler in the middle of the record.
    assert len(_INVOCATION_HOLDERS) == held - 1
    assert late.messages == ["figs are ripe"]


@pytest.mark.parametrize(
    "inner_args",
    (
        pytest.param((), id="inner-run-returns"),
        # The inner run fails while parsing, once it holds the handler.
        pytest.param(("--no-such-option",), id="inner-run-fails"),
    ),
)
def test_nested_runs_share_one_handler(invoke, app_handler, inner_args):
    """A run started from within another one prints through the same handler,
    and leaves it to the run around it when it ends."""
    root = logging.getLogger()
    handlers = root.handlers[:]
    seen = {}

    @command
    def greenhouse():
        seen["inner"] = run_handlers()
        logging.getLogger("orchard").warning("cherries are ripe")

    @command
    def orchard():
        seen["before"] = run_handlers()
        try:
            greenhouse.main(list(inner_args), standalone_mode=False)
        except click.UsageError:
            seen["inner"] = None
        seen["after"] = run_handlers()
        logging.getLogger("orchard").warning("plums are ripe")

    result = invoke(orchard, color=False)
    assert result.exit_code == 0

    assert len(seen["before"]) == 1
    assert seen["after"] == seen["before"]
    if inner_args:
        assert seen["inner"] is None
        assert result.stderr == "warning: plums are ripe\n"
    else:
        assert seen["inner"] == seen["before"]
        assert result.stderr == "warning: cherries are ripe\nwarning: plums are ripe\n"
    assert root.handlers == handlers


def test_resilient_parsing_adds_no_handler(app_handler):
    """Click parses without side effects to complete a command line: the root
    logger gets no handler then."""
    root = logging.getLogger()
    handlers = root.handlers[:]

    @click.command
    @verbosity_option
    def orchard():
        pass

    orchard.make_context("orchard", [], resilient_parsing=True)
    assert root.handlers == handlers

    # Control: the same call adds the handler when Click parses for a run.
    ctx = orchard.make_context("orchard", [])
    assert len(run_handlers()) == 1
    ctx.close()
    assert root.handlers == handlers


@pytest.mark.parametrize(
    "set_up",
    (
        pytest.param(lambda: new_logger(format=CUSTOM_FORMAT), id="new_logger"),
        pytest.param(
            lambda: basicConfig(format=CUSTOM_FORMAT, force=True), id="basicConfig"
        ),
    ),
)
@pytest.mark.parametrize("build", (extra_command, click_command))
def test_root_logger_set_up_on_purpose_is_left_as_it_is(
    invoke, restored_root_logger, set_up, build
):
    """A command left on the root logger keeps the format ``new_logger()`` or
    ``basicConfig()`` gave it, and adds no handler of its own."""
    root = restored_root_logger
    # Both helpers remove and close the handlers they find: keep the ones of
    # pytest out of their reach.
    root.handlers[:] = []
    set_up()
    handlers = root.handlers[:]
    during = []

    def body():
        during.append(root.handlers[:])
        logging.getLogger("orchard").warning("limes are ripe")

    cli, args = build(body)
    result = invoke(cli, *args, color=False)
    assert result.exit_code == 0
    assert result.stderr == "warning | orchard | limes are ripe\n"
    assert during == [handlers]
    assert root.handlers == handlers


def test_handlers_given_to_new_logger_replace_the_run_handler(
    invoke, restored_root_logger
):
    """``new_logger()`` given the handlers of the caller is how an application
    keeps the handler of Click Extra off the root logger."""
    root = restored_root_logger
    root.handlers[:] = []
    recorder = RecordingHandler()
    new_logger(handlers=[recorder])
    during = []

    @command
    def orchard():
        during.append(root.handlers[:])
        logging.getLogger("orchard").warning("kiwis are ripe")

    result = invoke(orchard, color=False)
    assert result.exit_code == 0
    assert not result.stderr
    assert during == [[recorder]]
    assert recorder.messages == ["kiwis are ripe"]


@pytest.mark.parametrize(
    ("force", "replaced"),
    (
        pytest.param(True, True, id="forced"),
        pytest.param(False, False, id="not-forced"),
    ),
)
def test_new_logger_replaces_the_handlers_of_the_root_logger(
    restored_root_logger, force, replaced
):
    """Left on its default name, ``new_logger()`` removes and closes every handler
    of the root logger, unless told not to force.

    That is its documented contract, and the reason not to call it at import
    time: the handlers of an application go with the others.
    """
    root = restored_root_logger
    # Keep the handlers of pytest out of reach: they would be closed for good.
    recorder = RecordingHandler()
    root.handlers[:] = [recorder]

    assert new_logger(force=force) is root

    assert recorder.closed is replaced
    if replaced:
        (handler,) = root.handlers
        assert isinstance(handler, StreamHandler)
        assert isinstance(handler.formatter, Formatter)
    else:
        assert root.handlers == [recorder]


def test_new_logger_with_a_name_leaves_the_root_logger_alone(app_handler):
    """Given a name, ``new_logger()`` sets that logger up and no other."""
    root = logging.getLogger()
    handlers = root.handlers[:]

    paddock = new_logger("paddock")

    assert paddock is not root
    assert root.handlers == handlers
    assert not app_handler.closed


@pytest.fixture
def application_levels(restored_root_logger):
    """Give the loggers the levels of an application for the time of a test.

    The ``root`` logger works at ``INFO``, and the ``click_extra`` one follows
    it, as it does from the start. None of the two is at the level the verbosity
    options default to: a test can so tell a level given back from one reset.
    """
    package_logger = logging.getLogger("click_extra")
    saved_level = package_logger.level
    restored_root_logger.setLevel(logging.INFO)
    package_logger.setLevel(logging.NOTSET)
    try:
        yield logging.INFO, logging.NOTSET
    finally:
        package_logger.setLevel(saved_level)


def levels():
    """The levels a verbosity option sets: of ``root`` and of ``click_extra``."""
    return logging.getLogger().level, logging.getLogger("click_extra").level


@pytest.mark.parametrize(
    ("args", "exit_code", "traced"),
    (
        pytest.param((), 0, True, id="return"),
        pytest.param(("--end", "raise"), 1, True, id="exception"),
        pytest.param(("--end", "exit"), 3, True, id="exit"),
        # The run fails while parsing, once the verbosity option set the levels:
        # Click never closes its context, and the levels come back without a trace.
        pytest.param(("--baskets", "many"), 2, False, id="invalid-value"),
    ),
)
def test_levels_are_given_back_however_the_run_ends(
    invoke, application_levels, args, exit_code, traced
):
    """A Click Extra command gives its loggers the levels they had before the run
    back the moment it ends, whatever it ends on."""

    @command
    @click.option("--baskets", type=int)
    @click.option("--end", default="return")
    @click.pass_context
    def orchard(ctx, baskets, end):
        if end == "raise":
            raise RuntimeError("frost")
        if end == "exit":
            ctx.exit(3)

    result = invoke(orchard, "--verbosity", "DEBUG", *args, color=False)
    assert result.exit_code == exit_code
    assert "debug: Set <RootLogger root (DEBUG)> to DEBUG.\n" in result.stderr
    # The trace names the level each logger works at from then on: the
    # ``click_extra`` one follows ``root`` again.
    trace = (
        "debug: Reset <RootLogger root (DEBUG)> to INFO.\n"
        "debug: Reset <Logger click_extra (DEBUG)> to INFO.\n"
    )
    assert (trace in result.stderr) is traced
    assert levels() == application_levels


def test_logger_of_the_option_gets_its_own_level_back(invoke, application_levels):
    """An option given a logger of its own leaves the level of ``root`` alone, and
    gives that logger the level it had."""
    cellar = logging.getLogger("cellar")
    cellar.setLevel(logging.ERROR)

    @click.command
    @verbosity_option(default_logger=cellar)
    def orchard():
        pass

    try:
        result = invoke(orchard, "--verbosity", "DEBUG", color=False)
        assert result.exit_code == 0
        assert "debug: Reset <Logger cellar (DEBUG)> to ERROR.\n" in result.stderr
        assert cellar.level == logging.ERROR
        assert levels() == application_levels
    finally:
        cellar.setLevel(logging.NOTSET)


def test_reset_loggers_falls_back_on_the_default_level(application_levels):
    """Called with no level to give back, ``reset_loggers()`` sets the default one."""
    VerbosityOption().reset_loggers()
    assert levels() == (logging.WARNING, logging.WARNING)


def test_levels_are_given_back_when_a_subcommand_fails_while_parsing(
    invoke, application_levels
):
    """The context of the group closes, the one of its subcommand never does.

    The group carries no verbosity option of its own here: one that does queues
    the reset on its own context, which closes.
    """

    @group(params=None)
    def farm():
        pass

    # Parenthesized: the group is Cloup-based, which rejects the naked form.
    @farm.command()
    @verbosity_option
    @click.option("--baskets", type=int)
    def orchard(baskets):
        pass

    result = invoke(
        farm, "orchard", "--verbosity", "DEBUG", "--baskets", "many", color=False
    )
    assert result.exit_code == 2
    assert "debug: Set <RootLogger root (DEBUG)> to DEBUG.\n" in result.stderr
    assert levels() == application_levels


def test_failed_run_of_a_click_command_gives_its_levels_back_when_collected(
    invoke, application_levels
):
    """A plain Click command has no hook on a run that fails while parsing: the
    levels come back once Python collects the context of that run."""

    @click.command
    @verbosity_option
    @click.option("--baskets", type=int)
    def orchard(baskets):
        pass

    result = invoke(orchard, "--verbosity", "DEBUG", "--baskets", "many", color=False)
    assert result.exit_code == 2
    assert "debug: Set <RootLogger root (DEBUG)> to DEBUG.\n" in result.stderr

    del result
    gc.collect()
    assert levels() == application_levels


def failing_click_command(contexts, body=None):
    """A plain Click command that keeps the context of each of its runs alive, and
    fails while parsing when given an invalid ``--baskets``."""

    def keep_context(ctx, param, value):
        contexts.append(ctx)

    @click.command
    @verbosity_option
    @click.option(
        "--keep",
        is_flag=True,
        is_eager=True,
        expose_value=False,
        callback=keep_context,
    )
    @click.option("--baskets", type=int, expose_value=False)
    def orchard():
        if body:
            body()

    return orchard


def test_run_keeps_its_levels_when_a_failed_run_is_collected(
    invoke, application_levels
):
    """The context of a failed run may be collected in the middle of a later run:
    the levels are by then the ones of that later run, and stay."""
    contexts: list[click.Context] = []
    holders = []
    seen = []

    def body():
        seen.append(levels())
        holders.append(len(_INVOCATION_HOLDERS))
        contexts.clear()
        gc.collect()
        holders.append(len(_INVOCATION_HOLDERS))
        seen.append(levels())

    orchard = failing_click_command(contexts, body)

    # The eager option keeps the context of the run, which then fails on the
    # value of the other one.
    failed = invoke(orchard, "--verbosity", "DEBUG", "--baskets", "many", color=False)
    assert failed.exit_code == 2
    del failed
    # Nothing gave the levels back yet: the context of the failed run is alive.
    assert levels() == (logging.DEBUG, logging.DEBUG)

    result = invoke(orchard, "--verbosity", "ERROR", color=False)
    assert result.exit_code == 0
    # The failed run was collected in the middle of this run.
    assert holders[0] - holders[1] == 1
    assert seen == [(logging.ERROR, logging.ERROR), (logging.ERROR, logging.ERROR)]
    assert levels() == application_levels


def test_levels_found_before_a_failed_run_are_the_ones_given_back(
    invoke, application_levels
):
    """A run that starts on the levels a failed run left behind gives back the
    ones found before that failed run, not the ones it left."""
    contexts: list[click.Context] = []
    orchard = failing_click_command(contexts)

    failed = invoke(orchard, "--verbosity", "DEBUG", "--baskets", "many", color=False)
    assert failed.exit_code == 2
    del failed
    assert levels() == (logging.DEBUG, logging.DEBUG)

    result = invoke(orchard, color=False)
    assert result.exit_code == 0
    assert levels() == application_levels

    # The failed run has nothing left to give back once it is collected.
    contexts.clear()
    gc.collect()
    assert levels() == application_levels


def test_released_handler_put_back_on_the_root_logger_prints_nothing(
    invoke, app_handler, capsys
):
    """Code that saves the handlers of the root logger and puts them back later
    may attach again a handler its run let go of in between. That handler prints
    nothing, and the next run takes it off.

    A fixture isolating a test does that around a plain Click command that failed
    while parsing: Python collects the context of that run, and so releases its
    handler, whenever it sees fit.
    """
    root = logging.getLogger()
    contexts: list[click.Context] = []
    orchard = failing_click_command(
        contexts, lambda: logging.getLogger("orchard").warning("apples are ripe")
    )

    failed = invoke(orchard, "--baskets", "many", color=False)
    assert failed.exit_code == 2
    del failed
    (lent,) = run_handlers()

    saved = root.handlers[:]
    contexts.clear()
    gc.collect()
    assert not run_handlers()
    root.handlers[:] = saved
    assert run_handlers() == [lent]

    capsys.readouterr()
    logging.getLogger("orchard").warning("pears are ripe")
    assert not capsys.readouterr().err

    result = invoke(orchard, color=False)
    assert result.exit_code == 0
    assert result.stderr == "warning: apples are ripe\n"
    assert lent not in root.handlers


@pytest.mark.once
def test_importing_a_cli_leaves_the_root_logger_alone():
    """In a new interpreter, importing Click Extra and defining a command leave
    the root logger with the one handler the application gave it."""
    script = dedent("""\
        import logging

        application_handler = logging.NullHandler()
        logging.getLogger().addHandler(application_handler)

        import click_extra

        assert logging.getLogger().handlers == [application_handler]


        @click_extra.command
        def orchard():
            pass


        assert logging.getLogger().handlers == [application_handler]
        assert logging.getLogger().level == logging.WARNING
        """)
    process = run(
        (sys.executable, "-c", script),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert process.returncode == 0, process.stderr


@pytest.mark.once
def test_root_logger_prints_in_a_new_interpreter_beside_a_named_logger():
    """A command whose verbosity option sets a named logger still prints the
    records of the root logger in the style of Click Extra.

    Run in a new interpreter: no other command of the process may have given the
    root logger its handler.
    """
    script = dedent("""\
        import logging

        import click
        from click_extra import new_logger, verbosity_option

        new_logger(name="greenhouse", format="{levelname} | {name} | {message}")


        @click.command
        @verbosity_option(default_logger="greenhouse")
        def orchard():
            logging.warning("frost on the orchard")
            logging.getLogger("greenhouse").warning("frost in the greenhouse")


        orchard()
        """)
    process = run(
        (sys.executable, "-c", script),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert process.stderr == (
        "warning: frost on the orchard\n"
        "warning | greenhouse | frost in the greenhouse\n"
    )


def test_stream_handler_honors_no_color_from_background_threads(capsys, monkeypatch):
    """A record emitted with no reachable Click context (as from run_cli's stream
    reader threads) still honors --no-color, through the process-wide mirror
    published by the color options."""
    from click_extra import color as color_module

    handler = StreamHandler()
    handler.setFormatter(Formatter("{levelname}: {message}", style="{"))
    record = logging.LogRecord(
        name="test",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="env: node: No such file or directory",
        args=None,
        exc_info=None,
    )
    record.label = "yarn-berry"

    # Make the captured stream claim to be a TTY: the terminal where the leak
    # showed, since click.echo's auto default keeps ANSI codes there.
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)

    # Control: under the auto default, the themed levelname and label reach the
    # "terminal" with their ANSI codes.
    handler.emit(record)
    assert "\x1b[" in capsys.readouterr().err

    # A --no-color invocation mirrored process-wide strips them, even though this
    # thread has no Click context to consult.
    monkeypatch.setattr(color_module, "_invocation_color", False)
    handler.emit(record)
    assert capsys.readouterr().err == (
        "debug:yarn-berry: env: node: No such file or directory\n"
    )


def test_formatter_renders_label_glued_to_level_name():
    """A record tagged with a ``label`` attribute (as run_cli's streamed output
    lines are) renders it inside the level prefix: ``debug:mas: message``."""
    formatter = Formatter(fmt="{levelname}: {message}", style="{")
    record = logging.LogRecord(
        name="test",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="Warning: No installed apps found",
        args=None,
        exc_info=None,
    )
    record.label = "mas"
    rendered = strip_ansi(formatter.format(record))
    assert rendered == "debug:mas: Warning: No installed apps found"


@pytest.mark.parametrize(
    ("label", "prefix"),
    ((None, "info:"), ("almanac", "info:almanac:")),
)
@pytest.mark.parametrize(
    ("message", "expected"),
    (
        # Control: a single line stays glued to its prefix, a trailing line
        # break included.
        pytest.param("Sunny in Lima", " Sunny in Lima", id="line"),
        pytest.param("Sunny in Lima\n", " Sunny in Lima\n", id="trailing-break"),
        pytest.param(
            "City  Forecast\n====  ========\nOslo  Snow\nLima  Sunny",
            "\nCity  Forecast\n====  ========\nOslo  Snow\nLima  Sunny",
            id="block",
        ),
        # Already below its prefix: no second line break.
        pytest.param(
            "\nOslo  Snow\nLima  Sunny",
            " \nOslo  Snow\nLima  Sunny",
            id="leading-break",
        ),
    ),
)
def test_formatter_starts_a_block_below_its_prefix(label, prefix, message, expected):
    """A message spanning several lines starts on the line below its prefix, so
    its first line keeps the columns of the lines under it."""
    formatter = Formatter(fmt="{levelname}: {message}", style="{")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=None,
        exc_info=None,
    )
    if label:
        record.label = label
    assert strip_ansi(formatter.format(record)) == prefix + expected
    # The record keeps its own message for the next handler to format.
    assert record.message == message


def test_stream_handler_routes_through_active_spinner(capsys):
    """A record emitted while a spinner animates on the same stream is printed
    through Spinner.echo(), on its own line, instead of over the frame."""
    handler = StreamHandler()
    # A plain stdlib formatter keeps the assertion free of theme ANSI codes.
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="mind the spinner",
        args=None,
        exc_info=None,
    )

    # A huge delay keeps the spinner registered without ever drawing a frame,
    # making the test timing-free: echo() then degrades to a plain line write.
    spinner = Spinner("work", live="always", delay=3600)
    spinner.start()
    try:
        handler.emit(record)
    finally:
        spinner.stop()
    assert capsys.readouterr().err == "WARNING: mind the spinner\n"

    # With no spinner running, the plain click.echo path takes over.
    handler.emit(record)
    assert capsys.readouterr().err == "WARNING: mind the spinner\n"
