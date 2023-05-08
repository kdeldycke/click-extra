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
"""Wraps vanilla Click and Cloup commands with extra features.

Our flavor of commands, groups and context are all subclasses of their vanilla
counterparts, but are pre-configured with good and common defaults. You can still
leverage the mixins in here to build up your own custom variants.
"""

from __future__ import annotations

from gettext import gettext as _
from logging import getLevelName, getLogger
from time import perf_counter
from typing import Any, Dict, Sequence, Iterable

import click
import cloup

from . import Command, Group, echo
from .colorize import ExtraHelpColorsMixin
from .parameters import ExtraOption, all_envvars, normalize_envvar
from .colorize import ColorOption, HelpOption
from .config import ConfigOption, ShowParamsOption
from .logging import VerbosityOption
from .version import VersionOption


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
        param_decls: Sequence[str] | None = None,
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


class ExtraContext(cloup.Context):
    """Like ``cloup._context.Context``, but with the ability to populate the context's
    ``meta`` property at instanciation."""

    _extra_meta: dict[str, Any] = {}

    def __init__(self, *args, meta: dict[str, Any] = {}, **kwargs) -> None:
        """Like parent's context but with an extra ``meta`` keyword-argument."""
        self._extra_meta = meta
        super().__init__(*args, **kwargs)

    @property
    def meta(self) -> dict[str, Any]:
        """Returns context meta augmented with our own."""
        meta = dict(self._meta)
        meta.update(self._extra_meta)
        return meta


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
    """
    return [
        TimerOption(),
        ColorOption(),
        # XXX Should we move config to the top as it might influence other options?
        ConfigOption(),
        ShowParamsOption(),
        VerbosityOption(),
        VersionOption(print_env_info=True),
        HelpOption(),
    ]


class ExtraCommand(ExtraHelpColorsMixin, Command):
    """Like ``cloup.command``, with sane defaults and extra help screen colorization."""

    context_class: type[cloup.Context] = ExtraContext

    @staticmethod
    def _search_params(
        params: Iterable[click.Parameter],
        klass: type[click.Parameter],
        unique: bool = True,
    ) -> list[click.Parameter] | click.Parameter | None:
        """Search on the command all instances of a parameter and return them.

        :param klass: the class of the parameters to look for.
        :param unique: if ``True``, raise an error if more than one parameter of the
            provided ``klass`` is found.
        """
        param_list = [p for p in params if isinstance(p, klass)]
        if not param_list:
            return None
        if unique:
            if len(param_list) != 1:
                raise RuntimeError(
                    f"More than one {klass.__name__} parameters found "
                    f"on command: {param_list}"
                )
            return param_list.pop()
        return param_list

    def __init__(
        self,
        *args,
        version: str | None = None,
        extra_option_at_end: bool = True,
        populate_auto_envvars: bool = True,
        **kwargs: Any,
    ):
        """List of extra parameters:

        :param version: allows a version string to be set directly on the command. Will
            be passed to the first instance of ``VersionOption`` parameter attached to
            the command.
        :param extra_option_at_end: `reorders all parameters attached to the command
            <https://kdeldycke.github.io/click-extra/commands.html#option-order>`_, by
            moving all instances of ``ExtraOption`` at the end of the parameter list.
            The original order of the options is preserved among themselves.
        :param populate_auto_envvars: forces all parameters to have their auto-generated
            environment variables registered. This address the shortcoming of ``click``
            which only evaluates them dynamiccaly. By forcing their registration, the
            auto-generated environment variables gets displayed in the help screen,
            fixing `click#2483 issue <https://github.com/pallets/click/issues/2483>`_.

        By default, these context settings are applied:

        - ``show_default = True``: `show all default values
          <https://click.palletsprojects.com/en/8.1.x/api/#click.Context.show_default>`_
          in help screen.

        - ``auto_envvar_prefix = self.name``: auto-generate environment variables for
          all options, using the command ID as prefix.

        - ``align_option_groups = False``: `align option groups in help screen
          <https://cloup.readthedocs.io/en/stable/pages/option-groups.html#aligned-vs-non-aligned-groups>`_.

        - ``show_constraints = True``: `show all constraints in help screen
          <https://cloup.readthedocs.io/en/stable/pages/constraints.html#the-constraint-decorator>`_.

        - ``show_subcommand_aliases = True``: `show all subcommand aliases in help
          screen
          <https://cloup.readthedocs.io/en/stable/pages/aliases.html?highlight=show_subcommand_aliases#help-output-of-the-group>`_.

        - ``help_option_names = ("--help", "-h")``: `allow help screen to be invoked
          with either --help or -h options
          <https://click.palletsprojects.com/en/8.1.x/documentation/#help-parameter-customization>`_.

        To override these defaults, you can pass your own settings with the
        ``context_settings`` parameter:

        .. code-block:: python

            @extra_command(
                context_settings={
                    "show_default": False,
                    ...
                }
            )
        """
        super().__init__(*args, **kwargs)

        # TODO: implements:
        # self.show_all_default = show_default
        # self.show_all_choices = show_choices
        # self.show_all_envvar = show_envvar =>
        # https://github.com/pallets/click/issues/2313

        default_ctx_settings: Dict[str, Any] = {
            "show_default": True,
            # "default_map": {"verbosity": "DEBUG"},
            "align_option_groups": False,
            "show_constraints": True,
            "show_subcommand_aliases": True,
            "help_option_names": ("--help", "-h"),
        }

        if self.name:
            default_ctx_settings["auto_envvar_prefix"] = normalize_envvar(self.name)

        # Fill-in the unset settings with our defaults.
        default_ctx_settings.update(self.context_settings)
        self.context_settings: Dict[str, Any] = default_ctx_settings

        if populate_auto_envvars:
            for param in self.params:
                param.envvar = all_envvars(param, self.context_settings)

        if version:
            version_param = self._search_params(self.params, VersionOption)
            if version_param:
                version_param.version = version  # type: ignore[union-attr]

        if extra_option_at_end:
            self.params.sort(key=lambda p: isinstance(p, ExtraOption))

        # Forces re-identification of grouped and non-grouped options as we re-ordered
        # them above and added our own extra options since initialization.
        _grouped_params = self._group_params(self.params)  # type: ignore[attr-defined]
        self.arguments, self.option_groups, self.ungrouped_options = _grouped_params

    def main(self, *args, **kwargs):
        """Pre-invokation step that is instantiating the context, then call ``invoke()``
        within it.

        During context instantiation, each option's callbacks are called. Beware that
        these might break the execution flow (like ``--version``).
        """
        return super().main(*args, **kwargs)

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: Any,
    ) -> Any:
        """Intercept the call to the original ``click.core.BaseCommand.make_context`` so
        we can keep a copy of the raw, pre-parsed arguments provided to the CLI.

        The result are passed to our own ``ExtraContext`` constructor which is able to
        initialize the context's ``meta`` property under our own
        ``click_extra.raw_args`` entry. This will be used in
        ``ShowParamsOption.print_params()`` to print the table of parameters fed to the
        CLI.

        .. seealso::
            This workaround is being discussed upstream in `click#1279
            <https://github.com/pallets/click/issues/1279#issuecomment-1493348208>`_.
        """
        # ``args`` needs to be copied: its items are consummed by the parsing process.
        extra.update({"meta": {"click_extra.raw_args": args.copy()}})
        ctx = super().make_context(info_name, args, parent, **extra)
        return ctx

    def invoke(self, ctx):
        """Main execution of the command, just after the context has been instantiated
        in ``main()``.

        If an instance of ``VersionOption`` has been setup on the command, adds to the
        normal execution flow the output of ``--version`` in ``DEBUG`` logs. This
        facilitates troubleshooting of user's issues.
        """
        logger = getLogger("click_extra")
        if getLevelName(logger.level) == "DEBUG":
            # Look for our custom version parameter.
            version_param = self._search_params(ctx.command.params, VersionOption)
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

    # XXX This simple override might be enough to replace the command() override below,
    # but there is a bug in click that prevents this from working:
    #   https://github.com/pallets/click/issues/2416
    #   https://github.com/pallets/click/pull/2417
    #
    # command_class = ExtraCommand

    def command(self, *args, **kwargs):
        """Returns a decorator that creates a new subcommand for this ``Group``.

        This makes a command that is a :class:`~click_extra.command.ExtraCommand`
        instead of a :class:`~cloup._command.Command` so by default all subcommands of
        an ``ExtraGroup`` benefits from the same defaults and extra help screen
        colorization.

        Fixes `click-extra#479 <https://github.com/kdeldycke/click-extra/issues/479>`_.

        .. todo::
            Allow this decorator to be called without parenthesis.
        """
        kwargs.setdefault("cls", ExtraCommand)
        return super().command(*args, **kwargs)


# -0, --zero-exit
# rospector will exit with a code of 1 (one) if any messages are found. This makes
# automation easier; if there are any problems at all, the exit code is non-zero.
# However this behaviour is not always desirable, so if this flag is set, prospector
# will exit with a code of 0 if it ran successfully, and non-zero if it failed to run.
