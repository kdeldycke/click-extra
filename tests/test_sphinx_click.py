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

import re
from textwrap import dedent

import pytest

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
