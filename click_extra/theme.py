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
"""Help-screen color themes for Click Extra.

Holds the :class:`HelpExtraTheme` dataclass, the global :data:`default_theme`
and :data:`nocolor_theme` instances, the named-theme :data:`theme_registry`
plus :func:`register_theme` helper, and the :class:`ThemeOption` that exposes
``--theme`` on every Click Extra command.

.. note::
    :data:`default_theme` is mutated at runtime by :class:`ThemeOption` to
    apply the user's pick. Modules that read the theme at format time should
    either import the module (``from . import theme``) and reference
    ``theme.default_theme`` for late binding, or accept that their local
    ``from .theme import default_theme`` binding is frozen at import time.
    :class:`~click_extra.colorize.HelpExtraFormatter` uses the late-binding
    pattern.
"""

from __future__ import annotations

import dataclasses
import sys
from dataclasses import dataclass
from gettext import gettext as _

import click
import cloup
from cloup._util import identity
from cloup.styling import Color

from . import Style
from .parameters import ExtraOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from cloup.styling import IStyle


@dataclass(frozen=True)
class HelpExtraTheme(cloup.HelpTheme):
    """Extends ``cloup.HelpTheme`` with ``logging.levels`` and extra properties."""

    critical: IStyle = identity
    error: IStyle = identity
    warning: IStyle = identity
    info: IStyle = identity
    debug: IStyle = identity
    """Log levels from Python's logging module."""

    option: IStyle = identity
    subcommand: IStyle = identity
    choice: IStyle = identity
    metavar: IStyle = identity
    bracket: IStyle = identity
    envvar: IStyle = identity
    default: IStyle = identity
    range_label: IStyle = identity
    required: IStyle = identity
    argument: IStyle = identity
    deprecated: IStyle = identity
    search: IStyle = identity
    success: IStyle = identity
    """Click Extra new coloring properties."""

    cross_ref_highlight: bool = True
    """Highlight options, choices, arguments, metavars and CLI names in
    free-form text (descriptions, docstrings).

    When ``False``, only structural elements are styled: bracket fields
    (``[default: ...]``, ``[env var: ...]``, ranges, ``[required]``),
    deprecated messages, and subcommand names in definition lists.
    """

    subheading: IStyle = identity
    """Non-canonical Click Extra properties.

    .. note::
        Subheading is used for sub-sections, like `in the help of mail-deduplicate
        <https://github.com/kdeldycke/mail-deduplicate/blob/0764287/mail_deduplicate/deduplicate.py#L445>`_.

    .. todo::
        Maybe this shouldn't be in Click Extra because it is a legacy inheritance from
        one of my other project.
    """

    def with_(  # type: ignore[override]
        self,
        **kwargs: dict[str, IStyle | None],
    ) -> HelpExtraTheme:
        """Derives a new theme from the current one, with some styles overridden.

        Returns the same instance if the provided styles are the same as the current.
        """
        # Check for unrecognized arguments.
        unrecognized_args = set(kwargs).difference(self.__dataclass_fields__)
        if unrecognized_args:
            raise TypeError(
                f"Got unexpected keyword argument(s): {', '.join(unrecognized_args)}"
            )

        # List of styles that are different from the base theme.
        new_styles = {
            field_id: new_style
            for field_id, new_style in kwargs.items()
            if new_style != getattr(self, field_id)
        }
        if new_styles:
            return dataclasses.replace(self, **new_styles)  # type: ignore[arg-type]

        # No new styles, return the same instance.
        return self

    @staticmethod
    def dark() -> HelpExtraTheme:
        """A theme assuming a dark terminal background color."""
        return HelpExtraTheme(
            invoked_command=Style(fg=Color.bright_white),
            heading=Style(fg=Color.bright_blue, bold=True, underline=True),
            constraint=Style(fg=Color.magenta),
            # Neutralize Cloup's col1, as it interferes with our finer option styling
            # which takes care of separators.
            col1=identity,
            # Style aliases like options and subcommands.
            alias=Style(fg=Color.cyan),
            # Style aliases punctuation like options, but dimmed.
            alias_secondary=Style(fg=Color.cyan, dim=True),
            ### Log styles.
            critical=Style(fg=Color.red, bold=True),
            error=Style(fg=Color.red),
            warning=Style(fg=Color.yellow),
            info=identity,  # INFO level is the default, so no style applied.
            debug=Style(fg=Color.blue),
            ### Click Extra styles.
            option=Style(fg=Color.cyan),
            # Style subcommands like options and aliases.
            subcommand=Style(fg=Color.cyan),
            choice=Style(fg=Color.magenta),
            metavar=Style(fg=Color.cyan, dim=True),
            bracket=Style(dim=True),
            envvar=Style(fg=Color.yellow, dim=True),
            default=Style(fg=Color.green, dim=True, italic=True),
            range_label=Style(fg=Color.cyan, dim=True),
            required=Style(fg=Color.red, dim=True),
            argument=Style(fg=Color.cyan),
            deprecated=Style(fg=Color.bright_yellow, bold=True),
            search=Style(fg=Color.green, bold=True),
            success=Style(fg=Color.green),
            ### Non-canonical Click Extra styles.
            subheading=Style(fg=Color.blue),
        )

    @staticmethod
    def light() -> HelpExtraTheme:
        """A theme assuming a light terminal background color.

        .. todo::
            Tweak colors to make them more readable.
        """
        return HelpExtraTheme.dark()


default_theme: HelpExtraTheme = HelpExtraTheme.dark()
"""Default color theme for Click Extra.

.. caution::
    This module-level attribute is reassigned at CLI parse time by
    :class:`ThemeOption` (and by :func:`click_extra.wrap.unpatch_click` in
    tests). Consumers that need to track the current theme must reference
    ``theme.default_theme`` via the module, not a local
    ``from .theme import default_theme`` binding.
"""


nocolor_theme: HelpExtraTheme = HelpExtraTheme()
"""Color theme for Click Extra to force no colors."""


theme_registry: dict[str, Callable[[], HelpExtraTheme]] = {
    "dark": HelpExtraTheme.dark,
    "light": HelpExtraTheme.light,
}
"""Registry of named theme factories used by :class:`ThemeOption`.

Each entry maps a theme name to a zero-argument callable returning a
:class:`HelpExtraTheme` instance. Factories (rather than pre-built instances)
let consumers register themes that depend on runtime state.

Use :func:`register_theme` to add custom themes before the CLI is invoked,
since :class:`ThemeOption` builds its ``click.Choice`` from this registry at
instantiation time.
"""


def register_theme(name: str, factory: Callable[[], HelpExtraTheme]) -> None:
    """Register a named theme factory in :data:`theme_registry`.

    :param name: Lowercase identifier used as the ``--theme`` choice value.
    :param factory: Zero-argument callable returning a :class:`HelpExtraTheme`.
    """
    theme_registry[name] = factory


OK = default_theme.success("✓")
KO = default_theme.error("✘")
"""Pre-rendered UI-elements."""


class ThemeOption(ExtraOption):
    """A pre-configured option that adds a ``--theme`` flag to select the help-screen
    color theme.

    The list of valid theme names is pulled from :data:`theme_registry` at instantiation
    time. Register new themes with :func:`register_theme` *before* declaring your
    commands, otherwise they will not appear in the option's choices.

    The selected theme replaces the module-level :data:`default_theme`, so all help
    screens rendered after the option is processed pick up the new styling.
    """

    @staticmethod
    def set_theme(
        ctx: click.Context,
        param: click.Parameter,
        value: str | None,
    ) -> None:
        """Resolve the chosen theme name and override :data:`default_theme` globally.

        Looks up *value* in :data:`theme_registry`, calls its factory, and reassigns
        ``theme.default_theme`` so :class:`~click_extra.colorize.HelpExtraFormatter`
        (which reads the module attribute lazily through a module reference) picks
        up the change.
        """
        if value is None:
            return
        try:
            factory = theme_registry[value]
        except KeyError as exc:
            choices = ", ".join(sorted(theme_registry))
            raise click.BadParameter(
                f"Unknown theme {value!r}. Available: {choices}.",
                ctx=ctx,
                param=param,
            ) from exc
        # Reassign the module attribute. Other modules that imported it via
        # ``from .theme import default_theme`` keep their original binding,
        # but :class:`~click_extra.colorize.HelpExtraFormatter` resolves the
        # name at call time through ``theme.default_theme``, so help screens
        # see the new theme.
        sys.modules[__name__].default_theme = factory()

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default: str = "dark",
        is_eager: bool = True,
        expose_value: bool = False,
        help: str = _("Color theme used for help screens."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--theme",)

        kwargs.setdefault("callback", self.set_theme)

        super().__init__(
            param_decls=param_decls,
            type=click.Choice(sorted(theme_registry), case_sensitive=False),
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )
