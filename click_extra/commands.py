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

"""Wrap-up all click-extra extensions into click-like commands.

The collection of pre-defined decorators here present good and common defaults. You can
still mix'n'match the mixins below to build your own custom variants.
"""

import io
from functools import partial
from logging import getLevelName
from time import perf_counter
from unittest.mock import patch

import click
import cloup

from . import (
    Command,
    Group,
    Option,
    color_option,
    config_option,
    echo,
    help_option,
    verbosity_option,
    version_option,
)
from .colorize import ExtraHelpColorsMixin, VersionOption
from .logging import logger


def register_timer_on_close(ctx, param, value):
    """Callback setting up all timer's machinery.

    Computes and print the execution time at the end of the CLI, if option has been
    activated.
    """
    # Skip time keeping if option is not active.
    if not value:
        return

    # Take timestamp snapshot.
    timer_start_time = perf_counter()

    def print_timer():
        """Compute and print elapsed execution time."""
        echo(f"Execution time: {perf_counter() - timer_start_time:0.3f} seconds.")

    # Register printing at the end of execution.
    ctx.call_on_close(print_timer)


def timer_option(
    *names,
    default=False,
    expose_value=False,
    callback=register_timer_on_close,
    help="Measure and print elapsed execution time.",
    cls=Option,
    **kwargs,
):
    """A ready to use option decorator that is adding a ``--time/--no-time`` option flag
    to print elapsed time at the end of CLI execution."""
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


class ExtraOptionsMixin:
    """A set of default extra options."""

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
        help_option(*self.context_settings["help_option_names"], cls=Option)(self)

        # Forces re-identification of grouped and non-grouped options.
        self.arguments, self.option_groups, self.ungrouped_options = self._group_params(
            self.params
        )

    def main(self, *args, **kwargs):
        """Pre-invokation step that is instanciating the context, then call ``invoke()``
        within it.

        During context instanciation, each option's callbacks are called. Beware that
        these might break the execution flow (like ``--version``).
        """
        super().main(*args, **kwargs)

    def invoke(self, ctx):
        """Main execution of the command, just after the context has been instanciated
        in ``main()``.

        Adds, to the normal execution flow, the output of the `--version` parameter in
        DEBUG logs. This facilitates troubleshooting user's issues.
        """
        if getLevelName(logger.level) == "DEBUG":

            # Look for our custom version parameter.
            for param in ctx.find_root().command.params:
                if isinstance(param, VersionOption):

                    # Call the --version parameter, but:
                    #  - capture its output from stdout to redirect it to the DEBUG logger:
                    #    https://github.com/pallets/click/blob/c1d0729bbb26e3f8b0a28440fb0ebca352535c25/src/click/decorators.py#L451-L455
                    #    https://github.com/pallets/click/blob/14472ffcd80dd86d47ddc08341168152540ee6f2/src/click/utils.py#L205-L211
                    capture = io.StringIO()
                    capture_echo = partial(echo, file=capture)
                    with patch.object(click.decorators, "echo", new=capture_echo):

                        # Neutralize parameter call to `ctx.exit()`, as seen in:
                        # https://github.com/pallets/click/blob/c1d0729bbb26e3f8b0a28440fb0ebca352535c25/src/click/decorators.py#L456
                        with patch(
                            f"{ctx.__class__.__module__}.{ctx.__class__.__name__}.exit"
                        ):
                            param.callback(ctx, param, True)

                    for line in capture.getvalue().splitlines():
                        logger.debug(line)

        return super().invoke(ctx)


class ExtraCommand(ExtraHelpColorsMixin, ExtraOptionsMixin, Command):
    """Same as ``cloup.command``, but with extra help screen colorization and
    options."""

    pass


class ExtraGroup(ExtraHelpColorsMixin, ExtraOptionsMixin, Group):
    """Same as ``cloup.group``, but with extra help screen colorization and options."""

    pass


def command(*args, cls=ExtraCommand, **kwargs):
    return cloup.command(*args, cls=cls, **kwargs)


def group(*args, cls=ExtraGroup, **kwargs):
    return cloup.group(*args, cls=cls, **kwargs)
