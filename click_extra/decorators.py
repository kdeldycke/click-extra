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

"""Decorators for group, commands and options."""

from functools import wraps
from typing import Any, Callable, Dict, TypeVar

import cloup

from .colorize import ColorOption, HelpOption
from .commands import ExtraCommand, ExtraGroup, TimerOption
from .config import ConfigOption, ShowParamsOption
from .logging import VerbosityOption
from .tabulate import TableFormatOption
from .version import VersionOption

AnyCallable = Callable[..., Any]

F = TypeVar('F', bound=AnyCallable)
"""Type variable for a Callable."""

Decorator = Callable[[F], F]
DecoratorFactory = Callable[..., Decorator[F]]


def allow_missing_parenthesis(dec_factory):
    """Allow to use decorators with or without parenthesis.

    As proposed in `Cloup issue #127
    <https://github.com/janluke/cloup/issues/127#issuecomment-1264704896>`_.
    """
    @wraps(dec_factory)
    def new_factory(*args, **kwargs):
        if args and callable(args[0]):
            return dec_factory(*args[1:], **kwargs)(args[0])
        return dec_factory(*args, **kwargs)

    return new_factory


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


def decorator_factory(dec: Decorator, **new_defaults: Dict[str, Any]) -> Decorator[F]:
    """Clone decorator with a set of new defaults.

    Used to create our own collection of decorators for our custom options, based on
    Cloup's.
    """

    @allow_missing_parenthesis
    def decorator(*args, **kwargs) -> Decorator:
        """Returns a new decorator instanciated with new defaults and the user's own
        arguments.

        This decorator can be used with or without arguments.
        """
        # Use a copy of the defaults to avoid modifying the original dict.
        new_kwargs = new_defaults.copy()
        new_kwargs.update(kwargs)
        # Return the original decorator with the new defaults.
        return dec(*args, **new_kwargs)

    return decorator


# Command and group decorators.
command = decorator_factory(dec=cloup.command)
group = decorator_factory(dec=cloup.group)

# Option decorators.
color_option = decorator_factory(dec=cloup.option, cls=ColorOption)
config_option = decorator_factory(dec=cloup.option, cls=ConfigOption)
help_option = decorator_factory(dec=cloup.option, cls=HelpOption)
show_params_option = decorator_factory(dec=cloup.option, cls=ShowParamsOption)
table_format_option = decorator_factory(dec=cloup.option, cls=TableFormatOption)
timer_option = decorator_factory(dec=cloup.option, cls=TimerOption)
verbosity_option = decorator_factory(dec=cloup.option, cls=VerbosityOption)
version_option = decorator_factory(dec=cloup.option, cls=VersionOption)