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
"""The `click-extra wrap` command and the machinery to wrap a foreign Click CLI.

Monkey-patches Click's decorator functions before importing (or running) a
target module so its `@click.command()` / `@click.group()` produce
colorized, keyword-highlighted, themed variants. Also resolves and invokes the
target, and introspects it for `--params`, `--man`, `--tree` and `--help-format`
without firing its callbacks.

Not to be confused with text wrapping: that is {func}`click.wrap_text`, exposed
at the package root as `click_extra.wrap_text`.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import runpy
import shlex
import sys
from pathlib import Path

import click
import cloup
from click.core import ParameterSource
from click.utils import make_str

from . import context
from ._utils import console_script
from .carapace import (
    dump_carapace_spec,
    install_carapace_spec,
    write_carapace_spec,
)
from .command_doc import (
    INSTALLABLE_FORMATS,
    HelpFormat,
    install_manpages,
    read_manpage,
    render_help,
    write_manpages,
)
from .commands import ColorizedCommand, ColorizedGroup, Context, LazyGroup
from .config.flags import config_table_to_flags
from .decorators import columns_option, option
from .highlight import HelpFormatter, HelpKeywords, _HelpColorsMixin
from .param_tools import child_context, make_resilient_context
from .project import resolve_entry_point
from .show_params import ShowParamsOption, render_params_table
from .table import TableFormat
from .table_options import TableFormatOption
from .theme import (
    HelpTheme,
    get_current_theme,
    get_default_theme,
    set_default_theme,
)
from .tree import render_command_tree
from .types import EnumChoice

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType
    from typing import Any

logger = logging.getLogger(__name__)

# Save pristine references before any patching occurs.
_original_click_command = click.decorators.command
_original_click_group = click.decorators.group
_original_get_help = click.Command.get_help
_original_format_help = click.Command.format_help

_theme_before_patch: HelpTheme | None = None
"""The process-wide default theme a {func}`patch_click` call replaced.

`None` while no call replaced it: {func}`unpatch_click` then keeps the default
as it is.
"""


class WrapperGroup(LazyGroup):
    """Group that falls back to the `wrap` subcommand for unknown names.

    Known subcommands and their aliases are dispatched normally, the lazy ones
    included. Anything else is treated as a target script and forwarded to `wrap`.
    """

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        cmd_name = make_str(args[0])
        # Cloup's resolve_command_name handles both direct names and aliases, but
        # knows only the subcommands registered so far: a lazy one not imported
        # yet answers to its name alone.
        resolved = super().resolve_command_name(ctx, cmd_name)
        if resolved is None and cmd_name in self.lazy_subcommands:
            resolved = cmd_name
        if resolved is not None:
            cmd = self.get_command(ctx, resolved)
            if cmd is not None:
                return cmd_name, cmd, args[1:]
        # Unknown name: delegate the entire arg list to `wrap`.
        wrap_cmd = self.get_command(ctx, "wrap")
        if wrap_cmd is not None:
            return "wrap", wrap_cmd, args
        return super().resolve_command(ctx, args)


def _make_patched_decorator(
    original: Callable[..., Any],
    default_cls: type[click.Command],
) -> Callable[..., Any]:
    """Build a drop-in replacement for `click.command` / `click.group`.

    The returned wrapper defaults its `cls` to `default_cls` (a colorized
    variant) while forwarding to `original`. It handles both the parenthesized
    form (`@command(...)`) and the bare form (`@command`), where the decorated
    function arrives as the first positional `name` argument.
    """

    def _patched(name=None, cls=None, **attrs):
        cls = cls or default_cls
        # Handle bare usage (no parentheses): the decorated function is passed as
        # the first positional argument.
        if callable(name):
            return original(cls=cls, **attrs)(name)
        return original(name=name, cls=cls, **attrs)

    return _patched


def patch_click(
    theme: HelpTheme | None = None,
    color: bool | None = True,
) -> None:
    """Replace Click's decorator functions with colorized variants.

    Must be called before importing the target CLI module so that
    `@click.command()` and `@click.group()` decorators produce colorized
    commands.

    ```{note}
    Only the decorator functions are replaced, not the class names
    (`click.Command`, `click.Group`). Replacing class names would
    break `isinstance` and `issubclass` checks in Click internals
    (`_param_memo`) and Cloup's decorator validators.
    ```

    ```{note}
    A decided *color* (anything but `None`) is pinned in two places, because the
    two kinds of target are colorized by different routes. One built with a plain
    `@click.command()` picks up the patched decorator and therefore *is* a
    `_HelpColorsMixin`: the context class installed below carries the decision for
    it. One carrying an explicit `cls=` (like Flask's `FlaskGroup`) keeps its own
    class and a stock `click.Context`, and is served by the `get_help` patch
    further down instead. Cover a single route and the flag silently works for
    half the CLIs in the wild.
    ```

    :param theme: Color theme to use, as the process-wide default. `None` keeps
        the current default. {func}`unpatch_click` gives back the default this
        replaced.
    :param color: Tri-state ANSI control mirroring `ctx.color`: `True` forces
        colors on, `False` strips them, and `None` (the GNU `auto` default)
        defers to the output stream's TTY status.
    """
    global _theme_before_patch

    if color is None:
        ColorizedCommand.context_class = Context
        ColorizedGroup.context_class = Context
    else:

        class _PinnedColorContext(Context):
            """Context variant pinning the caller's colorization decision."""

            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                # Pin the decision on a root context, overriding the auto default
                # Context would otherwise resolve from the environment.
                if not self.parent:
                    self.color = color

        ColorizedCommand.context_class = _PinnedColorContext
        ColorizedGroup.context_class = _PinnedColorContext

    _patched_command_func = _make_patched_decorator(
        _original_click_command, ColorizedCommand
    )
    _patched_group_func = _make_patched_decorator(_original_click_group, ColorizedGroup)

    # Replace decorator functions in both namespaces so both `click.command`
    # and `from click.decorators import command` resolve to the wrappers.
    click.command = _patched_command_func
    click.group = _patched_group_func
    click.decorators.command = _patched_command_func
    click.decorators.group = _patched_group_func
    logger.debug("Patched click.command and click.group decorators.")

    # Patch Command methods to colorize ALL commands, including those with
    # explicit `cls=` (like Flask's `FlaskGroup`). Commands that already
    # have `_HelpColorsMixin` skip this path to avoid double-processing: the
    # context class installed above is what carries the color decision to them.
    def _patched_get_help(self, ctx):
        if not isinstance(self, _HelpColorsMixin):
            ctx.formatter_class = HelpFormatter
            if not ctx.parent and ctx.color is None:
                ctx.color = color
        return _original_get_help(self, ctx)

    def _patched_format_help(self, ctx, formatter):
        if isinstance(formatter, HelpFormatter) and not isinstance(
            self, _HelpColorsMixin
        ):
            logger.debug(
                "Collecting keywords for %s (%s).",
                type(self).__name__,
                self.name,
            )
            # collect_keywords() works on any command: its static methods are
            # class-qualified and it reads extra_keywords with a default.
            formatter.keywords = _HelpColorsMixin.collect_keywords(self, ctx)
            formatter.excluded_keywords = _HelpColorsMixin._collect_excluded_keywords(
                ctx
            )
        _original_format_help(self, ctx, formatter)

    click.Command.get_help = _patched_get_help  # type: ignore[method-assign]
    click.Command.format_help = _patched_format_help  # type: ignore[method-assign]
    logger.debug("Patched click.Command.get_help and format_help methods.")

    # Override the default theme if requested. Only the first override saves the
    # default it replaces: unpatch_click() goes back to the state before any patch.
    if theme is not None:
        if _theme_before_patch is None:
            _theme_before_patch = get_default_theme()
        set_default_theme(theme)

    logger.info(
        "Click patched: color=%s, theme=%s.",
        color,
        type(theme).__name__ if theme is not None else "default",
    )


def unpatch_click() -> None:
    """Restore Click's original decorator functions and methods.

    Reverses the changes made by {func}`patch_click`. Useful in tests to
    avoid leaking global state between test cases.

    The process-wide default theme goes back to the one in place before the
    first {func}`patch_click` call that set a theme. If no call set one, the
    default stays as it is, so a {func}`~click_extra.theme.set_default_theme`
    call made while patched is kept.
    """
    global _theme_before_patch

    click.command = _original_click_command
    click.group = _original_click_group
    click.decorators.command = _original_click_command
    click.decorators.group = _original_click_group
    click.Command.get_help = _original_get_help  # type: ignore[method-assign]
    click.Command.format_help = _original_format_help  # type: ignore[method-assign]
    ColorizedCommand.context_class = Context
    ColorizedGroup.context_class = Context
    if _theme_before_patch is not None:
        set_default_theme(_theme_before_patch)
        _theme_before_patch = None


def _resolve_project_dir(directory: Path) -> tuple[str, str, Path]:
    """Resolve a local project directory to an importable target.

    Reads the project's console-script entry point from its packaging metadata,
    with {func}`~click_extra.project.resolve_entry_point`, which also locates
    the top-level package on disk, so it can be imported without an install
    step. This lets `wrap` target a checked-out project by its directory, the
    way an editable install plus its console script would.

    :return: `(module_path, function_name, syspath_entry)`. *syspath_entry*
        is the directory to prepend to `sys.path` so *module_path* resolves.
    :raises click.ClickException: when no entry point can be determined, or the
        package backing it cannot be found on disk.
    """
    try:
        entry_point = resolve_entry_point(directory)
    except ValueError as error:
        raise click.ClickException(
            f"{error} Pass the target explicitly as module:function."
        ) from error

    if entry_point.root is None:
        raise click.ClickException(
            f"Found entry point {entry_point.target!r} in {directory}, but its "
            f"top-level package {entry_point.package!r} is not under {directory} "
            f"or {directory / 'src'}."
        )
    return entry_point.module, entry_point.function, entry_point.root


def resolve_target(script: str) -> tuple[str, str]:
    """Resolve a script name to a module path and function name.

    Resolution order:

    1. `console_scripts` entry points from installed packages.
    2. A local project directory: its `console_scripts` entry point is read
       from `pyproject.toml` / `setup.cfg` and its package is added to
       `sys.path`.
    3. `.py` file path.
    4. Explicit `module:function` notation.
    5. Bare Python module or package name.

    :return: `(module_path, function_name)` tuple. *function_name* is
        empty when the target should be invoked as a module or script file.
    :raises click.ClickException: If the script cannot be resolved.

    ```{note}
    Resolving a local project directory has a side effect: the directory
    holding its top-level package is prepended to `sys.path` so the
    subsequent import succeeds. The target's own dependencies must still be
    importable in the current environment.
    ```
    """
    logger.debug("Resolving target %r.", script)

    # 1. Console scripts entry points.
    entry_point = console_script(script)
    if entry_point is not None:
        logger.info(
            "Resolved %r as console_scripts entry point: %s:%s.",
            script,
            entry_point.module,
            entry_point.attr,
        )
        return entry_point.module, entry_point.attr

    # 2. Local project directory: discover its console-script entry point and
    # make its package importable. Checked before the path/module heuristics so
    # a real directory on disk is never mistaken for module:function notation or
    # a bare module name.
    script_path = Path(script)
    if script and script_path.is_dir():
        module_path, function_name, syspath_entry = _resolve_project_dir(script_path)
        entry_str = str(syspath_entry.resolve())
        if entry_str not in sys.path:
            sys.path.insert(0, entry_str)
            logger.debug("Prepended %r to sys.path.", entry_str)
        logger.info(
            "Resolved %r as local project: %s:%s.",
            script,
            module_path,
            function_name,
        )
        return module_path, function_name

    # 3. .py file path. Checked before the module:function heuristic so that
    # Windows absolute paths (like `C:\...\foo.py`) are not mistaken for
    # `module:function` notation: the drive-letter colon would otherwise
    # split the path at the wrong position. A .py path that does not exist
    # falls through to the bare module lookup, skipping the module:function
    # check: a .py name is never valid module:function notation.
    if script.endswith(".py"):
        if script_path.is_file():
            logger.info("Resolved %r as .py file.", script)
            return script, ""
    # 4. Explicit module:function notation.
    elif ":" in script:
        module_path, function_name = script.rsplit(":", 1)
        logger.info(
            "Resolved %r as module:function: %s:%s.",
            script,
            module_path,
            function_name,
        )
        return module_path, function_name

    # 5. Bare module name. Check existence without importing so the module
    # is not loaded before patch_click() runs.
    try:
        spec = importlib.util.find_spec(script)
    except (ModuleNotFoundError, ValueError):
        spec = None

    if spec is not None:
        logger.info("Resolved %r as Python module.", script)
        return script, ""

    msg = (
        f"Cannot resolve {script!r} as a console_scripts entry point, "
        f"module:function, .py file, or Python module."
    )
    raise click.ClickException(msg)


def invoke_target(
    script: str,
    module_path: str,
    function_name: str,
    args: tuple[str, ...],
) -> None:
    """Import and call the target CLI.

    Reconstructs `sys.argv` so Click's argument parsing sees the
    target's program name and arguments, and pins `__main__.__package__`
    so the program name Click *detects* is that same script name.

    ```{note}
    A target whose Click command is invoked without an explicit `prog_name`
    falls back to `click.utils._detect_program_name()`, which reads
    `__main__.__package__`. That attribute states how *click-extra itself*
    was launched: under a documentation build running `python -m sphinx`, a
    wrapped usage line would read `python -m sphinx.flask`, and under
    `python -m click_extra` it would read `python -m click_extra.flask`.
    Emptying it for the call pins the detection on its file-execution branch,
    which answers the basename of `sys.argv[0]`: the script name set above.
    ```

    :param script: Original script name (used as `sys.argv[0]`).
    :param module_path: Dotted module path or `.py` file path.
    :param function_name: Function to call, or empty for module execution.
    :param args: Arguments to pass to the target CLI.
    """
    logger.info(
        "Invoking target: script=%r, module=%r, function=%r, args=%r.",
        script,
        module_path,
        function_name,
        args,
    )
    original_argv = sys.argv
    main_module = sys.modules["__main__"]
    original_package = getattr(main_module, "__package__", None)
    try:
        sys.argv = [script, *args]
        # Hide how click-extra itself was launched, so a target detecting its
        # own program name lands on the script above, not on the launcher.
        main_module.__package__ = ""

        if function_name:
            logger.debug("Importing %s and calling %s().", module_path, function_name)
            mod = importlib.import_module(module_path)
            func = getattr(mod, function_name)
            func()
        elif module_path.endswith(".py"):
            logger.debug("Running %s as script.", module_path)
            runpy.run_path(module_path, run_name="__main__")
        else:
            logger.debug("Running %s as module.", module_path)
            runpy.run_module(module_path, run_name="__main__")
    finally:
        sys.argv = original_argv
        main_module.__package__ = original_package


def _scan_for_command(mod: ModuleType, module_path: str) -> click.Command:
    """The one Click command a module defines at its top level, groups first.

    An entry point can be a plain function wrapping the command, so the module's
    namespace is scanned instead: a single group wins, then a single command.

    :raises click.ClickException: when the module defines several candidates
        of the winning kind, or none at all.
    """
    groups: dict[str, click.Command] = {}
    commands: dict[str, click.Command] = {}
    for attr_name in dir(mod):
        obj = getattr(mod, attr_name, None)
        if isinstance(obj, click.Group):
            groups[attr_name] = obj
        elif isinstance(obj, click.Command):
            commands[attr_name] = obj

    for kind, found in (("command groups", groups), ("commands", commands)):
        if len(found) == 1:
            return next(iter(found.values()))
        if found:
            raise click.ClickException(
                f"Multiple {kind} in {module_path}: {', '.join(sorted(found))}. "
                "Specify the correct one with module:name notation."
            )
    raise click.ClickException(
        f"No Click command found in {module_path}. If its entry point imports "
        "the command lazily, point at the module that defines it with "
        "module:function notation (for example, mypackage.cli:cli)."
    )


def _root_context(command: click.Command, script: str) -> click.Context:
    """Build the root context of `command` without parsing any argument.

    Built from the command's own `context_class` and `context_settings`, as
    {meth}`click.Command.make_context` builds the context of a run, so
    introspection reads what a run reads: the `auto_envvar_prefix`, the help
    option spellings, the `default_map` and the subcommand order. A plain
    `click.Context` would not do: a Cloup command's `context_settings` carry
    Cloup-only keys (`align_option_groups`, `show_constraints`, …) that it
    rejects with a `TypeError`. The root counterpart of
    {func}`~click_extra.param_tools.child_context`.

    :param command: the command to build the context of.
    :param script: the name the command answers to when it has none of its own.
    :return: the root context, with no argument parsed.
    """
    return command.context_class(
        command, info_name=command.name or script, **command.context_settings
    )


def resolve_target_command(
    script: str,
    subcommands: tuple[str, ...] = (),
) -> tuple[click.Command, click.Context]:
    """Import SCRIPT and return its Click command object and a matching context.

    Resolves SCRIPT through {func}`resolve_target`, imports the module, then
    obtains the command object without running the CLI: the entry-point
    attribute when it is itself a command, otherwise by scanning the module's
    namespace for Click command instances (preferring groups). Optional
    `subcommands` navigate into nested groups, mirroring the path a user would
    type.

    Shared by the introspection modes of the `wrap` command (`--params`,
    `--man`, `--tree` and `--help-format`) and by the man page hook of the
    Sphinx extension, so all describe the exact same resolved command.

    :raises click.ClickException: when no unambiguous Click command can be
        found, or a requested subcommand does not exist.
    """
    module_path, function_name = resolve_target(script)
    if module_path.endswith(".py"):
        # Load the file as a module. exec_module runs it under a synthetic
        # name, so the target's `if __name__ == "__main__"` guard does not
        # fire: the command objects are defined, not executed.
        spec = importlib.util.spec_from_file_location(
            "_click_extra_target", module_path
        )
        if spec is None or spec.loader is None:
            raise click.ClickException(f"Cannot load {module_path!r} as a module.")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    else:
        mod = importlib.import_module(module_path)
    cli_obj = getattr(mod, function_name) if function_name else None
    cmd = (
        cli_obj
        if isinstance(cli_obj, click.Command)
        else _scan_for_command(mod, module_path)
    )

    # Each context is built from its command's own `context_settings`, so the
    # environment variables introspection names are the ones a run reads. Click
    # applies these only through `make_context`, which would also parse
    # arguments.
    cmd_ctx = _root_context(cmd, script)
    for sub in subcommands:
        if not isinstance(cmd, click.Group):
            raise click.ClickException(
                f"{cmd.name!r} is not a group; cannot navigate to {sub!r}."
            )
        child = cmd.get_command(cmd_ctx, sub)
        if child is None:
            raise click.ClickException(f"No subcommand {sub!r} in {cmd.name!r}.")
        cmd_ctx = child_context(child, cmd_ctx, sub)
        cmd = child

    return cmd, cmd_ctx


class _WrapCommand(_HelpColorsMixin, cloup.Command):  # type: ignore[misc]
    """Cloup Command for the `wrap` subcommand.

    Uses Cloup (not vanilla Click) to support aliases. Like
    {class}`~click_extra.commands.ColorizedCommand` but based on
    `cloup.Command`.

    ```{note}
    This extends `cloup.Command` instead of
    {class}`~click_extra.commands.Command`, so it does **not** inherit
    the full {func}`~click_extra.commands.default_params` set. `wrap`
    carries only the options that act on the *target* CLI rather than on
    click-extra itself:

    - **Action flags** (`--params`, `--man`, `--tree`, `--help-format`)
      describe the target and exit without running it. Their group-level twins
      (`click-extra --params`) introspect the `click-extra` CLI
      itself, so they cannot reach a wrapped foreign command: the subject
      differs, which is why these are *not* redundant with the group
      versions. They route through the same rendering cores as the
      group-level options ({func}`~click_extra.show_params.render_params_table`,
      {func}`~click_extra.command_doc.read_manpage`,
      {func}`~click_extra.tree.render_command_tree`,
      {func}`~click_extra.command_doc.render_help`), so a new introspection
      feature only has to add one option here, never a parallel subcommand.

    - **Modifiers** (`--table-format`, `--columns`, `--output-dir`,
      `--install`) shape the action output and are inert in the default run
      mode.

    Presentation flags that style the *wrapping* (`--color`, `--theme`,
    `--verbosity`) stay on the parent {class}`WrapperGroup` and are
    inherited through the context, so they are deliberately absent here.
    ```
    """

    context_class: type[cloup.Context] = Context


#: Default columns for the standalone `wrap --params`: the full registry
#: minus `allowed_in_conf`, which only a click-extra `--config` option can
#: populate and a foreign CLI therefore always leaves empty.
_FOREIGN_PARAM_COLUMNS: tuple[str, ...] = tuple(
    col_id
    for col_id in ShowParamsOption.default_column_ids()
    if col_id != "allowed_in_conf"
)


def _split_navigation(args: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split target arguments into subcommand navigation and replay arguments.

    Leading tokens that do not look like options are treated as subcommand
    names to descend into; everything from the first option-like token onward
    is returned separately, to be replayed against the resolved command so the
    `value` and `source` columns reflect those arguments.

    `("run", "--port", "8080")` splits into `(("run",), ("--port", "8080"))`.
    """
    split = next(
        (index for index, arg in enumerate(args) if arg.startswith("-")), len(args)
    )
    return args[:split], args[split:]


def _wrap_params(
    ctx: click.Context,
    script: str,
    nav: tuple[str, ...],
    target_args: tuple[str, ...],
    table_format: TableFormat,
) -> None:
    """Resolve a foreign target and print its parameter table.

    Re-roots the parameter walk at the resolved (sub)command while preserving
    the `auto_envvar_prefix` computed along the navigation path, then defers
    to the shared {func}`~click_extra.show_params.render_params_table` core.

    The table format resolves in priority order: the `wrap --table-format`
    flag when given explicitly, then the click-extra group's `--table-format`
    (shared through the context), then the default.
    """
    cmd, drill_ctx = resolve_target_command(script, nav)

    # `render_params_table` walks from `subject_ctx.command` downward, so a
    # fresh root context scopes the table to the resolved node (matching what
    # the user navigated to). The drilled context already carries the nested
    # envvar prefix, so copy it over.
    subject_ctx = _root_context(cmd, script)
    subject_ctx.auto_envvar_prefix = drill_ctx.auto_envvar_prefix

    # An explicit `wrap --table-format` wins; otherwise defer to the group's
    # value (threaded through the shared context meta), then the default.
    if ctx.get_parameter_source("table_format") == ParameterSource.DEFAULT:
        resolved_format = context.get(ctx, context.TABLE_FORMAT) or table_format
    else:
        resolved_format = table_format
    context.set(subject_ctx, context.TABLE_FORMAT, resolved_format)
    selected_columns = context.get(ctx, context.COLUMNS)
    if selected_columns:
        context.set(subject_ctx, context.COLUMNS, selected_columns)
    if target_args:
        context.set(subject_ctx, context.RAW_ARGS, list(target_args))

    render_params_table(subject_ctx, default_columns=_FOREIGN_PARAM_COLUMNS)


def target_prog_name(script: str, command: click.Command) -> str:
    """Return the name a user would type to run SCRIPT.

    Every rendering of a target is titled with this: a man page's `.TH` line, a
    Carapace spec's `name`, a Markdown heading, the root of a `--tree`. None of
    them wants the string that was typed to *reach* the command, which is a
    filesystem path or a dotted import path as often as it is a command name.

    Three shapes, in the order they are distinguished:

    1. A path (a separator, or a `.py` suffix): its basename, dropping that
       suffix. `path/to/my_cli.py` is run as `my_cli`, not as its own path.
    2. A dotted or colon-separated import path: the command's own name, which
       Click took from the function or an explicit `name=`. An import path
       names a module, never a binary.
    3. Anything else is a console-script name, already exactly what a user
       types, and beats the command's own name when the two differ (Flask's
       entry point is `flask`, its group object is named `cli`).

    ```{caution}
    Case 2 is a best effort. A target reached as `python -m my_package.cli` has
    no single name a user types, so the command's own is the closest thing to
    one. Pass an explicit `prog_name` to the underlying renderer when that is
    not what you want in the output.
    ```
    """
    if script.endswith(".py"):
        return Path(script).stem
    if "/" in script or "\\" in script:
        return Path(script).name
    if ":" in script or "." in script:
        return command.name or script
    return script


def _wrap_man(script: str, nav: tuple[str, ...]) -> None:
    """Resolve a foreign target and read its manual page.

    Typesets and pages it, exactly as a CLI's own `--man` does, so a manual can
    be read for a CLI that ships none. The roff source a packager wants is
    `--help-format man`, which also takes `--output-dir` and `--install`.
    """
    cmd, _ = resolve_target_command(script, nav)
    read_manpage(cmd)


def _wrap_help_format(
    ctx: click.Context,
    script: str,
    nav: tuple[str, ...],
    help_format: HelpFormat,
    output_dir: Path | None,
    install: bool,
) -> None:
    """Resolve a foreign target and render it in one of the {class}`HelpFormat` formats.

    The target needs no cooperation for this: it is loaded, walked and described
    from the outside, like `--params` and `--man`. A CLI whose author never heard
    of Click Extra is therefore as machine-readable as one that ships
    `--help-format` itself.

    Stdout is the default destination. `output_dir` and `install` redirect it for
    the two formats that exist to be *installed* somewhere a consumer reads them
    from: a man page under a `man` directory, a Carapace spec under Carapace's.
    The other formats are documents, with no such place to be put, and both flags
    are refused for them by the caller. Each format's own module owns where it
    installs, and resolves that directory at call time, so an XDG override set
    for one invocation is honored.
    """
    cmd, _ = resolve_target_command(script, nav)

    if help_format is HelpFormat.CARAPACE:
        # A spec is keyed on the binary a shell completes, not on the path typed
        # to reach it (see render_help). The reconstructed wrap command goes in
        # the header, rebuilt from the context rather than sys.argv so it is also
        # correct under CliRunner, in tests and Sphinx.
        prog_name = nav[-1] if nav else target_prog_name(script, cmd)
        parts = [*ctx.command_path.split(), "--help-format", "carapace"]
        if install:
            parts.append("--install")
        parts.extend(("--", script, *nav))
        invocation = shlex.join(parts)
        if output_dir:
            written = write_carapace_spec(
                cmd,
                output_dir / f"{prog_name}.yaml",
                prog_name=prog_name,
                invocation=invocation,
            )
        elif install:
            written = install_carapace_spec(
                cmd, prog_name=prog_name, invocation=invocation
            )
        else:
            click.echo(
                dump_carapace_spec(cmd, prog_name=prog_name, invocation=invocation)
            )
            return
        click.echo(str(written))
        return

    if help_format is HelpFormat.MAN and (output_dir or install):
        if nav:
            raise click.ClickException(
                "Writing man pages always emits the full tree rooted at SCRIPT "
                "and cannot be combined with extra SUBCOMMAND arguments. To "
                "write a single subcommand page, drop --output-dir/--install and "
                "redirect stdout into a .1 file instead."
            )
        prog_name = target_prog_name(script, cmd)
        written_pages = (
            write_manpages(cmd, output_dir, prog_name=prog_name)
            if output_dir
            else install_manpages(cmd, prog_name=prog_name)
        )
        for path in written_pages:
            click.echo(str(path))
        return

    prog_name = " ".join((target_prog_name(script, cmd), *nav))
    click.echo(render_help(cmd, help_format, prog_name=prog_name), color=False)


def _wrap_tree(
    ctx: click.Context,
    script: str,
    nav: tuple[str, ...],
) -> None:
    """Resolve a foreign target and print its subcommand tree.

    Roots the tree at the resolved (sub)command, labeled with the navigation
    path the user typed, and defers to the shared
    {func}`~click_extra.tree.render_command_tree` core. Accessibility mode is
    carried over from the wrapping context so the rail degrades to ASCII (the
    resolved target gets a fresh root context whose `meta` would otherwise
    lose the {data}`~click_extra.context.ACCESSIBLE` entry).
    """
    cmd, _ = resolve_target_command(script, nav)
    prog_name = " ".join((target_prog_name(script, cmd), *nav))
    subject_ctx = make_resilient_context(cmd, prog_name)
    if context.get(ctx, context.ACCESSIBLE, False):
        context.set(subject_ctx, context.ACCESSIBLE, True)
    click.echo(render_command_tree(cmd, ctx=subject_ctx), color=ctx.color)


def _config_args_for_target(
    ctx: click.Context,
    script: str,
) -> tuple[str, ...]:
    """Read the `[wrap.<script>]` config section and convert to CLI args.

    Looks for a config section named after the target script under `wrap`.
    For example, `click-extra wrap -- flask` reads `[tool.click-extra.wrap.flask]`
    in `pyproject.toml`. All keys in that section are converted to CLI
    arguments through {func}`~click_extra.config.flags.config_table_to_flags`,
    after their underscores become dashes, and prepended to the target's
    invocation.

    Invalid options are naturally caught by the target CLI itself, producing
    standard Click error messages like "No such option: --foo".

    ```{code-block} toml

    [tool.click-extra.wrap.flask]
    app = "myapp:create_app"
    debug = true
    ```
    """
    # `ctx.meta` is shared across the parent/child hierarchy, so reading
    # from the local context is sufficient. The root command's name is still
    # needed below to locate the right TOML section.
    full_conf = context.get(ctx, context.CONF_FULL)
    if not full_conf:
        return ()

    # Extract the [click-extra.wrap.<script>] section from the raw config.
    app_name = ctx.find_root().command.name or ""
    # Normalize path separators to forward slashes so Windows absolute paths
    # like "C:\...\script.py" match TOML keys written as "C:/.../script.py".
    # TOML basic strings interpret backslashes as escape sequences, so users
    # must use forward slashes in their pyproject.toml keys.
    normalized_script = script.replace("\\", "/")
    target_section = (
        full_conf.get(app_name, {}).get("wrap", {}).get(normalized_script, {})
    )
    if not target_section or not isinstance(target_section, dict):
        return ()

    return tuple(
        config_table_to_flags({
            key.replace("_", "-"): value for key, value in target_section.items()
        })
    )


#: Sample invocations closing the `wrap` help screen.
WRAP_EPILOG = """\b
Examples:

\b
  Run a CLI with Click Extra's colored help:
    $ click-extra wrap -- my-cli --help

\b
  Read the help of one of its subcommands:
    $ click-extra wrap -- my-cli pick --help

\b
  Report what a subcommand accepts, and where each value comes from:
    $ click-extra wrap --params -- my-cli pick

\b
  Write a shell-completion spec where its consumer looks for it:
    $ click-extra wrap --help-format carapace --install -- my-cli
"""


@click.command(
    name="wrap",
    aliases=["run"],
    cls=_WrapCommand,
    context_settings={"allow_interspersed_args": False},
    epilog=WRAP_EPILOG,
)
@option(
    "--params",
    is_flag=True,
    default=False,
    help="Show the parameters of the target CLI and exit, without running it.",
)
@option(
    "--man",
    is_flag=True,
    default=False,
    help="Read the manual page of the target CLI and exit, without running it.",
)
@option(
    "--tree",
    is_flag=True,
    default=False,
    help="Show the tree of nested subcommands of the target CLI and exit, "
    "without running it.",
)
@option(
    "--help-format",
    type=EnumChoice(HelpFormat),
    default=None,
    help="Render the target CLI in the given format and exit, without running it.",
)
@option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True, writable=True, path_type=Path),
    default=None,
    help="With --help-format, write the rendering into this directory instead of "
    "printing it. Created if missing.",
)
@option(
    "--install",
    is_flag=True,
    default=False,
    help="With --help-format, write the rendering where its consumer looks for it "
    "instead of printing it, and echo the written path.",
)
@option(
    # Reuses the canonical option, so its name, type, metavar and default are
    # declared once. This copy exposes its value and drops the class callback:
    # `_wrap_params` resolves the format against the group's pick and sets it on
    # the target's own context, which the callback would preempt.
    cls=TableFormatOption,
    expose_value=True,
    is_eager=False,
    callback=None,
    help="With --params, the rendering style of the parameter table. "
    "Falls back to the click-extra group's --table-format when not set here.",
)
@columns_option(columns=ShowParamsOption.TABLE_HEADERS)
@click.argument(
    "script_and_args",
    nargs=-1,
    type=click.UNPROCESSED,
    metavar="SCRIPT [ARGS]...",
)
@click.pass_context
def wrap(
    ctx: click.Context,
    script_and_args: tuple[str, ...],
    params: bool,
    man: bool,
    tree: bool,
    help_format: HelpFormat | None,
    output_dir: Path | None,
    install: bool,
    table_format: TableFormat,
) -> None:
    """Run, or introspect, any Click CLI through Click Extra.

    By default, runs SCRIPT with keyword highlighting and themed styling for
    its help screens. The target CLI is not modified.

    With --params, --man, --tree or --help-format, SCRIPT is loaded and
    described without being run. The first three answer a question a person is
    asking right now; --help-format renders the target as an artifact for a
    program or a build step. Extra arguments after SCRIPT navigate into
    nested subcommands; for --params, any trailing options are replayed
    against the resolved command so the parameter table reports their value and
    source.

    Resolution order for SCRIPT: installed console_scripts entry point, a local
    project directory (its entry point is read from pyproject.toml or setup.cfg),
    Python file path, module:function notation, or Python module name.
    """
    if not script_and_args:
        click.echo(ctx.get_help(), color=ctx.color)
        ctx.exit(0)

    if sum((params, man, tree, bool(help_format))) > 1:
        raise click.UsageError(
            "--params, --man, --tree and --help-format are mutually exclusive."
        )
    # Only the formats a consumer installs somewhere have a destination to be
    # redirected to. The rest are documents: stdout is the only answer.
    if (output_dir is not None or install) and help_format not in INSTALLABLE_FORMATS:
        flag = "--output-dir" if output_dir is not None else "--install"
        formats = ", ".join(sorted(INSTALLABLE_FORMATS))
        raise click.UsageError(f"{flag} requires --help-format with one of: {formats}.")

    script = script_and_args[0]
    args = script_and_args[1:]

    # Introspection modes: load the target and describe it without running it.
    if params or man or tree or help_format:
        nav, target_args = _split_navigation(args)
        if man:
            _wrap_man(script, nav)
        elif tree:
            _wrap_tree(ctx, script, nav)
        elif help_format:
            _wrap_help_format(ctx, script, nav, help_format, output_dir, install)
        else:
            _wrap_params(ctx, script, nav, target_args, table_format)
        ctx.exit(0)

    # Default mode: run the target with colorized help.
    # Extract config from the [wrap.<script>] section and prepend as CLI
    # arguments for the target.
    config_args = _config_args_for_target(ctx, script)
    if config_args:
        logger.info("Config args for target CLI: %s.", config_args)
        args = (*config_args, *args)

    module_path, function_name = resolve_target(script)

    # Color and theme are inherited from the parent group's context: ColorOption
    # has already processed --color/--no-color flags and environment variables
    # (NO_COLOR, CLICOLOR, etc.), and ThemeOption has recorded the user's --theme
    # pick on the shared context meta. The wrapped target runs under its own fresh
    # context with no meta, so `get_current_theme` (reading that meta, or the
    # dark default when --theme was omitted) resolves the pick here and hands it to
    # `patch_click`, which installs it as the process-wide default the target's
    # help then renders with.
    patch_click(theme=get_current_theme(), color=ctx.color)
    invoke_target(script, module_path, function_name, args)


#: Choice values of this command's own options that are also plain English
#: words its description uses: the parameter table "reports their value and
#: source". Excluded from the cross-reference pass, which would otherwise paint
#: them as values wherever the prose says the word. Their own metavars keep
#: their coloring, see `HelpFormatter.highlight_extra_keywords`.
wrap.excluded_keywords = HelpKeywords(
    choices={"default", "help", "source", "value"},
)
