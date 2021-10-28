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

import click
import pytest

from ..commands import group
from ..logging import LOG_LEVELS, logger, verbosity_option
from .conftest import skip_windows_colors


def test_unrecognized_verbosity(invoke):
    @click.command()
    @verbosity_option()
    def dummy_cli():
        click.echo("It works!")

    result = invoke(dummy_cli, "--verbosity", "random")
    assert result.exit_code == 2
    assert not result.output
    assert result.stderr == (
        "Usage: dummy-cli [OPTIONS]\n"
        "Try 'dummy-cli --help' for help.\n\n"
        "Error: Invalid value for '--verbosity' / '-v': "
        "'random' is not one of 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'.\n"
    )


@skip_windows_colors
@pytest.mark.parametrize("level", LOG_LEVELS.keys())
def test_standalone_verbosity_option(invoke, level):
    @click.command()
    @verbosity_option()
    def dummy_cli():
        click.echo("It works!")
        logger.debug("my debug message.")
        logger.info("my info message.")
        logger.warning("my warning message.")
        logger.error("my error message.")
        logger.critical("my critical message.")

    result = invoke(dummy_cli, "--verbosity", level, color=True)
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
def test_integrated_verbosity_option(invoke, level):
    @group()
    def dummy_cli():
        click.echo("It works!")

    @dummy_cli.command()
    def command1():
        click.echo("Run command #1...")

    result = invoke(dummy_cli, "--verbosity", level, "command1", color=True)
    assert result.exit_code == 0
    assert result.output == "It works!\nRun command #1...\n"
    if level == "DEBUG":
        assert re.fullmatch(
            r"\x1b\[34mdebug: \x1b\[0mVerbosity set to DEBUG.\n"
            r"\x1b\[34mdebug: \x1b\[0mLoad configuration at \S+config.toml\n"
            r"\x1b\[34mdebug: \x1b\[0mConfiguration not found at \S+config.toml\n"
            r"\x1b\[34mdebug: \x1b\[0mIgnore configuration file.\n"
            r"\x1b\[34mdebug: \x1b\[0mLoaded configuration: {}\n",
            result.stderr,
        )
    else:
        assert not result.stderr
