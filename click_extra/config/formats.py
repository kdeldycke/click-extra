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

Holds the :class:`ConfigFormat` enum, the optional third-party parser probes
that decide which formats are enabled, and :func:`parse_content`, the stateless
dispatch used by :class:`~click_extra.config.option.ConfigOption` for every format that
does not need the CLI parameter structure.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from enum import Enum

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]


TYPE_CHECKING = False
if TYPE_CHECKING:
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
the ``click-extra[extra]`` install target and the human-readable format label
used in the disabled-support debug message."""

PARSER_SUPPORT: dict[str, bool] = {}
"""Availability of each optional parser, keyed by ``click-extra[extra]`` name.

Populated once at import time by probing each module in ``_OPTIONAL_PARSERS``
with :func:`importlib.util.find_spec`. Read by :class:`ConfigFormat` to mark the
matching format as enabled or disabled. The probe does not import the module, so
the actual parser is loaded lazily by :func:`parse_content` only when used."""

for _module_name, _extra, _label in _OPTIONAL_PARSERS:
    PARSER_SUPPORT[_extra] = importlib.util.find_spec(_module_name) is not None
    if not PARSER_SUPPORT[_extra]:
        logger.debug(
            f"{_label} support disabled: install click-extra[{_extra}] to enable it."
        )


class ConfigFormat(Enum):
    """All configuration formats, associated to their support status.

    The first element of the tuple is a sequence of file extensions associated to the
    format. Patterns are fed to ``wcmatch.glob`` for matching, and are influenced by the
    flags set on the ``ConfigOption`` instance.

    The second element indicates whether the format is supported or not, depending on
    the availability of the required third-party packages. This evaluation is performed
    at runtime when this module is imported.

    .. caution::
        The order is important for both format members and file patterns. It defines the
        priority order in which formats are tried when multiple candidate files are found.

    .. todo::
        Add support for `JWCC
        <https://nigeltao.github.io/blog/2021/json-with-commas-comments.html>`_
        / `hujson <https://github.com/tailscale/hujson>`_ format?
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
        """Returns ``True`` if the format is supported, ``False`` otherwise."""
        return self.value[1]  # type: ignore[no-any-return]

    @property
    def patterns(self) -> tuple[str, ...]:
        """Returns the default file patterns associated to the format."""
        return self.value[0]  # type: ignore[no-any-return]


def parse_content(fmt: ConfigFormat, content: str) -> Any:
    """Parse content with a single stateless format.

    INI is excluded: it needs the CLI parameter structure for type
    coercion and is handled by ConfigOption.load_ini_config.

    .. note::
        Optional third-party parsers are imported lazily, at the point of use,
        rather than at module load. Only enabled formats reach this function
        (disabled ones are filtered out of ``ConfigOption.file_format_patterns``),
        so the import always resolves for the formats actually parsed here.
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
