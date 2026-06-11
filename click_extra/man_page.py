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
"""Generate roff/troff man pages from Click commands.

Produces one man page per command, mirroring the man-pages(7) section
structure documented in :doc:`/man-page`: NAME, SYNOPSIS, DESCRIPTION,
OPTIONS, COMMANDS, ENVIRONMENT, FILES and EXIT STATUS.

This is Click Extra's answer to the unmaintained `click-man
<https://github.com/click-contrib/click-man>`_ package. It improves on it by:

- working on a command *object* via :meth:`click.Command.make_context`, so it
  needs no ``console_scripts`` entry point;
- discovering subcommands dynamically through
  :meth:`click.Group.list_commands` / :meth:`click.Group.get_command` with a
  live context;
- honoring Click's ``\\b`` no-rewrap marker (rendered as roff ``.nf`` / ``.fi``);
- rendering boolean flags (``--foo`` / ``--no-foo``) and skipping hidden
  commands and options;
- mirroring Cloup option groups as ``.SS`` subsections of OPTIONS (ungrouped
  options fall under an ``Other options`` heading), matching the help screen;
- emitting ENVIRONMENT (from auto-generated env vars), FILES (from the
  ``--config`` search pattern) and EXIT STATUS sections that click-man never
  grew.

Font selection follows the man typographic convention encoded by
:data:`click_extra.theme.LITERAL_STYLES` / :data:`~click_extra.theme.REPLACEABLE_STYLES`:
literal tokens (command and option names) render bold (``\\fB``), replaceable
tokens (metavars, operands) render italic (``\\fI``).
"""

from __future__ import annotations

import inspect
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import click
from cloup import OptionGroupMixin

from .config import ConfigOption
from .envvar import param_envvar_ids
from .parameters import ExtraOption, search_params

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from click import Command, Context, Parameter


INLINE_LITERAL_RE = re.compile(r"``([^`]+?)``")
"""Match a reST inline literal (``"``...``"``) in a docstring.

Click stores docstrings verbatim, so any reST markup the author used to
render code-like tokens in HTML docs leaks into ``Command.help`` /
``Command.short_help``. The roff and HTML man-page paths translate these
matches into the bold/literal markers their renderers understand; the
Sphinx index directive translates them into ``nodes.literal``.
"""


def iter_inline_literals(text: str) -> Iterator[tuple[str, bool]]:
    """Walk ``text`` and yield ``(segment, is_literal)`` pairs.

    Split on :data:`INLINE_LITERAL_RE` so the consumer can apply
    different rendering to the literal segments (bold for roff, a
    ``literal`` node for docutils) without re-parsing the regex.
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


def full_short_help(command: click.Command) -> str:
    """Return the command's canonical one-line short help, untruncated.

    Click's :meth:`click.Command.get_short_help_str` truncates to 45
    characters by default with a trailing ``"..."`` so subcommand listings
    fit a terminal column. That bound is wrong for a man page: the NAME
    and COMMANDS sections in man-pages(7) carry the full description, and
    the man-page renderer (mandoc, groff, less) wraps text on its own.

    The lookup mirrors Click's order: an explicit ``short_help`` wins,
    otherwise the first paragraph of ``command.help`` is joined into one
    line. A truthy ``deprecated`` flag prepends ``(Deprecated)`` so the
    flag stays visible in both sections.
    """
    if command.short_help:
        text = command.short_help.strip()
    elif command.help:
        # Click already stores ``help`` after ``inspect.cleandoc``: split
        # on the first blank line to grab the leading paragraph, then
        # squash internal newlines so the result is one line.
        paragraph = command.help.split("\n\n", 1)[0]
        text = paragraph.strip().replace("\n", " ")
    else:
        text = ""
    if command.deprecated:
        text = f"(Deprecated) {text}".strip()
    return text


DEFAULT_EXIT_STATUS: tuple[tuple[str, str], ...] = (
    ("0", "Success."),
    (
        "1",
        "A runtime error, or an aborted prompt (Ctrl-C, a declined confirmation).",
    ),
    (
        "2",
        "A usage error: unknown option, invalid value, missing operand, or an "
        "unparsable configuration file.",
    ),
)
"""Conventional exit codes shared by every Click Extra CLI.

Mirrors the EXIT STATUS table in :doc:`/man-page`. Click returns ``2`` for
usage errors (``UsageError``), ``1`` for aborts, and ``0`` on success.
"""


# --- roff helpers -----------------------------------------------------------


def _roff_escape(text: str) -> str:
    """Escape inline text for roff.

    Backslashes become ``\\e`` first (so escapes added afterwards survive), then
    literal hyphens become ``\\-`` so they render as copy-pasteable minus signs
    rather than typographic hyphens (important for option names like
    ``--config``).
    """
    return text.replace("\\", "\\e").replace("-", "\\-")


def _roff_line(text: str) -> str:
    """Escape a whole output line, neutralizing a leading control character.

    A line starting with ``.`` or ``'`` is a roff control request; prefix such
    lines with the zero-width ``\\&`` so literal text is not mistaken for a
    macro.
    """
    escaped = _roff_escape(text)
    if escaped[:1] in (".", "'"):
        escaped = "\\&" + escaped
    return escaped


def _bold(text: str) -> str:
    """Wrap text in the roff bold font escape."""
    return f"\\fB{_roff_escape(text)}\\fR"


def _italic(text: str) -> str:
    """Wrap text in the roff italic font escape."""
    return f"\\fI{_roff_escape(text)}\\fR"


def _quote(text: str) -> str:
    """Quote a ``.TH`` header field, dropping any embedded double quotes."""
    return '"{}"'.format(text.replace('"', ""))


def _render_inline(text: str) -> str:
    """Render one line of Click help prose to a roff body line.

    Translates each reST inline literal (``"``...``"``) to a bold span
    (``\\fB...\\fR``); escapes plain prose with :func:`_roff_escape`;
    neutralizes a leading control character (``.`` or ``'``) the way
    :func:`_roff_line` does so the result is safe to emit between any
    other roff macros.
    """
    parts: list[str] = []
    for segment, is_literal in iter_inline_literals(text):
        parts.append(_bold(segment) if is_literal else _roff_escape(segment))
    rendered = "".join(parts)
    if rendered[:1] in (".", "'"):
        rendered = "\\&" + rendered
    return rendered


def _emit_help(text: str) -> list[str]:
    """Render Click help/description prose to roff body lines (no section macro).

    Click marks a no-rewrap region with a ``\\b`` (``\\x08``) control
    character: everything after the marker within the same paragraph is
    rendered verbatim. Each paragraph is therefore split into a filled
    prefix and a preformatted suffix, with ``.nf`` / ``.fi`` wrapping
    only the suffix. Paragraphs without a marker collapse to a single
    filled line, separated from the previous one by ``.PP``.
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
            # ``\b`` may sit on its own line: strip the surrounding
            # newlines so the .nf block is compact, but keep internal
            # line breaks so the no-fill region looks as written.
            post = post.strip("\n")
            if post:
                out.append(".nf")
                out.extend(_render_inline(line) for line in post.splitlines())
                out.append(".fi")
    return out


# --- structured man page ----------------------------------------------------


@dataclass
class ManOptionItem:
    """A single OPTIONS entry, extracted from a Click option."""

    names: tuple[str, ...]
    """All literal spellings: primary ``opts`` followed by ``secondary_opts``
    (so ``--foo`` / ``--no-foo`` boolean flags render both)."""

    metavar: str | None
    """The rendered metavar, or ``None`` for boolean flags (which take no value)."""

    is_choice: bool
    """Whether the option's type is a :class:`click.Choice`."""

    help: str | None
    """The option's help text, possibly carrying a ``\\b`` no-rewrap marker."""

    envvars: tuple[str, ...]
    """Environment variables read by the option, auto-generated one included."""

    required: bool
    """Whether the option is mandatory."""

    def to_roff(self) -> list[str]:
        """Render this option as a roff tagged paragraph (``.TP``)."""
        tag = " / ".join(_bold(name) for name in self.names)
        if self.metavar:
            tag += " " + _italic(self.metavar)
        lines = [".TP", tag]
        lines.extend(_emit_help(self.help or ""))
        if self.required:
            lines.append(".br")
            lines.append("[required]")
        return lines


@dataclass
class ManOptionGroup:
    """A titled cluster of OPTIONS entries, mirroring a Cloup option group.

    A plain Click command, or a Cloup command with no explicit
    ``@option_group``, yields a single group with ``title=None``: it renders as
    a flat OPTIONS list with no ``.SS`` subsection heading, identical to a man
    page that never grouped its options.
    """

    options: tuple[ManOptionItem, ...]
    """The option entries in this group."""

    title: str | None = None
    """The subsection heading, rendered as a roff ``.SS``. ``None`` for the
    implicit single group of an ungrouped command (no heading emitted)."""

    help: str | None = None
    """Optional group description, rendered as prose under the heading."""

    def to_roff(self) -> list[str]:
        """Render an optional ``.SS`` heading, group help, then the options."""
        lines: list[str] = []
        if self.title:
            lines.append(".SS " + _quote(self.title))
        if self.help:
            lines.extend(_emit_help(self.help))
        for option in self.options:
            lines.extend(option.to_roff())
        return lines


@dataclass
class ManPage:
    """A whole man page in structured form, ready to render to roff.

    One :class:`ManPage` maps to one command (or subcommand). Its fields are
    the man-pages(7) sections, in the order :doc:`/man-page` documents them.
    Build it with :func:`~click_extra.man_page.extract_manpage` and serialize with :meth:`to_roff`.
    """

    name: str
    """Full command path, space-joined (e.g. ``weather forecast``)."""

    short_help: str = ""
    """One-line description for the NAME section."""

    section: str = MAN_SECTION
    """Man section number."""

    synopsis_pieces: tuple[str, ...] = ()
    """Usage metavars after the command name (``[OPTIONS]``, ``CITY``, ...)."""

    description: str = ""
    """The command's full help text / docstring for the DESCRIPTION section."""

    operands: tuple[tuple[str, str], ...] = ()
    """Positional arguments as ``(metavar, help)`` pairs."""

    option_groups: tuple[ManOptionGroup, ...] = ()
    """The OPTIONS entries, partitioned into one or more groups. A command
    without explicit option groups carries a single untitled group."""

    subcommands: tuple[tuple[str, str], ...] = ()
    """For groups: ``(name, short_help)`` pairs for the COMMANDS section."""

    environment: tuple[tuple[str, str], ...] = ()
    """ENVIRONMENT entries as ``(variable_name, help)`` pairs."""

    files: tuple[str, ...] = ()
    """FILES entries (configuration search patterns)."""

    exit_status: tuple[tuple[str, str], ...] = DEFAULT_EXIT_STATUS
    """EXIT STATUS entries as ``(code, meaning)`` pairs."""

    version: str | None = None
    """Version string for the ``.TH`` header."""

    date: str = ""
    """Date for the ``.TH`` header (``YYYY-MM-DD``)."""

    manual: str | None = None
    """Manual name for the ``.TH`` header (the centered footer title)."""

    authors: str | None = None
    """AUTHORS section content, or ``None`` to omit the section."""

    copyright: str | None = None
    """COPYRIGHT section content, or ``None`` to omit the section."""

    @property
    def title(self) -> str:
        """The ``.TH`` page title: the command path, hyphen-joined and upper-cased."""
        return self.name.replace(" ", "-").upper()

    def to_roff(self) -> str:
        """Render the full man page as a roff/troff string."""
        lines: list[str] = [
            f'.\\" Generated by {_generator_tag()} <{CLICK_EXTRA_URL}>. '
            "Do not edit by hand.",
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
        # ``self.short_help`` is the author's docstring or explicit
        # ``short_help``: route it through ``_render_inline`` so inline
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

        if self.authors:
            lines.append(".SH AUTHORS")
            lines.extend(_emit_help(self.authors))

        if self.copyright:
            lines.append(".SH COPYRIGHT")
            lines.extend(_emit_help(self.copyright))

        return "\n".join(lines) + "\n"


# --- extraction -------------------------------------------------------------


def _resolve_date() -> str:
    """Resolve the man page date, honoring ``SOURCE_DATE_EPOCH`` for reproducible
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


def _generator_tag() -> str:
    """Provenance tag for the header comment: ``Click Extra <version>``.

    This is Click Extra's *own* version (the generator), not the documented
    CLI's version, which is carried by the ``.TH`` header instead. Falls back to
    the bare name when the distribution metadata is unavailable (e.g. running
    from an uninstalled source tree).
    """
    try:
        return f"Click Extra {metadata.version('click-extra')}"
    except metadata.PackageNotFoundError:
        return "Click Extra"


def _resolve_version(ctx: Context) -> str | None:
    """Best-effort version lookup via :mod:`importlib.metadata`.

    Pass ``version=`` to :func:`render_manpage` to override this.
    """
    for name in _distribution_names(ctx):
        if not name:
            continue
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return None


def _resolve_authors(ctx: Context) -> str | None:
    """Best-effort AUTHORS lookup from distribution metadata."""
    for name in _distribution_names(ctx):
        if not name:
            continue
        try:
            meta = metadata.metadata(name)
        except metadata.PackageNotFoundError:
            continue
        author = meta["Author"] or meta["Author-email"]
        if author:
            return author
    return None


def _config_default(config_option: ConfigOption, ctx: Context) -> str | None:
    """The portable, home-relative ``--config`` search pattern (as shown in help)."""
    return config_option.get_help_extra(ctx).get("default")


def _resolve_files(command: Command, ctx: Context) -> tuple[str, ...]:
    """FILES entries from the command's ``--config`` search pattern, if any.

    ``ConfigOption.default_pattern`` reads :func:`click.get_current_context`, so
    the context is entered when none is active (the build-time path); the live
    invocation context (the ``--man`` path) is reused as-is.
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


def _option_item(param: Parameter, ctx: Context) -> ManOptionItem:
    """Build a :class:`ManOptionItem` from a single Click option."""
    is_flag = bool(getattr(param, "is_flag", False))
    return ManOptionItem(
        names=tuple(param.opts) + tuple(param.secondary_opts),
        metavar=None if is_flag else param.make_metavar(ctx=ctx),
        is_choice=isinstance(param.type, click.Choice),
        help=getattr(param, "help", None),
        envvars=param_envvar_ids(param, ctx),
        required=param.required,
    )


def _build_option_groups(
    command: Command,
    ctx: Context,
    option_items: list[tuple[Parameter, ManOptionItem]],
) -> tuple[ManOptionGroup, ...]:
    """Partition extracted options into man-page OPTIONS subsections.

    Cloup commands expose explicit option groups: each visible one becomes a
    titled :class:`ManOptionGroup` (a roff ``.SS``), with the ungrouped
    remainder gathered under Cloup's default-group title (``Other options``),
    mirroring the ``--help`` screen. A command with no explicit
    ``@option_group`` collapses to a single untitled group, rendered as a flat
    list exactly as before.

    Group membership is matched by option identity, not name: Click Extra's
    ``--config`` / ``--no-config`` pair shares the ``config`` destination name,
    so a name-keyed lookup would drop one of them.
    """
    items_by_id = {id(param): item for param, item in option_items}

    if isinstance(command, OptionGroupMixin) and command.option_groups:
        explicit: list[ManOptionGroup] = []
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
                    ManOptionGroup(options=members, title=group.title, help=group.help)
                )
        ungrouped = tuple(
            item for param, item in option_items if id(param) not in claimed
        )
        if explicit:
            if ungrouped:
                title = command.get_default_option_group(ctx).title
                explicit.append(ManOptionGroup(options=ungrouped, title=title))
            return tuple(explicit)
        return (ManOptionGroup(options=ungrouped),) if ungrouped else ()

    items = tuple(item for _, item in option_items)
    return (ManOptionGroup(options=items),) if items else ()


def extract_manpage(
    command: Command,
    ctx: Context,
    *,
    version: str | None = None,
    date: str | None = None,
    manual: str | None = None,
    authors: str | None = None,
    copyright: str | None = None,
) -> ManPage:
    """Build a :class:`ManPage` from a Click command and its context.

    The context must have been created for ``command`` (e.g. via
    :meth:`click.Command.make_context` with ``resilient_parsing=True``), so
    that auto-generated environment-variable prefixes resolve correctly.
    """
    operands: list[tuple[str, str]] = []
    environment: list[tuple[str, str]] = []
    seen_envvars: set[str] = set()
    option_items: list[tuple[Parameter, ManOptionItem]] = []

    for param in command.get_params(ctx):
        if getattr(param, "hidden", False):
            continue

        if isinstance(param, click.Argument):
            operands.append((
                param.make_metavar(ctx=ctx),
                getattr(param, "help", None) or "",
            ))
            continue

        option_items.append((param, _option_item(param, ctx)))
        for var in param_envvar_ids(param, ctx):
            if var in seen_envvars:
                continue
            seen_envvars.add(var)
            environment.append((var, getattr(param, "help", None) or ""))

    subcommands: list[tuple[str, str]] = []
    if isinstance(command, click.Group):
        for sub_name in command.list_commands(ctx):
            sub = command.get_command(ctx, sub_name)
            if sub is None or getattr(sub, "hidden", False):
                continue
            subcommands.append((sub_name, full_short_help(sub)))

    return ManPage(
        name=ctx.command_path,
        short_help=full_short_help(command),
        synopsis_pieces=tuple(command.collect_usage_pieces(ctx)),
        description=command.help or "",
        operands=tuple(operands),
        option_groups=_build_option_groups(command, ctx, option_items),
        subcommands=tuple(subcommands),
        environment=tuple(environment),
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
    """Walk a command tree, yielding ``(path, command, context)`` for each
    visible command.

    Subcommands are discovered dynamically (:meth:`click.Group.list_commands` /
    :meth:`~click.Group.get_command`), so dynamically-registered commands are
    included. Hidden commands are skipped. Each context is built with
    ``resilient_parsing=True`` to avoid triggering required-argument errors,
    prompts, or eager-option side effects.
    """
    info_name = (prog_name or command.name or "") if not _path else (command.name or "")
    ctx = command.make_context(info_name, [], parent=_parent, resilient_parsing=True)
    path = _path + (info_name,)
    yield path, command, ctx

    if isinstance(command, click.Group):
        for sub_name in command.list_commands(ctx):
            sub = command.get_command(ctx, sub_name)
            if sub is None or getattr(sub, "hidden", False):
                continue
            yield from iter_command_contexts(sub, _parent=ctx, _path=path)


def render_manpage(
    command: Command,
    prog_name: str | None = None,
    ctx: Context | None = None,
    **overrides: str | None,
) -> str:
    """Render a single command's man page as a roff string.

    Reuses ``ctx`` when given (e.g. the live invocation context), otherwise
    builds a throwaway one with ``resilient_parsing=True``. Keyword overrides
    (``version``, ``date``, ``manual``, ``authors``, ``copyright``) are passed
    through to :func:`~click_extra.man_page.extract_manpage`.
    """
    if ctx is None:
        ctx = command.make_context(
            prog_name or command.name, [], resilient_parsing=True
        )
    return extract_manpage(command, ctx, **overrides).to_roff()


def render_manpages(
    command: Command,
    prog_name: str | None = None,
    **overrides: str | None,
) -> dict[str, str]:
    """Render the whole command tree, one man page per (sub)command.

    Returns an ordered mapping of ``{filename: roff}`` where each filename is
    the command path joined by hyphens plus the section suffix (e.g.
    ``weather-forecast.1``).
    """
    pages: dict[str, str] = {}
    for path, cmd, ctx in iter_command_contexts(command, prog_name):
        page = extract_manpage(cmd, ctx, **overrides)
        pages["{}.{}".format("-".join(path), page.section)] = page.to_roff()
    return pages


def write_manpages(
    command: Command,
    target_dir: str | Path,
    prog_name: str | None = None,
    **overrides: str | None,
) -> list[Path]:
    """Render the command tree and write each man page into ``target_dir``.

    Creates ``target_dir`` if missing. Returns the list of written paths.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, roff in render_manpages(command, prog_name, **overrides).items():
        path = target / filename
        path.write_text(roff, encoding="utf-8")
        written.append(path)
    return written


class ManOption(ExtraOption):
    """A pre-configured ``--man`` flag that prints the command's man page
    (roff) to stdout and exits.

    Eager and value-less, like :class:`~click_extra.parameters.ShowParamsOption`.
    Part of the default option set injected by
    :func:`~click_extra.commands.default_extra_params`, so every ``@extra_command``
    and ``@extra_group`` exposes it. Use
    :func:`@man_option <click_extra.decorators.man_option>` to add it to a plain
    Click CLI.

    .. note::
        The flag is named ``--man``, not ``--show-man`` or ``--man-page``.

        In the POSIX, GNU and BSD traditions a program does not emit its own man
        page through a flag: the page is a separate file read with ``man <prog>``,
        either hand-written (BSD ``mdoc``) or generated at build time from
        ``--help`` output (GNU ``help2man``). Click Extra already covers that
        build-time path with :func:`~click_extra.man_page.write_manpages`, its
        ``help2man`` equivalent.

        The one ecosystem that exposes a *runtime* flag is Perl's ``Pod::Usage``,
        whose convention is ``--help`` for the brief usage and bare ``--man`` for
        the full manual. ``--man`` also lines up with the neighbouring ``--help``
        and ``--version`` informational flags, which use bare nouns with no
        ``show-`` prefix. ``--show-man`` and ``--man-page`` have no precedent
        outside Click Extra.
    """

    def __init__(
        self,
        param_decls: tuple[str, ...] | None = None,
        is_flag: bool = True,
        expose_value: bool = False,
        is_eager: bool = True,
        help: str = "Show the command's man page (roff) and exit.",
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
        """Render and print the invoked command's man page, then exit."""
        if not value or ctx.resilient_parsing:
            return
        click.echo(render_manpage(ctx.command, ctx=ctx))
        ctx.exit()
