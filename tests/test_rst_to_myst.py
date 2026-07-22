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
"""Tests for the `sphinx-apidoc` RST-to-MyST stub converter."""

from __future__ import annotations

from textwrap import dedent

import pytest

from click_extra.rst_to_myst import (
    convert_apidoc_rst_to_myst,
    convert_rst_files_in_directory,
)

APIDOC_STUB = dedent("""\
    orchard package
    ===============

    Submodules
    ----------

    orchard.basket module
    ---------------------

    .. automodule:: orchard.basket
       :members:
       :undoc-members:
       :show-inheritance:
    """)


@pytest.mark.parametrize(
    ("rst", "expected"),
    [
        # Underline characters map to heading levels.
        ("Title\n=====", "# Title"),
        ("Section\n-------", "## Section"),
        ("Sub\n~~~", "### Sub"),
        # Backslash escapes are stripped and identifiers wrapped in backticks.
        (
            "fruit\\_stand.apples module\n--------------------------",
            "## `fruit_stand.apples` module",
        ),
    ],
    ids=["h1", "h2", "h3", "escaped-identifier"],
)
def test_heading_conversion(rst, expected):
    assert expected in convert_apidoc_rst_to_myst(rst)


def test_automodule_block_wrapped_in_eval_rst():
    result = convert_apidoc_rst_to_myst(APIDOC_STUB)
    assert "# `orchard` package" in result
    assert "## Submodules" in result
    assert "## `orchard.basket` module" in result
    # The directive block is preserved verbatim inside an eval-rst fence.
    assert "```{eval-rst}" in result
    assert ".. automodule:: orchard.basket" in result
    assert "   :members:" in result
    assert result.rstrip().endswith("```")


def test_convert_rst_files_creates_md_and_deletes_rst(tmp_path):
    rst_path = tmp_path / "orchard.rst"
    rst_path.write_text(APIDOC_STUB, encoding="utf-8")
    converted = convert_rst_files_in_directory(tmp_path)
    assert converted == [tmp_path / "orchard.md"]
    assert not rst_path.exists()
    assert "```{eval-rst}" in (tmp_path / "orchard.md").read_text(encoding="utf-8")


def test_convert_rst_files_skips_non_apidoc(tmp_path):
    rst_path = tmp_path / "prose.rst"
    rst_path.write_text("Just prose\n==========\n", encoding="utf-8")
    assert convert_rst_files_in_directory(tmp_path) == []
    # Non-apidoc RST files are left in place.
    assert rst_path.exists()


def test_convert_rst_files_existing_md_wins(tmp_path):
    rst_path = tmp_path / "orchard.rst"
    rst_path.write_text(APIDOC_STUB, encoding="utf-8")
    md_path = tmp_path / "orchard.md"
    md_path.write_text("# Hand-written page\n", encoding="utf-8")
    assert convert_rst_files_in_directory(tmp_path) == []
    # The stale stub is deleted; the hand-written markdown is untouched.
    assert not rst_path.exists()
    assert md_path.read_text(encoding="utf-8") == "# Hand-written page\n"
