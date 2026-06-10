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
"""Sphinx integration to render roff man pages alongside the HTML build.

A project that adds ``click_extra.sphinx`` to its ``extensions`` list and
declares one or more entries in ``click_extra_manpages`` gets its Click
command tree(s) emitted as ``.1`` files into ``<outdir>/<output_dir>/`` on
every HTML build, with no project-local helper script. Pages mirror what
:func:`click_extra.man_page.write_manpages` produces from a CLI invocation,
so the docs site, the release pipeline, and downstream packagers all share
one generator.

The hook only fires for HTML-class builders (``html``, ``dirhtml``,
``singlehtml``). Non-HTML builders (``linkcheck``, ``man``, ``epub``,
``coverage``, etc.) skip it: they typically have different output
semantics, and writing roff into a ``linkcheck`` ``output/`` directory
serves no purpose.

Configuration shape::

    click_extra_manpages = [
        {
            "script": "meta_package_manager.cli:mpm",  # required
            "prog_name": "mpm",  # optional, see below
            "output_dir": "man",  # optional, defaults to "man"
        },
    ]

* ``script`` is resolved by :func:`click_extra.wrap.resolve_target_command`
  exactly as it would be from the ``click-extra man`` CLI: a
  ``console_scripts`` entry-point name, a ``module:function`` path, a
  ``.py`` file, or a plain module name.
* ``prog_name`` is the basename used for both the man-page ``.TH`` header
  and the generated filenames. When omitted, it falls back to the resolved
  Click command's own ``name`` attribute (``mpm`` for the
  ``meta_package_manager.cli:mpm`` target), matching the default the
  ``click-extra man --output-dir`` CLI uses.
* ``output_dir`` is a relative path under ``app.outdir``. It is created
  on demand and reused across builds.

An empty (or absent) ``click_extra_manpages`` list disables the feature,
which is the default for every project pulling in the extension.
"""

from __future__ import annotations

from pathlib import Path

from sphinx.util import logging

from ..man_page import write_manpages
from ..wrap import resolve_target_command

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx


logger = logging.getLogger(__name__)


MANPAGES_CONFIG_KEY = "click_extra_manpages"
"""Name of the ``conf.py`` config flag holding the man-page emit list."""


DEFAULT_OUTPUT_DIR = "man"
"""Subdirectory under ``app.outdir`` where ``.1`` files land when the
caller omits the ``output_dir`` entry. Picked to match the URL fragment
projects typically publish their man pages under
(e.g. ``https://example.com/<project>/man/<cli>.1``)."""


HTML_BUILDER_NAMES = frozenset({"html", "dirhtml", "singlehtml"})
"""Builder names that get the man-page emit hook.

Restricted to HTML-family builders because they are the ones whose output
directory becomes the published docs site. Other builders (``linkcheck``,
``man``, ``epub``, ``coverage``) have different output semantics, and
writing roff into their build trees would either be redundant or
confusing."""


def _emit_manpages(app: Sphinx) -> None:
    """Walk ``click_extra_manpages`` and write each tree under ``app.outdir``.

    No-ops for non-HTML builders and for an empty config list. Errors
    resolving a single entry are logged but do not abort the build, so
    one misconfigured entry cannot derail an otherwise-good docs deploy.
    """
    if app.builder.name not in HTML_BUILDER_NAMES:
        return

    entries = getattr(app.config, MANPAGES_CONFIG_KEY, None) or ()
    if not entries:
        return

    for index, entry in enumerate(entries):
        script = entry.get("script")
        if not script:
            logger.warning(
                "click_extra.sphinx: %s[%d] is missing the required "
                "'script' key; skipping entry.",
                MANPAGES_CONFIG_KEY,
                index,
            )
            continue

        output_dir = entry.get("output_dir") or DEFAULT_OUTPUT_DIR
        target = Path(app.outdir) / output_dir

        # The hook fires once per HTML build, so an unimportable script must
        # not abort the whole docs build: log and skip it instead.
        try:
            cmd, _ = resolve_target_command(script)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "click_extra.sphinx: cannot resolve %s[%d] script %r: %s",
                MANPAGES_CONFIG_KEY,
                index,
                script,
                exc,
            )
            continue

        prog_name = entry.get("prog_name") or cmd.name or script
        written = write_manpages(cmd, target, prog_name=prog_name)
        logger.info(
            "click_extra.sphinx: wrote %d man page(s) for %r into %s",
            len(written),
            prog_name,
            target,
        )


def setup(app: Sphinx) -> None:
    """Register the man-page emit hook on the Sphinx ``app``.

    Called from :func:`click_extra.sphinx.setup` so projects only need to
    list ``"click_extra.sphinx"`` in their ``extensions``. The hook is
    a no-op when ``click_extra_manpages`` is unset or empty.
    """
    app.add_config_value(MANPAGES_CONFIG_KEY, default=[], rebuild="env", types=[list])
    app.connect("builder-inited", _emit_manpages)
