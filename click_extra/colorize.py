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

import dataclasses
import os
import re
from configparser import RawConfigParser
from dataclasses import dataclass
from enum import Enum
from functools import cache
from gettext import gettext as _
from itertools import chain
from operator import getitem

import click
import cloup
from boltons.strutils import complement_int_list, int_ranges_from_int_list
from cloup._util import identity
from cloup.styling import Color

from . import ParameterSource, Style
from .parameters import ExtraOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from typing import ClassVar

    from cloup.styling import IStyle


@dataclass(frozen=True)
class HelpExtraTheme(cloup.HelpTheme):
    """Extends ``cloup.HelpTheme`` with ``logging.levels`` and extra properties."""

    critical: IStyle = identity
    error: IStyle = identity
    warning: IStyle = identity
    info: IStyle = identity
    debug: IStyle = identity
    """Log levels from Python's logging module."""

    option: IStyle = identity
    subcommand: IStyle = identity
    choice: IStyle = identity
    metavar: IStyle = identity
    bracket: IStyle = identity
    envvar: IStyle = identity
    default: IStyle = identity
    range_label: IStyle = identity
    required: IStyle = identity
    argument: IStyle = identity
    deprecated: IStyle = identity
    search: IStyle = identity
    success: IStyle = identity
    """Click Extra new coloring properties."""

    cross_ref_highlight: bool = True
    """Highlight options, choices, arguments, metavars and CLI names in
    free-form text (descriptions, docstrings).

    When ``False``, only structural elements are styled: bracket fields
    (``[default: ...]``, ``[env var: ...]``, ranges, ``[required]``),
    deprecated messages, and subcommand names in definition lists.
    """

    subheading: IStyle = identity
    """Non-canonical Click Extra properties.

    .. note::
        Subheading is used for sub-sections, like `in the help of mail-deduplicate
        <https://github.com/kdeldycke/mail-deduplicate/blob/0764287/mail_deduplicate/deduplicate.py#L445>`_.

    .. todo::
        Maybe this shouldn't be in Click Extra because it is a legacy inheritance from
        one of my other project.
    """

    def with_(  # type: ignore[override]
        self,
        **kwargs: dict[str, IStyle | None],
    ) -> HelpExtraTheme:
        """Derives a new theme from the current one, with some styles overridden.

        Returns the same instance if the provided styles are the same as the current.
        """
        # Check for unrecognized arguments.
        unrecognized_args = set(kwargs).difference(self.__dataclass_fields__)
        if unrecognized_args:
            raise TypeError(
                f"Got unexpected keyword argument(s): {', '.join(unrecognized_args)}"
            )

        # List of styles that are different from the base theme.
        new_styles = {
            field_id: new_style
            for field_id, new_style in kwargs.items()
            if new_style != getattr(self, field_id)
        }
        if new_styles:
            return dataclasses.replace(self, **new_styles)  # type: ignore[arg-type]

        # No new styles, return the same instance.
        return self

    @staticmethod
    def dark() -> HelpExtraTheme:
        """A theme assuming a dark terminal background color."""
        return HelpExtraTheme(
            invoked_command=Style(fg=Color.bright_white),
            heading=Style(fg=Color.bright_blue, bold=True, underline=True),
            constraint=Style(fg=Color.magenta),
            # Neutralize Cloup's col1, as it interferes with our finer option styling
            # which takes care of separators.
            col1=identity,
            # Style aliases like options and subcommands.
            alias=Style(fg=Color.cyan),
            # Style aliases punctuation like options, but dimmed.
            alias_secondary=Style(fg=Color.cyan, dim=True),
            ### Log styles.
            critical=Style(fg=Color.red, bold=True),
            error=Style(fg=Color.red),
            warning=Style(fg=Color.yellow),
            info=identity,  # INFO level is the default, so no style applied.
            debug=Style(fg=Color.blue),
            ### Click Extra styles.
            option=Style(fg=Color.cyan),
            # Style subcommands like options and aliases.
            subcommand=Style(fg=Color.cyan),
            choice=Style(fg=Color.magenta),
            metavar=Style(fg=Color.cyan, dim=True),
            bracket=Style(dim=True),
            envvar=Style(fg=Color.yellow, dim=True),
            default=Style(fg=Color.green, dim=True, italic=True),
            range_label=Style(fg=Color.cyan, dim=True),
            required=Style(fg=Color.red, dim=True),
            argument=Style(fg=Color.cyan),
            deprecated=Style(fg=Color.bright_yellow, bold=True),
            search=Style(fg=Color.green, bold=True),
            success=Style(fg=Color.green),
            ### Non-canonical Click Extra styles.
            subheading=Style(fg=Color.blue),
        )

    @staticmethod
    def light() -> HelpExtraTheme:
        """A theme assuming a light terminal background color.

        .. todo::
            Tweak colors to make them more readable.
        """
        return HelpExtraTheme.dark()


default_theme: HelpExtraTheme = HelpExtraTheme.dark()
"""Default color theme for Click Extra."""


nocolor_theme: HelpExtraTheme = HelpExtraTheme()
"""Color theme for Click Extra to force no colors."""


OK = default_theme.success("✓")
KO = default_theme.error("✘")
"""Pre-rendered UI-elements."""

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


class ColorOption(ExtraOption):
    """A pre-configured option that is adding a ``--color``/``--no-color`` (aliased by
    ``--ansi``/``--no-ansi``) to keep or strip colors and ANSI codes from CLI output.

    This option is eager by default to allow for other eager options (like
    ``--version``) to be rendered colorless.

    .. todo::

        Should we switch to ``--color=<auto|never|always>`` `as GNU tools does
        <https://news.ycombinator.com/item?id=36102377>`_?

        Also see `how the isatty property defaults with this option
        <https://news.ycombinator.com/item?id=36100865>`_, and `how it can be
        implemented in Python <https://bixense.com/clicolors/>`_.

    .. todo::

        Support the `TERM environment variable convention
        <https://news.ycombinator.com/item?id=36101712>`_?
    """

    @staticmethod
    def disable_colors(
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Callback disabling all coloring utilities.

        Re-inspect the environment for existence of colorization flags to re-interpret
        the provided value.
        """
        # Collect all colorize flags in environment variables we recognize.
        colorize_from_env = set()
        for var, default in color_envvars.items():
            if var in os.environ:
                # Presence of the variable in the environment without a value encodes
                # for an activation, hence the default to True.
                var_value = os.environ.get(var, "true")
                # `os.environ` is a dict whose all values are strings. Here we normalize
                # these string into booleans. If we can't, we fallback to True, in the
                # same spirit as above.
                var_boolean = RawConfigParser.BOOLEAN_STATES.get(
                    var_value.lower(),
                    True,
                )
                colorize_from_env.add(default ^ (not var_boolean))

        # Re-interpret the provided value against the recognized environment variables.
        if colorize_from_env:
            # The environment can only override the provided value if it comes from
            # the default value or the config file.
            env_takes_precedence = (
                ctx.get_parameter_source("color") == ParameterSource.DEFAULT
            )
            if env_takes_precedence:
                # One env var is enough to activate colorization.
                value = True in colorize_from_env

        # Set the official context color flag. This is used by Click's
        # ``resolve_color_default()`` → ``should_strip_ansi()`` chain in ``echo()``.
        ctx.color = value

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=True,
        default=True,
        is_eager=True,
        expose_value=False,
        help=_("Strip out all colors and all ANSI codes from output."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--color/--no-color", "--ansi/--no-ansi")

        kwargs.setdefault("callback", self.disable_colors)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )


class ExtraHelpColorsMixin:  # (Command)??
    """Adds extra-keywords highlighting to Click commands.

    This mixin for ``click.Command``-like classes intercepts the top-level helper-
    generation method to initialize the formatter with dynamic settings. This is
    implemented at this stage so we have access to the global context.
    """

    def _collect_keywords(
        self,
        ctx: click.Context,
    ) -> tuple[
        set[str],
        set[str],
        set[str],
        set[str],
        set[str],
        set[str],
        set[str],
        set[str],
        set[str],
        set[str],
        set[str],
    ]:
        """Parse click context to collect option names, choices and metavar keywords.

        This is Click Extra-specific and is not part of the upstream ``click.Command``
        API.
        """
        cli_names: set[str] = set()
        subcommands: set[click.Command] = set()
        subcommand_ids: set[str] = set()
        command_aliases: set[str] = set()
        arguments: set[str] = set()
        options: set[str] = set()
        long_options: set[str] = set()
        short_options: set[str] = set()
        choices: set[str] = set()
        metavars: set[str] = set()
        envvars: set[str] = set()
        defaults: set[str] = set()
        deprecated_messages: set[str] = set()

        # Includes the full command path and each ancestor name, so that
        # individual components are highlighted even when interleaved with
        # options (e.g. "repomatic --table-format github sync-uv-lock").
        if ctx.command_path:
            cli_names.add(ctx.command_path)
        ancestor: click.Context | None = ctx
        while ancestor:
            if ancestor.info_name:
                cli_names.add(ancestor.info_name)
            ancestor = ancestor.parent
        command = ctx.command

        # Will fetch command's metavar (i.e. the "[OPTIONS]" after the CLI name in
        # "Usage:") and dig into subcommands to get subcommand_metavar:
        # ("COMMAND1 [ARGS]... [COMMAND2 [ARGS]...]...").
        metavars.update(command.collect_usage_pieces(ctx))

        # Get subcommands and their aliases.
        if isinstance(command, click.Group):
            # Process all subcommands, in the order they are listed, to have a stable
            # and predictable loading order. Which is important on lazy-loading.
            for sub_id in command.list_commands(ctx):
                subcommand = command.get_command(ctx, sub_id)
                if not subcommand:
                    raise RuntimeError(f"Subcommand {sub_id!r} not found.")
                subcommand_ids.add(sub_id)
                command_aliases.update(getattr(subcommand, "aliases", []))
                # Keep reference to subcommand object for later processing.
                subcommands.add(subcommand)

        # Add user defined help options.
        options.update(ctx.help_option_names)

        # Collect all options, choices, metavars, envvars and default values.
        for param in command.get_params(ctx):
            # Ignore hidden options that are not meant to be displayed in help screens.
            if isinstance(param, click.Option) and param.hidden:
                continue

            # Only collect option names from actual Option parameters, not from
            # Arguments. An Argument's opts contains the bare parameter name
            # (e.g. "keys") which would pollute the option keywords and interfere
            # with highlighting of real options like "--list-keys".
            if isinstance(param, click.Option):
                options.update(param.opts)
                options.update(param.secondary_opts)
            elif isinstance(param, click.Argument):
                # Collect argument metavars (e.g. "MY_ARG") as a distinct
                # category from option metavars. The uppercased name is used
                # in the Usage line and the positional arguments section.
                arguments.add(param.make_metavar(ctx=ctx))

            # Only Choice and DateTime types produce their own structured
            # metavar (with delimiters like brackets and pipes). All other
            # types fall back to a plain uppercased name (e.g. TEXT, INTEGER).
            if isinstance(param.type, click.Choice):
                # Use normalize_choice() to get the exact strings that appear
                # in the metavar. This handles Enum member names, case-folding
                # from case_sensitive=False, and EnumChoice's ChoiceSource.
                choices.update(
                    param.type.normalize_choice(c, ctx)
                    for c in param.type.choices
                )
            elif isinstance(param.type, click.DateTime):
                # Highlight each datetime format string as a choice.
                choices.update(param.type.formats)
            elif not isinstance(param, click.Argument):
                # Argument metavars are collected separately in the
                # ``arguments`` set with their own style.
                metavars.add(param.make_metavar(ctx=ctx))

            # A user-provided metavar (e.g. ``metavar="LEVEL"``) is always
            # a plain token worth highlighting, even for Choice/DateTime.
            # For arguments, this is already covered by the arguments set.
            if param.metavar and not isinstance(param, click.Argument):
                metavars.add(param.metavar)

            if param.envvar:
                if isinstance(param.envvar, str):
                    envvars.add(param.envvar)
                else:
                    envvars.update(param.envvar)

            if isinstance(param, click.Option):
                default_string = param.get_help_extra(ctx).get("default")
                if default_string:
                    defaults.add(default_string)

        # Collect option names and choices from parent groups. Subcommand
        # docstrings often reference parent options in usage examples (e.g.
        # "myapp --table-format github sub").
        parent_ctx = ctx.parent
        while parent_ctx:
            for param in parent_ctx.command.get_params(parent_ctx):
                if isinstance(param, click.Option) and not param.hidden:
                    options.update(param.opts)
                    options.update(param.secondary_opts)
                    if isinstance(param.type, click.Choice):
                        choices.update(
                            param.type.normalize_choice(c, parent_ctx)
                            for c in param.type.choices
                        )
            parent_ctx = parent_ctx.parent

        # Split between shorts and long options
        for option_name in options:
            # Short options are no longer than 2 characters like "-D", "/d", "/?",
            # "+w", "-w", "f_", "_f", ...
            # XXX We cannot reuse the _short_opts and _long_opts attributes from
            # https://github.com/pallets/click/blob/b0538df/src/click/parser.py#L173-L182
            # because their values are not passed when the context is updated like
            # ctx._opt_prefixes is at:
            # https://github.com/pallets/click/blob/b0538df/src/click/core.py#L1408 .
            # So we rely on simple heuristics to guess the option category.
            if len(option_name) <= 2:
                short_options.add(option_name)
            # Any other is considered a long options. Like: "--debug", "--c", "-otest",
            # "---debug", "-vvvv, "++foo", "/debug", "from_", "_from", ...
            else:
                long_options.add(option_name)

        # Collect all deprecated messages on subcommands and parameters.
        for obj in chain(subcommands, command.get_params(ctx)):
            deprecated = getattr(obj, "deprecated", None)
            if deprecated:
                # Generated deprecated message as Click does:
                # https://github.com/pallets/click/blob/c9f7d9d/src/click/core.py#L1061-L1065
                # https://github.com/pallets/click/blob/c9f7d9d/src/click/core.py#L1098-L1102
                # https://github.com/pallets/click/blob/c9f7d9d/src/click/core.py#L2556-L2560
                deprecated_messages.add(
                    f"(DEPRECATED: {deprecated})"
                    if isinstance(deprecated, str)
                    else "(DEPRECATED)"
                )

        return (
            cli_names,
            subcommand_ids,
            command_aliases,
            arguments,
            long_options,
            short_options,
            choices,
            metavars,
            envvars,
            defaults,
            deprecated_messages,
        )

    def get_help(self, ctx: click.Context) -> str:
        """Replace default formatter by our own."""
        ctx.formatter_class = HelpExtraFormatter
        return super().get_help(ctx)  # type: ignore[no-any-return,misc]

    def format_help(self, ctx: click.Context, formatter: HelpExtraFormatter) -> None:
        """Feed our custom formatter instance with the keywords to highlight."""
        (
            formatter.cli_names,
            formatter.subcommands,
            formatter.command_aliases,
            formatter.arguments,
            formatter.long_options,
            formatter.short_options,
            formatter.choices,
            formatter.metavars,
            formatter.envvars,
            formatter.defaults,
            formatter.deprecated_messages,
        ) = self._collect_keywords(ctx)
        super().format_help(ctx, formatter)  # type: ignore[misc]


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


class HelpExtraFormatter(cloup.HelpFormatter):
    """Extends Cloup's custom HelpFormatter to highlights options, choices, metavars and
    default values.

    This is being discussed for upstream integration at:

    - https://github.com/janluke/cloup/issues/97
    - https://github.com/click-contrib/click-help-colors/issues/17
    - https://github.com/janluke/cloup/issues/95
    """

    theme: HelpExtraTheme

    def __init__(self, *args, **kwargs) -> None:
        """Forces theme to our default.

        Also transform Cloup's standard ``HelpTheme`` to our own ``HelpExtraTheme``.
        """
        theme = kwargs.get("theme", default_theme)
        if not isinstance(theme, HelpExtraTheme):
            theme = default_theme.with_(**theme._asdict())
        kwargs["theme"] = theme
        super().__init__(*args, **kwargs)

    # Lists of extra keywords to highlight.
    cli_names: set[str] = set()  # noqa: RUF012
    subcommands: set[str] = set()  # noqa: RUF012
    command_aliases: set[str] = set()  # noqa: RUF012
    arguments: set[str] = set()  # noqa: RUF012
    long_options: set[str] = set()  # noqa: RUF012
    short_options: set[str] = set()  # noqa: RUF012
    choices: set[str] = set()  # noqa: RUF012
    metavars: set[str] = set()  # noqa: RUF012
    envvars: set[str] = set()  # noqa: RUF012
    defaults: set[str] = set()  # noqa: RUF012
    deprecated_messages: set[str] = set()  # noqa: RUF012

    # TODO: Highlight extra keywords <stdout> or <stderr>

    # TODO: add collection of regexps as pre-compiled constants, so we can
    # inspect them and get some performances improvements.


    #: Matches range expressions like ``0<=x<=9``, ``x>=1024``, ``0<=x<100``.
    _range_re = re.compile(
        r"(?:\S+(?:<|<=))?"  # Optional lower bound + operator.
        r"x"  # The variable.
        r"(?:<|<=|>|>=)"  # Any comparison operator.
        r"\S+"  # Upper (or lower) bound value.
    )

    def _style_bracket_fields(self, match: re.Match) -> str:
        """Style a trailing ``[env var: ...; default: ...; ...]`` block.

        Parses the bracket content by splitting on ``;`` separators and
        matching each field by its label prefix. Applied post-wrapping because
        Click's text wrapper splits lines after ``get_help_record()`` returns,
        which would break pre-styled ANSI codes.
        """
        prefix = match.group(1)
        content = match.group(2)

        # Split on semicolons, keeping the separators.
        parts = re.split(r"(;\s+)", content)

        styled = []
        for part in parts:
            # Separator between fields.
            if re.fullmatch(r";\s+", part):
                styled.append(self.theme.bracket(part))
            # Environment variable field.
            elif m := re.match(r"(env\s+var:\s+)(.*)", part, re.DOTALL):
                styled.append(
                    self.theme.bracket(m.group(1)) + self.theme.envvar(m.group(2))
                )
            # Default value field.
            elif m := re.match(r"(default:\s+)(.*)", part, re.DOTALL):
                styled.append(
                    self.theme.bracket(m.group(1)) + self.theme.default(m.group(2))
                )
            # Required label.
            elif part == "required":
                styled.append(self.theme.required(part))
            # Range expression.
            elif self._range_re.fullmatch(part):
                styled.append(self.theme.range_label(part))
            # Fallback: style as generic bracket content.
            else:
                styled.append(self.theme.bracket(part))

        return (  # type: ignore[no-any-return]
            prefix
            + self.theme.bracket("[")
            + "".join(styled)
            + self.theme.bracket("]")
        )

    def highlight_extra_keywords(self, help_text: str) -> str:
        """Highlight extra keywords in help screens based on the theme.

        Uses the ``highlight()`` function for all keyword categories. Each
        category is processed as a batch of regex patterns with a single styling
        function, which handles overlapping matches and prevents double-styling.
        """
        # Highlight deprecated messages.
        if self.deprecated_messages:
            help_text = highlight(
                help_text,
                (
                    re.compile(_escape_for_help_screen(msg))
                    for msg in self.deprecated_messages
                ),
                self.theme.deprecated,
            )

        # Highlight subcommands and their aliases. Both share the subcommand
        # style and require 2-space indentation as a leading boundary.
        all_subcommands = self.subcommands | self.command_aliases
        if all_subcommands:
            help_text = highlight(
                help_text,
                (
                    re.compile(rf"(?<=  ){re.escape(name)}(?=\s)")
                    for name in sorted(all_subcommands, key=len, reverse=True)
                ),
                self.theme.subcommand,
            )

        # Style trailing bracket fields [env var: ...; default: ...; ...].
        # This must happen post-wrapping because Click's text wrapper splits
        # lines after get_help_record() returns, which would break pre-styled
        # ANSI codes.
        help_text = re.sub(
            r"(  )"  # 2 spaces (column or description spacing).
            r"\["  # Opening bracket.
            r"("  # Capture the bracket content.
            r"(?:env\s+var:|default:|required"  # Must contain a recognized label
            r"|(?:\S+(?:<|<=))?x(?:<|<=|>|>=)\S+)"  # or a range expression.
            r"[^\]]*"  # Followed by any non-] characters.
            r")"
            r"\]",  # Closing bracket.
            self._style_bracket_fields,
            help_text,
            flags=re.DOTALL,
        )

        # The remaining passes search free-form text (descriptions, docstrings)
        # for option names, choices, arguments, metavars and CLI names. This
        # cross-reference highlighting can be disabled via the theme to avoid
        # over-interpretation in help text that references external identifiers.
        if not self.theme.cross_ref_highlight:
            return help_text

        # Highlight CLI names and commands.
        if self.cli_names:
            help_text = highlight(
                help_text,
                (
                    re.compile(rf"(?<=\s){re.escape(name)}(?=\s)")
                    for name in sorted(self.cli_names, key=len, reverse=True)
                ),
                self.theme.invoked_command,
            )

        # Highlight options (long and short combined). Per-keyword lookbehind
        # excludes the option's own leading symbol to prevent matching repeated
        # prefixes (e.g. "---debug" should not match "--debug").
        all_options = sorted(
            self.long_options | self.short_options, key=len, reverse=True
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

        # Highlight other keywords, which are expected to be separated by any
        # character but word characters.
        for keywords, style_func in (
            # Arguments before metavars: argument names like MY_ARG are a
            # subset of metavars, so highlighting them first with a distinct
            # style takes priority.
            (self.arguments, self.theme.argument),
            # Choices are already featured in metavars, so we process them
            # before metavars to avoid double-highlighting.
            (self.choices, self.theme.choice),
            (self.metavars, self.theme.metavar),
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

    # Ranges of character indices flagged for highlighting.
    ranges = set()

    # Normalize patterns into regular expression and find matches.
    for pattern in pattern_list:
        # Pattern is already a regex.
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

        # Find all matches including overlapping ones.
        start_pos = 0
        while start_pos < len(content):
            match = regex.search(content, start_pos)
            # No more matches possible with this pattern from this position.
            if not match:
                break

            start_idx = match.start()
            end_idx = match.end() - 1

            # Ensure valid range.
            assert start_idx <= end_idx, "Invalid match range"
            assert 0 <= start_idx < len(content), "Start index out of bounds"
            assert 0 <= end_idx < len(content), "End index out of bounds"
            ranges.add(f"{start_idx}-{end_idx}")

            # Because re.search() is matching the first occurrence only, we can safely
            # skip ahead to the next character just after the start of the current
            # match.
            start_pos = start_idx + 1

    # If no matches found, return original content.
    if not ranges:
        return content

    # Reduce ranges, compute complement ranges, transform them to list of integers.
    range_arg = ",".join(ranges)
    highlight_ranges = int_ranges_from_int_list(range_arg)
    untouched_ranges = int_ranges_from_int_list(
        complement_int_list(range_arg, range_end=len(content))
    )

    # Apply style to range of characters flagged as matching.
    styled_str = ""
    for i, j in sorted(highlight_ranges + untouched_ranges):
        segment = getitem(content, slice(i, j + 1))
        if (i, j) in highlight_ranges:
            segment = styling_func(segment)
        styled_str += str(segment)

    return styled_str
