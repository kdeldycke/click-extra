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

import inspect
import io
import shlex
import subprocess
import sys
from contextlib import nullcontext
from functools import partial
from pathlib import Path
from textwrap import indent
from typing import (
    IO,
    Any,
    ContextManager,
    Iterable,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Union,
    cast,
)
from unittest.mock import patch

import click
import click.testing
from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from boltons.tbutils import ExceptionInfo

from . import Color, Style
from .colorize import default_theme
from .envvar import TEnvVars

PROMPT = "► "
INDENT = " " * len(PROMPT)
"""Constants for rendering of CLI execution."""


TArg = str | Path | None
TArgs = Iterable[TArg]
TNestedArgs = Iterable[TArg | Iterable["TNestedArgs"]]
"""Types for arbitrary nested CLI arguments.

Arguments can be ``str``, :py:class:`pathlib.Path` objects or ``None`` values.
"""


def args_cleanup(*args: TArg | TNestedArgs) -> tuple[str, ...]:
    """Flatten recursive iterables, remove all ``None``, and cast each element to
    strings.

    Helps serialize :py:class:`pathlib.Path` and other objects.

    It also allows for nested iterables and ``None`` values as CLI arguments for
    convenience. We just need to flatten and filters them out.
    """
    return tuple(str(arg) for arg in flatten(args) if arg is not None)


def format_cli_prompt(
    cmd_args: Iterable[str],
    extra_env: TEnvVars | None = None,
) -> str:
    """Simulate the console prompt used to invoke the CLI."""
    extra_env_string = ""
    if extra_env:
        extra_env_string = default_theme.envvar(
            "".join(f"{k}={v} " for k, v in extra_env.items()),
        )

    cmd_str = default_theme.invoked_command(" ".join(cmd_args))

    return f"{PROMPT}{extra_env_string}{cmd_str}"


def render_cli_run(
    args: Iterable[str],
    result: click.testing.Result | subprocess.CompletedProcess,
    env: TEnvVars | None = None,
) -> str:
    """Generates the full simulation of CLI execution, including output.

    Mostly used to print debug traces to user or in test results.
    """
    prompt = format_cli_prompt(args, env)
    stdout = ""
    stderr = ""
    output = ""
    exit_code = None

    if isinstance(result, click.testing.Result):
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.exit_code
        output = result.output

    elif isinstance(result, subprocess.CompletedProcess):
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode

    # Render the execution trace.
    trace = prompt + "\n"
    if output:
        trace += f"{PROMPT}{Style(fg=Color.blue)('<output>')} stream:\n"
        trace += indent(output, INDENT) + "\n"
    if stdout:
        trace += f"{PROMPT}{Style(fg=Color.green)('<stdout>')} stream:\n"
        trace += indent(stdout, INDENT) + "\n"
    if stderr:
        trace += f"{PROMPT}{Style(fg=Color.red)('<stderr>')} stream:\n"
        trace += indent(stderr, INDENT) + "\n"
    if exit_code is not None:
        trace += f"{PROMPT}{Style(fg=Color.yellow)('Exit code:')} {exit_code}\n"
    return trace + "\n"


def print_cli_run(
    args: Iterable[str],
    result: click.testing.Result | subprocess.CompletedProcess,
    env: TEnvVars | None = None,
) -> None:
    """Prints the full simulation of CLI execution, including output."""
    print(render_cli_run(args, result, env))


INVOKE_ARGS = set(inspect.getfullargspec(click.testing.CliRunner.invoke).args)
"""Parameter IDs of ``click.testing.CliRunner.invoke()``.

We need to collect them to help us identify which extra parameters passed to
``invoke()`` collides with its original signature.

.. warning::
    This has been `reported upstream to Click project
    <https://github.com/pallets/click/issues/2110>`_ but has been rejected and not
    considered an issue worth fixing.
"""


class BytesIOCopy(io.BytesIO):
    """Patch ``io.BytesIO`` to let the written stream be copied to another.

    .. caution::
        This has been `proposed upstream to Click project
        <https://github.com/pallets/click/pull/2523>`_ but has not been merged yet.
    """

    def __init__(self, copy_to: io.BytesIO) -> None:
        super().__init__()
        self.copy_to = copy_to

    def flush(self) -> None:
        super().flush()
        self.copy_to.flush()

    def write(self, b) -> int:
        self.copy_to.write(b)
        return super().write(b)


class ExtraCliRunner(click.testing.CliRunner):
    """Augment :class:`click.testing.CliRunner` with extra features and bug fixes."""

    force_color: bool = False
    """Global class attribute to override the ``color`` parameter in ``invoke``.

    .. note::
        This was initially developed to `force the initialization of the runner during
        the setup of Sphinx new directives <sphinx#click_extra.sphinx.setup>`_. This
        was the only way we found, as to patch some code we had to operate at the class
        level.
    """

    def invoke2(
        self,
        cli: click.core.Command,
        args: str | Sequence[str] | None = None,
        input: str | bytes | IO[Any] | None = None,
        env: Mapping[str, str | None] | None = None,
        catch_exceptions: bool = True,
        color: bool = False,
        **extra: Any,
    ) -> click.testing.Result:
        """Copy of ``click.testing.CliRunner.invoke()`` with extra ``<output>`` stream.

        .. caution::
            This is a hard-copy of the modified ``invoke()`` method `from click#2523 PR
            <https://github.com/pallets/click/pull/2523/files#diff-b07fd6fad9f9ea8be5cbcbeaf34c956703b929b2de95c56229e77c328a7c6010>`_
            which has not been merged upstream yet.

        .. todo::
            Reduce the code duplication here by using clever monkeypatching?
        """
        exc_info = None
        with self.isolation(input=input, env=env, color=color) as outstreams:
            return_value = None
            exception: BaseException | None = None
            exit_code = 0

            if isinstance(args, str):
                args = shlex.split(args)

            try:
                prog_name = extra.pop("prog_name")
            except KeyError:
                prog_name = self.get_default_prog_name(cli)

            try:
                return_value = cli.main(args=args or (), prog_name=prog_name, **extra)
            except SystemExit as e:
                exc_info = sys.exc_info()
                e_code = cast(Optional[Union[int, Any]], e.code)

                if e_code is None:
                    e_code = 0

                if e_code != 0:
                    exception = e

                if not isinstance(e_code, int):
                    sys.stdout.write(str(e_code))
                    sys.stdout.write("\n")
                    e_code = 1

                exit_code = e_code

            except Exception as e:
                if not catch_exceptions:
                    raise
                exception = e
                exit_code = 1
                exc_info = sys.exc_info()
            finally:
                sys.stdout.flush()
                stdout = outstreams[0].getvalue()
                stderr = outstreams[1].getvalue()
                output = outstreams[2].getvalue()

        return click.testing.Result(
            runner=self,
            stdout_bytes=stdout,
            stderr_bytes=stderr,
            output_bytes=output,
            return_value=return_value,
            exit_code=exit_code,
            exception=exception,
            exc_info=exc_info,  # type: ignore
        )

    def invoke(  # type: ignore[override]
        self,
        cli: click.core.Command,
        *args: TArg | TNestedArgs,
        input: str | bytes | IO | None = None,
        env: TEnvVars | None = None,
        catch_exceptions: bool = True,
        color: bool | Literal["forced"] | None = None,
        **extra: Any,
    ) -> click.testing.Result:
        """Same as ``click.testing.CliRunner.invoke()`` with extra features.

        - The first positional parameter is the CLI to invoke. The remaining positional
          parameters of the function are the CLI arguments. All other parameters are
          required to be named.

        - The CLI arguments can be nested iterables of arbitrary depth. This is
          `useful for argument composition of test cases with @pytest.mark.parametrize
          <https://docs.pytest.org/en/stable/example/parametrize.html>`_.

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
        cli_args = list(args)
        if "args" in extra:
            cli_args.extend(extra.pop("args"))
        # Flatten and filters out CLI arguments.
        clean_args = args_cleanup(*cli_args)

        if color == "forced":
            # Pass the color argument as an extra parameter to the invoked CLI.
            extra["color"] = True
            # TODO: investigate the possibility of forcing coloring on ``echo`` too,
            # because by default, Windows is rendered colorless:
            # https://github.com/pallets/click/blob/0c85d80/src/click/utils.py#L295-L296
            # echo_extra["color"] = True

        # The class attribute ``force_color`` overrides the ``color`` parameter.
        if self.force_color:
            isolation_color = True
        # Cast to ``bool`` to avoid passing ``None`` or ``"forced"`` to ``invoke()``.
        else:
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
            extra_params_bypass = patch.object(
                cli,
                "main",
                partial(cli.main, **extra_bypass),
            )

        with extra_params_bypass:
            result = self.invoke2(
                cli=cli,
                args=clean_args,
                input=input,
                env=env,
                catch_exceptions=catch_exceptions,
                color=isolation_color,
                **extra,
            )

        # ``color`` has been explicitly set to ``False``, so strip all ANSI codes.
        if color is False:
            result.stdout_bytes = strip_ansi(result.stdout_bytes)
            result.stderr_bytes = strip_ansi(result.stderr_bytes)
            result.output_bytes = strip_ansi(result.output_bytes)

        print_cli_run(
            [self.get_default_prog_name(cli), *clean_args],
            result,
            env=env,
        )

        if result.exception:
            print(ExceptionInfo.from_exc_info(*result.exc_info).get_formatted())

        return result
