# {octicon}`sliders` Configuration files

The structure of the configuration file is automatically [derived from the
parameters](parameters.md#parameter-structure) of the CLI and their types. There is no need to manually produce a configuration
data structure to mirror the CLI.

## Standalone option

The `@config_option` decorator provided by Click Extra can be used as-is with vanilla Click:

```{click:example}
---
emphasize-lines: 7
---
from click import group, option, echo
from click_extra import config_option

@group(context_settings={"show_default": True})
@option("--dummy-flag/--no-flag")
@option("--my-list", multiple=True)
@config_option
def my_cli(dummy_flag, my_list):
    echo(f"dummy_flag    is {dummy_flag!r}")
    echo(f"my_list       is {my_list!r}")

@my_cli.command
@option("--int-param", type=int, default=10)
def subcommand(int_param):
    echo(f"int_parameter is {int_param!r}")
```

The code above is saved into a file named `my_cli.py`.

It produces the following help screen:

```{click:run}
---
emphasize-lines: 7-10
---
result = invoke(my_cli, args=["--help"])
assert "--config CONFIG_PATH" in result.stdout
```

See in the result above, there is an explicit mention of the default location of the configuration file (`[default: ~/.config/my-cli/*.{toml,yaml,yml,json,json5,jsonc,hjson,ini,xml}]`). This improves discoverability, and [makes sysadmins happy](https://utcc.utoronto.ca/~cks/space/blog/sysadmin/ReportConfigFileLocations), especially those not familiar with your CLI.

A bare call returns:

```{click:run}
from textwrap import dedent
result = invoke(my_cli, args=["subcommand"])
assert result.stdout == dedent("""\
    dummy_flag    is False
    my_list       is ()
    int_parameter is 10
    """
)
```

With a simple TOML file in the application folder, we will change the CLI's default output.

Here is what `~/.config/my-cli/config.toml` contains:

```{code-block} toml
:caption: `~/.config/my-cli/config.toml`
:emphasize-lines: 6,7,13
# My default configuration file.
top_level_param = "is_ignored"

[my-cli]
extra_value = "is ignored too"
dummy_flag = true                                  # New boolean default.
my_list = ["item 1", "item #2", "Very Last Item!"]

[garbage]
# An empty random section that will be skipped.

[my-cli.subcommand]
int_param = 3
random_stuff = "will be ignored"
```

In the file above, pay attention to:

- the [default configuration base path](#default-folder), which is OS-dependant (the `~/.config/my-cli/` path here is for Linux) ;
- the app's folder (`/my-cli/`) which is built from the script's
  name (`my_cli.py`);
- the top-level config section (`[my-cli]`), based on the CLI's
  group ID (`def my_cli()`);
- all the extra comments, sections and values that will be silently ignored.

Now we can verify the configuration file is properly read and change the defaults:

```{code-block} shell-session
$ my-cli subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 3
```

## Precedence

The configuration loader fetch values according the following precedence:

- `CLI parameters`
  - ↖ `Configuration file`
    - ↖ `Environment variables`
      - ↖ `Defaults`

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

## Get configuration values

After gathering all the configuration from the different sources, and assembling them together following the precedence rules above, the configuration values are merged back into the Context's `default_map`. But only the values that are matching the CLI's parameters are kept and passed as defaults. All others are silently ignored.

You can still access the full configuration by looking into the context's `meta` attribute:

```{code-block} python
---
emphasize-lines: 9-12
---
from click_extra import option, echo, pass_context, command, config_option


@command
@option("--int-param", type=int, default=10)
@config_option
@pass_context
def my_cli(ctx, int_param):
    echo(f"Configuration location: {ctx.meta['click_extra.conf_source']}")
    echo(f"Full configuration: {ctx.meta['click_extra.conf_full']}")
    echo(f"Default values: {ctx.default_map}")
    echo(f"int_param is {int_param!r}")
```

```{code-block} toml
:caption: `./conf.toml`
[my-cli]
int_param = 3
random_stuff = "will be ignored"

[garbage]
dummy_flag = true
```

```{code-block} shell-session
---
emphasize-lines: 3-6
---
$ my-cli --config ./conf.toml --int-param 999
Load configuration matching ./conf.toml
Configuration location: /home/me/conf.toml
Full configuration: {'my-cli': {'int_param': 3, 'random_stuff': 'will be ignored'}, 'garbage': {'dummy_flag': True}}
Default values: {'int_param': 3}
int_parameter is 999
```

```{hint}
Variables in `meta` are presented in their original Python type:
- `click_extra.conf_source` is either a normalized [`Path`](https://docs.python.org/3/library/pathlib.html) or [`URL` object](https://boltons.readthedocs.io/en/latest/urlutils.html#the-url-type)
- `click_extra.conf_full` is a `dict` whose values are either `str` or richer types, depending on the capabilities of [each format](#formats)
```

## Strictness

As you can see [in the first example above](#standalone-option), all unrecognized content is ignored.

If for any reason you do not want to allow any garbage in configuration files provided by the user, you can use the `strict` argument.

Given this `cli.toml` file:

```{code-block} toml
:caption: `cli.toml`
:emphasize-lines: 3
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

Will raise an error and stop the CLI execution on unrecognized `random_param` value:

```{code-block} shell-session
---
emphasize-lines: 4
---
$ cli --config "cli.toml"
Load configuration matching cli.toml
(...)
ValueError: Parameter 'random_param' is not allowed in configuration file.
```

## Excluding parameters

The {py:attr}`excluded_params <click_extra.config.ConfigOption.excluded_params>` argument allows you to block some of your CLI options to be loaded from configuration. By setting this argument, you will prevent your CLI users to set these parameters in their configuration file.

It {py:attr}`defaults to the value of ParamStructure.DEFAULT_EXCLUDED_PARAMS <click_extra.parameters.ParamStructure.DEFAULT_EXCLUDED_PARAMS>`.

You can set your own list of option to ignore with the `excluded_params` argument:

```{code-block} python
---
emphasize-lines: 7
---
from click import command, option, echo

from click_extra import config_option

@command
@option("--int-param", type=int, default=10)
@config_option(excluded_params=["my-cli.non_configurable_option", "my-cli.dangerous_param"])
def my_cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

```{attention}
You need to provide the fully-qualified ID of the option you're looking to block. I.e. the dot-separated ID that is prefixed by the CLI name. That way you can specify an option to ignore at any level, including subcommands.

If you have difficulties identifying your options and their IDs, run your CLI with the [`--show-params` option](#show-params-option) for introspection.
```

## Formats

Several dialects are supported:

| Format            | Description                                                                               | Extensions        | Enabled by default |
| :---------------- | :---------------------------------------------------------------------------------------- | :---------------- | :----------------- |
| [`TOML`](#toml)   | -                                                                                         | `*.toml`          | ✅                 |
| [`YAML`](#yaml)   | -                                                                                         | `*.yaml`, `*.yml` | ❌                 |
| [`JSON`](#json)   | -                                                                                         | `*.json`          | ✅                 |
| [`JSON5`](#json5) | A [superset of JSON made for configuration file](https://json5.org)                       | `*.json5`         | ❌                 |
| [`JSONC`](#jsonc) | Like JSON, but with comments and trailing commas                                          | `*.jsonc`         | ❌                 |
| [`HJSON`](#hjson) | Another flavor of a [user-friendly JSON](https://hjson.github.io)                         | `*.hjson`         | ❌                 |
| [`INI`](#ini)     | With extended interpolation, multi-level sections and non-native types (`list`, `set`, …) | `*.ini`           | ✅                 |
| [`XML`](#xml)     | -                                                                                         | `*.xml`           | ❌                 |

### TOML

See the [example in the top of this page](#standalone-option).

### YAML

```{important}
YAML support requires additional packages. You need to [install `click_extra[yaml]`](install.md#extra-dependencies) extra dependency group to enable it.
```

The example above, given for a TOML configuration file, is working as-is with YAML.

Just replace the TOML file with the following configuration at
`~/.config/my-cli/config.yaml`:

```{code-block} yaml
:caption: `~/.config/my-cli/config.yaml`
:emphasize-lines: 6,7-10,13
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

```{code-block} shell-session
---
emphasize-lines: 2-4
---
$ my-cli --config "~/.config/my-cli/config.yaml" subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```

### JSON

Again, same for JSON:

```{code-block} json
:caption: `~/.config/my-cli/config.json`
:emphasize-lines: 5,7-11,13
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

```{code-block} shell-session
---
emphasize-lines: 2-4
---
$ my-cli --config "~/.config/my-cli/config.json" subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 65
```

### JSON5

```{important}
JSON5 support requires additional packages. You need to [install `click_extra[json5]`](install.md#extra-dependencies) extra dependency group to enable it.
```

```{todo}
Write example.
```

### JSONC

```{important}
JSONC support requires additional packages. You need to [install `click_extra[jsonc]`](install.md#extra-dependencies) extra dependency group to enable it.
```

```{todo}
Write example.
```

### HJSON

```{important}
HJSON support requires additional packages. You need to [install `click_extra[hjson]`](install.md#extra-dependencies) extra dependency group to enable it.
```

```{todo}
Write example.
```

### INI

`INI` configuration files are allowed to use [`ExtendedInterpolation`](https://docs.python.org/3/library/configparser.html?highlight=configparser#configparser.ExtendedInterpolation) by default.

```{todo}
Write example.
```

### XML

```{important}
XML support requires additional packages. You need to [install `click_extra[xml]`](install.md#extra-dependencies) extra dependency group to enable it.
```

```{todo}
Write example.
```

## Search pattern

The configuration file is searched based on a wildcard-based glob pattern.

By default, the pattern is `<app_dir>/*.{toml,json,ini}`, where:

- `<app_dir>` is the [default application folder](#default-folder)
- `*.{toml,json,ini}` are the [extensions of formats](#formats) enabled by default

```{hint}
Depending on the formats you enabled in your installation of Click Extra, the default extensions may vary. For example, if you installed Click Extra with all extra dependencies, the default extensions would be `*.{toml,yaml,yml,json,json5,jsonc,hjson,ini,xml}`.
```

```{seealso}
There is a long history about the choice of the default application folder.

For Unix, the oldest reference I can track is from the [*Where Configurations Live* chapter](http://www.catb.org/~esr/writings/taoup/html/ch10s02.html)
of [The Art of Unix Programming](https://a.co/d/aC36Ft0).

The [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html) is the latest iteration of this tradition on Linux. This long-due guidelines brings [lots of benefits](https://xdgbasedirectoryspecification.com) to the platform. This is what Click Extra is [implementing by default](#default-folder).

But there is still a lot of cases for which the XDG doesn't cut it, like on other platforms (macOS, Windows, …) or for legacy applications. That's why Click Extra allows you to customize the way configuration is searched and located.
```

### Default folder

The configuration file is searched in the default application path, as defined by [`click.get_app_dir()`](https://click.palletsprojects.com/en/stable/api/#click.get_app_dir).

Like the latter, the `@config_option` decorator accept a `roaming` and `force_posix` argument to alter the default path:

| Platform          | `roaming` | `force_posix` | Folder                                    |
| :---------------- | :-------- | :------------ | :---------------------------------------- |
| macOS (default)   | -         | `False`       | `~/Library/Application Support/Foo Bar`   |
| macOS             | -         | `True`        | `~/.foo-bar`                              |
| Unix (default)    | -         | `False`       | `~/.config/foo-bar`                       |
| Unix              | -         | `True`        | `~/.foo-bar`                              |
| Windows (default) | `True`    | -             | `C:\Users\<user>\AppData\Roaming\Foo Bar` |
| Windows           | `False`   | -             | `C:\Users\<user>\AppData\Local\Foo Bar`   |

Let's change the default base folder in the following example:

```{click:example}
---
emphasize-lines: 6
---
from click import command

from click_extra import config_option

@command(context_settings={"show_default": True})
@config_option(force_posix=True)
def cli():
    pass
```

See how the default to `--config` option has been changed to `~/.cli/`:

```{click:run}
---
emphasize-lines: 7
---
result = invoke(cli, args=["--help"])
assert "~/.cli/*.{" in result.stdout
```

### Custom pattern

You can directly provide a customized search pattern to the `default` argument of the decorator:

```{click:example}
---
emphasize-lines: 6
---
from click import command

from click_extra import config_option

@command(context_settings={"show_default": True})
@config_option(default="~/my_special_folder/*.{toml,conf}")
def cli():
    pass
```

```{click:run}
---
emphasize-lines: 7
---
result = invoke(cli, args=["--help"])
assert "~/my_special_folder/*.{toml,conf}]" in result.stdout
```

The rules for the pattern are described in the next section.

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

### Extension-less files

This is an example of a special case that is popular on Unix-like systems: the configuration file is an extension-less dotfile in the home directory.

Here is how to set up `@config_option` for a pre-defined `.commandrc` file in YAML:

```{click:example}
---
emphasize-lines: 7
---
from click import command

from click_extra import config_option
from click_extra.config import Formats

@command(context_settings={"show_default": True})
@config_option(default="~/.commandrc", formats=Formats.YAML)
def cli():
    pass
```

```{click:run}
---
emphasize-lines: 7
---
result = invoke(cli, args=["--help"])
assert "~/.commandrc]" in result.stdout
```

### Multi-format matching

The default behavior consist in searching for all files matching the default `*.{toml,json,ini}` pattern.

A parsing attempt is made for each file matching the extension pattern, in the order of the table above.

As soon as a file is able to be parsed without error and returns a `dict`, the search stops and the file is used to feed the CLI's default values.

### Forcing formats

If you know in advance the only format you'd like to support, you can use the `formats` argument on your decorator like so:

```{click:example}
---
emphasize-lines: 8
---
from click import command, option, echo

from click_extra import config_option
from click_extra.config import Formats

@command(context_settings={"show_default": True})
@option("--int-param", type=int, default=10)
@config_option(formats=Formats.JSON)
def cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

Notice how the default search pattern gets limited to files with a `.json` extension:

```{click:run}
---
emphasize-lines: 8
---
result = invoke(cli, args=["--help"])
assert "*.json]" in result.stdout
```

This also works with a subset of formats:

```{click:example}
---
emphasize-lines: 8
---
from click import command, option, echo

from click_extra import config_option
from click_extra.config import Formats

@command(context_settings={"show_default": True})
@option("--int-param", type=int, default=10)
@config_option(formats=[Formats.INI, Formats.YAML])
def cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

```{click:run}
---
emphasize-lines: 8
---
result = invoke(cli, args=["--help"])
assert "*.{ini,yaml,yml}]" in result.stdout
```

### Remote URL

Remote URL can be passed directly to the `--config` option:

```{code-block} shell-session
---
emphasize-lines: 1
---
$ my-cli --config "https://example.com/dummy/configuration.yaml" subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```

## `click_extra.config` API

```{eval-rst}
.. autoclasstree:: click_extra.config
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.config
   :members:
   :undoc-members:
   :show-inheritance:
```
