# {octicon}`sliders` Configuration files

The structure of the configuration file is [derived from the CLI's parameters](parameters.md#parameter-structure) and their types. You never write a data structure to mirror the CLI.

```{tip}
After loading, the resolved file path, the full parsed document, and (when a `config_schema` is set) the typed app section are exposed on `ctx.meta` as `CONF_SOURCE`, `CONF_FULL`, and `TOOL_CONFIG`. With [`cascade=True`](config-discovery.md#cascading-configuration-files), `CONF_SOURCES` additionally lists every file that was loaded. See the [available keys](context.md#available-keys) table to read them from your own callbacks.
```

## Resolving a configuration file

Before any value is read, Click Extra decides *which* file, if any, provides the configuration. An explicit `--config` (or its environment variable or interactive prompt) wins outright. Otherwise autodiscovery applies: `pyproject.toml` is searched from the current directory up to the VCS root, then the [app-dir search pattern](config-discovery.md) takes over. The first file that parses to a non-empty mapping is used, with no merging across files.

```mermaid
:align: center

flowchart TD
    start(["@config_option resolves a pattern"]) --> nc{"autodiscovery disabled?"}
    nc -->|yes| skip["Skip loading, use bare defaults"]
    nc -->|no| exp{"--config, env or prompt set?"}
    exp -->|"no, auto-discover"| pyp{"pyproject.toml format enabled?"}
    pyp -->|yes| cwd{"tool.cli table in a pyproject.toml, CWD up to VCS root?"}
    cwd -->|yes| usepyp["Use that tool.cli section"]
    cwd -->|no| search["Search files matching the pattern, try formats in order"]
    pyp -->|no| search
    exp -->|yes| search
    search --> parse{"a file parses to a non-empty config?"}
    parse -->|yes| win["First match wins, no merging"]
    parse -->|"no, explicit"| fail["Exit with code 2"]
    parse -->|"no, auto-discover"| defaults["Use bare defaults"]
```

Once a file is selected, its values feed into the [precedence chain](#precedence) below: environment variables, CLI parameters, and interactive prompts all override what the file provides.

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

The code above is saved in a file named `my_cli.py`. It produces the following help screen:

```{click:run}
:emphasize-result-lines: 7-10
result = invoke(my_cli, args=["--help"])
assert "--config LOCATION" in result.stdout
```

The help screen names the default location of the configuration file (`[default: ~/.config/my-cli/{*.toml,*.yaml,*.yml,*.json,*.json5,*.jsonc,*.hjson,*.ini,*.xml,*.plist,*.sqlite,*.sqlite3,*.conf,pyproject.toml}]`). This improves discoverability, and [makes sysadmins happy](https://utcc.utoronto.ca/~cks/space/blog/sysadmin/ReportConfigFileLocations), especially those not familiar with your CLI.

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

A TOML file in the application folder changes the CLI's defaults. Here is what `~/.config/my-cli/config.toml` contains:

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

In the file above, note:

- The [default configuration base path](config-discovery.md#default-folder), which is OS-dependent (the `~/.config/my-cli/` path here is for Linux).
- The app's folder (`/my-cli/`), built from the script's name (`my_cli.py`).
- The top-level config section (`[my-cli]`), based on the CLI's group ID (`def my_cli()`).
- The extra comments, sections and values, all silently ignored.

The configuration file is read and changes the defaults:

```{code-block} shell-session
$ my-cli subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 3
```

## Key spelling

Configuration keys address CLI parameters by name, in either of two spellings:

- **kebab-case** is the canonical presentation: it matches the spelling of the CLI flags and the convention of TOML and YAML files. It is what [`--export-config`](#exporting-the-configuration) emits.
- **snake_case** is the parameter's internal ID, which Click derives from the flag by replacing hyphens with underscores: the `--dummy-flag` option is the `dummy_flag` parameter. This ID is what [`--params`](parameters.md#params-option) reports, and what roots the auto-generated environment variable (`CLI_DUMMY_FLAG`), since neither Python identifiers nor environment variables can carry dashes.

Both spellings resolve to the same parameter: `dummy-flag` and `dummy_flag` both set `--dummy-flag`. When the two coexist in a file, the last one in file order wins and a warning names both.

```{note}
Click also accepts snake_case flags: `--my_option` is legal and derives the same `my_option` parameter ID as `--my-option` would. For such a CLI the canonical config key is still the kebab-cased `my-option`, which loads back to the same parameter.
```

### Decoupling the flag from the configuration key

Click's third positional declaration names the parameter explicitly, decoupling it from the flags. This is handy for repeatable options, where the flag names one occurrence but the configuration key holds the whole collection: keep the flag singular and pluralize the parameter, so the config key, the environment variable and the callback argument all read as the list they are.

```{click:source}
from click_extra import command, echo, option

@command
@option("--hash-header", "hash_headers", multiple=True)
def scanner(hash_headers):
    echo(f"headers = {hash_headers!r}")
```

The `--hash-header` flag is repeated once per value:

```{click:run}
result = invoke(scanner, args=["--hash-header", "Date", "--hash-header", "From"])
assert "headers = ('Date', 'From')" in result.stdout
```

While the configuration key, shown here by exporting the values just set, is the plural `hash-headers` list:

```{click:run}
result = invoke(
    scanner,
    args=["--hash-header", "Date", "--hash-header", "From", "--export-config", "toml"],
)
assert 'hash-headers = ["Date", "From"]' in result.stdout
```

The environment variable follows the parameter ID too, so a single `SCANNER_HASH_HEADERS` value feeds the whole list.

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

Dotted keys are expanded into nested dicts and deep-merged before the configuration is applied. This works across all [supported formats](config-formats.md), and at any nesting depth (for example, `"subcommand.nested.option"` expands to three levels).

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

Here `subcommand` is a plain string, but `subcommand.int_param` requires it to be a dict. By default, Click Extra logs a warning and the **last value wins**: in this case, `subcommand` becomes `{"int_param": 3}`, silently dropping `"some_value"`.

In [`strict` mode](config-validation.md#strictness), conflicts and invalid dotted keys raise a `ValueError` instead of being silently resolved.

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
Most formats prevent these conflicts at parse time (TOML rejects a key used as both a scalar and a table, YAML forbids duplicate keys), so in practice this mainly affects JSON.
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

All three keys above are ignored. Use `--verbosity WARNING` or higher to see the warnings. In [`strict` mode](config-validation.md#strictness), they raise a `ValueError`.

## Precedence

The loader fetches values in the following precedence order:

```mermaid
:align: center

flowchart TD
    P["Interactive prompt"] -->|unset| C["CLI parameters"]
    C -->|unset| E["Environment variables"]
    E -->|unset| F["Configuration file"]
    F -->|unset| D["Defaults"]
```

Each parameter takes the first value set in that chain.

Configuration file values are loaded into Click's `default_map`, so they are reported as {attr}`~click.ParameterSource.DEFAULT_MAP` and sit below environment variables in the hierarchy.

Inline parameters take priority over the file's defaults:

```{code-block} shell-session
:emphasize-lines: 1, 4
$ my-cli subcommand --int-param 555
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 555
```

## Get configuration values

The resolved values are merged into the context's `default_map`. Only values matching a CLI parameter are kept and passed as defaults. All others are silently ignored.

The full configuration stays accessible in the context's `meta` attribute:

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
- `click_extra.conf_full` is a `dict` whose values are either `str` or richer types, depending on the capabilities of [each format](config-formats.md)
```

## Exporting the configuration

The `@export_config_option` decorator adds a `--export-config FORMAT` option that resolves the CLI's current configuration and writes it to `<stdout>` as a ready-to-use configuration file, then exits. It is part of the [default options](commands.md#default-options) of every `@command` and `@group`, so click-extra CLIs ship with it out of the box.

The values are resolved through the usual [precedence chain](#precedence): command-line parameters override environment variables, which override an autodiscovered configuration file, which overrides the defaults. So combining `--export-config` with other options or environment variables captures them in the generated configuration, which makes it a convenient way to freeze the current invocation into a file or to produce a starting-point template.

```{click:source}
from click_extra import command, echo, option

@command
@option("--city", default="Lisbon")
@option("--temperature", type=int, default=18)
@option("--tags", multiple=True, default=("sunny",))
def weather(city, temperature, tags):
    echo(f"{city}: {temperature}C {tags!r}")
```

A bare export renders every configurable parameter, including click-extra's own built-in options:

```{click:run}
result = invoke(weather, args=["--export-config", "toml"])
assert result.exit_code == 0
assert "[weather]" in result.stdout
assert 'city = "Lisbon"' in result.stdout
assert "temperature = 18" in result.stdout
```

Any value set on the command line (or via an environment variable) is reflected in the export, so the output can be saved straight into a configuration file:

```{click:run}
result = invoke(
    weather,
    args=["--city", "Oslo", "--temperature", "4", "--export-config", "toml"],
)
assert result.exit_code == 0
assert 'city = "Oslo"' in result.stdout
assert "temperature = 4" in result.stdout
```

Redirect the output to your configuration file to persist it:

```{code-block} shell-session
$ weather --city Oslo --export-config toml > ~/.config/weather/config.toml
```

The accepted formats are the ones click-extra can serialize: `toml`, `yaml`, `json`, `json5`, `jsonc`, `hjson`, `xml` and `plist`. `ini`, `sqlite`, `argfile` and `pyproject.toml` have no serializer and cannot be exported. A format whose optional dependency is missing exits with code 1 and an install hint.

Exported keys use the canonical kebab-case spelling (see [Key spelling](#key-spelling)), so the generated file reads like the CLI flags it mirrors.

Parameters without a value are exported too, so the generated file names every key a configuration file can set. Multi-value parameters read as empty lists, and unset scalars render as `null`, except in TOML which has no null type and comments them out:

```{click:source}
from click_extra import command, echo, option

@command
@option("--regexp")
@option("--tags", multiple=True)
def filters(regexp, tags):
    echo(f"{regexp!r} {tags!r}")
```

```{click:run}
result = invoke(filters, args=["--export-config", "toml"])
assert result.exit_code == 0
assert "tags = []" in result.stdout
assert "# regexp =" in result.stdout
```

If a configuration file is discovered or passed via `--config`, its values are loaded before the export renders, so the output reflects the full precedence chain regardless of the order of the flags on the command line. The same guarantee applies to [`--params`](parameters.md#params-option).

```{note}
`--export-config` is itself excluded from the export, like the other [introspection options](#excluding-parameters) (`--help`, `--version`, `--params`, `--validate-config`). It requires a sibling `@config_option` decorator to be present on the same command.
```

## Excluding parameters

The {py:attr}`excluded_params <click_extra.config.option.ConfigOption.excluded_params>` argument blocks listed CLI options from being loaded from configuration.

It defaults to the value of {py:data}`~click_extra.config.option.DEFAULT_EXCLUDED_PARAMS`, plus the CLI's `--help` option, resolved at runtime.

Set your own blocklist with the `excluded_params` argument:

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
Provide the fully-qualified ID of the option to block: the dot-separated ID prefixed by the CLI name. This reaches options at any level, including subcommands.

To discover options and their IDs, run your CLI with the [`--params` option](parameters.md#params-option).
```

On the default `@command` and `@group` decorators, the `excluded_params` keyword extends the blocklist without replacing the whole default parameter list. Unlike the option-level argument above, it is additive: the built-in exclusions (`--config`, `--version`, `--help`, ...) are preserved and your IDs are unioned into them.

```{code-block} python
from click_extra import command

@command(excluded_params=["my-cli.dangerous_param"])
def my_cli(): ...
```

Under [strict mode](config-validation.md#strictness), a blocked parameter found in a configuration file is refused with a dedicated message naming it as not allowed, rather than unknown.

## Including parameters

The `included_params` argument is the inverse of `excluded_params`: only the listed parameters will be loaded from the configuration file. All other parameters found in the configuration will be ignored.

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
Like `excluded_params`, this takes fully-qualified option IDs. Run your CLI with the [`--params` option](parameters.md#params-option) to discover them.
```

### Schema-only configuration

When using `config_schema` for typed configuration access, your config keys typically don't correspond to CLI parameters: they're custom fields consumed via `get_tool_config()`. In that case, passing them through `merge_default_map` is unnecessary and can cause collisions if a config key happens to share a name with a subcommand.

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
`included_params=()` is different from `included_params=None`. `None` means "not configured, use the default behavior" (which applies `excluded_params`). `()` means "the allowlist is explicitly empty: merge nothing into `default_map`."
```

## Disabling autodiscovery

By default, `@config_option` automatically searches for configuration files in the [default application folder](config-discovery.md#default-folder). If you want to disable this autodiscovery and only load a configuration file when the user explicitly passes `--config <path>`, use the `NO_CONFIG` sentinel as the default:

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

```{click:source}
from click_extra import echo, group, option


@group
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

```{click:run}
import tempfile, textwrap
from pathlib import Path

config = Path(tempfile.mkdtemp()) / "my-cli.toml"
config.write_text(textwrap.dedent("""
    [my-cli]
    _default_subcommands = ["backup"]

    [my-cli.backup]
    path = "/home"
"""))
result = invoke(my_cli, args=["--config", str(config)])
assert result.exit_code == 0
assert "Backing up /home" in result.stdout
```

### Chained commands

For groups created with `chain=True`, you can list multiple default subcommands. They run in the order specified. The rest of this section builds on a chained variant of the CLI above, with a `debug` subcommand to prepend later:

```{click:source}
:emphasize-lines: 4
from click_extra import echo, group, option


@group(chain=True)
def my_cli():
    pass


@my_cli.command()
@option("--path", default="/tmp")
def backup(path):
    echo(f"Backing up {path}")


@my_cli.command()
def sync():
    echo("Syncing")


@my_cli.command()
def debug():
    echo("Debug mode activated")
```

```{code-block} toml
:emphasize-lines: 2
[my-cli]
_default_subcommands = ["backup", "sync"]
```

```{click:run}
import tempfile, textwrap
from pathlib import Path

config = Path(tempfile.mkdtemp()) / "my-cli.toml"
config.write_text(textwrap.dedent("""
    [my-cli]
    _default_subcommands = ["backup", "sync"]

    [my-cli.backup]
    path = "/home"
"""))
result = invoke(my_cli, args=["--config", str(config)])
assert result.exit_code == 0
assert result.stdout.index("Backing up /home") < result.stdout.index("Syncing")
```

```{note}
Non-chained groups only accept a single default subcommand. Listing more than one will produce an error.
```

### CLI precedence

If the user names subcommands explicitly on the command line, the `_default_subcommands` configuration is ignored:

```{click:run}
import tempfile, textwrap
from pathlib import Path

config = Path(tempfile.mkdtemp()) / "my-cli.toml"
config.write_text(textwrap.dedent("""
    [my-cli]
    _default_subcommands = ["backup"]
"""))
result = invoke(my_cli, args=["--config", str(config), "sync"])
assert result.exit_code == 0
assert "Syncing" in result.stdout
assert "Backing up" not in result.stdout
```

### Prepend subcommands

The `_prepend_subcommands` key always prepends subcommands to every invocation, regardless of whether CLI subcommands are provided. This is useful for always injecting a subcommand (like `debug`) on a dev machine.

```{important}
`_prepend_subcommands` only works with `chain=True` groups. Non-chained groups resolve exactly one subcommand, so prepending would break the user's intended command.
```

```{code-block} toml
:emphasize-lines: 2
[my-cli]
_prepend_subcommands = ["debug"]
```

Running `my-cli sync` effectively becomes `my-cli debug sync`:

```{click:run}
import tempfile, textwrap
from pathlib import Path

config = Path(tempfile.mkdtemp()) / "my-cli.toml"
config.write_text(textwrap.dedent("""
    [my-cli]
    _prepend_subcommands = ["debug"]
"""))
result = invoke(my_cli, args=["--config", str(config), "sync"])
assert result.exit_code == 0
assert result.stdout.index("Debug mode activated") < result.stdout.index("Syncing")
```

### `_default_subcommands` with `_prepend_subcommands`

When both keys are set and no CLI subcommands are given, `_default_subcommands` fires first, then `_prepend_subcommands` is prepended. The result is `[*prepend, *defaults]`:

```toml
[my-cli]
_default_subcommands = ["sync"]
_prepend_subcommands = ["debug"]
```

```{click:run}
import tempfile, textwrap
from pathlib import Path

config = Path(tempfile.mkdtemp()) / "my-cli.toml"
config.write_text(textwrap.dedent("""
    [my-cli]
    _default_subcommands = ["sync"]
    _prepend_subcommands = ["debug"]
"""))
result = invoke(my_cli, args=["--config", str(config)])
assert result.exit_code == 0
assert result.stdout.index("Debug mode activated") < result.stdout.index("Syncing")
```

When CLI subcommands are given explicitly, `_default_subcommands` is ignored but `_prepend_subcommands` still applies:

```{click:run}
import tempfile, textwrap
from pathlib import Path

config = Path(tempfile.mkdtemp()) / "my-cli.toml"
config.write_text(textwrap.dedent("""
    [my-cli]
    _default_subcommands = ["sync"]
    _prepend_subcommands = ["debug"]
"""))
result = invoke(my_cli, args=["--config", str(config), "backup"])
assert result.exit_code == 0
assert result.stdout.index("Debug mode activated") < result.stdout.index("Backing up /tmp")
assert "Syncing" not in result.stdout
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
.. autoclasstree:: click_extra.config.builtin
   :strict:

.. automodule:: click_extra.config.builtin
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclasstree:: click_extra.config.option
   :strict:

.. automodule:: click_extra.config.option
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
