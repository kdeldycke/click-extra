from __future__ import annotations

from pathlib import Path

import tomllib  # type: ignore[import-not-found]  # stdlib >=3.11; docs require >=3.14.
from docutils.nodes import make_id

project_path = Path(__file__).parent.parent.resolve()

# Fetch general information about the project from pyproject.toml.
toml_path = project_path / "pyproject.toml"
toml_config = tomllib.loads(toml_path.read_text(encoding="utf-8"))

# Redistribute pyproject.toml config to Sphinx.
project_id = toml_config["project"]["name"]
version = release = toml_config["project"]["version"]
url = toml_config["project"]["urls"]["Homepage"]
author = ", ".join(author["name"] for author in toml_config["project"]["authors"])

# Title-case each word of the project ID.
project = " ".join(word.title() for word in project_id.split("-"))

# Addons.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.todo",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    # Adds a copy button to code blocks.
    "sphinx_copybutton",
    "sphinx_design",
    # Link to GitHub issues and PRs.
    "sphinx_issues",
    "sphinxext.opengraph",
    "myst_parser",
    "sphinx.ext.autosectionlabel",
    "sphinx_autodoc_typehints",
    "click_extra.sphinx",
    "sphinxcontrib.mermaid",
]

# Opt into the click:* and python:* directive families. Both execute
# arbitrary Python at build time; see docs/sphinx.md for the security
# trust boundary.
click_extra_enable_exec_directives = True

# Emit roff man pages for click-extra's own CLI into <outdir>/man/ on every
# HTML build. See click_extra/sphinx/manpages.py.
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

# https://myst-parser.readthedocs.io/en/latest/syntax/optional.html
myst_enable_extensions = [
    "alert",
    "attrs_block",
    "attrs_inline",
    "colon_fence",
    "deflist",
    "fieldlist",
    "replacements",
    "smartquotes",
    "strikethrough",
    "substitution",
    "tasklist",
]

# Substitutions exposed to MyST documents as ``{{ name }}``. Built from
# Python data so single-source-of-truth content (like the --show-params column
# registry) stays in sync between code and docs automatically.
from click_extra.parameters import ShowParamsOption

myst_substitutions = {
    "show_params_columns_table": ShowParamsOption.render_doc_table(),
}
# Register a cross-reference target for every heading down to <h6>, so Markdown
# links of the form [text](other.md#heading-slug) resolve. Without this, MyST
# only resolves explicit (target)= anchors and emits best-effort hrefs that
# happen to work because docutils generates matching HTML ids — but each one
# raises a myst.xref_missing warning at build time.
myst_heading_anchors = 6
# Slugify headings exactly the way docutils derives HTML ids, so the anchors
# MyST resolves match the ids actually rendered in the page. The default
# GitHub-style slugifier keeps leading digits, "--" prefixes, dots and
# underscores that docutils strips or collapses (e.g. "`--show-params` option"
# → "show-params-option", "solarized_dark" → "solarized-dark"), which otherwise
# leaves every cross-reference to such a heading unresolved.
myst_heading_slug_func = make_id
# XXX Allow ```mermaid``` directive to be used without curly braces (```{mermaid}```), see:
# https://github.com/mgaitan/sphinxcontrib-mermaid/issues/99#issuecomment-2339587001
myst_fence_as_directive = ["mermaid"]

mermaid_d3_zoom = True

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

nitpicky = True

# Cosmetic or unavoidable warning categories, suppressed wholesale. Mirrors the
# kdeldycke/extra-platforms Sphinx configuration.
suppress_warnings = [
    # Names used only in (lazily-evaluated, PEP 563) type annotations are not
    # bound at build time, so sphinx_autodoc_typehints cannot resolve the forward
    # reference. Cosmetic: the rendered signature is unaffected.
    "sphinx_autodoc_typehints.forward_reference",
    # The click-extra Sphinx domain does not implement resolve_any_xref.
    "myst.domains",
    # ``~~text~~`` strikethrough (used to mark incorrect spellings in prose) only
    # renders in HTML, which is the only builder in use.
    "myst.strikethrough",
    # A few docstring code examples trip docutils' indentation heuristics.
    "docutils",
    # index.md opens at H2 (octicon card layout) and a couple of pages skip a
    # heading level; cosmetic, the rendered table of contents is unaffected.
    "myst.header",
    # Links to explicit raw-HTML anchors (``<a name="...">``), which MyST cannot
    # see at build time though they render and resolve correctly in HTML.
    "myst.xref_missing",
]

# Cross-reference targets that legitimately have nothing to link to, so nitpicky
# mode would otherwise flood the build with "reference target not found". These
# are NOT broken refs in click-extra's own docstrings (those are fully qualified).
# click-extra re-exports click's and cloup's public classes as a drop-in
# replacement, so autodoc renders their upstream docstrings and type annotations
# here, which reference upstream-internal names and private types absent from any
# intersphinx inventory.
nitpick_ignore_regex = [
    # External packages without an intersphinx inventory, plus click/cloup
    # internals not exposed in their public docs.
    (
        r"py:.*",
        r"(boltons|cloup|docutils|extra_platforms|mkdocs|pygments|sphinx|_pytest)\..*",
    ),
    (r"py:.*", r"click\.(testing|types|_\w+)\..*"),
    # Private (underscore-prefixed) symbols, in click-extra or upstream.
    (r"py:.*", r"(.*\.)?_[A-Za-z]\w*(\..*)?"),
]

# Bare names inherited from re-exported click/cloup docstrings: they resolve in
# their own upstream docs through the module context, which is lost when autodoc
# re-renders them under click-extra.
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
    ("py:class", "click.MultiCommand"),
    ("py:meth", "click.types.ParamType[t.Any].shell_complete"),
    # pygments' inherited ``aliases`` attribute docstring.
    ("py:func", "get_formatter_by_name"),
    # sphinx exception raised by the (deprecated) GitHub-alerts converter.
    ("py:exc", "ConfigError"),
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
]

# Concatenates the docstrings of the class and the __init__ method.
autoclass_content = "both"
# Keep the same ordering as in original source code.
autodoc_member_order = "bysource"
always_use_bars_union = True

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

# GitHub pre-implemented shortcuts.
github_user = "kdeldycke"
issues_github_path = f"{github_user}/{project_id}"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "click": ("https://click.palletsprojects.com", None),
}

# Prefix document path to section labels, to use:
# `path/to/file:heading` instead of just `heading`
autosectionlabel_prefix_document = True

# Theme config.
html_theme = "furo"
html_title = project
html_logo = "assets/logo-square.svg"
html_favicon = "assets/favicon.svg"
html_theme_options = {
    "sidebar_hide_name": True,
    # Activates edit links.
    "source_repository": f"https://github.com/{issues_github_path}",
    "source_branch": "main",
    "source_directory": "docs/",
    "announcement": (
        f"{project} works fine, but is <em>maintained by only one person</em> "
        "😶‍🌫️.<br/>You can help if you "
        "<strong><a class='reference external' "
        f"href='https://github.com/sponsors/{github_user}'>"
        "purchase business support 🤝</a></strong> or "
        "<strong><a class='reference external' "
        f"href='https://github.com/sponsors/{github_user}'>"
        "sponsor the project 🫶</a></strong>."
    ),
}

# Linkcheck configuration.
# GitHub renders issue comments, README tab anchors and blob line anchors with
# JavaScript, so the linkcheck builder cannot find them in the static HTML.
linkcheck_anchors_ignore = [
    r"issuecomment-\d+",
    r"a-simple-example",
    r"readme",
    r"L\d+",
]

linkcheck_ignore = [
    # These sites return 403 to bots but are valid.
    r"https://docutils\.sourceforge\.io",
    r"https://guix\.gnu\.org",
    # asciinema.org and no-color.org are valid but intermittently fail DNS
    # resolution or time out from CI runners. Also excluded from the lychee run
    # (see [tool.lychee] in pyproject.toml).
    r"https://asciinema\.org",
    r"https://no-color\.org",
    # crates.io blocks automated link checkers.
    r"https://crates\.io/crates/.*",
    # star-history uses client-side hash routing; fragments are not real HTML anchors.
    r"https://star-history\.com/#.*",
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

html_static_path = ["_static"]
html_css_files = ["custom.css"]


def setup(app):
    """Sphinx extension entry point.

    Registers the ``autodoc-process-docstring`` hook that injects a colored
    example into every :class:`HelpTheme` slot's autodoc block. The
    example is computed live by replaying the templates in
    ``_PALETTE_EXAMPLES`` through the active dark theme's slot styling, so
    the rendered output cannot drift from the actual Theme code path —
    tweak ``themes.toml`` and the next build picks up the new colors.
    """
    from click_extra.theme_docs import inject_slot_example_docstring

    app.connect("autodoc-process-docstring", inject_slot_example_docstring)
