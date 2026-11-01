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
"""Runner executing the bodies of the `click:*` directives.

{class}`ClickRunner` runs every block of a document in one shared namespace, and
returns what a terminal would show for it: the invocations, the input, the
output, the prompts and the tracebacks. The `exec` plumbing around it lives here
too: the redirected `subprocess.call`, the program name read off a command line,
and the `^D` that {class}`TerminatedEchoingStdin` echoes.

```{seealso}
Adapted, like the directives of {mod}`click_extra.sphinx.click`, from
[Pallets' Sphinx Themes](https://github.com/pallets/pallets-sphinx-themes/blob/main/src/pallets_sphinx_themes/themes/click/domain.py),
[released under a BSD-3-Clause license](https://github.com/pallets/pallets-sphinx-themes/blob/main/LICENSE.txt).
```
"""

from __future__ import annotations

import ast
import contextlib
import logging
import re
import subprocess
import sys
import tempfile
from functools import partial

import click
from click.testing import CliRunner, EchoingStdin
from sphinx.directives import SphinxDirective

from .._utils import patch_attr
from ..color import forced_color
from ..execution import format_cli_prompt, is_windows
from ..logging import DEFAULT_LEVEL
from ..testing import isolated_filesystem
from ..theme import NOCOLOR_THEME
from ..version import reset_version_resolution
from ._base import PLACEHOLDER_FILE, compile_directive, directive_source

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Literal


PROMPT_SIGIL = "$"
"""Sigil a block draws before the command it ran.

Fixed rather than taken from {data}`~click_extra.execution.PROMPT`, which
answers to the platform the build runs on: a page would otherwise prompt with a
`>` for every reader whose documentation was built on Windows. A capture drawn
as another terminal swaps it for that terminal's own, see
{class}`~click_extra.capture.presets.TerminalPreset`.

Passed as the `prompt` argument of
{func}`~click_extra.execution.format_cli_prompt`, which is what builds the line
for both the results code block and the SVG capture drawn from it.
"""


_INTERPRETER_RE = re.compile(r"(?:^|/)(?:python|pypy)[\d.]*$")
"""Match the first word of a command line that only *runs* a program.

`python -m my-cli` is typed as three words but names `my-cli`, which is how
Click derives its own `prog_name` too. Every other multi-word command line
names a program whose words all belong to it, `click-extra wrap` being the one
these pages document.
"""


class TerminatedEchoingStdin(EchoingStdin):
    r"""Like `click.testing.EchoingStdin` but adds a visible
    `^D` in place of the EOT character (`\x04`).

    {meth}`ClickRunner.invoke` adds `\x04` when `terminate_input=True`.
    """

    def _echo(self, rv: bytes) -> bytes:
        # A read past the end of the input returns no byte at all.
        eof = rv.endswith(b"\x04")

        if eof:
            rv = rv[:-1]

        if not self._paused:
            self._output.write(rv)

            if eof:
                self._output.write(b"^D\n")

        return rv


@contextlib.contextmanager
def patch_subprocess():
    """Patch subprocess to work better with {meth}`ClickRunner.invoke`.

    `subprocess.call` output is redirected to `click.echo` so it
    shows up in the example output.

    ```{caution}
    The replacement is installed on the `subprocess` module itself
    (not thread-local), so for the duration of the `with` block any
    other code in the same process that calls `subprocess.call` sees
    the patched version. With `parallel_read_safe = True` declared
    on {class}`~click_extra.sphinx.click_reference.ClickDomain`, a parallel
    reader running concurrently on a different document gets the patched
    `subprocess.call` too.
    The redirection is benign (output goes to `click.echo`) but the
    race is real, and the parallel-safe claim is weaker than it
    looks for documents that themselves shell out via
    `subprocess.call`.
    ```
    """

    def dummy_call(*args, **kwargs):
        with tempfile.TemporaryFile("wb+") as f:
            kwargs["stdout"] = f
            kwargs["stderr"] = f
            rv = subprocess.Popen(*args, **kwargs).wait()
            f.seek(0)
            click.echo(f.read().decode("UTF-8", "replace").rstrip())
        return rv

    with patch_attr(subprocess, "call", dummy_call):
        yield


def program_from_command_line(command_line: str) -> str:
    """The program name Click is given for a command line a block displays.

    A block documenting a multi-word program has to hand Click all of it: the
    command reads its own name back out of the context, for its usage line and
    for any output quoting the invocation that produced it, like the provenance
    header of a {doc}`Carapace spec </carapace>`. Handing over the last word alone
    makes an image contradict the prompt drawn right above it.

    Only an interpreter prefix is dropped, since it names no program: see
    {data}`_INTERPRETER_RE`.
    """
    first, _, rest = command_line.partition(" ")
    if rest and _INTERPRETER_RE.search(first):
        return command_line.rsplit(" ", 1)[-1]
    return command_line


def _resolve_run_capture(
    configured: Literal["sys", "fd"],
) -> Literal["sys", "fd"]:
    """Degrade a preferred stream-capture mode to one the platform supports.

    `"fd"` backs the captured streams with a real file descriptor so a command
    writing through `sys.stdout.fileno()` renders (see {class}`ClickRunner`), but
    Windows has no Unix file descriptors and Click rejects `capture="fd"` there.
    Degrading `"fd"` to `"sys"` on Windows lets the documentation build proceed:
    such fileno-writing commands do not render, instead of aborting the whole
    build.

    Applies to the `click_extra_run_capture` `conf.py` value and to the default of
    {class}`ClickRunner`, never to a mode a caller passes it explicitly.
    """
    if configured == "fd" and is_windows():
        return "sys"
    return configured


class ClickRunner(CliRunner):
    """A sub-class of {class}`click.testing.CliRunner` for Sphinx directive execution.

    Produces unfiltered ANSI codes so that the directives of
    {mod}`click_extra.sphinx.click` can render colors in the HTML output. Because
    Click Extra executes the documented command here, {meth}`invoke` forces color
    across both color systems a CLI might use:
    `color=True` covers Click's (`should_strip_ansi`), and
    {func}`~click_extra.color.forced_color` sets `FORCE_COLOR` for Rich's (which
    `rich-click` uses and `color=True` never reaches). The MkDocs plugin shares the
    latter lever but cannot pass `color=True`, since it patches a renderer it never
    executes.

    The runner defaults to `capture="fd"`, overridable through the
    `click_extra_run_capture` `conf.py` value, so a documented command that writes
    through `sys.stdout.fileno()` is captured and rendered, instead of aborting the
    build with {exc}`io.UnsupportedOperation`. On Windows, where fd-backed streams
    are not supported, the default falls back to `capture="sys"`.
    """

    def __init__(self, capture: Literal["sys", "fd"] | None = None) -> None:
        # Click defaults to "sys", which keeps a command from clobbering the
        # stdout of the test runner hosting it. A documentation build hosts no
        # test runner, so it takes "fd".
        super().__init__(echo_stdin=True, capture=capture or _resolve_run_capture("fd"))
        self.namespace = {"click": click, "__file__": PLACEHOLDER_FILE}
        # How the root logger is set up before the document runs any code belongs
        # to the build. See `without_build_logging`.
        root = logging.getLogger()
        self.build_handlers = tuple(root.handlers)
        self.build_level = root.level

    @contextlib.contextmanager
    def without_build_logging(self) -> Generator[None, None, None]:
        """Take the logging setup of the build off the `root` logger for the block.

        A build is one process, shared with Sphinx, its extensions and its theme,
        and any of them may set the `root` logger up: the Furo theme depends on
        `accessible-pygments`, which calls `logging.basicConfig()` when imported,
        and so gives the `root` logger a handler and the `INFO` level.

        A documented command adds the handler of Click Extra beside the ones it
        finds, so each of its records would print a second time, in the format of
        the build. It also leaves the `root` logger the level it found, so the one
        of the build would let through the records a command logs before its
        verbosity options apply. The shell of a reader has none of this: the
        `root` logger holds no handler there, at
        {data}`~click_extra.logging.DEFAULT_LEVEL`.

        A handler the code of the document attached itself, or a level it set, is
        not of the build, and stays in place.
        """
        root = logging.getLogger()
        hidden = [h for h in self.build_handlers if h in root.handlers]
        for handler in hidden:
            root.removeHandler(handler)
        level = root.level
        if level == self.build_level:
            root.setLevel(DEFAULT_LEVEL.value)
        try:
            yield
        finally:
            if level == self.build_level:
                root.setLevel(level)
            for handler in hidden:
                root.addHandler(handler)

    @contextlib.contextmanager
    def isolation(self, *args, **kwargs):
        """Echo a `^D` marker at the end of the isolated stdin.

        ```{todo}
        Delete {class}`TerminatedEchoingStdin` and this override once the Click
        floor reaches the release that ships
        [pallets/click#3878](https://github.com/pallets/click/pull/3878), targeted
        at `8.6.0`: `CliRunner(echo_stdin=True)` then echoes the EOT byte as `^D`
        itself.
        ```
        """
        with super().isolation(*args, **kwargs) as streams:
            # Click wraps the echoing buffer it built in the text stream it binds
            # to sys.stdin, so swapping the class of that buffer is safe: the
            # wrapper is the only handle on it.
            sys.stdin.buffer.__class__ = TerminatedEchoingStdin
            yield streams

    def invoke(  # type: ignore[override]
        self,
        cli,
        args=None,
        prog_name=None,
        input=None,
        terminate_input=False,
        env=None,
        _output_lines=None,
        _show_prompt=True,
        **extra,
    ) -> click.testing.Result:
        """Like `CliRunner.invoke` but displays what the user
        would enter in the terminal for env vars, command arguments, and
        prompts.

        :param terminate_input: Whether to display `^D` after a list of
            input.
        :param _output_lines: A list used internally to collect lines to
            be displayed.
        :param _show_prompt: Whether to draw the invocation above the output.
            Set from the directive's `:show-prompt:` / `:hide-prompt:` options,
            see {attr}`~click_extra.sphinx.click.ClickDirective.show_prompt`.
        """
        output_lines = _output_lines if _output_lines is not None else []

        args = args or []

        # A build renders many commands in one process, so a version resolved
        # by an earlier render (the man-page hook runs before any page is read)
        # would stand for every block below it. Each documented invocation gets
        # the reading a reader's own shell would give it.
        reset_version_resolution(cli)

        if prog_name is None:
            prog_name = cli.name.replace("_", "-")

        if _show_prompt:
            # The same renderer the SVG captures draw their prompt with, so a
            # block and its `:screenshot:` cannot word the invocation
            # differently. `NOCOLOR_THEME` keeps the line plain: the results
            # block is lexed as `ansi-shell-session`, which highlights the
            # prompt itself, and ANSI of our own would fight it.
            output_lines.append(
                format_cli_prompt(
                    (prog_name, *args),
                    extra_env=dict(sorted(env.items())) if env else None,
                    theme=NOCOLOR_THEME,
                    prompt=PROMPT_SIGIL,
                )
            )
        prog_name = program_from_command_line(prog_name)

        if isinstance(input, (tuple, list)):
            input = "\n".join(input) + "\n"

            if terminate_input:
                input += "\x04"

        # `color=True` keeps ANSI in Click's color system: it flips
        # `should_strip_ansi`, which CliRunner otherwise leaves stripping on its
        # non-TTY buffer. But rich-click renders through Rich's Console, a separate
        # system that ignores `should_strip_ansi` and only honors `FORCE_COLOR`, so
        # `forced_color()` sets that too. Together they cover both color systems a
        # documented CLI might use.
        with forced_color(), self.without_build_logging():
            result = super().invoke(
                cli=cli,
                args=args,
                input=input,
                env=env,
                prog_name=prog_name,
                color=True,
                **extra,
            )
        output_lines.extend(result.output.splitlines())
        return result

    def execute_source(self, directive: SphinxDirective) -> None:
        """Execute the given code, adding it to the runner's namespace."""
        code = compile_directive(directive)
        with patch_subprocess():
            exec(code, self.namespace)

    def run_cli(self, directive: SphinxDirective) -> list[str]:
        """Execute the body of `directive` and return what a terminal would show.

        The lines mix the invocations, the input, the output, the prompts and
        the tracebacks of every command the body ran.

        The body can call these functions without importing them:

        - {meth}`invoke()`: which is the same as {meth}`ClickRunner.invoke`
        - `isolated_filesystem()`: A context manager that changes to a temporary
          directory while executing the block.

        :raises RuntimeError: when the body assigns a variable named like one of
            these functions, naming the document line that does.
        """
        source_code, location = directive_source(directive)

        buffer: list[str] = []

        # Functions available as local variables when executing the code.
        local_vars = {
            "invoke": partial(
                self.invoke,
                _output_lines=buffer,
                # Read off the directive rather than the runner: one runner
                # serves every block of a document, so the flag has to travel
                # per-invocation.
                _show_prompt=directive.show_prompt,
            ),
            # The module-level helper: Click deprecates the inherited method of
            # the runner.
            "isolated_filesystem": isolated_filesystem,
        }

        # Check for local variable conflicts.
        tree = ast.parse(source_code, location)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Store)
                and node.id in local_vars
            ):
                # Get the source lines for better error reporting.
                source_lines = source_code.splitlines()
                # Get the line number relative to the source code.
                python_lineno = node.lineno
                python_line = source_lines[python_lineno - 1]
                # Compute the absolute line number in the document.
                doc_lineno = directive.abs_content_offset + python_lineno
                raise RuntimeError(
                    f"Local variable {node.id!r} at "
                    f"{location}:{directive.name}:{doc_lineno} conflicts with "
                    f"the one automatically provided by the {directive.name} "
                    "directive.\n"
                    f"Line: {python_line}"
                )

        # The tree the conflict check walked is the code to run, so the source
        # is parsed once.
        exec(compile(tree, location, "exec"), self.namespace, local_vars)
        return buffer
