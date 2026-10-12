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

"""The `prebake` command group of the `click-extra` CLI.

Fills the empty `__version__` and `__<field>__` dunders of a package at build
time, from the Git state and the build host, through
{mod}`click_extra.prebake`. {mod}`click_extra.cli` registers the group on the
root command.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from click import ClickException, echo

from .config import get_tool_config
from .decorators import argument, group, option
from .prebake import (
    _find_dunder_str,
    discover_package_init_files,
    prebake_dunder,
    prebake_version,
)
from .version import BUILD_RESOLVERS, GIT_FIELDS, GIT_RESOLVERS, run_git

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


def _resolve_paths(module: Path | None) -> list[Path]:
    """Resolve target `__init__.py` paths.

    Precedence: an explicit `--module`, then the `[tool.click-extra.prebake]`
    `module` config value, then `[project.scripts]` auto-discovery.
    """
    if module:
        return [module]
    config = get_tool_config()
    if config and config.prebake.module:
        return [Path(config.prebake.module)]
    paths = discover_package_init_files()
    if not paths:
        raise ClickException(
            "No __init__.py found. Pass --module explicitly, set "
            "[tool.click-extra.prebake] module, or add [project.scripts] to "
            "pyproject.toml."
        )
    return paths


def _to_dunder(name: str) -> str:
    """Ensure *name* has `__` prefix and suffix."""
    if not name.startswith("__"):
        name = f"__{name}"
    if not name.endswith("__"):
        name = f"{name}__"
    return name


def _bake_dunder_fields(
    init_path: Path,
    fields: Iterable[tuple[str, Callable[[], str | None]]],
) -> bool:
    """Fill every empty `__<field>__` placeholder of `init_path` that resolves.

    Each field is resolved only when its placeholder is present and still
    empty, so a value already baked is never recomputed and a resolver that
    cannot answer (no git repository, no tag) leaves its placeholder alone.

    :param fields: `(field name, resolver)` pairs, each resolver answering the
        value to bake, or `None` when it has none.
    :return: whether the file was written.
    """
    changed = False
    source = init_path.read_text(encoding="utf-8")
    for field_name, resolve in fields:
        dunder_name = f"__{field_name}__"
        node = _find_dunder_str(source, dunder_name)
        if node is None:
            continue
        if node.value:
            echo(f"Skipped {init_path}: {dunder_name} already set")
            continue
        value = resolve()
        if not value:
            echo(f"Skipped {init_path}: {dunder_name} (no value)")
            continue
        baked = prebake_dunder(init_path, dunder_name, value)
        if baked:
            echo(f"Pre-baked {init_path}: {dunder_name} = {baked!r}")
            changed = True
            # Re-read the source after each write so AST offsets stay valid.
            source = init_path.read_text(encoding="utf-8")
    return changed


_module_option = option(
    "--module",
    type=Path,
    default=None,
    help="Path to __init__.py to modify. "
    "Auto-discovered from [project.scripts] if not provided.",
)


@group()
def prebake():
    """Pre-bake build-time metadata into Python source files."""


@prebake.command()
@option(
    "--hash",
    "git_hash",
    default=None,
    help="Git short hash to append. Auto-detected from HEAD if not provided.",
)
@_module_option
def version(git_hash: str | None, module: Path | None) -> None:
    """Inject Git commit hash into `__version__`.

    Appends the Git short hash as a PEP 440 local version identifier
    (for example `1.0.0.dev0` becomes `1.0.0.dev0+abc1234`).

    Only modifies `.dev` versions without an existing `+` suffix.
    Release versions and already pre-baked versions are left untouched.
    """
    if git_hash is None:
        git_hash = run_git(*GIT_FIELDS["git_short_hash"])
        if not git_hash:
            raise ClickException(
                "No --hash provided and Git hash auto-detection failed. "
                "Pass --hash explicitly or run from a Git repository."
            )

    for init_path in _resolve_paths(module):
        baked = prebake_version(init_path, local_version=git_hash)
        if baked:
            echo(f"Pre-baked {init_path}: {baked}")
        else:
            echo(f"No changes to {init_path}")


@prebake.command()
@argument("name")
@argument("value")
@_module_option
def field(name: str, module: Path | None, value: str) -> None:
    """Replace an empty dunder variable with a value.

    NAME is the template field name (like `git_tag_sha`) or the full
    dunder name (like `__git_tag_sha__`). Double underscores are added
    automatically when missing.

    VALUE is the string to inject.

    Only modifies variables that are currently empty. Already-populated
    values are left untouched (idempotent).
    """
    dunder_name = _to_dunder(name)
    for init_path in _resolve_paths(module):
        baked = prebake_dunder(init_path, dunder_name, value)
        if baked:
            echo(f"Pre-baked {init_path}: {dunder_name} = {baked!r}")
        else:
            echo(f"No changes to {init_path}")


@prebake.command(name="all")
@_module_option
def all_fields(module: Path | None) -> None:
    """Pre-bake `__version__`, all git fields and all build fields in one pass.

    Scans each target file for empty `__<field>__` dunder placeholders,
    resolves their values from the current Git state and build host, and
    injects them.

    Also appends the Git short hash to `.dev` versions in
    `__version__` (same as `prebake version`).

    \b
    Supported git fields:
        git_branch, git_long_hash, git_short_hash, git_date, git_tag

    \b
    Supported build fields:
        build_time, build_os, build_target, build_target_arch

    \b
    Additional computed fields (`__git_tag_sha__`, `__git_distance__`,
    `__git_dirty__`) are baked if their dunder placeholder exists and a git
    resolution is available. Fields without a placeholder in the source file
    are skipped silently.
    """
    # The field-to-resolver tables live in click_extra.version, so adding a
    # field there needs no matching edit here. A git resolver runs in the
    # current directory; a build resolver describes the host running this
    # command, so it takes no directory and always answers.
    fields: list[tuple[str, Callable[[], str | None]]] = [
        *((name, partial(resolve, None)) for name, resolve in GIT_RESOLVERS.items()),
        *BUILD_RESOLVERS.items(),
    ]

    changed = False
    for init_path in _resolve_paths(module):
        # Pre-bake __version__ with git short hash.
        git_hash = run_git(*GIT_FIELDS["git_short_hash"])
        if git_hash:
            baked = prebake_version(init_path, local_version=git_hash)
            if baked:
                echo(f"Pre-baked {init_path}: __version__ = {baked!r}")
                changed = True
        changed |= _bake_dunder_fields(init_path, fields)

    if not changed:
        echo("No changes made.")
