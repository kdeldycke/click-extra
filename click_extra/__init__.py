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

import sys

__version__ = "4.7.0"
"""Examples of valid version strings according :pep:`440#version-scheme`:

.. code-block:: python

    __version__ = "1.2.3.dev1"  # Development release 1
    __version__ = "1.2.3a1"  # Alpha Release 1
    __version__ = "1.2.3b1"  # Beta Release 1
    __version__ = "1.2.3rc1"  # RC Release 1
    __version__ = "1.2.3"  # Final Release
    __version__ = "1.2.3.post1"  # Post Release 1
"""

if sys.version_info >= (3, 9):
    from functools import cache
else:
    from functools import lru_cache

    def cache(user_function):
        """Simple lightweight unbounded cache. Sometimes called "memoize".

        .. important::

            This is a straight `copy of the functools.cache implementation
            <https://github.com/python/cpython/blob/55a26de/Lib/functools.py#L647-L653>`_,
            which is only `available in the standard library starting with Python v3.9
            <https://docs.python.org/3/library/functools.html?highlight=caching#functools.cache>`.
        """
        return lru_cache(maxsize=None)(user_function)


# Import all click's module-level content to allow for drop-in replacement.
# XXX Star import is really badly supported by mypy for now and leads to lots of
# "Module 'XXX' has no attribute 'YYY'". See: https://github.com/python/mypy/issues/4930
# Overrides click helpers with cloup's.
from click import *  # noqa: E402, F403
from click.core import ParameterSource  # noqa: E402
from cloup import *  # type: ignore[no-redef, assignment] # noqa: E402, F403

from .colorize import (  # noqa: E402
    ColorOption,
    HelpExtraFormatter,
    HelpExtraTheme,
    HelpOption,
)
from .commands import (  # noqa: E402
    ExtraCommand,
    ExtraContext,
    ExtraGroup,
)
from .config import ConfigOption  # noqa: E402
from .decorators import (  # type: ignore[no-redef] # noqa: E402
    color_option,
    command,
    config_option,
    extra_command,
    extra_group,
    extra_version_option,
    group,
    help_option,
    show_params_option,
    table_format_option,
    telemetry_option,
    timer_option,
    verbosity_option,
)
from .logging import (  # noqa: E402
    ExtraLogFormatter,
    ExtraLogHandler,
    VerbosityOption,
    extra_basic_config,
)
from .parameters import (  # noqa: E402
    ExtraOption,
    ParamStructure,
    ShowParamsOption,
    search_params,
)
from .tabulate import TableFormatOption  # noqa: E402
from .telemetry import TelemetryOption  # noqa: E402
from .testing import ExtraCliRunner  # noqa: E402
from .timer import TimerOption  # noqa: E402
from .version import ExtraVersionOption  # noqa: E402

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
    # XXX Color cannot be imported from cloup. It leads to an issue in the way autodoc
    # is trying to render it:
    #   Exception occurred:
    #     File ".../python3.11/site-packages/cloup/_util.py", line 128, in __setattr__
    #       raise Exception("you can't set attributes on this class")
    #   Exception: you can't set attributes on this class
    # "Color",
    "color_option",
    "ColorOption",
    "Command",
    "command",
    "CommandCollection",
    "config_option",
    "ConfigOption",
    "confirm",
    "confirmation_option",
    "constrained_params",
    "constraint",
    "ConstraintMixin",
    "Context",
    "DateTime",
    "dir_path",
    "echo",
    "echo_via_pager",
    "edit",
    "extra_basic_config",
    "extra_command",
    "extra_group",
    "extra_version_option",
    "ExtraCliRunner",
    "ExtraCommand",
    "ExtraContext",
    "ExtraGroup",
    "ExtraLogFormatter",
    "ExtraLogHandler",
    "ExtraOption",
    "ExtraVersionOption",
    "File",
    "file_path",
    "FileError",
    "FLOAT",
    "FloatRange",
    "format_filename",
    "get_app_dir",
    "get_binary_stream",
    "get_current_context",
    "get_text_stream",
    "getchar",
    "Group",
    "group",
    "help_option",
    "HelpExtraFormatter",
    "HelpExtraTheme",
    "HelpFormatter",
    "HelpOption",
    "HelpSection",
    "HelpTheme",
    "INT",
    "IntRange",
    "launch",
    "make_pass_decorator",
    "MissingParameter",
    "MultiCommand",
    "NoSuchOption",
    "open_file",
    "Option",
    "option",
    "option_group",
    "OptionGroup",
    "OptionGroupMixin",
    "OptionParser",
    "Parameter",
    "ParameterSource",
    "ParamStructure",
    "ParamType",
    "pass_context",
    "pass_obj",
    "password_option",
    "Path",
    "path",
    "pause",
    "progressbar",
    "prompt",
    "search_params",
    "secho",
    "Section",
    "SectionMixin",
    "show_params_option",
    "ShowParamsOption",
    "STRING",
    "Style",
    "style",
    "table_format_option",
    "TableFormatOption",
    "telemetry_option",
    "TelemetryOption",
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
    "warnings",
    "wrap_text",
]
"""Expose all of Click, Cloup and Click Extra.

.. note::
    The content of ``__all__` is checked and enforced in unittests.
"""
