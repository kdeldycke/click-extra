# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

"""All we need to keep click-extra documentation up-to-date."""

from __future__ import annotations

from pathlib import Path

from tabulate import tabulate

from .pygments import lexer_map


def generate_lexer_table():
    """Generate a Markdown table mapping original lexers to their new ANSI variants."""
    table = []
    for orig_lexer, ansi_lexer in sorted(
        lexer_map.items(), key=lambda i: i[0].__qualname__
    ):
        table.append(
            [
                f"[`{orig_lexer.__qualname__}`](https://pygments.org/docs/lexers/#"
                f"{orig_lexer.__module__}.{orig_lexer.__qualname__})",
                f"{', '.join(f'`{a}`' for a in sorted(orig_lexer.aliases))}",
                f"{', '.join(f'`{a}`' for a in sorted(ansi_lexer.aliases))}",
            ]
        )
    output = tabulate(
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
    return output


def update_lexer_table():
    """Update the lexer table in the ``pygments.md`` documentation."""
    file = Path(__file__).parent.parent.joinpath("docs/pygments.md").resolve()
    content = file.read_text()

    # HTML comment delimiting the lexer table to update.
    start_tag = "<!-- lexer-table-start -->"
    end_tag = "<!-- lexer-table-end -->"

    # Extract pre- and post-content surrounding the table we're trying to update.
    pre_table, table_start = content.split(start_tag, 1)
    table_content, post_table = table_start.split(end_tag, 1)

    # Reconstruct the content with our updated table.
    file.write_text(
        f"{pre_table}"
        f"{start_tag}\n\n"
        f"{generate_lexer_table()}"
        f"\n\n{end_tag}"
        f"{post_table}"
    )


def update_docs():
    """Update all documentation files with dynamic content."""
    update_lexer_table()
