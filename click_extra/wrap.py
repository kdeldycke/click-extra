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
"""Wrap any Click CLI with Click Extra's help colorization.

Monkey-patches Click's decorator functions before importing the target module
so ``@click.command()`` and ``@click.group()`` produce colorized variants with
keyword highlighting and themed styling.
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
from click.utils import make_str

from . import context
from . import theme as _theme
from .colorize import ExtraHelpColorsMixin, HelpExtraFormatter
from .commands import ColorizedCommand, ColorizedGroup, ExtraGroup
from .context import ExtraContext
from .theme import HelpExtraTheme

logger = logging.getLogger("click_extra")

# Save pristine references before any patching occurs.
_original_click_command = click.decorators.command
_original_click_group = click.decorators.group
_original_get_help = click.Command.get_help
_original_format_help = click.Command.format_help


class WrapperGroup(ExtraGroup):
    """ExtraGroup that falls back to the ``wrap`` subcommand for unknown names.

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


def patch_click(
    theme: HelpExtraTheme | None = None,
    color: bool = True,
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
    :param color: When ``False``, the patched context disables ANSI output.
    """
    if not color:

        class _NoColorContext(ExtraContext):
            """ExtraContext variant that forces colors off."""

            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                # Override the color=True default that ExtraContext sets for
                # root contexts.
                if not self.parent:
                    self.color = False

        ColorizedCommand.context_class = _NoColorContext
        ColorizedGroup.context_class = _NoColorContext
    else:
        ColorizedCommand.context_class = ExtraContext
        ColorizedGroup.context_class = ExtraContext

    def _patched_command_func(name=None, cls=None, **attrs):
        """Wrapper around ``click.command`` defaulting cls to ColorizedCommand."""
        # Handle bare @click.command usage (no parentheses): the decorated
        # function is passed as the first positional argument.
        if callable(name):
            func = name
            if cls is None:
                cls = ColorizedCommand
            return _original_click_command(cls=cls, **attrs)(func)
        if cls is None:
            cls = ColorizedCommand
        return _original_click_command(name=name, cls=cls, **attrs)

    def _patched_group_func(name=None, cls=None, **attrs):
        """Wrapper around ``click.group`` defaulting cls to ColorizedGroup."""
        if callable(name):
            func = name
            if cls is None:
                cls = ColorizedGroup
            return _original_click_group(cls=cls, **attrs)(func)
        if cls is None:
            cls = ColorizedGroup
        return _original_click_group(name=name, cls=cls, **attrs)

    # Replace decorator functions in both namespaces so both ``click.command``
    # and ``from click.decorators import command`` resolve to the wrappers.
    click.command = _patched_command_func
    click.group = _patched_group_func
    click.decorators.command = _patched_command_func
    click.decorators.group = _patched_group_func
    logger.debug("Patched click.command and click.group decorators.")

    # Patch Command methods to colorize ALL commands, including those with
    # explicit ``cls=`` (like Flask's ``FlaskGroup``). Commands that already
    # have ``ExtraHelpColorsMixin`` skip this path to avoid double-processing.
    color_flag = color

    def _patched_get_help(self, ctx):
        if not isinstance(self, ExtraHelpColorsMixin):
            ctx.formatter_class = HelpExtraFormatter
            if not ctx.parent and ctx.color is None:
                ctx.color = color_flag
        return _original_get_help(self, ctx)

    def _patched_format_help(self, ctx, formatter):
        if isinstance(formatter, HelpExtraFormatter) and not isinstance(
            self, ExtraHelpColorsMixin
        ):
            logger.debug(
                "Collecting keywords for %s (%s).",
                type(self).__name__,
                self.name,
            )
            # collect_keywords() now works on any command: static methods are
            # class-qualified and extra_keywords uses getattr with defaults.
            formatter.keywords = ExtraHelpColorsMixin.collect_keywords(self, ctx)
            formatter.excluded_keywords = (
                ExtraHelpColorsMixin._collect_excluded_keywords(ctx)
            )
        _original_format_help(self, ctx, formatter)

    click.Command.get_help = _patched_get_help  # type: ignore[method-assign]
    click.Command.format_help = _patched_format_help  # type: ignore[method-assign]
    logger.debug("Patched click.Command.get_help and format_help methods.")

    # Override the default theme if requested.
    if theme is not None:
        _theme.default_theme = theme

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
    ColorizedCommand.context_class = ExtraContext
    ColorizedGroup.context_class = ExtraContext

    # Restore the default theme.
    _theme.default_theme = HelpExtraTheme.dark()


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


class _WrapCommand(ExtraHelpColorsMixin, cloup.Command):  # type: ignore[misc]
    """Cloup Command for the ``wrap`` subcommand.

    Uses Cloup (not vanilla Click) to support aliases. Like
    :class:`~click_extra.commands.ColorizedCommand` but based on
    ``cloup.Command``.

    .. note::
        This deliberately extends ``cloup.Command`` instead of
        :class:`~click_extra.commands.ExtraCommand`, so it does **not** inherit
        :func:`~click_extra.commands.default_extra_params`. The reasons:

        1. **The parent group already exposes them.** The hosting
           :class:`WrapperGroup` is an :class:`~click_extra.commands.ExtraGroup`,
           so ``--time``, ``--config``, ``--no-config``, ``--validate-config``,
           ``--color``, ``--theme``, ``--show-params``, ``--table-format``,
           ``--verbosity``, ``--verbose``, ``--version`` and ``--help`` are
           already attached at the ``click-extra`` group level. Duplicating
           them on ``wrap`` would create two valid spellings
           (``click-extra --color wrap …`` versus
           ``click-extra wrap --color …``) for the same effect.

        2. **Argument forwarding constraints.** ``wrap`` uses
           ``allow_interspersed_args=False`` and forwards everything after
           ``SCRIPT`` to the target CLI verbatim. Adding more options on
           ``wrap`` widens the surface for accidental collisions with the
           wrapped CLI's own options, and bloats ``wrap --help`` with flags
           unrelated to wrapping.

        3. **All defaults are semantically irrelevant here.**
           ``--show-params``, ``--table-format``, ``--config``,
           ``--verbosity`` and ``--theme`` all describe behavior of
           click-extra itself (its own config file, its own logging, its own
           parameter introspection, its own help-screen theme). Re-declaring
           any of them on ``wrap`` would shadow the group versions but operate
           on the same global state: pure redundancy.

        ``wrap`` therefore declares no options of its own: the parent group
        carries every relevant flag, and everything after ``SCRIPT`` is
        forwarded verbatim to the target CLI.
    """

    context_class: type[cloup.Context] = ExtraContext


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
    # Walk up to the root context to find the full config.
    root_ctx = ctx.find_root()
    full_conf = root_ctx.meta.get(context.CONF_FULL)
    if not full_conf:
        return ()

    # Extract the [click-extra.wrap.<script>] section from the raw config.
    app_name = root_ctx.command.name or ""
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
) -> None:
    """Apply Click Extra help colorization to any Click CLI.

    Wraps SCRIPT with keyword highlighting and themed styling for help
    screens. The target CLI is not modified.

    Resolution order for SCRIPT: installed console_scripts entry point,
    module:function notation, Python file path, or Python module name.
    """
    if not script_and_args:
        click.echo(ctx.get_help(), color=ctx.color)
        ctx.exit(0)

    script = script_and_args[0]
    args = script_and_args[1:]

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
    patch_click(theme=None, color=ctx.color or False)
    invoke_target(script, module_path, function_name, args)
