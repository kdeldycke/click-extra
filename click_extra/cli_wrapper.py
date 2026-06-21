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
"""The ``click-extra wrap`` command and the machinery to wrap a foreign Click CLI.

Monkey-patches Click's decorator functions before importing (or running) a
target module so its ``@click.command()`` / ``@click.group()`` produce
colorized, keyword-highlighted, themed variants. Also resolves and invokes the
target, and introspects it for ``--show-params`` and ``--man`` without firing
its callbacks.

Not to be confused with text wrapping: that is :func:`click.wrap_text`, exposed
at the package root as ``click_extra.wrap_text``.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import runpy
import sys
from importlib import metadata
from pathlib import Path

import click
import cloup
from click.core import ParameterSource
from click.utils import make_str

from . import EnumChoice, context, option
from .commands import ColorizedCommand, ColorizedGroup, Group
from .context import Context
from .decorators import columns_option
from .highlight import HelpFormatter, _HelpColorsMixin
from .man_page import render_manpage, write_manpages
from .parameters import ShowParamsOption, render_params_table
from .table import DEFAULT_FORMAT, TableFormat
from .theme import BUILTIN_THEMES, HelpTheme, nocolor_theme, set_default_theme

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

logger = logging.getLogger(__name__)

# Save pristine references before any patching occurs.
_original_click_command = click.decorators.command
_original_click_group = click.decorators.group
_original_get_help = click.Command.get_help
_original_format_help = click.Command.format_help


class WrapperGroup(Group):
    """Group that falls back to the ``wrap`` subcommand for unknown names.

    Known subcommands and their aliases are dispatched normally. Anything
    else is treated as a target script and forwarded to ``wrap``.
    """

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        cmd_name = make_str(args[0])
        # Cloup's resolve_command_name handles both direct names and aliases.
        resolved = super().resolve_command_name(ctx, cmd_name)
        if resolved is not None:
            cmd = self.get_command(ctx, resolved)
            if cmd is not None:
                return cmd_name, cmd, args[1:]
        # Unknown name: delegate the entire arg list to ``wrap``.
        wrap_cmd = self.get_command(ctx, "wrap")
        if wrap_cmd is not None:
            return "wrap", wrap_cmd, args
        return super().resolve_command(ctx, args)


def _make_patched_decorator(
    original: Callable[..., Any],
    default_cls: type[click.Command],
) -> Callable[..., Any]:
    """Build a drop-in replacement for ``click.command`` / ``click.group``.

    The returned wrapper defaults its ``cls`` to ``default_cls`` (a colorized
    variant) while forwarding to ``original``. It handles both the parenthesized
    form (``@command(...)``) and the bare form (``@command``), where the decorated
    function arrives as the first positional ``name`` argument.
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
    ``@click.command()`` and ``@click.group()`` decorators produce colorized
    commands.

    .. note::
        Only the decorator functions are replaced, not the class names
        (``click.Command``, ``click.Group``). Replacing class names would
        break ``isinstance`` and ``issubclass`` checks in Click internals
        (``_param_memo``) and Cloup's decorator validators.

    :param theme: Color theme to use. ``None`` keeps the current default.
    :param color: Tri-state ANSI control mirroring ``ctx.color``: ``True`` forces
        colors on, ``False`` strips them, and ``None`` (the GNU ``auto`` default)
        defers to the output stream's TTY status.
    """
    if color is False:

        class _NoColorContext(Context):
            """Context variant that forces colors off."""

            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                # Pin colors off for a root context, overriding the auto default
                # Context would otherwise resolve from the environment.
                if not self.parent:
                    self.color = False

        ColorizedCommand.context_class = _NoColorContext
        ColorizedGroup.context_class = _NoColorContext
    else:
        ColorizedCommand.context_class = Context
        ColorizedGroup.context_class = Context

    _patched_command_func = _make_patched_decorator(
        _original_click_command, ColorizedCommand
    )
    _patched_group_func = _make_patched_decorator(
        _original_click_group, ColorizedGroup
    )

    # Replace decorator functions in both namespaces so both ``click.command``
    # and ``from click.decorators import command`` resolve to the wrappers.
    click.command = _patched_command_func
    click.group = _patched_group_func
    click.decorators.command = _patched_command_func
    click.decorators.group = _patched_group_func
    logger.debug("Patched click.command and click.group decorators.")

    # Patch Command methods to colorize ALL commands, including those with
    # explicit ``cls=`` (like Flask's ``FlaskGroup``). Commands that already
    # have ``_HelpColorsMixin`` skip this path to avoid double-processing.
    color_flag = color

    def _patched_get_help(self, ctx):
        if not isinstance(self, _HelpColorsMixin):
            ctx.formatter_class = HelpFormatter
            if not ctx.parent and ctx.color is None:
                ctx.color = color_flag
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
            # collect_keywords() now works on any command: static methods are
            # class-qualified and extra_keywords uses getattr with defaults.
            formatter.keywords = _HelpColorsMixin.collect_keywords(self, ctx)
            formatter.excluded_keywords = (
                _HelpColorsMixin._collect_excluded_keywords(ctx)
            )
        _original_format_help(self, ctx, formatter)

    click.Command.get_help = _patched_get_help  # type: ignore[method-assign]
    click.Command.format_help = _patched_format_help  # type: ignore[method-assign]
    logger.debug("Patched click.Command.get_help and format_help methods.")

    # Override the default theme if requested.
    if theme is not None:
        set_default_theme(theme)

    logger.info(
        "Click patched: color=%s, theme=%s.",
        color,
        type(theme).__name__ if theme is not None else "default",
    )


def unpatch_click() -> None:
    """Restore Click's original decorator functions and methods.

    Reverses the changes made by :func:`patch_click`. Useful in tests to
    avoid leaking global state between test cases.
    """
    click.command = _original_click_command
    click.group = _original_click_group
    click.decorators.command = _original_click_command
    click.decorators.group = _original_click_group
    click.Command.get_help = _original_get_help  # type: ignore[method-assign]
    click.Command.format_help = _original_format_help  # type: ignore[method-assign]
    # Reset context classes to defaults.
    ColorizedCommand.context_class = Context
    ColorizedGroup.context_class = Context

    # Restore the default theme. Fall back to the colorless theme when
    # themes.toml is absent (some packaging setups drop the data file, so the
    # built-in "dark" palette is unavailable).
    set_default_theme(BUILTIN_THEMES.get("dark", nocolor_theme))


def resolve_target(script: str) -> tuple[str, str]:
    """Resolve a script name to a module path and function name.

    Resolution order:

    1. ``console_scripts`` entry points from installed packages.
    2. Explicit ``module:function`` notation.
    3. ``.py`` file path.
    4. Bare Python module or package name.

    :returns: ``(module_path, function_name)`` tuple. *function_name* is
        empty when the target should be invoked as a module or script file.
    :raises click.ClickException: If the script cannot be resolved.
    """
    logger.debug("Resolving target %r.", script)

    # 1. Console scripts entry points.
    for ep in metadata.entry_points().select(group="console_scripts"):
        if ep.name == script:
            module_path, _, function_name = ep.value.partition(":")
            logger.info(
                "Resolved %r as console_scripts entry point: %s:%s.",
                script,
                module_path,
                function_name,
            )
            return module_path, function_name

    # 2. .py file path. Checked before the module:function heuristic so that
    # Windows absolute paths (e.g. ``C:\...\foo.py``) are not mistaken for
    # ``module:function`` notation — the drive-letter colon would otherwise
    # split the path at the wrong position.
    if script.endswith(".py"):
        if Path(script).is_file():
            logger.info("Resolved %r as .py file.", script)
            return script, ""
        # .py path that does not exist: fall through to bare module lookup.
        # Skip the module:function check below — a .py name is never valid
        # module:function notation.
    else:
        # 3. Explicit module:function notation.
        if ":" in script:
            module_path, function_name = script.rsplit(":", 1)
            logger.info(
                "Resolved %r as module:function: %s:%s.",
                script,
                module_path,
                function_name,
            )
            return module_path, function_name

    # 4. Bare module name. Check existence without importing so the module
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

    Reconstructs ``sys.argv`` so Click's argument parsing sees the
    target's program name and arguments.

    :param script: Original script name (used as ``sys.argv[0]``).
    :param module_path: Dotted module path or ``.py`` file path.
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
    try:
        sys.argv = [script, *args]

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


def resolve_target_command(
    script: str,
    subcommands: tuple[str, ...] = (),
) -> tuple[click.Command, click.Context]:
    """Import SCRIPT and return its Click command object and a matching context.

    Resolves SCRIPT through :func:`resolve_target`, imports the module, then
    obtains the command object without running the CLI: the entry-point
    attribute when it is itself a command, otherwise by scanning the module's
    namespace for Click command instances (preferring groups). Optional
    ``subcommands`` navigate into nested groups, mirroring the path a user would
    type.

    Shared by the ``wrap`` command's ``--show-params`` and ``--man`` modes so
    both introspect the exact same resolved command.

    :raises click.ClickException: when no unambiguous Click command can be
        found, or a requested subcommand does not exist.
    """
    module_path, function_name = resolve_target(script)
    if module_path.endswith(".py"):
        # Load the file as a module. exec_module runs it under a synthetic
        # name, so the target's ``if __name__ == "__main__"`` guard does not
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

    if not isinstance(cli_obj, click.Command):
        # The entry point might be a wrapper function. Scan the module
        # for Click command instances, preferring groups.
        groups = {}
        commands = {}
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if isinstance(obj, click.Group):
                groups[attr_name] = obj
            elif isinstance(obj, click.Command):
                commands[attr_name] = obj

        if len(groups) == 1:
            cli_obj = next(iter(groups.values()))
        elif groups:
            names = ", ".join(sorted(groups))
            raise click.ClickException(
                f"Multiple command groups in {module_path}: {names}. "
                f"Specify the correct one with module:name notation."
            )
        elif len(commands) == 1:
            cli_obj = next(iter(commands.values()))
        elif commands:
            names = ", ".join(sorted(commands))
            raise click.ClickException(
                f"Multiple commands in {module_path}: {names}. "
                f"Specify the correct one with module:name notation."
            )
        else:
            raise click.ClickException(f"No Click commands found in {module_path}.")

    # Navigate to the requested subcommand, if any.
    assert isinstance(cli_obj, click.Command)
    cmd: click.Command = cli_obj
    # Propagate ``context_settings`` (notably ``auto_envvar_prefix``) so
    # introspection sees the same envvar layout the CLI exposes at runtime.
    # Click reads these only through ``make_context``; the raw ``Context``
    # constructor ignores them. Build through ``cmd.context_class`` (not
    # ``click.Context``) exactly as ``make_context`` does: a Cloup command's
    # ``context_settings`` carry Cloup-only keys (``align_option_groups``,
    # ``show_constraints``, …) that a plain ``click.Context`` rejects with a
    # ``TypeError``. Child contexts inherit ``auto_envvar_prefix`` from their
    # parent automatically.
    cmd_ctx = cmd.context_class(
        cmd, info_name=cmd.name or script, **dict(cmd.context_settings)
    )
    for sub in subcommands:
        if not isinstance(cmd, click.Group):
            raise click.ClickException(
                f"{cmd.name!r} is not a group; cannot navigate to {sub!r}."
            )
        child = cmd.get_command(cmd_ctx, sub)
        if child is None:
            raise click.ClickException(f"No subcommand {sub!r} in {cmd.name!r}.")
        cmd_ctx = child.context_class(child, parent=cmd_ctx, info_name=sub)
        cmd = child

    return cmd, cmd_ctx


class _WrapCommand(_HelpColorsMixin, cloup.Command):  # type: ignore[misc]
    """Cloup Command for the ``wrap`` subcommand.

    Uses Cloup (not vanilla Click) to support aliases. Like
    :class:`~click_extra.commands.ColorizedCommand` but based on
    ``cloup.Command``.

    .. note::
        This extends ``cloup.Command`` instead of
        :class:`~click_extra.commands.Command`, so it does **not** inherit
        the full :func:`~click_extra.commands.default_params` set. ``wrap``
        carries only the options that act on the *target* CLI rather than on
        click-extra itself:

        - **Action flags** (``--show-params``, ``--man``) describe and exit
          without running the target. Their group-level twins
          (``click-extra --show-params``) introspect the ``click-extra`` CLI
          itself, so they cannot reach a wrapped foreign command: the subject
          differs, which is why these are *not* redundant with the group
          versions. They route through the same rendering cores as the
          group-level options (:func:`~click_extra.parameters.render_params_table`,
          :func:`~click_extra.man_page.render_manpage`), so a new introspection
          feature only has to add one option here, never a parallel subcommand.

        - **Modifiers** (``--table-format``, ``--columns``, ``--output-dir``)
          shape the action output and are inert in the default run mode.

        Presentation flags that style the *wrapping* (``--color``, ``--theme``,
        ``--verbosity``) stay on the parent :class:`WrapperGroup` and are
        inherited through the context, so they are deliberately absent here.
    """

    context_class: type[cloup.Context] = Context


#: Default columns for the standalone ``wrap --show-params``: the full registry
#: minus ``allowed_in_conf``, which only a click-extra ``--config`` option can
#: populate and a foreign CLI therefore always leaves empty.
_FOREIGN_PARAM_COLUMNS: tuple[str, ...] = tuple(
    col.id for col in ShowParamsOption.TABLE_HEADERS if col.id != "allowed_in_conf"
)


def _split_navigation(args: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split target arguments into subcommand navigation and replay arguments.

    Leading tokens that do not look like options are treated as subcommand
    names to descend into; everything from the first option-like token onward
    is returned separately, to be replayed against the resolved command so the
    ``value`` and ``source`` columns reflect those arguments.

    ``("run", "--port", "8080")`` splits into ``(("run",), ("--port", "8080"))``.
    """
    nav = []
    rest = list(args)
    while rest and not rest[0].startswith("-"):
        nav.append(rest.pop(0))
    return tuple(nav), tuple(rest)


def _wrap_show_params(
    ctx: click.Context,
    script: str,
    nav: tuple[str, ...],
    target_args: tuple[str, ...],
    table_format: TableFormat,
) -> None:
    """Resolve a foreign target and print its parameter table.

    Re-roots the parameter walk at the resolved (sub)command while preserving
    the ``auto_envvar_prefix`` computed along the navigation path, then defers
    to the shared :func:`~click_extra.parameters.render_params_table` core.

    The table format resolves in priority order: the ``wrap --table-format``
    flag when given explicitly, then the click-extra group's ``--table-format``
    (shared through the context), then the default.
    """
    cmd, drill_ctx = resolve_target_command(script, nav)

    # ``render_params_table`` walks from ``subject_ctx.command`` downward, so a
    # fresh root context scopes the table to the resolved node (matching what
    # the user navigated to). The drilled context already carries the nested
    # envvar prefix, so copy it over.
    subject_ctx = click.Context(cmd, info_name=cmd.name or script)
    subject_ctx.auto_envvar_prefix = drill_ctx.auto_envvar_prefix

    # An explicit ``wrap --table-format`` wins; otherwise defer to the group's
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


def _wrap_man(
    script: str,
    nav: tuple[str, ...],
    output_dir: Path | None,
) -> None:
    """Resolve a foreign target and render its man page (roff).

    With ``output_dir`` set, writes one ``.1`` file per (sub)command of the
    tree rooted at SCRIPT; otherwise prints a single page to stdout.
    """
    cmd, _ = resolve_target_command(script, nav)
    if output_dir is not None:
        if nav:
            raise click.ClickException(
                "--output-dir always emits the full tree rooted at SCRIPT and "
                "cannot be combined with extra SUBCOMMAND arguments. To render "
                "a single subcommand page, drop --output-dir and redirect "
                "stdout into a .1 file instead."
            )
        prog_name = cmd.name or script
        for path in write_manpages(cmd, output_dir, prog_name=prog_name):
            click.echo(str(path))
    else:
        prog_name = " ".join((script, *nav))
        click.echo(render_manpage(cmd, prog_name=prog_name))


def _config_args_for_target(
    ctx: click.Context,
    script: str,
) -> tuple[str, ...]:
    """Read the ``[wrap.<script>]`` config section and convert to CLI args.

    Looks for a config section named after the target script under ``wrap``.
    For example, ``click-extra wrap flask`` reads ``[tool.click-extra.wrap.flask]``
    in ``pyproject.toml``. All keys in that section are converted to CLI
    arguments and prepended to the target's invocation.

    Invalid options are naturally caught by the target CLI itself, producing
    standard Click error messages like "No such option: --foo".

    .. code-block:: toml

        [tool.click-extra.wrap.flask]
        app = "myapp:create_app"
        debug = true
    """
    # ``ctx.meta`` is shared across the parent/child hierarchy, so reading
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

    extra: list[str] = []
    for key, value in target_section.items():
        # Convert underscores to dashes for CLI option names.
        opt_name = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            # Only pass the flag when true. A false boolean means "don't
            # pass the flag," which is the default for Click flags. Sending
            # --no-<name> would fail on plain is_flag=True options that
            # don't define a --flag/--no-flag pair.
            if value:
                extra.append(opt_name)
        elif isinstance(value, list):
            for item in value:
                extra.append(opt_name)
                extra.append(str(item))
        else:
            extra.append(opt_name)
            extra.append(str(value))

    return tuple(extra)


@click.command(
    name="wrap",
    aliases=["run"],
    cls=_WrapCommand,
    context_settings={"allow_interspersed_args": False},
)
@option(
    "--show-params",
    is_flag=True,
    default=False,
    help="Show the parameters of the target CLI and exit, without running it.",
)
@option(
    "--man",
    is_flag=True,
    default=False,
    help="Show the man page (roff) of the target CLI and exit, without running it.",
)
@option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True, writable=True, path_type=Path),
    default=None,
    help="With --man, write one .1 file per (sub)command into this directory "
    "instead of printing a single page to stdout. Created if missing.",
)
@option(
    "--table-format",
    type=EnumChoice(TableFormat),
    default=DEFAULT_FORMAT,
    help="With --show-params, the rendering style of the parameter table. "
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
    show_params: bool,
    man: bool,
    output_dir: Path | None,
    table_format: TableFormat,
) -> None:
    """Run, or introspect, any Click CLI through Click Extra.

    By default, runs SCRIPT with keyword highlighting and themed styling for
    its help screens. The target CLI is not modified.

    With --show-params or --man, SCRIPT is loaded and described without being
    run. Extra arguments after SCRIPT navigate into nested subcommands; for
    --show-params, any trailing options are replayed against the resolved
    command so the parameter table reports their value and source.

    Resolution order for SCRIPT: installed console_scripts entry point,
    module:function notation, Python file path, or Python module name.
    """
    if not script_and_args:
        click.echo(ctx.get_help(), color=ctx.color)
        ctx.exit(0)

    if show_params and man:
        raise click.UsageError("--show-params and --man are mutually exclusive.")
    if output_dir is not None and not man:
        raise click.UsageError("--output-dir requires --man.")

    script = script_and_args[0]
    args = script_and_args[1:]

    # Introspection modes: load the target and describe it without running it.
    if show_params or man:
        nav, target_args = _split_navigation(args)
        if man:
            _wrap_man(script, nav, output_dir)
        else:
            _wrap_show_params(ctx, script, nav, target_args, table_format)
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
    # (NO_COLOR, CLICOLOR, etc.), and ThemeOption has reassigned
    # ``theme.default_theme`` to the user's pick. ``theme=None`` instructs
    # ``patch_click`` to keep that current default.
    patch_click(theme=None, color=ctx.color)
    invoke_target(script, module_path, function_name, args)
