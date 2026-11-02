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
"""Deprecated alias of {mod}`click_extra.markdown.blocks`.

Serves each `9.x` name of this path that the new module still defines. A
[PEP 562](https://peps.python.org/pep-0562/) module `__getattr__` hook resolves
each one and warns on every access. Released `repomatic` versions up to `8.0.0`
import `region_markers` and `replace_region` from here, and downstream workflows
pin them.
"""

from __future__ import annotations

import warnings

from .markdown import blocks as _markdown_blocks

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

_ALIASED_NAMES = frozenset({
    "FenceSpan",
    "fence_spans",
    "iter_markdown_files",
    "marker_res",
    "region_markers",
    "replace_region",
    "rewrite_fenced_regions",
    "skip_region",
    "split_options",
    "update_blocks",
})
"""Public names of the `9.x` module that {mod}`click_extra.markdown.blocks` keeps.

`OPTION_LINE_RE` is not among them: `10.0.0` removed it with no replacement.
"""

__all__ = tuple(sorted(_ALIASED_NAMES))
"""The names a star import binds, each through `__getattr__` and its warning.

Derived rather than spelled out: ruff's F822 reports each name of a literal
`__all__` that only `__getattr__` defines.
"""

_REMOVAL_VERSION = "11.0.0"
"""The release in which this alias stops resolving."""


def __getattr__(name: str) -> Any:
    """Serve a name of {data}`_ALIASED_NAMES` from its new module, with a warning.

    The value is never cached here, so every access warns. Any other name raises
    {exc}`AttributeError` without a warning, like the `__path__` probe the import
    system runs on every `from click_extra.blocks import` statement.
    """
    if name not in _ALIASED_NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        f"{__name__}.{name} is deprecated and will be removed in click-extra "
        f"{_REMOVAL_VERSION}, use {_markdown_blocks.__name__}.{name} instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return getattr(_markdown_blocks, name)
