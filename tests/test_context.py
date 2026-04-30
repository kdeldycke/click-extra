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

"""Tests for :mod:`click_extra.context`.

Covers four surfaces the module exposes:

- The registry of ``ctx.meta`` key constants.
- The :func:`get` / :func:`set` helpers that read and write them.
- :class:`ExtraContext`, Click Extra's :class:`cloup.Context` subclass.
- :class:`_LazyMetaDict`, the lazy ``ctx._meta`` proxy used by
  :class:`~click_extra.version.ExtraVersionOption`.
"""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from click_extra import context
from click_extra.colorize import HelpExtraFormatter
from click_extra.context import META_NAMESPACE, ExtraContext, _LazyMetaDict


# --- META key registry ------------------------------------------------------

KEY_CONSTANTS: tuple[tuple[str, str], ...] = (
    ("RAW_ARGS", "click_extra.raw_args"),
    ("CONF_SOURCE", "click_extra.conf_source"),
    ("CONF_FULL", "click_extra.conf_full"),
    ("TOOL_CONFIG", "click_extra.tool_config"),
    ("VERBOSITY_LEVEL", "click_extra.verbosity_level"),
    ("VERBOSITY", "click_extra.verbosity"),
    ("VERBOSE", "click_extra.verbose"),
    ("START_TIME", "click_extra.start_time"),
    ("JOBS", "click_extra.jobs"),
    ("TABLE_FORMAT", "click_extra.table_format"),
    ("SORT_BY", "click_extra.sort_by"),
    ("THEME", "click_extra.theme.active"),
)
"""Pairs of ``(attribute name, raw string key)`` for every registered
``ctx.meta`` entry. Single source of truth used by every parametrized
registry test below."""


@pytest.mark.parametrize(("attr", "expected"), KEY_CONSTANTS)
def test_key_constant_value(attr: str, expected: str) -> None:
    """Each registered constant binds to its documented string value.

    Pins the spelling of every key so a rename of the literal does not
    silently break downstream code that reads ``ctx.meta["click_extra.X"]``.
    """
    assert getattr(context, attr) == expected


@pytest.mark.parametrize("key", [v for _, v in KEY_CONSTANTS])
def test_key_uses_namespace_prefix(key: str) -> None:
    """Every registered key sits under :data:`META_NAMESPACE`."""
    assert key.startswith(META_NAMESPACE)


def test_keys_are_unique() -> None:
    """No two registry constants share a string value."""
    values = [v for _, v in KEY_CONSTANTS]
    assert len(set(values)) == len(values)


def test_registry_covers_all_module_constants() -> None:
    """``KEY_CONSTANTS`` lists every public namespace-prefixed constant.

    Drift detector: when a new ``ctx.meta`` key is added to
    :mod:`click_extra.context` but not to ``KEY_CONSTANTS``, this test fails
    so the maintainer remembers to update both sides.
    """
    declared = {attr for attr, _ in KEY_CONSTANTS}
    found = {
        name
        for name in dir(context)
        if name.isupper()
        and not name.startswith("_")
        and isinstance(getattr(context, name), str)
        and getattr(context, name).startswith(META_NAMESPACE)
        and name != "META_NAMESPACE"
    }
    assert found == declared


# --- get / set helpers ------------------------------------------------------


def test_get_returns_default_for_missing_key() -> None:
    """:func:`context.get` mirrors ``dict.get`` semantics."""

    @click.command
    @click.pass_context
    def cli(ctx):
        sentinel = object()
        assert context.get(ctx, "click_extra.does_not_exist", sentinel) is sentinel
        assert context.get(ctx, "click_extra.does_not_exist") is None

    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0


def test_set_then_get_round_trip() -> None:
    """:func:`context.set` is observable through :func:`context.get`."""

    @click.command
    @click.pass_context
    def cli(ctx):
        context.set(ctx, context.JOBS, 7)
        assert context.get(ctx, context.JOBS) == 7

    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0


# --- ExtraContext -----------------------------------------------------------


def test_extra_context_uses_help_extra_formatter() -> None:
    """:class:`ExtraContext` installs Click Extra's colorized formatter."""
    assert ExtraContext.formatter_class is HelpExtraFormatter


def test_extra_context_meta_kwarg_seeds_ctx_meta() -> None:
    """The ``meta=`` kwarg populates ``ctx.meta`` at construction time."""
    payload = {"x.foo": "bar", "x.baz": 42}
    ctx = ExtraContext(click.Command("test"), meta=payload)
    for key, value in payload.items():
        assert ctx.meta[key] == value


def test_extra_context_meta_kwarg_omitted_leaves_meta_empty() -> None:
    """Without ``meta=``, ``ctx.meta`` is an empty dict, not ``None``."""
    ctx = ExtraContext(click.Command("test"))
    assert ctx.meta == {}


@pytest.mark.parametrize(
    ("parent_color", "child_color", "expected"),
    [
        # Root context, color= explicitly set.
        pytest.param(None, True, True, id="root-explicit-true"),
        pytest.param(None, False, False, id="root-explicit-false"),
        # Root context, color= unset → defaults to True.
        pytest.param(None, None, True, id="root-default-true"),
        # Child context inherits parent color when own color= unset.
        pytest.param(True, None, True, id="child-inherits-true"),
        pytest.param(False, None, False, id="child-inherits-false"),
        # Child context with explicit color= overrides the parent.
        pytest.param(True, False, False, id="child-overrides-to-false"),
        pytest.param(False, True, True, id="child-overrides-to-true"),
    ],
)
def test_extra_context_color(
    parent_color: bool | None,
    child_color: bool | None,
    expected: bool,
) -> None:
    """:class:`ExtraContext` color resolution covers every parent/child path.

    Root contexts without an explicit ``color=`` default to ``True`` (so help
    screens stay colorized when piped). Child contexts inherit the parent's
    color unless they override it explicitly.
    """
    parent = None
    if parent_color is not None:
        parent = ExtraContext(click.Command("parent"), color=parent_color)

    kwargs: dict[str, object] = {}
    if parent is not None:
        kwargs["parent"] = parent
    if child_color is not None:
        kwargs["color"] = child_color

    ctx = ExtraContext(click.Command("child"), **kwargs)
    assert ctx.color is expected


# --- _LazyMetaDict ----------------------------------------------------------


class _SourceSpy:
    """Source object for ``_LazyMetaDict`` tests: counts attribute accesses."""

    def __init__(self) -> None:
        self.access_count = {"alpha": 0, "beta": 0}

    @property
    def alpha(self) -> str:
        self.access_count["alpha"] += 1
        return "alpha-value"

    @property
    def beta(self) -> str:
        self.access_count["beta"] += 1
        return "beta-value"


def test_lazy_meta_dict_resolves_on_first_access() -> None:
    """Reading a lazy key triggers exactly one source attribute access."""
    source = _SourceSpy()
    d = _LazyMetaDict({}, source, ("alpha", "beta"))

    assert source.access_count["alpha"] == 0
    assert d["click_extra.alpha"] == "alpha-value"
    assert source.access_count["alpha"] == 1


def test_lazy_meta_dict_caches_after_resolution() -> None:
    """Subsequent reads of the same lazy key do not re-hit the source."""
    source = _SourceSpy()
    d = _LazyMetaDict({}, source, ("alpha",))

    d["click_extra.alpha"]
    d["click_extra.alpha"]
    d["click_extra.alpha"]
    assert source.access_count["alpha"] == 1


def test_lazy_meta_dict_get_resolves_lazy_key() -> None:
    """``.get(lazy_key)`` triggers resolution like ``__getitem__``."""
    source = _SourceSpy()
    d = _LazyMetaDict({}, source, ("alpha",))

    assert d.get("click_extra.alpha") == "alpha-value"
    assert source.access_count["alpha"] == 1


def test_lazy_meta_dict_get_returns_default_for_unknown_key() -> None:
    """``.get(unknown, default)`` returns the default without touching source."""
    source = _SourceSpy()
    d = _LazyMetaDict({}, source, ("alpha",))

    sentinel = object()
    assert d.get("click_extra.unknown", sentinel) is sentinel
    assert source.access_count["alpha"] == 0


def test_lazy_meta_dict_contains_includes_lazy_keys_without_resolving() -> None:
    """``in`` returns ``True`` for declared lazy keys before any resolution."""
    source = _SourceSpy()
    d = _LazyMetaDict({}, source, ("alpha",))

    assert "click_extra.alpha" in d
    assert source.access_count["alpha"] == 0


def test_lazy_meta_dict_preserves_base_entries() -> None:
    """Entries from the wrapped base dict remain accessible."""
    source = _SourceSpy()
    d = _LazyMetaDict({"existing.key": "existing-value"}, source, ("alpha",))

    assert d["existing.key"] == "existing-value"
    assert "existing.key" in d
    assert d.get("existing.key") == "existing-value"


def test_lazy_meta_dict_independent_keys_resolve_independently() -> None:
    """Resolving one lazy key does not resolve sibling lazy keys."""
    source = _SourceSpy()
    d = _LazyMetaDict({}, source, ("alpha", "beta"))

    d["click_extra.alpha"]
    assert source.access_count["alpha"] == 1
    assert source.access_count["beta"] == 0
