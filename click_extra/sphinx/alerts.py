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
"""Utilities to convert GitHub alerts into MyST admonitions for Sphinx."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

from sphinx.errors import ConfigError

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx


GITHUB_ALERT_PATTERN = re.compile(
    r"^(\s*)>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$"
)
"""Regex pattern to match GitHub alerts opening lines.

.. seealso::
    - GitHub documentation for `alerts syntax
    <https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#alerts>`_.
    - Announcement for `alert support starting 2023-12-14
    <https://github.blog/changelog/2023-12-14-new-markdown-extension-alerts-provide-distinctive-styling-for-significant-content/>`_.
"""

GITHUB_ALERT_CONTENT_PATTERN = re.compile(r"^(\s*)>(.*)$")
"""Regex pattern to match GitHub alert content lines."""

CODE_FENCE_PATTERN = re.compile(r"^(\s*)(`{3,}|~{3,})")
"""Regex pattern to match code fence opening/closing lines."""

INDENTED_CODE_BLOCK_PATTERN = re.compile(r"^( {4}|\t)")
"""Regex pattern to match indented code block lines (4 spaces or 1 tab)."""


@cache
def check_colon_fence(app: Sphinx) -> None:
    """Check that `colon_fence support
    <https://myst-parser.readthedocs.io/en/latest/syntax/optional.html#code-fences-using-colons>`_
    is enabled for MyST.

    :raises ConfigError: If ``colon_fence`` is not in ``myst_enable_extensions``.
    """
    myst_extensions = getattr(app.config, "myst_enable_extensions", [])
    if "colon_fence" not in myst_extensions:
        raise ConfigError(
            "GitHub alerts conversion requires 'colon_fence' in "
            "myst_enable_extensions. Add it to your conf.py:\n"
            "    myst_enable_extensions = [..., 'colon_fence']"
        )


@dataclass
class AlertParserState:
    """State machine for parsing GitHub alerts."""

    in_alert: bool = False
    in_code_block: bool = False
    code_fence_char: str = ""
    code_fence_len: int = 0
    code_fence_indent: str = ""
    alert_indent: str = ""
    prev_line_blank: bool = True
    modified: bool = False

    def reset_code_fence(self) -> None:
        self.in_code_block = False
        self.code_fence_char = ""
        self.code_fence_len = 0
        self.code_fence_indent = ""

    def enter_code_fence(self, char: str, length: int, indent: str) -> None:
        self.in_code_block = True
        self.code_fence_char = char
        self.code_fence_len = length
        self.code_fence_indent = indent

    def handle_fence(
        self, fence_char: str, fence_len: int, fence_indent: str, line: str
    ) -> bool:
        """Handle fence matching. Returns True if fence was processed."""
        if not self.in_code_block:
            self.enter_code_fence(fence_char, fence_len, fence_indent)
            return True
        elif (
            fence_char == self.code_fence_char
            and fence_len >= self.code_fence_len
            and fence_indent == self.code_fence_indent
            and line.strip() == fence_char * fence_len
        ):
            self.reset_code_fence()
            return True
        return False


def replace_github_alerts(text: str) -> str | None:
    """Transform GitHub alerts into MyST admonitions.

    Identify GitHub alerts in the provided ``text`` and transform them into
    colon-fenced ``:::`` MyST admonitions.

    Code blocks (fenced with ``` or ``~~~``, or indented with 4 spaces/tab) are
    detected and their content is preserved unchanged.

    Returns ``None`` if no transformation was applied, else returns the transformed
    text.
    """
    lines = text.split("\n")
    result = []
    state = AlertParserState()

    for line in lines:
        # Check for code fence boundaries.
        fence_match = CODE_FENCE_PATTERN.match(line)
        if fence_match:
            fence_indent = fence_match.group(1)
            fence_chars = fence_match.group(2)
            fence_char = fence_chars[0]
            fence_len = len(fence_chars)

            if state.handle_fence(fence_char, fence_len, fence_indent, line):
                result.append(line)
                continue

        if state.in_code_block:
            result.append(line)
            continue

        if state.prev_line_blank and INDENTED_CODE_BLOCK_PATTERN.match(line):
            result.append(line)
            state.prev_line_blank = False
            continue

        is_blank = line.strip() == ""

        # Only check for new alert if we're not already inside one
        if not state.in_alert:
            match = GITHUB_ALERT_PATTERN.match(line)
            if match:
                state.alert_indent, alert_type = match.groups()
                result.append(f"{state.alert_indent}:::{{{alert_type.lower()}}}")
                state.in_alert = True
                state.modified = True
                state.prev_line_blank = is_blank
                continue

        if state.in_alert:
            content_match = GITHUB_ALERT_CONTENT_PATTERN.match(line)
            if content_match:
                result.append(state.alert_indent + content_match.group(2).lstrip())
            else:
                result.append(f"{state.alert_indent}:::")
                result.append(line)
                state.in_alert = False
                state.prev_line_blank = is_blank
                continue
        else:
            result.append(line)

        state.prev_line_blank = is_blank

    if state.in_alert:
        result.append(":::")

    return "\n".join(result) if state.modified else None


def convert_github_alerts(app: Sphinx, *args) -> None:
    """Convert GitHub alerts into MyST admonitions in content blocks."""
    content = args[-1]

    for i, orig_content in enumerate(content):
        transformed = replace_github_alerts(orig_content)
        if transformed is not None:
            check_colon_fence(app)
            content[i] = transformed
