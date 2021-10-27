# Changelog

## [1.0.1 (unreleased)](https://github.com/kdeldycke/click-extra/compare/v1.0.0...main)

```{important}
This version is not released yet and is under active development.
```

- Re-release previous version with fixed dependency.

## [1.0.0 (2021-10-27)](https://github.com/kdeldycke/click-extra/compare/v0.0.1...v1.0.0)

- Add colorization of options, choices and metavars in help screens.
- Add ``--color/--no-color`` option flag (aliased to ``--ansi/--no-ansi``).
- Add colored ``--version`` option.
- Add colored ``--verbosity`` option and logs.
- Add dependency on ``click-log``.
- ``--time/--no-time`` flag to measure duration of command execution.
- Add platform recognition utilities.
- Add new conditional markers for `pytest`: `@skip_{linux,macos,windows}`, `@unless_{linux,macos,windows}`, `@destructive` and `@non_destructive`.

## [0.0.1 (2021-10-18)](https://github.com/kdeldycke/click-extra/compare/88b81e...v0.0.1)

- Initial public release.
