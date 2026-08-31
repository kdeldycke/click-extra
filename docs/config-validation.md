# {octicon}`verified` Configuration validation

By default every unrecognized key is ignored. The options below reject it instead, check a file before it is used, and let an application validate the sub-trees Click Extra knows nothing about.

## Strictness

As the [standalone option example](config.md#standalone-option) shows, all unrecognized content is ignored. To reject it instead, use the `strict` argument.

Given this `cli.toml` file:

```{code-block} toml
:caption: `cli.toml`
:emphasize-lines: 3
[cli]
int_param = 3
random_param = "forbidden"
```

With `strict=True` on the CLI below:

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

the CLI stops on the unrecognized `random_param` value before the command runs:

```{code-block} shell-session
:emphasize-lines: 3
$ cli --config "cli.toml"
Load configuration matching cli.toml
Configuration validation error: Unknown configuration key 'random_param'.
```

The error is reported at critical level and the process exits with code 1, the same failure mode as [`--validate-config`](#validating-configuration-files) and the [extension validators](#extending-validation). All three share the single `ValidationError` type.

A parameter deliberately kept out of configuration files (see [Excluding parameters](config.md#excluding-parameters)) is reported with a dedicated message, so users are not led to believe the option does not exist:

```{code-block} shell-session
Configuration validation error: Configuration key 'version' is not allowed in configuration files.
```

The strict check only polices the app's own section: other tools' sections in a shared file (like the `[tool.*]` tables of a `pyproject.toml`, or a multi-app configuration file) are ignored.

On the default `@command` and `@group` decorators, activate strict mode with the `config_strict` keyword instead of replacing the whole default parameter list:

```{code-block} python
from click_extra import command

@command(config_strict=True)
def cli(): ...
```

```{tip}
If you want to check a configuration file for unrecognized keys without running the CLI, see the [`--validate-config` option](#validating-configuration-files) below.
```

```{tip}
Strict mode rejects every key it doesn't recognize as a CLI flag, which is the right default for most apps but breaks sub-tables whose keys are *data* rather than flag names (per-plugin overrides, matrix axes, user-defined IDs). The [Extending validation](#extending-validation) section covers how to declare such sub-trees as passthrough and route them to your own validator.
```

## Validating configuration files

The `@validate_config_option` decorator adds a `--validate-config LOCATION` option that checks whether a configuration file is well-formed and contains only recognized parameters, then exits. This is useful for CI pipelines, editor integrations, or simply verifying a configuration file before deploying it.

`LOCATION` is the same value `--config` takes: a file, a folder, a [glob pattern](config-discovery.md#custom-pattern) or a [remote URL](config-discovery.md#remote-url). Both options hand it to the same reader, so a configuration your CLI can load is one it can also validate.

Reusing the [standalone option example](config.md#standalone-option):

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
Configuration validation error: Unknown configuration key 'unknown_key'.
$ echo $?
1
```

An unparsable file produces exit code 2:

```{code-block} shell-session
:emphasize-lines: 2,4
$ my-cli --validate-config garbage.txt
Error parsing garbage.txt as TOML, YAML, JSON, INI, XML, plist, SQLite, Argfile or pyproject.toml.
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

## Extending validation

`--validate-config` and the runtime strict check both speak the language of CLI parameters: every recognized key must correspond to a flag on the command tree. That works for configurations that mirror the CLI one-to-one, but breaks the moment your app declares its own sub-tables whose keys are *data*, not flag names. The user-defined IDs under `[my-cli.managers.<id>]`, the matrix axes in `[my-cli.test-matrix.<axis>]`, the plugin names in `[my-cli.plugins.<plugin>]`: none of these are CLI options, so click-extra's strict mode rightfully refuses to accept them.

Click-extra's answer is to declare such sub-tables as **extension points**. Each extension point names a dotted path in the app's configuration section and pairs with a {py:class}`~click_extra.config.schema.ConfigValidator` that owns the validation logic for it. Click-extra's machinery treats the path as a passthrough: the strict check skips it, the dataclass schema doesn't descend into it, and the contents arrive at the app's validator verbatim. The result is one validation surface that covers both halves: click-extra checks the CLI-flag-bound keys, the app checks its own extension content, and `--validate-config` reports every failure with the same path-rooted error type.

```{tip}
Three terms describe the same mechanism from three angles, and you'll see all of them in this documentation and in the click-extra source:

- **Extension** is what the *app* does: declare a sub-tree that lives outside click-extra's schema and validate it through your own logic. This is the public-facing name (`ConfigValidator`, `EXTENSION_METADATA_KEY`).
- **Passthrough** is what *click-extra* does: let the extension sub-tree flow through the strict-check, normalize, and flatten stages without inspection. Use this term when describing how data moves through the pipeline.
- **Opaque** is what the *pipeline* sees: a path it must not descend into. The internal helpers (`_collect_opaque_paths_from_schema`, the `opaque_keys` parameter on `normalize_config_keys`/`flatten_config_keys`, the `_opaque_paths` cache on `ConfigOption`) all use this term. Same set of paths, viewed from the inside.

All three vocabularies refer to the same dotted-path set. *Extension* is what you write in your app code, *passthrough* is what you'd say to explain the behavior, *opaque* is what you'll search for when reading click-extra's source.
```

### Declaring an extension point

The most ergonomic way is to add a `dict[str, X]`-typed field to your dataclass schema. Click-extra recognizes mapping-typed fields automatically and treats them as extension points without further annotation:

```{code-block} python
:emphasize-lines: 7
from dataclasses import dataclass, field

@dataclass
class AppConfig:
    """Schema for my-cli."""
    verbose: bool = False
    managers: dict[str, dict] = field(default_factory=dict)
```

The `managers` field is now an extension point at the dotted path `managers` (relative to the app's section). A configuration like:

```{code-block} toml
[my-cli]
verbose = true

[my-cli.managers.winget]
search_path = ["C:\\Program Files\\WindowsApps"]

[my-cli.managers.brew]
timeout = 600
```

passes through both the CLI-flag strict check (which sees `verbose` and ignores everything under `managers`) and the schema's typed instantiation (which receives `managers` as a single dict, not flattened into `managers_winget_search_path` etc.).

When the underlying Python type isn't a mapping (for example, a nested dataclass that still represents extension content), mark the field explicitly with {py:data}`~click_extra.config.schema.EXTENSION_METADATA_KEY`:

```{code-block} python
:emphasize-lines: 1,7
from click_extra import EXTENSION_METADATA_KEY

@dataclass
class AppConfig:
    plugins: list = field(
        default_factory=list,
        metadata={EXTENSION_METADATA_KEY: True},
    )
```

The metadata flag and the `dict[str, X]` type hint are interchangeable for declaring opacity. Use whichever matches your schema's natural shape.

### Registering a validator

A {py:class}`~click_extra.config.schema.ConfigValidator` binds an `extension_path` to a callable that inspects the sub-tree and raises {py:class}`~click_extra.config.schema.ValidationError` on failure. Pass a tuple of validators through the `config_validators=` kwarg on `@group` or `@config_option`:

```{code-block} python
:emphasize-lines: 14-23,33-39
from dataclasses import dataclass, field

from click_extra import (
    ConfigValidator,
    ValidationError,
    config_option,
    group,
    option,
)

ALLOWED_KEYS = frozenset({"timeout", "search_path"})


def validate_managers(section: dict) -> None:
    """Lint the [my-cli.managers.<id>] sub-tree."""
    for manager_id, fields in section.items():
        for key in fields:
            if key not in ALLOWED_KEYS:
                raise ValidationError(
                    f"{manager_id}.{key}",
                    f"unknown field {key!r}",
                    code="unknown_field",
                )


@dataclass
class AppConfig:
    managers: dict[str, dict] = field(default_factory=dict)


@group(
    config_schema=AppConfig,
    config_validators=(
        ConfigValidator(
            extension_path="managers",
            validator=validate_managers,
            description="Validate per-manager override blocks.",
        ),
    ),
)
@option("--verbose/--quiet")
def my_cli(verbose):
    """An app that validates its own extension sub-tree."""
```

The validator receives the value at `app_section[extension_path]` (the contents of `[my-cli.managers]`, in this example) already extracted from the file. It's a pure function: no side effects, no `click.echo`, no `sys.exit`. Click-extra runs it both during `--validate-config` (where every error is collected and reported before exit) and during normal `--config` loading (where the first error fails the run with a clean exit code).

`ValidationError` carries a dotted `path` and a `message`. Validators raise with paths relative to their extension sub-tree:

```python
raise ValidationError("winget.unknown_field", "unknown field 'unknown_field'")
```

Click-extra re-anchors the path against the configuration file root before surfacing the error, so the user sees `my-cli.managers.winget.unknown_field` regardless of where in the schema the validator lives.

### Validator-only extension paths

A `ConfigValidator` registration *also* declares the extension path: even without a corresponding dataclass field, the path is added to click-extra's opaque set and the strict check skips it. This lets you opt sub-trees out of strict mode without touching the schema:

```{code-block} python
:emphasize-lines: 4-7
@group(
    strict=True,
    config_validators=(
        ConfigValidator(
            extension_path="plugins",
            validator=accept_anything,
        ),
    ),
)
def my_cli(): ...
```

Now `[my-cli.plugins.*]` content passes through to `accept_anything`, even though `plugins` isn't a field on any schema. Useful for plugin systems where the set of sub-paths isn't known when the CLI is defined.

### Error reporting

`--validate-config` runs the full pipeline and collects every error before exiting:

```{code-block} shell-session
:emphasize-lines: 2-3
$ my-cli --validate-config bad.toml
Configuration validation error: Unknown configuration key 'unknown_flag'.
Configuration validation error: my-cli.managers.winget.bad_key: unknown field 'bad_key'
$ echo $?
1
```

Normal `--config` loading is fail-fast: the first `ValidationError` becomes a critical-level log message and the run exits 1, before any subcommand callback fires. Both modes go through the same pipeline, so an unknown CLI-flag key, an unknown schema field (under `schema_strict`), and an extension-validator failure all surface as the same `ValidationError`, whichever sub-tree the offending key sits in.

```{note}
The internal name for an extension path is `opaque_path`. You'll see it in click-extra's source under `_collect_opaque_paths_from_schema`, in the `opaque_keys` parameter of `normalize_config_keys` and `flatten_config_keys`, and in the cached `ConfigOption._opaque_paths` attribute. From the pipeline's point of view those paths are stop markers: places it must not descend into. From your app's point of view they're extension points. The vocabulary divergence is intentional: developers reading their own code see *extension* (intent); developers reading click-extra's source see *opaque* (implementation).
```

### Validating programmatically

Both `--validate-config` and the runtime strict check are built on top of a single primitive, {py:func}`~click_extra.config.schema.run_config_validation`. It runs all three stages (the CLI-parameter strict check, the typed schema build, and every registered `ConfigValidator`) in one pass and returns a {py:class}`~click_extra.config.schema.ValidationReport`. Reach for it when you want to validate a parsed configuration document outside Click's option callbacks: a pre-flight check in a deployment script, a custom subcommand that lints config files, or a test harness.

```{code-block} python
from dataclasses import dataclass, field

from click_extra import run_config_validation

@dataclass
class Forecast:
    city: str = ""
    stations: dict[str, dict] = field(default_factory=dict)

report = run_config_validation(
    {"weather": {"city": "Oslo", "stations": {"north": {"altitude": 12}}}},
    app_name="weather",
    params_template=None,
    config_schema=Forecast,
)
```

The report exposes the typed instance, the extracted extension sub-trees, and every error found:

- `report.ok` is `True` when no error was detected.
- `report.schema_instance` holds the built `Forecast(city="Oslo", stations={"north": {"altitude": 12}})`, or `None` when no schema is configured.
- `report.opaque_subtrees` maps each extension path to its sub-tree, here `{"stations": {"north": {"altitude": 12}}}`.
- `report.errors` is a tuple of {py:class}`~click_extra.config.schema.ValidationError`, empty on success.

Pass `params_template=None` to skip the CLI-parameter strict check (useful for a schema-only validation), or the command's template to enable it. `collect_all=True` (the default) gathers every error so a single run yields the full punch list; `collect_all=False` stops at the first failure.

### Built-in extension points

Click-extra auto-registers one extension point on every `ConfigOption`:

- **`themes`**: `[<cli>.themes.<name>]` tables override existing palettes or define new ones. Validated by {py:func}`~click_extra.theme.validate_themes_config`; loaded into `ctx.meta` by {py:meth}`ConfigOption._apply_theme_overrides <click_extra.config.option.ConfigOption._apply_theme_overrides>`. See [Themes from your `--config` file](theme.md#themes-from-your-config-file) for the schema and behavior.

App-supplied `ConfigValidator`s on the same `extension_path` run alongside the built-in: both validators are called, both sets of errors surface.
