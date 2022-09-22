<p align="center">
  <a href="https://github.com/kdeldycke/click-extra/">
    <img src="https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/images/logo-banner.svg" alt="Click Extra">
  </a>
</p>

[![Last release](https://img.shields.io/pypi/v/click-extra.svg)](https://pypi.python.org/pypi/click-extra)
[![Python versions](https://img.shields.io/pypi/pyversions/click-extra.svg)](https://pypi.python.org/pypi/click-extra)
[![Unittests status](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml?query=branch%3Amain)
[![Documentation status](https://github.com/kdeldycke/click-extra/actions/workflows/docs.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/click-extra/actions/workflows/docs.yaml?query=branch%3Amain)
[![Coverage status](https://codecov.io/gh/kdeldycke/click-extra/branch/main/graph/badge.svg)](https://codecov.io/gh/kdeldycke/click-extra/branch/main)

## What is Click Extra?

A collection of helpers and utilities for
[Click](https://click.palletsprojects.com), the Python CLI framework.

It is a drop-in replacement with good defaults that saves you some boilerplate
code. It also comes with
[workarounds and patches](https://kdeldycke.github.io/click-extra/issues.html) that have not
reached upstream yet (or are unlikely to).

## Example

It can transform this vanilla `click` CLI:

![click CLI help screen](https://github.com/kdeldycke/click-extra/raw/main/docs/images/click-help-screen.png)

Into this:

![click-extra CLI help screen](https://github.com/kdeldycke/click-extra/raw/main/docs/images/click-extra-screen.png)

To undestrand how we ended up with the result above, go [read the tutorial](https://kdeldycke.github.io/click-extra/tutorial.html).

## Features

- Configuration file loader for:
  - `TOML`
  - `YAML`
  - `JSON`, with inline and block comments (Python-style `#` and Javascript-style `//`)
  - `INI`, with extended interpolation, multi-level sections and non-native types (`list`, `set`, …)
  - `XML`
- Download configuration from remote URLs
- Optional strict validation of configuration
- Search of configuration file from default user folder and glob patterns
- Respect of `CLI` > `Configuration` > `Environment` > `Defaults` precedence
- `--show-params` option to debug parameters defaults, values, environment variables and provenance
- Colorization of help screens
- `-h`/`--help` option names (see [rant on other inconsistencies](https://blog.craftyguy.net/cmdline-help/))
- `--color`/`--no-color` option flag
- Recognize the `NO_COLOR` environment variable convention from [`no-color.org`](https://no-color.org)
- Colored `--version` option
- Colored `--verbosity` option and logs
- `--time`/`--no-time` flag to measure duration of command execution
- Platform recognition utilities (macOS, Linux and Windows)
- New conditional markers for `pytest`:
  - `@skip_linux`, `@skip_macos` and `@skip_windows`
  - `@unless_linux`, `@unless_macos` and `@unless_windows`
  - `@destructive` and `@non_destructive`
- [ANSI-capable Pygments lexers](https://kdeldycke.github.io/click-extra/pygments.html#lexers) for shell session and console output
- Pygments styles and filters for ANSI rendering
- [Fixes 30+ bugs](https://kdeldycke.github.io/click-extra/issues.html) from other Click-related projects
- Rely on [`cloup`](https://github.com/janluke/cloup) to add:
  - option groups
  - constraints
  - subcommands sections
  - aliases
  - command suggestion (`Did you mean <subcommand>?`)

## Used in

Check these projects to get real-life examples of `click-extra` usage:

- [Mail Deduplicate](https://github.com/kdeldycke/mail-deduplicate#readme) - A
  CLI to deduplicate similar emails.
- [Meta Package Manager](https://github.com/kdeldycke/meta-package-manager#readme)
  \- A unifying CLI for multiple package managers.

## Development

[Development guidelines](https://kdeldycke.github.io/meta-package-manager/development.html)
are the same as
[parent project `mpm`](https://github.com/kdeldycke/meta-package-manager), from
which `click-extra` originated.
