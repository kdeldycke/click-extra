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
"""Publish only the `sphinx.ext.viewcode` pages that a documented object links to.

`sphinx.ext.viewcode` reads the source of every module a documented object may
come from, and keeps an entry for that module even when none of its objects gets
a `[source]` link. Each such entry becomes a page of highlighted source that only
the `_modules` index links to. A documented constant is the usual cause:
viewcode looks for its definition in the module that defines the class of its
value, like `re` for a compiled pattern, and finds none there.

A serial read drops such an entry when it purges the next document, so only the
last document read leaves one behind. A parallel read merges the entries of its
workers after every purge has run, so it publishes a page for each unused module
([sphinx-doc/sphinx#14675](https://github.com/sphinx-doc/sphinx/issues/14675)).
This module drops every entry with no recorded use once the read is over, which
gives both reads the same pages.

A module whose source viewcode cannot read keeps an entry too, set to `False`.
An attribute whose value is a builtin class, like a `group_class` set to `type`,
sends viewcode to `builtins`, which has no source. viewcode writes no page for
such a module, but its index lists every entry, so the index links a page that
does not exist. This module drops these entries as well.

The same entry also sets where the `[docs]` links of a page point. viewcode
builds all of them from one module path: the path of the signature that created
the entry. A documented instance reports the module of its class, so an instance
can create the entry of that class's module and lend it its own module path,
under which none of the objects of the page is indexed. The links then lead to
anchors that do not exist, and which signature comes first follows the read
order ([sphinx-doc/sphinx#14815](https://github.com/sphinx-doc/sphinx/pull/14815)).
This module gives each page the module path under which most of its objects are
indexed, and points each link at the page that holds the object.

That count reads the objects of the Python domain. A parallel read merges the
objects of its workers with `PythonDomain.merge_domaindata`, which copies the
entries of each worker over the ones in place. So the alias that a page
re-exporting an object declares with `:canonical:` can replace the definition
that the page of its module registered in another worker, and the `[docs]` links
of that module lose their anchors. A serial read keeps the definition, because
`PythonDomain.note_object` never lets an alias replace one. This module puts back
each definition that an alias replaced. The cross-references to such an object
then lead to the page of its module, as in a serial read.

```{todo}
Delete {func}`drop_unused_viewcode_modules` once
[sphinx-doc/sphinx#14675](https://github.com/sphinx-doc/sphinx/issues/14675) is
fixed and the viewcode index leaves out the modules it could not read,
{func}`anchor_viewcode_backlinks` once
[sphinx-doc/sphinx#14815](https://github.com/sphinx-doc/sphinx/pull/14815)
ships, and {func}`keep_definitions_over_aliases` once
`PythonDomain.merge_domaindata` keeps a definition over an alias. Each goes when
the `sphinx` extra's floor passes the release that carries its fix, and the
module goes with the last of them.
```
"""

from __future__ import annotations

from collections import Counter

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

    from sphinx.application import Sphinx
    from sphinx.domains.python import ObjectEntry
    from sphinx.environment import BuildEnvironment


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


def drop_unused_viewcode_modules(app: Sphinx, env: BuildEnvironment) -> None:
    """Forget each module that viewcode could not read, or that no document links.

    Connected to `env-updated`, which fires once the read is over: after a
    parallel read merged the entries of its workers, and before Sphinx pickles
    the environment. A module viewcode could not read has no page, and the
    viewcode index links every module it keeps. Without its entry, the next
    incremental read that documents an object of that module tries to read it
    again, which fails at the same cost. Inert without `sphinx.ext.viewcode`,
    which creates the entries.
    """
    modules = getattr(env, "_viewcode_modules", {})
    for modname, entry in list(modules.items()):
        # A module viewcode could not read is `False`. A read one is a tuple of
        # its code, its tags, the objects documented from it, and its refname.
        if not entry or not entry[2]:
            del modules[modname]


def anchor_viewcode_backlinks(app: Sphinx, env: BuildEnvironment) -> None:
    """Point the `[docs]` links of each viewcode page at the objects' own anchors.

    Connected to `env-updated` after {func}`drop_unused_viewcode_modules`. For
    each module, counts the linked objects that the Python domain indexes under
    each leading part of the module path, and keeps the part that indexes the
    most, the shortest on a tie. Each link then leads to the page of the object
    indexed under that part. A module whose objects no part indexes keeps the
    links viewcode gave it. In a parallel read, the count relies on
    {func}`keep_definitions_over_aliases` to index each object as a serial read
    does. Inert without `sphinx.ext.viewcode`.
    """
    objects = env.domaindata["py"]["objects"]
    modules = getattr(env, "_viewcode_modules", {})
    for modname, entry in list(modules.items()):
        if not entry:
            continue
        code, tags, used, _ = entry
        parts = modname.split(".")
        hits: Counter[str] = Counter()
        for prefix in (".".join(parts[:depth]) for depth in range(1, len(parts) + 1)):
            for fullname in used:
                target = objects.get(f"{prefix}.{fullname}")
                if target and not target.aliased:
                    hits[prefix] += 1
        if not hits:
            continue
        best = min(hits, key=lambda prefix: (-hits[prefix], prefix))
        for fullname in used:
            target = objects.get(f"{best}.{fullname}")
            if target and not target.aliased:
                used[fullname] = target.docname
        modules[modname] = (code, tags, used, best)


def setup(app: Sphinx) -> None:
    """Register the viewcode fixes on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. The two merge hooks keep the
    Python domain of a parallel read as a serial read leaves it, with or without
    `sphinx.ext.viewcode`. The two `env-updated` hooks run in the order they are
    connected: the backlinks are set on the modules the first one keeps.
    """
    app.connect("env-before-read-docs", forget_merged_definitions)
    app.connect("env-merge-info", keep_definitions_over_aliases)
    app.connect("env-updated", drop_unused_viewcode_modules)
    app.connect("env-updated", anchor_viewcode_backlinks)
