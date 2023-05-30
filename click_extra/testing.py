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
"""All utilities to test CLIs."""

from __future__ import annotations

from typing import IO, Any, Mapping, Optional, Sequence

import click
import click.testing
from boltons.tbutils import ExceptionInfo

from .run import EnvVars


class ExtraCliRunner(click.testing.CliRunner):
    """Extends Click's ``CliRunner`` to add extra features:

    - Adds a ``force_color`` property
    - Sets ``mix_stderr`` to ``False`` by default
    """

    force_color: bool = False
    """Flag to override the ``color`` parameter in ``invoke``.

    .. note::
        This is only used to initialize the ``CliRunner`` `in the context of Sphinx
        documentation <sphinx#click_extra.sphinx.setup>`_.
    """

    def __init__(
        self,
        charset: str = "utf-8",
        env: Optional[Mapping[str, Optional[str]]] = None,
        echo_stdin: bool = False,
        # Set to False to avoid mixing stdout and stderr in the result object.
        mix_stderr: bool = False,
    ) -> None:
        return super().__init__(
            charset=charset,
            env=env,
            echo_stdin=echo_stdin,
            mix_stderr=mix_stderr
        )

    def invoke(
        self,
        cli: click.core.BaseCommand,
        args: str | Sequence[str] | None = None,
        input: str | bytes | IO | None = None,
        env: EnvVars | None = None,
        catch_exceptions: bool = True,
        color: bool = False,
        **extra: Any,
    ) -> click.testing.Result:
        """Same as ``click.testing.CliRunner.invoke()`` with extra features.

        - Activates ``color`` property depending on the ``force_color`` value.
        - Prints a formatted exception traceback if the command fails.
        """
        if self.force_color:
            color = True

        result = super().invoke(
            cli=cli,
            args=args,
            input=input,
            env=env,
            catch_exceptions=catch_exceptions,
            color=color,
            **extra,
        )

        if result.exception:
            print(ExceptionInfo.from_exc_info(*result.exc_info).get_formatted())

        return result

