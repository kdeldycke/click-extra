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
"""Shared scaffolding for the `click:*` and `python:*` directive families.

Holds the small bits of plumbing that both {mod}`click_extra.sphinx.click` and
{mod}`click_extra.sphinx.python` need verbatim: directive-content compilation,
per-document runner cleanup, and the stateless `Domain` boilerplate Sphinx
demands of any domain that ships only directives (no roles or objects).

The offline self-updating block toolkit those directives share (fence-aware
Markdown scanning, the `<!-- name … --> / <!-- name-end -->` marker grammar,
and the walk-rewrite-write loop behind the `click-extra refresh-directives`
command) now lives in the dependency-light {mod}`click_extra.blocks` module, so
it stays importable without the `sphinx` extra.
"""

from __future__ import annotations

from docutils import nodes
from docutils.statemachine import StringList
from sphinx.domains import Domain

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from types import CodeType

    from docutils.nodes import Element
    from sphinx.addnodes import pending_xref
    from sphinx.application import Sphinx
    from sphinx.builders import Builder
    from sphinx.directives import SphinxDirective
    from sphinx.environment import BuildEnvironment

    from .click import ClickDirective


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
    # computation and retire the content_offset workaround in click.py (see
    # click.MYST_CONTENT_OFFSET_INFLATED_MAX); until then, stay on
    # directive.content.
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
    directive: ClickDirective,
    lines: list[str],
) -> list[nodes.Node]:
    """Hand generated source *lines* back to the directive's parser.

    Nested directives inside *lines* execute during this pass and share the
    directive's runner namespace. Returns the parsed children, ready to be
    returned from the directive's `run()`.

    ```{note}
    A generated line has no source line of its own, so each is labelled with
    the document line the directive's content starts at
    ({attr}`~click_extra.sphinx.click.ClickDirective.abs_content_offset`) plus
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
