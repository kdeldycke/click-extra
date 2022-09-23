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

from functools import partial
from gettext import gettext as _
from logging import getLevelName
from time import perf_counter
from typing import Any, Dict, List, Optional, Type

from click import Context as ClickContext
from click import echo
from cloup import Command
from cloup import Context as CloupContext
from cloup import Group, command, group, option

from .colorize import ColorOption, ExtraHelpColorsMixin, HelpOption, VersionOption
from .config import ConfigOption, ShowParamsOption
from .logging import VerbosityOption, logger
from .parameters import ExtraOption


class TimerOption(ExtraOption):
    """A pre-configured option that is adding a ``--time``/``--no-time`` flag to print
    elapsed time at the end of CLI execution."""

    def print_timer(self):
        """Compute and print elapsed execution time."""
        echo(f"Execution time: {perf_counter() - self.start_time:0.3f} seconds.")

    def register_timer_on_close(self, ctx, param, value):
        """Callback setting up all timer's machinery.

        Computes and print the execution time at the end of the CLI, if option has been
        activated.
        """
        # Skip timekeeping if option is not active.
        if not value:
            return

        # Take timestamp snapshot.
        self.start_time = perf_counter()

        # Register printing at the end of execution.
        ctx.call_on_close(self.print_timer)

    def __init__(
        self,
        param_decls=None,
        default=False,
        expose_value=False,
        help=_("Measure and print elapsed execution time."),
        **kwargs,
    ):
        if not param_decls:
            param_decls = ("--time/--no-time",)

        kwargs.setdefault("callback", self.register_timer_on_close)

        super().__init__(
            param_decls=param_decls,
            default=default,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )


timer_option = partial(option, cls=TimerOption)
"""Decorator for ``TimerOption``."""


class ExtraContext(CloupContext):
    """Like ``cloup._context.Context``, but with the ability to populate the context's
    ``meta`` property at instanciation."""

    _extra_meta: Dict[str, Any] = {}

    def __init__(self, *args, meta: Dict[str, Any] = {}, **kwargs) -> None:
        """Like parent's context but with an extra ``meta`` keyword-argument."""
        self._extra_meta = meta
        super().__init__(*args, **kwargs)

    @property
    def meta(self) -> Dict[str, Any]:
        """Returns context meta augmented with our own."""
        # Check the two set of meta keys does not intersect.
        assert not set(self._meta).intersection(self._extra_meta)
        meta = dict(self._meta)
        meta.update(self._extra_meta)
        return meta


class ExtraCommand(ExtraHelpColorsMixin, Command):
    """Same as ``cloup.command``, but with sane defaults and extra help screen
    colorization."""

    context_class: Type[ClickContext] = ExtraContext

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
        return super().main(*args, **kwargs)

    def make_context(
        self,
        info_name: Optional[str],
        args: List[str],
        parent: Optional[ClickContext] = None,
        **extra: Any,
    ) -> Any:
        """Intercept the call to the original ``click.core.BaseCommand.make_context`` so
        we can keep a copy of the raw, pre-parsed arguments provided to the CLI.

        The result are passed to our own ``ExtraContext`` constructor which is able to
        initialize the context's ``meta`` property under our own
        ``click_extra.raw_args`` variable. This will be used in ``ShowParamsOption`` to
        print the table of parameters fed to the CLI.
        """
        # args needs to be copied: its items are consummed by the parsing process.
        extra.update({"meta": {"click_extra.raw_args": args.copy()}})
        ctx = super().make_context(info_name, args, parent, **extra)
        return ctx

    @staticmethod
    def _get_param(ctx, klass):
        """Search for the unique instance of a parameter that has been setup on the
        command and return it."""
        params = [p for p in ctx.find_root().command.params if isinstance(p, klass)]
        if params:
            assert len(params) == 1
            return params.pop()

    def invoke(self, ctx):
        """Main execution of the command, just after the context has been instantiated
        in ``main()``.

        If an instance of ``VersionOption`` has been setup on the command, adds to the
        normal execution flow the output of ``--version`` in ``DEBUG`` logs. This
        facilitates troubleshooting of user's issues.
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


class ExtraGroup(ExtraCommand, Group):
    """Same as ``cloup.group``, but with sane defaults and extra help screen
    colorization."""

    pass


def default_extra_params():
    """Default additional options added to ``extra_command`` and ``extra_group``:

    #. ``--time`` / ``--no-time``
    #. ``--color``, ``--ansi`` / ``--no-color``, ``--no-ansi``
    #. ``-C``, ``--config CONFIG_PATH``
    #. ``--show-params``
    #. ``-v``, ``--verbosity LEVEL``
    #. ``--version``
    #. ``-h``, ``--help``

    Order is important to let options at the top have influence on those below.

    .. note::

        This default set is a list wrapped in a method, as a workaround for unittests, in which option instances seems to be
        reused in unrelated commands and mess with test isolation.
    """
    return [
        TimerOption(),
        ColorOption(),
        ConfigOption(),
        ShowParamsOption(),
        VerbosityOption(),
        VersionOption(print_env_info=True),
        HelpOption(),
    ]


extra_command = partial(command, cls=ExtraCommand, params=default_extra_params())
"""Augment default ``cloup.command`` with additional options.

See :py:func:`click_extra.commands.default_extra_params` for the list of default options.
"""


extra_group = partial(group, cls=ExtraGroup, params=default_extra_params())
"""Augment default ``cloup.group`` with additional options.

See :py:func:`click_extra.commands.default_extra_params` for the list of default options.
"""
