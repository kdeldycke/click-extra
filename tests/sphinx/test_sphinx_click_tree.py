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
"""Tests for the ``click:tree`` Sphinx directive."""

from __future__ import annotations

from textwrap import dedent

import pytest

KITCHEN_CLI = dedent("""\
    ```{click:source}
    :hide-source:
    from click import command, echo, group, option

    @group
    def kitchen():
        \"\"\"Manage kitchen tools and recipes.\"\"\"

    @kitchen.command
    @option("--minutes", type=int, default=5)
    def boil(minutes):
        \"\"\"Boil water for tea.\"\"\"
        echo(f"Boiling for {minutes} minutes.")

    @kitchen.group
    def pantry():
        \"\"\"Inspect pantry contents.\"\"\"

    @pantry.command
    def jars():
        \"\"\"List jars on the shelf.\"\"\"
        echo("Olives, honey, pickles.")
    ```
""")
"""Toy CLI reused across tests. Defines a multi-level group so the walk
exercises the recursive descent into nested :class:`click.Group` commands.
"""


def test_click_tree_renders_summary_table_and_help_blocks(sphinx_app_myst):
    """The directive expands into a GFM table + one help capture per command."""
    content = KITCHEN_CLI + dedent("""
        ```{click:tree} kitchen
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None

    # Summary table links every command to its anchor.
    assert 'href="#kitchen"' in html
    assert 'href="#kitchen-boil"' in html
    assert 'href="#kitchen-pantry"' in html
    assert 'href="#kitchen-pantry-jars"' in html

    # Each command renders its own --help capture as a shell session.
    assert "Manage kitchen tools and recipes." in html
    assert "Boil water for tea." in html
    assert "Inspect pantry contents." in html
    assert "List jars on the shelf." in html

    # Help screen heading rendered for the root.
    assert "Help screen" in html


def test_click_tree_inline_import_in_body(sphinx_app_myst):
    """The directive body runs as a preamble, so a seed ``click:source`` is optional."""
    content = dedent("""
        ```{click:tree} demo
        :max-depth: 1
        from click_extra.cli import demo
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert "Help screen" in html
    # The bundled `demo` CLI's `cli.name` is "click-extra"; the anchor
    # prefix is derived from it, not from the Python variable name.
    assert 'href="#click-extra"' in html


def test_click_tree_no_table_and_no_root(sphinx_app_myst):
    """``:no-table:`` and ``:no-root:`` drop the summary table and root block."""
    content = KITCHEN_CLI + dedent("""
        ```{click:tree} kitchen
        :no-table:
        :no-root:
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    # Subcommand sections are still emitted.
    assert "Boil water for tea." in html
    # Root help heading is gone.
    assert "Help screen" not in html
    # Summary table is gone: no anchor-linking cells.
    assert 'href="#kitchen-boil"' not in html


def test_click_tree_max_depth_truncates_walk(sphinx_app_myst):
    """``:max-depth: 1`` stops the walk at one level below the root."""
    content = KITCHEN_CLI + dedent("""
        ```{click:tree} kitchen
        :max-depth: 1
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    # Top-level commands still listed.
    assert 'href="#kitchen-boil"' in html
    assert 'href="#kitchen-pantry"' in html
    # Nested subcommand of `pantry` should be skipped: no standalone section,
    # no entry in the summary table. The `pantry --help` output naturally
    # surfaces a row for `jars` in its own subcommand listing, so we only
    # assert on the directive-generated anchor.
    assert 'href="#kitchen-pantry-jars"' not in html
    assert 'id="kitchen-pantry-jars"' not in html


def test_click_tree_label_and_anchor_prefix_override(sphinx_app_myst):
    """``:label-prefix:`` and ``:anchor-prefix:`` override the defaults."""
    content = KITCHEN_CLI + dedent("""
        ```{click:tree} kitchen
        :label-prefix: my-kitchen
        :anchor-prefix: mk
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    # Custom anchor prefix replaces the default slug.
    assert 'href="#mk-boil"' in html
    assert 'href="#mk-pantry-jars"' in html
    # And the default slug is gone.
    assert 'href="#kitchen-boil"' not in html


def test_click_tree_errors_on_non_command(sphinx_app_myst):
    """Resolving the argument to a non-Command raises a clear directive error."""
    content = dedent("""
        ```{click:source}
        :hide-source:
        not_a_cli = 42
        ```

        ```{click:tree} not_a_cli
        ```
    """)
    with pytest.raises(Exception, match="did not yield a click.Command"):
        sphinx_app_myst.build_document(content)


def test_click_tree_errors_on_unknown_name(sphinx_app_myst):
    """An expression that can't be evaluated raises a clear directive error."""
    content = dedent("""
        ```{click:tree} missing_cli
        ```
    """)
    with pytest.raises(Exception, match="failed to evaluate"):
        sphinx_app_myst.build_document(content)


def test_click_tree_errors_in_rst(sphinx_app_rst):
    """``click:tree`` raises a clear error when used in an rST document."""
    content = dedent("""
        .. click:tree:: kitchen
    """)
    with pytest.raises(Exception, match="MyST"):
        sphinx_app_rst.build_document(content)
