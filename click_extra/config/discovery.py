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
"""Search for the configuration files a `--config` location designates.

{class}`ConfigDiscovery` is the mixin
{class}`~click_extra.config.option.ConfigOption` inherits to find its files. It
downloads a URL, or globs a local pattern, then walks up the parent folders
until a VCS root. It also looks for a `pyproject.toml` from the current working
directory upward.
"""

from __future__ import annotations

import logging
import os
import stat
from itertools import takewhile
from pathlib import Path

from click import get_current_context

from .._utils import IS_WINDOWS, walk_up
from .formats import ConfigFormat, format_from_path

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from typing import Any, Literal

    from .option import Sentinel

logger = logging.getLogger(__name__)


VCS_DIRS = (".git", ".hg", ".svn", ".bzr", "CVS", ".darcs")
"""VCS directory names used to identify version control system roots.

Includes:
- `.git`: Git
- `.hg`: Mercurial
- `.svn`: Subversion
- `.bzr`: Bazaar
- `CVS`: CVS (note: uppercase, no leading dot)
- `.darcs`: Darcs
"""


_PATH_READ_FORMATS = (ConfigFormat.SQLITE, ConfigFormat.PLIST)
"""Formats a local file is parsed from by its path, not from its text.

A SQLite database is binary, and so is the binary variant of a plist: see
{meth}`~click_extra.config.option.ConfigOption.load_sqlite_config` and
{meth}`~click_extra.config.option.ConfigOption.load_plist_config`.
{meth}`ConfigDiscovery.search_and_read_file` returns such a file with an empty
placeholder as its content.
"""


_DEFAULT_MAGIC_CHARACTERS = frozenset("*?[]{}|~")
"""Characters the default search flags make magic in a pattern.

The ones `wcmatch.glob.is_magic` looks for under the default
{attr}`~click_extra.config.option.ConfigOption.search_pattern_flags`, once
backslashes read as separators, as {meth}`ConfigDiscovery._is_magic` reads them.
{meth}`ConfigDiscovery._literal_base` splits a pattern with them, which needs no
import of wcmatch.
"""


class ConfigDiscovery:
    """Find the configuration files a location designates.

    A mixin of {class}`~click_extra.config.option.ConfigOption`, which sets the
    attributes the search reads: `search_pattern_flags`, `search_parents` and
    `stop_at`. A `pyproject.toml` is read with the option's own `parse_conf()`.
    """

    if TYPE_CHECKING:
        _search_pattern_flags: int | None
        search_parents: bool
        stop_at: Path | str | Literal[Sentinel.VCS] | None

        @property
        def search_pattern_flags(self) -> int: ...

        def parse_conf(
            self,
            content: str,
            formats: Sequence[ConfigFormat],
            location: Path | str | None = None,
        ) -> Iterable[dict[str, Any] | None]: ...

    @staticmethod
    def _find_vcs_root(start: Path) -> Path | None:
        """Walk up from `start` looking for a VCS root directory.

        Returns the directory containing one of the VCS directories defined in
        `VCS_DIRS`, or `None` if no VCS root is found before reaching the
        filesystem root.
        """
        current = start if start.is_dir() else start.parent
        for directory in walk_up(current):
            if any((directory / vcs_dir).exists() for vcs_dir in VCS_DIRS):
                return directory
        return None

    def _resolve_stop_at(self, start_dir: Path) -> Path | None:
        """Resolve the `stop_at` value to an absolute `Path` or `None`.

        - `None` → `None` (no boundary).
        - `VCS` → calls `_find_vcs_root(start_dir)`.
        - `Path` or other `str` → resolves to absolute.
        """
        if self.stop_at is None:
            return None
        if isinstance(self.stop_at, (str, Path)):
            return Path(self.stop_at).resolve()
        # The `VCS` sentinel is the only value left. Matching it by elimination
        # spares an import of its module, which imports this one.
        return self._find_vcs_root(start_dir)

    @staticmethod
    def _should_stop_walking(directory: Path, stop_at: Path | None) -> bool:
        """Return `True` if the parent-directory walk should stop.

        Stops when:
        - `stop_at` is set and `directory` is not equal to or a child of it.
        - The directory exists but is not readable.
        """
        if stop_at is not None:
            try:
                directory.relative_to(stop_at)
            except ValueError:
                return True
        return bool(directory.exists() and not os.access(directory, os.R_OK))

    def _is_magic(self, pattern: str) -> bool:
        """Whether `pattern` holds glob syntax, under the search flags.

        Backslashes are read as path separators first: on Windows, wcmatch
        mistakes the backslashes of a path for glob escape characters.
        """
        # Deferred import: keeps wcmatch off the startup path of every CLI.
        from wcmatch import glob

        return glob.is_magic(
            pattern.replace("\\", "/"), flags=self.search_pattern_flags
        )

    def _literal_base(self, pattern: str) -> str | None:
        """The folder a local `pattern` searches, found without wcmatch.

        Joins the leading segments of `pattern` that hold no character of
        `_DEFAULT_MAGIC_CHARACTERS`, the last segment left out. `None` when no
        segment qualifies, when `pattern` holds a `..` segment, which can resolve
        out of that folder, or when the search flags are not the default ones:
        only wcmatch can read them.
        """
        if self._search_pattern_flags is not None:
            return None
        parts = Path(pattern).parts
        if ".." in parts:
            return None
        literal = tuple(
            takewhile(
                lambda part: _DEFAULT_MAGIC_CHARACTERS.isdisjoint(
                    part.replace("\\", "/")
                ),
                parts[:-1],
            )
        )
        return str(Path(*literal)) if literal else None

    def parent_patterns(self, pattern: str) -> Iterable[tuple[str | None, str]]:
        """Generate `(root_dir, file_pattern)` pairs for searching.

        Each yielded pair can be passed directly to
        `glob.iglob(file_pattern, root_dir=root_dir)` so that every
        sub-pattern (whether from `BRACE` or `SPLIT` expansion) is
        correctly scoped to the same directory.

        `root_dir` is `None` for entirely magic patterns that will be
        evaluated relative to the current working directory.

        Stops when reaching the root folder, the `stop_at` boundary, or an
        inaccessible directory.
        """
        # Split pattern into non-magic directory prefix (root_dir) and magic
        # file suffix (file_pattern).
        root_dir: Path | None
        if not self._is_magic(pattern):
            resolved = Path(pattern).resolve()
            if resolved.is_file():
                root_dir = resolved.parent
                file_pattern = resolved.name
            else:
                root_dir = resolved
                file_pattern = ""
        else:
            parts = Path(pattern).parts
            magic_idx = next(i for i, part in enumerate(parts) if self._is_magic(part))
            if magic_idx == 0:
                # Entirely magic (like "{*.toml,*.yaml}").
                root_dir = None
                file_pattern = pattern
            else:
                root_dir = Path(*parts[:magic_idx]).resolve()
                file_pattern = str(Path(*parts[magic_idx:]))

        # Yield the original location.
        root_str = str(root_dir) if root_dir is not None else None
        yield root_str, file_pattern

        if not self.search_parents:
            return

        if root_dir is None:
            logger.debug("Entirely magic pattern, skipping parent search.")
            return

        logger.debug("Parent search enabled.")
        stop_at = self._resolve_stop_at(root_dir)

        for parent in root_dir.parents:
            if self._should_stop_walking(parent, stop_at):
                logger.debug(f"Stopped walking at {parent}")
                return
            yield str(parent), file_pattern

    def search_and_read_file(
        self,
        pattern: str,
    ) -> Iterable[tuple[Path | str, str, str | None]]:
        """Search filesystem or URL for files matching the `pattern`.

        If `pattern` is an URL, download its content. A pattern is considered an URL
        only if it validates as one and starts with `http://` or `https://`. All
        other patterns are considered glob patterns for local filesystem search.

        Returns an iterator of `(location, content, media_type)` triples, for each
        one matching the pattern. `location` is normalized and `content` raw.
        `media_type` is the bare `type/subtype` the server advertised in its
        `Content-Type` header, and is `None` for a local file, whose format is
        derived from its name. Only regular files are returned, directories are
        silently skipped. The exception is a `pattern` naming a character device
        or a named pipe, like `/dev/null`: it is read from that path.

        This method returns the raw content of all matching patterns, without trying to
        parse them. If the content is empty, it is still returned as-is.

        Also includes lookups into parents directories if `self.search_parents` is
        `True`.

        Raises `FileNotFoundError` if no file was found after searching all locations.
        """
        files_found = 0

        # Deferred import: keeps urllib off the startup path of every CLI.
        from urllib.parse import urlsplit

        # Check if the pattern is an URL.
        if urlsplit(pattern).scheme in ("http", "https"):
            location = pattern
            # It's an URL, try to download it.
            logger.debug(f"Download file from URL: {location}")
            # Deferred imports: keep http.client and ssl off the startup path of
            # every CLI. The standard library handles TLS, redirects and the
            # `*_proxy` environment variables, so a download needs no third-party
            # HTTP stack.
            from urllib.error import HTTPError
            from urllib.request import urlopen

            try:
                with urlopen(location) as response:
                    files_found += 1
                    # Decode using the charset advertised in the Content-Type
                    # header, defaulting to UTF-8: the near-universal encoding
                    # for configuration files.
                    charset = response.headers.get_content_charset() or "utf-8"
                    # The same header types the payload. A server sending no
                    # Content-Type at all reads as `text/plain`, which no format
                    # claims, so the URL's file name still decides.
                    media_type = response.headers.get_content_type()
                    yield location, response.read().decode(charset), media_type
            # A 4xx/5xx leaves files_found at 0, so the search falls through to
            # the FileNotFoundError below, like a missing local file. Lower-level
            # URLError failures (DNS, refused connection, TLS) still propagate.
            except HTTPError as error:
                logger.warning(f"Can't download {location}: {error.reason}")

        # Not an URL, search local file system.
        else:
            logger.debug(f"Search filesystem for {pattern}")
            # wcmatch expect patterns to be written with Unix-like syntax by default,
            # even on Windows. See more details at:
            # https://facelessuser.github.io/wcmatch/glob/#windows-separators
            # https://github.com/facelessuser/wcmatch/issues/194
            if IS_WINDOWS:
                win_path = Path(pattern)
                pattern = str(win_path.as_posix())
                logger.debug(f"Windows pattern converted from {win_path} to {pattern}")

            # A path naming a character device or a named pipe, like the null
            # device, is read as given. The glob below keeps to regular files, so a
            # pattern never blocks on a pipe it happens to match, and could not find
            # the `nul` device of Windows anyway, which no directory lists.
            try:
                mode = os.stat(pattern).st_mode
            except OSError:
                mode = 0
            if stat.S_ISCHR(mode) or stat.S_ISFIFO(mode):
                stream = Path(pattern)
                logger.debug(f"Read {stream} as a stream.")
                yield stream, stream.read_text(encoding="UTF-8"), None
                return

            # No file matches below a folder that does not exist. Testing for it
            # first keeps wcmatch off the startup path of every CLI whose default
            # configuration folder is missing. A parent walk still goes on above
            # such a folder.
            folder = None if self.search_parents else self._literal_base(pattern)
            if folder is not None and not os.path.isdir(folder):
                raise FileNotFoundError(f"No file found matching {pattern}")

            # Deferred import: keeps wcmatch off the startup path of every CLI.
            from wcmatch import glob

            for root_dir, file_pattern in self.parent_patterns(pattern):
                # Sort matches within each directory: iglob yields in filesystem
                # order, so without this the winner among sibling files (and
                # the layering order of a cascade) would be arbitrary.
                for file in sorted(
                    glob.iglob(
                        file_pattern,
                        root_dir=root_dir,
                        flags=self.search_pattern_flags,
                    )
                ):
                    base = Path(root_dir) if root_dir else Path()
                    file_path = (base / file).resolve()
                    logger.debug(f"Found candidate: {file_path}")
                    if not file_path.is_file():
                        logger.debug(f"Skipping non-file {file_path}")
                        continue
                    files_found += 1
                    if format_from_path(file_path, _PATH_READ_FORMATS):
                        yield file_path, "", None
                    else:
                        yield file_path, file_path.read_text(encoding="UTF-8"), None

        if not files_found:
            raise FileNotFoundError(f"No file found matching {pattern}")

    def _search_pyproject_cwd(self) -> Iterable[tuple[Path, dict[str, Any]]]:
        """Yield every `pyproject.toml` from CWD upward, deepest first.

        Mimics the discovery behavior of uv, ruff, and mypy: start in the
        current working directory and walk up to the VCS root (or filesystem
        root), yielding each `pyproject.toml` containing a
        `[tool.<cli_name>]` section as a `(path, parsed_document)` pair. The
        first one is the file a single-source discovery uses.

        A `pyproject.toml` without a `[tool.<cli_name>]` section is
        skipped so unrelated project configs (like a dotfiles repo's
        `[tool.ruff]`) do not shadow the user's app-dir config.

        Only runs when `ConfigFormat.PYPROJECT_TOML` is in
        `file_format_patterns`. Yields nothing when no valid
        `pyproject.toml` is found.
        """
        cwd = Path.cwd()
        stop_at = self._resolve_stop_at(cwd)

        cli_name = get_current_context().find_root().info_name

        for directory in walk_up(cwd):
            if self._should_stop_walking(directory, stop_at):
                logger.debug(f"pyproject.toml CWD search stopped at {directory}.")
                break

            candidate = directory / "pyproject.toml"
            if not candidate.is_file():
                continue

            logger.debug(f"Found {candidate}, parsing as pyproject.toml.")
            try:
                content = candidate.read_text(encoding="UTF-8")
            except OSError as ex:
                logger.debug(f"Cannot read {candidate}: {ex}")
                continue

            for conf in self.parse_conf(
                content, formats=(ConfigFormat.PYPROJECT_TOML,)
            ):
                if conf and cli_name in conf:
                    yield candidate, conf
                    break
            else:
                logger.debug(f"{candidate} has no [tool.{cli_name}] section; skipping.")
