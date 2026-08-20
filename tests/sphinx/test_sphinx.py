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
"""Fixtures and utilities for Sphinx testing."""

from __future__ import annotations

import subprocess
import sys
from textwrap import dedent

import pytest

# Import click_extra.sphinx with myst_parser blocked, to check the module does not
# hard-depend on it. Runs in a subprocess: a meta-path blocker installed in-process
# would leak into every later test of the session.
NO_MYST_PARSER_SCRIPT = dedent("""
    import sys
    from importlib.abc import MetaPathFinder

    class MystParserBlocker(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.partition(".")[0] == "myst_parser":
                raise ImportError("myst-parser is not installed")
            return None

    sys.meta_path.insert(0, MystParserBlocker())

    import click_extra.sphinx

    assert click_extra.sphinx.myst_parser is None
""")


@pytest.mark.once
def test_import_without_myst_parser():
    """The extension imports for a reST-only project, which installs no myst-parser.

    The `sphinx` extra does not declare `myst-parser` and Sphinx does not depend on
    it, so a hard import of it in `click_extra.sphinx` breaks such a project outright.
    """
    result = subprocess.run(
        (sys.executable, "-c", NO_MYST_PARSER_SCRIPT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_sphinx_extension_setup(sphinx_app):
    """Test that the Sphinx extension is properly loaded."""
    # Check that the domain is registered.
    assert "click" in sphinx_app.registry.domains
    assert "click" in sphinx_app.env.domains

    # Check that our directives are registered.
    assert "source" in sphinx_app.env.get_domain("click").directives
    assert "run" in sphinx_app.env.get_domain("click").directives
    assert "tree" in sphinx_app.env.get_domain("click").directives


def test_resolve_any_xref(sphinx_app):
    """Test that ``resolve_any_xref`` is implemented and returns an empty list.

    .. seealso:: https://github.com/kdeldycke/click-extra/issues/1502
    """
    domain = sphinx_app.env.get_domain("click")
    result = domain.resolve_any_xref(
        env=sphinx_app.env,
        fromdocname="index",
        builder=sphinx_app.builder,
        target="anything",
        node=None,
        contnode=None,
    )
    assert result == []
