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
"""Tests multicall / `argv[0]` dispatch and the invocation-name hook."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from enum import Enum

import pytest

from click_extra import (
    UNSET,
    argument,
    command,
    context,
    echo,
    multicall_group,
    option,
    pass_context,
)
from click_extra.multicall import _deepcopy_params, normalize_personality
from click_extra.version import VersionOption


def make_kitchen(
    personalities: Mapping[str, str | Sequence[str]] | None = None,
    **group_kwargs,
):
    """A fresh multicall CLI per test, to keep process-global state from leaking.

    The domain is deliberately a kitchen: the test suite asserts dispatch
    mechanics, not any real tool's behavior.
    """

    @multicall_group(personalities=personalities, **group_kwargs)
    def kitchen():
        """A multicall kitchen appliance."""
        echo("group callback ran")

    @kitchen.command()
    @option("--temperature", default="180")
    @argument("dishes", nargs=-1)
    def bake(temperature, dishes):
        """Bake dishes in the oven."""
        echo(f"Baking at {temperature}: {', '.join(dishes) or 'nothing'}")

    @kitchen.command(hidden=True)
    def defrost():
        """Defrost ingredients."""
        echo("defrosting")

    @kitchen.command()
    @option("--hours", default="2")
    @argument("bottles", nargs=-1)
    def chill(hours, bottles):
        """Chill bottles in the fridge."""
        echo(f"Chilling for {hours} hours: {', '.join(bottles) or 'nothing'}")

    return kitchen


def test_argv0_dispatch(runner, monkeypatch):
    """With no explicit `prog_name`, the basename of `argv[0]` dispatches."""
    kitchen = make_kitchen()
    monkeypatch.setattr("sys.argv", ["/usr/local/bin/bake"])
    result = runner.invoke(
        kitchen, ["--temperature", "230"], prog_name=None, color=False
    )
    assert result.exit_code == 0
    assert "Baking at 230" in result.stdout


def test_env_prefix_follows_personality(runner):
    """A personality reads its own `<NAME>_*` envvars, like a standalone binary."""
    kitchen = make_kitchen()
    result = runner.invoke(
        kitchen, [], prog_name="bake", env={"BAKE_TEMPERATURE": "250"}, color=False
    )
    assert result.exit_code == 0
    assert "Baking at 250" in result.stdout


def test_explicit_mapping_replaces_identity(runner):
    """An explicit `personalities` mapping is exhaustive, not additive."""
    kitchen = make_kitchen(personalities={"quick-chill": ("chill", "--hours", "1")})
    result = runner.invoke(kitchen, [], prog_name="quick-chill", color=False)
    assert result.exit_code == 0
    assert "Chilling for 1 hours" in result.stdout

    # `bake` is no longer a personality: the invocation falls through to the
    # group, which rejects the bare call with its usage screen.
    result = runner.invoke(kitchen, [], prog_name="bake", color=False)
    assert result.exit_code == 2
    assert "Usage:" in result.output


def test_explicit_prog_name_wins(runner, monkeypatch):
    """An explicit `prog_name` takes precedence over `argv[0]`."""
    kitchen = make_kitchen()
    monkeypatch.setattr("sys.argv", ["/usr/local/bin/chill"])
    result = runner.invoke(kitchen, [], prog_name="bake", color=False)
    assert result.exit_code == 0
    assert "Baking" in result.stdout


def test_extra_tokens_prepended(runner):
    """Personality tokens are prepended to the user's arguments."""
    kitchen = make_kitchen(personalities={"chill-fast": ("chill", "--hours", "1")})
    result = runner.invoke(kitchen, ["soda"], prog_name="chill-fast", color=False)
    assert result.exit_code == 0
    assert "Chilling for 1 hours: soda" in result.stdout


def test_flat_parse_any_order(runner):
    """Group and subcommand options mix freely in a personality."""
    kitchen = make_kitchen()
    for args in (
        ["--verbosity", "INFO", "--temperature", "200", "pie"],
        ["--temperature", "200", "--verbosity", "INFO", "pie"],
        ["pie", "--temperature", "200", "--verbosity", "INFO"],
    ):
        result = runner.invoke(kitchen, args, prog_name="bake", color=False)
        assert result.exit_code == 0
        assert "Baking at 200: pie" in result.stdout


def test_group_callback_skipped_in_personality_mode(runner):
    """A personality is standalone: the group's callback does not run."""
    kitchen = make_kitchen()
    result = runner.invoke(kitchen, [], prog_name="bake", color=False)
    assert result.exit_code == 0
    assert "group callback ran" not in result.output

    result = runner.invoke(kitchen, ["bake"], color=False)
    assert result.exit_code == 0
    assert "group callback ran" in result.output


def test_group_mode_unchanged(runner):
    """A non-matching invocation name leaves the regular group behavior intact."""
    kitchen = make_kitchen()
    result = runner.invoke(kitchen, ["--help"], color=False)
    assert result.exit_code == 0
    assert "bake" in result.stdout
    assert "chill" in result.stdout
    assert "defrost" not in result.stdout

    result = runner.invoke(
        kitchen, ["bake", "--temperature", "210", "tart"], color=False
    )
    assert result.exit_code == 0
    assert "Baking at 210: tart" in result.stdout

    # A name matching no personality falls through to the group as well.
    result = runner.invoke(kitchen, ["bake"], prog_name="oven", color=False)
    assert result.exit_code == 0
    assert "Baking" in result.stdout


def test_help_conformance(runner):
    """A personality's help lists every option the group's help lists.

    This is what catches the Cloup layout trap: patching `params` on a copy
    updates the parser but not the help formatter, which is computed from
    `params` at `__init__` time.
    """
    kitchen = make_kitchen()

    def option_flags(output):
        return set(re.findall(r"^\s{2}(-{1,2}\S+)", output, re.MULTILINE))

    group_flags = option_flags(runner.invoke(kitchen, ["--help"], color=False).stdout)
    personality_flags = option_flags(
        runner.invoke(kitchen, ["--help"], prog_name="bake", color=False).stdout
    )
    assert group_flags <= personality_flags
    assert "--temperature" in personality_flags


def test_hidden_subcommand_is_not_a_default_personality(runner):
    """The default identity mapping skips hidden and synthetic subcommands."""
    kitchen = make_kitchen()
    assert kitchen.match_personality("defrost") is None
    assert kitchen.match_personality("help") is None
    assert kitchen.match_personality("personalities") is None
    assert kitchen.match_personality("bake") == ("bake",)
    assert sorted(kitchen.list_personalities()) == ["bake", "chill"]


def test_invocation_name_meta_key(runner):
    """`ctx.meta` exposes the invocation name on the root context."""

    @command
    @pass_context
    def spy(ctx):
        echo(ctx.meta[context.INVOCATION_NAME])

    result = runner.invoke(spy, [], prog_name="greet", color=False)
    assert result.exit_code == 0
    assert result.stdout.strip() == "greet"

    # Without an explicit name, the command's own name is the invocation name.
    result = runner.invoke(spy, [], color=False)
    assert result.exit_code == 0
    assert result.stdout.strip() == "spy"

    # A personality carries its own name, not the group's.
    @multicall_group()
    def pair():
        """Two names, one binary."""

    @pair.command()
    @pass_context
    def report(ctx):
        echo(ctx.meta[context.INVOCATION_NAME])

    result = runner.invoke(pair, [], prog_name="report", color=False)
    assert result.exit_code == 0
    assert result.stdout.strip() == "report"

    result = runner.invoke(pair, ["report"], color=False)
    assert result.exit_code == 0
    assert result.stdout.strip() == "pair"


def test_no_envvar_leak_into_group_mode(runner):
    """Building a personality must not rewrite the original params' envvars."""
    kitchen = make_kitchen(personalities={"quick-bake": ("bake", "--temperature", "1")})
    result = runner.invoke(kitchen, [], prog_name="quick-bake", color=False)
    assert result.exit_code == 0

    # The group's options keep their `KITCHEN_*` auto envvars.
    verbosity = next(
        p for p in kitchen.params if "--verbosity" in getattr(p, "opts", [])
    )
    assert verbosity.envvar is not None
    assert all(var.startswith("KITCHEN_") for var in verbosity.envvar)

    # The subcommand's options keep their own `BAKE_*` auto envvars.
    temperature = next(
        p
        for p in kitchen.commands["bake"].params
        if "--temperature" in getattr(p, "opts", [])
    )
    assert temperature.envvar is not None
    assert all(var.startswith("BAKE_") for var in temperature.envvar)


@pytest.mark.parametrize(
    ("argv0", "expected"),
    [
        ("/usr/local/bin/bake", "bake"),
        ("/usr/local/bin/bake.exe", "bake"),
        ("/usr/local/bin/BAKE.EXE", "BAKE"),
        ("bake", "bake"),
        ("", None),
    ],
)
def test_resolve_invocation_name(runner, monkeypatch, argv0, expected):
    """The detector uses the unresolved basename and strips `.exe`."""
    kitchen = make_kitchen()
    monkeypatch.setattr("sys.argv", [argv0])
    assert kitchen.resolve_invocation_name() == expected
    # An explicit name always wins.
    assert kitchen.resolve_invocation_name("chill") == "chill"


def test_unknown_subcommand_in_mapping(runner):
    """A personality mapping an absent subcommand fails loudly at dispatch."""
    kitchen = make_kitchen(personalities={"ghost": "missing"})
    result = runner.invoke(kitchen, [], prog_name="ghost", color=False)
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)


def test_version_names_each_personality(runner):
    """Each personality's `--version` names itself, in sequence.

    Regression test: `VersionOption` used to cache `prog_name` on the
    instance, pinning the first name seen in a process forever. The warm-up
    invocation with debug logging matters: it resolves every version field
    without anyone calling `--version` at all.
    """
    kitchen = make_kitchen()

    result = runner.invoke(kitchen, ["--version"], prog_name="bake", color=False)
    assert result.exit_code == 0
    assert result.output.startswith("bake, version ")

    result = runner.invoke(
        kitchen, ["--verbosity", "DEBUG"], prog_name="bake", color=False
    )
    assert result.exit_code == 0

    result = runner.invoke(kitchen, ["--version"], prog_name="chill", color=False)
    assert result.exit_code == 0
    assert result.output.startswith("chill, version ")


def test_version_prog_name_varies_without_multicall(runner):
    """`--version` follows an explicit `prog_name` even in plain group mode."""
    kitchen = make_kitchen()
    result = runner.invoke(kitchen, ["--version"], prog_name="kitchen", color=False)
    assert result.exit_code == 0
    assert result.output.startswith("kitchen, version ")

    result = runner.invoke(kitchen, ["--version"], prog_name="toaster", color=False)
    assert result.exit_code == 0
    assert result.output.startswith("toaster, version ")


def test_personalities_subcommand(runner):
    """The auto-injected `personalities` subcommand lists the names."""
    kitchen = make_kitchen(personalities={"quick-chill": ("chill", "--hours", "1")})
    result = runner.invoke(kitchen, ["personalities"], color=False)
    assert result.exit_code == 0
    assert "quick-chill" in result.stdout
    assert "chill --hours 1" in result.stdout

    # The group's help lists it as a regular subcommand.
    result = runner.invoke(kitchen, ["--help"], color=False)
    assert "personalities" in result.stdout


def test_personalities_command_can_be_disabled(runner):
    """`personalities_command=False` suppresses the listing subcommand."""
    kitchen = make_kitchen(personalities_command=False)
    assert "personalities" not in kitchen.commands
    result = runner.invoke(kitchen, ["--help"], color=False)
    assert "personalities" not in result.stdout


def test_normalize_personality():
    """Personality values normalize to non-empty token tuples."""
    assert normalize_personality("chill") == ("chill",)
    assert normalize_personality(("chill", "--hours", "1")) == ("chill", "--hours", "1")

    bad: Sequence[str]
    for bad in ((), [], ("",), ("chill", "")):
        with pytest.raises(ValueError):
            normalize_personality(bad)
    with pytest.raises(TypeError):
        normalize_personality(42)


def test_deepcopy_params_keeps_every_sentinel_identical():
    """A copied parameter carries its enum members over, it does not rebuild them.

    An enum member is a singleton, so a copy handing back an equal-but-distinct
    one is already wrong. Python 3.10 does exactly that, rebuilding the member
    from a deep copy of its value, which the `object()` behind a
    [PEP 661](https://peps.python.org/pep-0661/) sentinel never survives. Walking
    the whole default option set catches the next parameter to grow one.
    """
    kitchen = make_kitchen()
    clones = _deepcopy_params(kitchen.params)
    assert len(clones) == len(kitchen.params)

    # Pair by position, not by name: `--config` and `--no-config` share the
    # `config` destination, so a name lookup matches the wrong parameter. Read
    # the stored attribute rather than the resolved one, since `ConfigOption`
    # answers `default` with a bound method computing the pattern.
    guarded = 0
    for source, clone in zip(kitchen.params, clones, strict=True):
        for attribute, value in vars(source).items():
            if not isinstance(value, Enum):
                continue
            guarded += 1
            assert vars(clone)[attribute] is value, (
                f"{source.name}.{attribute} was rebuilt instead of carried over."
            )
    assert guarded, "No enum-valued parameter attribute left to guard."


def test_version_option_deepcopy_drops_cache():
    """Deepcopying a warmed-up `VersionOption` yields fresh field resolution."""
    kitchen = make_kitchen()
    version_option = next(p for p in kitchen.params if isinstance(p, VersionOption))
    # Warm the cache with a process-constant field.
    _ = version_option.package_version
    clone = copy.deepcopy(version_option)
    assert clone is not version_option
    assert "package_version" not in clone.__dict__
    # Configuration state survives the copy.
    assert clone.message == version_option.message


def test_deepcopy_survives_the_python_310_enum_gap(monkeypatch):
    """Both copy entry points hold on an interpreter with no `Enum` copy hooks.

    Python 3.11 gave `Enum` a `__deepcopy__` handing the member back, which
    hides the whole problem: on 3.10 `copy.deepcopy` rebuilds a member from a
    deep copy of its *value* instead, and the bare `object()` behind Click's
    `UNSET` never survives that. Stripping the two hooks pins the guard on
    every interpreter rather than only on the floor, where CI alone would
    catch it.
    """
    monkeypatch.delattr(Enum, "__deepcopy__", raising=False)
    monkeypatch.delattr(Enum, "__copy__", raising=False)

    kitchen = make_kitchen()
    version_option = next(p for p in kitchen.params if isinstance(p, VersionOption))
    # Click stores a parameter's unset default as a `Sentinel` member from 8.5
    # on; the older releases still inside the supported range leave `__dict__`
    # free of one. Seed a member there when Click did not, so the copy below has
    # an enum to survive whatever Click is installed: without one in `__dict__`
    # this test guards nothing.
    if not any(isinstance(value, Enum) for value in vars(version_option).values()):
        version_option.__dict__["_unset_default_probe"] = UNSET
    assert any(isinstance(value, Enum) for value in vars(version_option).values())

    # A bare copy reaches `VersionOption.__deepcopy__` with an empty memo, so it
    # has to seed one for itself.
    assert copy.deepcopy(version_option) is not version_option
    # The multicall path seeds the memo before the copy starts.
    assert len(_deepcopy_params(kitchen.params)) == len(kitchen.params)
