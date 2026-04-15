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

import colorsys
from pathlib import Path

import click

from . import (
    Choice,
    ClickException,
    Color,
    __version__,
    argument,
    echo,
    group,
    option,
    pass_context,
    style,
)
from .colorize import _nearest_256
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


def _render_palette() -> str:
    """Render a compact 256-color palette swatch.

    Each color is shown as a pair of cells (normal + bold) with foreground and background
    set to the same index, producing a solid color block. Layout: 16 system colors on the
    first row, then the 6x6x6 color cube in 6 rows of 36, then the 24-step grayscale
    ramp.
    """
    swatch = "\x1b[38;5;{0};48;5;{0}m\u2588\x1b[1m\u2588\x1b[m"
    lines: list[str] = []

    # Header.
    lines.append("  + " + "".join(f"{i:2}" for i in range(36)))

    # System colors (indices 0-15).
    lines.append("  0 " + "".join(swatch.format(i) for i in range(16)))

    # 6x6x6 color cube (indices 16-231).
    for row in range(6):
        start = row * 36 + 16
        cells = "".join(swatch.format(start + j) for j in range(36))
        lines.append(f"{start:3} {cells}")

    # Grayscale ramp (indices 232-255).
    lines.append("232 " + "".join(swatch.format(i) for i in range(232, 256)))

    return "\n".join(lines)


def _render_8color_table() -> str:
    """Render a compact 8-color foreground/background combination table.

    Shows all 8 standard foreground colors (normal and bold) against all 8 standard
    background colors. Each cell displays a sample string styled with the fg/bg
    combination.
    """
    sample = " gYw "
    reset = "\x1b[m"
    lines: list[str] = []

    # Header row: background color codes.
    lines.append(
        " " * 6
        + " " * len(sample)
        + "".join(f"{bg:^{len(sample)}}" for bg in range(40, 48))
    )

    for fg in range(30, 38):
        for is_bold in (False, True):
            fg_code = f"{'1;' if is_bold else ''}{fg}"
            # First cell: sample with foreground only (default background).
            label = f" {fg_code:>4} "
            first = f"\x1b[{fg_code}m{sample}{reset}"
            # Remaining cells: sample with foreground + each background.
            cells = "".join(
                f"\x1b[{fg_code};{bg}m{sample}{reset}" for bg in range(40, 48)
            )
            lines.append(f"{label}{first}{cells}")

    return "\n".join(lines)


def _render_gradient() -> str:
    """Render 24-bit RGB gradients alongside their 256-color quantized equivalents.

    Each gradient is shown in two rows: the top row uses 24-bit ``SGR 38;2;r;g;b``
    escape codes, the bottom row uses the quantized ``SGR 38;5;n`` index from
    ``_nearest_256``. Visible stepping in the quantized row reveals the palette
    resolution limits.
    """
    width = 72
    block = "\u2588"
    reset = "\x1b[m"
    lines: list[str] = []

    def row_pair(label: str, rgb_func):
        """Generate a 24-bit row and its quantized counterpart."""
        row_24 = ""
        row_8 = ""
        for i in range(width):
            r, g, b = rgb_func(i / (width - 1))
            ri, gi, bi = int(r * 255), int(g * 255), int(b * 255)
            row_24 += f"\x1b[38;2;{ri};{gi};{bi}m{block}{reset}"
            idx = _nearest_256(ri, gi, bi)
            row_8 += f"\x1b[38;5;{idx}m{block}{reset}"
        lines.append(f"{label}")
        lines.append(f"  24-bit {row_24}")
        lines.append(f"   8-bit {row_8}")

    # Rainbow: sweep hue at full saturation and value.
    row_pair("Rainbow:", lambda t: colorsys.hsv_to_rgb(t, 1.0, 1.0))

    lines.append("")

    # Grayscale: black to white.
    row_pair("Grayscale:", lambda t: (t, t, t))

    lines.append("")

    # Red channel ramp.
    row_pair("Red:", lambda t: (t, 0.0, 0.0))

    lines.append("")

    # Cyan (green + blue) ramp: stresses the color cube boundary.
    row_pair("Cyan:", lambda t: (0.0, t, t))

    return "\n".join(lines)


_MATRIX_CHOICES = ("colors", "styles", "palette", "8color", "gradient")
"""Valid choices for the ``render-matrix`` argument."""


@demo.command(name="render-matrix")
@argument("matrix", type=Choice(_MATRIX_CHOICES))
@pass_context
def render_matrix(ctx: click.Context, matrix: str) -> None:
    """Render a color or style matrix for terminal capability testing.

    MATRIX is one of: colors, styles, palette, 8color, gradient.

    colors: every foreground color against every background color.
    styles: every color with each text style (bold, dim, italic, etc.).
    palette: compact 256-color indexed swatch.
    8color: all standard foreground/background combinations.
    gradient: 24-bit RGB gradients vs. their 256-color quantized equivalents.
    """
    # Compact renderings that bypass the table formatter.
    if matrix == "palette":
        echo(_render_palette())
        return
    if matrix == "8color":
        echo(_render_8color_table())
        return
    if matrix == "gradient":
        echo(_render_gradient())
        return

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
    ancestor: click.Context | None = ctx
    while ancestor:
        if hasattr(ancestor, "print_table"):
            print_func = ancestor.print_table
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
