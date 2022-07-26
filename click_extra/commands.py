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

from logging import getLevelName
from time import perf_counter

import click
import cloup

from . import (
    ColorOption,
    ConfigOption,
    ExtraOption,
    HelpOption,
    VerbosityOption,
    VersionOption,
    echo,
)
from .colorize import ExtraHelpColorsMixin, VersionOption
from .logging import logger


class TimerOption(cloup.Option, ExtraOption):
    """A pre-configured option that is adding a ``--time/--no-time`` flag
    to print elapsed time at the end of CLI execution."""

    @staticmethod
    def _register_timer_on_close(ctx, param, value):
        """Callback setting up all timer's machinery.

        Computes and print the execution time at the end of the CLI, if option has been
        activated.
        """
        # Skip timekeeping if option is not active.
        if not value:
            return

        # Take timestamp snapshot.
        timer_start_time = perf_counter()

        def print_timer():
            """Compute and print elapsed execution time."""
            echo(f"Execution time: {perf_counter() - timer_start_time:0.3f} seconds.")

        # Register printing at the end of execution.
        ctx.call_on_close(print_timer)

    def __init__(
        self,
        param_decls=None,
        default=False,
        expose_value=False,
        callback=_register_timer_on_close,
        help="Measure and print elapsed execution time.",
        **kwargs,
    ):
        if not param_decls:
            param_decls = ("--time/--no-time",)
        super().__init__(
            param_decls=param_decls,
            default=default,
            expose_value=expose_value,
            callback=callback,
            help=help,
            **kwargs,
        )


def timer_option(*param_decls: str, cls=TimerOption, **kwargs):
    """Decorator for ``TimerOption``."""
    return click.option(*param_decls, cls=cls, **kwargs)


class ExtraCommand(ExtraHelpColorsMixin, cloup.Command):
    """Same as ``cloup.command``, but with sane defaults and extra help screen colorization."""

    def __init__(self, *args, version=None, extra_option_at_end=True, **kwargs):

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

        # Update version number with the one provided on the command.
        if version:
            version_params = [p for p in self.params if isinstance(p, VersionOption)]
            if version_params:
                assert len(version_params) == 1
                version_param = version_params.pop()
                version_param.version = version

        # Move extra options to the end while keeping the original natural order.
        if extra_option_at_end:
            self.params.sort(key=lambda p: isinstance(p, ExtraOption))

        # Forces re-identification of grouped and non-grouped options.
        self.arguments, self.option_groups, self.ungrouped_options = self._group_params(
            self.params
        )

    def main(self, *args, **kwargs):
        """Pre-invokation step that is instantiating the context, then call ``invoke()``
        within it.

        During context instantiation, each option's callbacks are called. Beware that
        these might break the execution flow (like ``--version``).
        """
        super().main(*args, **kwargs)

    @staticmethod
    def _get_param(ctx, klass):
        """Search for the unique instance of a parameter that has been setup on the command and return it."""
        params = [p for p in ctx.find_root().command.params if isinstance(p, klass)]
        if params:
            assert len(params) == 1
            return params.pop()

    def invoke(self, ctx):
        """Main execution of the command, just after the context has been instantiated
        in ``main()``.

        If an instance of ``VersionOption`` has been setup on the command, adds to the normal execution flow
        the output of `--version` in DEBUG logs. This facilitates troubleshooting of user's issues.
        """
        if getLevelName(logger.level) == "DEBUG":

            # Look for our custom version parameter.
            version_param = self._get_param(ctx, VersionOption)
            if version_param:
                version_message = version_param.callback(
                    ctx, version_param, True, capture_output=True
                )
                for line in version_message.splitlines():
                    # TODO: pretty print JSON output (easier to read in bug reports).
                    logger.debug(line)

        return super().invoke(ctx)


class ExtraGroup(ExtraCommand, cloup.Group):
    """Same as ``cloup.group``, but with sane defaults and extra help screen colorization."""

    pass


extra_params = [
    # Add timer option flag.
    TimerOption(),
    # Add color stripping flag.
    ColorOption(),
    ConfigOption(),
    # Add logger verbosity selector.
    VerbosityOption(),
    # Add colored version option.
    VersionOption(),
    # Add help option.
    HelpOption(),
]
"""Default additional options added to ``extra_command`` and ``extra_group``.

Order is important so that options at the top of the list can have influence on options below.
"""


def extra_command(*args, cls=ExtraCommand, params=extra_params, **kwargs):
    """Augment default ``cloup.command`` with additional options."""
    return cloup.command(*args, cls=cls, params=params, **kwargs)


def extra_group(*args, cls=ExtraGroup, params=extra_params, **kwargs):
    """Augment default ``cloup.group`` with additional options."""
    return cloup.group(*args, cls=cls, params=params, **kwargs)
