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
"""Collapse the repeated entries `sphinx.ext.todo` accumulates on a `todolist`.

`sphinx.ext.todo` collects doctree nodes, not documented objects. A `{todo}`
written once in a docstring therefore lands on the `todolist` page once per
*rendering* of that docstring, and two conventions common to autodoc projects
render the same docstring several times:

- **A full-API page plus per-feature pages.** A project documenting every
  module on one page, then documenting the same modules again next to the
  prose that explains them, renders each docstring twice. `:no-index:` on the
  second block does not help: it suppresses the cross-reference target and the
  search-index entry, leaving the docstring (and its `todo` node) rendered in
  full.
- **A package re-exporting its members.** `automodule` documents the imported
  names a package lists in `__all__`, so a symbol appears once under the
  package and once under the module that defines it. Both renderings can even
  land on the same page.

The two multiply. On click-extra's own documentation the untreated list showed
35 entries for 17 distinct `{todo}` directives, one of them repeated four
times.

Nothing upstream deduplicates: {class}`sphinx.ext.todo.TodoListProcessor`
flattens the whole `todo` domain into the page in read order. This module
removes the surplus nodes from that domain just before the processor reads it,
so the rendered list carries one entry per directive.

```{todo}
Propose the deduplication upstream, as a `sphinx.ext.todo` feature rather
than a third-party hook.

The repetition is a property of how autodoc renders a docstring, not of how
a project writes one, so every autodoc project documenting a module twice
hits it and none of them can fix it in their own source: `:no-index:` reads
like the cure and is not.
{class}`sphinx.ext.todo.TodoListProcessor` already flattens the whole domain
in one place, which is where a `todo_deduplicate` config value would apply;
the two helpers this module needed ({func}`todo_identity` and
{func}`is_reexport`) are the whole of the logic.

Should it land, keep this module as a shim for the Sphinx releases below
that floor, then drop it once the floor moves past them.
```
"""

from __future__ import annotations

from pathlib import Path

from sphinx.ext.todo import todo_node, todolist
from sphinx.util import logging

TYPE_CHECKING = False
if TYPE_CHECKING:
    from docutils import nodes
    from sphinx.application import Sphinx


logger = logging.getLogger(__name__)


AUTODOC_DOCSTRING_MARKER = ":docstring of "
"""Separator autodoc puts between a source file and the object it documented.

A node produced from a docstring carries a synthetic source of the form
`{file}:docstring of {dotted.path}`, where `{file}` is the file the *reader*
reached the object through, not necessarily the one defining it. Splitting on
this marker is what lets {func}`todo_identity` recognize two renderings of a
single docstring reached through two import paths.
"""

DEDUPE_TODOS_CONFIG = "click_extra_dedupe_todos"
"""Name of the `conf.py` value gating the deduplication.

`True` by default: a `todolist` page listing the same item three times is a
defect in every project I know of, and a project that has not enabled
`sphinx.ext.todo` never notices the hook either way. Set it to `False` to get
Sphinx's raw output back, one entry per rendering.
"""


def todo_identity(node: todo_node) -> tuple[str, int | None]:
    """Identify the `{todo}` directive a node was rendered from.

    Two nodes share an identity when they come from the same line of the same
    docstring or document, whatever page rendered them and whichever import
    path autodoc reached the object through. The file prefix is dropped from a
    docstring source precisely so a re-exported symbol matches the module that
    defines it.
    """
    source = node.source or ""
    _, marker, dotted_path = source.partition(AUTODOC_DOCSTRING_MARKER)
    return (dotted_path if marker else source), node.line


def is_reexport(node: todo_node) -> bool:
    """Tell whether a node was rendered through a package's `__init__`.

    Used to rank competing renderings: the entry surviving deduplication keeps
    its backlink and its "located in ..." attribution, so a rendering reached
    through the defining module is worth more to a reader than the same
    docstring reached through a re-exporting package.
    """
    source = node.source or ""
    file_path, marker, _ = source.partition(AUTODOC_DOCSTRING_MARKER)
    return bool(marker) and Path(file_path).stem == "__init__"


def deduplicate_todos(app: Sphinx, doctree: nodes.document, docname: str) -> None:
    """Drop every `todo` node duplicating one already held by the domain.

    Connected to `doctree-resolved` below the priority
    {class}`sphinx.ext.todo.TodoListProcessor` runs at, and a no-op on any
    document holding no `todolist`, so the work happens once on the page that
    consumes the domain.

    Among the renderings of one directive, the surviving node is the first in
    `(rendered through a defining module, document name, position in the
    document)` order. That ordering is total and reads the same on a clean
    build and an incremental one, so the backlink a reader follows does not
    move around between builds.

    ```{note}
    The `todo` domain is mutated in place. That is safe because Sphinx pickles
    the environment at the end of the reading phase, before the writing phase
    this hook belongs to: the removals reach the page being written and never
    the cached environment, so an incremental rebuild still starts from the
    full set.
    ```
    """
    if not getattr(app.config, DEDUPE_TODOS_CONFIG, True):
        return

    # `sphinx.ext.todo` may not be among the project's extensions, in which
    # case no domain was ever registered and no page can hold a todolist.
    domain = app.env.domains.get("todo")
    if domain is None:
        return

    # Skip every page that does not consume the domain.
    if next(doctree.findall(todolist), None) is None:
        return

    winners: dict[tuple[str, int | None], tuple[bool, str, int]] = {}
    for name in sorted(domain.todos):
        for position, node in enumerate(domain.todos[name]):
            identity = todo_identity(node)
            rank = (is_reexport(node), name, position)
            current = winners.get(identity)
            if current is None or rank < current:
                winners[identity] = rank

    keep = {(name, position) for _, name, position in winners.values()}

    removed = 0
    for name, todos in domain.todos.items():
        kept = [node for position, node in enumerate(todos) if (name, position) in keep]
        removed += len(todos) - len(kept)
        if len(kept) != len(todos):
            domain.todos[name] = kept

    if removed:
        logger.info(
            "click_extra.sphinx.todos: collapsed %d duplicate todo %s into "
            "%d unique %s on %s.",
            removed,
            "entries" if removed > 1 else "entry",
            len(winners),
            "directives" if len(winners) > 1 else "directive",
            docname,
        )


def setup(app: Sphinx) -> None:
    """Register the deduplication hook on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. Priority 400 places the hook
    below the default 500 {class}`sphinx.ext.todo.TodoListProcessor` is
    connected at, which is what makes the domain already trimmed by the time
    the list is rendered.
    """
    app.add_config_value(
        DEDUPE_TODOS_CONFIG, default=True, rebuild="html", types=[bool]
    )
    app.connect("doctree-resolved", deduplicate_todos, priority=400)
