# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""Schema-building and validation engine behind config_option and --validate-config."""

from __future__ import annotations

import ast
import copy
import inspect
import logging
import sys
import textwrap
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import (
    MISSING,
    Field,
    dataclass,
    fields as dc_fields,
    is_dataclass,
)
from functools import cache, partial
from typing import NamedTuple, get_origin, get_type_hints

from click import get_current_context

from .. import context
from .._utils import set_nested
from ..param_tools import PARAM_PATH_SEP, canonical_param_name

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    import click

logger = logging.getLogger(__name__)


DEFAULT_SUBCOMMANDS_KEY = "_default_subcommands"
"""Reserved configuration key for specifying default subcommands.

When a group is invoked without explicit subcommands on the CLI, the subcommands
listed under this key execute automatically in order. CLI always wins: if the user
names subcommands explicitly, the config is ignored.

Example TOML configuration:

```{code-block} toml

[my-cli]
_default_subcommands = ["backup", "sync"]

[my-cli.backup]
path = "/home"
```
"""

PREPEND_SUBCOMMANDS_KEY = "_prepend_subcommands"
"""Reserved configuration key for prepending subcommands to every invocation.

Unlike `_default_subcommands` which only fires when no subcommands are given on the
CLI, `_prepend_subcommands` always prepends the listed subcommands. This is useful
for always injecting a `debug` subcommand on a dev machine, for example.

Only works with `chain=True` groups (non-chained groups resolve exactly one
subcommand, so prepending would break the user's intended command).

Example TOML configuration:

```{code-block} toml

[my-cli]
_prepend_subcommands = ["debug"]
```
"""

_RESERVED_CONFIG_KEYS = frozenset({DEFAULT_SUBCOMMANDS_KEY, PREPEND_SUBCOMMANDS_KEY})
"""Configuration keys with special meaning that should not be treated as parameters."""


EXTENSION_METADATA_KEY = "click_extra.extension"
"""Dataclass field metadata flag marking a field as an *extension point*.

Schema authors set ``metadata={EXTENSION_METADATA_KEY: True}`` on a field when
its sub-tree should pass through click-extra's CLI-parameter strict check and
be validated by app-specific logic instead. Equivalent to typing the field as
`dict[str, X]`: both forms are recognized by
`_collect_opaque_paths_from_schema` (the internal pipeline calls these paths
*opaque*, as its normalize, flatten and strict stages skip them). The metadata
form is useful when the underlying Python type is something other than a `dict`
(for example, a nested dataclass that represents user-extensible content)."""


CONFIG_PATH_METADATA_KEY = "click_extra.config_path"
"""Dataclass field metadata key pinning a field to an explicit config sub-path.

Schema authors set ``metadata={CONFIG_PATH_METADATA_KEY: "test-suite"}`` on a
field so the dataclass loader (`_from_dataclass`) reads its value from that
dotted path under the app's configuration section, rather than from a key named
after the field. The named counterpart to `EXTENSION_METADATA_KEY`."""


NORMALIZE_KEYS_METADATA_KEY = "click_extra.normalize_keys"
"""Dataclass field metadata key toggling key normalization on a field's value.

Defaults to `True`. Schema authors set
``metadata={NORMALIZE_KEYS_METADATA_KEY: False}`` to keep a sub-tree's keys
verbatim, so external identifiers (like `python-version` axis names) are not
rewritten to Python-style names (`python_version`). Read by
`_from_dataclass` alongside `CONFIG_PATH_METADATA_KEY`."""


class ValidationError(ValueError):
    """Raised when a configuration file fails validation.

    A single, structured exception type that uniformly carries the dotted
    `path` of the offending key, a human-readable `message`, and an optional
    `code` for programmatic handling. Used by click-extra's built-in
    strict-mode check and by every user-registered {class}`ConfigValidator`, so
    downstream apps and `--validate-config` see the same error shape regardless
    of who detected the problem.

    Click-extra raises it with one of these codes, all spelled in snake case:

    - `invalid_key`: a dotted key conflicts with another key, or has an empty
      segment, or a key is not a string.
    - `invalid_theme`: a `[tool.<cli>.themes.<name>]` table builds no theme, like
      one naming a slot no theme has.
    - `invalid_theme_shape`: a `[tool.<cli>.themes.<name>]` entry is not a table.
    - `schema_error`: the configuration schema rejects the section.
    - `unknown_parameter`: a key matches no CLI parameter, or one excluded from
      configuration files.

    :param path: Dotted path to the offending key, relative to the configuration
        file root (like `"my-cli.managers.winget.cli_searchpath"`). An empty
        string means the error applies to the document as a whole.
    :param message: Human-readable description of the failure. Should be a
        single sentence, no trailing punctuation, no path repeated.
    :param code: Optional machine-readable error code (like `"unknown_field"`)
        for callers that want to dispatch on error type without parsing the
        message string.
    """

    def __init__(
        self,
        path: str,
        message: str,
        code: str | None = None,
    ) -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.path = path
        self.message = message
        self.code = code


@dataclass(frozen=True)
class ConfigValidator:
    """Register an app-defined *extension* validator for one sub-tree of the
    configuration file.

    Apps register validators via the `config_validators=` kwarg on
    {class}`~click_extra.config.option.ConfigOption` (or the matching decorator) to extend click-extra's
    built-in CLI-parameter strict check with custom validation logic. Each
    validator targets a single dotted `extension_path` relative to the app's
    configuration section. Click-extra passes the matching sub-tree straight
    through to the registered validator: the strict check skips it, the schema
    machinery treats it as opaque, and the user's logic owns the result. The
    validator runs both during `--validate-config` and during normal config
    loading.

    :param extension_path: Dotted path of the sub-tree the validator owns,
        relative to the app's section in the configuration file. For example, an
        app named `my-cli` with `extension_path="managers"` receives the
        contents of the `[my-cli.managers]` table.
    :param validator: Callable taking the sub-tree dict and raising
        {class}`ValidationError` on failure. Must be a pure function: no side
        effects on the click context, no print statements. The caller decides
        how to surface the error.
    :param description: Optional human-readable summary of what the validator
        checks, for documentation generators that introspect the registration.
    """

    extension_path: str
    validator: Callable[[dict[str, Any]], None]
    description: str = ""


def _strip_reserved_keys(conf: dict) -> dict:
    """Recursively return a copy of *conf* with reserved keys removed at every level."""
    return {
        key: _strip_reserved_keys(value) if isinstance(value, dict) else value
        for key, value in conf.items()
        if key not in _RESERVED_CONFIG_KEYS
    }


def _check_type_conflict(
    target: dict,
    parts: list[str],
    new_value: object,
    label: str,
    strict: bool,
) -> None:
    """Walk *parts* into *target* and warn on scalar/dict mismatches.

    Checks every level (intermediate and leaf) so that deep conflicts like
    ``{"a.b.c": 1, "a.b": 2}`` are caught.

    :raises ValidationError: in strict mode, instead of logging a warning.
    """
    node = target
    for i, part in enumerate(parts):
        if part not in node:
            return
        existing = node[part]
        is_last = i == len(parts) - 1
        conflict = (
            # Leaf: flag when one side is a dict and the other is not.
            is_last and isinstance(existing, dict) != isinstance(new_value, dict)
        ) or (
            # Intermediate segment: the new value expects a dict here.
            not is_last and not isinstance(existing, dict)
        )
        if conflict:
            msg = (
                f"Configuration key {label!r} conflicts with "
                f"{'.'.join(parts[: i + 1])!r}: "
                f"mixing scalar and nested values."
            )
            if strict:
                raise ValidationError("", msg, code="invalid_key")
            logger.warning(f"{msg} Last value wins.")
            return
        if is_last:
            return
        node = existing


def _expand_dotted_keys(conf: dict, strict: bool = False) -> dict:
    """Expand dotted keys into nested dicts, then deep-merge.

    Allows configuration files to mix flat dot-notation and nested structures:

    ```{code-block} python
    {"subcommand.option_a": 1, "subcommand": {"option_b": 2}}
    ```

    becomes:

    ```{code-block} python
    {"subcommand": {"option_a": 1, "option_b": 2}}
    ```

    Recurses into nested dicts so dotted keys at any level are expanded.

    In non-strict mode, logs a warning when a key resolves to both a scalar
    and a dict (like ``{"a": 1, "a.b": 2}``), as one value will silently
    override the other, and skips a dotted key with an empty segment.

    A key that is not a string, like the number YAML reads `1:` as, holds no dot
    and is kept as it is: {func}`_merge_into_template` reports it.

    :raises ValidationError: in strict mode, on type conflicts and on dotted keys
        with an empty segment.
    """
    expanded: dict = {}
    for key, value in conf.items():
        if isinstance(value, dict):
            value = _expand_dotted_keys(value, strict=strict)
        if isinstance(key, str) and "." in key:
            parts = key.split(".")
            if not all(parts):
                msg = f"Configuration key {key!r} contains empty segments."
                if strict:
                    raise ValidationError("", msg, code="invalid_key")
                logger.warning(f"Ignoring {msg.lower()}")
                continue
            _check_type_conflict(expanded, parts, value, key, strict)
            set_nested(expanded, parts, value)
        else:
            _check_type_conflict(expanded, [key], value, key, strict)
            set_nested(expanded, (key,), value)
    return expanded


def _merge_into_template(
    template: dict[str, Any],
    conf: dict[Any, Any],
    strict: bool = False,
    blocked: frozenset[str] = frozenset(),
    exempt: frozenset[tuple[str, ...]] = frozenset(),
    _path: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Merge *conf* into *template* in place, bounded by the template's structure.

    Like a recursive {meth}`dict.update` restricted to the keys already present
    in *template*. A key absent from the template is retried twice, so every
    spelling Click could have derived a parameter name from reaches that
    parameter:

    1. with hyphens replaced by underscores, so the kebab-case conventional in
       TOML and YAML files (`hash-body`) reaches `hash_body`;
    2. with {func}`~click_extra.param_tools.canonical_param_name`, which also
       folds case, so `Hash-Body` and `HASH_BODY` reach it too.

    The second retry matches on the folded form but resolves to the template's
    own key, never to the folded one. A parameter Click named from an
    identifier declaration keeps its case (`@option("--x", "Foo_Bar")`), and
    the template stays the authority on how it is spelled. When two template
    keys fold together, nothing tells them apart and the key is skipped with a
    warning.

    When two spellings of the same key coexist (`hash-body` and
    `hash_body`), the last one wins and a warning names both.

    Keys matching nothing in the template are silently ignored, unless `strict`
    is `True`. The error message tells parameters deliberately blocked from
    configuration files (their fully-qualified IDs passed via `blocked`) from
    keys matching no CLI parameter at all.

    A key that is not a string, like the number YAML reads `1:` as, matches no
    parameter either. Strict mode rejects it as an invalid key, and lax mode
    skips it with a warning.

    :param blocked: fully-qualified parameter IDs excluded from configuration
        files, used only to sharpen strict-mode error messages.
    :param exempt: paths of the keys strict mode accepts although they match no
        parameter, like the keys a configuration schema reads. Each path holds
        the keys from the root of `conf` down to the key.
    :param _path: internal accumulator tracking the qualified path of the
        level being merged. Callers should not set this.
    :raises ValidationError: in strict mode, on a key matching no parameter, or
        on a key that is not a string.
    """
    # Index the template by the folded form of each of its keys, so a config
    # key can be resolved on the name Click would have derived from it. The
    # index answers with the template's own spelling: a parameter Click named
    # from an identifier declaration keeps its case, which no fold produces.
    folded: dict[str, list[str]] = {}
    for template_key in template:
        folded.setdefault(canonical_param_name(template_key), []).append(template_key)

    spellings: dict[str, str] = {}
    for key, value in conf.items():
        if not isinstance(key, str):
            message = f"Configuration key {key!r} is not a string."
            if strict:
                raise ValidationError("", message, code="invalid_key")
            logger.warning(f"{message} Ignoring it.")
            continue
        target_key = key
        if target_key not in template:
            normalized = key.replace("-", "_")
            if normalized in template:
                target_key = normalized
            else:
                candidates = folded.get(canonical_param_name(key), [])
                if len(candidates) == 1:
                    target_key = candidates[0]
                elif candidates:
                    logger.warning(
                        f"Configuration key {key!r} matches {candidates!r} once "
                        "folded, and is skipped: no spelling tells them apart."
                    )
        if target_key in template:
            if target_key in spellings:
                logger.warning(
                    f"Configuration keys {spellings[target_key]!r} and {key!r} "
                    f"both resolve to {target_key!r}. Last value wins."
                )
            spellings[target_key] = key
            if isinstance(value, dict) and isinstance(template[target_key], dict):
                template[target_key] = _merge_into_template(
                    template[target_key],
                    value,
                    strict=strict,
                    blocked=blocked,
                    exempt=exempt,
                    _path=(*_path, target_key),
                )
            else:
                template[target_key] = value
        elif strict and (*_path, key) not in exempt:
            qualified = PARAM_PATH_SEP.join((*_path, key.replace("-", "_")))
            message = (
                f"Configuration key {key!r} is not allowed in configuration files."
                if qualified in blocked
                else f"Unknown configuration key {key!r}."
            )
            raise ValidationError("", message, code="unknown_parameter")
    return template


def _scope_app_sections(
    conf: dict[str, Any],
    app_name: str,
    fallback_sections: Sequence[str] = (),
    warn: bool = True,
) -> dict[str, Any]:
    """Reduce a parsed config document to the app's own section.

    Returns ``{app_name: section}`` where the section is resolved by
    {func}`_select_app_section` (so legacy `fallback_sections` are honored,
    with their deprecation warning), or an empty dict when the document holds
    no section for the app. An empty `app_name` returns `conf` unchanged: the
    section is then the document itself.

    Foreign sections are dropped: a shared configuration file (like a
    `pyproject.toml` carrying other tools' `[tool.*]` tables, or a global
    config file with several apps' sections) must not trip the CLI-parameter
    strict check over keys that were never addressed to this app.
    """
    if not app_name:
        return conf
    section = _select_app_section(conf, app_name, fallback_sections, warn=warn)
    if not section:
        return {}
    return {app_name: section}


def normalize_config_keys(
    conf: dict[str, Any],
    opaque_keys: frozenset[str] = frozenset(),
    _prefix: str = "",
) -> dict[str, Any]:
    """Normalize configuration keys to valid Python identifiers.

    Recursively replaces hyphens with underscores in all dict keys, using the
    same `str.replace("-", "_")` transform that Click applies internally when
    deriving parameter names from option declarations (`--foo-bar` becomes
    `foo_bar`).

    Handles the convention mismatch between configuration formats (TOML, YAML,
    JSON all commonly use kebab-case) and Python identifiers. Works with all
    configuration formats supported by `ConfigOption`. A key that is not a
    string, like the number YAML reads `1:` as, is kept as it is.

    :param opaque_keys: Fully-qualified key names (using `"_"` as
        separator) where recursion stops. The key itself is still
        normalized, but its dict value is kept as-is. Used in tandem
        with `flatten_config_keys`'s `opaque_keys` to protect data
        dicts (like GitHub Actions matrix axes) from normalization.
    :param _prefix: Internal parameter for tracking the accumulated key
        path during recursion. Callers should not set this.

    ```{note}
    Click applies the same substitution in `Option._parse_decls` and
    `Argument._parse_decls`, but exposes no public accessor for it, so the
    one-liner is written out here.
    ```
    """
    normalized: dict[str, Any] = {}
    for key, value in conf.items():
        py_key = key.replace("-", "_") if isinstance(key, str) else key
        full_key = f"{_prefix}_{py_key}" if _prefix else py_key
        if isinstance(value, dict) and full_key not in opaque_keys:
            value = normalize_config_keys(value, opaque_keys, full_key)
        normalized[py_key] = value
    return normalized


def flatten_config_keys(
    conf: dict[str, Any],
    sep: str = "_",
    opaque_keys: frozenset[str] = frozenset(),
    _prefix: str = "",
) -> dict[str, Any]:
    """Flatten nested dicts into a single level by joining keys with a separator.

    Useful for mapping nested configuration structures (like TOML sub-tables) to
    flat Python dataclass fields. After normalization with
    `normalize_config_keys`, the flattened keys match dataclass field names
    directly::

        >>> from click_extra.config import (
        ...     flatten_config_keys,
        ...     normalize_config_keys,
        ... )
        >>> raw = {"dependency-graph": {"all-groups": True, "output": "deps.mmd"}}
        >>> flatten_config_keys(normalize_config_keys(raw))
        {'dependency_graph_all_groups': True, 'dependency_graph_output': 'deps.mmd'}

    :param conf: Nested dictionary to flatten.
    :param sep: Separator used to join parent and child keys. Defaults to
        `"_"` which produces valid Python identifiers when combined with
        `normalize_config_keys`.
    :param opaque_keys: Fully-qualified key names where flattening stops.
        When the accumulated key matches an entry in this set, the dict
        value is kept as-is instead of being recursively flattened. This
        is useful for fields typed as `dict[str, X]` where the dict keys
        are data (like GitHub Actions matrix axis names), not config
        structure.
    :param _prefix: Internal parameter for tracking the accumulated key
        path during recursion. Callers should not set this.
    """
    items: dict[str, Any] = {}
    for key, value in conf.items():
        full_key = f"{_prefix}{sep}{key}" if _prefix else key
        if isinstance(value, dict) and full_key not in opaque_keys:
            items.update(flatten_config_keys(value, sep, opaque_keys, full_key))
        else:
            items[full_key] = value
    return items


def get_tool_config(ctx: click.Context | None = None) -> Any:
    """Retrieve the typed tool configuration from the context.

    Returns the object stored under {data}`click_extra.context.TOOL_CONFIG`
    by `ConfigOption` when a `config_schema` is set, or `None` if no
    schema was configured or no configuration was loaded.

    :param ctx: Click context. Defaults to the current context.
    """
    if ctx is None:
        ctx = get_current_context()
    return context.get(ctx, context.TOOL_CONFIG)


class SchemaFieldInfo(NamedTuple):
    """Documentation record for one option of a configuration schema.

    Produced by {func}`schema_field_infos`. Consumed by the `click:config`
    Sphinx directive, and by CLIs building their own configuration reference
    (a `show-config` table, say) from the same introspection.
    """

    key: str
    """Dotted configuration path of the option.

    Field names are kebab-cased (`setup_guide` → `setup-guide`) unless the
    field pins an explicit path through
    {data}`click_extra.config.schema.CONFIG_PATH_METADATA_KEY`. Nested dataclass
    fields contribute one segment per nesting level (`test-suite.timeout`).
    """

    type_hint: str
    """The field's type annotation, as written in the schema source."""

    default: Any
    """The field's default value, taken from a pristine schema instance."""

    summary: str
    """First paragraph of the field's attribute docstring, collapsed onto a
    single line. Empty when the field has no docstring or the class source is
    unavailable (see {func}`field_docstrings`)."""

    description: str
    """Full attribute docstring of the field, paragraph breaks preserved."""


def field_docstrings(cls: type) -> dict[str, str]:
    """Extract attribute docstrings from a class body, keyed by field name.

    Attribute docstrings are string literals immediately following an
    annotated assignment in a class body (the PEP 257 convention used by
    Sphinx's autodoc). Python discards them at runtime, so they are recovered
    by parsing the class source with {mod}`ast`. Each docstring is cleaned up
    with {func}`inspect.cleandoc`, preserving paragraph breaks.

    ```{caution}
    Returns an empty mapping when the class source is unavailable, as for
    classes defined in an `exec`-ed code block (an interactive session,
    or the body of a `click:source` Sphinx directive). Import the schema
    from a real module to get its docstrings documented.
    ```
    """
    try:
        source = inspect.getsource(cls)
    except (OSError, TypeError):
        return {}
    tree = ast.parse(textwrap.dedent(source))
    cls_node = tree.body[0]
    if not isinstance(cls_node, ast.ClassDef):
        return {}

    docstrings: dict[str, str] = {}
    current_field = None
    for node in cls_node.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            current_field = node.target.id
        elif (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            if current_field:
                # cleandoc trims the first line and dedents the rest based on
                # the common indent of subsequent lines (PEP 257), unlike
                # textwrap.dedent which fails when the first line has no
                # leading whitespace but subsequent lines do.
                docstrings[current_field] = inspect.cleandoc(node.value.value)
                current_field = None
        else:
            current_field = None

    return docstrings


def _first_paragraph(text: str) -> str:
    """Collapse the first paragraph of `text` onto a single line."""
    return " ".join(text.split("\n\n", maxsplit=1)[0].split())


def _field_config_key(field: Field) -> str:
    """Return the config key of a dataclass field.

    The {data}`click_extra.config.schema.CONFIG_PATH_METADATA_KEY` metadata wins
    when set; otherwise the field name is kebab-cased
    (`setup_guide` → `setup-guide`).
    """
    path = field.metadata.get(CONFIG_PATH_METADATA_KEY)
    if path:
        return str(path)
    return field.name.replace("_", "-")


def _type_hint_str(field: Field) -> str:
    """Render a dataclass field's type annotation as a string.

    Under PEP 563 (`from __future__ import annotations`) the annotation is
    already the source string. Without it, the annotation is a live object:
    plain classes render as their name, typing generics as their `str()`
    form (`list[str]`).
    """
    hint = field.type
    if isinstance(hint, str):
        return hint
    return getattr(hint, "__name__", None) or str(hint)


def _collect_field_infos(
    cls: type,
    instance: Any,
    prefix: str,
    infos: list[SchemaFieldInfo],
) -> None:
    """Accumulate {class}`SchemaFieldInfo` records for `cls`, recursively.

    Nested dataclass defaults recurse with their key appended to `prefix`;
    only leaf fields produce records, matching how the options surface in the
    configuration file.
    """
    docstrings = field_docstrings(cls)
    for f in dc_fields(cls):
        key = _field_config_key(f)
        full_key = f"{prefix}.{key}" if prefix else key
        value = getattr(instance, f.name)
        if is_dataclass(value) and not isinstance(value, type):
            _collect_field_infos(type(value), value, full_key, infos)
            continue
        description = docstrings.get(f.name, "")
        infos.append(
            SchemaFieldInfo(
                key=full_key,
                type_hint=_type_hint_str(f),
                default=value,
                summary=_first_paragraph(description),
                description=description,
            ),
        )


def schema_field_infos(schema: type) -> list[SchemaFieldInfo]:
    """Walk a configuration schema dataclass into per-option records.

    Introspects the dataclass fields, their type annotations, defaults, and
    attribute docstrings. Nested dataclass fields expand recursively into
    dotted keys (`test-suite.timeout`), honoring
    {data}`click_extra.config.schema.CONFIG_PATH_METADATA_KEY` at every level.
    Records are sorted by key, segment-wise, so a sub-table's options stay
    contiguous even when another table's name shares their prefix
    (`workflow.sync` sorts before `workflow-pins.sync`).

    Defaults are read off a pristine `schema()` instance, so every field
    must carry a default: configuration schemas are default-complete by
    construction, since {func}`make_schema_callable` instantiates them from
    partial user data.

    :raises TypeError: when `schema` is not a dataclass type.
    """
    if not (isinstance(schema, type) and is_dataclass(schema)):
        raise TypeError(
            f"Config schema must be a dataclass type, got {schema!r}.",
        )
    instance = schema()
    infos: list[SchemaFieldInfo] = []
    _collect_field_infos(schema, instance, "", infos)
    return sorted(infos, key=lambda info: info.key.split("."))


@cache
def _resolved_type_hints(cls: type) -> dict[str, Any]:
    """{func}`typing.get_type_hints` of `cls`, cached per class.

    A schema is walked at each configuration load, and resolving the annotation
    strings of a large one dominates the walk. A failed resolution raises, so it
    is never cached: a forward reference resolves on a later call, once the module
    defining it is loaded.

    ```{caution}
    Every caller shares the returned dictionary: read it, never modify it.
    ```
    """
    return get_type_hints(cls)


def _safe_get_type_hints(cls: type) -> dict[str, Any]:
    """Resolve type hints for a class, returning empty dict on failure.

    Wraps {func}`typing.get_type_hints` to handle cases where annotations
    reference types that are not importable in the current context (like
    forward references to types only available under `TYPE_CHECKING`).

    When the initial resolution fails (common for locally-defined classes
    whose annotations are stringified by `from __future__ import annotations`),
    a second attempt is made with a `localns` built from `default_factory`
    values on the class's dataclass fields. This allows nested dataclass types
    like `sub: SubConfig = field(default_factory=SubConfig)` to be resolved even
    when `SubConfig` is not in the module's global scope.
    """
    try:
        return _resolved_type_hints(cls)
    except (NameError, AttributeError, TypeError, RecursionError):
        pass

    # Fallback: build localns from default_factory class references.
    localns: dict[str, Any] = {}
    try:
        for f in dc_fields(cls):
            factory = f.default_factory
            if factory is not MISSING and isinstance(factory, type):
                localns[factory.__name__] = factory
    except (TypeError, AttributeError):
        pass

    if localns:
        try:
            module = sys.modules.get(cls.__module__, None)
            globalns = getattr(module, "__dict__", {}) if module else {}
            return get_type_hints(
                cls,
                globalns=globalns,
                localns=localns,
            )
        except (NameError, AttributeError, TypeError, RecursionError):
            pass

    return {}


def _is_mapping_type(hint: object) -> bool:
    """Check if a resolved type hint is a `dict` or `Mapping`."""
    if hint is None:
        return False
    origin = get_origin(hint)
    return origin is dict or origin is Mapping


def _is_extension_field(field: Field, hint: object) -> bool:
    """Return `True` when a dataclass field is an *extension point*.

    A field qualifies when **either**:

    - it carries ``metadata={EXTENSION_METADATA_KEY: True}`` (explicit marker,
      useful when the Python type is not a mapping), or
    - its resolved type hint is `dict[str, X]` / `Mapping[str, X]` (the user
      controls the keys, not the schema).

    Single source of truth for the per-field extension-point criteria. Both the
    recursive schema walk in {func}`_collect_opaque_paths_from_schema` and the
    flatten-boundary set computed inside {func}`_from_dataclass` route through
    this helper, so a field marked off-limits is opaque to both.
    """
    return bool(field.metadata.get(EXTENSION_METADATA_KEY, False)) or _is_mapping_type(
        hint
    )


def _collect_opaque_paths_from_schema(
    schema: type | Callable[[dict[str, Any]], Any] | None,
    _prefix: str = "",
) -> frozenset[str]:
    """Collect dotted paths of *extension* fields from a dataclass schema.

    Walks the schema recursively. A field qualifies as an extension point (and
    is therefore treated as opaque by the rest of the pipeline) when
    {func}`_is_extension_field` says so.

    The public API calls these paths *extension paths*. The pipeline calls them
    *opaque*, as it must not descend into them: both names refer to the same set.

    Nested dataclass fields are not themselves opaque: the function recurses
    into them, prepending the field name to every collected sub-path.

    The returned set contains dotted paths **relative to the schema root**, not
    the configuration file root. The caller is responsible for prefixing them
    with the app section name (or any other root) before stripping or
    extracting sub-trees from a raw config dict.

    Returns an empty set when `schema` is `None` or not a dataclass, so
    callers can pass any of the values accepted by `config_schema`.
    """
    if schema is None or not is_dataclass(schema):
        return frozenset()

    hints = _safe_get_type_hints(schema)
    paths: set[str] = set()
    for f in dc_fields(schema):
        full_path = f"{_prefix}.{f.name}" if _prefix else f.name
        hint = hints.get(f.name)
        if _is_extension_field(f, hint):
            paths.add(full_path)
        elif is_dataclass(hint) and isinstance(hint, type):
            paths |= _collect_opaque_paths_from_schema(hint, _prefix=full_path)
    return frozenset(paths)


def _collect_opaque_paths(
    schema: type | Callable[[dict[str, Any]], Any] | None,
    validators: Sequence[ConfigValidator],
) -> frozenset[str]:
    """Union the opaque paths from a schema and a set of extension validators.

    Merges the dotted paths {func}`_collect_opaque_paths_from_schema` infers
    from `schema` with every validator's `extension_path`. The result is the
    single set of sub-trees, relative to the app section, that click-extra's
    normalize/flatten/strict machinery must skip. An app can declare an extension
    point through either source (or both, the union is idempotent), so callers
    that need the complete skip set route through this helper instead of
    re-combining the two sources by hand.
    """
    schema_paths = _collect_opaque_paths_from_schema(schema)
    validator_paths = frozenset(v.extension_path for v in validators)
    return schema_paths | validator_paths


def _rooted_path(app_name: str, path: str) -> str:
    """Root a dotted path relative to the app's section at the configuration file.

    An empty `app_name` leaves `path` as it stands: the section is then the
    document itself.
    """
    return f"{app_name}.{path}" if app_name else path


def _strip_opaque_subtrees(
    conf: dict[str, Any],
    opaque_paths: Iterable[str],
) -> dict[str, Any]:
    """Return a shallow-copied *conf* with every opaque sub-tree removed.

    Each path in `opaque_paths` is a dotted location relative to `conf`'s
    root (callers prepend the app section name when needed). Paths that don't
    resolve to anything are silently skipped: a schema may declare an opaque
    field that the user never sets, and that's not an error. The empty path
    is treated as a no-op for the same reason.

    Use to drop user-controlled sub-trees from a normalized configuration
    document before running click-extra's CLI-parameter strict check. The
    sub-trees themselves are not returned: when callers need both the stripped
    document and the extracted sub-trees, they can read them out of the
    original `conf` with {func}`_extract_dotted` before calling this
    helper.
    """
    result = dict(conf)
    for path in opaque_paths:
        if path:
            result = _remove_dotted(result, path)
    return result


def _match_dotted_segment(conf: dict[str, Any], part: str) -> str | None:
    """Resolve a dotted-path segment to the key actually used in *conf*.

    Prefers the exact spelling, then retries with hyphens replaced by
    underscores: a path segment declared in snake_case (`dependency_graph`,
    the Python-identifier form schema fields and validators use) also matches
    the kebab-case spelling conventional in configuration files
    (`dependency-graph`). Returns `None` when neither spelling is present.

    The tolerance stops there, unlike {func}`_merge_into_template`, which
    also folds case. A path addresses a schema field a developer declared, not
    a parameter Click named, so there is no derivation to be faithful to.
    """
    if part in conf:
        return part
    for key in conf:
        if isinstance(key, str) and key.replace("-", "_") == part:
            return key
    return None


def _extract_dotted(conf: dict[str, Any], path: str) -> tuple[Any, bool]:
    """Extract a value at a dotted path from a nested dict.

    Path segments match kebab-case spellings too, see
    {func}`_match_dotted_segment`.

    :param conf: Nested dict to search.
    :param path: Dotted path (like `"test-matrix.replace"`).
    :return: `(value, True)` if found, `(None, False)` otherwise.
    """
    current: Any = conf
    for part in path.split("."):
        if not isinstance(current, dict):
            return None, False
        key = _match_dotted_segment(current, part)
        if key is None:
            return None, False
        current = current[key]
    return current, True


def _remove_dotted(conf: dict[str, Any], path: str) -> dict[str, Any]:
    """Remove a value at a dotted path, returning a modified shallow copy.

    Parent dicts that become empty after removal are also pruned. Path
    segments match kebab-case spellings too, see
    {func}`_match_dotted_segment`.
    """
    head, _, rest = path.partition(".")
    top = _match_dotted_segment(conf, head)
    if top is None:
        return conf
    if rest:
        if not isinstance(conf[top], dict):
            return conf
        sub = _remove_dotted(conf[top], rest)
        if sub:
            return {**conf, top: sub}
    return {k: v for k, v in conf.items() if k != top}


def _apply_nested_schema(
    hint: type | None,
    value: dict[str, Any],
    strict: bool,
    do_normalize: bool = True,
    warn_unknown: bool = False,
) -> Any:
    """Recursively apply a schema callable to a dict value if the hint is a dataclass.

    Falls back to `normalize_config_keys` when the hint is not a dataclass
    but normalization is requested. Returns `value` unchanged otherwise.
    """
    if is_dataclass(hint):
        sub = make_schema_callable(
            hint, strict=strict, normalize=do_normalize, warn_unknown=warn_unknown
        )
        return sub(value) if sub else value
    if do_normalize:
        return normalize_config_keys(value)
    return value


def _from_dataclass(
    schema: type,
    raw: dict[str, Any],
    *,
    strict: bool = False,
    normalize: bool = True,
    warn_unknown: bool = False,
) -> Any:
    """Build a dataclass instance from a raw configuration dict.

    Handles explicit `config_path` metadata, type-aware normalization and
    flattening, nested dataclass recursion, and strict validation (raising in
    strict mode, logging a warning in `warn_unknown` mode). Called by
    `make_schema_callable` for dataclass schemas.
    """
    all_fields = dc_fields(schema)
    known = {f.name for f in all_fields}
    hints = _safe_get_type_hints(schema)

    # --- Phase 1: extract fields with explicit config_path. ---
    result: dict[str, Any] = {}
    remaining = dict(raw)

    for f in all_fields:
        path = f.metadata.get(CONFIG_PATH_METADATA_KEY)
        if path is None:
            continue
        do_normalize = f.metadata.get(NORMALIZE_KEYS_METADATA_KEY, True)
        value, found = _extract_dotted(remaining, path)
        if not found:
            continue
        remaining = _remove_dotted(remaining, path)

        hint = hints.get(f.name)
        if isinstance(value, dict):
            value = _apply_nested_schema(
                hint, value, strict, do_normalize, warn_unknown
            )
        result[f.name] = value

    # --- Phase 2: type-aware normalize + flatten. ---
    # Detect opaque fields, the flatten boundaries the recursion must not cross:
    #   - extension points (mapping-typed or EXTENSION_METADATA_KEY-marked), and
    #   - nested-dataclass-typed fields (Phase 3 hands their intact dict to the
    #     sub-schema callable, so flattening must stop here too).
    # The extension-point half goes through _is_extension_field so this set stays
    # in sync with _collect_opaque_paths_from_schema and honors the metadata
    # marker on non-mapping fields.
    opaque = frozenset(
        f.name
        for f in all_fields
        if f.name not in result
        and (
            _is_extension_field(f, hints.get(f.name)) or is_dataclass(hints.get(f.name))
        )
    )

    normalized = (
        normalize_config_keys(remaining, opaque_keys=opaque) if normalize else remaining
    )
    flattened = flatten_config_keys(normalized, opaque_keys=opaque)

    # --- Phase 3: recursively process nested dataclasses. ---
    for f in all_fields:
        if f.name in result:
            continue
        hint = hints.get(f.name)
        if (
            is_dataclass(hint)
            and f.name in flattened
            and isinstance(flattened[f.name], dict)
        ):
            sub = make_schema_callable(
                hint,  # type: ignore[arg-type]
                strict=strict,
                warn_unknown=warn_unknown,
            )
            flattened[f.name] = sub(flattened[f.name]) if sub else flattened[f.name]

    # --- Phase 4: merge and validate. ---
    for k, v in flattened.items():
        if k in known and k not in result:
            result[k] = v

    if strict or warn_unknown:
        all_keys = set(result) | set(flattened)
        # A key that is not a string, as YAML allows, sorts and reads by its text.
        unknown = sorted(map(str, all_keys - known))
        if unknown:
            msg = (
                f"Unknown configuration option(s): "
                f"{', '.join(unknown)}. "
                f"Valid options: {', '.join(sorted(known))}"
            )
            if strict:
                raise ValueError(msg)
            logger.warning(msg)

    return schema(**{k: v for k, v in result.items() if k in known})


def make_schema_callable(
    schema: type | Callable[[dict[str, Any]], Any] | None,
    *,
    strict: bool = False,
    normalize: bool = True,
    warn_unknown: bool = False,
) -> Callable[[dict[str, Any]], Any] | None:
    """Wrap a schema type into a callable that accepts a raw config dict.

    - **Dataclass types** (detected via `dataclasses.is_dataclass`) are
      auto-wrapped: keys are normalized (hyphens to underscores), nested
      dicts are flattened, and the result is filtered to known fields
      before instantiation. Three schema-aware features refine this
      process:

      1. **Type-aware flattening.**  Fields typed as `dict[str, X]`
         are treated as opaque: `flatten_config_keys` stops at their
         boundary so the dict value is kept intact.

      2. **Field metadata.**  Dataclass fields may carry
         `click_extra.config_path` (a dotted TOML path like
         `"test-matrix.replace"`) and `click_extra.normalize_keys`
         (`False` to skip key normalization on the extracted value).
         Fields with an explicit path are extracted from the raw config
         before normalization and flattening.

      3. **Nested dataclass support.**  Fields whose resolved type is
         itself a dataclass are recursively processed with the same
         logic.

    - **Any other callable** is returned as-is. The caller is responsible
      for key normalization if needed.
    - `None` returns `None`.

    :param strict: If `True`, raise `ValueError` when the config
        contains keys that do not match any dataclass field (after
        normalization and flattening).
    :param warn_unknown: If `True` (and `strict` is `False`), log a
        warning naming those same unknown keys instead of silently dropping
        them. Meant for configs whose section is schema-only (no CLI
        parameter is merged from it, i.e. `included_params=()`), where any
        unrecognized key can only be a typo. Applies recursively to nested
        dataclasses.
    :param normalize: If `False`, skip `normalize_config_keys` on
        the remaining config dict. Used internally when recursing into
        nested dataclasses whose parent opted out of normalization via
        `click_extra.normalize_keys = False`.
    """
    if schema is None:
        return None
    if is_dataclass(schema):
        return partial(
            _from_dataclass,
            schema,
            strict=strict,
            normalize=normalize,
            warn_unknown=warn_unknown,
        )
    # Already a callable (Pydantic .model_validate, custom function, etc.).
    return schema


def _select_app_section(
    conf: dict[str, Any],
    app_name: str,
    fallback_sections: Sequence[str] = (),
    warn: bool = True,
) -> dict[str, Any]:
    """Extract the app's configuration section from a parsed config document.

    Looks for `conf[app_name]` first. If it is missing or empty, tries each
    name in `fallback_sections` in order, logging a deprecation warning on
    match. Works identically for all configuration formats. Set `warn` to
    `False` when the caller already resolved the section once and the
    deprecation warning would repeat itself.

    An empty `app_name` returns `conf` itself, as {func}`_scope_app_sections` and
    {func}`_rooted_path` read it: the section is then the whole document.
    """
    if not app_name:
        return conf
    section = conf.get(app_name)
    if isinstance(section, dict) and section:
        # Warn about leftover legacy sections.
        if warn:
            for old_name in fallback_sections:
                if old_name in conf:
                    logger.warning(
                        f"Config section [{old_name}] is deprecated and "
                        f"should be removed. Using [{app_name}]."
                    )
        return section

    for old_name in fallback_sections:
        section = conf.get(old_name)
        if isinstance(section, dict) and section:
            if warn:
                logger.warning(
                    f"Config section [{old_name}] is deprecated, "
                    f"migrate to [{app_name}]."
                )
            return section
    return {}


def _schema_keys(
    section: dict[Any, Any],
    schema: type | Callable[[dict[str, Any]], Any] | None,
) -> frozenset[str]:
    """Return the keys of `section` a dataclass `schema` reads in full.

    Follows how {func}`_from_dataclass` consumes a section. A field pinned to a
    path by {data}`CONFIG_PATH_METADATA_KEY` takes the sub-tree there. The other
    keys are normalized and flattened, a nested dataclass or an extension field
    taking its table whole, and each flattened key naming a field is read. A key
    of `section` is returned when the schema reads all of it.

    Returns an empty set for a schema that is not a dataclass: a callable does not
    tell which keys it reads.
    """
    if schema is None or not is_dataclass(schema):
        return frozenset()
    all_fields = dc_fields(schema)
    known = {f.name for f in all_fields}
    hints = _safe_get_type_hints(schema)

    # Phase 1 of _from_dataclass: a found pinned path leaves the section.
    remaining = dict(section)
    pinned: set[str] = set()
    for f in all_fields:
        path = f.metadata.get(CONFIG_PATH_METADATA_KEY)
        if path is None:
            continue
        _value, found = _extract_dotted(remaining, path)
        if found:
            remaining = _remove_dotted(remaining, path)
            pinned.add(f.name)

    # Phase 2: the same flatten boundaries, so a table read whole stays one key.
    boundaries = frozenset(
        f.name
        for f in all_fields
        if f.name not in pinned
        and (
            _is_extension_field(f, hints.get(f.name)) or is_dataclass(hints.get(f.name))
        )
    )

    keys: set[str] = set()
    for key in section:
        if key not in remaining:
            keys.add(key)
            continue
        flattened = flatten_config_keys(
            normalize_config_keys({key: remaining[key]}, opaque_keys=boundaries),
            opaque_keys=boundaries,
        )
        if flattened and known.issuperset(flattened):
            keys.add(key)
    return frozenset(keys)


def _build_merged_conf(
    conf: dict[str, Any],
    *,
    app_name: str,
    params_template: dict[str, Any],
    opaque_paths: Iterable[str] = (),
    fallback_sections: Sequence[str] = (),
    strict: bool = False,
    blocked: frozenset[str] = frozenset(),
    warn: bool = True,
    config_schema: type | Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Merge the app's section of `conf` onto a copy of `params_template`.

    The single recipe behind {attr}`ValidationReport.merged_conf` and
    {meth}`~click_extra.config.option.ConfigOption.merge_default_map`, so the
    document that gets validated and the one merged into `default_map` match:

    1. Strip the opaque sub-trees and the reserved keys, then expand dotted keys.
       Opaque sub-trees leave before the expansion: their keys are data, not
       parameter paths, so a dot inside one belongs to the key.
    2. Strip the opaque sub-trees again, to drop one whose path the document
       spells as a dotted key.
    3. Reduce the document to the app's section with {func}`_scope_app_sections`,
       so foreign sections of a shared file are not checked.
    4. Merge the section onto the template with {func}`_merge_into_template`.
       Strict mode accepts a key of the section that matches no parameter when
       the dataclass `config_schema` reads it: a section can mix parameters
       with schema fields.

    A template without the app's section, as `included_params=()` produces, reads
    no parameter from the file: the section belongs to the schema alone, and
    nothing is checked or merged.

    :param opaque_paths: dotted paths of the opaque sub-trees, relative to the
        app's section.
    :param warn: log the deprecation warning of a fallback section. Set it to
        `False` when the caller already resolved the section.
    :param config_schema: the schema reading the app's section, whose keys strict
        mode accepts.
    :raises ValidationError: in strict mode, on an invalid dotted key or a key
        matching no parameter.
    """
    if app_name and app_name not in params_template:
        return {}
    rooted_paths = tuple(_rooted_path(app_name, path) for path in opaque_paths)
    stripped = _strip_reserved_keys(_strip_opaque_subtrees(conf, rooted_paths))
    expanded = _expand_dotted_keys(stripped, strict=strict)
    scoped = _scope_app_sections(
        _strip_opaque_subtrees(expanded, rooted_paths),
        app_name,
        fallback_sections,
        warn=warn,
    )
    exempt: frozenset[tuple[str, ...]] = frozenset()
    if strict:
        section = scoped.get(app_name, {}) if app_name else scoped
        root = (app_name,) if app_name else ()
        exempt = frozenset((*root, key) for key in _schema_keys(section, config_schema))
    return _merge_into_template(
        copy.deepcopy(params_template), scoped, strict, blocked=blocked, exempt=exempt
    )


def _collect_validator_errors(
    app_name: str,
    app_section: dict[str, Any],
    config_validators: Sequence[ConfigValidator],
) -> Iterator[ValidationError]:
    """Run every validator against its extension sub-tree, yielding re-anchored
    {class}`ValidationError` instances.

    Each validator receives the value of the sub-tree at its declared
    `extension_path` (relative to the app section). Missing and non-dict
    sub-trees are skipped without invoking the validator: an absent or malformed
    extension table is a click-extra concern, not the validator's. Raised paths
    are re-anchored to the configuration file root so reporting is uniform across
    click-extra's own checks and user-registered validators.

    The last stage of {func}`run_config_validation`. Generator interface so the
    caller picks its error-handling strategy (collect all, or stop at the first).
    """
    for cv in config_validators:
        subtree, found = _extract_dotted(app_section, cv.extension_path)
        if not found or not isinstance(subtree, dict):
            continue
        try:
            cv.validator(subtree)
        except ValidationError as exc:
            prefix = _rooted_path(app_name, cv.extension_path)
            rooted_path = f"{prefix}.{exc.path}" if exc.path else prefix
            yield ValidationError(rooted_path, exc.message, exc.code)


@dataclass(frozen=True)
class ValidationReport:
    """Outcome of one pass through {func}`run_config_validation`.

    Bundles everything a caller needs after validating a parsed configuration
    document: the typed schema instance, the extracted opaque sub-trees, the
    template-filtered config ready for `default_map`, and every error detected
    across all validation stages.

    ```{note}
    The report holds references to the parsed sub-trees, not copies, so
    building it is cheap regardless of document size.
    ```
    """

    schema_instance: Any | None
    """Typed object produced by the configured schema callable.

    `None` when no schema is configured, or when the schema stage raised
    (in which case the failure is recorded in {attr}`errors`)."""

    opaque_subtrees: dict[str, dict[str, Any]]
    """Extracted extension sub-trees, keyed by dotted path relative to the app
    section. Only paths actually present in the document appear here, so callers
    can re-route them to per-path validators or stash them on `ctx.meta`."""

    errors: tuple[ValidationError, ...]
    """Every {class}`ValidationError` detected, in stage order (CLI-flag keys
    first, then schema errors, then validator failures). Empty on success.

    With `collect_all=False` this holds at most one error: the first failure
    short-circuits the remaining stages."""

    merged_conf: dict[str, Any] | None = None
    """The CLI-flag-bound configuration merged onto `params_template`: the
    payload {meth}`~click_extra.config.option.ConfigOption.load_conf` layers into
    the context's `default_map`, as
    {meth}`~click_extra.config.option.ConfigOption.merge_default_map` does.

    `None` when `params_template` was `None` (no strict check) or the strict
    check failed."""

    @property
    def ok(self) -> bool:
        """`True` when no error was detected."""
        return not self.errors


def run_config_validation(
    user_conf: dict[str, Any],
    *,
    app_name: str,
    params_template: dict[str, Any] | None,
    config_schema: type | Callable[[dict[str, Any]], Any] | None = None,
    config_validators: Sequence[ConfigValidator] = (),
    fallback_sections: Sequence[str] = (),
    schema_strict: bool = False,
    schema_warn_unknown: bool = False,
    strict: bool = False,
    blocked_params: Iterable[str] = (),
    collect_all: bool = True,
) -> ValidationReport:
    """Validate a parsed configuration document in one schema-driven pass.

    Runs click-extra's three checks (the CLI-parameter strict check, the
    dataclass schema, and the app-registered {class}`ConfigValidator` hooks)
    behind a single function yielding a single error type. It is not named
    `validate_config`: that name belongs to
    {meth}`~click_extra.config.option.ValidateConfigOption.validate_config`, the
    callback powering the `--validate-config` flag.

    Stages, in order:

    1. **Partition.** Split opaque sub-trees (schema extension fields plus every
       registered validator's `extension_path`) from the CLI-flag-bound
       content. Extracted sub-trees land in
       {attr}`ValidationReport.opaque_subtrees`.
    2. **Strict-check** the CLI-flag-bound part against `params_template`, once
       its dotted keys are expanded, keeping the merged result as
       {attr}`ValidationReport.merged_conf` (skipped when `params_template` is
       `None`). A key the dataclass schema reads is left to stage 3.
    3. **Schema-build** the app section through the configured callable,
       producing {attr}`ValidationReport.schema_instance`.
    4. **Validate** every opaque sub-tree through its registered validator.

    :param user_conf: The full parsed configuration document.
    :param app_name: Name of the app's section (used to resolve the section and
        to root opaque paths and error paths at the document level).
    :param params_template: The CLI-parameter template the strict check runs
        against. Pass `None` to skip the strict check entirely (for example,
        for a schema-only validation).
    :param config_schema: Dataclass type or callable describing the typed
        configuration, or `None`.
    :param config_validators: Extension validators to run against opaque
        sub-trees.
    :param fallback_sections: Legacy section names to try when `app_name` is
        absent or empty.
    :param schema_strict: Reject keys the dataclass schema does not recognize.
    :param schema_warn_unknown: In lax mode, log a warning naming keys the
        dataclass schema does not recognize (see `warn_unknown` in
        {func}`make_schema_callable`). Ignored when `schema_strict` rejects
        them outright.
    :param strict: Reject keys that neither the CLI-parameter template nor the
        dataclass schema recognize, keys that are not strings, and dotted keys
        that conflict with another key or have an empty segment.
    :param blocked_params: Fully-qualified IDs of parameters excluded from
        configuration files, used to sharpen strict-mode error messages (a
        blocked parameter is reported as such, not as unknown).
    :param collect_all: When `True` (default), run every stage and collect all
        errors. When `False`, the first error short-circuits the rest.
    :return: A {class}`ValidationReport`. `ValidationError` is the single error
        type recorded by every stage; a `ValueError` or `TypeError` raised by
        the schema callable is wrapped into it.
    """
    errors: list[ValidationError] = []
    merged_conf: dict[str, Any] | None = None

    def record(error: ValidationError) -> bool:
        """Append *error*; return `True` when the caller should stop early."""
        errors.append(error)
        return not collect_all

    opaque_paths = _collect_opaque_paths(config_schema, config_validators)

    # Stage 1: partition opaque sub-trees from CLI-flag-bound content.
    app_section = _select_app_section(user_conf, app_name, fallback_sections)
    opaque_subtrees: dict[str, dict[str, Any]] = {}
    for path in opaque_paths:
        subtree, found = _extract_dotted(app_section, path)
        if found and isinstance(subtree, dict):
            opaque_subtrees[path] = subtree

    # Stage 2: strict-check the CLI-flag-bound part against the template. Stage 1
    # already resolved the section, so the legacy-section warning is muted here.
    if params_template is not None:
        try:
            merged_conf = _build_merged_conf(
                user_conf,
                app_name=app_name,
                params_template=params_template,
                opaque_paths=opaque_paths,
                fallback_sections=fallback_sections,
                strict=strict,
                blocked=frozenset(blocked_params),
                warn=False,
                config_schema=config_schema,
            )
        except ValidationError as exc:
            if record(exc):
                return ValidationReport(None, opaque_subtrees, tuple(errors))

    # Stage 3: build the typed schema instance from the app section.
    schema_instance = None
    schema_callable = make_schema_callable(
        config_schema, strict=schema_strict, warn_unknown=schema_warn_unknown
    )
    if schema_callable is not None:
        try:
            schema_instance = schema_callable(app_section)
        except (ValueError, TypeError) as exc:
            # An unknown schema field or a type mismatch. A custom schema
            # callable raising a ValidationError keeps its path and code. The
            # strict check passed, so merged_conf is carried even on this exit.
            schema_error = (
                exc
                if isinstance(exc, ValidationError)
                else ValidationError("", str(exc), code="schema_error")
            )
            if record(schema_error):
                return ValidationReport(
                    None, opaque_subtrees, tuple(errors), merged_conf
                )

    # Stage 4: run every ConfigValidator against its opaque sub-tree.
    for error in _collect_validator_errors(app_name, app_section, config_validators):
        if record(error):
            break

    return ValidationReport(
        schema_instance, opaque_subtrees, tuple(errors), merged_conf
    )
