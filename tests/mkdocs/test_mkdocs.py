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

import os
from textwrap import dedent

import click
import pytest
from pygments.formatters.html import HtmlFormatter

from click_extra.mkdocs import (
    ANSI_OUTPUT_FENCE,
    ANSI_STYLESHEET,
    TEXT_FENCE,
    AnsiColorPlugin,
    _ansi_stylesheet,
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
    plugin.on_config({"extra_css": []})  # type: ignore[arg-type]

    assert issubclass(pymdownx.highlight.BlockHtmlFormatter, AnsiHtmlFormatter)
    assert issubclass(pymdownx.highlight.InlineHtmlFormatter, AnsiHtmlFormatter)


@pytest.mark.usefixtures("_clean_pymdownx", "_clean_mkdocs_click")
def test_on_config_idempotent():
    """Calling ``on_config`` twice does not create a new class each time."""
    import pymdownx.highlight

    plugin = AnsiColorPlugin()
    plugin.on_config({"extra_css": []})  # type: ignore[arg-type]
    block_cls = pymdownx.highlight.BlockHtmlFormatter
    inline_cls = pymdownx.highlight.InlineHtmlFormatter

    plugin.on_config({"extra_css": []})  # type: ignore[arg-type]
    assert pymdownx.highlight.BlockHtmlFormatter is block_cls
    assert pymdownx.highlight.InlineHtmlFormatter is inline_cls


@pytest.mark.usefixtures("_clean_pymdownx", "_clean_mkdocs_click")
def test_patched_formatter_preserves_pymdownx_mro():
    """The patched formatters still inherit from the original pymdownx classes."""
    import pymdownx.highlight

    orig_block = pymdownx.highlight.BlockHtmlFormatter
    orig_inline = pymdownx.highlight.InlineHtmlFormatter

    plugin = AnsiColorPlugin()
    plugin.on_config({"extra_css": []})  # type: ignore[arg-type]

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
    plugin.on_config({"extra_css": []})  # type: ignore[arg-type]

    formatter = pymdownx.highlight.BlockHtmlFormatter(style="default")
    # AnsiHtmlFormatter augments the style with ANSI token definitions.
    style_defs = formatter.get_style_defs(".highlight")
    assert ".-Ansi-Red" in style_defs
    assert ".-Ansi-Bold" in style_defs


def test_ansi_stylesheet_only_contains_ansi_rules():
    """The generated stylesheet colors the ``-Ansi-*`` classes and nothing else.

    Standard Pygments token rules must stay out: dumping the full style would
    override the theme's own syntax-highlighting colors for every code block.
    """
    css = _ansi_stylesheet()
    # The classes emitted for typical colored CLI output are covered.
    assert ".highlight .-Ansi-Cyan { color:" in css
    assert ".highlight .-Ansi-Bold { font-weight: bold }" in css
    # SGR attributes, blink keyframes and the OSC 8 hyperlink rule are included.
    assert "@keyframes ansi-blink" in css
    assert ".highlight a { color: inherit" in css
    # Every rule is ANSI-specific: no standard token (.k, .s, .c, ...) leaks in.
    for line in filter(None, css.splitlines()):
        assert (
            "-Ansi" in line or "ansi-blink" in line or "a { color: inherit" in line
        ), line


@pytest.mark.usefixtures("_clean_pymdownx", "_clean_mkdocs_click")
def test_on_config_registers_stylesheet():
    """``on_config`` appends the ANSI stylesheet to ``extra_css`` exactly once."""
    config: dict[str, list[str]] = {"extra_css": []}
    plugin = AnsiColorPlugin()

    plugin.on_config(config)  # type: ignore[arg-type]
    assert config["extra_css"] == [ANSI_STYLESHEET]

    # Idempotent: a second pass does not duplicate the entry.
    plugin.on_config(config)  # type: ignore[arg-type]
    assert config["extra_css"] == [ANSI_STYLESHEET]


def test_on_post_build_writes_stylesheet(tmp_path):
    """``on_post_build`` writes the ANSI stylesheet under the site directory."""
    config = {"site_dir": str(tmp_path)}
    AnsiColorPlugin().on_post_build(config)  # type: ignore[arg-type]

    written = tmp_path / ANSI_STYLESHEET
    assert written.is_file()
    assert ".highlight .-Ansi-Cyan" in written.read_text(encoding="utf-8")


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


@pytest.mark.usefixtures("_clean_mkdocs_click")
def test_patch_mkdocs_click_forces_color_during_capture(monkeypatch):
    """The patched generators capture help with color forced, even under ``NO_COLOR``.

    Swapping the lexer to ``ansi-output`` is pointless if the captured help carries no
    escape codes, which is exactly what happens when the build's stdout is a pipe. The
    wrapper must therefore materialize the help *while* the color override is active.
    Spying on ``make_formatter`` (where Rich and Click read the environment to decide on
    color) proves ``FORCE_COLOR`` is set and the disabling vars are cleared at capture
    time, and that the surrounding environment is restored once the capture completes.
    """
    from mkdocs_click import _docs

    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    seen = {}
    real_make_formatter = click.Context.make_formatter

    def spy_make_formatter(self):
        seen.setdefault("FORCE_COLOR", os.environ.get("FORCE_COLOR"))
        seen.setdefault("NO_COLOR", os.environ.get("NO_COLOR"))
        return real_make_formatter(self)

    monkeypatch.setattr(click.Context, "make_formatter", spy_make_formatter)

    _patch_mkdocs_click()
    ctx = click.Context(_hello_cmd, info_name="hello")
    list(_docs._make_usage(ctx))

    # FORCE_COLOR was set (and NO_COLOR cleared) while the formatter was built...
    assert seen["FORCE_COLOR"] == "1"
    assert seen["NO_COLOR"] is None
    # ...and the build environment is restored once the capture completes.
    assert os.environ.get("FORCE_COLOR") is None
    assert os.environ["NO_COLOR"] == "1"


@pytest.mark.usefixtures("_clean_pymdownx", "_clean_mkdocs_click")
def test_on_config_patches_mkdocs_click():
    """``on_config`` patches mkdocs-click alongside pymdownx.highlight."""
    from mkdocs_click import _docs

    assert not getattr(_docs, "_click_extra_patched", False)

    plugin = AnsiColorPlugin()
    plugin.on_config({"extra_css": []})  # type: ignore[arg-type]

    assert _docs._click_extra_patched is True  # type: ignore[attr-defined]
    ctx = click.Context(_hello_cmd, info_name="hello")
    lines = list(_docs._make_usage(ctx))
    assert ANSI_OUTPUT_FENCE in lines


@pytest.mark.once
@pytest.mark.usefixtures("_clean_pymdownx", "_clean_mkdocs_click")
def test_full_build_renders_ansi_colors(tmp_path):
    """An end-to-end MkDocs build strips escape codes and ships the color stylesheet.

    This exercises the whole plugin wiring (formatter patch plus stylesheet
    injection) the way bump-my-version's site does: an ``ansi-output`` block goes
    in, and class-decorated spans backed by a linked stylesheet come out, with no
    raw escape codes left behind.
    """
    from mkdocs.commands.build import build
    from mkdocs.config import load_config

    esc = "\x1b"
    ansi = f"{esc}[1mgreet{esc}[0m [{esc}[1;36mOPTIONS{esc}[0m]"
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text(
        f"# CLI\n\n```ansi-output\n{ansi}\n```\n",
        encoding="utf-8",
    )
    config_file = tmp_path / "mkdocs.yml"
    config_file.write_text(
        dedent("""\
            site_name: ANSI build test
            markdown_extensions:
              - pymdownx.highlight
              - pymdownx.superfences
            plugins:
              - search
              - click-extra
            """),
        encoding="utf-8",
    )
    site = tmp_path / "site"

    build(load_config(str(config_file), site_dir=str(site)))

    # The color stylesheet is generated and contains the cyan rule used above.
    stylesheet = site / ANSI_STYLESHEET
    assert stylesheet.is_file()
    assert ".highlight .-Ansi-Cyan { color:" in stylesheet.read_text(encoding="utf-8")

    index = (site / "index.html").read_text(encoding="utf-8")
    # The page links the stylesheet, carries the decomposed class, and no longer
    # contains any raw escape byte.
    assert ANSI_STYLESHEET in index
    assert "-Ansi-Cyan" in index
    assert esc not in index
