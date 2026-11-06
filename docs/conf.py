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

from __future__ import annotations

import os
import tomllib
from datetime import date
from pathlib import Path

import click

import click_extra.config.option
from click_extra import ShowParamsOption
from click_extra.sphinx.announcement import years_since
from click_extra.sphinx.theme_docs import inject_slot_example_docstring

project_path = Path(__file__).parent.parent.resolve()

# Fetch general information about the project from pyproject.toml.
toml_path = project_path / "pyproject.toml"
toml_config = tomllib.loads(toml_path.read_text(encoding="UTF-8"))

# Redistribute pyproject.toml config to Sphinx.
project_id = toml_config["project"]["name"]
version = release = toml_config["project"]["version"]
author = ", ".join(author["name"] for author in toml_config["project"]["authors"])

# Canonical origin of the published site, read from the one place that declares
# it. The trailing slash is mandatory: Sphinx joins page paths onto it verbatim to
# build each `<link rel="canonical">`, and sphinx-sitemap concatenates it with
# every page link.
docs_site_url = toml_config["project"]["urls"]["Documentation"].rstrip("/") + "/"

# Title-case each word of the project ID.
project = " ".join(word.title() for word in project_id.split("-"))

# GitHub account owning the project. Factored out so a rename touches one line.
github_user = "kdeldycke"

# Whole years since `0.0.1` (2021-10-18), the oldest entry of the changelog, for
# the announcement banner below.
maintained_years = years_since(date(2021, 10, 18))

# Addons.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    # Adds a copy button to code blocks.
    "sphinx_copybutton",
    # Emits sitemap.xml from html_baseurl, so crawlers find the API reference as
    # well as the guide pages.
    "sphinx_sitemap",
    "sphinx_design",
    "sphinxext.opengraph",
    "myst_parser",
    # myst_docstrings hooks autodoc-process-docstring at priority 400 (vs default
    # 500) so it always runs before sphinx_autodoc_typehints. Listing it first
    # makes the intent explicit; the extension enforces this at load time.
    "click_extra.sphinx.myst_docstrings",
    "sphinx_autodoc_typehints",
    "click_extra.sphinx",
    "sphinxcontrib.mermaid",
    # jQuery must be listed explicitly: sphinx-datatables only activates it
    # from a html-page-context callback, too late for the jquery.js static
    # file to be registered and copied, leaving `$` undefined at runtime.
    "sphinxcontrib.jquery",
    "sphinx_datatables",
]

# Applies to every table carrying the (default) `sphinx-datatable` class:
# currently only the binaries catalog. An empty `order` preserves the CSV's
# newest-first row order on load instead of DataTables' default first-column
# ascending sort; the page length accommodates one release's worth of
# binaries per page with room to spare. The render callback appends a
# relative hint ("9 days ago") to the Released column (index 2 in
# repomatic.release.binaries_page.CSV_HEADERS) at display time only, so sorting and
# searching keep operating on the raw ISO dates and the generated CSV stays
# free of hints that would go stale between releases. Passed as a raw JS
# string because a JSON dict cannot carry the function. Raw string: the JS
# regex's backslashes are not Python escapes.
datatables_options = r"""
{
    "order": [],
    "pageLength": 25,
    "columnDefs": [
        {
            "targets": 2,
            "render": function (data, type, row) {
                if (type !== "display" || !data) {
                    return data;
                }
                // Cells arrive as rendered HTML (<p>2026-07-02</p>), so
                // extract the date instead of parsing the markup.
                const match = /\d{4}-\d{2}-\d{2}/.exec(data);
                if (!match) {
                    return data;
                }
                const days = Math.floor(
                    (Date.now() - Date.parse(match[0])) / 86400000);
                if (!isFinite(days)) {
                    return data;
                }
                let hint;
                if (days <= 0) {
                    hint = "today";
                } else if (days === 1) {
                    hint = "a day ago";
                } else if (days < 30) {
                    hint = days + " days ago";
                } else if (days < 350) {
                    const months = Math.round(days / 30.44);
                    hint = months === 1 ? "a month ago" : months + " months ago";
                } else {
                    const years = Math.round(days / 365.25);
                    hint = years === 1 ? "a year ago" : years + " years ago";
                }
                // Inject inside the paragraph so the hint stays on the
                // same line as the date.
                const label = " (" + hint + ")";
                return data.includes("</p>")
                    ? data.replace("</p>", label + "</p>")
                    : data + label;
            }
        }
    ]
}
"""

# Opt into the click:* and python:* directive families. Both execute
# arbitrary Python at build time; see docs/sphinx.md for the security
# trust boundary.
click_extra_enable_exec_directives = True

# Emit roff man pages for click-extra's own CLI into <outdir>/man/ on every
# HTML build. See click_extra/sphinx/manpages.py. Mirrors the
# `[tool.repomatic] manpages.script` entry of pyproject.toml, which builds the
# release asset.
click_extra_manpages = [
    {
        "script": "click_extra.cli:demo",
        "prog_name": "click-extra",
    },
]

# Resolve `:manpage:`click-extra(1)`` (and every subcommand page) to the
# HTML siblings the hook above emits. The {page}.{section}.html template
# matches whether the page is the root command or a deeply nested
# subcommand.
manpages_url = "man/{page}.{section}.html"

# Only the syntax the documentation uses: `attrs_inline` for the `{l=toml}` of
# inline code, `substitution` for the `{{ name }}` below.
# https://myst-parser.readthedocs.io/en/latest/syntax/optional.html
myst_enable_extensions = [
    "alert",
    "attrs_inline",
    "fieldlist",
    "replacements",
    "smartquotes",
    "substitution",
]

# Substitutions exposed to MyST documents as ``{{ name }}``. Built from
# Python data so single-source-of-truth content (like the --params column
# registry) stays in sync between code and docs automatically.
myst_substitutions = {
    "show_params_columns_table": ShowParamsOption.render_doc_table(),
}
# Register a cross-reference target for every heading down to <h6>, so Markdown
# links of the form [text](other.md#heading-slug) resolve. Without this, MyST
# only resolves explicit (target)= anchors and emits best-effort hrefs that
# happen to work because docutils generates matching HTML ids: each one still
# raises a myst.xref_missing warning at build time.
myst_heading_anchors = 6
# Slugify headings exactly the way docutils derives HTML ids, so the anchors
# MyST resolves match the ids actually rendered in the page. The default
# GitHub-style slugifier keeps leading digits, "--" prefixes, dots and
# underscores that docutils strips or collapses (like "`--params` option",
# which docutils turns into "params-option"), which otherwise leaves every
# cross-reference to such a heading unresolved. The dotted-path string form (not
# the function object) keeps the config value picklable, so Sphinx can cache it
# between builds.
myst_heading_slug_func = "docutils.nodes.make_id"
# Allow the ```mermaid``` directive without curly braces (```{mermaid}```), see:
# https://github.com/mgaitan/sphinxcontrib-mermaid/issues/99#issuecomment-2339587001
myst_fence_as_directive = ["mermaid"]

# d3 zoom on every diagram. click_extra.sphinx keeps it off the inline class
# trees of `autoclasstree`, so the wheel scrolls the page past them.
mermaid_d3_zoom = True

exclude_patterns = ["_build", "_linkcheck", "html", "Thumbs.db", ".DS_Store"]

nitpicky = True

# Warning categories with no actionable fix. Each entry names a warning it
# silences and why that warning cannot be fixed at its source.
suppress_warnings = [
    # Example: docs/index.md:10: WARNING: Document headings start at H2, not H1
    # [myst.header]
    # Explanation: index.md is readme.md included whole, and the readme's sections
    # open at H2 because its title is the banner image. The rendered table of
    # contents is unaffected.
    "myst.header",
    # Example: docs/upstream.md:198: WARNING: duplicate label
    # upstream:[`click`](https://github.com/pallets/click), other instance in
    # docs/upstream.md [autosectionlabel.upstream]
    # Explanation: upstream.md repeats a project's heading under each section
    # that names it, so autosectionlabel labels it twice. Nothing references
    # those labels.
    "autosectionlabel.upstream",
]

# A fragment link that resolves nowhere fails the build: myst-parser only warns,
# then ships the link dead. A docstring `{todo}` that no page renders fails it
# too. See click_extra/sphinx/fail_on_warnings.py.
click_extra_fail_on_warnings = ["click_extra.todo_unrendered", "myst.xref_missing"]

# Anchor each changelog release on its version, like `#v10-1-1`, in place of a
# positional `#idN` that every release shifts. See click_extra/sphinx/changelog.py.
click_extra_release_anchors = True

# Cross-reference targets that legitimately have nothing to link to, so nitpicky
# mode would otherwise flood the build with "reference target not found". These
# are NOT broken refs in click-extra's own docstrings (those are fully qualified).
# click-extra re-exports click's and cloup's public classes as a drop-in
# replacement, so autodoc renders their upstream docstrings and type annotations
# here, which reference upstream-internal names and private types absent from any
# intersphinx inventory.
nitpick_ignore_regex = [
    # Packages whose documented names autodoc cannot link to. The docs fetch no
    # intersphinx inventory for docutils, mkdocs, pygments and sphinx. Cloup's
    # inventory sits behind a Cloudflare bot challenge (HTTP 429,
    # `cf-mitigated: challenge`, probed 2026-07-30), so Sphinx's intersphinx
    # fetcher cannot retrieve its objects.inv. extra-platforms has an inventory,
    # but it documents `Group` and `Trait` under other names than the
    # `extra_platforms.group.Group` and `extra_platforms.trait.Trait` that
    # autodoc renders.
    (r"py:.*", r"(cloup|docutils|extra_platforms|mkdocs|pygments|sphinx)\..*"),
    # Click internals not exposed in its public docs.
    (r"py:.*", r"click\.(testing|types|_\w+)\..*"),
    # Private (underscore-prefixed) symbols, in click-extra or upstream.
    (r"py:.*", r"(.*\.)?_[A-Za-z]\w*(\..*)?"),
    # Third-party types that only a few annotations name: the test helpers on the
    # tests page, and the `requests` request of click_extra.sphinx.linkcheck. Not
    # worth an inventory download on every build.
    (r"py:.*", r"(packaging|requests)\..*"),
]

# Names inherited from re-exported click/cloup docstrings. The bare ones resolve
# in their own upstream docs through the module context, which is lost when
# autodoc re-renders them under click-extra.
nitpick_ignore = [
    ("py:func", "object_type"),
    ("py:attr", "Context.obj"),
    ("py:attr", "Context.default_map"),
    ("py:meth", "Context.lookup_default"),
    ("py:meth", "Context.token_normalize_func"),
    ("py:attr", "multiple"),
    ("py:attr", "nargs"),
    ("py:meth", "fail"),
    ("py:class", "Constraint"),
    # cloup's SectionMixin docstring names `click.MultiCommand`, which current
    # Click keeps only as a private, undocumented alias.
    ("py:class", "click.MultiCommand"),
    # The Constraints page that cloup's option_group docstring links to exists
    # only in cloup's own documentation.
    ("doc", "/pages/constraints"),
    # pygments' inherited ``aliases`` attribute docstring.
    ("py:func", "get_formatter_by_name"),
    # click ParameterSource enum members are absent from click's inventory.
    ("py:attr", "click.ParameterSource.DEFAULT_MAP"),
    # click-extra's own classes that live in a submodule but are re-exported at the
    # package root. They are dropped from the root ``automodule:: click_extra`` (see
    # docs/click_extra.md) to avoid ambiguous cross-references, so their bare name
    # has no target when autodoc re-renders a re-exported class's docstring in the
    # root module context. The canonical entry stays under the defining submodule.
    ("py:class", "ColumnSpec"),
    ("py:class", "ConfigValidator"),
    ("py:class", "LogLevel"),
    # The two decorator protocols of click_extra.decorators: TYPE_CHECKING-only
    # names that autodoc renders in decorator_factory's annotations, with no
    # documentable target.
    ("py:class", "click_extra.decorators.CommandDecorator"),
    ("py:class", "click_extra.decorators.ParameterDecorator"),
    # The TYPE_CHECKING-only alias of click_extra.envvar that autodoc renders in
    # env_copy()'s signature, under the defining module and the package root.
    ("py:data", "TEnvVars"),
]

# Concatenates the docstrings of the class and the __init__ method.
autoclass_content = "both"
# Keep the same ordering as in original source code.
autodoc_member_order = "bysource"

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "click": ("https://click.palletsprojects.com", None),
    # The annotations of click_extra.pytest name pytest's public classes, like
    # the `pytest.ParameterSet` its decorator expanders return.
    "pytest": ("https://docs.pytest.org/en/stable", None),
}

# Prefix document path to section labels, to use:
# `path/to/file:heading` instead of just `heading`
autosectionlabel_prefix_document = True

# Where these pages are published, which is what makes Sphinx emit a
# `<link rel="canonical">` on each one. Without it there is no canonical tag at
# all, so a page served from a mirror would compete with its own original.
html_baseurl = docs_site_url
# sphinx-sitemap defaults to a `{lang}{version}{link}` layout meant for sites
# publishing several translations or versions side by side. This one publishes a
# single tree, so anything but the bare link yields sitemap entries that 404.
sitemap_url_scheme = "{link}"
# The generated navigation pages hold no content a crawler should index.
sitemap_excludes = ["genindex.html", "py-modindex.html", "search.html"]

# Theme config.
html_theme = "furo"
html_title = project
html_favicon = "assets/favicon.svg"
# Without this, sphinxext.opengraph falls back to the favicon for social
# previews, which scales poorly. The dark variant matches the social preview
# uploaded to the repository's settings, so a link to the docs and a link to the
# repository unfurl as the same card. Either would carry the mark: flat-shaded,
# it holds its own on a light background and a dark one alike. The path is
# relative to the site root, where its html_static_path entry below copies the
# file: Sphinx does not publish docs/assets/.
ogp_image = "_static/banner-gradient-dark.png"
# ogp_image is relative to ogp_site_url, not to the page. Without a site URL,
# sphinxext.opengraph emits the image path as-is, which social crawlers can't
# resolve since they only ever see the raw HTML.
ogp_site_url = docs_site_url
html_theme_options = {
    # Sidebar logo. Furo renders this pair as .only-light/.only-dark images that
    # follow its theme toggle. A single html_logo cannot: the wordmark of
    # assets/logo-square.svg drops to a 2.62:1 contrast ratio on the dark
    # sidebar. Furo resolves both names against _static/, hence their
    # html_static_path entries.
    "light_logo": "logo-square-light.png",
    "dark_logo": "logo-square-dark.png",
    "sidebar_hide_name": True,
    # Activates edit links.
    "source_repository": f"https://github.com/{github_user}/{project_id}",
    "source_branch": "main",
    "source_directory": "docs/",
    # Sits atop every page, so it stays a single line and leads with the track
    # record rather than pleading scarcity: how thin the maintenance is says
    # nothing to a reader who has not yet decided the project is worth funding.
    # The age is recomputed at build time, so the claim never goes stale. Each
    # call to action opens on its emoji, which gives the eye two markers to land
    # on in a line that is otherwise unbroken prose.
    "announcement": (
        f"{project} has been maintained for {maintained_years}+ years, and is "
        "free to use. You can help if you "
        "<strong><a class='reference external' "
        f"href='https://github.com/sponsors/{github_user}'>"
        "🤝 purchase business support</a></strong> or "
        "<strong><a class='reference external' "
        f"href='https://github.com/sponsors/{github_user}'>"
        "🫶 sponsor the project</a></strong>."
    ),
}

# Linkcheck configuration.
# GitHub renders issue comments, README tab anchors and blob line anchors with
# JavaScript, so the linkcheck builder cannot find them in the static HTML:
# skip anchor checks for the whole host instead of stacking per-anchor patterns.
linkcheck_anchors_ignore_for_url = [
    r"https://github\.com/",
]

# Some links time out the linkcheck bot intermittently; retry before reporting
# them as broken.
linkcheck_retries = 3

linkcheck_ignore = [
    # This site returns 403 to bots but is valid.
    r"https://docutils\.sourceforge\.io",
    # no-color.org and openclipart.org are valid but intermittently fail DNS
    # resolution or time out from CI runners. Also excluded from the lychee run
    # (see [tool.lychee] in pyproject.toml).
    r"https://no-color\.org",
    r"https://openclipart\.org",
    # shields.io intermittently answers a badge with 408 Request Timeout, or
    # times out, from CI runners. The lychee run in the same job still checks
    # every badge.
    r"https://img\.shields\.io/",
    # repology.org refuses the linkcheck builder's connections from CI runners,
    # while the lychee run in the same job checks its badge and page fine.
    r"https://repology\.org",
    # crates.io blocks automated link checkers.
    r"https://crates\.io/crates/.*",
    # VirusTotal analysis pages are a JS app that rate-limits bots, and the
    # binaries catalog links one per released binary. Also excluded from the
    # lychee run (see [tool.lychee] in pyproject.toml).
    r"https://www\.virustotal\.com/gui/.*",
    # Telemetry opt-out endpoint is slow and times out from CI.
    r"https://telemetry\.timseverien\.com/.*",
    # Hacker News rate-limits automated checkers with HTTP 429. Already excluded
    # from the lychee run (see [tool.lychee] in pyproject.toml).
    r"https://news\.ycombinator\.com/.*",
    # The HTML man pages these relative links point at are emitted only by the
    # html builder (see click_extra/sphinx/manpages.py); the linkcheck builder
    # skips that step, so the siblings are absent when linkcheck runs. They
    # resolve correctly in the published site.
    r"man/.+\.html",
]

# Footer content.
html_last_updated_fmt = "%Y-%m-%d"
copyright = f"{author} and contributors"
html_show_sphinx = False

# Do not publish a copy of every source document under `_sources/`: no page
# links to it, and the sources are the repository. `html_copy_source` gates the
# files and `html_show_sourcelink` the link, so both are set: a theme reading only
# the second would otherwise offer a link to files that are no longer there.
html_copy_source = False
html_show_sourcelink = False

# Individual files are copied to the root of _static/, which is where Furo looks
# for the light_logo/dark_logo pair, and where ogp_image points social crawlers.
# Listing docs/assets/ wholesale would drag every other asset along.
html_static_path = [
    "_static",
    "assets/banner-gradient-dark.png",
    "assets/logo-square-dark.png",
    "assets/logo-square-light.png",
]
html_css_files = ["custom.css"]

# Copy only the commands of a session block, without their prompt: `$ ` for a
# shell, `>>> ` and `... ` for Python. A block holding no prompt is copied whole.
# Matching Pygments classes instead (`.gp`, `.go`) misses most output here: an
# ANSI session draws its colored lines as `-Ansi-*` spans and its plain ones as
# bare text.
copybutton_prompt_text = r"\$ |>>> |\.\.\. "
copybutton_prompt_is_regexp = True


def pin_app_dir() -> None:
    """Render every configuration path as the POSIX one, whatever host builds.

    `click.get_app_dir()` answers per platform, so a `--config` default renders
    as `~/Library/Application Support/foo` on macOS and `~/.config/foo` on
    Linux. Left alone, a page therefore documents whichever machine happened to
    build it, and the captures a `:screenshot:` block commits flip back and
    forth with their author's laptop.

    Pinning to the POSIX form keeps a build reproducible, and keeps the
    published output exactly what it has always been, since these pages are
    built on Linux. The per-platform folders stay documented as a table in
    `config.md`, which is where a reader should look for their own anyway.

    Both bindings are patched, `click`'s and the reference bound into Click
    Extra's configuration machinery, the way
    {func}`click_extra.pytest.isolated_app_dir` does for a test suite.
    """

    def posix_app_dir(app_name, roaming=True, force_posix=False):
        """`click.get_app_dir()`'s Unix branch, taken on every platform.

        Returns an *expanded* path like the original, since a caller resolves
        it before Click Extra shrinks the home prefix back to `~` for display.
        `XDG_CONFIG_HOME` is deliberately ignored: honoring it would put the
        host back into the rendered output.
        """
        folder = "-".join(app_name.split()).lower()
        if force_posix:
            return os.path.expanduser(f"~/.{folder}")
        return os.path.join(os.path.expanduser("~/.config"), folder)

    click.get_app_dir = posix_app_dir
    click_extra.config.option.get_app_dir = posix_app_dir


pin_app_dir()


def setup(app):
    """Sphinx extension entry point.

    Registers the `autodoc-process-docstring` hook that injects a colored
    example into every {class}`HelpTheme` slot's autodoc block. The
    example is computed live by replaying the templates in
    `_PALETTE_EXAMPLES` through the active dark theme's slot styling, so
    the rendered output cannot drift from the actual Theme code path: tweak a
    built-in theme in `click_extra/theme.py` and the next build picks up the
    new colors.
    """
    app.connect("autodoc-process-docstring", inject_slot_example_docstring)
