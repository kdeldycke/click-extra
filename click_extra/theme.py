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

Holds the :class:`HelpExtraTheme` dataclass (pure data, no factory methods),
the module-level :data:`default_theme` and :data:`nocolor_theme` instances,
the named-theme :data:`theme_registry` plus :func:`register_theme` helper,
and the :class:`ThemeOption` that exposes ``--theme`` on every Click Extra
command.

The two built-in themes (``dark`` and ``light``) are declared as plain
:class:`HelpExtraTheme` instances in :mod:`click_extra.themes` and seeded
into :data:`theme_registry` at the end of this module's load. Adding a new
built-in theme is a one-file change in :mod:`click_extra.themes` — no
subclass, no factory method on :class:`HelpExtraTheme`.

.. note::
    The active theme for a CLI invocation is stored on the Click context's
    ``meta`` dict under :data:`click_extra.context.THEME` by
    :class:`ThemeOption`. Use :func:`get_current_theme` to retrieve it: that
    helper consults the active Click context first and falls back to
    :data:`default_theme` when no context is in flight (e.g. at import time,
    in ``wrap`` patching, or in bare REPL usage). Per-invocation context
    storage means concurrent invocations of the same CLI in one process
    (Sphinx builds, test runners, REPLs) do not leak ``--theme`` choices
    into each other.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from gettext import gettext as _
from typing import cast

import click
import cloup
from cloup._util import identity

from . import context
from .parameters import ExtraOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from cloup.styling import IStyle


@dataclass(frozen=True)
class HelpExtraTheme(cloup.HelpTheme):
    """Extends ``cloup.HelpTheme`` with slots for log levels and the
    structural elements Click Extra highlights in help screens.

    Each slot below documents *what* it colors. Themes (see
    :mod:`click_extra.themes`) provide the visual styling by overriding
    the relevant slot defaults.
    """

    # --- Log-level slots -----------------------------------------------------
    # Applied by :class:`~click_extra.logging.ExtraFormatter` to ``levelname``
    # before each record is emitted, so the visible level in the formatted
    # message picks up the matching style.

    critical: IStyle = identity
    """Style applied to the ``CRITICAL`` level name in log records."""

    error: IStyle = identity
    """Style applied to the ``ERROR`` level name in log records."""

    warning: IStyle = identity
    """Style applied to the ``WARNING`` level name in log records."""

    info: IStyle = identity
    """Style applied to the ``INFO`` level name in log records.

    Usually left at :func:`identity <cloup._util.identity>`: ``INFO`` is the
    default verbosity and shouldn't stand out from regular output.
    """

    debug: IStyle = identity
    """Style applied to the ``DEBUG`` level name in log records."""

    # --- Help-screen structural slots ----------------------------------------
    # Applied by :class:`~click_extra.colorize.HelpExtraFormatter` while
    # rendering each command's help output. The post-wrap formatter pass
    # walks the rendered help text and styles the matching tokens.

    option: IStyle = identity
    """Style applied to option names (``--config``, ``-v``, ``--ansi/--no-ansi``)
    wherever they appear: synopsis column, free-form descriptions, and
    docstrings (when :attr:`cross_ref_highlight` is enabled).
    """

    subcommand: IStyle = identity
    """Style applied to subcommand names: in a group's command list and
    wherever they are referenced in prose.
    """

    choice: IStyle = identity
    """Style applied to each individual value inside a :class:`click.Choice`
    metavar (e.g. ``json``, ``csv``, ``xml`` within ``[json|csv|xml]``) and
    to those values referenced in option descriptions.
    """

    metavar: IStyle = identity
    """Style applied to type metavars (``INTEGER``, ``TEXT``, ``PATH``,
    ``FILE``, ...) that follow an option name in the synopsis column.
    """

    bracket: IStyle = identity
    """Style applied to the literal bracket characters and label prefixes of
    trailing fields: ``[``, ``]``, ``default:``, ``env var:``, ``required``,
    and the field separators between them.
    """

    envvar: IStyle = identity
    """Style applied to environment-variable values inside ``[env var: ...]``
    bracket fields, and to envvar names mentioned in option descriptions.
    """

    default: IStyle = identity
    """Style applied to the default-value content inside ``[default: ...]``
    bracket fields.
    """

    range_label: IStyle = identity
    """Style applied to range expressions (``0<=x<=9``, ``x>=1024``,
    ``0<=x<100``) that appear inside bracket fields for ``IntRange`` and
    ``FloatRange`` options.
    """

    required: IStyle = identity
    """Style applied to the ``required`` label inside bracket fields on
    mandatory options.
    """

    argument: IStyle = identity
    """Style applied to argument metavars (positional parameter names like
    ``MY_ARG``, ``SCRIPT``, ``[FILENAMES]...``) in the synopsis column and
    when referenced in prose.
    """

    deprecated: IStyle = identity
    """Style applied to ``(DEPRECATED)`` / ``(Deprecated: reason)`` markers
    appended to options and commands.
    """

    search: IStyle = identity
    """Style applied to substring matches in :command:`<cli> help --search`
    output.
    """

    success: IStyle = identity
    """Style applied to success glyphs in pre-rendered UI elements (the ``✓``
    in :data:`OK`) and any text passed through this slot by downstream code.
    """

    cross_ref_highlight: bool = True
    """Highlight options, choices, arguments, metavars and CLI names in
    free-form text (descriptions, docstrings).

    When ``False``, only structural elements are styled: bracket fields
    (``[default: ...]``, ``[env var: ...]``, ranges, ``[required]``),
    deprecated messages, and subcommand names in definition lists.
    """

    subheading: IStyle = identity
    """Style for sub-section headings inside log output or inline help.

    Distinct from :attr:`heading` (which styles the top-level help-screen
    section titles): :attr:`subheading` is intended for downstream code that
    wants a second styling level for its own narrative output.

    .. seealso::
        Used by `mail-deduplicate
        <https://github.com/kdeldycke/mail-deduplicate/blob/main/mail_deduplicate/deduplicate.py>`_
        to style ``◼ N mails sharing hash …`` log lines.
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


nocolor_theme: HelpExtraTheme = HelpExtraTheme()
"""Color theme for Click Extra to force no colors.

All style slots default to :func:`identity <cloup._util.identity>`, so styling
calls return the raw text unchanged.
"""


default_theme: HelpExtraTheme = nocolor_theme
"""Process-wide fallback theme.

Used by :func:`get_current_theme` when no Click context is active or when the
active context has no theme set. :class:`ThemeOption` writes its picked theme
to ``ctx.meta`` rather than reassigning this attribute, so per-invocation
choices do not leak across CLI invocations sharing the same process.

:func:`click_extra.wrap.patch_click` does reassign this attribute, by design:
``patch_click`` is itself a process-wide monkey-patch, so a process-wide
theme override matches its scope.

Initialized to :data:`nocolor_theme` here, then reassigned to the ``dark``
built-in theme by the ``_seed_builtin_themes()`` call at the bottom of this
module (deferred to avoid a circular import with :mod:`click_extra.themes`).
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
    if ctx is not None:
        active = context.get(ctx, context.THEME)
        if active is not None:
            return cast("HelpExtraTheme", active)
    return default_theme


theme_registry: dict[str, HelpExtraTheme | Callable[[], HelpExtraTheme]] = {}
"""Registry of named themes used by :class:`ThemeOption`.

Each entry maps a theme name to either a :class:`HelpExtraTheme` instance
(the common case) or a zero-argument callable returning one (for themes
whose styling depends on runtime state). :class:`ThemeOption.set_theme`
resolves callables on lookup.

The two built-in themes are seeded here at module load time from
:data:`click_extra.themes.BUILTIN_THEMES`. Use :func:`register_theme` to
add your own *before* declaring your commands, since :class:`ThemeOption`
builds its ``click.Choice`` from this registry at instantiation time.
"""


def register_theme(
    name: str,
    theme: HelpExtraTheme | Callable[[], HelpExtraTheme],
) -> None:
    """Register a named theme in :data:`theme_registry`.

    :param name: Lowercase identifier used as the ``--theme`` choice value.
    :param theme: A :class:`HelpExtraTheme` instance, or a zero-argument
        callable returning one. Callables are resolved at ``--theme`` parse
        time, which lets a theme depend on terminal capabilities or other
        runtime state.
    """
    theme_registry[name] = theme


def _resolve_theme(
    entry: HelpExtraTheme | Callable[[], HelpExtraTheme],
) -> HelpExtraTheme:
    """Return *entry* itself if it's already a theme, otherwise call it."""
    if isinstance(entry, HelpExtraTheme):
        return entry
    return entry()


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
        if value is None or ctx.resilient_parsing:
            return
        try:
            entry = theme_registry[value]
        except KeyError as exc:
            choices = ", ".join(sorted(theme_registry))
            raise click.BadParameter(
                f"Unknown theme {value!r}. Available: {choices}.",
                ctx=ctx,
                param=param,
            ) from exc
        context.set(ctx, context.THEME, _resolve_theme(entry))

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


# Late-bind the built-in themes. Imported at the bottom of the module to break
# the circular dependency: ``themes.py`` needs ``HelpExtraTheme`` from this
# module, while this module needs the populated registry to drive
# ``ThemeOption``. The order is: define ``HelpExtraTheme``/registry first,
# then load ``themes.py`` (which references ``HelpExtraTheme``), then seed the
# registry and reassign ``default_theme`` so consumers reading it via
# ``from .theme import default_theme`` capture the dark theme as expected.
from .themes import BUILTIN_THEMES  # noqa: E402

theme_registry.update(BUILTIN_THEMES)
default_theme = BUILTIN_THEMES["dark"]


OK = default_theme.success("✓")
KO = default_theme.error("✘")
"""Pre-rendered UI-elements."""
