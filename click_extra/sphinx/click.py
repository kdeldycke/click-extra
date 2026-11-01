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

Holds the `click:source` and `click:run` directives, their options, and the
`:screenshot:` captures and `:mirror:` regions they maintain.
{mod}`click_extra.sphinx.click_runner` runs their blocks, and
{mod}`click_extra.sphinx.click_reference` builds the `click:tree` and
`click:config` reference directives on top of them.

```{seealso}
These directives are based on [Pallets' Sphinx Themes](https://github.com/pallets/pallets-sphinx-themes/blob/main/src/pallets_sphinx_themes/themes/click/domain.py),
[released under a BSD-3-Clause license](https://github.com/pallets/pallets-sphinx-themes/blob/main/LICENSE.txt).

Compared to the latter, it:

- Adds support for MyST syntax.
- Adds rendering of ANSI codes in CLI results.
- Has better error handling and reporting which helps you pinpoint the failing
  code in your documentation.
- Has no `println` function: a block prints a blank line natively.
```

```{todo}
Retire the MyST `content_offset` workaround of `click_extra.sphinx._base` once
the pinned `myst-parser` floor rises past the release carrying the fix for the
inflated `content_offset`, which the open rework
[`#1175`](https://github.com/executablebooks/MyST-Parser/pull/1175) does not
include:

- delete `_myst_content_offset_inflation` and
  `MYST_CONTENT_OFFSET_INFLATED_MAX`, and collapse
  `ContentOffsetMixin.abs_content_offset` onto its rST branch
  (`content_offset` verbatim);
- drop the `directive.content` fallback in `directive_source`, which stays off
  `block_text` only because that attribute is body-only in
  `myst-parser <= 5.1.0`
  ([`#1164`](https://github.com/executablebooks/MyST-Parser/pull/1164) is
  merged but unreleased). A released `block_text` anchors a robust
  line-number computation and retires the workaround from both sides.

The single-trailing-blank-line case documented on
`_myst_content_offset_inflation` stays off by one until then, and no local fix
can reach it: the round-trip consumes that line without a trace.
```
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import cached_property
from pathlib import Path

from docutils import nodes
from sphinx.directives import directives
from sphinx.directives.code import CodeBlock
from sphinx.util import parselinenos

from ..capture.presets import (
    OPAQUE,
    PRESETS,
    Chrome,
    Cursor,
    CursorShape,
    TerminalPreset,
)
from ..capture.recording import (
    DEFAULT_QUANTUM,
    DEFAULT_RECORDING_BLANK,
    DEFAULT_RECORDING_HOLD,
    DEFAULT_SUBMIT,
    Frame,
    quantize,
    type_line,
)
from ..capture.screenshot import (
    AUTO_CURSOR,
    DEFAULT_COLUMNS,
    append_prompt,
    parse_columns,
    prompt_line,
    render,
)
from ..capture.snippet import highlight_code, resolve_style, style_palette
from ..capture.svg import animation_metadata, parse_hold, parse_pause
from ..color import TerminalBackground
from ..layout import number_frames, number_lines
from ..markdown.blocks import (
    region_markers,
    rewrite_fenced_regions,
    split_options,
    update_blocks,
)
from ..spinner import Spinner
from ._base import ContentOffsetMixin, make_cleanup, parse_into_section
from .click_runner import PROMPT_SIGIL, ClickRunner, _resolve_run_capture

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any, ClassVar

    from sphinx.application import Sphinx
    from sphinx.util.typing import OptionSpec

    from ..capture.presets import TerminalPalette
    from ..capture.screenshot import TColumns
    from ..capture.svg import THold


RST_INDENT = " " * 3
"""The indentation used for rST code blocks lines."""


DEFAULT_SCREENSHOT_DIR = "assets"
"""Directory a `click:run` `:screenshot:` capture is written to by default.

Relative to the documentation source root. Overridden by the
`click_extra_screenshot_dir` `conf.py` value, see {data}`SCREENSHOT_DIR_CONFIG`.
"""

RUN_CAPTURE_CONFIG = "click_extra_run_capture"
"""Name of the `conf.py` value selecting the stream-capture mode for the CLIs that
`click:run` and `click:tree` execute.

Maps to the `capture` parameter of Click's {class}`~click.testing.CliRunner`,
`"sys"` or `"fd"`. Defaults to `"fd"` so a command writing through
`sys.stdout.fileno()` is captured at the file-descriptor level and renders,
instead of aborting the build with {exc}`io.UnsupportedOperation`. Windows has no
file-descriptor capture, so `"fd"` degrades to `"sys"` there.
"""

SCREENSHOT_DIR_CONFIG = "click_extra_screenshot_dir"
"""Name of the `conf.py` value locating the directory `click:run` writes captures to.

A path relative to the documentation source directory, holding the SVG a
`click:run` block names with its `:screenshot:` option. Defaults to
{data}`DEFAULT_SCREENSHOT_DIR`, matching where a Sphinx project conventionally
keeps the images its pages embed, and where a README pointing at the repository
finds them.
"""

SCREENSHOT_PRESET_CONFIG = "click_extra_screenshot_preset"
"""Name of the `conf.py` value naming the terminal every capture is drawn as.

One of {data}`~click_extra.capture.presets.PRESETS`, applied to each
`click:run` block whose `:screenshot:` does not name a preset of its own. Empty
by default, which keeps the renderer's neutral window: a project wanting all of
its captures to look like the same desktop states it once here instead of on
every block.
"""

SCREENSHOT_SYNTAX_STYLE_CONFIG = "click_extra_screenshot_syntax_style"
"""Name of the `conf.py` value coloring every capture drawn from source code.

One of the [Pygments styles](https://pygments.org/styles/), applied to each
source block whose `:screenshot:` does not name a
`:screenshot-syntax-style:` of its own. Empty by default, which takes the style
each chrome is drawn for, see
{data}`~click_extra.capture.snippet.DEFAULT_SYNTAX_STYLES`. Unused by a block picturing
what a command printed, whose colors that command already chose.
"""

SCREENSHOT_WATERMARK_CONFIG = "click_extra_screenshot_watermark"
"""Name of the `conf.py` value crediting every capture a `click:run` writes.

Empty by default, where a capture carries the credit of the `screenshot` command.
A project wanting its own text states it here, or per block with
`:screenshot-watermark:`.
"""

SCREENSHOT_MARKER_START = region_markers("screenshot")[0]
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

SCREENSHOT_MARKER_END = region_markers("screenshot")[1]
"""Closing marker of a `:mirror:` region. See {data}`SCREENSHOT_MARKER_START`."""

_CAPTURE_FENCE_OPEN_RE = re.compile(
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


def register_config(app: Sphinx) -> None:
    """Declare the `conf.py` values the `click:*` directives read.

    Called by {func}`click_extra.sphinx.setup` beside the opt-in flag gating the
    directives, and whether or not the project opts in: a `conf.py` naming one of
    these values is then valid on every project loading the extension.
    """
    # Stream-capture mode for the CLIs click:run and click:tree execute, see
    # ClickRunner.
    app.add_config_value(RUN_CAPTURE_CONFIG, "fd", "env", types=[str])
    # Where a `click:run` `:screenshot:` capture is written.
    app.add_config_value(
        SCREENSHOT_DIR_CONFIG, DEFAULT_SCREENSHOT_DIR, "env", types=[str]
    )
    # Terminal every capture is drawn as, unless a block says otherwise.
    app.add_config_value(SCREENSHOT_PRESET_CONFIG, "", "env", types=[str])
    # Pygments style every source capture is colored with, see snippet.py.
    app.add_config_value(SCREENSHOT_SYNTAX_STYLE_CONFIG, "", "env", types=[str])
    # Credit line every capture carries, off unless a project asks for one.
    app.add_config_value(SCREENSHOT_WATERMARK_CONFIG, "", "env", types=[str])


def _screenshot_opacity(argument: str) -> float:
    """Read the `:screenshot-opacity:` option into how solid the window is."""
    opacity = float(argument)
    if not 0.0 <= opacity <= OPAQUE:
        raise ValueError(f"{argument} is not an opacity, between 0 and {OPAQUE}.")
    return opacity


def _screenshot_cursor(argument: str | None) -> CursorShape | None:
    """Read the `:screenshot-cursor:` option into a shape, or into the preset's.

    A bare `:screenshot-cursor:` reaches here as `None`, which docutils passes
    for an option written without a value. That, an empty one, and
    {data}`~click_extra.capture.screenshot.AUTO_CURSOR` all leave the shape to the
    terminal preset the block is drawn as.
    """
    shape = (argument or "").strip().lower()
    if not shape or shape == AUTO_CURSOR:
        return None
    try:
        return CursorShape(shape)
    except ValueError:
        known = ", ".join(member.value for member in CursorShape)
        raise ValueError(
            f"{argument} is not a cursor shape: name one of {known}, or {AUTO_CURSOR}."
        ) from None


def _positive_number(argument: str) -> float:
    """Read an option that only a number above zero makes sense for.

    A frame duration, a typing pace, a replay speed and a rounding grid all take
    one.
    """
    number = float(argument)
    if number <= 0:
        raise ValueError(f"{argument} is not a positive number.")
    return number


def _screenshot_preset(argument: str) -> TerminalPreset:
    """Read the `:screenshot-preset:` option into the terminal it names."""
    return PRESETS[directives.choice(argument, tuple(sorted(PRESETS)))]


def _screenshot_background(argument: str) -> TerminalBackground:
    """Read the `:screenshot-background:` option into its enum member.

    Rejecting an unknown chrome here, at the option level, is what turns a typo
    into a build error naming the choices, instead of a capture silently drawn
    on the default.
    """
    choices = tuple(member.value for member in TerminalBackground)
    return TerminalBackground(directives.choice(argument, choices))


def _code_fence(lines: Iterable[str]) -> str:
    """Return a backtick fence longer than any backtick run opening one of `lines`.

    A MyST fence closes on the first bare backtick run at least as long as its
    opener. A fixed three-backtick fence therefore ends early around content
    holding a fence of its own, like a command's Markdown help. The fence is
    never shorter than three backticks.
    """
    longest = max(
        (len(line) - len(line.lstrip("`")) for line in map(str.lstrip, lines)),
        default=0,
    )
    return "`" * max(3, longest + 1)


def _write_capture(path: Path, svg: str) -> None:
    """Write `svg` to `path`, unless the file holds it already.

    The rule of {func}`click_extra.markdown.blocks.rewrite_file`, for a file that
    may not exist yet. Writing the same bytes again would still move the
    modification time of the file, which a tool watching the documentation tree
    reads as a change.
    """
    if path.exists() and path.read_text(encoding="UTF-8") == svg:
        return
    path.write_text(svg, encoding="UTF-8")


class ClickDirective(ContentOffsetMixin):
    """Base class of every `click:*` directive."""

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
        "mirror": directives.flag,
        "screenshot": directives.unchanged_required,
        "screenshot-animate": directives.unchanged_required,
        "screenshot-backdrop": directives.unchanged_required,
        "screenshot-background": _screenshot_background,
        "screenshot-blank": parse_pause,
        "screenshot-blink": parse_pause,
        "screenshot-border": directives.unchanged_required,
        "screenshot-border-width": directives.nonnegative_int,
        "screenshot-closing-prompt": directives.flag,
        "screenshot-columns": parse_columns,
        "screenshot-cursor": _screenshot_cursor,
        "screenshot-emphasize-lines": directives.unchanged_required,
        "screenshot-hold": parse_hold,
        "screenshot-interval": _positive_number,
        "screenshot-line-numbers": directives.flag,
        "screenshot-margin": directives.nonnegative_int,
        "screenshot-opacity": _screenshot_opacity,
        "screenshot-padding": directives.nonnegative_int,
        "screenshot-preset": _screenshot_preset,
        "screenshot-prompt": directives.unchanged,
        "screenshot-quantum": _positive_number,
        "screenshot-radius": directives.nonnegative_int,
        "screenshot-record": directives.unchanged_required,
        "screenshot-shadow": directives.unchanged_required,
        "screenshot-speed": _positive_number,
        "screenshot-submit": _positive_number,
        "screenshot-syntax-style": directives.unchanged_required,
        "screenshot-title": directives.unchanged_required,
        "screenshot-typing": _positive_number,
        "screenshot-watermark": directives.unchanged_required,
        "screenshot-watermark-color": directives.unchanged_required,
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
    block's own code, highlighted by {mod}`click_extra.capture.snippet`.

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

    source_language: str | None = None
    """Language the source block is highlighted in, when it is not `language`.

    `None` for a directive showing code of the language it names: the source
    block of a `click:source` follows its `:language:` option. A directive that
    *runs* a block names the language of its results instead, so it states the
    language of the code producing them here, `python` for every runner of this
    package.
    """

    screenshots_source: bool = False
    """Whether a `:screenshot:` on this directive pictures the block's own code.

    `False` for a directive that runs something: what is worth committing there
    is the output, and the code producing it is on the page already. `True` for
    one that only declares code, which has no output to picture and whose
    subject is the code itself. See
    {meth}`~click_extra.sphinx.click.ClickDirective.screenshot_lines`.
    """

    show_source_by_default: bool = True
    """Whether to render the source code of the example in the code block."""
    show_results_by_default: bool = True
    """Whether to render the results of the example in the code block."""
    show_prompt_by_default: bool = True
    """Whether to draw the invocation above the results it produced."""

    runner_method: str
    """The name of the method to call on the per-document runner.

    A {class}`~click_extra.sphinx.click_runner.ClickRunner` for the `click:*`
    directives.
    """

    runner_attr: ClassVar[str] = "click_runner"
    """Name of the attribute holding the runner on the doctree.

    Subclasses (like `PythonDirective`)
    override this so the Click and Python runners don't collide on the same
    document.
    """

    runner_factory: ClassVar[type] = ClickRunner
    """Class to instantiate for the per-document runner.

    Called with the `capture` mode the `click_extra_run_capture` `conf.py` value
    resolves to, see {attr}`runner`.
    """

    @property
    def runner(self):
        """Get or create the per-document runner.

        Creates one runner per document, keyed by {attr}`runner_attr`.
        """
        runner = getattr(self.state.document, self.runner_attr, None)
        if runner is None:
            runner = self.runner_factory(
                capture=_resolve_run_capture(
                    getattr(self.env.config, RUN_CAPTURE_CONFIG),
                ),
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

    def _toggle(self, subject: str, default: bool) -> bool:
        """Resolve a `show-<subject>` / `hide-<subject>` option pair.

        The last one given wins, in the order the options were written. With
        neither, `default` answers.
        """
        value = default
        for option_id in self.options:
            if option_id == f"show-{subject}":
                value = True
            elif option_id == f"hide-{subject}":
                value = False
        return value

    @cached_property
    def show_source(self) -> bool:
        """Whether to show the source code of the example in the code block.

        The last occurrence of either `show-source` or `hide-source` options
        wins. If neither is set, the default is taken from `show_source_by_default`.
        """
        return self._toggle("source", self.show_source_by_default)

    @cached_property
    def show_results(self) -> bool:
        """Whether to show the results of running the example in the code block.

        The last occurrence of either `show-results` or `hide-results` options
        wins. If neither is set, the default is taken from `show_results_by_default`.
        """
        return self._toggle("results", self.show_results_by_default)

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
        return self._toggle("prompt", self.show_prompt_by_default)

    def evaluate(self, expression: str, subject: str) -> Any:
        """Evaluate `expression` in the runner namespace of the document.

        The namespace is the one the earlier blocks of the page filled, so an
        expression names what a `click:source` above built. `subject` opens the
        error, naming what asked for the evaluation: a directive, like
        `click:tree`, or one of its options, like `click:run: :screenshot-animate:`.

        :raises RuntimeError: when the expression cannot be evaluated.
        """
        try:
            return eval(expression, self.runner.namespace)
        except Exception as exc:
            raise RuntimeError(
                f"{subject}: failed to evaluate {expression!r}: {exc}",
            ) from exc

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
        lines = list(lines)
        if not lines:
            return block

        # Initiate the code block with its MyST or rST syntax. The MyST fence
        # outgrows any fence the lines hold, which would otherwise close it.
        fence = _code_fence(lines)
        code_directive = (
            f"{fence}{{code-block}}" if self.is_myst_syntax else ".. code-block::"
        )
        block.append(f"{code_directive} {language}")

        # Re-attach each option to the code block. An rST block indents its
        # options and body under the directive.
        indent = "" if self.is_myst_syntax else RST_INDENT
        block.extend(indent + line for line in self.code_block_options(target))

        # Both rST and MyST need a blank line before the body of the block else the
        # first line will be interpreted as a directive option or argument.
        block.append("")

        block.extend(indent + line for line in lines)

        # In MyST, we need to close the code block.
        if self.is_myst_syntax:
            block.append(fence)

        return block

    @cached_property
    def screenshot(self) -> str | None:
        """Name of the SVG capture this block renders to, without its extension.

        Set by the `:screenshot:` option. `None` when the block renders its
        results as a code block, which is the default.
        """
        return self.options.get("screenshot")  # type: ignore[no-any-return]

    @cached_property
    def screenshot_background(self) -> TerminalBackground:
        """Chrome the capture is drawn on, set by `:screenshot-background:`.

        Defaults to the dark chrome a terminal and this package's default theme
        both look like. A block rendering a light-background theme says so, or
        its capture washes out: see
        {class}`~click_extra.color.TerminalBackground`.
        """
        return self.options.get(  # type: ignore[no-any-return]
            "screenshot-background", TerminalBackground.DARK
        )

    @cached_property
    def screenshot_columns(self) -> TColumns:
        """Width the capture is laid out at, set by `:screenshot-columns:`.

        Defaults to the fixed width a terminal capture is taken at. `auto` sizes
        the image to the longest line the block printed, which is what a run
        holding a line Click does not wrap needs to keep on one line: a prompt,
        a wide table, a machine-readable dump.
        """
        return self.options.get(  # type: ignore[no-any-return]
            "screenshot-columns", DEFAULT_COLUMNS
        )

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
        - a sequence of {class}`~click_extra.capture.recording.Frame`, as a recording
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
        cannot, its frames being timed by the wall clock, so it is written once:
        {meth}`~click_extra.sphinx.click.ClickDirective.write_screenshot` leaves
        an asset that carries an `@recording` line alone.

        :return: the frames and how long each is shown, or `None` when the block
            draws a still.
        :raises RuntimeError: when the expression cannot be evaluated.
        :raises TypeError: when it yields neither a spinner nor strings.
        :raises ValueError: when a bare sequence of frames states no interval.
        """
        interval = self.options.get("screenshot-interval")
        subject = self.evaluate(expression, f"click:run: {option}")

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
        animation whose rows accumulate therefore numbers more of them as it
        goes. The gutter is as wide on every frame as on the tallest, so no row
        moves when the count gains a digit, see
        {func}`~click_extra.layout.number_frames`.

        :param frames: the animation's frames.
        :return: the same frames, each with a gutter, or unchanged.
        """
        if "screenshot-line-numbers" not in self.options:
            return frames
        return number_frames(frames)

    def screenshot_hold(self, fallback: THold) -> THold:
        """Seconds the last frame stays up, set by `:screenshot-hold:`.

        :param fallback: what to hold for when the block states nothing.
        :return: the pause, in seconds, or the `auto` sentinel.
        """
        return self.options.get(  # type: ignore[no-any-return]
            "screenshot-hold", fallback
        )

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
            or getattr(self.env.config, SCREENSHOT_SYNTAX_STYLE_CONFIG)
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
        {func}`~click_extra.capture.snippet.highlight_code` into the same ANSI a command
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
        rendered, its prompt first. `:screenshot-cursor:` draws a terminal
        cursor, in the shape it names or in the preset's own, and
        `:screenshot-blink:` says how long one blink takes. See
        {func}`~click_extra.capture.svg.render_svg`.

        A block naming no preset falls back to the one the
        `click_extra_screenshot_preset` `conf.py` value names, so a project
        drawing all of its captures as the same terminal states it once.
        """
        decoration = {
            name.replace("-", "_"): self.options[f"screenshot-{name}"]
            for name in (
                "backdrop",
                "border",
                "border-width",
                "margin",
                "opacity",
                "padding",
                "radius",
                "shadow",
                "watermark",
                "watermark-color",
            )
            if f"screenshot-{name}" in self.options
        }
        # Stated even when nothing asks for one, the renderer crediting
        # click-extra by default: an image a build rewrites and commits cannot
        # carry a release number without being rewritten by every release.
        decoration.setdefault(
            "watermark",
            getattr(self.env.config, SCREENSHOT_WATERMARK_CONFIG),
        )
        frame: dict[str, Any] = {
            name: self.options[f"screenshot-{name}"]
            for name in ("preset", "title")
            if f"screenshot-{name}" in self.options
        }
        frame["chrome"] = Chrome(**decoration)
        if "screenshot-cursor" in self.options:
            frame["cursor"] = Cursor(
                shape=self.options["screenshot-cursor"],
                blink=self.options.get("screenshot-blink", Cursor().blink),
            )
        default_preset = getattr(self.env.config, SCREENSHOT_PRESET_CONFIG)
        if default_preset and "preset" not in frame:
            if default_preset not in PRESETS:
                raise ValueError(
                    f"{SCREENSHOT_PRESET_CONFIG} names no terminal Click "
                    f"Extra knows: {default_preset!r} is not one of "
                    f"{', '.join(sorted(PRESETS))}."
                )
            frame["preset"] = PRESETS[default_preset]
        return frame

    @cached_property
    def invocation(self) -> str:
        """The command line the capture draws above itself, styled as a prompt.

        Set by `:screenshot-prompt:`, which states the line a reader would type
        rather than anything the block ran: a `click:run` block invokes a Python
        callable, so there is no argv to recover one from. Styled exactly as a
        still capture styles its own, see
        {func}`~click_extra.capture.screenshot.prompt_line`.

        ```{note}
        Animations only. A still block already prints its invocation, so the
        option would draw it twice; the animated paths are the ones holding
        what a command *drew* and nothing about the command line that drew it.
        ```

        :return: the styled line, empty when the block states none.
        """
        spec = self.options.get("screenshot-prompt")
        if not spec:
            return ""
        return prompt_line(
            (),
            prompt=spec,
            background=self.screenshot_background,
            preset=self.screenshot_frame.get("preset"),
        )

    def closed(self, frames: tuple[str, ...]) -> tuple[str, ...]:
        """Put the shell's prompt under the last frame, when asked.

        `:screenshot-closing-prompt:` draws the sigil on the row a finished
        command leaves the shell waiting on, see
        {func}`~click_extra.capture.screenshot.append_prompt`. The last frame alone
        carries it: the shell has not come back while the command is still
        drawing.

        :param frames: the animation's frames, in order.
        :return: the same frames, the last one closed, or unchanged.
        """
        if "screenshot-closing-prompt" not in self.options or not frames:
            return frames
        return (
            *frames[:-1],
            append_prompt(
                frames[-1],
                background=self.screenshot_background,
                preset=self.screenshot_frame.get("preset"),
            ),
        )

    def opened(
        self,
        frames: tuple[str, ...],
        interval: float | tuple[float, ...],
    ) -> tuple[tuple[str, ...], float | tuple[float, ...]]:
        """Draw the invocation over an animation, and type it when asked.

        A block records what a command *drew* and never the command line that
        drew it, so an animation opens on output arriving from nowhere.
        `:screenshot-prompt:` puts the line back over every frame, and
        `:screenshot-typing:` opens on it being typed, one character a frame,
        see {func}`~click_extra.capture.recording.type_line`.

        :param frames: the animation's frames, in order.
        :param interval: how long each is shown, one number for all alike.
        :return: the frames and their timing, both grown by the opening.
        """
        line = self.invocation
        if not line:
            return (tuple(frames), interval)
        frames = tuple(f"{line}\n{frame}" for frame in frames)
        typing = self.options.get("screenshot-typing")
        if not typing:
            return (frames, interval)
        opening = type_line(
            line,
            typing=typing,
            submit=self.options.get("screenshot-submit", DEFAULT_SUBMIT),
        )
        # A typed frame lasts a keystroke and the rest last whatever they were
        # given, so one number covering every frame alike no longer can: it is
        # spread over the frames it was standing for before the two are joined.
        if isinstance(interval, int | float):
            interval = (float(interval),) * len(frames)
        return (
            tuple(frame.text for frame in opening) + frames,
            tuple(frame.duration for frame in opening) + tuple(interval),
        )

    def render_animation(
        self,
        frames: tuple[str, ...],
        interval: float | tuple[float, ...],
        *,
        hold: THold,
        blank: float,
    ) -> str:
        """Draw an animated capture of `frames`, whatever produced them.

        The two animated paths agree on everything but what closes a cycle: a
        recording ends somewhere and pauses on that ending, while a declared
        animation turns in place and ends nowhere, so it pauses for nothing
        unless the block asks. Both fallbacks are overridden by
        `:screenshot-hold:` and `:screenshot-blank:`.

        :param frames: the animation's frames, in order.
        :param interval: how long each of them is shown.
        :param hold: seconds the last frame stays up when the block states none.
        :param blank: seconds of empty screen closing the cycle when the block
            states none.
        :return: the SVG document.
        """
        frames, interval = self.opened(self.closed(frames), interval)
        return render(
            columns=self.screenshot_columns,
            unique_id=self.screenshot,
            background=self.screenshot_background,
            frames=self.numbered(frames),
            emphasize=self.screenshot_emphasis(
                max(frame.count("\n") + 1 for frame in frames)
            ),
            interval=interval,
            hold=self.screenshot_hold(hold),
            blank=self.options.get("screenshot-blank", blank),
            speed=self.options.get("screenshot-speed", 1.0),
            **self.screenshot_frame,
        )

    def write_screenshot(self, results: Iterable[str]) -> None:
        """Write the captured output as an SVG beside the documentation.

        The file lands in the directory the `click_extra_screenshot_dir`
        `conf.py` value names, under the source root, so a README pointing at
        the repository embeds the very output this page renders live.

        This is a side effect, not a rendering: the page keeps its results code
        block, which stays selectable, searchable and theme-aware where an image
        would not be. Use `:mirror:` to put the image on the page as well.

        Writing during the build keeps the committed asset in step with the CLI
        without anyone remembering to refresh it. `unique_id` is pinned to the
        asset's name, so an unchanged CLI draws the same bytes, and the file is
        then left alone, its modification time included. Only the generator's
        release stamps and any output that varies by machine can change.

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
            / getattr(self.env.config, SCREENSHOT_DIR_CONFIG)
            / f"{self.screenshot}.svg"
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        recording = self.options.get("screenshot-record")
        if recording is not None:
            if path.exists() and animation_metadata(path.read_text(encoding="UTF-8")):
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
            _write_capture(
                path,
                self.render_animation(
                    frames,
                    interval,
                    hold=DEFAULT_RECORDING_HOLD,
                    blank=DEFAULT_RECORDING_BLANK,
                ),
            )
            return

        animation = self.screenshot_animation
        if animation is not None:
            frames, interval = animation
            _write_capture(
                path,
                self.render_animation(frames, interval, hold=0.0, blank=0.0),
            )
            return

        lines = self.screenshot_lines(results)
        if lines:
            lines = self.closed(("\n".join(lines),))[0].split("\n")
        if "screenshot-line-numbers" in self.options and lines:
            # Numbered whole, so line 1 is the first line the picture shows.
            lines = number_lines("\n".join(lines)).splitlines()
        _write_capture(
            path,
            render(
                "\n".join(lines),
                emphasize=self.screenshot_emphasis(len(lines)),
                columns=self.screenshot_columns,
                unique_id=self.screenshot,
                background=self.screenshot_background,
                palette=self.screenshot_palette,
                **self.screenshot_frame,
            ),
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
            language = self.source_language or self.language
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
    source_language = SourceDirective.default_language


def rewrite_screenshot_regions(
    text: str,
    directory: str = DEFAULT_SCREENSHOT_DIR,
) -> str:
    """Return `text` with every capture block's `:mirror:` region refreshed.

    Only a top-level `click:run`, `click:source`, `python:run` or
    `python:source` fence carrying both `:screenshot:` and `:mirror:` gets a
    region, holding the Markdown link to the capture. The walk, the insertion and
    the idempotency are those of
    {func}`click_extra.markdown.blocks.rewrite_fenced_regions`.

    The image itself is written by the directive at build time. This only
    maintains the Markdown pointing at it. The `click-extra refresh-directives`
    command calls it on each page, and {func}`update_screenshot_blocks` on each
    file it is given.
    """

    def link(inner: list[str]) -> list[str] | None:
        options, _content = split_options(inner)
        name = options.get("screenshot")
        if not name or "mirror" not in options:
            return None
        return [f"![{name}]({directory}/{name}.svg)"]

    return rewrite_fenced_regions(text, "screenshot", _CAPTURE_FENCE_OPEN_RE, link)


def update_screenshot_blocks(
    paths: Iterable[Path],
    *,
    check: bool = False,
    directory: str = DEFAULT_SCREENSHOT_DIR,
) -> list[Path]:
    """Refresh every capture block's `:mirror:` region in the given sources.

    See {func}`click_extra.markdown.blocks.update_blocks` for the walk, write, and
    `check`-mode contract. Unlike the `python:render` `:mirror:` refresher, this
    executes nothing: a region's content is derived from the block's
    `:screenshot:` name.

    :param paths: Markdown files, or directories recursed for `*.md`.
    :param check: report what would change without writing.
    :param directory: where the captures live, relative to each document.
    :return: the files whose regions were (or, under `check`, would be) updated.
    """

    def rewrite(text: str, path: Path) -> str:
        return rewrite_screenshot_regions(text, directory)

    return update_blocks(paths, rewrite, check=check)


cleanup_runner = make_cleanup(ClickDirective.runner_attr)
"""Drop the {class}`~click_extra.sphinx.click_runner.ClickRunner` from the doctree.

Connected to `doctree-read`, so it runs once the document is read.
"""
