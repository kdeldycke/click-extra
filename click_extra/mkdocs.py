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

When `mkdocs-click <https://pypi.org/project/mkdocs-click/>`_ is installed, the plugin
also patches its code-block generators to use the ``ansi-output`` lexer instead of plain
``text``, so that CLI help text with ANSI escape codes renders with colors.

.. note::
    This is the MkDocs counterpart of the Sphinx integration in
    :mod:`click_extra.sphinx`, which achieves the same result by replacing
    ``sphinx.highlighting.PygmentsBridge.html_formatter``.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import wraps

try:
    from mkdocs.plugins import BasePlugin
except ImportError:
    raise ImportError(
        "You need to install click_extra[mkdocs] dependency group to use this module."
    )

import pymdownx.highlight

from .pygments import AnsiHtmlFormatter

ANSI_OUTPUT_FENCE = "```ansi-output"
"""Fenced code-block opening that triggers the ANSI-aware Pygments lexer."""

TEXT_FENCE = "```text"
"""Fenced code-block opening used by ``mkdocs-click`` for CLI help output."""

TYPE_CHECKING = False
if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig


def _ansi_lines(gen: Iterator[str]) -> Iterator[str]:
    """Replace ``TEXT_FENCE`` with ``ANSI_OUTPUT_FENCE`` in a line iterator."""
    for line in gen:
        yield ANSI_OUTPUT_FENCE if line == TEXT_FENCE else line


def _patch_mkdocs_click() -> None:
    """Patch ``mkdocs-click`` code blocks to use the ``ansi-output`` lexer.

    Wraps ``_make_usage`` and ``_make_plain_options`` so that their fenced
    code blocks use the ANSI-aware lexer instead of plain ``text``.  The patch
    is idempotent: calling it twice has no additional effect.
    """
    try:
        from mkdocs_click import _docs
    except ImportError:
        return

    if getattr(_docs, "_click_extra_patched", False):
        return

    orig_usage = _docs._make_usage
    orig_plain = _docs._make_plain_options

    @wraps(orig_usage)
    def _ansi_usage(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _ansi_lines(orig_usage(*args, **kwargs))

    @wraps(orig_plain)
    def _ansi_plain_options(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _ansi_lines(orig_plain(*args, **kwargs))

    _docs._make_usage = _ansi_usage
    _docs._make_plain_options = _ansi_plain_options
    _docs._click_extra_patched = True


class AnsiColorPlugin(BasePlugin):
    """MkDocs plugin that adds ANSI color support to Pygments code blocks.

    Monkey-patches ``pymdownx.highlight``'s block and inline formatter classes to
    inherit from :class:`~click_extra.pygments.AnsiHtmlFormatter`. This gives every code
    block in the MkDocs site full ANSI color rendering: compound tokens like
    ``Token.Ansi.Bold.Cyan`` are decomposed into individual CSS classes, and the
    stylesheet includes rules for the 256-color indexed palette and all SGR text
    attributes.

    When ``mkdocs-click`` is installed, its code-block generators are also patched to use
    the ``ansi-output`` lexer so that CLI help text renders with colors.
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
        _patch_mkdocs_click()
        return config
