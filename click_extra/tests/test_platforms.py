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

from __future__ import annotations

from itertools import combinations
from types import FunctionType

from ..platforms import (
    ALL_GROUPS,
    ALL_OS_FAMILIES,
    ALL_OS_LABELS,
    ANY_BSD,
    ANY_LINUX,
    ANY_LINUX_COMPATIBILITY_LAYER,
    ANY_OTHER_UNIX,
    ANY_PLATFORM,
    ANY_UNIX,
    ANY_UNIX_COMPATIBILITY_LAYER,
    ANY_UNIX_SYSTEM_V,
    ANY_WINDOWS,
    CURRENT_OS_ID,
    CURRENT_OS_LABEL,
    LINUX,
    MACOS,
    OS_DEFINITIONS,
    WINDOWS,
    current_os,
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
from .conftest import (
    skip_linux,
    skip_macos,
    skip_windows,
    unless_linux,
    unless_macos,
    unless_windows,
)


def test_mutual_exclusion():
    # Only test the OSes on which the test suite is running via GitHub actions.
    if is_linux():
        assert not is_aix()
        assert not is_cygwin()
        assert not is_freebsd()
        assert not is_hurd()
        assert not is_macos()
        assert not is_netbsd()
        assert not is_openbsd()
        assert not is_solaris()
        assert not is_sunos()
        assert not is_windows()
        assert not is_wsl1()
        assert not is_wsl2()
        assert CURRENT_OS_ID == LINUX
        assert CURRENT_OS_LABEL == os_label(LINUX)
    if is_macos():
        assert not is_aix()
        assert not is_cygwin()
        assert not is_freebsd()
        assert not is_hurd()
        assert not is_linux()
        assert not is_netbsd()
        assert not is_openbsd()
        assert not is_solaris()
        assert not is_sunos()
        assert not is_windows()
        assert not is_wsl1()
        assert not is_wsl2()
        assert CURRENT_OS_ID == MACOS
        assert CURRENT_OS_LABEL == os_label(MACOS)
    if is_windows():
        assert not is_aix()
        assert not is_cygwin()
        assert not is_freebsd()
        assert not is_hurd()
        assert not is_linux()
        assert not is_macos()
        assert not is_netbsd()
        assert not is_openbsd()
        assert not is_solaris()
        assert not is_sunos()
        assert not is_wsl1()
        assert not is_wsl2()
        assert CURRENT_OS_ID == WINDOWS
        assert CURRENT_OS_LABEL == os_label(WINDOWS)


def test_unix_family_content():
    for family in ALL_GROUPS:
        assert isinstance(family, frozenset)
        assert len(family) > 0
        assert all(os_id in OS_DEFINITIONS for os_id in family)


def test_unix_family_subsets():
    assert ANY_WINDOWS | ANY_UNIX == ANY_PLATFORM
    assert (
        ANY_BSD
        | ANY_LINUX
        | ANY_LINUX_COMPATIBILITY_LAYER
        | ANY_UNIX_SYSTEM_V
        | ANY_UNIX_COMPATIBILITY_LAYER
        | ANY_OTHER_UNIX
        == ANY_UNIX
    )


def test_family_no_missing():
    """Check all platform are attached to a family."""
    all_platforms = []
    for family in ALL_OS_FAMILIES:
        all_platforms.extend(family)
    assert sorted(all_platforms) == sorted(OS_DEFINITIONS.keys())


def test_family_non_overlap():
    """Check our platform groups are mutually exclusive."""
    for combination in combinations(ALL_OS_FAMILIES, 2):
        assert combination[0].isdisjoint(combination[1])


def test_os_definitions():
    assert isinstance(OS_DEFINITIONS, dict)
    # Each OS definition must be unique.
    assert isinstance(ALL_OS_LABELS, frozenset)
    assert len(OS_DEFINITIONS) == len(ALL_OS_LABELS)
    for os_id, data in OS_DEFINITIONS.items():
        # OS ID.
        assert isinstance(os_id, str)
        assert os_id
        assert os_id.isascii()
        assert os_id.isalnum()
        assert os_id.islower()
        # Metadata.
        assert isinstance(data, tuple)
        assert len(data) == 2
        label, os_flag = data
        # OS label.
        assert label
        assert isinstance(label, str)
        assert label.isascii()
        assert label.isprintable()
        assert label in ALL_OS_LABELS
        # OS identification function.
        assert isinstance(os_flag, bool)
        os_id_func_name = f"is_{os_id}"
        assert os_id_func_name in globals()
        os_id_func = globals()[os_id_func_name]
        assert isinstance(os_id_func, FunctionType)
        assert isinstance(os_id_func(), bool)
        assert os_id_func() == os_flag


def test_current_os_func():
    # Function.
    os_id, label = current_os()
    assert os_id in OS_DEFINITIONS
    assert label in [os[0] for os in OS_DEFINITIONS.values()]
    # Constants.
    assert os_id == CURRENT_OS_ID
    assert label == CURRENT_OS_LABEL


def test_os_label():
    os_id, os_name = current_os()
    assert os_label(os_id) == os_name


# Test unittest decorator helpers.


@skip_linux
def test_skip_linux():
    assert not is_linux()
    assert is_macos() or is_windows()


@skip_macos
def test_skip_macos():
    assert not is_macos()
    assert is_linux() or is_windows()


@skip_windows
def test_skip_windows():
    assert not is_windows()
    assert is_linux() or is_macos()


@unless_linux
def test_unless_linux():
    assert is_linux()
    assert not is_macos()
    assert not is_windows()


@unless_macos
def test_unless_macos():
    assert not is_linux()
    assert is_macos()
    assert not is_windows()


@unless_windows
def test_unless_windows():
    assert not is_linux()
    assert not is_macos()
    assert is_windows()
