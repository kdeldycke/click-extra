# {octicon}`file-code` MkDocs

[MkDocs](https://www.mkdocs.org) can render ANSI-colored terminal output using Click Extra's [Pygments lexers](pygments.md). Without proper setup, raw escape codes show up as garbage text: `[1mbump-my-version[0m [[1;36mOPTIONS[0m]` instead of colored output.

````{important}
For these helpers to work, you need to install `click_extra`'s additional dependencies from the `pygments` extra group:

```{code-block} shell-session
$ pip install click-extra[pygments]
```
````

## Setup

Your `mkdocs.yml` should use [pymdownx.highlight](https://facelessuser.github.io/pymdown-extensions/extensions/highlight/) and [pymdownx.superfences](https://facelessuser.github.io/pymdown-extensions/extensions/superfences/) for fenced code block support:

```{code-block} yaml
:caption: `mkdocs.yml`
markdown_extensions:
  - pymdownx.highlight:
      use_pygments: true
  - pymdownx.superfences
```

## ANSI CSS

MkDocs themes ship Pygments CSS for standard tokens but know nothing about `Token.Ansi.*`. Run this script to generate a stylesheet covering the 16 named colors, their background variants, and all text attributes (bold, italic, underline, strikethrough, etc.):

```{code-block} python
:caption: `generate_ansi_css.py`
"""Generate CSS for ANSI-colored code blocks in MkDocs."""

from pathlib import Path

from click_extra.pygments import EXTRA_ANSI_CSS, _NAMED_COLORS

lines = []

# Text attributes (bold, italic, underline, etc.).
for attr, declaration in EXTRA_ANSI_CSS.items():
    lines.append(
        f'.highlight [class*="-Ansi"][class*="-{attr}"] {{ {declaration} }}'
    )

# Named foreground and background colors (standard + bright).
for name, hex_value in _NAMED_COLORS.items():
    lines.append(
        f'.highlight [class*="-Ansi"][class*="-{name}"]'
        f" {{ color: {hex_value} }}"
    )
    lines.append(
        f'.highlight [class*="-Ansi"][class*="-BG{name}"]'
        f" {{ background-color: {hex_value} }}"
    )

# Blink animation keyframes.
lines.append("@keyframes ansi-blink { 50% { opacity: 0 } }")

Path("docs/css/ansi-colors.css").write_text("\n".join(lines) + "\n")
```

### Why attribute selectors

Pygments' standard `HtmlFormatter` (used by pymdownx.highlight) renders compound tokens like `Token.Ansi.Bold.Cyan` as a single concatenated CSS class: `-Ansi-Bold-Cyan`. A class selector for `-Ansi-Cyan` won't match that. But the attribute selector `[class*="-Cyan"]` matches because `-Cyan` appears as a substring of `-Ansi-Bold-Cyan`, so both the bold and cyan rules apply from their individual selectors.

The `[class*="-Ansi"]` guard scopes every rule to ANSI tokens, preventing collisions with other Pygments classes.

### Include the CSS

Reference the generated file in `mkdocs.yml`:

```{code-block} yaml
:caption: `mkdocs.yml`
:emphasize-lines: 2
extra_css:
  - css/ansi-colors.css
```

## Usage

Use Click Extra's `ansi-` prefixed lexers as the language identifier in fenced code blocks. The lexer names map directly to Pygments IDs registered via [entry points](pygments.md#integration), so MkDocs picks them up automatically.

For terminal sessions with colored output, `ansi-shell-session` is the most common:

````{code-block} markdown
```ansi-shell-session
$ my-cli --help
[1mUsage:[0m [97mmy-cli[0m [36m[2m[OPTIONS][0m [36m[2mCOMMAND[0m [36m[2m[ARGS][0m...

  Manage recipes and shopping lists.

[1mOptions:[0m
  [36m--name[0m [36m[2mTEXT[0m    Your name.
  [36m--help[0m          Show this message and exit.
```
````

For Python console sessions:

````{code-block} markdown
```ansi-pycon
>>> print("\033[1;32mHarvest ready!\033[0m Check your garden.")
[1;32mHarvest ready![0m Check your garden.
```
````

See the [full list of available ANSI lexer variants](pygments.md#lexer-variants).

## Limitations

The CSS attribute selector approach covers the 16 standard named colors, their bright and background variants, and all text attributes, in any combination. This handles the vast majority of CLI output.

The [256-color indexed palette](pygments.md#ansi-html-formatter) is not covered because numeric suffixes create prefix collisions (`C1` matching `C10`, `C100`, etc.). If your CLI uses 256-color or 24-bit RGB codes, generate the full palette CSS with:

```{code-block} python
from pygments.formatters import get_formatter_by_name

formatter = get_formatter_by_name("ansi-html")
print(formatter.get_style_defs(".highlight"))
```

This produces individual class selectors (`.highlight .-Ansi-C42 { ... }`) for all 512 palette entries. These work for simple (single-color) tokens but not for compound tokens like bold + 256-color.
