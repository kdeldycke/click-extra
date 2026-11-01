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
"""Convert reST to MyST: the docstrings of Python sources, and `sphinx-apidoc` pages.

{func}`convert_source` transforms the reST markup of docstrings and comments
to MyST markdown. The companion Sphinx extension
{mod}`click_extra.sphinx.myst_docstrings` converts the MyST back to reST at
build time, so `sphinx.ext.autodoc` still works.

Conversions applied (in order):

1. Cross-references: a reST role, its name between colons, becomes a MyST
   role, its name in braces.
2. Named links: a reST hyperlink embedding its URL becomes a Markdown link.
3. Inline code: double-backtick literals become single-backtick code spans.
4. `#:` comment blocks: strip prefix, convert directives, re-wrap.
5. Directives: a reST directive and its indented body become a backtick
   directive fence.

Only docstrings (bare string-expression statements, located with {mod}`ast`)
and comments (located with {mod}`tokenize`) are transformed.  String
literals, f-strings, and every other piece of runtime code pass through
byte-for-byte: a regex pattern or an error message that happens to contain
reST markup is not documentation and must not be rewritten.

Safe to re-run: already-converted MyST syntax does not match the reST
patterns, so the script is idempotent.

```{note}
**f-string exclusion**: Cross-reference and inline-code regexes exclude
targets containing ``{`` so that interpolation-style placeholders (like
``{self.id}`` in a documented format template) are untouched.
```

```{note}
**Nested fences stay as reST**: A directive whose body already contains a
triple-backtick fence is left in reST.  Converting it would nest two
same-level fences, which markdown cannot delimit, and the build-time
extension passes reST through unchanged anyway.
```

```{note}
**Nested directives stay as reST**: A `.. code-block::` inside a
converted backtick-fenced `warning` directive is emitted as-is.  The
hook handles this correctly because it re-indents the body when
converting back to reST.
```

```{note}
**Link labels lose backticks**: reST has no nested markup, so the hook drops
the backticks of a code span in a link label before emitting the reST link.
```

{func}`convert_apidoc_rst_to_myst` handles only the narrow reST subset that
`sphinx-apidoc` generates: section headings (title + underline), `automodule`
directives with indented options, and structural headers like `Submodules`.

```{note}
Autodoc directives cannot be used as native MyST directives because they
perform internal rST nested parsing that requires an rST parser context
only ``{eval-rst}`` provides. See
[executablebooks/MyST-Parser#587](https://github.com/executablebooks/MyST-Parser/issues/587).
```

The patterns are compiled on first use, through the cache of {mod}`re`.
"""

from __future__ import annotations

import ast
import io
import logging
import re
import tokenize
from pathlib import Path

from .blocks import rewrite_fences, rewrite_file, walk_fences

TYPE_CHECKING = False
if TYPE_CHECKING:
    from .blocks import FenceSpan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cross-references
# ---------------------------------------------------------------------------
# A reST role becomes a MyST role: its colon-wrapped name moves into braces.
# Exclude targets containing { so interpolation placeholders are untouched.
# The lookbehind rejects role-shaped text preceded by a backtick or a word
# character.  A backtick means the text sits inside a code span: in prose
# like `` `:param:`, `:return:` `` the first span's closing backtick would
# otherwise be misread as the opening of a role target, mangling both spans.
# A word character means the text is the tail of a domain-qualified role: in
# ``:py:class:`X``` the inner `:class:` must not convert on its own, which
# would leave the mangled `:py{class}`X``.  Domain-qualified roles stay in
# reST entirely, which the build-time extension passes through unchanged.
# reST forbids inline markup directly after either character, so no
# legitimate cross-reference is lost.
_XREF_PATTERN = r"(?<![\w`]):(\w+):`([^`{]*?)`"


def convert_xrefs(text: str) -> str:
    """Convert reST cross-references to MyST syntax."""
    return re.sub(_XREF_PATTERN, r"{\1}`\2`", text)


# ---------------------------------------------------------------------------
# Named links
# ---------------------------------------------------------------------------
# A reST hyperlink embedding its URL becomes a Markdown link. Its text may wrap
# over several lines.
_LINK_PATTERN = r"`([^`]+?)\s+<(https?://[^>]+)>`_"


def _link_replacer(m: re.Match[str]) -> str:
    """Collapse internal whitespace (handles multi-line reST links)."""
    return f"[{' '.join(m.group(1).split())}]({m.group(2)})"


def convert_links(text: str) -> str:
    """Convert reST named hyperlinks to markdown links."""
    return re.sub(_LINK_PATTERN, _link_replacer, text)


# ---------------------------------------------------------------------------
# Inline code: double-backtick literals become single-backtick code spans
# ---------------------------------------------------------------------------
# A reST literal on a single line, its content captured. The lookarounds pin
# the match to exactly two backticks on each side, so triple-backtick fence
# lines and longer backtick runs are never mistaken for literal delimiters.
# Both directions read reST literals through this one pattern: this module
# halves their backticks, and `click_extra.sphinx.myst_docstrings` keeps them
# verbatim.
# Matches every well-formed double-backtick literal; the halving decision is
# made in the replacement callback.  Matching brace-bearing literals too
# (instead of excluding them from the pattern) is what consumes each literal
# atomically in the left-to-right scan: an excluded literal would leave its
# delimiters open for a later match to pair a closing `` with the next
# literal's opening ``, halving backticks across the gap between them.
_RST_LITERAL_PATTERN = r"(?<!`)``(?!`)([^`\n]+?)``(?!`)"


def _halve_backticks(m: re.Match[str]) -> str:
    """Halve a literal's backticks, keeping brace-bearing content double.

    Content with `{` (interpolation placeholders, format templates) must stay
    double-backticked: single-backticked it would clash with MyST
    cross-reference syntax.
    """
    content = m.group(1)
    if "{" in content:
        return m.group(0)
    return f"`{content}`"


def convert_inline_code(text: str) -> str:
    """Convert reST double-backtick literals to single-backtick."""
    return re.sub(_RST_LITERAL_PATTERN, _halve_backticks, text)


# ---------------------------------------------------------------------------
# Directives  (.. name:: arg  +  indented body)
# ---------------------------------------------------------------------------
_DIRECTIVE_PATTERN = r"^(\s*)\.\. ([\w-]+)::\s*(.*)"


def convert_directives(text: str) -> str:
    """Convert reST directives to MyST backtick fences in a single pass.

    Body lines are collected by indentation (deeper than the `..` line)
    and dedented to the fence level.  Trailing blank lines between
    consecutive directives are preserved as a single separator.

    Nested reST directives (like `.. code-block::` inside `.. warning::`)
    are emitted as-is in the fence body.  The hook re-indents them during
    the reST round-trip.

    A directive whose body contains a triple-backtick fence is left in reST
    entirely: converting it would produce two same-level fences that
    markdown cannot tell apart.

    Symmetrically, existing fences are opaque: a reST directive *inside* a
    fence body is exactly what a previous conversion of nested directives
    produces (the inner one stays reST by design), so re-scanning it would
    break idempotency and nest same-level fences.

    ```{todo}
    Convert a directive whose body holds a fence to a longer outer fence,
    instead of leaving it in reST: the build-time extension
    {mod}`click_extra.sphinx.myst_docstrings` reads fences of any length.
    ```
    """
    directive_re = re.compile(_DIRECTIVE_PATTERN)
    lines = text.split("\n")

    def convert(i: int, span: FenceSpan | None) -> tuple[list[str], int] | None:
        # Emit fences and their interiors verbatim.
        if span is not None:
            return None

        m = directive_re.match(lines[i])

        if not m:
            return None

        indent = m.group(1)
        directive = m.group(2)
        argument = m.group(3).rstrip()
        directive_col = len(indent)
        segment_start = i

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

        # Fenced body: emit the whole directive segment verbatim.
        if any(bl.lstrip().startswith("```") for bl in body):
            return lines[segment_start:i], i

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
        result = [fence]

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

        return result, i

    return "\n".join(rewrite_fences(lines, convert))


# ---------------------------------------------------------------------------
# #: comment blocks  (strip prefix, convert, re-wrap)
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


def _docstring_spans(source: str) -> dict[int, int]:
    """Map each docstring's start line to its end line (1-based, inclusive).

    A docstring here is any bare string-expression statement: module, class,
    and function docstrings, plus the attribute docstrings Sphinx recognizes
    after an assignment.  f-strings are excluded by construction (they parse
    as `JoinedStr`, not `Constant`), and every other string literal in the
    file is runtime code that must not be rewritten.
    """
    spans: dict[int, int] = {}
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            constant = node.value
            spans[constant.lineno] = constant.end_lineno or constant.lineno
    return spans


def _comment_columns(source: str) -> dict[int, int]:
    """Map each commented line (1-based) to the column its comment starts at."""
    columns: dict[int, int] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            columns[token.start[0]] = token.start[1]
    return columns


def _convert_inline(text: str) -> str:
    """Apply the inline conversions: cross-references, links, inline code."""
    return convert_inline_code(convert_links(convert_xrefs(text)))


def _convert_inline_outside_fences(block: str) -> str:
    """Apply inline conversions to a docstring block, skipping fence interiors.

    Fenced content is sample code: a reST-looking pattern inside it is data,
    not markup to rewrite.  Chunks outside fences are converted as a whole so
    multi-line constructs (like wrapped reST links) still match.
    """
    lines = block.split("\n")
    result: list[str] = []
    outside: list[str] = []

    def _flush() -> None:
        if outside:
            result.extend(_convert_inline("\n".join(outside)).split("\n"))
            outside.clear()

    for index, span in walk_fences(lines):
        if span is None:
            outside.append(lines[index])
            continue
        _flush()
        result.extend(lines[index : span.end])
    _flush()
    return "\n".join(result)


def convert_source(source: str) -> str:
    """Convert reST markup to MyST in a Python module's docstrings and comments.

    Docstrings get the full pipeline, in an order that matters: inline
    constructs (cross-references, links, inline code) run before directives
    so that directive bodies are already converted when they are dedented
    into fences.  Comments get the inline conversions only, except
    consecutive full-line `#:` comments, whose directives are also converted
    through {func}`~click_extra.markdown.myst.convert_comment_blocks`.
    Everything outside docstrings and comments passes through byte-for-byte.
    """
    docstrings = _docstring_spans(source)
    comments = _comment_columns(source)
    lines = source.split("\n")

    result: list[str] = []
    lineno = 1
    while lineno <= len(lines):
        # Docstring: apply the full conversion pipeline to the whole span.
        end = docstrings.get(lineno)
        if end is not None:
            block = "\n".join(lines[lineno - 1 : end])
            block = _convert_inline_outside_fences(block)
            block = convert_directives(block)
            result.extend(block.split("\n"))
            lineno = end + 1
            continue

        line = lines[lineno - 1]
        column = comments.get(lineno)

        if column is None:
            result.append(line)
            lineno += 1
            continue

        # `#:` block: collect consecutive full-line `#:` comments so their
        # directives are converted alongside the inline constructs.
        if line[column:].startswith("#:") and not line[:column].strip():
            block_lines: list[str] = []
            while (
                lineno <= len(lines)
                and lineno in comments
                and lines[lineno - 1].lstrip().startswith("#:")
            ):
                block_lines.append(lines[lineno - 1])
                lineno += 1
            block = convert_comment_blocks(_convert_inline("\n".join(block_lines)))
            result.extend(block.split("\n"))
            continue

        # Regular or trailing comment: inline conversions only.
        result.append(line[:column] + _convert_inline(line[column:]))
        lineno += 1

    return "\n".join(result)


def convert_file(filepath: Path) -> bool:
    """Apply all conversions to a single Python file.

    :param filepath: The Python file to convert in place.
    :return: `True` if the file was modified.
    """
    return rewrite_file(filepath, convert_source)


def convert_directory(directory: Path) -> list[Path]:
    """Convert all Python files in a directory from reST to MyST docstrings.

    :param directory: Directory to process recursively.
    :return: List of files that were modified.
    """
    return [path for path in sorted(directory.rglob("*.py")) if convert_file(path)]


# ---------------------------------------------------------------------------
# sphinx-apidoc pages
# ---------------------------------------------------------------------------

_RST_UNDERLINE_LEVELS: dict[str, str] = {
    "=": "#",
    "-": "##",
    "~": "###",
    "^": "####",
}
"""RST underline characters mapped to Markdown heading levels."""


def _clean_heading(title: str) -> str:
    r"""Normalize an RST heading for markdown.

    Strips RST-specific backslash escapes (like the `\_` preventing reference
    interpretation) and wraps qualified Python identifiers in backticks so they
    render as code.

    ```{note}
    `sphinx-apidoc` produces headings like
    `weather\_station\_manager.managers.apm module`.  The backslash
    escapes are necessary in RST but meaningless in markdown, where they
    cause a tug-of-war with `mdformat` (which strips them on every
    reformat pass).  Wrapping the identifier in backticks makes the
    escaping moot and produces cleaner output.
    ```
    """
    # Strip RST backslash-escapes, the one before an underscore.
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
        underline = lines[i + 1] if i + 1 < len(lines) else ""
        level = _RST_UNDERLINE_LEVELS.get(underline[:1])
        if level and underline == underline[0] * len(underline):
            result.append(f"{level} {_clean_heading(lines[i])}")
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
        content = rst_path.read_text(encoding="UTF-8")

        # Only process files that contain automodule directives (sphinx-apidoc stubs).
        if ".. automodule::" not in content:
            logger.debug("Skipping %s: no automodule directive found.", rst_path.name)
            continue

        md_path = rst_path.with_suffix(".md")

        if md_path.exists():
            logger.info(
                "Deleting %s: MyST equivalent %s exists.", rst_path.name, md_path.name
            )
            rst_path.unlink()
            continue

        myst_content = convert_apidoc_rst_to_myst(content)
        md_path.write_text(myst_content, encoding="UTF-8")
        rst_path.unlink()
        converted.append(md_path)
        logger.info("Converted %s to %s", rst_path.name, md_path.name)

    return converted
