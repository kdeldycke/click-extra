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
"""Click Extra CLI with pre-baking utilities."""

from __future__ import annotations

import colorsys
import logging
import os
import random
import shlex
import shutil
import sys
import time
from functools import partial
from pathlib import Path

import click
import cloup
from click import (
    BadParameter,
    Choice,
    ClickException,
    FloatRange,
    IntRange,
    echo,
    style,
)
from cloup import Color, dir_path, file_path
from extra_platforms import ALL_IDS

from . import context
from ._utils import missing_extra_message
from .cli_wrapper import WrapperGroup, wrap as wrap_cmd
from .color import invocation_color, is_a_tty
from .commands import ColorizedCommand, default_params
from .config import ClickExtraConfig, TestSuiteConfig, get_tool_config
from .context import pass_context
from .decorators import argument, command, group, jobs_option, option
from .envvar import merge_envvar_ids
from .execution import run_jobs
from .logo import BRAND_SCREEN
from .myst_converter import convert_directory, detect_source_package
from .parameters import make_resilient_context
from .prebake import (
    _find_dunder_str,
    discover_package_init_files,
    prebake_dunder,
    prebake_version,
)
from .screenshot import (
    AUTO_COLUMNS,
    DEFAULT_BORDER_WIDTH,
    DEFAULT_COLUMNS,
    DEFAULT_MARGIN,
    DEFAULT_PADDING,
    DEFAULT_RADIUS,
    DEFAULT_TRUNCATION,
    DEFAULT_WATERMARK,
    MIN_COLUMNS,
    NO_PAINT,
    OPAQUE,
    STDOUT_PATH,
    CaptureBackground,
    CaptureFormat,
    capture,
    format_from_path,
)
from .screenshot_presets import PRESETS
from .spinner import (
    _DEFAULT_SHOWCASE,
    OperationTrail,
    _animate_spinners,
    _spinner_preview,
    _tour_duration,
)
from .spinner_presets import SPINNERS
from .styling import _nearest_256
from .test_suite import (
    DEFAULT_TEST_SUITE,
    CLITestCase,
    cases_from_data,
    load_test_suite,
    parse_test_suite,
    run_test_suite,
)
from .theme import BUILTIN_THEMES
from .types import EnumChoice
from .version import (
    BUILD_RESOLVERS,
    GIT_FIELDS,
    GIT_RESOLVERS,
    run_git,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from .screenshot import TColumns

logger = logging.getLogger(__name__)


def _resolve_paths(module: Path | None) -> list[Path]:
    """Resolve target `__init__.py` paths.

    Precedence: an explicit `--module`, then the `[tool.click-extra.prebake]`
    `module` config value, then `[project.scripts]` auto-discovery.
    """
    if module:
        return [module]
    config = get_tool_config()
    if config and config.prebake.module:
        return [Path(config.prebake.module)]
    paths = discover_package_init_files()
    if not paths:
        raise ClickException(
            "No __init__.py found. Pass --module explicitly, set "
            "[tool.click-extra.prebake] module, or add [project.scripts] to "
            "pyproject.toml."
        )
    return paths


def _to_dunder(name: str) -> str:
    """Ensure *name* has `__` prefix and suffix."""
    if not name.startswith("__"):
        name = f"__{name}"
    if not name.endswith("__"):
        name = f"{name}__"
    return name


_module_option = option(
    "--module",
    type=Path,
    default=None,
    help="Path to __init__.py to modify. "
    "Auto-discovered from [project.scripts] if not provided.",
)


_demo_section = cloup.Section(
    "Demo",
    is_sorted=True,
)
"""Section grouping terminal capability demo subcommands."""


@group(
    name="click-extra",
    cls=WrapperGroup,
    # Draws --version as the brand-mark screen, degrading to the plain rendering
    # wherever it cannot be shown. Bound uncalled so each application gets its own
    # option instances, as default_params documents. See click_extra.logo.
    params=partial(default_params, screen=BRAND_SCREEN),
    version_fields={"prog_name": "Click Extra"},
    config_schema=ClickExtraConfig,
    schema_strict=False,
)
def demo():
    """Click Extra CLI."""


demo.add_command(wrap_cmd)


@command(name="test-suite")
@option(
    "--command",
    "--binary",
    required=True,
    metavar="COMMAND",
    help="Path to the binary file to test, or a command line to be executed.",
)
@option(
    "-F",
    "--suite-file",
    type=file_path(exists=True, readable=True, resolve_path=True),
    multiple=True,
    metavar="FILE_PATH",
    help="Path to a test suite file; its format is taken from the extension "
    "(YAML, TOML, JSON, JSON5, JSONC, Hjson). Repeat to run multiple suites in "
    "sequence. Without any suite source, a built-in default suite runs.",
)
@option(
    "-E",
    "--suite-envvar",
    multiple=True,
    metavar="ENVVAR_NAME",
    help="Name of an environment variable holding a test suite in YAML. Repeat "
    "to collect multiple suites.",
)
@option(
    "-t",
    "--select-test",
    type=IntRange(min=1),
    multiple=True,
    metavar="INTEGER",
    help="Only run the cases with these 1-based numbers. Repeat to select "
    "several; omit to run them all.",
)
@option(
    "-s",
    "--skip-platform",
    type=Choice(sorted(ALL_IDS), case_sensitive=False),
    multiple=True,
    help="Skip cases on these platforms. Repeat to skip several.",
)
@option(
    "-x",
    "--exit-on-error",
    is_flag=True,
    default=False,
    help="Exit instantly on the first failed case (sequential runs only).",
)
@jobs_option
@option(
    "-T",
    "--timeout",
    type=FloatRange(min=0, clamp=True),
    metavar="SECONDS",
    help="Default timeout for each CLI call, unless the case sets its own.",
)
@option(
    "-W",
    "--work-directory",
    type=dir_path(exists=True, readable=True, resolve_path=True),
    metavar="DIR_PATH",
    help="Directory to run each case's command in. Defaults to the current one. "
    "Moves the command under test, not the runner: suite files are read before "
    "any case starts.",
)
@option(
    "--show-trace-on-error/--hide-trace-on-error",
    default=True,
    help="Show the execution trace of failed cases.",
)
@option(
    "--stats/--no-stats",
    is_flag=True,
    default=True,
    help="Print the worker summary and the result tally.",
)
@pass_context
def test_suite_cmd(
    ctx: context.Context,
    command: str,
    suite_file: tuple[Path, ...],
    suite_envvar: tuple[str, ...],
    select_test: tuple[int, ...],
    skip_platform: tuple[str, ...],
    exit_on_error: bool,
    timeout: float | None,
    work_directory: Path | None,
    show_trace_on_error: bool,
    stats: bool,
) -> None:
    """Run declarative CLI test cases against a command or binary.

    Resolves the suite by precedence: --suite-file or --suite-envvar, then the
    [tool.click-extra.test-suite] config (cases, then file), then a built-in
    default. Each case invokes the target with its parameters and checks the
    exit code and output.

    Cases run in parallel by default (see --jobs): each is an independent
    process invocation, so they overlap well. Pass --jobs max to use every
    logical core, or --jobs 1 for sequential execution, which lets
    --exit-on-error stop on the first failure.

    On an interactive terminal a spinner reports how many cases have finished.
    It stays silent in pipes and CI logs, and --no-progress or --accessible
    turns it off.
    """
    # click-extra's --jobs option stores its resolved worker count on the
    # context; read it and hand it to the runner.
    worker_count = context.get(ctx, context.JOBS, 1)

    # The [tool.click-extra.test-suite] config, or its defaults when the section
    # (or any config file) is absent.
    config = get_tool_config(ctx)
    test_suite_config = config.test_suite if config else TestSuiteConfig()

    # Collect cases by precedence: CLI sources (--suite-file, --suite-envvar), then
    # the configured native cases, then the suite file, then a built-in default.
    cases: list[CLITestCase] = []
    for suite in suite_file:
        cases.extend(load_test_suite(suite))
    for envvar_id in merge_envvar_ids(suite_envvar):
        cases.extend(parse_test_suite(os.getenv(envvar_id)))
    if not cases and test_suite_config.cases:
        cases.extend(cases_from_data(test_suite_config.cases))
    if not cases and test_suite_config.file:
        suite_path = Path(test_suite_config.file)
        if suite_path.exists():
            cases.extend(load_test_suite(suite_path))
    if not cases:
        cases = DEFAULT_TEST_SUITE

    # Fall back to the configured timeout when --timeout is not given.
    if timeout is None and test_suite_config.timeout is not None:
        timeout = float(test_suite_config.timeout)

    counter = run_test_suite(
        command,
        cases,
        jobs=worker_count,
        select_test=select_test,
        skip_platform=skip_platform,
        timeout=timeout,
        work_directory=work_directory,
        exit_on_error=exit_on_error,
        show_trace_on_error=show_trace_on_error,
        stats=stats,
        show_progress=context.get(ctx, context.PROGRESS, True),
    )
    if counter["failed"]:
        ctx.exit(1)


demo.add_command(test_suite_cmd)


@command(name="refresh-directives")
@argument(
    "paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
@option(
    "--check",
    is_flag=True,
    default=False,
    help="Do not write; exit with a non-zero status if any block is stale.",
)
@pass_context
def refresh_directives_cmd(
    ctx: context.Context,
    paths: tuple[Path, ...],
    check: bool,
) -> None:
    """Refresh the self-updating blocks embedded in Markdown files.

    Walks each PATH (a Markdown file, or a directory scanned recursively for
    Markdown sources) and rewrites every supported self-updating block in
    place:

    - matrix blocks (directive fences and marker regions alike), regenerated
      from the project git history;

    - python:render blocks carrying the :mirror: flag, whose Python code is
      executed to regenerate the mirrored region below the fence (inserted on
      first refresh);

    - click:run blocks carrying both :screenshot: and :mirror:, whose region
      below the fence links to the capture the block writes at build time.

    Examples nested inside longer code fences are never refreshed or executed.

    Pass --check to report stale blocks without writing; the command then exits
    with a non-zero status, so a continuous-integration job can fail on
    out-of-date documentation.

    Refreshing reads the project git history and needs the sphinx extra:
    install it with click-extra[sphinx]. Beware: mirror blocks are arbitrary
    Python executed with the privileges of this process, so only refresh
    documentation you trust, exactly as you would only build trusted docs.
    """
    # Imported lazily so the sphinx extra stays optional: this is the only CLI
    # command that needs it. Importing it eagerly would break the rest of the
    # CLI when sphinx is absent, and slow every invocation with a heavy import.
    try:
        from .sphinx.click import update_screenshot_blocks
        from .sphinx.matrix import update_matrix_blocks
        from .sphinx.python import update_mirror_blocks
    except ImportError as error:
        raise ClickException(
            missing_extra_message("sphinx", subject="Refreshing directives"),
        ) from error

    # A matrix block carrying an invalid option value (like a misspelled
    # column-order) raises ValueError: surface it as a clean CLI error.
    try:
        changed = set(update_matrix_blocks(paths, check=check))
    except ValueError as error:
        raise ClickException(str(error)) from error
    changed.update(update_mirror_blocks(paths, check=check))
    changed.update(update_screenshot_blocks(paths, check=check))
    for path in sorted(changed):
        echo(f"{'would refresh' if check else 'refreshed'}: {path}")
    if check and changed:
        ctx.exit(1)


demo.add_command(refresh_directives_cmd)


@command(name="convert-to-myst")
@argument("directory", required=False, default=None)
def convert_to_myst_cmd(directory: str | None) -> None:
    """Convert reST docstrings to MyST markdown in Python source files.

    Transforms reST markup in docstrings and #: comment blocks to MyST. The
    companion click_extra.sphinx.myst_docstrings Sphinx extension converts the
    MyST back to reST at build time, so sphinx.ext.autodoc still works.

    If DIRECTORY is not specified, auto-detects the source package directory
    from the project's script entry points in pyproject.toml.

    Safe to re-run: already-converted MyST syntax does not match the reST
    patterns, so the conversion is idempotent.
    """
    if directory:
        root = Path(directory)
    else:
        try:
            root = detect_source_package()
        except ValueError as error:
            raise ClickException(str(error)) from error

    if not root.is_dir():
        raise ClickException(f"Not a directory: {root}")

    changed = convert_directory(root)
    for filepath in changed:
        echo(f"  Converted: {filepath}")
    echo(f"\n{len(changed)} file(s) converted.")


demo.add_command(convert_to_myst_cmd)


def _parse_columns(
    ctx: click.Context,
    param: click.Parameter,
    value: str,
) -> int | str:
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
            metavar="INTEGER|auto",
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
            default=None,
            help="Color of the frame drawn around the terminal window, as CSS "
            "names it. Pass none to draw no frame. Defaults to the one the "
            "chrome can show.",
        ),
        option(
            "--border-width",
            type=IntRange(min=0),
            default=DEFAULT_BORDER_WIDTH,
            show_default=True,
            help="Thickness of that frame, in pixels.",
        ),
        option(
            "--radius",
            type=IntRange(min=0),
            default=None,
            help="How round the window's corners are, in pixels. Zero squares "
            f"them. Defaults to {DEFAULT_RADIUS}, or to the rounding --preset "
            "terminal draws.",
        ),
        option(
            "--backdrop",
            default=NO_PAINT,
            show_default=True,
            help="Color filling the image behind the window, margin included, "
            "as CSS names it. Left transparent by default, so the page shows "
            "through.",
        ),
        option(
            "--shadow",
            default=None,
            help="Color of the drop shadow lifting the window off the page, as "
            "CSS names it. Pass none to draw no shadow. Defaults to the one the "
            "chrome calls for.",
        ),
        option(
            "--margin",
            type=IntRange(min=0),
            default=DEFAULT_MARGIN,
            show_default=True,
            help="Transparent pixels left around the window, on all four sides. "
            "The room the drop shadow falls into, so a capture drawing one "
            "wants some.",
        ),
        option(
            "--padding",
            type=IntRange(min=0),
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
            default=DEFAULT_TRUNCATION,
            show_default=True,
            help="Line standing in for what --head or --tail cut away.",
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


@command(name="screenshot")
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
    default=None,
    help="Seconds before the command is killed. Waits forever by default.",
)
def screenshot_cmd(
    command_line: tuple[str, ...],
    output: Path,
    columns: TColumns,
    background: CaptureBackground,
    preset: str | None,
    border: str | None,
    border_width: int,
    radius: int | None,
    backdrop: str,
    shadow: str | None,
    margin: int,
    padding: int,
    opacity: float,
    watermark: str,
    watermark_color: str | None,
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
) -> None:
    """Capture a command's colored output and write it as an image or HTML.

    Runs COMMAND_LINE with colors forced on and its terminal width pinned, then
    writes the captured output where --output points. Its extension picks the
    format:

      .svg  a picture of a terminal window, for a surface that strips inline
            HTML. A README on GitHub or PyPI has no other option.

      .html selectable, searchable, copy-pasteable text, for a page you own.

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
    """
    capture_format = resolve_capture_format(output, fragment)

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
            title=title,
            unique_id=output.stem,
            full=not fragment,
            background=background,
            preset=None if preset is None else PRESETS[preset.lower()],
            border=border,
            border_width=border_width,
            radius=radius,
            backdrop=backdrop,
            shadow=shadow,
            margin=margin,
            padding=padding,
            opacity=opacity,
            watermark=watermark,
            watermark_color=watermark_color,
        )
    except ImportError as error:
        raise ClickException(str(error)) from error

    if returncode:
        logger.warning(f"{command_line[0]} exited with code {returncode}.")

    deliver_capture(document, output)


demo.add_command(screenshot_cmd)


@command(name="snippet")
@argument(
    "source",
    type=file_path(exists=True, readable=True, allow_dash=True),
)
@capture_options(
    default_columns=AUTO_COLUMNS,
    columns_help="Width, in characters, the image is laid out at. Defaults to "
    "the longest line the source holds, so nothing folds: a file was never "
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
    border: str | None,
    border_width: int,
    radius: int | None,
    backdrop: str,
    shadow: str | None,
    margin: int,
    padding: int,
    opacity: float,
    watermark: str,
    watermark_color: str | None,
    head: int | None,
    tail: int | None,
    truncation: str,
    line_numbers: bool,
    emphasize: tuple[int, ...],
    title: str,
    fragment: bool,
    language: str | None,
    syntax_style: str | None,
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

      .svg  a picture, for a surface that strips inline HTML.

      .html selectable, searchable, copy-pasteable text.

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
            preset=None if preset is None else PRESETS[preset.lower()],
            border=border,
            border_width=border_width,
            radius=radius,
            backdrop=backdrop,
            shadow=shadow,
            margin=margin,
            padding=padding,
            opacity=opacity,
            watermark=watermark,
            watermark_color=watermark_color,
        )
    except ValueError as error:
        raise ClickException(str(error)) from error

    deliver_capture(document, output)


demo.add_command(snippet_cmd)


_ALL_STYLES = (
    "bold",
    "dim",
    "underline",
    "overline",
    "italic",
    "blink",
    "reverse",
    "strikethrough",
)
"""ANSI text style names supported by `click.style()`."""

_ALL_COLORS = sorted(Color._dict.values())  # type: ignore[attr-defined]
"""All color names from `click_extra.Color`."""


def _render_palette() -> str:
    """Render a compact 256-color palette swatch.

    Each color is shown as a pair of cells (normal + bold) with foreground and background
    set to the same index, producing a solid color block. Layout: 16 system colors on the
    first row, then the 6x6x6 color cube in 6 rows of 36, then the 24-step grayscale
    ramp.
    """
    swatch = "\x1b[38;5;{0};48;5;{0}m\u2588\x1b[1m\u2588\x1b[m"
    lines: list[str] = []

    # Header.
    lines.append("  + " + "".join(f"{i:2}" for i in range(36)))

    # System colors (indices 0-15).
    lines.append("  0 " + "".join(swatch.format(i) for i in range(16)))

    # 6x6x6 color cube (indices 16-231).
    for row in range(6):
        start = row * 36 + 16
        cells = "".join(swatch.format(start + j) for j in range(36))
        lines.append(f"{start:3} {cells}")

    # Grayscale ramp (indices 232-255).
    lines.append("232 " + "".join(swatch.format(i) for i in range(232, 256)))

    return "\n".join(lines)


def _render_8color_table() -> str:
    """Render a compact 8-color foreground/background combination table.

    Shows all 8 standard foreground colors (normal and bold) against all 8 standard
    background colors. Each cell displays a sample string styled with the fg/bg
    combination.
    """
    sample = " gYw "
    reset = "\x1b[m"
    lines: list[str] = []

    # Header row: background color codes.
    lines.append(
        " " * 6
        + " " * len(sample)
        + "".join(f"{bg:^{len(sample)}}" for bg in range(40, 48))
    )

    for fg in range(30, 38):
        for is_bold in (False, True):
            fg_code = f"{'1;' if is_bold else ''}{fg}"
            # First cell: sample with foreground only (default background).
            label = f" {fg_code:>4} "
            first = f"\x1b[{fg_code}m{sample}{reset}"
            # Remaining cells: sample with foreground + each background.
            cells = "".join(
                f"\x1b[{fg_code};{bg}m{sample}{reset}" for bg in range(40, 48)
            )
            lines.append(f"{label}{first}{cells}")

    return "\n".join(lines)


def _render_gradient() -> str:
    """Render 24-bit RGB gradients alongside their 256-color quantized equivalents.

    Each gradient is shown in two rows: the top row uses 24-bit `SGR 38;2;r;g;b`
    escape codes, the bottom row uses the quantized `SGR 38;5;n` index from
    `_nearest_256`. Visible stepping in the quantized row reveals the palette
    resolution limits.
    """
    # Each row is prefixed by a 9-character label gutter ("  24-bit "), so the
    # ramp stops at 71 blocks to keep the whole line inside a conventional
    # 80-column terminal. One block more and every row wraps.
    width = 71
    block = "\u2588"
    reset = "\x1b[m"
    lines: list[str] = []

    def row_pair(label: str, rgb_func):
        """Generate a 24-bit row and its quantized counterpart."""
        row_24 = ""
        row_8 = ""
        for i in range(width):
            r, g, b = rgb_func(i / (width - 1))
            ri, gi, bi = int(r * 255), int(g * 255), int(b * 255)
            row_24 += f"\x1b[38;2;{ri};{gi};{bi}m{block}{reset}"
            idx = _nearest_256(ri, gi, bi)
            row_8 += f"\x1b[38;5;{idx}m{block}{reset}"
        lines.append(f"{label}")
        lines.append(f"  24-bit {row_24}")
        lines.append(f"   8-bit {row_8}")

    # Rainbow: sweep hue at full saturation and value.
    row_pair("Rainbow:", lambda t: colorsys.hsv_to_rgb(t, 1.0, 1.0))

    lines.append("")

    # Grayscale: black to white.
    row_pair("Grayscale:", lambda t: (t, t, t))

    lines.append("")

    # Red channel ramp.
    row_pair("Red:", lambda t: (t, 0.0, 0.0))

    lines.append("")

    # Cyan (green + blue) ramp: stresses the color cube boundary.
    row_pair("Cyan:", lambda t: (0.0, t, t))

    return "\n".join(lines)


@demo.command(name="colors", section=_demo_section)
@pass_context
def demo_colors(ctx: context.Context) -> None:
    """Render every foreground color against every background color."""
    styled_headers = [style(c, bg=c) for c in _ALL_COLORS]
    headers = ["Foreground \u21b4 \\ Background \u2192"] + styled_headers
    table: list[list[str]] = []
    for fg in _ALL_COLORS:
        row = [style(fg, fg=fg)]
        row.extend(style(fg, fg=fg, bg=bg) for bg in _ALL_COLORS)
        table.append(row)
    ctx.print_table(table, headers=headers)


@demo.command(name="styles", section=_demo_section)
@pass_context
def demo_styles(ctx: context.Context) -> None:
    """Render every color with each text style (bold, dim, italic, etc.)."""
    styled_headers = [style(s, **{s: True}) for s in _ALL_STYLES]
    headers = ["Color \u21b4 \\ Style \u2192"] + styled_headers
    table: list[list[str]] = []
    for color_name in _ALL_COLORS:
        row = [style(color_name, fg=color_name)]
        row.extend(
            style(color_name, fg=color_name, **{prop: True}) for prop in _ALL_STYLES
        )
        table.append(row)
    ctx.print_table(table, headers=headers)


@demo.command(name="palette", section=_demo_section)
def demo_palette() -> None:
    """Render a compact 256-color indexed swatch."""
    echo(_render_palette())


@demo.command(name="8color", section=_demo_section)
def demo_8color() -> None:
    """Render all standard 8-color foreground/background combinations."""
    echo(_render_8color_table())


@demo.command(name="gradient", section=_demo_section)
def demo_gradient() -> None:
    """Render 24-bit RGB gradients vs. their 256-color quantized equivalents."""
    echo(_render_gradient())


@demo.command(name="spinner", section=_demo_section)
@option(
    "--all",
    "every",
    is_flag=True,
    help="Show the whole catalog instead of a curated selection.",
)
@option(
    "--random",
    "sample_size",
    type=int,
    metavar="N",
    default=None,
    help="Show N spinners chosen at random.",
)
@option(
    "--select",
    "names",
    metavar="NAME,...",
    default=None,
    help="Show a comma-separated list of spinner names.",
)
@option(
    "--table",
    "show_table",
    is_flag=True,
    help="Print a reference table of the selected spinners.",
)
@pass_context
def demo_spinner(
    ctx: context.Context,
    every: bool,
    sample_size: int | None,
    names: str | None,
    show_table: bool,
) -> None:
    """Animate the spinner widget; --table lists the catalog instead.

    On an interactive terminal it animates a tour of the selected spinners. By
    default a curated handful is shown; use --all for the whole catalog,
    --random N for a random sample, or --select to name specific spinners (these
    three are mutually exclusive). Pass --table to print a reference table
    instead of animating: name, frames, per-frame interval, and the tour's
    per-spinner dwell time.
    """
    if sum((every, sample_size is not None, names is not None)) > 1:
        raise ClickException("--all, --random and --select are mutually exclusive.")

    if every:
        selection = list(SPINNERS)
    elif sample_size is not None:
        if sample_size < 1:
            raise ClickException("--random needs a count of at least 1.")
        selection = random.sample(list(SPINNERS), min(sample_size, len(SPINNERS)))
    elif names is not None:
        selection = [name.strip() for name in names.split(",") if name.strip()]
        unknown = [name for name in selection if name not in SPINNERS]
        if unknown:
            raise ClickException(
                f"Unknown spinner(s): {', '.join(unknown)}. "
                "Run with --all to list every name."
            )
        if not selection:
            raise ClickException("--select needs at least one spinner name.")
    else:
        selection = list(_DEFAULT_SHOWCASE)

    # `--table` prints the reference table straight away, with no animation. The
    # Tour column is the per-spinner dwell time the live tour would spend.
    if show_table:
        rows = []
        for name in selection:
            preset = SPINNERS[name]
            rows.append([
                name,
                _spinner_preview(preset),
                f"{preset.interval}s",
                f"{_tour_duration(preset):.1f}s",
            ])
        ctx.print_table(
            rows,
            headers=["Name", "Frames", "Interval", "Tour"],
            # Right-align Tour so its single-decimal values line up on the dot.
            colalign=("left", "left", "left", "right"),
        )
        return

    # Otherwise animate a live tour on an interactive terminal, honoring
    # --progress / --accessible. A no-op when captured or piped.
    if is_a_tty(sys.stderr) and context.get(ctx, context.PROGRESS, True):
        _animate_spinners(selection)


# A make-believe batch for the trail demo: each entry is one roasting operation.
# Durations are a few seconds each and staggered, so the live spinner, bar and
# streaming outcomes stay watchable (the leeks scorch to leave a ✘ in the trail).
# Tests stub time.sleep, so these never slow the suite.
_TRAIL_BATCH = (
    ("carrots", 2.4, True),
    ("fennel", 3.2, True),
    ("leeks", 2.7, False),
    ("peppers", 3.6, True),
    ("shallots", 2.2, True),
    ("squash", 3.0, True),
)
"""Vegetables roasted by the `trail` demo, as `(name, seconds, roasted_ok)`."""


@demo.command(name="trail", section=_demo_section)
@option(
    "--progress-bar",
    "use_bar",
    is_flag=True,
    help="Drive the batch with a determinate progress bar instead of a spinner.",
)
@option(
    "--eta/--elapsed",
    "eta",
    default=None,
    help="For --progress-bar, show the time remaining (--eta) or elapsed "
    "(--elapsed); either one turns timing on, like --time. A spinner always "
    "shows elapsed time.",
)
@option(
    "--spinner",
    "spinner_name",
    # Validate against the catalog and enable completion, but keep the metavar a
    # plain NAME: the ~90-entry choice list would otherwise bloat --help (and the
    # help render in the docs). The help text points to the spinner command,
    # whose --all lists every name.
    type=Choice(sorted(SPINNERS)),
    metavar="NAME",
    default=None,
    help="Aggregate spinner animation for concurrent runs (see the spinner "
    "command for names). Defaults to the built-in spinner; ignored with "
    "--progress-bar.",
)
@jobs_option
@pass_context
def demo_trail(
    ctx: context.Context,
    use_bar: bool,
    eta: bool | None,
    spinner_name: str | None,
) -> None:
    """Trace a simulated batch of operations behind an operation trail.

    Roasts a handful of make-believe vegetables (each a short pause, the leeks
    scorching) and reports them as they land. The display follows the batch:
    with --jobs 1 each outcome echoes as a plain line; with two or more jobs a
    spinner carries the running tally while outcomes stream above it;
    --progress-bar swaps that spinner for a determinate progress bar. Add --time
    to append each vegetable's roast time and the batch total; --elapsed and
    --eta turn that on too, counting up from zero or down as an estimate. Honors
    --progress / --no-progress and stays silent off an interactive terminal.
    """
    worker_count = context.get(ctx, context.JOBS, 1)
    progress_on = context.get(ctx, context.PROGRESS, True)
    total = len(_TRAIL_BATCH)
    # Choosing a clock mode with --eta / --elapsed turns timing on too, so they
    # work without --time; left unset, timing follows --time (timer=None).
    timer = True if eta is not None else None

    with OperationTrail(
        label="Roasting",
        unit="vegetables",
        total=total,
        jobs=worker_count,
        progress_bar=use_bar,
        # An unset --spinner uses the trail's built-in default; the bar and a
        # spinner are mutually exclusive. Both map to spinner=None.
        spinner=None if use_bar or spinner_name is None else SPINNERS[spinner_name],
        timer=timer,
        clock="eta" if eta else "elapsed",
        enabled=None if progress_on else False,
    ) as trail:

        def roast(item: tuple[str, float, bool]) -> None:
            name, duration, roasted = item
            op = trail.operation()
            time.sleep(duration)
            verb = "roasted" if roasted else "scorched"
            op.mark(roasted, f"{name} {verb}")

        list(run_jobs(roast, _TRAIL_BATCH, jobs=worker_count))
        trail.finish(
            trail.ok_count == total,
            f"Roasted {trail.ok_count}/{total} vegetables",
        )


# A throwaway CLI used only by `demo themes` to showcase each palette on a real
# help screen. Built on ColorizedCommand so it renders through the themed
# HelpFormatter without inheriting the default_params that would bury the accent
# colors under click-extra's own options. Its callback is never invoked (only
# its help is rendered), and its example data is domain-neutral on purpose.
@click.command(cls=ColorizedCommand, name="garden")
@option(
    "--rows",
    type=int,
    default=4,
    show_default=True,
    help="Number of planting rows to dig.",
)
@option(
    "--crop",
    type=Choice(["carrot", "tomato", "basil", "radish"]),
    default="carrot",
    show_default=True,
    show_envvar=True,
    envvar="GARDEN_CROP",
    help="Which crop to sow.",
)
@option(
    "--spacing",
    type=IntRange(5, 40),
    default=15,
    show_default=True,
    help="Centimetres between seeds.",
)
@option("--water/--no-water", default=True, help="Water the bed right after sowing.")
@argument("plot")
def _theme_gallery_sample(**_kwargs: object) -> None:
    """Sow a crop into a garden PLOT and water it in."""


@demo.command(name="themes", section=_demo_section)
@pass_context
def demo_themes(ctx: click.Context) -> None:
    """Render a sample help screen under every built-in theme, one after another.

    Each built-in palette is applied in turn to the same throwaway CLI so the
    themes can be eyeballed back to back. A terminal keeps a single background,
    so light-background themes (light, manpage) look washed out on a dark
    terminal, and dark themes look washed out on a light one.
    """
    for name, theme in BUILTIN_THEMES.items():
        # Point get_current_theme() at this palette by writing the same
        # context.THEME meta ThemeOption sets from --theme; the HelpFormatter
        # reads it back when it renders the sample below. Scoped to this
        # context, so no process-global theme state leaks between invocations.
        context.set(ctx, context.THEME, theme)
        sample_ctx = make_resilient_context(_theme_gallery_sample, "garden")
        sample_ctx.color = ctx.color
        echo(style("─" * 60, fg="bright_black"), color=ctx.color)
        echo("Theme: " + theme.heading(name), color=ctx.color)
        echo()
        echo(_theme_gallery_sample.get_help(sample_ctx), color=ctx.color)
        echo()


@demo.group()
def prebake():
    """Pre-bake build-time metadata into Python source files."""


@prebake.command()
@option(
    "--hash",
    "git_hash",
    default=None,
    help="Git short hash to append. Auto-detected from HEAD if not provided.",
)
@_module_option
def version(git_hash: str | None, module: Path | None) -> None:
    """Inject Git commit hash into `__version__`.

    Appends the Git short hash as a PEP 440 local version identifier
    (for example `1.0.0.dev0` becomes `1.0.0.dev0+abc1234`).

    Only modifies `.dev` versions without an existing `+` suffix.
    Release versions and already pre-baked versions are left untouched.
    """
    if git_hash is None:
        git_hash = run_git(*GIT_FIELDS["git_short_hash"])
        if not git_hash:
            raise ClickException(
                "No --hash provided and Git hash auto-detection failed. "
                "Pass --hash explicitly or run from a Git repository."
            )

    for init_path in _resolve_paths(module):
        baked = prebake_version(init_path, local_version=git_hash)
        if baked:
            echo(f"Pre-baked {init_path}: {baked}")
        else:
            echo(f"No changes to {init_path}")


@prebake.command()
@argument("name")
@argument("value")
@_module_option
def field(name: str, module: Path | None, value: str) -> None:
    """Replace an empty dunder variable with a value.

    NAME is the template field name (like `git_tag_sha`) or the full
    dunder name (like `__git_tag_sha__`). Double underscores are added
    automatically when missing.

    VALUE is the string to inject.

    Only modifies variables that are currently empty. Already-populated
    values are left untouched (idempotent).
    """
    dunder_name = _to_dunder(name)
    for init_path in _resolve_paths(module):
        baked = prebake_dunder(init_path, dunder_name, value)
        if baked:
            echo(f"Pre-baked {init_path}: {dunder_name} = {baked!r}")
        else:
            echo(f"No changes to {init_path}")


@prebake.command(name="all")
@_module_option
def all_fields(module: Path | None) -> None:
    """Pre-bake `__version__`, all git fields and all build fields in one pass.

    Scans each target file for empty `__<field>__` dunder placeholders,
    resolves their values from the current Git state and build host, and
    injects them.

    Also appends the Git short hash to `.dev` versions in
    `__version__` (same as `prebake version`).

    \b
    Supported git fields:
        git_branch, git_long_hash, git_short_hash, git_date, git_tag

    \b
    Supported build fields:
        build_time, build_os, build_target, build_target_arch

    \b
    Additional computed fields (`__git_tag_sha__`, `__git_distance__`,
    `__git_dirty__`) are baked if their dunder placeholder exists and a git
    resolution is available. Fields without a placeholder in the source file
    are skipped silently.
    """
    paths = _resolve_paths(module)
    changed = False

    for init_path in paths:
        source = init_path.read_text(encoding="utf-8")

        # Pre-bake __version__ with git short hash.
        git_hash = run_git(*GIT_FIELDS["git_short_hash"])
        if git_hash:
            baked = prebake_version(init_path, local_version=git_hash)
            if baked:
                echo(f"Pre-baked {init_path}: __version__ = {baked!r}")
                changed = True

        # Pre-bake each git field that has an empty dunder placeholder. The
        # canonical field-to-resolver mapping lives in click_extra.version, so
        # adding a git field there needs no matching edit here. Direct fields,
        # the tag-derived git_tag_sha, and the computed git_distance/git_dirty
        # all resolve uniformly through their GIT_RESOLVERS callable.
        for field_name, resolver in GIT_RESOLVERS.items():
            dunder_name = f"__{field_name}__"
            node = _find_dunder_str(source, dunder_name)
            if node is None:
                continue
            if node.value:
                echo(f"Skipped {init_path}: {dunder_name} already set")
                continue
            value = resolver(None)
            if not value:
                echo(f"Skipped {init_path}: {dunder_name} (no git value)")
                continue
            baked = prebake_dunder(init_path, dunder_name, value)
            if baked:
                echo(f"Pre-baked {init_path}: {dunder_name} = {baked!r}")
                changed = True
                # Re-read source after each write so AST offsets stay valid.
                source = init_path.read_text(encoding="utf-8")

        # Pre-bake each build field the same way. Their resolvers describe the
        # host running this command, so they take no working directory and
        # always answer.
        for field_name, build_resolver in BUILD_RESOLVERS.items():
            dunder_name = f"__{field_name}__"
            node = _find_dunder_str(source, dunder_name)
            if node is None:
                continue
            if node.value:
                echo(f"Skipped {init_path}: {dunder_name} already set")
                continue
            baked = prebake_dunder(init_path, dunder_name, build_resolver())
            if baked:
                echo(f"Pre-baked {init_path}: {dunder_name} = {baked!r}")
                changed = True
                # Re-read source after each write so AST offsets stay valid.
                source = init_path.read_text(encoding="utf-8")

    if not changed:
        echo("No changes made.")
