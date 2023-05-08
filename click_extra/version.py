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
"""Extraction of CLI's version and its printing."""

from __future__ import annotations

import inspect
import re
from gettext import gettext as _
from importlib import metadata
from typing import Sequence

from boltons.ecoutils import get_profile

from . import Context, Parameter, Style, echo
from .colorize import default_theme
from .parameters import ExtraOption


class VersionOption(ExtraOption):
    """Prints the colored version of the CLI.

    .. warning::
        This is a `copy of the standard @click.version_option() decorator
        <https://github.com/pallets/click/blob/dc918b48fb9006be683a684b42cc7496ad649b83/src/click/decorators.py#L399-L466>`_.

        It has been made into a class here, to allow its use with the declarative
        ``params=`` argument. Which `fixes Click #2324 issue
        <https://github.com/pallets/click/issues/2324>`_.
    """

    version: str | None = None
    package_name: str | None = None
    prog_name: str | None = None
    message: str = _("%(prog)s, version %(version)s")

    def guess_package_name(self):
        package_name = None

        frame = inspect.currentframe()
        f_back = frame.f_back if frame is not None else None
        f_globals = f_back.f_globals if f_back is not None else None
        # break reference cycle
        # https://docs.python.org/3/library/inspect.html#the-interpreter-stack
        del frame

        if f_globals is not None:
            package_name = f_globals.get("__name__")

            if package_name == "__main__":
                package_name = f_globals.get("__package__")

            if package_name:
                package_name = package_name.partition(".")[0]

        return package_name

    def print_version(
        self,
        ctx: Context,
        param: Parameter,
        value: bool,
        capture_output: bool = False,
    ) -> str | None:
        """Prints version and exits.

        Standard callback with an extra ``capture_output`` parameter which returns the
        output string instead of printing the (colored) version to the console.
        """
        if not value or ctx.resilient_parsing:
            return None

        if self.prog_name is None:
            self.prog_name = ctx.find_root().info_name

        if self.version is None and self.package_name is not None:
            try:
                self.version = metadata.version(self.package_name)
            except metadata.PackageNotFoundError:
                raise RuntimeError(
                    f"{self.package_name!r} is not installed. Try passing"
                    " 'package_name' instead."
                ) from None

        if self.version is None:
            raise RuntimeError(
                f"Could not determine the version for "
                f"{self.package_name!r} automatically."
            )

        output = self.message % {
            "prog": self.prog_name,
            "package": self.package_name,
            "version": self.version,
        }

        if capture_output:
            return output

        echo(output, color=ctx.color)

        # Do not just ctx.exit() as it will prevent callbacks defined on options
        # to be called.
        ctx.close()
        ctx.exit()

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        version: str | None = None,
        package_name: str | None = None,
        prog_name: str | None = None,
        message: str | None = None,
        print_env_info: bool = False,
        version_style=Style(fg="green"),
        package_name_style=default_theme.invoked_command,  # type: ignore[has-type]
        prog_name_style=default_theme.invoked_command,  # type: ignore[has-type]
        message_style=None,
        env_info_style=Style(fg="bright_black"),
        is_flag=True,
        expose_value=False,
        is_eager=True,
        help=_("Show the version and exit."),
        **kwargs,
    ) -> None:
        """Adds a couple of extra parameters to the standard ``click.version_option``.

        :param version_style: adds environment info at the end of the message. Useful to
            gather user's details for troubleshooting. Defaults to
            ``Style(fg="green")``.
        :param package_name_style: style of the ``version``. Defaults to
            ``default_theme.invoked_command``.
        :param prog_name_style: style of the ``prog_name``. Defaults to
            ``default_theme.invoked_command``.
        :param message_style: default style of the ``message`` parameter. Defaults to
            ``None``.
        :param env_info_style: style of the environment info. Defaults to
            ``Style(fg="bright_black")``.

        For other params `see Click's version_option decorator
        <https://click.palletsprojects.com/en/8.1.x/api/#click.version_option>`_.
        """
        if not param_decls:
            param_decls = ("--version",)

        kwargs.setdefault("callback", self.print_version)

        self.version = version
        self.package_name = package_name
        self.prog_name = prog_name
        if message:
            self.message = message

        if self.version is None and self.package_name is None:
            self.package_name = self.guess_package_name()

        if print_env_info:
            env_info = "\n" + str(get_profile(scrub=True))
            if env_info_style:
                env_info = env_info_style(env_info)
            self.message += env_info

        colorized_message = ""
        for part in re.split(r"(%\(version\)s|%\(package\)s|%\(prog\)s)", self.message):
            # Skip empty strings.
            if not part:
                continue
            if part == "%(package)s" and package_name_style:
                part = package_name_style(part)
            elif part == "%(prog)s" and prog_name_style:
                part = prog_name_style(part)
            elif part == "%(version)s" and version_style:
                part = version_style(part)
            elif message_style:
                part = message_style(part)
            colorized_message += part
        if colorized_message:
            self.message = colorized_message

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )
