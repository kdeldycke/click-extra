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
"""Gather CLI metadata and print them."""

from __future__ import annotations

import inspect
import logging
import os
import re
from functools import cached_property
from gettext import gettext as _
from importlib import metadata
from typing import TYPE_CHECKING, cast

import click
from boltons.ecoutils import get_profile

from . import Context, Parameter, Style, echo, get_current_context
from .colorize import default_theme
from .parameters import ExtraOption

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import FrameType, ModuleType

    from cloup.styling import IStyle


class ExtraVersionOption(ExtraOption):
    """Gather CLI metadata and prints a colored version string.

    .. warning::
        This started as a `copy of the standard @click.version_option() decorator
        <https://github.com/pallets/click/blob/dc918b4/src/click/decorators.py#L399-L466>`_,
        but is **no longer a drop-in replacement**. Hence the ``Extra`` prefix.

        Still, we'll keep an eye on the original implementation to backport fixes and
        improvements.

    .. important::
        This option has been made into a class here, to allow its use with the
        declarative ``params=`` argument. Which `fixes Click #2324 issue
        <https://github.com/pallets/click/issues/2324>`_.

    .. note::
        This address `click#2331 issue <https://github.com/pallets/click/issues/2331>`_,
        by distingushing the module from the package.
    """

    template_keys: tuple[str] = (
        "module",
        "module_name",
        "module_path",
        "module_version",
        "package_name",
        "package_version",
        "exec_name",
        "version",
        "prog_name",
        "env_info",
    )
    """List of variables available for the message template."""

    message: str = _("%(prog_name)s, version %(version)s")
    """Default message template used to render the version string."""

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        # Variable ovverrides.
        module: str | None = None,
        module_name: str | None = None,
        module_path: str | None = None,
        module_version: str | None = None,
        package_name: str | None = None,
        package_version: str | None = None,
        exec_name: str | None = None,
        version: str | None = None,
        prog_name: str | None = None,
        env_info: dict[str, str] | None = None,
        message: str | None = None,
        # Variable's styles.
        module_style: IStyle | None = None,
        module_name_style: IStyle | None = default_theme.invoked_command,
        module_path_style: IStyle | None = None,
        module_version_style: IStyle | None = Style(fg="green"),
        package_name_style: IStyle | None = default_theme.invoked_command,
        package_version_style: IStyle | None = Style(fg="green"),
        exec_name_style: IStyle | None = default_theme.invoked_command,
        version_style: IStyle | None = Style(fg="green"),
        prog_name_style: IStyle | None = default_theme.invoked_command,
        env_info_style: IStyle | None = Style(fg="bright_black"),
        message_style: IStyle | None = None,
        is_flag=True,
        expose_value=False,
        is_eager=True,
        help=_("Show the version and exit."),
        **kwargs,
    ) -> None:
        """Adds a couple of extra parameters to the standard ``click.version_option``.

        :param version: forces the value of ``%(version)s``.
        :param package_name: forces the value of ``%(package_name)s``.
        :param prog_name: forces the value of ``%(prog_name)s``.
        :param env_info: forces the value of ``%(env_info)s``.
        :param message: the message template to print. Defaults to
            ``%(prog_name)s, version %(version)s``.

        :param version_style: style of ``%(version)s``.
        :param package_name_style: style of ``%(package_name)s``.
        :param prog_name_style: style of ``%(prog_name)s``.
        :param env_info_style: style of ``%(env_info)s``.
        :param message_style: default style of rest of the message.

        For other params `see Click's version_option decorator
        <https://click.palletsprojects.com/en/8.1.x/api/#click.version_option>`_.
        """
        if not param_decls:
            param_decls = ("--version",)

        # Use the user-provided values instead of relying on auto-detection and
        # defaults.
        for var in self.template_keys:
            var_value = locals().get(var)
            if var_value:
                setattr(self, var, var_value)
        if message:
            self.message = message

        # Save the styles for later use.
        for var in self.template_keys:
            setattr(self, f"{var}_style", locals()[f"{var}_style"])
        self.message_style = message_style

        kwargs.setdefault("callback", self.print_and_exit)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )

    @staticmethod
    def cli_frame() -> FrameType:
        """Returns the frame in which the CLI is implemented.

        Inspects the execution stack frames to find the package in which the user's CLI
        is implemented.

        Returns the frame name, the frame itself, and the frame chain for debugging.
        """
        logging.getLogger("click_extra")

        # Walk the execution stack from bottom to top.
        frame_number = 0
        for frame_info in inspect.stack():
            frame = frame_info.frame

            # Get the current package name from the frame's globals.
            frame_name = frame.f_globals["__name__"]

            # Get the current function name.
            func_name = frame_info.function

            # Keep track of inspected frames.
            frame_number += 1

            # Stop at the invoke() function of any CliRunner class, which is used for
            # testing.
            if func_name == "invoke" and isinstance(
                frame.f_locals.get("self"),
                click.testing.CliRunner,
            ):
                pass

            # Skip the intermediate frames added by the `@cached_property` decorator
            # and the Click ecosystem.
            elif frame_name.startswith(("functools", "click_extra", "cloup", "click")):
                continue

            # We found the frame where the CLI is implemented.
            return frame
        return None

    @cached_property
    def module(self) -> ModuleType:
        """Returns the module in which the CLI resides."""
        frame = self.cli_frame()

        module = inspect.getmodule(frame)
        if not module:
            msg = f"Cannot find module of {frame!r}"
            raise RuntimeError(msg)

        return module

    @cached_property
    def module_name(self) -> str:
        """Returns the full module name or ``__main__`."""
        return self.module.__name__

    @cached_property
    def module_path(self) -> str:
        """Returns the module's full path."""
        return self.module.__file__

    @cached_property
    def module_version(self) -> str | None:
        """Returns the string found in the local ``__version__`` variable."""
        version = getattr(self.module, "__version__", None)
        if version is not None and not isinstance(version, str):
            msg = f"Module version {version!r} is not a string."
            raise ValueError(msg)
        return version

    @cached_property
    def package_name(self) -> str | None:
        """Returns the package name."""
        return self.module.__package__

    @cached_property
    def package_version(self) -> str:
        """Returns the package version if installed.

        Will raise an error if the package is not installed, or if the package version
        cannot be determined from the package metadata.
        """
        if not self.package_name:
            return None

        try:
            version = metadata.version(self.package_name)
        except metadata.PackageNotFoundError:
            msg = (
                f"{self.package_name!r} is not installed. Try passing "
                "'package_name' instead."
            )
            raise RuntimeError(msg) from None

        if not version:
            msg = (
                f"Could not determine the version for {self.package_name!r} "
                "automatically."
            )
            raise RuntimeError(msg)

        return version

    @cached_property
    def exec_name(self) -> str:
        """User-friendly name of the executed CLI.

        Returns the module name. But if the later is ``__main__``, returns the package
        name.

        If not packaged, the CLI is assumed to be a simple standalone script, and the
        returned name is the script's file name (including its extension).
        """
        # The CLI has its own module.
        if self.module_name != "__main__":
            return self.module_name

        # The CLI module is a `__main__` entry-point, so returns its package name.
        if self.package_name:
            return self.package_name

        # The CLI is not packaged: it is a standalone script. Fallback to its
        # filename.
        filename = os.path.basename(self.module_path)
        if filename:
            return filename

        msg = (
            "Could not determine the user-friendly name of the CLI from the frame "
            "stack."
        )
        raise RuntimeError(msg)

    @cached_property
    def version(self) -> str | None:
        """Return the version of the CLI.

        Returns the module version if a ``__version__`` variable is set alongside the
        CLI in its module.

        Else returns the package version if the CLI is implemented in a package, using
        `importlib.metadata.version()
        <https://docs.python.org/3/library/importlib.metadata.html?highlight=metadata#distribution-versions>`_.
        """
        if self.module_version:
            return self.module_version

        if self.package_version:
            return self.package_version

        return None

    @cached_property
    def prog_name(self) -> str | None:
        """Return the name of the CLI, from Click's point of view."""
        return get_current_context().find_root().info_name

    @cached_property
    def env_info(self) -> dict[str, str]:
        """Various environment info.

        Returns the data produced by `boltons.ecoutils.get_profile()
        <https://boltons.readthedocs.io/en/latest/ecoutils.html#boltons.ecoutils.get_profile>`_.
        """
        return cast("dict[str, str]", get_profile(scrub=True))

    def colored_template(self, template: str | None = None) -> str:
        """Insert ANSI style to a message template.

        Accepts a custom ``template`` as parameter, otherwise uses the default message
        defined on the instance.
        """
        if template is None:
            template = self.message

        # Map the template parts to their style function.
        part_vars = {
            f"%({var})s": getattr(self, f"{var}_style")
            for var in self.template_keys
        }
        part_regex = re.compile("(" + "|".join(map(re.escape, part_vars)) + ")")

        colored_template = ""
        for part in re.split(part_regex, template):
            # Skip empty strings.
            if not part:
                continue
            # Get the style function for this part, defaults to `self.message_style`.
            style_func = part_vars.get(part, self.message_style)
            # Apply the style function if any, otherwise just append the part.
            colored_template += style_func(part) if style_func else part

        return colored_template

    def render_message(self, template: str | None = None) -> str:
        """Render the version string from the provided template.

        Accepts a custom ``template`` as parameter, otherwise uses the default
        ``self.colored_template()`` defined on the instance.
        """
        if template is None:
            template = self.colored_template()

        return template % {
            var: getattr(self, var)
            for var in self.template_keys
        }

    def print_and_exit(
        self,
        ctx: Context,
        param: Parameter,
        value: bool,
    ) -> None:
        """Print the version string and exits.

        Also stores all version string elements in the Context's ``meta`` `dict`.
        """
        # Populate the context's meta dict with the version string elements.
        for var in self.template_keys:
            ctx.meta[f"click_extra.{var}"] = getattr(self, var)

        if not value or ctx.resilient_parsing:
            return

        echo(self.render_message(), color=ctx.color)

        ctx.exit()
        return  # type: ignore[unreachable]
