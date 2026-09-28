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

"""Every `{click:run}` block pins the outcome of the CLI it invokes.

The directive executes its body at build time through a bare `exec()`
(`click_extra.sphinx.click`), so any exception a block raises aborts
`sphinx-build`. That makes the documentation build a real gate, but only over
the blocks that raise: a block asserting nothing renders whatever the CLI
printed, and a broken invocation prints a usage error into the published page
while the build stays green. A stale option has shipped that way.

So the build cannot be the only check, and this test supplies the half it
misses: it reads the Markdown as text and requires each block to carry at
least one assertion. What that assertion pins is the author's call. An exact
`result.exit_code` is the strongest form, a containment check on
`result.stdout` still fails when the CLI errors instead of running, and either
one turns a silent page-level regression into a red build.

The check runs on text alone: no build, no network, no platform floor. It
parses the fences through {func}`click_extra.blocks.fence_spans`, which
consumes a fence as an opaque unit, so a `{click:run}` example quoted inside a
longer `code-block` fence is never mistaken for a live directive.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from click_extra.blocks import OPTION_LINE_RE, fence_spans

PROJECT_ROOT = Path(__file__).parent.parent

# Every page a documentation build renders, plus the readme, which carries the
# same directives whenever a feature is showcased there.
MARKDOWN_FILES = (
    *sorted(PROJECT_ROOT.glob("*.md")),
    *sorted((PROJECT_ROOT / "docs").glob("*.md")),
)

# Opening line of a live directive, once its backticks are stripped. A
# `{click:source}` block only defines a CLI, so it asserts nothing by design.
RUN_DIRECTIVE = "{click:run}"


def run_blocks(path: Path) -> list[tuple[int, str]]:
    """Return each `{click:run}` body in `path`, as `(line number, source)`.

    The leading `:option:` lines the directive consumes are dropped, so the
    remainder parses as plain Python. Line numbers are 1-based, naming the
    opening fence.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks = []
    for start, span in sorted(fence_spans(lines).items()):
        if lines[start].strip().lstrip("`") != RUN_DIRECTIVE:
            continue
        close = span.close if span.close is not None else len(lines)
        body = lines[start + 1 : close]
        while body and OPTION_LINE_RE.match(body[0]):
            body.pop(0)
        blocks.append((start + 1, "\n".join(body)))
    return blocks


def test_markdown_files_are_collected():
    """The glob feeding the check still finds the documentation."""
    assert len(MARKDOWN_FILES) > 40, "documentation pages went missing"


def test_run_directives_are_collected():
    """The fence parser still recognizes the directives it is pointed at."""
    total = sum(len(run_blocks(path)) for path in MARKDOWN_FILES)
    assert total > 300, f"only {total} {RUN_DIRECTIVE} blocks found"


@pytest.mark.parametrize(
    "path",
    MARKDOWN_FILES,
    ids=lambda path: str(path.relative_to(PROJECT_ROOT)),
)
def test_run_directives_assert_their_outcome(path):
    """No `{click:run}` block renders its CLI's output unchecked."""
    unchecked = []
    for number, body in run_blocks(path):
        location = f"{path.relative_to(PROJECT_ROOT)}:{number}"
        try:
            tree = ast.parse(body)
        except SyntaxError as error:
            pytest.fail(f"{location} does not parse as Python: {error}")
        if not any(isinstance(node, ast.Assert) for node in ast.walk(tree)):
            unchecked.append(location)

    assert not unchecked, (
        "These {} blocks assert nothing, so a broken invocation renders its "
        "usage error into the page while the build stays green:\n  {}".format(
            RUN_DIRECTIVE,
            "\n  ".join(unchecked),
        )
    )
