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
import sys
import time
from functools import partial
from pathlib import Path

import click
import cloup
from click import (
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
from .cli_capture import screenshot_cmd, snippet_cmd
from .cli_prebake import prebake
from .cli_wrapper import WrapperGroup, wrap as wrap_cmd
from .color import is_a_tty
from .commands import ColorizedCommand, default_params
from .config import ClickExtraConfig, TestSuiteConfig, get_tool_config
from .context import pass_context
from .decorators import argument, command, group, jobs_option, option
from .envvar import merge_envvar_ids
from .execution import run_jobs
from .highlight import HelpKeywords
from .layout import center_in_rule
from .logo import BRAND_SCREEN
from .myst_converter import convert_directory, detect_source_package
from .parameters import make_resilient_context
from .spinner import (
    _DEFAULT_SHOWCASE,
    OperationTrail,
    _animate_spinners,
    _spinner_preview,
    _tour_duration,
)
from .spinner_presets import SPINNERS
from .styling import _nearest_256
from .table import corner_header
from .test_suite import (
    DEFAULT_TEST_SUITE,
    CLITestCase,
    cases_from_data,
    load_test_suite,
    parse_test_suite,
    run_test_suite,
)
from .theme import AUTO_THEME, ThemeChoice, get_theme_registry, resolve_auto_theme

logger = logging.getLogger(__name__)


_demo_section = cloup.Section(
    "Demo",
    is_sorted=True,
)
"""Section grouping terminal capability demo subcommands."""


#: Sample invocations closing the root help screen. Each `\b` escape is Click's
#: marker for a paragraph to keep as written, since the help formatter rewraps
#: an epilog into one block otherwise.
DEMO_EPILOG = """\b
Examples:

\b
  Run any Click CLI through Click Extra's colored help:
    $ click-extra wrap -- my-cli --help

\b
  Draw that help screen as a picture a README can show:
    $ click-extra screenshot --output my-cli.svg -- my-cli --help

\b
  Report the parameters a CLI accepts, and where each value comes from:
    $ click-extra wrap --params -- my-cli

\b
  Highlight a source file as a themed picture:
    $ click-extra snippet --output basket.svg basket.py

\b
  See how a help screen reads under each built-in theme:
    $ click-extra themes
"""


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
    epilog=DEMO_EPILOG,
)
def demo():
    """Click Extra CLI."""


demo.add_command(wrap_cmd)


#: Sample invocations closing the `test-suite` help screen.
TEST_SUITE_EPILOG = """\b
Examples:

\b
  Run the built-in default suite against a CLI:
    $ click-extra test-suite --command my-cli

\b
  Run the cases a file declares, one at a time, stopping on the first failure:
    $ click-extra test-suite --command my-cli --suite-file cases.yaml --jobs 1 --exit-on-error

\b
  Run two of them, skipping the cases a platform cannot answer:
    $ click-extra test-suite --command my-cli --select-test 3 --select-test 7 --skip-platform windows
"""


@command(name="test-suite", epilog=TEST_SUITE_EPILOG)
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
    # Roughly 180 IDs, which Click would enumerate on one unwrappable line.
    # The `man`, `markdown` and `json` renders list them.
    metavar="PLATFORM",
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


#: Sample invocations closing the `refresh-directives` help screen.
REFRESH_DIRECTIVES_EPILOG = """\b
Examples:

\b
  Refresh every self-updating block of a documentation tree:
    $ click-extra refresh-directives docs

\b
  Refresh one page:
    $ click-extra refresh-directives docs/recipes.md

\b
  Report the stale ones without writing, for a continuous-integration job:
    $ click-extra refresh-directives --check docs
"""


@command(name="refresh-directives", epilog=REFRESH_DIRECTIVES_EPILOG)
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


#: Sample invocations closing the `convert-to-myst` help screen.
CONVERT_TO_MYST_EPILOG = """\b
Examples:

\b
  Convert the docstrings of the package in the current directory:
    $ click-extra convert-to-myst

\b
  Convert the docstrings under another one:
    $ click-extra convert-to-myst src/basket
"""


@command(name="convert-to-myst", epilog=CONVERT_TO_MYST_EPILOG)
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


demo.add_command(screenshot_cmd)


#: Choice values of the default options every command inherits that are also
#: plain English words these descriptions use: "never refreshed", "MyST
#: markdown", "a plain line". See `HelpFormatter.highlight_extra_keywords`.
refresh_directives_cmd.excluded_keywords = HelpKeywords(choices={"never"})
convert_to_myst_cmd.excluded_keywords = HelpKeywords(choices={"markdown"})


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
    headers = [corner_header("Foreground", "Background"), *styled_headers]
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
    headers = [corner_header("Color", "Style"), *styled_headers]
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
    """Render 24-bit RGB gradients beside their 256-color quantized equivalents."""
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
    --eta turn that on too, counting up from zero or down as an estimate. Under
    --no-progress, or off an interactive terminal, no spinner or bar draws, and
    each outcome and the summary print as plain lines.
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
        # --no-progress drops the redrawing indicator, never the outcome lines.
        live="auto" if progress_on else "never",
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
# Click lists a positional argument only when it carries a help string. Cloup 3.x's
# own `Argument` forces a row for a help-less one, and cloup 4.0.0 dropped that
# shim: without this `help=`, cloup 3.x draws a `Positional arguments:` section
# here and cloup 4.0.0 draws none, so the committed capture can only match one of
# them.
@argument("plot", help="Garden bed to sow the crop into.")
def _theme_gallery_sample(**_kwargs: object) -> None:
    """Sow a crop into a garden PLOT and water it in."""


@demo.command(name="themes", section=_demo_section)
@argument(
    "theme_ids",
    type=ThemeChoice(),
    nargs=-1,
    # Spell the choices as a metavar: the list is long enough that Click breaks
    # it mid-word in the usage line, and `--theme` already advertises the names.
    metavar="[auto|THEME]...",
    help="Palettes to render, in the order given. Defaults to all of them.",
)
@pass_context
def demo_themes(ctx: click.Context, theme_ids: tuple[str, ...]) -> None:
    """Render a sample help screen under each theme, one after another.

    Each palette is applied in turn to the same throwaway CLI so the themes can
    be eyeballed back to back. A terminal keeps a single background, so
    light-background themes (light, manpage) look washed out on a dark terminal,
    and dark themes look washed out on a light one.

    Without an argument the whole registry is rendered, alphabetically: the
    built-in palettes, plus any a configuration file defines. Name palettes to
    render only those, in the order given. The auto value stands for the palette
    the terminal background resolves to, as it does on --theme.
    """
    registry = get_theme_registry(ctx)
    if theme_ids:
        # "auto" names no palette, so map it onto the one the terminal
        # background resolves to: the gallery labels palettes, not directives.
        auto_theme = resolve_auto_theme(ctx) if AUTO_THEME in theme_ids else None
        auto_name = next(
            (name for name, theme in registry.items() if theme is auto_theme),
            None,
        )
        selection = [
            auto_name if theme_id == AUTO_THEME else theme_id for theme_id in theme_ids
        ]
        # A name is None once ThemeChoice found nothing to resolve against,
        # which is an empty registry: themes.toml was dropped at packaging time.
        gallery = [(name, registry[name]) for name in selection if name is not None]
    else:
        gallery = sorted(registry.items())

    for name, theme in gallery:
        # Point get_current_theme() at this palette by writing the same
        # context.THEME meta ThemeOption sets from --theme; the HelpFormatter
        # reads it back when it renders the sample below. Scoped to this
        # context, so no process-global theme state leaks between invocations.
        context.set(ctx, context.THEME, theme)
        sample_ctx = make_resilient_context(_theme_gallery_sample, "garden")
        sample_ctx.color = ctx.color
        # Center the theme name in a rule as wide as the column count the sample
        # help below wraps to, so the gallery keeps a single right edge.
        echo(
            center_in_rule(
                f"Theme: {theme.heading(name)}",
                sample_ctx.make_formatter().width,
            ),
            color=ctx.color,
        )
        echo()
        echo(_theme_gallery_sample.get_help(sample_ctx), color=ctx.color)
        echo()


demo.add_command(prebake)
