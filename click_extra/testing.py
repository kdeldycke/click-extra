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

import contextlib
import inspect
import io
import os
import shlex
import subprocess
import sys
from contextlib import nullcontext
from functools import partial
from pathlib import Path
from textwrap import indent
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    BinaryIO,
    ContextManager,
    Iterable,
    Iterator,
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
from click import formatting, termui, utils

from . import Color, Style
from .colorize import default_theme

if TYPE_CHECKING:
    from types import TracebackType

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
        extra_env_string = default_theme.envvar(
            "".join(f"{k}={v} " for k, v in extra_env.items()),
        )

    cmd_str = default_theme.invoked_command(" ".join(cmd_args))

    return f"{PROMPT}{extra_env_string}{cmd_str}"


def print_cli_run(
    args: Iterable[str],
    result: click.testing.Result | subprocess.CompletedProcess,
    env: EnvVars | None = None,
) -> None:
    """Prints the full simulation of CLI execution, including output.

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

        if isinstance(result, ExtraResult):
            output = result.output

    elif isinstance(result, subprocess.CompletedProcess):
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode

    # Render the execution trace.
    print()
    print(prompt)
    if output:
        print(f"{PROMPT}{Style(fg=Color.blue)('<output>')} stream:")
        print(indent(output, INDENT))
    if stdout:
        print(f"{PROMPT}{Style(fg=Color.green)('<stdout>')} stream:")
        print(indent(stdout, INDENT))
    if stderr:
        print(f"{PROMPT}{Style(fg=Color.red)('<stderr>')} stream:")
        print(indent(stderr, INDENT))
    if exit_code is not None:
        print(f"{PROMPT}{Style(fg=Color.yellow)('Exit code:')} {exit_code}")
    print()


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


def run_cmd(
    *args: str,
    extra_env: EnvVars | None = None,
    print_output: bool = True,
) -> tuple[int, str, str]:
    """Run a system command, print output and return results."""
    result = subprocess.run(
        args,
        capture_output=True,
        encoding="utf-8",
        env=cast("subprocess._ENV", env_copy(extra_env)),
    )
    if print_output:
        print_cli_run(args, result, env=extra_env)
    return result.returncode, result.stdout, result.stderr


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


class StreamMixer:
    """Mixes ``<stdout>`` and ``<stderr>`` streams if ``mix_stderr=True``.

    The result is available in the ``output`` attribute.

    If ``mix_stderr=False``, the ``<stdout>`` and ``<stderr>`` streams are kept
    independent and the ``output`` is the same as the ``<stdout>`` stream.

    .. caution::
        This has been `proposed upstream to Click project
        <https://github.com/pallets/click/pull/2523>`_ but has not been merged yet.
    """

    def __init__(self, mix_stderr: bool) -> None:
        if not mix_stderr:
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()
            self.output = self.stdout

        else:
            self.output = io.BytesIO()
            self.stdout = BytesIOCopy(copy_to=self.output)
            self.stderr = BytesIOCopy(copy_to=self.output)


class ExtraResult(click.testing.Result):
    """Like ``click.testing.Result``, with finer ``<stdout>`` and ``<stderr>`` streams.

    .. caution::
        This has been `proposed upstream to Click project
        <https://github.com/pallets/click/pull/2523>`_ but has not been merged yet.
    """

    stderr_bytes: bytes
    """Makes ``stderr_bytes`` mandatory."""

    def __init__(
        self,
        runner: click.testing.CliRunner,
        stdout_bytes: bytes,
        stderr_bytes: bytes,
        output_bytes: bytes,
        return_value: Any,
        exit_code: int,
        exception: BaseException | None,
        exc_info: tuple[type[BaseException], BaseException, TracebackType]
        | None = None,
    ) -> None:
        """Same as original but adds ``output_bytes`` parameter.

        Also makes ``stderr_bytes`` mandatory.
        """
        self.output_bytes = output_bytes
        super().__init__(
            runner=runner,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            return_value=return_value,
            exit_code=exit_code,
            exception=exception,
            exc_info=exc_info,
        )

    @property
    def output(self) -> str:
        """The terminal output as unicode string, as the user would see it.

        .. caution::
            Contrary to original ``click.testing.Result.output``, it is not a proxy for
            ``self.stdout``. It now possess its own stream to mix ``<stdout>`` and
            ``<stderr>`` depending on the ``mix_stderr`` value.
        """
        return self.output_bytes.decode(self.runner.charset, "replace").replace(
            "\r\n",
            "\n",
        )

    @property
    def stderr(self) -> str:
        """The standard error as unicode string.

        .. caution::
            Contrary to original ``click.testing.Result.stderr``, it no longer raise an
            exception, and always returns the ``<stderr>`` string.
        """
        return self.stderr_bytes.decode(self.runner.charset, "replace").replace(
            "\r\n",
            "\n",
        )


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

    @contextlib.contextmanager
    def isolation(  # type: ignore[override]
        self,
        input: str | bytes | IO[Any] | None = None,
        env: Mapping[str, str | None] | None = None,
        color: bool = False,
    ) -> Iterator[tuple[io.BytesIO, io.BytesIO, io.BytesIO]]:
        """Copy of ``click.testing.CliRunner.isolation()`` with extra features.

        - An additional output stream is returned, which is a mix of ``<stdout>`` and
          ``<stderr>`` streams if ``mix_stderr=True``.

        - Always returns the ``<stderr>`` stream.

        .. caution::
            This is a hard-copy of the modified ``isolation()`` method `from click#2523
            PR
            <https://github.com/pallets/click/pull/2523/files#diff-b07fd6fad9f9ea8be5cbcbeaf34c956703b929b2de95c56229e77c328a7c6010>`_
            which has not been merged upstream yet.

        .. todo::
            Reduce the code duplication here by using clever monkeypatching?
        """
        bytes_input = click.testing.make_input_stream(input, self.charset)
        echo_input = None

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_forced_width = formatting.FORCED_WIDTH
        formatting.FORCED_WIDTH = 80

        env = self.make_env(env)

        stream_mixer = StreamMixer(mix_stderr=self.mix_stderr)

        if self.echo_stdin:
            bytes_input = echo_input = cast(
                BinaryIO,
                click.testing.EchoingStdin(bytes_input, stream_mixer.stdout),
            )

        sys.stdin = text_input = click.testing._NamedTextIOWrapper(
            bytes_input,
            encoding=self.charset,
            name="<stdin>",
            mode="r",
        )

        if self.echo_stdin:
            # Force unbuffered reads, otherwise TextIOWrapper reads a
            # large chunk which is echoed early.
            text_input._CHUNK_SIZE = 1  # type: ignore

        sys.stdout = click.testing._NamedTextIOWrapper(
            stream_mixer.stdout,
            encoding=self.charset,
            name="<stdout>",
            mode="w",
        )

        sys.stderr = click.testing._NamedTextIOWrapper(
            stream_mixer.stderr,
            encoding=self.charset,
            name="<stderr>",
            mode="w",
            errors="backslashreplace",
        )

        @click.testing._pause_echo(echo_input)  # type: ignore[arg-type]
        def visible_input(prompt: str | None = None) -> str:
            sys.stdout.write(prompt or "")
            val = text_input.readline().rstrip("\r\n")
            sys.stdout.write(f"{val}\n")
            sys.stdout.flush()
            return val

        @click.testing._pause_echo(echo_input)  # type: ignore[arg-type]
        def hidden_input(prompt: str | None = None) -> str:
            sys.stdout.write(f"{prompt or ''}\n")
            sys.stdout.flush()
            return text_input.readline().rstrip("\r\n")

        @click.testing._pause_echo(echo_input)  # type: ignore[arg-type]
        def _getchar(echo: bool) -> str:
            char = sys.stdin.read(1)

            if echo:
                sys.stdout.write(char)

            sys.stdout.flush()
            return char

        default_color = color

        def should_strip_ansi(
            stream: IO[Any] | None = None,
            color: bool | None = None,
        ) -> bool:
            if color is None:
                return not default_color
            return not color

        old_visible_prompt_func = termui.visible_prompt_func
        old_hidden_prompt_func = termui.hidden_prompt_func
        old__getchar_func = termui._getchar
        old_should_strip_ansi = utils.should_strip_ansi
        termui.visible_prompt_func = visible_input
        termui.hidden_prompt_func = hidden_input
        termui._getchar = _getchar
        utils.should_strip_ansi = should_strip_ansi

        old_env = {}
        try:
            for key, value in env.items():
                old_env[key] = os.environ.get(key)
                if value is None:
                    with contextlib.suppress(Exception):
                        del os.environ[key]

                else:
                    os.environ[key] = value
            yield (stream_mixer.stdout, stream_mixer.stderr, stream_mixer.output)
        finally:
            for key, value in old_env.items():
                if value is None:
                    with contextlib.suppress(Exception):
                        del os.environ[key]

                else:
                    os.environ[key] = value
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin
            termui.visible_prompt_func = old_visible_prompt_func
            termui.hidden_prompt_func = old_hidden_prompt_func
            termui._getchar = old__getchar_func
            utils.should_strip_ansi = old_should_strip_ansi
            formatting.FORCED_WIDTH = old_forced_width

    def invoke2(
        self,
        cli: click.core.BaseCommand,
        args: str | Sequence[str] | None = None,
        input: str | bytes | IO[Any] | None = None,
        env: Mapping[str, str | None] | None = None,
        catch_exceptions: bool = True,
        color: bool = False,
        **extra: Any,
    ) -> ExtraResult:
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

        return ExtraResult(
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
        cli: click.core.BaseCommand,
        *args: Arg | NestedArgs,
        input: str | bytes | IO | None = None,
        env: EnvVars | None = None,
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
