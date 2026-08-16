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
    CAPTURE_BORDERS,
    CAPTURE_FOREGROUND,
    CAPTURE_SHADOWS,
    CAPTURE_TERMINAL_HINTS,
    DEFAULT_COLUMNS,
    LIGHT_CAPTURE_BACKGROUND,
    LIGHT_CAPTURE_FOREGROUND,
    MIN_COLUMNS,
    NO_PAINT,
    OPAQUE,
    PADDING,
    TITLEBAR_HEIGHT,
    CaptureBackground,
    CaptureFormat,
    _rich_svg,
    capture,
    capture_output,
    fit_columns,
    format_from_path,
    gradient_svg,
    harden_svg,
    measure_cell_width,
    number_lines,
    palette_theme,
    render,
    trim_lines,
    window_buttons,
)
from click_extra.screenshot_presets import PRESETS

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

    background: CaptureBackground = CaptureBackground.DARK
    """Chrome it was drawn on, which is also the terminal it was told it ran in."""

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
    Capture("auto-theme-dark-screen.svg", ("--theme", "auto", "themes", "--help")),
    Capture(
        "auto-theme-light-screen.svg",
        ("--theme", "auto", "themes", "--help"),
        background=CaptureBackground.LIGHT,
    ),
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


@pytest.mark.parametrize("background", CaptureBackground)
def test_capture_output_states_the_terminal_it_simulates(background, monkeypatch):
    """The chrome reaches the command as the variables a terminal would set.

    Which is what lets a CLI asking for `--theme auto` render for the window its
    capture lands in, instead of falling back to dark inside a light one.
    """
    monkeypatch.delenv("CLITHEME", raising=False)
    monkeypatch.delenv("COLORFGBG", raising=False)

    process = capture_output(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ['CLITHEME'], os.environ['COLORFGBG'])",
        ],
        background=background,
    )
    hints = CAPTURE_TERMINAL_HINTS[background]
    assert process.stdout.split() == [hints["CLITHEME"], hints["COLORFGBG"]]


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
        background=committed.background,
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


def svg_box(svg: str) -> tuple[float, float]:
    """The width and height of a rendered capture's own box."""
    match = re.search(r'viewBox="0 0 (?P<width>[\d.]+) (?P<height>[\d.]+)"', svg)
    assert match
    return (float(match["width"]), float(match["height"]))


def svg_window(svg: str) -> tuple[float, float]:
    """The width and height of the terminal window drawn in a capture."""
    match = re.search(
        r'<rect [^>]*width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)" rx=', svg
    )
    assert match
    return (float(match["w"]), float(match["h"]))


@pytest.mark.parametrize("background", CaptureBackground)
def test_render_frames_with_a_border_its_chrome_can_show(background):
    """Each chrome frames its window in something its own background shows.

    The regression this guards is a light capture keeping the translucent white
    a dark renderer draws by default: a white window on a white page, whose
    shape is left for the reader to infer from the text inside it.
    """
    svg = render("kiwi", unique_id="fruit", background=background)
    assert f'stroke="{CAPTURE_BORDERS[background]}"' in svg
    assert f'flood-color="{CAPTURE_SHADOWS[background]}"' in svg


def test_frame_svg_paints_what_it_is_given():
    """A caller's own frame and shadow reach the window."""
    svg = render("kiwi", unique_id="fruit", border="red", shadow="blue")
    assert 'stroke="red"' in svg
    assert 'flood-color="blue"' in svg
    assert 'filter="url(#fruit-shadow)"' in svg


def test_frame_svg_restates_the_whole_window():
    """Corner radius, frame thickness, backdrop and title all reach the source."""
    svg = render(
        "kiwi",
        unique_id="fruit",
        title="caption",
        border="red",
        border_width=3,
        radius=0,
        backdrop="#1f6feb",
    )
    assert 'stroke-width="3"' in svg
    assert 'rx="0"' in svg
    assert '<rect fill="#1f6feb" x="0" y="0"' in svg
    # Drawn centered in the window's title bar, by the renderer itself.
    assert '<text class="fruit-title"' in svg
    assert 'text-anchor="middle"' in svg
    assert "caption" in svg
    # The backdrop covers the image, margin included, and sits under the window.
    assert svg.index('fill="#1f6feb"') < svg.index('stroke="red"')


@pytest.mark.parametrize(
    ("backdrop", "expected"),
    (
        # A plain color is left for the `fill` attribute to take verbatim.
        ("#1f6feb", None),
        ("rebeccapurple", None),
        ("rgba(0, 0, 0, 0.5)", None),
        # A gradient needs two stops to interpolate between.
        ("linear-gradient(#000)", None),
        ("linear-gradient(45deg)", None),
        # Both shapes, opening with an angle, a side, or nothing at all.
        ("linear-gradient(#000, #fff)", "linearGradient"),
        ("linear-gradient(135deg, #667eea, #764ba2)", "linearGradient"),
        ("linear-gradient(to bottom right, #000, #fff 30%, #888)", "linearGradient"),
        ("radial-gradient(rgba(0, 0, 0, 0.5), #fff)", "radialGradient"),
    ),
)
def test_gradient_svg(backdrop, expected):
    """A CSS gradient becomes a paint server; anything else stays a color."""
    translated = gradient_svg(backdrop, "fruit", 100, 50)
    if expected is None:
        assert translated is None
        return
    assert translated
    markup, paint = translated
    assert paint == "url(#fruit)"
    assert f'<{expected} id="fruit"' in markup
    # Every color the value named is carried over, in order.
    assert markup.count("<stop ") >= 2


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        # 90 degrees is `to right`: a horizontal line spanning the image's width.
        ("linear-gradient(90deg, #000, #fff)", 'x1="0" y1="25" x2="100" y2="25"'),
        # No direction at all means `to bottom`, spanning its height.
        ("linear-gradient(#000, #fff)", 'x1="50" y1="0" x2="50" y2="50"'),
        # A side keyword names the same angles.
        ("linear-gradient(to right, #000, #fff)", 'x1="0" y1="25" x2="100" y2="25"'),
    ),
)
def test_gradient_svg_places_the_line_in_user_space(value, expected):
    """The gradient line runs through the center, at the angle asked for."""
    translated = gradient_svg(value, "fruit", 100, 50)
    assert translated
    assert expected in translated[0]


def test_render_paints_a_gradient_backdrop():
    """A gradient backdrop reaches the capture as a declared paint server."""
    svg = render("kiwi", unique_id="fruit", backdrop="linear-gradient(#000, #fff)")
    assert '<linearGradient id="fruit-backdrop"' in svg
    assert '<rect fill="url(#fruit-backdrop)"' in svg


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("", ""),
        ("kiwi", ["1 │ kiwi"]),
        ("kiwi\nbanana", ["1 │ kiwi", "2 │ banana"]),
        # The gutter is one column wide whatever the tally reaches.
        ("\n".join("fruit" for _ in range(10))[:], None),
    ),
)
def test_number_lines(text, expected):
    """Each line gets its number, right-aligned on the widest one."""
    numbered = unstyle(number_lines(text))
    if expected == "":
        assert numbered == ""
    elif expected is not None:
        assert numbered.splitlines() == expected
    else:
        lines = numbered.splitlines()
        assert lines[0].startswith(" 1 │ ")
        assert lines[-1].startswith("10 │ ")


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_preset_catalog(name):
    """Every preset carries a full palette on both of its dresses."""
    preset = PRESETS[name]
    assert preset.label
    for palette in (preset.dark, preset.light):
        assert len(palette.ansi) == 16
        for color in (
            palette.background,
            palette.foreground,
            palette.titlebar,
            *palette.ansi,
        ):
            assert re.fullmatch(r"#[0-9a-f]{6}", color), color
    # A stack always ends on the family every renderer resolves.
    assert preset.font_stack.endswith("monospace")


def test_palette_theme_carries_the_colors_over():
    """A palette becomes the terminal theme a renderer resolves ANSI with."""
    theme = palette_theme(PRESETS["windows"].dark)
    assert theme.background_color.hex == "#0c0c0c"
    assert theme.foreground_color.hex == "#cccccc"
    # Campbell's bright blue, the thirteenth entry.
    assert theme.ansi_colors[12].hex == "#3b78ff"


@pytest.mark.parametrize(
    ("name", "expected", "unwanted"),
    (
        # Round buttons on the left, the colors Aqua paints them.
        ("macos", "<circle", "<text"),
        # Glyphs against the right edge, close last.
        ("windows", 'text-anchor="end"', "<circle"),
        ("linux", 'text-anchor="end"', "<circle"),
        # A window wearing none of it.
        ("plain", "", "<circle"),
    ),
)
def test_window_buttons(name, expected, unwanted):
    """Each preset draws the decorations its desktop does, or none at all."""
    markup = window_buttons(PRESETS[name].buttons, width=500, color="#ffffff")
    if expected:
        assert expected in markup
    else:
        assert markup == ""
    assert unwanted not in markup


def test_render_draws_the_preset_it_is_given():
    """A preset reaches the capture: its palette, its font, its decorations."""
    svg = render("kiwi", unique_id="fruit", preset=PRESETS["windows"])
    assert 'fill="#0c0c0c"' in svg
    assert "Cascadia Code" in svg
    assert 'text-anchor="end"' in svg
    assert "Fira Code" not in svg
    # Its square corners come along, unless the caller states otherwise.
    assert 'rx="0"' in svg
    assert 'rx="8"' in render(
        "kiwi", unique_id="fruit", preset=PRESETS["windows"], radius=8
    )


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_preset_paints_its_own_titlebar(name):
    """A window drawn as a desktop's carries that desktop's chrome on top."""
    preset = PRESETS[name]
    svg = render("kiwi", unique_id="fruit", preset=preset, title="Pantry")
    assert f'fill="{preset.dark.titlebar}"' in svg
    # Every desktop paints the strip a shade off the terminal it frames. Only
    # the preset mimicking no desktop leaves the two the same color.
    wears_chrome = preset.dark.titlebar != preset.dark.background
    assert wears_chrome is (name != "plain")


def test_titlebar_collapses_on_a_window_wearing_nothing():
    """An empty strip is dropped, and comes back as soon as it holds something."""
    bare, titled, decorated = (
        render("kiwi", unique_id="fruit", preset=PRESETS[name], title=title)
        for name, title in (("plain", ""), ("plain", "Pantry"), ("macos", ""))
    )
    boxes = [
        re.search(r'viewBox="0 0 [\d.]+ ([\d.]+)"', svg)
        for svg in (bare, titled, decorated)
    ]
    assert all(boxes)
    heights = [float(box[1]) for box in boxes if box]
    assert heights[0] == heights[1] - TITLEBAR_HEIGHT
    assert heights[1] == heights[2]


@pytest.mark.parametrize(
    ("format", "expected"),
    (
        (CaptureFormat.SVG, 'fill-opacity="0.4"'),
        (CaptureFormat.HTML, "color-mix(in srgb, #292929 40%, transparent)"),
    ),
)
def test_render_thins_the_window_out(format, expected):
    """Opacity below one lets whatever the capture sits on through its body."""
    thinned = render("kiwi", format=format, unique_id="fruit", opacity=0.4)
    assert expected in thinned
    # The text keeps its own paint whatever the body does.
    assert "kiwi" in thinned
    assert expected not in render(
        "kiwi", format=format, unique_id="fruit", opacity=OPAQUE
    )


def test_frame_svg_draws_neither_when_asked_for_neither():
    """`none` is the value that leaves the window bare."""
    svg = render("kiwi", unique_id="fruit", border=NO_PAINT, shadow=NO_PAINT)
    assert 'stroke="none"' in svg
    assert "feDropShadow" not in svg
    assert "filter=" not in svg


@pytest.mark.parametrize(
    ("margin", "padding"),
    ((0, 0), (16, 0), (0, 12), (10, 10)),
)
def test_frame_svg_geometry(margin, padding):
    """Margin grows the image alone; padding grows the window inside it too.

    Neither moves a glyph relative to the others: the capture is repositioned as
    a whole, so its text still reads back line by line.
    """
    bare = render("kiwi", unique_id="fruit", margin=0, padding=0)
    framed = render("kiwi", unique_id="fruit", margin=margin, padding=padding)

    grown = 2 * (margin + padding)
    assert svg_box(framed) == tuple(side + grown for side in svg_box(bare))
    assert svg_window(framed) == tuple(side + 2 * padding for side in svg_window(bare))
    assert svg_to_lines(framed) == svg_to_lines(bare)


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
