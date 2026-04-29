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
"""Expose package-wide elements."""

from __future__ import annotations

# Import all click's module-level content to allow for drop-in replacement.
# XXX Star import is really badly supported by mypy for now and leads to lots of
# "Module 'XXX' has no attribute 'YYY'". See: https://github.com/python/mypy/issues/4930
from click import *
from click._utils import UNSET
from click.core import ParameterSource

# Overrides click helpers with cloup's.
from cloup import *  # type: ignore[no-redef, assignment]

# XXX Import types first to avoid circular imports. The True condition is a hack to
# prevent ruff from re-ordering imports.
if True:
    from .types import ChoiceSource, EnumChoice

from .colorize import (
    ColorOption,
    HelpExtraFormatter,
    HelpKeywords,
)
from .theme import (
    HelpExtraTheme,
    ThemeOption,
    register_theme,
    theme_registry,
)
from .commands import (
    ExtraCommand,
    ExtraContext,
    ExtraGroup,
    HelpCommand,
    LazyGroup,
)
from .config import (
    DEFAULT_SUBCOMMANDS_KEY,
    NO_CONFIG,
    PREPEND_SUBCOMMANDS_KEY,
    VCS,
    ConfigFormat,
    ConfigOption,
    NoConfigOption,
    ValidateConfigOption,
    flatten_config_keys,
    get_tool_config,
    normalize_config_keys,
)
from .decorators import (  # type: ignore[no-redef]
    argument,
    color_option,
    command,
    config_option,
    group,
    help_option,
    jobs_option,
    lazy_group,
    no_config_option,
    option,
    show_params_option,
    table_format_option,
    telemetry_option,
    theme_option,
    timer_option,
    validate_config_option,
    verbose_option,
    verbosity_option,
    version_option,
)
from .jobs import CPU_COUNT, DEFAULT_JOBS, JobsOption
from .logging import (
    ExtraFormatter,
    ExtraStreamHandler,
    LogLevel,
    VerboseOption,
    VerbosityOption,
    extraBasicConfig,
    new_extra_logger,
)
from .parameters import (
    Argument,
    ExtraOption,
    Option,
    ParamStructure,
    ShowParamsOption,
    format_param_row,
    get_param_spec,
    search_params,
)
from .table import (
    SortByOption,
    TableFormat,
    TableFormatOption,
    print_data,
    print_sorted_table,
    print_table,
    render_table,
    serialize_data,
)
from .telemetry import TelemetryOption
from .testing import ExtraCliRunner
from .timer import TimerOption
from .version import ExtraVersionOption

__all__ = [
    "BOOL",
    "CPU_COUNT",
    "DEFAULT_JOBS",
    "DEFAULT_SUBCOMMANDS_KEY",
    "FLOAT",
    "INT",
    "NO_CONFIG",
    "PREPEND_SUBCOMMANDS_KEY",
    "STRING",
    "UNPROCESSED",
    "UNSET",
    "UUID",
    "VCS",
    "Abort",
    "Argument",
    "BadArgumentUsage",
    "BadOptionUsage",
    "BadParameter",
    "Choice",
    "ChoiceSource",
    "ClickException",
    "Color",
    "ColorOption",
    "Command",
    "CommandCollection",
    "ConfigFormat",
    "ConfigOption",
    "ConstraintMixin",
    "Context",
    "DateTime",
    "EnumChoice",
    "ExtraCliRunner",
    "ExtraCommand",
    "ExtraContext",
    "ExtraFormatter",
    "ExtraGroup",
    "ExtraOption",
    "ExtraStreamHandler",
    "ExtraVersionOption",
    "File",
    "FileError",
    "FloatRange",
    "Group",
    "HelpCommand",
    "HelpExtraFormatter",
    "HelpExtraTheme",
    "HelpFormatter",
    "HelpKeywords",
    "HelpSection",
    "HelpTheme",
    "IntRange",
    "JobsOption",
    "LazyGroup",
    "LogLevel",
    "MissingParameter",
    "NoConfigOption",
    "NoSuchOption",
    "Option",
    "OptionGroup",
    "OptionGroupMixin",
    "ParamStructure",
    "ParamType",
    "Parameter",
    "ParameterSource",
    "Path",
    "Section",
    "SectionMixin",
    "ShowParamsOption",
    "SortByOption",
    "Style",
    "TableFormat",
    "TableFormatOption",
    "TelemetryOption",
    "ThemeOption",
    "TimerOption",
    "Tuple",
    "UsageError",
    "ValidateConfigOption",
    "VerboseOption",
    "VerbosityOption",
    "VersionOption",
    "annotations",
    "argument",
    "clear",
    "color_option",
    "command",
    "config_option",
    "confirm",
    "confirmation_option",
    "constrained_params",
    "constraint",
    "dir_path",
    "echo",
    "echo_via_pager",
    "edit",
    "extraBasicConfig",
    "file_path",
    "flatten_config_keys",
    "format_filename",
    "format_param_row",
    "get_app_dir",
    "get_binary_stream",
    "get_current_context",
    "get_param_spec",
    "get_text_stream",
    "get_tool_config",
    "getchar",
    "group",
    "help_option",
    "jobs_option",
    "launch",
    "lazy_group",
    "make_pass_decorator",
    "new_extra_logger",
    "no_config_option",
    "normalize_config_keys",
    "open_file",
    "option",
    "option_group",
    "pass_context",
    "pass_obj",
    "password_option",
    "path",
    "pause",
    "print_data",
    "print_sorted_table",
    "print_table",
    "progressbar",
    "prompt",
    "register_theme",
    "render_table",
    "search_params",
    "secho",
    "serialize_data",
    "show_params_option",
    "style",
    "table_format_option",
    "telemetry_option",
    "theme_option",
    "theme_registry",
    "timer_option",
    "unstyle",
    "validate_config_option",
    "verbose_option",
    "verbosity_option",
    "version_option",
    "warnings",
    "wrap_text",
]
"""Expose all of Click, Cloup and Click Extra.

.. note::
    The content of ``__all__`` is checked by a unittest and sorted by
    ``ruff`` via `RUF022 <https://docs.astral.sh/ruff/rules/unsorted-dunder-all/>`_.
"""


__version__ = "7.15.0.dev0"
__git_branch__ = ""
__git_date__ = ""
__git_long_hash__ = ""
__git_short_hash__ = ""
__git_tag__ = ""
__git_tag_sha__ = ""


def __getattr__(name: str) -> object:
    import warnings

    old_to_new = {
        "extra_command": (command, "command"),
        "extra_group": (group, "group"),
        "extra_version_option": (version_option, "version_option"),
    }

    if name in old_to_new:
        func, new_name = old_to_new[name]
        warnings.warn(
            f"{name!r} is deprecated and will be removed in Click Extra 8.0.0. Use"
            f" {new_name!r} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return func

    raise AttributeError(name)
