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
"""Our own flavor of ``Option``, ``Argument`` and ``parameters``.

Also implements environment variable utilities.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Sequence, Iterable
import inspect
from gettext import gettext as _

import click
from boltons.iterutils import unique

from . import Option


def auto_envvar(
    param: click.Parameter, ctx: click.Context | Dict[str, Any]
) -> str | None:
    """Compute the auto-generated environment variable of an option or argument.

    Returns the auto envvar as it is exacly computed within Click's internals, i.e.
    ``click.core.Parameter.resolve_envvar_value()`` and
    ``click.core.Option.resolve_envvar_value()``.
    """
    # Skip parameters that have their auto-envvar explicitly disabled.
    if not getattr(param, "allow_from_autoenv", None):
        return None

    if isinstance(ctx, click.Context):
        prefix = ctx.auto_envvar_prefix
    else:
        prefix = ctx.get("auto_envvar_prefix")
    if not prefix or not param.name:
        return None

    # Mimicks Click's internals.
    return f"{prefix}_{param.name.upper()}"


def extend_envvars(
    envvars_1: str | Sequence[str] | None, envvars_2: str | Sequence[str] | None
) -> tuple[str, ...]:
    """Utility to build environment variables value to be fed to options.

    Variable names are deduplicated while preserving their initial order.

    Returns a tuple of environment variable strings. The result is ready to be used as
    the ``envvar`` parameter for options or arguments.
    """
    # Make the fist argument into a list of string.
    envvars = []
    if envvars_1:
        if isinstance(envvars_1, str):
            envvars = [envvars_1]
        else:
            envvars = list(envvars_1)

    # Merge the second argument into the list.
    if envvars_2:
        if isinstance(envvars_2, str):
            envvars.append(envvars_2)
        else:
            envvars.extend(envvars_2)

    # Deduplicate the list and cast it into an immutable tuple.
    return tuple(unique(envvars))


def normalize_envvar(envvar: str) -> str:
    """Utility to normalize an environment variable name.

    The normalization process separates all contiguous alphanumeric string segments,
    eliminate empty strings, join them with an underscore and uppercase the result.
    """
    return "_".join((p for p in re.split(r"[^a-zA-Z0-9]+", envvar) if p)).upper()


def all_envvars(
    param: click.Parameter, ctx: click.Context | Dict[str, Any], normalize: bool = False
) -> tuple[str, ...]:
    """Returns the deduplicated, ordered list of environment variables for an option or
    argument, including the auto-generated one.

    The auto-generated environment variable is added at the end of the list, so that
    user-defined envvars takes precedence. This respects the current implementation
    of ``click.core.Option.resolve_envvar_value()``.

    If ``normalize`` is `True`, the returned value is normalized. By default it is
    `False` to perfectly reproduce the
    `current behavior of Click, which is subject to discussions <https://github.com/pallets/click/issues/2483>`_.
    """
    auto_envvar_id = auto_envvar(param, ctx)
    envvars = extend_envvars(param.envvar, auto_envvar_id)

    if normalize:
        envvars = tuple(normalize_envvar(var) for var in envvars)

    return envvars


def search_params(
    params: Iterable[click.Parameter],
    klass: type[click.Parameter],
    unique: bool = True,
) -> list[click.Parameter] | click.Parameter | None:
    """Search a particular class of parameter in a list and return them.

    :param params: list of parameter instances to search in.
    :param klass: the class of the parameters to look for.
    :param unique: if ``True``, raise an error if more than one parameter of the
        provided ``klass`` is found.
    """
    param_list = [p for p in params if isinstance(p, klass)]
    if not param_list:
        return None
    if unique:
        if len(param_list) != 1:
            raise RuntimeError(
                f"More than one {klass.__name__} parameters found "
                f"on command: {param_list}"
            )
        return param_list.pop()
    return param_list


class ExtraOption(Option):
    """All new options implemented by ``click-extra`` inherits this class.

    Does nothing in particular for now but provides a way to identify Click Extra's own
    options with certainty.

    Also contains Option-specific code that should be contributed upstream to Click.
    """

    @staticmethod
    def get_help_default(option: click.Option, ctx: click.Context) -> str | None:
        """Produce the string to be displayed in the help as option's default.

        .. caution::
            This is a `copy of Click's default value rendering of the default
            <https://github.com/pallets/click/blob/b0538df/src/click/core.py#L2754-L2792>`_

            This code **should be keep in sync with Click's implementation**.

        .. attention::
            This doens't work with our own ``--config`` option because we are also
            monkey-patching `ConfigOption.get_help_record()
            <https://kdeldycke.github.io/click-extra/config.html#click_extra.config.ConfigOption.get_help_record>`_
            to display the dynamic default value.

            So the results of this method call is:

                .. code-block:: text

                    <bound method ConfigOption.default_pattern of <ConfigOption config>>

            instead of the expected:

                .. code-block:: text

                    ~/(...)/multiple_envvars.py/*.{toml,yaml,yml,json,ini,xml}

        .. todo::
            A better solution has been proposed upstream to Click:
            - https://github.com/pallets/click/issues/2516
            - https://github.com/pallets/click/pull/2517
        """
        # Temporarily enable resilient parsing to avoid type casting
        # failing for the default. Might be possible to extend this to
        # help formatting in general.
        resilient = ctx.resilient_parsing
        ctx.resilient_parsing = True

        try:
            default_value = option.get_default(ctx, call=False)
        finally:
            ctx.resilient_parsing = resilient

        show_default = False
        show_default_is_str = False

        if option.show_default is not None:
            if isinstance(option.show_default, str):
                show_default_is_str = show_default = True
            else:
                show_default = option.show_default
        elif ctx.show_default is not None:
            show_default = ctx.show_default

        if show_default_is_str or (show_default and (default_value is not None)):
            if show_default_is_str:
                default_string = f"({option.show_default})"
            elif isinstance(default_value, (list, tuple)):
                default_string = ", ".join(str(d) for d in default_value)
            elif inspect.isfunction(default_value):
                default_string = _("(dynamic)")
            elif option.is_bool_flag and option.secondary_opts:
                # For boolean flags that have distinct True/False opts,
                # use the opt without prefix instead of the value.
                default_string = click.parser.split_opt(
                    (option.opts if option.default else option.secondary_opts)[0]
                )[1]
            elif (
                option.is_bool_flag and not option.secondary_opts and not default_value
            ):
                default_string = ""
            else:
                default_string = str(default_value)

            if default_string:
                return default_string

        return None
