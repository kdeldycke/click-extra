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

The built-in themes (``dark``, ``dracula``, ``light``, ``monokai``, ``nord``,
``solarized_dark``) live in the package data file ``click_extra/themes.toml``
and are loaded at module import time via :meth:`HelpExtraTheme.from_dict`.
Adding a new built-in theme is a one-file edit in that TOML file — no Python
needed. The same TOML schema is used for user-defined themes loaded from
configuration: see :doc:`/theme` for the user guide.

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
import sys
from dataclasses import dataclass
from gettext import gettext as _
from pathlib import Path
from typing import cast

import click
import cloup
from cloup._util import identity

from . import context
from .parameters import ExtraOption
from .styling import Style

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    from cloup.styling import IStyle


@dataclass(frozen=True)
class HelpExtraTheme(cloup.HelpTheme):
    """Extends ``cloup.HelpTheme`` with slots for log levels and the
    structural elements Click Extra highlights in help screens.

    Each slot below documents *what* it colors. The built-in themes shipped
    in :data:`~click_extra.theme.BUILTIN_THEMES` provide the visual styling
    by setting the relevant slots; user-defined themes can be authored as
    plain mappings and loaded via :meth:`from_dict`.
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the theme to a plain dict suitable for TOML/JSON/YAML.

        Each :class:`~click_extra.styling.Style` slot is emitted via
        :meth:`Style.to_dict <click_extra.styling.Style.to_dict>`. Slots left
        at their default (:func:`identity <cloup._util.identity>` or
        ``None``) are omitted, so the output only carries what the theme
        actually overrides. Pair with :meth:`from_dict` to round-trip.

        :raises TypeError: when a slot holds an opaque ``IStyle`` callable
            that is not a :class:`Style` (those cannot be serialized).
        """
        out: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if value is identity or value is None:
                continue
            if f.name == "cross_ref_highlight":
                # Only emit the bool when it differs from the field default.
                if value != f.default:
                    out[f.name] = value
                continue
            if isinstance(value, Style):
                out[f.name] = value.to_dict()
                continue
            raise TypeError(
                f"Cannot serialize {type(self).__name__}.{f.name}: "
                f"{value!r} is not a Style instance."
            )
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HelpExtraTheme:
        """Build a theme from the plain dict produced by :meth:`to_dict`.

        Each value is interpreted by field type: a mapping becomes a
        :class:`~click_extra.styling.Style` via
        :meth:`Style.from_dict <click_extra.styling.Style.from_dict>`, while
        ``cross_ref_highlight`` is read as a plain ``bool``. Unknown keys
        raise :class:`TypeError` so typos surface immediately.
        """
        unknown = set(data).difference(cls.__dataclass_fields__)
        if unknown:
            raise TypeError(
                f"Unknown {cls.__name__} field(s): {', '.join(sorted(unknown))}"
            )
        kwargs: dict[str, Any] = {}
        for name, raw in data.items():
            if name == "cross_ref_highlight":
                kwargs[name] = bool(raw)
                continue
            if isinstance(raw, dict):
                kwargs[name] = Style.from_dict(raw)
                continue
            raise TypeError(
                f"Cannot deserialize {cls.__name__}.{name}: "
                f"{raw!r} is neither a mapping nor a recognized scalar."
            )
        return cls(**kwargs)

    def cascade(self, base: HelpExtraTheme) -> HelpExtraTheme:
        """Layer this theme's set slots on top of *base*.

        Mirrors :meth:`Style.cascade <click_extra.styling.Style.cascade>` at
        the slot level: this theme's non-default slots win, *base* fills the
        rest. Useful for layering a sparse override (typically parsed from a
        config file's ``[tool.<cli>.themes.<name>]`` table) on top of a
        full built-in palette.

        :raises TypeError: when *base* is not a :class:`HelpExtraTheme`.
        """
        if not isinstance(base, HelpExtraTheme):
            raise TypeError(
                f"Cannot cascade onto {type(base).__name__}: not a HelpExtraTheme."
            )
        merged = {**base.to_dict(), **self.to_dict()}
        return type(self).from_dict(merged)


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

Initialized to :data:`nocolor_theme` here, then reassigned to :data:`DARK`
at the bottom of this module once the built-in themes are loaded from
``themes.toml``.
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
"""Process-wide registry of named themes used by :class:`ThemeOption`.

Each entry maps a theme name to either a :class:`HelpExtraTheme` instance
(the common case) or a zero-argument callable returning one (for themes
whose styling depends on runtime state). :class:`ThemeOption.set_theme`
resolves callables on lookup.

The built-in themes are seeded here at module load time from
:data:`BUILTIN_THEMES` (loaded from ``click_extra/themes.toml``). Use
:func:`register_theme` to add your own at import time, *or* declare them
in your CLI's config file under ``[tool.<cli>.themes.<name>]`` — the
latter goes through :class:`ConfigOption <click_extra.config.ConfigOption>`,
lands on ``ctx.meta`` (see :data:`click_extra.context.THEME_OVERRIDES`),
and never mutates this module-level dict, so per-invocation choices
don't leak between sibling invocations sharing the same process.
"""

THEMES_CONFIG_KEY: str = "themes"
"""Sub-key under ``[tool.<cli>]`` where user-defined themes live in config.

Used by :class:`ConfigOption <click_extra.config.ConfigOption>` to find
``[tool.<cli>.themes.<name>]`` tables, build them via
:meth:`HelpExtraTheme.from_dict`, and stash the result on
``ctx.meta[click_extra.context.THEME_OVERRIDES]``.
"""


def register_theme(
    name: str,
    theme: HelpExtraTheme | Callable[[], HelpExtraTheme],
) -> None:
    """Register a named theme in the module-level :data:`theme_registry`.

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


def get_theme_registry(
    ctx: click.Context | None = None,
) -> dict[str, HelpExtraTheme | Callable[[], HelpExtraTheme]]:
    """Return the theme registry visible to *ctx*.

    Merges the module-level :data:`theme_registry` with any per-invocation
    overrides stored on ``ctx.meta`` under
    :data:`click_extra.context.THEME_OVERRIDES`. Per-invocation entries win
    on key collisions, which is what lets a config file's
    ``[tool.<cli>.themes.dark]`` table override the built-in ``dark`` palette
    for one invocation without touching the global registry.

    When *ctx* is ``None`` or has no overrides, returns a copy of the
    module-level registry.
    """
    merged: dict[str, HelpExtraTheme | Callable[[], HelpExtraTheme]] = dict(
        theme_registry
    )
    if ctx is not None:
        overrides = context.get(ctx, context.THEME_OVERRIDES)
        if overrides:
            merged.update(overrides)
    return merged


def themes_from_config(
    table: dict[str, Any],
) -> dict[str, HelpExtraTheme]:
    """Build a ``{name: HelpExtraTheme}`` mapping from a ``[tool.<cli>.themes]`` sub-tree.

    For each entry, build a :class:`HelpExtraTheme` via :meth:`from_dict`. If
    *name* matches an existing key in :data:`theme_registry`, the new theme
    is layered on top via :meth:`HelpExtraTheme.cascade` so partial overrides
    (e.g. just one slot) inherit the rest from the built-in palette.
    Stand-alone names produce theme instances with the unset slots left at
    their defaults.
    """
    result: dict[str, HelpExtraTheme] = {}
    for name, slots in table.items():
        overlay = HelpExtraTheme.from_dict(slots)
        if name in theme_registry:
            result[name] = overlay.cascade(_resolve_theme(theme_registry[name]))
        else:
            result[name] = overlay
    return result


def validate_themes_config(themes_subtree: dict[str, Any]) -> None:
    """Validate a ``[tool.<cli>.themes]`` sub-tree.

    Registered as a built-in :class:`ConfigValidator <click_extra.config.ConfigValidator>`
    by :class:`ConfigOption <click_extra.config.ConfigOption>` so malformed
    theme tables surface as :class:`~click_extra.config.ValidationError` with
    a rooted path (``my-cli.themes.<name>``) rather than a deep
    :class:`TypeError` from :meth:`HelpExtraTheme.from_dict`.
    """
    # Lazy-imported to avoid a load-time cycle with config.py.
    from .config import ValidationError

    for name, slots in themes_subtree.items():
        if not isinstance(slots, dict):
            raise ValidationError(
                path=name,
                message=(
                    f"theme definition must be a table, got "
                    f"{type(slots).__name__}"
                ),
                code="invalid-theme-shape",
            )
        try:
            HelpExtraTheme.from_dict(slots)
        except TypeError as exc:
            raise ValidationError(
                path=name,
                message=str(exc),
                code="invalid-theme",
            ) from exc


class ThemeChoice(click.Choice):
    """A :class:`click.Choice` whose ``choices`` track the live theme registry.

    Where a vanilla ``click.Choice`` snapshots its choices at instantiation,
    ``ThemeChoice.choices`` is a property that queries
    :func:`get_theme_registry` at every lookup. That means themes registered
    late — typically by :class:`ConfigOption <click_extra.config.ConfigOption>`
    parsing ``[tool.<cli>.themes.<name>]`` tables before ``--theme`` is
    processed — are valid choices and appear in the ``--help`` metavar.

    Subclassing :class:`click.Choice` (rather than rolling a fresh
    :class:`~click.ParamType`) keeps the per-choice token coloring that
    :mod:`click_extra.colorize` applies to ``Choice`` metavars: each theme
    name in the bracket-style metavar is styled with the active theme's
    ``choice`` slot.
    """

    def __init__(self, case_sensitive: bool = False) -> None:
        # ``click.Choice.__init__`` assigns ``self.choices``; pass an empty
        # tuple so the assignment is harmless, then let the property below
        # take over for every read.
        super().__init__((), case_sensitive=case_sensitive)

    @property
    def choices(self) -> tuple[str, ...]:
        try:
            ctx = click.get_current_context(silent=True)
        except RuntimeError:
            ctx = None
        return tuple(sorted(get_theme_registry(ctx)))

    @choices.setter
    def choices(self, _value: object) -> None:
        # Swallow ``click.Choice.__init__``'s assignment; the property is the
        # authoritative source.
        return


class ThemeOption(ExtraOption):
    """A pre-configured option that adds ``--theme`` to select the help-screen palette.

    Accepts any name registered in :data:`theme_registry` *or* in the
    per-invocation overrides loaded by
    :class:`ConfigOption <click_extra.config.ConfigOption>` from
    ``[tool.<cli>.themes.<name>]``. Validation goes through
    :class:`ThemeChoice`, which reads the live registry at parse time, so
    config-defined themes appear as valid choices and in the ``--help``
    metavar without any further wiring.

    The resolved :class:`HelpExtraTheme` lands on the Click context under
    :data:`click_extra.context.THEME` and applies for the duration of the
    current invocation only.
    """

    @staticmethod
    def set_theme(
        ctx: click.Context,
        param: click.Parameter,
        value: str | None,
    ) -> None:
        """Resolve the chosen theme name and store it on the Click context.

        :class:`ThemeChoice` has already validated *value* against the live
        registry by the time this fires, so the lookup is unconditional.
        """
        if value is None or ctx.resilient_parsing:
            return
        entry = get_theme_registry(ctx)[value]
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
            type=ThemeChoice(),
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )


_BUILTIN_THEMES_TOML = Path(__file__).parent / "themes.toml"


def _load_builtin_themes() -> dict[str, HelpExtraTheme]:
    """Parse ``themes.toml`` into a ``{name: HelpExtraTheme}`` mapping.

    Each top-level table maps to a :class:`HelpExtraTheme` via
    :meth:`HelpExtraTheme.from_dict`. Failures surface immediately at import
    time so a malformed shipped TOML cannot silently degrade ``--theme``.
    """
    raw = tomllib.loads(_BUILTIN_THEMES_TOML.read_text(encoding="utf-8"))
    return {name: HelpExtraTheme.from_dict(data) for name, data in raw.items()}


BUILTIN_THEMES: dict[str, HelpExtraTheme] = _load_builtin_themes()
"""Mapping of built-in theme names to their :class:`HelpExtraTheme` instances.

Loaded from the package data file ``click_extra/themes.toml`` at module
import time and seeded into :data:`theme_registry`. Adding a new built-in
theme is a one-file edit in that TOML file: declare a new ``[<name>]``
table with one inline-table per styled slot.
"""

DARK: HelpExtraTheme = BUILTIN_THEMES["dark"]
"""Theme tuned for terminals with a dark background.

Used as the process-wide :data:`default_theme`.
"""

DRACULA: HelpExtraTheme = BUILTIN_THEMES["dracula"]
"""Dracula by Zeno Rocha. High-contrast dark theme with vivid neon accents.

Palette: https://draculatheme.com/contribute
"""

LIGHT: HelpExtraTheme = BUILTIN_THEMES["light"]
"""Theme tuned for terminals with a light/white background.

Mirrors :data:`DARK` but swaps the palette for one that stays legible on a
white background: bright variants (which most terminals render as washed-out
tints) are replaced by their standard counterparts, ``bright_white`` becomes
``black``, and cyan accents become ``blue`` since cyan on white is hard to
read.
"""

MONOKAI: HelpExtraTheme = BUILTIN_THEMES["monokai"]
"""Monokai by Wimer Hazenberg. Classic dark theme with high-saturation
magenta and lime accents.

Palette: https://monokai.pro/
"""

NORD: HelpExtraTheme = BUILTIN_THEMES["nord"]
"""Nord by Arctic Ice Studio. Cool-toned dark theme built around
frost-blue and aurora accents.

Palette: https://www.nordtheme.com/docs/colors-and-palettes
"""

SOLARIZED_DARK: HelpExtraTheme = BUILTIN_THEMES["solarized_dark"]
"""Solarized Dark by Ethan Schoonover. Warm-toned dark theme with selective
accent contrast.

Palette: https://ethanschoonover.com/solarized/
"""


theme_registry.update(BUILTIN_THEMES)
default_theme = DARK


OK = default_theme.success("✓")
KO = default_theme.error("✘")
"""Pre-rendered UI-elements."""
