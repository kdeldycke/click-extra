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
from sphinx.util import logging

from .. import __version__
from ..pygments import AnsiHtmlFormatter
from .alerts import convert_github_alerts
from .click import ClickDomain, cleanup_runner
from .python import PythonDomain, cleanup_python_runner

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.config import Config
    from sphinx.util.typing import ExtensionMetadata


logger = logging.getLogger(__name__)


PYTHON_DIRECTIVES_OPT_IN = "click_extra_enable_python_directives"
"""Name of the ``conf.py`` config flag that gates the ``python:*`` directives.

Default is ``False``: a project that adds ``click_extra.sphinx`` to its
``extensions`` list does *not* automatically gain access to arbitrary Python
build-time execution. The maintainer must opt in explicitly.

See :func:`_register_python_directives` for the rationale.
"""


def _register_python_directives(app: Sphinx, config: Config) -> None:
    """Register the ``python:*`` directives if the project has opted in.

    Connected to the ``config-inited`` event so the user's ``conf.py`` value
    has been merged before this runs. Without the opt-in, the
    :class:`~click_extra.sphinx.python.PythonDomain` is never registered:
    referencing ``python:run`` / ``python:render*`` in a document raises an
    "Unknown directive type" warning, exactly as if the extension were not
    installed.

    .. danger::
        These directives execute arbitrary Python at build time with the
        full privileges of the Sphinx process: filesystem, network,
        environment variables, secrets. Auto-enabling them on every project
        that imports ``click_extra.sphinx`` (transitively or otherwise)
        would silently expand the attack surface of every consumer.
        See ``docs/sphinx.md`` for the full trust boundary.
    """
    if not getattr(config, PYTHON_DIRECTIVES_OPT_IN, False):
        logger.info(
            "click_extra.sphinx: python:* directives are disabled. "
            "Set %s = True in conf.py to enable build-time Python "
            "execution. See docs/sphinx.md for security implications.",
            PYTHON_DIRECTIVES_OPT_IN,
        )
        return

    app.add_domain(PythonDomain)
    app.connect("doctree-read", cleanup_python_runner)


def setup(app: Sphinx) -> ExtensionMetadata:
    """Register extensions to Sphinx.

    - ``click:source`` / ``click:run`` directives, augmented with ANSI coloring.
      These run user-controlled Python (the directive body) at build time and
      are enabled unconditionally because documenting Click CLIs is the core
      feature this package provides.
    - ``python:source`` / ``python:run`` / ``python:render`` /
      ``python:render-myst`` / ``python:render-rst`` directives that execute
      arbitrary Python code at build time. The ``render`` family parses the
      captured output as live document content (host parser, forced MyST, or
      forced reST respectively), replacing the regenerator-script +
      marker-region pattern for auto-generated docs. **Disabled by default.**
      Set ``click_extra_enable_python_directives = True`` in ``conf.py`` to
      register them.
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

    # Declare the opt-in flag for the python:* directive family. The
    # `config-inited` callback below registers the domain only if the
    # project's conf.py opts in. Default is `False`: build-time arbitrary
    # Python execution is off unless explicitly turned on.
    app.add_config_value(PYTHON_DIRECTIVES_OPT_IN, False, "env", types=[bool])
    app.connect("config-inited", _register_python_directives)

    # Register GitHub alerts converter.
    app.connect("source-read", convert_github_alerts)
    app.connect("include-read", convert_github_alerts)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
