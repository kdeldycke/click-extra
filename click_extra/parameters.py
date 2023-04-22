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
"""Our own flavor of ``Option``, ``Argument`` and ``parameters``.

Also implements environment variable utilities.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Sequence

import click
from boltons.iterutils import unique

from . import Option


def auto_envvar(
    param: click.Parameter, ctx: click.Context | Dict[str, Any]
) -> str | None:
    """Compute the auto-generated environment variable of an option or argument.

    Returns the auto envvar as it is exacly computed within Click's internals, i.e.
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

    # Mimicks Click's internals.
    return f"{prefix}_{param.name.upper()}"


def extend_envvars(
    envvars_1: str | Sequence[str] | None, envvars_2: str | Sequence[str] | None
) -> tuple[str, ...]:
    """Utility to build environment variables value to be fed to options.

    Variable names are deduplicated while preserving their initial order.

    Returns a tuple of environment variable strings. The result is ready to be used as
    the ``envvar`` parameter for options or arguments.
    """
    # Make the fist argument into a list of string.
    envvars = []
    if envvars_1:
        if isinstance(envvars_1, str):
            envvars = [envvars_1]
        else:
            envvars = list(envvars_1)

    # Merge the second argument into the list.
    if envvars_2:
        if isinstance(envvars_2, str):
            envvars.append(envvars_2)
        else:
            envvars.extend(envvars_2)

    # Deduplicate the list and cast it into an immutable tuple.
    return tuple(unique(envvars))


def normalize_envvar(envvar: str) -> str:
    """Utility to normalize an environment variable name.

    The normalization process separates all contiguous alphanumeric string segments,
    eliminate empty strings, join them with an underscore and uppercase the result.
    """
    return "_".join((p for p in re.split(r"[^a-zA-Z0-9]+", envvar) if p)).upper()


def all_envvars(
    param: click.Parameter, ctx: click.Context | Dict[str, Any], normalize: bool = False
) -> tuple[str, ...]:
    """Returns the deduplicated, ordered list of environment variables for an option or
    argument, including the auto-generated one.

    The auto-generated environment variable is added at the end of the list, so that
    user-defined envvars takes precedence. This respects the current implementation
    of ``click.core.Option.resolve_envvar_value()``.

    If ``normalize`` is `True`, the returned value is normalized. By default it is
    `False` to perfectly reproduce the
    `current behavior of Click, which is subject to discussions <https://github.com/pallets/click/issues/2483>`_.
    """
    auto_envvar_id = auto_envvar(param, ctx)
    envvars = extend_envvars(param.envvar, auto_envvar_id)

    if normalize:
        envvars = tuple(normalize_envvar(var) for var in envvars)

    return envvars


class ExtraOption(Option):
    """All new options implemented by ``click-extra`` derives from this class.

    Does nothing in particular for now but provides a way to identify click-extra's own
    options with certainty. Might be used in the future to implement common behavior,
    fixes or hacks.
    """
