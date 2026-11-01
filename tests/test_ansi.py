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
"""Tests for `click_extra.ansi`, the ANSI escape grammar and its decoders."""

from __future__ import annotations

import re

import pytest

from click_extra import open_ansi, strip_ansi
from click_extra.ansi import nearest_256

# --- open_ansi() -------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        pytest.param("", "", id="empty"),
        pytest.param("no escapes at all", "", id="unstyled"),
        pytest.param("\x1b[31mred\x1b[0m", "", id="closed-by-reset"),
        pytest.param("\x1b[31mred\x1b[m", "", id="closed-by-bare-reset"),
        pytest.param("\x1b[93mopen", "\x1b[93m", id="one-code-left-open"),
        pytest.param(
            "\x1b[93m\x1b[1mopen", "\x1b[93m\x1b[1m", id="two-codes-left-open"
        ),
        pytest.param(
            "\x1b[93mout \x1b[36min\x1b[0m back",
            "",
            id="reset-clears-the-whole-stack",
        ),
        pytest.param(
            "\x1b[93mout \x1b[36min\x1b[0m\x1b[93m back",
            "\x1b[93m",
            id="reopened-after-a-reset",
        ),
        pytest.param("\x1b[0;31mred", "\x1b[0;31m", id="reset-carrying-a-color"),
        pytest.param(
            "\x1b[93mold\x1b[0;31mnew", "\x1b[0;31m", id="reset-carrying-a-color-clears"
        ),
    ),
)
def test_open_ansi(text, expected):
    assert open_ansi(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        pytest.param("", "\x1b[93m", id="empty-chunk-keeps-what-was-open"),
        pytest.param("plain", "\x1b[93m", id="unstyled-chunk-keeps-what-was-open"),
        pytest.param(
            "\x1b[1mbold", "\x1b[93m\x1b[1m", id="chunk-adds-to-what-was-open"
        ),
        pytest.param("closed\x1b[0m", "", id="chunk-closes-what-was-open"),
    ),
)
def test_open_ansi_resumes_from_an_opened_state(text, expected):
    assert open_ansi(text, "\x1b[93m") == expected


def test_open_ansi_chunked_matches_one_shot():
    """Reading a string in two chunks answers like reading it whole.

    Every cut is tried except the ones splitting an escape in half, which no
    parser can carry across a chunk boundary.
    """
    text = "\x1b[93mrain \x1b[36mon\x1b[0m Monday \x1b[1mand\x1b[0m\x1b[93m Tuesday"
    inside = {
        index
        for match in re.finditer(r"\x1b\[[0-9;]*m", text)
        for index in range(match.start() + 1, match.end())
    }
    for cut in set(range(len(text) + 1)) - inside:
        assert open_ansi(text[cut:], open_ansi(text[:cut])) == open_ansi(text), cut


# --- strip_ansi() ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        pytest.param("plain", "plain", id="plain"),
        pytest.param("\x1b[1;31mbold red\x1b[0m", "bold red", id="sgr"),
        pytest.param("\x1b[38;2;255;0;0mtrue\x1b[m", "true", id="sgr_truecolor"),
        pytest.param("\x1b[2J\x1b[H\x1b[?25lhidden\x1b[1;2H", "hidden", id="csi"),
        pytest.param(
            "\x1b]8;;https://example.com\x1b\\link\x1b]8;;\x1b\\", "link", id="osc8_st"
        ),
        pytest.param(
            "\x1b]8;;https://example.com\x07link\x1b]8;;\x07", "link", id="osc8_bel"
        ),
        pytest.param("\x1b]0;a title\x07body", "body", id="osc_title"),
        pytest.param("body\x1b]0;left open", "body", id="osc_open"),
        pytest.param("\x1bMup\x1bDdown", "updown", id="two_byte"),
        # Save and restore the cursor.
        pytest.param("\x1b7saved\x1b8", "saved", id="two_byte_digit"),
        # Full reset, and the keypad modes.
        pytest.param("\x1bcfresh\x1b=keypad\x1b>", "freshkeypad", id="two_byte_symbol"),
        # A character set selection, as `tput sgr0` writes it, and a screen test.
        pytest.param("\x1b(Bplain\x1b#8grid", "plaingrid", id="intermediate_byte"),
        # Neither bracket closes an escape: they open a CSI and an OSC.
        pytest.param("\x1b[", "\x1b[", id="csi_unfinished"),
    ),
)
def test_strip_ansi(text, expected):
    assert strip_ansi(text) == expected


def test_strip_ansi_keeps_bytes_as_bytes():
    assert strip_ansi(b"\x1b[32mok\x1b[0m \xc3\xa9") == b"ok \xc3\xa9"
    assert strip_ansi(b"\x1b7saved\x1b8") == b"saved"


# --- nearest_256() -----------------------------------------------------------


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
    assert nearest_256(r, g, b) == expected
