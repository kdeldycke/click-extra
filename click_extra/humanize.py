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
"""Human-readable rendering of machine values.

Formatters that turn raw numbers into the compact strings shown in terminal
output, tables and reports. The reverse direction, parsing a human-written
value back into a machine type, lives in {mod}`click_extra.types` (see
{class}`~click_extra.types.Duration`).
"""

from __future__ import annotations

from datetime import timedelta

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Literal

_UNIT_SYSTEMS: dict[str, tuple[int, tuple[str, ...]]] = {
    "iec": (1024, ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")),
    "si": (1000, ("B", "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")),
    "jedec": (1024, ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")),
}
"""Byte-unit systems, mapping a name to its base and unit symbols.

- `iec`: binary powers of `1024` with the unambiguous IEC symbols (`KiB`, `MiB`).
- `si`: decimal powers of `1000` with the SI symbols (`kB`, `MB`).
- `jedec`: binary powers of `1024` with the customary symbols (`KB`, `MB`): the
  widespread convention (Windows, many CLIs), though `KB` for 1024 bytes is
  imprecise.
"""


def format_size(
    size: float, *, units: Literal["iec", "si", "jedec"] = "iec", precision: int = 1
) -> str:
    """Render a byte count as a compact, human-readable string.

    :param size: The number of bytes. A negative value keeps a leading `-`.
    :param units: The unit system to render in, one of {data}`_UNIT_SYSTEMS`:
        `iec` (the default) for binary powers with the unambiguous `KiB`/`MiB`
        symbols, `si` for decimal powers with `kB`/`MB`, or `jedec` for binary
        powers with the customary but imprecise `KB`/`MB`.
    :param precision: Number of fractional digits for every unit above bytes. A
        byte count is always rendered as a whole number.
    :return: The size followed by a space and its unit, like `1.5 KiB`. The
        integer part is grouped with thousands separators.
    :raises ValueError: If *units* is not a known unit system.
    """
    try:
        base, symbols = _UNIT_SYSTEMS[units]
    except KeyError:
        msg = f"Unknown unit system {units!r}; pick one of {sorted(_UNIT_SYSTEMS)}."
        raise ValueError(msg) from None
    sign = "-" if size < 0 else ""
    amount = float(abs(size))
    index = 0
    last = len(symbols) - 1
    while amount >= base and index < last:
        amount /= base
        index += 1
    unit = symbols[index]
    # Bytes have no fractional part; every larger unit honors `precision`.
    if index == 0:
        return f"{sign}{round(amount):,} {unit}"
    return f"{sign}{amount:,.{precision}f} {unit}"


def format_duration(duration: float | timedelta) -> str:
    """Render an elapsed duration compactly: `2.3s`, `1:05`, then `1:02:03`.

    Below a minute the duration reads as one-decimal seconds (`2.3s`). From a
    minute up it switches to a clock layout, growing an hours field only once it
    reaches an hour: `1:05` under an hour, `1:02:03` at or above.

    The reverse direction, parsing a human-written duration back into a
    {class}`~datetime.timedelta`, lives in {mod}`click_extra.types` (see
    {class}`~click_extra.types.Duration`).

    :param duration: The elapsed time, as a number of seconds or a
        {class}`~datetime.timedelta`.
    :return: The compact rendering described above.
    """
    if isinstance(duration, timedelta):
        duration = duration.total_seconds()
    if duration < 60:
        return f"{duration:.1f}s"
    minutes, secs = divmod(int(duration), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
