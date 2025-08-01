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

.. seealso::
    These directives are based on `Pallets' Sphinx Themes
    <https://github.com/pallets/pallets-sphinx-themes/blob/main/src/pallets_sphinx_themes/themes/click/domain.py>`_,
    `released under a BSD-3-Clause license
    <https://github.com/pallets/pallets-sphinx-themes/tree/main?tab=BSD-3-Clause-1-ov-file#readme>`_.

    Compared to the latter, it:

    - Add support for MyST syntax.
    - Adds rendering of ANSI codes in CLI results.
    - Has better error handling and reporting which helps you pinpoint the failing
      code in your documentation.
    - Removes the ``println`` function which was used to explicitly print a blank
      line. This is no longer needed as it is now handled natively.
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
from functools import cached_property, partial
from typing import TYPE_CHECKING, Iterable

import click
from click.testing import EchoingStdin
from docutils import nodes
from docutils.statemachine import StringList
from sphinx.directives import SphinxDirective, directives
from sphinx.directives.code import CodeBlock
from sphinx.domains import Domain
from sphinx.highlighting import PygmentsBridge

from . import __version__
from .pygments import AnsiHtmlFormatter
from .testing import ExtraCliRunner

if TYPE_CHECKING:
    from typing import ClassVar

    from sphinx.application import Sphinx
    from sphinx.util.typing import ExtensionMetadata, OptionSpec


RST_INDENT = " " * 3
"""The indentation used for rST code blocks lines."""


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
    ) -> click.testing.Result:
        """Like :meth:`CliRunner.invoke` but displays what the user
        would enter in the terminal for env vars, command arguments, and
        prompts.

        :param terminate_input: Whether to display ``^D`` after a list of
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

    def run_example(self, source_code: str, location: str) -> list[str]:
        """Run commands by executing the given code, returning the lines
        of input and output. The code should be a series of the
        following functions:

        - :meth:`invoke`: Invoke a command, adding env vars, input,
          and output to the output.
        - :meth:`isolated_filesystem`: A context manager that changes
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


class ClickDirective(SphinxDirective):
    has_content = True

    required_arguments = 0
    optional_arguments = 1
    """The optional argument overrides the default Pygments language to use."""

    final_argument_whitespace = False

    option_spec: ClassVar[OptionSpec] = CodeBlock.option_spec | {
        "language": directives.unchanged_required,
        "show-source": directives.flag,
        "hide-source": directives.flag,
        "show-results": directives.flag,
        "hide-results": directives.flag,
    }
    """Options supported by this directive.

    Support the `same options
    <https://github.com/sphinx-doc/sphinx/blob/ead64df/sphinx/directives/code.py#L108-L117>`_
    as :class:`sphinx.directives.code.CodeBlock`, and some specific to Click
    directives.
    """

    default_language: str
    """Default highlighting language to use to render the code block.

    `All Pygments' languages short names <https://pygments.org/languages/>`_ are
    recognized.
    """

    default_show_source: bool = True
    """Whether to render the source code of the example in the code block."""
    default_show_results: bool = True
    """Whether to render the results of the example in the code block."""

    runner_func_id: str
    """The name of the function to call on the :class:`ExampleRunner` instance."""

    @property
    def runner(self) -> ExampleRunner:
        """Get or create the :class:`ExampleRunner` instance associated with
        a document.

        Creates one runner per document.
        """
        runner = getattr(self.state.document, "click_example_runner", None)
        if runner is None:
            runner = self.state.document.click_example_runner = ExampleRunner()
        return runner

    @cached_property
    def language(self) -> str:
        """Short name of the Pygments lexer used to highlight the code block.

        Returns, in order of precedence, the language specified in the `:language:`
        directive options, the first argument of the directive (if any), or the default
        set in the directive class.
        """
        if "language" in self.options:
            return self.options["language"]
        if self.arguments:
            return self.arguments[0]
        return self.default_language

    @cached_property
    def code_block_options(self) -> list[str]:
        """Render the options supported by Sphinx' native `code-block` directive."""
        options = []
        for option_id in CodeBlock.option_spec:
            if option_id in self.options:
                value = self.options[option_id]
                line = f":{option_id}:"
                if value:
                    line += f" {value}"
                options.append(line)
        return options

    @cached_property
    def show_source(self) -> bool:
        """Whether to show the source code of the example in the code block.

        The last occurrence of either ``show-source`` or ``hide-source`` options
        wins. If neither is set, the default is taken from ``default_show_source``.
        """
        show_source = self.default_show_source
        for option_id in self.options:
            if option_id == "show-source":
                show_source = True
            elif option_id == "hide-source":
                show_source = False
        return show_source

    @cached_property
    def show_results(self) -> bool:
        """Whether to show the results of running the example in the code block.

        The last occurrence of either ``show-results`` or ``hide-results`` options
        wins. If neither is set, the default is taken from ``default_show_results``.
        """
        show_results = self.default_show_results
        for option_id in self.options:
            if option_id == "show-results":
                show_results = True
            elif option_id == "hide-results":
                show_results = False
        return show_results

    @cached_property
    def is_myst_syntax(self) -> bool:
        """Check if the current directive is written with MyST syntax."""
        return self.state.__module__.split(".", 1)[0] == "myst_parser"

    def render_code_block(self, lines: Iterable[str], language: str) -> list[str]:
        """Render the code block with the source code and results."""
        block = []
        if not lines:
            return block

        # Initiate the code block with with its MyST or rST syntax.
        code_directive = "```{code-block}" if self.is_myst_syntax else ".. code-block::"
        block.append(f"{code_directive} {language}")

        # Re-attach each option to the code block.
        for line in self.code_block_options:
            # Indent the line in rST code block.
            block.append(line if self.is_myst_syntax else RST_INDENT + line)

        # rST code directives needs a blank line before the body of the block else the
        # first line will be interpreted as a directive option.
        if not self.is_myst_syntax:
            block.append("")

        for line in lines:
            block.append(line if self.is_myst_syntax else RST_INDENT + line)

        # In MyST, we need to close the code block.
        if self.is_myst_syntax:
            block.append("```")

        return block

    def run(self) -> list[nodes.Node]:
        assert hasattr(self.runner, self.runner_func_id), (
            f"{self.runner!r} does not have a function named {self.runner_func_id!r}."
        )
        runner_func = getattr(self.runner, self.runner_func_id)
        results = runner_func("\n".join(self.content), self.get_location())

        # If neither source code nor results are requested, we don't render anything.
        if not self.show_source and not self.show_results:
            return []

        lines = []
        if self.show_source:
            language = self.language
            # If we are running a CLI, we force rendering the source code as a
            # Python code block.
            if self.runner_func_id == "run_example":
                language = DeclareExampleDirective.default_language
            lines.extend(self.render_code_block(self.content, language))
        if self.show_results:
            lines.extend(self.render_code_block(results, self.language))

        # Convert code block lines to a Docutils node tree.
        # The section element is the main unit of hierarchy for Docutils documents.
        section = nodes.section()
        source_file, line_number = self.get_source_info()
        self.state.nested_parse(
            StringList(lines, source_file), self.content_offset, section
        )
        return section.children


class DeclareExampleDirective(ClickDirective):
    """Directive to declare a Click CLI example.

    This directive is used to declare a Click CLI example in the
    documentation. It renders the source code of the example in a
    Python code block.
    """

    default_language = "python"
    default_show_source = True
    default_show_results = False
    runner_func_id = "declare_example"


class RunExampleDirective(ClickDirective):
    """Directive to run a Click CLI example.

    This directive is used to run a Click CLI example in the
    documentation. It renders the results of running the example in a
    shell session code block supporting ANSI colors.
    """

    default_language = "ansi-shell-session"
    default_show_source = False
    default_show_results = True
    runner_func_id = "run_example"


class ClickDomain(Domain):
    """Setup new directives under the same ``click`` namespace:

    - ``click:example`` which renders a Click CLI source code
    - ``click:run`` which renders the results of running a Click CLI
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
        del doctree.click_example_runner


def setup(app: Sphinx) -> ExtensionMetadata:
    """Register new directives, augmented with ANSI coloring.

    .. caution::
        This function forces the Sphinx app to use
        ``sphinx.highlighting.PygmentsBridge`` instead of the default HTML formatter to
        add support for ANSI colors in code blocks.
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
