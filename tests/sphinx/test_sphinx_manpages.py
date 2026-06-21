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
"""Tests for :mod:`click_extra.sphinx.manpages`."""

from __future__ import annotations

from inspect import cleandoc
from pathlib import Path
from typing import Any

import pytest
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from click_extra.sphinx import manpages

_HAS_RENDERER = manpages._find_renderer() is not None
"""``True`` if at least one roff → HTML renderer is on ``PATH`` and
actually produces output. Drives the ``skipif`` on tests that need the
HTML sibling to exist."""


def _build_with_manpages(
    tmp_path: Path,
    manpages_config: list[dict[str, Any]],
    *,
    builder: str = "html",
    index_body: str = "Hi\n==\n\nstub.\n",
) -> Path:
    """Build a tiny Sphinx project that declares ``click_extra_manpages``.

    Returns the build output directory so the caller can inspect the man
    pages emitted by the hook. Uses a CLI shipped with click-extra
    (``click_extra.cli:demo``) as the target, so no external project has
    to be importable for the test to run.

    ``index_body`` overrides the contents of ``index.rst`` for tests that
    exercise directives or roles inside the page.
    """
    srcdir = tmp_path / "source"
    outdir = tmp_path / "build"
    doctreedir = outdir / ".doctrees"
    srcdir.mkdir()
    outdir.mkdir()

    conf = {
        "master_doc": "index",
        "extensions": ["click_extra.sphinx"],
        "click_extra_manpages": manpages_config,
    }
    (srcdir / "conf.py").write_text(
        "\n".join(f"{key} = {value!r}" for key, value in conf.items())
    )
    (srcdir / "index.rst").write_text(index_body)

    with docutils_namespace():
        app = Sphinx(
            str(srcdir),
            str(srcdir),
            str(outdir),
            str(doctreedir),
            builder,
            verbosity=0,
            warning=None,
        )
        app.build()
    return outdir


def test_manpages_hook_writes_tree_into_outdir(tmp_path):
    """An entry with just ``script`` writes the whole tree under ``man/``."""
    outdir = _build_with_manpages(
        tmp_path,
        [{"script": "click_extra.cli:demo"}],
    )
    man_dir = outdir / "man"
    assert man_dir.is_dir(), f"missing {man_dir}"
    names = {p.name for p in man_dir.iterdir()}
    # The default prog_name falls back to the resolved Click command's own
    # ``name`` attribute. The ``demo`` group declares ``name="click-extra"``,
    # so the root page is ``click-extra.1`` and each subcommand hyphenates
    # from there (``click-extra-wrap.1``, ``click-extra-colors.1``...).
    assert "click-extra.1" in names, names
    assert "click-extra-wrap.1" in names, names


def test_manpages_hook_honors_prog_name_and_output_dir(tmp_path):
    """An entry can override both the basename and the subdirectory."""
    outdir = _build_with_manpages(
        tmp_path,
        [
            {
                "script": "click_extra.cli:demo",
                "prog_name": "demo",
                "output_dir": "share/man/man1",
            }
        ],
    )
    target = outdir / "share" / "man" / "man1"
    assert target.is_dir(), f"missing {target}"
    assert (target / "demo.1").is_file()
    # Pick a known subcommand. ``wrap`` is part of the click-extra demo group.
    assert (target / "demo-wrap.1").is_file()


def test_manpages_hook_skips_non_html_builder(tmp_path):
    """Non-HTML builders (like ``linkcheck``) must not emit man pages."""
    outdir = _build_with_manpages(
        tmp_path,
        [{"script": "click_extra.cli:demo"}],
        builder="linkcheck",
    )
    # The hook is gated on the builder name so nothing under outdir/man/
    # should have been created.
    assert not (outdir / "man").exists()


def test_manpages_hook_empty_config_is_noop(tmp_path):
    """An empty list leaves the build untouched."""
    outdir = _build_with_manpages(tmp_path, [])
    assert not (outdir / "man").exists()


def test_manpages_hook_skips_entry_without_script(tmp_path):
    """An entry missing ``script`` is skipped (logged as a warning) instead
    of aborting the build."""
    outdir = _build_with_manpages(
        tmp_path,
        [{"prog_name": "demo"}],
    )
    # No man pages produced (the entry was unusable), but the build still
    # finished and wrote the index page Sphinx normally writes.
    assert not (outdir / "man").exists()
    assert (outdir / "index.html").is_file()


def test_manpages_module_help_documents_config_shape():
    """The module docstring spells out every supported key.

    A safety net against silent removal: distributors and downstream
    projects depend on the docstring as the canonical reference, since
    it is what ``help(click_extra.sphinx.manpages)`` prints.
    """
    body = cleandoc(manpages.__doc__ or "")
    for key in ("script", "prog_name", "output_dir", "render_html"):
        assert key in body, f"missing documentation for {key!r}"


@pytest.mark.skipif(
    not _HAS_RENDERER,
    reason="needs mandoc or groff on PATH to render the HTML siblings",
)
def test_manpages_hook_emits_html_siblings(tmp_path):
    """When a renderer is available, every ``.1`` gets a ``.1.html`` next
    to it whose body carries the section headings from the source roff."""
    outdir = _build_with_manpages(
        tmp_path,
        [{"script": "click_extra.cli:demo"}],
    )
    man_dir = outdir / "man"
    root_roff = man_dir / "click-extra.1"
    root_html = man_dir / "click-extra.1.html"
    assert root_roff.is_file()
    assert root_html.is_file()
    body = root_html.read_text(encoding="utf-8")
    # mandoc emits per-section <h1> blocks; groff -Thtml emits <h2>. Either
    # way the section title appears verbatim in the page so a simple "in"
    # check is portable across renderers.
    assert "NAME" in body
    assert "SYNOPSIS" in body
    assert "OPTIONS" in body
    # Every subcommand page gets an HTML sibling too.
    assert (man_dir / "click-extra-wrap.1.html").is_file()


def test_manpages_hook_respects_render_html_opt_out(tmp_path):
    """``render_html=False`` skips the HTML pass even when a renderer is
    present, keeping the build to roff only."""
    outdir = _build_with_manpages(
        tmp_path,
        [{"script": "click_extra.cli:demo", "render_html": False}],
    )
    man_dir = outdir / "man"
    assert (man_dir / "click-extra.1").is_file()
    # No .html sibling, regardless of mandoc availability.
    assert not any(man_dir.glob("*.html"))


_INDEX_WITH_DIRECTIVE = """\
Hi
==

.. click-extra-manpages::
"""
"""``index.rst`` body that hosts a single bare ``click-extra-manpages``
directive call. Used by the directive tests to render the auto-generated
link list into ``index.html``."""


def test_manpages_directive_renders_one_link_per_command(tmp_path):
    """The directive emits a bullet list with one entry per (sub)command
    of every script declared in ``click_extra_manpages``."""
    outdir = _build_with_manpages(
        tmp_path,
        # render_html=False keeps the test independent of mandoc
        # availability: the directive points at the .html siblings
        # regardless of whether they were actually written.
        [{"script": "click_extra.cli:demo", "render_html": False}],
        index_body=_INDEX_WITH_DIRECTIVE,
    )
    body = (outdir / "index.html").read_text(encoding="utf-8")
    # One link per page the emit hook would have written: the root
    # command plus every visible subcommand.
    assert 'href="man/click-extra.1.html"' in body
    assert 'href="man/click-extra-wrap.1.html"' in body
    assert 'href="man/click-extra-prebake.1.html"' in body
    assert 'href="man/click-extra-prebake-all.1.html"' in body
    # The visible label uses the ``name(section)`` convention so it
    # reads naturally next to the short-help suffix.
    assert "click-extra(1)" in body
    assert "click-extra-wrap(1)" in body


def test_manpages_directive_is_noop_when_config_empty(tmp_path):
    """An empty config means no bullet list, no warning, build still
    finishes."""
    outdir = _build_with_manpages(
        tmp_path,
        [],
        index_body=_INDEX_WITH_DIRECTIVE,
    )
    body = (outdir / "index.html").read_text(encoding="utf-8")
    assert (outdir / "index.html").is_file()
    # No anchors pointing at man/* because the directive had nothing to
    # enumerate. The rest of index.html still renders.
    assert 'href="man/' not in body


def test_manpages_directive_renders_inline_literals_as_code(tmp_path):
    """Inline reST literals in a command's short_help land as <code>
    spans in the rendered index, not as raw backticks rendered like
    quotes."""
    outdir = _build_with_manpages(
        tmp_path,
        # The click-extra prebake-all subcommand has the short help
        # ``Pre-bake __version__ and all git fields in one pass.``,
        # which is what triggered the original bug report.
        [{"script": "click_extra.cli:demo", "render_html": False}],
        index_body=_INDEX_WITH_DIRECTIVE,
    )
    body = (outdir / "index.html").read_text(encoding="utf-8")
    # The literal token rendered as a <code> span. The raw markers (the
    # paired backticks) must not appear next to ``__version__`` in the
    # output.
    assert "<code" in body
    assert "__version__" in body
    assert "``__version__``" not in body
