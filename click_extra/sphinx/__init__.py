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

```{note}
The MkDocs counterpart lives in {mod}`click_extra.mkdocs`, which achieves the same
ANSI color rendering by patching `pymdownx.highlight`'s formatter classes.
```
"""

from __future__ import annotations

from .._utils import missing_extra_message

try:
    import sphinx  # noqa: F401
except ImportError as err:
    raise ImportError(missing_extra_message("sphinx", subject="This module")) from err

from packaging.version import Version
from sphinx.highlighting import PygmentsBridge
from sphinx.util import logging

from .. import __version__
from ..blocks import (
    marker_res as marker_res,
    replace_region as replace_region,
    update_blocks as update_blocks,
)
from ..pygments import AnsiHtmlFormatter
from . import manpages, matrix, todos
from .alerts import convert_github_alerts
from .click import ClickDomain, cleanup_runner
from .python import (
    PythonDomain,
    cleanup_python_runner,
    rewrite_python_mirror_regions,
)

try:
    import myst_parser
except ImportError:
    # The `sphinx` extra does not declare myst-parser and Sphinx does not pull it
    # in, so a reST-only project has none installed. Keep this module importable
    # for it: setup() then skips the GitHub-alerts converter, which would emit
    # `:::{note}` fences no parser is there to render.
    myst_parser = None  # type: ignore[assignment]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.config import Config
    from sphinx.util.typing import ExtensionMetadata


logger = logging.getLogger(__name__)


MYST_NATIVE_ALERTS_VERSION = Version("5.1.0")
"""First `myst-parser` release that ships the native `"alert"` syntax
extension.

Below this version, {mod}`click_extra.sphinx.alerts` patches GitHub alert
syntax into MyST admonitions via a `source-read` / `include-read`
hook. At or above this version, the converter is skipped at
{func}`setup` time and projects should add `"alert"` to
`myst_enable_extensions` instead. A project with no `myst-parser`
installed writes no MyST document, so the converter is skipped there too.
"""


EXEC_DIRECTIVES_OPT_IN = "click_extra_enable_exec_directives"
"""Name of the `conf.py` config flag that gates every code-execution directive.

Default is `False`. A project that adds `click_extra.sphinx` to its
`extensions` list gets the ANSI Pygments formatter unconditionally, plus
the GitHub-alerts converter when `myst-parser` is below
{data}`MYST_NATIVE_ALERTS_VERSION` (see {mod}`.alerts` for the deprecation
rationale), but does *not* gain access to either the `click:*` or the
`python:*` directive families until the maintainer opts in explicitly.
Both families `exec` user-supplied Python at build time with full
Sphinx-process privileges; gating them behind a single explicit flag keeps
a transitive import or a doc-only pull request from silently expanding
the build's attack surface.
"""


SCREENSHOT_DIR_CONFIG = "click_extra_screenshot_dir"
"""Name of the `conf.py` value locating the directory `click:run` writes captures to.

A path relative to the documentation source directory, holding the SVG a
`click:run` block names with its `:screenshot:` option. Defaults to `assets`,
matching where a Sphinx project conventionally keeps the images its pages embed,
and where a README pointing at the repository finds them.
"""

SCREENSHOT_PRESET_CONFIG = "click_extra_screenshot_preset"
"""Name of the `conf.py` value naming the terminal every capture is drawn as.

One of {data}`~click_extra.screenshot_presets.PRESETS`, applied to each
`click:run` block whose `:screenshot:` does not name a preset of its own. Empty
by default, which keeps the renderer's neutral window: a project wanting all of
its captures to look like the same desktop states it once here instead of on
every block.
"""

SCREENSHOT_SYNTAX_STYLE_CONFIG = "click_extra_screenshot_syntax_style"
"""Name of the `conf.py` value coloring every capture drawn from source code.

One of the [Pygments styles](https://pygments.org/styles/), applied to each
source block whose `:screenshot:` does not name a
`:screenshot-syntax-style:` of its own. Empty by default, which takes the style
each chrome is drawn for, see
{data}`~click_extra.snippet.DEFAULT_SYNTAX_STYLES`. Unused by a block picturing
what a command printed, whose colors that command already chose.
"""

SCREENSHOT_WATERMARK_CONFIG = "click_extra_screenshot_watermark"
"""Name of the `conf.py` value crediting every capture a `click:run` writes.

Empty by default, where the `screenshot` command credits click-extra: a capture
written by a documentation build is rewritten and committed on every build, so a
mark naming a release would rewrite every image the day that release changes,
and the page carrying the image already says what drew it. A project wanting one
anyway states the text here, or per block with `:screenshot-watermark:`.
"""

RUN_CAPTURE_CONFIG = "click_extra_run_capture"
"""Name of the `conf.py` value selecting the stream-capture mode for the CLIs that
`click:run` and `click:tree` execute.

Maps to the `capture` parameter of Click's {class}`~click.testing.CliRunner`,
`"sys"` or `"fd"` (added in Click 8.4). Defaults to `"fd"` so a command writing
through `sys.stdout.fileno()` is captured at the file-descriptor level and renders,
instead of aborting the build with {exc}`io.UnsupportedOperation`. Ignored on Click
releases older than 8.4, which lack the parameter.
"""


def _register_exec_directives(app: Sphinx, config: Config) -> None:
    """Register the `click:*` and `python:*` directives if opted in.

    Connected to the `config-inited` event so the user's `conf.py`
    value is merged before this runs. Without the opt-in, neither
    {class}`~click_extra.sphinx.click.ClickDomain` nor
    {class}`~click_extra.sphinx.python.PythonDomain` is registered:
    referencing any of their directives in a document raises an
    "Unknown directive type" warning, exactly as if the extension were
    not installed.

    ```{danger}
    Both directive families execute arbitrary Python at build time
    with the full privileges of the Sphinx process: filesystem,
    network, environment variables, secrets. Auto-enabling them on
    every project that imports `click_extra.sphinx` (transitively
    or otherwise) would silently expand the attack surface of every
    consumer. See `docs/sphinx.md` for the full trust boundary.
    ```
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
    # Refresh `python:render :mirror:` regions in memory before the document
    # is parsed, so builds always render fresh output even when the committed
    # region is stale (the disk copy is refreshed offline by the click-extra
    # refresh-directives command). Priority 100 (below the default 500) runs
    # it ahead of any other source-read transformer (like the GitHub-alerts
    # converter) so generated content participates in later transforms.
    app.connect("source-read", rewrite_python_mirror_regions, priority=100)


def setup(app: Sphinx) -> ExtensionMetadata:
    """Register extensions to Sphinx.

    Always-on features (no execution surface):

    - The ANSI-capable HTML formatter for Pygments (replaces
      `sphinx.highlighting.PygmentsBridge` with one that renders ANSI
      colors in code blocks).
    - GitHub-flavored alert syntax (`> [!NOTE]`, etc.) in *included*
      and regular *source* files, converted to MyST/reST admonitions.
      Registered only when the installed `myst-parser` is below
      {data}`MYST_NATIVE_ALERTS_VERSION` (`5.1.0`). On newer versions,
      the converter is skipped and a one-shot info message points users
      at `myst-parser`'s native `"alert"` extension; with no `myst-parser`
      installed it is skipped without a message. See
      {mod}`click_extra.sphinx.alerts` for the deprecation plan.
    - The `matrix` directive, which renders a package's compatibility grid
      (``{matrix} python`` or ``{matrix} <distribution>``) from its git tag
      history. It runs a canned generator rather than user-supplied Python, so
      it carries no execution surface and needs no opt-in. See
      {mod}`click_extra.sphinx.matrix`.
    - Deduplication of the `todolist` page, which `sphinx.ext.todo` fills
      with one entry per *rendering* of a `{todo}` directive rather than one
      per directive. Inert on a project that enables neither the extension
      nor a `todolist`, and switched off with
      {data}`click_extra.sphinx.todos.DEDUPE_TODOS_CONFIG`. See
      {mod}`click_extra.sphinx.todos`.

    Opt-in features (gated behind `click_extra_enable_exec_directives`):

    - `click:source` / `click:run` to define and execute Click CLIs
      at build time.
    - `python:source` / `python:run` to execute arbitrary Python at
      build time and render its source or captured `stdout`.
    - `python:render` / `python:render-myst` / `python:render-rst`
      to execute arbitrary Python and parse the captured `stdout` as
      live document content.

    All directives in the opt-in group execute user-supplied Python with
    the same privileges as the Sphinx process. They are therefore
    disabled by default. Set `click_extra_enable_exec_directives = True`
    in `conf.py` to register them.

    ```{caution}
    This function forces the Sphinx app to use
    `sphinx.highlighting.PygmentsBridge` instead of the default
    HTML formatter to add support for ANSI colors in code blocks.
    ```
    """
    # Set Sphinx's default HTML formatter to an ANSI capable one.
    PygmentsBridge.html_formatter = AnsiHtmlFormatter

    # Declare the single opt-in flag covering both directive families.
    # The `config-inited` callback below registers the domains only if
    # the project's conf.py opts in. Default is `False`: build-time
    # arbitrary Python execution is off unless explicitly turned on.
    app.add_config_value(EXEC_DIRECTIVES_OPT_IN, False, "env", types=[bool])
    # Stream-capture mode for executed click:run/click:tree CLIs (see click.py).
    app.add_config_value(RUN_CAPTURE_CONFIG, "fd", "env", types=[str])
    # Where a `click:run` `:screenshot:` capture is written (see click.py).
    app.add_config_value(SCREENSHOT_DIR_CONFIG, "assets", "env", types=[str])
    # Terminal every capture is drawn as, unless a block says otherwise.
    app.add_config_value(SCREENSHOT_PRESET_CONFIG, "", "env", types=[str])
    # Pygments style every source capture is colored with (see snippet.py).
    app.add_config_value(SCREENSHOT_SYNTAX_STYLE_CONFIG, "", "env", types=[str])
    # Credit line every capture carries, off unless a project asks for one.
    app.add_config_value(SCREENSHOT_WATERMARK_CONFIG, "", "env", types=[str])
    app.connect("config-inited", _register_exec_directives)

    # Wire the man-page emit hook (see manpages.py). No-op until a project
    # declares one or more entries in `click_extra_manpages`.
    manpages.setup(app)

    # Register the always-on `matrix:*` compatibility-matrix directives (see
    # matrix.py). Unlike the `click:*` / `python:*` families, these run a
    # canned generator against the documented project's git history rather
    # than user-supplied Python, so they need no exec opt-in.
    matrix.setup(app)

    # Collapse the duplicate `todolist` entries autodoc's repeated docstring
    # renderings produce (see todos.py). Inert unless the project enables
    # `sphinx.ext.todo` and writes a `todolist`.
    todos.setup(app)

    # Register GitHub alerts converter only when myst-parser predates
    # the native "alert" syntax extension (added in 5.1.0). On newer
    # versions, log a migration notice and skip the converter:
    # projects should add "alert" to myst_enable_extensions to use
    # myst-parser's native rendering instead. With no myst-parser at all
    # there is no MyST document to convert, so it is skipped silently.
    if myst_parser is not None:
        if Version(myst_parser.__version__) < MYST_NATIVE_ALERTS_VERSION:
            app.connect("source-read", convert_github_alerts)
            app.connect("include-read", convert_github_alerts)
        else:
            logger.info(
                "click_extra.sphinx: skipping the GitHub alerts converter "
                "(myst-parser %s ships the native 'alert' syntax extension). "
                "Add 'alert' to myst_enable_extensions to render "
                "'> [!NOTE]' blockquotes as Sphinx admonitions.",
                myst_parser.__version__,
            )

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
