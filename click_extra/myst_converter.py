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

Transforms reST markup in docstrings and comments to MyST markdown.  The
companion Sphinx extension {mod}`click_extra.sphinx.myst_docstrings` converts
the MyST back to reST at build time, so `sphinx.ext.autodoc` still works.

Conversions applied (in order):

1. Cross-references: ``:role:`target``` -> ``{role}`target```
2. Named links: ```text <url>`_` -> `[text](url)``
3. Inline code: ````code```` -> ```code```
4. `#:` comment blocks: strip prefix, convert directives, re-wrap.
5. Directives: `.. directive::` + indented body -> ```` ```{directive} ```` /
   ```` ``` ````

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
**Link labels lose backticks**: ``[`sys.platform`](url)`` is valid MyST
but reST has no nested markup.  The hook strips backticks from labels
before emitting the reST link.
```
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

from .blocks import fence_spans
from .prebake import entry_point_package, locate_package_root, read_project_scripts

TYPE_CHECKING = False
if TYPE_CHECKING:
    from .blocks import FenceSpan


def detect_source_package(pyproject_path: Path | None = None) -> Path:
    """Locate the project's single source package from its script entry points.

    Reads the console scripts the project declares, through
    {func}`~click_extra.prebake.read_project_scripts`, and derives the top-level
    package of each entry point target (`"pkg.cli:main"` gives `pkg`), so the
    `convert-to-myst` command can run bare from a project root. The package is
    located under the project root or its `src/` folder, see
    {func}`~click_extra.prebake.locate_package_root`.

    :param pyproject_path: Path of the `pyproject.toml` to inspect. Defaults
        to the one in the current working directory.
    :return: Path of the single detected package directory.
    :raises ValueError: When `pyproject.toml` is missing, the project declares
        no script entry point, or several distinct packages are detected.
    """
    if pyproject_path is None:
        pyproject_path = Path("pyproject.toml")
    if not pyproject_path.is_file():
        raise ValueError(f"No pyproject.toml found at {pyproject_path}.")

    scripts = read_project_scripts(pyproject_path.parent)
    source_dirs = {entry_point_package(target) for target in scripts.values()}

    if not source_dirs:
        raise ValueError(
            "Cannot auto-detect the source directory: no console script in"
            " pyproject.toml or setup.cfg. Specify a directory argument."
        )
    if len(source_dirs) > 1:
        raise ValueError(
            f"Multiple source packages detected: {', '.join(sorted(source_dirs))}."
            " Specify a directory argument."
        )
    package = source_dirs.pop()
    root = locate_package_root(pyproject_path.parent, package) or pyproject_path.parent
    return root / package


# ---------------------------------------------------------------------------
# 1. Cross-references
# ---------------------------------------------------------------------------
# {role}`target` -> {role}`target`
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
XREF_RE = re.compile(r"(?<![\w`]):(\w+):`([^`{]*?)`")


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
# Matches every well-formed double-backtick literal; the halving decision is
# made in the replacement callback.  Matching brace-bearing literals too
# (instead of excluding them from the pattern) is what consumes each literal
# atomically in the left-to-right scan: an excluded literal would leave its
# delimiters open for a later match to pair a closing `` with the next
# literal's opening ``, halving backticks across the gap between them.
DOUBLE_BACKTICK_RE = re.compile(r"(?<!`)``(?!`)([^`\n]+?)``(?!`)")


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
    return DOUBLE_BACKTICK_RE.sub(_halve_backticks, text)


# ---------------------------------------------------------------------------
# 4. Directives  (.. name:: arg  +  indented body)
# ---------------------------------------------------------------------------
DIRECTIVE_RE = re.compile(r"^(\s*)\.\. ([\w-]+)::\s*(.*)")


def _fence_end(lines: list[str], span: FenceSpan) -> int:
    """Index just past the fence `span` covers, which is the text's end when
    the fence never closes."""
    return len(lines) if span.close is None else span.close + 1


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
    markdown cannot tell apart, and a longer outer fence is no better since
    the build-time hook only recognizes triple-backtick fences.

    Symmetrically, existing fences are opaque: a reST directive *inside* a
    fence body is exactly what a previous conversion of nested directives
    produces (the inner one stays reST by design), so re-scanning it would
    break idempotency and nest same-level fences.
    """
    lines = text.split("\n")
    spans = fence_spans(lines)
    result: list[str] = []
    i = 0

    while i < len(lines):
        # Emit fences and their interiors verbatim.
        span = spans.get(i)
        if span is not None:
            end = _fence_end(lines, span)
            result.extend(lines[i:end])
            i = end
            continue

        m = DIRECTIVE_RE.match(lines[i])

        if not m:
            result.append(lines[i])
            i += 1
            continue

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
            result.extend(lines[segment_start:i])
            continue

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
    spans = fence_spans(lines)
    result: list[str] = []
    outside: list[str] = []

    def _flush() -> None:
        if outside:
            result.extend(_convert_inline("\n".join(outside)).split("\n"))
            outside.clear()

    i = 0
    while i < len(lines):
        span = spans.get(i)
        if span is None:
            outside.append(lines[i])
            i += 1
            continue
        _flush()
        end = _fence_end(lines, span)
        result.extend(lines[i:end])
        i = end
    _flush()
    return "\n".join(result)


def convert_source(source: str) -> str:
    """Convert reST markup to MyST in a Python module's docstrings and comments.

    Docstrings get the full pipeline, in an order that matters: inline
    constructs (cross-references, links, inline code) run before directives
    so that directive bodies are already converted when they are dedented
    into fences.  Comments get the inline conversions only, except
    consecutive full-line `#:` comments, whose directives are also converted
    through {func}`~click_extra.myst_converter.convert_comment_blocks`.
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

    Returns `True` if the file was modified.
    """
    original = filepath.read_text(encoding="utf-8")
    converted = convert_source(original)

    if converted != original:
        filepath.write_text(converted, encoding="utf-8")
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
