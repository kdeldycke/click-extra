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
"""Tests for the reST-to-MyST docstring converter and its CLI command."""

from __future__ import annotations

from textwrap import dedent

import pytest
from click.testing import CliRunner

from click_extra.cli import convert_to_myst_cmd
from click_extra.myst_converter import (
    convert_comment_blocks,
    convert_directives,
    convert_directory,
    convert_file,
    convert_inline_code,
    convert_links,
    convert_source,
    convert_xrefs,
    detect_source_package,
)

# ---- Cross-references: :role:`target` -> {role}`target` --------------------


@pytest.mark.parametrize(
    ("rst", "expected"),
    [
        (":func:`foo`", "{func}`foo`"),
        (":data:`~extra_platforms.MACOS`", "{data}`~extra_platforms.MACOS`"),
        (
            "see :class:`str` and :meth:`str.split`",
            "see {class}`str` and {meth}`str.split`",
        ),
        # F-string interpolation targets are excluded.
        ('f":func:`~{self.id}`"', 'f":func:`~{self.id}`"'),
        # A backtick right before the role means the role-shaped text sits
        # inside a literal span, not a cross-reference.
        ("(`:param:`, `:return:`)", "(`:param:`, `:return:`)"),
        # Domain-qualified roles stay reST: converting the inner role alone
        # would leave a mangled hybrid.
        (":py:class:`Basket`", ":py:class:`Basket`"),
        # Already-MyST input is untouched (idempotence).
        ("{func}`foo`", "{func}`foo`"),
    ],
    ids=[
        "simple",
        "tilde",
        "multiple",
        "fstring-excluded",
        "backtick-preceded-excluded",
        "domain-qualified-excluded",
        "idempotent",
    ],
)
def test_convert_xrefs(rst, expected):
    assert convert_xrefs(rst) == expected


# ---- Named links: `text <url>`_ -> [text](url) -----------------------------


@pytest.mark.parametrize(
    ("rst", "expected"),
    [
        (
            "`Weather report <https://example.com/weather>`_",
            "[Weather report](https://example.com/weather)",
        ),
        # Multi-line link text collapses to single spaces.
        (
            "`a very\n   long label <https://example.com>`_",
            "[a very long label](https://example.com)",
        ),
        # Already-MyST input is untouched (idempotence).
        ("[done](https://example.com)", "[done](https://example.com)"),
    ],
    ids=["simple", "multi-line", "idempotent"],
)
def test_convert_links(rst, expected):
    assert convert_links(rst) == expected


# ---- Inline code: ``code`` -> `code` ---------------------------------------


@pytest.mark.parametrize(
    ("rst", "expected"),
    [
        ("``True``", "`True`"),
        ("mix of ``a`` and ``b``", "mix of `a` and `b`"),
        # Braces are excluded so f-string interpolations survive.
        ("``{self.id}``", "``{self.id}``"),
        # A brace-bearing literal is consumed whole: its closing backticks
        # must not pair with the next literal across the gap.
        (
            "``size``  ``{width}: {height}``  ``%(width)s``",
            "`size`  ``{width}: {height}``  `%(width)s`",
        ),
        ("``{``  ``%``", "``{``  `%`"),
        # Already-MyST input is untouched (idempotence).
        ("`True`", "`True`"),
    ],
    ids=[
        "simple",
        "multiple",
        "brace-excluded",
        "brace-gap-not-paired",
        "bare-brace-gap",
        "idempotent",
    ],
)
def test_convert_inline_code(rst, expected):
    assert convert_inline_code(rst) == expected


# ---- Directives: .. name:: -> ```{name} fences -----------------------------


@pytest.mark.parametrize(
    ("rst", "expected_fragments"),
    [
        (
            ".. note::\n\n    Cloudy today.",
            ["```{note}", "Cloudy today.", "```"],
        ),
        (
            ".. warning:: Storm ahead\n\n    Stay inside.",
            ["```{warning} Storm ahead", "Stay inside."],
        ),
        # Indented directive keeps its indentation on the fences.
        (
            "    .. hint::\n\n        Try oranges.",
            ["    ```{hint}", "    Try oranges.", "    ```"],
        ),
    ],
    ids=["bare", "with-argument", "indented"],
)
def test_convert_directives(rst, expected_fragments):
    result = convert_directives(rst)
    for fragment in expected_fragments:
        assert fragment in result


def test_convert_directives_keeps_fenced_body():
    """A directive body already holding a fence cannot nest: it stays reST."""
    rst = dedent("""\
        .. code-block:: markdown

            ```{python:render}
            print("kiwi")
            ```
        """)
    assert convert_directives(rst) == rst


def test_convert_directives_skips_fence_interiors():
    """A reST directive inside a fence is prior nested-conversion output: keep it."""
    myst = dedent("""\
        ```{tip}
        Ripen at room temperature.

        .. note::

            Bananas brown faster in the fridge.
        ```
        """)
    assert convert_directives(myst) == myst


def test_convert_source_nested_directives_idempotent():
    """Nested directives convert the outer level only, and re-runs are no-ops."""
    source = dedent('''\
        def store(fruit):
            """Store a fruit.

            .. tip::
                Check the skin first.

                .. note::
                    Thick skins keep longer.
            """
        ''')
    converted = convert_source(source)
    assert "```{tip}" in converted
    # The inner directive stays reST inside the fence, and stays stable.
    assert ".. note::" in converted
    assert "```{note}" not in converted
    assert convert_source(converted) == converted


def test_convert_source_fenced_samples_untouched():
    """Fence bodies are sample code: reST markup inside them is data."""
    source = dedent('''\
        def brew(tea):
            """Brew a cup.

            ```markdown
            See :func:`steep` and ``leaves``.
            ```
            """
        ''')
    assert convert_source(source) == source


def test_convert_comment_blocks():
    """`#:` blocks are unwrapped, converted, and re-wrapped."""
    rst = "#: .. note::\n#:\n#:     Ripe bananas only."
    result = convert_comment_blocks(rst)
    assert "#: ```{note}" in result
    assert "#: Ripe bananas only." in result
    assert "#: ```" in result


# ---- Scoping: only docstrings and comments are converted --------------------


def test_convert_source_scopes_to_docstrings_and_comments():
    source = dedent('''\
        """Sort ``apples`` before :func:`peel`."""

        # Ripeness is checked by :func:`peel` on ``green`` fruits.
        RIPE_RE = re.compile(r"``(\\w+)``")
        MESSAGE = "Use ``ripe`` fruit, see :func:`peel`."
        count = 3  # Twice the ``basket`` size.
        ''')
    converted = convert_source(source)

    assert '"""Sort `apples` before {func}`peel`."""' in converted
    assert "# Ripeness is checked by {func}`peel` on `green` fruits." in converted
    assert "# Twice the `basket` size." in converted
    # String literals and regex patterns are runtime code: byte-for-byte.
    assert 'RIPE_RE = re.compile(r"``(\\w+)``")' in converted
    assert 'MESSAGE = "Use ``ripe`` fruit, see :func:`peel`."' in converted


def test_convert_source_attribute_docstrings():
    source = dedent('''\
        FRUIT = "banana"
        """Default fruit, in its ``ripe`` state, see :data:`FRUIT`."""
        ''')
    converted = convert_source(source)
    assert 'FRUIT = "banana"' in converted
    assert '"""Default fruit, in its `ripe` state, see {data}`FRUIT`."""' in converted


def test_convert_source_sharp_colon_comment_blocks():
    source = dedent("""\
        #: .. note::
        #:
        #:     Ripe ``bananas`` only.
        BASKET = ["banana"]
        """)
    converted = convert_source(source)
    assert "#: ```{note}" in converted
    assert "#: Ripe `bananas` only." in converted
    assert '\nBASKET = ["banana"]' in converted


# ---- File and directory pipeline -------------------------------------------

SAMPLE_RST_MODULE = dedent('''\
    """Pick the ripest fruit.

    See :func:`ripeness` and the `market guide <https://example.com/fruits>`_.

    .. note::

        Prefer ``fresh`` produce.
    """
    ''')


def test_convert_file_roundtrip_and_idempotence(tmp_path):
    module = tmp_path / "basket.py"
    module.write_text(SAMPLE_RST_MODULE, encoding="utf-8")

    assert convert_file(module) is True
    converted = module.read_text(encoding="utf-8")
    assert "{func}`ripeness`" in converted
    assert "[market guide](https://example.com/fruits)" in converted
    assert "```{note}" in converted
    assert "`fresh`" in converted

    # A second pass finds nothing to change.
    assert convert_file(module) is False
    assert module.read_text(encoding="utf-8") == converted


def test_convert_directory_reports_only_changed(tmp_path):
    (tmp_path / "rest.py").write_text(SAMPLE_RST_MODULE, encoding="utf-8")
    (tmp_path / "myst.py").write_text('"""Already `MyST`."""\n', encoding="utf-8")
    changed = convert_directory(tmp_path)
    assert [path.name for path in changed] == ["rest.py"]


# ---- Source-package auto-detection -----------------------------------------


def _write_pyproject(tmp_path, scripts: dict[str, str]) -> None:
    lines = ["[project]", 'name = "orchard"', 'version = "1.0.0"']
    if scripts:
        lines.append("[project.scripts]")
        lines.extend(f'{name} = "{target}"' for name, target in scripts.items())
    (tmp_path / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_detect_source_package_single(tmp_path):
    _write_pyproject(tmp_path, {"orchard": "orchard.cli:main"})
    assert detect_source_package(tmp_path / "pyproject.toml") == tmp_path / "orchard"


def test_detect_source_package_no_entry_point(tmp_path):
    _write_pyproject(tmp_path, {})
    with pytest.raises(ValueError, match="no .project.scripts. entry point"):
        detect_source_package(tmp_path / "pyproject.toml")


def test_detect_source_package_multiple(tmp_path):
    _write_pyproject(
        tmp_path,
        {"orchard": "orchard.cli:main", "grove": "grove.cli:main"},
    )
    with pytest.raises(ValueError, match="Multiple source packages"):
        detect_source_package(tmp_path / "pyproject.toml")


def test_detect_source_package_missing_pyproject(tmp_path):
    with pytest.raises(ValueError, match="No pyproject.toml"):
        detect_source_package(tmp_path / "pyproject.toml")


# ---- CLI command ------------------------------------------------------------


def test_convert_to_myst_cli_explicit_directory(tmp_path):
    (tmp_path / "basket.py").write_text(SAMPLE_RST_MODULE, encoding="utf-8")
    result = CliRunner().invoke(convert_to_myst_cmd, [str(tmp_path)])
    assert result.exit_code == 0
    assert "Converted:" in result.output
    assert "1 file(s) converted." in result.output


def test_convert_to_myst_cli_autodetect(tmp_path, monkeypatch):
    _write_pyproject(tmp_path, {"orchard": "orchard.cli:main"})
    package = tmp_path / "orchard"
    package.mkdir()
    (package / "basket.py").write_text(SAMPLE_RST_MODULE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(convert_to_myst_cmd, [])
    assert result.exit_code == 0
    assert "1 file(s) converted." in result.output


def test_convert_to_myst_cli_autodetect_failure(tmp_path, monkeypatch):
    _write_pyproject(tmp_path, {})
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(convert_to_myst_cmd, [])
    assert result.exit_code != 0
    assert "Cannot auto-detect" in result.output


def test_convert_to_myst_cli_not_a_directory(tmp_path):
    target = tmp_path / "missing"
    result = CliRunner().invoke(convert_to_myst_cmd, [str(target)])
    assert result.exit_code != 0
    assert "Not a directory" in result.output
