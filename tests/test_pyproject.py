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
"""Consistency checks tying the test matrix to the declared dependencies.

The ``click`` version axis of the test matrix is the one dependency whose whole
supported range is exercised release-by-release (a patch can change behavior
mid-stream). These tests keep that axis in sync with the ``click`` dependency
specifier, so a drift, like a new Click release or a raised floor, fails CI
instead of silently rotting.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import requests
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from click_extra.cli import LAZY_SUBCOMMANDS

from .conftest import fetch_or_skip

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"
"""Path to the project's ``pyproject.toml``, relative to this test file."""

SENTINELS = ("released", "stable", "main")
"""Moving-reference values of the ``click-version`` axis: the lockfile-resolved
release, and Click's ``stable`` and ``main`` development branches. Everything
else in the axis is a pinned release number."""

UV_LOCK = PYPROJECT.parent / "uv.lock"
"""Path to the project's ``uv.lock``, which holds the Click ``released`` cells run."""


def load_click_matrix() -> tuple[SpecifierSet, list[str], set[str]]:
    """Read the Click setup from ``pyproject.toml``.

    The ``click-version`` axis is spread across the forward-looking
    ``test-matrix.full-include`` rows (the pinned releases and the ``stable`` /
    ``main`` sentinels) and the ``released`` default declared in
    ``test-matrix.include``.

    :return: the ``click`` dependency specifier, the collected ``click-version``
        axis values, and the subset that are pinned release numbers (sentinels
        start with a letter, pinned versions with a digit).
    """
    config = tomllib.loads(PYPROJECT.read_text(encoding="UTF-8"))
    click = next(
        Requirement(dep)
        for dep in config["project"]["dependencies"]
        if Requirement(dep).name == "click"
    )
    test_matrix = config["tool"]["repomatic"]["test-matrix"]
    versions = {
        row["click-version"]
        for row in test_matrix.get("full-include", ())
        if "click-version" in row
    }
    versions.update(
        directive["click-version"]
        for directive in test_matrix.get("include", ())
        if "click-version" in directive
    )
    pinned = {entry for entry in versions if entry[0].isdigit()}
    return click.specifier, sorted(versions), pinned


def stable_pypi_versions(package: str) -> set[Version]:
    """Return all non-yanked, non-prerelease versions of ``package`` on PyPI."""
    response = fetch_or_skip(f"https://pypi.org/pypi/{package}/json", timeout=30)
    versions = set()
    for release, files in response.json()["releases"].items():
        # Skip releases with no distribution files, or whose files are all yanked.
        if not files or all(f.get("yanked", False) for f in files):
            continue
        version = Version(release)
        if not version.is_prerelease:
            versions.add(version)
    return versions


def locked_versions(package: str) -> set[str]:
    """Return the versions of ``package`` that ``uv.lock`` pins.

    A ``released`` cell installs from the lock with ``uv run --frozen``, so it runs
    this version, not the newest one on PyPI: the cooldown keeps a new release out
    of the lock for a week.
    """
    lock = tomllib.loads(UV_LOCK.read_text(encoding="UTF-8"))
    return {
        str(Version(entry["version"]))
        for entry in lock["package"]
        if entry["name"] == package
    }


@pytest.mark.once
def test_click_floor_is_pinned_and_sentinels_present():
    """The matrix floor stays in sync with the dependency floor (hermetic).

    The lowest pinned ``click-version`` must equal the lower bound of the
    ``click`` specifier, so raising or lowering the dependency floor without
    updating the matrix (or vice versa) fails here. Runs offline, unlike the
    PyPI cross-check below.
    """
    specifier, variations, pinned = load_click_matrix()
    assert pinned, "No Click release pinned in test-matrix.full-include."

    floor = min(
        Version(spec.version)
        for spec in specifier
        if spec.operator in (">=", "==", "~=")
    )
    lowest_pin = min(Version(entry) for entry in pinned)
    assert lowest_pin == floor, (
        f"Lowest pinned Click version ({lowest_pin}) does not match the dependency "
        f"floor (`click{specifier}` => {floor}). Keep the pinned click-version rows "
        "in test-matrix.full-include in sync with the click specifier in [project] "
        "dependencies."
    )

    missing_sentinels = set(SENTINELS) - set(variations)
    assert not missing_sentinels, (
        f"The test matrix dropped the {sorted(missing_sentinels)} click-version "
        "sentinel(s) from test-matrix.full-include / include; the latest release and "
        "Click's dev branches would stop being tested."
    )


@pytest.mark.once
@pytest.mark.network
def test_click_matrix_matches_authorized_releases():
    """The pinned releases match exactly the Click releases the specifier allows.

    Every release allowed by the ``click`` specifier must be referenced in the
    matrix: the locked one through the ``released`` sentinel, every other one by
    an explicit pin. This asserts the set equality in both directions:

    - a **missing** pin means a Click release that no cell runs, like a new
      release that the cooldown still keeps out of ``uv.lock``;
    - a **stale** pin means a pinned version is no longer an authorized release
      (the floor was raised past it, or the release was yanked).

    Either way, the matrix needs an edit, and this is the signal. There is no
    exemption list: a release the suite cannot run on gets its own answer at the
    moment it appears, whether that is a floor bump past it or a hole opened
    here on purpose.
    """
    specifier, variations, pinned = load_click_matrix()

    try:
        available = stable_pypi_versions("click")
    except requests.RequestException as error:
        pytest.skip(f"Cannot reach PyPI to list Click releases: {error}")

    authorized = sorted(v for v in available if specifier.contains(v))
    assert authorized, f"No Click release satisfies {specifier}."
    authorized_strings = {str(v) for v in authorized}

    # The `released` sentinel runs the locked release; every other authorized
    # release must be pinned explicitly.
    covered = locked_versions("click") if "released" in variations else set()
    required = authorized_strings - covered

    missing = required - pinned
    stale = pinned - authorized_strings
    assert not (missing or stale), "\n".join(
        message
        for message in (
            f"No cell runs these Click releases: {sorted(missing, key=Version)}. "
            f"The `released` cells run the {sorted(covered, key=Version)} of uv.lock: "
            "lock the newest release, or pin the others as test-matrix.full-include "
            "rows."
            if missing
            else "",
            f"Drop these stale pins, no longer authorized by `click{specifier}`: "
            f"{sorted(stale, key=Version)}."
            if stale
            else "",
        )
        if message
    )


def test_nuitka_includes_every_lazy_subcommand_module():
    """A Nuitka build bundles the module of each lazily mounted subcommand.

    Nuitka follows `import` statements only, while a lazy subcommand is imported
    from a string: a module missing here ships a binary whose subcommand fails.
    """
    config = tomllib.loads(PYPROJECT.read_text(encoding="UTF-8"))
    included = set(config["tool"]["nuitka"]["include-module"])
    modules = {
        spec.import_path.rpartition(".")[0] for spec in LAZY_SUBCOMMANDS.values()
    }
    assert modules <= included, f"missing from include-module: {modules - included}"
