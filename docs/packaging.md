# {octicon}`package-dependents` Downstream packaging

This page is for distribution packagers building `click-extra` from source, either a PyPI sdist or a Git tag. To install it on your own system, use `uv pip install click-extra` or your distribution's package.

## Building

The wheel is built with [`uv_build`](https://docs.astral.sh/uv/), declared as the `[build-system]` backend. Distributions that do not yet package `uv-build` can fall back to `setuptools`. The `[tool.setuptools]` table is a compatibility shim for that case: it declares `click_extra`'s bundled data files (`themes.toml` and `py.typed`) as `package-data` so a `setuptools.build_meta` build ships them, which `setuptools` otherwise drops when it installs only `*.py`. `uv_build` ignores the table entirely.

## Test suite

Since `click-extra` > `8.6.0`, the PyPI sdist ships `tests/`, `docs/` and the `.github/` files the tests read, so the suite runs straight from the sdist. Earlier releases shipped no tests; those builds must start from [a Git tag tarball](https://github.com/kdeldycke/click-extra/tags) instead.

A plain `pytest` run is friendly to a hermetic build sandbox:

- **Network tests are marked.** Exclude them with `-m "not network"`: the build sandbox has no outbound network.
- **Configuration-discovery tests are `HOME`-independent.** The `runner` fixture pins `HOME` (and its platform equivalents) to an isolated directory, so the handful of tests asserting on the config-search debug output stay deterministic even where `HOME=/homeless-shelter` (Guix, Nixpkgs).
- **The MkDocs tests self-skip when their extras are missing.** `tests/mkdocs/` needs the MkDocs documentation extras (`mkdocs`, `mkdocs-click`, `pymdown-extensions`); `tests/mkdocs/conftest.py` skips the whole tree through `collect_ignore_glob` when any of them is absent, so no `--ignore=tests/mkdocs` is needed.
- **The Sphinx tests self-skip too**, when `sphinx` or `myst-parser` is absent.

The recommended invocation for a hermetic builder is therefore:

```{code-block} shell-session
$ pytest -m "not network"
```

Several test modules import optional libraries at collection time (`hjson`, `jsonschema`, `pygments`, `tomlkit`, `xmltodict`, and others) to exercise the matching features. Install them to run the full suite, as the [project's own CI](https://github.com/kdeldycke/click-extra/actions) does.

## Test helpers for downstream projects

`click_extra.pytest` (installed with the `[pytest]` extra) provides fixtures reused by projects built on click-extra, notably the `runner`/`invoke` fixtures that pin `HOME`, and `assert_output_regex`. Platform-skip decorators such as `@skip_hermetic_build` come from [`extra-platforms`](https://kdeldycke.github.io/extra-platforms/pytest.html).
