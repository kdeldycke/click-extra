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

from functools import cache, partial
from pathlib import Path

from click import ClickException, echo

from .config import get_tool_config
from .decorators import argument, group, option
from .prebake import (
    discover_package_init_files,
    prebake_dunder,
    prebake_dunders,
    prebake_version,
)
from .version import BUILD_RESOLVERS, GIT_RESOLVERS, dunder_name

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable


def _resolve_paths(module: Path | None) -> list[Path]:
    """Resolve target `__init__.py` paths.

    Precedence: an explicit `--module`, then the `[tool.click-extra.prebake]`
    `module` config value, then the package behind the console scripts of
    `pyproject.toml` or `setup.cfg`.
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
            "[tool.click-extra.prebake] module, or declare a console script in "
            "pyproject.toml or setup.cfg."
        )
    return paths


_module_option = option(
    "--module",
    type=Path,
    default=None,
    help="Path to __init__.py to modify. Auto-discovered from the console scripts "
    "in pyproject.toml or setup.cfg if not provided.",
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
        git_hash = GIT_RESOLVERS["git_short_hash"](None)
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
    # The dunders are stripped before being added back, so both spellings of
    # NAME resolve to the one the version option reads.
    dunder = dunder_name(name.removeprefix("__").removesuffix("__"))
    for init_path in _resolve_paths(module):
        baked = prebake_dunder(init_path, dunder, value)
        if baked:
            echo(f"Pre-baked {init_path}: {dunder} = {baked!r}")
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
    # command, so it takes no directory and always answers. Each resolver is
    # cached: a value is computed once per run, however many files are baked.
    fields: dict[str, Callable[[], str | None]] = {
        **{
            dunder_name(field_id): cache(partial(resolve, None))
            for field_id, resolve in GIT_RESOLVERS.items()
        },
        **{
            dunder_name(field_id): cache(resolve)
            for field_id, resolve in BUILD_RESOLVERS.items()
        },
    }
    git_hash = fields[dunder_name("git_short_hash")]()

    changed = False
    for init_path in _resolve_paths(module):
        # Pre-bake __version__ with git short hash.
        if git_hash:
            baked = prebake_version(init_path, local_version=git_hash)
            if baked:
                echo(f"Pre-baked {init_path}: __version__ = {baked!r}")
                changed = True
        for name, value in prebake_dunders(init_path, fields).items():
            echo(f"Pre-baked {init_path}: {name} = {value!r}")
            changed = True

    if not changed:
        echo("No changes made.")
