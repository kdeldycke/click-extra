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
"""Find a local project's entry point and packages from its packaging metadata.

{func}`read_project_scripts` lists the console scripts a project declares,
{func}`entry_point_package` names the top-level package of an entry point, and
{func}`locate_package_root` finds the directory a package imports from, whether
the project uses the flat or the src layout.

{func}`resolve_entry_point` combines them into the one entry point of a project,
under one ambiguity rule. The `wrap` command runs a project directory through
it, and {func}`detect_source_package` finds the package the `convert-to-myst`
command converts. {func}`discover_package_init_files` finds the `__init__.py`
of every package the scripts enter, for the `prebake` commands to bake.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

from .config.formats import ConfigFormat, parse_content

logger = logging.getLogger(__name__)

_SCRIPT_SOURCES = "[project.scripts] in pyproject.toml and console_scripts in setup.cfg"
"""Where {func}`read_project_scripts` looks, named when a project declares none."""


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
        data = parse_content(ConfigFormat.TOML, pyproject.read_text(encoding="UTF-8"))
        scripts = data.get("project", {}).get("scripts", {})
        if scripts:
            return {str(name): str(target) for name, target in scripts.items()}

    setup_cfg = directory / "setup.cfg"
    if setup_cfg.is_file():
        # Deferred import: keeps configparser off the startup path of every CLI.
        from configparser import ConfigParser

        parser = ConfigParser()
        parser.read(setup_cfg, encoding="UTF-8")
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

    :param target: the entry point, as `module:function`.
    :return: the top-level package name.
    """
    return target.partition(":")[0].split(".", 1)[0]


def locate_package_root(directory: Path, top_package: str) -> Path | None:
    """Find which directory must be on `sys.path` to import `top_package`.

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
        if (root / top_package).is_dir() or (root / f"{top_package}.py").is_file():
            return root
    return None


class ProjectEntryPoint(NamedTuple):
    """The console-script entry point a project directory resolves to."""

    target: str
    """The `module:function` target the console scripts name."""

    root: Path | None
    """The directory to put on `sys.path` to import the target, or `None` when
    its package is not on disk."""

    @property
    def module(self) -> str:
        """The module path of the target, before its colon."""
        return self.target.partition(":")[0]

    @property
    def function(self) -> str:
        """The function name of the target, after its colon."""
        return self.target.partition(":")[2]

    @property
    def package(self) -> str:
        """The top-level package of the target, see {func}`entry_point_package`."""
        return entry_point_package(self.target)


def resolve_entry_point(directory: Path) -> ProjectEntryPoint:
    """Resolve the one console-script entry point of the project in `directory`.

    Reads the console scripts with {func}`read_project_scripts`, and locates
    the package of their target with {func}`locate_package_root`.

    The ambiguity rule: the console scripts must name a single
    `module:function` target. Several script names for one target, like a long
    name and its short alias, count as one. Two targets are ambiguous even when
    they live in one package: nothing tells which function the project means.

    :param directory: the project root, holding its `pyproject.toml` or
        `setup.cfg`.
    :return: the entry point, whose `root` is `None` when its package is not
        on disk.
    :raises ValueError: When the project declares no console script, or
        scripts naming several targets.
    """
    scripts = read_project_scripts(directory)
    if not scripts:
        msg = (
            f"No console-script entry point found in {directory.resolve()}. Looked"
            f" for {_SCRIPT_SOURCES}."
        )
        raise ValueError(msg)

    targets = sorted(set(scripts.values()))
    if len(targets) > 1:
        listing = ", ".join(
            f"{name} = {target}" for name, target in sorted(scripts.items())
        )
        msg = f"Multiple console scripts in {directory.resolve()}: {listing}."
        raise ValueError(msg)

    target = targets[0]
    return ProjectEntryPoint(
        target, locate_package_root(directory, entry_point_package(target))
    )


def detect_source_package(directory: Path | None = None) -> Path:
    """Locate the project's source package from its script entry point.

    Resolves the entry point with
    {func}`~click_extra.project.resolve_entry_point`, under its ambiguity rule,
    and derives the top-level package of its target (`"pkg.cli:main"` gives
    `pkg`), so the `convert-to-myst` command can run bare from a project root.
    The package is located under the project root or its `src/` folder, see
    {func}`~click_extra.project.locate_package_root`, and assumed under the
    project root when it is in neither.

    :param directory: The project root, holding its `pyproject.toml` or
        `setup.cfg`. Defaults to the current working directory.
    :return: Path of the detected package directory.
    :raises ValueError: When the project declares no script entry point, or
        scripts naming several targets.
    """
    if directory is None:
        directory = Path()

    try:
        entry_point = resolve_entry_point(directory)
    except ValueError as error:
        msg = (
            f"Cannot auto-detect the source directory: {error}"
            " Specify a directory argument."
        )
        raise ValueError(msg) from error
    return (entry_point.root or directory) / entry_point.package


def discover_package_init_files(directory: Path | None = None) -> list[Path]:
    """Discover the `__init__.py` of each package a project's console scripts enter.

    Reads the console scripts of the project in `directory` with
    {func}`read_project_scripts`, takes the top-level package of each entry
    point and locates it on disk with {func}`locate_package_root`, so a
    src-layout project resolves like a flat one.

    :param directory: the project root. `None` reads the current directory.
    :return: each `__init__.py` found, once, in entry point order. Empty when
        the project declares no console script, or none of their packages is
        found.
    """
    if directory is None:
        directory = Path()
    scripts = read_project_scripts(directory)
    if not scripts:
        logger.warning(
            "No console script found in %s: looked for %s.", directory, _SCRIPT_SOURCES
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
