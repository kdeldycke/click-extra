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

""" Wrap-up all click-extra extensions into click-like commands.

The collection of pre-defined decorators here present good and common defaults. You can
still mix'n'match the mixins below to build your own custom variants.
"""

import click
from cloup import Command, Group, OptionGroupMixin
from cloup import command as cloup_command
from cloup import group as cloup_group

from .colorize import ExtraHelpColorsMixin
from .logging import print_level, verbosity_option


class ExtraGroup(ExtraHelpColorsMixin, OptionGroupMixin, Group):
    """Click's `group` with Cloup's `option_group` and extra colorization and options.

    Cloup does not support option groups on `Click.group`. This is a workaround that is
    being discussed at https://github.com/janluke/cloup/issues/98
    """

    def __init__(self, *args, **kwargs):
        """ Augment group with additional default options."""
        super().__init__(*args, **kwargs)

        self.context_settings.update(
            {
                "show_default": True,
                "auto_envvar_prefix": self.name,
                # "default_map": {"verbosity": "DEBUG"},
                "align_option_groups": False,
                "show_constraints": True,
                "show_subcommand_aliases": True,
            }
        )

        # Add logger verbosity selector.
        verbosity_option()(self)

        # Add help option.
        click.help_option("-h", "--help")(self)

    def main(self, *args, **kwargs):
        """Pre-invokation step that is instanciating the context."""
        super().main(*args, **kwargs)

    def invoke(self, ctx):
        """Main execution of the command, just after the context has been instanciated."""
        # Always print log level beforehand.
        print_level()

        return super().invoke(ctx)


class ExtraCommand(ExtraHelpColorsMixin, Command):
    """Cloup's `command` with extra help screen colorization."""

    pass


def group(name=None, cls=ExtraGroup, **kwargs):
    return cloup_group(name=name, cls=cls, **kwargs)


def command(name=None, aliases=None, cls=ExtraCommand, **kwargs):
    return cloup_command(name=name, aliases=aliases, cls=cls, **kwargs)
