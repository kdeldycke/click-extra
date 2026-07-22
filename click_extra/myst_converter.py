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
"""Convert reST docstrings to MyST in Python source files.

Transforms reST markup in docstrings and `#:` comment blocks to MyST
markdown.  The companion Sphinx extension
{mod}`click_extra.sphinx.myst_docstrings` converts the MyST back to reST at
build time, so `sphinx.ext.autodoc` still works.

Conversions applied (in order):

1. Cross-references: ``{role}`target``` -> ``{role}`target```
2. Named links: ```text <url>`_` -> `[text](url)``
3. Inline code: ````code```` -> ```code```
4. `#:` comment blocks: strip prefix, convert directives, re-wrap.
5. Directives: `.. directive::` + indented body -> ```` ```{directive} ```` /
   ```` ``` ````

Safe to re-run: already-converted MyST syntax does not match the reST
patterns, so the script is idempotent.

```{note}
**f-string exclusion**: Cross-reference and inline-code regexes exclude
targets containing ``{`` so that f-string interpolations (like
``f":func:`~{self.id}`"``) are untouched.
```

```{note}
**Nested directives stay as reST**: A `.. code-block::` inside a
converted backtick-fenced `warning` directive is emitted as-is.  The
hook handles this correctly because it re-indents the body when
converting back to reST.
```

```{note}
**Link labels lose backticks**: ``[`sys.platform`](url)`` is valid MyST
but reST has no nested markup.  The hook strips backticks from labels
before emitting the reST link.
```
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]


def detect_source_package(pyproject_path: Path | None = None) -> Path:
    """Locate the project's single source package from its script entry points.

    Reads `[project.scripts]` from `pyproject.toml` and derives the top-level
    package of each entry point target (`"pkg.cli:main"` gives `pkg`), so the
    `convert-to-myst` command can run bare from a project root.

    :param pyproject_path: Path of the `pyproject.toml` to inspect. Defaults
        to the one in the current working directory.
    :return: Path of the single detected package directory.
    :raises ValueError: When `pyproject.toml` is missing, declares no script
        entry point, or several distinct packages are detected.
    """
    if pyproject_path is None:
        pyproject_path = Path("pyproject.toml")
    if not pyproject_path.is_file():
        raise ValueError(f"No pyproject.toml found at {pyproject_path}.")

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    scripts: dict[str, str] = data.get("project", {}).get("scripts", {})
    # "pkg.cli:main" -> "pkg"; a bare "pkg:main" target maps to "pkg" too.
    source_dirs = {target.split(":", 1)[0].split(".")[0] for target in scripts.values()}

    if not source_dirs:
        raise ValueError(
            "Cannot auto-detect the source directory: no [project.scripts]"
            " entry point in pyproject.toml. Specify a directory argument."
        )
    if len(source_dirs) > 1:
        raise ValueError(
            f"Multiple source packages detected: {', '.join(sorted(source_dirs))}."
            " Specify a directory argument."
        )
    return pyproject_path.parent / source_dirs.pop()


# ---------------------------------------------------------------------------
# 1. Cross-references
# ---------------------------------------------------------------------------
# {role}`target` -> {role}`target`
# Exclude targets containing { so f-string interpolations are untouched.
XREF_RE = re.compile(r":(\w+):`([^`{]*?)`")


def convert_xrefs(text: str) -> str:
    """Convert reST cross-references to MyST syntax."""
    return XREF_RE.sub(r"{\1}`\2`", text)


# ---------------------------------------------------------------------------
# 2. Named links
# ---------------------------------------------------------------------------
# `text <url>`_ -> [text](url)     (may span lines)
LINK_RE = re.compile(r"`([^`]+?)\s+<(https?://[^>]+)>`_", re.DOTALL)


def _link_replacer(m: re.Match) -> str:
    """Collapse internal whitespace (handles multi-line reST links)."""
    text = re.sub(r"\s+", " ", m.group(1).strip())
    url = m.group(2)
    return f"[{text}]({url})"


def convert_links(text: str) -> str:
    """Convert reST named hyperlinks to markdown links."""
    return LINK_RE.sub(_link_replacer, text)


# ---------------------------------------------------------------------------
# 3. Inline code:  `code`  ->  `code`
# ---------------------------------------------------------------------------
# Exclude content containing { so f-string interpolations like
# ``{self.id}`` are untouched.
DOUBLE_BACKTICK_RE = re.compile(r"(?<!`)``([^`{\n]+?)``(?!`)")


def convert_inline_code(text: str) -> str:
    """Convert reST double-backtick literals to single-backtick."""
    return DOUBLE_BACKTICK_RE.sub(r"`\1`", text)


# ---------------------------------------------------------------------------
# 4. Directives  (.. name:: arg  +  indented body)
# ---------------------------------------------------------------------------
DIRECTIVE_RE = re.compile(r"^(\s*)\.\. ([\w-]+)::\s*(.*)")


def convert_directives(text: str) -> str:
    """Convert reST directives to MyST backtick fences in a single pass.

    Body lines are collected by indentation (deeper than the `..` line)
    and dedented to the fence level.  Trailing blank lines between
    consecutive directives are preserved as a single separator.

    Nested directives (like `.. code-block::` inside `.. warning::`)
    are emitted as-is in the fence body.  The hook re-indents them during
    the reST round-trip.
    """
    lines = text.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        m = DIRECTIVE_RE.match(lines[i])

        if not m:
            result.append(lines[i])
            i += 1
            continue

        indent = m.group(1)
        directive = m.group(2)
        argument = m.group(3).rstrip()
        directive_col = len(indent)

        # Collect body: blank lines and lines indented more than the
        # directive.
        body: list[str] = []
        body_indent: int | None = None
        i += 1

        while i < len(lines):
            bline = lines[i]

            if not bline.strip():
                body.append("")
                i += 1
                continue

            bcol = len(bline) - len(bline.lstrip())
            if bcol > directive_col:
                if body_indent is None:
                    body_indent = bcol
                body.append(bline)
                i += 1
            else:
                break

        # Trim trailing blanks but count them so we can re-emit one as
        # a separator between consecutive directives or paragraphs.
        trailing_blanks = 0
        while body and not body[-1]:
            body.pop()
            trailing_blanks += 1

        # Opening fence.
        fence = f"{indent}```{{{directive}}}"
        if argument:
            fence += f" {argument}"
        result.append(fence)

        # Dedent body to fence indent level.
        dedent_n = (body_indent - directive_col) if body_indent else 0
        for bl in body:
            if not bl:
                result.append("")
            else:
                n_spaces = len(bl) - len(bl.lstrip())
                remove = min(dedent_n, n_spaces)
                result.append(bl[remove:])

        # Closing fence.
        result.append(f"{indent}```")

        # Re-emit one blank line if the original had trailing blanks.
        if trailing_blanks:
            result.append("")

    return "\n".join(result)


# ---------------------------------------------------------------------------
# 5. #: comment blocks  (strip prefix, convert, re-wrap)
# ---------------------------------------------------------------------------


def convert_comment_blocks(text: str) -> str:
    """Convert `#:` Sphinx comment docstrings.

    Consecutive `#:` lines are collected, the prefix is stripped, all
    conversions are applied to the extracted content, and the prefix is
    re-added.
    """
    lines = text.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        stripped = lines[i].lstrip()
        if not stripped.startswith("#:"):
            result.append(lines[i])
            i += 1
            continue

        # Collect consecutive #: lines.
        leading_ws = lines[i][: len(lines[i]) - len(stripped)]
        block_contents: list[str] = []

        while i < len(lines):
            s = lines[i].lstrip()
            if not s.startswith("#:"):
                break
            # Strip the #: prefix (with optional trailing space).
            after = s[2:]
            after = after.removeprefix(" ")
            block_contents.append(after)
            i += 1

        # Convert directives in the extracted block.
        block_text = "\n".join(block_contents)
        block_text = convert_directives(block_text)
        converted_lines = block_text.split("\n")

        # Re-wrap with #: prefix.
        for cl in converted_lines:
            if cl.strip():
                result.append(f"{leading_ws}#: {cl}")
            else:
                result.append(f"{leading_ws}#:")

    return "\n".join(result)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def convert_file(filepath: Path) -> bool:
    """Apply all conversions to a single Python file.

    Returns `True` if the file was modified.

    Ordering matters:

    1. Cross-references and links are simple global regexes.
    2. Inline code runs before directives so that `code` inside
       directive bodies is converted when the body is dedented.
    3. `#:` comment blocks are processed before directives so that
       their inner directives are converted in isolation.
    4. Directives run last on the full text.
    """
    text = filepath.read_text(encoding="utf-8")
    original = text

    text = convert_xrefs(text)
    text = convert_links(text)
    text = convert_inline_code(text)
    text = convert_comment_blocks(text)
    text = convert_directives(text)

    if text != original:
        filepath.write_text(text, encoding="utf-8")
        return True
    return False


def convert_directory(directory: Path) -> list[Path]:
    """Convert all Python files in a directory from reST to MyST docstrings.

    :param directory: Directory to process recursively.
    :return: List of files that were modified.
    """
    changed: list[Path] = [
        filepath
        for filepath in sorted(directory.glob("**/*.py"))
        if convert_file(filepath)
    ]
    return changed
