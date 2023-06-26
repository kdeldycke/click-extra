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
"""Automation to keep click-extra documentation up-to-date.

.. tip::

    When the module is called directly, it will update all documentation files in-place:

    .. code-block:: shell-session

        $ run python -m click_extra.docs_update

    See how it is `used in .github/workflows/docs.yaml workflow
    <https://github.com/kdeldycke/click-extra/blob/a978bd0/.github/workflows/docs.yaml#L35-L37>`_.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path
from textwrap import indent

from .platforms import ALL_GROUPS, EXTRA_GROUPS, NON_OVERLAPPING_GROUPS, Group
from .pygments import lexer_map
from .tabulate import tabulate


def replace_content(
    filepath: Path,
    start_tag: str,
    end_tag: str,
    new_content: str,
) -> None:
    """Replace in the provided file the content surrounded by the provided tags."""
    filepath = filepath.resolve()
    assert filepath.exists(), f"File {filepath} does not exist."
    assert filepath.is_file(), f"File {filepath} is not a file."

    orig_content = filepath.read_text()

    # Extract pre- and post-content surrounding the tags.
    pre_content, table_start = orig_content.split(start_tag, 1)
    _, post_content = table_start.split(end_tag, 1)

    # Reconstruct the content with our updated table.
    filepath.write_text(
        f"{pre_content}{start_tag}{new_content}{end_tag}{post_content}",
    )


def generate_lexer_table() -> str:
    """Generate a Markdown table mapping original Pygments' lexers to their new ANSI
    variants implemented by Click Extra."""
    table = []
    for orig_lexer, ansi_lexer in sorted(
        lexer_map.items(),
        key=lambda i: i[0].__qualname__,
    ):
        table.append(
            [
                f"[`{orig_lexer.__qualname__}`](https://pygments.org/docs/lexers/#"
                f"{orig_lexer.__module__}.{orig_lexer.__qualname__})",
                f"{', '.join(f'`{a}`' for a in sorted(orig_lexer.aliases))}",
                f"{', '.join(f'`{a}`' for a in sorted(ansi_lexer.aliases))}",
            ],
        )
    return tabulate.tabulate(
        table,
        headers=[
            "Original Lexer",
            "Original IDs",
            "ANSI variants",
        ],
        tablefmt="github",
        colalign=["left", "left", "left"],
        disable_numparse=True,
    )


def generate_platforms_graph(
    graph_id: str,
    description: str,
    groups: frozenset[Group],
) -> str:
    """Generates an `Euler diagram <https://xkcd.com/2721/>`_ of platform and their
    grouping.

    Euler diagrams are
    `not supported by mermaid yet <https://github.com/mermaid-js/mermaid/issues/2583>`_
    so we fallback on a flowchart without arrows.

    Returns a ready to use and properly indented MyST block.
    """
    INDENT = " " * 4
    subgraphs = set()

    # Create one subgraph per group.
    for group in sorted(groups, key=lambda g: g.id):
        nodes = set()
        for platform in group:
            # Make the node ID unique for overlapping groups.
            nodes.add(
                f"{group.id}_{platform.id}"
                f"(<code>{platform.id}</code><br/><em>{html.escape(platform.name)}</em>)",
            )
        subgraphs.add(
            f"subgraph <code>click_extra.platforms.{group.id.upper()}</code>"
            "<br/>"
            f"<em>{group.name}</em>"
            "\n" + indent("\n".join(sorted(nodes)), INDENT) + "\nend",
        )

    # Wrap the Mermaid code into a MyST block.
    return "\n".join(
        (
            # Use attributes blocks extension to add a title.
            ('{caption="' f"`click_extra.platforms.{graph_id}` - {description}" '"}'),
            "```mermaid",
            ":zoom:",
            "flowchart",
            indent("\n".join(sorted(subgraphs)), INDENT),
            "```",
        ),
    )


def update_docs() -> None:
    """Update documentation with dynamic content."""
    project_root = Path(__file__).parent.parent

    # Update the lexer table in Sphinx's documentation.
    replace_content(
        project_root.joinpath("docs/pygments.md"),
        "<!-- lexer-table-start -->\n\n",
        "\n\n<!-- lexer-table-end -->",
        generate_lexer_table(),
    )

    # TODO: Replace this hard-coded dict by allowing Group dataclass to group
    # other groups.
    all_groups = (
        {
            "id": "NON_OVERLAPPING_GROUPS",
            "description": "Non-overlapping groups.",
            "groups": NON_OVERLAPPING_GROUPS,
        },
        {
            "id": "EXTRA_GROUPS",
            "description": "Overlapping groups, defined for convenience.",
            "groups": EXTRA_GROUPS,
        },
    )
    assert frozenset(g for groups in all_groups for g in groups["groups"]) == ALL_GROUPS

    # Update the platform diagram in Sphinx's documentation.
    platform_doc = project_root.joinpath("docs/platforms.md")
    for top_groups in all_groups:
        replace_content(
            platform_doc,
            f"<!-- {top_groups['id']}-graph-start -->\n\n",
            f"\n\n<!-- {top_groups['id']}-graph-end -->",
            generate_platforms_graph(
                top_groups["id"],  # type: ignore[arg-type]
                top_groups["description"],  # type: ignore[arg-type]
                top_groups["groups"],  # type: ignore[arg-type]
            ),
        )


if __name__ == "__main__":
    sys.exit(update_docs())  # type: ignore[func-returns-value]
