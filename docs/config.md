# Configuration loader

The structure of the configuration file is automatically derived from the
parameters of the CLI and their types. There is no need to manually produce a configuration
data structure to mirror the CLI.

## Standalone option

The `@config_option` decorator provided by Click Extra can be used as-is with vanilla Click:

```{eval-rst}
.. click:example::
    from click import group, option, echo

    from click_extra import config_option

    @group(context_settings={"show_default": True})
    @option("--dummy-flag/--no-flag")
    @option("--my-list", multiple=True)
    @config_option()
    def my_cli(dummy_flag, my_list):
        echo(f"dummy_flag    is {dummy_flag!r}")
        echo(f"my_list       is {my_list!r}")

    @my_cli.command
    @option("--int-param", type=int, default=10)
    def subcommand(int_param):
        echo(f"int_parameter is {int_param!r}")

The code above is saved into a file named ``my_cli.py``.

It produces the following help screen:

.. click:run::
    invoke(my_cli, args=["--help"])

A bare call returns:

.. click:run::
    invoke(my_cli, args=["subcommand"])
```

With a simple TOML file in the application folder, we will change the CLI's default output.

Here is what `~/.config/my-cli/config.toml` contains:

```toml
# My default configuration file.
top_level_param = "is_ignored"

[my-cli]
extra_value = "is ignored too"
dummy_flag = true   # New boolean default.
my_list = ["item 1", "item #2", "Very Last Item!"]

[garbage]
# An empty random section that will be skipped.

[my-cli.subcommand]
int_param = 3
random_stuff = "will be ignored"
```

In the file above, pay attention to:

- the [default configuration base path](#default-folder) (`~/.config/my-cli/` here on Linux) which is OS-dependant;
- the app's folder (`/my-cli/`) which is built from the script's
  name (`my_cli.py`);
- the top-level config section (`[my-cli]`), based on the CLI's
  group ID (`def my_cli()`);
- all the extra comments, sections and values that will be silently ignored.

Now we can verify the configuration file is properly read and change the defaults:

```shell-session
$ my-cli subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 3
```

## Precedence

The configuration loader fetch values according the following precedence:

- `CLI parameters`
  - `Configuration file`
    - `Environment variables`
      - `Defaults`

The parameter will take the first value set in that chain.

See how inline parameters takes priority on defaults from the previous example:

```{code-block} shell-session
---
emphasize-lines: 1, 4
---
$ my-cli subcommand --int-param 555
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 555
```

## Strictness

As you can see [in the example above](#standalone-option), all unrecognized content is ignored.

If for any reason you do not want to allow any garbage in configuration files provided by the user, you can use the `strict` argument.

Given this `cli.toml` file:

```{code-block} toml
---
emphasize-lines: 3
---
[cli]
int_param = 3
random_param = "forbidden"
```

The use of `strict=True` parameter in the CLI below:

```{code-block} python
---
emphasize-lines: 7
---
from click import command, option, echo

from click_extra import config_option

@command
@option("--int-param", type=int, default=10)
@config_option(strict=True)
def cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

Will raise an error and stop the the CLI execution on unrecognized `random_param` value:

```{code-block} shell-session
---
emphasize-lines: 4
---
$ cli --config "cli.toml"
Load configuration matching cli.toml
(...)
ValueError: Parameter 'random_param' is not allowed in configuration file.
```

## Ignoring parameters

The {py:attr}`ignored_params <click_extra.config.ConfigOption.ignored_params>` argument will exclude some of your CLI options from the configuration machinery. This will prevent your CLI users to set these parameters in their configuration files.

It defaults to:
  - `--help`, as it makes no sense to have the configurable file always forces a CLI to show the help and exit.
  - `--version`, which is not a configurable option *per-se*.
  - `-C`/`--config` option, which cannot be used to recursively load another configuration file (yet?).
  - `--show-params` flag, which is like `--help` and stops the CLI execution.

You can set your own list of option to ignore with the `ignored_params` argument:

```{code-block} python
---
emphasize-lines: 7
---
from click import command, option, echo

from click_extra import config_option

@command
@option("--int-param", type=int, default=10)
@config_option(ignored_params=["non_configurable_option", "really_dangerous_param"])
def cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

## Formats

Several dialects are supported:

- [`TOML`](#toml)
- [`YAML`](#yaml)
- [`JSON`](#json), with inline and block comments (Python-style `#` and Javascript-style `//`, thanks to [`commentjson`](https://github.com/vaidik/commentjson))
- [`INI`](#ini), with extended interpolation, multi-level sections and non-native types (`list`, `set`, …)
- [`XML`](#xml)

### TOML

See the [example in the top of this page](standalone-option).

### YAML

The example above, given for a TOML configuration file, is working as-is with YAML.

Just replace the TOML file with the following configuration at
`~/.config/my-cli/config.yaml`:

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
$ my-cli --config "~/.config/my-cli/config.yaml" subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```

### JSON

Again, same for JSON:

```json
{
  "top_level_param": "is_ignored",
  "garbage": {},
  "my-cli": {
    "dummy_flag": true,
    "extra_value": "is ignored too",
    "my_list": [
      "item 1",
      "item #2",
      "Very Last Item!"
    ],
    "subcommand": {
      "int_param": 65,
      "random_stuff": "will be ignored"
    }
  }
}
```

```shell-session
$ my-cli --config "~/.config/my-cli/config.json" subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 65
```

### INI

`INI` configuration files are allowed to use [`ExtendedInterpolation`](https://docs.python.org/3/library/configparser.html?highlight=configparser#configparser.ExtendedInterpolation) by default.

```{todo}
Write example.
```

### XML

```{todo}
Write example.
```

## Pattern matching

The configuration file is searched based on a wildcard-based pattern.

By default, the pattern is `/<app_dir>/*.{toml,yaml,yml,json,ini,xml}`, where:

- `<app_dir>` is the [default application folder (see below)](#default-folder)
- `*.{toml,yaml,yml,json,ini,xml}` is any file in that folder with any of `.toml`, `.yaml`, `.yml`, `.json` , `.ini` or `.xml` extension.

### Default extensions

The extensions that are used for each dialect to produce the default file pattern matching are encoded by
the {py:class}`Formats <click_extra.config.Formats>` Enum:

| Format | Extensions        |
| :----- | :---------------- |
| `TOML` | `*.toml`          |
| `YAML` | `*.yaml`, `*.yml` |
| `JSON` | `*.json`          |
| `INI`  | `*.ini`           |
| `XML`  | `*.xml`           |

The default behavior consist in searching for all files matching the default `*.{toml,yaml,yml,json,ini,xml}` pattern. And parse each of the matchin file with every supported format, in the priority order of the table above. As soon as a file is able to be parsed without error and returns a `dict`, the search stops and the file is used to feed the CLI's default values.

### Forcing formats

If you know in advance the only format you'd like to support, you can use the `formats` argument on your decorator like so:

```{eval-rst}
.. click:example::
    from click import command, option, echo

    from click_extra import config_option
    from click_extra.config import Formats

    @command(context_settings={"show_default": True})
    @option("--int-param", type=int, default=10)
    @config_option(formats=Formats.JSON)
    def cli(int_param):
        echo(f"int_parameter is {int_param!r}")

Notice how the default search pattern gets limited to files with a ``.json`` extension:

.. click:run::
    invoke(cli, args=["--help"])
```

This also works with a subset of formats:

```{eval-rst}
.. click:example::
    from click import command, option, echo

    from click_extra import config_option
    from click_extra.config import Formats

    @command(context_settings={"show_default": True})
    @option("--int-param", type=int, default=10)
    @config_option(formats=[Formats.INI, Formats.YAML])
    def cli(int_param):
        echo(f"int_parameter is {int_param!r}")

.. click:run::
    invoke(cli, args=["--help"])
```

### Default folder

The configuration file is searched in the default application path, as defined by [`click.get_app_dir()`](https://click.palletsprojects.com/en/8.1.x/api/#click.get_app_dir).

Like the latter, the `@config_option` decorator and `ConfigOption` class accept a `roaming` and `force_posix` argument to alter the default path:

| Platform          | `roaming` | `force_posix` | Folder                                    |
| :---------------- | :-------- | :------------ | :---------------------------------------- |
| macOS (default)   | -         | `False`       | `~/Library/Application Support/Foo Bar`   |
| macOS             | -         | `True`        | `~/.foo-bar`                              |
| Unix (default)    | -         | `False`       | `~/.config/foo-bar`                       |
| Unix              | -         | `True`        | `~/.foo-bar`                              |
| Windows (default) | `True`    | -             | `C:\Users\<user>\AppData\Roaming\Foo Bar` |
| Windows           | `False`   | -             | `C:\Users\<user>\AppData\Local\Foo Bar`   |

Let's change the default base folder in the following example:

```{eval-rst}
.. click:example::
    from click import command

    from click_extra import config_option

    @command(context_settings={"show_default": True})
    @config_option(force_posix=True)
    def cli():
        pass

See how the default to ``--config`` option has been changed to ``~/.cli/*.{toml,yaml,yml,json,ini,xml}``:

.. click:run::
    invoke(cli, args=["--help"])
```

### Custom pattern

If you'd like to customize the pattern, you can pass your own to the `default` parameter.

Here is how to look for an extension-less YAML dotfile in the home directory, with a pre-defined `.commandrc` name:

```{eval-rst}
.. click:example::
    from click import command

    from click_extra import config_option
    from click_extra.config import Formats

    @command(context_settings={"show_default": True})
    @config_option(default="~/.commandrc", formats=Formats.YAML)
    def cli():
        pass

.. click:run::
    invoke(cli, args=["--help"])
```

### Pattern specifications

Patterns provided to `@config_option`:

- are [based on `wcmatch.glob` syntax](https://facelessuser.github.io/wcmatch/glob/#syntax)
- should be written with Unix separators (`/`), even for Windows (the [pattern will be normalized to the local platform dialect](https://facelessuser.github.io/wcmatch/glob/#windows-separators))
- are configured with the following default flags:
  - [`IGNORECASE`](https://facelessuser.github.io/wcmatch/glob/#ignorecase): case-insensitive matching
  - [`GLOBSTAR`](https://facelessuser.github.io/wcmatch/glob/#globstar): recursive directory search via `**`
  - [`FOLLOW`](https://facelessuser.github.io/wcmatch/glob/#follow): traverse symlink directories
  - [`DOTGLOB`](https://facelessuser.github.io/wcmatch/glob/#dotglob): allow match of file or directory starting with a dot (`.`)
  - [`BRACE`](https://facelessuser.github.io/wcmatch/glob/#brace): allow brace expansion for greater expressiveness
  - [`GLOBTILDE`](https://facelessuser.github.io/wcmatch/glob/#globtilde): allows for user path expansion via `~`
  - [`NODIR`](https://facelessuser.github.io/wcmatch/glob/#nodir): restricts results to files

### Remote URL

Remote URL can be passed directly to the `--config` option:

```shell-session
$ my-cli --config "https://example.com/dummy/configuration.yaml" subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```

## `--show-params` option

Click Extra provides a ready-to-use `--show-params` option, which is enabled by default.

It produces a comprehensive table of your CLI parameters, normalized IDs, types and corresponding environment variables. And because it dynamiccaly print their default value, actual value and its source, it is a pratical tool for users to introspect and debug the parameters of a CLI.

See how the default `@extra_command` decorator come with the default `--show-params` option and the result of its use:

```{eval-rst}
.. click:example::
    from click_extra import *

    @extra_command()
    @option("--int-param1", type=int, default=10)
    @option("--int-param2", type=int, default=555)
    def cli(int_param1, int_param2):
        echo(f"int_param1 is {int_param1!r}")
        echo(f"int_param2 is {int_param2!r}")

.. click:run::
    invoke(cli, args=["--verbosity", "Debug", "--int-param1", "3", "--show-params"])
```

.. note::
    Notice how `--show-params` is ignoring the ignored parameters provided to `ignored_params`. I.e. you can still see `--help`, `--version`, `-C`/`--config` and `--show-params` in the table.

## `click_extra.config` API

```{eval-rst}
.. automodule:: click_extra.config
   :members:
   :undoc-members:
   :show-inheritance:
```
