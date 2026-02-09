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
"""Tests for GitHub alert syntax conversion in Sphinx with MyST parser."""

from __future__ import annotations

from textwrap import dedent

import pytest
from sphinx.application import Sphinx
from sphinx.errors import ConfigError
from sphinx.util.docutils import docutils_namespace

from click_extra.sphinx.alerts import replace_github_alerts

from .conftest import HTML, DirectiveTestCase, FormatType, admonition_block


@pytest.mark.parametrize(
    "alert_type",
    ["NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION"],
)
def test_all_alert_types(alert_type):
    """Test all supported alert types are converted correctly."""
    text = dedent(f"""\
        > [!{alert_type}]
        > Content.""")
    expected = dedent(f"""\
        :::{{{alert_type.lower()}}}
        Content.
        :::""")
    assert replace_github_alerts(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            dedent("""\
                > [!NOTE]
                > This is a note.
                > With multiple lines.

                Regular text after."""),
            dedent("""\
                :::{note}
                This is a note.
                With multiple lines.
                :::

                Regular text after."""),
            id="note_alert",
        ),
        pytest.param(
            dedent("""\
                > [!RANDOM]
                > This is not a known alert type."""),
            None,
            id="unknown_type_unchanged",
        ),
        pytest.param(
            dedent("""\
                > Regular blockquote
                > without alert syntax."""),
            None,
            id="no_alerts_returns_none",
        ),
        pytest.param(
            dedent("""\
                > [!NOTE]
                > First paragraph.
                >
                > Second paragraph."""),
            dedent("""\
                :::{note}
                First paragraph.

                Second paragraph.
                :::"""),
            id="empty_line_in_alert",
        ),
        pytest.param(
            dedent("""\
                > [!NOTE]
                > A note.

                Some text between.

                > [!WARNING]
                > A warning."""),
            dedent("""\
                :::{note}
                A note.
                :::

                Some text between.

                :::{warning}
                A warning.
                :::"""),
            id="multiple_alerts",
        ),
        pytest.param(
            dedent("""\
                > [!NOTE]
                >  This line has an extra space after >.
                >   This line has two extra spaces.
                >    This line has three extra spaces."""),
            dedent("""\
                :::{note}
                This line has an extra space after >.
                This line has two extra spaces.
                This line has three extra spaces.
                :::"""),
            id="extra_spaces_after_chevron",
        ),
        pytest.param(
            dedent("""\
                >[!TIP]
                > This alert has no space after the chevron on the first line."""),
            dedent("""\
                :::{tip}
                This alert has no space after the chevron on the first line.
                :::"""),
            id="no_space_after_chevron_on_first_line",
        ),
        pytest.param(
            dedent("""\
                > [!TIP]
                >No space after the bracket."""),
            dedent("""\
                :::{tip}
                No space after the bracket.
                :::"""),
            id="no_space_after_bracket",
        ),
        pytest.param(
            dedent("""\
                > [!WARNING]
                > Normal spacing.
                >  Extra space.
                >No space.
                >   Lots of spaces."""),
            dedent("""\
                :::{warning}
                Normal spacing.
                Extra space.
                No space.
                Lots of spaces.
                :::"""),
            id="mixed_spacing",
        ),
        pytest.param(
            dedent("""\
                >    [!TIP]
                > This alert has extra spaces before the directive."""),
            dedent("""\
                :::{tip}
                This alert has extra spaces before the directive.
                :::"""),
            id="leading_spaces_before_directive",
        ),
        pytest.param(
            dedent("""\
                > [! TIP]
                > This should remain a regular blockquote."""),
            None,
            id="invalid_space_after_bang",
        ),
        pytest.param(
            dedent("""\
                > [ !TIP]
                > This should remain a regular blockquote."""),
            None,
            id="invalid_space_before_bang",
        ),
        pytest.param(
            dedent("""\
                > [!TIP ]
                > This should remain a regular blockquote."""),
            None,
            id="invalid_space_before_closing_bracket",
        ),
        pytest.param(
            dedent("""\
                > [!tip]
                > Lowercase should not match."""),
            None,
            id="lowercase_invalid",
        ),
        pytest.param(
            dedent("""\
                > [!TIP]
                > [!TIP]
                > Hello."""),
            dedent("""\
                :::{tip}
                [!TIP]
                Hello.
                :::"""),
            id="duplicate_directive",
        ),
        pytest.param(
            "> [!TIP]",
            dedent("""\
                :::{tip}
                :::"""),
            id="empty_alert",
        ),
        pytest.param(
            "> Hello [!NOTE] This is a note.",
            None,
            id="invalid_text_before_directive",
        ),
        pytest.param(
            dedent("""\
                # Regular Heading

                Regular paragraph text.

                > Regular blockquote without alert syntax.

                ```python
                print("code block")
                ```"""),
            None,
            id="content_without_alerts_unchanged",
        ),
        pytest.param(
            dedent("""\
                ```markdown
                > [!NOTE]
                > Inside code block.
                ```"""),
            None,
            id="code_block_preserved",
        ),
        pytest.param(
            dedent("""\
                ~~~markdown
                > [!NOTE]
                > This is inside a tilde code block.
                ~~~"""),
            None,
            id="code_block_tilde_preserved",
        ),
        pytest.param(
            dedent("""\
                ```
                > [!TIP]
                > This is inside a code block without language.
                ```"""),
            None,
            id="code_block_no_language_preserved",
        ),
        pytest.param(
            dedent("""\
                ````markdown
                > [!WARNING]
                > This is inside a 4-backtick code block.
                ```
                nested code fence
                ```
                ````"""),
            None,
            id="code_block_four_backticks_preserved",
        ),
        pytest.param(
            dedent("""\
                ```{code-block} markdown
                > [!NOTE]
                > This is inside a code-block directive.
                ```"""),
            None,
            id="code_block_directive_preserved",
        ),
        pytest.param(
            dedent("""\
                Some text before.

                    > [!TIP]
                    > This is inside a code block without language.

                Some text after."""),
            None,
            id="indented_code_block_4_spaces_preserved",
        ),
        pytest.param(
            dedent("""\
                Some text before.

                  > [!TIP]
                  > This is inside a 2-space indented block.

                Some text after."""),
            dedent("""\
                Some text before.

                  :::{tip}
                  This is inside a 2-space indented block.
                  :::

                Some text after."""),
            id="indented_2_spaces_converted",
        ),
        pytest.param(
            dedent("""\
                > [!NOTE]
                > Real alert.

                ```
                > [!NOTE]
                > In code block.
                ```

                > [!TIP]
                > Another alert."""),
            dedent("""\
                :::{note}
                Real alert.
                :::

                ```
                > [!NOTE]
                > In code block.
                ```

                :::{tip}
                Another alert.
                :::"""),
            id="mixed_alerts_and_code_blocks",
        ),
        pytest.param(
            dedent("""\
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
                > Final admonition."""),
            dedent("""\
                :::{note}
                This should be converted to an admonition.
                :::

                ```markdown
                > [!NOTE]
                > This should NOT be converted (inside code block).
                ```

                :::{warning}
                This should also be converted to an admonition.
                :::

                ~~~markdown
                > [!WARNING]
                > This should NOT be converted (inside tilde block).
                ~~~

                :::{tip}
                Final admonition.
                :::"""),
            id="mixed_code_blocks_comprehensive",
        ),
        pytest.param(
            dedent("""\
                > [!NOTE]
                > Outer note.
                >
                > :::{tip}
                > Nested tip using MyST syntax.
                > :::"""),
            dedent("""\
                :::{note}
                Outer note.

                :::{tip}
                Nested tip using MyST syntax.
                :::
                :::"""),
            id="github_alert_with_nested_myst_directive",
        ),
        pytest.param(
            dedent("""\
                :::{note}
                Outer MyST note.

                > [!WARNING]
                > Nested GitHub alert inside MyST directive.
                :::"""),
            dedent("""\
                :::{note}
                Outer MyST note.

                :::{warning}
                Nested GitHub alert inside MyST directive.
                :::
                :::"""),
            id="myst_directive_with_nested_github_alert",
        ),
        pytest.param(
            dedent("""\
                > [!NOTE]
                > Level 1.
                >
                > ::::{tip}
                > Level 2.
                >
                > :::{warning}
                > Level 3.
                > :::
                > ::::"""),
            dedent("""\
                :::{note}
                Level 1.

                ::::{tip}
                Level 2.

                :::{warning}
                Level 3.
                :::
                ::::
                :::"""),
            id="deeply_nested_directives",
        ),
        pytest.param(
            dedent("""\
                ::::{note}
                Outer note with 4 colons.

                > [!TIP]
                > GitHub alert inside.

                :::{warning}
                MyST warning inside.
                :::
                ::::"""),
            dedent("""\
                ::::{note}
                Outer note with 4 colons.

                :::{tip}
                GitHub alert inside.
                :::

                :::{warning}
                MyST warning inside.
                :::
                ::::"""),
            id="mixed_nesting_with_colon_counts",
        ),
        pytest.param(
            dedent("""\
                ````{note}
                The next info should be nested

                > [!WARNING]
                > Here's my GitHub alert warning.
                ````"""),
            dedent("""\
                ````{note}
                The next info should be nested

                :::{warning}
                Here's my GitHub alert warning.
                :::
                ````"""),
            id="backtick_fence_with_nested_github_alert",
        ),
        pytest.param(
            dedent("""\
                ````{note}
                The warning block will be properly-parsed

                   > [!WARNING]
                   > Here's my indented warning.

                But the next block will be parsed as raw text

                    > [!TIP]
                    > Here's my raw text tip that isn't parsed...
                ````"""),
            dedent("""\
                ````{note}
                The warning block will be properly-parsed

                   :::{warning}
                   Here's my indented warning.
                   :::

                But the next block will be parsed as raw text

                    > [!TIP]
                    > Here's my raw text tip that isn't parsed...
                ````"""),
            id="backtick_fence_indentation_matters",
        ),
        pytest.param(
            dedent("""\
                ``````{note}
                The next info should be nested
                `````{warning}
                Here's my warning

                > [!TIP]
                > GitHub alert inside deeply nested directives.

                ````{admonition} Custom Title
                ```python
                print('nested code')
                ```
                ````
                `````
                ``````"""),
            dedent("""\
                ``````{note}
                The next info should be nested
                `````{warning}
                Here's my warning

                :::{tip}
                GitHub alert inside deeply nested directives.
                :::

                ````{admonition} Custom Title
                ```python
                print('nested code')
                ```
                ````
                `````
                ``````"""),
            id="deeply_nested_backtick_fences_with_code",
        ),
        pytest.param(
            dedent("""\
                ````{note}
                > [!TIP]
                > First alert.

                ```{warning}
                Nested MyST warning.
                ```

                > [!CAUTION]
                > Second alert after nested directive.
                ````"""),
            # XXX We cannot just add :::{tip} after ````{note}, as it is misinterpreted
            # as an admonition's :parameter:. We should probably fix the parser to use
            # ```{tip} instead of :::{tip} in the future and keep track of the indention.
            # In the mean time, the trick is to introduce an empty line before :::{tip}.
            dedent("""\
                ````{note}

                :::{tip}
                First alert.
                :::

                ```{warning}
                Nested MyST warning.
                ```

                :::{caution}
                Second alert after nested directive.
                :::
                ````"""),
            id="multiple_alerts_around_nested_directive",
        ),
        pytest.param(
            dedent("""\
                `````{note}
                Outer note.

                ````{tip}
                > [!WARNING]
                > Alert inside tip.

                ```{important}
                Deeply nested important.
                ```
                ````
                `````"""),
            dedent("""\
                `````{note}
                Outer note.

                ````{tip}

                :::{warning}
                Alert inside tip.
                :::

                ```{important}
                Deeply nested important.
                ```
                ````
                `````"""),
            id="alert_between_nested_directives",
        ),
        pytest.param(
            dedent("""\
                ````{note}
                > [!TIP]
                > This should convert.

                ```markdown
                > [!TIP]
                > This should NOT convert (code block).
                ```

                > [!WARNING]
                > This should also convert.
                ````"""),
            dedent("""\
                ````{note}

                :::{tip}
                This should convert.
                :::

                ```markdown
                > [!TIP]
                > This should NOT convert (code block).
                ```

                :::{warning}
                This should also convert.
                :::
                ````"""),
            id="alerts_and_code_block_inside_directive",
        ),
        pytest.param(
            dedent("""\
                > [!NOTE]
                > This alert contains:
                > - A bullet list
                > - With multiple items
                >
                > And a code block:
                > ```python
                > print("Hello, world!")
                > ```"""),
            dedent("""\
                :::{note}
                This alert contains:
                - A bullet list
                - With multiple items

                And a code block:
                ```python
                print("Hello, world!")
                ```
                :::"""),
            id="alert_with_list_and_code_block",
        ),
        pytest.param(
            dedent("""\
                > [!WARNING]
                > Be careful with this operation.
                >
                > > [!TIP]
                > > If you encounter issues, try restarting the service."""),
            dedent("""\
                ::::{warning}
                Be careful with this operation.

                :::{tip}
                If you encounter issues, try restarting the service.
                :::
                ::::"""),
            id="nested_alert_within_alert",
        ),
        pytest.param(
            dedent("""\
                > [!IMPORTANT]
                > Before proceeding, ensure you have:
                >
                > 1. Backed up your data
                > 2. Reviewed the changelog
                >
                > > This is important context that applies to all the steps above.
                >
                > > [!CAUTION]
                > > This action cannot be undone.
                >
                > ```bash
                > $ make backup
                > ```"""),
            dedent("""\
                ::::{important}
                Before proceeding, ensure you have:

                1. Backed up your data
                2. Reviewed the changelog

                > This is important context that applies to all the steps above.

                :::{caution}
                This action cannot be undone.
                :::

                ```bash
                $ make backup
                ```
                ::::"""),
            id="complex_nested_with_list_blockquote_alert_and_code",
        ),
        pytest.param(
            dedent("""\
                ```{list-table}
                :header-rows: 1
                :widths: 10 30 30 30

                * - Type
                  - GitHub syntax
                  - MyST syntax
                  - Rendered
                * - Note
                  - ```markdown
                    > [!NOTE]
                    > Useful information.
                    ```
                  - ```markdown
                    :::{note}
                    Useful information.
                    :::
                    ```
                  - ```{note}
                    Useful information.
                    ```
                * - Tip
                  - ```markdown
                    > [!TIP]
                    > Helpful advice.
                    ```
                  - ```markdown
                    :::{tip}
                    Helpful advice.
                    :::
                    ```
                  - ```{tip}
                    Helpful advice.
                    ```
                ```"""),
            None,
            id="list_table_with_alert_examples_preserved",
        ),
    ],
)
def test_alert_conversion(text, expected):
    """Test GitHub alerts are converted to MyST admonitions.

    When expected is None, no conversion should occur.
    """
    assert replace_github_alerts(text) == expected


EMPTY_DIRECTIVE_TEST_CASE = DirectiveTestCase(
    name="empty_admonition_rendering",
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


CODE_BLOCK_TEST_CASE = DirectiveTestCase(
    name="pygments_highlighting_integration",
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

CODE_BLOCK_DIRECTIVE_TEST_CASE = DirectiveTestCase(
    name="myst_code_block_directive_interaction",
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

INDENTED_CODE_BLOCK_TEST_CASE = DirectiveTestCase(
    name="indented_code_block_rendering",
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

MIXED_CODE_BLOCKS_TEST_CASE = DirectiveTestCase(
    name="comprehensive_mixed_alerts_and_code_blocks",
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


NESTED_ADMONITION_TEST_CASE = DirectiveTestCase(
    name="nested_admonitions_rendering",
    format_type=FormatType.MYST,
    document="""
        ::::{note}
        This is the outer note.

        > [!TIP]
        > This is a nested GitHub alert.

        :::{warning}
        This is a nested MyST warning.
        :::
        ::::
    """,
    html_matches=admonition_block(
        "note",
        "<p>This is the outer note.</p>\n"
        + admonition_block("tip", "<p>This is a nested GitHub alert.</p>\n")
        + admonition_block("warning", "<p>This is a nested MyST warning.</p>\n"),
    ),
)


TRIPLE_NESTED_TEST_CASE = DirectiveTestCase(
    name="triple_nested_admonitions",
    format_type=FormatType.MYST,
    document="""
        :::::{note}
        Level 1.

        ::::{tip}
        Level 2.

        > [!WARNING]
        > Level 3 GitHub alert.

        ::::
        :::::
    """,
    html_matches=admonition_block(
        "note",
        "<p>Level 1.</p>\n"
        + admonition_block(
            "tip",
            "<p>Level 2.</p>\n"
            + admonition_block("warning", "<p>Level 3 GitHub alert.</p>\n"),
        ),
    ),
)


BACKTICK_FENCE_MIXED_DIRECTIVES_TEST_CASE = DirectiveTestCase(
    name="backtick_fence_with_alerts_and_myst_directive",
    format_type=FormatType.MYST,
    document="""
        ````{note}
        > [!TIP]
        > First alert.

        ```{warning}
        Nested MyST warning.
        ```

        > [!CAUTION]
        > Second alert after nested directive.
        ````
    """,
    html_matches=admonition_block(
        "note",
        admonition_block("tip", "<p>First alert.</p>\n")
        + admonition_block("warning", "<p>Nested MyST warning.</p>\n")
        + admonition_block("caution", "<p>Second alert after nested directive.</p>\n"),
    ),
)


COMPLEX_NESTED_CONTENT_TEST_CASE = DirectiveTestCase(
    name="complex_nested_with_list_blockquote_alert_and_code",
    format_type=FormatType.MYST,
    document="""
        > [!IMPORTANT]
        > Before proceeding, ensure you have:
        >
        > 1. Backed up your data
        > 2. Reviewed the changelog
        >
        > > This is important context that applies to all the steps above.
        >
        > > [!CAUTION]
        > > This action cannot be undone.
        >
        > ```bash
        > $ make backup
        > ```
    """,
    html_matches=admonition_block(
        "important",
        "<p>Before proceeding, ensure you have:</p>\n"
        '<ol class="arabic simple">\n'
        "<li><p>Backed up your data</p></li>\n"
        "<li><p>Reviewed the changelog</p></li>\n"
        "</ol>\n"
        "<blockquote>\n"
        "<div><p>This is important context that applies to all the steps above.</p>\n"
        "</div></blockquote>\n"
        + admonition_block("caution", "<p>This action cannot be undone.</p>\n")
        + '<div class="highlight-bash notranslate"><div class="highlight">'
        '<pre><span></span>$<span class="w"> </span>make<span class="w"> </span>backup\n'
        "</pre></div>\n"
        "</div>\n",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        EMPTY_DIRECTIVE_TEST_CASE,
        CODE_BLOCK_TEST_CASE,
        CODE_BLOCK_DIRECTIVE_TEST_CASE,
        INDENTED_CODE_BLOCK_TEST_CASE,
        MIXED_CODE_BLOCKS_TEST_CASE,
        NESTED_ADMONITION_TEST_CASE,
        TRIPLE_NESTED_TEST_CASE,
        BACKTICK_FENCE_MIXED_DIRECTIVES_TEST_CASE,
        COMPLEX_NESTED_CONTENT_TEST_CASE,
    ],
)
def test_sphinx_integration(sphinx_app, test_case):
    """Integration-critical tests that verify Sphinx rendering behavior."""
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


@pytest.mark.parametrize(
    ("included_files", "main_content", "expected_fragments", "unexpected_fragments"),
    [
        pytest.param(
            {
                "included.md": """\
                    > [!NOTE]
                    > This note is from an included file.

                    Some regular text.

                    > [!WARNING]
                    > This warning is also from the included file.
                """
            },
            """\
                # Main Document

                ```{include} included.md
                ```

                Text after include.
            """,
            [
                ("note", "<p>This note is from an included file.</p>\n"),
                ("warning", "<p>This warning is also from the included file.</p>\n"),
            ],
            [],
            id="basic_include",
        ),
        pytest.param(
            {
                "partial.md": """\
                    # Header to Skip

                    This content should be skipped.

                    <!-- start-content -->

                    > [!TIP]
                    > This tip appears after the marker.

                    Important information here.
                """
            },
            """\
                # Documentation

                ```{include} partial.md
                :start-after: <!-- start-content -->
                ```
            """,
            [("tip", "<p>This tip appears after the marker.</p>\n")],
            ["Header to Skip", "This content should be skipped"],
            id="start_after",
        ),
        pytest.param(
            {
                "partial_end.md": """\
                    > [!IMPORTANT]
                    > This important note should be included.

                    <!-- end-content -->

                    > [!CAUTION]
                    > This caution should NOT be included.
                """
            },
            """\
                # Documentation

                ```{include} partial_end.md
                :end-before: <!-- end-content -->
                ```
            """,
            [("important", "<p>This important note should be included.</p>\n")],
            ["admonition caution", "This caution should NOT be included"],
            id="end_before",
        ),
        pytest.param(
            {
                "docs/nested.md": """\
                    > [!NOTE]
                    > This note is from a nested directory.
                """
            },
            """\
                # Main Document

                ```{include} docs/nested.md
                ```
            """,
            [("note", "<p>This note is from a nested directory.</p>\n")],
            [],
            id="nested_directory",
        ),
        pytest.param(
            {
                "warning.md": """\
                    > [!WARNING]
                    > Warning from included file.
                """
            },
            """\
                > [!NOTE]
                > Direct note in main document.

                ```{include} warning.md
                ```

                > [!TIP]
                > Another direct tip.
            """,
            [
                ("note", "<p>Direct note in main document.</p>\n"),
                ("warning", "<p>Warning from included file.</p>\n"),
                ("tip", "<p>Another direct tip.</p>\n"),
            ],
            [],
            id="mixed_direct_and_included",
        ),
    ],
)
def test_github_alert_in_included_files(
    sphinx_app_myst_with_include,
    included_files,
    main_content,
    expected_fragments,
    unexpected_fragments,
):
    """Test GitHub alerts in included files with various configurations."""
    sphinx_app, srcdir = sphinx_app_myst_with_include

    for path, content in included_files.items():
        file_path = srcdir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(dedent(content))

    html_output = sphinx_app.build_document(dedent(main_content))

    for alert_type, content in expected_fragments:
        assert admonition_block(alert_type, content) in html_output

    for fragment in unexpected_fragments:
        assert fragment not in html_output
