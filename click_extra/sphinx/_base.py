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
"""Shared scaffolding of the `click:*`, `python:*` and `matrix` directives.

Holds the small bits of plumbing that {mod}`click_extra.sphinx.click`,
{mod}`click_extra.sphinx.python` and {mod}`click_extra.sphinx.matrix` need
verbatim: directive-content compilation, the line-offset arithmetic of
{class}`ContentOffsetMixin`, per-document runner cleanup, and the stateless
`Domain` boilerplate Sphinx demands of any domain that ships only directives
(no roles or objects).

The offline self-updating block toolkit those directives share (fence-aware
Markdown scanning, the `<!-- name … --> / <!-- name-end -->` marker grammar,
and the walk-rewrite-write loop behind the `click-extra refresh-directives`
command) lives in the dependency-light {mod}`click_extra.blocks` module, so it
stays importable without the `sphinx` extra.
"""

from __future__ import annotations

from functools import cached_property

from docutils import nodes
from docutils.statemachine import StringList
from packaging.version import Version
from sphinx.directives import SphinxDirective
from sphinx.domains import Domain

# The `sphinx` extra does not declare `myst-parser` and Sphinx does not pull it
# in, so a reST-only project has none: the extension stays importable for it.
try:
    import myst_parser
except ImportError:
    myst_parser = None  # type: ignore[assignment]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from types import CodeType

    from docutils.nodes import Element
    from sphinx.addnodes import pending_xref
    from sphinx.application import Sphinx
    from sphinx.builders import Builder
    from sphinx.environment import BuildEnvironment


PLACEHOLDER_FILE = "dummy.py"
"""The `__file__` every directive body runs under.

A block is compiled from a document, not loaded from a module, so the runner
namespaces of both directive families seed `__file__` with this name rather than
a path. A block reading it gets the same answer in a Sphinx build and in the
offline refresh of a `:mirror:` region.
"""


def myst_version() -> Version | None:
    """The installed `myst-parser` release, or `None` when there is none.

    Every MyST-specific behavior of the extension is keyed on this answer, so a
    reST-only project, which has no `myst-parser`, takes none of them.
    """
    return None if myst_parser is None else Version(myst_parser.__version__)


MYST_CONTENT_OFFSET_INFLATED_MAX = Version("5.1.0")
"""Last `myst-parser` release that miscomputes a directive's `content_offset`.

Up to and including this version, `myst-parser` over-counts `content_offset`
by one whenever an option block is followed by a body ending in blank
line(s): the parsed body is rebuilt through a string round-trip that drops
one trailing blank line, so the option-block line count comes out one too
high. This shifts the reported source line of every body element down by one.

This fix is not yet upstream: the open rework in
[`#1175`](https://github.com/executablebooks/MyST-Parser/pull/1175) does not
include it, and also makes `content_offset` document-relative. So the release
that eventually lands the fix requires
{attr}`ContentOffsetMixin.abs_content_offset` to converge on the rST branch it
already carries, not merely drop this compensation. See `docs/upstream.md`. The
steps that retire the workaround are the `{todo}` of the `click_extra.sphinx.click`
module, where Sphinx renders them.
"""


def _myst_content_offset_inflation(directive: SphinxDirective) -> int:
    """Lines to subtract from the MyST error-line computation (`0` or `1`).

    Works around the {data}`MYST_CONTENT_OFFSET_INFLATED_MAX` bug so the
    variable-conflict error points at the true source line. Only engages on an
    affected `myst-parser`, and only when the directive carries both an option
    block and a body ending in a blank line: the two conditions that together
    trigger the inflation.

    ```{caution}
    The round-trip behind the bug consumes the *first* trailing blank line, so
    a body ending in exactly one blank line inflates `content_offset` without
    leaving a trace in `directive.content`. That single-blank case therefore
    stays off by one until the upstream fix is adopted; bodies ending in two or
    more blank lines are corrected.
    ```
    """
    version = myst_version()
    if version is None or version > MYST_CONTENT_OFFSET_INFLATED_MAX:
        return 0
    body = list(directive.content)
    if directive.options and body and not body[-1].strip():
        return 1
    return 0


class ContentOffsetMixin(SphinxDirective):
    """Directive base reconciling the line counts of the two parsers.

    docutils and `myst-parser` both expose a `content_offset`, counted from
    different places, so anything naming a document line goes through
    {attr}`abs_content_offset` rather than reading `content_offset` directly.
    Every directive handing generated lines to {func}`parse_into_section`
    derives from here, which is what lets a diagnostic in those lines name the
    right line whichever parser owns the document.
    """

    @cached_property
    def is_myst_syntax(self) -> bool:
        """Check if the current directive is written with MyST syntax."""
        return bool(self.state.__module__.split(".", 1)[0] == "myst_parser")

    @cached_property
    def abs_content_offset(self) -> int:
        """0-based offset of the directive's first content line in the document.

        Both parsers expose a `content_offset` and they count it from
        different places: docutils from the top of the document, `myst-parser`
        from the directive's own first line. Everything naming a document line
        reads this property instead, so the two conventions are reconciled in
        one place: the variable-conflict error of
        {meth}`~click_extra.sphinx.click.ClickRunner.run_cli`, and the
        source-line labels {func}`parse_into_section` attaches to a generated
        block.

        Named after docutils' `abs_line_offset()`, whose convention it
        follows.
        """
        # Both attributes reach mypy as Any, since the [tool.mypy] overrides
        # skip following `sphinx.*`. Restate the contract docutils declares.
        content_offset: int = self.content_offset
        if not self.is_myst_syntax:
            return content_offset
        lineno: int = self.lineno
        # Correct a myst-parser <= 5.1.0 bug that inflates content_offset by
        # one when an option block precedes a body ending in blank line(s).
        # See the mechanism and the single-trailing-blank caveat in
        # _myst_content_offset_inflation().
        return lineno + content_offset - _myst_content_offset_inflation(self)


def directive_source(directive: SphinxDirective) -> tuple[str, str]:
    """Return the `(source_code, location)` pair for `directive`.

    Centralizes the "join the content lines, fetch the Sphinx-reported source
    location" preamble shared by every `exec`-based directive in this
    package, so callers needing the raw source (for an AST conflict check, say)
    do not re-derive it independently of {func}`compile_directive`.
    """
    # Use directive.content, not directive.block_text: block_text is body-only
    # in myst-parser <= 5.1.0, and includes the directive header and options in
    # rST. executablebooks/MyST-Parser#1164 (merged, not yet released) aligns
    # MyST's block_text with rST's full-directive form. Once a myst-parser
    # release ships #1164, block_text could anchor a robust line-number
    # computation and retire the content_offset workaround of
    # ContentOffsetMixin (see MYST_CONTENT_OFFSET_INFLATED_MAX); until then,
    # stay on directive.content.
    source_code = "\n".join(directive.content)
    # The location string Sphinx reports in tracebacks for this directive.
    location = directive.get_location()
    return source_code, location


def compile_directive(directive: SphinxDirective) -> CodeType:
    """Compile the body of `directive` for later `exec`.

    Joins the directive's content lines, labels them with the directive's
    source location (via {func}`directive_source`), and hands the result to
    {func}`compile`.

    ```{danger}
    The compiled code object is intended to run via {func}`exec` in the
    runner's full module namespace. It executes with the same privileges
    as the Sphinx process: filesystem, network, environment variables,
    and any secrets the build environment holds. There is no sandbox.

    Only build documentation from trusted source. Both the
    {class}`~click_extra.sphinx.click.ClickDomain` and the
    {class}`~click_extra.sphinx.python.PythonDomain` are gated behind
    the `click_extra_enable_exec_directives` opt-in for exactly this
    reason. See `docs/sphinx.md` under the Setup section for the
    full trust boundary.
    ```
    """
    source_code, location = directive_source(directive)
    return compile(source_code, location, "exec")


def parse_into_section(
    directive: ContentOffsetMixin,
    lines: list[str],
) -> list[nodes.Node]:
    """Hand generated source *lines* back to the directive's parser.

    Nested directives inside *lines* execute during this pass and share the
    directive's runner namespace. Returns the parsed children, ready to be
    returned from the directive's `run()`.

    ```{note}
    A generated line has no source line of its own, so each is labelled with
    the document line the directive's content starts at
    ({attr}`ContentOffsetMixin.abs_content_offset`) plus
    its index in the block, and the offset handed to `nested_parse()` says the
    same thing in the convention that parser reads it in. Both halves are
    needed because the two parsers consult different ones: docutils resolves a
    diagnostic's line through the labels, and numbers the block from the top
    of the *file* when they are left to default; `myst-parser` drops them and
    re-renders the joined text against the offset alone.
    ```
    """
    section = nodes.section()
    source_file, _ = directive.get_source_info()
    offset = directive.abs_content_offset
    directive.state.nested_parse(
        StringList(
            lines,
            source_file,
            items=[(source_file, offset + index) for index in range(len(lines))],
        ),
        offset - directive.lineno if directive.is_myst_syntax else offset,
        section,
    )
    return section.children


def make_cleanup(attr: str) -> Callable[[Sphinx, nodes.document], None]:
    """Build a `doctree-read` callback that drops `attr` from the doctree.

    Per-document runners live as attributes on `state.document` so they
    persist across directive invocations within the same page. Without an
    explicit cleanup, the runner namespace would leak into the next document
    Sphinx parses in the same process.
    """

    def cleanup(app: Sphinx, doctree: nodes.document) -> None:
        if getattr(doctree, attr, None) is not None:
            delattr(doctree, attr)

    cleanup.__name__ = f"cleanup_{attr}"
    cleanup.__qualname__ = cleanup.__name__
    return cleanup


class StatelessDomain(Domain):
    """{class}`~sphinx.domains.Domain` base for directive-only domains.

    Sphinx requires {meth}`merge_domaindata` on any domain declaring
    `parallel_read_safe = True`, and MyST-Parser warns when
    {meth}`resolve_any_xref` is missing. Both stubs are no-ops here because
    `click:*` and `python:*` register directives only: no roles, no
    cross-references, no shared state to merge.
    """

    def merge_domaindata(self, docnames: list[str], otherdata: dict) -> None:
        """No-op: stateless, safe to run in parallel."""

    def resolve_any_xref(
        self,
        env: BuildEnvironment,
        fromdocname: str,
        builder: Builder,
        target: str,
        node: pending_xref,
        contnode: Element,
    ) -> list[tuple[str, nodes.reference]]:
        """No-op: this domain provides no objects to cross-reference.

        ```{seealso} https://github.com/kdeldycke/click-extra/issues/1502
        ```
        """
        return []
