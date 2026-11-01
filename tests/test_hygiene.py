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
"""Conventions the whole code base follows, checked file by file."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
"""Root of the repository."""

PYTHON_FILES = tuple(
    sorted(
        path
        for folder in ("click_extra", "tests")
        for path in (ROOT / folder).rglob("*.py")
    )
)
"""Python sources of the package and its test suite."""


def codec_names(tree: ast.AST) -> list[tuple[int, str]]:
    """Each codec name an `encoding=` argument, `encode()` or `decode()` receives.

    :return: the line and the literal of every codec spelled as a string
        constant, in the order of the source.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        values = [
            keyword.value for keyword in node.keywords if keyword.arg == "encoding"
        ]
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"encode", "decode"}
            and node.args
        ):
            values.append(node.args[0])
        found.extend(
            (value.lineno, value.value)
            for value in values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    return sorted(found)


def test_codec_names_detected() -> None:
    """The scan sees every way the suite spells a codec name."""
    source = (
        'open(path, encoding="utf-8")\n'
        "text.encode('utf8')\n"
        'data.decode("UTF-8")\n'
        'subprocess.run(args, text=True, encoding="ascii")\n'
    )
    assert codec_names(ast.parse(source)) == [
        (1, "utf-8"),
        (2, "utf8"),
        (3, "UTF-8"),
        (4, "ascii"),
    ]


@pytest.mark.once
def test_utf8_spelled_uppercase() -> None:
    """Every UTF-8 codec name reads `UTF-8`, the one spelling of this code base.

    Python normalizes `utf-8`, `utf8` and `UTF-8` alike, so the difference carries
    no meaning, and a mixed code base only makes a reader stop to work that out.
    """
    wrong = [
        f"{path.relative_to(ROOT)}:{line}: {name!r}"
        for path in PYTHON_FILES
        for line, name in codec_names(ast.parse(path.read_text(encoding="UTF-8")))
        if name.replace("_", "-").lower() in {"utf-8", "utf8"} and name != "UTF-8"
    ]
    assert not wrong, "\n".join(wrong)
