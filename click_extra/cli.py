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
"""Click Extra CLI with pre-baking utilities."""

from __future__ import annotations

from pathlib import Path

import click

from . import (
    Choice,
    ClickException,
    Color,
    argument,
    echo,
    group,
    option,
    pass_context,
    style,
)
from .table import print_table
from .version import (
    GIT_FIELDS,
    _find_dunder_str,
    discover_package_init_files,
    prebake_dunder,
    prebake_version,
    run_git,
)


def _resolve_paths(module: Path | None) -> list[Path]:
    """Resolve target ``__init__.py`` paths from ``--module`` or auto-discovery."""
    if module:
        return [module]
    paths = discover_package_init_files()
    if not paths:
        raise ClickException(
            "No __init__.py found. Pass --module explicitly or add "
            "[project.scripts] to pyproject.toml."
        )
    return paths


def _to_dunder(name: str) -> str:
    """Ensure *name* has ``__`` prefix and suffix."""
    if not name.startswith("__"):
        name = f"__{name}"
    if not name.endswith("__"):
        name = f"{name}__"
    return name


_module_option = option(
    "--module",
    type=Path,
    default=None,
    help="Path to __init__.py to modify. "
    "Auto-discovered from [project.scripts] if not provided.",
)


@group(name="click-extra", version_fields={"prog_name": "Click Extra"})
def demo():
    """Click Extra CLI."""


_ALL_STYLES = (
    "bold",
    "dim",
    "underline",
    "overline",
    "italic",
    "blink",
    "reverse",
    "strikethrough",
)
"""ANSI text style names supported by ``click.style()``."""

_ALL_COLORS = sorted(Color._dict.values())  # type: ignore[attr-defined]
"""All color names from ``click_extra.Color``."""


@demo.command(name="render-matrix")
@option(
    "--matrix",
    type=Choice(["colors", "styles"]),
    required=True,
    help="Which matrix to render.",
)
@pass_context
def render_matrix(ctx: click.Context, matrix: str) -> None:
    """Render a color or style matrix for terminal capability testing.

    The ``colors`` matrix shows every foreground color against every
    background color. The ``styles`` matrix shows every color with each
    text style (bold, dim, italic, etc.).

    Respects the global ``--table-format`` option.
    """
    table: list[list[str]] = []

    if matrix == "colors":
        headers = ["Foreground \u21b4 \\ Background \u2192"] + _ALL_COLORS
        for fg in _ALL_COLORS:
            row = [style(fg, fg=fg)]
            row.extend(style(fg, fg=fg, bg=bg) for bg in _ALL_COLORS)
            table.append(row)

    elif matrix == "styles":
        headers = ["Color \u21b4 \\ Style \u2192"] + list(_ALL_STYLES)
        for color_name in _ALL_COLORS:
            row = [style(color_name, fg=color_name)]
            for prop in _ALL_STYLES:
                row.append(style(color_name, fg=color_name, **{prop: True}))
            table.append(row)

    # Walk up the context chain to find ctx.print_table (set by
    # --table-format on the parent group). Fall back to the bare
    # print_table for standalone invocation (e.g. in docs).
    print_func = print_table
    ancestor = ctx
    while ancestor:
        if hasattr(ancestor, "print_table"):
            print_func = ancestor.print_table  # type: ignore[assignment]
            break
        ancestor = ancestor.parent
    print_func(table, headers=headers)


@demo.group()
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
    """Inject Git commit hash into ``__version__``.

    Appends the Git short hash as a PEP 440 local version identifier
    (e.g. ``1.0.0.dev0`` becomes ``1.0.0.dev0+abc1234``).

    Only modifies ``.dev`` versions without an existing ``+`` suffix.
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

    NAME is the template field name (e.g. ``git_tag_sha``) or the full
    dunder name (e.g. ``__git_tag_sha__``). Double underscores are added
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
    """Pre-bake ``__version__`` and all git fields in one pass.

    Scans each target file for empty ``__<field>__`` dunder placeholders,
    resolves their values from the current Git state, and injects them.

    Also appends the Git short hash to ``.dev`` versions in
    ``__version__`` (same as ``prebake version``).

    \b
    Supported git fields:
        git_branch, git_long_hash, git_short_hash, git_date, git_tag

    \b
    Additional fields (e.g. ``__git_tag_sha__``) are baked if their
    dunder placeholder exists and a git resolution is available. Fields
    without a placeholder in the source file are skipped silently.
    """
    paths = _resolve_paths(module)
    changed = False

    for init_path in paths:
        source = init_path.read_text(encoding="utf-8")

        # Pre-bake __version__ with git short hash.
        git_hash = run_git(*GIT_FIELDS["git_short_hash"])
        if git_hash:
            baked = prebake_version(init_path, local_version=git_hash)
            if baked:
                echo(f"Pre-baked {init_path}: __version__ = {baked!r}")
                changed = True

        # Pre-bake each git field that has an empty dunder placeholder.
        resolved: dict[str, str] = {}
        for field_name, git_args in GIT_FIELDS.items():
            dunder_name = f"__{field_name}__"
            node = _find_dunder_str(source, dunder_name)
            if node is None:
                continue
            if node.value:
                echo(f"Skipped {init_path}: {dunder_name} already set")
                continue
            value = run_git(*git_args)
            if not value:
                echo(f"Skipped {init_path}: {dunder_name} (no git value)")
                continue
            resolved[field_name] = value
            baked = prebake_dunder(init_path, dunder_name, value)
            if baked:
                echo(f"Pre-baked {init_path}: {dunder_name} = {baked!r}")
                changed = True
                # Re-read source after each write so AST offsets stay valid.
                source = init_path.read_text(encoding="utf-8")

        # Handle git_tag_sha: resolved from the tag, not a direct git command.
        dunder_name = "__git_tag_sha__"
        node = _find_dunder_str(source, dunder_name)
        if node is not None and not node.value:
            tag = resolved.get("git_tag")
            if tag:
                sha = run_git("rev-list", "-1", tag)
                if sha:
                    baked = prebake_dunder(init_path, dunder_name, sha)
                    if baked:
                        echo(f"Pre-baked {init_path}: {dunder_name} = {baked!r}")
                        changed = True

    if not changed:
        echo("No changes made.")
