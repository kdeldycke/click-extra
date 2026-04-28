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
"""Helpers and utilities for Sphinx.

.. note::
    The MkDocs counterpart lives in :mod:`click_extra.mkdocs`, which achieves the same
    ANSI color rendering by patching ``pymdownx.highlight``'s formatter classes.
"""

from __future__ import annotations

try:
    import sphinx  # noqa: F401
except ImportError:
    raise ImportError(
        "You need to install click_extra[sphinx] dependency group to use this module."
    )

from sphinx.highlighting import PygmentsBridge

from .. import __version__
from ..pygments import AnsiHtmlFormatter
from .alerts import convert_github_alerts
from .click import ClickDomain, cleanup_runner
from .python import PythonDomain, cleanup_python_runner

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.util.typing import ExtensionMetadata


def setup(app: Sphinx) -> ExtensionMetadata:
    """Register extensions to Sphinx.

    - ``click:source`` / ``click:run`` directives, augmented with ANSI coloring.
    - ``python:source`` / ``python:run`` / ``python:render`` /
      ``python:render-myst`` / ``python:render-rst`` directives that execute
      arbitrary Python code at build time. The ``render`` family parses the
      captured output as live document content (host parser, forced MyST, or
      forced reST respectively), replacing the regenerator-script +
      marker-region pattern for auto-generated docs.
    - Support for GitHub alerts syntax in *included* and regular *source* files.

    .. caution::
        This function forces the Sphinx app to use
        ``sphinx.highlighting.PygmentsBridge`` instead of the default HTML formatter to
        add support for ANSI colors in code blocks.
    """
    # Set Sphinx's default HTML formatter to an ANSI capable one.
    PygmentsBridge.html_formatter = AnsiHtmlFormatter

    # Register click:source and click:run directives.
    app.add_domain(ClickDomain)
    app.connect("doctree-read", cleanup_runner)

    # Register the python:* directive family (source, run, render,
    # render-myst, render-rst).
    app.add_domain(PythonDomain)
    app.connect("doctree-read", cleanup_python_runner)

    # Register GitHub alerts converter.
    app.connect("source-read", convert_github_alerts)
    app.connect("include-read", convert_github_alerts)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
