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

"""Helpers and utilities to apply ANSI coloring to terminal content."""

import inspect
import os
import re
import sys
import types
import typing as t
from collections import namedtuple
from configparser import RawConfigParser
from functools import partial
from gettext import gettext as _
from operator import getitem

import click
import cloup
import regex as re3
from boltons.strutils import complement_int_list, int_ranges_from_int_list
from click_log import ColorFormatter

from . import (
    Choice,
    ExtraOption,
    HelpFormatter,
    HelpTheme,
    ParameterSource,
    Style,
    echo,
    get_current_context,
)

# Extend the predefined theme named tuple with our extra styles.
theme_params = {
    field: Style()
    for field in HelpTheme._fields
    + ("subheading", "option", "choice", "metavar", "search", "success")
}

# Extend even more with logging styles.
log_level_styles = {
    "critical": Style(fg="red"),
    "error": Style(fg="red"),
    "warning": Style(fg="yellow"),
    "info": Style(),
    "debug": Style(fg="blue"),
}
# Check consistency.
assert set(log_level_styles) == {l.lower() for l in LOG_LEVELS}
assert set(theme_params).isdisjoint(log_level_styles)
theme_params.update(log_level_styles)

# Populate theme with all default styles.
HelpExtraTheme = namedtuple(
    "HelpExtraTheme", theme_params.keys(), defaults=theme_params.values()
)
"""Like ``cloup.HelpTheme`` but with Click Extra's specific themeable properties and click-log's."""


# Set our CLI global theme.
theme = HelpExtraTheme(
    invoked_command=Style(fg="bright_white"),
    heading=Style(fg="bright_blue", bold=True),
    subheading=Style(fg="blue"),
    constraint=Style(fg="magenta"),
    col1=Style(fg="cyan"),
    option=Style(fg="cyan"),
    choice=Style(fg="magenta"),
    metavar=Style(fg="bright_black"),
    search=Style(fg="green", bold=True),
    success=Style(fg="green"),
)


# No color theme.
nocolor_theme = HelpExtraTheme(
    **{style_id: Style() for style_id in HelpExtraTheme._fields}
)


OK = theme.success("✓")
KO = theme.error("✘")
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
"""List of environment variables recognized as flags to switch color rendering on or off.

The key is the name of the variable and the boolean value the value to pass to ``--color`` option flag when encountered.

Source: https://github.com/pallets/click/issues/558
"""


class ColorOption(ExtraOption):
    """A pre-configured option that is adding a ``--color/--no-color`` (aliased
    by ``--ansi/--no-ansi``) option to keep or strip colors and ANSI codes from CLI
    output.

    This option is eager by default to allow for other eager options (like
    ``--version``) to be rendered colorless.
    """

    @staticmethod
    def _disable_colors(ctx, param, value):
        """Callback disabling all coloring utilities.

        Re-inspect the environment for existence of colorization flags to re-interpret the
        provided value.
        """
        # Collect all colorize flags in environment variables we recognize.
        colorize_from_env = set()
        for var, default in color_env_vars.items():
            if var in os.environ:
                # Presence of the variable in the environment without a value encodes for an activation,
                # hence the default to True.
                var_value = os.environ.get(var, "true")
                # `os.environ` is a dict whose all values are strings. Here we normalize these string into
                # booleans. If we can't, we fallback to True, in the same spirit as above.
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
        # https://github.com/pallets/click/blob/65eceb08e392e74dcc761be2090e951274ccbe36/src/click/globals.py#L56-L69
        ctx.color = value

        if not value:

            def restore_original_styling():
                """Reset color flag in context."""
                ctx = get_current_context()
                ctx.color = None

            ctx.call_on_close(restore_original_styling)

    def __init__(
        self,
        param_decls=None,
        is_flag=True,
        default=True,
        is_eager=True,
        expose_value=False,
        callback=_disable_colors.__func__,
        help=_("Strip out all colors and all ANSI codes from output."),
        **kwargs,
    ):
        if not param_decls:
            param_decls = ("--color/--no-color", "--ansi/--no-ansi")

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            callback=callback,
            help=help,
            **kwargs,
        )


def color_option(*param_decls: str, cls=ColorOption, **kwargs):
    """Decorator for ``ColorOption``."""
    return cloup.option(*param_decls, cls=cls, **kwargs)


class VersionOption(ExtraOption):
    """Prints the colored version of the CLI.

    This is a [copy of the standard ``@click.version_option()`` decorator](https://github.com/pallets/click/blob/dc918b48fb9006be683a684b42cc7496ad649b83/src/click/decorators.py#L399-L466)
    that has been made into a class to allow it to be used with declarative `params=` argument
    (fixes [Click #2324 issue](https://github.com/pallets/click/issues/2324)).
    """

    def guess_package_name(self):
        package_name = None

        frame = inspect.currentframe()
        f_back = frame.f_back if frame is not None else None
        f_globals = f_back.f_globals if f_back is not None else None
        # break reference cycle
        # https://docs.python.org/3/library/inspect.html#the-interpreter-stack
        del frame

        if f_globals is not None:
            package_name = f_globals.get("__name__")

            if package_name == "__main__":
                package_name = f_globals.get("__package__")

            if package_name:
                package_name = package_name.partition(".")[0]

        return package_name

    def callback(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
        capture_output: bool = False,
    ) -> None:
        """Standard callback with an extra ``capture_output`` parameter which returns the output string instead of printing the (colored) version to the console."""
        if not value or ctx.resilient_parsing:
            return

        if self.prog_name is None:
            self.prog_name = ctx.find_root().info_name

        if self.version is None and self.package_name is not None:
            metadata: t.Optional[types.ModuleType]

            try:
                from importlib import metadata  # type: ignore
            except ImportError:
                # Python < 3.8
                import importlib_metadata as metadata  # type: ignore

            try:
                self.version = metadata.version(self.package_name)  # type: ignore
            except metadata.PackageNotFoundError:  # type: ignore
                raise RuntimeError(
                    f"{self.package_name!r} is not installed. Try passing"
                    " 'package_name' instead."
                ) from None

        if self.version is None:
            raise RuntimeError(
                f"Could not determine the version for {self.package_name!r} automatically."
            )

        output = t.cast(str, self.message) % {
            "prog": self.prog_name,
            "package": self.package_name,
            "version": self.version,
        }

        if capture_output:
            return output

        echo(output, color=ctx.color)
        ctx.exit()

    def __init__(
        self,
        param_decls=None,
        version=None,
        package_name: t.Optional[str] = None,
        prog_name: t.Optional[str] = None,
        message: str = _("%(prog)s, version %(version)s"),
        print_env_info=False,
        version_style=Style(fg="green"),
        package_name_style=theme.invoked_command,
        prog_name_style=theme.invoked_command,
        message_style=None,
        env_info_style=Style(fg="bright_black"),
        is_flag=True,
        expose_value=False,
        is_eager=True,
        help=_("Show the version and exit."),
        **kwargs,
    ):
        """
        For other params see Click's ``version_option`` decorator:
        https://click.palletsprojects.com/en/8.1.x/api/#click.version_option

        :param param_decls: _description_, defaults to None
        :type param_decls: _type_, optional
        :param version: _description_, defaults to None
        :type version: _type_, optional
        :param package_name: _description_, defaults to None
        :type package_name: t.Optional[str], optional
        :param prog_name: _description_, defaults to None
        :type prog_name: t.Optional[str], optional
        :param message: _description_, defaults to "%(prog)s, version %(version)s"
        :type message: str, optional
        :param print_env_info: _description_, defaults to False
        :type print_env_info: bool, optional
        :param version_style: adds environment info at the end of the message. Useful to gather user's details for troubleshooting. Defaults to ``Style(fg="green")``.
        :type version_style: _type_, optional
        :param package_name_style: style of the ``version``. Defaults to ``theme.invoked_command``.
        :type package_name_style: _type_, optional
        :param prog_name_style: style of the ``prog_name``. Defaults to ``theme.invoked_command``.
        :type prog_name_style: _type_, optional
        :param message_style: default style of the ``message`` parameter. Defaults to ``None``.
        :type message_style: _type_, optional
        :param env_info_style: style of the environment info. Defaults to ``Style(fg="bright_black")``.
        :type env_info_style: _type_, optional
        :param is_flag: _description_, defaults to True
        :type is_flag: bool, optional
        :param expose_value: _description_, defaults to False
        :type expose_value: bool, optional
        :param is_eager: _description_, defaults to True
        :type is_eager: bool, optional
        :param help: _description_, defaults to "Show the version and exit."
        :type help: str, optional
        """
        if not param_decls:
            param_decls = ("--version",)

        kwargs.setdefault("callback", self.callback)

        self.version = version
        self.package_name = package_name
        self.prog_name = prog_name
        self.message = message

        if self.version is None and self.package_name is None:
            self.package_name = self.guess_package_name()

        # XXX Temporarily skip displaying environment details for Python >= 3.10 while we wait for
        # https://github.com/mahmoud/boltons/issues/294 to be released upstream.
        if print_env_info and sys.version_info[:2] < (3, 10):
            from boltons.ecoutils import get_profile

            env_info = "\n" + str(get_profile(scrub=True))
            if env_info_style:
                env_info = env_info_style(env_info)
            self.message += env_info

        colorized_message = ""
        for part in re.split(r"(%\(version\)s|%\(package\)s|%\(prog\)s)", self.message):
            # Skip empty strings.
            if not part:
                continue
            if part == "%(package)s" and package_name_style:
                part = package_name_style(part)
            elif part == "%(prog)s" and prog_name_style:
                part = prog_name_style(part)
            elif part == "%(version)s" and version_style:
                part = version_style(part)
            elif message_style:
                part = message_style(part)
            colorized_message += part
        if colorized_message:
            self.message = colorized_message

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )


def version_option(*param_decls: str, cls=VersionOption, **kwargs):
    """Decorator for ``VersionOption``."""
    return cloup.option(*param_decls, cls=cls, **kwargs)


class HelpOption(ExtraOption):
    @staticmethod
    def callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
        if not value or ctx.resilient_parsing:
            return

        echo(ctx.get_help(), color=ctx.color)
        ctx.exit()

    def __init__(
        self,
        param_decls=None,
        callback=callback.__func__,
        is_flag=True,
        expose_value=False,
        is_eager=True,
        help=_("Show this message and exit."),
        **kwargs,
    ):
        if not param_decls:
            param_decls = ("--help", "-h")

        super().__init__(
            param_decls=param_decls,
            callback=callback,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )


def help_option(*param_decls: str, cls=HelpOption, **kwargs):
    """Decorator for ``HelpOption``."""
    return cloup.option(*param_decls, cls=cls, **kwargs)


class ExtraHelpColorsMixin:
    """Adds extra-keywords highlighting to Click commands.

    This mixin for `click.core.Command`-like classes intercepts the top-level
    helper-generation method to initialize the formatter with dynamic settings.

    This is implemented here to get access to the global context.
    """

    def collect_keywords(self, ctx):
        """Parse click context to collect option names, choices and metavar keywords."""
        options = set()
        choices = set()
        metavars = set()

        # Includes CLI base name and its commands.
        cli_name = ctx.command_path

        # Add user defined help options.
        options.update(ctx.help_option_names)

        # Collect all option names and choice keywords.
        for param in ctx.command.params:
            options.update(param.opts)

            if isinstance(param.type, Choice):
                choices.update(param.type.choices)

            if param.metavar:
                metavars.add(param.metavar)

        # Split between shorts and long options
        long_options = set()
        short_options = set()
        for option in options:
            if option.startswith("--"):
                long_options.add(option)
            else:
                short_options.add(option)

        return cli_name, long_options, short_options, choices, metavars

    def get_help(self, ctx):
        """Replace default formatter by our own."""
        ctx.formatter_class = HelpExtraFormatter
        return super().get_help(ctx)

    def format_help(self, ctx, formatter):
        """Feed our custom formatter instance with the keywords to highlight."""
        (
            formatter.cli_name,
            formatter.long_options,
            formatter.short_options,
            formatter.choices,
            formatter.metavars,
        ) = self.collect_keywords(ctx)
        return super().format_help(ctx, formatter)


class HelpExtraFormatter(HelpFormatter):
    """Extends Cloup's custom HelpFormatter to highlights options, choices, metavars and
    default values.

    This is being discussed for upstream integration at:
    * https://github.com/janluke/cloup/issues/97
    * https://github.com/click-contrib/click-help-colors/issues/17
    * https://github.com/janluke/cloup/issues/95
    """

    def __init__(self, *args, **kwargs):
        """Forces our hard-coded theme as default if none provided."""
        if "theme" not in kwargs:
            kwargs["theme"] = theme
        super().__init__(*args, **kwargs)

    # Lists of extra keywords to highlight.
    cli_name = None
    long_options = set()
    short_options = set()
    choices = set()
    metavars = set()

    def highlight_extra_keywords(self, help_text):
        """Highlight extra keywords in help screens based on the theme.

        It is based on regular expressions. While this is not a bullet-proof method, it
        is good enough. After all, help screens are not consumed by machine but are
        designed for humans.
        """

        def colorize(match, style):
            """Recreate the matching string by concatenating all groups, but only
            colorize named groups."""
            txt = ""
            for group in match.groups():
                if group in match.groupdict().values():
                    txt += style(group)
                else:
                    txt += group
            return txt

        # Highligh numbers.
        help_text = re.sub(
            r"(\s)(?P<colorize>-?\d+)",
            partial(colorize, style=self.theme.choice),
            help_text,
        )

        # Highlight CLI name and command.
        help_text = re.sub(
            rf"(\s)(?P<colorize>{self.cli_name})",
            partial(colorize, style=self.theme.invoked_command),
            help_text,
        )

        # Highligh sections.
        help_text = re.sub(
            r"^(?P<colorize>\S[\S+ ]+)(:)",
            partial(colorize, style=self.theme.heading),
            help_text,
            flags=re.MULTILINE,
        )

        # Highlight keywords.
        for matching_keywords, style in (
            (sorted(self.long_options, reverse=True), self.theme.option),
            (sorted(self.short_options), self.theme.option),
            (sorted(self.choices, reverse=True), self.theme.choice),
            (sorted(self.metavars, reverse=True), self.theme.metavar),
        ):
            for keyword in matching_keywords:
                # Accounts for text wrapping after a dash.
                keyword = keyword.replace("-", "-\\s*")
                help_text = re.sub(
                    rf"([\s\[\|\(])(?P<colorize>{keyword})(\W)",
                    partial(colorize, style=style),
                    help_text,
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
