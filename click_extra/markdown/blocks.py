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

Every scanner of the package that must not read inside a fence walks the
document through {func}`walk_fences`, or rebuilds it through
{func}`rewrite_fences`: a fence is one opaque unit, whose body is never read as
live markup.

The toolkit backs the ``{matrix}`` directive ({mod}`click_extra.sphinx.matrix`),
the `python:render` `:mirror:` flag and the `click:run` `:screenshot:` mirror,
but it depends only on {mod}`re` and {mod}`pathlib`: nothing here imports Sphinx
or docutils. Living outside {mod}`click_extra.sphinx` lets a release pipeline or
a standalone documentation script reuse `replace_region` and `update_blocks`
without pulling in the `sphinx` extra.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import NamedTuple

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence


@cache
def _option_line_re() -> re.Pattern[str]:
    """Match a `:key: value` MyST directive option line (value optional for flags).

    Whitespace or the end of the line follows the key, which tells an option
    from a line opening on a reST role.

    Compiled on first use, like `_fence_open_re`.
    """
    return re.compile(r"^[ \t]*:(?P<key>[\w+-]+):(?:[ \t]+(?P<value>.*?))?[ \t]*$")


@cache
def _fence_open_re(chars: str) -> re.Pattern[str]:
    """Match the opening line of a fence of `chars`, of any length and indentation.

    Most readers take backtick fences alone: in a MyST document, colon (`:::`)
    fences delimit directives whose body *is* parsed (an admonition can
    legitimately host a live ``{matrix}`` or `python:render` block), while
    backtick-fence content is always literal. A reader converting fences of
    either kind, like the MyST-to-reST docstring converter, asks for both.

    Compiled on first use: only a documentation tool scans a fence.
    """
    fences = "|".join(f"{re.escape(char)}{{3,}}" for char in chars)
    return re.compile(rf"^(?P<indent>[ \t]*)(?P<fence>{fences})")


class FenceSpan(NamedTuple):
    """A top-level fence in a Markdown source, as line indices."""

    start: int
    """Index of the opening fence line."""

    close: int | None
    """Index of the closing fence line, or `None` when unterminated."""

    end: int
    """Index just past the fence: past its closing line, or the line count of
    the source when the fence never closes."""

    @property
    def body(self) -> slice:
        """The lines between the opening fence line and the closing one, which
        run to the end of the source when the fence never closes."""
        return slice(self.start + 1, self.end if self.close is None else self.close)


def fence_spans(lines: Sequence[str], *, chars: str = "`") -> dict[int, FenceSpan]:
    """Map each top-level fence's opening line index to its span.

    Fences are consumed as opaque units: a fence line *inside* an outer fence
    (a documented example wrapped in a longer `code-block` fence) never
    starts a span of its own. A close requires a bare run of the same
    character, at least as long as the opener, at the same indentation or
    deeper. An unterminated fence spans to the end of the file with
    `close=None`.

    :param chars: The characters a fence is made of: backticks by default,
        `:` for colon fences alone, or both. A colon fence delimits a MyST
        directive whose body is parsed, so most scanners read backtick fences
        alone.
    """
    fence_open = _fence_open_re(chars)
    spans: dict[int, FenceSpan] = {}
    index = 0
    total = len(lines)
    while index < total:
        open_match = fence_open.match(lines[index])
        if not open_match:
            index += 1
            continue
        indent = open_match.group("indent")
        fence = open_match.group("fence")
        close = None
        for probe in range(index + 1, total):
            stripped = lines[probe].strip()
            if (
                len(stripped) >= len(fence)
                and not stripped.strip(fence[0])
                and lines[probe].startswith(indent)
            ):
                close = probe
                break
        end = total if close is None else close + 1
        spans[index] = FenceSpan(index, close, end)
        index = end
    return spans


def walk_fences(
    lines: Sequence[str],
    spans: Mapping[int, FenceSpan] | None = None,
    start: int = 0,
) -> Iterator[tuple[int, FenceSpan | None]]:
    """Walk `lines` from `start`, a line at a time, stepping over each fence whole.

    Yields `(index, None)` for each line outside the top-level fences, and
    `(index, span)` for each fence, from its opening line. The walk then
    resumes at `span.end`: the body of a fence is never visited, and an
    unterminated fence ends the walk.

    :param lines: the Markdown source, split in lines.
    :param spans: the fences of `lines`, from {func}`fence_spans`. Computed
        when not given.
    :param start: the index to start from, outside any fence body.
    """
    if spans is None:
        spans = fence_spans(lines)
    index = start
    while index < len(lines):
        span = spans.get(index)
        yield index, span
        index = index + 1 if span is None else span.end


def rewrite_fences(
    lines: Sequence[str],
    visit: Callable[[int, FenceSpan | None], tuple[list[str], int] | None],
    spans: Mapping[int, FenceSpan] | None = None,
) -> list[str]:
    """Rebuild `lines` along {func}`walk_fences`, letting `visit` rewrite them.

    `visit(index, span)` sees each step of the walk. It answers `None` to keep
    that line, or that whole fence, verbatim: an unterminated fence keeps the
    rest of the source. Or it answers `(replacement, resume)`, to emit the
    `replacement` lines in place of the source lines up to `resume`, which
    must lie past `index` and outside any fence body.

    :param lines: the Markdown source, split in lines.
    :param visit: decides what replaces each line or fence.
    :param spans: the fences of `lines`, from {func}`fence_spans`. Computed
        when not given.
    :return: the rebuilt lines.
    """
    if spans is None:
        spans = fence_spans(lines)
    out: list[str] = []
    resume: int | None = 0
    while resume is not None:
        walk = walk_fences(lines, spans, resume)
        resume = None
        for index, span in walk:
            rewritten = visit(index, span)
            if rewritten is not None:
                chunk, resume = rewritten
                out.extend(chunk)
                break
            out.extend(lines[index : index + 1 if span is None else span.end])
    return out


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


def _find_marker(
    lines: Sequence[str],
    marker: re.Pattern[str],
    spans: Mapping[int, FenceSpan],
    start: int = 0,
) -> int | None:
    """Index of the first line from `start` matching `marker`, outside fences."""
    return next(
        (
            index
            for index, span in walk_fences(lines, spans, start)
            if span is None and marker.match(lines[index])
        ),
        None,
    )


def replace_region(text: str, name: str, content: str, *, pad: bool = True) -> str:
    """Return `text` with the body of a `<!-- name -->` region swapped for `content`.

    Finds the `<!-- name [args] -->` opening and `<!-- name-end -->` closing
    markers (the grammar of {func}`~click_extra.markdown.blocks.marker_res`) and
    replaces everything between them with `content`. The markers themselves are
    preserved, so the region round-trips: a second call with the same `content`
    is a no-op. A marker quoted inside a code fence, like in a page documenting
    the grammar, is never taken for a live one.

    When either marker is missing the text is returned unchanged, so the call is
    safe to fan out over every file of an
    {func}`~click_extra.markdown.blocks.update_blocks` rewrite even when only
    some carry the region. This is the generic counterpart to the
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
        own line right after a footnote definition
        ([executablebooks/mdformat-footnote#11](https://github.com/executablebooks/mdformat-footnote/issues/11)),
        so a region wrapping footnotes must place its closing marker on the line
        immediately below the last body line. An empty `content` collapses to a
        single blank line between the markers whatever the padding.
    """
    open_re, close_re = marker_res(name)
    lines = text.split("\n")
    spans = fence_spans(lines)

    open_idx = _find_marker(lines, open_re, spans)
    if open_idx is None:
        return text
    close_idx = _find_marker(lines, close_re, spans, open_idx + 1)
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
    """The `(open, close)` marker lines of a `<!-- name -->` region.

    The writing-side twin of {func}`~click_extra.markdown.blocks.marker_res`:
    `<!-- name -->` opens the region and `<!-- name-end -->` closes it, and every
    refresher writes both through here so they cannot drift from what that
    reader matches.
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
    option_line = _option_line_re()
    options: dict[str, str] = {}
    index = 0
    while index < len(lines) and (match := option_line.match(lines[index])):
        options[match.group("key")] = match.group("value") or ""
        index += 1
    if index < len(lines) and not lines[index].strip():
        index += 1
    return options, list(lines[index:])


def skip_region(
    lines: Sequence[str],
    index: int,
    name: str,
    spans: Mapping[int, FenceSpan] | None = None,
) -> int:
    """Return the index just past the `<!-- name -->` region opening at `index`.

    Skips leading blank lines, then a whole region if one opens there. Returns
    `index` unchanged when no region follows, so the content below a
    first-time block is never consumed as if it were a stale region. The search
    for the closing marker steps over fences: a `<!-- name-end -->` quoted in a
    code example the region holds does not end it.

    :param spans: the fences of `lines`, from {func}`fence_spans`. Computed
        when not given.
    """
    open_re, close_re = marker_res(name)
    cursor = index
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor < len(lines) and open_re.match(lines[cursor]):
        if spans is None:
            spans = fence_spans(lines)
        close = _find_marker(lines, close_re, spans, cursor + 1)
        if close is not None:
            return close + 1
    return index


def rewrite_fenced_regions(
    text: str,
    name: str,
    fence_open: re.Pattern[str],
    content: Callable[[list[str]], list[str] | None],
) -> str:
    """Refresh the `<!-- name -->` region kept below every matching fence of `text`.

    Walks the document through {func}`rewrite_fences`, so an example nested
    inside a longer `code-block` fence is copied verbatim, never read as a live
    block. A top-level fence whose opening line matches `fence_open` hands its
    inner lines, options included, to `content`, which answers the lines the
    region holds, or `None` to leave the fence with no region at all. The
    region is inserted directly below the fence on first sight and replaced
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

    def refresh(index: int, span: FenceSpan | None) -> tuple[list[str], int] | None:
        # An unterminated fence keeps the tail untouched.
        if span is None or span.close is None or not fence_open.match(lines[index]):
            return None
        region = content(lines[span.body])
        if region is None:
            return None
        # Emit the whole fence unit (source and close line) verbatim.
        chunk = [*lines[index : span.end], "", opening, "", *region, "", closing]
        resume = skip_region(lines, span.end, name, spans)
        # Collapse the gap to the following content to a single blank line.
        while resume < total and not lines[resume].strip():
            resume += 1
        if resume < total:
            chunk.append("")
        return chunk, resume

    return "\n".join(rewrite_fences(lines, refresh, spans))


def iter_markdown_files(paths: Iterable[Path]) -> Iterator[Path]:
    """Yield the Markdown sources under `paths` (files as-is, dirs recursed)."""
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.md"))
        else:
            yield path


def rewrite_file(
    path: Path,
    rewrite: Callable[[str], str],
    *,
    check: bool = False,
) -> bool:
    """Apply `rewrite` to the text of `path`, and write it back when it changed.

    The one write-if-changed step of every source rewriter: the block refreshers
    through {func}`~click_extra.markdown.blocks.update_blocks`, and the
    reST-to-MyST docstring converter through
    {func}`~click_extra.markdown.myst.convert_file`.

    :param check: report the change without writing it.
    :return: whether the text changed, or would have under `check`.
    """
    original = path.read_text(encoding="UTF-8")
    updated = rewrite(original)
    if updated == original:
        return False
    if not check:
        path.write_text(updated, encoding="UTF-8")
    return True


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

    def refresh(path: Path) -> bool:
        return rewrite_file(path, lambda text: rewrite(text, path), check=check)

    return [path for path in iter_markdown_files(paths) if refresh(path)]
