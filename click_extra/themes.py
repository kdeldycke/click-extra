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

Each theme is a single :class:`~click_extra.theme.HelpExtraTheme` instance
declared at module level. Adding a new theme means adding one more constant
here and registering it in :data:`BUILTIN_THEMES`: no factory function or
subclass needed. The :mod:`click_extra.theme` module imports
:data:`BUILTIN_THEMES` at the end of its own load to seed
:data:`~click_extra.theme.theme_registry`.

Third-party packages can grow the registry at runtime via
:func:`click_extra.theme.register_theme`.

Style constants below are named after their visual properties (color +
attributes), not by what they are used for: that lets the same constant be
reused across multiple theme slots and across multiple themes.
"""

from __future__ import annotations

from cloup._util import identity
from cloup.styling import Color

from . import Style
from .theme import HelpExtraTheme

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


# --- Themes -------------------------------------------------------------------

DARK = HelpExtraTheme(
    invoked_command=BRIGHT_WHITE,
    heading=BRIGHT_BLUE_HEADING,
    constraint=MAGENTA,
    # Neutralize Cloup's col1: it interferes with our finer per-token styling.
    col1=identity,
    alias=CYAN,
    alias_secondary=CYAN_DIM,
    # Log levels.
    critical=RED_BOLD,
    error=RED,
    warning=YELLOW,
    info=identity,  # INFO is the default level: no styling.
    debug=BLUE,
    # Click Extra slots.
    option=CYAN,
    subcommand=CYAN,
    choice=MAGENTA,
    metavar=CYAN_DIM,
    bracket=DIM,
    envvar=YELLOW_DIM,
    default=GREEN_DIM_ITALIC,
    range_label=CYAN_DIM,
    required=RED_DIM,
    argument=CYAN,
    deprecated=BRIGHT_YELLOW_BOLD,
    search=GREEN_BOLD,
    success=GREEN,
    # Non-canonical Click Extra slots.
    subheading=BLUE,
)
"""Theme tuned for terminals with a dark background.

Used as the process-wide :data:`~click_extra.theme.default_theme`.
"""


LIGHT = HelpExtraTheme(
    invoked_command=BLACK_BOLD,
    heading=BLUE_HEADING,
    constraint=MAGENTA,
    col1=identity,
    alias=BLUE,
    alias_secondary=BLUE_DIM,
    # Log levels: bright variants and yellow read poorly on white, so swap them.
    critical=RED_BOLD,
    error=RED,
    warning=MAGENTA,
    info=identity,
    debug=BLUE_DIM,
    # Click Extra slots: cyan on white is hard to read, so blue takes its place.
    option=BLUE,
    subcommand=BLUE,
    choice=MAGENTA,
    metavar=BLUE_DIM,
    bracket=DIM,
    envvar=MAGENTA_DIM,
    default=GREEN_DIM_ITALIC,
    range_label=BLUE_DIM,
    required=RED_DIM,
    argument=BLUE,
    deprecated=RED_BOLD,
    search=GREEN_BOLD,
    success=GREEN,
    # Non-canonical Click Extra slots.
    subheading=BLUE_DIM,
)
"""Theme tuned for terminals with a light/white background.

Mirrors :data:`DARK` but swaps the palette for one that stays legible on a
white background: bright variants (which most terminals render as washed-out
tints) are replaced by their standard counterparts, ``bright_white`` becomes
``black``, and cyan accents become ``blue`` since cyan on white is hard to read.
"""


BUILTIN_THEMES: dict[str, HelpExtraTheme] = {
    "dark": DARK,
    "light": LIGHT,
}
"""Mapping of built-in theme names to their :class:`HelpExtraTheme` instances.

Seeded into :data:`click_extra.theme.theme_registry` at module load time.
Adding a new built-in theme is a two-step edit in this file: declare the
``HelpExtraTheme`` instance, then add it to this dict.
"""
