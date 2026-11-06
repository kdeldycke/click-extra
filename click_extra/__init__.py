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
"""Expose package-wide elements.

Importing this package is the startup cost of every CLI built on it, so the
dependencies a code path may never need (wcwidth, PyYAML, wcmatch and
extra-platforms) are imported where they are used, and
`tests/test_commands.py` checks that a hello-world `--help` loads none of them.

```{todo}
Drop `CLOUP_METADATA_PROBE_VERSION` from `tests/test_commands.py` once this
package's cloup floor is above `4.0.0`. That release is the last to import
`importlib.metadata` at module scope, which
[janluke/cloup#242](https://github.com/janluke/cloup/pull/242) removes. The
startup ballast list then names `importlib.metadata` and `email`
unconditionally.
```

```{todo}
Delete `_DEPRECATED_CLICK_EXPORTS`, the loop dropping its bindings and its
branch in `__getattr__` once the Click floor reaches `9.0`, which removes the
five names it forwards.
```

```{todo}
Delete `click_extra/blocks.py`, the deprecated alias of
`click_extra.markdown.blocks`, and its tests in `tests/test_blocks.py` in
`11.0.0`: its warnings announce that release.
```

```{todo}
Delete `_tile_runs`, `_TILE_RUN` and `_TILE_RE` from `click_extra/capture/svg.py`
in `11.0.0`, with the `__getattr__` serving them as `tile_runs`, `TILE_RUN` and
`_TILING_RE`, and their tests in `tests/test_screenshots.py`: its warnings
announce that release.
```
"""

from __future__ import annotations

TYPE_CHECKING = False
# Mypy override: the `from click import *` / `from cloup import *` star imports
# below make mypy resolve these re-implemented names to the click or cloup base class,
# which hides click-extra's own attributes. Declaring the correct types here first,
# before the star imports, makes mypy treat the later bindings as no-redefs and keeps
# click-extra's subclasses canonical for consumers of this package.
# The .capture, .markdown, .progress, .project, .test_suite, .testing and .trail
# entries have no runtime counterpart: those symbols are served lazily by the module
# __getattr__ hook at the bottom of this file, so this block is also what keeps
# them visible to type checkers.
if TYPE_CHECKING:
    from types import ModuleType
    from typing import Any

    from .capture.recording import record_command
    from .capture.screenshot import AUTO_WRAP_MARKER, resolve_wrap_marker
    from .capture.svg import AUTO_HOLD
    from .commands import Command, Context, Group
    from .context import pass_context
    from .highlight import HelpFormatter
    from .markdown.blocks import region_markers, replace_region
    from .markdown.myst import (
        convert_apidoc_rst_to_myst,
        convert_directory,
        convert_file,
        convert_rst_files_in_directory,
        convert_source,
    )
    from .parameters import Argument, Option
    from .progress import progressbar
    from .project import detect_source_package
    from .styling import Style
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
    from .theme import HelpTheme
    from .trail import OperationTrail, trail_line

import warnings

# Import all click's module-level content to allow for drop-in replacement.
# Mypy handles star imports poorly, reporting "Module 'X' has no attribute 'Y'":
# see https://github.com/python/mypy/issues/4930. The ignore mirrors the cloup
# star import below: the names pre-declared in the TYPE_CHECKING block above are
# re-implemented by click-extra, so click's originals arrive here as incompatible
# redefinitions.
from click import *  # type: ignore[assignment]
from click._utils import UNSET
from click.core import ParameterSource

# Overrides click helpers with cloup's. Cloup lists Click's deprecated names in its
# `__all__` and serves them through its own `__getattr__`, so this star import
# resolves each of them and Click warns: silence that here, then drop the bindings
# further down, where _DEPRECATED_CLICK_EXPORTS takes them over.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from cloup import *  # type: ignore[no-redef, assignment]

# Imported for its registration side effect: defining the module registers the
# `carapace` shell completion class (see click_extra.carapace.CarapaceComplete),
# so dynamic Carapace completion resolves in any CLI that imports click_extra.
from . import (
    carapace as carapace,
    context,
)
from .accessibility import AccessibleOption, clear, echo_via_pager
from .ansi import open_ansi, strip_ansi
from .carapace import get_cache_dir, xdg_dir
from .color import (
    COLOR_ENVVARS,
    ColorOption,
    NoColorOption,
    TerminalBackground,
    forced_color,
    invocation_color,
    is_a_tty,
    is_dumb_terminal,
    resolve_color_env,
)
from .columns import (
    ColumnSpec,
    render_columns_markdown_table,
    select_columns,
    select_row,
)
from .command_doc import (
    HELP_FORMATS,
    INSTALLABLE_FORMATS,
    CommandDoc,
    HelpFormat,
    HelpFormatOption,
    ManOption,
    format_manpage,
    install_manpages,
    read_manpage,
    render_help,
    render_manpage,
    render_manpages,
    strip_overstrike,
    write_manpages,
)
from .commands import (
    Command,
    Context,
    ExtraOptionGroup,
    Group,
    HelpCommand,
    LazyGroup,
    LazySubcommand,
    default_params,
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
    config_table_to_flags,
    field_docstrings,
    flatten_config_keys,
    format_from_mime,
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
from .context import pass_context
from .decorators import (  # type: ignore[no-redef]
    accessible_option,
    argument,
    color_option,
    columns_option,
    command,
    config_option,
    debug_option,
    export_config_option,
    group,
    help_format_option,
    help_option,
    jobs_option,
    lazy_group,
    man_option,
    multicall_group,
    no_color_option,
    no_config_option,
    option,
    progress_option,
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
from .envvar import env_copy, machine_envvars_apply
from .execution import (
    INDENT,
    TimerOption,
    ZeroExitOption,
    args_cleanup,
    format_cli_prompt,
    highlight_bin_name,
    install_interrupt_handler,
    run_cli,
    terminate_live_processes,
)
from .highlight import (
    HelpFormatter,
    HelpKeywords,
)
from .humanize import format_duration, format_size
from .jobs import (
    CPU_COUNT,
    DEFAULT_JOBS,
    JobsOption,
    resolve_jobs,
    run_jobs,
    run_lanes,
)
from .layout import cell_width, wrap_ansi
from .logging import (
    DebugOption,
    Formatter,
    LogLevel,
    QuietOption,
    StreamHandler,
    VerboseOption,
    VerbosityOption,
    basicConfig,
    new_logger,
)
from .multicall import MulticallGroup
from .output import (
    STDOUT_SENTINEL,
    MissingExtraError,
    force_unicode_output,
    is_stdout,
    prep_path,
)
from .param_tools import (
    ParamStructure,
    get_param_spec,
    last_param,
    require_sibling_param,
    search_params,
)
from .parameters import Argument, ExtraOption, Option
from .show_params import ShowParamsOption

# OperationTrail and progressbar are served lazily: see _LAZY_DISPLAYS.
from .spinner import ProgressOption, Spinner
from .spinner_presets import SPINNERS, SpinnerPreset

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
    AUTO_WIDTH,
    SERIALIZATION_FORMATS,
    TableFormat,
    corner_header,
    print_data,
    print_table,
    render_table,
    serialize_data,
)
from .table_options import (
    ColumnsOption,
    SortByOption,
    TableFormatOption,
    column_sort_key,
)
from .telemetry import TelemetryOption

# The test tooling (.testing, .test_suite) is deliberately NOT imported here:
# click_extra.testing imports click.testing, whose module-level `import pdb`
# drags asyncio and the _pyrepl machinery (Python 3.13+) into every program
# that merely imports click_extra. That debugger stack is pure dead weight in
# production CLIs, and Nuitka bundles it into every compiled binary. The
# symbols stay in __all__ and resolve on first access through the module
# __getattr__ hook below; see _LAZY_TEST_TOOLING.
from .theme import (
    BUILTIN_THEMES,
    KO_GLYPH,
    OK_GLYPH,
    HelpTheme,
    ThemeOption,
    get_current_theme,
    get_default_theme,
    register_theme,
    set_default_theme,
    theme_registry,
)
from .tree import TreeOption, render_command_tree
from .types import (
    ChoiceSource,
    Duration,
    EnumChoice,
    LazyChoice,
    MultiChoice,
    parse_duration,
    parse_friendly_duration,
    parse_iso8601_duration,
)
from .version import VersionOption, VersionScreen
from .version_facts import default_facts, env_summary

__all__ = [
    "AUTO_HOLD",
    "AUTO_WIDTH",
    "AUTO_WRAP_MARKER",
    "BOOL",
    "BUILTIN_THEMES",
    "COLOR_ENVVARS",
    "CONFIG_PATH_METADATA_KEY",
    "CPU_COUNT",
    "DEFAULT_JOBS",
    "DEFAULT_SUBCOMMANDS_KEY",
    "DEFAULT_TEST_SUITE",
    "EXTENSION_METADATA_KEY",
    "FLOAT",
    "HELP_FORMATS",
    "INDENT",
    "INSTALLABLE_FORMATS",
    "INT",
    "KO_GLYPH",
    "NORMALIZE_KEYS_METADATA_KEY",
    "NO_CONFIG",
    "OK_GLYPH",
    "PREPEND_SUBCOMMANDS_KEY",
    "SERIALIZATION_FORMATS",
    "SPINNERS",
    "STDOUT_SENTINEL",
    "STRING",
    "SUITE_FORMATS",
    "UNPROCESSED",
    "UNSET",
    "UUID",
    "VCS",
    "Abort",
    "AccessibleOption",
    "Argument",
    "ArgumentKwargs",
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
    "CommandDoc",
    "ConfigFormat",
    "ConfigOption",
    "ConfigValidator",
    "ConstraintMixin",
    "Context",
    "DateTime",
    "DebugOption",
    "Duration",
    "EnumChoice",
    "ExportConfigOption",
    "ExtraOption",
    "ExtraOptionGroup",
    "File",
    "FileError",
    "FloatRange",
    "Formatter",
    "Group",
    "HelpCommand",
    "HelpFormat",
    "HelpFormatOption",
    "HelpFormatter",
    "HelpKeywords",
    "HelpSection",
    "HelpTheme",
    "IntRange",
    "JobsOption",
    "LazyChoice",
    "LazyGroup",
    "LazySubcommand",
    "LogLevel",
    "ManOption",
    "MissingExtraError",
    "MissingParameter",
    "MultiChoice",
    "MulticallGroup",
    "NoColorOption",
    "NoConfigOption",
    "NoSuchCommand",
    "NoSuchOption",
    "OperationTrail",
    "Option",
    "OptionGroup",
    "OptionGroupMixin",
    "OptionKwargs",
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
    "TerminalBackground",
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
    "VersionScreen",
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
    "cell_width",
    "clear",
    "color_option",
    "column_sort_key",
    "columns_option",
    "command",
    "config_option",
    "config_table_to_flags",
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
    "corner_header",
    "custom_version_option",
    "debug_option",
    "default_facts",
    "default_params",
    "detect_source_package",
    "dir_path",
    "echo",
    "echo_via_pager",
    "edit",
    "env_copy",
    "env_summary",
    "export_config_option",
    "field_docstrings",
    "file_path",
    "flatten_config_keys",
    "force_unicode_output",
    "forced_color",
    "format_cli_prompt",
    "format_duration",
    "format_filename",
    "format_from_mime",
    "format_from_path",
    "format_manpage",
    "format_size",
    "get_app_dir",
    "get_cache_dir",
    "get_current_context",
    "get_current_theme",
    "get_default_theme",
    "get_pager_file",
    "get_param_spec",
    "get_tool_config",
    "getchar",
    "group",
    "help_format_option",
    "help_option",
    "highlight_bin_name",
    "install_interrupt_handler",
    "install_manpages",
    "invocation_color",
    "is_a_tty",
    "is_dumb_terminal",
    "is_stdout",
    "jobs_option",
    "last_param",
    "launch",
    "lazy_group",
    "load_test_suite",
    "machine_envvars_apply",
    "make_pass_decorator",
    "make_schema_callable",
    "man_option",
    "multicall_group",
    "new_logger",
    "no_color_option",
    "no_config_option",
    "normalize_config_keys",
    "open_ansi",
    "open_file",
    "option",
    "option_group",
    "parse_content",
    "parse_duration",
    "parse_friendly_duration",
    "parse_iso8601_duration",
    "parse_test_suite",
    "pass_context",
    "pass_obj",
    "password_option",
    "path",
    "pause",
    "prep_path",
    "print_data",
    "print_table",
    "progress_option",
    "progressbar",
    "prompt",
    "quiet_option",
    "read_file",
    "read_manpage",
    "record_command",
    "region_markers",
    "register_theme",
    "render_ansi",
    "render_columns_markdown_table",
    "render_command_tree",
    "render_help",
    "render_manpage",
    "render_manpages",
    "render_table",
    "replace_region",
    "require_sibling_param",
    "resolve_color_env",
    "resolve_jobs",
    "resolve_wrap_marker",
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
    "strip_ansi",
    "strip_overstrike",
    "style",
    "table_format_option",
    "telemetry_option",
    "terminate_live_processes",
    "theme_option",
    "theme_registry",
    "timer_option",
    "trail_line",
    "tree_option",
    "unstyle",
    "validate_config_option",
    "verbose_option",
    "verbosity_option",
    "version_option",
    "wrap_ansi",
    "wrap_text",
    "write_manpages",
    "xdg_dir",
    "zero_exit_option",
]
"""Expose all of Click, Cloup and Click Extra.

```{note}
The content of `__all__` is checked for completeness by unittests: it covers
click's and cloup's public members, every public binding of this namespace is
declared here, every declared name resolves, and no foreign module leaks in.
Sorting is enforced by `ruff` via
[RUF022](https://docs.astral.sh/ruff/rules/unsorted-dunder-all/).
```
"""

# Scrub namespace artifacts that are not part of the public API: `annotations`
# is this module's own `from __future__ import annotations` binding (deleting
# it does not affect postponed evaluation, which is settled at compile time).
del annotations


def _scrub_foreign_modules() -> None:
    """Drop the module objects the imports above leaked into this namespace.

    click ships no `__all__`, so `from click import *` copies every submodule
    its own `__init__` binds (`click.core`, `click.globals`, `click.termui`,
    ...). These bindings are traps: `click_extra.core.Group` would resolve to
    click's original class instead of click-extra's override, and `globals`
    even shadows the builtin. The stdlib `warnings` module this file imports
    goes the same way. The package's genuine submodules, bound by the relative
    imports above, are kept. A unittest checks none of this regresses.
    """
    # Imported here, so no `ModuleType` binding joins the public namespace. The
    # namespace is read through `sys.modules`: until this scrub, `globals` names
    # the `click.globals` module the star import bound, not the builtin.
    import sys
    from types import ModuleType

    namespace = vars(sys.modules[__name__])
    for name in [
        module_id
        for module_id, value in namespace.items()
        if isinstance(value, ModuleType)
        and not value.__name__.startswith(f"{__name__}.")
    ]:
        del namespace[name]


_scrub_foreign_modules()
del _scrub_foreign_modules


__version__ = "10.2.0.dev0"
__git_branch__ = ""
__git_date__ = ""
__git_long_hash__ = ""
__git_short_hash__ = ""
__git_tag__ = ""
__git_tag_sha__ = ""


_LAZY_TEST_TOOLING = {
    "CLITestCase": "test_suite",
    "CliRunner": "testing",
    "DEFAULT_TEST_SUITE": "test_suite",
    "Result": "testing",
    "SUITE_FORMATS": "test_suite",
    "SkippedTest": "test_suite",
    "cases_from_data": "test_suite",
    "load_test_suite": "test_suite",
    "parse_test_suite": "test_suite",
    "run_test_suite": "test_suite",
}
"""Test-tooling symbols served lazily by `__getattr__`, keyed to their module.

Keeps `import click_extra` free of `click.testing` and the pdb/asyncio/_pyrepl
debugger stack it pulls in (see the note above the `.theme` import). The names
remain listed in `__all__`: plain attribute access and
`from click_extra import ...` resolve them on first use, and a star-import
materializes them all, at the cost of loading the test tooling.
"""


_LAZY_CONVERTERS = {
    "convert_apidoc_rst_to_myst": "markdown.myst",
    "convert_directory": "markdown.myst",
    "convert_file": "markdown.myst",
    "convert_rst_files_in_directory": "markdown.myst",
    "convert_source": "markdown.myst",
    "detect_source_package": "project",
    "region_markers": "markdown.blocks",
    "replace_region": "markdown.blocks",
}
"""Converter symbols served lazily by `__getattr__`, keyed to their module.

The reST-to-MyST converters and the Markdown region helpers are documentation
tooling, which a CLI built on click-extra seldom runs: serving them lazily keeps
{mod}`click_extra.markdown` and {mod}`click_extra.project` off the startup path,
the way {data}`_LAZY_TEST_TOOLING` keeps the test tooling off it.
"""

_LAZY_CAPTURES = {
    "AUTO_HOLD": "capture.svg",
    "AUTO_WRAP_MARKER": "capture.screenshot",
    "record_command": "capture.recording",
    "resolve_wrap_marker": "capture.screenshot",
}
"""Capture symbols served lazily by `__getattr__`, keyed to their module.

Drawing a command's output as a picture is documentation tooling too: serving
these lazily keeps {mod}`click_extra.capture` off the startup path.
"""

_LAZY_DISPLAYS = {
    "OperationTrail": "trail",
    "progressbar": "progress",
    "trail_line": "trail",
}
"""Live-display symbols served lazily by `__getattr__`, keyed to their module.

Keeps {mod}`click_extra.trail` and {mod}`click_extra.progress` off
`import click_extra`: only a CLI that draws a trail or a determinate bar loads
them. Click's own `progressbar`, which the star import binds, is dropped right
below, so the name reaches the hook and resolves to Click Extra's drop-in.
"""

for _name in _LAZY_DISPLAYS:
    globals().pop(_name, None)


_DEPRECATED_CLICK_EXPORTS = frozenset({
    "BaseCommand",
    "MultiCommand",
    "OptionParser",
    "get_binary_stream",
    "get_text_stream",
})
"""Click symbols deprecated for removal in Click `9.0`, forwarded on access instead.

Click serves these only through its own module `__getattr__`, which warns on
access. A star import never consults that hook, so `from click import *` binds
none of them, and `__all__` declares none of them either: a star import of
click-extra would otherwise fetch each one and set off the warning. Cloup lists
all five in its own `__all__`, whose star import resolves each one: the bindings
it leaves are deleted right below. Forwarding each access keeps click-extra a
drop-in for as long as Click serves them, and warns exactly when Click does: the
value is never cached, so every access reaches Click's shim.
"""

for _name in _DEPRECATED_CLICK_EXPORTS:
    globals().pop(_name, None)
del _name


def _lazy_module(path: str) -> ModuleType:
    """Import the module a lazy name lives in, by an import statement of its own.

    ```{note}
    Nuitka bundles what a live import statement names: it drops the
    `TYPE_CHECKING` block above as dead code, and cannot follow a computed
    `import_module()` call. Spelling out each import keeps these modules in a
    binary built on click-extra, and each one still loads on the first access
    to one of its names only.
    ```
    """
    match path:
        case "capture.recording":
            from .capture import recording

            return recording
        case "capture.screenshot":
            from .capture import screenshot

            return screenshot
        case "capture.svg":
            from .capture import svg

            return svg
        case "markdown.blocks":
            from .markdown import blocks

            return blocks
        case "markdown.myst":
            from .markdown import myst

            return myst
        case "progress":
            from . import progress

            return progress
        case "project":
            from . import project

            return project
        case "test_suite":
            from . import test_suite

            return test_suite
        case "testing":
            from . import testing

            return testing
        case "trail":
            from . import trail

            return trail
        case _:
            raise ModuleNotFoundError(f"No module named '{__name__}.{path}'")


def __getattr__(name: str) -> Any:
    """Resolve lazy top-level symbols via PEP 562.

    Names registered in {data}`_LAZY_TEST_TOOLING`, {data}`_LAZY_CONVERTERS`,
    {data}`_LAZY_CAPTURES` and {data}`_LAZY_DISPLAYS`
    are imported from their hosting module on first access, then cached in the
    module namespace so later accesses bypass this hook. Names in
    {data}`_DEPRECATED_CLICK_EXPORTS` are forwarded to Click on every access,
    uncached. Fires only for names not defined in this module, so live exports
    stay zero-overhead.
    """
    if name in _DEPRECATED_CLICK_EXPORTS:
        # Imported here rather than at module level: the star imports above bind
        # no `click` name, and _scrub_foreign_modules() would drop one anyway.
        import click

        # Never cached, so each access reaches Click's own deprecation shim.
        return getattr(click, name)

    lazy_module = (
        _LAZY_TEST_TOOLING.get(name)
        or _LAZY_CONVERTERS.get(name)
        or _LAZY_CAPTURES.get(name)
        or _LAZY_DISPLAYS.get(name)
    )
    if lazy_module:
        value = getattr(_lazy_module(lazy_module), name)
        # Cache the symbol on the module so later accesses bypass this hook.
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Expose every name `__getattr__` serves to `dir()` before its first access."""
    return sorted(
        set(globals())
        | set(_LAZY_TEST_TOOLING)
        | set(_LAZY_CONVERTERS)
        | set(_LAZY_CAPTURES)
        | set(_LAZY_DISPLAYS)
        | _DEPRECATED_CLICK_EXPORTS
    )
