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
"""Draw terminal text as a static document: an SVG picture, HTML or ANSI.

- {mod}`click_extra.capture.screenshot` runs a command, captures its output and
  renders it.
- {mod}`click_extra.capture.recording` rebuilds the frames of an animation from
  the stream a command writes at a terminal.
- {mod}`click_extra.capture.snippet` colors a source file to render it the same
  way.
- {mod}`click_extra.capture.svg` and {mod}`click_extra.capture.html` are the two
  renderers.
- {mod}`click_extra.capture.presets` describes the window a capture is drawn in:
  the terminal presets, the chrome and its palettes.
"""
