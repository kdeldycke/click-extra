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

from .conftest import HTML, DirectiveTestCase, FormatType, admonition_block

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
