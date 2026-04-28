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


EXEC_DIRECTIVES_OPT_IN = "click_extra_enable_exec_directives"
"""Name of the ``conf.py`` config flag that gates every code-execution directive.

Default is ``False``. A project that adds ``click_extra.sphinx`` to its
``extensions`` list gets the ANSI Pygments formatter and the GitHub-alerts
converter unconditionally, but does *not* gain access to either the
``click:*`` or the ``python:*`` directive families until the maintainer
opts in explicitly. Both families ``exec`` user-supplied Python at build
time with full Sphinx-process privileges; gating them behind a single
explicit flag keeps a transitive import or a doc-only pull request from
silently expanding the build's attack surface.
"""


def _register_exec_directives(app: Sphinx, config: Config) -> None:
    """Register the ``click:*`` and ``python:*`` directives if opted in.

    Connected to the ``config-inited`` event so the user's ``conf.py``
    value is merged before this runs. Without the opt-in, neither
    :class:`~click_extra.sphinx.click.ClickDomain` nor
    :class:`~click_extra.sphinx.python.PythonDomain` is registered:
    referencing any of their directives in a document raises an
    "Unknown directive type" warning, exactly as if the extension were
    not installed.

    .. danger::
        Both directive families execute arbitrary Python at build time
        with the full privileges of the Sphinx process: filesystem,
        network, environment variables, secrets. Auto-enabling them on
        every project that imports ``click_extra.sphinx`` (transitively
        or otherwise) would silently expand the attack surface of every
        consumer. See ``docs/sphinx.md`` for the full trust boundary.
    """
    if not getattr(config, EXEC_DIRECTIVES_OPT_IN, False):
        logger.info(
            "click_extra.sphinx: click:* and python:* directives are "
            "disabled. Set %s = True in conf.py to enable build-time "
            "code execution. See docs/sphinx.md for security implications.",
            EXEC_DIRECTIVES_OPT_IN,
        )
        return

    app.add_domain(ClickDomain)
    app.connect("doctree-read", cleanup_runner)
    app.add_domain(PythonDomain)
    app.connect("doctree-read", cleanup_python_runner)


def setup(app: Sphinx) -> ExtensionMetadata:
    """Register extensions to Sphinx.

    Always-on features (no execution surface):

    - The ANSI-capable HTML formatter for Pygments (replaces
      ``sphinx.highlighting.PygmentsBridge`` with one that renders ANSI
      colors in code blocks).
    - GitHub-flavored alert syntax (``> [!NOTE]``, etc.) in *included*
      and regular *source* files, converted to MyST/reST admonitions.

    Opt-in features (gated behind ``click_extra_enable_exec_directives``):

    - ``click:source`` / ``click:run`` to define and execute Click CLIs
      at build time.
    - ``python:source`` / ``python:run`` to execute arbitrary Python at
      build time and render its source or captured ``stdout``.
    - ``python:render`` / ``python:render-myst`` / ``python:render-rst``
      to execute arbitrary Python and parse the captured ``stdout`` as
      live document content.

    All directives in the opt-in group execute user-supplied Python with
    the same privileges as the Sphinx process. They are therefore
    disabled by default. Set ``click_extra_enable_exec_directives = True``
    in ``conf.py`` to register them.

    .. caution::
        This function forces the Sphinx app to use
        ``sphinx.highlighting.PygmentsBridge`` instead of the default
        HTML formatter to add support for ANSI colors in code blocks.
    """
    # Set Sphinx's default HTML formatter to an ANSI capable one.
    PygmentsBridge.html_formatter = AnsiHtmlFormatter

    # Declare the single opt-in flag covering both directive families.
    # The `config-inited` callback below registers the domains only if
    # the project's conf.py opts in. Default is `False`: build-time
    # arbitrary Python execution is off unless explicitly turned on.
    app.add_config_value(EXEC_DIRECTIVES_OPT_IN, False, "env", types=[bool])
    app.connect("config-inited", _register_exec_directives)

    # Register GitHub alerts converter.
    app.connect("source-read", convert_github_alerts)
    app.connect("include-read", convert_github_alerts)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
