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

"""Describe the columns of a table, and select among them.

A {class}`ColumnSpec` names a column, labels it and documents it, so one
declaration feeds the rendered header, the `--columns` and `--sort-by`
options and the documentation table. {mod}`click_extra.table` renders the
columns and {mod}`click_extra.parameters` declares the `--params` table's: a
home below both is what lets each import the other's half without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from typing import Any, Literal

    ColumnWidth = int | Literal["auto"] | None
    """Width limit of a single column: a character count, `auto`, or no limit."""


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """Rich description of a single column in a rendered table.

    Three fields, all required-by-convention even though `description` defaults to
    empty so quick prototypes do not have to write a sentence for every column:

    - `id`: stable, snake_case identifier used by `--columns` to address the column,
      to key structured-format serializations, and to thread state through
      {data}`click_extra.context.COLUMNS`.
    - `label`: the human-readable header shown at the top of the rendered table.
    - `description`: a MyST/Markdown blurb describing what the column represents.
      Used to auto-generate the column reference in the documentation.

    The other fields tune presentation and sorting: `max_width`, `optional` and
    `sortable`.

    ```{note}
    Frozen + slots: instances are immutable and lightweight. Tuples of
    `ColumnSpec` are intended to be defined as module-level constants
    (like {data}`click_extra.parameters.ShowParamsOption.TABLE_HEADERS`).
    ```
    """

    id: str
    """Stable, snake_case identifier addressing this column from CLI flags and code."""

    label: str
    """Human-readable header label rendered at the top of the table."""

    description: str = ""
    """MyST/Markdown description of what the column carries.

    Used to auto-generate the *Available columns* section in the docs via the
    `show_params_columns_table` MyST substitution. Plain text without inline
    markup is fine: links and emphasis are optional sugar."""

    max_width: ColumnWidth = None
    """Width limit of this column, as a character count or
    {data}`~click_extra.table.AUTO_WIDTH`.

    Cells longer than the limit wrap onto several lines, in the formats able to
    render that (see {data}`~click_extra.table.WRAPPABLE_FORMATS`). `None`, the
    default, lets the column take whatever width its widest cell needs.

    Declaring the width here rather than passing a positional list to
    {func}`~click_extra.table.render_table` keeps it attached to its column, so it
    survives a `--columns` projection that drops or reorders columns."""

    optional: bool = False
    """Whether the column is left out of the table until `--columns` asks for it.

    A column carrying long free-form prose costs every other column its width once
    it joins the default projection, which is a poor trade for a reader who did not
    ask for it. Marking it optional keeps it out of the unprojected table while
    leaving it addressable by ID, so a consumer that wants it (a structured-format
    export feeding a machine, typically) selects it explicitly."""

    sortable: bool = True
    """Whether `--sort-by` offers this column and a sort selection matches it.

    A column that only annotates its row (free-form notes, a path) still needs a
    place in the table layout, so a sort key knows where the sortable columns
    sit, without becoming a sort choice itself."""


def render_columns_markdown_table(columns: Iterable[ColumnSpec]) -> str:
    """Render an iterable of {class}`ColumnSpec` as a 2-column Markdown table.

    Output shape::

        | Column | Description |
        | :--- | :--- |
        | `Label` | description |
        ...

    Suitable for inlining into MyST documents via `myst_substitutions` so the
    *Available columns* reference can be auto-generated from a single source of
    truth.
    """
    lines = ["| Column | Description |", "| :--- | :--- |"]
    for col in columns:
        # Pipe characters in descriptions would break the markdown row: escape them.
        description = col.description.replace("|", "\\|")
        lines.append(f"| `{col.label}` | {description} |")
    return "\n".join(lines)


def select_columns(
    columns: Sequence[ColumnSpec],
    selected_ids: Sequence[str] | None,
) -> tuple[ColumnSpec, ...]:
    """Filter and reorder `columns` according to `selected_ids`.

    Returns `columns` unchanged when `selected_ids` is falsy (no projection).
    Otherwise yields the matching {class}`ColumnSpec` in the order `selected_ids`
    specifies, SQL-`SELECT`-style. Raises `KeyError` for an unknown ID. A
    selection reaching here through `--columns` is already checked against the
    registry by {class}`~click_extra.types.MultiChoice`, so that guards a caller
    assembling `selected_ids` on its own.
    """
    if not selected_ids:
        return tuple(columns)
    by_id = {c.id: c for c in columns}
    return tuple(by_id[col_id] for col_id in selected_ids)


def select_row(
    row: Mapping[str, Any],
    selected_ids: Sequence[str] | None,
    canonical_ids: Sequence[str],
) -> tuple:
    """Build a positional row by reading cells from `row` in the selection order.

    Falls back to `canonical_ids` when `selected_ids` is empty / unset, so the
    row preserves its canonical column order in the absence of any user selection.
    """
    ids = selected_ids or canonical_ids
    return tuple(row[col_id] for col_id in ids)
