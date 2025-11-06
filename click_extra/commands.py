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

import importlib
import logging
from collections import OrderedDict

import click
import cloup

from .colorize import ColorOption, ExtraHelpColorsMixin, HelpExtraFormatter
from .config import ConfigOption, NoConfigOption
from .envvar import clean_envvar_id, param_envvar_ids
from .logging import VerboseOption, VerbosityOption
from .parameters import ExtraOption, ShowParamsOption, search_params
from .table import TableFormatOption
from .timer import TimerOption
from .version import ExtraVersionOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any, NoReturn


class ExtraContext(cloup.Context):
    """Like ``cloup._context.Context``, but with the ability to populate the context's
    ``meta`` property at instantiation.

    Also inherits ``color`` property from parent context. And sets it to `True` for
    parentless contexts at instantiatiom, so we can always have colorized output.

    .. todo::
        Propose addition of ``meta`` keyword upstream to Click.
    """

    formatter_class = HelpExtraFormatter
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


def default_extra_params() -> list[click.Option]:
    """Default additional options added to ``@command`` and ``@group``.

    .. caution::
        The order of options has been carefully crafted to handle subtle edge-cases and
        avoid leaky states in unittests.

        You can still override this hard-coded order for easthetic reasons and it
        should be fine. Your end-users are unlikely to be affected by these sneaky
        bugs, as the CLI context is going to be naturraly reset after each
        invocation (which is not the case in unitests).

    #. ``--time`` / ``--no-time``
        .. hint::
            ``--time`` is placed at the top of all other eager options so all other
            options' processing time can be measured.
    #. ``--config CONFIG_PATH``
        .. hint::
            ``--config`` is at the top so it can have a direct influence on the default
            behavior and value of the other options.
    #. ``--no-config``
    #. ``--color``, ``--ansi`` / ``--no-color``, ``--no-ansi``
    #. ``--show-params``
    #. ``--table-format FORMAT``
    #. ``--verbosity LEVEL``
    #. ``-v``, ``--verbose``
    #. ``--version``
    #. ``-h``, ``--help``
        .. attention::
            This is the option produced by the `@click.decorators.help_option
            <https://click.palletsprojects.com/en/stable/api/#click.help_option>`_
            decorator.

            It is not explicitly referenced in the implementation of this function.

            That's because it's `going to be added by Click itself
            <https://github.com/pallets/click/blob/c9f7d9d/src/click/core.py#L966-L969>`_,
            at the end of the list of options. By letting Click handle this, we ensure
            that the help option will take into account the `help_option_names
            <https://click.palletsprojects.com/en/stable/documentation/#help-parameter-customization>`_
            setting.

    .. important::
        Sensitivity to order still remains to be proven. With the code of Click Extra
        and its dependencies moving fast, there is a non-zero chance that all the
        options are now sound enough to be re-ordered in a more natural way.

    .. todo::
        For bullet-proof handling of edge-cases, we should probably add an indirection
        layer to have the processing order of options (the one below) different from
        the presentation order of options in the help screen.

        This is probably something that has been `requested in issue #544
        <https://github.com/kdeldycke/click-extra/issues/544>`_.
    """
    return [
        TimerOption(),
        ColorOption(),
        ConfigOption(),
        NoConfigOption(),
        ShowParamsOption(),
        TableFormatOption(),
        VerbosityOption(),
        VerboseOption(),
        ExtraVersionOption(),
        # @click.decorators.help_option(),
    ]


DEFAULT_HELP_NAMES: tuple[str, ...] = ("--help", "-h")


class ExtraCommand(ExtraHelpColorsMixin, cloup.Command):  # type: ignore[misc]
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
            On Windows, environment variable names are case-insensitive, so we normalize
            them to uppercase.

        By default, these `Click context settings
        <https://click.palletsprojects.com/en/stable/api/#click.Context>`_ are applied:

        - ``auto_envvar_prefix = self.name`` (*Click feature*)

          Auto-generate environment variables for all options, using the command ID as
          prefix. The prefix is normalized to be uppercased and all non-alphanumerics
          replaced by underscores.

        - ``help_option_names = ("--help", "-h")`` (*Click feature*)

          `Allow help screen to be invoked with either --help or -h options
          <https://click.palletsprojects.com/en/stable/documentation/#help-parameter-customization>`_.

        - ``show_default = True`` (*Click feature*)

          `Show all default values
          <https://click.palletsprojects.com/en/stable/api/#click.Context.show_default>`_
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

            @command(
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
            "help_option_names": DEFAULT_HELP_NAMES,
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
            default_ctx_settings["auto_envvar_prefix"] = clean_envvar_id(self.name)

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
                param.envvar = param_envvar_ids(param, self.context_settings)

        if version:
            version_param = search_params(self.params, ExtraVersionOption)
            if version_param:
                version_param.version = version  # type: ignore[union-attr]

        if extra_option_at_end:
            self.params.sort(key=lambda p: isinstance(p, ExtraOption))

        # Forces re-identification of grouped and non-grouped options as we re-ordered
        # them above and added our own extra options since initialization.
        _grouped_params = self._group_params(self.params)
        self.arguments, self.option_groups, self.ungrouped_options = _grouped_params

    def main(  # type: ignore[override]
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        **kwargs: Any,
    ) -> Any | NoReturn:
        """Pre-invocation step that is instantiating the context, then call ``invoke()``
        within it.

        .. caution::
            During context instantiation, each option's callbacks are called. These
            might break the execution flow (like ``--help`` or ``--version``).

        Sets the default CLI's ``prog_name`` to the command's name if not provided,
        instead of relying on Click's auto-detection via the
        ``_detect_program_name()`` method. This is to avoid the CLI being called
        ``python -m <module_name>``, which is not very user-friendly.
        """
        if not prog_name and self.name:
            prog_name = self.name

        return super().main(args=args, prog_name=prog_name, **kwargs)

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: Any,
    ) -> Any:
        """Intercept the call to the original ``click.core.Command.make_context`` so
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


class ExtraGroup(ExtraCommand, cloup.Group):  # type: ignore[misc]
    """Like ``cloup.Group``, with sane defaults and extra help screen colorization."""

    command_class = ExtraCommand
    """Makes commands of an ``ExtraGroup`` be instances of ``ExtraCommand``.

    That way all subcommands created from an ``ExtraGroup`` benefits from the same
    defaults and extra help screen colorization.

    See: https://click.palletsprojects.com/en/stable/api/#click.Group.command_class
    """

    group_class = type
    """Let ``ExtraGroup`` produce sub-groups that are also of ``ExtraGroup`` type.

    See: https://click.palletsprojects.com/en/stable/api/#click.Group.group_class
    """


class LazyGroup(ExtraGroup):
    """An ``ExtraGroup`` that supports lazy loading of subcommands.

    This implementation adds special handling for ``config_option`` to ensure
    configuration values are passed to lazily loaded commands correctly.

    .. hint::
        This implementation is based on the snippet from Click's documentation:
        `Defining the lazy group
        <https://click.palletsprojects.com/en/stable/complex/#defining-the-lazy-group>`_.

        And has been adapted to work with Click Extra's ``config_option`` in
        `click_extra#1332 issue
        <https://github.com/kdeldycke/click-extra/issues/1332#issuecomment-3299486142>`_.
    """

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the ``LazyGroup``.

        Args:
            *args: Positional arguments for the parent class.
            lazy_subcommands (dict, optional): Mapping of command names to import paths.
            **kwargs: Keyword arguments for the parent class.

        .. tip::
            ``lazy_subcommands`` is a map of the form:

            .. code-block:: python

                {"<command-name>": "<module-name>.<command-object-name>"}

            Example:

            .. code-block:: python

                {"mycmd": "my_cli.commands.mycmd"}
        """
        super().__init__(*args, **kwargs)
        # Explicitly sort lazy subcommands so we have a predictable and stable
        # lazy loading order.
        self.lazy_subcommands = (
            OrderedDict(sorted(lazy_subcommands.items())) if lazy_subcommands else {}
        )

    def list_commands(self, ctx: click.Context) -> list[str]:
        """List all commands, including lazy subcommands.

        Returns the list of command names, including the lazy-loaded.
        """
        base = super().list_commands(ctx)
        lazy = list(self.lazy_subcommands.keys())
        return base + lazy

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Get a command by name, loading lazily if necessary.

        .. todo::
            Allow passing extra parameters to the ``self.lazy_subcommands`` so we can
            registered commands with custom settings like Cloup's ``section`` or
            ``fallback_to_default_section``:

            - section: Optional[Section] = None,
            - fallback_to_default_section: bool = True,

            See: https://github.com/janluke/cloup/blob/master/cloup/_sections.py#L169
        """
        # Lazily load the command if it's not already registered.
        if cmd_name in self.lazy_subcommands and cmd_name not in self.commands:
            cmd_object = self._lazy_load(ctx, cmd_name)
            # Register the command with Click public API so it triggers the whole Help
            # machinery properly, including the way Cloup initialize its Section system.
            self.add_command(cmd_object)

        return super().get_command(ctx, cmd_name)

    def _lazy_load(self, ctx: click.Context, cmd_name: str) -> click.Command:
        """Lazily load a command from its import path."""
        import_path = self.lazy_subcommands[cmd_name]
        modname, cmd_object_name = import_path.rsplit(".", 1)
        mod = importlib.import_module(modname)
        cmd_object = getattr(mod, cmd_object_name)
        if not isinstance(cmd_object, click.Command):
            raise ValueError(
                f"Lazy loading of {import_path!r} failed by returning a non-command "
                f"object: {cmd_object!r}"
            )

        # Fix for config_option: ensure name is set correctly.
        cmd_object.name = cmd_name

        # Extract and apply config at load time, before any parameter resolution
        self._apply_config_to_parent_context(ctx, cmd_name)

        return cmd_object

    def _apply_config_to_parent_context(
        self, ctx: click.Context, cmd_name: str
    ) -> None:
        """Apply configuration values to the parent context's ``default_map``.

        This is the key fix for ``config_option`` with lazy commands. Instead of trying
        to apply config to the command's context (which doesn't exist yet), we apply it
        to the parent context's default_map with the command name as the key.

        When Click later creates the command's context, it will automatically inherit
        this config through Click's standard context inheritance mechanism.
        """
        logger = logging.getLogger("click_extra")

        try:
            # Skip if no click_extra config was loaded.
            if not ctx or not ctx.meta or "click_extra.conf_full" not in ctx.meta:
                return

            # Get the full configuration loaded by click_extra.
            full_config = ctx.meta["click_extra.conf_full"]
            if not full_config:
                return

            # Get root command name.
            root = ctx.find_root()
            root_name = (
                root.command.name if root.command and root.command.name else None
            )
            if not root_name or root_name not in full_config:
                return

            # Get parent command name (our current group).
            parent_cmd_name = self.name if hasattr(self, "name") else None
            if not parent_cmd_name:
                return

            # Find config for our command.
            try:
                # Start with root config.
                config_branch = full_config[root_name]

                # Navigate to parent group's config.
                current_ctx = ctx
                path_segments: list[str] = []

                # Build path from root to our parent group (excluding root).
                while current_ctx and current_ctx.parent:
                    if current_ctx.command and current_ctx.command.name:
                        if current_ctx.command.name != root_name:  # Skip root command.
                            path_segments.insert(0, current_ctx.command.name)
                    current_ctx = current_ctx.parent

                # Navigate through path segments in config.
                for segment in path_segments:
                    if segment in config_branch and isinstance(
                        config_branch[segment], dict
                    ):
                        config_branch = config_branch[segment]
                    else:
                        # Path doesn't exist in config.
                        return

                # Now check for our command's config.
                if cmd_name in config_branch and isinstance(
                    config_branch[cmd_name], dict
                ):
                    cmd_config = config_branch[cmd_name]

                    # Initialize parent context's default_map if needed
                    if ctx.default_map is None:
                        ctx.default_map = {}

                    # Set up for this command in parent's default_map
                    if cmd_name not in ctx.default_map:
                        ctx.default_map[cmd_name] = {}

                    # Apply the command's config to parent context's default_map.
                    # Click will automatically pass this to the command's context.
                    ctx.default_map[cmd_name].update(cmd_config)
                    logger.debug(f"Config found for {cmd_name}: {cmd_config}")

            # Log error but continue.
            except (KeyError, AttributeError, TypeError) as ex:
                logger.error(f"Error finding config: {ex}")

        # Log error but continue - better to run without config than crash.
        except (KeyError, AttributeError, TypeError) as ex:
            logger.error(f"Error applying config: {ex}")
