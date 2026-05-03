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
"""Utilities to load parameters and options from a configuration file.

.. hint::
    Why ``config``?

    That whole namespace is using the common ``config`` short-name to designate
    configuration files.

    Not ``conf``, not ``cfg``, not ``configuration``, not ``settings``. Just ``config``.

    A quick survey of existing practices, and poll to my friends informed me that
    ``config`` is more explicit and less likely to be misunderstood.

    After all, is there a chance for it to be misunderstood, in the context of a CLI,
    for something else? *Confirm*? *Conference*? *Conflict* *Confuse*?...

    So yes, ``config`` is good enough.

.. todo::
    Add a ``--dump-config`` or ``--export-config`` option to write down the current
    configuration (or a template) into a file or ``<stdout>``.

    Help message would be: *you can use this option with other options or environment
    variables to have them set in the generated configuration*.

Dotted keys in configuration files (e.g. ``"subcommand.option": value``) are
automatically expanded into nested dicts before merging, so users can freely mix
flat dot-notation and nested structures in any supported format.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import ChainMap
from collections.abc import Iterable, Mapping
from configparser import ConfigParser, ExtendedInterpolation
from dataclasses import MISSING, fields as dc_fields, is_dataclass
from enum import Enum
from functools import cached_property, partial
from gettext import gettext as _
from pathlib import Path, PurePosixPath
from typing import get_origin, get_type_hints

import requests
from boltons.iterutils import flatten, unique
from boltons.pathutils import shrinkuser
from boltons.urlutils import URL
from deepmerge import always_merger
from extra_platforms import is_windows
from extra_platforms._utils import _recursive_update, _remove_blanks
from wcmatch import fnmatch, glob

from . import (
    UNPROCESSED,
    ParameterSource,
    Path as ClickPath,
    context,
    echo,
    get_app_dir,
    get_current_context,
)
from .parameters import ExtraOption, ParamStructure, search_params

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]


TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any, Literal

    import click


yaml_support = True
try:
    import yaml
except ImportError:
    yaml_support = False
    logging.getLogger("click_extra").debug(
        "YAML support disabled: install click-extra[yaml] to enable it."
    )


json5_support = True
try:
    import json5
except ImportError:
    json5_support = False
    logging.getLogger("click_extra").debug(
        "JSON5 support disabled: install click-extra[json5] to enable it."
    )


jsonc_support = True
try:
    import jsonc
except ImportError:
    jsonc_support = False
    logging.getLogger("click_extra").debug(
        "JSONC support disabled: install click-extra[jsonc] to enable it."
    )


hjson_support = True
try:
    import hjson
except ImportError:
    hjson_support = False
    logging.getLogger("click_extra").debug(
        "HJSON support disabled: install click-extra[hjson] to enable it."
    )


xml_support = True
try:
    import xmltodict
except ImportError:
    xml_support = False
    logging.getLogger("click_extra").debug(
        "XML support disabled: install click-extra[xml] to enable it."
    )


VCS_DIRS = (".git", ".hg", ".svn", ".bzr", "CVS", ".darcs")
"""VCS directory names used to identify version control system roots.

Includes:
- ``.git`` — Git
- ``.hg`` — Mercurial
- ``.svn`` — Subversion
- ``.bzr`` — Bazaar
- ``CVS`` — CVS (note: uppercase, no leading dot)
- ``.darcs`` — Darcs
"""


class ConfigFormat(Enum):
    """All configuration formats, associated to their support status.

    The first element of the tuple is a sequence of file extensions associated to the
    format. Patterns are fed to ``wcmatch.glob`` for matching, and are influenced by the
    flags set on the ``ConfigOption`` instance.

    The second element indicates whether the format is supported or not, depending on
    the availability of the required third-party packages. This evaluation is performed
    at runtime when this module is imported.

    .. caution::
        The order is important for both format members and file patterns. It defines the
        priority order in which formats are tried when multiple candidate files are found.

    .. todo::
        Add support for `JWCC
        <https://nigeltao.github.io/blog/2021/json-with-commas-comments.html>`_
        / `hujson <https://github.com/tailscale/hujson>`_ format?
    """

    TOML = (("*.toml",), True, "TOML")
    YAML = (("*.yaml", "*.yml"), yaml_support, "YAML")
    JSON = (("*.json",), True, "JSON")
    JSON5 = (("*.json5",), json5_support, "JSON5")
    JSONC = (("*.jsonc",), jsonc_support, "JSONC")
    HJSON = (("*.hjson",), hjson_support, "Hjson")
    INI = (("*.ini",), True, "INI")
    XML = (("*.xml",), xml_support, "XML")
    PYPROJECT_TOML = (("pyproject.toml",), True, "pyproject.toml")

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        """Human-friendly name of the format for display in messages."""
        return self.value[2]  # type: ignore[no-any-return]

    @property
    def enabled(self) -> bool:
        """Returns ``True`` if the format is supported, ``False`` otherwise."""
        return self.value[1]  # type: ignore[no-any-return]

    @property
    def patterns(self) -> tuple[str]:
        """Returns the default file patterns associated to the format."""
        return self.value[0]  # type: ignore[no-any-return]


CONFIG_OPTION_NAME = "config"
"""Hardcoded name of the configuration option.

This name is going to be shared by both the ``--config`` and ``--no-config`` options
below, so they can compete with each other to either set a path pattern or disable the
use of any configuration file at all.
"""


DEFAULT_EXCLUDED_PARAMS = (
    CONFIG_OPTION_NAME,
    "help",
    "show_params",
    "version",
)
"""Default parameter IDs to exclude from the configuration file.

Defaults to:

- ``--config`` option, which cannot be used to recursively load another configuration
  file.
- ``--help``, as it makes no sense to have the configurable file always forces a CLI to
  show the help and exit.
- ``--show-params`` flag, which is like ``--help`` and stops the CLI execution.
- ``--version``, which is not a configurable option *per-se*.
"""


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
    logger = logging.getLogger("click_extra")
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
    logger = logging.getLogger("click_extra")
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

        >>> from click_extra.config import flatten_config_keys, normalize_config_keys
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
    return ctx.find_root().meta.get(context.TOOL_CONFIG)


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
        sub = _make_schema_callable(hint, strict=strict, normalize=do_normalize)
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
    ``_make_schema_callable`` for dataclass schemas.
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
    # Detect opaque fields: dict-typed or nested-dataclass-typed.
    opaque = frozenset(
        f.name
        for f in all_fields
        if f.name not in result
        and (_is_mapping_type(hints.get(f.name)) or is_dataclass(hints.get(f.name)))
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
            sub = _make_schema_callable(hint, strict=strict)  # type: ignore[arg-type]
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


def _make_schema_callable(
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


class Sentinel(Enum):
    """Enum used to define sentinel values.

    .. note::
        This reuse the same pattern as ``Click._utils.Sentinel``.

    .. seealso::
        `PEP 661 - Sentinel Values <https://peps.python.org/pep-0661/>`_.
    """

    NO_CONFIG = object()
    VCS = object()  # noqa: PIE796

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"


NO_CONFIG = Sentinel.NO_CONFIG
"""Sentinel used to indicate that no configuration file must be used at all."""

VCS = Sentinel.VCS
"""Sentinel used to stop parent directory walking at the nearest VCS root."""


class ConfigOption(ExtraOption, ParamStructure):
    """A pre-configured option adding ``--config CONFIG_PATH``."""

    # excluded_params: frozenset[str]

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        metavar="CONFIG_PATH",
        type=UNPROCESSED,
        help=_(
            "Location of the configuration file. Supports local path with glob patterns "
            "or remote URL.",
        ),
        is_eager: bool = True,
        expose_value: bool = False,
        file_format_patterns: dict[ConfigFormat, Sequence[str] | str]
        | Iterable[ConfigFormat]
        | ConfigFormat
        | None = None,
        file_pattern_flags: int = fnmatch.NEGATE | fnmatch.SPLIT,
        roaming: bool = True,
        force_posix: bool = False,
        search_pattern_flags: int = (
            glob.GLOBSTAR
            | glob.FOLLOW
            | glob.DOTGLOB
            | glob.BRACE
            | glob.SPLIT
            | glob.GLOBTILDE
            | glob.NODIR
        ),
        search_parents: bool = False,
        stop_at: Path | str | Literal[Sentinel.VCS] | None = Sentinel.VCS,
        excluded_params: Iterable[str] | None = None,
        included_params: Iterable[str] | None = None,
        strict: bool = False,
        config_schema: type | Callable[[dict[str, Any]], Any] | None = None,
        schema_strict: bool = False,
        fallback_sections: Sequence[str] = (),
        **kwargs,
    ) -> None:
        """Takes as input a path to a file or folder, a glob pattern, or an URL.

        - ``is_eager`` is active by default so the ``callback`` gets the opportunity to
          set the ``default_map`` of the CLI before any other parameter is processed.

        - ``default`` is set to the value returned by ``self.default_pattern()``, which
          is a pattern combining the default configuration folder for the CLI (as
          returned by ``click.get_app_dir()``) and all supported file formats.

          .. attention::
            Default search pattern must follow the syntax of `wcmatch.glob
            <https://facelessuser.github.io/wcmatch/glob/#syntax>`_.

        - ``excluded_params`` are parameters which, if present in the configuration
          file, will be ignored and not applied to the CLI. Items are expected to be the
          fully-qualified ID of the parameter, as produced in the output of
          ``--show-params``. Will default to the value of ``DEFAULT_EXCLUDED_PARAMS``.

        - ``included_params`` is the inverse of ``excluded_params``: only the listed
          parameters will be loaded from the configuration file. Cannot be used together
          with ``excluded_params``.
        """
        logger = logging.getLogger("click_extra")

        if not param_decls:
            param_decls = ("--config", CONFIG_OPTION_NAME)

        # Setup supported file format patterns.
        self.file_format_patterns: dict[ConfigFormat, tuple[str, ...]]
        """Mapping of ``ConfigFormat`` to their associated file patterns.

        Can be a string or a sequence of strings. This defines which configuration file
        formats are supported, and which file patterns are used to search for them.

        .. note::
            All formats depending on third-party dependencies that are not installed
            will be ignored.

        .. attention::
            File patterns must follow the syntax of `wcmatch.fnmatch
            <https://facelessuser.github.io/wcmatch/fnmatch/#syntax>`_.
        """

        if isinstance(file_format_patterns, ConfigFormat):
            self.file_format_patterns = {
                file_format_patterns: file_format_patterns.patterns
            }
        elif isinstance(file_format_patterns, dict):
            self.file_format_patterns = {
                fmt: (patterns,) if isinstance(patterns, str) else tuple(patterns)
                for fmt, patterns in file_format_patterns.items()
            }
        elif isinstance(file_format_patterns, Iterable):
            self.file_format_patterns = {
                fmt: fmt.patterns for fmt in file_format_patterns
            }
        else:
            self.file_format_patterns = {fmt: fmt.patterns for fmt in ConfigFormat}

        # Check mapping of file formats to their patterns.
        for fmt, patterns in self.file_format_patterns.items():
            assert fmt in ConfigFormat
            assert isinstance(patterns, tuple)
            assert patterns, f"No pattern defined for {fmt}"
            assert all(isinstance(pat, str) and pat for pat in patterns)
            assert len(set(patterns)) == len(patterns), f"Duplicate patterns for {fmt}"

        # Filter out disabled formats.
        disabled = {fmt for fmt in self.file_format_patterns if not fmt.enabled}
        if disabled:
            logger.debug(f"Skip disabled {', '.join(map(str, disabled))}.")
            for fmt in disabled:
                del self.file_format_patterns[fmt]

        if not self.file_format_patterns:
            raise ValueError("No configuration format is enabled.")

        # Validate file pattern flags.
        if not file_pattern_flags & glob.SPLIT:
            logger.warning("Forcing SPLIT flag for file patterns.")
            file_pattern_flags |= glob.SPLIT

        self.file_pattern_flags = file_pattern_flags
        """Flags provided to all calls of ``wcmatch.fnmatch``.

        Applies to the matching of file names against supported format patterns
        specified in ``file_format_patterns``.

        .. important::
            The ``SPLIT`` flag is always forced, as our multi-pattern design relies on
            it.
        """

        # Setup the configuration for default folder search.
        self.roaming = roaming
        self.force_posix = force_posix
        """Configuration for default folder search.

        ``roaming`` and ``force_posix`` are `fed to click.get_app_dir()
        <https://click.palletsprojects.com/en/stable/api/#click.get_app_dir>`_ to
        determine the location of the default configuration folder.
        """

        kwargs.setdefault("default", self.default_pattern)

        # Force BRACE to ensure multi-format default patterns expand correctly.
        if not search_pattern_flags & glob.BRACE:
            logger.warning("Forcing BRACE flag for search patterns.")
            search_pattern_flags |= glob.BRACE

        # Force NODIR to optimize search for files only.
        if not search_pattern_flags & glob.NODIR:
            logger.warning("Forcing NODIR flag for search patterns.")
            search_pattern_flags |= glob.NODIR

        self.search_pattern_flags = search_pattern_flags
        """Flags provided to all calls of ``wcmatch.glob``.

        Applies to both the default pattern and any user-provided pattern.

        .. important::
            The ``BRACE`` flag is always forced, so that multi-format default
            patterns using ``{pat1,pat2,...}`` syntax expand correctly.

            The ``NODIR`` flag is always forced, to optimize the search for files only.
        """

        self.search_parents = search_parents
        """Indicates whether to walk back the tree of parent folders when searching for
        configuration files.
        """

        self.stop_at = stop_at
        """Boundary for parent directory walking.

        - ``None`` — walk up to filesystem root.
        - ``VCS`` — stop at the nearest VCS root (``.git`` or ``.hg``) (default).
        - A ``Path`` or ``str`` — stop at that directory.
        """

        if excluded_params is not None and included_params is not None:
            msg = "excluded_params and included_params are mutually exclusive."
            raise ValueError(msg)

        # If the user provided its own excluded params, freeze them now and store it
        # to prevent the dynamic default property to be called.
        if excluded_params is not None:
            self.excluded_params = frozenset(excluded_params)

        # Freeze and store included_params. The resolution into
        # excluded_params happens in params_objects.
        self.included_params: frozenset[str] | None = (
            frozenset(included_params) if included_params is not None else None
        )

        self.strict = strict
        """Defines the strictness of the configuration loading.

        - If ``True``, raise an error if the configuration file contain parameters not
          recognized by the CLI.
        - If ``False``, silently ignore unrecognized parameters.
        """

        self.config_schema = config_schema
        """Optional schema for structured access to configuration values.

        When set, the app's configuration section is extracted from the parsed
        config file, normalized (hyphens replaced with underscores), flattened
        (nested dicts joined with ``_``), and passed to this callable to produce
        a typed configuration object.

        Supports:

        - **Dataclass types** — detected via ``__dataclass_fields__``.  Keys
          are normalized, nested dicts are flattened, and the result is filtered
          to known fields before instantiation.  This allows nested config
          sections (e.g. ``[tool.myapp.sub-section]``) to map directly to flat
          dataclass fields (e.g. ``sub_section_key``).
        - **Any callable** ``dict → T`` — called directly with the raw
          dict.  Works with Pydantic's ``Model.model_validate``, attrs, or
          custom factory functions.  The caller is responsible for key
          normalization and flattening.

        The resulting object is stored in
        ``ctx.meta[click_extra.context.TOOL_CONFIG]`` and can be retrieved
        via `get_tool_config`.
        """

        self.schema_strict = schema_strict
        """Strictness for schema validation (separate from ``strict``).

        - If ``True``, raise ``ValueError`` when the config section contains keys
          that do not match any dataclass field (after normalization and
          flattening).  Only applies when ``config_schema`` is a dataclass.
        - If ``False``, silently ignore unrecognized keys.

        .. note::
            This is distinct from ``strict``, which controls whether
            ``merge_default_map`` rejects config keys not matching CLI
            parameters.  ``schema_strict`` validates against dataclass fields
            instead.
        """

        self.fallback_sections: Sequence[str] = tuple(fallback_sections)
        """Legacy section names to try when the app's own section is empty.

        Useful when a CLI tool has been renamed: old configuration files that
        still use ``[tool.old-name]`` (TOML), ``old-name:`` (YAML), or
        ``{"old-name": …}`` (JSON) are recognized with a deprecation warning.
        Works with all configuration formats.
        """

        self._config_schema_callable = _make_schema_callable(
            config_schema,
            strict=schema_strict,
        )

        kwargs.setdefault("callback", self.load_conf)

        super().__init__(
            param_decls=param_decls,
            metavar=metavar,
            type=type,
            help=help,
            is_eager=is_eager,
            expose_value=expose_value,
            **kwargs,
        )

        self._check_pattern_sanity()

    def _check_pattern_sanity(self) -> None:
        """Emit DEBUG-level logs for common ``ConfigOption`` misconfigurations.

        The checks help developers catch suboptimal patterns early when running
        with debug logging enabled. Four categories are covered:

        1. Broad glob + narrow (all-literal) format patterns.
        2. Literal default whose filename doesn't match any format pattern.
        3. Format/extension mismatch (unconditional).
        4. Dotfile referenced without ``DOTGLOB`` in ``search_pattern_flags``.
        """
        logger = logging.getLogger("click_extra")

        # --- Check 3 (unconditional): format/extension mismatch ---
        # Build a reverse map: extension → canonical ConfigFormats.
        ext_to_formats: dict[str, set[ConfigFormat]] = {}
        for fmt in ConfigFormat:
            for pat in fmt.patterns:
                ext = PurePosixPath(pat).suffix
                if ext:
                    ext_to_formats.setdefault(ext, set()).add(fmt)

        for fmt, patterns in self.file_format_patterns.items():
            for pat in patterns:
                ext = PurePosixPath(pat).suffix
                if ext and ext in ext_to_formats:
                    canonical = ext_to_formats[ext]
                    if fmt not in canonical:
                        canonical_names = ", ".join(sorted(f.name for f in canonical))
                        logger.debug(
                            f"Format pattern {pat!r} mapped to {fmt.name} but "
                            f"extension {ext!r} is canonically associated with "
                            f"{canonical_names}."
                        )

        # --- Checks 1, 2, 4 require an explicit default ---
        if not isinstance(self.default, str):
            return

        file_part = PurePosixPath(self.default).name
        default_is_magic = glob.is_magic(
            self.default.replace("\\", "/"), flags=self.search_pattern_flags
        )
        all_format_patterns = tuple(flatten(self.file_format_patterns.values()))

        # Check 1: broad glob + all-literal format patterns
        if default_is_magic:
            all_literal = all(
                not glob.is_magic(p.replace("\\", "/"), flags=self.search_pattern_flags)
                for p in all_format_patterns
            )
            if all_literal:
                logger.debug(
                    f"Broad search pattern {self.default!r} with literal format "
                    f"patterns {all_format_patterns!r}. The glob may scan many "
                    f"files only to discard most of them."
                )

        # Check 2: literal default that never matches any format pattern
        if not default_is_magic:
            pattern_str = "|".join(all_format_patterns)
            if not fnmatch.fnmatch(
                file_part, pattern_str, flags=self.file_pattern_flags
            ):
                logger.debug(
                    f"Literal search pattern {self.default!r} does not match "
                    f"any format pattern ({pattern_str!r}). No config will ever "
                    f"be found."
                )

        # Check 4: dotfile without DOTGLOB
        if not (self.search_pattern_flags & glob.DOTGLOB):
            dotfiles: list[str] = []
            if file_part.startswith("."):
                dotfiles.append(self.default)
            dotfiles.extend(
                pat
                for pat in all_format_patterns
                if PurePosixPath(pat).name.startswith(".")
            )
            if dotfiles:
                logger.debug(
                    f"Dotfile(s) {dotfiles!r} referenced but DOTGLOB is not set "
                    f"in search_pattern_flags. Hidden files may be skipped by "
                    f"glob."
                )

    @cached_property
    def excluded_params(self) -> frozenset[str]:  # type: ignore[override]
        """Generates the default list of fully-qualified IDs to exclude.

        .. danger::
            It is only called once to produce the default exclusion list if the user did
            not provided its own.

            It was not implemented in the constructor but made as a property, to allow
            for a just-in-time call within the current context. Without this trick we could
            not have fetched the CLI name.
        """
        cli = get_current_context().find_root().command
        return frozenset(
            f"{cli.name}{ParamStructure.SEP}{p}" for p in DEFAULT_EXCLUDED_PARAMS
        )

    @cached_property
    def file_pattern(self) -> str:
        """Compile all file patterns from the supported formats.

        Uses ``,`` (comma) notation to combine multiple patterns, suitable for
        ``wcmatch`` brace expansion (``{pat1,pat2,...}``).

        Returns a single pattern string.
        """
        patterns = unique(flatten(self.file_format_patterns.values()))
        return ",".join(patterns)

    def default_pattern(self) -> str:
        """Returns the default pattern used to search for the configuration file.

        Defaults to ``<app_dir>/{*.toml,*.json,*.ini}``. Where ``<app_dir>`` is
        produced by the `click.get_app_dir() method
        <https://click.palletsprojects.com/en/stable/api/#click.get_app_dir>`_.
        The result depends on OS and is influenced by the ``roaming`` and
        ``force_posix`` properties.

        Multiple file format patterns are wrapped with ``{…}`` brace-expansion
        syntax so that ``wcmatch.glob`` correctly applies the directory prefix
        to every sub-pattern.

        .. todo::
            Use `platformdirs <https://github.com/tox-dev/platformdirs>`_ for more
            advanced configuration folder detection?
        """
        ctx = get_current_context()
        cli_name = ctx.find_root().info_name
        if not cli_name:
            raise ValueError
        app_dir = Path(
            get_app_dir(cli_name, roaming=self.roaming, force_posix=self.force_posix),
        ).resolve()
        fp = self.file_pattern
        # Wrap multi-pattern with braces for BRACE expansion.
        suffix = f"{{{fp}}}" if "," in fp else fp
        return f"{app_dir}{os.path.sep}{suffix}"

    def get_help_extra(self, ctx: click.Context) -> click.types.OptionHelpExtra:
        """Replaces the default value of the configuration option.

        Display a pretty path that is relative to the user's home directory:

        .. code-block:: text

            ~/folder/my_cli/{*.toml,*.json,*.ini}

        Instead of the full absolute path:

        .. code-block:: text

            /home/user/folder/my_cli/{*.toml,*.json,*.ini}

        .. caution::
            This only applies when the ``GLOBTILDE`` flag is set in ``search_pattern_flags``.
        """
        extra = super().get_help_extra(ctx)
        default = self.get_default(ctx)
        if default is NO_CONFIG:
            extra["default"] = "disabled"
        elif self.search_pattern_flags & glob.GLOBTILDE:
            # When the default already starts with ``~`` (user-supplied tilde
            # pattern), use it as-is.  Passing through ``Path()`` would
            # normalise forward slashes to backslashes on Windows.
            default_str = str(default)
            extra["default"] = (
                default_str
                if default_str.startswith("~")
                else shrinkuser(Path(default))
            )
        else:
            extra["default"] = str(default)
        return extra

    @staticmethod
    def _find_vcs_root(start: Path) -> Path | None:
        """Walk up from ``start`` looking for a VCS root directory.

        Returns the directory containing one of the VCS directories defined in
        ``VCS_DIRS``, or ``None`` if no VCS root is found before reaching the
        filesystem root.
        """
        current = start if start.is_dir() else start.parent
        for directory in (current, *current.parents):
            if any((directory / vcs_dir).exists() for vcs_dir in VCS_DIRS):
                return directory
        return None

    def _resolve_stop_at(self, start_dir: Path) -> Path | None:
        """Resolve the ``stop_at`` value to an absolute ``Path`` or ``None``.

        - ``None`` → ``None`` (no boundary).
        - ``VCS`` → calls ``_find_vcs_root(start_dir)``.
        - ``Path`` or other ``str`` → resolves to absolute.
        """
        if self.stop_at is None:
            return None
        if self.stop_at is VCS:
            return self._find_vcs_root(start_dir)
        # Mypy cannot narrow ``Literal[Sentinel.VCS]`` via the ``is`` check above.
        assert isinstance(self.stop_at, (str, Path))
        return Path(self.stop_at).resolve()

    @staticmethod
    def _should_stop_walking(directory: Path, stop_at: Path | None) -> bool:
        """Return ``True`` if the parent-directory walk should stop.

        Stops when:
        - ``stop_at`` is set and ``directory`` is not equal to or a child of it.
        - The directory exists but is not readable.
        """
        if stop_at is not None:
            try:
                directory.relative_to(stop_at)
            except ValueError:
                return True
        return bool(directory.exists() and not os.access(directory, os.R_OK))

    def parent_patterns(self, pattern: str) -> Iterable[tuple[str | None, str]]:
        """Generate ``(root_dir, file_pattern)`` pairs for searching.

        Each yielded pair can be passed directly to
        ``glob.iglob(file_pattern, root_dir=root_dir)`` so that every
        sub-pattern (whether from ``BRACE`` or ``SPLIT`` expansion) is
        correctly scoped to the same directory.

        ``root_dir`` is ``None`` for entirely magic patterns that will be
        evaluated relative to the current working directory.

        Stops when reaching the root folder, the ``stop_at`` boundary, or an
        inaccessible directory.
        """
        logger = logging.getLogger("click_extra")

        # Normalize path separators for magic detection: on Windows, backslashes
        # in paths are mistaken for glob escape characters by wcmatch.
        def is_magic(p: str) -> bool:
            return glob.is_magic(p.replace("\\", "/"), flags=self.search_pattern_flags)

        # Split pattern into non-magic directory prefix (root_dir) and magic
        # file suffix (file_pattern).
        root_dir: Path | None
        if not is_magic(pattern):
            resolved = Path(pattern).resolve()
            if resolved.is_file():
                root_dir = resolved.parent
                file_pattern = resolved.name
            else:
                root_dir = resolved
                file_pattern = ""
        else:
            parts = Path(pattern).parts
            magic_idx = next(i for i, part in enumerate(parts) if is_magic(part))
            if magic_idx == 0:
                # Entirely magic (e.g., "{*.toml,*.yaml}").
                root_dir = None
                file_pattern = pattern
            else:
                root_dir = Path(*parts[:magic_idx]).resolve()
                file_pattern = str(Path(*parts[magic_idx:]))

        # Yield the original location.
        root_str = str(root_dir) if root_dir is not None else None
        yield root_str, file_pattern

        if not self.search_parents:
            return

        if root_dir is None:
            logger.debug("Entirely magic pattern, skipping parent search.")
            return

        logger.debug("Parent search enabled.")
        stop_at = self._resolve_stop_at(root_dir)

        for parent in root_dir.parents:
            if self._should_stop_walking(parent, stop_at):
                logger.debug(f"Stopped walking at {parent}")
                return
            yield str(parent), file_pattern

    def search_and_read_file(self, pattern: str) -> Iterable[tuple[Path | URL, str]]:
        """Search filesystem or URL for files matching the ``pattern``.

        If ``pattern`` is an URL, download its content. A pattern is considered an URL
        only if it validates as one and starts with ``http://`` or ``https://``. All
        other patterns are considered glob patterns for local filesystem search.

        Returns an iterator of the normalized location and its raw content, for each
        one matching the pattern. Only files are returned, directories are silently
        skipped.

        This method returns the raw content of all matching patterns, without trying to
        parse them. If the content is empty, it is still returned as-is.

        Also includes lookups into parents directories if ``self.search_parents`` is
        ``True``.

        Raises ``FileNotFoundError`` if no file was found after searching all locations.
        """
        logger = logging.getLogger("click_extra")
        files_found = 0

        # Check if the pattern is an URL.
        location = URL(pattern)
        location.normalize()
        if location and location.scheme in ("http", "https"):
            # It's an URL, try to download it.
            logger.debug(f"Download file from URL: {location}")
            with requests.get(str(location)) as response:
                if response.ok:
                    files_found += 1
                    # TODO: use mime-type to guess file format?
                    yield location, response.text
                else:
                    logger.warning(f"Can't download {location}: {response.reason}")

        # Not an URL, search local file system.
        else:
            logger.debug(f"Search filesystem for {pattern}")
            # wcmatch expect patterns to be written with Unix-like syntax by default,
            # even on Windows. See more details at:
            # https://facelessuser.github.io/wcmatch/glob/#windows-separators
            # https://github.com/facelessuser/wcmatch/issues/194
            if is_windows():
                win_path = Path(pattern)
                pattern = str(win_path.as_posix())
                logger.debug(f"Windows pattern converted from {win_path} to {pattern}")

            for root_dir, file_pattern in self.parent_patterns(pattern):
                for file in glob.iglob(
                    file_pattern,
                    root_dir=root_dir,
                    flags=self.search_pattern_flags,
                ):
                    base = Path(root_dir) if root_dir else Path()
                    file_path = (base / file).resolve()
                    logger.debug(f"Found candidate: {file_path}")
                    if not file_path.is_file():
                        logger.debug(f"Skipping non-file {file_path}")
                        continue
                    files_found += 1
                    yield file_path, file_path.read_text(encoding="utf-8")

        if not files_found:
            raise FileNotFoundError(f"No file found matching {pattern}")

    def parse_conf(
        self,
        content: str,
        formats: Sequence[ConfigFormat],
    ) -> Iterable[dict[str, Any] | None]:
        """Parse the ``content`` with the given ``formats``.

        Tries to parse the given raw ``content`` string with each of the given
        ``formats``, in order. Yields the resulting data structure for each
        successful parse.

        .. attention::
            Formats whose parsing raises an exception or does not return a ``dict``
            are considered a failure and are skipped.

            This follows the *parse, don't validate* principle.
        """
        logger = logging.getLogger("click_extra")

        conf = None
        for fmt in formats:
            try:
                match fmt:
                    case ConfigFormat.TOML:
                        conf = tomllib.loads(content)
                    case ConfigFormat.YAML:
                        conf = yaml.full_load(content)
                    case ConfigFormat.JSON:
                        conf = json.loads(content)
                    case ConfigFormat.JSON5:
                        conf = json5.loads(content)
                    case ConfigFormat.JSONC:
                        conf = jsonc.loads(content)
                    case ConfigFormat.HJSON:
                        conf = hjson.loads(content)
                    case ConfigFormat.INI:
                        conf = self.load_ini_config(content)
                    case ConfigFormat.XML:
                        conf = xmltodict.parse(content)
                    case ConfigFormat.PYPROJECT_TOML:
                        full_conf = tomllib.loads(content)
                        conf = full_conf.get("tool", {})

            except Exception as ex:  # noqa: BLE001
                logger.debug(f"{fmt} parsing failed: {ex}")
                continue

            # A parseable but empty configuration is expected to return an empty dict.
            if not isinstance(conf, dict) or conf is None:
                logger.debug(
                    f"{fmt} parsing failed: expecting a dict, got {conf!r} instead."
                )
                continue

            logger.debug(f"{fmt} parsing successful, got {conf!r}.")
            yield conf

    def _search_pyproject_cwd(
        self,
    ) -> tuple[Path, dict[str, Any]] | tuple[None, None]:
        """Search for ``pyproject.toml`` from CWD upward to the VCS root.

        Mimics the discovery behavior of uv, ruff, and mypy: start in the
        current working directory and walk up until a ``pyproject.toml`` is
        found or the VCS root (or filesystem root) is reached.

        Only runs when ``ConfigFormat.PYPROJECT_TOML`` is in
        ``file_format_patterns``.  Returns ``(path, parsed_tool_section)`` on
        success, or ``(None, None)`` if no valid ``pyproject.toml`` was found.
        """
        logger = logging.getLogger("click_extra")
        cwd = Path.cwd()
        stop_at = self._resolve_stop_at(cwd)

        for directory in (cwd, *cwd.parents):
            if self._should_stop_walking(directory, stop_at):
                logger.debug(f"pyproject.toml CWD search stopped at {directory}.")
                break

            candidate = directory / "pyproject.toml"
            if not candidate.is_file():
                continue

            logger.debug(f"Found {candidate}, parsing as pyproject.toml.")
            try:
                content = candidate.read_text(encoding="UTF-8")
            except OSError as ex:
                logger.debug(f"Cannot read {candidate}: {ex}")
                continue

            for conf in self.parse_conf(
                content, formats=(ConfigFormat.PYPROJECT_TOML,)
            ):
                if conf:
                    return candidate, conf
            logger.debug(f"{candidate} parsed but empty [tool] section.")

        return None, None

    def read_and_parse_conf(
        self,
        pattern: str,
    ) -> tuple[Path | URL, dict[str, Any]] | tuple[None, None]:
        """Search for a parseable configuration file.

        Returns the location and data structure of the first configuration matching the
        ``pattern``.

        Only return the first match that:

        - exists,
        - is a file,
        - is not empty,
        - match file format patterns,
        - can be parsed successfully, and
        - produce a non-empty data structure.

        Raises ``FileNotFoundError`` if no configuration file was found matching the
        criteria above.

        Returns ``(None, None)`` if files were found but none could be parsed.
        """
        logger = logging.getLogger("click_extra")

        for location, content in self.search_and_read_file(pattern):
            if isinstance(location, URL):
                filename = location.path_parts[-1]
            else:
                filename = location.name

            # Match file with formats.
            matching_formats = tuple(
                fmt
                for fmt, patterns in self.file_format_patterns.items()
                if fnmatch.fnmatch(filename, patterns, flags=self.file_pattern_flags)
            )

            # PYPROJECT_TOML is a specialization of TOML that unwraps [tool].
            # When both match, drop generic TOML so [tool] unwrapping takes effect.
            if (
                ConfigFormat.PYPROJECT_TOML in matching_formats
                and ConfigFormat.TOML in matching_formats
            ):
                matching_formats = tuple(
                    f for f in matching_formats if f is not ConfigFormat.TOML
                )

            if not matching_formats:
                logger.debug(f"{location} does not match {self.file_pattern}.")
                continue

            logger.debug(
                f"Parsing {location} with {','.join(map(str, matching_formats))}"
            )
            for conf in self.parse_conf(content, formats=matching_formats):
                if conf:
                    return location, conf
                logger.debug("Empty configuration, try next file.")

        return None, None

    def load_ini_config(self, content: str) -> dict[str, Any]:
        """Utility method to parse INI configuration file.

        Internal convention is to use a dot (``.``, as set by ``self.SEP``) in
        section IDs as a separator between levels. This is a workaround
        the limitation of ``INI`` format which doesn't allow for sub-sections.

        Returns a ready-to-use data structure.
        """
        ini_config = ConfigParser(interpolation=ExtendedInterpolation())
        ini_config.read_string(content)

        conf: dict[str, Any] = {}
        for section_id in ini_config.sections():
            # Extract all options of the section.
            sub_conf = {}
            for option_id in ini_config.options(section_id):
                # Fetch the expected type of the CLI parameter.
                try:
                    target_params = self.get_tree_value(
                        self.params_objects, section_id, option_id
                    )
                # The item in the INI config file does not correspond to any existing
                # parameter in the CLI structure.
                except KeyError:
                    target_type = None
                # The item in the INI config file corresponds to a single parameter
                # in the CLI structure.
                else:
                    # Because one variable name can be shared by multiple options, we
                    # need to fetch all of those we detected in the CLI structure.
                    assert isinstance(target_params, list)
                    # We deduplicate them to simplify the next steps. If we are lucky,
                    # all options sharing the same name also share the same type.
                    target_types = [self.get_param_type(p) for p in target_params]
                    dedup_types = set(target_types)

                    # XXX This case is tricky and not even covered in Click unittests.
                    if len(dedup_types) > 1:
                        raise ValueError(
                            f"Cannot handle the {target_types!r} types defined by the "
                            "multiple options associated to the "
                            f"[{section_id}]:{option_id} INI config item."
                        )
                    target_type = dedup_types.pop()

                value: Any

                if target_type in (None, str):
                    value = ini_config.get(section_id, option_id)

                elif target_type is int:
                    value = ini_config.getint(section_id, option_id)

                elif target_type is float:
                    value = ini_config.getfloat(section_id, option_id)

                elif target_type is bool:
                    value = ini_config.getboolean(section_id, option_id)

                # Types not natively supported by INI format are loaded as
                # JSON-serialized strings.
                elif target_type in (list, tuple, set, frozenset, dict):
                    value = json.loads(ini_config.get(section_id, option_id))

                else:
                    raise ValueError(
                        f"Cannot handle the conversion of [{section_id}]:{option_id} "
                        f"INI config item to {target_type} type."
                    )

                sub_conf[option_id] = value

            # Place collected options at the right level of the dict tree.
            conf = always_merger.merge(
                conf, self.init_tree_dict(*section_id.split(self.SEP), leaf=sub_conf)
            )

        return conf

    def _resolve_app_section(
        self,
        conf: dict[str, Any],
        app_name: str,
    ) -> dict[str, Any]:
        """Extract the app's configuration section from the parsed config.

        Looks for ``conf[app_name]`` first.  If empty, tries each name in
        ``fallback_sections`` in order, logging a deprecation warning on match.
        Works identically for all configuration formats.
        """
        logger = logging.getLogger("click_extra")
        section = conf.get(app_name)
        if isinstance(section, dict) and section:
            # Warn about leftover legacy sections.
            for old_name in self.fallback_sections:
                if old_name in conf:
                    logger.warning(
                        f"Config section [{old_name}] is deprecated and "
                        f"should be removed. Using [{app_name}]."
                    )
            return section

        for old_name in self.fallback_sections:
            section = conf.get(old_name)
            if isinstance(section, dict) and section:
                logger.warning(
                    f"Config section [{old_name}] is deprecated, "
                    f"migrate to [{app_name}]."
                )
                return section
        return {}

    def _apply_config_schema(
        self,
        ctx: click.Context,
        user_conf: dict[str, Any],
    ) -> None:
        """Apply the config schema to the app's section and store the result.

        Extracts the app-specific section from the full parsed config, passes
        it through the schema callable, and stores the result in
        ``ctx.meta[click_extra.context.TOOL_CONFIG]``.
        """
        if self._config_schema_callable is None:
            return
        app_name = ctx.find_root().command.name or ctx.info_name or ""
        app_section = self._resolve_app_section(user_conf, app_name)
        ctx.meta[context.TOOL_CONFIG] = self._config_schema_callable(
            app_section,
        )

    def merge_default_map(self, ctx: click.Context, user_conf: dict) -> None:
        """Save the user configuration into the context's ``default_map``.

        Merge the user configuration into the pre-computed template structure, which
        will filter out all unrecognized options not supported by the command. Then
        cleans up blank values and update the context's ``default_map``.

        Uses a `~collections.ChainMap` so each config source keeps its own layer.
        The first layer wins on key lookup, which makes parameter-source precedence
        explicit and future-proofs for multi-file config loading.
        """
        normalized_conf = _expand_dotted_keys(
            _strip_reserved_keys(user_conf), strict=self.strict
        )
        filtered_conf = _recursive_update(
            self.params_template, normalized_conf, self.strict
        )

        # Clean-up the conf by removing all blank values left-over by the template
        # structure.
        clean_conf = _remove_blanks(filtered_conf, remove_str=False)

        # Layer the config values on top of any existing default_map via ChainMap.
        # Click only calls .get() on default_map, which ChainMap supports with
        # first-match-wins semantics.
        local_conf = clean_conf.get(ctx.find_root().command.name, {})
        ctx.default_map = ChainMap(local_conf, ctx.default_map or {})

    def load_conf(
        self,
        ctx: click.Context,
        param: click.Parameter,
        path_pattern: str | Path | Literal[Sentinel.NO_CONFIG],
    ) -> None:
        """Fetch parameter values from a configuration file and set them as defaults.

        User configuration is merged to the `context's default_map
        <https://click.palletsprojects.com/en/stable/commands/#overriding-defaults>`_,
        `like Click does
        <https://click.palletsprojects.com/en/stable/commands/#context-defaults>`_.

        By relying on Click's ``default_map``, we make sure that precedence is
        respected. Direct CLI parameters, environment variables or interactive prompts
        take precedence over any values from the config file.

        ..hint::
            Once loading is complete, the resolved file path and its full parsed content
            are stored in ``ctx.meta[click_extra.context.CONF_SOURCE]`` and
            ``ctx.meta[click_extra.context.CONF_FULL]`` respectively. This is the
            recommended way to identify which configuration file was loaded.

            We intentionally do not
            add a custom ``ParameterSource.CONFIG_FILE`` enum member: ``ParameterSource``
            is a closed enum in Click, and monkeypatching it would be fragile. Besides,
            config values end up in ``default_map``, so Click already reports them as
            ``ParameterSource.DEFAULT_MAP``, which is accurate.
        """
        logger = logging.getLogger("click_extra")

        # In this function we would like to inform the user of what we're doing.
        # In theory we could use logger.info() for that, but the logger is stuck to its
        # default WARNING level at this point, because the defaults have not been
        # loaded yet. So we use echo() to print messages to stderr instead.
        info_msg = partial(echo, err=True)

        assert self.name is not None  # Always set for Option subclasses.

        # Listed explicitly: the ParameterSource IntEnum ordering does not
        # cleanly split explicit from non-explicit sources, since DEFAULT and
        # DEFAULT_MAP fall between the user-set members.
        explicit_sources = {
            ParameterSource.COMMANDLINE,
            ParameterSource.ENVIRONMENT,
            ParameterSource.PROMPT,
        }

        if path_pattern is NO_CONFIG:
            logger.debug(f"{NO_CONFIG} received.")
            source = ctx.get_parameter_source(self.name)
            explicit = source is not None and source in explicit_sources
            if explicit:
                info_msg("Skip configuration file loading altogether.")
            else:
                logger.debug("Configuration file autodiscovery disabled by default.")
            return

        conf_source = ctx.get_parameter_source(self.name)
        explicit_conf = conf_source is not None and conf_source in explicit_sources

        # Print configuration location to the user if it was explicitly set.
        # Normalize to string to both allow parsing as a glob pattern or URL.
        if isinstance(path_pattern, Path):
            # Normalize the path without checking for its existence.
            path_pattern = str(path_pattern.resolve(strict=False))
        # NO_CONFIG was handled above with an early return. Help mypy see that.
        assert isinstance(path_pattern, str)
        message = f"Load configuration matching {path_pattern}"
        if explicit_conf:
            info_msg(message)
        else:
            logger.debug(message)

        # Search for pyproject.toml from CWD upward before the standard
        # app-dir search.  This matches the discovery behavior of uv, ruff,
        # and mypy.  Only runs on auto-discovery (not explicit --config).
        conf_path: Path | URL | None = None
        user_conf = None
        if (
            not explicit_conf
            and ConfigFormat.PYPROJECT_TOML in self.file_format_patterns
        ):
            conf_path, user_conf = self._search_pyproject_cwd()
            if conf_path is not None:
                logger.debug(f"Using {conf_path} from CWD search.")

        # Fall back to the standard app-dir search if CWD search found nothing.
        if user_conf is None:
            try:
                conf_path, user_conf = self.read_and_parse_conf(path_pattern)
            # Exit the CLI if no user-provided config file was found. Else, it
            # means we were just trying to automatically discover a config file
            # with the default pattern, so we can just log it and continue.
            except FileNotFoundError:
                message = "No configuration file found."
                if explicit_conf:
                    logger.critical(message)
                    ctx.exit(2)
                else:
                    logger.debug(message)
            else:
                if user_conf is None:
                    formats = list(map(str, self.file_format_patterns))
                    message = (
                        f"Error parsing file as "
                        f"{', '.join(formats[:-1])} or {formats[-1]}."
                    )
                    if explicit_conf:
                        logger.critical(message)
                        ctx.exit(2)
                    else:
                        logger.debug(message)

        # Apply the loaded configuration (from CWD or app-dir search).
        if user_conf is not None:
            logger.debug(f"Parsed user configuration: {user_conf}")
            logger.debug(f"Initial defaults: {ctx.default_map}")
            self.merge_default_map(ctx, user_conf)
            logger.debug(f"New defaults: {ctx.default_map}")
            self._apply_config_schema(ctx, user_conf)

        # When a schema is configured but no config file was found, still
        # produce the default instance so get_tool_config() never returns None.
        elif self._config_schema_callable is not None:
            logger.debug("No config file found; instantiating schema defaults.")
            self._apply_config_schema(ctx, {})

        # Expose the resolved config file path and its full parsed content via
        # ctx.meta, so downstream CLI code can inspect what was loaded and from where.
        # See the load_conf docstring for why we use ctx.meta instead of a custom
        # ParameterSource enum member.
        ctx.meta[context.CONF_SOURCE] = conf_path
        ctx.meta[context.CONF_FULL] = user_conf


class NoConfigOption(ExtraOption):
    """A pre-configured option adding ``--no-config``.

    This option is supposed to be used alongside the ``--config`` option
    (``ConfigOption``) to allow users to explicitly disable the use of any
    configuration file.

    This is especially useful to debug side-effects caused by autodetection of
    configuration files.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        type=UNPROCESSED,
        help=_(
            "Ignore all configuration files and only use command line parameters and "
            "environment variables.",
        ),
        is_flag=True,
        flag_value=NO_CONFIG,
        is_eager=True,
        expose_value=False,
        **kwargs,
    ) -> None:
        """
        .. seealso::
            An alternative implementation of this class would be to create a custom
            `click.ParamType
            <https://click.palletsprojects.com/en/stable/api/#click.ParamType>`_
            instead of a custom ``Option`` subclass. `Here is for example
            <https://github.com/pallets/click/issues/3024#issuecomment-3146511356>`_.
        """
        if not param_decls:
            param_decls = ("--no-config", CONFIG_OPTION_NAME)

        kwargs.setdefault("callback", self.check_sibling_config_option)

        super().__init__(
            param_decls=param_decls,
            type=type,
            help=help,
            is_flag=is_flag,
            flag_value=flag_value,
            is_eager=is_eager,
            expose_value=expose_value,
            **kwargs,
        )

    def check_sibling_config_option(
        self, ctx: click.Context, param: click.Parameter, value: int
    ) -> None:
        """Ensure that this option is used alongside a ``ConfigOption`` instance."""
        config_option = search_params(ctx.command.params, ConfigOption)
        if config_option is None:
            raise RuntimeError(
                f"{'/'.join(param.opts)} {self.__class__.__name__} must be used "
                f"alongside {ConfigOption.__name__}."
            )


class ValidateConfigOption(ExtraOption):
    """A pre-configured option adding ``--validate-config CONFIG_PATH``.

    Loads the config file at the given path, validates it against the CLI's
    parameter structure in strict mode, reports results, and exits.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        type: click.ParamType | Any = ClickPath(
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
        is_eager: bool = True,
        expose_value: bool = False,
        help: str = _("Validate the configuration file and exit."),
        **kwargs: Any,
    ) -> None:
        if not param_decls:
            param_decls = ("--validate-config",)

        kwargs.setdefault("callback", self.validate_config)

        super().__init__(
            param_decls=param_decls,
            type=type,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )

    def validate_config(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: str | None,
    ) -> None:
        """Load, parse, and validate the configuration file, then exit."""
        if not value:
            return

        info_msg: Callable[..., None] = partial(echo, err=True)

        # Find the sibling ConfigOption to reuse its parsing machinery.
        result = search_params(ctx.command.params, ConfigOption)
        if not isinstance(result, ConfigOption):
            raise TypeError(
                f"{'/'.join(param.opts)} {self.__class__.__name__} must be "
                f"used alongside {ConfigOption.__name__}."
            )
        config_option = result

        # Read and parse the config file.
        try:
            _conf_path, user_conf = config_option.read_and_parse_conf(value)
        except FileNotFoundError:
            info_msg(f"Configuration file not found: {value}")
            ctx.exit(2)

        if user_conf is None:
            formats = list(map(str, config_option.file_format_patterns))
            info_msg(
                f"Error parsing {value} as {', '.join(formats[:-1])} or {formats[-1]}."
            )
            ctx.exit(2)

        # Validate in strict mode — _recursive_update raises ValueError
        # on unrecognized keys.
        try:
            _recursive_update(
                config_option.params_template,
                _expand_dotted_keys(_strip_reserved_keys(user_conf), strict=True),
                strict=True,
            )
        except ValueError as exc:
            info_msg(f"Configuration validation error: {exc}")
            ctx.exit(1)

        info_msg(f"Configuration file {value} is valid.")
        ctx.exit(0)
