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
"""List each docstring `{todo}` once on a `todolist`, and report those it misses.

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

The same cause has the opposite effect on a docstring that no page renders: the
docstring of a private module, of a private member that `:members:` skips, or
of a nested function. It never becomes a node, so its `{todo}` reaches no
`todolist`. This module reads the source of the documented packages instead,
and logs a {data}`UNRENDERED_TODO_WARNING` for each such `{todo}`. Its author can
then move it into a docstring that a page renders.

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

import ast
import inspect
import pkgutil
import re
import warnings
from importlib import import_module
from importlib.machinery import FileFinder
from importlib.util import find_spec
from pathlib import Path

from sphinx.ext.todo import todo_node, todolist
from sphinx.util import logging

from ..blocks import fence_spans

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from docutils import nodes
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment


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

UNRENDERED_TODO_WARNING = "click_extra.todo_unrendered"
"""Type and subtype of the warning about a docstring `{todo}` no page renders.

List it in `suppress_warnings` to silence the warning, or in
{data}`click_extra.sphinx.fail_on_warnings.FAIL_ON_WARNINGS_CONFIG` to fail the
build on it.
"""

_SHARED_VALUE_TYPES = (int, float, complex, str, bytes, tuple, frozenset, type(None))
"""Types whose equal values can be one object under several names.

Python reuses small integers, interned strings and the constants it folds at
compile time, so the identity of such a value tells nothing about its origin.
"""

_TODO_INFO_RE = re.compile(r"\{todo\}(?:\s|$)")
"""Info string of a backtick fence that opens a `todo` directive."""

_TODO_LINE_RE = re.compile(r"^\s*(?:\.\.\s+todo::|:{3,}\{todo\})(?:\s|$)")
"""A `todo` directive opened outside a backtick fence.

Matches the reST syntax and MyST's colon fence. A colon fence holds no code
block, so the lines inside one are read like any other line.
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


def _todo_lines(lines: list[str]) -> Iterator[int]:
    """Yield the index of each line in `lines` that opens a `todo` directive.

    A backtick fence holds a directive when its info string names one, like
    `{note}`, and a code block otherwise. The body of a directive is parsed, so
    a `todo` nested in it counts. The body of a code block is literal text, so
    a `todo` quoted in it as an example does not.
    """
    spans = fence_spans(lines)
    index = 0
    while index < len(lines):
        span = spans.get(index)
        if span is None:
            if _TODO_LINE_RE.match(lines[index]):
                yield index
            index += 1
            continue
        end = len(lines) if span.close is None else span.close
        info = lines[index].strip().lstrip("`")
        if _TODO_INFO_RE.match(info):
            yield index
        if info.startswith("{"):
            body = index + 1
            yield from (body + nested for nested in _todo_lines(lines[body:end]))
        index = end + 1


def _string_literal(statement: ast.stmt) -> ast.Constant | None:
    """Return the string literal `statement` is made of, or `None`."""
    if (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    ):
        return statement.value
    return None


def _assigned_names(statement: ast.stmt | None) -> list[str]:
    """Return the names an assignment binds, or none for any other statement."""
    if isinstance(statement, ast.Assign):
        targets = statement.targets
    elif isinstance(statement, ast.AnnAssign):
        targets = [statement.target]
    else:
        return []
    names: list[str] = []
    for target in targets:
        elements = (
            target.elts if isinstance(target, (ast.List, ast.Tuple)) else [target]
        )
        names.extend(item.id for item in elements if isinstance(item, ast.Name))
    return names


def _nested_blocks(statement: ast.stmt) -> Iterator[list[ast.stmt]]:
    """Yield the statement lists of a compound statement, like `if` or `try`."""
    for field in ("body", "orelse", "finalbody"):
        block = getattr(statement, field, None)
        if isinstance(block, list):
            yield block
    for handler in getattr(statement, "handlers", ()):
        yield handler.body
    for case in getattr(statement, "cases", ()):
        yield case.body


def _block_docstrings(
    body: list[ast.stmt], prefix: str
) -> Iterator[tuple[str, ast.Constant]]:
    """Yield each docstring defined in `body`, with its owner under `prefix`."""
    previous: ast.stmt | None = None
    for statement in body:
        if isinstance(statement, ast.ClassDef):
            yield from _scope_docstrings(statement.body, f"{prefix}.{statement.name}")
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = f"{prefix}.{statement.name}"
            if statement.body and (literal := _string_literal(statement.body[0])):
                yield qualname, literal
            yield from _block_docstrings(statement.body, f"{qualname}.<locals>")
        elif literal := _string_literal(statement):
            for name in _assigned_names(previous):
                yield f"{prefix}.{name}", literal
        else:
            for block in _nested_blocks(statement):
                yield from _block_docstrings(block, prefix)
        previous = statement


def _scope_docstrings(
    body: list[ast.stmt], owner: str
) -> Iterator[tuple[str, ast.Constant]]:
    """Yield the docstring of a module or class body, then the ones inside it."""
    if body and (literal := _string_literal(body[0])):
        yield owner, literal
    yield from _block_docstrings(body, owner)


def docstring_todos(source: str, module: str) -> Iterator[tuple[str, int]]:
    """Yield the owner and the line of each `todo` directive in docstrings.

    `source` is the text of the module named `module`. The owner of a docstring
    is the dotted path autodoc labels it with: `module` for the module
    docstring, and `{module}.{qualname}` for a class or a function, with
    `<locals>` for a definition nested in a function. An attribute docstring,
    the string literal right after an assignment, belongs to each name the
    assignment binds, as autodoc reads it. Lines count from 1.

    A directive counts in both syntaxes a docstring can use: a MyST fence,
    with backticks or colons, and a reST directive. A directive nested in
    another one counts too. A directive quoted in a code block does not.

    :raises SyntaxError: If `source` does not parse.
    """
    # The module compiled once already: do not print its syntax warnings again.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(source)
    lines = source.splitlines()
    for owner, literal in _scope_docstrings(tree.body, module):
        start = literal.lineno
        for offset in _todo_lines(lines[start - 1 : literal.end_lineno]):
            yield owner, start + offset


def _package_modules(package: str) -> Iterator[tuple[str, Path]]:
    """Yield the name and source file of `package` and of each module below it.

    Walks the file system the way the import system does, through
    {func}`importlib.util.find_spec` and {func}`pkgutil.iter_modules`, but
    imports nothing. A compiled extension has no source to read, and a
    directory without an `__init__.py` is not a package: both are skipped.
    """
    try:
        spec = find_spec(package)
    except (ImportError, ValueError):
        return
    if spec is None:
        return
    if spec.origin and spec.origin.endswith(".py"):
        yield package, Path(spec.origin)
    if spec.submodule_search_locations:
        yield from _submodules(package, spec.submodule_search_locations)


def _submodules(package: str, locations: Iterable[str]) -> Iterator[tuple[str, Path]]:
    """Yield the name and source file of each module found in `locations`."""
    for info in pkgutil.iter_modules(locations, prefix=f"{package}."):
        finder = info.module_finder
        if not isinstance(finder, FileFinder):
            continue
        spec = finder.find_spec(info.name)
        if spec is None:
            continue
        if spec.origin and spec.origin.endswith(".py"):
            yield info.name, Path(spec.origin)
        if info.ispkg and spec.submodule_search_locations:
            yield from _submodules(info.name, spec.submodule_search_locations)


def _resolve_object(dotted_path: str) -> object | None:
    """Import the object `dotted_path` names, or return `None` if it cannot.

    Imports the longest prefix that is a module, then reads the rest as
    attributes. An import can raise any exception, `SystemExit` included,
    which autodoc's own importer also catches whole.
    """
    parts = dotted_path.split(".")
    for index in range(len(parts), 0, -1):
        try:
            target: object = import_module(".".join(parts[:index]))
        except KeyboardInterrupt:
            raise
        except BaseException:  # noqa: BLE001, S112
            continue
        try:
            for name in parts[index:]:
                target = getattr(target, name)
        except Exception:  # noqa: BLE001
            return None
        return target
    return None


def _identity(target: object) -> int | None:
    """Return the `id()` that stands for `target`, or `None` if none can.

    A bound method is a new object at each attribute access, so it stands for
    its function. A value of `_SHARED_VALUE_TYPES` stands for nothing.
    """
    if inspect.ismethod(target):
        target = target.__func__
    if isinstance(target, _SHARED_VALUE_TYPES):
        return None
    return id(target)


def report_unrendered_todos(app: Sphinx, env: BuildEnvironment) -> None:
    """Warn about each docstring `{todo}` that no page renders.

    The warning has the {data}`UNRENDERED_TODO_WARNING` type, and points at the
    line of the directive. The check is connected to `env-check-consistency`,
    which fires once the build has read its documents and merged the domains of
    a parallel read: the `todo` domain then holds a node for each `{todo}` a
    page renders. Like Sphinx's own consistency checks, it does not fire on a
    build that reads no document.

    The packages read are the ones holding a module of the Python domain, which
    is where `automodule` registers the modules it documents. Every module of
    such a package is read, private ones included, without being imported.

    A docstring rendered under another path still counts. autodoc labels a
    function or a class with the path of its defining module, whatever path
    reached it, but labels an attribute or a property with the path it
    documented. So when the labels differ, the check imports the object behind
    both paths and compares them.

    Inert unless the project enables `sphinx.ext.todo` with `todo_include_todos`:
    without it, no `{todo}` renders anywhere, so none can be missing.
    """
    domain = env.domains.get("todo")
    if domain is None or not getattr(app.config, "todo_include_todos", False):
        return

    rendered = set()
    for todos in domain.todos.values():
        for node in todos:
            source = node.source or ""
            _, marker, dotted_path = source.partition(AUTODOC_DOCSTRING_MARKER)
            if marker:
                rendered.add(dotted_path)

    python_domain = env.domains.get("py")
    modules = python_domain.modules if python_domain is not None else {}
    packages = sorted({name.partition(".")[0] for name in modules})

    warning_type, _, subtype = UNRENDERED_TODO_WARNING.partition(".")
    # Built for the first todo that no label matches, since building it imports.
    rendered_objects: dict[int, object] | None = None
    for package in packages:
        for module, path in _package_modules(package):
            try:
                found = list(docstring_todos(path.read_text(encoding="utf-8"), module))
            except (OSError, SyntaxError, ValueError):
                continue
            for owner, line in found:
                if owner in rendered:
                    continue
                if rendered_objects is None:
                    rendered_objects = {}
                    for dotted_path in rendered:
                        target = _resolve_object(dotted_path)
                        key = _identity(target)
                        if key is not None:
                            rendered_objects[key] = target
                if (
                    rendered_objects
                    and _identity(_resolve_object(owner)) in rendered_objects
                ):
                    continue
                logger.warning(
                    "click_extra.sphinx: no page renders the docstring of %s, so "
                    "no todolist can list this todo.",
                    owner,
                    type=warning_type,
                    subtype=subtype,
                    location=f"{path}:{line}",
                )


def setup(app: Sphinx) -> None:
    """Register the deduplication hook and the unrendered-todo check on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. Priority 400 places the
    deduplication hook below the default 500
    {class}`sphinx.ext.todo.TodoListProcessor` is connected at, which is what
    makes the domain already trimmed by the time the list is rendered.
    """
    app.add_config_value(
        DEDUPE_TODOS_CONFIG, default=True, rebuild="html", types=[bool]
    )
    app.connect("doctree-resolved", deduplicate_todos, priority=400)
    app.connect("env-check-consistency", report_unrendered_todos)
