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
"""Generic Python execution directives for Sphinx documentation.

Sibling to :mod:`click_extra.sphinx.click`. The Click directives execute a
Click CLI and render its terminal output; these execute arbitrary Python and
render either captured ``stdout`` (``python:run``) or live document content
parsed from the captured output (``python:render``, ``python:render-myst``,
``python:render-rst``).

The render trio lets a documentation page embed dynamically generated tables,
references, or whole sections without a separate ``docs_update.py``
regenerator script: the content stays in sync with its source by construction.

Each render variant has a clear parser contract:

- ``python:render`` parses the captured output with whatever parser owns the
  host document. Use it when the generated markup matches the host file
  format (MyST inside ``.md``, reST inside ``.rst``).
- ``python:render-myst`` always parses the captured output as MyST,
  regardless of host. Lets ``.rst`` documents embed MyST-generated content.
- ``python:render-rst`` always parses the captured output as reST, regardless
  of host. Lets ``.md`` documents embed reST-generated content.
"""

from __future__ import annotations

import contextlib
import io

from docutils import nodes
from docutils.parsers.rst import Parser as RstParser
from docutils.statemachine import StringList
from docutils.utils import new_document

from ._base import StatelessDomain, compile_directive, make_cleanup
from .click import ClickDirective

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import ClassVar

    from docutils.frontend import Values
    from docutils.parsers import Parser


class PythonRunner:
    """Stateful runner for ``python:*`` directives.

    Holds a per-document namespace so consecutive directive blocks share
    imports and variables. One instance is attached to ``state.document`` on
    first use and dropped at ``doctree-read`` time by
    :func:`cleanup_python_runner`.
    """

    def __init__(self) -> None:
        self.namespace: dict[str, object] = {"__file__": "dummy.py"}

    def execute_source(self, directive: ClickDirective) -> None:
        """Execute the directive's content with no output capture.

        Used by :class:`PythonSourceDirective` when the example is run only
        for its side effects (typically to seed imports for a follow-up
        ``python:run`` block).
        """
        exec(compile_directive(directive), self.namespace)  # noqa: S102

    def run_python(self, directive: ClickDirective) -> list[str]:
        """Execute the directive's content and capture ``stdout``.

        Returns the captured output as a list of lines, suitable for either
        a code-block render (``python:run``) or a live nested-parse pass
        (the ``python:render`` directives).
        """
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exec(compile_directive(directive), self.namespace)  # noqa: S102
        return buffer.getvalue().splitlines()


class PythonDirective(ClickDirective):
    """Base class for ``python:*`` directives.

    Reuses :class:`ClickDirective`'s option spec and rendering scaffolding
    but rebinds the per-document runner so the Click and Python namespaces
    don't collide within the same document.
    """

    runner_attr = "python_runner"
    runner_factory = PythonRunner


class PythonSourceDirective(PythonDirective):
    """Render a Python source block and execute it silently.

    Counterpart to :class:`~click_extra.sphinx.click.SourceDirective` for
    non-Click code: show the source for teaching, run it as a side effect
    to seed the runner namespace for subsequent ``python:run`` or
    ``python:render`` blocks in the same document.
    """

    default_language = "python"
    show_source_by_default = True
    show_results_by_default = False
    runner_method = "execute_source"


class PythonRunDirective(PythonDirective):
    """Execute a Python block and render its captured ``stdout``.

    Default language for the result code block is ``text`` (plain, no
    highlighting). Override with the ``:language:`` option when the output
    is structured (``json``, ``html``, ``yaml``, etc.).
    """

    default_language = "text"
    show_source_by_default = False
    show_results_by_default = True
    runner_method = "run_python"

    def run(self) -> list[nodes.Node]:
        """Render captured stdout as a code block.

        Like :meth:`ClickDirective.run` but without the ``run_cli``-specific
        source-language override: the source (if shown) is always rendered
        as ``python``, regardless of the result language.
        """
        results = self.runner.run_python(self)

        if not self.show_source and not self.show_results:
            return []

        lines: list[str] = []
        if self.show_source:
            lines.extend(self.render_code_block(self.content, "python", "source"))
        if self.show_results:
            lines.extend(self.render_code_block(results, self.language, "results"))

        section = nodes.section()
        source_file, _ = self.get_source_info()
        self.state.nested_parse(
            StringList(lines, source_file),
            self.content_offset,
            section,
        )
        return section.children


def _parse_with(
    parser: Parser,
    text: str,
    settings: Values | None,
    parent: nodes.Element,
    source_path: str,
) -> None:
    """Parse ``text`` with ``parser`` and graft the resulting nodes into ``parent``.

    Builds a fresh sub-document that inherits the host document's settings,
    runs the supplied parser on the captured text, then transfers the
    sub-document's children to ``parent``. This lets a directive force a
    specific parser regardless of what owns the surrounding source file.
    """
    sub_doc = new_document(source_path, settings)
    parser.parse(text, sub_doc)
    parent.extend(sub_doc.children)


class PythonRenderBaseDirective(PythonDirective):
    """Common scaffolding for the ``python:render`` directive family.

    Subclasses set ``forced_parser`` to either ``None`` (use the host
    document's parser via ``state.nested_parse``) or a :class:`Parser`
    factory that produces the parser to apply to the captured output.
    """

    default_language = "markdown"
    show_source_by_default = False
    show_results_by_default = True
    runner_method = "run_python"

    forced_parser: ClassVar[type[Parser] | None] = None
    """Parser class to instantiate for the captured output.

    ``None`` means defer to the host document's parser via
    ``state.nested_parse`` (preserving full Sphinx context). A concrete
    class forces that parser regardless of host file format.
    """

    def run(self) -> list[nodes.Node]:
        """Render the captured stdout as live document content."""
        results = self.runner.run_python(self)

        if not self.show_source and not self.show_results:
            return []

        section = nodes.section()
        source_file, _ = self.get_source_info()

        if self.show_source:
            source_lines = list(self.render_code_block(self.content, "python"))
            self.state.nested_parse(
                StringList(source_lines, source_file),
                self.content_offset,
                section,
            )

        if self.show_results and results:
            if self.forced_parser is None:
                # Host parser: reuse the surrounding state machine so cross
                # references and Sphinx-aware roles resolve naturally.
                self.state.nested_parse(
                    StringList(results, source_file),
                    self.content_offset,
                    section,
                )
            else:
                _parse_with(
                    self.forced_parser(),
                    "\n".join(results),
                    self.state.document.settings,
                    section,
                    source_file,
                )

        return section.children


class PythonRenderDirective(PythonRenderBaseDirective):
    """Execute a Python block and parse its ``stdout`` with the host parser.

    The captured output is fed to whatever parser owns the surrounding
    source file: MyST inside ``.md`` documents, reST inside ``.rst``
    documents. Use this when the generated markup matches the host file
    format. Cross-references and Sphinx-aware roles resolve naturally
    because the host state machine is reused.

    For a host-independent contract, see :class:`PythonRenderMystDirective`
    and :class:`PythonRenderRstDirective`.
    """

    forced_parser = None


class PythonRenderMystDirective(PythonRenderBaseDirective):
    """Execute a Python block and parse its ``stdout`` as MyST, regardless of host.

    Lets a ``.rst`` document embed MyST-generated content: the captured
    output goes through MyST parsing even when the surrounding file is
    reST. Requires ``myst-parser`` to be importable; the import is
    deferred to directive run time so consumers that never use this
    directive don't pay the dependency cost.

    Replaces the ``docs_update.py`` regenerator pattern (write generated
    content between ``<!-- start -->`` / ``<!-- end -->`` markers) with
    inline build-time execution. The content is always current and there
    is no separate regeneration step.
    """

    @property
    def forced_parser(self) -> type[Parser]:  # type: ignore[override]
        """Lazy-import the MyST docutils parser.

        Deferred so reST-only consumers don't need ``myst-parser``.
        """
        from myst_parser.parsers.docutils_ import Parser as MystParser

        return MystParser


class PythonRenderRstDirective(PythonRenderBaseDirective):
    """Execute a Python block and parse its ``stdout`` as reST, regardless of host.

    Lets a ``.md`` MyST document embed reST-generated content: the
    captured output goes through the docutils reST parser even when the
    surrounding file is MyST. No additional dependency: the reST parser
    ships with docutils.
    """

    forced_parser = RstParser


class PythonDomain(StatelessDomain):
    """Sphinx domain registering the ``python:*`` directives.

    Provides:

    - ``python:source`` to show and silently execute Python source.
    - ``python:run`` to execute Python and render the captured stdout in a
      code block.
    - ``python:render`` to execute Python and parse the captured stdout
      with the host document's parser.
    - ``python:render-myst`` to force MyST parsing of the captured stdout.
    - ``python:render-rst`` to force reST parsing of the captured stdout.

    The domain name is ``python``, distinct from Sphinx's built-in ``py``
    domain (which provides ``py:function`` / ``py:class`` / ``py:mod`` for
    documenting Python API objects). Both coexist without collision.
    """

    name = "python"
    label = "Python (build-time execution)"
    directives: ClassVar[dict] = {
        "source": PythonSourceDirective,
        "run": PythonRunDirective,
        "render": PythonRenderDirective,
        "render-myst": PythonRenderMystDirective,
        "render-rst": PythonRenderRstDirective,
    }


cleanup_python_runner = make_cleanup("python_runner")
"""Drop the :class:`PythonRunner` from the doctree once the document is read."""
