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

from click_extra.screenshot import CAPTURE_BACKGROUND, LIGHT_CAPTURE_BACKGROUND
from click_extra.sphinx.click import (
    _CLIRUNNER_HAS_CAPTURE,
    SCREENSHOT_MARKER_END,
    SCREENSHOT_MARKER_START,
    ClickRunner,
    _rewrite_screenshot_regions,
    _screenshot_background,
    _screenshot_columns,
    _screenshot_opacity,
    program_from_command_line,
)

from .conftest import HTML, DirectiveTestCase, FormatType

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
    "test_case",
    [
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


@pytest.mark.skipif(
    not _CLIRUNNER_HAS_CAPTURE,
    reason="Click < 8.4 has no capture mode for ClickRunner to select.",
)
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
