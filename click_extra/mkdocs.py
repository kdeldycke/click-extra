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
"""MkDocs plugin for ANSI color rendering in code blocks.

Patches `pymdownx.highlight <https://facelessuser.github.io/pymdown-extensions/
extensions/highlight/>`_'s formatter classes so that ``Token.Ansi.*`` tokens produced by
Click Extra's :doc:`Pygments lexers <pygments>` are decomposed into individual CSS classes
and styled with the correct colors.

.. note::
    This is the MkDocs counterpart of the Sphinx integration in
    :mod:`click_extra.sphinx`, which achieves the same result by replacing
    ``sphinx.highlighting.PygmentsBridge.html_formatter``.
"""

from __future__ import annotations

try:
    from mkdocs.plugins import BasePlugin
except ImportError:
    raise ImportError(
        "You need to install click_extra[mkdocs] dependency group to use this module."
    )

import pymdownx.highlight

from .pygments import AnsiHtmlFormatter

TYPE_CHECKING = False
if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig


class AnsiColorPlugin(BasePlugin):
    """MkDocs plugin that adds ANSI color support to Pygments code blocks.

    Monkey-patches ``pymdownx.highlight``'s block and inline formatter classes to
    inherit from :class:`~click_extra.pygments.AnsiHtmlFormatter`. This gives every code
    block in the MkDocs site full ANSI color rendering: compound tokens like
    ``Token.Ansi.Bold.Cyan`` are decomposed into individual CSS classes, and the
    stylesheet includes rules for the 256-color indexed palette and all SGR text
    attributes.
    """

    def on_config(self, config: MkDocsConfig) -> MkDocsConfig:
        """Patch pymdownx.highlight formatters before page processing begins."""
        if not issubclass(pymdownx.highlight.BlockHtmlFormatter, AnsiHtmlFormatter):
            pymdownx.highlight.BlockHtmlFormatter = type(
                "AnsiBlockHtmlFormatter",
                (AnsiHtmlFormatter, pymdownx.highlight.BlockHtmlFormatter),
                {},
            )
        if not issubclass(pymdownx.highlight.InlineHtmlFormatter, AnsiHtmlFormatter):
            pymdownx.highlight.InlineHtmlFormatter = type(
                "AnsiInlineHtmlFormatter",
                (AnsiHtmlFormatter, pymdownx.highlight.InlineHtmlFormatter),
                {},
            )
        return config
