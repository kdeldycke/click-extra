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
"""Implements environment variable utilities.

.. seealso:
    [Environment variables are a legacy mess: Let's dive deep into them](https://allvpv.org/haotic-journey-through-envvars/).
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager

import click
from boltons.iterutils import flatten_iter
from extra_platforms import is_windows

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping
    from typing import Any

    TEnvVarID = str | None
    """Type of environment variable names."""

    TNestedEnvVarIDs = Iterable[TEnvVarID | Iterable["TNestedEnvVarIDs"]]
    """Type for arbitrary nested environment variable names."""

    TEnvVars = Mapping[str, str | None]
    """Type for `dict`-like environment variables."""


def merge_envvar_ids(*envvar_ids: TEnvVarID | TNestedEnvVarIDs) -> tuple[str, ...]:
    """Merge and deduplicate environment variables.

    Multiple parameters are accepted and can be single strings or arbitrary-nested
    iterables of strings. `None` values are ignored.

    Variable names are deduplicated while preserving their initial order.

    ```{caution}
    [On Windows, environment variable names are case-insensitive](https://docs.python.org/3/library/os.html#os.environ), so we [normalize them to uppercase as the standard library does](https://github.com/python/cpython/blob/3.14/Lib/os.py#L770-L782).
    ```

    Returns a tuple of strings. The result is ready to be used as the `envvar`
    parameter for Click's options or arguments.
    """
    ids = []
    for envvar in flatten_iter(envvar_ids):
        if envvar:
            if is_windows():
                envvar = envvar.upper()
            # Deduplicate names.
            if envvar not in ids:
                ids.append(envvar)
    return tuple(ids)


def clean_envvar_id(envvar_id: str) -> str:
    """Utility to produce a user-friendly environment variable name from a string.

    Separates all contiguous alphanumeric string segments, eliminate empty strings,
    join them with an underscore and uppercase the result.

    ```{attention}
    We do not rely too much on this utility to try to reproduce the [current behavior of Click, which is not consistent regarding case-handling of environment variable](https://github.com/pallets/click/issues/2483).
    ```
    """
    return "_".join(p for p in re.split(r"[^a-zA-Z0-9]+", envvar_id) if p).upper()


def param_auto_envvar_id(
    param: click.Parameter,
    ctx: click.Context | dict[str, Any],
) -> str | None:
    """Compute the auto-generated environment variable of an option or argument.

    Returns the auto envvar exactly as computed within Click's internals, by
    `click.core.Parameter.resolve_envvar_value()` and
    `click.core.Option.resolve_envvar_value()`.
    """
    # Skip parameters that have their auto-envvar explicitly disabled.
    if not getattr(param, "allow_from_autoenv", None):
        return None

    if isinstance(ctx, click.Context):
        prefix = ctx.auto_envvar_prefix
    else:
        prefix = ctx.get("auto_envvar_prefix")
    if not prefix or not param.name:
        return None

    # Mimics Click's internals.
    return f"{prefix}_{param.name.upper()}"


def param_envvar_ids(
    param: click.Parameter,
    ctx: click.Context | dict[str, Any],
) -> tuple[str, ...]:
    """Returns the deduplicated, ordered list of environment variables for an option or
    argument, including the auto-generated one.

    The auto-generated environment variable is added at the end of the list, so that
    user-defined envvars takes precedence. This respects the current implementation
    of `click.core.Option.resolve_envvar_value()`.

    Names are normalized to uppercase on Windows by {func}`merge_envvar_ids`.
    """
    return merge_envvar_ids(param.envvar, param_auto_envvar_id(param, ctx))


@contextmanager
def temporary_env(
    set_vars: Mapping[str, str] | None = None,
    unset_vars: Iterable[str] = (),
) -> Iterator[None]:
    """Apply environment variable changes for the block's duration, then restore.

    *set_vars* are written into {data}`os.environ` and *unset_vars* removed. On
    exit, every touched variable is restored to its pre-block state: recreated
    with its former value, or removed when it did not exist before.

    The process environment is patched directly (not through test-framework
    fixtures) so the helper serves production code paths and test harnesses
    alike, with a single restore discipline.
    """
    set_vars = dict(set_vars or {})
    # Materialized up front: the iterable is consumed twice (snapshot + removal).
    unset_vars = tuple(unset_vars)
    saved = {var: os.environ.get(var) for var in (*set_vars, *unset_vars)}
    os.environ.update(set_vars)
    for var in unset_vars:
        os.environ.pop(var, None)
    try:
        yield
    finally:
        for var, value in saved.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value


def env_copy(extend: TEnvVars | None = None) -> TEnvVars | None:
    """Returns a copy of the current environment variables and eventually `extend` it.

    Mimics [Python's original implementation](https://github.com/python/cpython/blob/3.14/Lib/subprocess.py#L1907-L1908) by
    returning `None` if no `extend` content are provided.

    Environment variables are expected to be a `dict` of `str:str`.
    """
    if isinstance(extend, dict):
        for k, v in extend.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
    else:
        assert not extend
    env_copy: TEnvVars | None = None
    if extend:
        # By casting to dict we make a copy and prevent the modification of the
        # global environment.
        env_copy = dict(os.environ)
        env_copy.update(extend)
    return env_copy
