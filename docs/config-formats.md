# {octicon}`stack` Configuration formats

Click Extra reads a configuration file in any of the dialects below. Each one lists the extensions it matches, what it brings, and whether it is available without an extra dependency.

| Format                              | Extensions              | Description                                                                               | Enabled by default |
| :---------------------------------- | :---------------------- | :---------------------------------------------------------------------------------------- | :----------------- |
| [`TOML`](#toml)                     | `*.toml`                | -                                                                                         | ✅                 |
| [`YAML`](#yaml)                     | `*.yaml`, `*.yml`       | -                                                                                         | ❌                 |
| [`JSON`](#json)                     | `*.json`                | -                                                                                         | ✅                 |
| [`JSON5`](#json5)                   | `*.json5`               | A [superset of JSON made for configuration file](https://json5.org)                       | ❌                 |
| [`JSONC`](#jsonc)                   | `*.jsonc`               | Like JSON, but with comments and trailing commas                                          | ❌                 |
| [`HJSON`](#hjson)                   | `*.hjson`               | Another flavor of a [user-friendly JSON](https://hjson.github.io)                         | ❌                 |
| [`INI`](#ini)                       | `*.ini`                 | With extended interpolation, multi-level sections and non-native types (`list`, `set`, …) | ✅                 |
| [`XML`](#xml)                       | `*.xml`                 | -                                                                                         | ❌                 |
| [`plist`](#plist)                   | `*.plist`               | Apple's property list, in its XML or binary variant                                       | ✅                 |
| [`SQLITE`](#sqlite)                 | `*.sqlite`, `*.sqlite3` | Reads a `config` table of dotted keys and JSON-encoded values                             | ✅                 |
| [`ARGFILE`](#argfile)               | `*.conf`                | Plain-text list of command-line options, in the style of `mpv` and `yt-dlp`               | ✅                 |
| [`PYPROJECT_TOML`](#pyproject-toml) | `pyproject.toml`        | Reads `[tool.*]`{l=toml}{l=toml} sections from `pyproject.toml`                           | ✅                 |

Formats depending on third-party packages are not enabled by default. You need to [install Click Extra with the corresponding extra dependency group](install.md#extra-dependencies) to enable them.

Every supported format expresses the same configuration. Here is the `my-cli` section from the [standalone option example](config.md#standalone-option), written in each one: they all set the same defaults and produce the same result. The one exception is [`ARGFILE`](#argfile), which cannot reach a subcommand's options and is shown on its own below.

`````{tab-set}

````{tab-item} TOML
```{code-block} toml
[my-cli]
extra_value = "is ignored too"
dummy_flag = true
my_list = ["item 1", "item #2", "Very Last Item!"]

[my-cli.subcommand]
int_param = 3
random_stuff = "will be ignored"
```
````

````{tab-item} YAML
```{code-block} yaml
my-cli:
  extra_value: is ignored too
  dummy_flag: true
  my_list:
    - item 1
    - "item #2"
    - Very Last Item!
  subcommand:
    int_param: 3
    random_stuff: will be ignored
```
````

````{tab-item} JSON
```{code-block} json
{
  "my-cli": {
    "extra_value": "is ignored too",
    "dummy_flag": true,
    "my_list": ["item 1", "item #2", "Very Last Item!"],
    "subcommand": {
      "int_param": 3,
      "random_stuff": "will be ignored"
    }
  }
}
```
````

````{tab-item} JSON5
```{code-block} json5
{
  // Unquoted keys, comments, trailing commas, single quotes.
  'my-cli': {
    extra_value: 'is ignored too',
    dummy_flag: true,
    my_list: ['item 1', 'item #2', 'Very Last Item!'],
    subcommand: {
      int_param: 3,
      random_stuff: 'will be ignored',
    },
  },
}
```
````

````{tab-item} JSONC
```{code-block} json5
{
  // JSON, plus comments and trailing commas.
  "my-cli": {
    "extra_value": "is ignored too",
    "dummy_flag": true,
    "my_list": ["item 1", "item #2", "Very Last Item!"],
    "subcommand": {
      "int_param": 3,
      "random_stuff": "will be ignored",
    },
  },
}
```
````

````{tab-item} HJSON
```{code-block} text
{
  # No quotes, no commas.
  my-cli:
  {
    extra_value: is ignored too
    dummy_flag: true
    my_list:
    [
      item 1
      item #2
      Very Last Item!
    ]
    subcommand:
    {
      int_param: 3
      random_stuff: will be ignored
    }
  }
}
```
````

````{tab-item} INI
```{code-block} ini
[my-cli]
extra_value = is ignored too
dummy_flag = true
my_list = ["item 1", "item #2", "Very Last Item!"]

[my-cli.subcommand]
int_param = 3
random_stuff = will be ignored
```
````

````{tab-item} XML
```{code-block} xml
<?xml version="1.0"?>
<my-cli>
  <extra_value>is ignored too</extra_value>
  <dummy_flag>true</dummy_flag>
  <my_list>item 1</my_list>
  <my_list>item #2</my_list>
  <my_list>Very Last Item!</my_list>
  <subcommand>
    <int_param>3</int_param>
    <random_stuff>will be ignored</random_stuff>
  </subcommand>
</my-cli>
```
````

````{tab-item} plist
```{code-block} xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>my-cli</key>
  <dict>
    <key>extra_value</key>
    <string>is ignored too</string>
    <key>dummy_flag</key>
    <true/>
    <key>my_list</key>
    <array>
      <string>item 1</string>
      <string>item #2</string>
      <string>Very Last Item!</string>
    </array>
    <key>subcommand</key>
    <dict>
      <key>int_param</key>
      <integer>3</integer>
      <key>random_stuff</key>
      <string>will be ignored</string>
    </dict>
  </dict>
</dict>
</plist>
```
````

````{tab-item} SQLite
```{code-block} sql
CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT);

INSERT INTO config VALUES
  ('my-cli.extra_value', '"is ignored too"'),
  ('my-cli.dummy_flag', 'true'),
  ('my-cli.my_list', '["item 1", "item #2", "Very Last Item!"]'),
  ('my-cli.subcommand.int_param', '3'),
  ('my-cli.subcommand.random_stuff', '"will be ignored"');
```
````
`````

## TOML

`TOML` is enabled by default, and is the reference format used in the examples throughout this page.

## YAML

```{important}
`YAML` support requires the `yaml` extra: [install `click-extra[yaml]`](install.md#extra-dependencies).
```

## JSON

`JSON` is enabled by default.

## JSON5

```{important}
`JSON5` support requires the `json5` extra: [install `click-extra[json5]`](install.md#extra-dependencies).
```

## JSONC

```{important}
`JSONC` support requires the `jsonc` extra: [install `click-extra[jsonc]`](install.md#extra-dependencies).
```

## HJSON

```{important}
`HJSON` support requires the `hjson` extra: [install `click-extra[hjson]`](install.md#extra-dependencies).
```

## INI

`INI` files use sections, and a dot (`.`) in a section name marks a sub-level: `[my-cli.subcommand]` nests under `my-cli`. [`ExtendedInterpolation`](https://docs.python.org/3/library/configparser.html#configparser.ExtendedInterpolation) is enabled by default. Each value is typed after its matching CLI parameter; types `INI` has no native syntax for (lists, sets, …) are read as JSON-serialized strings, like `my_list` above.

## XML

```{important}
`XML` support requires the `xml` extra: [install `click-extra[xml]`](install.md#extra-dependencies).
```

The root element is the CLI's name. A repeated element (like `my_list` above) is collected into a list, and every value is read as a string, then coerced to its matching parameter's type.

## plist

`plist` is enabled by default, and read through Python's built-in [`plistlib`](https://docs.python.org/3/library/plistlib.html) module, so no extra dependency is needed. Both the XML and the binary variants of the format are supported, but a `plist` fetched over `http://` or `https://` is only parsed in its XML variant, as remote content is downloaded as text. The root of the property list is a dictionary, with the same top-level sections as every other format.

[`--export-config`](config.md#exporting-the-configuration) writes the XML variant, and drops parameters without a value from the export, as `plist` has no null type.

## SQLite

`SQLITE` is enabled by default, and read through Python's built-in [`sqlite3`](https://docs.python.org/3/library/sqlite3.html) module, so no extra dependency is needed. The database holds a single `config` table of `key`/`value` rows: keys are parameter paths, with a dot (`.`) separating each level, and values are JSON-encoded, which carries every type the other formats do. Other tables in the database are ignored, so a configuration table can live alongside an application's own data.

`SQLITE` is read-only: it cannot be produced by [`--export-config`](config.md#exporting-the-configuration), and a database fetched over `http://` or `https://` is skipped.

## Argfile

`ARGFILE` is enabled by default, and needs no extra dependency. The file is a plain-text list of command-line options, one per line, in the style of [`mpv`](https://mpv.io/manual/stable/#configuration-files) and [`yt-dlp`](https://github.com/yt-dlp/yt-dlp#configuration) configuration files. Each line is written exactly as it would be typed on the command line, and comments start with a hash sign (`#`):

```{code-block} text
:caption: `~/.config/my-cli/my-cli.conf`
# Print more details.
--verbose

# Repeat the operation three times, in French.
--count 3
--language fr

# A list is fed one item per occurrence.
--my-list pip
--my-list npm
```

Both the `--option value` and `--option=value` spellings are supported, and shell quoting rules apply, so a value containing spaces or a `#` is wrapped in quotes. A boolean flag takes no value: `--flag` sets it, and its `--no-flag` counterpart unsets it.

```{note}
An argfile can only address the options of the CLI's top-level command: the format has no section syntax with which to reach a subcommand's own options, and positional arguments are skipped.
```

`ARGFILE` is read-only: it cannot be produced by [`--export-config`](config.md#exporting-the-configuration).

<a name="pyproject-toml"></a>

## `pyproject.toml`

The `PYPROJECT_TOML` format reads `[tool.<cli-name>]`{l=toml} sections from a `pyproject.toml` file, following [PEP 518](https://peps.python.org/pep-0518/). This stores the CLI's configuration alongside project metadata. Non-Python tools like [ruff](https://docs.astral.sh/ruff/configuration/#configuring-ruff) and [typos](https://github.com/crate-ci/typos/blob/master/docs/reference.md) use the same convention.

```{tip}
`pyproject.toml` is becoming the standard place to centralize tool configuration for Python projects. Instead of scattering dedicated config files at the root of your repository (`ruff.toml`, `typos.toml`, `mypy.ini`, …), you can consolidate them all under `[tool.*]`{l=toml} sections in a single `pyproject.toml`. This keeps the repository root clean, makes it easy to review and coordinate tool configurations in one place, and reduces the number of files contributors need to discover.
```

`PYPROJECT_TOML` is included in the default format patterns, so it is automatically discovered alongside other formats. The `[tool]` wrapper is automatically unwrapped: `merge_default_map` sees `{"cli": {"int_param": 3}}`, exactly the [same structure as a regular TOML config file](#toml).

```{seealso}
For a production example of a CLI built on Click Extra's `pyproject.toml` configuration with a [typed dataclass schema](config-schema.md), nested sub-tables, and 48 config options, see [repomatic's configuration reference](https://kdeldycke.github.io/repomatic/configuration.html). Repomatic also uses Click Extra's config system to [bridge `[tool.X]` sections](https://kdeldycke.github.io/repomatic/tool-runner.html#config-resolution) for third-party tools that don't read `pyproject.toml` natively.
```

### CWD-first discovery

When auto-discovering configuration (no explicit `--config` flag), Click Extra searches for `pyproject.toml` starting from the current working directory and walking up to the VCS root *before* checking the standard app config directory. This matches the discovery behavior of uv, ruff, and mypy, so users get the configuration they expect without passing `--config` explicitly.

The CWD search only applies to `pyproject.toml`: other config formats (TOML, YAML, JSON, etc.) are still discovered from the app config directory. If a `pyproject.toml` is found via CWD search, the app-dir search is skipped entirely. If `--config` is passed explicitly, CWD search is bypassed.

Given a `pyproject.toml` in the search path:

```{code-block} toml
:caption: `pyproject.toml`
:emphasize-lines: 4-5
[build-system]
requires = ["setuptools"]

[tool.cli]
int_param = 3
```

This is especially powerful combined with `search_parents` to walk up from a project directory:

```{code-block} python
:emphasize-lines: 7
from click import command, option, echo

from click_extra import config_option

@command
@option("--int-param", type=int, default=10)
@config_option(search_parents=True)
def cli(int_param):
    echo(f"int_parameter is {int_param!r}")
```

Running `cli` from anywhere inside the project tree will find `pyproject.toml` at the repository root and apply `[tool.cli]`{l=toml} values. The walk [automatically stops at the VCS root](config-discovery.md#walk-boundaries).

### Dedicated file wins, no merging

When both a dedicated configuration file (like `my-cli.toml`) and a `pyproject.toml` with a `[tool.my-cli]`{l=toml} section exist, Click Extra uses the **first parseable file** it finds and ignores all others. There is no merging across files, unless [`cascade=True`](config-discovery.md#cascading-configuration-files) opts into layering every discovered file.

This is the de facto standard across the ecosystem. Every major tool that supports both a dedicated config file and `pyproject.toml` follows the same strict precedence (dedicated file wins, `pyproject.toml` is ignored entirely):

| Tool                                                                              | Precedence rule                                                                |
| :-------------------------------------------------------------------------------- | :----------------------------------------------------------------------------- |
| [ruff](https://docs.astral.sh/ruff/configuration/#config-file-discovery)          | `.ruff.toml` > `ruff.toml` > `pyproject.toml`                                  |
| [uv](https://docs.astral.sh/uv/concepts/configuration-files/#configuration-files) | `uv.toml` > `pyproject.toml`                                                   |
| [typos](https://github.com/crate-ci/typos/blob/master/docs/reference.md)          | `typos.toml` / `_typos.toml` / `.typos.toml` > `Cargo.toml` > `pyproject.toml` |

The rationale:

- **No merging surprises.** Merging two config sources creates ambiguity: which key wins when both files define it? Are arrays concatenated or replaced? Every tool above chose "first match wins, full stop" to avoid this class of problems entirely.
- **Explicit intent.** A dedicated file at the repository root, named after the tool, is the most visible and explicit signal. If someone creates one alongside a `[tool.*]`{l=toml} section, the dedicated file represents a deliberate override.
- **Clean migration path.** Users moving from a dedicated file to `pyproject.toml` simply delete the dedicated file. Users who need the dedicated file (for example, sharing it across non-Python repos) keep it and `pyproject.toml` is silently ignored.

```{seealso}
Other non-Python tools that support `[tool.*]`{l=toml} in `pyproject.toml`:
[basedpyright](https://docs.basedpyright.com/latest/configuration/config-files/),
[lychee](https://lychee.cli.rs/guides/config/),
[maturin](https://www.maturin.rs/config),
[pixi](https://pixi.prefix.dev/latest/python/pyproject_toml/),
[Pyrefly](https://pyrefly.org/en/docs/configuration/),
[Pyright](https://github.com/microsoft/pyright/blob/main/docs/configuration.md),
[rumdl](https://github.com/rvben/rumdl),
[Tombi](https://tombi-toml.github.io/tombi/docs/configuration/),
[ty](https://docs.astral.sh/ty/),
[typos](https://github.com/crate-ci/typos/blob/master/docs/reference.md),
[uv](https://docs.astral.sh/uv/concepts/configuration-files/),
and [Zuban](https://docs.zubanls.com/en/latest/usage.html).

Click Extra's own `[tool.*]`{l=toml} bridge in [repomatic's tool runner](https://kdeldycke.github.io/repomatic/tool-runner.html#level-2-tool-x-in-pyproject-toml) translates `[tool.yamllint]`{l=toml}, `[tool.actionlint]`{l=toml}, `[tool.biome]`{l=toml}, and others into native config files at invocation time, giving tools that lack native `pyproject.toml` support the same single-file experience.

Other tools are following suit:
[actionlint#623](https://github.com/rhysd/actionlint/issues/623),
[biome#9239](https://github.com/biomejs/biome/discussions/9239),
[gitleaks#2066](https://github.com/gitleaks/gitleaks/issues/2066),
[Nuitka#3909](https://github.com/Nuitka/Nuitka/issues/3909),
[taplo#603](https://github.com/tamasfe/taplo/issues/603),
[zizmor#322](https://github.com/orgs/zizmorcore/discussions/322#discussioncomment-15919620).
[sh#1268](https://github.com/mvdan/sh/issues/1268) was declined.
```

## `click_extra.config.formats` API

```{eval-rst}
.. autoclasstree:: click_extra.config.formats
   :strict:

.. automodule:: click_extra.config.formats
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
