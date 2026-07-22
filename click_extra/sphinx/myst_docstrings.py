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

Lightweight replacement for
[`sphinx-autodoc2`](https://github.com/sphinx-extensions2/sphinx-autodoc2),
which provided native MyST docstring parsing but is abandoned (last release
`0.5.0`, November 2023; incompatible with current Sphinx and docutils).

Hooks into `autodoc-process-docstring` to transparently convert MyST markdown
syntax in Python docstrings to reStructuredText before Sphinx processes them.
Preserves full compatibility with `sphinx_autodoc_typehints`,
`autodoc_default_options`, and every other extension that builds on
`sphinx.ext.autodoc`. See {doc}`/myst-docstrings` for setup, usage, and
limitations.

The conversion is idempotent: docstrings already in reST pass through
unchanged. This allows incremental migration one module at a time.

Supported conversions:

```{list-table}
:header-rows: 1

* - Construct
  - MyST input
  - reST output
* - Cross-references
  - ``{role}`target```
  - ``{role}`target```
* - Fenced directives
  - `` ```{note} ``
  - `.. note::`
* - Plain code fences
  - ```` ```python ````
  - `.. code-block:: python`
* - Markdown links
  - `[text](url)`
  - ```text <url>`_``
* - Footnote references
  - `[^label]`
  - `[#label]_`
* - Footnote definitions
  - `[^label]: text`
  - `.. [#label] text`
```

Inline code (single backtick) is converted to reST double backticks.
Field list markers (`:param:`, `:return:`) need no conversion; the content
inside field list entries is converted normally (inline code, cross-references,
links).

````{note}
Register this extension in your Sphinx `conf.py`, before
`sphinx_autodoc_typehints` if present:

```{code-block} python
extensions = [
    "sphinx.ext.autodoc",
    "click_extra.sphinx.myst_docstrings",
    "sphinx_autodoc_typehints",  # must come after
]
```

This requires `click-extra[sphinx]` in your docs dependency group.
````
"""

from __future__ import annotations

import logging
import re

from .. import __version__

logger = logging.getLogger(__name__)

# {role}`target` -> {role}`target`
# Negative lookbehind prevents matching inside double backticks (``{version}``).
_XREF_RE = re.compile(r"(?<!``)\{([\w-]+)\}`([^`]*?)`")

# Colon fences are recognized for legacy docstrings; new content uses
# backtick fences (see `_BACKTICK_FENCE_RE` below).
# :::{directive} optional-title
# body
# :::
_COLON_FENCE_RE = re.compile(
    r"^( *):::\{([\w-]+)\}[ ]*([^\n]*)\n(.*?)^\1:::\s*$",
    re.MULTILINE | re.DOTALL,
)
_BACKTICK_FENCE_RE = re.compile(
    r"^( *)```\{([\w-]+)\}[ ]*([^\n]*)\n(.*?)^\1```\s*$",
    re.MULTILINE | re.DOTALL,
)

# ```language           (plain code fence, no {directive})
# code
# ```
# Negative lookahead for `{` prevents matching directive fences that were not
# consumed by the directive regex (malformed body, etc.).
_PLAIN_CODE_FENCE_RE = re.compile(
    r"^( *)```(?!\{)([\w.+-][\w.+-]*)?\s*\n(.*?)^\1```\s*$",
    re.MULTILINE | re.DOTALL,
)

# [^label] -> [#label]_   (footnote reference, not followed by ":" definition)
_FOOTNOTE_REF_RE = re.compile(r"\[\^([\w-]+)\](?!:)")

# [^label]: text -> .. [#label] text   (footnote definition)
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([\w-]+)\]:\s?(.*)$", re.MULTILINE)

# [text](url) but not ![alt](url)
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")


def _convert_link(match: re.Match) -> str:
    """Convert a markdown link to reST, stripping backticks from the label."""
    label = match.group(1).replace("`", "")
    url = match.group(2)
    return f"`{label} <{url}>`_"


# Single-backtick inline code spans are doubled for reST (after protected
# spans are placeholdered out).
_INLINE_CODE_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")

# A reST double-backtick literal on a single line.  The lookarounds pin the
# match to exactly two backticks on each side, so triple-backtick fence lines
# and longer backtick runs are never mistaken for literal delimiters.
_RST_LITERAL_RE = re.compile(r"(?<!`)``(?!`)[^`\n]+``(?!`)")

# Backtick spans that must NOT be treated as plain inline code, lexed in one
# left-to-right pass so each alternative consumes its span before a later
# alternative can restart inside it.  In priority order:
#   {role}`target`   — reST cross-references (from step 1), kept verbatim
#   `text`_          — reST hyperlink references (idempotent pass-through)
#   `:role-shaped:`  — a code span holding a literal role or option name
#                      (like `:tag-pattern:`), doubled for reST on the spot
# The single pass is what makes adjacency safe: when two converted roles
# abut with no separator, the first role consumes the backtick that the
# role-shaped-span alternative would otherwise claim as its opening
# delimiter.  Without the last alternative, the role pattern would read a
# role-shaped span's closing backtick as a role's target delimiter and
# swallow everything up to the next backtick, corrupting the span and any
# cross-reference after it.
# The hyperlink alternative anchors its opening backtick at a non-word,
# non-backtick boundary so it cannot start at the *closing* backtick of a
# preceding inline-code span.
_PROTECTED_RE = re.compile(
    r":[\w-]+:`[^`]*`"
    r"|(?<![\w`])`[^`]+`_{1,2}"
    r"|(?<!`)`(:[\w-]+:[^`\n]*)`(?!`)"
)


def _convert_plain_code_fence(match: re.Match) -> str:
    """Convert a plain triple-backtick code fence to a reST `code-block`."""
    indent = match.group(1)
    lang = match.group(2) or ""
    body = match.group(3)

    header = f"{indent}.. code-block::"
    if lang:
        header += f" {lang}"
    header += "\n"

    body_indent = indent + "    "
    converted_lines: list[str] = []
    for line in body.split("\n"):
        if line.strip():
            stripped = line.lstrip()
            extra_spaces = len(line) - len(stripped) - len(indent)
            converted_lines.append(body_indent + " " * max(0, extra_spaces) + stripped)
        else:
            converted_lines.append("")

    # reST directives need a blank line between the header and the body.
    return header + "\n" + "\n".join(converted_lines) + "\n"


def _convert_fence(match: re.Match) -> str:
    """Convert a single colon-fenced directive to reST."""
    indent = match.group(1)
    directive = match.group(2)
    title = match.group(3).strip()
    body = match.group(4)

    header = f"{indent}.. {directive}::"
    if title:
        header += f" {title}"
    header += "\n"

    body_indent = indent + "    "
    converted_lines: list[str] = []
    for line in body.split("\n"):
        if line.strip():
            # Preserve relative indentation within the body.
            stripped = line.lstrip()
            extra_spaces = len(line) - len(stripped) - len(indent)
            converted_lines.append(body_indent + " " * max(0, extra_spaces) + stripped)
        else:
            converted_lines.append("")

    # reST directives need a blank line between the header and the body.
    return header + "\n" + "\n".join(converted_lines) + "\n"


def myst_to_rst(lines: list[str]) -> None:
    """Convert MyST syntax to reST, modifying *lines* in place.

    The conversion is idempotent: reST-only docstrings pass through unchanged
    because none of the patterns match reST syntax.
    """
    text = "\n".join(lines)

    placeholders: dict[str, str] = {}
    counter = 0

    def _stash(value: str) -> str:
        nonlocal counter
        key = f"\x00P{counter}\x00"
        counter += 1
        placeholders[key] = value
        return key

    def _save(m: re.Match) -> str:
        return _stash(m.group(0))

    def _save_protected(m: re.Match) -> str:
        # A role-shaped code span (group 1) is doubled for reST on its way
        # into the placeholder; other protected spans are kept verbatim.
        if m.group(1):
            return _stash(f"``{m.group(1)}``")
        return _stash(m.group(0))

    # 0. Protect reST double-backtick literals from every following step.
    # Their content is verbatim by definition, and a brace-bearing literal
    # abutting its closing backticks (like ``{levelname}:{message}``) would
    # otherwise be misread by the cross-reference pattern as a {role} with an
    # empty target, mangling the literal.
    text = _RST_LITERAL_RE.sub(_save, text)

    # 1. Cross-references: {role}`target` -> {role}`target`.
    text = _XREF_RE.sub(r":\1:`\2`", text)

    # 2. Fenced directives -> reST directives.
    # Handles both colon fences (:::) and backtick fences (```).
    # Loop handles nesting (rare in docstrings, but correct).
    prev = None
    while prev != text:
        prev = text
        text = _COLON_FENCE_RE.sub(_convert_fence, text)
        text = _BACKTICK_FENCE_RE.sub(_convert_fence, text)

    # 3. Plain code fences -> reST code-block directives.
    # Runs after directive fences are consumed so only plain fences remain.
    text = _PLAIN_CODE_FENCE_RE.sub(_convert_plain_code_fence, text)

    # 4. Footnote definitions: [^label]: text -> .. [#label] text.
    # Runs before inline code so the reST output is not mangled.
    text = _FOOTNOTE_DEF_RE.sub(r".. [#\1] \2", text)

    # 5. Single-backtick inline code -> double-backtick.
    # Protect reST backtick spans (cross-references from step 1, reST
    # hyperlink references in idempotent pass-through, and role-shaped code
    # spans, which are doubled as they are stashed) with placeholders so
    # their backticks are not mistaken for inline code boundaries.
    text = _PROTECTED_RE.sub(_save_protected, text)
    text = _INLINE_CODE_RE.sub(r"``\1``", text)

    # 6. Footnote references: [^label] -> [#label]_.
    # Runs after inline code (no backticks involved) and before links so that
    # [^label] is not mistaken for a markdown link with text "^label".
    text = _FOOTNOTE_REF_RE.sub(r"[#\1]_", text)

    # 7. Markdown links -> reST links.
    # Runs after inline code so that the reST links it produces (which use
    # single backticks: `text <url>`_) are not doubled by step 5.
    # Backticks in link labels are stripped because reST does not support
    # nested markup (inline code inside hyperlinks).  This lets authors write
    # idiomatic MyST like [`sys.platform`](url) and get a clean reST link.
    text = _LINK_RE.sub(_convert_link, text)

    # Restore the spans protected in steps 0 and 5, byte-for-byte.
    for key, value in placeholders.items():
        text = text.replace(key, value)

    lines[:] = text.split("\n")


def _on_process_docstring(app, what, name, obj, options, lines):
    """`autodoc-process-docstring` event handler."""
    myst_to_rst(lines)


_TYPEHINTS_EXT = "sphinx_autodoc_typehints"
"""Extension whose `autodoc-process-docstring` hook must run after ours.

`sphinx_autodoc_typehints` hooks at default priority 500. We register at 400
so MyST-to-reST conversion always runs first, regardless of `conf.py`
ordering. The `setup()` check is a belt-and-suspenders safety net: it catches
misconfiguration early with a clear message rather than letting it surface as
garbled backticks in the rendered docs.
"""

_PRIORITY = 400
"""Event priority for `autodoc-process-docstring`.

Sphinx invokes callbacks in ascending priority order. The default is 500.
We use 400 to guarantee MyST-to-reST conversion runs before any extension
that injects reST markup into docstrings (like `sphinx_autodoc_typehints`).
"""


def setup(app):
    """Sphinx extension entry point.

    :raises ExtensionError: If `sphinx_autodoc_typehints` is already loaded.
    """
    if _TYPEHINTS_EXT in app.extensions:
        from sphinx.errors import ExtensionError

        msg = (
            f"click_extra.sphinx.myst_docstrings must be listed before"
            f" {_TYPEHINTS_EXT} in conf.py extensions."
            f" Both hook autodoc-process-docstring; while priority"
            f" ordering (400 vs 500) handles execution order,"
            f" listing myst_docstrings first makes the intent explicit."
        )
        raise ExtensionError(msg)
    app.connect("autodoc-process-docstring", _on_process_docstring, _PRIORITY)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
