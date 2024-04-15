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

from typing import TYPE_CHECKING, Any

import click
import cloup

from . import Command, Group, Option
from .colorize import ColorOption, ExtraHelpColorsMixin, HelpExtraFormatter, HelpOption
from .config import ConfigOption
from .logging import VerbosityOption
from .parameters import (
    ExtraOption,
    ShowParamsOption,
    all_envvars,
    normalize_envvar,
    search_params,
)
from .timer import TimerOption
from .version import ExtraVersionOption

if TYPE_CHECKING:
    from typing import NoReturn

from click.exceptions import Exit


def patched_exit(self, code: int = 0) -> NoReturn:
    """Exits the application with a given exit code.

    Forces the context to close before exiting, so callbacks attached to parameters
    will be called to clean up their state. This is not important in normal CLI
    execution as the Python process will just be destroyed. But it will lead to leaky
    states in unitttests.

    .. seealso::
        This fix has been `proposed upstream to Click
        <https://github.com/pallets/click/pull/2680>`_.
    """
    self.close()
    raise Exit(code)


cloup.Context.exit = patched_exit  # type: ignore[method-assign]
"""Monkey-patch ``cloup.Context.exit``."""


class ExtraContext(cloup.Context):
    """Like ``cloup._context.Context``, but with the ability to populate the context's
    ``meta`` property at instantiation.

    Also inherits ``color`` property from parent context. And sets it to `True` for
    parentless contexts at instantiatiom, so we can always have colorized output.

    .. todo::
        Propose addition of ``meta`` keyword upstream to Click.
    """

    formatter_class = HelpExtraFormatter  # type: ignore[assignment]
    """Use our own formatter to colorize the help screen."""

    def __init__(self, *args, meta: dict[str, Any] | None = None, **kwargs) -> None:
        """Like parent's context but with an extra ``meta`` keyword-argument.

        Also force ``color`` property default to `True` if not provided by user and
        this context has no parent.
        """
        super().__init__(*args, **kwargs)

        # Update the context's meta property with the one provided by user.
        if meta:
            self._meta.update(meta)

        # Transfer user color setting to our internally managed value.
        self._color: bool | None = kwargs.get("color", None)

        # A Context created from scratch, i.e. without a parent, and whose color
        # setting is set to auto-detect (i.e. is None), will defaults to forced
        # colorized output.
        if not self.parent and self._color is None:
            self._color = True

    @property
    def color(self) -> bool | None:
        """Overrides ``Context.color`` to allow inheritance from parent context.

        Returns the color setting of the parent context if it exists and the color is
        not set on the current context.
        """
        if self._color is None and self.parent:
            return self.parent.color
        return self._color

    @color.setter
    def color(self, value: bool | None) -> None:
        """Set the color value of the current context."""
        self._color = value

    @color.deleter
    def color(self) -> None:
        """Reset the color value so it defaults to inheritance from parent's."""
        self._color = None


def default_extra_params() -> list[Option]:
    """Default additional options added to ``extra_command`` and ``extra_group``.

    .. caution::
        The order of options has been carefully crafted to handle subtle edge-cases and
        avoid leaky states in unittests.

        You can still override this hard-coded order for easthetic reasons and it
        should be fine. Your end-users are unlikely to be affected by these sneaky
        bugs, as the CLI context is going to be naturraly reset after each
        invocation (which is not the case in unitests).

    #. ``--time`` / ``--no-time``
        .. hint::
            ``--time`` is placed at the top so all other options can be timed.
    #. ``-C``, ``--config CONFIG_PATH``
        .. attention::
            ``--config`` is at the top so it can have a direct influence on the default
            behavior and value of the other options.
    #. ``--color``, ``--ansi`` / ``--no-color``, ``--no-ansi``
    #. ``--show-params``
    #. ``-v``, ``--verbosity LEVEL``
    #. ``--version``
    #. ``-h``, ``--help``

    .. todo::
        For bullet-proof handling of edge-cases, we should probably add an indirection
        layer to have the processing order of options (the one below) different from
        the presentation order of options in the help screen.

        This is probably something that has been `requested in issue #544
        <https://github.com/kdeldycke/click-extra/issues/544>`_.

    .. important::
        Sensitivity to order still remains to be proven. With the code of Click Extra
        and its dependencies moving fast, there is a non-zero chance that all the
        options are now sound enough to be re-ordered in a more natural way.
    """
    return [
        TimerOption(),
        ColorOption(),
        ConfigOption(),
        ShowParamsOption(),
        VerbosityOption(),
        ExtraVersionOption(),
        HelpOption(),
    ]


class ExtraCommand(ExtraHelpColorsMixin, Command):  # type: ignore[misc]
    """Like ``cloup.command``, with sane defaults and extra help screen colorization."""

    context_class: type[cloup.Context] = ExtraContext

    def __init__(
        self,
        *args,
        version: str | None = None,
        extra_option_at_end: bool = True,
        populate_auto_envvars: bool = True,
        **kwargs: Any,
    ) -> None:
        """List of extra parameters:

        :param version: allows a version string to be set directly on the command. Will
            be passed to the first instance of ``ExtraVersionOption`` parameter
            attached to the command.
        :param extra_option_at_end: `reorders all parameters attached to the command
            <https://kdeldycke.github.io/click-extra/commands.html#option-order>`_, by
            moving all instances of ``ExtraOption`` at the end of the parameter list.
            The original order of the options is preserved among themselves.
        :param populate_auto_envvars: forces all parameters to have their auto-generated
            environment variables registered. This address the shortcoming of ``click``
            which only evaluates them dynamiccaly. By forcing their registration, the
            auto-generated environment variables gets displayed in the help screen,
            fixing `click#2483 issue <https://github.com/pallets/click/issues/2483>`_.

        By default, these `Click context settings
        <https://click.palletsprojects.com/en/8.1.x/api/#click.Context>`_ are applied:

        - ``auto_envvar_prefix = self.name`` (*Click feature*)

          Auto-generate environment variables for all options, using the command ID as
          prefix. The prefix is normalized to be uppercased and all non-alphanumerics
          replaced by underscores.

        - ``help_option_names = ("--help", "-h")`` (*Click feature*)

          `Allow help screen to be invoked with either --help or -h options
          <https://click.palletsprojects.com/en/8.1.x/documentation/#help-parameter-customization>`_.

        - ``show_default = True`` (*Click feature*)

          `Show all default values
          <https://click.palletsprojects.com/en/8.1.x/api/#click.Context.show_default>`_
          in help screen.

        Additionally, these `Cloup context settings
        <https://cloup.readthedocs.io/en/stable/pages/formatting.html#formatting-settings>`_
        are set:

        - ``align_option_groups = False`` (*Cloup feature*)

          `Aligns option groups in help screen
          <https://cloup.readthedocs.io/en/stable/pages/option-groups.html#aligned-vs-non-aligned-groups>`_.

        - ``show_constraints = True`` (*Cloup feature*)

          `Show all constraints in help screen
          <https://cloup.readthedocs.io/en/stable/pages/constraints.html#the-constraint-decorator>`_.

        - ``show_subcommand_aliases = True`` (*Cloup feature*)

          `Show all subcommand aliases in help screen
          <https://cloup.readthedocs.io/en/stable/pages/aliases.html?highlight=show_subcommand_aliases#help-output-of-the-group>`_.

        Click Extra also adds its own ``context_settings``:

        - ``show_choices = None`` (*Click Extra feature*)

          If set to ``True`` or ``False``, will force that value on all options, so we
          can globally show or hide choices when prompting a user for input. Only makes
          sense for options whose ``prompt`` property is set.

          Defaults to ``None``, which will leave all options untouched, and let them
          decide of their own ``show_choices`` setting.

        - ``show_envvar = None`` (*Click Extra feature*)

          If set to ``True`` or ``False``, will force that value on all options, so we
          can globally enable or disable the display of environment variables in help
          screen.

          Defaults to ``None``, which will leave all options untouched, and let them
          decide of their own ``show_envvar`` setting. The rationale being that
          discoverability of environment variables is enabled by the ``--show-params``
          option, which is active by default on extra commands. So there is no need to
          surcharge the help screen.

          This addresses the
          `click#2313 issue <https://github.com/pallets/click/issues/2313>`_.

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

        # List of additional global settings for options.
        extra_option_settings = [
            "show_choices",
            "show_envvar",
        ]

        default_ctx_settings: dict[str, Any] = {
            # Click settings:
            # "default_map": {"verbosity": "DEBUG"},
            "help_option_names": ("--help", "-h"),
            "show_default": True,
            # Cloup settings:
            "align_option_groups": False,
            "show_constraints": True,
            "show_subcommand_aliases": True,
            # Click Extra settings:
            "show_choices": None,
            "show_envvar": None,
        }

        # Generate environment variables for all options based on the command name.
        if self.name:
            default_ctx_settings["auto_envvar_prefix"] = normalize_envvar(self.name)

        # Merge defaults and user settings.
        default_ctx_settings.update(self.context_settings)

        # If set, force extra settings on all options.
        for setting in extra_option_settings:
            if default_ctx_settings[setting] is not None:
                for param in self.params:
                    # These attributes are specific to options.
                    if isinstance(param, click.Option):
                        param.show_envvar = default_ctx_settings[setting]

        # Remove Click Extra-specific settings, before passing it to Cloup and Click.
        for setting in extra_option_settings:
            del default_ctx_settings[setting]
        self.context_settings: dict[str, Any] = default_ctx_settings

        if populate_auto_envvars:
            for param in self.params:
                param.envvar = all_envvars(param, self.context_settings)

        if version:
            version_param = search_params(self.params, ExtraVersionOption)
            if version_param:
                version_param.version = version  # type: ignore[union-attr]

        if extra_option_at_end:
            self.params.sort(key=lambda p: isinstance(p, ExtraOption))

        # Forces re-identification of grouped and non-grouped options as we re-ordered
        # them above and added our own extra options since initialization.
        _grouped_params = self._group_params(self.params)  # type: ignore[attr-defined]
        self.arguments, self.option_groups, self.ungrouped_options = _grouped_params

    def main(self, *args, **kwargs):
        """Pre-invocation step that is instantiating the context, then call ``invoke()``
        within it.

        During context instantiation, each option's callbacks are called. Beware that
        these might break the execution flow (like ``--help`` or ``--version``).
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
        # ``args`` needs to be copied: its items are consumed by the parsing process.
        extra.update({"meta": {"click_extra.raw_args": args.copy()}})
        return super().make_context(info_name, args, parent, **extra)

    def invoke(self, ctx: click.Context) -> Any:
        """Main execution of the command, just after the context has been instantiated
        in ``main()``.
        """
        return super().invoke(ctx)


class ExtraGroup(ExtraCommand, Group):  # type: ignore[misc]
    """Like``cloup.Group``, with sane defaults and extra help screen colorization."""

    command_class = ExtraCommand
    """Makes commands of an ``ExtraGroup`` be instances of ``ExtraCommand``.

    That way all subcommands created from an ``ExtraGroup`` benefits from the same
    defaults and extra help screen colorization.

    See: https://click.palletsprojects.com/en/8.1.x/api/#click.Group.command_class
    """

    group_class = type
    """Let ``ExtraGroup`` produce sub-groups that are also of ``ExtraGroup`` type.

    See: https://click.palletsprojects.com/en/8.1.x/api/#click.Group.group_class
    """
