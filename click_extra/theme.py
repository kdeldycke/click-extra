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

Holds the :class:`HelpExtraTheme` dataclass, the module-level
:data:`default_theme` and :data:`nocolor_theme` instances, the named-theme
:data:`theme_registry` plus :func:`register_theme` helper, and the
:class:`ThemeOption` that exposes ``--theme`` on every Click Extra command.

.. note::
    The active theme for a CLI invocation is stored on the Click context's
    ``meta`` dict under :data:`THEME_META_KEY` by :class:`ThemeOption`. Use
    :func:`get_current_theme` to retrieve it: that helper consults the active
    Click context first and falls back to :data:`default_theme` when no
    context is in flight (e.g. at import time, in ``wrap`` patching, or in
    bare REPL usage). Per-invocation context storage means concurrent
    invocations of the same CLI in one process (Sphinx builds, test runners,
    REPLs) do not leak ``--theme`` choices into each other.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from gettext import gettext as _
from typing import cast

import click
import cloup
from cloup._util import identity
from cloup.styling import Color

from . import Style
from . import context
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

        Mirrors :meth:`dark` but swaps the palette for one that stays legible on a white
        background: bright variants (which most terminals render as washed-out tints) are
        replaced by their standard counterparts, ``bright_white`` becomes ``black``, and
        cyan accents become ``blue`` since cyan on white is hard to read.
        """
        return HelpExtraTheme(
            invoked_command=Style(fg=Color.black, bold=True),
            heading=Style(fg=Color.blue, bold=True, underline=True),
            constraint=Style(fg=Color.magenta),
            # Neutralize Cloup's col1, as it interferes with our finer option styling
            # which takes care of separators.
            col1=identity,
            # Style aliases like options and subcommands.
            alias=Style(fg=Color.blue),
            # Style aliases punctuation like options, but dimmed.
            alias_secondary=Style(fg=Color.blue, dim=True),
            ### Log styles.
            critical=Style(fg=Color.red, bold=True),
            error=Style(fg=Color.red),
            warning=Style(fg=Color.magenta),
            info=identity,  # INFO level is the default, so no style applied.
            debug=Style(fg=Color.blue, dim=True),
            ### Click Extra styles.
            option=Style(fg=Color.blue),
            # Style subcommands like options and aliases.
            subcommand=Style(fg=Color.blue),
            choice=Style(fg=Color.magenta),
            metavar=Style(fg=Color.blue, dim=True),
            bracket=Style(dim=True),
            envvar=Style(fg=Color.magenta, dim=True),
            default=Style(fg=Color.green, dim=True, italic=True),
            range_label=Style(fg=Color.blue, dim=True),
            required=Style(fg=Color.red, dim=True),
            argument=Style(fg=Color.blue),
            deprecated=Style(fg=Color.red, bold=True),
            search=Style(fg=Color.green, bold=True),
            success=Style(fg=Color.green),
            ### Non-canonical Click Extra styles.
            subheading=Style(fg=Color.blue, dim=True),
        )


default_theme: HelpExtraTheme = HelpExtraTheme.dark()
"""Process-wide fallback theme.

Used by :func:`get_current_theme` when no Click context is active or when the
active context has no theme set. :class:`ThemeOption` writes its picked theme
to ``ctx.meta`` rather than reassigning this attribute, so per-invocation
choices do not leak across CLI invocations sharing the same process.

:func:`click_extra.wrap.patch_click` does reassign this attribute, by design:
``patch_click`` is itself a process-wide monkey-patch, so a process-wide
theme override matches its scope.
"""


def get_current_theme() -> HelpExtraTheme:
    """Return the theme active for the current CLI invocation.

    Resolution order:

    1. The theme stored on the active Click context under
       :data:`click_extra.context.THEME` (set by :class:`ThemeOption`
       from ``--theme``).
    2. The module-level :data:`default_theme` (the dark default, or whatever
       :func:`click_extra.wrap.patch_click` set at process start).

    Falling back through the active context (instead of reading a module
    attribute) keeps ``--theme`` scoped to the invocation that received it,
    so a second invocation in the same process starts from the default
    again.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is not None and context.THEME in ctx.meta:
        return cast("HelpExtraTheme", ctx.meta[context.THEME])
    return default_theme


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

    The selected theme is stored on the Click context under
    :data:`click_extra.context.THEME`, so it applies for the duration of the
    current invocation only and does not leak into sibling invocations sharing
    the same process.
    """

    @staticmethod
    def set_theme(
        ctx: click.Context,
        param: click.Parameter,
        value: str | None,
    ) -> None:
        """Resolve the chosen theme name and store it on the Click context.

        Looks up *value* in :data:`theme_registry`, calls its factory, and writes
        the resulting :class:`HelpExtraTheme` under
        :data:`click_extra.context.THEME` in ``ctx.meta``. Click shares
        ``meta`` across the parent/child context hierarchy, so subcommands
        inherit the parent group's pick automatically.
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
        ctx.meta[context.THEME] = factory()

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
