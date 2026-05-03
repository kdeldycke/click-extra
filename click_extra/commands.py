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
from difflib import get_close_matches

import click
import cloup

from . import context
from .colorize import (
    ColorOption,
    ExtraHelpColorsMixin,
    HelpKeywords,
)
from .config import (
    DEFAULT_SUBCOMMANDS_KEY,
    PREPEND_SUBCOMMANDS_KEY,
    ConfigOption,
    NoConfigOption,
    ValidateConfigOption,
    _make_schema_callable,
)
from .context import ExtraContext
from .envvar import clean_envvar_id, param_envvar_ids
from .logging import VerboseOption, VerbosityOption
from .parameters import ExtraOption, ShowParamsOption
from .table import TableFormatOption
from .theme import ThemeOption
from .timer import TimerOption
from .version import ExtraVersionOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any, NoReturn


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
    #. ``--validate-config CONFIG_PATH``
    #. ``--color``, ``--ansi`` / ``--no-color``, ``--no-ansi``
    #. ``--theme``
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
        ThemeOption(),
        ConfigOption(),
        NoConfigOption(),
        ValidateConfigOption(),
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
        version_fields: dict[str, Any] | None = None,
        config_schema: type | Callable[[dict[str, Any]], Any] | None = None,
        schema_strict: bool = False,
        fallback_sections: Sequence[str] = (),
        included_params: Sequence[str] | None = None,
        extra_option_at_end: bool = True,
        populate_auto_envvars: bool = True,
        extra_keywords: HelpKeywords | None = None,
        excluded_keywords: HelpKeywords | None = None,
        **kwargs: Any,
    ) -> None:
        """List of extra parameters:

        :param version_fields: dictionary of
            ``ExtraVersionOption`` template field overrides forwarded to the
            version option.  Accepts any field from
            ``ExtraVersionOption.template_fields`` (e.g. ``prog_name``,
            ``version``, ``git_branch``).  Lets you customize ``--version``
            output from the command decorator without replacing the default
            ``params`` list.
        :param extra_keywords: a ``HelpKeywords`` instance whose entries are
            merged into the auto-collected keyword set. Use this to inject
            additional strings for help screen highlighting.
        :param excluded_keywords: a ``HelpKeywords`` instance whose entries are
            removed from the auto-collected keyword set. Use this to suppress
            highlighting of specific strings.
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

        # Forward keyword overrides to the ExtraHelpColorsMixin attributes.
        if extra_keywords is not None:
            self.extra_keywords = extra_keywords
        if excluded_keywords is not None:
            self.excluded_keywords = excluded_keywords

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

        # Forward version template fields to the version option.
        if version_fields:
            for param in self.params:
                if isinstance(param, ExtraVersionOption):
                    for field_id, field_value in version_fields.items():
                        if field_id not in param.template_fields:
                            msg = (
                                f"Unknown version field {field_id!r}."
                                f" Must be one of {param.template_fields}."
                            )
                            raise TypeError(msg)
                        setattr(param, field_id, field_value)

        # Forward config option parameters to the ConfigOption instance.
        if (
            config_schema is not None
            or schema_strict
            or fallback_sections
            or included_params is not None
        ):
            for param in self.params:
                if isinstance(param, ConfigOption):
                    if included_params is not None:
                        param.included_params = frozenset(included_params)
                    if schema_strict:
                        param.schema_strict = schema_strict
                    if config_schema is not None:
                        param.config_schema = config_schema
                        param._config_schema_callable = _make_schema_callable(
                            config_schema,
                            strict=param.schema_strict,
                        )
                    if fallback_sections:
                        param.fallback_sections = tuple(fallback_sections)

        if populate_auto_envvars:
            for param in self.params:
                param.envvar = param_envvar_ids(param, self.context_settings)

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
    ) -> Any:
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
        :data:`click_extra.context.RAW_ARGS` entry. This will be used in
        ``ShowParamsOption.print_params()`` to print the table of parameters fed to the
        CLI.

        .. seealso::
            This workaround is being discussed upstream in `click#1279
            <https://github.com/pallets/click/issues/1279#issuecomment-1493348208>`_.
        """
        # ``args`` needs to be copied: its items are consumed by the parsing process.
        extra.update({"meta": {context.RAW_ARGS: args.copy()}})
        return super().make_context(info_name, args, parent, **extra)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Like parent's ``parse_args`` but with better error messages for
        single-dash multi-character tokens.
        """
        original_args = args.copy()
        try:
            return super().parse_args(ctx, args)
        except click.NoSuchOption as exc:
            _enhance_short_option_error(exc, original_args, ctx)

    def invoke(self, ctx: click.Context) -> Any:
        """Main execution of the command, just after the context has been instantiated
        in ``main()``.
        """
        return super().invoke(ctx)


def _enhance_short_option_error(
    exc: click.NoSuchOption,
    original_args: list[str],
    ctx: click.Context,
) -> NoReturn:
    """Re-raise *exc* with the full token and close-match suggestions when
    appropriate, or re-raise it unchanged.

    Click's parser treats ``-dbgwrong`` as stacked short flags ``-d -b -g -w
    -r -o -n -g``, then reports "No such option: -d" on the first unregistered
    character.  That is technically correct (short-option combining is POSIX
    behaviour) but confusing when the user meant it as a single option name.

    This function detects that situation by checking whether the failed character
    is the *first* character of a multi-char single-dash token from the original
    argument list.  If so, it collects every registered option name and uses
    ``difflib.get_close_matches`` to suggest alternatives, then raises a new
    ``NoSuchOption`` with the full token.

    When the failed character is *not* the leading character (the user was
    genuinely combining short flags and one of them doesn't exist), the original
    exception is re-raised as-is: Click's per-character diagnostic is already
    the right message.

    .. seealso::
        - Upstream issue: https://github.com/pallets/click/issues/2779
        - ``_match_short_opt`` in Click's ``parser.py`` raises ``NoSuchOption``
          with only the single failed character.
        - ``_match_long_opt`` already provides ``get_close_matches`` suggestions,
          but its exception is discarded when ``_process_opts`` falls through to
          the short-option path.
        - Upstream docs PR: https://github.com/pallets/click/pull/3179
        - Rejected upstream code PRs (all tried to patch ``parser.py`` instead of
          adding the requested docs):
          https://github.com/pallets/click/pull/3207 ,
          https://github.com/pallets/click/pull/3236 ,
          https://github.com/pallets/click/pull/3339
    """
    option_name = exc.option_name

    # Only enhance single-char short-option errors (like "-d").
    # Long-option errors ("--foo") already carry the full name and suggestions
    # from Click's _match_long_opt.
    if not (len(option_name) == 2 and option_name[0] == "-" and option_name[1] != "-"):
        raise exc

    failed_char = option_name[1]

    # Find the original multi-char token whose *first* character (after the
    # dash) is the one that failed.  That means the whole token was never
    # partially consumed as stacked short flags: it was one thing the user
    # typed, and Click split it character-by-character without matching
    # anything.
    original_token = None
    for arg in original_args:
        if len(arg) > 2 and arg[0] == "-" and arg[1] != "-" and arg[1] == failed_char:
            original_token = arg
            break

    if original_token is None:
        raise exc

    # Collect every registered option name for close-match suggestions.
    all_option_names: list[str] = []
    for param in ctx.command.params:
        if isinstance(param, click.Option):
            all_option_names.extend(param.opts)
            all_option_names.extend(param.secondary_opts)

    possibilities = get_close_matches(original_token, all_option_names)

    raise click.NoSuchOption(original_token, possibilities=possibilities, ctx=ctx)


class ColorizedCommand(ExtraHelpColorsMixin, click.Command):  # type: ignore[misc]
    """Click Command with help colorization but no extra params.

    Mixes in :class:`~click_extra.colorize.ExtraHelpColorsMixin` for keyword
    highlighting and uses :class:`ExtraContext` for the colorized formatter,
    without inheriting from ``ExtraCommand`` (which would inject
    ``default_extra_params``).

    Use this as a base for lightweight subcommands (like ``help``) or for
    monkey-patching third-party CLIs (via :func:`~click_extra.wrap.patch_click`).
    """

    context_class: type[cloup.Context] = ExtraContext


class ColorizedGroup(ExtraHelpColorsMixin, click.Group):  # type: ignore[misc]
    """Click Group with help colorization but no extra params.

    Same as :class:`ColorizedCommand` but for groups.
    """

    context_class: type[cloup.Context] = ExtraContext


class HelpCommand(ColorizedCommand):
    """Synthetic subcommand that displays help for the parent group or a subcommand.

    Auto-injected into every ``ExtraGroup``. Supports nested resolution:
    ``mycli help subgroup subcmd`` shows the help for ``subcmd`` within
    ``subgroup``.
    """

    def invoke(self, ctx: click.Context) -> None:
        """Resolve the command path and display its help."""
        command_path: tuple[str, ...] = ctx.params["command_path"]
        search_term: str | None = ctx.params.get("search")

        parent_ctx = ctx.parent
        assert parent_ctx is not None
        group = parent_ctx.command
        assert isinstance(group, click.Group)

        if search_term:
            self._search(parent_ctx, group, search_term)
            ctx.exit()

        # No command path: show the group's own help.
        if not command_path:
            click.echo(group.get_help(parent_ctx), color=parent_ctx.color)
            ctx.exit()

        # Walk the command path to find the target.
        target_cmd: click.Command = group
        target_ctx = parent_ctx
        for name in command_path:
            if not isinstance(target_cmd, click.Group):
                raise click.UsageError(
                    f"Command {target_cmd.name!r} has no subcommands.",
                    ctx=parent_ctx,
                )
            resolved = target_cmd.get_command(target_ctx, name)
            if resolved is None:
                raise click.UsageError(
                    f"No such command {name!r}.",
                    ctx=parent_ctx,
                )
            target_ctx = click.Context(
                resolved,
                parent=target_ctx,
                info_name=name,
            )
            target_cmd = resolved

        click.echo(target_cmd.get_help(target_ctx), color=parent_ctx.color)
        ctx.exit()

    def _search(
        self,
        group_ctx: click.Context,
        group: click.Group,
        term: str,
    ) -> None:
        """Search all subcommands for options or descriptions matching *term*."""
        from .colorize import highlight
        from .theme import get_current_theme

        term_lower = term.lower()
        results: list[tuple[str, str]] = []

        self._search_group(group_ctx, group, term_lower, "", results)

        if not results:
            click.echo(f"No commands matching {term!r}.")
            return

        styling_func = get_current_theme().search
        for cmd_path, line in results:
            styled_line = highlight(line, [term], styling_func, ignore_case=True)
            click.echo(f"  {cmd_path}: {styled_line}", color=group_ctx.color)

    def _search_group(
        self,
        group_ctx: click.Context,
        group: click.Group,
        term_lower: str,
        prefix: str,
        results: list[tuple[str, str]],
    ) -> None:
        """Recursively search a group's subcommands."""
        for sub_name in group.list_commands(group_ctx):
            if sub_name == "help":
                continue
            sub_cmd = group.get_command(group_ctx, sub_name)
            if sub_cmd is None:
                continue

            cmd_path = f"{prefix}{sub_name}" if prefix else sub_name
            sub_ctx = click.Context(
                sub_cmd,
                parent=group_ctx,
                info_name=sub_name,
            )

            # Check command docstring.
            if sub_cmd.help and term_lower in sub_cmd.help.lower():
                results.append((cmd_path, sub_cmd.help))

            # Check each parameter.
            for param in sub_cmd.get_params(sub_ctx):
                opts_str = " / ".join(getattr(param, "opts", []))
                help_str = getattr(param, "help", None) or ""
                combined = f"{opts_str}  {help_str}".strip()
                if term_lower in combined.lower():
                    results.append((cmd_path, combined))

            # Recurse into nested groups.
            if isinstance(sub_cmd, click.Group):
                self._search_group(
                    sub_ctx,
                    sub_cmd,
                    term_lower,
                    f"{cmd_path} ",
                    results,
                )


def _make_help_command() -> HelpCommand:
    """Create the synthetic ``help`` subcommand for an ``ExtraGroup``."""
    return HelpCommand(
        name="help",
        help="Show help for a command.",
        params=[
            click.Argument(["command_path"], nargs=-1, required=False),
            click.Option(
                ["--search"],
                default=None,
                help="Search all subcommands for matching options or descriptions.",
            ),
        ],
        context_settings={"auto_envvar_prefix": None},
    )


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

    def __init__(
        self,
        *args: Any,
        help_command: bool = True,
        **kwargs: Any,
    ) -> None:
        """Like ``ExtraCommand.__init__``, but auto-injects a ``help`` subcommand.

        :param help_command: when ``True`` (the default), a ``help`` subcommand is
            automatically registered.  Set to ``False`` to suppress it, or register
            your own ``help`` subcommand to override it.
        """
        super().__init__(*args, **kwargs)
        if help_command and "help" not in self.commands:
            self.add_command(_make_help_command())

    def add_command(  # type: ignore[override]
        self,
        cmd: click.Command,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Like ``cloup.Group.add_command``, but replaces an auto-injected
        ``HelpCommand`` when the user registers their own ``help`` subcommand.
        """
        cmd_name = name or cmd.name
        if cmd_name and cmd_name in self.commands:
            existing = self.commands[cmd_name]
            if isinstance(existing, HelpCommand) and not isinstance(cmd, HelpCommand):
                # Remove the auto-injected help from its Cloup section so the
                # user's command can take its place without a duplicate error.
                for section in self._user_sections:
                    if cmd_name in section.commands:
                        del section.commands[cmd_name]
                        break
                else:
                    if cmd_name in self._default_section.commands:
                        del self._default_section.commands[cmd_name]
                del self.commands[cmd_name]
        super().add_command(cmd, name, **kwargs)

    def invoke(self, ctx: click.Context) -> Any:
        """Inject ``_default_subcommands`` and ``_prepend_subcommands`` from config.

        If the user has not provided any subcommands explicitly, and the loaded
        configuration contains a ``_default_subcommands`` list for this group, those
        subcommands are injected into ``ctx.protected_args`` so that Click's normal
        ``Group.invoke()`` dispatches them.

        ``_prepend_subcommands`` always prepends subcommands to the invocation,
        regardless of whether CLI subcommands were provided. Only works with
        ``chain=True`` groups.
        """
        if not ctx._protected_args and not ctx.args:
            default_subcmds = self._get_default_subcommands(ctx)
            if default_subcmds is not None:
                ctx._protected_args = list(default_subcmds)
        elif ctx._protected_args or ctx.args:
            # CLI subcommands were given explicitly; log if config defaults exist.
            default_subcmds = self._get_default_subcommands(ctx)
            if default_subcmds is not None:
                logger = logging.getLogger("click_extra")
                logger.debug(
                    f"CLI subcommands provided; ignoring {DEFAULT_SUBCOMMANDS_KEY}"
                    f" config: {default_subcmds!r}."
                )

        # Always prepend _prepend_subcommands, regardless of CLI args.
        prepend_subcmds = self._get_prepend_subcommands(ctx)
        if prepend_subcmds is not None:
            logger = logging.getLogger("click_extra")
            logger.info(
                f"Prepending {PREPEND_SUBCOMMANDS_KEY} config: {prepend_subcmds!r}."
            )
            ctx._protected_args = list(prepend_subcmds) + ctx._protected_args

        return super().invoke(ctx)

    def _get_default_subcommands(self, ctx: click.Context) -> list[str] | None:
        """Read and validate ``_default_subcommands`` from the loaded configuration."""
        full_config = ctx.meta.get(context.CONF_FULL)
        if not full_config:
            return None

        root_ctx = ctx.find_root()
        config_branch = full_config.get(root_ctx.command.name)
        if not isinstance(config_branch, dict):
            return None

        # Walk from root context down to the current group.
        path: list[str] = []
        current: click.Context | None = ctx
        while current is not None and current is not root_ctx:
            if current.command.name is not None:
                path.append(current.command.name)
            current = current.parent
        path.reverse()

        for segment in path:
            config_branch = config_branch.get(segment)
            if not isinstance(config_branch, dict):
                return None

        raw = config_branch.get(DEFAULT_SUBCOMMANDS_KEY)
        if raw is None:
            return None

        # Validate type.
        if not isinstance(raw, list) or not all(isinstance(s, str) for s in raw):
            raise click.UsageError(
                f"{DEFAULT_SUBCOMMANDS_KEY} must be a list of strings, got {raw!r}."
            )

        if not raw:
            return None

        # Deduplicate, keeping first occurrence, and warn on duplicates.
        seen: set[str] = set()
        deduped: list[str] = []
        for name in raw:
            if name in seen:
                continue
            seen.add(name)
            deduped.append(name)
        if len(deduped) < len(raw):
            logger = logging.getLogger("click_extra")
            logger.warning(
                f"Duplicate entries in {DEFAULT_SUBCOMMANDS_KEY}: {raw!r}. "
                f"Keeping first occurrences: {deduped!r}."
            )
        raw = deduped

        # Non-chained groups can only have one default subcommand.
        if not self.chain and len(raw) > 1:
            raise click.UsageError(
                f"Non-chained group {self.name!r} can have at most 1 default "
                f"subcommand, got {len(raw)}: {raw!r}."
            )

        # Validate that all subcommands exist.
        for name in raw:
            if self.get_command(ctx, name) is None:
                raise click.UsageError(
                    f"Default subcommand {name!r} not found in group {self.name!r}."
                )

        return raw

    def _get_prepend_subcommands(self, ctx: click.Context) -> list[str] | None:
        """Read and validate ``_prepend_subcommands`` from the loaded configuration."""
        full_config = ctx.meta.get(context.CONF_FULL)
        if not full_config:
            return None

        root_ctx = ctx.find_root()
        config_branch = full_config.get(root_ctx.command.name)
        if not isinstance(config_branch, dict):
            return None

        # Walk from root context down to the current group.
        path: list[str] = []
        current: click.Context | None = ctx
        while current is not None and current is not root_ctx:
            if current.command.name is not None:
                path.append(current.command.name)
            current = current.parent
        path.reverse()

        for segment in path:
            config_branch = config_branch.get(segment)
            if not isinstance(config_branch, dict):
                return None

        raw = config_branch.get(PREPEND_SUBCOMMANDS_KEY)
        if raw is None:
            return None

        # Validate type.
        if not isinstance(raw, list) or not all(isinstance(s, str) for s in raw):
            raise click.UsageError(
                f"{PREPEND_SUBCOMMANDS_KEY} must be a list of strings, got {raw!r}."
            )

        if not raw:
            return None

        # Prepend subcommands only work with chained groups.
        if not self.chain:
            raise click.UsageError(
                f"{PREPEND_SUBCOMMANDS_KEY} requires chain=True on group {self.name!r}."
            )

        # Deduplicate, keeping first occurrence, and warn on duplicates.
        seen: set[str] = set()
        deduped: list[str] = []
        for name in raw:
            if name in seen:
                continue
            seen.add(name)
            deduped.append(name)
        if len(deduped) < len(raw):
            logger = logging.getLogger("click_extra")
            logger.warning(
                f"Duplicate entries in {PREPEND_SUBCOMMANDS_KEY}: {raw!r}. "
                f"Keeping first occurrences: {deduped!r}."
            )
        raw = deduped

        # Validate that all subcommands exist.
        for name in raw:
            if self.get_command(ctx, name) is None:
                raise click.UsageError(
                    f"Prepend subcommand {name!r} not found in group {self.name!r}."
                )

        return raw


class LazyGroup(ExtraGroup):
    """An ``ExtraGroup`` that supports lazy loading of subcommands.

    .. hint::
        This implementation is based on the snippet from Click's documentation:
        `Defining the lazy group
        <https://click.palletsprojects.com/en/stable/complex/#defining-the-lazy-group>`_.

        It has been extended to work with Click Extra's ``config_option`` in
        `click_extra#1332 issue
        <https://github.com/kdeldycke/click-extra/issues/1332#issuecomment-3299486142>`_.
    """

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        """``lazy_subcommands`` maps command names to their import paths.

        .. tip::
            ``lazy_subcommands`` is a map of the form:

            .. code-block:: python

                {"<command-name>": "<module-name>.<command-object-name>"}

            Example:

            .. code-block:: python

                {"mycmd": "my_cli.commands.mycmd"}
        """
        super().__init__(*args, **kwargs)
        # Sort for predictable and stable lazy loading order.
        self.lazy_subcommands: dict[str, str] = (
            dict(sorted(lazy_subcommands.items())) if lazy_subcommands else {}
        )

    def list_commands(self, ctx: click.Context) -> list[str]:
        """List all commands, including not-yet-loaded lazy subcommands."""
        base = super().list_commands(ctx)
        # Only include lazy subcommands that haven't been loaded into
        # self.commands yet (add_command moves them there).
        lazy = [name for name in self.lazy_subcommands if name not in self.commands]
        return sorted(base + lazy)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Get a command by name, loading lazily if necessary.

        .. todo::
            Allow passing extra parameters to the ``self.lazy_subcommands`` so we can
            register commands with custom settings like Cloup's ``section`` or
            ``fallback_to_default_section``:

            - section: Optional[Section] = None,
            - fallback_to_default_section: bool = True,

            See: https://github.com/janluke/cloup/blob/master/cloup/_sections.py#L169
        """
        if cmd_name in self.lazy_subcommands and cmd_name not in self.commands:
            cmd_object = self._lazy_load(cmd_name)
            # Register with Click's API so help and Cloup sections work properly.
            self.add_command(cmd_object)
            # Inject the lazy command's config section into the context's
            # default_map, since it was missed by ConfigOption.merge_default_map.
            self._apply_config_to_parent_context(ctx, cmd_name)

        return super().get_command(ctx, cmd_name)

    def _lazy_load(self, cmd_name: str) -> click.Command:
        """Import and return the command object for ``cmd_name``."""
        import_path = self.lazy_subcommands[cmd_name]

        if "." not in import_path:
            raise ValueError(
                f"Lazy subcommand {cmd_name!r} has invalid import path "
                f"{import_path!r}: expected 'module.attribute' form."
            )

        modname, cmd_object_name = import_path.rsplit(".", 1)
        mod = importlib.import_module(modname)
        cmd_object = getattr(mod, cmd_object_name)
        if not isinstance(cmd_object, click.Command):
            raise TypeError(
                f"Lazy loading of {import_path!r} failed by returning a non-command "
                f"object: {cmd_object!r}"
            )

        # Override name with the lazy_subcommands key, since the imported
        # command object may have a different name.
        cmd_object.name = cmd_name
        return cmd_object

    def _apply_config_to_parent_context(
        self, ctx: click.Context, cmd_name: str
    ) -> None:
        """Inject a lazy command's config into ``ctx.default_map``.

        Lazy commands are not yet registered when ``ConfigOption.merge_default_map``
        builds ``params_template``, so their config sections get filtered out. This
        method compensates by reading the full config from ``ctx.meta`` and placing
        the lazy command's section into ``ctx.default_map[cmd_name]``.

        Click will then pass that dict as the ``default_map`` of the command's own
        context.
        """
        full_config = ctx.meta.get(context.CONF_FULL)
        if not full_config:
            return

        # Descend into the root command's config section.
        root_ctx = ctx.find_root()
        config_branch = full_config.get(root_ctx.command.name)
        if not isinstance(config_branch, dict):
            return

        # For nested lazy groups, walk from the current context up to the root
        # to collect intermediate group names, then descend through the config.
        path: list[str] = []
        current: click.Context | None = ctx
        while current is not None and current is not root_ctx:
            if current.command.name is not None:
                path.append(current.command.name)
            current = current.parent
        path.reverse()

        for segment in path:
            config_branch = config_branch.get(segment)
            if not isinstance(config_branch, dict):
                return

        # Extract the lazy command's config section.
        cmd_config = config_branch.get(cmd_name)
        if not isinstance(cmd_config, dict):
            return

        if ctx.default_map is None:
            ctx.default_map = {}
        ctx.default_map.setdefault(cmd_name, {}).update(cmd_config)

        logging.getLogger("click_extra").debug(
            f"Lazy config for {cmd_name!r}: {cmd_config}"
        )
