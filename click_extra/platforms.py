# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

"""Helpers and utilities to identify platforms.

.. seealso::

    A nice alternative would be to use the excellent `distro
    <https://github.com/python-distro/distro>`_ package, but it `does not yet support
    detection of macOS and Windows
    <https://github.com/python-distro/distro/issues/177>`_.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field

if sys.version_info >= (3, 9):
    from functools import cache
else:
    from functools import lru_cache

    def cache(user_function):
        """Simple lightweight unbounded cache. Sometimes called "memoize".

        .. important::

            This is a straight `copy of the functools.cache implementation
            <https://github.com/python/cpython/blob/55a26de6ba938962dc23f2495723cf0f4f3ab7c6/Lib/functools.py#L647-L653>`_,
            which is only `available in the standard library starting with Python v3.9
            <https://docs.python.org/3/library/functools.html?highlight=caching#functools.cache>`.
        """
        return lru_cache(maxsize=None)(user_function)


""" Below is the collection of heuristics used to identify each platform.

All these heuristics can be hard-cached as the underlying system is not suppose to
change between code execution.
"""


@cache
def is_aix() -> bool:
    """Return `True` only if current platform is of the AIX family."""
    return sys.platform.startswith("aix")


@cache
def is_cygwin() -> bool:
    """Return `True` only if current platform is of the Cygwin family."""
    return sys.platform.startswith("cygwin")


@cache
def is_freebsd() -> bool:
    """Return `True` only if current platform is of the FreeBSD family."""
    return sys.platform.startswith(("freebsd", "midnightbsd"))


@cache
def is_hurd() -> bool:
    """Return `True` only if current platform is of the GNU/Hurd family."""
    return sys.platform.startswith("GNU")


@cache
def is_linux() -> bool:
    """Return `True` only if current platform is of the Linux family."""
    return sys.platform.startswith("linux")


@cache
def is_macos() -> bool:
    """Return `True` only if current platform is of the macOS family."""
    return platform.platform(terse=True).startswith(("macOS", "Darwin"))


@cache
def is_netbsd() -> bool:
    """Return `True` only if current platform is of the NetBSD family."""
    return sys.platform.startswith("netbsd")


@cache
def is_openbsd() -> bool:
    """Return `True` only if current platform is of the OpenBSD family."""
    return sys.platform.startswith("openbsd")


@cache
def is_solaris() -> bool:
    """Return `True` only if current platform is of the Solaris family."""
    return platform.platform(aliased=True, terse=True).startswith("Solaris")


@cache
def is_sunos() -> bool:
    """Return `True` only if current platform is of the SunOS family."""
    return platform.platform(aliased=True, terse=True).startswith("SunOS")


@cache
def is_windows() -> bool:
    """Return `True` only if current platform is of the Windows family."""
    return sys.platform.startswith("win32")


@cache
def is_wsl1() -> bool:
    """Return `True` only if current platform is Windows Subsystem for Linux v1.

    .. caution::
        The only difference between WSL1 and WSL2 is `the case of the kernel release
        version <https://github.com/andweeb/presence.nvim/pull/64#issue-1174430662>`_:

        - WSL 1:

          .. code-block:: shell-session

                $ uname -r
                4.4.0-22572-Microsoft

        - WSL 2:

          .. code-block:: shell-session

                $ uname -r
                5.10.102.1-microsoft-standard-WSL2
    """
    return "Microsoft" in platform.release()


@cache
def is_wsl2() -> bool:
    """Return `True` only if current platform is Windows Subsystem for Linux v2."""
    return "microsoft" in platform.release()


@dataclass()
class Platform:
    """A platform can identify multiple distributions or OSes with the same
    characteristics."""

    id: str
    """Unique ID of the platform."""

    name: str
    """User-friendly name of the platform."""

    current: bool = field(init=False)
    """`True` if current environment has been identified as being of this platform."""

    def __post_init__(self):
        """Set the ``current`` attribute to identifying the current platform."""
        check_func_id = f"is_{self.id}"
        assert check_func_id in globals()
        self.current = globals()[check_func_id]()


AIX = Platform("aix", "AIX")
""" Identify distributions of the AIX family. """

CYGWIN = Platform("cygwin", "Cygwin")
""" Identify distributions of the Cygwin family. """

FREEBSD = Platform("freebsd", "FreeBSD")
""" Identify distributions of the FreeBSD family. """

HURD = Platform("hurd", "GNU/Hurd")
""" Identify distributions of the GNU/Hurd family. """

LINUX = Platform("linux", "Linux")
""" Identify distributions of the Linux family. """

MACOS = Platform("macos", "macOS")
""" Identify distributions of the macOS family. """

NETBSD = Platform("netbsd", "NetBSD")
""" Identify distributions of the NetBSD family. """

OPENBSD = Platform("openbsd", "OpenBSD")
""" Identify distributions of the OpenBSD family. """

SOLARIS = Platform("solaris", "Solaris")
""" Identify distributions of the Solaris family. """

SUNOS = Platform("sunos", "SunOS")
""" Identify distributions of the SunOS family. """

WINDOWS = Platform("windows", "Windows")
""" Identify distributions of the Windows family. """

WSL1 = Platform("wsl1", "Windows Subsystem for Linux v1")
""" Identify Windows Subsystem for Linux v1. """

WSL2 = Platform("wsl2", "Windows Subsystem for Linux v2")
""" Identify Windows Subsystem for Linux v2. """


ALL_PLATFORMS: tuple[Platform, ...] = (
    AIX,
    CYGWIN,
    FREEBSD,
    HURD,
    LINUX,
    MACOS,
    NETBSD,
    OPENBSD,
    SOLARIS,
    SUNOS,
    WINDOWS,
    WSL1,
    WSL2,
)
"""All platforms."""


@dataclass()
class Group:
    """A ``Group`` identify a family of ``Platform``."""

    id: str
    """Unique ID of the group."""

    name: str
    """User-friendly description of a group."""

    platforms: list[Platform]

    def __post_init__(self):
        """Keep the platforms sorted by IDs."""
        self.platforms.sort(key=lambda p: p.id)

    def __iter__(self):
        """Iterate over the platforms of the group."""
        yield from self.platforms

    def __len__(self):
        """Return the number of platforms in the group."""
        return len(self.platforms)


ALL_WINDOWS = Group("all_windows", "All Windows", [WINDOWS])
""" All Windows operating systems."""


ALL_UNIX = Group("unix", "All Unix", [p for p in ALL_PLATFORMS if p not in ALL_WINDOWS])
""" All Unix-like operating systems and compatibility layers."""


ALL_UNIX_WITHOUT_MACOS = Group(
    "unix_without_macos", "All Unix without macOS", [p for p in ALL_UNIX if p != MACOS]
)
""" All Unix platforms, without macOS.

This is useful to avoid macOS-specific workarounds on Unix platforms.
"""


ALL_BSD = Group("bsd", "All BSD", [FREEBSD, MACOS, NETBSD, OPENBSD, SUNOS])
""" All BSD platforms.

.. note::
    Are considered of this family (`according Wikipedia
    <https://en.wikipedia.org/wiki/Template:Unix>`_):

    - `386BSD` (`FreeBSD`, `NetBSD`, `OpenBSD`, `DragonFly BSD`)
    - `NeXTSTEP`
    - `Darwin` (`macOS`, `iOS`, `audioOS`, `iPadOS`, `tvOS`, `watchOS`, `bridgeOS`)
    - `SunOS`
    - `Ultrix`
"""


ALL_LINUX = Group("all_linux", "All Linux", [LINUX])
""" All Unix platforms based on a Linux kernel.

.. note::
    Are considered of this family (`according Wikipedia
    <https://en.wikipedia.org/wiki/Template:Unix>`_):

    - `Android`
    - `ChromeOS`
    - any other distribution
"""


ALL_LINUX_COMPATIBILITY_LAYER = Group(
    "all_linux_layers", "All Linux compatibility layers", [WSL1, WSL2]
)
""" Interfaces that allows Linux binaries to run on a different host system.

.. note::
    Are considered of this family (`according Wikipedia
    <https://en.wikipedia.org/wiki/Template:Unix>`_):

    - `Windows Subsystem for Linux`
"""


ALL_UNIX_SYSTEM_V = Group(
    "all_system_v", "All Unix derived from AT&T System Five", [AIX, SOLARIS]
)
""" All Unix platforms derived from AT&T System Five.

.. note::
    Are considered of this family (`according Wikipedia
    <https://en.wikipedia.org/wiki/Template:Unix>`_):

    - `A/UX`
    - `AIX`
    - `HP-UX`
    - `IRIX`
    - `OpenServer`
    - `Solaris`
    - `OpenSolaris`
    - `Illumos`
    - `Tru64`
    - `UNIX`
    - `UnixWare`
"""


ALL_UNIX_COMPATIBILITY_LAYER = Group(
    "all_unix_layers", "All Unix compatibility layers", [CYGWIN]
)
""" Interfaces that allows Unix binaries to run on a different host system.

.. note::
    Are considered of this family (`according Wikipedia
    <https://en.wikipedia.org/wiki/Template:Unix>`_):

    - `Cygwin`
    - `Darling`
    - `Eunice`
    - `GNV`
    - `Interix`
    - `MachTen`
    - `Microsoft POSIX subsystem`
    - `MKS Toolkit`
    - `PASE`
    - `P.I.P.S.`
    - `PWS/VSE-AF`
    - `UNIX System Services`
    - `UserLAnd Technologies`
    - `Windows Services for UNIX`
"""


ALL_OTHER_UNIX = Group(
    "all_other_unix",
    "All other Unix",
    [
        p
        for p in ALL_UNIX
        if p
        not in (
            ALL_BSD.platforms
            + ALL_LINUX.platforms
            + ALL_LINUX_COMPATIBILITY_LAYER.platforms
            + ALL_UNIX_SYSTEM_V.platforms
            + ALL_UNIX_COMPATIBILITY_LAYER.platforms
        )
    ],
)
""" All other Unix platforms.

.. note::
    Are considered of this family (`according Wikipedia
    <https://en.wikipedia.org/wiki/Template:Unix>`_):

    - `Coherent`
    - `GNU/Hurd`
    - `HarmonyOS`
    - `LiteOS`
    - `LynxOS`
    - `Minix`
    - `MOS`
    - `OSF/1`
    - `QNX`
    - `BlackBerry 10`
    - `Research Unix`
    - `SerenityOS`
"""


NON_OVERLAPPING_GROUPS: tuple[Group, ...] = (
    ALL_WINDOWS,
    ALL_BSD,
    ALL_LINUX,
    ALL_LINUX_COMPATIBILITY_LAYER,
    ALL_UNIX_SYSTEM_V,
    ALL_UNIX_COMPATIBILITY_LAYER,
    ALL_OTHER_UNIX,
)
"""Non-overlapping groups."""


EXTRA_GROUPS: tuple[Group, ...] = (ALL_UNIX, ALL_UNIX_WITHOUT_MACOS)
"""Overlapping groups, defined for convenience."""


ALL_GROUPS: tuple[Group, ...] = NON_OVERLAPPING_GROUPS + EXTRA_GROUPS
"""All groups."""


ALL_OS_LABELS: frozenset[str] = frozenset({p.name for p in ALL_PLATFORMS})
""" Sets of all recognized labels. """


@cache
def os_label(os_id: str) -> str | None:
    """Return platform label for user-friendly output."""
    for p in ALL_PLATFORMS:
        if p.id == os_id:
            return p.name
    return None


@cache
def current_os() -> Platform:
    """Return the current platform."""
    matching = []
    for p in ALL_PLATFORMS:
        if p.current:
            matching.append(p)

    if len(matching) > 1:
        raise RuntimeError(f"Multiple platforms match current OS: {matching}")

    if not matching:
        raise SystemError(
            f"Unrecognized {sys.platform} / {platform.platform(aliased=True, terse=True)} platform."
        )

    assert len(matching) == 1
    return matching.pop()


CURRENT_OS_ID: str = current_os().id
CURRENT_OS_LABEL: str = current_os().name
"""Constants about the current platform."""
