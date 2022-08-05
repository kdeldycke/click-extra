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

import pytest
from click import echo

from ..commands import extra_command
from ..logging import LOG_LEVELS, logger, verbosity_option
from .conftest import command_decorators, default_debug_colored_log, skip_windows_colors


@pytest.mark.parametrize("cmd_decorator, cmd_type", command_decorators(with_types=True))
def test_unrecognized_verbosity(invoke, cmd_decorator, cmd_type):
    @cmd_decorator
    @verbosity_option()
    def logging_cli1():
        echo("It works!")

    result = invoke(logging_cli1, "--verbosity", "random")
    assert result.exit_code == 2
    assert not result.output

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
    # Skip click extra's commands, as verbosity option is already part of the default.
    "cmd_decorator",
    command_decorators(no_groups=True, no_extra=True),
)
@pytest.mark.parametrize("level", LOG_LEVELS.keys())
def test_standalone_verbosity_option(invoke, cmd_decorator, level):
    @cmd_decorator
    @verbosity_option()
    def logging_cli2():
        echo("It works!")
        logger.debug("my debug message.")
        logger.info("my info message.")
        logger.warning("my warning message.")
        logger.error("my error message.")
        logger.critical("my critical message.")

    result = invoke(logging_cli2, "--verbosity", level, color=True)
    assert result.exit_code == 0
    assert result.output == "It works!\n"

    messages = (
        "\x1b[34mdebug: \x1b[0mVerbosity set to DEBUG.\n\x1b[34mdebug: \x1b[0mmy debug message.\n",
        "my info message.\n",
        "\x1b[33mwarning: \x1b[0mmy warning message.\n",
        "\x1b[31merror: \x1b[0mmy error message.\n",
        "\x1b[31mcritical: \x1b[0mmy critical message.\n",
    )
    level_index = {index: level for level, index in enumerate(LOG_LEVELS)}[level]
    log_records = "".join(messages[-level_index - 1 :])
    assert result.stderr == log_records


@skip_windows_colors
@pytest.mark.parametrize("level", LOG_LEVELS.keys())
# TODO: test extra_group
def test_integrated_verbosity_option(invoke, level):
    @extra_command()
    def logging_cli3():
        echo("It works!")

    result = invoke(logging_cli3, "--verbosity", level, color=True)
    assert result.exit_code == 0
    assert result.output == "It works!\n"
    if level == "DEBUG":
        assert re.fullmatch(default_debug_colored_log, result.stderr)
    else:
        assert not result.stderr
