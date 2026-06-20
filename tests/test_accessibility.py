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

from __future__ import annotations

import click
import pytest

import click_extra
from click_extra import (
    AccessibleOption,
    Color,
    accessible_option,
    color_option,
    command,
    echo,
    pass_context,
    style,
    table_format_option,
)
from click_extra.commands import default_extra_params
from click_extra.context import ACCESSIBLE, TABLE_FORMAT


@pytest.fixture
def report_cli():
    """An extra command that echoes the resolved color flag and table format,
    then renders a table with a styled cell."""

    @command
    @pass_context
    def report(ctx):
        echo(f"color={ctx.color}")
        echo(f"table_format={ctx.meta.get(TABLE_FORMAT)}")
        ctx.print_table(
            ((style("apple", fg=Color.red), "red"),),
            headers=("fruit", "color"),
        )

    return report


@pytest.mark.once
def test_default_params_include_accessible():
    assert any(isinstance(p, AccessibleOption) for p in default_extra_params())


@pytest.mark.parametrize(
    ("extra_args", "expected_color", "expected_format"),
    (
        # Untouched defaults: the GNU auto default leaves ctx.color at None.
        ((), "color=None", "table_format=rounded-outline"),
        # --accessible lowers both defaults.
        (("--accessible",), "color=False", "table_format=plain"),
        # An explicit color flag keeps precedence over --accessible.
        (("--accessible", "--color"), "color=True", "table_format=plain"),
        (("--accessible", "--no-color"), "color=False", "table_format=plain"),
        # An explicit table format keeps precedence over --accessible.
        (
            ("--accessible", "--table-format", "github"),
            "color=False",
            "table_format=github",
        ),
        # Each underlying option still works on its own.
        (("--no-color",), "color=False", "table_format=rounded-outline"),
    ),
)
def test_accessible_precedence(
    invoke, report_cli, extra_args, expected_color, expected_format
):
    result = invoke(report_cli, *extra_args, color=True)
    assert result.exit_code == 0
    assert expected_color in result.stdout
    assert expected_format in result.stdout


def test_accessible_via_envvar(invoke, report_cli):
    result = invoke(report_cli, color=True, env={"ACCESSIBLE": "1"})
    assert result.exit_code == 0
    assert "color=False" in result.stdout
    assert "table_format=plain" in result.stdout


def test_explicit_flag_overrides_accessible_envvar(invoke, report_cli):
    result = invoke(report_cli, "--color", color=True, env={"ACCESSIBLE": "1"})
    assert result.exit_code == 0
    assert "color=True" in result.stdout
    # The table format is still lowered: only the color flag was overridden.
    assert "table_format=plain" in result.stdout


def test_default_renders_box_drawing_and_ansi(invoke, report_cli):
    result = invoke(report_cli, color=True)
    assert "│" in result.stdout
    assert "\x1b[" in result.stdout


def test_accessible_strips_box_drawing_and_ansi(invoke, report_cli):
    result = invoke(report_cli, "--accessible", color=True)
    assert "│" not in result.stdout
    assert "╭" not in result.stdout
    assert "\x1b[" not in result.stdout


def test_standalone_decorator_on_plain_click_command(invoke):
    """``--accessible`` lowers the defaults of the sibling color and table options,
    so they must be composed alongside it on a plain ``click.command``."""

    @click.command
    @accessible_option
    @color_option
    @table_format_option
    @pass_context
    def standalone(ctx):
        echo(f"color={ctx.color}")
        echo(f"table_format={ctx.meta.get(TABLE_FORMAT)}")

    result = invoke(standalone, "--accessible", color=True)
    assert result.exit_code == 0
    assert "color=False" in result.stdout
    assert "table_format=plain" in result.stdout


@pytest.mark.parametrize(
    ("args", "expected"),
    (((), False), (("--accessible",), True)),
)
def test_accessible_flag_published_to_context(invoke, args, expected):
    """set_accessible publishes the resolved intent at ctx.meta[ACCESSIBLE]."""

    @command
    @pass_context
    def cli(ctx):
        echo(f"accessible={ctx.meta.get(ACCESSIBLE)}")

    result = invoke(cli, *args)
    assert f"accessible={expected}" in result.stdout


def test_clear_is_noop_under_accessible(invoke, monkeypatch):
    """clear() defers to click.clear normally, but no-ops under --accessible."""
    calls = []
    monkeypatch.setattr(click, "clear", lambda: calls.append(1))

    @command
    def cli():
        click_extra.clear()

    assert invoke(cli).exit_code == 0
    assert calls == [1]  # Deferred to click.clear.

    calls.clear()
    assert invoke(cli, "--accessible").exit_code == 0
    assert calls == []  # Bypassed.


def test_echo_via_pager_streams_plainly_under_accessible(invoke, monkeypatch):
    """echo_via_pager pages normally, but writes straight to stdout under --accessible."""
    paged = []
    monkeypatch.setattr(click, "echo_via_pager", lambda *a, **k: paged.append(a))

    def fruit_pages():
        yield "kiwi\n"
        yield "mango\n"

    @command
    def cli():
        click_extra.echo_via_pager("apricot\n")  # str
        click_extra.echo_via_pager(fruit_pages)  # generator function
        click_extra.echo_via_pager(["pear\n", "plum\n"])  # iterable

    # Normal mode: every call is handed to the pager.
    result = invoke(cli)
    assert result.exit_code == 0
    assert len(paged) == 3

    # Accessible mode: the pager is bypassed and the text streamed in order.
    paged.clear()
    result = invoke(cli, "--accessible")
    assert result.exit_code == 0
    assert paged == []
    assert result.stdout == "apricot\nkiwi\nmango\npear\nplum\n"


def test_pager_and_clear_defer_without_accessible_option(invoke, monkeypatch):
    """With no --accessible option wired, the wrappers defer to Click unchanged."""
    paged, cleared = [], []
    monkeypatch.setattr(click, "echo_via_pager", lambda *a, **k: paged.append(a))
    monkeypatch.setattr(click, "clear", lambda: cleared.append(1))

    @click.command
    def standalone():
        click_extra.echo_via_pager("apricot\n")
        click_extra.clear()

    result = invoke(standalone)
    assert result.exit_code == 0
    assert len(paged) == 1
    assert cleared == [1]
