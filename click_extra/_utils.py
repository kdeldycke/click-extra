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

import sys
from contextlib import contextmanager
from enum import Enum
from functools import cache

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from importlib.metadata import EntryPoint
    from typing import Any


IS_WINDOWS: bool = sys.platform.startswith("win32")
"""Whether the running platform is Windows, as `extra_platforms.is_windows()` says.

Mirrors that function's own `sys.platform` test instead of calling it, for the
two places that cannot wait for a deferred import of `extra_platforms`: the
module-level prompt sigil of {mod}`click_extra.execution`, and the environment
variable names {func}`click_extra.envvar.merge_envvar_ids` computes for every
option at decoration time. Every other platform check in the package goes
through `extra_platforms`, imported where it is used.
"""

CLI_ECOSYSTEM_PACKAGES = frozenset({"functools", "click_extra", "cloup", "click"})
"""Top-level packages that never implement the *user's* CLI.

`functools` shows up as the intermediate frames a `@cached_property` adds; the
other three are the Click ecosystem itself. A frame belonging to one of them
is plumbing between a stack walk and the CLI that declared it, so both
{meth}`click_extra.version.VersionOption.cli_frame` and the deprecation
`stacklevel` walk in `_deprecated.py` step over them, and
{attr}`click_extra.version.VersionOption.module` and
{attr}`click_extra.version.VersionOption.module_version` read landing on one
as a failed walk. Those three exempt a module
{func}`click_extra.version.is_main_module` recognizes, since an entry point is
never plumbing, whichever package it sits under. The `stacklevel` walk needs no
such exemption: it reads a frame's own `__name__`, which an entry point sets to
`__main__`, already outside this set.
"""


def exception_chain(exc: BaseException | None) -> Iterator[BaseException]:
    """Yield `exc`, then each exception it stems from, nearest first.

    Follows the cause an exception was raised from, and failing that the
    exception it replaced while that one was being handled. Stops at an
    exception already seen, so a chain that loops back on itself still ends.
    """
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        yield exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__


def console_script(name: str) -> EntryPoint | None:
    """The `console_scripts` entry point installed under `name`, or `None`.

    Its `module` and `attr` name the callable the script runs, which is how a
    generated script in a `bin/` folder is traced back to the package behind it.
    """
    # Deferred import: keeps importlib.metadata off the startup path of every CLI.
    from importlib import metadata

    for entry_point in metadata.entry_points(group="console_scripts", name=name):
        return entry_point
    return None


@cache
def generator_tag() -> str:
    """Provenance tag for generated artifacts: `Click Extra`.

    Stamped into the header comments of the documents Click Extra generates
    from a CLI (man pages, Carapace completion specs, captures). This is Click
    Extra's *own* name (the generator), not the documented CLI's.

    The tag names no release. A capture carrying one is regenerated and
    re-committed at every release, which would surface each bump as a diff in
    every committed asset. A man page or completion spec is regenerated in
    place on the machine that reads it, so its header gains nothing from naming
    a release that machine's own environment already reports.
    """
    return "Click Extra"


def memoize_enums(obj: object, memo: dict[int, Any], *also: Enum) -> None:
    """Seed a `copy.deepcopy` *memo* with the enum members `obj` holds, and *also*.

    Python 3.10's `Enum` implements no `__deepcopy__`, so `copy.deepcopy`
    rebuilds a member by calling its class with a deep copy of the member's
    *value*. Click and Click Extra both follow
    [PEP 661](https://peps.python.org/pep-0661/) and back their sentinels with
    bare `object()` values, which copy into a different object no lookup can
    resolve, raising `ValueError: <object object> is not a valid Sentinel`.
    Since Click 8.3 one of those sentinels sits on most parameters as their
    unset default, so copying a parameter at all crashes there.

    A memo entry mapping a member's `id()` to the member itself makes
    `copy.deepcopy` hand it back untouched, which is what Python 3.11 and later
    do natively. Every member of a class found on `obj` is seeded, not just the
    one held, so a sibling sentinel nested deeper in the same copy is covered
    too.

    ```{caution}
    Reading `obj` alone covers a copy only when `obj` itself holds a member of
    the class that breaks it, which is why *also* takes the members a caller
    knows the graph carries. Click 8.4 leaves `VersionOption.default` a plain
    `False` and puts the sentinel on its siblings instead, so a copy seeded
    from the option alone still reached an unseeded one through their shared
    option group.

    Seeding is required on every entry point into a copy: a `__deepcopy__`
    reached with an empty memo has to do it for itself.
    ```

    :param obj: the object about to be copied, read for the members it holds.
    :param memo: the `copy.deepcopy` memo to seed, updated in place.
    :param also: members whose classes are seeded whatever `obj` holds.
    """
    for value in (*vars(obj).values(), *also):
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
def patch_attr(obj: object, name: str, value: Any) -> Generator[None, None, None]:
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
