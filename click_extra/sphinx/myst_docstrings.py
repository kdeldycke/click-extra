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
"""Convert MyST-flavored docstrings to reST for `sphinx.ext.autodoc`.

Hooks into `autodoc-process-docstring` to convert the MyST markdown of Python
docstrings to reStructuredText before Sphinx processes them, so
`sphinx_autodoc_typehints`, `autodoc_default_options` and every other extension
built on `sphinx.ext.autodoc` keep working. It replaces
[`sphinx-autodoc2`](https://github.com/sphinx-extensions2/sphinx-autodoc2),
whose native MyST parsing does not work with current Sphinx and docutils. See
{doc}`/myst-docstrings` for setup, the syntax reference and the limitations.

The conversion is idempotent: docstrings already in reST pass through
unchanged. This allows incremental migration one module at a time.

Supported conversions:

- Cross-references: a MyST role, its name in braces, becomes a reST role, its
  name between colons.
- Directive fences, with backticks or colons, become reST directives, their
  leading option lines right under the directive header.
- Plain code fences become `code-block` directives. The content of a code block
  is kept verbatim.
- A fence longer than three characters can hold fences of its own character, as
  in any MyST document. {func}`click_extra.markdown.blocks.fence_spans` reads
  the fences.
- Inline code spans get the double backticks of reST literals.
- Markdown links become reST hyperlinks, without the backticks of their label.
- Footnote references and definitions become auto-numbered reST footnotes.

Field list markers (`:param:`, `:return:`) need no conversion; the content
inside field list entries is converted normally (inline code, cross-references,
links).

Register this extension in your Sphinx `conf.py`, before
`sphinx_autodoc_typehints` if present, with `click-extra[sphinx]` in your docs
dependency group:

```python
extensions = [
    "sphinx.ext.autodoc",
    "click_extra.sphinx.myst_docstrings",
    "sphinx_autodoc_typehints",  # must come after
]
```
"""

from __future__ import annotations

import re

from sphinx.errors import ExtensionError

from .. import __version__
from ..markdown.blocks import fence_spans, rewrite_fences, split_options
from ..markdown.myst import _RST_LITERAL_PATTERN

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

    from ..markdown.blocks import FenceSpan

_TYPEHINTS_EXT = "sphinx_autodoc_typehints"
"""Extension whose `autodoc-process-docstring` hook must run after ours.

`sphinx_autodoc_typehints` hooks at default priority 500, and this extension
at {data}`_PRIORITY`, so MyST-to-reST conversion always runs first, regardless
of `conf.py` ordering. The `setup()` check is a belt-and-suspenders safety net:
it catches misconfiguration early with a clear message rather than letting it
surface as garbled backticks in the rendered docs.
"""

_PRIORITY = 400
"""Event priority for `autodoc-process-docstring`.

Sphinx invokes callbacks in ascending priority order, 500 by default. 400 runs
the MyST-to-reST conversion before any extension that injects reST markup into
docstrings (like `sphinx_autodoc_typehints`).
"""

# A MyST role becomes a reST one: the name moves from braces to colons.
# Negative lookbehind prevents matching inside double backticks (``{version}``).
_XREF_RE = re.compile(r"(?<!``)\{([\w-]+)\}`([^`]*?)`")

# The opening line of a directive fence, with colons or backticks: the
# directive name in braces, then its optional argument. `mdformat` escapes colon
# fences, so docstrings prefer backtick ones. The fences themselves, and the
# closing line each pairs with, are read by `click_extra.markdown.blocks`.
_DIRECTIVE_HEAD_RE = re.compile(
    r"^(?P<indent> *)(?:`{3,}|:{3,})\{(?P<directive>[\w-]+)\}[ ]*(?P<argument>.*)$"
)

# The opening line of a plain code fence: backticks, then an optional language.
# The negative lookahead for `{` keeps out a directive fence the directive
# conversion left alone, like one whose name holds a colon.
_PLAIN_HEAD_RE = re.compile(r"^(?P<indent> *)`{3,}(?!\{)(?P<language>[\w.+-]+)?\s*$")

_CODE_DIRECTIVES = frozenset(("code", "code-block", "sourcecode"))
"""Directives whose body is code: a plain backtick fence is one too."""

# [^label] -> [#label]_   (footnote reference, not followed by ":" definition)
_FOOTNOTE_REF_RE = re.compile(r"\[\^([\w-]+)\](?!:)")

# [^label]: text -> .. [#label] text   (footnote definition)
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([\w-]+)\]:\s?(.*)$", re.MULTILINE)

# [text](url) but not ![alt](url). The destination takes either CommonMark
# shape: angle-bracketed (the escape hatch for parentheses and spaces), or
# bare with parentheses allowed one balanced level deep (a man-page anchor
# like man.cgi?pkg(8)). Newlines never cross a destination: a link broken
# over two lines stays unconverted rather than swallowing the paragraph.
_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]+)\]\((?:<([^<>\n]*)>|((?:[^()\n]|\([^()\n]*\))+))\)"
)


def _convert_link(match: re.Match[str]) -> str:
    """Convert a markdown link to reST, stripping backticks from the label."""
    label = match.group(1).replace("`", "")
    url = match.group(2) if match.group(2) is not None else match.group(3)
    return f"`{label} <{url}>`_"


# A reST double-backtick literal on a single line, in the grammar the
# reST-to-MyST converter reads it with.
_RST_LITERAL_RE = re.compile(_RST_LITERAL_PATTERN)

# A code span opened and closed by exactly two backticks, whose content may hold
# single backticks. Its content holding one is what tells a MyST span apart from
# the reST literals of `_RST_LITERAL_RE`.
_DOUBLE_SPAN_RE = re.compile(r"(?<!`)``(?!`)((?:[^`\n]|(?<!`)`(?!`))+?)(?<!`)``(?!`)")

# Backtick spans, lexed in one left-to-right pass so each alternative consumes
# its span before a later alternative can restart inside it. In priority order:
#   a reST role  — a cross-reference converted by step 2, kept verbatim
#   `text`_      — reST hyperlink references (idempotent pass-through)
#   `code`       — a single-line code span, doubled into a reST literal
# The single pass is what keeps a code span whole. Its opening backtick comes
# before anything it holds, so the span is consumed before the scan reaches a
# role-shaped word inside it, like the `:keep-stems:` of `` `:keep-stems:` ``
# or of `` `basket :keep-stems:` ``. Read as a role, that word would take the
# span's closing backtick as the opening of its target, and swallow everything
# up to the next backtick, a line below if need be: the span and the one after
# it would mispair. The role alternative cannot stop at a line end instead,
# since the target of a real role can wrap.
# Adjacency stays safe the same way: when two converted roles abut with no
# separator, the first role consumes the backtick that the code-span
# alternative would otherwise claim as its opening delimiter.
# The hyperlink alternative anchors its opening backtick at a non-word,
# non-backtick boundary AND requires its trailing reference marker (`_` or
# `__`) not to be glued to an identifier. Both guard a span the code-span
# alternative leaves alone, like one broken over two lines. When its content
# ends in a non-word character, its *closing* backtick clears the lookbehind,
# so the alternative would start there, read the gap as link text, swallow the
# next span's *opening* backtick, and match a following `_word` as a bogus
# reference marker. A genuine reST reference marker is never followed by a word
# character, so the trailing `(?![\w])` rejects that false match while still
# matching real `` `text`_ `` links.
_BACKTICK_SPAN_RE = re.compile(
    r":[\w-]+:`[^`]*`"
    r"|(?<![\w`])`[^`]+`_{1,2}(?![\w])"
    r"|(?<!`)`([^`\n]+)`(?!`)"
)


def _rst_directive(
    indent: str,
    directive: str,
    argument: str,
    options: dict[str, str],
    content: list[str],
) -> str:
    """Write a reST directive at `indent`, its `options` and `content` under it.

    The options sit right under the header, where reST reads them. The content
    keeps the relative indentation it had in the fence, shifted to the four
    spaces a reST directive body sits at. A blank line separates the content
    from what precedes it, as reST requires, and another closes the directive.
    """
    header = f"{indent}.. {directive}::"
    if argument:
        header += f" {argument}"

    body_indent = indent + "    "
    lines = [header]
    lines.extend(
        f"{body_indent}:{key}: {value}" if value else f"{body_indent}:{key}:"
        for key, value in options.items()
    )
    lines.append("")
    for line in content:
        if line.strip():
            stripped = line.lstrip()
            extra_spaces = len(line) - len(stripped) - len(indent)
            lines.append(body_indent + " " * max(0, extra_spaces) + stripped)
        else:
            lines.append("")

    return "\n".join(lines) + "\n"


def _convert_plain_code_fence(lines: list[str], span: FenceSpan) -> str | None:
    """Convert a plain backtick code fence to a reST `code-block`.

    The blank lines opening the code are dropped. `None` when the fence opens
    on anything but a language.
    """
    head = _PLAIN_HEAD_RE.match(lines[span.start])
    if head is None:
        return None
    code = lines[span.body]
    first = next((index for index, line in enumerate(code) if line.strip()), len(code))
    return _rst_directive(
        head.group("indent"),
        "code-block",
        head.group("language") or "",
        {},
        [*code[first:], ""],
    )


def _convert_fence(lines: list[str], span: FenceSpan) -> str | None:
    """Convert a single fenced directive, colon or backtick, to reST.

    Leading `:key: value` lines of the body are the directive's options, as
    MyST reads them. `None` when the fence opens on no directive.
    """
    head = _DIRECTIVE_HEAD_RE.match(lines[span.start])
    if head is None:
        return None
    options, content = split_options([*lines[span.body], ""])
    return _rst_directive(
        head.group("indent"),
        head.group("directive"),
        head.group("argument").strip(),
        options,
        content,
    )


def _convert_fences(
    text: str,
    chars: str,
    convert: Callable[[list[str], FenceSpan], str | None],
) -> str:
    """Replace each top-level fence of `chars` in `text` that `convert` turns to reST.

    The reST takes the place of the fence and of the blank lines after it: it
    ends on the one blank line reST wants after a directive. A fence left
    unclosed is not converted.
    """
    lines = text.split("\n")
    total = len(lines)

    def replace(index: int, span: FenceSpan | None) -> tuple[list[str], int] | None:
        if span is None or span.close is None:
            return None
        rst = convert(lines, span)
        if rst is None:
            return None
        resume = span.end
        while resume < total and not lines[resume].strip():
            resume += 1
        return rst.split("\n"), resume

    return "\n".join(rewrite_fences(lines, replace, fence_spans(lines, chars=chars)))


def _protect_code(lines: list[str], stash: Callable[[str], str]) -> list[str]:
    """Return `lines` with the code of each code block behind a placeholder.

    A code block is a plain backtick fence, or the fence of a code directive,
    whose options stay for the fence conversion to read. Each line of code
    becomes a placeholder behind its indentation, which the fence conversion
    then shifts like any other body line. The body of a prose directive is
    prose: only the code blocks nested in it are code.
    """
    protected = list(lines)
    for span in fence_spans(lines, chars="`:").values():
        head = lines[span.start]
        directive = _DIRECTIVE_HEAD_RE.match(head)
        if span.close is None or not (directive or _PLAIN_HEAD_RE.match(head)):
            continue
        body = lines[span.body]
        name = directive.group("directive") if directive else None
        if name is not None and name not in _CODE_DIRECTIVES:
            protected[span.body] = _protect_code(body, stash)
            continue
        first = span.body.start
        if name:
            first += len(body) - len(split_options(body)[1])
        for index in range(first, span.body.stop):
            code = lines[index].lstrip()
            if code:
                protected[index] = lines[index][: -len(code)] + stash(code)
    return protected


def _double_inline_code(m: re.Match[str]) -> str:
    """Double a MyST inline-code span's backticks for reST.

    reST inline literals cannot carry whitespace adjacent to their delimiters,
    so a span whose content has leading or trailing spaces (a `` `> ` ``
    prompt) is stripped to its core before doubling. An all-whitespace span has
    no reST literal to become, so it is left untouched.
    """
    content = m.group(1).strip()
    if not content:
        return m.group(0)
    return f"``{content}``"


def myst_to_rst(lines: list[str]) -> None:
    """Convert MyST syntax to reST, modifying *lines* in place.

    The conversion is idempotent: reST-only docstrings pass through unchanged
    because none of the patterns match reST syntax.
    """
    text = "\n".join(lines)

    placeholders: dict[str, str] = {}

    def _stash(value: str) -> str:
        key = f"\x00P{len(placeholders)}\x00"
        placeholders[key] = value
        return key

    def _save(m: re.Match[str]) -> str:
        return _stash(m.group(0))

    def _save_backtick_span(m: re.Match[str]) -> str:
        # The padding that lets a MyST span start or end on a backtick goes:
        # reST allows no space next to the delimiters of a literal.
        if "`" not in m.group(1):
            return m.group(0)
        return _stash(f"``{m.group(1).strip()}``")

    def _convert_span(m: re.Match[str]) -> str:
        # A code span (group 1) is doubled in place. A role or a hyperlink
        # reference is kept verbatim behind a placeholder.
        if m.group(1) is None:
            return _stash(m.group(0))
        return _double_inline_code(m)

    # 0. Protect the content of code blocks from every following step. It is
    # code, so a backtick, a role or a link in it is kept as written.
    text = "\n".join(_protect_code(text.split("\n"), _stash))

    # 1. Protect double-backtick literals from every following step. Their
    # content is verbatim by definition. The single backticks of a MyST span
    # like `` `apple` pie `` would otherwise be doubled by step 6, which ends
    # the literal early. And a brace-bearing literal abutting its closing
    # backticks (like ``{levelname}:{message}``) would be misread by the
    # cross-reference pattern as a role with an empty target.
    text = _DOUBLE_SPAN_RE.sub(_save_backtick_span, text)
    text = _RST_LITERAL_RE.sub(_save, text)

    # 2. Cross-references: MyST roles become reST roles.
    text = _XREF_RE.sub(r":\1:`\2`", text)

    # 3. Fenced directives -> reST directives.
    # Handles both colon fences (:::) and backtick fences (```).
    # Loop handles nesting (rare in docstrings, but correct).
    prev = None
    while prev != text:
        prev = text
        text = _convert_fences(text, ":", _convert_fence)
        text = _convert_fences(text, "`", _convert_fence)

    # 4. Plain code fences -> reST code-block directives.
    # Runs after directive fences are consumed so only plain fences remain.
    text = _convert_fences(text, "`", _convert_plain_code_fence)

    # 5. Footnote definitions: [^label]: text -> .. [#label] text.
    # Runs before inline code so the reST output is not mangled.
    text = _FOOTNOTE_DEF_RE.sub(r".. [#\1] \2", text)

    # 6. Single-backtick inline code -> double-backtick.
    # The same pass protects reST backtick spans (cross-references from step 2,
    # and reST hyperlink references in idempotent pass-through) with
    # placeholders, so their backticks are not mistaken for inline code
    # boundaries, and no code span is read as one of them.
    text = _BACKTICK_SPAN_RE.sub(_convert_span, text)

    # 7. Footnote references: [^label] -> [#label]_.
    # Runs after inline code (no backticks involved) and before links so that
    # [^label] is not mistaken for a markdown link with text "^label".
    text = _FOOTNOTE_REF_RE.sub(r"[#\1]_", text)

    # 8. Markdown links -> reST links.
    # Runs after inline code so that the reST links it produces (which use
    # single backticks: `text <url>`_) are not doubled by step 6.
    # Backticks in link labels are stripped because reST does not support
    # nested markup (inline code inside hyperlinks).  This lets authors write
    # idiomatic MyST like [`sys.platform`](url) and get a clean reST link.
    text = _LINK_RE.sub(_convert_link, text)

    # Restore the protected spans, byte-for-byte. Last in, first out: a span
    # stashed late can hold the placeholder of one stashed before it, like a
    # reST literal inside a reST hyperlink reference.
    for key, value in reversed(placeholders.items()):
        text = text.replace(key, value)

    lines[:] = text.split("\n")


def _on_process_docstring(app, what, name, obj, options, lines):
    """`autodoc-process-docstring` event handler."""
    myst_to_rst(lines)


def setup(app):
    """Sphinx extension entry point.

    :raises sphinx.errors.ExtensionError: If `sphinx_autodoc_typehints` is
        already loaded.
    """
    if _TYPEHINTS_EXT in app.extensions:
        msg = (
            f"click_extra.sphinx.myst_docstrings must be listed before"
            f" {_TYPEHINTS_EXT} in conf.py extensions."
            f" Both hook autodoc-process-docstring; while priority"
            f" ordering ({_PRIORITY} vs 500) handles execution order,"
            f" listing myst_docstrings first makes the intent explicit."
        )
        raise ExtensionError(msg)
    app.connect("autodoc-process-docstring", _on_process_docstring, _PRIORITY)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
