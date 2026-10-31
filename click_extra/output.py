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
"""Send command output to a file path or to stdout.

Helpers for the common `--output` option pattern, where a `-` value means
"write to stdout" instead of creating a file literally named `-`, and for
standard streams that cannot encode what a command prints.
"""

from __future__ import annotations

import codecs
import sys

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path
    from typing import IO, TextIO


STDOUT_SENTINEL = "-"
"""Conventional `--output` value asking for stdout instead of a file on disk."""


def is_stdout(path: Path) -> bool:
    """Return `True` when *path* is the stdout sentinel `-`.

    Guards against accidentally creating a file literally named `-` in the
    current directory.
    """
    return str(path) == STDOUT_SENTINEL


def prep_path(path: Path) -> IO[str]:
    """Open *path* for writing as UTF-8 text, or return stdout for `-`.

    Always yields a UTF-8 stream, stdout included, sidestepping the
    `UnicodeEncodeError` a non-ASCII payload triggers on Windows, where the
    console defaults to `cp1252`. For a real path, missing parent directories
    are created first, absorbing the `mkdir -p` a caller would otherwise need.

    ```{note}
    When stdout is an in-memory capture with no backing file descriptor (Click's
    test runner, the Sphinx `{click:run}` directive that live-renders CLI output
    in the docs), `fileno()` raises and the existing stream is returned as-is.
    Such streams are already Python text objects, so the Windows `cp1252` concern
    does not apply: that only bites a real terminal, which always has a
    descriptor.
    ```

    :param path: The destination path, or `-` for stdout.
    :return: A writable text stream. The caller closes it; the stdout stream is
        wrapped with `closefd=False`, so closing it leaves the real stdout open.
    """
    if is_stdout(path):
        try:
            fd = sys.stdout.fileno()
        except (OSError, ValueError):
            return sys.stdout
        return open(fd, "w", encoding="utf-8", closefd=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("w", encoding="utf-8")


def _speaks_utf8(stream: TextIO) -> bool:
    """Whether `stream` already encodes the whole of Unicode, as UTF-8."""
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return False
    try:
        return codecs.lookup(encoding).name == "utf-8"
    except LookupError:
        return False


def force_unicode_output() -> None:
    """Switch `sys.stdout` and `sys.stderr` to UTF-8 when they do not speak it.

    Windows gives a redirected stream the encoding of its legacy code page,
    `cp1252` on a Western install, which has no `✓`, no `✘` and none of the
    box-drawing characters of a table border. A command printing one of them dies
    on a `UnicodeEncodeError` the moment its output is piped or redirected, which
    is how automation runs a CLI. A narrow `PYTHONIOENCODING`, like `ascii`, leads
    a POSIX host to the same crash.

    A stream already speaking UTF-8 is left alone. A stream refusing the new
    encoding is asked for `backslashreplace` errors instead: an escaped character
    in the output is ugly, but it loses nothing and does not crash. A stream with
    no `reconfigure()`, like an `io.StringIO` capture, is skipped.

    {meth}`~click_extra.commands.Command.main` calls it as each run starts.

    ```{note}
    Python 3.15 turns UTF-8 mode on by default
    ([PEP 686](https://peps.python.org/pep-0686/)), so its standard streams speak
    UTF-8 unless the environment asks otherwise.
    ```

    ```{todo}
    Remove once the minimum supported Python is 3.15, where UTF-8 mode makes the
    standard streams speak UTF-8.
    ```
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None or _speaks_utf8(stream):
            continue
        try:
            reconfigure(encoding="UTF-8")
        except (OSError, ValueError, LookupError):
            try:
                reconfigure(errors="backslashreplace")
            except (OSError, ValueError, LookupError):
                # Nothing more to try: leave the stream as the platform made it.
                pass
