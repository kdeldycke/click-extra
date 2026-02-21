# {octicon}`sliders` Configuration files

The structure of the configuration file is automatically [derived from the
parameters](parameters.md#parameter-structure) of the CLI and their types. There is no need to manually produce a configuration
data structure to mirror the CLI.

## Standalone option

The `@config_option` decorator provided by Click Extra can be used as-is with vanilla Click:

```{click:source}
---
emphasize-lines: 2,7
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

See in the result above, there is an explicit mention of the default location of the configuration file (`[default: ~/.config/my-cli/*.toml|*.yaml|*.yml|*.json|*.json5|*.jsonc|*.hjson|*.ini|*.xml]`). This improves discoverability, and [makes sysadmins happy](https://utcc.utoronto.ca/~cks/space/blog/sysadmin/ReportConfigFileLocations), especially those not familiar with your CLI.

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

The [`excluded_params`](#click_extra.config.ConfigOption.excluded_params) argument allows you to block some of your CLI options to be loaded from configuration. By setting this argument, you will prevent your CLI users to set these parameters in their configuration file.

It [defaults to the value of `DEFAULT_EXCLUDED_PARAMS`](#click_extra.config.DEFAULT_EXCLUDED_PARAMS).

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

```{hint}
You need to provide the fully-qualified ID of the option you're looking to block. I.e. the dot-separated ID that is prefixed by the CLI name. That way you can specify an option to ignore at any level, including subcommands.

If you have difficulties identifying your options and their IDs, run your CLI with the [`--show-params` option](#show-params-option) for introspection.
```

## Disabling autodiscovery

By default, `@config_option` automatically searches for configuration files in the [default application folder](#default-folder). If you want to disable this autodiscovery and only load a configuration file when the user explicitly passes `--config <path>`, use the `NO_CONFIG` sentinel as the default:

```{code-block} python
---
emphasize-lines: 2,7
---
from click import group, option, echo
from click_extra import config_option, NO_CONFIG

@group(context_settings={"show_default": True})
@option("--dummy-flag/--no-flag")
@config_option(default=NO_CONFIG)
def my_cli(dummy_flag):
    echo(f"dummy_flag is {dummy_flag!r}")
```

With this setup:

- The `--help` output shows `[default: disabled]` instead of a filesystem path.
- Running the CLI without `--config` produces no configuration-related output on stderr.
- Users can still explicitly pass `--config <path>` to load a specific configuration file.
- The `--no-config` flag (if added via `@no_config_option`) still prints the "Skip configuration file loading altogether." message when used explicitly.

This is useful for CLIs where configuration files are opt-in rather than opt-out, or when you want to avoid side effects from automatically discovered configuration files during development or testing.

## Formats

Several dialects are supported:

| Format            | Extensions        | Description                                                                               | Enabled by default |
| :---------------- | :---------------- | :---------------------------------------------------------------------------------------- | :----------------- |
| [`TOML`](#toml)   | `*.toml`          | -                                                                                         | ✅                 |
| [`YAML`](#yaml)   | `*.yaml`, `*.yml` | -                                                                                         | ❌                 |
| [`JSON`](#json)   | `*.json`          | -                                                                                         | ✅                 |
| [`JSON5`](#json5) | `*.json5`         | A [superset of JSON made for configuration file](https://json5.org)                       | ❌                 |
| [`JSONC`](#jsonc) | `*.jsonc`         | Like JSON, but with comments and trailing commas                                          | ❌                 |
| [`HJSON`](#hjson) | `*.hjson`         | Another flavor of a [user-friendly JSON](https://hjson.github.io)                         | ❌                 |
| [`INI`](#ini)     | `*.ini`           | With extended interpolation, multi-level sections and non-native types (`list`, `set`, …) | ✅                 |
| [`XML`](#xml)     | `*.xml`           | -                                                                                         | ❌                 |

Formats depending on third-party packages are not enabled by default. You need to [install Click Extra with the corresponding extra dependency group](install.md#configuration-file-formats) to enable them.

### TOML

See the [example in the top of this page](#standalone-option).

### YAML

```{important}
YAML support requires additional packages. You need to [install `click-extra[yaml]`](install.md#configuration-file-formats) extra dependency group to enable it.
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
JSON5 support requires additional packages. You need to [install `click-extra[json5]`](install.md#configuration-file-formats) extra dependency group to enable it.
```

```{todo}
Write example.
```

### JSONC

```{important}
JSONC support requires additional packages. You need to [install `click-extra[jsonc]`](install.md#configuration-file-formats) extra dependency group to enable it.
```

```{todo}
Write example.
```

### HJSON

```{important}
HJSON support requires additional packages. You need to [install `click-extra[hjson]`](install.md#configuration-file-formats) extra dependency group to enable it.
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
XML support requires additional packages. You need to [install `click-extra[xml]`](install.md#configuration-file-formats) extra dependency group to enable it.
```

```{todo}
Write example.
```

## Search pattern

The configuration file is searched with a wildcard-based glob pattern.

There is multiple stages to locate and parse the configuration file:

1. Locate all files matching the search pattern
2. Match each file against the supported formats, in order, until one is successfully parsed
3. Use the first successfully parsed file as the configuration source

By default, the pattern is `<app_dir>/*.toml|*.json|*.ini`, where:

- `<app_dir>` is the [default application folder](#default-folder)
- `*.toml|*.json|*.ini` are the [extensions of formats](#formats) enabled by default

```{hint}
Depending on the formats you enabled in your installation of Click Extra, the default extensions may vary. For example, if you installed Click Extra with all extra dependencies, the default extensions would extended to `*.toml|*.yaml|*.yml|*.json|*.json5|*.jsonc|*.hjson|*.ini|*.xml`.
```

```{tip}
The search process can be hard to follow. To help you see clearly, you can enable debug logging for the `click_extra` logger to see which files are located, matched, parsed, skipped, and finally used.

Or better, just pass the [`--verbosity DEBUG` option](logging.md#colored-verbosity) to your CLI if it is powered by Click Extra.
```

### Default folder

The configuration file is searched in the default application path, as defined by [`click.get_app_dir()`](https://click.palletsprojects.com/en/stable/api/#click.get_app_dir).

To mirror the latter, the `@config_option` decorator accept a `roaming` and `force_posix` argument to alter the default path:

| Platform          | `roaming` | `force_posix` | Folder                                    |
| :---------------- | :-------- | :------------ | :---------------------------------------- |
| macOS (default)   | -         | `False`       | `~/Library/Application Support/Foo Bar`   |
| macOS             | -         | `True`        | `~/.foo-bar`                              |
| Unix (default)    | -         | `False`       | `~/.config/foo-bar`                       |
| Unix              | -         | `True`        | `~/.foo-bar`                              |
| Windows (default) | `True`    | -             | `C:\Users\<user>\AppData\Roaming\Foo Bar` |
| Windows           | `False`   | -             | `C:\Users\<user>\AppData\Local\Foo Bar`   |

Let's change the default in the following example:

```{click:source}
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
emphasize-lines: 6
---
result = invoke(cli, args=["--help"])
assert "~/.cli/*.toml|*.yaml|*.yml|*.json|*.json5|*.jsonc|*.hjson|*.ini|*.xml]" in result.stdout.replace("\n                        ", "")
```

```{seealso}
The default application folder concept has a long and complicated history in the Unix world.

The oldest reference I can track is from the [*Where Configurations Live*](http://www.catb.org/~esr/writings/taoup/html/ch10s02.html) chapter from [*The Art of Unix Programming*](https://a.co/d/aC36Ft0).

The [*XDG base directory specification*](https://specifications.freedesktop.org/basedir/latest/) is the latest iteration of this tradition on Linux. This long-due guidelines brings [lots of benefits](https://xdgbasedirectoryspecification.com) to the platform. This is what Click Extra is [implementing by default](#default-folder).

But there is still a lot of cases for which the XDG doesn't cut it, like on other platforms (macOS, Windows, …) or for legacy applications. That's why Click Extra allows you to customize the way configuration is searched and located.
```

### Custom pattern

You can directly provide a customized search pattern to the `default` argument of the decorator:

```{click:source}
---
emphasize-lines: 6
---
from click import command

from click_extra import config_option

@command(context_settings={"show_default": True})
@config_option(default="~/my_special_folder/*.toml|*.conf")
def cli():
    pass
```

```{click:run}
---
emphasize-lines: 7
---
result = invoke(cli, args=["--help"])
assert "~/my_special_folder/*.toml|*.conf]" in result.stdout
```

The rules for the pattern are described in the next section.

### Search pattern specifications

Patterns provided to `@config_option`'s `default` argument:

- Are [based on `wcmatch.glob` syntax](https://facelessuser.github.io/wcmatch/glob/#syntax).
- Should be written with Unix separators (`/`), even for Windows: the [pattern will be normalized to the local platform dialect](https://facelessuser.github.io/wcmatch/glob/#windows-separators).
- Can be absolute or relative paths.
- Have their default case-sensitivity aligned with the local platform:
  - Windows is insensitive to case,
  - Unix and macOS are case-sensitive.
- Are setup with the following default flags:
  | Flag                                                                  | Description                                                  |
  | :-------------------------------------------------------------------- | :----------------------------------------------------------- |
  | [`GLOBSTAR`](https://facelessuser.github.io/wcmatch/glob/#globstar)   | Recursive directory search via `**` glob notation.           |
  | [`FOLLOW`](https://facelessuser.github.io/wcmatch/glob/#follow)       | Traverse symlink directories.                                |
  | [`DOTGLOB`](https://facelessuser.github.io/wcmatch/glob/#dotglob)     | Include file or directory starting with a literal dot (`.`). |
  | [`SPLIT`](https://facelessuser.github.io/wcmatch/glob/#split)         | Allow multiple patterns separated by \`                      |
  | [`GLOBTILDE`](https://facelessuser.github.io/wcmatch/glob/#globtilde) | Allow user's home path `~` to be expanded.                   |
  | [`NODIR`](https://facelessuser.github.io/wcmatch/glob/#nodir)         | Restricts results to files.                                  |

```{important}
The `NODIR` flag is always forced, to optimize the search for files only.
```

The flags above can be changed via the [`search_pattern_flags` argument of the decorator](config.md#click_extra.config.ConfigOption). So to make the matching case-insensitive, add the `IGNORECASE` flag:

```{code-block} python
---
emphasize-lines: 8,13
---
from wcmatch.glob import (
    GLOBSTAR,
    FOLLOW,
    DOTGLOB,
    SPLIT,
    GLOBTILDE,
    NODIR,
    IGNORECASE
)

@config_option(
    file_pattern_flags=(
        GLOBSTAR | FOLLOW | DOTGLOB | SPLIT | GLOBTILDE | NODIR | IGNORECASE
    )
)
```

But because of the way flags works, you have to re-specify all flags you want to keep, including the default ones.

```{seealso}
This is the same pinciple as [file pattern flags](#file-pattern-flags).
```

### Multi-format matching

The default behavior consist in searching for all files matching the default `*.toml|*.json|*.ini` pattern. Or more, depending on the [extra dependencies](install.md#configuration-file-formats) installed with Click Extra.

As soon as files are located, they are matched against each supported format, in order, until one is successfully parsed.

The first successfully parsed file is used to feed the CLI's default values.

The search will only consider matches that:

- exists,
- are a file,
- are not empty,
- matches file format patterns,
- can be parsed successfully, and
- produce a non-empty data structure.

All others are skipped. And the search continues with the next matching file.

To influence which formats are supported, see the next section.

### Format selection

If you want to limit the formats supported by your CLI, you can use the `file_format_patterns` argument to specify which formats are allowed:

```{click:source}
---
emphasize-lines: 7
---
from click import command, option, echo

from click_extra import config_option, ConfigFormat

@command(context_settings={"show_default": True})
@option("--int-param", type=int, default=10)
@config_option(file_format_patterns=[ConfigFormat.JSON, ConfigFormat.TOML])
def cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

Notice how the default search pattern has been restricted to only `*.json` and `*.toml` files, and also that the order is reflected in the help:

```{click:run}
---
emphasize-lines: 8
---
result = invoke(cli, args=["--help"])
assert "*.json|*.toml]" in result.stdout
```

You can also specify a single format:

```{click:source}
---
emphasize-lines: 7
---
from click import command, option, echo

from click_extra import config_option, ConfigFormat

@command(context_settings={"show_default": True})
@option("--int-param", type=int, default=10)
@config_option(file_format_patterns=ConfigFormat.XML)
def cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

```{click:run}
---
emphasize-lines: 8
---
result = invoke(cli, args=["--help"])
assert "*.xml]" in result.stdout
```

### Custom file format patterns

Each format is associated with [default file patterns](#formats). But you can also change these with the same `file_format_patterns` argument:

```{click:source}
---
emphasize-lines: 8-11
---
from click import command, option, echo

from click_extra import config_option, ConfigFormat

@command(context_settings={"show_default": True})
@option("--int-param", type=int, default=10)
@config_option(
    file_format_patterns={
        ConfigFormat.TOML: ["*.toml", "my_app.conf"],
        ConfigFormat.JSON: ["settings*.js", "*.json"],
    }
)
def cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

Again, this is reflected in the help:

```{click:run}
---
emphasize-lines: 9
---
result = invoke(cli, args=["--help"])
assert "*.toml|my_app.conf|settings*.js|*.json]" in result.stdout
```

### Parsing priority

The syntax of `file_format_patterns` argument allows you to specify either a list of formats, a single format, or a mapping of formats to patterns. And we can even have multiple formats share the same pattern:

```{click:source}
---
emphasize-lines: 8-12
---
from click import command, option, echo

from click_extra import config_option, ConfigFormat

@command(context_settings={"show_default": True})
@option("--int-param", type=int, default=10)
@config_option(
    file_format_patterns={
        ConfigFormat.TOML: "*.toml",
        ConfigFormat.JSON5: "config*.js",
        ConfigFormat.JSON: ["config*.js", "*.js"],
    }
)
def cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

Notice how all formats are merged into the same pattern:

```{click:run}
---
emphasize-lines: 8
---
result = invoke(cli, args=["--help"])
assert "*.toml|config*.js|*.js" in result.stdout
```

What will happen in this case is that the search will try to parse matching files first as `JSON5`, then as `JSON`. The first format that successfully parses the file will be used.

So a file named `config123.js` containing valid `JSON5` syntax will be parsed as such, even if it also contains valid `JSON` syntax and match the `*.js` pattern. But if for any reason the `JSON5` parsing fails, the search will try to parse it as `JSON` next, which is the second-best match.

On the other hand, a file named `settings.js` will only be tried as `JSON`, since it doesn't match the `JSON5` pattern.

This illustrates the flexibility of this approach, but how the order of formats matter.

### File pattern flags

The `file_pattern_flags` argument controls the matching behavior of file patterns.

These flags are defined in [`wcmatch.fnmatch`](https://facelessuser.github.io/wcmatch/fnmatch/#flags) and default to:

| Flag                                                               | Description                                        |
| :----------------------------------------------------------------- | :------------------------------------------------- |
| [`NEGATE`](https://facelessuser.github.io/wcmatch/fnmatch/#negate) | Adds support of `!` negation to define exclusions. |
| [`SPLIT`](https://facelessuser.github.io/wcmatch/fnmatch/#split)   | Allow multiple patterns separated by \`            |

```{important}
The `SPLIT` flag is always forced, as our multi-pattern design relies on it.
```

If for example, you want to make the matching case-insensitive, you do that by adding the `IGNORECASE` flag:

```python
from wcmatch.fnmatch import NEGATE, SPLIT, IGNORECASE

@config_option(file_pattern_flags=NEGATE | SPLIT | IGNORECASE)
```

But because of the way flags works, you have to re-specify all flags you want to keep, including the default ones.

```{seealso}
This is the same pinciple as [search pattern specifications](#search-pattern-specifications).
```

### Excluding files

[Negation is active by default](#file-pattern-flags), which is useful when you want to exclude some files from being considered during the search.

To ignore, for example, all your template files residing alongside real configuration files. Then, to exclude all files starting with `template_` in their name, you can do:

```{code-block} python
---
emphasize-lines: 3
---
@config_option(
    file_format_patterns={
        ConfigFormat.TOML: ["*.toml", "!template_*.toml"],
    }
)
```

### Extension-less files

This demonstrate the popular case on Unix-like systems, where the configuration file is an extension-less dotfile in the home directory.

Here is how to set up `@config_option` for a pre-defined `.commandrc` file in YAML:

```{click:source}
---
emphasize-lines: 7-8
---
from click import command

from click_extra import config_option, ConfigFormat

@command(context_settings={"show_default": True})
@config_option(
    default="~/*",
    file_format_patterns={ConfigFormat.YAML: ".commandrc"}
)
def cli():
    pass
```

```{click:run}
---
emphasize-lines: 6
---
result = invoke(cli, args=["--help"])
assert "[default: ~/*]" in result.stdout
```

```{caution}
Depending on how you set up your patterns, files starting with a dot (`.`) may not be matched by default. Make sure to include the [`DOTMATCH`](https://facelessuser.github.io/wcmatch/fnmatch/#dotmatch) flag in `file_pattern_flags` if needed.
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

```{warning}
URLs do not support multi-format matching. You need to provide a direct link to the configuration file, including its extension.

Glob patterns are also not supported for URLs. Unless you want to let your users download the whole internet…
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
