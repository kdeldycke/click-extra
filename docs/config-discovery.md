# {octicon}`search` Configuration discovery

The configuration file is searched with a wildcard-based glob pattern.

Locating and parsing it happens in three stages:

1. Locate all files matching the search pattern.
2. Match each file against the supported formats, in order, until one parses.
3. Use the first successfully parsed file, or layer every one of them with [`cascade=True`](#cascading-configuration-files).

By default, the pattern is `<app_dir>/{*.toml,*.json,*.ini}`, where:

- `<app_dir>` is the [default application folder](#default-folder)
- `{*.toml,*.json,*.ini}` are the [extensions of formats](config-formats.md) enabled by default, wrapped in brace-expansion syntax

```{hint}
Depending on the formats you enabled in your installation of Click Extra, the default extensions may vary. For example, if you installed Click Extra with all extra dependencies, the default extensions would be extended to `{*.toml,*.yaml,*.yml,*.json,*.json5,*.jsonc,*.hjson,*.ini,*.xml,*.plist,*.sqlite,*.sqlite3,*.conf,pyproject.toml}`.
```

```{tip}
If the search process is hard to follow, enable debug logging for the `click_extra` logger to see which files are located, matched, parsed, skipped, and finally used. A Click Extra CLI takes the [`--verbosity DEBUG` option](logging.md#colored-verbosity) directly.
```

## Default folder

The configuration file is searched in the default application path, as defined by [`click.get_app_dir()`](https://click.palletsprojects.com/en/stable/api/#click.get_app_dir).

To mirror it, the `@config_option` decorator accepts a `roaming` and a `force_posix` argument that alter the default path:

| Platform          | `roaming` | `force_posix` | Folder                                    |
| :---------------- | :-------- | :------------ | :---------------------------------------- |
| macOS (default)   | -         | `False`       | `~/Library/Application Support/Foo Bar`   |
| macOS             | -         | `True`        | `~/.foo-bar`                              |
| Unix (default)    | -         | `False`       | `~/.config/foo-bar`                       |
| Unix              | -         | `True`        | `~/.foo-bar`                              |
| Windows (default) | `True`    | -             | `C:\Users\<user>\AppData\Roaming\Foo Bar` |
| Windows           | `False`   | -             | `C:\Users\<user>\AppData\Local\Foo Bar`   |

Change the default in the following example:

```{click:source}
:emphasize-lines: 6
from click import command

from click_extra import config_option

@command(context_settings={"show_default": True})
@config_option(force_posix=True)
def cli():
    pass
```

The `--config` default is now `~/.cli/`:

```{click:run}
:emphasize-result-lines: 6
import re
from boltons.iterutils import flatten, unique
from click_extra import ConfigFormat
result = invoke(cli, args=["--help"])
fp = ",".join(unique(flatten(f.patterns for f in ConfigFormat if f.enabled)))
# Cloup wraps the default at a column driven by the widest option label, so
# drop every whitespace run before looking for the pattern.
assert f"~/.cli/{{{fp}}}]" in re.sub(r"\s+", "", result.stdout)
```

```{seealso}
The default application folder concept has a long history in the Unix world.

The oldest reference I can track is the [*Where Configurations Live*](http://www.catb.org/~esr/writings/taoup/html/ch10s02.html) chapter of [*The Art of Unix Programming*](https://a.co/d/aC36Ft0).

The [*XDG base directory specification*](https://specifications.freedesktop.org/basedir/latest/) is the latest iteration of this tradition on Linux. It brings [lots of benefits](https://xdgbasedirectoryspecification.com) to the platform, and Click Extra [implements it by default](#default-folder).

XDG does not cover other platforms (macOS, Windows, …) or legacy applications. That is why Click Extra lets you customize where configuration is searched.
```

## Custom pattern

To change the default search pattern, pass a custom value to the `default` argument of the decorator:

```{click:source}
:emphasize-lines: 6
from click import command

from click_extra import config_option

@command(context_settings={"show_default": True})
@config_option(default="~/my_special_folder/*.toml")
def cli():
    pass
```

```{click:run}
:emphasize-result-lines: 7
result = invoke(cli, args=["--help"])
assert "~/my_special_folder/*.toml]" in result.stdout
```

The next section describes the pattern rules.

## Search pattern specifications

Patterns provided to `@config_option`'s `default` argument:

- Are [based on `wcmatch.glob` syntax](https://facelessuser.github.io/wcmatch/glob/#syntax).
- Should be written with Unix separators (`/`), even for Windows: the [pattern will be normalized to the local platform dialect](https://facelessuser.github.io/wcmatch/glob/#windows-separators).
- Can be absolute or relative paths.
- Have their default case-sensitivity aligned with the local platform:
  - Windows is insensitive to case,
  - Unix and macOS are case-sensitive.
- Are set up with the following default flags:
  | Flag                                                                  | Description                                                        |
  | :-------------------------------------------------------------------- | :----------------------------------------------------------------- |
  | [`GLOBSTAR`](https://facelessuser.github.io/wcmatch/glob/#globstar)   | Recursive directory search via `**` glob notation.                 |
  | [`FOLLOW`](https://facelessuser.github.io/wcmatch/glob/#follow)       | Traverse symlink directories.                                      |
  | [`DOTGLOB`](https://facelessuser.github.io/wcmatch/glob/#dotglob)     | Include file or directory starting with a literal dot (`.`).       |
  | [`BRACE`](https://facelessuser.github.io/wcmatch/glob/#brace)         | Expand `{pat1,pat2,...}` brace expressions into multiple patterns. |
  | [`SPLIT`](https://facelessuser.github.io/wcmatch/glob/#split)         | Allow multiple patterns separated by `\|`.                         |
  | [`GLOBTILDE`](https://facelessuser.github.io/wcmatch/glob/#globtilde) | Allow user's home path `~` to be expanded.                         |
  | [`NODIR`](https://facelessuser.github.io/wcmatch/glob/#nodir)         | Restricts results to files.                                        |

```{important}
The `BRACE` flag is always forced, so that multi-format default patterns using `{pat1,pat2,...}` syntax expand correctly. The `NODIR` flag is always forced, to optimize the search for files only.
```

The flags above can be changed via the {py:class}`search_pattern_flags argument of the decorator <click_extra.config.option.ConfigOption>`. So to make the matching case-insensitive, add the `IGNORECASE` flag:

```{code-block} python
:emphasize-lines: 9,14
from wcmatch.glob import (
    GLOBSTAR,
    FOLLOW,
    DOTGLOB,
    BRACE,
    SPLIT,
    GLOBTILDE,
    NODIR,
    IGNORECASE
)

@config_option(
    search_pattern_flags=(
        GLOBSTAR | FOLLOW | DOTGLOB | BRACE | SPLIT | GLOBTILDE | NODIR | IGNORECASE
    )
)
```

Flags form a bitmask: re-specify every flag you want to keep, including the defaults.

```{seealso}
This is the same principle as [file pattern flags](#file-pattern-flags).
```

## Multi-format matching

By default, the search covers all files matching the `{*.toml,*.json,*.ini}` pattern, or more depending on the [extra dependencies](install.md#extra-dependencies) installed.

Each located file is matched against each supported format, in order, until one parses. The first successfully parsed file feeds the CLI's default values.

The search only considers matches that:

- exist,
- are a file,
- are not empty,
- match a file format pattern,
- parse successfully, and
- produce a non-empty data structure.

All others are skipped, and the search continues with the next file. The next section covers how to change which formats are supported.

## Format selection

To limit the formats your CLI supports, use the `file_format_patterns` argument:

```{click:source}
:emphasize-lines: 7
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
:emphasize-result-lines: 8
result = invoke(cli, args=["--help"])
assert "{*.json,*.toml}]" in result.stdout
```

You can also specify a single format:

```{click:source}
:emphasize-lines: 7
from click import command, option, echo

from click_extra import config_option, ConfigFormat

@command(context_settings={"show_default": True})
@option("--int-param", type=int, default=10)
@config_option(file_format_patterns=ConfigFormat.XML)
def cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

```{click:run}
:emphasize-result-lines: 8
result = invoke(cli, args=["--help"])
assert "*.xml]" in result.stdout
```

## Custom file format patterns

Each format is associated with [default file patterns](config-formats.md). But you can also change these with the same `file_format_patterns` argument:

```{click:source}
:emphasize-lines: 8-11
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
:emphasize-result-lines: 8
result = invoke(cli, args=["--help"])
assert "{*.toml,my_app.conf,settings*.js,*.json}]" in result.stdout
```

## Parsing priority

The `file_format_patterns` argument takes a list of formats, a single format, or a mapping of formats to patterns. Multiple formats can share the same pattern:

```{click:source}
:emphasize-lines: 8-12
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

All formats are merged into the same pattern:

```{click:run}
:emphasize-result-lines: 8
result = invoke(cli, args=["--help"])
assert "{*.toml,config*.js,*.js}" in result.stdout
```

The search tries to parse matching files first as `JSON5`, then as `JSON`. The first format that parses the file wins.

A file named `config123.js` containing valid `JSON5` syntax is parsed as such, even though it also matches the `*.js` pattern as valid `JSON`. If the `JSON5` parsing fails, the search tries `JSON` next.

A file named `settings.js` is only tried as `JSON`, since it does not match the `JSON5` pattern. The order of formats matters.

## File pattern flags

The `file_pattern_flags` argument controls the matching behavior of file patterns.

These flags are defined in [`wcmatch.fnmatch`](https://facelessuser.github.io/wcmatch/fnmatch/#flags) and default to:

| Flag                                                               | Description                                        |
| :----------------------------------------------------------------- | :------------------------------------------------- |
| [`NEGATE`](https://facelessuser.github.io/wcmatch/fnmatch/#negate) | Adds support of `!` negation to define exclusions. |
| [`SPLIT`](https://facelessuser.github.io/wcmatch/fnmatch/#split)   | Allow multiple patterns separated by `\|`.         |

```{important}
The `SPLIT` flag is always forced, as the multi-pattern design relies on it.
```

To make the matching case-insensitive, add the `IGNORECASE` flag:

```python
from wcmatch.fnmatch import NEGATE, SPLIT, IGNORECASE

@config_option(file_pattern_flags=NEGATE | SPLIT | IGNORECASE)
```

Flags form a bitmask: re-specify every flag you want to keep, including the defaults.

```{seealso}
This is the same principle as [search pattern specifications](#search-pattern-specifications).
```

## Excluding files

[Negation is active by default](#file-pattern-flags), which excludes files from the search. To skip every template file starting with `template_`:

```{code-block} python
:emphasize-lines: 3
@config_option(
    file_format_patterns={
        ConfigFormat.TOML: ["*.toml", "!template_*.toml"],
    }
)
```

## Extension-less files

On Unix-like systems the configuration file is often an extension-less dotfile in the home directory. Here is how to set up `@config_option` for a pre-defined `.commandrc` file in YAML:

```{click:source}
:emphasize-lines: 7-8
from click import command

from click_extra import config_option, ConfigFormat

@command(context_settings={"show_default": True})
@config_option(
    default="~/.commandrc",
    file_format_patterns={ConfigFormat.YAML: ".commandrc"}
)
def cli():
    pass
```

```{click:run}
:emphasize-result-lines: 6
result = invoke(cli, args=["--help"])
assert "[default: ~/.commandrc]" in " ".join(result.stdout.split())
```

```{caution}
Depending on how you set up your patterns, files starting with a dot (`.`) may not be matched by default. Make sure to include the [`DOTMATCH`](https://facelessuser.github.io/wcmatch/fnmatch/#dotmatch) flag in `file_pattern_flags` if needed.
```

## Parent folder search

By default, configuration files are only searched in the [default application folder](#default-folder). With `search_parents=True`, Click Extra also walks up the directory tree from the search location to the filesystem root, looking for matching files at each level:

```{click:source}
:emphasize-lines: 6
from click import command

from click_extra import config_option

@command
@config_option(search_parents=True)
def cli():
    pass
```

For a CLI named `cli` on a Unix system, this searches for configuration files in:

1. `~/.config/cli/{*.toml,*.yaml,…}` *(the default location)*
2. `~/.config/{*.toml,*.yaml,…}`
3. `~/{*.toml,*.yaml,…}`
4. `/{*.toml,*.yaml,…}`

By default, the first successfully [parsed file wins](#parsing-priority). This is useful for monorepo or project-local configuration, where a config file placed higher in the tree acts as a fallback. Set [`cascade=True`](#cascading-configuration-files) to load and merge every file found instead.

```{note}
Parent search works with both plain paths and [glob patterns](#search-pattern-specifications). For glob patterns, the non-magic directory prefix is identified and the file pattern is searched at each parent level via `root_dir`. Entirely magic patterns like `*.toml` have no directory prefix to walk up, so only the original pattern is searched.
```

### Walk boundaries

The parent directory walk stops as soon as it hits any of the following boundaries:

- **Filesystem root**: the walk always stops at `/` (or the drive root on Windows).
- **Inaccessible directory**: if a parent directory exists but is not readable, the walk stops immediately.
- **VCS root** (`stop_at=VCS`, the default): the walk stops at the nearest repository root (a directory containing `.git` or `.hg`). If no VCS root is found, the walk continues to the filesystem root.
- **Explicit path** (`stop_at="/some/path"`): the walk stops as soon as it leaves the given directory.
- **No boundary** (`stop_at=None`): the walk continues all the way to the filesystem root.

```{code-block} python
:caption: Stop at an explicit directory
:emphasize-lines: 6
from click import command

from click_extra import config_option

@command
@config_option(search_parents=True, stop_at="/home/user/projects")
def cli():
    pass
```

```{code-block} python
:caption: Walk to the filesystem root
:emphasize-lines: 6
from click import command

from click_extra import config_option

@command
@config_option(search_parents=True, stop_at=None)
def cli():
    pass
```

```{tip}
The default `stop_at=VCS` mirrors the behavior of tools like `bump-my-version` and prevents the walk from escaping the repository into unrelated parent directories.
```

### Cascading configuration files

By default, discovery stops at the first parseable file. With `cascade=True`, **every** file discovered by auto-discovery is loaded and layered into the defaults, the most local one winning on each key:

```{code-block} python
:caption: Merge user-wide and project-local configuration
:emphasize-lines: 6
from click import command

from click_extra import config_option

@command
@config_option(search_parents=True, cascade=True)
def cli():
    pass
```

Precedence, highest first:

1. The nearest `pyproject.toml` with a `[tool.<cli>]`{l=toml} section, found by the [CWD-first discovery](config-formats.md#cwd-first-discovery) walk, then its parents.
2. The files found by the app-dir search, walking up: a config in `~/.config/cli/` beats one found in a parent of that folder.

A key defined in several files resolves to the most local one; a key defined in a single file applies wherever it sits in the hierarchy. Each file is validated individually, so an error message names the file it comes from, and the `config_schema` is built from the merged result.

```{important}
An explicit `--config` value never cascades: it pins a single configuration source, whatever `cascade` is set to. Cascading only applies to auto-discovery.
```

Every loaded file is recorded in `ctx.meta[context.CONF_SOURCES]` as `(location, parsed_conf)` pairs, highest precedence first, and `ctx.meta[context.CONF_FULL]` holds the deep-merged document as it was applied. To see the layering at work, ask [`--params`](parameters.md) for the opt-in `config_file` column: it names, for every parameter sourced from a configuration file, the exact file its value resolved from:

```{code-block} shell-session
$ my-cli --params --columns id,value,source,config_file
```

## Remote URL

A remote URL can be passed directly to the `--config` option:

```{code-block} shell-session
:emphasize-lines: 1
$ my-cli --config "https://example.com/dummy/configuration.yaml" subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```

### Typing a download

A URL is free to carry no file extension at all, so the format of a download is guessed from two sources, tried in that order:

1. The `Content-Type` header the server answers with. This is the only clue an endpoint like `https://example.com/api/settings` gives, and it is what a private API's own media type (`application/vnd.acme.settings+json`) resolves through, following [RFC 6839](https://www.rfc-editor.org/rfc/rfc6839.html) structured syntax suffixes.
2. The last segment of the URL path, matched against [file format patterns](#custom-file-format-patterns) exactly as a local file name is.

Each format is served as the media types below:

| Format                               | Media types                                                          |
| :----------------------------------- | :------------------------------------------------------------------- |
| [`TOML`](config-formats.md#toml)     | `application/toml`, `text/x-toml`                                    |
| [`YAML`](config-formats.md#yaml)     | `application/yaml`, `text/yaml`, `application/x-yaml`, `text/x-yaml` |
| [`JSON`](config-formats.md#json)     | `application/json`, `text/json`                                      |
| [`JSON5`](config-formats.md#json5)   | `application/json5`                                                  |
| [`JSONC`](config-formats.md#jsonc)   | `application/jsonc`                                                  |
| [`HJSON`](config-formats.md#hjson)   | `application/hjson`                                                  |
| [`XML`](config-formats.md#xml)       | `application/xml`, `text/xml`                                        |
| [`plist`](config-formats.md#plist)   | `application/x-plist`                                                |
| [`SQLITE`](config-formats.md#sqlite) | `application/vnd.sqlite3`, `application/x-sqlite3`                   |

[`INI`](config-formats.md#ini) and [`ARGFILE`](config-formats.md#argfile) are both served as `text/plain`, which names no format, and [`PYPROJECT_TOML`](config-formats.md#pyproject-toml) is keyed on a file name no media type tells apart from plain `TOML`. All three are matched on the URL path alone.

The two sources are layered rather than exclusive, so a server advertising a generic `text/plain`, an `application/octet-stream`, or a plain wrong type costs nothing: the formats derived from the URL path are still tried behind it. A media type never widens the format set either, as it is resolved against the formats the option accepts.

```{warning}
Glob patterns are not supported for URLs.
```
