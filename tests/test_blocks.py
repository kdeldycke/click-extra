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
"""Test the dependency-light self-updating block toolkit."""

from __future__ import annotations

import subprocess
import sys

import pytest

from click_extra.blocks import (
    fence_spans,
    iter_markdown_files,
    marker_res,
    replace_region,
    update_blocks,
)

REGION = "intro\n\n<!-- t -->\nOLD\n<!-- t-end -->\n\nend\n"
"""A minimal document carrying a single `<!-- t --> / <!-- t-end -->` region."""


@pytest.mark.once
def test_blocks_module_needs_no_sphinx_extra():
    """`click_extra.blocks` imports without pulling in the `sphinx` extra.

    The whole point of hosting the toolkit in the package root is that a
    release pipeline or standalone script can reuse it without installing
    Sphinx or docutils. Assert it in a fresh interpreter so an already-loaded
    Sphinx (from another test) cannot mask a regression.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, click_extra.blocks; "
            "assert 'sphinx' not in sys.modules, 'sphinx leaked'; "
            "assert 'docutils' not in sys.modules, 'docutils leaked'",
        ],
        capture_output=True,
        text=True,
        encoding="UTF-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_blocks_reexported_from_sphinx_package():
    """The public trio stays importable from `click_extra.sphinx` too."""
    from click_extra import sphinx

    assert sphinx.replace_region is replace_region
    assert sphinx.marker_res is marker_res
    assert sphinx.update_blocks is update_blocks


def test_marker_res_grammar():
    """The open marker is bare; the close marker carries the `-end` suffix."""
    open_re, close_re = marker_res("demo")
    assert open_re.match("<!-- demo -->")
    assert open_re.match("<!-- demo arg1 arg2 -->")
    assert close_re.match("<!-- demo-end -->")
    # The open regex must not swallow the close marker of the same region.
    assert not open_re.match("<!-- demo-end -->")


@pytest.mark.parametrize(
    ("content", "pad", "expected"),
    [
        # Default padding: one blank line on each side of the body.
        (
            "NEW",
            True,
            "intro\n\n<!-- t -->\n\nNEW\n\n<!-- t-end -->\n\nend\n",
        ),
        # Empty content collapses to a single blank line between the markers,
        # whatever the padding.
        (
            "",
            True,
            "intro\n\n<!-- t -->\n\n<!-- t-end -->\n\nend\n",
        ),
        (
            "",
            False,
            "intro\n\n<!-- t -->\n\n<!-- t-end -->\n\nend\n",
        ),
        # pad=False keeps the blank line after the opening marker but drops the
        # one before the closing marker, so the region ends flush against it
        # (the mdformat-footnote layout).
        (
            "L1\nL2",
            False,
            "intro\n\n<!-- t -->\n\nL1\nL2\n<!-- t-end -->\n\nend\n",
        ),
    ],
)
def test_replace_region(content, pad, expected):
    """`replace_region` swaps the marked body under both padding modes."""
    out = replace_region(REGION, "t", content, pad=pad)
    assert out == expected
    # A second call with the same content is a no-op.
    assert replace_region(out, "t", content, pad=pad) == out


def test_replace_region_missing_markers_is_noop():
    """A document without the markers is returned untouched."""
    assert replace_region("no markers here", "t", "NEW") == "no markers here"
    # Opening marker present but no closing marker: also a no-op.
    assert replace_region("<!-- t -->\nbody\n", "t", "NEW") == "<!-- t -->\nbody\n"


def test_fence_spans_treats_nested_fences_as_opaque():
    """A fence nested inside a longer fence never starts a span of its own."""
    lines = [
        "````",  # Outer fence (4 backticks).
        "```",  # Inner fence, must be consumed as opaque content.
        "not a real fence open",
        "```",
        "````",  # Outer close.
    ]
    spans = fence_spans(lines)
    assert list(spans) == [0]
    assert spans[0].start == 0
    assert spans[0].close == 4


def test_update_blocks_writes_and_check_mode(tmp_path):
    """`update_blocks` rewrites changed files, and `check` reports without writing."""
    page = tmp_path / "page.md"
    page.write_text(REGION, encoding="utf-8")

    def rewrite(text, path):
        return replace_region(text, "t", "NEW")

    # check mode: reports the stale file but leaves it on disk untouched.
    would_change = update_blocks([tmp_path], rewrite, check=True)
    assert would_change == [page]
    assert page.read_text(encoding="utf-8") == REGION

    # write mode: rewrites the file, then a second pass is a clean no-op.
    changed = update_blocks([tmp_path], rewrite)
    assert changed == [page]
    assert "NEW" in page.read_text(encoding="utf-8")
    assert update_blocks([tmp_path], rewrite) == []


def test_iter_markdown_files_recurses_directories(tmp_path):
    """Directories are recursed for `*.md`; explicit files pass through as-is."""
    (tmp_path / "sub").mkdir()
    top = tmp_path / "a.md"
    nested = tmp_path / "sub" / "b.md"
    for path in (top, nested):
        path.write_text("", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("", encoding="utf-8")

    assert list(iter_markdown_files([tmp_path])) == [top, nested]
    assert list(iter_markdown_files([top])) == [top]
