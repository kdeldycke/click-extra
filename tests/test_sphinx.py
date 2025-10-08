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
from enum import StrEnum
from inspect import cleandoc
from pathlib import Path
from textwrap import dedent, indent
from typing import Generator, Sequence

import pytest
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace


class FormatType(StrEnum):
    """Sphinx document format types and their file extensions."""

    RST = ".rst"
    MYST = ".md"


RST = FormatType.RST
MYST = FormatType.MYST


class SphinxAppWrapper:
    """Wrapper around Sphinx application with additional testing methods."""

    def __init__(self, app: Sphinx, format_type: FormatType):
        self.app = app
        self.format_type = format_type
        # Delegate all other attributes to the wrapped app.
        self._app = app

    def __getattr__(self, name):
        """Delegate attribute access to the wrapped Sphinx app."""
        return getattr(self._app, name)

    @classmethod
    def create(
        cls, format_type: FormatType, tmp_path
    ) -> Generator[SphinxAppWrapper, None, None]:
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
        if format_type == MYST:
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
            # Return wrapped app instead of raw Sphinx app.
            yield cls(app, format_type)

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

        # Produce click:example and click:run directives in the appropriate format.
        lines = []

        if test_case.example_block:
            if self.format_type == RST:
                lines.append(".. click:example::")
                # We need a blank line if there are no options.
                if not test_case.example_block.startswith(":"):
                    lines.append("")
                lines.append(indent(test_case.example_block, " " * 4))
            elif self.format_type == MYST:
                lines += [
                    "```{click:example}",
                    test_case.example_block,
                    "```",
                ]

        # Separate directives with a blank line.
        if lines:
            lines.append("")

        if test_case.run_block:
            if self.format_type == RST:
                lines.append(".. click:run::")
                # We need a blank line if there are no options.
                if not test_case.run_block.startswith(":"):
                    lines.append("")
                lines.append(indent(test_case.run_block, " " * 4))
            elif self.format_type == MYST:
                lines += [
                    "```{click:run}",
                    test_case.run_block,
                    "```",
                ]

        return "\n".join(lines)


@pytest.fixture(params=[RST, MYST])
def sphinx_app(request, tmp_path):
    """Create a Sphinx application for testing."""
    yield from SphinxAppWrapper.create(request.param, tmp_path)


@pytest.fixture
def sphinx_app_rst(tmp_path):
    """Create a Sphinx application for testing RST format only."""
    yield from SphinxAppWrapper.create(RST, tmp_path)


@pytest.fixture
def sphinx_app_myst(tmp_path):
    """Create a Sphinx application for testing MyST format only."""
    yield from SphinxAppWrapper.create(MYST, tmp_path)


@dataclass
class DirectiveTestCase:
    """Test case data for directive tests."""

    name: str
    format_type: FormatType | None = None
    example_block: str | None = None
    run_block: str | None = None
    document: str | None = None
    html_matches: Sequence[str] | None = None

    def __post_init__(self):
        self.html_matches = self.html_matches or tuple()

        # Validate mutually exclusive options
        if self.document is not None:
            if self.example_block is not None or self.run_block is not None:
                raise ValueError(
                    "DirectiveTestCase: 'document' cannot be used with 'example_block' or 'run_block'"
                )
            if self.format_type is None:
                raise ValueError(
                    "DirectiveTestCase: 'format_type' must be specified when using 'document'"
                )

        # Dedent code fields to remove leading and trailing whitespace.
        if self.example_block:
            self.example_block = cleandoc(self.example_block)
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


# Common HTML fragments for assertions.
HTML = {
    "python_highlight": '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>',
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
    example_block="""
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
    example_block="""
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
    example_block="""
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
    # Test that :hide-source: hides source code in click:example directive.
    name="hide_source",
    example_block="""
        :hide-source:

        from click import command, echo

        @command
        def simple_print():
            echo("Just a string to print.")
    """,
    run_block="invoke(simple_print)",
    html_matches=(
        # Check from the start of the body to make sure the click:example is gone.
        '          <div class="body" role="main">\n'
        + "            \n  "
        + HTML["shell_session"]
        + '<span class="gp">$ </span>simple-print\n'
        + "Just a string to print.\n"
        + "</pre></div>\n",
    ),
)

SHOW_SOURCE_TEST_CASE = DirectiveTestCase(
    # Test that :show-source: option shows source code in click:run directive.
    name="show_source",
    example_block="""
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
        # Example directive should show source.
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
    example_block="""
        from click import command, echo

        @command
        def simple_print():
            echo("Just a string to print.")
    """,
    run_block="""
        :hide-results:

        invoke(simple_print)
    """,
    html_matches=(
        # Example directive should show source.
        (
            HTML["python_highlight"]
            + HTML["import_click"]
            + "\n"
            + '<span class="nd">@command</span>\n'
            + '<span class="k">def</span><span class="w"> </span><span class="nf">simple_print</span><span class="p">():</span>\n'
            + '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;Just a string to print.&quot;</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
    ),
)

SHOW_RESULTS_TEST_CASE = DirectiveTestCase(
    # Test that :show-results: option shows execution results (default behavior).
    name="show_results",
    example_block="""
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
        # Example directive should show source.
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
    example_block="""
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
        # Example directive should show source.
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
    example_block="""
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
    html_matches=(
        # Should show mixed stdout/stderr output with colors.
        (
            HTML["shell_session"]
            + '<span class="gp">$ </span>mixed-output\n'
            + 'This goes to <span class=" -Color -Color-Blue -C-Blue">stdout</span>\n'
            + 'This is an <span class=" -Color -Color-Red -C-Red">error</span>\n'
            + 'Direct <span class=" -Color -Color-Blue -C-Blue">stdout</span> print\n'
            + 'Direct <span class=" -Color -Color-Red -C-Red">stderr</span> print\n'
            + "</pre></div>"
        ),
    ),
)

ISOLATED_FILESYSTEM_TEST_CASE = DirectiveTestCase(
    # Test that isolated_filesystem works properly in click:run directives.
    name="isolated_filesystem",
    example_block="""
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
    html_matches=(
        # Should show command execution within isolated filesystem.
        (
            HTML["shell_session"]
            + '<span class="gp">$ </span>greet\n'
            + "Hello World!\n"
            + "</pre></div>\n"
        ),
    ),
)

RST_WITHIN_MYST_EVAL_TEST_CASE = DirectiveTestCase(
    name="rst_within_myst_eval",
    format_type=MYST,  # This test is MyST-specific but contains embedded RST
    document="""
        ```{eval-rst}
        .. click:example::

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
    ids=lambda tc: tc.name,
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
        .. click:example::
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

    if format_type == RST:
        content = dedent("""
            .. click:example::

                from click import command, echo, option

                @command
                @option("--name")
                def sql_output(name):
                    sql_query = f"SELECT * FROM users WHERE name = '{name}';"
                    echo(sql_query)

            .. click:run:: sql

                invoke(sql_output, args=["--name", "Joe"])
        """)
    elif format_type == MYST:
        content = dedent("""
            ```{click:example}
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

    if format_type == RST:
        content = dedent("""
            .. click:example::

                from click import command, echo

                @command
                def cmd1():
                    echo("Command 1")

            .. click:example::

                @command
                def cmd2():
                    echo("Command 2")

            .. click:run::

                invoke(cmd1)

            .. click:run::

                invoke(cmd2)
        """)
    elif format_type == MYST:
        content = dedent("""
            ```{click:example}
            from click import command, echo

            @command
            def cmd1():
                echo("Command 1")
            ```

            ```{click:example}
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
            RST,
            """\
            .. click:run::

                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"
            """,
            1,
            4,
        ),
        (
            MYST,
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
            RST,
            """



            .. click:example::

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
            MYST,
            """



            ```{{click:example}}
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
            RST,
            """\
            .. click:run::

                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"


            """,
            1,
            4,
        ),
        (
            MYST,
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
            RST,
            """\
            .. click:run::



                # This should fail due to variable conflict.
                {var_name} = "Do not overwrite me!"
            """,
            1,
            6,
        ),
        (
            MYST,
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
            RST,
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
            MYST,
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
            RST,
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
            MYST,
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
            RST,
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
            MYST,
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
            RST,
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
            MYST,
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
        + r"conflicts with the one automaticcaly provided by the click:run directive\.\n"
        rf"Line: {var_name} = \"Do not overwrite me!\""
    )
    assert re.fullmatch(expected_pattern, str(exc_info.value))


def test_exit_exception_percolate(sphinx_app):
    """Test directives that handle command errors and exit codes."""
    format_type = sphinx_app.format_type

    if format_type == RST:
        content = dedent("""
            .. click:example::

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
    elif format_type == MYST:
        content = dedent("""
            ```{click:example}
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
