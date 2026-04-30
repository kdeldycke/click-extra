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
"""Tests for :class:`click_extra.context.ExtraContext` and the central
``ctx.meta`` key registry."""

from __future__ import annotations

import click
from click.testing import CliRunner

from click_extra import context
from click_extra.context import ExtraContext


REGISTERED_KEYS = (
    context.RAW_ARGS,
    context.CONF_SOURCE,
    context.CONF_FULL,
    context.TOOL_CONFIG,
    context.VERBOSITY_LEVEL,
    context.VERBOSITY,
    context.VERBOSE,
    context.START_TIME,
    context.JOBS,
    context.TABLE_FORMAT,
    context.SORT_BY,
    context.THEME,
)


def test_keys_share_namespace():
    """Every Click Extra ``meta`` key lives under the ``click_extra.`` prefix."""
    for key in REGISTERED_KEYS:
        assert key.startswith("click_extra."), key


def test_keys_are_unique():
    """No two registry constants share a value."""
    assert len(set(REGISTERED_KEYS)) == len(REGISTERED_KEYS)


def test_get_returns_default_for_missing_key():
    """:func:`context.get` mirrors ``dict.get`` semantics."""

    @click.command
    @click.pass_context
    def cli(ctx):
        sentinel = object()
        assert context.get(ctx, "click_extra.does_not_exist", sentinel) is sentinel
        assert context.get(ctx, "click_extra.does_not_exist") is None

    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0


def test_set_then_get_round_trip():
    """:func:`context.set` is observable through :func:`context.get`."""

    @click.command
    @click.pass_context
    def cli(ctx):
        context.set(ctx, context.JOBS, 7)
        assert context.get(ctx, context.JOBS) == 7

    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0


# --- ExtraContext color behavior ---


def test_extra_context_root_defaults_color_true():
    """Root ExtraContext without color= arg defaults to color=True."""
    ctx = ExtraContext(click.Command("test"))
    assert ctx.color is True


def test_extra_context_inherits_from_parent():
    """Child ExtraContext inherits color from parent when not set."""
    parent = ExtraContext(click.Command("parent"), color=False)
    child = ExtraContext(click.Command("child"), parent=parent)
    assert child.color is False


def test_extra_context_explicit_overrides_parent():
    """Child ExtraContext with explicit color overrides parent."""
    parent = ExtraContext(click.Command("parent"), color=True)
    child = ExtraContext(click.Command("child"), parent=parent, color=False)
    assert child.color is False
