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

"""Tests for `click_extra.snippet`.

A snippet rides the screenshot renderer, so this module tests the step that is
new: the colors a Pygments style hands over, and the shape of the text it hands
them on. What the renderer then does with that text is covered by
`test_screenshots.py`, and is deliberately not re-tested here.
"""

from __future__ import annotations

import re
from functools import partial

import pytest
from click import Command, Option, unstyle
from pygments.styles import get_style_by_name
from pygments.token import Token

from click_extra.cli import capture_options, screenshot_cmd, snippet_cmd
from click_extra.screenshot import (
    AUTO_COLUMNS,
    CAPTURE_PALETTES,
    DEFAULT_COLUMNS,
    CaptureBackground,
    CaptureFormat,
)
from click_extra.screenshot_presets import PRESETS
from click_extra.snippet import (
    DEFAULT_SYNTAX_STYLES,
    TAB_WIDTH,
    highlight_code,
    known_styles,
    render_snippet,
    resolve_lexer,
    resolve_style,
    style_palette,
)
from click_extra.styling import split_ansi

from .test_screenshots import svg_to_lines

SAMPLE = 'def ripen(fruit, days=3):\n    """Wait for the mango."""\n    return fruit\n'
"""A few lines of Python exercising keywords, strings and punctuation."""

WINDOW_RE = re.compile(r'<rect fill="(?P<paint>#[0-9a-f]{6})" stroke=')
"""The window's own rectangle, whose fill is the terminal's background."""


def window_paint(svg: str) -> str:
    """The background color a rendered snippet's window is filled with."""
    match = WINDOW_RE.search(svg)
    assert match
    return match["paint"]


@pytest.mark.parametrize("background", CaptureBackground)
def test_snippet_wears_the_style_background(background):
    """The window is painted the background the syntax style was designed for.

    A style states the surface its colors were chosen against, and drawn on any
    other one it is a picture of that style in a window it was never meant for.
    """
    style = DEFAULT_SYNTAX_STYLES[background]
    svg = render_snippet(SAMPLE, language="python", background=background)
    assert window_paint(svg) == get_style_by_name(style).background_color


def test_snippet_style_beats_the_preset_chrome():
    """A preset dresses the window; the style still paints its body.

    The two answer different questions, so a snippet wearing a terminal's
    decorations keeps the colors its code was highlighted with.
    """
    svg = render_snippet(
        SAMPLE,
        language="python",
        style="monokai",
        preset=PRESETS["plain"],
    )
    assert window_paint(svg) == get_style_by_name("monokai").background_color


@pytest.mark.parametrize("style", known_styles())
def test_every_style_paints_a_readable_window(style):
    """Every style Pygments ships renders, and states a background and an ink.

    A conformance sweep rather than a spot check: the palette is built from two
    attributes a style is free to leave unset, and the fallback for each has to
    hold across the whole catalog.
    """
    palette = style_palette(style, CaptureBackground.DARK)
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", palette.background)
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", palette.foreground)
    assert palette.background != palette.foreground


def test_style_without_text_color_keeps_the_chrome_ink():
    """A style naming no color for plain text falls back to the chrome's own.

    Twenty-five of the styles Pygments ships are in this case, all of them light
    ones whose code is meant to be black.
    """
    assert not get_style_by_name("default").style_for_token(Token.Text)["color"]
    light = style_palette("default", CaptureBackground.LIGHT)
    assert light.foreground == "#000000"


def test_snippet_carries_the_style_colors_into_the_picture():
    """The colors a style names reach the rendered document.

    The whole premise of the module: Pygments writes true-color ANSI, which is
    the interchange format the renderer already reads.
    """
    keyword = get_style_by_name("monokai").style_for_token(Token.Keyword)["color"]
    svg = render_snippet(SAMPLE, language="python", style="monokai")
    assert f"#{keyword}" in svg


def test_highlight_expands_tabs():
    """A tab becomes spaces before the snippet is laid out.

    It has no width on a character grid, so one reaching the renderer takes the
    whole line's measurement down with it.
    """
    colored = highlight_code("\tfruit\n", language="python")
    assert "\t" not in colored
    assert " " * TAB_WIDTH in "".join(run for _, run in split_ansi(colored))


def test_snippet_draws_the_lines_it_was_given():
    """The code comes back out of the picture, character for character."""
    svg = render_snippet(SAMPLE, language="python", watermark="")
    assert svg_to_lines(svg) == SAMPLE.rstrip("\n").split("\n")


def test_snippet_numbers_its_lines():
    """A numbered snippet counts from one, in a gutter of its own."""
    lines = svg_to_lines(
        render_snippet(SAMPLE, language="python", line_numbers=True, watermark=""),
    )
    assert lines[0].startswith("1 │ ")
    assert lines[-1].startswith("3 │ ")


def test_snippet_renders_the_same_bytes_twice():
    """Nothing in a snippet is timed, sampled or ordered by chance.

    Which is what lets a documentation build rewrite a committed asset and leave
    the working tree clean.
    """
    shot = partial(
        render_snippet,
        SAMPLE,
        language="python",
        unique_id="ripen",
        title="ripen.py",
        emphasize=(2,),
    )
    assert shot() == shot()


@pytest.mark.parametrize(
    ("language", "filename", "expected"),
    (
        ("python", None, "Python"),
        ("python", "mango.js", "Python"),
        (None, "mango.py", "Python"),
        (None, "recipe.json", "JSON"),
        (None, None, None),
    ),
)
def test_resolve_lexer(language, filename, expected):
    """A stated language wins over a file name, which wins over a guess."""
    lexer = resolve_lexer(SAMPLE, language=language, filename=filename)
    if expected is not None:
        assert lexer.name == expected


def test_unknown_language_is_an_error():
    """A misspelled language fails loudly rather than drawing plain text.

    A typo swallowed here would surface as an uncolored picture nobody re-reads.
    """
    with pytest.raises(ValueError, match="not a language Pygments knows"):
        resolve_lexer(SAMPLE, language="pythn")


def test_unknown_style_is_an_error():
    """A misspelled style names the ones that exist."""
    with pytest.raises(ValueError, match="not a style Pygments knows"):
        resolve_style("monokia", CaptureBackground.DARK)


@pytest.mark.parametrize("background", CaptureBackground)
def test_style_defaults_to_the_chrome(background):
    """Naming no style takes the one the chrome is drawn for."""
    assert resolve_style(None, background) == DEFAULT_SYNTAX_STYLES[background]


@pytest.mark.parametrize("background", CaptureBackground)
def test_default_style_sits_close_to_the_capture_chrome(background):
    """The default style's background is a near match for a capture's own.

    The reason these two were picked: a snippet and a terminal capture sharing a
    page must not show a step between their windows.
    """
    chrome = CAPTURE_PALETTES[background].background
    style = get_style_by_name(DEFAULT_SYNTAX_STYLES[background]).background_color
    distance = max(
        abs(int(chrome[index : index + 2], 16) - int(style[index : index + 2], 16))
        for index in (1, 3, 5)
    )
    assert distance <= 16


def test_snippet_renders_html():
    """The HTML format carries the style's colors too."""
    document = render_snippet(SAMPLE, language="python", format=CaptureFormat.HTML)
    assert get_style_by_name("monokai").background_color in document


def shared_option_names() -> tuple[str, ...]:
    """Every option name {func}`~click_extra.cli.capture_options` attaches.

    Read off a bare function the decorator is applied to, rather than restated
    here: a list written out by hand is one more place for the two commands to
    drift apart, which is the thing this is here to catch.
    """

    def probe() -> None:
        pass

    decorated = capture_options(columns_help="")(probe)
    params: list[Option] = decorated.__click_params__  # type: ignore[attr-defined]
    return tuple(str(param.name) for param in params)


def options_of(cmd: Command) -> dict[str, Option]:
    """The command's options, keyed by the name they bind to."""
    return {
        str(param.name): param
        for param in cmd.params
        if isinstance(param, Option) and param.name
    }


def test_capture_commands_share_one_vocabulary():
    """Both capture commands spell every shared option the same way.

    The drift this guards against is silent and lands on the reader rather than
    the maintainer: an option learned on one command that means something else,
    or nothing at all, on the other.

    `--columns` is the deliberate exception. Its whole purpose is to differ:
    a command wraps its own output to it, where a file was never wrapped.
    """
    shot = options_of(screenshot_cmd)
    snippet = options_of(snippet_cmd)
    for name in shared_option_names():
        assert name in shot, f"screenshot lost the shared --{name}"
        assert name in snippet, f"snippet lost the shared --{name}"
        if name == "columns":
            continue
        assert shot[name].help == snippet[name].help
        assert shot[name].default == snippet[name].default
        assert shot[name].opts == snippet[name].opts
        assert type(shot[name].type) is type(snippet[name].type)


def test_columns_defaults_differ_by_command():
    """A snippet sizes itself to its longest line; a capture pins a width."""
    shot = next(param for param in screenshot_cmd.params if param.name == "columns")
    snippet = next(param for param in snippet_cmd.params if param.name == "columns")
    assert shot.default == str(DEFAULT_COLUMNS)
    assert snippet.default == AUTO_COLUMNS


def test_snippet_command_writes_a_capture(invoke, tmp_path):
    """The command colors a file and writes the picture where it was told."""
    source = tmp_path / "ripen.py"
    source.write_text(SAMPLE, encoding="utf-8")
    output = tmp_path / "ripen.svg"
    result = invoke(snippet_cmd, ["--output", str(output), str(source)])
    assert result.exit_code == 0
    assert svg_to_lines(output.read_text(encoding="utf-8")) == SAMPLE.rstrip(
        "\n"
    ).split("\n")


def test_snippet_command_reads_stdin(invoke, tmp_path):
    """A dash reads the source from stdin, where no file name identifies it."""
    output = tmp_path / "ripen.svg"
    result = invoke(
        snippet_cmd,
        ["--output", str(output), "--language", "python", "-"],
        input=SAMPLE,
    )
    assert result.exit_code == 0
    assert output.exists()


def test_snippet_command_rejects_a_fragment_image(invoke, tmp_path):
    """`--fragment` is an HTML notion: an SVG has no page to be pasted into."""
    source = tmp_path / "ripen.py"
    source.write_text(SAMPLE, encoding="utf-8")
    result = invoke(
        snippet_cmd,
        ["--output", str(tmp_path / "ripen.svg"), "--fragment", str(source)],
    )
    assert result.exit_code != 0
    assert "--fragment only applies" in result.output


def test_snippet_command_reports_an_unknown_language(invoke, tmp_path):
    """A misspelled language is a clean CLI error, not a traceback."""
    source = tmp_path / "ripen.py"
    source.write_text(SAMPLE, encoding="utf-8")
    result = invoke(
        snippet_cmd,
        ["--output", str(tmp_path / "ripen.svg"), "--language", "pythn", str(source)],
    )
    assert result.exit_code != 0
    assert "not a language Pygments knows" in result.output


def test_snippet_prints_ansi_to_stdout(invoke, tmp_path):
    """A dash target prints the escape sequences a terminal paints.

    The one target that needs no rendering: what a terminal reads is the stream
    the capture was carried in all along.
    """
    source = tmp_path / "ripen.py"
    source.write_text(SAMPLE, encoding="utf-8")
    result = invoke(snippet_cmd, ["--output", "-", "--color=always", str(source)])
    assert result.exit_code == 0
    assert "\x1b[38;2;" in result.stdout
    assert unstyle(result.stdout).rstrip("\n") == SAMPLE.rstrip("\n")
    # No window was drawn, so none of the markup a picture carries is present.
    assert "<svg" not in result.stdout
    assert "<pre" not in result.stdout


def test_snippet_stdout_strips_color_when_piped(invoke, tmp_path):
    """Piped, the escapes go and the code stays.

    The reason this routes through `echo` rather than a bare write: a redirect
    that captured raw escape sequences would produce a file nobody can read.
    """
    source = tmp_path / "ripen.py"
    source.write_text(SAMPLE, encoding="utf-8")
    result = invoke(snippet_cmd, ["--output", "-", str(source)], color=False)
    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout
    assert result.stdout.rstrip("\n") == SAMPLE.rstrip("\n")


def test_snippet_stdout_closes_on_one_newline(invoke, tmp_path):
    """Exactly one, so the next prompt does not land on the last row."""
    source = tmp_path / "ripen.py"
    source.write_text(SAMPLE, encoding="utf-8")
    result = invoke(snippet_cmd, ["--output", "-", str(source)], color=False)
    assert result.stdout.endswith("\n")
    assert not result.stdout.endswith("\n\n")


def test_snippet_writes_an_ansi_file(invoke, tmp_path):
    """The `.ansi` extension names the same format, written out."""
    source = tmp_path / "ripen.py"
    source.write_text(SAMPLE, encoding="utf-8")
    output = tmp_path / "ripen.ansi"
    result = invoke(snippet_cmd, ["--output", str(output), str(source)])
    assert result.exit_code == 0
    assert "\x1b[38;2;" in output.read_text(encoding="utf-8")
