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
import sys
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from extra_platforms.pytest import skip_windows

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
    assert target.read_text(encoding="UTF-8") == "café — smörgåsbord"


def test_prep_path_stdout(capsys) -> None:
    stream = prep_path(Path("-"))
    stream.write("papaya")
    stream.flush()
    assert capsys.readouterr().out == "papaya"


def test_prep_path_reopens_the_process_stdout_as_utf8(monkeypatch, tmp_path) -> None:
    """The stdout of the process itself is opened again on its descriptor, as UTF-8.

    Its own `cp1252` encoding cannot carry the glyphs. Closing the stream returned
    leaves that stdout open.
    """
    target = tmp_path / "stdout.txt"
    glyphs = "".join(UNENCODABLE_ON_CP1252)
    with target.open("w", encoding="cp1252") as stdout, monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", stdout)
        patch.setattr(sys, "__stdout__", stdout)

        stream = prep_path(Path("-"))
        stream.write(glyphs)
        stream.close()

        assert not stdout.closed
    assert target.read_bytes() == glyphs.encode("UTF-8")


def test_prep_path_returns_a_process_stdout_without_descriptor(monkeypatch) -> None:
    """A stdout of the process with no file descriptor is returned as-is."""
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "__stdout__", stdout)

    assert prep_path(Path("-")) is stdout


@pytest.mark.parametrize(
    "capture",
    (
        "sys",
        pytest.param(
            "fd", marks=skip_windows(reason='Click rejects capture="fd" on Windows.')
        ),
    ),
)
def test_prep_path_stdout_reaches_the_runner_capture(capture) -> None:
    """A command writing to `-` prints into the capture of Click's test runner.

    Under `capture="fd"`, `sys.stdout.fileno()` returns a copy of the original
    stdout descriptor, so a stream opened on it writes past the capture.
    """

    @click.command()
    def harvest():
        stream = prep_path(Path("-"))
        try:
            echo("papaya", file=stream)
        finally:
            if stream is not sys.stdout:
                stream.close()

    result = CliRunner(capture=capture).invoke(harvest)

    assert result.exit_code == 0
    assert result.output == "papaya\n"


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
    """A command prints a glyph to a `cp1252` stream instead of crashing on it.

    The streams keep `\\n` as written: the default would turn it into `\\r\\n` on
    Windows.
    """
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\n")
    stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\n")
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", stderr)

    @command
    def fruit_cli():
        echo("".join(UNENCODABLE_ON_CP1252))

    fruit_cli.main([], standalone_mode=False)

    stdout.flush()
    assert stdout.buffer.getvalue().decode("UTF-8") == "✓✘╭─\n"
