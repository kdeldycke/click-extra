# {octicon}`book` MkDocs

[MkDocs](https://www.mkdocs.org) can render ANSI-colored terminal output using Click Extra's [Pygments lexers](pygments.md). Without this, raw escape codes show up as garbage text in documentation.

````{important}
For these helpers to work, you need to install `click_extra`'s additional dependencies from the `mkdocs` extra group:

```{code-block} shell-session
$ pip install click-extra[mkdocs]
```
````

## Setup

Once [Click Extra is installed](install.md), enable the plugin in your `mkdocs.yml`:

```{code-block} yaml
:caption: `mkdocs.yml`
:emphasize-lines: 6-7
markdown_extensions:
  - pymdownx.highlight:
      use_pygments: true
  - pymdownx.superfences

plugins:
  - click-extra
```

The plugin patches [pymdownx.highlight](https://facelessuser.github.io/pymdown-extensions/extensions/highlight/)'s formatter classes to use `AnsiHtmlFormatter`, the same way the [Sphinx integration](sphinx.md#setup) patches `PygmentsBridge`. This gives every code block full ANSI color rendering: compound tokens like `Token.Ansi.Bold.Cyan` are decomposed into individual CSS classes, and the stylesheet includes rules for the 256-color indexed palette and all SGR text attributes.

## ANSI shell sessions

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

## `click_extra.mkdocs` API

```{eval-rst}
.. automodule:: click_extra.mkdocs
   :members:
   :undoc-members:
   :show-inheritance:
```
