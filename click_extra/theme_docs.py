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
"""Render a theme palette as an inline-styled HTML fragment for documentation.

:func:`palette_html` is called from ``docs/theme.md`` to render every
built-in theme's palette at Sphinx build time.
:func:`inject_slot_example_docstring` is registered as a Sphinx
``autodoc-process-docstring`` hook from ``docs/conf.py`` to inject a colored
example into each HelpTheme slot's autodoc block. This is build-time
documentation code, kept out of the runtime theme module.
"""

from __future__ import annotations

import dataclasses
import html
import re

from cloup._util import identity

from .styling import _ATTR_CSS, Style, _color_to_css, _rgb_to_hex
from .theme import BUILTIN_THEMES, HelpTheme

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any


_PALETTE_SKIP_SLOTS: frozenset[str] = frozenset({
    # Inherited cloup slots that built-in themes leave at identity.
    "command_help",
    "section_help",
    "col1",
    "col2",
    "epilog",
    # Log-level slot intentionally left unstyled by every built-in (INFO is
    # the default verbosity and shouldn't stand out).
    "info",
    # Internal cache from cloup; never rendered.
    "_style_kwargs",
    # Boolean toggle, not a Style.
    "cross_ref_highlight",
})

_PALETTE_SWATCH = (
    '<span style="display:inline-block;width:0.85em;height:0.85em;'
    "background:{css};border:1px solid var(--color-foreground-muted,#888);"
    'border-radius:2px;vertical-align:-0.15em;margin-right:0.35em"></span>'
)

# Per-attribute inline CSS so each attribute's label visually demonstrates
# itself in the rendered swatch row (``bold`` shown in bold, ``italic``
# in italic, ``underline`` with an underline, …). Iteration order doubles
# as the visual order of the attribute pills next to each slot.
#
# Derived from the shared ``_ATTR_CSS`` source of truth in
# ``click_extra.styling`` so the documentation pills and ``Style.to_css``
# never drift. ``blink`` has no standard CSS and maps to an empty string,
# leaving its pill unstyled (no built-in theme sets it).
_PALETTE_ATTR_CSS: dict[str, str] = {
    attr: f"{prop}: {value}" if prop else ""
    for attr, (prop, value) in _ATTR_CSS.items()
}

# Slots inherited from cloup's HelpTheme. Each one links to cloup's
# autoapi-generated docs (which expose per-field anchors), instead of
# click-extra's local HelpTheme autodoc anchor (which only covers the
# slots HelpTheme adds on top of cloup's base class).
_PALETTE_CLOUP_SLOTS: frozenset[str] = frozenset({
    "invoked_command",
    "command_help",
    "heading",
    "constraint",
    "section_help",
    "col1",
    "col2",
    "alias",
    "alias_secondary",
    "epilog",
})

# Per-slot example templates. Substrings wrapped in ``«…»`` (U+00AB / U+00BB
# guillemets, picked because they never appear in real CLI help output) are
# styled by calling ``theme.<slot>(text)`` at render time, so the example
# faithfully reflects whatever the active theme's slot produces. Each slot
# that the built-in themes actually style has an entry; unstyled inherited
# slots and the boolean ``cross_ref_highlight`` toggle are intentionally
# left out and the renderer falls back to a plain "(no example available)"
# placeholder for them.
_PALETTE_EXAMPLES: dict[str, str] = {
    # Log-level slots: rendered by Formatter on the levelname token.
    "critical": "«CRITICAL»: Database connection lost.",
    "error": "«ERROR»: Configuration file not found.",
    "warning": "«WARNING»: Requested 16 jobs exceeds available CPU cores (8).",
    "info": "INFO: Loaded 23 records.",
    "debug": "«DEBUG»: Resolved /etc/myapp/config.toml.",
    # Cloup-inherited help-screen slots: rendered by HelpFormatter on
    # the matching tokens of help-screen output.
    "invoked_command": "Usage: «my-cli» [OPTIONS] COMMAND [ARGS]...",
    "heading": "«Options:»",
    "constraint": "(«mutually exclusive»)",
    "alias": "  show, «ls»     Show the current state.",
    "alias_secondary": "  show «(»ls«)»     Show the current state.",
    # HelpTheme-native help-screen slots.
    "option": (
        "«--config» CONFIG_PATH    Location of the configuration file.\n"
        "«-v», «--verbose»           Increase verbosity."
    ),
    "subcommand": (
        "Commands:\n"
        "  «backup»        Snapshot the data store.\n"
        "  «restore»       Restore from a snapshot."
    ),
    "choice": ("--format [«json»|«csv»|«xml»]   Output format. Defaults to «json»."),
    "metavar": (
        "--output «TEXT»       Destination file.\n--workers «INTEGER»   Worker count."
    ),
    # The single wide marker covers the entire bracket field because
    # ``bracket`` is the runtime fallback for every inner slot (``envvar``,
    # ``default``, ``required``, ``range_label``) when those slots are left
    # at ``identity``. A theme that only sets ``bracket`` therefore colors
    # the whole field (structural tokens and value tokens alike) with the
    # same style. See ``_bracket_or`` in ``highlight.py`` and
    # ``test_bracket_field_inner_slot_fallback_to_bracket`` in the test suite.
    "bracket": "--port INTEGER    «[env var: PORT; default: 8080; required]»",
    "envvar": (
        "--threshold INTEGER   Acceptable error rate.\n"
        "                      [env var: «THRESHOLD, TEST_THRESHOLD»]"
    ),
    "default": (
        "--output FILENAME    Destination file.  [default: «out.csv»]\n"
        "--retries INTEGER    Retry budget.  [default: «5»]"
    ),
    "range_label": (
        "--level INTEGER RANGE    Verbosity level.  [«0<=x<=9»]\n"
        "--port INTEGER RANGE     Bind port.        [«x>=1024»]"
    ),
    "required": "--token TEXT    Authentication token.  [«required»]",
    "argument": (
        "Usage: cp [OPTIONS] «SRC» «DST»\nUsage: pack [OPTIONS] «[FILES]...» «[OUTPUT]»"
    ),
    "deprecated": (
        "--old-api    Legacy endpoint. «(DEPRECATED: use --new-api instead)»\n"
        "--legacy     Kept for compatibility. «(deprecated: removed in v9)»"
    ),
    "search": "--«retry»-budget INTEGER    The «retry» budget.",
    "success": "«✓» database migration completed\n«✓» 1,245 records imported",
    "subheading": (
        "«◼ 3 mails sharing hash a1b2c3d4»\n«◼ 7 mails sharing hash e5f6a7b8»"
    ),
}

# Matches a single ``«…»`` segment for the slot-example renderer.
_PALETTE_EXAMPLE_RE: re.Pattern[str] = re.compile("«([^»]+)»")

_PALETTE_CLOUP_URL = "https://cloup.readthedocs.io/en/stable/autoapi/cloup/index.html"


def _palette_slot_link(name: str) -> str:
    """Wrap a slot name in an anchor pointing at its dataclass-field definition.

    Cloup-inherited slots resolve to a per-field anchor on cloup's autoapi
    page (like ``#cloup.HelpTheme.invoked_command``); HelpTheme-native
    slots resolve to the local autodoc anchor on the same page that hosts
    the palette (``docs/theme.md``), so the link works inside click-extra's
    own documentation without an external roundtrip.
    """
    if name in _PALETTE_CLOUP_SLOTS:
        href = f"{_PALETTE_CLOUP_URL}#cloup.HelpTheme.{name}"
    else:
        href = f"#click_extra.theme.HelpTheme.{name}"
    return f'<a href="{href}"><code>{name}</code></a>'


def _render_slot_ansi(theme: HelpTheme, slot: str) -> str:
    """Render a slot's example template with literal ANSI SGR escapes.

    For each ``«…»`` segment, calls ``theme.<slot>(text)`` (the same code
    path click-extra uses to style real help-screen output at runtime)
    and splices the resulting escape-bearing string into the template.
    Used by the Sphinx ``autodoc-process-docstring`` hook in
    :func:`inject_slot_example_docstring` to inject a colored example into
    each :class:`~click_extra.theme.HelpTheme` slot's autodoc block, mirroring the
    HTML rendering :func:`_render_slot_example` produces for the
    palette tables.

    Returns an empty string when the slot has no template; callers treat
    that as "skip" rather than emitting an empty code block.
    """
    template = _PALETTE_EXAMPLES.get(slot)
    if template is None:
        return ""
    style = getattr(theme, slot)
    return _PALETTE_EXAMPLE_RE.sub(
        lambda m: style(m.group(1)) if callable(style) else m.group(1),
        template,
    )


def inject_slot_example_docstring(
    app: Any,
    what: str,
    name: str,
    obj: Any,
    options: Any,
    lines: list[str],
) -> None:
    """Sphinx ``autodoc-process-docstring`` hook injecting per-slot colored examples.

    For every :class:`~click_extra.theme.HelpTheme` slot that has an entry in
    :data:`_PALETTE_EXAMPLES`, append an ``ansi-color`` code block to the
    slot's autodoc lines. The example is rendered through
    :func:`_render_slot_ansi`, which calls ``BUILTIN_THEMES["dark"].<slot>(text)``
    to obtain the actual ANSI escapes click-extra would emit at runtime.

    Wire this up from a Sphinx ``conf.py`` with:

    .. code-block:: python

        from click_extra.theme_docs import inject_slot_example_docstring


        def setup(app):
            app.connect("autodoc-process-docstring", inject_slot_example_docstring)

    The hook intentionally targets *only* ``click_extra.theme.HelpTheme.<slot>``
    names so it won't accidentally rewrite unrelated docstrings; downstream
    projects can register the hook in their own ``conf.py`` if they
    consume HelpTheme docstrings.
    """
    prefix = "click_extra.theme.HelpTheme."
    if not name.startswith(prefix):
        return
    slot = name[len(prefix) :]
    # Skip the example when themes.toml is absent: there is no built-in
    # "dark" palette to render the slot with.
    default_theme = BUILTIN_THEMES.get("dark")
    if default_theme is None:
        return
    rendered = _render_slot_ansi(default_theme, slot)
    if not rendered:
        return
    lines.append("")
    lines.append("Rendered with the default ``dark`` theme:")
    lines.append("")
    lines.append(".. code-block:: ansi-color")
    lines.append("")
    lines.extend(f"   {ansi_line}" for ansi_line in rendered.split("\n"))


def _render_slot_example(theme: HelpTheme, slot: str) -> str:
    """Render a slot's example template as inline-styled HTML.

    Looks up the slot's template in :data:`_PALETTE_EXAMPLES`, then for
    every ``«…»``-marked segment calls ``theme.<slot>(text)`` to obtain the
    actual styling click-extra would apply at runtime. The styled bytes are
    converted to an inline CSS ``<span>`` via :meth:`Style.to_css`, so the
    rendered HTML faithfully reflects whatever the theme's slot produces,
    including the dim/italic/bold attribute mix and the foreground color.

    Returns an empty string when the slot has no example template (cloup
    slots that built-ins leave at identity, the boolean toggle, …); the
    palette renderer treats that as "no example row" rather than emitting
    an empty cell.
    """
    template = _PALETTE_EXAMPLES.get(slot)
    if template is None:
        return ""
    style = getattr(theme, slot)
    css = style.to_css() if isinstance(style, Style) else ""
    parts: list[str] = []
    last = 0
    for match in _PALETTE_EXAMPLE_RE.finditer(template):
        # Plain text between the previous segment and this match.
        parts.append(html.escape(template[last : match.start()]))
        token = html.escape(match.group(1))
        if css:
            parts.append(f'<span style="{css}">{token}</span>')
        else:
            # Slot is identity (or a non-Style callable we can't introspect):
            # emit the token plain, matching the runtime no-op behavior.
            parts.append(token)
        last = match.end()
    parts.append(html.escape(template[last:]))
    return (
        '<pre class="slot-example" style="margin:0.3em 0 0;'
        "padding:0.4em 0.6em;background:var(--color-code-background,#f5f5f5);"
        "border-radius:4px;font-size:0.85em;line-height:1.4;"
        'white-space:pre-wrap">' + "".join(parts) + "</pre>"
    )


def palette_html(theme: HelpTheme) -> str:
    """Render a theme's palette as an inline-styled HTML ``<dl>`` fragment.

    The output is a two-column definition list (slot name → styled swatch
    plus attribute decorations) safe to inject into MyST or reST host
    documents via the ``python:render`` Sphinx directive (or any
    ``raw:: html`` block). Used by ``docs/theme.md`` to render every
    built-in theme's palette at Sphinx build time without hand-maintaining
    swatch tables. Downstream projects with their own custom themes can
    call the same helper to get matching swatch listings in their own docs:

    .. code-block:: markdown

        ```{python:render}
        from click_extra.theme_docs import palette_html
        from my_app.themes import MY_THEME
        print(palette_html(MY_THEME))
        ```

    Slots that hold ``identity`` (no styling applied), the boolean
    :attr:`cross_ref_highlight` toggle, the internal ``_style_kwargs``
    cache, and a handful of inherited cloup slots that built-ins never
    style are skipped: every emitted row corresponds to a real palette
    choice in the theme.
    """
    rows: list[str] = []
    for f in dataclasses.fields(theme):
        if f.name in _PALETTE_SKIP_SLOTS:
            continue
        value = getattr(theme, f.name)
        if value is identity or value is None:
            continue
        fg = getattr(value, "fg", None)
        cell_parts: list[str] = []
        if fg is not None:
            css = _color_to_css(fg)
            if isinstance(fg, tuple) and len(fg) == 3:
                color_label = _rgb_to_hex(fg)
            else:
                color_label = str(fg)
            cell_parts.append(
                _PALETTE_SWATCH.format(css=css) + f"<code>{color_label}</code>"
            )
        attrs = [
            f'<span style="{css}">{name}</span>'
            for name, css in _PALETTE_ATTR_CSS.items()
            if getattr(value, name, None)
        ]
        if attrs:
            cell_parts.append(" ".join(attrs))
        # Tack the styled example onto the <dd> body when one exists.
        # Each example is rendered by replaying ``theme.<slot>(text)`` on
        # the marked segments of ``_PALETTE_EXAMPLES[slot]``, so the visual
        # is computed from the same code path that styles real help-screen
        # output at runtime: no hand-authored ANSI escapes anywhere.
        example_html = _render_slot_example(theme, f.name)
        body = " ".join(cell_parts) or "—"
        if example_html:
            body = body + example_html
        rows.append(f"<dt>{_palette_slot_link(f.name)}</dt><dd>{body}</dd>")
    return (
        '<dl class="theme-palette" style="display:grid;'
        "grid-template-columns:max-content 1fr;gap:0.2em 1em;"
        'margin:0.5em 0">' + "".join(rows) + "</dl>"
    )
