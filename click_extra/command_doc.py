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
"""Extract a Click command into a structured document and render it.

{func}`extract_command_doc` walks a command (and, through
{func}`iter_command_contexts`, its whole tree) into a {class}`CommandDoc`: one
extraction carrying the man-pages(7) sections documented in {doc}`/man-page`
(NAME, SYNOPSIS, DESCRIPTION, OPTIONS, COMMANDS, ENVIRONMENT, FILES and EXIT
STATUS). The model then renders to any of the {data}`HELP_FORMATS` backends:
roff ({meth}`CommandDoc.to_roff`), Markdown ({meth}`CommandDoc.to_markdown`)
and JSON ({meth}`CommandDoc.to_dict` / {meth}`CommandDoc.to_json`), with the
Carapace completion spec delegated to {mod}`click_extra.carapace`.

The roff backend is Click Extra's answer to the unmaintained [click-man](https://github.com/click-contrib/click-man) package. It improves on it by:

- working on a command *object* via {meth}`click.Command.make_context`, so it
  needs no `console_scripts` entry point;
- discovering subcommands dynamically through
  {meth}`click.Group.list_commands` / {meth}`click.Group.get_command` with a
  live context;
- honoring Click's `\\b` no-rewrap marker (rendered as roff `.nf` / `.fi`);
- rendering boolean flags (`--foo` / `--no-foo`) and skipping hidden
  commands and options;
- mirroring Cloup option groups as `.SS` subsections of OPTIONS (ungrouped
  options fall under an `Other options` heading), matching the help screen;
- emitting ENVIRONMENT (from auto-generated env vars), FILES (from the
  `--config` search pattern) and EXIT STATUS sections that click-man never
  grew.

Font selection follows the man typographic convention encoded by
{data}`click_extra.theme.LITERAL_STYLES` / {data}`~click_extra.theme.REPLACEABLE_STYLES`:
literal tokens (command and option names) render bold (`\\fB`), replaceable
tokens (metavars, operands) render italic (`\\fI`).
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from gettext import gettext as _
from importlib import metadata
from pathlib import Path

import click
from cloup import OptionGroupMixin

from . import context
from ._utils import generator_tag
from .accessibility import echo_via_pager
from .config import ConfigOption
from .envvar import param_envvar_ids
from .parameters import (
    ExtraOption,
    full_short_help,
    iter_params_for_display,
    iter_subcommands,
    make_resilient_context,
    option_value_kind,
    param_spellings,
    resolve_param_help,
    search_params,
)
from .version import resolve_author, resolve_distribution

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from typing import Any

    from click import Command, Context, Parameter


INLINE_LITERAL_RE = re.compile(r"``([^`]+?)``")
"""Match a reST inline literal (`"`...`"`) in a docstring.

Click stores docstrings verbatim, so any reST markup the author used to
render code-like tokens in HTML docs leaks into `Command.help` /
`Command.short_help`. The roff and HTML man-page paths translate these
matches into the bold/literal markers their renderers understand; the
Sphinx index directive translates them into `nodes.literal`.
"""


def iter_inline_literals(text: str) -> Iterator[tuple[str, bool]]:
    """Walk `text` and yield `(segment, is_literal)` pairs.

    Split on {data}`INLINE_LITERAL_RE` so the consumer can apply
    different rendering to the literal segments (bold for roff, a
    `literal` node for docutils) without re-parsing the regex.
    """
    pos = 0
    for match in INLINE_LITERAL_RE.finditer(text):
        if match.start() > pos:
            yield text[pos : match.start()], False
        yield match.group(1), True
        pos = match.end()
    if pos < len(text):
        yield text[pos:], False


CLICK_EXTRA_URL = "https://github.com/kdeldycke/click-extra"
"""Click Extra's home page, stamped into the provenance comment of every
generated man page so a reader of the raw roff knows where it came from."""


MAN_SECTION = "1"
"""Default man page section. Section 1 is for executable programs and shell
commands, which is what a Click CLI is."""


DEFAULT_EXIT_STATUS: tuple[tuple[str, str], ...] = (
    ("0", "Success."),
    (
        "1",
        "A runtime error, or an aborted prompt (Ctrl-C, a declined confirmation).",
    ),
    (
        "2",
        (
            "A usage error: unknown option, invalid value, missing operand, or an "
            "unparsable configuration file."
        ),
    ),
)
"""Conventional exit codes shared by every Click Extra CLI.

Mirrors the EXIT STATUS table in {doc}`/man-page`. Click returns `2` for
usage errors (`UsageError`), `1` for aborts, and `0` on success.
"""


# --- roff helpers -----------------------------------------------------------


def _roff_escape(text: str) -> str:
    """Escape inline text for roff.

    Backslashes become `\\e` first (so escapes added afterwards survive), then
    literal hyphens become `\\-` so they render as copy-pasteable minus signs
    rather than typographic hyphens (important for option names like
    `--config`).
    """
    return text.replace("\\", "\\e").replace("-", "\\-")


def _neutralize_leading_control(text: str) -> str:
    """Prefix a zero-width `\\&` when `text` starts with a roff control
    character (`.` or `'`) so it is not mistaken for a macro request.
    """
    if text[:1] in (".", "'"):
        return "\\&" + text
    return text


def _bold(text: str) -> str:
    """Wrap text in the roff bold font escape."""
    return f"\\fB{_roff_escape(text)}\\fR"


def _italic(text: str) -> str:
    """Wrap text in the roff italic font escape."""
    return f"\\fI{_roff_escape(text)}\\fR"


def _quote(text: str) -> str:
    """Quote a `.TH` header field, dropping any embedded double quotes."""
    return '"{}"'.format(text.replace('"', ""))


def _render_inline(text: str) -> str:
    """Render one line of Click help prose to a roff body line.

    Translates each reST inline literal (`"`...`"`) to a bold span
    (`\\fB...\\fR`); escapes plain prose with {func}`_roff_escape`;
    neutralizes a leading control character (`.` or `'`) so the result
    is safe to emit between any other roff macros.
    """
    parts: list[str] = []
    for segment, is_literal in iter_inline_literals(text):
        parts.append(_bold(segment) if is_literal else _roff_escape(segment))
    return _neutralize_leading_control("".join(parts))


def _emit_help(text: str) -> list[str]:
    """Render Click help/description prose to roff body lines (no section macro).

    Click marks a no-rewrap region with a `\\b` (`\\x08`) control
    character: everything after the marker within the same paragraph is
    rendered verbatim. Each paragraph is therefore split into a filled
    prefix and a preformatted suffix, with `.nf` / `.fi` wrapping
    only the suffix. Paragraphs without a marker collapse to a single
    filled line, separated from the previous one by `.PP`.
    """
    text = inspect.cleandoc(text).strip()
    if not text:
        return []

    out: list[str] = []
    for index, paragraph in enumerate(re.split(r"\n\s*\n", text)):
        if not paragraph.strip():
            continue
        if index > 0:
            out.append(".PP")
        pre, marker, post = paragraph.partition("\x08")
        pre = pre.strip()
        if pre:
            out.append(_render_inline(" ".join(pre.split())))
        if marker:
            # `\b` may sit on its own line: strip the surrounding
            # newlines so the .nf block is compact, but keep internal
            # line breaks so the no-fill region looks as written.
            post = post.strip("\n")
            if post:
                out.append(".nf")
                out.extend(_render_inline(line) for line in post.splitlines())
                out.append(".fi")
    return out


# --- examples ---------------------------------------------------------------


def normalize_examples(
    examples: Sequence[Sequence[str]] | None,
) -> tuple[tuple[str, str], ...]:
    """Validate and freeze a command's `examples` into `(description, command)` pairs.

    Accepts any sequence of two-item sequences, so a list of tuples and a list
    of lists (what a configuration file or a JSON payload would produce) are
    both fine. `None` and an empty sequence both yield an empty tuple.

    :raises TypeError: when an entry is not a pair of strings, naming the
        offending entry. Raised at command construction, so a malformed example
        surfaces on import rather than on the first `--help` a user runs.
    """
    if not examples:
        return ()
    normalized: list[tuple[str, str]] = []
    for entry in examples:
        if isinstance(entry, str) or len(tuple(entry)) != 2:
            raise TypeError(
                f"Example {entry!r} is not a (description, command) pair.",
            )
        description, command_line = entry
        if not isinstance(description, str) or not isinstance(command_line, str):
            raise TypeError(
                f"Example {entry!r} must hold two strings.",
            )
        normalized.append((description, command_line))
    return tuple(normalized)


# --- plain-prose helpers ----------------------------------------------------


def _clean_help(text: str) -> str:
    """Normalize Click help prose for the backends that carry newlines natively.

    Runs {func}`inspect.cleandoc` and drops Click's `\\b` (`\\x08`) no-rewrap
    marker, keeping every line break the marker protected. Markdown and JSON
    both represent those breaks on their own, so neither needs an equivalent of
    the roff `.nf` / `.fi` pair {func}`_emit_help` emits: only the control
    character has to go, or it lands in the output as a stray byte.
    """
    return inspect.cleandoc(text).replace("\x08\n", "").replace("\x08", "").strip()


def _markdown_help(text: str) -> list[str]:
    """Render Click help prose as Markdown block lines.

    Paragraphs are emitted as prose, with one exception: the region Click marks
    with `\\b` keeps its shape inside a fenced code block. That marker exists
    precisely because the author aligned something by hand (a table, a tree, a
    sample session), and Markdown would reflow it into a single line otherwise.
    """
    text = inspect.cleandoc(text).strip()
    if not text:
        return []

    out: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        if not paragraph.strip():
            continue
        if out:
            out.append("")
        pre, marker, post = paragraph.partition("\x08")
        pre = pre.strip()
        if pre:
            out.append(" ".join(pre.split()))
        if marker:
            post = post.strip("\n")
            if post:
                if pre:
                    out.append("")
                out.append("```text")
                out.extend(post.splitlines())
                out.append("```")
    return out


def _markdown_inline(text: str) -> str:
    """Collapse help prose to a single Markdown line, for list items and tables.

    Inline reST literals become Markdown code spans, mirroring what
    {func}`_render_inline` does for roff.
    """
    cleaned = " ".join(_clean_help(text).split())
    return "".join(
        f"`{segment}`" if is_literal else segment
        for segment, is_literal in iter_inline_literals(cleaned)
    )


# --- structured man page ----------------------------------------------------


@dataclass
class DocOptionItem:
    """A single OPTIONS entry, extracted from a Click option."""

    names: tuple[str, ...]
    """All literal spellings: primary `opts` followed by `secondary_opts`
    (so `--foo` / `--no-foo` boolean flags render both)."""

    metavar: str | None
    """The rendered metavar, or `None` when the option takes no value (boolean
    flags and counters)."""

    help: str | None
    """The option's help text, possibly carrying a `\\b` no-rewrap marker."""

    required: bool
    """Whether the option is mandatory."""

    optional_value: bool = False
    """Whether the option's value is optional (a bare flag is allowed). Rendered as
    the attached `[=METAVAR]` form instead of a space-separated metavar."""

    def to_roff(self) -> list[str]:
        """Render this option as a roff tagged paragraph (`.TP`)."""
        tag = " / ".join(_bold(name) for name in self.names)
        if self.metavar:
            if self.optional_value:
                # An optional value renders attached and bracketed
                # (`--color[=auto|always|never]`), the man convention for a flag
                # usable bare. Strip the metavar's own outer brackets, if any, so a
                # Choice does not double up.
                inner = self.metavar
                if inner.startswith("[") and inner.endswith("]"):
                    inner = inner[1:-1]
                tag += _italic("[=" + inner + "]")
            else:
                tag += " " + _italic(self.metavar)
        lines = [".TP", tag]
        lines.extend(_emit_help(self.help or ""))
        if self.required:
            lines.append(".br")
            lines.append("[required]")
        return lines

    @property
    def spec(self) -> str:
        """The option's spelling and value placeholder, as one plain string."""
        spec = " / ".join(self.names)
        if self.metavar:
            if self.optional_value:
                inner = self.metavar
                if inner.startswith("[") and inner.endswith("]"):
                    inner = inner[1:-1]
                spec += f"[={inner}]"
            else:
                spec += f" {self.metavar}"
        return spec

    def to_markdown(self) -> list[str]:
        """Render this option as a Markdown list item.

        A `\\b` no-rewrap region in the help becomes a fenced block indented
        under the item, rather than being folded into the sentence: the author
        aligned it on purpose, and a list item can carry a block as well as a
        paragraph can.
        """
        item = f"- `{self.spec}`"
        if self.required:
            item += " *(required)*"

        pre, _marker, post = (self.help or "").partition("\x08")
        help_text = _markdown_inline(pre)
        if help_text:
            item += f": {help_text}"
        lines = [item]

        post = inspect.cleandoc(post).strip("\n")
        if post:
            lines.append("")
            lines.append("  ```text")
            lines.extend(f"  {line}" for line in post.splitlines())
            lines.append("  ```")
            lines.append("")
        return lines

    def to_dict(self) -> dict[str, Any]:
        """Render this option as a JSON-serializable mapping."""
        return {
            "names": list(self.names),
            "spec": self.spec,
            "metavar": self.metavar,
            "help": _clean_help(self.help or "") or None,
            "required": self.required,
            "optional_value": self.optional_value,
        }


@dataclass
class DocOptionGroup:
    """A titled cluster of OPTIONS entries, mirroring a Cloup option group.

    A plain Click command, or a Cloup command with no explicit
    `@option_group`, yields a single group with `title=None`: it renders as
    a flat OPTIONS list with no `.SS` subsection heading, identical to a man
    page that never grouped its options.
    """

    options: tuple[DocOptionItem, ...]
    """The option entries in this group."""

    title: str | None = None
    """The subsection heading, rendered as a roff `.SS`. `None` for the
    implicit single group of an ungrouped command (no heading emitted)."""

    help: str | None = None
    """Optional group description, rendered as prose under the heading."""

    def to_roff(self) -> list[str]:
        """Render an optional `.SS` heading, group help, then the options."""
        lines: list[str] = []
        if self.title:
            lines.append(".SS " + _quote(self.title))
        if self.help:
            lines.extend(_emit_help(self.help))
        for option in self.options:
            lines.extend(option.to_roff())
        return lines

    def to_markdown(self, level: int = 3) -> list[str]:
        """Render an optional heading, group help, then the options."""
        lines: list[str] = []
        if self.title:
            lines.append("#" * level + " " + self.title)
            lines.append("")
        if self.help:
            lines.extend(_markdown_help(self.help))
            lines.append("")
        for option in self.options:
            lines.extend(option.to_markdown())
        return lines

    def to_dict(self) -> dict[str, Any]:
        """Render this group as a JSON-serializable mapping."""
        return {
            "title": self.title,
            "help": _clean_help(self.help or "") or None,
            "options": [option.to_dict() for option in self.options],
        }


@dataclass
class CommandDoc:
    """A whole man page in structured form, ready to render to roff.

    One {class}`CommandDoc` maps to one command (or subcommand). Its fields are
    the man-pages(7) sections, in the order {doc}`/man-page` documents them.
    Build it with {func}`~click_extra.command_doc.extract_command_doc` and serialize with {meth}`to_roff`.
    """

    name: str
    """Full command path, space-joined (like `weather forecast`)."""

    short_help: str = ""
    """One-line description for the NAME section."""

    section: str = MAN_SECTION
    """Man section number."""

    synopsis_pieces: tuple[str, ...] = ()
    """Usage metavars after the command name (`[OPTIONS]`, `CITY`, ...)."""

    description: str = ""
    """The command's full help text / docstring for the DESCRIPTION section."""

    operands: tuple[tuple[str, str], ...] = ()
    """Positional arguments as `(metavar, help)` pairs."""

    option_groups: tuple[DocOptionGroup, ...] = ()
    """The OPTIONS entries, partitioned into one or more groups. A command
    without explicit option groups carries a single untitled group."""

    subcommands: tuple[tuple[str, str], ...] = ()
    """For groups: `(name, short_help)` pairs for the COMMANDS section."""

    environment: tuple[tuple[str, str], ...] = ()
    """ENVIRONMENT entries as `(variable_name, help)` pairs."""

    files: tuple[str, ...] = ()
    """FILES entries (configuration search patterns)."""

    exit_status: tuple[tuple[str, str], ...] = DEFAULT_EXIT_STATUS
    """EXIT STATUS entries as `(code, meaning)` pairs."""

    examples: tuple[tuple[str, str], ...] = ()
    """EXAMPLES entries as `(description, command_line)` pairs.

    Collected from the command's own `examples` attribute (see
    {attr}`click_extra.commands.Command.examples`). Empty for a command that
    declares none, in which case every backend omits the section entirely.
    """

    version: str | None = None
    """Version string for the `.TH` header."""

    date: str = ""
    """Date for the `.TH` header (`YYYY-MM-DD`)."""

    manual: str | None = None
    """Manual name for the `.TH` header (the centered footer title)."""

    authors: str | None = None
    """AUTHORS section content, or `None` to omit the section."""

    copyright: str | None = None
    """COPYRIGHT section content, or `None` to omit the section."""

    @property
    def title(self) -> str:
        """The `.TH` page title: the command path, hyphen-joined and upper-cased."""
        return self.name.replace(" ", "-").upper()

    def to_roff(self) -> str:
        """Render the full man page as a roff/troff string."""
        lines: list[str] = [
            (
                f'.\\" Generated by {generator_tag()} <{CLICK_EXTRA_URL}>. '
                "Do not edit by hand."
            ),
            " ".join((
                ".TH",
                _quote(self.title),
                _quote(self.section),
                _quote(self.date),
                _quote(self.version or ""),
                _quote(self.manual or ""),
            )),
        ]

        lines.append(".SH NAME")
        name = _roff_escape(self.name)
        # `self.short_help` is the author's docstring or explicit
        # `short_help`: route it through `_render_inline` so inline
        # reST literals show up as bold instead of leaking through as
        # raw backticks rendered as quotes by mandoc.
        lines.append(
            f"{name} \\- {_render_inline(self.short_help)}" if self.short_help else name
        )

        lines.append(".SH SYNOPSIS")
        synopsis = _bold(self.name)
        if self.synopsis_pieces:
            synopsis += " " + " ".join(_italic(piece) for piece in self.synopsis_pieces)
        lines.append(synopsis)

        if self.description or self.operands:
            lines.append(".SH DESCRIPTION")
            lines.extend(_emit_help(self.description))
            for metavar, help_text in self.operands:
                lines.append(".TP")
                lines.append(_italic(metavar))
                lines.extend(_emit_help(help_text))

        if self.option_groups:
            lines.append(".SH OPTIONS")
            for group in self.option_groups:
                lines.extend(group.to_roff())

        if self.subcommands:
            lines.append(".SH COMMANDS")
            for sub_name, sub_help in self.subcommands:
                lines.append(".TP")
                lines.append(_bold(sub_name))
                lines.extend(_emit_help(sub_help))

        if self.environment:
            lines.append(".SH ENVIRONMENT")
            for var_name, help_text in self.environment:
                lines.append(".TP")
                lines.append(_bold(var_name))
                lines.extend(_emit_help(help_text))

        if self.files:
            lines.append(".SH FILES")
            for index, path in enumerate(self.files):
                if index > 0:
                    lines.append(".sp")
                lines.append(".nf")
                lines.append(_italic(path))
                lines.append(".fi")

        if self.exit_status:
            lines.append('.SH "EXIT STATUS"')
            for code, meaning in self.exit_status:
                lines.append(".TP")
                lines.append(_bold(code))
                lines.extend(_emit_help(meaning))

        if self.examples:
            lines.append(".SH EXAMPLES")
            for index, (description, command_line) in enumerate(self.examples):
                if index > 0:
                    lines.append(".PP")
                lines.extend(_emit_help(description))
                lines.append(".RS")
                lines.append(".nf")
                lines.append(_bold(_roff_escape(command_line)))
                lines.append(".fi")
                lines.append(".RE")

        if self.authors:
            lines.append(".SH AUTHORS")
            lines.extend(_emit_help(self.authors))

        if self.copyright:
            lines.append(".SH COPYRIGHT")
            lines.extend(_emit_help(self.copyright))

        return "\n".join(lines) + "\n"

    def to_markdown(self) -> str:
        """Render the whole document as Markdown.

        Same sections as {meth}`to_roff`, in the same order, minus the roff
        `.TH` header, whose date, section number and manual name describe a man
        page rather than the command. The version survives, as a line under the
        title.
        """
        lines: list[str] = [f"# {self.name}", ""]
        if self.short_help:
            lines.extend((_markdown_inline(self.short_help), ""))
        if self.version:
            lines.extend((f"Version `{self.version}`.", ""))

        synopsis = self.name
        if self.synopsis_pieces:
            synopsis += " " + " ".join(self.synopsis_pieces)
        lines.extend((
            "## Synopsis",
            "",
            "```shell-session",
            f"$ {synopsis}",
            "```",
            "",
        ))

        if self.description:
            lines.extend(("## Description", ""))
            lines.extend(_markdown_help(self.description))
            lines.append("")

        if self.operands:
            lines.extend(("## Arguments", ""))
            for metavar, help_text in self.operands:
                item = f"- `{metavar}`"
                rendered = _markdown_inline(help_text)
                lines.append(f"{item}: {rendered}" if rendered else item)
            lines.append("")

        if self.option_groups:
            lines.extend(("## Options", ""))
            for group in self.option_groups:
                lines.extend(group.to_markdown())
                lines.append("")

        if self.subcommands:
            lines.extend(("## Commands", ""))
            for sub_name, sub_help in self.subcommands:
                item = f"- `{sub_name}`"
                rendered = _markdown_inline(sub_help)
                lines.append(f"{item}: {rendered}" if rendered else item)
            lines.append("")

        if self.examples:
            lines.extend(("## Examples", ""))
            for description, command_line in self.examples:
                lines.extend((
                    _markdown_inline(description) + ":",
                    "",
                    "```shell-session",
                    f"$ {command_line}",
                    "```",
                    "",
                ))

        if self.environment:
            lines.extend(("## Environment variables", ""))
            for var_name, help_text in self.environment:
                item = f"- `{var_name}`"
                rendered = _markdown_inline(help_text)
                lines.append(f"{item}: {rendered}" if rendered else item)
            lines.append("")

        if self.files:
            lines.extend(("## Files", ""))
            lines.extend(f"- `{path}`" for path in self.files)
            lines.append("")

        if self.exit_status:
            lines.extend(("## Exit status", ""))
            for code, meaning in self.exit_status:
                lines.append(f"- `{code}`: {_markdown_inline(meaning)}")
            lines.append("")

        if self.authors:
            lines.extend(("## Authors", ""))
            lines.extend(_markdown_help(self.authors))
            lines.append("")

        if self.copyright:
            lines.extend(("## Copyright", ""))
            lines.extend(_markdown_help(self.copyright))
            lines.append("")

        # Collapse the trailing blank line each section leaves behind.
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, Any]:
        """Render the whole document as a JSON-serializable mapping.

        Subcommands are listed by name and one-line description only, never
        recursively: a consumer walking a deep tree asks for the child it cares
        about instead of paying for the whole tree at once. {func}`render_help`
        exposes the recursive variant separately, for the consumers that do want
        everything.
        """
        return {
            "name": self.name,
            "short_help": _clean_help(self.short_help) or None,
            "version": self.version,
            "synopsis": " ".join((self.name, *self.synopsis_pieces)),
            "description": _clean_help(self.description) or None,
            "arguments": [
                {"metavar": metavar, "help": _clean_help(help_text) or None}
                for metavar, help_text in self.operands
            ],
            "option_groups": [group.to_dict() for group in self.option_groups],
            "subcommands": [
                {"name": name, "short_help": _clean_help(help_text) or None}
                for name, help_text in self.subcommands
            ],
            "examples": [
                {"description": description, "command": command_line}
                for description, command_line in self.examples
            ],
            "environment": [
                {"variable": name, "help": _clean_help(help_text) or None}
                for name, help_text in self.environment
            ],
            "files": list(self.files),
            "exit_status": [
                {"code": code, "meaning": _clean_help(meaning)}
                for code, meaning in self.exit_status
            ],
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Serialize {meth}`to_dict` to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent) + "\n"


# --- extraction -------------------------------------------------------------


def _resolve_date() -> str:
    """Resolve the man page date, honoring `SOURCE_DATE_EPOCH` for reproducible
    builds (https://reproducible-builds.org/specs/source-date-epoch/)."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    when = (
        datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        if epoch
        else datetime.now(tz=timezone.utc)
    )
    return when.strftime("%Y-%m-%d")


def _distribution_names(ctx: Context) -> tuple[str, ...]:
    """Candidate distribution names to probe for version and author metadata."""
    root = ctx.find_root().info_name or ""
    return tuple(dict.fromkeys((root, root.replace("-", "_"), root.replace("_", "-"))))


def _resolve_version(ctx: Context) -> str | None:
    """Best-effort version lookup via {mod}`importlib.metadata`.

    Resolves the distribution from the program name (see
    {func}`_distribution_names`) and reads its version. Pass `version=` to
    {func}`render_manpage` to override this.
    """
    name = resolve_distribution(_distribution_names(ctx))
    return metadata.version(name) if name else None


def _resolve_authors(ctx: Context) -> str | None:
    """Best-effort AUTHORS lookup from distribution metadata.

    Resolves the distribution from the program name (see
    {func}`_distribution_names`) and reads its author(s) through the shared
    {func}`click_extra.version.resolve_author`, so `--man` and `--version`
    report the same author string (`Author` / `Maintainer` / email display
    name, in that order).
    """
    name = resolve_distribution(_distribution_names(ctx))
    return resolve_author(metadata.metadata(name)) if name else None


def _config_default(config_option: ConfigOption, ctx: Context) -> str | None:
    """The portable, home-relative `--config` search pattern (as shown in help)."""
    return config_option.get_help_extra(ctx).get("default")


def _resolve_files(command: Command, ctx: Context) -> tuple[str, ...]:
    """FILES entries from the command's `--config` search pattern, if any.

    `ConfigOption.default_pattern` reads {func}`click.get_current_context`, so
    the context is entered when none is active (the build-time path); the live
    invocation context (the `--man` path) is reused as-is.
    """
    config_option = search_params(command.params, ConfigOption)
    if not isinstance(config_option, ConfigOption):
        return ()
    try:
        if click.get_current_context(silent=True) is None:
            with ctx:
                default = _config_default(config_option, ctx)
        else:
            default = _config_default(config_option, ctx)
    # FILES is an optional section: any failure resolving the search pattern
    # (missing context, app-dir lookup errors, …) just drops it silently.
    except Exception:  # noqa: BLE001
        return ()
    if not default or default in ("disabled", "None"):
        return ()
    return (str(default),)


def _option_item(param: Parameter, ctx: Context) -> DocOptionItem:
    """Build a {class}`DocOptionItem` from a single Click option.

    The metavar follows {func}`~click_extra.parameters.option_value_kind`: a flag
    or counter takes no value (no metavar), an optional-value option renders the
    attached `[=METAVAR]` form, and a regular option a space-separated metavar.
    """
    kind = option_value_kind(param)
    return DocOptionItem(
        names=param_spellings(param),
        metavar=None if kind == "flag" else param.make_metavar(ctx=ctx),
        help=resolve_param_help(param, ctx),
        required=param.required,
        optional_value=kind == "optional",
    )


def _build_option_groups(
    command: Command,
    ctx: Context,
    option_items: list[tuple[Parameter, DocOptionItem]],
) -> tuple[DocOptionGroup, ...]:
    """Partition extracted options into man-page OPTIONS subsections.

    Cloup commands expose explicit option groups: each visible one becomes a
    titled {class}`DocOptionGroup` (a roff `.SS`), with the ungrouped
    remainder gathered under Cloup's default-group title (`Other options`),
    mirroring the `--help` screen. A command with no explicit
    `@option_group` collapses to a single untitled group, rendered as a flat
    list exactly as before.

    Group membership is matched by option identity, not name: Click Extra's
    `--config` / `--no-config` pair shares the `config` destination name,
    so a name-keyed lookup would drop one of them.
    """
    items_by_id = {id(param): item for param, item in option_items}

    if isinstance(command, OptionGroupMixin) and command.option_groups:
        explicit: list[DocOptionGroup] = []
        claimed: set[int] = set()
        for group in command.option_groups:
            claimed.update(id(opt) for opt in group.options)
            if group.hidden:
                continue
            members = tuple(
                items_by_id[id(opt)] for opt in group.options if id(opt) in items_by_id
            )
            if members:
                explicit.append(
                    DocOptionGroup(options=members, title=group.title, help=group.help)
                )
        ungrouped = tuple(
            item for param, item in option_items if id(param) not in claimed
        )
        if explicit:
            if ungrouped:
                title = command.get_default_option_group(ctx).title
                explicit.append(DocOptionGroup(options=ungrouped, title=title))
            return tuple(explicit)
        return (DocOptionGroup(options=ungrouped),) if ungrouped else ()

    items = tuple(item for _, item in option_items)
    return (DocOptionGroup(options=items),) if items else ()


def extract_command_doc(
    command: Command,
    ctx: Context,
    *,
    version: str | None = None,
    date: str | None = None,
    manual: str | None = None,
    authors: str | None = None,
    copyright: str | None = None,
) -> CommandDoc:
    """Build a {class}`CommandDoc` from a Click command and its context.

    The context must have been created for `command` (for example via
    {meth}`click.Command.make_context` with `resilient_parsing=True`), so
    that auto-generated environment-variable prefixes resolve correctly.
    """
    operands: list[tuple[str, str]] = []
    environment: list[tuple[str, str]] = []
    seen_envvars: set[str] = set()
    option_items: list[tuple[Parameter, DocOptionItem]] = []

    for param in iter_params_for_display(command, ctx):
        if getattr(param, "hidden", False):
            continue

        if isinstance(param, click.Argument):
            operands.append((
                param.make_metavar(ctx=ctx),
                resolve_param_help(param, ctx) or "",
            ))
            continue

        option_items.append((param, _option_item(param, ctx)))
        for var in param_envvar_ids(param, ctx):
            if var in seen_envvars:
                continue
            seen_envvars.add(var)
            environment.append((var, resolve_param_help(param, ctx) or ""))

    subcommands: list[tuple[str, str]] = [
        (name, full_short_help(sub)) for name, sub in iter_subcommands(command, ctx)
    ]

    return CommandDoc(
        name=ctx.command_path,
        short_help=full_short_help(command),
        synopsis_pieces=tuple(command.collect_usage_pieces(ctx)),
        description=command.help or "",
        operands=tuple(operands),
        option_groups=_build_option_groups(command, ctx, option_items),
        subcommands=tuple(subcommands),
        environment=tuple(environment),
        examples=normalize_examples(getattr(command, "examples", None)),
        files=_resolve_files(command, ctx),
        version=version if version is not None else _resolve_version(ctx),
        date=date if date is not None else _resolve_date(),
        manual=manual,
        authors=authors if authors is not None else _resolve_authors(ctx),
        copyright=copyright,
    )


def iter_command_contexts(
    command: Command,
    prog_name: str | None = None,
    _parent: Context | None = None,
    _path: tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], Command, Context]]:
    """Walk a command tree, yielding `(path, command, context)` for each
    visible command.

    Subcommands are discovered dynamically ({meth}`click.Group.list_commands` /
    {meth}`~click.Group.get_command`), so dynamically-registered commands are
    included. Hidden commands are skipped. Each context is built with
    `resilient_parsing=True` to avoid triggering required-argument errors,
    prompts, or eager-option side effects.
    """
    info_name = (prog_name or command.name or "") if not _path else (command.name or "")
    ctx = make_resilient_context(command, info_name, parent=_parent)
    path = _path + (info_name,)
    yield path, command, ctx

    for sub_name, sub in iter_subcommands(command, ctx):
        yield from iter_command_contexts(sub, _parent=ctx, _path=path)


def render_manpage(
    command: Command,
    prog_name: str | None = None,
    ctx: Context | None = None,
    **overrides: str | None,
) -> str:
    """Render a single command's man page as a roff string.

    Reuses `ctx` when given (like the live invocation context), otherwise
    builds a throwaway one with `resilient_parsing=True`. Keyword overrides
    (`version`, `date`, `manual`, `authors`, `copyright`) are passed
    through to {func}`~click_extra.command_doc.extract_command_doc`.
    """
    if ctx is None:
        ctx = make_resilient_context(command, prog_name or command.name)
    return extract_command_doc(command, ctx, **overrides).to_roff()


def render_manpages(
    command: Command,
    prog_name: str | None = None,
    **overrides: str | None,
) -> dict[str, str]:
    """Render the whole command tree, one man page per (sub)command.

    Returns an ordered mapping of ``{filename: roff}`` where each filename is
    the command path joined by hyphens plus the section suffix (like
    `weather-forecast.1`).
    """
    pages: dict[str, str] = {}
    for path, cmd, ctx in iter_command_contexts(command, prog_name):
        page = extract_command_doc(cmd, ctx, **overrides)
        pages["{}.{}".format("-".join(path), page.section)] = page.to_roff()
    return pages


def write_manpages(
    command: Command,
    target_dir: str | Path,
    prog_name: str | None = None,
    **overrides: str | None,
) -> list[Path]:
    """Render the command tree and write each man page into `target_dir`.

    Creates `target_dir` if missing. Returns the list of written paths.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, roff in render_manpages(command, prog_name, **overrides).items():
        path = target / filename
        path.write_text(roff, encoding="utf-8")
        written.append(path)
    return written


def install_manpages(
    command: Command,
    prog_name: str | None = None,
    **overrides: str | None,
) -> list[Path]:
    """Write the command tree's man pages where `man` can find them.

    Targets `$XDG_DATA_HOME/man/man1` when that variable is set, else
    {data}`MAN_INSTALL_DIR`. Returns the written paths.

    The environment is read here rather than at import time, so a caller that
    sets `XDG_DATA_HOME` for one invocation (a test, a packaging script staging
    into a build root) is honored. This mirrors
    {func}`~click_extra.carapace.install_carapace_spec`, whose spec directory
    resolves the same way.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    target = Path(xdg).expanduser() / "man" / "man1" if xdg else MAN_INSTALL_DIR
    return write_manpages(command, target, prog_name, **overrides)


HELP_FORMATS: dict[str, str] = {
    "carapace": (
        "Carapace completion spec (YAML). Doubles as a command-and-flag tree, "
        "and is the shape `carapace` itself consumes. Needs the `yaml` extra."
    ),
    "json": (
        "This command as a JSON object: usage, description, arguments, options "
        "grouped as the help screen groups them, environment variables, files, "
        "exit codes, and its direct subcommands by name."
    ),
    "json-full": (
        "Every command of the tree as JSON, under a `commands` array, each entry "
        "in the `json` shape."
    ),
    "markdown": "This command as a Markdown document, one section per topic.",
    "markdown-full": (
        "Every command of the tree as one Markdown document, in tree order."
    ),
    "man": (
        "This command as a man page: the roff source a packager installs, which "
        "`--man` typesets for reading."
    ),
}
"""The formats {func}`render_help` renders, mapped to their one-line description.

Ordered alphabetically, which is also the order `--help-format` advertises them
in. Adding a format is an entry here plus a branch in {func}`render_help`: no new
flag, no wider help screen. See {doc}`/man-page` for what each one is good for.

```{note}
The distinction the plain and `-full` variants draw is progressive disclosure.
A plain render describes one command and names its children, so a reader (a
tool or an agent, typically) descends one level at a time instead of pulling a
whole tree into a context window to answer a question about one leaf. The
`-full` variants exist for the opposite job: generating documentation, or
diffing a CLI's whole surface between two releases.
```
"""

INSTALLABLE_FORMATS: frozenset[str] = frozenset({"carapace", "man"})
"""The formats with a canonical place on disk their consumer reads them from.

A man page under a `man` directory, a Carapace spec under Carapace's. These are
the two renderings that are *installed* rather than read, which is what lets
`click-extra wrap` offer them a destination (`--output-dir`, `--install`) and
refuse one to the others. A JSON or Markdown document has no such place: nothing
goes looking for it, so stdout and a shell redirection are the whole story.
"""


def render_help(
    command: Command,
    help_format: str,
    prog_name: str | None = None,
    ctx: Context | None = None,
    **overrides: str | None,
) -> str:
    """Render *command* in one of the {data}`HELP_FORMATS`.

    Reuses `ctx` when given (like the live invocation context), otherwise builds
    a throwaway one with `resilient_parsing=True`, exactly like
    {func}`render_manpage`. Keyword overrides are passed through to
    {func}`extract_command_doc`, and ignored by the `carapace` format, which carries
    no version or authorship of its own.

    :raises ValueError: on an unknown format, listing the known ones.
    """
    if help_format not in HELP_FORMATS:
        known = ", ".join(sorted(HELP_FORMATS))
        raise ValueError(f"Unknown help format {help_format!r}. Pick one of: {known}.")

    if help_format == "carapace":
        # Imported here rather than at module level: click_extra.carapace reaches
        # click_extra.commands, which imports this module for ManOption.
        from .carapace import dump_carapace_spec

        # A spec is keyed on the binary name a shell completes, never on the
        # invocation a synopsis line prints. `prog_name` carries the latter for
        # the document formats (`click-extra wrap` hands it a whole script path),
        # so narrow it to the last word here. A spec named after a path binds to
        # nothing, and does so silently.
        return dump_carapace_spec(
            command,
            prog_name=command.name or (prog_name.split()[-1] if prog_name else None),
        )

    if help_format.endswith("-full"):
        pages = [
            extract_command_doc(cmd, sub_ctx, **overrides)
            for _path, cmd, sub_ctx in iter_command_contexts(command, prog_name)
        ]
        if help_format == "json-full":
            return (
                json.dumps({"commands": [page.to_dict() for page in pages]}, indent=2)
                + "\n"
            )
        return "\n".join(page.to_markdown() for page in pages)

    if ctx is None:
        ctx = make_resilient_context(command, prog_name or command.name)
    page = extract_command_doc(command, ctx, **overrides)
    if help_format == "json":
        return page.to_json()
    if help_format == "markdown":
        return page.to_markdown()
    return page.to_roff()


MAN_FORMATTERS: tuple[tuple[str, ...], ...] = (
    ("groff", "-man", "-Tutf8", "-rLL={width}n", "-P-c"),
    ("mandoc", "-Tutf8", "-Owidth={width}"),
)
"""Commands able to typeset roff into readable terminal text, best first.

Each entry is an argv template read on stdin, with `{width}` filled from the
terminal. `groff` is the GNU implementation found nearly everywhere a man page
is; `mandoc` covers the BSDs and Alpine, which ship it instead.

```{note}
`-P-c` hands `-c` down to `grotty`, groff's terminal driver, pinning the
emphasis it produces to the character-backspace pairs {data}`OVERSTRIKE_RE`
matches and {func}`read_manpage` strips under `--accessible`. Left to its own
default a `grotty` recent enough writes SGR escape sequences instead, which
that regular expression cannot see: the manual then reaches a screen reader
with its emphasis intact, and loses it altogether once the output is not a
terminal and the codes are stripped as color. `mandoc` needs no counterpart:
it overstrikes already.
```

```{note}
The `man` binary is deliberately not in this list, even though it is the tool
being imitated. Reading roff from stdin is where the implementations diverge:
GNU `man` takes `-l -`, while the BSD one wants a real file path. Driving the
typesetter directly sidesteps a portability problem that buys nothing, since
paging is handled here anyway.
```
"""

MAN_INSTALL_DIR: Path = Path("~/.local/share/man/man1").expanduser()
"""Where `--install` writes man pages: the user's own section-1 directory.

The default of the [XDG base directory spec](https://specifications.freedesktop.org/basedir-spec/latest/), which
{func}`install_manpages` overrides from `XDG_DATA_HOME` when that is set. Some
systems do not carry this path in their `MANPATH`, in which case the pages land
correctly but `man` has to be told where to look.
"""


def format_manpage(roff: str, width: int | None = None) -> str | None:
    """Typeset *roff* into readable terminal text, or `None` if nothing can.

    Tries each entry of {data}`MAN_FORMATTERS` in turn and returns the output of
    the first that succeeds. Returns `None` when none of them is installed, which
    the caller is expected to degrade on rather than fail: a CLI that cannot find
    a typesetter is a CLI running somewhere that never had man pages to begin
    with (Windows, a slim container), and that is no reason for `--man` to error.

    :param roff: the man page source, as {meth}`CommandDoc.to_roff` renders it.
    :param width: line length in columns. Defaults to the terminal's own, so the
        result matches what `man` would have produced in the same window.
    """
    if width is None:
        width = shutil.get_terminal_size().columns
    for template in MAN_FORMATTERS:
        if not shutil.which(template[0]):
            continue
        argv = [arg.format(width=width) for arg in template]
        try:
            process = subprocess.run(
                argv,
                input=roff,
                capture_output=True,
                text=True,
                encoding="UTF-8",
                check=False,
            )
        except OSError:
            continue
        if process.returncode == 0 and process.stdout.strip():
            return process.stdout
    return None


OVERSTRIKE_RE = re.compile(r".\x08")
"""Match the character-backspace pairs a roff typesetter emits for emphasis.

A bold `N` is written `N\\x08N` and an underlined one `_\\x08N`, a convention
inherited from line printers that a pager still renders as bold and underline
today. Dropping the pair's first half leaves the plain character.
"""


def read_manpage(command: Command, ctx: Context | None = None) -> None:
    """Typeset a command's manual and send it to the pager.

    The reading counterpart of `--help-format man`, which emits the roff source
    a packager installs. Falls back to printing that source, with a warning
    naming what to install, when no typesetter is available: something on screen
    beats an error, and the source still carries every word of the manual.

    Under `--accessible` the emphasis is stripped and the pager bypassed
    ({func}`~click_extra.accessibility.echo_via_pager` streams instead). Both
    matter to the same reader: a pager is a cursor-driven takeover, and
    overstrike is worse than the ANSI codes accessible mode already removes,
    since a screen reader voices `N\\x08NA\\x08AM\\x08ME\\x08E` rather than
    skipping it.
    """
    roff = render_manpage(command, ctx=ctx)
    typeset = format_manpage(roff)
    if typeset is None:
        logging.getLogger("click_extra").warning(
            "No man page typesetter found (tried %s): printing the roff source "
            "instead. Install one to read the manual, or ask for the source on "
            "purpose with --help-format man.",
            ", ".join(template[0] for template in MAN_FORMATTERS),
        )
        click.echo(roff)
        return

    active_ctx = click.get_current_context(silent=True)
    if active_ctx is not None and context.get(active_ctx, context.ACCESSIBLE, False):
        typeset = OVERSTRIKE_RE.sub("", typeset)
    echo_via_pager(typeset)


class ManOption(ExtraOption):
    """A pre-configured `--man` flag that typesets the command's manual, pages
    it, and exits.

    Eager and value-less, like {class}`~click_extra.parameters.ShowParamsOption`.
    Part of the default option set injected by
    {func}`~click_extra.commands.default_params`, so every `@command`
    and `@group` exposes it. Use
    {func}`@man_option <click_extra.decorators.man_option>` to add it to a plain
    Click CLI.

    ```{note}
    The flag is named `--man`, not `--show-man` or `--man-page`.

    In the POSIX, GNU and BSD traditions a program does not emit its own man
    page through a flag: the page is a separate file read with `man <prog>`,
    either hand-written (BSD `mdoc`) or generated at build time from
    `--help` output (GNU `help2man`). Click Extra already covers that
    build-time path with {func}`~click_extra.command_doc.write_manpages`, its
    `help2man` equivalent.

    The one ecosystem that exposes a *runtime* flag is Perl's `Pod::Usage`,
    whose convention is `--help` for the brief usage and bare `--man` for
    the full manual. `--man` also lines up with the neighbouring `--help`
    and `--version` informational flags, which use bare nouns with no
    `show-` prefix. `--show-man` and `--man-page` have no precedent
    outside Click Extra.
    ```

    ```{note}
    That Perl convention is about *reading* a manual, and this flag used to
    print roff source instead, which nobody reads: it was a build artifact
    wearing a reader's name. It now typesets the page and sends it to the pager,
    the way `man` itself does, so the flag does what its tradition says.

    The source did not go away, it moved to where a build step looks for it:
    `--help-format man`, beside every other artifact this module renders. The
    two are one question apart. Do you want to read the manual, or to ship it?
    ```
    """

    def __init__(
        self,
        param_decls: tuple[str, ...] | None = None,
        is_flag: bool = True,
        expose_value: bool = False,
        is_eager: bool = True,
        help: str = _("Read the command's manual page and exit."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--man",)
        kwargs.setdefault("callback", self.print_man)
        super().__init__(
            param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )

    def print_man(self, ctx: Context, param: Parameter, value: bool) -> None:
        """Typeset the invoked command's manual, page it, then exit."""
        if not value or ctx.resilient_parsing:
            return
        read_manpage(ctx.command, ctx=ctx)
        ctx.exit()


class HelpFormatOption(ExtraOption):
    """A pre-configured `--help-format` option printing the command in one of the
    {data}`HELP_FORMATS` and exiting.

    Eager and value-taking, unlike its `--man` neighbour, which is the same
    renderer reached through a bare flag: `--man` is exactly
    `--help-format roff`, kept because a runtime manual flag has its own
    tradition (see {class}`ManOption`).

    ```{note}
    One option carrying a format, rather than one flag per format. A CLI's
    option list is the most expensive real estate in its help screen, and every
    reader pays for it whether or not they will ever export anything: a family
    of `--help-json`, `--help-markdown` and `--help-carapace` flags would widen
    the label column of every screen, forever, one line per format anyone ever
    adds. Here a new format costs an entry in {data}`HELP_FORMATS` and nothing
    on screen.
    ```

    ```{note}
    The rendered output is deliberately colorless whatever `--color` says.
    Every format here is meant to be piped into something (a file, a parser, a
    model), and ANSI escapes in a JSON string or a Markdown fence are noise to
    all of them. `--help` remains the colorized human view.
    ```
    """

    def __init__(
        self,
        param_decls: tuple[str, ...] | None = None,
        expose_value: bool = False,
        is_eager: bool = True,
        help: str = _("Render the command in the given format and exit."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--help-format",)
        kwargs.setdefault("callback", self.print_help_format)
        kwargs.setdefault("type", click.Choice(sorted(HELP_FORMATS)))
        super().__init__(
            param_decls,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )

    def print_help_format(
        self,
        ctx: Context,
        param: Parameter,
        value: str | None,
    ) -> None:
        """Render the invoked command in the requested format, then exit."""
        if not value or ctx.resilient_parsing:
            return
        click.echo(render_help(ctx.command, value, ctx=ctx), color=False)
        ctx.exit()
