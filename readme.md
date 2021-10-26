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

- [Meta Package Manager](https://github.com/kdeldycke/meta-package-manager#readme) - A unifying CLI for multiple package managers.
- [Mail Deduplicate](https://github.com/kdeldycke/mail-deduplicate#readme) - A CLI to deduplicate similar emails.

## Installation

Install `click-extra` with `pip`:

```shell-session
$ pip install click-extra
```

## Features

- Colorization of help screens
- ``--color/--no-color`` option flag
- Colored ``--version`` option
- Colored ``--verbosity`` option and logs
- ``--time/--no-time`` flag to measure duration of command execution
- Platform recognition utilities
- New conditional markers for `pytest`:
    - `@skip_linux`, `@skip_macos` and `@skip_windows`
    - `@unless_linux`, `@unless_macos` and `@unless_windows`
    - `@destructive` and `@non_destructive`

### Colorization of help screen

Extend [Cloup's own help formatter and theme](https://cloup.readthedocs.io/en/stable/pages/formatting.html#help-formatting-and-themes) to add colorization of:
- Options
- Choices
- Metavars

This has been discussed upstream at:
- https://github.com/janluke/cloup/issues/97
- https://github.com/click-contrib/click-help-colors/issues/17
- https://github.com/janluke/cloup/issues/95

## Dependencies

Here is a graph of Python package dependencies:

![click-extra dependency graph](https://github.com/kdeldycke/click-extra/blob/main/dependencies.png)

## Development

[Development guidelines](https://kdeldycke.github.io/meta-package-manager/development.html)
are the same as
[parent project `mpm`](https://github.com/kdeldycke/meta-package-manager), from
which `click-extra` originated.
