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

"""Expose package-wide elements."""

from __future__ import annotations

__version__ = "3.8.1"
"""Examples of valid version strings according :pep:`440#version-scheme`:

.. code-block:: python

    __version__ = "1.2.3.dev1"  # Development release 1
    __version__ = "1.2.3a1"  # Alpha Release 1
    __version__ = "1.2.3b1"  # Beta Release 1
    __version__ = "1.2.3rc1"  # RC Release 1
    __version__ = "1.2.3"  # Final Release
    __version__ = "1.2.3.post1"  # Post Release 1
"""

# Import all click's module-level content to allow for drop-in replacement.
# XXX Star import is really badly supported by mypy for now and leads to lots of
# "Module 'XXX' has no attribute 'YYY'". See: https://github.com/python/mypy/issues/4930
from click import *  # noqa: E402, F403
from click.core import ParameterSource  # noqa: E402

# Overrides some of click helpers with cloup's.
from cloup import (  # type: ignore # noqa: E402
    Argument,
    Command,
    Group,
    HelpFormatter,
    HelpTheme,
    Option,
    Style,
    argument,
    command,  # noqa: E402
    group,  # noqa: E402
    option,
    option_group,
)

# Replace some of click defaults with click-extra variant.
from .colorize import (  # noqa: I001, E402
    ColorOption,
    HelpOption,
    color_option,
    help_option,
)

# Import last to avoid circular dependencies.
from .commands import (  # noqa: I001, E402
    TimerOption,
    extra_command,
    extra_group,
    timer_option,
)
from .config import (  # noqa: I001, E402
    ConfigOption,
    ShowParamsOption,
    config_option,
    show_params_option,
)
from .logging import VerbosityOption, verbosity_option  # noqa: I001, E402
from .parameters import ExtraOption  # noqa: I001, E402
from .tabulate import table_format_option  # noqa: I001, E402
from .version import VersionOption, version_option  # noqa: I001, E402

__all__ = [
    "Argument",
    "argument",
    "color_option",
    "ColorOption",
    "Command",
    "command",
    "config_option",
    "ConfigOption",
    "extra_command",
    "extra_group",
    "ExtraOption",
    "group",
    "Group",
    "help_option",
    "HelpFormatter",
    "HelpOption",
    "HelpTheme",
    "Option",
    "option",
    "option_group",
    "ParameterSource",
    "show_params_option",
    "ShowParamsOption",
    "Style",
    "table_format_option",
    "timer_option",
    "TimerOption",
    "verbosity_option",
    "VerbosityOption",
    "version_option",
    "VersionOption",
]
