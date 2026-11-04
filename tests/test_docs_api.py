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

"""Every public module is indexed on the API page of its package.

`sphinx-apidoc` writes the API pages: `docs/click_extra.md` and one page per
subpackage, plus the same set for `tests`. It writes each page once. A later
run keeps the page already in place, as
{func}`click_extra.markdown.myst.convert_rst_files_in_directory` does, so a
module added afterwards never reaches its API page. Its only `automodule` block
then tends to land on a guide page, and the build accepts that without a
warning.

So the API page owns the index entry of each module, and every guide-page block
carries `:no-index:`. This test reads the source trees and the API pages as
text, and fails naming each public module that no API page indexes. The check
imports nothing, so it needs none of the optional dependencies a module pulls
in.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent

# The packages `sphinx-apidoc` documents. The API pages of each one are named
# after it: `click_extra.md`, `click_extra.config.md`, `tests.sphinx.md`.
DOCUMENTED_PACKAGES = ("click_extra", "tests")

# Deprecated aliases of a moved module. They document nothing of their own, so
# they get no API page section.
DEPRECATION_SHIMS = frozenset({"click_extra.blocks"})

# An `automodule` directive inside an `{eval-rst}` fence, and an option line
# below it. The API pages carry them at the margin.
AUTOMODULE = re.compile(r"^\.\. automodule:: (?P<module>\S+)\s*$")
OPTION = re.compile(r"^\s+:[\w-]+:")


def public_modules(package: str) -> list[str]:
    """Name every public module of `package`, read from its source tree.

    A name with an underscore-prefixed part is private, and so is everything
    below it: `click_extra._utils`, `click_extra.sphinx._base` and
    `click_extra.__main__` are all skipped. A package is named by its
    `__init__.py`.
    """
    modules = []
    for path in sorted((PROJECT_ROOT / package).rglob("*.py")):
        parts = path.relative_to(PROJECT_ROOT).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not any(part.startswith("_") for part in parts):
            modules.append(".".join(parts))
    return modules


def api_pages(package: str) -> list[Path]:
    """Return the API pages of `package`, in the documentation tree."""
    return sorted((PROJECT_ROOT / "docs").glob(f"{package}*.md"))


def indexed_modules(pages: list[Path]) -> set[str]:
    """Collect each module an `automodule` directive indexes on `pages`.

    A block carrying `:no-index:` registers no index entry, so it does not count.
    """
    modules = set()
    for page in pages:
        lines = page.read_text(encoding="UTF-8").splitlines()
        for number, line in enumerate(lines):
            directive = AUTOMODULE.match(line)
            if not directive:
                continue
            options = itertools.takewhile(OPTION.match, lines[number + 1 :])
            if ":no-index:" not in (option.strip() for option in options):
                modules.add(directive.group("module"))
    return modules


@pytest.mark.parametrize("package", DOCUMENTED_PACKAGES)
def test_package_is_collected(package):
    """The globs feeding the check still find the modules and their API pages."""
    assert len(public_modules(package)) > 20, f"{package} modules went missing"
    assert api_pages(package), f"{package} API pages went missing"


def test_deprecation_shims_still_exist():
    """An exemption goes in the same change that deletes its shim."""
    stale = sorted(DEPRECATION_SHIMS.difference(public_modules("click_extra")))
    assert not stale, f"exempted shims are gone: {', '.join(stale)}"


@pytest.mark.parametrize("package", DOCUMENTED_PACKAGES)
def test_every_module_is_indexed_on_an_api_page(package):
    """No public module is left to a guide page, or to no page at all.

    A failure names a module that no API page indexes. Add its section to the
    API page of its package, in alphabetical order with the others, and give
    any guide-page block of the same module `:no-index:`.
    """
    indexed = indexed_modules(api_pages(package))
    missing = [
        module
        for module in public_modules(package)
        if module not in indexed and module not in DEPRECATION_SHIMS
    ]
    assert not missing, (
        "These modules have no indexed automodule on an API page:\n  "
        + "\n  ".join(missing)
    )


def test_indexed_modules(tmp_path):
    """A `:no-index:` block counts for nothing, wherever its option sits."""
    page = tmp_path / "orchard.md"
    page.write_text(
        "# Orchard\n"
        "\n"
        "```{eval-rst}\n"
        ".. automodule:: orchard.apples\n"
        "   :members:\n"
        "\n"
        ".. automodule:: orchard.pears\n"
        "   :members:\n"
        "   :no-index:\n"
        "\n"
        ".. automodule:: orchard.plums\n"
        "```\n",
        encoding="UTF-8",
    )
    assert indexed_modules([page]) == {"orchard.apples", "orchard.plums"}
