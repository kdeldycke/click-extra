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

from typing import TYPE_CHECKING

# Mypy override: the ``from click import *`` / ``from cloup import *`` star imports
# below make mypy resolve these re-implemented names to the click or cloup base class,
# which hides click-extra's own attributes. Declaring the correct types here first,
# before the star imports, makes mypy treat the later bindings as no-redefs and keeps
# click-extra's subclasses canonical for consumers of this package.
if TYPE_CHECKING:
    from .commands import Command, Group
    from .context import Context, pass_context
    from .highlight import HelpFormatter
    from .parameters import Argument, Option
    from .styling import Style
    from .theme import HelpTheme

# Import all click's module-level content to allow for drop-in replacement.
# XXX Star import is really badly supported by mypy for now and leads to lots of
# "Module 'XXX' has no attribute 'YYY'". See: https://github.com/python/mypy/issues/4930
# The ignore mirrors the cloup star import below: the names pre-declared in the
# TYPE_CHECKING block above are re-implemented by click-extra, so click's originals
# arrive here as incompatible redefinitions.
from click import *  # type: ignore[assignment]
from click._utils import UNSET
from click.core import ParameterSource

# NoSuchCommand (PR pallets/click#3228) and get_pager_file (PR pallets/click#1572)
# are Click 8.4.0 additions, absent on the Click 8.3.x releases click-extra still
# supports. Import them only when present so click-extra mirrors Click's own public
# surface; the matching __all__ entries are trimmed below when they are missing.
try:
    from click import NoSuchCommand, get_pager_file

    _HAS_CLICK_8_4_EXPORTS = True
except ImportError:  # Click < 8.4.0.
    _HAS_CLICK_8_4_EXPORTS = False

# Overrides click helpers with cloup's.
from cloup import *  # type: ignore[no-redef, assignment]

# XXX Import types first to avoid circular imports. The True condition is a hack to
# prevent ruff from re-ordering imports.
if True:
    from .types import ChoiceSource, EnumChoice, MultiChoice

# Override cloup.Style with our own version. The override must happen after
# ``from cloup import *`` (which would otherwise re-shadow our subclass) and
# before any module that does ``from . import Style`` is loaded (parameters,
# version, testing all do).
from . import styling as _styling_module

Style = _styling_module.Style  # type: ignore[misc]
del _styling_module

from . import context
from .accessibility import AccessibleOption, clear, echo_via_pager
from .color import (
    ColorOption,
    NoColorOption,
)
from .commands import (
    Command,
    Group,
    HelpCommand,
    LazyGroup,
)
from .config import (
    DEFAULT_SUBCOMMANDS_KEY,
    EXTENSION_METADATA_KEY,
    NO_CONFIG,
    PREPEND_SUBCOMMANDS_KEY,
    VCS,
    ClickExtraConfig,
    ConfigFormat,
    ConfigOption,
    ConfigValidator,
    NoConfigOption,
    PrebakeConfig,
    TestPlanConfig,
    ValidateConfigOption,
    ValidationError,
    ValidationReport,
    flatten_config_keys,
    get_tool_config,
    make_schema_callable,
    normalize_config_keys,
    run_config_validation,
)
from .context import Context, pass_context
from .decorators import (  # type: ignore[no-redef]
    accessible_option,
    argument,
    color_option,
    columns_option,
    command,
    config_option,
    group,
    help_option,
    jobs_option,
    lazy_group,
    man_option,
    no_color_option,
    no_config_option,
    option,
    quiet_option,
    show_params_option,
    sort_by_option,
    table_format_option,
    telemetry_option,
    theme_option,
    timer_option,
    validate_config_option,
    verbose_option,
    verbosity_option,
    version_option,
    zero_exit_option,
)
from .execution import (
    CPU_COUNT,
    DEFAULT_JOBS,
    JobsOption,
    TimerOption,
    ZeroExitOption,
    run_jobs,
)
from .highlight import (
    HelpFormatter,
    HelpKeywords,
)
from .logging import (
    Formatter,
    LogLevel,
    QuietOption,
    StreamHandler,
    VerboseOption,
    VerbosityOption,
    basicConfig,
    new_logger,
)
from .man_page import (
    ManOption,
    ManPage,
    render_manpage,
    render_manpages,
    write_manpages,
)
from .parameters import (
    Argument,
    ExtraOption,
    Option,
    ParamStructure,
    ShowParamsOption,
    format_param_row,
    get_param_spec,
    last_param,
    require_sibling_param,
    search_params,
)
from .spinner import (  # type: ignore[no-redef]
    SPINNERS,
    ProgressOption,
    Spinner,
    SpinnerPreset,
    progressbar,
)
from .table import (
    ColumnsOption,
    ColumnSpec,
    SortByOption,
    TableFormat,
    TableFormatOption,
    print_data,
    print_table,
    render_columns_markdown_table,
    render_table,
    select_columns,
    select_row,
    serialize_data,
)
from .telemetry import TelemetryOption
from .test_plan import (
    DEFAULT_TEST_PLAN,
    PLAN_FORMATS,
    CLITestCase,
    SkippedTest,
    load_test_plan,
    parse_test_plan,
    run_test_plan,
)
from .testing import CliRunner, Result
from .theme import (
    BUILTIN_THEMES,
    HelpTheme,
    ThemeOption,
    get_current_theme,
    get_default_theme,
    register_theme,
    set_default_theme,
    theme_registry,
)
from .version import VersionOption

__all__ = [
    "BOOL",
    "BUILTIN_THEMES",
    "CPU_COUNT",
    "DEFAULT_JOBS",
    "DEFAULT_SUBCOMMANDS_KEY",
    "DEFAULT_TEST_PLAN",
    "EXTENSION_METADATA_KEY",
    "FLOAT",
    "INT",
    "NO_CONFIG",
    "PLAN_FORMATS",
    "PREPEND_SUBCOMMANDS_KEY",
    "SPINNERS",
    "STRING",
    "UNPROCESSED",
    "UNSET",
    "UUID",
    "VCS",
    "Abort",
    "AccessibleOption",
    "Argument",
    "BadArgumentUsage",
    "BadOptionUsage",
    "BadParameter",
    "CLITestCase",
    "Choice",
    "ChoiceSource",
    "CliRunner",
    "ClickException",
    "ClickExtraConfig",
    "Color",
    "ColorOption",
    "ColumnSpec",
    "ColumnsOption",
    "Command",
    "CommandCollection",
    "ConfigFormat",
    "ConfigOption",
    "ConfigValidator",
    "ConstraintMixin",
    "Context",
    "DateTime",
    "EnumChoice",
    "ExtraOption",
    "File",
    "FileError",
    "FloatRange",
    "Formatter",
    "Group",
    "HelpCommand",
    "HelpFormatter",
    "HelpKeywords",
    "HelpSection",
    "HelpTheme",
    "IntRange",
    "JobsOption",
    "LazyGroup",
    "LogLevel",
    "ManOption",
    "ManPage",
    "MissingParameter",
    "MultiChoice",
    "NoColorOption",
    "NoConfigOption",
    "NoSuchCommand",
    "NoSuchOption",
    "Option",
    "OptionGroup",
    "OptionGroupMixin",
    "ParamStructure",
    "ParamType",
    "Parameter",
    "ParameterSource",
    "Path",
    "PrebakeConfig",
    "ProgressOption",
    "QuietOption",
    "Result",
    "Section",
    "SectionMixin",
    "ShowParamsOption",
    "SkippedTest",
    "SortByOption",
    "Spinner",
    "SpinnerPreset",
    "StreamHandler",
    "Style",
    "TableFormat",
    "TableFormatOption",
    "TelemetryOption",
    "TestPlanConfig",
    "ThemeOption",
    "TimerOption",
    "Tuple",
    "UsageError",
    "ValidateConfigOption",
    "ValidationError",
    "ValidationReport",
    "VerboseOption",
    "VerbosityOption",
    "VersionOption",
    "ZeroExitOption",
    "accessible_option",
    "annotations",
    "argument",
    "basicConfig",
    "clear",
    "color_option",
    "columns_option",
    "command",
    "config_option",
    "confirm",
    "confirmation_option",
    "constrained_params",
    "constraint",
    "context",
    "dir_path",
    "echo",
    "echo_via_pager",
    "edit",
    "file_path",
    "flatten_config_keys",
    "format_filename",
    "format_param_row",
    "get_app_dir",
    "get_binary_stream",
    "get_current_context",
    "get_current_theme",
    "get_default_theme",
    "get_pager_file",
    "get_param_spec",
    "get_text_stream",
    "get_tool_config",
    "getchar",
    "group",
    "help_option",
    "jobs_option",
    "last_param",
    "launch",
    "lazy_group",
    "load_test_plan",
    "make_pass_decorator",
    "make_schema_callable",
    "man_option",
    "new_logger",
    "no_color_option",
    "no_config_option",
    "normalize_config_keys",
    "open_file",
    "option",
    "option_group",
    "parse_test_plan",
    "pass_context",
    "pass_obj",
    "password_option",
    "path",
    "pause",
    "print_data",
    "print_table",
    "progressbar",
    "prompt",
    "quiet_option",
    "register_theme",
    "render_columns_markdown_table",
    "render_manpage",
    "render_manpages",
    "render_table",
    "require_sibling_param",
    "run_config_validation",
    "run_jobs",
    "run_test_plan",
    "search_params",
    "secho",
    "select_columns",
    "select_row",
    "serialize_data",
    "set_default_theme",
    "show_params_option",
    "sort_by_option",
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
    "write_manpages",
    "zero_exit_option",
]
"""Expose all of Click, Cloup and Click Extra.

.. note::
    The content of ``__all__`` is checked by a unittest and sorted by
    ``ruff`` via `RUF022 <https://docs.astral.sh/ruff/rules/unsorted-dunder-all/>`_.
"""

# NoSuchCommand and get_pager_file are only re-exported on Click >= 8.4.0 (see the
# guarded import above). Drop them from the public API on older Click so ``__all__``
# matches the names actually bound in this module.
if not _HAS_CLICK_8_4_EXPORTS:
    __all__.remove("NoSuchCommand")
    __all__.remove("get_pager_file")
del _HAS_CLICK_8_4_EXPORTS


__version__ = "8.1.0.dev0"
__git_branch__ = ""
__git_date__ = ""
__git_long_hash__ = ""
__git_short_hash__ = ""
__git_tag__ = ""
__git_tag_sha__ = ""
