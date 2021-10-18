# Click Extra

[![Last release](https://img.shields.io/pypi/v/click-extra.svg)](https://pypi.python.org/pypi/click-extra)
[![Python versions](https://img.shields.io/pypi/pyversions/click-extra.svg)](https://pypi.python.org/pypi/click-extra)
[![Unittests status](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml?query=branch%3Amain)
[![Coverage status](https://codecov.io/gh/kdeldycke/click-extra/branch/main/graph/badge.svg)](https://codecov.io/gh/kdeldycke/click-extra/branch/main)

**What is Click Extra?**

`click-extra` is a collection of helpers and utilities for
[Click](https://click.palletsprojects.com), the Python CLI framework.

It mainly consist of hacks, workarounds and other patches that have not reached
upstream yet. Or are unlikely to be accepted upstream.

## Installation

Install `click-extra` with `pip`:

```shell-session
$ pip install click-extra
```

## Features

- Platform recognition utilities
- `unless_linux`, `unless_macos`, `unless_windows` markers for `pytest`
- `destructive` and `non_destructive` markers for `pytest`
```

### Colorization of help screen

Extend [Cloup's theme]() to add colorization of:
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
