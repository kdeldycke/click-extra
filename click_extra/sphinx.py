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
"""Helpers and utilities for Sphinx rendering of CLI based on Click Extra.

.. todo::
    Add support for plain MyST directives to remove the need of wrapping rST into an
    ``{eval-rst}`` block. Ideally, this would allow for the following simpler syntax in
    MyST:

    .. code-block:: markdown

        ```{click-example}
        from click_extra import echo, extra_command, option, style

        @extra_command
        @option("--name", prompt="Your name", help="The person to greet.")
        def hello_world(name):
            "Simple program that greets NAME."
            echo(f"Hello, {style(name, fg='red')}!")
        ```

    .. code-block:: markdown

        ```{click-run}
        invoke(hello_world, args=["--help"])
        ```

.. todo::
    Fix the need to have both ``.. click:example::`` and ``.. click:run::`` directives
    in the same ``{eval-rst}`` block in MyST. This is required to have both directives
    shares states and context.

.. seealso::
    This is based on `Pallets' Sphinx Themes
    <https://github.com/pallets/pallets-sphinx-themes/blob/main/src/pallets_sphinx_themes/themes/click/domain.py>`_,
    `released under a BSD-3-Clause license
    <https://github.com/pallets/pallets-sphinx-themes/tree/main?tab=BSD-3-Clause-1-ov-file#readme>`_.

    Compared to the latter, it:

    - Adds rendering of ANSI codes in CLI results.
    - Has better error handling and reporting which helps you pinpoint the failing
      code in your documentation.
"""

from __future__ import annotations

try:
    import sphinx  # noqa: F401
except ImportError:
    raise ImportError(
        "You need to install click_extra[sphinx] dependency group to use this module."
    )

import contextlib
import shlex
import subprocess
import sys
import tempfile
from functools import partial
from typing import TYPE_CHECKING

import click
from click.testing import EchoingStdin
from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.statemachine import ViewList
from sphinx.domains import Domain
from sphinx.highlighting import PygmentsBridge

from . import __version__
from .pygments import AnsiHtmlFormatter
from .testing import ExtraCliRunner

if TYPE_CHECKING:
    from docutils import nodes
    from sphinx.application import Sphinx
    from sphinx.util.typing import ExtensionMetadata


class EofEchoingStdin(EchoingStdin):
    """Like :class:`click.testing.EchoingStdin` but adds a visible
    ``^D`` in place of the EOT character (``\x04``).

    :meth:`ExampleRunner.invoke` adds ``\x04`` when
    ``terminate_input=True``.
    """

    def _echo(self, rv: bytes) -> bytes:
        eof = rv[-1] == b"\x04"[0]

        if eof:
            rv = rv[:-1]

        if not self._paused:
            self._output.write(rv)

            if eof:
                self._output.write(b"^D\n")

        return rv


@contextlib.contextmanager
def patch_modules():
    """Patch modules to work better with :meth:`ExampleRunner.invoke`.

    ``subprocess.call` output is redirected to ``click.echo`` so it
    shows up in the example output.
    """
    old_call = subprocess.call

    def dummy_call(*args, **kwargs):
        with tempfile.TemporaryFile("wb+") as f:
            kwargs["stdout"] = f
            kwargs["stderr"] = f
            rv = subprocess.Popen(*args, **kwargs).wait()
            f.seek(0)
            click.echo(f.read().decode("utf-8", "replace").rstrip())
        return rv

    subprocess.call = dummy_call

    try:
        yield
    finally:
        subprocess.call = old_call


class ExampleRunner(ExtraCliRunner):
    """:class:`click.testing.CliRunner` with additional features.

    This class inherits from ``click_extra.testing.ExtraCliRunner`` to have full
    control of contextual color settings by the way of the ``color`` parameter. It also
    produce unfiltered ANSI codes so that the ``Directive`` sub-classes below can
    render colors in the HTML output.
    """

    force_color = True
    """Force color rendering in ``invoke`` calls."""

    def __init__(self):
        super().__init__(echo_stdin=True)
        self.namespace = {"click": click, "__file__": "dummy.py"}

    @contextlib.contextmanager
    def isolation(self, *args, **kwargs):
        iso = super().isolation(*args, **kwargs)

        with iso as streams:
            try:
                buffer = sys.stdin.buffer
            except AttributeError:
                buffer = sys.stdin

            # FIXME: We need to replace EchoingStdin with our custom
            # class that outputs "^D". At this point we know sys.stdin
            # has been patched so it's safe to reassign the class.
            # Remove this once EchoingStdin is overridable.
            buffer.__class__ = EofEchoingStdin
            yield streams

    def invoke(
        self,
        cli,
        args=None,
        prog_name=None,
        input=None,
        terminate_input=False,
        env=None,
        _output_lines=None,
        **extra,
    ):
        """Like :meth:`CliRunner.invoke` but displays what the user
        would enter in the terminal for env vars, command args, and
        prompts.

        :param terminate_input: Whether to display "^D" after a list of
            input.
        :param _output_lines: A list used internally to collect lines to
            be displayed.
        """
        output_lines = _output_lines if _output_lines is not None else []

        if env:
            for key, value in sorted(env.items()):
                value = shlex.quote(value)
                output_lines.append(f"$ export {key}={value}")

        args = args or []

        if prog_name is None:
            prog_name = cli.name.replace("_", "-")

        output_lines.append(f"$ {prog_name} {shlex.join(args)}".rstrip())
        # remove "python" from command
        prog_name = prog_name.rsplit(" ", 1)[-1]

        if isinstance(input, (tuple, list)):
            input = "\n".join(input) + "\n"

            if terminate_input:
                input += "\x04"

        result = super().invoke(
            cli=cli, args=args, input=input, env=env, prog_name=prog_name, **extra
        )
        output_lines.extend(result.output.splitlines())
        return result

    def declare_example(self, source_code: str, location: str) -> None:
        """Execute the given code, adding it to the runner's namespace."""
        with patch_modules():
            code = compile(source_code, location, "exec")
            exec(code, self.namespace)

    def run_example(self, source_code: str, location: str) -> None:
        """Run commands by executing the given code, returning the lines
        of input and output. The code should be a series of the
        following functions:

        *   :meth:`invoke`: Invoke a command, adding env vars, input,
            and output to the output.
        *   :meth:`isolated_filesystem`: A context manager that changes
            to a temporary directory while executing the block.
        """
        code = compile(source_code, location, "exec")
        buffer = []
        invoke = partial(self.invoke, _output_lines=buffer)

        exec(
            code,
            self.namespace,
            {
                "invoke": invoke,
                "isolated_filesystem": self.isolated_filesystem,
            },
        )
        return buffer

    def close(self) -> None:
        """Clean up the runner once the document has been read."""
        pass


class ClickDirective(Directive):
    has_content = True
    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = False

    code_block_dialect: str
    """Pygments dialect to use to render the code block."""

    render_source: bool = True
    """Whether to render the source code of the example in a code block."""
    render_results: bool = True
    """Whether to render the results of the example in a code block."""

    def example_runner(self) -> ExampleRunner:
        """Get or create the :class:`ExampleRunner` instance associated with
        a document.
        """
        runner = getattr(self.state.document, "click_example_runner", None)
        if runner is None:
            runner = self.state.document.click_example_runner = ExampleRunner()
        return runner

    def run(self) -> list[nodes.Node]:
        doc = ViewList()
        runner = self.example_runner()

        location = "{0}:line {1}".format(
            *self.state_machine.get_source_and_line(self.lineno)
        )
        run_func = runner.run_example if self.render_results else runner.declare_example

        try:
            results = run_func("\n".join(self.content), location)
        except BaseException:
            runner.close()
            raise

        doc.append(f".. code-block:: {self.code_block_dialect}", "")
        doc.append("", "")

        if self.render_source:
            for line in self.content:
                doc.append(" " + line, "")

        if self.render_results:
            for line in results:
                doc.append(" " + line, "")

        node = nodes.section()
        self.state.nested_parse(doc, self.content_offset, node)
        return node.children


class DeclareExampleDirective(ClickDirective):
    """Directive to declare a Click CLI example.

    This directive is used to declare a Click CLI example in the
    documentation. It renders the source code of the example in a
    Python code block.
    """

    code_block_dialect = "python"
    render_source = True
    render_results = False


class RunExampleDirective(ClickDirective):
    """Directive to run a Click CLI example.

    This directive is used to run a Click CLI example in the
    documentation. It renders the results of running the example in a
    shell session code block supporting ANSI colors.
    """

    code_block_dialect = "ansi-shell-session"
    render_source = False
    render_results = True


class ClickDomain(Domain):
    """Setup new directives under the same ``.. click:`` namespace:

    - ``.. click:example::`` which renders a Click CLI source code
    - ``.. click:run::`` which renders the results of running a Click CLI
    """

    name = "click"
    label = "Click"
    directives = {
        "example": DeclareExampleDirective,
        "run": RunExampleDirective,
    }


def delete_example_runner_state(app: Sphinx, doctree: nodes.document) -> None:
    """Close and remove the :class:`ExampleRunner` instance once the
    document has been read.
    """
    runner = getattr(doctree, "click_example_runner", None)

    if runner is not None:
        runner.close()
        del doctree.click_example_runner


def setup(app: Sphinx) -> ExtensionMetadata:
    """Register new directives, augmented with ANSI coloring.

    .. danger::
        This function activates some monkey-patches:

        - ``sphinx.highlighting.PygmentsBridge`` is updated to set its default HTML
          formatter to an ANSI capable one for the whole Sphinx app.

    """
    # Set Sphinx's default HTML formatter to an ANSI capable one.
    PygmentsBridge.html_formatter = AnsiHtmlFormatter

    # Register directives to Sphinx.
    app.add_domain(ClickDomain)
    app.connect("doctree-read", delete_example_runner_state)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
