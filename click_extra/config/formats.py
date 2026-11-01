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
"""Configuration file formats and their stateless content parsers.

Holds the {class}`ConfigFormat` enum, which probes on first use the modules that
decide whether a format is enabled, and {func}`parse_content`, the stateless
dispatch used by {class}`~click_extra.config.option.ConfigOption` for every format
that does not need the CLI parameter structure.

```{caution}
This module is imported early in the package's import graph
({mod}`~click_extra.table` reaches it before the
{mod}`~click_extra.parameters` / {mod}`~click_extra.context` chain has
settled), so it takes no top-level import from `click_extra` itself. A format
whose parsing needs the CLI structure or a binary file, like `INI`, `ARGFILE`
and `SQLITE`, lives as a `ConfigOption` method in
{mod}`~click_extra.config.option` instead of here.
```
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
from enum import Enum
from fnmatch import fnmatch
from functools import cache

from .._utils import missing_extra_message

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any

logger = logging.getLogger(__name__)


_NO_SQLITE_MESSAGE = (
    "SQLite support disabled: this Python provides no sqlite3 module. "
    "Install the sqlite3 package of your Python distribution to enable it."
)
"""Reason and remedy reported for a Python whose SQLite bindings are missing.

{func}`disabled_format_message` cannot derive it the way it does for the other
formats: `SQLITE` is backed by a standard library module, so no
`click-extra[extra]` install target enables it."""

_JSONC_COMMENT = r'(?s)("(?:\\.|[^"\\])*")|//[^\n]*|/\*.*?\*/'
"""Match a JSON string, kept, or a `//` line or `/* */` block comment, dropped.

A pattern string rather than a compiled pattern: {mod}`re` compiles and caches it
on the first {func}`parse_jsonc` call, which keeps the compilation off the
startup path of every CLI."""

_JSONC_TRAILING_COMMA = r'("(?:\\.|[^"\\])*")|,(\s*[}\]])'
"""Match a JSON string, kept, or the comma closing an object or an array, dropped.

Compiled on first use, like `_JSONC_COMMENT`."""


class ConfigFormat(Enum):
    """All configuration formats, associated to their support status.

    Each member's value is a tuple of four elements:

    1. The file patterns associated to the format. Patterns are fed to
       `wcmatch.glob` for matching, and are influenced by the flags set on the
       `ConfigOption` instance.
    2. The module backing the format, or `None` for a format the interpreter
       always supports. {attr}`enabled` probes it on first use.
    3. The human-readable label of the format.
    4. The media types a server may serve it as, as matched by
       {func}`format_from_mime`.

    ```{caution}
    The order is important for both format members and file patterns. It defines the
    priority order in which formats are tried when multiple candidate files are found.
    ```
    """

    TOML = (("*.toml",), None, "TOML", ("application/toml", "text/x-toml"))
    YAML = (
        ("*.yaml", "*.yml"),
        "yaml",
        "YAML",
        ("application/yaml", "text/yaml", "application/x-yaml", "text/x-yaml"),
    )
    JSON = (("*.json",), None, "JSON", ("application/json", "text/json"))
    # `*.jwcc` reads through the JSON5 parser: a JWCC document is JSON plus
    # comments and trailing commas, both of which JSON5 already accepts, so the
    # format needs no parser of its own. See
    # https://nigeltao.github.io/blog/2021/json-with-commas-comments.html.
    JSON5 = (("*.json5", "*.jwcc"), "json5", "JSON5", ("application/json5",))
    JSONC = (("*.jsonc",), None, "JSONC", ("application/jsonc",))
    HJSON = (("*.hjson",), "hjson", "Hjson", ("application/hjson",))
    INI = (("*.ini",), None, "INI", ())
    XML = (("*.xml",), None, "XML", ("application/xml", "text/xml"))
    PLIST = (("*.plist",), None, "plist", ("application/x-plist",))
    # A distribution can ship a Python without the SQLite bindings: FreeBSD
    # packages them apart from the interpreter, as `pyXXX-sqlite3`. The probe
    # targets `_sqlite3`, the extension module holding the bindings, and not the
    # `sqlite3` package importing them: every standard library has the latter,
    # including one that raises `ModuleNotFoundError` on its first import.
    SQLITE = (
        ("*.sqlite", "*.sqlite3"),
        "_sqlite3",
        "SQLite",
        ("application/vnd.sqlite3", "application/x-sqlite3"),
    )
    ARGFILE = (("*.conf",), None, "Argfile", ())
    PYPROJECT_TOML = (("pyproject.toml",), None, "pyproject.toml", ())

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        """Human-friendly name of the format for display in messages."""
        return self.value[2]  # type: ignore[no-any-return]

    @property
    def enabled(self) -> bool:
        """Whether the module backing the format is available.

        The module is probed on the first read, without being imported, and the
        answer is cached for the life of the process. Importing `click_extra`
        probes nothing: the first `ConfigOption` built does.
        """
        return _module_available(self)

    @property
    def patterns(self) -> tuple[str, ...]:
        """Returns the default file patterns associated to the format."""
        return self.value[0]  # type: ignore[no-any-return]

    @property
    def mime_types(self) -> tuple[str, ...]:
        """Media types a server may advertise the format as.

        Feeds {func}`format_from_mime`. Empty for a format no `Content-Type`
        header designates: `INI` and `ARGFILE` are both served as `text/plain`,
        which names no format, and `PYPROJECT_TOML` is keyed on a file name, so
        no media type tells it apart from plain `TOML`.
        """
        return self.value[3]  # type: ignore[no-any-return]


@cache
def _module_available(fmt: ConfigFormat) -> bool:
    """Probe the module backing `fmt`, without importing it.

    Logs {func}`disabled_format_message` at debug level when the module is missing.
    The parser itself is imported by {func}`parse_content`, on the first file it
    parses.
    """
    module = fmt.value[1]
    if module is None or importlib.util.find_spec(module) is not None:
        return True
    logger.debug(disabled_format_message(fmt))
    return False


SQLITE_CONFIG_TABLE = "config"
"""Name of the table {func}`click_extra.config.option.ConfigOption.load_sqlite_config`
reads a `SQLITE` configuration from.

The table holds `key`/`value` columns: dotted parameter paths and their
JSON-encoded values."""


def _toml_ready(data: Any) -> Any:
    """Replace every tuple in *data* with a list, at any depth.

    `tomlrt` refuses a tuple, while Click returns one for a parameter with
    `multiple=True` or `nargs`. TOML has a single array type, so the list writes
    the same array.
    """
    if isinstance(data, dict):
        return {key: _toml_ready(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [_toml_ready(value) for value in data]
    return data


def parse_jsonc(content: str) -> Any:
    """Read a JSONC document: JSON with comments and trailing commas.

    The comments are blanked and the trailing commas removed before {mod}`json`
    reads the rest, so an error it raises still names the line it sits on. A
    string keeps its content whole: a `//` or a comma inside it is not syntax.
    """

    def blank_comment(match: re.Match[str]) -> str:
        if match.group(1) is not None:
            return match.group(1)
        return "\n" * match.group().count("\n")

    content = re.sub(_JSONC_COMMENT, blank_comment, content)
    content = re.sub(
        _JSONC_TRAILING_COMMA,
        lambda match: match.group(1) if match.group(1) is not None else match.group(2),
        content,
    )
    return json.loads(content)


def parse_xml(content: str) -> dict[str, Any]:
    """Read an XML document into nested dictionaries, the root element outermost.

    An element holding text alone reads as that text, stripped of the whitespace
    around it, or as `None` when there is none. One holding attributes or child
    elements reads as a dictionary: an attribute under its name prefixed with
    `@`, a child under its tag, and the text under `#text`. Elements repeating
    a tag under the same parent are collected into a list, in document order.
    Comments and processing instructions are skipped, and a tag keeps its
    namespace prefix as written. These are the conventions of `xmltodict`.

    :raises xml.parsers.expat.ExpatError: on a malformed document.
    """
    # Deferred import: keeps xml off the startup path of every CLI.
    from xml.parsers import expat

    root: dict[str, Any] = {}
    # Each open element, as the dictionary it builds and its text so far.
    stack: list[tuple[dict[str, Any], list[str]]] = [(root, [])]

    def start_element(name: str, attributes: dict[str, str]) -> None:
        stack.append(({f"@{key}": value for key, value in attributes.items()}, []))

    def end_element(name: str) -> None:
        node, chunks = stack.pop()
        text = "".join(chunks).strip()
        value: Any
        if node:
            if text:
                node["#text"] = text
            value = node
        else:
            value = text or None
        parent = stack[-1][0]
        if name in parent:
            siblings = parent[name]
            if isinstance(siblings, list):
                siblings.append(value)
            else:
                parent[name] = [siblings, value]
        else:
            parent[name] = value

    def character_data(data: str) -> None:
        stack[-1][1].append(data)

    parser = expat.ParserCreate()
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    parser.CharacterDataHandler = character_data
    parser.Parse(content, True)
    return root


def _xml_text(value: Any) -> str:
    """Spell a value as XML text: `true` or `false` for a boolean, `str()` otherwise."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def serialize_xml(data: Mapping[str, Any], *, indent: str = "\t") -> str:
    """Write nested dictionaries as an XML document, one element per level.

    The inverse of {func}`parse_xml`, with the same conventions: a `@` key is an
    attribute, `#text` the text of an element that also carries attributes or
    children, a list a run of elements sharing a tag, and `None` or an empty
    string an empty element. Each top-level key is a root element. Child
    elements sit on their own lines, each level pushed by one `indent`.
    """
    # Deferred import: keeps xml off the startup path of every CLI.
    from xml.sax.saxutils import escape, quoteattr

    lines: list[str] = []

    def emit(name: str, value: Any, depth: int) -> None:
        if isinstance(value, list):
            for item in value:
                emit(name, item, depth)
            return
        attributes = ""
        text: str | None = None
        children: list[tuple[str, Any]] = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key.startswith("@"):
                    attributes += f" {key[1:]}={quoteattr(_xml_text(item))}"
                elif key == "#text":
                    text = _xml_text(item)
                else:
                    children.append((key, item))
        elif value is not None:
            text = _xml_text(value)
        pad = indent * depth
        opening = len(lines)
        lines.append(f"{pad}<{name}{attributes}>")
        for key, item in children:
            emit(key, item, depth + 1)
        if len(lines) == opening + 1:
            # Nothing was written under the element: close it on its own line.
            lines[opening] += f"{escape(text) if text else ''}</{name}>"
            return
        if text:
            lines.append(f"{pad}{indent}{escape(text)}")
        lines.append(f"{pad}</{name}>")

    for name, value in data.items():
        emit(name, value, 0)
    return "\n".join(lines)


def parse_content(fmt: ConfigFormat, content: str) -> Any:
    """Parse content with a single stateless format.

    `INI` is excluded: it needs the CLI parameter structure for type coercion and
    is handled by {meth}`~click_extra.config.option.ConfigOption.load_ini_config`.
    `ARGFILE` is excluded for the same reason: it maps command-line tokens to the
    CLI's parameters and is handled by
    {meth}`~click_extra.config.option.ConfigOption.load_argfile_config`. `SQLITE`
    is excluded too: it is a binary format, read from its file path by
    {meth}`~click_extra.config.option.ConfigOption.load_sqlite_config` instead of
    a text payload.

    `PLIST` parses here from its XML variant, the only one expressible as a text
    payload. The binary variant is read from its file path by
    {meth}`~click_extra.config.option.ConfigOption.load_plist_config`.

    ```{note}
    Optional third-party parsers are imported at the point of use. Only enabled
    formats reach this function (disabled ones are filtered out of
    `ConfigOption.file_format_patterns`), so the import always resolves for the
    formats parsed here.
    ```
    """
    match fmt:
        case ConfigFormat.TOML:
            # Deferred import: keeps tomllib off the startup path of every CLI.
            import tomllib

            return tomllib.loads(content)

        case ConfigFormat.YAML:
            import yaml

            return yaml.full_load(content)

        case ConfigFormat.JSON:
            return json.loads(content)

        case ConfigFormat.JSON5:
            import json5

            return json5.loads(content)

        case ConfigFormat.JSONC:
            return parse_jsonc(content)

        case ConfigFormat.HJSON:
            import hjson

            return hjson.loads(content)

        case ConfigFormat.XML:
            return parse_xml(content)

        case ConfigFormat.PLIST:
            # Deferred import: keeps plistlib off the startup path of every CLI.
            import plistlib

            return plistlib.loads(content.encode("UTF-8"))

        case ConfigFormat.PYPROJECT_TOML:
            # Deferred import: keeps tomllib off the startup path of every CLI.
            import tomllib

            return tomllib.loads(content).get("tool", {})

    raise ValueError(f"{fmt!r} is not handled by parse_content().")


SERIALIZABLE_FORMATS: tuple[ConfigFormat, ...] = (
    ConfigFormat.TOML,
    ConfigFormat.YAML,
    ConfigFormat.JSON,
    ConfigFormat.JSON5,
    ConfigFormat.JSONC,
    ConfigFormat.HJSON,
    ConfigFormat.XML,
    ConfigFormat.PLIST,
)
"""Configuration formats {func}`serialize_content` can write, in priority order.

Every {class}`ConfigFormat` except {attr}`~ConfigFormat.INI`,
{attr}`~ConfigFormat.SQLITE`, {attr}`~ConfigFormat.ARGFILE` and
{attr}`~ConfigFormat.PYPROJECT_TOML`, which have no serializer. `JSON`,
`JSON5` and `JSONC` are emitted as plain JSON and `PLIST` through
{mod}`plistlib`, all from the standard library, so they need no optional
dependency; the others require their format's extra.

```{caution}
Keep this in sync with the `match` statement in {func}`serialize_content`.
```
"""


def serialize_content(fmt: ConfigFormat, data: Any, **kwargs: Any) -> str:
    """Serialize a Python object to a string in the given format.

    The dumping counterpart to {func}`parse_content`. Per-format defaults can be
    overridden through `kwargs` (forwarded to the underlying serializer). JSON5
    and JSONC are emitted as plain JSON, a valid subset of both.

    ```{caution}
    Not every format round-trips: `TOML`, `XML` and `PLIST` have no null
    type (`plistlib` even raises on `None` values), and `XML` expects a
    single root mapping, so the caller is responsible for shaping `data`
    accordingly. `INI`, `SQLITE`, `ARGFILE` and `PYPROJECT_TOML` have no
    serializer.
    ```

    ```{note}
    Optional third-party serializers are imported lazily, at the point of use.
    Writing `TOML` uses [`tomlrt`](https://dimbleby.github.io/tomlrt/) (the
    `[toml]` extra), unlike reading which relies on the built-in `tomllib`.
    ```

    :raises ValueError: the format has no serializer.
    """
    match fmt:
        case ConfigFormat.JSON | ConfigFormat.JSON5 | ConfigFormat.JSONC:
            return (
                json.dumps(data, **{"ensure_ascii": False, "indent": 2, **kwargs})
                + "\n"
            )
        case ConfigFormat.YAML:
            import yaml

            return str(
                yaml.dump(
                    data,
                    **{"allow_unicode": True, "default_flow_style": False, **kwargs},
                )
            )
        case ConfigFormat.TOML:
            import tomlrt

            return tomlrt.dumps(_toml_ready(data))
        case ConfigFormat.HJSON:
            import hjson

            return str(hjson.dumps(data, **{"ensure_ascii": False, **kwargs})) + "\n"
        case ConfigFormat.XML:
            return serialize_xml(data, **kwargs) + "\n"
        case ConfigFormat.PLIST:
            # Deferred import: keeps plistlib off the startup path of every CLI.
            import plistlib

            return plistlib.dumps(data, **kwargs).decode("UTF-8") + "\n"
    raise ValueError(f"{fmt!r} is not handled by serialize_content().")


def _serialize_toml_with_unset(tree: dict[str, Any]) -> str:
    """Render *tree* as TOML, emitting `None` leaves as commented-out keys.

    TOML has no null type, so parameters without a value cannot round-trip as
    real entries. Instead of dropping them from the export, each one is
    rendered as a `# key =` comment line: the generated file documents every
    key that can be set, while leaving the unset ones inert.

    Relies on `tomlrt` (the `[toml]` extra), like
    {func}`~click_extra.config.formats.serialize_content` does for TOML.

    `tomlrt` attaches a comment to the key or the section header below it. The
    tree is walked in the order TOML renders it, the keys of a table before its
    sub-tables. Each comment waits for the next key or header, or goes to the
    end of the document.

    `tomlrt` writes no header for a table that holds only sub-tables. When such a
    table also has commented-out keys, they would read as keys of the table
    above. A comment or a blank line set above a header pins it, so each section
    gets a blank line there.

    :raises ImportError: when `tomlrt` is not installed.
    """
    import tomlrt

    pending: list[str] = []

    def fill(container: Any, mapping: dict[str, Any]) -> None:
        for key, value in mapping.items():
            if isinstance(value, dict):
                continue
            if value is None:
                pending.append(f"{key} =")
                continue
            container[key] = _toml_ready(value)
            if pending:
                container.leading_comments[key] = tuple(pending)
                pending.clear()
        for key, value in mapping.items():
            if not isinstance(value, dict):
                continue
            section = tomlrt.Table.section()
            # A blank line above the header pins it, and separates the section
            # from the one above.
            section.header_leading_block = (None,)
            container[key] = section
            # Comments waiting for this header are set on the installed table:
            # set on the detached one, tomlrt adds a second blank line above them.
            table = container[key]
            if pending:
                table.header_leading_block = (*pending, None)
                pending.clear()
            fill(table, value)

    doc = tomlrt.Document()
    fill(doc, tree)
    if pending:
        doc.epilogue = tuple(pending)
    return tomlrt.dumps(doc)


def format_from_path(
    path: Path,
    formats: Iterable[ConfigFormat] | None = None,
) -> ConfigFormat | None:
    """Return the configuration format whose patterns match a file name.

    The name is matched against each format's
    {attr}`~click_extra.config.formats.ConfigFormat.patterns`, so `app.toml`
    resolves to `TOML` and `app.yml` to `YAML`. `formats` restricts and
    orders the candidates (the first match wins); it defaults to every
    {class}`~click_extra.config.formats.ConfigFormat`.
    """
    for fmt in ConfigFormat if formats is None else formats:
        if any(fnmatch(path.name, pattern) for pattern in fmt.patterns):
            return fmt
    return None


def format_from_mime(
    mime_type: str,
    formats: Iterable[ConfigFormat] | None = None,
) -> ConfigFormat | None:
    """Return the configuration format a media type designates.

    The counterpart of {func}`format_from_path` for a configuration fetched over
    HTTP, whose URL often carries no usable file extension: the `Content-Type`
    header is then the only thing typing the payload. The media type is matched
    against each format's {attr}`~click_extra.config.formats.ConfigFormat.mime_types`,
    so `application/toml` resolves to `TOML` and `text/yaml` to `YAML`. `formats`
    restricts and orders the candidates (the first match wins); it defaults to
    every {class}`~click_extra.config.formats.ConfigFormat`.

    Parameters are stripped, so a raw `application/yaml; charset=utf-8` header
    value can be passed as-is, and matching is case-insensitive.

    ```{note}
    A [RFC 6839](https://www.rfc-editor.org/rfc/rfc6839.html) structured syntax
    suffix is honored, so the `application/vnd.acme.settings+json` a private API
    answers with resolves to `JSON`. An exact match wins over a suffix.
    ```

    Returns `None` for a media type no format claims, which covers the generic
    `text/plain` and `application/octet-stream` a server falls back to for an
    extension it does not recognize.
    """
    media_type = mime_type.partition(";")[0].strip().lower()
    if not media_type:
        return None

    lookups = [media_type]
    suffix = media_type.rpartition("+")[2]
    if suffix != media_type:
        lookups.append(f"application/{suffix}")

    # Materialize: `formats` may be a one-shot iterable, and the suffix lookup
    # walks the candidates a second time.
    candidates = tuple(ConfigFormat) if formats is None else tuple(formats)
    for lookup in lookups:
        for fmt in candidates:
            if lookup in fmt.mime_types:
                return fmt
    return None


def disabled_format_message(fmt: ConfigFormat) -> str:
    """Build the "format support disabled" message for a format.

    The single source for the debug line logged when {attr}`ConfigFormat.enabled`
    finds the parser missing, and for the {exc}`ImportError` text raised when such
    a format is requested, shared by {func}`read_file` and
    {func}`click_extra.test_suite.parse_test_suite`. A format's
    {attr}`~click_extra.config.formats.ConfigFormat.label`, lower-cased, is its
    `click-extra[<extra>]` install target, worded like every other missing
    optional dependency of the package.

    {attr}`~ConfigFormat.SQLITE` is the exception: it reads through the standard
    library, so no extra installs it and it gets `_NO_SQLITE_MESSAGE` instead.
    """
    if fmt is ConfigFormat.SQLITE:
        return _NO_SQLITE_MESSAGE
    return missing_extra_message(fmt.label.lower(), subject=f"{fmt} support")


def read_file(path: Path, formats: Iterable[ConfigFormat] | None = None) -> Any:
    """Read a file and parse it, picking the format from its name.

    The format is resolved with {func}`format_from_path` over `formats` (every
    {class}`~click_extra.config.formats.ConfigFormat` by default), then the
    content is parsed with {func}`parse_content`.

    :raises ValueError: the file name matches none of the candidate `formats`.
    :raises ImportError: the matched format's parser is not available.
    """
    fmt = format_from_path(path, formats)
    if fmt is None:
        raise ValueError(f"Unsupported file extension: {path.name!r}")
    if not fmt.enabled:
        raise ImportError(disabled_format_message(fmt))
    return parse_content(fmt, path.read_text(encoding="UTF-8"))
