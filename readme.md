<p align="center">
  <a href="https://github.com/kdeldycke/click-extra/">
    <img src="https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/logo-banner.svg" alt="Click Extra">
  </a>
</p>

[![Last release](https://img.shields.io/pypi/v/click-extra.svg)](https://pypi.python.org/pypi/click-extra)
[![Python versions](https://img.shields.io/pypi/pyversions/click-extra.svg)](https://pypi.python.org/pypi/click-extra)
[![Unittests status](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml?query=branch%3Amain)
[![Documentation status](https://github.com/kdeldycke/click-extra/actions/workflows/docs.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/click-extra/actions/workflows/docs.yaml?query=branch%3Amain)
[![Coverage status](https://codecov.io/gh/kdeldycke/click-extra/branch/main/graph/badge.svg)](https://app.codecov.io/gh/kdeldycke/click-extra)
[![DOI](https://zenodo.org/badge/418402236.svg)](https://zenodo.org/badge/latestdoi/418402236)

## What is Click Extra?

A ready-to-use wrapper for [Click](https://click.palletsprojects.com), the Python CLI framework.

It is a drop-in replacement with good defaults that saves lots of boilerplate code and frustration.
It also comes with
[workarounds and patches](https://kdeldycke.github.io/click-extra/issues.html) that have not
reached upstream yet (or are unlikely to).

## Example

It transforms this vanilla `click` CLI:

![click CLI help screen](https://github.com/kdeldycke/click-extra/raw/main/docs/assets/click-help-screen.png)

Into this:

![click-extra CLI help screen](https://github.com/kdeldycke/click-extra/raw/main/docs/assets/click-extra-screen.png)

To undestrand how we ended up with the result above, [go read the tutorial](https://kdeldycke.github.io/click-extra/tutorial.html).

## Features

- Configuration file loader for:
  - `TOML`
  - `YAML`
  - `JSON`, with inline and block comments (Python-style `#` and Javascript-style `//`)
  - `INI`, with extended interpolation, multi-level sections and non-native types (`list`, `set`, …)
  - `XML`
- Automatic inference of the configuration file structure from your CLI's options
- Remote loading of configuration files from URLs
- Optional strict validation of configuration
- Search of configuration file from default user folder and glob patterns
- Respect of `CLI` > `Configuration` > `Environment` > `Defaults` precedence
- `--show-params` option to debug parameters defaults, values, environment variables and provenance
- Colorization of help screens
- `-h`/`--help` option names (see [rant on other inconsistencies](https://blog.craftyguy.net/cmdline-help/))
- `--color`/`--no-color` option flag
- `--telemetry`/`--no-telemetry` flag to opt-in/out of tracking code
- Recognize traditional environment variable conventions:
  - `NO_COLOR` from [`no-color.org`](https://no-color.org)
  - `DO_NOT_TRACK` from [`consoledonottrack.com`](https://consoledonottrack.com)
- Colored `--version` option
- Colored `--verbosity` option and logs
- `--time`/`--no-time` flag to measure duration of command execution
- Platform recognition utilities (macOS, Linux, Windows, UNIX, \*BSD, …)
- New conditional markers for `pytest`:
  - `@skip_linux`, `@skip_macos` and `@skip_windows`
  - `@unless_linux`, `@unless_macos` and `@unless_windows`
  - `@destructive` and `@non_destructive`
- [`.. click:example::` and `.. click:run::` Sphinx directives](https://kdeldycke.github.io/click-extra/sphinx.html) to document CLI source code and their execution
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

- ![GitHub stars](https://img.shields.io/github/stars/kdeldycke/meta-package-manager?label=%E2%AD%90&style=flat-square) [Meta Package Manager](https://github.com/kdeldycke/meta-package-manager#readme)
  \- A unifying CLI for multiple package managers.
- ![GitHub stars](https://img.shields.io/github/stars/kdeldycke/mail-deduplicate?label=%E2%AD%90&style=flat-square) [Mail Deduplicate](https://github.com/kdeldycke/mail-deduplicate#readme) - A
  CLI to deduplicate similar emails.
- ![GitHub stars](https://img.shields.io/github/stars/Sprocket-Security/fireproxng?label=%E2%AD%90&style=flat-square) [fireproxng](https://github.com/Sprocket-Security/fireproxng#readme) - A rewrite of the fireprox tool.
- ![GitHub stars](https://img.shields.io/github/stars/hugolundin/badger?label=%E2%AD%90&style=flat-square) [badger-proxy](https://github.com/hugolundin/badger#readme) - An mDNS-based reverse
  proxy for naming services on a local network.
- ![GitHub stars](https://img.shields.io/github/stars/tclick/mdstab?label=%E2%AD%90&style=flat-square) [Molecular Dynamics Trajectory Analysis](https://github.com/tclick/mdstab#readme)

Feel free to send a PR to add your project in this list if you are relying on Click Extra in any way.

## Development

[Development guidelines](https://kdeldycke.github.io/meta-package-manager/development.html)
are the same as
[parent project `mpm`](https://github.com/kdeldycke/meta-package-manager), from
which `click-extra` originated.
