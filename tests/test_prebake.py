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
"""Tests for the one-pass dunder baking and the project metadata readers.

The single-field ``prebake_dunder`` and ``prebake_version`` helpers are covered
in ``test_version.py``, beside the version option that reads what they write.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from click_extra.cli import demo
from click_extra.prebake import (
    discover_package_init_files,
    entry_point_package,
    locate_package_root,
    prebake_dunders,
    read_project_scripts,
)

PYPROJECT_SCRIPTS = (
    '[project]\nname = "orchard"\n\n[project.scripts]\norchard = "orchard.cli:main"\n'
)
"""A ``pyproject.toml`` declaring one console script."""

SETUP_CFG_SCRIPTS = (
    "[options.entry_points]\nconsole_scripts =\n    vineyard = vineyard.cli:main\n"
)
"""A ``setup.cfg`` declaring one console script."""


@pytest.fixture
def src_project(tmp_path):
    """A src-layout project declaring one console script.

    Its package carries two empty placeholders: a build field, which always
    resolves, and a git field, which cannot resolve outside a repository.
    """
    package = tmp_path / "src" / "orchard"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        '__version__ = "1.0.0"\n__build_os__ = ""\n__git_branch__ = ""\n',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_SCRIPTS, encoding="utf-8")
    return tmp_path


# --- prebake_dunders ----------------------------------------------------------


def test_prebake_dunders_fills_every_empty_placeholder_in_one_pass(tmp_path):
    """Every empty placeholder is filled, and only the resolvers it needs run.

    A placeholder already holding a value and a field with no placeholder at all
    never trigger their resolver, so a build does not shell out for nothing.
    """
    source = tmp_path / "__init__.py"
    source.write_text(
        '__git_branch__ = ""\n__build_os__ = \'\'\n__git_tag__ = "v1"\n',
        encoding="utf-8",
    )
    calls: list[str] = []

    def resolver(name: str, value: str):
        def resolve() -> str:
            calls.append(name)
            return value

        return resolve

    baked = prebake_dunders(
        source,
        {
            "__git_branch__": resolver("__git_branch__", "main"),
            "__build_os__": "Linux",
            "__git_tag__": resolver("__git_tag__", "v2"),
            "__git_dirty__": resolver("__git_dirty__", "clean"),
        },
    )
    assert baked == {"__git_branch__": "main", "__build_os__": "Linux"}
    assert calls == ["__git_branch__"]
    assert source.read_text(encoding="utf-8") == (
        '__git_branch__ = "main"\n__build_os__ = \'Linux\'\n__git_tag__ = "v1"\n'
    )


def test_prebake_dunders_leaves_a_placeholder_its_resolver_cannot_fill(tmp_path):
    """A resolver answering nothing leaves its placeholder, and the file, alone."""
    source = tmp_path / "__init__.py"
    source.write_text('__git_branch__ = ""\n', encoding="utf-8")
    before = source.stat().st_mtime_ns

    assert prebake_dunders(source, {"__git_branch__": lambda: None}) == {}
    assert source.read_text(encoding="utf-8") == '__git_branch__ = ""\n'
    assert source.stat().st_mtime_ns == before


def test_prebake_dunders_fills_two_placeholders_sharing_a_line(tmp_path):
    """Two literals on one line both land, whatever the first one's new length."""
    source = tmp_path / "__init__.py"
    source.write_text('__a__ = ""; __b__ = ""\n', encoding="utf-8")

    baked = prebake_dunders(source, {"__a__": "a longer value", "__b__": "b"})
    assert baked == {"__a__": "a longer value", "__b__": "b"}
    assert (
        source.read_text(encoding="utf-8") == '__a__ = "a longer value"; __b__ = "b"\n'
    )


# --- project metadata readers -------------------------------------------------


def test_read_project_scripts_prefers_pyproject(tmp_path):
    """``[project.scripts]`` wins over a ``setup.cfg`` sitting beside it."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_SCRIPTS, encoding="utf-8")
    (tmp_path / "setup.cfg").write_text(SETUP_CFG_SCRIPTS, encoding="utf-8")
    assert read_project_scripts(tmp_path) == {"orchard": "orchard.cli:main"}


def test_read_project_scripts_falls_back_to_setup_cfg(tmp_path):
    """``console_scripts`` in ``setup.cfg`` is read when ``pyproject.toml`` has none."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    (tmp_path / "setup.cfg").write_text(SETUP_CFG_SCRIPTS, encoding="utf-8")
    assert read_project_scripts(tmp_path) == {"vineyard": "vineyard.cli:main"}


def test_read_project_scripts_without_metadata(tmp_path):
    assert read_project_scripts(tmp_path) == {}


@pytest.mark.parametrize(
    ("target", "expected"),
    (
        ("orchard.cli:main", "orchard"),
        ("orchard:main", "orchard"),
        ("orchard.cli.entry:run", "orchard"),
        ("orchard", "orchard"),
    ),
)
def test_entry_point_package(target, expected):
    assert entry_point_package(target) == expected


@pytest.mark.parametrize(
    ("layout", "expected"),
    (
        pytest.param(("orchard", "__init__.py"), ".", id="flat-package"),
        pytest.param(("src", "orchard", "__init__.py"), "src", id="src-package"),
        pytest.param(("orchard.py",), ".", id="flat-module"),
        pytest.param(("src", "orchard.py"), "src", id="src-module"),
        pytest.param(("orchard", "cli.py"), ".", id="namespace-package"),
    ),
)
def test_locate_package_root(tmp_path, layout, expected):
    """The directory to import from follows the package through both layouts."""
    target = tmp_path.joinpath(*layout)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    assert locate_package_root(tmp_path, "orchard") == tmp_path / expected


def test_locate_package_root_misses_an_absent_package(tmp_path):
    assert locate_package_root(tmp_path, "orchard") is None


def test_discover_package_init_files_finds_a_src_layout(src_project):
    """A package under ``src/`` is discovered like one at the project root."""
    assert discover_package_init_files(src_project) == [
        src_project / "src" / "orchard" / "__init__.py"
    ]


def test_discover_package_init_files_defaults_to_the_current_directory(
    src_project, monkeypatch
):
    """Without a directory, the paths are relative to the current one."""
    monkeypatch.chdir(src_project)
    assert discover_package_init_files() == [Path("src") / "orchard" / "__init__.py"]


# --- prebake all --------------------------------------------------------------


def test_prebake_all_bakes_a_src_layout_project(invoke, src_project, monkeypatch):
    """``prebake all`` finds the package of a src-layout project on its own.

    A build field always resolves, so its placeholder proves the file was found
    and written. The git field stays empty outside a repository.
    """
    monkeypatch.chdir(src_project)
    result = invoke(demo, ["prebake", "all"])
    assert result.exit_code == 0, result.output

    init_path = Path("src") / "orchard" / "__init__.py"
    baked = init_path.read_text(encoding="utf-8")
    assert '__build_os__ = ""' not in baked
    assert '__version__ = "1.0.0"' in baked
    assert f"Pre-baked {init_path}: __build_os__ = " in result.output
