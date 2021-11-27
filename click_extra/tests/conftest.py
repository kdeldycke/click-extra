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

""" Fixtures, configuration and helpers for tests. """

import os
from functools import partial
from pathlib import Path
from textwrap import dedent

import pytest
from boltons.iterutils import flatten, same
from boltons.strutils import strip_ansi
from boltons.tbutils import ExceptionInfo
from click.testing import CliRunner

from ..platform import is_linux, is_macos, is_windows
from ..run import print_cli_output

DESTRUCTIVE_MODE = bool(
    os.environ.get("DESTRUCTIVE_TESTS", False) not in {True, 1, "True", "true", "1"}
)
""" Pre-computed boolean flag indicating if destructive mode is activated by
the presence of a ``DESTRUCTIVE_TESTS`` environment variable set to ``True``.
"""


destructive = pytest.mark.skipif(DESTRUCTIVE_MODE, reason="destructive test")
""" Pytest mark to skip a test unless destructive mode is allowed.

.. todo:

    Test destructive test assessment.
"""


non_destructive = pytest.mark.skipif(
    not DESTRUCTIVE_MODE, reason="non-destructive test"
)
""" Pytest mark to skip a test unless destructive mode is allowed.

.. todo:

    Test destructive test assessment.
"""


skip_linux = pytest.mark.skipif(is_linux(), reason="Skip Linux")
""" Pytest mark to skip a test if run on a Linux system. """

skip_macos = pytest.mark.skipif(is_macos(), reason="Skip macOS")
""" Pytest mark to skip a test if run on a macOS system. """

skip_windows = pytest.mark.skipif(is_windows(), reason="Skip Windows")
""" Pytest mark to skip a test if run on a Windows system. """


unless_linux = pytest.mark.skipif(not is_linux(), reason="Linux required")
""" Pytest mark to skip a test unless it is run on a Linux system. """

unless_macos = pytest.mark.skipif(not is_macos(), reason="macOS required")
""" Pytest mark to skip a test unless it is run on a macOS system. """

unless_windows = pytest.mark.skipif(not is_windows(), reason="Windows required")
""" Pytest mark to skip a test unless it is run on a Windows system. """


skip_windows_colors = skip_windows(reason="Click overstrip colors on Windows")
"""Skips color tests on Windows as click.testing.invoke overzealously strips colors.

See: https://github.com/pallets/click/issues/2111 and https://github.com/pallets/click/issues/2110
"""


@pytest.fixture
def runner():
    runner = CliRunner(mix_stderr=False)
    with runner.isolated_filesystem():
        yield runner


@pytest.fixture
def invoke(runner, monkeypatch):
    """Executes Click's CLI, print output and return results.

    If ``color=False`` both ``<stdout>`` and ``<stderr>`` are stripped out of ANSI codes.

    Adds a special case in the form of ``color="forced"`` parameter, which allows
    colored output to be kept, while forcing the initialization of ``Context.color = True``.
    This is not allowed in current implementation of ``click.testing.CliRunner.invoke()``. See:
    https://github.com/pallets/click/issues/2110
    """

    def _run(cli, *args, env=None, color=None):
        # We allow for nested iterables and None values as args for
        # convenience. We just need to flatten and filters them out.
        args = list(filter(None.__ne__, flatten(args)))
        if args:
            assert same(map(type, args), str)

        # Extra parameters passed to the invoked command's ``main()`` constructor.
        extra = {}
        if color == "forced":
            extra["color"] = True

        with monkeypatch.context() as patch:
            # Monkeypatch the original command's ``main()`` call to pass extra parameter
            # for Context initialization. Because we cannot simply add ``color`` to ``**extra``.
            patch.setattr(cli, "main", partial(cli.main, **extra))

            result = runner.invoke(cli, args, env=env, color=bool(color))

        # Force stripping of all colors from results.
        if color is False:
            result.stdout_bytes = strip_ansi(result.stdout_bytes)
            result.stderr_bytes = strip_ansi(result.stderr_bytes)

        print_cli_output(
            [runner.get_default_prog_name(cli)] + args,
            result.output,
            result.stderr,
            result.exit_code,
        )

        if result.exception:
            print(ExceptionInfo.from_exc_info(*result.exc_info).get_formatted())

        return result

    return _run


@pytest.fixture
def create_config(tmp_path):
    """A generic fixture to produce a temporary configuration file."""

    def _create_config(filename, content):
        """Create a fake configuration file."""
        assert isinstance(content, str)

        if isinstance(filename, str):
            config_path = tmp_path.joinpath(filename)
        else:
            assert isinstance(filename, Path)
            config_path = filename.resolve()

        # Create the missing folder structure, like "mkdir -p" does.
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(dedent(content).strip())

        return config_path

    return _create_config
