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


@dataclass(frozen=True)
class Dracula(HelpExtraTheme):
    """Dracula by Zeno Rocha.

    High-contrast dark theme with vivid neon accents.
    """

    invoked_command: IStyle = Style(fg="#f8f8f2", bold=True)
    heading: IStyle = Style(fg="#ff79c6", bold=True, underline=True)
    constraint: IStyle = Style(fg="#ff79c6")
    col1: IStyle = identity
    alias: IStyle = Style(fg="#8be9fd")
    alias_secondary: IStyle = Style(fg="#8be9fd", dim=True)
    # Log levels.
    critical: IStyle = Style(fg="#ff5555", bold=True)
    error: IStyle = Style(fg="#ff5555")
    warning: IStyle = Style(fg="#ffb86c")
    info: IStyle = identity
    debug: IStyle = Style(fg="#6272a4")
    # Click Extra slots.
    option: IStyle = Style(fg="#bd93f9")
    subcommand: IStyle = Style(fg="#bd93f9")
    choice: IStyle = Style(fg="#ff79c6")
    metavar: IStyle = Style(fg="#bd93f9", dim=True)
    bracket: IStyle = Style(fg="#6272a4")
    envvar: IStyle = Style(fg="#ffb86c", dim=True)
    default: IStyle = Style(fg="#50fa7b", dim=True, italic=True)
    range_label: IStyle = Style(fg="#bd93f9", dim=True)
    required: IStyle = Style(fg="#ff5555", dim=True)
    argument: IStyle = Style(fg="#bd93f9")
    deprecated: IStyle = Style(fg="#ffb86c", bold=True)
    search: IStyle = Style(fg="#f1fa8c", bold=True)
    success: IStyle = Style(fg="#50fa7b")
    subheading: IStyle = Style(fg="#8be9fd")


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


@dataclass(frozen=True)
class Monokai(HelpExtraTheme):
    """Monokai by Wimer Hazenberg.

    Classic dark theme with high-saturation magenta and lime accents.
    """

    invoked_command: IStyle = Style(fg="#f8f8f2", bold=True)
    heading: IStyle = Style(fg="#a6e22e", bold=True, underline=True)
    constraint: IStyle = Style(fg="#ae81ff")
    col1: IStyle = identity
    alias: IStyle = Style(fg="#a6e22e")
    alias_secondary: IStyle = Style(fg="#a6e22e", dim=True)
    # Log levels.
    critical: IStyle = Style(fg="#f92672", bold=True)
    error: IStyle = Style(fg="#f92672")
    warning: IStyle = Style(fg="#fd971f")
    info: IStyle = identity
    debug: IStyle = Style(fg="#75715e")
    # Click Extra slots.
    option: IStyle = Style(fg="#66d9ef")
    subcommand: IStyle = Style(fg="#66d9ef")
    choice: IStyle = Style(fg="#ae81ff")
    metavar: IStyle = Style(fg="#66d9ef", dim=True)
    bracket: IStyle = Style(fg="#75715e")
    envvar: IStyle = Style(fg="#fd971f", dim=True)
    default: IStyle = Style(fg="#e6db74", dim=True, italic=True)
    range_label: IStyle = Style(fg="#66d9ef", dim=True)
    required: IStyle = Style(fg="#f92672", dim=True)
    argument: IStyle = Style(fg="#66d9ef")
    deprecated: IStyle = Style(fg="#fd971f", bold=True)
    search: IStyle = Style(fg="#e6db74", bold=True)
    success: IStyle = Style(fg="#a6e22e")
    subheading: IStyle = Style(fg="#a6e22e")


# --- Nord by Arctic Ice Studio -----------------------------------------------
# Palette: https://www.nordtheme.com/docs/colors-and-palettes


@dataclass(frozen=True)
class Nord(HelpExtraTheme):
    """Nord by Arctic Ice Studio.

    Cool-toned dark theme built around frost-blue and aurora accents.
    """

    invoked_command: IStyle = Style(fg="#eceff4", bold=True)  # nord6: snow storm
    heading: IStyle = Style(fg="#5e81ac", bold=True, underline=True)  # nord10
    constraint: IStyle = Style(fg="#b48ead")  # nord15
    col1: IStyle = identity
    alias: IStyle = Style(fg="#8fbcbb")  # nord7
    alias_secondary: IStyle = Style(fg="#8fbcbb", dim=True)
    # Log levels.
    critical: IStyle = Style(fg="#bf616a", bold=True)  # nord11: aurora
    error: IStyle = Style(fg="#bf616a")
    warning: IStyle = Style(fg="#d08770")  # nord12
    info: IStyle = identity
    debug: IStyle = Style(fg="#4c566a")  # nord3: polar night
    # Click Extra slots.
    option: IStyle = Style(fg="#81a1c1")  # nord9
    subcommand: IStyle = Style(fg="#81a1c1")
    choice: IStyle = Style(fg="#b48ead")
    metavar: IStyle = Style(fg="#81a1c1", dim=True)
    bracket: IStyle = Style(fg="#4c566a")
    envvar: IStyle = Style(fg="#d08770", dim=True)
    default: IStyle = Style(fg="#a3be8c", dim=True, italic=True)  # nord14
    range_label: IStyle = Style(fg="#81a1c1", dim=True)
    required: IStyle = Style(fg="#bf616a", dim=True)
    argument: IStyle = Style(fg="#81a1c1")
    deprecated: IStyle = Style(fg="#d08770", bold=True)
    search: IStyle = Style(fg="#ebcb8b", bold=True)  # nord13
    success: IStyle = Style(fg="#a3be8c")
    subheading: IStyle = Style(fg="#88c0d0")  # nord8


# --- Solarized Dark by Ethan Schoonover --------------------------------------
# Palette: https://ethanschoonover.com/solarized/


@dataclass(frozen=True)
class SolarizedDark(HelpExtraTheme):
    """Solarized Dark by Ethan Schoonover.

    Warm-toned dark theme with selective accent contrast.
    """

    invoked_command: IStyle = Style(fg="#eee8d5", bold=True)  # base2: emphasized
    heading: IStyle = Style(fg="#268bd2", bold=True, underline=True)
    constraint: IStyle = Style(fg="#6c71c4")
    col1: IStyle = identity
    alias: IStyle = Style(fg="#2aa198")
    alias_secondary: IStyle = Style(fg="#2aa198", dim=True)
    # Log levels.
    critical: IStyle = Style(fg="#dc322f", bold=True)
    error: IStyle = Style(fg="#dc322f")
    warning: IStyle = Style(fg="#b58900")
    info: IStyle = identity
    debug: IStyle = Style(fg="#586e75")  # base01
    # Click Extra slots.
    option: IStyle = Style(fg="#268bd2")
    subcommand: IStyle = Style(fg="#268bd2")
    choice: IStyle = Style(fg="#6c71c4")
    metavar: IStyle = Style(fg="#268bd2", dim=True)
    bracket: IStyle = Style(fg="#586e75")
    envvar: IStyle = Style(fg="#cb4b16", dim=True)
    default: IStyle = Style(fg="#859900", dim=True, italic=True)
    range_label: IStyle = Style(fg="#268bd2", dim=True)
    required: IStyle = Style(fg="#dc322f", dim=True)
    argument: IStyle = Style(fg="#268bd2")
    deprecated: IStyle = Style(fg="#d33682", bold=True)
    search: IStyle = Style(fg="#b58900", bold=True)
    success: IStyle = Style(fg="#859900")
    subheading: IStyle = Style(fg="#2aa198")


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
