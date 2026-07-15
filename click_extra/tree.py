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
"""Render Click command hierarchies as trees.

Provides the ``--tree`` flag: a constant-cost overview of a CLI's nested
subcommands, where the only alternative is walking ``--help`` screens one
level at a time or generating a full man page or completion spec dump.

This is the command-level, hierarchical companion of ``--show-params``:
where the parameter table flattens the hierarchy into dotted ``id`` paths
(``cli.subcommand.param``), the tree renders the skeleton those paths hang
off. Both share the same dynamic discovery (:meth:`click.Group.list_commands`
/ :meth:`click.Group.get_command` via
:func:`~click_extra.parameters.iter_subcommands`) and the same one-line
descriptions (:func:`~click_extra.parameters.full_short_help`).

The tree is a human rendering only: machine-readable hierarchies are already
served by ``--show-params --table-format json`` (parameters with dotted
paths) and the Carapace exporter (:mod:`click_extra.carapace`, a YAML
command-and-flag tree).

Subcommands are discovered through a live-context walk, so lazily-registered
commands are included, and the view hides behind a dedicated eager flag, so
the plain help screen stays untouched. See :doc:`/upstream` for how this
compares to the tree views of neighboring packages.
"""

from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass
from gettext import gettext as _

import click
import cloup
from wcwidth import wcswidth

from . import context
from .parameters import (
    ExtraOption,
    full_short_help,
    iter_subcommands,
    make_resilient_context,
)
from .theme import get_current_theme

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TreeGlyphs:
    """The four drawing strings composing a tree's left-hand rail."""

    branch: str
    """Connector of a subcommand with siblings below it."""

    last: str
    """Connector of the last subcommand of its level."""

    pipe: str
    """Rail continuation under a :attr:`branch` connector."""

    space: str
    """Rail continuation under a :attr:`last` connector."""


BOX_GLYPHS = TreeGlyphs(branch="├── ", last="└── ", pipe="│   ", space="    ")
"""Unicode box-drawing rail, the same set drawn by ``tree(1)``.

The default table format (``rounded-outline``) already emits box-drawing
characters, so the tree matches the rest of Click Extra's terminal output.
"""

ASCII_GLYPHS = TreeGlyphs(branch="|-- ", last="`-- ", pipe="|   ", space="    ")
"""Pure-ASCII rail, the same set drawn by ``tree(1)`` under ``--charset=ascii``.

Selected when accessibility mode is active
(:data:`~click_extra.context.ACCESSIBLE`): box-drawing characters are hostile
to screen readers, which either skip them or spell out their Unicode names.
"""

COLUMN_GAP = 2
"""Blank cells between the tree rail column and the description column."""

MIN_DESCRIPTION_WIDTH = 20
"""Floor for the description column's wrap width.

A deep tree with long labels can push the description column close to (or
past) the terminal's right edge. Below this floor, wrapping would shred
sentences into confetti, so the column keeps this width and overflows the
terminal instead.
"""


def _command_labels(
    command: click.Command,
    name: str,
    ctx: click.Context,
    style_name: Callable[[str], str],
) -> tuple[str, str]:
    """Build the plain and styled labels of a tree node.

    The label is the command *name*, followed by its parenthesized aliases when
    the command declares any (a Cloup feature), mirroring the group help-screen
    listing (like ``wrap (run)``), then the metavars of its operands (like
    ``CITY`` or ``[ARGS]...``), mirroring the usage line. Option synopses are
    deliberately left out: they are ``--show-params``' job. The plain variant
    is used to measure column widths, the styled one to print.

    Aliases render through Cloup's own ``format_subcommand_aliases``: the
    alias words take the ``alias`` theme slot and the parentheses and
    separators the ``alias_secondary`` slot, exactly like the help-screen
    keyword pass (:class:`~click_extra.highlight.HelpFormatter`), which
    routes through the same formatter.
    """
    theme = get_current_theme()
    aliases = tuple(getattr(command, "aliases", None) or ())
    plain = name
    styled = style_name(name)
    if aliases:
        plain += f" ({', '.join(aliases)})"
        styled += " " + cloup.Group.format_subcommand_aliases(aliases, theme)
    operands = " ".join(
        param.make_metavar(ctx=ctx)
        for param in command.params
        if isinstance(param, click.Argument)
    )
    if operands:
        plain += f" {operands}"
        styled += " " + theme.metavar(operands)
    return plain, styled


def _tree_rows(
    command: click.Command,
    ctx: click.Context,
    glyphs: TreeGlyphs,
    prefix: str = "",
) -> Iterator[tuple[str, str, str, str, str]]:
    """Depth-first walk yielding a ``(rail, cont, plain, styled, help)`` row per
    node.

    ``rail`` is the accumulated glyph prefix of the node's own line and
    ``cont`` the one drawn under it when its description wraps over several
    lines: the ancestors' continuation, plus the bar dropping to the node's
    first child when it has any, so the child connector below stays visually
    attached through the wrapped lines. ``plain`` and ``styled`` are the two
    label variants, ``help`` the one-line description. Subcommands are
    discovered dynamically and hidden ones skipped, like help screens (see
    :func:`~click_extra.parameters.iter_subcommands`). Each level is walked
    under its own resilient child context, like the man-page and Carapace
    exporters.
    """
    theme = get_current_theme()
    subs = list(iter_subcommands(command, ctx))
    for index, (name, sub) in enumerate(subs):
        is_last = index == len(subs) - 1
        rail = prefix + (glyphs.last if is_last else glyphs.branch)
        cont = prefix + (glyphs.space if is_last else glyphs.pipe)
        sub_ctx = make_resilient_context(sub, name, parent=ctx)
        plain, styled = _command_labels(sub, name, sub_ctx, theme.subcommand)
        child_rows = list(_tree_rows(sub, sub_ctx, glyphs, cont))
        desc_cont = cont + glyphs.pipe if child_rows else cont
        yield rail, desc_cont, plain, styled, full_short_help(sub)
        yield from child_rows


def render_command_tree(
    command: click.Command,
    prog_name: str | None = None,
    ctx: click.Context | None = None,
    width: int | None = None,
) -> str:
    """Render the hierarchy rooted at ``command`` as a tree with descriptions.

    Reuses ``ctx`` when given (like the live invocation context), otherwise
    builds a throwaway one with ``resilient_parsing=True``. The root line is
    labeled with ``prog_name`` when given, else the context's command path.

    Each node carries the command name, its aliases, its operand metavars
    (mirroring the usage line) and a column-aligned description from
    :func:`~click_extra.parameters.full_short_help`, so deprecated commands
    carry their ``(Deprecated)`` marker. Everything is styled with the same
    theme slots as help screens (``invoked_command`` for the root,
    ``subcommand`` and ``alias`` for children, ``metavar`` for operands), so
    the tree follows ``--theme`` and ``--color``. The rail switches from
    box-drawing to ASCII when accessibility mode is active on the context
    (see :data:`~click_extra.context.ACCESSIBLE`).

    Descriptions wrap at ``width``, resolved like help screens when not given
    (``ctx.make_formatter()``, honoring the ``terminal_width`` and
    ``max_content_width`` context settings). Wrapped lines keep the tree rail
    running through the description column. A label wider than the column
    (typically a long script path as the root, under ``wrap --tree``) keeps
    its line to itself and hangs its description underneath, at the column.

    .. note::
        The tree is a point-in-time snapshot: groups computing their
        subcommands from external state (plugins, scanned directories) render
        exactly what :meth:`click.Group.list_commands` returns at that moment,
        in listing order. Cloup section groupings are not rendered.

    .. caution::
        A non-group command renders as a single root line: valid, just not
        very interesting. Like a man page, the output stays meaningful for
        every command type.
    """
    if ctx is None:
        ctx = make_resilient_context(command, prog_name or command.name)
    if width is None:
        width = ctx.make_formatter().width

    glyphs = ASCII_GLYPHS if context.get(ctx, context.ACCESSIBLE, False) else BOX_GLYPHS
    theme = get_current_theme()

    root_plain, root_styled = _command_labels(
        command,
        prog_name or ctx.command_path or command.name or "",
        ctx,
        theme.invoked_command,
    )
    child_rows = list(_tree_rows(command, ctx, glyphs))
    root_cont = glyphs.pipe if child_rows else ""
    rows = [("", root_cont, root_plain, root_styled, full_short_help(command))]
    rows.extend(child_rows)

    # The root is left out of the column measurement (when it has children):
    # it can be an arbitrarily long script path under ``wrap --tree``, and
    # letting it drive the column would crush every description against the
    # right edge. An over-wide label hangs its description on the next line
    # instead (see below).
    measure_rows = child_rows or rows
    label_width = max(
        max(wcswidth(rail + plain), 0) for rail, _, plain, _, _ in measure_rows
    )
    desc_column = label_width + COLUMN_GAP
    desc_width = max(width - desc_column, MIN_DESCRIPTION_WIDTH)

    lines = []
    for rail, cont, plain, styled, help_text in rows:
        line = rail + styled
        row_width = max(wcswidth(rail + plain), 0)
        wrapped = textwrap.wrap(help_text, width=desc_width) if help_text else []
        cont_pad = " " * (desc_column - max(wcswidth(cont), 0))
        if wrapped and row_width + COLUMN_GAP > desc_column:
            # Label wider than the description column: keep it on its own
            # line and hang the whole description under it, at the column.
            lines.append(line)
            lines.extend(cont + cont_pad + part for part in wrapped)
        elif wrapped:
            line += " " * (desc_column - row_width) + wrapped[0]
            lines.append(line)
            lines.extend(cont + cont_pad + part for part in wrapped[1:])
        else:
            lines.append(line)
    return "\n".join(lines)


class TreeOption(ExtraOption):
    """A pre-configured ``--tree`` flag that prints the hierarchy of nested
    subcommands and exits.

    Eager and value-less, like :class:`~click_extra.man_page.ManOption`. Part
    of the default option set injected by
    :func:`~click_extra.commands.default_params`, so every ``@command`` and
    ``@group`` exposes it. Use
    :func:`@tree_option <click_extra.decorators.tree_option>` to add it to a
    plain Click CLI.

    .. note::
        The flag is named ``--tree``, not ``--show-tree`` or ``--commands``.

        Rendering a hierarchy as a tree is conventionally named ``tree``
        across ecosystems: ``eza --tree``, ``lsblk --tree``,
        ``poetry show --tree``, ``cargo tree``, ``pstree(1)`` and ``tree(1)``
        itself (``ps --forest`` being the lone dissenter). ``--commands``
        would suggest the flat listing ``--help`` already provides.

        The bare noun also lines up with the neighbouring ``--man``,
        ``--version`` and ``--help`` informational flags; ``--show-params`` is
        the historical outlier, not the pattern. A flag was preferred over a
        registered ``tree`` subcommand, which could collide with the user's
        own command namespace.
    """

    def __init__(
        self,
        param_decls: tuple[str, ...] | None = None,
        is_flag: bool = True,
        expose_value: bool = False,
        is_eager: bool = True,
        help: str = _("Show the tree of nested subcommands and exit."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--tree",)
        kwargs.setdefault("callback", self.print_tree)
        super().__init__(
            param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )

    def print_tree(self, ctx: click.Context, param: click.Parameter, value: bool):
        """Render and print the invoked command's subcommand tree, then exit."""
        if not value or ctx.resilient_parsing:
            return
        click.echo(render_command_tree(ctx.command, ctx=ctx), color=ctx.color)
        ctx.exit()
