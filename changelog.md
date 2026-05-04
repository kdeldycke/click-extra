# Changelog

## [`7.15.2.dev0` (unreleased)](https://github.com/kdeldycke/click-extra/compare/v7.15.1...main)

> [!WARNING]
> This version is **not released yet** and is under active development.

## [`7.15.1` (2026-05-04)](https://github.com/kdeldycke/click-extra/compare/v7.15.0...v7.15.1)

- Flip the `AnsiColorLexer.true_color` default to `True`. 24-bit RGB sequences (`SGR 38;2;r;g;b` and `48;2;r;g;b`) now render with their exact hex values via inline `style="color: #rrggbb"` spans by default — including in Sphinx, MkDocs, and `pygmentize` consumers, which can't pass kwargs to lexer constructors. The previous lossy 256-color quantization is still available as `AnsiColorLexer(true_color=False)`. **Behavior change for downstream HTML output:** documents that previously rendered 24-bit codes through `Ansi-C{n}` palette CSS classes now use inline RGB styles. Stylesheet contents are unchanged.
- Add `:emphasize-result-lines:` option to the `click:run` and `python:run` Sphinx directives. The standard `:emphasize-lines:` now applies to the source block only; pass `:emphasize-result-lines:` (same syntax: `1,3-5`) to highlight specific lines in the captured output. Lets authors call out a key call-site in the source and a key line in the output independently.

## [`7.15.0` (2026-05-03)](https://github.com/kdeldycke/click-extra/compare/v7.14.1...v7.15.0)

- Add opt-in 24-bit true-color rendering to the ANSI Pygments stack. Pass `true_color=True` to `AnsiColorLexer`, `AnsiFilter`, or any session lexer (like `get_lexer_by_name("ansi-shell-session", true_color=True)`) to preserve `SGR 38;2;r;g;b` and `48;2;r;g;b` sequences as `Token.Ansi.FG_{rrggbb}` / `Token.Ansi.BG_{rrggbb}` tokens instead of quantizing them to the 256-color palette. `AnsiHtmlFormatter` renders those tokens as inline `style="color: #rrggbb"` / `style="background-color: #rrggbb"` spans. The default behavior (256-color quantization) is unchanged.
- New `click_extra.theme` module centralizes all theme machinery: `HelpExtraTheme`, `default_theme`, `nocolor_theme`, `OK`, `KO`, `ThemeOption`, `theme_option` decorator, `theme_registry`, and `register_theme()`. Every click-extra command now accepts `--theme [dark|light]`; downstream consumers can extend the choice list via `register_theme()`. The active theme for a CLI run is stored in `ctx.meta[context.THEME]` by `ThemeOption` and retrieved via `get_current_theme()`, so back-to-back invocations in the same process (Sphinx builds, test runners, REPLs) no longer leak `--theme` choices into each other. The `wrap` subcommand reads the theme from the parent group's context rather than carrying its own `--theme`. Adds a corresponding `docs/theme.md` user guide. **Breaking:** downstream code importing theme symbols directly from `click_extra.colorize` must update to `click_extra.theme`; the canonical `from click_extra import HelpExtraTheme` path is unaffected.
- New `click_extra.context` module consolidates `ExtraContext` (moved from `click_extra.commands`) and a documented registry of every `ctx.meta` key Click Extra writes or reads: `RAW_ARGS`, `CONF_SOURCE`, `CONF_FULL`, `TOOL_CONFIG`, `VERBOSITY_LEVEL`, `VERBOSITY`, `VERBOSE`, `START_TIME`, `JOBS`, `TABLE_FORMAT`, `SORT_BY`, and `THEME`. The `get()` and `set()` helpers replace scattered `ctx.meta.get(key, ...)` calls throughout the codebase. Replaces the former `click_extra.ctx_meta` module. **Breaking:** `from click_extra.commands import ExtraContext` and `from click_extra import ctx_meta` must be updated to `from click_extra.context import ExtraContext` and `from click_extra import context` respectively; the canonical `from click_extra import ExtraContext` path is unaffected.
- Add `python:source`, `python:run`, `python:render`, `python:render-myst`, and `python:render-rst` Sphinx directives under a new `python` domain in `click_extra.sphinx`. They mirror `click:source` / `click:run` for arbitrary Python (no Click CLI required): `python:source` runs silently and shows source, `python:run` captures `stdout` and renders it in a code block (default lexer `text`, override via `:language:`), and the `render` family parses the captured `stdout` as live document content: generated tables, headings, admonitions, and cross-references become first-class document nodes rather than a code block. `python:render` uses the host file's parser; `python:render-myst` forces MyST parsing (so a `.rst` host can embed MyST-generated content); `python:render-rst` forces reST parsing (so a `.md` host can embed reST-generated content). The Python and Click runners hold independent per-document namespaces. The render family replaces the `docs_update.py` regenerator + marker-region pattern many downstream projects use; the same logic now lives inline in the doc page and runs at build time, so the rendered HTML is always current.
- **Breaking change:** the `click:*` and `python:*` Sphinx directives are now **disabled by default**. Both families execute arbitrary Python at build time with full Sphinx-process privileges (filesystem, network, environment secrets), so registering them on every project that imports `click_extra.sphinx` silently expanded the attack surface of every consumer. To re-enable, add `click_extra_enable_exec_directives = True` to `conf.py`. Always-on features (the ANSI-capable Pygments HTML formatter and the GitHub-alerts → MyST/reST converter) are unaffected. Without the flag, `click:source`, `click:run`, `python:source`, `python:run`, `python:render`, `python:render-myst`, and `python:render-rst` are not registered and any reference to them produces an "Unknown directive" warning at build time.
- Tighten Click floor from `8.1` to `8.3.1`. The relaxation in `7.14.1` went further than needed; `8.3.1` is the minimum that ships the parameter-name fix we depend on.
- Move `--cov` and `--cov-report=term` from `pyproject.toml` `[tool.pytest].addopts` into the CI workflow. Removes `pytest-cov` as an unconditional test-time dependency for downstream packagers.
- Move `tests/test_mkdocs.py` into `tests/mkdocs/`. Downstream packagers can skip it with `--ignore=tests/mkdocs` without pulling in `mkdocs-click`.
- Loosen `default_debug_*_version_details` regex helpers to also match `None` for `git_long_hash`, `git_short_hash`, and `git_date`. Lets debug-output tests pass when the source tree has no `.git` directory (Guix `git-fetch`, sdist installs).
- Mark `test_ansi_lexers_candidates` with the new `network` marker. Sandboxed builds can exclude it with `pytest -m "not network"`.
- Make `tests/test_table.py` tolerate tabulate `<0.10`: branch the asciidoc fixture on the cell-alignment marker (`<8` vs `8<`) and skip the `colon-grid` parametrize case when the format is aliased to `grid`.

## [`7.14.1` (2026-04-26)](https://github.com/kdeldycke/click-extra/compare/v7.14.0...v7.14.1)

> [!NOTE]
> `7.14.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.14.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.14.1).

- Relax Click requirement back to `8.1`. Replace `ParameterSource` ordered comparisons in `ConfigOption` with explicit set membership so the code works on both the regular `Enum` (Click `8.1`/`8.2`) and the `IntEnum` (Click `8.3`+).
- Relax tabulate requirement back to `0.9`. Backport the `colon_grid` format by aliasing it to `grid` at module load when tabulate `< 0.10` is installed.

## [`7.14.0` (2026-04-24)](https://github.com/kdeldycke/click-extra/compare/v7.13.0...v7.14.0)

> [!NOTE]
> `7.14.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.14.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.14.0).

- Add `wrap` subcommand: `click-extra wrap SCRIPT [ARGS]...` applies help colorization to any installed Click CLI without modifying its source. Supports `--theme` option and `[tool.click-extra.wrap.<script>]` config sections for persistent CLI defaults. Resolves SCRIPT via console_scripts entry points, `module:function` notation, `.py` file paths, or bare module names. Unknown subcommand names fall through to `wrap` automatically, so `click-extra flask --help` works without typing `wrap`. `run` is kept as an alias.
- Add `show-params` subcommand: `click-extra show-params SCRIPT [SUBCOMMAND]...` introspects any external Click CLI's parameters and displays them as a table. Supports all `--table-format` renderings. Drills into nested subcommands. Auto-discovers the Click command when the entry point is a wrapper function.
- Style `Spec.` column with `option` theme (cyan) and `Python type` with `metavar` theme (cyan dim) in both `--show-params` and `show-params`, matching help-screen conventions.
- Add `get_param_spec()` and `format_param_row()` as public API in `click_extra.parameters`. `get_param_spec()` extracts option-spec strings and handles hidden-param unhiding. `format_param_row()` is the shared cell renderer for both `--show-params` and `show-params` tables.
- Make `ParamStructure.get_param_type()` a `@staticmethod`. Returns `str` for unrecognised custom types instead of raising `ValueError`.
- Replace `render-matrix` subcommand with individual `colors`, `styles`, `palette`, `8color`, and `gradient` subcommands grouped under a "Demo" section. Remove the `click-extra-demo` entry point.
- Move Sphinx tests into `tests/sphinx/`. Downstream packagers can skip them with `--ignore=tests/sphinx` without pulling in Sphinx dependencies.
- Bump Click requirement to `8.3.3`. Simplify `ParameterSource` comparisons in `ConfigOption` using the new `IntEnum` ordering.

## [`7.13.0` (2026-04-16)](https://github.com/kdeldycke/click-extra/compare/v7.12.0...v7.13.0)

> [!NOTE]
> `7.13.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.13.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.13.0).

- Add MkDocs plugin for ANSI color rendering in code blocks. Install with `pip install click-extra[mkdocs]`, then add `click-extra` to your `mkdocs.yml` plugins list. Patches `pymdownx.highlight` formatters to use `AnsiHtmlFormatter`.
- Automatically patch `mkdocs-click` code blocks to use the `ansi-output` lexer when the `click-extra` MkDocs plugin is enabled. CLI help text with ANSI escape codes now renders with colors instead of garbled `[1m`/`[0m` sequences.
- Fix API reference sections rendering as raw RST markup instead of formatted documentation. Wrap all `automodule` and `autoclasstree` directives in `eval-rst` blocks to force RST parsing, working around MyST-Parser's `MockState.nested_parse()` treating autodoc output as Markdown.
- Add OSC 8 hyperlink support to `AnsiColorLexer` and `AnsiHtmlFormatter`. Terminal hyperlinks in CLI output are rendered as clickable HTML `<a>` tags in Sphinx documentation. Other OSC sequences are now fully stripped instead of leaking their payload as visible text.

## [`7.12.0` (2026-04-16)](https://github.com/kdeldycke/click-extra/compare/v7.11.0...v7.12.0)

> [!NOTE]
> `7.12.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.12.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.12.0).

- Add `JobsOption` and `jobs_option` decorator for controlling parallel execution. Defaults to available CPUs minus one. Warns when the requested count is clamped or exceeds available cores.
- Improve error messages for single-dash multi-character tokens. When Click splits `-dbgwrong` character by character and reports "No such option: -d", `ExtraCommand` now catches that and re-raises with the full token and close-match suggestions.
- Replace `pygments-ansi-color` dependency with inline ANSI SGR parser. Adds support for italic (SGR 3), underline (SGR 4), reverse video (SGR 7), strikethrough (SGR 9), and 24-bit RGB colors (quantized to the 256-color palette). The token namespace changes from `Token.Color.*`/`Token.C.*` to a unified `Token.Ansi.*`, and CSS classes change accordingly (from `.-Color-*`/`.-C-*` to `.-Ansi-*`). Fixes bold, italic, underline, and other text attributes not rendering in Sphinx/Furo: Furo's dark-mode CSS generator injected `color: #D0D0D0` fallbacks for every Pygments style dict entry, overriding foreground color rules on compound tokens. All SGR attribute CSS is now injected separately via `EXTRA_ANSI_CSS`.
- Rename `lexer_map` to `LEXER_MAP`.
- Change `render-matrix --matrix=<choice>` option to a positional argument: `render-matrix <choice>`. Add `palette`, `8color`, and `gradient` choices. `palette` shows a compact 256-color indexed swatch. `8color` shows all standard foreground/background combinations. `gradient` renders 24-bit RGB gradients alongside their 256-color quantized equivalents to visualize the palette resolution limits.
- Fix `render-matrix colors` background color column headers: the color swatches were styled as foreground instead of background colors.

## [`7.11.0` (2026-04-13)](https://github.com/kdeldycke/click-extra/compare/v7.10.1...v7.11.0)

> [!NOTE]
> `7.11.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.11.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.11.0).

- Add `serialize_data()` and `print_data()` functions for serializing arbitrary nested Python data (not just tabular rows) to JSON, HJSON, TOML, YAML, and XML. Complements the existing `render_table()`/`print_table()` pair.
- Add `sort_key` parameter to `render_table()` and `print_table()` for pre-render row sorting.
- Catch `ImportError` from missing optional dependencies in `print_table()` and `print_data()`, producing a clean one-line error instead of a traceback. The `print_data()` `package` parameter lets downstream projects customize install instructions.
- Add `print_sorted_table()` and `SortByOption` for column-based table sorting. `SortByOption` generates a `--sort-by` CLI option from column definitions and auto-wires `ctx.print_table` to the sorted variant.
- Add auto-injected `help` subcommand to `ExtraGroup`. `mycli help` shows group help, `mycli help subcommand` shows that subcommand's help (with nested group resolution). `mycli help --search term` searches all subcommands for matching options or descriptions. Disable with `help_command=False`.
- Relax `ParamStructure._recurse_cmd` to skip subcommands whose name collides with a top-level parameter (e.g. the `help` subcommand vs Click's `--help` option) instead of raising.
- Expose `HelpKeywords` dataclass and `collect_keywords()` as public API for extending help screen highlighting. `collect_keywords()` (renamed from the private `_collect_keywords()`) can be overridden to customize keyword collection.
- Add `extra_keywords` and `excluded_keywords` parameters to `ExtraCommand` and `ExtraGroup`. `extra_keywords` injects additional strings for highlighting; `excluded_keywords` suppresses highlighting of specific strings. Both accept a `HelpKeywords` instance.
- Switch deprecated-message highlighting from pre-collected keyword sets to a case-insensitive regex. Manually-added markers like `(Deprecated)` or `(deprecated: reason)` in help strings are now styled alongside Click-native `(DEPRECATED)` markers.
- Style individual choices inside their own metavar (`[json|csv|xml]`) as structural elements. Excluded choices and `cross_ref_highlight=False` only suppress free-text highlighting; the metavar itself is always styled.
- Propagate `excluded_keywords` from parent groups to subcommands. Parent exclusions are merged with child exclusions so that choices excluded at the group level are not styled in subcommand descriptions.
- Fix command aliases not being highlighted in help screens. Aliases rendered by Cloup inside parenthetical groups (like `backup (save, freeze)`) were not matched by the subcommand highlighting regex, which only recognized 2-space-indented names.
- Fix choice cross-reference highlighting bleeding into bracket fields. When a default value contained a choice keyword (e.g. `outline` in `rounded-outline`), the choice style would override the default value style. Bracket fields are now placeholder-protected before cross-reference passes run.
- Fix parent-context choice collection always normalizing (lowercasing) case-insensitive choices, ignoring custom metavars. Parent choices with a custom metavar now preserve original case, matching the behavior already applied to the current command's parameters.

## [`7.10.1` (2026-04-07)](https://github.com/kdeldycke/click-extra/compare/v7.10.0...v7.10.1)

> [!NOTE]
> `7.10.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.10.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.10.1).

- Fix `pipe` and `github` table formats to produce mdformat-compatible separator rows, preventing a formatting cycle between tabulate and mdformat.
- Replace hardcoded test matrix with `repomatic metadata`-managed matrix; OS, Python, and stability axes are now computed dynamically, with custom Click/Cloup version axes via `[tool.repomatic.test-matrix]`. PRs get a reduced matrix to save CI minutes. Drops Python `3.15t` (free-threaded), aligning with repomatic `v6.10.0` defaults.
- Replace `{eval-rst}`-wrapped `automodule` and `autoclasstree` directives with native MyST syntax in all docs.

## [`7.10.0` (2026-04-02)](https://github.com/kdeldycke/click-extra/compare/v7.9.0...v7.10.0)

> [!NOTE]
> `7.10.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.10.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.10.0).

- Highlight parent group names in subcommand help text, so ancestor command names are colored even when interleaved with options.
- Add `range_label`, `required`, and `argument` theme slots to `HelpExtraTheme`. Argument metavars are now styled separately from option metavars.
- Add `cross_ref_highlight` flag to `HelpExtraTheme`. Set to `False` to disable free-text highlighting of options, choices, arguments, metavars, and CLI names in descriptions and docstrings. Structural elements (bracket fields, deprecated messages, subcommand lists) are always styled.
- Add type-aware flattening, field metadata, and nested dataclass support to `config_schema`. `flatten_config_keys()` and `normalize_config_keys()` accept an `opaque_keys` parameter to preserve data-keyed dicts. Fields support `click_extra.config_path` and `click_extra.normalize_keys` metadata. Nested dataclass fields are recursively instantiated with the same normalize/flatten/opaque logic.
- Fix help text highlighting of hyphenated option names (e.g. `--table-format` split at the first hyphen), argument names (e.g. `keys`) colliding with option keywords, and substring matches in compound keywords (e.g. `outline` inside `rounded-outline`).
- Fix enum coloring: use `normalize_choice()` to produce the exact strings shown in the metavar instead of raw enum member names.

## [`7.9.0` (2026-03-31)](https://github.com/kdeldycke/click-extra/compare/v7.8.0...v7.9.0)

> [!NOTE]
> `7.9.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.9.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.9.0).

- Add `flatten_config_keys()` utility to flatten nested config dicts into a single level by joining keys with a separator.
- Flatten nested config dicts before dataclass field matching in `config_schema`, so nested TOML sub-tables (e.g. `[tool.myapp.sub-section]`) map to flat dataclass fields (e.g. `sub_section_key`).
- Add `schema_strict` parameter to `ConfigOption` and `ExtraCommand`/`ExtraGroup`: when `True`, unknown config keys raise `ValueError` during dataclass schema validation instead of being silently dropped.
- Auto-discover `pyproject.toml` from the current working directory upward to the VCS root before falling back to the app config directory. Matches the discovery behavior of uv, ruff, and mypy. Only active during auto-discovery (not when `--config` is passed explicitly).
- Instantiate `config_schema` defaults when no config file is found, so `get_tool_config()` never returns `None` when a schema is configured.
- Forward `included_params` from `ExtraCommand`/`ExtraGroup` to `ConfigOption`. Allows `@group(included_params=())` to disable `merge_default_map` when config keys are schema-only and would collide with subcommand names.
- Move `prebake_version()`, `prebake_dunder()`, and `discover_package_init_files()` from `ExtraVersionOption` static methods to module-level functions in `click_extra.version`. Import them directly: `from click_extra.version import prebake_version`.
- Add `git_tag` template field. Resolved from a `__git_tag__` dunder or `git describe --tags --exact-match HEAD` at runtime. Returns the tag name if HEAD is at a tagged commit.
- Add `git_tag_sha` template field. Resolved from a `__git_tag_sha__` dunder on the CLI module, with a `git` subprocess fallback. Replaces the old `__tag_sha__` convention.
- Git template fields (`git_branch`, `git_long_hash`, `git_short_hash`, `git_date`) now check for pre-baked `__<field>__` dunders on the CLI module before falling back to subprocess calls. Enables compiled binaries (Nuitka/PyInstaller) to embed git metadata at build time.
- Add `click-extra prebake` CLI with three subcommands: `prebake all` bakes `__version__` and all git fields in one pass, `prebake version` injects Git hashes into `__version__`, and `prebake field` replaces any empty dunder variable. Field names auto-wrap with `__...__` (e.g. `git_tag_sha` becomes `__git_tag_sha__`). All subcommands auto-discover target files from `[project.scripts]`.
- Add empty `__git_*__` dunder placeholders to `click_extra/__init__.py` for dogfooding the prebake system.
- Pin image URLs in `readme.md` and `docs/tutorial.md` to the release tag at bump time, and restore them to `main` on the next dev bump.

## [`7.8.0` (2026-03-09)](https://github.com/kdeldycke/click-extra/compare/v7.7.0...v7.8.0)

> [!NOTE]
> `7.8.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.8.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.8.0).

- Add `config_schema` parameter to `ConfigOption` and `ExtraCommand`/`ExtraGroup` for typed configuration access via dataclasses or custom callables.
- Add `fallback_sections` parameter for legacy configuration section name migration with deprecation warnings.
- Add `normalize_config_keys()` utility to convert kebab-case config keys to snake_case Python identifiers.
- Add `get_tool_config()` helper to retrieve typed configuration from context.
- Check more variations of local, stable and dev CLI invocations.
- Adopt `RUF022` rule to let `ruff` enforce `__all__` sorting.
- Fix ruff `0.15.5` lint errors.

## [`7.7.0` (2026-03-07)](https://github.com/kdeldycke/click-extra/compare/v7.6.5...v7.7.0)

> [!NOTE]
> `7.7.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.7.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.7.0).

- Add `version_fields` parameter to `ExtraCommand` and `ExtraGroup`. Forwards any `ExtraVersionOption` template field (e.g. `prog_name`, `version`, `git_branch`) from the command decorator without replacing the default params list.
- Lazily evaluate version metadata fields in `ctx.meta`.
- Remove `version` parameter from `ExtraCommand` and `ExtraGroup`.
- Add `hjson`, `json`, `json5`, `jsonc`, `toml`, `xml` and `yaml` table formats for `--table-format`.
- Add `TableFormat.is_markup` property.
- Strip ANSI color codes from markup table formats (`csv`, `html`, `latex`, `rst`, etc.) by default. Use `--color` to preserve them.
- Add `[toml]` extra dependency group for TOML table output via `tomlkit`.
- Emit native types (booleans, nulls, lists) in `--show-params` output for structured serialization formats (JSON, YAML, TOML, HJSON, XML).
- Fix `--show-params` ignoring `--table-format` when it appears first on the command line.
- Expand dotted keys in configuration files (e.g. `"subcommand.option": value`) into nested dicts before merging, to allow for mixing flat dot-notation and nested structures.
- Only capture timer start time when `--time` is actually requested.
- Add `click-extra` entry point so `uvx click-extra` works out of the box. The `click-extra-demo` alias is kept for backward compatibility.

## [`7.6.5` (2026-03-05)](https://github.com/kdeldycke/click-extra/compare/v7.6.4...v7.6.5)

> [!NOTE]
> `7.6.5` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.6.5/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.6.5).

- Bump `tabulate` requirement from `>=0.9` to `>=0.10`.
- Add new `colon-grid` table format.
- Replace custom `github` table renderer with tabulate's `pipe` format. Backport of [python-tabulate#410](https://github.com/astanin/python-tabulate/pull/410).

## [`7.6.4` (2026-03-04)](https://github.com/kdeldycke/click-extra/compare/v7.6.3...v7.6.4)

> [!NOTE]
> `7.6.4` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.6.4/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.6.4).

- Fix `ExtraVersionOption.cli_frame()` crashing in Nuitka-compiled binaries where all stack frames belong to the Click ecosystem.
- Fix `ExtraVersionOption.module_version` returning `None` in `__main__` entry points by checking the parent package's `__version__`.
- Fix test plan for Nuitka-compiled binary.
- Add `@pytest.mark.once` marker for platform-independent structural tests. Run them in a single CI job instead of across the full matrix.

## [`7.6.3` (2026-03-02)](https://github.com/kdeldycke/click-extra/compare/v7.6.2...v7.6.3)

> [!NOTE]
> `7.6.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.6.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.6.3).

- Fix `test_default_pattern_roaming_force_posix` test failures when `XDG_CONFIG_HOME` is set. Closes {issue}`1541`.

## [`7.6.2` (2026-02-27)](https://github.com/kdeldycke/click-extra/compare/v7.6.1...v7.6.2)

> [!NOTE]
> `7.6.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.6.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.6.2).

- Add `ExtraVersionOption.prebake_version()` static method to pre-bake `__version__` strings with Git hashes at compile time, complementing the runtime `version` property for Nuitka/PyInstaller binaries.

## [`7.6.1` (2026-02-27)](https://github.com/kdeldycke/click-extra/compare/v7.6.0...v7.6.1)

> [!NOTE]
> `7.6.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.6.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.6.1).

- Fix test failures when optional config format dependencies are not installed. Closes {issue}`1538`.

## [`7.6.0` (2026-02-26)](https://github.com/kdeldycke/click-extra/compare/v7.5.3...v7.6.0)

> [!NOTE]
> `7.6.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.6.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.6.0).

- Add `_default_subcommands` reserved configuration key to auto-invoke subcommands when none are provided on the CLI. Closes {issue}`1405`.
- Add `_prepend_subcommands` reserved configuration key to always prepend subcommands to every invocation (requires `chain=True`). Closes {issue}`1405`.
- Add `--validate-config` option to validate configuration files.
- Add `ConfigFormat.PYPROJECT_TOML` format for `[tool.*]` section support in `pyproject.toml`. Closes {issue}`1524`.
- Stop parent directory walk on inaccessible directories.
- Add `stop_at` parameter to `@config_option` to limit parent directory walking. Defaults to `VCS`. Closes {issue}`651`.
- Add `VCS` sentinel and `VCS_DIRS` constant for VCS root detection.
- Resolve relative paths to absolute in `parent_patterns` before yielding.
- Add `included_params` allowlist to `ConfigOption` and `@config_option`, the inverse of `excluded_params`. Closes {issue}`1362`.
- Add human-friendly display labels to `ConfigFormat`.
- Switch back from `SPLIT` to `BRACE` flag for multi-format config file patterns. Fixes a bug where only the first format received the directory prefix with `SPLIT`.
- Hard code icon workaround for Sphinx index entries.
- Automatically append Git short hash as a PEP 440 local version identifier to `.dev` versions (e.g., `1.2.3.dev0+abc1234`).
- Skip Git hash suffix for versions that already contain `+` (pre-baked local identifiers) to avoid invalid double-suffixed versions.
- Recognize `LLM` environment variable to strip ANSI codes when running under an AI agent.

## [`7.5.3` (2026-02-22)](https://github.com/kdeldycke/click-extra/compare/v7.5.2...v7.5.3)

> [!NOTE]
> `7.5.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.5.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.5.3).

- Allow disabling of autodiscovery of configuration files by setting `default=NO_CONFIG` on `@config_option`. Closes {issue}`1495`.
- Implement `resolve_any_xref` in `ClickDomain` to prevent MyST-Parser warning. Closes {issue}`1502`.
- Fix subcommand conflict detection checking against root-level params instead of parent params. Closes {pr}`1286`.

## [`7.5.2` (2026-02-12)](https://github.com/kdeldycke/click-extra/compare/v7.5.1...v7.5.2)

> [!NOTE]
> `7.5.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.5.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.5.2).

- Fix GitHub alerts converter mangling `list-table` directive content. Closes {issue}`1490`.
- Replace Dependabot by Renovate.
- Move `click_extra/docs_update.py` to `docs/docs_update.py`.
- Add `pygments-ansi-color` to `docs` dependency group for lexer table generation.

## [`7.5.1` (2026-02-05)](https://github.com/kdeldycke/click-extra/compare/v7.5.0...v7.5.1)

> [!NOTE]
> `7.5.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.5.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.5.1).

- Add new `aligned` table format with single-space column separators and no borders.
- Fix parallel mode support in Sphinx extension. Closes {issue}`1482`.

## [`7.5.0` (2026-02-03)](https://github.com/kdeldycke/click-extra/compare/v7.4.0...v7.5.0)

> [!NOTE]
> `7.5.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.5.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.5.0).

- Fix `TableFormat.GITHUB` to render proper alignment hints in the separator row (`:---`, `:---:`, `---:`).
- Move auto-lock time from 8:43 to 4:43.
- Set cooldown period via the `pyproject.toml`.
- Add Download link to project metadata.
- Include license file in package.
- Replace deprecated `codecov/test-results-action` by `codecov/codecov-action`.
- Remove utilization workaround for `macos-15-intel`.
- Bump requirement of `extra-platforms` to 8.0.0.

## [`7.4.0` (2025-12-08)](https://github.com/kdeldycke/click-extra/compare/v7.3.0...v7.4.0)

> [!NOTE]
> `7.4.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.4.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.4.0).

- Add cooldown period for dependabot and `uv.lock` updates.
- Uncap all dependencies.
- Replace `tool.uv` section by `build-system`.
- Merge all label jobs into a single one.
- Unlock a CPU core stuck at 100% utilization on `macos-15-intel`.

## [`7.3.0` (2025-12-01)](https://github.com/kdeldycke/click-extra/compare/v7.2.0...v7.3.0)

> [!NOTE]
> `7.3.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.3.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.3.0).

- Add `click:source` directive as an alias to `click:example` directive in Sphinx extension.
- Flag `click:example` directive as deprecated in favor of `click:source`.
- Add support for nested GitHub alerts.
- Fix fetching version when the CLI is implemented as a standalone script and not as a package module.

## [`7.2.0` (2025-11-26)](https://github.com/kdeldycke/click-extra/compare/v7.1.0...v7.2.0)

> [!NOTE]
> `7.2.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.2.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.2.0).

- Add support for auto-conversion of GitHub alerts into MyST admonitions in Sphinx extension.
- Rename `click-extra` demo CLI to `click-extra-demo` to avoid confusion with the package name.
- Run tests on `ubuntu-slim` GitHub Actions runner.
- Run docs update job on `ubuntu-slim` runner.

## [`7.1.0` (2025-11-21)](https://github.com/kdeldycke/click-extra/compare/v7.0.1...v7.1.0)

> [!NOTE]
> `7.1.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.1.0).

- Add support for aliases in `EnumChoice` type.
- Register pre-configured `render_table()` utility in the context when `table_format` is set, in the same spirit as `print_table()`.

## [`7.0.1` (2025-11-18)](https://github.com/kdeldycke/click-extra/compare/v7.0.0...v7.0.1)

> [!NOTE]
> `7.0.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.0.1).

- Restore support for `@extra_command`, `@extra_group` and `@extra_version_option`, but mark them as deprecated.

## [`7.0.0` (2025-11-18)](https://github.com/kdeldycke/click-extra/compare/v6.2.0...v7.0.0)

> [!NOTE]
> `7.0.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.0.0).

- Allow parent directories search for configuration files. Adds `search_parents` argument on `@config_file`. Closes {issue}`651`.
- Allow fine-tuning of configuration file format pattern matching. Replaces `formats` argument on `@config_file` by `file_format_patterns`.
- Adds `search_pattern_flags` and `file_pattern_flags` arguments on `@config_file` to allow user to tweak pattern matching behavior.
- Use `|` as separator for multiple file patterns instead of `{,}` syntax. Replace `glob.BRACE` by `glob.SPLIT` for search pattern flags. Force `glob.SPLIT` for file pattern flags.
- Remove `glob.IGNORECASE` flag to make case-sensitivity determined by the underlying platform at runtime.
- Force `glob.NODIR` for search pattern flags to speed up search.
- Rename `click_extra.config.Formats` enum to `click_extra.config.ConfigFormat`. Expose it at the root `click_extra` module.
- Eat our own dog food: add a `click-extra` CLI to run self-tests.
- Override base decorators and classes with Click Extra's own variants:
  - `@command` now points to what was `@extra_command`.
  - `@group` now points to what was `@extra_group`.
  - `Option` class now points to `click_extra.Option`, which is a subclass of `cloup.Option`.
  - `Argument` class now points to `click_extra.Argument`, which is a subclass of `cloup.Argument`.
  - `@option` now instantiates `click_extra.Option` by default.
  - `@argument` now instantiates `click_extra.Argument` by default.
  - `@version_option` now points to what was `@extra_version_option`.
  - Now if you want to use the previous aliases to Click's and Cloup's originals, import them directly from `click` or `cloup` instead of `click_extra`, which makes origination clearer.
- Remove `@extra_command`, `@extra_group` and `@extra_version_option`.
- Remove `no_redefined` argument in `click_extra.pytest.command_decorators()` method.
- Validates that classes passed to the `cls` parameter of decorators are subclasses of the expected base classes.
- Normalize the default value of `EnumChoice` parameters to their string choice representation in help screens.
- Run tests on Python `3.14t` and `3.15t` free-threaded variants.

## [`6.2.0` (2025-11-04)](https://github.com/kdeldycke/click-extra/compare/v6.1.0...v6.2.0)

> [!NOTE]
> `6.2.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/6.2.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v6.2.0).

- Add new `EnumChoice` type for fine-tunable Enum-based choices. Expose `EnumChoice` and `ChoiceSource` at the root `click_extra` module.
- Relax dependencies to support Python 3.10. Closes {issue}`1385`.
- Re-introduce `tomli` dependency for Python 3.10 users.
- Skip tests on intermediate Python versions (`3.11`, `3.12` and `3.13`) to reduce CI load.

## [`6.1.0` (2025-10-29)](https://github.com/kdeldycke/click-extra/compare/v6.0.3...v6.1.0)

> [!NOTE]
> `6.1.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/6.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v6.1.0).

- Add support for JSON5, JSONC and HJSON configuration files.
- YAML and XML configuration support is now optional. You need to install the `click_extra[yaml]` and `click_extra[xml]` extra dependency groups to enable it.
- Add new `@lazy_group` decorator and `LazyGroup` class to create groups that only load their subcommands when invoked. Closes {issue}`1332`.
- Move all custom types to `click_extra._types` module.
- Avoid importing all types at runtime to reduce startup time.
- Upgrade tests runs from `macos-13` to `macos-15-intel`, and from `macos-15` to `macos-26`.
- Use `astral-sh/setup-uv` action to install `uv`.

## [`6.0.3` (2025-10-13)](https://github.com/kdeldycke/click-extra/compare/v6.0.2...v6.0.3)

> [!NOTE]
> `6.0.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/6.0.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v6.0.3).

- Fix `regex_fullmatch_line_by_line` to accept compiled regex patterns as well as string patterns.

## [`6.0.2` (2025-10-11)](https://github.com/kdeldycke/click-extra/compare/v6.0.1...v6.0.2)

> [!NOTE]
> `6.0.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/6.0.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v6.0.2).

- Add a new `regex_fullmatch_line_by_line` utility to compare a wall of text against a regex, line by line, and raise a custom `RegexLineMismatch` exception on the first mismatch.

## [`6.0.1` (2025-10-08)](https://github.com/kdeldycke/click-extra/compare/v6.0.0...v6.0.1)

> [!NOTE]
> `6.0.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/6.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v6.0.1).

- Fix `@config_option` to accept `Path` objects as default value. Closes {issue}`1356`.
- Add official support of Python 3.14.
- Run tests on Python 3.15-dev.

## [`6.0.0` (2025-09-25)](https://github.com/kdeldycke/click-extra/compare/v5.1.1...v6.0.0)

> [!NOTE]
> `6.0.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/6.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v6.0.0).

- Add new variables for version string template: `{git_repo_path}`, `{git_branch}`, `{git_long_hash}`, `{git_short_hash}` and `{git_date}`.
- Add a new `--no-config` option on `@extra_command` and `@extra_group` to disable configuration files. Closes {issue}`750`.
- Add `--table-format` option by default on `@extra_command` and `@extra_group`.
- Let `--table-format` and `--no-color` affect the rendering of `--show-params` table.
- Swap `Class` and `Spec.` columns in `--show-params` output.
- Remove the `-C` short option associated with `--config`.
- Remove the `-t` short option associated with `--table-format`.
- Classify table formats into two categories: markup formats and plain-text formats.
- Rename all table format identifiers to use dashes instead of underscores:
  - `double_grid` → `double-grid`
  - `double_outline` → `double-outline`
  - `fancy_grid` → `fancy-grid`
  - `fancy_outline` → `fancy-outline`
  - `heavy_grid` → `heavy-grid`
  - `heavy_outline` → `heavy-outline`
  - `latex_booktabs` → `latex-booktabs`
  - `latex_longtable` → `latex-longtable`
  - `latex_raw` → `latex-raw`
  - `mixed_grid` → `mixed-grid`
  - `mixed_outline` → `mixed-outline`
  - `rounded_grid` → `rounded-grid`
  - `rounded_outline` → `rounded-outline`
  - `simple_grid` → `simple-grid`
  - `simple_outline` → `simple-outline`
- Fix display in `--show-params` for parameters sharing the same name.
- Fix detection in the `--version` option of the module in which the user's CLI is implemented.
- Rename `click_extra.tabulate` namespace to `click_extra.table`.
- Expose `click._utils.UNSET` and `click.logging.LogLevel` at the root `click_extra` module.
- Replace unmaintained `mergedeep` dependency by `deepmerge`.
- Remove maximum capped version of all dependencies (relax all `~=` specifiers to `>=`). This gives more freedom to downstream and upstream packagers. Document each minimal version choice.
- Add unit tests for Sphinx extension.
- Render GitHub-Flavored Markdown admonitions in Sphinx.

## [`5.1.1` (2025-08-24)](https://github.com/kdeldycke/click-extra/compare/v5.1.0...v5.1.1)

> [!NOTE]
> `5.1.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/5.1.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v5.1.1).

- Relax Click dependency to account for yanked release. Closes {issue}`1307`.

## [`5.1.0` (2025-08-03)](https://github.com/kdeldycke/click-extra/compare/v5.0.2...v5.1.0)

> [!NOTE]
> `5.1.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/5.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v5.1.0).

- Add support for MyST Markdown syntax for `click:example` and `click:run` Sphinx directives.
- Add support for all `code-block` options to `click:example` and `click:run`: `:linenos:`, `:lineno-start:`, `:emphasize-lines:`, `:force:`, `:caption:`, `:name:`, `:class:` and `:dedent:`.
- Add new `:show-source:`/`:hide-source:`, `:show-results:`/`:hide-results:` and `:language:` options to `click:example` and `click:run`. Closes {issue}`719`.
- Support non-string choices in colored help screens. Closes {issue}`1284`.
- Replace `LOG_LEVELS` mapping with `LogLevel` enum.
- Remove `DEFAULT_LEVEL_NAME` constants.
- Fix rendering of default values in `--show-params` output.
- Fix reconciliation of flags' environment variables.
- Force requirement on `cloup >= 3.0.7`.
- Be more informative when error is found in `click:example` and `click:run` Sphinx directives by displaying the path of the original document and the line number of the error.

## [`5.0.2` (2025-05-31)](https://github.com/kdeldycke/click-extra/compare/v5.0.1...v5.0.2)

> [!NOTE]
> `5.0.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/5.0.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v5.0.2).

- Set `ExtraCommand` default `prog_name` to CLI's `name` to avoid it to be named `python -m <module_name>` if invoked out of a module.
- Tweak exit code rendering of CLI runs.

## [`5.0.1` (2025-05-28)](https://github.com/kdeldycke/click-extra/compare/v5.0.0...v5.0.1)

> [!NOTE]
> `5.0.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/5.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v5.0.1).

- Fix highlighting of deprecated messages.
- Use ASCII characters instead of unicode for prompt rendering in messages.

## [`5.0.0` (2025-05-13)](https://github.com/kdeldycke/click-extra/compare/v4.15.0...v5.0.0)

> [!NOTE]
> `5.0.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/5.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v5.0.0).

- Upgrade to Click 8.2.0.
- Add support for custom deprecated messages on commands and parameters.
- Remove `ExtraOption.get_help_default()` and rely on new `Option.get_help_extra()`.
- Remove dependency on `pallets-sphinx-themes`.
- Drop supports for Python 3.10.
- Add `windows-11-arm` to the test matrix.
- Remove tests on `ubuntu-22.04-arm`, `ubuntu-22.04` and `windows-2022` to keep matrix small.

## [`4.15.0` (2025-03-05)](https://github.com/kdeldycke/click-extra/compare/v4.14.2...v4.15.0)

> [!NOTE]
> `4.15.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.15.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.15.0).

- Regroup all envronment variables-related code.
- Rename `extend_envvars()` to `merge_envvar_ids()` and allow it to merge arbitrary-nested structures. Normalize names to uppercase on Windows.
- Rename `normalize_envvar()` to `clean_envvar_id()`.
- Rename `all_envvars()` to `param_envvar_ids()`.
- Rename `auto_envvar()` to `param_auto_envvar_id()`.
- Remove unused `normalize` parameter on `all_envvars()`.
- Add missing line returns in `render_cli_run()`.
- Prefix all types with capital-`T`.

## [`4.14.2` (2025-02-23)](https://github.com/kdeldycke/click-extra/compare/v4.14.1...v4.14.2)

> [!NOTE]
> `4.14.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.14.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.14.2).

- Extract rendering part of the `print_cli_run()` helper to `render_cli_run()`.
- Remove unused `click_extra.testing.run_cmd`.
- Relax requirement on `extra-platforms`.
- Add tests on `windows-2025`. Remove tests on `windows-2019`.

## [`4.14.1` (2025-02-02)](https://github.com/kdeldycke/click-extra/compare/v4.14.0...v4.14.1)

> [!NOTE]
> `4.14.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.14.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.14.1).

- Fix upload of Python package to GitHub release on tagging.

## [`4.14.0` (2025-02-02)](https://github.com/kdeldycke/click-extra/compare/v4.13.2...v4.14.0)

> [!NOTE]
> `4.14.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.14.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.14.0).

- Add a new `--verbose` option on `@extra_command` and `@extra_group` to increase the verbosity level for each additional repetition.
- Add new `@verbose_option` pre-configured decorator.
- Reassign the short `-v` option from `--verbosity` to `--verbose`.
- Improve logging documentation.
- Align `ExtraStreamHandler` behavior to `logging.StreamHandler`.
- Move `stream_handler_class` and `formatter_class` arguments from `new_extra_logger` to `extraBasicConfig`.
- Add new `file_handler_class` argument to `extraBasicConfig`.
- Fix upload of Python package to GitHub release on tagging.
- Remove dependency on `pytest-cases`.

## [`4.13.2` (2025-01-28)](https://github.com/kdeldycke/click-extra/compare/v4.13.1...v4.13.2)

> [!NOTE]
> `4.13.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.13.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.13.2).

- Re-release to fix GitHub publishing.
- Reactivates some color tests on Windows.

## [`4.13.1` (2025-01-28)](https://github.com/kdeldycke/click-extra/compare/v4.13.0...v4.13.1)

> [!NOTE]
> `4.13.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.13.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.13.1).

- Re-release to fix GitHub publishing.

## [`4.13.0` (2025-01-28)](https://github.com/kdeldycke/click-extra/compare/v4.12.0...v4.13.0)

> [!NOTE]
> `4.13.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.13.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.13.0).

- Revamps logging helpers and aligns them with Python's `logging` module.
- Remove `extra_basic_config`.
- Adds new `extraBasicConfig`, and aligns it with Python's `basicConfig`.
- Replace `ExtraLogFormatter` with `ExtraFormatter`.
- Replace `ExtraLogHandler` with `ExtraStreamHandler`.
- Add new `new_extra_logger` helper.
- Rewrite the logging documentation with all use-cases and custom configuration examples. Closes {issue}`989`.
- Removes old platforms page from documentation.

## [`4.12.0` (2025-01-20)](https://github.com/kdeldycke/click-extra/compare/v4.11.7...v4.12.0)

> [!NOTE]
> `4.12.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.12.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.12.0).

- Remove Click Extra's own implementation of `HelpOption` class now that fixes have reached Click's upstream.
- Redefine `@help_option` decorator to default to `--help`/`-h` options.
- Add more logging examples in documentation.
- Add tests on `ubuntu-24.04-arm` and `ubuntu-22.04-arm`.
- Use `uv` to install specific versions of Python.

## [`4.11.7` (2024-12-01)](https://github.com/kdeldycke/click-extra/compare/v4.11.6...v4.11.7)

> [!NOTE]
> `4.11.7` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.11.7/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.11.7).

- Remove support for comments in JSON configuration files. Remove dependency on unmaintained `commentjson`. Closes [`click-extra#1152`](https://github.com/kdeldycke/click-extra/issues/1152).

## [`4.11.6` (2024-11-29)](https://github.com/kdeldycke/click-extra/compare/v4.11.5...v4.11.6)

> [!NOTE]
> `4.11.6` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.11.6/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.11.6).

- Make `--timer` option eager so it can jumps the queue of processing order.
- Fix configuration of help option generated by the `help_option_names` context setting. Closes [`mail-deduplicate#762`](https://github.com/kdeldycke/mail-deduplicate/issues/762).
- Fix eagerness of help option generated by `help_option_names`. Refs [`click#2811`](https://github.com/pallets/click/pull/2811).
- Display generated help option in `--show-params` results.
- Force UTF-8 encoding everywhere.

## [`4.11.5` (2024-11-18)](https://github.com/kdeldycke/click-extra/compare/v4.11.4...v4.11.5)

> [!NOTE]
> `4.11.5` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.11.5/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.11.5).

- Allow `replace_content()` utility method to replace any content found after the start tag.

## [`4.11.4` (2024-11-14)](https://github.com/kdeldycke/click-extra/compare/v4.11.3...v4.11.4)

> [!NOTE]
> `4.11.4` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.11.4/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.11.4).

- Ignore hidden options when coloring help screen.

## [`4.11.3` (2024-11-12)](https://github.com/kdeldycke/click-extra/compare/v4.11.2...v4.11.3)

> [!NOTE]
> `4.11.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.11.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.11.3).

- Aligns dependencies.

## [`4.11.2` (2024-11-11)](https://github.com/kdeldycke/click-extra/compare/v4.11.1...v4.11.2)

> [!NOTE]
> `4.11.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.11.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.11.2).

- Aligns dependencies.

## [`4.11.1` (2024-10-27)](https://github.com/kdeldycke/click-extra/compare/v4.11.0...v4.11.1)

> [!NOTE]
> `4.11.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.11.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.11.1).

- Fix tests against development version of Click.

## [`4.11.0` (2024-10-08)](https://github.com/kdeldycke/click-extra/compare/v4.10.0...v4.11.0)

> [!NOTE]
> `4.11.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.11.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.11.0).

- Add support for Python 3.13.
- Drop supports for Python 3.9.
- Run tests on Python 3.14-dev.
- Add tests on `ubuntu-24.04`. Remove tests on `ubuntu-20.04`.
- Upgrade tests from `macos-14` to `macos-15`.

## [`4.10.0` (2024-09-05)](https://github.com/kdeldycke/click-extra/compare/v4.9.0...v4.10.0)

> [!NOTE]
> `4.10.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.10.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.10.0).

- Move all platform detection utilities to its own standalone [Extra Platforms project](https://github.com/kdeldycke/extra-platforms).
- Add dependency on `extra-platforms`.

## [`4.9.0` (2024-07-25)](https://github.com/kdeldycke/click-extra/compare/v4.8.3...v4.9.0)

> [!NOTE]
> `4.9.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.9.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.9.0).

- Switch from Poetry to `uv`.
- Drop support for Python 3.8.
- Mark Python 3.13-dev tests as stable.
- Remove dependency on `regex`.

## [`4.8.3` (2024-05-25)](https://github.com/kdeldycke/click-extra/compare/v4.8.2...v4.8.3)

> [!NOTE]
> `4.8.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.8.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.8.3).

- Fix string interpolation in log message.

## [`4.8.2` (2024-05-25)](https://github.com/kdeldycke/click-extra/compare/v4.8.1...v4.8.2)

> [!NOTE]
> `4.8.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.8.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.8.2).

- Do not raise error if package version cannot be fetched.

## [`4.8.1` (2024-05-23)](https://github.com/kdeldycke/click-extra/compare/v4.8.0...v4.8.1)

> [!NOTE]
> `4.8.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.8.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.8.1).

- Do not fail on `docs_update` import if `pygments` is not installed.

## [`4.8.0` (2024-05-23)](https://github.com/kdeldycke/click-extra/compare/v4.7.5...v4.8.0)

> [!NOTE]
> `4.8.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.8.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.8.0).

- Slim down package by moving unit tests out of the main package.
- Allow reuse of Pytest fixures and marks by other packages.
- Move dependencies extending `pygments`, `sphinx` and `pytest` into optional extra dependencies. Closes {issue}`836`.
- Split `dev` dependency groups into optional `test`, `typing` and `docs` groups.
- Remove direct dependency on `mypy`.
- Allow running tests with Python 3.8 and 3.9 on `macos-14` runners.

## [`4.7.5` (2024-04-05)](https://github.com/kdeldycke/click-extra/compare/v4.7.4...v4.7.5)

> [!NOTE]
> `4.7.5` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.7.5/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.7.5).

- Remove bypass of `cloup.Color` re-import.

## [`4.7.4` (2024-02-23)](https://github.com/kdeldycke/click-extra/compare/v4.7.3...v4.7.4)

> [!NOTE]
> `4.7.4` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.7.4/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.7.4).

- Allow standalone `--version` option to output its debug messages.
- Force closing of context before exiting CLIs to provoque callback calls and prevent state leaks.
- Run tests on `macos-14`. Remove tests on `macos-12`.

## [`4.7.3` (2024-01-07)](https://github.com/kdeldycke/click-extra/compare/v4.7.2...v4.7.3)

> [!NOTE]
> `4.7.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.7.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.7.3).

- Run tests on Python 3.13-dev branch.

## [`4.7.2` (2023-11-08)](https://github.com/kdeldycke/click-extra/compare/v4.7.1...v4.7.2)

> [!NOTE]
> `4.7.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.7.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.7.2).

- Run tests on released Python 3.12 version.

## [`4.7.1` (2023-09-29)](https://github.com/kdeldycke/click-extra/compare/v4.7.0...v4.7.1)

> [!NOTE]
> `4.7.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.7.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.7.1).

- Distinguish between parameter type and Python type in `--show-params` output.
- Recognize custom parameter type as string-based. Closes {issue}`721`.
- Rely on `bump-my-version` to update citation file metadata.

## [`4.7.0` (2023-09-04)](https://github.com/kdeldycke/click-extra/compare/v4.6.5...v4.7.0)

> [!NOTE]
> `4.7.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.7.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.7.0).

- Switch to format string style for version template.
- Add new variables for version string template: `{module}`, `{module_name}`, `{module_file}`, `{module_version}`, `{package_version}` and `{exec_name}`.
- Remove support for Click-specific `%(prog)` and `%(package)` variables in version string.
- Print all versions string variables in debug mode.

## [`4.6.5` (2023-09-01)](https://github.com/kdeldycke/click-extra/compare/v4.6.4...v4.6.5)

> [!NOTE]
> `4.6.5` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.6.5/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.6.5).

- Highlight required label and value range in option description. Closes {issue}`748`.

## [`4.6.4` (2023-08-23)](https://github.com/kdeldycke/click-extra/compare/v4.6.3...v4.6.4)

> [!NOTE]
> `4.6.4` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.6.4/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.6.4).

- Fix collection of subcommand parameters in `--show-params` output. Closes {issue}`725`.
- Set `%(package_name)` in `--version` to file name for CLI that are standalone scripts and not packaged. Fix {issue}`729`.
- Allow standalone scripts to define a local `__version__` variable to set the `%(version)` element in `--version` output.
- Allow building of documentation with Sphinx 7.
- Run tests on `macos-13`. Remove tests on `macos-11`.
- Ignore unstable tests on upcoming Click `8.2.x` / `main` branch.

## [`4.6.3` (2023-07-16)](https://github.com/kdeldycke/click-extra/compare/v4.6.2...v4.6.3)

> [!NOTE]
> `4.6.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.6.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.6.3).

- Forces `ExtraContext` to properly close itself before exiting the program, to trigger all callbacks.

## [`4.6.2` (2023-07-15)](https://github.com/kdeldycke/click-extra/compare/v4.6.1...v4.6.2)

> [!NOTE]
> `4.6.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.6.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.6.2).

- Remove workaround for Cloup handling of `command_class` default on custom groups.
- Force `@extra_group` to produce sub-groups of the same class.

## [`4.6.1` (2023-07-13)](https://github.com/kdeldycke/click-extra/compare/v4.6.0...v4.6.1)

> [!NOTE]
> `4.6.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.6.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.6.1).

- Inspect in `--version` the whole execution stack to find the package in which the user's CLI is implemented.

## [`4.6.0` (2023-07-12)](https://github.com/kdeldycke/click-extra/compare/v4.5.0...v4.6.0)

> [!NOTE]
> `4.6.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.6.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.6.0).

- Keep the promise of drop-in replacement for `@version_option` which is now a proxy to Click's original.
- Rename the colored, enhanced `--version` option to `@extra_version_option` for its decorator, and `ExtraVersionOption` for its class.
- Activate colors on `@extra_command` and `@extra_group` by default, even if stripped of all their default parameters. Closes {issue}`534` and {pr}`543`.
- Expose location and content of user's configuration file in the Context's `meta` property. Closes {issue}`673`.
- Render specs of hidden parameters in `--show-params` output. Fixes {issue}`689`.
- Swap `Exposed` and `Allowed in conf?` columns in `--show-params` output.
- Add a `hidden` column to `--show-params` output. Refs {issue}`689`.

## [`4.5.0` (2023-07-06)](https://github.com/kdeldycke/click-extra/compare/v4.4.0...v4.5.0)

> [!NOTE]
> `4.5.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.5.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.5.0).

- Expose verbosity level name, table format ID and CLI start timestamp in the Context's `meta` property.
- Refactor `VersionOption`. Introduce internal caching.
- Expose version string elements in the Context's `meta` property. Closes {issue}`325`.
- Remove `print_env_info` option from `VersionOption` class and `version_option` decorators.
- Add new `%(env_info)` element. Default value is the same as what the removed `print_env_info` produced (i.e. a JSON dump of the environment).
- Allow `%(env_info)` value to be set by user on `--version`.
- Rename in version string formatting the `%(prog)` element to `%(prog_name)`, and `%(package)` to `%(package_name)`.
- Detect Click-specific `%(prog)` and `%(package)` and raise a deprecated warning.
- Do not print environment info in `--version` by default. Change default message from `%(prog)s, version %(version)s\n%(env_info)` to `%(prog_name)s, version %(version)s`.
- Automaticcaly augment version string with environment info in `DEBUG` log level.
- Expose `click_extra.search_params` utility.

## [`4.4.0` (2023-06-16)](https://github.com/kdeldycke/click-extra/compare/v4.3.0...v4.4.0)

> [!NOTE]
> `4.4.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.4.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.4.0).

- Add a `reduce()` utility to reduce a collection of `Group` and `Platform` to a minimal set.
- Remove `@destructive` and `@non_destructive` pytest markers.
- Rename the `exclude_params` argument of `ParamStructure` and `ConfigOption` to `excluded_params`.
- Fix over-styling of usage heading in help screen.
- Move `bump-my-version` configuration to `pyproject.toml`.
- Remove `bump2version` from dev dependencies, and let the external workflows install it.
- Remove workaround for `pallets-sphinx-themes`'s outdated reference to old `click`'s Python 2 compatibility hack.

## [`4.3.0` (2023-06-02)](https://github.com/kdeldycke/click-extra/compare/v4.2.0...v4.3.0)

> [!NOTE]
> `4.3.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.3.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.3.0).

- Colorize envvars and default values in `--show-params` option.
- Keep `<stdout>` and `<stderr>` streams independent in `ExtraCliRunner`.
- Always collect `<stderr>` output and never raise an exception.
- Add a new `<output>` stream to simulate what the user sees in its terminal.
- Only mix `<stdout>` and `<stderr>` in `<output>` when `mix_stderr=True`.
- Print detailed CLI execution trace in logs.
- Document inline tests in Sphinx CLI execution blocks.
- Improve Pygments ANSI formatter and lexers documentation.
- Document usage of `pygmentize` command line.
- Regroup all parameter-related code.
- Regroup all testing and CLI execution utilities.
- Activate zoom on big Mermaid graphs.

## [`4.2.0` (2023-05-24)](https://github.com/kdeldycke/click-extra/compare/v4.1.0...v4.2.0)

> [!NOTE]
> `4.2.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.2.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.2.0).

- Add support for dedicated styling of environment variables, defaults, command aliases, aliases punctuation, subcommands and deprecated tag in help screen.
- Update default colors of help screen to improve readability.
- Change default style of critical log messages' prefix to bold red.
- Document the full matrix of colors and styles.
- Render bright variants of ANSI colors in documentation.
- Dynamically patch the style provided to `AnsiHtmlFormatter` to augment it with ANSI colors.
- Remove main dependency on `furo`, make it a development dependency.
- Remove the custom `ansi-click-extra-furo-style` Pygments style for Furo and its `AnsiClickExtraFuroStyle` class.

## [`4.1.0` (2023-05-12)](https://github.com/kdeldycke/click-extra/compare/v4.0.0...v4.1.0)

> [!NOTE]
> `4.1.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.1.0).

- Add new global `show_envvar` option to display all environment variables in help screens.
- Global `show_choices` setting to show or hide choices when prompting a user for input.
- Populate the `Allowed in conf?` column in `--show-params` output if there is a `--config` option in the command.
- Print all modified loggers and their levels in `DEBUG` mode.
- Directly download Pygments source code from GitHub to check for candidates for ANSI-coloring in unittests.
- Test continuously against Click and Cloup development version. Closes {issue}`525`.
- Move `click_extra.commands.TimerOption` to `click_extra.timer.TimerOption`.

## [`4.0.0` (2023-05-08)](https://github.com/kdeldycke/click-extra/compare/v3.10.0...v4.0.0)

> [!NOTE]
> `4.0.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.0.0).

- Drop support for Python 3.7.
- Add a simple `--telemetry`/`--no-telemetry` option flag which respects the `DO_NOT_TRACK` environment variable.
- Add new `populate_auto_envvars` parameter to `@extra_command`/`@extra_group` decorators to allow auto-generated environment variables to be displayed in help screens.
- Display all environment variables in `--show-params` output, including those auto-generated by the way of the `auto_envvar_prefix` context parameter.
- Allow user to override hard-coded context defaults on `@extra_command`/`@extra_group`.
- Change default log level from `INFO` to `WARNING` to aligns with Python's global root logger.
- Force resetting of log level on `--verbosity`'s context closing to the hard-coded default.
- Use a dedicated `click_extra` logger for all internal messages, instead of sending them to the user-defined one.
- Aligns `click_extra` logger level to `--verbosity` option level.
- Set default logger of `--verbosity` to Python's global `root` logger, instead a local wrapped logger. Closes {issue}`318`.
- Allow user to provide a string as the default logger to `--verbosity` that will be used to fetch the global logger singleton of that name. Closes {issue}`318`.
- Only colorize the `%(levelname)s` field during log record formatting, not the `:` message separator.
- Prefix `INFO`-level log message with `info: ` prefix by default.
- Raise an error if multiple `--version` options are defined in the same command. Closes {issue}`317`.
- Remove dependency on `click-log`.
- Remove supports for `Pallets-Sphinx-Themes < 2.1.0`.
- Force closing of the context before stopping the execution flow, to make sure all callbacks are called.
- Fix rendering of GitHub-Flavored Markdown tables in canonical format.

## [`3.10.0` (2023-04-04)](https://github.com/kdeldycke/click-extra/compare/v3.9.0...v3.10.0)

> [!NOTE]
> `3.10.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.10.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.10.0).

- Colorize help screens of subcommands spawned out of an `@extra_group`. Closes {issue}`479`.
- Remove deprecated `click_extra.platform`.

## [`3.9.0` (2023-04-01)](https://github.com/kdeldycke/click-extra/compare/v3.8.3...v3.9.0)

> [!NOTE]
> `3.9.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.9.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.9.0).

- Allow `@color_option`, `@command`, `@config_option`, `@extra_command`, `@extra_group`, `@group`, `@help_option`, `@show_params_option`, `@table_format_option`, `@timer_option`, `@verbosity_option` and `@version_option` decorators to be used without parenthesis.
- Fix wrapping of Cloup decorators by `@extra_group`/`@extra_command` decorators. Closes {issue}`489`.
- Add main dependency on `furo` which is referenced in ANSI-aware Pygment styles.
- Move all documentation assets to `assets` subfolder.

## [`3.8.3` (2023-02-25)](https://github.com/kdeldycke/click-extra/compare/v3.8.2...v3.8.3)

> [!NOTE]
> `3.8.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.8.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.8.3).

- Let `--version` option output system details when run on `python >= 3.10`.

## [`3.8.2` (2023-02-20)](https://github.com/kdeldycke/click-extra/compare/v3.8.1...v3.8.2)

> [!NOTE]
> `3.8.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.8.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.8.2).

- Fix overlapping detection of `linux` and `wsl2` platforms.
- Renders platform groups in documentation in Mermaid format instead of Graphviz. Add new dependency on `sphinxcontrib-mermaid`, removed dependency on `graphviz`.
- Produce dependency graph in Mermaid instead of Graphviz.

## [`3.8.1` (2023-02-15)](https://github.com/kdeldycke/click-extra/compare/v3.8.0...v3.8.1)

> [!NOTE]
> `3.8.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.8.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.8.1).

- Code, comments and documentation style change to conform to new QA workflows based on `ruff`.

## [`3.8.0` (2023-01-25)](https://github.com/kdeldycke/click-extra/compare/v3.7.0...v3.8.0)

> [!NOTE]
> `3.8.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.8.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.8.0).

- Rename `click_extra.platform` to `click_extra.platforms`.
- Refactor platforms and their groups with dataclasses instead of string IDs.
- Add new `LINUX_LAYERS`, `ALL_WINDOWS`, `BSD_WITHOUT_MACOS`, `EXTRA_GROUPS` and `ALL_GROUPS` groups.
- Add new dependency on `graphviz`.
- Activate Graphviz extension in Sphinx.
- Let Sphinx produce the dependency graph from Graphviz file.
- Produce platform graph dynamically.
- Rename `docs.py` to `docs_update.py` and allow this module to be called directly.

## [`3.7.0` (2023-01-03)](https://github.com/kdeldycke/click-extra/compare/v3.6.0...v3.7.0)

> [!NOTE]
> `3.7.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.7.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.7.0).

- Add support for new ANSI-capable lexers: `ansi-gap-console` and `ansi-gap-repl`.
- Auto-update table of supported lexers in documentation.
- Add test to search in Pygments' test data for REPL/terminal-like lexers, as candidates for ANSI-coloring.
- Depends on `importlib_metadata` for `Python < 3.8`.

## [`3.6.0` (2022-12-28)](https://github.com/kdeldycke/click-extra/compare/v3.5.0...v3.6.0)

> [!NOTE]
> `3.6.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.6.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.6.0).

- Add new constants to group platforms by family.
- Add heuristics to recognize new platforms: IBM AIX, Cygwin, FreeBSD, GNU/Hurd, NetBSD, OpenBSD, Oracle Solaris, SunOS, Windows Subsystem for Linux v1 and v2.
- Document version option usage.
- Split version code to its own file and tests.
- Run tests on Python `3.12-dev`.

## [`3.5.0` (2022-12-09)](https://github.com/kdeldycke/click-extra/compare/v3.4.1...v3.5.0)

> [!NOTE]
> `3.5.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.5.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.5.0).

- Print fully qualified class of options in `--show-params` output.
- Add new columns in `--show-params` table to show option specifications, configuration exclusion and exposed attribute.
- Rename `ignored_params` argument to `exclude_params` on the `ConfigOption` class.
- Blocking parameters from configuration files now requires the fully qualified ID. Which adds support for selectively blocking parameters at any subcommand level.

## [`3.4.1` (2022-12-08)](https://github.com/kdeldycke/click-extra/compare/v3.4.0...v3.4.1)

> [!NOTE]
> `3.4.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.4.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.4.1).

- Fix highlighting of `+`-prefixed options in help screens. Closes {issue}`316`.
- Fix highlighting of hard-coded deprecated labels in option help.
- Document parameter introspection. Closes {issue}`319`.

## [`3.4.0` (2022-12-01)](https://github.com/kdeldycke/click-extra/compare/v3.3.4...v3.4.0)

> [!NOTE]
> `3.4.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.4.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.4.0).

- Streamline setup of Sphinx extensions.
- Document `click:example` and `click:run` Sphinx extensions.

## [`3.3.4` (2022-11-14)](https://github.com/kdeldycke/click-extra/compare/v3.3.3...v3.3.4)

> [!NOTE]
> `3.3.4` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.3.4/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.3.4).

- Fix some types.

## [`3.3.3` (2022-11-14)](https://github.com/kdeldycke/click-extra/compare/v3.3.2...v3.3.3)

> [!NOTE]
> `3.3.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.3.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.3.3).

- Fix release workflow.

## [`3.3.2` (2022-11-14)](https://github.com/kdeldycke/click-extra/compare/v3.3.1...v3.3.2)

> [!NOTE]
> `3.3.2` is available on [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.3.2).

> [!WARNING]
> `3.3.2` is **not available** on 🐍 PyPI.

- Remove use of deprecated `::set-output` directives and replace them by environment files.

## [`3.3.1` (2022-11-11)](https://github.com/kdeldycke/click-extra/compare/v3.3.0...v3.3.1)

> [!NOTE]
> `3.3.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.3.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.3.1).

- Keep a copy of the table format ID in the context when set.

## [`3.3.0` (2022-11-11)](https://github.com/kdeldycke/click-extra/compare/v3.2.5...v3.3.0)

> [!NOTE]
> `3.3.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.3.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.3.0).

- Use `tabulate` dependency instead of `cli-helpers` for all the table rendering utilities.
- Remove dependency on `cli-helpers`.
- Re-implement locally the `vertical` table rendering format from `cli-helpers`.
- Add new table rendering formats: `asciidoc`, `fancy_outline`, `heavy_grid`, `heavy_outline`, `latex_longtable`, `latex_raw`, `mixed_grid`, `mixed_outline`, `presto`, `pretty`, `unsafehtml` and `youtrack`.
- Remove `minimal` table rendering formats, which was an alias of `plain`.
- Add new `csv-excel`, `csv-excel-tab` and `csv-unix` formats based on Python defaults dialects.
- Remove `csv-tab` rendering format.
- Make `csv` format an alias of `csv-excel`.
- Deactivate number alignment and extra-spacing in table rendering by default.
- Remove tests on Pypy. Nobody asked for it and I need to speed up tests.

## [`3.2.5` (2022-09-30)](https://github.com/kdeldycke/click-extra/compare/v3.2.4...v3.2.5)

> [!NOTE]
> `3.2.5` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.2.5/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.2.5).

- Fix argument's property getter in `--show-params`.
- Remove GitHub edit link workaround in documentation.

## [`3.2.4` (2022-09-27)](https://github.com/kdeldycke/click-extra/compare/v3.2.3...v3.2.4)

> [!NOTE]
> `3.2.4` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.2.4/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.2.4).

- Add citation file.
- Fix type casting.

## [`3.2.3` (2022-09-27)](https://github.com/kdeldycke/click-extra/compare/v3.2.2...v3.2.3)

> [!NOTE]
> `3.2.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.2.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.2.3).

- Increase type coverage.

## [`3.2.2` (2022-09-26)](https://github.com/kdeldycke/click-extra/compare/v3.2.1...v3.2.2)

> [!NOTE]
> `3.2.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.2.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.2.2).

- Fix bad typing import.

## [`3.2.1` (2022-09-26)](https://github.com/kdeldycke/click-extra/compare/v3.2.0...v3.2.1)

> [!NOTE]
> `3.2.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.2.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.2.1).

- Move some command utility from test machinery to `run` submodule.

## [`3.2.0` (2022-09-25)](https://github.com/kdeldycke/click-extra/compare/v3.1.0...v3.2.0)

> [!NOTE]
> `3.2.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.2.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.2.0).

- New `--show-params` option to debug parameters defaults, values, environment variables and provenance.
- Rename `ignored_options` to `ignored_params` on `ConfigOption`.
- Highlight command's metavars, default values and deprecated flag in help.
- Finer highlighting of options, subcommands and their aliases in help screens.
- Fix highlight of dynamic metavars and secondary option in help screen.
- New custom `ExtraContext` which allows populating `meta` at instantiation.
- Use the `Formats` enum to encode for default configuration file extensions.
- Re-introduce `*.yml` as a possible extension for YAML files.

## [`3.1.0` (2022-09-20)](https://github.com/kdeldycke/click-extra/compare/v3.0.1...v3.1.0)

> [!NOTE]
> `3.1.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.1.0).

- Add support for pattern matching to search for configuration file.
- Add a new `formats` option to specify which dialects the configuration file is written in, regardless of its name or file extension. Closes {issue}`197`.
- Set default configuration folder according each OS preferred location. Closes {issue}`211`.
- Add `roaming` and `force_posix` option to influence default application directory of configuration file.
- Add a `ignored_options` parameter to the configuration file instead of hard-coding them.
- Add dependency on `wcmatch`.
- Remove tests on deprecated `ubuntu-18.04`.
- Document preset options overriding. Closes {issue}`232`.
- Document configuration option pattern matching and default folder. Closes {issue}`197` and {issue}`211`.

## [`3.0.1` (2022-08-07)](https://github.com/kdeldycke/click-extra/compare/v3.0.0...v3.0.1)

> [!NOTE]
> `3.0.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.0.1).

- Fix wrong dependency bump on `pytest-cov` produced by major release.

## [`3.0.0` (2022-08-07)](https://github.com/kdeldycke/click-extra/compare/v2.1.3...v3.0.0)

> [!NOTE]
> `3.0.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.0.0).

- Make default extra features optional, so `click_extra` can act as a drop-in replacement for `click` and `cloup` (closes {issue}`173`):
  - Rename `click_extra.group` to `click_extra.extra_group`.
  - Rename `click_extra.command` to `click_extra.extra_command`.
  - Alias `click_extra.group` to `cloup.group`.
  - Alias `click_extra.command` to `cloup.group`.
- Use declarative `params=` argument to set defaults options on `extra_command` and `extra_group`.
- Move the implementation of options to classes.
- Hard-copy `version_option` code from `click` to allow for more flexibility. Addresses {issue}`176`.
- All custom options inherits from `ExtraOption` class.
- New `extra_option_at_end` to `extra_command` to force position of all extra options (on by default).
- Replace theme styles inherited from `click-log` by Python standard `logging` module. Adds `info` and removes `exception` styles.
- Add a tutorial in documentation.
- Add support for `click:example` and `click:run` directives in documentation.
- Add ANSI session and console lexers for Pygments.
- Add a Pygments filter to transform tokens into ANSI tokens.
- Add custom Pygment style to render ANSI tokens in `furo` theme.
- Add dependency on `pygments`, `pygments-ansi-color` and `Pallets-Sphinx-Themes`.
- Allow translation of short help in extra options.
- Add minimal type hints.
- Pre-compute test matrix to allow for a subset of jobs to fail if flagged as unstable.
- Run tests on `ubuntu-22.04` and `macos-12`.
- Remove tests on deprecated `macos-10.15`.

## [`2.1.3` (2022-07-08)](https://github.com/kdeldycke/click-extra/compare/v2.1.2...v2.1.3)

> [!NOTE]
> `2.1.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/2.1.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v2.1.3).

- Do not render `None` cells in tables with `<null>` string.
- Disable workflow grouping and concurrency management.

## [`2.1.2` (2022-06-27)](https://github.com/kdeldycke/click-extra/compare/v2.1.1...v2.1.2)

> [!NOTE]
> `2.1.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/2.1.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v2.1.2).

- Fix auto-mapping and recognition of all missing Click option types in config module. Closes {issue}`170`.
- Fix CI workflow grouping.

## [`2.1.1` (2022-05-22)](https://github.com/kdeldycke/click-extra/compare/v2.1.0...v2.1.1)

> [!NOTE]
> `2.1.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/2.1.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v2.1.1).

- Fix compatibility with `cloup >= 0.14.0`.
- Group workflow jobs so new commits cancels in-progress execution triggered by previous commits.
- Run tests on early Python 3.11 releases.

## [`2.1.0` (2022-04-22)](https://github.com/kdeldycke/click-extra/compare/v2.0.2...v2.1.0)

> [!NOTE]
> `2.1.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/2.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v2.1.0).

- Add a `highlight` utility to style substrings.
- Add `regex` dependency.

## [`2.0.2` (2022-04-14)](https://github.com/kdeldycke/click-extra/compare/v2.0.1...v2.0.2)

> [!NOTE]
> `2.0.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/2.0.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v2.0.2).

- Fix and unittest derivation of configuration template and types from CLI
  options.
- Fix dependency requirements induced by overzealous automatic post-release
  version bump workflow.
- Replace `sphinx_tabs` by `sphinx-design`.
- Add edit link to documentation pages.

## [`2.0.1` (2022-04-13)](https://github.com/kdeldycke/click-extra/compare/v2.0.0...v2.0.1)

> [!NOTE]
> `2.0.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/2.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v2.0.1).

- Fix mapping of file arguments in configuration files.
- Fix Sphinx documentation update and publishing.
- Run tests on `pypy-3.7`.

## [`2.0.0` (2022-04-11)](https://github.com/kdeldycke/click-extra/compare/v1.9.0...v2.0.0)

> [!NOTE]
> `2.0.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/2.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v2.0.0).

- Add support for XML configuration file. Closes {issue}`122`.
- Add strict mode to fail on unrecognized configuration options.
- Support the `NO_COLOR` environment variable convention from
  [`no-color.org`](https://no-color.org).
- Recognize a subset of `(FORCE_)(CLI)(NO_)COLOR(S)(_FORCE)` variations as
  color-sensitive environment variables.
- Print version and environment details in logs at the `DEBUG` level.
- Add Sphinx-based documentation.
- Add a logo.
- Outsource documentation publishing to external workflow.

## [`1.9.0` (2022-04-08)](https://github.com/kdeldycke/click-extra/compare/v1.8.0...v1.9.0)

> [!NOTE]
> `1.9.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.9.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.9.0).

- Add supports for `.ini` configuration files.
- Add supports for commented JSON configuration files.
- Fix identification of TOML and JSON configuration files.
- Fix leak of local environment variable update on `extend_env()` usage.
- Ignore `help` boolean in configuration files.
- Add new dependency on `mergedeep`.

## [`1.8.0` (2022-04-03)](https://github.com/kdeldycke/click-extra/compare/v1.7.0...v1.8.0)

> [!NOTE]
> `1.8.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.8.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.8.0).

- Split the `print_cli_output` method to expose the simpler `format_cli` utility.

## [`1.7.0` (2022-03-31)](https://github.com/kdeldycke/click-extra/compare/v1.6.4...v1.7.0)

> [!NOTE]
> `1.7.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.7.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.7.0).

- Refactor global logging management.
- Remove `click_extra.run.run` and rebase all run utilities around `subprocess.run`.
- Use the `tomllib` from the standard library starting with Python 3.11.

## [`1.6.4` (2022-03-04)](https://github.com/kdeldycke/click-extra/compare/v1.6.3...v1.6.4)

> [!NOTE]
> `1.6.4` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.6.4/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.6.4).

- Fix extension of default environment variables.

## [`1.6.3` (2022-03-04)](https://github.com/kdeldycke/click-extra/compare/v1.6.2...v1.6.3)

> [!NOTE]
> `1.6.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.6.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.6.3).

- Add support for environment variables to run utilities.

## [`1.6.2` (2022-03-03)](https://github.com/kdeldycke/click-extra/compare/v1.6.1...v1.6.2)

> [!NOTE]
> `1.6.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.6.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.6.2).

- Temporarily skip displaying environment details in `--version` option results
  for `python >= 3.10`.
- Reactivate all tests on Python 3.10.

## [`1.6.1` (2022-03-02)](https://github.com/kdeldycke/click-extra/compare/v1.6.0...v1.6.1)

> [!NOTE]
> `1.6.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.6.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.6.1).

- Expose some `cloup` versions of `click` utilities at the root of
  `click_extra`.

## [`1.6.0` (2022-03-02)](https://github.com/kdeldycke/click-extra/compare/v1.5.0...v1.6.0)

> [!NOTE]
> `1.6.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.6.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.6.0).

- Allow `click_extra` to be imported as a drop-in replacement for `click`.
- Share the same set of default options between `click_extra.command` and
  `click_extra.group`.
- Document default help screen comparison between simple `click` CLI and
  enhanced `click-extra` CLI.

## [`1.5.0` (2022-02-21)](https://github.com/kdeldycke/click-extra/compare/v1.4.1...v1.5.0)

> [!NOTE]
> `1.5.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.5.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.5.0).

- Add support for JSON configuration file.
- Search all supported formats in default location if configuration file not
  provided.
- Print configuration file default location in help screens.

## [`1.4.1` (2022-02-13)](https://github.com/kdeldycke/click-extra/compare/v1.4.0...v1.4.1)

> [!NOTE]
> `1.4.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.4.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.4.1).

- Add new external workflow to modernize Python code.
- Use external workflow suite to manage changelog and build & publish packages
  on PyPI on release.
- Use external workflow to label sponsored issues and PRs.
- Replace local workflow by external one to label issues and PRs.
- Reuse externnal workflow to produce dependency graph.
- Remove dev dependencies on `check-wheel-contents`, `graphviz`, `pipdeptree`
  and `twine`.

## [`1.4.0` (2022-01-08)](https://github.com/kdeldycke/click-extra/compare/v1.3.0...v1.4.0)

> [!NOTE]
> `1.4.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.4.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.4.0).

- Allow downloading of a remote config URL.
- Add new dependencies on `requests` and `pytest-httpserver`.
- Fix inference of config file top-level section name.
- Document usage of `click_extra.config.config_option`.
- Use external workflows for GitHub actions.
- Automate version and changelog management.

## [`1.3.0` (2021-11-28)](https://github.com/kdeldycke/click-extra/compare/v1.2.2...v1.3.0)

> [!NOTE]
> `1.3.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.3.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.3.0).

- Add support for YAML configuration file. Closes #13.
- Auto-detect configuration file on loading.
- Add `pyyaml` dependency.

## [`1.2.2` (2021-11-04)](https://github.com/kdeldycke/click-extra/compare/v1.2.1...v1.2.2)

> [!NOTE]
> `1.2.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.2.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.2.2).

- Evaluate format option dynamically at use to let third-party register new
  rendering formats.

## [`1.2.1` (2021-11-04)](https://github.com/kdeldycke/click-extra/compare/v1.2.0...v1.2.1)

> [!NOTE]
> `1.2.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.2.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.2.1).

- Fix creation of post-release version bump PR on tagging.

## [`1.2.0` (2021-11-03)](https://github.com/kdeldycke/click-extra/compare/v1.1.1...v1.2.0)

> [!NOTE]
> `1.2.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.2.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.2.0).

- Extend `cli-helper.TabularOutputFormatter` with new formats: `simple_grid`,
  `rounded_grid`, `double_grid`, `outline`, `simple_outline`, `rounded_outline`
  and `double_outline`. Address {issue}`astanin/python-tabulate#151`.
- Add a new `--table-format`/`-t` option to select table format rendering mode.
- Add new dependency on `cli-helper` and `tabulate`.
- Automate post-release version bump.

## [`1.1.1` (2021-11-01)](https://github.com/kdeldycke/click-extra/compare/v1.1.0...v1.1.1)

> [!NOTE]
> `1.1.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.1.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.1.1).

- Fix printing of additional non-grouped default options in help screen.

## [`1.1.0` (2021-10-28)](https://github.com/kdeldycke/click-extra/compare/v1.0.1...v1.1.0)

> [!NOTE]
> `1.1.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.1.0).

- Add a `--config`/`-C` option to load CLI configuration from a TOML file.

## [`1.0.1` (2021-10-27)](https://github.com/kdeldycke/click-extra/compare/v1.0.0...v1.0.1)

> [!NOTE]
> `1.0.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/1.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.0.1).

- Re-release previous version with fixed dependency.

## [`1.0.0` (2021-10-27)](https://github.com/kdeldycke/click-extra/compare/v0.0.1...v1.0.0)

> [!NOTE]
> `1.0.0` is available on [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v1.0.0).

> [!WARNING]
> `1.0.0` is **not available** on 🐍 PyPI.

- Add colorization of options, choices and metavars in help screens.
- Add `--color`/`--no-color` option flag (aliased to `--ansi`/`--no-ansi`).
- Add colored `--version` option.
- Add colored `--verbosity` option and logs.
- Add dependency on `click-log`.
- `--time`/`--no-time` flag to measure duration of command execution.
- Add platform recognition utilities.
- Add new conditional markers for `pytest`: `@skip_{linux,macos,windows}`,
  `@unless_{linux,macos,windows}`, `@destructive` and `@non_destructive`.

## [`0.0.1` (2021-10-18)](https://github.com/kdeldycke/click-extra/compare/88b81e...v0.0.1)

> [!NOTE]
> `0.0.1` is the *first version* available on [🐍 PyPI](https://pypi.org/project/click-extra/0.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v0.0.1).

- Initial public release.
