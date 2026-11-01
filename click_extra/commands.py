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

Click Extra's commands, groups and contexts subclass their vanilla counterparts,
pre-configured with common defaults. The mixins here build custom variants.
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from gettext import gettext as _

import click
import cloup
from click import echo
from click.core import iter_params_for_processing
from click.exceptions import Abort, Exit
from cloup.formatting import ensure_is_cloup_formatter

from . import context
from ._utils import exception_chain
from .accessibility import ACCESSIBLE_ENVVAR, AccessibleOption
from .color import ColorOption, NoColorOption, resolve_color_env
from .command_doc import HelpFormatOption, ManOption, normalize_examples
from .config import (
    ConfigOption,
    ConfigValidator,
    ExportConfigOption,
    NoConfigOption,
    ValidateConfigOption,
)
from .config.subcommands import _descend_to_group_config
from .context import TABLE_FORMAT, TABLE_SORT_KEY, _scoped_run, get
from .envvar import clean_envvar_id, param_envvar_ids
from .execution import (
    TimerOption,
    _exit_interrupted,
    _interrupt_handling,
    _interrupted,
    _run_end_watch,
)
from .highlight import HelpFormatter, HelpKeywords, _HelpColorsMixin, highlight
from .logging import DebugOption, QuietOption, VerboseOption, VerbosityOption
from .output import force_unicode_output
from .param_tools import (
    child_context,
    iter_subcommands,
    param_spellings,
    resolve_param_help,
)
from .parameters import ExtraOption
from .show_params import ShowParamsOption
from .spinner import ProgressOption
from .table import print_table, render_table
from .table_options import TableFormatOption
from .theme import THEME_ENVVAR, ThemeOption, get_current_theme
from .tree import TreeOption
from .version import VersionOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence
    from types import TracebackType
    from typing import Any, Final, NoReturn

    from .table import TableFormat, THeader
    from .version import VersionScreen

logger = logging.getLogger(__name__)

DEFAULT_HELP_NAMES: tuple[str, ...] = ("--help", "-h")
"""Flags of the help option: every command's `help_option_names`, and the flags of
{func}`~click_extra.decorators.help_option`."""

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


def _assign_option_groups(params: Sequence[click.Parameter]) -> None:
    """Sort *params* into a fresh set of
    {data}`~click_extra.commands.DEFAULT_OPTION_GROUPS`.

    An option the CLI author put in a group of their own is left where they put
    it. Any other is re-filed, including one already in a section from an earlier
    call: a section is one group instance, so filing a late arrival into a group
    of its own would draw its title twice.

    Called once as {func}`default_params` builds its own options, then again by
    {func}`~click_extra.decorators.decorator_factory` on whatever a `params` hook
    returns. That second pass is what gives a section back to an option the hook
    swapped for a subclass of it, since the replacement is built after the first
    call and would otherwise be drawn under `Other options`. It reads the hook's
    output alone, so an option the author declares through a decorator stays
    ungrouped, next to `--help`.

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
            # `cloup.Option.__init__` carries no annotation, so mypy skips its
            # body and never records the `group` attribute it binds.
            current = getattr(param, "group", None)
            if current is not None and not isinstance(current, ExtraOptionGroup):
                continue
            if wanted.intersection(param_spellings(param)):
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
    #. `--debug`
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
    The list above is the *processing* order, and it is the only one these
    edge-cases care about. The help screen reads a separate presentation order,
    which the `option_priorities` argument of `@command` and `@group` reshuffles
    without touching a single callback. See
    {meth}`~click_extra.commands.Command.param_priority` and
    [click_extra#544 issue](https://github.com/kdeldycke/click-extra/issues/544).

    Presentation also sorts these options into the sections
    {data}`~click_extra.commands.DEFAULT_OPTION_GROUPS` declares, drawn after the
    command's own options. The two orders are independent: `--time` is processed
    first and rendered last.
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


POSIXLY_CORRECT_ENVVAR: Final[str] = "POSIXLY_CORRECT"
"""Environment variable that requests strict POSIX argument parsing.

When this variable is present in the environment (regardless of its value,
matching GNU `getopt` semantics), {class}`Context` forces
`allow_interspersed_args` to `False` so option parsing stops at the first
positional argument.
"""


_ABORT_EXCEPTIONS: Final = (EOFError, KeyboardInterrupt, Abort)
"""The exceptions Click's `main()` answers with `Aborted!` and the exit status `1`."""


@dataclass
class _AbortNotice:
    """The `Aborted!` notice of one standalone run of a Click Extra command.

    Click prints that notice once the root context has closed, so after every
    close callback of the run. A run that owns its notice prints it as soon as
    the abort leaves a command, before any context closes: the user reads it at
    once, even when the clean-up is slow.
    """

    command: click.Command
    """The command whose `main()` drives the run."""

    printed_for: BaseException | None = None
    """The abort the notice is printed for, if any."""

    def covers(self, exc: BaseException | None) -> bool:
        """Whether the notice is printed for `exc`, or for the abort `exc` stems from.

        An abort keeps its notice on its way up the commands, and when a later
        exception replaces it, like a second Ctrl+C landing in a close callback.
        """
        return any(link is self.printed_for for link in exception_chain(exc))


_ABORT_NOTICE: ContextVar[_AbortNotice | None] = ContextVar(
    "_ABORT_NOTICE", default=None
)
"""The notice of the run in progress, or `None` where Click prints its own."""


@contextmanager
def _owning_abort_notice(
    command: click.Command, standalone: bool
) -> Generator[None, None, None]:
    """Make the run of `command` in the block print its own abort notice.

    Only a standalone run prints one. Without standalone mode, Click raises the
    {exc}`~click.exceptions.Abort` to the caller and prints no notice.
    """
    token = _ABORT_NOTICE.set(_AbortNotice(command) if standalone else None)
    try:
        yield
    finally:
        _ABORT_NOTICE.reset(token)


@contextmanager
def _abort_notice(ctx: click.Context) -> Generator[None, None, None]:
    """Print Click's `Aborted!` as soon as an abort leaves the block.

    Wraps the invocation of a command, which Click runs inside the context of
    that command. The notice so precedes the close callbacks of every context of
    the run, the innermost included.

    Code that runs a command through {meth}`click.Context.invoke` never enters
    this block, so it stays free to catch the abort and carry on.
    """
    try:
        yield
    except _ABORT_EXCEPTIONS as exc:
        notice = _ABORT_NOTICE.get()
        if (
            notice is not None
            and ctx.find_root().command is notice.command
            and not notice.covers(exc)
        ):
            notice.printed_for = exc
            if not isinstance(exc, Abort):
                # The blank line ends the line of the `^C` the terminal echoed.
                echo(file=sys.stderr)
            echo(_("Aborted!"), file=sys.stderr)
        raise


class Context(cloup.Context):
    """Like `cloup.Context`, but with the ability to populate the context's `meta`
    property at instantiation.

    Also pre-seeds `color` for root contexts (those without a parent) from the
    color environment variables, so the eager help and version screens honor
    `FORCE_COLOR`, `NO_COLOR` and their siblings (see
    {func}`~click_extra.color.resolve_color_env`). With none of them set, `color`
    stays at Click's `None` default, which auto-detects a TTY. Child contexts
    inherit the color of their parent, as Click does.

    When the `POSIXLY_CORRECT` environment variable is set, this context forces
    `allow_interspersed_args` to `False` so option parsing stops at the first
    positional argument, as GNU getopt-based tools do. See
    {data}`~click_extra.commands.POSIXLY_CORRECT_ENVVAR`.

    Carries the `sort_subcommands` setting read by
    {meth}`click_extra.commands.Group.must_sort_subcommands`, so a whole command
    tree can settle its subcommand listings in one place.

    ```{todo}
    Propose addition of `meta` keyword upstream to Click.
    ```
    """

    formatter_class = HelpFormatter
    """Use Click Extra's formatter to colorize the help screen."""

    def __init__(
        self,
        *args: Any,
        meta: dict[str, Any] | None = None,
        sort_subcommands: bool | None = None,
        **kwargs: Any,
    ) -> None:
        """Like parent's context but with an extra `meta` keyword-argument.

        Also pre-seed `color` from the color environment variables for a parentless
        context when the user did not provide it, and force
        `allow_interspersed_args` to `False` when `POSIXLY_CORRECT` is set in the
        environment.

        :param sort_subcommands: whether groups list their subcommands
            alphabetically. Inherited from the parent context when left to `None`,
            the way Cloup inherits `align_sections`, so declaring it once on the
            root group settles every subgroup below it.
        """
        super().__init__(*args, **kwargs)

        # Inherit from the parent context, so a setting declared on the root group
        # reaches subgroups that never mention it. Cloup does the same for its own
        # `align_sections` and `show_subcommand_aliases` settings.
        self.sort_subcommands = (
            sort_subcommands
            if sort_subcommands is not None
            else getattr(self.parent, "sort_subcommands", None)
        )

        # Click defaults root `ctx.color` to `None` (GNU `auto`: keep ANSI on a
        # TTY, strip it when piped). For a parentless context, pre-seed it from the
        # color environment variables so the eager help and version screens, which
        # can render before `--color` resolves, still honor `FORCE_COLOR` /
        # `NO_COLOR`. With no recognized variable the value stays `None` (auto),
        # and the `ColorOption` callback later layers the command line, configuration
        # and `--accessible` on top.
        if not self.parent and self.color is None:
            self.color = resolve_color_env()

        # Honor the POSIX conformance switch: when POSIXLY_CORRECT is present in the
        # environment, stop parsing options at the first positional argument, the way
        # GNU getopt-based tools do. Presence alone is enough, regardless of value.
        # This can only tighten parsing (True -> False), never loosen it.
        if POSIXLY_CORRECT_ENVVAR in os.environ:
            self.allow_interspersed_args = False

        # Update the context's meta property with the one provided by user.
        if meta:
            self._meta.update(meta)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        """Like parent's `__exit__`, but ends an aborted run whose notice is printed.

        {func}`_abort_notice` prints `Aborted!` before the contexts of the run
        close. Click would print it again once the root context has closed, so
        that context exits with Click's abort status itself.
        """
        notice = _ABORT_NOTICE.get()
        # Only the exit that closes the root context ends the run.
        if (
            notice is None
            or notice.printed_for is None
            or self._depth != 1
            or self.parent is not None
            or self.command is not notice.command
        ):
            return super().__exit__(exc_type, exc_value, tb)
        try:
            suppressed = super().__exit__(exc_type, exc_value, tb)
        except _ABORT_EXCEPTIONS as exc:
            # A close callback raised an abort, like a second Ctrl+C landing there.
            if not notice.covers(exc):
                raise
            raise Exit(1) from exc
        if suppressed or not (
            isinstance(exc_value, _ABORT_EXCEPTIONS) and notice.covers(exc_value)
        ):
            return suppressed
        raise Exit(1) from exc_value

    def render_table(
        self,
        table_data: Sequence[Sequence[str | None]],
        headers: Sequence[THeader] | None = None,
        table_format: TableFormat | None = None,
        sort_key: Callable[[Sequence[str | None]], Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Render a table honoring the invocation's table options, and return it.

        Same contract as {func}`click_extra.table.render_table`, with
        `table_format` and `sort_key` defaulting to the values resolved by
        the `--table-format` and `--sort-by` options (read from
        {data}`~click_extra.context.TABLE_FORMAT` and
        {data}`~click_extra.context.TABLE_SORT_KEY`). `ctx.meta` is
        shared along the context chain, so this works from any subcommand
        without reaching for the root context. Without those options in the
        chain, falls back to the default format and no sort.
        """
        if table_format is None:
            table_format = get(self, TABLE_FORMAT)
        if sort_key is None:
            sort_key = get(self, TABLE_SORT_KEY)
        return render_table(
            table_data,
            headers,
            table_format=table_format,
            sort_key=sort_key,
            **kwargs,
        )

    def print_table(
        self,
        table_data: Sequence[Sequence[str | None]],
        headers: Sequence[THeader] | None = None,
        table_format: TableFormat | None = None,
        sort_key: Callable[[Sequence[str | None]], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Render a table honoring the invocation's table options, and print it.

        The printing counterpart of {meth}`render_table`: same defaulting of
        `table_format` and `sort_key` from the context's shared `meta`,
        delegating to {func}`click_extra.table.print_table` (which also
        handles ANSI translation and colorization policy).
        """
        if table_format is None:
            table_format = get(self, TABLE_FORMAT)
        if sort_key is None:
            sort_key = get(self, TABLE_SORT_KEY)
        print_table(
            table_data,
            headers,
            table_format=table_format,
            sort_key=sort_key,
            **kwargs,
        )


class _WatchedContextMixin:
    """Watches what a run of the command ends on.

    Every context is built through `_watched_context`, which records what leaves
    a root context: its parsing, then its closing. See
    `click_extra.execution._run_end_watch` for what reads the record.
    """

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: Any,
    ) -> click.Context:
        """Like parent's `make_context`, but watches what the run ends on."""
        return _watched_context(
            super().make_context,  # type: ignore[misc]
            info_name,
            args,
            parent,
            **extra,
        )


class Command(  # type: ignore[misc]
    _HelpColorsMixin, _WatchedContextMixin, cloup.Command
):
    """Like `cloup.command`, with sane defaults and extra help screen colorization."""

    context_class: type[cloup.Context] = Context

    examples: tuple[tuple[str, str], ...] = ()
    """`(description, command)` pairs showing the command in use.

    Normalized from the `examples` constructor argument by
    {func}`~click_extra.command_doc.normalize_examples`. Declared here so the
    attribute exists on every command, whether or not its author passed any:
    the renderers reading it (help screen, man page, and every
    {class}`~click_extra.command_doc.HelpFormat` backend) then need no guard.
    """

    def __init__(
        self,
        *args: Any,
        version_fields: dict[str, Any] | None = None,
        config_schema: type | Callable[[dict[str, Any]], Any] | None = None,
        config_strict: bool = False,
        schema_strict: bool = False,
        fallback_sections: Sequence[str] = (),
        config_validators: Sequence[ConfigValidator] = (),
        included_params: Sequence[str] | None = None,
        excluded_params: Sequence[str] | None = None,
        config_cascade: bool = False,
        extra_option_at_end: bool = True,
        option_priorities: Mapping[str, float] | None = None,
        populate_auto_envvars: bool = True,
        extra_keywords: HelpKeywords | None = None,
        excluded_keywords: HelpKeywords | None = None,
        examples: Sequence[Sequence[str]] = (),
        **kwargs: Any,
    ) -> None:
        """Like `cloup.Command.__init__`, with Click Extra's defaults and parameters.

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
        :param config_cascade: forwarded to the default
            {class}`~click_extra.config.option.ConfigOption`'s `cascade`
            setting: auto-discovery layers every configuration file it finds, the
            most local one winning on key lookup, instead of stopping at the
            first.
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
            environment variables registered. This addresses the shortcoming of
            `click` which only evaluates them dynamically. Once registered, the
            auto-generated environment variables get displayed in the help screen,
            fixing [click#2483 issue](https://github.com/pallets/click/issues/2483).
            On Windows, environment variable names are case-insensitive, so they are
            normalized to uppercase.

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

        # Pull Click Extra's own settings out before Cloup and Click read the rest,
        # forcing each one that is set on every option.
        for setting in EXTRA_OPTION_SETTINGS:
            value = default_ctx_settings.pop(setting)
            if value is not None:
                for param in self.params:
                    # These attributes are specific to options.
                    if isinstance(param, click.Option):
                        setattr(param, setting, value)
        self.context_settings: dict[str, Any] = default_ctx_settings

        # Forward version template fields to the version option.
        if version_fields:
            for param in self.params:
                if isinstance(param, VersionOption):
                    for field_id, field_value in version_fields.items():
                        param.pin_field(field_id, field_value)

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
            or config_cascade
        ):
            for param in self.params:
                if isinstance(param, ConfigOption):
                    param.apply_command_settings(
                        config_schema=config_schema,
                        config_strict=config_strict,
                        schema_strict=schema_strict,
                        fallback_sections=fallback_sections,
                        config_validators=config_validators,
                        included_params=included_params,
                        excluded_params=excluded_params,
                        cascade=config_cascade,
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
            for key in (*param_spellings(param), param.name):
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
        {class}`~click_extra.command_doc.HelpFormat` backend
        ({func}`~click_extra.command_doc._build_option_groups`), and the
        completion specs ({func}`~click_extra.param_tools.iter_params_for_display`)
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
        the `help` attribute as is. Resolution goes through
        {func}`~click_extra.param_tools.resolve_param_help` instead, the same helper
        the man page and every other {class}`~click_extra.command_doc.HelpFormat`
        backend reads, so an operand carries one description whatever renders it.
        An argument without help gets an empty string, not `None`.
        """
        return arg.make_metavar(ctx=ctx), resolve_param_help(arg, ctx) or ""

    def format_params(self, ctx: click.Context, formatter: Any) -> None:
        """Draw the parameter sections of the help screen.

        Reimplements `cloup.OptionGroupMixin.format_params` to honor the order
        {meth}`split_option_groups` computes, and to title the ungrouped section
        against the groups the CLI author declared alone. Cloup picks that title
        by counting every visible group, click-extra's included, so a command
        carrying the default options would otherwise never show a plain `Options`
        heading.
        """
        formatter = ensure_is_cloup_formatter(formatter)

        sections = []
        arguments_section = self.get_arguments_help_section(ctx)
        if arguments_section:
            sections.append(arguments_section)

        own_groups, extra_groups = self.split_option_groups()
        default_group = self.get_default_option_group(
            ctx,
            is_the_only_visible_option_group=all(group.hidden for group in own_groups),
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

        An abort still prints Click's `Aborted!`, which Click prints on purpose
        ([pallets/click#2584](https://github.com/pallets/click/issues/2584)), but
        prints it as soon as the abort leaves the command: before the close
        callbacks run, where Click prints it after them.

        A Ctrl+C then ends the process the way an unhandled Ctrl+C does in Python:
        by `SIGINT`, once the running threads finish. Click
        [exits with status `1`](https://github.com/pallets/click/blob/8.5.0/src/click/core.py#L1591-L1595)
        instead, which tells a calling shell the program handled the interrupt
        itself, so a shell loop runs on.

        The process-wide state the options of Click Extra take for a run leaves
        with it, a run that fails while parsing included: the log handler they
        attach to the `root` logger, the levels the verbosity options set, and the
        color the color options publish. See `click_extra.context._scoped_run`.

        A standard stream that cannot encode Unicode is switched to UTF-8 before
        anything prints, and stays so: see
        {func}`~click_extra.output.force_unicode_output`.
        """
        force_unicode_output()

        if not prog_name and self.name:
            prog_name = self.name

        with (
            _scoped_run(),
            _interrupt_handling(),
            _owning_abort_notice(self, kwargs.get("standalone_mode", True)),
        ):
            try:
                return super().main(args=args, prog_name=prog_name, **kwargs)
            except SystemExit:
                if _interrupted():
                    _exit_interrupted()
                raise

    def invoke(self, ctx: click.Context) -> Any:
        """Like parent's `invoke`, but prints the `Aborted!` of an abort at once.

        Click prints it once the root context has closed, so after every close
        callback. See `_abort_notice`.
        """
        with _abort_notice(ctx):
            return super().invoke(ctx)

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: Any,
    ) -> Any:
        """Like parent's `make_context`, but seeds `ctx.meta` with the raw arguments.

        A copy of the raw, pre-parsed arguments goes under
        {data}`~click_extra.context.RAW_ARGS`, which
        {meth}`~click_extra.show_params.ShowParamsOption.print_params` re-parses to
        draw the `--params` table. A root context also records the name the CLI was
        invoked under, as {data}`~click_extra.context.INVOCATION_NAME`.

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
        extra["meta"] = meta
        return super().make_context(info_name, args, parent, **extra)

    def format_examples(
        self,
        ctx: click.Context,
        formatter: click.HelpFormatter,
    ) -> None:
        r"""Write an `Examples:` section listing the command's {attr}`examples`.

        Each entry renders its description, then the command line it describes,
        indented behind a `$` prompt. A command declaring none writes nothing at
        all, so a help screen only grows the section when it has something to
        put in it.

        The command lines go out verbatim rather than through
        `formatter.write_text()`: an example exists to be copied, and Click's
        text wrapper would fold a long one onto a second line mid-token. This is
        the same call the `\b` no-rewrap marker makes for help prose.

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
        *not* typed last, so any option that renders and exits (`--help`,
        `--version`, `--man`, `--params`) is processed before every eager option
        the user did not also type. `--color`, `--no-color`, `--accessible` and
        `--theme` would therefore pin their state too late: the screen has already
        rendered. This pre-pass resolves them ahead of the regular parameter loop,
        so the choice reaches those screens whatever its position.

        {class}`~click_extra.accessibility.AccessibleOption` is resolved first,
        because it works by *lowering the `--color` default* through the context's
        `default_map`, which the color options then read. Reversing the two would
        leave the lowered default unread. Its global `ACCESSIBLE` environment
        variable triggers the pre-pass as well: the flag is absent from the command
        line in that case, which is exactly the sorting hole described above.
        Accessible mode advertises itself as equivalent to `--no-color`, so
        `--accessible --version` has to render a screen free of ANSI codes.

        {class}`~click_extra.theme.ThemeOption` is resolved last, and for the same
        reason it is resolved at all: a palette whose only observable effect is the
        look of a rendered screen is worthless if it lands after the screen. Its
        environment variables trigger the pre-pass too, both the machine-wide
        {data}`~click_extra.theme.THEME_ENVVAR` and the per-CLI `<CLI>_THEME` that
        Click derives, since neither puts a flag on the command line. The per-CLI
        `<CLI>_COLOR` and `<CLI>_NO_COLOR` variables Click derives for the color
        options trigger it for the same reason.

        ```{note}
        Every group is resolved a second time by `super().parse_args()`. Their
        callbacks are idempotent (no env-var side effects, no prompt, and a
        `setdefault` on the `default_map`), so re-running them lands the exact same
        state.

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
        # command line, or when the environment asks for accessible mode, a color
        # choice or a palette.
        flags = {
            flag
            for param in (*accessible_params, *color_params, *theme_params)
            for flag in param_spellings(param)
        }
        on_cli = any(arg.split("=", 1)[0] in flags for arg in args)
        envvars = set()
        if accessible_params:
            envvars.add(ACCESSIBLE_ENVVAR)
        if theme_params:
            envvars.add(THEME_ENVVAR)
        for param in (*color_params, *theme_params):
            envvars.update(param_envvar_ids(param, ctx))
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


def _watched_context(
    make_context: Callable[..., click.Context],
    info_name: str | None,
    args: list[str],
    parent: click.Context | None,
    **extra: Any,
) -> click.Context:
    """Build a context with `make_context`, and watch what a root one ends on.

    The run ends on what leaves the root context: its parsing here, then its
    closing, since a context that fails to parse never closes. See
    `click_extra.execution._run_end_watch`.
    """
    if parent is not None:
        return make_context(info_name, args, parent, **extra)
    with _run_end_watch():
        ctx = make_context(info_name, args, parent, **extra)
    ctx.with_resource(_run_end_watch())
    return ctx


def _enhance_short_option_error(
    exc: click.NoSuchOption,
    original_args: list[str],
    ctx: click.Context,
) -> NoReturn:
    """Re-raise *exc* with the full token and close-match suggestions when
    appropriate, or re-raise it unchanged.

    Click's parser treats `-dbgwrong` as stacked short flags `-d -b -g -w -r -o
    -n -g`, then reports "No such option: -d" on the first unregistered
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
    - Upstream issue: [pallets/click#2779](https://github.com/pallets/click/issues/2779).
    - `_match_short_opt` in Click's `parser.py` raises `NoSuchOption`
      with only the single failed character.
    - `_match_long_opt` already provides `get_close_matches` suggestions,
      but its exception is discarded when `_process_opts` falls through to
      the short-option path.
    - Upstream docs: [pallets/click#3179](https://github.com/pallets/click/pull/3179).
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
    all_option_names = [
        name
        for param in ctx.command.params
        if isinstance(param, click.Option)
        for name in param_spellings(param)
    ]

    # Deferred import: keeps difflib off the startup path of every CLI.
    from difflib import get_close_matches

    possibilities = get_close_matches(original_token, all_option_names)

    raise click.NoSuchOption(original_token, possibilities=possibilities, ctx=ctx)


class ColorizedCommand(  # type: ignore[misc]
    _HelpColorsMixin, _WatchedContextMixin, click.Command
):
    """Click Command with help colorization but no extra params.

    Mixes in `_HelpColorsMixin` for keyword
    highlighting and uses {class}`Context` for the colorized
    formatter, without inheriting from `Command` (which would inject
    `default_params`).

    Watches what its run ends on, like `Command`: a patched CLI runs under
    Click's own `main()`, inside the `wrap` command, and the watch is what tells
    that command a Ctrl+C ended its target.

    Use this as a base for lightweight subcommands (like `help`) or for
    monkey-patching third-party CLIs (via {func}`~click_extra.cli_wrapper.patch_click`).
    """

    context_class: type[cloup.Context] = Context


class ColorizedGroup(  # type: ignore[misc]
    _HelpColorsMixin, _WatchedContextMixin, click.Group
):
    """Click Group with help colorization but no extra params.

    Same as {class}`ColorizedCommand` but for groups.
    """

    context_class: type[cloup.Context] = Context


class _InjectedCommand(ColorizedCommand):
    """A subcommand a group registers on its own, like `help`.

    {class}`Group` treats it apart from the subcommands the CLI author declares:
    registering one of theirs under the same name replaces it, and a listing in
    registration order puts it last.
    """


class HelpCommand(_InjectedCommand):
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
                # Click picks the close matches out of the listing, which names
                # the lazy subcommands not imported yet too.
                raise click.NoSuchCommand(
                    name,
                    possibilities=target_cmd.list_commands(target_ctx),
                    ctx=parent_ctx,
                )
            target_ctx = child_context(resolved, target_ctx, name)
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
        """Recursively search a group's subcommands.

        Walks the subcommands every rendering of the tree lists (see
        {func}`~click_extra.param_tools.iter_subcommands`), so a hidden one stays
        out of the results. Each is read under a child context that processes
        none of its parameters, so a search runs no callback.
        """
        for sub_name, sub_cmd in iter_subcommands(group, group_ctx):
            if sub_name == "help":
                continue

            cmd_path = f"{prefix}{sub_name}" if prefix else sub_name
            sub_ctx = child_context(sub_cmd, group_ctx, sub_name)

            # Check command docstring.
            if sub_cmd.help and term_lower in sub_cmd.help.lower():
                results.append((cmd_path, sub_cmd.help))

            # Check each parameter.
            for param in sub_cmd.get_params(sub_ctx):
                opts_str = " / ".join(param.opts)
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
    """Create the synthetic `help` subcommand for a `Group`."""
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

    def _registered_subcommands(self) -> list[str]:
        """Subcommand names in registration order, before any ordering is applied.

        The extension point {class}`LazyGroup` overrides to fold in the subcommands
        it has not imported yet.
        """
        return list(self.commands)

    def _resolve_subcommand(self, name: str) -> click.Command | None:
        """The subcommand registered under *name*, or `None`, with no context.

        The extension point {class}`LazyGroup` overrides to import a subcommand it
        has not loaded yet. Unlike {meth}`get_command`, it needs no context, so it
        serves the code running ahead of one, like the personality dispatch of
        {class}`~click_extra.multicall.MulticallGroup`.
        """
        return self.commands.get(name)

    def listed_command(self, ctx: click.Context, name: str) -> click.Command | None:
        """The command the help screen describes under *name*: the subcommand.

        The extension point {class}`LazyGroup` overrides to describe a lazy
        subcommand by the help it declares, without importing it. The keyword
        highlighting of the help screen reads the subcommands through here.
        """
        return self.get_command(ctx, name)

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Subcommand names in presentation order.

        Sorted on `subcommand_priorities` first, then broken apart by
        {meth}`~click_extra.commands.Group.must_sort_subcommands`: alphabetically,
        or by registration order. With no priority declared every subcommand ties,
        leaving the tie-break as the only ordering, which is Click's plain
        alphabetical listing.

        In registration order the auto-injected subcommands, like `help`, are
        listed last, wherever they happen to have been registered: `Group.__init__`
        appends `help` before any `@cli.command()` decorator runs, while a
        `commands=[…]` constructor argument lands it after, so its natural position
        says nothing about the author's intent. Mirrors what `extra_option_at_end`
        does to options.
        """
        names = self._registered_subcommands()
        if self.must_sort_subcommands(ctx):
            names = sorted(names)
        else:
            names = sorted(
                names,
                key=lambda name: isinstance(self.commands.get(name), _InjectedCommand),
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
        """Like `cloup.Group.add_command`, but a subcommand of the author's replaces
        an auto-injected one of the same name, like the `help` subcommand.
        """
        cmd_name = name or cmd.name
        if (
            cmd_name
            and isinstance(self.commands.get(cmd_name), _InjectedCommand)
            and not isinstance(cmd, _InjectedCommand)
        ):
            # Remove the injected command from its Cloup section, so the author's
            # can take its place without a duplicate error.
            for section in (*self._user_sections, self._default_section):
                if section.commands.pop(cmd_name, None) is not None:
                    break
            del self.commands[cmd_name]
        super().add_command(cmd, name, **kwargs)


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

    short_help: str | None = None
    """The first paragraph of the subcommand's help, for the help screen to list.

    Declared, it lets the group's help screen list the subcommand without importing
    it: the listing shortens it the way it shortens the help of an imported
    subcommand, so the line reads the same before and after the import. Left to
    `None`, drawing the help screen imports the subcommand to read its help.
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
        declared with a {class}`~click_extra.commands.LazySubcommand` instead of a
        bare string:

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

        # A subcommand declaring its help is listed by a stand-in until imported.
        # It sits in the section the subcommand is filed under, never in
        # `self.commands`, so resolving the name still imports the real one.
        self._stand_ins: dict[str, click.Command] = {}
        for name, spec in self.lazy_subcommands.items():
            if spec.short_help is None or name in self.commands:
                continue
            stand_in = click.Command(name, help=spec.short_help)
            self._stand_ins[name] = stand_in
            if spec.section is not None or spec.fallback_to_default_section:
                self._add_command_to_section(stand_in, name, spec.section)

    def _registered_subcommands(self) -> list[str]:
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

    def _resolve_subcommand(self, name: str) -> click.Command | None:
        """Like the parent, but importing a lazy subcommand not loaded yet.

        Registration goes through {meth}`_register_lazy`, so the subcommand lands
        in the section it was declared with. No configuration is applied to it:
        that takes the context {meth}`get_command` receives.
        """
        if name in self.lazy_subcommands and name not in self.commands:
            return self._register_lazy(name)
        return super()._resolve_subcommand(name)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Get a command by name, loading lazily if necessary."""
        if cmd_name in self.lazy_subcommands and cmd_name not in self.commands:
            self._register_lazy(cmd_name)
            # Inject the lazy command's config section into the context's
            # default_map, since it was missed by ConfigOption.merge_default_map.
            self._apply_config_to_parent_context(ctx, cmd_name)

        return super().get_command(ctx, cmd_name)

    def listed_command(self, ctx: click.Context, name: str) -> click.Command | None:
        """Like the parent, but describing a lazy subcommand not imported yet by
        the stand-in its {attr}`~LazySubcommand.short_help` builds."""
        if name in self._stand_ins and name not in self.commands:
            return self._stand_ins[name]
        return super().listed_command(ctx, name)

    def _register_lazy(self, cmd_name: str) -> click.Command:
        """Import `cmd_name` and register it with the settings it was declared with.

        The single place a lazy subcommand enters the group, so a settings-carrying
        {class}`~click_extra.commands.LazySubcommand` reaches Cloup whichever route
        triggered the import.
        """
        spec = self.lazy_subcommands[cmd_name]
        cmd_object = self._lazy_load(cmd_name)
        # A stand-in listed the subcommand so far: the subcommand takes its slot,
        # so the help screen keeps listing it in the same place of its section.
        stand_in = self._stand_ins.get(cmd_name)
        for section in (*self._user_sections, self._default_section):
            if stand_in is not None and section.commands.get(cmd_name) is stand_in:
                section.commands[cmd_name] = cmd_object
                self.add_command(cmd_object, fallback_to_default_section=False)
                return cmd_object
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

        Covers a lazy command imported after the configuration loaded, which the
        walk building `ConfigOption.params_template` did not reach, so its config
        section never reached `default_map`. This method reads the full config
        from `ctx.meta` and places the lazy command's section into
        `ctx.default_map[cmd_name]`.

        Click will then pass that dict as the `default_map` of the command's own
        context.

        An allowlist (`included_params`) on the root's `ConfigOption` turns the
        injection off. Its walk imports each subcommand an allowed ID lies under,
        so the template already carries every allowed value. A section injected
        here would bypass the allowlist.
        """
        if any(
            isinstance(param, ConfigOption) and param.included_params is not None
            for param in ctx.find_root().command.params
        ):
            return

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
