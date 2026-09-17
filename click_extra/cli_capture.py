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

"""The `screenshot` and `snippet` commands of the `click-extra` CLI.

Both draw a document from terminal text: the first captures what a command
prints, the second colors a source file, and they share the window options,
the output resolution and the delivery through {func}`capture_options`,
{func}`resolve_capture_format` and {func}`deliver_capture`.
{mod}`click_extra.cli` registers them on the root group.
"""

from __future__ import annotations

import logging
import shlex
import shutil
import sys
from pathlib import Path

import click
from click import BadParameter, Choice, ClickException, FloatRange, IntRange, echo
from cloup import file_path

from ._utils import missing_extra_message
from .color import invocation_color
from .decorators import argument, command, option
from .highlight import HelpKeywords
from .recording import (
    DEFAULT_RECORDING_BLANK,
    DEFAULT_RECORDING_HOLD,
    DEFAULT_ROWS,
    DEFAULT_SUBMIT,
    record_and_render,
)
from .screenshot import (
    AUTO_COLUMNS,
    AUTO_CURSOR,
    AUTO_TRUNCATION,
    DEFAULT_COLUMNS,
    DEFAULT_MARGIN,
    DEFAULT_PADDING,
    DEFAULT_TRUNCATION,
    MIN_COLUMNS,
    STDOUT_PATH,
    CaptureBackground,
    CaptureFormat,
    Chrome,
    capture,
    format_from_path,
)
from .screenshot_presets import PRESETS, Cursor, CursorShape
from .screenshot_svg import (
    AUTO_HOLD,
    DEFAULT_BORDER_WIDTH,
    DEFAULT_RADIUS,
    DEFAULT_WATERMARK,
    NO_PAINT,
    OPAQUE,
)
from .types import EnumChoice

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from typing_extensions import Unpack

    from .screenshot import ChromeArguments, TColumns
    from .screenshot_presets import TerminalPreset
    from .screenshot_svg import THold

logger = logging.getLogger(__name__)


def _resolve_preset(name: str | None) -> TerminalPreset | None:
    """The terminal preset `--preset` names, or `None` when it names none."""
    return None if name is None else PRESETS[name.lower()]


def _parse_columns(
    ctx: click.Context,
    param: click.Parameter,
    value: str,
) -> TColumns:
    """Read `--columns` into a width, or into the sentinel asking for none.

    A width and {data}`~click_extra.screenshot.AUTO_COLUMNS` are the two things
    the capture pipeline accepts, and Click has no type spelling "an integer or
    that one word".
    """
    if value.strip().lower() == AUTO_COLUMNS:
        return AUTO_COLUMNS
    try:
        width = int(value)
    except ValueError:
        raise BadParameter(f"{value!r} is neither an integer nor {AUTO_COLUMNS!r}.")
    if width < MIN_COLUMNS:
        raise BadParameter(f"{width} is narrower than the {MIN_COLUMNS}-column floor.")
    return width


def _parse_emphasis(
    ctx: click.Context,
    param: click.Parameter,
    value: str | None,
) -> tuple[int, ...]:
    """Read `--emphasize-lines` into the lines it names.

    Takes the shape `:emphasize-lines:` takes, `2,4-5`, minus the open-ended
    range: a range needs the capture's height to close, and that is not known
    until the command has run and its output has been trimmed.
    """
    if not value:
        return ()
    lines: set[int] = set()
    for entry in value.split(","):
        piece = entry.strip()
        if not piece:
            continue
        bounds = piece.split("-")
        if len(bounds) > 2 or not all(bound.strip().isdigit() for bound in bounds):
            raise BadParameter(
                f"{piece!r} is neither a line nor a closed range of them.",
            )
        first, last = int(bounds[0]), int(bounds[-1])
        if first < 1 or last < first:
            raise BadParameter(f"{piece!r} is not a range of lines, counted from 1.")
        lines.update(range(first, last + 1))
    return tuple(sorted(lines))


def deliver_capture(document: str, output: Path) -> None:
    """Write a rendered capture where `--output` points.

    {data}`~click_extra.screenshot.STDOUT_PATH` prints it instead, through
    {func}`click.echo` rather than a bare write: that is what strips the escape
    sequences when the terminal turns out to be a pipe, and what lets `--color`,
    `--no-color`, `--accessible` and `NO_COLOR` reach a capture, since
    {func}`~click_extra.color.invocation_color` carries the tri-state all four
    of them resolve to.

    :param document: the rendered capture.
    :param output: where it goes.
    """
    if output.name == STDOUT_PATH:
        # Exactly one closing newline, whether or not the capture brought its
        # own: a picture is a file and may end however it likes, but a terminal
        # left mid-line puts the next prompt on top of the last row.
        echo(document, nl=not document.endswith("\n"), color=invocation_color())
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    echo(f"Wrote {output}")


def resolve_capture_format(output: Path, fragment: bool) -> CaptureFormat:
    """Read the capture format off `--output`, and settle `--fragment` on it.

    Both capture commands carry the pair of options, so both carry the same
    rejection: `--fragment` asks for the bare block of a standalone document,
    and only HTML has one.

    :param output: where the capture goes; its extension names the format.
    :param fragment: whether the caller asked for the bare block.
    :raises ClickException: on an extension no format claims, or on `--fragment`
        against anything but HTML.
    """
    try:
        capture_format = format_from_path(output)
    except ValueError as error:
        raise ClickException(str(error)) from error

    if fragment and capture_format is not CaptureFormat.HTML:
        raise ClickException("--fragment only applies to an HTML capture.")

    return capture_format


def capture_options(
    *,
    columns_help: str,
    default_columns: TColumns = DEFAULT_COLUMNS,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attach every option the two capture commands share.

    `screenshot` pictures what a command printed and `snippet` pictures what a
    file says, but both hand their text to the same renderer, so everything from
    the window's frame to its credit line is one vocabulary. Declaring it once
    is what stops the two drifting into near-synonyms, which is the failure a
    reader hits rather than a maintainer: they learn `--backdrop` on one command
    and expect it on the other.

    Only the width differs, both in what it defaults to and in what it governs:
    a command wraps its own output to it, where a file was never wrapped at all.

    ```{note}
    The options are applied in reverse, so the tuple below reads in the order
    `--help` prints. A command's own options are declared under this decorator
    and land after the shared ones, which is what keeps the common vocabulary
    together at the top of every capture command's help screen.
    ```

    :param columns_help: what the width means for this command.
    :param default_columns: the width it takes when nothing states one.
    :return: the decorator attaching all of them.
    """
    shared = (
        option(
            "--output",
            required=True,
            type=file_path(writable=True, resolve_path=True, allow_dash=True),
            help="Path of the file to write. Its extension picks the format: "
            ".svg for an image, .html for selectable text, .ansi for the escape "
            "sequences themselves. Pass - to print those to the terminal, "
            "which draws no window.",
        ),
        option(
            "--columns",
            metavar="[auto|INTEGER]",
            default=str(default_columns),
            show_default=True,
            callback=_parse_columns,
            help=columns_help,
        ),
        option(
            "--background",
            type=EnumChoice(CaptureBackground),
            default=CaptureBackground.DARK,
            show_default=True,
            help="Terminal chrome the capture is drawn on, and the palette its "
            "colors resolve against. Match it to the theme the captured CLI "
            "renders with: a light-background theme washes out on the dark "
            "default.",
        ),
        option(
            "--preset",
            type=Choice(sorted(PRESETS), case_sensitive=False),
            default=None,
            help="Terminal to draw the capture as: its window decorations, "
            "palette, font and prompt sigil. Anything stated alongside wins "
            "over it. Left out, the capture keeps the renderer's own neutral "
            "window.",
        ),
        option(
            "--border",
            metavar="COLOR",
            default=None,
            help="Color of the frame drawn around the terminal window, as CSS "
            "names it. Pass none to draw no frame. Defaults to the one the "
            "chrome can show.",
        ),
        option(
            "--border-width",
            type=IntRange(min=0),
            metavar="PIXELS",
            default=DEFAULT_BORDER_WIDTH,
            show_default=True,
            help="Thickness of that frame, in pixels.",
        ),
        option(
            "--radius",
            type=IntRange(min=0),
            metavar="PIXELS",
            default=None,
            help="How round the window's corners are, in pixels. Zero squares "
            f"them. Defaults to {DEFAULT_RADIUS}, or to the rounding --preset "
            "terminal draws.",
        ),
        option(
            "--backdrop",
            metavar="COLOR",
            default=NO_PAINT,
            show_default=True,
            help="Color filling the image behind the window, margin included, "
            "as CSS names it. Left transparent by default, so the page shows "
            "through.",
        ),
        option(
            "--shadow",
            metavar="COLOR",
            default=None,
            help="Color of the drop shadow lifting the window off the page, as "
            "CSS names it. Pass none to draw no shadow. Defaults to the one the "
            "chrome calls for.",
        ),
        option(
            "--margin",
            type=IntRange(min=0),
            metavar="PIXELS",
            default=DEFAULT_MARGIN,
            show_default=True,
            help="Transparent pixels left around the window, on all four sides. "
            "The room the drop shadow falls into, so a capture drawing one "
            "wants some.",
        ),
        option(
            "--padding",
            type=IntRange(min=0),
            metavar="PIXELS",
            default=DEFAULT_PADDING,
            show_default=True,
            help="Pixels added inside the window, around the drawn text, on top "
            "of the few the renderer adds on its own.",
        ),
        option(
            "--opacity",
            type=FloatRange(min=0, max=1),
            default=OPAQUE,
            show_default=True,
            help="How solid the window's body is. Under 1 it turns see-through, "
            "the way a terminal set to transparency does: whatever the capture "
            "sits on shows through it, while its text, frame and title bar keep "
            "their own paint.",
        ),
        option(
            "--watermark",
            default=DEFAULT_WATERMARK,
            show_default=True,
            help="Credit line drawn in the image's bottom-right corner, in the "
            "margin around the window. Pass an empty string to draw none, or "
            "your own text to credit your project instead.",
        ),
        option(
            "--watermark-color",
            metavar="COLOR",
            default=None,
            help="Color that credit line is drawn in, as CSS names it, alpha "
            "included. Defaults to a neutral gray: the line sits in the "
            "transparent margin, so it answers to the page embedding the image "
            "rather than to the chrome.",
        ),
        option(
            "--head",
            type=IntRange(min=1),
            default=None,
            help="Keep only the first N lines.",
        ),
        option(
            "--tail",
            type=IntRange(min=1),
            default=None,
            help="Keep only the last N lines.",
        ),
        option(
            "--truncation",
            metavar="[auto|TEXT]",
            default=DEFAULT_TRUNCATION,
            show_default=True,
            help=f"Line standing in for what --head or --tail cut away, or "
            f"{AUTO_TRUNCATION} to rule one across the width the kept lines "
            f"span.",
        ),
        option(
            "--line-numbers",
            is_flag=True,
            help="Number the drawn lines in a gutter, the way Pygments does "
            "inline. Line 1 is the first line the picture shows.",
        ),
        option(
            "--emphasize-lines",
            "emphasize",
            metavar="LINES",
            default=None,
            callback=_parse_emphasis,
            help="Draw a band behind the lines named, as 2,4-5. Counted from 1 "
            "as the picture draws them. Ranges are closed: state both ends.",
        ),
        option(
            "--title",
            default="",
            help="Caption drawn in an SVG's window chrome, or an HTML "
            "document's title.",
        ),
        option(
            "--fragment",
            is_flag=True,
            help="For HTML, emit the bare block instead of a standalone "
            "document, to paste into a page that has its own.",
        ),
    )

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        for add_option in reversed(shared):
            func = add_option(func)
        return func

    return decorate


def _parse_hold(
    ctx: click.Context,
    param: click.Parameter,
    value: str | None,
) -> THold | None:
    """Read `--hold` into seconds or the `auto` sentinel, keeping unset as-is."""
    if value is None:
        return None
    if value.strip().lower() == AUTO_HOLD:
        return AUTO_HOLD
    try:
        hold = float(value)
    except ValueError:
        raise click.UsageError(
            f"{value!r} is not a hold, which is seconds or 'auto'."
        ) from None
    if hold < 0:
        raise click.UsageError(f"{value} is not a pause, which is never negative.")
    return hold


#: Sample invocations closing the `screenshot` help screen.
SCREENSHOT_EPILOG = """\b
Examples:

\b
  Draw a help screen as a picture a README can show:
    $ click-extra screenshot --output my-cli.svg -- my-cli --help

\b
  Draw it as selectable text, for a page you own:
    $ click-extra screenshot --output my-cli.html -- my-cli --help

\b
  Capture a CLI that is not built on Click Extra, colored all the same:
    $ click-extra screenshot --output flask.svg --wrap -- flask run --help

\b
  Record the frames a spinner draws, as an animation:
    $ click-extra screenshot --output ripen.svg --record --columns 80 -- ripen
"""


@command(name="screenshot", epilog=SCREENSHOT_EPILOG)
@argument("command_line", nargs=-1, required=True, type=click.UNPROCESSED)
@capture_options(
    columns_help="Terminal width, in characters, the command wraps its output "
    "to and the image is laid out at. Pass auto to pin neither: the command "
    "finds its own width, and the image is laid out at the longest line it "
    "printed, so nothing folds inside the picture.",
)
@option(
    "--prompt",
    default=None,
    help="Command line to display above the output, when it differs from the "
    "one that is run. Pass an empty string to draw no prompt at all. Defaults "
    "to the command line itself.",
)
@option(
    "--merge-stderr",
    is_flag=True,
    help="Fold the command's stderr into the capture, for a CLI printing its "
    "help there. Off by default, which is what keeps a wrapper's build chatter "
    "out of the image.",
)
@option(
    "--wrap",
    is_flag=True,
    help="Route COMMAND_LINE through the wrap subcommand, so a Click CLI that "
    "is not built on Click Extra is captured with its colors. Only works on a "
    "target wrap can resolve.",
)
@option(
    "--timeout",
    type=FloatRange(min=0, min_open=True),
    metavar="SECONDS",
    default=None,
    help="Seconds before the command is killed. Waits forever by default. "
    "With --record, this is also where the recording stops.",
)
@option(
    "--record",
    is_flag=True,
    help="Run the command under a pseudo-terminal and write an animated SVG "
    "of the screens it draws, spinners and progress bars included. Needs an "
    ".svg --output and a numeric --columns. Unix only.",
)
@option(
    "--rows",
    type=IntRange(min=1),
    default=None,
    help=f"With --record, the height of the terminal the command runs in, in "
    f"characters. Defaults to {DEFAULT_ROWS}.",
)
@option(
    "--hold",
    default=None,
    # The callback reads seconds or the `auto` keyword, and Click infers TEXT
    # for a type it was never given. Naming both keeps the accepted values on
    # the help screen, the way a `click.Choice` puts them there.
    metavar="[auto|FLOAT]",
    callback=_parse_hold,
    help=f"With --record, extra seconds the last frame stays up before the "
    f"animation starts over, or {AUTO_HOLD} to scale them to that frame's line "
    f"count. Defaults to {DEFAULT_RECORDING_HOLD}.",
)
@option(
    "--blank",
    type=FloatRange(min=0),
    metavar="SECONDS",
    default=None,
    help=f"With --record, seconds of empty screen closing the cycle. Defaults "
    f"to {DEFAULT_RECORDING_BLANK}.",
)
@option(
    "--cursor",
    type=click.Choice(
        (AUTO_CURSOR, *(shape.value for shape in CursorShape)),
        case_sensitive=False,
    ),
    is_flag=False,
    flag_value=AUTO_CURSOR,
    default=None,
    help="Draw a terminal cursor where the command left it. Bare, it takes "
    "the shape the --preset terminal draws; name one to override that. "
    "Omitted, no cursor is drawn.",
)
@option(
    "--blink",
    type=FloatRange(min=0),
    metavar="SECONDS",
    default=None,
    help=f"With --cursor, seconds one blink takes. Pass 0 to draw a steady "
    f"cursor. Defaults to {Cursor().blink}.",
)
@option(
    "--closing-prompt/--no-closing-prompt",
    default=False,
    help="Draw the shell's prompt on the row under the output, where it comes "
    "back once the command exits. Costs no height alongside --cursor, which "
    "already leaves that row for the cursor to wait on.",
)
@option(
    "--typing",
    type=FloatRange(min=0, min_open=True),
    metavar="SECONDS",
    default=None,
    help="With --record, open the animation by typing the command line out, "
    "this many seconds per character. Omitted, the prompt stands there from "
    "the first frame.",
)
@option(
    "--submit",
    type=FloatRange(min=0, min_open=True),
    metavar="SECONDS",
    default=None,
    help=f"With --typing, seconds the finished command line waits before its "
    f"output starts. Defaults to {DEFAULT_SUBMIT}.",
)
@option(
    "--speed",
    type=FloatRange(min=0, min_open=True),
    default=None,
    help="With --record, how much faster to play than recorded: 2 halves "
    "every frame's time. Defaults to 1.0.",
)
def screenshot_cmd(
    command_line: tuple[str, ...],
    output: Path,
    columns: TColumns,
    background: CaptureBackground,
    preset: str | None,
    prompt: str | None,
    head: int | None,
    tail: int | None,
    truncation: str,
    merge_stderr: bool,
    line_numbers: bool,
    emphasize: tuple[int, ...],
    title: str,
    fragment: bool,
    wrap: bool,
    timeout: float | None,
    record: bool,
    rows: int | None,
    hold: THold | None,
    blank: float | None,
    cursor: str | None,
    blink: float | None,
    closing_prompt: bool,
    typing: float | None,
    submit: float | None,
    speed: float | None,
    **chrome_fields: Unpack[ChromeArguments],
) -> None:
    """Capture a command's colored output and write it as an image or HTML.

    Runs COMMAND_LINE with colors forced on and its terminal width pinned, then
    writes the captured output where --output points. Its extension picks the
    format:

    - .svg: a picture of a terminal window, for a surface that strips inline
      HTML. A README on GitHub or PyPI has no other option;

    - .html: selectable, searchable, copy-pasteable text, for a page you own.

    Put -- before the command line so its own options are not mistaken for this
    command's:

      click-extra screenshot --output shot.svg -- my-cli --help

    COMMAND_LINE is anything the shell can run, Click CLI or not. A Click CLI
    not built on Click Extra prints its help uncolored, so --wrap routes it
    through the wrap subcommand first and captures the colored rendering.

    An SVG starts each run of text on its own column, so it renders correctly
    outside a web browser, where a file manager, a git client or a thumbnailer
    would otherwise slide the columns out of place.

    Neither format needs an optional dependency.

    --record runs the command under a pseudo-terminal instead, and writes an
    animated SVG of every screen it drew: the frames a spinner or a progress
    bar asks a terminal for, which a plain capture never sees. The invocation
    is drawn above every frame, and the loop pauses on the final screen for as
    long as its line count asks, see --hold.
    """
    capture_format = resolve_capture_format(output, fragment)
    chrome = Chrome(**chrome_fields)
    terminal = _resolve_preset(preset)

    if record:
        if capture_format is not CaptureFormat.SVG:
            raise click.UsageError(
                "--record draws an animated SVG: point --output at an .svg file."
            )
        if columns == AUTO_COLUMNS:
            raise click.UsageError(
                "--record pins its terminal width up front: give --columns a number."
            )
        if merge_stderr:
            raise click.UsageError(
                "--record already folds the streams: a pseudo-terminal has one."
            )
        if head is not None or tail is not None:
            raise click.UsageError(
                "--head and --tail do not apply to --record, which keeps whole screens."
            )
    else:
        for name, given in (
            ("--rows", rows is not None),
            ("--hold", hold is not None),
            ("--blank", blank is not None),
            ("--speed", speed is not None),
            ("--typing", typing is not None),
            ("--submit", submit is not None),
        ):
            if given:
                raise click.UsageError(f"{name} requires --record.")
    if blink is not None and cursor is None:
        raise click.UsageError("--blink requires --cursor.")
    if submit is not None and typing is None:
        raise click.UsageError("--submit requires --typing.")

    drawn_cursor = None
    if cursor is not None:
        drawn_cursor = Cursor(
            # The bare flag names no shape, which is what leaves the preset to.
            shape=None if cursor == AUTO_CURSOR else CursorShape(cursor),
            blink=Cursor().blink if blink is None else blink,
        )

    if wrap:
        # Reached through the installed console script, never through
        # `python -m click_extra`: the two resolve a target differently, since
        # `-m` puts the working directory on `sys.path` and shifts what
        # `console_scripts` discovery and a bare module name find. Routing
        # through it would silently capture a different CLI than the one the
        # documented composition captures.
        executable = shutil.which("click-extra")
        if executable is None:
            raise ClickException(
                "--wrap needs the click-extra command on PATH. Install the "
                "package, or compose the two by hand: "
                "click-extra screenshot ... -- click-extra wrap -- TARGET."
            )
        # Show the invocation a reader would type to reproduce the capture,
        # which is the wrap call: running the target on its own renders it
        # uncolored.
        if prompt is None:
            prompt = shlex.join(("click-extra", "wrap", "--", *command_line))
        command_line = (executable, "wrap", "--", *command_line)

    if record:
        # A recording pins its width up front, which the guard above enforced:
        # a pseudo-terminal is opened before the command writes anything, so
        # there is no output yet to size the screen against.
        assert columns != AUTO_COLUMNS
        try:
            document, returncode = record_and_render(
                list(command_line),
                columns=columns,
                rows=DEFAULT_ROWS if rows is None else rows,
                background=background,
                prompt=prompt,
                duration=timeout,
                hold=DEFAULT_RECORDING_HOLD if hold is None else hold,
                blank=DEFAULT_RECORDING_BLANK if blank is None else blank,
                speed=1.0 if speed is None else speed,
                typing=0.0 if typing is None else typing,
                submit=DEFAULT_SUBMIT if submit is None else submit,
                cursor=drawn_cursor,
                closing_prompt=closing_prompt,
                line_numbers=line_numbers,
                emphasize=emphasize,
                title=title,
                unique_id=output.stem,
                preset=terminal,
                chrome=chrome,
            )
        except (NotImplementedError, ValueError) as error:
            raise ClickException(str(error)) from error
    else:
        try:
            document, returncode = capture(
                list(command_line),
                format=capture_format,
                columns=columns,
                prompt=prompt,
                head=head,
                tail=tail,
                truncation=truncation,
                merge_stderr=merge_stderr,
                timeout=timeout,
                line_numbers=line_numbers,
                emphasize=emphasize,
                cursor=drawn_cursor,
                closing_prompt=closing_prompt,
                title=title,
                unique_id=output.stem,
                full=not fragment,
                background=background,
                preset=terminal,
                chrome=chrome,
            )
        except ImportError as error:
            raise ClickException(str(error)) from error

    if returncode:
        logger.warning(f"{command_line[0]} exited with code {returncode}.")

    deliver_capture(document, output)


#: Choice values of this command's own options that are also plain English
#: words its description uses: "a progress bar", "a plain capture", "never
#: sees". Excluded from the cross-reference pass, which would otherwise paint
#: them as values wherever the prose says the word. Their own metavars keep
#: their coloring, see `HelpFormatter.highlight_extra_keywords`.
screenshot_cmd.excluded_keywords = HelpKeywords(choices={"bar", "never", "plain"})


#: Sample invocations closing the `snippet` help screen.
SNIPPET_EPILOG = """\b
Examples:

\b
  Draw a source file as a picture a README can show:
    $ click-extra snippet --output basket.svg basket.py

\b
  Draw it as selectable text, under a named theme:
    $ click-extra snippet --output basket.html --theme dracula basket.py

\b
  Number the lines and point at the one that matters:
    $ click-extra snippet --output basket.svg --line-numbers --emphasize-lines 12 basket.py
"""


@command(name="snippet", epilog=SNIPPET_EPILOG)
@argument(
    "source",
    type=file_path(exists=True, readable=True, allow_dash=True),
)
@capture_options(
    default_columns=AUTO_COLUMNS,
    columns_help="Width, in characters, the image is laid out at. Pass auto to "
    "take the longest line the source holds, so nothing folds: a file was never "
    "wrapped to a terminal's width, and code that soft-wrapped in the picture "
    "would lose the indentation a reader is there to read.",
)
@option(
    "--language",
    default=None,
    help="Language the source is highlighted as, as Pygments names it. Guessed "
    "from the file name, then from the content, when left out. See "
    "https://pygments.org/languages/ for the ones it knows.",
)
@option(
    "--syntax-style",
    "syntax_style",
    metavar="STYLE",
    default=None,
    help="Pygments style the source is colored with, which also paints the "
    "window: a style states the background its colors were designed against. "
    "Defaults to monokai on the dark chrome and to Pygments' own default on "
    "the light one.",
)
def snippet_cmd(
    source: Path,
    output: Path,
    columns: TColumns,
    background: CaptureBackground,
    preset: str | None,
    head: int | None,
    tail: int | None,
    truncation: str,
    line_numbers: bool,
    emphasize: tuple[int, ...],
    title: str,
    fragment: bool,
    language: str | None,
    syntax_style: str | None,
    **chrome_fields: Unpack[ChromeArguments],
) -> None:
    """Highlight a source file and write it as an image or HTML.

    Colors SOURCE with Pygments, then draws it in the same window a captured
    command is drawn in. Pass - to read the source from stdin, which needs
    --language: there is no file name left to guess from.

      click-extra snippet --output ripen.svg ripen.py

    The window is painted the background the syntax style was designed against,
    so a snippet looks like that theme does in an editor rather than like the
    same theme dropped on a foreign surface.

    Both formats are the screenshot command's:

    - .svg: a picture, for a surface that strips inline HTML;

    - .html: selectable, searchable, copy-pasteable text.

    Highlighting needs the pygments extra.
    """
    try:
        from .snippet import render_snippet
    except ImportError as error:
        raise ClickException(
            missing_extra_message("pygments", subject="Drawing a code snippet"),
        ) from error

    capture_format = resolve_capture_format(output, fragment)

    reading_stdin = str(source) == "-"
    if reading_stdin:
        code = sys.stdin.read()
    else:
        code = source.read_text(encoding="utf-8")

    try:
        document = render_snippet(
            code,
            format=capture_format,
            language=language,
            # Left unstated for stdin, which carries no name to read a language
            # off: a guess from the content is all that is left, and naming the
            # dash would have the lexer lookup fail on an extension of "-".
            filename=None if reading_stdin else source.name,
            style=syntax_style,
            columns=columns,
            head=head,
            tail=tail,
            truncation=truncation,
            line_numbers=line_numbers,
            emphasize=emphasize,
            title=title,
            unique_id=output.stem,
            full=not fragment,
            background=background,
            preset=_resolve_preset(preset),
            chrome=Chrome(**chrome_fields),
        )
    except ValueError as error:
        raise ClickException(str(error)) from error

    deliver_capture(document, output)
