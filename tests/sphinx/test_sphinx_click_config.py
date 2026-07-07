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
"""Tests for the ``click:config`` Sphinx directive."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from textwrap import dedent

import pytest

from click_extra import group
from click_extra.config import CONFIG_PATH_METADATA_KEY


@dataclass
class BasketConfig:
    """Nested sub-table exercising the dotted-key expansion."""

    apples: int = 3
    """How many apples fit in the basket."""


@dataclass
class MarketConfig:
    """Toy schema reused across tests.

    Defined at module level (not inside a ``click:source`` block) so
    ``inspect.getsource`` can recover the attribute docstrings.
    """

    city: str = "Lisbon"
    """City where the market is held.

    The market moves to the main square during summer, and to the covered
    hall the rest of the year.
    """

    stalls: list[str] = field(default_factory=lambda: ["fruits", "flowers"])
    """Stall types allowed on the premises."""

    basket: BasketConfig = field(
        default_factory=BasketConfig,
        metadata={CONFIG_PATH_METADATA_KEY: "hand-basket"},
    )
    """Parent table docstring, never rendered: only leaves get sections."""


@group(name="market", config_schema=MarketConfig)
def market():
    """Manage the fruit market."""


MARKET_SEED = dedent("""\
    ```{click:source}
    :hide-source:
    from tests.sphinx.test_sphinx_click_config import market
    ```
""")
"""Seed block importing the module-level CLI into the runner namespace."""


def _plain_text(html: str) -> str:
    """Strip tags and decode entities, so assertions survive Pygments tokenizing.

    A highlighted TOML block splits ``city = "Lisbon"`` across ``<span>``
    elements; matching on the tag-stripped text keeps the assertions
    readable and independent of the lexer's token boundaries.
    """
    return unescape(re.sub(r"<[^>]+>", "", html))


def test_click_config_renders_table_and_sections(sphinx_app_myst):
    """The directive expands into a summary table + one section per option."""
    content = MARKET_SEED + dedent("""
        ```{click:config} market
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None

    # Summary table links every option to its natural heading anchor.
    assert 'href="#city"' in html
    assert 'href="#stalls"' in html
    assert 'href="#hand-basket-apples"' in html

    # The headings exist and carry the anchors the table points to.
    assert 'id="city"' in html
    assert 'id="hand-basket-apples"' in html

    # Docstring summaries surface in the table and the sections.
    assert "City where the market is held." in html
    assert "How many apples fit in the basket." in html

    # The docstring's later paragraphs render in the section body.
    assert "covered\nhall the rest of the year" in _plain_text(html)

    # Type and default lines are rendered with bold labels.
    text = _plain_text(html)
    assert 'Type: str | Default: "Lisbon"' in text
    assert "Type: int | Default: 3" in text

    # The parent table's own docstring is not rendered: leaves only.
    assert "Parent table docstring" not in html


def test_click_config_toml_examples(sphinx_app_myst):
    """Each option gets a TOML example pinned to its default value.

    The section header defaults to ``tool.{cli-name}``, matching how
    click-extra and its downstream CLIs read their section from
    ``pyproject.toml``.
    """
    content = MARKET_SEED + dedent("""
        ```{click:config} market
        ```
    """)
    text = _plain_text(sphinx_app_myst.build_document(content))
    assert "[tool.market]" in text
    assert 'city = "Lisbon"' in text
    assert 'stalls = ["fruits", "flowers"]' in text
    assert "hand-basket.apples = 3" in text


def test_click_config_section_override_and_suppress(sphinx_app_myst):
    """``:section:`` overrides the example header; an empty value drops it."""
    content = MARKET_SEED + dedent("""
        ```{click:config} market
        :section: fruit.stand
        ```
    """)
    text = _plain_text(sphinx_app_myst.build_document(content))
    assert "[fruit.stand]" in text
    assert "[tool.market]" not in text

    content = MARKET_SEED + dedent("""
        ```{click:config} market
        :section:
        ```
    """)
    text = _plain_text(sphinx_app_myst.build_document(content))
    assert 'city = "Lisbon"' in text
    assert "[tool.market]" not in text


def test_click_config_bare_schema_argument(sphinx_app_myst):
    """A dataclass argument documents the schema without any CLI wired.

    Without a CLI there is no name to derive the section header from, so the
    examples render bare assignments.
    """
    content = dedent("""
        ```{click:config} MarketConfig
        from tests.sphinx.test_sphinx_click_config import MarketConfig
        ```
    """)
    text = _plain_text(sphinx_app_myst.build_document(content))
    assert "City where the market is held." in text
    assert 'city = "Lisbon"' in text
    assert "[tool." not in text


def test_click_config_no_table_and_no_examples(sphinx_app_myst):
    """``:no-table:`` and ``:no-examples:`` drop their blocks."""
    content = MARKET_SEED + dedent("""
        ```{click:config} market
        :no-table:
        :no-examples:
        ```
    """)
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    # Sections are still emitted (each heading keeps its permalink anchor,
    # so absence is asserted on the table element, not on hrefs).
    assert "City where the market is held." in html
    # Summary table is gone: it was the only table on the page.
    assert "<table" not in html
    # Example blocks are gone.
    assert "[tool.market]" not in _plain_text(html)


def test_click_config_exec_defined_schema_lacks_docstrings(sphinx_app_myst):
    """A schema defined in an exec'd block renders without descriptions."""
    content = dedent("""
        ```{click:config} InlineConfig
        from dataclasses import dataclass

        @dataclass
        class InlineConfig:
            pears: int = 7
            \"\"\"Lost to exec.\"\"\"
        ```
    """)
    text = _plain_text(sphinx_app_myst.build_document(content))
    # Structure renders from the dataclass alone.
    assert "pears = 7" in text
    assert "Type: int | Default: 7" in text
    # The attribute docstring is unrecoverable without source.
    assert "Lost to exec" not in text


def test_click_config_errors_without_schema(sphinx_app_myst):
    """A CLI with no ``config_schema`` raises a clear directive error."""
    content = dedent("""
        ```{click:source}
        :hide-source:
        from click_extra import group

        @group(name="bare")
        def bare():
            pass
        ```

        ```{click:config} bare
        ```
    """)
    with pytest.raises(Exception, match="has no config_schema"):
        sphinx_app_myst.build_document(content)


def test_click_config_errors_on_non_schema(sphinx_app_myst):
    """Resolving the argument to a non-dataclass raises a clear error."""
    content = dedent("""
        ```{click:source}
        :hide-source:
        not_a_schema = 42
        ```

        ```{click:config} not_a_schema
        ```
    """)
    with pytest.raises(Exception, match="did not yield a dataclass schema"):
        sphinx_app_myst.build_document(content)


def test_click_config_errors_on_unknown_name(sphinx_app_myst):
    """An expression that can't be evaluated raises a clear directive error."""
    content = dedent("""
        ```{click:config} missing_schema
        ```
    """)
    with pytest.raises(Exception, match="failed to evaluate"):
        sphinx_app_myst.build_document(content)


def test_click_config_errors_in_rst(sphinx_app_rst):
    """``click:config`` raises a clear error when used in an rST document."""
    content = dedent("""
        .. click:config:: market
    """)
    with pytest.raises(Exception, match="MyST"):
        sphinx_app_rst.build_document(content)


def test_click_config_heading_offset_adapts_to_surrounding_section(sphinx_app_myst):
    """Nested inside an ``h2`` section, option headings render at ``h3``."""
    content = (
        dedent("""
        # Doc title

        ## Configuration

    """)
        + MARKET_SEED
        + dedent("""
        ```{click:config} market
        ```
    """)
    )
    html = sphinx_app_myst.build_document(content)
    assert html is not None
    assert re.search(r"<h3[^>]*>\s*<code[^>]*>\s*city", html) or "<h3>" in html
    assert 'id="city"' in html
