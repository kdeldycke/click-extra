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
"""Tests for the MyST-to-reST docstring conversion hook."""

from __future__ import annotations

import pytest

from click_extra.sphinx.myst_docstrings import _TYPEHINTS_EXT, myst_to_rst, setup


def _convert(text: str) -> str:
    """Helper: run myst_to_rst on a string and return the result."""
    lines = text.split("\n")
    myst_to_rst(lines)
    return "\n".join(lines)


# ---- Cross-references: {role}`target` -> :role:`target` --------------------


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        ("{func}`foo`", ":func:`foo`"),
        ("{data}`~extra_platforms.MACOS`", ":data:`~extra_platforms.MACOS`"),
        ("{deco}`~pytest.skip_linux`", ":deco:`~pytest.skip_linux`"),
        (
            "{func}`is_a`, {func}`is_b` and {data}`C`",
            ":func:`is_a`, :func:`is_b` and :data:`C`",
        ),
        ("a {class}`frozenset` of items", "a :class:`frozenset` of items"),
        # Adjacent xrefs with no whitespace.
        ("{func}`a`{func}`b`", ":func:`a`:func:`b`"),
        # Hyphenated role name.
        ("{pull-request}`#42`", ":pull-request:`#42`"),
        # Empty target (Sphinx will warn later).
        ("{func}``", ":func:``"),
    ],
    ids=[
        "simple",
        "tilde",
        "custom-role",
        "multiple",
        "mid-sentence",
        "adjacent-no-space",
        "hyphenated-role",
        "empty-target",
    ],
)
def test_xref_conversion(myst, expected):
    assert _convert(myst) == expected


# ---- Colon-fenced directives: :::{directive} -> .. directive:: -------------


@pytest.mark.parametrize(
    ("myst", "expected_fragments"),
    [
        (
            ":::{note}\nSome content.\n:::",
            [".. note::", "    Some content."],
        ),
        (
            ":::{hint}\nLine one.\nLine two.\n:::",
            [".. hint::", "    Line one.", "    Line two."],
        ),
        (
            ":::{warning} Be careful\nDon't do this.\n:::",
            [".. warning:: Be careful", "    Don't do this."],
        ),
        (
            ":::{note}\nOuter.\n\n    - Item one.\n    - Item two.\n:::",
            [".. note::", "        - Item one."],
        ),
        (
            ":::{seealso}\nSource: <https://example.com>\n:::",
            [".. seealso::", "    Source: <https://example.com>"],
        ),
        # Empty body.
        (":::{note}\n:::", [".. note::"]),
        # Indented fence (nested context).
        (
            "    :::{warning}\n    Watch out.\n    :::",
            ["    .. warning::", "        Watch out."],
        ),
        # Directive with option lines.
        (
            ":::{list-table}\n:header-rows: 1\n\n* - A\n  - B\n:::",
            [".. list-table::", "    :header-rows: 1"],
        ),
    ],
    ids=[
        "note",
        "multiline",
        "with-title",
        "indented-body",
        "seealso",
        "empty-body",
        "indented-fence",
        "directive-options",
    ],
)
def test_colon_fence_conversion(myst, expected_fragments):
    result = _convert(myst)
    for fragment in expected_fragments:
        assert fragment in result


def test_colon_fence_preserves_blank_lines():
    result = _convert(":::{note}\nFirst.\n\nSecond.\n:::")
    assert "" in result.split("\n")


def test_colon_fence_blank_line_before_body():
    """Converted directive inserts blank line between header and body."""
    result = _convert(":::{code-block} python\nprint(1)\n:::")
    lines = result.split("\n")
    header_idx = next(i for i, l in enumerate(lines) if ".. code-block::" in l)
    assert lines[header_idx + 1] == "", "blank line required after directive header"


# ---- Backtick-fenced directives: ```{directive} -> .. directive:: ----------


@pytest.mark.parametrize(
    ("myst", "expected_fragments"),
    [
        (
            "```{note}\nSome content.\n```",
            [".. note::", "    Some content."],
        ),
        (
            "```{warning} Be careful\nDon't do this.\n```",
            [".. warning:: Be careful", "    Don't do this."],
        ),
        (
            "```{code-block} python\nprint(1)\n```",
            [".. code-block:: python", "    print(1)"],
        ),
        # Empty body.
        ("```{tip}\n```", [".. tip::"]),
        # Inline code inside body must not close the fence.
        (
            "```{note}\nUse `foo` here.\n```",
            [".. note::", "    Use ``foo`` here."],
        ),
    ],
    ids=["note", "with-title", "code-block", "empty-body", "inline-code-in-body"],
)
def test_backtick_fence_conversion(myst, expected_fragments):
    result = _convert(myst)
    for fragment in expected_fragments:
        assert fragment in result


def test_mixed_colon_outer_backtick_inner():
    """Colon fence wrapping a backtick-fenced code block."""
    myst = ":::{note}\nExample:\n\n```{code-block} python\nx = 1\n```\n:::"
    result = _convert(myst)
    assert ".. note::" in result
    assert ".. code-block:: python" in result


# ---- Plain code fences: ```lang -> .. code-block:: lang ---------------------


@pytest.mark.parametrize(
    ("myst", "expected_fragments"),
    [
        # With language identifier.
        (
            "```python\nprint(1)\n```",
            [".. code-block:: python", "    print(1)"],
        ),
        # No language identifier.
        (
            "```\nsome code\n```",
            [".. code-block::", "    some code"],
        ),
        # Language with hyphen.
        (
            "```shell-session\n$ ls\n```",
            [".. code-block:: shell-session", "    $ ls"],
        ),
        # Multi-line body.
        (
            "```python\nx = 1\ny = 2\n```",
            [".. code-block:: python", "    x = 1", "    y = 2"],
        ),
        # Indented fence.
        (
            "    ```python\n    x = 1\n    ```",
            ["    .. code-block:: python", "        x = 1"],
        ),
        # Language with dots (like c++, c#).
        (
            "```c++\nint x = 0;\n```",
            [".. code-block:: c++", "    int x = 0;"],
        ),
    ],
    ids=[
        "with-language",
        "no-language",
        "hyphenated-language",
        "multiline-body",
        "indented-fence",
        "language-with-special-chars",
    ],
)
def test_plain_code_fence_conversion(myst, expected_fragments):
    result = _convert(myst)
    for fragment in expected_fragments:
        assert fragment in result


def test_plain_code_fence_blank_line_before_body():
    """Converted plain code fence inserts blank line between header and body."""
    result = _convert("```python\nprint(1)\n```")
    lines = result.split("\n")
    header_idx = next(i for i, l in enumerate(lines) if ".. code-block::" in l)
    assert lines[header_idx + 1] == "", "blank line required after directive header"


def test_plain_code_fence_not_directive():
    """Plain code fences must not be confused with directive fences."""
    # Directive fence: already handled by the directive regex.
    directive = "```{note}\nSome content.\n```"
    result = _convert(directive)
    assert ".. note::" in result
    assert ".. code-block::" not in result


def test_plain_code_fence_idempotent():
    """Already-converted code-block directive passes through unchanged."""
    rst = ".. code-block:: python\n\n    print(1)"
    assert _convert(rst) == rst


# ---- Footnotes: [^label] -> [#label]_ / [^label]: -> .. [#label] -----------


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        # Simple reference.
        ("See this note[^1].", "See this note[#1]_."),
        # Reference with word label.
        ("Details in[^footnote-a].", "Details in[#footnote-a]_."),
        # Multiple references.
        (
            "Text[^a] and more[^b].",
            "Text[#a]_ and more[#b]_.",
        ),
        # Reference at end of line.
        ("End of line[^ref]", "End of line[#ref]_"),
    ],
    ids=[
        "simple-ref",
        "word-label-ref",
        "multiple-refs",
        "ref-at-eol",
    ],
)
def test_footnote_reference_conversion(myst, expected):
    assert _convert(myst) == expected


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        # Single-line definition.
        ("[^1]: This is a footnote.", ".. [#1] This is a footnote."),
        # Definition with word label.
        ("[^note-a]: Explanation here.", ".. [#note-a] Explanation here."),
        # Definition with empty text (opening line of multi-line footnote).
        ("[^label]:", ".. [#label] "),
    ],
    ids=[
        "simple-def",
        "word-label-def",
        "empty-text-def",
    ],
)
def test_footnote_definition_conversion(myst, expected):
    assert _convert(myst) == expected


def test_footnote_ref_and_def_combined():
    """Footnote reference and definition in the same docstring."""
    myst = "Some claim[^1].\n\n[^1]: Source for the claim."
    result = _convert(myst)
    assert "[#1]_" in result
    assert ".. [#1] Source for the claim." in result


def test_footnote_def_not_matched_as_ref():
    """Footnote definition must not also produce a spurious reference."""
    myst = "[^1]: The definition."
    result = _convert(myst)
    # The definition is converted.
    assert result.startswith(".. [#1]")
    # No stray reference marker inside the definition line.
    assert "[#1]_" not in result


# ---- Links: [text](url) -> `text <url>`_ ----------------------------------


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        (
            "[click here](https://example.com)",
            "`click here <https://example.com>`_",
        ),
        (
            "See [the docs](https://docs.example.com) for details.",
            "See `the docs <https://docs.example.com>`_ for details.",
        ),
        (
            "[Wikipedia](https://en.wikipedia.org/wiki/Foo)",
            "`Wikipedia <https://en.wikipedia.org/wiki/Foo>`_",
        ),
        # Adjacent to punctuation.
        (
            "See [docs](https://example.com).",
            "See `docs <https://example.com>`_.",
        ),
    ],
    ids=["simple", "mid-sentence", "parens-in-url", "adjacent-to-punctuation"],
)
def test_link_conversion(myst, expected):
    assert _convert(myst) == expected


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        # Image links must not be converted.
        ("![logo](https://example.com/logo.png)", None),
    ],
    ids=["image-link"],
)
def test_link_not_converted(myst, expected):
    assert _convert(myst) == (expected if expected is not None else myst)


def test_multiple_links_on_same_line():
    myst = "[A](https://example.com/a) and [B](https://example.com/b)"
    result = _convert(myst)
    assert "`A <https://example.com/a>`_" in result
    assert "`B <https://example.com/b>`_" in result


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        (
            "[`sys.platform`](https://docs.python.org/3)",
            "`sys.platform <https://docs.python.org/3>`_",
        ),
        (
            "the [`/proc`](https://example.com) filesystem",
            "the `/proc <https://example.com>`_ filesystem",
        ),
        (
            "[from `foo` to `bar`](https://example.com)",
            "`from foo to bar <https://example.com>`_",
        ),
    ],
    ids=["code-label", "code-label-mid-sentence", "multiple-code-spans"],
)
def test_link_strips_backticks_from_label(myst, expected):
    """reST has no nested markup, so backticks are stripped from link labels."""
    assert _convert(myst) == expected


# ---- Inline code: `text` -> ``text`` ---------------------------------------


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        ("`True`", "``True``"),
        ("Returns `True` if detected.", "Returns ``True`` if detected."),
        ("`foo` and `bar`", "``foo`` and ``bar``"),
        ("`platform.machine()`", "``platform.machine()``"),
        # Single character.
        ("`x`", "``x``"),
        # Regex metacharacters.
        ("`foo*bar`", "``foo*bar``"),
        ("`a[0]`", "``a[0]``"),
        # Adjacent to punctuation.
        ("`code`.", "``code``."),
        ("(`code`)", "(``code``)"),
        # At line boundaries.
        ("`start`", "``start``"),
        ("end `here`", "end ``here``"),
    ],
    ids=[
        "simple",
        "in-sentence",
        "multiple",
        "dotted-call",
        "single-char",
        "regex-star",
        "regex-bracket",
        "before-period",
        "in-parens",
        "start-of-line",
        "end-of-line",
    ],
)
def test_inline_code_conversion(myst, expected):
    assert _convert(myst) == expected


@pytest.mark.parametrize(
    "text",
    [
        # Already-doubled backticks must not be quadrupled.
        "Returns ``True`` if detected.",
        # Double backticks with braces (converter output) must pass through.
        "``{version}``",
        # Triple backticks must not be mangled.
        "```not inline```",
        # Backtick span across newlines must not match.
        "`start\nend`",
    ],
    ids=[
        "double-backtick-passthrough",
        "braces-in-double-backticks",
        "triple-backticks",
        "across-newlines",
    ],
)
def test_inline_code_not_converted(text):
    assert _convert(text) == text


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        ("{func}`foo` returns `True`", ":func:`foo` returns ``True``"),
        ("a {data}`~X` or `None`", "a :data:`~X` or ``None``"),
        ("`some_var` is a {class}`str`", "``some_var`` is a :class:`str`"),
    ],
    ids=["xref-then-code", "xref-or-code", "code-then-xref"],
)
def test_inline_code_no_cross_contamination_with_xref(myst, expected):
    """Closing backtick of a cross-ref must not pair with inline code."""
    assert _convert(myst) == expected


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        ("a `Foo` and `_bar` end", "a ``Foo`` and ``_bar`` end"),
        ("a `Foo` then {func}`_bar` end", "a ``Foo`` then :func:`_bar` end"),
        ("a `_bar` then `Foo` end", "a ``_bar`` then ``Foo`` end"),
        ("see `apple`, `_pear`, `cherry`", "see ``apple``, ``_pear``, ``cherry``"),
    ],
    ids=[
        "code-then-underscore-code",
        "code-then-underscore-xref",
        "underscore-code-first",
        "underscore-code-middle",
    ],
)
def test_leading_underscore_span_not_a_hyperlink_ref(myst, expected):
    """A backtick span starting with `_` must not be read as a hyperlink ref.

    The reST hyperlink-reference pattern ``` `label`_ ``` would otherwise let
    the protection regex span the gap between two inline-code spans (consuming
    the first span's closing backtick and the second span's leading underscore),
    corrupting both. The opening backtick of a hyperlink ref is anchored at a
    word boundary to prevent this.
    """
    assert _convert(myst) == expected


@pytest.mark.parametrize(
    "text",
    [
        # A braced word abutting the literal's closing backticks must not be
        # misread as a {role} with an empty target.
        "``{levelname}:{message}`` and ``%(levelname)s``",
        # Same shape inside a reST table row.
        "``format``  ``{levelname}:{message}``  the default",
        # A literal ending in a braced word, followed by more prose.
        "set to ``{version}`` before the build",
    ],
    ids=["brace-abuts-close", "table-row", "trailing-prose"],
)
def test_rst_literals_are_opaque(text):
    """Double-backtick reST literals pass through every step verbatim."""
    assert _convert(text) == text


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        # Role-shaped text inside a code span is an option name, not a role:
        # it must not swallow the cross-reference that follows.
        (
            "`:tag-pattern:` defaults to {data}`DEFAULT_TAG_PATTERN`.",
            "``:tag-pattern:`` defaults to :data:`DEFAULT_TAG_PATTERN`.",
        ),
        ("the `:manpage:` role", "the ``:manpage:`` role"),
        # A real role right after prose still converts.
        ("see {data}`X` and `:path:`", "see :data:`X` and ``:path:``"),
    ],
    ids=["span-then-xref", "span-alone", "xref-then-span"],
)
def test_role_shaped_code_span_not_protected_as_role(myst, expected):
    """A backtick-preceded role pattern sits inside a code span, not a role."""
    assert _convert(myst) == expected


# ---- Idempotent pass-through for reST docstrings ---------------------------


@pytest.mark.parametrize(
    "text",
    [
        ":func:`~extra_platforms.is_linux`",
        ".. note::\n    Some content.",
        ".. code-block:: python\n\n    print(1)",
        "`click here <https://example.com>`_",
        "`click here <https://example.com>`__",
        "Returns ``True`` if detected.",
        ":param name: The name.\n:return: A value.",
    ],
    ids=[
        "xref",
        "admonition",
        "code-block",
        "named-hyperlink",
        "anonymous-hyperlink",
        "double-backtick",
        "field-list",
    ],
)
def test_idempotent_rst_passthrough(text):
    assert _convert(text) == text


def test_idempotent_already_converted():
    """Running the converter twice produces the same result."""
    myst = (
        "{func}`foo` returns `True`.\n"
        "\n"
        ":::{note}\nSee [docs](https://example.com).\n:::"
    )
    first = _convert(myst)
    second = _convert(first)
    assert first == second


def test_idempotent_full_rst_docstring():
    """A complete reST docstring passes through unchanged."""
    text = (
        "Return :data:`True` if current architecture is"
        " :data:`~extra_platforms.ARM`.\n"
        "\n"
        ".. hint::\n"
        "    This is a fallback detection for generic ARM architecture."
        " It will return\n"
        "    ``True`` for any ARM architecture not specifically covered"
        " by the more precise\n"
        "    variants: :func:`~extra_platforms.is_aarch64`,"
        " :func:`~extra_platforms.is_armv5tel`.\n"
    )
    assert _convert(text) == text


# ---- Mixed MyST + reST (generated docstrings) ------------------------------


def test_mixed_myst_attribute_then_rst_metadata():
    """Simulates generate_docstring() output: MyST attribute docstring
    concatenated with reST metadata lines.
    """
    text = (
        "All BSD platforms.\n"
        "\n"
        ":::{note}\n"
        "Includes FreeBSD and macOS.\n"
        ":::\n"
        "\n"
        "- **ID**: ``bsd``\n"
        "- **Detection function**: :func:`~is_bsd`\n"
    )
    result = _convert(text)
    assert ".. note::" in result
    assert "    Includes FreeBSD and macOS." in result
    assert "- **ID**: ``bsd``" in result
    assert "- **Detection function**: :func:`~is_bsd`" in result


# ---- Realistic docstring patterns ------------------------------------------


def test_real_detection_function():
    myst = (
        "Return {data}`True` if current platform is"
        " {data}`~extra_platforms.ANDROID`.\n"
        "\n"
        ":::{seealso}\n"
        "Source:\n"
        "[kivy/utils.py](https://github.com/kivy/kivy/blob/master/kivy/utils.py)\n"
        ":::"
    )
    result = _convert(myst)
    assert ":data:`True`" in result
    assert ":data:`~extra_platforms.ANDROID`" in result
    assert ".. seealso::" in result
    assert (
        "    `kivy/utils.py <https://github.com/kivy/kivy/blob/master/kivy/utils.py>`_"
    ) in result


def test_real_group_with_wikipedia_link():
    myst = (
        "All BSD platforms.\n"
        "\n"
        ":::{note}\n"
        "Are considered of this family ([according Wikipedia]"
        "(https://en.wikipedia.org/wiki/Template:Unix)):\n"
        "\n"
        "- `386BSD` (`FreeBSD`, `NetBSD`)\n"
        "- `Darwin` (`macOS`, `iOS`)\n"
        ":::"
    )
    result = _convert(myst)
    assert ".. note::" in result
    assert (
        "    Are considered of this family"
        " (`according Wikipedia <https://en.wikipedia.org/wiki/Template:Unix>`_):"
    ) in result
    assert "    - ``386BSD`` (``FreeBSD``, ``NetBSD``)" in result


def test_all_conversions_combined():
    """A docstring exercising every conversion step in one pass."""
    myst = (
        "Return {data}`True` if `path` exists.\n"
        "\n"
        "See [os.path](https://docs.python.org/3/library/os.path.html)\n"
        "for details.\n"
        "\n"
        "```{warning}\n"
        "Symlinks are not resolved.\n"
        "```\n"
        "\n"
        ":param path: The filesystem path.\n"
        ":return: `True` or `False`.\n"
    )
    result = _convert(myst)
    # Xref converted.
    assert ":data:`True`" in result
    # Inline code doubled.
    assert "``path``" in result
    # Link converted.
    assert "`os.path <https://docs.python.org/3/library/os.path.html>`_" in result
    # Backtick fence converted.
    assert ".. warning::" in result
    assert "    Symlinks are not resolved." in result
    # Field list unchanged.
    assert ":param path:" in result
    # Inline code in field list doubled.
    assert "``True`` or ``False``" in result


def test_real_caution_with_code_block():
    myst = (
        "Return {data}`True` if architecture is"
        " {data}`~extra_platforms.AARCH64`.\n"
        "\n"
        ":::{caution}\n"
        "`platform.machine()` returns different values depending on the OS:\n"
        "\n"
        "- Linux: `aarch64`\n"
        "- macOS: `arm64`\n"
        "- Windows: `ARM64`\n"
        ":::"
    )
    result = _convert(myst)
    assert ":data:`True`" in result
    assert ".. caution::" in result
    assert (
        "    ``platform.machine()`` returns different values depending on the OS:"
    ) in result
    assert "    - Linux: ``aarch64``" in result


# ---- MyST inside field lists (:param:, :return:, :raises:) -------------------


@pytest.mark.parametrize(
    ("myst", "expected"),
    [
        # Inline code inside :param:.
        (
            ":param path: The `path` to the file.",
            ":param path: The ``path`` to the file.",
        ),
        # Cross-reference inside :param:.
        (
            ":param config: A {class}`Config` instance.",
            ":param config: A :class:`Config` instance.",
        ),
        # Cross-reference with tilde inside :return:.
        (
            ":return: A {class}`~orchard.config.Config` object.",
            ":return: A :class:`~orchard.config.Config` object.",
        ),
        # Markdown link inside :param:.
        (
            ":param url: See [the docs](https://example.com) for format.",
            ":param url: See `the docs <https://example.com>`_ for format.",
        ),
        # Multiple inline codes inside :return:.
        (
            ":return: `True` if valid, `False` otherwise.",
            ":return: ``True`` if valid, ``False`` otherwise.",
        ),
        # Mixed xref and inline code inside :raises:.
        (
            ":raises ValueError: If `name` is not a {class}`str`.",
            ":raises ValueError: If ``name`` is not a :class:`str`.",
        ),
        # Inline code in multi-line :param: continuation.
        (
            ":param items: A list of `str` values.\n"
            "    Each must be a valid {class}`Path`.",
            ":param items: A list of ``str`` values.\n"
            "    Each must be a valid :class:`Path`.",
        ),
    ],
    ids=[
        "inline-code-in-param",
        "xref-in-param",
        "tilde-xref-in-return",
        "link-in-param",
        "multiple-codes-in-return",
        "mixed-in-raises",
        "multiline-param-continuation",
    ],
)
def test_myst_inside_field_lists(myst, expected):
    """MyST inline constructs inside field list entries are converted."""
    assert _convert(myst) == expected


def test_full_docstring_with_myst_field_lists():
    """Realistic docstring with MyST in both prose and field list entries."""
    myst = (
        "Process a configuration file.\n"
        "\n"
        ":::{note}\n"
        "Only `TOML` files are supported.\n"
        ":::\n"
        "\n"
        ":param path: Filesystem `path` to process.\n"
        ":param config: A {class}`~orchard.config.Config` instance.\n"
        ":return: `True` if the file was processed.\n"
        ":raises FileNotFoundError: If `path` does not exist.\n"
    )
    result = _convert(myst)
    # Prose converted.
    assert ".. note::" in result
    assert "    Only ``TOML`` files are supported." in result
    # Field list markers unchanged.
    assert ":param path:" in result
    assert ":param config:" in result
    assert ":return:" in result
    assert ":raises FileNotFoundError:" in result
    # Content inside field lists converted.
    assert "Filesystem ``path`` to process." in result
    assert ":class:`~orchard.config.Config`" in result
    assert "``True`` if the file was processed." in result
    assert "If ``path`` does not exist." in result


# ---- Unsupported constructs and known limitations ----------------------------


@pytest.mark.parametrize(
    ("myst", "description"),
    [
        # MyST substitution references are not converted.
        ("The version is {{version}}.", "substitution-reference"),
        # Definition list syntax is not converted.
        ("Term\n: Definition of the term.", "definition-list"),
        # Heading syntax is not converted (and should not appear in docstrings).
        ("## Subheading", "heading-syntax"),
        # Strikethrough is not converted.
        ("This is ~~deleted~~ text.", "strikethrough"),
        # Task list checkboxes are not converted.
        ("- [x] Done\n- [ ] Not done", "task-list"),
    ],
    ids=[
        "substitution-reference",
        "definition-list",
        "heading-syntax",
        "strikethrough",
        "task-list",
    ],
)
def test_unsupported_constructs_pass_through(myst, description):
    """Unsupported MyST constructs pass through unchanged."""
    assert _convert(myst) == myst, f"Expected {description} to pass through unchanged"


def test_curly_braces_in_inline_code():
    """Inline code containing `{` and `}` characters.

    A standalone `{word}` in single backticks is safe: it gets doubled to
    ``{word}`` because the xref regex needs the `{word}`target`` pattern
    (two backtick-delimited spans). Double-backtick input also passes through.

    The dangerous case is `{word}`text`` where the braces plus adjacent
    backtick-delimited span mimics the xref pattern. The `convert-to-myst`
    command intentionally keeps these as double backticks to avoid this.
    """
    # Double backticks with braces: safe, passes through.
    assert _convert("``{version}``") == "``{version}``"
    # Single backtick with braces but no adjacent backtick span: safe.
    assert _convert("`{version}`") == "``{version}``"
    # Pattern that mimics a cross-reference: {word}`target`.
    # This IS misinterpreted as a xref.
    result = _convert("`{foo}`bar`")
    assert result != "``{foo}`bar``", (
        "Known limitation: `{foo}`bar` is misinterpreted as a cross-reference"
    )


def test_plain_code_fence_empty_body():
    """Plain code fence with an empty body."""
    myst = "```python\n```"
    result = _convert(myst)
    assert ".. code-block:: python" in result


def test_nested_same_type_fences_not_supported():
    """Nested fences of the same type are not reliably converted.

    A colon fence inside a colon fence, or a backtick fence inside a backtick
    fence, may not parse correctly because the regex matches the first closing
    fence it finds.
    """
    myst = ":::{note}\nOuter content.\n\n:::{warning}\nInner content.\n:::\n\n:::"
    result = _convert(myst)
    # The outer note should be converted.
    assert ".. note::" in result
    # The inner warning may or may not convert correctly depending on regex
    # greediness. We just verify no crash.
    assert "Inner content." in result


def test_directive_inside_field_list_not_supported():
    """Fenced directives inside field list entries do not render correctly.

    Field list entries in Sphinx are paragraph-level constructs.
    Block-level MyST content (admonitions, code blocks) inside them is
    converted by the regex but won't render correctly in Sphinx.
    """
    myst = ":param path: The path.\n\n    :::{note}\n    Extra info.\n    :::\n"
    result = _convert(myst)
    # The directive syntax is converted (the regex does not know about context).
    assert ".. note::" in result
    # But this won't render correctly as a field list continuation in Sphinx.
    assert ":param path:" in result


def test_link_with_parentheses_in_url():
    """Markdown links where the URL contains parentheses."""
    myst = "[wiki](https://en.wikipedia.org/wiki/Foo_(bar))"
    result = _convert(myst)
    # The regex matches the first closing `)`, so the URL is truncated.
    # This is a known limitation of the simple regex approach.
    assert "`_" in result


def test_consecutive_field_list_entries_all_converted():
    """Multiple consecutive field list entries each get their content converted."""
    myst = (
        ":param a: First `param`.\n"
        ":param b: Second {class}`Config`.\n"
        ":param c: Third [link](https://example.com).\n"
        ":return: A `bool`.\n"
    )
    result = _convert(myst)
    assert "First ``param``." in result
    assert "Second :class:`Config`." in result
    assert "Third `link <https://example.com>`_." in result
    assert "A ``bool``." in result


def test_empty_field_list_content():
    """Field list entries with empty or whitespace-only content."""
    assert _convert(":param x:") == ":param x:"
    assert _convert(":return:") == ":return:"
    assert _convert(":param x: ") == ":param x: "


def test_xref_adjacent_to_field_list_colon():
    """Cross-reference immediately after the field list colon."""
    myst = ":param x: {class}`Foo` instance."
    expected = ":param x: :class:`Foo` instance."
    assert _convert(myst) == expected


def test_multiple_xrefs_in_single_field_entry():
    """Multiple cross-references in one field list entry."""
    myst = ":return: A {class}`dict` mapping {class}`str` to {class}`int`."
    expected = ":return: A :class:`dict` mapping :class:`str` to :class:`int`."
    assert _convert(myst) == expected


def test_link_with_backtick_label_in_field_list():
    """Markdown link with backtick-wrapped label inside a field list entry."""
    myst = ":param url: See [`requests`](https://example.com) docs."
    expected = ":param url: See `requests <https://example.com>`_ docs."
    assert _convert(myst) == expected


# ---- Extension setup ---------------------------------------------------------


def test_setup_rejects_wrong_extension_order():
    """Extension must error if sphinx_autodoc_typehints loaded first."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    sphinx_errors = pytest.importorskip("sphinx.errors")
    ExtensionError = sphinx_errors.ExtensionError

    app = MagicMock()
    # Simulate sphinx_autodoc_typehints already registered.
    app.extensions = {_TYPEHINTS_EXT: SimpleNamespace()}

    with pytest.raises(ExtensionError, match="must be listed before"):
        setup(app)


def test_setup_accepts_correct_order():
    """Extension loads normally when sphinx_autodoc_typehints is absent."""
    from unittest.mock import MagicMock

    app = MagicMock()
    app.extensions = {}

    result = setup(app)
    assert result["parallel_read_safe"] is True
    app.connect.assert_called_once()
    assert app.connect.call_args[0][0] == "autodoc-process-docstring"
