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


def _build_with_manpages(
    tmp_path: Path,
    manpages_config: list[dict[str, Any]],
    *,
    builder: str = "html",
) -> Path:
    """Build a tiny Sphinx project that declares ``click_extra_manpages``.

    Returns the build output directory so the caller can inspect the man
    pages emitted by the hook. Uses a CLI shipped with click-extra
    (``click_extra.cli:demo``) as the target, so no external project has
    to be importable for the test to run.
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
    (srcdir / "index.rst").write_text("Hi\n==\n\nstub.\n")

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
    # from there (``click-extra-man.1``, ``click-extra-colors.1``...).
    assert "click-extra.1" in names, names
    assert "click-extra-man.1" in names, names


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
    # Pick a known subcommand. ``man`` is part of the click-extra demo group.
    assert (target / "demo-man.1").is_file()


def test_manpages_hook_skips_non_html_builder(tmp_path):
    """Non-HTML builders (e.g. ``linkcheck``) must not emit man pages."""
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
    from click_extra.sphinx import manpages

    body = cleandoc(manpages.__doc__ or "")
    for key in ("script", "prog_name", "output_dir"):
        assert key in body, f"missing documentation for {key!r}"
