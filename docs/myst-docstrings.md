# {octicon}`pencil` MyST docstrings

Write Python docstrings in [MyST markdown](https://myst-parser.readthedocs.io/en/latest/) instead of reStructuredText. The {mod}`click_extra.sphinx.myst_docstrings` Sphinx extension transparently converts MyST back to reST at build time, so `sphinx.ext.autodoc` works without modification.

## Why not `sphinx-autodoc2`?

[`sphinx-autodoc2`](https://github.com/sphinx-extensions2/sphinx-autodoc2) was designed as a full replacement for `sphinx.ext.autodoc` with native MyST support. It parses docstrings as MyST directly, eliminating the need for a conversion step. In practice the project is abandoned: the last release (`v0.5.0`) dates from November 2023, its test suite does not pass against current Sphinx or docutils versions, and it has no compatibility with `sphinx_autodoc_typehints`.

{mod}`click_extra.sphinx.myst_docstrings` fills the same gap with a lighter approach: it hooks into `sphinx.ext.autodoc`'s existing `autodoc-process-docstring` event and converts MyST constructs to reST before Sphinx processes them. This preserves full compatibility with `sphinx_autodoc_typehints`, `autodoc_default_options`, `autoclass_content`, and every other extension or setting that builds on `sphinx.ext.autodoc`. The conversion is regex-based, idempotent, and handles all inline and block constructs that are valid inside docstrings: cross-references, inline code, links, fenced directives, plain code blocks, and footnotes. See [Comparison with `sphinx-autodoc2`](#comparison-with-sphinx-autodoc2) for a detailed feature matrix.

## Setup

### 1. Add the extension

In your Sphinx `conf.py`, add {mod}`click_extra.sphinx.myst_docstrings` alongside `sphinx.ext.autodoc`:

```python
extensions = [
    "sphinx.ext.autodoc",
    "click_extra.sphinx.myst_docstrings",
    "sphinx_autodoc_typehints",  # must come after myst_docstrings
    # ... other extensions
]
```

If `sphinx.ext.autodoc` is absent, the `autodoc-process-docstring` event never fires and the extension silently does nothing.

```{warning}
If you also use `sphinx_autodoc_typehints`, list `click_extra.sphinx.myst_docstrings` **before** it in the `extensions` list. The extension registers its `autodoc-process-docstring` hook at priority 400 (vs the default 500 used by `sphinx_autodoc_typehints`), so MyST-to-reST conversion always runs first regardless of registration order. Listing it first makes the intent explicit and is enforced at load time: if `sphinx_autodoc_typehints` is already registered when `click_extra.sphinx.myst_docstrings` loads, the build fails with a clear error.

The concrete failure mode if the order is wrong: the inline-code converter doubles the backticks inside domain-qualified roles (like `` :py:obj:`None` ``) that `sphinx_autodoc_typehints` injects into the docstring after type-hint resolution. The result is visible `` ``...`` `` in the rendered HTML around return-type annotations.
```

### 2. Add the dependency

`click-extra` with its `sphinx` extra must be importable during the docs build. Add it to your docs dependency group in `pyproject.toml`:

```toml
[dependency-groups]
docs = [
  "click-extra[sphinx]",
  "sphinx>=8",
  # ...
]
```

### 3. Migrate existing docstrings

For a one-time migration of an existing reST codebase, run the bundled converter on your source directory:

```shell-session
$ click-extra convert-to-myst
```

The command auto-detects the source package directory from the `[project.scripts]` entry points in `pyproject.toml`. You can also pass an explicit path:

```shell-session
$ click-extra convert-to-myst src/mypackage
```

The conversion is idempotent: re-running it on already-converted files is a no-op. Migration is also optional: the extension passes reST-only docstrings through unchanged, so a codebase can convert one module at a time.

The applied transformations, in order:

1. **Cross-references**: `` :role:`target` `` becomes `` {role}`target` ``
2. **Named links**: `` `text <url>`_ `` becomes `[text](url)`
3. **Inline code**: ``` ``code`` ``` becomes `` `code` ``
4. **`#:` comment blocks**: prefix stripped, directives converted, prefix restored
5. **Directives**: `.. directive::` + indented body becomes ```` ```{directive} ```` / ```` ``` ````

Content containing `{` inside inline code is left as double backticks to avoid clashing with MyST cross-reference syntax. These pass through the build-time extension unchanged.

## Syntax reference

Write docstrings in standard MyST markdown. The extension handles the reST translation at build time.

### Cross-references

Use MyST `` {role}`target` `` syntax instead of reST `` :role:`target` `` syntax:

| MyST (write this)                    | reST (produced at build time)        |
| :----------------------------------- | :----------------------------------- |
| `` {func}`foo` ``                    | `` :func:`foo` ``                    |
| `` {data}`~extra_platforms.MACOS` `` | `` :data:`~extra_platforms.MACOS` `` |
| `` {class}`str` ``                   | `` :class:`str` ``                   |

The `~` prefix for abbreviating to the last component works the same way.

### Admonitions

Use backtick fences:

````python
def detect():
    """Detect the current platform.

    ```{note}
    Falls back to generic detection if the specific
    platform check is unavailable.
    ```
    """
````

All standard Sphinx admonitions work: `note`, `warning`, `caution`, `hint`, `tip`, `seealso`, `danger`, `important`. Colon fences (`:::{note}` / `:::`) parse identically in MyST but `mdformat` treats them as literal text and escapes the colons, so prefer backtick fences.

Admonitions with titles:

````python
"""
```{warning} Experimental API
This function may change in future releases.
```
"""
````

### Links

Use standard markdown links:

| MyST (write this)                                 | reST (produced at build time)                     |
| :------------------------------------------------ | :------------------------------------------------ |
| `[click here](https://example.com)`               | `` `click here <https://example.com>`_ ``         |
| `` [`sys.platform`](https://docs.python.org/3) `` | `` `sys.platform <https://docs.python.org/3>`_ `` |

Backticks in link labels are stripped automatically because reST does not support nested markup.

### Inline code

Use single backticks. The extension doubles them for reST:

| MyST (write this)          | reST (produced at build time)  |
| :------------------------- | :----------------------------- |
| `` `True` ``               | ``` ``True`` ```               |
| `` `platform.machine()` `` | ``` ``platform.machine()`` ``` |

### Code blocks

Both plain triple-backtick fences and `{code-block}` directive fences are supported:

````python
"""
```python
extensions = [
    "sphinx.ext.autodoc",
    "click_extra.sphinx.myst_docstrings",
]
```
"""
````

Plain fences (```` ```python ````) are converted to `.. code-block:: python` directives. Directive fences (```` ```{code-block} python ````) are also converted. The language identifier is optional: a bare ```` ``` ```` fence becomes `.. code-block::` with no language.

### Footnotes

Footnote references and definitions are converted:

| MyST (write this)          | reST (produced at build time) |
| :------------------------- | :---------------------------- |
| `[^1]`                     | `[#1]_`                       |
| `[^label]: Footnote text.` | `.. [#label] Footnote text.`  |

Continuation lines in multi-line footnote definitions pass through with their indentation preserved.

### Field lists

`:param:`, `:return:`, `:raises:` and other Sphinx field list entries use the same syntax in MyST and reST, so the field list markers themselves need no conversion. The content *inside* field list entries is converted normally: inline code, cross-references, and links all work:

```python
def read(path, config):
    """Read a file and return its contents.

    :param path: Filesystem `path` to process.
    :param config: A {class}`~orchard.config.Config` instance.
    :return: `True` if the file was read successfully.
    :raises FileNotFoundError: If `path` does not exist.
    """
```

In the example above, single-backtick code spans (`path`, `True`) are doubled for reST, and the `{class}` cross-reference is converted to `:class:`. The field list markers (`:param path:`, `:return:`, `:raises FileNotFoundError:`) pass through unchanged.

## Limitations

The extension handles the constructs listed above. It does **not** convert:

- **Nested fences of the same type** (` ` `/` \`\`\` \`\`\`\`). A single nesting level works because the inner directive (like `.. code-block::`) stays as reST inside the converted outer fence.
- **Complex tables** (```` ```{list-table} ````, ```` ```{csv-table} ````). These work in module-level docstrings processed by `myst-parser` but are unlikely to appear in function docstrings.
- **`{` inside single backticks**. Content like `` `{version}` `` would be misinterpreted as a cross-reference. Keep these as double backticks (``` ``{version}`` ```), which the extension passes through to Sphinx as-is.
- **MyST substitution references** (`{{variable}}`). These are a `myst-parser` feature for `.md` files and are not processed inside docstrings.
- **MyST definition lists**. The `deflist` extension syntax (term on one line, `: definition` on the next) is not converted. The `: ` prefix is ambiguous with field list continuations and other reST constructs, making reliable regex detection impractical without a full parser. Use reST definition lists or restructure as a field list.
- **Heading syntax** (`#`, `##`). Markdown headings inside docstrings are not converted to reST sections. Docstrings should not contain headings.
- **Strikethrough** (`~~text~~`). Not a standard reST construct; no conversion target exists.
- **Task lists** (`- [x]`, `- [ ]`). No reST equivalent.

For constructs the extension does not handle, use reST syntax directly in the docstring body. The extension is idempotent: reST content passes through unchanged.

## Comparison with `sphinx-autodoc2`

[`sphinx-autodoc2`](https://github.com/sphinx-extensions2/sphinx-autodoc2) took a different architectural approach: it replaced `sphinx.ext.autodoc` entirely and parsed docstrings as native MyST using `myst-parser` directly. This eliminated the need for any conversion step. The project is abandoned (last release `v0.5.0`, November 2023; incompatible with Sphinx 8+, docutils 0.21+, and astroid 4+).

{mod}`click_extra.sphinx.myst_docstrings` covers the same docstring-authoring use case with a lighter approach: regex-based conversion inside `autodoc-process-docstring`. The trade-off is a handful of unsupported constructs (listed above) in exchange for full compatibility with the existing `sphinx.ext.autodoc` ecosystem.

Architectural differences that are inherent to `sphinx.ext.autodoc` and cannot be addressed by a conversion extension:

| Capability                         | `sphinx-autodoc2`                      | `autodoc` + `myst_docstrings`                         |
| :--------------------------------- | :------------------------------------- | :---------------------------------------------------- |
| Static analysis (no module import) | Yes (via `astroid`)                    | No: modules must be importable at build time          |
| Integrated module discovery        | Yes (no `sphinx-apidoc` step)          | No: requires separate `sphinx-apidoc` or manual stubs |
| Incremental per-object rebuilds    | Yes                                    | No: full rebuild on any change                        |
| `TYPE_CHECKING` block visibility   | Yes (static analysis sees all imports) | No: only sees runtime imports                         |
| Native MyST output files           | Yes (generates `.md` API docs)         | No: generates reST internally                         |

These are limitations of `sphinx.ext.autodoc` itself, not of the conversion extension. They affect how Sphinx discovers and imports modules, not how docstring content is authored or rendered.
