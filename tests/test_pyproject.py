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
"""Consistency checks on ``pyproject.toml`` metadata."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests
from packaging.requirements import Requirement
from packaging.version import Version

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"
"""Path to the project's ``pyproject.toml``, relative to this test file."""


def stable_pypi_versions(package: str) -> set[Version]:
    """Return all non-yanked, non-prerelease versions of ``package`` on PyPI."""
    response = requests.get(f"https://pypi.org/pypi/{package}/json", timeout=30)
    response.raise_for_status()
    versions = set()
    for release, files in response.json()["releases"].items():
        # Skip releases with no distribution files, or whose files are all yanked.
        if not files or all(f.get("yanked", False) for f in files):
            continue
        version = Version(release)
        if not version.is_prerelease:
            versions.add(version)
    return versions


@pytest.mark.once
def test_click_matrix_covers_authorized_releases():
    """Every Click release allowed by our dependency specifier is exercised by the
    test matrix.

    Click is the one dependency whose whole supported range is tested
    release-by-release (a patch can change behavior mid-stream), so each
    authorized release must be referenced in
    ``[tool.repomatic] test-matrix.variations.click-version``. The newest
    release is covered by the ``released`` sentinel; every earlier one must be
    pinned by version.

    When Click publishes a new release, the previous newest becomes an
    intermediate version that is no longer covered by ``released``, so this test
    fails: the signal that the matrix needs a new pinned entry.
    """
    config = tomllib.loads(PYPROJECT.read_text(encoding="UTF-8"))

    # The Click specifier declared in the runtime dependencies.
    click = next(
        Requirement(dep)
        for dep in config["project"]["dependencies"]
        if Requirement(dep).name == "click"
    )

    # The Click versions referenced in the test matrix. Sentinels (released,
    # stable, main) start with a letter; pinned releases start with a digit.
    variations = config["tool"]["repomatic"]["test-matrix"]["variations"][
        "click-version"
    ]
    pinned = {entry for entry in variations if entry[0].isdigit()}

    try:
        available = stable_pypi_versions("click")
    except requests.RequestException as error:
        pytest.skip(f"Cannot reach PyPI to list Click releases: {error}")

    authorized = sorted(v for v in available if click.specifier.contains(v))
    assert authorized, f"No Click release satisfies {click.specifier}."

    # The newest authorized release is exercised through the `released` sentinel;
    # every older release must be pinned explicitly.
    sentinel_covered = {authorized[-1]} if "released" in variations else set()
    required = {str(v) for v in authorized} - {str(v) for v in sentinel_covered}

    missing = required - pinned
    assert not missing, (
        f"Click releases allowed by `click{click.specifier}` but missing from "
        f"test-matrix.variations.click-version: {sorted(missing, key=Version)}. "
        "Add them so the whole supported range stays tested, and re-check which "
        "release the `released` sentinel now covers."
    )
