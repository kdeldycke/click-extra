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
import shutil
import sys
from html import unescape
from pathlib import Path
from typing import NamedTuple

import pytest

from click_extra import screenshot, unstyle
from click_extra.cli import screenshot_cmd
from click_extra.screenshot import (
    _TEXT_ELEMENT_RE,
    AUTO_COLUMNS,
    CAPTURE_BACKGROUND,
    CAPTURE_FOREGROUND,
    DEFAULT_COLUMNS,
    LIGHT_CAPTURE_BACKGROUND,
    LIGHT_CAPTURE_FOREGROUND,
    MIN_COLUMNS,
    PADDING,
    CaptureBackground,
    CaptureFormat,
    _rich_svg,
    capture,
    capture_output,
    fit_columns,
    format_from_path,
    harden_svg,
    measure_cell_width,
    render,
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
    Capture("theme-gallery-screen.svg", ("themes",), head=34),
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


def test_render_without_the_extra(monkeypatch):
    """Rendering without Rich installed names the extra that ships it."""
    monkeypatch.setattr(screenshot, "Console", None)
    with pytest.raises(ImportError, match=r"screenshot"):
        render(SAMPLE_CAPTURE)


def test_render_folds_an_unusable_unique_id():
    """A file name that is not a CSS identifier cannot leak into a class name."""
    svg = render(SAMPLE_CAPTURE, unique_id="my shot (v2).final")
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
            (ASSETS / committed.filename).read_text(encoding="utf-8")
            for committed in COMMITTED_CAPTURES
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
    "committed",
    COMMITTED_CAPTURES,
    ids=tuple(committed.filename for committed in COMMITTED_CAPTURES),
)
def test_committed_capture_matches_cli(committed):
    """Every committed capture still pictures what its command prints today.

    The capture is reshot through {func}`~click_extra.screenshot.capture`,
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
    source = (ASSETS / committed.filename).read_text(encoding="utf-8")

    fresh, returncode = capture(
        list(committed.command),
        columns=committed.columns,
        prompt=committed.prompt.removeprefix("$ "),
        head=committed.head,
    )
    assert returncode == 0
    assert svg_to_lines(source) == svg_to_lines(fresh)


@pytest.mark.parametrize(
    ("filename", "expected"),
    (
        ("shot.svg", CaptureFormat.SVG),
        ("shot.SVG", CaptureFormat.SVG),
        ("shot.html", CaptureFormat.HTML),
        # The older extension names the same document.
        ("shot.htm", CaptureFormat.HTML),
    ),
)
def test_format_from_path(filename, expected):
    """A capture's format is read off the file name it is written under."""
    assert format_from_path(Path(filename)) == expected


@pytest.mark.parametrize("filename", ("shot.png", "shot", "shot.svg.bak"))
def test_format_from_path_rejects_an_unknown_extension(filename):
    """An extension naming no format says which ones do."""
    with pytest.raises(ValueError, match=r"\.html, \.svg"):
        format_from_path(Path(filename))


@pytest.mark.parametrize(
    ("background", "expected", "unwanted"),
    (
        (
            CaptureBackground.DARK,
            (CAPTURE_BACKGROUND, CAPTURE_FOREGROUND),
            (LIGHT_CAPTURE_BACKGROUND,),
        ),
        (
            CaptureBackground.LIGHT,
            (LIGHT_CAPTURE_BACKGROUND, LIGHT_CAPTURE_FOREGROUND),
            (CAPTURE_BACKGROUND,),
        ),
    ),
    ids=("dark", "light"),
)
@pytest.mark.parametrize("format", (CaptureFormat.HTML, CaptureFormat.SVG))
def test_render_draws_on_the_chrome_it_is_given(format, background, expected, unwanted):
    """Both renderers answer to the chrome, so a light capture stays readable.

    The colors are the contract: an SVG paints its window rect with them, and an
    HTML capture inlines them on its `<pre>`.
    """
    document = render("kiwi", format=format, background=background)
    for color in expected:
        assert color in document
    for color in unwanted:
        assert color not in document


def test_render_html_escapes_the_captured_text():
    """Markup a CLI prints is escaped, not handed to the browser as markup.

    The load-bearing test of the HTML renderer: `ansi_to_html()` translates ANSI
    and copies everything else verbatim, so a caller skipping the escape turns
    click-extra's own `--export-config` help, which says it writes `to <stdout>`,
    into an unclosed tag.
    """
    html = render(
        "plain <stdout> & \x1b[31mstyled <b>bold</b>\x1b[0m",
        format=CaptureFormat.HTML,
    )
    assert "&lt;stdout&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html
    assert "&amp;" in html
    # The only tags are the ones the renderer emits itself.
    assert "<stdout>" not in html
    assert "<b>" not in html


def test_render_html_round_trips_the_terminal_text():
    """Stripping the markup back off returns exactly what the CLI printed.

    The HTML counterpart of {func}`svg_to_lines`: it catches a dropped
    character, a mangled escape and a stray tag in one assertion.
    """
    html = render(SAMPLE_CAPTURE, format=CaptureFormat.HTML)
    body = html[html.index("<pre") : html.index("</pre>")]
    text = unescape(re.sub(r"<[^>]+>", "", body))
    assert text == unstyle(SAMPLE_CAPTURE)


def test_render_html_fragment_is_self_contained():
    """A fragment carries its own styling, and no document scaffolding."""
    fragment = render(SAMPLE_CAPTURE, format=CaptureFormat.HTML, full=False)
    assert fragment.startswith("<pre style=")
    assert fragment.endswith("</pre>")
    assert "<!doctype" not in fragment.lower()
    # Inline styling means a host page needs to supply no stylesheet.
    assert CAPTURE_BACKGROUND in fragment
    assert CAPTURE_FOREGROUND in fragment


def test_render_html_document_wraps_the_fragment():
    """A full document is the fragment plus scaffolding, nothing else."""
    fragment = render(SAMPLE_CAPTURE, format=CaptureFormat.HTML, full=False)
    document = render(SAMPLE_CAPTURE, format=CaptureFormat.HTML, title="Fruit <&> veg")
    assert document.lower().startswith("<!doctype html>")
    assert fragment in document
    # The title is escaped like any other text.
    assert "<title>Fruit &lt;&amp;&gt; veg</title>" in document


def test_render_html_quotes_survive_the_style_attribute():
    """The font stack cannot terminate the `style` attribute it sits in.

    A double-quoted family name would close the attribute early and spill CSS
    into the markup, so the stack is single-quoted.
    """
    fragment = render(SAMPLE_CAPTURE, format=CaptureFormat.HTML, full=False)
    opening = fragment[: fragment.index(">") + 1]
    assert opening.count('"') == 2, f"unbalanced quoting: {opening}"
    assert "monospace" in opening


def test_render_html_needs_no_extra(monkeypatch):
    """HTML renders with Rich absent: only SVG is behind the extra."""
    monkeypatch.setattr(screenshot, "Console", None)
    assert "banana" in render(SAMPLE_CAPTURE, format=CaptureFormat.HTML)


def html_to_text(markup: str) -> str:
    """Strip a capture's markup back off, leaving the terminal text."""
    body = markup[markup.index("<pre") : markup.index("</pre>")]
    return unescape(re.sub(r"<[^>]+>", "", body))


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        # Nothing to measure still asks for a picture glyphs fit in.
        ("", MIN_COLUMNS),
        ("kiwi", MIN_COLUMNS),
        ("k" * 40, 40),
        ("kiwi\n" + "banana " * 10, 70),
        # An escape styles the glyphs around it and occupies no cell.
        ("\x1b[31m" + "cherry" * 6 + "\x1b[0m", 36),
    ),
)
def test_fit_columns(text, expected):
    """The width `auto` resolves to is the longest line, floored."""
    assert fit_columns(text) == expected


def test_render_auto_columns_folds_nothing():
    """`auto` lays the image out at what the text asks for.

    A line the command does not wrap on its own (a prompt, a wide table) is
    folded by a pinned width and kept whole by this one.
    """
    text = "banana " * 20
    assert svg_to_lines(render(text, columns=AUTO_COLUMNS)) == [text.rstrip()]
    assert len(svg_to_lines(render(text, columns=DEFAULT_COLUMNS))) > 1


@pytest.mark.parametrize(
    ("value", "message"),
    (
        ("wide", "neither an integer"),
        ("4", "narrower than"),
    ),
)
def test_screenshot_rejects_an_unusable_width(invoke, tmp_path, value, message):
    """`--columns` takes a width or the one word standing for none of them."""
    result = invoke(
        screenshot_cmd,
        ["--columns", value, "--output", str(tmp_path / "shot.svg"), "--", "echo"],
    )
    assert result.exit_code != 0
    assert message in result.output


def test_screenshot_wrap_needs_the_console_script(invoke, monkeypatch, tmp_path):
    """`--wrap` refuses to re-enter through anything but the installed command.

    `python -m click_extra` resolves a target differently, so falling back to it
    would capture a different CLI than the composition it stands for. Better to
    say so than to quietly picture the wrong thing.
    """
    monkeypatch.setattr(shutil, "which", lambda _: None)
    result = invoke(
        screenshot_cmd,
        ["--wrap", "--output", str(tmp_path / "shot.svg"), "--", "mkdocs", "--help"],
    )
    assert result.exit_code != 0
    assert "click-extra wrap -- TARGET" in result.output


@pytest.mark.skipif(
    shutil.which("click-extra") is None,
    reason="--wrap re-enters through the installed console script",
)
def test_screenshot_wrap_matches_the_composition(invoke, tmp_path):
    """`--wrap` is the nested composition, spelled as a flag.

    Captured both ways, the terminal text has to match: the flag is a shortcut,
    not a second way of rendering.
    """
    target = ("click_extra.cli:demo_themes", "--help")
    shortcut = tmp_path / "shortcut.html"
    composed = tmp_path / "composed.html"

    assert (
        invoke(
            screenshot_cmd,
            [
                "--wrap",
                "--fragment",
                "--head",
                "3",
                "--output",
                str(shortcut),
                "--",
                *target,
            ],
        ).exit_code
        == 0
    )
    assert (
        invoke(
            screenshot_cmd,
            [
                "--fragment",
                "--head",
                "3",
                "--prompt",
                f"click-extra wrap -- {' '.join(target)}",
                "--output",
                str(composed),
                "--",
                shutil.which("click-extra"),
                "wrap",
                "--",
                *target,
            ],
        ).exit_code
        == 0
    )

    text = html_to_text(shortcut.read_text(encoding="utf-8"))
    assert text == html_to_text(composed.read_text(encoding="utf-8"))
    # The prompt shows what a reader types, not the plumbing that ran.
    assert (
        text.splitlines()[0]
        == "$ click-extra wrap -- click_extra.cli:demo_themes --help"
    )
