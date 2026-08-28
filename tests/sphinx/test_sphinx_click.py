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
"""Tests for Sphinx directives click:source and click:run in rST and MyST formats."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from textwrap import dedent

import click
import pytest
from docutils import nodes
from pygments.styles import get_style_by_name

from click_extra.screenshot import (
    CAPTURE_BACKGROUND,
    LIGHT_CAPTURE_BACKGROUND,
    CaptureBackground,
)
from click_extra.snippet import DEFAULT_SYNTAX_STYLES
from click_extra.sphinx.click import (
    SCREENSHOT_MARKER_END,
    SCREENSHOT_MARKER_START,
    ClickRunner,
    _rewrite_screenshot_regions,
    _screenshot_background,
    _screenshot_columns,
    _screenshot_opacity,
    program_from_command_line,
)
from click_extra.spinner_presets import SPINNERS

from .conftest import (
    HTML,
    DirectiveTestCase,
    FormatType,
    format_params,
    unescape_quotes,
)

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

EMPHASIZE_LINES_TEST_CASE = DirectiveTestCase(
    # Test that :emphasize-lines: applies to source only and
    # :emphasize-result-lines: applies to results only, independently.
    name="emphasize_lines_split",
    source_block="""
        from click import command, echo

        @command
        def two_liner():
            echo("first line")
            echo("second line")
    """,
    run_block="""
        :show-source:
        :emphasize-lines: 1
        :emphasize-result-lines: 3

        invoke(two_liner)
    """,
    html_matches=(
        # Source code-block from click:source has no emphasis.
        (
            HTML["python_highlight"]
            + HTML["import_click"]
            + "\n"
            + '<span class="nd">@command</span>\n'
            + '<span class="k">def</span><span class="w"> </span><span class="nf">two_liner</span><span class="p">():</span>\n'
            + '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;first line&quot;</span><span class="p">)</span>\n'
            + '    <span class="n">echo</span><span class="p">(</span><span class="s2">&quot;second line&quot;</span><span class="p">)</span>\n'
            + "</pre></div>\n"
        ),
        # Run directive's source block: line 1 (the only line) is highlighted.
        (
            HTML["python_highlight"]
            + '<span class="hll"><span class="n">invoke</span><span class="p">(</span><span class="n">two_liner</span><span class="p">)</span>\n</span>'
            + "</pre></div>\n"
        ),
        # Run directive's result block: line 3 ("second line") is highlighted,
        # not the prompt or "first line".
        (
            HTML["shell_session"]
            + '<span class="gp">$ </span>two-liner\n'
            + "first line\n"
            + '<span class="hll">second line\n</span>'
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
    + 'This goes to <span class="-Ansi -Ansi-Blue">stdout</span>\n'
    + 'This is an <span class="-Ansi -Ansi-Red">error</span>\n'
    + 'Direct <span class="-Ansi -Ansi-Blue">stdout</span> print\n'
    + 'Direct <span class="-Ansi -Ansi-Red">stderr</span> print\n'
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


@pytest.mark.parametrize(
    ("sphinx_app_for_format", "test_case"),
    format_params(
        BASIC_DIRECTIVES_TEST_CASE,
        EMPHASIZE_LINES_TEST_CASE,
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
    ),
    indirect=["sphinx_app_for_format"],
)
def test_directive_functionality(sphinx_app_for_format, test_case):
    """Test standard directive functionalities in each format a case targets."""
    content = sphinx_app_for_format.generate_test_content(test_case)
    html_output = sphinx_app_for_format.build_document(content)

    # Assert all expected fragments are present.
    for fragment in test_case.html_matches:
        assert unescape_quotes(fragment) in unescape_quotes(html_output)


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

    expected = (
        HTML["sql_highlight"]
        + '<span class="err">$</span><span class="w"> </span><span class="k">sql</span><span class="o">-</span><span class="k">output</span><span class="w"> </span><span class="c1">--name Joe</span>\n'
        + '<span class="k">SELECT</span><span class="w"> </span><span class="o">*</span><span class="w"> </span><span class="k">FROM</span><span class="w"> </span><span class="n">users</span><span class="w"> </span><span class="k">WHERE</span><span class="w"> </span><span class="n">name</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s1">&#39;Joe&#39;</span><span class="p">;</span>\n'
        + "</pre></div>\n"
    )
    assert unescape_quotes(expected) in unescape_quotes(html_output)


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
    ("sphinx_app_for_format", "content", "directive_lineno", "error_lineno"),
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
    ],
    indirect=["sphinx_app_for_format"],
)
def test_directive_variable_conflict(
    var_name, sphinx_app_for_format, content, directive_lineno, error_lineno
):
    """Test that variable conflicts are properly detected in real Sphinx environment."""
    format_type = sphinx_app_for_format.format_type

    content = dedent(content).format(var_name=var_name)

    with pytest.raises(RuntimeError) as exc_info:
        sphinx_app_for_format.build_document(content)

    file_extension = format_type.value
    expected_pattern = (
        rf"Local variable '{var_name}' at .+index"
        + re.escape(file_extension)
        + rf":{directive_lineno}:click:run:{error_lineno} "
        + r"conflicts with the one automatically provided by the click:run directive\.\n"
        rf"Line: {var_name} = \"Do not overwrite me!\""
    )
    assert re.fullmatch(expected_pattern, str(exc_info.value))


GENERATED_BLOCK_ANCHOR = "from click_extra import command, echo"
"""First body line of the ``GENERATED_BLOCK_LINE_CASES`` documents below.

The line a generated block is expected to be attributed to, located in the
document itself so editing a case moves the expectation with it.
"""

GENERATED_BLOCK_LINE_CASES = format_params(
    DirectiveTestCase(
        name="plain-body",
        format_type=FormatType.RST,
        document=f"""
            Title
            =====

            Filler paragraph.

            .. click:run::
               :emphasize-result-lines: 1

               {GENERATED_BLOCK_ANCHOR}

               @command
               def hello():
                   echo("Hello")

               invoke(hello, args=[])
        """,
    ),
    DirectiveTestCase(
        name="plain-body",
        format_type=FormatType.MYST,
        document=f"""
            # Title

            Filler paragraph.

            ```{{click:run}}
            :emphasize-result-lines: 1

            {GENERATED_BLOCK_ANCHOR}

            @command
            def hello():
                echo("Hello")

            invoke(hello, args=[])
            ```
        """,
    ),
    DirectiveTestCase(
        name="body-ending-on-blank-lines",
        format_type=FormatType.RST,
        document=f"""
            Title
            =====

            Filler paragraph.

            .. click:run::
               :emphasize-result-lines: 1

               {GENERATED_BLOCK_ANCHOR}

               @command
               def hello():
                   echo("Hello")

               invoke(hello, args=[])


            Trailer paragraph.
        """,
    ),
    DirectiveTestCase(
        name="body-ending-on-blank-lines",
        format_type=FormatType.MYST,
        document=f"""
            # Title

            Filler paragraph.

            ```{{click:run}}
            :emphasize-result-lines: 1

            {GENERATED_BLOCK_ANCHOR}

            @command
            def hello():
                echo("Hello")

            invoke(hello, args=[])


            ```
        """,
    ),
)


@pytest.mark.parametrize(
    ("sphinx_app_for_format", "test_case"),
    GENERATED_BLOCK_LINE_CASES,
    indirect=["sphinx_app_for_format"],
)
def test_generated_block_is_attributed_to_the_directive_body(
    sphinx_app_for_format, test_case
):
    """A block a directive generates is attributed to its first body line.

    The generated lines exist nowhere in the document, so the parser has to be
    told which document line to hang a diagnostic raised inside them on. Both
    formats must answer the same way, and neither is free to fall back on its
    own default: docutils numbers an unlabelled block from the top of the
    *file*, and ``myst-parser`` measures its offsets from the directive rather
    than the document.

    The last two cases pin the ``content_offset`` inflation
    ``click_extra.sphinx.click.MYST_CONTENT_OFFSET_INFLATED_MAX`` documents,
    which only fires on a directive carrying both an option block and a body
    ending in blank lines.
    """
    document = test_case.document
    sphinx_app_for_format.build_document(document)

    expected_line = next(
        number
        for number, line in enumerate(document.splitlines(), start=1)
        if line.strip() == GENERATED_BLOCK_ANCHOR
    )
    generated = sphinx_app_for_format.env.get_doctree("index").findall(
        nodes.literal_block
    )
    assert [block.line for block in generated] == [expected_line]


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


def test_clickrunner_forces_color(monkeypatch):
    """``ClickRunner`` forces ``FORCE_COLOR`` so Rich-based CLIs colorize under ``NO_COLOR``.

    The runner already passes ``color=True`` (Click's color system). But rich-click
    renders help through Rich's ``Console``, gated on ``FORCE_COLOR``, which ``color=True``
    never reaches. The runner therefore also forces ``FORCE_COLOR`` (clearing the
    disabling vars) around the executed command, then restores the environment.
    """
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    seen = {}

    @click.command()
    def probe():
        seen["FORCE_COLOR"] = os.environ.get("FORCE_COLOR")
        seen["NO_COLOR"] = os.environ.get("NO_COLOR")

    ClickRunner().invoke(probe, [])

    # Color was forced through Rich's system while the command ran...
    assert seen["FORCE_COLOR"] == "1"
    assert seen["NO_COLOR"] is None
    # ...and the build environment is restored afterwards.
    assert os.environ.get("FORCE_COLOR") is None
    assert os.environ["NO_COLOR"] == "1"


@pytest.mark.parametrize(
    ("capture", "renders"),
    (
        # No argument: defaults to "fd" on Unix (renders) and "sys" on Windows (no render).
        pytest.param(None, sys.platform != "win32"),
        # Explicit "fd": not supported on Windows (fd-backed streams require Unix fds).
        pytest.param(
            "fd",
            True,
            marks=pytest.mark.skipif(
                sys.platform == "win32",
                reason='capture="fd" is not supported on Windows.',
            ),
        ),
        ("sys", False),
    ),
)
def test_clickrunner_capture_mode_controls_fileno(capture, renders):
    """``ClickRunner(capture=...)`` decides whether a fileno-writing CLI renders.

    Click's ``"sys"`` mode backs the captured stream with an in-memory buffer whose
    ``fileno()`` raises :exc:`io.UnsupportedOperation`, so a documented command that
    re-opens its descriptor (a common UTF-8-on-Windows guard) aborts. ``"fd"`` (the
    default on Unix, also exposed as the ``click_extra_run_capture`` conf.py value)
    backs it with a real descriptor, so the command renders. On Windows, where fd-backed
    streams are not supported, the default falls back to ``"sys"``.
    """

    @click.command()
    def probe():
        # A real CLI might re-open this descriptor to force an encoding before writing.
        sys.stdout.fileno()
        click.echo("papaya")

    result = ClickRunner(capture=capture).invoke(probe, [])

    if renders:
        assert result.exit_code == 0
        assert "papaya" in result.output
    else:
        assert result.exit_code != 0
        assert "papaya" not in result.output


@pytest.mark.parametrize(
    ("command_line", "expected"),
    (
        # A single word is the program, interpreter or not.
        ("my-cli", "my-cli"),
        ("python", "python"),
        # Every word of a multi-word program belongs to it.
        ("click-extra wrap", "click-extra wrap"),
        ("git remote add", "git remote add"),
        # An interpreter prefix names no program.
        ("python -m my_cli", "my_cli"),
        ("python3 -m my_cli", "my_cli"),
        ("python3.14 -m my_cli", "my_cli"),
        ("/usr/bin/python3 -m my_cli", "my_cli"),
        ("pypy3 -m my_cli", "my_cli"),
    ),
)
def test_program_from_command_line(command_line, expected):
    """Only an interpreter prefix is dropped from a displayed command line."""
    assert program_from_command_line(command_line) == expected


def test_clickrunner_keeps_a_multi_word_prog_name(monkeypatch):
    """A subcommand-shaped program name reaches the command it runs, whole."""
    monkeypatch.setenv("FORCE_COLOR", "0")

    @click.group()
    def parent():
        pass

    @parent.command()
    def child():
        """Do something."""
        click.echo(click.get_current_context().command_path)

    lines: list[str] = []
    ClickRunner().invoke(
        child,
        args=[],
        prog_name="parent child",
        _output_lines=lines,
    )
    assert lines[0] == "$ parent child"
    assert lines[1] == "parent child"


def test_clickrunner_prompt_inlines_environment_assignments(monkeypatch):
    """Variables are set on the invocation, the way the runner applies them.

    `CliRunner` scopes `env` to the one call, so an `export` line would advertise
    a persistence the next block does not inherit.
    """
    monkeypatch.setenv("FORCE_COLOR", "0")

    @click.command()
    def forecast():
        click.echo("18 degrees.")

    lines: list[str] = []
    ClickRunner().invoke(
        forecast,
        env={"WEATHER_UNITS": "celsius", "WEATHER_CITY": "Paris"},
        _output_lines=lines,
    )
    assert lines[0] == "$ WEATHER_CITY=Paris WEATHER_UNITS=celsius forecast"


def test_clickrunner_prompt_quotes_a_spaced_argument(monkeypatch):
    """An argument holding spaces stays the single token a reader must type."""
    monkeypatch.setenv("FORCE_COLOR", "0")

    @click.command()
    @click.option("--city")
    def forecast(city):
        click.echo(city)

    lines: list[str] = []
    ClickRunner().invoke(
        forecast,
        args=["--city", "Rio de Janeiro"],
        _output_lines=lines,
    )
    assert lines[0] == "$ forecast --city 'Rio de Janeiro'"


def test_clickrunner_hide_prompt_drops_the_invocation(monkeypatch):
    """`_show_prompt=False` leaves the output alone and drops the line above it."""
    monkeypatch.setenv("FORCE_COLOR", "0")

    @click.command()
    def forecast():
        click.echo("18 degrees.")

    lines: list[str] = []
    ClickRunner().invoke(
        forecast,
        env={"WEATHER_UNITS": "celsius"},
        _output_lines=lines,
        _show_prompt=False,
    )
    assert lines == ["18 degrees."]


@pytest.mark.parametrize(
    ("options", "prompted"),
    (
        pytest.param("", True, id="default"),
        pytest.param(":show-prompt:\n", True, id="show-prompt"),
        pytest.param(":hide-prompt:\n", False, id="hide-prompt"),
        # Last occurrence wins, mirroring the source and results flags.
        pytest.param(":hide-prompt:\n:show-prompt:\n", True, id="hide-then-show"),
    ),
)
def test_click_run_prompt_options(sphinx_app_myst, options, prompted):
    """`:show-prompt:` / `:hide-prompt:` gate the invocation line."""
    html = sphinx_app_myst.build_document(
        dedent("""
            ```{{click:source}}
            from click_extra import command, echo

            @command
            def greet():
                echo("Hello, papaya!")
            ```

            ```{{click:run}}
            {options}result = invoke(greet)
            ```
        """).format(options=options)
    )
    assert html
    # The output is rendered either way; only the prompt above it moves.
    assert "Hello, papaya!" in html
    assert ('<span class="gp">$ </span>greet' in html) is prompted


def test_click_run_hide_prompt_reaches_the_screenshot(sphinx_app_myst):
    """A capture is drawn from the same lines, so it loses the prompt too."""
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            from click_extra import command, echo

            @command
            def greet():
                echo("Hello, papaya!")
            ```

            ```{click:run}
            :hide-prompt:
            :screenshot: bare-greet-screen
            :screenshot-preset: windows
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "bare-greet-screen.svg"
    svg = asset.read_text(encoding="utf-8")
    assert "Hello," in svg
    # Neither this platform's sigil nor the one the preset would have swapped in.
    assert "$&#160;greet" not in svg
    assert "PS&#160;C:\\&gt;" not in svg


def test_click_run_screenshot_writes_the_asset(sphinx_app_myst):
    """``:screenshot:`` writes the capture beside the documentation.

    The image is a side effect: the page keeps its results code block, which
    inside Sphinx beats an image by staying selectable and searchable.
    """
    html_output = sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            from click_extra import command, echo

            @command
            def greet():
                echo("Hello, papaya!")
            ```

            ```{click:run}
            :screenshot: greet-screen
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "greet-screen.svg"
    assert asset.exists(), "the capture was not written"
    svg = asset.read_text(encoding="utf-8")
    # `unique_id` is pinned to the asset name, so a regenerated capture diffs
    # line by line instead of renaming every CSS class.
    assert "greet-screen-r1" in svg
    assert "papaya" in svg
    # The results block is still rendered, rather than swapped for the image.
    assert "papaya" in html_output


ANIMATED_SOURCE = """
    ```{click:source}
    :hide-source:
    from click_extra import SPINNERS, Spinner, Style, command, echo

    @command
    def greet():
        echo("Hello, papaya!")

    steeping = Spinner("Steeping", spinner=SPINNERS["moon"], style=Style(fg="green"))
    ```
"""
"""A spinner and a CLI, seeded for the animated-capture blocks below."""


def test_click_run_screenshot_animate_stacks_a_spinner(sphinx_app_myst):
    """``:screenshot-animate:`` draws every frame of the spinner it names.

    The frames and the interval are taken off the spinner itself, so the picture
    and the animation cannot disagree about either.
    """
    sphinx_app_myst.build_document(
        dedent(ANIMATED_SOURCE)
        + dedent("""
            ```{click:run}
            :screenshot: steeping-screen
            :screenshot-animate: steeping
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "steeping-screen.svg"
    svg = asset.read_text(encoding="utf-8")
    frame_count = len(SPINNERS["moon"].frames)
    assert len(re.findall(r'class="steeping-screen-f\d+"', svg)) == frame_count
    assert svg.count("@keyframes ") == frame_count
    assert "prefers-reduced-motion" in svg
    # The block's own results are not what the picture shows.
    assert "papaya" not in svg
    # Chrome is drawn once, whatever the frame count.
    assert svg.count("<clipPath") == 1


def test_click_run_screenshot_animate_defines_every_class_it_uses(sphinx_app_myst):
    """No frame names a class the animated capture leaves undefined.

    A frame whose rules are missing does not vanish: it falls back to the
    presentation attributes and draws in the wrong face and the wrong color,
    which reads as the animation resetting its styling once a cycle.
    """
    sphinx_app_myst.build_document(
        dedent(ANIMATED_SOURCE)
        + dedent("""
            ```{click:run}
            :screenshot: styled-steeping-screen
            :screenshot-animate: steeping
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "styled-steeping-screen.svg"
    svg = asset.read_text(encoding="utf-8")
    block = re.search(r"<style>(.*?)</style>", svg, re.DOTALL)
    assert block
    stylesheet = block.group(1)
    used = set(re.findall(r'class="([\w-]+)"', svg))
    defined = set(re.findall(r"\.([\w-]+)\s*\{", stylesheet))
    assert not used - defined, f"undefined: {sorted(used - defined)}"


def test_click_run_screenshot_animate_accepts_bare_frames(sphinx_app_myst):
    """A sequence of texts animates too, timed by ``:screenshot-interval:``."""
    sphinx_app_myst.build_document(
        dedent(ANIMATED_SOURCE)
        + dedent("""
            ```{click:run}
            :screenshot: pears-screen
            :screenshot-animate: ["one pear", "two pears", "three pears"]
            :screenshot-interval: 0.25
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "pears-screen.svg"
    svg = asset.read_text(encoding="utf-8")
    assert len(re.findall(r'class="pears-screen-f\d+"', svg)) == 3
    # Three frames of a quarter second each cycle in three quarters of one.
    assert "0.75s" in svg


def test_click_run_screenshot_animate_bare_frames_need_an_interval(sphinx_app_myst):
    """Bare frames carry no timing of their own, so one has to be stated."""
    content = dedent(ANIMATED_SOURCE) + dedent("""
        ```{click:run}
        :screenshot: untimed-screen
        :screenshot-animate: ["one pear", "two pears"]
        result = invoke(greet)
        ```
    """)

    with pytest.raises(ValueError, match="screenshot-interval"):
        sphinx_app_myst.build_document(content)


def test_click_run_screenshot_animate_rejects_a_foreign_subject(sphinx_app_myst):
    """Something that is neither a spinner nor frames fails the build."""
    content = dedent(ANIMATED_SOURCE) + dedent("""
        ```{click:run}
        :screenshot: foreign-screen
        :screenshot-animate: 42
        result = invoke(greet)
        ```
    """)

    with pytest.raises(TypeError, match="neither a Spinner nor a sequence"):
        sphinx_app_myst.build_document(content)


def test_click_run_screenshot_animate_is_deterministic(sphinx_app_myst):
    """A declared subject composes the same lines on every build.

    This is what lets an animated capture be committed at all: a recording would
    time its frames a little differently on every run and dirty the tree.
    """
    content = dedent(ANIMATED_SOURCE) + dedent("""
        ```{click:run}
        :screenshot: stable-screen
        :screenshot-animate: steeping
        result = invoke(greet)
        ```
    """)

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "stable-screen.svg"
    sphinx_app_myst.build_document(content)
    first = asset.read_text(encoding="utf-8")
    sphinx_app_myst.build_document(content)
    assert asset.read_text(encoding="utf-8") == first


def test_click_run_screenshot_animate_rewrites_a_declared_asset(sphinx_app_myst):
    """A declared animation is regenerated on every build, like any capture.

    It composes the same lines every time, so rewriting costs nothing and is
    what keeps the asset from drifting away from the code. Gating the write on
    what the animation *is* would freeze out every change to how it is *drawn*.
    """
    content = dedent(ANIMATED_SOURCE) + dedent("""
        ```{click:run}
        :screenshot: declared-screen
        :screenshot-animate: steeping
        result = invoke(greet)
        ```
    """)
    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "declared-screen.svg"

    sphinx_app_myst.build_document(content)
    first = asset.read_text(encoding="utf-8")
    asset.write_text(first + "<!-- stale -->", encoding="utf-8")

    sphinx_app_myst.build_document(content)
    assert asset.read_text(encoding="utf-8") == first, "the asset was not rewritten"


def test_click_run_screenshot_animate_carries_a_presentation_change(sphinx_app_myst):
    """Restating how an animation is drawn reaches the committed asset.

    The frames are untouched by a margin, so nothing about what the animation
    *is* moves. The picture still has to change.
    """
    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "restyled-screen.svg"

    def build(margin):
        sphinx_app_myst.build_document(
            dedent(ANIMATED_SOURCE)
            + dedent(f"""
                ```{{click:run}}
                :screenshot: restyled-screen
                :screenshot-animate: steeping
                :screenshot-margin: {margin}
                result = invoke(greet)
                ```
            """)
        )
        return asset.read_text(encoding="utf-8")

    assert build(8) != build(48)


RECORDED_SOURCE = """
    ```{click:source}
    :hide-source:
    from click_extra.recording import Frame

    kettle = [Frame("filling", 0.2), Frame("boiled", 0.2)]
    ```
"""
"""A stand-in recording: frames carrying their own durations, as one does."""


def test_click_run_screenshot_record_writes_once(sphinx_app_myst):
    """A recorded animation is written the first time and then left alone.

    Which spinner glyph pairs with which screen is settled by the scheduler, so
    a recording cannot be reproduced and rewriting it would dirty the working
    tree for nothing anyone did.
    """
    content = dedent(RECORDED_SOURCE) + dedent("""
        ```{click:run}
        :screenshot: kettle-screen
        :screenshot-record: kettle
        :hide-results:
        assert kettle
        ```
    """)
    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "kettle-screen.svg"

    sphinx_app_myst.build_document(content)
    marked = asset.read_text(encoding="utf-8").replace(
        "</svg>", "<!-- as it was recorded --></svg>"
    )
    asset.write_text(marked, encoding="utf-8")

    sphinx_app_myst.build_document(content)
    assert asset.read_text(encoding="utf-8") == marked


def test_click_run_screenshot_record_holds_its_last_frame(sphinx_app_myst):
    """A recording pauses on its final screen before starting over.

    An animation that ends somewhere is worth reading, and a loop restarting the
    instant it arrives never lets anyone.
    """
    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "held-screen.svg"
    sphinx_app_myst.build_document(
        dedent(RECORDED_SOURCE)
        + dedent("""
            ```{click:run}
            :screenshot: held-screen
            :screenshot-record: kettle
            :hide-results:
            assert kettle
            ```
        """)
    )

    # Two frames of 0.2s, the last held two seconds, then a 0.6s blank beat.
    svg = asset.read_text(encoding="utf-8")
    assert "period=3s" in svg
    assert "3s step-end" in svg


def test_click_run_screenshot_hold_overrides_the_pause(sphinx_app_myst):
    """`:screenshot-hold:` states the pause a page would rather have."""
    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "brief-screen.svg"
    sphinx_app_myst.build_document(
        dedent(RECORDED_SOURCE)
        + dedent("""
            ```{click:run}
            :screenshot: brief-screen
            :screenshot-record: kettle
            :screenshot-hold: 0
            :hide-results:
            assert kettle
            ```
        """)
    )

    # The recorded frames alone, plus the blank beat closing the cycle.
    assert "period=1s" in asset.read_text(encoding="utf-8")


def test_click_run_screenshot_blank_closes_the_cycle(sphinx_app_myst):
    """A recording ends on an empty beat, so the loop's turnover is visible.

    Without it, a loop jumping from its last frame back to its first reads as
    one long animation doing something odd rather than as a repetition.
    """
    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "blanked-screen.svg"
    sphinx_app_myst.build_document(
        dedent(RECORDED_SOURCE)
        + dedent("""
            ```{click:run}
            :screenshot: blanked-screen
            :screenshot-record: kettle
            :hide-results:
            assert kettle
            ```
        """)
    )

    svg = asset.read_text(encoding="utf-8")
    frames = re.findall(r'<g class="blanked-screen-f(\d+)"([^>]*)>(.*?)</g>', svg)
    empty = [index for index, _, body in frames if not body.strip()]
    assert empty, "the cycle closes on nothing"
    # A frame drawing nothing is never what a still falls back to.
    posters = [index for index, attrs, _ in frames if "hidden" not in attrs]
    assert posters and posters[0] not in empty


def test_click_run_screenshot_speed_scales_the_recorded_frames(sphinx_app_myst):
    """`:screenshot-speed:` replays faster, leaving the pauses as stated.

    The pauses are how long a reader is given, not part of what is replayed, so
    they are stated in real seconds and speed does not touch them.
    """
    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "quick-screen.svg"
    sphinx_app_myst.build_document(
        dedent(RECORDED_SOURCE)
        + dedent("""
            ```{click:run}
            :screenshot: quick-screen
            :screenshot-record: kettle
            :screenshot-speed: 2
            :hide-results:
            assert kettle
            ```
        """)
    )

    # Two 0.2s frames replayed at double speed, then the 2s hold and 0.6s blank.
    assert "period=2.8s" in asset.read_text(encoding="utf-8")


def test_click_run_screenshot_emphasize_lines_bands_a_still(sphinx_app_myst):
    """`:screenshot-emphasize-lines:` draws a band behind the lines it names."""
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            from click_extra import command, echo

            @command
            def stock():
                for fruit in ("apples", "bread", "cheese", "damsons"):
                    echo(f"{fruit} shelved")
            ```

            ```{click:run}
            :screenshot: banded-screen
            :screenshot-emphasize-lines: 2,4-5
            result = invoke(stock)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "banded-screen.svg"
    svg = asset.read_text(encoding="utf-8")
    group = re.search(r'<g clip-path="url\(#[\w-]+-window\)">(.*?)</g>', svg)
    assert group, "the bands are clipped to the window"
    bands = re.findall(r'<rect fill="(#[0-9a-f]+)"[^>]*\by="([\d.]+)"', group.group(1))
    assert len(bands) == 3, "one band per emphasized line"
    # All three share the one blended shade, and none sits on the first line.
    assert len({fill for fill, _ in bands}) == 1
    assert "0" not in {offset for _, offset in bands}


def test_click_run_screenshot_emphasize_lines_bands_an_animation(sphinx_app_myst):
    """A band marks a row of the screen, so an animation keeps it throughout.

    Drawn once behind every frame rather than per frame: the emphasis is on the
    row, not on whatever a given frame happened to put there.
    """
    sphinx_app_myst.build_document(
        dedent(RECORDED_SOURCE)
        + dedent("""
            ```{click:run}
            :screenshot: banded-animation-screen
            :screenshot-record: kettle
            :screenshot-emphasize-lines: 1
            :hide-results:
            assert kettle
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "banded-animation-screen.svg"
    svg = asset.read_text(encoding="utf-8")
    banded = {
        int(index)
        for index, drawn in re.findall(
            r'<g class="banded-animation-screen-f(\d+)"[^>]*'
            r'clip-path="url\(#[\w-]+-window\)">(.*?)</g>',
            svg,
            re.DOTALL,
        )
        if "<rect" in drawn
    }
    # Both recorded frames draw the first row; the blank closing the cycle does
    # not, so it carries no band either.
    assert banded == {0, 1}


def test_click_run_screenshot_emphasize_lines_rejects_a_line_that_is_not_there(
    sphinx_app_myst,
):
    """Naming a line the capture never drew fails the build rather than passing."""
    content = dedent("""
        ```{click:source}
        from click_extra import command, echo

        @command
        def stock():
            echo("apples shelved")
        ```

        ```{click:run}
        :screenshot: overreach-screen
        :screenshot-emphasize-lines: 40
        result = invoke(stock)
        ```
    """)

    with pytest.raises(ValueError, match="emphasize line 40"):
        sphinx_app_myst.build_document(content)


def test_click_run_screenshot_background(sphinx_app_myst):
    """``:screenshot-background:`` draws the capture on the chrome it names."""
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            from click_extra import command, echo

            @command
            def greet():
                echo("Hello, papaya!")
            ```

            ```{click:run}
            :screenshot: pale-greet-screen
            :screenshot-background: light
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "pale-greet-screen.svg"
    svg = asset.read_text(encoding="utf-8")
    assert LIGHT_CAPTURE_BACKGROUND in svg
    assert CAPTURE_BACKGROUND not in svg


def test_click_run_screenshot_columns_auto(sphinx_app_myst):
    """``:screenshot-columns: auto`` widens the image to what the block printed.

    Click wraps a CLI's own text at its fixed width whatever the option says.
    What it decides is the picture, and a line the CLI never wrapped (the prompt
    of a long invocation) is the one that needs the room.
    """
    source = dedent("""
        ```{{click:source}}
        from click_extra import command, echo

        @command
        def chant():
            echo("papaya " * 20)
        ```

        ```{{click:run}}
        :screenshot: {name}
        {options}
        result = invoke(chant)
        ```
    """)
    assets = Path(sphinx_app_myst.app.srcdir) / "assets"

    sphinx_app_myst.build_document(
        source.format(name="pinned-chant-screen", options="")
    )
    sphinx_app_myst.build_document(
        source.format(name="wide-chant-screen", options=":screenshot-columns: auto")
    )

    widths = {}
    for name in ("pinned-chant-screen", "wide-chant-screen"):
        svg = (assets / f"{name}.svg").read_text(encoding="utf-8")
        match = re.search(r'viewBox="0 0 (?P<width>[\d.]+)', svg)
        assert match
        widths[name] = float(match["width"])
    assert widths["wide-chant-screen"] > widths["pinned-chant-screen"]


@pytest.mark.parametrize("value", ("beige", "0", "-3", "12"))
def test_click_run_screenshot_columns_rejects_an_unusable_width(value):
    """A width narrower than the floor, or no width at all, is a build error."""
    with pytest.raises(ValueError):
        _screenshot_columns(value)


def test_click_run_screenshot_frame_options(sphinx_app_myst):
    """The `:screenshot-*:` options restate the window, the title included.

    The hex color is quoted because a directive's options are read as YAML,
    where an unquoted `#` opens a comment and leaves the option empty.
    """
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            from click_extra import command, echo

            @command
            def greet():
                echo("Hello, papaya!")
            ```

            ```{click:run}
            :screenshot: framed-greet-screen
            :screenshot-title: greeter
            :screenshot-backdrop: "#1f6feb"
            :screenshot-border: red
            :screenshot-border-width: 3
            :screenshot-radius: 0
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "framed-greet-screen.svg"
    svg = asset.read_text(encoding="utf-8")
    assert 'stroke="red"' in svg
    assert 'stroke-width="3"' in svg
    assert 'rx="0"' in svg
    assert 'fill="#1f6feb"' in svg
    assert "greeter" in svg


def test_click_run_screenshot_preset_swaps_the_prompt(sphinx_app_myst):
    """A capture drawn as another terminal prompts the way that one does.

    A block runs under a documentation build, so its own prompt is this
    platform's `$`. The picture is of a Windows terminal, whose shell prompts
    with something else entirely.
    """
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            from click_extra import command, echo

            @command
            def greet():
                echo("Hello, papaya!")
            ```

            ```{click:run}
            :screenshot: windows-greet-screen
            :screenshot-preset: windows
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "windows-greet-screen.svg"
    svg = asset.read_text(encoding="utf-8")
    assert "PS&#160;C:\\&gt;&#160;greet" in svg
    assert "Cascadia Code" in svg
    # Campbell's background, and the square corners Windows draws.
    assert 'fill="#0c0c0c"' in svg
    assert 'rx="0"' in svg


def test_click_run_screenshot_preset_defaults_to_the_project_wide_one(sphinx_app_myst):
    """A project drawing every capture as the same terminal states it once."""
    sphinx_app_myst.app.config.click_extra_screenshot_preset = "linux"
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            from click_extra import command, echo

            @command
            def greet():
                echo("Hello, papaya!")
            ```

            ```{click:run}
            :screenshot: gnome-greet-screen
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "gnome-greet-screen.svg"
    svg = asset.read_text(encoding="utf-8")
    assert "Ubuntu Mono" in svg
    # Tango's dark background, and the strip GNOME paints over it.
    assert 'fill="#2e3436"' in svg
    assert 'fill="#303030"' in svg


def test_click_run_screenshot_carries_no_watermark_by_default(sphinx_app_myst):
    """A capture a build rewrites carries no release number to go stale.

    The `screenshot` command credits click-extra on every image it writes. A
    block's image is regenerated and committed on every build, so the same mark
    would rewrite every asset the day the release it names changes.
    """
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            from click_extra import command, echo

            @command
            def greet():
                echo("Hello, papaya!")
            ```

            ```{click:run}
            :screenshot: unmarked-greet-screen
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "unmarked-greet-screen.svg"
    assert "watermark" not in asset.read_text(encoding="utf-8")


def test_click_run_screenshot_watermark(sphinx_app_myst):
    """A project wanting its captures credited states the line once."""
    sphinx_app_myst.app.config.click_extra_screenshot_watermark = "pantry 1.4.2"
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            from click_extra import command, echo

            @command
            def greet():
                echo("Hello, papaya!")
            ```

            ```{click:run}
            :screenshot: credited-greet-screen
            result = invoke(greet)
            ```

            ```{click:run}
            :screenshot: recredited-greet-screen
            :screenshot-watermark: shot on a Tuesday
            result = invoke(greet)
            ```
        """)
    )

    assets = Path(sphinx_app_myst.app.srcdir) / "assets"
    project_wide = (assets / "credited-greet-screen.svg").read_text(encoding="utf-8")
    assert '<text class="watermark"' in project_wide
    assert "pantry 1.4.2" in project_wide
    # A block naming its own mark keeps it.
    per_block = (assets / "recredited-greet-screen.svg").read_text(encoding="utf-8")
    assert "shot on a Tuesday" in per_block
    assert "pantry 1.4.2" not in per_block


def test_click_run_screenshot_opacity(sphinx_app_myst):
    """A see-through window lets the page it is laid on show through its body."""
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            from click_extra import command, echo

            @command
            def greet():
                echo("Hello, papaya!")
            ```

            ```{click:run}
            :screenshot: glassy-greet-screen
            :screenshot-opacity: 0.4
            result = invoke(greet)
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "glassy-greet-screen.svg"
    assert 'fill-opacity="0.4"' in asset.read_text(encoding="utf-8")


@pytest.mark.parametrize("argument", ("-0.1", "1.5", "opaque"))
def test_click_run_screenshot_opacity_rejects_what_is_not_one(argument):
    """Anything outside the zero-to-one range fails the build instead of clamping."""
    with pytest.raises(ValueError):
        _screenshot_opacity(argument)


def test_click_run_screenshot_background_rejects_an_unknown_chrome():
    """A typo names the chromes it could have been, instead of drawing a default."""
    with pytest.raises(ValueError, match=r'"dark".+"light"'):
        _screenshot_background("beige")


def test_click_run_mirror_region_round_trips():
    """``:mirror:`` inserts an image link below the fence, then leaves it alone."""
    source = dedent("""
        # Title

        ```{click:run}
        :screenshot: greet-screen
        :mirror:
        result = invoke(greet)
        ```

        Trailing prose.
    """)

    once = _rewrite_screenshot_regions(source)
    assert SCREENSHOT_MARKER_START in once
    assert "![greet-screen](assets/greet-screen.svg)" in once
    assert SCREENSHOT_MARKER_END in once
    assert "Trailing prose." in once
    # Idempotent: a second pass over an already-refreshed region is a no-op.
    assert _rewrite_screenshot_regions(once) == once


def test_click_run_mirror_needs_both_options():
    """A block missing either option gets no region.

    ``:screenshot:`` alone maintains an asset some other surface embeds, without
    putting it on this page; ``:mirror:`` alone has no capture to point at.
    """
    for options in (":screenshot: lone-screen", ":mirror:"):
        source = dedent(f"""
            ```{{click:run}}
            {options}
            result = invoke(greet)
            ```
        """)
        assert _rewrite_screenshot_regions(source) == source


def test_click_run_mirror_skips_a_nested_example():
    """A ``click:run`` shown inside a longer fence is documentation, not a block."""
    source = dedent("""
        ````markdown
        ```{click:run}
        :screenshot: nested-screen
        :mirror:
        result = invoke(greet)
        ```
        ````
    """)
    assert _rewrite_screenshot_regions(source) == source


def test_click_source_screenshot_pictures_its_own_code(sphinx_app_myst):
    """A source block's ``:screenshot:`` draws the code it declares.

    A directive that runs something has output worth committing; one that only
    declares code has none, so its subject is the code itself.
    """
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            :screenshot: ripen-source
            from click_extra import command, echo

            @command
            def ripen():
                echo("The papaya is ready.")
            ```
        """)
    )

    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "ripen-source.svg"
    assert asset.exists(), "the source capture was not written"
    svg = asset.read_text(encoding="utf-8")
    assert "ripen-source-r1" in svg
    assert "papaya" in svg
    # Painted the background its syntax style was designed against, rather than
    # the terminal chrome a captured command is drawn on.
    assert (
        get_style_by_name(
            DEFAULT_SYNTAX_STYLES[CaptureBackground.DARK]
        ).background_color
        in svg
    )


def test_click_source_screenshot_takes_a_syntax_style(sphinx_app_myst):
    """``:screenshot-syntax-style:`` repaints the window along with the code."""
    sphinx_app_myst.build_document(
        dedent("""
            ```{click:source}
            :screenshot: dracula-source
            :screenshot-syntax-style: dracula
            from click_extra import command

            @command
            def ripen():
                pass
            ```
        """)
    )

    svg = (
        Path(sphinx_app_myst.app.srcdir) / "assets" / "dracula-source.svg"
    ).read_text(
        encoding="utf-8",
    )
    assert get_style_by_name("dracula").background_color in svg


def test_click_source_screenshot_bands_its_emphasized_lines(sphinx_app_myst):
    """``:emphasize-lines:`` marks the same lines on the page and in the image.

    A source block has one content, so saying it twice would be the surprise.
    """
    body = dedent("""
        from click_extra import command

        @command
        def ripen():
            pass
        ```
    """)
    assets = Path(sphinx_app_myst.app.srcdir) / "assets"

    sphinx_app_myst.build_document(
        "```{click:source}\n:screenshot: plain-source\n" + body,
    )
    sphinx_app_myst.build_document(
        "```{click:source}\n:screenshot: banded-source\n:emphasize-lines: 2\n" + body,
    )

    plain = (assets / "plain-source.svg").read_text(encoding="utf-8")
    banded = (assets / "banded-source.svg").read_text(encoding="utf-8")
    # The band is drawn in a clipped group of its own, which the unmarked
    # capture of the same code does not carry at all.
    assert '<g clip-path="url(#plain-source-window)">' not in plain
    assert '<g clip-path="url(#banded-source-window)">' in banded


def test_click_source_screenshot_is_deterministic(sphinx_app_myst):
    """Two builds of one source block write the same bytes.

    Nothing here runs a command or reads a clock, so a committed asset stays
    put and leaves the working tree clean.
    """
    document = dedent("""
        ```{click:source}
        :screenshot: stable-source
        from click_extra import command

        @command
        def ripen():
            pass
        ```
    """)
    asset = Path(sphinx_app_myst.app.srcdir) / "assets" / "stable-source.svg"
    sphinx_app_myst.build_document(document)
    first = asset.read_text(encoding="utf-8")
    sphinx_app_myst.build_document(document)
    assert asset.read_text(encoding="utf-8") == first


def test_click_source_mirror_shows_the_snippet():
    """A source block mirrors its capture the way a run block does.

    Same marker pair, same derivation from the ``:screenshot:`` name: what
    changed is only which directives are allowed to ask.
    """
    source = dedent("""
        ```{click:source}
        :screenshot: ripen-source
        :mirror:
        from click_extra import command
        ```
    """)
    once = _rewrite_screenshot_regions(source)
    assert "![ripen-source](assets/ripen-source.svg)" in once
    assert SCREENSHOT_MARKER_END in once
    assert _rewrite_screenshot_regions(once) == once


def test_python_render_mirror_is_left_to_its_own_refresher():
    """``python:render`` keeps the one ``:mirror:`` that means something else.

    It mirrors the markup the block generated, and a second refresher writing
    that region would undo the first on every alternate run.
    """
    source = dedent("""
        ```{python:render}
        :screenshot: rendered-screen
        :mirror:
        print("The papaya is ready.")
        ```
    """)
    assert _rewrite_screenshot_regions(source) == source
