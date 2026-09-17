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
"""Backward-compatible deprecated aliases and arguments.

Symbols that were renamed or moved between modules stay importable from their
original location for one deprecation cycle. Accessing one emits a
{exc}`DeprecationWarning` pointing at its replacement, through the
[PEP 562](https://peps.python.org/pep-0562/) module `__getattr__` hooks wired
into `click_extra/color.py`, `click_extra/parameters.py` and
`click_extra/theme.py`. A renamed argument keeps its old name for the same
cycle, and passing it warns through {func}`warn_deprecated_argument`, as a
retired value or shape of a value does through {func}`warn_deprecated_usage`.

```{todo}
Cut all of it in the release recorded in {data}`REMOVAL_VERSION`: delete this
module, every `__getattr__` hook that calls {func}`resolve_deprecated`, every
form handled by a call to {func}`warn_deprecated_argument` or
{func}`warn_deprecated_usage`, and their tests,
exactly as the `9.0.0` release did with the previous batch.
```
"""

from __future__ import annotations

import os
import sys
import warnings
from importlib import import_module

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

REMOVAL_VERSION = "10.0.0"
"""The release in which the registered aliases stop resolving."""

_PACKAGE_DIR = os.path.join(os.path.dirname(__file__), "")
"""This package's directory, trailing separator included, to tell its frames apart."""

DEPRECATED_ALIASES: dict[str, dict[str, str]] = {
    "click_extra.color": {
        "color_envvars": "color.COLOR_ENVVARS",
    },
    "click_extra.parameters": {
        "generator_tag": "_utils.generator_tag",
        "missing_extra_message": "_utils.missing_extra_message",
        "patch_attr": "_utils.patch_attr",
    },
    "click_extra.theme": {
        "nocolor_theme": "theme.NOCOLOR_THEME",
    },
}
"""Maps each deprecated symbol to its replacement, keyed by hosting module.

Replacement paths are relative to the top-level `click_extra` package, which
{func}`resolve_deprecated` prepends: every target therefore resolves under
`click_extra`.
"""


def deprecation_message(subject: str, replacement: str) -> str:
    """Standard deprecation notice for `subject`, pointing at `replacement`.

    Single source for the wording every deprecation warning in the package
    shares, emitted by the module `__getattr__` hooks through
    {func}`resolve_deprecated`. Threads in {data}`REMOVAL_VERSION` so the
    announced removal release lives in one place.

    :param subject: dotted name of the deprecated symbol or module.
    :param replacement: dotted name of what to use instead.
    :return: the warning message text.
    """
    return (
        f"{subject} is deprecated and will be removed in click-extra "
        f"{REMOVAL_VERSION}, use {replacement} instead."
    )


def _outside_stacklevel() -> int:
    """The `stacklevel` of the first frame outside this package, for its caller.

    Counted from the function calling this one, which is where
    {func}`warnings.warn` starts counting. A deprecated form can be caught
    several frames deep (a header deep in a table render, an argument
    forwarded by a subclass), and a fixed level would then blame this
    package instead of the code to change.
    """
    frame = sys._getframe(1)
    level = 1
    while frame.f_back is not None and frame.f_code.co_filename.startswith(
        _PACKAGE_DIR
    ):
        frame = frame.f_back
        level += 1
    return level


def warn_deprecated_usage(subject: str, replacement: str) -> None:
    """Warn that `subject` is deprecated, at the first call site outside this package.

    The counterpart of the module aliases for everything else a caller passes:
    a renamed argument, a retired value, an old shape of a value. The wording
    and the announced removal release stay in one place.

    :param subject: what is deprecated, like `A (label, column_id) header`.
    :param replacement: what to use instead.
    """
    warnings.warn(
        deprecation_message(subject, replacement),
        DeprecationWarning,
        stacklevel=_outside_stacklevel(),
    )


def warn_deprecated_argument(function: str, argument: str, replacement: str) -> None:
    """Warn that `argument` of `function` is deprecated, at the caller's call site.

    A renamed argument keeps its old name for one deprecation cycle, and passing
    it warns through here.

    :param function: name of the callable taking the argument, like `Spinner`.
    :param argument: the deprecated argument name.
    :param replacement: what to pass instead, like `live=`.
    """
    warnings.warn(
        deprecation_message(f"{function}({argument}=...)", replacement),
        DeprecationWarning,
        stacklevel=_outside_stacklevel(),
    )


def resolve_deprecated(module_id: str, name: str) -> Any:
    """Resolve an attribute access delegated from a module's `__getattr__` hook.

    Looks `name` up among the {data}`DEPRECATED_ALIASES` registered for
    `module_id`. For a deprecated alias, emits a {exc}`DeprecationWarning`
    naming the replacement and returns the replacement object. For any other
    name, raises {exc}`AttributeError` so unknown attributes behave as usual.

    The warning is attributed to the caller's access site (`stacklevel=3`:
    this function, the hosting module's `__getattr__`, then the caller).

    ```{note}
    An unregistered `module_id` yields {exc}`AttributeError`, not
    {exc}`KeyError`. Hooks pass their live `__name__`, which is not always the
    import-time module name: frame-walking helpers may rebind a module's
    `__name__` (the `VersionOption.cli_frame` test does), and this stays a
    graceful missing-attribute lookup rather than crashing.
    ```

    :param module_id: dotted name of the module hosting the deprecated alias.
    :param name: the attribute being accessed on that module.
    :return: the replacement object the alias now points to.
    :raises AttributeError: when `module_id` or `name` is not registered.
    """
    target = DEPRECATED_ALIASES.get(module_id, {}).get(name)
    if target is None:
        raise AttributeError(f"module {module_id!r} has no attribute {name!r}")
    full_target = f"{module_id.split('.', 1)[0]}.{target}"
    warnings.warn(
        deprecation_message(f"{module_id}.{name}", full_target),
        DeprecationWarning,
        stacklevel=3,
    )
    target_module, _, target_attr = full_target.rpartition(".")
    return getattr(import_module(target_module), target_attr)
