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

"""Tests for ``click_extra.layout``: measuring a line and composing one."""

from __future__ import annotations

import pytest

from click_extra import Style, unstyle
from click_extra.layout import (
    RESET,
    RULE_COLOR,
    RULE_GLYPH,
    cell_width,
    center_in_rule,
    fit_columns,
    pad_to,
)


@pytest.mark.parametrize("label", (None, ""))
def test_center_in_rule_draws_an_unbroken_line_for_no_label(label):
    """Naming nothing draws a divider, not a frame around an empty middle."""
    assert unstyle(center_in_rule(label, 40)) == RULE_GLYPH * 40


def test_center_in_rule_measures_a_styled_label_unstyled():
    """A label's escapes occupy no cell, so they must not shorten the rule."""
    plain = center_in_rule("nord", 40)
    styled = center_in_rule(Style(fg="cyan")("nord"), 40)
    assert cell_width(unstyle(styled)) == cell_width(unstyle(plain)) == 40


def test_center_in_rule_paints_the_rule_and_leaves_the_label_alone():
    """The rule recedes by default, and a caller's own label styling survives."""
    ruled = center_in_rule(Style(fg="cyan")("nord"), 40)
    assert Style(fg="cyan")("nord") in ruled
    assert Style(fg=RULE_COLOR)(f"{RULE_GLYPH * 16}[ ") in ruled
    # Opting out leaves the whole line as its parts arrived.
    bare = center_in_rule("nord", 40, color=None)
    assert unstyle(bare) == bare


def test_fit_columns_floors_at_nothing_by_default():
    """The floor belongs to whoever lays the text out, not to the measure.

    It was `MIN_COLUMNS` while the function lived in the capture module, which
    is a property of a picture rather than of the text measured for one.
    """
    assert fit_columns("") == 0
    assert fit_columns("kiwi") == 4
    assert fit_columns("kiwi", floor=20) == 20


@pytest.mark.parametrize(
    ("text", "cells"),
    (
        ("apricot", 7),
        ("杏", 2),
        ("e\u0301", 1),
        # An escape styles the glyphs around it and occupies no cell of its own.
        ("\x1b[31mapricot\x1b[0m", 7),
        ("\x1b]8;;https://example.com\x1b\\apricot\x1b]8;;\x1b\\", 7),
        # A tab reaches the next stop, eight columns along.
        ("a\tb", 9),
        ("", 0),
    ),
)
def test_cell_width_discounts_what_a_terminal_draws_nowhere(text, cells):
    """Escapes and hyperlinks measure nothing, and a tab measures to its stop.

    `wcwidth.wcswidth`, which this used to call, refuses any string carrying a
    control character and answers `-1`, so every styled string fell back to its
    character count: 16 for a red `apricot` the terminal draws in 7.
    """
    assert cell_width(text) == cells


def test_cell_width_is_never_negative():
    """A control character measures what a terminal advances by, never `-1`."""
    assert cell_width("\x07") == 0
    assert cell_width("\x00") == 0


def test_pad_to_measures_the_text_a_terminal_draws():
    """`str.ljust` counts escapes it cannot see, so a styled line pads short."""
    styled = Style(fg="red")("kiwi")
    assert len(styled.ljust(10)) == len(styled)  # str.ljust does nothing here.
    assert cell_width(pad_to(styled, 10)) == 10
    assert cell_width(pad_to("kiwi", 10)) == 10


def test_pad_to_closes_a_style_before_the_blanks():
    """A background left open would otherwise bleed across the gap."""
    assert pad_to("\x1b[41mkiwi", 8).endswith(f"{RESET}    ")
    # A line already closed gains no second reset.
    assert pad_to(Style(fg="red")("kiwi"), 8).count(RESET) == 1


def test_pad_to_leaves_text_already_wide_enough_alone():
    """Nothing to pad, nothing added, reset included."""
    assert pad_to("apricot", 4) == "apricot"
    assert pad_to("杏杏", 4) == "杏杏"
