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
"""Helpers and utilities for Sphinx rendering of CLI based on Click Extra.

.. danger::
    This module is quite janky but does the job. Still, it would benefits from a total
    clean rewrite. This would require a better understanding of Sphinx, Click and MyST
    internals. And as a side effect will eliminate the dependency on
    ``pallets_sphinx_themes``.

    If you're up to the task, you can try to refactor it. I'll probably start by moving
    the whole ``pallets_sphinx_themes.themes.click.domain`` code here, merge it with
    the local collection of monkey-patches below, then clean the whole code to make it
    more readable and maintainable. And finally, address all the todo-list below.

.. todo::
    Add support for plain MyST directives to remove the need of wrapping rST into an
    ``{eval-rst}`` block. Ideally, this would allow for the following simpler syntax in
    MyST:

    .. code-block:: markdown

        ```{click-example}
        from click_extra import echo, extra_command, option, style

        @extra_command
        @option("--name", prompt="Your name", help="The person to greet.")
        def hello_world(name):
            "Simple program that greets NAME."
            echo(f"Hello, {style(name, fg='red')}!")
        ```

    .. code-block:: markdown

        ```{click-run}
        invoke(hello_world, args=["--help"])
        ```

.. todo::
    Fix the need to have both ``.. click:example::`` and ``.. click:run::`` directives
    in the same ``{eval-rst}`` block in MyST. This is required to have both directives
    shares states and context.
"""

from __future__ import annotations

try:
    import sphinx  # noqa: F401
except ImportError:
    raise ImportError(
        "You need to install click_extra[sphinx] extra dependencies to use this "
        "module."
    )

from typing import Any

from docutils.statemachine import ViewList
from sphinx.highlighting import PygmentsBridge

from .pygments import AnsiHtmlFormatter
from .testing import ExtraCliRunner


class PatchedViewList(ViewList):
    """Force the rendering of ANSI shell session.

    Replaces the ``.. sourcecode:: shell-session`` code block produced by
    ``.. click:run::`` directive with an ANSI Shell Session:
    ``.. code-block:: ansi-shell-session``.

    ``.. sourcecode:: shell-session`` has been `released in Pallets-Sphinx-Themes 2.1.0
    <https://github.com/pallets/pallets-sphinx-themes/pull/62>`_.
    """

    def append(self, *args, **kwargs) -> None:
        """Search the default code block and replace it with our own version."""
        default_code_block = ".. sourcecode:: shell-session"
        new_code_block = ".. code-block:: ansi-shell-session"

        if default_code_block in args:
            new_args = list(args)
            index = args.index(default_code_block)
            new_args[index] = new_code_block
            args = tuple(new_args)

        return super().append(*args, **kwargs)


def setup(app: Any) -> None:
    """Register new directives, augmented with ANSI coloring.

    New directives:
        - ``.. click:example::``
        - ``.. click:run::``

    .. danger::
        This function activates lots of monkey-patches:

        - ``sphinx.highlighting.PygmentsBridge`` is updated to set its default HTML
          formatter to an ANSI capable one for the whole Sphinx app.

        - ``pallets_sphinx_themes.themes.click.domain.ViewList`` is
          `patched to force an ANSI lexer on the rST code block
          <#click_extra.sphinx.PatchedViewList>`_.

        - ``pallets_sphinx_themes.themes.click.domain.ExampleRunner`` is replaced with
          ``click_extra.testing.ExtraCliRunner`` to have full control of
          contextual color settings by the way of the ``color`` parameter. It also
          produce unfiltered ANSI codes so that the other ``PatchedViewList``
          monkey-patch can do its job and render colors in the HTML output.
    """
    # Set Sphinx's default HTML formatter to an ANSI capable one.
    PygmentsBridge.html_formatter = AnsiHtmlFormatter

    from pallets_sphinx_themes.themes.click import domain

    domain.ViewList = PatchedViewList

    # Brutal, but effective.
    # Alternative patching methods: https://stackoverflow.com/a/38928265
    domain.ExampleRunner.__bases__ = (ExtraCliRunner,)
    # Force color rendering in ``invoke`` calls.
    domain.ExampleRunner.force_color = True

    # Register directives to Sphinx.
    domain.setup(app)
