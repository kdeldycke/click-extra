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

**What is Click Extra?**

A collection of helpers and utilities for
[Click](https://click.palletsprojects.com), the Python CLI framework.

It is a drop-in replacement with good defaults that saves you some boilerplate
code. It also comes with some
[workarounds and patches](#issues-addressed-by-click-extra) that have not
reached upstream yet (or are unlikely to).

<table><tr>
<td>Simple <code>click</code> example</td>
<td>Same with <code>click-extra</code></td>
</tr><tr>
<td>

```python
from click import command, echo, option


@command()
@option("--count", default=1, help="Number of greetings.")
@option("--name", prompt="Your name", help="The person to greet.")
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        echo(f"Hello, {name}!")


if __name__ == "__main__":
    hello()
```

</td><td>

```python
from click_extra import command, echo, option


@command()
@option("--count", default=1, help="Number of greetings.")
@option("--name", prompt="Your name", help="The person to greet.")
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        echo(f"Hello, {name}!")


if __name__ == "__main__":
    hello()
```

</td></tr>
<tr>
<td><img alt="click CLI help screen" width="70%" src="https://github.com/kdeldycke/click-extra/raw/main/docs/images/click-help-screen.png"/></td>
<td><img alt="click-extra CLI help screen" width="70%" src="https://github.com/kdeldycke/click-extra/raw/main/docs/images/click-extra-screen.png"/></td>
</tr>
</table>

This example demonstrate the all-in-one package with its default options. You
are still free to pick-up some of these options one-by-one, as documented
below.

## Features

- Configuration file loader for:
  - `TOML`
  - `YAML`
  - `JSON`, with inline and block comments (Python-style `#` and Javascript-style `//`)
  - `INI`, with extended interpolation, multi-level sections and non-native types (list, sets, …)
  - `XML`
- Download configuration from remote URLs
- Optional strict validation of configuration
- Automatic search of configuration file from default user folder
- Respect of `CLI > Configuration > Environment > Defaults` precedence
- Colorization of help screens
- `--color/--no-color` option flag
- Recognize the `NO_COLOR` environment variable convention from [`no-color.org`](https://no-color.org)
- Colored `--version` option
- Colored `--verbosity` option and logs
- `--time/--no-time` flag to measure duration of command execution
- Platform recognition utilities (macOS, Linux and Windows)
- New conditional markers for `pytest`:
  - `@skip_linux`, `@skip_macos` and `@skip_windows`
  - `@unless_linux`, `@unless_macos` and `@unless_windows`
  - `@destructive` and `@non_destructive`
- [Fixes 20+ bugs](https://kdeldycke.github.io/click-extra/issues.html) from other Click-related projects

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
