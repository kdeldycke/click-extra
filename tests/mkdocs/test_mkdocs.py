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
"""Tests for the MkDocs ANSI color plugin."""

from __future__ import annotations

import click
import pytest
from pygments.formatters.html import HtmlFormatter

from click_extra.mkdocs import (
    ANSI_OUTPUT_FENCE,
    TEXT_FENCE,
    AnsiColorPlugin,
    _patch_mkdocs_click,
)
from click_extra.pygments import AnsiHtmlFormatter


@pytest.fixture()
def _clean_pymdownx():
    """Save and restore pymdownx.highlight formatter classes around each test."""
    import pymdownx.highlight

    orig_block = pymdownx.highlight.BlockHtmlFormatter
    orig_inline = pymdownx.highlight.InlineHtmlFormatter
    yield
    pymdownx.highlight.BlockHtmlFormatter = orig_block
    pymdownx.highlight.InlineHtmlFormatter = orig_inline


@pytest.fixture()
def _clean_mkdocs_click():
    """Save and restore mkdocs-click functions around each test."""
    from mkdocs_click import _docs

    orig_usage = _docs._make_usage
    orig_plain = _docs._make_plain_options
    orig_patched = getattr(_docs, "_click_extra_patched", False)
    yield
    _docs._make_usage = orig_usage
    _docs._make_plain_options = orig_plain
    _docs._click_extra_patched = orig_patched  # type: ignore[attr-defined]


@pytest.mark.once
def test_mkdocs_entry_point():
    """Verify the ``mkdocs.plugins`` entry point is declared in ``pyproject.toml``."""
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib  # type: ignore[import-not-found]

    from pathlib import Path

    toml_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    config = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    ep = config["project"]["entry-points"]["mkdocs.plugins"]
    assert ep == {"click-extra": "click_extra.mkdocs:AnsiColorPlugin"}


@pytest.mark.usefixtures("_clean_pymdownx", "_clean_mkdocs_click")
def test_on_config_patches_formatters():
    """After ``on_config``, both formatter classes inherit from ``AnsiHtmlFormatter``."""
    import pymdownx.highlight

    # Before patching: standard HtmlFormatter subclasses.
    assert not issubclass(pymdownx.highlight.BlockHtmlFormatter, AnsiHtmlFormatter)
    assert not issubclass(pymdownx.highlight.InlineHtmlFormatter, AnsiHtmlFormatter)

    plugin = AnsiColorPlugin()
    plugin.on_config({})  # type: ignore[arg-type]

    assert issubclass(pymdownx.highlight.BlockHtmlFormatter, AnsiHtmlFormatter)
    assert issubclass(pymdownx.highlight.InlineHtmlFormatter, AnsiHtmlFormatter)


@pytest.mark.usefixtures("_clean_pymdownx", "_clean_mkdocs_click")
def test_on_config_idempotent():
    """Calling ``on_config`` twice does not create a new class each time."""
    import pymdownx.highlight

    plugin = AnsiColorPlugin()
    plugin.on_config({})  # type: ignore[arg-type]
    block_cls = pymdownx.highlight.BlockHtmlFormatter
    inline_cls = pymdownx.highlight.InlineHtmlFormatter

    plugin.on_config({})  # type: ignore[arg-type]
    assert pymdownx.highlight.BlockHtmlFormatter is block_cls
    assert pymdownx.highlight.InlineHtmlFormatter is inline_cls


@pytest.mark.usefixtures("_clean_pymdownx", "_clean_mkdocs_click")
def test_patched_formatter_preserves_pymdownx_mro():
    """The patched formatters still inherit from the original pymdownx classes."""
    import pymdownx.highlight

    orig_block = pymdownx.highlight.BlockHtmlFormatter
    orig_inline = pymdownx.highlight.InlineHtmlFormatter

    plugin = AnsiColorPlugin()
    plugin.on_config({})  # type: ignore[arg-type]

    assert issubclass(pymdownx.highlight.BlockHtmlFormatter, orig_block)
    assert issubclass(pymdownx.highlight.InlineHtmlFormatter, orig_inline)
    # Both must still descend from Pygments' HtmlFormatter.
    assert issubclass(pymdownx.highlight.BlockHtmlFormatter, HtmlFormatter)
    assert issubclass(pymdownx.highlight.InlineHtmlFormatter, HtmlFormatter)


@pytest.mark.usefixtures("_clean_pymdownx", "_clean_mkdocs_click")
def test_patched_formatter_renders_ansi():
    """The patched block formatter decomposes compound ANSI tokens into CSS classes."""
    import pymdownx.highlight

    plugin = AnsiColorPlugin()
    plugin.on_config({})  # type: ignore[arg-type]

    formatter = pymdownx.highlight.BlockHtmlFormatter(style="default")
    # AnsiHtmlFormatter augments the style with ANSI token definitions.
    style_defs = formatter.get_style_defs(".highlight")
    assert ".-Ansi-Red" in style_defs
    assert ".-Ansi-Bold" in style_defs


@click.command()
@click.option("--name", help="The person to greet.")
def _hello_cmd(name):
    """Greet someone."""


@pytest.mark.usefixtures("_clean_mkdocs_click")
def test_patch_mkdocs_click_usage():
    """After patching, ``_make_usage`` yields ``ansi-output`` fences."""
    from mkdocs_click import _docs

    ctx = click.Context(_hello_cmd, info_name="hello")
    lines_before = list(_docs._make_usage(ctx))
    assert TEXT_FENCE in lines_before
    assert ANSI_OUTPUT_FENCE not in lines_before

    _patch_mkdocs_click()

    lines_after = list(_docs._make_usage(ctx))
    assert ANSI_OUTPUT_FENCE in lines_after
    assert TEXT_FENCE not in lines_after


@pytest.mark.usefixtures("_clean_mkdocs_click")
def test_patch_mkdocs_click_plain_options():
    """After patching, ``_make_plain_options`` yields ``ansi-output`` fences."""
    from mkdocs_click import _docs

    ctx = click.Context(_hello_cmd, info_name="hello")
    lines_before = list(_docs._make_plain_options(ctx))
    assert TEXT_FENCE in lines_before
    assert ANSI_OUTPUT_FENCE not in lines_before

    _patch_mkdocs_click()

    lines_after = list(_docs._make_plain_options(ctx))
    assert ANSI_OUTPUT_FENCE in lines_after
    assert TEXT_FENCE not in lines_after


@pytest.mark.usefixtures("_clean_mkdocs_click")
def test_patch_mkdocs_click_idempotent():
    """Calling ``_patch_mkdocs_click`` twice does not double-wrap."""
    from mkdocs_click import _docs

    _patch_mkdocs_click()
    usage_fn = _docs._make_usage
    plain_fn = _docs._make_plain_options

    _patch_mkdocs_click()
    assert _docs._make_usage is usage_fn
    assert _docs._make_plain_options is plain_fn


@pytest.mark.usefixtures("_clean_pymdownx", "_clean_mkdocs_click")
def test_on_config_patches_mkdocs_click():
    """``on_config`` patches mkdocs-click alongside pymdownx.highlight."""
    from mkdocs_click import _docs

    assert not getattr(_docs, "_click_extra_patched", False)

    plugin = AnsiColorPlugin()
    plugin.on_config({})  # type: ignore[arg-type]

    assert _docs._click_extra_patched is True  # type: ignore[attr-defined]
    ctx = click.Context(_hello_cmd, info_name="hello")
    lines = list(_docs._make_usage(ctx))
    assert ANSI_OUTPUT_FENCE in lines
