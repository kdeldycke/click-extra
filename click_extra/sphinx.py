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

"""Helpers and utilities for Sphinx rendering of CLI based on Click Extra."""

from __future__ import annotations

from unittest.mock import patch

import click
from docutils.statemachine import ViewList
from sphinx.highlighting import PygmentsBridge

from .pygments import AnsiHtmlFormatter
from .tests.conftest import ExtraCliRunner

click_compat_hack = patch.object(
    click._compat, "text_type", create=True, return_value=str
)
""" Workaround for ``pallets-sphinx-themes``'s outdated reference to old ``click``'s Python 2 compatibility hack.

Emulates:
    .. code-block:: python

        import click._compat

        click._compat.text_type = str

See:
    - `similar hack in click 8.x's docs/conf.py <https://github.com/pallets/click/commit/00883dd3d0a29f68f375cab5e21cef0669941aba#diff-85933aa74a2d66c3e4dcdf7a9ad8397f5a7971080d34ef1108296a7c6b69e7e3>`_
    - `incriminating import in pallets_sphinx_themes <https://github.com/pallets/pallets-sphinx-themes/blob/7b69241f1fde3cc3849f513a9dd83fa8a2f36603/src/pallets_sphinx_themes/themes/click/domain.py#L9>`_
"""


def setup_ansi_pygment_styles(app):
    """Add support for ANSI Shell Session syntax highlighting."""
    app.config.pygments_style = "ansi-click-extra-furo-style"
    PygmentsBridge.html_formatter = AnsiHtmlFormatter


class PatchedViewList(ViewList):
    """Replace the code block produced by ``.. click:run::`` directive with an ANSI
    Shell Session (``.. code-block:: ansi-shell-session``).

    Targets:
        - ``.. sourcecode:: text`` `for Pallets-Sphinx-Themes <= 2.0.2 <https://github.com/pallets/pallets-sphinx-themes/blob/7b69241f1fde3cc3849f513a9dd83fa8a2f36603/src/pallets_sphinx_themes/themes/click/domain.py#L245>`_
        - ``.. sourcecode:: shell-session`` `for Pallets-Sphinx-Themes > 2.0.2 <https://github.com/pallets/pallets-sphinx-themes/pull/62>`_
    """

    def append(self, *args, **kwargs):
        default_run_blocks = (
            ".. sourcecode:: text",
            ".. sourcecode:: shell-session",
        )
        for run_block in default_run_blocks:
            if run_block in args:
                args = list(args)
                index = args.index(run_block)
                args[index] = ".. code-block:: ansi-shell-session"

        return super().append(*args, **kwargs)


def setup(app):
    """Register ``.. click:example::`` and ``.. click:run::`` directives, augmented with ANSI coloring."""
    setup_ansi_pygment_styles(app)

    with click_compat_hack:

        from pallets_sphinx_themes.themes.click import domain

        domain.ViewList = PatchedViewList

        ####################################
        #  pallets_sphinx_themes Patch #2  #
        ####################################
        # Replace the call to default ``CliRunner.invoke`` with a call to click_extra own version which is sensible to contextual color settings
        # and output unfiltered ANSI codes.
        # Fixes: <insert upstream bug report here>

        # Brutal, but effective.
        # Alternative patching methods: https://stackoverflow.com/a/38928265
        domain.ExampleRunner.__bases__ = (ExtraCliRunner,)

        # Force color rendering in ``invoke`` calls.
        domain.ExampleRunner.force_color = True

        # Register directives to Sphinx.
        domain.setup(app)
