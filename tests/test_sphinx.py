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

import tempfile
from pathlib import Path
from textwrap import dedent

import pytest
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace


@pytest.fixture(params=["rst", "myst"])
def sphinx_app(request):
    """Create a Sphinx application for testing.

    Args:
        request.param: Either ``rst`` for reStructuredText only,
                      or ``myst`` for MyST Markdown support.
    """
    format_type = request.param

    with tempfile.TemporaryDirectory() as tmpdir:
        srcdir = Path(tmpdir) / "source"
        outdir = Path(tmpdir) / "build"
        doctreedir = outdir / ".doctrees"
        confdir = srcdir

        srcdir.mkdir()
        outdir.mkdir()

        # Sphinx's configuration is Python code.
        conf = {
            "master_doc": "index",
            "extensions": ["click_extra.sphinx"],
        }
        if format_type == "myst":
            conf["extensions"].append("myst_parser")
            conf["myst_enable_extensions"] = ["colon_fence"]

        # Write the conf.py file.
        config_content = "\n".join(
            f"{key} = {repr(value)}" for key, value in conf.items()
        )
        (srcdir / "conf.py").write_text(config_content)

        with docutils_namespace():
            app = Sphinx(
                str(srcdir),
                str(confdir),
                str(outdir),
                str(doctreedir),
                "html",
                verbosity=0,
                warning=None,
            )
            # Add format type as an attribute for easy access in tests.
            app._test_format = format_type
            yield app


def build_sphinx_document(sphinx_app: Sphinx, content: str) -> str | None:
    """Build a Sphinx document with content and return the HTML output.

    Automatically detects the format from the app configuration and uses
    the appropriate file extension (.rst or .md).
    """
    # Determine file extension based on app configuration.
    assert hasattr(sphinx_app, "_test_format")
    file_extension = ".md" if sphinx_app._test_format == "myst" else ".rst"

    index_file = Path(sphinx_app.srcdir) / f"index{file_extension}"
    index_file.write_text(content)

    # Build the documentation.
    sphinx_app.build()

    # Read the generated HTML.
    output_file = Path(sphinx_app.outdir) / "index.html"
    if output_file.exists():
        return output_file.read_text()


def test_sphinx_extension_setup(sphinx_app):
    """Test that the Sphinx extension is properly loaded."""
    # Check that the domain is registered.
    assert "click" in sphinx_app.registry.domains
    assert "click" in sphinx_app.env.domains

    # Check that our directives are registered.
    assert "example" in sphinx_app.env.get_domain("click").directives
    assert "run" in sphinx_app.env.get_domain("click").directives


def test_simple_directives(sphinx_app):
    """Test minimal documents with directives in both RST and MyST formats."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""\
            Test Document
            =============

            This is a test document.

            .. click:example::

                import click

                @click.command()
                def simple():
                    click.echo("It works!")

            .. click:run::

                invoke(simple, [])
        """)
    elif format_type == "myst":
        content = dedent("""\
            # Test Document

            This is a test document.

            ```{click:example}
            import click

            @click.command()
            def simple():
                click.echo("It works!")
            ```

            ```{click:run}
            invoke(simple, [])
            ```
        """)
    else:
        pytest.fail(f"Unknown format type: {format_type}")

    html_output = build_sphinx_document(sphinx_app, content)

    assert html_output is not None
    assert "<h1>Test Document" in html_output

    # click:example renders into a code block with syntax highlighting.
    assert (
        '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="kn">import</span><span class="w"> </span><span class="nn">click</span>\n'
        "\n"
        '<span class="nd">@click</span><span class="o">.</span><span class="n">command</span><span class="p">()</span>\n'
    ) in html_output

    # click:run renders into an ANSI shell session block with syntax highlighting.
    assert (
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="gp">$ </span>simple\n'
        "It works!\n"
        "</pre></div>\n"
    ) in html_output
