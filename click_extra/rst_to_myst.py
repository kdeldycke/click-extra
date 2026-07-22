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
"""Convert `sphinx-apidoc` RST output to MyST markdown.

```{note}
The converter handles only the narrow RST subset that `sphinx-apidoc`
generates: section headings (title + underline), `automodule` directives
with indented options, and structural headers like `Submodules`.

Autodoc directives cannot be used as native MyST directives because they
perform internal rST nested parsing that requires an rST parser context
only ``{eval-rst}`` provides. See [MyST-Parser #587](https://github.com/executablebooks/MyST-Parser/issues/587).
```
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

#: RST underline characters mapped to Markdown heading levels.
_RST_UNDERLINE_LEVELS: dict[str, str] = {
    "=": "#",
    "-": "##",
    "~": "###",
    "^": "####",
}


def _clean_heading(title: str) -> str:
    """Normalize an RST heading for markdown.

    Strips RST-specific backslash escapes (e.g. `\\_` used to prevent
    reference interpretation) and wraps qualified Python identifiers in
    backticks so they render as code.

    ```{note}
    `sphinx-apidoc` produces headings like
    `meta\\_package\\_manager.managers.apm module`.  The backslash
    escapes are necessary in RST but meaningless in markdown, where they
    cause a tug-of-war with `mdformat` (which strips them on every
    reformat pass).  Wrapping the identifier in backticks makes the
    escaping moot and produces cleaner output.
    ```
    """
    # Strip RST backslash-escapes (\_  →  _).
    title = title.replace("\\_", "_")
    # Wrap Python identifiers in backticks when followed by "module" or "package".
    return re.sub(r"^([\w.]+) (module|package)$", r"`\1` \2", title)


def convert_apidoc_rst_to_myst(content: str) -> str:
    """Convert `sphinx-apidoc` RST to MyST markdown with ``{eval-rst}`` blocks.

    :param content: RST content produced by `sphinx-apidoc`.
    :return: Equivalent MyST markdown.
    """
    lines = content.splitlines()
    result: list[str] = []
    i = 0

    while i < len(lines):
        # Section header: a text line followed by a line of identical underline chars.
        if (
            i + 1 < len(lines)
            and lines[i + 1]
            and lines[i + 1][0] in _RST_UNDERLINE_LEVELS
            and re.fullmatch(re.escape(lines[i + 1][0]) + r"+", lines[i + 1])
        ):
            level = _RST_UNDERLINE_LEVELS[lines[i + 1][0]]
            title = _clean_heading(lines[i])
            result.append(f"{level} {title}")
            i += 2
            continue

        # Directive block: starts with ".. directive::" and includes indented body.
        if lines[i].startswith(".. "):
            block = [lines[i]]
            i += 1
            while i < len(lines):
                if lines[i].startswith("   "):
                    block.append(lines[i])
                    i += 1
                elif not lines[i].strip():
                    # Blank line: include if the next line is still indented.
                    if i + 1 < len(lines) and lines[i + 1].startswith("   "):
                        block.append(lines[i])
                        i += 1
                    else:
                        break
                else:
                    break
            result.append("```{eval-rst}")
            result.extend(block)
            result.append("```")
            continue

        result.append(lines[i])
        i += 1

    return "\n".join(result) + "\n"


def convert_rst_files_in_directory(directory: Path) -> list[Path]:
    """Convert `sphinx-apidoc` RST files to MyST markdown in the given directory.

    For each `.rst` file containing `.. automodule::` directives:

    - If a `.md` file with the same stem exists, delete the `.rst` (the
      existing markdown takes precedence).
    - Otherwise, convert the RST content to MyST and write a `.md` file,
      then delete the `.rst`.

    :param directory: Directory to scan for `.rst` files.
    :return: List of newly created `.md` file paths.
    """
    converted: list[Path] = []

    for rst_path in sorted(directory.glob("*.rst")):
        content = rst_path.read_text(encoding="utf-8")

        # Only process files that contain automodule directives (sphinx-apidoc stubs).
        if ".. automodule::" not in content:
            logging.debug(f"Skipping {rst_path.name}: no automodule directive found.")
            continue

        md_path = rst_path.with_suffix(".md")

        if md_path.exists():
            logging.info(
                f"Deleting {rst_path.name}: MyST equivalent {md_path.name} exists."
            )
            rst_path.unlink()
            continue

        myst_content = convert_apidoc_rst_to_myst(content)
        md_path.write_text(myst_content, encoding="utf-8")
        rst_path.unlink()
        converted.append(md_path)
        logging.info(f"Converted {rst_path.name} → {md_path.name}")

    return converted
