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
"""Introspect CLI metadata at runtime and print a colored `--version` string.

{class}`VersionOption` gathers the executed CLI's metadata (module and
package names, distribution version, author and license, environment profile,
and the live Git state) and renders them through a customizable, colorized
message template.

Git fields (`git_branch`, `git_short_hash`, ...) are resolved at runtime by
shelling out to `git`, with three fallbacks for `git`-less environments: a
pre-baked `__<field>__` dunder in the CLI module or its package (injected before
build by {mod}`click_extra.prebake`), then a committed `.git_archival.json`
populated by `git archive`, then the commit an installer records for a
distribution installed from a Git URL. The resolvers behind each field live in
{mod}`click_extra.version_facts`.
"""

from __future__ import annotations

import copy
import inspect
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from functools import cached_property
from gettext import gettext as _
from pathlib import Path
from string import Formatter

import click
from click import echo, get_current_context

# CLI_ECOSYSTEM_PACKAGES is bound under a private name so this module does not
# offer a second public spelling of it: its canonical home is click_extra._utils.
from ._utils import (
    CLI_ECOSYSTEM_PACKAGES as _CLI_ECOSYSTEM_PACKAGES,
)
from .color import invocation_color, is_a_tty
from .context import ACCESSIBLE, _LazyMetaDict, get
from .layout import cell_width, pad_to
from .parameters import ExtraOption
from .styling import Style
from .theme import get_current_theme
from .version_facts import (
    GIT_RESOLVERS,
    archival_field,
    default_facts,
    direct_url_field,
    distribution_of,
    dunder_name,
    find_archival_file,
    find_git_root,
    read_archival,
    read_direct_url,
    resolve_author,
    resolve_license,
    run_git,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
    from importlib.metadata import PackageMetadata
    from types import FrameType, ModuleType
    from typing import Any, ClassVar, TypeAlias

    from click import Command
    from cloup.styling import IStyle

    Facts: TypeAlias = Mapping[str, str]
    """Label-to-value rows of a version screen, in the order they are drawn."""

logger = logging.getLogger(__name__)

MUTED = Style(fg="bright_black")
"""The recessive style of what a version message says beside its name and version.

The tagline and the fact labels of a {class}`VersionScreen` take it, and so do
the template fields that locate a build rather than identify it: the repository
path, the commit date, the build facts and the environment profile.
"""


def is_main_module(module_name: str) -> bool:
    """Is *module_name* a `__main__` entry point, of a package or of a script?

    An entry point is where the interpreter started: `python -m package`, a
    console script, or a compiled binary. It is never plumbing a stack walk
    lands on after running out of user frames, so it is exempt from
    `CLI_ECOSYSTEM_PACKAGES` even when it sits under one of those
    packages, as `click_extra.__main__` does in Click Extra's own binary.
    """
    return module_name == "__main__" or module_name.endswith(".__main__")


def _is_plumbing(module_name: str) -> bool:
    """Whether *module_name* is plumbing between a stack walk and the CLI.

    A module of `CLI_ECOSYSTEM_PACKAGES` is, unless it is an entry point
    {func}`is_main_module` recognizes.
    """
    top_level = module_name.partition(".")[0]
    return top_level in _CLI_ECOSYSTEM_PACKAGES and not is_main_module(module_name)


def theme_slot(slot: str) -> IStyle:
    """A style reading its palette slot off the active theme, on every call.

    The lookup happens at call time, so the message follows `--theme`,
    `CLICK_EXTRA_THEME` and the background-sniffing `auto` alike, and drops its
    color under the monochrome `manpage` palette. A style captured at import would
    paint every theme with one palette: the bright white program name of `dark` is
    white on white on a light terminal.

    {func}`~click_extra.theme.get_current_theme` answers with the colorless theme
    outside an invocation, and with a full palette inside one, so no slot can come
    back missing.
    """

    def apply(text: str) -> str:
        return getattr(get_current_theme(), slot)(text)  # type: ignore[no-any-return]

    return apply


def unstyled(text: str) -> str:
    """Identity style, for a segment left with no color of its own."""
    return text


@dataclass(frozen=True)
class VersionScreen:
    """A logo, and the facts to seat beside it, as `--version` should draw them.

    Owns the layout only. The artwork arrives already rendered, as a string or the
    lines of one, so a CLI is free to draw its mark however it likes, in ASCII line
    art, half-blocks or anything else, without this class knowing. Hand one to
    {class}`VersionOption` through its `screen` argument, or to a whole CLI through
    `default_params(screen=…)`.
    """

    logo: str | Sequence[str] | Callable[[], str | Sequence[str]]
    """The mark, pre-rendered, or a callable producing it. A string splits on newlines.

    A callable defers the rendering to the first `--version` that draws the
    screen, as {attr}`facts` does for its values: a mark painted by code, from
    an image say, then costs nothing to the invocations that never ask for it.
    """

    tagline: str = ""
    """One line under the program name. Omitted, with its blank line, when empty."""

    facts: Facts | Callable[[], Facts] = default_facts
    """Label-to-value rows under the tagline, or a callable producing them.

    A callable defers the work to render time, which matters when a value costs
    something to compute: a CLI counting plugins should not pay for that on every
    invocation just to have the number ready in case `--version` is asked for.
    """

    gutter: str = "   "
    """Blank columns between the mark and the facts, and between label and value."""

    def _artwork(self) -> list[str]:
        """The lines of the mark, as its renderer produced them."""
        logo = self.logo() if callable(self.logo) else self.logo
        return logo.split("\n") if isinstance(logo, str) else list(logo)

    def _block(self) -> tuple[tuple[str, ...], int]:
        """The mark's lines padded out to its width, and that width.

        Draws the mark once, a callable `logo` included, for both answers.
        """
        raw = self._artwork()
        width = max(map(cell_width, raw), default=0)
        return tuple(pad_to(line, width) for line in raw), width

    @property
    def lines(self) -> tuple[str, ...]:
        """The mark's lines, every one padded out to {attr}`width`.

        Padding here rather than asking for it is what lets a caller hand over
        whatever its renderer produced. Trailing blanks are invisible on a line by
        itself and ragged the moment anything is placed beside it, and a caller
        cannot repair that afterwards: {func}`~click_extra.layout.pad_to` is
        what measures a styled line right and closes the style it left open.
        """
        return self._block()[0]

    @property
    def width(self) -> int:
        """Columns the mark occupies, taken from its widest line."""
        return max(map(cell_width, self._artwork()), default=0)

    def rows(
        self, prog_name: str, version: str, styles: Mapping[str, IStyle | None]
    ) -> tuple[tuple[str, str], ...]:
        """The column of facts, as (plain, styled) pairs.

        Both forms are built together because the styled one cannot be measured: its
        escape sequences take columns that never reach the screen, and the plain twin
        is what {meth}`render` sizes the layout against.

        The program name and version take the same styles the plain message gives
        them, so the two renderings of `--version` cannot drift apart on color.
        """
        facts = self.facts() if callable(self.facts) else self.facts
        # One column per the longest label, so the values line up without anyone
        # having to declare a width that a later row could outgrow.
        label_width = max((len(label) for label in facts), default=0)

        def paint(field: str, text: str) -> str:
            style = styles.get(field)
            return style(text) if style else text

        header = [
            (
                f"{prog_name}, version {version}",
                paint("prog_name", prog_name)
                + ", version "
                + paint("version", version),
            ),
        ]
        if self.tagline:
            header.append((self.tagline, MUTED(self.tagline)))
        if facts:
            header.append(("", ""))
        return (
            *header,
            *(
                (
                    f"{label:<{label_width}}{self.gutter}{value}",
                    MUTED(f"{label:<{label_width}}") + self.gutter + value,
                )
                for label, value in facts.items()
            ),
        )

    def render(
        self, prog_name: str, version: str, styles: Mapping[str, IStyle | None]
    ) -> str | None:
        """Compose the mark and the facts into the screen, or decline to.

        The facts are centred against the mark's height, and either column may be
        the taller of the two: a line missing from one side simply renders blank.

        Returns `None` when the terminal is too narrow to seat the two columns side
        by side, leaving the caller to fall back rather than emit a wrapped mess. The
        threshold is measured off the facts actually built, since their widest row
        grows with whatever a CLI chose to report. A non-interactive stream reports
        `shutil`'s 80-column default, wide enough that a redirected-but-forced-color
        run still gets the screen it asked for.
        """
        rows = self.rows(prog_name, version, styles)
        logo, width = self._block()
        needed = width + len(self.gutter) + max(len(plain) for plain, _ in rows)
        if needed > shutil.get_terminal_size().columns:
            return None

        offset = max(0, (len(logo) - len(rows)) // 2)
        blank = " " * width
        lines = []
        for index in range(max(len(logo), offset + len(rows))):
            left = logo[index] if index < len(logo) else blank
            row = index - offset
            right = rows[row][1] if 0 <= row < len(rows) else ""
            lines.append(f"{left}{self.gutter}{right}".rstrip())
        # Open on a blank line: `--version` is often the tail of a noisier command (a
        # `uv run` resolving, a wrapper announcing itself), and the mark reads as part
        # of that noise when it starts flush against it.
        return "\n" + "\n".join(lines)


def colors_reach_output() -> bool:
    """Will ANSI codes survive all the way to the user's terminal?

    Resolves Click Extra's color tri-state, deferring to the output stream's TTY
    status on its `auto` default, exactly as `click.echo` does when it decides
    whether to strip the codes itself.

    ```{note}
    The stream probed is {data}`sys.stdout`, not Click's own resolution of it.
    `click.echo` reaches stdout through a private cached wrapper, which fixes the
    output encoding and delegates `isatty()` to the stream beneath it, so both
    answer alike. Click deprecates the public accessor of that wrapper,
    `click.get_text_stream()`.
    ```
    """
    color = invocation_color()
    if color is None:
        return is_a_tty(sys.stdout)
    return color


def template_segments(
    template: str,
) -> Iterator[tuple[str, str | None, str | None]]:
    """Split a version message template into its literal and field segments.

    Yields one `(literal, field_id, field)` triple per field of `template`, in
    order: the literal text before the field, the identifier the field resolves
    on the option (`module` for `{module.__name__}`, the part before any index
    or attribute), and the field as written, braces and format spec
    included. A doubled brace of a literal comes back single. Literal text left
    after the last field comes in a final triple carrying no field.
    """
    for literal, field_name, format_spec, conversion in Formatter().parse(template):
        if field_name is None:
            yield literal, None, None
            continue
        field = "{" + field_name
        if conversion:
            field += f"!{conversion}"
        if format_spec:
            field += f":{format_spec}"
        yield literal, re.split(r"[.\[]", field_name, maxsplit=1)[0], field + "}"


class VersionOption(ExtraOption):
    """Gathers CLI metadata and prints a colored version string.

    ```{note}
    This is **not a drop-in replacement** for the [standard `@click.version_option()` decorator](https://github.com/pallets/click/blob/cdab890/src/click/decorators.py#L421-L524).

    It addresses the following Click issues:

    - [click#2324](https://github.com/pallets/click/issues/2324),
      to allow its use with the declarative `params=` argument.

    - [click#2331](https://github.com/pallets/click/issues/2331),
      by distinguishing the module from the package.

    - [click#1756](https://github.com/pallets/click/issues/1756),
      by allowing path and Python version.
    ```
    """

    message: str = _("{prog_name}, version {version}")
    """Default message template used to render the version string."""

    template_fields: tuple[str, ...] = (
        "module",
        "module_name",
        "module_file",
        "module_version",
        "package_name",
        "package_version",
        "author",
        "license",
        "exec_name",
        "version",
        "git_repo_path",
        "git_branch",
        "git_long_hash",
        "git_short_hash",
        "git_date",
        "git_tag",
        "git_tag_sha",
        "git_distance",
        "git_dirty",
        "build_time",
        "build_os",
        "build_target",
        "build_target_arch",
        "prog_name",
    )
    """List of field IDs recognized by the message template."""

    default_styles: ClassVar[dict[str, IStyle]] = {
        "module_name": theme_slot("invoked_command"),
        "module_version": theme_slot("success"),
        "package_name": theme_slot("invoked_command"),
        "package_version": theme_slot("success"),
        "exec_name": theme_slot("invoked_command"),
        "version": theme_slot("success"),
        "git_repo_path": MUTED,
        "git_branch": Style(fg="cyan"),
        "git_long_hash": Style(fg="yellow"),
        "git_short_hash": Style(fg="yellow"),
        "git_date": MUTED,
        "git_tag": Style(fg="cyan"),
        "git_tag_sha": Style(fg="yellow"),
        "git_distance": theme_slot("success"),
        "git_dirty": Style(fg="red"),
        "build_time": MUTED,
        "build_os": MUTED,
        "build_target": MUTED,
        "build_target_arch": MUTED,
        "prog_name": theme_slot("invoked_command"),
    }
    """Default style for each template field.

    Fields absent from this mapping render with no style of their own and fall
    back to `message_style` (or no color when that is unset). User-provided
    `styles` are merged over these defaults.

    The name and version fields read their style off the active palette through
    {func}`~click_extra.version.theme_slot` rather than naming a color, so the
    message follows `--theme`. Under the default `dark` palette, `invoked_command`
    is bright white bold and `success` is green.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
        message: str | None = None,
        fields: Mapping[str, Any] | None = None,
        styles: Mapping[str, IStyle | None] | None = None,
        message_style: IStyle | None = None,
        screen: VersionScreen | None = None,
        is_flag: bool = True,
        expose_value: bool = False,
        is_eager: bool = True,
        help: str = _("Show the version and exit."),
        **kwargs: Any,
    ) -> None:
        """Preconfigured as a `--version` option flag.

        :param message: the message template to print, in [format string syntax](https://docs.python.org/3/library/string.html#format-string-syntax).
            Defaults to ``{prog_name}, version {version}``.

        :param fields: mapping of template field name to a forced value,
            overriding the value auto-computed for that field. Keys must be
            members of `template_fields` (for example
            ``{"version": "1.2.3"}``).

        :param styles: mapping of template field name to its `Style`, merged
            over `default_styles`. Pass `None` as a value to clear a
            field's default style. Keys must be members of `template_fields`.

        :param message_style: fallback style for the message literals and for
            any field that has no style of its own.

        :param screen: a {class}`~click_extra.version.VersionScreen` to draw instead
            of the one-line message, whenever the terminal can take it. Left unset,
            `--version` prints the one-line message.

        :raises TypeError: when a key of `fields` or `styles` names no template
            field.
        """
        if not param_decls:
            param_decls = ("--version",)

        if message is not None:
            self.message = message
        self.message_style = message_style
        self.screen = screen

        self._field_overrides: frozenset[str] = frozenset()
        """Fields the caller pinned, which no later resolution may reconsider.

        An override lands in the instance dict under the name of the
        `cached_property` it shadows, so nothing distinguishes the two by
        inspection. {meth}`reset_resolution` and {meth}`__deepcopy__` need the
        difference: they drop a resolved field and must keep a pinned one.
        """

        # A field value override shadows the cached_property of the same name.
        for field_id, field_value in (fields or {}).items():
            self.pin_field(field_id, field_value)

        # Per-field styles: class defaults overridden by user-provided styles.
        style_overrides = dict(styles or {})
        self._reject_unknown(style_overrides)
        self.styles: dict[str, IStyle | None] = {
            **self.default_styles,
            **style_overrides,
        }

        kwargs.setdefault("callback", self.print_and_exit)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )

    def pin_field(self, field_id: str, value: Any) -> None:
        """Pin a template field to a caller-supplied value.

        The value shadows the `cached_property` that would otherwise resolve
        the field, and is recorded so {meth}`reset_resolution` can tell the two
        apart. Every caller that pins a field goes through here: a bare
        `setattr` sets the value without the record, and the next reset then
        discards it.

        :param field_id: Name of the template field to pin.
        :param value: Value the field reports from now on.
        :raises TypeError: when `field_id` names no template field.
        """
        self._reject_unknown((field_id,))
        setattr(self, field_id, value)
        self._field_overrides = self._field_overrides | {field_id}

    def _reject_unknown(self, field_ids: Iterable[str]) -> None:
        """Raise on the first of *field_ids* that names no template field.

        :raises TypeError: naming the unknown field, and the known ones.
        """
        for field_id in field_ids:
            if field_id not in self.template_fields:
                msg = (
                    f"Unknown version field {field_id!r}."
                    f" Must be one of {self.template_fields}."
                )
                raise TypeError(msg)

    def _is_resolved(self, key: str) -> bool:
        """Whether the instance dict entry *key* holds a memoized resolution.

        A pinned field lands under the same name as the `cached_property` it
        shadows, but holds the caller's value: see {attr}`_field_overrides`.
        """
        return key not in self._field_overrides and isinstance(
            getattr(type(self), key, None), cached_property
        )

    def reset_resolution(self) -> None:
        """Drop every memoized field, so the next read resolves from scratch.

        The resolution chain starts on a stack walk, and the option is built
        once at decoration time, so the first read in a process fixes the
        answer for every later one. That is what a CLI wants: one invocation,
        one process, one walk.

        A documentation build breaks the assumption. It renders many commands
        in one process, and a render that carries no CLI frame (writing roff
        for a command tree, say) resolves the chain from a stack the walk
        cannot read. The wrong answer then stands for the rest of the build,
        and a later `--version` example publishes it. Clearing the memo hands
        the next reader its own walk, at the cost of repeating one.

        A field the caller pinned through `fields=` is not a resolution and
        survives: see {attr}`_field_overrides`.
        """
        for key in [key for key in self.__dict__ if self._is_resolved(key)]:
            del self.__dict__[key]

    def __deepcopy__(self, memo: dict[int, Any]) -> VersionOption:
        """Copy the option, dropping every memoized field value.

        {mod}`~click_extra.multicall` deep-copies a group's parameters to
        build each personality, and the memo cannot travel along: the
        `module` entry holds a module object `copy.deepcopy` cannot
        reconstruct, and a copy is a new option anyway, free to resolve its
        fields against its own invocations. The configuration state is carried
        over: message template, styles, screen, and the fields the caller
        pinned, which keep the caller's own objects.
        """
        cls = type(self)
        clone = cls.__new__(cls)
        memo[id(self)] = clone
        for key, value in self.__dict__.items():
            if self._is_resolved(key):
                continue
            if key not in self._field_overrides:
                value = copy.deepcopy(value, memo)
            setattr(clone, key, value)
        return clone

    @staticmethod
    def cli_frame() -> FrameType:
        """Returns the frame in which the CLI is implemented.

        Walks the execution stack from the innermost frame outwards, to find the
        package in which the user's CLI is implemented. The walk reads the module
        and the function name of each frame off the frame itself, with no source
        lookup: `--version` is eager, so every CLI pays for this walk at startup.

        Returns the frame itself. When every frame belongs to the Click ecosystem
        and none is an entry point, returns the outermost frame, which has no
        caller: {attr}`module` then defers to the module of the root command's
        callback.
        """
        # No runner exists until its module is imported, which test tooling does
        # and a CLI does not: importing it here would load it for every CLI.
        runner_class = getattr(sys.modules.get("click.testing"), "CliRunner", None)

        # Keep a list of all frames inspected for debugging.
        frame_chain: list[tuple[str | None, str]] = []

        candidate: FrameType | None = None
        frame = sys._getframe()
        while True:
            frame_name = frame.f_globals.get("__name__")
            func_name = frame.f_code.co_name
            frame_chain.append((frame_name, func_name))

            # The invoke() of a CliRunner, which tests drive a CLI with. The runner
            # of Click Extra subclasses the one of Click, so the walk goes on while
            # it meets one, to stop on the outermost.
            if (
                runner_class is not None
                and func_name == "invoke"
                and isinstance(frame.f_locals.get("self"), runner_class)
            ):
                candidate = frame
            # The frame past the outermost invoke() of a runner.
            elif candidate is not None:
                return candidate
            # A frame outside the Click ecosystem, or an entry point: the frame in
            # which the user's CLI is implemented. The ones in between are
            # plumbing, like the frames `@cached_property` adds.
            elif not (frame_name and _is_plumbing(frame_name)):
                return frame

            if frame.f_back is None:
                break
            frame = frame.f_back

        # The heuristics failed: every frame belongs to the Click ecosystem, and
        # none is an entry point. Fall back to the outermost frame in the stack, the
        # last one the walk visited.
        count_size = len(str(len(frame_chain)))
        for counter, (p_name, f_name) in enumerate(frame_chain):
            logger.debug(f"Frame {counter:<{count_size}} # {p_name}:{f_name}")
        logger.debug(
            "cli_frame heuristics exhausted, falling back to outermost frame: "
            f"{frame.f_globals.get('__name__')}:{frame.f_code.co_name}"
        )
        return frame

    @staticmethod
    def command_module(ctx: click.Context) -> ModuleType | None:
        """Returns the module implementing the root command's callback.

        The stack walk in {meth}`cli_frame` can only find the CLI when the CLI's
        own module is on the stack. That holds for a normal invocation, and for a
        `CliRunner` driven from the test module that declares the command, but not
        when a runner invokes a command it merely *imported*: the walk then finds
        no user frame at all and stops on the runner's own `invoke()`, inside the
        Click ecosystem.

        The Sphinx `click:run` directive is that shape: without this, a documented
        `--version` would render the version of the ecosystem package owning the
        runner in place of the CLI's own.

        A launcher is the other shape. A console script or a compiled binary whose
        entry point is a command object, like `orchard.cli:cli`, leaves no frame of
        that module on the stack: the walk ends on the launcher itself.

        A command's callback names its defining module directly and needs no
        stack, so it settles the case the walk cannot see. Returns `None` when the
        command has no callback (a bare {class}`click.Group`) or its module is not
        imported, leaving the walk's own answer in place.
        """
        callback = ctx.find_root().command.callback
        module_name = getattr(callback, "__module__", None)
        if not module_name:
            return None
        return sys.modules.get(module_name)

    @cached_property
    def module(self) -> ModuleType:
        """Returns the module in which the CLI resides."""
        frame = self.cli_frame()

        # The globals of a frame name its module, for the cost of a dictionary
        # lookup. `inspect.getmodule()` matches a frame by file name instead, and
        # scans every loaded module on its first call: it only gets asked about
        # code whose globals name no loaded module, like code run by `exec()`.
        name = frame.f_globals.get("__name__", "")
        module = sys.modules.get(name) or inspect.getmodule(frame)
        if not module:
            raise RuntimeError(f"Cannot find module of {frame!r}")

        # The walk can stop on a frame that only leads to the CLI. Defer then to
        # the module of the root command's callback, which needs no stack.
        #
        # A packageless `__main__` is such a frame when it launches a command
        # object of another module: a console script in a `bin/` folder, or the
        # runner Nuitka compiles for `--main-entry-point`. A standalone script
        # declares its command in that same `__main__`, and gets it back.
        #
        # Standard library code is such a frame too, as no CLI lives there. The
        # walk stops on it when a thread or an executor starts the command, like
        # `threading.Thread(target=cli.main)`.
        #
        # Ecosystem plumbing that no installed distribution provides is another
        # case: the walk ran out of user frames and stopped on the runner that
        # invoked an imported command. Both halves of that test matter. A runner
        # living in a real distribution (`click.testing`, `click_extra.testing`)
        # keeps its own module, which is what a CLI declared in the module driving
        # the runner relies on. Among runners, only one under a subpackage that
        # resolves to nothing (`click_extra.sphinx`, which the `click:run`
        # directive invokes through) reaches the fallback.
        #
        # Ecosystem plumbing with no caller is deferred whatever its distribution:
        # the walk ran out of frames and fell back to the outermost one. That is
        # the `main()` of a CLI started with no frame under it, like the target of
        # `_thread.start_new_thread()`, an `atexit` hook or a call from a C host.
        #
        # An entry point with a package is never deferred. The distribution test
        # cannot see it: a Nuitka binary ships no metadata at all, so
        # `distribution_of()` answers `None` for the CLI's own package too.
        # Click Extra's own binary resolves to `click_extra.__main__`, and trading
        # that for the callback's module costs it the {func}`is_main_module`
        # exemption `_package_dunder()` needs to read the pre-baked `__version__`
        # off the parent package.
        launcher = module.__name__ == "__main__" and not module.__package__
        stdlib = module.__name__.partition(".")[0] in sys.stdlib_module_names
        plumbing = _is_plumbing(module.__name__) and (
            frame.f_back is None or distribution_of(module.__package__) is None
        )
        if launcher or stdlib or plumbing:
            ctx = click.get_current_context(silent=True)
            if ctx is not None:
                from_command = self.command_module(ctx)
                if from_command is not None:
                    return from_command

        return module

    @cached_property
    def module_name(self) -> str:
        """Returns the full module name or `__main__`."""
        return self.module.__name__

    @cached_property
    def module_file(self) -> str | None:
        """Returns the module's file full path.

        `None` for a module with no file, like the `__main__` of `python -c`.
        """
        return getattr(self.module, "__file__", None)

    @cached_property
    def module_version(self) -> str | None:
        """Returns the string found in the local `__version__` variable.

        ```{hint}
        `__version__` is a convention from early Python packaging. It is not a
        standard variable and is not defined in the packaging PEPs.

        Prefer the `package_version` property below, which uses the standard
        library `importlib.metadata` API.

        Click's own `version_option` reads the package metadata only
        ([pallets/click#2598](https://github.com/pallets/click/issues/2598)).
        Click Extra reads `__version__` too, for the scripts and codebases that
        set it.
        ```
        """
        # First, try to get __version__ from the detected module.
        version = getattr(self.module, "__version__", None)

        # If not found, read it off the globals of the command's callback, for a
        # command defined in another context (like Sphinx documentation blocks, or
        # standalone scripts).
        if version is None:
            ctx = get_current_context(silent=True)
            callback = ctx.command.callback if ctx is not None else None
            version = getattr(callback, "__globals__", {}).get("__version__")

        # If still not found, read it off the package, whose `__init__.py` holds
        # it for a CLI that sits in a sibling module.
        if version is None:
            version = self._package_dunder("__version__")

        if version is not None and not isinstance(version, str):
            raise ValueError(
                f"Module version {version!r} expected to be a string or None."
            )
        return version

    @cached_property
    def package_name(self) -> str | None:
        """Returns the package name."""
        return self.module.__package__

    def _package_dunder(self, name: str) -> Any:
        """Read *name* off the package of the CLI module, or `None`.

        `__version__` and the dunders `click-extra prebake all` writes live in the
        `__init__.py` of the package, while the CLI usually sits in a module beside
        it, like `__main__` or `cli`.

        The package is read only when the walk found the CLI's own module: an entry
        point {func}`is_main_module` recognizes, or any module outside
        `CLI_ECOSYSTEM_PACKAGES`. A walk that stops on the `invoke()` of a
        `CliRunner` lands in the ecosystem, and reading the package there would
        report Click Extra's own values for the CLI under test.
        """
        if not self.package_name or _is_plumbing(self.module_name):
            return None
        parent = sys.modules.get(self.package_name)
        return getattr(parent, name, None) if parent else None

    @cached_property
    def _distribution_name(self) -> str | None:
        """{attr}`package_name`, an *import* name, resolved to the installed
        distribution name {mod}`importlib.metadata` looks up.

        See {func}`~click_extra.version_facts.distribution_of` for the resolution
        rules.
        """
        return distribution_of(self.package_name)

    @cached_property
    def package_version(self) -> str | None:
        """Returns the package version if installed.

        Resolved from the distribution name (see
        `_distribution_name`) via {func}`importlib.metadata.version`.
        Returns `None` if the package is not installed or cannot be
        resolved.
        """
        # Deferred import: keeps importlib.metadata off the startup path of every CLI.
        from importlib import metadata

        name = self._distribution_name
        return metadata.version(name) if name else None

    @cached_property
    def _package_metadata(self) -> PackageMetadata | None:
        """Returns the distribution's core metadata, or `None`.

        Reads the [core metadata](https://packaging.python.org/en/latest/specifications/core-metadata/)
        (`Author`, `License-Expression`, classifiers, ...) of the
        resolved distribution (see `_distribution_name`). Returns
        `None` when the package is not installed or cannot be resolved.
        """
        # Deferred import: keeps importlib.metadata off the startup path of every CLI.
        from importlib import metadata

        name = self._distribution_name
        return metadata.metadata(name) if name else None

    @cached_property
    def author(self) -> str | None:
        """Returns the package author(s) from its core metadata.

        See {func}`~click_extra.version_facts.resolve_author` for the fields read, in
        order. `None` if no author can be determined.
        """
        return resolve_author(self._package_metadata)

    @cached_property
    def license(self) -> str | None:
        """Returns the package license from its core metadata.

        See {func}`~click_extra.version_facts.resolve_license` for the fields read, in
        order. `None` if no license can be determined.
        """
        return resolve_license(self._package_metadata)

    @cached_property
    def exec_name(self) -> str:
        """User-friendly name of the executed CLI.

        Returns the module name. But if the module is a `__main__` entry point,
        returns the package name: `python -m` runs it as `__main__`, while a console
        script or a compiled binary imports it as `package.__main__`.

        If not packaged, the CLI is assumed to be a simple standalone script, and the
        returned name is the script's file name (including its extension). Code with
        no file, like a CLI run by `python -c`, keeps the `__main__` module name.
        """
        # The CLI has its own module.
        if not is_main_module(self.module_name):
            return self.module_name

        # The CLI module is a `__main__` entry-point, so returns its package name.
        if self.package_name:
            return self.package_name

        # The CLI is not packaged: it is a standalone script. Fallback to its
        # filename.
        if self.module_file:
            return os.path.basename(self.module_file)

        return self.module_name

    @cached_property
    def version(self) -> str | None:
        """Return the version of the CLI.

        Returns the module version if a `__version__` variable is set alongside the
        CLI in its module.

        Else returns the package version if the CLI is implemented in a package, using
        [importlib.metadata.version()](https://docs.python.org/3/library/importlib.metadata.html?highlight=metadata#distribution-versions).

        For development versions (containing `.dev`), automatically appends the Git
        short hash as a [PEP 440 local version identifier](https://peps.python.org/pep-0440/#local-version-identifiers), producing
        versions like `1.2.3.dev0+abc1234`. This helps identify the exact commit a
        dev build was produced from. When {attr}`git_short_hash` finds no commit,
        the plain dev version is returned.

        Versions that already contain a `+` (a pre-baked local version
        identifier, typically set at build time by CI pipelines) are returned as-is
        to avoid producing invalid double-suffixed versions like
        `1.2.3.dev0+abc1234+xyz5678`.
        """
        ver = self.module_version or self.package_version
        if ver and ".dev" in ver and "+" not in ver:
            git_hash = self.git_short_hash
            if git_hash:
                return f"{ver}+{git_hash}"
        return ver or None

    @property
    def _search_start(self) -> Path:
        """Where the walks for a Git repository and an archival file start.

        The directory of the CLI module, or the working directory for a module
        with no file, like the `__main__` of `python -c`. Read on each call
        rather than cached: the working directory is free to change between two.
        """
        if self.module_file:
            return Path(self.module_file).parent
        return Path.cwd()

    @cached_property
    def git_repo_path(self) -> Path | None:
        """Find the Git repository root directory.

        Walks up from `_search_start` to the first directory holding a `.git`
        entry: see {func}`~click_extra.version_facts.find_git_root`.
        """
        return find_git_root(self._search_start)

    def _get_prebaked(self, field_id: str) -> str | None:
        """Read a pre-baked `__<field_id>__` dunder of the CLI.

        Checks the CLI module, then its package, where `click-extra prebake all`
        writes the dunders: see {meth}`_package_dunder`. Returns the first
        non-empty string, otherwise `None`.
        """
        name = dunder_name(field_id)
        for value in (getattr(self.module, name, None), self._package_dunder(name)):
            # `isinstance` first so mypy narrows `value` from `Any` to `str`
            # for the return; the `and value` keeps only non-empty strings.
            if isinstance(value, str) and value:
                return value
        return None

    @cached_property
    def _archival_data(self) -> dict[str, str]:
        """Parsed `.git_archival.json` for the CLI, or an empty mapping.

        Found by walking up from the CLI module's directory (falling back to
        the current working directory). Only populated inside an archive
        produced by `git archive` (including GitHub's source tarballs),
        where git substitutes the `$Format:…$` placeholders. A normal
        checkout holds the raw placeholders and yields nothing here, so live
        `git` calls take precedence and this is consulted only as a fallback.
        """
        path = find_archival_file(self._search_start)
        return read_archival(path) if path else {}

    @cached_property
    def _direct_url_data(self) -> dict[str, Any]:
        """Parsed `direct_url.json` record of the CLI's distribution, or an empty
        mapping.

        Only a distribution installed from a URL carries one. A wheel that
        `uvx --from git+https://...` builds from a Git source ships no `.git`
        directory, no substituted `.git_archival.json`, and no pre-baked dunder
        unless the build ran `click-extra prebake`: this record is the one place
        left that names its commit.
        """
        return read_direct_url(self._distribution_name)

    def _resolve_uniform_git_field(self, field_id: str) -> str | None:
        """Resolve a `git_*` field through the shared precedence.

        A pre-baked `__<field_id>__` dunder first, then the live value from
        {data}`~click_extra.version_facts.GIT_RESOLVERS` (run inside
        {attr}`git_repo_path`), then the `.git_archival.json` fallback, then the
        `direct_url.json` record of an install from a Git URL. Both fallbacks
        answer `None` for a field they do not carry.

        Valid for every field in {data}`~click_extra.version_facts.GIT_RESOLVERS`
        but {attr}`git_tag_sha`, whose live value derives from a tag that may
        itself be pre-baked.
        """
        live = None
        if self.git_repo_path:
            live = GIT_RESOLVERS[field_id](self.git_repo_path)
        return (
            self._get_prebaked(field_id)
            or live
            or archival_field(self._archival_data, field_id)
            or direct_url_field(self._direct_url_data, field_id)
        )

    @cached_property
    def git_branch(self) -> str | None:
        """Returns the current Git branch name.

        Checks for a pre-baked `__git_branch__` dunder first, then
        `git rev-parse --abbrev-ref HEAD`, then `.git_archival.json`.
        """
        return self._resolve_uniform_git_field("git_branch")

    @cached_property
    def git_long_hash(self) -> str | None:
        """Returns the full Git commit hash.

        Checks for a pre-baked `__git_long_hash__` dunder first, then
        `git rev-parse HEAD`, then `.git_archival.json`, then the commit recorded
        for an install from a Git URL.
        """
        return self._resolve_uniform_git_field("git_long_hash")

    @cached_property
    def git_short_hash(self) -> str | None:
        """Returns the short Git commit hash.

        Checks for a pre-baked `__git_short_hash__` dunder first, then
        `git rev-parse --short HEAD`, then `.git_archival.json`, then the commit
        recorded for an install from a Git URL. Both fallbacks derive it from the
        first 7 characters of the full hash.

        ```{hint}
        The short hash is usually the first 7 characters of the full hash, but this
        is not guaranteed to be the case.

        But it is at least guaranteed to be unique within the repository, and
        a [minimum of 4 characters](https://git-scm.com/docs/git-config#Documentation/git-config.txt-coreabbrev).
        ```
        """
        return self._resolve_uniform_git_field("git_short_hash")

    @cached_property
    def git_date(self) -> str | None:
        """Returns the commit date in ISO format: `YYYY-MM-DD HH:MM:SS +ZZZZ`.

        Checks for a pre-baked `__git_date__` dunder first, then
        `git show -s --format=%ci HEAD`, then `.git_archival.json` (whose
        `node-date` is strict ISO 8601, like `2021-01-01T12:00:00+00:00`).
        """
        return self._resolve_uniform_git_field("git_date")

    @cached_property
    def git_tag(self) -> str | None:
        """Returns the Git tag pointing at HEAD, if any.

        Checks for a pre-baked `__git_tag__` dunder first, then
        `git describe --tags --exact-match HEAD`, then `.git_archival.json`.

        Returns `None` if HEAD is not at a tagged commit.
        """
        return self._resolve_uniform_git_field("git_tag")

    @cached_property
    def git_tag_sha(self) -> str | None:
        """Returns the commit SHA that the current tag points at.

        Checks for a pre-baked `__git_tag_sha__` dunder first, then
        `git rev-list -1` on the tag returned by {attr}`git_tag`, then
        `.git_archival.json`. Returns `None` if HEAD is not at a tag.
        """
        prebaked = self._get_prebaked("git_tag_sha")
        if prebaked:
            return prebaked
        tag = self.git_tag
        if tag and self.git_repo_path:
            live = run_git("rev-list", "-1", tag, cwd=self.git_repo_path)
            if live:
                return live
        return archival_field(self._archival_data, "git_tag_sha")

    @cached_property
    def git_distance(self) -> str | None:
        """Number of commits since the most recent tag, or `None`.

        Checks for a pre-baked `__git_distance__` dunder first, then parses
        `git describe --tags --long`, then falls back to
        `.git_archival.json`. `None` when no tag is reachable or Git is
        unavailable.
        """
        return self._resolve_uniform_git_field("git_distance")

    @cached_property
    def git_dirty(self) -> str | None:
        """Work-tree state: `"dirty"`, `"clean"` or `None`.

        Checks for a pre-baked `__git_dirty__` dunder first, then runs
        `git status --porcelain`. `None` when not in a Git repository or
        Git is unavailable. There is no `.git_archival.json` fallback: an
        archive has no work tree, so its state is unknowable.
        """
        return self._resolve_uniform_git_field("git_dirty")

    @cached_property
    def build_time(self) -> str | None:
        """When the distribution was built, as an RFC 3339 UTC timestamp.

        Reads the pre-baked `__build_time__` dunder, the only source of a build
        fact: see {data}`~click_extra.version_facts.BUILD_RESOLVERS` and
        {func}`~click_extra.version_facts.resolve_build_time`.
        """
        return self._get_prebaked("build_time")

    @cached_property
    def build_os(self) -> str | None:
        """The operating system the build ran on.

        Reads the pre-baked `__build_os__` dunder. See
        {func}`~click_extra.version_facts.resolve_build_os`.
        """
        return self._get_prebaked("build_os")

    @cached_property
    def build_target(self) -> str | None:
        """The platform a distribution built here installs on.

        Reads the pre-baked `__build_target__` dunder. See
        {func}`~click_extra.version_facts.resolve_build_target`.
        """
        return self._get_prebaked("build_target")

    @cached_property
    def build_target_arch(self) -> str | None:
        """The CPU architecture the build ran on.

        Reads the pre-baked `__build_target_arch__` dunder. See
        {func}`~click_extra.version_facts.resolve_build_target_arch`.
        """
        return self._get_prebaked("build_target_arch")

    @property
    def prog_name(self) -> str | None:
        """Return the name of the CLI, from Click's point of view.

        Get the [info_name](https://click.palletsprojects.com/en/stable/api/#click.Context.info_name) of
        the [root](https://click.palletsprojects.com/en/stable/api/#click.Context.find_root)
        command.

        ```{note}
        Unlike its siblings, this field is resolved on every access instead
        of being cached on the instance: it is the one template field whose
        value legitimately varies between invocations of the same option
        instance sharing a process. {mod}`~click_extra.multicall` dispatch
        relies on that, running one CLI under many names in sequence, and a
        `prog_name` passed to `main()` varies it without any multicall at
        all. A cached value would pin the first name seen forever.
        ```
        """
        if "_prog_name_override" in self.__dict__:
            override: str | None = self.__dict__["_prog_name_override"]
            return override
        return get_current_context().find_root().info_name

    @prog_name.setter
    def prog_name(self, value: str | None) -> None:
        """Pin a forced value, the way `fields={"prog_name": …}` does.

        Field overrides are applied with `setattr()`, and no instance `__dict__`
        entry can shadow a property: this setter takes the value instead.
        """
        self.__dict__["_prog_name_override"] = value

    def field_style(self, field_id: str | None = None) -> IStyle:
        """Style painting the *field_id* segment of a rendered message.

        A field carrying no style of its own falls back to `message_style`, and one
        left unset by the caller too renders bare. Call with no `field_id` for the
        style of the template's literal segments, which is `message_style` alone.
        """
        style = self.styles.get(field_id) if field_id else None
        return style or self.message_style or unstyled

    def colored_template(self, template: str | None = None) -> str:
        """Insert ANSI styles to a message template.

        Accepts a custom `template` as parameter, otherwise uses the default message
        defined on the Option instance.

        The template is linearized so the ANSI codes apply to its string segments:
        an ANSI directive cannot be nested within another, unlike a markup tag of
        HTML.
        """
        if template is None:
            template = self.message

        default_style = self.field_style()

        # A copy of the template, where literal and field segments are colored.
        colored_template = ""

        # Literals accumulate until the next field, so a run of them gets a single
        # style span. Their braces are re-escaped: the copy is a template too.
        literal_accu = ""
        for literal, field_id, field in template_segments(template):
            literal_accu += literal.replace("{", "{{").replace("}", "}}")
            if field is None:
                continue
            if literal_accu:
                colored_template += default_style(literal_accu)
                literal_accu = ""
            colored_template += self.field_style(field_id)(field)
        if literal_accu:
            colored_template += default_style(literal_accu)

        return colored_template

    def render_message(self, template: str | None = None) -> str:
        """Render the version string from the provided template.

        Accepts a custom `template` as parameter, otherwise uses the default
        `self.colored_template()` produced by the instance.

        A CLI carrying a {class}`~click_extra.version.VersionScreen` gets that
        drawn instead, whenever three conditions hold. Failing any one of them
        falls back to the plain template unchanged, which is a deliberate
        guarantee rather than a default: that form is the one every machine
        reader parses.

        - **Color reaches the output.** A flat-shaded mark carries its shape in its
          colors, and color is the one lever a caller already has. A redirected
          `--version`, or one run under `--no-color` or
          [`NO_COLOR`](https://no-color.org), is asking for something parseable.
        - **The terminal is wide enough** to seat the facts beside the mark without
          wrapping them.
        - **Accessible mode is off.** A mark read out character by character is
          noise to a screen reader, so `--accessible` keeps the plain message.
        """
        if template is None and self.screen is not None:
            ctx = click.get_current_context(silent=True)
            accessible = bool(ctx is not None and get(ctx, ACCESSIBLE, False))
            if not accessible and colors_reach_output():
                screen = self.screen.render(
                    str(self.prog_name or ""),
                    str(self.version or ""),
                    self.styles,
                )
                if screen is not None:
                    return screen

        if template is None:
            template = self.colored_template()

        # Only resolve fields that actually appear in the template, so unused
        # properties, the git calls above all, are never evaluated.
        used_fields = {
            field_id
            for _literal, field_id, _field in template_segments(template)
            if field_id is not None
        }
        return template.format(**{v: getattr(self, v) for v in used_fields})

    def print_debug_message(self) -> None:
        """Render in debug logs all template fields in color."""
        if not logger.isEnabledFor(logging.DEBUG):
            return

        # Double the braces: the label renders as a literal `{field_id}`, naming the
        # placeholder a template would write, rather than expanding it.
        labels = {field_id: f"{{{{{field_id}}}}}" for field_id in self.template_fields}
        max_len = max(map(len, labels.values()))

        logger.debug("Version string template variables:")
        for field_id, label in labels.items():
            logger.debug(
                self.render_message(
                    self.colored_template(f"{label:<{max_len}}: {{{field_id}}}")
                )
            )

    def print_and_exit(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Print the version string and exits.

        Also stores all version string elements in the Context's `meta` `dict`.
        """
        # Install a lazy dict so that version fields in ctx.meta are only
        # evaluated when actually accessed, sparing every invocation the git calls
        # and the metadata lookups.
        ctx._meta = _LazyMetaDict(ctx._meta, self, self.template_fields)

        # Eagerly resolve `module` now: cli_frame() relies on stack
        # inspection that only produces the correct result during the eager
        # callback. Once cached, all dependent properties (module_name,
        # package_name, etc.) will use this cached value regardless of when
        # they are accessed.
        self.module  # noqa: B018

        # Always log all template fields at DEBUG level, even if --version is
        # not called. This provides valuable execution context in bug reports.
        # The debug check inside the method ensures fields are only resolved
        # (and thus the lazy dict entries materialized) when DEBUG is active.
        self.print_debug_message()

        if not value or ctx.resilient_parsing:
            # Do not print the version and continue normal CLI execution.
            return

        echo(self.render_message(), color=ctx.color)
        ctx.exit()


def reset_version_resolution(command: Command) -> None:
    """Reset every {class}`VersionOption` in a command tree.

    Walks the tree once, cycle-safe, and calls
    {meth}`VersionOption.reset_resolution` on each option it finds.

    Written for a documentation build, which renders many commands in one
    process where a CLI renders one. See that method for what a stale
    resolution costs a published page.

    ```{note}
    The walk reads the subcommands each group has registered, rather than going
    through {func}`~click_extra.param_tools.iter_subcommand_contexts` like the
    renderers do. A lazy subcommand not imported yet holds no resolution to
    reset, and the context that function builds for each subcommand runs its
    `--version` callback, which resolves the very chain this function clears.
    ```
    """
    seen: set[int] = set()

    def walk(cmd: Command) -> None:
        if id(cmd) in seen:
            return
        seen.add(id(cmd))
        for param in cmd.params:
            if isinstance(param, VersionOption):
                param.reset_resolution()
        for sub in getattr(cmd, "commands", {}).values():
            walk(sub)

    walk(command)
