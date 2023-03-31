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

"""Decorators for group, commands and options.

..todo::

    Reuse code proposed in `Cloup issue #127
    <https://github.com/janluke/cloup/issues/127>`_ to reduce the boilerplate code used
    below to allow decorators to be used without parenthesis.
"""

from cloup import command as cloup_command
from cloup import group as cloup_group
from cloup import option

from .colorize import ColorOption, HelpOption
from .commands import ExtraCommand, ExtraGroup, TimerOption
from .config import ConfigOption, ShowParamsOption
from .logging import VerbosityOption
from .tabulate import TableFormatOption
from .version import VersionOption


def default_extra_params():
    """Default additional options added to ``extra_command`` and ``extra_group``:

    #. ``--time`` / ``--no-time``
    #. ``--color``, ``--ansi`` / ``--no-color``, ``--no-ansi``
    #. ``-C``, ``--config CONFIG_PATH``
    #. ``--show-params``
    #. ``-v``, ``--verbosity LEVEL``
    #. ``--version``
    #. ``-h``, ``--help``

    Order is important to let options at the top have influence on those below.

    .. note::

        This default set is a list wrapped in a method, as a workaround for unittests,
        in which option instances seems to be reused in unrelated commands and mess with
        test isolation.
    """
    return [
        TimerOption(),
        ColorOption(),
        # XXX Should we move config to the top as it might influence other options?
        ConfigOption(),
        ShowParamsOption(),
        VerbosityOption(),
        VersionOption(print_env_info=True),
        HelpOption(),
    ]


# Command and group decorators.


def command(_func=None, *args, **kwargs):
    """Allows ``cloup.command`` decorator to be used with or without arguments.

    Fixes `Cloup issue #127 <https://github.com/janluke/cloup/issues/127>`_
    """
    def cloup_decorator(func):
        return cloup_command(*args, **kwargs)(func)

    if _func is None:
        return cloup_decorator
    else:
        return cloup_decorator(_func)


def group(_func=None, *args, **kwargs):
    """Allows ``cloup.group`` decorator to be used with or without arguments.

    Fixes `Cloup issue #127 <https://github.com/janluke/cloup/issues/127>`_
    """
    def cloup_decorator(func):
        return cloup_group(*args, **kwargs)(func)

    if _func is None:
        return cloup_decorator
    else:
        return cloup_decorator(_func)


def extra_command(_func=None, *args, **kwargs):
    """Augment default ``cloup.command`` with additional options.

    The list of default options is available at
    :py:func:`click_extra.commands.default_extra_params`.

    This decorator can be used with or without arguments.
    """
    def extra_decorator(func):
        kwargs.setdefault("cls", ExtraCommand)
        kwargs.setdefault("params", default_extra_params())
        return command(*args, **kwargs)(func)

    if _func is None:
        return extra_decorator
    else:
        return extra_decorator(_func)


def extra_group(_func=None, *args, **kwargs):
    """Augment default ``cloup.group`` with additional options.

    The list of default options is available at
    :py:func:`click_extra.commands.default_extra_params`.

    This decorator can be used with or without arguments.
    """
    def extra_decorator(func):
        kwargs.setdefault("cls", ExtraGroup)
        kwargs.setdefault("params", default_extra_params())
        return group(*args, **kwargs)(func)

    if _func is None:
        return extra_decorator
    else:
        return extra_decorator(_func)


# Option decorators.


def color_option(_func=None, *args, **kwargs):
    """Decorator for ``ColorOption``.

    This decorator can be used with or without arguments.
    """
    def option_decorator(func):
        kwargs.setdefault("cls", ColorOption)
        return option(*args, **kwargs)(func)

    if _func is None:
        return option_decorator
    else:
        return option_decorator(_func)


def config_option(_func=None, *args, **kwargs):
    """Decorator for ``ConfigOption``.

    This decorator can be used with or without arguments.
    """
    def option_decorator(func):
        kwargs.setdefault("cls", ConfigOption)
        return option(*args, **kwargs)(func)

    if _func is None:
        return option_decorator
    else:
        return option_decorator(_func)


def help_option(_func=None, *args, **kwargs):
    """Decorator for ``HelpOption``.

    This decorator can be used with or without arguments.
    """
    def option_decorator(func):
        kwargs.setdefault("cls", HelpOption)
        return option(*args, **kwargs)(func)

    if _func is None:
        return option_decorator
    else:
        return option_decorator(_func)


def show_params_option(_func=None, *args, **kwargs):
    """Decorator for ``ShowParamsOption``.

    This decorator can be used with or without arguments.
    """
    def option_decorator(func):
        kwargs.setdefault("cls", ShowParamsOption)
        return option(*args, **kwargs)(func)

    if _func is None:
        return option_decorator
    else:
        return option_decorator(_func)


def table_format_option(_func=None, *args, **kwargs):
    """Decorator for ``TableFormatOption``.

    This decorator can be used with or without arguments.
    """
    def option_decorator(func):
        kwargs.setdefault("cls", TableFormatOption)
        return option(*args, **kwargs)(func)

    if _func is None:
        return option_decorator
    else:
        return option_decorator(_func)


def timer_option(_func=None, *args, **kwargs):
    """Decorator for ``TimerOption``.

    This decorator can be used with or without arguments.
    """
    def option_decorator(func):
        kwargs.setdefault("cls", TimerOption)
        return option(*args, **kwargs)(func)

    if _func is None:
        return option_decorator
    else:
        return option_decorator(_func)


def verbosity_option(_func=None, *args, **kwargs):
    """Decorator for ``VerbosityOption``.

    This decorator can be used with or without arguments.
    """
    def option_decorator(func):
        kwargs.setdefault("cls", VerbosityOption)
        return option(*args, **kwargs)(func)

    if _func is None:
        return option_decorator
    else:
        return option_decorator(_func)


def version_option(_func=None, *args, **kwargs):
    """Decorator for ``VersionOption``.

    This decorator can be used with or without arguments.
    """
    def option_decorator(func):
        kwargs.setdefault("cls", VersionOption)
        return option(*args, **kwargs)(func)

    if _func is None:
        return option_decorator
    else:
        return option_decorator(_func)
