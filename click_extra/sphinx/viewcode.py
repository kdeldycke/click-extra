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

{mod}`click_extra.sphinx.parallel` keeps the index of a parallel read in line.

```{todo}
Delete {func}`drop_unused_viewcode_modules` once
[sphinx-doc/sphinx#14675](https://github.com/sphinx-doc/sphinx/issues/14675) is
fixed and [sphinx-doc/sphinx#14677](https://github.com/sphinx-doc/sphinx/pull/14677)
leaves the modules viewcode could not read out of its index, and
{func}`anchor_viewcode_backlinks` once
[sphinx-doc/sphinx#14815](https://github.com/sphinx-doc/sphinx/pull/14815)
ships, each when the `sphinx` extra's floor passes the release that carries the
fix. The module goes with the second of the two.
```
"""

from __future__ import annotations

from collections import Counter

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment


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
    {func}`~click_extra.sphinx.parallel.keep_definitions_over_aliases` to index
    each object as a serial read does. Inert without `sphinx.ext.viewcode`.
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
    `"click_extra.sphinx"` in their `extensions`. Both hooks share the
    `env-updated` event, so they run in the order they are connected: the
    backlinks are set on the modules the first hook keeps.
    """
    app.connect("env-updated", drop_unused_viewcode_modules)
    app.connect("env-updated", anchor_viewcode_backlinks)
