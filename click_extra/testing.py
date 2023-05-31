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
"""CLI testing and simulation of their execution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from textwrap import indent
from typing import Iterable, Mapping, Optional, Union, cast, IO, Any, Mapping, Optional,ContextManager, Literal
import os
import inspect
from functools import partial
from pathlib import Path
from contextlib import nullcontext
from unittest.mock import patch

import click
import click.testing
from boltons.strutils import strip_ansi
from boltons.tbutils import ExceptionInfo
from boltons.iterutils import flatten

from .colorize import default_theme


PROMPT = "► "
INDENT = " " * len(PROMPT)
"""Constants for rendering of CLI execution."""


EnvVars = Mapping[str, Optional[str]]
"""Type for ``dict``-like environment variables."""

Arg = Union[str, Path, None]
Args = Iterable[Arg]
NestedArgs = Iterable[Union[Arg, Iterable["NestedArgs"]]]
"""Types for arbitrary nested CLI arguments.

Arguments can be ``str``, :py:class:`pathlib.Path` objects or ``None`` values.
"""


def args_cleanup(*args: Arg | NestedArgs) -> tuple[str, ...]:
    """Flatten recursive iterables, remove all ``None``, and cast each element to
    strings.

    Helps serialize :py:class:`pathlib.Path` and other objects.

    It also allows for nested iterables and ``None`` values as CLI arguments for
    convenience. We just need to flatten and filters them out.
    """
    return tuple(str(arg) for arg in flatten(args) if arg is not None)


def format_cli_prompt(cmd_args: Iterable[str], extra_env: EnvVars | None = None) -> str:
    """Simulate the console prompt used to invoke the CLI."""
    extra_env_string = ""
    if extra_env:
        extra_env_string = "".join(f"{k}={v} " for k, v in extra_env.items())

    cmd_str = default_theme.invoked_command(" ".join(cmd_args))

    return f"{PROMPT}{extra_env_string}{cmd_str}"


def print_cli_run(
    args, output=None, error=None, error_code=None, extra_env=None
) -> None:
    """Prints the full simulation of CLI execution, including output.

    Mostly used to print debug traces to user or in test results.
    """
    print(f"\n{format_cli_prompt(args, extra_env)}")
    if output:
        print(indent(output, INDENT))
    if error:
        print(indent(default_theme.error(error), INDENT))
    if error_code is not None:
        print(default_theme.error(f"{INDENT}Return code: {error_code}"))


def env_copy(extend: EnvVars | None = None) -> EnvVars | None:
    """Returns a copy of the current environment variables and eventually ``extend`` it.

    Mimics `Python's original implementation
    <https://github.com/python/cpython/blob/7b5b429/Lib/subprocess.py#L1648-L1649>`_ by
    returning ``None`` if no ``extend`` content are provided.

    Environment variables are expected to be a ``dict`` of ``str:str``.
    """
    if isinstance(extend, dict):
        for k, v in extend.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
    else:
        assert not extend
    env_copy: EnvVars | None = None
    if extend:
        # By casting to dict we make a copy and prevent the modification of the
        # global environment.
        env_copy = dict(os.environ)
        env_copy.update(extend)
    return env_copy


def run_cmd(*args, extra_env: EnvVars | None = None, print_output: bool = True):
    """Run a system command, print output and return results."""
    assert isinstance(args, tuple)
    process = subprocess.run(
        args,
        capture_output=True,
        encoding="utf-8",
        env=cast("subprocess._ENV", env_copy(extra_env)),
    )

    if print_output:
        print_cli_run(
            args,
            process.stdout,
            process.stderr,
            process.returncode,
            extra_env=extra_env,
        )

    return process.returncode, process.stdout, process.stderr


INVOKE_ARGS = set(inspect.getfullargspec(click.testing.CliRunner.invoke).args)
"""Parameter IDs of ``click.testing.CliRunner.invoke()``.

We need to collect them to help us identify which extra parameters passed to
``invoke()`` collides with its original signature.

.. note::
    This has been `reported upstream to Click project
    <https://github.com/pallets/click/issues/2110>`_ but was not considered an issue.
"""


class ExtraCliRunner(click.testing.CliRunner):
    """Augment ``click.testing.CliRunner`` with extra features and bug fixes."""

    force_color: bool = False
    """Global class attribute to override the ``color`` parameter in ``invoke``.

    .. note::
        This was initially developed to `force the initialization of the runner during
        the setup of Sphinx new directives <sphinx#click_extra.sphinx.setup>`_. This
        was the only way we found, as to patch some code we had to operate at the class
        level.
    """

    def __init__(
        self,
        charset: str = "utf-8",
        env: Optional[Mapping[str, Optional[str]]] = None,
        echo_stdin: bool = False,
        mix_stderr: bool = False,
    ) -> None:
        """Same as original but sets default to ``mix_stderr=False``.

        This way we avoid mixing ``<stdout>`` and ``<stderr>`` in the result object.
        """
        return super().__init__(
            charset=charset,
            env=env,
            echo_stdin=echo_stdin,
            mix_stderr=mix_stderr
        )

    def invoke(
        self,
        cli: click.core.BaseCommand,
        *args: Arg | NestedArgs,
        input: str | bytes | IO | None = None,
        env: EnvVars | None = None,
        catch_exceptions: bool = True,
        color: bool | Literal["forced"] | None = None,
        **extra: Mapping[str, Any],
    ) -> click.testing.Result:
        """Same as ``click.testing.CliRunner.invoke()`` with extra features.

        - The first positional parameter is the CLI to invoke. The remaining positional
          parameters of the function are the CLI arguments. All other parameters are
          required to be named.

        - The CLI arguments can be nested iterables of arbitrary depth.

        - Allow forcing of the ``color`` property at the class-level via
          ``force_color`` attribute.

        - Adds a special case in the form of ``color="forced"`` parameter, which allows
          colored output to be kept, while forcing the initialization of
          ``Context.color = True``. This is `not allowed in current implementation
          <https://github.com/pallets/click/issues/2110>`_ of
          ``click.testing.CliRunner.invoke()`` because of colliding parameters.

        - Strips all ANSI codes from results if ``color`` was explicirely set to
          ``False``.

        - Always prints a simulation of the CLI execution as the user would see it in
          its terminal. Including colors.

        - Pretty-prints a formatted exception traceback if the command fails.

        :param cli: CLI to invoke.
        :param *args: can be nested iterables composed of ``str``,
            :py:class:`pathlib.Path` objects and ``None`` values. The nested structure
            will be flattened and ``None`` values will be filtered out. Then all
            elements will be casted to ``str``. See :func:`args_cleanup` for details.
        :param input: same as ``click.testing.CliRunner.invoke()``.
        :param env: same as ``click.testing.CliRunner.invoke()``.
        :param catch_exceptions: same as ``click.testing.CliRunner.invoke()``.
        :param color: If a boolean, the parameter will be passed as-is to
            ``click.testing.CliRunner.isolation()``. If ``"forced"``, the parameter
            will be passed as ``True`` to ``click.testing.CliRunner.isolation()`` and
            an extra ``color=True`` parameter will be passed to the invoked CLI.
        :param **extra: same as ``click.testing.CliRunner.invoke()``, but colliding
            parameters are allowed and properly passed on to the invoked CLI.
        """
        # Initialize ``extra`` if not provided.
        if not extra:
            extra = {}

        # Pop out the ``args`` parameter from ``extra`` and append it to the positional
        # arguments. This situation append when the ``args`` parameter is passed as a
        # keyword argument in
        # ``pallets_sphinx_themes.themes.click.domain.ExampleRunner.invoke()``.
        args = list(args)
        if "args" in extra:
            args.extend(extra.pop("args"))
        # Flatten and filters out CLI arguments.
        args = args_cleanup(args)

        # The class attribute ``force_color`` overrides the ``color`` parameter.
        if self.force_color:
            isolation_color = True

        if color == "forced":
            # Pass the color argument as an extra parameter to the invoked CLI.
            extra["color"] = True
            # TODO: investigate the possibility of forcing coloring on ``echo`` too,
            # because by default, Windows is rendered colorless:
            # https://github.com/pallets/click/blob/0c85d80/src/click/utils.py#L295-L296
            # echo_extra["color"] = True

        # Cast to ``bool`` to avoid passing ``None`` or ``"forced"`` to ``invoke()``.
        isolation_color = bool(color)

        # No-op context manager without any effects.
        extra_params_bypass: ContextManager = nullcontext()

        # If ``extra`` contains parameters that collide with the original ``invoke()``
        # parameters, we need to remove them from ``extra``, then use a monkeypatch to
        # properly pass them to the CLI.
        colliding_params = INVOKE_ARGS.intersection(extra)
        if colliding_params:
            # Transfer colliding parameters from ``extra`` to ``extra_bypass``.
            extra_bypass = {pid: extra.pop(pid) for pid in colliding_params}
            # Monkeypatch the original command's ``main()`` call to pass extra
            # parameter for ``Context`` initialization. Because we cannot simply add
            # colliding parameter IDs to ``**extra``.
            extra_params_bypass = patch.object(cli, "main", partial(cli.main, **extra_bypass))

        with extra_params_bypass:
            result = super().invoke(
                    cli=cli,
                    args=args,
                    input=input,
                    env=env,
                    catch_exceptions=catch_exceptions,
                    color=isolation_color,
                    **extra,
                )

        # ``color`` has been explicitely set to ``False``, so strip all ANSI codes.
        if color is False:
            result.stdout_bytes = strip_ansi(result.stdout_bytes)
            result.stderr_bytes = strip_ansi(result.stderr_bytes)

        print_cli_run(
            [self.get_default_prog_name(cli)] + list(args),
            result.output,
            result.stderr,
            result.exit_code,
        )

        if result.exception:
            print(ExceptionInfo.from_exc_info(*result.exc_info).get_formatted())

        return result