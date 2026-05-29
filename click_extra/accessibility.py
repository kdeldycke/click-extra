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

A screen reader consumes a terminal as a linear stream of characters. Two of the
defaults that make output pleasant for sighted users actively harm that stream:

- ANSI color codes, which carry no meaning once flattened to text;
- tables drawn with Unicode box characters (``│``, ``╭``, ``─``, …), whose
  separators and whitespace-based column alignment are read out as noise.

The :class:`AccessibleOption` collapses both concerns into a single
``--accessible`` switch (also driven by the ``ACCESSIBLE`` environment variable),
which is the same rationale that leads Click Extra to render help screens as
minimal-width text rather than inside a terminal-wide table. See the
``--accessible`` section of ``docs/colorize.md`` for the full reasoning.
"""

from __future__ import annotations

import os
from configparser import RawConfigParser
from gettext import gettext as _

from .parameters import ExtraOption
from .table import TableFormat

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence

    import click


class AccessibleOption(ExtraOption):
    """A pre-configured ``--accessible`` switch.

    Turning it on (either via the flag or the ``ACCESSIBLE`` environment variable)
    is equivalent to passing ``--no-color --table-format plain``: it strips ANSI
    codes and renders tables without box-drawing characters.

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
        the ``ChainMap`` that :class:`~click_extra.config.ConfigOption` layers on top
        of ``default_map``, this yields the precedence:
        command line > configuration file > ``--accessible`` > built-in defaults.
    """

    def set_accessible(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Lower the ``--color`` and ``--table-format`` defaults for accessibility.

        Does nothing unless accessibility mode is active, so a CLI that never sees
        ``--accessible`` (nor ``ACCESSIBLE``) behaves exactly as before.

        .. note::
            The global ``ACCESSIBLE`` environment variable is read here rather than
            wired through the option's ``envvar``. Click would otherwise list it
            alongside the auto-generated ``<CLI>_ACCESSIBLE`` variable in the
            ``--show-params`` table, making the combined string the widest cell of
            the env-var column and pushing every other row's padding out. This
            mirrors how :class:`~click_extra.colorize.ColorOption` reads
            ``NO_COLOR`` and friends.
        """
        if not value:
            raw = os.environ.get("ACCESSIBLE")
            if raw is not None:
                # Bare presence (or an unparsable value) counts as activation, in
                # the same spirit as the color environment variables.
                value = RawConfigParser.BOOLEAN_STATES.get(raw.lower(), True)

        if not value:
            return

        if ctx.default_map is None:
            ctx.default_map = {}
        ctx.default_map.setdefault("color", False)
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
