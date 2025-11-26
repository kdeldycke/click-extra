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

import ast
import contextlib
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from functools import cache, cached_property, partial

import click
from click.testing import EchoingStdin
from docutils import nodes
from docutils.statemachine import StringList
from sphinx.directives import SphinxDirective, directives
from sphinx.directives.code import CodeBlock
from sphinx.domains import Domain
from sphinx.errors import ConfigError
from sphinx.highlighting import PygmentsBridge

from . import __version__
from .pygments import AnsiHtmlFormatter
from .testing import ExtraCliRunner

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable
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
            cli=cli, args=args, input=input, env=env, prog_name=prog_name, **extra
        )
        # TODO: Maybe we can intercept the exception here either make it:
        # - part of the output in the rendered Sphinx code block, or
        # - re-raise it so Sphinx can display it properly in its logs.
        output_lines.extend(result.output.splitlines())
        return result

    def declare_example(self, directive: SphinxDirective) -> None:
        """Execute the given code, adding it to the runner's namespace."""
        # Use directive.content instead of directive.block_text as the latter
        # include the directive text itself in rST.
        source_code = "\n".join(directive.content)
        # Get the user-friendly location string as provided by Sphinx.
        location = directive.get_location()

        with patch_modules():
            code = compile(source_code, location, "exec")
            exec(code, self.namespace)

    def run_example(self, directive: SphinxDirective) -> list[str]:
        """Execute the given ``source_code``.

        Returns a simulation of terminaml execution, including a mix of input, output,
        prompts and tracebacks.

        The execution context is augmented, so you can refer directly to these
        functions in the provided ``source_code``:

        - :meth:`invoke()`: which is the same as :meth:`ExtraCliRunner.invoke`
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
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                if node.id in local_vars:
                    # Get the source lines for better error reporting.
                    source_lines = source_code.splitlines()
                    # Get the line number relative to the source code.
                    python_lineno = node.lineno
                    python_line = source_lines[python_lineno - 1]
                    # Compute the absolute line number in the document.
                    if directive.is_myst_syntax:  # type:ignore[attr-defined]
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
                        f"the one automaticcaly provided by the {directive.name} "
                        "directive.\n"
                        f"Line: {python_line}"
                    )

        code = compile(source_code, location, "exec")
        exec(code, self.namespace, local_vars)
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
        # TODO: Add a show-prompts and hide-prompts options?
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
            runner = ExampleRunner()
            setattr(self.state.document, "click_example_runner", runner)
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
        block: list[str] = []
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
        results = runner_func(self)

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
        source_file, _line_number = self.get_source_info()
        self.state.nested_parse(
            StringList(lines, source_file),
            # XXX Check that the offset here is properly computed in both rST and MyST.
            self.content_offset,
            section,
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
        delattr(doctree, "click_example_runner")


GITHUB_ALERT_PATTERN = re.compile(
    r"^(\s*)>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$"
)
"""Regex pattern to match GitHub alerts opening lines.

.. seealso::
    - GitHub documentation for `alerts syntax
    <https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#alerts>`_.
    - Announcement for `alert support starting 2023-12-14
    <https://github.blog/changelog/2023-12-14-new-markdown-extension-alerts-provide-distinctive-styling-for-significant-content/>`_.
"""

GITHUB_ALERT_CONTENT_PATTERN = re.compile(r"^(\s*)>(.*)$")
"""Regex pattern to match GitHub alert content lines."""

CODE_FENCE_PATTERN = re.compile(r"^(\s*)(`{3,}|~{3,})")
"""Regex pattern to match code fence opening/closing lines."""

INDENTED_CODE_BLOCK_PATTERN = re.compile(r"^( {4}|\t)")
"""Regex pattern to match indented code block lines (4 spaces or 1 tab)."""


@cache
def check_colon_fence(app: Sphinx) -> None:
    """Check that `colon_fence support
    <https://myst-parser.readthedocs.io/en/latest/syntax/optional.html#code-fences-using-colons>`_
    is enabled for MyST.

    :raises ConfigError: If ``colon_fence`` is not in ``myst_enable_extensions``.
    """
    myst_extensions = getattr(app.config, "myst_enable_extensions", [])
    if "colon_fence" not in myst_extensions:
        raise ConfigError(
            "GitHub alerts conversion requires 'colon_fence' in "
            "myst_enable_extensions. Add it to your conf.py:\n"
            "    myst_enable_extensions = [..., 'colon_fence']"
        )


@dataclass
class AlertParserState:
    """State machine for parsing GitHub alerts."""

    in_alert: bool = False
    in_code_block: bool = False
    code_fence_char: str = ""
    code_fence_len: int = 0
    code_fence_indent: str = ""
    alert_indent: str = ""
    prev_line_blank: bool = True
    modified: bool = False

    def reset_code_fence(self) -> None:
        self.in_code_block = False
        self.code_fence_char = ""
        self.code_fence_len = 0
        self.code_fence_indent = ""

    def enter_code_fence(self, char: str, length: int, indent: str) -> None:
        self.in_code_block = True
        self.code_fence_char = char
        self.code_fence_len = length
        self.code_fence_indent = indent

    def handle_fence(
        self, fence_char: str, fence_len: int, fence_indent: str, line: str
    ) -> bool:
        """Handle fence matching. Returns True if fence was processed."""
        if not self.in_code_block:
            self.enter_code_fence(fence_char, fence_len, fence_indent)
            return True
        elif (
            fence_char == self.code_fence_char
            and fence_len >= self.code_fence_len
            and fence_indent == self.code_fence_indent
            and line.strip() == fence_char * fence_len
        ):
            self.reset_code_fence()
            return True
        return False


def replace_github_alerts(text: str) -> str | None:
    """Transform GitHub alerts into MyST admonitions.

    Identify GitHub alerts in the provided ``text`` and transform them into
    colon-fenced ``:::`` MyST admonitions.

    Code blocks (fenced with ``` or ``~~~``, or indented with 4 spaces/tab) are
    detected and their content is preserved unchanged.

    Returns ``None`` if no transformation was applied, else returns the transformed
    text.
    """
    lines = text.split("\n")
    result = []
    state = AlertParserState()

    for line in lines:
        # Check for code fence boundaries.
        fence_match = CODE_FENCE_PATTERN.match(line)
        if fence_match:
            fence_indent = fence_match.group(1)
            fence_chars = fence_match.group(2)
            fence_char = fence_chars[0]
            fence_len = len(fence_chars)

            if state.handle_fence(fence_char, fence_len, fence_indent, line):
                result.append(line)
                continue

        if state.in_code_block:
            result.append(line)
            continue

        if state.prev_line_blank and INDENTED_CODE_BLOCK_PATTERN.match(line):
            result.append(line)
            state.prev_line_blank = False
            continue

        is_blank = line.strip() == ""

        # Only check for new alert if we're not already inside one
        if not state.in_alert:
            match = GITHUB_ALERT_PATTERN.match(line)
            if match:
                state.alert_indent, alert_type = match.groups()
                result.append(f"{state.alert_indent}:::{{{alert_type.lower()}}}")
                state.in_alert = True
                state.modified = True
                state.prev_line_blank = is_blank
                continue

        if state.in_alert:
            content_match = GITHUB_ALERT_CONTENT_PATTERN.match(line)
            if content_match:
                result.append(state.alert_indent + content_match.group(2).lstrip())
            else:
                result.append(f"{state.alert_indent}:::")
                result.append(line)
                state.in_alert = False
                state.prev_line_blank = is_blank
                continue
        else:
            result.append(line)

        state.prev_line_blank = is_blank

    if state.in_alert:
        result.append(":::")

    return "\n".join(result) if state.modified else None


def convert_github_alerts(app: Sphinx, *args) -> None:
    """Convert GitHub alerts into MyST admonitions in content blocks."""
    content = args[-1]

    for i, orig_content in enumerate(content):
        transformed = replace_github_alerts(orig_content)
        if transformed is not None:
            check_colon_fence(app)
            content[i] = transformed


def setup(app: Sphinx) -> ExtensionMetadata:
    """Register Click Extra specific extensions to Sphinx.

    - new directives, augmented with ANSI coloring.
    - support for GitHub alerts syntax in *included* and regular *source* files.

    .. caution::
        This function forces the Sphinx app to use
        ``sphinx.highlighting.PygmentsBridge`` instead of the default HTML formatter to
        add support for ANSI colors in code blocks.
    """
    # Set Sphinx's default HTML formatter to an ANSI capable one.
    PygmentsBridge.html_formatter = AnsiHtmlFormatter

    # Register click:example and click:run directives.
    app.add_domain(ClickDomain)
    app.connect("doctree-read", delete_example_runner_state)

    # Register GitHub alerts converter.
    app.connect("source-read", convert_github_alerts)
    app.connect("include-read", convert_github_alerts)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
