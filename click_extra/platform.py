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

from boltons.dictutils import FrozenDict

AIX = "aix"
""" Constant used to identify distributions of the AIX family. """

CYGWIN = "cygwin"
""" Constant used to identify distributions of the Cygwin family. """

FREEBSD = "freebsd"
""" Constant used to identify distributions of the FreeBSD family. """

HURD = "hurd"
""" Constant used to identify distributions of the GNU/Hurd family. """

LINUX = "linux"
""" Constant used to identify distributions of the Linux family. """

MACOS = "macos"
""" Constant used to identify distributions of the macOS family. """

NETBSD = "netbsd"
""" Constant used to identify distributions of the NetBSD family. """

OPENBSD = "openbsd"
""" Constant used to identify distributions of the OpenBSD family. """

SOLARIS = "solaris"
""" Constant used to identify distributions of the Solaris family. """

SUNOS = "sunos"
""" Constant used to identify distributions of the SunOS family. """

WINDOWS = "windows"
""" Constant used to identify distributions of the Windows family. """

WSL1 = "wsl1"
""" Constant used to identify Windows Subsystem for Linux v1. """

WSL2 = "wsl2"
""" Constant used to identify Windows Subsystem for Linux v2. """


def is_aix():
    """Return `True` only if current platform is of the AIX family."""
    return sys.platform.startswith("aix")


def is_cygwin():
    """Return `True` only if current platform is of the Cygwin family."""
    return sys.platform.startswith("cygwin")


def is_freebsd():
    """Return `True` only if current platform is of the FreeBSD family."""
    return sys.platform.startswith(("freebsd", "midnightbsd"))


def is_hurd():
    """Return `True` only if current platform is of the GNU/Hurd family."""
    return sys.platform.startswith("GNU")


def is_linux():
    """Return `True` only if current platform is of the Linux family."""
    return sys.platform.startswith("linux")


def is_macos():
    """Return `True` only if current platform is of the macOS family."""
    return platform.platform(terse=True).startswith(("macOS", "Darwin"))


def is_netbsd():
    """Return `True` only if current platform is of the NetBSD family."""
    return sys.platform.startswith("netbsd")


def is_openbsd():
    """Return `True` only if current platform is of the OpenBSD family."""
    return sys.platform.startswith("openbsd")


def is_solaris():
    """Return `True` only if current platform is of the Solaris family."""
    return platform.platform(aliased=True, terse=True).startswith("Solaris")


def is_sunos():
    """Return `True` only if current platform is of the SunOS family."""
    return platform.platform(aliased=True, terse=True).startswith("SunOS")


def is_windows():
    """Return `True` only if current platform is of the Windows family."""
    return sys.platform.startswith("win32")


def is_wsl1():
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


def is_wsl2():
    """Return `True` only if current platform is Windows Subsystem for Linux v2."""
    return "microsoft" in platform.release()


OS_DEFINITIONS = FrozenDict(
    {
        AIX: ("IBM AIX", is_aix()),
        CYGWIN: ("Cygwin", is_cygwin()),
        FREEBSD: ("FreeBSD", is_freebsd()),
        HURD: ("GNU/Hurd", is_hurd()),
        LINUX: ("Linux", is_linux()),
        MACOS: ("macOS", is_macos()),
        NETBSD: ("NetBSD", is_netbsd()),
        OPENBSD: ("OpenBSD", is_openbsd()),
        SOLARIS: ("Oracle Solaris", is_solaris()),
        SUNOS: ("SunOS", is_sunos()),
        WINDOWS: ("Windows", is_windows()),
        WSL1: ("Windows Subsystem for Linux v1", is_wsl1()),
        WSL2: ("Windows Subsystem for Linux v2", is_wsl2()),
    }
)
"""Map OS IDs to evaluation function and OS labels."""

ANY_PLATFORM = frozenset(OS_DEFINITIONS)
""" IDs of all platforms."""

ANY_UNIX = frozenset(set(OS_DEFINITIONS) - {WINDOWS})
""" IDs of all Unix-like operating systems and compatibility layers."""

ANY_UNIX_BUT_MACOS = frozenset(ANY_UNIX - {MACOS})
""" IDs of all Unix platforms, without macOS.

This is useful to avoid macOS-specific workarounds on Unix platforms.
"""

ANY_BSD = frozenset({FREEBSD, MACOS, NETBSD, OPENBSD, SUNOS})
""" IDs of all BSD platforms.

.. note::
    Are considered of this family (`according Wikipedia
    <https://en.wikipedia.org/wiki/Template:Unix>`_):

    - `386BSD` (`FreeBSD`, `NetBSD`, `OpenBSD`, `DragonFly BSD`)
    - `NeXTSTEP`
    - `Darwin` (`macOS`, `iOS`, `audioOS`, `iPadOS`, `tvOS`, `watchOS`, `bridgeOS`)
    - `SunOS`
    - `Ultrix`
"""

ANY_LINUX = frozenset({LINUX})
""" IDs of all Unix platforms based on a Linux kernel.

.. note::
    Are considered of this family (`according Wikipedia
    <https://en.wikipedia.org/wiki/Template:Unix>`_):

    - `Android`
    - `ChromeOS`
    - any other distribution
"""

ANY_UNIX_SYSTEM_V = frozenset({AIX, SOLARIS})
""" IDs of all Unix platforms derived from AT&T System Five.

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

ANY_UNIX_COMPATIBILITY_LAYER = frozenset({CYGWIN, WSL1, WSL2})
""" IDs of interfaces that allows UNIX binaries to run on a different host system.

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
    - `Windows Subsystem for Linux`
"""


ANY_OTHER_UNIX = (
    ANY_UNIX - ANY_BSD - ANY_LINUX - ANY_UNIX_SYSTEM_V - ANY_UNIX_COMPATIBILITY_LAYER
)
""" IDs of all other Unix platforms.

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


ALL_OS_LABELS: frozenset[str] = frozenset(
    {label for label, _ in OS_DEFINITIONS.values()}
)
""" Sets of recognized IDs and labels. """


def os_label(os_id):
    """Return platform label for user-friendly output."""
    return OS_DEFINITIONS[os_id][0]


def current_os():
    """Return a 2-items `tuple` with ID and label of current OS."""
    for os_id, (os_name, os_flag) in OS_DEFINITIONS.items():
        if os_flag is True:
            return os_id, os_name
    raise SystemError(
        f"Unrecognized {sys.platform} / {platform.platform(aliased=True, terse=True)} platform."
    )


CURRENT_OS_ID, CURRENT_OS_LABEL = current_os()
