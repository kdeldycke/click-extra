from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

project_path = Path(__file__).parent.parent.resolve()

# Fetch general information about the project from pyproject.toml.
toml_path = project_path / "pyproject.toml"
toml_config = tomllib.loads(toml_path.read_text())

# Redistribute pyproject.toml config to Sphinx.
project_id = toml_config["tool"]["poetry"]["name"]
version = release = toml_config["tool"]["poetry"]["version"]
url = toml_config["tool"]["poetry"]["homepage"]
author = ", ".join(
    a.split("<")[0].strip() for a in toml_config["tool"]["poetry"]["authors"]
)

# Title-case each word of the project ID.
project = " ".join(word.title() for word in project_id.split("-"))
htmlhelp_basename = project_id

# Addons.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.todo",
    "sphinx.ext.extlinks",
    "sphinx.ext.viewcode",
    # Adds a copy button to code blocks.
    "sphinx_copybutton",
    "sphinx_design",
    # Link to GitHub issues and PRs.
    "sphinx_issues",
    "sphinxext.opengraph",
    "myst_parser",
]

myst_enable_extensions = [
    "colon_fence",
]

master_doc = "index"

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

nitpicky = True

# Both the class’ and the __init__ method’s docstring are concatenated and
# inserted.
autoclass_content = "both"
# Keep the same ordering as in original source code.
autodoc_member_order = "bysource"
autodoc_default_flags = ["members", "undoc-members", "show-inheritance"]

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

# GitHub pre-implemented shortcuts.
github_user = "kdeldycke"
issues_github_path = f"{github_user}/{project_id}"

# External reference shortcuts.
github_project = f"https://github.com/{issues_github_path}"
extlinks = {
    "gh": (f"{github_project}/%s", "GitHub: %s"),
}

# Theme config.
html_theme = "furo"
html_title = project
html_logo = "images/logo-square.svg"
html_theme_options = {
    "sidebar_hide_name": True,
    # Activates edit links.
    "source_repository": github_project,
    "source_branch": "main",
    "source_directory": "docs/",
}

# Footer content.
html_last_updated_fmt = "%Y-%m-%d"
copyright = f"{author} and contributors"
html_show_copyright = True
html_show_sphinx = False


pygments_style = "ansi-click-extra-furo-style"


from sphinx.highlighting import PygmentsBridge

from click_extra.pygments import AnsiHtmlFormatter

PygmentsBridge.html_formatter = AnsiHtmlFormatter  # type: ignore


####################################
#  pallets_sphinx_themes Patch #1  #
####################################

# XXX Compatibility workaround because of https://github.com/pallets/pallets-sphinx-themes/blob/7b69241f1fde3cc3849f513a9dd83fa8a2f36603/src/pallets_sphinx_themes/themes/click/domain.py#L9
# Source:
# https://github.com/pallets/click/blob/dc918b48fb9006be683a684b42cc7496ad649b83/docs/conf.py#L6-L7
import click

setattr(click._compat, "text_type", str)

# Add support for ".. click:example::" and ".. click:run::" directives.
from pallets_sphinx_themes.themes.click import domain

append_orig = domain.ViewList.append


def patched_append(*args, **kwargs):
    """Replace the code block produced by ``.. click:run::`` directive with an ANSI
    Shell Session (``.. code-block:: ansi-shell-session``).

    Targets:
    - [``.. sourcecode:: text`` for `Pallets-Sphinx-Themes <= 2.0.2`](https://github.com/pallets/pallets-sphinx-themes/blob/7b69241f1fde3cc3849f513a9dd83fa8a2f36603/src/pallets_sphinx_themes/themes/click/domain.py#L245)
    - [``.. sourcecode:: shell-session`` for `Pallets-Sphinx-Themes > 2.0.2`](https://github.com/pallets/pallets-sphinx-themes/pull/62)
    """
    default_run_blocks = (
        ".. sourcecode:: text",
        ".. sourcecode:: shell-session",
    )
    for run_block in default_run_blocks:
        if run_block in args:
            args = list(args)
            index = args.index(run_block)
            args[index] = ".. code-block:: ansi-shell-session"

    return append_orig(*args, **kwargs)


domain.ViewList.append = patched_append


####################################
#  pallets_sphinx_themes Patch #2  #
####################################

# Replace the call to default ``CliRunner.invoke`` with a call to click_extra own version which is sensible to contextual color settings
# and output unfiltered ANSI codes.
# Fixes: <insert upstream bug report here>
from click_extra.tests.conftest import ExtraCliRunner

# Force color rendering in ``invoke`` calls.
ExtraCliRunner.force_color = True

# Brutal, but effective.
# Alternative patching methods: https://stackoverflow.com/a/38928265
domain.ExampleRunner.__bases__ = (ExtraCliRunner,)


####################################
#  Register new click directives   #
####################################
extensions.append("pallets_sphinx_themes.themes.click.domain")
