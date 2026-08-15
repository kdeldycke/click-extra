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

"""Tests for `click_extra.screenshot` and the captures committed under `docs/`.

A screenshot is CLI output that stopped re-running, so it rots the moment the
command it pictures changes. Rich's SVG export happens to be machine-readable,
which is what makes both halves of this module possible: every run of
same-styled characters is one `<text>` element carrying its column as an `x`
offset and its width as a `textLength`, so the terminal text can be rebuilt from
the glyph coordinates and compared to what a CLI prints today.

That comparison needs neither a network round-trip nor a capture tool, which
keeps this an ordinary unit test. When the drift check fails, re-run the command
documented alongside the image in `docs/screenshots.md`.
"""

from __future__ import annotations

import os
import re
import sys
from html import unescape
from pathlib import Path
from typing import NamedTuple

import pytest

from click_extra import screenshot
from click_extra.screenshot import (
    _TEXT_ELEMENT_RE,
    PADDING,
    _rich_svg,
    capture_output,
    capture_svg,
    harden_svg,
    measure_cell_width,
    render_svg,
    trim_lines,
)

ASSETS = Path(__file__).parent.parent / "docs" / "assets"
"""Directory the committed captures live in."""

class Capture(NamedTuple):
    """A terminal capture committed under `docs/assets` and embedded in the docs.

    Carries what it takes to reshoot it, which is what makes the drift check
    below able to state the command each image is supposed to picture.
    """

    filename: str
    """Name of the SVG under {data}`ASSETS`."""

    args: tuple[str, ...]
    """Arguments the `click-extra` CLI was invoked with."""

    columns: int = 80
    """Terminal width it was shot at.

    A CLI wraps its output to the ambient terminal size, so a check running
    under a different width would compare a differently wrapped screen and fail
    on the wrapping alone.
    """

    head: int | None = None
    """Number of leading lines kept, or `None` when nothing was trimmed."""

    @property
    def prompt(self) -> str:
        """The `$` line the capture draws above its output."""
        return f"$ click-extra {' '.join(self.args)}"

    @property
    def command(self) -> tuple[str, ...]:
        """The command line reproducing this capture through this interpreter.

        `docs/screenshots.md` documents the same commands reached through
        `uv run`, which is what a human types from a checkout. Going straight at
        {data}`sys.executable` keeps the check independent of uv, and of whether
        the environment happens to be synced.
        """
        return (sys.executable, "-m", "click_extra", *self.args)


COMMITTED_CAPTURES = (
    Capture("color-gradient-screen.svg", ("gradient",)),
    Capture("text-styles-screen.svg", ("styles",), columns=160, head=14),
    Capture("theme-gallery-screen.svg", ("themes",), head=16),
)
"""Every capture shot by the `screenshot` command, in file-name order.

The `hello-click*` pair opening the readme is not here: those are written by
the tutorial's own `click:run` blocks at documentation-build time, and guarded
by `tests/test_sphinx_crossrefs.py` instead.
"""


SAMPLE_CAPTURE = (
    "\x1b[1mFruit\x1b[0m   Colour\nbanana  yellow\nkiwi    green\n\n2 fruits\n"
)
"""A small styled capture, with padded columns and a blank line to preserve.

The second column is deliberately left unstyled: sharing a style with the
padding that precedes it is what folds the two into a single run, which is the
case {func}`~click_extra.screenshot.harden_svg` exists to fix. Style the column
and the padding becomes a run of its own, which needs no fixing.
"""


def svg_to_lines(svg: str) -> list[str]:
    """Rebuild the captured terminal lines from a rendered capture.

    Groups the `<text>` runs into lines by their shared `y` baseline, then lays
    each one back on its column: the capture is monospaced, so dividing a run's
    `x` offset by the cell width gives the character column it starts at.

    Reads the same source of truth whether or not the file went through
    {func}`~click_extra.screenshot.harden_svg`, since hardening only moves a
    run's padding from its text into its offset.

    :param svg: source of a rendered capture.
    :return: the captured lines, top to bottom, with trailing whitespace removed.
    """
    cell_width = measure_cell_width(svg)
    lines: dict[float, str] = {}
    for element in _TEXT_ELEMENT_RE.finditer(svg):
        content = unescape(element["content"]).replace("\N{NO-BREAK SPACE}", " ")
        offset = re.search(r'\bx="(?P<value>-?[\d.]+)"', element["attrs"])
        baseline = re.search(r'\by="(?P<value>-?[\d.]+)"', element["attrs"])
        if not content or not offset or not baseline:
            continue
        y = float(baseline["value"])
        column = round(float(offset["value"]) / cell_width)
        lines[y] = lines.get(y, "").ljust(column) + content
    return [line.rstrip() for line in lines.values()]


def test_measure_cell_width_rejects_a_foreign_document():
    """A document carrying no sized text run is not a rendered capture."""
    with pytest.raises(ValueError, match="not a rendered terminal capture"):
        measure_cell_width("<svg><text x='0' y='0'>plain</text></svg>")


@pytest.mark.parametrize(
    ("head", "tail", "expected"),
    (
        (None, None, ["one", "two", "three", "four"]),
        (1, None, ["one", "<cut>"]),
        (None, 1, ["<cut>", "four"]),
        (1, 1, ["one", "<cut>", "four"]),
        # Bounds wide enough to cover the whole text leave it alone, marker
        # included: nothing was cut, so nothing should claim otherwise.
        (4, None, ["one", "two", "three", "four"]),
        (2, 2, ["one", "two", "three", "four"]),
    ),
)
def test_trim_lines(head, tail, expected):
    """`head` and `tail` keep their ends and account for what they dropped."""
    trimmed = trim_lines(
        "one\ntwo\nthree\nfour", head=head, tail=tail, truncation="<cut>"
    )
    assert trimmed.splitlines() == expected


def test_render_svg_without_the_extra(monkeypatch):
    """Rendering without Rich installed names the extra that ships it."""
    monkeypatch.setattr(screenshot, "Console", None)
    with pytest.raises(ImportError, match=r"screenshot"):
        render_svg(SAMPLE_CAPTURE)


def test_render_svg_folds_an_unusable_unique_id():
    """A file name that is not a CSS identifier cannot leak into a class name."""
    svg = render_svg(SAMPLE_CAPTURE, unique_id="my shot (v2).final")
    assert "my-shot-v2-.final" not in svg
    assert 'class="my-shot-v2-final-r1"' in svg


def test_harden_svg_preserves_every_column():
    """Hardening moves padding out of the glyphs without moving the glyphs.

    Rebuilding the terminal text from the raw render and from the hardened one
    has to yield the same lines: the padding a run carried inline is exactly the
    offset its `x` gained.
    """
    raw = _rich_svg(SAMPLE_CAPTURE, columns=40, title="", unique_id="sample")
    assert svg_to_lines(harden_svg(raw)) == svg_to_lines(raw)


def test_harden_svg_leaves_no_run_behind_padding():
    """No visible run in a hardened capture starts on padding.

    The invariant the whole hardening pass exists for: a renderer that ignores
    `textLength` or cannot resolve the font still lands every run on its column,
    because no glyph is positioned by the width of the spaces preceding it.
    """
    pads = tuple(PADDING)
    for svg in (
        *(
            (ASSETS / capture.filename).read_text(encoding="utf-8")
            for capture in COMMITTED_CAPTURES
        ),
        harden_svg(_rich_svg(SAMPLE_CAPTURE, columns=40, title="", unique_id="s")),
    ):
        for element in _TEXT_ELEMENT_RE.finditer(svg):
            content = unescape(element["content"])
            # Runs carrying no glyph (the newline ending each line) are left
            # alone, having no column of their own to land on.
            if content.strip(PADDING):
                assert not content.startswith(pads), f"padded run: {content!r}"


def test_capture_output_forces_color_and_pins_width(monkeypatch):
    """A capture overrides the environment's color opt-out and terminal width."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "999")

    process = capture_output(
        [
            sys.executable,
            "-c",
            (
                "import os; print(os.environ['FORCE_COLOR'], os.environ['COLUMNS'], "
                "os.environ.get('NO_COLOR', 'cleared'))"
            ),
        ],
        columns=57,
    )

    assert process.returncode == 0
    assert process.stdout.split() == ["1", "57", "cleared"]
    # The override is scoped to the capture and restored on the way out.
    assert os.environ["NO_COLOR"] == "1"


def test_capture_output_keeps_stderr_out_unless_asked():
    """Only `stdout` is captured by default, so a wrapper's chatter stays out."""
    args = [
        sys.executable,
        "-c",
        "import sys; print('kept'); print('noise', file=sys.stderr)",
    ]
    assert capture_output(args).stdout.split() == ["kept"]
    assert sorted(capture_output(args, merge_stderr=True).stdout.split()) == [
        "kept",
        "noise",
    ]


@pytest.mark.parametrize(
    "capture",
    COMMITTED_CAPTURES,
    ids=tuple(capture.filename for capture in COMMITTED_CAPTURES),
)
def test_committed_capture_matches_cli(capture):
    """Every committed capture still pictures what its command prints today.

    The capture is reshot through {func}`~click_extra.screenshot.capture_svg`,
    the very pipeline that produced the committed file, and the two are compared
    as terminal text. Going through the whole pipeline rather than against the
    command's raw output is what keeps the check honest on both counts the two
    differ:

    - a command wrapping to an 80-column terminal is handed
      `min(columns, max_width) - 2`, while Click's own `CliRunner` pins
      `FORCED_WIDTH` to 80, so an in-process render sits two columns wider;
    - the renderer folds a line longer than the terminal, exactly as a terminal
      does, so a help screen carrying an unwrappable option list (`--table-format`
      and its 463-character choice list) occupies more rows in the image than the
      command printed.

    Only the text is compared, so restyling a theme does not redden this.
    """
    committed = (ASSETS / capture.filename).read_text(encoding="utf-8")

    fresh, returncode = capture_svg(
        list(capture.command),
        columns=capture.columns,
        prompt=capture.prompt.removeprefix("$ "),
        head=capture.head,
    )
    assert returncode == 0
    assert svg_to_lines(committed) == svg_to_lines(fresh)
