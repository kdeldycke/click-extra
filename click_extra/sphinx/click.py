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
"""Sphinx rendering of CLI based on Click Extra.

```{seealso}
These directives are based on [Pallets' Sphinx Themes](https://github.com/pallets/pallets-sphinx-themes/blob/main/src/pallets_sphinx_themes/themes/click/domain.py),
[released under a BSD-3-Clause license](https://github.com/pallets/pallets-sphinx-themes/blob/main/LICENSE.txt).

Compared to the latter, it:

- Add support for MyST syntax.
- Adds rendering of ANSI codes in CLI results.
- Has better error handling and reporting which helps you pinpoint the failing
  code in your documentation.
- Removes the `println` function which was used to explicitly print a blank
  line. This is no longer needed as it is now handled natively.
```
"""

from __future__ import annotations

import ast
import contextlib
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import is_dataclass
from functools import cached_property, partial
from pathlib import Path

import click
from click.testing import CliRunner, EchoingStdin
from docutils import nodes
from packaging.version import Version
from sphinx.directives import SphinxDirective, directives
from sphinx.directives.code import CodeBlock
from sphinx.util import logging, parselinenos

from ..blocks import OPTION_LINE_RE, fence_spans, marker_res, update_blocks
from ..color import forced_color
from ..execution import format_cli_prompt
from ..recording import DEFAULT_QUANTUM, Frame, quantize
from ..screenshot import (
    AUTO_COLUMNS,
    DEFAULT_COLUMNS,
    MIN_COLUMNS,
    OPAQUE,
    CaptureBackground,
    animation_metadata,
    number_lines,
    render,
)
from ..screenshot_presets import PRESETS, TerminalPreset
from ..snippet import highlight_code, resolve_style, style_palette
from ..spinner import Spinner
from ..testing import isolated_filesystem
from ..theme import NOCOLOR_THEME
from ._base import (
    StatelessDomain,
    compile_directive,
    directive_source,
    make_cleanup,
    parse_into_section,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any, ClassVar, Literal

    from sphinx.util.typing import OptionSpec

    from ..screenshot import TColumns
    from ..screenshot_presets import TerminalPalette


logger = logging.getLogger(__name__)


RST_INDENT = " " * 3
"""The indentation used for rST code blocks lines."""


PROMPT_SIGIL = "$"
"""Sigil a block draws before the command it ran.

Fixed rather than taken from {data}`~click_extra.execution.PROMPT`, which
answers to the platform the build runs on: a page would otherwise prompt with a
`>` for every reader whose documentation was built on Windows. A capture drawn
as another terminal swaps it for that terminal's own, see
{class}`~click_extra.screenshot_presets.TerminalPreset`.

Passed as the `prompt` argument of
{func}`~click_extra.execution.format_cli_prompt`, which is what builds the line
for both the results code block and the SVG capture drawn from it.
"""


DEFAULT_SCREENSHOT_DIR = "assets"
"""Directory a `click:run` `:screenshot:` capture is written to by default.

Relative to the documentation source root. Overridden by the
`click_extra_screenshot_dir` `conf.py` value.
"""

DEFAULT_RECORDING_HOLD = 2.0
"""Seconds a recorded animation holds its last frame before starting over.

A recording ends somewhere, and the end is usually its point: the trail filled
in, the bar run out, the outcome landed. Looping straight back gives a reader no
time to read any of it. A declared animation cycles in place and ends nowhere,
so it holds for nothing unless a page asks.
"""

DEFAULT_RECORDING_BLANK = 0.6
"""Seconds of empty screen closing a recorded animation's cycle.

Long enough to read as a deliberate beat, short enough not to look broken. It is
what tells a reader the loop has come round rather than the command having done
something strange. A declared animation cycles in place with no end to mark, so
it blanks for nothing unless a page asks.
"""

SCREENSHOT_MARKER_START = "<!-- screenshot -->"
"""Opening marker of a `click:run` `:mirror:` region.

Written on its own line, directly below the fence, and paired with
{data}`SCREENSHOT_MARKER_END`. The region holds the Markdown link to the capture
the block's `:screenshot:` option names, so the image shows wherever the raw
Markdown is read: on GitHub, on PyPI, in an editor's preview.

Same `<!-- name --> / <!-- name-end -->` grammar as the `python:render`
`:mirror:` regions, under a name saying what this one holds. Unlike those, the
region's content is derived from the option alone, never from executing
anything: it goes stale only when the capture is renamed, which is why no
build-time pass regenerates it in memory.
"""

SCREENSHOT_MARKER_END = "<!-- screenshot-end -->"
"""Closing marker of a `:mirror:` region. See {data}`SCREENSHOT_MARKER_START`."""

# Reading-side regexes of the marker pair above, in the shared grammar from
# `blocks.marker_res`.
_SCREENSHOT_OPEN_RE, _SCREENSHOT_CLOSE_RE = marker_res("screenshot")

_INTERPRETER_RE = re.compile(r"(?:^|/)(?:python|pypy)[\d.]*$")
"""Match the first word of a command line that only *runs* a program.

`python -m my-cli` is typed as three words but names `my-cli`, which is how
Click derives its own `prog_name` too. Every other multi-word command line
names a program whose words all belong to it, `click-extra wrap` being the one
these pages document.
"""

_CAPTURE_FENCE_OPEN = re.compile(
    r"^[ \t]*`{3,}\{(?:click:(?:run|source)|python:(?:run|source))\}[ \t]*\S*[ \t]*$"
)
"""Match the opening line of a MyST fence whose `:mirror:` shows a capture.

`:mirror:` writes Markdown back into a Markdown host, so it is scoped to the
MyST fence form: an rST directive has no Markdown region to hold.

`python:render` is deliberately absent, being the one directive whose
`:mirror:` already means something else: it mirrors the *markup* the block
generated, and {func}`~click_extra.sphinx.python.update_mirror_blocks` owns
that region. Two refreshers writing one region would each undo the other on
alternate runs.
"""


MYST_CONTENT_OFFSET_INFLATED_MAX = Version("5.1.0")
"""Last `myst-parser` release that miscomputes a directive's `content_offset`.

Up to and including this version, `myst-parser` over-counts `content_offset`
by one whenever an option block is followed by a body ending in blank
line(s): the parsed body is rebuilt through a string round-trip that drops
one trailing blank line, so the option-block line count comes out one too
high. This shifts the reported source line of every body element down by one.

This fix is not yet upstream: the open rework in
[`#1175`](https://github.com/executablebooks/MyST-Parser/pull/1175) does not
include it, and also makes `content_offset` document-relative. So the release
that eventually lands the fix requires
{attr}`ClickDirective.abs_content_offset` to converge on the rST branch it
already carries, not merely drop this compensation. See `docs/upstream.md`.

```{todo}
Retire the MyST `content_offset` workaround once the pinned `myst-parser`
floor rises past the release carrying the fix:

- delete {func}`_myst_content_offset_inflation` and this constant, and
  collapse {attr}`ClickDirective.abs_content_offset` onto its rST branch
  (`content_offset` verbatim);
- drop the `directive.content` fallback in
  `click_extra.sphinx._base.directive_source()`, which stays off `block_text`
  only because that attribute is body-only in `myst-parser <= 5.1.0`
  ([`#1164`](https://github.com/executablebooks/MyST-Parser/pull/1164) is
  merged but unreleased). A released `block_text` anchors a robust
  line-number computation and retires the workaround from both sides.

The single-trailing-blank-line case documented on
{func}`_myst_content_offset_inflation` stays off by one until then, and no
local fix can reach it: the round-trip consumes that line without a trace.
```
"""


def _myst_content_offset_inflation(directive: SphinxDirective) -> int:
    """Lines to subtract from the MyST error-line computation (`0` or `1`).

    Works around the {data}`MYST_CONTENT_OFFSET_INFLATED_MAX` bug so the
    variable-conflict error points at the true source line. Only engages on an
    affected `myst-parser`, and only when the directive carries both an option
    block and a body ending in a blank line: the two conditions that together
    trigger the inflation.

    ```{caution}
    The round-trip behind the bug consumes the *first* trailing blank line, so
    a body ending in exactly one blank line inflates `content_offset` without
    leaving a trace in `directive.content`. That single-blank case therefore
    stays off by one until the upstream fix is adopted; bodies ending in two or
    more blank lines are corrected.
    ```
    """
    myst = sys.modules.get("myst_parser")
    if myst is None or Version(myst.__version__) > MYST_CONTENT_OFFSET_INFLATED_MAX:
        return 0
    body = list(directive.content)
    if directive.options and body and not body[-1].strip():
        return 1
    return 0


class TerminatedEchoingStdin(EchoingStdin):
    """Like `click.testing.EchoingStdin` but adds a visible
    `^D` in place of the EOT character (`\x04`).

    {meth}`ClickRunner.invoke` adds `\x04` when `terminate_input=True`.
    """

    def _echo(self, rv: bytes) -> bytes:
        eof = rv[-1] == b"\x04"[0]

        if eof:
            rv = rv[:-1]

        if not self._paused:
            self._output.write(rv)

            if eof:
                self._output.write(b"^D\n")

        return rv


@contextlib.contextmanager
def patch_subprocess():
    """Patch subprocess to work better with {meth}`ClickRunner.invoke`.

    `subprocess.call` output is redirected to `click.echo` so it
    shows up in the example output.

    ```{caution}
    The replacement is installed on the `subprocess` module itself
    (not thread-local), so for the duration of the `with` block any
    other code in the same process that calls `subprocess.call` sees
    the patched version. With `parallel_read_safe = True` declared
    on {class}`ClickDomain`, a parallel reader running concurrently
    on a different document gets the patched `subprocess.call` too.
    The redirection is benign (output goes to `click.echo`) but the
    race is real, and the parallel-safe claim is weaker than it
    looks for documents that themselves shell out via
    `subprocess.call`.
    ```
    """
    old_call = subprocess.call

    def dummy_call(*args, **kwargs):
        with tempfile.TemporaryFile("wb+") as f:
            kwargs["stdout"] = f
            kwargs["stderr"] = f
            rv = subprocess.Popen(*args, **kwargs).wait()
            f.seek(0)
            click.echo(f.read().decode("utf-8", "replace").rstrip())
        return rv

    subprocess.call = dummy_call

    try:
        yield
    finally:
        subprocess.call = old_call


def program_from_command_line(command_line: str) -> str:
    """The program name Click is given for a command line a block displays.

    A block documenting a multi-word program has to hand Click all of it: the
    command reads its own name back out of the context, for its usage line and
    for any output quoting the invocation that produced it, like the provenance
    header of a [Carapace spec](carapace.md). Handing over the last word alone
    makes an image contradict the prompt drawn right above it.

    Only an interpreter prefix is dropped, since it names no program: see
    {data}`_INTERPRETER_RE`.
    """
    first, _, rest = command_line.partition(" ")
    if rest and _INTERPRETER_RE.search(first):
        return command_line.rsplit(" ", 1)[-1]
    return command_line


class ClickRunner(CliRunner):
    """A sub-class of {class}`click.testing.CliRunner` for Sphinx directive execution.

    Produces unfiltered ANSI codes so that the `Directive` sub-classes below can
    render colors in the HTML output. Because Click Extra executes the documented
    command here, {meth}`invoke` forces color across both color systems a CLI might use:
    `color=True` covers Click's (`should_strip_ansi`), and
    {func}`~click_extra.color.forced_color` sets `FORCE_COLOR` for Rich's (which
    `rich-click` uses and `color=True` never reaches). The MkDocs plugin shares the
    latter lever but cannot pass `color=True`, since it patches a renderer it never
    executes.

    On Click 8.4+ the runner defaults to `capture="fd"` on Unix (overridable through
    the `click_extra_run_capture` `conf.py` value) so a documented command that
    writes through `sys.stdout.fileno()` is captured and rendered, instead of aborting
    the build with {exc}`io.UnsupportedOperation`. On Windows, where fd-backed streams
    are not supported, the default falls back to `capture="sys"`.
    """

    def __init__(self, capture: Literal["sys", "fd"] | None = None) -> None:
        # capture="fd" backs the captured streams with a real file descriptor so a
        # documented command calling sys.stdout.fileno() renders instead of crashing
        # the build. It is the default (the click_extra_run_capture conf.py value
        # selects it), safe at doc-build time unlike under the pytest stream
        # duplication that got it reverted as a Click default (pallets/click#3391).
        # Windows does not support fd-backed streams (no Unix file descriptors), so
        # fall back to "sys" when the caller has not pinned a mode explicitly.
        default_capture: Literal["sys", "fd"] = (
            "sys" if sys.platform == "win32" else "fd"
        )
        super().__init__(echo_stdin=True, capture=capture or default_capture)
        self.namespace = {"click": click, "__file__": "dummy.py"}

    @contextlib.contextmanager
    def isolation(self, *args, **kwargs):
        """Echo a `^D` marker at the end of the isolated stdin.

        ```{todo}
        Declare {class}`TerminatedEchoingStdin` instead of rewriting the
        `__class__` of the instance Click already built. That needs Click to
        make `EchoingStdin` overridable: an `echo_stdin_class` attribute on
        {class}`click.testing.CliRunner`, say, that `isolation()` instantiates
        rather than hard-coding. Worth proposing upstream.
        ```
        """
        iso = super().isolation(*args, **kwargs)

        with iso as streams:
            try:
                buffer = sys.stdin.buffer
            except AttributeError:
                buffer = sys.stdin

            # sys.stdin is patched by now, so swapping the class of the buffer
            # Click built is safe: it is the only handle on that object.
            buffer.__class__ = TerminatedEchoingStdin
            yield streams

    def invoke(  # type: ignore[override]
        self,
        cli,
        args=None,
        prog_name=None,
        input=None,
        terminate_input=False,
        env=None,
        _output_lines=None,
        _show_prompt=True,
        **extra,
    ) -> click.testing.Result:
        """Like `CliRunner.invoke` but displays what the user
        would enter in the terminal for env vars, command arguments, and
        prompts.

        :param terminate_input: Whether to display `^D` after a list of
            input.
        :param _output_lines: A list used internally to collect lines to
            be displayed.
        :param _show_prompt: Whether to draw the invocation above the output.
            Set from the directive's `:show-prompt:` / `:hide-prompt:` options,
            see {attr}`ClickDirective.show_prompt`.
        """
        output_lines = _output_lines if _output_lines is not None else []

        args = args or []

        if prog_name is None:
            prog_name = cli.name.replace("_", "-")

        if _show_prompt:
            # The same renderer the SVG captures draw their prompt with, so a
            # block and its `:screenshot:` cannot word the invocation
            # differently. `NOCOLOR_THEME` keeps the line plain: the results
            # block is lexed as `ansi-shell-session`, which highlights the
            # prompt itself, and ANSI of our own would fight it.
            output_lines.append(
                format_cli_prompt(
                    # Pre-quoted so an argument holding spaces stays one token,
                    # matching what a reader would have to type. The renderer
                    # joins on spaces and quotes nothing itself.
                    (prog_name, *(shlex.quote(arg) for arg in args)),
                    extra_env={k: shlex.quote(v) for k, v in sorted(env.items())}
                    if env
                    else None,
                    theme=NOCOLOR_THEME,
                    prompt=PROMPT_SIGIL,
                )
            )
        prog_name = program_from_command_line(prog_name)

        if isinstance(input, (tuple, list)):
            input = "\n".join(input) + "\n"

            if terminate_input:
                input += "\x04"

        # `color=True` keeps ANSI in Click's color system: it flips
        # `should_strip_ansi`, which CliRunner otherwise leaves stripping on its
        # non-TTY buffer. But rich-click renders through Rich's Console, a separate
        # system that ignores `should_strip_ansi` and only honors `FORCE_COLOR`, so
        # `forced_color()` sets that too. Together they cover both color systems a
        # documented CLI might use.
        with forced_color():
            result = super().invoke(
                cli=cli,
                args=args,
                input=input,
                env=env,
                prog_name=prog_name,
                color=True,
                **extra,
            )
        output_lines.extend(result.output.splitlines())
        return result

    def execute_source(self, directive: SphinxDirective) -> None:
        """Execute the given code, adding it to the runner's namespace."""
        code = compile_directive(directive)
        with patch_subprocess():
            exec(code, self.namespace)  # noqa: S102

    def run_cli(self, directive: SphinxDirective) -> list[str]:
        """Execute the given `source_code`.

        Returns a simulation of terminal execution, including a mix of input, output,
        prompts and tracebacks.

        The execution context is augmented, so you can refer directly to these
        functions in the provided `source_code`:

        - {meth}`invoke()`: which is the same as {meth}`ClickRunner.invoke`
        - `isolated_filesystem()`: A context manager that changes to a temporary
          directory while executing the block.

        If any local variable in the provided `source_code` conflicts with these
        functions, a {class}`RuntimeError` is raised to help you pinpoint the issue.
        """
        source_code, location = directive_source(directive)

        buffer: list[str] = []

        # Functions available as local variables when executing the code.
        local_vars = {
            "invoke": partial(
                self.invoke,
                _output_lines=buffer,
                # Read off the directive rather than the runner: one runner
                # serves every block of a document, so the flag has to travel
                # per-invocation.
                _show_prompt=directive.show_prompt,
            ),
            # The module-level helper, not the runner's inherited method:
            # Click deprecated its own in 8.5.0 and removes it in 9.0.
            "isolated_filesystem": isolated_filesystem,
        }

        # Check for local variable conflicts.
        tree = ast.parse(source_code, location)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Store)
                and node.id in local_vars
            ):
                # Get the source lines for better error reporting.
                source_lines = source_code.splitlines()
                # Get the line number relative to the source code.
                python_lineno = node.lineno
                python_line = source_lines[python_lineno - 1]
                # Compute the absolute line number in the document.
                doc_lineno = directive.abs_content_offset + python_lineno
                raise RuntimeError(
                    f"Local variable {node.id!r} at "
                    f"{location}:{directive.name}:{doc_lineno} conflicts with "
                    f"the one automatically provided by the {directive.name} "
                    "directive.\n"
                    f"Line: {python_line}"
                )

        code = compile_directive(directive)
        exec(code, self.namespace, local_vars)  # noqa: S102
        return buffer


def _resolve_run_capture(
    configured: Literal["sys", "fd"],
) -> Literal["sys", "fd"]:
    """Degrade the configured stream-capture mode to one the platform supports.

    The `click_extra_run_capture` `conf.py` value is a build-time
    *preference*. `"fd"` backs the captured streams with a real file descriptor
    so a command writing through `sys.stdout.fileno()` renders (see
    {class}`ClickRunner`), but Windows has no Unix file descriptors and Click
    rejects `capture="fd"` there. Degrade `"fd"` to `"sys"` on Windows so
    the documentation build proceeds: such fileno-writing commands simply do not
    render, instead of aborting the whole build.

    A direct `ClickRunner(capture="fd")` call still honors the explicit pin (and
    raises on Windows); only the config-derived preference degrades here.
    """
    if configured == "fd" and sys.platform == "win32":
        return "sys"
    return configured


def _screenshot_columns(argument: str) -> TColumns:
    """Read the `:screenshot-columns:` option into a width, or into `auto`.

    The block's own text is wrapped by Click at its fixed width whatever this
    says: what it decides is the width the *image* is laid out at, which is what
    a line the CLI does not wrap on its own needs to stay on one line.
    """
    if argument.strip().lower() == AUTO_COLUMNS:
        return AUTO_COLUMNS
    width = int(directives.positive_int(argument))
    if width < MIN_COLUMNS:
        raise ValueError(f"{width} is narrower than the {MIN_COLUMNS}-column floor.")
    return width


def _screenshot_opacity(argument: str) -> float:
    """Read the `:screenshot-opacity:` option into how solid the window is."""
    opacity = float(argument)
    if not 0.0 <= opacity <= OPAQUE:
        raise ValueError(f"{argument} is not an opacity, between 0 and {OPAQUE}.")
    return opacity


def _screenshot_hold(argument: str) -> float:
    """Read the `:screenshot-hold:` option into seconds, zero included."""
    hold = float(argument)
    if hold < 0:
        raise ValueError(f"{argument} is not a pause, which is never negative.")
    return hold


def _screenshot_interval(argument: str) -> float:
    """Read the `:screenshot-interval:` option into seconds per frame."""
    interval = float(argument)
    if interval <= 0:
        raise ValueError(f"{argument} is not a frame duration, which is positive.")
    return interval


def _screenshot_preset(argument: str) -> TerminalPreset:
    """Read the `:screenshot-preset:` option into the terminal it names."""
    return PRESETS[directives.choice(argument, tuple(sorted(PRESETS)))]


def _screenshot_background(argument: str) -> CaptureBackground:
    """Read the `:screenshot-background:` option into its enum member.

    Rejecting an unknown chrome here, at the option level, is what turns a typo
    into a build error naming the choices, instead of a capture silently drawn
    on the default.
    """
    choices = tuple(member.value for member in CaptureBackground)
    return CaptureBackground(directives.choice(argument, choices))


class ClickDirective(SphinxDirective):
    """Base class of every `click:*` directive.

    The two directive parsers count `content_offset` from different places, so
    anything naming a document line goes through {attr}`abs_content_offset`
    rather than reading `content_offset` directly.
    """

    has_content = True

    required_arguments = 0
    optional_arguments = 1
    """The optional argument overrides the default Pygments language to use."""

    final_argument_whitespace = False

    option_spec: ClassVar[OptionSpec] = CodeBlock.option_spec | {
        "language": directives.unchanged_required,
        "show-source": directives.flag,
        "hide-source": directives.flag,
        "show-results": directives.flag,
        "hide-results": directives.flag,
        "show-prompt": directives.flag,
        "hide-prompt": directives.flag,
        "emphasize-result-lines": CodeBlock.option_spec["emphasize-lines"],
        "screenshot": directives.unchanged_required,
        "screenshot-animate": directives.unchanged_required,
        "screenshot-backdrop": directives.unchanged_required,
        "screenshot-background": _screenshot_background,
        "screenshot-interval": _screenshot_interval,
        "screenshot-border": directives.unchanged_required,
        "screenshot-blank": _screenshot_hold,
        "screenshot-border-width": directives.nonnegative_int,
        "screenshot-columns": _screenshot_columns,
        "screenshot-emphasize-lines": directives.unchanged_required,
        "screenshot-hold": _screenshot_hold,
        "screenshot-line-numbers": directives.flag,
        "screenshot-margin": directives.nonnegative_int,
        "screenshot-opacity": _screenshot_opacity,
        "screenshot-padding": directives.nonnegative_int,
        "screenshot-preset": _screenshot_preset,
        "screenshot-quantum": _screenshot_interval,
        "screenshot-radius": directives.nonnegative_int,
        "screenshot-record": directives.unchanged_required,
        "screenshot-shadow": directives.unchanged_required,
        "screenshot-speed": _screenshot_interval,
        "screenshot-syntax-style": directives.unchanged_required,
        "screenshot-title": directives.unchanged_required,
        "screenshot-watermark": directives.unchanged_required,
        "screenshot-watermark-color": directives.unchanged_required,
        "mirror": directives.flag,
    }
    """Options supported by this directive.

    Support the [same options](https://github.com/sphinx-doc/sphinx/blob/cc7c6f4/sphinx/directives/code.py#L108-L117)
    as `sphinx.directives.code.CodeBlock`, and some specific to Click
    directives.

    The standard `emphasize-lines` option applies to the source block only. Use
    `emphasize-result-lines` to highlight specific lines in the captured output
    block, with the same syntax (like `:emphasize-result-lines: 1,3-5`).

    Every directive carries the `:screenshot:` family, because every one of them
    shows something worth committing as an image. What lands in that image is
    whatever the block itself draws: a run's captured output, and a source
    block's own code, highlighted by {mod}`click_extra.snippet`.

    `:screenshot:` and `:mirror:` are deliberately independent. `:screenshot:
    <name>` only *writes* `<name>.svg` under the `click_extra_screenshot_dir`,
    leaving the page's code block alone: inside Sphinx that block beats an
    image, being selectable, searchable and theme-aware. `:mirror:` is what puts
    the image on the page, by keeping a Markdown link to it in the source `.md`
    between the same marker pair the `python:render` `:mirror:` flag uses, so
    the capture shows on GitHub and PyPI as well.

    So `:screenshot:` alone maintains an asset some other surface embeds, and
    the two together also show it here. Both are refreshed offline by
    `click-extra refresh-directives`.
    """

    default_language: str
    """Default highlighting language to use to render the code block.

    [All Pygments' languages short names](https://pygments.org/languages/) are
    recognized.
    """

    screenshots_source: bool = False
    """Whether a `:screenshot:` on this directive pictures the block's own code.

    `False` for a directive that runs something: what is worth committing there
    is the output, and the code producing it is on the page already. `True` for
    one that only declares code, which has no output to picture and whose
    subject is the code itself. See {meth}`screenshot_lines`.
    """

    show_source_by_default: bool = True
    """Whether to render the source code of the example in the code block."""
    show_results_by_default: bool = True
    """Whether to render the results of the example in the code block."""
    show_prompt_by_default: bool = True
    """Whether to draw the invocation above the results it produced."""

    runner_method: str
    """The name of the method to call on the {class}`ClickRunner` instance."""

    runner_attr: ClassVar[str] = "click_runner"
    """Name of the attribute holding the runner on the doctree.

    Subclasses (like `PythonDirective`)
    override this so the Click and Python runners don't collide on the same
    document.
    """

    runner_factory: ClassVar[type] = None  # type: ignore[assignment]
    """Class to instantiate for the per-document runner.

    Defaults to {class}`ClickRunner` in {class}`ClickDirective` (set after the
    class definition to break the forward reference).
    """

    @property
    def runner(self):
        """Get or create the per-document runner.

        Creates one runner per document, keyed by {attr}`runner_attr`.
        """
        runner = getattr(self.state.document, self.runner_attr, None)
        if runner is None:
            runner = self.runner_factory(
                capture=_resolve_run_capture(self.env.config.click_extra_run_capture)
            )
            setattr(self.state.document, self.runner_attr, runner)
        return runner

    @cached_property
    def language(self) -> str:
        """Short name of the Pygments lexer used to highlight the code block.

        Returns, in order of precedence, the language specified in the `:language:`
        directive options, the first argument of the directive (if any), or the default
        set in the directive class.
        """
        if "language" in self.options:
            return self.options["language"]  # type: ignore[no-any-return]
        if self.arguments:
            return str(self.arguments[0])
        return self.default_language

    def code_block_options(self, target: str = "source") -> list[str]:
        """Render the options supported by Sphinx' native `code-block` directive.

        `target` selects which block these options will be attached to:
        `"source"` for the directive's input source code, `"results"` for the
        captured output. `emphasize-lines` routes to the source block;
        `emphasize-result-lines` is rewritten as `emphasize-lines` on the
        results block, so authors can highlight different lines in each.
        """
        options = []
        for option_id in CodeBlock.option_spec:
            if option_id == "emphasize-lines":
                if target == "source" and "emphasize-lines" in self.options:
                    options.append(f":emphasize-lines: {self.options[option_id]}")
                elif target == "results" and "emphasize-result-lines" in self.options:
                    options.append(
                        f":emphasize-lines: {self.options['emphasize-result-lines']}"
                    )
                continue
            if option_id in self.options:
                value = self.options[option_id]
                line = f":{option_id}:"
                if value:
                    line += f" {value}"
                options.append(line)
        return options

    @cached_property
    def show_source(self) -> bool:
        """Whether to show the source code of the example in the code block.

        The last occurrence of either `show-source` or `hide-source` options
        wins. If neither is set, the default is taken from `show_source_by_default`.
        """
        show_source = self.show_source_by_default
        for option_id in self.options:
            if option_id == "show-source":
                show_source = True
            elif option_id == "hide-source":
                show_source = False
        return show_source

    @cached_property
    def show_results(self) -> bool:
        """Whether to show the results of running the example in the code block.

        The last occurrence of either `show-results` or `hide-results` options
        wins. If neither is set, the default is taken from `show_results_by_default`.
        """
        show_results = self.show_results_by_default
        for option_id in self.options:
            if option_id == "show-results":
                show_results = True
            elif option_id == "hide-results":
                show_results = False
        return show_results

    @cached_property
    def show_prompt(self) -> bool:
        """Whether to draw the invocation above the output it produced.

        The last occurrence of either `show-prompt` or `hide-prompt` options
        wins. If neither is set, the default is taken from
        `show_prompt_by_default`.

        The prompt is one line rendered by
        {func}`~click_extra.execution.format_cli_prompt`, prepended to the
        captured output. It is therefore part of the results, not a block of its
        own: hiding it drops it from the results code block *and* from the SVG a
        `:screenshot:` writes, which is drawn from the same lines. Reach for it
        when the invocation is noise the surrounding prose already carries, or
        when a capture is wanted as bare output.
        """
        show_prompt = self.show_prompt_by_default
        for option_id in self.options:
            if option_id == "show-prompt":
                show_prompt = True
            elif option_id == "hide-prompt":
                show_prompt = False
        return show_prompt

    @cached_property
    def is_myst_syntax(self) -> bool:
        """Check if the current directive is written with MyST syntax."""
        return bool(self.state.__module__.split(".", 1)[0] == "myst_parser")

    @cached_property
    def abs_content_offset(self) -> int:
        """0-based offset of the directive's first content line in the document.

        Both parsers expose a `content_offset` and they count it from
        different places: docutils from the top of the document, `myst-parser`
        from the directive's own first line. Everything naming a document line
        reads this property instead, so the two conventions are reconciled in
        one place: the variable-conflict error of {meth}`ClickRunner.run_cli`,
        and the source-line labels
        {func}`~click_extra.sphinx._base.parse_into_section` attaches to a
        generated block.

        Named after docutils' `abs_line_offset()`, whose convention it
        follows.
        """
        # Both attributes reach mypy as Any, since the [tool.mypy] overrides
        # skip following `sphinx.*`. Restate the contract docutils declares.
        content_offset: int = self.content_offset
        if not self.is_myst_syntax:
            return content_offset
        lineno: int = self.lineno
        # Correct a myst-parser <= 5.1.0 bug that inflates content_offset by
        # one when an option block precedes a body ending in blank line(s).
        # See the mechanism and the single-trailing-blank caveat in
        # _myst_content_offset_inflation().
        return lineno + content_offset - _myst_content_offset_inflation(self)

    @staticmethod
    def _slug(value: str) -> str:
        """Lower-case + non-alphanumeric → `-`, mirroring docutils' `make_id`."""
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    def _surrounding_section_depth(self) -> int:
        """Return the heading level of the section wrapping this directive.

        Drives the default `heading-offset` of the scaffolding directives
        (`click:tree`, `click:config`) so generated headings nest
        correctly under the surrounding section, regardless of how deep in
        the document the directive is placed. A value of `1` means the
        directive sits inside the document's top-level `h1` section (the
        next legal heading is `h2`); `3` means it sits inside an `h3`
        section (next legal heading is `h4`).

        Read from `state.memo.section_level`, which docutils' `RSTState`
        and MyST's `MockState` both populate. Falls back to `1` if the
        attribute is unavailable (preserves the historical default).
        """
        try:
            level = self.state.memo.section_level
        except AttributeError:
            return 1
        return max(int(level), 1)

    def render_code_block(
        self,
        lines: Iterable[str],
        language: str,
        target: str = "source",
    ) -> list[str]:
        """Render the code block with the source code or results.

        `target` is forwarded to {meth}`code_block_options` so the
        `emphasize-lines` / `emphasize-result-lines` split routes the right
        highlighting to each block.
        """
        block: list[str] = []
        if not lines:
            return block

        # Initiate the code block with with its MyST or rST syntax.
        code_directive = "```{code-block}" if self.is_myst_syntax else ".. code-block::"
        block.append(f"{code_directive} {language}")

        # Re-attach each option to the code block.
        # Indent the line in rST code block.
        block.extend(
            line if self.is_myst_syntax else RST_INDENT + line
            for line in self.code_block_options(target)
        )

        # Both rST and MyST need a blank line before the body of the block else the
        # first line will be interpreted as a directive option or argument.
        block.append("")

        block.extend(
            line if self.is_myst_syntax else RST_INDENT + line for line in lines
        )

        # In MyST, we need to close the code block.
        if self.is_myst_syntax:
            block.append("```")

        return block

    @cached_property
    def screenshot(self) -> str | None:
        """Name of the SVG capture this block renders to, without its extension.

        Set by the `:screenshot:` option. `None` when the block renders its
        results as a code block, which is the default.
        """
        return self.options.get("screenshot")  # type: ignore[no-any-return]

    @cached_property
    def screenshot_background(self) -> CaptureBackground:
        """Chrome the capture is drawn on, set by `:screenshot-background:`.

        Defaults to the dark chrome a terminal and this package's default theme
        both look like. A block rendering a light-background theme says so, or
        its capture washes out: see
        {class}`~click_extra.screenshot.CaptureBackground`.
        """
        return self.options.get("screenshot-background", CaptureBackground.DARK)  # type: ignore[no-any-return]

    @cached_property
    def screenshot_columns(self) -> TColumns:
        """Width the capture is laid out at, set by `:screenshot-columns:`.

        Defaults to the fixed width a terminal capture is taken at. `auto` sizes
        the image to the longest line the block printed, which is what a run
        holding a line Click does not wrap needs to keep on one line: a prompt,
        a wide table, a machine-readable dump.
        """
        return self.options.get("screenshot-columns", DEFAULT_COLUMNS)  # type: ignore[no-any-return]

    def resolve_animation(
        self,
        expression: str,
        option: str,
    ) -> tuple[tuple[str, ...], float | tuple[float, ...]]:
        """Frames the capture animates, set by `:screenshot-animate:`.

        The option is a Python expression, evaluated in the same per-document
        namespace the block's own source runs in, so a `click:source` block
        above can build the subject and this one picture it. It yields either:

        - a {class}`~click_extra.spinner.Spinner`, whose
          {meth}`~click_extra.spinner.Spinner.frame_lines` and `interval` are
          taken as they stand, which is the whole declaration for a spinner;
        - a sequence of {class}`~click_extra.recording.Frame`, as a recording
          hands back, each carrying the screen it held and for how long. Those
          durations are wall-clock, so they are rounded onto a grid before they
          reach the picture, see `:screenshot-quantum:`;
        - any other sequence of strings, one captured text per frame, whose
          `:screenshot-interval:` says how long each is shown.

        `:screenshot-interval:` overrides a spinner's own when both are stated,
        and times a recording flatly when it would rather not keep the pace it
        was recorded at.

        ```{caution}
        An animated block pictures its *frames*, not its results. The block
        still runs, and its results still render on the page as any other
        block's do, but they are not what the image shows.
        ```

        A declared subject keeps the committed asset deterministic outright: the
        same expression composes the same lines on every build. A recording
        cannot, its frames being timed by the wall clock, so it leans on the
        quantum above and on the `@recording` line
        {meth}`~RunDirective.recording_moved` compares, which together leave an
        unchanged animation's committed bytes alone.

        :return: the frames and how long each is shown, or `None` when the block
            draws a still.
        :raises RuntimeError: when the expression cannot be evaluated.
        :raises TypeError: when it yields neither a spinner nor strings.
        :raises ValueError: when a bare sequence of frames states no interval.
        """
        interval = self.options.get("screenshot-interval")
        try:
            subject = eval(expression, self.runner.namespace)
        except Exception as exc:
            raise RuntimeError(
                f"click:run: {option}: failed to evaluate {expression!r}: {exc}",
            ) from exc

        if isinstance(subject, Spinner):
            return (subject.frame_lines(), interval or subject.interval)
        if isinstance(subject, str) or not isinstance(subject, Sequence):
            raise TypeError(
                f"click:run: {option}: {expression!r} yielded neither "
                f"a Spinner nor a sequence of frames (got "
                f"{type(subject).__name__}).",
            )
        recorded = tuple(subject)
        if not recorded:
            raise ValueError(
                f"click:run: {option}: {expression!r} yielded no frame to draw.",
            )
        if all(isinstance(frame, Frame) for frame in recorded):
            # Rounded here rather than left to the page, so forgetting to do it
            # cannot be what dirties the working tree on the next build.
            timed = quantize(
                recorded,
                self.options.get("screenshot-quantum", DEFAULT_QUANTUM),
            )
            texts = tuple(frame.text for frame in timed)
            if interval is not None:
                return (texts, interval)
            return (texts, tuple(frame.duration for frame in timed))
        if not all(isinstance(frame, str) for frame in recorded):
            raise TypeError(
                f"click:run: {option}: {expression!r} yielded a "
                "sequence holding neither a frame's text nor a recorded Frame.",
            )
        if interval is None:
            raise ValueError(
                f"click:run: {option}: needs a :screenshot-interval: "
                "when it does not name a spinner or a recording carrying one.",
            )
        return (recorded, interval)

    @cached_property
    def screenshot_animation(
        self,
    ) -> tuple[tuple[str, ...], float | tuple[float, ...]] | None:
        """Frames a *declared* animation draws, set by `:screenshot-animate:`.

        Declared frames are composed rather than timed, so they come out the
        same on every build and the asset is regenerated like any other, which
        is what keeps it from drifting away from the code. See
        {meth}`resolve_animation` for what the expression may yield, and
        `:screenshot-record:` for the case that cannot be regenerated.

        :return: the frames and how long each is shown, or `None` when the block
            draws a still.
        """
        expression = self.options.get("screenshot-animate")
        if expression is None:
            return None
        return self.resolve_animation(expression, ":screenshot-animate:")

    @property
    def emphasis_spec(self) -> str | None:
        """The lines the capture bands, as the block spells them.

        Only `:screenshot-emphasize-lines:` on a directive whose image is its
        *output*: the block's three emphasis options then mark three different
        contents, and folding any two together would band the wrong one.

        A block picturing its own code has one content, so `:emphasize-lines:`
        marks the same lines in the page's code block and in the image, and
        saying it twice would be the surprise. `:screenshot-emphasize-lines:`
        still overrides it where the two should differ.
        """
        spec = self.options.get("screenshot-emphasize-lines")
        if spec or not self.screenshots_source:
            return spec  # type: ignore[no-any-return]
        return self.options.get("emphasize-lines")  # type: ignore[no-any-return]

    def screenshot_emphasis(self, total: int) -> tuple[int, ...]:
        """Lines the capture bands, set by `:screenshot-emphasize-lines:`.

        Takes the same specification `:emphasize-lines:` does, `1,3-5` and the
        rest, and counts from one the same way. It is read here rather than at
        option-parsing time because the specification may name a range open at
        one end, which only means something once the capture's height is known.

        :param total: how many lines the capture is drawing.
        :return: the lines to band, counted from one.
        :raises ValueError: when the specification names no readable line.
        """
        spec = self.emphasis_spec
        if not spec:
            return ()
        try:
            wanted = parselinenos(spec, total)
        except ValueError as exc:
            raise ValueError(
                f"click:run: :screenshot-emphasize-lines: {spec!r}: {exc}",
            ) from exc
        return tuple(index + 1 for index in wanted)

    def numbered(self, frames: tuple[str, ...]) -> tuple[str, ...]:
        """Number every frame's lines when `:screenshot-line-numbers:` asks.

        Counted within each frame rather than once across the animation: a frame
        is a screen, and a screen's gutter numbers the rows it is showing. An
        animation whose rows accumulate therefore grows its gutter alongside
        them, which is what a terminal does.

        :param frames: the animation's frames.
        :return: the same frames, each with a gutter, or unchanged.
        """
        if "screenshot-line-numbers" not in self.options:
            return frames
        return tuple(number_lines(frame) for frame in frames)

    def screenshot_hold(self, fallback: float) -> float:
        """Seconds the last frame stays up, set by `:screenshot-hold:`.

        :param fallback: what to hold for when the block states nothing.
        :return: the pause, in seconds.
        """
        return self.options.get("screenshot-hold", fallback)  # type: ignore[no-any-return]

    @cached_property
    def screenshot_syntax_style(self) -> str:
        """Pygments style a source capture is colored with.

        Set by `:screenshot-syntax-style:`, falling back to the
        `click_extra_screenshot_syntax_style` `conf.py` value, then to the one
        the chrome is drawn for. Unused by a directive picturing its output,
        whose colors the command it ran already chose.

        :return: the style's name.
        :raises ValueError: when the name is not a style Pygments knows.
        """
        return resolve_style(
            self.options.get("screenshot-syntax-style")
            or self.env.config.click_extra_screenshot_syntax_style
            or None,
            self.screenshot_background,
        )

    @cached_property
    def screenshot_palette(self) -> TerminalPalette | None:
        """Colors the capture resolves against, beyond what the chrome names.

        `None` for a capture of a terminal, which is every run: its colors are
        the terminal's own, and the chrome already answers for them. A capture
        of *code* takes them from its syntax style instead, background included,
        so the picture looks like that style does in an editor.
        """
        if not self.screenshots_source:
            return None
        return style_palette(
            self.screenshot_syntax_style,
            self.screenshot_background,
            preset=self.screenshot_frame.get("preset"),
        )

    def screenshot_lines(self, results: Iterable[str]) -> list[str]:
        """The lines the still capture draws, before its gutter is added.

        The captured output, with one substitution: a block is run by a
        documentation build rather than by the terminal it pictures, so it
        prompts with this platform's sigil where the drawn terminal has its own.

        A block picturing its own code draws that instead, colored by
        {func}`~click_extra.snippet.highlight_code` into the same ANSI a command
        would have printed. It has no prompt to substitute, and `results` is
        whatever its runner returned, which for a source block is nothing.

        :param results: what the block's runner returned.
        :return: the lines to draw.
        :raises ValueError: when the block names a language or style Pygments
            does not know.
        """
        if self.screenshots_source:
            return highlight_code(
                "\n".join(self.content),
                language=self.language,
                style=self.screenshot_syntax_style,
            ).split("\n")

        lines = list(results)
        preset = self.screenshot_frame.get("preset")
        if (
            self.show_prompt
            and preset is not None
            and lines
            and lines[0].startswith(f"{PROMPT_SIGIL} ")
        ):
            # Gated on `show_prompt` so a `:hide-prompt:` block whose first
            # *output* line happens to open with "$ " is not mistaken for an
            # invocation.
            lines[0] = f"{preset.prompt} {lines[0].removeprefix(f'{PROMPT_SIGIL} ')}"
        return lines

    @cached_property
    def screenshot_frame(self) -> dict[str, Any]:
        """Window the capture is drawn in, set by the `:screenshot-*:` options.

        Each entry is left out when its option is: the renderer then picks what
        the chrome asks for, which is what every block on these pages wants.
        `:screenshot-backdrop:`, `:screenshot-border:` and
        `:screenshot-shadow:` take a CSS color (or `none` to paint neither),
        `:screenshot-border-width:`, `:screenshot-margin:`,
        `:screenshot-padding:` and `:screenshot-radius:` take pixels,
        `:screenshot-opacity:` how solid the window's body is,
        `:screenshot-title:` the caption drawn in the window's own chrome, and
        `:screenshot-watermark:` a credit line for the image's corner, which no
        capture carries here unless asked for.
        `:screenshot-line-numbers:` is a flag, numbering every line the block
        rendered, its prompt first. See
        {func}`~click_extra.screenshot.render_svg`.

        A block naming no preset falls back to the one the
        `click_extra_screenshot_preset` `conf.py` value names, so a project
        drawing all of its captures as the same terminal states it once.
        """
        frame = {
            name.replace("-", "_"): self.options[f"screenshot-{name}"]
            for name in (
                "backdrop",
                "border",
                "border-width",
                "margin",
                "opacity",
                "padding",
                "preset",
                "radius",
                "shadow",
                "title",
                "watermark",
                "watermark-color",
            )
            if f"screenshot-{name}" in self.options
        }
        # Stated even when nothing asks for one, the renderer crediting
        # click-extra by default: an image a build rewrites and commits cannot
        # carry a release number without being rewritten by every release.
        frame.setdefault(
            "watermark",
            self.env.config.click_extra_screenshot_watermark,
        )
        # Spelled out rather than imported from the package declaring it, as
        # the screenshot directory next door is: the name is the conf.py API.
        default_preset = self.env.config.click_extra_screenshot_preset
        if default_preset and "preset" not in frame:
            if default_preset not in PRESETS:
                raise ValueError(
                    "click_extra_screenshot_preset names no terminal Click "
                    f"Extra knows: {default_preset!r} is not one of "
                    f"{', '.join(sorted(PRESETS))}."
                )
            frame["preset"] = PRESETS[default_preset]
        return frame

    def write_screenshot(self, results: Iterable[str]) -> None:
        """Write the captured output as an SVG beside the documentation.

        The file lands in the directory the `click_extra_screenshot_dir`
        `conf.py` value names, under the source root, so a README pointing at
        the repository embeds the very output this page renders live.

        This is a side effect, not a rendering: the page keeps its results code
        block, which stays selectable, searchable and theme-aware where an image
        would not be. Use `:mirror:` to put the image on the page as well.

        Writing during the build keeps the committed asset in step with the CLI
        without anyone remembering to refresh it, and it is deterministic:
        `unique_id` is pinned to the asset's name, so an unchanged CLI rewrites
        byte-identical bytes and leaves the working tree clean.

        ```{note}
        That refresh only happens when the document carrying the block is
        re-parsed: Sphinx's environment cache skips unchanged sources. A
        change on the *package* side (a new config format widening a
        `--config` default, say) leaves every capture stale until a rebuild
        with a fresh environment (`sphinx-build -E`).
        ```
        """
        assert self.screenshot
        path = (
            Path(self.env.srcdir)
            / self.env.config.click_extra_screenshot_dir
            / f"{self.screenshot}.svg"
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        recording = self.options.get("screenshot-record")
        if recording is not None:
            if path.exists() and animation_metadata(path.read_text(encoding="utf-8")):
                # Kept as it was recorded. A recording of an animation cannot be
                # reproduced: which spinner glyph pairs with which screen is
                # decided by the scheduler, so the same command records a
                # different set of frames every other run. Rewriting on each
                # build would dirty the working tree for nothing anyone did, so
                # the first recording is the one that stands.
                #
                # The expression is not even evaluated here, which is what keeps
                # the command it records off every later build's clock. To take
                # a fresh recording, delete the file and build again.
                return
            frames, interval = self.resolve_animation(recording, ":screenshot-record:")
            path.write_text(
                render(
                    columns=self.screenshot_columns,
                    unique_id=self.screenshot,
                    background=self.screenshot_background,
                    frames=self.numbered(frames),
                    emphasize=self.screenshot_emphasis(
                        max(frame.count("\n") + 1 for frame in frames)
                    ),
                    interval=interval,
                    hold=self.screenshot_hold(DEFAULT_RECORDING_HOLD),
                    blank=self.options.get("screenshot-blank", DEFAULT_RECORDING_BLANK),
                    speed=self.options.get("screenshot-speed", 1.0),
                    **self.screenshot_frame,
                ),
                encoding="utf-8",
            )
            return

        animation = self.screenshot_animation
        if animation is not None:
            frames, interval = animation
            drawn = render(
                columns=self.screenshot_columns,
                unique_id=self.screenshot,
                background=self.screenshot_background,
                frames=self.numbered(frames),
                emphasize=self.screenshot_emphasis(
                    max(frame.count("\n") + 1 for frame in frames)
                ),
                interval=interval,
                hold=self.screenshot_hold(0.0),
                blank=self.options.get("screenshot-blank", 0.0),
                speed=self.options.get("screenshot-speed", 1.0),
                **self.screenshot_frame,
            )
            path.write_text(drawn, encoding="utf-8")
            return

        lines = self.screenshot_lines(results)
        if "screenshot-line-numbers" in self.options and lines:
            # Numbered whole, so line 1 is the first line the picture shows.
            lines = number_lines("\n".join(lines)).splitlines()
        path.write_text(
            render(
                "\n".join(lines),
                emphasize=self.screenshot_emphasis(len(lines)),
                columns=self.screenshot_columns,
                unique_id=self.screenshot,
                background=self.screenshot_background,
                palette=self.screenshot_palette,
                **self.screenshot_frame,
            ),
            encoding="utf-8",
        )

    def run(self) -> list[nodes.Node]:
        """Execute the directive and render its source and results."""
        assert hasattr(self.runner, self.runner_method), (
            f"{self.runner!r} does not have a method named {self.runner_method!r}."
        )
        runner_func = getattr(self.runner, self.runner_method)
        results = runner_func(self)

        # Materialize the committed capture before deciding what to render: the
        # asset is wanted even by a block hiding its own results.
        if self.screenshot:
            self.write_screenshot(results)

        # If neither source code nor results are requested, we don't render anything.
        if not self.show_source and not self.show_results:
            return []

        lines = []
        if self.show_source:
            language = self.language
            # If we are running a CLI, we force rendering the source code as a
            # Python code block.
            if self.runner_method == "run_cli":
                language = SourceDirective.default_language
            lines.extend(self.render_code_block(self.content, language, "source"))
        if self.show_results:
            lines.extend(self.render_code_block(results, self.language, "results"))

        # Convert code block lines to a Docutils node tree.
        return parse_into_section(self, lines)


class SourceDirective(ClickDirective):
    """Directive to declare a Click CLI source code.

    This directive is used to declare a Click CLI example in the
    documentation. It renders the source code of the example in a
    Python code block.
    """

    default_language = "python"
    show_source_by_default = True
    show_results_by_default = False
    runner_method = "execute_source"
    screenshots_source = True


class RunDirective(ClickDirective):
    """Directive to run a Click CLI example.

    This directive is used to run a Click CLI example in the
    documentation. It renders the results of running the example in a
    shell session code block supporting ANSI colors.
    """

    default_language = "ansi-shell-session"
    show_source_by_default = False
    show_results_by_default = True
    runner_method = "run_cli"


ClickDirective.runner_factory = ClickRunner


def _split_run_options(inner: Iterable[str]) -> dict[str, str]:
    """Collect the leading `:key: value` option lines of a fence body.

    Stops at the first line that is not an option, so a body whose Python
    happens to start with a colon is never mistaken for one.
    """
    options: dict[str, str] = {}
    for line in inner:
        match = OPTION_LINE_RE.match(line)
        if not match:
            break
        options[match.group("key")] = match.group("value")
    return options


def _skip_existing_screenshot_region(lines: list[str], index: int) -> int:
    """Return the index just past an existing screenshot region at `index`.

    Skips leading blank lines, then a {data}`SCREENSHOT_MARKER_START` …
    {data}`SCREENSHOT_MARKER_END` block if one is present. Returns `index`
    unchanged when no region follows, so a first-time block is not consumed.
    """
    cursor = index
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor < len(lines) and _SCREENSHOT_OPEN_RE.match(lines[cursor]):
        while cursor < len(lines) and not _SCREENSHOT_CLOSE_RE.match(lines[cursor]):
            cursor += 1
        if cursor < len(lines):
            return cursor + 1
    return index


def _rewrite_screenshot_regions(
    text: str,
    directory: str = DEFAULT_SCREENSHOT_DIR,
) -> str:
    """Return `text` with every capture block's `:mirror:` region refreshed.

    Walks the document fence by fence via {func}`click_extra.blocks.fence_spans`,
    so an example nested inside a longer `code-block` fence is copied verbatim,
    never treated as a live block. Only a top-level fence
    ({data}`_CAPTURE_FENCE_OPEN`) carrying both `:screenshot:` and `:mirror:`
    gets a region, inserted directly below it on first sight. Idempotent: an
    unchanged block round-trips to the same text.

    The image itself is written by the directive at build time. This only
    maintains the Markdown pointing at it.
    """
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

        options: dict[str, str] = {}
        if _CAPTURE_FENCE_OPEN.match(lines[index]):
            options = _split_run_options(lines[index + 1 : span.close])
        # Emit the whole fence unit (source and close line) verbatim.
        out.extend(lines[index : span.close + 1])
        index = span.close + 1
        name = options.get("screenshot")
        if not name or "mirror" not in options:
            continue

        index = _skip_existing_screenshot_region(lines, index)
        out.extend([
            "",
            SCREENSHOT_MARKER_START,
            "",
            f"![{name}]({directory}/{name}.svg)",
            "",
            SCREENSHOT_MARKER_END,
        ])
        # Collapse the gap to the following content to a single blank line.
        while index < total and not lines[index].strip():
            index += 1
        if index < total:
            out.append("")

    return "\n".join(out)


def update_screenshot_blocks(
    paths: Iterable[Path],
    *,
    check: bool = False,
    directory: str = DEFAULT_SCREENSHOT_DIR,
) -> list[Path]:
    """Refresh every capture block's `:mirror:` region in the given sources.

    See {func}`click_extra.blocks.update_blocks` for the walk, write, and
    `check`-mode contract. Unlike the `python:render` `:mirror:` refresher, this
    executes nothing: a region's content is derived from the block's
    `:screenshot:` name.

    :param paths: Markdown files, or directories recursed for `*.md`.
    :param check: report what would change without writing.
    :param directory: where the captures live, relative to each document.
    :return: the files whose regions were (or, under `check`, would be) updated.
    """

    def rewrite(text: str, path: Path) -> str:
        return _rewrite_screenshot_regions(text, directory)

    return update_blocks(paths, rewrite, check=check)


class TreeDirective(ClickDirective):
    """Render a complete CLI reference for a Click command and all its subcommands.

    Walks the Click command tree at build time and emits, in MyST syntax:

    - A GFM summary table linking each command to its section anchor.
    - A heading + `click:run` `--help` block for the root command.
    - One heading + `click:run` `--help` block per subcommand, nested by
      depth.

    Designed to replace per-project hand-rolled generators (like repomatic's
    `docs_update.py::cli_reference()`) with a single declarative directive
    that walks the live command tree on every build.

    The required argument is a Python expression evaluated in the per-document
    runner namespace; it must yield a {class}`click.Command`. The optional
    directive body is Python preamble exec'd in the same namespace before
    evaluation, so authors may either import the CLI in a prior
    `click:source :hide-source:` block or inline the import here.

    ```{note}
    Currently MyST-only. Use the directive in a `.md` document with
    `myst_parser` enabled.
    ```
    """

    has_content = True
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False

    option_spec: ClassVar[OptionSpec] = {
        "max-depth": directives.positive_int,
        "heading-offset": directives.nonnegative_int,
        "anchor-prefix": directives.unchanged,
        "label-prefix": directives.unchanged,
        "root-label": directives.unchanged,
        "no-table": directives.flag,
        "no-root": directives.flag,
    }
    """Recognized directive options.

    `max-depth` caps the recursion into nested {class}`click.Group` commands
    (default: `10`). `heading-offset` shifts all generated headings down
    by N levels. When unset, the directive reads
    `state.memo.section_level` and uses the surrounding section depth so
    the root nests one level below the enclosing section: inside the
    document's `h1` title this yields `1` (root at `h2`); inside an
    `h3` section it yields `3` (root at `h4`). Override only when the
    auto-detected depth is wrong for the page layout. `anchor-prefix` and
    `label-prefix` override the slug and display prefix used for anchors
    and labels; both default to the CLI's {attr}`click.Command.name`.
    `root-label` sets the heading text for the root help block
    (default: `"Help screen"`). `no-table` skips the summary table;
    `no-root` skips the root `--help` block.
    """

    # The runner_attr, runner property, is_myst_syntax cached-property, and
    # the _slug/_surrounding_section_depth helpers are inherited unchanged
    # from ClickDirective. Sharing the "click_runner" attribute means a
    # click:source that ran earlier on the same document has already
    # populated the namespace with the CLI variable this directive resolves.

    def _walk(
        self,
        root: click.Command,
        max_depth: int,
    ) -> list[tuple[list[str], click.Command]]:
        """Depth-first traversal of the command tree, sorted alphabetically.

        Returns `(path, command)` tuples where `path` is the list of
        subcommand names from the root (exclusive) down to `command`. The
        root itself is not included; callers that want a root entry add it
        separately (see {meth}`run`).
        """
        entries: list[tuple[list[str], click.Command]] = []

        def recurse(cmd: click.Command, path: list[str], depth: int) -> None:
            if not isinstance(cmd, click.Group) or depth >= max_depth:
                return
            for name in sorted(cmd.commands):
                sub_path = [*path, name]
                entries.append((sub_path, cmd.commands[name]))
                recurse(cmd.commands[name], sub_path, depth + 1)

        recurse(root, [], 0)
        return entries

    def run(self) -> list[nodes.Node]:
        # Hard errors (RuntimeError, not self.error()) so the build fails
        # fast: a partially rendered reference page hides bugs in the CLI
        # tree the directive was meant to document.
        if not self.is_myst_syntax:
            raise RuntimeError(
                "click:tree currently only supports MyST syntax. "
                "Place the directive in a .md document with myst_parser enabled.",
            )

        # Execute the optional body in the runner namespace so callers can
        # inline `from mypkg.cli import mycli` instead of seeding the
        # namespace with a separate `click:source :hide-source:` block.
        if self.content:
            self.runner.execute_source(self)

        cli_expr = self.arguments[0].strip()
        try:
            cli = eval(cli_expr, self.runner.namespace)
        except Exception as exc:
            raise RuntimeError(
                f"click:tree: failed to evaluate {cli_expr!r}: {exc}",
            ) from exc
        if not isinstance(cli, click.Command):
            raise TypeError(
                f"click:tree: {cli_expr!r} did not yield a click.Command "
                f"(got {type(cli).__name__}).",
            )

        max_depth = self.options.get("max-depth", 10)
        # Without an explicit override, nest the generated headings one
        # level below the surrounding section so the document outline stays
        # consistent regardless of where the directive is placed. At the
        # document's top level this resolves to the historical default of 1
        # (root rendered at h2 under a document title at h1).
        heading_offset = self.options.get(
            "heading-offset",
            self._surrounding_section_depth(),
        )
        label_prefix = self.options.get("label-prefix") or cli.name or cli_expr
        anchor_prefix = self.options.get("anchor-prefix") or self._slug(label_prefix)
        root_label = self.options.get("root-label", "Help screen")
        include_table = "no-table" not in self.options
        include_root = "no-root" not in self.options

        entries = self._walk(cli, max_depth)

        # Local import to avoid a circular import: click_extra.table is part
        # of the same package and pulls in optional rendering deps.
        from ..table import TableFormat, render_table

        lines: list[str] = []

        # Summary table.
        if include_table:
            rows: list[list[str]] = []
            if include_root:
                desc = (cli.get_short_help_str() or "").rstrip(".")
                rows.append([f"[`{label_prefix}`](#{anchor_prefix})", desc])
            for path, cmd in entries:
                label = f"{label_prefix} {' '.join(path)}".strip()
                anchor = "-".join([anchor_prefix, *(self._slug(p) for p in path)])
                desc = (cmd.get_short_help_str() or "").rstrip(".")
                rows.append([f"[`{label}`](#{anchor})", desc])
            if rows:
                lines.append(
                    render_table(
                        rows,
                        headers=["Command", "Description"],
                        table_format=TableFormat.GITHUB,
                    ),
                )
                lines.append("")

        # Root help block. Placed at the same heading level as top-level
        # commands so subcommands always nest one level deeper than their
        # parent, matching the repomatic convention.
        if include_root:
            heading = "#" * (heading_offset + 1)
            lines.append(f"({anchor_prefix})=")
            lines.append(f"{heading} {root_label}")
            lines.append("")
            lines.append("```{click:run}")
            lines.append(f"invoke({cli_expr}, args=['--help'])")
            lines.append("```")
            lines.append("")

        # Per-command sections.
        for path, _cmd in entries:
            heading = "#" * (heading_offset + len(path))
            anchor = "-".join([anchor_prefix, *(self._slug(p) for p in path)])
            label = f"{label_prefix} {' '.join(path)}".strip()
            args_repr = ", ".join(repr(a) for a in [*path, "--help"])

            lines.append(f"({anchor})=")
            lines.append(f"{heading} `{label}`")
            lines.append("")
            lines.append("```{click:run}")
            lines.append(f"invoke({cli_expr}, args=[{args_repr}])")
            lines.append("```")
            lines.append("")

        # Nested `{click:run}` directives execute during the shared parse and
        # resolve the CLI variable from the same runner namespace.
        return parse_into_section(self, lines)


def _format_default(value: object) -> str:
    """Format a schema field default as a Markdown fragment.

    Used in both the summary table cells and the per-option `**Default:**`
    lines of `click:config`. Multi-line strings are elided to a pointer,
    since the TOML example block below renders them in full.
    """
    if value is None:
        return "*(none)*"
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    if isinstance(value, int):
        return f"`{value}`"
    if isinstance(value, str):
        if "\n" in value:
            return "*(see example)*"
        return f'`"{value}"`'
    if isinstance(value, list):
        if not value:
            return "`[]`"
        return f"`{value!r}`"
    return str(value)


def _toml_value(value: object) -> str | None:
    """Format a Python value as a TOML literal.

    Returns `None` when no sensible literal exists (`None` defaults,
    opaque objects), which suppresses the option's example block in
    `click:config`.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        if "\n" in value:
            return "'''\n" + value + "\n'''"
        return f'"{value}"'
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [_toml_value(v) for v in value]
        if any(v is None for v in items):
            return None
        return "[" + ", ".join(items) + "]"  # type: ignore[arg-type]
    return None


class ConfigDirective(ClickDirective):
    """Render the configuration reference of a CLI's `config_schema`.

    Introspects a configuration schema dataclass at build time and expands,
    in MyST syntax:

    - A GFM summary table linking each option to its section anchor, with its
      one-line summary and default value.
    - One heading per option, with its docstring, type, default, and a TOML
      example pinned to the default value.

    Option metadata comes from
    {func}`~click_extra.config.schema.schema_field_infos`: dotted kebab-case
    keys, type annotations, defaults from a pristine schema instance, and
    attribute docstrings (which are parsed as the host document's markup).
    Designed to replace per-project hand-rolled generators (like repomatic's
    `docs_update.py::config_deflist()`) with a single declarative directive
    that documents the live schema on every build.

    The required argument is a Python expression evaluated in the per-document
    runner namespace; it must yield either a {class}`click.Command` whose
    `config_schema` is set (the schema is pulled off its
    {class}`~click_extra.config.option.ConfigOption`), or a schema dataclass
    directly. The optional directive body is Python preamble exec'd in the
    same namespace before evaluation, so authors may either import the CLI in
    a prior `click:source` `:hide-source:` block or inline the import
    here.

    ```{caution}
    Attribute docstrings are recovered from the schema's source file, so
    a schema defined inside an exec'd `click:source` block documents
    its options without descriptions. Import the schema from a real
    module instead (see
    {func}`~click_extra.config.schema.field_docstrings`).
    ```

    ```{note}
    Currently MyST-only. Use the directive in a `.md` document with
    `myst_parser` enabled.
    ```
    """

    has_content = True
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False

    option_spec: ClassVar[OptionSpec] = {
        "heading-offset": directives.nonnegative_int,
        "section": directives.unchanged,
        "no-table": directives.flag,
        "no-examples": directives.flag,
    }
    """Recognized directive options.

    `heading-offset` shifts all generated headings down by N levels; when
    unset, the surrounding section depth is used (same behavior as
    `click:tree`). `section` overrides the TOML table header shown in the
    per-option examples: it defaults to ``tool.{cli-name}`` when the argument
    is a CLI (matching how click-extra and its downstream CLIs read their
    section from `pyproject.toml`), and to no header at all for a bare
    schema; an explicitly empty `:section:` suppresses the header.
    `no-table` skips the summary table; `no-examples` skips the TOML
    example blocks.
    """

    def run(self) -> list[nodes.Node]:
        # Hard errors (RuntimeError, not self.error()) so the build fails
        # fast: a partially rendered reference page hides bugs in the schema
        # the directive was meant to document.
        if not self.is_myst_syntax:
            raise RuntimeError(
                "click:config currently only supports MyST syntax. "
                "Place the directive in a .md document with myst_parser enabled.",
            )

        # Execute the optional body in the runner namespace so callers can
        # inline `from mypkg.cli import mycli` instead of seeding the
        # namespace with a separate `click:source :hide-source:` block.
        if self.content:
            self.runner.execute_source(self)

        target_expr = self.arguments[0].strip()
        try:
            target = eval(target_expr, self.runner.namespace)
        except Exception as exc:
            raise RuntimeError(
                f"click:config: failed to evaluate {target_expr!r}: {exc}",
            ) from exc

        # Local import to avoid a circular import: click_extra.config is part
        # of the same package and is imported after click_extra.sphinx from
        # the package __init__.
        from ..config.option import ConfigOption
        from ..config.schema import schema_field_infos

        section = self.options.get("section")
        if isinstance(target, click.Command):
            schema = None
            for param in target.params:
                if isinstance(param, ConfigOption) and param.config_schema:
                    schema = param.config_schema
                    break
            if schema is None:
                raise RuntimeError(
                    f"click:config: {target_expr!r} has no config_schema wired "
                    "to its ConfigOption.",
                )
            if section is None and target.name:
                section = f"tool.{target.name}"
        else:
            schema = target

        # Also narrows the ConfigOption union (its config_schema may be a bare
        # callable) down to the dataclass type schema_field_infos expects.
        if not (isinstance(schema, type) and is_dataclass(schema)):
            raise TypeError(
                f"click:config: {target_expr!r} did not yield a dataclass "
                f"schema (got {schema!r}).",
            )

        infos = schema_field_infos(schema)

        heading_offset = self.options.get(
            "heading-offset",
            self._surrounding_section_depth(),
        )
        include_table = "no-table" not in self.options
        include_examples = "no-examples" not in self.options

        # Local import to avoid a circular import: click_extra.table is part
        # of the same package and pulls in optional rendering deps.
        from ..table import TableFormat, render_table

        lines: list[str] = []

        # Summary table. Each option links to the natural anchor docutils
        # derives from its heading below, so the same slugs keep working when
        # a page migrates from a hand-generated reference to this directive.
        if include_table and infos:
            rows = [
                [
                    f"[`{info.key}`](#{self._slug(info.key)})",
                    info.summary.replace("|", "\\|"),
                    _format_default(info.default),
                ]
                for info in infos
            ]
            lines.append(
                render_table(
                    rows,
                    headers=["Option", "Description", "Default"],
                    table_format=TableFormat.GITHUB,
                ),
            )
            lines.append("")

        # Per-option sections: lead with the summary, then type and default,
        # then the rest of the docstring, and finally a TOML example pinned
        # to the field's default value.
        heading = "#" * (heading_offset + 1)
        for info in infos:
            # Strip the summary (already shown first) from the full docstring.
            _head, _sep, tail = info.description.partition("\n\n")
            rest = tail.strip()

            lines.append(f"{heading} `{info.key}`")
            lines.append("")
            if info.summary:
                lines.append(info.summary)
                lines.append("")
            # The "| None" half of an optional type is noise here: the
            # Default line right next to it already says whether the option
            # defaults to nothing.
            type_hint = info.type_hint.replace(" | None", "")
            lines.append(
                f"**Type:** `{type_hint}` | **Default:** "
                f"{_format_default(info.default)}",
            )
            lines.append("")
            if rest:
                lines.extend(rest.splitlines())
                lines.append("")
            example = _toml_value(info.default) if include_examples else None
            if example is not None:
                lines.append("**Example:**")
                lines.append("")
                lines.append("```toml")
                if section:
                    lines.append(f"[{section}]")
                lines.extend(f"{info.key} = {example}".splitlines())
                lines.append("```")
                lines.append("")

        # Hand the generated MyST source back to the parser, like click:tree.
        return parse_into_section(self, lines)


class ClickDomain(StatelessDomain):
    """Setup new directives under the same `click` namespace:

    - `click:source` which renders a Click CLI source code
    - `click:run` which renders the results of running a Click CLI
    - `click:tree` which walks a Click command tree and renders the full
      `--help` reference for every subcommand, with a summary table on top
    - `click:config` which documents a CLI's `config_schema`: a summary
      table plus one section per option, with types, defaults, and TOML
      examples
    """

    name = "click"
    label = "Click"
    directives: ClassVar[dict] = {
        "source": SourceDirective,
        "run": RunDirective,
        "tree": TreeDirective,
        "config": ConfigDirective,
    }


cleanup_runner = make_cleanup("click_runner")
"""Drop the {class}`ClickRunner` from the doctree once the document is read."""
