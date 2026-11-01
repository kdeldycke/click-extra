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

Holds the {class}`HelpTheme` dataclass, the {data}`NOCOLOR_THEME` constant,
the process-wide fallback accessed via
{func}`get_default_theme` / {func}`set_default_theme`, the named-theme
{data}`theme_registry` plus {func}`register_theme` helper, and the
{class}`ThemeOption` that exposes `--theme` on every Click Extra command.

The built-in themes (`dark`, `dracula`, `light`, `manpage`,
`monokai`, `nord`, `solarized-dark`) are plain mappings declared in this module,
each built through {meth}`HelpTheme.from_dict` on its first lookup: importing
the package builds none of them, and a help screen builds only the one it
renders with. `manpage` is a colorless theme that
shadows man-pages(7) typography (bold literals, italic replaceable); the
others apply that same bold/italic split on top of their color palettes.
Those mappings follow the schema of user-defined themes loaded from
configuration: see {doc}`/theme` for the user guide.

```{note}
The active theme for a CLI invocation is stored on the Click context's
`meta` dict under {data}`click_extra.context.THEME` by
{class}`ThemeOption`. Use {func}`get_current_theme` to retrieve it: that
helper consults the active Click context first and falls back to
{func}`get_default_theme` when no context is in flight (like at import
time, in `wrap` patching, or in bare REPL usage). Per-invocation
context storage means concurrent invocations of the same CLI in one
process (Sphinx builds, test runners, REPLs) do not leak `--theme`
choices into each other.
```
"""

from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import MutableMapping
from dataclasses import dataclass
from gettext import gettext as _

import click
import cloup
from click.shell_completion import CompletionItem
from cloup._util import identity

from . import color, context
from ._utils import AUTO
from .envvar import machine_envvars_apply
from .parameters import ExtraOption
from .styling import Style, dict_to_fields, fields_to_dict

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from typing import Any, Final, Self

    from cloup.styling import IStyle

logger = logging.getLogger(__name__)


THEME_ENVVAR: Final[str] = "CLICK_EXTRA_THEME"
"""Environment variable naming the help-screen palette of every Click Extra CLI.

Global and CLI-agnostic, unlike the `<CLI>_THEME` variable Click derives from
the option itself: exporting it once from a shell profile themes every Click
Extra command installed on the machine, including the ones a user wraps with
`click-extra wrap`. It accepts the same values as `--theme`, the
{data}`~click_extra.theme.AUTO_THEME` directive included.

Read by {meth}`~click_extra.theme.ThemeOption.set_theme` as a last resort, so a
`--theme` flag, a `<CLI>_THEME` variable and a configuration file each outrank
it. See that method for why it is read directly instead of being wired through
the option's `envvar`.
"""


def _widen_style(value: Any) -> Any:
    """Widen a `cloup.Style` to {class}`~click_extra.styling.Style`.

    Any other slot value, a `Style` already included, passes through.
    """
    if isinstance(value, cloup.Style) and not isinstance(value, Style):
        return Style() | value
    return value


@dataclass(frozen=True)
class HelpTheme(cloup.HelpTheme):
    """Extends `cloup.HelpTheme` with slots for log levels and the
    structural elements Click Extra highlights in help screens.

    Each slot below documents *what* it colors. The built-in themes shipped
    in {data}`~click_extra.theme.BUILTIN_THEMES` provide the visual styling
    by setting the relevant slots; user-defined themes can be authored as
    plain mappings and loaded via {meth}`from_dict`.
    """

    # --- Log-level slots -----------------------------------------------------
    # Applied by {class}`~click_extra.logging.Formatter` to `levelname`
    # before each record is emitted, so the visible level in the formatted
    # message picks up the matching style.

    critical: IStyle = identity
    """Style applied to the `CRITICAL` level name in log records.

    Example: `CRITICAL: Database connection lost.`
    """

    error: IStyle = identity
    """Style applied to the `ERROR` level name in log records.

    Example: `ERROR: Configuration file not found.`
    """

    warning: IStyle = identity
    """Style applied to the `WARNING` level name in log records.

    Example: `WARNING: Requested 16 jobs exceeds the 8 logical CPUs: honored, but pays only for I/O-bound work.`
    """

    info: IStyle = identity
    """Style applied to the `INFO` level name in log records.

    Usually left at {func}`identity <cloup._util.identity>`: `INFO` is the
    default verbosity and shouldn't stand out from regular output.
    """

    debug: IStyle = identity
    """Style applied to the `DEBUG` level name in log records.

    Example: `DEBUG: Resolved /etc/myapp/config.toml.`
    """

    # --- Help-screen structural slots ----------------------------------------
    # Applied by {class}`~click_extra.highlight.HelpFormatter` while
    # rendering each command's help output. The post-wrap formatter pass
    # walks the rendered help text and styles the matching tokens.

    option: IStyle = identity
    """Style applied to option names (`--config`, `-v`, `--color/--no-color`)
    wherever they appear: synopsis column, free-form descriptions, and
    docstrings (when {attr}`cross_ref_highlight` is enabled).
    """

    subcommand: IStyle = identity
    """Style applied to subcommand names: in a group's command list and
    wherever they are referenced in prose.
    """

    choice: IStyle = identity
    """Style applied to each individual value inside a {class}`click.Choice`
    metavar (like `json`, `csv`, `xml` within `[json|csv|xml]`) and
    to those values referenced in option descriptions.
    """

    metavar: IStyle = identity
    """Style applied to type metavars (`INTEGER`, `TEXT`, `PATH`,
    `FILE`, ...) that follow an option name in the synopsis column.
    """

    bracket: IStyle = identity
    """Style applied to the literal bracket characters and label prefixes of
    trailing fields: `[`, `]`, `default:`, `env var:`, and the field
    separators between them. Also acts as the **fallback** for the four
    inner bracket-field slots ({attr}`envvar`, {attr}`default`,
    {attr}`required`, {attr}`range_label`) whenever any of them is left at
    {func}`identity <cloup._util.identity>`. A theme that only sets
    `bracket` therefore renders the whole bracket field with a single
    uniform style; richer themes layer specific colors on top by setting
    the inner slots.
    """

    envvar: IStyle = identity
    """Style applied to environment-variable values inside `[env var: ...]`
    bracket fields, and to envvar names mentioned in option descriptions.
    Falls back to {attr}`bracket` when left at
    {func}`identity <cloup._util.identity>`, so a theme that only styles
    `bracket` still gets a consistent rendering inside bracket fields.
    """

    default: IStyle = identity
    """Style applied to the default-value content inside `[default: ...]`
    bracket fields. Falls back to {attr}`bracket` when left at
    {func}`identity <cloup._util.identity>`.
    """

    range_label: IStyle = identity
    """Style applied to range expressions (`0<=x<=9`, `x>=1024`,
    `0<=x<100`) that appear inside bracket fields for `IntRange` and
    `FloatRange` options. Falls back to {attr}`bracket` when left at
    {func}`identity <cloup._util.identity>`.
    """

    required: IStyle = identity
    """Style applied to the `required` label inside bracket fields on
    mandatory options. Falls back to {attr}`bracket` when left at
    {func}`identity <cloup._util.identity>`.
    """

    argument: IStyle = identity
    """Style applied to argument metavars (positional parameter names like
    `MY_ARG`, `SCRIPT`, `[FILENAMES]...`) in the synopsis column and
    when referenced in prose.
    """

    deprecated: IStyle = identity
    """Style applied to `(DEPRECATED)` / `(Deprecated: reason)` markers
    appended to options and commands.
    """

    separator: IStyle = identity
    """Style applied to the `--` end-of-options separator, wherever a help
    screen writes it on its own: `my-cli wrap -- target-cli --help`.

    It is punctuation rather than a word, and it reads as one of the target
    CLI's own options until something tells the two apart.
    """

    search: IStyle = identity
    """Style applied to substring matches in {command}`<cli> help --search`
    output, so users can spot where their query matched.
    """

    success: IStyle = identity
    """Style applied to success glyphs in pre-rendered UI elements (the `✓`
    in {data}`~click_extra.theme.OK_GLYPH`) and any text passed through this
    slot by downstream code.
    """

    cross_ref_highlight: bool = True
    """Highlight options, choices, arguments, metavars and CLI names in
    free-form text (descriptions, docstrings).

    When `False`, only structural elements are styled: bracket fields
    (`[default: ...]`, `[env var: ...]`, ranges, `[required]`),
    deprecated messages, and subcommand names in definition lists.
    """

    subheading: IStyle = identity
    """Style for sub-section headings inside log output or inline help.

    Distinct from `heading` (which styles the top-level help-screen
    section titles): {attr}`subheading` is intended for downstream code that
    wants a second styling level for its own narrative output.

    ```{seealso}
    Used by [mail-deduplicate](https://github.com/kdeldycke/mail-deduplicate/blob/main/mail_deduplicate/deduplicate.py)
    to style `◼ N mails sharing hash …` log lines.
    ```
    """

    def with_(  # type: ignore[override]
        self,
        **kwargs: IStyle | bool | None,
    ) -> Self:
        """Derive a new theme from this one, with some slots overridden.

        Returns the same instance when every slot keeps its value, where cloup's
        version builds a copy whatever it is given. `None` is a value like any
        other, not a slot left alone.

        :raises TypeError: listing every argument that names no slot.
        """
        changed = {
            name: value
            for name, value in dict_to_fields(type(self), kwargs).items()
            if value != getattr(self, name)
        }
        return dataclasses.replace(self, **changed) if changed else self

    def _with_cloup_slots(self, theme: cloup.HelpTheme) -> Self:
        """Derive a new theme carrying the slots `cloup.HelpTheme` declares.

        Reads each of those slots from *theme* and keeps the ones this subclass
        adds. Each `cloup.Style` is widened to
        {class}`~click_extra.styling.Style` on the way, the only class
        {meth}`to_dict` and {meth}`cascade` accept.
        """
        return self.with_(**{
            field.name: _widen_style(getattr(theme, field.name))
            for field in dataclasses.fields(cloup.HelpTheme)
        })

    @classmethod
    def dark(cls) -> Self:
        """A theme assuming a dark terminal background color.

        Carries cloup's palette, each style widened to
        {class}`~click_extra.styling.Style`, and leaves the slots this subclass
        adds at their default. For a theme coloring those too, reach for
        {data}`~click_extra.theme.BUILTIN_THEMES` instead.
        """
        return cls()._with_cloup_slots(cloup.HelpTheme.dark())

    @classmethod
    def light(cls) -> Self:
        """A theme assuming a light terminal background color.

        Carries cloup's palette, like {meth}`dark`.
        """
        return cls()._with_cloup_slots(cloup.HelpTheme.light())

    @staticmethod
    def _encode_slot(field: Any, value: Any) -> Any:
        """Encode a slot value for {meth}`to_dict`.

        {class}`~click_extra.styling.Style` instances become their
        {meth}`Style.to_dict <click_extra.styling.Style.to_dict>` mapping;
        `cross_ref_highlight`'s `bool` passes through as-is. Anything
        else (an opaque `IStyle` callable that isn't a {class}`Style`)
        raises {class}`TypeError` since those cannot be serialized.
        """
        if isinstance(value, Style):
            return value.to_dict()
        if field.name == "cross_ref_highlight":
            return value
        raise TypeError(
            f"Cannot serialize HelpTheme.{field.name}: "
            f"{value!r} is not a Style instance."
        )

    @staticmethod
    def _decode_slot(field: Any, raw: Any) -> Any:
        """Decode a slot value for {meth}`from_dict`.

        Mappings become {class}`~click_extra.styling.Style` instances via
        {meth}`Style.from_dict <click_extra.styling.Style.from_dict>`;
        `cross_ref_highlight` is coerced to `bool`; anything else
        raises {class}`TypeError`.
        """
        if field.name == "cross_ref_highlight":
            return bool(raw)
        if isinstance(raw, dict):
            return Style.from_dict(raw)
        raise TypeError(
            f"Cannot deserialize HelpTheme.{field.name}: "
            f"{raw!r} is neither a mapping nor a recognized scalar."
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the theme to a plain dict suitable for TOML/JSON/YAML.

        Each {class}`~click_extra.styling.Style` slot is emitted via
        {meth}`Style.to_dict <click_extra.styling.Style.to_dict>`. Slots left
        at their default (`identity` or
        `None`) are omitted, so the output only carries what the theme
        actually overrides. Pair with {meth}`from_dict` to round-trip.

        :raises TypeError: when a slot holds an opaque `IStyle` callable
            that is not a {class}`~click_extra.styling.Style` (those cannot be
            serialized).
        """
        return fields_to_dict(self, encode=self._encode_slot)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HelpTheme:
        """Build a theme from the plain dict produced by {meth}`to_dict`.

        Each value is interpreted by field type: a mapping becomes a
        {class}`~click_extra.styling.Style` via
        {meth}`Style.from_dict <click_extra.styling.Style.from_dict>`, while
        `cross_ref_highlight` is read as a plain `bool`. Unknown keys
        raise {class}`TypeError` so typos surface immediately.
        """
        return cls(**dict_to_fields(cls, data, decode=cls._decode_slot))

    def cascade(self, base: HelpTheme) -> HelpTheme:
        """Layer this theme's set slots on top of *base*.

        Mirrors {meth}`Style.cascade <click_extra.styling.Style.cascade>` at
        the slot level: this theme's non-default slots win, *base* fills the
        rest. Useful for layering a sparse override (typically parsed from a
        config file's `[tool.<cli>.themes.<name>]` table) on top of a
        full built-in palette.

        :raises TypeError: when *base* is not a {class}`HelpTheme`.
        """
        if not isinstance(base, HelpTheme):
            raise TypeError(
                f"Cannot cascade onto {type(base).__name__}: not a HelpTheme."
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
    "separator",
})
r"""Names of the {class}`HelpTheme` slots that color *literal* tokens:
text the user types verbatim on the command line.

Covers the command and subcommand names, their aliases, option flags
(`--config`, `-v`), the concrete values of a {class}`click.Choice`
(`json` in `[json|csv|xml]`), and the `--` separator.

These map to the **bold** font of the man-pages(7) typographic convention,
which sets text "typed literally" in bold (`\fB` in roff) "even in the
SYNOPSIS section". Paired with {data}`REPLACEABLE_STYLES`: the two are
disjoint, and every remaining slot is an annotation, prose, or chrome style
that the literal/replaceable dichotomy does not classify (log levels,
`[default: ...]` / `[env var: ...]` fields, headings, ...).

```{note}
Every built-in theme applies this classification: literal slots render
bold and {data}`REPLACEABLE_STYLES` italic, mirroring a man page even in
the color palettes. `tests/test_theme.py` enforces the invariant, and
the `manpage` built-in theme is its pure-monochrome embodiment
(bold/italic, no color). The man-page generator of
{mod}`click_extra.command_doc` follows the same split, setting each token in
`\fB` or `\fI`.
```
"""

REPLACEABLE_STYLES: frozenset[str] = frozenset({
    "metavar",
    "argument",
})
r"""Names of the {class}`HelpTheme` slots that color *replaceable* tokens:
placeholders the user substitutes with a real value.

Covers type metavars on options (`INTEGER`, `PATH`) and positional
argument metavars (`SOURCE`, `[FILENAMES]...`).

These map to the *italic* font of the man-pages(7) convention, which sets
replaceable arguments in italic (`\fI` in roff). See {data}`LITERAL_STYLES`
for the bold counterpart and the full rationale.
"""


NOCOLOR_THEME: HelpTheme = HelpTheme()
"""Color theme for Click Extra to force no colors.

All style slots default to `identity`, so styling
calls return the raw text unchanged.
"""


_BUILTIN_THEME_DEFINITIONS: Final[dict[str, dict[str, Any]]] = {
    # Theme tuned for terminals with a dark background. Used as the process-wide
    # default, returned by get_default_theme().
    "dark": {
        "invoked_command": {"fg": "bright_white", "bold": True},
        "heading": {"fg": "bright_blue", "underline": True},
        "constraint": {"fg": "magenta"},
        "alias": {"fg": "cyan", "bold": True},
        "alias_secondary": {"fg": "cyan", "dim": True, "bold": True},
        "critical": {"fg": "red", "bold": True},
        "error": {"fg": "red"},
        "warning": {"fg": "yellow"},
        "debug": {"fg": "blue"},
        "option": {"fg": "cyan", "bold": True},
        "subcommand": {"fg": "cyan", "bold": True},
        "choice": {"fg": "magenta", "bold": True},
        "metavar": {"fg": "cyan", "dim": True, "italic": True},
        "bracket": {"dim": True},
        "envvar": {"fg": "yellow", "dim": True},
        "default": {"fg": "green", "dim": True, "italic": True},
        "range_label": {"fg": "cyan", "dim": True},
        "required": {"fg": "red", "dim": True},
        "argument": {"fg": "cyan", "italic": True},
        "separator": {"fg": "bright_white", "dim": True, "bold": True},
        "deprecated": {"fg": "bright_yellow"},
        "search": {"fg": "green"},
        "success": {"fg": "green"},
        "subheading": {"fg": "blue"},
    },
    # Dracula by Zeno Rocha. High-contrast dark theme with vivid neon accents,
    # from the https://draculatheme.com/contribute palette.
    "dracula": {
        "invoked_command": {"fg": "#f8f8f2", "bold": True},
        "heading": {"fg": "#ff79c6", "underline": True},
        "constraint": {"fg": "#ff79c6"},
        "alias": {"fg": "#8be9fd", "bold": True},
        "alias_secondary": {"fg": "#8be9fd", "dim": True, "bold": True},
        "critical": {"fg": "#ff5555", "bold": True},
        "error": {"fg": "#ff5555"},
        "warning": {"fg": "#ffb86c"},
        "debug": {"fg": "#6272a4"},
        "option": {"fg": "#bd93f9", "bold": True},
        "subcommand": {"fg": "#bd93f9", "bold": True},
        "choice": {"fg": "#ff79c6", "bold": True},
        "metavar": {"fg": "#bd93f9", "dim": True, "italic": True},
        "bracket": {"fg": "#6272a4"},
        "envvar": {"fg": "#ffb86c", "dim": True},
        "default": {"fg": "#50fa7b", "dim": True, "italic": True},
        "range_label": {"fg": "#bd93f9", "dim": True},
        "required": {"fg": "#ff5555", "dim": True},
        "argument": {"fg": "#bd93f9", "italic": True},
        "separator": {"fg": "#f8f8f2", "dim": True, "bold": True},
        "deprecated": {"fg": "#ffb86c"},
        "search": {"fg": "#f1fa8c"},
        "success": {"fg": "#50fa7b"},
        "subheading": {"fg": "#8be9fd"},
    },
    # Theme tuned for terminals with a light/white background. Mirrors `dark`
    # but swaps the palette for one that stays legible on white: bright variants
    # (washed-out on most terminals) become standard counterparts, bright_white
    # becomes black, and cyan accents become blue (cyan on white is hard to read).
    "light": {
        "invoked_command": {"fg": "black", "bold": True},
        "heading": {"fg": "magenta", "underline": True},
        "constraint": {"fg": "magenta"},
        "alias": {"fg": "blue", "bold": True},
        "alias_secondary": {"fg": "blue", "dim": True, "bold": True},
        "critical": {"fg": "red", "bold": True},
        "error": {"fg": "red"},
        "warning": {"fg": "magenta"},
        "debug": {"fg": "blue", "dim": True},
        "option": {"fg": "blue", "bold": True},
        "subcommand": {"fg": "blue", "bold": True},
        "choice": {"fg": "magenta", "bold": True},
        "metavar": {"fg": "blue", "dim": True, "italic": True},
        "bracket": {"dim": True},
        "envvar": {"fg": "magenta", "dim": True},
        "default": {"fg": "green", "dim": True, "italic": True},
        "range_label": {"fg": "blue", "dim": True},
        "required": {"fg": "red", "dim": True},
        "argument": {"fg": "blue", "italic": True},
        "separator": {"fg": "black", "dim": True, "bold": True},
        "deprecated": {"fg": "red"},
        "search": {"fg": "green"},
        "success": {"fg": "green"},
        "subheading": {"fg": "blue", "dim": True},
    },
    # Monochrome theme shadowing man-pages(7) typography: bold for literal tokens,
    # italic for replaceable ones, no color. Useful for low-color terminals,
    # screenshots, or matching how a command reads in its own man page. The
    # literal/replaceable split is the one LITERAL_STYLES and REPLACEABLE_STYLES
    # encode.
    "manpage": {
        "invoked_command": {"bold": True},
        "heading": {"underline": True},
        "alias": {"bold": True},
        "alias_secondary": {"bold": True},
        "option": {"bold": True},
        "subcommand": {"bold": True},
        "choice": {"bold": True},
        "metavar": {"italic": True},
        "argument": {"italic": True},
        "separator": {"bold": True},
    },
    # Monokai by Wimer Hazenberg. Classic dark theme with high-saturation magenta
    # and lime accents, from the https://monokai.pro/ palette.
    "monokai": {
        "invoked_command": {"fg": "#f8f8f2", "bold": True},
        "heading": {"fg": "#a6e22e", "underline": True},
        "constraint": {"fg": "#ae81ff"},
        "alias": {"fg": "#a6e22e", "bold": True},
        "alias_secondary": {"fg": "#a6e22e", "dim": True, "bold": True},
        "critical": {"fg": "#f92672", "bold": True},
        "error": {"fg": "#f92672"},
        "warning": {"fg": "#fd971f"},
        "debug": {"fg": "#75715e"},
        "option": {"fg": "#66d9ef", "bold": True},
        "subcommand": {"fg": "#66d9ef", "bold": True},
        "choice": {"fg": "#ae81ff", "bold": True},
        "metavar": {"fg": "#66d9ef", "dim": True, "italic": True},
        "bracket": {"fg": "#75715e"},
        "envvar": {"fg": "#fd971f", "dim": True},
        "default": {"fg": "#e6db74", "dim": True, "italic": True},
        "range_label": {"fg": "#66d9ef", "dim": True},
        "required": {"fg": "#f92672", "dim": True},
        "argument": {"fg": "#66d9ef", "italic": True},
        "separator": {"fg": "#f8f8f2", "dim": True, "bold": True},
        "deprecated": {"fg": "#fd971f"},
        "search": {"fg": "#e6db74"},
        "success": {"fg": "#a6e22e"},
        "subheading": {"fg": "#a6e22e"},
    },
    # Nord by Arctic Ice Studio. Cool-toned dark theme built around frost-blue
    # and aurora accents, from the
    # https://www.nordtheme.com/docs/colors-and-palettes palette.
    "nord": {
        "invoked_command": {"fg": "#eceff4", "bold": True},  # nord6: snow storm.
        "heading": {"fg": "#5e81ac", "underline": True},  # nord10.
        "constraint": {"fg": "#b48ead"},  # nord15.
        "alias": {"fg": "#8fbcbb", "bold": True},  # nord7.
        "alias_secondary": {"fg": "#8fbcbb", "dim": True, "bold": True},
        "critical": {"fg": "#bf616a", "bold": True},  # nord11: aurora.
        "error": {"fg": "#bf616a"},
        "warning": {"fg": "#d08770"},  # nord12.
        "debug": {"fg": "#4c566a"},  # nord3: polar night.
        "option": {"fg": "#81a1c1", "bold": True},  # nord9.
        "subcommand": {"fg": "#81a1c1", "bold": True},
        "choice": {"fg": "#b48ead", "bold": True},
        "metavar": {"fg": "#81a1c1", "dim": True, "italic": True},
        "bracket": {"fg": "#4c566a"},
        "envvar": {"fg": "#d08770", "dim": True},
        "default": {"fg": "#a3be8c", "dim": True, "italic": True},  # nord14.
        "range_label": {"fg": "#81a1c1", "dim": True},
        "required": {"fg": "#bf616a", "dim": True},
        "argument": {"fg": "#81a1c1", "italic": True},
        "separator": {"fg": "#e5e9f0", "dim": True, "bold": True},
        "deprecated": {"fg": "#d08770"},
        "search": {"fg": "#ebcb8b"},  # nord13.
        "success": {"fg": "#a3be8c"},
        "subheading": {"fg": "#88c0d0"},  # nord8.
    },
    # Solarized Dark by Ethan Schoonover. Warm-toned dark theme with selective
    # accent contrast, from the https://ethanschoonover.com/solarized/ palette.
    "solarized-dark": {
        "invoked_command": {"fg": "#eee8d5", "bold": True},  # base2: emphasized.
        "heading": {"fg": "#6c71c4", "underline": True},
        "constraint": {"fg": "#6c71c4"},
        "alias": {"fg": "#2aa198", "bold": True},
        "alias_secondary": {"fg": "#2aa198", "dim": True, "bold": True},
        "critical": {"fg": "#dc322f", "bold": True},
        "error": {"fg": "#dc322f"},
        "warning": {"fg": "#b58900"},
        "debug": {"fg": "#586e75"},  # base01.
        "option": {"fg": "#268bd2", "bold": True},
        "subcommand": {"fg": "#268bd2", "bold": True},
        "choice": {"fg": "#6c71c4", "bold": True},
        "metavar": {"fg": "#268bd2", "dim": True, "italic": True},
        "bracket": {"fg": "#586e75"},
        "envvar": {"fg": "#cb4b16", "dim": True},
        "default": {"fg": "#859900", "dim": True, "italic": True},
        "range_label": {"fg": "#268bd2", "dim": True},
        "required": {"fg": "#dc322f", "dim": True},
        "argument": {"fg": "#268bd2", "italic": True},
        "separator": {"fg": "#93a1a1", "dim": True, "bold": True},
        "deprecated": {"fg": "#d33682"},
        "search": {"fg": "#b58900"},
        "success": {"fg": "#859900"},
        "subheading": {"fg": "#2aa198"},
    },
}
"""Slot styles of each built-in theme, keyed by theme name.

Each value is the mapping {meth}`HelpTheme.from_dict` reads, in the shape of a
`[tool.<cli>.themes.<name>]` configuration table. Adding a built-in theme is a
one-entry edit here. Names are kept in alphabetical order, which
`tests/test_theme.py` enforces.
"""


_built_themes: dict[str, HelpTheme] = {}
"""The built-in themes built so far, keyed by name. See {func}`_builtin_theme`."""


def _builtin_theme(name: str) -> HelpTheme:
    """Return the built-in theme *name*, built from its definition on first call.

    Later calls return the same instance, so an identity check against a
    built-in theme holds wherever it was looked up.

    :raises KeyError: when *name* is not a built-in theme.
    """
    theme = _built_themes.get(name)
    if theme is None:
        # setdefault keeps one instance per name if two threads build it at once.
        theme = _built_themes.setdefault(
            name, HelpTheme.from_dict(_BUILTIN_THEME_DEFINITIONS[name])
        )
    return theme


class _LazyThemes(MutableMapping[str, HelpTheme]):
    """A `{name: HelpTheme}` mapping that builds a built-in theme on its first lookup.

    A built-in theme is a `None` placeholder until something reads its value.
    Listing, counting or testing the names builds nothing, so `--theme` lists
    its choices for free and a help screen builds only the theme it renders
    with. Any other value is stored and returned as given.
    """

    def __init__(self, themes: Mapping[str, HelpTheme] | None = None) -> None:
        """Start from every built-in theme, or from a copy of *themes*.

        A `_LazyThemes` hands over its placeholders as they are, so copying one
        builds no theme.
        """
        self._themes: dict[str, HelpTheme | None]
        if themes is None:
            self._themes = dict.fromkeys(_BUILTIN_THEME_DEFINITIONS)
        elif isinstance(themes, _LazyThemes):
            self._themes = themes._themes.copy()
        else:
            self._themes = dict(themes)

    def __getitem__(self, name: str) -> HelpTheme:
        theme = self._themes[name]
        return _builtin_theme(name) if theme is None else theme

    def __setitem__(self, name: str, theme: HelpTheme) -> None:
        self._themes[name] = theme

    def __delitem__(self, name: str) -> None:
        del self._themes[name]

    def __contains__(self, name: object) -> bool:
        # Overridden: the inherited version reads the value, building the theme.
        return name in self._themes

    def __iter__(self) -> Iterator[str]:
        return iter(self._themes)

    def __len__(self) -> int:
        return len(self._themes)

    def clear(self) -> None:
        # Overridden: the inherited version pops, and so builds, every theme.
        self._themes.clear()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._themes)!r})"


BUILTIN_THEMES: Mapping[str, HelpTheme] = _LazyThemes()
"""Mapping of built-in theme names to their {class}`HelpTheme` instances.

Each theme is built from its definition in this module on its first lookup, and
the same instance is returned from then on. {data}`theme_registry` starts with
the same entries.

Index by name to access any palette, like `BUILTIN_THEMES["dark"]` or
`BUILTIN_THEMES["solarized-dark"]`.
"""


_default_theme: HelpTheme | None = None
"""Process-wide fallback theme set by {func}`set_default_theme`, if any.

`None` until then: {func}`get_default_theme` answers the built-in `dark` theme.
"""


def get_default_theme() -> HelpTheme:
    """Return the process-wide fallback theme.

    Read by {func}`get_current_theme` when no Click context is active or
    when the active context has no theme set. The default is the built-in
    `dark` palette; {func}`~click_extra.cli_wrapper.patch_click` overrides it
    via {func}`set_default_theme` for the duration of a patched session.

    Resolved through a function rather than a module attribute so callers
    always observe the current value: a module attribute bound once, like a
    default parameter value, keeps whatever was set at import time.
    """
    return _builtin_theme("dark") if _default_theme is None else _default_theme


def set_default_theme(theme: HelpTheme) -> None:
    """Override the process-wide fallback theme.

    {class}`ThemeOption` writes its picked theme to `ctx.meta` rather
    than calling this helper, so per-invocation choices do not leak across
    invocations sharing the same process. Use this only for genuinely
    process-wide overrides: {func}`~click_extra.cli_wrapper.patch_click` is the
    canonical caller.
    """
    global _default_theme
    _default_theme = theme


def get_current_theme() -> HelpTheme:
    """Return the theme active for the current CLI invocation.

    Resolution order:

    1. The theme stored on the active Click context under
       {data}`click_extra.context.THEME` (set by {class}`ThemeOption`
       from `--theme`).
    2. The process-wide fallback returned by {func}`get_default_theme`
       (the dark default, or whatever {func}`~click_extra.cli_wrapper.patch_click`
       set at process start).

    Falling back through the active context (instead of reading a module
    attribute) keeps `--theme` scoped to the invocation that received it,
    so a second invocation in the same process starts from the default
    again.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is not None:
        active: HelpTheme | None = context.get(ctx, context.THEME)
        if active is not None:
            return active
    return get_default_theme()


theme_registry: MutableMapping[str, HelpTheme] = _LazyThemes()
"""Process-wide registry of named themes used by {class}`ThemeOption`.

Each entry maps a theme name to its {class}`HelpTheme` instance. It starts with
the entries of {data}`BUILTIN_THEMES`, each built on its first lookup.

Use {func}`register_theme` to add your own at import time, *or* declare
them in your CLI's config file under `[tool.<cli>.themes.<name>]`: the
latter goes through {class}`ConfigOption <click_extra.config.option.ConfigOption>`,
lands on `ctx.meta` (see {data}`click_extra.context.THEME_OVERRIDES`),
and never mutates this module-level dict, so per-invocation choices don't
leak between sibling invocations sharing the same process.
"""


def register_theme(name: str, theme: HelpTheme) -> None:
    """Register a named theme in the module-level
    {data}`~click_extra.theme.theme_registry`.

    :param name: Lowercase identifier used as the `--theme` choice value.
    :param theme: A {class}`HelpTheme` instance.
    """
    theme_registry[name] = theme


def get_theme_registry(
    ctx: click.Context | None = None,
) -> MutableMapping[str, HelpTheme]:
    """Return the theme registry visible to *ctx*.

    Merges the module-level {data}`theme_registry` with any per-invocation
    overrides stored on `ctx.meta` under
    {data}`click_extra.context.THEME_OVERRIDES`. Per-invocation entries win
    on key collisions, which is what lets a config file's
    `[tool.<cli>.themes.dark]` table override the built-in `dark` palette
    for one invocation without touching the global registry.

    When *ctx* is `None` or has no overrides, returns a copy of the
    module-level registry. Either way, a built-in theme is built only when its
    value is read.
    """
    merged = _LazyThemes(theme_registry)
    if ctx is not None:
        overrides = context.get(ctx, context.THEME_OVERRIDES)
        if overrides:
            merged.update(overrides)
    return merged


AUTO_THEME: str = AUTO
"""Reserved `--theme` value resolving the palette from the terminal background.

Unlike the named built-in palettes, `auto` is not a registry entry: it is a
directive handled by {class}`ThemeOption`, which calls {func}`resolve_auto_theme`
to pick `dark` or `light` from the detected background, mirroring
`--color=auto`.

It is advertised all the same, in the `--help` metavar and in shell completion
({attr}`ThemeChoice.choices`), because it works on every Click Extra CLI whether
or not that CLI knows about it: a value accepted everywhere and named nowhere is
one nobody finds. `--color` lists its own `auto` beside `always` and `never` for
the same reason.
"""


def _theme_choices(ctx: click.Context | None = None) -> tuple[str, ...]:
    """The values `--theme` takes in `ctx`, alphabetically sorted.

    The theme names {func}`get_theme_registry` sees, plus {data}`AUTO_THEME`.
    """
    return tuple(sorted({AUTO_THEME, *get_theme_registry(ctx)}))


def resolve_auto_theme(
    ctx: click.Context | None = None,
    query_background: bool = False,
) -> HelpTheme | None:
    """Pick a built-in palette from the detected terminal background.

    Resolves the background mode via
    {func}`~click_extra.color.resolve_background` and maps `"dark"` /
    `"light"` to the same-named theme in the registry visible to *ctx*
    (built-ins plus any `[tool.<cli>.themes.<name>]` config overlays). An
    undetected background falls back to `"dark"`, preserving Click Extra's
    default.

    :param ctx: context whose theme registry is consulted.
    :param query_background: when true, allow the live OSC 11 terminal query
        ({func}`~click_extra.color.query_osc_background`) on top of the
        environment-variable signals. Off by default because the query reads
        stdin.
    :return: the chosen {class}`HelpTheme`, or `None` when neither the
        detected palette nor the `dark` fallback is registered (both were
        removed from the registry). A `None` leaves `ctx.meta` untouched so
        {func}`get_current_theme` keeps the default theme.
    """
    registry = get_theme_registry(ctx)
    mode = color.resolve_background(query_background=query_background)
    for name in (mode, "dark"):
        if name is not None and name in registry:
            return registry[name]
    return None


def themes_from_config(
    table: dict[str, Any],
) -> dict[str, HelpTheme]:
    """Build a ``{name: HelpTheme}`` mapping from a `[tool.<cli>.themes]` sub-tree.

    For each entry, build a {class}`HelpTheme` via {meth}`HelpTheme.from_dict`. If
    *name* matches an existing key in {data}`theme_registry`, the new theme
    is layered on top via {meth}`HelpTheme.cascade` so partial overrides
    (like just one slot) inherit the rest from the built-in palette.
    Stand-alone names produce theme instances with the unset slots left at
    their defaults.
    """
    result: dict[str, HelpTheme] = {}
    for name, slots in table.items():
        overlay = HelpTheme.from_dict(slots)
        if name in theme_registry:
            result[name] = overlay.cascade(theme_registry[name])
        else:
            result[name] = overlay
    return result


def validate_themes_config(themes_subtree: dict[str, Any]) -> None:
    """Validate a `[tool.<cli>.themes]` sub-tree.

    Registered as a built-in {class}`ConfigValidator <click_extra.config.schema.ConfigValidator>`
    by {class}`ConfigOption <click_extra.config.option.ConfigOption>` so malformed
    theme tables surface as {class}`~click_extra.config.schema.ValidationError` with
    a rooted path (`my-cli.themes.<name>`) rather than a deep
    {class}`TypeError` from {meth}`HelpTheme.from_dict`.
    """
    # Lazy-imported to avoid a load-time cycle with the config package.
    from .config import ValidationError

    for name, slots in themes_subtree.items():
        if not isinstance(slots, dict):
            raise ValidationError(
                path=name,
                message=(
                    f"theme definition must be a table, got {type(slots).__name__}"
                ),
                code="invalid_theme_shape",
            )
        try:
            HelpTheme.from_dict(slots)
        except TypeError as exc:
            raise ValidationError(
                path=name,
                message=str(exc),
                code="invalid_theme",
            ) from exc


class ThemeChoice(click.ParamType):
    """A {class}`click.ParamType` whose `choices` track the live theme registry.

    Implements the `click.Choice`-shaped duck interface (`choices`,
    `case_sensitive`, `normalize_choice`) so {mod}`click_extra.highlight`
    can collect theme names for per-token highlighting through the same
    code path it uses for Click's own `Choice`. The `choices` attribute
    is a property that queries {func}`get_theme_registry` at every lookup,
    so themes registered late (typically by
    {class}`ConfigOption <click_extra.config.option.ConfigOption>` parsing
    `[tool.<cli>.themes.<name>]` tables before `--theme` is processed)
    are valid choices and appear in the `--help` metavar.

    A plain {class}`click.ParamType` rather than a {class}`click.Choice`
    subclass: `click.Choice.__init__` assigns `self.choices`, which a
    read-only property cannot take.
    """

    # Match `click.Choice.name` so machinery that branches on parameter
    # type (like metavar generation) treats this the same way.
    name: str = "choice"

    def __init__(self, case_sensitive: bool = False) -> None:
        self.case_sensitive = case_sensitive

    @property
    def choices(self) -> tuple[str, ...]:
        """Values `--theme` takes, alphabetically sorted.

        The theme names visible in the current context, plus
        {data}`AUTO_THEME`, which says why a directive is listed among them.
        """
        return _theme_choices(click.get_current_context(silent=True))

    def _normalize(self, value: str) -> str:
        return value if self.case_sensitive else value.casefold()

    def normalize_choice(self, choice: Any, ctx: click.Context | None) -> str:
        """Mirrors {meth}`click.Choice.normalize_choice` for highlight compatibility."""
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
        """Resolve *value* to a canonical theme name from the live registry.

        Normalizes *value* and looks it up against the names visible in
        *ctx*. Returns the canonical name, `None` when no themes are
        registered at all (an inert `--theme`), and calls `fail` when
        *value* is not a string or does not match any registered theme.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            self.fail(f"{value!r} is not a string.", param, ctx)
        # "auto" is a reserved directive resolved from the terminal background by
        # ThemeOption, not a registered palette, so it bypasses the registry lookup.
        if self._normalize(value) == self._normalize(AUTO_THEME):
            return AUTO_THEME
        registry = get_theme_registry(ctx)
        # No themes available at all: every palette was removed from the
        # registry and no config themes are defined. The --theme option is
        # inert, so ignore the value (including the built-in "dark" default,
        # which then resolves to nothing) and let get_current_theme() fall back
        # to the default theme instead of failing the whole invocation.
        if not registry:
            return None
        lookup = {self._normalize(name): name for name in registry}
        canonical = lookup.get(self._normalize(value))
        if canonical is None:
            choices = "|".join(_theme_choices(ctx))
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
    ) -> list[CompletionItem]:
        prefix = self._normalize(incomplete)
        return [
            CompletionItem(name)
            for name in _theme_choices(ctx)
            if self._normalize(name).startswith(prefix)
        ]


class ThemeOption(ExtraOption):
    """A pre-configured option that adds `--theme` to select the help-screen palette.

    Accepts any name registered in {data}`~click_extra.theme.theme_registry`
    *or* in the per-invocation overrides loaded by
    {class}`ConfigOption <click_extra.config.option.ConfigOption>` from
    `[tool.<cli>.themes.<name>]`. Validation goes through
    {class}`~click_extra.theme.ThemeChoice`, which reads the live registry at
    parse time, so
    config-defined themes appear as valid choices and in the `--help`
    metavar without any further wiring.

    The resolved {class}`HelpTheme` lands on the Click context under
    {data}`click_extra.context.THEME` and applies for the duration of the
    current invocation only.

    A user who never passes the flag can still pick a palette by exporting
    {data}`~click_extra.theme.THEME_ENVVAR` (`CLICK_EXTRA_THEME`), which is
    honored by every Click Extra CLI at once. See {meth}`set_theme` for how it
    ranks against the flag, the `<CLI>_THEME` variable and the configuration
    file.

    The reserved value {data}`~click_extra.theme.AUTO_THEME` (`--theme=auto`)
    is also accepted on every CLI: it resolves the palette from the terminal
    background via {func}`~click_extra.theme.resolve_auto_theme` instead of
    naming a registered theme. Background detection reads environment variables
    by default; pass `query_background=True` to additionally allow the live
    OSC 11 terminal query ({func}`~click_extra.color.query_osc_background`),
    which is opt-in because it reads stdin.
    """

    def set_theme(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: str | None,
    ) -> None:
        """Resolve the chosen theme name and store it on the Click context.

        {class}`~click_extra.theme.ThemeChoice` has already validated *value*
        against the live registry (or accepted the
        {data}`~click_extra.theme.AUTO_THEME` directive) by the time this fires.
        A plain palette name is looked up unconditionally; `auto` is resolved
        from the terminal background via
        {func}`~click_extra.theme.resolve_auto_theme`, leaving `ctx.meta`
        untouched when no palette can be resolved so {func}`get_current_theme`
        keeps its default.

        Before that, {data}`~click_extra.theme.THEME_ENVVAR` is consulted when
        the value still comes from the option's own default, as for every
        machine-wide variable (see
        {func}`~click_extra.envvar.machine_envvars_apply`). This yields the
        precedence: `--theme` > `<CLI>_THEME` > configuration file >
        `CLICK_EXTRA_THEME` > built-in default. The global variable therefore
        only names the palette of the CLIs nothing else has an opinion about.

        ```{note}
        The variable is read here rather than wired through the option's
        `envvar`. Click resolves an explicit `envvar` *before* the
        auto-generated `<CLI>_THEME`, which would let the machine-wide
        preference outrank the CLI-specific one, and would list both names in
        the `--params` table, making the combined string the widest cell of its
        column. This mirrors how
        {class}`~click_extra.accessibility.AccessibleOption` reads `ACCESSIBLE`
        and {class}`~click_extra.color.ColorOption` reads `NO_COLOR`.
        ```

        An unparsable palette name is a warning, not an error: a typo in a
        shell profile would otherwise break every Click Extra CLI on the
        machine at once, including the ones needed to fix it.
        """
        if ctx.resilient_parsing:
            return

        # Nothing more specific picked a palette, so let the machine-wide
        # variable have the last word before the built-in default.
        if machine_envvars_apply(ctx, param):
            raw = os.environ.get(THEME_ENVVAR)
            if raw:
                try:
                    value = param.type.convert(raw, param, ctx)
                except click.BadParameter:
                    logger.warning(
                        "Ignoring %s=%r: not one of [%s].",
                        THEME_ENVVAR,
                        raw,
                        "|".join(_theme_choices(ctx)),
                    )

        if value is None:
            return
        if value == AUTO_THEME:
            theme = resolve_auto_theme(ctx, query_background=self.query_background)
            if theme is not None:
                context.set(ctx, context.THEME, theme)
            return
        context.set(ctx, context.THEME, get_theme_registry(ctx)[value])

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
        default: str = "dark",
        is_eager: bool = True,
        expose_value: bool = False,
        query_background: bool = False,
        help: str = _("Color theme used for help screens."),
        **kwargs: Any,
    ) -> None:
        if not param_decls:
            param_decls = ("--theme",)

        # Read by set_theme when resolving the "auto" directive: gates the
        # live OSC 11 query on top of the environment-variable detection.
        self.query_background = query_background

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


OK_GLYPH: str = "✓"
"""Plain check-mark glyph for success indicators.

Style at the call site with the active theme's `success` slot:
`get_current_theme().success(OK_GLYPH)`. Stored as a raw string so
downstream code can render it under whichever theme is active rather
than the (frozen) theme that happened to be loaded at import time.
"""

KO_GLYPH: str = "✘"
"""Plain heavy-ballot-X glyph for failure indicators.

Style at the call site with the active theme's `error` slot:
`get_current_theme().error(KO_GLYPH)`. See {data}`~click_extra.theme.OK_GLYPH` for why
the glyph is exposed unstyled.
"""
