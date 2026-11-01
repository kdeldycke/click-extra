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
"""Tests for the one-pass dunder baking.

The single-field ``prebake_dunder`` and ``prebake_version`` helpers are covered
in ``test_version.py``, beside the version option that reads what they write.
The project metadata readers are covered in ``test_project.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from click_extra.cli import demo
from click_extra.prebake import prebake_dunders

PYPROJECT_SCRIPTS = (
    '[project]\nname = "orchard"\n\n[project.scripts]\norchard = "orchard.cli:main"\n'
)
"""A ``pyproject.toml`` declaring one console script."""


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


# --- prebake_dunders ----------------------------------------------------------


def test_prebake_dunders_fills_every_empty_placeholder_in_one_pass(tmp_path):
    """Every empty placeholder is filled, and only the resolvers it needs run.

    A placeholder already holding a value and a field with no placeholder at all
    never trigger their resolver, so a build does not shell out for nothing.
    """
    source = tmp_path / "__init__.py"
    source.write_text(
        '__git_branch__ = ""\n__build_os__ = \'\'\n__git_tag__ = "v1"\n',
        encoding="UTF-8",
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
    assert source.read_text(encoding="UTF-8") == (
        '__git_branch__ = "main"\n__build_os__ = \'Linux\'\n__git_tag__ = "v1"\n'
    )


def test_prebake_dunders_leaves_a_placeholder_its_resolver_cannot_fill(tmp_path):
    """A resolver answering nothing leaves its placeholder, and the file, alone."""
    source = tmp_path / "__init__.py"
    source.write_text('__git_branch__ = ""\n', encoding="UTF-8")
    before = source.stat().st_mtime_ns

    assert prebake_dunders(source, {"__git_branch__": lambda: None}) == {}
    assert source.read_text(encoding="UTF-8") == '__git_branch__ = ""\n'
    assert source.stat().st_mtime_ns == before


def test_prebake_dunders_fills_two_placeholders_sharing_a_line(tmp_path):
    """Two literals on one line both land, whatever the first one's new length."""
    source = tmp_path / "__init__.py"
    source.write_text('__a__ = ""; __b__ = ""\n', encoding="UTF-8")

    baked = prebake_dunders(source, {"__a__": "a longer value", "__b__": "b"})
    assert baked == {"__a__": "a longer value", "__b__": "b"}
    assert (
        source.read_text(encoding="UTF-8") == '__a__ = "a longer value"; __b__ = "b"\n'
    )


@pytest.mark.parametrize(
    ("placeholder", "value", "expected"),
    (
        pytest.param('""', "main", '"main"', id="double-quotes"),
        pytest.param("''", "main", "'main'", id="single-quotes"),
        pytest.param('""', 'say "cheese"', '"say \\"cheese\\""', id="quote-in-value"),
        pytest.param("''", "kiwi's", "'kiwi\\'s'", id="apostrophe-in-value"),
        pytest.param('""', "a\\b", '"a\\\\b"', id="backslash-in-value"),
        pytest.param('""""""', "main", '"""main"""', id="triple-quotes"),
        pytest.param('r""', "a\\b", '"a\\\\b"', id="raw-prefix"),
        pytest.param('("" "")', "main", '("main")', id="implicit-concatenation"),
    ),
)
def test_prebake_dunders_writes_a_literal_holding_the_value(
    tmp_path, placeholder, value, expected
):
    """The baked literal parses back to the value, in the quotes it opened with.

    A value can carry the quote character the placeholder is written in, like a
    branch named after a fruit's owner: escaped, it cannot close the literal
    early, and the file still compiles.
    """
    source = tmp_path / "__init__.py"
    source.write_text(f"__git_branch__ = {placeholder}\n", encoding="UTF-8")

    assert prebake_dunders(source, {"__git_branch__": value}) == {
        "__git_branch__": value
    }
    baked = source.read_text(encoding="UTF-8")
    assert baked == f"__git_branch__ = {expected}\n"
    namespace: dict[str, str] = {}
    exec(baked, namespace)
    assert namespace["__git_branch__"] == value


def test_prebake_dunders_counts_columns_past_non_ascii_text(tmp_path):
    """A placeholder after a non-ASCII literal on the same line lands in place.

    The parser counts columns in UTF-8 bytes: read as characters, every
    multi-byte character ahead of the placeholder would shift the splice right.
    """
    source = tmp_path / "__init__.py"
    source.write_text(
        '__dessert__ = "crème brûlée"; __git_tag__ = ""\n', encoding="UTF-8"
    )

    prebake_dunders(source, {"__git_tag__": "v1.0"})
    assert (
        source.read_text(encoding="UTF-8")
        == '__dessert__ = "crème brûlée"; __git_tag__ = "v1.0"\n'
    )


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
    baked = init_path.read_text(encoding="UTF-8")
    assert '__build_os__ = ""' not in baked
    assert '__version__ = "1.0.0"' in baked
    assert f"Pre-baked {init_path}: __build_os__ = " in result.output
