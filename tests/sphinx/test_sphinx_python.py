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
"""Tests for the ``python:*`` Sphinx directive family.

Covers ``python:source``, ``python:run``, and the three render variants:

- ``python:render`` (host parser)
- ``python:render-myst`` (forced MyST, regardless of host)
- ``python:render-rst`` (forced reST, regardless of host)
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from click.testing import CliRunner

from click_extra.cli import refresh_directives_cmd
from click_extra.sphinx.python import (
    MIRROR_MARKER_END,
    MIRROR_MARKER_START,
    _rewrite_mirror_regions,
    update_mirror_blocks,
)

from .conftest import FormatType, SphinxAppWrapper


def test_python_run_renders_stdout(sphinx_app_myst):
    """``python:run`` captures ``print`` output and renders it in a code block."""
    content = dedent("""
        ```{python:run}
        print("It works!")
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert 'class="highlight-text' in html or 'class="highlight-default' in html
    assert "It works!" in html


def test_python_source_seeds_namespace_for_python_run(sphinx_app_myst):
    """``python:source`` runs silently; a follow-up ``python:run`` reuses its imports."""
    content = dedent("""
        ```{python:source}
        from textwrap import dedent
        greeting = "hello, sphinx"
        ```

        ```{python:run}
        print(dedent(greeting).upper())
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert 'class="highlight-python' in html
    assert "HELLO, SPHINX" in html


def test_python_run_language_override(sphinx_app_myst):
    """``:language:`` overrides the default ``text`` lexer for the result block."""
    content = dedent("""
        ```{python:run} json
        import json
        print(json.dumps({"name": "sphinx", "kind": "doc"}))
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert 'class="highlight-json' in html
    assert "&quot;name&quot;" in html
    assert "&quot;sphinx&quot;" in html


def test_python_run_emphasize_lines_split(sphinx_app_myst):
    """``:emphasize-lines:`` highlights source only; ``:emphasize-result-lines:``
    highlights result only: independently, on the same block."""
    content = dedent("""
        ```{python:run}
        :show-source:
        :emphasize-lines: 1
        :emphasize-result-lines: 2
        print("first line")
        print("second line")
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    # Source block carries the source emphasis on line 1 (the `print("first line")`).
    assert '<span class="hll"><span class="nb">print</span>' in html
    # Result block carries the result emphasis on line 2 (the literal `second line`).
    assert '<span class="hll">second line\n</span>' in html
    # And the sibling lines are not highlighted.
    assert '<span class="hll">first line\n</span>' not in html, (
        "result emphasis must not bleed onto line 1 of the result block"
    )


def test_python_render_passes_block_level_html(sphinx_app_myst):
    """``python:render`` passes block-level raw HTML through unchanged.

    A naked ``print('<div>...</div>')`` should reach the rendered page without
    any ``{raw} html`` wrapping. Locks down the natural-form pattern so a future
    MyST upgrade or extension reordering can't silently regress it.
    """
    content = dedent("""
        ```{python:render}
        print('<div class="custom-marker">')
        print('<span style="color: #ff8800">orange span</span>')
        print('</div>')
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert '<div class="custom-marker">' in html
    assert '<span style="color: #ff8800">orange span</span>' in html


def test_python_render_host_myst_injects_table(sphinx_app_myst):
    """``python:render`` parses captured stdout with the host (MyST) parser."""
    content = dedent("""
        ```{python:render}
        rows = [("apple", 3), ("banana", 5), ("cherry", 8)]
        print("| Fruit | Count |")
        print("|-------|------:|")
        for name, count in rows:
            print(f"| {name} | {count} |")
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "<table" in html
    assert "<th" in html
    for fruit in ("apple", "banana", "cherry"):
        assert f"<td>{fruit}</td>" in html or f">{fruit}<" in html


def test_python_render_host_myst_injects_heading(sphinx_app_myst):
    """A heading printed by ``python:render`` becomes a real heading node."""
    content = dedent("""
        ```{python:render}
        print("## Generated section")
        print()
        print("Body text under the generated heading.")
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "Generated section" in html
    assert "<h2" in html or "<h3" in html
    assert "Body text under the generated heading." in html


def test_python_render_host_rst_injects_admonition(sphinx_app_rst):
    """``python:render`` in an rST host: stdout is parsed as reST."""
    content = dedent("""
        .. python:render::

            print(".. note::")
            print()
            print("   A pear ripens after picking.")
    """)
    html = sphinx_app_rst.build_document(content)
    assert html is not None
    assert "admonition" in html and "note" in html
    assert "A pear ripens after picking." in html


def test_python_render_myst_in_rst_host(sphinx_app_rst):
    """``python:render-myst`` forces MyST parsing inside an rST host document.

    This is the headline use case: an rST file embeds Python that prints
    MyST markup and the directive parses it as MyST regardless of host.
    """
    content = dedent("""
        .. python:render-myst::

            print("| Fruit | Count |")
            print("|-------|------:|")
            print("| mango | 4 |")
            print("| kiwi | 7 |")
    """)
    html = sphinx_app_rst.build_document(content)
    assert html is not None
    assert "<table" in html
    for fruit in ("mango", "kiwi"):
        assert f"<td>{fruit}</td>" in html or f">{fruit}<" in html


def test_python_render_rst_in_myst_host(sphinx_app_myst):
    """``python:render-rst`` forces reST parsing inside a MyST host document."""
    content = dedent("""
        ```{python:render-rst}
        print(".. note::")
        print()
        print("   A persimmon must be very ripe to eat raw.")
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "admonition" in html and "note" in html
    assert "A persimmon must be very ripe to eat raw." in html


def test_python_render_myst_in_myst_host_still_works(sphinx_app_myst):
    """``python:render-myst`` works in MyST hosts too; it always picks MyST."""
    content = dedent("""
        ```{python:render-myst}
        print("**Bold tomato.**")
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "<strong>Bold tomato.</strong>" in html


def test_python_render_rst_in_rst_host_still_works(sphinx_app_rst):
    """``python:render-rst`` works in rST hosts too; it always picks reST."""
    content = dedent("""
        .. python:render-rst::

            print("**Bold cucumber.**")
    """)
    html = sphinx_app_rst.build_document(content)
    assert html is not None
    assert "<strong>Bold cucumber.</strong>" in html


def test_exec_directives_disabled_by_default(tmp_path):
    """Without the opt-in flag, ``click:*`` and ``python:*`` are not registered.

    The Sphinx build still succeeds but neither family's directive body is
    ever executed. This is the desired security default: a project that
    adds ``click_extra.sphinx`` to its extensions list does not silently
    gain build-time arbitrary Python execution.

    The exact rendering of an unrecognized directive is parser-dependent
    (MyST silently swallows it; reST emits a system message), so the
    assertion focuses on the security-relevant invariant: the directive
    body's ``print`` output never reaches the rendered HTML.
    """
    factory = SphinxAppWrapper.create(
        FormatType.MYST, tmp_path, enable_exec_directives=False
    )
    app = next(factory)
    assert isinstance(app, SphinxAppWrapper)
    sentinel = "EXEC-MUST-NOT-HAPPEN-9c1f8"
    content = dedent(f"""
        ```{{python:run}}
        print("{sentinel}")
        ```

        ```{{click:source}}
        from click import command, echo

        @command
        def boom():
            echo("{sentinel}-click")
        ```

        ```{{click:run}}
        invoke(boom)
        ```
    """)
    html = app.build_document(content)
    assert html is not None
    assert sentinel not in html, "directive executed despite the opt-in gate being off"


def test_exec_directives_enabled_with_opt_in(tmp_path):
    """Setting ``click_extra_enable_exec_directives = True`` activates them."""
    factory = SphinxAppWrapper.create(
        FormatType.MYST, tmp_path, enable_exec_directives=True
    )
    app = next(factory)
    assert isinstance(app, SphinxAppWrapper)
    content = dedent("""
        ```{python:run}
        print("Opt-in works.")
        ```
    """)
    html = app.build_document(content)
    assert html is not None
    assert "Opt-in works." in html


def test_python_runner_isolated_from_click_runner(sphinx_app_myst):
    """The Python and Click runners hold independent namespaces."""
    content = dedent("""
        ```{python:source}
        secret = "python-only"
        ```

        ```{click:source}
        from click import command, echo

        @command
        def show():
            echo("click-only")
        ```

        ```{click:run}
        invoke(show)
        ```

        ```{python:run}
        print(secret)
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "click-only" in html
    assert "python-only" in html


# --- python:render :mirror: source mirroring ----------------------------------

_MIRROR_TABLE_BLOCK = dedent("""
    # Title

    ```{python:render}
    :mirror:
    rows = [("apple", 3), ("banana", 5), ("cherry", 8)]
    print("| Fruit  | Count |")
    print("| :----- | ----: |")
    for name, count in rows:
        print(f"| {name} | {count} |")
    ```

    Trailing prose.
""")


def test_mirror_rewrite_inserts_region():
    """A mirror block with no region yet gets one inserted below the fence."""
    out = _rewrite_mirror_regions(_MIRROR_TABLE_BLOCK, "<test>")
    assert out.count(MIRROR_MARKER_START) == 1
    assert out.count(MIRROR_MARKER_END) == 1
    assert "| apple | 3 |" in out
    # The fence and the trailing prose are preserved around the region.
    assert "```{python:render}" in out
    assert out.index("```{python:render}") < out.index(MIRROR_MARKER_START)
    assert out.index(MIRROR_MARKER_END) < out.index("Trailing prose.")


def test_mirror_rewrite_is_idempotent():
    """Re-running over an already-mirrored document is a no-op."""
    once = _rewrite_mirror_regions(_MIRROR_TABLE_BLOCK, "<test>")
    twice = _rewrite_mirror_regions(once, "<test>")
    assert once == twice
    # The region is replaced in place, never appended a second time.
    assert twice.count(MIRROR_MARKER_START) == 1


def test_mirror_rewrite_replaces_stale_region():
    """A stale region is refreshed from the block's current output."""
    stale = dedent(f"""
        ```{{python:render}}
        :mirror:
        print("| Fruit |")
        print("| :---- |")
        print("| apple |")
        ```

        {MIRROR_MARKER_START}

        | Fruit |
        | :---- |
        | STALE |

        {MIRROR_MARKER_END}

        After.
    """)
    out = _rewrite_mirror_regions(stale, "<test>")
    assert "| apple |" in out
    assert "STALE" not in out
    assert out.count(MIRROR_MARKER_START) == 1
    assert "After." in out


def test_mirror_rewrite_skips_example_nested_in_code_block():
    """A mirror block shown inside a longer code-block fence is never executed."""
    documented = dedent("""
        ````{code-block} markdown
        ```{python:render}
        :mirror:
        print("MUST-NOT-RUN")
        ```
        ````
    """)
    out = _rewrite_mirror_regions(documented, "<test>")
    # No region is generated: the inner block was copied verbatim, not run.
    assert MIRROR_MARKER_START not in out
    assert out == documented


def test_python_render_mirror_renders_fresh_without_touching_source(sphinx_app_myst):
    """`:mirror:` renders the table once; the build never writes to the source."""
    html = sphinx_app_myst.build_document(_MIRROR_TABLE_BLOCK)
    assert html is not None
    # Rendered exactly once (from the in-memory mirrored region; the directive
    # itself emits nothing in mirror mode, so there is no second copy).
    assert html.count("<table") == 1
    for fruit in ("apple", "banana", "cherry"):
        assert fruit in html
    # The build is read-only: the committed source is byte-for-byte untouched
    # (the disk region is refreshed offline by update_mirror_blocks).
    source = (Path(sphinx_app_myst.srcdir) / "index.md").read_text(encoding="utf-8")
    assert source == _MIRROR_TABLE_BLOCK


def test_update_mirror_blocks_populates_and_idempotent(tmp_path):
    """The offline refresher inserts the region, then round-trips clean."""
    doc = tmp_path / "page.md"
    doc.write_text(_MIRROR_TABLE_BLOCK, encoding="utf-8")
    # First pass inserts the region on disk.
    assert update_mirror_blocks([doc]) == [doc]
    source = doc.read_text(encoding="utf-8")
    assert MIRROR_MARKER_START in source
    assert MIRROR_MARKER_END in source
    assert "| apple | 3 |" in source
    # Second pass is a no-op.
    assert update_mirror_blocks([doc]) == []


def test_update_mirror_blocks_check_mode(tmp_path):
    """`check=True` reports the stale file without writing it."""
    doc = tmp_path / "page.md"
    doc.write_text(_MIRROR_TABLE_BLOCK, encoding="utf-8")
    assert update_mirror_blocks([doc], check=True) == [doc]
    assert doc.read_text(encoding="utf-8") == _MIRROR_TABLE_BLOCK


def test_refresh_directives_cli_refreshes_mirror_blocks(tmp_path):
    """`click-extra refresh-directives` covers mirror regions too."""
    doc = tmp_path / "page.md"
    doc.write_text(_MIRROR_TABLE_BLOCK, encoding="utf-8")
    runner = CliRunner()
    # A missing region exits non-zero under --check, without writing.
    result = runner.invoke(refresh_directives_cmd, ["--check", str(doc)])
    assert result.exit_code == 1
    assert doc.read_text(encoding="utf-8") == _MIRROR_TABLE_BLOCK
    # Write mode inserts the region and names the file.
    result = runner.invoke(refresh_directives_cmd, [str(doc)])
    assert result.exit_code == 0
    assert "refreshed" in result.output
    assert MIRROR_MARKER_START in doc.read_text(encoding="utf-8")
    # A freshly refreshed region is clean.
    result = runner.invoke(refresh_directives_cmd, ["--check", str(doc)])
    assert result.exit_code == 0


def test_python_render_mirror_show_source_still_single_table(sphinx_app_myst):
    """`:mirror: :show-source:` shows the Python but still renders one table."""
    content = dedent("""
        ```{python:render}
        :mirror:
        :show-source:
        print("| Fruit  | Count |")
        print("| :----- | ----: |")
        print("| apple  | 3     |")
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    # The Python source is shown as a highlighted block...
    assert 'class="highlight-python' in html
    # ...and the generated table renders exactly once.
    assert html.count("<table") == 1
    assert "apple" in html
