# {octicon}`git-pull-request` Contribution guide

This page holds the commands and the rules for developing `click-extra` itself. The rules come from its [`AGENTS.md`](https://github.com/kdeldycke/click-extra/blob/main/AGENTS.md) file, which coding agents read too.

## Development commands

### Run the tests

```shell-session
# Run all tests, with the dependency set CI uses.
$ uv run --frozen --all-extras --group test -- pytest

# Run a single test file.
$ uv run --frozen --all-extras --group test -- pytest tests/test_color.py

# Run a specific test.
$ uv run --frozen --all-extras --group test -- pytest tests/test_color.py::test_function_name
```

Name `--all-extras --group test` every time, even though a bare `uv run pytest` usually works. Any other `uv run` variant in the same tree re-resolves the environment and can drop those packages: one `uv run --group docs` is enough to make the next bare `pytest` report `fixture 'httpserver' not found` and error 36 configuration tests, which reads as a regression rather than a missing dependency group.

### Build the documentation

```shell-session
$ uv run --frozen --all-extras --group test --group docs -- sphinx-build -b html --fail-on-warning docs docs/_build
```

Name all three of `--all-extras`, `--group test` and `--group docs`: `docs` is not a default group, so a run without it dies in `conf.py` on a missing `sphinxcontrib.mermaid`, and a run naming only `--group docs` drops the test packages from the shared environment, which breaks the next test run as shown above.

`--fail-on-warning` matches CI, where `[tool.repomatic] sphinx.fail-on-warning` fails the build on any warning. A warning that is unavoidable goes to `suppress_warnings` or `nitpick_ignore` in `docs/conf.py`, with a comment saying why.

A local build rewrites a committed capture in `docs/assets/` only when its bytes change, as they do for output that varies by machine. The `@generated` stamp names no release, so a version bump does not restamp them. Unless refreshing them is the task, restore them with `git checkout -- docs/assets` before staging.

### Run the CLI

```shell-session
$ uv run -- click-extra --help
```

## `AGENTS.md` file

```{include} ../AGENTS.md
:start-line: 2
```
