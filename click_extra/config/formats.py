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

Holds the {class}`ConfigFormat` enum, the optional third-party parser probes
that decide which formats are enabled, and {func}`parse_content`, the stateless
dispatch used by {class}`~click_extra.config.option.ConfigOption` for every format that
does not need the CLI parameter structure.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from enum import Enum
from fnmatch import fnmatch

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]


TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path
    from typing import Any

logger = logging.getLogger(__name__)


_OPTIONAL_PARSERS: tuple[tuple[str, str, str], ...] = (
    # (import module name, click-extra[extra] name, display label).
    ("yaml", "yaml", "YAML"),
    ("json5", "json5", "JSON5"),
    ("jsonc", "jsonc", "JSONC"),
    ("hjson", "hjson", "Hjson"),
    ("xmltodict", "xml", "XML"),
)
"""Third-party parsers each gating one optional configuration format.

Each entry pairs the importable module name (probed without importing it) with
the `click-extra[extra]` install target and the human-readable format label
used in the disabled-support debug message."""

PARSER_SUPPORT: dict[str, bool] = {}
"""Availability of each optional parser, keyed by `click-extra[extra]` name.

Populated once at import time by probing each module in `_OPTIONAL_PARSERS`
with {func}`importlib.util.find_spec`. Read by {class}`ConfigFormat` to mark the
matching format as enabled or disabled. The probe does not import the module, so
the actual parser is loaded lazily by {func}`parse_content` only when used."""

for _module_name, _extra, _label in _OPTIONAL_PARSERS:
    PARSER_SUPPORT[_extra] = importlib.util.find_spec(_module_name) is not None
    if not PARSER_SUPPORT[_extra]:
        logger.debug(
            f"{_label} support disabled: install click-extra[{_extra}] to enable it."
        )


class ConfigFormat(Enum):
    """All configuration formats, associated to their support status.

    The first element of the tuple is a sequence of file extensions associated to the
    format. Patterns are fed to `wcmatch.glob` for matching, and are influenced by the
    flags set on the `ConfigOption` instance.

    The second element indicates whether the format is supported or not, depending on
    the availability of the required third-party packages. This evaluation is performed
    at runtime when this module is imported.

    ```{caution}
    The order is important for both format members and file patterns. It defines the
    priority order in which formats are tried when multiple candidate files are found.
    ```

    ```{todo}
    Add support for [JWCC](https://nigeltao.github.io/blog/2021/json-with-commas-comments.html)
    / [hujson](https://github.com/tailscale/hujson) format?
    ```
    """

    TOML = (("*.toml",), True, "TOML")
    YAML = (("*.yaml", "*.yml"), PARSER_SUPPORT["yaml"], "YAML")
    JSON = (("*.json",), True, "JSON")
    JSON5 = (("*.json5",), PARSER_SUPPORT["json5"], "JSON5")
    JSONC = (("*.jsonc",), PARSER_SUPPORT["jsonc"], "JSONC")
    HJSON = (("*.hjson",), PARSER_SUPPORT["hjson"], "Hjson")
    INI = (("*.ini",), True, "INI")
    XML = (("*.xml",), PARSER_SUPPORT["xml"], "XML")
    PYPROJECT_TOML = (("pyproject.toml",), True, "pyproject.toml")

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        """Human-friendly name of the format for display in messages."""
        return self.value[2]  # type: ignore[no-any-return]

    @property
    def enabled(self) -> bool:
        """Returns `True` if the format is supported, `False` otherwise."""
        return self.value[1]  # type: ignore[no-any-return]

    @property
    def patterns(self) -> tuple[str, ...]:
        """Returns the default file patterns associated to the format."""
        return self.value[0]  # type: ignore[no-any-return]


def parse_content(fmt: ConfigFormat, content: str) -> Any:
    """Parse content with a single stateless format.

    INI is excluded: it needs the CLI parameter structure for type
    coercion and is handled by ConfigOption.load_ini_config.

    ```{note}
    Optional third-party parsers are imported lazily, at the point of use,
    rather than at module load. Only enabled formats reach this function
    (disabled ones are filtered out of `ConfigOption.file_format_patterns`),
    so the import always resolves for the formats actually parsed here.
    ```
    """
    match fmt:
        case ConfigFormat.TOML:
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
            import jsonc

            return jsonc.loads(content)

        case ConfigFormat.HJSON:
            import hjson

            return hjson.loads(content)

        case ConfigFormat.XML:
            import xmltodict

            return xmltodict.parse(content)

        case ConfigFormat.PYPROJECT_TOML:
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
)
"""Configuration formats {func}`serialize_content` can write, in priority order.

Every {class}`ConfigFormat` except {attr}`~ConfigFormat.INI` and
{attr}`~ConfigFormat.PYPROJECT_TOML`, which have no serializer. `JSON`,
`JSON5` and `JSONC` are emitted as plain JSON through the standard library,
so they need no optional dependency; the others require their format's extra.

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
    Not every format round-trips: `TOML` and `XML` have no null type, and
    `XML` expects a single root mapping, so the caller is responsible for
    shaping `data` accordingly. `INI` and `pyproject.toml` have no
    serializer here.
    ```

    ```{note}
    Optional third-party serializers are imported lazily, at the point of use.
    Writing `TOML` uses `tomlkit` (the `[toml]` extra), unlike reading
    which relies on the built-in `tomllib`.
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
            import tomlkit

            doc = tomlkit.document()
            for key, value in data.items():
                doc.add(key, value)
            return tomlkit.dumps(doc)
        case ConfigFormat.HJSON:
            import hjson

            return str(hjson.dumps(data, **{"ensure_ascii": False, **kwargs})) + "\n"
        case ConfigFormat.XML:
            import xmltodict

            result: str = xmltodict.unparse(
                data,
                **{
                    "pretty": True,
                    "encoding": "unicode",
                    "full_document": False,
                    **kwargs,
                },
            )
            return result + "\n"
    raise ValueError(f"{fmt!r} is not handled by serialize_content().")


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
    candidates = tuple(ConfigFormat) if formats is None else formats
    for fmt in candidates:
        if any(fnmatch(path.name, pattern) for pattern in fmt.patterns):
            return fmt
    return None


def disabled_format_message(fmt: ConfigFormat) -> str:
    """Build the "format support disabled, install the extra" message for a format.

    The single source for the {exc}`ImportError` text raised when a format whose
    optional parser is not installed is requested, shared by {func}`read_file` and
    {func}`click_extra.test_suite.parse_test_suite`. A format's
    {attr}`~click_extra.config.formats.ConfigFormat.label`, lower-cased, is its
    `click-extra[<extra>]` install target.
    """
    return (
        f"{fmt} support disabled: install click-extra[{fmt.label.lower()}] "
        "to enable it."
    )


def read_file(path: Path, formats: Iterable[ConfigFormat] | None = None) -> Any:
    """Read a file and parse it, picking the format from its name.

    The format is resolved with {func}`format_from_path` over `formats` (every
    {class}`~click_extra.config.formats.ConfigFormat` by default), then the
    content is parsed with {func}`parse_content`.

    :raises ValueError: the file name matches none of the candidate `formats`.
    :raises ImportError: the matched format's optional parser is not installed.
    """
    fmt = format_from_path(path, formats)
    if fmt is None:
        raise ValueError(f"Unsupported file extension: {path.name!r}")
    if not fmt.enabled:
        raise ImportError(disabled_format_message(fmt))
    return parse_content(fmt, path.read_text(encoding="utf-8"))
