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
from functools import cached_property
from gettext import gettext as _
from importlib import metadata
from typing import TYPE_CHECKING, cast

import click
from boltons.ecoutils import get_profile
from boltons.formatutils import BaseFormatField, tokenize_format_str

from . import Context, Parameter, Style, echo, get_current_context
from .colorize import default_theme
from .parameters import ExtraOption

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import FrameType, ModuleType

    from cloup.styling import IStyle


class ExtraVersionOption(ExtraOption):
    """Gather CLI metadata and prints a colored version string.

    .. note::
        This started as a `copy of the standard @click.version_option() decorator
        <https://github.com/pallets/click/blob/dc918b4/src/click/decorators.py#L399-L466>`_,
        but is **no longer a drop-in replacement**. Hence the ``Extra`` prefix.

        This address the following Click issues:

        - `click#2324 <https://github.com/pallets/click/issues/2324>`_,
          to allow its use with the declarative ``params=`` argument.

        - `click#2331 <https://github.com/pallets/click/issues/2331>`_,
          by distinguishing the module from the package.

        - `click#1756 <https://github.com/pallets/click/issues/1756>`_,
          by allowing path and Python version.
    """

    message: str = _("{prog_name}, version {version}")
    """Default message template used to render the version string."""

    template_fields: tuple[str, ...] = (
        "module",
        "module_name",
        "module_file",
        "module_version",
        "package_name",
        "package_version",
        "exec_name",
        "version",
        "prog_name",
        "env_info",
    )
    """List of field IDs recognized by the message template."""

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        message: str | None = None,
        # Field value overrides.
        module: str | None = None,
        module_name: str | None = None,
        module_file: str | None = None,
        module_version: str | None = None,
        package_name: str | None = None,
        package_version: str | None = None,
        exec_name: str | None = None,
        version: str | None = None,
        prog_name: str | None = None,
        env_info: dict[str, str] | None = None,
        # Field style overrides.
        message_style: IStyle | None = None,
        module_style: IStyle | None = None,
        module_name_style: IStyle | None = default_theme.invoked_command,
        module_file_style: IStyle | None = None,
        module_version_style: IStyle | None = Style(fg="green"),
        package_name_style: IStyle | None = default_theme.invoked_command,
        package_version_style: IStyle | None = Style(fg="green"),
        exec_name_style: IStyle | None = default_theme.invoked_command,
        version_style: IStyle | None = Style(fg="green"),
        prog_name_style: IStyle | None = default_theme.invoked_command,
        env_info_style: IStyle | None = Style(fg="bright_black"),
        is_flag=True,
        expose_value=False,
        is_eager=True,
        help=_("Show the version and exit."),
        **kwargs,
    ) -> None:
        """Preconfigured as a ``--version`` option flag.

        :param message: the message template to print, in `format string syntax
            <https://docs.python.org/3/library/string.html#format-string-syntax>`_.
            Defaults to ``{prog_name}, version {version}``.

        :param module: forces the value of ``{module}``.
        :param module_name: forces the value of ``{module_name}``.
        :param module_file: forces the value of ``{module_file}``.
        :param module_version: forces the value of ``{module_version}``.
        :param package_name: forces the value of ``{package_name}``.
        :param package_version: forces the value of ``{package_version}``.
        :param exec_name: forces the value of ``{exec_name}``.
        :param version: forces the value of ``{version}``.
        :param prog_name: forces the value of ``{prog_name}``.
        :param env_info: forces the value of ``{env_info}``.

        :param message_style: default style of the message.

        :param module_style: style of ``{module}``.
        :param module_name_style: style of ``{module_name}``.
        :param module_file_style: style of ``{module_file}``.
        :param module_version_style: style of ``{module_version}``.
        :param package_name_style: style of ``{package_name}``.
        :param package_version_style: style of ``{package_version}``.
        :param exec_name_style: style of ``{exec_name}``.
        :param version_style: style of ``{version}``.
        :param prog_name_style: style of ``{prog_name}``.
        :param env_info_style: style of ``{env_info}``.
        """
        if not param_decls:
            param_decls = ("--version",)

        if message is not None:
            self.message = message

        self.message_style = message_style

        # Overrides default field's value and style with user-provided parameters.
        for field_id in self.template_fields:
            # Override field value.
            user_value = locals().get(field_id)
            if user_value is not None:
                setattr(self, field_id, user_value)

            # Set field style.
            style_id = f"{field_id}_style"
            setattr(self, style_id, locals()[style_id])

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
        # Keep a list of all frames inspected for debugging.
        frame_chain: list[tuple[str, str]] = []

        # Walk the execution stack from bottom to top.
        for frame_info in inspect.stack():
            frame = frame_info.frame

            # Get the current package name from the frame's globals.
            frame_name = frame.f_globals["__name__"]

            # Get the current function name.
            func_name = frame_info.function

            # Keep track of the inspected frames.
            frame_chain.append((frame_name, func_name))

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

        # Our heuristics to locate the CLI implementation failed.
        logger = logging.getLogger("click_extra")
        count_size = len(str(len(frame_chain)))
        for counter, (p_name, f_name) in enumerate(frame_chain):
            logger.debug(f"Frame {counter:<{count_size}} # {p_name}:{f_name}")
        msg = "Could not find the frame in which the CLI is implemented."
        raise RuntimeError(msg)

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
    def module_file(self) -> str | None:
        """Returns the module's file full path."""
        return self.module.__file__

    @cached_property
    def module_version(self) -> str | None:
        """Returns the string found in the local ``__version__`` variable."""
        version = getattr(self.module, "__version__", None)
        if version is not None and not isinstance(version, str):
            msg = f"Module version {version!r} expected to be a string or None."
            raise ValueError(msg)
        return version

    @cached_property
    def package_name(self) -> str | None:
        """Returns the package name."""
        return self.module.__package__

    @cached_property
    def package_version(self) -> str | None:
        """Returns the package version if installed."""
        logger = logging.getLogger("click_extra")

        if not self.package_name:
            logger.debug("Cannot guess version from package: no package name provided.")
            return None

        try:
            version = metadata.version(self.package_name)
        except metadata.PackageNotFoundError:
            logger.debug(
                f"Cannot get version: {self.package_name!r} package not found or not "
                "installed."
            )
            return None

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
        if self.module_file:
            return os.path.basename(self.module_file)

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
        """Insert ANSI styles to a message template.

        Accepts a custom ``template`` as parameter, otherwise uses the default message
        defined on the Option instance.

        This step is necessary because we need to linearize the template to apply the
        ANSI codes on the string segments. This is a consequence of the nature of ANSI,
        directives which cannot be encapsulated within another (unlike markup tags
        like HTML).
        """
        if template is None:
            template = self.message

        # Normalize the default to a no-op Style() callable to simplify the code
        # of the colorization step.
        def noop(s: str) -> str:
            return s

        default_style = self.message_style if self.message_style else noop

        # Associate each field with its own style.
        field_styles = {}
        for field_id in self.template_fields:
            field_style = getattr(self, f"{field_id}_style")
            # If no style is defined for this field, use the default style of the
            # message.
            if not field_style:
                field_style = default_style
            field_styles[field_id] = field_style

        # Split the template semantically between fields and literals.
        segments = tokenize_format_str(template, resolve_pos=False)

        # A copy of the template, where literals and fields segments are colored.
        colored_template = ""

        # Apply styles to field and literal segments.
        literal_accu = ""
        for i, segment in enumerate(segments):
            # Is the segment a format field?
            is_field = isinstance(segment, BaseFormatField)
            # If not, keep accumulating literal strings until the next field.
            if not is_field:
                # Re-escape literal curly braces to avoid messing up the format.
                literal_accu += segment.replace("{", "{{").replace("}", "}}")

            # Dump the accumulated literals before processing the field, or at the end
            # of the template.
            is_last_segment = i + 1 == len(segments)
            if (is_field or is_last_segment) and literal_accu:
                # Colorize literals with the default style.
                colored_template += default_style(literal_accu)
                # Reset the accumulator.
                literal_accu = ""

            # Add the field to the template copy, colored with its own style.
            if is_field:
                colored_template += field_styles[segment.base_name](str(segment))

        return colored_template

    def render_message(self, template: str | None = None) -> str:
        """Render the version string from the provided template.

        Accepts a custom ``template`` as parameter, otherwise uses the default
        ``self.colored_template()`` produced by the instance.
        """
        if template is None:
            template = self.colored_template()

        return template.format(**{v: getattr(self, v) for v in self.template_fields})

    def print_debug_message(self) -> None:
        """Render in debug logs all template fields in color.

        .. todo::
            Pretty print JSON output (easier to read in bug reports)?
        """
        logger = logging.getLogger("click_extra")
        if logger.getEffectiveLevel() == logging.DEBUG:
            all_fields = {
                f"{{{{{field_id}}}}}": f"{{{field_id}}}"
                for field_id in self.template_fields
            }
            max_len = max(map(len, all_fields))
            raw_format = "\n".join(
                f"{k:<{max_len}}: {v}" for k, v in all_fields.items()
            )
            msg = self.render_message(self.colored_template(raw_format))
            logger.debug("Version string template variables:")
            for line in msg.splitlines():
                logger.debug(line)

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
        for var in self.template_fields:
            ctx.meta[f"click_extra.{var}"] = getattr(self, var)

        # Always print debug messages, even if --version is not called.
        self.print_debug_message()

        if not value or ctx.resilient_parsing:
            # Do not print the version and continue normal CLI execution.
            return

        echo(self.render_message(), color=ctx.color)

        # XXX Despite monkey-patching of click.Context.exit to force closing before
        # exit, we still need to force it here for unknown reason. 🤷
        # See: https://github.com/pallets/click/pull/2680
        ctx.close()
        ctx.exit()
