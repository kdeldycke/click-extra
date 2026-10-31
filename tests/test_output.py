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

import io
from pathlib import Path

import pytest

from click_extra import (
    STDOUT_SENTINEL,
    command,
    echo,
    force_unicode_output,
    is_stdout,
    prep_path,
)

UNENCODABLE_ON_CP1252 = ("✓", "✘", "╭", "─")
"""Glyphs Click Extra prints that a legacy Windows code page cannot encode: the two
status marks, and two characters of a rounded table border."""


class FakeStream:
    """A stand-in for a standard stream, recording what it was reconfigured to.

    The real streams of a test run already speak UTF-8, so the legacy path is never
    taken through them.
    """

    def __init__(self, encoding: str | None, *, refuse: bool = False) -> None:
        self.encoding = encoding
        self.refuse = refuse
        self.reconfigured: dict[str, str] = {}

    def reconfigure(self, **kwargs: str) -> None:
        if self.refuse:
            raise ValueError("stream refuses reconfiguration")
        self.reconfigured.update(kwargs)
        if "encoding" in kwargs:
            self.encoding = kwargs["encoding"]


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


@pytest.mark.parametrize(
    "encoding", ("cp1252", "ascii", "latin-1", "unknown-8bit", None)
)
def test_legacy_stream_is_switched_to_utf8(monkeypatch, encoding) -> None:
    """A stream unable to carry the glyphs is reconfigured to UTF-8.

    So is a stream reporting an encoding Python does not know.
    """
    out, err = FakeStream(encoding), FakeStream(encoding)
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)

    force_unicode_output()

    for stream in (out, err):
        assert stream.reconfigured == {"encoding": "UTF-8"}
        assert stream.encoding is not None
        for glyph in UNENCODABLE_ON_CP1252:
            glyph.encode(stream.encoding)


@pytest.mark.parametrize("encoding", ("utf-8", "UTF-8", "utf8"))
def test_utf8_stream_is_left_alone(monkeypatch, encoding) -> None:
    """A stream already speaking UTF-8 is never reconfigured, whatever its spelling."""
    out, err = FakeStream(encoding), FakeStream(encoding)
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)

    force_unicode_output()

    assert out.reconfigured == {}
    assert err.reconfigured == {}


def test_a_refusing_stream_never_raises(monkeypatch) -> None:
    """A stream refusing reconfiguration is left as the platform made it."""
    out = FakeStream("cp1252", refuse=True)
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", FakeStream("utf-8"))

    force_unicode_output()

    assert out.encoding == "cp1252"


def test_a_stream_without_reconfigure_is_skipped(monkeypatch) -> None:
    """A stream object without `reconfigure()`, like a capture, raises nothing."""
    monkeypatch.setattr("sys.stdout", io.StringIO())
    monkeypatch.setattr("sys.stderr", io.StringIO())

    force_unicode_output()


def test_command_prints_glyphs_to_a_legacy_stream(monkeypatch) -> None:
    """A command prints a glyph to a `cp1252` stream instead of crashing on it."""
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", stderr)

    @command
    def fruit_cli():
        echo("".join(UNENCODABLE_ON_CP1252))

    fruit_cli.main([], standalone_mode=False)

    stdout.flush()
    assert stdout.buffer.getvalue().decode("UTF-8") == "✓✘╭─\n"
