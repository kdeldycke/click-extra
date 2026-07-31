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

import pytest

from click_extra import format_size


@pytest.mark.parametrize(
    ("size", "expected"),
    (
        (0, "0 B"),
        (1, "1 B"),
        (512, "512 B"),
        (1023, "1,023 B"),
        (1024, "1.0 KiB"),
        (1536, "1.5 KiB"),
        (12345, "12.1 KiB"),
        (1024**2, "1.0 MiB"),
        (1024**2 * 2.5, "2.5 MiB"),
        (1024**3, "1.0 GiB"),
        (1024**4, "1.0 TiB"),
        (1024**5, "1.0 PiB"),
        (1024**6, "1.0 EiB"),
        (1024**7, "1.0 ZiB"),
        (1024**8, "1.0 YiB"),
        # Beyond the largest unit, the value keeps scaling in YiB.
        (1024**9, "1,024.0 YiB"),
    ),
)
def test_format_size_iec(size, expected) -> None:
    """IEC binary units are the default."""
    assert format_size(size) == expected
    assert format_size(size, units="iec") == expected


@pytest.mark.parametrize(
    ("size", "expected"),
    (
        (0, "0 B"),
        (999, "999 B"),
        (1000, "1.0 kB"),
        (1500, "1.5 kB"),
        (1_000_000, "1.0 MB"),
        (1_500_000, "1.5 MB"),
        (1_000_000_000, "1.0 GB"),
    ),
)
def test_format_size_si(size, expected) -> None:
    assert format_size(size, units="si") == expected


@pytest.mark.parametrize(
    ("size", "expected"),
    (
        # Binary powers, but with the customary KB/MB symbols.
        (0, "0 B"),
        (1023, "1,023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (10240, "10.0 KB"),
        (1024**2, "1.0 MB"),
        (1024**2 * 1.5, "1.5 MB"),
        (1024**3, "1.0 GB"),
    ),
)
def test_format_size_jedec(size, expected) -> None:
    assert format_size(size, units="jedec") == expected


@pytest.mark.parametrize(
    ("size", "precision", "expected"),
    (
        (1536, 0, "2 KiB"),
        (1536, 1, "1.5 KiB"),
        (1536, 3, "1.500 KiB"),
        (1234, 2, "1.21 KiB"),
    ),
)
def test_format_size_precision(size, precision, expected) -> None:
    assert format_size(size, precision=precision) == expected


@pytest.mark.parametrize(
    ("size", "expected"),
    (
        (-1, "-1 B"),
        (-1024, "-1.0 KiB"),
        (-1_500_000, "-1.4 MiB"),
    ),
)
def test_format_size_negative(size, expected) -> None:
    assert format_size(size) == expected


def test_format_size_unknown_units() -> None:
    with pytest.raises(ValueError, match="Unknown unit system"):
        format_size(1024, units="binary")  # type: ignore[arg-type]
