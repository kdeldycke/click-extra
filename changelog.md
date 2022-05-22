# Changelog

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
