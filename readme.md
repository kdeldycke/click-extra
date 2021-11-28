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

- TOML and YAML configuration file loader
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
  - [`#2111` - `Context.color = False` doesn't overrides `echo(color=True)`](https://github.com/pallets/click/issues/2111)
  - [`#2110` - `testing.CliRunner.invoke` cannot pass color for `Context` instantiation](https://github.com/pallets/click/issues/2110)

[`click-log`](https://github.com/click-contrib/click-log):
  - [`#30` - Add a `no-color` option, method or parameter to disable colouring globally](https://github.com/click-contrib/click-log/issues/30)
  - [`#29` - Log level is leaking between invokations: hack to force-reset it](https://github.com/click-contrib/click-log/issues/29)
  - [`#24` - Add missing string interpolation in error message](https://github.com/click-contrib/click-log/pull/24)
  - [`#18` - Add trailing dot to help text](https://github.com/click-contrib/click-log/pull/18)

[`click-help-color`](https://github.com/click-contrib/click-help-colors):
  - [`#17` - Highlighting of options, choices and metavars](https://github.com/click-contrib/click-help-colors/issues/17)

[`cli-helper`](https://github.com/dbcli/cli_helpers):
  - [`#79` -Replace local tabulate formats with those available upstream](https://github.com/dbcli/cli_helpers/issues/79)

[`cloup`](https://github.com/janluke/cloup):
  - [`#98` - Add support for option groups on `cloup.Group`](https://github.com/janluke/cloup/issues/98)
  - [`#97` - Styling metavars, default values, env var, choices](https://github.com/janluke/cloup/issues/97)
  - [`#95` - Highlights options, choices and metavars](https://github.com/janluke/cloup/issues/95)
  - [`#96` - Add loading of options from a TOML configuration file](https://github.com/janluke/cloup/issues/96)

[`python-tabulate`](https://github.com/astanin/python-tabulate):
  - [`#151` - Add new {`rounded`,`simple`,`double`}_(`grid`,`outline`} formats](https://github.com/astanin/python-tabulate/pull/151)

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
