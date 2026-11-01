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
"""Bake build-time metadata into Python source files before compilation.

Compiled binaries (Nuitka, PyInstaller) and `git`-less runtimes (Docker
images, archive checkouts) cannot resolve version or Git metadata at runtime
the way {class}`click_extra.version.VersionOption` does. The values must
instead be written into the source *before* the build, by rewriting the
relevant dunder assignments (`__version__`, `__git_short_hash__`, ...) in
place with {mod}`ast`.

This mirrors [shadow-rs](https://github.com/baoyachi/shadow-rs), which
injects build-time constants (`BRANCH`, `SHORT_COMMIT`, `COMMIT_HASH`,
`COMMIT_DATE`, `TAG`, ...) into Rust binaries at compile time. Its
`BUILD_TIME`, `BUILD_OS` and `BUILD_TARGET` constants have counterparts here
too, in {data}`click_extra.version_facts.BUILD_RESOLVERS`: those describe the host
that produced the binary, which neither the git fields nor the running
interpreter can answer once it is running somewhere else.

{func}`click_extra.project.discover_package_init_files` finds the files to bake
from a project's packaging metadata.
"""

from __future__ import annotations

import ast
import logging
from itertools import accumulate
from pathlib import Path

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping

logger = logging.getLogger(__name__)


def _iter_dunder_strs(tree: ast.Module) -> Iterator[tuple[str, ast.Constant]]:
    """Yield `(name, node)` for each top-level `name = "..."` of a parsed module.

    Only a single-target assignment of a string literal qualifies, which is the
    shape a dunder placeholder takes. The node is the {class}`ast.Constant` of
    the string value, whose positions locate the literal in the source.
    """
    for node in ast.iter_child_nodes(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            yield node.targets[0].id, node.value


def _find_dunder_str(source: str, name: str) -> ast.Constant | None:
    """The string constant the first top-level `name = "..."` of `source` assigns.

    :param source: the Python source to search.
    :param name: the variable to look for.
    :return: the node of the string value, or `None` when no such assignment
        exists.
    """
    for found, node in _iter_dunder_strs(ast.parse(source)):
        if found == name:
            return node
    return None


def _string_literal(value: str, delimiter: str) -> str:
    """Spell `value` as a Python string literal between `delimiter` quotes.

    Escapes what would otherwise end the literal or change its value: a
    backslash, the quote character itself, and a line break.
    """
    quote = delimiter[0]
    escaped = (
        value
        .replace("\\", "\\\\")
        .replace(quote, f"\\{quote}")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f"{delimiter}{escaped}{delimiter}"


def _replace_str_literals(
    source: str,
    replacements: Iterable[tuple[ast.Constant, str]],
) -> str:
    """Replace string literals in `source`, keeping the quotes they open with.

    Each node's positions locate its whole literal, string prefix and implicit
    concatenation included, and the span is rewritten as one literal opening and
    closing on the quotes the original opened with. Everything around it is
    left as it was.

    AST columns count UTF-8 bytes, so the splice happens on the encoded source.
    The spans are rewritten from the last one backwards: a literal earlier in the
    file keeps its offsets once a later one has changed length.

    :param source: the Python source, with `\\n` line endings.
    :param replacements: each literal's node, with the value it is to hold.
    :return: the rewritten source.
    """
    encoded = source.encode("UTF-8")
    line_starts = [0, *accumulate(len(line) + 1 for line in encoded.split(b"\n"))]
    spans: list[tuple[int, int, bytes]] = []
    for node, value in replacements:
        assert node.end_lineno is not None and node.end_col_offset is not None
        start = line_starts[node.lineno - 1] + node.col_offset
        end = line_starts[node.end_lineno - 1] + node.end_col_offset
        # A string prefix (`r`, `u`) carries no quote, and a triple quote opens
        # with three of them.
        original = encoded[start:end].decode("UTF-8").lstrip("rRuU")
        delimiter = original[:3] if original[:3] in ('"""', "'''") else original[0]
        spans.append((start, end, _string_literal(value, delimiter).encode("UTF-8")))
    for start, end, literal in sorted(spans, reverse=True):
        encoded = encoded[:start] + literal + encoded[end:]
    return encoded.decode("UTF-8")


def _bake(
    file_path: Path,
    fields: Mapping[str, str | Callable[[], str | None]],
    *,
    report_missing: Callable[..., None],
) -> dict[str, str]:
    """Fill the empty placeholders of `fields` in `file_path`, in one pass.

    The work behind {func}`prebake_dunders` and {func}`prebake_dunder`, which
    differ only in how loudly a field with no placeholder is reported.

    :param file_path: the Python source file to rewrite.
    :param fields: dunder names mapped to the value to bake, or to a callable
        resolving it on demand.
    :param report_missing: the logging call reporting a field the file holds no
        placeholder for.
    :return: the names written, each mapped to the value it received.
    """
    source = file_path.read_text(encoding="UTF-8")
    nodes: dict[str, ast.Constant] = {}
    for name, node in _iter_dunder_strs(ast.parse(source)):
        if name in fields and name not in nodes:
            nodes[name] = node
    for name in fields.keys() - nodes.keys():
        report_missing("No %s found in %s.", name, file_path)

    baked: dict[str, str] = {}
    for name, node in nodes.items():
        if node.value:
            logger.info(
                "%s in %s already has value %r: skipping.",
                name,
                file_path,
                node.value,
            )
            continue
        value = fields[name]
        resolved = value() if callable(value) else value
        if not resolved:
            logger.info("No value to bake into %s in %s: skipping.", name, file_path)
            continue
        baked[name] = resolved

    if baked:
        file_path.write_text(
            _replace_str_literals(
                source, ((nodes[name], value) for name, value in baked.items())
            ),
            encoding="UTF-8",
        )
        for name, value in baked.items():
            logger.info("Pre-baked %s in %s: %r", name, file_path, value)
    return baked


def prebake_version(file_path: Path, local_version: str) -> str | None:
    """Append a [PEP 440 local version identifier](https://peps.python.org/pep-0440/#local-version-identifiers) to `__version__`.

    The compile-time complement to the runtime
    {attr}`click_extra.version.VersionOption.version` property: a Nuitka or
    PyInstaller binary cannot run `git` at runtime, so the hash must be baked
    into `__version__` in the source file *before* compilation.

    Only a `.dev` version is touched, and only when it carries no `+` suffix
    yet: a release version and an already pre-baked one are left alone, which
    makes a second run safe.

    :param file_path: the Python source file declaring `__version__`.
    :param local_version: the identifier to append, like a Git short hash.
    :return: the new version, or `None` when nothing changed: a release
        version, an already pre-baked one, or no `__version__` at all.
    """
    source = file_path.read_text(encoding="UTF-8")
    node = _find_dunder_str(source, "__version__")
    if node is None:
        logger.warning("No __version__ found in %s.", file_path)
        return None

    version = node.value
    assert isinstance(version, str)
    if ".dev" not in version:
        logger.info("Release version %r in %s: skipping.", version, file_path)
        return None
    if "+" in version:
        logger.info(
            "Version %r in %s already has a local identifier: skipping.",
            version,
            file_path,
        )
        return None

    new_version = f"{version}+{local_version}"
    file_path.write_text(
        _replace_str_literals(source, ((node, new_version),)), encoding="UTF-8"
    )
    logger.info(
        "Pre-baked __version__ in %s: %r to %r", file_path, version, new_version
    )
    return new_version


def prebake_dunders(
    file_path: Path,
    fields: Mapping[str, str | Callable[[], str | None]],
) -> dict[str, str]:
    """Fill the empty dunder placeholders of a Python source file in one pass.

    Reads and parses `file_path` once, then writes it once, with every
    placeholder of `fields` that was found empty filled in. A field whose value
    is a callable is resolved only when its placeholder is present and still
    empty, so a resolver that shells out (to `git`, say) runs for the
    placeholders that need it, never for a file carrying none. A callable
    answering `None` or an empty string leaves its placeholder alone, as does a
    placeholder already holding a value: running the pass twice is safe.

    Placeholders must use empty strings (`__field__ = ""`, not `None`). The AST
    matcher only recognizes string literals, and the empty string acts as a
    falsy sentinel that stays type-consistent with baked values (always `str`).

    A name with no placeholder in the file is skipped: a build bakes every field
    it knows into every file of a package, and most files declare a few of them.
    {func}`prebake_dunder` is the single-field form, which does warn.

    :param file_path: the Python source file to rewrite.
    :param fields: dunder names (`__git_branch__`) mapped to the value to bake,
        or to a callable resolving it on demand.
    :return: the names written, each mapped to the value it received. Empty when
        the file was left untouched.
    """
    return _bake(file_path, fields, report_missing=logger.debug)


def prebake_dunder(file_path: Path, name: str, value: str) -> str | None:
    """Replace an empty dunder variable's value in a Python source file.

    The single-field form of {func}`prebake_dunders`, which carries the
    placeholder rules, with one addition: a file holding no `name` assignment
    at all is reported with a warning, since a lone field is asked for on
    purpose and a typo in its name would otherwise pass unnoticed.

    Where {func}`prebake_version` appends a PEP 440 local identifier to
    `__version__`, this replaces the whole value of any dunder variable that
    starts empty. Typical use case: injecting a release commit SHA into
    `__git_tag_sha__ = ""` at build time.

    :param file_path: the Python source file to rewrite.
    :param name: the dunder variable to fill, like `__git_tag_sha__`.
    :param value: the value to bake.
    :return: the value written, or `None` when nothing changed: no such
        variable, or one already holding a value.
    """
    return _bake(file_path, {name: value}, report_missing=logger.warning).get(name)
