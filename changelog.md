# Changelog

## [1.3.1 (unreleased)](https://github.com/kdeldycke/click-extra/compare/v1.3.0...main)

```{{important}}
This version is not released yet and is under active development.
```

- Allow downloading of a remote config URL.
- Add new dependency on `requests`.
- Fix inference of config file top-level section name.
- Document usage of `click_extra.config.config_option`.

## [1.3.0 (2021-11-28)](https://github.com/kdeldycke/click-extra/compare/v1.2.2...v1.3.0)

- Add support for YAML configuration file. Closes #13.
- Auto-detect configuration file on loading.
- Add `pyyaml` dependency.

## [1.2.2 (2021-11-04)](https://github.com/kdeldycke/click-extra/compare/v1.2.1...v1.2.2)

- Evaluate format option dynamiccaly at use to let third-party register new rendering formats.

## [1.2.1 (2021-11-04)](https://github.com/kdeldycke/click-extra/compare/v1.2.0...v1.2.1)

- Fix creation of post-release version bump PR on tagging.

## [1.2.0 (2021-11-04)](https://github.com/kdeldycke/click-extra/compare/v1.1.1...v1.2.0)

- Extend `cli-helper.TabularOutputFormatter` with new formats: `simple_grid`,
  `rounded_grid`, `double_grid`, `outline`, `simple_outline`, `rounded_outline` and
  `double_outline`. Address [astanin/python-tabulate:#151)](https://github.com/astanin/python-tabulate/pull/151).
- Add a new `--table-format`/`-t` option to select table format rendering mode.
- Add new dependency on `cli-helper` and `tabulate`.
- Automate post-release version bump.

## [1.1.1 (2021-11-01)](https://github.com/kdeldycke/click-extra/compare/v1.1.0...v1.1.1)

- Fix printing of additional non-grouped default options in help screen.

## [1.1.0 (2021-10-28)](https://github.com/kdeldycke/click-extra/compare/v1.0.1...v1.1.0)

- Add a `--config`/`-C` option to load CLI configuration from a TOML file.

## [1.0.1 (2021-10-27)](https://github.com/kdeldycke/click-extra/compare/v1.0.0...v1.0.1)

- Re-release previous version with fixed dependency.

## [1.0.0 (2021-10-27)](https://github.com/kdeldycke/click-extra/compare/v0.0.1...v1.0.0)

- Add colorization of options, choices and metavars in help screens.
- Add `--color`/`--no-color` option flag (aliased to `--ansi`/`--no-ansi`).
- Add colored `--version` option.
- Add colored `--verbosity` option and logs.
- Add dependency on `click-log`.
- `--time`/`--no-time` flag to measure duration of command execution.
- Add platform recognition utilities.
- Add new conditional markers for `pytest`: `@skip_{linux,macos,windows}`, `@unless_{linux,macos,windows}`, `@destructive` and `@non_destructive`.

## [0.0.1 (2021-10-18)](https://github.com/kdeldycke/click-extra/compare/88b81e...v0.0.1)

- Initial public release.
