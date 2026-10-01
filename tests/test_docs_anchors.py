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

Docstrings take a third path to the site. `click_extra.sphinx.myst_docstrings`
passes their link targets to reST unchanged. A `page.md#anchor` target, which
myst-parser resolves in a page, thus ships as written, and the site serves no
`.md` file. So a docstring links a page with `{doc}` and a section with `{ref}`.

The check runs on text alone: no build, no network, no platform floor. Its
counterpart on the built HTML is `test_sphinx_crossrefs.py`, which is skipped
off Linux, and the `check-broken-links` CI job, which files an issue instead
of failing a run. Both let a broken anchor sit for a full cycle.
"""

from __future__ import annotations

import ast
import re
import sys
import textwrap
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

# The modules whose docstrings autodoc renders into the API pages.
PACKAGE_SOURCES = tuple(sorted((PROJECT_ROOT / "click_extra").rglob("*.py")))

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

# An inline link to a page named by its source file: `](page.md)` or
# `](page.md#frag)`. A URL carries a scheme, so its colon keeps it from matching.
PAGE_LINK = re.compile(r"]\((?P<target>[^()\s:#]+\.md(?:#[^()\s]*)?)\)")

# A `#:` comment, which autodoc renders as the docstring of the name below it.
SHARP_COLON = re.compile(r"^\s*#:\s?(?P<text>.*)$")

# A code span: a run of backticks, closed by the next run of the same length.
# lychee reads no link and no anchor inside one. A span broken across two lines
# is left as it is.
INLINE_CODE = re.compile(r"(?<!`)(?P<ticks>`+)(?!`).+?(?<!`)(?P=ticks)(?!`)")


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


def closes_fence(marker: str, opening: str) -> bool:
    """Tell whether a line's fence `marker` closes the block `opening` started."""
    return marker.startswith(opening[0]) and len(marker) >= len(opening)


def uncoded_lines(
    content: str, keep_directive_bodies: bool = False
) -> list[tuple[int, str]]:
    """Number and return the lines sitting outside a code fence.

    lychee ignores fenced content, so a link in an example is not a link. The
    docstring converter renders the body of a directive fence like `{note}`, so
    `keep_directive_bodies` returns those lines, without the fence markers.
    """
    lines: list[tuple[int, str]] = []
    opening = ""
    directives: list[str] = []
    for number, line in enumerate(content.splitlines(), 1):
        close = FENCE_CLOSE.match(line)
        marker = close.group("marker") if close else ""
        if opening:
            if closes_fence(marker, opening):
                opening = ""
            continue
        if directives and closes_fence(marker, directives[-1]):
            directives.pop()
            continue
        fence = FENCE_OPEN.match(line)
        # A backtick fence's info string may not itself hold a backtick, which
        # is what keeps inline code like ``x`` from opening a block.
        if fence and not (
            fence.group("marker")[0] == "`" and "`" in fence.group("info")
        ):
            if keep_directive_bodies and fence.group("info").startswith("{"):
                directives.append(fence.group("marker"))
            else:
                opening = fence.group("marker")
            continue
        lines.append((number, line))
    return lines


def uncoded_spans(line: str) -> str:
    """Drop a line's code spans, so a link or anchor quoted in prose is not read.

    Headings are slugged from the raw line instead: GitHub keeps the text of a
    code span in a heading's slug.
    """
    return INLINE_CODE.sub("", line)


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
        anchors.update(HTML_ANCHOR.findall(uncoded_spans(line)))
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
            for link in FRAGMENT_LINK.finditer(uncoded_spans(line)):
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


def rendered_prose(path: Path) -> list[tuple[int, str]]:
    """Collect the prose autodoc renders from a module, with the line it starts on.

    Every bare string statement counts, so attribute docstrings join the module,
    class and function ones, and so does every `#:` comment. A docstring loses
    its indentation after the first line, so a fence opens at the margin as it
    does in a page.
    """
    source = path.read_text(encoding="utf-8")
    prose = [
        (number, comment.group("text"))
        for number, line in enumerate(source.splitlines(), 1)
        if (comment := SHARP_COLON.match(line))
    ]
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            first, _, rest = node.value.value.partition("\n")
            prose.append((node.lineno, f"{first}\n{textwrap.dedent(rest)}"))
    return sorted(prose)


def docstring_page_links(paths=PACKAGE_SOURCES) -> list[tuple[Path, int, str]]:
    """Report every docstring link that names a page by its `.md` file."""
    links = []
    for path in paths:
        for start, text in rendered_prose(path):
            for number, line in uncoded_lines(text, keep_directive_bodies=True):
                for link in PAGE_LINK.finditer(uncoded_spans(line)):
                    links.append((path, start + number - 1, link.group("target")))
    return links


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


@pytest.mark.parametrize(
    ("line", "expected"),
    (
        ("Write `[text](#walled-garden)` to link it.", "Write  to link it."),
        ("``a ` b`` and `c`", " and "),
        ("[`pond`](water.md#the-pond)", "[](water.md#the-pond)"),
        ("A lone ` backtick stays.", "A lone ` backtick stays."),
    ),
)
def test_uncoded_spans(line, expected):
    """A span goes whatever its backtick count, and a lone backtick stays."""
    assert uncoded_spans(line) == expected


def test_code_spans_hold_no_link_and_no_anchor(tmp_path):
    """A link or an anchor quoted in a code span is prose, as lychee reads it."""
    page = tmp_path / "pond.md"
    page.write_text(
        "# Pond\n\n"
        'Quote `<a name="lily"></a>` or `[the reeds](#reeds)` in prose.\n'
        "Then [go back up](#pond).\n",
        encoding="utf-8",
    )
    assert readable_anchors(page) == {"pond"}
    assert unresolved_fragments([page]) == []


def test_package_sources_are_collected():
    """The glob feeding the docstring check still finds the package."""
    assert len(PACKAGE_SOURCES) > 50, "package modules went missing"


def test_docstrings_link_pages_by_role():
    """No docstring links a documentation page by its `.md` file.

    A failure names a link that ships dead. Link the page with `{doc}`, or its
    section with `{ref}` after adding a `(label)=` target above the heading.
    """
    misses = [
        f"{path.relative_to(PROJECT_ROOT)}:{number} -> {target}"
        for path, number, target in docstring_page_links()
    ]
    assert not misses, "docstring links to .md files:\n  " + "\n  ".join(misses)


def test_docstring_page_links_are_found(tmp_path):
    """The scan reads every docstring autodoc renders, and only their prose."""
    module = tmp_path / "pond.py"
    module.write_text(
        '"""Frogs live in the [pond](pond.md#frogs)."""\n'
        "\n"
        "#: Counted on the [lily page](lilies.md).\n"
        "LILIES = 3\n"
        '"""Each one floats: see [floating](lilies.md#floating)."""\n'
        "\n"
        "\n"
        "def croak():\n"
        '    """Quote `[the reeds](reeds.md)`, or read about the\n'
        "    [heron](https://example.com/heron.md).\n"
        "\n"
        "    ```{note}\n"
        "    Herons [eat frogs](herons.md#diet).\n"
        "    ```\n"
        "\n"
        "    ```markdown\n"
        "    [a duck](ducks.md)\n"
        "    ```\n"
        '    """\n',
        encoding="utf-8",
    )
    assert docstring_page_links([module]) == [
        (module, 1, "pond.md#frogs"),
        (module, 3, "lilies.md"),
        (module, 5, "lilies.md#floating"),
        (module, 13, "herons.md#diet"),
    ]
