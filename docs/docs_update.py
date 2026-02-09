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
"""Regenerate dynamic documentation content.

Auto-detected and executed by the upstream ``docs.yaml`` reusable workflow.
"""

from pathlib import Path

from click_extra.pygments import lexer_map
from click_extra.table import TableFormat, render_table

project_root = Path(__file__).parent.parent

# Generate the Markdown table mapping Pygments lexers to their ANSI variants.
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
        ],
    )
new_table = render_table(
    table,
    table_format=TableFormat.GITHUB,
    headers=["Original Lexer", "Original IDs", "ANSI variants"],
    colalign=["left", "left", "left"],
)

# Replace the lexer table between markers in pygments.md.
start_tag = "<!-- lexer-table-start -->\n\n"
end_tag = "\n\n<!-- lexer-table-end -->"
pygments_md = project_root.joinpath("docs/pygments.md")
content = pygments_md.read_text()
pre, rest = content.split(start_tag, 1)
_, post = rest.split(end_tag, 1)
pygments_md.write_text(f"{pre}{start_tag}{new_table}{end_tag}{post}")
