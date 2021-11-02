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

""" Helpers and utilities to apply ANSI coloring to terminal content. """

import re
from collections import namedtuple
from functools import partial

import click
from boltons.ecoutils import get_profile
from click_log import ColorFormatter
from cloup import GroupedOption, HelpFormatter, HelpTheme, Style

# Extend the predefined theme named tuple with our extra styles.
theme_params = {
    field: Style()
    for field in HelpTheme._fields
    + ("subheading", "option", "choice", "metavar", "search", "success")
}

# Extend even more with logging styles.
assert set(theme_params).isdisjoint(ColorFormatter.colors)
theme_params.update(
    {
        style_id: Style(**color_params)
        for style_id, color_params in ColorFormatter.colors.items()
    }
)

# Populate theme with all default styles.
HelpExtraTheme = namedtuple(
    "HelpExtraTheme", theme_params.keys(), defaults=theme_params.values()
)


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


# Pre-rendered UI-elements.
OK = theme.success("✓")
KO = theme.error("✘")


def disable_colors(ctx, param, value):
    """Callback disabling all coloring utilities."""

    # There is an undocumented color flag in context:
    # https://github.com/pallets/click/blob/65eceb08e392e74dcc761be2090e951274ccbe36/src/click/globals.py#L56-L69
    ctx.color = value

    if not value:

        def restore_original_styling():
            # Reset color flag in context.
            ctx = click.get_current_context()
            ctx.color = None

        ctx.call_on_close(restore_original_styling)


def color_option(
    *names,
    is_flag=True,
    default=True,
    is_eager=True,
    expose_value=False,
    callback=disable_colors,
    help="Strip out all colors and all ANSI codes from output.",
    cls=GroupedOption,
    **kwargs,
):
    """A ready to use option decorator that is adding a ``--color/--no-color`` (aliased by
    ``--ansi/--no-ansi``) option to keep or strip colors and ANSI codes from CLI output.

    This option is eager by defaults to allow for other eager options (like
    ``--version``) to be rendered colorless.
    """
    if not names:
        names = ("--color/--no-color", "--ansi/--no-ansi")
    return click.option(
        *names,
        is_flag=is_flag,
        default=default,
        is_eager=is_eager,
        expose_value=expose_value,
        callback=callback,
        help=help,
        cls=cls,
        **kwargs,
    )


def version_option(
    version=None,
    *names,
    message="%(prog)s, version %(version)s",
    print_env_info=False,
    version_style=Style(fg="green"),
    package_name_style=theme.invoked_command,
    prog_name_style=theme.invoked_command,
    message_style=None,
    env_info_style=Style(fg="bright_black"),
    cls=GroupedOption,
    **kwargs,
):
    """
    :param print_env_info: adds environment info at the end of the message. Useful to gather user's details for troubleshooting.
    :param version_style: style of the ``version``. Defaults to green.
    :param package_name_style: style of the ``package_name``. Defaults to theme's invoked_command.
    :param prog_name_style: style of the ``prog_name``. Defaults to theme's invoked_command.
    :param message_style: default style of the ``message``.
    :param env_info_style: style of the environment info. Defaults to bright black.

    For other params see Click's ``version_option`` decorator:
    https://click.palletsprojects.com/en/8.0.x/api/#click.version_option
    """
    if not message:
        message = ""

    if print_env_info:
        env_info = "\n" + str(get_profile(scrub=True))
        if env_info_style:
            env_info = env_info_style(env_info)
        message += env_info

    colorized_message = ""
    for part in re.split(r"(%\(version\)s|%\(package\)s|%\(prog\)s)", message):
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
    if not colorized_message:
        colorized_message = message

    # XXX:fix to default to user's CLI, not click_extra.__version__).
    return click.version_option(
        version,
        *names,
        cls=cls,
        message=colorized_message,
        **kwargs,
    )


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

            if isinstance(param.type, click.Choice):
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
        """Feed our custom formatter instance with the keywords to highlights."""
        (
            formatter.cli_name,
            formatter.long_options,
            formatter.short_options,
            formatter.choices,
            formatter.metavars,
        ) = self.collect_keywords(ctx)
        return super().format_help(ctx, formatter)


class HelpExtraFormatter(HelpFormatter):
    """Extends Cloup's custom HelpFormatter to highlights options, choices,
    metavars and default values.

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
        """Highlight extra keywoards in help screens based on the theme.

        It is based on regular expressions. While this is not a bullet-proof method, it is good
        enough. After all, help screens are not consumed by machine but are designed for human.
        """

        def colorize(match, style):
            """Re-create the matching string by concatenating all groups, but only
            colorize named groups.
            """
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
            fr"(\s)(?P<colorize>{self.cli_name})",
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
                    fr"([\s\[\|\(])(?P<colorize>{keyword})(\W)",
                    partial(colorize, style=style),
                    help_text,
                )

        return help_text

    def getvalue(self):
        """Wrap original `Click.HelpFormatter.getvalue()` to force extra-colorization on rendering."""
        help_text = super().getvalue()
        return self.highlight_extra_keywords(help_text)
