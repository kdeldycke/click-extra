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

from time import perf_counter

import click
from cloup import Command, Group, GroupedOption, OptionGroupMixin
from cloup import command as cloup_command
from cloup import group as cloup_group

from .colorize import ExtraHelpColorsMixin, color_option, version_option
from .config import config_option
from .logging import verbosity_option


def register_timer_on_close(ctx, param, value):
    """Callback setting up all timer's machinery.

    Computes and print the execution time at the end of the CLI, if option has been activated.
    """
    # Skip time keeping if option is not active.
    if not value:
        return

    # Take timestamp snapshot.
    timer_start_time = perf_counter()

    def print_timer():
        """Compute and print elapsed execution time."""
        click.echo(f"Execution time: {perf_counter() - timer_start_time:0.3f} seconds.")

    # Register printing at the end of execution.
    ctx.call_on_close(print_timer)


def timer_option(
    *names,
    default=False,
    expose_value=False,
    callback=register_timer_on_close,
    help="Measure and print elapsed execution time.",
    cls=GroupedOption,
    **kwargs,
):
    """A ready to use option decorator that is adding a ``--time/--no-time``
    option flag to print elapsed time at the end of CLI execution."""
    if not names:
        names = ("--time/--no-time",)
    return click.option(
        *names,
        default=default,
        expose_value=expose_value,
        callback=callback,
        help=help,
        cls=cls,
        **kwargs,
    )


class ExtraGroup(ExtraHelpColorsMixin, OptionGroupMixin, Group):
    """Click's `group` with Cloup's `option_group` and extra colorization and options.

    Cloup does not support option groups on `Click.group`. This is a workaround that is
    being discussed at https://github.com/janluke/cloup/issues/98
    """

    def __init__(self, *args, version=None, **kwargs):
        """Augment group with additional default options."""

        super().__init__(*args, **kwargs)

        self.context_settings.update(
            {
                "show_default": True,
                "auto_envvar_prefix": self.name,
                # "default_map": {"verbosity": "DEBUG"},
                "align_option_groups": False,
                "show_constraints": True,
                "show_subcommand_aliases": True,
                "help_option_names": ("--help", "-h"),
            }
        )

        # Add timer option flag.
        timer_option()(self)

        # Add color stripping flag.
        color_option()(self)

        config_option()(self)

        # Add logger verbosity selector.
        verbosity_option()(self)

        # Add colored version option.
        version_option(version=version, print_env_info=True)(self)

        # Add help option.
        click.help_option(
            *self.context_settings["help_option_names"], cls=GroupedOption
        )(self)

        # Forces re-identification of grouped and non-grouped options.
        self.option_groups, self.ungrouped_options = self._option_groups_from_params(
            self.params
        )

    def main(self, *args, **kwargs):
        """Pre-invokation step that is instanciating the context, then call ``invoke()`` within it.

        During context instanciation, each option's callbacks are called. Beware that these
        might break the execution flow (like ``--version``).
        """
        super().main(*args, **kwargs)

    def invoke(self, ctx):
        """Main execution of the command, just after the context has been instanciated in ``main()``."""
        return super().invoke(ctx)


class ExtraCommand(ExtraHelpColorsMixin, Command):
    """Cloup's `command` with extra help screen colorization."""

    pass


def group(name=None, cls=ExtraGroup, **kwargs):
    return cloup_group(name=name, cls=cls, **kwargs)


def command(name=None, aliases=None, cls=ExtraCommand, **kwargs):
    return cloup_command(name=name, aliases=aliases, cls=cls, **kwargs)
