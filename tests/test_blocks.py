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

import re
import subprocess
import sys

import pytest

from click_extra.markdown.blocks import (
    fence_spans,
    iter_markdown_files,
    marker_res,
    replace_region,
    rewrite_fenced_regions,
    rewrite_fences,
    skip_region,
    split_options,
    update_blocks,
    walk_fences,
)

REGION = "intro\n\n<!-- t -->\nOLD\n<!-- t-end -->\n\nend\n"
"""A minimal document carrying a single `<!-- t --> / <!-- t-end -->` region."""


@pytest.mark.once
def test_blocks_module_needs_no_sphinx_extra():
    """`click_extra.markdown.blocks` imports without pulling in the `sphinx` extra.

    The whole point of hosting the toolkit outside `click_extra.sphinx` is that
    a release pipeline or standalone script can reuse it without installing
    Sphinx or docutils. Assert it in a fresh interpreter so an already-loaded
    Sphinx (from another test) cannot mask a regression.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, click_extra.markdown.blocks; "
                "assert 'sphinx' not in sys.modules, 'sphinx leaked'; "
                "assert 'docutils' not in sys.modules, 'docutils leaked'"
            ),
        ],
        capture_output=True,
        text=True,
        encoding="UTF-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr


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


QUOTED_REGION = (
    "<!-- t -->\n\nOLD\n\n```markdown\n<!-- t-end -->\n```\n\n<!-- t-end -->\n"
)
"""A region whose body quotes its own closing marker inside a code fence."""


def test_skip_region_steps_over_a_quoted_end_marker():
    """A closing marker quoted in a fence of the region does not end it."""
    lines = QUOTED_REGION.split("\n")
    assert skip_region(lines, 0, "t") == lines.index("<!-- t-end -->", 6) + 1


def test_rewrite_fenced_regions_keeps_a_quoted_end_marker():
    """A region holding a fence that quotes its closing marker round-trips.

    A search for the closing marker that does not step over fences ends the
    region on the quoted one, and each refresh then leaves the rest of the
    stale region below the new one.
    """
    fence = re.compile(r"^```\{demo\}")
    region = ["```markdown", "<!-- t-end -->", "```"]
    once = rewrite_fenced_regions("```{demo}\n```\n", "t", fence, lambda _: region)
    assert once.count("<!-- t-end -->") == 2
    assert rewrite_fenced_regions(once, "t", fence, lambda _: region) == once


def test_replace_region_ignores_markers_quoted_in_fences():
    """Markers shown in a code example are not the live region."""
    example = "```markdown\n<!-- t -->\nKEEP\n<!-- t-end -->\n```\n\n"
    out = replace_region(example + QUOTED_REGION, "t", "NEW")
    assert out.startswith(example)
    assert out == example + "<!-- t -->\n\nNEW\n\n<!-- t-end -->\n"


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


@pytest.mark.parametrize(
    ("lines", "close", "end"),
    [
        # A run at least as long as the opener closes it, a shorter one does not.
        (["```", "``", "````"], 2, 3),
        # A run followed by text opens a fence rather than closing one.
        (["```", "```python", "```"], 2, 3),
        # Blanks around the run do not matter.
        (["```", "apple", "```  "], 2, 3),
        # A close sits at the opener's indentation or deeper.
        (["  ```", "```", "  ```"], 2, 3),
        # A fence never closed spans to the end.
        (["```", "apple"], None, 2),
    ],
)
def test_fence_spans_close(lines, close, end):
    """A fence closes on the first bare backtick run that is long enough."""
    assert fence_spans(lines) == {0: (0, close, end)}


@pytest.mark.parametrize(
    ("lines", "body"),
    [
        (["```", "apple", "pear", "```", "after"], ["apple", "pear"]),
        (["```", "```"], []),
        # An unterminated fence holds the rest of the source.
        (["```", "apple", "pear"], ["apple", "pear"]),
    ],
)
def test_fence_span_body(lines, body):
    """The body of a span is everything between its fence lines."""
    assert lines[fence_spans(lines)[0].body] == body


@pytest.mark.parametrize(
    ("chars", "spans"),
    [
        ("`", {1: (1, None, 4)}),
        (":", {0: (0, 2, 3)}),
        ("`:", {0: (0, 2, 3)}),
    ],
)
def test_fence_spans_chars(chars, spans):
    """Colon fences are fences only on request, and close on colons alone."""
    assert fence_spans([":::{note}", "```", ":::", "after"], chars=chars) == spans


def test_walk_fences_steps_over_fences():
    """Lines outside fences come one by one, each fence as one unit."""
    lines = ["intro", "```", "<!-- t -->", "```", "outro", "````", "tail"]
    spans = fence_spans(lines)
    assert list(walk_fences(lines)) == [
        (0, None),
        (1, spans[1]),
        (4, None),
        (5, spans[5]),
    ]
    assert list(walk_fences(lines, spans, start=4)) == [(4, None), (5, spans[5])]


def test_rewrite_fences_keeps_what_visit_leaves():
    """A step `visit` passes on is copied, an unterminated fence included."""
    lines = ["apple", "```", "apple", "```", "apple", "```", "apple"]

    def visit(index, span):
        if span is None and lines[index] == "apple":
            return ["PEAR"], index + 1
        return None

    assert rewrite_fences(lines, visit) == [
        "PEAR",
        "```",
        "apple",
        "```",
        "PEAR",
        "```",
        "apple",
    ]


@pytest.mark.parametrize(
    ("lines", "options", "content"),
    [
        ([":caption: Orchard", "", "fig = 1"], {"caption": "Orchard"}, ["fig = 1"]),
        ([":linenos:", "fig = 1"], {"linenos": ""}, ["fig = 1"]),
        # A body opening on a reST role is content: an option needs whitespace
        # or the line end after its colon-wrapped name.
        (
            [":mod:`sqlite3` is imported here."],
            {},
            [":mod:`sqlite3` is imported here."],
        ),
    ],
)
def test_split_options(lines, options, content):
    """Leading option lines are split from the content of a fence body."""
    assert split_options(lines) == (options, content)


def test_update_blocks_writes_and_check_mode(tmp_path):
    """`update_blocks` rewrites changed files, and `check` reports without writing."""
    page = tmp_path / "page.md"
    page.write_text(REGION, encoding="UTF-8")

    def rewrite(text, path):
        return replace_region(text, "t", "NEW")

    # check mode: reports the stale file but leaves it on disk untouched.
    would_change = update_blocks([tmp_path], rewrite, check=True)
    assert would_change == [page]
    assert page.read_text(encoding="UTF-8") == REGION

    # write mode: rewrites the file, then a second pass is a clean no-op.
    changed = update_blocks([tmp_path], rewrite)
    assert changed == [page]
    assert "NEW" in page.read_text(encoding="UTF-8")
    assert update_blocks([tmp_path], rewrite) == []


def test_iter_markdown_files_recurses_directories(tmp_path):
    """Directories are recursed for `*.md`; explicit files pass through as-is."""
    (tmp_path / "sub").mkdir()
    top = tmp_path / "a.md"
    nested = tmp_path / "sub" / "b.md"
    for path in (top, nested):
        path.write_text("", encoding="UTF-8")
    (tmp_path / "ignore.txt").write_text("", encoding="UTF-8")

    assert list(iter_markdown_files([tmp_path])) == [top, nested]
    assert list(iter_markdown_files([top])) == [top]
