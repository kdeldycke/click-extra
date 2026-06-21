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
"""Helpers and utilities to apply ANSI coloring to terminal content."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from configparser import RawConfigParser
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from enum import Enum
from functools import lru_cache
from gettext import gettext as _

import click
import click.formatting
import cloup
from click._compat import term_len
from cloup._util import identity

from . import ParameterSource, theme as _theme
from .parameters import ExtraOption
from .theme import HelpTheme, ThemeChoice

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from typing import ClassVar

    from click.parser import _OptionParser
    from cloup.styling import IStyle


color_envvars = {
    # Colors.
    "COLOR": True,
    "COLORS": True,
    "CLICOLOR": True,
    "CLICOLORS": True,
    "FORCE_COLOR": True,
    "FORCE_COLORS": True,
    "CLICOLOR_FORCE": True,
    "CLICOLORS_FORCE": True,
    # No colors.
    "NOCOLOR": False,
    "NOCOLORS": False,
    "NO_COLOR": False,
    "NO_COLORS": False,
    # LLM agents have no use for ANSI codes.
    "LLM": False,
}
"""List of environment variables recognized as flags to switch color rendering on or
off.

The key is the name of the variable and the boolean value the value to pass to
``--color`` option flag when encountered.

Source:

- https://github.com/pallets/click/issues/558
- https://github.com/pallets/click/issues/1090
- https://github.com/pallets/click/issues/1498
- https://github.com/pallets/click/issues/3022
- https://blog.codemine.be/posts/2026/20260222-be-quiet/
"""


COLOR_DISABLING_TERMS = frozenset({"dumb", "unknown"})
"""``TERM`` values marking a terminal too limited for ANSI niceties.

A ``dumb`` or ``unknown`` terminal advertises neither SGR color nor the
cursor-control codes (carriage return, clear-line) an animation relies on, so both
Click Extra's color resolution (:func:`resolve_color_env`) and the spinner's
animation gating (:meth:`click_extra.spinner.Spinner._resolve_enabled`) treat these
two values as a hard opt-out. Sharing the set keeps the color and animation axes from
drifting apart.

An *unset* ``TERM`` is deliberately excluded: it is common on legitimately
color-capable streams (subprocesses, some IDEs) where defaulting to off would be a
regression. This matches `Rich
<https://github.com/Textualize/rich/blob/master/rich/console.py>`_, which keys its
own dumb-terminal detection on the same two values and not on absence.
"""


def resolve_color_env() -> bool | None:
    """Reconcile the recognized color environment variables into a tri-state.

    Inspects every variable listed in :data:`color_envvars` and returns:

    - ``True`` if at least one *enabling* variable (``FORCE_COLOR``, ``CLICOLOR``, …)
      is set. Enabling wins over disabling, so a single one is enough to keep colors.
    - ``False`` if only *disabling* variables (``NO_COLOR``, ``LLM``, …) are set.
    - ``None`` when no recognized variable is present, leaving the caller free to
      apply its own default (typically ``auto``).

    A bare variable (no value), or one whose value cannot be parsed as a boolean,
    counts as activation, in the permissive spirit of the `NO_COLOR
    <https://no-color.org>`_ and `FORCE_COLOR <https://force-color.org>`_ conventions.

    A ``dumb`` or ``unknown`` ``TERM`` (see :data:`COLOR_DISABLING_TERMS`) casts a
    disabling vote as well, so a terminal that cannot render ANSI is treated as
    color-off even when it still reports as a TTY. Because enabling wins, an explicit
    ``FORCE_COLOR`` stays authoritative over it.
    """
    enabling = set()
    for var, enables in color_envvars.items():
        if var in os.environ:
            # Presence without a value encodes an activation, hence the default to
            # "true"; an unparsable value falls back to True in the same spirit.
            raw_value = os.environ.get(var, "true")
            parsed = RawConfigParser.BOOLEAN_STATES.get(raw_value.lower(), True)
            enabling.add(enables ^ (not parsed))
    # A dumb/unknown terminal cannot render ANSI color: cast a disabling vote that an
    # explicit enabling variable still overrides, but which beats the auto default
    # when no recognized color variable is set.
    if os.environ.get("TERM", "").lower() in COLOR_DISABLING_TERMS:
        enabling.add(False)
    if not enabling:
        return None
    return True in enabling


@contextmanager
def forced_color() -> Iterator[None]:
    """Force ANSI color while Click Extra captures CLI text for documentation.

    Click Extra renders CLI help and output into docs from both the MkDocs plugin
    (:mod:`click_extra.mkdocs`) and the Sphinx directives
    (:mod:`click_extra.sphinx.click`). During a build that output is a pipe, not a TTY,
    so the underlying renderers strip their escape codes. Two independent color systems
    have to be defeated:

    - Click's, gated by ``should_strip_ansi`` / ``ctx.color`` (what ``click.echo`` and
      the Click and Click Extra help formatters consult). Sphinx's runner additionally
      flips this one with ``click.testing.CliRunner(color=True)``.
    - Rich's, gated by ``rich.console.Console.is_terminal``, which ignores the above and
      reads ``FORCE_COLOR`` (https://force-color.org). This is the system ``rich-click``
      uses, and ``color=True`` never reaches it.

    ``FORCE_COLOR`` is the only signal common to both systems (Rich reads it directly;
    Click Extra recognizes it through :data:`color_envvars`), so it is the lever we set
    here. We also clear the color-disabling variables Click Extra recognizes
    (``NO_COLOR``, ``LLM``, …) so an opt-out in the build environment cannot suppress the
    rendering, and pin ``COLORTERM=truecolor`` so the branded 24-bit themes render at
    full depth instead of being quantized to the 256-color palette (see
    :func:`~click_extra.styling.supports_truecolor`). The previous environment is
    restored on exit, so the override never leaks beyond a single capture.
    """
    disabling = [var for var, enables in color_envvars.items() if not enables]
    saved = {
        var: os.environ.get(var) for var in ("FORCE_COLOR", "COLORTERM", *disabling)
    }
    os.environ["FORCE_COLOR"] = "1"
    os.environ["COLORTERM"] = "truecolor"
    for var in disabling:
        os.environ.pop(var, None)
    try:
        yield
    finally:
        for var, value in saved.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value


COLOR_WHEN = ("auto", "always", "never")
"""GNU-canonical tri-state values accepted by ``--color=<WHEN>``.

``auto`` defers to terminal detection, ``always`` forces ANSI on, ``never`` strips
it. See the `GNU coding standards
<https://www.gnu.org/prep/standards/html_node/_002d_002dcolor.html>`_ and `this
discussion <https://news.ycombinator.com/item?id=36102377>`_.
"""


_WHEN_TO_TRISTATE: dict[str, bool | None] = {
    "auto": None,
    "always": True,
    "never": False,
}
"""Map each :data:`COLOR_WHEN` choice to the ``ctx.color`` value it produces.

``None`` lets Click auto-detect colorization from the output stream's TTY status,
``True`` keeps ANSI codes, ``False`` strips them.
"""


_COLOR_CLI_OVERRIDE_KEY = "click_extra.color_cli_override"
"""Context meta key flagging an explicit ``--no-color`` on the command line.

Set by :meth:`NoColorOption.set_no_color` and read by :meth:`ColorOption.set_color` so
an explicit negative alias outranks the color environment variables, which may only
override the built-in default.
"""


class ColorOption(ExtraOption):
    """A pre-configured ``--color[=WHEN]`` tri-state option.

    Mirrors the `GNU convention
    <https://www.gnu.org/prep/standards/html_node/_002d_002dcolor.html>`_: ``WHEN`` is
    one of :data:`COLOR_WHEN` (``auto``, ``always`` or ``never``), and a bare
    ``--color`` (no value) means ``always``. The negative alias ``--no-color`` is
    carried by the separate :class:`NoColorOption`, because Click forbids attaching
    ``/--no-x`` secondary flags to a value option.

    The resolved tri-state lands on ``ctx.color``, the Click-standard attribute that
    ``echo()`` reads through its ``resolve_color_default()`` → ``should_strip_ansi()``
    chain: ``True`` keeps ANSI codes, ``False`` strips them, ``None`` (``auto``) defers
    to the output stream's TTY status.

    This option is eager by default, so other eager options (like ``--version``) are
    rendered with the resolved color state.

    .. note::
        ``--color`` is deliberately not wired to an ``envvar``. The color environment
        variables (``NO_COLOR``, ``FORCE_COLOR``, …) are read manually through
        :func:`resolve_color_env`. Letting Click manage them would dump the whole
        :data:`color_envvars` set into the ``--show-params`` env-var column, and only
        bind one variable per option anyway.
    """

    _gnu_optional_value: ClassVar[bool] = True
    """Marks the option for GNU-style optional-argument parsing.

    Read by :meth:`add_to_parser` to make a bare ``--color`` resolve to
    ``flag_value`` instead of swallowing the following token.
    """

    def add_to_parser(self, parser: _OptionParser, ctx: click.Context) -> None:
        """Register the option, then teach the parser GNU optional-argument rules.

        Click's optional-value parser binds ``--color`` to the next token whenever it
        does not look like an option, so ``mycli --color subcommand`` would consume
        ``subcommand`` as the color value and fail. GNU instead binds an optional
        argument only when it is attached with ``=``.

        This wraps the parser's long-option matcher so a bare ``--color``
        replays as ``--color=<flag_value>`` (``always``) and leaves the following
        argument untouched, while ``--color=<when>`` keeps working. The wrapper stays
        inert for every option that does not carry :attr:`_gnu_optional_value`, so it
        is safe to install on the shared parser.
        """
        super().add_to_parser(parser, ctx)

        wrapped = parser._match_long_opt

        def _match_long_opt(opt, explicit_value, state):
            if explicit_value is None:
                parsed = parser._long_opt.get(opt)
                if parsed is not None and getattr(
                    parsed.obj,
                    "_gnu_optional_value",
                    False,
                ):
                    # Replay as if the user had typed --color=<flag_value>.
                    wrapped(opt, parsed.obj.flag_value, state)
                    return
            wrapped(opt, explicit_value, state)

        parser._match_long_opt = _match_long_opt  # type: ignore[method-assign]

    def set_color(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: str,
    ) -> None:
        """Resolve ``--color=<WHEN>`` against the environment and pin ``ctx.color``.

        Precedence, highest first:

        #. An explicit ``--color`` on the command line.
        #. The color environment variables, but only when the value comes from the
           built-in default. A configuration file or ``--accessible`` (both seen here
           as a non-``DEFAULT`` source) therefore wins over the environment, matching
           :class:`~click_extra.accessibility.AccessibleOption`.
        #. A color state already pinned by ``--no-color``, a forced
           test runner, or an explicit ``Context(color=...)`` — preserved when this
           option only resolves to ``auto`` from its default.
        #. The ``auto`` default, leaving ``ctx.color`` at ``None`` for TTY detection.
        """
        when = value
        source = ctx.get_parameter_source("color")

        # The environment can only override a pure built-in default, never a value
        # coming from the command line, a configuration file or --accessible. An
        # explicit --no-color (recorded by NoColorOption) is a
        # command-line choice and therefore outranks the environment too.
        if source == ParameterSource.DEFAULT and not ctx.meta.get(
            _COLOR_CLI_OVERRIDE_KEY,
        ):
            env_color = resolve_color_env()
            if env_color is not None:
                ctx.color = env_color
                return

        tristate = _WHEN_TO_TRISTATE[when]

        # "auto" defers to TTY detection. Do not overwrite a color state already
        # pinned upstream (--no-color, a forced runner, Context(color=...)) unless the
        # user explicitly spelled out --color=auto on the command line.
        if (
            tristate is None
            and source != ParameterSource.COMMANDLINE
            and ctx.color is not None
        ):
            return

        ctx.color = tristate

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=False,
        flag_value="always",
        default="auto",
        is_eager=True,
        expose_value=False,
        help=_(
            "Colorize the output. A bare --color is the same as --color=always; "
            "--no-color aliases --color=never.",
        ),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--color",)

        kwargs.setdefault("callback", self.set_color)
        kwargs.setdefault("type", click.Choice(COLOR_WHEN))

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            flag_value=flag_value,
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )


class NoColorOption(ExtraOption):
    """``--no-color`` flag that forces ``--color=never``.

    Click rejects ``/--no-x`` secondary flags on a value option, so the negative
    alias of the tri-state :class:`ColorOption` cannot live on it and is provided
    here as a standalone boolean flag. When set, it pins ``ctx.color`` to ``False``;
    when absent it is a no-op, leaving the resolution to :class:`ColorOption`.

    Hidden by default to keep the help screen focused on the canonical ``--color``,
    whose own help text documents this alias. Eager by default, like
    :class:`ColorOption`, so the color state is settled before other eager options
    render.
    """

    def set_no_color(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Force ``ctx.color`` off when a negative alias is passed; no-op otherwise."""
        if value:
            ctx.color = False
            # Flag the explicit choice so ColorOption keeps the environment from
            # overriding it (the environment may only override the built-in default).
            ctx.meta[_COLOR_CLI_OVERRIDE_KEY] = True

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=True,
        default=False,
        is_eager=True,
        expose_value=False,
        hidden=True,
        help=_("Disable colorization (alias of --color=never)."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--no-color",)

        kwargs.setdefault("callback", self.set_no_color)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            hidden=hidden,
            help=help,
            **kwargs,
        )


@dataclass
class HelpKeywords:
    """Structured collection of keywords extracted from a Click context for
    help screen highlighting.

    Each field corresponds to a semantic category with its own styling.
    """

    cli_names: set[str] = field(default_factory=set)
    subcommands: set[str] = field(default_factory=set)
    command_aliases: set[str] = field(default_factory=set)
    arguments: set[str] = field(default_factory=set)
    long_options: set[str] = field(default_factory=set)
    short_options: set[str] = field(default_factory=set)
    choices: set[str] = field(default_factory=set)
    choice_metavars: set[str] = field(default_factory=set)
    metavars: set[str] = field(default_factory=set)
    envvars: set[str] = field(default_factory=set)
    defaults: set[str] = field(default_factory=set)

    def merge(self, other: HelpKeywords) -> None:
        """Merge another ``HelpKeywords`` into this one.

        Each set field is updated with the corresponding set from ``other``.
        """
        for f in fields(self):
            getattr(self, f.name).update(getattr(other, f.name))

    def subtract(self, other: HelpKeywords) -> None:
        """Remove keywords found in ``other`` from this instance.

        Each set field is difference-updated with the corresponding set from
        ``other``. Mirror of :meth:`merge`.
        """
        for f in fields(self):
            getattr(self, f.name).difference_update(getattr(other, f.name))


class _HelpColorsMixin:
    """Adds extra-keywords highlighting to Click commands.

    This mixin for ``click.Command``-like classes intercepts the top-level helper-
    generation method to initialize the formatter with dynamic settings. This is
    implemented at this stage so we have access to the global context.
    """

    #: Extra keywords to merge into the auto-collected set. Consumers can set
    #: this attribute on a command instance to inject additional keywords for
    #: help screen highlighting (e.g. placeholder option names like
    #: ``--<manager-id>`` that appear in prose but are not real parameters).
    extra_keywords: HelpKeywords | None = None

    #: Keywords to remove from the auto-collected set. Mirror of
    #: :attr:`extra_keywords`: any string listed here will not be highlighted
    #: even if it was collected from the Click context.
    excluded_keywords: HelpKeywords | None = None

    def collect_keywords(self, ctx: click.Context) -> HelpKeywords:
        """Parse click context to collect option names, choices and metavar keywords.

        Override this method to customize keyword collection. Call ``super()`` and
        mutate the returned ``HelpKeywords`` to extend the default set.
        """
        kw = HelpKeywords()
        subcommand_objs: set[click.Command] = set()

        # Includes the full command path and each ancestor name, so that
        # individual components are highlighted even when interleaved with
        # options (e.g. "repomatic --table-format github sync-uv-lock").
        if ctx.command_path:
            kw.cli_names.add(ctx.command_path)
        ancestor: click.Context | None = ctx
        while ancestor:
            if ancestor.info_name:
                kw.cli_names.add(ancestor.info_name)
            ancestor = ancestor.parent
        command = ctx.command

        # Will fetch command's metavar (i.e. the "[OPTIONS]" after the CLI name in
        # "Usage:") and dig into subcommands to get subcommand_metavar:
        # ("COMMAND1 [ARGS]... [COMMAND2 [ARGS]...]...").
        kw.metavars.update(command.collect_usage_pieces(ctx))

        # Get subcommands and their aliases. Process in listed order for stable
        # and predictable loading, which is important on lazy-loading.
        if isinstance(command, click.Group):
            for sub_id in command.list_commands(ctx):
                subcommand = command.get_command(ctx, sub_id)
                if not subcommand:
                    raise RuntimeError(f"Subcommand {sub_id!r} not found.")
                kw.subcommands.add(sub_id)
                kw.command_aliases.update(getattr(subcommand, "aliases", []))
                # Keep reference to subcommand object for deprecated message
                # collection below.
                subcommand_objs.add(subcommand)

        # Collect options, choices, metavars, envvars, defaults from current
        # command parameters. User-defined help options (e.g. -h, --help) are
        # seeded into the options set.
        options: set[str] = set(ctx.help_option_names)
        # Static methods are qualified with the class name (not ``self``) so
        # ``collect_keywords`` can be called on commands that don't inherit the
        # mixin (used by ``wrap.patch_click`` for third-party CLIs).
        _HelpColorsMixin._collect_params(
            command.get_params(ctx),
            ctx,
            kw,
            options,
        )

        # Collect option names and choices from parent groups. Subcommand
        # docstrings often reference parent options in usage examples (e.g.
        # "myapp --table-format github sub").
        parent_ctx = ctx.parent
        while parent_ctx:
            for param in parent_ctx.command.get_params(parent_ctx):
                if isinstance(param, click.Option) and not param.hidden:
                    options.update(param.opts)
                    options.update(param.secondary_opts)
                    if isinstance(param.type, (click.Choice, ThemeChoice)):
                        _HelpColorsMixin._collect_choice_keywords(
                            param,
                            parent_ctx,
                            kw,
                        )
                    elif type_choices := getattr(param.type, "choices", None):
                        kw.choices.update(type_choices)
                        kw.choice_metavars.add(param.make_metavar(ctx=parent_ctx))
            parent_ctx = parent_ctx.parent

        # Split options into short and long by length heuristic. Short options
        # are no longer than 2 characters like "-D", "/d", "/?", "+w", "-w".
        # XXX We cannot reuse the _short_opts and _long_opts attributes from
        # Click's parser because their values are not passed when the context
        # is updated. So we rely on simple heuristics to guess the category.
        for name in options:
            if len(name) <= 2:
                kw.short_options.add(name)
            else:
                kw.long_options.add(name)

        # Merge consumer-provided extra keywords. Uses ``getattr`` so the
        # method works on commands that don't inherit the mixin.
        extra_kw = getattr(self, "extra_keywords", None)
        if extra_kw is not None:
            kw.merge(extra_kw)

        # Note: excluded_keywords is NOT applied here. It is applied later
        # in highlight_extra_keywords(), after choice metavars have been
        # placeholdered, so that exclusions only affect cross-ref passes.

        return kw

    @staticmethod
    def _collect_choice_keywords(
        param: click.Parameter,
        ctx: click.Context,
        kw: HelpKeywords,
    ) -> None:
        """Collect choice keywords from a ``click.Choice`` parameter.

        When a custom metavar (e.g. ``LEVEL``) replaces the standard
        ``[choice1|choice2]`` rendering, original-case choice strings are
        collected to match developer-written prose (e.g. "Either CRITICAL,
        ERROR, ...") without producing false-positive highlights for common
        English words like "error" and "info".
        """
        assert isinstance(param.type, (click.Choice, ThemeChoice))
        if isinstance(param, click.Option) and param.metavar:
            # Custom metavar hides the normalized choice list. Collect
            # original-case values. This is the first step of Click's own
            # ``normalize_choice()`` before case folding is applied.
            kw.choices.update(
                c.name if isinstance(c, Enum) else str(c) for c in param.type.choices
            )
        else:
            # Standard metavar: collect the normalized forms that
            # match what Click renders in ``[choice1|choice2]``.
            kw.choices.update(
                param.type.normalize_choice(c, ctx) for c in param.type.choices
            )
            # Also collect the rendered metavar string (e.g.
            # ``[json|xml|csv]``) so it can be styled and placeholdered
            # before cross-ref highlighting. This protects choices that
            # appear in ``excluded_keywords`` from losing their
            # highlight inside their own metavar.
            kw.choice_metavars.add(param.make_metavar(ctx=ctx))

    @staticmethod
    def _collect_params(
        params: list[click.Parameter],
        ctx: click.Context,
        kw: HelpKeywords,
        options: set[str],
    ) -> None:
        """Extract keywords from a list of parameters into ``kw`` and ``options``."""
        for param in params:
            # Ignore hidden options that are not meant to be displayed.
            if isinstance(param, click.Option) and param.hidden:
                continue

            # Only collect option names from actual Option parameters, not from
            # Arguments. An Argument's opts contains the bare parameter name
            # (e.g. "keys") which would pollute the option keywords and
            # interfere with highlighting of real options like "--list-keys".
            if isinstance(param, click.Option):
                options.update(param.opts)
                options.update(param.secondary_opts)
            elif isinstance(param, click.Argument):
                # Collect argument metavars (e.g. "MY_ARG") as a distinct
                # category from option metavars.
                kw.arguments.add(param.make_metavar(ctx=ctx))

            # Only Choice and DateTime types produce their own structured
            # metavar (with delimiters like brackets and pipes). All other
            # types fall back to a plain uppercased name (e.g. TEXT, INTEGER).
            if isinstance(param.type, (click.Choice, ThemeChoice)):
                _HelpColorsMixin._collect_choice_keywords(param, ctx, kw)
            elif isinstance(param.type, click.DateTime):
                # Highlight each datetime format string as a choice.
                kw.choices.update(param.type.formats)
            elif type_choices := getattr(param.type, "choices", None):
                # Duck-typed choice-like ``click.ParamType`` (e.g.
                # :class:`click_extra.types.MultiChoice` and its subclasses):
                # each accepted value is worth highlighting individually, and
                # the rendered ``[a,b,c]`` metavar protects the brackets +
                # separators from later passes. ``click.Choice`` subclasses are
                # already handled by the branch above.
                kw.choices.update(type_choices)
                kw.choice_metavars.add(param.make_metavar(ctx=ctx))
            elif not isinstance(param, click.Argument):
                # Argument metavars are collected in the arguments set.
                kw.metavars.add(param.make_metavar(ctx=ctx))

            # A user-provided metavar (e.g. ``metavar="LEVEL"``) is always
            # worth highlighting, even for Choice/DateTime types.
            if param.metavar and not isinstance(param, click.Argument):
                kw.metavars.add(param.metavar)

            if param.envvar:
                if isinstance(param.envvar, str):
                    kw.envvars.add(param.envvar)
                else:
                    kw.envvars.update(param.envvar)

            if isinstance(param, click.Option):
                default_string = param.get_help_extra(ctx).get("default")
                if default_string:
                    kw.defaults.add(default_string)

    def get_help(self, ctx: click.Context) -> str:
        """Replace default formatter by our own."""
        ctx.formatter_class = HelpFormatter
        return super().get_help(ctx)  # type: ignore[no-any-return,misc]

    @staticmethod
    def _collect_excluded_keywords(ctx: click.Context) -> HelpKeywords | None:
        """Merge ``excluded_keywords`` from the current command and all ancestors.

        Mirrors the parent-context traversal that collects parent choices in
        :meth:`collect_keywords`. Returns a fresh :class:`HelpKeywords` so that
        no command's original ``excluded_keywords`` is mutated.
        """
        excluded: HelpKeywords | None = None
        cmd_ctx: click.Context | None = ctx
        while cmd_ctx:
            cmd_excluded = getattr(cmd_ctx.command, "excluded_keywords", None)
            if cmd_excluded is not None:
                if excluded is None:
                    excluded = HelpKeywords()
                excluded.merge(cmd_excluded)
            cmd_ctx = cmd_ctx.parent
        return excluded

    def format_help(self, ctx: click.Context, formatter: HelpFormatter) -> None:
        """Feed our custom formatter instance with the keywords to highlight."""
        formatter.keywords = self.collect_keywords(ctx)
        formatter.excluded_keywords = self._collect_excluded_keywords(ctx)
        super().format_help(ctx, formatter)  # type: ignore[misc]


@lru_cache(maxsize=512)
def _escape_for_help_screen(text: str) -> str:
    """Prepares a string to be used in a regular expression for matches in help screen.

    Applies `re.escape <https://docs.python.org/3/library/re.html#re.escape>`_, then
    accounts for long strings being wrapped on multiple lines and padded with spaces to
    fit the columnar layout.

    It allows for:

    - additional number of optional blank characters (line-returns, spaces, tabs, ...)
      after a dash, as the help renderer is free to wrap strings after a dash.
    - a space to be replaced by any number of blank characters.
    """
    return re.escape(text).replace("-", "-\\s*").replace("\\ ", "\\s+")


class HelpFormatter(cloup.HelpFormatter):
    """Extends Cloup's custom HelpFormatter to highlights options, choices, metavars and
    default values.

    This is being discussed for upstream integration at:

    - https://github.com/janluke/cloup/issues/97
    - https://github.com/click-contrib/click-help-colors/issues/17
    - https://github.com/janluke/cloup/issues/95
    """

    theme: HelpTheme

    def __init__(self, *args, **kwargs) -> None:
        """Forces theme to the active one for the current Click context.

        Also transform Cloup's standard ``HelpTheme`` to our own ``HelpTheme``.

        Resolves the active theme via :func:`click_extra.theme.get_current_theme`,
        which reads the per-invocation pick from the Click context (set by
        :class:`~click_extra.theme.ThemeOption`) and falls back to the module-level
        default when no context is active.
        """
        active_theme = _theme.get_current_theme()
        theme = kwargs.get("theme", active_theme)
        if not isinstance(theme, HelpTheme):
            theme = active_theme.with_(**theme._asdict())
        kwargs["theme"] = theme
        super().__init__(*args, **kwargs)

    def write_usage(
        self,
        prog: str,
        args: str = "",
        prefix: str | None = None,
    ) -> None:
        """ANSI-aware override of :meth:`cloup.HelpFormatter.write_usage`.

        On Click ``8.3.x``, :func:`click.formatting.wrap_text` measures line length
        with raw :func:`len`, counting every byte of the ANSI escape sequences
        embedded in ``initial_indent`` (the styled ``Usage:`` heading +
        invoked-command name). With 24-bit RGB themes (e.g. Solarized Dark,
        Dracula, Nord, Monokai), each styled token carries 17+ extra
        bytes of escape, which inflates the measured line beyond the width
        budget and causes premature wraps mid-token: ``[OPTIONS\\n  ]``.

        Cloup styles ``prefix`` and ``prog`` then delegates to click's
        :meth:`HelpFormatter.write_usage`, inheriting the bug. This
        override re-applies the same styling, then bypasses ``wrap_text``
        whenever the visible content fits on a single line: the common case
        for short usage strings where wrapping is unnecessary. Lines that
        genuinely overflow the visible width fall back to click's
        implementation: the wrap point may still be sub-optimal but the
        output stays syntactically valid.

        .. note::
            Click ``8.4.0`` (PR `pallets/click#3420
            <https://github.com/pallets/click/pull/3420>`_) made
            :class:`click.formatting.TextWrapper` ANSI-aware by counting
            visible width instead of raw bytes, so this override is a no-op
            fast path on Click ``>= 8.4.0`` and only fixes wrapping on the
            Click ``8.3.x`` releases click-extra still supports.

        .. todo:: Drop this override once the minimum supported Click rises to
            ``8.4.0`` (which includes ``pallets/click#3420``). The
            ``term_len``-based visible-width check below becomes redundant
            once Click's own wrapper counts visible width.
        """
        if prefix is None:
            prefix = "Usage:"
        styled_prefix = self.theme.heading(prefix) + " "
        styled_prog = self.theme.invoked_command(prog)

        usage_prefix = f"{styled_prefix:>{self.current_indent}}{styled_prog} "
        text_width = self.width - self.current_indent
        visible_width = term_len(usage_prefix) + term_len(args)

        if visible_width <= text_width:
            # Fits on one visible line: skip click's wrap_text, which would
            # count the ANSI escape bytes toward line length and split
            # mid-token for 24-bit RGB themes.
            self.write(f"{usage_prefix}{args}\n")
            return

        # Visibly too wide for one line. Fall back to click's parent
        # implementation for multi-line wrapping. Bypass cloup's wrapper to
        # avoid double-styling ``prefix`` and ``prog``.
        click.formatting.HelpFormatter.write_usage(
            self,
            styled_prog,
            args,
            styled_prefix,
        )

    keywords: HelpKeywords = HelpKeywords()
    excluded_keywords: HelpKeywords | None = None

    #: Matches range expressions like ``0<=x<=9``, ``x>=1024``, ``0<=x<100``.
    _range_re: ClassVar[re.Pattern] = re.compile(r"(?:\S+(?:<|<=))?x(?:<|<=|>|>=)\S+")
    _bracket_re: ClassVar[re.Pattern] = re.compile(
        r"(  )"  # 2 spaces (column or description spacing).
        r"\["  # Opening bracket.
        r"("  # Capture the bracket content.
        r"(?:env\s+var:|default:|required"  # Must start with a recognized label
        r"|(?:\S+(?:<|<=))?x(?:<|<=|>|>=)\S+)"  # or a range expression.
        r"[^\]]*"  # Followed by any non-] characters.
        r")"
        r"\]",  # Closing bracket.
        re.DOTALL,
    )
    _sep_re: ClassVar[re.Pattern] = re.compile(r";\s+")
    _envvar_re: ClassVar[re.Pattern] = re.compile(r"(env\s+var:\s+)(.*)", re.DOTALL)
    _default_re: ClassVar[re.Pattern] = re.compile(r"(default:\s+)(.*)", re.DOTALL)

    #: Matches ``(DEPRECATED)`` and ``(DEPRECATED: reason)`` markers, regardless
    #: of casing. The canonical upstream format is produced by Click's shared
    #: ``_format_deprecated_label`` helper; the case-insensitive flag also
    #: catches manually-written variants in custom help strings.
    _deprecated_re: ClassVar[re.Pattern] = re.compile(
        r"\(deprecated(?::\s[^)]+)?\)",
        re.IGNORECASE,
    )

    def _bracket_or(self, slot_name: str) -> IStyle:
        """Return ``theme.<slot_name>`` or fall back to ``theme.bracket``.

        When a theme leaves an inner bracket-field slot (``envvar``,
        ``default``, ``required``, ``range_label``) at
        :func:`identity <cloup._util.identity>`, value tokens inside the
        bracket block default to the ``bracket`` styling rather than
        rendering plain. This lets a theme set only ``bracket`` and get a
        uniformly dim bracket field for free; richer themes layer specific
        styles on top by setting the inner slots.
        """
        slot: IStyle = getattr(self.theme, slot_name)
        if slot is identity:
            return self.theme.bracket
        return slot

    def _style_bracket_fields(self, match: re.Match) -> str:
        """Style a trailing ``[env var: ...; default: ...; ...]`` block.

        Parses the bracket content by splitting on ``;`` separators and
        matching each field by its label prefix. Applied post-wrapping because
        Click's text wrapper splits lines after ``get_help_record()`` returns,
        which would break pre-styled ANSI codes.

        Inner-slot fallback: when a theme leaves ``envvar`` / ``default`` /
        ``required`` / ``range_label`` at :func:`identity <cloup._util.identity>`,
        the value token inherits the ``bracket`` styling via
        :py:meth:`_bracket_or`. The bracket slot acts as the structural
        default for the whole field; the other four slots override
        piecemeal.
        """
        prefix = match.group(1)
        content = match.group(2)

        # Split on semicolons, keeping the separators.
        parts = re.split(r"(;\s+)", content)

        styled: list[str] = []
        for part in parts:
            # Separator between fields.
            if self._sep_re.fullmatch(part):
                styled.append(self.theme.bracket(part))
            # Environment variable field.
            elif m := self._envvar_re.match(part):
                styled.append(
                    self.theme.bracket(m.group(1))
                    + self._bracket_or("envvar")(m.group(2))
                )
            # Default value field.
            elif m := self._default_re.match(part):
                styled.append(
                    self.theme.bracket(m.group(1))
                    + self._bracket_or("default")(m.group(2))
                )
            # Required label.
            elif part == "required":
                styled.append(self._bracket_or("required")(part))
            # Range expression.
            elif self._range_re.fullmatch(part):
                styled.append(self._bracket_or("range_label")(part))
            # Fallback: style as generic bracket content.
            else:
                styled.append(self.theme.bracket(part))

        return (  # type: ignore[no-any-return]
            prefix + self.theme.bracket("[") + "".join(styled) + self.theme.bracket("]")
        )

    def _style_choice_metavar(self, metavar: str, choices: set[str]) -> str | None:
        """Style individual choices inside a choice metavar string.

        Takes a rendered metavar like ``[json|xml|csv]`` (Click ``Choice``-style)
        or ``[id,spec,value]`` (Click Extra ``MultiChoice``-style) and returns a
        styled version where each known choice is wrapped with
        ``theme.choice``. Returns ``None`` if ``metavar`` does not look like a
        choice list.
        """
        # Strip the surrounding brackets.
        if not (metavar.startswith("[") and metavar.endswith("]")):
            return None
        inner = metavar[1:-1]
        # Detect the separator from the metavar itself: pipe for pick-one
        # ``click.Choice``, comma for multi-pick ``MultiChoice``.
        sep = "|" if "|" in inner else ","
        parts = inner.split(sep)
        styled_parts = [
            self.theme.choice(part) if part in choices else part for part in parts
        ]
        return "[" + sep.join(styled_parts) + "]"

    @staticmethod
    def _add_placeholder(styled: str, store: dict[str, str]) -> str:
        """Register a styled fragment as a null-byte placeholder.

        Returns the placeholder key. Used to protect already-styled regions
        from subsequent regex passes.
        """
        key = f"\x00B{len(store)}\x00"
        store[key] = styled
        return key

    def highlight_extra_keywords(self, help_text: str) -> str:
        """Highlight extra keywords in help screens based on the theme.

        Uses the ``highlight()`` function for all keyword categories. Each
        category is processed as a batch of regex patterns with a single styling
        function, which handles overlapping matches and prevents double-styling.
        """
        kw = self.keywords

        # Highlight deprecated messages. Uses a case-insensitive regex to catch
        # both Click-native "(DEPRECATED)" markers and manually-added variants
        # like "(Deprecated)" in help strings.
        help_text = highlight(help_text, [self._deprecated_re], self.theme.deprecated)

        # Highlight subcommand names. Requires 2-space indentation as a
        # leading boundary.
        if kw.subcommands:
            help_text = highlight(
                help_text,
                (
                    re.compile(rf"(?<=  ){re.escape(name)}(?=\s)")
                    for name in sorted(kw.subcommands, key=len, reverse=True)
                ),
                self.theme.subcommand,
            )

        # Highlight command aliases inside parenthetical groups like
        # "(lock, freeze, snapshot)". Aliases are preceded by "(" or ", "
        # and followed by "," or ")".
        if kw.command_aliases:
            help_text = highlight(
                help_text,
                (
                    re.compile(rf"(?<=[(, ]){re.escape(name)}(?=[,)])")
                    for name in sorted(kw.command_aliases, key=len, reverse=True)
                ),
                self.theme.subcommand,
            )

        # Style trailing bracket fields [env var: ...; default: ...; ...].
        # This must happen post-wrapping because Click's text wrapper splits
        # lines after get_help_record() returns, which would break pre-styled
        # ANSI codes.
        #
        # To prevent cross-reference highlighting from restyling keywords that
        # appear inside bracket field content (e.g. a choice value like
        # "outline" within a default value "rounded-outline"), we replace each
        # styled bracket field with a null-byte placeholder, run all cross-ref
        # passes on the placeholder text, then restore the styled fields.
        bracket_placeholders: dict[str, str] = {}

        def _bracket_to_placeholder(match: re.Match) -> str:
            return self._add_placeholder(
                self._style_bracket_fields(match), bracket_placeholders
            )

        help_text = self._bracket_re.sub(_bracket_to_placeholder, help_text)

        # Style and placeholder choice metavars (e.g. ``[json|xml|csv]``)
        # before applying excluded_keywords and running cross-ref passes.
        # This ensures that choices excluded from cross-ref highlighting
        # (like "version") are still highlighted inside their own metavar.
        for metavar_str in kw.choice_metavars:
            styled = self._style_choice_metavar(metavar_str, kw.choices)
            if styled is None:
                continue
            pattern = re.compile(_escape_for_help_screen(metavar_str))
            help_text = pattern.sub(
                lambda m, s=styled: self._add_placeholder(s, bracket_placeholders),  # type: ignore[misc]
                help_text,
            )

        # Apply excluded_keywords after metavar placeholdering so that
        # exclusions only affect the cross-ref passes below.
        if self.excluded_keywords is not None:
            kw.subtract(self.excluded_keywords)

        # The remaining passes search free-form text (descriptions, docstrings)
        # for option names, choices, arguments, metavars and CLI names.
        # Cross-reference highlighting can be disabled via the theme to avoid
        # over-interpretation in help text that references external identifiers.
        if self.theme.cross_ref_highlight:
            # Highlight CLI names and commands.
            if kw.cli_names:
                help_text = highlight(
                    help_text,
                    (
                        re.compile(rf"(?<=\s){re.escape(name)}(?=\s)")
                        for name in sorted(kw.cli_names, key=len, reverse=True)
                    ),
                    self.theme.invoked_command,
                )

            # Highlight options (long and short combined). Per-keyword lookbehind
            # excludes the option's own leading symbol to prevent matching repeated
            # prefixes (e.g. "---debug" should not match "--debug").
            all_options = sorted(
                kw.long_options | kw.short_options, key=len, reverse=True
            )
            if all_options:
                help_text = highlight(
                    help_text,
                    (
                        re.compile(
                            rf"(?<=[^\w{re.escape(kw[0])}])"
                            rf"{_escape_for_help_screen(kw)}"
                            rf"(?=[^\w\-])"
                        )
                        for kw in all_options
                    ),
                    self.theme.option,
                )

            # Highlight other keywords, which are expected to be separated by
            # any character but word characters.
            for keywords, style_func in (
                # Arguments before metavars: argument names like MY_ARG are a
                # subset of metavars, so highlighting them first with a distinct
                # style takes priority.
                (kw.arguments, self.theme.argument),
                # Choices are already featured in metavars, so we process them
                # before metavars to avoid double-highlighting.
                (kw.choices, self.theme.choice),
                (kw.metavars, self.theme.metavar),
            ):
                if keywords:
                    # Transform keywords into regex patterns.
                    patterns = (
                        # Negative lookbehind rejects matches preceded by:
                        # - a word character (\w),
                        # - a dot: "pyproject.toml" (\.),
                        # - a hyphen: "rounded-outline" (\-),
                        # - a slash: "https://github.com" (\/),
                        # - an exclamation mark: "[!WARNING]" (!),
                        # - an ANSI escape: already-styled text (\x1b).
                        # Negative lookahead rejects matches followed by:
                        # - a word character (\w),
                        # - a hyphen: "github-actions" (\-).
                        re.compile(
                            rf"(?<![\w\.\x1b\-/!])"
                            rf"{_escape_for_help_screen(keyword)}"
                            rf"(?![\w\-])"
                        )
                        for keyword in sorted(keywords, reverse=True)
                    )
                    help_text = highlight(
                        content=help_text,
                        patterns=patterns,
                        styling_func=style_func,
                    )

        # Restore styled bracket fields.
        for key, styled in bracket_placeholders.items():
            help_text = help_text.replace(key, styled)

        return help_text

    def getvalue(self) -> str:
        """Wrap original `Click.HelpFormatter.getvalue()` to force extra-colorization on
        rendering."""
        help_text = super().getvalue()
        return self.highlight_extra_keywords(help_text)


def highlight(
    content: str,
    patterns: Iterable[str | re.Pattern] | str | re.Pattern,
    styling_func: Callable,
    ignore_case: bool = False,
) -> str:
    """Highlights parts of the ``content`` that matches ``patterns``.

    Takes care of overlapping parts within the ``content``, so that the styling function
    is applied only once to each contiguous range of matching characters.

    .. todo::
        Support case-foldeing, so we can have the ``Straße`` string matching the
        ``Strasse`` content.

        This could be tricky as it messes with string length and characters index, which
        our logic relies on.

        .. danger::
            Roundtrip through lower-casing/upper-casing is a can of worms, because some
            characters change length when their case is changed:

            - `Unicode roundtrip-unsafe characters
              <https://gist.github.com/rendello/4d8266b7c52bf0e98eab2073b38829d9>`_
            - `Unicode codepoints expanding or contracting on case changes
              <https://gist.github.com/rendello/d37552507a389656e248f3255a618127>`_
    """
    # Normalize input to a set of patterns.
    if isinstance(patterns, (str, re.Pattern)):
        pattern_list = {patterns}
    else:
        pattern_list = set(patterns)

    # Set of character indices flagged for highlighting.
    matched_indices: set[int] = set()

    # Normalize patterns into regular expressions and find matches.
    for pattern in pattern_list:
        # Pattern is already a compiled regex.
        if isinstance(pattern, re.Pattern):
            regex = pattern
        # Treat as literal string and escape for regex.
        elif isinstance(pattern, str):
            regex = re.compile(re.escape(pattern), re.IGNORECASE if ignore_case else 0)
        else:
            raise TypeError(f"Unsupported pattern type: {pattern!r}")

        # Force IGNORECASE flag if not already compiled with it.
        if ignore_case and not (regex.flags & re.IGNORECASE):
            regex = re.compile(regex.pattern, regex.flags | re.IGNORECASE)

        # Find all matches, including overlapping ones. Because re.search()
        # returns only the first match, we skip ahead one character past the
        # start of each match to find overlapping occurrences.
        start_pos = 0
        while start_pos < len(content):
            match = regex.search(content, start_pos)
            if not match:
                break

            start_idx = match.start()
            end_idx = match.end()

            # Skip zero-length matches (e.g. from pure lookbehind/lookahead).
            if start_idx >= end_idx:
                start_pos = start_idx + 1
                continue

            matched_indices.update(range(start_idx, end_idx))
            start_pos = start_idx + 1

    if not matched_indices:
        return content

    # Build the styled string in one pass: contiguous runs of matched or
    # unmatched characters are grouped, and only matched runs are styled.
    parts: list[str] = []
    in_match = 0 in matched_indices
    run_start = 0

    for i in range(1, len(content) + 1):
        current_in_match = i in matched_indices if i < len(content) else not in_match
        if current_in_match != in_match:
            segment = content[run_start:i]
            parts.append(styling_func(segment) if in_match else segment)
            run_start = i
            in_match = current_in_match

    # Flush the last run.
    if run_start < len(content):
        segment = content[run_start:]
        parts.append(styling_func(segment) if in_match else segment)

    return "".join(parts)
