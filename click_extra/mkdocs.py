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

Decomposing tokens into classes only strips the raw escape codes: the classes carry no
color until a matching stylesheet is present. Unlike Sphinx's ``PygmentsBridge``, which
regenerates ``pygments.css`` from the active formatter on every build, MkDocs never emits
one for these classes. The plugin therefore writes the ANSI rules to a dedicated
stylesheet (``_ansi_stylesheet``) and registers it in ``extra_css`` so every page
links it.

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
from pathlib import Path

from .parameters import missing_extra_message

try:
    from mkdocs.plugins import BasePlugin
except ImportError as err:
    raise ImportError(missing_extra_message("mkdocs", subject="This module")) from err

import pymdownx.highlight

from .color import forced_color
from .pygments import AnsiHtmlFormatter

ANSI_OUTPUT_FENCE = "```ansi-output"
"""Fenced code-block opening that triggers the ANSI-aware Pygments lexer."""

TEXT_FENCE = "```text"
"""Fenced code-block opening used by ``mkdocs-click`` for CLI help output."""

ANSI_STYLESHEET = "assets/click-extra/ansi.css"
"""Site-relative path of the generated ANSI color stylesheet.

Registered in the MkDocs config's ``extra_css`` by
:meth:`AnsiColorPlugin.on_config` so every page links it, and written into the build
output by :meth:`AnsiColorPlugin.on_post_build`.
"""

TYPE_CHECKING = False
if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig


def _ansi_lines(gen: Iterator[str]) -> Iterator[str]:
    """Replace ``TEXT_FENCE`` with ``ANSI_OUTPUT_FENCE`` in a line iterator."""
    for line in gen:
        yield ANSI_OUTPUT_FENCE if line == TEXT_FENCE else line


def _patch_mkdocs_click() -> None:
    """Patch ``mkdocs-click`` code blocks to use the ``ansi-output`` lexer.

    Wraps ``_make_usage`` and ``_make_plain_options`` so that their fenced code blocks
    use the ANSI-aware lexer instead of plain ``text``, and so that the help they
    capture is rendered with color forced on. ``mkdocs-click`` builds help from
    ``ctx.make_formatter()`` rather than executing the command, so the environment
    override (:func:`~click_extra.color.forced_color`) is the only lever available
    here, and the capture is materialized inside it: the wrapped generators read their
    formatter eagerly so the escape codes are produced while the override is active, not
    lazily once the caller iterates and the environment has been restored. The patch is
    idempotent: calling it twice has no additional effect.
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
    def _ansi_usage(*args, **kwargs):
        with forced_color():
            lines = list(orig_usage(*args, **kwargs))
        return _ansi_lines(iter(lines))

    @wraps(orig_plain)
    def _ansi_plain_options(*args, **kwargs):
        with forced_color():
            lines = list(orig_plain(*args, **kwargs))
        return _ansi_lines(iter(lines))

    _docs._make_usage = _ansi_usage
    _docs._make_plain_options = _ansi_plain_options
    _docs._click_extra_patched = True  # type: ignore[attr-defined]


def _ansi_stylesheet() -> str:
    """Build the CSS that colors Click Extra's ``-Ansi-*`` token classes.

    Delegates to :meth:`~click_extra.pygments.AnsiHtmlFormatter.get_ansi_style_defs`,
    which returns only the ANSI-specific rules: the named and 256-color palette, the
    SGR text-attribute declarations, the blink keyframes, and the OSC 8 hyperlink rule.
    The standard Pygments token rules are dropped on purpose. Dumping the full style
    would override the theme's own syntax-highlighting colors (and, on themes like
    Material, their light and dark variants) for every code block. The ANSI rules are
    additive and theme-agnostic, so they layer safely on top.

    Scoped under the formatter's default ``cssclass`` (``.highlight``), the wrapper
    ``pymdownx.highlight`` and the Material theme both emit.
    """
    formatter = AnsiHtmlFormatter()
    return formatter.get_ansi_style_defs(f".{formatter.cssclass}") + "\n"


class AnsiColorPlugin(BasePlugin):
    """MkDocs plugin that adds ANSI color support to Pygments code blocks.

    Monkey-patches ``pymdownx.highlight``'s block and inline formatter classes to
    inherit from :class:`~click_extra.pygments.AnsiHtmlFormatter`. This gives every code
    block in the MkDocs site full ANSI color rendering: compound tokens like
    ``Token.Ansi.Bold.Cyan`` are decomposed into individual CSS classes, and a generated
    stylesheet (written by :meth:`on_post_build` and registered in ``extra_css`` by
    :meth:`on_config`) supplies the color rules for the 256-color indexed palette and all
    SGR text attributes.

    When ``mkdocs-click`` is installed, its code-block generators are also patched to use
    the ``ansi-output`` lexer so that CLI help text renders with colors.
    """

    def on_config(self, config: MkDocsConfig) -> MkDocsConfig:
        """Patch pymdownx.highlight formatters and register the ANSI stylesheet.

        Runs before page processing begins. Appending :data:`ANSI_STYLESHEET` to
        ``extra_css`` makes MkDocs link it from every page (resolving the relative
        path per page, including under ``use_directory_urls``). The file itself is
        written later, in :meth:`on_post_build`.
        """
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
        if ANSI_STYLESHEET not in config["extra_css"]:
            config["extra_css"].append(ANSI_STYLESHEET)
        _patch_mkdocs_click()
        return config

    def on_post_build(self, config: MkDocsConfig) -> None:
        """Write the ANSI color stylesheet into the built site.

        The formatters patched in :meth:`on_config` emit ``-Ansi-*`` CSS classes, but
        MkDocs, unlike Sphinx's ``PygmentsBridge``, never regenerates a Pygments
        stylesheet from the active formatter. Without this file the classes have no
        color rules and terminal output renders colorless. Runs after the theme has
        copied its own assets, so the file survives the site-directory cleanup.
        """
        css_path = Path(config["site_dir"]) / ANSI_STYLESHEET
        css_path.parent.mkdir(parents=True, exist_ok=True)
        css_path.write_text(_ansi_stylesheet(), encoding="utf-8")
