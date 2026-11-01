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

"""Tests for :mod:`click_extra.context`, and the context class that carries it.

Covers four surfaces:

- The registry of ``ctx.meta`` key constants.
- The :func:`~click_extra.context.get` / :func:`~click_extra.context.set`
  helpers that read and write them.
- :class:`~click_extra.commands.Context`, Click Extra's :class:`cloup.Context`
  subclass, defined in :mod:`click_extra.commands`.
- :class:`_LazyMetaDict`, the lazy ``ctx._meta`` proxy used by
  :class:`~click_extra.version.VersionOption`.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

import click_extra
from click_extra import context
from click_extra.color import COLOR_ENVVARS
from click_extra.commands import POSIXLY_CORRECT_ENVVAR, Command, Context
from click_extra.context import META_NAMESPACE, _LazyMetaDict
from click_extra.highlight import HelpFormatter

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any


# --- META key registry ------------------------------------------------------

KEY_CONSTANTS: tuple[tuple[str, str], ...] = (
    ("RAW_ARGS", "click_extra.raw_args"),
    ("INVOCATION_NAME", "click_extra.invocation_name"),
    ("CONF_SOURCE", "click_extra.conf_source"),
    ("CONF_FULL", "click_extra.conf_full"),
    ("CONF_SOURCES", "click_extra.conf_sources"),
    ("TOOL_CONFIG", "click_extra.tool_config"),
    ("SUBCOMMANDS_APPLIED", "click_extra.subcommands_applied"),
    ("VERBOSITY_LEVEL", "click_extra.verbosity_level"),
    ("VERBOSITY", "click_extra.verbosity"),
    ("DEBUG", "click_extra.debug"),
    ("VERBOSE", "click_extra.verbose"),
    ("QUIET", "click_extra.quiet"),
    ("START_TIME", "click_extra.start_time"),
    ("JOBS", "click_extra.jobs"),
    ("TABLE_FORMAT", "click_extra.table_format"),
    ("SORT_BY", "click_extra.sort_by"),
    ("TABLE_SORT_KEY", "click_extra.table_sort_key"),
    ("COLUMNS", "click_extra.columns"),
    ("THEME", "click_extra.theme.active"),
    ("THEME_OVERRIDES", "click_extra.theme.overrides"),
    ("TELEMETRY", "click_extra.telemetry"),
    ("PROGRESS", "click_extra.progress"),
    ("ACCESSIBLE", "click_extra.accessible"),
    ("ZERO_EXIT", "click_extra.zero_exit"),
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
    """Every registered key sits under :data:`~click_extra.context.META_NAMESPACE`."""
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


NON_META_KEYS = frozenset({
    # Dataclass field metadata keys of configuration schemas.
    "click_extra.config_path",
    "click_extra.extension",
    "click_extra.normalize_keys",
    # The types of Sphinx warnings.
    "click_extra.config_docstring_heading",
    "click_extra.todo_unrendered",
})
"""Literals sharing :data:`~click_extra.context.META_NAMESPACE` that name no
``ctx.meta`` key."""


def _names_a_module_attribute(value: str) -> bool:
    """Whether ``value`` is the dotted path of an object a submodule defines.

    A lazy subcommand target or a monkeypatch path shares the namespace of the
    ``ctx.meta`` keys, but names an attribute of an importable submodule. The
    package root is never a match: it binds a submodule of every name.
    """
    module_name, _, attribute = value.rpartition(".")
    if module_name in ("", "click_extra"):
        return False
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return hasattr(module, attribute)


def _string_literals(tree: ast.AST) -> list[tuple[int, str]]:
    """The line and value of each string literal of ``tree`` but docstrings."""
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_meta_keys_are_spelled_in_context_only() -> None:
    """No module but :mod:`click_extra.context` spells a ``ctx.meta`` key.

    Every other module reads its keys from there: none builds one from
    :data:`~click_extra.context.META_NAMESPACE`, or writes one as a literal.
    """
    package = Path(click_extra.__file__).parent
    # A dotted name, not a message that happens to start with the package.
    key_re = re.compile(rf"{re.escape(META_NAMESPACE)}[a-z_][a-z0-9_.]*")
    found = []
    for path in sorted(package.rglob("*.py")):
        if path.name == "context.py" and path.parent == package:
            continue
        tree = ast.parse(path.read_text(encoding="UTF-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Name) and node.id == "META_NAMESPACE") or (
                isinstance(node, ast.Attribute) and node.attr == "META_NAMESPACE"
            ):
                found.append(f"{path.name}:{node.lineno}: META_NAMESPACE")
        for lineno, value in _string_literals(tree):
            if (
                key_re.fullmatch(value)
                and value not in NON_META_KEYS
                and not _names_a_module_attribute(value)
            ):
                found.append(f"{path.name}:{lineno}: {value!r}")
    assert not found


def test_internal_keys_are_private_and_unique() -> None:
    """The keys only Click Extra reads sit under ``click_extra._``, apart from the
    public ones."""
    internal = {
        name: getattr(context, name)
        for name in dir(context)
        if name.startswith("_")
        and name[1:].isupper()
        and isinstance(getattr(context, name), str)
    }
    assert internal
    for value in internal.values():
        assert value.startswith(f"{META_NAMESPACE}_")
    public = {v for _, v in KEY_CONSTANTS}
    assert len(set(internal.values())) == len(internal)
    assert not public & set(internal.values())


# --- get / set helpers ------------------------------------------------------


def test_get_returns_default_for_missing_key() -> None:
    """:func:`~click_extra.context.get` mirrors ``dict.get`` semantics."""

    @click.command
    @click.pass_context
    def cli(ctx):
        sentinel = object()
        assert context.get(ctx, "click_extra.does_not_exist", sentinel) is sentinel
        assert context.get(ctx, "click_extra.does_not_exist") is None

    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0


def test_set_then_get_round_trip() -> None:
    """:func:`~click_extra.context.set` is observable through
    :func:`~click_extra.context.get`.
    """

    @click.command
    @click.pass_context
    def cli(ctx):
        context.set(ctx, context.JOBS, 7)
        assert context.get(ctx, context.JOBS) == 7

    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0


def test_setdefault_stores_the_factory_value_once() -> None:
    """:func:`~click_extra.context.setdefault` creates a missing value, then keeps
    it."""
    calls = []

    def basket() -> set[str]:
        calls.append(1)
        return set()

    @click.command
    @click.pass_context
    def cli(ctx):
        first = context.setdefault(ctx, "click_extra.basket", basket)
        first.add("apple")
        second = context.setdefault(ctx, "click_extra.basket", basket)
        assert second is first
        assert second == {"apple"}
        assert len(calls) == 1

    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0


# --- Context -----------------------------------------------------------


def test_context_uses_help_formatter() -> None:
    """:class:`~click_extra.commands.Context` installs Click Extra's colorized
    formatter.
    """
    assert Context.formatter_class is HelpFormatter


def test_context_meta_kwarg_seeds_ctx_meta() -> None:
    """The ``meta=`` kwarg populates ``ctx.meta`` at construction time."""
    payload = {"x.foo": "bar", "x.baz": 42}
    ctx = Context(click.Command("test"), meta=payload)
    for key, value in payload.items():
        assert ctx.meta[key] == value


def test_context_meta_kwarg_omitted_leaves_meta_empty() -> None:
    """Without ``meta=``, ``ctx.meta`` is an empty dict, not ``None``."""
    ctx = Context(click.Command("test"))
    assert ctx.meta == {}


@pytest.mark.parametrize(
    ("parent_color", "child_color", "expected"),
    [
        # Root context, color= explicitly set.
        pytest.param(None, True, True, id="root-explicit-true"),
        pytest.param(None, False, False, id="root-explicit-false"),
        # Root context, color= unset → GNU auto default (None) with no color env var.
        pytest.param(None, None, None, id="root-default-auto"),
        # Child context inherits parent color when own color= unset.
        pytest.param(True, None, True, id="child-inherits-true"),
        pytest.param(False, None, False, id="child-inherits-false"),
        # Child context with explicit color= overrides the parent.
        pytest.param(True, False, False, id="child-overrides-to-false"),
        pytest.param(False, True, True, id="child-overrides-to-true"),
    ],
)
def test_context_color(
    monkeypatch: pytest.MonkeyPatch,
    parent_color: bool | None,
    child_color: bool | None,
    expected: bool | None,
) -> None:
    """:class:`~click_extra.commands.Context` color resolution covers every
    parent/child path.

    Root contexts without an explicit ``color=`` resolve the GNU auto default: with no
    color environment variable they stay at ``None`` (TTY detection). Child contexts
    inherit the parent's color unless they override it explicitly.
    """
    # Clear color env vars so a parentless context's auto default is deterministic.
    for var in COLOR_ENVVARS:
        monkeypatch.delenv(var, raising=False)

    parent = None
    if parent_color is not None:
        parent = Context(click.Command("parent"), color=parent_color)

    kwargs: dict[str, Any] = {}
    if parent is not None:
        kwargs["parent"] = parent
    if child_color is not None:
        kwargs["color"] = child_color

    ctx = Context(click.Command("child"), **kwargs)
    assert ctx.color is expected


# --- Context POSIXLY_CORRECT -------------------------------------------


@pytest.mark.parametrize(
    ("env_present", "expected"),
    [
        pytest.param(False, True, id="unset-keeps-interspersing"),
        pytest.param(True, False, id="set-forbids-interspersing"),
    ],
)
def test_context_posixly_correct(
    monkeypatch: pytest.MonkeyPatch,
    env_present: bool,
    expected: bool,
) -> None:
    """``POSIXLY_CORRECT`` flips ``allow_interspersed_args`` off when present.

    A plain ``click.Command`` defaults the flag to ``True``, so the unset case
    leaves interspersing enabled and the set case disables it.
    """
    if env_present:
        monkeypatch.setenv(POSIXLY_CORRECT_ENVVAR, "1")
    else:
        monkeypatch.delenv(POSIXLY_CORRECT_ENVVAR, raising=False)

    ctx = Context(click.Command("test"))
    assert ctx.allow_interspersed_args is expected


def test_posixly_correct_presence_overrides_explicit_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty ``POSIXLY_CORRECT`` still wins over an explicit ``True``.

    Presence alone triggers POSIX parsing (matching GNU getopt), regardless of
    value, and it takes precedence over a developer-supplied
    ``allow_interspersed_args=True``.
    """
    monkeypatch.setenv(POSIXLY_CORRECT_ENVVAR, "")

    ctx = Context(click.Command("test"), allow_interspersed_args=True)
    assert ctx.allow_interspersed_args is False


def test_posixly_correct_stops_option_parsing_at_first_argument() -> None:
    """End-to-end: parsing stops at the first positional under POSIXLY_CORRECT.

    Without the variable, the option interleaves with arguments (GNU style).
    With it set, the first positional ends option parsing, so the option keeps
    its default and the remaining tokens fall into the variadic argument.
    """

    @click.command(cls=Command)
    @click.option("--greeting", default="Hello")
    @click.argument("names", nargs=-1)
    @click.pass_context
    def hello(ctx, greeting, names):
        click.echo(repr((greeting, names)))

    runner = CliRunner()
    args = ["alice", "--greeting", "Hi", "bob"]

    gnu = runner.invoke(hello, args, env={POSIXLY_CORRECT_ENVVAR: None})
    assert gnu.exit_code == 0
    assert gnu.output == "('Hi', ('alice', 'bob'))\n"

    posix = runner.invoke(hello, args, env={POSIXLY_CORRECT_ENVVAR: "1"})
    assert posix.exit_code == 0
    assert posix.output == "('Hello', ('alice', '--greeting', 'Hi', 'bob'))\n"


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


LAZY_ENTRIES = {
    "existing.key": "existing-value",
    "click_extra.alpha": "alpha-value",
    "click_extra.beta": "beta-value",
}
"""Every entry of the lazy dicts below once resolved, in iteration order."""


def _lazy_dict(source: _SourceSpy) -> _LazyMetaDict:
    """A lazy dict holding one stored entry and two pending lazy keys."""
    return _LazyMetaDict({"existing.key": "existing-value"}, source, ("alpha", "beta"))


def test_lazy_meta_dict_lists_pending_keys_without_resolving() -> None:
    """``len()``, iteration and ``keys()`` count the keys ``in`` claims.

    Listing a key does not read its value, so nothing resolves.
    """
    source = _SourceSpy()
    d = _lazy_dict(source)

    assert all(key in d for key in LAZY_ENTRIES)
    assert len(d) == len(LAZY_ENTRIES)
    assert list(d) == list(LAZY_ENTRIES)
    assert list(d.keys()) == list(LAZY_ENTRIES)
    assert list(reversed(d)) == list(reversed(LAZY_ENTRIES))
    assert source.access_count == {"alpha": 0, "beta": 0}


@pytest.mark.parametrize(
    "read",
    [
        pytest.param(lambda d: dict(d.items()), id="items"),
        pytest.param(
            lambda d: dict(zip(LAZY_ENTRIES, d.values(), strict=True)), id="values"
        ),
        pytest.param(dict, id="dict"),
        pytest.param(lambda d: {**d}, id="unpacking"),
        pytest.param(lambda d: dict(d.copy()), id="copy"),
    ],
)
def test_lazy_meta_dict_reads_pending_values(read) -> None:
    """Whatever reads every value resolves the pending keys, and sees them all."""
    source = _SourceSpy()

    assert read(_lazy_dict(source)) == LAZY_ENTRIES
    assert source.access_count == {"alpha": 1, "beta": 1}


def test_lazy_meta_dict_equality_reads_pending_values() -> None:
    """Equality compares every entry, pending ones included, on both sides."""
    d = _lazy_dict(_SourceSpy())

    assert d == LAZY_ENTRIES
    assert LAZY_ENTRIES == d
    assert d == _lazy_dict(_SourceSpy())
    assert d != {"existing.key": "existing-value"}


def test_lazy_meta_dict_copy_keeps_pending_keys_pending() -> None:
    """A copy lists the pending keys, and resolves them only when read."""
    source = _SourceSpy()
    copy = _lazy_dict(source).copy()

    assert list(copy) == list(LAZY_ENTRIES)
    assert source.access_count == {"alpha": 0, "beta": 0}
    assert copy["click_extra.alpha"] == "alpha-value"


@pytest.mark.parametrize(
    ("remove", "removed"),
    [
        pytest.param(
            lambda d: d.__delitem__("click_extra.alpha"),
            ("click_extra.alpha",),
            id="del",
        ),
        pytest.param(
            lambda d: d.pop("click_extra.alpha"), ("click_extra.alpha",), id="pop"
        ),
        pytest.param(lambda d: d.popitem(), ("click_extra.beta",), id="popitem"),
        pytest.param(lambda d: d.clear(), tuple(LAZY_ENTRIES), id="clear"),
    ],
)
def test_lazy_meta_dict_removed_key_stays_removed(remove, removed) -> None:
    """A pending key removed from the mapping does not come back."""
    d = _lazy_dict(_SourceSpy())

    remove(d)
    assert all(key not in d for key in removed)
    assert list(d) == [key for key in LAZY_ENTRIES if key not in removed]
    assert len(d) == len(LAZY_ENTRIES) - len(removed)


def test_lazy_meta_dict_pop_returns_pending_values() -> None:
    """``pop()`` and ``popitem()`` resolve the pending key they remove."""
    d = _lazy_dict(_SourceSpy())

    assert d.pop("click_extra.alpha") == "alpha-value"
    assert d.popitem() == ("click_extra.beta", "beta-value")
    assert d.popitem() == ("existing.key", "existing-value")
    assert d.pop("click_extra.alpha", "default") == "default"


def test_lazy_meta_dict_setdefault_resolves_pending_key() -> None:
    """``setdefault()`` keeps the value of a pending key rather than the default."""
    d = _lazy_dict(_SourceSpy())

    assert d.setdefault("click_extra.alpha", "fallback") == "alpha-value"
    assert d["click_extra.alpha"] == "alpha-value"
    assert d.setdefault("other.key", "fallback") == "fallback"


def test_lazy_meta_dict_wraps_another_without_resolving() -> None:
    """Wrapping a lazy dict, as each ``--version`` of a command tree does, keeps
    its pending keys pending.
    """
    source = _SourceSpy()

    outer = _LazyMetaDict(_lazy_dict(source), _SourceSpy(), ("alpha", "beta"))
    assert source.access_count == {"alpha": 0, "beta": 0}
    assert dict(outer) == LAZY_ENTRIES


def test_pass_context_typed_for_enhanced_context(invoke):
    """@pass_context accepts a handler typed with the enhanced Context.

    Click's own pass_context is typed for the base click.Context, so annotating
    the handler with click-extra's Context (to reach its extra helpers) would
    fail static type checks by parameter contravariance. This must both
    type-check (mypy covers this file) and forward the active enhanced Context
    at runtime.
    """
    from click_extra import command, echo, pass_context

    @command
    @pass_context
    def cli(ctx: Context) -> None:
        echo(type(ctx).__name__)

    result = invoke(cli)
    assert result.exit_code == 0
    assert result.stdout == "Context\n"
