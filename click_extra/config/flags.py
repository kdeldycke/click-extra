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
"""Translate a configuration table into command-line flags."""

from __future__ import annotations

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any


def config_table_to_flags(table: Mapping[str, Any]) -> list[str]:
    """Translate a mapping of configuration keys into long-form CLI flags.

    For tools whose command-line options mirror their configuration keys but
    which cannot read the table themselves (no `--config` support, no native
    config file). Follows the conventional mapping:

    - `key = True` → `--key`
    - `key = "value"` (or a number) → `--key=value`
    - `key = ["a", "b"]` → `--key=a --key=b` (one flag per item)
    - `key = False` is skipped: there is no universal `--no-<key>` form.

    Keys keep their spelling, so hyphenated keys map straight onto long options,
    and flags follow the mapping's iteration order.

    :param table: The configuration keys and values, like a parsed `[tool.X]`
        section.
    :return: The equivalent list of `--flag` / `--flag=value` arguments.
    """
    args: list[str] = []
    for key, value in table.items():
        # bool must precede the scalar fallback: it subclasses int, and only a
        # truthy flag maps to a bare `--key`.
        if isinstance(value, bool):
            if value:
                args.append(f"--{key}")
        elif isinstance(value, (list, tuple)):
            args.extend(f"--{key}={item}" for item in value)
        else:
            args.append(f"--{key}={value}")
    return args
