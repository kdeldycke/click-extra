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

import sys
from pathlib import Path

from .tabulate import tabulate


def replace_content(
    filepath: Path,
    new_content: str,
    start_tag: str,
    end_tag: str | None = None,
) -> None:
    """Replace in a file the content surrounded by the provided start end end tags.

    If no end tag is provided, the whole content found after the start tag will be
    replaced.
    """
    filepath = filepath.resolve()
    assert filepath.exists(), f"File {filepath} does not exist."
    assert filepath.is_file(), f"File {filepath} is not a file."

    orig_content = filepath.read_text()

    # Extract pre-content before the start tag.
    assert start_tag, "Start tag must be empty."
    assert start_tag in orig_content, f"Start tag {start_tag!r} not found in content."
    pre_content, table_start = orig_content.split(start_tag, 1)

    # Extract the post-content after the end tag.
    if end_tag:
        _, post_content = table_start.split(end_tag, 1)
    # If no end tag is provided, we're going to replace the whole content found after
    # the start tag.
    else:
        end_tag = ""
        post_content = ""

    # Reconstruct the content with our updated table.
    filepath.write_text(
        f"{pre_content}{start_tag}{new_content}{end_tag}{post_content}",
    )


def generate_lexer_table() -> str:
    """Generate a Markdown table mapping original Pygments' lexers to their new ANSI
    variants implemented by Click Extra.

    Import ``pygments.lexer_map`` on function execution, to avoid referencing the
    optional ``pygments`` extra dependency.
    """
    from .pygments import lexer_map

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


def update_docs() -> None:
    """Update documentation with dynamic content."""
    project_root = Path(__file__).parent.parent

    # Update the lexer table in Sphinx's documentation.
    replace_content(
        project_root.joinpath("docs/pygments.md"),
        generate_lexer_table(),
        "<!-- lexer-table-start -->\n\n",
        "\n\n<!-- lexer-table-end -->",
    )


if __name__ == "__main__":
    sys.exit(update_docs())  # type: ignore[func-returns-value]
