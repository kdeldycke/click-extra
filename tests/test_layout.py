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
from click_extra.layout import RULE_COLOR, RULE_GLYPH, cell_width, center_in_rule


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
