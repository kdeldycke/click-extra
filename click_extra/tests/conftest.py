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

"""Fixtures, configuration and helpers for tests."""

import os
import sys
from functools import partial
from pathlib import Path
from textwrap import dedent
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import click
import cloup
import pytest
from boltons.strutils import strip_ansi

if TYPE_CHECKING:
    from click.core import BaseCommand

import pytest
from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from boltons.tbutils import ExceptionInfo
from click.testing import CliRunner, Result

from ..commands import extra_command, extra_group
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


# XXX Recursive types are not supported by mypy yet: https://github.com/python/mypy/issues/731
# _NestedArgs = Iterable[Union[str, Path, None, Iterable["_NestedArgs"]]]
_Arg = Union[str, Path, None]
_Args = Iterable[_Arg]
_NestedArgs = Iterable[
    Union[
        _Arg, Iterable[Union[_Arg, Iterable[Union[_Arg, Iterable[Union[_Arg, _Args]]]]]]
    ]
]


class ExtraCliRunner(CliRunner):

    force_color = False
    """Add a ``force_color`` boolean flag on the class to allow for overriding of the ``color`` parameter in ``invoke``.

    This is only used to initialize the CliRunner in the context of Sphinx documentation.
    """

    @classmethod
    def _args_cleanup(cls, *args: Union[_Arg, _NestedArgs]) -> Tuple[str, ...]:
        """Flatten recursive iterables, remove all ``None``, and cast each element to
        strings.

        Helps serialize :py:class:`pathlib.Path` and other objects.

        It also allows for nested iterables and ``None`` values as CLI arguments for
        convenience. We just need to flatten and filters them out.
        """
        return tuple(str(arg) for arg in flatten(args) if arg is not None)

    def invoke(  # type: ignore
        self,
        cli: "BaseCommand",
        args: Optional[Union[str, Sequence[str]]] = None,
        env: Optional[Mapping[str, Optional[str]]] = None,
        color: bool = False,
        **extra: Any,
    ) -> Result:

        if self.force_color:
            color = True

        result = super().invoke(cli=cli, args=args, env=env, color=color, **extra)

        if result.exception:
            print(ExceptionInfo.from_exc_info(*result.exc_info).get_formatted())

        return result


@pytest.fixture
def runner():
    runner = ExtraCliRunner(mix_stderr=False)
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
        args = ExtraCliRunner._args_cleanup(args)

        # Extra parameters passed to the invoked command's ``main()`` constructor.
        extra = {}
        if color == "forced":
            extra["color"] = True

        with monkeypatch.context() as patch:
            # Monkeypatch the original command's ``main()`` call to pass extra parameter
            # for Context initialization. Because we cannot simply add ``color`` to
            # ``**extra``.
            patch.setattr(cli, "main", partial(cli.main, **extra))

            result = runner.invoke(cli=cli, args=args, env=env, color=bool(color))

        # Force stripping of all colors from results.
        if color is False:
            result.stdout_bytes = strip_ansi(result.stdout_bytes)
            result.stderr_bytes = strip_ansi(result.stderr_bytes)

        print_cli_output(
            [runner.get_default_prog_name(cli)] + list(args),
            result.output,
            result.stderr,
            result.exit_code,
        )

        if result.exception:
            print(ExceptionInfo.from_exc_info(*result.exc_info).get_formatted())

        return result

    return _run


# XXX Support for decorator without parenthesis in Cloup has been reported upstream:
# https://github.com/janluke/cloup/issues/127
skip_naked = pytest.mark.skip(reason="Naked decorator not supported yet.")


def command_decorators(
    no_commands=False,
    no_groups=False,
    no_click=False,
    no_cloup=False,
    no_extra=False,
    with_types=False,
):
    """Returns collection of Pytest parameters to test all forms of click/cloup/click-
    extra command-like decorators."""
    params = []

    if no_commands == False:

        if not no_click:
            params.extend(
                [
                    (click.command, {"click", "command"}, "click.command", ()),
                    (click.command(), {"click", "command"}, "click.command()", ()),
                ]
            )

        if not no_cloup:
            params.extend(
                [
                    (cloup.command, {"cloup", "command"}, "cloup.command", skip_naked),
                    (cloup.command(), {"cloup", "command"}, "cloup.command()", ()),
                ]
            )

        if not no_extra:
            params.extend(
                [
                    (
                        extra_command,
                        {"extra", "command"},
                        "click_extra.extra_command",
                        skip_naked,
                    ),
                    (
                        extra_command(),
                        {"extra", "command"},
                        "click_extra.extra_command()",
                        (),
                    ),
                ]
            )

    if not no_groups:
        if not no_click:
            params.extend(
                [
                    (click.group, {"click", "group"}, "click.group", ()),
                    (click.group(), {"click", "group"}, "click.group()", ()),
                ]
            )

        if not no_cloup:
            params.extend(
                [
                    (cloup.group, {"cloup", "group"}, "cloup.group", skip_naked),
                    (cloup.group(), {"cloup", "group"}, "cloup.group()", ()),
                ]
            )

        if not no_extra:
            params.extend(
                [
                    (
                        extra_group,
                        {"extra", "group"},
                        "click_extra.extra_group",
                        skip_naked,
                    ),
                    (
                        extra_group(),
                        {"extra", "group"},
                        "click_extra.extra_group()",
                        (),
                    ),
                ]
            )

    decorator_params = []
    for deco, deco_type, label, marks in params:
        args = [deco]
        if with_types:
            args.append(deco_type)
        decorator_params.append(pytest.param(*args, id=label, marks=marks))

    return tuple(decorator_params)


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


default_options_uncolored_help = (
    r"  --time / --no-time        Measure and print elapsed execution time.  \[default:\n"
    r"                            no-time\]\n"
    r"  --color, --ansi / --no-color, --no-ansi\n"
    r"                            Strip out all colors and all ANSI codes from output.\n"
    r"                            \[default: color\]\n"
    r"  -C, --config CONFIG_PATH  Location of the configuration file. Supports glob\n"
    r"                            pattern of local path and remote URL.  \[default:( \S+)?\n"
    r"(                            .+\n)*"
    r"                            \S+\.{toml,yaml,yml,json,ini,xml}\]\n"
    r"  --show-params             Show all CLI parameters, their provenance, defaults,\n"
    r"                            value, then exit.\n"
    r"  -v, --verbosity LEVEL     Either CRITICAL, ERROR, WARNING, INFO, DEBUG.\n"
    r"                            \[default: INFO\]\n"
    r"  --version                 Show the version and exit.\n"
    r"  -h, --help                Show this message and exit.\n"
)


default_options_colored_help = (
    r"  \x1b\[36m--time\x1b\[0m / \x1b\[36m--no-time\x1b\[0m        Measure and print elapsed execution time.  \x1b\[90m\[default:\n"
    r"                            \x1b\[0m\x1b\[35mno-time\x1b\[0m\x1b\[90m\]\x1b\[0m\n"
    r"  \x1b\[36m--color\x1b\[0m, \x1b\[36m--ansi\x1b\[0m / \x1b\[36m--no-color\x1b\[0m, \x1b\[36m--no-ansi\x1b\[0m\n"
    r"                            Strip out all colors and all ANSI codes from output.\n"
    r"                            \x1b\[90m\[default: \x1b\[0m\x1b\[35mcolor\x1b\[0m\x1b\[90m\]\x1b\[0m\n"
    r"  \x1b\[36m-C\x1b\[0m, \x1b\[36m--config\x1b\[0m \x1b\[90mCONFIG_PATH\x1b\[0m  Location of the configuration file. Supports glob\n"
    r"                            pattern of local path and remote URL.  \x1b\[90m\[default:( \S+)?\n"
    r"(                            .+\n)*"
    r"                            \S+\.{toml,yaml,yml,json,ini,xml}\x1b\[0m\x1b\[90m\]\x1b\[0m\n"
    r"  \x1b\[36m--show-params\x1b\[0m             Show all CLI parameters, their provenance, defaults,\n"
    r"                            value, then exit.\n"
    r"  \x1b\[36m-v\x1b\[0m, \x1b\[36m--verbosity\x1b\[0m \x1b\[90mLEVEL\x1b\[0m     Either \x1b\[35mCRITICAL\x1b\[0m, \x1b\[35mERROR\x1b\[0m, \x1b\[35mWARNING\x1b\[0m, \x1b\[35mINFO\x1b\[0m, \x1b\[35mDEBUG\x1b\[0m.\n"
    r"                            \x1b\[90m\[default: \x1b\[0m\x1b\[35mINFO\x1b\[0m\x1b\[90m\]\x1b\[0m\n"
    r"  \x1b\[36m--version\x1b\[0m                 Show the version and exit.\n"
    r"  \x1b\[36m-h\x1b\[0m, \x1b\[36m--help\x1b\[0m                Show this message and exit.\n"
)


default_debug_uncolored_log = (
    r"debug: Verbosity set to DEBUG.\n"
    r"debug: Load configuration matching .+\*\.{toml,yaml,yml,json,ini,xml}\n"
    r"debug: Pattern is not an URL.\n"
    r"debug: Search local file system.\n"
    r"debug: No configuration file found. Ignore it.\n"
    r"debug: \S+, version \S+\n"
)


default_debug_colored_log = (
    r"\x1b\[34mdebug: \x1b\[0mVerbosity set to DEBUG.\n"
    r"\x1b\[34mdebug: \x1b\[0mLoad configuration matching .+\*\.{toml,yaml,yml,json,ini,xml}\n"
    r"\x1b\[34mdebug: \x1b\[0mPattern is not an URL.\n"
    r"\x1b\[34mdebug: \x1b\[0mSearch local file system.\n"
    r"\x1b\[34mdebug: \x1b\[0mNo configuration file found. Ignore it.\n"
    r"\x1b\[34mdebug: \x1b\[0m\x1b\[97m\S+\x1b\[0m, version \x1b\[32m\S+\x1b\[0m(\x1b\[90m)?\n"
)


# XXX Temporarily expect extra-env info for Python < 3.10 while we wait for
# https://github.com/mahmoud/boltons/issues/294 to be released upstream.
if sys.version_info[:2] < (3, 10):
    default_debug_uncolored_log += r"debug: {.*}\n"
    default_debug_colored_log += r"\x1b\[34mdebug: \x1b\[0m{.*}\x1b\[0m\n"
