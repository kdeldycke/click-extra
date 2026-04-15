# Development guide

## Upstream conventions

This project reuses workflows from [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic) and follows the conventions defined in its `claude.md`. **Regularly consult `../repomatic/claude.md`** (or the [upstream repository](https://github.com/kdeldycke/repomatic/blob/main/claude.md)) to distill new knowledge, learnings, and best practices into this file. When repomatic's conventions evolve, update this `claude.md` to stay in sync — keeping project-specific sections intact.

**Contributing upstream:** If you spot inefficiencies, potential improvements, or opportunities for better adaptability in the reusable workflows, `repomatic` CLI, or its `claude.md`, propose changes upstream via a pull request or issue at [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic/issues). This benefits all downstream repositories.

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
$ uv run sphinx-build -b html docs docs/html
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

- **`changelog.md`**: Add a bullet point describing **what** changed (new features, bug fixes, behavior changes), not **why**. Keep entries concise and actionable. Justifications and rationale belong in documentation (`docs/`) or code comments, not in the changelog.
- **`docs/`**: Update relevant sections when adding/modifying CLI commands, configuration options, or behavior.

### Knowledge placement

Each piece of knowledge has one canonical home, chosen by audience. Other locations get a brief pointer ("See `module.py` for rationale.").

| Audience              | Home                      | Content                                            |
| :-------------------- | :------------------------ | :------------------------------------------------- |
| End users             | `docs/`                   | Installation, configuration, usage, API reference. |
| Developers            | Python docstrings         | Design decisions, trade-offs, "why" explanations.  |
| Workflow maintainers  | YAML comments             | Brief "what" + pointer to Python code for "why."   |
| Bug reporters         | `.github/ISSUE_TEMPLATE/` | Reproduction steps, version commands.              |
| Contributors / Claude | `claude.md`               | Conventions, policies, non-obvious rules.          |

**YAML → Python distillation:** When workflow YAML files contain lengthy "why" explanations, migrate the rationale to Python module, class, or constant docstrings (using reST admonitions like `.. note::` and `.. warning::`). Trim the YAML comment to a one-line "what" plus a pointer to the relevant module.

### Documenting code decisions

Document design decisions, trade-offs, and non-obvious implementation choices directly in the code using docstring admonitions (reST `.. warning::`, `.. note::`, `.. caution::`), inline comments, and module-level docstrings for constants that need context.

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
3. **Always backtick-escape versions in prose.** Both `v1.2.3` (tag) and `1.2.3` (package) are identifiers, not natural language. In markdown, wrap them in backticks: `` `v1.2.3` ``, `` `1.2.3` ``. In reST docstrings, use double backticks: ``` ``v1.2.3`` ```.
4. **Development versions** follow PEP 440: `1.2.3.dev0` with optional `+{short_sha}` local identifier.

### Comments and docstrings

- All comments in Python files must end with a period.
- Docstrings use reStructuredText format (vanilla style, not Google/NumPy).
- Documentation in `./docs/` uses MyST markdown format where possible. Fallback to reStructuredText if necessary.
- Keep lines within 88 characters in Python files, including docstrings and comments (ruff default). When adding a trailing `# type: ignore[...]` comment would push a line past the limit, reformat the code block (break the expression across multiple lines) so that the ignore comment fits within 88 characters. Markdown files have no line-length limit — do not hard-wrap prose in markdown. Each sentence or logical clause should flow as a single long line; let the renderer handle wrapping.
- Titles in markdown use sentence case.
- **Dataclass field docs:** In dataclasses, document fields with attribute docstrings (a string literal immediately after the field declaration), not `:param:` entries in the class docstring. Attribute docstrings are co-located with the field they describe, recognized by Sphinx, and stay in sync when fields are added or reordered. The class docstring should contain only a summary of the class purpose.
- **CLI help text:** Click command docstrings serve double duty (Sphinx docs and terminal help). Click renders them as plain text, so avoid reST markup in the prose sections that appear in `--help` output. Use plain text for command names, option names, file paths, and tool names. reST markup (double backticks, `:param:`, admonitions) belongs in non-CLI docstrings only.

### `__init__.py` files

Keep `__init__.py` files minimal — avoid placing logic, constants, or business code in them. Acceptable content: license headers, package docstrings, `from __future__ import annotations`, `__version__`, and public API re-exports. The root `click_extra/__init__.py` is an intentional exception: it re-exports Click and Cloup symbols to serve as a drop-in replacement, which is the package's core design.

### Imports

- Import from the root package (`from click_extra import ...`) when possible.
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
- Keep test logic simple with straightforward asserts.
- Tests should be sorted logically and alphabetically where applicable.
- Test coverage is tracked with `pytest-cov` and reported to Codecov.
- Do not use classes for grouping tests. Write test functions as top-level module functions. Only use test classes when they provide shared fixtures, setup/teardown methods, or class-level state.
- **`@pytest.mark.once` for run-once tests.** Define a custom `once` marker (in `[tool.pytest].markers`) to tag tests that only need to run once — not across the full CI matrix. Typical candidates: CLI entry point invocability, plugin registration, package metadata checks. The main test matrix filters them out with `pytest -m "not once"`, while a dedicated `once-tests` job runs them on a single runner. This avoids wasting CI minutes on redundant cross-platform runs.
- **CI-only pytest flags belong in workflow steps, not `[tool.pytest].addopts`.** Flags like `--cov-report=xml`, `--junitxml=junit.xml`, and `--override-ini=junit_family=legacy` produce artifacts only needed in CI. Placing them in `addopts` pollutes local test runs with `junit.xml` files and XML coverage reports. Keep `addopts` for flags that apply everywhere (`--cov`, `--cov-report=term`, `--durations`, `--numprocesses`). Pass CI-specific flags in the workflow `run:` step.
- **Coverage configuration belongs in `[tool.coverage]`.** Use the `[tool.coverage]` section in `pyproject.toml` for `run.branch`, `run.source`, and `report.precision` instead of `--cov=<source>`, `--cov-branch`, and `--cov-precision` flags in `addopts`. This keeps coverage configuration canonical and `addopts` clean. The pytest `addopts` should only contain `--cov` (to activate the plugin) and `--cov-report=term` (for local feedback).

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

### Agent behavior policy

- Agents make fixes in the working tree only. Never commit, push, or create PRs unless explicitly asked.
- Prefer mechanical enforcement (tests, autofix jobs, linting checks) over prose rules. If a rule can be checked by code, it should be.
- Agent definitions should reference `CLAUDE.md` sections, not restate them.

### Skills

Skills in `.claude/skills/` are user-invocable only (`disable-model-invocation: true`) and follow agent conventions: lean definitions, no duplication with `CLAUDE.md`, reference sections instead of restating rules. They are synced from upstream via `uvx -- repomatic sync-skills`.
