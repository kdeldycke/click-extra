# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

"""Extend cli_helpers.tabulate utilities with new formats."""

from __future__ import annotations

from functools import partial
from gettext import gettext as _

import tabulate
from click import Choice, echo
from cloup import option

from .parameters import ExtraOption

tabulate.MIN_PADDING = 0


class TableFormatOption(ExtraOption):
    """A pre-configured option that is adding a ``-t``/``--table-format`` flag to select
    the rendering style of a table."""

    def print_table(self, *args, **kwargs):
        """Print table via echo."""
        defaults = {
            "disable_numparse": True,
            "numalign": None,
        }
        defaults.update(kwargs)
        echo(tabulate.tabulate(*args, **defaults))

    def init_formatter(self, ctx, param, value):
        """Attach a ready-to-use ``print_table()`` method to the context."""
        ctx.print_table = partial(self.print_table, tablefmt=value)

    def __init__(
        self,
        param_decls=None,
        type=Choice(sorted(tabulate._table_formats), case_sensitive=False),
        default="rounded_outline",
        expose_value=False,
        help=_("Rendering style of tables."),
        **kwargs,
    ):
        if not param_decls:
            param_decls = ("-t", "--table-format")

        kwargs.setdefault("callback", self.init_formatter)

        super().__init__(
            param_decls=param_decls,
            type=type,
            default=default,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )


table_format_option = partial(option, cls=TableFormatOption)
"""Decorator for ``TableFormatOption``."""
