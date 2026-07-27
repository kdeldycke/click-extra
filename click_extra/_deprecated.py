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
"""Backward-compatible deprecated aliases.

Symbols that were renamed or moved between modules stay importable from their
original location for one deprecation cycle. Accessing one emits a
{exc}`DeprecationWarning` pointing at its replacement, through the
[PEP 562](https://peps.python.org/pep-0562/) module `__getattr__` hooks wired
into `click_extra/__init__.py`, `click_extra/version.py` and
`click_extra/testing.py`. The renamed `click_extra.test_plan` module keeps its
own import-time shim in `click_extra/test_plan.py`.

```{important}
Aliases registered here are scheduled for removal in the release recorded in
{data}`REMOVAL_VERSION`. When that release is cut, delete this module, the
`test_plan.py` shim, every `__getattr__` hook that calls
{func}`resolve_deprecated`, and their tests.
```
"""

from __future__ import annotations

import warnings
from importlib import import_module

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

REMOVAL_VERSION = "9.0.0"
"""The release in which the registered aliases stop resolving."""

DEPRECATED_ALIASES: dict[str, dict[str, str]] = {
    "click_extra": {
        "ClickExtraConfig": "config.ClickExtraConfig",
        "DEFAULT_TEST_PLAN": "test_suite.DEFAULT_TEST_SUITE",
        "PrebakeConfig": "config.PrebakeConfig",
        "TestPlanConfig": "config.TestSuiteConfig",
        "TestSuiteConfig": "config.TestSuiteConfig",
        "parse_test_plan": "test_suite.parse_test_suite",
        "run_test_plan": "test_suite.run_test_suite",
    },
    "click_extra.testing": {
        "INDENT": "execution.INDENT",
        "PROMPT": "execution.PROMPT",
        "args_cleanup": "execution.args_cleanup",
        "format_cli_prompt": "execution.format_cli_prompt",
    },
    "click_extra.version": {
        "discover_package_init_files": "prebake.discover_package_init_files",
        "prebake_dunder": "prebake.prebake_dunder",
        "prebake_version": "prebake.prebake_version",
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
    shares: the module `__getattr__` hooks (through {func}`resolve_deprecated`)
    and the {mod}`click_extra.test_plan` import shim. Threads in
    {data}`REMOVAL_VERSION` so the announced removal release lives in one place.

    :param subject: dotted name of the deprecated symbol or module.
    :param replacement: dotted name of what to use instead.
    :return: the warning message text.
    """
    return (
        f"{subject} is deprecated and will be removed in click-extra "
        f"{REMOVAL_VERSION}, use {replacement} instead."
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
