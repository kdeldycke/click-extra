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

TYPE_CHECKING = False
# Mypy override: the `from click import *` / `from cloup import *` star imports
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

# Imported for its registration side effect: defining the module registers the
# `carapace` shell completion class (see click_extra.carapace.CarapaceComplete),
# so dynamic Carapace completion resolves in any CLI that imports click_extra.
from . import (
    carapace as carapace,
    context,
)
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
    CONFIG_PATH_METADATA_KEY,
    DEFAULT_SUBCOMMANDS_KEY,
    EXTENSION_METADATA_KEY,
    NO_CONFIG,
    NORMALIZE_KEYS_METADATA_KEY,
    PREPEND_SUBCOMMANDS_KEY,
    VCS,
    ConfigFormat,
    ConfigOption,
    ConfigValidator,
    ExportConfigOption,
    NoConfigOption,
    SchemaFieldInfo,
    ValidateConfigOption,
    ValidationError,
    ValidationReport,
    field_docstrings,
    flatten_config_keys,
    format_from_path,
    get_tool_config,
    make_schema_callable,
    normalize_config_keys,
    parse_content,
    read_file,
    run_config_validation,
    schema_field_infos,
    serialize_content,
)
from .context import Context, pass_context
from .decorators import (  # type: ignore[no-redef]
    accessible_option,
    argument,
    color_option,
    columns_option,
    command,
    config_option,
    export_config_option,
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
    tree_option,
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
    args_cleanup,
    format_cli_prompt,
    highlight_bin_name,
    install_interrupt_handler,
    resolve_jobs,
    run_cli,
    run_jobs,
    run_lanes,
    terminate_live_processes,
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
from .myst_converter import (
    convert_directory,
    convert_file,
    convert_source,
    detect_source_package,
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
from .rst_to_myst import (
    convert_apidoc_rst_to_myst,
    convert_rst_files_in_directory,
)
from .spinner import (  # type: ignore[no-redef]
    SPINNERS,
    OperationTrail,
    ProgressOption,
    Spinner,
    SpinnerPreset,
    progressbar,
)

# `Style` shadows the `cloup.Style` bound by the star import above with
# click-extra's enhanced subclass; relative imports always follow the cloup
# star import, so the override needs no special placement.
from .styling import (
    Style,
    ansi_to_html,
    ansi_to_jira,
    ansi_to_latex,
    ansi_to_textile,
    render_ansi,
    split_ansi,
)
from .table import (
    ColumnsOption,
    ColumnSpec,
    SortByOption,
    TableFormat,
    TableFormatOption,
    column_sort_key,
    print_data,
    print_table,
    render_columns_markdown_table,
    render_table,
    select_columns,
    select_row,
    serialize_data,
)
from .telemetry import TelemetryOption
from .test_suite import (
    DEFAULT_TEST_SUITE,
    SUITE_FORMATS,
    CLITestCase,
    SkippedTest,
    cases_from_data,
    load_test_suite,
    parse_test_suite,
    run_test_suite,
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
from .tree import TreeOption, render_command_tree
from .types import ChoiceSource, Duration, EnumChoice, MultiChoice
from .version import VersionOption

__all__ = [
    "BOOL",
    "BUILTIN_THEMES",
    "CONFIG_PATH_METADATA_KEY",
    "CPU_COUNT",
    "DEFAULT_JOBS",
    "DEFAULT_SUBCOMMANDS_KEY",
    "DEFAULT_TEST_SUITE",
    "EXTENSION_METADATA_KEY",
    "FLOAT",
    "INT",
    "NORMALIZE_KEYS_METADATA_KEY",
    "NO_CONFIG",
    "PREPEND_SUBCOMMANDS_KEY",
    "SPINNERS",
    "STRING",
    "SUITE_FORMATS",
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
    "Duration",
    "EnumChoice",
    "ExportConfigOption",
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
    "OperationTrail",
    "Option",
    "OptionGroup",
    "OptionGroupMixin",
    "ParamStructure",
    "ParamType",
    "Parameter",
    "ParameterSource",
    "Path",
    "ProgressOption",
    "QuietOption",
    "Result",
    "SchemaFieldInfo",
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
    "ThemeOption",
    "TimerOption",
    "TreeOption",
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
    "ansi_to_html",
    "ansi_to_jira",
    "ansi_to_latex",
    "ansi_to_textile",
    "args_cleanup",
    "argument",
    "basicConfig",
    "cases_from_data",
    "clear",
    "color_option",
    "column_sort_key",
    "columns_option",
    "command",
    "config_option",
    "confirm",
    "confirmation_option",
    "constrained_params",
    "constraint",
    "context",
    "convert_apidoc_rst_to_myst",
    "convert_directory",
    "convert_file",
    "convert_rst_files_in_directory",
    "convert_source",
    "detect_source_package",
    "dir_path",
    "echo",
    "echo_via_pager",
    "edit",
    "export_config_option",
    "field_docstrings",
    "file_path",
    "flatten_config_keys",
    "format_cli_prompt",
    "format_filename",
    "format_from_path",
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
    "highlight_bin_name",
    "install_interrupt_handler",
    "jobs_option",
    "last_param",
    "launch",
    "lazy_group",
    "load_test_suite",
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
    "parse_content",
    "parse_test_suite",
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
    "read_file",
    "register_theme",
    "render_ansi",
    "render_columns_markdown_table",
    "render_command_tree",
    "render_manpage",
    "render_manpages",
    "render_table",
    "require_sibling_param",
    "resolve_jobs",
    "run_cli",
    "run_config_validation",
    "run_jobs",
    "run_lanes",
    "run_test_suite",
    "schema_field_infos",
    "search_params",
    "secho",
    "select_columns",
    "select_row",
    "serialize_content",
    "serialize_data",
    "set_default_theme",
    "show_params_option",
    "sort_by_option",
    "split_ansi",
    "style",
    "table_format_option",
    "telemetry_option",
    "terminate_live_processes",
    "theme_option",
    "theme_registry",
    "timer_option",
    "tree_option",
    "unstyle",
    "validate_config_option",
    "verbose_option",
    "verbosity_option",
    "version_option",
    "wrap_text",
    "write_manpages",
    "zero_exit_option",
]
"""Expose all of Click, Cloup and Click Extra.

```{note}
The content of `__all__` is checked by a unittest and sorted by
`ruff` via [RUF022](https://docs.astral.sh/ruff/rules/unsorted-dunder-all/).
```
"""

# NoSuchCommand and get_pager_file are only re-exported on Click >= 8.4.0 (see the
# guarded import above). Drop them from the public API on older Click so `__all__`
# matches the names actually bound in this module.
if not _HAS_CLICK_8_4_EXPORTS:
    __all__.remove("NoSuchCommand")
    __all__.remove("get_pager_file")
del _HAS_CLICK_8_4_EXPORTS

# Scrub namespace artifacts that are not part of the public API: `annotations`
# is this module's own `from __future__ import annotations` binding (deleting
# it does not affect postponed evaluation, which is settled at compile time),
# and `warnings` is the stdlib module leaked through `from cloup import *`
# (cloup lists it in its `__all__`).
del annotations
del warnings  # noqa: F821


__version__ = "8.6.1.dev0"
__git_branch__ = ""
__git_date__ = ""
__git_long_hash__ = ""
__git_short_hash__ = ""
__git_tag__ = ""
__git_tag_sha__ = ""
