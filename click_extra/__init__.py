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

__version__ = "4.10.0"
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
from .decorators import (  # type: ignore[no-redef, has-type, unused-ignore] # noqa: E402
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

__all__ = [
    "Abort",  # noqa: F405
    "Argument",  # noqa: F405
    "argument",  # noqa: F405
    "BadArgumentUsage",  # noqa: F405
    "BadOptionUsage",  # noqa: F405
    "BadParameter",  # noqa: F405
    "BaseCommand",  # noqa: F405
    "BOOL",  # noqa: F405
    "Choice",  # noqa: F405
    "clear",  # noqa: F405
    "ClickException",  # noqa: F405
    "Color",  # noqa: F405
    "color_option",  # noqa: F405
    "ColorOption",  # noqa: F405
    "Command",  # noqa: F405
    "command",  # noqa: F405
    "CommandCollection",  # noqa: F405
    "config_option",  # noqa: F405
    "ConfigOption",  # noqa: F405
    "confirm",  # noqa: F405
    "confirmation_option",  # noqa: F405
    "constrained_params",  # noqa: F405
    "constraint",  # noqa: F405
    "ConstraintMixin",  # noqa: F405
    "Context",  # noqa: F405
    "DateTime",  # noqa: F405
    "dir_path",  # noqa: F405
    "echo",  # noqa: F405
    "echo_via_pager",  # noqa: F405
    "edit",  # noqa: F405
    "extra_basic_config",  # noqa: F405
    "extra_command",  # noqa: F405
    "extra_group",  # noqa: F405
    "extra_version_option",  # noqa: F405
    "ExtraCliRunner",  # noqa: F405
    "ExtraCommand",  # noqa: F405
    "ExtraContext",  # noqa: F405
    "ExtraGroup",  # noqa: F405
    "ExtraLogFormatter",  # noqa: F405
    "ExtraLogHandler",  # noqa: F405
    "ExtraOption",  # noqa: F405
    "ExtraVersionOption",  # noqa: F405
    "File",  # noqa: F405
    "file_path",  # noqa: F405
    "FileError",  # noqa: F405
    "FLOAT",  # noqa: F405
    "FloatRange",  # noqa: F405
    "format_filename",  # noqa: F405
    "get_app_dir",  # noqa: F405
    "get_binary_stream",  # noqa: F405
    "get_current_context",  # noqa: F405
    "get_text_stream",  # noqa: F405
    "getchar",  # noqa: F405
    "Group",  # noqa: F405
    "group",  # noqa: F405
    "help_option",  # noqa: F405
    "HelpExtraFormatter",  # noqa: F405
    "HelpExtraTheme",  # noqa: F405
    "HelpFormatter",  # noqa: F405
    "HelpOption",  # noqa: F405
    "HelpSection",  # noqa: F405
    "HelpTheme",  # noqa: F405
    "INT",  # noqa: F405
    "IntRange",  # noqa: F405
    "launch",  # noqa: F405
    "make_pass_decorator",  # noqa: F405
    "MissingParameter",  # noqa: F405
    "MultiCommand",  # noqa: F405
    "NoSuchOption",  # noqa: F405
    "open_file",  # noqa: F405
    "Option",  # noqa: F405
    "option",  # noqa: F405
    "option_group",  # noqa: F405
    "OptionGroup",  # noqa: F405
    "OptionGroupMixin",  # noqa: F405
    "OptionParser",  # noqa: F405
    "Parameter",  # noqa: F405
    "ParameterSource",  # noqa: F405
    "ParamStructure",  # noqa: F405
    "ParamType",  # noqa: F405
    "pass_context",  # noqa: F405
    "pass_obj",  # noqa: F405
    "password_option",  # noqa: F405
    "Path",  # noqa: F405
    "path",  # noqa: F405
    "pause",  # noqa: F405
    "progressbar",  # noqa: F405
    "prompt",  # noqa: F405
    "search_params",  # noqa: F405
    "secho",  # noqa: F405
    "Section",  # noqa: F405
    "SectionMixin",  # noqa: F405
    "show_params_option",  # noqa: F405
    "ShowParamsOption",  # noqa: F405
    "STRING",  # noqa: F405
    "Style",  # noqa: F405
    "style",  # noqa: F405
    "table_format_option",  # noqa: F405
    "TableFormatOption",  # noqa: F405
    "telemetry_option",  # noqa: F405
    "TelemetryOption",  # noqa: F405
    "timer_option",  # noqa: F405
    "TimerOption",  # noqa: F405
    "Tuple",  # noqa: F405
    "UNPROCESSED",  # noqa: F405
    "unstyle",  # noqa: F405
    "UsageError",  # noqa: F405
    "UUID",  # noqa: F405
    "verbosity_option",  # noqa: F405
    "VerbosityOption",  # noqa: F405
    "version_option",  # noqa: F405
    "VersionOption",  # noqa: F405
    "warnings",  # noqa: F405
    "wrap_text",  # noqa: F405
]
"""Expose all of Click, Cloup and Click Extra.

.. note::
    The content of ``__all__`` is checked and enforced in unittests.

.. todo::
    Test ruff __all__ formatting capabilities. And if good enough, remove ``__all__``
    checks in unittests.
"""
