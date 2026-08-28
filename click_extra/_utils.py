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
"""Generic helpers with no Click knowledge, shared across the package.

The counterpart of `extra_platforms._utils`: plumbing every module may need
(attribute patching, provenance tagging, optional-extra messaging) without a
domain of its own to live in. Nothing here imports from the rest of the
package, so any module can reach for these helpers without risking an import
cycle.
"""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from importlib import metadata

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any


def generator_tag() -> str:
    """Provenance tag for generated artifacts: `Click Extra <version>`.

    Stamped into the header comments of the documents Click Extra generates
    from a CLI (man pages, Carapace completion specs). This is Click Extra's
    *own* version (the generator), not the documented CLI's version. Falls back
    to the bare name when the distribution metadata is unavailable (such as
    running from an uninstalled source tree).
    """
    try:
        return f"Click Extra {metadata.version('click-extra')}"
    except metadata.PackageNotFoundError:
        return "Click Extra"


def memoize_enums(obj: object, memo: dict[int, Any]) -> None:
    """Seed a `copy.deepcopy` *memo* with the enum members `obj`'s attributes hold.

    Python 3.10's `Enum` implements no `__deepcopy__`, so `copy.deepcopy`
    rebuilds a member by calling its class with a deep copy of the member's
    *value*. Click and Click Extra both follow
    [PEP 661](https://peps.python.org/pep-0661/) and back their sentinels with
    bare `object()` values, which copy into a different object no lookup can
    resolve, raising `ValueError: <object object> is not a valid Sentinel`.
    Since Click 8.3 one of those sentinels sits on every parameter as its unset
    default, so copying any parameter at all crashes there.

    A memo entry mapping a member's `id()` to the member itself makes
    `copy.deepcopy` hand it back untouched, which is what Python 3.11 and later
    do natively. Every member of a class found on `obj` is seeded, not just the
    one held, so a sibling sentinel nested deeper in the same copy is covered
    too.

    ```{caution}
    Seeding is required on every entry point into a copy: a `__deepcopy__`
    reached with an empty memo has to do it for itself.
    ```
    """
    for value in vars(obj).values():
        if isinstance(value, Enum):
            memo.update({id(member): member for member in type(value)})


def missing_extra_message(
    extra: str,
    *,
    package: str = "click-extra",
    subject: str = "This feature",
) -> str:
    """Build the uniform "install the optional extra" error message.

    `subject` names what needs the dependency, `extra` is the optional
    dependency group and `package` its distribution name. Every feature gated
    behind an extra (the documentation integrations, the Carapace exporter, the
    table formatters) routes through this so they all point at the same canonical
    `pip install package[extra]` target, with the hyphenated distribution name.
    """
    return (
        f"{subject} requires an optional dependency. "
        f"Install it with: pip install {package}[{extra}]"
    )


@contextmanager
def patch_attr(obj: object, name: str, value: Any) -> Iterator[None]:
    """Temporarily set `obj.name` to `value`, restoring the original on exit.

    A minimal, dependency-free stand-in for `unittest.mock.patch.object` for
    the simple save-set-restore monkeypatching Click Extra performs at runtime
    (in {mod}`~click_extra.logging`, {mod}`~click_extra.parameters` and
    {mod}`~click_extra.testing`).

    ```{note}
    `unittest.mock` drags the whole test framework, and its heavy
    transitive imports, into the startup path of every CLI built with Click
    Extra. Reimplementing the single feature actually used keeps that cost
    out of import time. Do not swap this back for `unittest.mock`.
    ```

    Like `patch.object` without `create=True`, the attribute must already
    exist: a missing `name` raises {exc}`AttributeError`.
    """
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)
