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

```{todo}
Delete this module once
[sphinx-doc/sphinx#14675](https://github.com/sphinx-doc/sphinx/issues/14675) is
fixed and the `sphinx` extra's floor passes the release that carries the fix.
```
"""

from __future__ import annotations

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment


def drop_unused_viewcode_modules(app: Sphinx, env: BuildEnvironment) -> None:
    """Forget each module `sphinx.ext.viewcode` read but no document links.

    Connected to `env-updated`, which fires once the read is over: after a
    parallel read merged the entries of its workers, and before Sphinx pickles
    the environment. Inert without `sphinx.ext.viewcode`, which creates the
    entries.
    """
    modules = getattr(env, "_viewcode_modules", {})
    for modname, entry in list(modules.items()):
        # A module viewcode could not read is `False`. A read one is a tuple of
        # its code, its tags, the objects documented from it, and its refname.
        if entry and not entry[2]:
            del modules[modname]


def setup(app: Sphinx) -> None:
    """Register the cleanup of unused viewcode modules on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`.
    """
    app.connect("env-updated", drop_unused_viewcode_modules)
