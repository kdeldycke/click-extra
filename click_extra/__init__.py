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

__version__ = "3.10.0"
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
# Overrides click helpers with cloup's.
from click import *  # noqa: E402, F403
from click.core import ParameterSource  # noqa: E402, F401
from cloup import *  # noqa: E402, F403

from .colorize import ColorOption, HelpOption  # noqa: I001, E402, F401
from .commands import TimerOption  # noqa: I001, E402, F401
from .config import ConfigOption, ShowParamsOption  # noqa: I001, E402, F401
from .decorators import (  # type: ignore # noqa: I001, E402, F401
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
from .logging import VerbosityOption  # noqa: I001, E402, F401
from .parameters import ExtraOption  # noqa: I001, E402, F401
from .version import VersionOption  # noqa: I001, E402, F401

# Expose all of Click, Cloup and Click Extra.
__all__ = [  # noqa: F405
    "Abort",
    "Argument",
    "BOOL",
    "BadArgumentUsage",
    "BadOptionUsage",
    "BadParameter",
    "BaseCommand",
    "Choice",
    "ClickException",
    # XXX Color cannot be imported from cloup. It leads to an issue in the way autodoc
    # is trying to render it:
    #   Exception occurred:
    #     File ".../python3.11/site-packages/cloup/_util.py", line 128, in __setattr__
    #       raise Exception("you can't set attributes on this class")
    #   Exception: you can't set attributes on this class
    # "Color",
    "ColorOption",
    "Command",
    "CommandCollection",
    "ConfigOption",
    "ConstraintMixin",
    "Context",
    "DateTime",
    "ExtraOption",
    "FLOAT",
    "File",
    "FileError",
    "FloatRange",
    "Group",
    "HelpFormatter",
    "HelpOption",
    "HelpSection",
    "HelpTheme",
    "INT",
    "IntRange",
    "MissingParameter",
    "MultiCommand",
    "NoSuchOption",
    "Option",
    "OptionGroup",
    "OptionGroupMixin",
    "OptionParser",
    "ParamType",
    "Parameter",
    "ParameterSource",
    "Path",
    "STRING",
    "Section",
    "SectionMixin",
    "ShowParamsOption",
    "Style",
    "TimerOption",
    "Tuple",
    "UNPROCESSED",
    "UUID",
    "UsageError",
    "VerbosityOption",
    "VersionOption",
    "argument",
    "clear",
    "color_option",
    "command",
    "config_option",
    "confirm",
    "confirmation_option",
    "constrained_params",
    "constraint",
    "dir_path",
    "echo",
    "echo_via_pager",
    "edit",
    "extra_command",
    "extra_group",
    "file_path",
    "format_filename",
    "get_app_dir",
    "get_binary_stream",
    "get_current_context",
    "get_text_stream",
    "getchar",
    "group",
    "help_option",
    "launch",
    "make_pass_decorator",
    "open_file",
    "option",
    "option_group",
    "pass_context",
    "pass_obj",
    "password_option",
    "path",
    "pause",
    "progressbar",
    "prompt",
    "secho",
    "show_params_option",
    "style",
    "table_format_option",
    "timer_option",
    "unstyle",
    "verbosity_option",
    "version_option",
    "warnings",
    "wrap_text",
]
"""
..note::
    The content of ``__all__` is checked and enforced in unittests.
"""
