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

This package gathers the layers behind ``--config``, ``--no-config``, and
``--validate-config``:

- :mod:`~click_extra.config.formats`: the supported file formats and the
  generic, stateless helpers to read, serialize, auto-detect, and resolve them.
- :mod:`~click_extra.config.schema`: the generic schema-building and validation
  engine, applicable to any dataclass.
- :mod:`~click_extra.config.builtin`: click-extra's own configuration schema and
  the validators it registers by default (one concrete application of the
  engine).
- :mod:`~click_extra.config.option`: the ``--config`` / ``--no-config`` /
  ``--validate-config`` option classes.

Every public symbol is re-exported here so consumers can keep importing from
``click_extra.config``.
"""

from __future__ import annotations

from .builtin import (
    THEMES_CONFIG_KEY,
    ClickExtraConfig,
    PrebakeConfig,
    TestPlanConfig,
)
from .formats import (
    ConfigFormat,
    format_from_path,
    parse_content,
    read_file,
    serialize_content,
)
from .option import (
    NO_CONFIG,
    VCS,
    ConfigOption,
    NoConfigOption,
    ValidateConfigOption,
)
from .schema import (
    CONFIG_PATH_METADATA_KEY,
    DEFAULT_SUBCOMMANDS_KEY,
    EXTENSION_METADATA_KEY,
    NORMALIZE_KEYS_METADATA_KEY,
    PREPEND_SUBCOMMANDS_KEY,
    ConfigValidator,
    ValidationError,
    ValidationReport,
    flatten_config_keys,
    get_tool_config,
    make_schema_callable,
    normalize_config_keys,
    run_config_validation,
)

__all__ = [
    "CONFIG_PATH_METADATA_KEY",
    "DEFAULT_SUBCOMMANDS_KEY",
    "EXTENSION_METADATA_KEY",
    "NORMALIZE_KEYS_METADATA_KEY",
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
    "flatten_config_keys",
    "format_from_path",
    "get_tool_config",
    "make_schema_callable",
    "normalize_config_keys",
    "parse_content",
    "read_file",
    "run_config_validation",
    "serialize_content",
]
