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

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner

from click_extra.cli import refresh_directives_cmd
from click_extra.sphinx.matrix import (
    PYTHON_RELEASE_DATES,
    DependencyMatrixGroup,
    PythonMatrixGroup,
    _render_block,
    _resolve_root,
    _to_specifier_set,
    dependency_matrix_groups,
    dependency_matrix_table,
    parse_python_spec,
    python_matrix_groups,
    python_matrix_table,
    python_versions_released_by,
    update_matrix_blocks,
)


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
    repo.mkdir()

    def run(*args: str) -> None:
        subprocess.run(args, cwd=repo, check=True, capture_output=True)

    run("git", "init", "--initial-branch=main", "--quiet")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "user.name", "Test")
    run("git", "config", "commit.gpgsign", "false")

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
    repo.mkdir()

    def run(*args: str) -> None:
        subprocess.run(args, cwd=repo, check=True, capture_output=True)

    run("git", "init", "--initial-branch=main", "--quiet")
    run("git", "config", "user.email", "t@e.com")
    run("git", "config", "user.name", "T")
    run("git", "config", "commit.gpgsign", "false")
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


def test_python_matrix_table_synthetic(synthetic_repo: Path) -> None:
    table = python_matrix_table(synthetic_repo, "my-project")
    # Header row must carry the label in backticks and the version columns.
    assert "`my-project`" in table
    assert "Released" in table
    assert "`3.11`" in table
    assert "`3.12`" in table
    # The table body contains ✅ / ❌ glyphs.
    assert "✅" in table
    assert "❌" in table


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
        (">=8.3.1", "8.4.0", "8.3.0"),
        (">= 8.3.0", "8.3.0", "8.2.9"),
        # Compatible-release caps at the next minor.
        ("~= 8.1.4", "8.1.9", "8.2.0"),
        # Poetry caret caps at the next major.
        ("^8.1", "8.9.0", "9.0.0"),
        # Poetry tilde caps at the next minor.
        ("~8.1", "8.1.9", "8.2.0"),
    ],
)
def test_to_specifier_set(spec: str, member: str, nonmember: str) -> None:
    spec_set = _to_specifier_set(spec)
    assert spec_set is not None
    assert spec_set.contains(member, prereleases=True)
    assert not spec_set.contains(nonmember, prereleases=True)


@pytest.fixture
def synthetic_dep_repo(tmp_path: Path) -> Path:
    """A git repo whose ``widget`` dependency floor evolves across two tags,
    exercising both minor-grouped and patch-split column derivation.
    """
    repo = tmp_path / "deprepo"
    repo.mkdir()

    def run(*args: str) -> None:
        subprocess.run(args, cwd=repo, check=True, capture_output=True)

    run("git", "init", "--initial-branch=main", "--quiet")
    run("git", "config", "user.email", "t@e.com")
    run("git", "config", "user.name", "T")
    run("git", "config", "commit.gpgsign", "false")

    (repo / "pyproject.toml").write_text(
        '[project]\ndependencies = ["widget>=1.0"]\n',
        encoding="utf-8",
    )
    run("git", "add", "pyproject.toml")
    run("git", "commit", "-m", "v1.0.0", "--quiet")
    run("git", "tag", "v1.0.0")

    (repo / "pyproject.toml").write_text(
        '[project]\ndependencies = ["widget>=2.1.3"]\n',
        encoding="utf-8",
    )
    run("git", "add", "pyproject.toml")
    run("git", "commit", "-m", "v2.0.0", "--quiet")
    run("git", "tag", "v2.0.0")

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
    # The Spec column carries each range's raw specifier.
    assert "Spec" in table
    assert "`>=1.0`" in table
    assert "`>=2.1.3`" in table
    assert "✅" in table and "❌" in table


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
