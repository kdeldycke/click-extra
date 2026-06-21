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
"""Bake build-time metadata into Python source files before compilation.

Compiled binaries (Nuitka, PyInstaller) and ``git``-less runtimes (Docker
images, archive checkouts) cannot resolve version or Git metadata at runtime
the way :class:`click_extra.version.VersionOption` does. The values must
instead be written into the source *before* the build, by rewriting the
relevant dunder assignments (``__version__``, ``__git_short_hash__``, ...) in
place with :mod:`ast`.

This mirrors `shadow-rs <https://github.com/baoyachi/shadow-rs>`_, which
injects build-time constants (``BRANCH``, ``SHORT_COMMIT``, ``COMMIT_HASH``,
``COMMIT_DATE``, ``TAG``, ...) into Rust binaries at compile time.

.. todo::
    Add the following build-time template fields, mirroring the constants
    shadow-rs injects:

    - ``{build_time}``: when the distribution was built (shadow-rs exposes it
      as ``BUILD_TIME``, with RFC 2822 and RFC 3339 variants ``BUILD_TIME_2822``
      / ``BUILD_TIME_3339``).
    - ``{build_os}`` / ``{build_target}`` / ``{build_target_arch}``: the OS,
      target triple and architecture the build ran on. These describe the
      *build* host, unlike ``{env_info}`` which reports the *runtime* Python,
      OS and architecture, so both are worth keeping for cross-built binaries.
"""

from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]


def _find_dunder_str(source: str, name: str) -> ast.Constant | None:
    """Find a top-level dunder string constant in parsed source.

    Locates the first top-level ``name = "..."`` assignment and returns
    the :class:`ast.Constant` node for the string value. Returns
    ``None`` if no matching assignment is found.
    """
    tree = ast.parse(source)
    for node in ast.iter_child_nodes(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value
    return None


def _rewrite_str_literal(
    file_path: Path,
    source: str,
    node: ast.Constant,
    new_value: str,
) -> None:
    """Replace a string literal's content in a source file.

    Uses the AST node's line/column positions to swap the text between
    the opening and closing quotes, preserving quoting style and all
    surrounding content.
    """
    col_offset = node.col_offset
    end_lineno = node.end_lineno
    col_end = node.end_col_offset
    assert col_offset is not None
    assert end_lineno is not None and col_end is not None
    lines = source.splitlines(keepends=True)
    line = lines[end_lineno - 1]
    # Replace everything between the opening and closing quotes.
    new_line = line[: col_offset + 1] + new_value + line[col_end - 1 :]
    lines[end_lineno - 1] = new_line
    file_path.write_text("".join(lines), encoding="utf-8")


def prebake_version(
    file_path: Path,
    local_version: str,
) -> str | None:
    """Pre-bake a ``__version__`` string with a `PEP 440 local version
    identifier
    <https://peps.python.org/pep-0440/#local-version-identifiers>`_.

    Reads *file_path*, finds the ``__version__`` assignment via
    :mod:`ast`, and — if the version contains ``.dev`` and does not
    already contain ``+`` — appends ``+<local_version>``.

    This is the compile-time complement to the runtime
    :attr:`click_extra.version.VersionOption.version` property:
    Nuitka/PyInstaller binaries cannot run ``git`` at runtime, so the hash
    must be baked into ``__version__`` in the source file **before**
    compilation.

    Returns the new version string on success, or ``None`` if no change
    was made (release version, already pre-baked, or no ``__version__``
    found).
    """
    source = file_path.read_text(encoding="utf-8")
    node = _find_dunder_str(source, "__version__")
    if node is None:
        logging.warning("No __version__ found in %s", file_path)
        return None

    version = node.value
    assert isinstance(version, str)

    if ".dev" not in version:
        logging.info(
            "Release version %r in %s — skipping.",
            version,
            file_path,
        )
        return None

    if "+" in version:
        logging.info(
            "Version %r in %s already has a local identifier — skipping.",
            version,
            file_path,
        )
        return None

    new_version = f"{version}+{local_version}"
    _rewrite_str_literal(file_path, source, node, new_version)

    logging.info(
        "Pre-baked %s: %r → %r",
        file_path,
        version,
        new_version,
    )
    return new_version


def prebake_dunder(
    file_path: Path,
    name: str,
    value: str,
) -> str | None:
    """Replace an empty dunder variable's value in a Python source file.

    Reads *file_path*, finds a top-level ``name = ""`` assignment via
    :mod:`ast`, and — if the current value is an empty string — replaces
    it with *value*.

    Placeholders must use empty strings (``__field__ = ""``, not
    ``None``). The AST matcher only recognizes string literals, and
    the empty string serves as a falsy sentinel that stays
    type-consistent with baked values (always ``str``).

    This is the generic counterpart to :func:`prebake_version`: where
    ``prebake_version`` appends a PEP 440 local identifier to
    ``__version__``, this function does a full replacement of any dunder
    variable that starts empty. Typical use case: injecting a release
    commit SHA into ``__git_tag_sha__ = ""`` at build time.

    Returns the new value on success, or ``None`` if no change was made
    (variable not found, or already has a non-empty value).
    """
    source = file_path.read_text(encoding="utf-8")
    node = _find_dunder_str(source, name)
    if node is None:
        logging.warning("No %s found in %s", name, file_path)
        return None

    current = node.value

    if current:
        logging.info(
            "%s in %s already has value %r — skipping.",
            name,
            file_path,
            current,
        )
        return None

    _rewrite_str_literal(file_path, source, node, value)

    logging.info(
        "Pre-baked %s in %s: %r → %r",
        name,
        file_path,
        current,
        value,
    )
    return value


def discover_package_init_files() -> list[Path]:
    """Discover ``__init__.py`` files from ``[project.scripts]``.

    Reads the ``pyproject.toml`` in the current working directory,
    extracts ``[project.scripts]`` entry points, and returns the
    unique ``__init__.py`` paths for each top-level package.

    Only returns paths that exist on disk. Returns an empty list if
    ``pyproject.toml`` is missing or has no ``[project.scripts]``.
    """
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        logging.warning("No pyproject.toml found in current directory.")
        return []

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    scripts = data.get("project", {}).get("scripts", {})
    if not scripts:
        logging.warning("No [project.scripts] entries found in pyproject.toml.")
        return []

    seen: set[Path] = set()
    paths: list[Path] = []
    for script in scripts.values():
        # "repomatic.__main__:main" → "repomatic".
        module_id = script.split(":")[0]
        package_dir = module_id.split(".")[0]
        init_path = Path(package_dir) / "__init__.py"
        if init_path in seen:
            continue
        seen.add(init_path)
        if init_path.exists():
            paths.append(init_path)
        else:
            logging.warning("Package init not found: %s", init_path)
    return paths
