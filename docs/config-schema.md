# {octicon}`checklist` Configuration schema

By default, `ConfigOption` only feeds configuration values that match CLI options into the context's `default_map`. All other keys are silently ignored. This works when the configuration file mirrors the CLI, but some applications need *additional* configuration that matches no CLI option.

The `config_schema` parameter extracts the app's configuration section, normalizes its keys, and produces a typed object available to all commands via `ctx.meta["click_extra.tool_config"]`.

```{tip}
[repomatic](https://kdeldycke.github.io/repomatic/) is a production CLI that uses all of the features below: a [48-field Config dataclass](https://kdeldycke.github.io/repomatic/configuration.html) with nested sub-dataclasses, opaque dict fields for GitHub Actions matrices, `config_path` metadata for kebab-case TOML keys, and a schema-only section (`included_params=()`) so unknown keys warn. It can serve as a reference for building complex typed configuration.
```

## Dataclass schema

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

## Callable schema

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

## Retrieving the config object

The typed configuration is stored in `ctx.meta["click_extra.tool_config"]` and can be accessed in two ways:

```python
# Via the convenience helper (uses current context by default):
from click_extra.config import get_tool_config

config = get_tool_config()

# Or directly from the context:
config = ctx.find_root().meta.get("click_extra.tool_config")
```

If no `config_schema` was set, `get_tool_config()` returns `None`. When a `config_schema` is configured but no configuration file is found, the schema is instantiated with its defaults so `get_tool_config()` always returns a usable object.

## Format-agnostic

The `config_schema` feature works with every format `ConfigOption` supports. The parsed configuration is normalized into a Python dict before the schema is applied, so the same schema works regardless of the source format.

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

## Key normalization

Configuration formats commonly use kebab-case (`extra-categories`), while Python identifiers use snake_case (`extra_categories`). The `normalize_config_keys` utility handles this conversion recursively:

```python
from click_extra.config import normalize_config_keys

raw = {"extra-categories": ["a", "b"], "nested-section": {"sub-key": 1}}
normalized = normalize_config_keys(raw)
# {"extra_categories": ["a", "b"], "nested_section": {"sub_key": 1}}
```

For dataclass schemas, this normalization is applied automatically. For callable schemas, call `normalize_config_keys` explicitly if needed.

## Nested configuration sections

TOML and YAML configurations often group related settings under sub-tables (like `[tool.myapp.dependency-graph]`{l=toml}). When using a dataclass schema, Click Extra automatically flattens these nested sections by joining parent and child keys with `_`, so they map directly to flat dataclass fields:

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

## Type-aware flattening

By default, `flatten_config_keys` recurses into every nested dict. This breaks fields typed as `dict[str, X]` where the dict keys are data rather than config structure (for example, GitHub Actions matrix axis names like `os` or `python-version`).

When using a dataclass schema, Click Extra inspects field type hints and automatically stops flattening at `dict`-typed field boundaries: the same extension-point detection covered in [Extending validation](config-validation.md#extending-validation), seen from the flattening pipeline's side. The dict value is assigned whole to the matching field:

```python
from dataclasses import dataclass, field


@dataclass
class AppConfig:
    simple_value: str = ""
    matrix_axes: dict[str, list[str]] = field(default_factory=dict)
```

```{code-block} toml
:caption: Dict-typed fields are kept intact, not flattened.
[my-app]
simple-value = "hello"

[my-app.matrix-axes]
python-version = ["3.12", "3.13"]
os = ["ubuntu", "macos"]
```

Here `matrix_axes` receives `{"python_version": ["3.12", "3.13"], "os": ["ubuntu", "macos"]}` as a single dict, rather than being split into `matrix_axes_python_version` and `matrix_axes_os`. The pipeline calls this passthrough behavior internally: each extension path is added to an *opaque keys* set that `normalize_config_keys` and `flatten_config_keys` consult before recursing.

Both helpers accept an `opaque_keys` parameter for manual control, useful when working with raw config dicts outside the schema pipeline:

```python
from click_extra.config import flatten_config_keys

conf = {"matrix": {"replace": {"os": {"old": "new"}}, "count": 3}}
flatten_config_keys(conf, opaque_keys=frozenset({"matrix_replace"}))
# {"matrix_replace": {"os": {"old": "new"}}, "matrix_count": 3}
```

## Field metadata

Dataclass fields can carry metadata to control how their values are extracted from the raw config:

- **`click_extra.config_path`** (alias: {py:data}`~click_extra.config.schema.CONFIG_PATH_METADATA_KEY`): A dotted TOML path (like `"test-matrix.replace"`). The value is extracted directly from the raw config before normalization and flattening, bypassing the standard pipeline.

- **`click_extra.normalize_keys`** (alias: {py:data}`~click_extra.config.schema.NORMALIZE_KEYS_METADATA_KEY`): Set to `False` to skip key normalization on the extracted value. Useful when the value contains keys that are external identifiers (for example, GitHub Actions axis names like `python-version`) that must not be converted to `python_version`.

- **`click_extra.extension`** (alias: {py:data}`~click_extra.config.schema.EXTENSION_METADATA_KEY`): Set to `True` to declare the field as an [extension point](config-validation.md#extending-validation). The sub-tree at that field becomes a passthrough: strict-check skips it, the flatten pipeline treats it as opaque, and a registered `ConfigValidator` (or your own code) takes over its validation. Equivalent to typing the field as `dict[str, X]`; use the metadata form when the field's runtime type isn't a mapping.

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

## Nested dataclass schemas

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

## Schema validation

By default, configuration keys that don't match any dataclass field are ignored: the section may legitimately mix CLI parameter keys with schema fields, so an unrecognized key is not necessarily a typo. Two mechanisms tighten this:

- When the section is schema-only (`included_params=()`, so no CLI parameter is merged from it), any unknown key can only be a typo: lax mode then logs a warning naming it, while still loading the known fields.
- The `schema_strict` parameter goes further and reports a validation error, catching typos and stale configuration entries:

```python
@group(config_schema=AppConfig, schema_strict=True)
def my_app(): ...
```

Or directly on the config option:

```python
@config_option(config_schema=AppConfig, schema_strict=True)
```

When `schema_strict=True`, an unrecognized key stops the run with a critical-level log and exit code 1. The message lists both the unrecognized keys and all valid options:

```text
Configuration validation error: Unknown configuration option(s): typo_field. Valid options: known_field, output_format
```

```{note}
`schema_strict` is separate from the existing `strict` parameter. `strict` controls whether config keys that don't match CLI parameters are rejected; `schema_strict` validates against dataclass fields instead. The two can be used independently, and both report through the same `ValidationError` type (see [Error reporting](config-validation.md#error-reporting)).
```

## Coerce a config dict into a dataclass

When you load configuration yourself (or expose a `[tool.<name>]` section consumers fill in), `make_schema_callable(MyDataclass)` returns a callable that turns a raw dict into a validated `MyDataclass` instance. It is the same machinery `config_option` and `get_tool_config` use under the hood: hyphenated keys are normalized to field names, dotted `click_extra.config_path` field metadata is honored, and nested dataclasses are coerced recursively.

```python
from dataclasses import dataclass
from click_extra import make_schema_callable


@dataclass
class Forecast:
    city: str = "paris"
    high_c: int = 0


load = make_schema_callable(Forecast)
load({"city": "lyon", "high-c": 21})  # Forecast(city="lyon", high_c=21)
```

Pass `strict=True` to reject keys that match no field. A non-dataclass callable (a Pydantic `.model_validate`, say) is returned unchanged, and `None` passes through.

## `click_extra.config.schema` API

```{eval-rst}
.. autoclasstree:: click_extra.config.schema
   :strict:

.. automodule:: click_extra.config.schema
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
