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
"write to stdout" instead of creating a file literally named `-`.
"""

from __future__ import annotations

import sys

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path
    from typing import IO


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
