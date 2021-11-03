# Changelog


## [1.2.0 (unreleased)](https://github.com/kdeldycke/click-extra/compare/v1.1.1...main)

```{important}
This version is not released yet and is under active development.
```

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
