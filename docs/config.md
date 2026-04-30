# {octicon}`sliders` Configuration files

The structure of the configuration file is automatically [derived from the
parameters](parameters.md#parameter-structure) of the CLI and their types. There is no need to manually produce a configuration
data structure to mirror the CLI.

```{tip}
After loading, the resolved file path, the full parsed document, and (when a `config_schema` is set) the typed app section are exposed on `ctx.meta` as `CONF_SOURCE`, `CONF_FULL`, and `TOOL_CONFIG`. See the [available keys](context.md#available-keys) table to read them from your own callbacks.
```

## Standalone option

The `@config_option` decorator provided by Click Extra can be used as-is with vanilla Click:

```{click:source}
:emphasize-lines: 2,7
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
:emphasize-lines: 7-10
result = invoke(my_cli, args=["--help"])
assert "--config CONFIG_PATH" in result.stdout
```

See in the result above, there is an explicit mention of the default location of the configuration file (`[default: ~/.config/my-cli/{*.toml,*.yaml,*.yml,*.json,*.json5,*.jsonc,*.hjson,*.ini,*.xml,pyproject.toml}]`). This improves discoverability, and [makes sysadmins happy](https://utcc.utoronto.ca/~cks/space/blog/sysadmin/ReportConfigFileLocations), especially those not familiar with your CLI.

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

## Dotted keys

Configuration files support dotted keys as a shorthand for nested structures. Instead of writing:

```{code-block} toml
:caption: Nested structure
[my-cli.subcommand]
int_param = 3
```

You can write:

```{code-block} toml
:caption: Dotted key equivalent
[my-cli]
"subcommand.int_param" = 3
```

Both forms are equivalent. You can also freely mix them in the same file:

```{code-block} json
:caption: Mixed dotted and nested keys in JSON
{
    "my-cli": {
        "dummy_flag": true,
        "subcommand.int_param": 3,
        "subcommand": {
            "other_param": "value"
        }
    }
}
```

Dotted keys are expanded into nested dicts and deep-merged before the configuration is applied. This works across all [supported formats](#formats), and at any nesting depth (e.g. `"subcommand.nested.option"` expands to three levels).

```{hint}
This is especially handy in formats like JSON that have no native section syntax, letting you keep a flat structure when the nesting would be excessive.
```

### Merge rules

When dotted keys and nested structures target the same leaf, the **last one in file order wins**:

```{code-block} json
:caption: Last value wins
{
    "my-cli": {
        "subcommand": {"int_param": 3},
        "subcommand.int_param": 77
    }
}
```

Here `int_param` resolves to `77` because the dotted key appears after the nested one.

### Conflicts

A conflict occurs when the same key is used as both a scalar and a namespace. For example:

```{code-block} json
:caption: Conflicting types on the same key
{
    "my-cli": {
        "subcommand": "some_value",
        "subcommand.int_param": 3
    }
}
```

Here `subcommand` is a plain string, but `subcommand.int_param` requires it to be a dict. By default, Click Extra logs a warning and the **last value wins** — in this case, `subcommand` becomes `{"int_param": 3}`, silently dropping `"some_value"`.

In [`strict` mode](#strictness), conflicts and invalid dotted keys raise a `ValueError` instead of being silently resolved.

The same conflict detection applies at deeper levels:

```{code-block} json
:caption: Deep conflict
{
    "my-cli": {
        "subcommand.int_param.nested": 1,
        "subcommand.int_param": 2
    }
}
```

Here `int_param` is set to both `{"nested": 1}` (via the first key) and `2` (via the second). A warning is logged and `int_param` resolves to `2`.

```{note}
Most formats prevent these conflicts at parse time — TOML rejects a key used as both a scalar and a table, YAML forbids duplicate keys — so in practice this mainly affects JSON.
```

### Invalid dotted keys

Dotted keys with empty segments (leading, trailing, or consecutive dots) are skipped with a warning:

```{code-block} json
:caption: Invalid keys that are skipped
{
    "my-cli": {
        ".option": 1,
        "option.": 2,
        "sub..option": 3
    }
}
```

All three keys above are ignored. Use `--verbosity WARNING` or higher to see the warnings. In [`strict` mode](#strictness), they raise a `ValueError`.

## Precedence

The configuration loader fetch values according the following precedence:

- `Interactive prompt`
  - ↖ `CLI parameters`
    - ↖ `Environment variables`
      - ↖ `Configuration file`
        - ↖ `Defaults`

The parameter will take the first value set in that chain.

Configuration file values are loaded into Click's `default_map`, so they are reported as {attr}`~click.ParameterSource.DEFAULT_MAP` and sit below environment variables in the hierarchy.

See how inline parameters takes priority on defaults from the previous example:

```{code-block} shell-session
:emphasize-lines: 1, 4
$ my-cli subcommand --int-param 555
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 555
```

## Get configuration values

After gathering all the configuration from the different sources, and assembling them together following the precedence rules above, the configuration values are merged back into the Context's `default_map`. But only the values that are matching the CLI's parameters are kept and passed as defaults. All others are silently ignored.

You can still access the full configuration by looking into the context's `meta` attribute:

```{code-block} python
:emphasize-lines: 9-12
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
:emphasize-lines: 3-6
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
:emphasize-lines: 7
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
:emphasize-lines: 4
$ cli --config "cli.toml"
Load configuration matching cli.toml
(...)
ValueError: Parameter 'random_param' is not allowed in configuration file.
```

```{tip}
If you want to check a configuration file for unrecognized keys without running the CLI, see the [`--validate-config` option](#validating-configuration-files) below.
```

## Validating configuration files

The `@validate_config_option` decorator adds a `--validate-config CONFIG_PATH` option that checks whether a configuration file is well-formed and contains only recognized parameters, then exits. This is useful for CI pipelines, editor integrations, or simply verifying a configuration file before deploying it.

Reusing the [standalone option example](#standalone-option) above:

```{code-block} python
:emphasize-lines: 2,8
from click import group, option, echo
from click_extra import config_option, validate_config_option

@group
@option("--dummy-flag/--no-flag")
@option("--my-list", multiple=True)
@config_option
@validate_config_option
def my_cli(dummy_flag, my_list):
    echo(f"dummy_flag    is {dummy_flag!r}")
    echo(f"my_list       is {my_list!r}")

@my_cli.command
@option("--int-param", type=int, default=10)
def subcommand(int_param):
    echo(f"int_parameter is {int_param!r}")
```

A valid configuration file:

```{code-block} toml
:caption: `good.toml`
[my-cli]
dummy_flag = true
my_list = ["pip", "npm"]

[my-cli.subcommand]
int_param = 3
```

```{code-block} shell-session
:emphasize-lines: 1-2
$ my-cli --validate-config good.toml
Configuration file good.toml is valid.
$ echo $?
0
```

A configuration file with unrecognized keys:

```{code-block} toml
:caption: `bad.toml`
:emphasize-lines: 3
[my-cli]
dummy_flag = true
unknown_key = "oops"
```

```{code-block} shell-session
:emphasize-lines: 2
$ my-cli --validate-config bad.toml
Configuration validation error: Parameter 'unknown_key' found in second dict but not in first.
$ echo $?
1
```

An unparsable file produces exit code 2:

```{code-block} shell-session
:emphasize-lines: 2,4
$ my-cli --validate-config garbage.txt
Error parsing garbage.txt as TOML, YAML, JSON, INI, XML or pyproject.toml.
$ echo $?
2
```

The exit codes are:

| Exit code | Meaning                              |
| :-------- | :----------------------------------- |
| `0`       | Configuration file is valid          |
| `1`       | Validation error (unrecognized keys) |
| `2`       | File not found or cannot be parsed   |

```{note}
`--validate-config` always validates in [strict mode](#strictness), regardless of the `strict` setting on `@config_option`. It requires a sibling `@config_option` decorator to be present on the same command.
```

## Excluding parameters

The {py:attr}`excluded_params <click_extra.config.ConfigOption.excluded_params>` argument allows you to block some of your CLI options to be loaded from configuration. By setting this argument, you will prevent your CLI users to set these parameters in their configuration file.

It defaults to the value of {py:data}`~click_extra.config.DEFAULT_EXCLUDED_PARAMS`.

You can set your own list of option to ignore with the `excluded_params` argument:

```{code-block} python
:emphasize-lines: 7
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

## Including parameters

The {py:attr}`included_params <click_extra.config.ConfigOption.included_params>` argument is the inverse of `excluded_params`: only the listed parameters will be loaded from the configuration file. All other parameters found in the configuration will be ignored.

```{code-block} python
:emphasize-lines: 6,8
from click import command, option, echo

from click_extra import config_option

@command
@option("--flag-a/--no-flag-a")
@option("--flag-b/--no-flag-b")
@config_option(included_params=("my-cli.flag_a",))
def my_cli(flag_a, flag_b):
    echo(f"flag_a={flag_a!r}")
    echo(f"flag_b={flag_b!r}")
```

In the example above, only `flag_a` will be loaded from configuration. `flag_b` will keep its CLI default even if it is present in the configuration file.

```{caution}
`included_params` and `excluded_params` are mutually exclusive. Providing both will raise a `ValueError`.
```

```{hint}
Like `excluded_params`, you need to provide the fully-qualified ID of the option. Run your CLI with the [`--show-params` option](#show-params-option) to discover parameter IDs.
```

### Schema-only configuration

When using `config_schema` for typed configuration access, your config keys typically don't correspond to CLI parameters — they're custom fields consumed via `get_tool_config()`. In that case, passing them through `merge_default_map` is unnecessary and can cause collisions if a config key happens to share a name with a subcommand.

Set `included_params=()` (empty tuple) to disable `merge_default_map` entirely. All configuration access goes through the schema:

```python
from dataclasses import dataclass
from click_extra import group, pass_context
from click_extra.config import get_tool_config


@dataclass
class AppConfig:
    setup_guide: bool = True
    sync_interval: int = 60


@group(config_schema=AppConfig, schema_strict=True, included_params=())
@pass_context
def my_app(ctx):
    config = get_tool_config(ctx)
    # config is always an AppConfig instance, never None
```

```{note}
`included_params=()` is different from `included_params=None`. `None` means "not configured, use the default behavior" (which applies `excluded_params`). `()` means "the allowlist is explicitly empty — merge nothing into `default_map`."
```

## Disabling autodiscovery

By default, `@config_option` automatically searches for configuration files in the [default application folder](#default-folder). If you want to disable this autodiscovery and only load a configuration file when the user explicitly passes `--config <path>`, use the `NO_CONFIG` sentinel as the default:

```{code-block} python
:emphasize-lines: 2,6
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

## Default subcommands

You can specify which subcommands run by default when a group is invoked without any explicit subcommands on the CLI. This is done via the `_default_subcommands` reserved configuration key.

Given this CLI:

```python
from click_extra import group, command, echo, config_option, option


@group
@config_option
def my_cli():
    pass


@my_cli.command()
@option("--path", default="/tmp")
def backup(path):
    echo(f"Backing up {path}")


@my_cli.command()
def sync():
    echo("Syncing")
```

And this TOML configuration:

```{code-block} toml
:emphasize-lines: 2
[my-cli]
_default_subcommands = ["backup"]

[my-cli.backup]
path = "/home"
```

Running `my-cli` alone will automatically invoke the `backup` subcommand:

```{code-block} shell-session
:emphasize-lines: 2
$ my-cli
Backing up /home
```

### Chained commands

For groups created with `chain=True`, you can list multiple default subcommands. They run in the order specified:

```{code-block} toml
:emphasize-lines: 2
[my-cli]
_default_subcommands = ["backup", "sync"]
```

```{code-block} shell-session
:emphasize-lines: 2-3
$ my-cli
Backing up /home
Syncing
```

```{note}
Non-chained groups only accept a single default subcommand. Listing more than one will produce an error.
```

### CLI precedence

If the user names subcommands explicitly on the command line, the `_default_subcommands` configuration is ignored:

```shell-session
$ my-cli sync
Syncing
```

### Prepend subcommands

The `_prepend_subcommands` key always prepends subcommands to every invocation, regardless of whether CLI subcommands are provided. This is useful for always injecting a subcommand (e.g. `debug`) on a dev machine.

```{important}
`_prepend_subcommands` only works with `chain=True` groups. Non-chained groups resolve exactly one subcommand, so prepending would break the user's intended command.
```

```{code-block} toml
:emphasize-lines: 2-3
[my-cli]
_prepend_subcommands = ["debug"]
```

Running `my-cli sync` effectively becomes `my-cli debug sync`:

```{code-block} shell-session
:emphasize-lines: 2-3
$ my-cli sync
Debug mode activated
Syncing
```

### `_default_subcommands` with `_prepend_subcommands`

When both keys are set and no CLI subcommands are given, `_default_subcommands` fires first, then `_prepend_subcommands` is prepended. The result is `[*prepend, *defaults]`:

```toml
[my-cli]
_default_subcommands = ["sync"]
_prepend_subcommands = ["debug"]
```

```shell-session
$ my-cli
Debug mode activated
Syncing
```

When CLI subcommands are given explicitly, `_default_subcommands` is ignored but `_prepend_subcommands` still applies:

```shell-session
$ my-cli backup
Debug mode activated
Backing up /tmp
```

## Formats

Several dialects are supported:

| Format                              | Extensions        | Description                                                                               | Enabled by default |
| :---------------------------------- | :---------------- | :---------------------------------------------------------------------------------------- | :----------------- |
| [`TOML`](#toml)                     | `*.toml`          | -                                                                                         | ✅                 |
| [`YAML`](#yaml)                     | `*.yaml`, `*.yml` | -                                                                                         | ❌                 |
| [`JSON`](#json)                     | `*.json`          | -                                                                                         | ✅                 |
| [`JSON5`](#json5)                   | `*.json5`         | A [superset of JSON made for configuration file](https://json5.org)                       | ❌                 |
| [`JSONC`](#jsonc)                   | `*.jsonc`         | Like JSON, but with comments and trailing commas                                          | ❌                 |
| [`HJSON`](#hjson)                   | `*.hjson`         | Another flavor of a [user-friendly JSON](https://hjson.github.io)                         | ❌                 |
| [`INI`](#ini)                       | `*.ini`           | With extended interpolation, multi-level sections and non-native types (`list`, `set`, …) | ✅                 |
| [`XML`](#xml)                       | `*.xml`           | -                                                                                         | ❌                 |
| [`PYPROJECT_TOML`](#pyproject-toml) | `pyproject.toml`  | Reads `[tool.*]` sections from `pyproject.toml`                                           | ✅                 |

Formats depending on third-party packages are not enabled by default. You need to [install Click Extra with the corresponding extra dependency group](install.md#extra-dependencies) to enable them.

### TOML

See the [example in the top of this page](#standalone-option).

### YAML

```{important}
YAML support requires additional packages. You need to [install `click-extra[yaml]`](install.md#extra-dependencies) extra dependency group to enable it.
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
:emphasize-lines: 2-4
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
:emphasize-lines: 2-4
$ my-cli --config "~/.config/my-cli/config.json" subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 65
```

### JSON5

```{important}
JSON5 support requires additional packages. You need to [install `click-extra[json5]`](install.md#extra-dependencies) extra dependency group to enable it.
```

```{todo}
Write example.
```

### JSONC

```{important}
JSONC support requires additional packages. You need to [install `click-extra[jsonc]`](install.md#extra-dependencies) extra dependency group to enable it.
```

```{todo}
Write example.
```

### HJSON

```{important}
HJSON support requires additional packages. You need to [install `click-extra[hjson]`](install.md#extra-dependencies) extra dependency group to enable it.
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
XML support requires additional packages. You need to [install `click-extra[xml]`](install.md#extra-dependencies) extra dependency group to enable it.
```

```{todo}
Write example.
```

<a name="pyproject-toml"></a>

### `pyproject.toml`

The `PYPROJECT_TOML` format reads `[tool.<cli-name>]` sections from a `pyproject.toml` file, following [PEP 518](https://peps.python.org/pep-0518/). This is useful for any CLI tool that wants to store its configuration alongside project metadata — not just Python projects. Tools like [ruff](https://docs.astral.sh/ruff/configuration/#configuring-ruff) and [typos](https://github.com/crate-ci/typos/blob/master/docs/reference.md), which are not Python projects, all use this convention, to play nice with other communities and increase adoption.

```{tip}
`pyproject.toml` is becoming the standard place to centralize tool configuration for Python projects. Instead of scattering dedicated config files at the root of your repository (`ruff.toml`, `typos.toml`, `mypy.ini`, …), you can consolidate them all under `[tool.*]` sections in a single `pyproject.toml`. This keeps the repository root clean, makes it easy to review and coordinate tool configurations in one place, and reduces the number of files contributors need to discover.
```

`PYPROJECT_TOML` is included in the default format patterns, so it is automatically discovered alongside other formats. The `[tool]` wrapper is automatically unwrapped: `merge_default_map` sees `{"cli": {"int_param": 3}}` — exactly the [same structure as a regular TOML config file](#toml).

```{seealso}
For a production example of a CLI built on Click Extra's `pyproject.toml` configuration with a [typed dataclass schema](#typed-configuration-schema), nested sub-tables, and 48 config options, see [repomatic's configuration reference](https://kdeldycke.github.io/repomatic/configuration.html). Repomatic also uses Click Extra's config system to [bridge `[tool.X]` sections](https://kdeldycke.github.io/repomatic/tool-runner.html#config-resolution) for third-party tools that don't read `pyproject.toml` natively.
```

#### CWD-first discovery

When auto-discovering configuration (no explicit `--config` flag), Click Extra searches for `pyproject.toml` starting from the current working directory and walking up to the VCS root *before* checking the standard app config directory. This matches the discovery behavior of uv, ruff, and mypy, so users get the configuration they expect without passing `--config` explicitly.

The CWD search only applies to `pyproject.toml` — other config formats (TOML, YAML, JSON, etc.) are still discovered from the app config directory. If a `pyproject.toml` is found via CWD search, the app-dir search is skipped entirely. If `--config` is passed explicitly, CWD search is bypassed.

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

Running `cli` from anywhere inside the project tree will find `pyproject.toml` at the repository root and apply `[tool.cli]` values. The walk [automatically stops at the VCS root](#walk-boundaries).

#### Dedicated file wins, no merging

When both a dedicated configuration file (e.g., `my-cli.toml`) and a `pyproject.toml` with a `[tool.my-cli]` section exist, Click Extra uses the **first parseable file** it finds and ignores all others. There is no merging across files.

This is the de facto standard across the ecosystem. Every major tool that supports both a dedicated config file and `pyproject.toml` follows the same strict precedence — dedicated file wins, `pyproject.toml` is ignored entirely:

| Tool                                                                              | Precedence rule                                                                |
| :-------------------------------------------------------------------------------- | :----------------------------------------------------------------------------- |
| [ruff](https://docs.astral.sh/ruff/configuration/#config-file-discovery)          | `.ruff.toml` > `ruff.toml` > `pyproject.toml`                                  |
| [uv](https://docs.astral.sh/uv/concepts/configuration-files/#configuration-files) | `uv.toml` > `pyproject.toml`                                                   |
| [typos](https://github.com/crate-ci/typos/blob/master/docs/reference.md)          | `typos.toml` / `_typos.toml` / `.typos.toml` > `Cargo.toml` > `pyproject.toml` |

The rationale:

- **No merging surprises.** Merging two config sources creates ambiguity: which key wins when both files define it? Are arrays concatenated or replaced? Every tool above chose "first match wins, full stop" to avoid this class of problems entirely.
- **Explicit intent.** A dedicated file at the repository root, named after the tool, is the most visible and explicit signal. If someone creates one alongside a `[tool.*]` section, the dedicated file represents a deliberate override.
- **Clean migration path.** Users moving from a dedicated file to `pyproject.toml` simply delete the dedicated file. Users who need the dedicated file (e.g., sharing it across non-Python repos) keep it and `pyproject.toml` is silently ignored.

```{seealso}
Other non-Python tools that support `[tool.*]` in `pyproject.toml`:
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

Click Extra's own `[tool.*]` bridge in [repomatic's tool runner](https://kdeldycke.github.io/repomatic/tool-runner.html#level-2-tool-x-in-pyproject-toml) translates `[tool.yamllint]`, `[tool.actionlint]`, `[tool.biome]`, and others into native config files at invocation time, giving tools that lack native `pyproject.toml` support the same single-file experience.

Other tools are following suit:
[actionlint#623](https://github.com/rhysd/actionlint/issues/623),
[biome#9239](https://github.com/biomejs/biome/discussions/9239),
[gitleaks#2066](https://github.com/gitleaks/gitleaks/issues/2066),
[taplo#603](https://github.com/tamasfe/taplo/issues/603),
[zizmor#322](https://github.com/orgs/zizmorcore/discussions/322#discussioncomment-15919620).
[sh#1268](https://github.com/mvdan/sh/issues/1268) was declined.
```

## Search pattern

The configuration file is searched with a wildcard-based glob pattern.

There is multiple stages to locate and parse the configuration file:

1. Locate all files matching the search pattern
2. Match each file against the supported formats, in order, until one is successfully parsed
3. Use the first successfully parsed file as the configuration source

By default, the pattern is `<app_dir>/{*.toml,*.json,*.ini}`, where:

- `<app_dir>` is the [default application folder](#default-folder)
- `{*.toml,*.json,*.ini}` are the [extensions of formats](#formats) enabled by default, wrapped in brace-expansion syntax

```{hint}
Depending on the formats you enabled in your installation of Click Extra, the default extensions may vary. For example, if you installed Click Extra with all extra dependencies, the default extensions would be extended to `{*.toml,*.yaml,*.yml,*.json,*.json5,*.jsonc,*.hjson,*.ini,*.xml,pyproject.toml}`.
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
:emphasize-lines: 6
from click import command

from click_extra import config_option

@command(context_settings={"show_default": True})
@config_option(force_posix=True)
def cli():
    pass
```

See how the default to `--config` option has been changed to `~/.cli/`:

```{click:run}
:emphasize-lines: 6
from boltons.iterutils import flatten, unique
from click_extra import ConfigFormat
result = invoke(cli, args=["--help"])
fp = ",".join(unique(flatten(f.patterns for f in ConfigFormat if f.enabled)))
assert f"~/.cli/{{{fp}}}]" in result.stdout.replace("\n                        ", "")
```

```{seealso}
The default application folder concept has a long and complicated history in the Unix world.

The oldest reference I can track is from the [*Where Configurations Live*](http://www.catb.org/~esr/writings/taoup/html/ch10s02.html) chapter from [*The Art of Unix Programming*](https://a.co/d/aC36Ft0).

The [*XDG base directory specification*](https://specifications.freedesktop.org/basedir/latest/) is the latest iteration of this tradition on Linux. This long-due guidelines brings [lots of benefits](https://xdgbasedirectoryspecification.com) to the platform. This is what Click Extra is [implementing by default](#default-folder).

But there is still a lot of cases for which the XDG doesn't cut it, like on other platforms (macOS, Windows, …) or for legacy applications. That's why Click Extra allows you to customize the way configuration is searched and located.
```

### Custom pattern

You can also provide a custom path to the configuration file via the `--config` option added to your CLI by the `@config_option` decorator.

To change the default search pattern, pass a customized value to the `default` argument of the decorator:

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
:emphasize-lines: 7
result = invoke(cli, args=["--help"])
assert "~/my_special_folder/*.toml]" in result.stdout
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

The flags above can be changed via the {py:class}`search_pattern_flags argument of the decorator <click_extra.config.ConfigOption>`. So to make the matching case-insensitive, add the `IGNORECASE` flag:

```{code-block} python
:emphasize-lines: 8,9,14
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

But because of the way flags works, you have to re-specify all flags you want to keep, including the default ones.

```{seealso}
This is the same pinciple as [file pattern flags](#file-pattern-flags).
```

### Multi-format matching

The default behavior consist in searching for all files matching the default `{*.toml,*.json,*.ini}` pattern. Or more, depending on the [extra dependencies](install.md#extra-dependencies) installed with Click Extra.

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
:emphasize-lines: 8
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
:emphasize-lines: 8
result = invoke(cli, args=["--help"])
assert "*.xml]" in result.stdout
```

### Custom file format patterns

Each format is associated with [default file patterns](#formats). But you can also change these with the same `file_format_patterns` argument:

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
:emphasize-lines: 8
result = invoke(cli, args=["--help"])
assert "{*.toml,my_app.conf,settings*.js,*.json}]" in result.stdout
```

### Parsing priority

The syntax of `file_format_patterns` argument allows you to specify either a list of formats, a single format, or a mapping of formats to patterns. And we can even have multiple formats share the same pattern:

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

Notice how all formats are merged into the same pattern:

```{click:run}
:emphasize-lines: 8
result = invoke(cli, args=["--help"])
assert "{*.toml,config*.js,*.js}" in result.stdout
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
:emphasize-lines: 3
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
:emphasize-lines: 6
result = invoke(cli, args=["--help"])
assert "[default: ~/.commandrc]" in " ".join(result.stdout.split())
```

```{caution}
Depending on how you set up your patterns, files starting with a dot (`.`) may not be matched by default. Make sure to include the [`DOTMATCH`](https://facelessuser.github.io/wcmatch/fnmatch/#dotmatch) flag in `file_pattern_flags` if needed.
```

### Parent folder search

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

The first successfully [parsed file wins](#parsing-priority). This is useful for monorepo or project-local configuration, where a config file placed higher in the tree acts as a fallback.

```{note}
Parent search works with both plain paths and [glob patterns](#search-pattern-specifications). For glob patterns, the non-magic directory prefix is identified and the file pattern is searched at each parent level via `root_dir`. Entirely magic patterns like `*.toml` have no directory prefix to walk up, so only the original pattern is searched.
```

#### Walk boundaries

The parent directory walk stops as soon as it hits any of the following boundaries:

- **Filesystem root** — the walk always stops at `/` (or the drive root on Windows).
- **Inaccessible directory** — if a parent directory exists but is not readable, the walk stops immediately.
- **VCS root** (`stop_at=VCS`, the default) — the walk stops at the nearest repository root (a directory containing `.git` or `.hg`). If no VCS root is found, the walk continues to the filesystem root.
- **Explicit path** (`stop_at="/some/path"`) — the walk stops as soon as it leaves the given directory.
- **No boundary** (`stop_at=None`) — the walk continues all the way to the filesystem root.

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

### Remote URL

Remote URL can be passed directly to the `--config` option:

```{code-block} shell-session
:emphasize-lines: 1
$ my-cli --config "https://example.com/dummy/configuration.yaml" subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```

```{warning}
URLs do not support multi-format matching. You need to provide a direct link to the configuration file, including its extension.

Glob patterns are also not supported for URLs. Unless you want to let your users download the whole internet…
```

## Typed configuration schema

By default, `ConfigOption` only feeds configuration values that match CLI options into the context's `default_map`. Any other keys in the configuration file are silently ignored. This works well when the configuration file mirrors the CLI structure, but some applications need access to *additional* configuration that doesn't correspond to any CLI option.

The `config_schema` parameter solves this by extracting the app's configuration section, normalizing its keys, and producing a typed object available to all commands via `ctx.meta["click_extra.tool_config"]`.

```{tip}
[repomatic](https://kdeldycke.github.io/repomatic/) is a production CLI that uses all of the features below: a [48-field Config dataclass](https://kdeldycke.github.io/repomatic/configuration.html) with nested sub-dataclasses, opaque dict fields for GitHub Actions matrices, `config_path` metadata for kebab-case TOML keys, and `schema_strict=True` to catch typos. It can serve as a reference for building complex typed configuration.
```

### Dataclass schema

The most common pattern is a Python dataclass. Click Extra auto-detects dataclass types, normalizes hyphenated keys to underscores, flattens nested sections, and filters to known fields:

```{click:source}
from dataclasses import dataclass, field
from click_extra import command, echo, group, option, pass_context
from click_extra.config import get_tool_config

@dataclass
class AppConfig:
    """Typed configuration for my-app."""
    extra_categories: list[str] = field(default_factory=list)
    output_format: str = "text"

@group(config_schema=AppConfig)
@option("--verbose/--no-verbose")
@pass_context
def my_app(ctx, verbose):
    """An app with typed configuration."""
    config = get_tool_config(ctx)
    if config is not None:
        echo(f"output_format: {config.output_format}")
        echo(f"extra_categories: {config.extra_categories}")

@my_app.command()
@option("--name", default="World")
def greet(name):
    """Say hello."""
    echo(f"Hello, {name}!")
```

With a TOML configuration file:

```{code-block} toml
:caption: `~/.config/my-app/config.toml`
[my-app]
verbose = true
extra-categories = ["docs", "tests"]
output-format = "json"

[my-app.greet]
name = "Alice"
```

The CLI options (`verbose`, `name`) are fed into `default_map` as before. The additional keys (`extra-categories`, `output-format`) are normalized (hyphens to underscores) and passed to the `AppConfig` dataclass. Fields not present in the file get their dataclass defaults.

```{click:run}
result = invoke(my_app, args=["--help"])
assert result.exit_code == 0
assert "--verbose" in result.stdout
```

### Callable schema

Any callable that accepts a `dict` and returns an object can be used as `config_schema`. This supports Pydantic models, attrs classes, or custom factories:

```{click:source}
from types import SimpleNamespace
from click_extra import echo, group, pass_context
from click_extra.config import get_tool_config, normalize_config_keys

def parse_config(raw):
    """Custom config parser that normalizes keys."""
    return SimpleNamespace(**normalize_config_keys(raw))

@group(config_schema=parse_config)
@pass_context
def callable_app(ctx):
    """An app with a callable schema."""
    config = get_tool_config(ctx)
    if config is not None:
        echo(f"value: {config.custom_value}")

@callable_app.command()
def run():
    """Run the app."""
    echo("done")
```

```{click:run}
result = invoke(callable_app, args=["--help"])
assert result.exit_code == 0
```

### Retrieving the config object

The typed configuration is stored in `ctx.meta["click_extra.tool_config"]` and can be accessed in two ways:

```python
# Via the convenience helper (uses current context by default):
from click_extra.config import get_tool_config

config = get_tool_config()

# Or directly from the context:
config = ctx.find_root().meta.get("click_extra.tool_config")
```

If no `config_schema` was set, `get_tool_config()` returns `None`. When a `config_schema` is configured but no configuration file is found, the schema is instantiated with its defaults so `get_tool_config()` always returns a usable object.

### Format-agnostic

The `config_schema` feature works with all configuration formats supported by `ConfigOption` — TOML, YAML, JSON, JSON5, JSONC, Hjson, INI, and XML. The parsed configuration is normalized into a Python dict before the schema is applied, so the same schema works regardless of the source format.

For example, the same `AppConfig` dataclass works with YAML:

```{code-block} yaml
:caption: `~/.config/my-app/config.yaml`
my-app:
  extra-categories:
    - docs
    - tests
  output-format: json
```

Or JSON:

```{code-block} json
:caption: `~/.config/my-app/config.json`
{
    "my-app": {
        "extra-categories": ["docs", "tests"],
        "output-format": "json"
    }
}
```

### Key normalization

Configuration formats commonly use kebab-case (`extra-categories`), while Python identifiers use snake_case (`extra_categories`). The `normalize_config_keys` utility handles this conversion recursively:

```python
from click_extra.config import normalize_config_keys

raw = {"extra-categories": ["a", "b"], "nested-section": {"sub-key": 1}}
normalized = normalize_config_keys(raw)
# {"extra_categories": ["a", "b"], "nested_section": {"sub_key": 1}}
```

For dataclass schemas, this normalization is applied automatically. For callable schemas, call `normalize_config_keys` explicitly if needed.

### Nested configuration sections

TOML and YAML configurations often group related settings under sub-tables (e.g. `[tool.myapp.dependency-graph]`). When using a dataclass schema, Click Extra automatically flattens these nested sections by joining parent and child keys with `_`, so they map directly to flat dataclass fields:

```python
from click_extra.config import flatten_config_keys, normalize_config_keys

raw = {"dependency-graph": {"all-groups": True, "output": "deps.mmd"}}
flatten_config_keys(normalize_config_keys(raw))
# {"dependency_graph_all_groups": True, "dependency_graph_output": "deps.mmd"}
```

This means a dataclass with flat fields like `dependency_graph_output` and `dependency_graph_all_groups` can be populated from nested TOML:

```{code-block} toml
:caption: Nested sub-tables map to flat dataclass fields.
[my-app.dependency-graph]
output = "deps.mmd"
all-groups = false
```

The full pipeline applied to dataclass schemas is: normalize keys (hyphens to underscores), flatten nested dicts (joining with `_`), then match against dataclass field names. Top-level keys and nested sub-table keys can be mixed freely.

For callable schemas, use `flatten_config_keys` and `normalize_config_keys` explicitly if you need the same behavior.

### Type-aware flattening

By default, `flatten_config_keys` recurses into every nested dict. This breaks fields typed as `dict[str, X]` where the dict keys are data rather than config structure (e.g. GitHub Actions matrix axis names like `os` or `python-version`).

When using a dataclass schema, Click Extra inspects field type hints and automatically stops flattening at `dict`-typed field boundaries. The dict value is assigned whole to the matching field:

```python
from dataclasses import dataclass, field


@dataclass
class AppConfig:
    simple_value: str = ""
    opaque_map: dict[str, list[str]] = field(default_factory=dict)
```

```{code-block} toml
:caption: Dict-typed fields are kept intact, not flattened.
[my-app]
simple-value = "hello"

[my-app.opaque-map]
python-version = ["3.12", "3.13"]
os = ["ubuntu", "macos"]
```

Here `opaque_map` receives `{"python_version": ["3.12", "3.13"], "os": ["ubuntu", "macos"]}` as a single dict, rather than being split into `opaque_map_python_version` and `opaque_map_os`.

Both `normalize_config_keys` and `flatten_config_keys` accept an `opaque_keys` parameter for manual control:

```python
from click_extra.config import flatten_config_keys

conf = {"matrix": {"replace": {"os": {"old": "new"}}, "count": 3}}
flatten_config_keys(conf, opaque_keys=frozenset({"matrix_replace"}))
# {"matrix_replace": {"os": {"old": "new"}}, "matrix_count": 3}
```

### Field metadata

Dataclass fields can carry metadata to control how their values are extracted from the raw config:

- **`click_extra.config_path`**: A dotted TOML path (e.g. `"test-matrix.replace"`). The value is extracted directly from the raw config before normalization and flattening, bypassing the standard pipeline.

- **`click_extra.normalize_keys`**: Set to `False` to skip key normalization on the extracted value. Useful when the value contains keys that are external identifiers (e.g. GitHub Actions axis names like `python-version`) that must not be converted to `python_version`.

```python
from dataclasses import dataclass, field


@dataclass
class AppConfig:
    special: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "click_extra.config_path": "deep.section",
            "click_extra.normalize_keys": False,
        },
    )
```

```{code-block} toml
:caption: Keys in the extracted section are preserved as-is.
[my-app.deep.section]
kebab-key = "preserved"
```

With `normalize_keys=False`, `special` receives `{"kebab-key": "preserved"}` instead of `{"kebab_key": "preserved"}`.

### Nested dataclass schemas

Fields whose type is another dataclass are recursively instantiated with the same normalize/flatten/opaque logic. This allows complex config sections to be modeled as typed sub-schemas:

```python
from dataclasses import dataclass, field


@dataclass
class MatrixConfig:
    exclude: list[dict[str, str]] = field(default_factory=list)
    replace: dict[str, dict[str, str]] = field(default_factory=dict)
    variations: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class AppConfig:
    name: str = ""
    matrix: MatrixConfig = field(
        default_factory=MatrixConfig,
        metadata={
            "click_extra.config_path": "test-matrix",
            "click_extra.normalize_keys": False,
        },
    )
```

```{code-block} toml
:caption: Nested dataclass with opaque sub-fields.
[my-app]
name = "my-project"

[my-app.test-matrix]
exclude = [{os = "windows-11-arm"}]

[my-app.test-matrix.replace]
os = {"ubuntu-slim" = "ubuntu-24.04"}

[my-app.test-matrix.variations]
python-version = ["3.14"]
```

The `matrix` field receives a `MatrixConfig` instance. Because `normalize_keys=False`, axis names like `python-version` and runner identifiers like `ubuntu-slim` are preserved verbatim in the `replace` and `variations` dicts.

Nested dataclass fields without `config_path` metadata are matched by their normalized field name in the flattened config, just like scalar fields. The nesting is detected from the type hint and the sub-dict is recursively processed.

### Schema validation

By default, configuration keys that don't match any dataclass field are silently ignored. The `schema_strict` parameter changes this to raise a `ValueError`, catching typos and stale configuration entries:

```python
@group(config_schema=AppConfig, schema_strict=True)
def my_app(): ...
```

Or directly on the config option:

```python
@config_option(config_schema=AppConfig, schema_strict=True)
```

When `schema_strict=True`, the error message lists both the unrecognized keys and all valid options:

```text
ValueError: Unknown configuration option(s): typo_field. Valid options: known_field, output_format
```

```{note}
`schema_strict` is separate from the existing `strict` parameter. `strict` controls whether `merge_default_map` rejects config keys that don't match CLI parameters. `schema_strict` validates against dataclass fields instead. The two can be used independently.
```

## Fallback sections

When a CLI tool is renamed, existing configuration files may still use the old section name. The `fallback_sections` parameter lets you accept legacy names with a deprecation warning:

```{click:source}
from dataclasses import dataclass
from click_extra import echo, group, pass_context
from click_extra.config import get_tool_config

@dataclass
class ToolConfig:
    value: str = "default"

@group(
    config_schema=ToolConfig,
    fallback_sections=("old-tool-name", "even-older-name"),
)
@pass_context
def new_tool(ctx):
    """A tool that was renamed."""
    config = get_tool_config(ctx)
    if config is not None:
        echo(f"value: {config.value}")

@new_tool.command()
def run():
    """Run the tool."""
    echo("done")
```

With the following TOML:

```{code-block} toml
:caption: Legacy configuration still using the old name.
[old-tool-name]
value = "from-legacy"
```

The CLI loads the `[old-tool-name]` section and logs a deprecation warning to stderr:

```text
Config section [old-tool-name] is deprecated, migrate to [new-tool].
```

If both `[new-tool]` and `[old-tool-name]` exist, the current name always wins, and a warning is emitted about the leftover legacy section.

```{click:run}
result = invoke(new_tool, args=["--help"])
assert result.exit_code == 0
```

This works identically across all configuration formats (TOML, YAML, JSON, INI, etc.), since the section lookup operates on the normalized dict structure after parsing.

## `click_extra.config` API

```{eval-rst}
.. autoclasstree:: click_extra.config
   :strict:

.. automodule:: click_extra.config
   :members:
   :undoc-members:
   :show-inheritance:
```
