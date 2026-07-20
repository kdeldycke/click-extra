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

On top of live rendering, ``python:render`` accepts a ``:sync:`` flag. A
sync block also mirrors its generated Markdown back into the source ``.md``,
between :data:`SYNC_MARKER_START` / :data:`SYNC_MARKER_END` markers directly
below the fence, rewritten on every build by
:func:`rewrite_python_sync_regions`. The document then self-updates and its
output is reviewable in place and on GitHub, reviving the ``docs_update.py``
marker-region pattern with the generator inlined into the page.
"""

from __future__ import annotations

import contextlib
import io
import re
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import Parser as RstParser, directives
from docutils.statemachine import StringList
from docutils.utils import new_document
from sphinx.util import logging

from ._base import (
    StatelessDomain,
    compile_directive,
    make_cleanup,
    parse_into_section,
)
from .click import ClickDirective

logger = logging.getLogger(__name__)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import ClassVar

    from docutils.frontend import Values
    from docutils.parsers import Parser
    from sphinx.application import Sphinx
    from sphinx.util.typing import OptionSpec


SYNC_MARKER_START = "<!-- python:render:sync: auto-generated, do not edit -->"
"""Opening marker of a ``python:render`` ``:sync:`` region.

Written on its own line, directly below the fence, and paired with
:data:`SYNC_MARKER_END`. Everything between the two markers is regenerated on
every build by :func:`rewrite_python_sync_regions`: edit the Python block
above the marker, never the mirrored region itself.
"""

SYNC_MARKER_END = "<!-- python:render:sync: end -->"
"""Closing marker of a ``:sync:`` region. See :data:`SYNC_MARKER_START`."""

_SYNC_FENCE_OPEN = re.compile(
    r"^[ \t]*(?P<fence>`{3,}|:{3,})\{python:render\}[ \t]*\S*[ \t]*$"
)
"""Match a MyST ``python:render`` fence opening line (backtick or colon fence).

Anchored on ``{python:render}`` so the sibling ``python:render-myst`` and
``python:render-rst`` directives never match: ``:sync:`` mirrors Markdown back
into a Markdown host, so it is scoped to the plain ``python:render`` form.
"""

_SYNC_OPTION_LINE = re.compile(r"^:(?P<key>[A-Za-z0-9_+-]+):[ \t]*(?P<value>.*)$")
"""Match a MyST directive option line (``:key:`` or ``:key: value``)."""

_ANY_FENCE_OPEN = re.compile(r"^[ \t]*(?P<fence>`{3,}|:{3,})")
"""Match the opening line of any MyST fence (backtick or colon).

Lets :func:`_rewrite_sync_regions` treat every fence as a unit and skip over
its content, so a ``python:render :sync:`` example *shown inside* a longer
``code-block`` fence (as the documentation does) is copied verbatim rather
than executed.
"""


class PythonRunner:
    """Stateful runner for ``python:*`` directives.

    Holds a per-document namespace so consecutive directive blocks share
    imports and variables. One instance is attached to ``state.document`` on
    first use and dropped at ``doctree-read`` time by
    :func:`cleanup_python_runner`.
    """

    def __init__(self, capture: str | None = None) -> None:
        # ``capture`` is accepted for interface parity with the shared
        # :attr:`~click_extra.sphinx.click.ClickDirective.runner` property,
        # which passes the ``click_extra_run_capture`` value to every runner
        # factory. It is ignored here: ``python:*`` blocks capture stdout via
        # ``contextlib.redirect_stdout``, a sys-level mechanism with no
        # file-descriptor variant, so the "sys"/"fd" distinction does not apply.
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

        return parse_into_section(self, lines)


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

    def _run_sync(self) -> list[nodes.Node]:
        """Render (at most) the source block in ``:sync:`` mode.

        In sync mode the executed output is materialized as a raw Markdown
        region below the fence by :func:`rewrite_python_sync_regions` during
        the ``source-read`` pass, and that region is what the host parser
        renders. Emitting the results here as well would duplicate the
        content, so the directive stays silent (or shows only its Python
        source when ``:show-source:`` is set) and never runs the block a
        second time.
        """
        if not self.show_source:
            return []
        section = nodes.section()
        source_file, _ = self.get_source_info()
        source_lines = list(self.render_code_block(self.content, "python"))
        self.state.nested_parse(
            StringList(source_lines, source_file),
            self.content_offset,
            section,
        )
        return section.children

    def run(self) -> list[nodes.Node]:
        """Render the captured stdout as live document content."""
        if "sync" in self.options:
            return self._run_sync()

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

    Accepts an extra ``:sync:`` flag on top of the shared option spec. When
    set, the block also mirrors its generated Markdown back into the source
    file, between :data:`SYNC_MARKER_START` / :data:`SYNC_MARKER_END`
    markers, so the ``.md`` self-updates and the output is reviewable in
    place (and on GitHub). See :func:`rewrite_python_sync_regions`.
    """

    forced_parser = None

    option_spec: ClassVar[OptionSpec] = {
        **PythonRenderBaseDirective.option_spec,
        "sync": directives.flag,
    }
    """Shared option spec plus the ``:sync:`` flag (see the class docstring)."""


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


def _is_sync_close_fence(line: str, fence: str) -> bool:
    """Return whether ``line`` closes a fence opened with ``fence``.

    A closing fence is a run of the same fence character, at least as long as
    the opener, optionally surrounded by whitespace and nothing else.
    """
    stripped = line.strip()
    return bool(stripped) and set(stripped) == {fence[0]} and len(stripped) >= len(fence)


def _split_sync_options(inner: list[str]) -> tuple[set[str], list[str]]:
    """Split a fence's inner lines into its option keys and its Python body.

    Leading ``:key:`` lines are consumed as directive options; an optional
    single blank line separates them from the body. Returns the set of option
    keys and the remaining body lines.
    """
    options: set[str] = set()
    index = 0
    while index < len(inner) and (match := _SYNC_OPTION_LINE.match(inner[index])):
        options.add(match.group("key"))
        index += 1
    if index < len(inner) and not inner[index].strip():
        index += 1
    return options, inner[index:]


def _skip_existing_sync_region(lines: list[str], index: int) -> int:
    """Return the index just past an existing sync region starting at ``index``.

    Skips leading blank lines, then a :data:`SYNC_MARKER_START` …
    :data:`SYNC_MARKER_END` block if one is present. Returns ``index``
    unchanged when no region follows, so a first-time block is not consumed.
    """
    cursor = index
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor < len(lines) and lines[cursor].strip() == SYNC_MARKER_START:
        while cursor < len(lines) and lines[cursor].strip() != SYNC_MARKER_END:
            cursor += 1
        if cursor < len(lines):
            return cursor + 1
    return index


def _execute_sync_block(
    body: list[str],
    namespace: dict[str, object],
    location: str,
) -> list[str]:
    """Execute a sync block's Python body and return its captured stdout lines.

    Mirrors :meth:`PythonRunner.run_python` but works from raw source lines:
    the ``source-read`` pass runs before any directive instance exists. Shares
    ``namespace`` across the blocks of one document so a later block can reuse
    an earlier block's imports and variables.
    """
    buffer = io.StringIO()
    code = compile("\n".join(body), location, "exec")
    with contextlib.redirect_stdout(buffer):
        exec(code, namespace)  # noqa: S102
    return buffer.getvalue().splitlines()


def _rewrite_sync_regions(text: str, location: str) -> str:
    """Return ``text`` with every ``python:render :sync:`` region refreshed.

    Walks the document fence by fence. Every fence is consumed as a unit (so
    a ``python:render`` example nested inside a longer ``code-block`` fence is
    left untouched); only a top-level ``python:render`` fence carrying a
    ``:sync:`` option is executed, its output written into the marker region
    directly below it (a region is inserted on first sight). Idempotent: a
    region whose source is unchanged round-trips to the same text.
    """
    lines = text.split("\n")
    total = len(lines)
    out: list[str] = []
    namespace: dict[str, object] = {"__file__": "dummy.py"}
    index = 0
    while index < total:
        line = lines[index]
        fence_match = _ANY_FENCE_OPEN.match(line)
        if not fence_match:
            out.append(line)
            index += 1
            continue

        fence = fence_match.group("fence")
        close = index + 1
        while close < total and not _is_sync_close_fence(lines[close], fence):
            close += 1
        if close >= total:
            # Unterminated fence: leave the tail untouched.
            out.extend(lines[index:])
            break

        options: set[str] = set()
        body: list[str] = []
        if _SYNC_FENCE_OPEN.match(line):
            options, body = _split_sync_options(lines[index + 1 : close])
        # Emit the whole fence unit (source and close line) verbatim.
        out.extend(lines[index : close + 1])
        index = close + 1
        if "sync" not in options:
            continue

        generated = _execute_sync_block(body, namespace, location)
        index = _skip_existing_sync_region(lines, index)
        out.extend(["", SYNC_MARKER_START, "", *generated, "", SYNC_MARKER_END])
        # Collapse the gap to the following content to a single blank line.
        while index < total and not lines[index].strip():
            index += 1
        if index < total:
            out.append("")

    return "\n".join(out)


def rewrite_python_sync_regions(
    app: Sphinx,
    docname: str,
    source: list[str],
) -> None:
    """``source-read`` handler mirroring ``python:render :sync:`` output.

    For each ``python:render`` block flagged ``:sync:``, execute it before the
    document is parsed and write its generated Markdown back into a
    :data:`SYNC_MARKER_START` / :data:`SYNC_MARKER_END` region directly below
    the fence. The rewrite is applied both to the in-memory ``source`` (so the
    *same* build renders the fresh output with zero lag) and, best effort, to
    the file on disk (so the ``.md`` self-updates and the region is reviewable
    on GitHub and in diffs).

    .. danger::
        Like the ``python:*`` directives, this executes arbitrary Python at
        build time with the full privileges of the Sphinx process. It is
        registered only when ``click_extra_enable_exec_directives`` is set,
        and must run before any other ``source-read`` transformer (it is
        connected at a low priority) so the persisted file mirrors the
        on-disk source rather than a downstream in-memory conversion.

    .. note::
        The mirrored region is raw Markdown, re-parsed by the host on every
        build and reformatted by ``mdformat`` in the autofix pipeline. A sync
        block must therefore ``print`` ``mdformat``-canonical Markdown (like
        :func:`click_extra.table.render_table` in ``GITHUB`` mode) or the
        generator and the formatter will fight over the region.
    """
    text = source[0]
    if "python:render" not in text or ":sync:" not in text:
        return

    location = app.env.doc2path(docname)
    rewritten = _rewrite_sync_regions(text, location)
    if rewritten == text:
        return
    source[0] = rewritten

    try:
        path = Path(location)
        if path.read_text(encoding="utf-8") != rewritten:
            path.write_text(rewritten, encoding="utf-8")
    except OSError as error:
        logger.warning(
            "click_extra.sphinx: could not persist python:render:sync region "
            "for %s: %s",
            docname,
            error,
        )


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
