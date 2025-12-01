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
"""Utilities to convert GitHub alerts into MyST admonitions for Sphinx.

.. seealso::
    - GitHub documentation for `alerts syntax
    <https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#alerts>`_.
    - Announcement for `alert support starting 2023-12-14
    <https://github.blog/changelog/2023-12-14-new-markdown-extension-alerts-provide-distinctive-styling-for-significant-content/>`_.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache

from sphinx.errors import ConfigError

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx


GITHUB_ALERT_PATTERN = re.compile(r"^\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$")
"""Regex pattern to match GitHub alert type declaration (without leading >)."""

QUOTE_PREFIX_PATTERN = re.compile(r"^(\s*)((?:>\s*)+)(.*)$")
"""Regex pattern to extract indent, quote markers, and content."""

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


@dataclass
class Alert:
    """Represents a GitHub alert being processed."""

    alert_type: str
    indent: str
    depth: int  # Quote nesting depth (number of > markers)
    has_nested: bool = False
    opening_line_index: int = 0


@dataclass
class FenceState:
    """Tracks code fence state."""

    char: str
    length: int
    indent: str
    is_code_block: bool


@dataclass
class ParserState:
    """Mutable state for the alert parser."""

    result: list[str] = field(default_factory=list)
    alert_stack: list[Alert] = field(default_factory=list)
    fence_stack: list[FenceState] = field(default_factory=list)
    prev_line_blank: bool = True
    modified: bool = False
    just_opened_fence_directive: bool = False

    def in_code_block(self) -> bool:
        """Check if currently inside a code block."""
        return any(f.is_code_block for f in self.fence_stack)

    def current_depth(self) -> int:
        """Get current alert nesting depth."""
        return self.alert_stack[-1].depth if self.alert_stack else 0


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


def count_quote_depth(line: str) -> tuple[str, int, str]:
    """Parse a line to extract indent, quote depth, and content.

    Returns:
        Tuple of (indent, depth, content) where depth is the number of > markers.
    """
    if match := QUOTE_PREFIX_PATTERN.match(line):
        indent, quotes, content = match.groups()
        return indent, quotes.count(">"), content
    return "", 0, line


def process_fence(state: ParserState, indent: str, chars: str, after: str) -> None:
    """Process a fence line, updating fence stack."""
    char, length = chars[0], len(chars)

    # Try to close existing fence
    if not after.strip():
        for i in range(len(state.fence_stack) - 1, -1, -1):
            fence = state.fence_stack[i]
            if char == fence.char and length >= fence.length and indent == fence.indent:
                del state.fence_stack[i:]
                state.just_opened_fence_directive = False
                return

    # Opening a new fence - determine if it's a code block
    after_stripped = after.strip()
    is_code = True
    if after_stripped.startswith("{") and "}" in after_stripped:
        directive = after_stripped[1 : after_stripped.find("}")].split()[0]
        is_code = directive in CODE_CONTENT_DIRECTIVES
        if not is_code:
            state.just_opened_fence_directive = True

    state.fence_stack.append(FenceState(char, length, indent, is_code))


def close_alerts_to_depth(state: ParserState, target_depth: int) -> None:
    """Close all alerts deeper than target_depth."""
    while state.alert_stack and state.alert_stack[-1].depth > target_depth:
        alert = state.alert_stack.pop()
        colons = "::::" if alert.has_nested else ":::"
        state.result.append(f"{alert.indent}{colons}")


def mark_parent_nested(state: ParserState) -> None:
    """Mark the parent alert as having a nested alert and update its opening."""
    if not state.alert_stack:
        return

    parent = state.alert_stack[-1]
    if not parent.has_nested:
        # Update the opening line to use 4 colons
        old_line = state.result[parent.opening_line_index]
        state.result[parent.opening_line_index] = old_line.replace(":::{", "::::{", 1)
        parent.has_nested = True


def open_alert(state: ParserState, alert_type: str, indent: str, depth: int) -> None:
    """Open a new alert at the given depth."""
    # Mark parent as nested if this is a nested alert
    if state.alert_stack:
        mark_parent_nested(state)

    # Insert blank line if we just opened a fence directive
    if state.just_opened_fence_directive:
        state.result.append("")

    opening_idx = len(state.result)
    state.result.append(f"{indent}:::{{{alert_type.lower()}}}")
    state.alert_stack.append(
        Alert(
            alert_type=alert_type,
            indent=indent,
            depth=depth,
            opening_line_index=opening_idx,
        )
    )
    state.modified = True


def process_quoted_line(state: ParserState, line: str) -> bool:
    """Process a line that starts with quote markers.

    Returns True if the line was handled as part of an alert.
    """
    indent, depth, content = count_quote_depth(line)

    if depth == 0:
        return False

    # Check if this could start a new alert
    if alert_match := GITHUB_ALERT_PATTERN.match(content):
        alert_type = alert_match.group(1)

        # Check if we're inside an alert at the same depth
        # In that case, treat this as literal text, not a new alert
        # (handles duplicate directives like "> [!TIP]" followed by "> [!TIP]")
        if state.alert_stack and depth == state.alert_stack[-1].depth:
            # This is a duplicate directive line - treat as content
            current_alert = state.alert_stack[-1]
            stripped_content = content.lstrip()
            state.result.append(f"{current_alert.indent}{stripped_content}")
            return True

        # Close any alerts at same or deeper level
        close_alerts_to_depth(state, depth - 1)

        # Open new alert
        open_alert(state, alert_type, indent, depth)
        return True

    # Not a new alert - check if we're continuing an existing alert
    if not state.alert_stack:
        return False

    current_alert = state.alert_stack[-1]

    # If depth decreased below current alert, close deeper alerts
    if depth < current_alert.depth:
        close_alerts_to_depth(state, depth)
        if not state.alert_stack:
            return False
        current_alert = state.alert_stack[-1]

    # If at the alert's depth or deeper, add content
    if depth >= current_alert.depth:
        # Calculate how many extra > levels beyond the alert's depth
        extra_depth = depth - current_alert.depth

        if extra_depth > 0:
            # Preserve extra > markers as blockquote syntax
            blockquote_prefix = "> " * extra_depth
            stripped_content = content.lstrip()
            state.result.append(
                f"{current_alert.indent}{blockquote_prefix}{stripped_content}"
            )
        else:
            # Same depth as alert - just strip the quote prefix
            stripped_content = content.lstrip()
            state.result.append(f"{current_alert.indent}{stripped_content}")
        return True

    return False


def replace_github_alerts(text: str) -> str | None:
    """Transform GitHub alerts into MyST admonitions.

    Identify GitHub alerts in the provided ``text`` and transform them into
    colon-fenced ``:::`` MyST admonitions.

    Returns ``None`` if no transformation was applied, else returns the transformed
    text.
    """
    lines = text.split("\n")
    state = ParserState()

    for line in lines:
        # Handle code fences
        if fence_match := CODE_FENCE_PATTERN.match(line):
            indent, chars, after = fence_match.groups()

            # Check if fence would close and affect alerts
            if state.alert_stack:
                for fence in reversed(state.fence_stack):
                    if (
                        chars[0] == fence.char
                        and len(chars) >= fence.length
                        and indent == fence.indent
                        and not after.strip()
                    ):
                        # Closing a fence that contains our alert
                        close_alerts_to_depth(state, 0)
                        break

            process_fence(state, indent, chars, after)
            state.result.append(line)
            state.prev_line_blank = False
            continue

        # Skip processing inside code blocks
        if state.in_code_block():
            state.result.append(line)
            state.prev_line_blank = not line.strip()
            state.just_opened_fence_directive = False
            continue

        # Handle indented code blocks (4 spaces or tab after blank line)
        if state.prev_line_blank and INDENTED_CODE_BLOCK_PATTERN.match(line):
            state.result.append(line)
            state.prev_line_blank = False
            state.just_opened_fence_directive = False
            continue

        is_blank = not line.strip()

        # Try to process as a quoted line (potential alert)
        if process_quoted_line(state, line):
            state.prev_line_blank = is_blank
            state.just_opened_fence_directive = False
            continue

        # Non-quoted line - close all alerts
        if state.alert_stack:
            close_alerts_to_depth(state, 0)

        state.result.append(line)
        state.prev_line_blank = is_blank

        if not is_blank:
            state.just_opened_fence_directive = False

    # Close any remaining alerts
    close_alerts_to_depth(state, 0)

    return "\n".join(state.result) if state.modified else None


def convert_github_alerts(app: Sphinx, *args) -> None:
    """Convert GitHub alerts into MyST admonitions in content blocks."""
    content = args[-1]
    for i, orig_content in enumerate(content):
        if transformed := replace_github_alerts(orig_content):
            check_colon_fence(app)
            content[i] = transformed
