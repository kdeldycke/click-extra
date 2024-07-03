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

from __future__ import annotations

import sys
import tarfile
from importlib import metadata
from operator import itemgetter
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

import requests
from boltons.strutils import camel2under
from boltons.typeutils import issubclass
from pygments.filter import Filter
from pygments.filters import get_filter_by_name
from pygments.formatter import Formatter
from pygments.formatters import get_formatter_by_name
from pygments.lexer import Lexer
from pygments.lexers import find_lexer_class_by_name, get_lexer_by_name

from click_extra import pygments as extra_pygments
from click_extra.pygments import DEFAULT_TOKEN_TYPE, collect_session_lexers

PROJECT_ROOT = Path(__file__).parent.parent


def is_relative_to(path: Path, *other: Path) -> bool:
    """Return `True` if the path is relative to another path or `False`.

    This is a backport of `pathlib.Path.is_relative_to` from Python 3.9.
    """
    try:
        path.relative_to(*other)
        return True
    except ValueError:
        return False


def test_ansi_lexers_candidates(tmp_path):
    """Look into Pygments test suite to find all ANSI lexers candidates.

    Good candidates for ANSI colorization are lexers that are producing
    ``Generic.Output`` tokens, which are often used by REPL-like and scripting
    terminal to render text in a console.

    The list is manually maintained in Click Extra code, and this test is here to
    detect new candidates from new releases of Pygments.

    .. attention::
        The Pygments source code is downloaded from GitHub in the form of an archive,
        and extracted in a temporary folder.

        The version of Pygments used for this test is the one installed in the current
        environment.

    .. danger:: Security check
        While extracting the archive, we double check we are not fed an archive
        exploiting relative ``..`` or ``.`` path attacks.
    """
    version = metadata.version("pygments")

    source_url = (
        f"https://github.com/pygments/pygments/archive/refs/tags/{version}.tar.gz"
    )
    base_folder = f"pygments-{version}"
    archive_path = tmp_path / f"{base_folder}.tar.gz"

    # Download the source distribution from GitHub.
    with requests.get(source_url) as response:
        assert response.ok
        archive_path.write_bytes(response.content)

    assert archive_path.exists()
    assert archive_path.is_file()
    assert archive_path.stat().st_size > 0

    # Locations of lexer artifacts in test suite.
    parser_token_traces = {
        str(tmp_path / base_folder / "tests" / "examplefiles" / "*" / "*.output"),
        str(tmp_path / base_folder / "tests" / "snippets" / "*" / "*.txt"),
    }

    # Browse the downloaded package to find the test suite, and inspect the
    # traces of parsed tokens used as gold master for lexers tests.
    lexer_candidates = set()
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            # Skip non-test files.
            if not member.isfile():
                continue

            # XXX Security check of relative ``..`` or ``.`` path attacks.
            filename = tmp_path.joinpath(member.name).resolve()
            if sys.version_info >= (3, 9):
                assert filename.is_relative_to(tmp_path)
            else:
                assert is_relative_to(filename, tmp_path)

            # Skip files that are not part of the test suite data.
            match = False
            for pattern in parser_token_traces:
                if filename.match(pattern):
                    match = True
                    break
            if not match:
                continue

            file = tar.extractfile(member)
            # Skip empty files.
            if not file:
                continue

            content = file.read().decode("utf-8")

            # Skip lexers that are rendering generic, terminal-like output tokens.
            if f" {'.'.join(DEFAULT_TOKEN_TYPE)}\n" not in content:
                continue

            # Extarct lexer alias from the test file path.
            lexer_candidates.add(filename.parent.name)

    assert lexer_candidates
    lexer_classes = {find_lexer_class_by_name(alias) for alias in lexer_candidates}
    # We cannot test for strict equality yet, as some ANSI-ready lexers do not
    # have any test artifacts producing ``Generic.Output`` tokens.
    assert lexer_classes <= set(collect_session_lexers())


def collect_classes(klass, prefix="Ansi"):
    """Returns all classes defined in ``click_extra.pygments`` that are a subclass of
    ``klass``, and whose name starts with the provided ``prefix``."""
    klasses = {}
    for name, var in extra_pygments.__dict__.items():
        if issubclass(var, klass) and name.startswith(prefix):
            klasses[name] = var
    return klasses


def get_pyproject_section(*section_path: str) -> dict[str, str]:
    """Descends into the TOML tree of ``pyproject.toml`` to reach the value specified by
    ``section_path``."""
    toml_path = PROJECT_ROOT.joinpath("pyproject.toml").resolve()
    section: dict = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    for section_id in section_path:
        section = section[section_id]
    return section


def check_entry_points(entry_points: dict[str, str], *section_path: str) -> None:
    entry_points = dict(sorted(entry_points.items(), key=itemgetter(0)))
    project_entry_points = get_pyproject_section(*section_path)
    assert project_entry_points == entry_points


def test_formatter_entry_points():
    entry_points = {}
    for name in collect_classes(Formatter):
        entry_id = camel2under(name).replace("_", "-")
        entry_points[entry_id] = f"click_extra.pygments:{name}"

    check_entry_points(entry_points, "project", "entry-points", "pygments.formatters")


def test_filter_entry_points():
    entry_points = {}
    for name in collect_classes(Filter):
        entry_id = camel2under(name).replace("_", "-")
        entry_points[entry_id] = f"click_extra.pygments:{name}"

    check_entry_points(entry_points, "project", "entry-points", "pygments.filters")


def test_lexer_entry_points():
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

    check_entry_points(entry_points, "project", "entry-points", "pygments.lexers")


def test_registered_formatters():
    for klass in collect_classes(Formatter).values():
        for alias in klass.aliases:
            get_formatter_by_name(alias)


def test_registered_filters():
    for name in collect_classes(Filter):
        entry_id = camel2under(name).replace("_", "-")
        get_filter_by_name(entry_id)


def test_registered_lexers():
    for klass in collect_classes(Lexer).values():
        for alias in klass.aliases:
            get_lexer_by_name(alias)


def test_ansi_lexers_doc():
    doc_content = PROJECT_ROOT.joinpath("docs/pygments.md").read_text()
    for lexer in collect_session_lexers():
        assert lexer.__name__ in doc_content
