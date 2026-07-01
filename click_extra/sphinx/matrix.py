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
"""Python version compatibility matrix derived from a project's git history.

Walk every ``vX.Y.Z`` tag in a project's git repository, extract the declared
Python version support, group consecutive tags that agree, and render a
GitHub-flavored markdown matrix suitable for a project's ``install.md``.

The primary source per tag is the ``Programming Language :: Python :: X.Y``
classifier list in ``pyproject.toml`` (the explicit tested grid). Tags with no
classifiers fall back in priority order to PEP 621 ``requires-python``, Poetry
``[tool.poetry.dependencies].python``, and ``setup.py``'s ``python_requires``.
A floor-only declaration is capped at the latest Python released on or before
the range's end date (the next group's first-tag date, or ``date.today()`` for
the open-ended latest range) so the ``✅`` set does not over-claim support for
Pythons that did not yet exist while the range was current.

The rendered table backs the always-on ``matrix:python`` Sphinx directive (see
:class:`MatrixPythonDirective`), so a project's ``install.md`` can embed a live,
build-time matrix instead of a static table kept in sync by a regenerator
script. The generation functions shell out to ``git`` at build time; they carry
no runtime CLI relevance and are intentionally kept out of the ``click_extra``
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
from sphinx.directives import SphinxDirective, directives
from sphinx.util import logging

from ..table import TableFormat, render_table
from ._base import StatelessDomain

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
"""ISO release date of each ``X.Y`` Python final release.

Used to cap ``✅`` cells when a release range's Python support is derived from
a ``requires-python``-style floor rather than an explicit classifier list: a
floor without upper bound would otherwise over-claim support for Pythons that
did not yet exist while the range was current. Update this table each October
when a new final release ships.
"""

DEFAULT_TAG_PATTERN: str = r"^v\d+\.\d+\.\d+$"
"""Default regex for release tags (``vMAJOR.MINOR.PATCH``)."""

DEFAULT_TAGS_SORT: str = "version:refname"
"""Default ``git tag --sort`` argument."""


class PythonMatrixGroup(NamedTuple):
    """A contiguous run of release tags sharing the same Python support set."""

    first_tag: str
    """First tag in the group (in ``git tag --sort=version:refname`` order)."""

    last_tag: str
    """Last tag in the group."""

    first_date: str
    """ISO ``YYYY-MM-DD`` date of the first tag's commit."""

    python_versions: tuple[str, ...]
    """The ``X.Y`` Python versions this range supports, sorted ascending."""


def _version_sort_key(version: str) -> tuple[int, ...]:
    """Numeric sort key for ``X.Y`` version strings.

    A leading ``v`` tag namespace is tolerated so the same helper compares both
    bare versions (``3.10``) and release tags (``v3.10.2``).
    """
    return tuple(int(part) for part in version.lstrip("v").split("."))


def python_versions_released_by(
    cutoff_date: str,
    release_dates: dict[str, str] | None = None,
) -> list[str]:
    """Return Python ``X.Y`` versions released on or before ``cutoff_date``.

    :param cutoff_date: ISO ``YYYY-MM-DD`` date.
    :param release_dates: mapping of ``X.Y`` → ISO release date. Defaults to
        :data:`PYTHON_RELEASE_DATES`.
    :return: sorted list of ``X.Y`` strings.
    """
    if release_dates is None:
        release_dates = PYTHON_RELEASE_DATES
    return sorted(
        (v for v, d in release_dates.items() if d <= cutoff_date),
        key=_version_sort_key,
    )


def parse_python_spec(spec: str) -> tuple[str, str, set[str]]:
    """Parse a Python version spec into ``(floor, ceiling, excluded)``.

    Supports:

    - PEP 440: ``>=3.10``, ``>=3.10,<3.14``, ``>=2.7, !=3.0.*, !=3.1.*``.
    - Poetry caret: ``^3.7`` expands to ``>=3.7, <4.0``.
    - Poetry tilde: ``~3.7`` expands to ``>=3.7, <3.8``.
    - ``setup.py``'s ``python_requires`` (uses the same PEP 440 syntax as
      ``requires-python``).

    :return: ``(floor, ceiling, excluded)`` where each of ``floor`` and
        ``ceiling`` is a bare ``"X.Y"`` string (empty if unspecified) and
        ``excluded`` is the set of bare ``"X.Y"`` values one per ``!=X.Y.*``
        clause. The ceiling is *exclusive*: ``<3.14`` means 3.14 itself is
        not supported. Returns ``("", "", set())`` when no floor is found.
    """
    spec = spec.strip()
    if not spec:
        return "", "", set()
    # Poetry caret: ``^X.Y`` → floor X.Y, ceiling (X+1).0 (exclusive).
    m = re.match(r"^\^(\d+)\.(\d+)", spec)
    if m:
        return f"{m.group(1)}.{m.group(2)}", f"{int(m.group(1)) + 1}.0", set()
    # Poetry tilde: ``~X.Y`` → floor X.Y, ceiling X.(Y+1) (exclusive).
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


def _tag_date(project_root: Path, tag: str) -> str:
    """Return the ISO date of a tag's commit."""
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%as", tag],
        capture_output=True,
        encoding="utf-8",
        check=True,
        cwd=project_root,
    )
    return proc.stdout.strip()


def python_matrix_groups(
    project_root: Path,
    *,
    tag_pattern: str = DEFAULT_TAG_PATTERN,
    tags_sort: str = DEFAULT_TAGS_SORT,
    version_floor: str = "",
    release_dates: dict[str, str] | None = None,
) -> list[PythonMatrixGroup]:
    """Walk every release tag in ``project_root`` and group consecutive
    releases that declare the same effective set of Python versions.

    :param project_root: git working tree to walk.
    :param tag_pattern: regex matching release tags. Defaults to
        :data:`DEFAULT_TAG_PATTERN` (``vMAJOR.MINOR.PATCH``).
    :param tags_sort: value passed to ``git tag --sort``. Defaults to
        :data:`DEFAULT_TAGS_SORT` (``version:refname``).
    :param version_floor: drop every release tag below this bare version
        (``"4.9.0"``, ``"4.9"``). Empty (the default) keeps all tags. Applied
        before grouping so the oldest surviving group starts at the floor.
    :param release_dates: Python-version release-date table used for the
        cap. Defaults to :data:`PYTHON_RELEASE_DATES`.
    :return: List of :class:`PythonMatrixGroup`, in chronological order.
        Tags with no Python declaration in any recognized form are skipped.
    """
    if release_dates is None:
        release_dates = PYTHON_RELEASE_DATES
    tag_re = re.compile(tag_pattern)
    classifier_re = re.compile(r"Programming Language :: Python :: ([23]\.\d+)")
    reqpy_pep = re.compile(r'requires-python\s*=\s*["\']([^"\']+)["\']')
    reqpy_poetry = re.compile(
        r'\[tool\.poetry\.dependencies\][^\[]*?python\s*=\s*["\']([^"\']+)["\']',
        re.DOTALL,
    )
    reqpy_setup = re.compile(r'python_requires\s*=\s*["\']([^"\']+)["\']')

    proc = subprocess.run(
        ["git", "tag", f"--sort={tags_sort}"],
        capture_output=True,
        encoding="utf-8",
        check=True,
        cwd=project_root,
    )

    # Pass 1: per-tag (tag, iso_date, classifiers, spec).
    tag_data: list[tuple[str, str, tuple[str, ...], str]] = []
    floor_key = _version_sort_key(version_floor) if version_floor else None
    for tag in proc.stdout.split():
        if not tag_re.match(tag):
            continue
        # Drop tags below the requested package-version floor before any git
        # show / date lookup: no point paying that cost for excluded releases.
        if floor_key is not None and _version_sort_key(tag) < floor_key:
            continue
        pyproject = subprocess.run(
            ["git", "show", f"{tag}:pyproject.toml"],
            capture_output=True,
            encoding="utf-8",
            check=False,
            cwd=project_root,
        ).stdout
        setup_py = subprocess.run(
            ["git", "show", f"{tag}:setup.py"],
            capture_output=True,
            encoding="utf-8",
            check=False,
            cwd=project_root,
        ).stdout
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
        tag_data.append((tag, _tag_date(project_root, tag), classifiers, spec))

    if not tag_data:
        return []

    # Pass 2: group consecutive tags with same raw (classifiers, spec).
    # Same-classifier neighbours with different spec strings (a floor bump
    # from ``>=3.8`` to ``>=3.8.6``) get split here and re-merge in Pass 4
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


def _range_label(first_tag: str, last_tag: str, *, is_latest: bool) -> str:
    """Render the version-range label for a matrix group.

    For the most recent (open-ended) group, collapse the upper bound to the
    major-version wildcard (like ``6.x``) so the label is stable across new
    minor releases that share the same Python compatibility. Closed
    historical groups keep the precise minor-version bounds.
    """
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
        ``"click-extra"`` or ``"repomatic"``). Rendered in backticks.
    :param tag_pattern: passed to :func:`python_matrix_groups`.
    :param tags_sort: passed to :func:`python_matrix_groups`.
    :param python_floor: drop every Python ``X.Y`` column below this bare
        version (``"3.9"``). Empty (the default) keeps all columns. Trims
        columns only; combine with ``version_floor`` to also drop the old
        release rows that supported nothing above the floor.
    :param version_floor: passed to :func:`python_matrix_groups` to drop
        release rows below a bare package version.
    :param release_dates: passed to :func:`python_matrix_groups`.
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
    for index, group in enumerate(reversed(groups)):
        cells = ["✅" if v in group.python_versions else "❌" for v in all_versions]
        rows.append(
            [
                _range_label(
                    group.first_tag,
                    group.last_tag,
                    is_latest=index == 0,
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


MATRIX_DOMAIN = "matrix"
"""Name of the Sphinx domain grouping the compatibility-matrix directives.

Distinct from the ``click:*`` and ``python:*`` families: those execute
user-supplied Python at build time and are gated behind
``click_extra_enable_exec_directives``. The ``matrix:*`` directives run a
fixed, canned matrix generator against the documented project's own git
history, so they are always-on and carry no arbitrary-code-execution surface.
"""


def _find_git_root(start: Path) -> Path:
    """Walk up from ``start`` to the first directory holding a ``.git`` entry.

    Falls back to ``start`` when none is found; the caller then gets an empty
    matrix (no tags) rather than an exception.
    """
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def _resolve_root(path_opt: str | None, base_dir: Path) -> Path:
    """Resolve the git working tree to walk from a ``:path:`` option value.

    ``base_dir`` anchors both the git-root search and any relative
    ``path_opt``: the docs source directory for the live directive, the
    Markdown file's parent for the offline updater. An absolute ``path_opt``
    is used verbatim.
    """
    git_root = _find_git_root(base_dir)
    if not path_opt:
        return git_root
    candidate = Path(path_opt)
    if not candidate.is_absolute():
        candidate = git_root / candidate
    return candidate.resolve()


def _render_from_options(options: Mapping[str, str], base_dir: Path) -> str:
    """Render the matrix table for a directive block's option mapping.

    Shared by :class:`MatrixPythonDirective` (live rendering) and
    :func:`update_matrix_blocks` (offline source refresh) so both resolve the
    package, path, and floors identically.
    """
    root = _resolve_root(options.get("path"), base_dir)
    package = options.get("package") or root.name
    return python_matrix_table(
        root,
        package,
        python_floor=options.get("python-floor", ""),
        version_floor=options.get("version-floor", ""),
        tag_pattern=options.get("tag-pattern") or DEFAULT_TAG_PATTERN,
    )


class MatrixPythonDirective(SphinxDirective):
    """Render a package's Python compatibility matrix.

    Emits a GitHub-flavored support table (release ranges × Python versions)
    parsed with the host document's parser, so it lands as a real ``<table>``.

    The table normally lives *inside* the directive block as its content, kept
    current by the offline updater (:func:`update_matrix_blocks`, exposed as the
    ``click-extra refresh-directives`` command). Rendering that embedded copy
    needs no git access at build time, so shallow clones and read-only build
    hosts still show the matrix. When the block is empty, the directive falls
    back to generating the table from the working tree's git tags, so a freshly
    authored block renders before its first refresh.

    Options (all optional):

    - ``:package:`` — header column label. Defaults to the repository
      directory name.
    - ``:path:`` — git working tree to walk, absolute or relative to the
      documented project's git root. Defaults to that git root.
    - ``:python-floor:`` — drop Python columns below this ``X.Y`` version.
    - ``:version-floor:`` — drop release rows below this package version.
    - ``:tag-pattern:`` — regex selecting release tags. Defaults to
      :data:`DEFAULT_TAG_PATTERN`.

    The git fallback is resilient: a missing git binary, a non-repository path,
    or a tag-less repository logs a build warning and renders nothing rather
    than aborting the build.
    """

    has_content = True
    required_arguments = 0
    optional_arguments = 0
    option_spec: ClassVar[OptionSpec] = {
        "package": directives.unchanged,
        "path": directives.unchanged,
        "python-floor": directives.unchanged,
        "version-floor": directives.unchanged,
        "tag-pattern": directives.unchanged,
    }

    def run(self) -> list[nodes.Node]:
        # Prefer the embedded table (kept fresh by update_matrix_blocks): it
        # renders without touching git, so the build works on shallow clones.
        if self.content:
            table_lines = list(self.content)
        else:
            # Empty block: generate from the git tags as a first-render
            # fallback until the updater populates the source.
            try:
                table = _render_from_options(self.options, Path(self.env.srcdir))
            except (OSError, subprocess.SubprocessError) as error:
                logger.warning(
                    "click_extra.sphinx: matrix:python could not read git "
                    "tags: %s",
                    error,
                    location=self.get_location(),
                )
                return []
            if not table:
                logger.warning(
                    "click_extra.sphinx: matrix:python found no release tags "
                    "and the block embeds no table",
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


class MatrixDomain(StatelessDomain):
    """Sphinx domain registering the always-on ``matrix:*`` directives.

    Currently provides ``matrix:python`` (see :class:`MatrixPythonDirective`).
    Grouped in their own domain, distinct from Sphinx's built-in ``py`` domain
    and from the exec-gated ``click:*`` / ``python:*`` families, so a future
    ``matrix:click`` compatibility matrix has an obvious home.
    """

    name = MATRIX_DOMAIN
    label = "Compatibility matrices"
    directives: ClassVar[dict] = {
        "python": MatrixPythonDirective,
    }


def setup(app: Sphinx) -> None:
    """Register the ``matrix`` domain on ``app``.

    Called from :func:`click_extra.sphinx.setup` so projects only need to list
    ``"click_extra.sphinx"`` in their ``extensions``. Unlike the ``click:*`` /
    ``python:*`` families, the domain is registered unconditionally: it runs a
    canned matrix generator, not user-supplied Python, so it needs no opt-in.
    """
    app.add_domain(MatrixDomain)


_FENCE_OPEN_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<fence>`{3,})\{matrix:python\}[ \t]*$",
)
"""Opening fence of a ``matrix:python`` directive block in a Markdown source."""

_FENCE_CLOSE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,})[ \t]*$")
"""A bare code fence, candidate for closing an open ``matrix:python`` block."""

_OPTION_RE = re.compile(r"^[ \t]*:(?P<key>[\w-]+):[ \t]*(?P<value>.*?)[ \t]*$")
"""A ``:key: value`` directive option line (value optional for flags)."""


def _rewrite_matrix_blocks(text: str, base_dir: Path) -> str:
    """Return ``text`` with every ``matrix:python`` block's table regenerated.

    Each block keeps its options verbatim; only the body (the embedded table)
    is replaced with a freshly generated one, separated from the options by a
    blank line. A block whose generation fails (non-repository path, missing
    git, no tags) is left byte-for-byte untouched, so a transient failure never
    wipes a good table.
    """
    lines = text.splitlines()
    out: list[str] = []
    index = 0
    total = len(lines)
    while index < total:
        open_match = _FENCE_OPEN_RE.match(lines[index])
        if not open_match:
            out.append(lines[index])
            index += 1
            continue

        indent = open_match.group("indent")
        fence = open_match.group("fence")

        # Collect the leading option lines.
        options: dict[str, str] = {}
        cursor = index + 1
        while cursor < total:
            option_match = _OPTION_RE.match(lines[cursor])
            if not option_match:
                break
            options[option_match.group("key")] = option_match.group("value")
            cursor += 1

        # Find the closing fence: same indent, at least as many backticks.
        close = None
        for probe in range(cursor, total):
            close_match = _FENCE_CLOSE_RE.match(lines[probe])
            if (
                close_match
                and close_match.group("indent") == indent
                and len(close_match.group("fence")) >= len(fence)
            ):
                close = probe
                break

        if close is None:
            # Unterminated block: leave the opening line as-is and move on.
            out.append(lines[index])
            index += 1
            continue

        try:
            table = _render_from_options(options, base_dir)
        except (OSError, subprocess.SubprocessError):
            table = ""

        if not table:
            # Non-destructive: keep the original block verbatim on failure.
            out.extend(lines[index : close + 1])
            index = close + 1
            continue

        out.append(f"{indent}{fence}{{matrix:python}}")
        for key, value in options.items():
            out.append(f"{indent}:{key}: {value}" if value else f"{indent}:{key}:")
        out.append("")
        out.extend(f"{indent}{row}" if row else row for row in table.splitlines())
        out.append(f"{indent}{fence}")
        index = close + 1

    result = "\n".join(out)
    if text.endswith("\n"):
        result += "\n"
    return result


def _iter_markdown_files(paths: Iterable[Path]) -> Iterable[Path]:
    """Yield the Markdown sources under ``paths`` (files as-is, dirs recursed)."""
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.md"))
        else:
            yield path


def update_matrix_blocks(paths: Iterable[Path], *, check: bool = False) -> list[Path]:
    """Refresh every ``matrix:python`` block in the given Markdown sources.

    Walks ``paths`` (files, or directories recursed for ``*.md``), regenerates
    each block's table from its own options, and rewrites the file when its
    content changed. In ``check`` mode nothing is written; the return value
    still lists the files that would change, so a caller can exit non-zero to
    flag stale documentation in CI.

    :return: the files whose ``matrix:python`` blocks were (or, under
        ``check``, would be) updated.
    """
    changed: list[Path] = []
    for path in _iter_markdown_files(paths):
        original = path.read_text(encoding="utf-8")
        updated = _rewrite_matrix_blocks(original, base_dir=path.parent)
        if updated != original:
            changed.append(path)
            if not check:
                path.write_text(updated, encoding="utf-8")
    return changed
