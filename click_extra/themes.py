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
"""Built-in :class:`~click_extra.theme.HelpExtraTheme` palettes.

Each theme is a frozen :class:`~click_extra.theme.HelpExtraTheme` subclass that
overrides the default field values with its own palette. The corresponding
UPPER_CASE module-level constant is a cached singleton instance ready to use:

.. code-block:: python

    from click_extra.themes import SOLARIZED_DARK, SolarizedDark

    # Use the cached instance directly:
    SOLARIZED_DARK.option("--theme")

    # Or instantiate the class for a fresh copy you can subclass / `.with_()`:
    my_theme = SolarizedDark().with_(option=Style(fg=Color.bright_cyan))

Shipping two flavors:

- **ANSI themes** (:class:`Dark`, :class:`Light`) use the 16 named ANSI colors
  via :class:`Color <cloup.styling.Color>` enums, so the rendered colors
  follow whatever palette the user's terminal is configured with. Best when
  you want to blend in with the user's terminal theme.

- **Branded themes** (:class:`Dracula`, :class:`Monokai`, :class:`Nord`,
  :class:`SolarizedDark`) use 24-bit RGB triplets from each theme's
  canonical palette, so the rendered colors match the published scheme
  regardless of the user's terminal configuration. Each theme's colors are
  mapped onto Click Extra's help-screen slots by hand: there's no automated
  translation from generic colour-scheme formats (base16, pygments, ...)
  because none of those formats expose the same semantic roles we care
  about (option, metavar, choice, deprecated, envvar, ...).

Adding a new theme is a one-file change here: subclass
:class:`~click_extra.theme.HelpExtraTheme`, override the relevant field
defaults, instantiate it as an UPPER_CASE constant, and add the constant to
:data:`BUILTIN_THEMES`. The :mod:`click_extra.theme` module imports
:data:`BUILTIN_THEMES` at the end of its own load to seed
:data:`~click_extra.theme.theme_registry`.

Third-party packages can grow the registry at runtime via
:func:`click_extra.theme.register_theme`.

Theme classes, palette constants, and singleton instances are kept in
**alphabetical order** by their identifier. The ``test_themes_alphabetical``
test in ``tests/test_themes.py`` enforces this so adding a new theme always
slots in cleanly.

The "Shared style constants" section below collects ANSI-named styles reused
across :class:`Dark` and :class:`Light`. Branded themes declare their palette
inline as private ``_`` constants so each theme reads top-to-bottom.
"""

from __future__ import annotations

from dataclasses import dataclass

from cloup._util import identity
from cloup.styling import Color

from . import Style
from .theme import HelpExtraTheme

TYPE_CHECKING = False
if TYPE_CHECKING:
    from cloup.styling import IStyle


# --- Shared style constants (named by visual properties) ----------------------

DIM = Style(dim=True)

# Cyan family: dark theme's accent color.
CYAN = Style(fg=Color.cyan)
CYAN_DIM = Style(fg=Color.cyan, dim=True)

# Blue family: dark theme's debug/subheading + light theme's accent color.
BLUE = Style(fg=Color.blue)
BLUE_DIM = Style(fg=Color.blue, dim=True)

# Red family: errors and required markers (shared by both themes).
RED = Style(fg=Color.red)
RED_BOLD = Style(fg=Color.red, bold=True)
RED_DIM = Style(fg=Color.red, dim=True)

# Green family: success/default value/search highlight (shared).
GREEN = Style(fg=Color.green)
GREEN_BOLD = Style(fg=Color.green, bold=True)
GREEN_DIM_ITALIC = Style(fg=Color.green, dim=True, italic=True)

# Magenta family: constraints and choices (shared).
MAGENTA = Style(fg=Color.magenta)
MAGENTA_DIM = Style(fg=Color.magenta, dim=True)

# Yellow family: dark theme's warning/envvar.
YELLOW = Style(fg=Color.yellow)
YELLOW_DIM = Style(fg=Color.yellow, dim=True)

# Bright variants for dark theme's high-contrast slots.
BRIGHT_WHITE = Style(fg=Color.bright_white)
BRIGHT_YELLOW_BOLD = Style(fg=Color.bright_yellow, bold=True)
BRIGHT_BLUE_HEADING = Style(fg=Color.bright_blue, bold=True, underline=True)

# Light theme's heading/invoked-command (avoid bright variants on white).
BLACK_BOLD = Style(fg=Color.black, bold=True)
BLUE_HEADING = Style(fg=Color.blue, bold=True, underline=True)


# --- Dark by Click Extra ------------------------------------------------------


@dataclass(frozen=True)
class Dark(HelpExtraTheme):
    """Theme tuned for terminals with a dark background.

    Used as the process-wide :data:`~click_extra.theme.default_theme`.
    """

    invoked_command: IStyle = BRIGHT_WHITE
    heading: IStyle = BRIGHT_BLUE_HEADING
    constraint: IStyle = MAGENTA
    # Neutralize Cloup's col1: it interferes with our finer per-token styling.
    col1: IStyle = identity
    alias: IStyle = CYAN
    alias_secondary: IStyle = CYAN_DIM
    # Log levels.
    critical: IStyle = RED_BOLD
    error: IStyle = RED
    warning: IStyle = YELLOW
    info: IStyle = identity  # INFO is the default level: no styling.
    debug: IStyle = BLUE
    # Click Extra slots.
    option: IStyle = CYAN
    subcommand: IStyle = CYAN
    choice: IStyle = MAGENTA
    metavar: IStyle = CYAN_DIM
    bracket: IStyle = DIM
    envvar: IStyle = YELLOW_DIM
    default: IStyle = GREEN_DIM_ITALIC
    range_label: IStyle = CYAN_DIM
    required: IStyle = RED_DIM
    argument: IStyle = CYAN
    deprecated: IStyle = BRIGHT_YELLOW_BOLD
    search: IStyle = GREEN_BOLD
    success: IStyle = GREEN
    # Non-canonical Click Extra slots.
    subheading: IStyle = BLUE


# --- Dracula by Zeno Rocha ---------------------------------------------------
# Palette: https://draculatheme.com/contribute

_drac_comment = (0x62, 0x72, 0xa4)
_drac_cyan = (0x8b, 0xe9, 0xfd)
_drac_fg = (0xf8, 0xf8, 0xf2)
_drac_green = (0x50, 0xfa, 0x7b)
_drac_orange = (0xff, 0xb8, 0x6c)
_drac_pink = (0xff, 0x79, 0xc6)
_drac_purple = (0xbd, 0x93, 0xf9)
_drac_red = (0xff, 0x55, 0x55)
_drac_yellow = (0xf1, 0xfa, 0x8c)


@dataclass(frozen=True)
class Dracula(HelpExtraTheme):
    """Dracula by Zeno Rocha.

    High-contrast dark theme with vivid neon accents.
    """

    invoked_command: IStyle = Style(fg=_drac_fg, bold=True)
    heading: IStyle = Style(fg=_drac_pink, bold=True, underline=True)
    constraint: IStyle = Style(fg=_drac_pink)
    col1: IStyle = identity
    alias: IStyle = Style(fg=_drac_cyan)
    alias_secondary: IStyle = Style(fg=_drac_cyan, dim=True)
    # Log levels.
    critical: IStyle = Style(fg=_drac_red, bold=True)
    error: IStyle = Style(fg=_drac_red)
    warning: IStyle = Style(fg=_drac_orange)
    info: IStyle = identity
    debug: IStyle = Style(fg=_drac_comment)
    # Click Extra slots.
    option: IStyle = Style(fg=_drac_purple)
    subcommand: IStyle = Style(fg=_drac_purple)
    choice: IStyle = Style(fg=_drac_pink)
    metavar: IStyle = Style(fg=_drac_purple, dim=True)
    bracket: IStyle = Style(fg=_drac_comment)
    envvar: IStyle = Style(fg=_drac_orange, dim=True)
    default: IStyle = Style(fg=_drac_green, dim=True, italic=True)
    range_label: IStyle = Style(fg=_drac_purple, dim=True)
    required: IStyle = Style(fg=_drac_red, dim=True)
    argument: IStyle = Style(fg=_drac_purple)
    deprecated: IStyle = Style(fg=_drac_orange, bold=True)
    search: IStyle = Style(fg=_drac_yellow, bold=True)
    success: IStyle = Style(fg=_drac_green)
    subheading: IStyle = Style(fg=_drac_cyan)


# --- Light by Click Extra ----------------------------------------------------


@dataclass(frozen=True)
class Light(HelpExtraTheme):
    """Theme tuned for terminals with a light/white background.

    Mirrors :class:`Dark` but swaps the palette for one that stays legible on a
    white background: bright variants (which most terminals render as washed-out
    tints) are replaced by their standard counterparts, ``bright_white`` becomes
    ``black``, and cyan accents become ``blue`` since cyan on white is hard to
    read.
    """

    invoked_command: IStyle = BLACK_BOLD
    heading: IStyle = BLUE_HEADING
    constraint: IStyle = MAGENTA
    col1: IStyle = identity
    alias: IStyle = BLUE
    alias_secondary: IStyle = BLUE_DIM
    # Log levels: bright variants and yellow read poorly on white, so swap them.
    critical: IStyle = RED_BOLD
    error: IStyle = RED
    warning: IStyle = MAGENTA
    info: IStyle = identity
    debug: IStyle = BLUE_DIM
    # Click Extra slots: cyan on white is hard to read, so blue takes its place.
    option: IStyle = BLUE
    subcommand: IStyle = BLUE
    choice: IStyle = MAGENTA
    metavar: IStyle = BLUE_DIM
    bracket: IStyle = DIM
    envvar: IStyle = MAGENTA_DIM
    default: IStyle = GREEN_DIM_ITALIC
    range_label: IStyle = BLUE_DIM
    required: IStyle = RED_DIM
    argument: IStyle = BLUE
    deprecated: IStyle = RED_BOLD
    search: IStyle = GREEN_BOLD
    success: IStyle = GREEN
    # Non-canonical Click Extra slots.
    subheading: IStyle = BLUE_DIM


# --- Monokai by Wimer Hazenberg ----------------------------------------------
# Palette: https://monokai.pro/

_mono_comment = (0x75, 0x71, 0x5e)
_mono_cyan = (0x66, 0xd9, 0xef)
_mono_fg = (0xf8, 0xf8, 0xf2)
_mono_green = (0xa6, 0xe2, 0x2e)
_mono_orange = (0xfd, 0x97, 0x1f)
_mono_pink = (0xf9, 0x26, 0x72)
_mono_purple = (0xae, 0x81, 0xff)
_mono_yellow = (0xe6, 0xdb, 0x74)


@dataclass(frozen=True)
class Monokai(HelpExtraTheme):
    """Monokai by Wimer Hazenberg.

    Classic dark theme with high-saturation magenta and lime accents.
    """

    invoked_command: IStyle = Style(fg=_mono_fg, bold=True)
    heading: IStyle = Style(fg=_mono_green, bold=True, underline=True)
    constraint: IStyle = Style(fg=_mono_purple)
    col1: IStyle = identity
    alias: IStyle = Style(fg=_mono_green)
    alias_secondary: IStyle = Style(fg=_mono_green, dim=True)
    # Log levels.
    critical: IStyle = Style(fg=_mono_pink, bold=True)
    error: IStyle = Style(fg=_mono_pink)
    warning: IStyle = Style(fg=_mono_orange)
    info: IStyle = identity
    debug: IStyle = Style(fg=_mono_comment)
    # Click Extra slots.
    option: IStyle = Style(fg=_mono_cyan)
    subcommand: IStyle = Style(fg=_mono_cyan)
    choice: IStyle = Style(fg=_mono_purple)
    metavar: IStyle = Style(fg=_mono_cyan, dim=True)
    bracket: IStyle = Style(fg=_mono_comment)
    envvar: IStyle = Style(fg=_mono_orange, dim=True)
    default: IStyle = Style(fg=_mono_yellow, dim=True, italic=True)
    range_label: IStyle = Style(fg=_mono_cyan, dim=True)
    required: IStyle = Style(fg=_mono_pink, dim=True)
    argument: IStyle = Style(fg=_mono_cyan)
    deprecated: IStyle = Style(fg=_mono_orange, bold=True)
    search: IStyle = Style(fg=_mono_yellow, bold=True)
    success: IStyle = Style(fg=_mono_green)
    subheading: IStyle = Style(fg=_mono_green)


# --- Nord by Arctic Ice Studio -----------------------------------------------
# Palette: https://www.nordtheme.com/docs/colors-and-palettes

_nord_comment = (0x4c, 0x56, 0x6a)  # nord3: polar night
_nord_fg = (0xec, 0xef, 0xf4)  # nord6: snow storm
_nord_frost_blue = (0x81, 0xa1, 0xc1)  # nord9
_nord_frost_blue_dark = (0x5e, 0x81, 0xac)  # nord10
_nord_frost_blue_light = (0x88, 0xc0, 0xd0)  # nord8
_nord_frost_cyan = (0x8f, 0xbc, 0xbb)  # nord7
_nord_green = (0xa3, 0xbe, 0x8c)  # nord14
_nord_orange = (0xd0, 0x87, 0x70)  # nord12
_nord_purple = (0xb4, 0x8e, 0xad)  # nord15
_nord_red = (0xbf, 0x61, 0x6a)  # nord11: aurora
_nord_yellow = (0xeb, 0xcb, 0x8b)  # nord13


@dataclass(frozen=True)
class Nord(HelpExtraTheme):
    """Nord by Arctic Ice Studio.

    Cool-toned dark theme built around frost-blue and aurora accents.
    """

    invoked_command: IStyle = Style(fg=_nord_fg, bold=True)
    heading: IStyle = Style(fg=_nord_frost_blue_dark, bold=True, underline=True)
    constraint: IStyle = Style(fg=_nord_purple)
    col1: IStyle = identity
    alias: IStyle = Style(fg=_nord_frost_cyan)
    alias_secondary: IStyle = Style(fg=_nord_frost_cyan, dim=True)
    # Log levels.
    critical: IStyle = Style(fg=_nord_red, bold=True)
    error: IStyle = Style(fg=_nord_red)
    warning: IStyle = Style(fg=_nord_orange)
    info: IStyle = identity
    debug: IStyle = Style(fg=_nord_comment)
    # Click Extra slots.
    option: IStyle = Style(fg=_nord_frost_blue)
    subcommand: IStyle = Style(fg=_nord_frost_blue)
    choice: IStyle = Style(fg=_nord_purple)
    metavar: IStyle = Style(fg=_nord_frost_blue, dim=True)
    bracket: IStyle = Style(fg=_nord_comment)
    envvar: IStyle = Style(fg=_nord_orange, dim=True)
    default: IStyle = Style(fg=_nord_green, dim=True, italic=True)
    range_label: IStyle = Style(fg=_nord_frost_blue, dim=True)
    required: IStyle = Style(fg=_nord_red, dim=True)
    argument: IStyle = Style(fg=_nord_frost_blue)
    deprecated: IStyle = Style(fg=_nord_orange, bold=True)
    search: IStyle = Style(fg=_nord_yellow, bold=True)
    success: IStyle = Style(fg=_nord_green)
    subheading: IStyle = Style(fg=_nord_frost_blue_light)


# --- Solarized Dark by Ethan Schoonover --------------------------------------
# Palette: https://ethanschoonover.com/solarized/

_sol_blue = (0x26, 0x8b, 0xd2)
_sol_comment = (0x58, 0x6e, 0x75)  # base01
_sol_cyan = (0x2a, 0xa1, 0x98)
_sol_emph = (0xee, 0xe8, 0xd5)  # base2: emphasized foreground
_sol_green = (0x85, 0x99, 0x00)
_sol_magenta = (0xd3, 0x36, 0x82)
_sol_orange = (0xcb, 0x4b, 0x16)
_sol_red = (0xdc, 0x32, 0x2f)
_sol_violet = (0x6c, 0x71, 0xc4)
_sol_yellow = (0xb5, 0x89, 0x00)


@dataclass(frozen=True)
class SolarizedDark(HelpExtraTheme):
    """Solarized Dark by Ethan Schoonover.

    Warm-toned dark theme with selective accent contrast.
    """

    invoked_command: IStyle = Style(fg=_sol_emph, bold=True)
    heading: IStyle = Style(fg=_sol_blue, bold=True, underline=True)
    constraint: IStyle = Style(fg=_sol_violet)
    col1: IStyle = identity
    alias: IStyle = Style(fg=_sol_cyan)
    alias_secondary: IStyle = Style(fg=_sol_cyan, dim=True)
    # Log levels.
    critical: IStyle = Style(fg=_sol_red, bold=True)
    error: IStyle = Style(fg=_sol_red)
    warning: IStyle = Style(fg=_sol_yellow)
    info: IStyle = identity
    debug: IStyle = Style(fg=_sol_comment)
    # Click Extra slots.
    option: IStyle = Style(fg=_sol_blue)
    subcommand: IStyle = Style(fg=_sol_blue)
    choice: IStyle = Style(fg=_sol_violet)
    metavar: IStyle = Style(fg=_sol_blue, dim=True)
    bracket: IStyle = Style(fg=_sol_comment)
    envvar: IStyle = Style(fg=_sol_orange, dim=True)
    default: IStyle = Style(fg=_sol_green, dim=True, italic=True)
    range_label: IStyle = Style(fg=_sol_blue, dim=True)
    required: IStyle = Style(fg=_sol_red, dim=True)
    argument: IStyle = Style(fg=_sol_blue)
    deprecated: IStyle = Style(fg=_sol_magenta, bold=True)
    search: IStyle = Style(fg=_sol_yellow, bold=True)
    success: IStyle = Style(fg=_sol_green)
    subheading: IStyle = Style(fg=_sol_cyan)


# --- Cached singleton instances ---------------------------------------------
#
# Each theme class instantiates with its own field defaults, so calling it
# with no arguments gives you the canonical palette. These constants are the
# convenient public surface; subclassing the corresponding class is the
# extension surface.

DARK = Dark()
DRACULA = Dracula()
LIGHT = Light()
MONOKAI = Monokai()
NORD = Nord()
SOLARIZED_DARK = SolarizedDark()


BUILTIN_THEMES: dict[str, HelpExtraTheme] = {
    "dark": DARK,
    "dracula": DRACULA,
    "light": LIGHT,
    "monokai": MONOKAI,
    "nord": NORD,
    "solarized_dark": SOLARIZED_DARK,
}
"""Mapping of built-in theme names to their cached :class:`HelpExtraTheme` instances.

Seeded into :data:`click_extra.theme.theme_registry` at module load time.
Adding a new built-in theme is a one-file edit here: declare a
:class:`HelpExtraTheme` subclass with the palette as field defaults,
instantiate it as an UPPER_CASE constant, and add the constant to this dict.
"""
