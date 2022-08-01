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

"""Helpers and utilities to allow Pygments to parse and render ANSI codes."""

from configparser import ConfigParser

import furo
from pygments.filter import Filter
from pygments.filters import TokenMergeFilter
from pygments.formatters import HtmlFormatter
from pygments.lexer import LexerMeta
from pygments.lexers.shell import (
    BashSessionLexer,
    MSDOSSessionLexer,
    PowerShellSessionLexer,
    TcshSessionLexer,
)
from pygments.styles import get_style_by_name
from pygments.token import Generic, string_to_tokentype
from pygments_ansi_color import (
    AnsiColorLexer,
    ExtendedColorHtmlFormatterMixin,
    color_tokens,
)

# Note: You can use different background colors for improved readability.
fg_colors = bg_colors = {
    "Black": "#000000",
    "Red": "#EF2929",
    "Green": "#8AE234",
    "Yellow": "#FCE94F",
    "Blue": "#3465A4",
    "Magenta": "#c509c5",
    "Cyan": "#34E2E2",
    "White": "#ffffff",
}


# Extract the name of furo's default pygment style, as defined in:
# https://github.com/pradyunsg/furo/blob/8eba6499b812d7aeab2a99fcdf33e8bcb07b05fc/src/furo/theme/furo/theme.conf#L4
furo_conf = furo.THEME_PATH / "theme.conf"
ini_config = ConfigParser()
ini_config.read_string(furo_conf.read_text())
furo_style_name = ini_config.get("theme", "pygments_style")


# Base our new custom style in furo's.
style_base = get_style_by_name(furo_style_name)


class ClickExtraAnsiFuroStyle(style_base):
    styles = dict(style_base.styles)
    styles.update(color_tokens(fg_colors, bg_colors, enable_256color=True))


class AnsiFilter(Filter):
    """Custom filter transforming a particular kind of token (``Generic.Output`` by defaults) into ANSI tokens."""

    def __init__(self, **options) -> None:
        """Initialize a ``AnsiColorLexer`` and get the ``token_type`` to transform."""
        super().__init__(**options)
        self.ansi_lexer = AnsiColorLexer()
        self.token_type = string_to_tokentype(options.get("token_type", Generic.Output))

    def filter(self, lexer, stream):
        """Transform each ``Generic.Output`` token into a stream of ANSI tokens."""
        for ttype, value in stream:
            if ttype == self.token_type:
                # TODO: re-wrap the resulting list of token into Generic.Output?
                yield from self.ansi_lexer.get_tokens(value)
            else:
                yield ttype, value


class AnsiSessionLexer(LexerMeta):
    """Custom metaclass used as a class factory to derive an ANSI variant of default shell session lexers."""

    def __new__(cls, name, bases, dct):
        """Setup class properties defaults for new ANSI-capable lexers

        Add an ANSI prefix to its name.

        Replace all ``aliases`` IDs from the parent lexer with variants prefixed with ``ansi-``.
        """
        new_cls = super().__new__(cls, name, bases, dct)

        # Prefix new lexer name.
        new_cls.name = f"ANSI {new_cls.name}"

        # Update all lexer IDs with ansi prefix.
        new_cls.aliases = tuple(f"ansi-{alias}" for alias in new_cls.aliases)

        return new_cls


class AnsiLexerFiltersMixin:
    def __init__(self, *args, **kwargs) -> None:
        """Adds a ``TokenMergeFilter`` and ``AnsiOutputFilter`` to the list of filters.

        The shell-session lexers we inherits from are parsing the code block line by line.
        Each output line ends up encapsulated into a ``Generic.Output`` token. We forces the use of ``TokenMergeFilter`` to
        have all the output blocks wrap by a single token.

        Then we apply our custom ``AnsiOutputFilter`` to transform the
        ``Generic.Output`` monoblock into ANSI tokens.
        """
        super().__init__(*args, **kwargs)
        self.filters.append(TokenMergeFilter())
        self.filters.append(AnsiFilter())


# TODO: fetch all lexers which are a subclass of ShellSessionBaseLexer and use auto-class generation to replace the repeating code below.


class AnsiBashSessionLexer(
    AnsiLexerFiltersMixin, BashSessionLexer, metaclass=AnsiSessionLexer
):
    pass


class AnsiMSDOSSessionLexer(
    AnsiLexerFiltersMixin, MSDOSSessionLexer, metaclass=AnsiSessionLexer
):
    pass


class AnsiPowerShellSessionLexer(
    AnsiLexerFiltersMixin, PowerShellSessionLexer, metaclass=AnsiSessionLexer
):
    pass


class AnsiTcshSessionLexer(
    AnsiLexerFiltersMixin, TcshSessionLexer, metaclass=AnsiSessionLexer
):
    pass


class AnsiHtmlFormatter(ExtendedColorHtmlFormatterMixin, HtmlFormatter):
    """
    Extend standard Pygments' ``HtmlFormatter`` to [add support for ANSI 256 colors](https://github.com/chriskuehl/pygments-ansi-color#optional-enable-256-color-support).
    """

    name = "ANSI HTML"
    aliases = ["ansi-html"]
