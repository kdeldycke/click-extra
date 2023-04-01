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

__version__ = "3.9.0"
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
from cloup import (  # noqa: E402
    Argument,
    Command,
    Group,
    HelpFormatter,
    HelpTheme,
    Option,
    Style,
    argument,
    option,
    option_group,
)

from .colorize import ColorOption, HelpOption  # noqa: I001, E402
from .commands import TimerOption  # noqa: I001, E402
from .config import ConfigOption, ShowParamsOption  # noqa: I001, E402
from .decorators import (  # type: ignore # noqa: I001, E402
    color_option,
    command,  # noqa: E402
    config_option,
    extra_command,
    extra_group,
    group,  # noqa: E402
    help_option,
    show_params_option,
    table_format_option,
    timer_option,
    verbosity_option,
    version_option,
)
from .logging import VerbosityOption  # noqa: I001, E402
from .parameters import ExtraOption  # noqa: I001, E402
from .version import VersionOption  # noqa: I001, E402

__all__ = [  # noqa: F405
    "Abort",
    "Argument",
    "argument",
    "BadArgumentUsage",
    "BadOptionUsage",
    "BadParameter",
    "BaseCommand",
    "BOOL",
    "Choice",
    "clear",
    "ClickException",
    "color_option",
    "ColorOption",
    "command",
    "Command",
    "CommandCollection",
    "config_option",
    "ConfigOption",
    "confirm",
    "confirmation_option",
    "Context",
    "DateTime",
    "echo",
    "echo_via_pager",
    "edit",
    "extra_command",
    "extra_group",
    "ExtraOption",
    "File",
    "FileError",
    "FLOAT",
    "FloatRange",
    "format_filename",
    "get_app_dir",
    "get_binary_stream",
    "get_current_context",
    "get_text_stream",
    "getchar",
    "group",
    "Group",
    "help_option",
    "HelpFormatter",
    "HelpOption",
    "HelpTheme",
    "INT",
    "IntRange",
    "launch",
    "make_pass_decorator",
    "MissingParameter",
    "MultiCommand",
    "NoSuchOption",
    "open_file",
    "option",
    "Option",
    "option_group",
    "OptionParser",
    "Parameter",
    "ParameterSource",
    "ParamType",
    "pass_context",
    "pass_obj",
    "password_option",
    "Path",
    "pause",
    "progressbar",
    "prompt",
    "secho",
    "show_params_option",
    "ShowParamsOption",
    "STRING",
    "style",
    "Style",
    "table_format_option",
    "timer_option",
    "TimerOption",
    "Tuple",
    "UNPROCESSED",
    "unstyle",
    "UsageError",
    "UUID",
    "verbosity_option",
    "VerbosityOption",
    "version_option",
    "VersionOption",
    "wrap_text",
]
