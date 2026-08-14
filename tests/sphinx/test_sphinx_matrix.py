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
"""Tests for :mod:`click_extra.sphinx.matrix`.

Split in two halves: the dependency-light matrix-generation logic (git tag
walking, spec parsing, floor filtering) and the ``matrix`` Sphinx directive
that surfaces it. Both live under ``tests/sphinx/`` because importing
:mod:`click_extra.sphinx.matrix` pulls in the Sphinx package; the sibling
``conftest.py`` skips the whole tree when Sphinx or MyST-Parser is absent.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner

from click_extra.cli import refresh_directives_cmd
from click_extra.sphinx.matrix import (
    FORBIDDEN_CELL,
    PYTHON_RELEASE_DATES,
    SUPPORTED_CELL,
    UNDECLARED_CELL,
    DependencyMatrixGroup,
    PythonMatrixGroup,
    _dependency_columns,
    _extract_requirement,
    _python_cell,
    _render_block,
    _resolve_root,
    _spec_floor,
    _to_specifier_set,
    dependency_matrix_groups,
    dependency_matrix_table,
    parse_python_spec,
    python_matrix_groups,
    python_matrix_table,
    python_versions_released_by,
    update_matrix_blocks,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="matrix generation walks git tags, so the whole module needs a git binary",
)
"""Skip the module when git is missing, instead of failing 155 times.

The sibling ``conftest.py`` already spares downstream packagers an
``--ignore=tests/sphinx`` when Sphinx or MyST-Parser is absent. Git is the third
thing this tree needs, and the only one that is a binary rather than an import,
so it escaped that guard: a packager shipping the documentation extras without
git got a wall of ``FileNotFoundError`` naming no cause.
"""


def git_repo(path: Path) -> Callable[..., None]:
    """Initialize a bare-bones git repository at ``path``.

    Returns a ``run(*args)`` helper executing commands in that working tree,
    so each fixture only spells out the commits and tags it cares about.
    """
    path.mkdir(parents=True, exist_ok=True)

    def run(*args: str) -> None:
        subprocess.run(args, cwd=path, check=True, capture_output=True)

    run("git", "init", "--initial-branch=main", "--quiet")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "user.name", "Test")
    run("git", "config", "commit.gpgsign", "false")
    return run


def declare_widget(repo: Path, spec: str) -> None:
    """Write a ``pyproject.toml`` requiring ``widget{spec}``.

    Picks whichever dialect can express the range: Poetry's caret and tilde
    are not valid PEP 508, so they only ever appear in Poetry's own table.
    """
    if spec.startswith(("^", "~")) and not spec.startswith("~="):
        body = f'[tool.poetry.dependencies]\nwidget = "{spec}"\n'
    else:
        body = f'[project]\ndependencies = ["widget{spec}"]\n'
    (repo / "pyproject.toml").write_text(body, encoding="utf-8")


def tagged_table_rows(table: str) -> dict[str, list[str]]:
    """Parse a rendered GFM matrix into ``{row label: [cells…]}``.

    Lets a test assert a whole row at once (date, spec, then the full
    ``✅`` / ``❌`` vector) instead of probing the table for loose substrings.
    """
    rows = {}
    # Skip the header and its alignment separator.
    for line in table.splitlines()[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows[cells[0]] = cells[1:]
    return rows


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        # PEP 440.
        (">=3.10", ("3.10", "", set())),
        (">= 3.10", ("3.10", "", set())),
        (">=3.10,<3.14", ("3.10", "3.14", set())),
        (">=3.10, <3.14", ("3.10", "3.14", set())),
        (
            ">= 2.7, != 3.0.*, != 3.1.*, != 3.2.*",
            ("2.7", "", {"3.0", "3.1", "3.2"}),
        ),
        # setup.py's older non-wildcard syntax.
        (">= 2.7, != 3.0, != 3.1, != 3.2", ("2.7", "", {"3.0", "3.1", "3.2"})),
        # Poetry caret expands to major-bump ceiling.
        ("^3.7", ("3.7", "4.0", set())),
        ("^3.10", ("3.10", "4.0", set())),
        # Poetry tilde expands to minor-bump ceiling.
        ("~3.7", ("3.7", "3.8", set())),
        # Empty / whitespace.
        ("", ("", "", set())),
        ("   ", ("", "", set())),
    ],
)
def test_parse_python_spec(spec: str, expected: tuple[str, str, set[str]]) -> None:
    assert parse_python_spec(spec) == expected


def test_python_versions_released_by_default_table() -> None:
    # Python 3.10 released 2021-10-04, 3.11 released 2022-10-24.
    assert "3.10" in python_versions_released_by("2022-01-01")
    assert "3.11" not in python_versions_released_by("2022-01-01")
    assert "3.11" in python_versions_released_by("2023-01-01")


def test_python_versions_released_by_sorted_ascending() -> None:
    result = python_versions_released_by("2020-01-01")
    assert result == sorted(result, key=lambda v: tuple(int(p) for p in v.split(".")))


def test_python_versions_released_by_custom_table() -> None:
    custom = {"3.99": "2099-01-01", "3.5": "2010-01-01"}
    assert python_versions_released_by("2020-01-01", release_dates=custom) == ["3.5"]
    assert python_versions_released_by("2099-06-01", release_dates=custom) == [
        "3.5",
        "3.99",
    ]


def test_python_release_dates_shape() -> None:
    """Every entry must be ``X.Y`` → ISO date string."""
    for version, iso_date in PYTHON_RELEASE_DATES.items():
        assert version.count(".") == 1
        major, minor = version.split(".")
        assert major.isdigit()
        assert minor.isdigit()
        assert len(iso_date) == 10
        assert iso_date[4] == "-" and iso_date[7] == "-"


@pytest.fixture
def synthetic_repo(tmp_path: Path) -> Path:
    """Build a tiny git repo with two tagged commits declaring different
    Python support sets, so ``python_matrix_groups`` sees an evolution.
    """
    repo = tmp_path / "repo"
    run = git_repo(repo)

    # Tag v1.0.0: Poetry-style declaration, no classifiers.
    (repo / "pyproject.toml").write_text(
        '[tool.poetry.dependencies]\npython = "^3.10"\n',
        encoding="utf-8",
    )
    run("git", "add", "pyproject.toml")
    run("git", "commit", "-m", "v1.0.0", "--quiet")
    run("git", "tag", "v1.0.0")

    # Tag v2.0.0: PEP 621 + classifiers.
    (repo / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.11"\n'
        "classifiers = [\n"
        '  "Programming Language :: Python :: 3.11",\n'
        '  "Programming Language :: Python :: 3.12",\n'
        "]\n",
        encoding="utf-8",
    )
    run("git", "add", "pyproject.toml")
    run("git", "commit", "-m", "v2.0.0", "--quiet")
    run("git", "tag", "v2.0.0")

    return repo


def test_python_matrix_groups_synthetic(synthetic_repo: Path) -> None:
    groups = python_matrix_groups(synthetic_repo)
    assert len(groups) == 2
    # v1.0.0: Poetry ``^3.10`` capped at next-group-start = v2.0.0's date.
    # v2.0.0 commits are all on the same day, so the cap barely stretches
    # past v1.0.0; the exact set depends on when Python versions had shipped
    # relative to that day. The floor is what we can assert deterministically.
    assert groups[0].first_tag == "v1.0.0"
    assert "3.10" in groups[0].python_versions
    # v2.0.0: classifiers drive the set.
    assert groups[1].first_tag == "v2.0.0"
    assert groups[1].python_versions == ("3.11", "3.12")


def test_python_matrix_groups_returns_named_tuple(synthetic_repo: Path) -> None:
    groups = python_matrix_groups(synthetic_repo)
    assert all(isinstance(g, PythonMatrixGroup) for g in groups)
    assert groups[0].first_tag == groups[0][0]
    assert groups[0].python_versions == groups[0][3]


def test_python_matrix_groups_no_tags(tmp_path: Path) -> None:
    """A repo with no matching tags returns an empty list."""
    repo = tmp_path / "empty"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", "--quiet"], cwd=repo, check=True
    )
    assert python_matrix_groups(repo) == []


def test_python_matrix_groups_version_floor(synthetic_repo: Path) -> None:
    """``version_floor`` drops release tags below the bare version."""
    # Floor at 2.0.0 keeps only v2.0.0, so the v1.0.0 group disappears.
    groups = python_matrix_groups(synthetic_repo, version_floor="2.0.0")
    assert len(groups) == 1
    assert groups[0].first_tag == "v2.0.0"
    assert groups[0].python_versions == ("3.11", "3.12")
    # A floor above every tag yields no group at all.
    assert python_matrix_groups(synthetic_repo, version_floor="99.0.0") == []


def test_python_matrix_groups_ceiling_honored(tmp_path: Path) -> None:
    """A declared ``<X.Y`` ceiling excludes those versions from ``✅``."""
    repo = tmp_path / "ceiling"
    run = git_repo(repo)
    (repo / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.10,<3.13"\n',
        encoding="utf-8",
    )
    run("git", "add", "pyproject.toml")
    run("git", "commit", "-m", "v1.0.0", "--quiet")
    run("git", "tag", "v1.0.0")

    groups = python_matrix_groups(repo)
    assert len(groups) == 1
    assert "3.10" in groups[0].python_versions
    assert "3.11" in groups[0].python_versions
    assert "3.12" in groups[0].python_versions
    # 3.13 is above the explicit ceiling.
    assert "3.13" not in groups[0].python_versions


def test_python_matrix_groups_keeps_declared_spec(synthetic_repo: Path) -> None:
    """Each group carries its raw ``requires-python`` next to the set it
    attests, since the two drive different cells."""
    groups = python_matrix_groups(synthetic_repo)
    assert [g.spec for g in groups] == ["^3.10", ">=3.11"]


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        # Attested by a classifier.
        ("3.11", SUPPORTED_CELL),
        ("3.12", SUPPORTED_CELL),
        # Below the declared floor: an installer refuses outright.
        ("3.10", FORBIDDEN_CELL),
        ("3.9", FORBIDDEN_CELL),
        # Above every classifier, but nothing rules it out.
        ("3.13", UNDECLARED_CELL),
        ("3.14", UNDECLARED_CELL),
    ],
)
def test_python_cell(version: str, expected: str) -> None:
    group = PythonMatrixGroup(
        "v1.0.0", "v1.0.0", "2024-01-01", ("3.11", "3.12"), ">=3.11"
    )
    assert _python_cell(version, group) == expected


@pytest.mark.parametrize(
    ("spec", "version", "expected"),
    [
        # A ceiling is exclusive, so the ceiling itself is forbidden…
        (">=3.9,<3.12", "3.12", FORBIDDEN_CELL),
        (">=3.9,<3.12", "3.13", FORBIDDEN_CELL),
        # …and an exclusion clause punches an isolated hole.
        (">=3.9,!=3.11", "3.11", FORBIDDEN_CELL),
        (">=3.9,!=3.11", "3.13", UNDECLARED_CELL),
        # A range declaring no spec at all can forbid nothing.
        ("", "2.7", UNDECLARED_CELL),
    ],
)
def test_python_cell_spec_shapes(spec: str, version: str, expected: str) -> None:
    group = PythonMatrixGroup("v1.0.0", "v1.0.0", "2024-01-01", ("3.9", "3.10"), spec)
    assert _python_cell(version, group) == expected


def test_python_matrix_table_three_states(tmp_path: Path) -> None:
    """A release claiming less than its floor allows renders all three cells.

    The classifiers stop at 3.11 while ``requires-python`` only rules out
    everything under 3.10, so 3.12 is neither supported nor forbidden.
    """
    repo = tmp_path / "tristate"
    run = git_repo(repo)
    (repo / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.10"\n'
        "classifiers = [\n"
        '  "Programming Language :: Python :: 3.10",\n'
        '  "Programming Language :: Python :: 3.11",\n'
        "]\n",
        encoding="utf-8",
    )
    run("git", "add", "pyproject.toml")
    run("git", "commit", "-m", "v1.0.0", "--quiet")
    run("git", "tag", "v1.0.0")
    # A later release widens the classifier list, so 3.12 and 3.9 become
    # columns the older row has to classify.
    (repo / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.9"\n'
        "classifiers = [\n"
        + "".join(
            f'  "Programming Language :: Python :: 3.{n}",\n' for n in (9, 10, 11, 12)
        )
        + "]\n",
        encoding="utf-8",
    )
    run("git", "add", "pyproject.toml")
    run("git", "commit", "-m", "v2.0.0", "--quiet")
    run("git", "tag", "v2.0.0")

    rows = tagged_table_rows(python_matrix_table(repo, "proj"))
    # Columns run 3.12, 3.11, 3.10, 3.9 (newest-first).
    assert "".join(rows["`2.0.0`"][1:]) == "✅✅✅✅"
    assert "".join(rows["`1.0.0`"][1:]) == f"{UNDECLARED_CELL}✅✅{FORBIDDEN_CELL}"


def test_python_matrix_table_synthetic(synthetic_repo: Path) -> None:
    table = python_matrix_table(synthetic_repo, "my-project")
    # Header row must carry the label in backticks and the version columns.
    assert "`my-project`" in table
    assert "Released" in table
    assert "`3.11`" in table
    assert "`3.12`" in table
    # Columns run newest-first so the current support sits in the upper-left.
    assert table.index("`3.12`") < table.index("`3.11`")
    # The table body contains ✅ / ❌ glyphs.
    assert "✅" in table
    assert "❌" in table


@pytest.mark.parametrize("column_order", ["newest-first", "oldest-first"])
def test_python_matrix_table_column_order(
    synthetic_repo: Path, column_order: str
) -> None:
    table = python_matrix_table(synthetic_repo, "my-project", column_order=column_order)
    newest_first = table.index("`3.12`") < table.index("`3.11`")
    assert newest_first == (column_order == "newest-first")


@pytest.mark.parametrize("row_order", ["newest-first", "oldest-first"])
def test_python_matrix_table_row_order(synthetic_repo: Path, row_order: str) -> None:
    # Each tag forms its own single-release group, labeled by its bare version.
    table = python_matrix_table(synthetic_repo, "my-project", row_order=row_order)
    newest_on_top = table.index("`2.0.0`") < table.index("`1.0.0`")
    assert newest_on_top == (row_order == "newest-first")


def test_python_matrix_table_invalid_order(synthetic_repo: Path) -> None:
    with pytest.raises(ValueError, match="column-order"):
        python_matrix_table(synthetic_repo, "my-project", column_order="sideways")
    with pytest.raises(ValueError, match="row-order"):
        python_matrix_table(synthetic_repo, "my-project", row_order="sideways")


def test_python_matrix_table_python_floor(synthetic_repo: Path) -> None:
    """``python_floor`` trims the low Python columns from the header."""
    table = python_matrix_table(synthetic_repo, "my-project", python_floor="3.12")
    assert "`3.12`" in table
    # Columns below the floor are gone.
    assert "`3.10`" not in table
    assert "`3.11`" not in table


def test_python_matrix_table_empty(tmp_path: Path) -> None:
    """An empty repo produces the empty string, matching the ``if not
    groups: return ""`` early exit."""
    repo = tmp_path / "empty"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", "--quiet"], cwd=repo, check=True
    )
    assert python_matrix_table(repo, "proj") == ""


def test_matrix_python_directive_renders_table(sphinx_app_myst, synthetic_repo) -> None:
    """``{matrix} python`` renders the generated table as a real ``<table>``."""
    content = dedent(f"""
        ```{{matrix}} python
        :package: my-project
        :path: {synthetic_repo}
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    # The GitHub-flavored table is parsed by the host MyST parser into HTML.
    assert "<table" in html
    assert "my-project" in html
    assert "3.11" in html
    assert "3.12" in html


def test_matrix_python_directive_respects_floors(sphinx_app_myst, synthetic_repo):
    """The hyphenated directive options map to the floor parameters."""
    content = dedent(f"""
        ```{{matrix}} python
        :package: my-project
        :path: {synthetic_repo}
        :python-floor: 3.12
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "<table" in html
    # 3.12 column survives the floor; 3.10 / 3.11 header cells are dropped.
    assert ">3.12<" in html
    assert ">3.10<" not in html
    assert ">3.11<" not in html


def test_matrix_python_directive_order_options(sphinx_app_myst, synthetic_repo):
    """The `:column-order:` / `:row-order:` options flip both axes."""
    content = dedent(f"""
        ```{{matrix}} python
        :package: my-project
        :path: {synthetic_repo}
        :column-order: oldest-first
        :row-order: oldest-first
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "<table" in html
    assert html.index(">3.11<") < html.index(">3.12<")
    assert html.index("1.0.0") < html.index("2.0.0")


def test_matrix_python_directive_no_tags_renders_nothing(sphinx_app_myst, tmp_path):
    """A repository with no release tags yields no table (a build warning)."""
    repo = tmp_path / "untagged"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", "--quiet"], cwd=repo, check=True
    )
    content = dedent(f"""
        ```{{matrix}} python
        :package: my-project
        :path: {repo}
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "<table" not in html


def test_matrix_python_directive_renders_embedded_table(sphinx_app_myst) -> None:
    """An embedded table renders as a real ``<table>`` without any git access.

    This is the self-updating steady state: the offline updater keeps the
    table in the source, and the build renders that copy verbatim.
    """
    content = dedent("""
        ```{matrix} python
        :package: demo

        | `demo`  | `3.11` | `3.12` |
        | :------ | :----: | :----: |
        | `1.0.x` |   ✅   |   ❌   |
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "<table" in html
    assert "demo" in html
    assert "✅" in html and "❌" in html


def test_update_matrix_blocks_populates_empty_block(synthetic_repo, tmp_path) -> None:
    """The updater fills an empty block, keeping options and surrounding text."""
    doc = tmp_path / "page.md"
    doc.write_text(
        dedent(f"""
            # Doc

            Intro paragraph.

            ```{{matrix}} python
            :package: my-project
            :path: {synthetic_repo}
            ```

            Outro paragraph.
        """),
        encoding="utf-8",
    )
    assert update_matrix_blocks([doc]) == [doc]
    text = doc.read_text(encoding="utf-8")
    assert "| `my-project`" in text
    assert "✅" in text
    # Options preserved verbatim.
    assert ":package: my-project" in text
    assert f":path: {synthetic_repo}" in text
    # Prose around the block is untouched.
    assert "Intro paragraph." in text
    assert "Outro paragraph." in text


def test_update_matrix_blocks_idempotent(synthetic_repo, tmp_path) -> None:
    """A second run over freshly written blocks reports no change."""
    doc = tmp_path / "page.md"
    doc.write_text(
        dedent(f"""
            ```{{matrix}} python
            :package: my-project
            :path: {synthetic_repo}
            ```
        """),
        encoding="utf-8",
    )
    assert update_matrix_blocks([doc]) == [doc]
    assert update_matrix_blocks([doc]) == []


def test_update_matrix_blocks_check_mode(synthetic_repo, tmp_path) -> None:
    """``check=True`` flags a stale block without writing to disk."""
    doc = tmp_path / "page.md"
    original = dedent(f"""
        ```{{matrix}} python
        :package: my-project
        :path: {synthetic_repo}
        ```
    """)
    doc.write_text(original, encoding="utf-8")
    assert update_matrix_blocks([doc], check=True) == [doc]
    assert doc.read_text(encoding="utf-8") == original


def test_update_matrix_blocks_leaves_bad_path_untouched(tmp_path) -> None:
    """A block whose git generation fails is left byte-for-byte unchanged."""
    doc = tmp_path / "page.md"
    original = dedent("""
        ```{matrix} python
        :package: nope
        :path: /nonexistent/not-a-repo
        ```
    """)
    doc.write_text(original, encoding="utf-8")
    assert update_matrix_blocks([doc]) == []
    assert doc.read_text(encoding="utf-8") == original


def test_update_matrix_blocks_skips_examples_nested_in_code_block(
    synthetic_repo, tmp_path
) -> None:
    """Matrix examples shown inside a longer code fence are never refreshed.

    Both forms are documented illustrations here, not live blocks, even though
    their generation would succeed: the fence-aware walk copies them verbatim.
    """
    doc = tmp_path / "page.md"
    documented = dedent(f"""
        ````{{code-block}} markdown
        ```{{matrix}} python
        :package: my-project
        :path: {synthetic_repo}
        ```
        ````

        ````{{code-block}} markdown
        <!-- matrix python path={synthetic_repo} -->

        <!-- matrix-end -->
        ````
    """)
    doc.write_text(documented, encoding="utf-8")
    assert update_matrix_blocks([doc]) == []
    assert doc.read_text(encoding="utf-8") == documented


def test_refresh_directives_cli(synthetic_repo, tmp_path) -> None:
    """`click-extra refresh-directives` refreshes in place; --check gates CI."""
    doc = tmp_path / "page.md"
    doc.write_text(
        dedent(f"""
            ```{{matrix}} python
            :package: my-project
            :path: {synthetic_repo}
            ```
        """),
        encoding="utf-8",
    )
    runner = CliRunner()
    # A stale block exits non-zero under --check, without writing.
    result = runner.invoke(refresh_directives_cmd, ["--check", str(doc)])
    assert result.exit_code == 1
    assert "| `my-project`" not in doc.read_text(encoding="utf-8")
    # Write mode refreshes the block and names the file.
    result = runner.invoke(refresh_directives_cmd, [str(doc)])
    assert result.exit_code == 0
    assert "refreshed" in result.output
    assert "| `my-project`" in doc.read_text(encoding="utf-8")
    # A freshly refreshed block is clean.
    result = runner.invoke(refresh_directives_cmd, ["--check", str(doc)])
    assert result.exit_code == 0


def test_refresh_directives_cli_without_sphinx(tmp_path, monkeypatch) -> None:
    """The command fails gracefully (not a traceback) when sphinx is absent."""
    doc = tmp_path / "page.md"
    doc.write_text("```{matrix} python\n:package: x\n```\n", encoding="utf-8")
    # Simulate the optional sphinx extra being uninstalled: a ``None`` entry in
    # ``sys.modules`` makes the lazy ``import`` raise ImportError.
    monkeypatch.setitem(sys.modules, "click_extra.sphinx.matrix", None)
    result = CliRunner().invoke(refresh_directives_cmd, [str(doc)])
    assert result.exit_code != 0
    assert "sphinx" in result.output.lower()


@pytest.mark.parametrize(
    ("spec", "member", "nonmember"),
    [
        # Inclusive and exclusive floors.
        (">=8.3.1", "8.4.0", "8.3.0"),
        (">= 8.3.0", "8.3.0", "8.2.9"),
        (">8.1.4", "8.1.5", "8.1.4"),
        # Ceilings on their own.
        ("<=8.2", "8.2", "8.2.1"),
        ("<8.2", "8.1.9", "8.2"),
        # Pins: exact, wildcard, and PEP 440 arbitrary equality.
        ("==8.1.4", "8.1.4", "8.1.5"),
        ("==8.1.*", "8.1.9", "8.2.0"),
        ("===8.1.4", "8.1.4", "8.1.5"),
        # Compatible-release caps at the next minor…
        ("~= 8.1.4", "8.1.9", "8.2.0"),
        # …but at the next major when given a single minor.
        ("~=8.1", "8.9.0", "9.0"),
        # Bounded range, with and without the whitespace Poetry-era
        # declarations sprinkle around the comma.
        (">=8.0,<8.2", "8.1.0", "8.2.0"),
        (">= 8.0 , < 8.2", "8.1.0", "8.2.0"),
        # An exclusion clause punches a hole in an open floor.
        (">=8.0,!=8.1.*", "8.2.0", "8.1.5"),
        # Poetry caret caps at the next major, whatever its precision.
        ("^8", "8.9", "9.0"),
        ("^8.1", "8.9.0", "9.0.0"),
        ("^8.1.1", "8.9.0", "8.1.0"),
        # Poetry tilde caps at the next minor, whatever its precision.
        ("~8.1", "8.1.9", "8.2.0"),
        ("~8.1.4", "8.1.9", "8.2.0"),
        # A pre-release floor only matches under prereleases=True, which is
        # how every cell is computed.
        (">=8.0.0rc1", "8.0.0rc2", "7.9"),
        # An epoch outranks every epoch-less version.
        (">=1!2.0", "1!2.1", "2.0"),
    ],
)
def test_to_specifier_set(spec: str, member: str, nonmember: str) -> None:
    spec_set = _to_specifier_set(spec)
    assert spec_set is not None
    assert spec_set.contains(member, prereleases=True)
    assert not spec_set.contains(nonmember, prereleases=True)


@pytest.mark.parametrize(
    "spec",
    [
        "garbage",
        "8.1.4",  # A bare version is not a specifier.
        ">=8.0||<7.0",  # npm-style union, not PEP 440.
        "^8.1.1.1",  # Caret with more precision than the regex allows.
    ],
)
def test_to_specifier_set_unparsable(spec: str) -> None:
    """An unparsable specifier yields ``None``, which renders as an all-``❌``
    row rather than raising out of the Sphinx build."""
    assert _to_specifier_set(spec) is None


def test_to_specifier_set_empty_matches_everything() -> None:
    """An empty specifier is the universal set, not ``None``.

    Unreachable through the matrix itself, since a tag with no declared
    requirement is skipped before this point.
    """
    spec_set = _to_specifier_set("")
    assert spec_set is not None
    assert spec_set.contains("1.0", prereleases=True)


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        # Open floors accept only part of their minor series, so it splits
        # into patch-level columns.
        (">=8.3.1", ("8.3.1", True)),
        (">8.1.4", ("8.1.4", True)),
        (">=8.0,!=8.1.*", ("8.0", True)),
        # An exact pin accepts a single release of its series, so it needs a
        # column of its own precision.
        ("==8.1.4", ("8.1.4", True)),
        ("===8.1.4", ("8.1.4", True)),
        # Ranges covering their minor series keep it whole.
        (">=8.0,<8.2", ("8.0", False)),
        ("~=8.1.4", ("8.1.4", False)),
        ("^8.1.1", ("8.1.1", False)),
        ("~8.1", ("8.1", False)),
        ("~8", ("8", False)),
        ("==8.1.*", ("8.1", False)),
        ("8.1.*", ("8.1", False)),
        # No lower bound at all: a lone ceiling and a bare wildcard anchor
        # nothing of their own.
        ("<8.2", (None, False)),
        ("*", (None, False)),
    ],
)
def test_spec_floor(spec: str, expected: tuple[str | None, bool]) -> None:
    floor, patch_precise = _spec_floor(spec)
    expected_floor, expected_precise = expected
    assert (str(floor) if floor is not None else None) == expected_floor
    assert patch_precise == expected_precise


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        # PEP 621, with and without the whitespace and parentheses that core
        # metadata allows.
        ('[project]\ndependencies = ["widget>=1.0"]', ">=1.0"),
        ('[project]\ndependencies = ["widget (>=1.0)"]', ">=1.0"),
        ('[project]\ndependencies = ["widget >= 1.0"]', ">= 1.0"),
        ('[project]\ndependencies = ["widget~=1.0.4"]', "~=1.0.4"),
        ('[project]\ndependencies = ["widget>=1.0,<2.0"]', ">=1.0,<2.0"),
        ('[project]\ndependencies = ["widget==1.0.*"]', "==1.0.*"),
        # An extras bracket sits between the name and the specifier, and an
        # environment marker after it. Neither belongs in the Spec column.
        ('[project]\ndependencies = ["widget[extra]>=1.0"]', ">=1.0"),
        (
            "[project]\ndependencies = [\"widget>=1.0; python_version<'3.11'\"]",
            ">=1.0",
        ),
        (
            "[project]\ndependencies = [\"widget[a,b]>=1.0; sys_platform=='win32'\"]",
            ">=1.0",
        ),
        # A requirement declared behind an extra still counts.
        (
            '[project.optional-dependencies]\nrender = ["widget>=1.0"]',
            ">=1.0",
        ),
        # Development tooling does not describe what a consumer resolves.
        ('[dependency-groups]\ntest = ["widget>=1.0"]', ""),
        # Poetry's bare string and inline-table forms.
        ('[tool.poetry.dependencies]\nwidget = "^1.0"', "^1.0"),
        ('[tool.poetry.dependencies]\nwidget = { version = "^1.0" }', "^1.0"),
        (
            (
                "[tool.poetry.dependencies]\n"
                'widget = { version = "^1.0", optional = true }'
            ),
            "^1.0",
        ),
        # A name differing only in its separators is the same distribution…
        ('[project]\ndependencies = ["Widget_Lib>=1.0"]', ""),
        # …but one that merely starts with it is not.
        ('[project]\ndependencies = ["widgetry>=9.9"]', ""),
        # A requirement with no version constraint declares no range.
        ('[project]\ndependencies = ["widget"]', ""),
        # Unparsable TOML costs the tag its row rather than raising.
        ("[project\ndependencies = ", ""),
    ],
)
def test_extract_requirement(declaration: str, expected: str) -> None:
    assert _extract_requirement(declaration, "", "widget") == expected


def test_extract_requirement_canonicalizes_name() -> None:
    """PEP 503 name normalization decides the match, so a dependency spelled
    with any separator is found under any other spelling."""
    declaration = '[project]\ndependencies = ["Widget.Lib>=1.0"]'
    for spelling in ("widget-lib", "Widget_Lib", "WIDGET.LIB"):
        assert _extract_requirement(declaration, "", spelling) == ">=1.0"


def test_extract_requirement_from_setup_py() -> None:
    """A `setup.py` release has no tables to read, so its string literals are
    harvested and filtered by the same PEP 508 parse."""
    setup_py = (
        "from setuptools import setup\n"
        "setup(name='proj', install_requires=['widget[extra]>=1.0', 'other<2'])\n"
    )
    assert _extract_requirement("", setup_py, "widget") == ">=1.0"
    assert _extract_requirement("", setup_py, "other") == "<2"
    assert _extract_requirement("", setup_py, "absent") == ""


@pytest.mark.parametrize(
    ("specs", "latest", "expected"),
    [
        # A minor series stays one column…
        ([">=1.0"], "1.4.2", ["1.4", "1.0"]),
        # …unless an open floor pins a patch inside it, which splits it into
        # `X.Y.0` plus that floor.
        ([">=2.1.3"], "", ["2.1.3", "2.1.0"]),
        # A capped floor does not split, even at patch precision.
        (["~=2.1.3"], "", ["2.1"]),
        # Several ranges collapse onto one column per minor series.
        ([">=8.0,<8.2", "~=8.1.4"], "8.4.2", ["8.4", "8.1", "8.0"]),
        # A wildcard pin anchors the series it names.
        (["==8.1.*"], "8.4.2", ["8.4", "8.1"]),
        (["==8.1.*"], "", ["8.1"]),
        # An exact pin splits its series, so the release it accepts is
        # distinguishable from the rest of the minor.
        (["==8.1.4"], "", ["8.1.4", "8.1.0"]),
        # A lone ceiling has no lower bound to place, so it anchors nothing;
        # only the locked version contributes a column.
        (["<8.2"], "8.4.2", ["8.4"]),
        (["<8.2"], "", []),
    ],
)
def test_dependency_columns(specs: list[str], latest: str, expected: list[str]) -> None:
    columns = _dependency_columns(specs, latest)
    assert [str(version) for version, _ in columns] == expected


@pytest.fixture
def synthetic_dep_repo(tmp_path: Path) -> Path:
    """A git repo whose ``widget`` dependency floor evolves across two tags,
    exercising both minor-grouped and patch-split column derivation.
    """
    repo = tmp_path / "deprepo"
    run = git_repo(repo)

    for tag, spec in (("v1.0.0", ">=1.0"), ("v2.0.0", ">=2.1.3")):
        declare_widget(repo, spec)
        run("git", "add", "pyproject.toml")
        run("git", "commit", "-m", tag, "--quiet")
        run("git", "tag", tag)

    return repo


def test_dependency_matrix_groups(synthetic_dep_repo: Path) -> None:
    groups = dependency_matrix_groups(synthetic_dep_repo, "widget")
    assert all(isinstance(g, DependencyMatrixGroup) for g in groups)
    assert [g.spec for g in groups] == [">=1.0", ">=2.1.3"]


def test_dependency_matrix_table_columns_and_cells(synthetic_dep_repo: Path) -> None:
    table = dependency_matrix_table(
        synthetic_dep_repo, "proj", "widget", show_spec=True
    )
    # Minor 1.0 stays grouped; the open >=2.1.3 floor splits 2.1 into .0 / .3.
    assert "`1.0`" in table
    assert "`2.1.0`" in table
    assert "`2.1.3`" in table
    # Columns run newest-first, like the Python axis.
    assert table.index("`2.1.3`") < table.index("`2.1.0`") < table.index("`1.0`")
    # The Spec column carries each range's raw specifier.
    assert "Spec" in table
    assert "`>=1.0`" in table
    assert "`>=2.1.3`" in table
    assert "✅" in table and "❌" in table


@pytest.fixture
def exotic_spec_repo(tmp_path: Path) -> Path:
    """A repo whose ``widget`` requirement takes a different exotic shape at
    every tag, so one render exercises the whole specifier vocabulary.

    The caret tag also migrates the declaration from Poetry to PEP 621 and
    back, the way a real project's history crosses packaging backends.
    """
    repo = tmp_path / "exotic"
    run = git_repo(repo)
    specs = (
        ("v1.0.0", ">=1.0,<2.0"),  # Bounded range.
        ("v2.0.0", "~=2.1.4"),  # Compatible release.
        ("v3.0.0", "^3.1"),  # Poetry caret.
        ("v4.0.0", ">=4.0,!=4.1.*"),  # Open floor with an exclusion hole.
        ("v5.0.0", ">=5.2.1"),  # Open patch-level floor: splits its minor.
        ("v6.0.0", ">= 6.0, < 7.0"),  # Whitespace around the clauses.
    )
    for tag, spec in specs:
        declare_widget(repo, spec)
        run("git", "add", "pyproject.toml")
        run("git", "commit", "-m", tag, "--quiet")
        run("git", "tag", tag)
    return repo


def test_dependency_matrix_table_exotic_specs(exotic_spec_repo: Path) -> None:
    """Each specifier shape resolves to the right ``✅`` / ``❌`` vector.

    Columns are derived from the floors across history: every capped range
    contributes a whole minor series, while the open ``>=5.2.1`` floor splits
    5.2 into ``5.2.0`` / ``5.2.1``.
    """
    table = dependency_matrix_table(exotic_spec_repo, "proj", "widget", show_spec=True)
    header = table.splitlines()[0]
    assert [cell.strip() for cell in header.strip().strip("|").split("|")] == [
        "`proj`",
        "Released",
        "Spec",
        "`6.0`",
        "`5.2.1`",
        "`5.2.0`",
        "`4.0`",
        "`3.1`",
        "`2.1`",
        "`1.0`",
    ]
    rows = tagged_table_rows(table)
    # Each row keeps its raw specifier (whitespace squeezed out) next to the
    # cells it produced.
    assert {label: (cells[1], "".join(cells[2:])) for label, cells in rows.items()} == {
        "`6.0.0`": ("`>=6.0,<7.0`", "✅❌❌❌❌❌❌"),
        "`5.0.0`": ("`>=5.2.1`", "✅✅❌❌❌❌❌"),
        "`4.0.0`": ("`>=4.0,!=4.1.*`", "✅✅✅✅❌❌❌"),
        "`3.0.0`": ("`^3.1`", "❌❌❌❌✅❌❌"),
        "`2.0.0`": ("`~=2.1.4`", "❌❌❌❌❌✅❌"),
        "`1.0.0`": ("`>=1.0,<2.0`", "❌❌❌❌❌❌✅"),
    }


def test_dependency_matrix_table_merges_equivalent_specs(tmp_path: Path) -> None:
    """Consecutive ranges differing only in spelling render as a single row.

    Poetry's ``^2.0`` and PEP 621's ``>=2.0,<3.0.0`` describe the same set, so
    the re-merge pass collapses them instead of emitting two identical rows.
    This is what a packaging-backend migration looks like in the history.
    """
    repo = tmp_path / "equivalent"
    run = git_repo(repo)
    for tag, spec in (("v1.0.0", "^2.0"), ("v1.1.0", ">=2.0,<3.0.0")):
        declare_widget(repo, spec)
        run("git", "add", "pyproject.toml")
        run("git", "commit", "-m", tag, "--quiet")
        run("git", "tag", tag)

    assert [g.spec for g in dependency_matrix_groups(repo, "widget")] == [
        "^2.0",
        ">=2.0,<3.0.0",
    ]
    # Two groups, but one row: the label spans both tags (collapsing to the
    # whole major series) and the Spec column keeps the oldest spelling.
    rows = tagged_table_rows(
        dependency_matrix_table(repo, "proj", "widget", show_spec=True)
    )
    assert list(rows) == ["`1.x`"]
    assert rows["`1.x`"][1] == "`^2.0`"


def pinned_widget_repo(tmp_path: Path, name: str, spec: str) -> Path:
    """A one-tag repo pinning ``widget`` to ``spec``, locked at 2.4.0."""
    repo = tmp_path / name
    run = git_repo(repo)
    declare_widget(repo, spec)
    (repo / "uv.lock").write_text(
        'name = "widget"\nversion = "2.4.0"\n',
        encoding="utf-8",
    )
    run("git", "add", "pyproject.toml")
    run("git", "commit", "-m", "v1.0.0", "--quiet")
    run("git", "tag", "v1.0.0")
    return repo


@pytest.mark.parametrize(
    ("spec", "columns", "cells"),
    [
        # An exact pin earns a patch-precise column, so the one release it
        # accepts is visible instead of the row reading as all-❌.
        ("==2.1.4", ["`2.4`", "`2.1.4`", "`2.1.0`"], "❌✅❌"),
        ("===2.1.4", ["`2.4`", "`2.1.4`", "`2.1.0`"], "❌✅❌"),
        # A wildcard pin accepts its whole series, which one column serves.
        ("==2.1.*", ["`2.4`", "`2.1`"], "❌✅"),
    ],
)
def test_dependency_matrix_table_pinned_spec(
    tmp_path: Path, spec: str, columns: list[str], cells: str
) -> None:
    repo = pinned_widget_repo(tmp_path, f"pinned{abs(hash(spec))}", spec)
    table = dependency_matrix_table(repo, "proj", "widget")
    header = [c.strip() for c in table.splitlines()[0].strip().strip("|").split("|")]
    assert header == ["`proj`", "Released", *columns]
    assert "".join(tagged_table_rows(table)["`1.0.0`"][1:]) == cells


def test_dependency_matrix_table_lone_ceiling(tmp_path: Path) -> None:
    """A lone ceiling anchors no column of its own.

    Unlike a pin, it has no lower bound to place, so the only column left is
    the locked version, which the ceiling genuinely forbids. The all-❌ row is
    the honest rendering here, not a missing column.
    """
    repo = pinned_widget_repo(tmp_path, "ceiling-only", "<2.1")
    table = dependency_matrix_table(repo, "proj", "widget")
    assert "".join(tagged_table_rows(table)["`1.0.0`"][1:]) == "❌"


# Every example from Poetry's dependency-specification reference, mapping the
# declared range to the `(inclusive floor, exclusive ceiling)` it documents.
# https://python-poetry.org/docs/dependency-specification/
POETRY_RANGES: dict[str, tuple[str, str]] = {
    # Caret: bumps the leftmost non-zero component.
    "^0": ("0.0.0", "1.0.0"),
    "^0.0": ("0.0.0", "0.1.0"),
    "^0.0.3": ("0.0.3", "0.0.4"),
    "^0.2.3": ("0.2.3", "0.3.0"),
    "^1": ("1.0.0", "2.0.0"),
    "^1.2": ("1.2.0", "2.0.0"),
    "^1.2.3": ("1.2.3", "2.0.0"),
    # Tilde: bumps the minor, unless only a major was given.
    "~1": ("1.0.0", "2.0.0"),
    "~1.2": ("1.2.0", "1.3.0"),
    "~1.2.3": ("1.2.3", "1.3.0"),
    # Wildcard: pins the series it names.
    "1.*": ("1.0.0", "2.0.0"),
    "1.2.*": ("1.2.0", "1.3.0"),
}


@pytest.mark.parametrize(("spec", "bounds"), POETRY_RANGES.items())
def test_to_specifier_set_poetry_conformance(
    spec: str, bounds: tuple[str, str]
) -> None:
    """Every Poetry range translates to the interval Poetry documents.

    The `0.x` caret is the one that matters in practice: Poetry caps it at the
    next *minor*, since a `0.` release is allowed to break on every minor.
    """
    floor, ceiling = bounds
    spec_set = _to_specifier_set(spec)
    assert spec_set is not None, f"{spec} did not translate"
    assert spec_set.contains(floor, prereleases=True), f"{spec} excludes {floor}"
    assert not spec_set.contains(ceiling, prereleases=True), (
        f"{spec} reaches its exclusive ceiling {ceiling}"
    )


def test_to_specifier_set_poetry_bare_wildcard() -> None:
    """Poetry's bare ``*`` allows any version, so it has no bounds to check."""
    spec_set = _to_specifier_set("*")
    assert spec_set is not None
    assert spec_set.contains("0.0.1", prereleases=True)
    assert spec_set.contains("99.0", prereleases=True)


@pytest.mark.parametrize("column_order", ["newest-first", "oldest-first"])
def test_dependency_matrix_table_column_order(
    synthetic_dep_repo: Path, column_order: str
) -> None:
    table = dependency_matrix_table(
        synthetic_dep_repo, "proj", "widget", column_order=column_order
    )
    newest_first = table.index("`2.1.3`") < table.index("`1.0`")
    assert newest_first == (column_order == "newest-first")


@pytest.mark.parametrize("row_order", ["newest-first", "oldest-first"])
def test_dependency_matrix_table_row_order(
    synthetic_dep_repo: Path, row_order: str
) -> None:
    table = dependency_matrix_table(
        synthetic_dep_repo, "proj", "widget", row_order=row_order
    )
    newest_on_top = table.index("`2.0.0`") < table.index("`1.0.0`")
    assert newest_on_top == (row_order == "newest-first")


def test_dependency_matrix_table_empty(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", "--quiet"], cwd=repo, check=True
    )
    assert dependency_matrix_table(repo, "proj", "widget") == ""


def test_matrix_dependency_directive_renders(sphinx_app_myst, synthetic_dep_repo):
    """``{matrix} <dep>`` renders the dependency matrix as a real ``<table>``."""
    content = dedent(f"""
        ```{{matrix}} widget
        :package: proj
        :path: {synthetic_dep_repo}
        :show-spec:
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "<table" in html
    assert "Spec" in html
    assert "2.1.3" in html


def test_update_matrix_blocks_marker_form(synthetic_repo, tmp_path) -> None:
    """The `<!-- matrix AXIS opts -->` comment form refreshes to a raw table."""
    doc = tmp_path / "page.md"
    doc.write_text(
        f"# T\n\n<!-- matrix python package=my-project path={synthetic_repo} -->\n"
        "<!-- matrix-end -->\n\nafter\n",
        encoding="utf-8",
    )
    assert update_matrix_blocks([doc]) == [doc]
    text = doc.read_text(encoding="utf-8")
    # Start/end markers preserved; a raw GFM table sits between them.
    assert "<!-- matrix python package=my-project" in text
    assert "<!-- matrix-end -->" in text
    assert "| `my-project`" in text
    assert "✅" in text
    # No directive fence: the table is plain Markdown (renders on GitHub).
    assert "```{matrix}" not in text
    # Idempotent.
    assert update_matrix_blocks([doc]) == []


def test_update_matrix_blocks_marker_order_options(synthetic_repo, tmp_path) -> None:
    """`column-order` / `row-order` marker options flip the refreshed table."""
    doc = tmp_path / "page.md"
    doc.write_text(
        f"<!-- matrix python package=my-project path={synthetic_repo} "
        "column-order=oldest-first row-order=oldest-first -->\n"
        "<!-- matrix-end -->\n",
        encoding="utf-8",
    )
    assert update_matrix_blocks([doc]) == [doc]
    text = doc.read_text(encoding="utf-8")
    assert text.index("`3.11`") < text.index("`3.12`")
    assert text.index("`1.0.0`") < text.index("`2.0.0`")


def test_marker_form_renders_natively_in_sphinx(sphinx_app_myst) -> None:
    """A marker region's raw table renders as a real ``<table>`` with no
    directive involved (so it renders on GitHub the same way)."""
    content = dedent("""
        <!-- matrix python -->

        | `demo`  | `3.14` |
        | :------ | :----: |
        | `1.0.x` |   ✅   |

        <!-- matrix-end -->
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "<table" in html
    assert "demo" in html


def test_resolve_root_relative_base_dir(synthetic_repo, monkeypatch) -> None:
    """A relative ``base_dir`` still resolves to the real repo folder, so the
    default package label is never the empty ``Path(".").name``."""
    monkeypatch.chdir(synthetic_repo)
    root = _resolve_root(None, Path("."))
    assert root == synthetic_repo.resolve()
    assert root.name == synthetic_repo.name != ""


def test_render_block_raises_without_git(tmp_path, monkeypatch) -> None:
    """With git absent from PATH, generation raises an error the callers catch."""
    monkeypatch.setenv("PATH", "")
    with pytest.raises((OSError, subprocess.SubprocessError)):
        _render_block("python", {"path": str(tmp_path)}, tmp_path)


def test_update_matrix_blocks_preserves_table_without_git(tmp_path, monkeypatch):
    """Refreshing is non-destructive when git is unavailable: an embedded table
    stays put rather than being wiped by a failed regeneration."""
    doc = tmp_path / "page.md"
    doc.write_text(
        "```{matrix} python\n"
        ":package: p\n\n"
        "| `p`     | `3.14` |\n"
        "| :------ | :----: |\n"
        "| `1.0.0` |   ✅   |\n"
        "```\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PATH", "")
    assert update_matrix_blocks([doc]) == []
    assert "| `p`" in doc.read_text(encoding="utf-8")
    assert "✅" in doc.read_text(encoding="utf-8")


def test_matrix_directive_renders_embedded_without_git(sphinx_app_myst, monkeypatch):
    """A populated block renders at build time with no git on PATH: the
    shallow-clone / no-git CI case the embedded copy is designed for."""
    monkeypatch.setenv("PATH", "")
    content = dedent("""
        ```{matrix} python
        :package: demo

        | `demo`  | `3.14` |
        | :------ | :----: |
        | `1.0.x` |   ✅   |
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "<table" in html
    assert "demo" in html
