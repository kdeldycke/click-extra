# Click Extra

[![Last release](https://img.shields.io/pypi/v/click-extra.svg)](https://pypi.python.org/pypi/click-extra)
[![Python versions](https://img.shields.io/pypi/pyversions/click-extra.svg)](https://pypi.python.org/pypi/click-extra)
[![Unittests status](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml?query=branch%3Amain)
[![Coverage status](https://codecov.io/gh/kdeldycke/click-extra/branch/main/graph/badge.svg)](https://codecov.io/gh/kdeldycke/click-extra/branch/main)

**What is Click Extra?**

`click-extra` is a collection of helpers and utilities for
[Click](https://click.palletsprojects.com), the Python CLI framework.

It provides boilerplate code and good defaults, as weel as some workarounds
and patches that have not reached upstream yet (or are unlikely to).

## Used in

- [Mail Deduplicate](https://github.com/kdeldycke/mail-deduplicate#readme) - A CLI to deduplicate similar emails.
- [Meta Package Manager](https://github.com/kdeldycke/meta-package-manager#readme) - A unifying CLI for multiple package managers.

## Installation

Install `click-extra` with `pip`:

```shell-session
$ pip install click-extra
```

## Features

- TOML configuration file loader
- Colorization of help screens
- ``--color/--no-color`` option flag
- Colored ``--version`` option
- Colored ``--verbosity`` option and logs
- ``--time/--no-time`` flag to measure duration of command execution
- Platform recognition utilities (macOS, Linux and Windows)
- New conditional markers for `pytest`:
    - `@skip_linux`, `@skip_macos` and `@skip_windows`
    - `@unless_linux`, `@unless_macos` and `@unless_windows`
    - `@destructive` and `@non_destructive`

### Issues addressed by `click-extra`

Keep track of things to undo if they reach upstream.

[`click`](https://github.com/pallets/click):
  - [`testing.CliRunner.invoke` cannot pass color for `Context` instantiation (#2110)](https://github.com/pallets/click/issues/2110)

[`click-log`](https://github.com/click-contrib/click-log):
  - [Add a `no-color` option, method or parameter to disable colouring globally (#30)](https://github.com/click-contrib/click-log/issues/30)
  - [Log level is leaking between invokations: hack to force-reset it (#29)](https://github.com/click-contrib/click-log/issues/29)
  - [Add missing string interpolation in error message (#24)](https://github.com/click-contrib/click-log/pull/24)
  - [Add trailing dot to help text (#18)](https://github.com/click-contrib/click-log/pull/18)

[`click-help-color`](https://github.com/click-contrib/click-help-colors):
  - [Highlighting of options, choices and metavars (#17)](https://github.com/click-contrib/click-help-colors/issues/17)

[`cli-helper`](https://github.com/dbcli/cli_helpers):
  - [Replace local tabulate formats with those available upstream (#79)](https://github.com/dbcli/cli_helpers/issues/79)

[`cloup`](https://github.com/janluke/cloup):
  - [Add support for option groups on `cloup.Group` (#98)](https://github.com/janluke/cloup/issues/98)
  - [Styling metavars, default values, env var, choices (#97)](https://github.com/janluke/cloup/issues/97) & [Highlights options, choices and metavars (#95)](https://github.com/janluke/cloup/issues/95)
  - [Add loading of options from a TOML configuration file (#96)](https://github.com/janluke/cloup/issues/96)

[`python-tabulate`](https://github.com/astanin/python-tabulate):
  - [Add new {`rounded`,`simple`,`double`}_(`grid`,`outline`} formats (#151)](https://github.com/astanin/python-tabulate/pull/151)

### TOML configuration file

Allows a CLI to read defaults options from a configuration file.

Here is a sample:

``` toml
# My default configuration file.

[my_cli]
verbosity = "DEBUG"
manager = ["brew", "cask"]

[my_cli.search]
exact = true
```

### Colorization of help screen

Extend [Cloup's own help formatter and theme](https://cloup.readthedocs.io/en/stable/pages/formatting.html#help-formatting-and-themes) to add colorization of:
- Options
- Choices
- Metavars

## Dependencies

Here is a graph of Python package dependencies:

![click-extra dependency graph](https://github.com/kdeldycke/click-extra/raw/main/dependencies.png)

## Development

[Development guidelines](https://kdeldycke.github.io/meta-package-manager/development.html)
are the same as
[parent project `mpm`](https://github.com/kdeldycke/meta-package-manager), from
which `click-extra` originated.
