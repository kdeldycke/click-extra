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
"""Count the years an announcement banner claims, like "maintained for 5+ years".

A figure written by hand in `conf.py` goes stale on the next anniversary.
{func}`years_since` computes it again on each build, so the banner of a site
published from CI stays current.
"""

from __future__ import annotations

from datetime import UTC, datetime

TYPE_CHECKING = False
if TYPE_CHECKING:
    from datetime import date


def years_since(start: date, *, today: date | None = None) -> int:
    """Return the whole years from `start` to `today`.

    The count goes up on each anniversary of `start`, never before it. A count
    of days divided by 365 would run a day ahead for each leap day in between.
    A `start` on 29 February has its anniversary on 1 March of a common year.

    :param start: the day the count starts from.
    :param today: the day the count ends on. Defaults to the current day in UTC,
        which is the day of the build.
    :return: the whole years from `start` to `today`, rounded down: negative
        when `today` comes before `start`.
    """
    if today is None:
        today = datetime.now(tz=UTC).date()
    return (
        today.year - start.year - ((today.month, today.day) < (start.month, start.day))
    )
