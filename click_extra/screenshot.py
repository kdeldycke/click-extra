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

"""Run a CLI, capture its colors, and render the result as a static document.

In Sphinx the {mod}`click:run <click_extra.sphinx.click>` directive executes each
CLI and renders its real output at build time, so a documentation page never
needs a screenshot. A README on GitHub or PyPI, a slide, or a social post cannot
run code, and those surfaces need a capture instead.

The pipeline is three steps, each replaceable on its own:

1. {func}`capture_output` runs the command through
   {func}`~click_extra.execution.run_cli`, under
   {func}`~click_extra.color.forced_color` and a pinned terminal width, and hands
   back its raw ANSI text.
2. {func}`render` turns that text into a document, in one of the
   {class}`CaptureFormat` members.
3. For SVG, {func}`harden_svg` rewrites the rendered source so it survives
   renderers that are not a web browser. That function documents what goes wrong
   without it. HTML needs no such pass: a `<pre>` keeps its own spacing.

{func}`capture` chains all three, and is what the `click-extra screenshot`
command calls.

The two formats are not interchangeable, and neither is a fallback for the
other:

- **SVG** goes where you do not own the page. GitHub and PyPI render an image
  and strip inline HTML, so a README has no other option. It is a picture: the
  text is not selectable, and not searchable.
- **HTML** goes where you do own the page. The text stays selectable,
  searchable and copy-pasteable, and reflows with the container.

```{note}
Only SVG needs the `screenshot` extra, whose Rich dependency renders it. HTML
is built on {func}`~click_extra.styling.ansi_to_html`, which ships with the
package, so it is always available.
```
"""

from __future__ import annotations

import re
import shlex
import subprocess
from enum import Enum
from html import escape, unescape
from io import StringIO

from .color import forced_color
from .execution import args_cleanup, format_cli_prompt, run_cli
from .parameters import missing_extra_message
from .styling import ansi_to_html
from .theme import BUILTIN_THEMES

try:
    from rich.console import Console
    from rich.terminal_theme import DEFAULT_TERMINAL_THEME, SVG_EXPORT_THEME
    from rich.text import Text
except ImportError:
    # Rich ships behind the `screenshot` extra: importing this module stays cheap,
    # and only the rendering entry point raises (see _rich_svg).
    Console = None  # type: ignore[assignment,misc]
    Text = None  # type: ignore[assignment,misc]
    DEFAULT_TERMINAL_THEME = None  # type: ignore[assignment]
    SVG_EXPORT_THEME = None  # type: ignore[assignment]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path

    from .execution import TArg, TEnvVars, TNestedArgs
    from .theme import HelpTheme


class CaptureFormat(Enum):
    """Document formats a capture can be rendered to.

    The value doubles as the file extension {func}`format_from_path` matches on.
    """

    HTML = "html"
    """Selectable, searchable text in a self-contained `<pre>`.

    Built on {func}`~click_extra.styling.ansi_to_html`, so it needs no extra.
    """

    SVG = "svg"
    """A picture of a terminal window, for a surface that strips inline HTML.

    Rendered by Rich, behind the `screenshot` extra.
    """


class CaptureBackground(Enum):
    """Terminal chrome a capture is drawn on.

    A capture freezes the colors of the run it pictures, so the chrome has to
    answer to the palette that run was colored for. Neither direction survives
    the other: a screen colored for a dark terminal is unreadable on white, and
    click-extra's own `light` and `manpage` themes wash out on the dark chrome
    a renderer defaults to.

    The value doubles as the `--background` choice the CLI offers.
    """

    DARK = "dark"
    """What a terminal, and this package's default theme, usually look like."""

    LIGHT = "light"
    """For a CLI rendered with a light-background theme."""

    def __str__(self):
        return self.name.lower()


CAPTURE_BACKGROUND = "#292929"
"""Background a dark capture is drawn on.

Matches the palette Rich's SVG export uses, so the two formats look like the
same terminal. Stating it is not optional: a help screen colored for a dark
terminal is unreadable on a page that defaults to white.
"""

CAPTURE_FOREGROUND = "#c5c8c6"
"""Color of the text a dark capture leaves unstyled. See {data}`CAPTURE_BACKGROUND`."""

LIGHT_CAPTURE_BACKGROUND = "#ffffff"
"""Background a light capture is drawn on.

The white Rich's own light terminal theme names, for the same reason
{data}`CAPTURE_BACKGROUND` mirrors its dark one: an SVG and an HTML capture of
the same run have to look like the same terminal.
"""

LIGHT_CAPTURE_FOREGROUND = "#000000"
"""Color of the text a light capture leaves unstyled.

See {data}`LIGHT_CAPTURE_BACKGROUND`.
"""

CAPTURE_COLORS: dict[CaptureBackground, tuple[str, str]] = {
    CaptureBackground.DARK: (CAPTURE_BACKGROUND, CAPTURE_FOREGROUND),
    CaptureBackground.LIGHT: (LIGHT_CAPTURE_BACKGROUND, LIGHT_CAPTURE_FOREGROUND),
}
"""Background and unstyled-foreground pair each chrome draws HTML with."""

PROMPT_THEMES: dict[CaptureBackground, HelpTheme | None] = {
    CaptureBackground.DARK: None,
    CaptureBackground.LIGHT: BUILTIN_THEMES.get("light"),
}
"""Theme the prompt line is drawn with, per chrome.

The captured output arrives already colored by the CLI that produced it, under
whatever theme *that* run was told to use. The prompt is the one line this
process draws itself, so it is the one that would otherwise land on white
chrome in the dark default's near-white `invoked_command` style, invisible.

`None` keeps whatever theme the invocation already runs under. So does a
missing entry: the mapping is read through {meth}`dict.get`, and
{data}`~click_extra.theme.BUILTIN_THEMES` is empty when a trimmed install drops
`themes.toml`.
"""

CAPTURE_THEMES = {
    CaptureBackground.DARK: SVG_EXPORT_THEME,
    CaptureBackground.LIGHT: DEFAULT_TERMINAL_THEME,
}
"""Rich terminal theme each chrome renders SVG with.

A theme carries the 16 ANSI colors alongside the chrome, which is the other half
of the job: a CLI naming `blue` leaves the shade to whoever draws it, and the
one that reads on white is not the one that reads on `#292929`. Both entries are
`None` without the `screenshot` extra, where no SVG is rendered anyway.
"""

CAPTURE_FONT_STACK = "'Fira Code', 'Cascadia Code', Menlo, Consolas, monospace"
"""Monospaced fonts an HTML capture asks for, best first.

Opens with the family Rich's SVG export names, so a reader who has it sees both
formats set identically.

Family names are single-quoted on purpose: this lands in a double-quoted
`style` attribute, which a double quote here would terminate early.
"""

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

    A run carrying no glyph is left alone. Rich ends every line with one holding
    just a newline, and that is what keeps a blank line present in the source; a
    run of pure padding (which Rich never emits, though another tool might) has
    nothing to reposition anyway.

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


def render_html(
    text: str,
    *,
    title: str = "",
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
) -> str:
    """Render captured terminal text to HTML.

    The `<pre>` carries its own inline styling, so a fragment pasted into an
    existing page needs no stylesheet and cannot be restyled out of legibility
    by the host. Nothing else is needed either: a `<pre>` preserves the
    capture's own spacing, which is what spares HTML the offset surgery
    {func}`harden_svg` performs on SVG.

    ```{caution}
    The text is escaped before its ANSI is translated, the order
    {mod}`click_extra.table` uses for its `html` format. Skip it and any `<` a
    CLI prints opens a tag: click-extra's own `--export-config` help says it
    writes `to <stdout>`.
    ```

    ```{note}
    An OSC 8 hyperlink loses its URL and keeps its visible text: the escape is
    dropped rather than turned into an `<a>`.
    ```

    :param text: captured output, ANSI escape sequences included.
    :param title: `<title>` of the document. Ignored for a fragment.
    :param full: wrap the `<pre>` in a standalone document. `False` returns the
        `<pre>` alone, to paste into a page that has its own.
    :param background: chrome to draw on, see {class}`CaptureBackground`.
    :return: the rendered markup.
    """
    chrome, ink = CAPTURE_COLORS[background]
    body = (
        f'<pre style="background: {chrome}; color: {ink}; '
        f"font-family: {CAPTURE_FONT_STACK}; line-height: 1.25; padding: 1em; "
        f'overflow-x: auto">{ansi_to_html(escape(text, quote=False))}</pre>'
    )
    if not full:
        return body
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{escape(title, quote=False)}</title>\n"
        "</head>\n"
        f'<body style="margin: 0">\n{body}\n</body>\n'
        "</html>\n"
    )


def render(
    text: str,
    *,
    format: CaptureFormat = CaptureFormat.SVG,
    columns: int = DEFAULT_COLUMNS,
    title: str = "",
    unique_id: str | None = None,
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
) -> str:
    """Render captured terminal text to the document `format` names.

    :param text: captured output, ANSI escape sequences included.
    :param format: which document to produce.
    :param columns: terminal width, in characters, an SVG is laid out at. HTML
        reflows, so it ignores this.
    :param title: caption drawn in an SVG's window chrome, or an HTML document's
        `<title>`.
    :param unique_id: SVG only. Prefix namespacing the source's CSS classes and
        element IDs. Pinning it to something stable (the output file's name, say)
        keeps a regenerated capture diffing line by line, instead of renaming
        every class as soon as a single character of output changes. Characters
        a CSS class name cannot carry are folded to a dash.
    :param full: HTML only. See {func}`render_html`.
    :param background: chrome to draw on, see {class}`CaptureBackground`.
    :return: the rendered document.
    :raises ImportError: rendering SVG without the `screenshot` extra installed.
    """
    if format is CaptureFormat.HTML:
        return render_html(text, title=title, full=full, background=background)
    if unique_id:
        unique_id = _NON_IDENTIFIER_RE.sub("-", unique_id)
    return harden_svg(
        _rich_svg(
            text,
            columns=columns,
            title=title,
            unique_id=unique_id,
            background=background,
        ),
    )


def capture(
    args: TArg | TNestedArgs,
    *,
    format: CaptureFormat = CaptureFormat.SVG,
    columns: int = DEFAULT_COLUMNS,
    prompt: str | None = None,
    head: int | None = None,
    tail: int | None = None,
    truncation: str = DEFAULT_TRUNCATION,
    merge_stderr: bool = False,
    timeout: float | None = None,
    title: str = "",
    unique_id: str | None = None,
    full: bool = True,
    background: CaptureBackground = CaptureBackground.DARK,
) -> tuple[str, int]:
    """Run a command and render its output as a document.

    Chains {func}`capture_output`, {func}`trim_lines` and {func}`render`. The
    invocation is drawn above the output as a shell prompt, styled by the active
    theme through {func}`~click_extra.execution.format_cli_prompt`, so the
    capture shows what to type to reproduce it.

    :param args: the command line to run.
    :param format: which document to produce.
    :param columns: terminal width, in characters.
    :param prompt: command line to *display*, when it differs from the one run.
        `uv run --frozen -- my-cli` reproduces a capture from a checkout, but
        `my-cli` is what a reader types. An empty string draws no prompt at all.
    :param head: number of leading output lines to keep.
    :param tail: number of trailing output lines to keep.
    :param truncation: line standing in for the lines cut by `head` or `tail`.
    :param merge_stderr: fold `stderr` into the captured output.
    :param timeout: seconds before the command is killed.
    :param title: see {func}`render`.
    :param unique_id: see {func}`render`.
    :param full: see {func}`render`.
    :param background: see {func}`render`.
    :return: the rendered document, and the command's exit code.
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
            prompt_line = format_cli_prompt(displayed, theme=PROMPT_THEMES[background])
            text = f"{prompt_line}\n{text}"
    return (
        render(
            text,
            format=format,
            columns=columns,
            title=title,
            unique_id=unique_id,
            full=full,
            background=background,
        ),
        process.returncode,
    )


def format_from_path(path: Path) -> CaptureFormat:
    """Pick the capture format a file name asks for.

    :param path: where the capture is to be written.
    :return: the {class}`CaptureFormat` its extension names.
    :raises ValueError: when the extension names no format.
    """
    suffix = path.suffix.lower().lstrip(".")
    # `.htm` is the same document under the older extension.
    if suffix == "htm":
        suffix = CaptureFormat.HTML.value
    try:
        return CaptureFormat(suffix)
    except ValueError:
        known = ", ".join(sorted(f".{member.value}" for member in CaptureFormat))
        raise ValueError(
            f"Cannot tell the capture format of {path.name!r}: name it {known}."
        ) from None


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
    background: CaptureBackground = CaptureBackground.DARK,
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
    return console.export_svg(
        title=title,
        unique_id=unique_id,
        theme=CAPTURE_THEMES[background],
    )
