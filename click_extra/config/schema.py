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

import copy
import logging
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import (
    MISSING,
    Field,
    dataclass,
    fields as dc_fields,
    is_dataclass,
)
from functools import partial
from typing import get_origin, get_type_hints

from deepmerge import always_merger
from extra_platforms._utils import _recursive_update

from .. import context, get_current_context
from ..parameters import ParamStructure

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

.. code-block:: toml

    [my-cli]
    _default_subcommands = ["backup", "sync"]

    [my-cli.backup]
    path = "/home"
"""

PREPEND_SUBCOMMANDS_KEY = "_prepend_subcommands"
"""Reserved configuration key for prepending subcommands to every invocation.

Unlike ``_default_subcommands`` which only fires when no subcommands are given on the
CLI, ``_prepend_subcommands`` always prepends the listed subcommands. This is useful
for always injecting a ``debug`` subcommand on a dev machine, for example.

Only works with ``chain=True`` groups (non-chained groups resolve exactly one
subcommand, so prepending would break the user's intended command).

Example TOML configuration:

.. code-block:: toml

    [my-cli]
    _prepend_subcommands = ["debug"]
"""

_RESERVED_CONFIG_KEYS = frozenset({DEFAULT_SUBCOMMANDS_KEY, PREPEND_SUBCOMMANDS_KEY})
"""Configuration keys with special meaning that should not be treated as parameters."""


EXTENSION_METADATA_KEY = "click_extra.extension"
"""Dataclass field metadata flag marking a field as an *extension point*.

Schema authors set ``metadata={EXTENSION_METADATA_KEY: True}`` on a field when
its sub-tree should pass through click-extra's CLI-parameter strict check and
be validated by app-specific logic instead. Equivalent to typing the field as
``dict[str, X]``: both forms are recognized by
:py:func:`_collect_opaque_paths_from_schema` (the internal pipeline still calls
these paths "opaque" since they're skipped by the normalize/flatten/strict
machinery). The metadata form is useful when the underlying Python type is
something other than a ``dict`` (for example, a nested dataclass that
nonetheless represents user-extensible content)."""


THEMES_CONFIG_KEY: str = "themes"
"""Sub-key under ``[tool.<cli>]`` where user-defined themes live in config.

Used by :class:`~click_extra.config.option.ConfigOption` to find ``[tool.<cli>.themes.<name>]`` tables,
build them via :meth:`HelpTheme.from_dict
<click_extra.theme.HelpTheme.from_dict>`, and stash the result on
``ctx.meta[click_extra.context.THEME_OVERRIDES]``. The constant is the
single source of truth shared by :func:`_builtin_config_validators`,
:meth:`~click_extra.config.option.ConfigOption._apply_theme_overrides`, and
:func:`click_extra.theme.themes_from_config`.
"""


class ValidationError(Exception):
    """Raised when a configuration file fails validation.

    A single, structured exception type that uniformly carries the dotted
    ``path`` of the offending key, a human-readable ``message``, and an optional
    ``code`` for programmatic handling. Used by click-extra's built-in
    strict-mode check and by every user-registered :class:`ConfigValidator`, so
    downstream apps and ``--validate-config`` see the same error shape regardless
    of who detected the problem.

    :param path: Dotted path to the offending key, relative to the configuration
        file root (e.g. ``"my-cli.managers.winget.cli_searchpath"``). An empty
        string means the error applies to the document as a whole.
    :param message: Human-readable description of the failure. Should be a
        single sentence, no trailing punctuation, no path repeated.
    :param code: Optional machine-readable error code (e.g. ``"unknown_field"``)
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

    Apps register validators via the ``config_validators=`` kwarg on
    :class:`~click_extra.config.option.ConfigOption` (or the matching decorator) to extend click-extra's
    built-in CLI-parameter strict check with custom validation logic. Each
    validator targets a single dotted ``extension_path`` relative to the app's
    configuration section. Click-extra passes the matching sub-tree straight
    through to the registered validator: the strict check skips it, the schema
    machinery treats it as opaque, and the user's logic owns the result. The
    validator runs both during ``--validate-config`` and during normal config
    loading.

    :param extension_path: Dotted path of the sub-tree the validator owns,
        relative to the app's section in the configuration file. For example, an
        app named ``my-cli`` with ``extension_path="managers"`` receives the
        contents of the ``[my-cli.managers]`` table.
    :param validator: Callable taking the sub-tree dict and raising
        :class:`ValidationError` on failure. Must be a pure function: no side
        effects on the click context, no print statements. The caller decides
        how to surface the error.
    :param description: Optional human-readable summary of what the validator
        checks. Surfaces in documentation generators that introspect the
        decorator (e.g. autodoc), and may be reused in ``--help`` text in a
        future release.
    """

    extension_path: str
    validator: Callable[[dict[str, Any]], None]
    description: str = ""


def _builtin_config_validators() -> tuple[ConfigValidator, ...]:
    """Return the validators click-extra registers on every :class:`~click_extra.config.option.ConfigOption`.

    Currently a single validator for ``[tool.<cli>.themes.<name>]`` tables.
    Lazy-imports :func:`~click_extra.theme.validate_themes_config` to avoid
    a load-time cycle: :mod:`click_extra.theme` is imported after
    :mod:`click_extra.config` from the package ``__init__``.
    """
    from ..theme import validate_themes_config

    return (
        ConfigValidator(
            extension_path=THEMES_CONFIG_KEY,
            validator=validate_themes_config,
            description=(
                "Validate user-defined and override themes declared under "
                "[tool.<cli>.themes.<name>]."
            ),
        ),
    )


def _strip_reserved_keys(conf: dict, keys: frozenset[str] | None = None) -> dict:
    """Recursively return a copy of *conf* with reserved keys removed at every level."""
    if keys is None:
        keys = _RESERVED_CONFIG_KEYS
    cleaned: dict = {}
    for k, v in conf.items():
        if k in keys:
            continue
        cleaned[k] = _strip_reserved_keys(v, keys) if isinstance(v, dict) else v
    return cleaned


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

    In strict mode, raises ``ValueError`` instead of logging a warning.
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
                raise ValueError(msg)
            logger.warning(f"{msg} Last value wins.")
            return
        if is_last:
            return
        node = existing


def _expand_dotted_keys(conf: dict, strict: bool = False) -> dict:
    """Expand dotted keys into nested dicts, then deep-merge.

    Allows configuration files to mix flat dot-notation and nested structures::

        {"subcommand.option_a": 1, "subcommand": {"option_b": 2}}

    becomes::

        {"subcommand": {"option_a": 1, "option_b": 2}}

    Recurses into nested dicts so dotted keys at any level are expanded.

    In non-strict mode, logs a warning when a key resolves to both a scalar
    and a dict (e.g. ``{"a": 1, "a.b": 2}``), as one value will silently
    override the other.

    In strict mode, raises ``ValueError`` on type conflicts and invalid
    dotted keys (empty segments).
    """
    expanded: dict = {}
    for key, value in conf.items():
        if isinstance(value, dict):
            value = _expand_dotted_keys(value, strict=strict)
        if "." in key:
            parts = key.split(".")
            if not all(parts):
                msg = f"Configuration key {key!r} contains empty segments."
                if strict:
                    raise ValueError(msg)
                logger.warning(f"Ignoring {msg.lower()}")
                continue
            nested = ParamStructure.init_tree_dict(*parts, leaf=value)
            _check_type_conflict(expanded, parts, value, key, strict)
            expanded = always_merger.merge(expanded, nested)
        else:
            _check_type_conflict(expanded, [key], value, key, strict)
            expanded = always_merger.merge(expanded, {key: value})
    return expanded


def normalize_config_keys(
    conf: dict[str, Any],
    opaque_keys: frozenset[str] = frozenset(),
    _prefix: str = "",
) -> dict[str, Any]:
    """Normalize configuration keys to valid Python identifiers.

    Recursively replaces hyphens with underscores in all dict keys, using the
    same ``str.replace("-", "_")`` transform that Click applies internally when
    deriving parameter names from option declarations (e.g. ``--foo-bar`` becomes
    ``foo_bar``).  Click does not expose this as a public function, so we
    replicate the one-liner here.

    Handles the convention mismatch between configuration formats (TOML, YAML,
    JSON all commonly use kebab-case) and Python identifiers.  Works with all
    configuration formats supported by ``ConfigOption``.

    :param opaque_keys: Fully-qualified key names (using ``"_"`` as
        separator) where recursion stops.  The key itself is still
        normalized, but its dict value is kept as-is.  Used in tandem
        with ``flatten_config_keys``'s ``opaque_keys`` to protect data
        dicts (e.g. GitHub Actions matrix axes) from normalization.
    :param _prefix: Internal parameter for tracking the accumulated key
        path during recursion.  Callers should not set this.

    .. todo::
        Propose upstream to Click to extract the inline ``name.replace("-", "_")``
        into a private ``_normalize_param_name`` helper, so downstream projects
        like Click Extra can reuse it instead of duplicating the transform.
    """
    normalized: dict[str, Any] = {}
    for key, value in conf.items():
        py_key = key.replace("-", "_")
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

    Useful for mapping nested configuration structures (e.g. TOML sub-tables) to
    flat Python dataclass fields.  After normalization with
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
    :param sep: Separator used to join parent and child keys.  Defaults to
        ``"_"`` which produces valid Python identifiers when combined with
        `normalize_config_keys`.
    :param opaque_keys: Fully-qualified key names where flattening stops.
        When the accumulated key matches an entry in this set, the dict
        value is kept as-is instead of being recursively flattened.  This
        is useful for fields typed as ``dict[str, X]`` where the dict keys
        are data (e.g. GitHub Actions matrix axis names), not config
        structure.
    :param _prefix: Internal parameter for tracking the accumulated key
        path during recursion.  Callers should not set this.
    """
    items: dict[str, Any] = {}
    for key, value in conf.items():
        full_key = f"{_prefix}{sep}{key}" if _prefix else key
        if isinstance(value, dict) and full_key not in opaque_keys:
            items.update({
                sub_key: sub_value
                for sub_key, sub_value in flatten_config_keys(
                    value, sep, opaque_keys, full_key
                ).items()
            })
        else:
            items[full_key] = value
    return items


def get_tool_config(ctx: click.Context | None = None) -> Any:
    """Retrieve the typed tool configuration from the context.

    Returns the object stored under :data:`click_extra.context.TOOL_CONFIG`
    by ``ConfigOption`` when a ``config_schema`` is set, or ``None`` if no
    schema was configured or no configuration was loaded.

    :param ctx: Click context. Defaults to the current context.
    """
    if ctx is None:
        ctx = get_current_context()
    return context.get(ctx, context.TOOL_CONFIG)


def _safe_get_type_hints(cls: type) -> dict[str, Any]:
    """Resolve type hints for a class, returning empty dict on failure.

    Wraps ``typing.get_type_hints`` to handle cases where annotations
    reference types that are not importable in the current context (e.g.
    forward references to types only available under ``TYPE_CHECKING``).

    When the initial resolution fails (common for locally-defined classes
    whose annotations are stringified by ``from __future__ import
    annotations``), a second attempt is made with a ``localns`` built from
    ``default_factory`` values on the class's dataclass fields.  This
    allows nested dataclass types like ``sub: SubConfig =
    field(default_factory=SubConfig)`` to be resolved even when
    ``SubConfig`` is not in the module's global scope.
    """
    try:
        return get_type_hints(cls)
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
    """Check if a resolved type hint is a ``dict`` or ``Mapping``."""
    if hint is None:
        return False
    origin = get_origin(hint)
    return origin is dict or origin is Mapping


def _is_extension_field(field: Field, hint: object) -> bool:
    """Return ``True`` when a dataclass field is an *extension point*.

    A field qualifies when **either**:

    - it carries ``metadata={EXTENSION_METADATA_KEY: True}`` (explicit marker,
      useful when the Python type is not a mapping), or
    - its resolved type hint is ``dict[str, X]`` / ``Mapping[str, X]`` (the user
      controls the keys, not the schema).

    Single source of truth for the per-field extension-point criteria. Both the
    recursive schema walk in :py:func:`_collect_opaque_paths_from_schema` and the
    flatten-boundary set computed inside :py:func:`_from_dataclass` route through
    this helper so they cannot drift apart. The historical leak this closes:
    :py:func:`_from_dataclass` used to inspect only the type hint, so a
    non-mapping field flagged with ``EXTENSION_METADATA_KEY`` was opaque at the
    outer strip yet transparent at the inner flatten, which then descended into a
    sub-tree the schema author had marked off-limits.
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
    is therefore treated as opaque by the rest of the pipeline) when **any** of
    the following is true:

    - The field's type hint is ``dict[str, X]`` or ``Mapping[str, X]`` (user
      controls the keys, not the schema).
    - The field carries ``metadata={EXTENSION_METADATA_KEY: True}`` (explicit
      marker, useful when the underlying Python type is something other than a
      mapping).

    The helper name retains the historical ``opaque`` term because callers
    inside :py:mod:`click_extra.config` use the result to bypass the
    normalize/flatten/strict machinery — that pipeline's vocabulary is "opaque
    paths." From a public API point of view those are the *extension paths*,
    but inside this module the two names refer to the same set.

    Nested dataclass fields are not themselves opaque: the function recurses
    into them, prepending the field name to every collected sub-path.

    The returned set contains dotted paths **relative to the schema root**, not
    the configuration file root. The caller is responsible for prefixing them
    with the app section name (or any other root) before stripping or
    extracting sub-trees from a raw config dict.

    Returns an empty set when ``schema`` is ``None`` or not a dataclass, so
    callers can pass any of the values accepted by ``config_schema``.
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


def _strip_opaque_subtrees(
    conf: dict[str, Any],
    opaque_paths: Iterable[str],
) -> dict[str, Any]:
    """Return a shallow-copied *conf* with every opaque sub-tree removed.

    Each path in ``opaque_paths`` is a dotted location relative to ``conf``'s
    root (callers prepend the app section name when needed). Paths that don't
    resolve to anything are silently skipped: a schema may declare an opaque
    field that the user never sets, and that's not an error. The empty path
    is treated as a no-op for the same reason.

    Use to drop user-controlled sub-trees from a normalized configuration
    document before running click-extra's CLI-parameter strict check. The
    sub-trees themselves are not returned: when callers need both the stripped
    document and the extracted sub-trees, they can read them out of the
    original ``conf`` with :py:func:`_extract_dotted` before calling this
    helper.
    """
    result = dict(conf)
    for path in opaque_paths:
        if path:
            result = _remove_dotted(result, path)
    return result


def _extract_dotted(conf: dict[str, Any], path: str) -> tuple[Any, bool]:
    """Extract a value at a dotted path from a nested dict.

    :param conf: Nested dict to search.
    :param path: Dotted path (e.g. ``"test-matrix.replace"``).
    :return: ``(value, True)`` if found, ``(None, False)`` otherwise.
    """
    current: Any = conf
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def _remove_dotted(conf: dict[str, Any], path: str) -> dict[str, Any]:
    """Remove a value at a dotted path, returning a modified shallow copy.

    Parent dicts that become empty after removal are also pruned.
    """
    parts = path.split(".")
    if len(parts) == 1:
        return {k: v for k, v in conf.items() if k != parts[0]}
    top = parts[0]
    if top not in conf or not isinstance(conf[top], dict):
        return conf
    sub = _remove_dotted(conf[top], ".".join(parts[1:]))
    if not sub:
        return {k: v for k, v in conf.items() if k != top}
    return {**conf, top: sub}


def _apply_nested_schema(
    hint: type | None,
    value: dict[str, Any],
    strict: bool,
    do_normalize: bool = True,
) -> Any:
    """Recursively apply a schema callable to a dict value if the hint is a dataclass.

    Falls back to ``normalize_config_keys`` when the hint is not a dataclass
    but normalization is requested.  Returns ``value`` unchanged otherwise.
    """
    if is_dataclass(hint):
        sub = make_schema_callable(hint, strict=strict, normalize=do_normalize)
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
) -> Any:
    """Build a dataclass instance from a raw configuration dict.

    Handles explicit ``config_path`` metadata, type-aware normalization and
    flattening, nested dataclass recursion, and strict validation.  Called by
    ``make_schema_callable`` for dataclass schemas.
    """
    all_fields = dc_fields(schema)
    known = {f.name for f in all_fields}
    hints = _safe_get_type_hints(schema)

    # --- Phase 1: extract fields with explicit config_path. ---
    result: dict[str, Any] = {}
    remaining = dict(raw)

    for f in all_fields:
        path = f.metadata.get("click_extra.config_path")
        if path is None:
            continue
        do_normalize = f.metadata.get("click_extra.normalize_keys", True)
        value, found = _extract_dotted(remaining, path)
        if not found:
            continue
        remaining = _remove_dotted(remaining, path)

        hint = hints.get(f.name)
        if isinstance(value, dict):
            value = _apply_nested_schema(hint, value, strict, do_normalize)
        result[f.name] = value

    # --- Phase 2: type-aware normalize + flatten. ---
    # Detect opaque fields, i.e. flatten boundaries the recursion must not cross:
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
            sub = make_schema_callable(hint, strict=strict)  # type: ignore[arg-type]
            flattened[f.name] = sub(flattened[f.name]) if sub else flattened[f.name]

    # --- Phase 4: merge and validate. ---
    for k, v in flattened.items():
        if k in known and k not in result:
            result[k] = v

    if strict:
        all_keys = set(result) | set(flattened)
        unknown = sorted(all_keys - known)
        if unknown:
            msg = (
                f"Unknown configuration option(s): "
                f"{', '.join(unknown)}. "
                f"Valid options: {', '.join(sorted(known))}"
            )
            raise ValueError(msg)

    return schema(**{k: v for k, v in result.items() if k in known})


def make_schema_callable(
    schema: type | Callable[[dict[str, Any]], Any] | None,
    *,
    strict: bool = False,
    normalize: bool = True,
) -> Callable[[dict[str, Any]], Any] | None:
    """Wrap a schema type into a callable that accepts a raw config dict.

    - **Dataclass types** (detected via ``dataclasses.is_dataclass``) are
      auto-wrapped: keys are normalized (hyphens to underscores), nested
      dicts are flattened, and the result is filtered to known fields
      before instantiation.  Three schema-aware features refine this
      process:

      1. **Type-aware flattening.**  Fields typed as ``dict[str, X]``
         are treated as opaque: ``flatten_config_keys`` stops at their
         boundary so the dict value is kept intact.

      2. **Field metadata.**  Dataclass fields may carry
         ``click_extra.config_path`` (a dotted TOML path like
         ``"test-matrix.replace"``) and ``click_extra.normalize_keys``
         (``False`` to skip key normalization on the extracted value).
         Fields with an explicit path are extracted from the raw config
         before normalization and flattening.

      3. **Nested dataclass support.**  Fields whose resolved type is
         itself a dataclass are recursively processed with the same
         logic.

    - **Any other callable** is returned as-is.  The caller is responsible
      for key normalization if needed.
    - ``None`` returns ``None``.

    :param strict: If ``True``, raise ``ValueError`` when the config
        contains keys that do not match any dataclass field (after
        normalization and flattening).
    :param normalize: If ``False``, skip ``normalize_config_keys`` on
        the remaining config dict.  Used internally when recursing into
        nested dataclasses whose parent opted out of normalization via
        ``click_extra.normalize_keys = False``.
    """
    if schema is None:
        return None
    if is_dataclass(schema):
        return partial(
            _from_dataclass,
            schema,
            strict=strict,
            normalize=normalize,
        )
    # Already a callable (Pydantic .model_validate, custom function, etc.).
    return schema


def _select_app_section(
    conf: dict[str, Any],
    app_name: str,
    fallback_sections: Sequence[str] = (),
) -> dict[str, Any]:
    """Extract the app's configuration section from a parsed config document.

    Looks for ``conf[app_name]`` first. If it is missing or empty, tries each
    name in ``fallback_sections`` in order, logging a deprecation warning on
    match. Works identically for all configuration formats.

    Free-function form of :py:meth:`~click_extra.config.option.ConfigOption._resolve_app_section`, shared
    with :py:func:`run_config_validation` so both resolve the section (and warn
    about leftover legacy sections) the exact same way.
    """
    section = conf.get(app_name)
    if isinstance(section, dict) and section:
        # Warn about leftover legacy sections.
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
            logger.warning(
                f"Config section [{old_name}] is deprecated, migrate to [{app_name}]."
            )
            return section
    return {}


def _collect_validator_errors(
    app_name: str,
    app_section: dict[str, Any],
    config_validators: Sequence[ConfigValidator],
) -> Iterator[ValidationError]:
    """Run every validator against its extension sub-tree, yielding re-anchored
    :class:`ValidationError` instances.

    Each validator receives the value of the sub-tree at its declared
    ``extension_path`` (relative to the app section). Missing and non-dict
    sub-trees are skipped without invoking the validator: an absent or malformed
    extension table is a click-extra concern, not the validator's. Raised paths
    are re-anchored to the configuration file root so reporting is uniform across
    click-extra's own checks and user-registered validators.

    Stage 5 of :py:func:`run_config_validation`. Generator interface so the
    caller picks its error-handling strategy (collect all, or stop at the first).
    """
    for cv in config_validators:
        subtree, found = _extract_dotted(app_section, cv.extension_path)
        if not found or not isinstance(subtree, dict):
            continue
        try:
            cv.validator(subtree)
        except ValidationError as exc:
            prefix = (
                f"{app_name}.{cv.extension_path}" if app_name else cv.extension_path
            )
            rooted_path = f"{prefix}.{exc.path}" if exc.path else prefix
            yield ValidationError(rooted_path, exc.message, exc.code)


@dataclass(frozen=True)
class ValidationReport:
    """Outcome of one pass through :py:func:`run_config_validation`.

    Bundles everything a caller needs after validating a parsed configuration
    document: the typed schema instance, the extracted opaque sub-trees, and
    every error detected across all validation stages.

    .. note::
        The report holds references to the parsed sub-trees, not copies, so
        building it is cheap regardless of document size.
    """

    schema_instance: Any | None
    """Typed object produced by the configured schema callable.

    ``None`` when no schema is configured, or when the schema stage raised
    (in which case the failure is recorded in :py:attr:`errors`)."""

    opaque_subtrees: dict[str, dict[str, Any]]
    """Extracted extension sub-trees, keyed by dotted path relative to the app
    section. Only paths actually present in the document appear here, so callers
    can re-route them to per-path validators or stash them on ``ctx.meta``."""

    errors: tuple[ValidationError, ...]
    """Every :class:`ValidationError` detected, in stage order (unknown CLI-flag
    keys first, then schema errors, then validator failures). Empty on success.

    With ``collect_all=False`` this holds at most one error: the first failure
    short-circuits the remaining stages."""

    @property
    def ok(self) -> bool:
        """``True`` when no error was detected."""
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
    strict: bool = False,
    collect_all: bool = True,
) -> ValidationReport:
    """Validate a parsed configuration document in one schema-driven pass.

    This is the module-level entry point that unifies click-extra's three
    historical validation paths (CLI-parameter strict check, dataclass schema,
    and app-registered :class:`ConfigValidator` hooks) behind a single function
    yielding a single error type. It is deliberately *not* named
    ``validate_config``: that name belongs to
    :py:meth:`~click_extra.config.option.ValidateConfigOption.validate_config`, the callback powering the
    ``--validate-config`` flag.

    Stages, in order:

    1. **Normalize.** Strip reserved keys and expand dotted keys.
    2. **Partition.** Split opaque sub-trees (schema extension fields plus every
       registered validator's ``extension_path``) from the CLI-flag-bound
       content. Extracted sub-trees land in
       :py:attr:`ValidationReport.opaque_subtrees`.
    3. **Strict-check** the CLI-flag-bound part against ``params_template``
       (skipped when ``params_template`` is ``None``).
    4. **Schema-build** the app section through the configured callable,
       producing :py:attr:`ValidationReport.schema_instance`.
    5. **Validate** every opaque sub-tree through its registered validator.

    :param user_conf: The full parsed configuration document.
    :param app_name: Name of the app's section (used to resolve the section and
        to root opaque paths and error paths at the document level).
    :param params_template: The CLI-parameter template the strict check runs
        against. Pass ``None`` to skip the strict check entirely (e.g. for a
        schema-only validation).
    :param config_schema: Dataclass type or callable describing the typed
        configuration, or ``None``.
    :param config_validators: Extension validators to run against opaque
        sub-trees.
    :param fallback_sections: Legacy section names to try when ``app_name`` is
        absent or empty.
    :param schema_strict: Reject keys the dataclass schema does not recognize.
    :param strict: Reject keys the CLI-parameter template does not recognize.
    :param collect_all: When ``True`` (default), run every stage and collect all
        errors. When ``False``, the first error short-circuits the rest.
    :return: A :class:`ValidationReport`. ``ValidationError`` is the single error
        type recorded by every stage; ``ValueError`` / ``TypeError`` raised by
        the strict check or schema callable are wrapped into it.
    """
    errors: list[ValidationError] = []

    def record(error: ValidationError) -> bool:
        """Append *error*; return ``True`` when the caller should stop early."""
        errors.append(error)
        return not collect_all

    # Stage 1 — normalize.
    normalized = _expand_dotted_keys(_strip_reserved_keys(user_conf), strict=strict)

    # Stage 2 — partition opaque sub-trees from CLI-flag-bound content.
    opaque_paths = _collect_opaque_paths_from_schema(config_schema) | frozenset(
        cv.extension_path for cv in config_validators
    )
    app_section = _select_app_section(user_conf, app_name, fallback_sections)
    opaque_subtrees: dict[str, dict[str, Any]] = {}
    for path in opaque_paths:
        subtree, found = _extract_dotted(app_section, path)
        if found and isinstance(subtree, dict):
            opaque_subtrees[path] = subtree

    # Stage 3 — strict-check the CLI-flag-bound part against the template.
    if params_template is not None:
        prefixed_paths = (
            f"{app_name}.{path}" if app_name else path for path in opaque_paths
        )
        stripped = _strip_opaque_subtrees(normalized, prefixed_paths)
        try:
            _recursive_update(copy.deepcopy(params_template), stripped, strict)
        except ValueError as exc:
            # Path-1 error. Empty path keeps str(ValidationError) == str(exc),
            # so existing message-based assertions and CLI output are preserved.
            if record(ValidationError("", str(exc), code="unknown_parameter")):
                return ValidationReport(None, opaque_subtrees, tuple(errors))

    # Stage 4 — build the typed schema instance from the app section.
    schema_instance = None
    schema_callable = make_schema_callable(config_schema, strict=schema_strict)
    if schema_callable is not None:
        try:
            schema_instance = schema_callable(app_section)
        except (ValueError, TypeError) as exc:
            # Path-2 error (unknown schema field or type mismatch).
            if record(ValidationError("", str(exc), code="schema_error")):
                return ValidationReport(None, opaque_subtrees, tuple(errors))

    # Stage 5 — run every ConfigValidator against its opaque sub-tree.
    for error in _collect_validator_errors(app_name, app_section, config_validators):
        if record(error):
            break

    return ValidationReport(schema_instance, opaque_subtrees, tuple(errors))
