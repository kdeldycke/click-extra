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
use the mixins in here to build up your own custom variants.
"""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass
from difflib import get_close_matches
from gettext import gettext as _

import click
import cloup
from click.core import iter_params_for_processing
from cloup.formatting import ensure_is_cloup_formatter

from . import context
from .accessibility import ACCESSIBLE_ENVVAR, AccessibleOption
from .color import ColorOption, NoColorOption, _reset_invocation_color
from .command_doc import HelpFormatOption, ManOption, normalize_examples
from .config import (
    DEFAULT_SUBCOMMANDS_KEY,
    PREPEND_SUBCOMMANDS_KEY,
    ConfigOption,
    ConfigValidator,
    ExportConfigOption,
    NoConfigOption,
    ValidateConfigOption,
    make_schema_callable,
)
from .config.schema import _opaque_paths
from .context import Context
from .envvar import clean_envvar_id, param_envvar_ids
from .execution import TimerOption
from .highlight import HelpKeywords, _HelpColorsMixin, highlight
from .logging import DebugOption, QuietOption, VerboseOption, VerbosityOption
from .parameters import ExtraOption, ShowParamsOption, resolve_param_help
from .spinner import ProgressOption
from .table import TableFormatOption
from .theme import THEME_ENVVAR, ThemeOption, get_current_theme
from .tree import TreeOption
from .version import VersionOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from typing import Any, Final, NoReturn

    from .version import VersionScreen

logger = logging.getLogger(__name__)

DEFAULT_HELP_NAMES: tuple[str, ...] = ("--help", "-h")

DEFAULT_PRIORITY: Final[float] = 100.0
"""Implicit priority of any subcommand or option left unnumbered.

Priorities order the subcommands of a `Group` and the options of a `Command`, lowest
first. Anything the author did not number sits on this line, so a lone `{"prep": 1}`
promotes `prep` without displacing the rest, and a number above `100` demotes.

```{note}
Priorities are floats, not integers, so a new entry can be wedged between two existing
ones without renumbering: `1.5` lands between `1` and `2`.

That trick is as old as interactive computing.
[JOSS](https://en.wikipedia.org/wiki/JOSS), which RAND put online in 1963, required
every line number to be a pair of integers separated by a period (`1.1`, `10.12`): a
page and a line within it, jointly a *step*.
DEC's [FOCAL](https://gunkies.org/wiki/FOCAL) carried the scheme to the PDP-8, with
steps running from `1.01` to `31.99`. BASIC numbered lines with plain integers, and its
`10, 20, 30` convention is programmers buying back the same insertion room by hand.
```
"""

EXTRA_OPTION_SETTINGS: tuple[str, ...] = ("show_choices", "show_envvar")
"""Click Extra context settings forced onto every option when set to non-`None`."""


class ExtraOptionGroup(cloup.OptionGroup):
    """An option group Click Extra draws after the command's own options.

    Cloup lays a help screen out as the explicit option groups first and the
    ungrouped options last. Click Extra injects a score of its own options into
    every command, so grouping them under that rule would push the author's own
    options below click-extra's and retitle them `Other options`.
    {meth}`~click_extra.commands.Command.split_option_groups` sends a group
    carrying this marker past the ungrouped section instead.

    ```{note}
    The marker mirrors {class}`~click_extra.parameters.ExtraOption`, which
    {class}`~click_extra.commands.Command` reads the same way to push
    click-extra's own options to the end of `params`.
    ```

    :param priority: rank of the group among the other trailing groups, lowest
        first. Defaults to {data}`~click_extra.commands.DEFAULT_PRIORITY`, so a
        group a CLI author marks this way lands after click-extra's own.
    """

    def __init__(
        self,
        *args: Any,
        priority: float = DEFAULT_PRIORITY,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.priority = priority


DEFAULT_OPTION_GROUPS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "Configuration options",
        ("--config", "--no-config", "--validate-config", "--export-config"),
    ),
    (
        "Output options",
        (
            "--accessible",
            "--color",
            "--no-color",
            "--progress",
            "--theme",
            "--table-format",
        ),
    ),
    ("Logging options", ("--verbosity", "--verbose", "--quiet", "--debug")),
    (
        "Introspection options",
        ("--time", "--params", "--tree", "--man", "--help-format", "--version"),
    ),
)
"""Sections {func}`default_params` sorts its options into, in rendering order.

Each entry pairs a help-screen heading with the primary flags it collects. The
sequence is the order the sections are drawn in, which
{class}`ExtraOptionGroup` carries as a priority so it survives the reshuffling
`Command` does to `params`.

The last section gathers the options that *replace* the run instead of
configuring it: each one prints and exits. `--time` is the exception, and sits
there because it reports on the run rather than changing what it does.

```{caution}
Membership is declared, not inferred. Deriving it from the callbacks looks
tempting, since each option of the last section ends the run, but `--config`
ends it too when a file fails to load, and would be misfiled.
```

`-h` / `--help` is deliberately absent: Click appends it to every command on its
own, so it stays ungrouped and closes the author's own section, where a reader
looks for it first.
"""


def _assign_option_groups(params: Sequence[click.Option]) -> None:
    """Sort *params* into a fresh set of {data}`DEFAULT_OPTION_GROUPS`.

    ```{caution}
    The groups are built here, once per call, and never shared between commands.
    `cloup.OptionGroup.options` is a *setter* replacing the group's whole member
    list, so a module-level group reused by two commands ends up holding
    whichever was built last, and the first command then renders its sibling's
    option instances. The setter also latches `hidden` on, which would then hide
    every later command's options too.
    ```
    """
    groups = {
        title: ExtraOptionGroup(title, priority=priority)
        for priority, (title, _) in enumerate(DEFAULT_OPTION_GROUPS)
    }
    for title, flags in DEFAULT_OPTION_GROUPS:
        wanted = set(flags)
        for param in params:
            if wanted.intersection((*param.opts, *param.secondary_opts)):
                # `cloup.Option.__init__` carries no annotation, so mypy skips
                # its body and never records the `group` attribute it binds.
                param.group = groups[title]  # type: ignore[attr-defined]


def default_params(screen: VersionScreen | None = None) -> list[click.Option]:
    """Default additional options added to `@command` and `@group`.

    :param screen: a {class}`~click_extra.version.VersionScreen` for `--version` to
        draw in place of its one-line message. Reach it through the `params` hook,
        binding the screen with `functools.partial` so each decorated command still
        gets its own fresh option instances:

        ```{code-block} python
        @group(params=partial(default_params, screen=MY_SCREEN))
        def cli():
            pass
        ```

    ```{caution}
    The order of options has been carefully crafted to handle subtle edge-cases and
    avoid leaky states in unit tests.

    You can still override this hard-coded order for aesthetic reasons and it
    should be fine. Your end-users are unlikely to be affected by these sneaky
    bugs, as the CLI context is going to be naturally reset after each
    invocation (which is not the case in unit tests).
    ```

    #. `--time` / `--no-time`
        ```{hint}
        `--time` is placed at the top of all other eager options so all other
        options' processing time can be measured.
        ```
    #. `--config LOCATION`
        ```{hint}
        `--config` is at the top so it can have a direct influence on the default
        behavior and value of the other options.
        ```
    #. `--no-config`
    #. `--validate-config LOCATION`
    #. `--export-config FORMAT`
    #. `--accessible`
        ```{hint}
        `--accessible` is placed before `--color` and `--table-format` so it
        can lower their defaults (via `default_map`) before they are resolved.
        ```
    #. `--color` / `--no-color`
    #. `--progress` / `--no-progress`
    #. `--theme`
    #. `--params`
    #. `--table-format FORMAT`
    #. `--verbosity LEVEL`
    #. `-v`, `--verbose`
    #. `-q`, `--quiet`
    #. `--tree`
    #. `--man`
    #. `--help-format FORMAT`
    #. `--version`
    #. `-h`, `--help`
        ```{attention}
        This is the option produced by the [@click.decorators.help_option](https://click.palletsprojects.com/en/stable/api/#click.help_option)
        decorator.

        It is not explicitly referenced in the implementation of this function.

        That's because it's [going to be added by Click itself](https://github.com/pallets/click/blob/c9f7d9d/src/click/core.py#L966-L969),
        at the end of the list of options. By letting Click handle this, we ensure
        that the help option will take into account the [help_option_names](https://click.palletsprojects.com/en/stable/documentation/#help-parameter-customization)
        setting.
        ```

    ```{note}
    The list below is the *processing* order, and it is the only one these
    edge-cases care about. The help screen reads a separate presentation order,
    which the `option_priorities` argument of `@command` and `@group` reshuffles
    without touching a single callback. See
    {meth}`~click_extra.commands.Command.param_priority`, added for
    [click_extra#544 issue](https://github.com/kdeldycke/click-extra/issues/544).

    Presentation also sorts these options into the sections
    {data}`DEFAULT_OPTION_GROUPS` declares, drawn after the command's own
    options. The two orders are independent: `--time` is processed first and
    rendered last.
    ```
    """
    params: list[click.Option] = [
        TimerOption(),
        ConfigOption(),
        NoConfigOption(),
        ValidateConfigOption(),
        ExportConfigOption(),
        AccessibleOption(),
        ColorOption(),
        NoColorOption(),
        ProgressOption(),
        ThemeOption(),
        ShowParamsOption(),
        TableFormatOption(),
        VerbosityOption(),
        VerboseOption(),
        QuietOption(),
        DebugOption(),
        TreeOption(),
        ManOption(),
        HelpFormatOption(),
        VersionOption(screen=screen),
    ]
    _assign_option_groups(params)
    return params


class Command(_HelpColorsMixin, cloup.Command):  # type: ignore[misc]
    """Like `cloup.command`, with sane defaults and extra help screen colorization."""

    context_class: type[cloup.Context] = Context

    examples: tuple[tuple[str, str], ...] = ()
    """`(description, command)` pairs showing the command in use.

    Normalized from the `examples` constructor argument by
    {func}`~click_extra.command_doc.normalize_examples`. Declared here so the
    attribute exists on every command, whether or not its author passed any:
    the renderers reading it (help screen, man page, and every
    {data}`~click_extra.command_doc.HELP_FORMATS` backend) then need no guard.
    """

    def __init__(
        self,
        *args,
        version_fields: dict[str, Any] | None = None,
        config_schema: type | Callable[[dict[str, Any]], Any] | None = None,
        config_strict: bool = False,
        schema_strict: bool = False,
        fallback_sections: Sequence[str] = (),
        config_validators: Sequence[ConfigValidator] = (),
        included_params: Sequence[str] | None = None,
        excluded_params: Sequence[str] | None = None,
        extra_option_at_end: bool = True,
        option_priorities: Mapping[str, float] | None = None,
        populate_auto_envvars: bool = True,
        extra_keywords: HelpKeywords | None = None,
        excluded_keywords: HelpKeywords | None = None,
        examples: Sequence[Sequence[str]] = (),
        **kwargs: Any,
    ) -> None:
        """List of extra parameters:

        :param version_fields: dictionary of
            `VersionOption` template field overrides forwarded to the
            version option. Accepts any field from
            `VersionOption.template_fields` (like `prog_name`,
            `version`, `git_branch`). Lets you customize `--version`
            output from the command decorator without replacing the default
            `params` list.
        :param config_strict: forwarded to the default
            {class}`~click_extra.config.option.ConfigOption`'s `strict`
            setting: configuration keys not matching any CLI parameter raise
            an error instead of being silently ignored. Like the other
            `config_*` and `*_params` forwards, it spares you from
            replacing the whole default `params` list to customize the
            config option.
        :param excluded_params: additional parameter IDs to block from
            configuration files, merged into the default
            {class}`~click_extra.config.option.ConfigOption`'s
            `excluded_params` blocklist. Additive, unlike the option-level
            `excluded_params` which replaces the default blocklist
            entirely. Items are fully-qualified parameter IDs (like
            `mycli.mail_sources`). Mutually exclusive with
            `included_params`.
        :param extra_keywords: a `HelpKeywords` instance whose entries are
            merged into the auto-collected keyword set. Use this to inject
            additional strings for help screen highlighting.
        :param excluded_keywords: a `HelpKeywords` instance whose entries are
            removed from the auto-collected keyword set. Use this to suppress
            highlighting of specific strings.
        :param examples: a sequence of `(description, command)` string pairs
            showing the command in use. They are rendered in an `Examples:`
            section of the help screen, in the man page, and in every
            [`--help-format`](https://kdeldycke.github.io/click-extra/machine-readable.html#the-help-format-option)
            rendering. A malformed pair raises `TypeError` here, at command
            construction, rather than on the first `--help` a user runs.
        :param extra_option_at_end: [reorders all parameters attached to the command](https://kdeldycke.github.io/click-extra/commands.html#option-order), by
            moving all instances of `ExtraOption` at the end of the parameter list.
            The original order of the options is preserved among themselves.
        :param option_priorities: maps an option to its priority in the help
            screen, relative to
            {data}`~click_extra.commands.DEFAULT_PRIORITY`, lowest
            shown first. Keys are matched against each parameter's long and short
            flags first, then its destination name, so the `--config` /
            `--no-config` pair (which shares the `config` destination) stays
            addressable one flag at a time. Presentation only: `self.params`, and
            with it the order callbacks are evaluated in, is left alone. Positional
            arguments are never reordered, their sequence being part of the
            command's grammar.
        :param populate_auto_envvars: forces all parameters to have their auto-generated
            environment variables registered. This address the shortcoming of `click`
            which only evaluates them dynamically. By forcing their registration, the
            auto-generated environment variables gets displayed in the help screen,
            fixing [click#2483 issue](https://github.com/pallets/click/issues/2483).
            On Windows, environment variable names are case-insensitive, so we normalize
            them to uppercase.

        By default, these [Click context settings](https://click.palletsprojects.com/en/stable/api/#click.Context) are applied:

        - `auto_envvar_prefix = self.name` (*Click feature*)

          Auto-generate environment variables for all options, using the command ID as
          prefix. The prefix is normalized to be uppercased and all non-alphanumerics
          replaced by underscores.

        - `help_option_names = ("--help", "-h")` (*Click feature*)

          [Allow help screen to be invoked with either --help or -h options](https://click.palletsprojects.com/en/stable/documentation/#help-parameter-customization).

        - `show_default = True` (*Click feature*)

          [Show all default values](https://click.palletsprojects.com/en/stable/api/#click.Context.show_default)
          in help screen.

        Additionally, these [Cloup context settings](https://cloup.readthedocs.io/en/stable/pages/formatting.html#formatting-settings)
        are set:

        - `align_option_groups = True` (*Cloup feature*)

          [Aligns option groups in help screen](https://cloup.readthedocs.io/en/stable/pages/option-groups.html#aligned-vs-non-aligned-groups).

          Every command carries the sections of
          {data}`~click_extra.commands.DEFAULT_OPTION_GROUPS`, so
          leaving each to compute its own column width would step the help text
          left and right from one section to the next. Aligned, a command's own
          options keep the column click-extra's widest option sets, which is what
          the `default_options_*_help` fixtures of {mod}`click_extra.pytest`
          match against.

        - `show_constraints = True` (*Cloup feature*)

          [Show all constraints in help screen](https://cloup.readthedocs.io/en/stable/pages/constraints.html#the-constraint-decorator).

        - `show_subcommand_aliases = True` (*Cloup feature*)

          [Show all subcommand aliases in help screen](https://cloup.readthedocs.io/en/stable/pages/aliases.html?highlight=show_subcommand_aliases#help-output-of-the-group).

        Click Extra also adds its own `context_settings`:

        - `show_choices = None` (*Click Extra feature*)

          If set to `True` or `False`, will force that value on all options, so we
          can globally show or hide choices when prompting a user for input. Only makes
          sense for options whose `prompt` property is set.

          Defaults to `None`, which will leave all options untouched, and let them
          decide of their own `show_choices` setting.

        - `show_envvar = None` (*Click Extra feature*)

          If set to `True` or `False`, will force that value on all options, so we
          can globally enable or disable the display of environment variables in help
          screen.

          Defaults to `None`, which will leave all options untouched, and let them
          decide of their own `show_envvar` setting. The rationale being that
          discoverability of environment variables is enabled by the `--params`
          option, which is active by default on extra commands. So there is no need to
          surcharge the help screen.

          This addresses the
          [click#2313 issue](https://github.com/pallets/click/issues/2313).

        To override these defaults, you can pass your own settings with the
        `context_settings` parameter:

        ```{code-block} python

        @command(
            context_settings={
                "show_default": False,
                ...
            }
        )
        ```
        """
        super().__init__(*args, **kwargs)

        # Forward keyword overrides to the _HelpColorsMixin attributes.
        if extra_keywords is not None:
            self.extra_keywords = extra_keywords
        if excluded_keywords is not None:
            self.excluded_keywords = excluded_keywords

        self.examples = normalize_examples(examples)

        self.option_priorities: dict[str, float] = dict(option_priorities or {})

        default_ctx_settings: dict[str, Any] = {
            # Click settings:
            "help_option_names": DEFAULT_HELP_NAMES,
            "show_default": True,
            # Cloup settings:
            "align_option_groups": True,
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
        for setting in EXTRA_OPTION_SETTINGS:
            if default_ctx_settings[setting] is not None:
                for param in self.params:
                    # These attributes are specific to options.
                    if isinstance(param, click.Option):
                        setattr(param, setting, default_ctx_settings[setting])

        # Remove Click Extra-specific settings, before passing it to Cloup and Click.
        for setting in EXTRA_OPTION_SETTINGS:
            del default_ctx_settings[setting]
        self.context_settings: dict[str, Any] = default_ctx_settings

        # Forward version template fields to the version option.
        if version_fields:
            for param in self.params:
                if isinstance(param, VersionOption):
                    for field_id, field_value in version_fields.items():
                        if field_id not in param.template_fields:
                            msg = (
                                f"Unknown version field {field_id!r}."
                                f" Must be one of {param.template_fields}."
                            )
                            raise TypeError(msg)
                        setattr(param, field_id, field_value)

        # Forward config option parameters to the ConfigOption instance.
        if included_params is not None and excluded_params is not None:
            msg = "excluded_params and included_params are mutually exclusive."
            raise ValueError(msg)
        if (
            config_schema is not None
            or config_strict
            or schema_strict
            or fallback_sections
            or config_validators
            or included_params is not None
            or excluded_params is not None
        ):
            for param in self.params:
                if isinstance(param, ConfigOption):
                    if included_params is not None:
                        param.included_params = frozenset(included_params)
                        # Schema-only section: see the same inference in
                        # ConfigOption.__init__.
                        param.schema_warn_unknown = not param.included_params
                    if excluded_params is not None:
                        if param.included_params is not None:
                            msg = (
                                "excluded_params conflicts with the config "
                                "option's own included_params."
                            )
                            raise ValueError(msg)
                        if "excluded_params" in param.__dict__:
                            # The option carries an explicit blocklist: extend
                            # the frozen instance value directly.
                            param.excluded_params = param.excluded_params | (
                                frozenset(excluded_params)
                            )
                        else:
                            # Stash the additions for the dynamic default
                            # property to merge at resolution time, when the
                            # runtime context is available.
                            param.extra_excluded_params = frozenset(excluded_params)
                    if config_strict:
                        param.strict = config_strict
                    if schema_strict:
                        param.schema_strict = schema_strict
                    if config_schema is not None:
                        param.config_schema = config_schema
                        param._config_schema_callable = make_schema_callable(
                            config_schema,
                            strict=param.schema_strict,
                            warn_unknown=param.schema_warn_unknown,
                        )
                    if fallback_sections:
                        param.fallback_sections = tuple(fallback_sections)
                    if config_validators:
                        param.config_validators = tuple(config_validators)
                    # Recompute the opaque-path union whenever the schema or
                    # validators have been forwarded so the strict-check skip
                    # set stays in sync with the new sources.
                    if config_schema is not None or config_validators:
                        param._opaque_paths = _opaque_paths(
                            param.config_schema, param.config_validators
                        )

        if populate_auto_envvars:
            for param in self.params:
                param.envvar = param_envvar_ids(param, self.context_settings)

        if extra_option_at_end:
            self.params.sort(key=lambda p: isinstance(p, ExtraOption))

        # Forces re-identification of grouped and non-grouped options as we re-ordered
        # them above and added our own extra options since initialization. Feeds a
        # presentation-ordered copy rather than `self.params` itself: the two are
        # different concerns, and only the copy may be reshuffled. See
        # `param_priority`.
        _grouped_params = self._group_params(
            sorted(self.params, key=self.param_priority)
        )
        self.arguments, self.option_groups, self.ungrouped_options = _grouped_params

    def param_priority(self, param: click.Parameter) -> float:
        """Priority of *param* in the help screen.

        Defaults to {data}`~click_extra.commands.DEFAULT_PRIORITY`, and is otherwise
        resolved against `option_priorities` by trying each of the parameter's flags
        in turn, then its destination name.

        ```{important}
        This orders the help screen alone. The order of `self.params` decides when
        each callback fires: `click.core.iter_params_for_processing` sorts on
        `(not is_eager, position on the command line)`, and every eager option the
        user did not type ties on that second key, leaving declaration order as the
        tie-break. That is what puts `--time` ahead of everything it measures and
        `--accessible` ahead of the `--color` default it lowers, so the two orders
        have to be free to disagree.
        ```

        Positional arguments always resolve to the default: their sequence is part
        of the command's grammar, not a matter of presentation.
        """
        if self.option_priorities and not isinstance(param, click.Argument):
            for key in (*param.opts, *param.secondary_opts, param.name):
                if key is not None and key in self.option_priorities:
                    return self.option_priorities[key]
        return DEFAULT_PRIORITY

    def split_option_groups(
        self,
    ) -> tuple[tuple[cloup.OptionGroup, ...], tuple[cloup.OptionGroup, ...]]:
        """Explicit option groups, split around the ungrouped section.

        Hands back the groups drawn *before* the ungrouped options, then those
        drawn *after*. Cloup draws the ungrouped section last, with no setting to
        move it, which would bury a CLI's own options under the ones Click Extra
        injects. So the rule is kept for the groups a CLI author declares, and
        every {class}`ExtraOptionGroup` goes past the ungrouped section, ordered
        by its `priority`.

        ```{important}
        This is the one place the section order is decided. The help screen
        ({meth}`format_params`), the man page and every other
        {data}`~click_extra.command_doc.HELP_FORMATS` backend
        ({func}`~click_extra.command_doc._build_option_groups`), and the
        completion specs ({func}`~click_extra.parameters.iter_params_for_display`)
        all read it, so a CLI never lists its options in one order on `--help`
        and another on `--help-format man`.
        ```
        """
        own: list[cloup.OptionGroup] = []
        extra: list[ExtraOptionGroup] = []
        for group in self.option_groups:
            if isinstance(group, ExtraOptionGroup):
                extra.append(group)
            else:
                own.append(group)
        return tuple(own), tuple(sorted(extra, key=lambda group: group.priority))

    def get_argument_help_record(
        self,
        arg: click.Argument,
        ctx: click.Context,
    ) -> tuple[str, str]:
        """Pair a positional argument's metavar with its help text.

        Reimplements `cloup.OptionGroupMixin.get_argument_help_record`, which reads
        the text off a `cloup.Argument` and hands back an empty string for any other
        argument. Click 8.5.0 gave `click.Argument` a `help` parameter of its own, so
        a plain `click.argument(..., help=...)` earns a `Positional arguments` entry
        and renders blank under that rule.

        Resolution goes through {func}`~click_extra.parameters.resolve_param_help`,
        the same helper the man page and every other
        {data}`~click_extra.command_doc.HELP_FORMATS` backend reads, so an operand
        carries one description whatever renders it.
        """
        return arg.make_metavar(ctx=ctx), resolve_param_help(arg, ctx) or ""

    def format_params(self, ctx: click.Context, formatter: Any) -> None:
        """Draw the parameter sections of the help screen.

        Reimplements `cloup.OptionGroupMixin.format_params` to honor the order
        {meth}`split_option_groups` computes, and to title the ungrouped section
        against the groups the CLI author declared alone. Cloup picks that title
        by counting every visible group, click-extra's included, so a command
        carrying the default options would never show a plain `Options` heading
        again.
        """
        formatter = ensure_is_cloup_formatter(formatter)

        sections = []
        arguments_section = self.get_arguments_help_section(ctx)
        if arguments_section:
            sections.append(arguments_section)

        own_groups, extra_groups = self.split_option_groups()
        default_group = self.get_default_option_group(
            ctx,
            is_the_only_visible_option_group=not any(
                not group.hidden for group in own_groups
            ),
        )
        sections.extend(
            self.make_option_group_help_section(group, ctx)
            for group in (*own_groups, default_group, *extra_groups)
            if not group.hidden
        )

        formatter.write_many_sections(
            sections,
            aligned=self.must_align_option_groups(ctx),
        )

    def main(  # type: ignore[override]
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Pre-invocation step that is instantiating the context, then call `invoke()`
        within it.

        ```{caution}
        During context instantiation, each option's callbacks are called. These
        might break the execution flow (like `--help` or `--version`).
        ```

        Sets the default CLI's `prog_name` to the command's name if not provided,
        instead of relying on Click's auto-detection via the
        `_detect_program_name()` method. This is to avoid the CLI being called
        `python -m <module_name>`, which is not very user-friendly.
        """
        if not prog_name and self.name:
            prog_name = self.name

        try:
            return super().main(args=args, prog_name=prog_name, **kwargs)
        finally:
            # The color mirror is scoped to one invocation. Its reset is queued
            # on the context by `publish_invocation_color()`, but a callback
            # raising during parameter processing aborts before the context is
            # entered, so that close callback never fires and the mirror stays
            # pinned for the rest of the process. Reset here so the scope holds
            # however the invocation ended.
            _reset_invocation_color()

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: Any,
    ) -> Any:
        """Intercept the call to the original `click.core.Command.make_context` so
        we can keep a copy of the raw, pre-parsed arguments provided to the CLI.

        The result are passed to our own `Context` constructor which is able to
        initialize the context's `meta` property under our own
        {data}`click_extra.context.RAW_ARGS` entry. This will be used in
        `ShowParamsOption.print_params()` to print the table of parameters fed to the
        CLI.

        ```{seealso}
        See {data}`click_extra.context.RAW_ARGS` for the full rationale and
        the upstream-proposal notes (related: [click#1279](https://github.com/pallets/click/issues/1279#issuecomment-1493348208)).
        ```
        """
        # `args` needs to be copied: its items are consumed by the parsing process.
        meta: dict[str, Any] = {context.RAW_ARGS: args.copy()}
        # Record the invocation name once, on the root context: `ctx.meta` is
        # shared down the whole context hierarchy, and a subcommand's own
        # `info_name` is not the name the binary was invoked under.
        if parent is None:
            meta[context.INVOCATION_NAME] = info_name
        extra.update({"meta": meta})
        return super().make_context(info_name, args, parent, **extra)

    def format_examples(
        self,
        ctx: click.Context,
        formatter: click.HelpFormatter,
    ) -> None:
        """Write an `Examples:` section listing the command's {attr}`examples`.

        Each entry renders its description, then the command line it describes,
        indented behind a `$` prompt. A command declaring none writes nothing at
        all, so a help screen only grows the section when it has something to
        put in it.

        The command lines go out verbatim rather than through
        `formatter.write_text()`: an example exists to be copied, and Click's
        text wrapper would fold a long one onto a second line mid-token. This is
        the same call the `\\b` no-rewrap marker makes for help prose.

        Nothing here styles anything. The lines land in the formatter's buffer,
        which {meth}`~click_extra.highlight.HelpFormatter.getvalue` runs through
        keyword highlighting on its way out, so the option names, subcommands and
        CLI names inside an example are painted by the same pass that paints them
        everywhere else.
        """
        if not self.examples:
            return
        with formatter.section(_("Examples")):
            for index, (description, command_line) in enumerate(self.examples):
                if index:
                    formatter.write_paragraph()
                formatter.write_text(f"{description}:")
                formatter.indent()
                formatter.write(f"{' ' * formatter.current_indent}$ {command_line}\n")
                formatter.dedent()

    def format_epilog(
        self,
        ctx: click.Context,
        formatter: click.HelpFormatter,
    ) -> None:
        """Insert the examples section ahead of the epilog.

        Places it after the options and subcommands, which is where a reader
        arrives once they know what the command accepts, and keeps the author's
        own epilog as the last word on the screen.
        """
        self.format_examples(ctx, formatter)
        super().format_epilog(ctx, formatter)

    def _resolve_presentation_eagerly(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> None:
        """Settle the presentation options before any eager one renders.

        Click sorts eager options by their command-line position and puts the ones
        *not* typed last, so any option that renders and exits — `--help`,
        `--version`, `--man`, `--show-params` — is processed before every eager
        option the user did not also type. `--color`, `--no-color`, `--accessible`
        and `--theme` would therefore pin their state too late: the screen has
        already rendered. This pre-pass resolves them ahead of the regular parameter
        loop, so the choice reaches those screens whatever its position.

        {class}`~click_extra.accessibility.AccessibleOption` is resolved first,
        because it works by *lowering the `--color` default* through the context's
        `default_map`, which the color options then read. Reversing the two would
        leave the lowered default unread. Its global `ACCESSIBLE` environment
        variable triggers the pre-pass as well: the flag is absent from the command
        line in that case, which is exactly the sorting hole described above.

        {class}`~click_extra.theme.ThemeOption` is resolved last, and for the same
        reason it is resolved at all: a palette whose only observable effect is the
        look of a rendered screen is worthless if it lands after the screen. Its
        environment variables trigger the pre-pass too, both the machine-wide
        {data}`~click_extra.theme.THEME_ENVVAR` and the per-CLI `<CLI>_THEME` that
        Click derives, since neither puts a flag on the command line.

        Skipping accessible mode here used to be deliberate, on the grounds that it
        matched the scope of the environment pre-seed in
        {meth}`click_extra.context.Context.__init__` (which settles `FORCE_COLOR` /
        `NO_COLOR` at context-construction time). That reasoning does not survive
        contact with the contract {class}`~click_extra.accessibility.AccessibleOption`
        advertises — "equivalent to passing `--no-color`" — nor with who is harmed
        when it goes unhonored: `--accessible --version` emitted a screen full of
        ANSI to the one audience that asked for none. Configuration files stay out,
        having no such promise to keep.

        ```{note}
        Every group is resolved a second time by `super().parse_args()`. Their
        callbacks are idempotent (no env-var side effects, no prompt, and a
        `setdefault` on the `default_map`), so re-running them lands the exact same
        state, and {meth}`click_extra.parameters.ExtraOption.handle_parse_result`
        skips its source pre-record once the slot already carries one.

        That second pass is also what keeps a configuration file authoritative
        over the environment for `--theme`: this pre-pass runs before
        {class}`~click_extra.config.option.ConfigOption` has populated the
        `default_map`, so it can only ever see the command line and the
        environment. The screens rendered here are painted by whichever of those
        two won; a palette read from a configuration file lands on the second
        pass, in time for everything the command itself prints.
        ```
        """
        accessible_params: list[click.Parameter] = []
        color_params: list[click.Parameter] = []
        theme_params: list[click.Parameter] = []
        for param in self.get_params(ctx):
            if isinstance(param, AccessibleOption):
                accessible_params.append(param)
            elif isinstance(param, (ColorOption, NoColorOption)):
                color_params.append(param)
            elif isinstance(param, ThemeOption):
                theme_params.append(param)
        if not accessible_params and not color_params and not theme_params:
            return

        # Only pay for a re-parse when one of these flags actually sits on the
        # command line, or when the environment asks for accessible mode or a
        # palette.
        flags = {
            flag
            for param in (*accessible_params, *color_params, *theme_params)
            for flag in (*param.opts, *param.secondary_opts)
        }
        on_cli = any(arg.split("=", 1)[0] in flags for arg in args)
        envvars = set()
        if accessible_params:
            envvars.add(ACCESSIBLE_ENVVAR)
        for theme_param in theme_params:
            envvars.add(THEME_ENVVAR)
            envvars.update(param_envvar_ids(theme_param, ctx))
        if not on_cli and not any(var in os.environ for var in envvars):
            return

        parser = self.make_parser(ctx)
        try:
            opts, _, param_order = parser.parse_args(args=args.copy())
            # Accessible first: it lowers the color default the color options read.
            # Within each group, respect the relative command-line order so the last
            # of --color / --no-color wins, matching the regular loop's arbitration.
            for group in (accessible_params, color_params, theme_params):
                for param in iter_params_for_processing(param_order, group):
                    param.handle_parse_result(ctx, opts, args.copy())
        except click.ClickException:
            # Defer every parsing and validation error (and its enhanced message) to
            # the regular parse below, which renders an eager --help/--version first
            # when present. This pre-pass must never surface an error on its own.
            return

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Like parent's `parse_args` but with better error messages for
        single-dash multi-character tokens.

        Also settles the presentation options before delegating, so `--color`,
        `--no-color`, `--accessible` and `--theme` reach the eager help and version
        screens regardless of their position on the command line. See
        `_resolve_presentation_eagerly`.
        """
        original_args = args.copy()
        self._resolve_presentation_eagerly(ctx, args)
        try:
            return super().parse_args(ctx, args)
        except click.NoSuchOption as exc:
            _enhance_short_option_error(exc, original_args, ctx)


def _enhance_short_option_error(
    exc: click.NoSuchOption,
    original_args: list[str],
    ctx: click.Context,
) -> NoReturn:
    """Re-raise *exc* with the full token and close-match suggestions when
    appropriate, or re-raise it unchanged.

    Click's parser treats `-dbgwrong` as stacked short flags ``-d -b -g -w
    -r -o -n -g``, then reports "No such option: -d" on the first unregistered
    character. That is technically correct (short-option combining is POSIX
    behavior) but confusing when the user meant it as a single option name.

    This function detects that situation by checking whether the failed character
    is the *first* character of a multi-char single-dash token from the original
    argument list. If so, it collects every registered option name and uses
    `difflib.get_close_matches` to suggest alternatives, then raises a new
    `NoSuchOption` with the full token.

    When the failed character is *not* the leading character (the user was
    genuinely combining short flags and one of them doesn't exist), the original
    exception is re-raised as-is: Click's per-character diagnostic is already
    the right message.

    ```{seealso}
    - Upstream issue: https://github.com/pallets/click/issues/2779
    - `_match_short_opt` in Click's `parser.py` raises `NoSuchOption`
      with only the single failed character.
    - `_match_long_opt` already provides `get_close_matches` suggestions,
      but its exception is discarded when `_process_opts` falls through to
      the short-option path.
    - Upstream docs PR: https://github.com/pallets/click/pull/3179
    - Rejected upstream code PRs (all tried to patch `parser.py` instead of
      adding the requested docs):
      https://github.com/pallets/click/pull/3207 ,
      https://github.com/pallets/click/pull/3236 ,
      https://github.com/pallets/click/pull/3339
    ```
    """
    option_name = exc.option_name

    # Only enhance single-char short-option errors (like "-d").
    # Long-option errors ("--foo") already carry the full name and suggestions
    # from Click's _match_long_opt.
    if not (len(option_name) == 2 and option_name[0] == "-" and option_name[1] != "-"):
        raise exc

    failed_char = option_name[1]

    # Find the original multi-char token whose *first* character (after the
    # dash) is the one that failed. That means the whole token was never
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


class ColorizedCommand(_HelpColorsMixin, click.Command):  # type: ignore[misc]
    """Click Command with help colorization but no extra params.

    Mixes in `_HelpColorsMixin` for keyword
    highlighting and uses {class}`~click_extra.context.Context` for the colorized
    formatter, without inheriting from `Command` (which would inject
    `default_params`).

    Use this as a base for lightweight subcommands (like `help`) or for
    monkey-patching third-party CLIs (via {func}`~click_extra.cli_wrapper.patch_click`).
    """

    context_class: type[cloup.Context] = Context


class ColorizedGroup(_HelpColorsMixin, click.Group):  # type: ignore[misc]
    """Click Group with help colorization but no extra params.

    Same as {class}`ColorizedCommand` but for groups.
    """

    context_class: type[cloup.Context] = Context


class HelpCommand(ColorizedCommand):
    """Synthetic subcommand that displays help for the parent group or a subcommand.

    Auto-injected into every `Group`. Supports nested resolution:
    `mycli help subgroup subcmd` shows the help for `subcmd` within
    `subgroup`.
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
                raise click.NoSuchCommand(
                    name,
                    possibilities=get_close_matches(name, target_cmd.commands),
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
    """Create the synthetic `help` subcommand for an `Group`."""
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


def _descend_to_group_config(ctx: click.Context) -> dict[str, Any] | None:
    """Return the loaded config section for the current group's command path.

    Reads the full configuration document from `ctx.meta`, descends into the
    root command's section, then walks from the root context down to `ctx`
    following each group name. Returns the resolved mapping, or `None` when no
    configuration was loaded or any segment along the path is missing.
    """
    full_config = context.get(ctx, context.CONF_FULL)
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

    return config_branch


def _dedupe_subcommands(raw: list[str], key: str) -> list[str]:
    """Drop duplicate subcommand names, keeping the first occurrence.

    Warns when duplicates are dropped, naming the configuration `key` they
    came from.
    """
    seen: set[str] = set()
    deduped: list[str] = []
    for name in raw:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    if len(deduped) < len(raw):
        logger.warning(
            f"Duplicate entries in {key}: {raw!r}. "
            f"Keeping first occurrences: {deduped!r}."
        )
    return deduped


class Group(Command, cloup.Group):  # type: ignore[misc]
    """Like `cloup.Group`, with sane defaults and extra help screen colorization."""

    command_class = Command
    """Makes commands of a `Group` be instances of `Command`.

    That way all subcommands created from a `Group` benefits from the same
    defaults and extra help screen colorization.

    See: https://click.palletsprojects.com/en/stable/api/#click.Group.command_class
    """

    group_class = type
    """Let `Group` produce sub-groups that are also of `Group` type.

    See: https://click.palletsprojects.com/en/stable/api/#click.Group.group_class
    """

    def __init__(
        self,
        *args: Any,
        help_command: bool = True,
        sort_subcommands: bool | None = None,
        subcommand_priorities: Mapping[str, float] | None = None,
        **kwargs: Any,
    ) -> None:
        """Like `Command.__init__`, but auto-injects a `help` subcommand.

        :param help_command: when `True` (the default), a `help` subcommand is
            automatically registered. Set to `False` to suppress it, or register
            your own `help` subcommand to override it.
        :param sort_subcommands: how subcommands sharing a priority are broken
            apart. `True` lists them alphabetically, `False` in the order they
            were registered. `None` (the default) defers to the
            `sort_subcommands` context setting, then to `True`. See
            {meth}`~click_extra.commands.Group.must_sort_subcommands`.
        :param subcommand_priorities: maps a subcommand name to its priority
            relative to {data}`~click_extra.commands.DEFAULT_PRIORITY`, lowest
            listed first. Names left out keep the default priority, so numbering
            a few subcommands moves only those.
        """
        super().__init__(*args, **kwargs)
        self.sort_subcommands = sort_subcommands
        self.subcommand_priorities: dict[str, float] = dict(subcommand_priorities or {})
        if help_command and "help" not in self.commands:
            self.add_command(_make_help_command())

    def must_sort_subcommands(self, ctx: click.Context | None) -> bool:
        """Resolve whether subcommand listings are alphabetical.

        Reads the group's own `sort_subcommands`, then the context setting of the
        same name, then falls back to `True`. This is the resolution order Cloup
        uses for `align_sections`, and it is what lets a single
        `context_settings={"sort_subcommands": False}` on the root group reach every
        subgroup below it instead of being repeated on each.
        """
        if self.sort_subcommands is not None:
            return self.sort_subcommands
        from_context = getattr(ctx, "sort_subcommands", None)
        if from_context is not None:
            return bool(from_context)
        return True

    def subcommand_priority(self, name: str) -> float:
        """Priority of the *name* subcommand.

        Defaults to {data}`~click_extra.commands.DEFAULT_PRIORITY`.
        """
        return self.subcommand_priorities.get(name, DEFAULT_PRIORITY)

    def _registered_subcommands(self, ctx: click.Context) -> list[str]:
        """Subcommand names in registration order, before any ordering is applied.

        The extension point {class}`LazyGroup` overrides to fold in the subcommands
        it has not imported yet.
        """
        return list(self.commands)

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Subcommand names in presentation order.

        Sorted on `subcommand_priorities` first, then broken apart by
        {meth}`~click_extra.commands.Group.must_sort_subcommands`: alphabetically,
        or by registration order. With no priority declared every subcommand ties,
        leaving the tie-break as the only ordering, which is Click's plain
        alphabetical listing.

        In registration order the auto-injected `help` subcommand is listed last,
        wherever it happens to have been registered: `Group.__init__` appends it
        before any `@cli.command()` decorator runs, while a `commands=[…]`
        constructor argument lands it after, so its natural position says nothing
        about the author's intent. Mirrors what `extra_option_at_end` does to
        options.
        """
        names = self._registered_subcommands(ctx)
        if self.must_sort_subcommands(ctx):
            names = sorted(names)
        else:
            names = sorted(
                names,
                key=lambda name: isinstance(self.commands.get(name), HelpCommand),
            )
        # Stable, so subcommands sharing a priority keep the order settled above.
        return sorted(names, key=self.subcommand_priority)

    def list_sections(
        self,
        ctx: click.Context,
        include_default_section: bool = True,
    ) -> list[cloup.Section]:
        """Like `cloup.Group.list_sections`, but ordering the default section.

        Cloup hard-codes the default section to `Section.sorted(…)`, which is why
        overriding {meth}`list_commands` alone leaves the help screen alphabetical:
        the screen is rendered from sections and never calls it. Rebuild that
        section from {meth}`list_commands` instead, and hand it over already
        ordered.

        ```{note}
        Sections the author declared themselves are returned untouched. Cloup's own
        `Section(is_sorted=…)` already governs those, and a user holding a `Section`
        instance should not have it rewritten underneath them. Priorities and
        `sort_subcommands` therefore address the default section and the flat
        listings (`--tree`, man pages, completion specs), not the contents of an
        explicit section.
        ```
        """
        section_list = list(self._user_sections)
        if include_default_section and len(self._default_section) > 0:
            default_commands = self._default_section.commands
            section_list.append(
                cloup.Section(
                    title="Other commands" if self._user_sections else "Commands",
                    commands={
                        name: default_commands[name]
                        for name in self.list_commands(ctx)
                        if name in default_commands
                    },
                )
            )
        return section_list

    def add_command(  # type: ignore[override]
        self,
        cmd: click.Command,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Like `cloup.Group.add_command`, but replaces an auto-injected
        `HelpCommand` when the user registers their own `help` subcommand.
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
        """Inject `_default_subcommands` and `_prepend_subcommands` from config.

        If the user has not provided any subcommands explicitly, and the loaded
        configuration contains a `_default_subcommands` list for this group, those
        subcommands are injected into `ctx.protected_args` so that Click's normal
        `Group.invoke()` dispatches them.

        `_prepend_subcommands` always prepends subcommands to the invocation,
        regardless of whether CLI subcommands were provided. Only works with
        `chain=True` groups.
        """
        if not ctx._protected_args and not ctx.args:
            default_subcmds = self._get_default_subcommands(ctx)
            if default_subcmds is not None:
                ctx._protected_args = list(default_subcmds)
        elif ctx._protected_args or ctx.args:
            # CLI subcommands were given explicitly; log if config defaults exist.
            default_subcmds = self._get_default_subcommands(ctx)
            if default_subcmds is not None:
                logger.debug(
                    f"CLI subcommands provided; ignoring {DEFAULT_SUBCOMMANDS_KEY}"
                    f" config: {default_subcmds!r}."
                )

        # Always prepend _prepend_subcommands, regardless of CLI args.
        prepend_subcmds = self._get_prepend_subcommands(ctx)
        if prepend_subcmds is not None:
            logger.info(
                f"Prepending {PREPEND_SUBCOMMANDS_KEY} config: {prepend_subcmds!r}."
            )
            ctx._protected_args = list(prepend_subcmds) + ctx._protected_args

        return super().invoke(ctx)

    def _read_subcommand_list(self, ctx: click.Context, key: str) -> list[str] | None:
        """Read, validate, dedupe, and existence-check a subcommand-list config key.

        Returns the deduplicated list of subcommand names declared under `key`
        in the loaded configuration, or `None` when the key is absent or empty.
        Shared by {meth}`_get_default_subcommands` and
        {meth}`_get_prepend_subcommands`; each caller layers on its own chain-mode
        rule (the only behavior that differs between the two keys).

        :raises click.UsageError: when the value is not a list of strings, or when
            a listed subcommand does not exist in this group.
        """
        config_branch = _descend_to_group_config(ctx)
        if config_branch is None:
            return None

        raw = config_branch.get(key)
        if raw is None:
            return None

        # Validate type.
        if not isinstance(raw, list) or not all(isinstance(s, str) for s in raw):
            raise click.UsageError(f"{key} must be a list of strings, got {raw!r}.")

        if not raw:
            return None

        raw = _dedupe_subcommands(raw, key)

        # Validate that all subcommands exist.
        for name in raw:
            if self.get_command(ctx, name) is None:
                raise click.UsageError(
                    f"Subcommand {name!r} from {key} not found in group {self.name!r}."
                )

        return raw

    def _get_default_subcommands(self, ctx: click.Context) -> list[str] | None:
        """Read and validate `_default_subcommands` from the loaded configuration."""
        raw = self._read_subcommand_list(ctx, DEFAULT_SUBCOMMANDS_KEY)
        if raw is None:
            return None

        # Non-chained groups can only have one default subcommand.
        if not self.chain and len(raw) > 1:
            raise click.UsageError(
                f"Non-chained group {self.name!r} can have at most 1 default "
                f"subcommand, got {len(raw)}: {raw!r}."
            )

        return raw

    def _get_prepend_subcommands(self, ctx: click.Context) -> list[str] | None:
        """Read and validate `_prepend_subcommands` from the loaded configuration."""
        raw = self._read_subcommand_list(ctx, PREPEND_SUBCOMMANDS_KEY)
        if raw is None:
            return None

        # Prepend subcommands only work with chained groups.
        if not self.chain:
            raise click.UsageError(
                f"{PREPEND_SUBCOMMANDS_KEY} requires chain=True on group {self.name!r}."
            )

        return raw


@dataclass(frozen=True)
class LazySubcommand:
    """Declaration of a lazily-imported subcommand of a {class}`LazyGroup`.

    Carries the registration settings {meth}`cloup.Group.add_command` accepts, which
    a bare import path cannot express. A subcommand needing none of them is declared
    as a plain string instead.
    """

    import_path: str
    """Where to import the command object from, as `"<module-name>.<command-name>"`."""

    section: cloup.Section | None = None
    """Help-screen section the subcommand is filed under, once imported.

    A section declared here is registered on the group right away, so the help screen
    orders its sections as they are declared, not as their subcommands happen to be
    imported. The same `Section` instance can be shared with eagerly-registered
    subcommands.
    """

    fallback_to_default_section: bool = True
    """Whether to file the subcommand under the default section when {attr}`section`
    is `None`.

    Set to `False` to leave the subcommand out of every section, which hides it from
    the help screen while keeping it invocable. Cloup calls this an escape hatch for
    internal code: do not disable it unless you know what you are doing.
    """


class LazyGroup(Group):
    """A `Group` that supports lazy loading of subcommands.

    ```{hint}
    This implementation is based on the snippet from Click's documentation:
    [Defining the lazy group](https://click.palletsprojects.com/en/stable/complex/#defining-the-lazy-group).

    It has been extended to work with Click Extra's `config_option` in
    [click_extra#1332 issue](https://github.com/kdeldycke/click-extra/issues/1332#issuecomment-3299486142).
    ```
    """

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: Mapping[str, str | LazySubcommand] | None = None,
        **kwargs: Any,
    ) -> None:
        """`lazy_subcommands` maps command names to their import paths.

        ```{tip}
        `lazy_subcommands` is a map of the form:

        .. code-block:: python

            {"<command-name>": "<module-name>.<command-object-name>"}

        For example:

        .. code-block:: python

            {"mycmd": "my_cli.commands.mycmd"}
        ```

        A subcommand needing registration settings on top of its import path is
        declared with a {class}`LazySubcommand` instead of a bare string:

        .. code-block:: python

            {"mycmd": LazySubcommand("my_cli.commands.mycmd", section=my_section)}

        Every section declared that way is registered on the group here, so the help
        screen orders its sections as the author declared them. Waiting for each
        subcommand to be imported would instead order them by import, which is
        alphabetical and says nothing about intent.
        """
        super().__init__(*args, **kwargs)
        self.lazy_subcommands: dict[str, LazySubcommand] = {
            name: LazySubcommand(spec) if isinstance(spec, str) else spec
            for name, spec in (lazy_subcommands or {}).items()
        }

        for spec in self.lazy_subcommands.values():
            # Sections passed to the constructor are already registered, and Cloup
            # refuses the same instance twice.
            if spec.section is not None and spec.section not in self._section_set:
                self.add_section(spec.section)

    def _registered_subcommands(self, ctx: click.Context) -> list[str]:
        """Like the parent, but folding in the not-yet-imported subcommands.

        A lazily-declared subcommand holds the same slot whether or not
        {meth}`get_command` has already imported it. Importing appends it to
        `self.commands`, so reading registration order off that dictionary alone
        would reshuffle the listing halfway through a run. Eagerly registered
        subcommands come first, in the order they were added, then the lazy ones in
        declaration order.

        The import order itself follows whatever {meth}`Group.list_commands`
        returns, which is alphabetical unless the author says otherwise.
        """
        eager = [name for name in self.commands if name not in self.lazy_subcommands]
        return eager + list(self.lazy_subcommands)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Get a command by name, loading lazily if necessary."""
        if cmd_name in self.lazy_subcommands and cmd_name not in self.commands:
            self._register_lazy(cmd_name)
            # Inject the lazy command's config section into the context's
            # default_map, since it was missed by ConfigOption.merge_default_map.
            self._apply_config_to_parent_context(ctx, cmd_name)

        return super().get_command(ctx, cmd_name)

    def _register_lazy(self, cmd_name: str) -> click.Command:
        """Import `cmd_name` and register it with the settings it was declared with.

        The single place a lazy subcommand enters the group, so a settings-carrying
        {class}`LazySubcommand` reaches Cloup whichever route triggered the import.
        """
        spec = self.lazy_subcommands[cmd_name]
        cmd_object = self._lazy_load(cmd_name)
        # Register with Click's API so help and Cloup sections work properly.
        self.add_command(
            cmd_object,
            section=spec.section,
            fallback_to_default_section=spec.fallback_to_default_section,
        )
        return cmd_object

    def _lazy_load(self, cmd_name: str) -> click.Command:
        """Import and return the command object for `cmd_name`."""
        import_path = self.lazy_subcommands[cmd_name].import_path

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
        """Inject a lazy command's config into `ctx.default_map`.

        Lazy commands are not yet registered when `ConfigOption.merge_default_map`
        builds `params_template`, so their config sections get filtered out. This
        method compensates by reading the full config from `ctx.meta` and placing
        the lazy command's section into `ctx.default_map[cmd_name]`.

        Click will then pass that dict as the `default_map` of the command's own
        context.
        """
        config_branch = _descend_to_group_config(ctx)
        if config_branch is None:
            return

        # Extract the lazy command's config section.
        cmd_config = config_branch.get(cmd_name)
        if not isinstance(cmd_config, dict):
            return

        if ctx.default_map is None:
            ctx.default_map = {}
        ctx.default_map.setdefault(cmd_name, {}).update(cmd_config)

        logger.debug(f"Lazy config for {cmd_name!r}: {cmd_config}")
