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
"""Configuration file loading, format parsing, and schema validation.

This package gathers the three layers behind ``--config``, ``--no-config``, and
``--validate-config``:

- :mod:`~click_extra.config.formats` — the supported file formats and their
  stateless content parsers.
- :mod:`~click_extra.config.schema` — the schema-building and validation engine.
- :mod:`~click_extra.config.option` — the option classes and click-extra's own
  configuration schemas.

Every public symbol is re-exported here so consumers can keep importing from
``click_extra.config``.
"""

from __future__ import annotations

from .formats import ConfigFormat
from .option import (
    NO_CONFIG,
    VCS,
    ClickExtraConfig,
    ConfigOption,
    NoConfigOption,
    PrebakeConfig,
    TestPlanConfig,
    ValidateConfigOption,
)
from .schema import (
    DEFAULT_SUBCOMMANDS_KEY,
    EXTENSION_METADATA_KEY,
    PREPEND_SUBCOMMANDS_KEY,
    THEMES_CONFIG_KEY,
    ConfigValidator,
    ValidationError,
    ValidationReport,
    _builtin_config_validators,
    _collect_opaque_paths_from_schema,
    _expand_dotted_keys,
    _select_app_section,
    _strip_opaque_subtrees,
    _strip_reserved_keys,
    flatten_config_keys,
    get_tool_config,
    make_schema_callable,
    normalize_config_keys,
    run_config_validation,
)

__all__ = [
    "DEFAULT_SUBCOMMANDS_KEY",
    "EXTENSION_METADATA_KEY",
    "NO_CONFIG",
    "PREPEND_SUBCOMMANDS_KEY",
    "THEMES_CONFIG_KEY",
    "VCS",
    "ClickExtraConfig",
    "ConfigFormat",
    "ConfigOption",
    "ConfigValidator",
    "NoConfigOption",
    "PrebakeConfig",
    "TestPlanConfig",
    "ValidateConfigOption",
    "ValidationError",
    "ValidationReport",
    "_builtin_config_validators",
    "_collect_opaque_paths_from_schema",
    "_expand_dotted_keys",
    "_select_app_section",
    "_strip_opaque_subtrees",
    "_strip_reserved_keys",
    "flatten_config_keys",
    "get_tool_config",
    "make_schema_callable",
    "normalize_config_keys",
    "run_config_validation",
]
