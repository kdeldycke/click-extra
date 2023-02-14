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

"""Old deprecated module.

Redefines all constants to keep backward compatibility.

.. warning::

    ``click_extra.platform`` is deprecated since version 3.8.0.

    Use ``click_extra.platforms`` (with a trailing ``s``) instead.
"""

import warnings

from boltons.dictutils import FrozenDict

from .platforms import AIX as NEW_AIX
from .platforms import OTHER_UNIX  # noqa: F401
from .platforms import (  # noqa: F401
    ALL_LINUX,
    ALL_OS_LABELS,
    ALL_PLATFORMS,
    BSD,
    CURRENT_OS_ID,
    CURRENT_OS_LABEL,
)
from .platforms import CYGWIN as NEW_CYGWIN
from .platforms import FREEBSD as NEW_FREEBSD
from .platforms import HURD as NEW_HURD
from .platforms import LINUX as NEW_LINUX
from .platforms import MACOS as NEW_MACOS
from .platforms import NETBSD as NEW_NETBSD
from .platforms import OPENBSD as NEW_OPENBSD
from .platforms import SOLARIS as NEW_SOLARIS
from .platforms import SUNOS as NEW_SUNOS
from .platforms import SYSTEM_V, UNIX, UNIX_LAYERS, UNIX_WITHOUT_MACOS  # noqa: F401
from .platforms import WINDOWS as NEW_WINDOWS
from .platforms import WSL1 as NEW_WSL1
from .platforms import WSL2 as NEW_WSL2
from .platforms import current_os as new_current_os
from .platforms import (  # noqa: F401
    is_aix,
    is_cygwin,
    is_freebsd,
    is_hurd,
    is_linux,
    is_macos,
    is_netbsd,
    is_openbsd,
    is_solaris,
    is_sunos,
    is_windows,
    is_wsl1,
    is_wsl2,
    os_label,
)

warnings.warn(
    "Use click_extra.platforms instead of click_extra.platform", DeprecationWarning
)

AIX = NEW_AIX.id
CYGWIN = NEW_CYGWIN.id
FREEBSD = NEW_FREEBSD.id
HURD = NEW_HURD.id
LINUX = NEW_LINUX.id
MACOS = NEW_MACOS.id
NETBSD = NEW_NETBSD.id
OPENBSD = NEW_OPENBSD.id
SOLARIS = NEW_SOLARIS.id
SUNOS = NEW_SUNOS.id
WINDOWS = NEW_WINDOWS.id
WSL1 = NEW_WSL1.id
WSL2 = NEW_WSL2.id

OS_DEFINITIONS = FrozenDict({p.id: (p.name, p.current) for p in ALL_PLATFORMS})
ANY_PLATFORM = frozenset(p.id for p in ALL_PLATFORMS)
ANY_UNIX = frozenset(p.id for p in UNIX.platforms)
ANY_UNIX_BUT_MACOS = frozenset(p.id for p in UNIX_WITHOUT_MACOS.platforms)
ANY_BSD = frozenset(p.id for p in BSD.platforms)
ANY_LINUX = frozenset(p.id for p in ALL_LINUX.platforms)
ANY_UNIX_SYSTEM_V = frozenset(p.id for p in SYSTEM_V.platforms)
ANY_UNIX_COMPATIBILITY_LAYER = frozenset(p.id for p in UNIX_LAYERS.platforms)
ANY_OTHER_UNIX = frozenset(p.id for p in OTHER_UNIX.platforms)


def current_os():
    platform = new_current_os()
    return platform.id, platform.name
