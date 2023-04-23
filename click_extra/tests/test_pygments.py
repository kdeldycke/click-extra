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
from operator import itemgetter
from pathlib import Path
from importlib import metadata

from boltons.strutils import camel2under
from boltons.typeutils import issubclass
from pip._internal.cli.status_codes import SUCCESS
from pip._internal.commands.download import DownloadCommand
from pip._internal.utils.temp_dir import global_tempdir_manager, tempdir_registry
from pygments.filter import Filter
from pygments.formatter import Formatter
from pygments.lexers import find_lexer_class_by_name
from pygments.style import Style

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import]

from .. import pygments as extra_pygments
from ..pygments import DEFAULT_TOKEN_TYPE, collect_session_lexers

PROJECT_ROOT = Path(__file__).parent.parent.parent


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
    detect new candidates from Pygments new releases.
    """
    # Get the version of the Pygments package installed in the current environment.
    version = metadata.version("pygments")

    # Emulate CLI call to download Pygments' source distribution (which contains the
    # full test suite and data) from PyPi via pip:
    #   $ pip download --no-binary=:all: --no-deps pygments==2.14.0
    # Source: https://stackoverflow.com/a/56773693
    cmd = DownloadCommand(name="dummy_name", summary="dummy_summary")

    # Inspired by pip._internal.cli.base_command.Command._main(). See:
    # https://github.com/pypa/pip/blob/ba38c33b6b4fc3ee22dabb747a4b4ccff0a87d22/src/pip/_internal/cli/base_command.py#L105-L114
    with cmd.main_context():
        cmd.tempdir_registry = cmd.enter_context(tempdir_registry())
        cmd.enter_context(global_tempdir_manager())
        options, args = cmd.parse_args(
            [
                "--no-binary=:all:",
                "--no-deps",
                "--dest",
                f"{tmp_path}",
                f"pygments=={version}",
            ]
        )
        cmd.verbosity = options.verbose
        outcome = cmd.run(options, args)
        assert outcome == SUCCESS

    base_folder = f"Pygments-{version}"
    package_path = tmp_path.joinpath(f"{base_folder}.tar.gz")
    assert package_path.exists()
    assert package_path.is_file()

    # Locations of lexer artifacts in test suite.
    parser_token_traces = {
        str(tmp_path / base_folder / "tests" / "examplefiles" / "*" / "*.output"),
        str(tmp_path / base_folder / "tests" / "snippets" / "*" / "*.txt"),
    }

    # Browse the downloaded package to find the test suite, and inspect the
    # traces of parsed tokens used as gold master for lexers tests.
    lexer_candidates = set()
    with tarfile.open(package_path, "r:gz") as tar:
        for member in tar.getmembers():
            # Skip non-test files.
            if not member.isfile():
                continue

            # Double check we are not fed an archive exploiting relative ``..`` or
            # ``.`` path attacks.
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

    lexer_classes = {find_lexer_class_by_name(alias) for alias in lexer_candidates}
    # We cannot test for strict equality yet, as some ANSI-ready lexers do not
    # have any test artifacts producing ``Generic.Output`` tokens.
    assert lexer_classes.issubset(collect_session_lexers())


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
