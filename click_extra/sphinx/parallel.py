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
"""Make a parallel Sphinx read index what a serial read indexes.

A parallel read, started with `--jobs`, shares the documents among worker
processes, then merges what each worker read into the environment of the main
process. A serial read reads every document in one process, in name order. Two
things then differ between the two reads.

The first is the merge of the Python domain. `PythonDomain.merge_domaindata`
copies the entries of each worker over the ones in place. So the alias that a
page re-exporting an object declares with `:canonical:` can replace the
definition that the page of its module registered in another worker. A serial
read keeps the definition, because `PythonDomain.note_object` never lets an
alias replace one. This module puts back each definition that an alias
replaced. The cross-references to such an object then lead to the page of its
module, and so do the `[docs]` links of {mod}`click_extra.sphinx.viewcode`.

The second is what a worker does not see of the other documents. To find the
type of a documented attribute, autodoc copies the annotations of the source of
a module into the `__annotations__` of that module and of its classes. These
include the `self.x: T` of an `__init__` and the names of an
`if TYPE_CHECKING:` block, and autodoc lists each name of `__annotations__` as a
member. So a page lists these names only after another page has documented an
attribute of the same module, which in a parallel read can happen in another
worker. This module copies the annotations before autodoc lists the members of
a module or a class, so that every read lists the same members.

```{todo}
Delete {func}`keep_definitions_over_aliases` once
`PythonDomain.merge_domaindata` keeps a definition over an alias, and
{func}`copy_source_annotations` once autodoc lists the members of an object
whatever it documented before. Each goes when the `sphinx` extra's floor passes
the release that carries its fix, and the module goes with the last of them.
```
"""

from __future__ import annotations

import sys
from types import ModuleType

from sphinx.errors import PycodeError
from sphinx.pycode import ModuleAnalyzer
from sphinx.util.inspect import getmro, safe_getattr

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet
    from typing import Any

    from sphinx.application import Sphinx
    from sphinx.domains.python import ObjectEntry
    from sphinx.environment import BuildEnvironment


AUTODOC_EXTENSION = "sphinx.ext.autodoc"
"""Module name of the extension whose member lists {func}`copy_source_annotations`
keeps from following the read order."""


_MERGED_DEFINITIONS: dict[str, ObjectEntry] = {}
"""The Python objects that the merged workers of the running read define, by name.

{func}`keep_definitions_over_aliases` fills it as the main process merges each
worker, and {func}`forget_merged_definitions` empties it before each read.
"""


def forget_merged_definitions(
    app: Sphinx, env: BuildEnvironment, docnames: list[str]
) -> None:
    """Empty the record of {func}`keep_definitions_over_aliases` before a read.

    Connected to `env-before-read-docs`, so a read restores only the definitions
    of its own workers, never one from an earlier build in the same process.
    """
    _MERGED_DEFINITIONS.clear()


def keep_definitions_over_aliases(
    app: Sphinx,
    env: BuildEnvironment,
    docnames: AbstractSet[str],
    other: BuildEnvironment,
) -> None:
    """Put back each Python definition that the alias of a later worker replaced.

    Connected to `env-merge-info`, which fires in the main process each time a
    parallel read has merged the entries of a worker. Records each definition
    the worker brings, and puts the recorded definition back over each alias the
    worker brings for the same name, as a serial read keeps it. A worker holds
    the entries of the documents it did not read too, but merges only those of
    `docnames`, so only those count. Inert in a serial read, which merges no
    worker.
    """
    objects = env.domaindata["py"]["objects"]
    for fullname, entry in other.domaindata["py"]["objects"].items():
        if entry.docname not in docnames:
            continue
        if not entry.aliased:
            _MERGED_DEFINITIONS[fullname] = entry
        elif fullname in _MERGED_DEFINITIONS:
            objects[fullname] = _MERGED_DEFINITIONS[fullname]


def _annotate_from_source(module: ModuleType) -> None:
    """Add each annotation the source of `module` gives to the object it annotates.

    The annotations of the module body go to the module, and those of a class
    body or of `self` in a method go to the class, as autodoc adds them the
    first time it documents an attribute of the module. A name already annotated
    keeps its annotation, so a second call changes nothing.

    ```{caution}
    The annotations are added to the mapping the object holds, in place. autodoc
    assigns a new mapping instead, which from Python 3.14 on also clears the
    `__annotate__` of a class. A `TypedDict` reads the fields of its bases
    through their `__annotate__`, so after that assignment a subclass whose
    annotations are not cached yet lists its own fields alone. An object whose
    annotations do not evaluate yet is left alone, for autodoc to read later.
    ```
    """
    try:
        analyzer = ModuleAnalyzer.for_module(module.__name__)
        analyzer.analyze()
    except PycodeError:
        return
    owners: dict[str, dict[str, Any] | None] = {}
    for (qualname, attribute), annotation in analyzer.annotations.items():
        if qualname not in owners:
            owner: Any = module
            for part in filter(None, qualname.split(".")):
                owner = safe_getattr(owner, part, None)
            annotations = safe_getattr(owner, "__annotations__", None)
            owners[qualname] = annotations if isinstance(annotations, dict) else None
        if (annotations := owners[qualname]) is not None:
            annotations.setdefault(attribute, annotation)


def copy_source_annotations(
    app: Sphinx, what: str, name: str, obj: Any, options: Any, lines: list[str]
) -> None:
    """Annotate a module or a class from its source before autodoc lists members.

    Connected to `autodoc-process-docstring`, which fires for a module or a class
    before autodoc gathers its members. For a class, the module of each class of
    its MRO gets annotated, as a class also lists the annotations of its bases.
    """
    if what == "module":
        modules = [obj]
    elif what in {"class", "exception"}:
        modules = [
            sys.modules.get(safe_getattr(cls, "__module__", "")) for cls in getmro(obj)
        ]
    else:
        return
    for module in modules:
        if isinstance(module, ModuleType):
            _annotate_from_source(module)


def connect_source_annotations(app: Sphinx) -> None:
    """Connect {func}`copy_source_annotations` once every extension is set up.

    Connected to `builder-inited`, so `sphinx.ext.autodoc` has registered its
    events whatever its place in `extensions`. Inert without autodoc, and with
    `autodoc_use_type_comments` off, which keeps autodoc from copying any
    annotation.
    """
    if AUTODOC_EXTENSION in app.extensions and getattr(
        app.config, "autodoc_use_type_comments", True
    ):
        app.connect("autodoc-process-docstring", copy_source_annotations)


def setup(app: Sphinx) -> None:
    """Register the parallel-read fixes on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. The two merge hooks are inert in
    a serial read, which merges no worker. The annotation hook steadies the
    members of a serial read too, whose pages also follow one another.
    """
    app.connect("builder-inited", connect_source_annotations)
    app.connect("env-before-read-docs", forget_merged_definitions)
    app.connect("env-merge-info", keep_definitions_over_aliases)
