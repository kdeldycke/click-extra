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

"""Utilities to execute external commands."""

import os
import subprocess
from textwrap import indent

from .colorize import theme

# Some CLI printing constants.
PROMPT = "► "
INDENT = " " * len(PROMPT)


def print_cli_output(cmd, output=None, error=None, error_code=None, extra_env=None):
    """Simulate CLI's terminal output.

    Mostly used to print debug traces to user or in test results."""
    extra_env_string = ""
    if extra_env:
        extra_env_string = "".join(f"{k}={v} " for k, v in extra_env.items())
    print(
        "\n{}{}{}".format(
            PROMPT, extra_env_string, theme.invoked_command(" ".join(cmd))
        )
    )
    if output:
        print(indent(output, INDENT))
    if error:
        print(indent(theme.error(error), INDENT))
    if error_code is not None:
        print(theme.error(f"{INDENT}Return code: {error_code}"))


def extend_env(extra_env=None):
    """Utility method to extend current environment variable.

    Mimicks Python's original implementation. See:
    https://github.com/python/cpython/blob/7b5b429adab4fe0fe81858fe3831f06adc2e2141/Lib/subprocess.py#L1648-L1649
    """
    assert not extra_env or isinstance(extra_env, dict)
    env = None
    if extra_env:
        env = os.environ
        env.update(extra_env)
    return env


def run_cmd(*args, extra_env=None, print_output=True):
    """Run a system command, print output and return results."""
    assert isinstance(args, tuple)
    process = subprocess.run(args, capture_output=True, encoding="utf-8", env=extend_env(extra_env))

    if print_output:
        print_cli_output(args, process.stdout, process.stderr, process.returncode, extra_env=extra_env)

    return process.returncode, process.stdout, process.stderr
