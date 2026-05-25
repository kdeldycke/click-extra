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
the :data:`nocolor_theme` constant, the process-wide fallback accessed via
:func:`get_default_theme` / :func:`set_default_theme`, the named-theme
:data:`theme_registry` plus :func:`register_theme` helper, and the
:class:`ThemeOption` that exposes ``--theme`` on every Click Extra command.

The built-in themes (``dark``, ``dracula``, ``light``, ``manpage``,
``monokai``, ``nord``, ``solarized_dark``) live in the package data file
``click_extra/themes.toml`` and are loaded at module import time via
:meth:`HelpExtraTheme.from_dict`. ``manpage`` is a colorless theme that
shadows man-pages(7) typography (bold literals, italic replaceables); the
others apply that same bold/italic split on top of their color palettes.
Adding a new built-in theme is a one-file edit in that TOML file — no Python
needed. The same TOML schema is used for user-defined themes loaded from
configuration: see :doc:`/theme` for the user guide.

.. note::
    The active theme for a CLI invocation is stored on the Click context's
    ``meta`` dict under :data:`click_extra.context.THEME` by
    :class:`ThemeOption`. Use :func:`get_current_theme` to retrieve it: that
    helper consults the active Click context first and falls back to
    :func:`get_default_theme` when no context is in flight (e.g. at import
    time, in ``wrap`` patching, or in bare REPL usage). Per-invocation
    context storage means concurrent invocations of the same CLI in one
    process (Sphinx builds, test runners, REPLs) do not leak ``--theme``
    choices into each other.
"""

from __future__ import annotations

import dataclasses
import html
import re
import sys
from dataclasses import dataclass
from gettext import gettext as _
from importlib import resources
from typing import cast

import click
import cloup
from cloup._util import identity

from . import context
from .parameters import ExtraOption
from .styling import Style, _color_to_css, dict_to_fields, fields_to_dict

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence
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
    """Style applied to the ``CRITICAL`` level name in log records.

    Example: ``CRITICAL: Database connection lost.``
    """

    error: IStyle = identity
    """Style applied to the ``ERROR`` level name in log records.

    Example: ``ERROR: Configuration file not found.``
    """

    warning: IStyle = identity
    """Style applied to the ``WARNING`` level name in log records.

    Example: ``WARNING: Requested 16 jobs exceeds available CPU cores (8).``
    """

    info: IStyle = identity
    """Style applied to the ``INFO`` level name in log records.

    Usually left at :func:`identity <cloup._util.identity>`: ``INFO`` is the
    default verbosity and shouldn't stand out from regular output.
    """

    debug: IStyle = identity
    """Style applied to the ``DEBUG`` level name in log records.

    Example: ``DEBUG: Resolved /etc/myapp/config.toml.``
    """

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
    trailing fields: ``[``, ``]``, ``default:``, ``env var:``, and the field
    separators between them. Also acts as the **fallback** for the four
    inner bracket-field slots — :attr:`envvar`, :attr:`default`,
    :attr:`required`, :attr:`range_label` — whenever any of them is left at
    :func:`identity <cloup._util.identity>`. A theme that only sets
    ``bracket`` therefore renders the whole bracket field with a single
    uniform style; richer themes layer specific colors on top by setting
    the inner slots.
    """

    envvar: IStyle = identity
    """Style applied to environment-variable values inside ``[env var: ...]``
    bracket fields, and to envvar names mentioned in option descriptions.
    Falls back to :attr:`bracket` when left at
    :func:`identity <cloup._util.identity>`, so a theme that only styles
    ``bracket`` still gets a consistent rendering inside bracket fields.
    """

    default: IStyle = identity
    """Style applied to the default-value content inside ``[default: ...]``
    bracket fields. Falls back to :attr:`bracket` when left at
    :func:`identity <cloup._util.identity>`.
    """

    range_label: IStyle = identity
    """Style applied to range expressions (``0<=x<=9``, ``x>=1024``,
    ``0<=x<100``) that appear inside bracket fields for ``IntRange`` and
    ``FloatRange`` options. Falls back to :attr:`bracket` when left at
    :func:`identity <cloup._util.identity>`.
    """

    required: IStyle = identity
    """Style applied to the ``required`` label inside bracket fields on
    mandatory options. Falls back to :attr:`bracket` when left at
    :func:`identity <cloup._util.identity>`.
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
    output, so users can spot where their query matched.
    """

    success: IStyle = identity
    """Style applied to success glyphs in pre-rendered UI elements (the ``✓``
    in :data:`OK_GLYPH`) and any text passed through this slot by downstream
    code.
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
        **kwargs: IStyle | bool | None,
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
    def _encode_slot(field: Any, value: Any) -> Any:
        """Encode a slot value for :meth:`to_dict`.

        :class:`~click_extra.styling.Style` instances become their
        :meth:`Style.to_dict <click_extra.styling.Style.to_dict>` mapping;
        ``cross_ref_highlight``'s ``bool`` passes through as-is. Anything
        else (an opaque ``IStyle`` callable that isn't a :class:`Style`)
        raises :class:`TypeError` since those cannot be serialized.
        """
        if isinstance(value, Style):
            return value.to_dict()
        if field.name == "cross_ref_highlight":
            return value
        raise TypeError(
            f"Cannot serialize HelpExtraTheme.{field.name}: "
            f"{value!r} is not a Style instance."
        )

    @staticmethod
    def _decode_slot(field: Any, raw: Any) -> Any:
        """Decode a slot value for :meth:`from_dict`.

        Mappings become :class:`~click_extra.styling.Style` instances via
        :meth:`Style.from_dict <click_extra.styling.Style.from_dict>`;
        ``cross_ref_highlight`` is coerced to ``bool``; anything else
        raises :class:`TypeError`.
        """
        if field.name == "cross_ref_highlight":
            return bool(raw)
        if isinstance(raw, dict):
            return Style.from_dict(raw)
        raise TypeError(
            f"Cannot deserialize HelpExtraTheme.{field.name}: "
            f"{raw!r} is neither a mapping nor a recognized scalar."
        )

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
        return fields_to_dict(self, encode=self._encode_slot)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HelpExtraTheme:
        """Build a theme from the plain dict produced by :meth:`to_dict`.

        Each value is interpreted by field type: a mapping becomes a
        :class:`~click_extra.styling.Style` via
        :meth:`Style.from_dict <click_extra.styling.Style.from_dict>`, while
        ``cross_ref_highlight`` is read as a plain ``bool``. Unknown keys
        raise :class:`TypeError` so typos surface immediately.
        """
        return cls(**dict_to_fields(cls, data, decode=cls._decode_slot))

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


LITERAL_STYLES: frozenset[str] = frozenset({
    "invoked_command",
    "subcommand",
    "alias",
    "alias_secondary",
    "option",
    "choice",
})
r"""Names of the :class:`HelpExtraTheme` slots that color *literal* tokens:
text the user types verbatim on the command line.

Covers the command and subcommand names, their aliases, option flags
(``--config``, ``-v``), and the concrete values of a :class:`click.Choice`
(``json`` in ``[json|csv|xml]``).

These map to the **bold** font of the man-pages(7) typographic convention,
which sets text "typed literally" in bold (``\fB`` in roff) "even in the
SYNOPSIS section". Paired with :data:`REPLACEABLE_STYLES`: the two are
disjoint, and every remaining slot is an annotation, prose, or chrome style
that the literal/replaceable dichotomy does not classify (log levels,
``[default: ...]`` / ``[env var: ...]`` fields, headings, ...).

.. note::
    Every built-in theme applies this classification: literal slots render
    bold and :data:`REPLACEABLE_STYLES` italic, mirroring a man page even in
    the color palettes. ``tests/test_themes.py`` enforces the invariant, and
    the ``manpage`` built-in theme is its pure-monochrome embodiment
    (bold/italic, no color). A man-page generator can reuse the same two sets
    to map each styled token to ``\fB`` / ``\fI``. See :doc:`/benchmark` for
    the man-page generation gap.
"""

REPLACEABLE_STYLES: frozenset[str] = frozenset({
    "metavar",
    "argument",
})
r"""Names of the :class:`HelpExtraTheme` slots that color *replaceable* tokens:
placeholders the user substitutes with a real value.

Covers type metavars on options (``INTEGER``, ``CONFIG_PATH``) and positional
argument metavars (``SOURCE``, ``[FILENAMES]...``).

These map to the *italic* font of the man-pages(7) convention, which sets
replaceable arguments in italic (``\fI`` in roff). See :data:`LITERAL_STYLES`
for the bold counterpart and the full rationale.
"""


nocolor_theme: HelpExtraTheme = HelpExtraTheme()
"""Color theme for Click Extra to force no colors.

All style slots default to :func:`identity <cloup._util.identity>`, so styling
calls return the raw text unchanged.
"""


_default_theme: HelpExtraTheme = nocolor_theme
"""Process-wide fallback theme. See :func:`get_default_theme`.

Initialized to :data:`nocolor_theme` here, then reassigned to the ``dark``
built-in theme at the bottom of this module once :file:`themes.toml` is loaded.
"""


def get_default_theme() -> HelpExtraTheme:
    """Return the process-wide fallback theme.

    Read by :func:`get_current_theme` when no Click context is active or
    when the active context has no theme set. The default is the built-in
    ``dark`` palette; :func:`click_extra.wrap.patch_click` overrides it
    via :func:`set_default_theme` for the duration of a patched session.

    Resolved through a function rather than a module attribute so callers
    always observe the current value: capturing ``default_theme`` as a
    default function parameter (the previous pattern) would freeze whatever
    was set at import time.
    """
    return _default_theme


def set_default_theme(theme: HelpExtraTheme) -> None:
    """Override the process-wide fallback theme.

    :class:`ThemeOption` writes its picked theme to ``ctx.meta`` rather
    than calling this helper, so per-invocation choices do not leak across
    invocations sharing the same process. Use this only for genuinely
    process-wide overrides — :func:`click_extra.wrap.patch_click` is the
    canonical caller.
    """
    global _default_theme
    _default_theme = theme


def get_current_theme() -> HelpExtraTheme:
    """Return the theme active for the current CLI invocation.

    Resolution order:

    1. The theme stored on the active Click context under
       :data:`click_extra.context.THEME` (set by :class:`ThemeOption`
       from ``--theme``).
    2. The process-wide fallback returned by :func:`get_default_theme`
       (the dark default, or whatever :func:`click_extra.wrap.patch_click`
       set at process start).

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
    return _default_theme


theme_registry: dict[str, HelpExtraTheme] = {}
"""Process-wide registry of named themes used by :class:`ThemeOption`.

Each entry maps a theme name to its :class:`HelpExtraTheme` instance.
Built-in themes are seeded here at module load time from
:data:`BUILTIN_THEMES` (loaded from ``click_extra/themes.toml``).

Use :func:`register_theme` to add your own at import time, *or* declare
them in your CLI's config file under ``[tool.<cli>.themes.<name>]`` — the
latter goes through :class:`ConfigOption <click_extra.config.ConfigOption>`,
lands on ``ctx.meta`` (see :data:`click_extra.context.THEME_OVERRIDES`),
and never mutates this module-level dict, so per-invocation choices don't
leak between sibling invocations sharing the same process.
"""


def register_theme(name: str, theme: HelpExtraTheme) -> None:
    """Register a named theme in the module-level :data:`theme_registry`.

    :param name: Lowercase identifier used as the ``--theme`` choice value.
    :param theme: A :class:`HelpExtraTheme` instance.
    """
    theme_registry[name] = theme


def get_theme_registry(
    ctx: click.Context | None = None,
) -> dict[str, HelpExtraTheme]:
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
    merged: dict[str, HelpExtraTheme] = dict(theme_registry)
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
            result[name] = overlay.cascade(theme_registry[name])
        else:
            result[name] = overlay
    return result


# --- Palette documentation helper --------------------------------------------
#
# Public entry point for rendering a theme's palette as an inline-styled HTML
# fragment, suitable for injection into MyST/reST documents via
# ``python:render`` / ``raw:: html``. Used by ``docs/theme.md`` to render the
# built-in palettes; downstream projects with their own custom themes can call
# the same helper to get matching swatch listings in their own docs.

_PALETTE_SKIP_SLOTS: frozenset[str] = frozenset({
    # Inherited cloup slots that built-in themes leave at identity.
    "command_help",
    "section_help",
    "col1",
    "col2",
    "epilog",
    # Log-level slot intentionally left unstyled by every built-in (INFO is
    # the default verbosity and shouldn't stand out).
    "info",
    # Internal cache from cloup; never rendered.
    "_style_kwargs",
    # Boolean toggle, not a Style.
    "cross_ref_highlight",
})

_PALETTE_SWATCH = (
    '<span style="display:inline-block;width:0.85em;height:0.85em;'
    "background:{css};border:1px solid var(--color-foreground-muted,#888);"
    'border-radius:2px;vertical-align:-0.15em;margin-right:0.35em"></span>'
)

# Per-attribute inline CSS so each attribute's label visually demonstrates
# itself in the rendered swatch row (``bold`` shown in bold, ``italic``
# in italic, ``underline`` with an underline, …). Iteration order doubles
# as the visual order of the attribute pills next to each slot.
_PALETTE_ATTR_CSS: dict[str, str] = {
    "bold": "font-weight: bold",
    "dim": "opacity: 0.6",
    "italic": "font-style: italic",
    "underline": "text-decoration: underline",
    "overline": "text-decoration: overline",
    "blink": "text-decoration: blink",
    "reverse": "filter: invert(1)",
    "strikethrough": "text-decoration: line-through",
}

# Slots inherited from cloup's HelpTheme. Each one links to cloup's
# autoapi-generated docs (which expose per-field anchors), instead of
# click-extra's local HelpExtraTheme autodoc anchor (which only covers the
# slots HelpExtraTheme adds on top of cloup's base class).
_PALETTE_CLOUP_SLOTS: frozenset[str] = frozenset({
    "invoked_command",
    "command_help",
    "heading",
    "constraint",
    "section_help",
    "col1",
    "col2",
    "alias",
    "alias_secondary",
    "epilog",
})

# Per-slot example templates. Substrings wrapped in ``«…»`` (U+00AB / U+00BB
# guillemets, picked because they never appear in real CLI help output) are
# styled by calling ``theme.<slot>(text)`` at render time, so the example
# faithfully reflects whatever the active theme's slot produces. Each slot
# that the built-in themes actually style has an entry; unstyled inherited
# slots and the boolean ``cross_ref_highlight`` toggle are intentionally
# left out and the renderer falls back to a plain "(no example available)"
# placeholder for them.
_PALETTE_EXAMPLES: dict[str, str] = {
    # Log-level slots: rendered by ExtraFormatter on the levelname token.
    "critical": "«CRITICAL»: Database connection lost.",
    "error": "«ERROR»: Configuration file not found.",
    "warning": "«WARNING»: Requested 16 jobs exceeds available CPU cores (8).",
    "info": "INFO: Loaded 23 records.",
    "debug": "«DEBUG»: Resolved /etc/myapp/config.toml.",
    # Cloup-inherited help-screen slots: rendered by HelpExtraFormatter on
    # the matching tokens of help-screen output.
    "invoked_command": "Usage: «my-cli» [OPTIONS] COMMAND [ARGS]...",
    "heading": "«Options:»",
    "constraint": "(«mutually exclusive»)",
    "alias": "  show, «ls»     Show the current state.",
    "alias_secondary": "  show «(»ls«)»     Show the current state.",
    # HelpExtraTheme-native help-screen slots.
    "option": (
        "«--config» CONFIG_PATH    Location of the configuration file.\n"
        "«-v», «--verbose»           Increase verbosity."
    ),
    "subcommand": (
        "Commands:\n"
        "  «backup»        Snapshot the data store.\n"
        "  «restore»       Restore from a snapshot."
    ),
    "choice": ("--format [«json»|«csv»|«xml»]   Output format. Defaults to «json»."),
    "metavar": (
        "--output «TEXT»       Destination file.\n--workers «INTEGER»   Worker count."
    ),
    # The single wide marker covers the entire bracket field because
    # ``bracket`` is the runtime fallback for every inner slot (``envvar``,
    # ``default``, ``required``, ``range_label``) when those slots are left
    # at ``identity``.  A theme that only sets ``bracket`` therefore colours
    # the whole field — structural tokens and value tokens alike — with the
    # same style.  See ``_bracket_or`` in ``colorize.py`` and
    # ``test_bracket_field_inner_slot_fallback_to_bracket`` in the test suite.
    "bracket": "--port INTEGER    «[env var: PORT; default: 8080; required]»",
    "envvar": (
        "--threshold INTEGER   Acceptable error rate.\n"
        "                      [env var: «THRESHOLD, TEST_THRESHOLD»]"
    ),
    "default": (
        "--output FILENAME    Destination file.  [default: «out.csv»]\n"
        "--retries INTEGER    Retry budget.  [default: «5»]"
    ),
    "range_label": (
        "--level INTEGER RANGE    Verbosity level.  [«0<=x<=9»]\n"
        "--port INTEGER RANGE     Bind port.        [«x>=1024»]"
    ),
    "required": "--token TEXT    Authentication token.  [«required»]",
    "argument": (
        "Usage: cp [OPTIONS] «SRC» «DST»\nUsage: pack [OPTIONS] «[FILES]...» «[OUTPUT]»"
    ),
    "deprecated": (
        "--old-api    Legacy endpoint. «(DEPRECATED: use --new-api instead)»\n"
        "--legacy     Kept for compatibility. «(deprecated: removed in v9)»"
    ),
    "search": "--«retry»-budget INTEGER    The «retry» budget.",
    "success": "«✓» database migration completed\n«✓» 1,245 records imported",
    "subheading": (
        "«◼ 3 mails sharing hash a1b2c3d4»\n«◼ 7 mails sharing hash e5f6a7b8»"
    ),
}

# Matches a single ``«…»`` segment for the slot-example renderer.
_PALETTE_EXAMPLE_RE: re.Pattern[str] = re.compile("«([^»]+)»")

_PALETTE_CLOUP_URL = "https://cloup.readthedocs.io/en/stable/autoapi/cloup/index.html"


def _palette_slot_link(name: str) -> str:
    """Wrap a slot name in an anchor pointing at its dataclass-field definition.

    Cloup-inherited slots resolve to a per-field anchor on cloup's autoapi
    page (e.g. ``#cloup.HelpTheme.invoked_command``); HelpExtraTheme-native
    slots resolve to the local autodoc anchor on the same page that hosts
    the palette (``docs/theme.md``), so the link works inside click-extra's
    own documentation without an external roundtrip.
    """
    if name in _PALETTE_CLOUP_SLOTS:
        href = f"{_PALETTE_CLOUP_URL}#cloup.HelpTheme.{name}"
    else:
        href = f"#click_extra.theme.HelpExtraTheme.{name}"
    return f'<a href="{href}"><code>{name}</code></a>'


def _render_slot_ansi(theme: HelpExtraTheme, slot: str) -> str:
    """Render a slot's example template with literal ANSI SGR escapes.

    For each ``«…»`` segment, calls ``theme.<slot>(text)`` — the same code
    path click-extra uses to style real help-screen output at runtime —
    and splices the resulting escape-bearing string into the template.
    Used by the Sphinx ``autodoc-process-docstring`` hook in
    :func:`inject_slot_example_docstring` to inject a colored example into
    each :class:`HelpExtraTheme` slot's autodoc block, mirroring the
    HTML rendering :func:`_render_slot_example` produces for the
    palette tables.

    Returns an empty string when the slot has no template; callers treat
    that as "skip" rather than emitting an empty code block.
    """
    template = _PALETTE_EXAMPLES.get(slot)
    if template is None:
        return ""
    style = getattr(theme, slot)
    return _PALETTE_EXAMPLE_RE.sub(
        lambda m: style(m.group(1)) if callable(style) else m.group(1),
        template,
    )


def inject_slot_example_docstring(
    app: Any,
    what: str,
    name: str,
    obj: Any,
    options: Any,
    lines: list[str],
) -> None:
    """Sphinx ``autodoc-process-docstring`` hook injecting per-slot colored examples.

    For every :class:`HelpExtraTheme` slot that has an entry in
    :data:`_PALETTE_EXAMPLES`, append an ``ansi-color`` code block to the
    slot's autodoc lines. The example is rendered through
    :func:`_render_slot_ansi`, which calls ``BUILTIN_THEMES["dark"].<slot>(text)``
    to obtain the actual ANSI escapes click-extra would emit at runtime.

    Wire this up from a Sphinx ``conf.py`` with:

    .. code-block:: python

        from click_extra.theme import inject_slot_example_docstring


        def setup(app):
            app.connect("autodoc-process-docstring", inject_slot_example_docstring)

    The hook intentionally targets *only* ``click_extra.theme.HelpExtraTheme.<slot>``
    names so it won't accidentally rewrite unrelated docstrings; downstream
    projects can register the hook in their own ``conf.py`` if they
    consume HelpExtraTheme docstrings.
    """
    prefix = "click_extra.theme.HelpExtraTheme."
    if not name.startswith(prefix):
        return
    slot = name[len(prefix) :]
    rendered = _render_slot_ansi(BUILTIN_THEMES["dark"], slot)
    if not rendered:
        return
    lines.append("")
    lines.append("Rendered with the default ``dark`` theme:")
    lines.append("")
    lines.append(".. code-block:: ansi-color")
    lines.append("")
    lines.extend(f"   {ansi_line}" for ansi_line in rendered.split("\n"))


def _render_slot_example(theme: HelpExtraTheme, slot: str) -> str:
    """Render a slot's example template as inline-styled HTML.

    Looks up the slot's template in :data:`_PALETTE_EXAMPLES`, then for
    every ``«…»``-marked segment calls ``theme.<slot>(text)`` to obtain the
    actual styling click-extra would apply at runtime. The styled bytes are
    converted to an inline CSS ``<span>`` via :meth:`Style.to_css`, so the
    rendered HTML faithfully reflects whatever the theme's slot produces —
    including the dim/italic/bold attribute mix and the foreground color.

    Returns an empty string when the slot has no example template (cloup
    slots that built-ins leave at identity, the boolean toggle, …); the
    palette renderer treats that as "no example row" rather than emitting
    an empty cell.
    """
    template = _PALETTE_EXAMPLES.get(slot)
    if template is None:
        return ""
    style = getattr(theme, slot)
    css = style.to_css() if isinstance(style, Style) else ""
    parts: list[str] = []
    last = 0
    for match in _PALETTE_EXAMPLE_RE.finditer(template):
        # Plain text between the previous segment and this match.
        parts.append(html.escape(template[last : match.start()]))
        token = html.escape(match.group(1))
        if css:
            parts.append(f'<span style="{css}">{token}</span>')
        else:
            # Slot is identity (or a non-Style callable we can't introspect):
            # emit the token plain, matching the runtime no-op behavior.
            parts.append(token)
        last = match.end()
    parts.append(html.escape(template[last:]))
    return (
        '<pre class="slot-example" style="margin:0.3em 0 0;'
        "padding:0.4em 0.6em;background:var(--color-code-background,#f5f5f5);"
        "border-radius:4px;font-size:0.85em;line-height:1.4;"
        'white-space:pre-wrap">' + "".join(parts) + "</pre>"
    )


def palette_html(theme: HelpExtraTheme) -> str:
    """Render a theme's palette as an inline-styled HTML ``<dl>`` fragment.

    The output is a two-column definition list (slot name → styled swatch
    plus attribute decorations) safe to inject into MyST or reST host
    documents via the ``python:render`` Sphinx directive (or any
    ``raw:: html`` block). Used by ``docs/theme.md`` to render every
    built-in theme's palette at Sphinx build time without hand-maintaining
    swatch tables. Downstream projects with their own custom themes can
    call the same helper to get matching swatch listings in their own docs:

    .. code-block:: markdown

        ```{python:render}
        from click_extra.theme import palette_html
        from my_app.themes import MY_THEME
        print(palette_html(MY_THEME))
        ```

    Slots that hold ``identity`` (no styling applied), the boolean
    :attr:`cross_ref_highlight` toggle, the internal ``_style_kwargs``
    cache, and a handful of inherited cloup slots that built-ins never
    style are skipped: every emitted row corresponds to a real palette
    choice in the theme.
    """
    rows: list[str] = []
    for f in dataclasses.fields(theme):
        if f.name in _PALETTE_SKIP_SLOTS:
            continue
        value = getattr(theme, f.name)
        if value is identity or value is None:
            continue
        fg = getattr(value, "fg", None)
        cell_parts: list[str] = []
        if fg is not None:
            css = _color_to_css(fg)
            if isinstance(fg, tuple) and len(fg) == 3:
                color_label = f"#{fg[0]:02x}{fg[1]:02x}{fg[2]:02x}"
            else:
                color_label = str(fg)
            cell_parts.append(
                _PALETTE_SWATCH.format(css=css) + f"<code>{color_label}</code>"
            )
        attrs = [
            f'<span style="{css}">{name}</span>'
            for name, css in _PALETTE_ATTR_CSS.items()
            if getattr(value, name, None)
        ]
        if attrs:
            cell_parts.append(" ".join(attrs))
        # Tack the styled example onto the <dd> body when one exists.
        # Each example is rendered by replaying ``theme.<slot>(text)`` on
        # the marked segments of ``_PALETTE_EXAMPLES[slot]``, so the visual
        # is computed from the same code path that styles real help-screen
        # output at runtime — no hand-authored ANSI escapes anywhere.
        example_html = _render_slot_example(theme, f.name)
        body = " ".join(cell_parts) or "—"
        if example_html:
            body = body + example_html
        rows.append(f"<dt>{_palette_slot_link(f.name)}</dt><dd>{body}</dd>")
    return (
        '<dl class="theme-palette" style="display:grid;'
        "grid-template-columns:max-content 1fr;gap:0.2em 1em;"
        'margin:0.5em 0">' + "".join(rows) + "</dl>"
    )


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
                    f"theme definition must be a table, got {type(slots).__name__}"
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


class ThemeChoice(click.ParamType):
    """A :class:`click.ParamType` whose ``choices`` track the live theme registry.

    Implements the ``click.Choice``-shaped duck interface (``choices``,
    ``case_sensitive``, ``normalize_choice``) so :mod:`click_extra.colorize`
    can collect theme names for per-token highlighting through the same
    code path it uses for Click's own ``Choice``. The ``choices`` attribute
    is a property that queries :func:`get_theme_registry` at every lookup,
    so themes registered late — typically by
    :class:`ConfigOption <click_extra.config.ConfigOption>` parsing
    ``[tool.<cli>.themes.<name>]`` tables before ``--theme`` is processed —
    are valid choices and appear in the ``--help`` metavar.

    Implemented as a fresh :class:`click.ParamType` rather than a
    :class:`click.Choice` subclass to avoid relying on Click's setter
    semantics for ``self.choices``: the previous subclass design swallowed
    Click's :py:meth:`__init__`-time assignment with a no-op setter, which
    would silently break under any future Click version that uses
    ``object.__setattr__`` (e.g. for slots) instead of regular attribute
    assignment.
    """

    # Match ``click.Choice.name`` so machinery that branches on parameter
    # type (e.g. metavar generation) treats this the same way.
    name: str = "choice"

    def __init__(self, case_sensitive: bool = False) -> None:
        self.case_sensitive = case_sensitive

    @property
    def choices(self) -> tuple[str, ...]:
        """Theme names visible in the current context, alphabetically sorted."""
        try:
            ctx = click.get_current_context(silent=True)
        except RuntimeError:
            ctx = None
        return tuple(sorted(get_theme_registry(ctx)))

    def _normalize(self, value: str) -> str:
        return value if self.case_sensitive else value.casefold()

    def normalize_choice(self, choice: Any, ctx: click.Context | None) -> str:
        """Mirrors :meth:`click.Choice.normalize_choice` for colorize compatibility."""
        normed = str(choice)
        if ctx is not None and ctx.token_normalize_func is not None:
            normed = ctx.token_normalize_func(normed)
        return self._normalize(normed)

    def get_metavar(
        self,
        param: click.Parameter,
        ctx: click.Context,
    ) -> str | None:
        return "[" + "|".join(self.choices) + "]"

    def convert(
        self,
        value: Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            self.fail(f"{value!r} is not a string.", param, ctx)
        registry = get_theme_registry(ctx)
        lookup = {self._normalize(name): name for name in registry}
        canonical = lookup.get(self._normalize(value))
        if canonical is None:
            choices = "|".join(sorted(registry))
            self.fail(
                f"{value!r} is not one of [{choices}].",
                param,
                ctx,
            )
        return canonical

    def shell_complete(
        self,
        ctx: click.Context,
        param: click.Parameter,
        incomplete: str,
    ) -> list[click.shell_completion.CompletionItem]:
        from click.shell_completion import CompletionItem

        prefix = self._normalize(incomplete)
        return [
            CompletionItem(name)
            for name in sorted(get_theme_registry(ctx))
            if self._normalize(name).startswith(prefix)
        ]


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

    def set_theme(
        self,
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
        context.set(ctx, context.THEME, get_theme_registry(ctx)[value])

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


def _load_builtin_themes() -> dict[str, HelpExtraTheme]:
    """Parse ``themes.toml`` into a ``{name: HelpExtraTheme}`` mapping.

    Each top-level table maps to a :class:`HelpExtraTheme` via
    :meth:`HelpExtraTheme.from_dict`. Failures surface immediately at import
    time so a malformed shipped TOML cannot silently degrade ``--theme``.

    Reads the file via :mod:`importlib.resources` so the load works under
    zipped imports (PyOxidizer, PEX, certain Nuitka modes) where
    ``Path(__file__).parent`` doesn't resolve to a real filesystem location.
    """
    payload = (
        resources
        .files(__package__)
        .joinpath("themes.toml")
        .read_text(
            encoding="utf-8",
        )
    )
    raw = tomllib.loads(payload)
    return {name: HelpExtraTheme.from_dict(data) for name, data in raw.items()}


BUILTIN_THEMES: dict[str, HelpExtraTheme] = _load_builtin_themes()
"""Mapping of built-in theme names to their :class:`HelpExtraTheme` instances.

Loaded from the package data file ``click_extra/themes.toml`` at module
import time and seeded into :data:`theme_registry`. Adding a new built-in
theme is a one-file edit in that TOML file: declare a new ``[<name>]``
table with one inline-table per styled slot.

Index by name to access any palette, e.g. ``BUILTIN_THEMES["dark"]`` or
``BUILTIN_THEMES["solarized_dark"]``.
"""


OK_GLYPH: str = "✓"
"""Plain check-mark glyph for success indicators.

Style at the call site with the active theme's ``success`` slot:
``get_current_theme().success(OK_GLYPH)``. Stored as a raw string so
downstream code can render it under whichever theme is active rather
than the (frozen) theme that happened to be loaded at import time.
"""

KO_GLYPH: str = "✘"
"""Plain heavy-ballot-X glyph for failure indicators.

Style at the call site with the active theme's ``error`` slot:
``get_current_theme().error(KO_GLYPH)``. See :data:`OK_GLYPH` for why
the glyph is exposed unstyled.
"""


theme_registry.update(BUILTIN_THEMES)
set_default_theme(BUILTIN_THEMES["dark"])
