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

import functools
from itertools import combinations

from .. import platforms as platforms_module
from ..platforms import (
    ALL_GROUPS,
    ALL_LINUX,
    ALL_OS_LABELS,
    ALL_PLATFORMS,
    ALL_WINDOWS,
    BSD,
    BSD_WITHOUT_MACOS,
    CURRENT_OS_ID,
    CURRENT_OS_LABEL,
    EXTRA_GROUPS,
    LINUX,
    LINUX_LAYERS,
    MACOS,
    NON_OVERLAPPING_GROUPS,
    OTHER_UNIX,
    SYSTEM_V,
    UNIX,
    UNIX_LAYERS,
    UNIX_WITHOUT_MACOS,
    WINDOWS,
    Group,
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
    """Only directly tests OSes on which the test suite is running via GitHub
    actions."""
    if is_linux():
        assert CURRENT_OS_ID == LINUX.id
        assert CURRENT_OS_LABEL == os_label(LINUX.id)
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
    if is_macos():
        assert CURRENT_OS_ID == MACOS.id
        assert CURRENT_OS_LABEL == os_label(MACOS.id)
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
    if is_windows():
        assert CURRENT_OS_ID == WINDOWS.id
        assert CURRENT_OS_LABEL == os_label(WINDOWS.id)
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


def test_platform_definitions():
    for plaform in ALL_PLATFORMS.platforms:
        # ID.
        assert plaform.id
        assert plaform.id.isascii()
        assert plaform.id.isalnum()
        assert plaform.id.islower()
        # Name.
        assert plaform.name
        assert plaform.name.isascii()
        assert plaform.name.isprintable()
        assert plaform.name in ALL_OS_LABELS
        # Identification function.
        check_func_id = f"is_{plaform.id}"
        assert check_func_id in globals()
        check_func = globals()[check_func_id]
        assert isinstance(check_func, functools._lru_cache_wrapper)
        assert isinstance(check_func(), bool)
        assert check_func() == plaform.current


def test_unique_ids():
    """Platform and group IDs must be unique."""
    all_platform_ids = [p.id for p in ALL_PLATFORMS]

    # Platforms are expected to be sorted by ID.
    assert sorted(all_platform_ids) == all_platform_ids
    assert len(set(all_platform_ids)) == len(all_platform_ids)

    assert len(all_platform_ids) == len(ALL_PLATFORMS)
    assert len(all_platform_ids) == len(ALL_PLATFORMS.platform_ids)

    all_group_ids = {g.id for g in ALL_GROUPS}
    assert len(all_group_ids) == len(ALL_GROUPS)

    assert all_group_ids.isdisjoint(all_platform_ids)


def test_group_constants():
    """Group constants and IDs must be aligned."""
    for group in ALL_GROUPS:
        group_constant = group.id.upper()
        assert group_constant in platforms_module.__dict__
        assert getattr(platforms_module, group_constant) is group


def test_groups_content():
    for groups in (NON_OVERLAPPING_GROUPS, EXTRA_GROUPS, ALL_GROUPS):
        assert isinstance(groups, frozenset)
        for group in groups:
            assert isinstance(group, Group)

            assert len(group) > 0
            assert len(group.platforms) == len(group.platform_ids)
            assert group.platform_ids.issubset(ALL_PLATFORMS.platform_ids)

            # Check general subset properties.
            assert group.issubset(ALL_PLATFORMS)
            assert ALL_PLATFORMS.issuperset(group)

            # Each group is both a subset and a superset of itself.
            assert group.issubset(group)
            assert group.issuperset(group)
            assert group.issubset(group.platforms)
            assert group.issuperset(group.platforms)

            # Test against empty iterables.
            assert group.issuperset(tuple())
            assert group.issuperset(list())
            assert group.issuperset(dict())
            assert group.issuperset(set())
            assert group.issuperset(frozenset())
            assert not group.issubset(tuple())
            assert not group.issubset(list())
            assert not group.issubset(dict())
            assert not group.issubset(set())
            assert not group.issubset(frozenset())

            for platform in group.platforms:
                assert platform in group
                assert platform in ALL_PLATFORMS
                assert platform.id in group.platform_ids
                assert group.issuperset([platform])
                if len(group) == 1:
                    assert group.issubset([platform])
                else:
                    assert not group.issubset([platform])

            # A group cannot be disjoint from itself.
            assert not group.isdisjoint(group)
            assert not group.isdisjoint(group.platforms)
            assert group.fullyintersects(group)
            assert group.fullyintersects(group.platforms)


def test_logical_grouping():
    """Test logical grouping of platforms."""
    for group in BSD, ALL_LINUX, LINUX_LAYERS, SYSTEM_V, UNIX_LAYERS, OTHER_UNIX:
        assert group.issubset(UNIX)
        assert UNIX.issuperset(group)

    assert UNIX_WITHOUT_MACOS.issubset(UNIX)
    assert UNIX.issuperset(UNIX_WITHOUT_MACOS)

    assert BSD_WITHOUT_MACOS.issubset(UNIX)
    assert BSD_WITHOUT_MACOS.issubset(BSD)
    assert UNIX.issuperset(BSD_WITHOUT_MACOS)
    assert BSD.issuperset(BSD_WITHOUT_MACOS)

    # All platforms are divided into Windows and Unix at the highest level.
    assert {p.id for p in ALL_PLATFORMS} == ALL_WINDOWS.platform_ids | UNIX.platform_ids

    # All UNIX platforms are divided into BSD, Linux, and Unix families.
    assert UNIX.platform_ids == (
        BSD.platform_ids
        | ALL_LINUX.platform_ids
        | LINUX_LAYERS.platform_ids
        | SYSTEM_V.platform_ids
        | UNIX_LAYERS.platform_ids
        | OTHER_UNIX.platform_ids
    )


def test_group_no_missing_platform():
    """Check all platform are attached to at least one group."""
    grouped_platforms = set()
    for group in ALL_GROUPS:
        grouped_platforms |= group.platform_ids
    assert grouped_platforms == ALL_PLATFORMS.platform_ids


def test_non_overlapping_groups():
    """Check non-overlapping groups are mutually exclusive."""
    for combination in combinations(NON_OVERLAPPING_GROUPS, 2):
        group1, group2 = combination
        assert group1.isdisjoint(group2)
        assert group2.isdisjoint(group1)


def test_overlapping_groups():
    """Check all extra groups overlaps with at least one non-overlapping."""
    for extra_group in EXTRA_GROUPS:
        overlap = False
        for group in NON_OVERLAPPING_GROUPS:
            if not extra_group.isdisjoint(group):
                overlap = True
                break
        assert overlap is True


def test_current_os_func():
    # Function.
    current_platform = current_os()
    assert current_platform in ALL_PLATFORMS.platforms
    # Constants.
    assert current_platform.id == CURRENT_OS_ID
    assert current_platform.name == CURRENT_OS_LABEL


def test_os_labels():
    assert len(ALL_OS_LABELS) == len(ALL_PLATFORMS)
    current_platform = current_os()
    assert os_label(current_platform.id) == current_platform.name


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
