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

from pathlib import Path

from click_extra import STDOUT_SENTINEL, is_stdout, prep_path


def test_stdout_sentinel() -> None:
    assert STDOUT_SENTINEL == "-"


def test_is_stdout() -> None:
    assert is_stdout(Path("-")) is True
    assert is_stdout(Path("output.txt")) is False
    # Only a bare "-" is stdout, not a file that happens to be named "-".
    assert is_stdout(Path("dir") / "-") is False


def test_prep_path_creates_parents_and_writes_utf8(tmp_path) -> None:
    target = tmp_path / "sub" / "dir" / "report.md"
    with prep_path(target) as stream:
        # Non-ASCII payload exercises the forced UTF-8 encoding.
        stream.write("café — smörgåsbord")
    assert target.parent.is_dir()
    assert target.read_text(encoding="utf-8") == "café — smörgåsbord"


def test_prep_path_stdout(capsys) -> None:
    stream = prep_path(Path("-"))
    stream.write("papaya")
    stream.flush()
    assert capsys.readouterr().out == "papaya"
