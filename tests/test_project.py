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
"""Tests for the project and entry-point discovery of `click_extra.project`."""

from __future__ import annotations

from pathlib import Path

import click
import pytest

from click_extra.cli_wrapper import _resolve_project_dir
from click_extra.project import (
    detect_source_package,
    discover_package_init_files,
    entry_point_package,
    locate_package_root,
    read_project_scripts,
    resolve_entry_point,
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
        encoding="UTF-8",
    )
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_SCRIPTS, encoding="UTF-8")
    return tmp_path


# --- project metadata readers -------------------------------------------------


def test_read_project_scripts_prefers_pyproject(tmp_path):
    """``[project.scripts]`` wins over a ``setup.cfg`` sitting beside it."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_SCRIPTS, encoding="UTF-8")
    (tmp_path / "setup.cfg").write_text(SETUP_CFG_SCRIPTS, encoding="UTF-8")
    assert read_project_scripts(tmp_path) == {"orchard": "orchard.cli:main"}


def test_read_project_scripts_falls_back_to_setup_cfg(tmp_path):
    """``console_scripts`` in ``setup.cfg`` is read when ``pyproject.toml`` has none."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="UTF-8"
    )
    (tmp_path / "setup.cfg").write_text(SETUP_CFG_SCRIPTS, encoding="UTF-8")
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
    target.write_text("", encoding="UTF-8")
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


# --- discover_package_init_files tests ---


def test_discover_finds_init(tmp_path, monkeypatch):
    """Discovers ``__init__.py`` from ``[project.scripts]``."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\nmycli = "mypkg.__main__:main"\n',
        encoding="UTF-8",
    )
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('__version__ = "1.0"\n', encoding="UTF-8")

    paths = discover_package_init_files()
    assert len(paths) == 1
    assert paths[0].name == "__init__.py"


def test_discover_no_pyproject(tmp_path, monkeypatch):
    """Returns empty list when ``pyproject.toml`` is missing."""
    monkeypatch.chdir(tmp_path)
    assert discover_package_init_files() == []


def test_discover_no_scripts(tmp_path, monkeypatch):
    """Returns empty list when ``[project.scripts]`` is absent."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'test'\n",
        encoding="UTF-8",
    )
    assert discover_package_init_files() == []


def test_discover_deduplicates(tmp_path, monkeypatch):
    """Multiple scripts from the same package yield one path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\ncli1 = "mypkg.cli:main"\ncli2 = "mypkg.alt:run"\n',
        encoding="UTF-8",
    )
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('__version__ = "1.0"\n', encoding="UTF-8")

    paths = discover_package_init_files()
    assert len(paths) == 1


# --- detect_source_package -----------------------------------------------


def _write_pyproject(tmp_path, scripts: dict[str, str]) -> None:
    lines = ["[project]", 'name = "orchard"', 'version = "1.0.0"']
    if scripts:
        lines.append("[project.scripts]")
        lines.extend(f'{name} = "{target}"' for name, target in scripts.items())
    (tmp_path / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="UTF-8")


def test_detect_source_package_single(tmp_path):
    _write_pyproject(tmp_path, {"orchard": "orchard.cli:main"})
    assert detect_source_package(tmp_path) == tmp_path / "orchard"


def test_detect_source_package_src_layout(tmp_path):
    _write_pyproject(tmp_path, {"orchard": "orchard.cli:main"})
    (tmp_path / "src" / "orchard").mkdir(parents=True)
    assert detect_source_package(tmp_path) == tmp_path / "src" / "orchard"


def test_detect_source_package_setup_cfg_only(tmp_path):
    """A project declaring its scripts in `setup.cfg` alone is detected too."""
    (tmp_path / "setup.cfg").write_text(
        "[options.entry_points]\nconsole_scripts =\n    grove = grove.cli:main\n",
        encoding="UTF-8",
    )
    assert detect_source_package(tmp_path) == tmp_path / "grove"


def test_detect_source_package_no_entry_point(tmp_path):
    _write_pyproject(tmp_path, {})
    with pytest.raises(ValueError, match=r"No console-script entry point"):
        detect_source_package(tmp_path)


def test_detect_source_package_multiple(tmp_path):
    _write_pyproject(
        tmp_path,
        {"orchard": "orchard.cli:main", "grove": "grove.cli:main"},
    )
    with pytest.raises(ValueError, match="Multiple console scripts"):
        detect_source_package(tmp_path)


def test_detect_source_package_no_project(tmp_path):
    """A directory holding no packaging metadata names the place it read."""
    with pytest.raises(ValueError, match=r"No console-script entry point") as error:
        detect_source_package(tmp_path)
    assert str(tmp_path.resolve()) in str(error.value)


# --- resolve_entry_point ------------------------------------------------------


@pytest.mark.parametrize(
    ("scripts", "target"),
    (
        pytest.param({"orchard": "orchard.cli:main"}, "orchard.cli:main", id="one"),
        pytest.param(
            {"orchard": "orchard.cli:main", "orc": "orchard.cli:main"},
            "orchard.cli:main",
            id="alias",
        ),
        pytest.param(
            {"orchard": "orchard.cli:main", "orchard-admin": "orchard.cli:admin"},
            None,
            id="two-targets-one-package",
        ),
        pytest.param(
            {"orchard": "orchard.cli:main", "grove": "grove.cli:main"},
            None,
            id="two-packages",
        ),
        pytest.param({}, None, id="none"),
    ),
)
def test_resolve_entry_point_ambiguity_rule(tmp_path, scripts, target):
    """The scripts must name one target, however many names point to it.

    Two targets are ambiguous even inside one package: nothing tells which
    function the project means.
    """
    _write_pyproject(tmp_path, scripts)
    if target is None:
        with pytest.raises(ValueError):
            resolve_entry_point(tmp_path)
    else:
        assert resolve_entry_point(tmp_path).target == target


def test_resolve_entry_point_src_layout(src_project):
    """The entry point knows its module, function, package and import root."""
    entry_point = resolve_entry_point(src_project)
    assert entry_point.target == "orchard.cli:main"
    assert entry_point.root == src_project / "src"
    assert entry_point.module == "orchard.cli"
    assert entry_point.function == "main"
    assert entry_point.package == "orchard"


def test_resolve_entry_point_package_not_on_disk(tmp_path):
    """A package absent from disk leaves the root to each caller to settle."""
    _write_pyproject(tmp_path, {"orchard": "orchard.cli:main"})
    assert resolve_entry_point(tmp_path).root is None


def test_callers_share_the_ambiguity_rule(tmp_path):
    """`wrap` and `convert-to-myst` refuse the same project, each its own way."""
    _write_pyproject(
        tmp_path,
        {"orchard": "orchard.cli:main", "orchard-admin": "orchard.cli:admin"},
    )
    (tmp_path / "orchard").mkdir()
    with pytest.raises(ValueError, match="Multiple console scripts"):
        detect_source_package(tmp_path)
    with pytest.raises(click.ClickException, match="Multiple console scripts"):
        _resolve_project_dir(tmp_path)
