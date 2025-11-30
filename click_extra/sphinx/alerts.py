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

CODE_FENCE_PATTERN = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
"""Regex pattern to match code fence opening/closing lines."""

INDENTED_CODE_BLOCK_PATTERN = re.compile(r"^( {4}|\t)")
"""Regex pattern to match indented code block lines (4 spaces or 1 tab)."""

# Directives whose content should be preserved unchanged like code blocks
CODE_CONTENT_DIRECTIVES = frozenset({
    "code-block",
    "sourcecode",
    "literalinclude",
    "code",
})


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


def replace_github_alerts(text: str) -> str | None:
    """Transform GitHub alerts into MyST admonitions.

    Identify GitHub alerts in the provided ``text`` and transform them into
    colon-fenced ``:::`` MyST admonitions.

    Returns ``None`` if no transformation was applied, else returns the transformed
    text.
    """
    lines = text.split("\n")
    result = []
    # State tracking
    in_alert = False
    alert_indent = ""
    prev_line_blank = True
    modified = False
    # Fence stack: list of (char, length, indent, is_code_block)
    fence_stack: list[tuple[str, int, str, bool]] = []

    def in_code_block() -> bool:
        return any(f[3] for f in fence_stack)

    def process_fence(indent: str, chars: str, after: str) -> bool:
        """Process fence line. Returns True if it closes an existing fence."""
        char, length = chars[0], len(chars)

        # Check if this closes an existing fence
        for i in range(len(fence_stack) - 1, -1, -1):
            f_char, f_len, f_indent, _ = fence_stack[i]
            if (
                char == f_char
                and length >= f_len
                and indent == f_indent
                and not after.strip()
            ):
                fence_stack[:] = fence_stack[:i]
                return True

        # Opening a new fence - determine if it's a code block
        after_stripped = after.strip()
        is_code = True
        if after_stripped.startswith("{") and "}" in after_stripped:
            directive = after_stripped[1 : after_stripped.find("}")].split()[0]
            is_code = directive in CODE_CONTENT_DIRECTIVES

        fence_stack.append((char, length, indent, is_code))
        return False

    for line in lines:
        fence_match = CODE_FENCE_PATTERN.match(line)

        if fence_match:
            indent, chars, after = fence_match.groups()

            # Close alert if fence would close a parent fence
            if in_alert:
                for f_char, f_len, f_indent, _ in reversed(fence_stack):
                    if (
                        chars[0] == f_char
                        and len(chars) >= f_len
                        and indent == f_indent
                        and not after.strip()
                    ):
                        result.append(f"{alert_indent}:::")
                        in_alert = False
                        break

            process_fence(indent, chars, after)
            result.append(line)
            prev_line_blank = False
            continue

        if in_code_block():
            result.append(line)
            prev_line_blank = not line.strip()
            continue

        if prev_line_blank and INDENTED_CODE_BLOCK_PATTERN.match(line):
            result.append(line)
            prev_line_blank = False
            continue

        is_blank = not line.strip()

        # Check for new alert start
        if not in_alert:
            match = GITHUB_ALERT_PATTERN.match(line)
            if match:
                alert_indent, alert_type = match.groups()
                result.append(f"{alert_indent}:::{{{alert_type.lower()}}}")
                in_alert = True
                modified = True
                prev_line_blank = is_blank
                continue

        if in_alert:
            content_match = GITHUB_ALERT_CONTENT_PATTERN.match(line)
            if content_match:
                result.append(alert_indent + content_match.group(2).lstrip())
            else:
                result.append(f"{alert_indent}:::")
                result.append(line)
                in_alert = False
        else:
            result.append(line)

        prev_line_blank = is_blank

    if in_alert:
        result.append(":::")

    return "\n".join(result) if modified else None


def convert_github_alerts(app: Sphinx, *args) -> None:
    """Convert GitHub alerts into MyST admonitions in content blocks."""
    content = args[-1]
    for i, orig_content in enumerate(content):
        transformed = replace_github_alerts(orig_content)
        if transformed is not None:
            check_colon_fence(app)
            content[i] = transformed
