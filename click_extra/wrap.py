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
import runpy
import sys
from importlib import metadata
from pathlib import Path

import click
from click.utils import make_str

from . import colorize
from .colorize import ExtraHelpColorsMixin, HelpExtraTheme
from .commands import ExtraContext, ExtraGroup


# Save pristine references before any patching occurs.
_original_click_command = click.decorators.command
_original_click_group = click.decorators.group


class _PatchedCommand(ExtraHelpColorsMixin, click.Command):  # type: ignore[misc]
    """Click Command with help colorization but no extra params.

    Follows the same pattern as :class:`~click_extra.commands.HelpCommand`:
    mixes in :class:`~click_extra.colorize.ExtraHelpColorsMixin` for keyword
    highlighting and uses :class:`~click_extra.commands.ExtraContext` for the
    colorized formatter, without inheriting from ``ExtraCommand`` (which would
    inject ``default_extra_params``).
    """

    context_class: type[click.Context] = ExtraContext


class _PatchedGroup(ExtraHelpColorsMixin, click.Group):  # type: ignore[misc]
    """Click Group with help colorization but no extra params."""

    context_class: type[click.Context] = ExtraContext


class WrapperGroup(ExtraGroup):
    """ExtraGroup that falls back to the ``run`` subcommand for unknown names.

    Known subcommands (``help``, ``prebake``, ``render-matrix``) are dispatched
    normally. Anything else is treated as a target script and forwarded to
    ``run``.
    """

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        cmd_name = make_str(args[0])
        cmd = self.get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd_name, cmd, args[1:]
        # Unknown name: delegate the entire arg list to ``run``.
        run_cmd = self.get_command(ctx, "run")
        if run_cmd is not None:
            return "run", run_cmd, args
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

        _PatchedCommand.context_class = _NoColorContext
        _PatchedGroup.context_class = _NoColorContext
    else:
        _PatchedCommand.context_class = ExtraContext
        _PatchedGroup.context_class = ExtraContext

    def _patched_command_func(
        name: str | None = None,
        cls: type | None = None,
        **attrs,
    ):
        """Wrapper around ``click.command`` defaulting cls to _PatchedCommand."""
        # Handle bare @click.command usage (no parentheses): the decorated
        # function is passed as the first positional argument.
        if callable(name):
            func = name
            if cls is None:
                cls = _PatchedCommand
            return _original_click_command(cls=cls, **attrs)(func)
        if cls is None:
            cls = _PatchedCommand
        return _original_click_command(name=name, cls=cls, **attrs)

    def _patched_group_func(
        name: str | None = None,
        cls: type | None = None,
        **attrs,
    ):
        """Wrapper around ``click.group`` defaulting cls to _PatchedGroup."""
        if callable(name):
            func = name
            if cls is None:
                cls = _PatchedGroup
            return _original_click_group(cls=cls, **attrs)(func)
        if cls is None:
            cls = _PatchedGroup
        return _original_click_group(name=name, cls=cls, **attrs)

    # Replace decorator functions in both namespaces so both ``click.command``
    # and ``from click.decorators import command`` resolve to the wrappers.
    click.command = _patched_command_func  # type: ignore[assignment]
    click.group = _patched_group_func  # type: ignore[assignment]
    click.decorators.command = _patched_command_func  # type: ignore[assignment]
    click.decorators.group = _patched_group_func  # type: ignore[assignment]

    # Override the default theme if requested.
    if theme is not None:
        colorize.default_theme = theme


def unpatch_click() -> None:
    """Restore Click's original decorator functions.

    Reverses the changes made by :func:`patch_click`. Useful in tests to
    avoid leaking global state between test cases.
    """
    click.command = _original_click_command  # type: ignore[assignment]
    click.group = _original_click_group  # type: ignore[assignment]
    click.decorators.command = _original_click_command
    click.decorators.group = _original_click_group

    # Reset context classes to defaults.
    _PatchedCommand.context_class = ExtraContext
    _PatchedGroup.context_class = ExtraContext

    # Restore the default theme.
    colorize.default_theme = HelpExtraTheme.dark()


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
    # 1. Console scripts entry points.
    for ep in metadata.entry_points().select(group="console_scripts"):
        if ep.name == script:
            module_path, _, function_name = ep.value.partition(":")
            return module_path, function_name

    # 2. Explicit module:function notation.
    if ":" in script:
        module_path, function_name = script.rsplit(":", 1)
        return module_path, function_name

    # 3. .py file path.
    if script.endswith(".py") and Path(script).is_file():
        return script, ""

    # 4. Bare module name. Check existence without importing so the module
    # is not loaded before patch_click() runs.
    try:
        spec = importlib.util.find_spec(script)
    except (ModuleNotFoundError, ValueError):
        spec = None

    if spec is not None:
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
    original_argv = sys.argv
    try:
        sys.argv = [script, *args]

        if function_name:
            mod = importlib.import_module(module_path)
            func = getattr(mod, function_name)
            func()
        elif module_path.endswith(".py"):
            runpy.run_path(module_path, run_name="__main__")
        else:
            runpy.run_module(module_path, run_name="__main__")
    finally:
        sys.argv = original_argv


@click.command(
    name="run",
    cls=_PatchedCommand,
    context_settings={"allow_interspersed_args": False},
)
@click.argument(
    "script_and_args",
    nargs=-1,
    type=click.UNPROCESSED,
    metavar="SCRIPT [ARGS]...",
)
@click.option(
    "--theme",
    type=click.Choice(("dark", "light"), case_sensitive=False),
    default="dark",
    help="Color theme preset.",
)
@click.pass_context
def run(
    ctx: click.Context,
    script_and_args: tuple[str, ...],
    theme: str,
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

    module_path, function_name = resolve_target(script)

    help_theme = (
        HelpExtraTheme.light() if theme == "light" else HelpExtraTheme.dark()
    )
    # Color setting is inherited from the parent group's context, where
    # ColorOption already processed --color/--no-color flags and environment
    # variables (NO_COLOR, CLICOLOR, etc.).
    patch_click(theme=help_theme, color=ctx.color)
    invoke_target(script, module_path, function_name, args)
