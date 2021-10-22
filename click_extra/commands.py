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

""" Wrap-up all click-extra extensions into click-like commands. """


from cloup import Command, Group, OptionGroupMixin
from cloup import command as cloup_command
from cloup import group as cloup_group

from .colorize import ExtraHelpColorsMixin


class ExtraGroup(ExtraHelpColorsMixin, OptionGroupMixin, Group):
    """Click's `group` with Cloup's `option_group` and extra help screen colorization.

    Cloup does not support option groups on `Click.group`.

    This is a workaround that is being discussed at https://github.com/janluke/cloup/issues/98
    """

    pass


class ExtraCommand(ExtraHelpColorsMixin, Command):
    """Cloup's `command` with extra help screen colorization."""

    pass


def group(name=None, cls=ExtraGroup, **kwargs):
    return cloup_group(name=name, cls=cls, **kwargs)


def command(name=None, aliases=None, cls=ExtraCommand, **kwargs):
    return cloup_command(name=name, aliases=aliases, cls=cls, **kwargs)
