# {octicon}`code-square` Python directives

The Sphinx extension also runs arbitrary Python at build time. The `python:*` family renders what a block printed, as a code block or as live document content. The `matrix` directive renders a release compatibility table from a fixed generator.

```{seealso}
Both families need the `click_extra.sphinx` extension enabled, and the `python:*` one needs the build-time execution opt-in on top. The [Sphinx setup](sphinx.md#setup) covers each step.
```

## `python:*` directives

Click Extra also adds five general-purpose Python execution directives, registered under a separate `python` domain (distinct from Sphinx's built-in `py` domain for documenting API objects):

| Directive            | Purpose                                                                                                                                                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `python:source`      | Define and show a Python source block, executed silently. Use it to teach readers what a snippet looks like and to seed imports/variables for follow-up blocks.                                                                      |
| `python:run`         | Execute a Python block and render its captured `stdout` in a code block. Output language defaults to `text`; override with `:language:` for structured output (`json`, `html`, `yaml`, etc.).                                        |
| `python:render`      | Execute a Python block and parse its captured `stdout` as **live document content** using the host file's parser. Generated tables, headings, admonitions, and cross-references become first-class document nodes, not a code block. |
| `python:render-myst` | Execute a Python block and parse its captured `stdout` as MyST, regardless of host. Lets a `.rst` document embed MyST-generated content.                                                                                             |
| `python:render-rst`  | Execute a Python block and parse its captured `stdout` as reST, regardless of host. Lets a `.md` document embed reST-generated content.                                                                                              |

These complement the Click directives: `click:run` is for showing simulated CLI sessions; `python:run` is for showing arbitrary Python output; the `python:render*` family is for **inline content generation**, replacing the regenerator-script + marker-region pattern many projects use to keep auto-tables in sync.

```{hint}
This project eats its own dog food: the [ANSI lexer table in `pygments.md`](pygments.md#lexer-variants) is rendered live at build time by an inline [`python:render`](#python-directives) block that imports `LEXER_MAP` and prints a Markdown table. Read [the exact source lines on GitHub](https://github.com/kdeldycke/click-extra/blob/0cac18fdaa8770ac03a33a8e8969c2556fde674e/docs/pygments.md?plain=1#L243-L264) for a real-world example of replacing a regenerator script with a one-block inline build-time computation.
```

### Pick the right `render`

| Directive            | Parser used for captured stdout           | When to use                                    |
| -------------------- | ----------------------------------------- | ---------------------------------------------- |
| `python:render`      | Whatever parser owns the host source file | Generated markup matches the host file format. |
| `python:render-myst` | MyST, regardless of host                  | Embed MyST-generated content in a `.rst` host. |
| `python:render-rst`  | reST, regardless of host                  | Embed reST-generated content in a `.md` host.  |

`python:render` reuses the host state machine, so cross-references and Sphinx-aware roles resolve naturally. The forced-parser variants (`render-myst`, `render-rst`) parse into a fresh sub-document and graft the resulting nodes back into the page.

### `python:render`: docs as code

```{tip}
The strongest use case is replacing a `docs/docs_update.py` script that walks an in-process registry, renders Markdown, and rewrites a region of a `.md` file between `<!-- start -->` / `<!-- end -->` markers. With `python:render`, the same code lives inline in the page itself and runs at build time. The rendered HTML is always current because the source-of-truth registry is queried on every build.
```

Render the live list of Python's built-in modules as a Markdown table, executed by Sphinx at build time:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
```{python:render}
import sys
print("| Module | Type |")
print("|--------|------|")
for name in sorted(sys.builtin_module_names)[:5]:
    print(f"| `{name}` | built-in |")
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
.. python:render::

    import sys
    print("| Module | Type |")
    print("|--------|------|")
    for name in sorted(sys.builtin_module_names)[:5]:
        print(f"| `{name}` | built-in |")
```
`````
``````

Renders as a real HTML `<table>` (output truncated to 5 entries):

```{python:render}
import sys

print("| Module | Type |")
print("|--------|------|")
for name in sorted(sys.builtin_module_names)[:5]:
    print(f"| `{name}` | built-in |")
```

### Self-updating source with `:mirror:`

`python:render` accepts a `:mirror:` flag. On top of rendering live, a mirror block keeps a copy of its generated Markdown in the source `.md`, between two HTML-comment markers directly below the fence. The output stays reviewable in the raw file, in diffs, and on GitHub, which renders the mirrored Markdown even though it never executes the block. This revives the `docs_update.py` marker-region pattern with the generator inlined into the page: no separate regenerator script, and no drift.

Add `:mirror:` to a `python:render` fence:

````{code-block} markdown
```{python:render}
:mirror:
from click_extra.table import TableFormat, render_table

print(render_table(
    [["Lisbon", "12:00"], ["Denver", "05:00"]],
    headers=["City", "Local time"],
    table_format=TableFormat.GITHUB,
))
```
````

Running [`click-extra refresh-directives`](#keeping-the-tables-current) on the file inserts the mirrored region below the fence, and refreshes it in place on every later run:

````{code-block} markdown
```{python:render}
:mirror:
...
```

<!-- mirror -->

| City   | Local time |
| :----- | :--------- |
| Lisbon | 12:00      |
| Denver | 05:00      |

<!-- mirror-end -->
````

A few properties follow from the mirror being real Markdown:

- The mirrored region is the single rendered copy, so the directive emits nothing of its own in mirror mode: otherwise the table would render twice. Add `:show-source:` to also show the Python block above the region.
- Sphinx builds regenerate the region in memory before parsing the page, so the rendered HTML is always fresh, even when the committed region is stale. The build never writes to the source file: the committed copy is refreshed by `click-extra refresh-directives`, typically from the same automation that keeps `{matrix}` blocks current.
- The `<!-- mirror -->` … `<!-- mirror-end -->` pair follows the same marker grammar as the [`<!-- matrix … -->` regions](#matrix-directives), and a mirror example nested inside a longer code fence (like the ones on this page) is never executed or refreshed.
- The region is reformatted by `mdformat` like any other Markdown, so a mirror block must print `mdformat`-canonical Markdown. `render_table` in `GITHUB` mode already does; a hand-built table may be re-aligned by the formatter and then fight the generator.

`:mirror:` is scoped to `python:render` in a Markdown host, and shares the `click_extra_enable_exec_directives` opt-in with the rest of the executing directives.

<a name="mirror-src"></a>

(mirror-src)=

### Hiding the generator with `<!-- mirror-src -->`

A `:mirror:` fence renders live and mirrors its output into the source, but the generator fence itself stays visible: on GitHub or PyPI, which show the raw Markdown without running Sphinx, the reader sees the `python:render` code block above the table. When the output is the whole point (a table or diagram in `readme.md`) and the generator is just plumbing, the `<!-- mirror-src -->` comment form moves the generator into an HTML comment, so only its output renders.

The generator Python lives between an opening `<!-- mirror-src` line and a closing `-->`, each on its own line:

```{code-block} markdown
<!-- mirror-src
from click_extra.table import TableFormat, render_table

print(render_table(
    [["Lisbon", "12:00"], ["Denver", "05:00"]],
    headers=["City", "Local time"],
    table_format=TableFormat.GITHUB,
))
-->
```

Running [`click-extra refresh-directives`](#keeping-the-tables-current) executes the generator and writes its output just below the comment, closed by a `<!-- mirror-src-end -->` marker:

```{code-block} markdown
<!-- mirror-src
...
-->

| City   | Local time |
| :----- | :--------- |
| Lisbon | 12:00      |
| Denver | 05:00      |

<!-- mirror-src-end -->
```

Both markers are HTML comments, so GitHub, PyPI, and any plain Markdown renderer show only the generated table while the generator stays out of sight. Everything else matches the `:mirror:` fence: Sphinx regenerates the region in memory on each build so the rendered HTML is never stale, the committed copy is refreshed offline by `click-extra refresh-directives`, the region is reformatted by `mdformat` (so the generator must print `mdformat`-canonical Markdown), and an example nested inside a longer code fence (like the two above) is copied verbatim, never executed.

Choose between the two forms by what should be on the page: the `:mirror:` fence when the generator belongs there, like a docs example teaching `python:render` itself; the `<!-- mirror-src -->` comment when the page should read as its output alone, like a `readme.md` rendered on PyPI.

### Cross-format rendering

`python:render-myst` and `python:render-rst` let a host file embed content authored in the other markup. This page is MyST, but the following block prints reST and parses it as such:

```{python:render-rst}
print(".. note::")
print()
print("   A persimmon must be very ripe to eat raw.")
```

In an rST host, `python:render-myst` provides the symmetric path: print MyST and have it parsed as MyST regardless of the surrounding `.rst` file.

### Namespace persistence

Like `click:source` / `click:run`, the Python runner holds a per-document namespace, so consecutive blocks share imports and variables:

```{python:source}
from textwrap import dedent

GREETING = "hello, sphinx"
```

```{python:run}
print(dedent(GREETING).upper())
```

The `python:source` block ran silently to seed `dedent` and `GREETING`; the subsequent `python:run` referenced both.

### Shared options

`python:run` and the `python:render*` directives accept the same option spec as `click:run`. Defaults match: results shown, source hidden, so an inline `import` line in a `python:run` block runs silently and stays out of the rendered output.

| Option                              | Effect                                                                                    | Default |
| ----------------------------------- | ----------------------------------------------------------------------------------------- | ------- |
| `:show-source:` / `:hide-source:`   | Render the directive's source block, or omit it.                                          | hidden  |
| `:show-results:` / `:hide-results:` | Render the captured output block, or omit it.                                             | shown   |
| `:mirror:`                          | Keep a refreshable copy of the generated Markdown below the fence (`python:render` only). | off     |
| `:linenos:`                         | Display line numbers in both blocks.                                                      | off     |
| `:lineno-start:`                    | Starting line number when `:linenos:` is on. Applies to source.                           | 1       |
| `:emphasize-lines:`                 | Highlight lines in the source block. Syntax: `1,3-5`.                                     | none    |
| `:emphasize-result-lines:`          | Highlight lines in the result block. Same syntax as `:emphasize-lines:`.                  | none    |
| `:language:`                        | Override the Pygments lexer used to render the result block.                              | `text`  |
| `:caption:`                         | Set a caption on the rendered code block.                                                 | none    |
| `:name:`                            | Anchor name for cross-referencing.                                                        | none    |
| `:class:`                           | Extra CSS class on the rendered block.                                                    | none    |
| `:dedent:`                          | Strip N leading spaces from every line of the source.                                     | 0       |
| `:force:`                           | Suppress minor highlighting errors.                                                       | off     |

```{seealso}
Some related projects for build-time Python execution:

- [`sphinx-exec-code`](https://sphinx-exec-code.readthedocs.io/): single `exec_code` directive; supports external `:filename:` and inline `#hide:` / `#skip:` markers; fresh interpreter per block.
- [`jupyter-sphinx`](https://jupyter-sphinx.readthedocs.io/): runs Python in a real Jupyter kernel; rich outputs (matplotlib, widgets).
- [`MyST-NB`](https://myst-nb.readthedocs.io/): executes `.ipynb` and code-cell `.md`; `glue` / `eval` roles inject computed values into prose.
- [`sphinx-jinja`](https://github.com/tardyp/sphinx-jinja): Jinja2 templates with Python context, output parsed as reST/MyST. Closest analogue for the docs-as-code pattern without `exec`.
```

<a name="matrix-directives"></a>

(matrix-directives)=

## The `matrix` directive

The `matrix` directive renders a package's release compatibility matrix for a given axis. Unlike the `click:*` and `python:*` families, it runs a fixed generator rather than user-supplied Python, so it carries no execution surface and is registered without the `click_extra_enable_exec_directives` opt-in. Two axes are built in:

- `{matrix} python` renders the interpreter matrix (release ranges × Python versions).
- `{matrix} <distribution>` (like `{matrix} click`) renders a dependency matrix (release ranges × that dependency's versions).

The generated table lives **in the source**, kept current by the offline updater described below, so it shows up in the raw Markdown (and in pull-request diffs) and the HTML build needs no git access (it works on a shallow clone). There are two ways to write it, both refreshed by the same `refresh-directives` command:

- **A directive fence**, ```` ```{matrix} python ```` … ```` ``` ````, rendered by Sphinx. Simplest on a docs-only page, but GitHub shows the fenced block as a code block. An empty fence falls back to generating from the git tags at build time, so a freshly authored block renders before its first refresh.
- **A comment marker region**, `<!-- matrix python -->` … `<!-- matrix-end -->`, with the raw table between the markers. Being plain Markdown, it renders as a real table on **GitHub** and PyPI as well as in Sphinx. Options go in the start comment as `key=value` pairs and bare flags: `<!-- matrix click show-spec -->`. `install.md`'s tables use this form so they render everywhere.

The examples below use the directive fence; the marker form takes the same axis and options.

### The `python` axis

This project uses it for the [Python compatibility table in `install.md`](install.md#python-compatibility). You write the block with just its axis and options:

````{code-block} markdown
```{matrix} python
:package: click-extra
```
````

and the updater fills in the table below the options, regenerated from every `vMAJOR.MINOR.PATCH` tag (reading the declared Python support from the `Programming Language :: Python :: X.Y` classifiers in `pyproject.toml`, falling back to `requires-python`, Poetry's `python = "..."`, then `setup.py`'s `python_requires`). Consecutive releases that agree are grouped into one row, and a floor-only declaration is capped at the latest Python released while the range was current:

````{code-block} markdown
```{matrix} python
:package: click-extra

| `click-extra`       | Released   | `3.14` | `3.13` | `3.12` | `3.11` | `3.10` | `3.9` | `3.8` | `3.7` |
| :------------------ | :--------- | :----: | :----: | :----: | :----: | :----: | :---: | :---: | :---: |
| `6.2.x` → `8.x`     | 2025-11-04 |   ✅   |   ✅   |   ✅   |   ✅   |   ✅   |  ❌   |  ❌   |  ❌   |
| `6.0.x` → `6.1.x`   | 2025-10-08 |   ✅   |   ✅   |   ✅   |   ✅   |   ❌   |  ❌   |  ❌   |  ❌   |
| `5.0.x` → `6.0.x`   | 2025-05-13 |   –    |   ✅   |   ✅   |   ✅   |   ❌   |  ❌   |  ❌   |  ❌   |
| `4.11.x` → `4.15.x` | 2024-10-08 |   –    |   ✅   |   ✅   |   ✅   |   ✅   |  ❌   |  ❌   |  ❌   |
| `4.9.x` → `4.10.x`  | 2024-07-25 |   –    |   –    |   ✅   |   ✅   |   ✅   |  ✅   |  ❌   |  ❌   |
| `4.0.x` → `4.8.x`   | 2023-05-08 |   –    |   –    |   ✅   |   ✅   |   ✅   |  ✅   |  ✅   |  ❌   |
| `0.0.x` → `3.10.x`  | 2021-10-18 |   –    |   –    |   –    |   ✅   |   ✅   |  ✅   |  ✅   |  ✅   |
```
````

#### Three states, two sources

A release declares its Python support twice, and the two declarations answer different questions. The classifier list is what the project *claims* to have tested. `requires-python` is what an installer *enforces*: fall outside it and `pip` refuses to install, whatever the classifiers say. The matrix keeps them apart:

| Cell | Meaning                                                                                                 |
| :--: | :------------------------------------------------------------------------------------------------------ |
|  ✅  | Declared, via a `Programming Language :: Python :: X.Y` classifier.                                     |
|  ❌  | Ruled out by `requires-python`: below its floor, on or above its ceiling, or excluded by a `!=` clause. |
|  –   | Neither. The release never claimed that version, and nothing in its metadata stops you.                 |

The third state is what a two-state table has to lie about. When `4.9.0` shipped in July 2024 it declared `requires-python = ">= 3.9"` with classifiers up to `3.12`, and Python `3.13` did not exist yet. Marking that cell ❌ would assert an incompatibility nobody ever declared, so it renders `–` instead, while `3.8` stays ❌ because the `>= 3.9` floor genuinely rules it out.

The result reads as a staircase: ❌ fills the lower-left as the floor rises over the years, ✅ the middle band, and `–` the upper-right where the future had not happened yet.

### A dependency axis

`{matrix} <distribution>` tracks a runtime dependency instead. For each release range it reads that distribution's requirement specifier (PEP 621, Poetry, or `setup.py`) and marks ✅ / ❌ for each column version with [`packaging`](https://packaging.pypa.io). An extras bracket and an environment marker are both transparent: `tabulate[widechars]>=0.9` and `tomli>=2; python_version<'3.11'` each track the plain `>=` range. The distribution is matched on its [PEP 503](https://peps.python.org/pep-0503/) normalized name, looked up in the runtime dependencies then in those behind an extra. Development dependency groups ([PEP 735](https://peps.python.org/pep-0735/)) are skipped, since no installer resolves them for a consumer. Columns are auto-derived: a minor series stays a single `X.Y` column unless an open (`>=`) floor pins a specific patch, in which case it splits into `X.Y.0` plus that floor; the left edge is the version resolved in `uv.lock`. Add `:show-spec:` for a `Spec` column with each range's raw specifier, in the release's own spelling. Cells here stay two-valued: unlike Python, a dependency has no informational second declaration to disagree with its specifier, so there is nothing an undeclared cell could mean.

[Poetry's own range syntax](https://python-poetry.org/docs/dependency-specification/) is translated to PEP 440 before evaluation, since a project's older tags usually predate its move to PEP 621. Carets follow Poetry's rule of bumping the leftmost non-zero component, so `^1.2.3` caps at `2.0.0` while `^0.2.3` caps at `0.3.0` and `^0.0.3` at `0.0.4`: under a `0.` prefix every release may break, and a caret there covers far less than the major series. Tilde and wildcard ranges (`~1`, `~1.2`, `1.*`, `1.2.*`) translate the same way.

This project uses it for the [Click compatibility table](install.md#click-compatibility):

````{code-block} markdown
```{matrix} click
:package: click-extra
:show-spec:

| `click-extra`       | Released   | Spec      | `8.4.2` | `8.4.1` | `8.4.0` | `8.3.3` | `8.3.1` | `8.3.0` | `8.2` | `8.1` | `8.0` |
| :------------------ | :--------- | :-------- | :-----: | :-----: | :-----: | :-----: | :-----: | :-----: | :---: | :---: | :---: |
| `8.x`               | 2026-06-22 | `>=8.3.1` |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ❌    |  ❌   |  ❌   |  ❌   |
| `7.17.x` → `7.20.x` | 2026-05-25 | `>=8.4.1` |   ✅    |   ✅    |   ❌    |   ❌    |   ❌    |   ❌    |  ❌   |  ❌   |  ❌   |
| `7.15.x` → `7.16.x` | 2026-05-03 | `>=8.3.1` |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ❌    |  ❌   |  ❌   |  ❌   |
| `7.14.1`            | 2026-04-26 | `>=8.1`   |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |  ✅   |  ✅   |  ❌   |
| `7.14.0`            | 2026-04-24 | `>=8.3.3` |   ✅    |   ✅    |   ✅    |   ✅    |   ❌    |   ❌    |  ❌   |  ❌   |  ❌   |
| `7.0.x` → `7.13.x`  | 2025-11-17 | `>=8.3.1` |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ❌    |  ❌   |  ❌   |  ❌   |
| `6.x`               | 2025-09-25 | `>=8.3.0` |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |  ❌   |  ❌   |  ❌   |
| `5.x`               | 2025-05-13 | `~=8.2.0` |   ❌    |   ❌    |   ❌    |   ❌    |   ❌    |   ❌    |  ✅   |  ❌   |  ❌   |
| `4.9.x` → `4.15.x`  | 2024-07-25 | `~=8.1.4` |   ❌    |   ❌    |   ❌    |   ❌    |   ❌    |   ❌    |  ❌   |  ✅   |  ❌   |
| `1.7.x` → `4.8.x`   | 2022-03-31 | `^8.1.1`  |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |  ✅   |  ✅   |  ❌   |
| `0.0.x` → `1.6.x`   | 2021-10-18 | `^8.0.2`  |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |  ✅   |  ✅   |  ✅   |
```
````

### Options

| Option            | Effect                                                                           | Default                |
| ----------------- | -------------------------------------------------------------------------------- | ---------------------- |
| `:package:`       | Header column label, rendered in backticks.                                      | repository folder name |
| `:path:`          | Git working tree to walk, absolute or relative to the documented project's root. | project's git root     |
| `:version-floor:` | Drop release rows below this package version.                                    | none (all tags)        |
| `:tag-pattern:`   | Regex selecting release tags.                                                    | `^v\d+\.\d+\.\d+$`     |
| `:column-order:`  | Left-to-right ordering of the version columns: `newest-first` or `oldest-first`. | `newest-first`         |
| `:row-order:`     | Top-to-bottom ordering of the release rows: `newest-first` or `oldest-first`.    | `newest-first`         |
| `:python-floor:`  | (`python` axis) Drop Python `X.Y` columns below this version.                    | none (all columns)     |
| `:show-spec:`     | (dependency axis) Add a `Spec` column with each range's raw specifier.           | off                    |

The `:path:` option makes the directive reusable across repositories: point it at a sibling checkout to render another package's matrix.

### Keeping the tables current

The embedded tables are refreshed offline, formatter-style, by the `refresh-directives` command (which needs the sphinx extra):

```{code-block} shell-session
$ click-extra refresh-directives docs/
```

It walks the given Markdown files or directories, regenerates each matrix block's table (both the `{matrix}` directive fences and the `<!-- matrix … -->` marker regions) from that block's axis, options, and the project's git tags, and rewrites the block in place. Pass `--check` to write nothing and exit non-zero when a block is stale, so a CI job or pre-commit hook can fail on an out-of-date matrix. The same logic is importable as `click_extra.sphinx.matrix.update_matrix_blocks(paths, check=...)`. A block whose generation fails (missing git binary, non-repository `:path:`, no matching data) is left untouched, so a transient failure never wipes a good table. Examples nested inside longer code fences (like the ones on this page) are documented illustrations and are never refreshed.

The same command also refreshes the `python:render` `:mirror:` regions found in the same files, in both the visible [fence](#self-updating-source-with-mirror) and the invisible [`<!-- mirror-src -->` comment](#mirror-src) forms, by executing each block's Python (`click_extra.sphinx.python.update_mirror_blocks(paths, check=...)` is the importable form). One invocation therefore keeps every self-updating block of a documentation tree current, whatever its kind.

```{note}
Only the updater (and the empty-block fallback) needs the release tags, since it is the part that shells out to `git`. Run it wherever the full tag history is available. The HTML build renders the embedded table verbatim and needs no git access, so shallow clones and read-only build hosts render the matrix fine.
```

For content a directive cannot produce on its own, like a shared registry dumped into several files or an external generator's output, the same marker machinery is exposed as three primitives, importable from `click_extra.sphinx`:

- `marker_res(name)` builds the `(open, close)` regexes of a `<!-- name … -->` / `<!-- name-end -->` region, the grammar every self-updating marker shares.
- `replace_region(text, name, content)` swaps the body between those markers for `content`, keeping the markers so the region round-trips. It returns the text unchanged when either marker is absent, so it is safe to fan out over files that do not all carry the region.
- `update_blocks(paths, rewrite, check=...)` applies a `rewrite(text, path)` callback to every Markdown file under `paths`, writing back only the ones it changed (or, under `check`, returning the ones it would change). It is the read-rewrite-report loop behind both `update_matrix_blocks` and `update_mirror_blocks`.

`replace_region` is the counterpart to those two refreshers for content that originates outside the document rather than from an inline directive.
