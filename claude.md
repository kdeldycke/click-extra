# Development guide

Project-specific guidance for `click-extra`. The generic coding conventions load from the maintainer's machine configuration and are deliberately not committed here: a checkout carries only what is specific to this repository.

## click-extra house rules

What this repository does differently from, or in addition to, the generic conventions. Everything below is owned by this repository.

### Release coupling with repomatic

click-extra dogfoods repomatic in its own release pipeline, while repomatic depends on click-extra. Before releasing a change that renames or removes any symbol repomatic imports (the `click_extra.config` surface, or the CLI framework it builds on), release the fixed repomatic and bump the pin first. Otherwise the release publishes to PyPI but dies in repomatic's `metadata` step, leaving the version untagged with no GitHub release. See repomatic's `claude.md` ("click_extra is both a dependency and a release consumer") for the upstream side of this rule.

### Which workflows carry the cooldown literal

§ Where the window comes from puts `UV_EXCLUDE_NEWER` and `NPM_CONFIG_MIN_RELEASE_AGE` in a workflow-level `env:` block of every workflow. Here that means the two running a step of their own: `tests.yaml`, and `release.yaml` for its inline `publish-pypi` job. The thin callers that only `uses:` a repomatic reusable workflow carry no block, and adding one would be inert: a workflow-level `env:` does not cross into a reusable workflow, which carries its own upstream.

### Cooldown exemptions this repository claims

The inventory in § Documented exemptions is repomatic's own. Here it holds two entries, and a third is a bug until proven otherwise:

- **repomatic's own pin in `tests.yaml`.** The inline `'repomatic==X.Y.Z'` moves in lockstep with the `uses:` refs pointing at the same tag, so it routinely names a release published hours ago. It carries `--exclude-newer-package repomatic=P0D` beside the pin. Dropping that flag takes the entire Tests workflow down: `metadata` cannot resolve, and every job is `needs: metadata`, so the run reports failure while executing no test at all.
- **The `test-package-install` job.** Its subject *is* the freshly published click-extra, so a cooldown makes the question it exists to answer unanswerable, and it silently exercises the previous release instead. Scoped to that one job via a job-level `UV_EXCLUDE_NEWER: P0D`, which is what keeps it honest: it holds no secrets, inherits `permissions: {}`, and only runs `--version` on a throwaway runner.

When bumping the inline pin by hand, carry the exemption with it. `sync-workflow-pins` splices a missing one in, but only on a run that also moves the version, so a pin already sitting on the newest release never gets it backfilled.

### Package internals import from their source module

§ Imports tells consumers, docs and tests to import from the root package. Inside `click_extra` the rule inverts: import each symbol from its concrete source module (`from .types import EnumChoice`, `from .styling import Style`, `from click import echo`, `from click._utils import UNSET`), never from the root package (`from . import X`). Root-symbol imports read attributes off the partially-initialized package, which makes `__init__.py`'s import order load-bearing during package initialization. Importing a sibling module as a namespace (`from . import context`) is fine: Python resolves it through `sys.modules` without depending on the root's binding order.

That root `click_extra/__init__.py` is also the deliberate exception to [§ `__init__.py` files](#__init__py-files): it re-exports Click and Cloup symbols to serve as a drop-in replacement, which is the package's core design.

### What the MyST docstring converter cannot round-trip

`click_extra.sphinx.myst_docstrings` converts MyST docstrings back to reST at build time, and two constructs do not survive the trip: inline code containing `{` keeps double backticks, and a directive whose body holds a triple-backtick fence stays a reST directive. See the limitations section of `docs/myst-docstrings.md`.

When a trailing `# type: ignore[...]` comment would push a line past 88 characters, reformat the code block (break the expression across multiple lines) so the ignore comment fits, rather than letting the line run long.

### Test suite specifics

- **The suite is not `pytest-xdist`-safe.** Some tests depend on process-global state (logging configuration, default theme) and fail when run in isolation or reordered. Do not add `--numprocesses` or otherwise parallelize the suite without fixing that isolation first, which is why the `--numprocesses` entry in § Testing guidelines does not apply here.
- **`[tool.pytest].addopts` carries no coverage flag.** It holds only what applies everywhere (`--durations`, `--import-mode=importlib`), so a local `uv run pytest` stays fast, coverage-free and ungated. `--cov` and `--cov-report=term` are passed by the matrix `tests` job in `tests.yaml`, the only job that runs the whole suite and therefore the only one that can clear the floor. The `once-tests` job deliberately passes none: measuring its slice would gate nothing.
- Coverage is gated by the `[tool.coverage] report.fail_under` ratchet, with no external coverage service behind it.

### Benchmark and comparison table ordering

click-extra first, Click second, Cloup third, then remaining frameworks sorted by popularity (GitHub stars).

### `pyproject-fmt` panics on a version-opening indented comment

A comment whose text is indented two spaces or more and then opens on `N.N` (like `3.10`) reads as a Markdown ordered-list marker to `pyproject-fmt`, which panics and formats the whole file not at all. The bug is unfixed through `2.28.0`, the version repomatic ships. Prefix the version with a word (`Python 3.10`). The indentation that counts sits after the `#`, not before it. So a two-space-indented floor comment in `[project] dependencies` stays safe, while a continuation line indented under a `-` bullet in a comment block does not. A bare `3.` is safe too: the trigger needs a digit on each side of the dot. The crash surfaces as `PanicException: begin <= end`, and before repomatic's `rewrite_exit_code` check it was indistinguishable from a successful reformat: the autofix job stayed green for two months while formatting nothing.

### Synced rules this repository has not caught up with

Two managed sections above describe a state that does not hold here yet. Read them with this in mind, rather than as a description of the tree:

- **There is no `.claude/agents/` directory.** § Agent conventions opens on the three subagents repomatic ships. click-extra has never adopted the `subagents` component, so no agent definition lives in this repository.
- **The `UTF-8` spelling is not normalized.** § Testing guidelines asks for `UTF-8` over `utf-8` in every `encoding=` argument. This repository spells it lowercase almost everywhere and carries no conformance test pinning either form, so match the file you are editing until someone normalizes the tree in a single pass.

## Commands

### Testing

```shell-session
# Run all tests.
$ uv run pytest

# Run a single test file.
$ uv run pytest tests/test_color.py

# Run a specific test.
$ uv run pytest tests/test_color.py::test_function_name
```

### Building documentation

```shell-session
$ uv run sphinx-build -b html docs docs/_build
```

### Running the CLI

```shell-session
$ uv run -- click-extra --help
```

## Documentation: use `click:source` and `click:run` directives

When writing or updating Sphinx documentation in `docs/*.md`, **always prefer live CLI execution over static code blocks**. This project enforces a *documentation-as-code* and *test-as-documentation* philosophy: every usage example should be real, executed at build time, and verified with assertions.

### Directives

Use the two MyST directives provided by `click_extra.sphinx`:

- ```` ```{click:source} ```` — defines and displays a Click CLI's source code (syntax-highlighted as Python).
- ```` ```{click:run} ```` — invokes the CLI and renders the output as a terminal session. Code inside is executed at `sphinx-build` time.

### Basic pattern

First define the CLI with `click:source`, then invoke it with `click:run`:

````markdown
```{click:source}
from click_extra import echo, command, option

@command
@option("--name", help="The person to greet.")
def hello(name):
    """Greet someone."""
    echo(f"Hello, {name}!")
```

```{click:run}
result = invoke(hello, args=["--help"])
assert result.exit_code == 0
assert "Greet someone." in result.stdout
```

```{click:run}
result = invoke(hello, args=["--name", "World"])
assert result.exit_code == 0
assert "Hello, World!" in result.output
```
````

### Standalone `click:run`

You can import CLIs defined in the package source without a preceding `click:source`:

````markdown
```{click:run}
from click_extra.cli import demo
result = invoke(demo, args=["--version"])
assert result.exit_code == 0
```
````

### Inline assertions (mandatory)

Every `click:run` block **must** include assertions to verify the CLI output and exit code. This turns documentation into tests — if the CLI behavior changes, the Sphinx build fails, catching regressions early.

The `invoke()` function returns a result object with:

- `result.exit_code` — process exit status
- `result.stdout` — standard output
- `result.stderr` — standard error
- `result.output` — combined output

Common assertion patterns:

```python
# Exit code check (always include this).
assert result.exit_code == 0

# No errors on stderr.
assert not result.stderr

# String containment.
assert "--version" in result.stdout

# Exact output match.
assert result.output == "Hello, World!\n"

# Partial match with dedent for multiline.
from textwrap import dedent

assert result.stdout.startswith(
    dedent("""\
    Usage: hello [OPTIONS]
    """)
)

# Regex for variable content (timestamps, versions, etc.).
import re

assert re.fullmatch(
    r"Execution time: [0-9.]+ seconds\.\n",
    result.stdout,
)

# Output with ANSI color codes.
assert result.output == "Hello, \x1b[31mWorld\x1b[0m!\n"
```

### Display options

- `:hide-source:` on `click:source` — hides the CLI definition (useful when the source is not relevant to the reader).
- `:show-source:` on `click:run` — shows the invocation code alongside the terminal output.
- `:emphasize-lines:` — highlights specific lines in the source block. On `click:run`, `:emphasize-result-lines:` does the same for the captured output.

### Do not use static code blocks for CLI output

Never paste CLI output into a plain ```` ```shell-session ```` or ```` ```text ```` block. Always use `click:run` so the output is generated live and validated. This guarantees documentation stays in sync with the code.

### Example data in a directive

§ Example data governs the CLI a `click:source` block defines and everything a `click:run` block prints, the same as any other example: a domain-neutral subject, and never click-extra itself, its concepts or its metadata.

### Documentation prose style

Docs pages read as tutorials:

- **One concept per section.** Each section introduces one new concept and consumes only concepts from earlier sections. Group long pages into arcs under `##` headers.
- **Section names answer the reader's question.** Name them after the task or choice ("SVG or HTML", "Any command, any CLI"), not after clever phrasing ("Two formats, two surfaces").
- **Usage before rationale.** Lead with the command and what it does. Cut or compress implementation rationale and renderer-compatibility war stories into a single `{tip}`.
- **Viewer-behavior claims state the surface.** Say where a claim holds ("GitHub and PyPI render SVG as an image: its text is not selectable or searchable there"), never as a property of the format itself. A reader can select SVG text in a browser or Quick Look.
- **Renaming a heading repoints its inbound links.** Grep the docs tree and `readme.md` for `{file}.md#` before renaming any heading in `docs/*.md`, then rebuild and confirm the page adds no new warning.
