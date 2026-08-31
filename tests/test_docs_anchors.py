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

"""Every Markdown fragment link resolves in a raw-Markdown reader.

Three slug algorithms compete over the same headings. `docutils.nodes.make_id`
derives the ids Sphinx renders, and `myst_heading_slug_func` in `docs/conf.py`
points MyST at it, so a link written `parameters.md#params-option` is correct
on the published site. GitHub, and the `lychee` checker that models it, slug
the raw Markdown instead: they keep the leading `--`, the dots and the
underscores that `make_id` strips or folds, so the same link finds nothing
when the page is read on GitHub.

Neither reader can be dropped, so a heading whose two slugs disagree carries
an `<a name="…">` companion holding the `make_id` spelling. That HTML anchor
is invisible to Sphinx (it renders no `id`, so the page keeps one id per
section) and authoritative for GitHub and lychee.

The check runs on text alone: no build, no network, no platform floor. Its
counterpart on the built HTML is `test_sphinx_crossrefs.py`, which is skipped
off Linux, and the `check-broken-links` CI job, which files an issue instead
of failing a run. Both let a broken anchor sit for a full cycle.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

PROJECT_ROOT = Path(__file__).parent.parent

# Markdown a reader browses on GitHub, and the pages lychee reports on.
MARKDOWN_FILES = (
    *sorted(PROJECT_ROOT.glob("*.md")),
    *sorted((PROJECT_ROOT / "docs").glob("*.md")),
)

# A fence closes only on its own marker character, repeated at least as many
# times as it was opened with, and followed by nothing. That is what lets this
# documentation nest a ``` example inside a ```` block, and a MyST ``` fence
# inside a ::: one, without either inner marker closing the outer block.
FENCE_OPEN = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,}|:{3,})(?P<info>.*)$")
FENCE_CLOSE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,}|:{3,})\s*$")

ATX_HEADING = re.compile(r"^#{1,6} +(?P<text>.+?)\s*$")

# `<a name="x">` and `<a id="x">`, the two anchor forms lychee resolves.
HTML_ANCHOR = re.compile(r"""<a\s[^>]*\b(?:name|id)\s*=\s*["'](?P<anchor>[^"']+)["']""")

# An inline link whose target carries a fragment: `](page.md#frag)` or `](#frag)`.
# Angle-bracket and title forms are unused in this tree, so they are not parsed.
FRAGMENT_LINK = re.compile(r"]\((?P<page>[^()\s#]*)#(?P<fragment>[^()\s]+)\)")


def lychee_excludes() -> tuple[re.Pattern[str], ...]:
    """Read the link patterns `[tool.lychee]` waives, so both checkers agree.

    The palette anchors of `docs/theme.md` are the ones that matter here: a
    `{python:render}` loop emits their headings at build time, so no reader of
    the raw Markdown can see them.
    """
    config = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    )
    return tuple(
        re.compile(pattern) for pattern in config["tool"]["lychee"].get("exclude", ())
    )


def uncoded_lines(content: str) -> list[tuple[int, str]]:
    """Number and return the lines sitting outside a code fence.

    lychee ignores fenced content, so a link in an example is not a link.
    """
    lines: list[tuple[int, str]] = []
    opening = ""
    for number, line in enumerate(content.splitlines(), 1):
        if opening:
            close = FENCE_CLOSE.match(line)
            marker = close.group("marker") if close else ""
            if marker.startswith(opening[0]) and len(marker) >= len(opening):
                opening = ""
            continue
        fence = FENCE_OPEN.match(line)
        # A backtick fence's info string may not itself hold a backtick, which
        # is what keeps inline code like ``x`` from opening a block.
        if fence and not (
            fence.group("marker")[0] == "`" and "`" in fence.group("info")
        ):
            opening = fence.group("marker")
            continue
        lines.append((number, line))
    return lines


def github_slug(heading: str) -> str:
    """Slug a heading the way GitHub does, which is what lychee models.

    Lowercase, drop every character that is neither a word character, a space
    nor a hyphen, then hyphenate the spaces. Backticks vanish with the rest of
    the punctuation, so a leading `--`, a dot and an underscore all survive.
    """
    slug = heading.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    return re.sub(r"\s+", "-", slug.strip())


def readable_anchors(path: Path) -> set[str]:
    """Collect every fragment a raw-Markdown reader can reach on a page.

    Duplicate heading slugs are numbered the way GitHub numbers them, so a
    heading repeated three times answers to `slug`, `slug-1` and `slug-2`.
    """
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for _number, line in uncoded_lines(path.read_text(encoding="utf-8")):
        anchors.update(HTML_ANCHOR.findall(line))
        heading = ATX_HEADING.match(line)
        if not heading:
            continue
        slug = github_slug(heading.group("text"))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if not count else f"{slug}-{count}")
    return anchors


def unresolved_fragments(paths=MARKDOWN_FILES) -> list[str]:
    """Report every fragment link no raw-Markdown reader can follow.

    Each entry names the source location, the target and the fragment, so the
    failure says where to add the missing `<a name="…">`.
    """
    excludes = lychee_excludes()
    anchors: dict[Path, set[str]] = {}
    misses = []
    for path in paths:
        for number, line in uncoded_lines(path.read_text(encoding="utf-8")):
            for link in FRAGMENT_LINK.finditer(line):
                page, fragment = link.group("page"), link.group("fragment")
                target = (path.parent / page).resolve() if page else path
                # Only Markdown pages of this repository are checked: a URL or
                # an asset carries no headings to slug.
                if target.suffix != ".md" or not target.is_file():
                    continue
                # lychee matches its exclusions against the resolved file URI,
                # so a same-page `#dark` is waived like a `theme.md#dark` one.
                if any(rule.search(f"{target}#{fragment}") for rule in excludes):
                    continue
                if fragment not in anchors.setdefault(target, readable_anchors(target)):
                    source = path.relative_to(PROJECT_ROOT)
                    name = target.relative_to(PROJECT_ROOT)
                    misses.append(f"{source}:{number} -> {name}#{fragment}")
    return misses


def test_markdown_files_are_collected():
    """The glob feeding the check still finds the documentation."""
    assert len(MARKDOWN_FILES) > 40, "documentation pages went missing"


def test_fragment_links_resolve_in_raw_markdown():
    """No fragment link dangles for a reader of the raw Markdown.

    A failure means the target heading slugs differently on GitHub than
    `make_id` spells it. Add `<a name="{fragment}"></a>` above that heading,
    rather than rewording the link: the `make_id` spelling is what the built
    site renders.
    """
    misses = unresolved_fragments()
    assert not misses, "unreachable fragment links:\n  " + "\n  ".join(misses)


@pytest.mark.parametrize(
    ("heading", "expected"),
    (
        ("`--params` option", "--params-option"),
        ("The `--help-format` option", "the---help-format-option"),
        ("`pyproject.toml`", "pyprojecttoml"),
        ("`assert_output_regex`", "assert_output_regex"),
        (
            "Sphinx `click:source` and `click:run` directives",
            "sphinx-clicksource-and-clickrun-directives",
        ),
        ("{octicon}`workflow` Command tree", "octiconworkflow-command-tree"),
    ),
)
def test_github_slug(heading, expected):
    """The slugger reproduces the spellings that diverge from `make_id`.

    Every case is a heading of this documentation whose two slugs disagree,
    which is what makes its `<a name="…">` companion necessary.
    """
    assert github_slug(heading) == expected
