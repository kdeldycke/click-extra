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
from configparser import RawConfigParser
from gettext import gettext as _
from operator import getitem
from typing import NamedTuple, Sequence, cast, Optional

import regex as re3
from boltons.strutils import complement_int_list, int_ranges_from_int_list
from cloup._util import identity
from cloup.styling import IStyle, Color
from cloup.typing import MISSING, Possibly
import click

from . import (
    Choice,
    Context,
    HelpFormatter,
    Parameter,
    ParameterSource,
    Style,
    echo,
    get_current_context,
    cache,
)
from .parameters import ExtraOption


class HelpExtraTheme(NamedTuple):
    """Extends ``cloup.HelpTheme`` with extra properties and ``logging.levels``.

    .. caution::
        We had to redefined all fields and couldn't extend ``cloup.HelpTheme`` as there
        is no way to cleanly do it with MyPy.

        See:
        - https://github.com/python/typing/issues/427
        - https://mypy.readthedocs.io/en/stable/runtime_troubles.html#future-annotations-import-pep-563
    """

    invoked_command: IStyle = identity
    command_help: IStyle = identity
    heading: IStyle = identity
    constraint: IStyle = identity
    section_help: IStyle = identity
    col1: IStyle = identity
    col2: IStyle = identity
    alias: IStyle = identity
    alias_secondary: Optional[IStyle] = None
    epilog: IStyle = identity
    """Set of properties inherited from ``cloup.HelpTheme``.

    See: https://cloup.readthedocs.io/en/stable/autoapi/cloup/index.html#cloup.HelpTheme.invoked_command
    """

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
    deprecated: IStyle = identity
    search: IStyle = identity
    success: IStyle = identity
    """Click Extra new coloring properties."""

    subheading: IStyle = identity
    """Non-canonical Click Extra properties.

    .. note::
        Subheading is used for sub-sections, like `in the help of mail-deduplicate
        <https://github.com/kdeldycke/mail-deduplicate/blob/0764287/mail_deduplicate/deduplicate.py#L445>`_.

    .. todo::
        Maybe this shouln't be in Click Extra because it is a legacy inheritance from
        one of my other project.
    """

    def with_(
        self,
        ### Cloup properties.
        invoked_command: IStyle | None = None,
        command_help: IStyle | None = None,
        heading: IStyle | None = None,
        constraint: IStyle | None = None,
        section_help: IStyle | None = None,
        col1: IStyle | None = None,
        col2: IStyle | None = None,
        alias: IStyle | None = None,
        alias_secondary: Possibly[Optional[IStyle]] = MISSING,
        epilog: IStyle | None = None,
        ### Log levels.
        critical: IStyle | None = None,
        error: IStyle | None = None,
        warning: IStyle | None = None,
        info: IStyle | None = None,
        debug: IStyle | None = None,
        ### Click Extra properties.
        option: IStyle | None = None,
        subcommand: IStyle | None = None,
        choice: IStyle | None = None,
        metavar: IStyle | None = None,
        bracket: IStyle | None = None,
        envvar: IStyle | None = None,
        default: IStyle | None = None,
        deprecated: IStyle | None = None,
        search: IStyle | None = None,
        success: IStyle | None = None,
        ### Non-canonical Click Extra properties.
        subheading: IStyle | None = None,
    ) -> HelpExtraTheme:
        """Copy of ``cloup.HelpTheme.with_``."""
        kwargs = {key: val for key, val in locals().items() if val is not None}
        kwargs.pop("self")
        if kwargs:
            return self._replace(**kwargs)
        return self

    @staticmethod
    def dark() -> HelpExtraTheme:
        """A theme assuming a dark terminal background color.

        .. todo::

            Implement default dark theme.
        """
        raise NotImplementedError

    @staticmethod
    def light() -> HelpExtraTheme:
        """A theme assuming a light terminal background color.

        .. todo::

            Implement default light theme.
        """
        raise NotImplementedError


# Populate our global theme with all default styles.
default_theme = HelpExtraTheme(
    ### Cloup styles.
    invoked_command=Style(fg=Color.bright_white),
    heading=Style(fg=Color.bright_blue, bold=True, underline=True),
    constraint=Style(fg=Color.magenta),
    # Neutralize Cloup's col1, as it interfers with our finer option styling
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
    deprecated=Style(fg=Color.bright_yellow, bold=True),
    search=Style(fg=Color.green, bold=True),
    success=Style(fg=Color.green),
    ### Non-canonical Click Extra styles.
    subheading=Style(fg=Color.blue),
)


# No color theme.
nocolor_theme = HelpExtraTheme()


OK = default_theme.success("✓")
KO = default_theme.error("✘")
"""Pre-rendered UI-elements."""

color_env_vars = {
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
}
"""List of environment variables recognized as flags to switch color rendering on or
off.

The key is the name of the variable and the boolean value the value to pass to
``--color`` option flag when encountered.

Source: https://github.com/pallets/click/issues/558
"""


class ColorOption(ExtraOption):
    """A pre-configured option that is adding a ``--color``/``--no-color`` (aliased by
    ``--ansi``/``--no-ansi``) option to keep or strip colors and ANSI codes from CLI
    output.

    This option is eager by default to allow for other eager options (like
    ``--version``) to be rendered colorless.
    """

    @staticmethod
    def disable_colors(ctx, param, value):
        """Callback disabling all coloring utilities.

        Re-inspect the environment for existence of colorization flags to re-interpret
        the provided value.
        """
        # Collect all colorize flags in environment variables we recognize.
        colorize_from_env = set()
        for var, default in color_env_vars.items():
            if var in os.environ:
                # Presence of the variable in the environment without a value encodes
                # for an activation, hence the default to True.
                var_value = os.environ.get(var, "true")
                # `os.environ` is a dict whose all values are strings. Here we normalize
                # these string into booleans. If we can't, we fallback to True, in the
                # same spirit as above.
                var_boolean = RawConfigParser.BOOLEAN_STATES.get(
                    var_value.lower(), True
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

        # There is an undocumented color flag in context:
        # https://github.com/pallets/click/blob/65eceb0/src/click/globals.py#L56-L69
        ctx.color = value

        if not value:

            def restore_original_styling():
                """Reset color flag in context."""
                ctx = get_current_context()
                ctx.color = None

            ctx.call_on_close(restore_original_styling)

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


class HelpOption(ExtraOption):
    @staticmethod
    def print_help(ctx: Context, param: Parameter, value: bool) -> None:
        """Prints help text and exits."""
        if not value or ctx.resilient_parsing:
            return

        echo(ctx.get_help(), color=ctx.color)

        # Do not just ctx.exit() as it will prevent callbacks defined on options
        # to be called.
        ctx.close()
        ctx.exit()

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=True,
        expose_value=False,
        is_eager=True,
        help=_("Show this message and exit."),
        **kwargs,
    ):
        if not param_decls:
            param_decls = ("--help", "-h")

        kwargs.setdefault("callback", self.print_help)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )


class ExtraHelpColorsMixin:
    """Adds extra-keywords highlighting to Click commands.

    This mixin for ``click.core.Command``-like classes intercepts the top-level helper-
    generation method to initialize the formatter with dynamic settings.

    This is implemented here to get access to the global context.
    """

    def collect_keywords(self, ctx):
        """Parse click context to collect option names, choices and metavar keywords."""
        cli_names: set[str] = set()
        subcommands: set[str] = set()
        command_aliases: set[str] = set()
        options: set[str] = set()
        long_options: set[str] = set()
        short_options: set[str] = set()
        choices: set[str] = set()
        metavars: set[str] = set()
        envvars: set[str] = set()
        defaults: set[str] = set()

        # Includes CLI base name and its commands.
        cli_names.add(ctx.command_path)
        command = ctx.command

        # Will fetch command's metavar (i.e. the "[OPTIONS]" after the CLI name in
        # "Usage:") and dig into subcommands to get subcommand_metavar:
        # ("COMMAND1 [ARGS]... [COMMAND2 [ARGS]...]...").
        metavars.update(command.collect_usage_pieces(ctx))

        # Get subcommands and their aliases.
        if hasattr(command, "list_commands"):
            subcommands.update(command.list_commands(ctx))
            for sub_id in subcommands:
                sub_cmd = command.get_command(ctx, sub_id)
                command_aliases.update(getattr(sub_cmd, "aliases", []))

        # Add user defined help options.
        options.update(ctx.help_option_names)

        # Collect all options, choices, metavars, envvars and default values.
        for param in command.params:
            options.update(param.opts)
            options.update(param.secondary_opts)

            if isinstance(param.type, Choice):
                choices.update(param.type.choices)

            metavars.add(param.make_metavar())

            envvars.update(param.envvar)

            if isinstance(param, click.Option):
                default_string = ExtraOption.get_help_default(param, ctx)
                if default_string:
                    defaults.add(default_string)

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

        return (
            cli_names,
            subcommands,
            command_aliases,
            long_options,
            short_options,
            choices,
            metavars,
            envvars,
            defaults,
        )

    def get_help(self, ctx):
        """Replace default formatter by our own."""
        ctx.formatter_class = HelpExtraFormatter
        return super().get_help(ctx)

    def format_help(self, ctx, formatter):
        """Feed our custom formatter instance with the keywords to highlight."""
        (
            formatter.cli_names,
            formatter.subcommands,
            formatter.command_aliases,
            formatter.long_options,
            formatter.short_options,
            formatter.choices,
            formatter.metavars,
            formatter.envvars,
            formatter.defaults,
        ) = self.collect_keywords(ctx)
        return super().format_help(ctx, formatter)


def escape_for_help_sceen(text: str) -> str:
    """Escape a text to be used in a regural expression to match help screen.

    Like ``re.escape``, but allows any number of optional blank characters (line
    returns, spaces, tabs) after a dash, to accounts for text wrapping rules and
    columnar layout.
    """
    return re.escape(text).replace("-", "-\\s*")


class HelpExtraFormatter(HelpFormatter):
    """Extends Cloup's custom HelpFormatter to highlights options, choices, metavars and
    default values.

    This is being discussed for upstream integration at:

    - https://github.com/janluke/cloup/issues/97
    - https://github.com/click-contrib/click-help-colors/issues/17
    - https://github.com/janluke/cloup/issues/95
    """

    theme: HelpExtraTheme

    def __init__(self, *args, **kwargs):
        """Forces theme to our default.

        Also transform Cloup's standard ``HelpTheme`` to our own ``HelpExtraTheme``.
        """
        theme = kwargs.get("theme", default_theme)
        if not isinstance(theme, HelpExtraTheme):
            theme = default_theme.with_(**theme._asdict())
        kwargs["theme"] = theme
        super().__init__(*args, **kwargs)

    # Lists of extra keywords to highlight.
    cli_names: set[str] = set()
    subcommands: set[str] = set()
    command_aliases: set[str] = set()
    long_options: set[str] = set()
    short_options: set[str] = set()
    choices: set[str] = set()
    metavars: set[str] = set()
    envvars: set[str] = set()
    defaults: set[str] = set()

    # TODO: Hihglight extra keywords <stdout> or <stderr>

    # TODO: add collection of regexps as pre-compiled constants, so we can
    # inspect them and get some performances improvements.

    style_aliases = {
        # Layout elements of the square brackets trailing each option.
        "bracket_1": "bracket",
        "bracket_2": "bracket",
        "label_sep": "bracket",
        "envvar_label": "bracket",
        "default_label": "bracket",
        # Long and short options are options.
        "long_option": "option",
        "short_option": "option",
    }
    """Map regex's group IDs to styles.

    Most of the time, the style name is the same as the group ID. But some regular
    expression implementations requires us to work around group IDs limitations, like
    ``bracket_1`` and ``bracket_2``. In which case we use this mapping to apply back
    the canonical style to that regex-specific group ID.
    """

    @cache
    def get_style_id(self, group_id: str) -> str:
        """Get the style ID to apply to a group.

        Return the style which has the same ID as the group, unless it is defined in
        the ``style_aliases`` mapping above.
        """
        return self.style_aliases.get(group_id, group_id)

    @cache
    def colorize_group(self, str_to_style: str, group_id: str) -> str:
        """Colorize a string according to the style of the group ID."""
        style = cast("IStyle", getattr(self.theme, self.get_style_id(group_id)))
        return style(str_to_style)

    def colorize(self, match: re.Match) -> str:
        """Colorize all groups with IDs in the provided matching result.

        All groups without IDs are left as-is.

        All groups are proccessed in the order they appear in the ``match`` object.
        Then all groups are concatenated to form the final string that is returned.

        .. caution::
            Implementation is a bit funky here because there is no way to iterate over
            both unnamed and named groups, in the order they appear in the regex, while
            keeping track of the group ID.

            So we have to iterate over the list of matching strings and pick up the
            corresponding group ID along the way, from the ``match.groupdict()``
            dictionnary. This also means we assume that the ``match.groupdict()`` is
            returning an ordered dictionnary. Which is supposed to be true as of Python
            3.7.
        """
        # Get a snapshot of all named groups.
        named_matches = list(match.groupdict().items())

        txt = ""
        # Iterate over all groups, named or not.
        for group_string in match.groups():
            # Is the next available named group is matching current group string?
            if named_matches and group_string == named_matches[0][1]:
                # We just found a named group. Consume it from the list of named groups
                # to prevent it from being processed twice.
                group_id, group_string = named_matches.pop(0)
                if group_string is not None:
                    # Colorize the group with a style matching its ID.
                    txt += self.colorize_group(group_string, group_id)
            else:
                # No named group matching this string. Leave it as-is.
                txt += group_string

        # Double-check we processed all named groups.
        if len(named_matches) != 0:
            raise ValueError(
                "The matching result contains named groups that were not processed. "
                "There is an edge-case in the design of regular expressions."
            )

        return txt

    def highlight_extra_keywords(self, help_text):
        """Highlight extra keywords in help screens based on the theme.

        It is based on regular expressions. While this is not a bullet-proof method, it
        is good enough. After all, help screens are not consumed by machine but are
        designed for humans.

        .. danger::
            All the regular expressions below are designed to match its original string
            into a sequence of contiguous groups.

            This means each part of the matching result must be encapsulated in a group.
            And subgroups are not allowed (unless their are explicitly set as
            non-matching with ``(?:...)`` prefix).

            Groups with a name must have a corresponding style.
        """
        # Highlight " (Deprecated)" label, as set by either Click or Cloup:
        # https://github.com/pallets/click/blob/8.0.0rc1/tests/test_commands.py#L322
        # https://github.com/janluke/cloup/blob/v2.1.0/cloup/formatting/_formatter.py#L190
        help_text = re.sub(
            rf"""
            (\s)                                         # Any blank char.
            (?P<deprecated>{re.escape("(Deprecated)")})  # The flag string.
            """,
            self.colorize,
            help_text,
            flags=re.VERBOSE,
        )

        # Highligh subcommands.
        for subcommand in self.subcommands:
            help_text = re.sub(
                rf"""
                (\ \ )                        # 2 spaces (i.e. section indention).
                (?P<subcommand>{re.escape(subcommand)})
                (\s)                          # Any blank char.
                """,
                self.colorize,
                help_text,
                flags=re.VERBOSE,
            )

        # Highligh environment variables and defaults in trailing square brackets.
        help_text = re.sub(
            r"""
            (\ \ )                  # 2 spaces (column spacing or description spacing).
            (?P<bracket_1>\[)                  # Square brackets opening.

            (?:                         # Non-capturing group.
                (?P<envvar_label>
                    env\s+var:            # Starting content within the brackets.
                    \s+                 # Any number of blank chars.
                )
                (?P<envvar>.+?)  # Greedy-matching of any string and line returns.
            )?                  # The envvar group is optional.

            (?P<label_sep>
                ;               # Separator between labels.
                \s+                 # Any number of blank chars.
            )?

            (?:                         # Non-capturing group.
                (?P<default_label>
                    default:            # Starting content within the brackets.
                    \s+                 # Any number of blank chars.
                )
                (?P<default>.+?)  # Greedy-matching of any string and line returns.
            )?                      # The default group is optional.

            (?P<bracket_2>\])     # Square brackets closing.
            """,
            self.colorize,
            help_text,
            flags=re.VERBOSE | re.DOTALL,
        )

        # Highlight CLI names and commands.
        for cli_name in self.cli_names:
            help_text = re.sub(
                rf"""
                (\s)                                        # Any blank char.
                (?P<invoked_command>{re.escape(cli_name)})  # The CLI name.
                (\s)                                        # Any blank char.
                """,
                self.colorize,
                help_text,
                flags=re.VERBOSE,
            )

        # Highligh sections.
        # XXX Duplicates Cloup's job, with the only subtlety of not highlighting the
        # trailing semicolon.
        #
        # help_text = re.sub(
        #     r"""
        #     ^                       # Beginning of a line preceded by a newline.
        #     (?P<heading>\S[\S+ ]+)  # The section title.
        #     (:)                     # A semicolon.
        #     """,
        #     self.colorize,
        #     help_text,
        #     flags=re.VERBOSE | re.MULTILINE,
        # )

        # Highlight keywords.
        for matching_keywords, style_group_id in (
            (sorted(self.long_options, reverse=True), "long_option"),
            (sorted(self.short_options), "short_option"),
            (sorted(self.choices, reverse=True), "choice"),
            (sorted(self.metavars, reverse=True), "metavar"),
        ):
            for keyword in matching_keywords:
                keyword = escape_for_help_sceen(keyword)
                help_text = re.sub(
                    rf"""
                    ([               # A keyword is preceded with either:
                        \s           # - a blank char
                        \[           # - an opening square bracket (as in choice string)
                        \|           # - a pipe (again like in choice strings)
                        \(           # - an opening parenthesis
                    ])
                    (?P<{style_group_id}>{keyword})
                    (\W)             # Any character which is not a word character.
                    """,
                    self.colorize,
                    help_text,
                    flags=re.VERBOSE,
                )

        return help_text

    def getvalue(self):
        """Wrap original `Click.HelpFormatter.getvalue()` to force extra-colorization on
        rendering."""
        help_text = super().getvalue()
        return self.highlight_extra_keywords(help_text)


def highlight(string, substrings, styling_method, ignore_case=False):
    """Highlights parts of the ``string`` that matches ``substrings``.

    Takes care of overlapping parts within the ``string``.
    """
    # Ranges of character indices flagged for highlighting.
    ranges = set()

    for part in set(substrings):
        # Search for occurrences of query parts in original string.
        flags = re3.IGNORECASE if ignore_case else 0
        ranges |= {
            f"{match.start()}-{match.end() - 1}"
            for match in re3.finditer(part, string, flags=flags, overlapped=True)
        }

    # Reduce ranges, compute complement ranges, transform them to list of integers.
    ranges = ",".join(ranges)
    highlight_ranges = int_ranges_from_int_list(ranges)
    untouched_ranges = int_ranges_from_int_list(
        complement_int_list(ranges, range_end=len(string))
    )

    # Apply style to range of characters flagged as matching.
    styled_str = ""
    for i, j in sorted(highlight_ranges + untouched_ranges):
        segment = getitem(string, slice(i, j + 1))
        if (i, j) in highlight_ranges:
            segment = styling_method(segment)
        styled_str += segment

    return styled_str
