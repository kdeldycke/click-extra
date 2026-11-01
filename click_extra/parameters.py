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
"""Our own flavor of `Option`, `Argument` and `parameters`.

The helpers that introspect a CLI's parameters live in
{mod}`click_extra.param_tools`, and the `--params` option in
{mod}`click_extra.show_params`.
"""

from __future__ import annotations

from gettext import gettext as _

import click
import cloup
from click import ParamType, echo, style
from click._utils import UNSET
from click.core import ParameterSource, _format_deprecated_suffix

from .param_tools import param_spellings
from .types import EnumChoice

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

    from click.parser import _OptionParser

_CLICK_HAS_PARAMETER_SPEC = hasattr(click.Parameter, "spec")
"""Whether Click names a parameter by `Parameter.spec`, as it does from `8.6.0` on.

Click then reads `spec` everywhere it read `human_readable_name`, and warns
about a subclass that still overrides the old property.
"""


class _ParameterMixin:
    """Overrides of {class}`click.Parameter` methods shared by Click Extra parameters.

    ```{warning}
    An override of a `click.Parameter` method goes here, and the mixin comes
    first in the bases of {class}`Option` and {class}`Argument`. Click has no
    hook to swap the `Parameter` class those two inherit from, and Cloup ships
    no `Parameter` of its own.
    ```
    """

    # Attributes provided by the `click.Parameter` subclass this mixin is always
    # combined with. Declared here so the methods below can reference them without
    # mypy flagging them as undefined on the standalone mixin.
    multiple: bool
    nargs: int
    deprecated: bool | str
    name: str
    param_type_name: str
    type: ParamType

    def process_value(self, ctx: click.Context, value: Any) -> Any:
        """Warn about a deprecated parameter a configuration file switched on.

        Click warns only for a value it can attribute to the invocation itself:
        its check is `source < ParameterSource.DEFAULT_MAP`, which covers the
        command line and the environment and stops one rank short of the
        configuration. So the one place a selection outlives the project it
        names, a file written once and carried between machines, is the one
        place nothing says the parameter is on its way out.

        The notice is emitted here rather than by overriding
        `click.Parameter.handle_parse_result`, whose check sits inline in sixty
        lines of parsing internals that would have to be copied to reach it.
        `process_value` runs once per parse, right after that check, with the
        source already recorded. The wording is Click's own, down to the suffix
        helper and the property naming the parameter, so the two notices read
        as one feature.
        """
        if (
            self.deprecated
            and value is not UNSET
            and ctx.get_parameter_source(self.name) is ParameterSource.DEFAULT_MAP
        ):
            message = _(
                "DeprecationWarning: The {param_type} {name!r} is deprecated."
                "{extra_message}"
            ).format(
                param_type=self.param_type_name,
                name=(
                    self.spec  # type: ignore[attr-defined]
                    if _CLICK_HAS_PARAMETER_SPEC
                    else self.human_readable_name  # type: ignore[attr-defined]
                ),
                extra_message=_format_deprecated_suffix(self.deprecated),
            )
            echo(style(message, fg="red"), err=True)

        return super().process_value(ctx, value)  # type: ignore[misc]

    def get_default(self, ctx: click.Context, call: bool = True):
        """Override `click.Parameter.get_default()` to support `EnumChoice` types.

        Reuse the `EnumChoice.get_choice_string()` method to convert an `Enum`
        default value to its string representation, to bypass [Click's default behavior of returning the Enum.name](https://github.com/pallets/click/pull/3004).

        ```{note}
        A `multiple` option or a variadic (`nargs=-1`) parameter carries a
        *sequence* of members as its default, so each member is resolved on its
        own. Converting the sequence as a whole would stringify the tuple itself
        (`str((MyEnum.FOO,))`) and later trip Click's ``Value must be an
        iterable`` check on the default-value path.
        ```
        """
        default_value = super().get_default(ctx, call)  # type: ignore[misc]

        if (
            isinstance(self.type, EnumChoice)
            # UNSET is an Enum member too: leave it to Click.
            and default_value is not UNSET
            # A `None` default means no default: leave it for Click, which turns
            # it into `None` or an empty tuple. Stringified, it would read as a
            # choice called `None` and fail its own validation.
            and default_value is not None
        ):
            if self.multiple or self.nargs == -1:
                default_value = tuple(
                    self.type.get_choice_string(member) for member in default_value
                )
            else:
                default_value = self.type.get_choice_string(default_value)

        return default_value


class Argument(_ParameterMixin, click.Argument):
    """`click.Argument` with the overrides of {class}`_ParameterMixin`.

    Inherits from Click directly: `cloup.Argument` is `click.Argument` itself.
    """


class Option(_ParameterMixin, cloup.Option):
    """`cloup.Option` with the overrides of {class}`_ParameterMixin`.

    `cloup.Option` subclasses `click.Option` to let an option join a Cloup
    option group.

    ```{todo}
    Delete the `human_readable_name` override and `_CLICK_HAS_PARAMETER_SPEC`
    once this package's Click floor reaches `8.6.0`. From that release on,
    Click names a parameter by `Parameter.spec`, added by
    [pallets/click#3877](https://github.com/pallets/click/pull/3877): a
    deprecation notice then names the option by its longest-prefixed flag.
    ```
    """

    if not _CLICK_HAS_PARAMETER_SPEC:

        @property
        def human_readable_name(self) -> str:
            """Every spelling of the option, joined the way Click hints at one.

            Declared below Click `8.6.0` only: from that release on, Click
            reads `Parameter.spec` in its place, and warns about a subclass
            that overrides this property.

            Below it, Click returns `self.name` here: the Python identifier it
            derived from the declarations, which is the one spelling that
            appears nowhere on the command line. Left alone, a deprecated
            `--apt-cyg / --no-apt-cyg` announces itself as `'apt_cyg'`, naming
            a flag no user can type and none of the two they did.
            `click.Argument` already overrides the property for its own
            reasons, leaving `click.Option` re-declaring the inherited body
            verbatim.

            `" / "` is the separator `click.Parameter.get_error_hint` joins the
            same spellings with, so a message naming an option reads the same
            whichever of the two produced it.
            """
            return " / ".join(param_spellings(self))

    def get_error_hint(self, ctx: click.Context | None) -> str:
        """Like parent's `get_error_hint`, but naming each environment variable.

        Click appends `(env var: '…')` to the hint of an option showing its
        variables, and formats the `envvar` attribute as is. A string reads well
        there. Click Extra gives every parameter a tuple (see
        {func}`~click_extra.envvar.param_envvar_ids`), which Click prints as its
        Python `repr`: `(env var: '('WEATHER_UNITS',)')`.

        Each name is quoted on its own here, so one variable reads as Click
        prints a string, `(env var: 'WEATHER_UNITS')`, and several are separated
        by commas. Only that suffix is rewritten: the rest of the hint is Click's.
        An option of another class, like a plain `click.Option` added to a Click
        Extra command, keeps Click's rendering.

        ```{todo}
        Delete this override once
        [pallets/click#3884](https://github.com/pallets/click/pull/3884) ships:
        Click then names each variable of a sequence `envvar` itself.
        ```
        """
        hint = super().get_error_hint(ctx)
        if self.envvar is None or isinstance(self.envvar, str):
            return hint
        raw = f" (env var: '{self.envvar}')"
        if hint.endswith(raw):
            names = ", ".join(f"'{name}'" for name in self.envvar)
            hint = f"{hint.removesuffix(raw)} (env var: {names})"
        return hint


class ExtraOption(Option):
    """Base class of the options Click Extra implements itself.

    Identifies Click Extra's own options with certainty.

    ```{note}
    The one Click Extra class carrying the `Extra` prefix: every other one takes
    the name of the Click or Cloup class it shadows. The plain `Option` name
    belongs to the user-facing wrapper this class subclasses, and the prefix
    marks Click Extra's *own* built-in options apart from it.
    {class}`~click_extra.commands.Command` reads that mark: it sorts
    parameters with `isinstance(param, ExtraOption)` to push the built-in
    options to the end.
    ```

    ```{note}
    Bracket fields (envvar, default, range, required) cannot be pre-styled in
    `get_help_record()` because Click's text wrapper splits lines *after* the
    record is returned, which would break ANSI codes that span wrapped boundaries.
    Styling is instead applied post-wrapping in
    `HelpFormatter._style_bracket_fields()`, which uses the structured data
    from `Option.get_help_extra()` to identify each field by its label.
    ```

    ```{note}
    Built-in option subclasses share a common shape: their `__init__`
    defaults `param_decls` to the option's canonical flags and wires an
    eager callback via `kwargs.setdefault("callback", self.<callback>)`.
    Every callback name encodes its role with a verb prefix. The common
    roles are:

    - `set_<key>` publishes a resolved value to `ctx.meta` (`set_color`,
      `set_no_color`, `set_theme`, `set_telemetry`, `set_progress`,
      `set_accessible`, `set_zero_exit`, the verbosity options'
      `set_level`);
    - `init_<system>` additionally installs a `ctx` helper or records a
      snapshot (`init_timer`, `init_formatter`, `init_columns`,
      `init_sort`);
    - `validate_<thing>` coerces and validates the raw input
      (`validate_jobs`, `validate_config`);
    - `print_*` renders output and exits (`print_man`, `print_params`,
      `print_and_exit`).

    A few options own a richer operation and name it with its own verb
    rather than forcing one of the above. `ConfigOption` wires
    `load_conf` to read, parse, and merge a configuration file, and
    `NoConfigOption` wires `check_sibling_config_option` to assert that
    a sibling `--config` option exists.
    ```
    """

    def add_to_parser(self, parser: _OptionParser, ctx: click.Context) -> None:
        """Register the option, then give the `root` logger its handler for the run.

        Any of these options may log, and reports through its records: the level
        changes of the verbosity options, the status lines and the validation
        errors of `ConfigOption`, the warnings of `JobsOption`. A command that
        carries one of them so prints log records in the style of Click Extra
        while it runs.

        Click calls this method on every parameter of a command before it processes
        any of them, so the handler is in place for the records the first callbacks
        emit. It is also a step an option goes through on a command of any class,
        which is what lets one of these options work on a plain `click.command`.

        Nothing is attached while Click only completes or inspects a command line
        (`ctx.resilient_parsing`). See
        `click_extra.logging._hold_invocation_handler` for the other rules, and
        for how the handler leaves.
        """
        super().add_to_parser(parser, ctx)
        if not ctx.resilient_parsing:
            # Imported here to avoid a circular import with the logging module,
            # which imports from this one.
            from .logging import _hold_invocation_handler

            _hold_invocation_handler(ctx)
