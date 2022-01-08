# Click Extra

[![Last release](https://img.shields.io/pypi/v/click-extra.svg)](https://pypi.python.org/pypi/click-extra)
[![Python versions](https://img.shields.io/pypi/pyversions/click-extra.svg)](https://pypi.python.org/pypi/click-extra)
[![Unittests status](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml?query=branch%3Amain)
[![Coverage status](https://codecov.io/gh/kdeldycke/click-extra/branch/main/graph/badge.svg)](https://codecov.io/gh/kdeldycke/click-extra/branch/main)

**What is Click Extra?**

`click-extra` is a collection of helpers and utilities for
[Click](https://click.palletsprojects.com), the Python CLI framework.

It provides boilerplate code and good defaults, as well as some workarounds and
patches that have not reached upstream yet (or are unlikely to).

## Features

- TOML and YAML configuration file loader
- Colorization of help screens
- `--color/--no-color` option flag
- Colored `--version` option
- Colored `--verbosity` option and logs
- `--time/--no-time` flag to measure duration of command execution
- Platform recognition utilities (macOS, Linux and Windows)
- New conditional markers for `pytest`:
  - `@skip_linux`, `@skip_macos` and `@skip_windows`
  - `@unless_linux`, `@unless_macos` and `@unless_windows`
  - `@destructive` and `@non_destructive`

## Installation

Install `click-extra` with `pip`:

```shell-session
$ pip install click-extra
```

## Configuration loader usage

### TOML configuration

Given this CLI in a `my_cli.py` file:

```python
import click

from click_extra.config import config_option


@click.group(context_settings={"show_default": True})
@click.option("--dummy-flag/--no-flag")
@click.option("--my-list", multiple=True)
@config_option()
def my_cli(dummy_flag, my_list):
    click.echo(f"dummy_flag    is {dummy_flag!r}")
    click.echo(f"my_list       is {my_list!r}")


@my_cli.command()
@click.option("--int-param", type=int, default=10)
def subcommand(int_param):
    click.echo(f"int_parameter is {int_param!r}")


if __name__ == "__main__":
    my_cli()
```

It produces the following help screens:

```shell-session
$ python ./my_cli.py
Usage: my_cli.py [OPTIONS] COMMAND [ARGS]...

Options:
  --dummy-flag / --no-flag  [default: no-flag]
  --my-list TEXT
  -C, --config CONFIG_PATH  Location of the configuration file. Supports both
                            local path and remote URL.  [default: s(dynamic)]
  --help                    Show this message and exit.  [default: False]

Commands:
  subcommand
```

A bare call returns:

```shell-session
$ ./my_cli.py subcommand
dummy_flag    is False
my_list       is ()
int_parameter is 10
```

Now we will change the default CLI output by creating a TOML file at
`~/.my_cli.py/config.toml` which contains:

```toml
# My default configuration file.
top_level_param = "is_ignored"

[my-cli]
extra_value = "is ignored too"
dummy_flag = true   # New boolean default.
my_list = ["item 1", "item #2", "Very Last Item!"]

[garbage]
# An empty random section that will be skipped

[my-cli.subcommand]
int_param = 3
random_stuff = "will be ignored"
```

In the file above, pay attention to:

- the configuration's folder (`~/.my_cli.py/`) which correspond to the script's
  name (`my_cli.py`);
- the top-level config section (`[my-cli]`), that is derived from the CLI's
  group ID (`def my_cli()`);
- all the extra comments, sections and values that will be silently ignored.

Now we can verify the TOML file is read automatticaly and change the defaults:

```shell-session
$ ./my_cli.py subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 3
```

Still, any inline parameter is allowedal to ovverides the configuration
defaults:

```shell-session
$ ./my_cli.py subcommand --int-param 555
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 555
```

### YAML configuration

Same example as above is working as-is with YAML.

Just replace the TOML file with the following configuration at
`~/.my_cli.py/config.yaml`:

```yaml
# My default configuration file.
top_level_param: is_ignored

my-cli:
  extra_value: is ignored too
  dummy_flag: true   # New boolean default.
  my_list:
    - point 1
    - 'point #2'
    - Very Last Point!

  subcommand:
    int_param: 77
    random_stuff: will be ignored

garbage: >
  An empty random section that will be skipped
```

```shell-session
$ ./my_cli.py --config ~/.my_cli.py/config.yaml subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```

### Remote configuration

Remote URL can be passed directly to the `--config` option:

```shell-session
$ ./my_cli.py --config https://example.com/dummy/configuration.yaml subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```

## Colorization of help screen

Extend
[Cloup's own help formatter and theme](https://cloup.readthedocs.io/en/stable/pages/formatting.html#help-formatting-and-themes)
to add colorization of:

- Options
- Choices
- Metavars

## Used in

Check these projects to get real-life example of `click-extra` usage:

- [Mail Deduplicate](https://github.com/kdeldycke/mail-deduplicate#readme) - A
  CLI to deduplicate similar emails.
- [Meta Package Manager](https://github.com/kdeldycke/meta-package-manager#readme)
  \- A unifying CLI for multiple package managers.

## Issues addressed by `click-extra`

Keep track of things to undo if they reach upstream.

[`click`](https://github.com/pallets/click):

- [`#2111` - `Context.color = False` doesn't overrides `echo(color=True)`](https://github.com/pallets/click/issues/2111)
- [`#2110` - `testing.CliRunner.invoke` cannot pass color for `Context` instantiation](https://github.com/pallets/click/issues/2110)

[`click-config-file`](https://github.com/phha/click_config_file):

- [`#9` - Additional configuration providers](https://github.com/phha/click_config_file/issues/9)

[`click-help-color`](https://github.com/click-contrib/click-help-colors):

- [`#17` - Highlighting of options, choices and metavars](https://github.com/click-contrib/click-help-colors/issues/17)

[`click-log`](https://github.com/click-contrib/click-log):

- [`#30` - Add a `no-color` option, method or parameter to disable colouring globally](https://github.com/click-contrib/click-log/issues/30)
- [`#29` - Log level is leaking between invokations: hack to force-reset it](https://github.com/click-contrib/click-log/issues/29)
- [`#24` - Add missing string interpolation in error message](https://github.com/click-contrib/click-log/pull/24)
- [`#18` - Add trailing dot to help text](https://github.com/click-contrib/click-log/pull/18)

[`cli-helper`](https://github.com/dbcli/cli_helpers):

- [`#79` -Replace local tabulate formats with those available upstream](https://github.com/dbcli/cli_helpers/issues/79)

[`cloup`](https://github.com/janluke/cloup):

- [`#98` - Add support for option groups on `cloup.Group`](https://github.com/janluke/cloup/issues/98)
- [`#97` - Styling metavars, default values, env var, choices](https://github.com/janluke/cloup/issues/97)
- [`#95` - Highlights options, choices and metavars](https://github.com/janluke/cloup/issues/95)
- [`#96` - Add loading of options from a TOML configuration file](https://github.com/janluke/cloup/issues/96)

[`python-tabulate`](https://github.com/astanin/python-tabulate):

- [`#151` - Add new {`rounded`,`simple`,`double`}\_(`grid`,`outline`} formats](https://github.com/astanin/python-tabulate/pull/151)

## Dependencies

Here is a graph of Python package dependencies:

![click-extra dependency graph](https://github.com/kdeldycke/click-extra/raw/main/dependencies.png)

## Development

[Development guidelines](https://kdeldycke.github.io/meta-package-manager/development.html)
are the same as
[parent project `mpm`](https://github.com/kdeldycke/meta-package-manager), from
which `click-extra` originated.
