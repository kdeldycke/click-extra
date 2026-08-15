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

"""Run a CLI, capture its colors, and render the result as a static image.

In Sphinx the {mod}`click:run <click_extra.sphinx.click>` directive executes each
CLI and renders its real output at build time, so a documentation page never
needs a screenshot. A README on GitHub or PyPI, a slide, or a social post cannot
run code, and those surfaces need a captured image instead.

The pipeline is three steps, each replaceable on its own:

1. {func}`capture_output` runs the command through
   {func}`~click_extra.execution.run_cli`, under
   {func}`~click_extra.color.forced_color` and a pinned terminal width, and hands
   back its raw ANSI text.
2. {func}`render_svg` turns that text into SVG source. Rich is the only backend
   today, and every call into it is confined to {func}`_rich_svg`: swapping
   renderers means writing that one function, leaving the capture, the hardening
   pass, the CLI and their tests untouched.
3. {func}`harden_svg` rewrites the rendered source so it survives renderers that
   are not a web browser. That function documents what goes wrong without it.

{func}`capture_svg` chains all three, and is what the `click-extra screenshot`
command calls.

```{note}
The renderer ships behind the `screenshot` extra, so importing this module stays
cheap and only {func}`render_svg` raises when Rich is absent.
```
"""

from __future__ import annotations

import re
import shlex
import subprocess
from html import escape, unescape
from io import StringIO

from .color import forced_color
from .execution import args_cleanup, format_cli_prompt, run_cli
from .parameters import missing_extra_message

try:
    from rich.console import Console
    from rich.text import Text
except ImportError:
    # Rich ships behind the `screenshot` extra: importing this module stays cheap,
    # and only the rendering entry point raises (see _rich_svg).
    Console = None  # type: ignore[assignment,misc]
    Text = None  # type: ignore[assignment,misc]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from .execution import TArg, TEnvVars, TNestedArgs


DEFAULT_COLUMNS = 80
"""Terminal width a capture is taken at, in characters.

Both ends of the pipeline have to agree on it: the command wraps its output to
this width, and the renderer lays the image out at the same one. Let them
disagree and the rendered lines overrun the image. 80 is the width Click itself
falls back to off a terminal, which makes it the value a capture lands on by
accident anyway.
"""

DEFAULT_TRUNCATION = "[...]"
"""Marker standing in for the lines {func}`trim_lines` cut away."""

PADDING = " \N{NO-BREAK SPACE}"
"""Characters a renderer pads a text run with to place it on its column.

Rich emits every space as a non-breaking one, so the padding survives an XML
round-trip; a plain space is accepted too, for sources written by other tools.
"""

_TEXT_ELEMENT_RE = re.compile(r"<text(?P<attrs>[^>]*)>(?P<content>[^<]*)</text>")
"""One run of same-styled characters in a rendered capture."""

_X_ATTR_RE = re.compile(r'\bx="(?P<value>-?[\d.]+)"')
"""The horizontal offset a text run is drawn at, in pixels."""

_TEXT_LENGTH_ATTR_RE = re.compile(r'\btextLength="(?P<value>[\d.]+)"')
"""The width a text run is asked to occupy, in pixels."""

_NON_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_-]+")
"""Characters a CSS class name cannot carry, as written into `unique_id`."""


def capture_output(
    args: TArg | TNestedArgs,
    *,
    columns: int = DEFAULT_COLUMNS,
    merge_stderr: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and capture its output, ANSI escape sequences and all.

    A command whose output is a pipe rather than a terminal strips its own
    colors, and wraps to whatever width it can guess. Both are pinned here:
    {func}`~click_extra.color.forced_color` sets the `FORCE_COLOR` lever both
    Click's and Rich's color systems obey and clears any opt-out the environment
    carries, while `COLUMNS` fixes the width the command wraps to.

    Only `stdout` is captured by default. That is what keeps a capture free of
    the progress lines and build chatter a wrapper like `uv` writes to `stderr`,
    with no shell redirection to remember.

    :param args: the command line, in the nested form
        {func}`~click_extra.execution.run_cli` accepts.
    :param columns: terminal width, in characters, the command wraps its output
        to.
    :param merge_stderr: fold `stderr` into the captured output, for a command
        printing its help there.
    :param timeout: seconds before the command is killed. `None` waits forever.
    :return: the completed process, whose `stdout` holds the captured text.
    """
    extra_env: TEnvVars = {"COLUMNS": str(columns)}
    with forced_color():
        return run_cli(
            args,
            extra_env=extra_env,
            timeout=timeout,
            merge_streams=merge_stderr,
        )


def trim_lines(
    text: str,
    *,
    head: int | None = None,
    tail: int | None = None,
    truncation: str = DEFAULT_TRUNCATION,
) -> str:
    """Keep only the first `head` and last `tail` lines of `text`.

    Whatever is dropped is replaced by a single `truncation` line, so the image
    admits that it was cut rather than pretending to be the whole output. Text
    short enough to survive both bounds comes back untouched, with no marker.

    :param text: the captured output.
    :param head: number of leading lines to keep, or `None` for no head bound.
    :param tail: number of trailing lines to keep, or `None` for no tail bound.
    :param truncation: line standing in for what was cut.
    :return: the trimmed text.
    """
    if head is None and tail is None:
        return text
    lines = text.splitlines()
    kept = (head or 0) + (tail or 0)
    if kept >= len(lines):
        return text
    return "\n".join([
        *(lines[:head] if head else []),
        truncation,
        *(lines[-tail:] if tail else []),
    ])


def measure_cell_width(svg: str) -> float:
    """Measure the width of one glyph cell, in pixels, from a rendered capture.

    A capture is monospaced, so every run of characters is `textLength` pixels
    wide for exactly as many characters. The widest run gives that ratio with the
    least rounding error.

    :param svg: source of a rendered capture.
    :return: the width of a single character cell, in pixels.
    :raises ValueError: when the source carries no sized text run.
    """
    widest = 0
    cell_width = 0.0
    for element in _TEXT_ELEMENT_RE.finditer(svg):
        length = _TEXT_LENGTH_ATTR_RE.search(element["attrs"])
        content = unescape(element["content"])
        if length and len(content) > widest:
            widest = len(content)
            cell_width = float(length["value"]) / widest
    if not cell_width:
        raise ValueError("No sized text run found: not a rendered terminal capture.")
    return cell_width


def harden_svg(svg: str, cell_width: float | None = None) -> str:
    """Move each text run's leading padding out of its glyphs and into its offset.

    A renderer places a run of same-styled characters with an `x` offset, then
    leans on `textLength` to hold that run to an exact width. The padding that
    separates two columns lives *inside* the run, as spaces preceding the text.
    So a column only lands where it belongs if the glyphs are the exact width the
    renderer assumed, which asks two things of whoever displays the file: honor
    `textLength`, and resolve the font the source names.

    A web browser does both. Little else does. `librsvg` (and through it
    `rsvg-convert` and ImageMagick) ignores `textLength` outright, and a file
    manager, a git client or a thumbnailer commonly falls back to a proportional
    font. Either way every glyph sitting behind padding slides out of its column,
    and neighbouring words collide.

    Stripping that padding and advancing `x` by as many cells makes each run start
    on its own column, so a renderer only has to draw glyphs, not match metrics. A
    browser is unaffected: `textLength` is rewritten to the width of what is left.

    Runs made of nothing but padding are left alone. They paint no glyph in any
    font, and keeping them preserves the blank lines of the capture.

    :param svg: source of a rendered capture.
    :param cell_width: width of a character cell, in pixels. Measured from the
        source when not given (see {func}`measure_cell_width`).
    :return: the hardened source.
    """
    measured = measure_cell_width(svg) if cell_width is None else cell_width

    def rewrite(element: re.Match[str]) -> str:
        attrs = element["attrs"]
        content = unescape(element["content"])
        stripped = content.strip(PADDING)
        offset = _X_ATTR_RE.search(attrs)
        if not stripped or not offset:
            return element[0]
        indent = len(content) - len(content.lstrip(PADDING))
        column = float(offset["value"]) + indent * measured
        attrs = _X_ATTR_RE.sub(lambda _: f'x="{_svg_number(column)}"', attrs, count=1)
        attrs = _TEXT_LENGTH_ATTR_RE.sub(
            lambda _: f'textLength="{_svg_number(len(stripped) * measured)}"',
            attrs,
            count=1,
        )
        return f"<text{attrs}>{_xml_escape(stripped)}</text>"

    return _TEXT_ELEMENT_RE.sub(rewrite, svg)


def render_svg(
    text: str,
    *,
    columns: int = DEFAULT_COLUMNS,
    title: str = "",
    unique_id: str | None = None,
) -> str:
    """Render captured terminal text to hardened SVG source.

    :param text: captured output, ANSI escape sequences included.
    :param columns: terminal width, in characters, the image is laid out at.
    :param title: caption drawn in the window chrome.
    :param unique_id: prefix namespacing the source's CSS classes and element
        IDs. Pinning it to something stable (the output file's name, say) keeps a
        regenerated capture diffing line by line, instead of renaming every class
        as soon as a single character of output changes. Characters a CSS class
        name cannot carry are folded to a dash.
    :return: the rendered source.
    :raises ImportError: when the `screenshot` extra is not installed.
    """
    if unique_id:
        unique_id = _NON_IDENTIFIER_RE.sub("-", unique_id)
    return harden_svg(
        _rich_svg(text, columns=columns, title=title, unique_id=unique_id),
    )


def capture_svg(
    args: TArg | TNestedArgs,
    *,
    columns: int = DEFAULT_COLUMNS,
    prompt: str | None = None,
    head: int | None = None,
    tail: int | None = None,
    truncation: str = DEFAULT_TRUNCATION,
    merge_stderr: bool = False,
    timeout: float | None = None,
    title: str = "",
    unique_id: str | None = None,
) -> tuple[str, int]:
    """Run a command and render its output as hardened SVG source.

    Chains {func}`capture_output`, {func}`trim_lines` and {func}`render_svg`. The
    invocation is drawn above the output as a shell prompt, styled by the active
    theme through {func}`~click_extra.execution.format_cli_prompt`, so the image
    shows what to type to reproduce it.

    :param args: the command line to run.
    :param columns: terminal width, in characters.
    :param prompt: command line to *display*, when it differs from the one run.
        `uv run --frozen -- my-cli` reproduces a capture from a checkout, but
        `my-cli` is what a reader types. An empty string draws no prompt at all.
    :param head: number of leading output lines to keep.
    :param tail: number of trailing output lines to keep.
    :param truncation: line standing in for the lines cut by `head` or `tail`.
    :param merge_stderr: fold `stderr` into the captured output.
    :param timeout: seconds before the command is killed.
    :param title: caption drawn in the window chrome.
    :param unique_id: prefix namespacing the source's CSS classes.
    :return: the rendered source, and the command's exit code.
    """
    process = capture_output(
        args,
        columns=columns,
        merge_stderr=merge_stderr,
        timeout=timeout,
    )
    text = trim_lines(
        process.stdout,
        head=head,
        tail=tail,
        truncation=truncation,
    )
    displayed = args_cleanup(args) if prompt is None else tuple(shlex.split(prompt))
    if displayed:
        with forced_color():
            text = f"{format_cli_prompt(displayed)}\n{text}"
    return (
        render_svg(text, columns=columns, title=title, unique_id=unique_id),
        process.returncode,
    )


def _svg_number(value: float) -> str:
    """Render a coordinate the way a renderer does, to a tenth of a pixel."""
    return f"{value:.1f}".removesuffix(".0")


def _xml_escape(text: str) -> str:
    """Escape text for an XML element, spelling padding as a character reference.

    A literal non-breaking space is valid XML but invisible in a diff, and easily
    mangled by an editor stripping trailing whitespace.
    """
    return escape(text, quote=False).replace("\N{NO-BREAK SPACE}", "&#160;")


def _rich_svg(
    text: str,
    *,
    columns: int,
    title: str,
    unique_id: str | None,
) -> str:
    """Render terminal text to SVG source with Rich.

    The only place in Click Extra that talks to Rich. It takes ANSI text and
    returns SVG source, which is the whole contract {func}`render_svg` needs: a
    replacement backend has to satisfy that signature and emit `<text>` runs
    carrying `x` and `textLength`, and nothing else in the package changes.

    The console writes to a throwaway buffer because only the recording is
    wanted, and is forced into terminal mode at full color depth: it is fed text
    that already carries ANSI escapes, so nothing here should decide the output
    is not worth coloring.
    """
    if Console is None:
        raise ImportError(
            missing_extra_message("screenshot", subject="Screenshot rendering"),
        )
    console = Console(
        record=True,
        width=columns,
        file=StringIO(),
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
    )
    console.print(Text.from_ansi(text.rstrip("\n")))
    return console.export_svg(title=title, unique_id=unique_id)
