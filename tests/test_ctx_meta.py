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
"""Integrity tests for the central ``ctx.meta`` key registry."""

from __future__ import annotations

import click
from click.testing import CliRunner

from click_extra import ctx_meta


REGISTERED_KEYS = (
    ctx_meta.RAW_ARGS,
    ctx_meta.CONF_SOURCE,
    ctx_meta.CONF_FULL,
    ctx_meta.TOOL_CONFIG,
    ctx_meta.VERBOSITY_LEVEL,
    ctx_meta.VERBOSITY,
    ctx_meta.VERBOSE,
    ctx_meta.START_TIME,
    ctx_meta.JOBS,
    ctx_meta.TABLE_FORMAT,
    ctx_meta.SORT_BY,
    ctx_meta.THEME,
)


def test_keys_share_namespace():
    """Every Click Extra ``meta`` key lives under the ``click_extra.`` prefix."""
    for key in REGISTERED_KEYS:
        assert key.startswith("click_extra."), key


def test_keys_are_unique():
    """No two registry constants share a value."""
    assert len(set(REGISTERED_KEYS)) == len(REGISTERED_KEYS)


def test_get_returns_default_for_missing_key():
    """:func:`ctx_meta.get` mirrors ``dict.get`` semantics."""

    @click.command
    @click.pass_context
    def cli(ctx):
        sentinel = object()
        assert ctx_meta.get(ctx, "click_extra.does_not_exist", sentinel) is sentinel
        assert ctx_meta.get(ctx, "click_extra.does_not_exist") is None

    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0


def test_set_then_get_round_trip():
    """:func:`ctx_meta.set` is observable through :func:`ctx_meta.get`."""

    @click.command
    @click.pass_context
    def cli(ctx):
        ctx_meta.set(ctx, ctx_meta.JOBS, 7)
        assert ctx_meta.get(ctx, ctx_meta.JOBS) == 7

    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0
