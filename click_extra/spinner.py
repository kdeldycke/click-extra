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
"""An indeterminate terminal spinner for long-running, blocking work.

Click ships :func:`click.progressbar`, but it is *determinate*: it needs a known
length or an iterable to advance through. Some work has no measurable progress:
a blocking subprocess, a network round-trip, a query whose duration is unknown.
For those, the only honest feedback is "something is happening".

:class:`Spinner` fills that gap. It animates a small frame sequence on a daemon
thread, so the caller can stay blocked in a single call (``communicate()``,
``urlopen()``, ...) while the spinner keeps turning:

.. code-block:: python

    from time import sleep

    from click_extra import Spinner

    with Spinner("Brewing tea"):
        sleep(5)  # A blocking call with no measurable progress.

.. caution::
    The spinner draws with carriage returns and ANSI control codes, so it is a
    no-op whenever its output stream is not a TTY (a pipe, a file, a captured
    test buffer, a CI log), unless ``enabled`` is forced. This keeps redirected
    output and machine-readable formats clean.
"""

from __future__ import annotations

import functools
import os
import sys
import threading
import time
from gettext import gettext as _
from typing import NamedTuple

import click

from . import context
from .parameters import ExtraOption
from .styling import Style

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from types import TracebackType
    from typing import IO, Any, Final

    from typing_extensions import Self


ASCII_SPINNER_FRAMES: Final = ("-", "\\", "|", "/")
"""Plain ASCII animation frames, for terminals or fonts lacking Unicode glyphs."""

SPINNER_FRAMES: Final = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
"""Default animation frames: the ubiquitous Braille-dots spinner.

Ten frames give a smooth rotation in any UTF-8 terminal. Fall back to
:data:`ASCII_SPINNER_FRAMES` where Braille glyphs are unavailable.
"""


class SpinnerPreset(NamedTuple):
    """A named spinner animation: its frames and the interval they look best at.

    The :data:`SPINNERS` catalog is ported from `cli-spinners
    <https://github.com/sindresorhus/cli-spinners>`_, with intervals converted
    from milliseconds to seconds. Pass one to :class:`Spinner` via its
    ``spinner`` argument.
    """

    frames: tuple[str, ...]
    """The animation frames, cycled in order."""

    interval: float
    """Seconds between two frames, tuned per spinner upstream."""


# Single-code-point animations are packed as ``tuple("frames")`` to stay
# one-liners; animations with multi-character frames keep an explicit tuple.
SPINNERS: Final = {
    "dots": SpinnerPreset(SPINNER_FRAMES, 0.08),
    "dots2": SpinnerPreset(tuple("⣾⣽⣻⢿⡿⣟⣯⣷"), 0.08),
    "dots3": SpinnerPreset(tuple("⠋⠙⠚⠞⠖⠦⠴⠲⠳⠓"), 0.08),
    "dots4": SpinnerPreset(tuple("⠄⠆⠇⠋⠙⠸⠰⠠⠰⠸⠙⠋⠇⠆"), 0.08),
    "dots5": SpinnerPreset(tuple("⠋⠙⠚⠒⠂⠂⠒⠲⠴⠦⠖⠒⠐⠐⠒⠓⠋"), 0.08),
    "dots6": SpinnerPreset(tuple("⠁⠉⠙⠚⠒⠂⠂⠒⠲⠴⠤⠄⠄⠤⠴⠲⠒⠂⠂⠒⠚⠙⠉⠁"), 0.08),
    "dots7": SpinnerPreset(tuple("⠈⠉⠋⠓⠒⠐⠐⠒⠖⠦⠤⠠⠠⠤⠦⠖⠒⠐⠐⠒⠓⠋⠉⠈"), 0.08),
    "dots8": SpinnerPreset(tuple("⠁⠁⠉⠙⠚⠒⠂⠂⠒⠲⠴⠤⠄⠄⠤⠠⠠⠤⠦⠖⠒⠐⠐⠒⠓⠋⠉⠈⠈"), 0.08),
    "dots9": SpinnerPreset(tuple("⢹⢺⢼⣸⣇⡧⡗⡏"), 0.08),
    "dots10": SpinnerPreset(tuple("⢄⢂⢁⡁⡈⡐⡠"), 0.08),
    "dots11": SpinnerPreset(tuple("⠁⠂⠄⡀⢀⠠⠐⠈"), 0.1),
    "dots12": SpinnerPreset(
        (
            "⢀⠀",
            "⡀⠀",
            "⠄⠀",
            "⢂⠀",
            "⡂⠀",
            "⠅⠀",
            "⢃⠀",
            "⡃⠀",
            "⠍⠀",
            "⢋⠀",
            "⡋⠀",
            "⠍⠁",
            "⢋⠁",
            "⡋⠁",
            "⠍⠉",
            "⠋⠉",
            "⠋⠉",
            "⠉⠙",
            "⠉⠙",
            "⠉⠩",
            "⠈⢙",
            "⠈⡙",
            "⢈⠩",
            "⡀⢙",
            "⠄⡙",
            "⢂⠩",
            "⡂⢘",
            "⠅⡘",
            "⢃⠨",
            "⡃⢐",
            "⠍⡐",
            "⢋⠠",
            "⡋⢀",
            "⠍⡁",
            "⢋⠁",
            "⡋⠁",
            "⠍⠉",
            "⠋⠉",
            "⠋⠉",
            "⠉⠙",
            "⠉⠙",
            "⠉⠩",
            "⠈⢙",
            "⠈⡙",
            "⠈⠩",
            "⠀⢙",
            "⠀⡙",
            "⠀⠩",
            "⠀⢘",
            "⠀⡘",
            "⠀⠨",
            "⠀⢐",
            "⠀⡐",
            "⠀⠠",
            "⠀⢀",
            "⠀⡀",
        ),
        0.08,
    ),
    "dots13": SpinnerPreset(tuple("⣼⣹⢻⠿⡟⣏⣧⣶"), 0.08),
    "dots14": SpinnerPreset(
        ("⠉⠉", "⠈⠙", "⠀⠹", "⠀⢸", "⠀⣰", "⢀⣠", "⣀⣀", "⣄⡀", "⣆⠀", "⡇⠀", "⠏⠀", "⠋⠁"), 0.08
    ),
    "dots8Bit": SpinnerPreset(
        tuple(
            "⠀⠁⠂⠃⠄⠅⠆⠇⡀⡁⡂⡃⡄⡅⡆⡇⠈⠉⠊⠋⠌⠍⠎⠏⡈⡉⡊⡋⡌⡍⡎⡏⠐⠑⠒⠓⠔⠕⠖⠗⡐⡑⡒⡓⡔⡕⡖⡗⠘⠙⠚⠛⠜⠝⠞⠟⡘⡙⡚⡛⡜⡝⡞⡟⠠⠡⠢⠣⠤⠥⠦⠧⡠⡡⡢⡣⡤⡥⡦⡧⠨⠩⠪⠫⠬⠭⠮⠯⡨⡩⡪⡫⡬⡭⡮⡯⠰⠱⠲⠳⠴⠵⠶⠷⡰⡱⡲⡳⡴⡵⡶⡷⠸⠹⠺⠻⠼⠽⠾⠿⡸⡹⡺⡻⡼⡽⡾⡿⢀⢁⢂⢃⢄⢅⢆⢇⣀⣁⣂⣃⣄⣅⣆⣇⢈⢉⢊⢋⢌⢍⢎⢏⣈⣉⣊⣋⣌⣍⣎⣏⢐⢑⢒⢓⢔⢕⢖⢗⣐⣑⣒⣓⣔⣕⣖⣗⢘⢙⢚⢛⢜⢝⢞⢟⣘⣙⣚⣛⣜⣝⣞⣟⢠⢡⢢⢣⢤⢥⢦⢧⣠⣡⣢⣣⣤⣥⣦⣧⢨⢩⢪⢫⢬⢭⢮⢯⣨⣩⣪⣫⣬⣭⣮⣯⢰⢱⢲⢳⢴⢵⢶⢷⣰⣱⣲⣳⣴⣵⣶⣷⢸⢹⢺⢻⢼⢽⢾⢿⣸⣹⣺⣻⣼⣽⣾⣿"
        ),
        0.08,
    ),
    "dotsCircle": SpinnerPreset(("⢎ ", "⠎⠁", "⠊⠑", "⠈⠱", " ⡱", "⢀⡰", "⢄⡠", "⢆⡀"), 0.08),
    "sand": SpinnerPreset(tuple("⠁⠂⠄⡀⡈⡐⡠⣀⣁⣂⣄⣌⣔⣤⣥⣦⣮⣶⣷⣿⡿⠿⢟⠟⡛⠛⠫⢋⠋⠍⡉⠉⠑⠡⢁"), 0.08),
    "line": SpinnerPreset(ASCII_SPINNER_FRAMES, 0.13),
    "line2": SpinnerPreset(tuple("⠂-–—–-"), 0.1),
    "rollingLine": SpinnerPreset(
        ("/  ", " - ", " \\ ", "  |", "  |", " \\ ", " - ", "/  "), 0.08
    ),
    "pipe": SpinnerPreset(tuple("┤┘┴└├┌┬┐"), 0.1),
    "simpleDots": SpinnerPreset((".  ", ".. ", "...", "   "), 0.4),
    "simpleDotsScrolling": SpinnerPreset(
        (".  ", ".. ", "...", " ..", "  .", "   "), 0.2
    ),
    "star": SpinnerPreset(tuple("✶✸✹✺✹✷"), 0.07),
    "star2": SpinnerPreset(tuple("+x*"), 0.08),
    "flip": SpinnerPreset(tuple("___-``'´-___"), 0.07),
    "hamburger": SpinnerPreset(tuple("☱☲☴"), 0.1),
    "growVertical": SpinnerPreset(tuple("▁▃▄▅▆▇▆▅▄▃"), 0.12),
    "growHorizontal": SpinnerPreset(tuple("▏▎▍▌▋▊▉▊▋▌▍▎"), 0.12),
    "balloon": SpinnerPreset(tuple(" .oO@* "), 0.14),
    "balloon2": SpinnerPreset(tuple(".oO°Oo."), 0.12),
    "noise": SpinnerPreset(tuple("▓▒░"), 0.1),
    "bounce": SpinnerPreset(tuple("⠁⠂⠄⠂"), 0.12),
    "boxBounce": SpinnerPreset(tuple("▖▘▝▗"), 0.12),
    "boxBounce2": SpinnerPreset(tuple("▌▀▐▄"), 0.1),
    "triangle": SpinnerPreset(tuple("◢◣◤◥"), 0.05),
    "binary": SpinnerPreset(
        (
            "010010",
            "001100",
            "100101",
            "111010",
            "111101",
            "010111",
            "101011",
            "111000",
            "110011",
            "110101",
        ),
        0.08,
    ),
    "arc": SpinnerPreset(tuple("◜◠◝◞◡◟"), 0.1),
    "circle": SpinnerPreset(tuple("◡⊙◠"), 0.12),
    "squareCorners": SpinnerPreset(tuple("◰◳◲◱"), 0.18),
    "circleQuarters": SpinnerPreset(tuple("◴◷◶◵"), 0.12),
    "circleHalves": SpinnerPreset(tuple("◐◓◑◒"), 0.05),
    "squish": SpinnerPreset(tuple("╫╪"), 0.1),
    "toggle": SpinnerPreset(tuple("⊶⊷"), 0.25),
    "toggle2": SpinnerPreset(tuple("▫▪"), 0.08),
    "toggle3": SpinnerPreset(tuple("□■"), 0.12),
    "toggle4": SpinnerPreset(tuple("■□▪▫"), 0.1),
    "toggle5": SpinnerPreset(tuple("▮▯"), 0.1),
    "toggle6": SpinnerPreset(tuple("ဝ၀"), 0.3),
    "toggle7": SpinnerPreset(tuple("⦾⦿"), 0.08),
    "toggle8": SpinnerPreset(tuple("◍◌"), 0.1),
    "toggle9": SpinnerPreset(tuple("◉◎"), 0.1),
    "toggle10": SpinnerPreset(tuple("㊂㊀㊁"), 0.1),
    "toggle11": SpinnerPreset(tuple("⧇⧆"), 0.05),
    "toggle12": SpinnerPreset(tuple("☗☖"), 0.12),
    "toggle13": SpinnerPreset(tuple("=*-"), 0.08),
    "arrow": SpinnerPreset(tuple("←↖↑↗→↘↓↙"), 0.1),
    "arrow2": SpinnerPreset(("⬆️ ", "↗️ ", "➡️ ", "↘️ ", "⬇️ ", "↙️ ", "⬅️ ", "↖️ "), 0.08),
    "arrow3": SpinnerPreset(
        ("▹▹▹▹▹", "▸▹▹▹▹", "▹▸▹▹▹", "▹▹▸▹▹", "▹▹▹▸▹", "▹▹▹▹▸"), 0.12
    ),
    "bouncingBar": SpinnerPreset(
        (
            "[    ]",
            "[=   ]",
            "[==  ]",
            "[=== ]",
            "[====]",
            "[ ===]",
            "[  ==]",
            "[   =]",
            "[    ]",
            "[   =]",
            "[  ==]",
            "[ ===]",
            "[====]",
            "[=== ]",
            "[==  ]",
            "[=   ]",
        ),
        0.08,
    ),
    "bouncingBall": SpinnerPreset(
        (
            "( ●    )",
            "(  ●   )",
            "(   ●  )",
            "(    ● )",
            "(     ●)",
            "(    ● )",
            "(   ●  )",
            "(  ●   )",
            "( ●    )",
            "(●     )",
        ),
        0.08,
    ),
    "smiley": SpinnerPreset(("😄 ", "😝 "), 0.2),
    "monkey": SpinnerPreset(("🙈 ", "🙈 ", "🙉 ", "🙊 "), 0.3),
    "hearts": SpinnerPreset(("💛 ", "💙 ", "💜 ", "💚 ", "💗 "), 0.1),
    "clock": SpinnerPreset(
        (
            "🕛 ",
            "🕐 ",
            "🕑 ",
            "🕒 ",
            "🕓 ",
            "🕔 ",
            "🕕 ",
            "🕖 ",
            "🕗 ",
            "🕘 ",
            "🕙 ",
            "🕚 ",
        ),
        0.1,
    ),
    "earth": SpinnerPreset(("🌍 ", "🌎 ", "🌏 "), 0.18),
    "material": SpinnerPreset(
        (
            "█▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁",
            "██▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁",
            "███▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁",
            "████▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁",
            "██████▁▁▁▁▁▁▁▁▁▁▁▁▁▁",
            "██████▁▁▁▁▁▁▁▁▁▁▁▁▁▁",
            "███████▁▁▁▁▁▁▁▁▁▁▁▁▁",
            "████████▁▁▁▁▁▁▁▁▁▁▁▁",
            "█████████▁▁▁▁▁▁▁▁▁▁▁",
            "█████████▁▁▁▁▁▁▁▁▁▁▁",
            "██████████▁▁▁▁▁▁▁▁▁▁",
            "███████████▁▁▁▁▁▁▁▁▁",
            "█████████████▁▁▁▁▁▁▁",
            "██████████████▁▁▁▁▁▁",
            "██████████████▁▁▁▁▁▁",
            "▁██████████████▁▁▁▁▁",
            "▁██████████████▁▁▁▁▁",
            "▁██████████████▁▁▁▁▁",
            "▁▁██████████████▁▁▁▁",
            "▁▁▁██████████████▁▁▁",
            "▁▁▁▁█████████████▁▁▁",
            "▁▁▁▁██████████████▁▁",
            "▁▁▁▁██████████████▁▁",
            "▁▁▁▁▁██████████████▁",
            "▁▁▁▁▁██████████████▁",
            "▁▁▁▁▁██████████████▁",
            "▁▁▁▁▁▁██████████████",
            "▁▁▁▁▁▁██████████████",
            "▁▁▁▁▁▁▁█████████████",
            "▁▁▁▁▁▁▁█████████████",
            "▁▁▁▁▁▁▁▁████████████",
            "▁▁▁▁▁▁▁▁████████████",
            "▁▁▁▁▁▁▁▁▁███████████",
            "▁▁▁▁▁▁▁▁▁███████████",
            "▁▁▁▁▁▁▁▁▁▁██████████",
            "▁▁▁▁▁▁▁▁▁▁██████████",
            "▁▁▁▁▁▁▁▁▁▁▁▁████████",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁███████",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁██████",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁█████",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁█████",
            "█▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁████",
            "██▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁███",
            "██▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁███",
            "███▁▁▁▁▁▁▁▁▁▁▁▁▁▁███",
            "████▁▁▁▁▁▁▁▁▁▁▁▁▁▁██",
            "█████▁▁▁▁▁▁▁▁▁▁▁▁▁▁█",
            "█████▁▁▁▁▁▁▁▁▁▁▁▁▁▁█",
            "██████▁▁▁▁▁▁▁▁▁▁▁▁▁█",
            "████████▁▁▁▁▁▁▁▁▁▁▁▁",
            "█████████▁▁▁▁▁▁▁▁▁▁▁",
            "█████████▁▁▁▁▁▁▁▁▁▁▁",
            "█████████▁▁▁▁▁▁▁▁▁▁▁",
            "█████████▁▁▁▁▁▁▁▁▁▁▁",
            "███████████▁▁▁▁▁▁▁▁▁",
            "████████████▁▁▁▁▁▁▁▁",
            "████████████▁▁▁▁▁▁▁▁",
            "██████████████▁▁▁▁▁▁",
            "██████████████▁▁▁▁▁▁",
            "▁██████████████▁▁▁▁▁",
            "▁██████████████▁▁▁▁▁",
            "▁▁▁█████████████▁▁▁▁",
            "▁▁▁▁▁████████████▁▁▁",
            "▁▁▁▁▁████████████▁▁▁",
            "▁▁▁▁▁▁███████████▁▁▁",
            "▁▁▁▁▁▁▁▁█████████▁▁▁",
            "▁▁▁▁▁▁▁▁█████████▁▁▁",
            "▁▁▁▁▁▁▁▁▁█████████▁▁",
            "▁▁▁▁▁▁▁▁▁█████████▁▁",
            "▁▁▁▁▁▁▁▁▁▁█████████▁",
            "▁▁▁▁▁▁▁▁▁▁▁████████▁",
            "▁▁▁▁▁▁▁▁▁▁▁████████▁",
            "▁▁▁▁▁▁▁▁▁▁▁▁███████▁",
            "▁▁▁▁▁▁▁▁▁▁▁▁███████▁",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁███████",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁███████",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁█████",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁████",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁████",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁████",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁███",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁███",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁██",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁██",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁██",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁█",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁█",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁█",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁",
            "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁",
        ),
        0.017,
    ),
    "moon": SpinnerPreset(
        ("🌑 ", "🌒 ", "🌓 ", "🌔 ", "🌕 ", "🌖 ", "🌗 ", "🌘 "), 0.08
    ),
    "runner": SpinnerPreset(("🚶 ", "🏃 "), 0.14),
    "pong": SpinnerPreset(
        (
            "▐⠂       ▌",
            "▐⠈       ▌",
            "▐ ⠂      ▌",
            "▐ ⠠      ▌",
            "▐  ⡀     ▌",
            "▐  ⠠     ▌",
            "▐   ⠂    ▌",
            "▐   ⠈    ▌",
            "▐    ⠂   ▌",
            "▐    ⠠   ▌",
            "▐     ⡀  ▌",
            "▐     ⠠  ▌",
            "▐      ⠂ ▌",
            "▐      ⠈ ▌",
            "▐       ⠂▌",
            "▐       ⠠▌",
            "▐       ⡀▌",
            "▐      ⠠ ▌",
            "▐      ⠂ ▌",
            "▐     ⠈  ▌",
            "▐     ⠂  ▌",
            "▐    ⠠   ▌",
            "▐    ⡀   ▌",
            "▐   ⠠    ▌",
            "▐   ⠂    ▌",
            "▐  ⠈     ▌",
            "▐  ⠂     ▌",
            "▐ ⠠      ▌",
            "▐ ⡀      ▌",
            "▐⠠       ▌",
        ),
        0.08,
    ),
    "shark": SpinnerPreset(
        (
            "▐|\\____________▌",
            "▐_|\\___________▌",
            "▐__|\\__________▌",
            "▐___|\\_________▌",
            "▐____|\\________▌",
            "▐_____|\\_______▌",
            "▐______|\\______▌",
            "▐_______|\\_____▌",
            "▐________|\\____▌",
            "▐_________|\\___▌",
            "▐__________|\\__▌",
            "▐___________|\\_▌",
            "▐____________|\\▌",
            "▐____________/|▌",
            "▐___________/|_▌",
            "▐__________/|__▌",
            "▐_________/|___▌",
            "▐________/|____▌",
            "▐_______/|_____▌",
            "▐______/|______▌",
            "▐_____/|_______▌",
            "▐____/|________▌",
            "▐___/|_________▌",
            "▐__/|__________▌",
            "▐_/|___________▌",
            "▐/|____________▌",
        ),
        0.12,
    ),
    "dqpb": SpinnerPreset(tuple("dqpb"), 0.1),
    "weather": SpinnerPreset(
        (
            "☀️ ",
            "☀️ ",
            "☀️ ",
            "🌤 ",
            "⛅️ ",
            "🌥 ",
            "☁️ ",
            "🌧 ",
            "🌨 ",
            "🌧 ",
            "🌨 ",
            "🌧 ",
            "🌨 ",
            "⛈ ",
            "🌨 ",
            "🌧 ",
            "🌨 ",
            "☁️ ",
            "🌥 ",
            "⛅️ ",
            "🌤 ",
            "☀️ ",
            "☀️ ",
        ),
        0.1,
    ),
    "christmas": SpinnerPreset(tuple("🌲🎄"), 0.4),
    "grenade": SpinnerPreset(
        (
            "،  ",
            "′  ",
            " ´ ",
            " ‾ ",
            "  ⸌",
            "  ⸊",
            "  |",
            "  ⁎",
            "  ⁕",
            " ෴ ",
            "  ⁓",
            "   ",
            "   ",
            "   ",
        ),
        0.08,
    ),
    "point": SpinnerPreset(("∙∙∙", "●∙∙", "∙●∙", "∙∙●", "∙∙∙"), 0.125),
    "layer": SpinnerPreset(tuple("-=≡"), 0.15),
    "betaWave": SpinnerPreset(
        ("ρββββββ", "βρβββββ", "ββρββββ", "βββρβββ", "ββββρββ", "βββββρβ", "ββββββρ"),
        0.08,
    ),
    "fingerDance": SpinnerPreset(("🤘 ", "🤟 ", "🖖 ", "✋ ", "🤚 ", "👆 "), 0.16),
    "fistBump": SpinnerPreset(
        (
            "🤜\u3000\u3000\u3000\u3000🤛 ",
            "🤜\u3000\u3000\u3000\u3000🤛 ",
            "🤜\u3000\u3000\u3000\u3000🤛 ",
            "\u3000🤜\u3000\u3000🤛\u3000 ",
            "\u3000\u3000🤜🤛\u3000\u3000 ",
            "\u3000🤜✨🤛\u3000\u3000 ",
            "🤜\u3000✨\u3000🤛\u3000 ",
        ),
        0.08,
    ),
    "soccerHeader": SpinnerPreset(
        (
            " 🧑⚽️       🧑 ",
            "🧑  ⚽️      🧑 ",
            "🧑   ⚽️     🧑 ",
            "🧑    ⚽️    🧑 ",
            "🧑     ⚽️   🧑 ",
            "🧑      ⚽️  🧑 ",
            "🧑       ⚽️🧑  ",
            "🧑      ⚽️  🧑 ",
            "🧑     ⚽️   🧑 ",
            "🧑    ⚽️    🧑 ",
            "🧑   ⚽️     🧑 ",
            "🧑  ⚽️      🧑 ",
        ),
        0.08,
    ),
    "mindblown": SpinnerPreset(
        (
            "😐 ",
            "😐 ",
            "😮 ",
            "😮 ",
            "😦 ",
            "😦 ",
            "😧 ",
            "😧 ",
            "🤯 ",
            "💥 ",
            "✨ ",
            "\u3000 ",
            "\u3000 ",
            "\u3000 ",
        ),
        0.16,
    ),
    "speaker": SpinnerPreset(("🔈 ", "🔉 ", "🔊 ", "🔉 "), 0.16),
    "orangePulse": SpinnerPreset(("🔸 ", "🔶 ", "🟠 ", "🟠 ", "🔶 "), 0.1),
    "bluePulse": SpinnerPreset(("🔹 ", "🔷 ", "🔵 ", "🔵 ", "🔷 "), 0.1),
    "orangeBluePulse": SpinnerPreset(
        ("🔸 ", "🔶 ", "🟠 ", "🟠 ", "🔶 ", "🔹 ", "🔷 ", "🔵 ", "🔵 ", "🔷 "), 0.1
    ),
    "timeTravel": SpinnerPreset(
        (
            "🕛 ",
            "🕚 ",
            "🕙 ",
            "🕘 ",
            "🕗 ",
            "🕖 ",
            "🕕 ",
            "🕔 ",
            "🕓 ",
            "🕒 ",
            "🕑 ",
            "🕐 ",
        ),
        0.1,
    ),
    "aesthetic": SpinnerPreset(
        (
            "▰▱▱▱▱▱▱",
            "▰▰▱▱▱▱▱",
            "▰▰▰▱▱▱▱",
            "▰▰▰▰▱▱▱",
            "▰▰▰▰▰▱▱",
            "▰▰▰▰▰▰▱",
            "▰▰▰▰▰▰▰",
            "▰▱▱▱▱▱▱",
        ),
        0.08,
    ),
    "dwarfFortress": SpinnerPreset(
        (
            " ██████£££  ",
            "☺██████£££  ",
            "☺██████£££  ",
            "☺▓█████£££  ",
            "☺▓█████£££  ",
            "☺▒█████£££  ",
            "☺▒█████£££  ",
            "☺░█████£££  ",
            "☺░█████£££  ",
            "☺ █████£££  ",
            " ☺█████£££  ",
            " ☺█████£££  ",
            " ☺▓████£££  ",
            " ☺▓████£££  ",
            " ☺▒████£££  ",
            " ☺▒████£££  ",
            " ☺░████£££  ",
            " ☺░████£££  ",
            " ☺ ████£££  ",
            "  ☺████£££  ",
            "  ☺████£££  ",
            "  ☺▓███£££  ",
            "  ☺▓███£££  ",
            "  ☺▒███£££  ",
            "  ☺▒███£££  ",
            "  ☺░███£££  ",
            "  ☺░███£££  ",
            "  ☺ ███£££  ",
            "   ☺███£££  ",
            "   ☺███£££  ",
            "   ☺▓██£££  ",
            "   ☺▓██£££  ",
            "   ☺▒██£££  ",
            "   ☺▒██£££  ",
            "   ☺░██£££  ",
            "   ☺░██£££  ",
            "   ☺ ██£££  ",
            "    ☺██£££  ",
            "    ☺██£££  ",
            "    ☺▓█£££  ",
            "    ☺▓█£££  ",
            "    ☺▒█£££  ",
            "    ☺▒█£££  ",
            "    ☺░█£££  ",
            "    ☺░█£££  ",
            "    ☺ █£££  ",
            "     ☺█£££  ",
            "     ☺█£££  ",
            "     ☺▓£££  ",
            "     ☺▓£££  ",
            "     ☺▒£££  ",
            "     ☺▒£££  ",
            "     ☺░£££  ",
            "     ☺░£££  ",
            "     ☺ £££  ",
            "      ☺£££  ",
            "      ☺£££  ",
            "      ☺▓££  ",
            "      ☺▓££  ",
            "      ☺▒££  ",
            "      ☺▒££  ",
            "      ☺░££  ",
            "      ☺░££  ",
            "      ☺ ££  ",
            "       ☺££  ",
            "       ☺££  ",
            "       ☺▓£  ",
            "       ☺▓£  ",
            "       ☺▒£  ",
            "       ☺▒£  ",
            "       ☺░£  ",
            "       ☺░£  ",
            "       ☺ £  ",
            "        ☺£  ",
            "        ☺£  ",
            "        ☺▓  ",
            "        ☺▓  ",
            "        ☺▒  ",
            "        ☺▒  ",
            "        ☺░  ",
            "        ☺░  ",
            "        ☺   ",
            "        ☺  &",
            "        ☺ ☼&",
            "       ☺ ☼ &",
            "       ☺☼  &",
            "      ☺☼  & ",
            "      ‼   & ",
            "     ☺   &  ",
            "    ‼    &  ",
            "   ☺    &   ",
            "  ‼     &   ",
            " ☺     &    ",
            "‼      &    ",
            "      &     ",
            "      &     ",
            "     &   ░  ",
            "     &   ▒  ",
            "    &    ▓  ",
            "    &    £  ",
            "   &    ░£  ",
            "   &    ▒£  ",
            "  &     ▓£  ",
            "  &     ££  ",
            " &     ░££  ",
            " &     ▒££  ",
            "&      ▓££  ",
            "&      £££  ",
            "      ░£££  ",
            "      ▒£££  ",
            "      ▓£££  ",
            "      █£££  ",
            "     ░█£££  ",
            "     ▒█£££  ",
            "     ▓█£££  ",
            "     ██£££  ",
            "    ░██£££  ",
            "    ▒██£££  ",
            "    ▓██£££  ",
            "    ███£££  ",
            "   ░███£££  ",
            "   ▒███£££  ",
            "   ▓███£££  ",
            "   ████£££  ",
            "  ░████£££  ",
            "  ▒████£££  ",
            "  ▓████£££  ",
            "  █████£££  ",
            " ░█████£££  ",
            " ▒█████£££  ",
            " ▓█████£££  ",
            " ██████£££  ",
            " ██████£££  ",
        ),
        0.08,
    ),
    "fish": SpinnerPreset(
        (
            "~~~~~~~~~~~~~~~~~~~~",
            "> ~~~~~~~~~~~~~~~~~~",
            "º> ~~~~~~~~~~~~~~~~~",
            "(º> ~~~~~~~~~~~~~~~~",
            "((º> ~~~~~~~~~~~~~~~",
            "<((º> ~~~~~~~~~~~~~~",
            "><((º> ~~~~~~~~~~~~~",
            " ><((º> ~~~~~~~~~~~~",
            "~ ><((º> ~~~~~~~~~~~",
            "~~ <>((º> ~~~~~~~~~~",
            "~~~ ><((º> ~~~~~~~~~",
            "~~~~ <>((º> ~~~~~~~~",
            "~~~~~ ><((º> ~~~~~~~",
            "~~~~~~ <>((º> ~~~~~~",
            "~~~~~~~ ><((º> ~~~~~",
            "~~~~~~~~ <>((º> ~~~~",
            "~~~~~~~~~ ><((º> ~~~",
            "~~~~~~~~~~ <>((º> ~~",
            "~~~~~~~~~~~ ><((º> ~",
            "~~~~~~~~~~~~ <>((º> ",
            "~~~~~~~~~~~~~ ><((º>",
            "~~~~~~~~~~~~~~ <>((º",
            "~~~~~~~~~~~~~~~ ><((",
            "~~~~~~~~~~~~~~~~ <>(",
            "~~~~~~~~~~~~~~~~~ ><",
            "~~~~~~~~~~~~~~~~~~ <",
            "~~~~~~~~~~~~~~~~~~~~",
        ),
        0.08,
    ),
}
"""Named spinner animations ported from cli-spinners, keyed by name.

Each value is a :class:`SpinnerPreset` bundling frames and a tuned interval.
Select one with :class:`Spinner`'s ``spinner`` argument::

    from click_extra import Spinner, SPINNERS

    with Spinner("Brewing tea", spinner=SPINNERS["moon"]):
        ...

Unlike the upstream ``\\b``-based renderers, :class:`Spinner` redraws the whole
line, so the multi-character animations (``bouncingBar``, ``pong``, ``shark``, …)
render correctly here.
"""


class Spinner:
    """A thread-animated, indeterminate progress spinner usable as a context
    manager.

    The animation runs on a background daemon thread, leaving the calling thread
    free to block on the actual work. Entering the context (or calling
    :meth:`start`) begins the animation; leaving it (or calling :meth:`stop`)
    halts the thread and erases the spinner line so it never lingers above the
    next output.

    .. note::
        A single :class:`Spinner` instance drives one animation at a time. mpm
        and similar tools run their subprocesses sequentially, so one shared
        instance whose :attr:`label` is reassigned between steps is enough; for
        concurrent work, use one instance per thread.
    """

    label: str
    """Text drawn after the spinner glyph.

    Reassign it at any time while the spinner runs to reflect the current step;
    the animation thread reads it afresh on every frame.
    """

    def __init__(
        self,
        label: str | Callable[..., Any] = "",
        *,
        frames: Sequence[str] | None = None,
        spinner: SpinnerPreset | None = None,
        reverse: bool = False,
        interval: float | None = None,
        delay: float = 0.0,
        style: Style | None = None,
        timer: bool = False,
        stream: IO[str] | None = None,
        enabled: bool | None = None,
        hide_cursor: bool = True,
        beep: bool = False,
    ) -> None:
        """Configure (but do not start) the spinner.

        :param label: text shown after the spinner glyph. As a special case, a
            bare ``@Spinner`` decorator passes the wrapped function here instead;
            it is detected and the label defaults to empty.
        :param frames: the animation frames, cycled in order. Defaults to
            :data:`SPINNER_FRAMES`, or the ``spinner`` preset's frames when given.
        :param spinner: a :class:`SpinnerPreset` from the :data:`SPINNERS` catalog
            (``spinner=SPINNERS["moon"]``), supplying both frames and a tuned
            interval. An explicit ``frames`` or ``interval`` still overrides it.
        :param reverse: cycle the frames backwards, spinning the animation the
            other way. Set it when the rotation runs counter to what you expect;
            it composes with any custom ``frames``.
        :param interval: seconds between two frames. Defaults to ``0.1``, or the
            ``spinner`` preset's interval when given.
        :param delay: seconds to wait before drawing the first frame. A non-zero
            delay keeps the spinner silent for calls that finish quickly, so it
            only surfaces once an operation is genuinely slow.
        :param style: a :class:`~click_extra.styling.Style` applied to the spinner
            glyph, label and timer (``Style(fg="cyan", bold=True)``). Color is
            decoupled from animation: ``--no-color`` / ``NO_COLOR`` strip it while
            the spinner keeps spinning (see :class:`ProgressOption`).
        :param timer: append the elapsed wall-clock time to the spinner, and to
            any final :meth:`ok` / :meth:`fail` line.
        :param stream: where to draw; defaults to :data:`sys.stderr` so the
            spinner never mixes into ``stdout`` data.
        :param enabled: force the spinner on or off. ``None`` (the default)
            auto-detects, animating only when ``stream`` is a TTY.
        :param hide_cursor: hide the text cursor while spinning and restore it on
            stop.
        :param beep: ring the terminal bell once when the spinner stops. It
            fires only when the spinner was active, so a disabled or redirected
            spinner stays silent.
        :raises ValueError: if ``style`` carries a color or attribute that
            cannot be rendered.
        """
        # Support a bare `@Spinner` decorator (no parentheses): the first
        # positional is then the wrapped function, not a text label. `@Spinner(…)`
        # and `with Spinner(…)` keep passing a string label as usual. A string is
        # never callable, so this never misfires on a real label.
        #
        # This is the same `callable(first_arg)` test as
        # `click_extra.decorators.allow_missing_parenthesis`, inlined here on
        # purpose: that helper wraps a decorator *factory function* and returns a
        # function, so it cannot wrap `Spinner` without replacing the class — and
        # `Spinner` must stay a class to double as a context manager and to support
        # ``isinstance()`` / subclassing. The bare-call hook therefore has to live
        # in ``__init__``, the one place the parenthesis-less form reaches.
        self._decorated: Callable[..., Any] | None = None
        if callable(label):
            self._decorated = label
            # Make the instance masquerade as the function it stands in for,
            # without overwriting our own attributes (`updated=()`).
            functools.update_wrapper(self, label, updated=())
            label = ""

        self.label = label
        # `spinner=` supplies frames and interval together; an explicit `frames=`
        # or `interval=` overrides the preset, and both fall back to the defaults.
        if frames is not None:
            self.frames = frames
        elif spinner is not None:
            self.frames = spinner.frames
        else:
            self.frames = SPINNER_FRAMES
        if interval is not None:
            self.interval = interval
        elif spinner is not None:
            self.interval = spinner.interval
        else:
            self.interval = 0.1
        self.reverse = reverse
        self.delay = delay
        self.style = style
        self.timer = timer
        self.stream = stream
        self.enabled = enabled
        self.hide_cursor = hide_cursor
        self.beep = beep

        # Validate the style once, so a bad color or attribute fails loudly here
        # instead of silently killing the draw thread (cloup builds and applies
        # the style lazily on first call, where the error would surface off-thread).
        if style is not None:
            try:
                style("")
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid spinner style: {error}") from error

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._drawn = False
        self._cursor_hidden = False
        self._color_enabled = False
        self._start_time: float | None = None
        self._stop_time: float | None = None

    def _resolve_stream(self) -> IO[str]:
        """Return the explicit ``stream``, or default to :data:`sys.stderr`.

        Resolved lazily so a stream swapped in after construction (as test
        harnesses do) is honored.
        """
        return self.stream if self.stream is not None else sys.stderr

    def _resolve_enabled(self, stream: IO[str]) -> bool:
        """Decide whether to animate, honoring an explicit ``enabled`` override.

        Auto-detection (``enabled=None``) animates only on an interactive terminal
        that can move the cursor. That rules out non-interactive streams (a pipe,
        file or captured buffer, which are not a TTY) and ``TERM=dumb`` /
        ``TERM=unknown`` terminals, whose lack of cursor control would smear a trail
        of frames down the screen instead of animating in place.
        """
        if self.enabled is not None:
            return self.enabled
        if os.environ.get("TERM", "").lower() in {"dumb", "unknown"}:
            return False
        isatty = getattr(stream, "isatty", None)
        return bool(isatty and isatty())

    def _resolve_color_enabled(self, stream: IO[str]) -> bool:
        """Decide whether to apply ANSI color, orthogonally to whether it animates.

        Color follows Click Extra's reconciled :attr:`ctx.color
        <click.Context.color>` when a command context is active, so ``--color`` /
        ``--no-color`` and the ``NO_COLOR`` / ``FORCE_COLOR`` family have already
        been honored. Outside a CLI it falls back to those two environment
        variables, then to TTY detection. This is independent of
        :meth:`_resolve_enabled`: a spinner can spin in plain text (a TTY under
        ``NO_COLOR``), which is exactly the decoupling :class:`ProgressOption`
        documents.
        """
        ctx = click.get_current_context(silent=True)
        if ctx is not None and ctx.color is not None:
            return ctx.color
        # Match ColorOption's enabling-wins reconciliation: FORCE_COLOR before
        # NO_COLOR, so the two agree when both are set outside a command context.
        if "FORCE_COLOR" in os.environ:
            return True
        if "NO_COLOR" in os.environ:
            return False
        isatty = getattr(stream, "isatty", None)
        return bool(isatty and isatty())

    def _style(self, text: str) -> str:
        """Apply the configured :class:`~click_extra.styling.Style`, or return bare.

        A no-op when no style was set or color is disabled, so the same call site
        produces colored output on a capable terminal and plain output under
        ``NO_COLOR`` / a pipe.
        """
        if self._color_enabled and self.style is not None:
            return self.style(text)
        return text

    @property
    def elapsed_time(self) -> float:
        """Seconds elapsed since :meth:`start`, frozen once :meth:`stop` is called.

        Returns ``0.0`` before the spinner has started.
        """
        if self._start_time is None:
            return 0.0
        end = self._stop_time if self._stop_time is not None else time.monotonic()
        return end - self._start_time

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        """Render a duration compactly: ``2.3s``, ``1:05``, then ``1:02:03``."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes, secs = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def start(self) -> None:
        """Begin animating on a background thread, unless the spinner is disabled.

        A disabled spinner (non-TTY stream, or ``enabled=False``) returns at once
        without spawning a thread or emitting anything (but still records the
        start time, so a later :meth:`ok` / :meth:`fail` can report a duration).
        """
        # Time the operation even when the spinner is silenced, and resolve color
        # here on the calling thread: the animation thread never sees the Click
        # context that ``_resolve_color_enabled`` reads.
        self._start_time = time.monotonic()
        self._stop_time = None
        stream = self._resolve_stream()
        self._color_enabled = self._resolve_color_enabled(stream)
        if not self._resolve_enabled(stream):
            return
        self._stop.clear()
        self._drawn = False
        self._cursor_hidden = False
        self._thread = threading.Thread(
            target=self._animate,
            args=(stream,),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Halt the animation and erase the spinner line.

        Idempotent and safe to call when the spinner never started. Restores the
        cursor and clears the line only if the animation actually drew to the
        terminal.
        """
        # Freeze the timer first, before the early return, so even a never-drawn
        # spinner reports the operation's duration through `elapsed_time`.
        self._stop_time = time.monotonic()
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join()
        self._thread = None

        # The animation thread has joined, so the draw lock is now free: take it
        # so a concurrent `echo()` from another thread cannot interleave with the
        # final cleanup. Joining before acquiring avoids deadlocking against the
        # lock-holding frame write.
        with self._lock:
            # Undo only what was actually emitted: erase the line if a frame was
            # drawn, and restore the cursor if it was hidden. Reaching this point
            # means the spinner was active, so an opt-in bell rings here too: a
            # disabled or redirected spinner returns above and stays silent.
            cleanup = ""
            if self._drawn:
                cleanup += "\r\x1b[K"
            if self._cursor_hidden:
                cleanup += "\x1b[?25h"
            if self.beep:
                cleanup += "\a"
            if cleanup:
                stream = self._resolve_stream()
                stream.write(cleanup)
                stream.flush()
                self._cursor_hidden = False

    def echo(self, message: str = "") -> None:
        """Print ``message`` on its own line above the running spinner.

        Click's :func:`click.progressbar` and a bare ``print`` both fight the
        animation: a frame drawn between the cursor returns and the text mangles
        the line. :meth:`echo` takes the same draw lock as the animation thread,
        erases the in-progress frame, writes ``message`` followed by a newline,
        and lets the next tick redraw the spinner underneath. It is safe to call
        from another thread while the spinner runs.

        Output goes to the spinner's own ``stream`` (``stderr`` by default), so
        results written to ``stdout`` never need it. When the spinner is not
        animating (disabled, or a non-TTY stream), it degrades to a plain write
        of ``message`` with no control codes.
        """
        stream = self._resolve_stream()
        with self._lock:
            # Erase the in-progress frame so the message starts at column 0.
            if self._drawn:
                stream.write("\r\x1b[K")
            stream.write(f"{message}\n")
            stream.flush()

    def ok(self, symbol: str | None = None, *, style: Style | None = None) -> None:
        """Stop the spinner and leave a persistent success line on screen.

        Where :meth:`stop` erases the spinner, :meth:`ok` replaces the final
        frame with ``symbol`` followed by the current label (and the elapsed time
        when ``timer`` is set), then keeps that line. ``symbol`` defaults to the
        themed success glyph :data:`~click_extra.theme.OK_GLYPH` (``✓``), painted
        with the active theme's ``success`` slot unless ``style`` overrides it.
        Color is stripped under ``--no-color`` / ``NO_COLOR``; the glyph stays.
        """
        self._finalize(symbol, style, success=True)

    def fail(self, symbol: str | None = None, *, style: Style | None = None) -> None:
        """Stop the spinner and leave a persistent failure line on screen.

        The failure counterpart of :meth:`ok`, defaulting to
        :data:`~click_extra.theme.KO_GLYPH` (``✘``) painted with the active
        theme's ``error`` slot.
        """
        self._finalize(symbol, style, success=False)

    def _finalize(
        self,
        symbol: str | None,
        style: Style | None,
        *,
        success: bool,
    ) -> None:
        """Stop the animation and write a kept ``{symbol} {label}`` final line.

        Resolves color on the calling thread, stops the spinner (which erases the
        live frame and restores the cursor), then writes the final line in its
        place. The glyph and its paint default to the active theme's success /
        error slots, so a finished spinner matches the rest of a themed CLI.
        Degrades to a plain line when color is disabled or the spinner was never
        shown, so the outcome is still recorded off a TTY.
        """
        # Lazy import to avoid a circular dependency with theme (as parameters.py
        # does); the active theme is resolved here, not frozen at construction.
        from .theme import KO_GLYPH, OK_GLYPH, get_current_theme

        glyph = symbol if symbol is not None else (OK_GLYPH if success else KO_GLYPH)
        if style is None:
            theme = get_current_theme()
            paint = theme.success if success else theme.error
        else:
            paint = style

        stream = self._resolve_stream()
        color_enabled = self._resolve_color_enabled(stream)
        self.stop()
        label = f" {self.label}" if self.label else ""
        clock = f" ({self._format_elapsed(self.elapsed_time)})" if self.timer else ""
        marker = paint(glyph) if color_enabled else glyph
        with self._lock:
            stream.write(f"{marker}{label}{clock}\n")
            stream.flush()

    def _animate(self, stream: IO[str]) -> None:
        """Frame loop run on the background thread.

        Waits ``delay`` before the first frame, then writes one frame every
        ``interval`` until :meth:`stop` is called. Every wait goes through the
        stop :class:`~threading.Event`, so the spinner reacts to ``stop()``
        immediately instead of sleeping out the current interval. Stream errors
        (a closed terminal) end the loop quietly rather than surfacing a
        traceback from the background thread.
        """
        # A call that finishes within `delay` never draws anything.
        if self._stop.wait(self.delay):
            return
        # Resolve the rotation direction once: `reverse` flips the frame order.
        frames = tuple(reversed(self.frames)) if self.reverse else self.frames
        try:
            if self.hide_cursor:
                stream.write("\x1b[?25l")
                self._cursor_hidden = True
                stream.flush()
            index = 0
            while not self._stop.is_set():
                frame = frames[index % len(frames)]
                label = f" {self.label}" if self.label else ""
                clock = ""
                if self.timer:
                    clock = f" ({self._format_elapsed(self.elapsed_time)})"
                content = self._style(f"{frame}{label}{clock}")
                # Hold the draw lock so a concurrent `echo()` cannot interleave
                # with a half-written frame. Return to the line start, then
                # clear to end-of-line so a shrinking label leaves no stale
                # characters behind.
                with self._lock:
                    stream.write(f"\r{content}\x1b[K")
                    stream.flush()
                    self._drawn = True
                index += 1
                if self._stop.wait(self.interval):
                    break
        except (OSError, ValueError):
            # The stream was closed or detached mid-spin; nothing left to draw.
            return

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Use the spinner as a decorator, with or without parentheses.

        ``@Spinner`` wraps a function directly; ``@Spinner("Loading", …)`` first
        configures the spinner, then wraps. Either way the function spins for the
        duration of every call and returns its result untouched. The one instance
        is shared across calls, which is fine for sequential use; give concurrent
        callers their own spinner.
        """
        # Bare `@Spinner`: the instance stood in for the function (captured at
        # construction), so calling it runs that function inside the context.
        if self._decorated is not None:
            with self:
                return self._decorated(*args, **kwargs)

        # `@Spinner(…)`: wrap the single function argument so each call spins.
        (func,) = args

        @functools.wraps(func)
        def wrapper(*call_args: Any, **call_kwargs: Any) -> Any:
            with self:
                return func(*call_args, **call_kwargs)

        return wrapper


class ProgressOption(ExtraOption):
    """A pre-configured ``--progress``/``--no-progress`` flag gating spinner display.

    Resolves to a single boolean published at
    :data:`ctx.meta[click_extra.context.PROGRESS] <click_extra.context.PROGRESS>`,
    which a CLI reads to decide whether to start a :class:`Spinner`. The default is
    ``True``; ``--accessible`` lowers it to ``False`` (via ``default_map``) so a
    screen reader is never handed a spinning glyph.

    .. note::
        Spinner display is intentionally **decoupled from color**, even though both
        emit ANSI. A spinner is an *interactivity* concern, not a color one: it is
        built from cursor-control codes (hide-cursor, carriage return, clear-line),
        which the `NO_COLOR standard <https://no-color.org>`_ explicitly does not
        govern -- it "only signals the user's intention regarding adding ANSI color
        to text output". So ``--no-color`` / ``NO_COLOR`` strip the spinner's colors
        but never hide it.

        This matches how the wider ecosystem treats the two axes as orthogonal:
        cargo, npm, pip, Rich, indicatif and ora all gate progress on the terminal
        (and a dedicated ``--progress``/``--quiet`` knob), while ``NO_COLOR`` only
        affects color. Rich uses ``TERM=dumb`` -- not ``NO_COLOR`` -- as the signal
        to drop cursor-moving features like progress bars.

        The spinner is therefore silenced by two things only, neither of them color:

        - **non-interactive output** -- a pipe, file, CI log, or ``TERM=dumb``
          terminal that cannot move the cursor (see :meth:`Spinner._resolve_enabled`);
        - **explicit intent** -- ``--no-progress`` or ``--accessible``.

    This option is eager. It no longer reads ``ctx.color``, so its position relative
    to :class:`~click_extra.colorize.ColorOption` is not load-bearing.
    """

    def set_progress(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Publish whether progress spinners may be shown.

        Stores the resolved ``--progress`` flag at
        :data:`~click_extra.context.PROGRESS`. Deliberately independent of color:
        see the :class:`ProgressOption` note for why a spinner is gated on
        interactivity (TTY / ``TERM=dumb``) and ``--accessible``, never on
        ``--no-color`` / ``NO_COLOR``.
        """
        context.set(ctx, context.PROGRESS, value)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=True,
        default=True,
        is_eager=True,
        expose_value=False,
        help=_(
            "Show a progress spinner during long operations. Disabled for "
            "non-interactive output (pipes, dumb terminals, CI) and by --accessible."
        ),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--progress/--no-progress",)

        kwargs.setdefault("callback", self.set_progress)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )
