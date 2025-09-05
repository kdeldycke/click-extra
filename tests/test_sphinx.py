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

import re
from pathlib import Path
from textwrap import dedent

import pytest
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace


@pytest.fixture(params=["rst", "myst"])
def sphinx_app(request, tmp_path):
    """Create a Sphinx application for testing.

    .. todo::
        Deduplicate and merge ``sphinx_app``, ``sphinx_app_rst`` and ``sphinx_app_myst`` fixtures.
    """
    format_type = request.param

    srcdir = tmp_path / "source"
    outdir = tmp_path / "build"
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
    config_content = "\n".join(f"{key} = {repr(value)}" for key, value in conf.items())
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


@pytest.fixture
def sphinx_app_rst(tmp_path):
    """Create a Sphinx application for testing RST format only.

    .. todo::
        Deduplicate and merge ``sphinx_app``, ``sphinx_app_rst`` and ``sphinx_app_myst`` fixtures.
    """
    srcdir = tmp_path / "source"
    outdir = tmp_path / "build"
    doctreedir = outdir / ".doctrees"
    confdir = srcdir

    srcdir.mkdir()
    outdir.mkdir()

    # Sphinx's configuration is Python code.
    conf = {
        "master_doc": "index",
        "extensions": ["click_extra.sphinx"],
    }

    # Write the conf.py file.
    config_content = "\n".join(f"{key} = {repr(value)}" for key, value in conf.items())
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
        app._test_format = "rst"
        yield app


@pytest.fixture
def sphinx_app_myst(tmp_path):
    """Create a Sphinx application for testing MyST format only.

    .. todo::
        Deduplicate and merge ``sphinx_app``, ``sphinx_app_rst`` and ``sphinx_app_myst`` fixtures.
    """
    srcdir = tmp_path / "source"
    outdir = tmp_path / "build"
    doctreedir = outdir / ".doctrees"
    confdir = srcdir

    srcdir.mkdir()
    outdir.mkdir()

    # Sphinx's configuration is Python code.
    conf = {
        "master_doc": "index",
        "extensions": ["click_extra.sphinx", "myst_parser"],
        "myst_enable_extensions": ["colon_fence"],
    }

    # Write the conf.py file.
    config_content = "\n".join(f"{key} = {repr(value)}" for key, value in conf.items())
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
        app._test_format = "myst"
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
    """Test minimal documents with directives in both RST and MyST formats.

    .. todo::
        Test different unmatching indentions and spacing in example and run directives.
    """
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""
            Test Document
            =============

            This is a test document.

            .. click:example::

                import click

                @click.command
                def simple():
                    click.echo("It works!")

            .. click:run::

                invoke(simple)
        """)
    elif format_type == "myst":
        content = dedent("""
            # Test Document

            This is a test document.

            ```{click:example}
            import click

            @click.command
            def simple():
                click.echo("It works!")
            ```

            ```{click:run}
            invoke(simple)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None
    assert "<h1>Test Document" in html_output

    # click:example renders into a code block with syntax highlighting.
    assert (
        '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="kn">import</span><span class="w"> </span><span class="nn">click</span>\n'
        "\n"
        '<span class="nd">@click</span><span class="o">.</span><span class="n">command</span>\n'
    ) in html_output

    # click:run renders into an ANSI shell session block with syntax highlighting.
    assert (
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="gp">$ </span>simple\n'
        "It works!\n"
        "</pre></div>\n"
    ) in html_output


def test_legacy_mixed_syntax_eval_rst(sphinx_app_myst):
    """Test MyST's ``{eval-rst}`` directive with ``click`` directives for legacy compatibility."""
    # Test MyST with embedded RST using {eval-rst}
    content = dedent("""
        ```{eval-rst}
        .. click:example::

            from click import echo, command

            @command
            def yo_cli():
                echo("Yo!")

        .. click:run::

            invoke(yo_cli)
        ```
    """)

    html_output = build_sphinx_document(sphinx_app_myst, content)
    assert html_output is not None

    # Both directives should render correctly.
    assert (
        '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="kn">from</span><span class="w"> </span><span class="nn">click</span><span class="w"> </span><span class="kn">import</span> <span class="n">echo</span><span class="p">,</span> <span class="n">command</span>\n'
        "\n"
        '<span class="nd">@command</span>\n'
        '<span class="k">def</span><span class="w"> </span><span class="nf">yo_cli</span><span class="p">():</span>\n'
        '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Yo!&quot;</span><span class="p">)</span>\n'
        "</pre></div>\n"
    ) in html_output
    assert (
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="gp">$ </span>yo-cli\n'
        "Yo!\n"
        "</pre></div>\n"
    ) in html_output


def test_directive_option_format(sphinx_app_rst):
    """rST will fail to render if an ``:option:`` is not followed by an empty line."""
    content = dedent("""
        .. click:example::
            :linenos:
            import click

            @click.command
            def bad_format():
                click.echo("This should fail to parse")

        .. click:run::

            invoke(bad_format, [])
    """)

    # RST should fail to parse this malformed directive
    with pytest.raises(NameError) as exc_info:
        build_sphinx_document(sphinx_app_rst, content)

    assert str(exc_info.value) == "name 'bad_format' is not defined"


def test_directive_option_linenos(sphinx_app):
    """Test that ``:linenos:`` option adds line numbers to code blocks."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""
            .. click:example::
                :linenos:

                import click

                @click.command
                def numbered_example():
                    click.echo("Line numbers should appear")
                    click.echo("on the left side")

            .. click:run::
                :linenos:

                invoke(numbered_example)
        """)
    elif format_type == "myst":
        content = dedent("""
            ```{click:example}
            :linenos:
            import click

            @click.command
            def numbered_example():
                click.echo("Line numbers should appear")
                click.echo("on the left side")
            ```

            ```{click:run}
            :linenos:
            invoke(numbered_example)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="linenos">1</span><span class="kn">import</span><span class="w"> </span><span class="nn">click</span>\n'
        '<span class="linenos">2</span>\n'
        '<span class="linenos">3</span><span class="nd">@click</span><span class="o">.</span><span class="n">command</span>\n'
        '<span class="linenos">4</span><span class="k">def</span><span class="w"> </span><span class="nf">numbered_example</span><span class="p">():</span>\n'
        '<span class="linenos">5</span>    <span class="n">click</span><span class="o">.</span><span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Line numbers should appear&quot;</span><span class="p">)</span>\n'
        '<span class="linenos">6</span>    <span class="n">click</span><span class="o">.</span><span class="n">echo</span><span class="p">(</span><span class="s2">&quot;on the left side&quot;</span><span class="p">)</span>\n'
        "</pre></div>\n"
        "</div>\n"
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="linenos">1</span><span class="gp">$ </span>numbered-example\n'
        '<span class="linenos">2</span>Line numbers should appear\n'
        '<span class="linenos">3</span>on the left side\n'
        "</pre></div>\n"
    ) in html_output


def test_directive_option_linenos_start(sphinx_app):
    """Test that ``:lineno-start:`` shifts the starting line number."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""
            .. click:example::
                :linenos:
                :lineno-start: 5

                import click

                @click.command
                def numbered_example():
                    click.echo("Line numbers should start from 5")
                    click.echo("and continue incrementing")

            .. click:run::
                :linenos:
                :lineno-start: 10

                invoke(numbered_example)
        """)
    elif format_type == "myst":
        content = dedent("""
            ```{click:example}
            :linenos:
            :lineno-start: 5
            import click

            @click.command
            def numbered_example():
                click.echo("Line numbers should start from 5")
                click.echo("and continue incrementing")
            ```

            ```{click:run}
            :linenos:
            :lineno-start: 10
            invoke(numbered_example)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="linenos"> 5</span><span class="kn">import</span><span class="w"> </span><span class="nn">click</span>\n'
        '<span class="linenos"> 6</span>\n'
        '<span class="linenos"> 7</span><span class="nd">@click</span><span class="o">.</span><span class="n">command</span>\n'
        '<span class="linenos"> 8</span><span class="k">def</span><span class="w"> </span><span class="nf">numbered_example</span><span class="p">():</span>\n'
        '<span class="linenos"> 9</span>    <span class="n">click</span><span class="o">.</span><span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Line numbers should start from 5&quot;</span><span class="p">)</span>\n'
        '<span class="linenos">10</span>    <span class="n">click</span><span class="o">.</span><span class="n">echo</span><span class="p">(</span><span class="s2">&quot;and continue incrementing&quot;</span><span class="p">)</span>\n'
        "</pre></div>\n"
        "</div>\n"
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="linenos">10</span><span class="gp">$ </span>numbered-example\n'
        '<span class="linenos">11</span>Line numbers should start from 5\n'
        '<span class="linenos">12</span>and continue incrementing\n'
        "</pre></div>\n"
        "</div>\n"
    ) in html_output


def test_directive_option_hide_source(sphinx_app):
    """Test that ``:hide-source:``hides source code in ``click:example`` directive."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""
            .. click:example::
                :hide-source:

                from click import echo, command

                @command
                def simple_print():
                    echo("Just a string to print.")

            .. click:run::

                invoke(simple_print)
        """)
    elif format_type == "myst":
        content = dedent("""
            ```{click:example}
            :hide-source:
            from click import echo, command

            @command
            def simple_print():
                echo("Just a string to print.")
            ```

            ```{click:run}
            invoke(simple_print)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    # click:example should not display source code.
    assert "highlight-python" not in html_output
    assert "command" not in html_output
    assert "simple_print" not in html_output

    # But click:run should still display results.
    assert (
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="gp">$ </span>simple-print\n'
        "Just a string to print.\n"
        "</pre></div>\n"
    ) in html_output


def test_directive_option_show_source(sphinx_app):
    """Test that ``:show-source:`` option shows source code in ``click:run`` directive."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""
            .. click:example::

                from click import echo, command

                @command
                def simple_print():
                    echo("Just a string to print.")

            .. click:run::
                :show-source:

                invoke(simple_print)
        """)
    elif format_type == "myst":
        content = dedent("""
            ```{click:example}
            from click import echo, command

            @command
            def simple_print():
                echo("Just a string to print.")
            ```

            ```{click:run}
            :show-source:
            invoke(simple_print)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="kn">from</span><span class="w"> </span><span class="nn">click</span><span class="w"> </span><span class="kn">import</span> <span class="n">echo</span><span class="p">,</span> <span class="n">command</span>\n'
        "\n"
        '<span class="nd">@command</span>\n'
        '<span class="k">def</span><span class="w"> </span><span class="nf">simple_print</span><span class="p">():</span>\n'
        '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Just a string to print.&quot;</span><span class="p">)</span>\n'
        "</pre></div>\n"
    ) in html_output

    assert (
        '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="n">invoke</span><span class="p">(</span><span class="n">simple_print</span><span class="p">)</span>\n'
        "</pre></div>\n"
        "</div>\n"
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span><span class="gp">$ </span>simple-print\n'
        "Just a string to print.\n"
        "</pre></div>\n"
    ) in html_output


def test_directive_option_hide_results(sphinx_app):
    """Test that ``:hide-results:`` option hides execution results in ``click:run``."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""\
            .. click:example::

                from click import echo, command

                @command
                def simple():
                    echo("This output should be hidden")

            .. click:run::
                :hide-results:

                invoke(simple)
        """)
    elif format_type == "myst":
        content = dedent("""\
            ```{click:example}
            from click import echo, command

            @command
            def simple():
                echo("This output should be hidden")
            ```

            ```{click:run}
            :hide-results:
            invoke(simple)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="kn">from</span><span class="w"> </span><span class="nn">click</span><span class="w"> </span><span class="kn">import</span> <span class="n">echo</span><span class="p">,</span> <span class="n">command</span>\n'
        "\n"
        '<span class="nd">@command</span>\n'
        '<span class="k">def</span><span class="w"> </span><span class="nf">simple</span><span class="p">():</span>\n'
        '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;This output should be hidden&quot;</span><span class="p">)</span>\n'
        "</pre></div>\n"
    ) in html_output


def test_directive_option_show_results(sphinx_app):
    """Test that ``:show-results:`` option shows execution results (default behavior)."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""\
            .. click:example::

                from click import echo, command

                @command
                def simple():
                    echo("This output should be hidden")

            .. click:run::
                :show-results:

                invoke(simple)
        """)
    elif format_type == "myst":
        content = dedent("""\
            ```{click:example}
            from click import echo, command

            @command
            def simple():
                echo("This output should be hidden")
            ```

            ```{click:run}
            :show-results:
            invoke(simple)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '  <div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="kn">from</span><span class="w"> </span><span class="nn">click</span><span class="w"> </span><span class="kn">import</span> <span class="n">echo</span><span class="p">,</span> <span class="n">command</span>\n'
        "\n"
        '<span class="nd">@command</span>\n'
        '<span class="k">def</span><span class="w"> </span><span class="nf">simple</span><span class="p">():</span>\n'
        '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;This output should be hidden&quot;</span><span class="p">)</span>\n'
        "</pre></div>\n"
        "</div>\n"
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="gp">$ </span>simple\n'
        "This output should be hidden\n"
        "</pre></div>\n"
    ) in html_output


def test_directive_option_combinations(sphinx_app):
    """Test various combinations of display options."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""\
            .. click:example::
                :show-source:
                :hide-results:

                from click import command, echo

                @command
                def combo_test():
                    echo("Should not see this")

            .. click:run::
                :show-source:
                :show-results:

                invoke(combo_test)
        """)
    elif format_type == "myst":
        content = dedent("""\
            ```{click:example}
            :show-source:
            :hide-results:

            from click import command, echo

            @command
            def combo_test():
                echo("Should not see this")
            ```

            ```{click:run}
            :show-source:
            :show-results:
            invoke(combo_test)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="kn">from</span><span class="w"> </span><span class="nn">click</span><span class="w"> </span><span class="kn">import</span> <span class="n">command</span><span class="p">,</span> <span class="n">echo</span>\n'
        "\n"
        '<span class="nd">@command</span>\n'
        '<span class="k">def</span><span class="w"> </span><span class="nf">combo_test</span><span class="p">():</span>\n'
        '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Should not see this&quot;</span><span class="p">)</span>\n'
        "</pre></div>\n"
        "</div>\n"
        '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>'
        '<span class="n">invoke</span><span class="p">(</span><span class="n">combo_test</span><span class="p">)</span>\n'
        "</pre></div>\n"
        "</div>\n"
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="gp">$ </span>combo-test\n'
        "Should not see this\n"
        "</pre></div>\n"
    ) in html_output


def test_directive_option_language_override(sphinx_app):
    """Test that language override works for click:run directive."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""
            .. click:example::

                from click import echo, command, option

                @command
                @option("--name")
                def sql_output(name):
                    sql_query = f"SELECT * FROM users WHERE name = '{name}';"
                    echo(sql_query)

            .. click:run:: sql

                invoke(sql_output, args=["--name", "Joe"])
        """)
    elif format_type == "myst":
        content = dedent("""
            ```{click:example}
            from click import echo, command, option

            @command
            @option("--name")
            def sql_output(name):
                sql_query = f"SELECT * FROM users WHERE name = '{name}';"
                echo(sql_query)
            ```

            ```{click:run} sql
            invoke(sql_output, args=["--name", "Joe"])
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '<div class="highlight-sql notranslate"><div class="highlight"><pre><span></span>'
        '<span class="err">$</span><span class="w"> </span><span class="k">sql</span><span class="o">-</span><span class="k">output</span><span class="w"> </span><span class="c1">--name Joe</span>\n'
        '<span class="k">SELECT</span><span class="w"> </span><span class="o">*</span><span class="w"> </span><span class="k">FROM</span><span class="w"> </span><span class="n">users</span><span class="w"> </span><span class="k">WHERE</span><span class="w"> </span><span class="n">name</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s1">&#39;Joe&#39;</span><span class="p">;</span>\n'
        "</pre></div>\n"
        "</div>\n"
    ) in html_output


def test_sphinx_directive_state_persistence(sphinx_app):
    """Test that state persists between declare and run directives in real Sphinx."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""
            .. click:example::

                import click

                @click.command
                def cmd1():
                    click.echo("Command 1")

            .. click:example::

                @click.command
                def cmd2():
                    click.echo("Command 2")

            .. click:run::

                invoke(cmd1)

            .. click:run::

                invoke(cmd2)
        """)
    elif format_type == "myst":
        content = dedent("""
            ```{click:example}
            import click

            @click.command
            def cmd1():
                click.echo("Command 1")
            ```

            ```{click:example}
            @click.command
            def cmd2():
                click.echo("Command 2")
            ```

            ```{click:run}
            invoke(cmd1)
            ```

            ```{click:run}
            invoke(cmd2)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="gp">$ </span>cmd1\n'
        "Command 1\n"
        "</pre></div>\n"
        "</div>\n"
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="gp">$ </span>cmd2\n'
        "Command 2\n"
        "</pre></div>\n"
    ) in html_output


def test_stdout_stderr_output(sphinx_app):
    """Test directives that print to both ``<stdout>`` and ``<stderr>`` with proper rendering."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""
            .. click:example::

                import sys

                import click
                from click_extra import style, Color

                @click.command
                def mixed_output():
                    click.echo(f"This goes to {style('stdout', fg=Color.blue)}")
                    click.echo(f"This is an {style('error', fg=Color.red)}", err=True)
                    print(f"Direct {style('stdout', fg=Color.blue)} print", file=sys.stdout)
                    print(f"Direct {style('stderr', fg=Color.red)} print", file=sys.stderr)

            .. click:run::

                invoke(mixed_output)
        """)
    elif format_type == "myst":
        content = dedent("""
            ```{click:example}
            import sys

            import click
            from click_extra import style, Color

            @click.command
            def mixed_output():
                click.echo(f"This goes to {style('stdout', fg=Color.blue)}")
                click.echo(f"This is an {style('error', fg=Color.red)}", err=True)
                print(f"Direct {style('stdout', fg=Color.blue)} print", file=sys.stdout)
                print(f"Direct {style('stderr', fg=Color.red)} print", file=sys.stderr)
            ```

            ```{click:run}
            invoke(mixed_output)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span>'
        '</span><span class="gp">$ </span>mixed-output\n'
        'This goes to <span class=" -Color -Color-Blue -C-Blue">stdout</span>\n'
        'This is an <span class=" -Color -Color-Red -C-Red">error</span>\n'
        'Direct <span class=" -Color -Color-Blue -C-Blue">stdout</span> print\n'
        'Direct <span class=" -Color -Color-Red -C-Red">stderr</span> print\n'
        "</pre></div>"
    ) in html_output


def test_isolated_filesystem_directive(sphinx_app):
    """Test that isolated_filesystem works properly in click:run directives."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""\
            .. click:example::

                import click

                @click.command
                def greet():
                    click.echo("Hello World!")

            .. click:run::

                with isolated_filesystem():
                    with open("test.txt", "w") as f:
                        f.write("Hello File!")
                    invoke(greet)
        """)
    elif format_type == "myst":
        content = dedent("""\
            ```{click:example}
            import click

            @click.command
            def greet():
                click.echo("Hello World!")
            ```

            ```{click:run}
            with isolated_filesystem():
                with open("test.txt", "w") as f:
                    f.write("Hello File!")
                invoke(greet)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="gp">$ </span>greet\n'
        "Hello World!\n"
        "</pre></div>\n"
    ) in html_output


@pytest.mark.parametrize("var_name", ["invoke", "isolated_filesystem"])
def test_directive_variable_conflict(var_name, sphinx_app):
    """Test that variable conflicts are properly detected in real Sphinx environment.

    .. todo::
        Test different indentations and spacing around the conflicting variable to
        check line number reported in error message are accurate.
    """
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent(f"""
            .. click:example::

                import click

                @click.command
                def hello():
                    click.echo("Hello World!")

            .. click:run::

                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"
                result = invoke(hello)
        """)
        file_extension = ".rst"
        error_lineno = 23

    elif format_type == "myst":
        content = dedent(f"""
            ```{{click:example}}
            import click

            @click.command
            def hello():
                click.echo("Hello World!")
            ```

            ```{{click:run}}
            # This should fail due to variable conflict.
            {var_name} = "Do not overwrite me!"
            result = invoke(hello)
            ```
        """)
        file_extension = ".md"
        error_lineno = 12

    with pytest.raises(RuntimeError) as exc_info:
        build_sphinx_document(sphinx_app, content)

    expected_pattern = (
        rf"Local variable '{var_name}' at .+/index"
        + re.escape(file_extension)
        + rf":10:click:run:{error_lineno} conflicts with the one automaticcaly provided by the click:run directive\.\n"
        rf"Line: {var_name} = \"Do not overwrite me!\""
    )
    assert re.fullmatch(expected_pattern, str(exc_info.value))


def test_exit_exception_percolate(sphinx_app):
    """Test directives that handle command errors and exit codes."""
    format_type = sphinx_app._test_format

    if format_type == "rst":
        content = dedent("""
            .. click:example::

                import click
                import sys

                @click.command
                @click.option('--fail', is_flag=True, help='Force command to fail')
                def error_command(fail):
                    click.echo("Starting command...")
                    if fail:
                        click.echo("Something went wrong!", err=True)
                        sys.exit(1)
                    click.echo("Command completed successfully")

            .. click:run::

                # Test successful execution
                invoke(error_command, [])

            .. click:run::

                # Test failed execution
                try:
                    invoke(error_command, ['--fail'])
                except SystemExit as e:
                    click.echo(f"Command exited with code: {e.code}", err=True)
        """)
    elif format_type == "myst":
        content = dedent("""
            ```{click:example}
            import click
            import sys

            @click.command
            @click.option('--fail', is_flag=True, help='Force command to fail')
            def error_command(fail):
                click.echo("Starting command...")
                if fail:
                    click.echo("Something went wrong!", err=True)
                    sys.exit(1)
                click.echo("Command completed successfully")
            ```

            ```{click:run}
            # Test successful execution
            invoke(error_command, [])
            ```

            ```{click:run}
            # Test failed execution
            try:
                invoke(error_command, ['--fail'])
            except SystemExit as e:
                click.echo(f"Command exited with code: {e.code}", err=True)
            ```
        """)

    html_output = build_sphinx_document(sphinx_app, content)
    assert html_output is not None

    assert (
        '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>'
        '<span class="gp">$ </span>error<span class="w"> </span>--fail\n'
        "Starting command...\n"
        "Something went wrong!\n"
        "</pre></div>\n"
    ) in html_output
