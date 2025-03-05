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
"""Implements environment variable utilities."""

from __future__ import annotations

import os
import re
from typing import Any, Iterable, Mapping

import click
import click.testing
from boltons.iterutils import flatten_iter

TEnvVarID = str | None
TEnvVarIDs = Iterable[TEnvVarID]
TNestedEnvVarIDs = Iterable[TEnvVarID | Iterable["TNestedEnvVarIDs"]]
"""Types environment variable names."""

TEnvVars = Mapping[str, str | None]
"""Type for ``dict``-like environment variables."""


def merge_envvar_ids(*envvar_ids: TEnvVarID | TNestedEnvVarIDs) -> tuple[str, ...]:
    """Merge and deduplicate environment variables.

    Multiple parameters are accepted and can be single strings or arbitrary-nested
    iterables of strings. ``None`` values are ignored.

    Variable names are deduplicated while preserving their initial order.

    .. caution::
        `On Windows, environment variable names are case-insensitive
        <https://docs.python.org/3/library/os.html#os.environ>`_, so we `normalize them
        to uppercase as the standard library does
        <https://github.com/python/cpython/blob/ffef9b0/Lib/os.py#L777-L786>`_.

    Returns a tuple of strings. The result is ready to be used as the ``envvar``
    parameter for Click's options or arguments.
    """
    ids = []
    for envvar in flatten_iter(envvar_ids):
        if envvar:
            if os.name == "nt":
                envvar = envvar.upper()
            # Deduplicate names.
            if envvar not in ids:
                ids.append(envvar)
    return tuple(ids)


def clean_envvar_id(envvar_id: str) -> str:
    """Utility to produce a user-friendly environment variable name from a string.

    Separates all contiguous alphanumeric string segments, eliminate empty strings,
    join them with an underscore and uppercase the result.

    .. attention::
        We do not rely too much on this utility to try to reproduce the `current
        behavior of Click, which is is not consistent regarding case-handling of
        environment variable <https://github.com/pallets/click/issues/2483>`_.
    """
    return "_".join(p for p in re.split(r"[^a-zA-Z0-9]+", envvar_id) if p).upper()


def param_auto_envvar_id(
    param: click.Parameter,
    ctx: click.Context | dict[str, Any],
) -> str | None:
    """Compute the auto-generated environment variable of an option or argument.

    Returns the auto envvar as it is exactly computed within Click's internals, i.e.
    ``click.core.Parameter.resolve_envvar_value()`` and
    ``click.core.Option.resolve_envvar_value()``.
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
    of ``click.core.Option.resolve_envvar_value()``.

    .. caution::
        `On Windows, environment variable names are case-insensitive
        <https://docs.python.org/3/library/os.html#os.environ>`_, so we `normalize them
        to uppercase as the standard library does
        <https://github.com/python/cpython/blob/ffef9b0/Lib/os.py#L777-L786>`_.
    """
    return merge_envvar_ids(param.envvar, param_auto_envvar_id(param, ctx))


def env_copy(extend: TEnvVars | None = None) -> TEnvVars | None:
    """Returns a copy of the current environment variables and eventually ``extend`` it.

    Mimics `Python's original implementation
    <https://github.com/python/cpython/blob/7b5b429/Lib/subprocess.py#L1648-L1649>`_ by
    returning ``None`` if no ``extend`` content are provided.

    Environment variables are expected to be a ``dict`` of ``str:str``.
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
