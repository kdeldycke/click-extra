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

from __future__ import annotations

from . import Option
from typing import Sequence
from boltons.iterutils import unique


def extend_envvars(orig_envvar: str | Sequence[str] | None, extra_envvars: str | Sequence[str]) -> str | tuple[str]:
    """Utility to build environment variables value to be fed to options.

    Deduplicates the list of string if multiple elements are provided.

    Returns a tuple of environment variable strings or a plein string if only a single
    element persist. The result is ready to be used as the ``envvar`` parameter for
    options or arguments.
    """
    envvars = []
    if orig_envvar:
        if isinstance(orig_envvar, str):
            envvars = [orig_envvar]
        else:
            envvars = list(orig_envvar)

    if isinstance(extra_envvars, str):
        envvars.append(extra_envvars)
    else:
        envvars.extend(extra_envvars)

    envvars = unique(envvars)

    if len(envvars) == 1:
        return envvars[0]
    return tuple(envvars)


class ExtraOption(Option):
    """All new options implemented by ``click-extra`` derives from this class.

    Does nothing in particular for now but provides a way to identify click-extra's own
    options with certainty. Might be used in the future to implement common behavior,
    fixes or hacks.
    """
