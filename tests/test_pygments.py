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

from __future__ import annotations

import sys
import tarfile
from importlib import metadata
from operator import itemgetter
from pathlib import Path

import pytest
import requests
from boltons.strutils import camel2under
from boltons.typeutils import issubclass
from pygments import highlight
from pygments.filter import Filter
from pygments.filters import get_filter_by_name
from pygments.formatter import Formatter
from pygments.formatters import get_formatter_by_name
from pygments.lexer import Lexer
from pygments.lexers import find_lexer_class_by_name, get_lexer_by_name
from pygments.token import Text, Token

from click_extra import pygments as extra_pygments
from click_extra.colorize import _nearest_256
from click_extra.pygments import (
    _ANSI_STYLES,
    _NAMED_COLORS,
    _PALETTE_256,
    _SGR_ATTR_ON,
    DEFAULT_TOKEN_TYPE,
    EXTRA_ANSI_CSS,
    LEXER_MAP,
    Ansi,
    AnsiColorLexer,
    AnsiFilter,
    AnsiHtmlFormatter,
    _AnsiLinkEnd,
    _AnsiLinkStart,
    collect_session_lexers,
)

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]


PROJECT_ROOT = Path(__file__).parent.parent


# --- Helpers ---


def lex(text: str) -> list[tuple]:
    """Shorthand: lex ``text`` and return ``(token_type, value)`` pairs."""
    return list(AnsiColorLexer().get_tokens(text))


def collect_classes(klass, prefix="Ansi"):
    """Returns all classes defined in ``click_extra.pygments`` that are a subclass of
    ``klass``, and whose name starts with the provided ``prefix``."""
    return {
        name: var
        for name, var in extra_pygments.__dict__.items()
        if issubclass(var, klass) and name.startswith(prefix)
    }


def get_pyproject_section(*section_path: str) -> dict[str, str]:
    """Descends into the TOML tree of ``pyproject.toml`` to reach the value specified by
    ``section_path``."""
    toml_path = PROJECT_ROOT.joinpath("pyproject.toml").resolve()
    section: dict = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    for section_id in section_path:
        section = section[section_id]
    return section


def check_entry_points(entry_points: dict[str, str], *section_path: str) -> None:
    entry_points = dict(sorted(entry_points.items(), key=itemgetter(0)))
    project_entry_points = get_pyproject_section(*section_path)
    assert project_entry_points == entry_points


# --- Entry point and registration tests ---


@pytest.mark.network
@pytest.mark.once
def test_ansi_lexers_candidates(tmp_path):
    """Look into Pygments test suite to find all ANSI lexers candidates.

    Good candidates for ANSI colorization are lexers that are producing
    ``Generic.Output`` tokens, which are often used by REPL-like and scripting
    terminal to render text in a console.

    The list is manually maintained in Click Extra code, and this test is here to
    detect new candidates from new releases of Pygments.

    .. attention::
        The Pygments source code is downloaded from GitHub in the form of an archive,
        and extracted in a temporary folder.

        The version of Pygments used for this test is the one installed in the current
        environment.

    .. danger:: Security check
        While extracting the archive, we double check we are not fed an archive
        exploiting relative ``..`` or ``.`` path attacks.
    """
    version = metadata.version("pygments")

    source_url = (
        f"https://github.com/pygments/pygments/archive/refs/tags/{version}.tar.gz"
    )
    base_folder = f"pygments-{version}"
    archive_path = tmp_path / f"{base_folder}.tar.gz"

    # Download the source distribution from GitHub.
    with requests.get(source_url) as response:
        assert response.ok
        archive_path.write_bytes(response.content)

    assert archive_path.exists()
    assert archive_path.is_file()
    assert archive_path.stat().st_size > 0

    # Locations of lexer artifacts in test suite.
    parser_token_traces = {
        str(tmp_path / base_folder / "tests" / "examplefiles" / "*" / "*.output"),
        str(tmp_path / base_folder / "tests" / "snippets" / "*" / "*.txt"),
    }

    # Browse the downloaded package to find the test suite, and inspect the
    # traces of parsed tokens used as gold master for lexers tests.
    lexer_candidates = set()
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            # Skip non-test files.
            if not member.isfile():
                continue

            # XXX Security check of relative ``..`` or ``.`` path attacks.
            filename = tmp_path.joinpath(member.name).resolve()
            assert filename.is_relative_to(tmp_path)

            # Skip files that are not part of the test suite data.
            match = False
            for pattern in parser_token_traces:
                if filename.match(pattern):
                    match = True
                    break
            if not match:
                continue

            file = tar.extractfile(member)
            # Skip empty files.
            if not file:
                continue

            content = file.read().decode("utf-8")

            # Skip lexers that are rendering generic, terminal-like output tokens.
            if f" {'.'.join(DEFAULT_TOKEN_TYPE)}\n" not in content:
                continue

            # Extract lexer alias from the test file path.
            lexer_candidates.add(filename.parent.name)

    assert lexer_candidates
    lexer_classes = {find_lexer_class_by_name(alias) for alias in lexer_candidates}
    # We cannot test for strict equality yet, as some ANSI-ready lexers do not
    # have any test artifacts producing ``Generic.Output`` tokens.
    assert lexer_classes <= set(collect_session_lexers())


@pytest.mark.once
def test_formatter_entry_points():
    entry_points = {}
    for name in collect_classes(Formatter):
        entry_id = camel2under(name).replace("_", "-")
        entry_points[entry_id] = f"click_extra.pygments:{name}"

    check_entry_points(entry_points, "project", "entry-points", "pygments.formatters")


@pytest.mark.once
def test_filter_entry_points():
    entry_points = {}
    for name in collect_classes(Filter):
        entry_id = camel2under(name).replace("_", "-")
        entry_points[entry_id] = f"click_extra.pygments:{name}"

    check_entry_points(entry_points, "project", "entry-points", "pygments.filters")


@pytest.mark.once
def test_lexer_entry_points():
    entry_points = {}

    # The standalone AnsiColorLexer has its own entry point.
    entry_points["ansi-color"] = "click_extra.pygments:AnsiColorLexer"

    for lexer in collect_session_lexers():
        # Check an ANSI lexer variant is available for import from Click Extra.
        ansi_lexer_id = f"Ansi{lexer.__name__}"
        assert ansi_lexer_id in extra_pygments.__dict__

        # Transform ANSI lexer class ID into entry point ID.
        entry_id = "-".join(
            w for w in camel2under(ansi_lexer_id).split("_") if w != "lexer"
        )

        # Generate the lexer entry point.
        class_path = f"click_extra.pygments:{ansi_lexer_id}"
        entry_points[entry_id] = class_path

    check_entry_points(entry_points, "project", "entry-points", "pygments.lexers")


@pytest.mark.once
def test_registered_formatters():
    for klass in collect_classes(Formatter).values():
        for alias in klass.aliases:
            get_formatter_by_name(alias)


@pytest.mark.once
def test_registered_filters():
    for name in collect_classes(Filter):
        entry_id = camel2under(name).replace("_", "-")
        get_filter_by_name(entry_id)


@pytest.mark.once
def test_registered_lexers():
    for klass in collect_classes(Lexer).values():
        for alias in klass.aliases:
            get_lexer_by_name(alias)


# --- Plain text (no escapes) ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("hello", [(Text, "hello\n")], id="simple"),
        pytest.param("", [(Text, "\n")], id="empty"),
        pytest.param("line1\nline2", [(Text, "line1\nline2\n")], id="multiline"),
        pytest.param("tabs\there", [(Text, "tabs\there\n")], id="tabs"),
        pytest.param(
            "unicode: \u2603 \u2764",
            [(Text, "unicode: \u2603 \u2764\n")],
            id="unicode",
        ),
    ],
)
def test_plain_text(text, expected):
    """Plain text without escape sequences passes through unchanged."""
    assert lex(text) == expected


# --- Standard foreground colors (SGR 30-37) ---


@pytest.mark.parametrize(
    ("code", "color"),
    [
        (30, "Black"),
        (31, "Red"),
        (32, "Green"),
        (33, "Yellow"),
        (34, "Blue"),
        (35, "Magenta"),
        (36, "Cyan"),
        (37, "White"),
    ],
)
def test_sgr_fg_standard(code, color):
    """SGR 30-37 set standard foreground colors."""
    tokens = lex(f"\x1b[{code}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, color), "text")


# --- Standard background colors (SGR 40-47) ---


@pytest.mark.parametrize(
    ("code", "color"),
    [
        (40, "Black"),
        (41, "Red"),
        (42, "Green"),
        (43, "Yellow"),
        (44, "Blue"),
        (45, "Magenta"),
        (46, "Cyan"),
        (47, "White"),
    ],
)
def test_sgr_bg_standard(code, color):
    """SGR 40-47 set standard background colors."""
    tokens = lex(f"\x1b[{code}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, f"BG{color}"), "text")


# --- Bright foreground colors (SGR 90-97) ---


@pytest.mark.parametrize(
    ("code", "color"),
    [
        (90, "BrightBlack"),
        (91, "BrightRed"),
        (92, "BrightGreen"),
        (93, "BrightYellow"),
        (94, "BrightBlue"),
        (95, "BrightMagenta"),
        (96, "BrightCyan"),
        (97, "BrightWhite"),
    ],
)
def test_sgr_fg_bright(code, color):
    """SGR 90-97 set bright foreground colors."""
    tokens = lex(f"\x1b[{code}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, color), "text")


# --- Bright background colors (SGR 100-107) ---


@pytest.mark.parametrize(
    ("code", "color"),
    [
        (100, "BrightBlack"),
        (101, "BrightRed"),
        (102, "BrightGreen"),
        (103, "BrightYellow"),
        (104, "BrightBlue"),
        (105, "BrightMagenta"),
        (106, "BrightCyan"),
        (107, "BrightWhite"),
    ],
)
def test_sgr_bg_bright(code, color):
    """SGR 100-107 set bright background colors."""
    tokens = lex(f"\x1b[{code}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, f"BG{color}"), "text")


# --- Text attributes (SGR 1-9) ---


@pytest.mark.parametrize(
    ("code", "attr"),
    [
        (1, "Bold"),
        (2, "Faint"),
        (3, "Italic"),
        (4, "Underline"),
        (5, "Blink"),
        (7, "Reverse"),
        (9, "Strikethrough"),
        (53, "Overline"),
    ],
)
def test_sgr_text_attribute(code, attr):
    """SGR attribute codes set the corresponding text styling."""
    tokens = lex(f"\x1b[{code}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, attr), "text")


# --- Attribute resets (SGR 22-29) ---


@pytest.mark.parametrize(
    ("set_code", "reset_code", "attr"),
    [
        (1, 22, "Bold"),
        (2, 22, "Faint"),
        (3, 23, "Italic"),
        (4, 24, "Underline"),
        (5, 25, "Blink"),
        (7, 27, "Reverse"),
        (9, 29, "Strikethrough"),
        (53, 55, "Overline"),
    ],
)
def test_sgr_attribute_reset(set_code, reset_code, attr):
    """Each attribute can be individually reset by its specific SGR code."""
    tokens = lex(f"\x1b[{set_code}mON\x1b[{reset_code}mOFF\x1b[0m")
    assert tokens[0] == (getattr(Ansi, attr), "ON")
    assert tokens[1] == (Text, "OFF")


def test_sgr22_resets_bold_and_faint():
    """SGR 22 (normal intensity) resets both bold and faint simultaneously."""
    tokens = lex("\x1b[1;2mboth\x1b[22mnormal\x1b[0m")
    assert tokens[0] == (Ansi.Bold.Faint, "both")
    assert tokens[1] == (Text, "normal")


# --- SGR 0 and reset variants ---


def test_sgr0_resets_all():
    """SGR 0 resets all attributes and colors."""
    tokens = lex("\x1b[1;3;4;31;42mstyled\x1b[0mplain\x1b[0m")
    assert tokens[0] == (Ansi.Bold.Italic.Underline.Red.BGGreen, "styled")
    assert tokens[1] == (Text, "plain")


def test_empty_sgr_is_reset():
    """An empty SGR sequence (ESC [ m) is equivalent to SGR 0."""
    tokens = lex("\x1b[31mred\x1b[mplain")
    assert tokens[0] == (Ansi.Red, "red")
    assert tokens[1] == (Text, "plain\n")


# --- Default color resets (SGR 39, 49) ---


def test_sgr39_resets_foreground():
    """SGR 39 resets foreground color to default."""
    tokens = lex("\x1b[31mred\x1b[39mdefault")
    assert tokens[0] == (Ansi.Red, "red")
    assert tokens[1] == (Text, "default\n")


def test_sgr49_resets_background():
    """SGR 49 resets background color to default."""
    tokens = lex("\x1b[41mred-bg\x1b[49mdefault")
    assert tokens[0] == (Ansi.BGRed, "red-bg")
    assert tokens[1] == (Text, "default\n")


def test_sgr39_keeps_other_attributes():
    """SGR 39 only resets foreground; other attributes persist."""
    tokens = lex("\x1b[1;31mbold-red\x1b[39mbold-only\x1b[0m")
    assert tokens[0] == (Ansi.Bold.Red, "bold-red")
    assert tokens[1] == (Ansi.Bold, "bold-only")


# --- Combined SGR codes in a single sequence ---


@pytest.mark.parametrize(
    ("params", "expected_token"),
    [
        pytest.param("1;31", Ansi.Bold.Red, id="bold-red"),
        pytest.param("1;4;34", Ansi.Bold.Underline.Blue, id="bold-underline-blue"),
        pytest.param(
            "1;3;4;5;7;9;53;31;42",
            Ansi.Bold.Italic.Underline.Blink.Reverse.Strikethrough.Overline.Red.BGGreen,
            id="all-attributes",
        ),
        pytest.param("2;33", Ansi.Faint.Yellow, id="faint-yellow"),
        pytest.param("1;38;5;200", Ansi.Bold.C200, id="bold-256color"),
    ],
)
def test_sgr_combined(params, expected_token):
    """Multiple SGR codes in a single escape sequence are applied together."""
    tokens = lex(f"\x1b[{params}mtext\x1b[0m")
    assert tokens[0] == (expected_token, "text")


# --- 256-color indexed palette (SGR 38;5;n / 48;5;n) ---


@pytest.mark.parametrize(
    ("index",),
    [(0,), (15,), (16,), (128,), (231,), (232,), (255,)],
)
def test_256color_fg(index):
    """SGR 38;5;n sets foreground to 256-color index."""
    tokens = lex(f"\x1b[38;5;{index}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, f"C{index}"), "text")


@pytest.mark.parametrize(
    ("index",),
    [(0,), (15,), (128,), (255,)],
)
def test_256color_bg(index):
    """SGR 48;5;n sets background to 256-color index."""
    tokens = lex(f"\x1b[48;5;{index}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, f"BGC{index}"), "text")


# --- 24-bit RGB (SGR 38;2;r;g;b / 48;2;r;g;b) ---


def lex_quantized(text: str) -> list[tuple]:
    """Shorthand: lex ``text`` with explicit 256-color quantization opt-in."""
    return list(AnsiColorLexer(true_color=False).get_tokens(text))


@pytest.mark.parametrize(
    ("r", "g", "b", "expected_idx"),
    [
        pytest.param(255, 0, 0, 196, id="pure-red"),
        pytest.param(0, 255, 0, 46, id="pure-green"),
        pytest.param(0, 0, 255, 21, id="pure-blue"),
        pytest.param(0, 0, 0, 16, id="black"),
        pytest.param(255, 255, 255, 231, id="white"),
        pytest.param(128, 128, 128, 244, id="gray-quantizes-to-grayscale"),
        pytest.param(255, 128, 0, 208, id="orange"),
    ],
)
def test_24bit_rgb_fg_quantized(r, g, b, expected_idx):
    """SGR 38;2;r;g;b quantizes to nearest 256-color index when true_color=False."""
    tokens = lex_quantized(f"\x1b[38;2;{r};{g};{b}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, f"C{expected_idx}"), "text")


@pytest.mark.parametrize(
    ("r", "g", "b", "expected_idx"),
    [
        pytest.param(255, 0, 0, 196, id="pure-red-bg"),
        pytest.param(128, 128, 128, 244, id="gray-bg"),
    ],
)
def test_24bit_rgb_bg_quantized(r, g, b, expected_idx):
    """SGR 48;2;r;g;b quantizes background to nearest 256-color index when true_color=False."""
    tokens = lex_quantized(f"\x1b[48;2;{r};{g};{b}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, f"BGC{expected_idx}"), "text")


# --- 24-bit true-color mode ---


def lex_truecolor(text: str) -> list[tuple]:
    """Shorthand: lex ``text`` with true-color enabled."""
    return list(AnsiColorLexer(true_color=True).get_tokens(text))


@pytest.mark.parametrize(
    ("r", "g", "b", "expected_hex"),
    [
        pytest.param(255, 0, 0, "ff0000", id="pure-red"),
        pytest.param(0, 255, 0, "00ff00", id="pure-green"),
        pytest.param(255, 165, 0, "ffa500", id="orange"),
        pytest.param(1, 2, 3, "010203", id="low-channels-zero-padded"),
    ],
)
def test_truecolor_fg_preserves_hex(r, g, b, expected_hex):
    """With ``true_color=True``, SGR 38;2;r;g;b emits ``Token.Ansi.FG_{hex}``."""
    tokens = lex_truecolor(f"\x1b[38;2;{r};{g};{b}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, f"FG_{expected_hex}"), "text")


@pytest.mark.parametrize(
    ("r", "g", "b", "expected_hex"),
    [
        pytest.param(255, 0, 0, "ff0000", id="pure-red-bg"),
        pytest.param(128, 128, 128, "808080", id="gray-bg"),
    ],
)
def test_truecolor_bg_preserves_hex(r, g, b, expected_hex):
    """With ``true_color=True``, SGR 48;2;r;g;b emits ``Token.Ansi.BG_{hex}``."""
    tokens = lex_truecolor(f"\x1b[48;2;{r};{g};{b}mtext\x1b[0m")
    assert tokens[0] == (getattr(Ansi, f"BG_{expected_hex}"), "text")


def test_truecolor_combined_fg_and_bg():
    """Foreground and background 24-bit RGB combine into a single compound token."""
    tokens = lex_truecolor(
        "\x1b[38;2;255;165;0;48;2;0;68;136mtext\x1b[0m",
    )
    assert tokens[0] == (Ansi.FG_ffa500.BG_004488, "text")


def test_truecolor_with_attribute():
    """Bold + 24-bit RGB combines into a single compound token."""
    tokens = lex_truecolor("\x1b[1;38;2;255;128;0mbold-orange\x1b[0m")
    assert tokens[0] == (Ansi.Bold.FG_ff8000, "bold-orange")


def test_truecolor_default_enabled():
    """Default ``AnsiColorLexer()`` preserves 24-bit RGB as ``FG_{rrggbb}`` tokens."""
    tokens = lex("\x1b[38;2;255;165;0mtext\x1b[0m")
    assert tokens[0] == (Ansi.FG_ffa500, "text")


def test_truecolor_explicit_disable_quantizes():
    """``AnsiColorLexer(true_color=False)`` quantizes RGB to the 256-color palette."""
    # 255,165,0 quantizes to C214 (orange in the 6x6x6 cube).
    tokens = lex_quantized("\x1b[38;2;255;165;0mtext\x1b[0m")
    assert tokens[0] == (Ansi.C214, "text")


def test_truecolor_invalid_range_ignored():
    """Out-of-range RGB values are skipped in true-color mode too."""
    tokens = lex_truecolor("\x1b[38;2;300;0;0mtext\x1b[0m")
    assert tokens[0] == (Text, "text")


def test_truecolor_truncated_params_ignored():
    """Truncated RGB params are skipped in true-color mode too."""
    tokens = lex_truecolor("\x1b[38;2;255;128mtext\x1b[0m")
    assert tokens[0] == (Text, "text")


def test_truecolor_filter_forwards_flag():
    """``AnsiFilter(true_color=True)`` forwards the flag to its inner lexer."""
    filt = AnsiFilter(true_color=True)
    stream = [(DEFAULT_TOKEN_TYPE, "\x1b[38;2;255;165;0morange\x1b[0m")]
    result = list(filt.filter(None, stream))
    assert any(t == Ansi.FG_ffa500 for t, _ in result)


def test_truecolor_session_lexer_forwards_flag():
    """Lexer kwarg ``true_color=True`` flows through ``_AnsiFilterMixin``."""
    lexer = get_lexer_by_name("ansi-shell-session", true_color=True)
    text = "$ echo hi\n\x1b[38;2;0;128;255mhi\x1b[0m\n"
    found_truecolor = False
    for ttype, _ in lexer.get_tokens(text):
        if len(ttype) > 1 and ttype[0] == "Ansi" and ttype[-1] == "FG_0080ff":
            found_truecolor = True
            break
    assert found_truecolor


def test_formatter_renders_truecolor_inline_style():
    """``AnsiHtmlFormatter`` emits inline style for ``FG_/BG_`` tokens."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    text = "\x1b[38;2;255;165;0morange\x1b[0m"
    result = highlight(text, AnsiColorLexer(true_color=True), formatter)
    assert 'style="color: #ffa500"' in result
    assert "orange" in result
    # No CSS class should be emitted for the RGB component.
    assert "FG_ffa500" not in result


def test_formatter_renders_truecolor_background():
    """Background 24-bit RGB renders as ``background-color`` inline style."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    text = "\x1b[48;2;0;68;136mblue-bg\x1b[0m"
    result = highlight(text, AnsiColorLexer(true_color=True), formatter)
    assert 'style="background-color: #004488"' in result


def test_formatter_truecolor_combined_with_class_styling():
    """Bold + RGB renders both a CSS class for Bold and an inline style for the color."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    text = "\x1b[1;38;2;255;128;0mbold-orange\x1b[0m"
    result = highlight(text, AnsiColorLexer(true_color=True), formatter)
    assert "-Ansi-Bold" in result
    assert 'style="color: #ff8000"' in result


def test_formatter_truecolor_fg_and_bg_nested_spans():
    """Both fg and bg RGB on the same token produce two nested inline-style spans."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    text = "\x1b[38;2;255;0;0;48;2;0;0;255mfg-bg\x1b[0m"
    result = highlight(text, AnsiColorLexer(true_color=True), formatter)
    assert 'style="color: #ff0000"' in result
    assert 'style="background-color: #0000ff"' in result


def test_formatter_quantize_path_no_inline_styles():
    """When ``true_color=False`` is opted into, no inline styles are emitted."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    text = "\x1b[38;2;255;165;0morange\x1b[0m"
    result = highlight(text, AnsiColorLexer(true_color=False), formatter)
    # 255,165,0 quantizes to C214.
    assert "-Ansi-C214" in result
    assert "style=" not in result


def test_formatter_osc8_with_truecolor_coexist():
    """OSC 8 hyperlink and 24-bit RGB tokens cooperate in the same span.

    Both mechanisms inject Private Use Area markers into the token stream
    (``_LINK_*`` for hyperlinks, ``_RGB_*`` for RGB colors) and rely on
    independent post-processing passes in ``format_unencoded``. This test pins
    the contract that both rewrites happen and don't interfere.
    """
    formatter = AnsiHtmlFormatter(nowrap=True)
    text = (
        "\x1b[38;2;255;165;0m"
        "\x1b]8;;https://example.com\x07"
        "orange link"
        "\x1b]8;;\x07"
        "\x1b[0m"
    )
    result = highlight(text, AnsiColorLexer(), formatter)
    # OSC 8 → <a> tag.
    assert '<a href="https://example.com">' in result
    assert "</a>" in result
    # 24-bit RGB → inline color style on the link text.
    assert 'style="color: #ffa500"' in result
    # Visible text survives both rewrites.
    assert "orange link" in result


# --- _nearest_256 quantization ---


@pytest.mark.parametrize(
    ("r", "g", "b", "expected"),
    [
        pytest.param(0, 0, 0, 16, id="black-maps-to-cube-not-palette0"),
        pytest.param(255, 255, 255, 231, id="white-maps-to-cube-not-palette15"),
        pytest.param(95, 0, 0, 52, id="dark-red-cube"),
        pytest.param(135, 175, 215, 110, id="mid-range-cube"),
        pytest.param(8, 8, 8, 232, id="grayscale-start"),
        pytest.param(238, 238, 238, 255, id="grayscale-end"),
        pytest.param(118, 118, 118, 243, id="grayscale-mid"),
        pytest.param(1, 1, 1, 16, id="near-black-closer-to-cube"),
    ],
)
def test_nearest_256_quantization(r, g, b, expected):
    """Verify RGB-to-256 quantization for representative values."""
    assert _nearest_256(r, g, b) == expected


# --- SGR mapping consistency ---


def test_extra_css_matches_sgr_attributes():
    """EXTRA_ANSI_CSS keys match the attribute names in _SGR_ATTR_ON."""
    assert set(EXTRA_ANSI_CSS.keys()) == set(_SGR_ATTR_ON.values())


# --- Escape sequence stripping ---


def test_non_sgr_csi_stripped():
    """Non-SGR CSI sequences (cursor movement, etc.) are stripped."""
    # ESC[2J = clear screen, ESC[H = cursor home.
    tokens = lex("\x1b[2J\x1b[Hvisible")
    assert tokens == [(Text, "visible\n")]


def test_vt100_charset_stripped():
    """VT100 charset selection escapes are stripped."""
    # ESC(B = US ASCII charset.
    tokens = lex("\x1b(Btext")
    assert tokens == [(Text, "text\n")]


def test_vt100_charset_g1_stripped():
    """ESC ) designator for G1 charset is stripped."""
    tokens = lex("\x1b)0text")
    assert tokens == [(Text, "text\n")]


def test_unknown_escape_stripped():
    """Unknown single-byte escape sequences are stripped."""
    # ESC = (application keypad mode).
    tokens = lex("\x1b=text")
    assert tokens == [(Text, "text\n")]


def test_bare_escape_at_end():
    """A lone ESC at the end of input is consumed without error."""
    tokens = lex("text\x1b")
    assert tokens[0] == (Text, "text")


def test_osc_sequence_stripped():
    """Non-hyperlink OSC sequences are fully consumed and stripped."""
    # ESC ] 0 ; title BEL — OSC set window title.
    tokens = lex("\x1b]0;title\x07visible")
    assert tokens == [(Text, "visible\n")]


def test_osc_st_terminated_stripped():
    """OSC sequences terminated by ST (ESC \\) are fully stripped."""
    tokens = lex("\x1b]0;title\x1b\\visible")
    assert tokens == [(Text, "visible\n")]


# --- OSC 8 hyperlinks ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "\x1b]8;;https://example.com\x07click\x1b]8;;\x07",
            [
                (_AnsiLinkStart, "https://example.com"),
                (Text, "click"),
                (_AnsiLinkEnd, ""),
                (Text, "\n"),
            ],
            id="bel-terminated",
        ),
        pytest.param(
            "\x1b]8;;https://example.com\x1b\\click\x1b]8;;\x1b\\",
            [
                (_AnsiLinkStart, "https://example.com"),
                (Text, "click"),
                (_AnsiLinkEnd, ""),
                (Text, "\n"),
            ],
            id="st-terminated",
        ),
        pytest.param(
            "\x1b]8;id=abc;https://example.com\x07click\x1b]8;;\x07",
            [
                (_AnsiLinkStart, "https://example.com"),
                (Text, "click"),
                (_AnsiLinkEnd, ""),
                (Text, "\n"),
            ],
            id="with-params",
        ),
        pytest.param(
            "\x1b]8;;mailto:user@example.com\x07email\x1b]8;;\x07",
            [
                (_AnsiLinkStart, "mailto:user@example.com"),
                (Text, "email"),
                (_AnsiLinkEnd, ""),
                (Text, "\n"),
            ],
            id="mailto-scheme",
        ),
        pytest.param(
            "\x1b]8;;ftp://files.example.com/data\x07files\x1b]8;;\x07",
            [
                (_AnsiLinkStart, "ftp://files.example.com/data"),
                (Text, "files"),
                (_AnsiLinkEnd, ""),
                (Text, "\n"),
            ],
            id="ftp-scheme",
        ),
    ],
)
def test_osc8_hyperlink(text, expected):
    """OSC 8 hyperlinks emit link start/end tokens around the visible text."""
    assert lex(text) == expected


def test_osc8_with_sgr():
    """OSC 8 hyperlink combined with SGR color preserves both."""
    tokens = lex("\x1b[31m\x1b]8;;https://example.com\x07red link\x1b]8;;\x07\x1b[0m")
    assert tokens[0] == (_AnsiLinkStart, "https://example.com")
    assert tokens[1] == (Ansi.Red, "red link")
    assert tokens[2] == (_AnsiLinkEnd, "")


@pytest.mark.parametrize(
    ("url",),
    [
        ("javascript:alert(1)",),
        ("data:text/html,<h1>hi</h1>",),
        ("file:///etc/passwd",),
        ("relative/path",),
    ],
)
def test_osc8_unsafe_scheme_stripped(url):
    """OSC 8 with unsafe or missing URL scheme is stripped silently."""
    tokens = lex(f"\x1b]8;;{url}\x07click\x1b]8;;\x07")
    # No link tokens emitted, just the visible text.
    assert all(t is Text for t, _ in tokens)
    assert "".join(v for _, v in tokens) == "click\n"


def test_osc8_implicit_close():
    """A new OSC 8 link implicitly closes the previous one."""
    tokens = lex(
        "\x1b]8;;https://a.com\x07first\x1b]8;;https://b.com\x07second\x1b]8;;\x07"
    )
    assert tokens == [
        (_AnsiLinkStart, "https://a.com"),
        (Text, "first"),
        (_AnsiLinkEnd, ""),
        (_AnsiLinkStart, "https://b.com"),
        (Text, "second"),
        (_AnsiLinkEnd, ""),
        (Text, "\n"),
    ]


def test_osc8_unclosed():
    """An unclosed OSC 8 link is automatically closed at end of input."""
    tokens = lex("\x1b]8;;https://example.com\x07click")
    assert tokens[0] == (_AnsiLinkStart, "https://example.com")
    assert tokens[1] == (Text, "click\n")
    assert tokens[-1] == (_AnsiLinkEnd, "")


def test_osc8_close_without_open():
    """An OSC 8 close without a preceding open is silently ignored."""
    tokens = lex("\x1b]8;;\x07visible")
    assert tokens == [(Text, "visible\n")]


# --- State persistence across multiple sequences ---


def test_color_persists_until_changed():
    """A foreground color set in one sequence persists until explicitly changed."""
    tokens = lex("\x1b[31mred \x1b[1mbold-red\x1b[0m")
    assert tokens[0] == (Ansi.Red, "red ")
    assert tokens[1] == (Ansi.Bold.Red, "bold-red")


def test_multiple_color_changes():
    """Color can be changed multiple times without resetting."""
    tokens = lex("\x1b[31mred\x1b[32mgreen\x1b[34mblue\x1b[0m")
    assert tokens[0] == (Ansi.Red, "red")
    assert tokens[1] == (Ansi.Green, "green")
    assert tokens[2] == (Ansi.Blue, "blue")


def test_attribute_stacking():
    """Attributes accumulate: bold then italic produces bold+italic."""
    tokens = lex("\x1b[1mbold\x1b[3mboth\x1b[0m")
    assert tokens[0] == (Ansi.Bold, "bold")
    assert tokens[1] == (Ansi.Bold.Italic, "both")


def test_independent_fg_bg():
    """Foreground and background colors are independent of each other."""
    tokens = lex("\x1b[31;42mred-on-green\x1b[34mblue-on-green\x1b[0m")
    assert tokens[0] == (Ansi.Red.BGGreen, "red-on-green")
    assert tokens[1] == (Ansi.Blue.BGGreen, "blue-on-green")


# --- Edge cases and malformed input ---


def test_sgr_with_trailing_semicolons():
    """Trailing semicolons in SGR parameters produce zero codes, which are resets."""
    # \x1b[31;m is "31" then empty "m" — but this is one sequence with params "31;".
    # The ";" splits into ["31", ""], and int("") raises ValueError, so the whole
    # sequence is ignored.
    tokens = lex("\x1b[31;mtext")
    # The trailing ";" makes int("") fail, so color is not applied.
    assert tokens[0] == (Text, "text\n")


def test_sgr_leading_semicolons():
    """Leading semicolons produce 0 values (resets)."""
    # \x1b[;31m splits into ["", "31"]. int("") fails, sequence is skipped.
    tokens = lex("\x1b[;31mtext")
    assert tokens[0] == (Text, "text\n")


def test_sgr_double_semicolons():
    """Double semicolons produce empty strings that cause the sequence to be skipped."""
    tokens = lex("\x1b[1;;31mtext")
    assert tokens[0] == (Text, "text\n")


def test_sgr_unknown_codes_ignored():
    """Unknown SGR codes are silently ignored; known codes still apply."""
    # SGR 6 (rapid blink) is not handled. SGR 31 is red.
    tokens = lex("\x1b[6;31mtext\x1b[0m")
    assert tokens[0] == (Ansi.Red, "text")


def test_256color_truncated_params():
    """Truncated 256-color sequence (missing color index) leaves leftover codes.

    ``38;5``: code 38 triggers extended color handling but needs at least 2 more
    values (mode + index). Only 1 remains (5), so 38 skips. Then 5 is processed
    as SGR 5 (blink).
    """
    tokens = lex("\x1b[38;5mtext\x1b[0m")
    assert tokens[0] == (Ansi.Blink, "text")


def test_256color_out_of_range():
    """256-color index outside 0-255 is ignored."""
    tokens = lex("\x1b[38;5;256mtext\x1b[0m")
    assert tokens[0] == (Text, "text")


def test_24bit_truncated_params():
    """Truncated 24-bit RGB sequence (missing channels) is ignored."""
    # 38;2;255;128 — missing the blue channel.
    tokens = lex("\x1b[38;2;255;128mtext\x1b[0m")
    assert tokens[0] == (Text, "text")


def test_24bit_out_of_range():
    """24-bit RGB values outside 0-255 are ignored."""
    tokens = lex("\x1b[38;2;300;128;0mtext\x1b[0m")
    assert tokens[0] == (Text, "text")


def test_extended_color_unknown_mode():
    """Extended color with unknown mode (not 5 or 2) skips the mode byte.

    ``38;3;100``: code 38 triggers extended color handling, mode 3 is unknown so
    mode and nothing else are consumed, then 100 is processed as SGR 100 (bright
    black background).
    """
    tokens = lex("\x1b[38;3;100mtext\x1b[0m")
    assert tokens[0] == (Ansi.BGBrightBlack, "text")


def test_non_numeric_sgr_params():
    """Non-numeric characters in CSI params cause partial consumption.

    ``ESC[abc;31m`` is not a valid SGR sequence. The regex consumes ``ESC[a``
    as a CSI with ``a`` as the final byte, leaving ``bc;31mtext`` as plain text.
    """
    tokens = lex("\x1b[abc;31mtext")
    text = "".join(v for _, v in tokens)
    assert "text" in text


def test_consecutive_resets():
    """Multiple consecutive resets are harmless."""
    tokens = lex("\x1b[0m\x1b[0m\x1b[0mtext")
    assert tokens == [(Text, "text\n")]


def test_empty_text_between_sequences():
    """Sequences with no text between them produce no empty tokens."""
    tokens = lex("\x1b[31m\x1b[42m\x1b[1mtext\x1b[0m")
    assert tokens[0] == (Ansi.Bold.Red.BGGreen, "text")


def test_newline_in_colored_text():
    """Newlines within colored text are preserved in the token value."""
    tokens = lex("\x1b[31mline1\nline2\x1b[0m")
    assert tokens[0] == (Ansi.Red, "line1\nline2")


def test_interleaved_text_and_escapes():
    """Complex interleaving of plain text and escape sequences."""
    text = "a\x1b[31mb\x1b[0mc\x1b[32md\x1b[0me"
    tokens = lex(text)
    assert tokens[0] == (Text, "a")
    assert tokens[1] == (Ansi.Red, "b")
    assert tokens[2] == (Text, "c")
    assert tokens[3] == (Ansi.Green, "d")
    assert tokens[4] == (Text, "e\n")


# --- Lexer state isolation ---


def test_lexer_resets_between_calls():
    """Each call to get_tokens starts from a clean state."""
    lexer = AnsiColorLexer()
    tokens1 = list(lexer.get_tokens("\x1b[1;31mbold red"))
    tokens2 = list(lexer.get_tokens("plain"))
    assert tokens1[0][0] is Ansi.Bold.Red
    assert tokens2 == [(Text, "plain\n")]


# --- Style dict completeness ---


def test_ansi_styles_has_all_named_colors():
    """Style dict contains entries for all 16 named foreground and background colors."""
    for name in _NAMED_COLORS:
        assert getattr(Ansi, name) in _ANSI_STYLES
        assert getattr(Ansi, f"BG{name}") in _ANSI_STYLES


def test_ansi_styles_has_256_palette():
    """Style dict contains entries for all 256 foreground and background indices."""
    for i in range(256):
        assert getattr(Ansi, f"C{i}") in _ANSI_STYLES
        assert getattr(Ansi, f"BGC{i}") in _ANSI_STYLES


def test_ansi_styles_excludes_all_attributes():
    """All text attribute tokens are absent from the style dict.

    Furo's dark-mode CSS generator adds ``color: #D0D0D0`` to every token in the style
    dict. For attribute tokens, this overrides actual foreground colors on compound
    tokens when the attribute rule appears later in the CSS cascade. All attribute
    styling is handled by ``EXTRA_ANSI_CSS`` / ``custom.css`` instead.
    """
    for attr in _SGR_ATTR_ON.values():
        assert getattr(Ansi, attr) not in _ANSI_STYLES


def test_ansi_styles_count():
    """Style dict has only color entries: 32 named + 512 indexed."""
    assert len(_ANSI_STYLES) == 32 + 512


def test_formatter_no_color_on_attribute_css():
    """CSS rules for attribute-only tokens must not set a color property.

    When an attribute token (like -Ansi-Strikethrough) has a ``color`` property in its
    CSS rule, it can override the foreground color of a sibling color token (like
    -Ansi-Red) if the attribute rule appears later in the CSS cascade. This regression
    test catches the issue that Furo's dark-mode generator exposed.
    """
    formatter = AnsiHtmlFormatter()
    css = formatter.get_style_defs(".highlight")
    for attr in ("Faint", "Blink", "Reverse", "Strikethrough", "Overline"):
        # Find the CSS rule for this attribute.
        cls = f"-Ansi-{attr}"
        for line in css.split("\n"):
            if cls in line and "{" in line:
                # The rule should not contain a bare "color:" property.
                # (It may contain "background-color:" which is fine.)
                rule_body = line.split("{")[1].split("}")[0]
                declarations = [d.strip() for d in rule_body.split(";") if d.strip()]
                for decl in declarations:
                    prop = decl.split(":")[0].strip()
                    assert prop != "color", (
                        f"CSS for {cls} must not set 'color' (found: {decl!r})"
                    )


# --- Palette data ---


def test_palette_256_completeness():
    """256-color palette has exactly 256 entries."""
    assert len(_PALETTE_256) == 256
    assert set(_PALETTE_256.keys()) == set(range(256))


def test_palette_256_hex_format():
    """All palette values are 7-character hex strings."""
    for idx, color in _PALETTE_256.items():
        assert color.startswith("#"), f"Index {idx}: {color!r}"
        assert len(color) == 7, f"Index {idx}: {color!r}"


# --- LEXER_MAP ---


def test_lexer_map_completeness():
    """LEXER_MAP has one entry per session lexer."""
    session_lexers = list(collect_session_lexers())
    assert len(LEXER_MAP) == len(session_lexers)
    for lexer in session_lexers:
        assert lexer in LEXER_MAP


# --- AnsiFilter integration ---


def test_ansi_filter_transforms_output_tokens():
    """AnsiFilter converts Generic.Output tokens containing ANSI codes."""
    filt = AnsiFilter()
    stream = [(DEFAULT_TOKEN_TYPE, "\x1b[31mred\x1b[0m")]
    result = list(filt.filter(None, stream))
    assert any(t == Ansi.Red for t, _ in result)


def test_ansi_filter_passes_through_other_tokens():
    """AnsiFilter does not modify tokens that are not Generic.Output."""
    filt = AnsiFilter()
    stream = [(Token.Keyword, "for")]
    result = list(filt.filter(None, stream))
    assert result == [(Token.Keyword, "for")]


# --- AnsiHtmlFormatter CSS classes ---


def test_formatter_css_classes_single_color():
    """Single-color token gets the expected CSS classes."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    result = highlight("\x1b[31mred\x1b[0m", AnsiColorLexer(), formatter)
    assert "-Ansi-Red" in result


def test_formatter_css_classes_compound():
    """Compound token gets decomposed CSS classes."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    result = highlight("\x1b[1;31mbold-red\x1b[0m", AnsiColorLexer(), formatter)
    assert "-Ansi-Bold" in result
    assert "-Ansi-Red" in result


def test_formatter_css_classes_256color():
    """256-color tokens get the correct CSS class."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    result = highlight("\x1b[38;5;154mtext\x1b[0m", AnsiColorLexer(), formatter)
    assert "-Ansi-C154" in result


def test_formatter_style_defs_contain_ansi_colors():
    """get_style_defs() includes CSS rules for ANSI color tokens."""
    formatter = AnsiHtmlFormatter()
    css = formatter.get_style_defs(".highlight")
    assert "-Ansi-Red" in css
    assert "-Ansi-Bold" in css
    assert "-Ansi-C154" in css


# --- AnsiHtmlFormatter hyperlink rendering ---


def test_formatter_osc8_hyperlink():
    """OSC 8 hyperlink is rendered as an HTML <a> tag."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    text = "\x1b]8;;https://example.com\x07click here\x1b]8;;\x07"
    result = highlight(text, AnsiColorLexer(), formatter)
    assert '<a href="https://example.com">' in result
    assert "click here" in result
    assert "</a>" in result


def test_formatter_osc8_with_color():
    """OSC 8 hyperlink combined with SGR color renders both link and color."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    text = "\x1b[31m\x1b]8;;https://example.com\x07red link\x1b]8;;\x07\x1b[0m"
    result = highlight(text, AnsiColorLexer(), formatter)
    assert '<a href="https://example.com">' in result
    assert "-Ansi-Red" in result
    assert "</a>" in result


def test_formatter_osc8_url_escaping():
    """URLs with special HTML characters are properly escaped in href."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    text = "\x1b]8;;https://example.com/p?a=1&b=2\x07link\x1b]8;;\x07"
    result = highlight(text, AnsiColorLexer(), formatter)
    assert 'href="https://example.com/p?a=1&amp;b=2"' in result


def test_formatter_css_contains_link_rules():
    """get_style_defs() includes CSS for hyperlink styling."""
    formatter = AnsiHtmlFormatter()
    css = formatter.get_style_defs(".highlight")
    assert "color: inherit" in css
    assert "text-decoration: underline" in css


def test_formatter_osc8_unsafe_scheme_no_link():
    """Unsafe URL schemes produce no <a> tag in formatted output."""
    formatter = AnsiHtmlFormatter(nowrap=True)
    text = "\x1b]8;;javascript:alert(1)\x07click\x1b]8;;\x07"
    result = highlight(text, AnsiColorLexer(), formatter)
    assert "<a " not in result
    assert "click" in result


# --- Real-world ANSI patterns ---
#
# Test cases inspired by:
# - https://nbsphinx.readthedocs.io/en/latest/code-cells.html#ANSI-Colors
# - https://en.wikipedia.org/wiki/ANSI_escape_code
# - https://tldp.org/HOWTO/Bash-Prompt-HOWTO/x329.html
# - http://bitmote.com/index.php?post/2012/11/19/Using-ANSI-Color-Codes-to-Colorize-Your-Bash-Prompt-on-Linux


@pytest.mark.parametrize(
    ("text", "expected_tokens"),
    [
        pytest.param(
            # Bash prompt: bold green user@host, bold blue path, reset.
            "\x1b[01;32muser@host\x1b[00m:\x1b[01;34m~/code\x1b[00m$ ",
            [
                (Ansi.Bold.Green, "user@host"),
                (Text, ":"),
                (Ansi.Bold.Blue, "~/code"),
                (Text, "$ \n"),
            ],
            id="bash-prompt",
        ),
        pytest.param(
            # Git diff: red deletion, green addition.
            "\x1b[31m-old line\x1b[0m\n\x1b[32m+new line\x1b[0m",
            [
                (Ansi.Red, "-old line"),
                (Text, "\n"),
                (Ansi.Green, "+new line"),
                (Text, "\n"),
            ],
            id="git-diff",
        ),
        pytest.param(
            # Compiler error: bold white file, bold red "error:", normal message.
            "\x1b[1;37mmain.c:10:\x1b[0m \x1b[1;31merror:\x1b[0m use of undeclared",
            [
                (Ansi.Bold.White, "main.c:10:"),
                (Text, " "),
                (Ansi.Bold.Red, "error:"),
                (Text, " use of undeclared\n"),
            ],
            id="compiler-error",
        ),
        pytest.param(
            # lolcat-style 256-color: each letter a different color.
            "\x1b[38;5;196mR\x1b[38;5;208mA\x1b[38;5;226mI\x1b[38;5;46mN\x1b[0m",
            [
                (Ansi.C196, "R"),
                (Ansi.C208, "A"),
                (Ansi.C226, "I"),
                (Ansi.C46, "N"),
                (Text, "\n"),
            ],
            id="lolcat-256color",
        ),
        pytest.param(
            # 24-bit gradient: orange to red, preserved as FG_{rrggbb} tokens.
            "\x1b[38;2;255;165;0mO\x1b[38;2;255;69;0mR\x1b[0m",
            [
                (Ansi.FG_ffa500, "O"),
                (Ansi.FG_ff4500, "R"),
                (Text, "\n"),
            ],
            id="truecolor-gradient",
        ),
        pytest.param(
            # Combined fg/bg from the nbsphinx 8-color table: bold red on cyan.
            "\x1b[1;31;46m XYZ \x1b[0m",
            [(Ansi.Bold.Red.BGCyan, " XYZ "), (Text, "\n")],
            id="nbsphinx-8color-table",
        ),
        pytest.param(
            # 256-color swatch: foreground and background set to the same color.
            "\x1b[38;5;82;48;5;82mX\x1b[1mX\x1b[0m",
            [
                (Ansi.C82.BGC82, "X"),
                (Ansi.Bold.C82.BGC82, "X"),
                (Text, "\n"),
            ],
            id="nbsphinx-256color-swatch",
        ),
        pytest.param(
            # pytest output: green PASSED with bold percentage.
            "\x1b[32mPASSED\x1b[0m [\x1b[1m100%\x1b[0m]",
            [
                (Ansi.Green, "PASSED"),
                (Text, " ["),
                (Ansi.Bold, "100%"),
                (Text, "]\n"),
            ],
            id="pytest-output",
        ),
        pytest.param(
            # Cursor movement mixed with color: ESC[2K clears line, then colored text.
            "\x1b[2K\x1b[33mWarning:\x1b[0m check config",
            [
                (Ansi.Yellow, "Warning:"),
                (Text, " check config\n"),
            ],
            id="cursor-movement-with-color",
        ),
        pytest.param(
            # italic + underline + color: rich terminal output.
            "\x1b[3;4;35mdecorated\x1b[23;24mplain-magenta\x1b[0m",
            [
                (Ansi.Italic.Underline.Magenta, "decorated"),
                (Ansi.Magenta, "plain-magenta"),
                (Text, "\n"),
            ],
            id="rich-italic-underline",
        ),
        pytest.param(
            # Reverse video for status bars.
            "\x1b[7;1m STATUS \x1b[27m normal \x1b[0m",
            [
                (Ansi.Bold.Reverse, " STATUS "),
                (Ansi.Bold, " normal "),
                (Text, "\n"),
            ],
            id="reverse-video-statusbar",
        ),
        pytest.param(
            # Strikethrough for deprecated items.
            "\x1b[9mold_func\x1b[0m -> new_func",
            [
                (Ansi.Strikethrough, "old_func"),
                (Text, " -> new_func\n"),
            ],
            id="strikethrough-deprecated",
        ),
        pytest.param(
            # SGR 0 embedded in middle of combined params.
            "\x1b[1;0;31mred-not-bold\x1b[0m",
            [(Ansi.Red, "red-not-bold"), (Text, "\n")],
            id="reset-within-combined-params",
        ),
        pytest.param(
            # Long sequence of semicolons: all 8 standard colors in one SGR.
            "\x1b[31m\x1b[32m\x1b[33m\x1b[34m\x1b[35m\x1b[36mfinal-cyan\x1b[0m",
            [(Ansi.Cyan, "final-cyan"), (Text, "\n")],
            id="overridden-colors-last-wins",
        ),
    ],
)
def test_real_world_ansi(text, expected_tokens):
    """Real-world ANSI patterns from terminal tools and documentation references."""
    assert lex(text) == expected_tokens
