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

The counterpart of `extra_platforms._utils`: plumbing every module may need,
without a domain of its own to live in. Nothing here imports from the rest of the
package, so any module can reach for these helpers without risking an import
cycle.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from contextlib import contextmanager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator, Iterator, Mapping
    from importlib.metadata import EntryPoint
    from pathlib import Path
    from typing import Any, Final


AUTO: Final = "auto"
"""The value asking an option to work its setting out by itself.

One spelling for every option offering it, like `--color=auto`, `--theme=auto`,
`--jobs auto` or the `auto` width of a capture. Each option names its own use of
it, with what the use derives, like {data}`~click_extra.theme.AUTO_THEME` or
{data}`~click_extra.table.AUTO_WIDTH`.
"""

BOOLEAN_STATES: dict[str, bool] = {
    "1": True,
    "yes": True,
    "true": True,
    "on": True,
    "0": False,
    "no": False,
    "false": False,
    "off": False,
}
"""The spellings of a boolean in text, lowercase, mapped to the value they name.

The table of {attr}`configparser.ConfigParser.BOOLEAN_STATES`, copied here so that
reading a boolean does not import {mod}`configparser` on the startup path of every
CLI. Read through {func}`parse_bool`.
"""

IS_WINDOWS: bool = sys.platform.startswith("win32")
"""Whether the running platform is Windows, as `extra_platforms.is_windows()` says.

Mirrors that function's own `sys.platform` test instead of calling it, for the
places that cannot wait for a deferred import of `extra_platforms`: the
module-level prompt sigil of {mod}`click_extra.execution`, the environment
variable names {func}`click_extra.envvar.merge_envvar_ids` computes for every
option at decoration time, and the configuration file search every invocation
runs, in
{meth}`~click_extra.config.discovery.ConfigDiscovery.search_and_read_file`.
Every other platform check in the package goes through `extra_platforms`,
imported where it is used.
"""

CLI_ECOSYSTEM_PACKAGES = frozenset({"functools", "click_extra", "cloup", "click"})
"""Top-level packages that never implement the *user's* CLI.

`functools` shows up as the intermediate frames a `@cached_property` adds; the
other three are the Click ecosystem itself. A frame belonging to one of them
is plumbing between a stack walk and the CLI that declared it, so
{meth}`click_extra.version.VersionOption.cli_frame` steps over them, and
{attr}`click_extra.version.VersionOption.module` and
{attr}`click_extra.version.VersionOption.module_version` read landing on one
as a failed walk. Those three exempt a module
{func}`click_extra.version.is_main_module` recognizes, since an entry point is
never plumbing, whichever package it sits under.
"""


def parse_bool(value: str) -> bool | None:
    """Read `value` as one of the spellings of {data}`BOOLEAN_STATES`.

    Case and surrounding whitespace do not matter. Returns `None` when `value`
    spells no boolean, which leaves each caller its own reading of that case: an
    error, a vote cast for nothing, or a default.
    """
    return BOOLEAN_STATES.get(value.strip().lower())


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


GENERATOR_TAG = "Click Extra"
"""Provenance tag for generated artifacts.

Stamped into the header comments of the documents Click Extra generates from a
CLI (man pages, Carapace completion specs, captures). This is Click Extra's *own*
name (the generator), not the documented CLI's.

The tag names no release. A capture carrying one is regenerated and re-committed
at every release, which would surface each bump as a diff in every committed
asset. A man page or completion spec is regenerated in place on the machine that
reads it, so its header gains nothing from naming a release that machine's own
environment already reports.
"""

DOCS_URL = "https://kdeldycke.github.io/click-extra"
"""Click Extra's documentation host.

Listed on Click Extra's own version screen, and the base of the page each
generated Carapace spec and capture watermark links to."""

REPOSITORY_URL = "https://github.com/kdeldycke/click-extra"
"""Click Extra's source repository, named in the provenance comment of every
generated man page."""


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
    table formatters) routes through this so they all point at the same
    `uv pip install` command, with the hyphenated distribution name.

    The requirement is single-quoted: the brackets of `package[extra]` are a
    glob pattern to a shell like zsh, which refuses the command unquoted.
    """
    return (
        f"{subject} requires an optional dependency. "
        f"Install it with: uv pip install '{package}[{extra}]'"
    )


@contextmanager
def patch_attr(obj: object, name: str, value: Any) -> Generator[None, None, None]:
    """Temporarily set `obj.name` to `value`, restoring the original on exit.

    A minimal, dependency-free stand-in for `unittest.mock.patch.object` for
    the simple save-set-restore monkeypatching Click Extra performs at runtime
    (in {mod}`~click_extra.logging`, {mod}`~click_extra.param_tools`,
    {mod}`~click_extra.show_params` and {mod}`~click_extra.testing`).

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


def flatten(iterable: Iterable[Any]) -> Iterator[Any]:
    """Yield the leaves of `iterable`, collapsing the iterables nested in it.

    A string or bytes counts as a leaf, not as an iterable of its characters.
    """
    for item in iterable:
        if isinstance(item, Iterable) and not isinstance(item, (str, bytes)):
            yield from flatten(item)
        else:
            yield item


def shrinkuser(path: str | os.PathLike[str], home: str = "~") -> str:
    """Replace the home directory prefix of `path` with `home`, `~` by default.

    The home directory itself becomes `home`, a path below it has that prefix
    replaced, and any other path comes back normalized but otherwise unchanged.
    """
    normalized = os.path.normpath(path)
    user_home = os.path.expanduser("~")
    if normalized == user_home:
        return home
    if normalized.startswith(user_home + os.sep):
        return home + normalized[len(user_home) :]
    return normalized


def walk_up(start: Path) -> Iterator[Path]:
    """Yield `start`, then each folder above it, up to the root of its filesystem.

    The order of a search for the nearest folder holding something, like a `.git`
    entry or a configuration file: the first match is the closest one.
    """
    yield start
    yield from start.parents


def deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Return `base` updated with `overlay`, nested dictionaries merged key by key.

    A key both carry resolves to the value of `overlay`, unless the two values
    are dictionaries, which merge the same way. A list, like any other value,
    comes whole from `overlay`: a layer setting one replaces the layer below.
    Neither argument is modified.
    """
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def set_nested(tree: dict[Any, Any], keys: Iterable[Any], value: Any) -> None:
    """Set `value` at the end of the path `keys` spells in `tree`.

    Each key names one level, and `keys` holds at least one. A level the path
    finds missing, or holding anything but a dictionary, becomes an empty
    dictionary. At the end of the path, a dictionary `value` merges into a
    dictionary already there, the way {func}`deep_merge` merges two layers, and
    any other value replaces what the path held.

    Merging a one-path tree into `tree` with {func}`deep_merge` has the same
    outcome, but copies every level the path crosses: building a tree one path at
    a time that way takes a time that grows with the square of its size.

    ```{caution}
    `tree` is modified in place, and so is every dictionary the path crosses,
    including one that a former call stored as its `value`.
    ```

    :raises ValueError: when `keys` is empty.
    """
    *parents, last = keys
    node = tree
    for key in parents:
        child = node.get(key)
        if not isinstance(child, dict):
            child = node[key] = {}
        node = child
    current = node.get(last)
    if isinstance(current, dict) and isinstance(value, dict):
        node[last] = deep_merge(current, value)
    else:
        node[last] = value


def remove_blanks(
    tree: Mapping[Any, Any],
    *,
    remove_none: bool = True,
    remove_dicts: bool = True,
    remove_str: bool = True,
) -> dict[Any, Any]:
    """Return a copy of `tree` without the items whose values are blank.

    A blank value is `None`, an empty string or an empty dictionary. Each
    `remove_*` argument set to `False` keeps the values of its kind. Nested
    dictionaries are cleaned the same way, and a dictionary the cleaning leaves
    empty is blank too. `tree` is not modified.
    """
    result: dict[Any, Any] = {}
    for key, value in tree.items():
        if remove_none and value is None:
            continue
        if isinstance(value, dict):
            cleaned = remove_blanks(
                value,
                remove_none=remove_none,
                remove_dicts=remove_dicts,
                remove_str=remove_str,
            )
            if remove_dicts and not cleaned:
                continue
            result[key] = cleaned
        elif remove_str and isinstance(value, str) and not value:
            continue
        else:
            result[key] = value
    return result
