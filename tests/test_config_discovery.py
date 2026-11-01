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
"""Test the search for configuration files, in `click_extra.config.discovery`."""

from __future__ import annotations

import os
import string
import sys
import unittest.mock
from contextlib import chdir
from pathlib import Path
from subprocess import run

import click
import pytest
from extra_platforms import is_windows
from wcmatch import glob

from click_extra import (
    VCS,
    ConfigOption,
    config_option,
    search_params,
)
from click_extra.config.discovery import _DEFAULT_MAGIC_CHARACTERS


@pytest.mark.parametrize(
    ("search_parents", "subdirs", "create_file", "expected_start"),
    [
        pytest.param(
            False,
            ("subdir",),
            True,
            lambda p: [(str(p / "subdir"), "config.toml")],
            id="no-search",
        ),
        pytest.param(
            True,
            ("level1", "level2", "level3"),
            True,
            lambda p: [
                (str(p / "level1" / "level2" / "level3"), "config.toml"),
                (str(p / "level1" / "level2"), "config.toml"),
                (str(p / "level1"), "config.toml"),
                (str(p), "config.toml"),
            ],
            id="file-path",
        ),
        pytest.param(
            True,
            ("level1", "level2", "level3"),
            False,
            lambda p: [
                (str(p / "level1" / "level2" / "level3"), ""),
                (str(p / "level1" / "level2"), ""),
                (str(p / "level1"), ""),
                (str(p), ""),
            ],
            id="directory-path",
        ),
        pytest.param(
            True,
            (),
            True,
            lambda p: [(str(p), "config.toml")],
            id="shallow-reaches-root",
        ),
        pytest.param(
            True,
            ("a", "b", "c"),
            True,
            lambda p: [
                (str(p / "a" / "b" / "c"), "config.toml"),
                (str(p / "a" / "b"), "config.toml"),
                (str(p / "a"), "config.toml"),
                (str(p), "config.toml"),
            ],
            id="deep-order",
        ),
    ],
)
def test_parent_patterns(
    tmp_path, search_parents, subdirs, create_file, expected_start
):
    deep_path = tmp_path
    for subdir in subdirs:
        deep_path = deep_path / subdir
    deep_path.mkdir(parents=True, exist_ok=True)

    if create_file:
        config_file = deep_path / "config.toml"
        config_file.write_text("[test]\nvalue = 1")
        input_path = str(config_file)
    else:
        input_path = str(deep_path)

    @click.command
    @config_option(search_parents=search_parents)
    def test_cli():
        pass

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        assert isinstance(config_opt, ConfigOption)
        patterns = list(config_opt.parent_patterns(input_path))

    expected = expected_start(tmp_path)
    for i, exp in enumerate(expected):
        assert patterns[i] == exp, f"Pattern {i} mismatch"

    assert all(isinstance(p, tuple) and len(p) == 2 for p in patterns)

    if search_parents:
        assert all(
            root_dir is not None and Path(root_dir).is_absolute()
            for root_dir, _ in patterns
        )
        root_path = Path("/") if not is_windows() else Path(tmp_path.drive + "\\")
        last_root = patterns[-1][0]
        assert last_root is not None
        assert Path(last_root) == root_path


@pytest.mark.parametrize(
    ("pattern_factory", "expected_factory"),
    [
        pytest.param(
            lambda p: str(p / "a" / "b" / "*.toml"),
            lambda p: [
                (str(p / "a" / "b"), "*.toml"),
                (str(p / "a"), "*.toml"),
                (str(p), "*.toml"),
                *((str(parent), "*.toml") for parent in p.parents),
            ],
            id="file-glob-at-leaf",
        ),
        pytest.param(
            lambda p: "*.toml",
            lambda p: [(None, "*.toml")],
            id="entirely-magic",
        ),
        pytest.param(
            lambda p: str(p / "proj*" / "config.toml"),
            lambda p: [
                (str(p), str(Path("proj*") / "config.toml")),
                *(
                    (str(parent), str(Path("proj*") / "config.toml"))
                    for parent in p.parents
                ),
            ],
            id="magic-in-directory",
        ),
        pytest.param(
            lambda p: str(p / "a" / "*.toml|*.yaml|*.yml"),
            lambda p: [
                (str(p / "a"), "*.toml|*.yaml|*.yml"),
                (str(p), "*.toml|*.yaml|*.yml"),
                *((str(parent), "*.toml|*.yaml|*.yml") for parent in p.parents),
            ],
            id="pipe-separated-multi-glob",
        ),
        pytest.param(
            lambda p: str(p / "proj*" / "*.toml"),
            lambda p: [
                (str(p), str(Path("proj*", "*.toml"))),
                *((str(parent), str(Path("proj*", "*.toml"))) for parent in p.parents),
            ],
            id="multiple-magic-parts-in-suffix",
        ),
        pytest.param(
            lambda p: str(p / "*.toml"),
            lambda p: [
                (str(p), "*.toml"),
                *((str(parent), "*.toml") for parent in p.parents),
            ],
            id="single-depth-magic",
        ),
        pytest.param(
            lambda p: "~/a/b/*.toml",
            lambda p: [(None, "~/a/b/*.toml")],
            id="tilde-is-magic",
        ),
        pytest.param(
            lambda p: str(Path("**", "config.toml")),
            lambda p: [(None, str(Path("**", "config.toml")))],
            id="globstar-entirely-magic",
        ),
    ],
)
def test_parent_patterns_with_magic_pattern(
    tmp_path, pattern_factory, expected_factory
):
    """Test parent_patterns with glob patterns containing magic characters."""

    @click.command
    @config_option(search_parents=True)
    def test_cli():
        pass

    pattern = pattern_factory(tmp_path)
    expected = expected_factory(tmp_path)

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        assert isinstance(config_opt, ConfigOption)
        patterns = list(config_opt.parent_patterns(pattern))

    assert patterns == expected


def test_parent_patterns_magic_no_search(tmp_path):
    """Magic pattern with search_parents=False yields only the original."""

    @click.command
    @config_option(search_parents=False)
    def test_cli():
        pass

    pattern = str(tmp_path / "a" / "*.toml|*.yaml")

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        assert isinstance(config_opt, ConfigOption)
        patterns = list(config_opt.parent_patterns(pattern))

    assert patterns == [(str(tmp_path / "a"), "*.toml|*.yaml")]


def test_parent_patterns_relative_path(tmp_path):
    """Test parent_patterns resolves relative paths to absolute."""
    deep_path = tmp_path / "level1" / "level2"
    deep_path.mkdir(parents=True)
    config_file = deep_path / "config.toml"
    config_file.write_text("[test]\nvalue = 1")

    @click.command
    @config_option(search_parents=True)
    def test_cli():
        pass

    # Change to the parent directory to create a relative path.
    with chdir(tmp_path / "level1"):
        relative_path = "level2/config.toml"

        with click.Context(test_cli, info_name="test-cli"):
            config_opt = search_params(test_cli.params, ConfigOption)
            assert isinstance(config_opt, ConfigOption)

            patterns = list(config_opt.parent_patterns(relative_path))

            # All root_dirs should be absolute.
            assert all(
                root_dir is not None and Path(root_dir).is_absolute()
                for root_dir, _ in patterns
            )

            # First pattern should resolve to the config file's parent.
            root_dir, file_pattern = patterns[0]
            assert root_dir is not None
            assert Path(root_dir) == config_file.parent
            assert file_pattern == config_file.name


def test_parent_patterns_stop_at_path(tmp_path):
    """stop_at as a path limits the parent directory walk."""
    deep_path = tmp_path / "a" / "b" / "c"
    deep_path.mkdir(parents=True)
    config_file = deep_path / "config.toml"
    config_file.write_text("[test]\nvalue = 1")

    boundary = tmp_path / "a"

    @click.command
    @config_option(search_parents=True, stop_at=boundary)
    def test_cli():
        pass

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        assert isinstance(config_opt, ConfigOption)
        patterns = list(config_opt.parent_patterns(str(config_file)))

    # First yield should be (parent_of_file, filename).
    root_dir, file_pattern = patterns[0]
    assert root_dir is not None
    assert Path(root_dir) == config_file.parent
    assert file_pattern == config_file.name
    # Every root_dir should be inside or equal to the boundary.
    for root_dir, _ in patterns:
        assert root_dir is not None
        assert Path(root_dir).is_relative_to(boundary), (
            f"{root_dir} is outside boundary {boundary}"
        )


@pytest.mark.parametrize(
    ("has_vcs", "expected_bounded"),
    [
        pytest.param(True, True, id="with-vcs-root"),
        pytest.param(False, False, id="no-vcs-root"),
    ],
)
def test_parent_patterns_stop_at_vcs(tmp_path, has_vcs, expected_bounded):
    """stop_at=VCS stops at VCS root, or walks to filesystem root if none."""
    vcs_root = tmp_path / "repo"
    vcs_root.mkdir()
    if has_vcs:
        (vcs_root / ".git").mkdir()

    deep_path = vcs_root / "src" / "pkg"
    deep_path.mkdir(parents=True)

    @click.command
    @config_option(search_parents=True, stop_at=VCS)
    def test_cli():
        pass

    pattern = str(deep_path / "*.toml")

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        assert isinstance(config_opt, ConfigOption)
        patterns = list(config_opt.parent_patterns(pattern))

    assert patterns[0] == (str(deep_path), "*.toml")

    if expected_bounded:
        for root_dir, _ in patterns:
            assert root_dir is not None
            assert Path(root_dir).is_relative_to(vcs_root), (
                f"{root_dir} is outside VCS root {vcs_root}"
            )
    else:
        root_path = Path("/") if not is_windows() else Path(tmp_path.drive + "\\")
        last_root = patterns[-1][0]
        assert last_root is not None
        assert Path(last_root) == root_path


def test_parent_patterns_inaccessible_directory(tmp_path):
    """Walk stops at an inaccessible directory."""
    deep_path = tmp_path / "a" / "b" / "c"
    deep_path.mkdir(parents=True)
    config_file = deep_path / "config.toml"
    config_file.write_text("[test]\nvalue = 1")

    @click.command
    @config_option(search_parents=True)
    def test_cli():
        pass

    original_access = os.access

    def fake_access(path, mode, **kwargs):
        if Path(path).resolve() == (tmp_path / "a").resolve():
            return False
        return original_access(path, mode, **kwargs)

    with click.Context(test_cli, info_name="test-cli"):
        config_opt = search_params(test_cli.params, ConfigOption)
        assert isinstance(config_opt, ConfigOption)
        with unittest.mock.patch(
            "click_extra.config.discovery.os.access", side_effect=fake_access
        ):
            patterns = list(config_opt.parent_patterns(str(config_file)))

    # First yield: (parent_of_file, filename).
    root_dir, file_pattern = patterns[0]
    assert root_dir is not None
    assert Path(root_dir) == config_file.parent
    assert file_pattern == config_file.name
    # Should stop before tmp_path/a (inaccessible).
    for root_dir, _ in patterns:
        assert root_dir is not None
        assert Path(root_dir) != tmp_path / "a"
        assert Path(root_dir) != tmp_path


@pytest.mark.parametrize(
    ("vcs_dir", "expected"),
    [
        pytest.param(".git", "found", id="git"),
        pytest.param(".hg", "found", id="hg"),
        pytest.param(None, None, id="no-vcs"),
    ],
)
def test_find_vcs_root(tmp_path, vcs_dir, expected):
    """Test _find_vcs_root with .git, .hg, and no VCS markers."""
    repo = tmp_path / "repo"
    repo.mkdir()
    if vcs_dir:
        (repo / vcs_dir).mkdir()

    deep = repo / "a" / "b"
    deep.mkdir(parents=True)

    result = ConfigOption._find_vcs_root(deep)
    if expected:
        assert result == repo
    else:
        assert result is None


def test_default_magic_characters_match_wcmatch():
    """The characters `_literal_base` splits on are the ones wcmatch reads as magic.

    Checked under the default search flags, over every printable character.
    """
    option = ConfigOption()
    magic = {char for char in string.printable if option._is_magic(char)}
    assert magic == _DEFAULT_MAGIC_CHARACTERS


@pytest.mark.parametrize(
    ("pattern_factory", "expected_factory"),
    [
        pytest.param(
            lambda p: str(p / "orchard" / "{*.toml,*.yaml}"),
            lambda p: str(p / "orchard"),
            id="brace-file-part",
        ),
        pytest.param(
            lambda p: str(p / "orchard" / "apple.toml"),
            lambda p: str(p / "orchard"),
            id="literal-file",
        ),
        pytest.param(
            lambda p: str(p / "orchard*" / "apple.toml"),
            str,
            id="magic-folder",
        ),
        pytest.param(lambda p: "*.toml", lambda p: None, id="entirely-magic"),
        pytest.param(lambda p: "apple.toml", lambda p: None, id="file-name-only"),
        pytest.param(lambda p: "~/orchard/*.toml", lambda p: None, id="tilde-is-magic"),
        pytest.param(
            lambda p: str(p / "orchard" / ".." / "barn" / "*.toml"),
            lambda p: None,
            id="parent-segment",
        ),
    ],
)
def test_literal_base(tmp_path, pattern_factory, expected_factory):
    """`_literal_base` stops at the first segment holding glob syntax."""
    option = ConfigOption()
    base = option._literal_base(pattern_factory(tmp_path))
    assert base == expected_factory(tmp_path)


def test_literal_base_needs_the_default_search_flags():
    """Custom search flags take wcmatch to read, so no folder is derived."""
    option = ConfigOption(search_pattern_flags=glob.GLOBSTAR | glob.BRACE)
    assert option._literal_base(str(Path("orchard", "apple.toml"))) is None


def test_search_skips_the_glob_of_a_missing_folder(tmp_path, monkeypatch):
    """No file can match in a folder that does not exist, so it is never globbed."""

    def fail(*args, **kwargs):
        raise AssertionError("A missing folder was globbed.")

    monkeypatch.setattr(glob, "iglob", fail)
    option = ConfigOption()
    with pytest.raises(FileNotFoundError):
        list(option.search_and_read_file(str(tmp_path / "missing" / "*.toml")))


def test_parent_search_goes_on_above_a_missing_folder(tmp_path):
    """The parent walk still finds a file above a folder that does not exist."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("[test-cli]\nk = 1", encoding="UTF-8")
    option = ConfigOption(search_parents=True, stop_at=tmp_path)
    found = [
        location
        for location, _content, _media_type in option.search_and_read_file(
            str(tmp_path / "missing" / "*.toml")
        )
    ]
    assert found == [config_file.resolve()]


@pytest.mark.once
def test_plain_run_loads_no_search_dependency(tmp_path):
    """A plain run without a configuration file loads neither `extra_platforms` nor
    `wcmatch`.

    Every invocation searches the default configuration folder, which rarely
    exists: a missing folder is ruled out before wcmatch is imported. The probe
    runs in a pristine interpreter, since pytest itself has both loaded already.
    The default folder is pointed at a place that does not exist, on every
    platform `click.get_app_dir()` knows, and the working directory holds no
    `pyproject.toml`.
    """
    ballast = ("extra_platforms", "wcmatch")
    probe = (
        "import sys\n"
        "from click_extra import command, echo\n"
        "@command\n"
        "def hello():\n"
        "    echo('Hello')\n"
        "hello.main([], prog_name='hello', standalone_mode=False)\n"
        "loaded = set(sys.modules)\n"
        f"leaked = [m for m in {ballast!r} "
        "if m in loaded or any(n.startswith(m + '.') for n in loaded)]\n"
        "assert not leaked, f'loaded by a plain run: {leaked}'\n"
    )
    home = tmp_path / "home"
    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
    }
    process = run(
        (sys.executable, "-c", probe),
        capture_output=True,
        text=True,
        encoding="UTF-8",
        check=False,
        cwd=tmp_path,
        env=env,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout == "Hello\n"
