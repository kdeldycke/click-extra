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

A project that adds `click_extra.sphinx` to its `extensions` list and
declares one or more entries in `click_extra_manpages` gets its Click
command tree(s) emitted as `.1` files into `<outdir>/<output_dir>/` on
every HTML build, with no project-local helper script. Pages mirror what
{func}`click_extra.man_page.write_manpages` produces from a CLI invocation,
so the docs site, the release pipeline, and downstream packagers all share
one generator.

When `mandoc` or `groff` is available on `PATH`, each `.1` file is
also rendered to a browser-viewable `.html` sibling. Browsers download
raw `.1` files rather than display them, so the HTML pass is what makes
Sphinx's `:manpage:` role useful when `manpages_url` points at this
hook's output.

The hook only fires for HTML-class builders (`html`, `dirhtml`,
`singlehtml`). Non-HTML builders (`linkcheck`, `man`, `epub`,
`coverage`, etc.) skip it: they typically have different output
semantics, and writing roff into a `linkcheck` `output/` directory
serves no purpose.

Configuration shape::

    click_extra_manpages = [
        {
            "script": "meta_package_manager.cli:mpm",  # required
            "prog_name": "mpm",  # optional, see below
            "output_dir": "man",  # optional, defaults to "man"
            "render_html": True,  # optional, see below
        },
    ]

* `script` is resolved by {func}`click_extra.cli_wrapper.resolve_target_command`
  exactly as it would be from the `click-extra man` CLI: a
  `console_scripts` entry-point name, a `module:function` path, a
  `.py` file, or a plain module name.
* `prog_name` is the basename used for both the man-page `.TH` header
  and the generated filenames. When omitted, it falls back to the resolved
  Click command's own `name` attribute (`mpm` for the
  `meta_package_manager.cli:mpm` target), matching the default the
  `click-extra man --output-dir` CLI uses.
* `output_dir` is a relative path under `app.outdir`. It is created
  on demand and reused across builds.
* `render_html` toggles the HTML sibling pass. Defaults to `True`.
  When no renderer is on `PATH`, the build still produces the `.1`
  files and logs a single info-level notice; set `render_html` to
  `False` to suppress that notice.

An empty (or absent) `click_extra_manpages` list disables the feature,
which is the default for every project pulling in the extension.

Cross-referencing the generated pages from prose
================================================

To make ``:manpage:`myprog(1)``` resolve to the HTML sibling this hook
emits, set Sphinx's `manpages_url` to the same `output_dir`::

    manpages_url = "man/{page}.{section}.html"

Sphinx's role provides ``{page}``, ``{section}`` and ``{path}``
placeholders; the file layout produced here is ``{page}.{section}`` plus
the optional `.html` extension, so the template above matches every
file regardless of how deep the subcommand tree goes.
"""

from __future__ import annotations

import posixpath
import shutil
import subprocess
from pathlib import Path

from docutils import nodes
from sphinx.directives import SphinxDirective
from sphinx.errors import NoUri
from sphinx.util import logging
from sphinx.util.osutil import relative_uri

from ..cli_wrapper import resolve_target_command
from ..man_page import (
    iter_command_contexts,
    iter_inline_literals,
    write_manpages,
)
from ..parameters import full_short_help

TYPE_CHECKING = False
if TYPE_CHECKING:
    from click import Command
    from sphinx.application import Sphinx


logger = logging.getLogger(__name__)


MANPAGES_CONFIG_KEY = "click_extra_manpages"
"""Name of the `conf.py` config flag holding the man-page emit list."""


DEFAULT_OUTPUT_DIR = "man"
"""Subdirectory under `app.outdir` where `.1` files land when the
caller omits the `output_dir` entry. Picked to match the URL fragment
projects typically publish their man pages under
(like `https://example.com/<project>/man/<cli>.1`)."""


HTML_BUILDER_NAMES = frozenset({"html", "dirhtml", "singlehtml"})
"""Builder names that get the man-page emit hook.

Restricted to HTML-family builders because they are the ones whose output
directory becomes the published docs site. Other builders (`linkcheck`,
`man`, `epub`, `coverage`) have different output semantics, and
writing roff into their build trees would either be redundant or
confusing."""


HTML_RENDERERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mandoc", ("-Thtml",)),
    ("groff", ("-Thtml", "-mandoc")),
)
"""External roff → HTML renderers, tried in order.

`mandoc` is preferred: its HTML output ships semantic `id` anchors on
every section and option (`#NAME`, `#SYNOPSIS`, `#config`…), which
makes deep-linking from prose work. `groff -Thtml -mandoc` is the GNU
fallback. If neither is on `PATH`, the HTML pass is skipped and only
the `.1` files are emitted.
"""


_RENDERER_TIMEOUT_S = 30
"""Per-file ceiling on the renderer invocation. mandoc finishes a typical
CLI page in under 100 ms; the timeout exists to bound damage from a
pathological page or a hung external process."""


_ROFF_PROBE = ".TH TEST 1\n.SH NAME\ntest \\- probe\n"
"""Minimal roff source used to verify a renderer actually produces output.

Some environments install the renderer binary but not the HTML support
package (like `groff` without `groff-html` on Debian/Ubuntu ARM
runners). A bare `shutil.which` check would accept such a broken install
and later produce zero HTML files. The probe catches this early so the
caller can fall through to the next candidate.
"""


def _find_renderer() -> tuple[str, tuple[str, ...]] | None:
    """Locate the first available roff → HTML renderer on `PATH`.

    Returns `(executable, extra_argv)` so the caller can append a file
    path and run it. Returns `None` when no candidate is available or
    when the candidate is installed but cannot produce HTML output (like
    `groff` present but `groff-html` absent).

    A quick probe with a trivial roff snippet guards against the latter
    case: if the renderer exits non-zero or produces empty output, it is
    treated as absent.
    """
    for name, extra in HTML_RENDERERS:
        path = shutil.which(name)
        if not path:
            continue
        # Verify the renderer actually works rather than just existing.
        try:
            result = subprocess.run(
                [path, *extra],
                input=_ROFF_PROBE,
                capture_output=True,
                text=True,
                check=True,
                timeout=_RENDERER_TIMEOUT_S,
            )
        except (subprocess.SubprocessError, OSError):
            continue
        if result.stdout.strip():
            return path, extra
    return None


def _render_html(renderer: tuple[str, tuple[str, ...]], roff_path: Path) -> str | None:
    """Run `renderer` on `roff_path` and return its captured `stdout`.

    Returns `None` if the subprocess fails for any reason. Failure is
    logged at warning level but does not abort the build: a broken HTML
    pass on one page must not lose the rest of the docs.
    """
    executable, extra = renderer
    try:
        result = subprocess.run(
            [executable, *extra, str(roff_path)],
            capture_output=True,
            text=True,
            check=True,
            timeout=_RENDERER_TIMEOUT_S,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning(
            "click_extra.sphinx: %s failed on %s: %s",
            Path(executable).name,
            roff_path.name,
            exc,
        )
        return None
    return result.stdout


def _emit_manpages(app: Sphinx) -> None:
    """Walk `click_extra_manpages` and write each tree under `app.outdir`.

    No-ops for non-HTML builders and for an empty config list. Errors
    resolving a single entry are logged but do not abort the build, so
    one misconfigured entry cannot derail an otherwise-good docs deploy.

    For every emitted `.1` file, also write a browser-viewable `.html`
    sibling when the entry opts in (default) and a renderer is on
    `PATH`. The renderer is looked up once per build, so a project with
    several entries pays the `shutil.which` cost a single time.
    """
    if app.builder.name not in HTML_BUILDER_NAMES:
        return

    entries = getattr(app.config, MANPAGES_CONFIG_KEY, None) or ()
    if not entries:
        return

    renderer = _find_renderer()
    renderer_notice_logged = False

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

        render_html = entry.get("render_html", True)
        if not render_html:
            continue
        if renderer is None:
            # Tell the user once per build why no HTML was produced.
            # Suppressed when the user opts out explicitly via
            # `render_html: False` because they did not ask for it.
            if not renderer_notice_logged:
                logger.info(
                    "click_extra.sphinx: no roff renderer found on PATH "
                    "(tried %s); skipping HTML man-page rendering. Set "
                    "render_html=False to suppress this notice.",
                    ", ".join(name for name, _ in HTML_RENDERERS),
                )
                renderer_notice_logged = True
            continue

        html_written = 0
        for roff_path in written:
            html = _render_html(renderer, roff_path)
            if html is None:
                continue
            roff_path.with_suffix(roff_path.suffix + ".html").write_text(
                html, encoding="utf-8"
            )
            html_written += 1
        logger.info(
            "click_extra.sphinx: rendered %d HTML man page(s) for %r with %s",
            html_written,
            prog_name,
            Path(renderer[0]).name,
        )


MANPAGE_LIST_DIRECTIVE = "click-extra-manpages"
"""Name of the directive that renders an auto-generated index of every
man page declared in {data}`MANPAGES_CONFIG_KEY`. The hyphenated form
mirrors the `click_extra_manpages` config key it surfaces."""


_MANPAGE_URI_ATTRIBUTE = "click_extra_manpage_uri"
"""Node attribute carrying a man page's URI relative to the build root.

The `href` a reader needs depends on where the builder publishes the page
hosting the directive: `html` writes a nested document to `<docname>.html`,
`dirhtml` writes `<docname>/index.html` one directory deeper, and `singlehtml`
folds every document into one page at the root. So the directive stamps the
build-root-relative URI here and `_rebase_manpage_links` rewrites it into a
page-relative one at write time.

Resolving it in the directive instead would freeze one builder's layout into
the pickled doctree, and a build reusing that cache never re-runs the
directive: an `html` build followed by a `dirhtml` build sharing a doctree
directory would publish the `html` links."""


class ManpageListDirective(SphinxDirective):
    """Render a bullet list with one link per emitted man page.

    The directive walks every entry in {data}`MANPAGES_CONFIG_KEY` and,
    for each, calls {func}`~click_extra.man_page.iter_command_contexts`
    to discover the (sub)command tree. Each list item links to the
    corresponding `.1.html` file written by the emit hook.

    Link targets are stamped as build-root-relative URIs and rebased
    against the enclosing page by `_rebase_manpage_links`, so the list
    works whether it appears at the docs root or in a nested page. The
    directive takes no arguments and no content: it surfaces whatever
    the config declares at the time the doc is built.
    """

    has_content = False
    required_arguments = 0
    optional_arguments = 0

    def run(self) -> list[nodes.Node]:
        entries = getattr(self.config, MANPAGES_CONFIG_KEY, None) or ()
        result: list[nodes.Node] = []
        for index, entry in enumerate(entries):
            script = entry.get("script")
            if not script:
                continue
            # Same resilience contract as `_emit_manpages`: a single
            # broken entry must not break the doc page that hosts the
            # directive. Log and move on.
            try:
                cmd, _ = resolve_target_command(script)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "click_extra.sphinx: %s directive cannot resolve "
                    "%s[%d] script %r: %s",
                    MANPAGE_LIST_DIRECTIVE,
                    MANPAGES_CONFIG_KEY,
                    index,
                    script,
                    exc,
                )
                continue
            output_dir = entry.get("output_dir") or DEFAULT_OUTPUT_DIR
            prog_name = entry.get("prog_name") or cmd.name or script
            result.append(self._render_entry(cmd, prog_name, output_dir))
        return result

    def _render_entry(
        self,
        cmd: Command,
        prog_name: str,
        output_dir: str,
    ) -> nodes.bullet_list:
        """Build the bullet list of links for one `click_extra_manpages`
        entry's command tree.
        """
        list_node = nodes.bullet_list()
        for path, sub_cmd, _ctx in iter_command_contexts(cmd, prog_name):
            name = "-".join(path)
            url = posixpath.join(output_dir, f"{name}.1.html")

            # Seed `refuri` with the build-root-relative URI so the node is
            # renderable on its own, then let `_rebase_manpage_links` rewrite
            # it for the page the builder is about to write.
            ref = nodes.reference("", "", refuri=url)
            ref[_MANPAGE_URI_ATTRIBUTE] = url
            ref += nodes.literal(text=f"{name}(1)")

            para = nodes.paragraph()
            para += ref
            short_help = full_short_help(sub_cmd)
            if short_help:
                para += nodes.Text(" — ")
                # Translate any reST inline literal (`X`) in the help
                # text to a `nodes.literal` so it renders with the
                # docs code font instead of leaking through as raw
                # backticks.
                for segment, is_literal in iter_inline_literals(short_help):
                    if is_literal:
                        para += nodes.literal(text=segment)
                    else:
                        para += nodes.Text(segment)

            item = nodes.list_item()
            item += para
            list_node += item
        return list_node


def _rebase_manpage_links(app: Sphinx, doctree: nodes.document, docname: str) -> None:
    """Rewrite every man-page link relative to the page being written.

    Nodes stamped with `_MANPAGE_URI_ATTRIBUTE` carry a build-root-relative
    URI; this rebases each one against the URI the builder assigns to
    `docname`. The rebasing is delegated to Sphinx's own
    `sphinx.util.osutil.relative_uri`, which reads each layout the way the
    builder means it: a trailing slash for `dirhtml`, a bare fragment for
    `singlehtml`.

    Runs on every written page rather than once at parse time, so links stay
    correct when a doctree cache is shared between builders.
    """
    try:
        page_uri = app.builder.get_target_uri(docname)
    except NoUri:
        # `latex` and `texinfo` publish no URI for a document outside their
        # own tree. Leave the seeded build-root-relative URI in place.
        return
    for node in doctree.findall(nodes.reference):
        target = node.get(_MANPAGE_URI_ATTRIBUTE)
        if target:
            node["refuri"] = relative_uri(page_uri, target)


def setup(app: Sphinx) -> None:
    """Register the man-page hooks and the index directive on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to
    list `"click_extra.sphinx"` in their `extensions`. The hooks are
    a no-op when `click_extra_manpages` is unset or empty, and the
    directive renders nothing in that case.
    """
    app.add_config_value(MANPAGES_CONFIG_KEY, default=[], rebuild="env", types=[list])
    app.connect("builder-inited", _emit_manpages)
    app.connect("doctree-resolved", _rebase_manpage_links)
    app.add_directive(MANPAGE_LIST_DIRECTIVE, ManpageListDirective)
