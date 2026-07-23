# Development guide

## Upstream conventions

This project reuses workflows from [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic) and follows the conventions defined in its `claude.md`. **Regularly consult `../repomatic/claude.md`** (or the [upstream repository](https://github.com/kdeldycke/repomatic/blob/main/claude.md)) to distill new knowledge, learnings, and best practices into this file. When repomatic's conventions evolve, update this `claude.md` to stay in sync — keeping project-specific sections intact.

**Contributing upstream:** If you spot inefficiencies, potential improvements, or opportunities for better adaptability in the reusable workflows, `repomatic` CLI, or its `claude.md`, propose changes upstream via a pull request or issue at [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic/issues). This benefits all downstream repositories.

**Release coupling:** click-extra dogfoods repomatic in its own release pipeline, while repomatic depends on click-extra. Before releasing a change that renames or removes any symbol repomatic imports (the `click_extra.config` surface, or the CLI framework it builds on), release the fixed repomatic and bump the pin first. Otherwise the release publishes to PyPI but dies in repomatic's `metadata` step, leaving the version untagged with no GitHub release. See repomatic's `claude.md` ("click_extra is both a dependency and a release consumer") for the upstream side of this rule.

## Commands

### Testing

```shell-session
# Run all tests.
$ uv run pytest

# Run a single test file.
$ uv run pytest tests/test_colorize.py

# Run a specific test.
$ uv run pytest tests/test_colorize.py::test_function_name
```

### Building documentation

```shell-session
$ uv run sphinx-build -b html docs docs/_build
```

### Running the CLI

```shell-session
$ uv run -- click-extra --help
```

## Documentation requirements

### Scope of `claude.md` vs `docs/`

- **`claude.md`**: Contributor and Claude-focused directives — code style, testing guidelines, design principles, and internal development guidance.
- **`docs/`**: User-facing Sphinx documentation — installation, usage, configuration, and API reference.

### Keeping `claude.md` lean

`claude.md` must contain only conventions, policies, rationale, and non-obvious rules that Claude cannot discover by reading the codebase. Actively remove:

- **Structural inventories** — project trees, module tables, workflow lists. Claude can discover these via `Glob`/`Read`.
- **Code examples that duplicate source files** — YAML snippets copied from workflows, Python patterns visible in every module. Reference the source file instead.
- **General programming knowledge** — standard Python idioms, well-known library usage, tool descriptions derivable from imports.
- **Implementation details readable from code** — what a function does, what a workflow's concurrency block looks like. Only the *rationale* for non-obvious choices belongs here.

### Changelog and documentation updates

When making changes:

- **`changelog.md`**: Add a bullet point describing **what** changed (new features, bug fixes, behavior changes), not **why**. Justifications and rationale belong in documentation (`docs/`) or code comments, not in the changelog.
  - **Order within a release section:** `**Breaking:**` entries first, then new features, other changes, bug fixes, and finally docs and tests.
  - **One sentence per entry, roughly 10-25 words.** Name the change, don't narrate it. A bullet past ~40 words is a smell (`lint-changelog` warns past the `changelog.bullet-word-threshold`).
  - **Do not mention:** mechanical test updates that accompany a change, short-shelf-life workarounds, or commentary on upstream issues.
- **`docs/`**: Update relevant sections when adding/modifying CLI commands, configuration options, or behavior. Installation examples use `uv` as the primary installer (`uv tool install` for CLI usage, `uv pip install` for the library); other installers may appear as secondary options.

### Knowledge placement

Each piece of knowledge has one canonical home, chosen by audience. Other locations get a brief pointer ("See `module.py` for rationale.").

| Audience              | Home                      | Content                                            |
| :-------------------- | :------------------------ | :------------------------------------------------- |
| End users             | `docs/`                   | Installation, configuration, usage, API reference. |
| Developers            | Python docstrings         | Design decisions, trade-offs, "why" explanations.  |
| Workflow maintainers  | YAML comments             | Brief "what" + pointer to Python code for "why."   |
| Bug reporters         | `.github/ISSUE_TEMPLATE/` | Reproduction steps, version commands.              |
| Contributors / Claude | `claude.md`               | Conventions, policies, non-obvious rules.          |

**YAML → Python distillation:** When workflow YAML files contain lengthy "why" explanations, migrate the rationale to Python module, class, or constant docstrings (using MyST admonition fences like ```` ```{note} ```` and ```` ```{warning} ````). Trim the YAML comment to a one-line "what" plus a pointer to the relevant module.

### Documenting code decisions

Document design decisions, trade-offs, and non-obvious implementation choices directly in the code using docstring admonitions (MyST fences like ```` ```{warning} ````, ```` ```{note} ````, ```` ```{caution} ````), inline comments, and module-level docstrings for constants that need context.

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
- `:emphasize-lines:` — highlights specific lines in the rendered block.

### Do not use static code blocks for CLI output

Never paste CLI output into a plain ```` ```shell-session ```` or ```` ```text ```` block. Always use `click:run` so the output is generated live and validated. This guarantees documentation stays in sync with the code.

### Example data

Example data everywhere (documentation, docstrings, comments, workflows, `click:source`/`click:run` blocks, test fixtures) must be domain-neutral: cities, weather, fruits, animals, recipes, or similar real-world subjects. Do not reference click-extra itself, software engineering concepts, package metadata, or any project-internal details. The reader should understand the example without knowing what click-extra is.

## File naming conventions

### Extensions: prefer long form

Use the longest, most explicit file extension available. For YAML, that means `.yaml` (not `.yml`). Apply the same principle to all extensions (e.g., `.html` not `.htm`, `.jpeg` not `.jpg`).

### Filenames: lowercase

Use lowercase filenames everywhere. Avoid shouting-case names like `FUNDING.YML` or `README.MD`.

### GitHub exceptions

GitHub silently ignores certain files unless they use the exact name it expects. These are the known hard constraints where you **cannot** use `.yaml` or lowercase:

| File                     | Required name                       | Why                                               |
| ------------------------ | ----------------------------------- | ------------------------------------------------- |
| Issue form templates     | `.github/ISSUE_TEMPLATE/*.yml`      | `.yaml` is not recognized for issue forms         |
| Issue template config    | `.github/ISSUE_TEMPLATE/config.yml` | `.yaml` not recognized                            |
| Funding config           | `.github/funding.yml`               | Only `.yml` documented; no evidence `.yaml` works |
| Release notes config     | `.github/release.yml`               | Only `.yml` documented                            |
| Issue template directory | `.github/ISSUE_TEMPLATE/`           | Must be uppercase; GitHub ignores lowercase       |
| Code owners              | `CODEOWNERS`                        | Must be uppercase; no extension                   |

Workflows (`.github/workflows/*.yaml`) and action metadata (`action.yaml`) officially support both `.yml` and `.yaml` — use `.yaml`.

## Code style

### Terminology and spelling

Use correct capitalization for proper nouns and trademarked names:

<!-- typos:off -->

- **PyPI** (not ~~PyPi~~) — the Python Package Index. The "I" is capitalized because it stands for "Index". See [PyPI trademark guidelines](https://pypi.org/trademarks/).
- **GitHub** (not ~~Github~~)
- **GitHub Actions** (not ~~Github Actions~~ or ~~GitHub actions~~)
- **JavaScript** (not ~~Javascript~~)
- **TypeScript** (not ~~Typescript~~)
- **macOS** (not ~~MacOS~~ or ~~macos~~)
- **iOS** (not ~~IOS~~ or ~~ios~~)

<!-- typos:on -->

### Version formatting

The version string is always bare (e.g., `1.2.3`). The `v` prefix is a **tag namespace** — it only appears when the reference is to a git tag or something derived from a tag (action ref, comparison URL, commit message). This aligns with PEP 440, PyPI, and semver conventions.

**Rules:**

1. **No `v` prefix on package versions.** Anywhere the version identifies the *package* (PyPI, changelog heading, CLI output, `pyproject.toml`), use the bare version: `1.2.3`.
2. **`v` prefix on tag references.** Anywhere the version identifies a *git tag* (comparison URLs, action refs, commit messages, PR titles), use `v1.2.3`.
3. **Always backtick-escape versions in prose.** Both `v1.2.3` (tag) and `1.2.3` (package) are identifiers, not natural language. In markdown and MyST docstrings alike, wrap them in single backticks: `` `v1.2.3` ``, `` `1.2.3` ``.
4. **Development versions** follow PEP 440: `1.2.3.dev0` with optional `+{short_sha}` local identifier.

### GitHub cross-references in commit messages and PRs

Never write `#N` (a literal `#` followed by a number) in commit messages, PR titles, or PR bodies unless N is an actual issue/PR number in the target repo. GitHub auto-links every `#N`, so positional refs like `test #1` render as misleading cross-references. Use plain numbers (`test 1`, `tests 14 and 15`), backtick-quote a slot identifier (`` test `1` ``), or rephrase (`the first test`).

### Linking to external repositories in Markdown

In Markdown (changelog, `readme.md`, `docs/`, issue and PR bodies), link to another repository using GitHub's reference slug as the link text, not the raw URL:

- Issue or PR: `[owner/repo#N](https://github.com/owner/repo/issues/N)`. Issues and PRs share one number space; pick `/issues/N` or `/pull/N` to match the real type (GitHub redirects either way).
- Commit: `[owner/repo@shortsha](https://github.com/owner/repo/commit/fullsha)`.
- Repository homepage: `[owner/repo](https://github.com/owner/repo)`.

GitHub autolinks the bare `owner/repo#N` form only inside conversations (issues, PRs, commit messages), never in committed files, so the explicit link is what renders the compact slug in a Markdown file. Same-repo references drop the slug: `[#N](…/issues/N)`.

### Comments and docstrings

- All comments in Python files must end with a period.
- Docstrings and comments use MyST markdown: single-backtick inline code, `` {role}`target` `` cross-references, `[text](url)` links, and backtick-fenced admonitions and code blocks. The `click_extra.sphinx.myst_docstrings` extension converts them back to reST at build time; Sphinx field lists (`:param:`, `:return:`, `:raises:`) keep their reST syntax. Constructs the build-time converter cannot round-trip stay in reST: inline code containing `{` keeps double backticks, and a directive whose body holds a triple-backtick fence stays a reST directive. See the limitations section of `docs/myst-docstrings.md`.
- **No Google-style docstring sections** (`Args:`, `Returns:`, `Raises:`) and no `sphinx.ext.napoleon`. Use Sphinx field lists: `:param name:`, `:return:` (not `:returns:`), `:raises ExceptionType:`.
- Documentation in `./docs/` uses MyST markdown format where possible. Fallback to reStructuredText if necessary.
- **Heading anchors:** use the natural auto-generated heading anchor for cross-references. Add an explicit MyST anchor (`(my-anchor)=`) only when the natural one is unavailable: duplicate headings, non-heading targets.
- Keep lines within 88 characters in Python files, including docstrings and comments (ruff default). When adding a trailing `# type: ignore[...]` comment would push a line past the limit, reformat the code block (break the expression across multiple lines) so that the ignore comment fits within 88 characters. Markdown files have no line-length limit — do not hard-wrap prose in markdown. Each sentence or logical clause should flow as a single long line; let the renderer handle wrapping.
- Titles in markdown use sentence case.
- **Dataclass field docs:** In dataclasses, document fields with attribute docstrings (a string literal immediately after the field declaration), not `:param:` entries in the class docstring. Attribute docstrings are co-located with the field they describe, recognized by Sphinx, and stay in sync when fields are added or reordered. The class docstring should contain only a summary of the class purpose.
- **CLI help text:** Click command docstrings serve double duty (Sphinx docs and terminal help). Click renders them as plain text, so avoid any markup (MyST or reST) in the prose sections that appear in `--help` output. Use plain text for command names, option names, file paths, and tool names. Markup (backticks, roles, admonitions) belongs in non-CLI docstrings only.

### `__init__.py` files

Keep `__init__.py` files minimal — avoid placing logic, constants, or business code in them. Acceptable content: license headers, package docstrings, `from __future__ import annotations`, `__version__`, and public API re-exports. The root `click_extra/__init__.py` is an intentional exception: it re-exports Click and Cloup symbols to serve as a drop-in replacement, which is the package's core design.

### Imports

- **Consumers, docs, and tests** import from the root package (`from click_extra import ...`) when possible.
- **Package internals** import each symbol from its concrete source module (`from .types import EnumChoice`, `from .styling import Style`, `from click import echo`, `from click._utils import UNSET`), never from the root package (`from . import X`). Root-symbol imports read attributes off the partially-initialized package, which makes `__init__.py`'s import order load-bearing during package initialization. Importing a sibling module as a namespace (`from . import context`) is fine: Python resolves it through `sys.modules` without depending on the root's binding order.
- Place imports at the top of the file, unless avoiding circular imports. **Never use local imports inside functions** — move them to the module level. Local imports hide dependencies, bypass ruff's import sorting, and make it harder to see what a module depends on.
- **Version-dependent imports** (e.g., `tomllib` fallback for Python 3.10) should be placed **after all normal imports** but **before the `TYPE_CHECKING` block**. This allows ruff to freely sort and organize the normal imports above without interference.

### `TYPE_CHECKING` block

Place a module-level `TYPE_CHECKING` block after all imports (including version-dependent conditional imports). Use `TYPE_CHECKING = False` (not `from typing import TYPE_CHECKING`) to avoid importing `typing` at runtime. See existing modules for the canonical pattern.

**Only add `TYPE_CHECKING = False` when there is a corresponding `if TYPE_CHECKING:` block.** If all type-checking imports are removed, remove the `TYPE_CHECKING = False` assignment too — a bare assignment with no consumer is dead code.

### Modern `typing` practices

Use modern equivalents from `collections.abc` and built-in types instead of `typing` imports. Use `X | Y` instead of `Union` and `X | None` instead of `Optional`. New modules should include `from __future__ import annotations` ([PEP 563](https://peps.python.org/pep-0563/)).

### Minimal inline type annotations

Omit type annotations on local variables, loop variables, and assignments when mypy can infer the type from the right-hand side. Add an explicit annotation only when mypy reports an error — e.g., empty collections needing a specific element type (`items: list[Package] = []`), `None` initializations where the intended type is ambiguous, or narrowing a union mypy cannot resolve. Function signatures are unaffected — always annotate parameters and return types.

### Python 3.10 compatibility

This project supports Python 3.10+. Unavailable syntax: multi-line f-string expressions (3.12+; split into concatenated strings instead), exception groups / `except*` (3.11+), `Self` type hint (3.11+; use `from typing_extensions import Self`).

### Command-line options

Always prefer long-form options over short-form for readability when invoking commands in scripts and workflow files. Use `--output` instead of `-o`, `--verbose` instead of `-v`, etc.

### YAML workflows

For single-line commands, use plain inline `run:`. For multi-line, use the folded block scalar (`>`) which joins lines with spaces — no backslash continuations needed. Use literal block scalar (`|`) only when preserved newlines are required (multi-statement scripts, heredocs).

YAML lines may run to 120 characters (yamllint's `line-length` is set to 120 by the upstream lint workflow): do not carry Python's 88-character limit into workflow files.

### uv flags in CI workflows

When invoking `uv` and `uvx` commands in GitHub Actions workflows:

- **`--no-progress`** on all CI commands (uv-level flag, placed before the subcommand). Progress bars render poorly in CI logs.
- **`--frozen`** on `uv run` commands (run-level flag, placed after `run`). Lockfile should be immutable in CI.
- **Flag placement:** `uv --no-progress run --frozen -- command` (not `uv run --no-progress`).
- **Exceptions:** Omit `--frozen` for `uvx` with pinned versions, `uv tool install`, CLI invocability tests, and local development examples.
- **Prefer explicit flags over environment variables** (`UV_NO_PROGRESS`, `UV_FROZEN`). Flags are self-documenting, visible in logs, avoid conflicts (e.g., `UV_FROZEN` vs `--locked`), and align with the long-form option principle.
- **Per-group `requires-python` in `[tool.uv]`:** When docs or other dependency groups require newer Python features, restrict specific groups with `dependency-groups.docs = { requires-python = ">= 3.14" }`. This prevents uv from installing incompatible dependencies when running on older Python versions.

## Testing guidelines

- Use `@pytest.mark.parametrize` when testing the same logic for multiple inputs. Prefer parametrize over copy-pasted test functions that differ only in their data — it deduplicates test logic, improves readability, and makes it trivial to add new cases.
- **Write conformance tests when fixing a class of bugs.** For a bug that is a *category* (not a one-off), add a generic test locking in the invariant: enumerate the whole population (via `@pytest.mark.parametrize` or a loop), assert the property uniformly on each member, and fail naming the violator.
- Keep test logic simple with straightforward asserts.
- Tests should be sorted logically and alphabetically where applicable.
- Test coverage is tracked with `pytest-cov` and reported to Codecov.
- Do not use classes for grouping tests. Write test functions as top-level module functions. Only use test classes when they provide shared fixtures, setup/teardown methods, or class-level state.
- **`@pytest.mark.once` for run-once tests.** Define a custom `once` marker (in `[tool.pytest].markers`) to tag tests that only need to run once — not across the full CI matrix. Typical candidates: CLI entry point invocability, plugin registration, package metadata checks. The main test matrix filters them out with `pytest -m "not once"`, while a dedicated `once-tests` job runs them on a single runner. This avoids wasting CI minutes on redundant cross-platform runs.
- **Coverage flags belong in workflow steps, not `[tool.pytest].addopts`.** `addopts` carries only the flags that apply everywhere (`--durations`, `--import-mode=importlib`), so local `uv run pytest` iterations stay fast and coverage-free. Coverage activation and report flags (`--cov`, `--cov-report=term`, `--cov-report=xml`) are passed in the `tests.yaml` `run:` steps, alongside CI-only artifact flags like `--junitxml=junit.xml`.
- **Coverage configuration belongs in `[tool.coverage]`.** Use the `[tool.coverage]` section in `pyproject.toml` for `run.branch`, `run.source`, and `report.precision` instead of `--cov=<source>`, `--cov-branch`, and `--cov-precision` flags.
- **The suite is not `pytest-xdist`-safe.** Some tests depend on process-global state (logging configuration, default theme) and fail when run in isolation or reordered. Do not add `--numprocesses` or otherwise parallelize the suite without fixing that isolation first.
- **Pass `encoding="UTF-8"` to `subprocess.run(..., text=True)` when output may contain non-ASCII bytes.** `text=True` alone uses the platform default (`cp1252` on Windows), raising `UnicodeDecodeError` only in Windows CI.
- **Pass `encoding="utf-8"` to every text-mode `open()`, `read_text()`, and `write_text()` in tests, same as production.** The same Windows cp1252 default applies to file I/O, and the failure hides until content grows a non-ASCII character (✅/❌ in test fixtures already bit this repo). When a change touches file I/O, run the suite once with `PYTHONWARNDEFAULTENCODING=1` ([PEP 597](https://peps.python.org/pep-0597/)) to surface every bare call at runtime, on any platform.

## Design principles

### Philosophy

1. Create something that works (to provide business value).
2. Create something that's beautiful (to lower maintenance costs).
3. Work on performance.

### Linting and formatting

Linting and formatting are automated via GitHub workflows. Developers don't need to run these manually during development, but are still expected to do best effort. Push your changes and the workflows will catch any issues.

### Ordering conventions

Keep definitions sorted for readability and to minimize merge conflicts:

- **Workflow jobs**: Ordered by execution dependency (upstream jobs first), then alphabetically within the same dependency level.
- **Python module-level constants and variables**: Alphabetically, unless there is a logical grouping or dependency order. Hard-coded domain constants should be placed at the top of the file, immediately after imports. These constants encode domain assertions and business rules — surfacing them early gives readers an immediate sense of the assumptions the module operates under.
- **YAML configuration keys**: Alphabetically within each mapping level.
- **Documentation lists and tables**: Alphabetically, unless a logical order (e.g., chronological in changelog) takes precedence.
- **Benchmark and comparison tables**: click-extra first, Click second, Cloup third, then remaining frameworks sorted by popularity (GitHub stars).

### Named constants

Do not inline named constants during refactors. If a constant has a name and a docstring, it exists for readability and grep-ability — preserve both. When moving code between modules, carry the constant with it rather than replacing it with a literal.

## Agent conventions

### Source of truth hierarchy

`claude.md` defines the rules. The codebase and GitHub (issues, PRs, CI logs) are what you measure against those rules. When they disagree, fix the code to match the rules. If the rules are wrong, fix `claude.md`.

### Common maintenance pitfalls

- **Documentation drift** is the most frequent issue. CLI output, version references, and workflow job descriptions in docs go stale after every release or refactor. Always verify docs against actual output after changes.
- **CI debugging starts from the URL.** When a workflow fails, fetch the run logs first (`gh run view --log-failed`). Do not guess at the cause. When the user points to a specific failure, diagnose that exact error — do not wander into adjacent or speculative issues.
- **Type-checking divergence.** Code that passes `mypy` locally may fail in CI where `--python-version 3.10` is used. Always consider the minimum supported Python version.
- **Simplify before adding.** When asked to improve something, first ask whether existing code or tools already cover the case. Remove dead code and unused abstractions before introducing new ones.
- **Generator/formatter ping-pong is recurrent.** Any code that writes a checked-in Markdown file competes with the autofix format-markdown job for the canonical layout. After touching such code, run the generator, then `uvx -- repomatic run mdformat -- {file}`, then the generator again, confirming `git diff` stays empty across all three states; if not, align the generator with mdformat. Checked-in JSON has the same trap with format-json: Biome indents JSON with tabs, so generated JSON must serialize with tab indents (`docs/assets/virustotal-scans.json`, written by repomatic's release pipeline, already does).
- **Trace to root cause before coding a fix.** Audit a bug's scope before writing the patch. If the same pattern appears in multiple places, fix it at the shared layer; if only one call site is affected, check whether the data is on the wrong code path before handling it where it lands.
- **Route through existing infrastructure, don't bypass it.** Before writing a new helper, check whether the codebase already has a mechanism for the same operation. A bug caused by data taking the wrong code path is better fixed by routing the data to the right path than by duplicating logic at the wrong one.
- **Angle-bracket placeholders in bash code blocks.** `mdformat-shfmt` runs `shfmt` on ```` ```bash ```` fences, and `shfmt` parses `<foo>` as input redirection and `>foo` as output redirection, then reorders the command. Use curly braces (`{foo}`) for placeholders in bash examples.
- **`repomatic run {tool} --check` is unreliable for tools with a post-process fixup.** `--check` can report drift the write path would reconcile (false positive) or pass on files it would still rewrite (false negative). To verify or gate formatting, run the write path and inspect `git diff`, never `--check`.

### Agent behavior policy

- Agents make fixes in the working tree only. Never commit, push, or create PRs unless explicitly asked.
- Prefer mechanical enforcement (tests, autofix jobs, linting checks) over prose rules. If a rule can be checked by code, it should be.
- Agent definitions should reference `CLAUDE.md` sections, not restate them.

### Skills

Skills in `.claude/skills/` are user-invocable only (`disable-model-invocation: true`) and follow agent conventions: lean definitions, no duplication with `CLAUDE.md`, reference sections instead of restating rules. They are synced from upstream via `uvx -- repomatic init skills`.
