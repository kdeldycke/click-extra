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
from click import *  # noqa: F403
from click._utils import UNSET
from click.core import ParameterSource

# Overrides click helpers with cloup's.
from cloup import *  # type: ignore[no-redef, assignment] # noqa: F403

# XXX Import types first to avoid circular imports. The True condition is a hack to
# prevent ruff from re-ordering imports.
if True:
    from .types import ChoiceSource, EnumChoice

from .colorize import (
    ColorOption,
    HelpExtraFormatter,
    HelpExtraTheme,
)
from .commands import (
    ExtraCommand,
    ExtraContext,
    ExtraGroup,
    LazyGroup,
)
from .config import ConfigFormat, ConfigOption, NoConfigOption
from .decorators import (  # type: ignore[no-redef]
    argument,
    color_option,
    command,
    config_option,
    group,
    help_option,
    lazy_group,
    no_config_option,
    option,
    show_params_option,
    table_format_option,
    telemetry_option,
    timer_option,
    verbose_option,
    verbosity_option,
    version_option,
)
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
    search_params,
)
from .table import (
    TableFormat,
    TableFormatOption,
    print_table,
    render_table,
)
from .telemetry import TelemetryOption
from .testing import ExtraCliRunner
from .timer import TimerOption
from .version import ExtraVersionOption

__all__ = [  # noqa: F405
    "Abort",
    "annotations",
    "Argument",
    "argument",
    "BadArgumentUsage",
    "BadOptionUsage",
    "BadParameter",
    "BOOL",
    "Choice",
    "ChoiceSource",
    "clear",
    "ClickException",
    "Color",
    "color_option",
    "ColorOption",
    "Command",
    "command",
    "CommandCollection",
    "config_option",
    "ConfigFormat",
    "ConfigOption",
    "confirm",
    "confirmation_option",
    "constrained_params",
    "constraint",
    "ConstraintMixin",
    "Context",
    "DateTime",
    "dir_path",
    "echo",
    "echo_via_pager",
    "edit",
    "EnumChoice",
    "extraBasicConfig",
    "ExtraCliRunner",
    "ExtraCommand",
    "ExtraContext",
    "ExtraFormatter",
    "ExtraGroup",
    "ExtraOption",
    "ExtraStreamHandler",
    "ExtraVersionOption",
    "File",
    "file_path",
    "FileError",
    "FLOAT",
    "FloatRange",
    "format_filename",
    "get_app_dir",
    "get_binary_stream",
    "get_current_context",
    "get_text_stream",
    "getchar",
    "Group",
    "group",
    "help_option",
    "HelpExtraFormatter",
    "HelpExtraTheme",
    "HelpFormatter",
    "HelpSection",
    "HelpTheme",
    "INT",
    "IntRange",
    "launch",
    "lazy_group",
    "LazyGroup",
    "LogLevel",
    "make_pass_decorator",
    "MissingParameter",
    "new_extra_logger",
    "no_config_option",
    "NoConfigOption",
    "NoSuchOption",
    "open_file",
    "Option",
    "option",
    "option_group",
    "OptionGroup",
    "OptionGroupMixin",
    "Parameter",
    "ParameterSource",
    "ParamStructure",
    "ParamType",
    "pass_context",
    "pass_obj",
    "password_option",
    "Path",
    "path",
    "pause",
    "print_table",
    "progressbar",
    "prompt",
    "render_table",
    "search_params",
    "secho",
    "Section",
    "SectionMixin",
    "show_params_option",
    "ShowParamsOption",
    "STRING",
    "Style",
    "style",
    "table_format_option",
    "TableFormat",
    "TableFormatOption",
    "telemetry_option",
    "TelemetryOption",
    "timer_option",
    "TimerOption",
    "Tuple",
    "UNPROCESSED",
    "UNSET",
    "unstyle",
    "UsageError",
    "UUID",
    "verbose_option",
    "VerboseOption",
    "verbosity_option",
    "VerbosityOption",
    "version_option",
    "VersionOption",
    "warnings",
    "wrap_text",
]
"""Expose all of Click, Cloup and Click Extra.

.. note::
    The content of ``__all__`` is checked and enforced in unittests.

.. todo::
    Test ruff __all__ formatting capabilities. And if good enough, remove ``__all__``
    checks in unittests.
"""


__version__ = "7.4.0"


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
