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

import ast
import subprocess
import sys
from pathlib import Path
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


def imports_sphinx_package(node: ast.Import | ast.ImportFrom) -> bool:
    """Whether an import statement reaches `click_extra.sphinx` or a module of it."""
    if isinstance(node, ast.ImportFrom):
        names = [f"{node.module}.{alias.name}" for alias in node.names]
    else:
        names = [alias.name for alias in node.names]
    return any(name.split(".")[:2] == ["click_extra", "sphinx"] for name in names)


def is_sphinx_guard(call: ast.Call) -> bool:
    """Whether the call is `pytest.importorskip("sphinx", ...)`."""
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "importorskip"
        and bool(call.args)
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == "sphinx"
    )


def unguarded_sphinx_imports(tree: ast.Module) -> list[int]:
    """Lines importing `click_extra.sphinx` that no `importorskip("sphinx")` precedes.

    A guard covers the rest of the function it is called in, or the whole module
    when called at its top level.
    """
    guards: dict[ast.AST | None, int] = {}
    imports: list[tuple[ast.AST | None, int]] = []

    def visit(node: ast.AST, scope: ast.AST | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call) and is_sphinx_guard(child):
                guards.setdefault(scope, child.lineno)
            elif isinstance(child, (ast.Import, ast.ImportFrom)) and (
                imports_sphinx_package(child)
            ):
                imports.append((scope, child.lineno))
            function = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            visit(child, child if function else scope)

    visit(tree, None)
    return [
        line
        for scope, line in imports
        if not any(guards.get(owner, line) < line for owner in (None, scope))
    ]


@pytest.mark.once
def test_imports_outside_this_tree_skip_without_sphinx():
    """Outside `tests/sphinx/`, a test skips itself before importing the extension.

    The `collect_ignore_glob` of this tree skips it on a builder shipping no
    Sphinx, and covers no test outside it. Such a test has to call
    `pytest.importorskip("sphinx")` before it imports `click_extra.sphinx`, or it
    fails on that builder instead of skipping.
    """
    tests_root = Path(__file__).parent.parent
    offenders = [
        f"{path.relative_to(tests_root)}:{line}"
        for path in sorted(tests_root.rglob("*.py"))
        if tests_root / "sphinx" not in path.parents
        for line in unguarded_sphinx_imports(
            ast.parse(path.read_text(encoding="utf-8"))
        )
    ]
    assert not offenders, f"unguarded click_extra.sphinx imports: {offenders}"


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
