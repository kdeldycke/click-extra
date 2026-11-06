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
"""Tests for the year count of an announcement banner."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from click_extra.sphinx.announcement import years_since


def anniversaries(start: date, day: date) -> int:
    """Count the anniversaries of `start` that `day` has reached, one at a time.

    Counted apart from {func}`~click_extra.sphinx.announcement.years_since`, so
    the test does not grade a formula against itself. `start` cannot be a 29
    February, which `date.replace` cannot move to a common year.
    """
    count = 0
    while start.replace(year=start.year + count + 1) <= day:
        count += 1
    return count


def test_years_since_on_every_day_of_a_leap_span() -> None:
    """The count goes up on each anniversary, and never a day before it.

    The span holds the leap days of 2024, 2028 and 2032. Each moves a count of
    days divided by 365 one day further ahead, which the last assertion checks
    the span catches.
    """
    start = date(2021, 6, 21)
    day = start
    naive_ahead = 0
    while day <= date(2032, 12, 31):
        expected = anniversaries(start, day)
        assert years_since(start, today=day) == expected, day
        naive_ahead += (day - start).days // 365 > expected
        day += timedelta(days=1)
    assert naive_ahead


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2025, 2, 28), 0),
        (date(2025, 3, 1), 1),
        (date(2028, 2, 28), 3),
        (date(2028, 2, 29), 4),
        # Before the start, the count rounds down too.
        (date(2024, 2, 28), -1),
    ],
)
def test_years_since_a_leap_day(today: date, expected: int) -> None:
    """A start on 29 February has its anniversary on 1 March of a common year."""
    assert years_since(date(2024, 2, 29), today=today) == expected


def test_years_since_counts_to_the_current_day() -> None:
    """Without `today`, the count ends on the current day in UTC."""
    start = date(2000, 1, 1)
    before = datetime.now(tz=UTC).date()
    count = years_since(start)
    after = datetime.now(tz=UTC).date()
    # A run straddling midnight counts to either day.
    assert count in {years_since(start, today=before), years_since(start, today=after)}
