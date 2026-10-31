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

Compiled binaries (Nuitka, PyInstaller) and `git`-less runtimes (Docker
images, archive checkouts) cannot resolve version or Git metadata at runtime
the way {class}`click_extra.version.VersionOption` does. The values must
instead be written into the source *before* the build, by rewriting the
relevant dunder assignments (`__version__`, `__git_short_hash__`, ...) in
place with {mod}`ast`.

This mirrors [shadow-rs](https://github.com/baoyachi/shadow-rs), which
injects build-time constants (`BRANCH`, `SHORT_COMMIT`, `COMMIT_HASH`,
`COMMIT_DATE`, `TAG`, ...) into Rust binaries at compile time. Its
`BUILD_TIME`, `BUILD_OS` and `BUILD_TARGET` constants have counterparts here
too, in {data}`click_extra.version.BUILD_RESOLVERS`: those describe the host
that produced the binary, which neither the git fields nor the running
interpreter can answer once it is running somewhere else.

The module also reads a project's packaging metadata, to find the files to bake:
{func}`read_project_scripts` lists its console scripts, and
{func}`locate_package_root` finds the directory a package imports from, whether
the project uses the flat or the src layout. {mod}`click_extra.cli_wrapper`
shares both to run a project directory by its entry point.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from .config.formats import ConfigFormat, parse_content

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping

logger = logging.getLogger(__name__)


def _iter_dunder_strs(tree: ast.Module) -> Iterator[tuple[str, ast.Constant]]:
    """Yield `(name, node)` for each top-level `name = "..."` of a parsed module.

    Only a single-target assignment of a string literal qualifies, which is the
    shape a dunder placeholder takes. The node is the {class}`ast.Constant` of
    the string value, whose positions locate the literal in the source.
    """
    for node in ast.iter_child_nodes(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            yield node.targets[0].id, node.value


def _find_dunder_str(source: str, name: str) -> ast.Constant | None:
    """Find a top-level dunder string constant in parsed source.

    Locates the first top-level `name = "..."` assignment and returns
    the {class}`ast.Constant` node for the string value. Returns
    `None` if no matching assignment is found.
    """
    for found, node in _iter_dunder_strs(ast.parse(source)):
        if found == name:
            return node
    return None


def _replace_str_literals(
    source: str,
    replacements: Iterable[tuple[ast.Constant, str]],
) -> str:
    """Replace the content of string literals in `source`, keeping their quotes.

    Each node's line and column positions locate the text between its opening
    and closing quotes, so the quoting style and all surrounding content are
    preserved. The replacements are applied from the last literal backwards:
    a literal earlier on the same line keeps its offsets once a later one has
    changed length.
    """
    lines = source.splitlines(keepends=True)
    ordered = sorted(
        replacements,
        key=lambda item: (item[0].end_lineno or 0, item[0].end_col_offset or 0),
        reverse=True,
    )
    for node, new_value in ordered:
        col_offset = node.col_offset
        end_lineno = node.end_lineno
        col_end = node.end_col_offset
        assert end_lineno is not None and col_end is not None
        line = lines[end_lineno - 1]
        # Replace everything between the opening and closing quotes.
        lines[end_lineno - 1] = line[: col_offset + 1] + new_value + line[col_end - 1 :]
    return "".join(lines)


def prebake_version(
    file_path: Path,
    local_version: str,
) -> str | None:
    """Pre-bake a `__version__` string with a [PEP 440 local version identifier](https://peps.python.org/pep-0440/#local-version-identifiers).

    Reads *file_path*, finds the `__version__` assignment via
    {mod}`ast`, and, if the version contains `.dev` and does not
    already contain `+`, appends `+<local_version>`.

    This is the compile-time complement to the runtime
    {attr}`click_extra.version.VersionOption.version` property:
    Nuitka/PyInstaller binaries cannot run `git` at runtime, so the hash
    must be baked into `__version__` in the source file **before**
    compilation.

    Returns the new version string on success, or `None` if no change
    was made (release version, already pre-baked, or no `__version__`
    found).
    """
    source = file_path.read_text(encoding="utf-8")
    node = _find_dunder_str(source, "__version__")
    if node is None:
        logger.warning("No __version__ found in %s", file_path)
        return None

    version = node.value
    assert isinstance(version, str)

    if ".dev" not in version:
        logger.info(
            "Release version %r in %s — skipping.",
            version,
            file_path,
        )
        return None

    if "+" in version:
        logger.info(
            "Version %r in %s already has a local identifier — skipping.",
            version,
            file_path,
        )
        return None

    new_version = f"{version}+{local_version}"
    file_path.write_text(
        _replace_str_literals(source, ((node, new_version),)), encoding="utf-8"
    )

    logger.info(
        "Pre-baked %s: %r → %r",
        file_path,
        version,
        new_version,
    )
    return new_version


def prebake_dunders(
    file_path: Path,
    fields: Mapping[str, str | Callable[[], str | None]],
) -> dict[str, str]:
    """Fill the empty dunder placeholders of a Python source file in one pass.

    Reads and parses `file_path` once, then writes it once, with every
    placeholder of `fields` that was found empty filled in. A field whose value
    is a callable is resolved only when its placeholder is present and still
    empty, so a resolver that shells out (to `git`, say) runs for the
    placeholders that need it, never for a file carrying none. A callable
    answering `None` or an empty string leaves its placeholder alone, as does a
    placeholder already holding a value: running the pass twice is safe.

    Placeholders must use empty strings (`__field__ = ""`, not `None`). The AST
    matcher only recognizes string literals, and the empty string acts as a
    falsy sentinel that stays type-consistent with baked values (always `str`).

    A name with no placeholder in the file is skipped: a build bakes every field
    it knows into every file of a package, and most files declare a few of them.
    {func}`prebake_dunder` is the single-field form, which does warn.

    :param file_path: the Python source file to rewrite.
    :param fields: dunder names (`__git_branch__`) mapped to the value to bake,
        or to a callable resolving it on demand.
    :return: the names written, each mapped to the value it received. Empty when
        the file was left untouched.
    """
    source = file_path.read_text(encoding="utf-8")
    nodes: dict[str, ast.Constant] = {}
    for name, node in _iter_dunder_strs(ast.parse(source)):
        if name in fields and name not in nodes:
            nodes[name] = node
    for name in fields.keys() - nodes.keys():
        logger.debug("No %s found in %s — skipping.", name, file_path)

    baked: dict[str, str] = {}
    for name, node in nodes.items():
        current = node.value
        if current:
            logger.info(
                "%s in %s already has value %r — skipping.",
                name,
                file_path,
                current,
            )
            continue
        value = fields[name]
        resolved = value() if callable(value) else value
        if not resolved:
            logger.info("No value to bake into %s in %s — skipping.", name, file_path)
            continue
        baked[name] = resolved

    if baked:
        file_path.write_text(
            _replace_str_literals(
                source, ((nodes[name], value) for name, value in baked.items())
            ),
            encoding="utf-8",
        )
        for name, value in baked.items():
            logger.info("Pre-baked %s in %s: %r → %r", name, file_path, "", value)
    return baked


def prebake_dunder(
    file_path: Path,
    name: str,
    value: str,
) -> str | None:
    """Replace an empty dunder variable's value in a Python source file.

    Reads *file_path*, finds a top-level `name = ""` assignment via
    {mod}`ast`, and, if the current value is an empty string, replaces
    it with *value*. The single-field form of {func}`prebake_dunders`, which
    carries the placeholder rules, with one addition: a file holding no `name`
    assignment at all is reported with a warning, since a lone field is asked
    for on purpose and a typo in its name would otherwise pass unnoticed.

    This is the generic counterpart to {func}`prebake_version`: where
    `prebake_version` appends a PEP 440 local identifier to
    `__version__`, this function does a full replacement of any dunder
    variable that starts empty. Typical use case: injecting a release
    commit SHA into `__git_tag_sha__ = ""` at build time.

    Returns the new value on success, or `None` if no change was made
    (variable not found, or already has a non-empty value).
    """
    if _find_dunder_str(file_path.read_text(encoding="utf-8"), name) is None:
        logger.warning("No %s found in %s", name, file_path)
        return None
    return prebake_dunders(file_path, {name: value}).get(name)


def read_project_scripts(directory: Path) -> dict[str, str]:
    """Read the console-script entry points declared by a local project.

    Inspects PEP 621 `[project.scripts]` in `pyproject.toml` first, then
    `console_scripts` under `[options.entry_points]` in `setup.cfg`. The
    dynamic `setup.py` form cannot be parsed statically and is ignored.

    :param directory: the project root, holding the packaging metadata.
    :return: a mapping of each console-script name to its `module:function`
        target. Empty when the project declares none.
    """
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        data = parse_content(ConfigFormat.TOML, pyproject.read_text(encoding="utf-8"))
        scripts = data.get("project", {}).get("scripts", {})
        if scripts:
            return {str(name): str(target) for name, target in scripts.items()}

    setup_cfg = directory / "setup.cfg"
    if setup_cfg.is_file():
        # Deferred import: keeps configparser off the startup path of every CLI.
        from configparser import ConfigParser

        parser = ConfigParser()
        parser.read(setup_cfg, encoding="utf-8")
        raw = parser.get("options.entry_points", "console_scripts", fallback="")
        scripts = {}
        for line in raw.strip().splitlines():
            entry = line.strip()
            if not entry or "=" not in entry:
                continue
            name, _, target = entry.partition("=")
            scripts[name.strip()] = target.strip()
        return scripts

    return {}


def entry_point_package(target: str) -> str:
    """The top-level package an entry point target lives in.

    `orchard.cli:main` and `orchard:main` both answer `orchard`: the module
    path before the colon, cut at its first dot.
    """
    return target.partition(":")[0].split(".", 1)[0]


def locate_package_root(directory: Path, top_package: str) -> Path | None:
    """Find which directory must be on `sys.path` to import *top_package*.

    Handles the two common project layouts: the flat layout (the package sits
    directly under the project root) and the src layout (under a `src/`
    subdirectory). A package directory, with or without an `__init__.py`, and
    a single-module `{top_package}.py` all count.

    :param directory: the project root.
    :param top_package: the top-level package name, as
        {func}`entry_point_package` reads it off an entry point.
    :return: the directory to prepend to `sys.path`, or `None` when the
        package cannot be located on disk.
    """
    for root in (directory, directory / "src"):
        package = root / top_package
        if (package / "__init__.py").is_file():
            return root
        if (root / f"{top_package}.py").is_file():
            return root
        if package.is_dir():
            return root
    return None


def discover_package_init_files(directory: Path | None = None) -> list[Path]:
    """Discover the `__init__.py` of each package a project's console scripts enter.

    Reads the console scripts of the project in `directory` (the current
    directory by default) with {func}`read_project_scripts`, takes the top-level
    package of each entry point and locates it on disk with
    {func}`locate_package_root`, so a src-layout project resolves like a flat
    one. Each path is returned once, and only when it exists. Empty when the
    project declares no console script, or none of their packages is found.
    """
    if directory is None:
        directory = Path(".")
    scripts = read_project_scripts(directory)
    if not scripts:
        logger.warning(
            "No console script found in %s: looked for [project.scripts] in "
            "pyproject.toml and console_scripts in setup.cfg.",
            directory,
        )
        return []

    seen: set[Path] = set()
    paths: list[Path] = []
    for target in scripts.values():
        package = entry_point_package(target)
        root = locate_package_root(directory, package) or directory
        init_path = root / package / "__init__.py"
        if init_path in seen:
            continue
        seen.add(init_path)
        if init_path.is_file():
            paths.append(init_path)
        else:
            logger.warning("Package init not found: %s", init_path)
    return paths
