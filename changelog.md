# Changelog

## {gh}`3.3.3 (unreleased) <compare/v3.3.2...main>`

```{important}
This version is not released yet and is under active development.
```

## {gh}`3.3.2 (2022-11-14) <compare/v3.3.1...v3.3.2>`

- Remove use of deprecated `::set-output` directives and replace them by environment files.

## {gh}`3.3.1 (2022-11-11) <compare/v3.3.0...v3.3.1>`

- Keep a copy of the table format ID in the context when set.

## {gh}`3.3.0 (2022-11-09) <compare/v3.2.5...v3.3.0>`

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

## {gh}`3.2.5 (2022-09-30) <compare/v3.2.4...v3.2.5>`

- Fix argument's property getter in `--show-params`.
- Remove GitHub edit link workaround in documentation.

## {gh}`3.2.4 (2022-09-27) <compare/v3.2.3...v3.2.4>`

- Add citation file.
- Fix type casting.

## {gh}`3.2.3 (2022-09-27) <compare/v3.2.2...v3.2.3>`

- Increase type coverage.

## {gh}`3.2.2 (2022-09-26) <compare/v3.2.1...v3.2.2>`

- Fix bad typing import.

## {gh}`3.2.1 (2022-09-26) <compare/v3.2.0...v3.2.1>`

- Move some command utility from test machinery to `run` submodule.

## {gh}`3.2.0 (2022-09-24) <compare/v3.1.0...v3.2.0>`

- New `--show-params` option to debug parameters defaults, values, environment variables and provenance.
- Rename `ignored_options` to `ignored_params` on `ConfigOption`.
- Highlight command's metavars, default values and deprecated flag in help.
- Finer highlighting of options, subcommands and their aliases in help screens.
- Fix highlight of dynamic metavars and secondary option in help screen.
- New custom `ExtraContext` which allows populating `meta` at instanciation.
- Use the `Formats` enum to encode for default configuration file extensions.
- Re-introduce `*.yml` as a possible extension for YAML files.

## {gh}`3.1.0 (2022-09-20) <compare/v3.0.1...v3.1.0>`

- Add support for pattern matching to search for configuration file.
- Add a new `formats` option to specify which dialects the configuration file is written in, regardless of its name or file extension. Closes {issue}`197`.
- Set default configuration folder according each OS preffered location. Closes {issue}`211`.
- Add `roaming` and `force_posix` option to influence default application directory of configuration file.
- Add a `ignored_options` parameter to the configuration file instead of hard-coding them.
- Add dependency on `wcmatch`.
- Remove tests on deprecated `ubuntu-18.04`.
- Document preset options ovveriding. Closes {issue}`232`.
- Document configuration option pattern matching and default folder. Closes {issue}`197` and {issue}`211`.

## {gh}`3.0.1 (2022-08-07) <compare/v3.0.0...v3.0.1>`

- Fix wrong dependency bump on `pytest-cov` produced by major release.

## {gh}`3.0.0 (2022-08-07) <compare/v2.1.3...v3.0.0>`

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
- Add support for `.. click:example::` and `.. click:run::` directives in documentation.
- Add ANSI sesssion and console lexers for Pygments.
- Add a Pygments filter to transform tokens into ANSI tokens.
- Add custom Pygment style to render ANSI tokens in `furo` theme.
- Add dependency on `pygments`, `pygments-ansi-color` and `Pallets-Sphinx-Themes`.
- Allow translation of short help in extra options.
- Add minimal type hints.
- Pre-compute test matrix to allow for a subset of jobs to fail if flagged as unstable.
- Run tests on `ubuntu-22.04` and `macos-12`.
- Remove tests on deprecated `macos-10.15`.

## {gh}`2.1.3 (2022-07-08) <compare/v2.1.2...v2.1.3>`

- Do not render `None` cells in tables with `<null>` string.
- Disable workflow grouping and concurrency management.

## {gh}`2.1.2 (2022-06-02) <compare/v2.1.1...v2.1.2>`

- Fix auto-mapping and recognition of all missing Click option types in config module. Closes {issue}`170`.
- Fix CI workflow grouping.

## {gh}`2.1.1 (2022-05-22) <compare/v2.1.0...v2.1.1>`

- Fix compatibility with `cloup >= 0.14.0`.
- Group workflow jobs so new commits cancels in-progress execution triggered by previous commits.
- Run tests on early Python 3.11 releases.

## {gh}`2.1.0 (2022-04-22) <compare/v2.0.2...v2.1.0>`

- Add a `highlight` utility to style substrings.
- Add `regex` dependency.

## {gh}`2.0.2 (2022-04-14) <compare/v2.0.1...v2.0.2>`

- Fix and unittest derivation of configuration template and types from CLI
  options.
- Fix dependency requirements induced by overzealous automatic post-release
  version bump workflow.
- Replace `sphinx_tabs` by `sphinx-design`.
- Add edit link to documentation pages.

## {gh}`2.0.1 (2022-04-13) <compare/v2.0.0...v2.0.1>`

- Fix mapping of file arguments in configuration files.
- Fix Sphinx documentation update and publishing.
- Run tests on `pypy-3.7`.

## {gh}`2.0.0 (2022-04-11) <compare/v1.9.0...v2.0.0>`

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

## {gh}`1.9.0 (2022-04-08) <compare/v1.8.0...v1.9.0>`

- Add supports for `.ini` configuration files.
- Add supports for commented JSON configuration files.
- Fix identification of TOML and JSON configuration files.
- Fix leak of local environment variable update on `extend_env()` usage.
- Ignore `help` boolean in configuration files.
- Add new dependency on `mergedeep`.

## {gh}`1.8.0 (2022-04-03) <compare/v1.7.0...v1.8.0>`

- Split the `print_cli_output` method to expose the simpler `format_cli` utility.

## {gh}`1.7.0 (2022-03-31) <compare/v1.6.4...v1.7.0>`

- Refactor global logging management.
- Remove `click_extra.run.run` and rebase all run utilities around `subprocess.run`.
- Use the `tomllib` from the standard library starting with Python 3.11.

## {gh}`1.6.4 (2022-03-04) <compare/v1.6.3...v1.6.4>`

- Fix extension of default environment variables.

## {gh}`1.6.3 (2022-03-04) <compare/v1.6.2...v1.6.3>`

- Add support for environment variables to run utilities.

## {gh}`1.6.2 (2022-03-03) <compare/v1.6.1...v1.6.2>`

- Temporarily skip displaying environment details in `--version` option results
  for `python >= 3.10`.
- Reactivate all tests on Python 3.10.

## {gh}`1.6.1 (2022-03-02) <compare/v1.6.0...v1.6.1>`

- Expose some `cloup` versions of `click` utilities at the root of
  `click_extra`.

## {gh}`1.6.0 (2022-03-02) <compare/v1.5.0...v1.6.0>`

- Allow `click_extra` to be imported as a drop-in replacement for `click`.
- Share the same set of default options between `click_extra.command` and
  `click_extra.group`.
- Document default help screen comparison between simple `click` CLI and
  enhanced `click-extra` CLI.

## {gh}`1.5.0 (2022-02-21) <compare/v1.4.1...v1.5.0>`

- Add support for JSON configuration file.
- Search all supported formats in default location if configuration file not
  provided.
- Print configuration file default location in help screens.

## {gh}`1.4.1 (2022-02-13) <compare/v1.4.0...v1.4.1>`

- Add new external workflow to modernize Python code.
- Use external workflow suite to manage changelog and build & publish packages
  on PyPi on release.
- Use external workflow to label sponsored issues and PRs.
- Replace local workflow by external one to label issues and PRs.
- Reuse externnal workflow to produce dependency graph.
- Remove dev dependencies on `check-wheel-contents`, `graphviz`, `pipdeptree`
  and `twine`.

## {gh}`1.4.0 (2022-01-08) <compare/v1.3.0...v1.4.0>`

- Allow downloading of a remote config URL.
- Add new dependencies on `requests` and `pytest-httpserver`.
- Fix inference of config file top-level section name.
- Document usage of `click_extra.config.config_option`.
- Use external workflows for GitHub actions.
- Automate version and changelog management.

## {gh}`1.3.0 (2021-11-28) <compare/v1.2.2...v1.3.0>`

- Add support for YAML configuration file. Closes #13.
- Auto-detect configuration file on loading.
- Add `pyyaml` dependency.

## {gh}`1.2.2 (2021-11-04) <compare/v1.2.1...v1.2.2>`

- Evaluate format option dynamiccaly at use to let third-party register new
  rendering formats.

## {gh}`1.2.1 (2021-11-04) <compare/v1.2.0...v1.2.1>`

- Fix creation of post-release version bump PR on tagging.

## {gh}`1.2.0 (2021-11-04) <compare/v1.1.1...v1.2.0>`

- Extend `cli-helper.TabularOutputFormatter` with new formats: `simple_grid`,
  `rounded_grid`, `double_grid`, `outline`, `simple_outline`, `rounded_outline`
  and `double_outline`. Address {issue}`astanin/python-tabulate#151`.
- Add a new `--table-format`/`-t` option to select table format rendering mode.
- Add new dependency on `cli-helper` and `tabulate`.
- Automate post-release version bump.

## {gh}`1.1.1 (2021-11-01) <compare/v1.1.0...v1.1.1>`

- Fix printing of additional non-grouped default options in help screen.

## {gh}`1.1.0 (2021-10-28) <compare/v1.0.1...v1.1.0>`

- Add a `--config`/`-C` option to load CLI configuration from a TOML file.

## {gh}`1.0.1 (2021-10-27) <compare/v1.0.0...v1.0.1>`

- Re-release previous version with fixed dependency.

## {gh}`1.0.0 (2021-10-27) <compare/v0.0.1...v1.0.0>`

- Add colorization of options, choices and metavars in help screens.
- Add `--color`/`--no-color` option flag (aliased to `--ansi`/`--no-ansi`).
- Add colored `--version` option.
- Add colored `--verbosity` option and logs.
- Add dependency on `click-log`.
- `--time`/`--no-time` flag to measure duration of command execution.
- Add platform recognition utilities.
- Add new conditional markers for `pytest`: `@skip_{linux,macos,windows}`,
  `@unless_{linux,macos,windows}`, `@destructive` and `@non_destructive`.

## {gh}`0.0.1 (2021-10-18) <compare/88b81e...v0.0.1>`

- Initial public release.
