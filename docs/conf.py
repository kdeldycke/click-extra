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
    "tasklist",
]
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
    # crates.io blocks automated link checkers.
    r"https://crates\.io/crates/.*",
    # star-history uses client-side hash routing; fragments are not real HTML anchors.
    r"https://star-history\.com/#.*",
    # Telemetry opt-out endpoint is slow and times out from CI.
    r"https://telemetry\.timseverien\.com/.*",
    # Hacker News rate-limits automated checkers with HTTP 429. Already excluded
    # from the lychee run (see [tool.lychee] in pyproject.toml).
    r"https://news\.ycombinator\.com/.*",
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
    example into every :class:`HelpExtraTheme` slot's autodoc block. The
    example is computed live by replaying the templates in
    ``_PALETTE_EXAMPLES`` through the active dark theme's slot styling, so
    the rendered output cannot drift from the actual Theme code path —
    tweak ``themes.toml`` and the next build picks up the new colors.
    """
    from click_extra.theme import inject_slot_example_docstring

    app.connect("autodoc-process-docstring", inject_slot_example_docstring)
