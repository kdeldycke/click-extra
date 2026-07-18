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
"""Accessibility helpers switching CLI output to a screen-reader-friendly mode.

A screen reader consumes a terminal as a linear stream of characters. Several of
the defaults that make output pleasant for sighted users actively harm that
stream:

- ANSI color codes, which carry no meaning once flattened to text;
- tables drawn with Unicode box characters (``│``, ``╭``, ``─``, …), whose
  separators and whitespace-based column alignment are read out as noise;
- animated progress spinners and bars, whose cursor-driven frames repeat
  endlessly to a reader that cannot watch them advance;
- interactive takeovers like a pager or a screen-clear, which trap or wipe the
  linear stream the reader is following.

The :class:`AccessibleOption` collapses these concerns into a single
``--accessible`` switch (also driven by the ``ACCESSIBLE`` environment variable),
which is the same rationale that leads Click Extra to render help screens as
minimal-width text rather than inside a terminal-wide table. It lowers the
``--color``, ``--progress`` and ``--table-format`` defaults and publishes
:data:`~click_extra.context.ACCESSIBLE`, which :func:`clear` and
:func:`echo_via_pager` read to drop their interactive behavior. See the
``--accessible`` section of ``docs/colorize.md`` for the full reasoning.
"""

from __future__ import annotations

import inspect
import os
from configparser import RawConfigParser
from gettext import gettext as _
from typing import cast

import click

from . import context
from .parameters import ExtraOption
from .table import TableFormat

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence


class AccessibleOption(ExtraOption):
    """A pre-configured ``--accessible`` switch.

    Turning it on (either via the flag or the ``ACCESSIBLE`` environment variable)
    is equivalent to passing ``--no-color --no-progress --table-format plain``, and
    additionally streams :func:`echo_via_pager` output without a pager and turns
    :func:`clear` into a no-op: it strips ANSI codes, silences progress spinners and
    bars, renders tables without box-drawing characters, and avoids interactive
    screen takeovers.

    .. note::
        It is a one-way flag with no ``--no-accessible`` counterpart: to opt back
        out, pass the explicit ``--color`` / ``--table-format`` you want, which take
        precedence anyway (see below). A negation flag would also be the widest
        option label in the help screen, pushing every other option's description
        column to the right.

    The switch only adjusts the *defaults* of the ``--color`` and ``--table-format``
    options, through the context's ``default_map``. An explicit ``--color`` /
    ``--table-format`` on the command line (or in a configuration file) therefore
    keeps precedence over ``--accessible``.

    This option is eager so it lands its defaults before ``--color`` and
    ``--table-format`` are resolved.

    .. note::
        The values are injected with :meth:`dict.setdefault`, so they never clobber
        a colorization or table format already requested by the user. Combined with
        the ``ChainMap`` that :class:`~click_extra.config.option.ConfigOption` layers on top
        of ``default_map``, this yields the precedence:
        command line > configuration file > ``--accessible`` > built-in defaults.
    """

    def set_accessible(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Publish the accessibility intent and lower color/progress/table defaults.

        Reconciles ``--accessible`` with the ``ACCESSIBLE`` environment variable,
        stores the result at :data:`~click_extra.context.ACCESSIBLE` for output
        helpers (:func:`clear`, :func:`echo_via_pager`) to read, then lowers the
        ``--color`` / ``--progress`` / ``--table-format`` defaults when active. A
        CLI that never sees ``--accessible`` (nor ``ACCESSIBLE``) keeps every
        default untouched.

        .. note::
            The global ``ACCESSIBLE`` environment variable is read here rather than
            wired through the option's ``envvar``. Click would otherwise list it
            alongside the auto-generated ``<CLI>_ACCESSIBLE`` variable in the
            ``--params`` table, making the combined string the widest cell of
            the env-var column and pushing every other row's padding out. This
            mirrors how :class:`~click_extra.color.ColorOption` reads
            ``NO_COLOR`` and friends.
        """
        if not value:
            raw = os.environ.get("ACCESSIBLE")
            if raw is not None:
                # Bare presence (or an unparsable value) counts as activation, in
                # the same spirit as the color environment variables.
                value = RawConfigParser.BOOLEAN_STATES.get(raw.lower(), True)

        # Publish the resolved intent so output helpers (clear, echo_via_pager)
        # can degrade their interactive behavior to a linear stream.
        context.set(ctx, context.ACCESSIBLE, value)

        if not value:
            return

        if ctx.default_map is None:
            ctx.default_map = {}
        ctx.default_map.setdefault("color", "never")
        ctx.default_map.setdefault("progress", False)
        ctx.default_map.setdefault("table_format", TableFormat.PLAIN)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=True,
        default=False,
        is_eager=True,
        expose_value=False,
        help=_(
            "Accessibility mode: disable colors and render tables in a plain, "
            "screen-reader-friendly format."
        ),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--accessible",)

        kwargs.setdefault("callback", self.set_accessible)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )


def clear() -> None:
    """Drop-in for :func:`click.clear` that becomes a no-op under ``--accessible``.

    Clearing the screen wipes the scrollback a screen reader relies on and carries
    no meaning in a linear stream, so accessibility mode skips it entirely. Outside
    accessibility mode (or with no active context) it defers to :func:`click.clear`,
    which already no-ops when stdout is not a terminal.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is not None and context.get(ctx, context.ACCESSIBLE, False):
        return
    click.clear()


def echo_via_pager(
    text_or_generator: Iterable[str] | Callable[[], Iterable[str]] | str,
    color: bool | None = None,
) -> None:
    """Drop-in for :func:`click.echo_via_pager` that streams plainly under --accessible.

    A pager is a full-screen, cursor-driven TUI: it traps output behind its own
    keybindings, hostile to a screen reader consuming a linear stream. Under
    ``--accessible`` the text is written straight to stdout via :func:`click.echo`
    instead. Outside accessibility mode (or with no active context) it defers to
    :func:`click.echo_via_pager`, which already falls back to a plain write when
    stdout is not a terminal.

    The argument is normalized exactly as :func:`click.echo_via_pager` does (a
    generator function is called, a string is emitted as-is, anything else is
    iterated), so the two behave identically on their inputs.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is not None and context.get(ctx, context.ACCESSIBLE, False):
        chunks: Iterable[str]
        if inspect.isgeneratorfunction(text_or_generator):
            chunks = cast("Callable[[], Iterable[str]]", text_or_generator)()
        elif isinstance(text_or_generator, str):
            chunks = [text_or_generator]
        else:
            chunks = cast("Iterable[str]", text_or_generator)
        for chunk in chunks:
            click.echo(chunk, color=color, nl=False)
        return
    click.echo_via_pager(text_or_generator, color=color)
