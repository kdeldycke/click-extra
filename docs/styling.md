# {octicon}`pencil` Styling

Click Extra ships its own `Style` class as a drop-in replacement for [`cloup.Style`](https://cloup.readthedocs.io/en/stable/pages/help-formatting.html#cloup.Style) (which itself wraps [`click.style`](https://click.palletsprojects.com/en/stable/api/#click.style)). The runtime contract — calling the instance to apply styling, equality, hashing, `with_()` — is identical to cloup's; everything below is purely additive ergonomics.

The class lands automatically when you do `from click_extra import Style`: `__init__.py` re-exports it after `from cloup import *` so the click-extra version takes precedence.

```{python:run}
from click_extra import Style

red_bold = Style(fg="red", bold=True)
print(red_bold("hello"))
```

## Hex-string color shorthand

`Style.fg` and `Style.bg` accept `"#rrggbb"` or `"#rgb"` shorthand strings alongside Click's named colors and RGB tuples. The shorthand is converted to an RGB tuple on construction:

```{python:run}
from click_extra import Style

print(Style(fg="#f1fa8c"))  # 6-digit hex
print(Style(fg="#abc"))  # 3-digit shorthand expands to #aabbcc
print(Style(fg=(241, 250, 140)))  # tuple form still works
print(Style(fg="bright_yellow"))  # Click named color still works
```

## REPL-friendly `__repr__` and `__str__`

The compact `__repr__` hides `None` and falsy attributes and renders RGB tuples as `#rrggbb`. The `__str__` returns the styled word `"sample"` so `print(style)` and debugger inspectors visualize what the style does, not just its fields:

```{python:run}
from click_extra import Style

s = Style(fg="#f1fa8c", bold=True, italic=True)
print(repr(s))
print(s)
```

## Composition operator `a | b`

The `|` operator merges two styles. The right operand wins on conflicts; `None` fields on either side don't override the other side's set fields. The reflected `__ror__` makes mixing with `cloup.Style` (or any compatible subclass) symmetric:

```{python:run}
from click_extra import Style

base = Style(fg="cyan", bold=True)
override = Style(fg="magenta", italic=True)
print(repr(base | override))
print(repr(override | base))
```

## `cascade(base)` — fill gaps from a base style

Where `|` lets the right operand always win, `cascade` keeps the *instance*'s set values and only fills its `None` fields from `base`. Useful for theme-inheritance patterns where a derived style should keep its overrides and inherit the rest:

```{python:run}
from click_extra import Style

base = Style(fg="cyan", bold=True, italic=True)
derived = Style(fg="magenta")  # bold/italic are None
print(repr(derived.cascade(base)))
```

## TOML/JSON round-trip with `to_dict` / `from_dict`

`Style.to_dict()` emits a plain mapping containing only the set fields, with RGB tuples flattened to `#rrggbb` strings so the output round-trips through TOML/JSON/YAML untouched. `Style.from_dict()` is the symmetric loader and rejects unknown keys with `TypeError` so typos surface immediately:

```{python:run}
import json

from click_extra import Style

s = Style(fg=(241, 250, 140), bold=True)
payload = s.to_dict()
print(payload)

# Round-trip through JSON.
json_blob = json.dumps(payload)
print(json_blob)

s2 = Style.from_dict(json.loads(json_blob))
print(s == s2)
```

```{python:run}
from click_extra import Style

# Unknown field → TypeError at load time, not silent drop.
try:
    Style.from_dict({"colour": "red"})
except TypeError as exc:
    print(repr(exc))
```

## `to_css()` — CSS declaration list

Renders the style as a semicolon-separated CSS declaration list, suitable for inline `style="..."` attributes on HTML spans. Used by [`AnsiHtmlFormatter`](pygments.md#ansi-html-formatter) and the [theme palette swatches](theme.md#palettes):

```{python:run}
from click_extra import Style

print(Style(fg="#f1fa8c", bold=True, italic=True).to_css())
print(Style(fg="bright_red", underline=True, strikethrough=True).to_css())
print(Style(fg="cyan", dim=True).to_css())
```

The mapping is:

| Attribute       | CSS declaration                  |
| --------------- | -------------------------------- |
| `fg`            | `color: <color>`                 |
| `bg`            | `background-color: <color>`      |
| `bold`          | `font-weight: bold`              |
| `italic`        | `font-style: italic`             |
| `underline`     | `text-decoration: underline`     |
| `overline`      | `text-decoration: overline`      |
| `strikethrough` | `text-decoration: line-through`  |
| `dim`           | `opacity: 0.6`                   |
| `reverse`       | `filter: invert(1)`              |

`underline`, `overline` and `strikethrough` collapse into a single `text-decoration` declaration when more than one is set.

## `from_ansi()` — parse ANSI SGR escapes

Given one or more consecutive ANSI SGR escapes (the `\x1b[...m` sequences Click emits), rebuild a `Style` instance. Supports the standard 8/16-color codes (30–37, 40–47, 90–97, 100–107), the `38;5;n` / `48;5;n` 256-color extension, and the `38;2;r;g;b` / `48;2;r;g;b` 24-bit extension. Reset codes (`0`) are ignored. Multiple back-to-back escapes (as Click emits when combining colors with attributes) are merged into a single `Style`:

```{python:run}
from click_extra import Style

# Single escape with multiple SGR codes.
print(repr(Style.from_ansi("\x1b[31;1m")))

# Back-to-back escapes (Click's typical pattern).
print(repr(Style.from_ansi("\x1b[31m\x1b[1m")))

# 24-bit RGB.
print(repr(Style.from_ansi("\x1b[38;2;241;250;140m")))

# 256-color palette index.
print(repr(Style.from_ansi("\x1b[38;5;226m")))
```

`from_ansi` is the inverse of calling the style: parsing the output of `Style(fg="red", bold=True)("text")` recovers the same style.

## `contrast_ratio(other)` — WCAG accessibility check

Returns the [WCAG 2.x contrast ratio](https://www.w3.org/TR/WCAG22/#dfn-contrast-ratio) between this style's foreground and another style's foreground. Result is in `[1, 21]`: `1` = identical colors (no contrast), `21` = maximum contrast (black on white). WCAG AA requires `4.5+` for normal text and `3.0+` for large text; AAA wants `7.0+` and `4.5+` respectively.

```{python:run}
from click_extra import Style

# White text on black background: maximum contrast.
print(f"{Style(fg='white').contrast_ratio(Style(fg='black')):.2f}")

# Cyan on white background: low contrast (would fail WCAG AA).
print(f"{Style(fg='cyan').contrast_ratio(Style(fg='white')):.2f}")

# Solarized's accent blue on its base03 background.
solarized_blue = Style(fg="#268bd2")
solarized_bg = Style(fg="#002b36")
print(f"{solarized_blue.contrast_ratio(solarized_bg):.2f}")
```

Click Extra uses this internally to gate the [WCAG legibility floor and AA Large compliance for branded themes](https://github.com/kdeldycke/click-extra/blob/main/tests/test_themes.py).

## Equality and hash

`Style` overrides cloup's `__eq__` and `__hash__` to skip the lazily-populated `_style_kwargs` cache, so two otherwise-identical styles compare equal whether or not either has been called yet:

```{python:run}
from click_extra import Style

a = Style(fg="red", bold=True)
b = Style(fg="red", bold=True)
print(a == b)  # True even though neither was called yet
a("trigger cache")  # Populate `a`'s lazy cache.
print(a == b)  # Still True; the cache is excluded from equality.
print(hash(a) == hash(b))
```

## Shared dataclass round-trip helpers

The serialization machinery `Style.to_dict` / `from_dict` relies on three small module-level helpers that codify "walk dataclass fields, skip the cloup `_style_kwargs` cache, skip default-valued fields, raise on unknown keys". They're public so other dataclass-shaped values in click-extra (notably [`HelpExtraTheme`](theme.md)) can reuse them, and so downstream code with similar patterns can build on the same primitives.

### `fields_to_dict(instance, *, encode=…, keep=…)`

Walks every field via `dataclasses.fields`, applies an optional `keep(field, value) -> bool` filter (default keeps every non-default field), and passes the surviving values through an `encode(field, value) -> encoded_value` callback (default identity):

```{python:run}
from dataclasses import dataclass

from click_extra.styling import fields_to_dict


@dataclass
class Color:
    r: int = 0
    g: int = 0
    b: int = 0
    name: str = ""


# Default-valued fields are skipped automatically.
print(fields_to_dict(Color(r=255, g=128, name="orange")))


# Custom encoder: render RGB as a hex string.
def hex_encoder(field, value):
    if field.name in {"r", "g", "b"}:
        return f"{value:02x}"
    return value


print(fields_to_dict(Color(r=255, g=128, name="orange"), encode=hex_encoder))
```

### `dict_to_fields(cls, data, *, decode=…)`

The symmetric loader. Validates every key in `data` against `cls`'s dataclass fields and raises `TypeError` listing every unknown key, so callers can build a constructor call without an extra pre-validation pass:

```{python:run}
from dataclasses import dataclass

from click_extra.styling import dict_to_fields


@dataclass
class Color:
    r: int = 0
    g: int = 0
    b: int = 0
    name: str = ""


print(Color(**dict_to_fields(Color, {"r": 255, "name": "orange"})))

# Unknown key → TypeError listing the offending name.
try:
    dict_to_fields(Color, {"red": 255})
except TypeError as exc:
    print(repr(exc))
```

### `cascade_fields(base, overlay, *, is_set=…)`

Slot-level analogue of `Style.cascade`'s attribute-level merge. Walks both instances' fields and produces a kwargs dict suitable for `type(base)(**kwargs)` (or `dataclasses.replace(base, **kwargs)`):

```{python:run}
from dataclasses import dataclass, replace

from click_extra.styling import cascade_fields


@dataclass
class Color:
    r: int = 0
    g: int = 0
    b: int = 0
    name: str = ""


base = Color(r=255, g=255, b=255, name="white")
overlay = Color(name="snow")  # only `name` is set
merged = replace(base, **cascade_fields(base, overlay))
print(merged)
```

## `click_extra.styling` API

```{eval-rst}
.. autoclasstree:: click_extra.styling
   :strict:

.. automodule:: click_extra.styling
   :members:
   :undoc-members:
   :show-inheritance:
```
