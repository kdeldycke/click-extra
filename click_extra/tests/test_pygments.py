# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

import sys
from operator import itemgetter
from pathlib import Path
from typing import Dict

from boltons.strutils import camel2under
from boltons.typeutils import issubclass
from pygments.filter import Filter
from pygments.formatter import Formatter
from pygments.style import Style

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .. import pygments as extra_pygments
from ..pygments import collect_session_lexers

PROJECT_ROOT = Path(__file__).parent.parent.parent


def get_pyproject_section(*section_path: str) -> Dict[str, str]:
    toml_path = PROJECT_ROOT.joinpath("pyproject.toml").resolve()
    toml_config = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    section = toml_config
    for section_id in section_path:
        section = section[section_id]
    return section


def check_entry_points(entry_points: Dict[str, str], *section_path: str) -> None:
    entry_points = dict(sorted(entry_points.items(), key=itemgetter(0)))
    project_entry_points = get_pyproject_section(*section_path)
    assert project_entry_points == entry_points


def test_registered_lexers():
    entry_points = {}
    for lexer in collect_session_lexers():

        # Check an ANSI lexer variant is available for import from Click Extra.
        ansi_lexer_id = f"Ansi{lexer.__name__}"
        assert ansi_lexer_id in extra_pygments.__dict__

        # Transform ANSI lexer class ID into entry point ID.
        entry_id = "-".join(
            w for w in camel2under(ansi_lexer_id).split("_") if w != "lexer"
        )

        # Generate the lexer entry point.
        class_path = f"click_extra.pygments:{ansi_lexer_id}"
        entry_points[entry_id] = class_path

    check_entry_points(entry_points, "tool", "poetry", "plugins", "pygments.lexers")


def collect_class_names(klass, prefix="Ansi"):
    """Returns the name of all classes defined in ``click_extra.pygments`` that are a
    subclass of ``klass``, and whose name starts with the provided ``prefix``."""
    for name, var in extra_pygments.__dict__.items():
        if issubclass(var, klass) and name.startswith(prefix):
            yield name


def test_registered_filters():
    entry_points = {}
    for name in collect_class_names(Filter):
        entry_id = camel2under(name).replace("_", "-")
        entry_points[entry_id] = f"click_extra.pygments:{name}"

    check_entry_points(entry_points, "tool", "poetry", "plugins", "pygments.filters")


def test_registered_formatters():
    entry_points = {}
    for name in collect_class_names(Formatter):
        entry_id = camel2under(name).replace("_", "-")
        entry_points[entry_id] = f"click_extra.pygments:{name}"

    check_entry_points(entry_points, "tool", "poetry", "plugins", "pygments.formatters")


def test_registered_styles():
    entry_points = {}
    for name in collect_class_names(Style):
        entry_id = camel2under(name).replace("_", "-")
        entry_points[entry_id] = f"click_extra.pygments:{name}"

    check_entry_points(entry_points, "tool", "poetry", "plugins", "pygments.styles")


def test_ansi_lexers_doc():
    doc_content = PROJECT_ROOT.joinpath("docs/pygments.md").read_text()
    for lexer in collect_session_lexers():
        assert lexer.__name__ in doc_content
