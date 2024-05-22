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
"""Helpers and utilities to allow Pygments to parse and render ANSI codes."""

from __future__ import annotations

try:
    import pygments  # noqa: F401
except ImportError:
    raise ImportError(
        "You need to install click_extra[pygments] extra dependencies to use this "
        "module."
    )

from typing import Iterable, Iterator

from pygments import lexers
from pygments.filter import Filter
from pygments.filters import TokenMergeFilter
from pygments.formatter import _lookup_style  # type: ignore[attr-defined]
from pygments.formatters import HtmlFormatter
from pygments.lexer import Lexer, LexerMeta
from pygments.lexers.algebra import GAPConsoleLexer
from pygments.lexers.dylan import DylanConsoleLexer
from pygments.lexers.erlang import ElixirConsoleLexer, ErlangShellLexer
from pygments.lexers.julia import JuliaConsoleLexer
from pygments.lexers.matlab import MatlabSessionLexer
from pygments.lexers.php import PsyshConsoleLexer
from pygments.lexers.python import PythonConsoleLexer
from pygments.lexers.r import RConsoleLexer
from pygments.lexers.ruby import RubyConsoleLexer
from pygments.lexers.shell import ShellSessionBaseLexer
from pygments.lexers.special import OutputLexer
from pygments.lexers.sql import PostgresConsoleLexer, SqliteConsoleLexer
from pygments.style import StyleMeta
from pygments.token import Generic, _TokenType, string_to_tokentype
from pygments_ansi_color import (
    AnsiColorLexer,
    ExtendedColorHtmlFormatterMixin,
    color_tokens,
)

DEFAULT_TOKEN_TYPE = Generic.Output
"""Default Pygments' token type to render with ANSI support.

We defaults to ``Generic.Output`` tokens, as this is the token type used by all REPL-
like and terminal lexers.
"""


class AnsiFilter(Filter):
    """Custom filter transforming a particular kind of token (``Generic.Output`` by
    defaults) into ANSI tokens."""

    def __init__(self, **options) -> None:
        """Initialize a ``AnsiColorLexer`` and configure the ``token_type`` to be
        colorized.

        .. todo::

            Allow multiple ``token_type`` to be configured for colorization (if
            traditions are changed on Pygments' side).
        """
        super().__init__(**options)
        self.ansi_lexer = AnsiColorLexer()
        self.token_type = string_to_tokentype(
            options.get("token_type", DEFAULT_TOKEN_TYPE),
        )

    def filter(
        self, lexer: Lexer, stream: Iterable[tuple[_TokenType, str]]
    ) -> Iterator[tuple[_TokenType, str]]:
        """Transform each token of ``token_type`` type into a stream of ANSI tokens."""
        for ttype, value in stream:
            if ttype == self.token_type:
                # TODO: Should we re-wrap the resulting list of token into their
                # original Generic.Output?
                yield from self.ansi_lexer.get_tokens(value)
            else:
                yield ttype, value


class AnsiSessionLexer(LexerMeta):
    """Custom metaclass used as a class factory to derive an ANSI variant of default
    shell session lexers."""

    def __new__(cls, name, bases, dct):
        """Setup class properties' defaults for new ANSI-capable lexers.

        - Adds an ``ANSI`` prefix to the lexer's name.
        - Replaces all ``aliases`` IDs from the parent lexer with variants prefixed with
            ``ansi-``.
        """
        new_cls = super().__new__(cls, name, bases, dct)
        new_cls.name = f"ANSI {new_cls.name}"
        new_cls.aliases = tuple(f"ansi-{alias}" for alias in new_cls.aliases)
        return new_cls


class AnsiLexerFiltersMixin(Lexer):
    def __init__(self, *args, **kwargs) -> None:
        """Adds a ``TokenMergeFilter`` and ``AnsiOutputFilter`` to the list of filters.

        The session lexers we inherits from are parsing the code block line by line so
        they can differentiate inputs and outputs. Each output line ends up
        encapsulated into a ``Generic.Output`` token. We apply the ``TokenMergeFilter``
        filter to reduce noise and have each contiguous output lines part of the same
        single token.

        Then we apply our custom ``AnsiOutputFilter`` to transform any
        ``Generic.Output`` monoblocks into ANSI tokens.
        """
        super().__init__(*args, **kwargs)
        self.filters.append(TokenMergeFilter())
        self.filters.append(AnsiFilter())


def collect_session_lexers() -> Iterator[type[Lexer]]:
    """Retrieve all lexers producing shell-like sessions in Pygments.

    This function contain a manually-maintained list of lexers, to which we dynamiccaly
    adds lexers inheriting from ``ShellSessionBaseLexer``.

    .. hint::

        To help maintain this list, there is `a test that will fail
        <https://github.com/kdeldycke/click-extra/blob/main/click_extra/tests/test_pygments.py>`_
        if a new REPL/terminal-like lexer is added to Pygments but not referenced here.
    """
    yield from [
        DylanConsoleLexer,
        ElixirConsoleLexer,
        ErlangShellLexer,
        GAPConsoleLexer,
        JuliaConsoleLexer,
        MatlabSessionLexer,
        OutputLexer,
        PostgresConsoleLexer,
        PsyshConsoleLexer,
        PythonConsoleLexer,
        RConsoleLexer,
        RubyConsoleLexer,
        SqliteConsoleLexer,
    ]

    for lexer in lexers._iter_lexerclasses():
        if ShellSessionBaseLexer in lexer.__bases__:
            yield lexer


lexer_map = {}
"""Map original lexer to their ANSI variant."""


# Auto-generate the ANSI variant of all lexers we collected.
for original_lexer in collect_session_lexers():
    new_name = f"Ansi{original_lexer.__name__}"
    new_lexer = AnsiSessionLexer(new_name, (AnsiLexerFiltersMixin, original_lexer), {})
    locals()[new_name] = new_lexer
    lexer_map[original_lexer] = new_lexer


class AnsiHtmlFormatter(ExtendedColorHtmlFormatterMixin, HtmlFormatter):
    """Extend standard Pygments' ``HtmlFormatter``.

    `Adds support for ANSI 256 colors <https://github.com/chriskuehl/pygments-ansi-color#optional-enable-256-color-support>`_.
    """

    name = "ANSI HTML"
    aliases = ["ansi-html"]

    def __init__(self, **kwargs) -> None:
        """Intercept the ``style`` argument to augment it with ANSI colors support.

        Creates a new style instance that inherits from the one provided by the user,
        but updates its ``styles`` attribute to add ANSI colors support from
        ``pygments_ansi_color``.
        """
        # XXX Same default style as in Pygments' HtmlFormatter, which is... `default`:
        # https://github.com/pygments/pygments/blob/1d83928/pygments/formatter.py#LL89C33-L89C33
        base_style_id = kwargs.setdefault("style", "default")

        # Fetch user-provided style.
        base_style = _lookup_style(base_style_id)

        # Augment the style with ANSI colors support.
        augmented_styles = dict(base_style.styles)
        augmented_styles.update(color_tokens(enable_256color=True))

        # Prefix the style name with `Ansi` to avoid name collision with the original
        # and ease debugging.
        new_name = f"Ansi{base_style.__name__}"
        new_lexer = StyleMeta(new_name, (base_style,), {"styles": augmented_styles})

        kwargs["style"] = new_lexer

        super().__init__(**kwargs)
