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
"""Deprecated alias of {mod}`click_extra.command_doc`.

The module was named after the one format it could render. It now extracts a
command once, into a {class}`~click_extra.command_doc.CommandDoc`, and renders
that model as a man page, Markdown, JSON or a Carapace spec, so it is named
after the model rather than after one of its outputs.

Importing this module emits a {exc}`DeprecationWarning` and forwards every
public symbol. It is scheduled for removal in the release recorded in
{data}`~click_extra._deprecated.REMOVAL_VERSION`.
"""

from __future__ import annotations

import warnings

from ._deprecated import deprecation_message
from .command_doc import (
    CLICK_EXTRA_URL,
    DEFAULT_EXIT_STATUS,
    HELP_FORMATS,
    INLINE_LITERAL_RE,
    INSTALLABLE_FORMATS,
    MAN_FORMATTERS,
    MAN_INSTALL_DIR,
    MAN_SECTION,
    OVERSTRIKE_RE,
    CommandDoc,
    CommandDoc as ManPage,
    DocOptionGroup,
    DocOptionGroup as ManOptionGroup,
    DocOptionItem,
    DocOptionItem as ManOptionItem,
    HelpFormatOption,
    ManOption,
    extract_command_doc,
    extract_command_doc as extract_manpage,
    format_manpage,
    install_manpages,
    iter_command_contexts,
    iter_inline_literals,
    normalize_examples,
    read_manpage,
    render_help,
    render_manpage,
    render_manpages,
    write_manpages,
)

warnings.warn(
    deprecation_message("click_extra.man_page", "click_extra.command_doc"),
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "CLICK_EXTRA_URL",
    "DEFAULT_EXIT_STATUS",
    "HELP_FORMATS",
    "INLINE_LITERAL_RE",
    "INSTALLABLE_FORMATS",
    "MAN_FORMATTERS",
    "MAN_INSTALL_DIR",
    "MAN_SECTION",
    "OVERSTRIKE_RE",
    "CommandDoc",
    "DocOptionGroup",
    "DocOptionItem",
    "HelpFormatOption",
    "ManOption",
    "ManOptionGroup",
    "ManOptionItem",
    "ManPage",
    "extract_command_doc",
    "extract_manpage",
    "format_manpage",
    "install_manpages",
    "iter_command_contexts",
    "iter_inline_literals",
    "normalize_examples",
    "read_manpage",
    "render_help",
    "render_manpage",
    "render_manpages",
    "write_manpages",
]
