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
from dataclasses import dataclass
from enum import Enum
from inspect import cleandoc
from pathlib import Path
from textwrap import dedent, indent
from typing import Generator, Sequence

import pytest
from sphinx.application import Sphinx
from sphinx.errors import ConfigError
from sphinx.util.docutils import docutils_namespace


class FormatType(Enum):
    """Sphinx document format types and their file extensions."""

    RST = ".rst"
    MYST = ".md"


class SphinxAppWrapper:
    """Wrapper around Sphinx application with additional testing methods."""

    def __init__(self, app: Sphinx, format_type: FormatType):
        self.app = app
        self.format_type = format_type

    def __getattr__(self, name):
        """Delegate attribute access to the wrapped Sphinx app."""
        return getattr(self.app, name)

    @classmethod
    def create(
        cls, format_type: FormatType, tmp_path, return_srcdir: bool = False
    ) -> Generator[SphinxAppWrapper | tuple[SphinxAppWrapper, Path], None, None]:
        """Factory method to create a SphinxAppWrapper with given format."""
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
        if format_type == FormatType.MYST:
            conf["extensions"].append("myst_parser")  # type: ignore[attr-defined]
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
            wrapper = cls(app, format_type)
            yield (wrapper, srcdir) if return_srcdir else wrapper

    def build_document(self, content: str) -> str | None:
        """Build a Sphinx document with content and return the HTML output.

        Automatically detects the format from the app configuration and uses the
        appropriate file extension (.rst or .md).
        """
        # Determine file extension based on format type.
        file_extension = self.format_type.value

        index_file = Path(self.app.srcdir) / f"index{file_extension}"
        index_file.write_text(content)

        # Build the documentation.
        self.app.build()

        # Read the generated HTML.
        output_file = Path(self.app.outdir) / "index.html"
        if output_file.exists():
            html_output = output_file.read_text()
            assert html_output
            return html_output

        return None

    def generate_test_content(self, test_case: DirectiveTestCase) -> str:
        """Generate content for a test case based on the app's format type."""
        # If document is provided, use it directly.
        if test_case.document is not None:
            return test_case.document

        # Produce click:source and click:run directives in the appropriate format.
        lines = []

        if test_case.source_block:
            if self.format_type == FormatType.RST:
                lines.append(".. click:source::")
                # We need a blank line if there are no options.
                if not test_case.source_block.startswith(":"):
                    lines.append("")
                lines.append(indent(test_case.source_block, " " * 4))
            elif self.format_type == FormatType.MYST:
                lines += [
                    "```{click:source}",
                    test_case.source_block,
                    "```",
                ]

        # Separate directives with a blank line.
        if lines:
            lines.append("")

        if test_case.run_block:
            if self.format_type == FormatType.RST:
                lines.append(".. click:run::")
                # We need a blank line if there are no options.
                if not test_case.run_block.startswith(":"):
                    lines.append("")
                lines.append(indent(test_case.run_block, " " * 4))
            elif self.format_type == FormatType.MYST:
                lines += [
                    "```{click:run}",
                    test_case.run_block,
                    "```",
                ]

        return "\n".join(lines)


@pytest.fixture(params=[FormatType.RST, FormatType.MYST])
def sphinx_app(request, tmp_path):
    """Create a Sphinx application for testing."""
    yield from SphinxAppWrapper.create(request.param, tmp_path)


@pytest.fixture
def sphinx_app_rst(tmp_path):
    """Create a Sphinx application for testing RST format only."""
    yield from SphinxAppWrapper.create(FormatType.RST, tmp_path)


@pytest.fixture
def sphinx_app_myst(tmp_path):
    """Create a Sphinx application for testing MyST format only."""
    yield from SphinxAppWrapper.create(FormatType.MYST, tmp_path)


@pytest.fixture
def sphinx_app_myst_with_include(tmp_path):
    """Create a Sphinx application for testing MyST format with include files."""
    yield from SphinxAppWrapper.create(FormatType.MYST, tmp_path, return_srcdir=True)


@dataclass
class DirectiveTestCase:
    """Test case data for directive tests."""

    name: str
    format_type: FormatType | None = None
    source_block: str | None = None
    run_block: str | None = None
    document: str | None = None
    html_matches: Sequence[str] | str | None = None

    def __post_init__(self):
        if not self.html_matches:
            self.html_matches = tuple()
        elif isinstance(self.html_matches, str):
            self.html_matches = (self.html_matches,)

        # Validate mutually exclusive options
        if self.document is not None:
            if self.source_block is not None or self.run_block is not None:
                raise ValueError(
                    "DirectiveTestCase: 'document' cannot be used with 'source_block' or 'run_block'"
                )
            if self.format_type is None:
                raise ValueError(
                    "DirectiveTestCase: 'format_type' must be specified when using 'document'"
                )

        # Dedent code fields to remove leading and trailing whitespace.
        if self.source_block:
            self.source_block = cleandoc(self.source_block)
        if self.run_block:
            self.run_block = cleandoc(self.run_block)
        if self.document:
            self.document = cleandoc(self.document)

    def supports_format(self, format_type: FormatType) -> bool:
        """Check if this test case supports the given format type.

        .. todo::
            Get rid of this method, and make the test case provide its own sphinx_app.
        """
        return self.format_type is None or self.format_type == format_type

    def __str__(self) -> str:
        return self.name


# Common HTML fragments for assertions.
HTML = {
    "python_highlight": '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>',
    "markdown_highlight": '<div class="highlight-markdown notranslate"><div class="highlight"><pre><span></span>',
    "shell_session": '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>',
    "sql_highlight": '<div class="highlight-sql notranslate"><div class="highlight"><pre><span></span>',
    "import_click": '<span class="kn">from</span><span class="w"> </span><span class="nn">click</span><span class="w"> </span><span class="kn">import</span> <span class="n">command</span><span class="p">,</span> <span class="n">echo</span>\n',
}


def test_sphinx_extension_setup(sphinx_app):
    """Test that the Sphinx extension is properly loaded."""
    # Check that the domain is registered.
    assert "click" in sphinx_app.registry.domains
    assert "click" in sphinx_app.env.domains

    # Check that our directives are registered.
    assert "example" in sphinx_app.env.get_domain("click").directives
    assert "run" in sphinx_app.env.get_domain("click").directives


# Test case definitions
BASIC_DIRECTIVES_TEST_CASE = DirectiveTestCase(
    # Test minimal documents with directives in both RST and MyST formats.
    name="basic",
    source_block="""
        from click import command, echo

        @command
        def simple_cli():
            echo("It works!")
    """,
    run_block="invoke(simple_cli)",
    html_matches=(
        (
            HTML["python_highlight"]
            + HTML["import_click"]
            + "\n"
            + '<span class="nd">@command</span>\n'
            + '<span class="k">def</span><span class="w"> </span><span class="nf">simple_cli</span><span class="p">():</span>\n'
            + '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;It works!&quot;</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
        (
            HTML["shell_session"]
            + '<span class="gp">$ </span>simple-cli\n'
            + "It works!\n"
            + "</pre></div>\n"
        ),
    ),
)

LINENOS_TEST_CASE = DirectiveTestCase(
    # Test that :linenos: option adds line numbers to code blocks.
    name="linenos",
    source_block="""
        :linenos:

        from click import command, echo

        @command
        def numbered_example():
            echo("Line numbers should appear")
            echo("on the left side")
    """,
    run_block="""
        :linenos:

        invoke(numbered_example)
    """,
    html_matches=(
        (
            HTML["python_highlight"]
            + '<span class="linenos">1</span>'
            + HTML["import_click"]
            + '<span class="linenos">2</span>\n'
            + '<span class="linenos">3</span><span class="nd">@command</span>\n'
            + '<span class="linenos">4</span><span class="k">def</span><span class="w"> </span><span class="nf">numbered_example</span><span class="p">():</span>\n'
            + '<span class="linenos">5</span>    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Line numbers should appear&quot;</span><span class="p">)</span>\n'
            + '<span class="linenos">6</span>    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;on the left side&quot;</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
        (
            HTML["shell_session"]
            + '<span class="linenos">1</span><span class="gp">$ </span>numbered-example\n'
            + '<span class="linenos">2</span>Line numbers should appear\n'
            + '<span class="linenos">3</span>on the left side\n'
            + "</pre></div>\n"
        ),
    ),
)

LINENOS_START_TEST_CASE = DirectiveTestCase(
    # Test that :lineno-start: shifts the starting line number.
    name="linenos_start",
    source_block="""
        :linenos:
        :lineno-start: 5

        from click import command, echo

        @command
        def numbered_example():
            echo("Line numbers should start from 5")
            echo("and continue incrementing")
    """,
    run_block="""
        :linenos:
        :lineno-start: 10

        invoke(numbered_example)
    """,
    html_matches=(
        (
            HTML["python_highlight"]
            + '<span class="linenos"> 5</span>'
            + HTML["import_click"]
            + '<span class="linenos"> 6</span>\n'
            + '<span class="linenos"> 7</span><span class="nd">@command</span>\n'
            + '<span class="linenos"> 8</span><span class="k">def</span><span class="w"> </span><span class="nf">numbered_example</span><span class="p">():</span>\n'
            + '<span class="linenos"> 9</span>    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Line numbers should start from 5&quot;</span><span class="p">)</span>\n'
            + '<span class="linenos">10</span>    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;and continue incrementing&quot;</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
        (
            HTML["shell_session"]
            + '<span class="linenos">10</span><span class="gp">$ </span>numbered-example\n'
            + '<span class="linenos">11</span>Line numbers should start from 5\n'
            + '<span class="linenos">12</span>and continue incrementing\n'
            + "</pre></div>\n"
        ),
    ),
)

HIDE_SOURCE_TEST_CASE = DirectiveTestCase(
    # Test that :hide-source: hides source code in click:source directive.
    name="hide_source",
    source_block="""
        :hide-source:

        from click import command, echo

        @command
        def simple_print():
            echo("Just a string to print.")
    """,
    run_block="invoke(simple_print)",
    # Check from the start of the body to make sure the click:source is gone.
    html_matches='          <div class="body" role="main">\n'
    + "            \n  "
    + HTML["shell_session"]
    + '<span class="gp">$ </span>simple-print\n'
    + "Just a string to print.\n"
    + "</pre></div>\n",
)

SHOW_SOURCE_TEST_CASE = DirectiveTestCase(
    # Test that :show-source: option shows source code in click:run directive.
    name="show_source",
    source_block="""
        from click import command, echo

        @command
        def simple_print():
            echo("Just a string to print.")
    """,
    run_block="""
        :show-source:

        invoke(simple_print)
    """,
    html_matches=(
        # Source directive should show source.
        (
            HTML["python_highlight"]
            + HTML["import_click"]
            + "\n"
            + '<span class="nd">@command</span>\n'
            + '<span class="k">def</span><span class="w"> </span><span class="nf">simple_print</span><span class="p">():</span>\n'
            + '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Just a string to print.&quot;</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
        # Run directive should show source code.
        (
            HTML["python_highlight"]
            + '<span class="n">invoke</span><span class="p">(</span><span class="n">simple_print</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
        # Run directive should show execution results.
        (
            HTML["shell_session"]
            + '<span class="gp">$ </span>simple-print\n'
            + "Just a string to print.\n"
            + "</pre></div>\n"
            + "</div>\n"
        ),
    ),
)

HIDE_RESULTS_TEST_CASE = DirectiveTestCase(
    # Test that :hide-results: option hides execution results in click:run directive.
    name="hide_results",
    source_block="""
        from click import command, echo

        @command
        def simple_print():
            echo("Just a string to print.")
    """,
    run_block="""
        :hide-results:

        invoke(simple_print)
    """,
    # Source directive should show source.
    html_matches=HTML["python_highlight"]
    + HTML["import_click"]
    + "\n"
    + '<span class="nd">@command</span>\n'
    + '<span class="k">def</span><span class="w"> </span><span class="nf">simple_print</span><span class="p">():</span>\n'
    + '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Just a string to print.&quot;</span><span class="p">)</span>\n'
    + "</pre></div>\n",
)

SHOW_RESULTS_TEST_CASE = DirectiveTestCase(
    # Test that :show-results: option shows execution results (default behavior).
    name="show_results",
    source_block="""
        from click import command, echo

        @command
        def simple_print():
            echo("Just a string to print.")
    """,
    run_block="""
        :show-results:

        invoke(simple_print)
    """,
    html_matches=(
        # Source directive should show source.
        (
            HTML["python_highlight"]
            + HTML["import_click"]
            + "\n"
            + '<span class="nd">@command</span>\n'
            + '<span class="k">def</span><span class="w"> </span><span class="nf">simple_print</span><span class="p">():</span>\n'
            + '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Just a string to print.&quot;</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
        # Run directive should show execution results.
        (
            HTML["shell_session"]
            + '<span class="gp">$ </span>simple-print\n'
            + "Just a string to print.\n"
            + "</pre></div>\n"
        ),
    ),
)

OPTION_COMBINATIONS_TEST_CASE = DirectiveTestCase(
    # Test various combinations of display options.
    name="option_combinations",
    source_block="""
        :show-source:
        :hide-results:

        from click import command, echo

        @command
        def simple_print():
            echo("Just a string to print.")
    """,
    run_block="""
        :show-source:
        :hide-results:
        :show-results:

        invoke(simple_print)
    """,
    html_matches=(
        # Source directive should show source.
        (
            HTML["python_highlight"]
            + HTML["import_click"]
            + "\n"
            + '<span class="nd">@command</span>\n'
            + '<span class="k">def</span><span class="w"> </span><span class="nf">simple_print</span><span class="p">():</span>\n'
            + '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Just a string to print.&quot;</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
        # Run directive should show source code.
        (
            HTML["python_highlight"]
            + '<span class="n">invoke</span><span class="p">(</span><span class="n">simple_print</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
        # Run directive should show execution results (show-results overrides
        # hide-results).
        (
            HTML["shell_session"]
            + '<span class="gp">$ </span>simple-print\n'
            + "Just a string to print.\n"
            + "</pre></div>\n"
        ),
    ),
)

MIXED_OUTPUT_TEST_CASE = DirectiveTestCase(
    # Test directives that print to both stdout and stderr with proper rendering.
    name="mixed_output",
    source_block="""
        import sys

        from click import command, echo
        from click_extra import style, Color

        @command
        def mixed_output():
            echo(f"This goes to {style('stdout', fg=Color.blue)}")
            echo(f"This is an {style('error', fg=Color.red)}", err=True)
            print(f"Direct {style('stdout', fg=Color.blue)} print", file=sys.stdout)
            print(f"Direct {style('stderr', fg=Color.red)} print", file=sys.stderr)
    """,
    run_block="invoke(mixed_output)",
    # Should show mixed stdout/stderr output with colors.
    html_matches=HTML["shell_session"]
    + '<span class="gp">$ </span>mixed-output\n'
    + 'This goes to <span class=" -Color -Color-Blue -C-Blue">stdout</span>\n'
    + 'This is an <span class=" -Color -Color-Red -C-Red">error</span>\n'
    + 'Direct <span class=" -Color -Color-Blue -C-Blue">stdout</span> print\n'
    + 'Direct <span class=" -Color -Color-Red -C-Red">stderr</span> print\n'
    + "</pre></div>",
)

ISOLATED_FILESYSTEM_TEST_CASE = DirectiveTestCase(
    # Test that isolated_filesystem works properly in click:run directives.
    name="isolated_filesystem",
    source_block="""
        from click import command, echo

        @command
        def greet():
            echo("Hello World!")
    """,
    run_block="""
        with isolated_filesystem():
            with open("test.txt", "w") as f:
                f.write("Hello File!")
            invoke(greet)
    """,
    # Should show command execution within isolated filesystem.
    html_matches=HTML["shell_session"]
    + '<span class="gp">$ </span>greet\n'
    + "Hello World!\n"
    + "</pre></div>\n",
)

RST_WITHIN_MYST_EVAL_TEST_CASE = DirectiveTestCase(
    name="rst_within_myst_eval",
    # This test is MyST-specific but contains embedded RST.
    format_type=FormatType.MYST,
    document="""
        ```{eval-rst}
        .. click:source::

            from click import command, echo

            @command
            def yo_cli():
                echo("Yo!")

        .. click:run::

            invoke(yo_cli)
        ```
    """,
    html_matches=(
        (
            HTML["python_highlight"]
            + HTML["import_click"]
            + "\n"
            + '<span class="nd">@command</span>\n'
            + '<span class="k">def</span><span class="w"> </span><span class="nf">yo_cli</span><span class="p">():</span>\n'
            + '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Yo!&quot;</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
        (
            HTML["shell_session"]
            + '<span class="gp">$ </span>yo-cli\n'
            + "Yo!\n"
            + "</pre></div>\n"
        ),
    ),
)


def python_block(*lines: str) -> str:
    """Build expected Python highlight block."""
    return HTML["python_highlight"] + "".join(lines) + "</pre></div>\n"


def shell_block(*lines: str) -> str:
    """Build expected shell session block."""
    return HTML["shell_session"] + "".join(lines) + "</pre></div>\n"


def admonition_block(admonition_type: str, content: str) -> str:
    """Build expected admonition block.

    Args:
        admonition_type: The type of admonition (note, tip, warning, etc.)
        content: The inner HTML content of the admonition (without the title)
    """
    title = admonition_type.capitalize()
    return (
        f'<div class="admonition {admonition_type}">\n'
        f'<p class="admonition-title">{title}</p>\n'
        f"{content}"
        "</div>\n"
    )


@pytest.mark.parametrize(
    "test_case",
    [
        BASIC_DIRECTIVES_TEST_CASE,
        LINENOS_TEST_CASE,
        LINENOS_START_TEST_CASE,
        HIDE_SOURCE_TEST_CASE,
        SHOW_SOURCE_TEST_CASE,
        HIDE_RESULTS_TEST_CASE,
        SHOW_RESULTS_TEST_CASE,
        OPTION_COMBINATIONS_TEST_CASE,
        MIXED_OUTPUT_TEST_CASE,
        ISOLATED_FILESYSTEM_TEST_CASE,
        RST_WITHIN_MYST_EVAL_TEST_CASE,
    ],
)
def test_directive_functionality(sphinx_app, test_case):
    """Test standard directive functionalities in both rST and MyST."""
    # Skip test if format doesn't match
    if not test_case.supports_format(sphinx_app.format_type):
        pytest.skip(
            f"Test case '{test_case.name}' only supports {test_case.format_type}"
        )

    content = sphinx_app.generate_test_content(test_case)
    html_output = sphinx_app.build_document(content)

    # Assert all expected fragments are present.
    for fragment in test_case.html_matches:
        assert fragment in html_output


def test_directive_option_format(sphinx_app_rst):
    """rST will fail to render if an ``:option:`` is not followed by an empty line."""
    content = dedent("""
        .. click:source::
            :linenos:
            from click import command, echo

            @command
            def bad_format():
                echo("This should fail to parse")

        .. click:run::

            invoke(bad_format)
    """)

    # RST should fail to parse this malformed directive.
    with pytest.raises(NameError) as exc_info:
        sphinx_app_rst.build_document(content)

    assert str(exc_info.value) == "name 'bad_format' is not defined"


def test_directive_option_language_override(sphinx_app):
    """Test that language override works for click:run directive."""
    format_type = sphinx_app.format_type

    if format_type == FormatType.RST:
        content = dedent("""
            .. click:source::

                from click import command, echo, option

                @command
                @option("--name")
                def sql_output(name):
                    sql_query = f"SELECT * FROM users WHERE name = '{name}';"
                    echo(sql_query)

            .. click:run:: sql

                invoke(sql_output, args=["--name", "Joe"])
        """)
    elif format_type == FormatType.MYST:
        content = dedent("""
            ```{click:source}
            from click import command, echo, option

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

    html_output = sphinx_app.build_document(content)

    assert (
        HTML["sql_highlight"]
        + '<span class="err">$</span><span class="w"> </span><span class="k">sql</span><span class="o">-</span><span class="k">output</span><span class="w"> </span><span class="c1">--name Joe</span>\n'
        + '<span class="k">SELECT</span><span class="w"> </span><span class="o">*</span><span class="w"> </span><span class="k">FROM</span><span class="w"> </span><span class="n">users</span><span class="w"> </span><span class="k">WHERE</span><span class="w"> </span><span class="n">name</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s1">&#39;Joe&#39;</span><span class="p">;</span>\n'
        + "</pre></div>\n"
    ) in html_output


def test_sphinx_directive_state_persistence(sphinx_app):
    """Test that state persists between declare and run directives in real Sphinx."""
    format_type = sphinx_app.format_type

    if format_type == FormatType.RST:
        content = dedent("""
            .. click:source::

                from click import command, echo

                @command
                def cmd1():
                    echo("Command 1")

            .. click:source::

                @command
                def cmd2():
                    echo("Command 2")

            .. click:run::

                invoke(cmd1)

            .. click:run::

                invoke(cmd2)
        """)
    elif format_type == FormatType.MYST:
        content = dedent("""
            ```{click:source}
            from click import command, echo

            @command
            def cmd1():
                echo("Command 1")
            ```

            ```{click:source}
            @command
            def cmd2():
                echo("Command 2")
            ```

            ```{click:run}
            invoke(cmd1)
            ```

            ```{click:run}
            invoke(cmd2)
            ```
        """)

    html_output = sphinx_app.build_document(content)

    assert (
        HTML["shell_session"]
        + '<span class="gp">$ </span>cmd1\n'
        + "Command 1\n"
        + "</pre></div>\n"
    ) in html_output

    assert (
        HTML["shell_session"]
        + '<span class="gp">$ </span>cmd2\n'
        + "Command 2\n"
        + "</pre></div>\n"
    ) in html_output


@pytest.mark.parametrize("var_name", ["invoke", "isolated_filesystem"])
@pytest.mark.parametrize(
    ("sphinx_app", "content", "directive_lineno", "error_lineno"),
    [
        # Test variable conflicts in both rST and MyST formats.
        (
            FormatType.RST,
            """\
            .. click:run::

                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"
            """,
            1,
            4,
        ),
        (
            FormatType.MYST,
            """\
            ```{{click:run}}
            # This should fail due to variable conflict.
            {var_name} = "Do not overwrite me!"
            ```
            """,
            1,
            3,
        ),
        # Check proper line number reporting with preceding lines.
        (
            FormatType.RST,
            """



            .. click:source::

                from click import command, echo

                @command
                def hello():
                    echo("Hello World!")

            .. click:run::

                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"
                result = invoke(hello)
            """,
            9 + 4,
            12 + 4,
        ),
        (
            FormatType.MYST,
            """



            ```{{click:source}}
            from click import command, echo

            @command
            def hello():
                echo("Hello World!")
            ```

            ```{{click:run}}
            # This should fail due to variable conflict.
            {var_name} = "Do not overwrite me!"
            result = invoke(hello)
            ```
            """,
            9 + 4,
            11 + 4,
        ),
        # Check proper line number reporting with blank lines within the directive.
        (
            FormatType.RST,
            """\
            .. click:run::

                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"


            """,
            1,
            4,
        ),
        (
            FormatType.MYST,
            """\
            ```{{click:run}}
            # This should fail due to variable conflict.
            {var_name} = "Do not overwrite me!"


            ```
            """,
            1,
            3,
        ),
        (
            FormatType.RST,
            """\
            .. click:run::



                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"
            """,
            1,
            6,
        ),
        (
            FormatType.MYST,
            """\
            ```{{click:run}}


            # This should fail due to variable conflict.
            {var_name} = "Do not overwrite me!"
            ```
            """,
            1,
            5,
        ),
        # Options should not affect line numbering.
        (
            FormatType.RST,
            """\
            .. click:run::
                :linenos:

                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"
            """,
            1,
            5,
        ),
        (
            FormatType.MYST,
            """\
            ```{{click:run}}
            :linenos:
            # This should fail due to variable conflict.
            {var_name} = "Do not overwrite me!"
            ```
            """,
            1,
            4,
        ),
        (
            FormatType.RST,
            """\
            .. click:run::
                :linenos:
                :lineno-start: 10

                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"
            """,
            1,
            6,
        ),
        (
            FormatType.MYST,
            """\
            ```{{click:run}}
            :linenos:
            :lineno-start: 10
            # This should fail due to variable conflict.
            {var_name} = "Do not overwrite me!"
            ```
            """,
            1,
            5,
        ),
        (
            FormatType.RST,
            """\
            .. click:run::
                :linenos:



                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"
            """,
            1,
            7,
        ),
        (
            FormatType.MYST,
            """\
            ```{{click:run}}
            :linenos:


            # This should fail due to variable conflict.
            {var_name} = "Do not overwrite me!"
            ```
            """,
            1,
            6,
        ),
        (
            FormatType.RST,
            """\
            .. click:run::
                :linenos:

                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"



            """,
            1,
            5,
        ),
        pytest.param(
            FormatType.MYST,
            """\
            ```{{click:run}}
            :linenos:
            # This should fail due to variable conflict.
            {var_name} = "Do not overwrite me!"



            ```
            """,
            1,
            4,
            marks=pytest.mark.xfail(
                reason="MyST line reporting is off: "
                "https://github.com/executablebooks/MyST-Parser/pull/1048",
                # This is going to fail unless MyST is fixed upstream.
                strict=True,
            ),
        ),
    ],
    indirect=["sphinx_app"],
)
def test_directive_variable_conflict(
    var_name, sphinx_app, content, directive_lineno, error_lineno
):
    """Test that variable conflicts are properly detected in real Sphinx environment."""
    format_type = sphinx_app.format_type

    content = dedent(content).format(var_name=var_name)

    with pytest.raises(RuntimeError) as exc_info:
        sphinx_app.build_document(content)

    file_extension = format_type.value
    expected_pattern = (
        rf"Local variable '{var_name}' at .+index"
        + re.escape(file_extension)
        + rf":{directive_lineno}:click:run:{error_lineno} "
        + r"conflicts with the one automatically provided by the click:run directive\.\n"
        rf"Line: {var_name} = \"Do not overwrite me!\""
    )
    assert re.fullmatch(expected_pattern, str(exc_info.value))


def test_exit_exception_percolate(sphinx_app):
    """Test directives that handle command errors and exit codes."""
    format_type = sphinx_app.format_type

    if format_type == FormatType.RST:
        content = dedent("""
            .. click:source::

                import sys

                from click import command, echo, option

                @command
                @option('--fail', is_flag=True, help='Force command to fail')
                def error_command(fail):
                    echo("Starting command...")
                    if fail:
                        echo("Something went wrong!", err=True)
                        sys.exit(1)
                    echo("Command completed successfully")

            .. click:run::

                # Test successful execution
                invoke(error_command, [])

            .. click:run::

                # Test failed execution
                try:
                    invoke(error_command, ['--fail'])
                except SystemExit as e:
                    echo(f"Command exited with code: {e.code}", err=True)
        """)
    elif format_type == FormatType.MYST:
        content = dedent("""
            ```{click:source}
            import sys

            from click import command, echo, option

            @command
            @option('--fail', is_flag=True, help='Force command to fail')
            def error_command(fail):
                echo("Starting command...")
                if fail:
                    echo("Something went wrong!", err=True)
                    sys.exit(1)
                echo("Command completed successfully")
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
                echo(f"Command exited with code: {e.code}", err=True)
            ```
        """)

    html_output = sphinx_app.build_document(content)

    assert (
        HTML["shell_session"]
        + '<span class="gp">$ </span>error<span class="w"> </span>--fail\n'
        + "Starting command...\n"
        + "Something went wrong!\n"
        + "</pre></div>"
    ) in html_output


GITHUB_ALERT_NOTE_TEST_CASE = DirectiveTestCase(
    name="github_alert_note",
    format_type=FormatType.MYST,
    document="""
        > [!NOTE]
        > This is a note.
        > With multiple lines.

        Regular text after.
    """,
    html_matches=admonition_block(
        "note", "<p>This is a note.\nWith multiple lines.</p>\n"
    )
    + "<p>Regular text after.</p>\n",
)

GITHUB_ALERT_TIP_TEST_CASE = DirectiveTestCase(
    name="github_alert_tip",
    format_type=FormatType.MYST,
    document="""
        > [!TIP]
        > This is a tip.
    """,
    html_matches=admonition_block("tip", "<p>This is a tip.</p>\n"),
)

GITHUB_ALERT_IMPORTANT_TEST_CASE = DirectiveTestCase(
    name="github_alert_important",
    format_type=FormatType.MYST,
    document="""
        > [!IMPORTANT]
        > This is important.
    """,
    html_matches=admonition_block("important", "<p>This is important.</p>\n"),
)

GITHUB_ALERT_WARNING_TEST_CASE = DirectiveTestCase(
    name="github_alert_warning",
    format_type=FormatType.MYST,
    document="""
        > [!WARNING]
        > This is a warning.
    """,
    html_matches=admonition_block("warning", "<p>This is a warning.</p>\n"),
)

GITHUB_ALERT_CAUTION_TEST_CASE = DirectiveTestCase(
    name="github_alert_caution",
    format_type=FormatType.MYST,
    document="""
        > [!CAUTION]
        > This is a caution.
    """,
    html_matches=admonition_block("caution", "<p>This is a caution.</p>\n"),
)

GITHUB_ALERT_UNKNOWN_TYPE_TEST_CASE = DirectiveTestCase(
    name="github_alert_unknown_type",
    format_type=FormatType.MYST,
    document="""
        > [!RANDOM]
        > This is not a known alert type.
    """,
    html_matches="<blockquote>\n"
    "<div><p>[!RANDOM]\n"
    "This is not a known alert type.</p>\n"
    "</div></blockquote>\n",
)

GITHUB_ALERT_EMPTY_LINE_TEST_CASE = DirectiveTestCase(
    name="github_alert_empty_line",
    format_type=FormatType.MYST,
    document="""
        > [!NOTE]
        > First paragraph.
        >
        > Second paragraph.
    """,
    html_matches=admonition_block(
        "note", "<p>First paragraph.</p>\n<p>Second paragraph.</p>\n"
    ),
)

GITHUB_ALERT_MULTIPLE_TEST_CASE = DirectiveTestCase(
    name="github_alert_multiple",
    format_type=FormatType.MYST,
    document="""
        > [!NOTE]
        > A note.

        Some text between.

        > [!WARNING]
        > A warning.
    """,
    html_matches=admonition_block("note", "<p>A note.</p>\n")
    + "<p>Some text between.</p>\n"
    + admonition_block("warning", "<p>A warning.</p>\n"),
)

GITHUB_ALERT_EXTRA_SPACES_TEST_CASE = DirectiveTestCase(
    name="github_alert_extra_spaces",
    format_type=FormatType.MYST,
    document="""
        > [!NOTE]
        >  This line has an extra space after >.
        >   This line has two extra spaces.
        >    This line has three extra spaces.
    """,
    html_matches=admonition_block(
        "note",
        "<p>This line has an extra space after &gt;.\n"
        "This line has two extra spaces.\n"
        "This line has three extra spaces.</p>\n",
    ),
)

GITHUB_ALERT_NO_SPACE_AFTER_CHEVRON_TEST_CASE = DirectiveTestCase(
    name="github_alert_no_space_after_chevron",
    format_type=FormatType.MYST,
    document="""
        >[!TIP]
        > This alert has no space after the chevron on the first line.
    """,
    html_matches=admonition_block(
        "tip",
        "<p>This alert has no space after the chevron on the first line.</p>\n",
    ),
)

GITHUB_ALERT_NO_SPACE_AFTER_BRACKET_TEST_CASE = DirectiveTestCase(
    name="github_alert_no_space_after_bracket",
    format_type=FormatType.MYST,
    document="""
        > [!TIP]
        >No space after the bracket.
    """,
    html_matches=admonition_block("tip", "<p>No space after the bracket.</p>\n"),
)

GITHUB_ALERT_MIXED_SPACING_TEST_CASE = DirectiveTestCase(
    name="github_alert_mixed_spacing",
    format_type=FormatType.MYST,
    document="""
        > [!WARNING]
        > Normal spacing.
        >  Extra space.
        >No space.
        >   Lots of spaces.
    """,
    html_matches=admonition_block(
        "warning",
        "<p>Normal spacing.\nExtra space.\nNo space.\nLots of spaces.</p>\n",
    ),
)

GITHUB_ALERT_LEADING_SPACES_TEST_CASE = DirectiveTestCase(
    name="github_alert_leading_spaces",
    format_type=FormatType.MYST,
    document="""
        >    [!TIP]
        > This alert has extra spaces before the directive.
    """,
    html_matches=admonition_block(
        "tip",
        "<p>This alert has extra spaces before the directive.</p>\n",
    ),
)

GITHUB_ALERT_INVALID_SPACE_AFTER_BANG_TEST_CASE = DirectiveTestCase(
    name="github_alert_invalid_space_after_bang",
    format_type=FormatType.MYST,
    document="""
        > [! TIP]
        > This should remain a regular blockquote.
    """,
    html_matches="<blockquote>\n"
    "<div><p>[! TIP]\n"
    "This should remain a regular blockquote.</p>\n"
    "</div></blockquote>\n",
)

GITHUB_ALERT_INVALID_SPACE_BEFORE_BANG_TEST_CASE = DirectiveTestCase(
    name="github_alert_invalid_space_before_bang",
    format_type=FormatType.MYST,
    document="""
        > [ !TIP]
        > This should remain a regular blockquote.
    """,
    html_matches="<blockquote>\n"
    "<div><p>[ !TIP]\n"
    "This should remain a regular blockquote.</p>\n"
    "</div></blockquote>\n",
)

GITHUB_ALERT_INVALID_SPACE_BEFORE_BRACKET_TEST_CASE = DirectiveTestCase(
    name="github_alert_invalid_space_before_bracket",
    format_type=FormatType.MYST,
    document="""
        > [!TIP ]
        > This should remain a regular blockquote.
    """,
    html_matches="<blockquote>\n"
    "<div><p>[!TIP ]\n"
    "This should remain a regular blockquote.</p>\n"
    "</div></blockquote>\n",
)

GITHUB_ALERT_INVALID_LOWERCASE_TEST_CASE = DirectiveTestCase(
    name="github_alert_invalid_lowercase",
    format_type=FormatType.MYST,
    document="""
        > [!tip]
        > This should remain a regular blockquote.
    """,
    html_matches="<blockquote>\n"
    "<div><p>[!tip]\n"
    "This should remain a regular blockquote.</p>\n"
    "</div></blockquote>\n",
)

GITHUB_ALERT_DUPLICATE_DIRECTIVE_TEST_CASE = DirectiveTestCase(
    name="github_alert_duplicate_directive",
    format_type=FormatType.MYST,
    document="""
        > [!TIP]
        > [!TIP]
        > Hello.
    """,
    html_matches=admonition_block("tip", "<p>[!TIP]\nHello.</p>\n"),
)

GITHUB_ALERT_EMPTY_DIRECTIVE_TEST_CASE = DirectiveTestCase(
    name="github_alert_empty_directive",
    format_type=FormatType.MYST,
    document="""
        > [!TIP]
    """,
    html_matches='          <div class="body" role="main">\n'
    "            \n"
    "  \n"
    "\n"
    "          </div>\n",
)


GITHUB_ALERT_INVALID_TEXT_BEFORE_TEST_CASE = DirectiveTestCase(
    name="github_alert_invalid_text_before",
    format_type=FormatType.MYST,
    document="""
        > Hello [!NOTE] This is a note.
    """,
    html_matches="<blockquote>\n"
    "<div><p>Hello [!NOTE] This is a note.</p>\n"
    "</div></blockquote>\n",
)

GITHUB_ALERT_IN_CODE_BLOCK_TEST_CASE = DirectiveTestCase(
    name="github_alert_in_code_block",
    format_type=FormatType.MYST,
    document="""
        ```markdown
        > [!NOTE]
        > This is inside a code block and should not be converted.
        ```
    """,
    html_matches=HTML["markdown_highlight"]
    + '<span class="k">&gt; </span><span class="ge">[!NOTE]</span>\n'
    '<span class="k">&gt; </span><span class="ge">This is inside a code block and should not be converted.</span>\n'
    "</pre></div>\n"
    "</div>\n",
)

GITHUB_ALERT_IN_CODE_BLOCK_TILDE_TEST_CASE = DirectiveTestCase(
    name="github_alert_in_code_block_tilde",
    format_type=FormatType.MYST,
    document="""
        ~~~markdown
        > [!NOTE]
        > This is inside a tilde code block.
        ~~~
    """,
    html_matches=HTML["markdown_highlight"]
    + '<span class="k">&gt; </span><span class="ge">[!NOTE]</span>\n'
    '<span class="k">&gt; </span><span class="ge">This is inside a tilde code block.</span>\n'
    "</pre></div>\n",
)

GITHUB_ALERT_IN_CODE_BLOCK_NO_LANGUAGE_TEST_CASE = DirectiveTestCase(
    name="github_alert_in_code_block_no_language",
    format_type=FormatType.MYST,
    document="""
        ```
        > [!TIP]
        > This is inside a code block without language.
        ```
    """,
    html_matches='<div class="highlight-default notranslate"><div class="highlight"><pre><span></span>'
    "&gt; [!TIP]\n"
    "&gt; This is inside a code block without language.\n"
    "</pre></div>\n",
)

GITHUB_ALERT_IN_CODE_BLOCK_FOUR_BACKTICKS_TEST_CASE = DirectiveTestCase(
    name="github_alert_in_code_block_four_backticks",
    format_type=FormatType.MYST,
    document="""
        ````markdown
        > [!WARNING]
        > This is inside a 4-backtick code block.
        ```
        nested code fence
        ```
        ````
    """,
    html_matches=HTML["markdown_highlight"]
    + '<span class="k">&gt; </span><span class="ge">[!WARNING]</span>\n'
    '<span class="k">&gt; </span><span class="ge">This is inside a 4-backtick code block.</span>\n'
    '<span class="sb">```</span>\n'
    '<span class="sb">nested code fence</span>\n'
    '<span class="sb">```</span>\n'
    "</pre></div>\n"
    "</div>\n",
)

GITHUB_ALERT_IN_CODE_BLOCK_DIRECTIVE_TEST_CASE = DirectiveTestCase(
    name="github_alert_in_code_block_directive",
    format_type=FormatType.MYST,
    document="""
        ```{code-block} markdown
        > [!NOTE]
        > This is inside a code-block directive and should not be converted.
        ```
    """,
    html_matches=HTML["markdown_highlight"]
    + '<span class="k">&gt; </span><span class="ge">[!NOTE]</span>\n'
    '<span class="k">&gt; </span><span class="ge">This is inside a code-block directive and should not be converted.</span>\n'
    "</pre></div>\n"
    "</div>\n",
)

GITHUB_ALERT_IN_INDENTED_CODE_BLOCK_4_SPACES_TEST_CASE = DirectiveTestCase(
    name="github_alert_in_indented_code_block_4_spaces",
    format_type=FormatType.MYST,
    document="""
        Some text before.

            > [!TIP]
            > This is inside a code block without language.

        Some text after.
    """,
    # 4-space indentation creates a code block in Markdown.
    html_matches="<p>Some text before.</p>\n"
    '<div class="highlight-none notranslate"><div class="highlight"><pre><span></span>'
    "&gt; [!TIP]\n"
    "&gt; This is inside a code block without language.\n"
    "</pre></div>\n"
    "</div>\n"
    "<p>Some text after.</p>\n",
)

GITHUB_ALERT_IN_INDENTED_CODE_BLOCK_2_SPACES_TEST_CASE = DirectiveTestCase(
    name="github_alert_in_indented_code_block_2_spaces",
    format_type=FormatType.MYST,
    document="""
        Some text before.

          > [!TIP]
          > This is inside a 2-space indented block.

        Some text after.
    """,
    # 2-space indentation is not enough to create a code block, so the alert
    # is converted.
    html_matches="<p>Some text before.</p>\n"
    + admonition_block("tip", "<p>This is inside a 2-space indented block.</p>\n")
    + "<p>Some text after.</p>\n",
)

GITHUB_ALERT_MIXED_CODE_BLOCKS_TEST_CASE = DirectiveTestCase(
    name="github_alert_mixed_code_blocks",
    format_type=FormatType.MYST,
    document="""
        > [!NOTE]
        > This should be converted to an admonition.

        ```markdown
        > [!NOTE]
        > This should NOT be converted (inside code block).
        ```

        > [!WARNING]
        > This should also be converted to an admonition.

        ~~~markdown
        > [!WARNING]
        > This should NOT be converted (inside tilde block).
        ~~~

        > [!TIP]
        > Final admonition.
    """,
    # First alert - converted
    html_matches=admonition_block(
        "note", "<p>This should be converted to an admonition.</p>\n"
    )
    # Code block - not converted
    + HTML["markdown_highlight"]
    + '<span class="k">&gt; </span><span class="ge">[!NOTE]</span>\n'
    '<span class="k">&gt; </span><span class="ge">This should NOT be converted (inside code block).</span>\n'
    "</pre></div>\n"
    "</div>\n"
    # Second alert - converted
    + admonition_block(
        "warning", "<p>This should also be converted to an admonition.</p>\n"
    )
    # Tilde code block - not converted
    + HTML["markdown_highlight"]
    + '<span class="k">&gt; </span><span class="ge">[!WARNING]</span>\n'
    '<span class="k">&gt; </span><span class="ge">This should NOT be converted (inside tilde block).</span>\n'
    "</pre></div>\n"
    "</div>\n"
    # Third alert - converted
     + admonition_block("tip", "<p>Final admonition.</p>\n"),
)


@pytest.mark.parametrize(
    "test_case",
    [
        GITHUB_ALERT_NOTE_TEST_CASE,
        GITHUB_ALERT_TIP_TEST_CASE,
        GITHUB_ALERT_IMPORTANT_TEST_CASE,
        GITHUB_ALERT_WARNING_TEST_CASE,
        GITHUB_ALERT_CAUTION_TEST_CASE,
        GITHUB_ALERT_UNKNOWN_TYPE_TEST_CASE,
        GITHUB_ALERT_EMPTY_LINE_TEST_CASE,
        GITHUB_ALERT_MULTIPLE_TEST_CASE,
        GITHUB_ALERT_EXTRA_SPACES_TEST_CASE,
        GITHUB_ALERT_NO_SPACE_AFTER_CHEVRON_TEST_CASE,
        GITHUB_ALERT_NO_SPACE_AFTER_BRACKET_TEST_CASE,
        GITHUB_ALERT_MIXED_SPACING_TEST_CASE,
        GITHUB_ALERT_LEADING_SPACES_TEST_CASE,
        GITHUB_ALERT_INVALID_SPACE_AFTER_BANG_TEST_CASE,
        GITHUB_ALERT_INVALID_SPACE_BEFORE_BANG_TEST_CASE,
        GITHUB_ALERT_INVALID_SPACE_BEFORE_BRACKET_TEST_CASE,
        GITHUB_ALERT_INVALID_LOWERCASE_TEST_CASE,
        GITHUB_ALERT_DUPLICATE_DIRECTIVE_TEST_CASE,
        GITHUB_ALERT_EMPTY_DIRECTIVE_TEST_CASE,
        GITHUB_ALERT_INVALID_TEXT_BEFORE_TEST_CASE,
        GITHUB_ALERT_IN_CODE_BLOCK_TEST_CASE,
        GITHUB_ALERT_IN_CODE_BLOCK_TILDE_TEST_CASE,
        GITHUB_ALERT_IN_CODE_BLOCK_NO_LANGUAGE_TEST_CASE,
        GITHUB_ALERT_IN_CODE_BLOCK_FOUR_BACKTICKS_TEST_CASE,
        GITHUB_ALERT_IN_CODE_BLOCK_DIRECTIVE_TEST_CASE,
        GITHUB_ALERT_IN_INDENTED_CODE_BLOCK_4_SPACES_TEST_CASE,
        GITHUB_ALERT_IN_INDENTED_CODE_BLOCK_2_SPACES_TEST_CASE,
        GITHUB_ALERT_MIXED_CODE_BLOCKS_TEST_CASE,
    ],
)
def test_github_alert_conversion(sphinx_app, test_case):
    """Test GitHub alert syntax is converted to MyST directives."""
    if not test_case.supports_format(sphinx_app.format_type):
        pytest.skip(
            f"Test case '{test_case.name}' only supports {test_case.format_type}"
        )

    content = sphinx_app.generate_test_content(test_case)
    html_output = sphinx_app.build_document(content)

    for fragment in test_case.html_matches:
        assert fragment in html_output


def test_github_alert_no_colon_fence(tmp_path):
    """Test that ConfigError is raised when colon_fence is not enabled."""

    srcdir = tmp_path / "source"
    outdir = tmp_path / "build"
    doctreedir = outdir / ".doctrees"

    srcdir.mkdir()
    outdir.mkdir()

    # Configuration without colon_fence
    conf = {
        "master_doc": "index",
        "extensions": ["click_extra.sphinx", "myst_parser"],
        "myst_enable_extensions": [],  # Missing colon_fence
    }
    config_content = "\n".join(f"{key} = {repr(value)}" for key, value in conf.items())
    (srcdir / "conf.py").write_text(config_content)

    content = dedent("""
        > [!NOTE]
        > This should fail.
    """)
    (srcdir / "index.md").write_text(content)

    with docutils_namespace():
        app = Sphinx(
            str(srcdir),
            str(srcdir),
            str(outdir),
            str(doctreedir),
            "html",
            verbosity=0,
            warning=None,
        )
        with pytest.raises(ConfigError) as exc_info:
            app.build()

        assert "colon_fence" in str(exc_info.value)


def test_content_without_alerts_unchanged(sphinx_app_myst):
    """Test that content without GitHub alerts passes through unchanged."""
    content = dedent("""
        # Regular Heading

        Regular paragraph text.

        > Regular blockquote without alert syntax.

        ```python
        print("code block")
        ```
    """)

    html_output = sphinx_app_myst.build_document(content)

    expected_fragments = (
        "<h1>Regular Heading",
        "<p>Regular paragraph text.</p>",
        "<blockquote>\n<div><p>Regular blockquote without alert syntax.</p>\n</div></blockquote>",
        HTML["python_highlight"]
        + '<span class="nb">print</span><span class="p">(</span><span class="s2">&quot;code block&quot;</span><span class="p">)</span>\n'
        + "</pre></div>",
    )

    for fragment in expected_fragments:
        assert fragment in html_output


def test_github_alert_in_included_file(sphinx_app_myst_with_include):
    """Test that GitHub alerts in included files are properly converted."""
    sphinx_app, srcdir = sphinx_app_myst_with_include

    included_content = dedent("""\
        > [!NOTE]
        > This note is from an included file.

        Some regular text.

        > [!WARNING]
        > This warning is also from the included file.
    """)
    (srcdir / "included.md").write_text(included_content)

    main_content = dedent("""\
        # Main Document

        ```{include} included.md
        ```

        Text after include.
    """)

    html_output = sphinx_app.build_document(main_content)

    expected = (
        admonition_block("note", "<p>This note is from an included file.</p>\n")
        + "<p>Some regular text.</p>\n"
        + admonition_block(
            "warning", "<p>This warning is also from the included file.</p>\n"
        )
        + "<p>Text after include.</p>\n"
    )

    assert expected in html_output


def test_github_alert_in_included_file_with_start_after(sphinx_app_myst_with_include):
    """Test GitHub alerts in included files with :start-after: option."""
    sphinx_app, srcdir = sphinx_app_myst_with_include

    included_content = dedent("""\
        # Header to Skip

        This content should be skipped.

        <!-- start-content -->

        > [!TIP]
        > This tip appears after the marker.

        Important information here.
    """)
    (srcdir / "partial.md").write_text(included_content)

    main_content = dedent("""\
        # Documentation

        ```{include} partial.md
        :start-after: <!-- start-content -->
        ```
    """)

    html_output = sphinx_app.build_document(main_content)

    # The skipped content should not appear
    assert "Header to Skip" not in html_output
    assert "This content should be skipped" not in html_output

    # Check the expected content is present
    expected = (
        admonition_block("tip", "<p>This tip appears after the marker.</p>\n")
        + "<p>Important information here.</p>\n"
    )
    assert expected in html_output


def test_github_alert_in_included_file_with_end_before(sphinx_app_myst_with_include):
    """Test GitHub alerts in included files with :end-before: option."""
    sphinx_app, srcdir = sphinx_app_myst_with_include

    included_content = dedent("""\
        > [!IMPORTANT]
        > This important note should be included.

        <!-- end-content -->

        > [!CAUTION]
        > This caution should NOT be included.
    """)
    (srcdir / "partial_end.md").write_text(included_content)

    main_content = dedent("""\
        # Documentation

        ```{include} partial_end.md
        :end-before: <!-- end-content -->
        ```
    """)

    html_output = sphinx_app.build_document(main_content)

    # Check the expected content is present
    expected = admonition_block(
        "important", "<p>This important note should be included.</p>\n"
    )
    assert expected in html_output

    # The content after the marker should not appear
    assert "admonition caution" not in html_output
    assert "This caution should NOT be included" not in html_output


def test_github_alert_in_included_file_nested_directory(sphinx_app_myst_with_include):
    """Test GitHub alerts in included files from nested directories."""
    sphinx_app, srcdir = sphinx_app_myst_with_include

    docs_dir = srcdir / "docs"
    docs_dir.mkdir()

    included_content = dedent("""\
        > [!NOTE]
        > This note is from a nested directory.
    """)
    (docs_dir / "nested.md").write_text(included_content)

    main_content = dedent("""\
        # Main Document

        ```{include} docs/nested.md
        ```
    """)

    html_output = sphinx_app.build_document(main_content)

    expected = admonition_block(
        "note", "<p>This note is from a nested directory.</p>\n"
    )
    assert expected in html_output


def test_github_alert_in_included_file_with_code_block(sphinx_app_myst_with_include):
    """Test that code blocks in included files preserve GitHub alert syntax."""
    sphinx_app, srcdir = sphinx_app_myst_with_include

    included_content = dedent("""\
        > [!NOTE]
        > This should be converted to an admonition.

        ```markdown
        > [!NOTE]
        > This should stay as code.
        ```

        > [!TIP]
        > This should also be converted.
    """)
    (srcdir / "mixed.md").write_text(included_content)

    main_content = dedent("""\
        ```{include} mixed.md
        ```
    """)

    html_output = sphinx_app.build_document(main_content)

    expected = (
        admonition_block("note", "<p>This should be converted to an admonition.</p>\n")
        + HTML["markdown_highlight"]
        + '<span class="k">&gt; </span><span class="ge">[!NOTE]</span>\n'
        '<span class="k">&gt; </span><span class="ge">This should stay as code.</span>\n'
        "</pre></div>\n"
        "</div>\n" + admonition_block("tip", "<p>This should also be converted.</p>\n")
    )
    assert expected in html_output


def test_github_alert_mixed_direct_and_included(sphinx_app_myst_with_include):
    """Test mixing direct GitHub alerts with included file alerts."""
    sphinx_app, srcdir = sphinx_app_myst_with_include

    included_content = dedent("""\
        > [!WARNING]
        > Warning from included file.
    """)
    (srcdir / "warning.md").write_text(included_content)

    main_content = dedent("""\
        > [!NOTE]
        > Direct note in main document.

        ```{include} warning.md
        ```

        > [!TIP]
        > Another direct tip.
    """)

    html_output = sphinx_app.build_document(main_content)

    expected = (
        admonition_block("note", "<p>Direct note in main document.</p>\n")
        + admonition_block("warning", "<p>Warning from included file.</p>\n")
        + admonition_block("tip", "<p>Another direct tip.</p>\n")
    )
    assert expected in html_output
