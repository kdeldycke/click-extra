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
"""Sphinx rendering of CLI based on Click Extra.

.. seealso::
    These directives are based on `Pallets' Sphinx Themes
    <https://github.com/pallets/pallets-sphinx-themes/blob/main/src/pallets_sphinx_themes/themes/click/domain.py>`_,
    `released under a BSD-3-Clause license
    <https://github.com/pallets/pallets-sphinx-themes/blob/main/LICENSE.txt>`_.

    Compared to the latter, it:

    - Add support for MyST syntax.
    - Adds rendering of ANSI codes in CLI results.
    - Has better error handling and reporting which helps you pinpoint the failing
      code in your documentation.
    - Removes the ``println`` function which was used to explicitly print a blank
      line. This is no longer needed as it is now handled natively.
"""

from __future__ import annotations

import ast
import contextlib
import shlex
import subprocess
import sys
import tempfile
from functools import cached_property, partial

import click
from click.testing import CliRunner, EchoingStdin
from docutils import nodes
from docutils.statemachine import StringList
from sphinx.directives import SphinxDirective, directives
from sphinx.directives.code import CodeBlock
from sphinx.util import logging

from ._base import StatelessDomain, compile_directive, make_cleanup

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import ClassVar

    from sphinx.util.typing import OptionSpec


logger = logging.getLogger(__name__)


RST_INDENT = " " * 3
"""The indentation used for rST code blocks lines."""


class TerminatedEchoingStdin(EchoingStdin):
    """Like :class:`click.testing.EchoingStdin` but adds a visible
    ``^D`` in place of the EOT character (``\x04``).

    :meth:`ClickRunner.invoke` adds ``\x04`` when ``terminate_input=True``.
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
def patch_subprocess():
    """Patch subprocess to work better with :meth:`ClickRunner.invoke`.

    ``subprocess.call`` output is redirected to ``click.echo`` so it
    shows up in the example output.

    .. caution::
        The replacement is installed on the ``subprocess`` module itself
        (not thread-local), so for the duration of the ``with`` block any
        other code in the same process that calls ``subprocess.call`` sees
        the patched version. With ``parallel_read_safe = True`` declared
        on :class:`ClickDomain`, a parallel reader running concurrently
        on a different document gets the patched ``subprocess.call`` too.
        The redirection is benign (output goes to ``click.echo``) but the
        race is real, and the parallel-safe claim is weaker than it
        looks for documents that themselves shell out via
        ``subprocess.call``.
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


class ClickRunner(CliRunner):
    """A sub-class of :class:`click.testing.CliRunner` for Sphinx directive execution.

    Produces unfiltered ANSI codes so that the ``Directive`` sub-classes below can
    render colors in the HTML output.
    """

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
            buffer.__class__ = TerminatedEchoingStdin
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
            cli=cli,
            args=args,
            input=input,
            env=env,
            prog_name=prog_name,
            color=True,
            **extra,
        )
        # TODO: Maybe we can intercept the exception here either make it:
        # - part of the output in the rendered Sphinx code block, or
        # - re-raise it so Sphinx can display it properly in its logs.
        output_lines.extend(result.output.splitlines())
        return result

    def execute_source(self, directive: SphinxDirective) -> None:
        """Execute the given code, adding it to the runner's namespace."""
        code = compile_directive(directive)
        with patch_subprocess():
            exec(code, self.namespace)  # noqa: S102

    def run_cli(self, directive: SphinxDirective) -> list[str]:
        """Execute the given ``source_code``.

        Returns a simulation of terminal execution, including a mix of input, output,
        prompts and tracebacks.

        The execution context is augmented, so you can refer directly to these
        functions in the provided ``source_code``:

        - :meth:`invoke()`: which is the same as :meth:`ClickRunner.invoke`
        - :meth:`isolated_filesystem()`: A context manager that changes to a temporary
          directory while executing the block.

        If any local variable in the provided ``source_code`` conflicts with these
        functions, a :class:`RuntimeError` is raised to help you pinpoint the issue.
        """
        # Use directive.content instead of directive.block_text as the latter
        # include the directive text itself in rST.
        source_code = "\n".join(directive.content)
        # Get the user-friendly location string as provided by Sphinx.
        location = directive.get_location()

        buffer: list[str] = []

        # Functions available as local variables when executing the code.
        local_vars = {
            "invoke": partial(self.invoke, _output_lines=buffer),
            "isolated_filesystem": self.isolated_filesystem,
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
                if directive.is_myst_syntax:
                    # In MyST, the content offset is the position of the first line
                    # of the source code, relative to the directive itself.
                    doc_lineno = (
                        directive.lineno + directive.content_offset + python_lineno
                    )
                    # XXX MyST absolute error line reporting is broken in some
                    # situations, see:
                    # https://github.com/executablebooks/MyST-Parser/pull/1048
                else:
                    # In rST, the content offset is the absolute position at which
                    # the source code starts in the document.
                    doc_lineno = directive.content_offset + python_lineno
                raise RuntimeError(
                    f"Local variable {node.id!r} at "
                    f"{location}:{directive.name}:{doc_lineno} conflicts with "
                    f"the one automatically provided by the {directive.name} "
                    "directive.\n"
                    f"Line: {python_line}"
                )

        code = compile_directive(directive)
        exec(code, self.namespace, local_vars)  # noqa: S102
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
        "emphasize-result-lines": CodeBlock.option_spec["emphasize-lines"],
        # TODO: Add a show-prompts and hide-prompts options?
    }
    """Options supported by this directive.

    Support the `same options
    <https://github.com/sphinx-doc/sphinx/blob/cc7c6f4/sphinx/directives/code.py#L108-L117>`_
    as :class:`sphinx.directives.code.CodeBlock`, and some specific to Click
    directives.

    The standard ``emphasize-lines`` option applies to the source block only. Use
    ``emphasize-result-lines`` to highlight specific lines in the captured output
    block, with the same syntax (e.g. ``:emphasize-result-lines: 1,3-5``).
    """

    default_language: str
    """Default highlighting language to use to render the code block.

    `All Pygments' languages short names <https://pygments.org/languages/>`_ are
    recognized.
    """

    show_source_by_default: bool = True
    """Whether to render the source code of the example in the code block."""
    show_results_by_default: bool = True
    """Whether to render the results of the example in the code block."""

    runner_method: str
    """The name of the method to call on the :class:`ClickRunner` instance."""

    runner_attr: ClassVar[str] = "click_runner"
    """Name of the attribute holding the runner on the doctree.

    Subclasses (like :class:`~click_extra.sphinx.python.PythonDirective`)
    override this so the Click and Python runners don't collide on the same
    document.
    """

    runner_factory: ClassVar[type] = None  # type: ignore[assignment]
    """Class to instantiate for the per-document runner.

    Defaults to :class:`ClickRunner` in :class:`ClickDirective` (set after the
    class definition to break the forward reference).
    """

    @property
    def runner(self):
        """Get or create the per-document runner.

        Creates one runner per document, keyed by :attr:`runner_attr`.
        """
        runner = getattr(self.state.document, self.runner_attr, None)
        if runner is None:
            runner = self.runner_factory()
            setattr(self.state.document, self.runner_attr, runner)
        return runner

    @cached_property
    def language(self) -> str:
        """Short name of the Pygments lexer used to highlight the code block.

        Returns, in order of precedence, the language specified in the `:language:`
        directive options, the first argument of the directive (if any), or the default
        set in the directive class.
        """
        if "language" in self.options:
            return self.options["language"]  # type: ignore[no-any-return]
        if self.arguments:
            return str(self.arguments[0])
        return self.default_language

    def code_block_options(self, target: str = "source") -> list[str]:
        """Render the options supported by Sphinx' native ``code-block`` directive.

        ``target`` selects which block these options will be attached to:
        ``"source"`` for the directive's input source code, ``"results"`` for the
        captured output. ``emphasize-lines`` routes to the source block;
        ``emphasize-result-lines`` is rewritten as ``emphasize-lines`` on the
        results block, so authors can highlight different lines in each.
        """
        options = []
        for option_id in CodeBlock.option_spec:
            if option_id == "emphasize-lines":
                if target == "source" and "emphasize-lines" in self.options:
                    options.append(f":emphasize-lines: {self.options[option_id]}")
                elif target == "results" and "emphasize-result-lines" in self.options:
                    options.append(
                        f":emphasize-lines: {self.options['emphasize-result-lines']}"
                    )
                continue
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
        wins. If neither is set, the default is taken from ``show_source_by_default``.
        """
        show_source = self.show_source_by_default
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
        wins. If neither is set, the default is taken from ``show_results_by_default``.
        """
        show_results = self.show_results_by_default
        for option_id in self.options:
            if option_id == "show-results":
                show_results = True
            elif option_id == "hide-results":
                show_results = False
        return show_results

    @cached_property
    def is_myst_syntax(self) -> bool:
        """Check if the current directive is written with MyST syntax."""
        return bool(self.state.__module__.split(".", 1)[0] == "myst_parser")

    def render_code_block(
        self,
        lines: Iterable[str],
        language: str,
        target: str = "source",
    ) -> list[str]:
        """Render the code block with the source code or results.

        ``target`` is forwarded to :meth:`code_block_options` so the
        ``emphasize-lines`` / ``emphasize-result-lines`` split routes the right
        highlighting to each block.
        """
        block: list[str] = []
        if not lines:
            return block

        # Initiate the code block with with its MyST or rST syntax.
        code_directive = "```{code-block}" if self.is_myst_syntax else ".. code-block::"
        block.append(f"{code_directive} {language}")

        # Re-attach each option to the code block.
        # Indent the line in rST code block.
        block.extend(
            line if self.is_myst_syntax else RST_INDENT + line
            for line in self.code_block_options(target)
        )

        # Both rST and MyST need a blank line before the body of the block else the
        # first line will be interpreted as a directive option or argument.
        block.append("")

        block.extend(
            line if self.is_myst_syntax else RST_INDENT + line for line in lines
        )

        # In MyST, we need to close the code block.
        if self.is_myst_syntax:
            block.append("```")

        return block

    def run(self) -> list[nodes.Node]:
        assert hasattr(self.runner, self.runner_method), (
            f"{self.runner!r} does not have a method named {self.runner_method!r}."
        )
        runner_func = getattr(self.runner, self.runner_method)
        results = runner_func(self)

        # If neither source code nor results are requested, we don't render anything.
        if not self.show_source and not self.show_results:
            return []

        lines = []
        if self.show_source:
            language = self.language
            # If we are running a CLI, we force rendering the source code as a
            # Python code block.
            if self.runner_method == "run_cli":
                language = SourceDirective.default_language
            lines.extend(self.render_code_block(self.content, language, "source"))
        if self.show_results:
            lines.extend(self.render_code_block(results, self.language, "results"))

        # Convert code block lines to a Docutils node tree.
        # The section element is the main unit of hierarchy for Docutils documents.
        section = nodes.section()
        source_file, _line_number = self.get_source_info()
        self.state.nested_parse(
            StringList(lines, source_file),
            # XXX Check that the offset here is properly computed in both rST and MyST.
            self.content_offset,
            section,
        )
        return section.children


class SourceDirective(ClickDirective):
    """Directive to declare a Click CLI source code.

    This directive is used to declare a Click CLI example in the
    documentation. It renders the source code of the example in a
    Python code block.
    """

    default_language = "python"
    show_source_by_default = True
    show_results_by_default = False
    runner_method = "execute_source"


class RunDirective(ClickDirective):
    """Directive to run a Click CLI example.

    This directive is used to run a Click CLI example in the
    documentation. It renders the results of running the example in a
    shell session code block supporting ANSI colors.
    """

    default_language = "ansi-shell-session"
    show_source_by_default = False
    show_results_by_default = True
    runner_method = "run_cli"


class DeprecatedExampleDirective(SourceDirective):
    """Deprecated alias for SourceDirective.

    .. deprecated:: 7.3.0
        Use ``click:source`` instead of ``click:example``.
    """

    def run(self) -> list[nodes.Node]:
        logger.warning(
            "The 'click:example' directive is deprecated and will be remove in "
            "Click Extra 8.0.0. Use 'click:source' instead.",
            type="click",
            subtype="deprecated",
            location=self.get_location(),
        )
        return super().run()


ClickDirective.runner_factory = ClickRunner


class ClickDomain(StatelessDomain):
    """Setup new directives under the same ``click`` namespace:

    - ``click:source`` which renders a Click CLI source code
    - ``click:example``, an alias to ``click:source`` (deprecated)
    - ``click:run`` which renders the results of running a Click CLI
    """

    name = "click"
    label = "Click"
    directives: ClassVar[dict] = {
        "source": SourceDirective,
        "example": DeprecatedExampleDirective,
        "run": RunDirective,
    }


cleanup_runner = make_cleanup("click_runner")
"""Drop the :class:`ClickRunner` from the doctree once the document is read."""
