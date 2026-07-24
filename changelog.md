# Changelog

## [`8.6.2.dev0` (unreleased)](https://github.com/kdeldycke/click-extra/compare/v8.6.1...main)

> [!WARNING]
> This version is **not released yet** and is under active development.

## [`8.6.1` (2026-07-24)](https://github.com/kdeldycke/click-extra/compare/v8.6.0...v8.6.1)

## [`8.6.0` (2026-07-24)](https://github.com/kdeldycke/click-extra/compare/v8.5.0...v8.6.0)

- Add `OperationTrail`, the batch-reporting companion of `run_jobs`/`run_lanes`: each operation leaves a persistent `✓`/`✘` line and the batch closes with a timed summary. Adds the `trail_glyph` and `trail_line` helpers.
- Add `column-order` and `row-order` options to `{matrix}` blocks (`newest-first`/`oldest-first`), defaulting both axes to `newest-first` so the most recent compatibility information reads from the upper-left corner.
- Refresh each `python:render` `:mirror:` block through `click-extra refresh-directives` with the source file's directory on `sys.path`, so a block importing a sibling helper module resolves offline as it does at build time.
- Fix `test-suite --command` resolving a venv's symlinked Python interpreter (`.venv/bin/python`) to its base target, silently dropping the venv's installed packages.
- Upload coverage from the once-only test job to Codecov, and move the package-install CLI checks to a dedicated CI job skipped on pull requests.

## [`8.5.0` (2026-07-22)](https://github.com/kdeldycke/click-extra/compare/v8.4.0...v8.5.0)

> [!NOTE]
> `8.5.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.5.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v8.5.0).

- **Breaking:** Rename the `--show-params` flag to `--params`. Its parameter ID changes from `show_params` to `params`, its environment variable suffix from `_SHOW_PARAMS` to `_PARAMS`, and `click-extra wrap --show-params` becomes `click-extra wrap --params`. `ShowParamsOption` and `@show_params_option` keep their names.
- Add the `click_extra.sphinx.myst_docstrings` Sphinx extension: write Python docstrings in MyST markdown, transparently converted to reST at build time, keeping `sphinx.ext.autodoc` and `sphinx_autodoc_typehints` unmodified. Absorbed from `repomatic.myst_docstrings`.
- Add a `convert-to-myst` subcommand migrating a package's reST docstrings and comments to MyST in place, idempotently: string literals and other runtime code pass through byte-for-byte. Absorbed from `repomatic`, along with the `sphinx-apidoc` stub converter `click_extra.rst_to_myst` and the public `convert_source()`.
- Add a `:mirror:` flag to the `python:render` Sphinx directive: the block's generated Markdown is mirrored into the source `.md` between `<!-- mirror -->` markers, reviewable in raw diffs; builds regenerate it in memory, never writing to the source.
- Extend `click-extra refresh-directives` to also refresh `python:render` `:mirror:` regions, alongside `{matrix}` blocks, by executing each mirror block's Python.
- Add a `start_new_session` option to `run_cli()`: the child leads its own POSIX session and process group, and every kill path signals the whole group, so grandchildren are reaped. Off by default to keep interactive prompts working; no-op on Windows.
- Add a `themes` demo subcommand (`click-extra themes`) printing a sample help screen rendered under every built-in theme, for a quick terminal preview of all palettes.
- Promote `ctx.render_table` and `ctx.print_table` to methods on `click_extra.Context`, reading the `--table-format` and `--sort-by` selections from the context's shared `meta` so they work from any subcommand. `TableFormatOption` and `SortByOption` remain drop-ins on click and cloup commands; `ctx.render_table` now honors `--sort-by`.
- Warn on configuration keys unknown to the `config_schema` when the section is schema-only, instead of dropping them silently; strict mode still raises, and sections mixing CLI parameters stay silent. Exposed as `warn_unknown` on `make_schema_callable()` and `schema_warn_unknown` on `run_config_validation()`.
- Convert all of click-extra's own docstrings and comments from reST to MyST.
- Fix a group-level `--theme` not reaching the CLI wrapped by `click-extra wrap`: the target's help now renders in the chosen palette instead of falling back to the default `dark` theme.
- Fix `click-extra refresh-directives` rewriting `{matrix}` examples nested inside longer code fences: documented illustrations are copied verbatim, never refreshed or executed.

## [`8.4.0` (2026-07-16)](https://github.com/kdeldycke/click-extra/compare/v8.3.0...v8.4.0)

> [!NOTE]
> `8.4.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.4.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v8.4.0).

- **Breaking:** Remove the historical `from click_extra.version import prebake_*` compatibility imports; the pre-baking helpers are only importable from `click_extra.prebake`.
- **Breaking:** Remove the leaked `annotations` and `warnings` entries from the package's public API: both were star-import artifacts, not Click, Cloup or Click Extra API.
- **Breaking:** Move `args_cleanup`, `format_cli_prompt`, `PROMPT` and `INDENT` from `click_extra.testing` to `click_extra.execution`; all but `PROMPT` stay importable from their historical home.
- **Breaking:** Remove the dead `CarapaceCompletion.is_empty()` method and the deprecated alert parser's `current_depth()`.
- Add a `--tree` flag to the default option set: it prints the whole hierarchy of nested subcommands as a tree (names, aliases, operand metavars and one-line descriptions), then exits. The new `click_extra.tree` module exposes `render_command_tree()`, `TreeOption` and `@tree_option`.
- Add a `--tree` mode to `click-extra wrap`: prints the subcommand tree of any foreign Click CLI without running it, with the same target resolution as `--show-params` and `--man`.
- Help screens and the `--tree` view now style subcommand aliases with the `alias` theme slot and their parenthetical punctuation with `alias_secondary`; aliases used to take the `subcommand` slot and the punctuation stayed plain.
- Table formats able to express styles natively (`html`, `unsafehtml`, `mediawiki`, `textile`, `jira` and the four `latex*` variants) now translate the ANSI codes carried by cells and headers to the format's own styling markup instead of stripping them.
- An explicit `--color` no longer injects raw ANSI codes into the markup formats supporting native styling; the raw passthrough escape hatch remains for the formats without.
- Add `split_ansi()` and `render_ansi()` plus the `ansi_to_html()`, `ansi_to_jira()`, `ansi_to_latex()` and `ansi_to_textile()` converters to `click_extra.styling`.
- Add `run_cli(args)` to `click_extra.execution`: a `subprocess.run` work-alike that logs the invocation as a copy-pasteable prompt line and streams the child's output to the logger as it is produced; a per-call `label` tags each streamed record.
- `format_cli_prompt` now styles each token family with the theme slot it holds elsewhere in a CLI's output; the binary-path renderer behind it is public as `highlight_bin_name(program)`.
- Add the `Duration` parameter type to `click_extra.types`: parses a friendly duration (`7 days`, `12h`), an ISO 8601 duration (`P7D`) or an RFC 3339 timestamp into a `datetime.timedelta`; zero, empty and future values parse to `None`.
- One `--sort-by` can now serve subcommands rendering heterogeneous tables: `SortByOption` accepts bare column IDs resolved per table, `print_table()` and `render_table()` headers accept `ColumnSpec` instances and `(label, column_id)` pairs, and `column_sort_key()` is public. An explicit `default=()` declares no default sort.
- Add the `isolated_app_dir` fixture to `click_extra.pytest`: repoints `click.get_app_dir`-based configuration discovery at a fresh per-test directory, so in-process CLI invocations never read the host's real configuration folder.
- Add `install_interrupt_handler(ctx)` and `terminate_live_processes()` to `click_extra.execution`: the first Ctrl+C now `SIGTERM`s every subprocess spawned through `run_cli`.
- Log records emitted while a `Spinner` animates on the same stream are now printed through `Spinner.echo()`, on their own line above the animation, instead of garbling the in-progress frame. Adds `active_spinner()` to `click_extra.spinner`.
- Add `temporary_env()` to `click_extra.envvar`: a context manager applying environment variable changes for the duration of a block, then restoring every touched variable.
- Expose `generator_tag()` in `click_extra.parameters`: the provenance tag stamped into generated man pages and Carapace completion specs.
- Unify the palettes materializing the 16 ANSI colors as concrete RGB: `Style` CSS output, contrast math and the first 16 slots of the indexed palette now share the palette the documentation renders terminal sessions with.
- `select_row` accepts any `Mapping`, not just `dict`, so read-only row shapes project without a copy.
- `test-suite` now runs its target binaries through `run_cli`: each invocation is disclosed as a themed prompt line and its output streams live to `DEBUG` logs.
- `print_table()` now honors a `--color` forced on a parent group: the raw-ANSI escape hatch used to be ignored when the color option was not declared on the very command printing the table.
- `--color`/`--no-color` now reach output produced from background threads: `StreamHandler` consults the process-wide `invocation_color()` instead of `click.echo`'s thread-local context lookup.
- `Formatter` no longer mutates a record's `levelname` in place: a record formatted several times no longer accumulates styling or glued labels.
- `Style.from_ansi()` now parses the parameter-less reset escape (`\x1b[m`) and ignores all selective reset codes (`22`-`29`, `39`, `49`, `55`), not just the full `0` reset.
- `ConfigOption.excluded_params` now resolves the CLI's `--help` option ID from Click at runtime instead of assuming it is named `help`; the option keeps being excluded from configuration files if Click ever renames it.
- `ExtraOption.handle_parse_result` now pre-records the parameter source of every option, not just eager ones, so non-eager callbacks and types keep introspecting their provenance on Click `8.4.0`.
- The `--jobs` sequential-execution warning now fires only for an explicit `auto`/`max` request; the option's own default logs it at info level.
- `test-suite` no longer crashes on non-UTF-8 binary output: undecodable bytes are escaped into the captured stream, and the subprocess inherits `PYTHONIOENCODING=utf8`.
- A `test-suite` case skipped by `only_platforms` now reports the platforms it requires; the message used to name the current platform.
- `regex_fullmatch_line_by_line` now reports a regular line mismatch instead of crashing with an `IndexError` when the regex and the checked content do not have the same number of lines.
- Add a binaries page to the documentation: a searchable, sortable catalog of every released standalone executable with download links, VirusTotal analyses and a detection trend chart.
- Coverage now uploads to Codecov from one runner per OS and Python version, on released Click and Cloup only; the Test Analytics upload and its `junit.xml` artifact are dropped.

## [`8.3.0` (2026-07-08)](https://github.com/kdeldycke/click-extra/compare/v8.2.0...v8.3.0)

> [!NOTE]
> `8.3.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.3.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v8.3.0).

- Add a `click:config` Sphinx directive documenting a CLI's `config_schema`: a summary table plus one section per option, with docstring, type, default, and a TOML example. Adds `schema_field_infos()`, `field_docstrings()` and `SchemaFieldInfo` to the public API.
- Disable mouse zoom on the class inheritance diagrams of the documentation's API sections, so they no longer hijack page scrolling; the fullscreen viewer keeps zoom.
- Add tests covering 256-color palette index `0` and empty-string colors in `Style`, gated on runtime probes of Click `8.5.0`'s color validation.

## [`8.2.0` (2026-07-01)](https://github.com/kdeldycke/click-extra/compare/v8.1.4...v8.2.0)

> [!NOTE]
> `8.2.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.2.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v8.2.0).

- Add a `--export-config FORMAT` option to every `@command` and `@group`: it renders the resolved configuration on `<stdout>` in any writable format (`toml`, `yaml`, `json`, `json5`, `jsonc`, `hjson`, `xml`), then exits. Adds `ExportConfigOption`, `@export_config_option` and `SERIALIZABLE_FORMATS` to the public API.
- Add `--theme=auto`: it selects the `dark` or `light` palette from the terminal background, detected from `CLITHEME`, `COLORFGBG` or a live OSC 11 query; the default stays `dark`. Adds `resolve_background` and `query_osc_background` to `click_extra.color`, `resolve_auto_theme` and `AUTO_THEME` to `click_extra.theme`.
- Add `run_lanes(func, lanes)` and `resolve_jobs(ctx, count)` to `click_extra.execution`: run each lane serially while distinct lanes run concurrently, sized by `--jobs`; expose the worker-count policy shared with `run_jobs`. A `serial_at_debug` keyword collapses both fan-outs to sequential at `DEBUG` verbosity.
- Add the always-on `matrix` Sphinx directive, rendering a package's release compatibility matrix from its git tags, for the Python interpreter (`{matrix} python`) or a dependency (`{matrix} <distribution>`) axis; a comment-marker form renders the embedded table on GitHub too.
- Add the `click-extra refresh-directives` command (wrapping `click_extra.sphinx.matrix.update_matrix_blocks`) to regenerate the tables embedded in `{matrix}` directive blocks and `<!-- matrix … -->` marker regions; its `--check` mode flags stale tables in CI.
- Publish `format_cli_prompt` in `click_extra.testing` (was the private `_format_cli_prompt`): render a themed, copy-pasteable prompt simulating a CLI invocation.
- Fix Carapace dynamic completion: an option's value or a subcommand argument with a custom `shell_complete` now resolves through the generated spec, instead of returning empty or root-level candidates.
- Fix `EnumChoice` shell completion on Click 8.4.0: completion candidates are now normalized, so they match the option's accepted values instead of appearing as raw uppercase enum names.
- Fix `run_jobs` blocking on Ctrl+C during parallel execution: an interrupt now drops queued items and returns immediately, instead of waiting for every in-flight task to finish.
- Add a documentation page on Typer compatibility, explaining why click-extra cannot be combined with Typer and how to get the same options natively.

## [`8.1.4` (2026-06-27)](https://github.com/kdeldycke/click-extra/compare/v8.1.3...v8.1.4)

> [!NOTE]
> `8.1.4` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.1.4/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v8.1.4).

- Skip the `EnumChoice` shell-completion case-folding test on Click 8.3.

## [`8.1.3` (2026-06-27)](https://github.com/kdeldycke/click-extra/compare/v8.1.2...v8.1.3)

> [!NOTE]
> `8.1.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.1.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v8.1.3).

- Mark test as network-dependent.

## [`8.1.2` (2026-06-27)](https://github.com/kdeldycke/click-extra/compare/v8.1.1...v8.1.2)

> [!NOTE]
> `8.1.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.1.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v8.1.2).

- The `runner` pytest fixture now pins `HOME` and its platform equivalents inside its isolated filesystem, making configuration-file discovery independent of the ambient environment.
- The Sphinx, MkDocs and Carapace tests now self-skip when their optional dependencies are missing, so downstream packagers no longer need to `--ignore` them.

## [`8.1.1` (2026-06-24)](https://github.com/kdeldycke/click-extra/compare/v8.1.0...v8.1.1)

> [!NOTE]
> `8.1.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.1.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v8.1.1).

- Fix `multiple` and variadic (`nargs=-1`) options typed with `EnumChoice`: their tuple default was stringified as a whole (`str((MyEnum.FOO,))`) instead of per member, so the default tripped Click's `Value must be an iterable` check when the option was left unset.
- Fix `decorator_factory` leaking options across reuses of a pre-instantiated decorator: applying the same `command()` or `group()` decorator to several functions accumulated duplicate parameters, because Click extended its shared `params` list in place on each use.

## [`8.1.0` (2026-06-24)](https://github.com/kdeldycke/click-extra/compare/v8.0.1...v8.1.0)

> [!NOTE]
> `8.1.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v8.1.0).

- **Breaking:** Rename the `test-plan` subcommand to `test-suite`, its `--plan-file`/`--plan-envvar` options to `--suite-file`/`--suite-envvar`, its `[tool.<cli>.test-plan]` config section to `[tool.<cli>.test-suite]`, the `click_extra.test_plan` module to `click_extra.test_suite`, and the `TestPlanConfig`/`parse_test_plan`/`run_test_plan`/`DEFAULT_TEST_PLAN` API to `TestSuiteConfig`/`parse_test_suite`/`run_test_suite`/`DEFAULT_TEST_SUITE`. The `CLITestCase` class and the `[[cases]]` file structure keep their names.
- **Breaking:** Replace the test-suite config's `inline` field with a native `cases` array under `[tool.<cli>.test-suite.cases]` (or set `file` to a suite path). Adds the `cases` field to `TestSuiteConfig` and the `cases_from_data` helper.
- **Breaking:** `ClickExtraConfig`, `TestSuiteConfig`, and `PrebakeConfig` are no longer re-exported from the top-level `click_extra` namespace; import them from `click_extra.config`.
- Add a [Carapace](https://carapace.sh) completion exporter: the `click_extra.carapace` module serializes a Click command tree to [carapace-spec](https://github.com/carapace-sh/carapace-spec) YAML for native shell completion, behind a new `carapace` extra. The `to_carapace_spec`, `dump_carapace_spec`, `write_carapace_spec` and `install_carapace_spec` API answers [`click#3188`](https://github.com/pallets/click/issues/3188).
- Add a `--carapace` mode to the `wrap` command: `click-extra wrap --carapace SCRIPT` prints the target CLI's spec, and `--install` writes it into Carapace's user spec directory. Mutually exclusive with `--man` and `--show-params`.
- The `wrap` command now accepts a local project directory, reading its console-script entry point from `pyproject.toml` or `setup.cfg` so a checked-out project can be wrapped without installing it first.
- Add the `@sort_by_option` decorator for the `--sort-by` table option, composing with option groups and constraints; it accepts `ColumnSpec` definitions and a `columns=` registry so one column tuple drives both `--columns` and `--sort-by`. Closes [`click-extra#1777`](https://github.com/kdeldycke/click-extra/issues/1777).
- Decorators built by `decorator_factory` carry proper signatures: their option class's constructor surfaces in `help()`, the REPL and autodoc, and overloaded type hints let basedpyright, pyright and mypy infer the produced command or decorated callback. Closes [`click-extra#1781`](https://github.com/kdeldycke/click-extra/issues/1781).
- `@version_option` accepts an explicit version string as its first positional argument (`@version_option("1.2.3")`), for drop-in compatibility with Click.
- A test-suite file may now be in any list-capable config format detected from its extension: TOML and JSON (built-in), plus YAML, JSON5, JSONC and Hjson (with their extras). Adds the `load_test_suite` helper and `SUITE_FORMATS` constant.
- Accept a bare integer `timeout` in a test-suite case, coercing it to a float instead of rejecting it.
- Default the test-suite config file to `./tests/cli-test-suite.toml`, which parses with the built-in `tomllib` and so needs no optional extra.
- Add an `all` extra that pulls in every optional feature at once.
- Centralize config format reading, serialization, and detection in `click_extra.config` with the new `serialize_content`, `read_file`, and `format_from_path` helpers, joining the existing `parse_content`.
- Add `iter_subcommands` and `make_resilient_context` to `click_extra.parameters` for enumerating a group's visible subcommands and building a parse-free introspection context.
- Add the `CONFIG_PATH_METADATA_KEY` and `NORMALIZE_KEYS_METADATA_KEY` named constants for the schema field-metadata keys, alongside the existing `EXTENSION_METADATA_KEY`.
- Man pages now render optional-value options like `--color` as `--color[=auto|always|never]` and drop the spurious value metavar on repeatable count options like `-v`/`--verbose`.
- When introspection (`--man`, `--show-params`, `--carapace`) cannot find a Click command in the resolved module, the error now explains that an entry point importing its command lazily must be addressed with `module:function` notation.
- Unify the "missing optional dependency" error messages behind a shared `missing_extra_message` helper, pointing at the canonical `pip install click-extra[<extra>]` install target.
- Restrict pytest collection to the `tests` folder and switch to `importlib` import mode, fixing `import file mismatch` errors when building from a packaged source tree alongside an installed copy. Closes [`click-extra#1779`](https://github.com/kdeldycke/click-extra/issues/1779).
- Show the same configuration across all eight supported formats (TOML, YAML, JSON, JSON5, JSONC, Hjson, INI, XML) in a tabbed block in the configuration docs.
- Silence ambiguous cross-reference warnings in the Sphinx documentation build for the `ColumnSpec`, `ConfigFormat`, `ConfigValidator` and `LogLevel` classes re-exported at the package root.

## [`8.0.1` (2026-06-22)](https://github.com/kdeldycke/click-extra/compare/v8.0.0...v8.0.1)

> [!NOTE]
> `8.0.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v8.0.1).

- Redo a proper release.

## [`8.0.0` (2026-06-22)](https://github.com/kdeldycke/click-extra/compare/v7.20.1...v8.0.0)

> [!NOTE]
> `8.0.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/8.0.0/).

> [!WARNING]
> `8.0.0` is **not available** on 🐙 GitHub.

- **Breaking:** Drop the `Extra` prefix from public classes (`ExtraCommand` to `Command`, `ExtraGroup` to `Group`, `ExtraContext` to `Context`, `ExtraVersionOption` to `VersionOption`, and eight more); `ExtraOption` keeps its prefix.
- **Breaking:** Remove the deprecated `extra_command`, `extra_group` and `extra_version_option` aliases; use `command`, `group` and `version_option` instead.
- **Breaking:** `VersionOption` and `@version_option` now take `fields={...}` and `styles={...}` mappings instead of per-field value and `*_style` parameters; `message`/`message_style` are unchanged.
- **Breaking:** Replace the `--color`/`--no-color` boolean with the GNU tri-state `--color[=WHEN]` (`auto`, `always`, `never`), defaulting to `auto`; a bare `--color` means `always`.
- **Breaking:** Remove the `--ansi`/`--no-ansi` aliases of `--color`/`--no-color`.
- **Breaking:** Remove the `show-params` and `man` subcommands; use `click-extra wrap --show-params` and `click-extra wrap --man` instead.
- **Breaking:** Rename the `click_extra.wrap` module to `click_extra.cli_wrapper`; update any `from click_extra.wrap import ...` accordingly.
- **Breaking:** Reorganize the configuration subsystem into a `click_extra.config` package with `schema`, `formats`, and `option` submodules; public symbols stay importable from `click_extra.config`.
- **Breaking:** Split `click_extra.colorize` into `click_extra.highlight` (help-screen highlighting) and `click_extra.color` (color-mode resolution); root re-exports unchanged, update deeper imports.
- **Breaking:** Split the theme palette and HTML renderer into `click_extra.theme_docs` and the spinner preset catalog into `click_extra.spinner_presets`; root re-exports unchanged, update deeper imports.
- **Breaking:** Remove `print_sorted_table`; `SortByOption` now bakes the sort key into `ctx.print_table` for use with or without `--sort-by`.
- **Breaking:** Remove dead `ParamStructure` internals: the unused `flatten_tree_dict`/`_flatten_tree_dict_gen` methods, the `__init__`, and the redundant `SEP` attribute (use the module-level `click_extra.parameters.PARAM_PATH_SEP`).
- **Breaking:** Remove the unused `click_extra.styling.cascade_fields` helper.
- Add a `Spinner` widget for long blocking work as a context manager or decorator, with 90 presets in `SPINNERS` and TTY auto-disable; includes a `spinner` demo subcommand on the `click-extra` CLI.
- Add `click_extra.test_plan` and a `click-extra test-plan` subcommand for YAML-driven black-box subprocess testing of any CLI; YAML parsing needs the `yaml` extra.
- Add `--progress`/`--no-progress` (`ProgressOption`) and `click_extra.progressbar`, a drop-in for `click.progressbar` that hides under `--no-progress` or `--accessible`.
- Add `-q`/`--quiet` (`QuietOption`), the counterpart to `-v`/`--verbose`: each `-q` lowers the log level toward `CRITICAL`, the two cancelling out.
- Under `--accessible`, `click_extra.clear` is a no-op and `click_extra.echo_via_pager` streams to stdout instead of spawning a pager.
- Add `no_color_option`/`NoColorOption`, a standalone `--no-color` flag for plain `click.command` CLIs.
- Add `{author}`, `{license}`, `{git_distance}`, and `{git_dirty}` version-string template variables; git ones support pre-baking via `click-extra prebake all`.
- `VersionOption` git fields fall back to `.git_archival.json` when running from a `git archive` export without a `.git` directory.
- `--jobs` (`JobsOption`) now accepts `auto` and `max` keywords in addition to an integer, with shell completion; `run_jobs(func, items)` executes items against the resolved count.
- Add `make_schema_callable(schema)`, a callable that coerces a raw config dict into a validated dataclass.
- Add `require_sibling_param` and `last_param` helpers to `click_extra.parameters` for locating sibling and typed parameters at call time.
- Re-type `pass_context` for the enhanced `Context`, so `@pass_context def cmd(ctx: Context)` type-checks.
- Add `click_extra.prebake` hosting build-time version pre-baking helpers (`prebake_version`, `prebake_dunder`, `discover_package_init_files`); still importable from `click_extra.version`.
- Speed up `import click_extra` by deferring heavy imports, cutting startup time by roughly a third.
- Drop `requests` as a runtime dependency; the configuration-from-URL loader now uses `urllib.request`.
- `click-extra wrap` honors the tri-state color resolution, colorizing the wrapped CLI under `auto` only when the output is a terminal.
- `--color` and `--no-color` colorize eager `--help` and `--version` screens regardless of their position on the command line. Closes [`click-extra#137`](https://github.com/kdeldycke/click-extra/issues/137).
- `--color[=WHEN]` accepts `yes`/`force`, `no`/`none`, and `tty`/`if-tty` as hidden aliases; configuration files also accept native booleans (`true`/`false`).
- Under `auto`, a `dumb` or `unknown` `TERM` strips ANSI color even on a terminal; an explicit `--color` or `FORCE_COLOR` overrides.
- Branded 24-bit themes (`dracula`, `monokai`, `nord`, `solarized_dark`) downsample to 256 colors when the terminal does not advertise truecolor.
- `click-extra wrap --show-params` now reports the target's environment variables and resolves parameter values and their source from arguments passed after SCRIPT.
- Lower the Click floor from `8.4.1` to `8.3.1`, restoring support for Click `8.3.1` and later.
- The `click:run` and `click:tree` Sphinx directives now capture at the file-descriptor level by default (Click `8.4`+); set `click_extra_run_capture = "sys"` to opt out.
- Tolerate a missing `click_extra/themes.toml` data file: log a warning and fall back to the no-color theme.
- Fix `from click_extra import *` raising `AttributeError` due to `VersionOption` missing from the bound namespace.
- Fix the dim bracket styling of an `IntRange` option's `[x>=N]` constraint leaking across the next option in colored help.
- Fix inconsistent highlighting of the `--jobs [auto|max|INTEGER]` metavar in colored help.
- Fix the `assert_output_regex` testing fixture raising `TypeError` on a failed match under pytest 9.
- Fix `context_settings={"show_choices": True}` being ignored on a `Command` or `Group`.
- Fix `click-extra man` and `write_manpages` author and version resolution when the import name differs from the installed distribution name.
- `--validate-config` now raises `RuntimeError` instead of `TypeError` when used on a command with no sibling `--config` option, matching `--no-config`.
- Fix broken documentation links for the GNU `--color` reference, `click.Parameter` API anchor, and parameters page cross-references.

## [`7.20.1` (2026-06-18)](https://github.com/kdeldycke/click-extra/compare/v7.20.0...v7.20.1)

> [!NOTE]
> `7.20.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.20.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.20.1).

- Fix the MkDocs plugin and Sphinx directives leaving Rich-based CLIs (such as `rich-click`) colorless in rendered documentation.

## [`7.20.0` (2026-06-17)](https://github.com/kdeldycke/click-extra/compare/v7.19.0...v7.20.0)

> [!NOTE]
> `7.20.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.20.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.20.0).

- Add `MultiChoice` to `click_extra.types`: a Click `ParamType` for comma-separated multi-pick from a fixed set of values, the pick-many counterpart to `click.Choice`.
- Extend the `--show-params` table with seven new columns (`Is flag`, `Flag value`, `Is bool flag`, `Multiple`, `Nargs`, `Prompt`, `Confirmation prompt`).
- Add the `--columns` option (`ColumnsOption`, `@columns_option`) for SQL `SELECT`-style column selection on both `--show-params` and the standalone `click-extra show-params` subcommand.
- Add a `click:tree` Sphinx directive that walks a Click command tree and expands into a summary table plus one `{click:run}` `--help` block per command. MyST-only.
- Fix `click-extra show-params` ignoring the top-level `--table-format` option and rendering its default as the enum name instead of the kebab-case ID.
- Fix `click-extra show-params` and `click-extra man` resolving auto-generated environment variables as empty; the `envvars` column now matches what Click reads at runtime.
- Fix the MkDocs plugin stripping ANSI escape codes but rendering no colors: it now generates the ANSI Pygments stylesheet and registers it through `extra_css`, so the `-Ansi-*` classes it emits are styled.
- Drop duplicate and dead CSS classes from ANSI HTML rendering: compound tokens like `Token.Ansi.Bold.Cyan` now emit `-Ansi -Ansi-Bold -Ansi-Cyan` instead of repeating `-Ansi-Bold` and adding an unstyled `-Ansi-Bold-Cyan`.

## [`7.19.0` (2026-06-12)](https://github.com/kdeldycke/click-extra/compare/v7.18.0...v7.19.0)

> [!NOTE]
> `7.19.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.19.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.19.0).

- Add an `--output-dir DIR` option to `click-extra man`, writing one `.1` file per command into `DIR` instead of printing a single page to stdout.
- Add a `click_extra_manpages` Sphinx config value and a `click-extra-manpages` directive to emit Click command trees as roff `.1` files (and browser-viewable `.html` siblings when `mandoc` or `groff` is available) on every HTML build.
- Fix `ExtraVersionOption.package_version` resolving to `None` when the top-level module name differs from the installed distribution name (`PIL` vs `Pillow`); pass `package_name` explicitly to disambiguate.

## [`7.18.0` (2026-05-29)](https://github.com/kdeldycke/click-extra/compare/v7.17.2...v7.18.0)

> [!NOTE]
> `7.18.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.18.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.18.0).

- **Breaking:** Consolidate `--time`, `--jobs`, and `-0`/`--zero-exit` into a single `click_extra.execution` module; the `click_extra.jobs` and `click_extra.timer` submodules are removed (their decorators and classes remain importable from the `click_extra` root).
- **Breaking:** Unify configuration-loading errors under `ValidationError`. Unknown CLI-parameter keys (`strict=True`) and unknown schema fields (`schema_strict=True`) now exit with code 1 instead of raising an uncaught `ValueError`; catch the `SystemExit` or use `--validate-config` / `run_config_validation()` to inspect errors.
- Add a `--man` option to `@extra_command` and `@extra_group` (and the `@man_option` decorator) that prints the command's man page to stdout and exits.
- Add an `--accessible` option (and `@accessible_option` decorator, `AccessibleOption` class) to `@extra_command` and `@extra_group`; it or the `ACCESSIBLE` environment variable is equivalent to `--no-color --table-format plain` for screen readers. Explicit `--color` or `--table-format` keeps precedence.
- Add a `man` subcommand to the `click-extra` CLI: `click-extra man SCRIPT [SUBCOMMAND]...` renders any external Click CLI's man page. Both `man` and `show-params` now also accept `.py` file targets.
- Add the `click_extra.man_page` module to generate man pages programmatically: `render_manpage()`, `render_manpages()`, and `write_manpages()`.
- Add a `-0`/`--zero-exit` option (`@zero_exit_option` decorator, `ZeroExitOption` class) that records intent in `ctx.meta` under the `ZERO_EXIT` key for downstream code to read.
- Honor the standard `POSIXLY_CORRECT` environment variable: when present, `ExtraContext` forces `allow_interspersed_args` to `False`, stopping option parsing at the first positional argument.
- Add `run_config_validation()` and the `ValidationReport` dataclass to `click_extra.config`, running the CLI-parameter check, schema build, and every registered `ConfigValidator` in one pass; `collect_all` toggles between gathering all errors or stopping at the first.
- Fix `schema_strict=True` wrongly rejecting a configuration field marked with `EXTENSION_METADATA_KEY` when its Python type is not a mapping.

## [`7.17.2` (2026-05-26)](https://github.com/kdeldycke/click-extra/compare/v7.17.1...v7.17.2)

> [!NOTE]
> `7.17.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.17.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.17.2).

- Add Mermaid diagrams throughout the documentation for configuration source selection and precedence, class layering and default-option bundles, `--color`/`--no-color` enablement, `{version}`/`{exec_name}` fallback chains, the `decorator_factory` guardrail, and environment-variable id resolution.

## [`7.17.1` (2026-05-25)](https://github.com/kdeldycke/click-extra/compare/v7.17.0...v7.17.1)

> [!NOTE]
> `7.17.1` is available on [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.17.1).

> [!WARNING]
> `7.17.1` is **not available** on 🐍 PyPI.

- Fix the Nuitka standalone binaries aborting at startup with `FileNotFoundError: themes.toml` by bundling `click_extra/themes.toml` via a new `[tool.nuitka]` `include-package-data` setting.

## [`7.17.0` (2026-05-25)](https://github.com/kdeldycke/click-extra/compare/v7.16.1...v7.17.0)

> [!NOTE]
> `7.17.0` is available on [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.17.0).

> [!WARNING]
> `7.17.0` is **not available** on 🐍 PyPI.

- **Breaking:** Bump the Click floor to `8.4.1`, required for correct parameter-source detection in eager callbacks (`ColorOption` precedence, `ConfigOption` branching, `ShowParamsOption`'s `Source` column).
- **Breaking:** Bump the `requests` floor to `2.34`; it now ships inline type annotations, so the `types-requests` stub package is removed from the `typing` dependency group.
- All built-in themes now follow the man-pages(7) font convention: literal tokens (commands, aliases, option flags, choice values) render bold and replaceable tokens (metavars, argument names) render italic. Declared by the new `LITERAL_STYLES` / `REPLACEABLE_STYLES` frozensets in `click_extra.theme`.
- Add a colorless `manpage` built-in theme that renders the bold-literal / italic-replaceable convention with no color, selectable via `--theme manpage`.
- `HelpCommand` now raises `click.NoSuchCommand` instead of `click.UsageError` for an unknown subcommand, so the user sees did-you-mean suggestions.
- Remove the `HelpExtraFormatter.write_usage` override, no longer needed now that Click measures visible width when wrapping.
- Drop the explicit `type=UNPROCESSED` from `NoConfigOption.__init__`, now auto-detected by Click for `flag_value` with non-basic types.
- Bump the `myst-parser` floor in the `docs` dependency group to `5.1`; doc builds now use its native `"alert"` syntax extension instead of the in-tree converter.
- Drop the `colorama` test-matrix variation.

## [`7.16.1` (2026-05-15)](https://github.com/kdeldycke/click-extra/compare/v7.16.0...v7.16.1)

> [!NOTE]
> `7.16.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.16.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.16.1).

- Fix `ConfigOption` leaking keys from an earlier `--config` into later invocations of the same CLI in one process (Sphinx builds, test runners, REPLs).

## [`7.16.0` (2026-05-14)](https://github.com/kdeldycke/click-extra/compare/v7.15.0...v7.16.0)

> [!NOTE]
> `7.16.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.16.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.16.0).

- **Breaking:** Remove the `click_extra.themes` module and the per-theme constants `DARK`, `DRACULA`, `LIGHT`, `MONOKAI`, `NORD`, `SOLARIZED_DARK`; use `BUILTIN_THEMES["<name>"]` instead.
- **Breaking:** Replace the `default_theme` module attribute with `get_default_theme()` / `set_default_theme(theme)` accessors that always observe the current value.
- **Breaking:** Remove the pre-rendered `OK` and `KO` constants; use the raw `OK_GLYPH` / `KO_GLYPH` strings styled at the call site so they follow the active theme.
- **Breaking:** `theme_registry` no longer accepts a `Callable[[], HelpExtraTheme]` value; only `HelpExtraTheme` instances are valid entries.
- **Breaking:** Move telemetry storage to `ctx.meta[context.TELEMETRY]`; consumers reading `ctx.telemetry` must switch to `context.get(ctx, context.TELEMETRY)`.
- Add four branded built-in themes: `solarized_dark`, `dracula`, `nord`, and `monokai`. The full catalog now ships as `click_extra/themes.toml`; `BUILTIN_THEMES` is the single public `{name: HelpExtraTheme}` dict.
- Add a `ThemeChoice` `click.ParamType` (no longer a `click.Choice` subclass) whose choices read the live registry, so themes loaded from `--config` appear as valid `--theme` choices and in the `--help` metavar.
- Add the `click_extra.styling` module with a feature-rich `Style` subclass (hex constructor, `a | b` composition, `cascade`, `to_dict`/`from_dict`, `to_css`, `from_ansi`, WCAG `contrast_ratio`), exposed as `from click_extra import Style`.
- Add `to_dict()` / `from_dict()` / `cascade(base)` to `HelpExtraTheme` for sparse theme overrides layered on a full palette.
- Read user-defined theme palettes from the config file: every `[<cli>.themes.<name>]` table is parsed and available to `--theme`, cascading on the matching built-in or registered as a stand-alone theme, without mutating the global registry.
- Add an app-defined configuration-validation hook: new `ConfigValidator`, `ValidationError`, and `EXTENSION_METADATA_KEY` types, registered via a `config_validators=` kwarg on `ExtraCommand` / `ExtraGroup` (and `@command` / `@group` / `@config_option`). `--validate-config` now collects every error before exiting.
- Flip the `AnsiColorLexer.true_color` default to `True`: 24-bit RGB sequences render as inline `style="color: #rrggbb"` spans by default. Restore the old behavior with `AnsiColorLexer(true_color=False)`.
- Add the `:emphasize-result-lines:` option to the `click:run` and `python:run` Sphinx directives to highlight lines in the captured output.
- Fix `pyproject.toml` CWD discovery skipping files lacking a `[tool.<cli_name>]` section, so an unrelated `pyproject.toml` no longer shadows the user's app-dir config.
- Fix `ExtraVerbosity.set_level()` changing the logger level during help rendering and shell completion, and fix `reset_loggers` double-registration when both `--verbosity` and `-v` are passed.
- Inner bracket-field slots (`envvar`, `default`, `required`, `range_label`) now fall back to the `bracket` slot's style, so a minimal palette colours the whole bracket field uniformly.
- Deprecate `click_extra.sphinx.alerts` now that `myst-parser` `5.1.0` ships a native `"alert"` extension; the regex converter is registered only on older `myst-parser`.

## [`7.15.0` (2026-05-03)](https://github.com/kdeldycke/click-extra/compare/v7.14.1...v7.15.0)

> [!NOTE]
> `7.15.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.15.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.15.0).

- **Breaking:** Code importing theme symbols from `click_extra.colorize` must switch to `click_extra.theme` (the `from click_extra import HelpExtraTheme` path is unaffected).
- **Breaking:** `from click_extra.commands import ExtraContext` and `from click_extra import ctx_meta` must become `from click_extra.context import ExtraContext` and `from click_extra import context` (the `from click_extra import ExtraContext` path is unaffected).
- **Breaking:** Disable the `click:*` and `python:*` Sphinx directives by default, since they execute arbitrary Python at build time. Re-enable with `click_extra_enable_exec_directives = True` in `conf.py`.
- Add opt-in 24-bit true-color rendering to the ANSI Pygments stack via `true_color=True` on `AnsiColorLexer`, `AnsiFilter`, or any session lexer; `AnsiHtmlFormatter` renders the preserved RGB tokens as inline `style="color: #rrggbb"` spans. Default 256-color quantization is unchanged.
- Add a `click_extra.theme` module centralizing all theme machinery (`HelpExtraTheme`, `ThemeOption`, `theme_option`, `theme_registry`, `register_theme()`, …). Every command now accepts `--theme [dark|light]`, extensible via `register_theme()`; the active theme is read with `get_current_theme()`.
- Add a `click_extra.context` module consolidating `ExtraContext` and a documented registry of every `ctx.meta` key, with `get()` / `set()` helpers. Replaces `click_extra.ctx_meta`.
- Add `python:source`, `python:run`, `python:render`, `python:render-myst`, and `python:render-rst` Sphinx directives under a new `python` domain, mirroring `click:source` / `click:run` for arbitrary Python; the `render` family turns captured stdout into live document content.
- Tighten the Click floor to `8.3.1`, the minimum shipping the parameter-name fix this depends on.

## [`7.14.1` (2026-04-26)](https://github.com/kdeldycke/click-extra/compare/v7.14.0...v7.14.1)

> [!NOTE]
> `7.14.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.14.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.14.1).

- Relax the Click floor back to `8.1` by replacing `ParameterSource` ordered comparisons in `ConfigOption` with set membership.
- Relax the tabulate floor back to `0.9` by aliasing `colon_grid` to `grid` when tabulate `< 0.10` is installed.

## [`7.14.0` (2026-04-24)](https://github.com/kdeldycke/click-extra/compare/v7.13.0...v7.14.0)

> [!NOTE]
> `7.14.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.14.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.14.0).

- Add a `wrap` subcommand: `click-extra wrap SCRIPT [ARGS]...` applies help colorization to any installed Click CLI without modifying it. Supports `--theme` and `[tool.click-extra.wrap.<script>]` config sections; unknown subcommands fall through to `wrap` automatically. `run` is kept as an alias.
- Add a `show-params` subcommand: `click-extra show-params SCRIPT [SUBCOMMAND]...` introspects any external Click CLI's parameters as a table, honoring all `--table-format` renderings and drilling into nested subcommands.
- Add `get_param_spec()` and `format_param_row()` as public API in `click_extra.parameters`, the shared spec extractor and cell renderer for both `--show-params` and `show-params`.
- Make `ParamStructure.get_param_type()` a `@staticmethod` that returns `str` for unrecognised custom types instead of raising.
- Replace the `render-matrix` subcommand with individual `colors`, `styles`, `palette`, `8color`, and `gradient` subcommands under a Demo section, and remove the `click-extra-demo` entry point.
- Bump the Click floor to `8.3.3`.

## [`7.13.0` (2026-04-16)](https://github.com/kdeldycke/click-extra/compare/v7.12.0...v7.13.0)

> [!NOTE]
> `7.13.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.13.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.13.0).

- Add a MkDocs plugin for ANSI color rendering in code blocks: install with `pip install click-extra[mkdocs]`, then add `click-extra` to your `mkdocs.yml` plugins list.
- Automatically patch `mkdocs-click` code blocks to use the `ansi-output` lexer when the plugin is enabled, so CLI help text with ANSI codes renders with colors.
- Fix API reference sections rendering as raw RST instead of formatted documentation by wrapping `automodule` and `autoclasstree` directives in `eval-rst` blocks.
- Add OSC 8 hyperlink support to `AnsiColorLexer` and `AnsiHtmlFormatter`, rendering terminal hyperlinks as clickable HTML `<a>` tags; other OSC sequences are now fully stripped.

## [`7.12.0` (2026-04-16)](https://github.com/kdeldycke/click-extra/compare/v7.11.0...v7.12.0)

> [!NOTE]
> `7.12.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.12.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.12.0).

- **Breaking:** change `render-matrix --matrix=<choice>` to a positional argument `render-matrix <choice>`. Add `palette`, `8color`, and `gradient` choices.
- Add `JobsOption` and the `@jobs_option` decorator for parallel execution control. Defaults to available CPUs minus one, and warns when the count is clamped.
- Improve error messages for single-dash multi-character tokens like `-dbgwrong`: report the full token with close-match suggestions instead of `No such option: -d`.
- Replace the `pygments-ansi-color` dependency with an inline ANSI SGR parser, adding italic, underline, reverse video, strikethrough, and 24-bit RGB colors. The token namespace moves from `Token.Color.*`/`Token.C.*` to `Token.Ansi.*` and CSS classes from `.-Color-*`/`.-C-*` to `.-Ansi-*`.
- Rename `lexer_map` to `LEXER_MAP`.
- Fix `render-matrix colors` styling background color column headers as foreground colors.

## [`7.11.0` (2026-04-13)](https://github.com/kdeldycke/click-extra/compare/v7.10.1...v7.11.0)

> [!NOTE]
> `7.11.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.11.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.11.0).

- Add `serialize_data()` and `print_data()` to serialize arbitrary nested Python data to JSON, HJSON, TOML, YAML, and XML, complementing `render_table()`/`print_table()`.
- Add a `sort_key` parameter to `render_table()` and `print_table()` for pre-render row sorting.
- Catch `ImportError` from missing optional dependencies in `print_table()` and `print_data()`, emitting a clean one-line error instead of a traceback. `print_data()` takes a `package` parameter to customize install instructions.
- Add `print_sorted_table()` and `SortByOption`, which generates a `--sort-by` CLI option from column definitions and wires `ctx.print_table` to the sorted variant.
- Add an auto-injected `help` subcommand to `ExtraGroup`: `mycli help [subcommand]` shows help and `--search term` searches all subcommands. Disable with `help_command=False`.
- Expose the `HelpKeywords` dataclass and `collect_keywords()` (renamed from `_collect_keywords()`) as public API for extending help-screen highlighting.
- Add `extra_keywords` and `excluded_keywords` parameters to `ExtraCommand` and `ExtraGroup` to inject or suppress highlighted strings. Both accept a `HelpKeywords` instance.
- Highlight manually-added deprecation markers like `(Deprecated)` or `(deprecated: reason)` alongside Click-native `(DEPRECATED)` markers.
- Style individual choices inside their own metavar (`[json|csv|xml]`) as structural elements, always styled even when free-text highlighting is suppressed.
- Propagate `excluded_keywords` from parent groups to subcommands.
- Fix command aliases rendered by Cloup in parenthetical groups (like `backup (save, freeze)`) not being highlighted in help screens.
- Fix choice cross-reference highlighting bleeding into bracket fields when a default value contained a choice keyword (like `outline` in `rounded-outline`).
- Fix parent-context choice collection lowercasing case-insensitive choices that define a custom metavar.

## [`7.10.1` (2026-04-07)](https://github.com/kdeldycke/click-extra/compare/v7.10.0...v7.10.1)

> [!NOTE]
> `7.10.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.10.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.10.1).

- Fix the `pipe` and `github` table formats to produce mdformat-compatible separator rows, preventing a formatting cycle between tabulate and mdformat.
- Compute the test matrix dynamically via `repomatic metadata` (OS, Python, and stability axes), with custom Click/Cloup version axes via `[tool.repomatic.test-matrix]`. PRs get a reduced matrix.
- Replace `{eval-rst}`-wrapped `automodule` and `autoclasstree` directives with native MyST syntax in all docs.

## [`7.10.0` (2026-04-02)](https://github.com/kdeldycke/click-extra/compare/v7.9.0...v7.10.0)

> [!NOTE]
> `7.10.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.10.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.10.0).

- Highlight parent group names in subcommand help text even when interleaved with options.
- Add `range_label`, `required`, and `argument` theme slots to `HelpExtraTheme`, styling argument metavars separately from option metavars.
- Add a `cross_ref_highlight` flag to `HelpExtraTheme`. Set to `False` to disable free-text highlighting of options, choices, arguments, metavars, and CLI names; structural elements stay styled.
- Add type-aware flattening, field metadata, and nested dataclass support to `config_schema`. `flatten_config_keys()` and `normalize_config_keys()` accept an `opaque_keys` parameter, and fields support `click_extra.config_path` and `click_extra.normalize_keys` metadata.
- Fix help-text highlighting of hyphenated option names (like `--table-format`), argument names colliding with option keywords, and substring matches in compound keywords (like `outline` inside `rounded-outline`).
- Fix enum coloring to use `normalize_choice()` so the metavar strings match instead of raw enum member names.

## [`7.9.0` (2026-03-31)](https://github.com/kdeldycke/click-extra/compare/v7.8.0...v7.9.0)

> [!NOTE]
> `7.9.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.9.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.9.0).

- Add a `flatten_config_keys()` utility to flatten nested config dicts into a single level by joining keys with a separator.
- Flatten nested config dicts before dataclass field matching in `config_schema`, so nested TOML sub-tables map to flat dataclass fields.
- Add a `schema_strict` parameter to `ConfigOption` and `ExtraCommand`/`ExtraGroup`: when `True`, unknown config keys raise `ValueError` during schema validation instead of being dropped.
- Auto-discover `pyproject.toml` by walking up from the working directory to the VCS root before falling back to the app config directory.
- Instantiate `config_schema` defaults when no config file is found, so `get_tool_config()` never returns `None` when a schema is configured.
- Forward `included_params` from `ExtraCommand`/`ExtraGroup` to `ConfigOption`, letting `@group(included_params=())` disable `merge_default_map` when config keys are schema-only.
- Move `prebake_version()`, `prebake_dunder()`, and `discover_package_init_files()` from `ExtraVersionOption` static methods to module-level functions in `click_extra.version`.
- Add a `git_tag` template field, resolved from a `__git_tag__` dunder or `git describe --tags --exact-match HEAD` at runtime.
- Add a `git_tag_sha` template field, resolved from a `__git_tag_sha__` dunder with a `git` subprocess fallback. Replaces the old `__tag_sha__` convention.
- Resolve git template fields (`git_branch`, `git_long_hash`, `git_short_hash`, `git_date`) from pre-baked `__<field>__` dunders before falling back to subprocess calls, so compiled binaries can embed git metadata at build time.
- Add a `click-extra prebake` CLI with `all`, `version`, and `field` subcommands to bake `__version__` and git fields. Field names auto-wrap with `__...__`, and targets are auto-discovered from `[project.scripts]`.
- Add empty `__git_*__` dunder placeholders to `click_extra/__init__.py`.
- Pin image URLs in `readme.md` and `docs/tutorial.md` to the release tag at bump time, restoring them to `main` on the next dev bump.

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

- Fix `test_default_pattern_roaming_force_posix` test failures when `XDG_CONFIG_HOME` is set. Closes [#1541](https://github.com/kdeldycke/click-extra/issues/1541).

## [`7.6.2` (2026-02-27)](https://github.com/kdeldycke/click-extra/compare/v7.6.1...v7.6.2)

> [!NOTE]
> `7.6.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.6.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.6.2).

- Add `ExtraVersionOption.prebake_version()` static method to pre-bake `__version__` strings with Git hashes at compile time, complementing the runtime `version` property for Nuitka/PyInstaller binaries.

## [`7.6.1` (2026-02-27)](https://github.com/kdeldycke/click-extra/compare/v7.6.0...v7.6.1)

> [!NOTE]
> `7.6.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.6.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.6.1).

- Fix test failures when optional config format dependencies are not installed. Closes [#1538](https://github.com/kdeldycke/click-extra/issues/1538).

## [`7.6.0` (2026-02-26)](https://github.com/kdeldycke/click-extra/compare/v7.5.3...v7.6.0)

> [!NOTE]
> `7.6.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.6.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.6.0).

- Add `_default_subcommands` reserved configuration key to auto-invoke subcommands when none are provided on the CLI. Closes [#1405](https://github.com/kdeldycke/click-extra/issues/1405).
- Add `_prepend_subcommands` reserved configuration key to always prepend subcommands to every invocation (requires `chain=True`). Closes [#1405](https://github.com/kdeldycke/click-extra/issues/1405).
- Add `--validate-config` option to validate configuration files.
- Add `ConfigFormat.PYPROJECT_TOML` format for `[tool.*]` section support in `pyproject.toml`. Closes [#1524](https://github.com/kdeldycke/click-extra/issues/1524).
- Stop parent directory walk on inaccessible directories.
- Add `stop_at` parameter to `@config_option` to limit parent directory walking. Defaults to `VCS`. Closes [#651](https://github.com/kdeldycke/click-extra/issues/651).
- Add `VCS` sentinel and `VCS_DIRS` constant for VCS root detection.
- Resolve relative paths to absolute in `parent_patterns` before yielding.
- Add `included_params` allowlist to `ConfigOption` and `@config_option`, the inverse of `excluded_params`. Closes [#1362](https://github.com/kdeldycke/click-extra/issues/1362).
- Add human-friendly display labels to `ConfigFormat`.
- Switch back from `SPLIT` to `BRACE` flag for multi-format config file patterns. Fixes a bug where only the first format received the directory prefix with `SPLIT`.
- Hard code icon workaround for Sphinx index entries.
- Automatically append Git short hash as a PEP 440 local version identifier to `.dev` versions (e.g., `1.2.3.dev0+abc1234`).
- Skip Git hash suffix for versions that already contain `+` (pre-baked local identifiers) to avoid invalid double-suffixed versions.
- Recognize `LLM` environment variable to strip ANSI codes when running under an AI agent.

## [`7.5.3` (2026-02-22)](https://github.com/kdeldycke/click-extra/compare/v7.5.2...v7.5.3)

> [!NOTE]
> `7.5.3` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.5.3/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.5.3).

- Allow disabling of autodiscovery of configuration files by setting `default=NO_CONFIG` on `@config_option`. Closes [#1495](https://github.com/kdeldycke/click-extra/issues/1495).
- Implement `resolve_any_xref` in `ClickDomain` to prevent MyST-Parser warning. Closes [#1502](https://github.com/kdeldycke/click-extra/issues/1502).
- Fix subcommand conflict detection checking against root-level params instead of parent params. Closes [#1286](https://github.com/kdeldycke/click-extra/pull/1286).

## [`7.5.2` (2026-02-12)](https://github.com/kdeldycke/click-extra/compare/v7.5.1...v7.5.2)

> [!NOTE]
> `7.5.2` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.5.2/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.5.2).

- Fix GitHub alerts converter mangling `list-table` directive content. Closes [#1490](https://github.com/kdeldycke/click-extra/issues/1490).
- Replace Dependabot by Renovate.
- Move `click_extra/docs_update.py` to `docs/docs_update.py`.
- Add `pygments-ansi-color` to `docs` dependency group for lexer table generation.

## [`7.5.1` (2026-02-05)](https://github.com/kdeldycke/click-extra/compare/v7.5.0...v7.5.1)

> [!NOTE]
> `7.5.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/7.5.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v7.5.1).

- Add new `aligned` table format with single-space column separators and no borders.
- Fix parallel mode support in Sphinx extension. Closes [#1482](https://github.com/kdeldycke/click-extra/issues/1482).

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

- Allow parent directories search for configuration files. Adds `search_parents` argument on `@config_file`. Closes [#651](https://github.com/kdeldycke/click-extra/issues/651).
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
- Relax dependencies to support Python 3.10. Closes [#1385](https://github.com/kdeldycke/click-extra/issues/1385).
- Re-introduce `tomli` dependency for Python 3.10 users.
- Skip tests on intermediate Python versions (`3.11`, `3.12` and `3.13`) to reduce CI load.

## [`6.1.0` (2025-10-29)](https://github.com/kdeldycke/click-extra/compare/v6.0.3...v6.1.0)

> [!NOTE]
> `6.1.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/6.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v6.1.0).

- Add support for JSON5, JSONC and HJSON configuration files.
- YAML and XML configuration support is now optional. You need to install the `click_extra[yaml]` and `click_extra[xml]` extra dependency groups to enable it.
- Add new `@lazy_group` decorator and `LazyGroup` class to create groups that only load their subcommands when invoked. Closes [#1332](https://github.com/kdeldycke/click-extra/issues/1332).
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

- Fix `@config_option` to accept `Path` objects as default value. Closes [#1356](https://github.com/kdeldycke/click-extra/issues/1356).
- Add official support of Python 3.14.
- Run tests on Python 3.15-dev.

## [`6.0.0` (2025-09-25)](https://github.com/kdeldycke/click-extra/compare/v5.1.1...v6.0.0)

> [!NOTE]
> `6.0.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/6.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v6.0.0).

- Add new variables for version string template: `{git_repo_path}`, `{git_branch}`, `{git_long_hash}`, `{git_short_hash}` and `{git_date}`.
- Add a new `--no-config` option on `@extra_command` and `@extra_group` to disable configuration files. Closes [#750](https://github.com/kdeldycke/click-extra/issues/750).
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

- Relax Click dependency to account for yanked release. Closes [#1307](https://github.com/kdeldycke/click-extra/issues/1307).

## [`5.1.0` (2025-08-03)](https://github.com/kdeldycke/click-extra/compare/v5.0.2...v5.1.0)

> [!NOTE]
> `5.1.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/5.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v5.1.0).

- Add support for MyST Markdown syntax for `click:example` and `click:run` Sphinx directives.
- Add support for all `code-block` options to `click:example` and `click:run`: `:linenos:`, `:lineno-start:`, `:emphasize-lines:`, `:force:`, `:caption:`, `:name:`, `:class:` and `:dedent:`.
- Add new `:show-source:`/`:hide-source:`, `:show-results:`/`:hide-results:` and `:language:` options to `click:example` and `click:run`. Closes [#719](https://github.com/kdeldycke/click-extra/issues/719).
- Support non-string choices in colored help screens. Closes [#1284](https://github.com/kdeldycke/click-extra/issues/1284).
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
- Rewrite the logging documentation with all use-cases and custom configuration examples. Closes [#989](https://github.com/kdeldycke/click-extra/issues/989).
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
- Move dependencies extending `pygments`, `sphinx` and `pytest` into optional extra dependencies. Closes [#836](https://github.com/kdeldycke/click-extra/issues/836).
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
- Recognize custom parameter type as string-based. Closes [#721](https://github.com/kdeldycke/click-extra/issues/721).
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

- Highlight required label and value range in option description. Closes [#748](https://github.com/kdeldycke/click-extra/issues/748).

## [`4.6.4` (2023-08-23)](https://github.com/kdeldycke/click-extra/compare/v4.6.3...v4.6.4)

> [!NOTE]
> `4.6.4` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.6.4/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.6.4).

- Fix collection of subcommand parameters in `--show-params` output. Closes [#725](https://github.com/kdeldycke/click-extra/issues/725).
- Set `%(package_name)` in `--version` to file name for CLI that are standalone scripts and not packaged. Fix [#729](https://github.com/kdeldycke/click-extra/issues/729).
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
- Activate colors on `@extra_command` and `@extra_group` by default, even if stripped of all their default parameters. Closes [#534](https://github.com/kdeldycke/click-extra/issues/534) and [#543](https://github.com/kdeldycke/click-extra/pull/543).
- Expose location and content of user's configuration file in the Context's `meta` property. Closes [#673](https://github.com/kdeldycke/click-extra/issues/673).
- Render specs of hidden parameters in `--show-params` output. Fixes [#689](https://github.com/kdeldycke/click-extra/issues/689).
- Swap `Exposed` and `Allowed in conf?` columns in `--show-params` output.
- Add a `hidden` column to `--show-params` output. Refs [#689](https://github.com/kdeldycke/click-extra/issues/689).

## [`4.5.0` (2023-07-06)](https://github.com/kdeldycke/click-extra/compare/v4.4.0...v4.5.0)

> [!NOTE]
> `4.5.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/4.5.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v4.5.0).

- Expose verbosity level name, table format ID and CLI start timestamp in the Context's `meta` property.
- Refactor `VersionOption`. Introduce internal caching.
- Expose version string elements in the Context's `meta` property. Closes [#325](https://github.com/kdeldycke/click-extra/issues/325).
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
- Test continuously against Click and Cloup development version. Closes [#525](https://github.com/kdeldycke/click-extra/issues/525).
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
- Set default logger of `--verbosity` to Python's global `root` logger, instead a local wrapped logger. Closes [#318](https://github.com/kdeldycke/click-extra/issues/318).
- Allow user to provide a string as the default logger to `--verbosity` that will be used to fetch the global logger singleton of that name. Closes [#318](https://github.com/kdeldycke/click-extra/issues/318).
- Only colorize the `%(levelname)s` field during log record formatting, not the `:` message separator.
- Prefix `INFO`-level log message with `info: ` prefix by default.
- Raise an error if multiple `--version` options are defined in the same command. Closes [#317](https://github.com/kdeldycke/click-extra/issues/317).
- Remove dependency on `click-log`.
- Remove supports for `Pallets-Sphinx-Themes < 2.1.0`.
- Force closing of the context before stopping the execution flow, to make sure all callbacks are called.
- Fix rendering of GitHub-Flavored Markdown tables in canonical format.

## [`3.10.0` (2023-04-04)](https://github.com/kdeldycke/click-extra/compare/v3.9.0...v3.10.0)

> [!NOTE]
> `3.10.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.10.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.10.0).

- Colorize help screens of subcommands spawned out of an `@extra_group`. Closes [#479](https://github.com/kdeldycke/click-extra/issues/479).
- Remove deprecated `click_extra.platform`.

## [`3.9.0` (2023-04-01)](https://github.com/kdeldycke/click-extra/compare/v3.8.3...v3.9.0)

> [!NOTE]
> `3.9.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.9.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.9.0).

- Allow `@color_option`, `@command`, `@config_option`, `@extra_command`, `@extra_group`, `@group`, `@help_option`, `@show_params_option`, `@table_format_option`, `@timer_option`, `@verbosity_option` and `@version_option` decorators to be used without parenthesis.
- Fix wrapping of Cloup decorators by `@extra_group`/`@extra_command` decorators. Closes [#489](https://github.com/kdeldycke/click-extra/issues/489).
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

- Fix highlighting of `+`-prefixed options in help screens. Closes [#316](https://github.com/kdeldycke/click-extra/issues/316).
- Fix highlighting of hard-coded deprecated labels in option help.
- Document parameter introspection. Closes [#319](https://github.com/kdeldycke/click-extra/issues/319).

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
- Add a new `formats` option to specify which dialects the configuration file is written in, regardless of its name or file extension. Closes [#197](https://github.com/kdeldycke/click-extra/issues/197).
- Set default configuration folder according each OS preferred location. Closes [#211](https://github.com/kdeldycke/click-extra/issues/211).
- Add `roaming` and `force_posix` option to influence default application directory of configuration file.
- Add a `ignored_options` parameter to the configuration file instead of hard-coding them.
- Add dependency on `wcmatch`.
- Remove tests on deprecated `ubuntu-18.04`.
- Document preset options overriding. Closes [#232](https://github.com/kdeldycke/click-extra/issues/232).
- Document configuration option pattern matching and default folder. Closes [#197](https://github.com/kdeldycke/click-extra/issues/197) and [#211](https://github.com/kdeldycke/click-extra/issues/211).

## [`3.0.1` (2022-08-07)](https://github.com/kdeldycke/click-extra/compare/v3.0.0...v3.0.1)

> [!NOTE]
> `3.0.1` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.0.1).

- Fix wrong dependency bump on `pytest-cov` produced by major release.

## [`3.0.0` (2022-08-07)](https://github.com/kdeldycke/click-extra/compare/v2.1.3...v3.0.0)

> [!NOTE]
> `3.0.0` is available on [🐍 PyPI](https://pypi.org/project/click-extra/3.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/click-extra/releases/tag/v3.0.0).

- Make default extra features optional, so `click_extra` can act as a drop-in replacement for `click` and `cloup` (closes [#173](https://github.com/kdeldycke/click-extra/issues/173)):
  - Rename `click_extra.group` to `click_extra.extra_group`.
  - Rename `click_extra.command` to `click_extra.extra_command`.
  - Alias `click_extra.group` to `cloup.group`.
  - Alias `click_extra.command` to `cloup.group`.
- Use declarative `params=` argument to set defaults options on `extra_command` and `extra_group`.
- Move the implementation of options to classes.
- Hard-copy `version_option` code from `click` to allow for more flexibility. Addresses [#176](https://github.com/kdeldycke/click-extra/issues/176).
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

- Fix auto-mapping and recognition of all missing Click option types in config module. Closes [#170](https://github.com/kdeldycke/click-extra/issues/170).
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

- Add support for XML configuration file. Closes [#122](https://github.com/kdeldycke/click-extra/issues/122).
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
  and `double_outline`. Address [https://github.com/astanin/python-tabulate/issues/151](https://github.com/astanin/python-tabulate/issues/151).
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
