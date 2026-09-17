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
"""Offline self-updating block toolkit for Markdown sources.

Fence-aware Markdown scanning, the `<!-- name … --> / <!-- name-end -->` marker
grammar, and the walk-rewrite-write loop behind the `click-extra
refresh-directives` command.

The toolkit backs the `{matrix}` directive ({mod}`click_extra.sphinx.matrix`)
and the `python:render` `:mirror:` flag, but it depends only on {mod}`re` and
{mod}`pathlib`: nothing here imports Sphinx or docutils. Living in the package
root rather than under
{mod}`click_extra.sphinx` lets a release pipeline or a standalone documentation
script reuse `replace_region` and `update_blocks` without pulling in the
`sphinx` extra.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import NamedTuple

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence


OPTION_LINE_RE = re.compile(r"^[ \t]*:(?P<key>[\w+-]+):[ \t]*(?P<value>.*?)[ \t]*$")
"""A `:key: value` MyST directive option line (value optional for flags)."""

_FENCE_OPEN_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,})")
"""Opening line of a backtick code fence, of any length and indentation.

Colon (`:::`) fences are deliberately not treated as fences here: in MyST
they delimit directives whose body *is* parsed (an admonition can legitimately
host a live ``{matrix}`` or `python:render` block), while backtick-fence
content is always literal.
"""


class FenceSpan(NamedTuple):
    """A top-level backtick fence in a Markdown source, as line indices."""

    start: int
    """Index of the opening fence line."""

    close: int | None
    """Index of the closing fence line, or `None` when unterminated."""


def fence_spans(lines: list[str]) -> dict[int, FenceSpan]:
    """Map each top-level backtick fence's opening line index to its span.

    Fences are consumed as opaque units: a fence line *inside* an outer fence
    (a documented example wrapped in a longer `code-block` fence) never
    starts a span of its own. A close requires a bare run of the same
    character, at least as long as the opener, at the same indentation. An
    unterminated fence spans to the end of the file with `close=None`.
    """
    spans: dict[int, FenceSpan] = {}
    index = 0
    total = len(lines)
    while index < total:
        open_match = _FENCE_OPEN_RE.match(lines[index])
        if not open_match:
            index += 1
            continue
        indent = open_match.group("indent")
        fence = open_match.group("fence")
        close = None
        for probe in range(index + 1, total):
            stripped = lines[probe].strip()
            if (
                lines[probe].startswith(indent)
                and stripped
                and set(stripped) == {"`"}
                and len(stripped) >= len(fence)
            ):
                close = probe
                break
        spans[index] = FenceSpan(index, close)
        if close is None:
            break
        index = close + 1
    return spans


@cache
def marker_res(name: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Build the `(open, close)` regexes of a `<!-- name -->` region.

    The grammar is shared by every self-updating marker region: the opening
    comment is `<!-- name [args] -->` (`args` optional, whitespace
    separated), the closing comment is `<!-- name-end -->`. Both capture
    their leading indentation as `indent`.

    Cached: a region name maps to one pair of compiled patterns, however many
    refreshers read it.
    """
    escaped = re.escape(name)
    open_re = re.compile(
        rf"^(?P<indent>[ \t]*)<!--\s*{escaped}(?:[ \t]+(?P<args>.*?))?\s*-->[ \t]*$",
    )
    close_re = re.compile(rf"^(?P<indent>[ \t]*)<!--\s*{escaped}-end\s*-->[ \t]*$")
    return open_re, close_re


def replace_region(text: str, name: str, content: str, *, pad: bool = True) -> str:
    """Return `text` with the body of a `<!-- name -->` region swapped for `content`.

    Finds the `<!-- name [args] -->` opening and `<!-- name-end -->` closing
    markers (the grammar of {func}`marker_res`) and replaces everything between
    them with `content`. The markers themselves are preserved, so the region
    round-trips: a second call with the same `content` is a no-op.

    When either marker is missing the text is returned unchanged, so the call is
    safe to fan out over every file of an {func}`update_blocks` rewrite even when
    only some carry the region. This is the generic counterpart to the
    fence-driven refreshers of {mod}`click_extra.sphinx.matrix` and the
    `python:render` `:mirror:` flag: use it when the content is produced outside
    the document (a registry dump, an external generator) rather than by an
    inline directive.

    :param pad: With the default `True`, `content` is padded by one blank line
        on each side, the usual layout for a Markdown block. Set it to `False`
        to keep the blank line after the opening marker (Markdown needs it to
        start a fresh block) but drop the one before the closing marker, so the
        region ends flush against it. That flush layout is what
        `mdformat-footnote` requires: it strips an HTML comment sitting on its
        own line right after a footnote definition (executablebooks/
        mdformat-footnote#11), so a region wrapping footnotes must place its
        closing marker on the line immediately below the last body line. An
        empty `content` collapses to a single blank line between the markers
        whatever the padding.
    """
    open_re, close_re = marker_res(name)
    lines = text.split("\n")

    open_idx = next((i for i, line in enumerate(lines) if open_re.match(line)), None)
    if open_idx is None:
        return text
    close_idx = next(
        (i for i in range(open_idx + 1, len(lines)) if close_re.match(lines[i])),
        None,
    )
    if close_idx is None:
        return text

    body = content.split("\n") if content else []
    if not body:
        middle = [""]
    elif pad:
        middle = ["", *body, ""]
    else:
        middle = ["", *body]

    rebuilt = [*lines[: open_idx + 1], *middle, *lines[close_idx:]]
    return "\n".join(rebuilt)


def region_markers(name: str) -> tuple[str, str]:
    """The `(open, close)` lines of a `<!-- name -->` region, as a refresher writes them.

    The writing-side twin of {func}`marker_res`: `<!-- name -->` opens the
    region and `<!-- name-end -->` closes it, and every refresher writes both
    through here so they cannot drift from what that reader matches.
    """
    return f"<!-- {name} -->", f"<!-- {name}-end -->"


def split_options(lines: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    """Split a fence body into its leading `:key: value` options and its content.

    Stops at the first line that is not an option, so a body whose Python
    happens to start with a colon is never mistaken for one. A single blank
    line separating the options from the content goes with the options: the
    content comes back exactly as the directive would receive it.

    :param lines: the lines between a fence's opening and closing markers.
    :return: the options, in declaration order, and the content lines.
    """
    options: dict[str, str] = {}
    index = 0
    while index < len(lines) and (match := OPTION_LINE_RE.match(lines[index])):
        options[match.group("key")] = match.group("value")
        index += 1
    if index < len(lines) and not lines[index].strip():
        index += 1
    return options, list(lines[index:])


def skip_region(lines: Sequence[str], index: int, name: str) -> int:
    """Return the index just past the `<!-- name -->` region opening at `index`.

    Skips leading blank lines, then a whole region if one opens there. Returns
    `index` unchanged when no region follows, so the content below a
    first-time block is never consumed as if it were a stale region.
    """
    open_re, close_re = marker_res(name)
    cursor = index
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor < len(lines) and open_re.match(lines[cursor]):
        while cursor < len(lines) and not close_re.match(lines[cursor]):
            cursor += 1
        if cursor < len(lines):
            return cursor + 1
    return index


def rewrite_fenced_regions(
    text: str,
    name: str,
    fence_open: re.Pattern[str],
    content: Callable[[list[str]], list[str] | None],
) -> str:
    """Refresh the `<!-- name -->` region kept below every matching fence of `text`.

    Walks the document fence by fence via {func}`fence_spans`, so an example
    nested inside a longer `code-block` fence is copied verbatim, never read as
    a live block. A top-level fence whose opening line matches `fence_open`
    hands its inner lines, options included, to `content`, which answers the
    lines the region holds, or `None` to leave the fence with no region at all.
    The region is inserted directly below the fence on first sight and replaced
    afterwards, blank-line padded so `mdformat` never ping-pongs on the
    markers. Idempotent: an unchanged block round-trips to the same text.

    The `python:render` `:mirror:` and the `click:run` `:screenshot:` regions
    are both maintained through here, each with its own `content`.

    :param text: the Markdown source.
    :param name: the region's marker name, see {func}`region_markers`.
    :param fence_open: matches the opening line of a fence carrying a region.
    :param content: computes the region's lines from the fence's inner lines.
    :return: the rewritten source.
    """
    opening, closing = region_markers(name)
    lines = text.split("\n")
    spans = fence_spans(lines)
    total = len(lines)
    out: list[str] = []
    index = 0
    while index < total:
        span = spans.get(index)
        if span is None:
            out.append(lines[index])
            index += 1
            continue
        if span.close is None:
            # Unterminated fence: leave the tail untouched.
            out.extend(lines[index:])
            break

        region = None
        if fence_open.match(lines[index]):
            region = content(lines[index + 1 : span.close])
        # Emit the whole fence unit (source and close line) verbatim.
        out.extend(lines[index : span.close + 1])
        index = span.close + 1
        if region is None:
            continue

        index = skip_region(lines, index, name)
        out.extend(["", opening, "", *region, "", closing])
        # Collapse the gap to the following content to a single blank line.
        while index < total and not lines[index].strip():
            index += 1
        if index < total:
            out.append("")

    return "\n".join(out)


def iter_markdown_files(paths: Iterable[Path]) -> Iterable[Path]:
    """Yield the Markdown sources under `paths` (files as-is, dirs recursed)."""
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.md"))
        else:
            yield path


def update_blocks(
    paths: Iterable[Path],
    rewrite: Callable[[str, Path], str],
    *,
    check: bool = False,
) -> list[Path]:
    """Rewrite self-updating blocks in the Markdown sources under `paths`.

    Walks `paths` (files, or directories recursed for `*.md`), applies
    `rewrite(text, path)` to each, and writes the file back when its content
    changed. In `check` mode nothing is written; the return value still
    lists the files that would change, so a caller can exit non-zero to flag
    stale documentation in CI.

    :return: the files whose blocks were (or, under `check`, would be)
        updated.
    """
    changed: list[Path] = []
    for path in iter_markdown_files(paths):
        original = path.read_text(encoding="utf-8")
        updated = rewrite(original, path)
        if updated != original:
            changed.append(path)
            if not check:
                path.write_text(updated, encoding="utf-8")
    return changed
