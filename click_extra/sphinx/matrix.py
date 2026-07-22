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
"""Release compatibility matrices derived from a project's git history.

Walk every `vX.Y.Z` tag in a project's git repository, extract each release's
declared support for some axis, group consecutive tags that agree, and render a
GitHub-flavored markdown matrix suitable for a project's `install.md`.

Two axes are supported:

- **Python** (``{matrix} python``): per-tag support comes from the
  `Programming Language :: Python :: X.Y` classifier list in
  `pyproject.toml` (the explicit tested grid), falling back in priority order
  to PEP 621 `requires-python`, Poetry `[tool.poetry.dependencies].python`,
  and `setup.py`'s `python_requires`. A floor-only declaration is capped at
  the latest Python released while the range was current, so the `✅` set does
  not over-claim support for Pythons that did not yet exist.
- **A dependency** (``{matrix} <distribution>``, like ``{matrix} click``): the
  per-tag constraint is that distribution's requirement specifier; columns are
  auto-derived from the specifier boundaries plus the `uv.lock` resolved
  version, and each ✅ / ❌ cell is computed with {mod}`packaging`.

The rendered tables back the always-on `matrix` Sphinx directive (see
{class}`MatrixDirective`), so a project's `install.md` can embed a live matrix
kept current by the `click-extra refresh-directives` command instead of a
static table maintained by hand. The generation functions shell out to `git`;
they carry no runtime CLI relevance and are kept out of the `click_extra`
public API.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from docutils import nodes
from docutils.statemachine import StringList
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from sphinx.directives import SphinxDirective, directives
from sphinx.util import logging

from ..table import TableFormat, render_table
from ._base import (
    OPTION_LINE_RE,
    FenceSpan,
    fence_spans,
    marker_res,
    update_blocks,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import ClassVar

    from sphinx.application import Sphinx
    from sphinx.util.typing import OptionSpec


logger = logging.getLogger(__name__)


PYTHON_RELEASE_DATES: dict[str, str] = {
    "2.7": "2010-07-03",
    "3.0": "2008-12-03",
    "3.1": "2009-06-27",
    "3.2": "2011-02-20",
    "3.3": "2012-09-29",
    "3.4": "2014-03-16",
    "3.5": "2015-09-13",
    "3.6": "2016-12-23",
    "3.7": "2018-06-27",
    "3.8": "2019-10-14",
    "3.9": "2020-10-05",
    "3.10": "2021-10-04",
    "3.11": "2022-10-24",
    "3.12": "2023-10-02",
    "3.13": "2024-10-07",
    "3.14": "2025-10-07",
}
"""ISO release date of each `X.Y` Python final release.

Used to cap `✅` cells when a release range's Python support is derived from
a `requires-python`-style floor rather than an explicit classifier list: a
floor without upper bound would otherwise over-claim support for Pythons that
did not yet exist while the range was current. Update this table each October
when a new final release ships.
"""

DEFAULT_TAG_PATTERN: str = r"^v\d+\.\d+\.\d+$"
"""Default regex for release tags (`vMAJOR.MINOR.PATCH`)."""

DEFAULT_TAGS_SORT: str = "version:refname"
"""Default `git tag --sort` argument."""


class PythonMatrixGroup(NamedTuple):
    """A contiguous run of release tags sharing the same Python support set."""

    first_tag: str
    """First tag in the group (in `git tag --sort=version:refname` order)."""

    last_tag: str
    """Last tag in the group."""

    first_date: str
    """ISO `YYYY-MM-DD` date of the first tag's commit."""

    python_versions: tuple[str, ...]
    """The `X.Y` Python versions this range supports, sorted ascending."""


def _version_sort_key(version: str) -> tuple[int, ...]:
    """Numeric sort key for `X.Y` version strings.

    A leading `v` tag namespace is tolerated so the same helper compares both
    bare versions (`3.10`) and release tags (`v3.10.2`).
    """
    return tuple(int(part) for part in version.lstrip("v").split("."))


def python_versions_released_by(
    cutoff_date: str,
    release_dates: dict[str, str] | None = None,
) -> list[str]:
    """Return Python `X.Y` versions released on or before `cutoff_date`.

    :param cutoff_date: ISO `YYYY-MM-DD` date.
    :param release_dates: mapping of `X.Y` → ISO release date. Defaults to
        {data}`PYTHON_RELEASE_DATES`.
    :return: sorted list of `X.Y` strings.
    """
    if release_dates is None:
        release_dates = PYTHON_RELEASE_DATES
    return sorted(
        (v for v, d in release_dates.items() if d <= cutoff_date),
        key=_version_sort_key,
    )


def parse_python_spec(spec: str) -> tuple[str, str, set[str]]:
    """Parse a Python version spec into `(floor, ceiling, excluded)`.

    Supports:

    - PEP 440: `>=3.10`, `>=3.10,<3.14`, `>=2.7, !=3.0.*, !=3.1.*`.
    - Poetry caret: `^3.7` expands to `>=3.7, <4.0`.
    - Poetry tilde: `~3.7` expands to `>=3.7, <3.8`.
    - `setup.py`'s `python_requires` (uses the same PEP 440 syntax as
      `requires-python`).

    :return: `(floor, ceiling, excluded)` where each of `floor` and
        `ceiling` is a bare `"X.Y"` string (empty if unspecified) and
        `excluded` is the set of bare `"X.Y"` values one per `!=X.Y.*`
        clause. The ceiling is *exclusive*: `<3.14` means 3.14 itself is
        not supported. Returns `("", "", set())` when no floor is found.
    """
    spec = spec.strip()
    if not spec:
        return "", "", set()
    # Poetry caret: `^X.Y` → floor X.Y, ceiling (X+1).0 (exclusive).
    m = re.match(r"^\^(\d+)\.(\d+)", spec)
    if m:
        return f"{m.group(1)}.{m.group(2)}", f"{int(m.group(1)) + 1}.0", set()
    # Poetry tilde: `~X.Y` → floor X.Y, ceiling X.(Y+1) (exclusive).
    m = re.match(r"^~(\d+)\.(\d+)", spec)
    if m:
        return (
            f"{m.group(1)}.{m.group(2)}",
            f"{m.group(1)}.{int(m.group(2)) + 1}",
            set(),
        )
    # PEP 440 comma-separated clauses.
    floor = ""
    ceiling = ""
    excluded: set[str] = set()
    for part in spec.split(","):
        part = part.strip()
        m = re.match(r">=?\s*(\d+\.\d+)", part)
        if m:
            floor = m.group(1)
            continue
        m = re.match(r"<\s*(\d+\.\d+)", part)
        if m:
            ceiling = m.group(1)
            continue
        m = re.match(r"!=\s*(\d+\.\d+)(?:\.\*)?", part)
        if m:
            excluded.add(m.group(1))
    return floor, ceiling, excluded


def _git(project_root: Path, *args: str, check: bool = True) -> str:
    """Run a `git` command in `project_root` and return its captured stdout.

    The single place the module shells out to git, so every history read uses
    the same working tree and text decoding. `check` defaults to raising on a
    non-zero exit; the `git show` blob lookups pass `check=False` so a tag
    that lacks the file yields an empty string instead of an error.

    A missing git binary or a non-repository path surfaces as an
    {class}`OSError` / {class}`subprocess.SubprocessError`, which callers let
    propagate: {class}`MatrixDirective` turns it into a build warning, and
    {func}`_regenerate` swallows it to leave a block untouched.
    """
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        encoding="utf-8",
        check=check,
        cwd=project_root,
    ).stdout


def _tag_date(project_root: Path, tag: str) -> str:
    """Return the ISO date of a tag's commit."""
    return _git(project_root, "log", "-1", "--format=%as", tag).strip()


def _walk_tags(
    project_root: Path,
    *,
    tag_pattern: str = DEFAULT_TAG_PATTERN,
    tags_sort: str = DEFAULT_TAGS_SORT,
    version_floor: str = "",
) -> list[tuple[str, str, str, str]]:
    """Return `(tag, iso_date, pyproject, setup_py)` for each release tag.

    Walks `git tag` in `tags_sort` order, keeps the tags matching
    `tag_pattern` and at or above `version_floor`, and fetches each tag's
    `pyproject.toml` and `setup.py` blobs (empty string when absent). Shared
    by the Python and dependency axes so both read history identically.
    """
    tag_re = re.compile(tag_pattern)
    floor_key = _version_sort_key(version_floor) if version_floor else None
    walked: list[tuple[str, str, str, str]] = []
    for tag in _git(project_root, "tag", f"--sort={tags_sort}").split():
        if not tag_re.match(tag):
            continue
        # Drop tags below the package-version floor before any git show / date
        # lookup: no point paying that cost for excluded releases.
        if floor_key is not None and _version_sort_key(tag) < floor_key:
            continue
        pyproject = _git(project_root, "show", f"{tag}:pyproject.toml", check=False)
        setup_py = _git(project_root, "show", f"{tag}:setup.py", check=False)
        walked.append((tag, _tag_date(project_root, tag), pyproject, setup_py))
    return walked


def python_matrix_groups(
    project_root: Path,
    *,
    tag_pattern: str = DEFAULT_TAG_PATTERN,
    tags_sort: str = DEFAULT_TAGS_SORT,
    version_floor: str = "",
    release_dates: dict[str, str] | None = None,
) -> list[PythonMatrixGroup]:
    """Walk every release tag in `project_root` and group consecutive
    releases that declare the same effective set of Python versions.

    :param project_root: git working tree to walk.
    :param tag_pattern: regex matching release tags. Defaults to
        {data}`DEFAULT_TAG_PATTERN` (`vMAJOR.MINOR.PATCH`).
    :param tags_sort: value passed to `git tag --sort`. Defaults to
        {data}`DEFAULT_TAGS_SORT` (`version:refname`).
    :param version_floor: drop every release tag below this bare version
        (`"4.9.0"`, `"4.9"`). Empty (the default) keeps all tags. Applied
        before grouping so the oldest surviving group starts at the floor.
    :param release_dates: Python-version release-date table used for the
        cap. Defaults to {data}`PYTHON_RELEASE_DATES`.
    :return: List of {class}`PythonMatrixGroup`, in chronological order.
        Tags with no Python declaration in any recognized form are skipped.
    """
    if release_dates is None:
        release_dates = PYTHON_RELEASE_DATES
    classifier_re = re.compile(r"Programming Language :: Python :: ([23]\.\d+)")
    reqpy_pep = re.compile(r'requires-python\s*=\s*["\']([^"\']+)["\']')
    reqpy_poetry = re.compile(
        r'\[tool\.poetry\.dependencies\][^\[]*?python\s*=\s*["\']([^"\']+)["\']',
        re.DOTALL,
    )
    reqpy_setup = re.compile(r'python_requires\s*=\s*["\']([^"\']+)["\']')

    # Pass 1: per-tag (tag, iso_date, classifiers, spec).
    tag_data: list[tuple[str, str, tuple[str, ...], str]] = []
    for tag, iso_date, pyproject, setup_py in _walk_tags(
        project_root,
        tag_pattern=tag_pattern,
        tags_sort=tags_sort,
        version_floor=version_floor,
    ):
        classifiers = tuple(
            sorted(set(classifier_re.findall(pyproject)), key=_version_sort_key),
        )
        spec = ""
        for pat, content in (
            (reqpy_pep, pyproject),
            (reqpy_poetry, pyproject),
            (reqpy_setup, setup_py),
        ):
            if not content:
                continue
            m = pat.search(content)
            if m:
                spec = m.group(1)
                break
        if not classifiers and not spec:
            continue
        tag_data.append((tag, iso_date, classifiers, spec))

    if not tag_data:
        return []

    # Pass 2: group consecutive tags with same raw (classifiers, spec).
    # Same-classifier neighbours with different spec strings (a floor bump
    # from `>=3.8` to `>=3.8.6`) get split here and re-merge in Pass 4
    # when their effective versions coincide.
    raw_groups: list[list] = []
    for tag, iso_date, cls, spec in tag_data:
        key = (cls, spec)
        if raw_groups and raw_groups[-1][3] == key:
            raw_groups[-1][1] = tag
        else:
            raw_groups.append([tag, tag, iso_date, key])

    # Pass 3: resolve effective versions per group. Classifiers win when
    # present; otherwise apply the parsed floor / ceiling / excluded with cap.
    today_iso = datetime.now(tz=timezone.utc).date().isoformat()
    resolved: list[tuple[str, str, str, tuple[str, ...]]] = []
    for idx, group in enumerate(raw_groups):
        first_tag, last_tag, first_date, (cls, spec) = group
        if cls:
            versions: tuple[str, ...] = cls
        else:
            floor, ceiling, excluded = parse_python_spec(spec)
            if not floor:
                continue
            end_date = (
                raw_groups[idx + 1][2] if idx + 1 < len(raw_groups) else today_iso
            )
            existing = python_versions_released_by(
                end_date,
                release_dates=release_dates,
            )
            floor_ver_key = _version_sort_key(floor)
            ceiling_key = _version_sort_key(ceiling) if ceiling else None
            versions = tuple(
                v
                for v in existing
                if _version_sort_key(v) >= floor_ver_key
                and v not in excluded
                and (ceiling_key is None or _version_sort_key(v) < ceiling_key)
            )
        if not versions:
            continue
        resolved.append((first_tag, last_tag, first_date, versions))

    # Pass 4: re-merge consecutive resolved groups whose effective versions
    # collapsed to identical sets.
    merged: list[list] = []
    for first_tag, last_tag, first_date, versions in resolved:
        if merged and merged[-1][3] == versions:
            merged[-1][1] = last_tag
        else:
            merged.append([first_tag, last_tag, first_date, versions])

    return [PythonMatrixGroup(f, l, d, v) for f, l, d, v in merged]


def _spans_full_major(
    first_tag: str, last_tag: str, next_first_tag: str | None
) -> bool:
    """Whether a group covers an entire major series (so it labels as `X.x`).

    True when the group stays within one major, starts at that major's `.0`
    minor, and the chronologically newer group has moved on to a higher major
    (or there is none, for the latest group). `next_first_tag` is the first
    tag of that newer group, or `None`. The `.0` start guards against a
    floored partial major (`4.9.x` onward is not `4.x`), and the higher-major
    successor guards against a major that is split across several groups.
    """
    first = first_tag.lstrip("v").split(".")
    last = last_tag.lstrip("v").split(".")
    if first[0] != last[0] or first[1] != "0":
        return False
    if next_first_tag is None:
        return True
    return int(next_first_tag.lstrip("v").split(".")[0]) > int(first[0])


def _range_label(
    first_tag: str,
    last_tag: str,
    *,
    is_latest: bool,
    full_major: bool = False,
) -> str:
    """Render the version-range label for a matrix group.

    A group covering an entire major series collapses to `X.x` (see
    `full_major`). For the most recent multi-major group, the upper bound
    collapses to the major-version wildcard (like `8.x`) so the label is
    stable across new minor releases. A single-release group shows its exact
    `X.Y.Z` version rather than a patch wildcard, so two adjacent patch
    releases never collapse to the same ambiguous label. Other closed groups
    keep precise minor-version bounds.
    """
    if first_tag == last_tag:
        return f"`{first_tag.lstrip('v')}`"
    if full_major:
        return f"`{first_tag.lstrip('v').split('.')[0]}.x`"
    first_minor = ".".join(first_tag.lstrip("v").split(".")[:2])
    last_minor = ".".join(last_tag.lstrip("v").split(".")[:2])
    if first_minor == last_minor:
        return f"`{first_minor}.x`"
    if is_latest:
        last_major = last_tag.lstrip("v").split(".")[0]
        return f"`{first_minor}.x` → `{last_major}.x`"
    return f"`{first_minor}.x` → `{last_minor}.x`"


def python_matrix_table(
    project_root: Path,
    label: str,
    *,
    tag_pattern: str = DEFAULT_TAG_PATTERN,
    tags_sort: str = DEFAULT_TAGS_SORT,
    python_floor: str = "",
    version_floor: str = "",
    release_dates: dict[str, str] | None = None,
) -> str:
    """Render the Python compatibility matrix as a GitHub-flavored markdown table.

    Newest releases sit on top so the supported-version streak progresses
    from the upper-left toward the lower-right corner over time.

    :param project_root: git working tree to walk.
    :param label: the header column name (usually the package name, like
        `"click-extra"` or `"repomatic"`). Rendered in backticks.
    :param tag_pattern: passed to {func}`python_matrix_groups`.
    :param tags_sort: passed to {func}`python_matrix_groups`.
    :param python_floor: drop every Python `X.Y` column below this bare
        version (`"3.9"`). Empty (the default) keeps all columns. Trims
        columns only; combine with `version_floor` to also drop the old
        release rows that supported nothing above the floor.
    :param version_floor: passed to {func}`python_matrix_groups` to drop
        release rows below a bare package version.
    :param release_dates: passed to {func}`python_matrix_groups`.
    :return: rendered markdown table, or the empty string when no group
        was collected.
    """
    groups = python_matrix_groups(
        project_root,
        tag_pattern=tag_pattern,
        tags_sort=tags_sort,
        version_floor=version_floor,
        release_dates=release_dates,
    )
    if not groups:
        return ""

    all_versions = sorted(
        {v for g in groups for v in g.python_versions},
        key=_version_sort_key,
    )
    if python_floor:
        python_floor_key = _version_sort_key(python_floor)
        all_versions = [
            v for v in all_versions if _version_sort_key(v) >= python_floor_key
        ]
    if not all_versions:
        return ""

    rows = []
    ordered = list(reversed(groups))
    for index, group in enumerate(ordered):
        next_first = ordered[index - 1].first_tag if index else None
        cells = ["✅" if v in group.python_versions else "❌" for v in all_versions]
        rows.append(
            [
                _range_label(
                    group.first_tag,
                    group.last_tag,
                    is_latest=index == 0,
                    full_major=_spans_full_major(
                        group.first_tag,
                        group.last_tag,
                        next_first,
                    ),
                ),
                group.first_date,
                *cells,
            ],
        )
    headers = [f"`{label}`", "Released", *(f"`{v}`" for v in all_versions)]
    colalign = ("left", "left", *("center",) * len(all_versions))
    return render_table(
        rows,
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=colalign,
    )


class DependencyMatrixGroup(NamedTuple):
    """A contiguous run of release tags declaring the same dependency spec."""

    first_tag: str
    """First tag in the group (in `git tag --sort=version:refname` order)."""

    last_tag: str
    """Last tag in the group."""

    first_date: str
    """ISO `YYYY-MM-DD` date of the first tag's commit."""

    spec: str
    """The raw requirement specifier declared for the dependency at this range."""


def _safe_version(text: str) -> Version | None:
    """Parse `text` into a {class}`~packaging.version.Version`, or `None`."""
    try:
        return Version(text)
    except InvalidVersion:
        return None


def _extract_requirement(pyproject: str, setup_py: str, dep_name: str) -> str:
    """Return the version specifier declared for `dep_name`, or `""`.

    Reads a PEP 621 / `setup.py` requirement string (`click>=8.3.1`,
    `click (>=8.3.1)`) first, then a Poetry `[tool.poetry.dependencies]`
    entry (`click = "^8.1"`).
    """
    name = re.escape(dep_name)
    for content in (pyproject, setup_py):
        m = re.search(rf'["\']{name}\s*\(?\s*([<>=~^!][^"\')]+)', content)
        if m:
            return m.group(1).strip()
    m = re.search(
        rf'\[tool\.poetry\.dependencies\][^\[]*?\b{name}\s*=\s*["\']([^"\']+)["\']',
        pyproject,
        re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def _to_specifier_set(spec: str) -> SpecifierSet | None:
    """Convert a specifier (PEP 440 or Poetry caret/tilde) to a `SpecifierSet`.

    Poetry `^X.Y` expands to `>=X.Y,<(X+1).0.0` and `~X.Y` to
    `>=X.Y,<X.(Y+1).0`. PEP 440 specifiers (`>=`, `~=`, `==`, commas)
    pass through. Returns `None` for an unparsable specifier.
    """
    spec = spec.strip()
    caret = re.match(r"^\^\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?$", spec)
    if caret:
        major = int(caret.group(1))
        floor = ".".join(p for p in caret.groups() if p is not None)
        spec = f">={floor},<{major + 1}.0.0"
    tilde = re.match(r"^~\s*(\d+)\.(\d+)(?:\.(\d+))?$", spec)
    if tilde:
        major, minor = int(tilde.group(1)), int(tilde.group(2))
        floor = ".".join(p for p in tilde.groups() if p is not None)
        spec = f">={floor},<{major}.{minor + 1}.0"
    try:
        return SpecifierSet(spec.replace(" ", ""))
    except InvalidSpecifier:
        return None


def _spec_floor_open(spec: str) -> tuple[Version | None, bool]:
    """Return `(floor_version, is_open)` for a specifier.

    `is_open` is `True` for an unbounded-above floor (`>=` / `>`) and
    `False` for a capped range (`~=`, Poetry `^` / `~`, or any `<`).
    The floor drives column placement; openness drives whether a minor series
    is split into patch columns.
    """
    spec = spec.strip()
    m = re.match(r"^[\^~]\s*(\d+(?:\.\d+){0,2})", spec)
    if m:
        return _safe_version(m.group(1)), False
    m = re.match(r"^~=\s*(\d+(?:\.\d+){1,2})", spec)
    if m:
        return _safe_version(m.group(1)), False
    m = re.search(r">=?\s*(\d+(?:\.\d+){0,2})", spec)
    floor = _safe_version(m.group(1)) if m else None
    is_open = "<" not in spec and not spec.startswith("==")
    return floor, is_open


def _latest_locked_version(project_root: Path, dep_name: str) -> str:
    """Return `dep_name`'s resolved version from `uv.lock`, or `""`.

    Offline: reads the lockfile in the working tree (not per tag), only to
    anchor the right-most column at the version the project resolves today.
    """
    try:
        text = (project_root / "uv.lock").read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(rf'name = "{re.escape(dep_name)}"\nversion = "([^"]+)"', text)
    return m.group(1) if m else ""


def _minor_intersects(spec_set: SpecifierSet, major: int, minor: int) -> bool:
    """Does `spec_set` allow any release in the `major.minor` series?"""
    low = Version(f"{major}.{minor}.0")
    high = Version(f"{major}.{minor}.99999")
    return spec_set.contains(low, prereleases=True) or spec_set.contains(
        high,
        prereleases=True,
    )


def _dependency_columns(specs: list[str], latest: str) -> list[tuple[Version, bool]]:
    """Derive the ordered `(version, is_minor)` columns for a dependency axis.

    A minor series gets a single `X.Y` column unless an open (`>=`) spec
    pins a patch-level floor within it, in which case it is split into `X.Y.0`
    plus each such floor. The `latest` locked version anchors the right edge.
    """
    floors = [
        (floor, is_open)
        for floor, is_open in (_spec_floor_open(spec) for spec in specs)
        if floor is not None
    ]
    latest_version = _safe_version(latest) if latest else None

    split: dict[tuple[int, int], bool] = {}
    for floor, is_open in floors:
        key = (floor.major, floor.minor)
        split.setdefault(key, False)
        if is_open and floor.micro > 0:
            split[key] = True
    if latest_version is not None:
        split.setdefault((latest_version.major, latest_version.minor), False)

    columns: list[tuple[Version, bool]] = []
    for key in sorted(split):
        major, minor = key
        if not split[key]:
            columns.append((Version(f"{major}.{minor}"), True))
            continue
        patches = {Version(f"{major}.{minor}.0")}
        patches.update(
            floor
            for floor, is_open in floors
            if is_open and (floor.major, floor.minor) == key
        )
        if (
            latest_version is not None
            and (latest_version.major, latest_version.minor) == key
        ):
            patches.add(latest_version)
        columns.extend((patch, False) for patch in sorted(patches))
    return columns


def dependency_matrix_groups(
    project_root: Path,
    dep_name: str,
    *,
    tag_pattern: str = DEFAULT_TAG_PATTERN,
    tags_sort: str = DEFAULT_TAGS_SORT,
    version_floor: str = "",
) -> list[DependencyMatrixGroup]:
    """Group consecutive release tags declaring the same `dep_name` spec.

    :param dep_name: the distribution whose requirement specifier is tracked
        (like `"click"`).
    :return: {class}`DependencyMatrixGroup` list in chronological order; tags
        with no declared requirement for `dep_name` are skipped.
    """
    groups: list[DependencyMatrixGroup] = []
    for tag, iso_date, pyproject, setup_py in _walk_tags(
        project_root,
        tag_pattern=tag_pattern,
        tags_sort=tags_sort,
        version_floor=version_floor,
    ):
        spec = _extract_requirement(pyproject, setup_py, dep_name)
        if not spec:
            continue
        if groups and groups[-1].spec == spec:
            groups[-1] = groups[-1]._replace(last_tag=tag)
        else:
            groups.append(DependencyMatrixGroup(tag, tag, iso_date, spec))
    return groups


def dependency_matrix_table(
    project_root: Path,
    label: str,
    dep_name: str,
    *,
    show_spec: bool = False,
    tag_pattern: str = DEFAULT_TAG_PATTERN,
    tags_sort: str = DEFAULT_TAGS_SORT,
    version_floor: str = "",
) -> str:
    """Render the `dep_name` compatibility matrix as a markdown table.

    Columns are auto-derived from the requirement specifiers across history
    (see {func}`_dependency_columns`) plus the `uv.lock` resolved version;
    each ✅ / ❌ cell is computed with {mod}`packaging`. Consecutive ranges
    whose cells coincide are re-merged into one row.

    :param label: header column name (the documented package, in backticks).
    :param dep_name: the tracked distribution (`"click"`).
    :param show_spec: add a `Spec` column with each range's raw specifier.
    :return: rendered markdown table, or `""` when nothing was collected.
    """
    groups = dependency_matrix_groups(
        project_root,
        dep_name,
        tag_pattern=tag_pattern,
        tags_sort=tags_sort,
        version_floor=version_floor,
    )
    if not groups:
        return ""
    columns = _dependency_columns(
        [g.spec for g in groups],
        _latest_locked_version(project_root, dep_name),
    )
    if not columns:
        return ""

    # Resolve each range's ✅ / ❌ vector, then re-merge consecutive ranges
    # whose vectors coincide (a floor bump that changes no visible cell).
    merged: list[list] = []
    for group in groups:
        spec_set = _to_specifier_set(group.spec)
        cells = tuple(
            "✅"
            if spec_set is not None
            and (
                _minor_intersects(spec_set, version.major, version.minor)
                if is_minor
                else spec_set.contains(version, prereleases=True)
            )
            else "❌"
            for version, is_minor in columns
        )
        if merged and merged[-1][4] == cells:
            merged[-1][1] = group.last_tag
        else:
            merged.append(
                [group.first_tag, group.last_tag, group.first_date, group.spec, cells],
            )

    rows = []
    ordered = list(reversed(merged))
    for index, (first_tag, last_tag, first_date, spec, cells) in enumerate(ordered):
        next_first = ordered[index - 1][0] if index else None
        label_cell = _range_label(
            first_tag,
            last_tag,
            is_latest=index == 0,
            full_major=_spans_full_major(first_tag, last_tag, next_first),
        )
        spec_cell = [f"`{spec.replace(' ', '')}`"] if show_spec else []
        rows.append([label_cell, first_date, *spec_cell, *cells])
    spec_header = ["Spec"] if show_spec else []
    headers = [f"`{label}`", "Released", *spec_header, *(f"`{v}`" for v, _ in columns)]
    colalign = (
        "left",
        "left",
        *(("left",) if show_spec else ()),
        *("center",) * len(columns),
    )
    return render_table(
        rows,
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=colalign,
    )


def _find_git_root(start: Path) -> Path:
    """Walk up from `start` to the first directory holding a `.git` entry.

    Falls back to `start` when none is found; the caller then gets an empty
    matrix (no tags) rather than an exception.
    """
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def _resolve_root(path_opt: str | None, base_dir: Path) -> Path:
    """Resolve the git working tree to walk from a `:path:` option value.

    `base_dir` anchors both the git-root search and any relative
    `path_opt`: the docs source directory for the live directive, the
    Markdown file's parent for the offline updater. An absolute `path_opt`
    is used verbatim.
    """
    # Resolve to an absolute path so a relative `base_dir` (like the `docs`
    # the CLI passes) yields a git root whose `.name` is the real repo folder,
    # not an empty string from `Path(".")`.
    git_root = _find_git_root(base_dir.resolve())
    if not path_opt:
        return git_root
    candidate = Path(path_opt)
    if not candidate.is_absolute():
        candidate = git_root / candidate
    return candidate.resolve()


def _render_block(axis: str, options: Mapping[str, str], base_dir: Path) -> str:
    """Render the table for a ``{matrix} <axis>`` block.

    Dispatches on `axis`: `"python"` renders the interpreter matrix; any
    other value names a distribution and renders its dependency matrix. Shared
    by {class}`MatrixDirective` (live rendering) and {func}`update_matrix_blocks`
    (offline source refresh) so both resolve the package, path, and floors
    identically.
    """
    root = _resolve_root(options.get("path"), base_dir)
    package = options.get("package") or root.name
    tag_pattern = options.get("tag-pattern") or DEFAULT_TAG_PATTERN
    version_floor = options.get("version-floor", "")
    if axis == "python":
        return python_matrix_table(
            root,
            package,
            python_floor=options.get("python-floor", ""),
            version_floor=version_floor,
            tag_pattern=tag_pattern,
        )
    return dependency_matrix_table(
        root,
        package,
        axis,
        show_spec="show-spec" in options,
        version_floor=version_floor,
        tag_pattern=tag_pattern,
    )


class MatrixDirective(SphinxDirective):
    """Render a package's compatibility matrix for a given axis.

    ``{matrix} python`` renders the interpreter matrix (release ranges × Python
    versions). ``{matrix} <distribution>`` (like ``{matrix} click``) renders a
    dependency matrix (release ranges × that dependency's versions, from its
    requirement specifier across the git history). Both emit a GitHub-flavored
    table parsed by the host document's parser, so it lands as a real
    `<table>`.

    The table normally lives *inside* the block as its content, kept current by
    the offline updater ({func}`update_matrix_blocks`, exposed as the
    `click-extra refresh-directives` command). Rendering that embedded copy
    needs no git access at build time, so shallow clones and read-only build
    hosts still show the matrix. An empty block falls back to generating from
    the working tree's git tags, so a freshly authored block renders before its
    first refresh.

    Argument: the axis, `python` or a distribution name.

    Options:

    - `:package:` — header column label. Defaults to the repository name.
    - `:path:` — git working tree to walk, absolute or relative to the
      documented project's git root. Defaults to that git root.
    - `:version-floor:` — drop release rows below this package version.
    - `:tag-pattern:` — regex selecting release tags. Defaults to
      {data}`DEFAULT_TAG_PATTERN`.
    - `:python-floor:` — (python axis) drop Python columns below `X.Y`.
    - `:show-spec:` — (dependency axis) add a raw-specifier `Spec` column.

    The git fallback is resilient: a missing git binary, a non-repository path,
    or a tag-less repository logs a build warning and renders nothing rather
    than aborting the build.
    """

    has_content = True
    required_arguments = 1
    optional_arguments = 0
    option_spec: ClassVar[OptionSpec] = {
        "package": directives.unchanged,
        "path": directives.unchanged,
        "python-floor": directives.unchanged,
        "version-floor": directives.unchanged,
        "tag-pattern": directives.unchanged,
        "show-spec": directives.flag,
    }

    def run(self) -> list[nodes.Node]:
        axis = self.arguments[0].strip()
        # Prefer the embedded table (kept fresh by update_matrix_blocks): it
        # renders without touching git, so the build works on shallow clones.
        if self.content:
            table_lines = list(self.content)
        else:
            # Empty block: generate from the git tags as a first-render
            # fallback until the updater populates the source.
            try:
                table = _render_block(axis, self.options, Path(self.env.srcdir))
            except (OSError, subprocess.SubprocessError) as error:
                logger.warning(
                    "click_extra.sphinx: matrix %s could not read git tags: %s",
                    axis,
                    error,
                    location=self.get_location(),
                )
                return []
            if not table:
                logger.warning(
                    "click_extra.sphinx: matrix %s found no release data and "
                    "the block embeds no table",
                    axis,
                    location=self.get_location(),
                )
                return []
            table_lines = table.splitlines()

        # Parse the table with the host document's parser (MyST inside .md,
        # reST inside .rst) so it lands as a real table node rather than a
        # literal code block.
        container = nodes.section()
        source_file, _ = self.get_source_info()
        self.state.nested_parse(
            StringList(table_lines, source_file),
            self.content_offset,
            container,
        )
        return container.children


def setup(app: Sphinx) -> None:
    """Register the always-on `matrix` directive on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. Unlike the `click:*` /
    `python:*` families, the directive is registered unconditionally: it runs
    a canned matrix generator, not user-supplied Python, so it needs no opt-in.
    """
    app.add_directive("matrix", MatrixDirective)


_FENCE_OPEN_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<fence>`{3,})\{matrix\}[ \t]+(?P<axis>\S+)[ \t]*$",
)
"""Opening fence of a ``{matrix} <axis>`` directive block in a Markdown source."""

# `<!-- matrix <axis> [opts] -->` … `<!-- matrix-end -->` region markers, in the
# shared grammar from `_base.marker_res`. Unlike the directive fence (which
# GitHub shows as a code block), this marker form renders as a real table on
# GitHub and natively in Sphinx. Args are the axis followed by
# whitespace-separated `key=value` pairs and bare flags (like `show-spec`).
_MARKER_OPEN_RE, _MARKER_CLOSE_RE = marker_res("matrix")


def _parse_marker_options(tokens: Iterable[str]) -> dict[str, str]:
    """Parse a marker's `key=value` / bare-flag option tokens into a mapping."""
    options: dict[str, str] = {}
    for token in tokens:
        key, _, value = token.partition("=")
        options[key] = value
    return options


def _regenerate(axis: str, options: Mapping[str, str], base_dir: Path) -> str:
    """Render a block, returning `""` on any git/OS failure (non-destructive)."""
    try:
        return _render_block(axis, options, base_dir)
    except (OSError, subprocess.SubprocessError):
        return ""


def _refresh_fence_block(
    match: re.Match[str],
    lines: list[str],
    index: int,
    close: int,
    base_dir: Path,
) -> list[str]:
    """Regenerate one ``{matrix} <axis>`` directive fence closing at `close`.

    Returns the replacement lines. Keeps the block verbatim when generation
    fails.
    """
    indent = match.group("indent")
    fence = match.group("fence")
    axis = match.group("axis")

    options: dict[str, str] = {}
    for cursor in range(index + 1, close):
        option_match = OPTION_LINE_RE.match(lines[cursor])
        if not option_match:
            break
        options[option_match.group("key")] = option_match.group("value")

    table = _regenerate(axis, options, base_dir)
    if not table:
        return lines[index : close + 1]

    out = [f"{indent}{fence}{{matrix}} {axis}"]
    for key, value in options.items():
        out.append(f"{indent}:{key}: {value}" if value else f"{indent}:{key}:")
    out.append("")
    out.extend(f"{indent}{row}" if row else row for row in table.splitlines())
    out.append(f"{indent}{fence}")
    return out


def _refresh_marker_region(
    match: re.Match[str],
    lines: list[str],
    index: int,
    spans: Mapping[int, FenceSpan],
    base_dir: Path,
) -> tuple[list[str], int]:
    """Regenerate one `<!-- matrix <axis> -->` region starting at `index`.

    The start marker is kept verbatim; the raw table between the markers is
    replaced, blank-line padded so `mdformat` does not ping-pong on the
    surrounding HTML comments. The closing-marker search skips fence spans, so
    a `<!-- matrix-end -->` shown inside a code example cannot close a live
    region. Kept verbatim when unterminated, axis-less, or on failure.
    """
    indent = match.group("indent")
    tokens = (match.group("args") or "").split()
    if not tokens:
        return [lines[index]], index + 1
    axis = tokens[0]
    options = _parse_marker_options(tokens[1:])

    close = None
    probe = index + 1
    while probe < len(lines):
        span = spans.get(probe)
        if span is not None:
            if span.close is None:
                break
            probe = span.close + 1
            continue
        close_match = _MARKER_CLOSE_RE.match(lines[probe])
        if close_match and close_match.group("indent") == indent:
            close = probe
            break
        probe += 1
    if close is None:
        return [lines[index]], index + 1

    table = _regenerate(axis, options, base_dir)
    if not table:
        return lines[index : close + 1], close + 1

    out = [lines[index], ""]
    out.extend(f"{indent}{row}" if row else row for row in table.splitlines())
    out.extend(["", f"{indent}<!-- matrix-end -->"])
    return out, close + 1


def _rewrite_matrix_blocks(text: str, base_dir: Path) -> str:
    """Return `text` with every `matrix` block's table regenerated.

    Handles both forms: the ``{matrix} <axis>`` directive fence (rendered by
    Sphinx) and the `<!-- matrix <axis> -->` comment region (which renders as a
    real table on GitHub too). Each keeps its axis and options; only the embedded
    table is replaced. The walk is fence-aware: a ``{matrix}`` example nested
    inside a longer code fence is a documented illustration, copied verbatim and
    never refreshed. A block whose generation fails (non-repository path,
    missing git, no data) is left byte-for-byte untouched.
    """
    lines = text.splitlines()
    spans = fence_spans(lines)
    out: list[str] = []
    index = 0
    total = len(lines)
    while index < total:
        span = spans.get(index)
        if span is not None:
            if span.close is None:
                # Unterminated fence: leave the tail untouched.
                out.extend(lines[index:])
                break
            fence_match = _FENCE_OPEN_RE.match(lines[index])
            if fence_match:
                out.extend(
                    _refresh_fence_block(
                        fence_match, lines, index, span.close, base_dir
                    )
                )
            else:
                out.extend(lines[index : span.close + 1])
            index = span.close + 1
            continue
        marker_match = _MARKER_OPEN_RE.match(lines[index])
        if marker_match:
            chunk, index = _refresh_marker_region(
                marker_match, lines, index, spans, base_dir
            )
            out.extend(chunk)
            continue
        out.append(lines[index])
        index += 1

    result = "\n".join(out)
    if text.endswith("\n"):
        result += "\n"
    return result


def update_matrix_blocks(paths: Iterable[Path], *, check: bool = False) -> list[Path]:
    """Refresh every ``{matrix}`` block in the given Markdown sources.

    See {func}`click_extra.sphinx._base.update_blocks` for the walk, write, and
    `check`-mode contract.

    :return: the files whose ``{matrix}`` blocks were (or, under `check`,
        would be) updated.
    """
    return update_blocks(
        paths,
        lambda text, path: _rewrite_matrix_blocks(text, base_dir=path.parent),
        check=check,
    )
