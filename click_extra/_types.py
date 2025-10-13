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
"""Custom types used across the package.

Inspired by `how tomllib does it in the stdlib
<https://github.com/python/cpython/tree/main/Lib/tomllib>`_.

.. hint::
    These type are designed to be imported as follows:

    .. code-block:: python

        TYPE_CHECKING = False
        if TYPE_CHECKING:
            from typing import Sequence, ...

            from ._types import TEnvVarID, TNestedArgs, ...

    `Mypy is able to pick them up correctly
    <https://mypy.readthedocs.io/en/stable/common_issues.html#python-version-and-system-platform-checks>`_
    because ``TYPE_CHECKING`` is always evaluated to ``False`` at runtime, and to
    ``True`` `during static analysis
    <https://github.com/python/mypy/blob/6aa44da/mypy/reachability.py#L152>`_.
"""

from __future__ import annotations

from logging import Formatter, Handler
from pathlib import Path
from typing import Iterable, Mapping, TypeVar

# click_extra.envvar module.

TEnvVarID = str | None
"""Type of environment variable names."""

TEnvVarIDs = Iterable[TEnvVarID]
TNestedEnvVarIDs = Iterable[TEnvVarID | Iterable["TNestedEnvVarIDs"]]
"""Types for arbitrary nested environment variable names."""

TEnvVars = Mapping[str, str | None]
"""Type for ``dict``-like environment variables."""


# click_extra.logging module.

TFormatter = TypeVar("TFormatter", bound=Formatter)
THandler = TypeVar("THandler", bound=Handler)
"""Used in type hints in `click_extra.logging.extraBasicConfig()`.

.. warning::
    This is a workaround for the fact that `typing.TypeVar` cannot be
    parameterized with concrete types, and that `typing.Type` cannot be
    parameterized with `typing.TypeVar`.

    Else, we would have used `typing.Type[Formatter]` and
    `typing.Type[Handler]` directly.
"""


# click_extra.testing module.

TArg = str | Path | None
TArgs = Iterable[TArg]
TNestedArgs = Iterable[TArg | Iterable["TNestedArgs"]]
"""Types for arbitrary nested CLI arguments.

Arguments can be ``str``, :py:class:`pathlib.Path` objects or ``None`` values.
"""
