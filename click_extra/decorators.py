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

from __future__ import annotations

import inspect
from functools import wraps
from typing import overload

import click
import cloup
from click.decorators import _param_memo

from .accessibility import AccessibleOption
from .color import ColorOption, NoColorOption
from .commands import (
    DEFAULT_HELP_NAMES,
    Command,
    Group,
    LazyGroup,
    default_params,
)
from .config import (
    ConfigOption,
    ExportConfigOption,
    NoConfigOption,
    ValidateConfigOption,
)
from .execution import JobsOption, TimerOption, ZeroExitOption
from .logging import QuietOption, VerboseOption, VerbosityOption
from .man_page import ManOption
from .parameters import Argument, Option, ShowParamsOption
from .table import ColumnsOption, SortByOption, TableFormatOption
from .telemetry import TelemetryOption
from .theme import ThemeOption
from .tree import TreeOption
from .version import VersionOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, Protocol, TypeVar

    _AnyCallable = Callable[..., Any]
    CommandT_co = TypeVar("CommandT_co", bound=click.Command, covariant=True)
    SubCommandT = TypeVar("SubCommandT", bound=click.Command)
    ParamT = TypeVar("ParamT", bound=click.Parameter)
    FC = TypeVar("FC", bound="_AnyCallable | click.Command")

    class CommandDecorator(Protocol[CommandT_co]):
        """Static type of the command decorators built by `decorator_factory`.

        Mirrors Click's own overloads for `@command`/`@group` so type
        checkers infer the produced command class, while also covering the
        no-parenthesis form enabled by `allow_missing_parenthesis`.
        """

        @overload
        def __call__(self, name: _AnyCallable, /) -> CommandT_co:
            """Bare `@command` form: the callback is the only argument."""

        @overload
        def __call__(
            self,
            name: str | None = ...,
            *,
            cls: type[SubCommandT],
            **attrs: Any,
        ) -> Callable[[_AnyCallable], SubCommandT]:
            """Parenthesized form with an explicit `cls` override."""

        @overload
        def __call__(
            self,
            name: str | None = ...,
            *,
            cls: None = ...,
            **attrs: Any,
        ) -> Callable[[_AnyCallable], CommandT_co]:
            """Parenthesized form using the decorator's default command class."""

    class ParameterDecorator(Protocol):
        """Static type of the option and argument decorators built by
        `decorator_factory`.

        These decorators attach a parameter to the callback and return it
        unchanged, so the decorated function keeps its own type. The two
        overloads cover the bare (no-parenthesis) and parenthesized forms.
        """

        @overload
        def __call__(self, func: FC, /) -> FC:
            """Bare `@option` form: the callback is the only argument."""

        @overload
        def __call__(self, *param_decls: str, **attrs: Any) -> Callable[[FC], FC]:
            """Parenthesized form: option flags and attributes are forwarded."""


def allow_missing_parenthesis(dec_factory):
    """Allow to use decorators with or without parenthesis.

    As proposed in
    [Cloup issue #127](https://github.com/janluke/cloup/issues/127#issuecomment-1264704896).
    """

    @wraps(dec_factory)
    def new_factory(*args, **kwargs):
        if args and callable(args[0]):
            return dec_factory(*args[1:], **kwargs)(args[0])
        return dec_factory(*args, **kwargs)

    return new_factory


@overload
def decorator_factory(
    dec: Any, *new_args: Any, cls: type[CommandT_co], **new_defaults: Any
) -> CommandDecorator[CommandT_co]: ...


@overload
def decorator_factory(
    dec: Any, *new_args: Any, cls: type[ParamT] | None = ..., **new_defaults: Any
) -> ParameterDecorator: ...


def decorator_factory(dec, *new_args, **new_defaults):
    """Clone decorator with a set of new defaults.

    Used to create our own collection of decorators for our custom options, based on
    Cloup's.

    The two overloads give static type checkers a precise signature for the
    decorators this factory produces: command-style decorators (`cls` is a
    `click.Command` subclass) report the resulting command class, while
    parameter-style decorators (`cls` is a `click.Parameter` subclass, or
    absent) return the decorated callback unchanged. Both overloads model the
    optional-parenthesis behaviour added by `allow_missing_parenthesis`, which
    plain inference cannot recover. See `CommandDecorator` and
    `ParameterDecorator` for the produced shapes.

    ```{attention}
    The `cls` argument passed to the factory is used as the reference class from
    which the produced decorator's `cls` argument must inherit.

    The idea is to ensure that, for example, the `@command` decorator
    re-implemented by Click Extra is always a subclass of `Command`, even when
    the user overrides the `cls` argument. That way it can always rely on the
    additional properties and methods defined in the Click Extra framework, where we
    have extended Cloup and Click so much that we want to prevent surprising side
    effects.
    ```
    """

    @allow_missing_parenthesis
    def decorator(*args, **kwargs):
        """Returns a new decorator instantiated with custom defaults.

        These defaults values are merged with the user's own arguments.

        A special case is made for the `params` argument, to allow it to be callable.
        This limits the issue of the mutable options being shared between commands.

        This decorator can be used with or without arguments.
        """
        if not args:
            args = new_args

        # Validate that the provided 'cls' is a subclass of the default one.
        if (
            "cls" in new_defaults
            and "cls" in kwargs
            and not issubclass(kwargs["cls"], new_defaults["cls"])
        ):
            mro_list = ", ".join(
                f"{k.__module__}.{k.__name__}" for k in kwargs["cls"].__mro__
            )
            raise TypeError(
                f"The 'cls' argument must be a subclass of "
                f"{new_defaults['cls'].__name__}, got: {mro_list}"
            )

        # Use a copy of the defaults to avoid modifying the original dict.
        new_kwargs = new_defaults.copy()
        new_kwargs.update(kwargs)

        # If the params argument is a callable, we need to call it to get the actual
        # list of options.
        params_func = new_kwargs.get("params")
        if callable(params_func):
            new_kwargs["params"] = params_func()

        # Return the original decorator with the new defaults.
        result = dec(*args, **new_kwargs)

        # When the result is a decorator (not a Command), and we have a callable
        # params function, the decorator captures the evaluated params list in its
        # closure. Click mutates that list with params.extend() on every application
        # to a function, so a pre-instantiated decorator (e.g. stored in a pytest
        # parametrize list as `command()`) would accumulate options across uses,
        # creating duplicate parameters. Wrapping here calls params_func() freshly
        # on each application to prevent that shared mutation.
        if callable(params_func) and not isinstance(result, click.Command):
            _params_func = params_func
            _dec = dec
            _args = args
            _new_defaults = new_defaults
            _extra_kwargs = kwargs

            def _with_fresh_params(f):
                _fresh_kwargs = _new_defaults.copy()
                _fresh_kwargs.update(_extra_kwargs)
                _fresh_kwargs["params"] = _params_func()
                return _dec(*_args, **_fresh_kwargs)(f)

            result = _with_fresh_params

        return result

    # Surface the parameter class's constructor signature on the produced decorator,
    # instead of the opaque `(*args, **kwargs)`, so editors, `help()` and Sphinx
    # autodoc show the real options. Restricted to parameter decorators (`option`,
    # `argument` and their subclasses): their `cls.__init__` mirrors what the
    # decorator forwards, whereas `command`/`group` wrap a different (Cloup)
    # signature and `help_option` has no `cls`.
    cls = new_defaults.get("cls")
    if isinstance(cls, type) and issubclass(cls, click.Parameter):
        try:
            init_params = list(inspect.signature(cls.__init__).parameters.values())
        except (TypeError, ValueError):
            pass
        else:
            # Drop `self` and keep the rest as the decorator's public signature.
            decorator.__signature__ = inspect.Signature(init_params[1:])

    return decorator


# Replace and extend existing Click and Cloup commands decorators.
command = decorator_factory(
    dec=cloup.command,
    cls=Command,
    params=default_params,
)
group = decorator_factory(
    dec=cloup.group,
    cls=Group,
    params=default_params,
)


# Replace and extend existing Click parameter decorators.
option = decorator_factory(dec=cloup.option, cls=Option)
argument = decorator_factory(dec=cloup.argument, cls=Argument)

help_option = decorator_factory(click.decorators.help_option, *DEFAULT_HELP_NAMES)


def _register_grouped_option(f, option, group):
    """Memoize *option* on *f*, then wire its Cloup option-group membership.

    The shared tail of the hand-written `version_option` and `sort_by_option`
    decorators (the ones the `param_decls`-first `decorator_factory` cannot
    build): both register an already-built option with the `_param_memo`
    primitive Cloup uses, then attach the option to *group* (hiding it when the
    group is hidden). Returns *f* so a decorator can `return` it directly.
    """
    _param_memo(f, option)
    new_option = f.__click_params__[-1]
    new_option.group = group
    if group and group.hidden:
        new_option.hidden = True
    return f


# Hand-written rather than produced by `decorator_factory` so it stays a drop-in for
# Click's `@version_option`, whose first positional argument is the version string.
# That conflicts with the `param_decls`-first convention the factory relies on, so the
# two are told apart by their leading character (see the docstring below).
@allow_missing_parenthesis
def version_option(version=None, *param_decls, cls=VersionOption, group=None, **kwargs):
    """Attach a {class}`~click_extra.version.VersionOption` to a command.

    Drop-in compatible with Click's `@version_option`: the first positional
    argument may be an explicit version string. click-extra otherwise auto-detects
    the version and treats positional arguments as option flags (like every other
    option decorator), so the two are disambiguated by their leading character: a
    value starting with `-` is a flag declaration, anything else is a Click-style
    version string forwarded into the `version` template field.

    ```{code-block} python

    @command
    @version_option("1.2.3")  # Click idiom: pins the displayed version.
    def my_cmd(): ...
    ```

    ```{note}
    Hand-written instead of produced by
    {func}`~click_extra.decorators.decorator_factory` because Click's leading
    `version` positional conflicts with the `param_decls`-first convention
    the factory relies on.
    ```
    """
    if version is not None and not str(version).startswith("-"):
        # Click idiom `@version_option("1.2.3")`: forward as a `version` override.
        fields = dict(kwargs.pop("fields", None) or {})
        if fields.get("version", version) != version:
            raise TypeError(
                "version supplied both positionally and via fields={'version': ...}.",
            )
        fields["version"] = version
        kwargs["fields"] = fields
    elif version is not None:
        # Leading `-`: a flag declaration, not a version. Restore it as a param_decl.
        param_decls = (version, *param_decls)

    def decorator(f):
        return _register_grouped_option(f, cls(param_decls, **kwargs), group)

    return decorator


# Introduce new commands decorators specific to Click Extra.
lazy_group = decorator_factory(dec=group, cls=LazyGroup)


# Introduce new parameter decorators specific to Click Extra.
accessible_option = decorator_factory(dec=option, cls=AccessibleOption)
color_option = decorator_factory(dec=option, cls=ColorOption)
columns_option = decorator_factory(dec=option, cls=ColumnsOption)
config_option = decorator_factory(dec=option, cls=ConfigOption)
export_config_option = decorator_factory(dec=option, cls=ExportConfigOption)
jobs_option = decorator_factory(dec=option, cls=JobsOption)
man_option = decorator_factory(dec=option, cls=ManOption)
no_color_option = decorator_factory(dec=option, cls=NoColorOption)
no_config_option = decorator_factory(dec=option, cls=NoConfigOption)
quiet_option = decorator_factory(dec=option, cls=QuietOption)
validate_config_option = decorator_factory(dec=option, cls=ValidateConfigOption)
show_params_option = decorator_factory(dec=option, cls=ShowParamsOption)
table_format_option = decorator_factory(dec=option, cls=TableFormatOption)
telemetry_option = decorator_factory(dec=option, cls=TelemetryOption)
theme_option = decorator_factory(dec=option, cls=ThemeOption)
timer_option = decorator_factory(dec=option, cls=TimerOption)
tree_option = decorator_factory(dec=option, cls=TreeOption)
verbose_option = decorator_factory(dec=option, cls=VerboseOption)
verbosity_option = decorator_factory(dec=option, cls=VerbosityOption)
zero_exit_option = decorator_factory(dec=option, cls=ZeroExitOption)


# Unlike its siblings above, `sort_by_option` is hand-written rather than built by
# `decorator_factory`: `SortByOption` takes its column definitions as positional
# arguments (`*header_defs`), which occupy the slot the `cloup.option` plumbing
# reserves for `param_decls` (option-name strings). Routing through the factory
# would force the column definitions into a keyword, breaking the positional API
# `SortByOption` has shipped since 7.11.0. So the option is instantiated directly
# here and registered with the same `_param_memo` primitive Cloup uses, preserving
# that API and composing with option groups and constraints.
def sort_by_option(*header_defs, cls=SortByOption, group=None, **kwargs):
    """Attach a {class}`~click_extra.table.SortByOption` to a command.

    Forwards the positional `header_defs` (`(label, column_id)` pairs) straight
    to the option constructor and registers a regular Cloup `Option`, so the
    `--sort-by` option composes with `@option_group` and `@constraint` like any
    other option decorator.

    ```{note}
    Hand-written instead of produced by
    {func}`~click_extra.decorators.decorator_factory` because
    {class}`~click_extra.table.SortByOption` accepts its column definitions as
    positional arguments, which conflicts with the `param_decls`-first
    convention the factory relies on.
    ```
    """

    def decorator(f):
        return _register_grouped_option(f, cls(*header_defs, **kwargs), group)

    return decorator
